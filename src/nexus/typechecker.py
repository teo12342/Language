"""A gradual, best-effort static type checker for Nexus.

Only annotated code is checked. Anything without a type annotation is
treated as `any` and is never flagged - existing untyped Nexus programs
type-check with zero errors. Checks mirror the actual runtime semantics
in interpreter.py/vm.py (e.g. `+` allows string/number mixing because the
runtime auto-stringifies), so a typed program that type-checks will not
then fail at runtime with a *type* error.
"""

from dataclasses import dataclass, field

from .ast_nodes import (
    Assign, Binary, Block, BreakStmt, Call, ContinueStmt, Expr, ExprStmt,
    ForStmt, FuncExpr, FuncStmt, GetAttr, IfStmt, Index, LetStmt, ListLiteral,
    Literal, Logical, MapLiteral, ReturnStmt, Stmt, Unary, Variable, WhileStmt,
)
from .errors import NexusTypeError

ANY = "any"
KNOWN_TYPES = {"number", "string", "bool", "nil", "list", "map", "func", "tensor", ANY}

_NUMBER_OPS = {"-", "*", "/", "%"}
_COMPARE_OPS = {"<", "<=", ">", ">="}


def _literal_type(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "nil"
    return ANY


def _compatible(declared: str, actual: str) -> bool:
    return declared == ANY or actual == ANY or declared == actual


@dataclass
class FuncSig:
    param_types: list[str]
    return_type: str
    arity: int


class Scope:
    def __init__(self, parent: "Scope | None" = None):
        self.parent = parent
        self.vars: dict[str, str] = {}

    def declare(self, name: str, type_: str):
        self.vars[name] = type_

    def lookup(self, name: str) -> str:
        scope = self
        while scope is not None:
            if name in scope.vars:
                return scope.vars[name]
            scope = scope.parent
        return ANY


class TypeChecker:
    def __init__(self):
        self.functions: dict[str, FuncSig] = {}
        self.return_type_stack: list[str] = []

    def check(self, statements: list[Stmt]):
        scope = Scope()
        for stmt in statements:
            self._stmt(stmt, scope)

    # ---- statements ----

    def _stmt(self, stmt: Stmt, scope: Scope):
        getattr(self, f"_stmt_{type(stmt).__name__}")(stmt, scope)

    def _stmt_ExprStmt(self, stmt: ExprStmt, scope: Scope):
        self._expr(stmt.expr, scope)

    def _stmt_LetStmt(self, stmt: LetStmt, scope: Scope):
        value_type = self._expr(stmt.initializer, scope) if stmt.initializer else "nil"
        declared = stmt.type_annotation
        if declared is not None:
            if declared not in KNOWN_TYPES:
                raise NexusTypeError(f"Unknown type '{declared}'", stmt.line)
            if not _compatible(declared, value_type):
                raise NexusTypeError(
                    f"Cannot assign {value_type} to '{stmt.name}' declared as {declared}",
                    stmt.line,
                )
            scope.declare(stmt.name, declared)
        else:
            # No annotation: stays fully dynamic, even if the initializer
            # happens to have a known type - unannotated `let` can be
            # reassigned to any type, matching the untyped-v1 semantics.
            scope.declare(stmt.name, ANY)

    def _stmt_FuncStmt(self, stmt: FuncStmt, scope: Scope):
        self._register_and_check_function(
            stmt.name, stmt.params, stmt.param_types, stmt.return_type, stmt.body, scope, stmt.line,
        )

    def _stmt_ReturnStmt(self, stmt: ReturnStmt, scope: Scope):
        value_type = self._expr(stmt.value, scope) if stmt.value is not None else "nil"
        if self.return_type_stack:
            expected = self.return_type_stack[-1]
            if expected is not None and not _compatible(expected, value_type):
                raise NexusTypeError(
                    f"Function declared to return {expected} but returned {value_type}",
                    stmt.line,
                )

    def _stmt_IfStmt(self, stmt: IfStmt, scope: Scope):
        self._expr(stmt.condition, scope)
        inner = Scope(scope)
        for s in stmt.then_branch:
            self._stmt(s, inner)
        if stmt.else_branch is not None:
            inner2 = Scope(scope)
            for s in stmt.else_branch:
                self._stmt(s, inner2)

    def _stmt_WhileStmt(self, stmt: WhileStmt, scope: Scope):
        self._expr(stmt.condition, scope)
        inner = Scope(scope)
        for s in stmt.body:
            self._stmt(s, inner)

    def _stmt_ForStmt(self, stmt: ForStmt, scope: Scope):
        self._expr(stmt.iterable, scope)
        inner = Scope(scope)
        inner.declare(stmt.var_name, ANY)
        for s in stmt.body:
            self._stmt(s, inner)

    def _stmt_BreakStmt(self, stmt: BreakStmt, scope: Scope):
        pass

    def _stmt_ContinueStmt(self, stmt: ContinueStmt, scope: Scope):
        pass

    def _stmt_Block(self, stmt: Block, scope: Scope):
        inner = Scope(scope)
        for s in stmt.statements:
            self._stmt(s, inner)

    # ---- function helpers ----

    def _register_and_check_function(self, name, params, param_types, return_type, body, scope, line):
        types = [t if t is not None else ANY for t in (param_types or [None] * len(params))]
        for t in types:
            if t not in KNOWN_TYPES:
                raise NexusTypeError(f"Unknown type '{t}'", line)
        if return_type is not None and return_type not in KNOWN_TYPES:
            raise NexusTypeError(f"Unknown type '{return_type}'", line)

        if name is not None:
            self.functions[name] = FuncSig(types, return_type or ANY, len(params))
            scope.declare(name, "func")

        inner = Scope(scope)
        for p, t in zip(params, types):
            inner.declare(p, t)
        self.return_type_stack.append(return_type)
        for s in body:
            self._stmt(s, inner)
        self.return_type_stack.pop()

    # ---- expressions ----

    def _expr(self, expr: Expr, scope: Scope) -> str:
        return getattr(self, f"_expr_{type(expr).__name__}")(expr, scope)

    def _expr_Literal(self, expr: Literal, scope: Scope) -> str:
        return _literal_type(expr.value)

    def _expr_ListLiteral(self, expr: ListLiteral, scope: Scope) -> str:
        for e in expr.elements:
            self._expr(e, scope)
        return "list"

    def _expr_MapLiteral(self, expr: MapLiteral, scope: Scope) -> str:
        for k, v in zip(expr.keys, expr.values):
            self._expr(k, scope)
            self._expr(v, scope)
        return "map"

    def _expr_Variable(self, expr: Variable, scope: Scope) -> str:
        return scope.lookup(expr.name)

    def _expr_Assign(self, expr: Assign, scope: Scope) -> str:
        value_type = self._expr(expr.value, scope)
        target = expr.target
        if isinstance(target, Variable):
            declared = scope.lookup(target.name)
            if declared != ANY and not _compatible(declared, value_type):
                raise NexusTypeError(
                    f"Cannot assign {value_type} to '{target.name}' declared as {declared}",
                    expr.line,
                )
        else:
            self._expr(target, scope)
        return value_type

    def _expr_Unary(self, expr: Unary, scope: Scope) -> str:
        right = self._expr(expr.right, scope)
        if expr.op == "-":
            if right not in (ANY, "number"):
                raise NexusTypeError(f"Cannot negate a {right}", expr.line)
            return "number"
        return "bool"

    def _expr_Logical(self, expr: Logical, scope: Scope) -> str:
        left = self._expr(expr.left, scope)
        right = self._expr(expr.right, scope)
        return left if left == right else ANY

    def _expr_Binary(self, expr: Binary, scope: Scope) -> str:
        left = self._expr(expr.left, scope)
        right = self._expr(expr.right, scope)
        op = expr.op

        if left == "tensor" or right == "tensor":
            # Tensor arithmetic (elementwise +-*/ against another tensor or
            # a scalar) is checked at runtime by tensor.py, not here.
            if op in ("+", "-", "*", "/") and (left in (ANY, "tensor", "number")) and (right in (ANY, "tensor", "number")):
                return "tensor"
            if op in _COMPARE_OPS or op in ("==", "!="):
                return "bool"

        if op == "+":
            if left == "string" or right == "string":
                return "string"
            if left == "list" and right == "list":
                return "list"
            if left in (ANY, "number") and right in (ANY, "number"):
                return "number"
            raise NexusTypeError(f"Cannot add {left} and {right}", expr.line)

        if op in _NUMBER_OPS:
            if left not in (ANY, "number") or right not in (ANY, "number"):
                raise NexusTypeError(f"Operator '{op}' requires numbers, got {left} and {right}", expr.line)
            return "number"

        if op in _COMPARE_OPS:
            if left not in (ANY, "number") or right not in (ANY, "number"):
                raise NexusTypeError(f"Operator '{op}' requires numbers, got {left} and {right}", expr.line)
            return "bool"

        return "bool"  # == / !=

    def _expr_Call(self, expr: Call, scope: Scope) -> str:
        arg_types = [self._expr(a, scope) for a in expr.args]
        if isinstance(expr.callee, Variable) and expr.callee.name in self.functions:
            sig = self.functions[expr.callee.name]
            if len(expr.args) != sig.arity:
                raise NexusTypeError(
                    f"Function '{expr.callee.name}' expected {sig.arity} argument(s) but got {len(expr.args)}",
                    expr.line,
                )
            for i, arg_type in enumerate(arg_types):
                expected = sig.param_types[i]
                if not _compatible(expected, arg_type):
                    raise NexusTypeError(
                        f"Argument {i + 1} to '{expr.callee.name}' expected {expected}, got {arg_type}",
                        expr.line,
                    )
            return sig.return_type
        self._expr(expr.callee, scope)
        return ANY

    def _expr_Index(self, expr: Index, scope: Scope) -> str:
        self._expr(expr.obj, scope)
        self._expr(expr.index, scope)
        return ANY

    def _expr_GetAttr(self, expr: GetAttr, scope: Scope) -> str:
        self._expr(expr.obj, scope)
        return ANY

    def _expr_FuncExpr(self, expr: FuncExpr, scope: Scope) -> str:
        self._register_and_check_function(
            expr.name, expr.params, expr.param_types, expr.return_type, expr.body, scope, expr.line,
        )
        return "func"


def check_types(statements: list[Stmt]):
    TypeChecker().check(statements)
