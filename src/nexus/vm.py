from . import bytecode as B
from .bytecode import FunctionProto
from .errors import NexusRuntimeError
from .interpreter import _check_numbers, _check_number, _is_truthy, _stringify
from .tensor import Tensor


class Cell:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class Closure:
    __slots__ = ("proto", "upvalues")

    def __init__(self, proto: FunctionProto, upvalues: list[Cell]):
        self.proto = proto
        self.upvalues = upvalues

    def __repr__(self):
        return f"<func {self.proto.name or 'anonymous'}>"


class VM:
    def __init__(self, builtins: dict[str, object] | None = None, native: dict[str, object] | None = None):
        self._native = native or {}
        self.globals: dict[str, object] = dict(builtins or {})
        self.globals.update(self._native)

    def run_program(self, script_proto: FunctionProto):
        self._run(script_proto, [], [])

    def call_closure(self, closure: Closure, args: list, line: int):
        if len(args) != closure.proto.arity:
            raise NexusRuntimeError(
                f"Function '{closure.proto.name or '<anonymous>'}' expected "
                f"{closure.proto.arity} argument(s) but got {len(args)}",
                line,
            )
        return self._run(closure.proto, args, closure.upvalues)

    def _run(self, proto: FunctionProto, args: list, upvalues: list[Cell]):
        locals_: list[Cell | None] = [Cell(a) for a in args]
        locals_.extend([None] * (proto.num_locals - len(args)))
        code = proto.chunk.code
        constants = proto.chunk.constants
        stack: list = []
        ip = 0

        while True:
            op, arg, line = code[ip]
            ip += 1

            if op == B.GET_LOCAL:
                stack.append(locals_[arg].value)
            elif op == B.CONST:
                stack.append(constants[arg])
            elif op == B.CALL:
                argc = arg
                if argc:
                    call_args = stack[-argc:]
                    del stack[-argc:]
                else:
                    call_args = []
                callee = stack.pop()
                if isinstance(callee, Closure):
                    result = self.call_closure(callee, call_args, line)
                elif callable(callee):
                    try:
                        result = callee(*call_args)
                    except NexusRuntimeError:
                        raise
                    except Exception as e:
                        raise NexusRuntimeError(str(e), line)
                else:
                    raise NexusRuntimeError("Value is not callable", line)
                stack.append(result)
            elif op == B.ADD:
                b_ = stack.pop()
                a_ = stack.pop()
                if isinstance(a_, Tensor) or isinstance(b_, Tensor):
                    try:
                        stack.append(a_ + b_)
                    except (ValueError, TypeError) as e:
                        raise NexusRuntimeError(str(e), line)
                elif isinstance(a_, str) or isinstance(b_, str):
                    stack.append(_stringify(a_) + _stringify(b_))
                elif isinstance(a_, list) and isinstance(b_, list):
                    stack.append(a_ + b_)
                else:
                    _check_numbers(a_, b_, line)
                    stack.append(a_ + b_)
            elif op == B.SUB:
                b_ = stack.pop(); a_ = stack.pop()
                if isinstance(a_, Tensor) or isinstance(b_, Tensor):
                    try:
                        stack.append(a_ - b_)
                    except (ValueError, TypeError) as e:
                        raise NexusRuntimeError(str(e), line)
                else:
                    _check_numbers(a_, b_, line)
                    stack.append(a_ - b_)
            elif op == B.MUL:
                b_ = stack.pop(); a_ = stack.pop()
                if isinstance(a_, Tensor) or isinstance(b_, Tensor):
                    try:
                        stack.append(a_ * b_)
                    except (ValueError, TypeError) as e:
                        raise NexusRuntimeError(str(e), line)
                else:
                    _check_numbers(a_, b_, line)
                    stack.append(a_ * b_)
            elif op == B.LT:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                stack.append(a_ < b_)
            elif op == B.GT:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                stack.append(a_ > b_)
            elif op == B.SET_LOCAL:
                locals_[arg].value = stack[-1]
            elif op == B.INIT_LOCAL:
                locals_[arg] = Cell(stack.pop())
            elif op == B.JUMP:
                ip = arg
            elif op == B.JUMP_IF_FALSE_POP:
                if not _is_truthy(stack.pop()):
                    ip = arg
            elif op == B.RETURN:
                return stack.pop()
            elif op == B.POP:
                stack.pop()
            elif op == B.GET_GLOBAL:
                if arg not in self.globals:
                    raise NexusRuntimeError(f"Undefined variable '{arg}'", line)
                stack.append(self.globals[arg])
            elif op == B.SET_GLOBAL:
                if arg not in self.globals:
                    raise NexusRuntimeError(f"Undefined variable '{arg}'", line)
                self.globals[arg] = stack[-1]
            elif op == B.DEFINE_GLOBAL:
                value = stack.pop()
                if arg not in self._native:
                    self.globals[arg] = value
            elif op == B.GET_UPVALUE:
                stack.append(upvalues[arg].value)
            elif op == B.SET_UPVALUE:
                upvalues[arg].value = stack[-1]
            elif op == B.EQ:
                b_ = stack.pop(); a_ = stack.pop()
                stack.append(a_ == b_)
            elif op == B.NEQ:
                b_ = stack.pop(); a_ = stack.pop()
                stack.append(a_ != b_)
            elif op == B.LTE:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                stack.append(a_ <= b_)
            elif op == B.GTE:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                stack.append(a_ >= b_)
            elif op == B.DIV:
                b_ = stack.pop(); a_ = stack.pop()
                if isinstance(a_, Tensor) or isinstance(b_, Tensor):
                    try:
                        stack.append(a_ / b_)
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        raise NexusRuntimeError(str(e), line)
                    continue
                _check_numbers(a_, b_, line)
                if b_ == 0:
                    raise NexusRuntimeError("Division by zero", line)
                stack.append(a_ / b_)
            elif op == B.MOD:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                if b_ == 0:
                    raise NexusRuntimeError("Modulo by zero", line)
                stack.append(a_ % b_)
            elif op == B.NEG:
                v = stack.pop()
                _check_number(v, line)
                stack.append(-v)
            elif op == B.NOT:
                stack.append(not _is_truthy(stack.pop()))
            elif op == B.JUMP_IF_FALSE_PEEK:
                if not _is_truthy(stack[-1]):
                    ip = arg
            elif op == B.JUMP_IF_TRUE_PEEK:
                if _is_truthy(stack[-1]):
                    ip = arg
            elif op == B.BUILD_LIST:
                n = arg
                if n:
                    items = stack[-n:]
                    del stack[-n:]
                else:
                    items = []
                stack.append(list(items))
            elif op == B.BUILD_MAP:
                n = arg
                if n:
                    items = stack[-2 * n:]
                    del stack[-2 * n:]
                else:
                    items = []
                d = {}
                for i in range(0, len(items), 2):
                    d[items[i]] = items[i + 1]
                stack.append(d)
            elif op == B.GET_INDEX:
                key = stack.pop()
                obj = stack.pop()
                try:
                    stack.append(obj[key])
                except (KeyError, IndexError):
                    raise NexusRuntimeError(f"Index/key {key!r} not found", line)
                except TypeError as e:
                    raise NexusRuntimeError(str(e), line)
            elif op == B.SET_INDEX:
                value = stack.pop()
                key = stack.pop()
                obj = stack.pop()
                try:
                    obj[key] = value
                except (TypeError, IndexError) as e:
                    raise NexusRuntimeError(str(e), line)
                stack.append(value)
            elif op == B.GET_ATTR:
                obj = stack.pop()
                if isinstance(obj, dict) and arg in obj:
                    stack.append(obj[arg])
                else:
                    raise NexusRuntimeError(f"No attribute '{arg}'", line)
            elif op == B.SET_ATTR:
                value = stack.pop()
                obj = stack.pop()
                if isinstance(obj, dict):
                    obj[arg] = value
                else:
                    raise NexusRuntimeError("Cannot set attribute on this value", line)
                stack.append(value)
            elif op == B.GET_ITER:
                iterable = stack.pop()
                try:
                    stack.append(iter(iterable))
                except TypeError:
                    raise NexusRuntimeError("Value is not iterable", line)
            elif op == B.FOR_ITER:
                try:
                    stack.append(next(stack[-1]))
                except StopIteration:
                    stack.pop()
                    ip = arg
            elif op == B.CLOSURE:
                proto: FunctionProto = constants[arg]
                captured = []
                for is_local, index in proto.upvalue_specs:
                    if is_local:
                        captured.append(locals_[index])
                    else:
                        captured.append(upvalues[index])
                stack.append(Closure(proto, captured))
            else:
                raise NexusRuntimeError(f"Unknown opcode {op}", line)
