# nboltc — the native Bolt interpreter

A from-scratch Bolt interpreter written in C, with no Python runtime
dependency. This is a genuinely separate implementation (new lexer,
parser, and tree-walking evaluator in `bolt.c`), not a wrapper around
the existing Python one — the same relationship CPython has to the
Python language: Bolt-the-language, implemented natively.

## Build (Windows, MSVC)

```
powershell -File native\build.ps1
```

or manually from a VS Developer prompt:

```
cl /O2 bolt.c /Fe:nboltc.exe user32.lib gdi32.lib winmm.lib /link /STACK:67108864
```

## Build (Linux, gcc + SDL2)

Needs SDL2 dev headers (`apt install libsdl2-dev` or equivalent):

```
bash native/build-linux.sh
```

or manually:

```
gcc -O2 -DBOLT_USE_SDL -o nboltc bolt.c $(sdl2-config --cflags --libs) -lm
```

Without `-DBOLT_USE_SDL`, the game-dev builtins (`window()`, `tick()`,
etc.) aren't compiled in on non-Windows builds and calling them fails
with a clear `undefined name` error rather than a crash.

## Run

```
native\nboltc.exe examples\loops.bo      # Windows
native/nboltc examples/loops.bo          # Linux
```

## What works today (verified against the Python implementation's output)

- Numbers, strings, booleans, `nil`, lists, maps
- `let`, assignment, arithmetic/comparison/logical operators, string
  concat (`+`) and repeat (`*`)
- `if`/`else`, `while`, `for x in ...` (over `range()` and lists),
  `break`, `continue`
- Named and anonymous functions, closures, recursion (tested to
  50,000+ levels with the bundled 64MB stack — see `/STACK` above)
- Core builtins: `print`, `len`, `type`, `range`, `push`, `pop`,
  `keys`, `str`, `num`, `upper`, `lower`, `trim`, `sqrt`, `abs`,
  `floor`, `ceil`, `min`, `max`, `sort`, `reverse`
- **Native game-dev builtins**, on two backends with the same
  function names/signatures on both:
  - **Windows**: real Win32 GDI, no dependency install needed.
  - **Linux**: SDL2 (`-DBOLT_USE_SDL`, needs `libsdl2-dev`).

  `window()`, `tick()`, `clear()`, `rect()`, `circle()`, `line()`,
  `key()`, `mouse_x()`/`mouse_y()`/`mouse_down()`, `window_size()`, `close_window()`,
  `beep()`. `draw_text()` is a no-op on the Linux/SDL2 backend for now
  (no font decoder wired up there yet) but present and callable rather
  than an error, so the same script runs on both without special-casing.
- **Physics/collision helpers** (cross-platform, no windowing
  dependency — usable even without `window()`): `rects_overlap()`,
  `circles_overlap()`, `circle_rect_overlap()`, `clamp()`, `lerp()`,
  `distance()`, `random()`, `apply_gravity()`, `physics_step()`, and
  `physics_integrate()`.
  These are the same small, composable building blocks the Python
  implementation's `packages/` scripts use to build actual physics on
  top of, not a physics *engine* — see the honest gaps below.

## What's honestly not here yet

This is a new, smaller implementation, not full parity with the
Python VM:

- No gradual typing, tensors, `import()`/modules, or `pyimport()` —
  `pyimport()` specifically can't exist here by definition, since the
  whole point of this build is having no Python runtime to call into.
- No `draw_image()` / `play_sound()` (need an image/audio decoder
  this build doesn't have yet), no `replace`/`starts_with`/`slice`/
  `concat`/`round`/`pow` stdlib functions yet.
- No sprite animation, particle system, tilemap renderer, or camera —
  build these in Bolt itself on top of the physics helpers above, the
  same way the Python implementation's `packages/scenes.bo` does.
- No text rendering on the Linux/SDL2 backend yet (`draw_text()` is a
  silent no-op there) — needs SDL_ttf or a bitmap font, not yet added.
- No bytecode VM or `--native` AOT path — this is a tree-walker only,
  so it does not currently match the speed of Bolt's `--native` mode.
- No garbage collector — values are arena-leaked for the process
  lifetime. Fine for scripts and games that exit; not suitable yet
  for a long-running server process.
- No macOS backend (the game builtins are Win32 GDI or SDL2/Linux
  only for now).

Calling an unimplemented builtin fails with a clear `undefined name`
error rather than crashing (verified — see the min/max bounds fix in
this file's history) — same "fail loud, not silently" stance as the
rest of Bolt.
