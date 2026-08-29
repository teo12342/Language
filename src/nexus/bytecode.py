from dataclasses import dataclass, field

# Opcodes. Plain small ints for fast if/elif dispatch in the VM loop.
CONST = 1
BUILD_LIST = 2
BUILD_MAP = 3
GET_LOCAL = 4
SET_LOCAL = 5
INIT_LOCAL = 6
GET_UPVALUE = 7
SET_UPVALUE = 8
GET_GLOBAL = 9
SET_GLOBAL = 10
DEFINE_GLOBAL = 11
GET_INDEX = 12
SET_INDEX = 13
GET_ATTR = 14
SET_ATTR = 15
ADD = 16
SUB = 17
MUL = 18
DIV = 19
MOD = 20
EQ = 21
NEQ = 22
LT = 23
LTE = 24
GT = 25
GTE = 26
NEG = 27
NOT = 28
POP = 29
JUMP = 30
JUMP_IF_FALSE_POP = 31
JUMP_IF_FALSE_PEEK = 32
JUMP_IF_TRUE_PEEK = 33
GET_ITER = 34
FOR_ITER = 35
CALL = 36
CLOSURE = 37
RETURN = 38


@dataclass
class Chunk:
    code: list = field(default_factory=list)  # list of (op, arg, line)
    constants: list = field(default_factory=list)

    def emit(self, op, arg, line) -> int:
        self.code.append([op, arg, line])
        return len(self.code) - 1

    def add_const(self, value) -> int:
        self.constants.append(value)
        return len(self.constants) - 1

    def patch(self, index: int, target: int):
        self.code[index][1] = target


@dataclass
class FunctionProto:
    name: str | None
    arity: int
    chunk: Chunk
    upvalue_specs: list  # list of (is_local: bool, index: int)
    num_locals: int
