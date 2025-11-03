#!/usr/bin/env bash

set -euo pipefail

# This script sets up a new Ubuntu/Debian-based PC with:
# - Terminator
# - Zsh as default shell
# - Oh My Zsh + powerlevel10k
# - Dracula theme for Terminator
# - zsh-autosuggestions and zsh-completions
# - MesloLGS Nerd Fonts for p10k
# - Neovim built from source (stable)
# - LazyVim starter

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  SUDO="sudo"
else
  SUDO=""
fi

log() { printf "\033[1;32m[+] %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m[x] %s\033[0m\n" "$*"; }

require_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then
    err "This script targets Debian/Ubuntu (apt)."; exit 1
  fi
}

update_apt_once() {
  if [[ -z "${APT_UPDATED:-}" ]]; then
    $SUDO apt-get update -y
    APT_UPDATED=1
  fi
}

install_packages() {
  log "Installing base packages..."
  update_apt_once
  $SUDO apt-get install -y \
    git curl wget ca-certificates \
    build-essential pkg-config \
    libtool libtool-bin autoconf automake \
    cmake g++ unzip gettext \
    ninja-build doxygen \
    zsh terminator fonts-powerline \
    ripgrep fd-find
}

set_default_shell_zsh() {
  if [[ "${SHELL:-}" != *"zsh"* ]]; then
    local zsh_path
    zsh_path="$(command -v zsh || true)"
    if [[ -n "$zsh_path" ]]; then
      log "Setting default shell to zsh..."
      chsh -s "$zsh_path" "$USER" || warn "Could not change shell automatically. Change manually with: chsh -s $(which zsh)"
    fi
  else
    log "Zsh already default shell."
  fi
}

install_oh_my_zsh() {
  if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
    log "Installing Oh My Zsh (non-interactive)..."
    RUNZSH=no CHSH=no KEEP_ZSHRC=yes \
      sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
  else
    log "Oh My Zsh already installed."
  fi
}

install_powerlevel10k() {
  local theme_dir="$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
  if [[ ! -d "$theme_dir" ]]; then
    log "Installing powerlevel10k..."
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$theme_dir"
  else
    log "powerlevel10k already present. Pulling updates..."
    git -C "$theme_dir" pull --ff-only || true
  fi

  if [[ -f "$HOME/.zshrc" ]]; then
    if ! grep -q '^ZSH_THEME="powerlevel10k/powerlevel10k"' "$HOME/.zshrc"; then
      log "Setting ZSH_THEME to powerlevel10k in .zshrc..."
      if grep -q '^ZSH_THEME=' "$HOME/.zshrc"; then
        sed -i 's#^ZSH_THEME=.*#ZSH_THEME="powerlevel10k/powerlevel10k"#' "$HOME/.zshrc"
      else
        printf '\nZSH_THEME="powerlevel10k/powerlevel10k"\n' >> "$HOME/.zshrc"
      fi
    fi
  fi
}

install_zsh_plugins() {
  local custom_dir="$HOME/.oh-my-zsh/custom"
  local autosugg="$custom_dir/plugins/zsh-autosuggestions"
  local compl="$custom_dir/plugins/zsh-completions"

  if [[ ! -d "$autosugg" ]]; then
    log "Installing zsh-autosuggestions..."
    git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions "$autosugg"
  else
    git -C "$autosugg" pull --ff-only || true
  fi

  if [[ ! -d "$compl" ]]; then
    log "Installing zsh-completions..."
    git clone --depth=1 https://github.com/zsh-users/zsh-completions "$compl"
  else
    git -C "$compl" pull --ff-only || true
  fi

  # Enable in .zshrc plugins list
  if [[ -f "$HOME/.zshrc" ]]; then
    if grep -q '^plugins=' "$HOME/.zshrc"; then
      if ! grep -q 'zsh-autosuggestions' "$HOME/.zshrc"; then
        log "Adding zsh-autosuggestions to plugins in .zshrc..."
        sed -i 's/plugins=(\([^)]*\))/plugins=(\1 zsh-autosuggestions)/' "$HOME/.zshrc"
      fi
      if ! grep -q 'zsh-completions' "$HOME/.zshrc"; then
        log "Adding zsh-completions to plugins in .zshrc..."
        sed -i 's/plugins=(\([^)]*\))/plugins=(\1 zsh-completions)/' "$HOME/.zshrc"
      fi
    else
      log "Creating plugins line in .zshrc..."
      printf '\nplugins=(git zsh-autosuggestions zsh-completions)\n' >> "$HOME/.zshrc"
    fi

    # Source completions
    if ! grep -q 'fpath+=\(\$HOME/.oh-my-zsh/custom/plugins/zsh-completions/src\)' "$HOME/.zshrc"; then
      printf '\nfpath+=("$HOME/.oh-my-zsh/custom/plugins/zsh-completions/src")\nautoload -U compinit && compinit\n' >> "$HOME/.zshrc"
    fi
  fi
}

install_nerd_fonts() {
  local font_dir="$HOME/.local/share/fonts"
  mkdir -p "$font_dir"
  # MesloLGS Nerd Font (recommended for powerlevel10k)
  local base="https://github.com/romkatv/powerlevel10k-media/raw/master"
  for f in "MesloLGS NF Regular.ttf" "MesloLGS NF Bold.ttf" "MesloLGS NF Italic.ttf" "MesloLGS NF Bold Italic.ttf"; do
    if [[ ! -f "$font_dir/$f" ]]; then
      log "Downloading $f..."
      curl -fsSL -o "$font_dir/$f" "$base/${f// /%20}"
    fi
  done
  fc-cache -f "$font_dir" || true
}

apply_dracula_terminator() {
  local cfg_dir="$HOME/.config/terminator"
  local cfg_file="$cfg_dir/config"
  mkdir -p "$cfg_dir"

  # Minimal Terminator config with Dracula profile
  if [[ ! -f "$cfg_file" ]] || ! grep -q "\[profiles\]" "$cfg_file"; then
    log "Writing Dracula Terminator config..."
    cat > "$cfg_file" << 'EOF'
[global_config]
[keybindings]
[profiles]
  [[dracula]]
    palette = "#000000:#ff5555:#50fa7b:#f1fa8c:#bd93f9:#ff79c6:#8be9fd:#bbbbbb:#44475a:#ff5555:#50fa7b:#f1fa8c:#bd93f9:#ff79c6:#8be9fd:#ffffff"
    background_color = "#282a36"
    background_darkness = 0.95
    background_type = transparent
    cursor_color = "#f8f8f2"
    foreground_color = "#f8f8f2"
    use_system_font = False
    font = MesloLGS NF 12
    scrollbar_position = hidden
    show_titlebar = False
  [[default]]
    use_custom_command = False
    custom_command =
    palette = "#000000:#ff5555:#50fa7b:#f1fa8c:#bd93f9:#ff79c6:#8be9fd:#bbbbbb:#44475a:#ff5555:#50fa7b:#f1fa8c:#bd93f9:#ff79c6:#8be9fd:#ffffff"
    background_color = "#282a36"
    foreground_color = "#f8f8f2"
    scrollbar_position = hidden
    show_titlebar = False
    use_system_font = False
    font = MesloLGS NF 12
[layouts]
  [[default]]
    [[[child1]]]
      type = Terminal
      profile = dracula
    [[[window0]]]
      type = Window
      parent = ""
      child = child1
[plugins]
EOF
  else
    warn "Existing Terminator config detected. Updating font and titlebar settings."
    # Ensure MesloLGS NF font is used
    if grep -q '^\s*font\s*=\s*' "$cfg_file"; then
      sed -i 's/^\(\s*font\s*=\s*\).*/\1MesloLGS NF 12/' "$cfg_file"
    else
      printf '\n  [[dracula]]\n    font = MesloLGS NF 12\n  [[default]]\n    font = MesloLGS NF 12\n' >> "$cfg_file"
    fi
    # Ensure use_system_font is False
    if grep -q '^\s*use_system_font\s*=\s*' "$cfg_file"; then
      sed -i 's/^\(\s*use_system_font\s*=\s*\).*/\1False/' "$cfg_file"
    else
      printf '\n  [[dracula]]\n    use_system_font = False\n  [[default]]\n    use_system_font = False\n' >> "$cfg_file"
    fi
    # Ensure titlebar hidden
    if grep -q '^\s*show_titlebar\s*=\s*' "$cfg_file"; then
      sed -i 's/^\(\s*show_titlebar\s*=\s*\).*/\1False/' "$cfg_file"
    else
      printf '\n  [[dracula]]\n    show_titlebar = False\n  [[default]]\n    show_titlebar = False\n' >> "$cfg_file"
    fi
  fi
}

make_terminator_default() {
  if command -v terminator >/dev/null 2>&1; then
    log "Setting Terminator as default x-terminal-emulator..."
    $SUDO update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator /usr/bin/terminator 50 || true
    $SUDO update-alternatives --set x-terminal-emulator /usr/bin/terminator || true
  else
    warn "Terminator not found; cannot set as default terminal."
  fi
}

build_neovim_from_source() {
  if command -v nvim >/dev/null 2>&1; then
    log "Neovim already installed: $(nvim --version | head -n1)"
    return
  fi
  log "Building Neovim from source (stable)..."
  local work_dir="$HOME/.local/src"
  mkdir -p "$work_dir"
  if [[ ! -d "$work_dir/neovim" ]]; then
    git clone --depth=1 -b stable https://github.com/neovim/neovim.git "$work_dir/neovim"
  else
    git -C "$work_dir/neovim" fetch --depth=1 origin stable || true
    git -C "$work_dir/neovim" checkout stable || true
    git -C "$work_dir/neovim" pull --ff-only || true
  fi
  pushd "$work_dir/neovim" >/dev/null
  make CMAKE_BUILD_TYPE=Release
  $SUDO make install
  popd >/dev/null
}

install_lazyvim() {
  local nvim_cfg="$HOME/.config/nvim"
  if [[ ! -d "$nvim_cfg" || -z "$(ls -A "$nvim_cfg" 2>/dev/null || true)" ]]; then
    log "Installing LazyVim starter..."
    git clone --depth=1 https://github.com/LazyVim/starter "$nvim_cfg"
    rm -rf "$nvim_cfg/.git"
  else
    warn "~/.config/nvim is not empty. Skipping LazyVim starter clone."
  fi
}

setup_ssh_keys() {
  local ssh_dir="$HOME/.ssh"
  local key_file="$ssh_dir/id_ed25519"
  mkdir -p "$ssh_dir"
  chmod 700 "$ssh_dir"

  if [[ ! -f "$key_file" ]]; then
    log "Generating new SSH ed25519 key..."
    local comment
    comment="${USER}@${HOSTNAME}"
    ssh-keygen -t ed25519 -a 100 -C "$comment" -f "$key_file" -N ""
  else
    log "SSH key already exists at $key_file"
  fi

  # Create/update SSH config with sane defaults
  local cfg="$ssh_dir/config"
  if [[ ! -f "$cfg" ]]; then
    cat > "$cfg" << 'EOF'
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
EOF
    chmod 600 "$cfg"
  else
    # Ensure IdentityFile and AddKeysToAgent exist for Host *
    if ! grep -q "^Host \*" "$cfg"; then
      printf '\nHost *\n    AddKeysToAgent yes\n    IdentityFile ~/.ssh/id_ed25519\n    HashKnownHosts yes\n' >> "$cfg"
    else
      grep -q "AddKeysToAgent" "$cfg" || sed -i '/^Host \*/a\    AddKeysToAgent yes' "$cfg"
      grep -q "IdentityFile ~/.ssh/id_ed25519" "$cfg" || sed -i '/^Host \*/a\    IdentityFile ~/.ssh/id_ed25519' "$cfg"
      grep -q "HashKnownHosts" "$cfg" || sed -i '/^Host \*/a\    HashKnownHosts yes' "$cfg"
    fi
    chmod 600 "$cfg"
  fi

  # Start ssh-agent and add key (best-effort)
  if ! pgrep -u "$USER" ssh-agent >/dev/null 2>&1; then
    eval "$(ssh-agent -s)" >/dev/null 2>&1 || true
  fi
  ssh-add "$key_file" >/dev/null 2>&1 || true

  # Print public key and try to copy to clipboard if available
  if command -v xclip >/dev/null 2>&1; then
    cat "$key_file.pub" | xclip -selection clipboard
    log "Public key copied to clipboard. Paste it into GitHub/GitLab SSH keys."
  else
    warn "Install xclip to auto-copy SSH public key. Showing key below:"
  fi
  echo "----- PUBLIC KEY (add to GitHub/GitLab) -----"
  cat "$key_file.pub"
}

main() {
  require_apt
  install_packages
  set_default_shell_zsh
  install_oh_my_zsh
  install_powerlevel10k
  install_zsh_plugins
  install_nerd_fonts
  apply_dracula_terminator
  make_terminator_default
  build_neovim_from_source
  install_lazyvim
  setup_ssh_keys

  log "All done!" 
  echo "- Restart your terminal (or log out/in) to use zsh as default."
  echo "- In Terminator, set font to MesloLGS NF for best powerlevel10k appearance."
}

main "$@"


