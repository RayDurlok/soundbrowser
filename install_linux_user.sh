#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
RESOLVE_SCRIPTS_DIR="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Edit"

mkdir -p "$BIN_DIR" "$APPS_DIR" "$RESOLVE_SCRIPTS_DIR"

cat > "$BIN_DIR/resolve-freesound-browser" <<EOF
#!/usr/bin/env bash
exec python3 "$APP_DIR/run.py" "\$@"
EOF
chmod +x "$BIN_DIR/resolve-freesound-browser"

ln -sf "$APP_DIR/resolve_freesound_browser/resolve_launcher.py" \
  "$RESOLVE_SCRIPTS_DIR/Resolve Freesound Browser.py"

cat > "$APPS_DIR/resolve-freesound-browser.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Resolve Freesound Browser
Comment=Search Freesound previews and import them into DaVinci Resolve
Exec=$BIN_DIR/resolve-freesound-browser
Terminal=false
Categories=AudioVideo;Audio;
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "Installed:"
echo "  $BIN_DIR/resolve-freesound-browser"
echo "  $RESOLVE_SCRIPTS_DIR/Resolve Freesound Browser.py"
echo "  $APPS_DIR/resolve-freesound-browser.desktop"
