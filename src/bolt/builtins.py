import http.server
import math

from .errors import BoltRuntimeError
from .interpreter import _stringify
from .tensor import Tensor
from .tensor import dot as _tensor_dot
from .tensor import matmul as _tensor_matmul


def _nx_print(*args):
    print(" ".join(_stringify(a) for a in args))
    return None


def _nx_len(value):
    try:
        return len(value)
    except TypeError:
        raise BoltRuntimeError(f"len() not supported for {type(value).__name__}")


def _nx_range(*args):
    if len(args) == 1:
        return list(range(int(args[0])))
    if len(args) == 2:
        return list(range(int(args[0]), int(args[1])))
    if len(args) == 3:
        return list(range(int(args[0]), int(args[1]), int(args[2])))
    raise BoltRuntimeError("range() expects 1 to 3 arguments")


def _nx_str(value):
    return _stringify(value)


def _nx_num(value):
    try:
        return float(value) if isinstance(value, str) and "." in value else int(value)
    except (TypeError, ValueError):
        raise BoltRuntimeError(f"Cannot convert {value!r} to number")


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
        raise BoltRuntimeError("push() expects a list")
    lst.append(value)
    return lst


def _nx_pop(lst):
    if not isinstance(lst, list) or not lst:
        raise BoltRuntimeError("pop() expects a non-empty list")
    return lst.pop()


def _nx_keys(m):
    if not isinstance(m, dict):
        raise BoltRuntimeError("keys() expects a map")
    return list(m.keys())


def _nx_upper(s):
    return s.upper()


def _nx_lower(s):
    return s.lower()


def _nx_split(s, sep):
    return s.split(sep)


def _nx_join(lst, sep):
    return sep.join(_stringify(x) for x in lst)


def _nx_tensor(nested):
    if not isinstance(nested, list):
        raise BoltRuntimeError("tensor() expects a list")
    try:
        return Tensor.from_nested(nested)
    except ValueError as e:
        raise BoltRuntimeError(str(e))


def _nx_zeros(*dims):
    try:
        dims = [int(d) for d in dims]
    except (TypeError, ValueError):
        raise BoltRuntimeError("zeros() expects numeric dimensions")
    if len(dims) == 1:
        return Tensor((dims[0],), [0.0] * dims[0])
    if len(dims) == 2:
        return Tensor((dims[0], dims[1]), [0.0] * (dims[0] * dims[1]))
    raise BoltRuntimeError("zeros() supports 1 or 2 dimensions")


def _nx_dot(a, b):
    if not isinstance(a, Tensor) or not isinstance(b, Tensor):
        raise BoltRuntimeError("dot() expects two tensors")
    try:
        return _tensor_dot(a, b)
    except ValueError as e:
        raise BoltRuntimeError(str(e))


def _nx_matmul(a, b):
    if not isinstance(a, Tensor) or not isinstance(b, Tensor):
        raise BoltRuntimeError("matmul() expects two tensors")
    try:
        return _tensor_matmul(a, b)
    except ValueError as e:
        raise BoltRuntimeError(str(e))


def _nx_tshape(t):
    if not isinstance(t, Tensor):
        raise BoltRuntimeError("tshape() expects a tensor")
    return list(t.shape)


def _nx_tolist(t):
    if not isinstance(t, Tensor):
        raise BoltRuntimeError("tolist() expects a tensor")
    return t.to_nested()


def _nx_tsum(t):
    if not isinstance(t, Tensor):
        raise BoltRuntimeError("tsum() expects a tensor")
    return sum(t.data)


def _nx_transpose(t):
    if not isinstance(t, Tensor) or len(t.shape) != 2:
        raise BoltRuntimeError("transpose() expects a 2-D tensor")
    rows, cols = t.shape
    data = [0.0] * (rows * cols)
    for r in range(rows):
        for c in range(cols):
            data[c * rows + r] = t.data[r * cols + c]
    return Tensor((cols, rows), data)


def _nx_identity(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise BoltRuntimeError("identity() expects a number")
    data = [0.0] * (n * n)
    for i in range(n):
        data[i * n + i] = 1.0
    return Tensor((n, n), data)


def _make_tmap(call_fn):
    """tmap(tensor, fn): apply a Bolt function elementwise over a tensor."""

    def _tmap(t, fn):
        if not isinstance(t, Tensor):
            raise BoltRuntimeError("tmap() expects a tensor")
        if call_fn is None:
            raise BoltRuntimeError("tmap() is not available in this context")
        return Tensor(t.shape, [call_fn(fn, [x]) for x in t.data])

    return _tmap


# ---- math ----

def _nx_sqrt(x):
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise BoltRuntimeError("sqrt() expects a number")
    if x < 0:
        raise BoltRuntimeError("sqrt() of a negative number")
    return math.sqrt(x)


def _nx_abs(x):
    return abs(x)


def _nx_min(*args):
    values = args[0] if len(args) == 1 and isinstance(args[0], list) else args
    if not values:
        raise BoltRuntimeError("min() expects at least one value")
    return min(values)


def _nx_max(*args):
    values = args[0] if len(args) == 1 and isinstance(args[0], list) else args
    if not values:
        raise BoltRuntimeError("max() expects at least one value")
    return max(values)


def _nx_floor(x):
    return math.floor(x)


def _nx_ceil(x):
    return math.ceil(x)


def _nx_round(x, digits=0):
    digits = int(digits)
    return round(x, digits) if digits else round(x)


def _nx_pow(base, exponent):
    return base ** exponent


# ---- strings ----

def _nx_trim(s):
    return s.strip()


def _nx_replace(s, old, new):
    return s.replace(old, new)


def _nx_repeat(s, n):
    return s * int(n)


def _nx_starts_with(s, prefix):
    return s.startswith(prefix)


def _nx_ends_with(s, suffix):
    return s.endswith(suffix)


# ---- lists / general ----

def _nx_contains(container, item):
    try:
        return item in container
    except TypeError:
        raise BoltRuntimeError("contains() expects a list, map, or string")


def _nx_index_of(container, item):
    try:
        return container.index(item)
    except ValueError:
        return -1
    except AttributeError:
        raise BoltRuntimeError("index_of() expects a list or string")


def _nx_sort(lst):
    if not isinstance(lst, list):
        raise BoltRuntimeError("sort() expects a list")
    lst.sort()
    return lst


def _nx_reverse(lst):
    if not isinstance(lst, list):
        raise BoltRuntimeError("reverse() expects a list")
    lst.reverse()
    return lst


def _nx_slice(lst, start, end=None):
    if end is None:
        return lst[int(start):]
    return lst[int(start):int(end)]


def _nx_concat(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if isinstance(a, str) and isinstance(b, str):
        return a + b
    raise BoltRuntimeError("concat() expects two lists or two strings")


def _make_serve(call_fn):
    """serve(port, handler, max_requests=1): a real HTTP server.

    `handler` is a Bolt function taking a request path (string) and
    returning the response body (string) - called once per request via
    `call_fn`, so the response can be different for every path, computed
    by actual Bolt code. `max_requests` bounds how many requests to
    answer before returning (0 means run forever, like a normal server);
    it defaults to 1 so a script doesn't hang a test/demo run forever.
    """

    def _serve(port, handler, max_requests=1):
        if call_fn is None:
            raise BoltRuntimeError("serve() is not available in this context")

        class _Server(http.server.HTTPServer):
            allow_reuse_address = True

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    body = call_fn(handler, [self.path])
                except BoltRuntimeError as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))
                    return
                body_bytes = _stringify(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)

            def log_message(self, format, *args):
                pass  # keep the Bolt script's own output clean

        httpd = _Server(("127.0.0.1", int(port)), _Handler)
        try:
            n = int(max_requests)
            if n <= 0:
                httpd.serve_forever()
            else:
                for _ in range(n):
                    httpd.handle_request()
        finally:
            httpd.server_close()
        return None

    return _serve


def make_builtins(call_fn=None) -> dict[str, object]:
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
        "tensor": _nx_tensor,
        "zeros": _nx_zeros,
        "dot": _nx_dot,
        "matmul": _nx_matmul,
        "tshape": _nx_tshape,
        "tolist": _nx_tolist,
        "tsum": _nx_tsum,
        "transpose": _nx_transpose,
        "identity": _nx_identity,
        "tmap": _make_tmap(call_fn),
        "sqrt": _nx_sqrt,
        "abs": _nx_abs,
        "min": _nx_min,
        "max": _nx_max,
        "floor": _nx_floor,
        "ceil": _nx_ceil,
        "round": _nx_round,
        "pow": _nx_pow,
        "trim": _nx_trim,
        "replace": _nx_replace,
        "repeat": _nx_repeat,
        "starts_with": _nx_starts_with,
        "ends_with": _nx_ends_with,
        "contains": _nx_contains,
        "index_of": _nx_index_of,
        "sort": _nx_sort,
        "reverse": _nx_reverse,
        "slice": _nx_slice,
        "concat": _nx_concat,
        "serve": _make_serve(call_fn),
    }
