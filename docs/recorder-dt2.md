# The RECORDER as the Digitakt II's own SAMPLING screens (2026-11-10)

The User: "check the recorder screen from digitakt and extract it from digitakt firmware or
rebuild one for one (i prefer first option)". Measured on Digitakt II OS 1.16 (stock, sha256
`278541e4…`) and Digitone II OS 1.12. The User chose route B ("call for call") on the evidence
below. Code: `csrc/sampler/rec_dt2.c`; `smp_page.c`'s `rec_screen_draw` hands it every page except
the BOUNCE REC panel and the FILE NAME character grid (FUNC held), which stay ours.

## Route A (lift the DT2's view): not feasible as a whole

The DT2's sampling screen is the C++ class `SamplerView` (RTTI name at `0x40229737`, typeinfo
`0x401eebe4`, primary vtable `0x401eec54`, 19 slots; 7 more vtables for its listener bases,
constructor `0x40020fd6`, destructor `0x4019bc7a`). Its draw is vtable slot 4, `0x40021de0`, one
3,726-byte function with a switch over its pages (RECORDER, RECORDING, NORMALIZING, TRIM).

- **Its drawing is the shared widget library.** All 15 draw primitives it calls have a unique DN2
  1.12 twin (masked-byte match; the library sits at DT2 = DN2 − `0x1c54`), and its fonts and
  sprite bitmaps are in DN2 1.12's image byte for byte (tables below).
- **Its data is the DT2's.** The draw calls 24 DT2-only functions (about 1.9 KB: the `Recorder`
  singleton `0x4019988a` and its state `0x40015f6c`, the recorder status getters `0x400cd6ce..`,
  the DT2 sampler parameters `0x4004cc42..`, three waveform lane drawers), reads 8 DT2 RAM
  globals (`0x44f34010..`, `0x44d2e6f4`) and a DT2-layout `this` (waveform peaks at +420..+1936,
  page state +4512, clip hold +2440).
- **The rest of the class is the DT2's sample subsystem.** Its key handler (slot 2,
  `0x40022c6e`) saves takes through `ekFS` (`/recorded/REC0000`, `Save recording`, `PLEASE
  WAIT`); `Recorder`, `SampleManager`, `AssignPrompt` and the `ekFS` classes do not exist on the
  DN2 (docs/dt2-port-map.md: 150-240 KB of ColdFire code). From the eight vtables, the call graph
  reaches 107 functions (14 KB) with no DN2 twin.

So lifting the class means lifting the DT2's sample stack. Lifting only the draw would mean
3.7 KB of foreign binary plus 1.9 KB of helpers relocated, about 40 call and data sites patched,
and a fake `SamplerView` filled from rec.c: possible, brittle, not regenerable.

## Route B, call for call (what is built)

The DT2's draw was traced in digikit's emulator (`tools/guirun.py` with a hook on each primitive,
arguments and strings logged, filtered to calls returning into the view): the exact display list
of each page. `rec_dt2.c` makes the same calls to the same stock routines at their DN2 1.12
addresses, with the same fonts, sprites and coordinates; only the values are ours.

| DT2 1.16 | DN2 1.12 | what |
|---|---|---|
| `0x40113ae8` | `0x4011573c` | text with a font object; align 0 left, 2 centre, 4 right, 8 inverted |
| `0x401137a4` | `0x401153f8` | text with a font record (the big RECORDER) |
| `0x40113aa4` | `0x401156f8` | plain text (TRIM's bottom labels) |
| `0x40112568` | `0x401141bc` | vertical line x, y0, y1, colour (1, 0, -1 inverted) |
| `0x40112cb2` / `0x40112b9c` | `0x40114906` / `0x401147f0` | outlines |
| `0x40112e4e` | `0x40114aa2` | dotted outline (REC NOW!) |
| `0x40112ece` / `0x40112fe0` | `0x40114b22` / `0x40114c34` | fill / rounded fill |
| `0x40113e88` | `0x40115adc` | blit a frame |
| (set pixel) | `0x40113e70` | the two dots between R.STRT and ARM |

Fonts: records `0x402a4f6c` / `0x402a6c30` / `0x402a96a0` / `0x402a5d60` = DN2 `0x4028ffdc` (big),
`0x40291ca0` (labels), `0x40294710` (values), `0x40290dd0` (the name); font objects are
`{0x402069dc, record}` (DT2 vtable `0x4021cb58`). Sprites: stock frame objects `{0x402069c4, w,
h, 1, columns, mask, 0}`, one 32-bit word a column: ARM off/on 17×9 (`0x402a1c3c`, `0x402a1c80`),
TRIM ends 4×5, speaker 7×5, play mode 12×9, pencil 9×9, ASSIGN's dots 11×2.

### The pages

| page | as the DT2 | ours in it |
|---|---|---|
| RECORDER | title, meter box with the level cut out in dark and THRES's inverted tick (x = 65 + THRES/2), eight places, REC NOW! box, ARM switch | A SRC, B CHAN as MONO over L+R / L / R (the DN2 records one channel), D THRES, **E INTO** (SAMP n) in the DT2's MON place, F R.LEN (MAX or n STEPS over its seconds:centiseconds, 66:00 at most), G R.STRT, H ARM (on while the DSP is armed or recording) |
| RECORDING | header, frame, the take's lane, RECORDING / time / YES: STOP | the lane from rec.c's 120 columns; RECORDING kept lit (the DT2 blinks it) |
| TRIM | keys bar inverted, play-mode icon, frame, lane, \|◂TRIM ZOOM POS TRIM▸\| | the slot's overview (or the analysis' 1,024 columns zoomed); the ends cut away inverted; the preview's column inverted (`trim_head_x`); ZOOM reads 2X/4X/8X when zoomed |
| FILE NAME | inverted title with the pencil, the name with the cursor's letter inverted, the keys | 20 characters in view, `>>` when there is more; no SETTINGS:RANDOM (we have none) |
| ASSIGN | AssignPrompt's box over TRIM | as the DT2 |
| SAVING / NORMALIZING | the DT2's line | with our progress bar under it |

When YES cannot record, the REC NOW! box says why instead (NO DSP / STATUS or LINK, NO ROOM / NO
SLOT, WAITING for a Q.REC take, TRIG RECORDING for a BOUNCE trig take): the DT2 has no such states.

### Checks (emulator, 1.12)

- Pixel diff against the DT2's own screens: the idle RECORDER differs in 145 pixels, all inside
  CHAN and MON/INTO (the values that differ by design); TRIM's frame, bar, icons and labels,
  FILE NAME's title and keys, and ASSIGN's box are the same pixels.
- `recorder`, `recflow`, `rectrig` (ship_gate ColdFire steps) and the SHARC runner: see the
  build's report (dn2mk2-scratch notes).

The emulator holds the frame counter still and has no DSP status: the screenshots poke
`rec_heard`, `rec_link`, `rec_room`, `rec_peak`, `rec_state`, `rec_frames`, `rec_wave` (exported
for that in `coldfire.py` / `cpage.py`) and move the frame counter on to make the page redraw.

## Reproduce the DT2 side

`bench/digikit-up`: `emu.checkpoint make` on `Digitakt_II_OS1.16.syx` (ColdFire only, 400M is
enough), then `tools/guirun.py --slc` (not `--weakptr`: its site is 1.15C's) from that snapshot:
SAMPLING is button 50, YES 10. The CF-only DT2 reads its input as silence, so YES records an
empty take at once: RECORDING, TRIM, YES → FILE NAME, YES → ASSIGN. Encoder turns do not move
the DT2's values in this emulator.
