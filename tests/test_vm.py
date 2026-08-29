import io
import sys

import pytest

from bolt.builtins import make_builtins
from bolt.compiler import compile_program
from bolt.errors import BoltRuntimeError
from bolt.lexer import Lexer
from bolt.parser import Parser
from bolt.vm import VM


def run(source):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    proto = compile_program(stmts)
    VM(make_builtins()).run_program(proto)


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
    assert run_and_capture("print(1 + 2 * 3)").strip() == "7"


def test_string_concat():
    assert run_and_capture('print("a" + "b")').strip() == "ab"


def test_variables_and_reassignment():
    assert run_and_capture("let x = 1\nx = x + 1\nprint(x)").strip() == "2"


def test_if_else():
    out = run_and_capture('if 1 < 2 { print("yes") } else { print("no") }')
    assert out.strip() == "yes"


def test_while_loop():
    out = run_and_capture("let i = 0\nwhile i < 3 { print(i)\ni = i + 1 }")
    assert out.strip().splitlines() == ["0", "1", "2"]


def test_for_loop_over_list():
    out = run_and_capture("for x in [1,2,3] { print(x) }")
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


def test_closures_per_iteration_are_distinct():
    out = run_and_capture(
        """
        func make_adders() {
            let fns = []
            for i in range(3) {
                func adder(x) { return x + i }
                push(fns, adder)
            }
            return fns
        }
        let fns = make_adders()
        print(fns[0](10), fns[1](10), fns[2](10))
        """
    )
    assert out.strip() == "10 11 12"


def test_nested_closures():
    out = run_and_capture(
        """
        func outer() {
            let a = 1
            func middle() {
                let b = 2
                func inner() { return a + b }
                return inner()
            }
            return middle()
        }
        print(outer())
        """
    )
    assert out.strip() == "3"


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
    assert out.strip() == "4"


def test_break_and_continue_in_while():
    out = run_and_capture(
        """
        let i = 0
        let acc = 0
        while i < 10 {
            i = i + 1
            if i % 2 == 0 { continue }
            if i > 7 { break }
            acc = acc + i
        }
        print(acc)
        """
    )
    assert out.strip() == "16"


def test_undefined_variable_raises():
    with pytest.raises(BoltRuntimeError):
        run("print(missing)")


def test_division_by_zero_raises():
    with pytest.raises(BoltRuntimeError):
        run("print(1 / 0)")


def test_list_and_map_indexing():
    out = run_and_capture('let m = {"a": 1}\nlet l = [10, 20]\nprint(m["a"], l[1])')
    assert out.strip() == "1 20"


def test_and_or_short_circuit():
    out = run_and_capture(
        """
        func noisy(v) {
            print("called")
            return v
        }
        print(false and noisy(true))
        print(true or noisy(false))
        """
    )
    # noisy() should never run for either short-circuited branch
    assert "called" not in out
    assert out.strip().splitlines() == ["false", "true"]
