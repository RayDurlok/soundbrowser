#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
RESOLVE_SCRIPTS_DIR="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Edit"

mkdir -p "$BIN_DIR" "$APPS_DIR" "$ICON_DIR" "$RESOLVE_SCRIPTS_DIR"

cat > "$BIN_DIR/resolve-freesound-browser" <<EOF
#!/usr/bin/env bash
exec python3 "$APP_DIR/run.py" "\$@"
EOF
chmod +x "$BIN_DIR/resolve-freesound-browser"

ln -sf "$APP_DIR/resolve_freesound_browser/resolve_launcher.py" \
  "$RESOLVE_SCRIPTS_DIR/Resolve Freesound Browser.py"

install -m 0644 "$APP_DIR/resources/resolve-freesound-browser-wave.svg" \
  "$ICON_DIR/resolve-freesound-browser-wave.svg"

cat > "$APPS_DIR/resolve-freesound-browser.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Resolve Freesound Browser
Comment=Search Freesound previews and import them into DaVinci Resolve
Exec=$BIN_DIR/resolve-freesound-browser
Icon=resolve-freesound-browser-wave
Terminal=false
Categories=AudioVideo;Audio;
StartupWMClass=resolve-freesound-browser-wave
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "Installed:"
echo "  $BIN_DIR/resolve-freesound-browser"
echo "  $ICON_DIR/resolve-freesound-browser-wave.svg"
echo "  $RESOLVE_SCRIPTS_DIR/Resolve Freesound Browser.py"
echo "  $APPS_DIR/resolve-freesound-browser.desktop"
