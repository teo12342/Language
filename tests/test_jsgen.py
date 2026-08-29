import shutil
import subprocess
import sys

import pytest

from nexus.jsgen import generate_js
from nexus.lexer import Lexer
from nexus.parser import Parser

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
