import io
import sys

import pytest

from bolt.builtins import make_builtins
from bolt.compiler import compile_program
from bolt.errors import BoltError, BoltRuntimeError
from bolt.interpreter import Interpreter
from bolt.jsgen import generate_js
from bolt.lexer import Lexer
from bolt.parser import Parser
from bolt.vm import VM


def run_vm_and_capture(source):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    proto = compile_program(stmts)
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        VM(make_builtins()).run_program(proto)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def run_tree_and_capture(source):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        Interpreter(make_builtins()).run(stmts)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def test_pyimport_calls_real_python_stdlib_function():
    out = run_vm_and_capture(
        """
        let m = pyimport("math")
        print(m.sqrt(16))
        print(m.gcd(12, 18))
        """
    )
    assert out.strip().splitlines() == ["4.0", "6"]


def test_pyimport_exposes_constants_too():
    out = run_vm_and_capture('let m = pyimport("math")\nprint(m.pi)')
    assert out.strip().startswith("3.14159")


def test_pyimport_statistics_module():
    out = run_vm_and_capture(
        """
        let s = pyimport("statistics")
        print(s.mean([1, 2, 3, 4, 5]))
        print(s.median([5, 3, 1, 4, 2]))
        """
    )
    assert out.strip().splitlines() == ["3", "3"]


def test_pyimport_works_identically_on_tree_walker():
    src = 'let m = pyimport("math")\nprint(m.sqrt(16), m.floor(3.7))'
    assert run_vm_and_capture(src) == run_tree_and_capture(src)


def test_pyimport_is_cached():
    out = run_vm_and_capture(
        """
        let a = pyimport("math")
        let b = pyimport("math")
        print(a.sqrt(9), b.sqrt(9))
        """
    )
    assert out.strip() == "3.0 3.0"


def test_pyimport_rejects_modules_outside_the_allowlist():
    with pytest.raises(BoltRuntimeError, match="not in the allowed module list"):
        run_vm_and_capture('let os = pyimport("os")')


def test_pyimport_rejects_subprocess_and_sys():
    with pytest.raises(BoltRuntimeError, match="not in the allowed module list"):
        run_vm_and_capture('let sp = pyimport("subprocess")')
    with pytest.raises(BoltRuntimeError, match="not in the allowed module list"):
        run_vm_and_capture('let s = pyimport("sys")')


def test_pyimport_wraps_python_exceptions_as_bolt_runtime_errors():
    with pytest.raises(BoltRuntimeError, match="Python error"):
        run_vm_and_capture('let m = pyimport("math")\nm.sqrt(-1)')


def test_js_target_rejects_pyimport_with_clear_error():
    tokens = Lexer('let m = pyimport("math")').tokenize()
    stmts = Parser(tokens).parse()
    with pytest.raises(BoltError, match="pyimport\\(\\) is not supported by --target js"):
        generate_js(stmts)
