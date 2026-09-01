# Bolt

Bolt is a small, general-purpose scripting language implemented in Python,
with clean, readable syntax. All five phases of the original roadmap are now
in place: a bytecode VM, gradual static typing, tensors, an AOT native
backend for hot numeric code, and a JavaScript transpiler for the web.

## Execution paths

- **Bytecode VM** (default) — compiles the AST to bytecode (constant pool,
  resolved local/global/upvalue slots, jump-patched control flow) and runs
  it on a stack machine.
- **Tree-walking interpreter** — the original v1 engine, walks the AST
  directly. Kept as a reference implementation; both engines are tested
  against the same test cases and always agree.
- **Native backend** (`--native`) — AOT-compiles eligible number-only
  top-level functions to C, builds them with `gcc` (or MSVC's `cl.exe` on
  Windows machines that only have Visual Studio Build Tools installed —
  no MinGW/gcc required there), and transparently swaps them in for their
  interpreted counterparts — recursive self-calls included. Everything
  else in the script keeps running on the VM/interpreter.
- **JavaScript transpiler** (`--target js`) — compiles the AST directly to a
  standalone `.js` file that runs in Node or a browser with no dependencies.
- **Built-in web server** (`serve`) — a Bolt script can now serve real,
  dynamic HTTP responses directly, no external framework required.

## Quick start

```bash
python cli.py examples/fibonacci.bo                 # bytecode VM (default)
python cli.py --engine tree examples/fibonacci.bo    # tree-walking interpreter
python cli.py --native examples/bench_native.bo      # AOT-compile eligible functions
python cli.py --target js examples/fibonacci.bo      # write fibonacci.js, then: node fibonacci.js
python cli.py examples/webserver.bo                  # start a real HTTP server (see below)
```

No dependencies are required to run scripts (the native backend needs
`gcc` on PATH, or on Windows falls back to MSVC's `cl.exe` if Visual
Studio Build Tools are installed; the JS output needs `node` or a
browser to run it, not to generate it). Running the test suite needs
`pytest` (`pip install pytest`).

```bash
python -m pytest tests/
```

## Language tour

### Variables

```
let name = "Ada"
let age = 36
age = age + 1
```

### Functions and closures

```
func add(a, b) {
    return a + b
}

func make_counter() {
    let count = 0
    func increment() {
        count = count + 1
        return count
    }
    return increment
}

let counter = make_counter()
print(counter())   # 1
print(counter())   # 2
```

Anonymous functions work as expressions too:

```
let square = func(x) { return x * x }
print(square(5))   # 25
```

### Control flow

```
if score > 90 {
    print("A")
} else if score > 80 {
    print("B")
} else {
    print("C")
}

let i = 0
while i < 5 {
    print(i)
    i = i + 1
}

for n in range(5) {
    if n == 3 { break }
    print(n)
}
```

### Gradual static typing

Annotate `let` bindings, function parameters, and return types where you
want them checked; anything unannotated stays fully dynamic (`any`), so
existing untyped scripts are unaffected. The checker runs before your
script executes (`--no-typecheck` skips it) and mirrors real runtime
behavior — e.g. `+` between a string and a number is allowed, since that's
what the runtime actually does.

```
func add(a: number, b: number): number {
    return a + b
}

let total: number = add(2, 3)   # ok
let total: number = "oops"       # Type error: Cannot assign string to 'total' declared as number

let anything = 1   # unannotated: still fully dynamic
anything = "now a string"
anything = [1, 2, 3]
```

Checked: `let`/reassignment against a declared type, function argument
count and types against declared parameter types, `return` values against
a declared return type, and arithmetic/comparison operators against
`number`. Not yet checked: element types inside `list`/`map` (no generics
yet), and `dict`/index access always types as `any`.

### Numeric / tensor support

`tensor(nested_list)` builds a dense 1-D or 2-D array; `+ - * /` work
elementwise (against another tensor of the same shape, or a scalar), plus
`dot`, `matmul`, `transpose`, `identity`, `tmap`, `zeros`, `tshape`,
`tolist`, `tsum`:

```
let a: tensor = tensor([1, 2, 3])
let b: tensor = tensor([4, 5, 6])
print(tolist(a + b))     # [5.0, 7.0, 9.0]
print(dot(a, b))          # 32.0

let m = tensor([[1, 2], [3, 4]])
let n = tensor([[5, 6], [7, 8]])
print(tolist(matmul(m, n)))   # [[19.0, 22.0], [43.0, 50.0]]
print(tolist(transpose(m)))    # [[1.0, 3.0], [2.0, 4.0]]
print(tolist(identity(2)))      # [[1.0, 0.0], [0.0, 1.0]]

func square(x) { return x * x }
print(tolist(tmap(a, square)))   # [1.0, 4.0, 9.0] - a Bolt function applied elementwise
```

### Data types

```
let n = 42          # number (int or float)
let s = "hello"      # string
let b = true          # boolean
let x = nil            # nil
let list = [1, 2, 3]    # list
let map = {"a": 1, "b": 2}  # map

print(list[0])
print(map["a"])
print(map.a)          # dot access also works on maps
```

### Built-in functions

| Function | Description |
|---|---|
| `print(...)` | Print values, space-separated |
| `len(x)` | Length of a string, list, or map |
| `range(n)` / `range(start, stop)` / `range(start, stop, step)` | Build a list of numbers |
| `str(x)` | Convert to string |
| `num(x)` | Convert to number |
| `type(x)` | Name of a value's type |
| `push(list, x)` / `pop(list)` | Mutate a list |
| `keys(map)` | List a map's keys |
| `upper(s)` / `lower(s)` | String case conversion |
| `split(s, sep)` / `join(list, sep)` | String/list conversion |
| `sqrt(x)` / `abs(x)` / `min(...)` / `max(...)` | Basic math; `min`/`max` take either several args or one list |
| `floor(x)` / `ceil(x)` / `round(x, digits=0)` / `pow(base, exp)` | More math |
| `trim(s)` / `replace(s, old, new)` / `repeat(s, n)` | String utilities |
| `starts_with(s, prefix)` / `ends_with(s, suffix)` | String prefix/suffix checks |
| `contains(container, item)` / `index_of(container, item)` | Membership/search for a list or string (`index_of` returns `-1` if absent) |
| `sort(list)` / `reverse(list)` | Mutate a list in place (also returned) |
| `slice(list, start, end=None)` / `concat(a, b)` | Sublist, and list/list or string/string concatenation |
| `tensor(nested)` / `zeros(...)` / `identity(n)` | Build a tensor |
| `dot(a, b)` / `matmul(a, b)` / `transpose(t)` | Tensor dot product, matrix multiply, transpose |
| `tshape(t)` / `tolist(t)` / `tsum(t)` | Tensor shape, back to a list, sum of elements |
| `tmap(t, fn)` | Apply a Bolt function elementwise over a tensor |
| `serve(port, handler, max_requests=1)` | Start a real HTTP server; see below |
| `import(path)` | Load another `.bo` file as a module; see below |
| `pyimport(name)` | Load an allowlisted Python standard-library module; see below |
| `window(width, height, title="Bolt")` | Open a real on-screen window; see below |
| `clear(win, color="black")` / `rect(win, x, y, w, h, color)` / `circle(win, x, y, r, color)` / `draw_text(win, x, y, msg, color)` | Draw to a window |
| `draw_image(win, path, x, y)` | Draw a real PNG/GIF sprite image |
| `line(win, x1, y1, x2, y2, color, width=1)` | Draw a line |
| `key(win, name)` | Whether a key is currently held (e.g. `"left"`, `"space"`, `"escape"`) |
| `mouse_x(win)` / `mouse_y(win)` / `mouse_down(win, button="left")` | Real mouse position and button state (`"left"` or `"right"`) |
| `tick(win, fps=60)` | Pump the window and pace to `fps`; `false` once the window is closed - the game-loop condition |
| `close_window(win)` | Close a window |
| `rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2)` / `circles_overlap(x1, y1, r1, x2, y2, r2)` | Axis-aligned box / circle collision detection |
| `beep(freq=440, duration_ms=200)` / `play_sound(path, wait=false)` / `stop_sound()` | Real sound: a system beep, a `.wav` file, or stop playback (Windows via winsound, Linux via SDL2) |

### Built-in web server (`serve`)

```
func page(path) {
    if path == "/" {
        return "<h1>Hello from Bolt</h1>"
    }
    return "<h1>404</h1><p>No page at " + path + "</p>"
}

serve(8080, page, 3)   # answers 3 requests, then stops; pass 0 to run forever
```

`serve` starts a real `HTTPServer` on `port` and calls `handler(path)` once
per incoming GET request — the request path is a normal Bolt string, and
whatever the handler returns becomes the HTTP response body, so every page
can be computed live by Bolt code (different content per path, no static
files needed). `max_requests` bounds how many requests to answer before
returning, which defaults to `1` so a demo/test run doesn't hang forever;
pass `0` to run like a normal, indefinitely-running server. Works
identically on both the VM and the tree-walking interpreter — verified end
to end with real HTTP requests in `tests/test_webserver.py`, not just a
generated response inspected offline.

This is intentionally minimal (no routing table, no request body/headers,
GET only) — a starting point for "Bolt can serve a page" rather than a web
framework. See `examples/webserver.bo`.

### Packages (`import`)

Code can be split across files and reused. `import(path)` loads another
`.bo` file as an isolated module and returns a map of everything it
defines at its own top level:

```
let math = import("packages/mathutils.bo")
print(math.square(5))       # 25
print(math.factorial(5))    # 120
print(math.is_prime(17))    # true
```

`path` is looked up relative to the current directory, then `packages/`
(a small local registry shipped in this repo — `mathutils.bo`,
`stringutils.bo`, `stats.bo`), then the same two locations relative to
Bolt's own install directory, so it still works when Bolt is invoked from
somewhere else entirely. Each module runs in its own isolated VM so its
internal recursion and cross-function calls (e.g. `stats.bo`'s `stddev`
calling `variance` calling `mean`) resolve correctly no matter which
engine or VM instance calls into it from the outside — see
`_wrap_module_closure` in `builtins.py` for why that needs a small
wrapper rather than exposing the raw function. Imports are cached by
path, so importing the same module twice runs it once.

This is a real module system, not a package *manager* — there's no
registry to publish to, no version resolution, no `bolt install`. It's a
foothold for code reuse, not an ecosystem; see the comparison page for
how far that gap still is. Not available when transpiling with
`--target js` (fails with a clear error rather than generating broken
JS, since `import` is itself a reserved word in JavaScript).

### Python interop (`pyimport`)

Bolt's own standard library is tiny compared to Python's ~500,000
packages, and that gap won't close by writing more Bolt code alone.
`pyimport(name)` is a shortcut instead: it loads a real Python
standard-library module and hands back its public functions/constants as
a normal Bolt map, so Bolt code can call straight into Python:

```
let stats = pyimport("statistics")
print(stats.mean([4, 8, 15, 16, 23, 42]))   # 18
print(stats.median([4, 8, 15, 16, 23, 42])) # 15.5

let math = pyimport("math")
print(math.pi)                              # 3.141592653589793
```

Same idea as Deno staying npm-compatible instead of rebuilding a whole
new JS package ecosystem from scratch — borrow an existing ecosystem
rather than reimplement it one function at a time.

Deliberately restricted to a curated allowlist of safe, side-effect-free
stdlib modules (`math`, `random`, `statistics`, `json`, `re`,
`itertools`, `datetime`, `string`, `collections`, `functools`,
`fractions`, `decimal`, `textwrap`, `unicodedata`, `calendar`, `bisect`,
`heapq`) — this is a bridge to safe library code, not a general FFI.
`pyimport("os")` or `pyimport("subprocess")` fail with a clear error
rather than giving Bolt scripts shell or filesystem access. A Python
exception raised by the called function surfaces as a normal
`BoltRuntimeError` instead of crashing the interpreter. Works
identically on both engines; not available under `--target js`
(transpiled output has no Python runtime to call into). See
`examples/pyimport_demo.bo`.

### Windows and game development (`window`)

Bolt's first step toward game dev: `window()` opens a real, on-screen
window with a drawable canvas and live keyboard input, so a Bolt script
can be an actual small game, not a simulation of one.

```
let win = window(480, 320, "My Game")
let x = 220

while tick(win, 60) {
    if key(win, "left") { x = x - 4 }
    if key(win, "right") { x = x + 4 }

    clear(win, "#171410")
    rect(win, x, 140, 40, 40, "#e2895f")
}
```

`window()` is backed by tkinter, which ships with Python's standard
library — no extra install, same "borrow the ecosystem instead of
rebuilding it" approach as `pyimport()`, applied to graphics instead of
math/data. `tick(win, fps)` pumps the window's event loop, paces to the
target frame rate, and returns `false` once the window is closed, so
`while tick(win, 60) { ... }` is the whole game loop. See
`examples/game_demo.bo` for a small playable demo (arrow keys to move a
square, Escape to quit).

Now with sprites, sound, collision, and mouse input too:
`draw_image(win, path, x, y)` draws a real PNG/GIF image (tkinter decodes
it natively, no extra install); `line(win, x1, y1, x2, y2, color)` draws
a line; `rects_overlap(...)` / `circles_overlap(...)` are the
axis-aligned box and circle collision checks every 2D game needs;
`mouse_x(win)` / `mouse_y(win)` / `mouse_down(win, button)` track the
real mouse; `beep(...)`, `play_sound(path)`, and `stop_sound()` play (and
stop) a real system beep or `.wav` file (winsound on Windows, SDL2's
audio queue on Linux). `examples/game_demo.bo` uses all of it together: move
a sprite with the arrow keys or by holding the mouse button, collide
with a target to score a point and hear a beep. Still deliberately
minimal — no animation frames, no physics, no scene graph — a real step
toward game dev, not a game engine.

### Native compilation (`--native`)

Any top-level `func` whose parameters *and* return type are all annotated
`number` — and whose body only uses arithmetic, comparisons, `if`/`while`,
`for x in range(...)`, `return`, calls to `sqrt`/`abs`/`floor`/`ceil`/
`pow`/`min`/`max` (mapped straight to their `<math.h>` equivalents), and
calls to other such functions (including itself, for recursion) — is
eligible. Eligible functions get compiled to C, built with `gcc -O2` (or
MSVC's `cl.exe /O2` on Windows without gcc installed), and loaded back
via `ctypes`; the compiled version replaces the interpreted one under
the same name, so every call site (recursive calls included)
transparently runs at native speed. Anything not eligible (strings,
lists, maps, tensors, closures, untyped params, break/continue, a `for`
over anything but `range(...)`, `min`/`max` with anything but exactly two
arguments) is reported and simply keeps running on the VM/interpreter —
a script can freely mix both.

One known display quirk: C only has doubles, so a natively-compiled
function can't tell "this whole number is conceptually an int" from
"this whole number is conceptually a float" — e.g. `sqrt(25)` prints as
`5` when native-compiled vs. `5.0` on the VM/interpreter. The value is
numerically identical either way; only the printed form differs.

```bash
python cli.py --native examples/bench_native.bo
# [native] compiled: fib
# [native] skipped 'make_list': ...
```

### Web target (`--target js`)

`python cli.py --target js script.bo` writes `script.js` next to it — a
self-contained file (small runtime prelude + your program) that runs in
Node or any browser, no build step or dependency. JavaScript already has
closures, dynamic typing, and GC'd arrays/objects, so the transpiler is a
fairly direct structural translation (unlike the bytecode VM, which had to
build all of that itself). The full standard library (math, string, list
utilities) and the tensor type (`+ - * /`, `dot`, `matmul`, `transpose`,
`identity`, `tmap`) both work in the generated JS too, backed by the same
runtime prelude. Known gaps: JS numbers are float64, so scripts that rely
on Python/Bolt's arbitrary-precision integers (e.g. a multiply-heavy PRNG)
can diverge numerically, and a value that's numerically whole but
conceptually a float (e.g. `dot()` returning `11.0`) prints as `11` in JS
since it has no separate int/float type; `==`/`!=` on lists/maps is
reference equality in JS, not the VM's structural equality.

## Project structure

```
src/bolt/
  lexer.py         tokenizer
  parser.py        recursive-descent parser -> AST
  ast_nodes.py     AST node definitions
  interpreter.py   tree-walking evaluator (environments, closures, control flow)
  bytecode.py      opcodes, Chunk, and FunctionProto for the VM engine
  compiler.py      AST -> bytecode compiler (locals/globals/upvalue resolution,
                    jump patching for control flow)
  vm.py            stack-based bytecode VM (Cell/Closure runtime types)
  typechecker.py   gradual static type checker, runs before execution
  tensor.py        dense 1-D/2-D Tensor type (elementwise ops, dot, matmul)
  native.py        AOT compiler: eligible functions -> C -> gcc -> ctypes
  jsgen.py         AST -> JavaScript transpiler, for the web target
  builtins.py      built-in functions, shared by both interpreting engines
                    (incl. serve(), a real HTTP server; import(), a module
                    loader; and pyimport(), a Python-stdlib interop bridge -
                    the first two via a call_fn callback that lets a builtin
                    call back into Bolt code)
  errors.py        BoltSyntaxError / BoltRuntimeError / BoltTypeError / NativeCompileError
cli.py             entry point: run, --engine vm|tree, --native, --target run|js, --no-typecheck
packages/          the local package registry: mathutils.bo, stringutils.bo, stats.bo
examples/          example .bo scripts (bench.bo/.py for benchmarking, typed.bo,
                    tensor.bo, bench_native.bo for --native, webserver.bo for serve(),
                    packages_demo.bo for import(), pyimport_demo.bo for pyimport())
tests/             pytest suite: lexer, parser, interpreter, VM, typechecker,
                    tensor, native (skipped if no gcc), JS transpiler (skipped if no node),
                    webserver (spawns the CLI and makes real HTTP requests against it),
                    packages (import() correctness, including cross-CWD resolution),
                    pyimport (real stdlib calls, allowlist rejection, both engines)
```

## Roadmap

All five original phases are done. Each was built as a layer on the same
front end (lexer/parser/AST) and the same language semantics, so scripts
written for v1 still run unchanged today:

1. ~~**Bytecode VM**~~ — compiles to bytecode with resolved locals/upvalues
   and jump-patched control flow; faster than the tree-walker, same output.
2. ~~**Optional static typing**~~ — gradual `: Type` annotations checked by
   a static pass; unannotated code is always `any` and never flagged.
3. ~~**Numeric/tensor support**~~ — a dense `Tensor` type with elementwise
   ops, `dot`, and `matmul`, integrated into both engines' arithmetic.
4. ~~**Native/compiled backend**~~ — AOT-compiles eligible number-only
   functions to real machine code via C + gcc, transparently substituted
   in place of the interpreted version (recursive calls included).
5. ~~**Web target**~~ — transpiles to plain JavaScript, verified by actually
   running the output in Node against the same test cases.

Beyond the original five, first step toward Bolt being usable for real web
work: a built-in `serve()` that runs a real HTTP server and answers
requests with Bolt-computed HTML (`examples/webserver.bo`). Deliberately
minimal today (GET-only, no routing table, no request body/headers) — a
foothold, not a framework.

Next: tensor element types and list/map generics for the type checker,
widening what the native compiler accepts, closing the small JS semantic
gaps noted above, and growing `serve()` toward something closer to an
actual micro web framework (routes, POST bodies, static file serving).
