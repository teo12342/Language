# Nexus

Nexus is a small, general-purpose scripting language implemented in Python,
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
  top-level functions to C, builds them with `gcc`, and transparently
  swaps them in for their interpreted counterparts — recursive self-calls
  included. Everything else in the script keeps running on the VM/interpreter.
- **JavaScript transpiler** (`--target js`) — compiles the AST directly to a
  standalone `.js` file that runs in Node or a browser with no dependencies.

## Quick start

```bash
python cli.py examples/fibonacci.nx                 # bytecode VM (default)
python cli.py --engine tree examples/fibonacci.nx    # tree-walking interpreter
python cli.py --native examples/bench_native.nx      # AOT-compile eligible functions
python cli.py --target js examples/fibonacci.nx      # write fibonacci.js, then: node fibonacci.js
```

No dependencies are required to run scripts (the native backend needs
`gcc` on PATH; the JS output needs `node` or a browser to run it, not to
generate it). Running the test suite needs `pytest` (`pip install pytest`).

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
`dot`, `matmul`, `zeros`, `tshape`, `tolist`, `tsum`:

```
let a: tensor = tensor([1, 2, 3])
let b: tensor = tensor([4, 5, 6])
print(tolist(a + b))     # [5.0, 7.0, 9.0]
print(dot(a, b))          # 32.0

let m = tensor([[1, 2], [3, 4]])
let n = tensor([[5, 6], [7, 8]])
print(tolist(matmul(m, n)))   # [[19.0, 22.0], [43.0, 50.0]]
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
| `tensor(nested)` / `zeros(...)` | Build a tensor |
| `dot(a, b)` / `matmul(a, b)` | Tensor dot product / matrix multiply |
| `tshape(t)` / `tolist(t)` / `tsum(t)` | Tensor shape, back to a list, sum of elements |

### Native compilation (`--native`)

Any top-level `func` whose parameters *and* return type are all annotated
`number` — and whose body only uses arithmetic, comparisons, `if`/`while`,
`for x in range(...)`, `return`, and calls to other such functions
(including itself, for recursion) — is eligible. Eligible functions get
compiled to C, built with `gcc -O2`, and loaded back via `ctypes`; the
compiled version replaces the interpreted one under the same name, so
every call site (recursive calls included) transparently runs at native
speed. Anything not eligible (strings, lists, maps, tensors, closures,
untyped params, break/continue, a `for` over anything but `range(...)`)
is reported and simply keeps running on the VM/interpreter — a script can
freely mix both.

```bash
python cli.py --native examples/bench_native.nx
# [native] compiled: fib
# [native] skipped 'make_list': ...
```

### Web target (`--target js`)

`python cli.py --target js script.nx` writes `script.js` next to it — a
self-contained file (small runtime prelude + your program) that runs in
Node or any browser, no build step or dependency. JavaScript already has
closures, dynamic typing, and GC'd arrays/objects, so the transpiler is a
fairly direct structural translation (unlike the bytecode VM, which had to
build all of that itself). Known gaps: JS numbers are float64, so scripts
that rely on Python/Nexus's arbitrary-precision integers (e.g. a
multiply-heavy PRNG) can diverge numerically; `==`/`!=` on lists/maps is
reference equality in JS, not the VM's structural equality; and the
`tensor` builtins aren't available in the generated JS runtime yet.

## Project structure

```
src/nexus/
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
  errors.py        NexusSyntaxError / NexusRuntimeError / NexusTypeError / NativeCompileError
cli.py             entry point: run, --engine vm|tree, --native, --target run|js, --no-typecheck
examples/          example .nx scripts (bench.nx/.py for benchmarking, typed.nx,
                    tensor.nx, bench_native.nx for --native)
tests/             pytest suite: lexer, parser, interpreter, VM, typechecker,
                    tensor, native (skipped if no gcc), JS transpiler (skipped if no node)
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

What's next is refining what's here rather than adding new backends:
tensor element types and list/map generics for the type checker, widening
what the native compiler accepts (loops over ranges, more operators),
and closing the small JS semantic gaps noted above.
