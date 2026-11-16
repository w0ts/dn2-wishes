# The Machinedrum's machines on the DN2 (v0.17)

PERC's drum machines become the Elektron Machinedrum's own (SPS-1 UW, OS 1.63): the TRX,
EFM and GND machines as DSP2 computes them, read from the owner's copy of the firmware.
v0.11..v0.16 had the owner's Ravel designs *after* the Machinedrum; these are the
Machinedrum.

## Where the algorithms come from

`../md163/research/md-research.md` (outside the repository: it holds Elektron's code)
records the firmware's layout: an MCF5206e host, two DSP56303s, the OS and both DSP
programs as NRV2B blocks. DSP2 synthesises: per track and per 32-sample block it calls
the machine's init, trig and render through three tables, with the words the host's
scale function made from the eight parameters. Its research tools there (a DSP56300
emulator, `emu56k/`) ran each machine's own code and recorded its output for 19..38
cases a machine (`emu56k/golden/`), and wrote an integer model of each machine that
matches that output bit for bit (`emu56k/md_models.py`, `host_scale.py`).

The firmware is Elektron's, so none of it, nor anything copied out of it (tables, golden
output), is in this repository. The build reads the tables it needs from the owner's
file at build time (`dnfw.md.rom`, `MD_OS_BIN`, default `../md163/md_uw_os1.63.bin`), as
it reads the DN2's own firmware; the tests read the golden vectors (`MD_GOLDEN`, default
`../md163/research/emu56k/golden`).

## How a machine is written (`src/dnfw/md/`)

Each machine is a class with `NAME`, `ID` (the Machinedrum's machine id), `PNAMES` and
four DSL steps (`dnfw.perc.dsl`, the same two-backend DSL as PERC: emit mode writes the
SHARC code, run mode is its model):

| step | when | does |
|---|---|---|
| `host(p, L)` | a block with a parameter change or a note | the eight 14-bit inputs (`core.inp`, `INP0..`) -> the host's words W (`core.ws`); `VW['trg']` says whether it is a note (some scale functions send fewer words without one) |
| `init(p, L)` | the machine was just chosen | DSP2's init |
| `trig(p, L)` | a note | DSP2's trig |
| `render(p, L)` | every 44.1 kHz block | 32 samples into the stream at `OUT0` |

Conventions (`core.py`): a Q23 word is a float (w / 2^23); `mpy` is `*`; the limiter is
`sat` (a clamp); 48-bit envelopes and phases are one float, or a 32-bit phase whose top
15 bits index the sine (`SINE_SHIFT`); I3 is the slot's words, I5 is free inside
`render` (`gnd.out_loop` walks the output). Where a product feeds back on itself block
after block and the 56300's truncation sets the rate (an envelope multiplied once a
block), `core.mpy_floor` reproduces the truncation exactly: GND-SN's pitch ramp was
-6 dB without it, 77 dB with it.

## How each is checked

`test/test_md.py` runs every machine in run mode on every golden case (`dnfw.md.bench`)
and holds it to the Machinedrum's output: signal-to-error ratio of at least 60 dB over
the case, or an error under 2^-20 RMS. The SHARC runner then holds the assembled code to
run mode, bit for bit, as for PERC.

Every golden case of every machine passes; the worst case per machine (signal-to-error
over the case, against the Machinedrum's own output; 200 = bit-exact):

| machine | worst (dB) | | machine | worst (dB) |
|---|---|---|---|---|
| TRX-BD | 100 | | EFM-BD | exact pairs (130) |
| TRX-B2 | 119 | | EFM-SD | 111 |
| TRX-SD | 106 | | EFM-XT | 120 |
| TRX-XT | 82 | | EFM-CP | 116 |
| TRX-XC | 75 | | EFM-RS | 106 |
| TRX-CL | 82 | | EFM-CB | 122 |
| TRX-RS | 91 | | EFM-HH | 108 |
| TRX-CP | exact | | EFM-CY | 122 |
| TRX-CB | exact | | GND-SN | 76 |
| TRX-CH, OH | 74 | | GND-NS | 46 (DEC 0: gone in a block; 2^-20 RMS) |
| TRX-CY | exact | | GND-IM | exact |
| TRX-MA | exact | | | |
| TRX-S2 | exact | | | |

What it took:

- **DSP2's own sine, word for word.** DSP2 makes its 32768-word sine at boot with a
  48-bit recursion whose limiter clamps at the trough; from there the table runs 1.5
  indices ahead, and one word (k = 16384) has the wrong sign. The FM machines feed their
  output back into their phase, so one LSB becomes another waveform within a few hundred
  samples. `core.md_sine_words` is that recursion in Python (equal to the emulator's
  table). v0.24: the DSP decodes the table, with every Q23 table, from one compressed
  stream (`zpack`, below), 2,048 words a block for the first 29 blocks after power-on, the tables first.
  The runner checks the DSP's table against it.
- **The 56300's truncation where it feeds back**: envelopes multiplied once a block or
  once a sample (`mpy_floor`, `env_mul`), filter coefficients and recursions on
  integer words with 12-bit partial products a float holds exactly; the EFM pairs
  entirely in integer arithmetic.
- **The firmware's quirks kept**: TRX-S2's bump decays that only the first note after the
  machine is chosen gets; the XT/XC/CL oscillator's sample in its increment's fraction;
  TRX-MA's two stale words past its bead buffer (held at 0, as the golden runs start).

Cost: the exact machines are heavy (12,000 to 25,000 DSP instructions a 44.1 kHz block
for TRX-CP..S2 and the EFMs, about 1,000 for GND-SN). A machine rests when its sound has
died away (32 blocks under 2^-21) until its next note, so only sounding voices cost.

## The PERC page

TYPE (page 2) picks one of the 25 machines, in PERC's order until v0.16 with TRX-S2 added:
TRX (BD B2 SD XT CP RS CB CH OH CY MA CL XC S2), EFM (BD SD XT CP RS CB HH CY), GND (SN NS
IM); the note latches it, so
a p-locked TYPE changes the machine step by step, as before. Page 1 is the machine's
eight parameters under the Machinedrum's names; each knob is the nearest of the
Machinedrum's 128 positions. Page 2 keeps the track effects in the Machinedrum's FX order
(AMD AMF EQF EQG / FLTF FLTW FLTQ, TYPE in SRR's place). The note does not tune a machine
(as on the Machinedrum: PTCH does).

### Drawn as the Machinedrum draws it (v0.20, `csrc/waverider/md_page.c`)

Under the DN2's header, both pages are the Machinedrum's main screen as its own screen
code draws it, eight rows shorter (the MD's screen has no header):

- right, x 48..127: two rows of four 20-pixel cells, each its name in the MD's small font
  over the MD's own knob (11 x 13) and pointer (one of its 128 7 x 7 pointers); dotted
  lines between the cells and under the names, a solid line along the bottom; the MD's
  "clip" over two cells whose parameters belong together (the machine record's nibble
  bit 1). TYPE's cell shows the synth and machine instead of a knob.
- left: the tempo in the MD's big font; LEV and the track's level (record 10, "Track
  Level") as a bar; the kit box, inverted, with the track and the machine's long name;
  `>PERC 1` / `>PERC 2`; and the machine line, inverted: `TRX > BD > SYNT` (page 1) or
  `TFX` (page 2).

**Nothing of the Machinedrum is in the repository.** `dnfw.md.ui` runs the owner's MD OS
(`os_main.bin`, the decompressed OS at 0x200000) in a 68k emulator when the build is made,
reads the knob, pointers, clip, three fonts and every machine's nibbles from it, and the
mod places that blob (`MDUI`, version 1) at `MDUI_LOAD` in RAM. Without the MD OS the
blob is absent and the page falls back to the v0.19 grid. How the layout was measured:
the MD's own drawing routines run in the emulator (fill `0x210f84`, blit `0x21124c`, text
`0x211384`; canvas `0x2ab836`, column-major, y up).

## Room

The DSP's program must fit its 1 MB upload buffer. v0.17 needed about 100 KB more
(the machines' code, 80 KB in L2, and the firmware's tables), so: the four test
sounds are no longer in the image (the +Drive holds the owner's samples since v0.16; the
runner puts them in itself), the sample machines' L2 span is 16 KB (their code is), PERC's
span is the code's size, EXP2's table covers -16..16 (what PERC's effects and the sample
machines use), TRX-OH shares TRX-CH's code, and the firmware's Q23 tables ship packed
24 bits a word (`tpack`, 47 KB instead of 63 KB): the DSP unpacks them into their floats
1,024 words a block for the first 16 blocks after power-on (`core.unpack_fill`; the
runner checks every word against the build's).

## Arithmetic shifts

selas encodes the immediate `Rd = ASHIFT Rx BY -n` with a shifter-op field the firmware's
own immediate ASHIFTs do not carry (digikit: "unsupported ShiftImm opcode 0x20";
`reader.asm` met it first). So `dsl.ash` puts the count in a register (`ASHIFT Rx BY Rt`,
the form the firmware and our other code use), saving and restoring Rt in a scratch word
(`ash`): every register is as before, at three more instructions a shift. v0.18: the
count goes in R12, the DSL's scratch, wherever the shift's own registers leave it free (run
mode sets R12 too, so a machine that kept something in R12 across a shift would fail its
golden cases: none does); TRX-CY's block went from 30.5k instructions to 28k.

## Rate

DSP2 runs at 44.1 kHz in 32-sample blocks (`md-research.md`: the OS's `muluw #44100`,
the DSP clock from an 11.2896 MHz crystal). The DN2 runs at 48 kHz. Each voice runs its
machine at 44.1 kHz, block by block, and the DN2's block reads that stream through a
4-point interpolator at 0.91875 Machinedrum samples a sample; the machine itself is
unchanged.

## v0.22: level

The Machinedrum voice's output scale (`dnfw.perc.program.MD_LEVEL`) is 1.4, up from 0.7
(+6 dB). Measured in the SHARC runner at the amp stage over a note's first 40 ms at
defaults: WaveTone peaks at 0.16, FM Tone at 0.10; at 0.7 the MD machines peaked at 0.05
(EFM-SD) to 0.09 (TRX-BD), so the owner heard them as quiet. At 1.4 they sit at 0.09 to
0.17, with WaveTone and FM Tone. Only the scale changed: the machines' sound, parameters
and effects are as before.

## v0.24: the tables' stream (`zpack`) and the P-I machines' room

The P-I machines' code and tables took the DSP image over its 1 MiB upload buffer (by
80 KB). What made the room, with the sound unchanged word for word:

- **`zpack`** (`core.table_fill`): the sine and every Q23 table (the host's D, Q, R, A, S,
  B and DSP2's ROM tables) ship as one bit stream, in groups of 16 words: a 7-bit header
  (a predictor, 0-3: none, the last word, a line through the last two, a parabola through
  the last three; and a width) and 16 residuals of that width. 46.7 KB, where the
  sine's corrections and the tables packed 24 bits a word took 101.7 KB. The DSP decodes
  2,048 words a block after power-on (29 blocks, 19 ms; the tables in the first 13), as it
  filled the sine before.
  `core.z_decode` is the decoder in Python; the model runs the DSP's own (`bench`).
- **The host's scale function once**: the voice ran it from two places (a note, and
  dirty words), and the chain of 34 machines was emitted twice (35 KB).
- **One copy of the division** (`trx2.idiv`) and of `mpy_floor` (`core.mpyf_any`), as
  subroutines, and the machine chains read the machine once.
- **No constant loaded twice**: the DSL leaves out a load of a register already known
  to hold that constant (only along straight code: a label or a jump forgets them all).


## 2026-11-12 (opt-md): the dearest models cut, bit-exact

Measured with opt-host's `scripts/dsp_cost.py` (docs/dsp-cost.md's scale: instructions + 4 x L2 + 10 x DDR,
instruction-exact against the assembled code; the engine's own part of a steady voice-block, blocks 4..7 after a
note; the voice host's ~2,400 is on top). The target for 16 voices with room is an engine part of ~11,100.

| model | before | after | what |
|---|---|---|---|
| TRX-CY | 15,896 | 13,276 | (v0.52 merge, rule b: dropped; v0.51's float hp1/res2 kept instead, cost measured in the v0.52 report) its 8 filters inline (`path_inline`: one I1 a path, every offset within a compute's move); the limiter's bounds in R15 / R0; the wavetables' levels through I0, each load on the add before it (also TRX-CH/OH: 11,130 -> 10,780) |
| TRX-S2 | 11,248 | 10,001 | (v0.52 merge, rule b: dropped; v0.51's float hp1/res2 kept instead, cost measured in the v0.52 report) its hpc and res4 inline (`path_inline`) |
| EFM-CY | 15,142 | 13,161 | xround's constants (M24, 1, 0x7FFFFF), the sine table's address, 0x7FFF and 2^23 held in registers through the sample loop |
| PI-SD, PI-RS | 14,628 / 14,256 | 13,304 / 12,996 | one write address for the three lines (their positions start at 0 together and move on together); the lines' reads in bytes, step and mask in registers; the limiter's bounds in registers in the one-poles, mix, junction and high-pass |
| PI-ML | 14,752 | 11,198 | the modes on the multiplier \|\| ALU in a hardware loop (PI-SD's form); floor23 without a jump (below) |
| PI-MT | 14,096 | 10,848 | the 24 TUNE / POS multipliers kept in state words 38..61, made again only when either host word changes (36, 37 hold the words they were made from; init sets them to -1); the resonators' coefficients on integer words (SSF / SSI inline, no float halves); the damping loop's tap in bytes |
| PI-BD | 12,133 | 10,959 | the coefficients on integer words; the damping tap in bytes |
| PI-RC, PI-CC | 14,225 / 14,264 | 10,982 / 11,020 | XB is no longer copied between the slot and L1 (below); the third biquad's 48-bit products on SSF / SSI; _qf's constants and kc in registers |
| PI-HH | 12,722 | 10,466 | XB not copied; _qf's constants in registers |

Still over the ~11,100 target: PI-SD, TRX-CY, EFM-CY, PI-RS (~1.9..2.2k each) and PI-ML (~100). What is left there is
mostly DDR: EFM-CY's 256 sine reads a block (~2.5k; the 128 KB table has no exact smaller form: DSP2's recursion
leaves no half-wave or mirror symmetry, so bit-exact means all 32,768 words, and no L2 that size is free), the P-I
delay lines (~1.9k). A coarser interpolated sine or shorter lines in L2 would be declared sound changes: not done.

**XB not copied (PI-RC/CC/HH).** perf (2026-11-11) moved XB to the L1 rows and copied its words 0..63 in from
the slot's DDR at the start of render and back at the end (~1,300 a block). render writes every XB word before it
reads it (the state between blocks is in the slot's S words), and host, init and trig never touch XB: no word read
before written in 90 runs x 150 blocks a machine (random and extreme knobs, notes, trigs, knob changes), and the
output without the copies, the L1 rows poisoned before every block, identical to the output with them (54 runs).

Every output word is as before: the perf session's golden script and its poisoned-scratch run (all 34 MD models),
and 6 runs x 120 blocks a model of random and extreme knobs changed mid-note, against HEAD's source. One declared
difference, which no valid state reaches: **PI-ML's floor23r** (`d = FLOAT TRUNC u`, one less where `d - u > 0`)
equals the old floor23 for every accumulator `|a| < 256` (the 56300's own range; `test/test_pi_ml_floor23.py`);
for `a <= -256` the old form's TRUNC saturates and its `- 1` wraps to `+256`, floor23r gives `-256`.
PERC's code: 171,414 of 172,032 bytes (HEAD's 171,446).
