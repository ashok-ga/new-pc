#!/usr/bin/env python3
# /// script
# dependencies = [
#   "rich",
#   "questionary",
# ]
# ///

import os
import sys
import subprocess
import shutil
import time

# --- Bootstrap UV & Dependencies ---
def bootstrap():
    """Ensures uv is installed and re-runs script with 'uv run' if not already in that env."""
    
    # Check if we are already running under uv (simple check: VIRTUAL_ENV is set and seems managed by uv, 
    # or we can trust the 'uv run' invocation)
    # However, a robust way is to check if 'rich' is importable.
    try:
        import rich
        import questionary
        return # Dependencies present, proceed
    except ImportError:
        pass

    print("[*] Bootstrapping environment with 'uv'...")

    # 1. Install uv if missing
    if not shutil.which("uv"):
        print("    -> 'uv' not found. Installing via curl...")
        try:
            install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
            subprocess.run(install_cmd, shell=True, check=True)
            
            # Update PATH for the current process
            # UV can install to ~/.cargo/bin OR ~/.local/bin depending on system state
            possible_paths = [
                os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.cargo/bin")
            ]
            
            uv_found_path = None
            for p in possible_paths:
                if os.path.isdir(p) and os.path.exists(os.path.join(p, "uv")):
                   os.environ["PATH"] = f"{p}:{os.environ['PATH']}"
                   uv_found_path = os.path.join(p, "uv")
                   break

            if not uv_found_path:
                 # Last ditch: check if 'uv' is now in path via some other means
                 if shutil.which("uv"):
                     start_uv = "uv"
                 else:
                    print("[!] Failed to locate 'uv' after installation. Checked ~/.local/bin and ~/.cargo/bin.")
                    sys.exit(1)
            else:
                start_uv = uv_found_path
        except subprocess.CalledProcessError:
             print("[!] Failed to install uv. Cannot proceed.")
             sys.exit(1)
    else:
        start_uv = "uv"

    # 2. Re-run script with uv run
    print("    -> Re-launching with 'uv run'...")
    # This automatically reads the PEP 723 metadata or pyproject.toml
    full_cmd = [start_uv, "run", sys.argv[0]] + sys.argv[1:]
    try:
        os.execvp(start_uv, full_cmd)
    except Exception as e:
        print(f"[!] Failed to restart with uv: {e}")
        sys.exit(1)

# Run bootstrap before anything else
bootstrap()

# --- Imports (safe now) ---
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.markdown import Markdown
import rich.box
import questionary

console = Console()

# --- Configuration & Constants ---
HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".config")
LOCAL_DIR = os.path.join(HOME, ".local")
SSH_DIR = os.path.join(HOME, ".ssh")

# --- UI Theme ---
STYLE_ACCENT = "bold #d97757" # Terracotta/Orange-ish accent
STYLE_DIM = "dim white"
STYLE_SUCCESS = "bold green"
STYLE_ERROR = "bold red"
STYLE_WARNING = "bold yellow"

# --- Helpers ---
def print_header():
    console.print()
    console.print(Panel(
        Text(" Linux Environment Setup ", justify="center", style="bold white"),
        style=f"{STYLE_ACCENT}",
        subtitle=f"[{STYLE_DIM}]Powered by UV[/{STYLE_DIM}]",
        subtitle_align="right",
        width=60,
        box=rich.box.ROUNDED,
        padding=(0, 2)
    ))
    console.print()

def run_cmd(cmd, sudo=False, shell=False, cwd=None, capture=True):
    if sudo and os.geteuid() != 0:
        if isinstance(cmd, list):
            cmd = ["sudo"] + cmd
        else:
            cmd = "sudo " + cmd
    
    try:
        if capture:
            subprocess.run(
                cmd, 
                check=True, 
                shell=shell, 
                cwd=cwd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE 
            )
        else:
            # Interactive mode: let stdout/stderr go to terminal
            subprocess.run(
                cmd, 
                check=True, 
                shell=shell, 
                cwd=cwd
            )
        return True
    except subprocess.CalledProcessError:
        return False

def log_step(msg):
    console.print(f"  [{STYLE_ACCENT}]•[/{STYLE_ACCENT}] {msg}")

def log_success(msg):
    console.print(f"  [{STYLE_SUCCESS}]✓[/{STYLE_SUCCESS}] {msg}")

def log_warning(msg):
    console.print(f"  [{STYLE_WARNING}]![/{STYLE_WARNING}] {msg}")

def log_error(msg):
    console.print(f"  [{STYLE_ERROR}]✗[/{STYLE_ERROR}] {msg}")


# --- Installation Steps ---

class Installer:
    def __init__(self, user_config):
        self.config = user_config
        self.name = user_config.get("name")
        self.email = user_config.get("email")

    def install_base_packages(self):
        packages = [
            "git", "curl", "wget", "ca-certificates", "build-essential",
            "pkg-config", "libtool", "libtool-bin", "autoconf", "automake",
            "cmake", "g++", "unzip", "gettext", "ninja-build", "doxygen",
            "zsh", "terminator", "fonts-powerline", "ripgrep", "fd-find"
        ]
        
        # Check for apt
        if not shutil.which("apt-get"):
            log_error("apt-get not found. This script supports Debian/Ubuntu only.")
            return False

        console.print("[bold blue]Updating apt cache...[/bold blue]")
        run_cmd(["apt-get", "update", "-y"], sudo=True, capture=False)
        
        console.print(f"[bold blue]Installing packages: {', '.join(packages[:5])} and others...[/bold blue]")
        if run_cmd(["apt-get", "install", "-y"] + packages, sudo=True, capture=False):
            log_success("Base packages installed.")
            return True
        else:
            log_error("Failed to install base packages.")
            return False

    def setup_zsh(self):
        # Set default shell
        if "zsh" not in os.environ.get("SHELL", ""):
            zsh_path = shutil.which("zsh")
            if zsh_path:
                try:
                    # Run interactively to allow password prompt
                    subprocess.run(["chsh", "-s", zsh_path, os.environ["USER"]], check=True)
                    log_success("Default shell changed to Zsh.")
                except Exception:
                    log_warning(f"Could not automatically change shell. Run: chsh -s {zsh_path}")
        else:
            log_success("Zsh is already the default shell.")

        # Oh My Zsh
        omz_dir = os.path.join(HOME, ".oh-my-zsh")
        if not os.path.exists(omz_dir):
            console.print("Installing Oh My Zsh...")
            # Non-interactive install
            cmd = 'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended'
            run_cmd(cmd, shell=True)
            log_success("Oh My Zsh installed.")
        else:
            log_success("Oh My Zsh already installed.")

    # Rename setup_powerlevel10k to match usage or update calls
    def setup_powerlevel10k(self):
        theme_dir = os.path.join(HOME, ".oh-my-zsh/custom/themes/powerlevel10k")
        if not os.path.exists(theme_dir):
            console.print("Cloning Powerlevel10k...")
            run_cmd(["git", "clone", "--depth=1", "https://github.com/romkatv/powerlevel10k.git", theme_dir])
        else:
            run_cmd(["git", "-C", theme_dir, "pull", "--ff-only"])
        
        zshrc = os.path.join(HOME, ".zshrc")
        if os.path.exists(zshrc):
            with open(zshrc, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            theme_set = False
            for line in lines:
                if line.strip().startswith("ZSH_THEME="):
                    new_lines.append('ZSH_THEME="powerlevel10k/powerlevel10k"\n')
                    theme_set = True
                else:
                    new_lines.append(line)
            
            if not theme_set:
                new_lines.append('\nZSH_THEME="powerlevel10k/powerlevel10k"\n')
            
            with open(zshrc, "w") as f:
                f.writelines(new_lines)
            log_success("Updated .zshrc with p10k theme.")

    def setup_plugins(self):
        custom_dir = os.path.join(HOME, ".oh-my-zsh/custom")
        plugins = {
            "zsh-autosuggestions": "https://github.com/zsh-users/zsh-autosuggestions",
            "zsh-completions": "https://github.com/zsh-users/zsh-completions"
        }
        
        for name, url in plugins.items():
            path = os.path.join(custom_dir, "plugins", name)
            if not os.path.exists(path):
                run_cmd(["git", "clone", "--depth=1", url, path])
            else:
                 run_cmd(["git", "-C", path, "pull", "--ff-only"])
        
        log_success("Zsh plugins downloaded.")

        # Automate adding to .zshrc
        zshrc = os.path.join(HOME, ".zshrc")
        if os.path.exists(zshrc):
            with open(zshrc, "r") as f:
                content = f.read()

            # 1. Add plugins to plugins=(...)
            import re
            # Check if plugins line exists
            if re.search(r'^plugins=\(', content, re.MULTILINE):
                # Check individual plugins
                if "zsh-autosuggestions" not in content:
                    content = re.sub(r'(^plugins=\([^\)]*)(\))', r'\1 zsh-autosuggestions)', content, flags=re.MULTILINE)
                    log_success("Added zsh-autosuggestions to .zshrc")
                
                if "zsh-completions" not in content:
                    content = re.sub(r'(^plugins=\([^\)]*)(\))', r'\1 zsh-completions)', content, flags=re.MULTILINE)
                    log_success("Added zsh-completions to .zshrc")
            else:
                # Append if missing
                content += '\nplugins=(git zsh-autosuggestions zsh-completions)\n'
                log_success("Created plugins list in .zshrc")
            
            # 2. Add fpath for completions
            if "zsh-completions/src" not in content:
                content += f'\nfpath+=("{custom_dir}/plugins/zsh-completions/src")\nautoload -U compinit && compinit\n'
                log_success("Configured fpath for zsh-completions")

            with open(zshrc, "w") as f:
                f.write(content)

    def setup_terminator(self):
        cfg_dir = os.path.join(CONFIG_DIR, "terminator")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_file = os.path.join(cfg_dir, "config")
        
        config_content = r"""[global_config]
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
        # Backup and Overwrite to ensure theme applies
        if os.path.exists(cfg_file):
            timestamp = int(time.time())
            backup = f"{cfg_file}.bak.{timestamp}"
            shutil.copy(cfg_file, backup)
            log_warning(f"Backed up existing Terminator config to {os.path.basename(backup)}")
        
        with open(cfg_file, "w") as f:
            f.write(config_content)
        log_success("Terminator config created/updated with Dracula theme.")
            
        # Set as default
        if shutil.which("terminator"):
            run_cmd(["update-alternatives", "--install", "/usr/bin/x-terminal-emulator", "x-terminal-emulator", "/usr/bin/terminator", "50"], sudo=True, capture=False)
            run_cmd(["update-alternatives", "--set", "x-terminal-emulator", "/usr/bin/terminator"], sudo=True, capture=False)

    def setup_neovim(self):
        if shutil.which("nvim"):
            log_success("Neovim is already installed.")
            return

        console.print("[blue]Building Neovim from source (this may take a while)...[/blue]")
        work_dir = os.path.join(LOCAL_DIR, "src")
        os.makedirs(work_dir, exist_ok=True)
        repo = os.path.join(work_dir, "neovim")
        
        if not os.path.exists(repo):
            run_cmd(["git", "clone", "--depth=1", "-b", "stable", "https://github.com/neovim/neovim.git", repo])
        else:
            run_cmd(["git", "-C", repo, "pull", "--ff-only"])
            
        # Build
        if run_cmd(["make", "CMAKE_BUILD_TYPE=Release"], cwd=repo):
            run_cmd(["make", "install"], sudo=True, cwd=repo)
            log_success("Neovim built and installed.")
        else:
            log_error("Failed to build Neovim.")
            
        # LazyVim
        nvim_cfg = os.path.join(CONFIG_DIR, "nvim")
        if not os.path.exists(nvim_cfg):
            run_cmd(["git", "clone", "--depth=1", "https://github.com/LazyVim/starter", nvim_cfg])
            shutil.rmtree(os.path.join(nvim_cfg, ".git"), ignore_errors=True)
            log_success("LazyVim starter installed.")

    def setup_git(self):
        if self.name:
            run_cmd(["git", "config", "--global", "user.name", self.name])
        if self.email:
            run_cmd(["git", "config", "--global", "user.email", self.email])
        log_success("Git configured.")

    def setup_ssh(self):
        if not self.email:
             log_warning("No email provided. Skipping SSH key generation.")
             return

        key_file = os.path.join(SSH_DIR, "id_ed25519")
        if not os.path.exists(key_file):
            console.print("Generating SSH key...")
            os.makedirs(SSH_DIR, exist_ok=True)
            run_cmd(["ssh-keygen", "-t", "ed25519", "-a", "100", "-C", self.email, "-f", key_file, "-N", ""])
            log_success(f"SSH key generated at {key_file}")
        
        # SSH Config
        config_path = os.path.join(SSH_DIR, "config")
        config_content = """Host *
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_ed25519
    HashKnownHosts yes
    ServerAliveInterval 60
    ServerAliveCountMax 5

Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
""" 
        if not os.path.exists(config_path):
            with open(config_path, "w") as f:
                f.write(config_content)
            os.chmod(config_path, 0o600)

        # Show key
        if os.path.exists(key_file + ".pub"):
            with open(key_file + ".pub", "r") as f:
                pub_key = f.read().strip()
            console.print(Panel(pub_key, title="Public Key (Add to GitHub/GitLab)"))

    def install_nerd_fonts(self):
        font_dir = os.path.join(LOCAL_DIR, "share/fonts")
        os.makedirs(font_dir, exist_ok=True)
        fonts = [
            "MesloLGS NF Regular.ttf", "MesloLGS NF Bold.ttf", 
            "MesloLGS NF Italic.ttf", "MesloLGS NF Bold Italic.ttf"
        ]
        base_url = "https://github.com/romkatv/powerlevel10k-media/raw/master"
        
        for f in fonts:
            dest = os.path.join(font_dir, f)
            if not os.path.exists(dest):
                console.print(f"Downloading {f}...")
                run_cmd(["curl", "-fsSL", "-o", dest, f"{base_url}/{f.replace(' ', '%20')}"])
        
        run_cmd(["fc-cache", "-f", font_dir])
        log_success("Nerd Fonts installed.")


def main():
    console.clear()
    print_header()

    # User Inputs - Selection First
    custom_style = questionary.Style([
        ('qmark', 'fg:#d97757 bold'),       # Token.QuestionMark
        ('question', 'bold'),                # Token.Question
        ('answer', 'fg:#d97757 bold'),       # Token.Answer
        ('pointer', 'fg:#d97757 bold'),      # Token.Pointer
        ('highlighted', 'fg:#d97757 bold'),  # Token.Highlighted
        ('selected', 'fg:#d97757'),          # Token.Selected
        ('separator', 'fg:#cc5454'),         # Token.Separator
        ('instruction', 'fg:#6c6c6c'),       # Token.Instruction
        ('text', ''),                        # Token.Text
        ('disabled', 'fg:#858585 italic')    # Token.Disabled
    ])

    choices = [
        questionary.Choice("Base Packages (curl, git, ...)", checked=True, value="base"),
        questionary.Choice("Zsh & Oh My Zsh", checked=True, value="zsh"),
        questionary.Choice("Powerlevel10k & Nerd Fonts", checked=True, value="p10k"),
        questionary.Choice("Terminator (Dracula Theme)", checked=True, value="terminator"),
        questionary.Choice("Neovim (from source) & LazyVim", checked=True, value="nvim"),
        questionary.Choice("SSH Keys & Git Config", checked=True, value="ssh"),
    ]
    
    selected_options = questionary.checkbox("Select components to install:", choices=choices, style=custom_style).ask()
    
    if not selected_options:
        console.print(f"[{STYLE_ERROR}]No components selected. Exiting.[/{STYLE_ERROR}]")
        sys.exit(0)

    # Conditional Inputs
    name = ""
    email = ""
    if "ssh" in selected_options:
        console.print(f"[{STYLE_DIM}]SSH/Git config selected. Please provide details:[/{STYLE_DIM}]")
        name = questionary.text("What is your full name?", style=custom_style).ask()
        email = questionary.text("What is your email address?", style=custom_style).ask()

    config = {"name": name, "email": email}
    installer = Installer(config)
    
    console.print()
    console.print(f"[{STYLE_DIM}]Starting installation...[/{STYLE_DIM}]")
    console.print()

    # We use a progress bar for steps that don't output much text or where we suppress output.
    # For 'base', we want to show apt output, so we run it outside the main progress block or handle it specifically.
    
    installer = Installer(config)
    
    console.print()
    console.print(f"[{STYLE_DIM}]Starting installation...[/{STYLE_DIM}]")
    console.print()

    # 0. Refresh Sudo Credentials Early
    # This prevents timeouts or prompt issues later
    run_cmd("sudo -v", shell=True, capture=False)
    console.print()

    # 1. Base Packages (Interactive/Verbose)
    if "base" in selected_options:
        console.print(f"[{STYLE_ACCENT}]•[/{STYLE_ACCENT}] Installing Base Packages...")
        installer.install_base_packages()
        console.print()

    # 2. Zsh Setup (Interactive - chsh may prompt for password)
    if "zsh" in selected_options:
        console.print(f"[{STYLE_ACCENT}]•[/{STYLE_ACCENT}] Setting up Zsh...")
        installer.setup_zsh()
        installer.setup_plugins()
        console.print()

    # 3. Terminator (Interactive - sudo update-alternatives)
    if "terminator" in selected_options:
        console.print(f"[{STYLE_ACCENT}]•[/{STYLE_ACCENT}] Configuring Terminator...")
        installer.setup_terminator()
        console.print()

    # 4. Other Steps (Progress Bar)
    remaining_steps = [s for s in selected_options if s not in ["base", "zsh", "terminator"]]
    
    if remaining_steps:
        with Progress(
            SpinnerColumn(style=f"{STYLE_ACCENT}"),
            TextColumn("[bold white]{task.description}"),
            console=console,
            transient=False,
        ) as progress:
            
            if "p10k" in selected_options:
                 task = progress.add_task("Installing Fonts & Theme...", total=None)
                 installer.install_nerd_fonts()
                 installer.setup_powerlevel10k()
                 progress.update(task, completed=True)
            
            if "nvim" in selected_options:
                 task = progress.add_task("Building Neovim...", total=None)
                 installer.setup_neovim()
                 progress.update(task, completed=True)
            
            if "ssh" in selected_options:
                 task = progress.add_task("Configuring SSH & Git...", total=None)
                 installer.setup_git()
                 installer.setup_ssh()
                 progress.update(task, completed=True)
    
    console.print()
    console.print(Panel(
        Text("Installation Complete!", justify="center", style="bold green"),
        box=rich.box.ROUNDED,
        style="green",
        width=60,
    ))
    console.print(f"  [{STYLE_DIM}]Please restart your terminal session to apply changes.[/{STYLE_DIM}]")
    console.print()

if __name__ == "__main__":
    main()
