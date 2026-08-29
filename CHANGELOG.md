# Changelog

All notable changes to Bolt, by version.

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
