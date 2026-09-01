"""Real GPU-accelerated rendering backend for Bolt's game-dev builtins,
via SDL2 (SDL_Renderer, hardware-accelerated by default) - a genuine
capability upgrade over the original tkinter Canvas backend, which is
software-rendered and visibly dated. The public surface
(window/clear/rect/circle/line/draw_text/draw_image/key/mouse_*/tick/
close_window, plus sprite sheets/animation) is unchanged from a Bolt
script author's point of view; builtins.py picks this backend when SDL2
is available and falls back to tkinter otherwise.

Cross-platform library loading:
- Windows: the three DLLs are bundled in runtime/sdl2/ (zero extra
  install - see that directory's README).
- Linux: loaded from the system's own SDL2 install via ctypes.CDLL,
  trying each distro's real versioned .so name in turn. NOT via
  ctypes.util.find_library() - verified empirically that it returns
  None on a stock Debian/Ubuntu system with only the runtime packages
  (libsdl2-2.0-0 etc.) installed, because find_library() looks for the
  unversioned lib*.so symlink that only ships in the *-dev packages;
  real Linux users installing the runtime libs alone would silently
  get no SDL2 backend if this loader relied on it. If none of the
  candidate names load, a clear error names the exact apt packages to
  install rather than a raw ctypes error.
- Anywhere else (e.g. macOS): not attempted; falls back to tkinter.
"""

import ctypes
import os
import sys
import time
from pathlib import Path

from .errors import BoltRuntimeError

_RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent / "runtime" / "sdl2"

# Real versioned .so names as shipped by the runtime (non -dev) packages on
# Debian/Ubuntu and Fedora, in the order tried. libSDL2.so (unversioned) is
# tried last as a bonus for anyone who does have the -dev package.
_LINUX_CANDIDATES = {
    "SDL2": ["libSDL2-2.0.so.0", "libSDL2-2.0.so", "libSDL2.so"],
    "SDL2_gfx": ["libSDL2_gfx-1.0.so.0", "libSDL2_gfx-1.0.so", "libSDL2_gfx.so"],
    "SDL2_image": ["libSDL2_image-2.0.so.0", "libSDL2_image-2.0.so", "libSDL2_image.so"],
}
_LINUX_INSTALL_HINT = (
    "sudo apt install libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0 "
    "(Debian/Ubuntu) or sudo dnf install SDL2 SDL2_gfx SDL2_image (Fedora)"
)

_sdl2 = None
_gfx = None
_img = None
_available = None
_initialized = False

SDL_INIT_VIDEO = 0x00000020
SDL_INIT_AUDIO = 0x00000010
AUDIO_S16LSB = 0x8010
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
        if os.name == "nt":
            _available = (
                (_RUNTIME_DIR / "SDL2.dll").exists()
                and (_RUNTIME_DIR / "SDL2_gfx.dll").exists()
                and (_RUNTIME_DIR / "SDL2_image.dll").exists()
            )
        elif sys.platform.startswith("linux"):
            _available = all(_probe_linux_lib(names) is not None for names in _LINUX_CANDIDATES.values())
        else:
            _available = False
    return _available


def _probe_linux_lib(candidate_names):
    """Tries each real .so name in turn, returning the first name that
    actually loads (not the handle - _configure() below does the real
    load once and keeps it). Used both by available() (cheap yes/no) and
    _configure() (which needs to know which name worked).
    """
    for name in candidate_names:
        try:
            ctypes.CDLL(name)
            return name
        except OSError:
            continue
    return None


class _SDL_Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


class _SDL_AudioSpec(ctypes.Structure):
    _fields_ = [
        ("freq", ctypes.c_int),
        ("format", ctypes.c_uint16),
        ("channels", ctypes.c_uint8),
        ("silence", ctypes.c_uint8),
        ("samples", ctypes.c_uint16),
        ("padding", ctypes.c_uint16),
        ("size", ctypes.c_uint32),
        ("callback", ctypes.c_void_p),  # NULL - queue-based audio (SDL_QueueAudio) instead
        ("userdata", ctypes.c_void_p),
    ]


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
        missing = [n for n in ("SDL2.dll", "SDL2_gfx.dll", "SDL2_image.dll") if not (_RUNTIME_DIR / n).exists()]
        if missing:
            raise BoltRuntimeError(f"SDL2 backend requested but runtime/sdl2/ is missing: {', '.join(missing)}")
        try:
            os.add_dll_directory(str(_RUNTIME_DIR))
        except (AttributeError, OSError):
            pass
        _sdl2 = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2.dll"))
        _gfx = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2_gfx.dll"))
        _img = ctypes.CDLL(str(_RUNTIME_DIR / "SDL2_image.dll"))
    elif sys.platform.startswith("linux"):
        sdl2_name = _probe_linux_lib(_LINUX_CANDIDATES["SDL2"])
        gfx_name = _probe_linux_lib(_LINUX_CANDIDATES["SDL2_gfx"])
        img_name = _probe_linux_lib(_LINUX_CANDIDATES["SDL2_image"])
        if not (sdl2_name and gfx_name and img_name):
            missing = [
                lib for lib, name in [("SDL2", sdl2_name), ("SDL2_gfx", gfx_name), ("SDL2_image", img_name)]
                if not name
            ]
            raise BoltRuntimeError(
                f"SDL2 backend requested but {', '.join(missing)} isn't installed on this system. "
                f"Install it with: {_LINUX_INSTALL_HINT}"
            )
        _sdl2 = ctypes.CDLL(sdl2_name)
        _gfx = ctypes.CDLL(gfx_name)
        _img = ctypes.CDLL(img_name)
    else:
        raise BoltRuntimeError("SDL2 backend is only supported on Windows and Linux")

    _sdl2.SDL_Init.argtypes = [ctypes.c_uint32]
    _sdl2.SDL_Init.restype = ctypes.c_int
    _sdl2.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    _sdl2.SDL_InitSubSystem.restype = ctypes.c_int
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

    _sdl2.SDL_RWFromFile.restype = ctypes.c_void_p
    _sdl2.SDL_RWFromFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _sdl2.SDL_LoadWAV_RW.restype = ctypes.c_void_p
    _sdl2.SDL_LoadWAV_RW.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(_SDL_AudioSpec),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)), ctypes.POINTER(ctypes.c_uint32),
    ]
    _sdl2.SDL_FreeWAV.argtypes = [ctypes.c_void_p]
    _sdl2.SDL_OpenAudioDevice.restype = ctypes.c_uint32
    _sdl2.SDL_OpenAudioDevice.argtypes = [
        ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_SDL_AudioSpec), ctypes.POINTER(_SDL_AudioSpec), ctypes.c_int,
    ]
    _sdl2.SDL_PauseAudioDevice.argtypes = [ctypes.c_uint32, ctypes.c_int]
    _sdl2.SDL_QueueAudio.restype = ctypes.c_int
    _sdl2.SDL_QueueAudio.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    _sdl2.SDL_ClearQueuedAudio.argtypes = [ctypes.c_uint32]
    _sdl2.SDL_CloseAudioDevice.argtypes = [ctypes.c_uint32]


def _ensure_init():
    global _initialized
    if _initialized:
        return
    # Deliberately not gated on available() here - _configure() raises its
    # own specific, actionable error per platform (which Linux package is
    # missing, or that the DLLs directory is missing on Windows). A stale
    # generic "DLLs are missing" message here previously masked that error
    # on Linux entirely - caught by a test that simulated a missing lib and
    # found this exact message instead of the real one.
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


# ---- cross-platform audio (beep/play_sound/stop_sound) ----
#
# Windows keeps using winsound (see builtins.py) since it's already a
# perfectly good stdlib solution there. On Linux (no winsound module),
# this backs the same three builtins via SDL2's raw audio-queue API
# (SDL_QueueAudio), reusing the SDL2 handle already loaded for
# rendering rather than requiring a second audio library. Single-stream
# semantics match winsound.PlaySound(): starting a new sound replaces
# whatever was playing, same as SND_ASYNC's implicit behavior.

_audio_dev = None
_audio_dev_spec = None  # (freq, format, channels) of the currently open device
_audio_initialized = False


def _ensure_audio_init():
    global _audio_initialized
    if _audio_initialized:
        return
    if not available():
        raise BoltRuntimeError(
            "Cross-platform audio requested but SDL2 isn't available. "
            f"Install it with: {_LINUX_INSTALL_HINT}"
        )
    if _sdl2 is None:
        _configure()
    if _sdl2.SDL_InitSubSystem(SDL_INIT_AUDIO) != 0:
        raise BoltRuntimeError(f"SDL2 audio failed to initialize: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
    _audio_initialized = True


def _open_audio_device(freq, fmt, channels):
    global _audio_dev, _audio_dev_spec
    key = (freq, fmt, channels)
    if _audio_dev is not None and _audio_dev_spec == key:
        return _audio_dev
    if _audio_dev is not None:
        _sdl2.SDL_CloseAudioDevice(_audio_dev)
        _audio_dev = None
    desired = _SDL_AudioSpec(freq=freq, format=fmt, channels=channels, silence=0, samples=4096, padding=0, size=0, callback=None, userdata=None)
    obtained = _SDL_AudioSpec()
    dev = _sdl2.SDL_OpenAudioDevice(None, 0, ctypes.byref(desired), ctypes.byref(obtained), 0)
    if dev == 0:
        raise BoltRuntimeError(f"SDL2 audio device open failed: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
    _sdl2.SDL_PauseAudioDevice(dev, 0)
    _audio_dev = dev
    _audio_dev_spec = key
    return dev


def beep(freq=440, duration_ms=200):
    """Synthesizes a sine-wave tone and plays it, blocking for
    duration_ms - matching winsound.Beep()'s own blocking behavior so
    scripts written against the Windows path behave the same here.
    """
    _ensure_audio_init()
    sample_rate = 44100
    dev = _open_audio_device(sample_rate, AUDIO_S16LSB, 1)
    n_samples = max(1, int(sample_rate * duration_ms / 1000))
    import math
    import struct
    amplitude = 12000
    samples = [int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n_samples)]
    buf = struct.pack(f"<{n_samples}h", *samples)
    _sdl2.SDL_ClearQueuedAudio(dev)
    _sdl2.SDL_QueueAudio(dev, buf, len(buf))
    time.sleep(duration_ms / 1000)


def play_sound(path, wait=False):
    """Loads and plays a real .wav file via SDL_LoadWAV_RW + SDL_QueueAudio.
    wait=True blocks until playback finishes (computed from the WAV's own
    sample rate/format/length); wait=False returns immediately, matching
    winsound's SND_ASYNC.
    """
    _ensure_audio_init()
    rw = _sdl2.SDL_RWFromFile(str(path).encode("utf-8"), b"rb")
    if not rw:
        raise BoltRuntimeError(f"play_sound(): couldn't open '{path}': {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
    spec = _SDL_AudioSpec()
    buf_ptr = ctypes.POINTER(ctypes.c_uint8)()
    buf_len = ctypes.c_uint32()
    result = _sdl2.SDL_LoadWAV_RW(rw, 1, ctypes.byref(spec), ctypes.byref(buf_ptr), ctypes.byref(buf_len))
    if not result:
        raise BoltRuntimeError(f"play_sound(): couldn't decode '{path}' as a WAV file: {_sdl2.SDL_GetError().decode('utf-8', 'replace')}")
    dev = _open_audio_device(spec.freq, spec.format, spec.channels)
    _sdl2.SDL_ClearQueuedAudio(dev)
    _sdl2.SDL_QueueAudio(dev, buf_ptr, buf_len.value)
    bytes_per_sample = {0x8010: 2, 0x0008: 1, 0x0010: 2}.get(spec.format, 2)  # AUDIO_S16LSB, AUDIO_U8, AUDIO_S16
    duration_s = buf_len.value / (spec.freq * spec.channels * bytes_per_sample) if spec.freq and spec.channels else 0
    _sdl2.SDL_FreeWAV(buf_ptr)
    if wait:
        time.sleep(duration_s)


def stop_sound():
    """Stops whatever play_sound()/beep() is currently playing."""
    if _audio_dev is not None:
        _sdl2.SDL_ClearQueuedAudio(_audio_dev)
