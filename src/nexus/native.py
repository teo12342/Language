"""AOT-compiles a scoped subset of Nexus to native code via C + gcc.

Eligible: top-level `func` declarations whose parameters and return type
are all annotated `number`, whose bodies only use arithmetic, comparisons,
if/while/`for x in range(...)`/return, and calls to other eligible
functions (including themselves, for recursion) - no strings, lists, maps,
tensors, closures, or break/continue. This mirrors how real interpreters
(PyPy, LuaJIT, V8's TurboFan) carve out a fast-path subset instead of
natively compiling every language feature at once.

Compiled functions are handed back as plain Python callables (backed by
a ctypes-loaded .so) that can be dropped straight into a VM's or
Interpreter's globals table under their original name - any call site,
including recursive self-calls, then transparently runs at native speed
with zero changes to the VM/interpreter dispatch.
"""

import ctypes
import subprocess
import tempfile
from pathlib import Path

from .ast_nodes import Assign, Call, FuncStmt, Variable
from .errors import NexusError


class NativeCompileError(NexusError):
    pass


class _Unsupported(Exception):
    pass


_COMPARE_OPS = {"==", "!=", "<", "<=", ">", ">="}


class _CCompiler:
    def check_eligible(self, func: FuncStmt) -> str | None:
        try:
            self._emit_func(func)
            return None
        except _Unsupported as e:
            return str(e)

    def emit_module(self, funcs: list[FuncStmt]) -> str:
        protos = "\n".join(
            f"double {f.name}({', '.join('double' for _ in f.params)});" for f in funcs
        )
        bodies = "\n\n".join(self._emit_func(f) for f in funcs)
        return f"#include <math.h>\n\n{protos}\n\n{bodies}\n"

    # ---- function/statement/expression emission ----

    def _emit_func(self, func: FuncStmt) -> str:
        if len(func.param_types) != len(func.params) or any(t != "number" for t in func.param_types):
            raise _Unsupported(f"'{func.name}': all parameters must be annotated 'number'")
        if func.return_type != "number":
            raise _Unsupported(f"'{func.name}': return type must be annotated 'number'")
        params_c = ", ".join(f"double {p}" for p in func.params)
        known = set(func.params)
        body_c = self._emit_block(func.body, known)
        return f"double {func.name}({params_c}) {{\n{body_c}\n}}"

    def _emit_block(self, stmts, known: set) -> str:
        return "\n".join(self._emit_stmt(s, known) for s in stmts)

    def _emit_stmt(self, stmt, known: set) -> str:
        kind = type(stmt).__name__
        if kind == "LetStmt":
            if stmt.initializer is None:
                raise _Unsupported("'let' without an initializer is not supported")
            value = self._emit_expr(stmt.initializer, known)
            known.add(stmt.name)
            return f"double {stmt.name} = {value};"
        if kind == "ExprStmt":
            if isinstance(stmt.expr, Assign):
                return self._emit_expr(stmt.expr, known) + ";"
            raise _Unsupported("only assignment expression-statements are supported")
        if kind == "ReturnStmt":
            if stmt.value is None:
                raise _Unsupported("bare 'return' is not supported")
            return f"return {self._emit_expr(stmt.value, known)};"
        if kind == "IfStmt":
            cond = self._emit_expr(stmt.condition, known)
            then_c = self._emit_block(stmt.then_branch, set(known))
            if stmt.else_branch is not None:
                else_c = self._emit_block(stmt.else_branch, set(known))
                return f"if ({cond}) {{\n{then_c}\n}} else {{\n{else_c}\n}}"
            return f"if ({cond}) {{\n{then_c}\n}}"
        if kind == "WhileStmt":
            cond = self._emit_expr(stmt.condition, known)
            body_c = self._emit_block(stmt.body, set(known))
            return f"while ({cond}) {{\n{body_c}\n}}"
        if kind == "ForStmt":
            return self._emit_for(stmt, known)
        raise _Unsupported(f"unsupported statement: {kind}")

    def _emit_for(self, stmt, known: set) -> str:
        call = stmt.iterable
        if not isinstance(call, Call) or not isinstance(call.callee, Variable) or call.callee.name != "range":
            raise _Unsupported("native 'for' loops only support 'for x in range(...)'")
        if not (1 <= len(call.args) <= 3):
            raise _Unsupported("range() takes 1 to 3 arguments")
        c_args = [self._emit_expr(a, known) for a in call.args]
        if len(c_args) == 1:
            start, stop, step = "0.0", c_args[0], "1.0"
        elif len(c_args) == 2:
            start, stop, step = c_args[0], c_args[1], "1.0"
        else:
            start, stop, step = c_args

        inner_known = set(known)
        inner_known.add(stmt.var_name)
        body_c = self._emit_block(stmt.body, inner_known)
        v = stmt.var_name
        # step's sign decides the loop direction, matching range()'s semantics.
        return (
            f"for (double {v} = ({start}); "
            f"(({step}) >= 0) ? ({v} < ({stop})) : ({v} > ({stop})); "
            f"{v} += ({step})) {{\n{body_c}\n}}"
        )

    def _emit_expr(self, expr, known: set) -> str:
        kind = type(expr).__name__
        if kind == "Literal":
            v = expr.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise _Unsupported("only numeric literals are supported")
            return repr(float(v))
        if kind == "Variable":
            if expr.name not in known:
                raise _Unsupported(f"'{expr.name}' is not a local/param (globals/closures unsupported)")
            return expr.name
        if kind == "Unary":
            if expr.op == "-":
                return f"(-{self._emit_expr(expr.right, known)})"
            raise _Unsupported("unary 'not' is not supported")
        if kind == "Binary":
            left = self._emit_expr(expr.left, known)
            right = self._emit_expr(expr.right, known)
            if expr.op == "%":
                return f"fmod({left}, {right})"
            if expr.op in _COMPARE_OPS:
                return f"(({left}) {expr.op} ({right}) ? 1.0 : 0.0)"
            if expr.op in ("+", "-", "*", "/"):
                return f"(({left}) {expr.op} ({right}))"
            raise _Unsupported(f"unsupported operator '{expr.op}'")
        if kind == "Logical":
            left = self._emit_expr(expr.left, known)
            right = self._emit_expr(expr.right, known)
            op = "&&" if expr.op == "and" else "||"
            return f"((({left}) != 0.0) {op} (({right}) != 0.0) ? 1.0 : 0.0)"
        if kind == "Call":
            if not isinstance(expr.callee, Variable):
                raise _Unsupported("only direct calls to named functions are supported")
            args = ", ".join(self._emit_expr(a, known) for a in expr.args)
            return f"{expr.callee.name}({args})"
        if kind == "Assign":
            if not isinstance(expr.target, Variable):
                raise _Unsupported("only assignment to simple variables is supported")
            return f"{expr.target.name} = {self._emit_expr(expr.value, known)}"
        raise _Unsupported(f"unsupported expression: {kind}")


def _wrap(cfunc):
    def wrapper(*args):
        result = cfunc(*(float(a) for a in args))
        return int(result) if float(result).is_integer() else result
    return wrapper


def compile_native(statements, out_dir: str | None = None):
    """Returns (wrappers, compiled_names, skipped) for the top-level `func`
    declarations found in `statements`. `wrappers` maps name -> a Python
    callable backed by natively-compiled code; `skipped` maps name -> reason
    for every top-level function that wasn't eligible.
    """
    funcs = [s for s in statements if isinstance(s, FuncStmt)]
    compiler = _CCompiler()

    eligible, skipped = [], {}
    for f in funcs:
        reason = compiler.check_eligible(f)
        (skipped.__setitem__(f.name, reason) if reason else eligible.append(f))

    if not eligible:
        raise NativeCompileError(
            "No native-eligible top-level functions (need every param and the "
            "return type annotated 'number', with no strings/lists/maps/closures)"
        )

    work_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="nexus_native_"))
    c_path = work_dir / "nexus_native.c"
    so_path = work_dir / "nexus_native.so"
    c_path.write_text(compiler.emit_module(eligible))

    result = subprocess.run(
        ["gcc", "-O2", "-shared", "-fPIC", "-o", str(so_path), str(c_path), "-lm"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise NativeCompileError(f"gcc failed to compile native functions:\n{result.stderr}")

    lib = ctypes.CDLL(str(so_path))
    wrappers = {}
    for f in eligible:
        cfunc = getattr(lib, f.name)
        cfunc.restype = ctypes.c_double
        cfunc.argtypes = [ctypes.c_double] * len(f.params)
        wrappers[f.name] = _wrap(cfunc)

    return wrappers, [f.name for f in eligible], skipped
