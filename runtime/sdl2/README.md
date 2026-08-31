# Bundled SDL2 runtime

`SDL2.dll`, `SDL2_gfx.dll`, and `SDL2_image.dll` (Windows x64), bundled here
so Bolt's game-dev builtins get real GPU-accelerated rendering (via
`SDL_Renderer`) instead of tkinter's software `Canvas`, with no extra
install step - same "zero dependency" spirit as the rest of this project.

- Source: the official `pysdl2-dll` PyPI wheel (`pysdl2_dll-2.32.10-py2.py3-none-win_amd64.whl`),
  itself a redistribution of the upstream SDL2/SDL2_gfx/SDL2_image builds.
- License: zlib (SDL2, SDL2_image) / zlib-libpng-style (SDL2_gfx) - both
  permissive, redistribution-friendly, no royalty. See
  https://www.libsdl.org/license.php and https://libsdl.org/projects/old/SDL_image/
  and https://www.ferzkopp.net/wordpress/2016/01/02/sdl_gfx-sdl2_gfx/ for the
  upstream license text.
- Loaded by `src/bolt/sdl_backend.py` via `ctypes`, resolved relative to the
  repo root the same way `packages/` is - see `_RUNTIME_DIR` there.
- If these DLLs are missing (e.g. non-Windows, or this directory stripped
  out), Bolt's game builtins fall back to the original tkinter backend
  automatically - see `sdl_backend.available()` in `src/bolt/builtins.py`.
