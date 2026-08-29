import io
import sys

import pytest

from nexus.builtins import make_builtins
from nexus.compiler import compile_program
from nexus.errors import NexusRuntimeError
from nexus.lexer import Lexer
from nexus.parser import Parser
from nexus.tensor import Tensor, dot, matmul
from nexus.vm import VM


def run_and_capture(source):
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


def test_tensor_from_nested_1d():
    t = Tensor.from_nested([1, 2, 3])
    assert t.shape == (3,)
    assert t.data == [1.0, 2.0, 3.0]


def test_tensor_from_nested_2d():
    t = Tensor.from_nested([[1, 2], [3, 4]])
    assert t.shape == (2, 2)
    assert t.to_nested() == [[1.0, 2.0], [3.0, 4.0]]


def test_tensor_ragged_rows_raises():
    with pytest.raises(ValueError):
        Tensor.from_nested([[1, 2], [3]])


def test_elementwise_add_mul():
    a = Tensor.from_nested([1, 2, 3])
    b = Tensor.from_nested([4, 5, 6])
    assert (a + b).data == [5.0, 7.0, 9.0]
    assert (a * b).data == [4.0, 10.0, 18.0]


def test_scalar_broadcast():
    a = Tensor.from_nested([1, 2, 3])
    assert (a * 10).data == [10.0, 20.0, 30.0]


def test_shape_mismatch_raises():
    a = Tensor.from_nested([1, 2, 3])
    b = Tensor.from_nested([1, 2])
    with pytest.raises(ValueError):
        a + b


def test_dot_product():
    a = Tensor.from_nested([1, 2, 3])
    b = Tensor.from_nested([4, 5, 6])
    assert dot(a, b) == 32.0


def test_matmul():
    a = Tensor.from_nested([[1, 2], [3, 4]])
    b = Tensor.from_nested([[5, 6], [7, 8]])
    result = matmul(a, b)
    assert result.to_nested() == [[19.0, 22.0], [43.0, 50.0]]


def test_tensor_end_to_end_via_vm():
    out = run_and_capture(
        """
        let a = tensor([1, 2, 3])
        let b = tensor([4, 5, 6])
        print(tolist(a + b))
        print(dot(a, b))
        """
    )
    assert out.strip().splitlines() == ["[5.0, 7.0, 9.0]", "32.0"]


def test_tensor_shape_mismatch_is_runtime_error():
    with pytest.raises(NexusRuntimeError):
        run_and_capture(
            """
            let a = tensor([1, 2, 3])
            let b = tensor([1, 2])
            print(tolist(a + b))
            """
        )
