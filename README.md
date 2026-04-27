# New PC Setup

Two installers are provided:

- **`install_tui.py`** — recommended. Interactive TUI with preflight checks,
  retries, idempotent re-runs, dependency resolution, dry-run, and a final
  summary report. Auto-bootstraps `uv` and its own Python deps.
- **`setup.sh`** — plain bash equivalent, no UI.

## Quickstart (TUI)

```bash
chmod +x ./install_tui.py
./install_tui.py
```

### Useful flags

```bash
./install_tui.py --dry-run                    # show what would happen, change nothing
./install_tui.py -y -c base,zsh,p10k          # non-interactive, specific components
./install_tui.py -c ssh --name "Me" --email me@example.com -y
```

Components: `base`, `zsh`, `p10k`, `terminator`, `nvim`, `ssh`. Dependencies
are resolved automatically (e.g. `p10k` pulls in `zsh` and `base`).

Logs go to `~/.local/state/linux-setup-tui/install.log` for post-mortem.

## Quickstart (bash)

```bash
chmod +x ./setup.sh
./setup.sh
```

## Full guide

The long-form guide lives in `readme.adoc`. Render it with:

```bash
sudo apt-get update -y && sudo apt-get install -y asciidoctor
asciidoctor readme.adoc && xdg-open readme.html
```
