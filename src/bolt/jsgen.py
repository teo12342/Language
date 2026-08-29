"""Transpiles a Bolt AST directly to JavaScript.

Reuses the same AST the interpreter/VM consume - no separate IR. JS gets
this "for free" compared to the bytecode VM because it already has native
closures, dynamic typing, and garbage-collected lists/maps, so codegen is
a fairly direct structural translation. Type annotations are parsed but
ignored here (JS doesn't need them - the checker already validated them
before this ever runs).
"""

import json

from .ast_nodes import GetAttr, Index, Literal, Variable
from .errors import BoltError


class JSGenError(BoltError):
    pass

_BUILTIN_MAP = {
    "print": "nxPrint", "len": "nxLen", "range": "nxRange", "str": "nxStringify",
    "num": "nxNum", "type": "nxType", "push": "nxPush", "pop": "nxPop",
    "keys": "nxKeys", "upper": "nxUpper", "lower": "nxLower", "split": "nxSplit",
    "join": "nxJoin",
    "sqrt": "nxSqrt", "abs": "Math.abs", "min": "nxMin", "max": "nxMax",
    "floor": "Math.floor", "ceil": "Math.ceil", "round": "nxRound", "pow": "Math.pow",
    "trim": "nxTrim", "replace": "nxReplace", "repeat": "nxRepeat",
    "starts_with": "nxStartsWith", "ends_with": "nxEndsWith",
    "contains": "nxContains", "index_of": "nxIndexOf", "sort": "nxSort",
    "reverse": "nxReverse", "slice": "nxSlice", "concat": "nxConcat",
    "tensor": "nxTensorFromNested", "zeros": "nxZeros", "dot": "nxDot",
    "matmul": "nxMatmul", "tshape": "nxTshape", "tolist": "nxTensorToNested",
    "tsum": "nxTsum", "transpose": "nxTranspose", "identity": "nxIdentity",
    "tmap": "nxTmap",
}

_COMPARE_OPS = {"<", "<=", ">", ">="}

_PRELUDE = """\
// Tensors are plain objects {__isTensor:true, shape:[...], data:[...]} -
// flat row-major storage, same layout as tensor.py's Python Tensor class.
function nxIsTensor(v) { return typeof v === "object" && v !== null && v.__isTensor === true; }
function nxTensorFromNested(nested) {
  if (nested.length > 0 && Array.isArray(nested[0])) {
    const rows = nested.length, cols = nested[0].length;
    const data = [];
    for (const row of nested) for (const x of row) data.push(x);
    return { __isTensor: true, shape: [rows, cols], data };
  }
  return { __isTensor: true, shape: [nested.length], data: nested.slice() };
}
function nxTensorToNested(t) {
  if (t.shape.length === 1) return t.data.slice();
  const [rows, cols] = t.shape;
  const out = [];
  for (let r = 0; r < rows; r++) out.push(t.data.slice(r * cols, (r + 1) * cols));
  return out;
}
function nxTensorElementwise(a, b, op) {
  if (nxIsTensor(a) && nxIsTensor(b)) {
    return { __isTensor: true, shape: a.shape, data: a.data.map((x, i) => op(x, b.data[i])) };
  }
  if (nxIsTensor(a)) return { __isTensor: true, shape: a.shape, data: a.data.map(x => op(x, b)) };
  return { __isTensor: true, shape: b.shape, data: b.data.map(x => op(a, x)) };
}
function nxZeros(...dims) {
  const n = dims.length === 1 ? dims[0] : dims[0] * dims[1];
  return { __isTensor: true, shape: dims.length === 1 ? [dims[0]] : [dims[0], dims[1]], data: new Array(n).fill(0) };
}
function nxDot(a, b) { let s = 0; for (let i = 0; i < a.data.length; i++) s += a.data[i] * b.data[i]; return s; }
function nxMatmul(a, b) {
  const [m, k] = a.shape, n = b.shape[1];
  const data = new Array(m * n).fill(0);
  for (let i = 0; i < m; i++) for (let j = 0; j < n; j++) {
    let s = 0;
    for (let t = 0; t < k; t++) s += a.data[i * k + t] * b.data[t * n + j];
    data[i * n + j] = s;
  }
  return { __isTensor: true, shape: [m, n], data };
}
function nxTranspose(t) {
  const [rows, cols] = t.shape;
  const data = new Array(rows * cols);
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) data[c * rows + r] = t.data[r * cols + c];
  return { __isTensor: true, shape: [cols, rows], data };
}
function nxIdentity(n) {
  const data = new Array(n * n).fill(0);
  for (let i = 0; i < n; i++) data[i * n + i] = 1;
  return { __isTensor: true, shape: [n, n], data };
}
function nxTshape(t) { return t.shape.slice(); }
function nxTsum(t) { return t.data.reduce((a, b) => a + b, 0); }
function nxTmap(t, fn) { return { __isTensor: true, shape: t.shape, data: t.data.map(x => fn(x)) }; }

// Nested list/map printing mirrors Python's own repr() (which is what the
// reference engines fall back on for container elements), so e.g. nested
// booleans print as True/False and nested strings are quoted - matching
// the tree-walker/VM's actual output, quirks included.
function nxRepr(v) {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (nxIsTensor(v)) return "tensor" + nxRepr(nxTensorToNested(v));
  if (typeof v === "string") return "'" + v.replace(/\\\\/g, "\\\\\\\\").replace(/'/g, "\\\\'") + "'";
  if (Array.isArray(v)) return "[" + v.map(nxRepr).join(", ") + "]";
  if (typeof v === "object") return "{" + Object.entries(v).map(([k, val]) => `'${k}': ${nxRepr(val)}`).join(", ") + "}";
  return String(v);
}
function nxStringify(v) {
  if (v === null || v === undefined) return "nil";
  if (v === true) return "true";
  if (v === false) return "false";
  if (nxIsTensor(v)) return "tensor" + nxRepr(nxTensorToNested(v));
  if (Array.isArray(v)) return "[" + v.map(nxRepr).join(", ") + "]";
  if (typeof v === "object") return "{" + Object.entries(v).map(([k, val]) => `'${k}': ${nxRepr(val)}`).join(", ") + "}";
  return String(v);
}
function nxAdd(a, b) {
  if (nxIsTensor(a) || nxIsTensor(b)) return nxTensorElementwise(a, b, (x, y) => x + y);
  if (typeof a === "string" || typeof b === "string") return nxStringify(a) + nxStringify(b);
  if (Array.isArray(a) && Array.isArray(b)) return a.concat(b);
  return a + b;
}
function nxSub(a, b) {
  if (nxIsTensor(a) || nxIsTensor(b)) return nxTensorElementwise(a, b, (x, y) => x - y);
  return a - b;
}
function nxMul(a, b) {
  if (nxIsTensor(a) || nxIsTensor(b)) return nxTensorElementwise(a, b, (x, y) => x * y);
  return a * b;
}
function nxDiv(a, b) {
  if (nxIsTensor(a) || nxIsTensor(b)) return nxTensorElementwise(a, b, (x, y) => x / y);
  return a / b;
}
function nxSqrt(x) { if (x < 0) throw new Error("sqrt() of a negative number"); return Math.sqrt(x); }
function nxMin(...args) { const v = args.length === 1 && Array.isArray(args[0]) ? args[0] : args; return Math.min(...v); }
function nxMax(...args) { const v = args.length === 1 && Array.isArray(args[0]) ? args[0] : args; return Math.max(...v); }
function nxRound(x, digits) {
  if (!digits) return Math.round(x);
  const f = Math.pow(10, digits);
  return Math.round(x * f) / f;
}
function nxTrim(s) { return s.trim(); }
function nxReplace(s, oldS, newS) { return s.split(oldS).join(newS); }
function nxRepeat(s, n) { return s.repeat(n); }
function nxStartsWith(s, prefix) { return s.startsWith(prefix); }
function nxEndsWith(s, suffix) { return s.endsWith(suffix); }
function nxContains(container, item) {
  if (typeof container === "string") return container.includes(item);
  return container.includes(item);
}
function nxIndexOf(container, item) { return container.indexOf(item); }
function nxSort(lst) { lst.sort((a, b) => (a > b ? 1 : a < b ? -1 : 0)); return lst; }
function nxReverse(lst) { lst.reverse(); return lst; }
function nxSlice(lst, start, end) { return end === undefined ? lst.slice(start) : lst.slice(start, end); }
function nxConcat(a, b) { return Array.isArray(a) ? a.concat(b) : a + b; }
function nxPrint(...args) { console.log(args.map(nxStringify).join(" ")); }
function nxLen(x) { return x.length !== undefined ? x.length : Object.keys(x).length; }
function nxRange(a, b, c) {
  let start = 0, stop, step = 1;
  if (b === undefined) { stop = a; } else { start = a; stop = b; if (c !== undefined) step = c; }
  const out = [];
  if (step > 0) { for (let i = start; i < stop; i += step) out.push(i); }
  else { for (let i = start; i > stop; i += step) out.push(i); }
  return out;
}
function nxNum(x) { return typeof x === "string" && x.includes(".") ? parseFloat(x) : parseInt(x); }
function nxType(x) {
  if (x === null || x === undefined) return "nil";
  if (typeof x === "boolean") return "bool";
  if (typeof x === "number") return "number";
  if (typeof x === "string") return "string";
  if (Array.isArray(x)) return "list";
  if (typeof x === "object") return "map";
  return "func";
}
function nxPush(lst, v) { lst.push(v); return lst; }
function nxPop(lst) { return lst.pop(); }
function nxKeys(m) { return Object.keys(m); }
function nxUpper(s) { return s.toUpperCase(); }
function nxLower(s) { return s.toLowerCase(); }
function nxSplit(s, sep) { return s.split(sep); }
function nxJoin(lst, sep) { return lst.map(nxStringify).join(sep); }
"""


class JSGen:
    def __init__(self):
        self.lines: list[str] = []
        self.indent = 0

    def _emit(self, text: str):
        self.lines.append(("  " * self.indent) + text)

    def generate(self, statements) -> str:
        for s in statements:
            self._stmt(s)
        return _PRELUDE + "\n" + "\n".join(self.lines) + "\n"

    # ---- statements ----

    def _stmt(self, stmt):
        getattr(self, f"_stmt_{type(stmt).__name__}")(stmt)

    def _stmt_ExprStmt(self, stmt):
        self._emit(self._expr(stmt.expr) + ";")

    def _stmt_LetStmt(self, stmt):
        value = self._expr(stmt.initializer) if stmt.initializer is not None else "null"
        self._emit(f"let {stmt.name} = {value};")

    def _stmt_FuncStmt(self, stmt):
        self._emit_function(stmt.name, stmt.params, stmt.body)

    def _stmt_ReturnStmt(self, stmt):
        self._emit(f"return {self._expr(stmt.value)};" if stmt.value is not None else "return null;")

    def _stmt_IfStmt(self, stmt):
        self._emit(f"if ({self._expr(stmt.condition)}) {{")
        self.indent += 1
        for s in stmt.then_branch:
            self._stmt(s)
        self.indent -= 1
        if stmt.else_branch is not None:
            self._emit("} else {")
            self.indent += 1
            for s in stmt.else_branch:
                self._stmt(s)
            self.indent -= 1
        self._emit("}")

    def _stmt_WhileStmt(self, stmt):
        self._emit(f"while ({self._expr(stmt.condition)}) {{")
        self.indent += 1
        for s in stmt.body:
            self._stmt(s)
        self.indent -= 1
        self._emit("}")

    def _stmt_ForStmt(self, stmt):
        self._emit(f"for (const {stmt.var_name} of {self._expr(stmt.iterable)}) {{")
        self.indent += 1
        for s in stmt.body:
            self._stmt(s)
        self.indent -= 1
        self._emit("}")

    def _stmt_BreakStmt(self, stmt):
        self._emit("break;")

    def _stmt_ContinueStmt(self, stmt):
        self._emit("continue;")

    def _stmt_Block(self, stmt):
        self._emit("{")
        self.indent += 1
        for s in stmt.statements:
            self._stmt(s)
        self.indent -= 1
        self._emit("}")

    def _emit_function(self, name, params, body):
        self._emit(f"function {name}({', '.join(params)}) {{")
        self.indent += 1
        for s in body:
            self._stmt(s)
        self._emit("return null;")
        self.indent -= 1
        self._emit("}")

    # ---- expressions ----

    def _expr(self, expr) -> str:
        return getattr(self, f"_expr_{type(expr).__name__}")(expr)

    def _expr_Literal(self, expr: Literal):
        v = expr.value
        if v is None:
            return "null"
        if v is True:
            return "true"
        if v is False:
            return "false"
        if isinstance(v, str):
            return json.dumps(v)
        return repr(v)

    def _expr_ListLiteral(self, expr):
        return "[" + ", ".join(self._expr(e) for e in expr.elements) + "]"

    def _expr_MapLiteral(self, expr):
        pairs = ", ".join(f"[{self._expr(k)}]: {self._expr(v)}" for k, v in zip(expr.keys, expr.values))
        return "{" + pairs + "}"

    def _expr_Variable(self, expr: Variable):
        return expr.name

    def _expr_Assign(self, expr):
        target = expr.target
        if isinstance(target, Variable):
            return f"({target.name} = {self._expr(expr.value)})"
        if isinstance(target, Index):
            return f"({self._expr(target.obj)}[{self._expr(target.index)}] = {self._expr(expr.value)})"
        if isinstance(target, GetAttr):
            return f"({self._expr(target.obj)}.{target.name} = {self._expr(expr.value)})"
        raise ValueError("unsupported assignment target")

    def _expr_Unary(self, expr):
        right = self._expr(expr.right)
        return f"(-{right})" if expr.op == "-" else f"(!{right})"

    def _expr_Logical(self, expr):
        op = "&&" if expr.op == "and" else "||"
        return f"({self._expr(expr.left)} {op} {self._expr(expr.right)})"

    def _expr_Binary(self, expr):
        left = self._expr(expr.left)
        right = self._expr(expr.right)
        op = expr.op
        if op == "+":
            return f"nxAdd({left}, {right})"
        if op == "-":
            return f"nxSub({left}, {right})"
        if op == "*":
            return f"nxMul({left}, {right})"
        if op == "/":
            return f"nxDiv({left}, {right})"
        if op == "%":
            return f"({left} % {right})"
        if op in _COMPARE_OPS:
            return f"({left} {op} {right})"
        if op == "==":
            return f"({left} === {right})"
        if op == "!=":
            return f"({left} !== {right})"
        raise ValueError(f"unsupported operator {op}")

    def _expr_Call(self, expr):
        if isinstance(expr.callee, Variable) and expr.callee.name == "import":
            # "import" is a real reserved word in JS (dynamic import()), so
            # silently emitting a call to it would produce syntactically
            # valid but semantically wrong JS instead of a clear error.
            raise JSGenError("import() is not supported by --target js (VM/tree-walker only)", expr.line)
        if isinstance(expr.callee, Variable) and expr.callee.name == "pyimport":
            # pyimport() loads real Python code - meaningless once transpiled
            # to standalone JS, which has no Python runtime to call into.
            raise JSGenError("pyimport() is not supported by --target js (VM/tree-walker only)", expr.line)
        if isinstance(expr.callee, Variable) and expr.callee.name in _BUILTIN_MAP:
            callee = _BUILTIN_MAP[expr.callee.name]
        else:
            callee = self._expr(expr.callee)
        args = ", ".join(self._expr(a) for a in expr.args)
        return f"{callee}({args})"

    def _expr_Index(self, expr):
        return f"{self._expr(expr.obj)}[{self._expr(expr.index)}]"

    def _expr_GetAttr(self, expr):
        return f"{self._expr(expr.obj)}.{expr.name}"

    def _expr_FuncExpr(self, expr):
        inner = JSGen()
        for s in expr.body:
            inner._stmt(s)
        inner._emit("return null;")
        body = "\n".join("  " + line for line in inner.lines)
        return f"(function({', '.join(expr.params)}) {{\n{body}\n}})"


def generate_js(statements) -> str:
    return JSGen().generate(statements)
