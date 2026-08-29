from dataclasses import dataclass
from enum import Enum, auto

from .errors import BoltSyntaxError


class TokenType(Enum):
    # Literals
    NUMBER = auto()
    STRING = auto()
    IDENTIFIER = auto()
    # Keywords
    LET = auto()
    FUNC = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    BREAK = auto()
    CONTINUE = auto()
    TRUE = auto()
    FALSE = auto()
    NIL = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    # Symbols
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    EQEQ = auto()
    BANGEQ = auto()
    LT = auto()
    LTEQ = auto()
    GT = auto()
    GTEQ = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    DOT = auto()
    NEWLINE = auto()
    EOF = auto()


KEYWORDS = {
    "let": TokenType.LET,
    "func": TokenType.FUNC,
    "return": TokenType.RETURN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "nil": TokenType.NIL,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
}


@dataclass
class Token:
    type: TokenType
    lexeme: str
    literal: object
    line: int


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.tokens: list[Token] = []
        self.start = 0
        self.current = 0
        self.line = 1

    def tokenize(self) -> list[Token]:
        while not self._at_end():
            self.start = self.current
            self._scan_token()
        self.tokens.append(Token(TokenType.EOF, "", None, self.line))
        return self.tokens

    def _at_end(self) -> bool:
        return self.current >= len(self.source)

    def _advance(self) -> str:
        c = self.source[self.current]
        self.current += 1
        return c

    def _peek(self) -> str:
        if self._at_end():
            return "\0"
        return self.source[self.current]

    def _peek_next(self) -> str:
        if self.current + 1 >= len(self.source):
            return "\0"
        return self.source[self.current + 1]

    def _match(self, expected: str) -> bool:
        if self._at_end() or self.source[self.current] != expected:
            return False
        self.current += 1
        return True

    def _add_token(self, type_: TokenType, literal: object = None):
        lexeme = self.source[self.start:self.current]
        self.tokens.append(Token(type_, lexeme, literal, self.line))

    def _scan_token(self):
        c = self._advance()

        if c in " \t\r":
            return
        if c == "\n":
            self._add_token(TokenType.NEWLINE)
            self.line += 1
            return
        if c == "#":
            while self._peek() != "\n" and not self._at_end():
                self._advance()
            return

        if c == "+":
            self._add_token(TokenType.PLUS)
        elif c == "-":
            self._add_token(TokenType.MINUS)
        elif c == "*":
            self._add_token(TokenType.STAR)
        elif c == "/":
            self._add_token(TokenType.SLASH)
        elif c == "%":
            self._add_token(TokenType.PERCENT)
        elif c == "(":
            self._add_token(TokenType.LPAREN)
        elif c == ")":
            self._add_token(TokenType.RPAREN)
        elif c == "{":
            self._add_token(TokenType.LBRACE)
        elif c == "}":
            self._add_token(TokenType.RBRACE)
        elif c == "[":
            self._add_token(TokenType.LBRACKET)
        elif c == "]":
            self._add_token(TokenType.RBRACKET)
        elif c == ",":
            self._add_token(TokenType.COMMA)
        elif c == ":":
            self._add_token(TokenType.COLON)
        elif c == ";":
            self._add_token(TokenType.SEMICOLON)
        elif c == ".":
            self._add_token(TokenType.DOT)
        elif c == "=":
            self._add_token(TokenType.EQEQ if self._match("=") else TokenType.EQ)
        elif c == "!":
            if self._match("="):
                self._add_token(TokenType.BANGEQ)
            else:
                raise BoltSyntaxError(f"Unexpected character '!'", self.line)
        elif c == "<":
            self._add_token(TokenType.LTEQ if self._match("=") else TokenType.LT)
        elif c == ">":
            self._add_token(TokenType.GTEQ if self._match("=") else TokenType.GT)
        elif c == '"':
            self._string()
        elif c.isdigit():
            self._number()
        elif c.isalpha() or c == "_":
            self._identifier()
        else:
            raise BoltSyntaxError(f"Unexpected character '{c}'", self.line)

    def _string(self):
        value_chars = []
        start_line = self.line
        while self._peek() != '"' and not self._at_end():
            ch = self._advance()
            if ch == "\n":
                self.line += 1
                value_chars.append(ch)
            elif ch == "\\":
                esc = self._advance()
                mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}
                value_chars.append(mapping.get(esc, esc))
            else:
                value_chars.append(ch)

        if self._at_end():
            raise BoltSyntaxError("Unterminated string", start_line)

        self._advance()  # closing quote
        self._add_token(TokenType.STRING, "".join(value_chars))

    def _number(self):
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek_next().isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.source[self.start:self.current]
        self._add_token(TokenType.NUMBER, float(text) if is_float else int(text))

    def _identifier(self):
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[self.start:self.current]
        type_ = KEYWORDS.get(text, TokenType.IDENTIFIER)
        if type_ == TokenType.TRUE:
            self._add_token(type_, True)
        elif type_ == TokenType.FALSE:
            self._add_token(type_, False)
        else:
            self._add_token(type_)
