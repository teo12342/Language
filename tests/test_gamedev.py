from pathlib import Path

from bolt.builtins import (
    _apply_camera,
    _load_spritesheet,
    _load_tileset,
    _probe_image_size,
    _sprite_frame_count,
    _tilemap_placements,
)
from bolt import sdl_backend

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
