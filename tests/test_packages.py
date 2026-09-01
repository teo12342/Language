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


def test_import_exposes_module_functions_as_a_map():
    out = run_vm_and_capture(
        """
        let m = import("packages/mathutils.bo")
        print(m.square(5))
        print(m.is_even(4), m.is_odd(4))
        """
    )
    assert out.strip().splitlines() == ["25", "true false"]


def test_import_module_recursion_resolves_correctly():
    # Regression check for the cross-VM global-resolution bug: factorial()
    # calls itself by name, which only works if the wrapper dispatches
    # back through the module's OWN VM rather than the importer's.
    out = run_vm_and_capture('let m = import("packages/mathutils.bo")\nprint(m.factorial(5))')
    assert out.strip() == "120"


def test_import_module_internal_cross_calls_resolve():
    # stddev() calls variance() calls mean() - all within the same module.
    out = run_vm_and_capture(
        'let s = import("packages/stats.bo")\nprint(s.stddev([2, 4, 4, 4, 5, 5, 7, 9]))'
    )
    assert out.strip() == "2.0"


def test_import_works_identically_on_tree_walker():
    src = 'let m = import("packages/mathutils.bo")\nprint(m.factorial(5), m.gcd(48, 18))'
    assert run_vm_and_capture(src) == run_tree_and_capture(src)


def test_import_same_path_is_cached():
    out = run_vm_and_capture(
        """
        let a = import("packages/mathutils.bo")
        let b = import("packages/mathutils.bo")
        print(a.square(3), b.square(3))
        """
    )
    assert out.strip() == "9 9"


def test_import_resolves_relative_to_project_root_from_any_cwd(tmp_path, monkeypatch):
    # Regression check: import() must find packages/ even when Bolt runs
    # from an unrelated working directory, not just from the repo root.
    monkeypatch.chdir(tmp_path)
    out = run_vm_and_capture('let m = import("packages/mathutils.bo")\nprint(m.square(6))')
    assert out.strip() == "36"


def test_import_missing_module_raises_clear_error():
    with pytest.raises(BoltRuntimeError, match="Cannot find module"):
        run_vm_and_capture('let m = import("packages/does_not_exist.bo")')


def test_stringutils_package():
    out = run_vm_and_capture(
        """
        let s = import("packages/stringutils.bo")
        print(s.title_case("hello bolt world"))
        print(s.is_palindrome("racecar"), s.is_palindrome("bolt"))
        print(s.pad_left("7", 4, "0"))
        """
    )
    assert out.strip().splitlines() == ["Hello Bolt World", "true false", "0007"]


def test_stats_package():
    out = run_vm_and_capture(
        """
        let s = import("packages/stats.bo")
        print(s.mean([1, 2, 3, 4, 5]))
        print(s.median([5, 3, 1, 4, 2]))
        """
    )
    assert out.strip().splitlines() == ["3.0", "3"]


def test_js_target_rejects_import_with_clear_error():
    tokens = Lexer('let m = import("packages/mathutils.bo")').tokenize()
    stmts = Parser(tokens).parse()
    with pytest.raises(BoltError, match="import\\(\\) is not supported by --target js"):
        generate_js(stmts)


def test_game2d_package_moves_and_clamps_a_body():
    out = run_vm_and_capture(
        """
        let g = import("packages/game2d.bo")
        let p = g.body(2, 3, 10, 10)
        p["vx"] = 5
        p["ay"] = 10
        g.move(p, 0.1)
        g.keep_inside(p, 0, 0, 20, 20)
        print(p["x"], p["y"])
        """
    )
    assert out.strip() == "2.5 3.1"
