from . import bytecode as B
from .bytecode import FunctionProto
from .errors import BoltRuntimeError
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
            raise BoltRuntimeError(
                f"Function '{closure.proto.name or '<anonymous>'}' expected "
                f"{closure.proto.arity} argument(s) but got {len(args)}",
                line,
            )
        return self._run(closure.proto, args, closure.upvalues)

    def _run(self, proto: FunctionProto, args: list, upvalues: list[Cell]):
        # A Bolt-to-Bolt call (the B.CALL branch below, when the callee is a
        # Closure) does NOT recurse into a nested Python call to _run - that
        # was the original design, and it meant every Bolt function call
        # paid a full Python stack-frame's overhead on top of bytecode
        # dispatch (measured: ~75% of fib(30)'s VM runtime was exactly this
        # recursive-call overhead, not the actual arithmetic). Instead, the
        # caller's frame state is saved onto `call_stack` (a plain Python
        # list acting as an explicit call stack, the same technique
        # CPython's and Lua's own eval loops use) and execution continues
        # in this same while-loop with the callee's state swapped in -
        # RETURN pops it back off. Calls that enter _run from Python (a
        # fresh script run, or a builtin like tmap()/serve() calling back
        # into Bolt code via call_closure) still go through a real Python
        # call as before; each such call gets its own local `call_stack`,
        # so those still nest/reenter correctly.
        locals_: list = [
            (Cell(a) if boxed else a) for a, boxed in zip(args, proto.param_boxed)
        ]
        locals_.extend([None] * (proto.num_locals - len(args)))
        code = proto.chunk.code
        constants = proto.chunk.constants
        stack: list = []
        push = stack.append
        pop = stack.pop
        ip = 0
        _NUM = (int, float)
        call_stack: list = []

        while True:
            op, arg, line = code[ip]
            ip += 1

            if op == B.GET_LOCAL:
                push(locals_[arg].value)
            elif op == B.GET_LOCAL_RAW:
                push(locals_[arg])
            elif op == B.CONST:
                push(constants[arg])
            elif op == B.CALL:
                argc = arg
                if argc:
                    call_args = stack[-argc:]
                    del stack[-argc:]
                else:
                    call_args = []
                callee = pop()
                if type(callee) is Closure:
                    cproto = callee.proto
                    if argc != cproto.arity:
                        raise BoltRuntimeError(
                            f"Function '{cproto.name or '<anonymous>'}' expected "
                            f"{cproto.arity} argument(s) but got {argc}",
                            line,
                        )
                    call_stack.append((code, constants, locals_, stack, push, pop, ip, upvalues))
                    proto = cproto
                    locals_ = [
                        (Cell(a) if boxed else a) for a, boxed in zip(call_args, proto.param_boxed)
                    ]
                    locals_.extend([None] * (proto.num_locals - argc))
                    code = proto.chunk.code
                    constants = proto.chunk.constants
                    upvalues = callee.upvalues
                    stack = []
                    push = stack.append
                    pop = stack.pop
                    ip = 0
                    continue
                elif callable(callee):
                    try:
                        result = callee(*call_args)
                    except BoltRuntimeError:
                        raise
                    except Exception as e:
                        raise BoltRuntimeError(str(e), line)
                else:
                    raise BoltRuntimeError("Value is not callable", line)
                push(result)
            elif op == B.ADD:
                b_ = pop()
                a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ + b_)
                elif ta is Tensor or tb is Tensor:
                    try:
                        push(a_ + b_)
                    except (ValueError, TypeError) as e:
                        raise BoltRuntimeError(str(e), line)
                elif ta is str or tb is str:
                    push(_stringify(a_) + _stringify(b_))
                elif ta is list and tb is list:
                    push(a_ + b_)
                else:
                    _check_numbers(a_, b_, line)
                    push(a_ + b_)
            elif op == B.SUB:
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ - b_)
                elif ta is Tensor or tb is Tensor:
                    try:
                        push(a_ - b_)
                    except (ValueError, TypeError) as e:
                        raise BoltRuntimeError(str(e), line)
                else:
                    _check_numbers(a_, b_, line)
                    push(a_ - b_)
            elif op == B.MUL:
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ * b_)
                elif ta is Tensor or tb is Tensor:
                    try:
                        push(a_ * b_)
                    except (ValueError, TypeError) as e:
                        raise BoltRuntimeError(str(e), line)
                else:
                    _check_numbers(a_, b_, line)
                    push(a_ * b_)
            elif op == B.LT:
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ < b_)
                    continue
                _check_numbers(a_, b_, line)
                push(a_ < b_)
            elif op == B.GT:
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ > b_)
                    continue
                _check_numbers(a_, b_, line)
                push(a_ > b_)
            elif op == B.SET_LOCAL:
                locals_[arg].value = stack[-1]
            elif op == B.SET_LOCAL_RAW:
                locals_[arg] = stack[-1]
            elif op == B.INIT_LOCAL:
                locals_[arg] = Cell(pop())
            elif op == B.INIT_LOCAL_RAW:
                locals_[arg] = pop()
            elif op == B.JUMP:
                ip = arg
            elif op == B.JUMP_IF_FALSE_POP:
                if not _is_truthy(stack.pop()):
                    ip = arg
            elif op == B.RETURN:
                result = stack.pop()
                if call_stack:
                    code, constants, locals_, stack, push, pop, ip, upvalues = call_stack.pop()
                    push(result)
                    continue
                return result
            elif op == B.POP:
                stack.pop()
            elif op == B.GET_GLOBAL:
                try:
                    push(self.globals[arg])
                except KeyError:
                    raise BoltRuntimeError(f"Undefined variable '{arg}'", line)
            elif op == B.SET_GLOBAL:
                g = self.globals
                if arg in g:
                    g[arg] = stack[-1]
                else:
                    raise BoltRuntimeError(f"Undefined variable '{arg}'", line)
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
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ <= b_)
                    continue
                _check_numbers(a_, b_, line)
                push(a_ <= b_)
            elif op == B.GTE:
                b_ = pop(); a_ = pop()
                ta, tb = type(a_), type(b_)
                if (ta is int or ta is float) and (tb is int or tb is float):
                    push(a_ >= b_)
                    continue
                _check_numbers(a_, b_, line)
                push(a_ >= b_)
            elif op == B.DIV:
                b_ = stack.pop(); a_ = stack.pop()
                if isinstance(a_, Tensor) or isinstance(b_, Tensor):
                    try:
                        stack.append(a_ / b_)
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        raise BoltRuntimeError(str(e), line)
                    continue
                _check_numbers(a_, b_, line)
                if b_ == 0:
                    raise BoltRuntimeError("Division by zero", line)
                stack.append(a_ / b_)
            elif op == B.MOD:
                b_ = stack.pop(); a_ = stack.pop()
                _check_numbers(a_, b_, line)
                if b_ == 0:
                    raise BoltRuntimeError("Modulo by zero", line)
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
                    raise BoltRuntimeError(f"Index/key {key!r} not found", line)
                except TypeError as e:
                    raise BoltRuntimeError(str(e), line)
            elif op == B.SET_INDEX:
                value = stack.pop()
                key = stack.pop()
                obj = stack.pop()
                try:
                    obj[key] = value
                except (TypeError, IndexError) as e:
                    raise BoltRuntimeError(str(e), line)
                stack.append(value)
            elif op == B.GET_ATTR:
                obj = stack.pop()
                if isinstance(obj, dict) and arg in obj:
                    stack.append(obj[arg])
                else:
                    raise BoltRuntimeError(f"No attribute '{arg}'", line)
            elif op == B.SET_ATTR:
                value = stack.pop()
                obj = stack.pop()
                if isinstance(obj, dict):
                    obj[arg] = value
                else:
                    raise BoltRuntimeError("Cannot set attribute on this value", line)
                stack.append(value)
            elif op == B.GET_ITER:
                iterable = stack.pop()
                try:
                    stack.append(iter(iterable))
                except TypeError:
                    raise BoltRuntimeError("Value is not iterable", line)
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
                raise BoltRuntimeError(f"Unknown opcode {op}", line)
