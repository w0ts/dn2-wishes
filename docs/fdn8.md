# FDN8: the owner's reverb beside the stock reverb (OS 1.12 fork, not released)

The Reverb page gets a **TYPE** knob on its empty position **G**: **STOCK** (every existing kit)
or **FDN8**, shown in its cell. With FDN8 the page's DEC, FREQ and GAIN knobs are **SIZE**,
**DAMP** and **MOD** (the header's long names say so as a knob turns: Size, Damping,
Modulation; the knob labels stay DEC / FREQ / GAIN, see below); PRE, HPF, LPF and VOL keep
their roles. One reverb plays at a time.

FDN8 is optimist's (`firmware/src/fx/reverb/reverb_alt.c`, the `rvf_*` section, GPL-3.0-only,
the owner's), there at 22.05 kHz in integer arithmetic; here at the DN2's 48 kHz in float32,
with the same structure and curves (`src/dnfw/fdn8/ref.py` spells out every operation):

- a pre-delay, four input allpasses (0.75 / 0.625, growing to 0.8 / 0.7 above SIZE 90);
- eight lines, optimist's 32 KB ring's lengths (62..117 ms) at 48/22.05, each the nearest
  unused prime (2963 .. 5623 samples), each read through a slowly moving tap (its own LFO,
  0.56 .. 1.18 Hz) whose fraction goes through a first-order allpass;
- a one-pole damping per line (Jot: the same loss in dB per second on every line), its decay
  gain, the 8 x 8 Householder matrix; left lines 0 2 4 6, right 1 3 5 7.
- Optimist's random rounding is gone: float needs none.

| knob | FDN8 | from |
|---|---|---|
| PRE | pre-delay 0 .. 100 ms, square law | a knob of its own (optimist grows it with SIZE) |
| DEC -> SIZE | optimist's decay curve: the ROOM's up to 90, then the decay time doubles every 11 steps, a near-freeze at 127 | `rv_kt`, `RV_KNEE` 90, `RV_STEPS` 110, `RV_FRZ8` 18 (spread over 126..127 here: the knob is smoothed) |
| FREQ -> DAMP | optimist's DAMP cubic, per line by Jot (`rv_lpc`), solved at 48 kHz | `rv_damp`, `rv_lpc` |
| GAIN -> MOD | the lines' modulation depth x 0 .. 2 (64: optimist's 4 .. 8 samples at 22.05 kHz) | `RV_FEXC`, `RV_EXC` |
| HPF / LPF | one-pole input filters, 20 Hz .. 2 kHz / 200 Hz .. 20 kHz | the stock knobs' roles |
| VOL | the bus's, as for the stock reverb | stock |

**SIZE's knob travel (2026-11-16, the User: more resolution at 98..99 %, the User's choice B).** The knob goes through a
piecewise-linear map before the curve (design.SIZE_MAP, knob -> optimist's SIZE), held to 127: (90, 90) (102, 124)
(122, 126) (127, 127). 0..90 and 127 are unchanged bit for bit; 90..102 covers 1.6 -> 13.7 s (~24 % a step);
102..122 the old 98..99 % (13.7 -> 15.6 s, 0.6 % a step instead of 6.5 %); 122..127 the near-freeze (15.6 -> 79 s,
x 1.38 a step instead of one jump at 127). Loop RT60 at DC, LONG 1.5 x. The insert and the send run the same code.
A saved SIZE 91..126 plays longer than before (saved 100: 3.0 -> 9.6 s; 120: 10.7 -> 15.4 s; 125: 14.6 -> 41 s);
the SIZE values below are the knob's before the map.

RT60 of the reference (DAMP 30, MOD 64; an impulse, T30 x 2): SIZE 0 0.43 s, 45 0.69 s, 90
1.34 s, 120 9.17 s, 126 13.4 s. Optimist's own (22.05 kHz, DAMP 30): 0.5 .. 1.5 s at 0..90,
9.2 s at 120, 13.0 s at 126.

## Second page (2026-11-11)

A FUNC tap on the Reverb page (TYPE FDN8 or LONG) shows a second page of knobs: DIFF, WDTH, FREZ (docs/fxpage.md).

## LONG: the longer lines (TYPE 2, 2026-11-09)

TYPE has a third value, **LONG**: FDN8 in a bigger, darker room. Record 131's top value is widened
at run time from 1 to 2 (`RECORD_MAX`, record + 0x0c, `0x100` -> `0x200`). The stored values are FDN8 (0),
STOCK (1, what every kit stores), LONG (2); 2026-11-11 (the User: STOCK first) the **knob and the popup list go
STOCK, FDN8, LONG**: STOCK at the knob's left end, the stored values unchanged (`rvt_step`, called from the setter's
hook `fx_type_hook` -> `fx_type_quant`, fmt.c, at the kit setter 0x40037d86's store 0x40037df6, while a knob turn is fresh). What differs (`design.variant`):

- every line and diffuser about twice as long: the nearest unused primes to 2 x FDN8's (lines
  5927 .. 11243 samples, 123 .. 234 ms; diffusers 199, 157, 479, 359);
- the decay time 1.5 x at the same SIZE (each line's gain from its own length, and the decay per
  sample / 1.5);
- 1.5 x the high-frequency loss a second (Jot's damping per line scaled by its length, then x 1.5).

The DSP code reads what differs from an active table in L1, which a switch copies from the
variant's table (49 words). FDN8's own numbers are unchanged: its factors are exactly 1.0, so its
output is bit-for-bit what it was. The ring grew to 512 KB (LONG's layout ends at 74,899 words),
so a switch to FDN8 or LONG now clears 32 blocks (21 ms), and a switch between the two clears too.

## TYPE: stock's record 131

TYPE is stock's record 131 "Reverb FX Routing": kit slot 48, range 0..1, default 1, stored with
the kit, sent in the frame (word `0xa28`), shown on no page and read by nothing on the DSP (the
stock unpack keeps only a byte nobody reads; Digiwerk's T3.4 and T6.1 found it, their "path c").
**0 is FDN8, 1 the stock reverb**, so every existing kit plays as before. It is not lockable
and has no CC (stock's flags), which suits a type switch. This replaces §11's route (A) (a
spare kit byte and our own control): the same result with stock's own storage, knob and
transport, and no TDM packet word.

ColdFire, `csrc/fdn8/ui.c` `rvt_poll` (from `page.c` `wr_poll`, once a UI loop):
- the Reverb page's record list is built at boot at `0x42433f20` (stock 1.12, `0x400c9fca..`):
  `[123 124 125 126 127 128 0 0 130]`; G (`0x42433f38`, cleared by `clr.l` at `0x400c9fde`) is
  set to 131, and set again only if it is not;
- record 131's names become TYPE / "Reverb Type" and its value text STOCK / FDN8 (stock's
  formatter `0x400e3592` says Pre / Post); `rvt_cell` (from `page.c` `wr_cell`) draws TYPE's
  cell as STOCK / FDN8 in place of stock's PRE / POST FX picture, and its label;
- while TYPE is 0 (the value the page drew, or before that the frame's word at `0x80005e60 +
  0xa28`, the frame builder's `lea` at `0x400274ba`, byte-checked on 1.11 and 1.12), records
  124-126 carry the long names Size / Damping / Modulation; stock's go back otherwise.
- **The knob labels cannot follow TYPE**: this page copies its labels when its views are built
  at boot. Measured in the emulator: a short name changed later never reached the label, also
  after leaving and re-entering the page. Drawing them again from `wr_cell` would need stock's
  label font and placement (theirs is wider than the grid font). So DEC / FREQ / GAIN stay.

## DSP

The FX bus calls the stock reverb with `CJUMP 0xb836bc (DB)` at sw `0x1c1d11` and two pushes
(R4 its DDR state `0x80000018`, R8 its parameter struct `0x257918`, R12 the bus's I/O
descriptor). **The build changes only that CJUMP's target**, to `wr_fdn8` (sw `0xbd5000`). The
pushes still run, so `wr_fdn8` is entered exactly as the stock reverb is. It saves every
register it uses, then:

- TYPE not 0, no switch pending: restores everything and `JUMP 0xb836bc`. The stock reverb
  runs as if called directly and returns to the bus itself;
- TYPE changed: the type switched to is cleared first, 4096 words a block, the wet silent
  meanwhile. For FDN8 that is its ring, 16 blocks (11 ms). For the stock reverb it is its four
  sample buffers (pre-delay, diffusers, the two tank sets: Digiwerk T3.4 §3.3, checked by the
  runner), 22 blocks (15 ms). So an old tail never comes back (the stock init, 30
  instructions, clears no buffer);
  2026-11-21 (fx-fast, `ref.WINDOW_CLEAR`): FDN8 and LONG clear only the ring's window a fresh engine reads before
  it writes. Every access is at p + off with 0 <= off < RB_END, and p counts down, so a word enters the window at
  offset 0, where it is written first, unless it already lay in [p, p + RB_END) at the start. The same 32 silent
  blocks (the same output, bit for bit), each clearing 1,264 words (FDN8, 40,153 needed) or 2,352 (LONG, 74,899)
  from p rounded down to 16 words, a 16-word group at a time with its address masked, so it wraps round the ring's
  end. The ring's other words keep what they held; they are never read before being written. Clearing block
  4,096 -> 1,264 / 2,352 DDR stores (bus instance 0's first block 54,965 -> 23,680 on the shared scale). Proof:
  `test/test_fdn8_window.py`, the model with the ring NaN-poisoned against the whole-ring reference through
  stock / FDN8 / LONG switches whose window wraps;
- TYPE 0: one block of FDN8 into the bus's output pair (the wet only).

| where | what | size |
|---|---|---|
| L2 `0x200aa000` (sw `0xbd5000`) | `fdn8.asm`, generated from `dnfw.fdn8.program` | 7,018 B (span 10 KB; 16 KB until XDLY) |
| L1 `0x2e6400` | its words, the LFO phases, the stock buffers' chunk table, the variant tables | 2.5 KB (the last 512 B are XDLY's) |
| DDR `0x82400000` | the ring: 128 K float32, zeros at power-on (a fill block) | 512 KB (256 KB until LONG) |

The code sits inside `0x20088400..0x200b0000`, the L2 range complex-ping's mods proved on
units. The ring is DDR, as the stock reverb's own lines are (`0x80000018`, 364 KB).

**Cost** (the SHARC runner, which charges every access alike): FDN8 13,845 .. 15,338
instructions a block, mean 13,882; the stock reverb 14,564; the stock path through `wr_fdn8`
+66; a clearing block about 5,150. A sample makes 34 DDR accesses (8 lines x 2 reads + 8
writes, the pre-delay and the diffusers): about 1,100 a block. **On the unit a DDR access costs
several times an instruction. Unmeasured**: read the system meter's D with TYPE on FDN8.

**Budgets**: section 7 1,030,696 of 1,048,575 B (+7,148 over the combined base); USB image
2,088,377 of 2,097,152 B.

## Also the per-track FDN8 inserts' engine (2026-11-10)

The same code runs the FDN8 inserts on the tracks' buses (docs/inserts.md "On the track's bus"): a MODE
word after its register save; the bus pass swaps an instance's words in for the send's (and back), sets
MODE 1 and enters `wr_fdn8` as a leaf call, which runs one block of that instance and returns with
`JUMP (M14, I12)`. The send path (MODE 0) is the one it was, three instructions longer; its
ring's base is a word now
(each instance has its own DDR). Its runner step holds the send path to stock and to the reference as
before.

## HALF: the bus inserts' tank at 24 kHz (2026-11-22, the User's pick)

The bus inserts' FDN8 (MODE 1, every instance) runs **HALF** (`design.variant(3)`, reference `dnfw.fdn8.lite.BusRef`,
the A/B in `scratch/fdn8-bus-ab/`): the tank at 24 kHz, 16 samples a block, input diffusers 0 and 2 only, between a
19-tap half-band decimator (the 32 sums L x G_IN + R x G_IN, 17 kept a block) and two half-band interpolators (the
lines' L / R sums, 9 kept; the even outputs the tank's samples x GOUT, the odd ones the side taps x 2 GOUT). The same
eight lines and delay times (optimist's lengths x 24000 / 22050, the nearest unused primes 1481 .. 2803), the same
decay time (+2 %), Jot's damping solved at 24 kHz, the modulation's depth in milliseconds. The wet's top is ~9 kHz
(-0.1 dB at 8 kHz, -6 dB at 12 kHz). **The send (MODE 0) is unchanged**: its output and ring bit for bit as before
(the runner's `fdn8` step); the parameters' constants now come from the active table (`kkt kinv fexc dgrow pdf pdi
whp wlp`, the same float32 values the code loaded), and so do the block's sizes (`nb nb2 nb4 xtop lbuf dn dk4`), so
the send and HALF run the same stage code (`stages.tank`: the decimator and `_input_h` or `_input`, then the
diffusers / lines / writes, then `_interp` or `_output`).

Memory: an instance keeps only its persistent words (`program._PERSIST`, 97 with the resamplers' kept samples), the
bus pass swaps those and no table (VT3 goes into ACT once a pass, the send's ACT is set aside and put back); the
stores are 8 x 388 B from 0x2E4050, FDN8's block buffers (X S F) moved after them (`program.BUF_L1`, 0x2E4C70), the
state took their old room (VT3, the larger table). FDN8's code grew (the resamplers, 14 KB span from 0x200AA000):
XDLY moved to A2F's unused tail (0x200B3E00, sw 0xbd9f00). HALF's ring window clears 672 words a block.

Cost, one bus instance's whole pass (test_inserts_bus's measure, instructions + 4 L2 + 10 DDR): steady 17,843 ->
12,440; clearing 24,069 -> 16,678.

**On the DN2** (test file 0cd88167, the ladder: INSERT FDN8 MIX 100 on T1..T8, chords waking the stock voices, the
system meter's D per rung; `scratch/unit-now/fdn8cheap/runs/lite0cd8.json`): one playing bus FDN8 costs **~17.8-18.4k
cycles a block** (was ~22-24k before HALF); 4 were admitted at once (was 2-3), D 84.4 % from the 4th rung on. The
model's scale (12,585 the dearest block) is under the unit's: the unit pays more for a DDR access than the model's 10.
So the guard's charge `COST[FDN8]` is set from the unit, not the model: **18,500** (the ~17.9k measured plus a small
margin; 15,200 = 1.2 x the model's dearest until then). `FDN8_STEADY_MAX` stays the model's figure, and the bound
still holds `COST[FDN8] >= 1.2 x FDN8_STEADY_MAX`.

## Checked, and not

- `test/test_fdn8.py`: the DSL program's model equals `dnfw.fdn8.ref` bit for bit, ring included.
  The script covers 260 blocks: stock, a switch with its clearing, noise, an impulse, knob
  moves, SIZE 127 and a switch back. The approximations (exp2, log2, 1/x, sqrt, the sine) are
  within 1e-6.
- SHARC runner step `fdn8` (`scripts/sharc_fdn8_step.py`), on stock section 7 and the build:
  - **TYPE stock**: 40 blocks. Every output word, every register at the return and every word
    written are the stock image's, apart from FDN8's own state words.
  - **TYPE FDN8**: 230 blocks, every output word bit-exact to the reference and the ring word
    for word. Every register the bus left is back.
  - **Switches**: FDN8 to stock gives 22 silent blocks, then the stock reverb on silence gives
    exactly a fresh stock reverb's output (0). Stock to FDN8 gives 16 silent blocks, then
    exact zeros on silence.
- Reference renders: `dn2mk2-scratch/wav/fdn8/` (pluck and snare, SIZE 40..126, DAMP 30/90,
  MOD 0/64/127).
- **Not checked**: the unit (DDR cost, the sound at the DN2's levels, Digiwerk's warning that
  a spring reverb in this slot stopped the DSP on a unit). FDN8's code uses only the DSL's
  instruction forms, which PERC's code has run on units, and lives in proven L2.
  - The wet level against the stock reverb's is not matched: optimist's send and wet gains
    are kept.
  - The ColdFire emulator needs a snapshot booted on the build itself, because the chunk
    layout moved (a mismatched snapshot faults at warmup: tasks parked in the old layout).
- ColdFire emulator (1.12, a snapshot booted on this build): the Reverb page below its title
  is pixel-identical to the combined build's but TYPE's cell and label; TYPE sits on G and
  reads STOCK for the kit (value 1). Not shown: TYPE turned to FDN8 (the emulator's encoders
  did not move values on this page, and it builds no frames).
