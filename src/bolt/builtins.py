import http.server
import importlib
import math
from pathlib import Path

from . import sdl_backend
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


# The repo/project root that ships packages/ (three levels up from this
# file: src/bolt/builtins.py -> src/bolt -> src -> root). Used as a
# fallback so import() still finds the local registry even when Bolt is
# invoked from a different working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_module_path(path: str) -> Path:
    candidates = [
        Path(path),
        Path("packages") / path,
        _PROJECT_ROOT / path,
        _PROJECT_ROOT / "packages" / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise BoltRuntimeError(
        f"Cannot find module '{path}' (looked in the current directory, packages/, "
        "and the same locations relative to Bolt's own install directory)"
    )


def _wrap_module_closure(closure, owning_vm):
    """Makes a module's exported Closure callable from a different engine
    instance than the one that ran the module. A VM's global-name lookups
    (GET_GLOBAL/recursion/etc.) resolve against *whichever* VM instance is
    executing at CALL-time - so calling a module's Closure directly from
    the importing script's own VM would incorrectly look up the module's
    globals in the wrong VM. This wrapper always dispatches back through
    the module's own VM, so a module's internal recursion/globals stay
    correctly self-contained no matter who calls it.
    """
    def wrapper(*args):
        return owning_vm.call_closure(closure, list(args), 0)
    return wrapper


def _make_import():
    """import(path): load another .bo file as a module, once per path.

    Runs the file in its own isolated VM (so its top-level names never
    leak into or collide with the importing script's), then returns a
    Bolt map of everything it defined at its own top level - so
    `let math = import("packages/mathutils.bo")` then `math.square(3)`
    works from either engine. Looked up relative to the current
    directory first, then `packages/` (the local package registry).
    Only the VM/tree-walker engines support import(); it isn't available
    when transpiling with --target js.
    """
    cache: dict[str, dict] = {}

    def _import(path):
        if path in cache:
            return cache[path]
        # Imported lazily: builtins.py is the leaf of the package, and these
        # modules would otherwise import it back (a cycle) since they're
        # what wires builtins into an engine in the first place.
        from .compiler import compile_program
        from .lexer import Lexer
        from .parser import Parser
        from .typechecker import check_types
        from .vm import VM, Closure

        resolved = _resolve_module_path(path)
        try:
            source = resolved.read_text()
            tokens = Lexer(source).tokenize()
            stmts = Parser(tokens).parse()
            check_types(stmts)
            proto = compile_program(stmts)
        except BoltRuntimeError:
            raise
        except Exception as e:
            raise BoltRuntimeError(f"Error importing '{path}': {e}")

        module_vm = VM(make_builtins())
        base_keys = set(module_vm.globals.keys())
        module_vm.run_program(proto)

        exported = {}
        for name, value in module_vm.globals.items():
            if name in base_keys:
                continue
            exported[name] = _wrap_module_closure(value, module_vm) if isinstance(value, Closure) else value

        cache[path] = exported
        return exported

    return _import


# Curated set of standard-library modules pyimport() may load. This is not
# a general FFI: it's deliberately restricted to safe, side-effect-free
# stdlib modules so `pyimport("os")` (or `subprocess`, `sys`, ...) can't be
# used to shell out or touch the filesystem/network from Bolt code.
_PYIMPORT_ALLOWLIST = {
    "math", "random", "statistics", "json", "re", "itertools",
    "datetime", "string", "collections", "functools", "fractions",
    "decimal", "textwrap", "unicodedata", "calendar", "bisect", "heapq",
}


def _py_to_bolt(value):
    # Bolt's own values (numbers, str, bool, None, list, dict) already are
    # the matching Python types; only a few Python-only shapes need mapping.
    if isinstance(value, tuple):
        return [_py_to_bolt(v) for v in value]
    if isinstance(value, list):
        return [_py_to_bolt(v) for v in value]
    if isinstance(value, dict):
        return {k: _py_to_bolt(v) for k, v in value.items()}
    return value


def _wrap_py_callable(fn):
    def _wrapped(*args):
        try:
            return _py_to_bolt(fn(*args))
        except BoltRuntimeError:
            raise
        except Exception as e:
            raise BoltRuntimeError(f"Python error in '{fn.__name__ if hasattr(fn, '__name__') else fn}': {e}")

    return _wrapped


def _make_pyimport():
    """pyimport(name): load a real Python standard-library module and
    return a Bolt map of its public functions/constants, so Bolt code can
    call straight into Python (e.g. `let m = pyimport("statistics")`,
    `m.median([1, 2, 3])`). This is the interop bridge to Python's
    ecosystem: instead of Bolt reimplementing every useful function, it
    can borrow Python's - the same shortcut Deno took by staying
    npm-compatible instead of building a whole new JS package ecosystem.

    Restricted to `_PYIMPORT_ALLOWLIST` (safe stdlib modules only, no
    filesystem/network/process access) since this loads real Python code
    for execution - an unrestricted `pyimport(any_name)` would let Bolt
    scripts shell out via `os`/`subprocess`.
    """
    cache: dict[str, dict] = {}

    def _pyimport(name):
        if not isinstance(name, str):
            raise BoltRuntimeError("pyimport() expects a module name string")
        if name in cache:
            return cache[name]
        if name not in _PYIMPORT_ALLOWLIST:
            raise BoltRuntimeError(
                f"pyimport(): '{name}' is not in the allowed module list. "
                f"Allowed: {', '.join(sorted(_PYIMPORT_ALLOWLIST))}"
            )
        module = importlib.import_module(name)
        exported = {}
        for attr in dir(module):
            if attr.startswith("_"):
                continue
            value = getattr(module, attr)
            if callable(value):
                exported[attr] = _wrap_py_callable(value)
            elif isinstance(value, (int, float, str, bool)):
                exported[attr] = value
        cache[name] = exported
        return exported

    return _pyimport


class _BoltWindow:
    """A real, on-screen window with a drawable canvas and keyboard input,
    backed by tkinter (ships with Python's stdlib - no extra install, same
    "borrow the ecosystem" spirit as pyimport(), but for game dev instead
    of math/data). Bolt code never sees this class - only opaque handles
    returned by window() and passed back into the drawing functions below.
    """

    def __init__(self, width, height, title):
        import tkinter as tk

        self.width = int(width)
        self.height = int(height)
        self.closed = False
        self._last_tick = None
        self.camera_x = 0.0
        self.camera_y = 0.0

        self.root = tk.Tk()
        self.root.title(str(title))
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(
            self.root, width=self.width, height=self.height,
            bg="black", highlightthickness=0,
        )
        self.canvas.pack()

        self.keys_down: set[str] = set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<KeyPress>", lambda e: self.keys_down.add(e.keysym.lower()))
        self.root.bind("<KeyRelease>", lambda e: self.keys_down.discard(e.keysym.lower()))

        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_buttons_down: set[str] = set()
        self.root.bind("<Motion>", self._on_mouse_move)
        self.root.bind("<Button-1>", lambda e: self.mouse_buttons_down.add("left"))
        self.root.bind("<ButtonRelease-1>", lambda e: self.mouse_buttons_down.discard("left"))
        self.root.bind("<Button-3>", lambda e: self.mouse_buttons_down.add("right"))
        self.root.bind("<ButtonRelease-3>", lambda e: self.mouse_buttons_down.discard("right"))

        self._images: dict = {}  # path -> tk.PhotoImage, kept alive here

    def _on_mouse_move(self, event):
        self.mouse_x = event.x
        self.mouse_y = event.y

    def _on_close(self):
        self.closed = True
        try:
            self.root.destroy()
        except Exception:
            pass

    def __str__(self):
        state = "closed" if self.closed else "open"
        return f"<window {self.width}x{self.height} {state}>"


_WINDOW_TYPES = (_BoltWindow, sdl_backend.SDLWindow)


def _require_open_window(win, fn_name):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError(f"{fn_name}() expects a window handle from window()")
    return not win.closed


def _make_window():
    def _window(width, height, title="Bolt"):
        # Real GPU-accelerated rendering (SDL2, bundled in runtime/sdl2/ -
        # see that directory's README) when available; falls back to the
        # original tkinter Canvas backend otherwise (non-Windows, or that
        # directory stripped out) so nothing breaks either way. Every
        # drawing/input builtin below dispatches on which kind of handle
        # it got, so Bolt scripts see no difference either way.
        if sdl_backend.available():
            try:
                return sdl_backend.SDLWindow(width, height, title)
            except BoltRuntimeError:
                pass  # fall through to tkinter if SDL2 failed to init
        return _BoltWindow(width, height, title)

    return _window


def _clear(win, color="black"):
    if not _require_open_window(win, "clear"):
        return None
    if isinstance(win, sdl_backend.SDLWindow):
        win.clear(color)
        return None
    win.canvas.delete("all")
    win.canvas.configure(bg=color)
    return None


def _apply_camera(win, x, y):
    """Offsets a world-space (x, y) by the window's camera position, so
    set_camera(win, cx, cy) scrolls every subsequent rect/circle/line/
    draw_image/draw_sprite call without scripts doing the subtraction
    themselves. draw_text is deliberately excluded (HUD/UI stays in
    screen space) - the same convention most 2D engines use. Pure and
    windowless so it's testable without ever opening a real window.
    """
    return x - getattr(win, "camera_x", 0.0), y - getattr(win, "camera_y", 0.0)


def _set_camera(win, x, y):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("set_camera() expects a window handle from window()")
    win.camera_x = float(x)
    win.camera_y = float(y)
    return None


def _rect(win, x, y, w, h, color="white"):
    if not _require_open_window(win, "rect"):
        return None
    x, y = _apply_camera(win, x, y)
    if isinstance(win, sdl_backend.SDLWindow):
        win.rect(x, y, w, h, color)
        return None
    win.canvas.create_rectangle(x, y, x + w, y + h, fill=color, outline="")
    return None


def _circle(win, x, y, r, color="white"):
    if not _require_open_window(win, "circle"):
        return None
    x, y = _apply_camera(win, x, y)
    if isinstance(win, sdl_backend.SDLWindow):
        win.circle(x, y, r, color)
        return None
    win.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
    return None


def _line(win, x1, y1, x2, y2, color="white", width=1):
    if not _require_open_window(win, "line"):
        return None
    x1, y1 = _apply_camera(win, x1, y1)
    x2, y2 = _apply_camera(win, x2, y2)
    if isinstance(win, sdl_backend.SDLWindow):
        win.line(x1, y1, x2, y2, color, width)
        return None
    win.canvas.create_line(x1, y1, x2, y2, fill=color, width=width)
    return None


def _draw_text(win, x, y, msg, color="white"):
    if not _require_open_window(win, "draw_text"):
        return None
    if isinstance(win, sdl_backend.SDLWindow):
        win.draw_text(x, y, _stringify(msg), color)
        return None
    win.canvas.create_text(x, y, text=_stringify(msg), fill=color, anchor="nw")
    return None


def _draw_image(win, path, x, y):
    """Draws a real image at (x, y). Images are cached per window by
    path. Under the SDL2 backend this is a real GPU texture (via
    SDL2_image, PNG - the same format tkinter's PhotoImage decoded);
    under the tkinter fallback it's a PhotoImage, cached for the same
    reason as before: tkinter drops a PhotoImage's pixels the moment
    nothing keeps a Python reference to it - the classic "blank canvas"
    tkinter sprite bug.
    """
    if not _require_open_window(win, "draw_image"):
        return None
    x, y = _apply_camera(win, x, y)
    if isinstance(win, sdl_backend.SDLWindow):
        win.draw_image(path, x, y)
        return None
    import tkinter as tk

    img = win._images.get(path)
    if img is None:
        try:
            img = tk.PhotoImage(file=path)
        except Exception as e:
            raise BoltRuntimeError(f"draw_image(): couldn't load '{path}': {e}")
        win._images[path] = img
    win.canvas.create_image(x, y, image=img, anchor="nw")
    return None


def _rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
    """Axis-aligned bounding-box collision - the standard first check
    every 2D game needs before anything fancier."""
    return x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2


def _circles_overlap(x1, y1, r1, x2, y2, r2):
    dx = x1 - x2
    dy = y1 - y2
    return (dx * dx + dy * dy) < (r1 + r2) * (r1 + r2)


def _beep(freq=440, duration_ms=200):
    """A real system beep at a given frequency (Hz) and duration (ms).
    Uses winsound on Windows (ships with Python's stdlib there); on
    Linux, falls back to a synthesized tone played through SDL2's audio
    queue (sdl_backend.py - the same SDL2 already used for rendering),
    so this works without any extra install on either platform. Raises
    a clear error only if neither path is available (e.g. Linux without
    SDL2's runtime packages installed).
    """
    try:
        import winsound
    except ImportError:
        if sdl_backend.available():
            sdl_backend.beep(freq, duration_ms)
            return None
        raise BoltRuntimeError(
            "beep() needs either winsound (Windows) or SDL2 (Linux - "
            "install libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0)"
        )
    winsound.Beep(int(freq), int(duration_ms))
    return None


def _play_sound(path, wait=False):
    """Plays a real .wav file. Uses winsound on Windows; on Linux, falls
    back to SDL2's audio queue (same fallback as beep() above).
    `wait=true` blocks until playback finishes, otherwise it plays in
    the background so the game loop keeps running.
    """
    try:
        import winsound
    except ImportError:
        if sdl_backend.available():
            sdl_backend.play_sound(path, wait)
            return None
        raise BoltRuntimeError(
            "play_sound() needs either winsound (Windows) or SDL2 (Linux - "
            "install libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0)"
        )
    flags = winsound.SND_FILENAME
    flags |= 0 if wait else winsound.SND_ASYNC
    winsound.PlaySound(path, flags)
    return None


def _stop_sound():
    """Stops whatever play_sound() is currently playing asynchronously.
    Uses winsound on Windows; falls back to SDL2 on Linux, same as
    beep()/play_sound() above."""
    try:
        import winsound
    except ImportError:
        if sdl_backend.available():
            sdl_backend.stop_sound()
            return None
        raise BoltRuntimeError(
            "stop_sound() needs either winsound (Windows) or SDL2 (Linux - "
            "install libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0)"
        )
    winsound.PlaySound(None, winsound.SND_PURGE)
    return None


def _key(win, name):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("key() expects a window handle from window()")
    return str(name).lower() in win.keys_down


def _mouse_x(win):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("mouse_x() expects a window handle from window()")
    return win.mouse_x


def _mouse_y(win):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("mouse_y() expects a window handle from window()")
    return win.mouse_y


def _mouse_down(win, button="left"):
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("mouse_down() expects a window handle from window()")
    return str(button).lower() in win.mouse_buttons_down


def _tick(win, fps=60):
    """Pumps the window's event loop, presents the frame drawn since the
    last tick(), and paces to `fps`. Returns false once the window has
    been closed - the natural `while tick(win, 60) { ... }` game-loop
    condition. Under the SDL2 backend, SDLWindow.tick() does all of
    this itself (see sdl_backend.py); the tkinter path is unchanged
    from before.
    """
    if not isinstance(win, _WINDOW_TYPES):
        raise BoltRuntimeError("tick() expects a window handle from window()")
    if isinstance(win, sdl_backend.SDLWindow):
        return win.tick(fps)

    import time

    if win.closed:
        return False
    try:
        win.root.update()
    except Exception:
        win.closed = True
        return False
    if win.closed:
        return False

    frame_time = 1.0 / max(1.0, float(fps))
    now = time.perf_counter()
    if win._last_tick is not None:
        remaining = frame_time - (now - win._last_tick)
        if remaining > 0:
            time.sleep(remaining)
    win._last_tick = time.perf_counter()
    return True


def _close_window(win):
    if isinstance(win, sdl_backend.SDLWindow):
        win.close()
    elif isinstance(win, _BoltWindow):
        win._on_close()
    return None


def _probe_image_size(path):
    """Reads an image's pixel dimensions without tying the sprite sheet
    to any particular rendering backend (or even requiring a window to
    exist yet) - load_spritesheet() has no window argument, and under
    SDL2 the actual texture is created lazily, per-window, on first
    draw (SDL2_image needs a renderer to create a texture against).
    Reads the PNG IHDR chunk directly (no library needed) since every
    bundled sprite asset is PNG; falls back to tkinter's PhotoImage
    (which can decode PNG/GIF) for anything else.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(33)
    except OSError as e:
        raise BoltRuntimeError(f"load_spritesheet(): couldn't read '{path}': {e}")
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        import struct

        w, h = struct.unpack(">II", head[16:24])
        return w, h
    import tkinter as tk

    try:
        img = tk.PhotoImage(file=str(path))
    except Exception as e:
        raise BoltRuntimeError(f"load_spritesheet(): couldn't load '{path}': {e}")
    return img.width(), img.height()


class _BoltSpriteSheet:
    """A grid-sliced sprite sheet: one source image cut into equal-sized
    frame_w x frame_h cells, numbered left-to-right, top-to-bottom
    starting at 0. Backend-agnostic by design (see _probe_image_size) -
    the actual per-backend texture/cropped-frame is created lazily on
    first draw, in _draw_sprite() below, since that's the first point a
    window (and therefore a specific backend) is known.
    """

    def __init__(self, path, frame_w, frame_h):
        self.path = str(path)
        self.frame_w = int(frame_w)
        self.frame_h = int(frame_h)
        if self.frame_w <= 0 or self.frame_h <= 0:
            raise BoltRuntimeError("load_spritesheet(): frame width/height must be positive")
        width, height = _probe_image_size(self.path)
        self.cols = max(1, width // self.frame_w)
        self.rows = max(1, height // self.frame_h)
        self.count = self.cols * self.rows
        self._tk_source = None  # tkinter backend only, created lazily
        self._tk_frame_cache: dict = {}

    def _tk_frame_image(self, index):
        import tkinter as tk

        if self._tk_source is None:
            try:
                self._tk_source = tk.PhotoImage(file=self.path)
            except Exception as e:
                raise BoltRuntimeError(f"load_spritesheet(): couldn't load '{self.path}': {e}")
        cached = self._tk_frame_cache.get(index)
        if cached is not None:
            return cached
        col = index % self.cols
        row = index // self.cols
        x1 = col * self.frame_w
        y1 = row * self.frame_h
        frame = tk.PhotoImage(width=self.frame_w, height=self.frame_h)
        frame.tk.call(
            frame, "copy", self._tk_source,
            "-from", x1, y1, x1 + self.frame_w, y1 + self.frame_h,
            "-to", 0, 0,
        )
        self._tk_frame_cache[index] = frame
        return frame


def _load_spritesheet(path, frame_w, frame_h):
    return _BoltSpriteSheet(path, frame_w, frame_h)


def _sprite_frame_count(sheet):
    if not isinstance(sheet, _BoltSpriteSheet):
        raise BoltRuntimeError("sprite_frame_count() expects a spritesheet from load_spritesheet()")
    return sheet.count


def _draw_sprite(win, sheet, frame_index, x, y):
    if not _require_open_window(win, "draw_sprite"):
        return None
    if not isinstance(sheet, _BoltSpriteSheet):
        raise BoltRuntimeError("draw_sprite() expects a spritesheet from load_spritesheet()")
    frame_index = int(frame_index)
    if frame_index < 0 or frame_index >= sheet.count:
        raise BoltRuntimeError(
            f"sprite frame index {frame_index} out of range (sheet has {sheet.count} frames)"
        )
    x, y = _apply_camera(win, x, y)
    if isinstance(win, sdl_backend.SDLWindow):
        col = frame_index % sheet.cols
        row = frame_index // sheet.cols
        win.draw_sprite_frame(sheet.path, sheet.frame_w, sheet.frame_h, col, row, x, y)
        return None
    win.canvas.create_image(x, y, image=sheet._tk_frame_image(frame_index), anchor="nw")
    return None


def _load_tileset(path, tile_w, tile_h):
    """A tileset is structurally identical to a sprite sheet - a grid of
    equal-sized cells sliced from one source image - so this reuses
    _BoltSpriteSheet directly rather than a parallel implementation.
    """
    return _load_spritesheet(path, tile_w, tile_h)


def _draw_tile(win, tileset, tile_index, x, y):
    return _draw_sprite(win, tileset, tile_index, x, y)


def _tilemap_placements(grid, tile_w, tile_h, offset_x=0, offset_y=0):
    """Pure grid-to-placements logic for draw_tilemap(), factored out so
    it's unit-testable without a window: yields (tile_index, x, y) for
    every cell in `grid` (a list of rows, each a list of tile indices)
    whose index is >= 0 - a negative index marks an empty cell, skipped
    rather than drawn.
    """
    placements = []
    for row_idx, row in enumerate(grid):
        if not isinstance(row, list):
            raise BoltRuntimeError("draw_tilemap() expects a list of rows (each a list of tile indices)")
        for col_idx, tile_index in enumerate(row):
            tile_index = int(tile_index)
            if tile_index < 0:
                continue
            placements.append((tile_index, offset_x + col_idx * tile_w, offset_y + row_idx * tile_h))
    return placements


def _draw_tilemap(win, tileset, grid, tile_w, tile_h, offset_x=0, offset_y=0):
    """Draws a whole level laid out as a 2-D list of tile indices in one
    call - e.g. `draw_tilemap(win, tiles, [[0,0,1],[0,-1,1]], 16, 16)` -
    instead of a script hand-writing the row/col loop itself every time.
    Respects the window's camera (via draw_tile -> draw_sprite), so a
    tilemap pans correctly alongside everything else set_camera() moves.
    """
    if not isinstance(grid, list):
        raise BoltRuntimeError("draw_tilemap() expects a list of rows (each a list of tile indices)")
    for tile_index, x, y in _tilemap_placements(grid, tile_w, tile_h, offset_x, offset_y):
        _draw_tile(win, tileset, tile_index, x, y)
    return None


class _BoltParticles:
    """Small deterministic-friendly particle emitter for 2D games.

    Particles are plain Python state behind three builtins so game scripts do
    not need to manage parallel position/velocity/lifetime arrays.
    """

    def __init__(self, count, color="#e2895f", size=3):
        import random
        self.color = color
        self.size = max(1.0, float(size))
        self.items = []
        for _ in range(max(0, int(count))):
            angle = random.random() * 6.283185307179586
            speed = 20.0 + random.random() * 80.0
            self.items.append({"x": 0.0, "y": 0.0, "vx": __import__("math").cos(angle) * speed,
                               "vy": __import__("math").sin(angle) * speed,
                               "life": 1.0})


def _make_particles(count, color="#e2895f", size=3):
    return _BoltParticles(count, color, size)


def _particles_emit(particles, x, y):
    if not isinstance(particles, _BoltParticles):
        raise BoltRuntimeError("particles_emit() expects particles from make_particles()")
    for item in particles.items:
        item["x"], item["y"], item["life"] = float(x), float(y), 1.0
    return particles


def _particles_step(particles, dt, gravity=80):
    if not isinstance(particles, _BoltParticles):
        raise BoltRuntimeError("particles_step() expects particles from make_particles()")
    dt, gravity = float(dt), float(gravity)
    alive = []
    for item in particles.items:
        item["vy"] += gravity * dt
        item["x"] += item["vx"] * dt
        item["y"] += item["vy"] * dt
        item["life"] -= dt
        if item["life"] > 0:
            alive.append(item)
    particles.items = alive
    return len(alive)


def _particles_draw(win, particles):
    if not isinstance(particles, _BoltParticles):
        raise BoltRuntimeError("particles_draw() expects particles from make_particles()")
    for item in particles.items:
        _circle(win, item["x"], item["y"], particles.size, particles.color)
    return None


class _BoltAnim:
    """Time-driven playback state over a list of frame indices into one
    spritesheet. anim_draw() both advances playback (based on real
    elapsed wall-clock time since the last call) and draws the current
    frame - one call per game-loop iteration, same rhythm as tick().
    """

    def __init__(self, sheet, frames, fps, loop=True):
        import time

        if not isinstance(sheet, _BoltSpriteSheet):
            raise BoltRuntimeError("make_anim() expects a spritesheet from load_spritesheet()")
        if not isinstance(frames, list) or not frames:
            raise BoltRuntimeError("make_anim() expects a non-empty list of frame indices")
        self.sheet = sheet
        self.frames = [int(f) for f in frames]
        self.fps = max(0.001, float(fps))
        self.loop = bool(loop)
        self.index = 0
        self.finished = False
        self.playing = True
        self._last_time = time.perf_counter()
        self._accum = 0.0


def _make_anim(sheet, frames, fps, loop=True):
    return _BoltAnim(sheet, frames, fps, loop)


def _require_anim(anim, fn_name):
    if not isinstance(anim, _BoltAnim):
        raise BoltRuntimeError(f"{fn_name}() expects an animation handle from make_anim()")


def _anim_reset(anim):
    import time

    _require_anim(anim, "anim_reset")
    anim.index = 0
    anim.finished = False
    anim.playing = True
    anim._accum = 0.0
    anim._last_time = time.perf_counter()
    return None


def _anim_set_playing(anim, playing):
    _require_anim(anim, "anim_set_playing")
    anim.playing = bool(playing)
    return None


def _anim_advance(anim):
    """Advances anim's frame counter by real elapsed time since the
    last advance/draw call. Separated from anim_draw() so a script can
    advance animation state without a window (e.g. headless tests)."""
    import time

    _require_anim(anim, "anim_advance")
    now = time.perf_counter()
    dt = now - anim._last_time
    anim._last_time = now
    if not anim.playing or anim.finished:
        return None
    anim._accum += dt
    frame_time = 1.0 / anim.fps
    while anim._accum >= frame_time:
        anim._accum -= frame_time
        anim.index += 1
        if anim.index >= len(anim.frames):
            if anim.loop:
                anim.index = 0
            else:
                anim.index = len(anim.frames) - 1
                anim.finished = True
                anim.playing = False
                break
    return None


def _anim_frame(anim):
    _require_anim(anim, "anim_frame")
    return anim.frames[anim.index]


def _anim_finished(anim):
    _require_anim(anim, "anim_finished")
    return anim.finished


def _anim_draw(win, anim, x, y):
    _require_anim(anim, "anim_draw")
    _anim_advance(anim)
    return _draw_sprite(win, anim.sheet, _anim_frame(anim), x, y)


_MCI_MISSING = "audio channels need winmm.dll (Windows multimedia), which is Windows-only"
_mci_send_string = None
_open_audio_channels: set = set()


def _get_mci():
    global _mci_send_string
    if _mci_send_string is None:
        import ctypes

        try:
            _mci_send_string = ctypes.windll.winmm.mciSendStringW
        except (AttributeError, OSError):
            raise BoltRuntimeError(_MCI_MISSING)
    return _mci_send_string


def _mci_alias(channel):
    return f"bolt_channel_{_stringify(channel)}"


def _play_channel(channel, path, loop=False):
    """Plays a .wav file on a named channel via the Windows multimedia
    (MCI) API - unlike play_sound()/winsound (which can only play one
    sound system-wide, cutting off whatever was playing before), each
    channel is its own MCI device instance, so multiple channels mix
    together for real (e.g. play_channel("music", ...) plus
    play_channel("sfx", ...) at the same time). Calling play_channel()
    again on the same channel replaces whatever that channel was
    playing.
    """
    mci = _get_mci()
    alias = _mci_alias(channel)
    if alias in _open_audio_channels:
        mci(f"close {alias}", None, 0, None)
        _open_audio_channels.discard(alias)
    path = str(Path(path).resolve())
    rc = mci(f'open "{path}" type waveaudio alias {alias}', None, 0, None)
    if rc != 0:
        raise BoltRuntimeError(f"play_channel(): couldn't open '{path}'")
    _open_audio_channels.add(alias)
    mci(f"play {alias}" + (" repeat" if loop else ""), None, 0, None)
    return None


def _stop_channel(channel):
    mci = _get_mci()
    alias = _mci_alias(channel)
    if alias in _open_audio_channels:
        mci(f"stop {alias}", None, 0, None)
        mci(f"close {alias}", None, 0, None)
        _open_audio_channels.discard(alias)
    return None


def _stop_all_channels():
    mci = _get_mci()
    for alias in list(_open_audio_channels):
        mci(f"stop {alias}", None, 0, None)
        mci(f"close {alias}", None, 0, None)
    _open_audio_channels.clear()
    return None


def _channel_playing(channel):
    mci = _get_mci()
    alias = _mci_alias(channel)
    if alias not in _open_audio_channels:
        return False
    buf = __import__("ctypes").create_unicode_buffer(64)
    mci(f"status {alias} mode", buf, 64, None)
    return buf.value.strip().lower() == "playing"


def _apply_gravity(vy, gravity=980.0, dt=1.0 / 60.0):
    """vy after gravity accelerates it for dt seconds. Defaults (980
    px/s^2, 1/60s) suit a typical 60fps game loop with pixel units."""
    return vy + float(gravity) * float(dt)


def _apply_friction(v, friction=0.9):
    """Exponential-style per-call damping: friction=1 means no
    slowdown, 0 means an instant stop. Multiplicative (not subtractive)
    so it stays stable regardless of frame rate drift."""
    return v * float(friction)


def _integrate(pos, vel, dt=1.0 / 60.0):
    """pos advanced by vel over dt seconds - the one-line building
    block every hand-rolled game loop already writes; here as a named
    call so it reads the same way across scripts."""
    return pos + vel * dt


def _clamp(x, lo, hi):
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, x))


def _physics_step(x, y, vx, vy, ax, ay, dt=1.0 / 60.0):
    """One step of semi-implicit (symplectic) Euler integration:
    velocity is updated from acceleration first, then position is
    updated using that *new* velocity. More stable than naive Euler for
    games (e.g. a ball bouncing under gravity doesn't slowly gain
    energy) while still being one small, inspectable function rather
    than a physics engine. Returns [new_x, new_y, new_vx, new_vy].
    """
    dt = float(dt)
    nvx = vx + float(ax) * dt
    nvy = vy + float(ay) * dt
    nx = x + nvx * dt
    ny = y + nvy * dt
    return [nx, ny, nvx, nvy]


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
        "import": _make_import(),
        "pyimport": _make_pyimport(),
        "window": _make_window(),
        "clear": _clear,
        "rect": _rect,
        "circle": _circle,
        "line": _line,
        "draw_text": _draw_text,
        "draw_image": _draw_image,
        "set_camera": _set_camera,
        "load_tileset": _load_tileset,
        "draw_tile": _draw_tile,
        "draw_tilemap": _draw_tilemap,
        "key": _key,
        "mouse_x": _mouse_x,
        "mouse_y": _mouse_y,
        "mouse_down": _mouse_down,
        "tick": _tick,
        "close_window": _close_window,
        "rects_overlap": _rects_overlap,
        "circles_overlap": _circles_overlap,
        "beep": _beep,
        "play_sound": _play_sound,
        "stop_sound": _stop_sound,
        "load_spritesheet": _load_spritesheet,
        "sprite_frame_count": _sprite_frame_count,
        "draw_sprite": _draw_sprite,
        "make_anim": _make_anim,
        "anim_advance": _anim_advance,
        "anim_draw": _anim_draw,
        "anim_frame": _anim_frame,
        "anim_finished": _anim_finished,
        "anim_reset": _anim_reset,
        "anim_set_playing": _anim_set_playing,
        "play_channel": _play_channel,
        "stop_channel": _stop_channel,
        "stop_all_channels": _stop_all_channels,
        "channel_playing": _channel_playing,
        "apply_gravity": _apply_gravity,
        "apply_friction": _apply_friction,
        "integrate": _integrate,
        "clamp": _clamp,
        "physics_step": _physics_step,
        "make_particles": _make_particles,
        "particles_emit": _particles_emit,
        "particles_step": _particles_step,
        "particles_draw": _particles_draw,
    }
