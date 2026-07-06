#!/usr/bin/env bash
set -euo pipefail

APP_BUNDLE="${RESOLVE_FREESOUND_BROWSER_APP_BUNDLE:-$HOME/Applications/Resolve Freesound Browser.app}"
COMMAND_PATH="$HOME/.local/bin/resolve-freesound-browser"
RESOLVE_SCRIPT="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/Resolve Freesound Browser.py"

if [ "${1:-}" != "--yes" ]; then
  printf 'Remove the app launcher and Resolve integration? [y/N] '
  read -r answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "Cancelled."; exit 0 ;;
  esac
fi

lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$lsregister" ] && [ -d "$APP_BUNDLE" ]; then
  "$lsregister" -u "$APP_BUNDLE" >/dev/null 2>&1 || true
fi

rm -rf "$APP_BUNDLE"
rm -f "$COMMAND_PATH" "$RESOLVE_SCRIPT"

echo "Removed macOS launchers and Resolve integration."
echo "The app checkout, settings, downloads, and cache were preserved."
