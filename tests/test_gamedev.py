from pathlib import Path

import os
import sys

from bolt.builtins import (
    _apply_camera,
    _load_spritesheet,
    _load_tileset,
    _probe_image_size,
    _sprite_frame_count,
    _tilemap_placements,
    _make_particles,
    _particles_emit,
    _particles_step,
)
from bolt import sdl_backend

import pytest

from .test_stdlib import run_and_capture

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_probe_image_size_reads_real_png_header():
    # examples/run_sheet.png is a real, checked-in 64x16 PNG (4 frames of
    # 16x16) - read via the raw IHDR-chunk parser, not a library, so this
    # also proves that parser is correct against a real file, not just a
    # synthetic byte string.
    w, h = _probe_image_size(str(_REPO_ROOT / "examples" / "run_sheet.png"))
    assert (w, h) == (64, 16)


def test_load_spritesheet_frame_count_matches_real_asset():
    sheet = _load_spritesheet(str(_REPO_ROOT / "examples" / "run_sheet.png"), 16, 16)
    assert (sheet.cols, sheet.rows, sheet.count) == (4, 1, 4)
    assert _sprite_frame_count(sheet) == 4


def test_sdl_backend_pack_color_matches_verified_channel_order():
    # SDL2_gfx's Uint32 color format is 0xAABBGGRR (R in the lowest byte),
    # confirmed empirically against real rendered+read-back pixels (see
    # sdl_backend.py's _pack_color docstring/comment) - not the more
    # commonly assumed 0xRRGGBBAA, which silently rendered nothing at all
    # (alpha ended up 0). This locks that finding in as a regression test.
    packed = sdl_backend._pack_color("#e2895f")
    assert packed == 0xFF5F89E2  # (A=255)<<24 | (B=0x5F)<<16 | (G=0x89)<<8 | R=0xE2


def test_particles_emit_and_step_expire_without_a_window():
    particles = _make_particles(4, "#fff", 2)
    _particles_emit(particles, 10, 20)
    assert len(particles.items) == 4
    assert all(item["x"] == 10 and item["y"] == 20 for item in particles.items)
    assert _particles_step(particles, 0.5) == 4
    assert _particles_step(particles, 0.6) == 0



def test_probe_linux_lib_returns_none_when_nothing_matches():
    assert sdl_backend._probe_linux_lib(["libDefinitelyDoesNotExist_xyz.so.0"]) is None


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux system-library loading path only applies on Linux",
)
def test_linux_sdl2_backend_loads_from_real_system_libraries():
    # Requires the actual runtime packages installed (e.g. `apt install
    # libsdl2-2.0-0 libsdl2-gfx-1.0-0 libsdl2-image-2.0-0`) - skips rather
    # than failing if this machine doesn't have them, same pattern as
    # test_native.py skipping when no C compiler is present.
    if not sdl_backend.available():
        pytest.skip("SDL2 runtime libraries not installed on this machine")

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    win = sdl_backend.SDLWindow(20, 20, "linux backend test")
    try:
        win.clear("#000000")
        win.rect(0, 0, 20, 20, "#e2895f")
        win.tick(60)
        win.tick(60)  # presents the frame drawn above

        import ctypes

        class _Rect(ctypes.Structure):
            _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]

        # A NULL rect means "read the whole framebuffer" (here 20*20*4 =
        # 1600 bytes), not "read one pixel" - passing NULL with a 4-byte
        # buffer overflowed the heap and segfaulted, but only visibly so
        # under pytest's different memory layout (it silently corrupted
        # memory and ran fine standalone). Reading an explicit 1x1 rect
        # is the actual fix, not just what happened not to crash.
        one_px = _Rect(0, 0, 1, 1)
        buf = ctypes.create_string_buffer(4)
        sdl_backend._sdl2.SDL_RenderReadPixels.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_Rect), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int,
        ]
        rc = sdl_backend._sdl2.SDL_RenderReadPixels(win.ren, ctypes.byref(one_px), 0x16462004, buf, 4)
        assert rc == 0
        a, b, g, r = buf.raw[0], buf.raw[1], buf.raw[2], buf.raw[3]
        # same pixel-perfect check as the Windows-verified color packing,
        # now confirmed against a real system-installed SDL2 on Linux too
        assert (r, g, b) == (0xE2, 0x89, 0x5F)
    finally:
        win.close()




class _FakeWindow:
    """A minimal stand-in carrying only camera_x/camera_y, so camera and
    tilemap logic can be tested without ever opening a real window (SDL2
    or tkinter) - this sandbox has no display."""

    def __init__(self, camera_x=0.0, camera_y=0.0):
        self.camera_x = camera_x
        self.camera_y = camera_y


def test_apply_camera_offsets_by_window_camera_position():
    win = _FakeWindow(camera_x=50, camera_y=30)
    assert _apply_camera(win, 100, 80) == (50, 50)


def test_apply_camera_defaults_to_no_offset():
    class NoCamera:
        pass

    assert _apply_camera(NoCamera(), 10, 20) == (10, 20)


def test_apply_camera_handles_negative_camera_position():
    win = _FakeWindow(camera_x=-20, camera_y=10)
    assert _apply_camera(win, 0, 0) == (20, -10)


def test_load_tileset_reuses_spritesheet_logic():
    sheet = _load_tileset(str(_REPO_ROOT / "examples" / "run_sheet.png"), 16, 16)
    assert (sheet.cols, sheet.rows, sheet.count) == (4, 1, 4)


def test_tilemap_placements_computes_grid_positions_and_skips_negative_cells():
    grid = [
        [0, 0, 1],
        [0, -1, 1],
    ]
    placements = _tilemap_placements(grid, 16, 16)
    assert placements == [
        (0, 0, 0), (0, 16, 0), (1, 32, 0),
        (0, 0, 16), (1, 32, 16),
    ]


def test_tilemap_placements_applies_offset():
    grid = [[0]]
    placements = _tilemap_placements(grid, 16, 16, offset_x=100, offset_y=200)
    assert placements == [(0, 100, 200)]



def test_apply_gravity():
    out = run_and_capture(
        """
        let vy = 0
        vy = apply_gravity(vy, 980, 0.1)
        print(vy)
        """
    )
    assert out.strip() == "98.0"


def test_apply_friction():
    out = run_and_capture(
        """
        let v = 100
        v = apply_friction(v, 0.9)
        print(v)
        """
    )
    assert out.strip() == "90.0"


def test_integrate():
    out = run_and_capture(
        """
        print(integrate(0, 50, 0.1))
        """
    )
    assert out.strip() == "5.0"


def test_clamp():
    out = run_and_capture(
        """
        print(clamp(15, 0, 10))
        print(clamp(-5, 0, 10))
        print(clamp(5, 0, 10))
        """
    )
    assert out.strip().splitlines() == ["10", "0", "5"]


def test_physics_step_semi_implicit_euler():
    out = run_and_capture(
        """
        let step = physics_step(0, 0, 10, 0, 0, 980, 0.1)
        print(step)
        """
    )
    # semi-implicit Euler: vy updates first (0 + 980*0.1 = 98), then
    # position uses the *new* velocity (0 + 98*0.1 = 9.8)
    assert "9.8" in out
    assert "98" in out


def test_physics_step_no_acceleration_is_plain_motion():
    out = run_and_capture(
        """
        let step = physics_step(0, 0, 5, 0, 0, 0, 1)
        print(step[0], step[2])
        """
    )
    assert out.strip() == "5.0 5.0"
