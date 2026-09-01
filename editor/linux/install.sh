#!/usr/bin/env bash
# install.sh - installs Bolt Studio for the current Linux user.
#
# Extracts the bundled portable app into ~/.local/share/bolt-studio,
# symlinks a launcher into ~/.local/bin, and registers a .desktop entry
# so Bolt Studio shows up in application menus/launchers - all without
# root, matching the XDG user-install convention most desktop Linux
# distros already expect (~/.local/bin is on PATH by default on
# Ubuntu/Fedora/most others that ship a modern GNOME/KDE session).
#
# Usage: run this script from inside the extracted BoltStudio-linux-x64
# directory (it lives right next to the "VSCode-linux-x64" folder it
# installs).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="$SCRIPT_DIR/VSCode-linux-x64"
INSTALL_DIR="$HOME/.local/share/bolt-studio"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

if [ ! -d "$APP_SRC" ]; then
  echo "error: VSCode-linux-x64 not found next to this script (expected $APP_SRC)." >&2
  echo "Run this script from inside the extracted BoltStudio-linux-x64 tarball." >&2
  exit 1
fi

echo "Installing Bolt Studio to $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
mkdir -p "$(dirname "$INSTALL_DIR")"
cp -r "$APP_SRC" "$INSTALL_DIR"

# The real build (checked directly in CI) names the Linux launcher
# after product.json's applicationName - "bolt-studio" here, at the top
# level of the extracted tree, not "codium" and not under bin/ (an
# earlier version of this script wrongly assumed the upstream VSCodium
# default naming). Still checks a couple of fallback locations rather
# than hardcoding just the one path, in case that changes again.
for candidate in "$INSTALL_DIR/bolt-studio" "$INSTALL_DIR/bin/bolt-studio" "$INSTALL_DIR/codium" "$INSTALL_DIR/bin/codium"; do
  if [ -x "$candidate" ]; then
    LAUNCHER="$candidate"
    break
  fi
done
if [ -z "${LAUNCHER:-}" ]; then
  echo "error: couldn't find the Bolt Studio launcher under $INSTALL_DIR." >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
ln -sf "$LAUNCHER" "$BIN_DIR/bolt-studio"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/bolt-studio.desktop" <<EOF
[Desktop Entry]
Name=Bolt Studio
Comment=Editor for the Bolt programming language
Exec=$LAUNCHER %F
Icon=bolt-studio
Terminal=false
Type=Application
Categories=Development;IDE;
StartupWMClass=bolt-studio
EOF

mkdir -p "$ICON_DIR"
if [ -f "$INSTALL_DIR/resources/app/resources/linux/code.png" ]; then
  cp "$INSTALL_DIR/resources/app/resources/linux/code.png" "$ICON_DIR/bolt-studio.png"
fi

update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

echo "Done. Launch with 'bolt-studio' (make sure $BIN_DIR is on your PATH)"
echo "or find \"Bolt Studio\" in your application menu."
