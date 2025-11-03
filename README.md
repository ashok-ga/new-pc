## New PC Setup

Automation scripts to set up a fresh Linux machine (Debian/Ubuntu). Includes Terminator, Zsh, powerlevel10k, Dracula theme, zsh plugins, Nerd Fonts, Neovim (built from source), and LazyVim. A separate script manages SSH keys.

### Prerequisites
- OS: Debian/Ubuntu (uses `apt`)
- Internet connectivity

### 1) Full machine setup
Runs everything non-interactively: installs packages, sets Zsh default, configures Terminator (Dracula + no titlebar), installs fonts, builds Neovim, and installs LazyVim.

```bash
chmod +x ./setup.sh
./setup.sh
```

What it does:
- Installs: `terminator`, `zsh`, build tools, `ripgrep`, `fd`, etc.
- Sets default shell: Zsh + Oh My Zsh
- Theme: powerlevel10k
- Zsh plugins: `zsh-autosuggestions`, `zsh-completions`
- Terminator: Dracula theme, hides title bar, sets layout
- Fonts: MesloLGS Nerd Font (for p10k)
- Neovim: builds and installs stable from source
- LazyVim: clones starter to `~/.config/nvim`

Notes:
- Restart terminal (or log out/in) after running to use Zsh as default.
- Ensure Terminator profile font is "MesloLGS NF" for best powerlevel10k visuals.

Make Terminator default terminal (already done by the script, manual commands below if needed):
```bash
sudo update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator /usr/bin/terminator 50
sudo update-alternatives --set x-terminal-emulator /usr/bin/terminator
```

### 2) SSH keys setup
Standalone script to generate and configure SSH keys. It safely creates `id_ed25519`, configures `~/.ssh/config`, starts `ssh-agent`, adds the key, and prints/copies the public key.

```bash
chmod +x ./setup-ssh.sh
./setup-ssh.sh --email you@example.com
```

Options:
- `--email you@example.com`  Set the key comment (default: "$USER@$HOSTNAME")
- `--force`                  Overwrite existing `id_ed25519`
- `--no-agent`               Skip starting `ssh-agent` and `ssh-add`
- `--no-copy`                Skip copying pubkey to clipboard

Common tasks:
```bash
# Regenerate clean key with your email
./setup-ssh.sh --email you@example.com --force

# Recover a missing public key from an existing private key
ssh-keygen -y -f ~/.ssh/id_ed25519 > ~/.ssh/id_ed25519.pub && chmod 644 ~/.ssh/id_ed25519.pub

# Test GitHub SSH
ssh -T git@github.com
```

### 3) Initialize and push this repo
```bash
cd /path/to/this/repo
git init
git add -A
git commit -m "Initial commit: setup scripts and config"
git branch -M main
git remote add origin git@github.com:<your-user>/<your-repo>.git
git push -u origin main
```

### 4) VS Code configuration (optional)
Set MesloLGS Nerd Font for integrated terminal in VS Code:

Edit `settings.json` and add:
```json
{
    "terminal.integrated.fontFamily": "MesloLGS NF"
}
```

### Troubleshooting
- If Zsh isn’t default after running: `chsh -s "$(which zsh)"` and log out/in.
- If powerlevel10k icons look wrong, ensure the font is set to "MesloLGS NF" in Terminator.
- If clipboard copy fails in SSH script, install `xclip`: `sudo apt-get install -y xclip`.


