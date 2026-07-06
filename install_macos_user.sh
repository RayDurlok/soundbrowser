#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$APP_DIR/.venv/bin/python"
APP_BUNDLE="${RESOLVE_FREESOUND_BROWSER_APP_BUNDLE:-$HOME/Applications/Resolve Freesound Browser.app}"
BIN_DIR="$HOME/.local/bin"
RESOLVE_SCRIPTS_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
RESOLVE_SCRIPT="$RESOLVE_SCRIPTS_DIR/Resolve Freesound Browser.py"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
LAUNCHER="$MACOS_DIR/ResolveFreesoundBrowser"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This installer is for macOS." >&2
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Missing virtual environment: $VENV_PYTHON" >&2
  echo "Run install_latest_macos.sh first, or create .venv manually." >&2
  exit 1
fi

VERSION="$($VENV_PYTHON -c 'import sys; sys.path.insert(0, sys.argv[1]); from resolve_freesound_browser import __version__; print(__version__)' "$APP_DIR")"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$BIN_DIR" "$RESOLVE_SCRIPTS_DIR"
printf '%s\n' "$APP_DIR" > "$RESOURCES_DIR/app-path"

cat > "$LAUNCHER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$(<"$CONTENTS_DIR/Resources/app-path")"
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/run.py" "$@"
EOF
chmod +x "$LAUNCHER"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>Resolve Freesound Browser</string>
  <key>CFBundleExecutable</key>
  <string>ResolveFreesoundBrowser</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>org.raydurlok.resolve-freesound-browser</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Resolve Freesound Browser</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$VERSION</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$CONTENTS_DIR/Info.plist" >/dev/null
fi

if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  icon_work_dir="$(mktemp -d)"
  iconset="$icon_work_dir/AppIcon.iconset"
  mkdir -p "$iconset"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$APP_DIR/resources/icon.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
    double_size=$((size * 2))
    sips -z "$double_size" "$double_size" "$APP_DIR/resources/icon.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$iconset" -o "$RESOURCES_DIR/AppIcon.icns"
  rm -rf "$icon_work_dir"
fi

cat > "$BIN_DIR/resolve-freesound-browser" <<EOF
#!/usr/bin/env bash
exec /usr/bin/open "$APP_BUNDLE" --args "\$@"
EOF
chmod +x "$BIN_DIR/resolve-freesound-browser"

app_bundle_repr="$($VENV_PYTHON -c 'import sys; print(repr(sys.argv[1]))' "$APP_BUNDLE")"
cat > "$RESOLVE_SCRIPT" <<EOF
#!/usr/bin/env python3

import subprocess

subprocess.Popen(["/usr/bin/open", $app_bundle_repr])
EOF

lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$lsregister" ]; then
  "$lsregister" -f "$APP_BUNDLE" >/dev/null 2>&1 || true
fi
touch "$APP_BUNDLE"

echo "Installed macOS integration:"
echo "  App: $APP_BUNDLE"
echo "  Command: $BIN_DIR/resolve-freesound-browser"
echo "  Resolve: $RESOLVE_SCRIPT"
