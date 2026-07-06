#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/RayDurlok/soundbrowser.git"
RELEASE_API="https://api.github.com/repos/RayDurlok/soundbrowser/releases/latest"
APP_DIR="${RESOLVE_FREESOUND_BROWSER_DIR:-$HOME/Apps/ResolveFreesoundBrowser}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

latest_release_tag() {
  curl -fsSL "$RELEASE_API" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

require_command curl
require_command git
require_command python3

latest_tag="$(latest_release_tag)"
echo "Installing Resolve Freesound Browser $latest_tag"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: ffmpeg was not found. Install it with: brew install ffmpeg" >&2
fi

mkdir -p "$(dirname "$APP_DIR")"

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --tags --prune origin
  git -C "$APP_DIR" checkout --detach "$latest_tag"
elif [ -e "$APP_DIR" ]; then
  echo "Target exists but is not a Git checkout: $APP_DIR" >&2
  echo "Move it aside or set RESOLVE_FREESOUND_BROWSER_DIR to another folder." >&2
  exit 1
else
  git clone --depth 1 --branch "$latest_tag" "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

echo
echo "Installed latest release: $latest_tag"
echo "Start with:"
echo "  cd \"$APP_DIR\""
echo "  source .venv/bin/activate"
echo "  python run.py"
