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

_BUILTIN_MAP = {
    "print": "nxPrint", "len": "nxLen", "range": "nxRange", "str": "nxStringify",
    "num": "nxNum", "type": "nxType", "push": "nxPush", "pop": "nxPop",
    "keys": "nxKeys", "upper": "nxUpper", "lower": "nxLower", "split": "nxSplit",
    "join": "nxJoin",
}

_COMPARE_OPS = {"<", "<=", ">", ">="}

_PRELUDE = """\
// Nested list/map printing mirrors Python's own repr() (which is what the
// reference engines fall back on for container elements), so e.g. nested
// booleans print as True/False and nested strings are quoted - matching
// the tree-walker/VM's actual output, quirks included.
function nxRepr(v) {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "string") return "'" + v.replace(/\\\\/g, "\\\\\\\\").replace(/'/g, "\\\\'") + "'";
  if (Array.isArray(v)) return "[" + v.map(nxRepr).join(", ") + "]";
  if (typeof v === "object") return "{" + Object.entries(v).map(([k, val]) => `'${k}': ${nxRepr(val)}`).join(", ") + "}";
  return String(v);
}
function nxStringify(v) {
  if (v === null || v === undefined) return "nil";
  if (v === true) return "true";
  if (v === false) return "false";
  if (Array.isArray(v)) return "[" + v.map(nxRepr).join(", ") + "]";
  if (typeof v === "object") return "{" + Object.entries(v).map(([k, val]) => `'${k}': ${nxRepr(val)}`).join(", ") + "}";
  return String(v);
}
function nxAdd(a, b) {
  if (typeof a === "string" || typeof b === "string") return nxStringify(a) + nxStringify(b);
  if (Array.isArray(a) && Array.isArray(b)) return a.concat(b);
  return a + b;
}
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
        if op == "%":
            return f"({left} % {right})"
        if op in ("-", "*", "/") or op in _COMPARE_OPS:
            return f"({left} {op} {right})"
        if op == "==":
            return f"({left} === {right})"
        if op == "!=":
            return f"({left} !== {right})"
        raise ValueError(f"unsupported operator {op}")

    def _expr_Call(self, expr):
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
