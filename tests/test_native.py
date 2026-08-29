import shutil

import pytest

from bolt.errors import BoltTypeError
from bolt.lexer import Lexer
from bolt.native import NativeCompileError, compile_native
from bolt.parser import Parser
from bolt.typechecker import check_types

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not available")


def parse(source):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    check_types(stmts)
    return stmts


def test_compiles_eligible_function():
    stmts = parse(
        """
        func square(x: number): number {
            return x * x
        }
        """
    )
    wrappers, compiled, skipped = compile_native(stmts)
    assert compiled == ["square"]
    assert skipped == {}
    assert wrappers["square"](5) == 25


def test_recursive_native_function():
    stmts = parse(
        """
        func fib(n: number): number {
            if n < 2 { return n }
            return fib(n - 1) + fib(n - 2)
        }
        """
    )
    wrappers, compiled, _ = compile_native(stmts)
    assert wrappers["fib"](20) == 6765


def test_ineligible_function_is_skipped_not_fatal():
    stmts = parse(
        """
        func square(x: number): number { return x * x }
        func greet(name: string): string { return name }
        """
    )
    wrappers, compiled, skipped = compile_native(stmts)
    assert compiled == ["square"]
    assert "greet" in skipped


def test_while_loop_and_locals():
    stmts = parse(
        """
        func sum_to(n: number): number {
            let total = 0
            let i = 0
            while i < n {
                total = total + i
                i = i + 1
            }
            return total
        }
        """
    )
    wrappers, _, _ = compile_native(stmts)
    assert wrappers["sum_to"](10) == 45


def test_for_range_loop():
    stmts = parse(
        """
        func sum_range(n: number): number {
            let total = 0
            for i in range(n) {
                total = total + i
            }
            return total
        }
        """
    )
    wrappers, compiled, _ = compile_native(stmts)
    assert compiled == ["sum_range"]
    assert wrappers["sum_range"](10) == 45
    assert wrappers["sum_range"](1000) == 499500


def test_for_range_with_start_stop_step():
    stmts = parse(
        """
        func sum_evens(n: number): number {
            let total = 0
            for i in range(0, n, 2) {
                total = total + i
            }
            return total
        }
        """
    )
    wrappers, _, _ = compile_native(stmts)
    assert wrappers["sum_evens"](10) == 0 + 2 + 4 + 6 + 8


def test_for_over_non_range_is_skipped_not_fatal():
    stmts = parse(
        """
        func f(n: number): number {
            let total = 0
            for i in n {
                total = total + i
            }
            return total
        }
        func g(n: number): number {
            return n * 2
        }
        """
    )
    wrappers, compiled, skipped = compile_native(stmts)
    assert compiled == ["g"]
    assert "f" in skipped


def test_no_eligible_functions_raises():
    stmts = parse('func greet(name: string): string { return name }')
    with pytest.raises(NativeCompileError):
        compile_native(stmts)


def test_returns_int_for_whole_numbers():
    stmts = parse("func identity(x: number): number { return x }")
    wrappers, _, _ = compile_native(stmts)
    assert wrappers["identity"](7) == 7
    assert isinstance(wrappers["identity"](7), int)


def test_native_math_builtins():
    stmts = parse(
        """
        func hypot(a: number, b: number): number {
            return sqrt(a * a + b * b)
        }
        func clamp(x: number, lo: number, hi: number): number {
            return min(max(x, lo), hi)
        }
        func rounded(x: number): number {
            return floor(x) + ceil(x)
        }
        """
    )
    wrappers, compiled, skipped = compile_native(stmts)
    assert set(compiled) == {"hypot", "clamp", "rounded"}
    assert skipped == {}
    assert abs(wrappers["hypot"](3, 5) - 5.830951894845301) < 1e-9
    assert wrappers["clamp"](15, 0, 10) == 10
    assert wrappers["clamp"](-5, 0, 10) == 0
    assert wrappers["rounded"](3.2) == 7  # floor(3.2) + ceil(3.2) = 3 + 4


def test_native_min_max_wrong_arity_is_skipped():
    stmts = parse(
        """
        func f(a: number, b: number, c: number): number {
            return min(a, b, c)
        }
        func g(x: number): number {
            return x + 1
        }
        """
    )
    wrappers, compiled, skipped = compile_native(stmts)
    assert compiled == ["g"]
    assert "f" in skipped
