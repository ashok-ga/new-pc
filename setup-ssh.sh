#!/usr/bin/env bash

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: setup-ssh.sh [--email you@example.com] [--force] [--no-agent] [--no-copy]

Generates an ed25519 SSH key (if missing), configures ~/.ssh/config, starts ssh-agent,
adds the key, and prints the public key. Copies to clipboard if xclip is available
unless --no-copy is passed.

Options:
  --email <addr>   Email/comment for the key. Default: "$USER@$HOSTNAME"
  --force          Overwrite existing ~/.ssh/id_ed25519
  --no-agent       Do not start ssh-agent or add the key
  --no-copy        Do not copy public key to clipboard
  -h, --help       Show this help
EOF
}

email="${USER}@${HOSTNAME}"
force_overwrite="no"
use_agent="yes"
do_copy="yes"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --email)
      email="${2:-}"
      shift 2
      ;;
    --force)
      force_overwrite="yes"
      shift
      ;;
    --no-agent)
      use_agent="no"
      shift
      ;;
    --no-copy)
      do_copy="no"
      shift
      ;;
    -h|--help)
      show_help; exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help; exit 1
      ;;
  esac
done

log() { printf "\033[1;32m[+] %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m[x] %s\033[0m\n" "$*"; }

main() {
  local ssh_dir="$HOME/.ssh"
  local key_file="$ssh_dir/id_ed25519"
  mkdir -p "$ssh_dir"
  chmod 700 "$ssh_dir"

  if [[ -f "$key_file" && "$force_overwrite" != "yes" ]]; then
    log "SSH key already exists: $key_file (use --force to overwrite)"
    # Recreate missing public key if needed
    if [[ ! -f "$key_file.pub" ]]; then
      log "Public key missing; recreating from private key..."
      ssh-keygen -y -f "$key_file" > "$key_file.pub"
      chmod 644 "$key_file.pub"
    fi
  else
    if [[ -f "$key_file" && "$force_overwrite" == "yes" ]]; then
      warn "Overwriting existing key at $key_file"
      rm -f "$key_file" "$key_file.pub"
    fi
    log "Generating SSH ed25519 key with comment: $email"
    ssh-keygen -t ed25519 -a 100 -C "$email" -f "$key_file" -N ""
    chmod 600 "$key_file" && chmod 644 "$key_file.pub"
  fi

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
    log "Created $cfg"
  else
    # Ensure minimal defaults present under Host *
    grep -q "^Host \*" "$cfg" || printf '\nHost *\n' >> "$cfg"
    grep -q "AddKeysToAgent" "$cfg" || sed -i '/^Host \*/a\    AddKeysToAgent yes' "$cfg"
    grep -q "IdentityFile ~/.ssh/id_ed25519" "$cfg" || sed -i '/^Host \*/a\    IdentityFile ~/.ssh/id_ed25519' "$cfg"
    grep -q "HashKnownHosts" "$cfg" || sed -i '/^Host \*/a\    HashKnownHosts yes' "$cfg"
    chmod 600 "$cfg"
    log "Updated $cfg"
  fi

  if [[ "$use_agent" == "yes" ]]; then
    if ! pgrep -u "$USER" ssh-agent >/dev/null 2>&1; then
      eval "$(ssh-agent -s)" >/dev/null 2>&1 || true
    fi
    ssh-add "$key_file" >/dev/null 2>&1 || warn "Could not add key to agent (is agent running?)"
  fi

  if [[ "$do_copy" == "yes" && -f "$key_file.pub" ]]; then
    if command -v xclip >/dev/null 2>&1; then
      xclip -selection clipboard < "$key_file.pub"
      log "Public key copied to clipboard."
    else
      warn "xclip not installed; cannot copy to clipboard automatically."
    fi
  fi

  echo "----- PUBLIC KEY (add to GitHub/GitLab/Server) -----"
  cat "$key_file.pub"
}

main "$@"


