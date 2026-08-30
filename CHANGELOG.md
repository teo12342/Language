# Changelog

All notable changes to Bolt, by version.

## Unreleased

Bolt Studio's release build switched from a zip of the portable
VSCodium build to a proper Windows installer:

- `.github/workflows/build-bolt-studio.yml` now locates the Inno
  Setup `.exe` that VSCodium's own `build.sh` already produces as part
  of a normal Windows build (previously ignored in favor of zipping
  the raw `VSCode-win32-x64/` folder) - `BoltStudio-Setup-win32-x64.exe`
  - and attaches that to the GitHub release instead. Fails loudly with
  a clear error if no setup exe is found, rather than silently doing
  nothing.
- Reasoning: a single-file installer is a more familiar, more
  trustworthy download than a 220MB zip a user has to extract by
  hand, especially for an unsigned build.

## v0.17.1

Started the freestanding/bare-metal roadmap (`native/freestanding/`) —
stage 0 only, verified for real rather than just described:

- `boot.asm`: a hand-written 512-byte x86 real-mode boot sector,
  assembled with NASM, ending in the `0x55 0xAA` boot signature.
- Installed and used a real toolchain (NASM + QEMU, via winget) to
  actually boot it in an emulator and capture its serial output,
  rather than claiming it works without running it. Verified output:
  `BOLT FREESTANDING: no OS, no libc, boots on bare x86.` — written by
  code running with nothing else present, no OS, no libc, no runtime.
- Honestly scoped in `native/freestanding/README.md`: this is
  hand-written assembly proving the toolchain path works, not yet a
  bridge from Bolt source to bare metal. The path from here to an
  actual "hello from Bolt" kernel (a freestanding C stage, raw
  pointer/`unsafe` support in the language, a `--freestanding`
  compiler flag) is laid out but not built yet.

## v0.17.0

New: `native/bolt.c` — a from-scratch, standalone native Bolt
interpreter written in C, with no Python runtime dependency
(Windows/MSVC for now). This is a new, smaller implementation, not a
full port of the Python VM.

- Covers a real subset of the language: numbers, strings, booleans,
  nil, lists, maps, functions/closures, recursion (verified to
  50,000+ levels with a 64MB stack), control flow, and a core builtin
  set. Verified byte-for-byte against the Python implementation's
  output on `examples/loops.bo`, `examples/closures.bo`, and
  `examples/fibonacci.bo`.
- Game-dev builtins (`window`, `tick`, `clear`, `rect`, `circle`,
  `line`, `draw_text`, `key`, `mouse_x`/`mouse_y`/`mouse_down`,
  `close_window`, `beep`, `rects_overlap`) are reimplemented natively
  on real Win32/GDI instead of tkinter/winsound — verified end-to-end
  with a real window that opens, draws, and self-closes.
- Honestly incomplete: no gradual typing, tensors, `import()`, or
  `pyimport()` (which can't exist here by definition — no Python
  runtime to call into); no bytecode VM or `--native` AOT path yet
  (tree-walking only); no garbage collector (values are arena-leaked
  for the process lifetime); most of the string/list stdlib
  (`sort`, `replace`, `slice`, etc.) isn't ported yet. See
  `native/README.md` for the full honest scope.
- This is additive — the existing Python-based interpreter, VM,
  `--native` compiler, and JS transpiler are unchanged.

## v0.16.0

More game-dev primitives: mouse input, a line-drawing helper, and
sound control - closing the "keyboard only" and "play but can't stop"
gaps from the last two rounds.

- New `mouse_x(win)` / `mouse_y(win)` / `mouse_down(win,
  button="left")`: real mouse position and button state (left or
  right), tracked via tkinter's Motion/Button events.
- New `line(win, x1, y1, x2, y2, color, width=1)`: a real missing
  drawing primitive (rect/circle/text/image existed, lines didn't).
- New `stop_sound()`: stops whatever `play_sound()` is currently
  playing asynchronously - completes the play/stop pairing.
- `examples/game_demo.bo` now supports moving the sprite by holding
  the mouse button (in addition to arrow keys), and draws a ground
  line.
- 114/114 tests pass; all new builtins smoke-tested end-to-end this
  session (real window, real mouse tracking, real line drawn, real
  beep + stop_sound sequence).

## v0.15.0

Investigated why the default VM engine runs `fib(30)` in ~17 seconds
(vs. Python's 0.122s) - a real, honest look at the bottleneck, not a
number-chasing exercise.

- Found and fixed a real architectural bug: every Bolt-to-Bolt function
  call recursed through a nested Python call (`self._run()` calling
  itself), so deep Bolt recursion consumed Python's own call stack.
  Profiling confirmed 392,835 recursive Python calls for a single
  fib(26) run - and a Bolt script recursing ~1000 levels deep crashed
  outright with `RecursionError: maximum recursion depth exceeded`
  (reproduced and confirmed on the pre-fix code).
- Rewrote the VM's call/return handling to use an explicit frame stack
  (the same technique CPython's and Lua's own eval loops use) instead
  of Python recursion - a Bolt function call now pushes a saved frame
  onto a plain list and continues the same loop; RETURN pops it back.
  Calls that enter from Python (a fresh script run, or a builtin like
  tmap()/serve() calling back into Bolt code) still nest/reenter
  correctly, verified against the full test suite including closures,
  nested closures, and webserver request handlers.
- Result, honestly reported: this is a correctness fix, not a speed
  win. A Bolt script recursing 50,000 levels deep now runs
  successfully (previously crashed at ~1,000); `fib(30)`'s wall time
  is unchanged (~17s), because profiling after the fix showed the
  real bottleneck is per-opcode dispatch cost in the interpreter loop
  itself, not Python call overhead - fixing that meaningfully would
  need a much larger rewrite (e.g. compiling to real Python bytecode)
  than is in scope here.
- 114/114 tests pass.

## v0.14.0

Fixed two real bugs in the native (`--native`) backend, found while
investigating why native compilation was failing entirely on a machine
that had MSVC but not gcc.

- `--native` was hardcoded to invoke `gcc`, so it failed outright with
  a raw `FileNotFoundError` traceback on any machine without gcc/MinGW
  on PATH - a real gap on stock Windows dev machines that only have
  Visual Studio installed. Now falls back to MSVC's `cl.exe` (found
  via `vswhere`, environment harvested from `vcvars64.bat`) when gcc
  isn't available, with a clear error only if neither compiler exists.
- Emitted C functions used the Bolt function's own name as the C
  symbol name directly, so a Bolt function named e.g. `hypot` silently
  collided with `<math.h>`'s own `hypot` - gcc let this slide, MSVC
  correctly rejected it (`C2375: redefinition; different linkage`).
  All emitted C symbols are now namespaced (`bolt_fn_<name>`), so this
  class of collision is no longer possible under any compiler.
- Result: native compilation, which had been silently broken on this
  machine, now genuinely works - `fib(30)` runs in ~0.005s of native
  execution (excluding one-time compile time), matching C/C++ within
  measurement noise, exactly as the language's own docs have always
  claimed but this machine couldn't previously verify.
- `tests/test_native.py`'s skip condition only checked for `gcc`; now
  checks for either compiler, so its 11 tests actually run (and pass)
  on MSVC-only machines instead of silently skipping.

## v0.13.0

Closes the three gaps v0.12.0 explicitly called out: sprites, sound,
and collision.

- New `draw_image(win, path, x, y)`: draws a real PNG/GIF sprite image,
  decoded natively by tkinter, no extra install. Images are cached per
  window by path.
- New `rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2)` and
  `circles_overlap(x1, y1, r1, x2, y2, r2)`: axis-aligned box and
  circle collision detection.
- New `beep(freq=440, duration_ms=200)` and `play_sound(path,
  wait=false)`: real sound via the stdlib `winsound` module (Windows
  only; raises a clear error elsewhere rather than doing nothing).
- `examples/game_demo.bo` now uses all three together: a sprite target
  to collect, `rects_overlap()` to detect the hit, `beep()` on
  collision, and a running score - a real small game, not a tech demo
  of unconnected features.
- 103/103 existing tests still pass; all new capabilities smoke-tested
  end-to-end (real window, real sprite file, real collision, real
  beep).

## v0.12.0

First real step toward game development: an actual on-screen window
Bolt code can draw to and read keyboard input from.

- New `window(width, height, title="Bolt")` builtin: opens a real
  window with a drawable canvas, backed by tkinter (ships with Python's
  stdlib, no extra install) - the same "borrow the ecosystem" approach
  as `pyimport()`, applied to graphics.
- New drawing builtins: `clear(win, color)`, `rect(win, x, y, w, h,
  color)`, `circle(win, x, y, r, color)`, `draw_text(win, x, y, msg,
  color)`.
- New `key(win, name)`: whether a key is currently held.
- New `tick(win, fps=60)`: pumps the window's event loop, paces to the
  target frame rate, and returns `false` once the window is closed -
  `while tick(win, 60) { ... }` is the whole game loop.
- New `close_window(win)`.
- `examples/game_demo.bo`: a small playable demo (arrow keys to move a
  square, Escape to quit), verified running end-to-end.
- Deliberately minimal: solid shapes and text only, no sprites, sound,
  or collision helpers yet - a real capability, not a game engine.

## v0.11.0

A Python interop bridge - the shortcut approach to the ecosystem gap
instead of writing every library by hand: borrow Python's ecosystem the
way Deno stayed npm-compatible instead of rebuilding one.

- New `pyimport(name)` builtin: loads a real Python standard-library
  module and returns a Bolt map of its public functions and constants,
  callable directly from Bolt code (`let m = pyimport("statistics");
  m.mean([1, 2, 3])`). Works on both engines identically.
- Restricted to a curated allowlist of safe, side-effect-free stdlib
  modules (`math`, `random`, `statistics`, `json`, `re`, `itertools`,
  `datetime`, `string`, `collections`, `functools`, `fractions`,
  `decimal`, `textwrap`, `unicodedata`, `calendar`, `bisect`, `heapq`) -
  this is a bridge to safe library code, not a general FFI; modules like
  `os` or `subprocess` are rejected with a clear error rather than giving
  Bolt scripts shell/filesystem access.
- Python exceptions raised by the called function surface as normal
  `BoltRuntimeError`s instead of crashing the interpreter.
- Not available under `--target js` (transpiled output has no Python
  runtime to call into), same as `import()`.

9 new tests (114 total): real stdlib calls verified against actual
computed values, constants, caching, both engines, the allowlist
rejecting `os`/`subprocess`/`sys`, Python-exception wrapping, and the JS
rejection path.

## v0.10.0

A real module system - the start of an actual answer to Bolt's lowest
category, ecosystem/libraries, rather than just more built-ins:

- New `import(path)` builtin: loads another `.bo` file as an isolated
  module and returns a map of everything it defines at its own top
  level (`let math = import("packages/mathutils.bo"); math.square(5)`).
  Runs the module in its own VM so internal recursion and cross-function
  calls resolve correctly regardless of which engine or VM instance
  calls into it afterward (`_wrap_module_closure` in builtins.py).
  Cached by path; resolved relative to the current directory, then
  `packages/`, then the same two locations relative to Bolt's own
  install directory (so it still works when invoked from elsewhere).
- New `packages/` local registry with three real modules: `mathutils.bo`
  (square, factorial, is_prime, gcd, ...), `stringutils.bo` (title_case,
  is_palindrome, pad_left, ...), `stats.bo` (mean, median, variance,
  stddev - built on the standard library, not reimplementing it).
- Not available under `--target js` (JS reserves the `import` keyword
  for its own dynamic import syntax; attempting it fails with a clear
  compile-time error instead of generating broken JS).
- Explicitly *not* a package manager: no registry to publish to, no
  version resolution, no install step. A foothold for code reuse, not
  an ecosystem.

10 new tests (105 total): module functions callable from outside,
intra-module recursion and multi-level cross-calls, both engines,
caching, cross-working-directory resolution, missing-module errors,
and the JS rejection path.

## v0.9.0

Closed two more gaps identified by Bolt's own weak categories (native
compilation's narrow scope, and the JS transpiler's documented tensor
gap):

- **Native compiler**: `sqrt`, `abs`, `floor`, `ceil`, `pow`, `min`, `max`
  (with exactly two arguments) are now callable from native-eligible
  functions, mapped directly to their `<math.h>` C equivalents. Widens
  what real code qualifies for AOT compilation.
- **JS transpiler**: full tensor support (`tensor`, `zeros`, `dot`,
  `matmul`, `transpose`, `identity`, `tmap`, and elementwise `+ - * /`)
  plus the entire v0.8.0 standard library, all backed by matching runtime
  prelude functions. This was an explicit, named gap in the README before
  now; it's closed, with one honest caveat documented (JS has no
  int/float distinction, so a numerically-whole float like `dot()`'s
  result prints without a decimal point - same quirk native compilation
  already has via C doubles).

11 new tests (95 total, all passing): native math builtins verified with
real ctypes calls, JS tensor/stdlib output verified by actually running
the generated JS in Node and checking against known-correct values,
including fractional inputs to prove the underlying math is exact.

## v0.8.0

Grew the standard library, aimed directly at Bolt's two lowest-rated
categories (ecosystem/libraries, numeric computing) in its own comparison
page - not everything a real package ecosystem gives you, but real,
tested ground closed:

- Math: `sqrt`, `abs`, `min`, `max`, `floor`, `ceil`, `round`, `pow`.
- Strings: `trim`, `replace`, `repeat`, `starts_with`, `ends_with`.
- Lists/general: `contains`, `index_of`, `sort`, `reverse`, `slice`,
  `concat`.
- Tensors: `transpose`, `identity`, and `tmap` (apply a Bolt function
  elementwise over a tensor - the first builtin besides `serve()` to use
  the `call_fn` callback mechanism).

## v0.7.0

- Built-in web server: `serve(port, handler, max_requests)` starts a real
  `HTTPServer` and calls a Bolt function per request, so pages are computed
  live by Bolt code. Verified with real HTTP requests, both engines.
- `make_builtins()` gained a general `call_fn` callback mechanism so any
  builtin can invoke Bolt closures/functions, not just `serve()`.

## v0.6.0

- Renamed the language from Nexus to Bolt: package, error classes
  (`BoltError`/`BoltSyntaxError`/`BoltRuntimeError`/`BoltTypeError`), and the
  script file extension (`.nx` → `.bo`). Purely a rename, no behavior change.

## v0.5.1

- Native compiler: added support for `for x in range(...)` loops (1-3
  args), on top of the existing if/while/return/recursion subset.
- VM: inlined the closure-call arity check into the `CALL` opcode (one
  fewer Python function-call layer per call) and switched global lookups
  to a single dict hash instead of two.

## v0.5.0

- VM: locals a closure never captures skip Cell-boxing entirely (a
  conservative compile-time capture analysis decides which), and the hot
  arithmetic/comparison opcodes check for plain numbers before falling
  back to the general path. First round of dedicated VM speed work.

## v0.4.0

Completed the original 5-phase roadmap in one pass:

- **Numeric/tensor support** — a dense `Tensor` type (1-D/2-D, elementwise
  `+ - * /`, `dot`, `matmul`), integrated into both engines' arithmetic.
- **Native/compiled backend** (`--native`) — AOT-compiles eligible
  number-only functions to C, builds with `gcc`, loads back via `ctypes`,
  and transparently substitutes for the interpreted version.
- **Web target** (`--target js`) — transpiles the AST directly to
  standalone JavaScript, verified by running the output in Node.

## v0.3.0

- Gradual static typing: optional `: Type` annotations on `let`,
  parameters, and return types, checked by a static pass
  (`typechecker.py`) that runs before execution. Unannotated code stays
  fully dynamic (`any`) and is never flagged.

## v0.2.0

- Bytecode compiler + stack-based VM (`compiler.py`/`vm.py`/`bytecode.py`):
  compile-time local/global/upvalue resolution, jump-patched control flow,
  Lua/clox-style closure capture via `Cell` objects. Set as the default
  engine; the original tree-walker (v0.1.0) kept as a reference
  implementation via `--engine tree`.

## v0.1.0

- First working version: lexer → recursive-descent parser → AST →
  tree-walking interpreter. Variables, functions, closures, recursion,
  control flow, lists, maps, and a small set of built-ins.
