# Nexus

Nexus is a small, general-purpose scripting language with clean, readable
syntax, implemented in Python. It now has two execution engines sharing the
same lexer/parser/AST front end:

- **Bytecode VM** (default) — compiles the AST to bytecode (constant pool,
  resolved local/global/upvalue slots, jump-patched control flow) and runs
  it on a stack machine. ~1.7x faster than the tree-walker.
- **Tree-walking interpreter** — the original v1 engine, walks the AST
  directly. Kept as a reference implementation and for comparing engine
  behavior; both engines are tested against the same test cases.

## Quick start

```bash
python cli.py examples/fibonacci.nx                 # bytecode VM (default)
python cli.py --engine tree examples/fibonacci.nx    # tree-walking interpreter
```

No dependencies are required to run scripts. Running the test suite needs
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
  builtins.py      built-in functions, shared by both engines
  errors.py        NexusSyntaxError / NexusRuntimeError, with line numbers
cli.py             entry point: `python cli.py script.nx [--engine vm|tree]`
examples/          example .nx scripts, incl. bench.nx / bench.py for benchmarking
tests/             pytest suite covering the lexer, parser, interpreter, and VM
```

## Roadmap

This v1 intentionally favors a simple, correct, easy-to-extend implementation
over raw performance. Future phases, roughly in order:

1. ~~**Bytecode VM**~~ — done. Compiles the AST to bytecode and runs it on a
   stack machine; ~1.7x faster than tree-walking on the benchmark suite.
   Next optimization step would be a proper opcode dispatch table and
   avoiding per-instruction Python-object overhead, before reaching for (2).
2. **Optional static typing** — gradual type annotations and a type
   checker, without giving up dynamic-language ergonomics.
3. **Numeric/tensor support** — native array/tensor types and vectorized
   math ops, aimed at making Nexus viable for numerical and ML workloads.
4. **Native/compiled backend** — compile to native code (e.g. via LLVM) for
   performance-critical code paths, similar to what C++ offers today.
5. **Web target** — compile or transpile Nexus to run in the browser.

Each phase builds on the same language semantics established here, so
scripts written today should keep working as the implementation evolves.
