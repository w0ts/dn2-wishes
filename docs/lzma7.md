# Section 7 stored as LZMA (2026-11-11, branch lzma-dsp)

The DSP program (section 7) is stored as LZMA instead of aPLib. MAIN OS's SHARC uploader decodes it into RAM at
every power-on. **The USB upgrade image is 147,460 B smaller**, with the same unpacked DSP program byte for byte.
No flash is written by anything here. The study behind this is `scratch/room/smaller-image.md`, option S7.

## How it works

- **The uploader:** stock MAIN OS uploads the DSP program at `0x400cf4b0`, at every power-on:
  1. It reads section 7 from flash into a 1 MiB heap buffer.
  2. It writes `0x03` at the start of a second 1 MiB buffer.
  3. It depacks after that byte with stock's aPLib routine, `0x40136820(src, dst) -> length`.
  4. It pushes `length + 1` bytes to the SHARC over DSPI. A length + 1 over 1 MiB goes to its error path:
     both buffers freed, the DSP left in reset, error code 3 returned.
- **One edit:** that call (`jsr 0x40136820` at `0x400cf73a`, 6 bytes) becomes `jsr dn_depack7`
  (`csrc/waverider/lzma7.c`, linked into the page renderer's CODE chunk). Same arguments, same answer.
- **The format** (`dnfw.codec.lzma7`), after the section's own `[u32 length][u32 sum]` header: the magic
  `DN7Z`, the unpacked length, the LZMA props byte (lc 0, lp 1, pb 1), three zero bytes, a CRC-32 of the
  unpacked bytes, then a raw LZMA1 stream.
- **What `dn_depack7` does:**
  - A stream without the magic is stock's: it goes to `0x40136820` untouched, so an aPLib section 7 still
    works with this MAIN OS.
  - Ours is decoded into the uploader's own buffer (the dictionary is the output itself) and answered only
    if its length and CRC-32 match the header.
  - Anything else answers `0x100000`, which the uploader's own bound turns into its stock error path. A bad
    header, out-of-range props, a cut or corrupt stream, a CRC mismatch, or no heap all end there.
  - **Fail-safe result:** the DSP gets nothing, while MAIN OS, the UI and USB go on, so a normal Transfer
    reflash recovers.
- **RAM:** the decoder's 16 KB probability table comes from stock's `malloc` for the call and goes back
  through `free`, the uploader's own allocator. Stock's `malloc` answers in `d0`, so the call is typed as
  returning an integer. GCC's m68k ABI would read a pointer from `a0`; that bug faulted the first emulator
  boot.
- **The tools:** `dnfw.container.section` packs the format (`compress_lzma7`) and unpacks it in
  `Section.unpack`. So inspect, preflight, the gate's DSP identity and the runner all see section 7 as
  before. The waverider mod asks for it through `Result.codecs`. `firmware.verify` accepts the stream only in
  section 7.

## Measured

| check | result |
|---|---|
| USB upgrade image (the 2 MiB receive buffer) | 1,943,341 B used, **+153,811 B free**; the same tree with aPLib: +6,351 B. **147,460 B gained** |
| section 7 stored | 520,680 B (aPLib: 669,680 B); unpacked 982,522 B, unchanged |
| the decoder in MAIN OS's chunk | 1,808 B of code, 64 B CRC table, 12 B data (gcc -mcpu=5475 -Os, the chunk's flags) |
| `test/test_lzma7.py` | 15 pass: the C decoder (host build) and the Python codec agree on decodes, on the aPLib hand-off, and on every refusal |
| ship gate `--only preflight,code-fresh,rebuild,dsp-identity,hwrules,symbols,coldfire,overbridge` | each PASS (a partial run, not a gate) |
| boot from reset, 800 M instructions (gpufarm, `scripts/emu_lzma7_boot.py`, the build's own syx as flash) | PASS: the bytes pushed over DSPI are `0x03` + section 7 exactly; no fault; 9 task creations, as the aPLib build |
| the same with a corrupt LZMA stream (one byte flipped, section sum redone, test file only) | PASS: refused (`0x100000`), nothing pushed, the boot goes on to 800 M with 9 task creations, no fault |
| time to the DSP's program (emulator instructions, power-on to the last byte pushed) | aPLib 69.1 M, LZMA 313.6 M: **+244.5 M instructions**; the depack alone 25.3 M to 269.8 M |

The **time** is not measured: the instruction counts are. At the ColdFire's 250 MHz (part marking) and 1 to 3
cycles per instruction, +244.5 M instructions is about **+1.0 to +2.9 s before the DSP has its program**, so
before the first sound. Only the unit can tell the real figure.

## Not verified

- The decode on the real ColdFire (caches, SDRAM), and the real delay to the first sound: only the unit.
- The ship gate's own boot step fails on every 1.12 build in the bench (the start-up animation check);
  the boot above is the farm's 1.12 route, not the gate's step.
- The full ship gate was not run.
