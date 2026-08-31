"""Real GPU-accelerated rendering backend for Bolt's game-dev builtins,
via SDL2 (SDL_Renderer, hardware-accelerated by default) - a genuine
capability upgrade over the original tkinter Canvas backend, which is
software-rendered and visibly dated. The public surface
(window/clear/rect/circle/line/draw_text/draw_image/key/mouse_*/tick/
close_window, plus sprite sheets/animation) is unchanged from a Bolt
script author's point of view; builtins.py picks this backend when the
bundled DLLs (runtime/sdl2/) are present and falls back to tkinter
otherwise (e.g. non-Windows, or that directory stripped out).
"""

import ctypes
import os
import time
from pathlib import Path

from .errors import BoltRuntimeError

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtime" / "sdl2"

_sdl2 = None
_gfx = None
_img = None
_available = None
_initialized = False

SDL_INIT_VIDEO = 0x00000020
SDL_WINDOWPOS_UNDEFINED = 0x1FFF0000
SDL_WINDOW_SHOWN = 0x00000004
SDL_RENDERER_ACCELERATED = 0x00000002
SDL_RENDERER_PRESENTVSYNC = 0x00000004

SDL_QUIT = 0x100
SDL_WINDOWEVENT = 0x200
SDL_KEYDOWN = 0x300
SDL_KEYUP = 0x301
SDL_MOUSEMOTION = 0x400
SDL_MOUSEBUTTONDOWN = 0x401
SDL_MOUSEBUTTONUP = 0x402
SDL_WINDOWEVENT_CLOSE = 14

SDL_BUTTON_LEFT = 1
SDL_BUTTON_RIGHT = 3

IMG_INIT_PNG = 2


def available() -> bool:
    global _available
    if _available is None:
        _available = (
            os.name == "nt"
            and (_RUNTIME_DIR / "SDL2.dll").exists()
            and (_RUNTIME_DIR / "SDL2_gfx.dll").exists()
            and (_RUNTIME_DIR / "SDL2_image.dll").exists()
        )
    return _available


class _SDL_Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


# SDL_Event is a big union; we only need the leading `type` field to
# dispatch, then reinterpret the same buffer as the specific event struct
# for the fields each event type actually carries. Buffer sized generously
# (SDL2's real union is 56 bytes) to safely hold any variant.
class _SDL_KeyboardEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32), ("windowID", ctypes.c_uint32),
        ("state", ctypes.c_uint8), ("repeat", ctypes.c_uint8), ("_p2", ctypes.c_uint8), ("_p3", ctypes.c_uint8),
        ("scancode", ctypes.c_int32), ("sym", ctypes.c_int32), ("mod", ctypes.c_uint16), ("_unused", ctypes.c_uint32),
    ]


class _SDL_MouseMotionEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32), ("windowID", ctypes.c_uint32),
        ("which", ctypes.c_uint32), ("state", ctypes.c_uint32),
        ("x", ctypes.c_int32), ("y", ctypes.c_int32), ("xrel", ctypes.c_int32), ("yrel", ctypes.c_int32),
    ]


class _SDL_MouseButtonEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32), ("windowID", ctypes.c_uint32),
        ("which", ctypes.c_uint32), ("button", ctypes.c_uint8), ("state", ctypes.c_uint8),
        ("clicks", ctypes.c_uint8), ("_pad", ctypes.c_uint8), ("x", ctypes.c_int32), ("y", ctypes.c_int32),
    ]


class _SDL_WindowEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32), ("timestamp", ctypes.c_uint32), ("windowID", ctypes.c_uint32),
        ("event", ctypes.c_uint8), ("_p1", ctypes.c_uint8), ("_p2", ctypes.c_uint8), ("_p3", ctypes.c_uint8),
        ("data1", ctypes.c_int32), ("data2", ctypes.c_int32),
    ]


class _SDL_Event(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("key", _SDL_KeyboardEvent),
        ("motion", _SDL_MouseMotionEvent),
        ("button", _SDL_MouseButtonEvent),
        ("window", _SDL_WindowEvent),
        ("_padding", ctypes.c_uint8 * 56),
    ]


def _configure():
    global _sdl2, _gfx, _img
    if os.name == "nt":
        try:
            os.add_dll_directory(str(_RUNTIME_DIR))
        except (AttributeError, OSError):
            pass
    _sdl2 = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2.dll"))
    _gfx = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2_gfx.dll"))
    _img = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2_image.dll"))

    _sdl2.SDL_Init.argtypes = [ctypes.c_uint32]
    _sdl2.SDL_Init.restype = ctypes.c_int
    _sdl2.SDL_GetError.restype = ctypes.c_char_p
    _sdl2.SDL_CreateWindow.restype = ctypes.c_void_p
    _sdl2.SDL_CreateWindow.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
    _sdl2.SDL_CreateRenderer.restype = ctypes.c_void_p
    _sdl2.SDL_CreateRenderer.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    _sdl2.SDL_SetRenderDrawColor.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8]
    _sdl2.SDL_RenderClear.argtypes = [ctypes.c_void_p]
    _sdl2.SDL_RenderPresent.argtypes = [ctypes.c_void_p]
    _sdl2.SDL_DestroyRenderer.argtypes = [ctypes.c_void_p]
    _sdl2.SDL_DestroyWindow.argtypes = [ctypes.c_void_p]
    _sdl2.SDL_PollEvent.argtypes = [ctypes.POINTER(_SDL_Event)]
    _sdl2.SDL_PollEvent.restype = ctypes.c_int
    _sdl2.SDL_GetKeyName.restype = ctypes.c_char_p
    _sdl2.SDL_GetKeyName.argtypes = [ctypes.c_int32]
    _sdl2.SDL_RenderCopy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_SDL_Rect), ctypes.POINTER(_SDL_Rect)]
    _sdl2.SDL_QueryTexture.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    _sdl2.SDL_DestroyTexture.argtypes = [ctypes.c_void_p]

    _gfx.boxColor.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_uint32]
    _gfx.filledCircleColor.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_uint32]
    _gfx.lineColor.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_uint32]
    _gfx.thickLineColor.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_uint8, ctypes.c_uint32]
    _gfx.stringColor.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_int16, ctypes.c_char_p, ctypes.c_uint32]

    _img.IMG_LoadTexture.restype = ctypes.c_void_p
    _img.IMG_LoadTexture.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    _img.IMG_Init.argtypes = [ctypes.c_int]


def _ensure_init():
    global _initialized
    if _initialized:
        return
    if not available():
        raise BoltRuntimeError("SDL2 backend requested but runtime/sdl2/ DLLs are missing")
    _configure()
    if _sdl2.SDL_Init(SDL_INIT_VIDEO) != 0:
        raise BoltRuntimeError(f"SDL2 failed to initialize: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
    _img.IMG_Init(IMG_INIT_PNG)
    _initialized = True


def _hex_to_rgb(color):
    s = str(color).lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return (255, 255, 255)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def _pack_color(color, alpha=255):
    # SDL2_gfx's Uint32 color parameter is 0xAABBGGRR (R in the LOWEST
    # byte) - verified empirically against real rendered+read-back pixels
    # (pure red/green/blue plus the exact target hex color all matched
    # only under this packing; the more commonly-assumed 0xRRGGBBAA
    # rendered nothing at all, since it put alpha=0 in disguise).
    r, g, b = _hex_to_rgb(color)
    return ((alpha & 0xFF) << 24) | (b << 16) | (g << 8) | r


class SDLWindow:
    def __init__(self, width, height, title):
        _ensure_init()
        self.width = int(width)
        self.height = int(height)
        self.closed = False
        self._last_tick = None
        self._presented_once = False
        self.camera_x = 0.0
        self.camera_y = 0.0

        self.win = _sdl2.SDL_CreateWindow(
            str(title).encode("utf-8"),
            SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
            self.width, self.height, SDL_WINDOW_SHOWN,
        )
        if not self.win:
            raise BoltRuntimeError(f"SDL2 window() failed: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
        self.ren = _sdl2.SDL_CreateRenderer(self.win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC)
        if not self.ren:
            self.ren = _sdl2.SDL_CreateRenderer(self.win, -1, 0)
        if not self.ren:
            raise BoltRuntimeError(f"SDL2 renderer creation failed: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")

        self.keys_down: set[str] = set()
        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_buttons_down: set[str] = set()
        self._textures: dict[str, ctypes.c_void_p] = {}  # path -> SDL_Texture*

    def _pump(self):
        ev = _SDL_Event()
        while _sdl2.SDL_PollEvent(ctypes.byref(ev)) != 0:
            t = ev.type
            if t == SDL_QUIT:
                self.closed = True
            elif t == SDL_WINDOWEVENT and ev.window.event == SDL_WINDOWEVENT_CLOSE:
                self.closed = True
            elif t in (SDL_KEYDOWN, SDL_KEYUP):
                name_bytes = _sdl2.SDL_GetKeyName(ev.key.sym)
                name = (name_bytes or b"").decode("utf-8", "replace").lower()
                if name:
                    if t == SDL_KEYDOWN:
                        self.keys_down.add(name)
                    else:
                        self.keys_down.discard(name)
            elif t == SDL_MOUSEMOTION:
                self.mouse_x = ev.motion.x
                self.mouse_y = ev.motion.y
            elif t in (SDL_MOUSEBUTTONDOWN, SDL_MOUSEBUTTONUP):
                btn = "left" if ev.button.button == SDL_BUTTON_LEFT else ("right" if ev.button.button == SDL_BUTTON_RIGHT else None)
                if btn:
                    if t == SDL_MOUSEBUTTONDOWN:
                        self.mouse_buttons_down.add(btn)
                    else:
                        self.mouse_buttons_down.discard(btn)

    def tick(self, fps):
        # Presents whatever was drawn since the *previous* tick() call (the
        # script's own `clear()`/`rect()`/... calls in between), then paces
        # to `fps`, pumps input, and reports whether the window is still
        # open - mirrors tkinter's root.update() timing exactly so existing
        # `while tick(win, 60) { draw... }` scripts behave identically.
        if self.closed:
            return False
        if self._presented_once:
            _sdl2.SDL_RenderPresent(self.ren)
        self._presented_once = True

        self._pump()
        if self.closed:
            return False

        frame_time = 1.0 / max(1.0, float(fps))
        now = time.perf_counter()
        if self._last_tick is not None:
            remaining = frame_time - (now - self._last_tick)
            if remaining > 0:
                time.sleep(remaining)
        self._last_tick = time.perf_counter()
        return True

    def clear(self, color):
        r, g, b = _hex_to_rgb(color)
        _sdl2.SDL_SetRenderDrawColor(self.ren, r, g, b, 255)
        _sdl2.SDL_RenderClear(self.ren)

    def rect(self, x, y, w, h, color):
        _gfx.boxColor(self.ren, int(x), int(y), int(x) + int(w), int(y) + int(h), _pack_color(color))

    def circle(self, x, y, r, color):
        _gfx.filledCircleColor(self.ren, int(x), int(y), int(r), _pack_color(color))

    def line(self, x1, y1, x2, y2, color, width=1):
        # SDL2_gfx has no line-width param on lineColor; thickLineColor
        # exists but width=1 (the common case, matching every current
        # example/test) renders identically via the plain call.
        w = int(width)
        if w <= 1:
            _gfx.lineColor(self.ren, int(x1), int(y1), int(x2), int(y2), _pack_color(color))
        else:
            _gfx.thickLineColor(self.ren, int(x1), int(y1), int(x2), int(y2), w, _pack_color(color))

    def draw_text(self, x, y, msg, color):
        _gfx.stringColor(self.ren, int(x), int(y), str(msg).encode("utf-8", "replace"), _pack_color(color))

    def _get_texture(self, path):
        tex = self._textures.get(path)
        if tex is None:
            tex = _img.IMG_LoadTexture(self.ren, str(path).encode("utf-8"))
            if not tex:
                raise BoltRuntimeError(f"couldn't load image '{path}': {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
            self._textures[path] = tex
        return tex

    def draw_image(self, path, x, y):
        tex = self._get_texture(path)
        w, h = ctypes.c_int(), ctypes.c_int()
        _sdl2.SDL_QueryTexture(tex, None, None, ctypes.byref(w), ctypes.byref(h))
        dst = _SDL_Rect(int(x), int(y), w.value, h.value)
        _sdl2.SDL_RenderCopy(self.ren, tex, None, ctypes.byref(dst))

    def draw_sprite_frame(self, path, frame_w, frame_h, col, row, x, y):
        tex = self._get_texture(path)
        src = _SDL_Rect(col * frame_w, row * frame_h, frame_w, frame_h)
        dst = _SDL_Rect(int(x), int(y), frame_w, frame_h)
        _sdl2.SDL_RenderCopy(self.ren, tex, ctypes.byref(src), ctypes.byref(dst))

    def texture_size(self, path):
        tex = self._get_texture(path)
        w, h = ctypes.c_int(), ctypes.c_int()
        _sdl2.SDL_QueryTexture(tex, None, None, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            for tex in self._textures.values():
                _sdl2.SDL_DestroyTexture(tex)
            _sdl2.SDL_DestroyRenderer(self.ren)
            _sdl2.SDL_DestroyWindow(self.win)
        except Exception:
            pass

    def __str__(self):
        state = "closed" if self.closed else "open"
        return f"<window {self.width}x{self.height} {state} (sdl2)>"
