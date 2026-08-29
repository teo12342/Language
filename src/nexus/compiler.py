from dataclasses import dataclass, field, fields, is_dataclass

from . import bytecode as B
from .ast_nodes import (
    Assign, Binary, Block, BreakStmt, Call, ContinueStmt, Expr, ExprStmt,
    ForStmt, FuncExpr, FuncStmt, GetAttr, IfStmt, Index, LetStmt, ListLiteral,
    Literal, Logical, MapLiteral, ReturnStmt, Stmt, Unary, Variable, WhileStmt,
)
from .bytecode import Chunk, FunctionProto
from .errors import NexusSyntaxError

_BINARY_OPS = {
    "+": B.ADD, "-": B.SUB, "*": B.MUL, "/": B.DIV, "%": B.MOD,
    "==": B.EQ, "!=": B.NEQ, "<": B.LT, "<=": B.LTE, ">": B.GT, ">=": B.GTE,
}


def _collect_variable_names(node, out: set[str]):
    """Recursively collects every Variable node's name anywhere under `node`."""
    if isinstance(node, Variable):
        out.add(node.name)
    if is_dataclass(node):
        for f in fields(node):
            _collect_variable_names(getattr(node, f.name), out)
    elif isinstance(node, list):
        for item in node:
            _collect_variable_names(item, out)


def _collect_nested_functions(node, out: list):
    if isinstance(node, (FuncStmt, FuncExpr)):
        out.append(node)
    if is_dataclass(node):
        for f in fields(node):
            _collect_nested_functions(getattr(node, f.name), out)
    elif isinstance(node, list):
        for item in node:
            _collect_nested_functions(item, out)


def _captured_names(body: list[Stmt]) -> set[str]:
    """Names that MIGHT be captured by a closure defined anywhere inside `body`.

    Deliberately conservative (over-approximates rather than under-): a name
    referenced anywhere inside a nested function's own subtree counts, even
    if it's really that nested function's own param/local of the same name.
    A false positive here just means a slot gets boxed (in a Cell) when it
    didn't strictly need to be - safe. A false negative would break closures,
    so this never trims aggressively.
    """
    nested = []
    for stmt in body:
        _collect_nested_functions(stmt, nested)
    names: set[str] = set()
    for fn in nested:
        _collect_variable_names(fn.body, names)
    return names


@dataclass
class Local:
    name: str
    slot: int
    depth: int
    boxed: bool = True


@dataclass
class LoopCtx:
    continue_target: int
    breaks: list = field(default_factory=list)


class FuncCompilerCtx:
    def __init__(self, parent, name, is_script=False, captured_names: set[str] = frozenset()):
        self.parent = parent
        self.name = name
        self.is_script = is_script
        self.chunk = Chunk()
        self.locals: list[Local] = []
        self.scope_depth = 0
        self.next_slot = 0
        self.upvalues: list[tuple[bool, int]] = []
        self.loop_stack: list[LoopCtx] = []
        self.captured_names = captured_names

    def emit(self, op, arg=None, line=0):
        return self.chunk.emit(op, arg, line)


class Compiler:
    def compile_script(self, statements: list[Stmt]) -> FunctionProto:
        ctx = FuncCompilerCtx(
            parent=None, name="<script>", is_script=True,
            captured_names=_captured_names(statements),
        )
        for stmt in statements:
            self._stmt(ctx, stmt)
        ctx.emit(B.CONST, ctx.chunk.add_const(None), 0)
        ctx.emit(B.RETURN, None, 0)
        return FunctionProto("<script>", 0, ctx.chunk, [], ctx.next_slot, [])

    # ---- scope helpers ----

    def _begin_scope(self, ctx: FuncCompilerCtx):
        ctx.scope_depth += 1

    def _end_scope(self, ctx: FuncCompilerCtx):
        ctx.scope_depth -= 1
        while ctx.locals and ctx.locals[-1].depth > ctx.scope_depth:
            ctx.locals.pop()

    def _declare(self, ctx: FuncCompilerCtx, name: str):
        """Returns ('global', name) or ('local', slot)."""
        if ctx.is_script and ctx.scope_depth == 0:
            return ("global", name)
        slot = ctx.next_slot
        ctx.next_slot += 1
        boxed = name in ctx.captured_names
        ctx.locals.append(Local(name, slot, ctx.scope_depth, boxed=boxed))
        return ("local", slot)

    def _resolve_upvalue(self, ctx: FuncCompilerCtx, name: str):
        if ctx.parent is None:
            return None
        for local in reversed(ctx.parent.locals):
            if local.name == name:
                return self._add_upvalue(ctx, True, local.slot)
        up = self._resolve_upvalue(ctx.parent, name)
        if up is not None:
            return self._add_upvalue(ctx, False, up)
        return None

    def _add_upvalue(self, ctx: FuncCompilerCtx, is_local: bool, index: int) -> int:
        for i, (il, idx) in enumerate(ctx.upvalues):
            if il == is_local and idx == index:
                return i
        ctx.upvalues.append((is_local, index))
        return len(ctx.upvalues) - 1

    def _load_var(self, ctx: FuncCompilerCtx, name: str, line: int):
        for local in reversed(ctx.locals):
            if local.name == name:
                ctx.emit(B.GET_LOCAL if local.boxed else B.GET_LOCAL_RAW, local.slot, line)
                return
        up = self._resolve_upvalue(ctx, name)
        if up is not None:
            ctx.emit(B.GET_UPVALUE, up, line)
            return
        ctx.emit(B.GET_GLOBAL, name, line)

    def _store_var(self, ctx: FuncCompilerCtx, name: str, line: int):
        for local in reversed(ctx.locals):
            if local.name == name:
                ctx.emit(B.SET_LOCAL if local.boxed else B.SET_LOCAL_RAW, local.slot, line)
                return
        up = self._resolve_upvalue(ctx, name)
        if up is not None:
            ctx.emit(B.SET_UPVALUE, up, line)
            return
        ctx.emit(B.SET_GLOBAL, name, line)

    def _init_local(self, ctx: FuncCompilerCtx, slot: int, line: int):
        boxed = ctx.locals[-1].boxed  # the Local just declared for this slot
        ctx.emit(B.INIT_LOCAL if boxed else B.INIT_LOCAL_RAW, slot, line)

    # ---- statements ----

    def _stmt(self, ctx: FuncCompilerCtx, stmt: Stmt):
        getattr(self, f"_stmt_{type(stmt).__name__}")(ctx, stmt)

    def _stmt_ExprStmt(self, ctx, stmt: ExprStmt):
        self._expr(ctx, stmt.expr)
        ctx.emit(B.POP, None, stmt.line)

    def _stmt_LetStmt(self, ctx, stmt: LetStmt):
        if stmt.initializer is not None:
            self._expr(ctx, stmt.initializer)
        else:
            ctx.emit(B.CONST, ctx.chunk.add_const(None), stmt.line)
        kind, val = self._declare(ctx, stmt.name)
        if kind == "global":
            ctx.emit(B.DEFINE_GLOBAL, val, stmt.line)
        else:
            self._init_local(ctx, val, stmt.line)

    def _stmt_FuncStmt(self, ctx, stmt: FuncStmt):
        kind, val = self._declare(ctx, stmt.name)
        self._compile_function(ctx, stmt.name, stmt.params, stmt.body, stmt.line)
        if kind == "global":
            ctx.emit(B.DEFINE_GLOBAL, val, stmt.line)
        else:
            self._init_local(ctx, val, stmt.line)

    def _stmt_ReturnStmt(self, ctx, stmt: ReturnStmt):
        if stmt.value is not None:
            self._expr(ctx, stmt.value)
        else:
            ctx.emit(B.CONST, ctx.chunk.add_const(None), stmt.line)
        ctx.emit(B.RETURN, None, stmt.line)

    def _stmt_IfStmt(self, ctx, stmt: IfStmt):
        self._expr(ctx, stmt.condition)
        else_jump = ctx.emit(B.JUMP_IF_FALSE_POP, None, stmt.line)
        self._begin_scope(ctx)
        for s in stmt.then_branch:
            self._stmt(ctx, s)
        self._end_scope(ctx)
        if stmt.else_branch is not None:
            end_jump = ctx.emit(B.JUMP, None, stmt.line)
            ctx.chunk.patch(else_jump, len(ctx.chunk.code))
            self._begin_scope(ctx)
            for s in stmt.else_branch:
                self._stmt(ctx, s)
            self._end_scope(ctx)
            ctx.chunk.patch(end_jump, len(ctx.chunk.code))
        else:
            ctx.chunk.patch(else_jump, len(ctx.chunk.code))

    def _stmt_WhileStmt(self, ctx, stmt: WhileStmt):
        loop_start = len(ctx.chunk.code)
        self._expr(ctx, stmt.condition)
        exit_jump = ctx.emit(B.JUMP_IF_FALSE_POP, None, stmt.line)
        ctx.loop_stack.append(LoopCtx(continue_target=loop_start))
        self._begin_scope(ctx)
        for s in stmt.body:
            self._stmt(ctx, s)
        self._end_scope(ctx)
        loop = ctx.loop_stack.pop()
        ctx.emit(B.JUMP, loop_start, stmt.line)
        ctx.chunk.patch(exit_jump, len(ctx.chunk.code))
        for b in loop.breaks:
            ctx.chunk.patch(b, len(ctx.chunk.code))

    def _stmt_ForStmt(self, ctx, stmt: ForStmt):
        self._expr(ctx, stmt.iterable)
        ctx.emit(B.GET_ITER, None, stmt.line)
        loop_start = len(ctx.chunk.code)
        exit_jump = ctx.emit(B.FOR_ITER, None, stmt.line)
        self._begin_scope(ctx)
        kind, val = self._declare(ctx, stmt.var_name)
        self._init_local(ctx, val, stmt.line)
        ctx.loop_stack.append(LoopCtx(continue_target=loop_start))
        for s in stmt.body:
            self._stmt(ctx, s)
        loop = ctx.loop_stack.pop()
        self._end_scope(ctx)
        ctx.emit(B.JUMP, loop_start, stmt.line)
        ctx.chunk.patch(exit_jump, len(ctx.chunk.code))
        for b in loop.breaks:
            ctx.chunk.patch(b, len(ctx.chunk.code))

    def _stmt_BreakStmt(self, ctx, stmt: BreakStmt):
        if not ctx.loop_stack:
            raise NexusSyntaxError("'break' outside of a loop", stmt.line)
        idx = ctx.emit(B.JUMP, None, stmt.line)
        ctx.loop_stack[-1].breaks.append(idx)

    def _stmt_ContinueStmt(self, ctx, stmt: ContinueStmt):
        if not ctx.loop_stack:
            raise NexusSyntaxError("'continue' outside of a loop", stmt.line)
        ctx.emit(B.JUMP, ctx.loop_stack[-1].continue_target, stmt.line)

    def _stmt_Block(self, ctx, stmt: Block):
        self._begin_scope(ctx)
        for s in stmt.statements:
            self._stmt(ctx, s)
        self._end_scope(ctx)

    # ---- function/closure compilation ----

    def _compile_function(self, ctx: FuncCompilerCtx, name, params, body, line):
        fctx = FuncCompilerCtx(
            parent=ctx, name=name, is_script=False,
            captured_names=_captured_names(body),
        )
        for p in params:
            self._declare(fctx, p)
        param_boxed = [local.boxed for local in fctx.locals[:len(params)]]
        for s in body:
            self._stmt(fctx, s)
        fctx.emit(B.CONST, fctx.chunk.add_const(None), line)
        fctx.emit(B.RETURN, None, line)
        proto = FunctionProto(name, len(params), fctx.chunk, fctx.upvalues, fctx.next_slot, param_boxed)
        idx = ctx.chunk.add_const(proto)
        ctx.emit(B.CLOSURE, idx, line)

    # ---- expressions ----

    def _expr(self, ctx: FuncCompilerCtx, expr: Expr):
        getattr(self, f"_expr_{type(expr).__name__}")(ctx, expr)

    def _expr_Literal(self, ctx, expr: Literal):
        ctx.emit(B.CONST, ctx.chunk.add_const(expr.value), expr.line)

    def _expr_ListLiteral(self, ctx, expr: ListLiteral):
        for e in expr.elements:
            self._expr(ctx, e)
        ctx.emit(B.BUILD_LIST, len(expr.elements), expr.line)

    def _expr_MapLiteral(self, ctx, expr: MapLiteral):
        for k, v in zip(expr.keys, expr.values):
            self._expr(ctx, k)
            self._expr(ctx, v)
        ctx.emit(B.BUILD_MAP, len(expr.keys), expr.line)

    def _expr_Variable(self, ctx, expr: Variable):
        self._load_var(ctx, expr.name, expr.line)

    def _expr_Assign(self, ctx, expr: Assign):
        target = expr.target
        if isinstance(target, Variable):
            self._expr(ctx, expr.value)
            self._store_var(ctx, target.name, expr.line)
        elif isinstance(target, Index):
            self._expr(ctx, target.obj)
            self._expr(ctx, target.index)
            self._expr(ctx, expr.value)
            ctx.emit(B.SET_INDEX, None, expr.line)
        elif isinstance(target, GetAttr):
            self._expr(ctx, target.obj)
            self._expr(ctx, expr.value)
            ctx.emit(B.SET_ATTR, target.name, expr.line)
        else:
            raise NexusSyntaxError("Invalid assignment target", expr.line)

    def _expr_Unary(self, ctx, expr: Unary):
        self._expr(ctx, expr.right)
        ctx.emit(B.NEG if expr.op == "-" else B.NOT, None, expr.line)

    def _expr_Logical(self, ctx, expr: Logical):
        self._expr(ctx, expr.left)
        if expr.op == "and":
            jump = ctx.emit(B.JUMP_IF_FALSE_PEEK, None, expr.line)
        else:
            jump = ctx.emit(B.JUMP_IF_TRUE_PEEK, None, expr.line)
        ctx.emit(B.POP, None, expr.line)
        self._expr(ctx, expr.right)
        ctx.chunk.patch(jump, len(ctx.chunk.code))

    def _expr_Binary(self, ctx, expr: Binary):
        self._expr(ctx, expr.left)
        self._expr(ctx, expr.right)
        ctx.emit(_BINARY_OPS[expr.op], None, expr.line)

    def _expr_Call(self, ctx, expr: Call):
        self._expr(ctx, expr.callee)
        for a in expr.args:
            self._expr(ctx, a)
        ctx.emit(B.CALL, len(expr.args), expr.line)

    def _expr_Index(self, ctx, expr: Index):
        self._expr(ctx, expr.obj)
        self._expr(ctx, expr.index)
        ctx.emit(B.GET_INDEX, None, expr.line)

    def _expr_GetAttr(self, ctx, expr: GetAttr):
        self._expr(ctx, expr.obj)
        ctx.emit(B.GET_ATTR, expr.name, expr.line)

    def _expr_FuncExpr(self, ctx, expr: FuncExpr):
        self._compile_function(ctx, expr.name, expr.params, expr.body, expr.line)


def compile_program(statements: list[Stmt]) -> FunctionProto:
    return Compiler().compile_script(statements)
