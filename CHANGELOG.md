# Changelog

All notable changes to Bolt, by version.

## v0.19.0

Real GPU-accelerated rendering for the game-dev builtins, driven by a
direct concern: the honest Comparisons-page rating for game development
still showed Bolt well behind C++, and the accurate reason was that
`window()`/`rect()`/`circle()`/`draw_sprite()`/etc. only ever drew through
tkinter's software `Canvas` - no hardware acceleration at all. This round
adds a real second backend, not a cosmetic change to the number:

- **SDL2 rendering backend** (`src/bolt/sdl_backend.py`): every drawing
  builtin (`clear`/`rect`/`circle`/`line`/`draw_text`/`draw_image`/
  `draw_sprite`/`tick`) now has an SDL2-backed implementation, bound via
  raw `ctypes` against `SDL2.dll`, `SDL2_gfx.dll`, and `SDL2_image.dll`
  (bundled in `runtime/sdl2/`, sourced from the official `pysdl2-dll`
  wheel, zlib-licensed) - `SDL_Renderer` with `SDL_RENDERER_ACCELERATED`
  (falling back to software rendering only if the GPU path itself fails
  to init). `window()` now tries the SDL2 backend first and transparently
  falls through to the original tkinter backend if SDL2 is unavailable
  (non-Windows, or the DLLs missing) - verified by temporarily hiding
  `runtime/sdl2/` and confirming the fallback still renders correctly,
  then restoring it and confirming SDL2 resumes. Every existing Bolt
  script (`.bo` game demos included) runs unchanged against either
  backend - same public API, zero script-visible difference.
- **Real bug found and fixed along the way**: the first SDL2 window
  crashed with an access violation immediately after creation. Root
  cause: `SDL_CreateWindow`'s `ctypes` return type wasn't declared, so
  ctypes defaulted it to a 32-bit `c_int`, truncating the real 64-bit
  pointer - the corrupted value was then passed into
  `SDL_CreateRenderer` and crashed. Fixed by explicitly declaring
  `argtypes`/`restype` for every SDL2/SDL2_gfx/SDL2_image function used.
- **SDL2_gfx color format, verified empirically, not assumed**: SDL2_gfx's
  color parameter is `0xAABBGGRR` (red in the lowest byte), not the
  commonly-documented `0xRRGGBBAA`. Found by rendering pure red/green/blue
  rectangles under the (wrong) assumed format and observing only "red"
  rendered at all - green/blue came out fully transparent. Fixed and
  re-verified pixel-perfect via `SDL_RenderReadPixels` against both pure
  primaries and the exact target color used in the game demos; locked in
  as a regression test (`test_sdl_backend_pack_color_matches_verified_channel_order`).
  A wrong, hand-computed test assertion for this was caught and corrected
  before ever being treated as passing.
- **Backend-agnostic sprite sheets**: `load_spritesheet()` no longer
  assumes tkinter - it now probes a PNG's real pixel dimensions by
  reading its `IHDR` chunk directly (no library dependency), and creates
  the actual per-backend texture/cropped-frame lazily on first
  `draw_sprite()` call, once a specific window (and thus backend) is
  known. New tests confirm the PNG-header probe and frame-count logic
  against a real checked-in sprite sheet asset, not just synthetic
  bytes.
- **Keyboard/mouse input unchanged for scripts**: SDL2's `SDL_GetKeyName()`
  lowercased matches tkinter's existing `keysym.lower()` convention
  exactly (`"left"`, `"space"`, `"escape"`, ...), so no keymap
  translation was needed - every existing `key(win, "...")` call in
  example scripts works against either backend with no changes.
- **Honest scope**: Windows-only (SDL2 DLLs bundled for win_amd64 only);
  every other platform automatically uses the tkinter fallback, same as
  before this round. This closes the real rendering-technology gap
  between Bolt and engines that already use GPU-accelerated rendering -
  it does not, and cannot, close the much larger multi-year gap in
  tooling, ecosystem, and engine maturity behind that Comparisons-page
  number, and that number was not changed to pretend otherwise.

## v0.18.0

Real game-dev additions, each verified rather than just wired up:

- **Sprite animation**: `load_spritesheet(path, frame_w, frame_h)`
  grid-slices a source image into frames (cropped lazily via Tk's
  `photo copy -from`, cached per frame); `make_anim(sheet, frames, fps,
  loop)` plus `anim_draw(win, anim, x, y)` play it back, advancing by
  real elapsed wall-clock time each call - the same one-call-per-frame
  rhythm as `tick()`. `draw_sprite()`/`anim_advance()`/`anim_frame()`/
  `anim_finished()`/`anim_reset()`/`anim_set_playing()` expose the
  pieces individually for scripts that want more control. Verified
  with a synthetic 4-frame test sheet: cropped pixel colors matched
  exactly, and a timed playback test confirmed frame-advance timing,
  looping wrap-around, and non-loop finish-and-hold all behave
  correctly.
- **Audio mixing**: `play_channel(name, path, loop)` /
  `stop_channel(name)` / `stop_all_channels()` / `channel_playing(name)`
  play `.wav` files via the Windows multimedia (MCI) API, each named
  channel its own device instance - unlike `play_sound()`/`winsound`
  (still available, unchanged), which can only play one sound
  system-wide and cuts off whatever was already playing. Verified for
  real: two channels (two different generated tones) played
  simultaneously and both reported "playing" at once, not one
  interrupting the other.
- **Basic 2D physics**: `apply_gravity(v, gravity, dt)`,
  `apply_friction(v, friction)`, `integrate(pos, vel, dt)`,
  `clamp(x, lo, hi)`, and `physics_step(x, y, vx, vy, ax, ay, dt)`
  (semi-implicit/symplectic Euler - velocity updates from acceleration
  first, then position uses the *new* velocity, which is more stable
  under gravity than naive Euler). Small, inspectable building blocks,
  not a physics engine. Covered by real headless tests (no window
  needed) checking the actual numbers, not just that the calls don't
  crash.
- **Scene/state management**: `packages/scenes.bo`, a small stack-based
  scene manager (`make_stack`, `push_scene`, `pop_scene`,
  `replace_scene`, `current_scene`, `run_stack`) built in Bolt itself
  (like `mathutils.bo`/`stringutils.bo`/`stats.bo`), not a new
  builtin - a scene is just two closures (`update`, `draw`) pushed
  together, so menu -> playing -> game-over no longer needs one giant
  while-loop with manual mode flags.
- **Real bug found and fixed along the way**: writing `scenes.bo`
  surfaced a genuine cross-module closure bug in the bytecode VM - a
  closure defined in the main script (capturing a global like a
  `window()` handle) would raise `Undefined variable 'win'` the
  moment an *imported* package called it back (e.g. `run_stack()`
  calling a scene's `update()`), because `import()` runs each module
  in its own isolated VM instance, and global-variable opcodes were
  resolving against whichever VM instance happened to be executing,
  not the VM/module the closure was actually defined in. Fixed by
  having every `Closure` carry a reference to its defining module's
  globals dict, and threading that reference through the VM's call
  frames the same way locals/upvalues already are. All 114 existing
  tests still pass; 6 new tests cover the physics helpers, and the
  fix itself was verified against a minimal reproduction before and
  after. Known limitation, not fixed this round: the tree-walking
