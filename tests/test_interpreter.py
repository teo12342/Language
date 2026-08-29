import io
import sys

import pytest

from nexus.builtins import make_builtins
from nexus.errors import NexusRuntimeError
from nexus.interpreter import Interpreter
from nexus.lexer import Lexer
from nexus.parser import Parser


def run(source, builtins=None):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    Interpreter(builtins if builtins is not None else make_builtins()).run(stmts)


def run_and_capture(source):
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        run(source)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def test_arithmetic():
    out = run_and_capture("print(1 + 2 * 3)")
    assert out.strip() == "7"


def test_string_concat():
    out = run_and_capture('print("a" + "b")')
    assert out.strip() == "ab"


def test_variables_and_reassignment():
    out = run_and_capture("let x = 1\nx = x + 1\nprint(x)")
    assert out.strip() == "2"


def test_if_else():
    out = run_and_capture("if 1 < 2 { print(\"yes\") } else { print(\"no\") }")
    assert out.strip() == "yes"


def test_while_loop():
    out = run_and_capture("let i = 0\nwhile i < 3 { print(i)\ni = i + 1 }")
    assert out.strip().splitlines() == ["0", "1", "2"]


def test_for_loop_over_list():
    out = run_and_capture('for x in [1,2,3] { print(x) }')
    assert out.strip().splitlines() == ["1", "2", "3"]


def test_closures_capture_state():
    out = run_and_capture(
        """
        func make_counter() {
            let count = 0
            func inc() {
                count = count + 1
                return count
            }
            return inc
        }
        let c = make_counter()
        print(c())
        print(c())
        """
    )
    assert out.strip().splitlines() == ["1", "2"]


def test_recursion():
    out = run_and_capture(
        """
        func fact(n) {
            if n <= 1 { return 1 }
            return n * fact(n - 1)
        }
        print(fact(5))
        """
    )
    assert out.strip() == "120"


def test_break_and_continue():
    out = run_and_capture(
        """
        let total = 0
        for i in range(5) {
            if i == 2 { continue }
            if i == 4 { break }
            total = total + i
        }
        print(total)
        """
    )
    assert out.strip() == "4"  # 0 + 1 + 3


def test_undefined_variable_raises():
    with pytest.raises(NexusRuntimeError):
        run("print(missing)")


def test_division_by_zero_raises():
    with pytest.raises(NexusRuntimeError):
        run("print(1 / 0)")


def test_list_and_map_indexing():
    out = run_and_capture(
        'let m = {"a": 1}\nlet l = [10, 20]\nprint(m["a"], l[1])'
    )
    assert out.strip() == "1 20"
