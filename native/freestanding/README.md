# Freestanding roadmap — stage 0

**What this proves, verified for real:** the actual toolchain path
(assemble → flat binary with a valid boot signature → boot in an
emulator with no OS underneath it) works on this machine, end to end.

```
powershell -File native\freestanding\build.ps1
```

This assembles `boot.asm` with NASM into a 512-byte flat binary ending
in the `0x55 0xAA` boot signature — the exact mechanism every x86
bootloader (Linux's, Windows's, GRUB's) relies on to get control
before any OS exists — then boots it in QEMU and captures its serial
output. Verified output:

```
BOLT FREESTANDING: no OS, no libc, boots on bare x86.
```

That string is written by code running directly on emulated
bare-metal x86, with nothing else present: no OS, no libc, no
runtime. It's real-mode 16-bit assembly, not C yet, and it doesn't do
anything beyond prove it's alive — this is the foundation stage, not
a kernel.

## Honest scope

This is **stage 0 only** — a verified proof that the toolchain works,
not yet a bridge from Bolt source to bare metal. It is hand-written
NASM assembly, unrelated to `native/bolt.c`'s C code today. The
stages that would actually connect this to Bolt, in order:

1. **A freestanding C stage**, compiled with `-ffreestanding
   -nostdlib` (no libc calls at all — no `malloc`, no `printf`, no
   file I/O) and linked with a small assembly entry stub like this
   one, proving a *C* program (not hand-written assembly) can run
   bare-metal. Needs a real cross-toolchain (`i686-elf-gcc` or
   similar) — MSVC alone can't emit ELF/multiboot output, which is
   why this stage used NASM directly instead.
2. **Add raw pointer / `unsafe` support to the Bolt language and
   `native/bolt.c`'s interpreter**, since a kernel needs to place
   values at exact physical addresses (page tables, MMIO registers) —
   the current GC'd list/map/value model has no way to do that.
3. **A `--freestanding` flag for the native compiler** that emits
   code against stage 1's freestanding C runtime instead of the
   normal hosted one (no Win32 calls, no libc, no `pyimport`-style
   assumptions).
4. **A real "hello from Bolt" kernel**: a `.bo` script compiled
   through stage 3, linked with stage 1's entry stub, booted and
   verified the same way this stage was — actual output captured
   from a real boot, not claimed.

Each future stage should be verified the same way this one was: by
actually assembling/compiling and booting it, not by describing what
it would theoretically do.
