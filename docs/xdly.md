# XDLY: the owner's cross delay beside the stock delay (OS 1.12 fork, not released)

The Delay page gets a **TYPE** knob on its empty position **G**: **STOCK** (every existing kit)
or **XDLY**, shown in its cell (2026-11-11: STOCK first in the list and at the knob's left end; the stored values stay 0 XDLY, 1 STOCK: `dlt_step`, called from `fx_type_quant`, the kit setter's hook). With XDLY, five of the page's knobs change roles. The header's long
names say so as a knob turns; the knob labels stay stock's (see below):

| knob | XDLY | range |
|---|---|---|
| TIME | **TIME 1**, line 1 (left) | 1 ms .. 10 s, exponential |
| X | not used | |
| WID | **TIME 2**, line 2 (right) | 1 ms .. 10 s, exponential |
| FDBK | **FEEDBACK**, each line's repeats | up to 1.05: past ~95 % they grow into a soft clip and sustain |
| HPF | **MOD**, the cross modulation | each line's time moved by the other's last output, up to half its time either way |
| LPF | **TONE**, the loops' one-pole | 200 Hz .. 20 kHz (optimist's fixed 7 kHz is about LPF 98) |
| REV, VOL | the bus's, as for the stock delay | |

XDLY is optimist's (`firmware/src/fx/insfx/xdly.c`, GPL-3.0-only, the owner's; the idea is the
SOMA LYRA-8's modulated delay: no circuit, no code). There it runs at 44.1 kHz in Q15 with lines of
16384 samples, **0.37 s at most**; on the FM-1 its memory (XDLY MEM FULL / HALF) capped the times.
Here it runs at 48 kHz in float32. Its two lines of 2^19 samples (**10.9 s** each) sit in the stock
delay's own 4 MB sample area in DDR. One of the two delays plays at a time, so the area is free
while XDLY runs. `src/dnfw/xdly/ref.py` spells out every operation:

- x = (L + R) / 2; each TIME followed over ~23 ms, so turning one bends the repeats' pitch, as on tape;
- each loop: a one-pole on its line's last output, times FDBK, plus x, through optimist's soft
  knee (linear to 20000 / 32768, a tanh knee above), clamped to 1;
- each line read linearly between two samples, at its time moved by the other line's last output
  (the cross modulation: a slow chorus at low MOD, metallic FM grit as the repeats build up);
- out L = line 1, out R = line 2: the wet only. The bus mixes it in with VOL and sends it to the
  reverb with REV, as it does the stock delay's;
- nothing the lines held before XDLY started is read (a fill count, optimist's), so a start needs no
  clearing. Once both lines hold only zeros and a block's input is silent, the block is skipped;
- added here: a loop one-pole below 1e-20 is set to 0, so a tail ends at exact 0 and nothing reaches
  the denormal range (optimist rounds toward 0 for the same reason).

Reference renders, dry plus wet at VOL 0.8: `dn2mk2-scratch/wav/xdly/` (a slapback, 300/450 ms,
2 s/3 s, a snare at 375/500 ms, FM grit at 30/45 ms with MOD 100 and FDBK 110, a chorus at
12/17 ms, self-oscillation at FDBK 127, and 10 s/8 s).

## TYPE: stock's record 122

TYPE is stock's record 122, "Delay FX Routing": kit slot 40, range 0..1, default 1, stored with the
kit, sent in the frame (word `0x9c8 + 2 * 40 = 0xa18`; the DSP's frame image `0x25c48c + 0xa18 =
0x25cea4`, low half), shown on no page and read by nothing on the DSP. It is the delay's twin of
the reverb's record 131 that FDN8's TYPE uses (same formatter `0x400e3592`, same flags). **0 is
XDLY, 1 the stock delay**, so every existing kit plays as before.

- The frame mapping was measured in the SHARC runner: one frame word changed at a time, with the
  stock unpack run. Frame words `0xa08..0xa12` reach the delay's parameter struct `0x257934`
  (+0 TIME / 127, +4 X raw, +8 WID / 128, +0xc FDBK / 128, +0x10 HPF / 127, +0x14 LPF / 127).
  `0xa14..0xa18` (REV, VOL, routing) are not in it.
- The Delay page's record list is built at boot at `0x42433ef4` (stock 1.12, `0x400c9f50..`):
  `[113 114 115 116 117 118 0 119 121]`. G (`0x42433f0c`) is cleared there by `clr.l` at
  `0x400c9f68`. Byte-checked in stock 1.12's section 3, loaded at `0x40000400`.
- `csrc/xdly/ui.c`, as `csrc/fdn8/ui.c` does for the reverb:
  - `dlt_poll` puts record 122 at G and names it TYPE / "Delay Type", with value text STOCK / XDLY.
  - While TYPE is XDLY it swaps the long names of 113 115 116 117 118.
  - `dlt_cell` draws TYPE's cell (STOCK / XDLY) and its label.
- **The knob labels cannot follow TYPE**: the FX pages copy their labels when their views are built
  at boot (measured on the Reverb page, `docs/fdn8.md`).

## DSP

The FX bus calls the stock delay with `CALL 0xb8482c (DB)` at sw `0x1c1c58`, followed by two
pushes:
- R4: its DDR state, `0x8005912c`;
- R8: its parameter struct, `0x257934`;
- R12: the bus's I/O descriptor, `0x257e6c`, the reverb's too.

It returns to sw `0x1c1c5f` (the bus pushes `0x1c1c5e`, the return address - 1). **The build
changes only that CALL's target**, to `wr_xdly` (sw `0xbd6400`). `wr_xdly` saves every register it
uses, then does one of three things:

- **TYPE not 0, no clearing pending:** it restores everything and JUMPs to `0xb8482c`. The stock
  delay runs as if called directly.
- **TYPE changed:**
  - To XDLY, it starts at once, with the times set and nothing of its lines read.
  - To the stock delay, it clears the 4 MB sample area, 4096 words a block, with the wet silent
    meanwhile: 256 blocks, 171 ms. Neither an old stock tail nor XDLY's lines come back.
- **TYPE 0:** one block of XDLY into the bus's output pair.

| where | what | size |
|---|---|---|
| L2 `0x200ac800` (sw `0xbd6400`) | `xdly.asm`, generated from `dnfw.xdly.program` | 3,560 B (span 6 KB, to `0x200ae000`, where the per-track inserts' code starts) |
| L1 `0x2e6e00` | its words | 512 B (the last of FDN8's block, which shrank to 2.5 KB) |
| DDR `0x80059130..0x80459130` | its two lines: the stock delay's sample area | 2 x 2 MB, the stock's own |

The stock delay's sample area is `state + 4 .. state + 0x400004`. Measured in the runner: over 40
blocks the stock delay wrote only inside it and in control words after it (`+0x400008 ..`).

**Cost** (the SHARC runner, which charges every access alike):
- the stock delay: 4,748 .. 4,753 instructions a block;
- the stock path through `wr_xdly`: 4,814 .. 4,819 (+66);
- XDLY: 4,942 .. 9,432, mean 6,403 (the knee's tanh runs only on loud samples);
- a clearing block: about 5,130.

XDLY makes up to 6 DDR accesses a sample (2 writes, 2 x 2 reads), so up to 192 a block. **On the
unit a DDR access costs several times an instruction. Unmeasured**: read the system meter's D with
TYPE on XDLY.

## Also the per-track XDLY inserts' engine (2026-11-10)

The same code runs the XDLY inserts on the tracks' buses (docs/inserts.md "On the track's bus"): a MODE
word after its register save; the bus pass swaps an instance's words in for the send's (and back), sets
MODE 1 and enters `wr_xdly` as a leaf call, which runs one block of that instance and returns with
`JUMP (M14, I12)`. The send path (MODE 0) is the one it was, three instructions longer; its
lines' bases are words now
(each instance has its own DDR). Its runner step holds the send path to stock and to the reference as
before.

## Checked, and not

- `test/test_xdly.py`: the DSL program's model equals `dnfw.xdly.ref` bit for bit over 200 blocks,
  with the lines' written words compared word for word. The blocks cover stock, the switch, noise,
  an impulse, loud input into FDBK 127 (the knee), knob moves, the ends, TIME 2 at 10 s (past what
  was written) and the silent skip. A further case runs the switch back (256 clearing blocks, the
  area all 0).
- SHARC runner step `xdly` (`scripts/sharc_xdly_step.py`), on stock section 7 and the build:
  - **TYPE stock**, 40 blocks: every output word, every register at the return and every word
    written are the stock image's, apart from XDLY's own state words.
  - **TYPE XDLY**, 200 blocks: every output word is bit-exact to the reference, and so are the
    lines' written words. Every register the bus left is back.
  - **Switches:** XDLY to stock gives 256 silent blocks; the area is 0 when the clear ends; then the
    stock delay on silence peaks as a fresh one does (0). Stock to XDLY gives exact zeros on
    silence at once.
- **Not checked:**
  - On the unit: the DDR cost, the sound at the DN2's levels, whether the stock delay or another
    task touches its sample area while XDLY runs (the runner saw no such write).
  - In the emulator: TYPE turned to XDLY (its encoders did not move values on the FX pages for
    FDN8, and it builds no frames).
  - The wet level against the stock delay's: XDLY's lines run at unity.
