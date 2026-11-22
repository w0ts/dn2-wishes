# SAFE MODE with Elektron's stock DSP program: a study (not built)

The User, 2026-11-22: in SAFE MODE, make the unit run Elektron's **stock** DSP program (a "dual boot": stock's DSP
image instead of ours when SAFE MODE is entered). This note says whether it can be done, where the image would come
from, what the ColdFire side needs, and the risk. Nothing here is built.

## Today (docs/safe-mode.md)

In SAFE MODE the ColdFire runs stock Digitone II OS 1.12 byte for byte (the kernel's unpatch table), and the DSP gets
**no program**: override O1 turns the uploader's `jsr 0x40136820` (stock's aPLib depack) into `jsr sm_refuse7`,
which answers `0x100000` so the uploader takes its own error path. Stock's aPLib never reads our section 7, which is
LZMA (`DN7Z`), not aPLib. The unit boots to the UI without sound.

## Measured (2026-11-22, `dnfw.firmware.load`, `dnfw.image.bootstream`; build v0.69.1 440085e4)

| | stock 1.12 | ours (v0.69.1) |
|---|---:|---:|
| section 7 as stored in the `.syx` | 602,076 B (aPLib) | 549,672 B (LZMA) |
| the boot stream it decodes to | 836,956 B, 95 blocks (sha256 `336e340a...`) | 1,042,988 B, 190 blocks |
| the stream, LZMA-packed (preset 9e) | 479,828 B | - |

- Ours is not stock plus appended blocks only: 95 blocks are inserted before stock's final one, one stock block
  changes kind (a fill becomes a payload), and **67,578 of the bytes stock loads are loaded differently in 457 runs**
  (our patches, tables and the stock code changed under the `stockout` rule). A record of what to put back (address,
  length, stock's bytes) is 71,234 B, 62,120 B LZMA-packed. It changes with every build that changes the DSP.
- Our USB upgrade room is **57,356 B** (v0.69.2). Neither the stock stream (480 KB packed) nor the diff (62 KB packed)
  fits in the firmware. **The stock DSP program cannot ship inside our firmware.**
- The uploader's buffer holds DN7_MAX = 1,048,575 B: stock's 836,956-byte stream fits.

## Where the stock image could come from

1. **Inside our firmware:** no (sizes above).
2. **Rebuilt on the unit from ours:** needs the 62 KB diff, which is the same size problem, and it would come from a
   build that may be the broken one. No.
3. **A copy on the +Drive** (recommended): stock's boot stream (836,956 B, 1,635 sectors) in a range of ours below
   `0x600000` (`docs/memory-map.md`: `0x5EE800..0x5FEFFF` is free), with a header (magic, length, CRC-32). It has to
   reach the +Drive once from outside: the patcher page already holds the stock `.syx` the User flashes from, and our
   SysEx link already carries samples to the +Drive (whether a 837 KB image fits its commands as they are is not checked). So the patcher would send it once, after the
   first flash of a build that knows the place. The User would not need to do anything else; a unit without the copy
   behaves as today.

## What the ColdFire side needs (SAFE MODE only; the normal boot is untouched)

- **The upload after the eMMC's set-up.** Stock uploads the DSP program at `0x400cf086`, *before* the eMMC driver is
  set up: the +Drive cannot be read there. Our normal boot moves the call to `0x400cf0f2` (`dn7_late`); SAFE MODE puts
  stock's bytes back, so the upload is early again. A new kernel override (O5) would move the upload late again, to
  a kernel-side trampoline (`dn7_late` lives in the page renderer's chunk, which SAFE MODE does not run).
- **O1 changed:** `sm_refuse7` becomes `sm_stock7(src, dst)`: read the copy's header; when its magic, length and the
  CRC-32 of the 836,956 bytes (read into `dst`, the uploader's own buffer) match the kernel's constants for stock
  1.12's stream, answer the length; anything else (no copy, a failed read, a wrong CRC) answers `0x100000` as today.
  Stock's own uploader then sends `0x03` + the stream to the SHARC as it always does.
- **Nothing else:** the ColdFire in SAFE MODE *is* stock 1.12, so it drives stock's DSP program with stock's own
  frames, TDM and replies. No code of ours runs on either processor.
- Size: a +Drive read loop, a CRC-32 (the kernel has one), the trampoline: a few hundred bytes in the kernel chunk
  (`0x476F8100..`, about 10 KB used of 32 KB).

## Risk

- The SAFE path gains a +Drive read at boot. A read that fails or a copy that does not check out falls back to
  today's behaviour (no DSP program). The one new failure mode is a read that **hangs** in the stock driver at the
  upload point: the SAFE boot would hang where today it boots silent. The normal boot already reads the +Drive at
  that point every boot (`dn7_late`: the DSP copy, SAFE MODE's record), so the driver is proven there, but SAFE MODE
  exists for when something is wrong, and the +Drive could be the wrong thing.
- Stock ColdFire + stock DSP stream is the known-good pair (a stock unit). The CRC guarantees the bytes are stock's.
- Mitigation: SAFE MODE's own counter already gives up after `safe_tries` 2 and boots normal; a kernel flag could skip
  the stock DSP on the second SAFE try in a row, so a hang there costs one power cycle, not a loop.

## How it would be proven (when built)

- `safeboot` part s: a +Drive with the stock copy: SAFE MODE applied, the SHARC receives `0x03` + stock's stream byte
  for byte (the emulator compares the pushed bytes with stock section 7), the UI composes; part s2: a copy with one
  byte wrong, no copy, a failed read: no DSP program, as today; part s3: the normal boot never reads the copy.
- On the unit: SAFE MODE (STOP held at start) makes sound with a stock sound; leaving it (NO) boots ours.

## Verdict

Feasible, with the stock image on the +Drive (sent once by the patcher), a late upload and a checked read in the
SAFE MODE kernel. It cannot come from our firmware itself. Not built: waiting for the User's go.
