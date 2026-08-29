from .ast_nodes import (
    Assign, Binary, Block, BreakStmt, Call, ContinueStmt, Expr, ExprStmt,
    ForStmt, FuncExpr, FuncStmt, GetAttr, IfStmt, Index, LetStmt, ListLiteral,
    Literal, Logical, MapLiteral, ReturnStmt, Stmt, Unary, Variable, WhileStmt,
)
from .errors import BoltSyntaxError
from .lexer import Token, TokenType as T


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.current = 0

    # ---- helpers ----

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    def _at_end(self) -> bool:
        return self._peek().type == T.EOF

    def _advance(self) -> Token:
        if not self._at_end():
            self.current += 1
        return self._previous()

    def _check(self, type_: T) -> bool:
        if self._at_end():
            return type_ == T.EOF
        return self._peek().type == type_

    def _match(self, *types: T) -> bool:
        for t in types:
            if self._check(t):
                self._advance()
                return True
        return False

    def _consume(self, type_: T, message: str) -> Token:
        if self._check(type_):
            return self._advance()
        raise BoltSyntaxError(message, self._peek().line)

    def _skip_newlines(self):
        while self._match(T.NEWLINE, T.SEMICOLON):
            pass

    # ---- entry point ----

    def parse(self) -> list[Stmt]:
        statements = []
        self._skip_newlines()
        while not self._at_end():
            statements.append(self._declaration())
            self._skip_newlines()
        return statements

    # ---- statements ----

    def _declaration(self) -> Stmt:
        if self._match(T.LET):
            return self._let_statement()
        if self._match(T.FUNC):
            return self._func_statement()
        return self._statement()

    def _let_statement(self) -> Stmt:
        line = self._previous().line
        name = self._consume(T.IDENTIFIER, "Expected variable name after 'let'").lexeme
        type_annotation = None
        if self._match(T.COLON):
            type_annotation = self._consume(T.IDENTIFIER, "Expected type name after ':'").lexeme
        initializer = None
        if self._match(T.EQ):
            initializer = self._expression()
        self._end_statement()
        return LetStmt(name, initializer, line, type_annotation=type_annotation)

    def _func_statement(self) -> Stmt:
        line = self._previous().line
        name = self._consume(T.IDENTIFIER, "Expected function name").lexeme
        params, param_types = self._typed_param_list()
        return_type = None
        if self._match(T.COLON):
            return_type = self._consume(T.IDENTIFIER, "Expected return type after ':'").lexeme
        body = self._block()
        return FuncStmt(name, params, body, line, param_types=param_types, return_type=return_type)

    def _typed_param_list(self) -> tuple[list[str], list[str | None]]:
        self._consume(T.LPAREN, "Expected '(' after function name")
        params: list[str] = []
        param_types: list[str | None] = []
        if not self._check(T.RPAREN):
            while True:
                params.append(self._consume(T.IDENTIFIER, "Expected parameter name").lexeme)
                if self._match(T.COLON):
                    param_types.append(self._consume(T.IDENTIFIER, "Expected type name after ':'").lexeme)
                else:
                    param_types.append(None)
                if not self._match(T.COMMA):
                    break
        self._consume(T.RPAREN, "Expected ')' after parameters")
        return params, param_types

    def _block(self) -> list[Stmt]:
        self._consume(T.LBRACE, "Expected '{'")
        self._skip_newlines()
        statements = []
        while not self._check(T.RBRACE) and not self._at_end():
            statements.append(self._declaration())
            self._skip_newlines()
        self._consume(T.RBRACE, "Expected '}'")
        return statements

    def _statement(self) -> Stmt:
        if self._match(T.IF):
            return self._if_statement()
        if self._match(T.WHILE):
            return self._while_statement()
        if self._match(T.FOR):
            return self._for_statement()
        if self._match(T.RETURN):
            return self._return_statement()
        if self._match(T.BREAK):
            line = self._previous().line
            self._end_statement()
            return BreakStmt(line)
        if self._match(T.CONTINUE):
            line = self._previous().line
            self._end_statement()
            return ContinueStmt(line)
        if self._check(T.LBRACE):
            line = self._peek().line
            return Block(self._block(), line)
        return self._expr_statement()

    def _if_statement(self) -> Stmt:
        line = self._previous().line
        condition = self._expression()
        then_branch = self._block()
        else_branch = None
        self._skip_newlines_soft()
        if self._match(T.ELSE):
            if self._check(T.IF):
                self._advance()
                else_branch = [self._if_statement()]
            else:
                else_branch = self._block()
        return IfStmt(condition, then_branch, else_branch, line)

    def _skip_newlines_soft(self):
        # allow 'else' on the next line after a closing brace
        start = self.current
        while self._check(T.NEWLINE):
            self._advance()
        if not self._check(T.ELSE):
            self.current = start

    def _while_statement(self) -> Stmt:
        line = self._previous().line
        condition = self._expression()
        body = self._block()
        return WhileStmt(condition, body, line)

    def _for_statement(self) -> Stmt:
        line = self._previous().line
        var_name = self._consume(T.IDENTIFIER, "Expected loop variable name").lexeme
        self._consume(T.IN, "Expected 'in' after loop variable")
        iterable = self._expression()
        body = self._block()
        return ForStmt(var_name, iterable, body, line)

    def _return_statement(self) -> Stmt:
        line = self._previous().line
        value = None
        if not self._check(T.NEWLINE) and not self._check(T.SEMICOLON) and not self._check(T.RBRACE):
            value = self._expression()
        self._end_statement()
        return ReturnStmt(value, line)

    def _expr_statement(self) -> Stmt:
        line = self._peek().line
        expr = self._expression()
        self._end_statement()
        return ExprStmt(expr, line)

    def _end_statement(self):
        if self._at_end() or self._check(T.RBRACE):
            return
        if not self._match(T.NEWLINE, T.SEMICOLON):
            raise BoltSyntaxError("Expected end of statement", self._peek().line)
        self._skip_newlines()

    # ---- expressions (precedence climbing) ----

    def _expression(self) -> Expr:
        return self._assignment()

    def _assignment(self) -> Expr:
        expr = self._or()
        if self._match(T.EQ):
            line = self._previous().line
            value = self._assignment()
            if isinstance(expr, (Variable, Index, GetAttr)):
                return Assign(expr, value, line)
            raise BoltSyntaxError("Invalid assignment target", line)
        return expr

    def _or(self) -> Expr:
        expr = self._and()
        while self._match(T.OR):
            line = self._previous().line
            right = self._and()
            expr = Logical(expr, "or", right, line)
        return expr

    def _and(self) -> Expr:
        expr = self._equality()
        while self._match(T.AND):
            line = self._previous().line
            right = self._equality()
            expr = Logical(expr, "and", right, line)
        return expr

    def _equality(self) -> Expr:
        expr = self._comparison()
        while self._match(T.EQEQ, T.BANGEQ):
            op = self._previous()
            right = self._comparison()
            expr = Binary(expr, op.lexeme, right, op.line)
        return expr

    def _comparison(self) -> Expr:
        expr = self._term()
        while self._match(T.LT, T.LTEQ, T.GT, T.GTEQ):
            op = self._previous()
            right = self._term()
            expr = Binary(expr, op.lexeme, right, op.line)
        return expr

    def _term(self) -> Expr:
        expr = self._factor()
        while self._match(T.PLUS, T.MINUS):
            op = self._previous()
            right = self._factor()
            expr = Binary(expr, op.lexeme, right, op.line)
        return expr

    def _factor(self) -> Expr:
        expr = self._unary()
        while self._match(T.STAR, T.SLASH, T.PERCENT):
            op = self._previous()
            right = self._unary()
            expr = Binary(expr, op.lexeme, right, op.line)
        return expr

    def _unary(self) -> Expr:
        if self._match(T.NOT, T.MINUS):
            op = self._previous()
            right = self._unary()
            return Unary(op.lexeme, right, op.line)
        return self._call()

    def _call(self) -> Expr:
        expr = self._primary()
        while True:
            if self._match(T.LPAREN):
                expr = self._finish_call(expr)
            elif self._match(T.LBRACKET):
                line = self._previous().line
                index = self._expression()
                self._consume(T.RBRACKET, "Expected ']' after index")
                expr = Index(expr, index, line)
            elif self._match(T.DOT):
                line = self._previous().line
                name = self._consume(T.IDENTIFIER, "Expected property name after '.'").lexeme
                expr = GetAttr(expr, name, line)
            else:
                break
        return expr

    def _finish_call(self, callee: Expr) -> Expr:
        line = self._previous().line
        args = []
        if not self._check(T.RPAREN):
            while True:
                args.append(self._expression())
                if not self._match(T.COMMA):
                    break
        self._consume(T.RPAREN, "Expected ')' after arguments")
        return Call(callee, args, line)

    def _primary(self) -> Expr:
        tok = self._peek()

        if self._match(T.NUMBER, T.STRING, T.TRUE, T.FALSE):
            return Literal(self._previous().literal, tok.line)
        if self._match(T.NIL):
            return Literal(None, tok.line)
        if self._match(T.IDENTIFIER):
            return Variable(self._previous().lexeme, tok.line)
        if self._match(T.FUNC):
            params, param_types = self._typed_param_list()
            return_type = None
            if self._match(T.COLON):
                return_type = self._consume(T.IDENTIFIER, "Expected return type after ':'").lexeme
            body = self._block()
            return FuncExpr(params, body, tok.line, param_types=param_types, return_type=return_type)
        if self._match(T.LPAREN):
            expr = self._expression()
            self._consume(T.RPAREN, "Expected ')' after expression")
            return expr
        if self._match(T.LBRACKET):
            elements = []
            self._skip_newlines()
            if not self._check(T.RBRACKET):
                while True:
                    self._skip_newlines()
                    elements.append(self._expression())
                    self._skip_newlines()
                    if not self._match(T.COMMA):
                        break
                    self._skip_newlines()
            self._skip_newlines()
            self._consume(T.RBRACKET, "Expected ']' after list elements")
            return ListLiteral(elements, tok.line)
        if self._match(T.LBRACE):
            keys, values = [], []
            self._skip_newlines()
            if not self._check(T.RBRACE):
                while True:
                    self._skip_newlines()
                    keys.append(self._expression())
                    self._consume(T.COLON, "Expected ':' after map key")
                    values.append(self._expression())
                    self._skip_newlines()
                    if not self._match(T.COMMA):
                        break
                    self._skip_newlines()
            self._skip_newlines()
            self._consume(T.RBRACE, "Expected '}' after map entries")
            return MapLiteral(keys, values, tok.line)

        raise BoltSyntaxError(f"Unexpected token '{tok.lexeme}'", tok.line)
