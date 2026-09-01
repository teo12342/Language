#!/usr/bin/env bash
# Builds nboltc on Linux with the SDL2 game-dev backend enabled.
# Needs SDL2 dev headers: apt install libsdl2-dev (or your distro's
# equivalent). Mirrors native/build.ps1's role for Windows/MSVC.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gcc -O2 -DBOLT_USE_SDL -o "${HERE}/nboltc" "${HERE}/bolt.c" $(sdl2-config --cflags --libs) -lm
echo "Built ${HERE}/nboltc"
