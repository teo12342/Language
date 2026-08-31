// Static, local knowledge base about the Bolt programming language, used by
// the built-in assistant for keyword-retrieved context (see extension.js's
// searchKB()). This is a real, hand-authored reference, not a live model
// fine-tune or a vector DB - each chunk is matched against the user's
// question by simple keyword overlap and the top few are prepended to the
// assistant's system prompt.

module.exports = [
  {
    title: "Overview",
    keywords: ["bolt", "language", "overview", "what is bolt", "engines", "backends"],
    text: "Bolt is a small, general-purpose scripting language implemented in Python, with Python-like syntax (braces instead of indentation). It runs five ways from one codebase: a tree-walking interpreter (--engine tree), a bytecode VM (default), a native AOT compiler for number-only functions (--native), a JavaScript transpiler (--target js), and a built-in HTTP server (serve()). Run a script: `python cli.py script.bo`.",
  },
  {
    title: "Variables and data types",
    keywords: ["variable", "let", "type", "number", "string", "boolean", "nil", "list", "map"],
    text: "`let name = value` declares a variable; reassign with `name = value`. Types: number (always float internally, prints without trailing .0 when whole), string, boolean (true/false), nil, list ([1,2,3]), map ({\"a\":1}), tensor. `type(x)` returns the type name as a string. `num(x)`/`str(x)` convert.",
  },
  {
    title: "Functions and closures",
    keywords: ["function", "func", "closure", "return", "anonymous"],
    text: "Define with `func name(params) { ... }`. Anonymous functions are expressions: `let f = func(x) { return x * x }`. Closures correctly capture their enclosing scope - each call to a function that returns an inner function gets its own independent captured variables, not a shared one.",
  },
  {
    title: "Control flow",
    keywords: ["if", "else", "while", "for", "break", "continue", "loop"],
    text: "`if cond { } else if cond { } else { }`. `while cond { }`. `for x in range(n) { }` or `for x in someList { }`. `break` and `continue` work as in Python/C-family languages.",
  },
  {
    title: "Gradual static typing",
    keywords: ["typing", "type annotation", "typecheck", "static", ": number", "typed"],
    text: "Annotate `let`, function params, and return types with `: Type` (e.g. `func add(a: number, b: number): number`). Unannotated code stays fully dynamic (`any`) forever. The typechecker runs before execution and can be skipped with `--no-typecheck`. Mirrors runtime behavior (e.g. string+number concatenation is allowed since that's what the runtime does).",
  },
  {
    title: "Built-in functions - core/general",
    keywords: ["print", "len", "range", "push", "pop", "keys", "builtin", "stdlib"],
    text: "print(...), len(x), range(n)/range(start,stop)/range(start,stop,step), str(x), num(x), type(x), push(list,x), pop(list), keys(map), contains(container,item), index_of(container,item), sort(list) [mutates in place], reverse(list) [mutates in place], slice(list,start,end), concat(a,b).",
  },
  {
    title: "Built-in functions - strings",
    keywords: ["string function", "upper", "lower", "split", "join", "trim", "replace", "starts_with", "ends_with"],
    text: "upper(s), lower(s), split(s,sep), join(list,sep), trim(s), replace(s,old,new), repeat(s,n), starts_with(s,prefix), ends_with(s,suffix).",
  },
  {
    title: "Built-in functions - math",
    keywords: ["math function", "sqrt", "abs", "min", "max", "floor", "ceil", "round", "pow"],
    text: "sqrt(x), abs(x), min(...)/max(...) [several args or one list], floor(x), ceil(x), round(x,digits=0), pow(base,exp).",
  },
  {
    title: "Tensors / numeric computing",
    keywords: ["tensor", "matmul", "dot", "transpose", "identity", "tmap", "matrix"],
    text: "tensor(nested_list) builds a dense 1-D or 2-D array. `+ - * /` work elementwise (vs another tensor of same shape, or a scalar). dot(a,b), matmul(a,b), transpose(t), identity(n), tmap(t,fn) [applies a Bolt function elementwise], zeros(...), tshape(t), tolist(t), tsum(t). No broadcasting or GPU support.",
  },
  {
    title: "Modules (import)",
    keywords: ["import", "module", "package", "packages/"],
    text: "`import(path)` loads another .bo file as an isolated module, returning a map of everything it defines at its own top level. Resolved relative to cwd, then packages/, then the same two relative to Bolt's install dir. Cached by path. Not available under --target js (import is a JS reserved word). Bundled packages: packages/mathutils.bo, packages/stringutils.bo, packages/stats.bo.",
  },
  {
    title: "Python interop (pyimport)",
    keywords: ["pyimport", "python interop", "python module", "statistics", "allowlist"],
    text: "`pyimport(name)` loads a real Python standard-library module and returns its public functions/constants as a Bolt map, e.g. `let stats = pyimport(\"statistics\"); stats.mean([1,2,3])`. Restricted to a curated allowlist (math, random, statistics, json, re, itertools, datetime, string, collections, functools, fractions, decimal, textwrap, unicodedata, calendar, bisect, heapq). pyimport(\"os\") and similar fail with a clear error - no shell/filesystem access. Not available under --target js.",
  },
  {
    title: "Built-in web server (serve)",
    keywords: ["serve", "webserver", "http server", "web server"],
    text: "`serve(port, handler, max_requests=1)` starts a real HTTPServer. `handler` is a Bolt function taking the request path (string) and returning the HTML/response body string - every response is computed live by Bolt code. max_requests defaults to 1 (demo-safe); pass 0 to run until killed. GET-only, no routing table, no request bodies - a foothold, not a framework.",
  },
  {
    title: "Windows / game development",
    keywords: ["window", "game", "tick", "draw", "sprite", "key", "mouse", "collision", "beep"],
    text: "window(width,height,title) opens a real tkinter-backed window. tick(win,fps=60) pumps events, paces to fps, returns false when closed - `while tick(win,60) { ... }` is the whole game loop. Drawing: clear(win,color), rect(win,x,y,w,h,color), circle(win,x,y,r,color), draw_text(win,x,y,msg,color), draw_image(win,path,x,y), line(win,x1,y1,x2,y2,color,width=1). Input: key(win,name), mouse_x(win), mouse_y(win), mouse_down(win,button=\"left\"). Collision: rects_overlap(...), circles_overlap(...). Sound: beep(freq=440,duration_ms=200), play_sound(path), stop_sound() (Windows only).",
  },
  {
    title: "Native compilation (--native)",
    keywords: ["native", "aot", "compile", "gcc", "msvc", "speed", "performance"],
    text: "Any top-level function whose params and return type are all annotated `number`, whose body only uses arithmetic/comparisons/if/while/`for x in range(...)`/return and calls to sqrt/abs/floor/ceil/pow/min/max or other eligible functions, is eligible for `--native`. Compiles to C, builds with gcc -O2 (or MSVC cl.exe /O2 on Windows without gcc), loads via ctypes, transparently replaces the interpreted version (recursive calls included). fib(30) runs in ~0.005s native vs ~17s on the default VM.",
  },
  {
    title: "JavaScript transpiler (--target js)",
    keywords: ["javascript", "js", "transpile", "target js", "node"],
    text: "`python cli.py script.bo --target js` writes script.js - a standalone file with no dependencies, runs in Node or a browser. Full stdlib and tensor support included via a runtime prelude. Known gaps: JS numbers are float64 (no arbitrary-precision ints), no int/float distinction in output, `==`/`!=` on lists/maps is reference equality not structural. import()/pyimport() unavailable.",
  },
  {
    title: "CLI flags and project layout",
    keywords: ["cli", "flags", "cli.py", "project structure", "src/bolt"],
    text: "cli.py flags: --engine vm|tree, --native, --target run|js, --no-typecheck. Source lives in src/bolt/ (lexer.py, parser.py, ast_nodes.py, interpreter.py, bytecode.py, compiler.py, vm.py, typechecker.py, tensor.py, native.py, jsgen.py, builtins.py, errors.py). examples/ has runnable demo scripts. tests/ is the pytest suite.",
  },
  {
    title: "Known limitations (honest scope)",
    keywords: ["limitation", "missing", "not supported", "try catch", "error handling"],
    text: "No try/catch - a runtime error is fatal with a clear message and line number. No language server (no autocomplete/go-to-definition in the editor). No public package registry. Default VM is slow outside the native-compiled path (~100x slower than Python for pure interpretation). Tensors have no broadcasting/GPU. Game toolkit has no sprite animation, audio mixing, physics, or scene graph.",
  },
];
