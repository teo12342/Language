import io
import sys

import pytest

from bolt.builtins import make_builtins
from bolt.compiler import compile_program
from bolt.errors import BoltRuntimeError
from bolt.lexer import Lexer
from bolt.parser import Parser
from bolt.vm import VM, Closure


def _call_fn(vm_holder):
    def call_fn(fn, args):
        if isinstance(fn, Closure):
            return vm_holder["vm"].call_closure(fn, args, 0)
        return fn(*args)
    return call_fn


def run_and_capture(source):
    holder = {}
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    proto = compile_program(stmts)
    vm = VM(make_builtins(_call_fn(holder)))
    holder["vm"] = vm
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        vm.run_program(proto)
    finally:
        sys.stdout = old_stdout
    return captured.getvalue()


def test_math_functions():
    out = run_and_capture(
        """
        print(sqrt(16))
        print(abs(-5))
        print(min(3, 1, 2))
        print(max([3, 1, 2]))
        print(floor(3.7))
        print(ceil(3.2))
        print(round(3.456, 2))
        print(pow(2, 10))
        """
    )
    assert out.strip().splitlines() == ["4.0", "5", "1", "3", "3", "4", "3.46", "1024"]


def test_sqrt_negative_raises():
    with pytest.raises(BoltRuntimeError):
        run_and_capture("print(sqrt(-1))")


def test_string_functions():
    out = run_and_capture(
        """
        print(trim("  hi  "))
        print(replace("hello world", "world", "bolt"))
        print(repeat("ab", 3))
        print(starts_with("hello", "he"))
        print(ends_with("hello", "lo"))
        """
    )
    assert out.strip().splitlines() == ["hi", "hello bolt", "ababab", "true", "true"]


def test_list_functions():
    out = run_and_capture(
        """
        print(contains([1, 2, 3], 2))
        print(index_of([10, 20, 30], 20))
        print(index_of([10, 20, 30], 99))
        print(sort([3, 1, 2]))
        print(reverse([1, 2, 3]))
        print(slice([1, 2, 3, 4, 5], 1, 3))
        print(slice([1, 2, 3, 4, 5], 2))
        print(concat([1, 2], [3, 4]))
        print(concat("foo", "bar"))
        """
    )
    assert out.strip().splitlines() == [
        "true", "1", "-1", "[1, 2, 3]", "[3, 2, 1]", "[2, 3]", "[3, 4, 5]", "[1, 2, 3, 4]", "foobar",
    ]


def test_tensor_transpose():
    out = run_and_capture(
        """
        let t = tensor([[1, 2], [3, 4], [5, 6]])
        print(tolist(transpose(t)))
        """
    )
    assert out.strip() == "[[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]]"


def test_tensor_identity():
    out = run_and_capture("print(tolist(identity(3)))")
    assert out.strip() == "[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]"


def test_tmap_calls_back_into_bolt_function():
    out = run_and_capture(
        """
        func square(x) { return x * x }
        print(tolist(tmap(tensor([1, 2, 3]), square)))
        """
    )
    assert out.strip() == "[1.0, 4.0, 9.0]"


def test_sort_and_reverse_mutate_in_place_and_return_same_list():
    out = run_and_capture(
        """
        let a = [3, 1, 2]
        let b = sort(a)
        print(a)
        print(b)
        """
    )
    assert out.strip().splitlines() == ["[1, 2, 3]", "[1, 2, 3]"]
