from dataclasses import dataclass, field


class Node:
    pass


class Expr(Node):
    pass


class Stmt(Node):
    pass


# ---- Expressions ----

@dataclass
class Literal(Expr):
    value: object
    line: int


@dataclass
class ListLiteral(Expr):
    elements: list[Expr]
    line: int


@dataclass
class MapLiteral(Expr):
    keys: list[Expr]
    values: list[Expr]
    line: int


@dataclass
class Variable(Expr):
    name: str
    line: int


@dataclass
class Assign(Expr):
    target: Expr
    value: Expr
    line: int


@dataclass
class Unary(Expr):
    op: str
    right: Expr
    line: int


@dataclass
class Binary(Expr):
    left: Expr
    op: str
    right: Expr
    line: int


@dataclass
class Logical(Expr):
    left: Expr
    op: str
    right: Expr
    line: int


@dataclass
class Call(Expr):
    callee: Expr
    args: list[Expr]
    line: int


@dataclass
class Index(Expr):
    obj: Expr
    index: Expr
    line: int


@dataclass
class GetAttr(Expr):
    obj: Expr
    name: str
    line: int


@dataclass
class FuncExpr(Expr):
    params: list[str]
    body: list[Stmt]
    line: int
    name: str | None = None
    param_types: list[str | None] = field(default_factory=list)
    return_type: str | None = None


# ---- Statements ----

@dataclass
class ExprStmt(Stmt):
    expr: Expr
    line: int


@dataclass
class LetStmt(Stmt):
    name: str
    initializer: Expr | None
    line: int
    type_annotation: str | None = None


@dataclass
class FuncStmt(Stmt):
    name: str
    params: list[str]
    body: list[Stmt]
    line: int
    param_types: list[str | None] = field(default_factory=list)
    return_type: str | None = None


@dataclass
class ReturnStmt(Stmt):
    value: Expr | None
    line: int


@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_branch: list[Stmt]
    else_branch: list[Stmt] | None
    line: int


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: list[Stmt]
    line: int


@dataclass
class ForStmt(Stmt):
    var_name: str
    iterable: Expr
    body: list[Stmt]
    line: int


@dataclass
class BreakStmt(Stmt):
    line: int


@dataclass
class ContinueStmt(Stmt):
    line: int


@dataclass
class Block(Stmt):
    statements: list[Stmt]
    line: int
