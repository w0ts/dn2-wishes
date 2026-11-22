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
| boot from reset, 800 M instructions (the farm, `scripts/emu_lzma7_boot.py`, the build's own syx as flash) | PASS: the bytes pushed over DSPI are `0x03` + section 7 exactly; no fault; 9 task creations, as the aPLib build |
| the same with a corrupt LZMA stream (one byte flipped, section sum redone, test file only) | PASS: refused (`0x100000`), nothing pushed, the boot goes on to 800 M with 9 task creations, no fault |
| time to the DSP's program (emulator instructions, power-on to the last byte pushed) | aPLib 69.1 M, LZMA 313.6 M: **+244.5 M instructions**; the depack alone 25.3 M to 269.8 M |

The **time** is not measured: the instruction counts are. At the ColdFire's 250 MHz (part marking) and 1 to 3
cycles per instruction, +244.5 M instructions is about **+1.0 to +2.9 s before the DSP has its program**, so
before the first sound. Only the unit can tell the real figure.

## The cache: decoded once, kept on the +Drive (2026-11-11, branch lzma-cache)

The User found the boot slower ("lzma is slower") and asked for the decode to happen once. Since then the first
boot of a build decodes as above and writes the program to the +Drive. Every later boot reads that copy instead
of decoding. The study behind it is `scratch/room/smaller-image.md`, option A-eMMC.

**The eMMC is not up where stock uploads.** Stock 1.12's boot routine calls the uploader at `0x400cf086`. It
sets up the eMMC driver only after that: `0x4012bddc`, then `0x4012be52`, which clears the ready flag
`0x4461c68c` and sets it at its end (`0x4012c3b4`), then `0x4012c438` and `0x4012c620`. All its paths then meet
at `0x400cf0f2`, `move.l %d0,0x4243989c`: five `bra`s plus the fall-through, and no other jump into what follows.
The uploader takes no arguments, and the routine never uses its answer. So the upload moves:

- **`0x400cf086`**: its `jsr 0x400cf4b0` becomes three `nop`s.
- **`0x400cf0f2`**: becomes `jsr dn7_late` (`csrc/waverider/lzma7late.S`). That stub replays the store and jumps
  to the uploader, which returns to `0x400cf0f8`. Stock writes `d0` and `d1` there before reading them.
- **Nothing runs between the two points** but the eMMC's set-up. The DSP still has its program before the rest
  of the boot.

**`dn_depack7`, for our LZMA section 7** (`csrc/waverider/lzma7cache.c`):

1. **`dn7c_load`:** when the +Drive is up, it reads the header sector. A header is valid when:
   - its magic is `DN7C` and its version 1;
   - its id matches this firmware's section 7 (see below);
   - its length and CRC-32 match the shipped `DN7Z` header's;
   - its own CRC-32 checks.

   It then reads the program in the driver's 64 KB calls and checks it with the **shipped** CRC-32, the same check
   the decode passes. Answered: `dn7_status` 8.
2. **Otherwise:** the decode, as before. After the decode passes its checks, `dn7c_store` writes the copy:
   1. the header sector cleared;
   2. the program, whole sectors;
   3. the header, **written last**.

   A failed write stops there: the next boot decodes again.

| sectors | what |
|---|---|
| `0x5FF200` (v0.69.2; `0x6E8000` before, moved once at the first boot: `docs/memory-map.md`) | the header: `DN7C`, version, length, CRC-32 of the program, the id (the stored section 7's first 24 bytes: its length, its byte sum, the `DN7Z` header), the CRC-32 of those 40 bytes |
| `0x6E8001` .. `0x6E8800` | the program (up to 1 MiB; 1,005,956 B today: 1,965 sectors) |

**The id is not a sha256.** Computing one at power-on over 528 KB would cost part of what the cache saves. The id
above changes with any other stream (its length, its sum or its CRC-32). Each copy is then checked against the
shipped CRC-32 before it is used, so a stale copy is as safe as a decode: both pass the same check.

- **Invalidation:**
  - **a new firmware:** another id, so the copy is not used. Decoded and rewritten at its first boot.
  - **ERASE MOD DATA:** trims the range. It is job 7 in `csrc/sampler/erase.c` (after the inserts' records,
    before the bulk), it is in `er_inside`, and the verify samples it.
  - **a factory reset or FORMAT +DRIVE:** never reach the range (`docs/drive-storage-research.md`). The copy
    stays valid only for the same section 7.
- **Failures:** a +Drive that is not up, a failed read, a damaged or cut copy: all end in the decode. A failed
  write: the boot goes on, and the next boot decodes. No NOR flash is written.
- **On the unit:** `dn7_status` (8 the copy, 2 the decode), `dn7c_state` (1 loaded, 2 none valid, 3 written,
  4 a write failed, 5 a read failed) and `dn7c_why` are in the build's layout, for a PEEK.

### Measured (the cache)

| check | result |
|---|---|
| `test/test_lzma7cache.py` (host build, the driver played) | 18 pass: written with the header last; read byte for byte without a write; magic, id, length, header check, body and last byte damaged: decoded and rewritten; another build's copy and another stream of the same program: refreshed; a write failing at the header, the first, the fourth or the seventh call: decoded, and no wrong program on any later boot; a failed read; no +Drive; an erased copy (0x00 and 0xFF); the largest program |
| `test/test_lzma7.py` | 15 pass (unchanged) |
| `scripts/emu_lzma7_cache.py`, boots from reset (the build's syx as flash, the farm) | **PASS**, 5 boots on one played +Drive: **first** decoded and written (18 writes, header first and last); **second** read from the copy, no write, no decode; **corrupt** (a program byte) decoded (`why` 5) and rewritten; **newid** (another build's header) decoded (`why` 2) and refreshed; **writefail** decoded, state 4, the boot ran to 800 M instructions with no fault. In every boot: the SHARC got `0x03` + section 7 exactly, one upload, entered after the eMMC's set-up (`0x4012be52` at 27,121,726, the uploader at 27,123,044) |
| ship gate `--only erase` (the farm, the build's own UI snapshot) | PASS: 20,461 TRIMs only in the mod's regions, the copy's range with them and covered exactly, headers first; every region verified; 9 power-ons after cuts; 49 checks (a partial run, not a gate) |
| the emulated driver at the new upload point | ready 1, 48,340,992 sectors (digikit's eSDHC model) |
| the upload, the uploader's entry to its return (instructions) | decode **292.6 M**, copy **35.5 M** |
| power-on to the last byte pushed (instructions) | decode 318.4 M, copy **61.3 M**: **−257.1 M** (`docs/lzma7.md` above: aPLib 69.1 M on the earlier tree) |

In those counts the played driver costs nothing. **The eMMC's own read time for 1,006,080 B is not measured**: the
emulator plays the driver. The stock read moves each 64 KB call by eDMA from the eSDHC. Our buffer is not
16-byte aligned, so each call also goes through the driver's bounce buffer and a `memcpy` (counted above).

**Estimate, not measured:** −257 M instructions is about 1.0 to 3.1 s less at 250 MHz and 1 to 3 cycles each,
minus the eMMC's read of about 1 MB. The first boot after a new firmware adds the 1 MB write on top of the
decode. Only the unit can give the boot-to-first-sound figure.

## Not verified

- The decode on the real ColdFire (caches, SDRAM), and the real delay to the first sound: only the unit.
- The cache on the unit: the eMMC read and write times, the moved upload's order on the real card's set-up times
  (the emulator's set-up returns at once), and a boot with the copy versus a decoding boot.
- The ship gate's own boot step fails on every 1.12 build in the bench (the start-up animation check);
  the boot above is the farm's 1.12 route, not the gate's step.
- The full ship gate was not run.
