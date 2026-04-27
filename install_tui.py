#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "rich>=13.0.0",
#   "questionary>=2.0.0",
# ]
# ///
"""
Linux Environment Setup TUI

Robust, idempotent installer for a Debian/Ubuntu workstation:
zsh + Oh-My-Zsh + Powerlevel10k, Terminator with Dracula theme,
Nerd Fonts, Neovim from source + LazyVim, SSH keys + Git config.

Bootstraps its own dependencies via `uv` (auto-installed if missing).
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Bootstrap: ensure uv + dependencies are present, then re-exec under uv run.
# ---------------------------------------------------------------------------

MIN_PY = (3, 9)


def _bootstrap() -> None:
    if sys.version_info < MIN_PY:
        sys.stderr.write(
            f"[!] Python {MIN_PY[0]}.{MIN_PY[1]}+ required, found "
            f"{sys.version_info.major}.{sys.version_info.minor}\n"
        )
        sys.exit(2)

    try:
        import rich  # noqa: F401
        import questionary  # noqa: F401
        return
    except ImportError:
        pass

    print("[*] Bootstrapping environment with 'uv'...")

    uv = shutil.which("uv")
    if not uv:
        print("    -> 'uv' not found. Installing...")
        try:
            subprocess.run(
                "curl -LsSf https://astral.sh/uv/install.sh | sh",
                shell=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"[!] Failed to install uv: {exc}")
            sys.exit(1)

        for candidate in (
            Path.home() / ".local" / "bin",
            Path.home() / ".cargo" / "bin",
        ):
            if (candidate / "uv").exists():
                os.environ["PATH"] = f"{candidate}:{os.environ.get('PATH', '')}"
                uv = str(candidate / "uv")
                break

        if not uv:
            uv = shutil.which("uv")
        if not uv:
            print("[!] uv installed but not found on PATH. Add ~/.local/bin to PATH and retry.")
            sys.exit(1)

    print("    -> Re-launching under 'uv run'...")
    os.execvp(uv, [uv, "run", "--script", os.path.abspath(sys.argv[0]), *sys.argv[1:]])


_bootstrap()

# ---------------------------------------------------------------------------
# Imports that depend on bootstrap.
# ---------------------------------------------------------------------------

import questionary
import rich.box
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Constants & paths.
# ---------------------------------------------------------------------------

HOME = Path.home()
CONFIG_DIR = HOME / ".config"
LOCAL_DIR = HOME / ".local"
SSH_DIR = HOME / ".ssh"
LOG_DIR = HOME / ".local" / "state" / "linux-setup-tui"
LOG_FILE = LOG_DIR / "install.log"

STYLE_ACCENT = "bold #d97757"
STYLE_DIM = "dim white"
STYLE_OK = "bold green"
STYLE_ERR = "bold red"
STYLE_WARN = "bold yellow"

console = Console()

# ---------------------------------------------------------------------------
# Logging. Console gets short messages; file gets full detail incl. command output.
# ---------------------------------------------------------------------------


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("setup")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(file_handler)

    rich_handler = RichHandler(
        console=console, show_time=False, show_level=False, show_path=False, markup=True
    )
    rich_handler.setLevel(logging.WARNING)
    logger.addHandler(rich_handler)

    logger.propagate = False
    logger.debug("==== run started %s ====", time.strftime("%Y-%m-%d %H:%M:%S"))
    return logger


log = _setup_logging()


def step(msg: str) -> None:
    console.print(f"  [{STYLE_ACCENT}]•[/] {msg}")
    log.debug("STEP: %s", msg)


def ok(msg: str) -> None:
    console.print(f"  [{STYLE_OK}]✓[/] {msg}")
    log.info(msg)


def warn(msg: str) -> None:
    console.print(f"  [{STYLE_WARN}]![/] {msg}")
    log.warning(msg)


def err(msg: str) -> None:
    console.print(f"  [{STYLE_ERR}]✗[/] {msg}")
    log.error(msg)


# ---------------------------------------------------------------------------
# Command runner. Always logs full output; surfaces failures with stderr tail.
# ---------------------------------------------------------------------------


@dataclass
class CmdResult:
    ok: bool
    code: int
    stdout: str
    stderr: str

    def __bool__(self) -> bool:  # pragma: no cover
        return self.ok


def run_cmd(
    cmd: list[str] | str,
    *,
    sudo: bool = False,
    shell: bool = False,
    cwd: str | Path | None = None,
    capture: bool = True,
    check: bool = False,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> CmdResult:
    """Run a command. Logs everything. Returns CmdResult instead of raising by default."""
    if sudo and os.geteuid() != 0:
        # We pre-prime sudo at startup; let it prompt here if the cache expired
        # rather than running the real command speculatively to probe.
        cmd = (["sudo", *cmd]) if isinstance(cmd, list) else f"sudo {cmd}"

    log.debug("RUN: %s (cwd=%s capture=%s)", cmd, cwd, capture)
    try:
        proc = subprocess.run(
            cmd,
            shell=shell,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        err(f"Command timed out after {timeout}s: {exc.cmd!r}")
        return CmdResult(False, -1, "", f"timeout after {timeout}s")
    except FileNotFoundError as exc:
        err(f"Command not found: {exc}")
        return CmdResult(False, 127, "", str(exc))

    stdout = (proc.stdout or "") if capture else ""
    stderr = (proc.stderr or "") if capture else ""

    if stdout:
        log.debug("STDOUT:\n%s", stdout)
    if stderr:
        log.debug("STDERR:\n%s", stderr)

    if proc.returncode != 0:
        # Surface a short tail of stderr so the user has a clue.
        tail = "\n".join((stderr or stdout).strip().splitlines()[-10:])
        if tail:
            console.print(f"    [{STYLE_DIM}]{tail}[/]")
        if check:
            raise RuntimeError(f"Command failed (exit {proc.returncode}): {cmd}")
        return CmdResult(False, proc.returncode, stdout, stderr)

    return CmdResult(True, 0, stdout, stderr)


def with_retries(
    fn: Callable[[], CmdResult], *, attempts: int = 3, delay: float = 2.0, label: str = "command"
) -> CmdResult:
    last: CmdResult | None = None
    for attempt in range(1, attempts + 1):
        result = fn()
        if result.ok:
            return result
        last = result
        if attempt < attempts:
            warn(f"{label} failed (attempt {attempt}/{attempts}); retrying in {delay:.0f}s")
            time.sleep(delay)
            delay *= 1.5
    return last or CmdResult(False, -1, "", "no attempts made")


# ---------------------------------------------------------------------------
# Pre-flight checks.
# ---------------------------------------------------------------------------


@dataclass
class Preflight:
    is_linux: bool
    has_apt: bool
    has_internet: bool
    has_sudo: bool
    distro: str
    free_gb: float

    @property
    def fatal(self) -> list[str]:
        problems = []
        if not self.is_linux:
            problems.append(f"Unsupported OS: {platform.system()}")
        if not self.has_apt:
            problems.append("apt-get not found (Debian/Ubuntu required)")
        if not self.has_internet:
            problems.append("No internet connectivity (required for downloads)")
        if self.free_gb < 1.0:
            problems.append(f"Insufficient disk space in $HOME: {self.free_gb:.1f} GB free")
        return problems

    @property
    def warnings(self) -> list[str]:
        out = []
        if not self.has_sudo:
            out.append("sudo not available without password — you'll be prompted")
        return out


def preflight() -> Preflight:
    is_linux = platform.system() == "Linux"
    has_apt = shutil.which("apt-get") is not None
    has_internet = _check_internet()
    has_sudo = _check_sudo()
    distro = _detect_distro()
    free_gb = shutil.disk_usage(str(HOME)).free / (1024**3)
    return Preflight(is_linux, has_apt, has_internet, has_sudo, distro, free_gb)


def _check_internet() -> bool:
    try:
        with socket.create_connection(("github.com", 443), timeout=5):
            return True
    except OSError:
        return False


def _check_sudo() -> bool:
    if os.geteuid() == 0:
        return True
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=3).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _detect_distro() -> str:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return "unknown"
    for line in os_release.read_text().splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


# ---------------------------------------------------------------------------
# Configuration model & component metadata.
# ---------------------------------------------------------------------------


@dataclass
class UserConfig:
    name: str = ""
    email: str = ""
    assume_yes: bool = False
    dry_run: bool = False


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "skipped" | "failed"
    detail: str = ""


@dataclass
class Component:
    key: str
    label: str
    requires: tuple[str, ...] = ()
    default: bool = True


COMPONENTS: list[Component] = [
    Component("base", "Base packages (git, curl, build-essential, …)"),
    Component("zsh", "Zsh + Oh My Zsh", requires=("base",)),
    Component("p10k", "Powerlevel10k + Nerd Fonts", requires=("zsh",)),
    Component("terminator", "Terminator with Dracula theme", requires=("base",)),
    Component("nvim", "Neovim from source + LazyVim", requires=("base",)),
    Component("ssh", "SSH keys + Git config", requires=("base",)),
]


def resolve_dependencies(selected: Iterable[str]) -> list[str]:
    """Return ordered list of components, including transitive dependencies."""
    sel = set(selected)
    by_key = {c.key: c for c in COMPONENTS}
    added = True
    while added:
        added = False
        for key in list(sel):
            for dep in by_key[key].requires:
                if dep not in sel:
                    sel.add(dep)
                    added = True
                    warn(f"'{key}' requires '{dep}' — adding it")
    return [c.key for c in COMPONENTS if c.key in sel]


# ---------------------------------------------------------------------------
# Installer.
# ---------------------------------------------------------------------------


class Installer:
    def __init__(self, config: UserConfig) -> None:
        self.cfg = config
        self.results: list[StepResult] = []

    # -------- helpers ------------------------------------------------------

    def _record(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(StepResult(name, status, detail))

    def _ensure_zshrc(self) -> Path | None:
        zshrc = HOME / ".zshrc"
        if zshrc.exists():
            return zshrc
        warn("~/.zshrc not found; creating a minimal one")
        zshrc.write_text("# created by linux-setup-tui\n")
        return zshrc

    # -------- steps --------------------------------------------------------

    def install_base_packages(self) -> bool:
        packages = [
            "git", "curl", "wget", "ca-certificates", "build-essential",
            "pkg-config", "libtool", "libtool-bin", "autoconf", "automake",
            "cmake", "g++", "unzip", "gettext", "ninja-build", "doxygen",
            "zsh", "terminator", "fonts-powerline", "ripgrep", "fd-find",
            "xclip",
        ]
        step("Updating apt cache…")
        if self.cfg.dry_run:
            ok(f"[dry-run] would install {len(packages)} packages")
            self._record("base", "skipped", "dry-run")
            return True

        if not run_cmd(["apt-get", "update", "-y"], sudo=True, capture=False):
            err("apt-get update failed")
            self._record("base", "failed", "apt update")
            return False

        step(f"Installing {len(packages)} packages…")
        env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        result = run_cmd(
            ["apt-get", "install", "-y", *packages],
            sudo=True,
            capture=False,
            env=env,
            timeout=1800,
        )
        if result.ok:
            ok("Base packages installed")
            self._record("base", "ok")
            return True
        err("apt-get install failed (see log)")
        self._record("base", "failed", "apt install")
        return False

    def setup_zsh(self) -> bool:
        zsh_path = shutil.which("zsh")
        if not zsh_path:
            err("zsh not on PATH; install base packages first")
            self._record("zsh", "failed", "zsh not found")
            return False

        if "zsh" not in (os.environ.get("SHELL") or ""):
            if self.cfg.dry_run:
                ok(f"[dry-run] would chsh to {zsh_path}")
            else:
                step(f"Setting default shell to {zsh_path}")
                # `chsh` reads from /etc/passwd via PAM; let it prompt the user.
                result = run_cmd(["chsh", "-s", zsh_path, os.environ["USER"]], capture=False)
                if result.ok:
                    ok("Default shell changed (re-login to take effect)")
                else:
                    warn(f"chsh failed; run manually: chsh -s {zsh_path}")
        else:
            ok("Zsh already the default shell")

        omz = HOME / ".oh-my-zsh"
        if omz.exists():
            ok("Oh My Zsh already installed")
        elif self.cfg.dry_run:
            ok("[dry-run] would install Oh My Zsh")
        else:
            step("Installing Oh My Zsh (unattended)…")
            install_url = "https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
            cmd = (
                f'sh -c "$(curl -fsSL {install_url})" "" --unattended --keep-zshrc'
            )
            res = with_retries(
                lambda: run_cmd(cmd, shell=True),
                attempts=3,
                label="Oh My Zsh install",
            )
            if not res.ok:
                err("Oh My Zsh install failed")
                self._record("zsh", "failed", "omz install")
                return False
            ok("Oh My Zsh installed")

        self._configure_zsh_plugins()
        self._record("zsh", "ok")
        return True

    def _configure_zsh_plugins(self) -> None:
        custom = HOME / ".oh-my-zsh" / "custom"
        plugins_dir = custom / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        plugins = {
            "zsh-autosuggestions": "https://github.com/zsh-users/zsh-autosuggestions",
            "zsh-completions": "https://github.com/zsh-users/zsh-completions",
        }
        for name, url in plugins.items():
            target = plugins_dir / name
            if target.exists():
                run_cmd(["git", "-C", str(target), "pull", "--ff-only"])
            else:
                step(f"Cloning {name}…")
                with_retries(
                    lambda u=url, t=target: run_cmd(["git", "clone", "--depth=1", u, str(t)]),
                    attempts=3,
                    label=f"clone {name}",
                )

        zshrc = self._ensure_zshrc()
        if zshrc is None:
            return
        content = zshrc.read_text()
        original = content

        if re.search(r"^plugins=\(", content, re.MULTILINE):
            for plugin in plugins:
                if plugin not in content:
                    content = re.sub(
                        r"(^plugins=\([^\)]*)(\))",
                        rf"\1 {plugin}\2",
                        content,
                        count=1,
                        flags=re.MULTILINE,
                    )
        else:
            content += "\nplugins=(git zsh-autosuggestions zsh-completions)\n"

        fpath_marker = "# linux-setup-tui: zsh-completions fpath"
        if fpath_marker not in content:
            content += (
                f"\n{fpath_marker}\n"
                'fpath+=("$HOME/.oh-my-zsh/custom/plugins/zsh-completions/src")\n'
                "autoload -U compinit && compinit\n"
            )

        truecolor_marker = "# linux-setup-tui: truecolor"
        if truecolor_marker not in content:
            content += (
                f"\n{truecolor_marker}\n"
                "export COLORTERM=truecolor\n"
                "export TERM=${TERM:-xterm-256color}\n"
            )

        if content != original:
            zshrc.write_text(content)
            ok("Updated .zshrc plugins/fpath/COLORTERM")
        else:
            ok(".zshrc plugins/fpath already configured")

    def setup_powerlevel10k(self) -> bool:
        theme_dir = HOME / ".oh-my-zsh" / "custom" / "themes" / "powerlevel10k"
        if theme_dir.exists():
            run_cmd(["git", "-C", str(theme_dir), "pull", "--ff-only"])
            ok("Powerlevel10k up to date")
        elif self.cfg.dry_run:
            ok("[dry-run] would clone Powerlevel10k")
        else:
            step("Cloning Powerlevel10k…")
            res = with_retries(
                lambda: run_cmd(
                    [
                        "git", "clone", "--depth=1",
                        "https://github.com/romkatv/powerlevel10k.git",
                        str(theme_dir),
                    ]
                ),
                attempts=3,
                label="p10k clone",
            )
            if not res.ok:
                err("Powerlevel10k clone failed")
                self._record("p10k", "failed", "clone")
                return False

        zshrc = self._ensure_zshrc()
        if zshrc is None:
            self._record("p10k", "failed", "no zshrc")
            return False
        text = zshrc.read_text()
        new_theme = 'ZSH_THEME="powerlevel10k/powerlevel10k"'
        if re.search(r"^ZSH_THEME=", text, re.MULTILINE):
            text = re.sub(r'^ZSH_THEME=.*', new_theme, text, flags=re.MULTILINE)
        else:
            text += f"\n{new_theme}\n"
        zshrc.write_text(text)
        ok("Set ZSH_THEME to powerlevel10k")

        self._install_nerd_fonts()
        self._record("p10k", "ok")
        return True

    def _install_nerd_fonts(self) -> None:
        font_dir = LOCAL_DIR / "share" / "fonts"
        font_dir.mkdir(parents=True, exist_ok=True)
        base_url = "https://github.com/romkatv/powerlevel10k-media/raw/master"
        fonts = [
            "MesloLGS NF Regular.ttf",
            "MesloLGS NF Bold.ttf",
            "MesloLGS NF Italic.ttf",
            "MesloLGS NF Bold Italic.ttf",
        ]
        any_downloaded = False
        for name in fonts:
            dest = font_dir / name
            if dest.exists() and dest.stat().st_size > 0:
                continue
            step(f"Downloading {name}…")
            url = f"{base_url}/{name.replace(' ', '%20')}"
            res = with_retries(
                lambda u=url, d=dest: run_cmd(
                    ["curl", "-fsSL", "--retry", "3", "-o", str(d), u], timeout=120
                ),
                attempts=3,
                label=f"download {name}",
            )
            if not res.ok and dest.exists():
                dest.unlink(missing_ok=True)
            if res.ok:
                any_downloaded = True

        if any_downloaded and shutil.which("fc-cache"):
            run_cmd(["fc-cache", "-f", str(font_dir)])
        ok("Nerd Fonts installed")

    def setup_terminator(self) -> bool:
        cfg_dir = CONFIG_DIR / "terminator"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = cfg_dir / "config"

        config_content = """[global_config]
[keybindings]
[profiles]
  [[dracula-pinterest]]
    palette = "#1e1f29:#ff4d6d:#50fa7b:#ffd166:#4895ef:#b5179e:#4cc9f0:#f8f9fa:#4b4d59:#ff6b81:#69ff94:#ffe066:#5ec8ff:#ff79c6:#8be9fd:#ffffff"
    background_color = "#22232b"
    foreground_color = "#f8f9fa"
    cursor_color = "#f8f9fa"
    use_system_font = False
    use_theme_colors = False
    allow_bold = True
    bold_is_bright = True
    cursor_blink = True
    scrollback_infinite = True
    scrollback_lines = 20000
    font = MesloLGS NF 12
    scrollbar_position = hidden
    show_titlebar = False
[layouts]
  [[default]]
    [[[child1]]]
      type = Terminal
      profile = dracula-pinterest
    [[[window0]]]
      type = Window
      parent = ""
      child = child1
[plugins]
"""
        if cfg_file.exists():
            existing = cfg_file.read_text()
            if existing.strip() == config_content.strip():
                ok("Terminator config already up to date")
            else:
                backup = cfg_file.with_suffix(f".bak.{int(time.time())}")
                shutil.copy(cfg_file, backup)
                warn(f"Backed up existing config → {backup.name}")
                cfg_file.write_text(config_content)
                ok("Terminator config updated (Dracula theme)")
        else:
            cfg_file.write_text(config_content)
            ok("Terminator config created")

        if shutil.which("terminator") and not self.cfg.dry_run:
            run_cmd(
                [
                    "update-alternatives", "--install",
                    "/usr/bin/x-terminal-emulator", "x-terminal-emulator",
                    "/usr/bin/terminator", "50",
                ],
                sudo=True,
                capture=False,
            )
            run_cmd(
                ["update-alternatives", "--set", "x-terminal-emulator", "/usr/bin/terminator"],
                sudo=True,
                capture=False,
            )
            ok("Terminator set as default x-terminal-emulator")

        self._record("terminator", "ok")
        return True

    def setup_neovim(self) -> bool:
        if shutil.which("nvim"):
            ok(f"Neovim already installed: {self._nvim_version()}")
            self._install_lazyvim()
            self._record("nvim", "ok", "already installed")
            return True

        if self.cfg.dry_run:
            ok("[dry-run] would build Neovim from source")
            self._record("nvim", "skipped", "dry-run")
            return True

        for tool in ("git", "make", "cmake", "g++", "ninja"):
            if not shutil.which(tool):
                err(f"Required build tool missing: {tool}")
                self._record("nvim", "failed", f"missing {tool}")
                return False

        work_dir = LOCAL_DIR / "src"
        work_dir.mkdir(parents=True, exist_ok=True)
        repo = work_dir / "neovim"

        if repo.exists():
            run_cmd(["git", "-C", str(repo), "fetch", "--depth=1", "origin", "stable"])
            run_cmd(["git", "-C", str(repo), "checkout", "stable"])
            run_cmd(["git", "-C", str(repo), "pull", "--ff-only"])
        else:
            step("Cloning neovim/neovim (stable)…")
            res = with_retries(
                lambda: run_cmd(
                    [
                        "git", "clone", "--depth=1", "-b", "stable",
                        "https://github.com/neovim/neovim.git", str(repo),
                    ]
                ),
                label="neovim clone",
            )
            if not res.ok:
                err("neovim clone failed")
                self._record("nvim", "failed", "clone")
                return False

        step("Building Neovim (this can take several minutes)…")
        with console.status("[bold]compiling neovim…", spinner="dots"):
            build = run_cmd(
                ["make", "CMAKE_BUILD_TYPE=Release", f"-j{os.cpu_count() or 2}"],
                cwd=repo,
                timeout=1800,
            )
        if not build.ok:
            err("Neovim build failed (see log)")
            self._record("nvim", "failed", "build")
            return False

        step("Installing Neovim…")
        if not run_cmd(["make", "install"], sudo=True, cwd=repo, timeout=300).ok:
            err("Neovim install failed")
            self._record("nvim", "failed", "install")
            return False

        if not shutil.which("nvim"):
            err("nvim not on PATH after install")
            self._record("nvim", "failed", "post-install verify")
            return False
        ok(f"Neovim installed: {self._nvim_version()}")

        self._install_lazyvim()
        self._record("nvim", "ok")
        return True

    def _nvim_version(self) -> str:
        res = run_cmd(["nvim", "--version"])
        if res.ok and res.stdout:
            return res.stdout.splitlines()[0]
        return "unknown"

    def _install_lazyvim(self) -> None:
        nvim_cfg = CONFIG_DIR / "nvim"
        if nvim_cfg.exists() and any(nvim_cfg.iterdir()):
            ok("~/.config/nvim already populated; not overwriting")
            return
        if self.cfg.dry_run:
            ok("[dry-run] would install LazyVim starter")
            return
        step("Installing LazyVim starter…")
        res = with_retries(
            lambda: run_cmd(
                [
                    "git", "clone", "--depth=1",
                    "https://github.com/LazyVim/starter", str(nvim_cfg),
                ]
            ),
            label="LazyVim clone",
        )
        if res.ok:
            shutil.rmtree(nvim_cfg / ".git", ignore_errors=True)
            ok("LazyVim starter installed")
        else:
            warn("LazyVim clone failed; you can retry later")

    def setup_git_and_ssh(self) -> bool:
        if self.cfg.name:
            run_cmd(["git", "config", "--global", "user.name", self.cfg.name])
        if self.cfg.email:
            run_cmd(["git", "config", "--global", "user.email", self.cfg.email])
        if self.cfg.name or self.cfg.email:
            ok("Git global identity configured")

        if not self.cfg.email:
            warn("No email provided; skipping SSH key generation")
            self._record("ssh", "skipped", "no email")
            return True

        SSH_DIR.mkdir(mode=0o700, exist_ok=True)
        os.chmod(SSH_DIR, 0o700)
        key_file = SSH_DIR / "id_ed25519"
        pub_file = SSH_DIR / "id_ed25519.pub"

        if key_file.exists():
            ok(f"SSH key already exists at {key_file}")
            if not pub_file.exists():
                step("Public key missing; regenerating from private key…")
                run_cmd(["ssh-keygen", "-y", "-f", str(key_file)], capture=True)
        elif self.cfg.dry_run:
            ok("[dry-run] would generate ed25519 SSH key")
        else:
            step("Generating ed25519 SSH key…")
            res = run_cmd(
                [
                    "ssh-keygen", "-t", "ed25519", "-a", "100",
                    "-C", self.cfg.email, "-f", str(key_file), "-N", "",
                ]
            )
            if not res.ok:
                err("ssh-keygen failed")
                self._record("ssh", "failed", "keygen")
                return False
            os.chmod(key_file, 0o600)
            if pub_file.exists():
                os.chmod(pub_file, 0o644)
            ok(f"SSH key generated at {key_file}")

        self._write_ssh_config()

        if pub_file.exists():
            pub = pub_file.read_text().strip()
            console.print(
                Panel(
                    pub,
                    title="Public key — add to GitHub/GitLab",
                    border_style=STYLE_ACCENT,
                )
            )
            if shutil.which("xclip") and not self.cfg.dry_run:
                run_cmd(f'xclip -selection clipboard < "{pub_file}"', shell=True)
                ok("Public key copied to clipboard")

        self._record("ssh", "ok")
        return True

    def _write_ssh_config(self) -> None:
        cfg = SSH_DIR / "config"
        block = """# linux-setup-tui defaults
Host *
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
    HashKnownHosts yes
    ServerAliveInterval 60
    ServerAliveCountMax 5

Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519

Host gitlab.com
    HostName gitlab.com
    User git
    IdentityFile ~/.ssh/id_ed25519
"""
        if not cfg.exists():
            cfg.write_text(block)
            os.chmod(cfg, 0o600)
            ok("Wrote ~/.ssh/config")
        elif "linux-setup-tui defaults" not in cfg.read_text():
            with cfg.open("a") as f:
                f.write("\n" + block)
            os.chmod(cfg, 0o600)
            ok("Appended SSH defaults to ~/.ssh/config")
        else:
            ok("~/.ssh/config already configured")


# ---------------------------------------------------------------------------
# UI.
# ---------------------------------------------------------------------------


_QSTYLE = questionary.Style(
    [
        ("qmark", "fg:#d97757 bold"),
        ("question", "bold"),
        ("answer", "fg:#d97757 bold"),
        ("pointer", "fg:#d97757 bold"),
        ("highlighted", "fg:#d97757 bold"),
        ("selected", "fg:#d97757"),
        ("separator", "fg:#cc5454"),
        ("instruction", "fg:#6c6c6c"),
        ("text", ""),
        ("disabled", "fg:#858585 italic"),
    ]
)


def print_header(pre: Preflight) -> None:
    console.print()
    console.print(
        Panel(
            Text(" Linux Environment Setup ", justify="center", style="bold white"),
            style=STYLE_ACCENT,
            subtitle=f"[{STYLE_DIM}]{pre.distro} • log: {LOG_FILE}[/]",
            subtitle_align="right",
            width=72,
            box=rich.box.ROUNDED,
            padding=(0, 2),
        )
    )
    console.print()


def email_validator(text: str) -> bool | str:
    if not text:
        return "Email cannot be empty"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
        return "Invalid email format"
    return True


def name_validator(text: str) -> bool | str:
    if not text.strip():
        return "Name cannot be empty"
    return True


def collect_selections(args: argparse.Namespace) -> tuple[list[str], UserConfig]:
    if args.components:
        requested = [c.strip() for c in args.components.split(",") if c.strip()]
        unknown = [c for c in requested if c not in {x.key for x in COMPONENTS}]
        if unknown:
            err(f"Unknown components: {unknown}. Valid: {[c.key for c in COMPONENTS]}")
            sys.exit(2)
        selected = requested
    else:
        choices = [
            questionary.Choice(c.label, checked=c.default, value=c.key) for c in COMPONENTS
        ]
        answer = questionary.checkbox(
            "Select components to install:", choices=choices, style=_QSTYLE
        ).ask()
        if not answer:
            err("No components selected. Exiting.")
            sys.exit(0)
        selected = answer

    selected = resolve_dependencies(selected)

    cfg = UserConfig(assume_yes=args.yes, dry_run=args.dry_run)
    if "ssh" in selected:
        cfg.name = args.name or ""
        cfg.email = args.email or ""
        if not args.yes:
            if not cfg.name:
                cfg.name = questionary.text(
                    "Full name (for git):", style=_QSTYLE, validate=name_validator
                ).ask() or ""
            if not cfg.email:
                cfg.email = questionary.text(
                    "Email (for git + SSH key):", style=_QSTYLE, validate=email_validator
                ).ask() or ""
        else:
            if cfg.email and email_validator(cfg.email) is not True:
                err(f"Invalid --email: {cfg.email}")
                sys.exit(2)
    return selected, cfg


def confirm_plan(selected: list[str], cfg: UserConfig) -> bool:
    table = Table(box=rich.box.SIMPLE, show_header=True, header_style=STYLE_ACCENT)
    table.add_column("Component")
    table.add_column("Action")
    by_key = {c.key: c for c in COMPONENTS}
    for key in selected:
        table.add_row(by_key[key].label, "[green]install / update[/]")
    if cfg.name or cfg.email:
        table.add_row("git identity", f"{cfg.name} <{cfg.email}>")
    if cfg.dry_run:
        table.add_row("[yellow]dry-run[/]", "[yellow]no changes will be made[/]")
    console.print(table)

    if cfg.assume_yes:
        return True
    return bool(questionary.confirm("Proceed with installation?", default=True, style=_QSTYLE).ask())


def print_summary(results: list[StepResult]) -> int:
    table = Table(
        title="Installation Summary",
        box=rich.box.ROUNDED,
        title_style="bold",
        show_header=True,
        header_style=STYLE_ACCENT,
    )
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Detail")

    icons = {"ok": "[green]✓ ok[/]", "skipped": "[yellow]– skipped[/]", "failed": "[red]✗ failed[/]"}
    for r in results:
        table.add_row(r.name, icons.get(r.status, r.status), r.detail or "")
    console.print()
    console.print(table)

    failures = sum(1 for r in results if r.status == "failed")
    if failures:
        console.print(
            Panel(
                f"{failures} step(s) failed. Full log: {LOG_FILE}",
                border_style=STYLE_ERR,
                title="Errors",
            )
        )
        return 1

    console.print(
        Panel(
            Text("Installation Complete!", justify="center", style="bold green"),
            box=rich.box.ROUNDED,
            border_style="green",
            width=60,
        )
    )
    console.print(f"  [{STYLE_DIM}]Restart your terminal session to apply changes.[/]")
    return 0


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Robust Linux workstation setup TUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Components: " + ", ".join(c.key for c in COMPONENTS),
    )
    parser.add_argument(
        "-c", "--components",
        help="Comma-separated component list (skips picker). e.g. base,zsh,p10k",
    )
    parser.add_argument("--name", help="Git user.name (for ssh component)")
    parser.add_argument("--email", help="Git user.email (for ssh component)")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive; assume confirm")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    return parser.parse_args()


STEP_DISPATCH: dict[str, Callable[[Installer], bool]] = {
    "base": Installer.install_base_packages,
    "zsh": Installer.setup_zsh,
    "p10k": Installer.setup_powerlevel10k,
    "terminator": Installer.setup_terminator,
    "nvim": Installer.setup_neovim,
    "ssh": Installer.setup_git_and_ssh,
}


def main() -> int:
    args = parse_args()

    if sys.stdout.isatty():
        console.clear()

    pre = preflight()
    print_header(pre)

    if pre.fatal:
        for problem in pre.fatal:
            err(problem)
        return 2
    for w in pre.warnings:
        warn(w)

    selected, cfg = collect_selections(args)

    if not confirm_plan(selected, cfg):
        console.print(f"[{STYLE_DIM}]Aborted by user.[/]")
        return 0

    if not cfg.dry_run and os.geteuid() != 0:
        # Pre-prime sudo so subsequent calls don't all prompt.
        run_cmd("sudo -v", shell=True, capture=False)

    installer = Installer(cfg)
    for key in selected:
        console.rule(f"[{STYLE_ACCENT}]{key}[/]", style=STYLE_DIM)
        try:
            STEP_DISPATCH[key](installer)
        except Exception as exc:  # noqa: BLE001
            log.exception("step %s crashed", key)
            err(f"step '{key}' crashed: {exc}")
            installer.results.append(StepResult(key, "failed", str(exc)))

    return print_summary(installer.results)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print(f"\n[{STYLE_WARN}]Interrupted by user.[/]")
        sys.exit(130)
