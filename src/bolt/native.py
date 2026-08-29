"""AOT-compiles a scoped subset of Bolt to native code via C + gcc.

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
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ast_nodes import Assign, Call, FuncStmt, Variable
from .errors import BoltError


class NativeCompileError(BoltError):
    pass


class _Unsupported(Exception):
    pass


_COMPARE_OPS = {"==", "!=", "<", "<=", ">", ">="}

# Bolt builtin name -> (C function from <math.h>, arity). These are safe to
# inline directly since they're pure functions over doubles with no
# allocation - unlike Bolt's own min()/max() (which accept a list or
# varargs), the native versions require exactly this many plain arguments.
_MATH_BUILTINS = {
    "sqrt": ("sqrt", 1),
    "abs": ("fabs", 1),
    "floor": ("floor", 1),
    "ceil": ("ceil", 1),
    "pow": ("pow", 2),
    "min": ("fmin", 2),
    "max": ("fmax", 2),
}


_SYMBOL_PREFIX = "bolt_fn_"  # namespaces every emitted C symbol so a Bolt
# function named e.g. hypot/pow/log can't collide with the identically-
# named function libc's own math.h already declares - a real bug this
# surfaced under MSVC (C2375: redefinition; different linkage), which
# gcc had been silently letting slide.


class _CCompiler:
    def __init__(self, all_top_level_names: set[str] | None = None):
        # Every top-level Bolt function name, not just the eligible ones -
        # used only to decide whether a Call target should be prefixed as
        # a peer function; an unresolvable target still fails to compile
        # naturally (undefined C symbol), same as before this existed.
        self._user_fn_names = all_top_level_names or set()

    def check_eligible(self, func: FuncStmt) -> str | None:
        try:
            self._emit_func(func)
            return None
        except _Unsupported as e:
            return str(e)

    def emit_module(self, funcs: list[FuncStmt]) -> str:
        # __declspec(dllexport) is needed for MSVC to expose these symbols
        # from the DLL at all (unlike gcc/Clang, which export everything
        # from a shared object by default) - defining it as empty on other
        # compilers keeps one code path for both.
        export_macro = (
            "#if defined(_MSC_VER)\n"
            "#define BOLT_EXPORT __declspec(dllexport)\n"
            "#else\n"
            "#define BOLT_EXPORT\n"
            "#endif\n"
        )
        protos = "\n".join(
            f"BOLT_EXPORT double {_SYMBOL_PREFIX}{f.name}({', '.join('double' for _ in f.params)});"
            for f in funcs
        )
        bodies = "\n\n".join(self._emit_func(f) for f in funcs)
        return f"#include <math.h>\n\n{export_macro}\n{protos}\n\n{bodies}\n"

    # ---- function/statement/expression emission ----

    def _emit_func(self, func: FuncStmt) -> str:
        if len(func.param_types) != len(func.params) or any(t != "number" for t in func.param_types):
            raise _Unsupported(f"'{func.name}': all parameters must be annotated 'number'")
        if func.return_type != "number":
            raise _Unsupported(f"'{func.name}': return type must be annotated 'number'")
        params_c = ", ".join(f"double {p}" for p in func.params)
        known = set(func.params)
        body_c = self._emit_block(func.body, known)
        return f"BOLT_EXPORT double {_SYMBOL_PREFIX}{func.name}({params_c}) {{\n{body_c}\n}}"

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
            name = expr.callee.name
            if name in _MATH_BUILTINS:
                if len(expr.args) != _MATH_BUILTINS[name][1]:
                    raise _Unsupported(f"'{name}' in native code needs exactly {_MATH_BUILTINS[name][1]} argument(s)")
                c_name = _MATH_BUILTINS[name][0]
                args = ", ".join(self._emit_expr(a, known) for a in expr.args)
                return f"{c_name}({args})"
            args = ", ".join(self._emit_expr(a, known) for a in expr.args)
            c_name = f"{_SYMBOL_PREFIX}{name}" if name in self._user_fn_names else name
            return f"{c_name}({args})"
        if kind == "Assign":
            if not isinstance(expr.target, Variable):
                raise _Unsupported("only assignment to simple variables is supported")
            return f"{expr.target.name} = {self._emit_expr(expr.value, known)}"
        raise _Unsupported(f"unsupported expression: {kind}")


def _wrap(cfunc):
    def wrapper(*args):
        result = cfunc(*(float(a) for a in args))
        # C only has doubles, so a native result carries no int/float
        # distinction - collapse whole numbers to int since that's the
        # overwhelmingly common case (counters, indices, recursive
        # arithmetic like fib()). The one known gap this creates: a
        # function whose *interpreted* result is a genuine float that
        # happens to be a whole number (e.g. sqrt(25) == 5.0) will print
        # as "5" instead of "5.0" when run natively - the value is
        # numerically identical either way, just displayed differently.
        return int(result) if float(result).is_integer() else result
    return wrapper


_msvc_env_cache: dict | None = None


def _find_msvc_env() -> dict | None:
    """Locates a Visual Studio (or Build Tools) install via vswhere and
    harvests the environment vcvarsall.bat sets up (INCLUDE/LIB/PATH with
    cl.exe on it) by running it in a child cmd.exe and capturing `set`.
    Cached after the first successful call since it's a subprocess launch.
    """
    global _msvc_env_cache
    if _msvc_env_cache is not None:
        return _msvc_env_cache or None
    if platform.system() != "Windows":
        _msvc_env_cache = {}
        return None

    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
        "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        _msvc_env_cache = {}
        return None

    try:
        install_path = subprocess.run(
            [str(vswhere), "-latest", "-products", "*",
             "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-property", "installationPath"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        _msvc_env_cache = {}
        return None
    if not install_path:
        _msvc_env_cache = {}
        return None

    vcvars = Path(install_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.exists():
        _msvc_env_cache = {}
        return None

    try:
        out = subprocess.run(
            f'cmd /c "\"{vcvars}\" >nul 2>&1 && set"',
            capture_output=True, text=True, shell=True,
        ).stdout
    except OSError:
        _msvc_env_cache = {}
        return None

    env = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            env[k] = v
    if "PATH" not in env or not shutil.which("cl.exe", path=env.get("PATH")):
        _msvc_env_cache = {}
        return None

    _msvc_env_cache = env
    return env


def _compile_c(c_path: Path, dll_path: Path) -> None:
    """Compiles the emitted C into a shared library, preferring gcc (works
    unmodified on Linux/macOS/MinGW) and falling back to MSVC's cl.exe on
    Windows machines that only have Visual Studio Build Tools installed -
    no mingw/gcc required there.
    """
    if shutil.which("gcc"):
        result = subprocess.run(
            ["gcc", "-O2", "-shared", "-fPIC", "-o", str(dll_path), str(c_path), "-lm"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise NativeCompileError(f"gcc failed to compile native functions:\n{result.stderr}")
        return

    msvc_env = _find_msvc_env()
    if msvc_env is not None:
        cl_path = shutil.which("cl.exe", path=msvc_env.get("PATH"))
        result = subprocess.run(
            [cl_path, "/nologo", "/O2", "/LD", f"/Fe:{dll_path}", str(c_path)],
            capture_output=True, text=True, cwd=str(c_path.parent), env=msvc_env,
        )
        if result.returncode != 0:
            raise NativeCompileError(f"cl.exe failed to compile native functions:\n{result.stdout}\n{result.stderr}")
        return

    raise NativeCompileError(
        "No C compiler found for --native: install gcc (e.g. via MSYS2/MinGW) "
        "or Visual Studio Build Tools with the \"Desktop development with C++\" "
        "workload."
    )


def compile_native(statements, out_dir: str | None = None):
    """Returns (wrappers, compiled_names, skipped) for the top-level `func`
    declarations found in `statements`. `wrappers` maps name -> a Python
    callable backed by natively-compiled code; `skipped` maps name -> reason
    for every top-level function that wasn't eligible.
    """
    funcs = [s for s in statements if isinstance(s, FuncStmt)]
    compiler = _CCompiler({f.name for f in funcs})

    eligible, skipped = [], {}
    for f in funcs:
        reason = compiler.check_eligible(f)
        (skipped.__setitem__(f.name, reason) if reason else eligible.append(f))

    if not eligible:
        raise NativeCompileError(
            "No native-eligible top-level functions (need every param and the "
            "return type annotated 'number', with no strings/lists/maps/closures)"
        )

    work_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="bolt_native_"))
    c_path = work_dir / "bolt_native.c"
    dll_ext = ".dll" if platform.system() == "Windows" else ".so"
    so_path = work_dir / f"bolt_native{dll_ext}"
    c_path.write_text(compiler.emit_module(eligible))

    _compile_c(c_path, so_path)

    lib = ctypes.CDLL(str(so_path))
    wrappers = {}
    for f in eligible:
        cfunc = getattr(lib, f"{_SYMBOL_PREFIX}{f.name}")
        cfunc.restype = ctypes.c_double
        cfunc.argtypes = [ctypes.c_double] * len(f.params)
        wrappers[f.name] = _wrap(cfunc)

    return wrappers, [f.name for f in eligible], skipped
