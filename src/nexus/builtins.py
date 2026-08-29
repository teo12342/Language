from .errors import NexusRuntimeError
from .interpreter import _stringify


def _nx_print(*args):
    print(" ".join(_stringify(a) for a in args))
    return None


def _nx_len(value):
    try:
        return len(value)
    except TypeError:
        raise NexusRuntimeError(f"len() not supported for {type(value).__name__}")


def _nx_range(*args):
    if len(args) == 1:
        return list(range(int(args[0])))
    if len(args) == 2:
        return list(range(int(args[0]), int(args[1])))
    if len(args) == 3:
        return list(range(int(args[0]), int(args[1]), int(args[2])))
    raise NexusRuntimeError("range() expects 1 to 3 arguments")


def _nx_str(value):
    return _stringify(value)


def _nx_num(value):
    try:
        return float(value) if isinstance(value, str) and "." in value else int(value)
    except (TypeError, ValueError):
        raise NexusRuntimeError(f"Cannot convert {value!r} to number")


def _nx_type(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    return "func"


def _nx_push(lst, value):
    if not isinstance(lst, list):
        raise NexusRuntimeError("push() expects a list")
    lst.append(value)
    return lst


def _nx_pop(lst):
    if not isinstance(lst, list) or not lst:
        raise NexusRuntimeError("pop() expects a non-empty list")
    return lst.pop()


def _nx_keys(m):
    if not isinstance(m, dict):
        raise NexusRuntimeError("keys() expects a map")
    return list(m.keys())


def _nx_upper(s):
    return s.upper()


def _nx_lower(s):
    return s.lower()


def _nx_split(s, sep):
    return s.split(sep)


def _nx_join(lst, sep):
    return sep.join(_stringify(x) for x in lst)


def make_builtins() -> dict[str, object]:
    return {
        "print": _nx_print,
        "len": _nx_len,
        "range": _nx_range,
        "str": _nx_str,
        "num": _nx_num,
        "type": _nx_type,
        "push": _nx_push,
        "pop": _nx_pop,
        "keys": _nx_keys,
        "upper": _nx_upper,
        "lower": _nx_lower,
        "split": _nx_split,
        "join": _nx_join,
    }
