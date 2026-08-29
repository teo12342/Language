import pytest

from nexus.errors import NexusTypeError
from nexus.lexer import Lexer
from nexus.parser import Parser
from nexus.typechecker import check_types


def check(source):
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    check_types(stmts)


def test_untyped_code_always_passes():
    check(
        """
        let x = 1
        x = "now a string"
        x = [1, 2, 3]
        func f(a) { return a }
        print(f(x))
        """
    )


def test_valid_typed_function():
    check(
        """
        func add(a: number, b: number): number {
            return a + b
        }
        print(add(1, 2))
        """
    )


def test_valid_typed_let():
    check("let x: number = 5\nx = 10")


def test_string_plus_number_is_allowed():
    # Matches runtime auto-stringify semantics.
    check('let total: number = 5\nprint("count: " + total)')


def test_let_type_mismatch_raises():
    with pytest.raises(NexusTypeError):
        check('let x: number = "not a number"')


def test_reassign_typed_var_wrong_type_raises():
    with pytest.raises(NexusTypeError):
        check("let x: bool = true\nx = [1, 2]")


def test_call_arg_type_mismatch_raises():
    with pytest.raises(NexusTypeError):
        check(
            """
            func add(a: number, b: number): number { return a + b }
            print(add(1, "two"))
            """
        )


def test_call_arity_mismatch_raises():
    with pytest.raises(NexusTypeError):
        check(
            """
            func add(a: number, b: number): number { return a + b }
            print(add(1))
            """
        )


def test_return_type_mismatch_raises():
    with pytest.raises(NexusTypeError):
        check(
            """
            func greet(name: string): string {
                return 42
            }
            """
        )


def test_arithmetic_on_non_numbers_raises():
    with pytest.raises(NexusTypeError):
        check('let a: bool = true\nlet b: number = a - 1')


def test_unknown_type_name_raises():
    with pytest.raises(NexusTypeError):
        check("let x: frobnicate = 1")


def test_unannotated_params_stay_dynamic():
    check(
        """
        func identity(a) { return a }
        print(identity(1))
        print(identity("two"))
        print(identity([3]))
        """
    )


def test_nested_function_type_checked():
    with pytest.raises(NexusTypeError):
        check(
            """
            func outer() {
                func inner(a: number): number {
                    return "not a number"
                }
            }
            """
        )


def test_recursive_typed_function():
    check(
        """
        func fact(n: number): number {
            if n <= 1 { return 1 }
            return n * fact(n - 1)
        }
        print(fact(5))
        """
    )
