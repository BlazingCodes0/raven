#!/bin/bash
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
SHARE="$HOME/.local/share/applications"
DESK="$HOME/Desktop"

mkdir -p "$SHARE" "$DESK"

cat > "$SHARE/Raven.desktop" << EOD
[Desktop Entry]
Version=1.0
Type=Application
Name=Raven
Comment=Raven Lab (supervised with lifeline)
Exec=$APP_DIR/raven_boot.sh
Icon=$APP_DIR/assets/raven_neon.png
Terminal=false
Categories=Finance;Utility;
EOD

cp -f "$SHARE/Raven.desktop" "$DESK/Raven.desktop"
cp -f "$SHARE/Raven.desktop" "$APP_DIR/Raven.desktop" 2>/dev/null || true

chmod +x "$SHARE/Raven.desktop" "$DESK/Raven.desktop" 2>/dev/null || true
chmod +x "$APP_DIR/raven_boot.sh" "$APP_DIR/install.sh" 2>/dev/null || true

echo "Raven launchers created."
