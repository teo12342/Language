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

## Run

```
native\nboltc.exe examples\loops.bo
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
  `floor`, `ceil`, `min`, `max`
- **Native Win32 game-dev builtins** (replacing the old
  tkinter/winsound-backed ones — real GDI, no dependency install
  needed): `window()`, `tick()`, `clear()`, `rect()`, `circle()`,
  `line()`, `draw_text()`, `key()`, `mouse_x()`/`mouse_y()`/
  `mouse_down()`, `close_window()`, `beep()`, `rects_overlap()`.
  Verified end-to-end: opens a real window, draws, and self-closes.

## What's honestly not here yet

This is a new, smaller implementation, not full parity with the
Python VM:

- No gradual typing, tensors, `import()`/modules, or `pyimport()` —
  `pyimport()` specifically can't exist here by definition, since the
  whole point of this build is having no Python runtime to call into.
- No `draw_image()` / `play_sound()` (need an image/audio decoder
  this build doesn't have yet), no `sort`/`reverse`/`replace`/
  `starts_with`/`slice`/`concat`/`round`/`pow` stdlib functions yet.
- No bytecode VM or `--native` AOT path — this is a tree-walker only,
  so it does not currently match the speed of Bolt's `--native` mode.
- No garbage collector — values are arena-leaked for the process
  lifetime. Fine for scripts and games that exit; not suitable yet
  for a long-running server process.
- Windows-only for now (the game builtins are Win32 GDI directly;
  Linux/macOS would need an X11/Cocoa backend, not yet written).

Calling an unimplemented builtin fails with a clear `undefined name`
error rather than crashing (verified — see the min/max bounds fix in
this file's history) — same "fail loud, not silently" stance as the
rest of Bolt.
