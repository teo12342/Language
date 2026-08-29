import pytest

from nexus.ast_nodes import Binary, ExprStmt, FuncStmt, IfStmt, LetStmt
from nexus.errors import NexusSyntaxError
from nexus.lexer import Lexer
from nexus.parser import Parser


def parse(source):
    tokens = Lexer(source).tokenize()
    return Parser(tokens).parse()


def test_let_statement():
    stmts = parse("let x = 1 + 2")
    assert len(stmts) == 1
    assert isinstance(stmts[0], LetStmt)
    assert stmts[0].name == "x"
    assert isinstance(stmts[0].initializer, Binary)


def test_func_statement():
    stmts = parse("func add(a, b) { return a + b }")
    assert isinstance(stmts[0], FuncStmt)
    assert stmts[0].params == ["a", "b"]


def test_if_else():
    stmts = parse("if x { let a = 1 } else { let a = 2 }")
    assert isinstance(stmts[0], IfStmt)
    assert stmts[0].else_branch is not None


def test_expr_statement():
    stmts = parse("1 + 2 * 3")
    assert isinstance(stmts[0], ExprStmt)


def test_syntax_error_reports_line():
    with pytest.raises(NexusSyntaxError) as exc_info:
        parse("let x = 1\nlet y = )")
    assert exc_info.value.line == 2
