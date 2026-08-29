import pytest

from nexus.errors import NexusSyntaxError
from nexus.lexer import Lexer, TokenType as T


def types_of(source):
    return [t.type for t in Lexer(source).tokenize()]


def test_numbers():
    tokens = Lexer("42 3.14").tokenize()
    assert tokens[0].literal == 42
    assert tokens[1].literal == 3.14


def test_string_with_escapes():
    tokens = Lexer('"hi\\n"').tokenize()
    assert tokens[0].literal == "hi\n"


def test_keywords():
    result = types_of("let func if else while for in true false nil and or not")
    assert result[:-1] == [
        T.LET, T.FUNC, T.IF, T.ELSE, T.WHILE, T.FOR, T.IN,
        T.TRUE, T.FALSE, T.NIL, T.AND, T.OR, T.NOT,
    ]


def test_operators():
    result = types_of("+ - * / % == != < <= > >= =")
    assert result[:-1] == [
        T.PLUS, T.MINUS, T.STAR, T.SLASH, T.PERCENT,
        T.EQEQ, T.BANGEQ, T.LT, T.LTEQ, T.GT, T.GTEQ, T.EQ,
    ]


def test_unterminated_string_raises():
    with pytest.raises(NexusSyntaxError):
        Lexer('"unterminated').tokenize()


def test_comment_ignored():
    tokens = Lexer("1 # a comment\n2").tokenize()
    literals = [t.literal for t in tokens if t.type == T.NUMBER]
    assert literals == [1, 2]
