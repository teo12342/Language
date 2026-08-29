#!/usr/bin/env bash
# Builds Bolt Studio: a VSCodium fork, rebranded, with Bolt language support
# (editor/vscode-bolt) baked in as a built-in extension - not something a
# user installs separately, it's just there when they open the app.
#
# This is a real build script, not a stub - but it needs a machine with the
# full VSCodium/VS Code build toolchain (Node.js LTS, Python 3, a C/C++
# toolchain, and several GB of disk) and takes on the order of an hour.
# It is not run automatically by this repo's tests or CI.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${HERE}/.vscodium-src"

if [ ! -d "$WORK" ]; then
    git clone --depth 1 https://github.com/VSCodium/vscodium.git "$WORK"
fi

# Bolt Studio's own branding replaces VSCodium's default product.json.
cp "${HERE}/branding/product.json" "${WORK}/product.json"

# The Bolt language extension ships built into the app.
mkdir -p "${WORK}/vscode/extensions"
rm -rf "${WORK}/vscode/extensions/bolt-lang"
cp -r "${HERE}/vscode-bolt" "${WORK}/vscode/extensions/bolt-lang"

cd "$WORK"
./get_repo.sh
./build.sh

echo "Build artifacts are under ${WORK}/VSCode-*"
