# Bundled SDL2 runtime (Windows) / system SDL2 (Linux)

Bolt's game-dev builtins get real GPU-accelerated rendering (via
`SDL_Renderer`) and cross-platform audio (via `SDL_QueueAudio`) instead of
tkinter's software `Canvas` and Windows-only `winsound`, on both Windows
and Linux.

**Windows**: `SDL2.dll`, `SDL2_gfx.dll`, and `SDL2_image.dll` (x64) are
bundled right here, with no extra install step - same "zero dependency"
spirit as the rest of this project.
- Source: the official `pysdl2-dll` PyPI wheel (`pysdl2_dll-2.32.10-py2.py3-none-win_amd64.whl`),
  itself a redistribution of the upstream SDL2/SDL2_gfx/SDL2_image builds.
- License: zlib (SDL2, SDL2_image) / zlib-libpng-style (SDL2_gfx) - both
  permissive, redistribution-friendly, no royalty. See
  https://www.libsdl.org/license.php and https://libsdl.org/projects/old/SDL_image/
  and https://www.ferzkopp.net/wordpress/2016/01/02/sdl_gfx-sdl2_gfx/ for the
  upstream license text.

**Linux**: nothing is bundled here - `src/bolt/sdl_backend.py` loads the
system's own SDL2 install directly via `ctypes.CDLL`, trying each real
distro `.so` name in turn (e.g. `libSDL2-2.0.so.0`), not
`ctypes.util.find_library()` - verified empirically that it returns
`None` on a stock Debian/Ubuntu system with only the runtime packages
installed (it looks for the unversioned symlink that ships only in the
`-dev` packages). Install with:
```
sudo apt install libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0   # Debian/Ubuntu
sudo dnf install SDL2 SDL2_gfx SDL2_image                              # Fedora
```

Loaded relative to the repo root the same way `packages/` is - see
`_RUNTIME_DIR` in `src/bolt/sdl_backend.py`. If SDL2 isn't available on
either platform (DLLs missing on Windows, packages not installed on
Linux, or any other OS such as macOS), Bolt's game builtins fall back to
the original tkinter backend automatically - see `sdl_backend.available()`
in `src/bolt/builtins.py`.
