import shutil
import subprocess
import sys

import pytest

from bolt.jsgen import generate_js
from bolt.lexer import Lexer
from bolt.parser import Parser

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def run_js(source: str, tmp_path) -> str:
    tokens = Lexer(source).tokenize()
    stmts = Parser(tokens).parse()
    js_source = generate_js(stmts)
    js_path = tmp_path / "out.js"
    js_path.write_text(js_source)
    result = subprocess.run(["node", str(js_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_arithmetic(tmp_path):
    assert run_js("print(1 + 2 * 3)", tmp_path).strip() == "7"


def test_string_add_number_auto_stringifies(tmp_path):
    assert run_js('print("count: " + 5)', tmp_path).strip() == "count: 5"


def test_closures(tmp_path):
    out = run_js(
        """
        func make_counter() {
            let count = 0
            func inc() { count = count + 1\nreturn count }
            return inc
        }
        let c = make_counter()
        print(c())
        print(c())
        """,
        tmp_path,
    )
    assert out.strip().splitlines() == ["1", "2"]


def test_recursion(tmp_path):
    out = run_js(
        """
        func fact(n) {
            if n <= 1 { return 1 }
            return n * fact(n - 1)
        }
        print(fact(5))
        """,
        tmp_path,
    )
    assert out.strip() == "120"


def test_for_loop_break_continue(tmp_path):
    out = run_js(
        """
        let total = 0
        for i in range(5) {
            if i == 2 { continue }
            if i == 4 { break }
            total = total + i
        }
        print(total)
        """,
        tmp_path,
    )
    assert out.strip() == "4"


def test_lists_and_maps(tmp_path):
    out = run_js('let m = {"a": 1}\nlet l = [10, 20]\nprint(m["a"], l[1])', tmp_path)
    assert out.strip() == "1 20"


def test_nil_true_false_top_level(tmp_path):
    out = run_js("print(true)\nprint(nil)\nprint(false)", tmp_path)
    assert out.strip().splitlines() == ["true", "nil", "false"]


def test_stdlib_math_and_string_functions(tmp_path):
    out = run_js(
        """
        print(sqrt(16), abs(-5), min(3, 1, 2), max([3, 1, 2]))
        print(trim("  hi  "), replace("a-b", "-", "+"), starts_with("bolt", "bo"))
        print(sort([3, 1, 2]), reverse([1, 2, 3]), contains([1, 2], 2))
        """,
        tmp_path,
    )
    assert out.strip().splitlines() == [
        "4 5 1 3",
        "hi a+b true",
        "[1, 2, 3] [3, 2, 1] true",
    ]


def test_tensor_elementwise_and_matmul(tmp_path):
    out = run_js(
        """
        let a = tensor([1, 2, 3])
        let b = tensor([4, 5, 6])
        print(tolist(a + b))
        print(dot(a, b))
        let m = tensor([[1, 2], [3, 4]])
        let n = tensor([[5, 6], [7, 8]])
        print(tolist(matmul(m, n)))
        print(tolist(transpose(m)))
        """,
        tmp_path,
    )
    lines = out.strip().splitlines()
    assert lines[0] == "[5, 7, 9]"
    assert lines[1] == "32"
    assert lines[2] == "[[19, 22], [43, 50]]"
    assert lines[3] == "[[1, 3], [2, 4]]"


def test_tensor_fractional_values_match_numerically(tmp_path):
    # dot() here returns a value that's numerically 11.0 but prints as
    # "11" in JS (no separate int/float type, unlike Python) - the same
    # display-only quirk native compilation has via C doubles. The
    # fractional list entries prove the underlying math is exact.
    out = run_js(
        """
        let a = tensor([1, 2, 3])
        let b = tensor([0.5, 1.5, 2.5])
        print(tolist(a + b))
        print(dot(a, b))
        """,
        tmp_path,
    )
    assert out.strip().splitlines() == ["[1.5, 3.5, 5.5]", "11"]


def test_tmap_applies_bolt_function_elementwise(tmp_path):
    out = run_js(
        """
        func square(x) { return x * x }
        print(tolist(tmap(tensor([1, 2, 3]), square)))
        """,
        tmp_path,
    )
    assert out.strip() == "[1, 4, 9]"
