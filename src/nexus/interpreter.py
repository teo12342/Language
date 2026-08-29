from .ast_nodes import (
    Assign, Binary, Block, BreakStmt, Call, ContinueStmt, ExprStmt, ForStmt,
    FuncExpr, FuncStmt, GetAttr, IfStmt, Index, LetStmt, ListLiteral, Literal,
    Logical, MapLiteral, ReturnStmt, Unary, Variable, WhileStmt,
)
from .errors import NexusRuntimeError


class Environment:
    __slots__ = ("values", "parent")

    def __init__(self, parent: "Environment | None" = None):
        self.values: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value: object):
        self.values[name] = value

    def get(self, name: str, line: int):
        env = self
        while env is not None:
            if name in env.values:
                return env.values[name]
            env = env.parent
        raise NexusRuntimeError(f"Undefined variable '{name}'", line)

    def set(self, name: str, value: object, line: int):
        env = self
        while env is not None:
            if name in env.values:
                env.values[name] = value
                return
            env = env.parent
        raise NexusRuntimeError(f"Undefined variable '{name}'", line)


class NexusFunction:
    def __init__(self, name, params, body, closure: Environment):
        self.name = name
        self.params = params
        self.body = body
        self.closure = closure

    def call(self, interpreter: "Interpreter", args: list, line: int):
        if len(args) != len(self.params):
            raise NexusRuntimeError(
                f"Function '{self.name or '<anonymous>'}' expected {len(self.params)} "
                f"argument(s) but got {len(args)}",
                line,
            )
        env = Environment(self.closure)
        for param, arg in zip(self.params, args):
            env.define(param, arg)
        try:
            interpreter._exec_block(self.body, env)
        except _ReturnSignal as r:
            return r.value
        return None

    def __repr__(self):
        return f"<func {self.name or 'anonymous'}>"


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class Interpreter:
    def __init__(self, builtins: dict[str, object] | None = None):
        self.globals = Environment()
        for name, fn in (builtins or {}).items():
            self.globals.define(name, fn)

    def run(self, statements: list):
        self._exec_block(statements, self.globals)

    # ---- statement execution ----

    def _exec_block(self, statements: list, env: Environment):
        for stmt in statements:
            self._execute(stmt, env)

    def _execute(self, stmt, env: Environment):
        method = getattr(self, f"_stmt_{type(stmt).__name__}")
        method(stmt, env)

    def _stmt_ExprStmt(self, stmt: ExprStmt, env: Environment):
        self._evaluate(stmt.expr, env)

    def _stmt_LetStmt(self, stmt: LetStmt, env: Environment):
        value = self._evaluate(stmt.initializer, env) if stmt.initializer else None
        env.define(stmt.name, value)

    def _stmt_FuncStmt(self, stmt: FuncStmt, env: Environment):
        func = NexusFunction(stmt.name, stmt.params, stmt.body, env)
        env.define(stmt.name, func)

    def _stmt_ReturnStmt(self, stmt: ReturnStmt, env: Environment):
        value = self._evaluate(stmt.value, env) if stmt.value else None
        raise _ReturnSignal(value)

    def _stmt_IfStmt(self, stmt: IfStmt, env: Environment):
        if _is_truthy(self._evaluate(stmt.condition, env)):
            self._exec_block(stmt.then_branch, Environment(env))
        elif stmt.else_branch is not None:
            self._exec_block(stmt.else_branch, Environment(env))

    def _stmt_WhileStmt(self, stmt: WhileStmt, env: Environment):
        while _is_truthy(self._evaluate(stmt.condition, env)):
            try:
                self._exec_block(stmt.body, Environment(env))
            except _BreakSignal:
                break
            except _ContinueSignal:
                continue

    def _stmt_ForStmt(self, stmt: ForStmt, env: Environment):
        iterable = self._evaluate(stmt.iterable, env)
        try:
            items = iter(iterable)
        except TypeError:
            raise NexusRuntimeError(f"Value is not iterable", stmt.line)
        for item in items:
            loop_env = Environment(env)
            loop_env.define(stmt.var_name, item)
            try:
                self._exec_block(stmt.body, loop_env)
            except _BreakSignal:
                break
            except _ContinueSignal:
                continue

    def _stmt_BreakStmt(self, stmt: BreakStmt, env: Environment):
        raise _BreakSignal()

    def _stmt_ContinueStmt(self, stmt: ContinueStmt, env: Environment):
        raise _ContinueSignal()

    def _stmt_Block(self, stmt: Block, env: Environment):
        self._exec_block(stmt.statements, Environment(env))

    # ---- expression evaluation ----

    def _evaluate(self, expr, env: Environment):
        method = getattr(self, f"_expr_{type(expr).__name__}")
        return method(expr, env)

    def _expr_Literal(self, expr: Literal, env: Environment):
        return expr.value

    def _expr_ListLiteral(self, expr: ListLiteral, env: Environment):
        return [self._evaluate(e, env) for e in expr.elements]

    def _expr_MapLiteral(self, expr: MapLiteral, env: Environment):
        return {
            self._evaluate(k, env): self._evaluate(v, env)
            for k, v in zip(expr.keys, expr.values)
        }

    def _expr_Variable(self, expr: Variable, env: Environment):
        return env.get(expr.name, expr.line)

    def _expr_Assign(self, expr: Assign, env: Environment):
        value = self._evaluate(expr.value, env)
        target = expr.target
        if isinstance(target, Variable):
            env.set(target.name, value, expr.line)
        elif isinstance(target, Index):
            obj = self._evaluate(target.obj, env)
            key = self._evaluate(target.index, env)
            try:
                obj[key] = value
            except (TypeError, IndexError) as e:
                raise NexusRuntimeError(str(e), expr.line)
        elif isinstance(target, GetAttr):
            obj = self._evaluate(target.obj, env)
            if isinstance(obj, dict):
                obj[target.name] = value
            else:
                raise NexusRuntimeError("Cannot set attribute on this value", expr.line)
        else:
            raise NexusRuntimeError("Invalid assignment target", expr.line)
        return value

    def _expr_Unary(self, expr: Unary, env: Environment):
        right = self._evaluate(expr.right, env)
        if expr.op == "-":
            _check_number(right, expr.line)
            return -right
        if expr.op == "not":
            return not _is_truthy(right)
        raise NexusRuntimeError(f"Unknown unary operator '{expr.op}'", expr.line)

    def _expr_Logical(self, expr: Logical, env: Environment):
        left = self._evaluate(expr.left, env)
        if expr.op == "or":
            if _is_truthy(left):
                return left
            return self._evaluate(expr.right, env)
        else:  # and
            if not _is_truthy(left):
                return left
            return self._evaluate(expr.right, env)

    def _expr_Binary(self, expr: Binary, env: Environment):
        left = self._evaluate(expr.left, env)
        right = self._evaluate(expr.right, env)
        op = expr.op
        line = expr.line

        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return _stringify(left) + _stringify(right)
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            _check_numbers(left, right, line)
            return left + right
        if op == "-":
            _check_numbers(left, right, line)
            return left - right
        if op == "*":
            _check_numbers(left, right, line)
            return left * right
        if op == "/":
            _check_numbers(left, right, line)
            if right == 0:
                raise NexusRuntimeError("Division by zero", line)
            result = left / right
            return result
        if op == "%":
            _check_numbers(left, right, line)
            if right == 0:
                raise NexusRuntimeError("Modulo by zero", line)
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            _check_numbers(left, right, line)
            return left < right
        if op == "<=":
            _check_numbers(left, right, line)
            return left <= right
        if op == ">":
            _check_numbers(left, right, line)
            return left > right
        if op == ">=":
            _check_numbers(left, right, line)
            return left >= right
        raise NexusRuntimeError(f"Unknown operator '{op}'", line)

    def _expr_Call(self, expr: Call, env: Environment):
        callee = self._evaluate(expr.callee, env)
        args = [self._evaluate(a, env) for a in expr.args]
        if isinstance(callee, NexusFunction):
            return callee.call(self, args, expr.line)
        if callable(callee):
            try:
                return callee(*args)
            except NexusRuntimeError:
                raise
            except Exception as e:
                raise NexusRuntimeError(str(e), expr.line)
        raise NexusRuntimeError("Value is not callable", expr.line)

    def _expr_Index(self, expr: Index, env: Environment):
        obj = self._evaluate(expr.obj, env)
        key = self._evaluate(expr.index, env)
        try:
            return obj[key]
        except (KeyError, IndexError):
            raise NexusRuntimeError(f"Index/key {key!r} not found", expr.line)
        except TypeError as e:
            raise NexusRuntimeError(str(e), expr.line)

    def _expr_GetAttr(self, expr: GetAttr, env: Environment):
        obj = self._evaluate(expr.obj, env)
        if isinstance(obj, dict) and expr.name in obj:
            return obj[expr.name]
        raise NexusRuntimeError(f"No attribute '{expr.name}'", expr.line)

    def _expr_FuncExpr(self, expr: FuncExpr, env: Environment):
        return NexusFunction(expr.name, expr.params, expr.body, env)


def _is_truthy(value) -> bool:
    if value is None or value is False:
        return False
    if value == 0:
        return False
    if value == "":
        return False
    return True


def _check_number(value, line):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise NexusRuntimeError(f"Expected a number, got {type(value).__name__}", line)


def _check_numbers(left, right, line):
    _check_number(left, line)
    _check_number(right, line)


def _stringify(value) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)
