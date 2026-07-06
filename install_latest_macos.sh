#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/RayDurlok/soundbrowser.git"
RELEASE_API="https://api.github.com/repos/RayDurlok/soundbrowser/releases/latest"
APP_DIR="${RESOLVE_FREESOUND_BROWSER_DIR:-$HOME/Apps/ResolveFreesoundBrowser}"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

latest_release_tag() {
  curl -fsSL "$RELEASE_API" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

find_brew() {
  if command -v brew >/dev/null 2>&1; then
    command -v brew
  elif [ -x /opt/homebrew/bin/brew ]; then
    echo /opt/homebrew/bin/brew
  elif [ -x /usr/local/bin/brew ]; then
    echo /usr/local/bin/brew
  fi
}

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This installer is for macOS. Use install_latest_linux.sh on Linux." >&2
  exit 1
fi

require_command curl

BREW_BIN="$(find_brew)"
if [ -z "$BREW_BIN" ]; then
  echo "Homebrew is required for Python and ffmpeg and was not found."
  echo "Installing Homebrew from $HOMEBREW_INSTALL_URL"
  /bin/bash -c "$(curl -fsSL "$HOMEBREW_INSTALL_URL")"
  BREW_BIN="$(find_brew)"
fi

if [ -z "$BREW_BIN" ]; then
  echo "Homebrew installation completed, but brew is not available yet." >&2
  echo "Open a new Terminal and run this installer again." >&2
  exit 1
fi

eval "$("$BREW_BIN" shellenv)"
BREW_BIN="$(command -v brew)"

if ! command -v git >/dev/null 2>&1; then
  "$BREW_BIN" install git
fi
if ! "$BREW_BIN" list --versions python >/dev/null 2>&1; then
  "$BREW_BIN" install python
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  "$BREW_BIN" install ffmpeg
fi

require_command git
PYTHON_BIN="$("$BREW_BIN" --prefix python)/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Homebrew Python was not found at $PYTHON_BIN" >&2
  exit 1
fi

latest_tag="$(latest_release_tag)"
echo "Installing Resolve Freesound Browser $latest_tag"

mkdir -p "$(dirname "$APP_DIR")"

if [ -d "$APP_DIR/.git" ]; then
  if [ -n "$(git -C "$APP_DIR" status --porcelain)" ]; then
    stash_name="resolve-freesound-browser-installer-$(date +%Y%m%d-%H%M%S)"
    git -C "$APP_DIR" stash push --include-untracked -m "$stash_name"
    echo "Saved local changes in Git stash: $stash_name"
    echo "Restore them later with: git -C \"$APP_DIR\" stash pop"
  fi
  git -C "$APP_DIR" fetch --tags --prune "$REPO_URL"
  git -C "$APP_DIR" checkout --detach "$latest_tag"
elif [ -e "$APP_DIR" ]; then
  echo "Target exists but is not a Git checkout: $APP_DIR" >&2
  echo "Move it aside or set RESOLVE_FREESOUND_BROWSER_DIR to another folder." >&2
  exit 1
else
  git clone --depth 1 --branch "$latest_tag" "$REPO_URL" "$APP_DIR"
fi

"$PYTHON_BIN" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install --upgrade -r "$APP_DIR/requirements.txt"
"$APP_DIR/install_macos_user.sh"

echo
echo "Installed latest release: $latest_tag"
echo "Open Resolve Freesound Browser from Applications or run:"
echo "  open \"$HOME/Applications/Resolve Freesound Browser.app\""
