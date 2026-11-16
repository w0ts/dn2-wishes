# Per-track inserts (OS 1.12 fork, not released)

**Two insert slots per track** (2026-11-10, the User; one until then), Overtone's idea
(complex-ping/overtone, read only; nothing of its code taken): in each slot **M.SEL** picks the insert,
**MIX** mixes it in (dry / wet), and it has up to six knobs of its own. The eight, in build order: FUZZ,
TAPE, FOLD, CHOR, WIDE, HARM (2026-11-09), **FDN8 and XDLY** (2026-11-10: the send reverb's and the send
delay's engines, per track), then **SUB, DIST, GATER and RING** (2026-11-10, ported from Optimist: below,
"SUB, DIST, GATER, RING"). FUZZ, TAPE, FOLD, HARM, SUB, DIST, GATER and RING run on the mono voice before the filter, CHOR and
WIDE on the voice in stereo after the pan (below, "After the pan"), FDN8 and XDLY on the track's own bus
after the routing (below, "On the track's bus"). Within each of those stages slot 1 runs before slot 2.

**Slot order across the stages** (2026-11-11, the User: "i have the feeling insert 2 is BEFORE insert 1",
then "DSP: always run in slot order"). Until then the stage decided: a CHOR, WIDE, FDN8 or XDLY in slot 1
with a voice insert in slot 2 ran slot 2 first (measured in the SHARC runner on the unit's build and on
main 65edf070: e.g. XDLY | DIST entered DIST in the pre pass, XDLY after the routing). Now, in exactly that
pair (`design.MOVERS` in slot 1, a `design.BUILT` type in slot 2), **slot 2 moves to the track's bus**: the
pre pass leaves it out (`program.skip_moved`) and the bus pass runs it right after slot 1, on the track's
block x 1/14.125, L and R each with its own state (`bus.MV_STATE`, L2, zeros at power-on) and, for TAPE,
its own ring (`design.MV_RING_DDR`, 32 x 2 KB), then x 14.125 back. **The moved insert then acts on the
summed voices after the filter, amp and pan** (a chord distorted as a whole, not voice by voice; once a
track, not once a voice), as an insert after a reverb or chorus would in a studio chain. Every other pair
runs as before, bit for bit. Still by stage: slot 1 FDN8/XDLY with slot 2 CHOR/WIDE (CHOR/WIDE, after the
pan, runs before the bus; not part of the User's choice, left as it was).

The code is shared, not copied: the pre pass's one insert (`program.one`, the state load, the type's code,
the state store) is a callable at `design.INS_ONE_SW` (`INS_SW + 3`, after the pass's entry `JUMP`), entered
by the pre pass for each voice and by the bus pass for a moved slot 2, its return address in a scratch
word (it calls the leaf subroutines itself). inserts.asm grew to 6,850 B (span 0x1b00 -> 0x1c00, in the
L2 the pass's old state left free), insbus.asm to 3,742 B. The runner's `insorder` step
(`scripts/sharc_insorder_step.py`) holds the order of every kind of pair and both passes to their
references; `test/test_inserts_order.py` holds the models.

A type keeps its number for good (OFF 0, FUZZ 1 .. HARM 6, FDN8 7, XDLY 8, SUB 9, DIST 10, GATER 11,
RING 12): the saved records name types by number, and a build that does not know a number reads it as
OFF. SUB, DIST, GATER and RING are builder parts (`dnfw.builder.parts` INS_SUB .. INS_RING,
`design.PART`): a build that leaves one out does not emit it, and the type plays as OFF.

## The pages

Stock 1.12's track [FX] page is full: BR OVER SRR SR.RT / DEL REV CHR OD.RT, one page (measured in
the emulator). So M.SEL and MIX cannot sit on it, as Overtone puts them, without remapping stock's
FX page lists. Instead **the FX key has three pages** (2026-11-10, the User; two until then): **FX 1/3**
is stock's track FX page, **FX 2/3** the active track's **INSERT 1**, **FX 3/3** its **INSERT 2**.

- [FX] steps FX 1/3 -> 2/3 -> 3/3 -> 1/3; [FX] on any other page (a SEND page too) is stock's, to FX 1/3.
- FUNC + [FX] is stock's alone: the three SEND pages (Delay, Reverb, Chorus), never an INSERT page; from
  an INSERT page it closes it first.
- On each switch the title bar's message line says **FX (1/3)**, **FX (2/3)** or **FX (3/3)**, with
  stock's own routine (`SAY` 0x4005628c on the title view's message line, as stock's "Delay (1/3)";
  stock's own "FX" on entering FX 1/3 is renamed before it is drawn, its slide kept).
- Every page shows stock's page dots at the right edge (`0x4006598a`, three, the current one filled), as
  stock's multi-page pages do.
- NO or any page key closes an INSERT page.

The views are found in the screen's view list (as rec.c's question test): the FX page's class
`0x401e1448`, the title bar's `0x401e1d28` (its +120 is the message line; its text, a std::string at
+0x48), measured in the 1.12 emulator.

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| M.SEL | the insert's knob 1 | 2 | 3 | 4 | 5 | 6 | MIX |

M.SEL turns like a stock multi-choice (2026-11-09, the User: one detent per type was far too
sensitive): a 0..127 value turned as a knob, each type a band of it, `type = value x 13 / 128`
(OFF 0..9, FUZZ 10..19, TAPE 20..29, FOLD 30..39, CHOR 40..49, WIDE 50..59, HARM 60..68, FDN8 69..78,
XDLY 79..88, SUB 89..98, DIST 99..108, GATR 109..118, RING 119..127; with nine types, until 2026-11-10:
OFF 0..14 .. XDLY 114..127). A saved record keeps the type; loaded, M.SEL sits in the middle of its band. 2026-11-10 (the User): the list is sorted A-Z, OFF first (OFF CHOR DIST FDN8 FOLD FUZZ GATR HARM RING SUB TAPE WIDE XDLY), through `ORDER` / `POS` in ins.c: only the display order, a type's number (the saved byte) is unchanged; the bands above are by position.

| insert | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| FUZZ | DRIV | TONE | BIAS | PRE | GATE | PGAIN |
| TAPE | DRIV | WOW | WRAT | FLUT | AGE | HISS |
| FOLD | AMNT | SYMM | SHPE | TONE | PGAIN | |
| CHOR | DPTH | RATE | DLY | VOIC | WDTH | FDBK |
| WIDE | WDTH | TIME | BASS | TONE | | |
| HARM | AMNT | FREQ | EVEN | TONE | | |
| FDN8 | PRE | SIZE | DAMP | MOD | HPF | LPF |
| XDLY | TIM1 | TIM2 | FDBK | MOD | TONE | |
| SUB | BAND | TONE | OCT | | | |
| DIST | DRIV | TONE | BIAS | LOW | PGAIN | |
| GATR (GATER) | DPTH | PATN | RATE | SHPE | SWNG | |
| RING | FREQ | SHPE | AM | | | |

`csrc/inserts/ins.c` draws the page over the screen (page.c `wr_screen`) with **stock 1.12's own
widgets** (`csrc/waverider/widgets.h`, docs/widgets.md): M.SEL a choice box, the insert's knobs and
MIX stock's dial, each with stock's label; stock's left panel (the track box, LEV) is the FX page's
own, and so is the title bar (pattern, name, tempo), left as stock drew them under ours. It takes its knobs (rec.c `smp_ui_pop` gives every item to
`ins_pop` first, the encoders' pushes too while it is up), as the RECORDER's page does. The labels
follow M.SEL because our code draws them. Each track keeps every insert's knobs, so switching M.SEL and
back keeps them. (An insert a build does not run shows SOON under M.SEL and passes the sound
through; none in this build.)

**Saved with the project** (2026-11-10, below "Saving"); not lockable, not reachable by LFOs. Real
lockable parameters (Overtone's slots, a relocated parameter table) are a separate step.

## The values' way to the DSP

The link (`csrc/sampler/link.c` `smp_tdm`) sends them whenever `ins_gen` moves, 3 times (one packet may
be lost), after any recorder command and before a load's next chunk: 58 words at the sample pool's
directory page `+0xf18` (`0x84000f18`), all that lies between the command block (`0xf00`, 6 words) and the
directory page's end; loads never write past the command block (a static assert in link.c).

32 records (track t's slot j is record 2 t + j), each eight 7-bit fields: **type | instance << 4**, MIX,
K1..K6 (0..127). 32 x 8 bytes do not fit `0xf18..0x1000` (232 bytes), so they are packed
(`dnfw.inserts.design.pack`, `ins.c ins_words`, held to each other by `test/test_inserts_c.py`): word 0 the
change word (`ins_gen`), word 1 zero (GATER's clock word, no writer yet), then 8 groups of 7 words, each 4 records' 32 fields: word w holds
fields 4w .. 4w+3 in its bits 0..27, fields 28..31 are the 7 words' top nibbles. The pre pass unpacks them
into its table (`design.TABLE`, L2 `0x200afb00`, 32 x 8 words) whenever the change word moved; the three
passes read the table. At power-on the pool's directory and the table are zeros: every insert OFF until
the ColdFire's first send. A slot whose FDN8 / XDLY found no instance (FULL) is sent as OFF.

## DSP

`dnfw.inserts.program` (`csrc/waverider/sharc/inserts.asm`, L2 `0x200ae000`, sw `0xbd7000`) is a
pass in our own per-block chain: the block counter, PERC, the sample machines, which now JUMP here,
then PING (which restores the chain's registers and returns to the stock chain).

**Voice slots, not tracks (fixed 2026-11-09, the User: "only track 1 works, track 2 farts"):** the
16 buffers are the DSP's voice slots, which the ColdFire's voice allocator gives to tracks; the
track a slot plays is the frame's halfword `0xa5a + 2 s`, at `0x257898 + 2 s` on the DSP
(link-research §7). The pass reads it for each slot and runs that track's insert (a track playing
on several voices gets it on each; a value past 15 plays nothing); a slot's state starts again
whenever its track or M.SEL changes. Until then slot s took track s's values: right only while
voice s played track s, so mostly on track 1.

Every machine has rendered into its voice slot's buffer (`0x254a60` + 4 s), and the filter, amp and
pan are still to come.
So an insert works on the voice before the filter, mono, as a synth's drive does: each note on its
own. For each slot whose track's M.SEL is a built insert: the track's 8 bytes, the slot's state (L2
`0x200af800`, 8 words a slot), the insert over its 32 samples in place.

**FUZZ** (`dnfw.inserts.ref` spells out every operation): the input held to +-4; PRE pushes the
highs above 700 Hz into the clip (x 0..3); DRIV 0..48 dB; BIAS an offset into the clip (even
harmonics), its static part taken out after; a cubic soft clip; a 20 Hz DC blocker; TONE a one-pole,
300 Hz .. 12 kHz; GATE closes the output below 0..-26 dB (40 ms release, 10 ms smoothing; 0 off);
LEV the output level; MIX the dry / wet.

**TAPE**: DRIV x 1..8 into a soft saturation (a Pade tanh, x (27 + x^2) / (27 + 9 x^2), its input
held to +-3); a short delay per track (a 512-sample ring in DDR `0x82500000` + 2 KB t, zeros at
power-on and cleared whenever a track switches to TAPE) read 2.7 ms back, moved by the wow (WOW up to
1.5 ms either way at WRAT 0.1 .. 2 Hz) and a 7.3 Hz flutter (FLUT up to 0.25 ms), linear between two
samples, the move ramped across each block; AGE the high loss, a one-pole at 16 kHz x 2^(-3 AGE)
(16 .. 2 kHz); HISS white noise (a linear congruential generator) at HISS^2 x 0.03; MIX the dry / wet.

**FOLD**: AMNT gain x 1..16 and SYMM an offset (64 none) into a wavefolder, triangle at SHPE 0 and
sine at 127 (the sine from the same fold's phase); a 20 Hz DC blocker; TONE a one-pole (300 Hz ..
12 kHz); LEV; MIX.

**HARM**: the band above FREQ (a one-pole high-pass, 500 Hz .. 8 kHz) driven x 4 into b^2 (even) and
4 b^3 - 3 b (odd), mixed by EVEN; a DC blocker; TONE a one-pole; added to the dry track at AMNT x 0.5;
LEV; MIX.

## SUB, DIST, GATER, RING (ported from Optimist)

Ported from Optimist (GPL-3.0-only, the User's own): `firmware/src/fx/insfx/insfx.c` (`ifx_mod`: RING,
SUB), `firmware/src/fx/fx.c` (`dist_gains`, `dist_run`: DIST), `firmware/src/fx/insfx/gater.c` (GATER),
rewritten in float32 for the SHARC (`dnfw.inserts.ref` spells out every operation; `dnfw.inserts.program`
the code). First built on the one-slot design (ports3, 2026-11-09), re-ported 2026-11-10 onto the two
slots: types 9..12, mono, in the pass before the filter, in **either slot**; each (voice slot, insert
slot) has its own state (8 words at `STATE + 32 (2 s + j)`), so the same type in both slots of a track
runs twice, each its own (SUB into SUB is a sub of the sub). Optimist's fades in and out (2.9 ms) and
rest on silence are left out: MIX is the dry / wet, and a slot's state starts from zeros whenever its
track or its type changes, as for the others.

**SUB** (state: the band, its envelope, the square, two flip-flops and the trigger): the band under BAND
(a one-pole, 110 Hz x 8^p: 110 .. 880 Hz; Optimist's ~440 Hz at BAND 85); its envelope, up at 1/8 a
sample (~0.2 ms), down at 1/1024 (~21 ms); a Schmitt trigger at +-1/8 of the envelope turns a flip-flop on
each rising crossing (the octave down) and, OCT 64..127, a second flip-flop on the first's rising edges
(two octaves down); a square at the envelope's level, rounded by TONE (a one-pole, 60 Hz x 16^p: 60 ..
960 Hz; Optimist's ~220 Hz at TONE 59); out = DRY x the voice + LEV x the square, then MIX.

2026-11-11 (the User: "remove it", MIX does the dry / wet): SUB's **DRY knob is gone**, and its **LEV** with it
(below). Their values are still saved, loaded and sent (a project that has them plays as before); a NEW SUB
starts with DRY 0 (`SUB_DRY` in ins.c: the wet is the sub alone, MIX blends the voice) and LEV 100. **OCT**
reads **-1** (knob 0..63) and **-2** (64..127): the same two sounds as before, only the readout changed.

### What each LEV did (audit 2026-11-11, the User: "the level of the wet ... we have a dry wet. useless")

Every insert's LEV scaled the wet before MIX (`dnfw.inserts.ref`). Kept and renamed **PGAIN** where the wet's level is
set by the effect, not by the input, so only a gain stage after it can match it to the dry; removed from the page
where it only turned a wet already at the input's level down, which MIX (and the track's volume) does:

| insert | knob | in the DSP | now |
|---|---|---|---|
| FUZZ | K6 LEV | the clipped, toned signal (about full scale whatever the input) x LEV x the gate | kept, **PGAIN** |
| FOLD | K5 LEV | the folded signal (a triangle / sine of full scale) x LEV | kept, **PGAIN** |
| DIST | K5 LEV | the clip, brought back to the voice's peak, x LEV x 2 (a boost up to 2) | kept, **PGAIN** |
| HARM | K5 LEV | (dry + harmonics) x LEV, LEV at most 1 | removed from the page |
| SUB | K1 LEV | the square (at the band's envelope, so the input's level) x LEV, at most 1 | removed from the page |
| SUB | K5 DRY | the voice x DRY added to the sub | removed from the page |
| RING | K4 LEV | voice x carrier (at most the input's level) x LEV, at most 1 | removed from the page |

A removed knob's stored value stays in the record and goes to the DSP unchanged, so an old project sounds the
same; the page just cannot change it (a NEW insert starts at its DEFAULT: HARM 100, SUB LEV 100, RING 100,
SUB DRY 0). The place is left empty.

**DIST**: Optimist's DIST, on FUZZ's sample loop (one copy of the loop, `fz_loop`, run after FUZZ's or
DIST's block values; DIST adds its block values only). The drive is relative to the voice's peak (FUZZ's
envelope follower, instant up, ~0.35 s down; floor 0.1), so DRIV clips a quiet and a loud note alike:
DRIV 0.5x .. 48x (0.5 x 96^p) of the peak into FUZZ's clip (BIAS, its static part out, the 20 Hz DC
blocker, TONE 300 Hz .. 12 kHz); the band under LOW (a one-pole, 20 Hz x 16^p: 20 .. 320 Hz; Optimist's
fixed 55 Hz) stays out of the clip and is added back dry; the clip's output goes back to the peak's level
with a make-up of 1 / (1.5 min(G, 1)); LEV x 2. It fades in over ~10 ms (FUZZ's gate smoothing, the gate
off). (FUZZ's loop gained 6 instructions a sample for it: the pre-filter and release from words, the dry
share, the low band back.)

**RING**: the voice times a sine of FREQ, 26 Hz x 100^p (26 Hz .. 2.6 kHz, Optimist's exponential knob);
SHPE drives the sine into a clip (x 1 .. 16: towards a square); AM lifts the carrier towards 1 (0 ring
modulation, 127 the dry); LEV; MIX.

**GATER** (GATR on the page): Optimist's trance gate. PATN one of Optimist's 16 patterns of 16 steps
(`design.GT_PAT`, `GT_PAT_NAMES`: 16TH 8TH 4TH HALF OFF8 OF16 DOT8 DOT4 TRN1..TRN4 GALP RGAL CLAV TRSL;
index = trunc(16 p)); RATE a step's note value (1/2 1/4 1/8 1/8T 1/16 1/16T 1/32 1/64; index =
trunc(8 p)). An open step is a pulse, open to its end, or to its middle when the next step is open too;
closed, the gain is 1 - DPTH. The gain follows at a bounded slope: SHPE a ramp of 2^((SHPE - 127) / 16) / 2
of a step, held to 1 ms .. 171 ms (48 .. 8192 samples). SWNG makes each pair's first step longer by 0 ..
50 %. GATER's tables (8 rates, 16 patterns: 96 B) are loaded with the pass's state, after its words
(`program.state_bytes`).

**GATER's clock.** The phase is Q28 a step, 2^32 the 16 steps (it wraps by itself), per (voice slot,
insert slot). It runs from the tempo: the frame copy's word 108 (`0x25c48c + 216`), BPM x 120 (120 BPM
when 0): (BPM x 120) / 112,500 ticks of 1/96 beat a block (a 16th = 24 ticks). The ColdFire's **clock
word** puts it on the sequencer's place: **the values' word 1** (`design.CLK`, `0x84000f1c`, between the
change word and the packed records; ports3 had it at `+0xf7c`, which the two slots' packed records now
fill; `ins.c ins_words` sends 0 there):

    bit 31      playing
    bits 0..11  the sequencer's place since PLAY, in ticks of 1/96 beat, modulo 3072 (8 bars)

The pass acts on the word only when it differs from the one the slot last saw: playing, the phase goes
to (place / RATE's ticks) mod 16 steps when it is more than 2 ticks off; bit 31 clear (or 0): the phase
runs on. **No ColdFire writes it yet**, so GATER free-runs from the tempo; a writer would have to send
word 1 on its own (the link sends the 58 words only when `ins_gen` moves).

**Cost** (2026-11-10, **the model's steps**, `dnfw.perc.dsl` run mode, one step an instruction; not run on
the SHARC runner, which read up to 20 % more than the model for the others; slot s playing track s, a
steady block; the pass with every insert OFF is 1,751):

| (model) | slot 1, one voice | both slots, one voice | slot 1, 16 voices | both slots, 16 voices |
|---|---|---|---|---|
| SUB | +2,143 | +4,281 | 35,692 | 69,447 |
| DIST | +2,946 | +5,892 | 48,887 | 96,023 |
| GATER | +1,610 | +3,220 | 27,511 | 53,271 |
| RING | +1,836 | +3,672 | 31,127 | 60,503 |
| (FUZZ, its loop shared) | +2,828 | +5,656 | 46,999 | 92,247 |

`design.COST` (the guard's bound): one unit's model steps x 1.2 x 1.5 (SUB 3,900, DIST 5,400, GATER 2,900,
RING 3,400), an estimate until the runner measures them.

**Code** (inserts.asm, assembled with selas at sw `0xbd7000`): 1,432 instructions, 6,384 B with the four
(936 / 4,124 B before); left out alone: SUB 139 instructions / 632 B, DIST 77 / 378 B, GATER 195 / 862 B,
RING 76 / 336 B; none of the four 945 / 4,176 B. **It does not fit `INS_L2_SPAN` (0x1400): 6,384 + 128
(L2_TAIL) = 6,512 B, 1,392 over.**

**Cost** (the SHARC runner, the pass called alone, slot s playing track s): per **voice**, since each
voice slot playing a track with an insert runs it (a chord on one track costs one insert a voice).

| | one voice | sixteen voices |
|---|---|---|
| every insert OFF (the 16 slots' track lookups) | 941 | |
| FUZZ | 3,772 | 46,252 (about 7 % of a frame) |
| TAPE | 5,410 | 72,460 (about 11 %) |
| FOLD | 4,150 | 52,300 (about 8 %) |
| HARM | 3,104 | 35,564 (about 5 %) |

**Cost after the pan** (the runner, the pass alone, its second call: no ring cleared; slot s playing
track s):

| | one slot | sixteen slots |
|---|---|---|
| every insert OFF (the 16 slots' lookups) | 859 | |
| WIDE | 3,098 | 36,683 (about 6 % of a frame) |
| CHOR, one voice | 3,948 | 50,283 (about 8 %) |
| CHOR, four voices | 8,615 | 124,955 (about 19 %) |

A slot whose track or M.SEL just changed also clears its 4 KB ring once (1,024 stores).

**Budget** (the build of sophie-v043-os112-chorwide, on GRAN's removal d208630): USB image 2,071,611 of
2,097,152 B (25,541 free), DSP upload 1,047,016 of 1,048,575 B (1,559 free). inspost.asm: 2,942 B (the
hook and the slots' lookups 1,238, WIDE 580, CHOR 1,124).

## After the pan: CHOR, WIDE and JUNO

`dnfw.inserts.post` (`csrc/waverider/sharc/inspost.asm`, L2 `0x200b0000`, sw `0xbd8000`; its state in L2
`0x200b1000`, its rings in DDR `0x82510000`, 16 x 4 KB, zeros at power-on).

**The hook.** The engine (sw `0x1c2712`) renders every voice through its chain (`CJUMP 0x1c8ef1` at sw
`0x1c3044`), which leaves each voice slot's block in stereo, then calls the FX sends with
`CJUMP 0x1c1738 (DB)` at sw `0x1c3054` (`04181c003817`, byte-checked on stock 1.12; R4, R8 and R12 set
before it, its two pushes in the delay slots), then the routing (`0x1c1f1e`). **The build changes only that
call's target**, to `wr_inpost`, as XDLY's is: it saves R0..R15, I0..I4, I12 and ASTAT, runs each slot's post
insert in place, restores them and JUMPs to `0x1c1738`, which runs as if the engine had called it. Every
insert OFF: the slots' blocks and every register at the sends' entry as they came (the runner, 24 blocks).

**The stereo blocks.** Slot s: L 32 floats at `0x257ee8 + 0x100 s`, R at `+ 0x80` (byte addresses), the
layout link-research §5 gave. The voice chain writes them every block for all 16 slots (sw `0x1c9af9`,
`0x1c9b0c`, `0x1c9b21`, measured: idle slots too, so working in place never feeds our own output back);
the sends (`0x1c179d`, `0x1c1800`, `0x1c1884`) and the routing (`0x1c1fb0`) read them, so an insert here is
heard on the main mix and in the FX sends, as a channel insert is. Each slot plays the track the slot map
says (as before the filter), so a track on several voices gets the insert on each.

**The emulator does not join them (measured 2026-11-09).** The voice chain writes through
`I1 = MODIFY(I0, M4)` with I0 = 0 and M4 the block's address; the emulator scales that modifier by 4
(byte-space address scaling) and stores the block at `0x95fba0 + 0x400 s`, while the readers' `I4 =
0x257ee8` is not scaled: in the runner the stock sends and routing read stale words there. On the unit
they meet (the stock FX sends sound), so the runner step copies each block from where the emulator put it
to `0x257ee8 + ...` before the pass, standing in for the unit. **The unit's blocks are at
`0x257ee8 + 0x100 s`: measured on hardware 2026-11-09** (build b5, d071dbc, sha `f7cc86f3...`: the User
heard CHOR and WIDE work on the unit, which they can only do reading and writing the blocks there).

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| M.SEL CHOR | DPTH | RATE | DLY | VOIC | WDTH | FDBK | MIX |
| M.SEL WIDE | WDTH | TIME | BASS | TONE | | | MIX |

**WIDE** (`dnfw.inserts.postref` spells out every operation): mid m = (L + R) / 2 and side s = (L - R) / 2;
the side x 2 WDTH (0: mono, 64: as it was, 127: about double), plus the mid delayed by TIME (0.5 .. 20 ms,
whole samples), high-passed at BASS (a one-pole, 40 .. 640 Hz: the lows stay in the middle) and through
TONE (300 Hz .. 12 kHz), x WDTH (the Haas widening, which a mono voice needs: its side is zero); L = m + s',
R = m - s'; MIX the dry / wet.

**CHOR**: one to four voices (VOIC: 1 + trunc(3.99 VOIC / 127)) reading one ring of the mid; voice v's delay
DLY (5 .. 15 ms) + DPTH (0 .. 4 ms) x a sine at RATE (0.05 .. 5 Hz), each voice a quarter turn on, moved
linearly across the block and read between two samples; even voices to the left, odd to the right by WDTH
(a voice alone stays centred), x 2 / voices; the ring takes the mid + FDBK (0 .. 0.7) x the wet's mid; MIX
the dry / wet (127: the wet alone, a vibrato). Every read is 48 samples or more back, so of an earlier
block.

A slot starts its post insert from zeros (state and ring) whenever its track or that track's M.SEL
changes.

**JUNO** (type 13, 2026-11-12, the User): Optimist's JUNO CHORUS (`firmware/src/fx/junocho/juno_cho.h`,
GPL-3.0-only, the User's own; fm-106's model of the Juno-106's MN3009 BBD chorus, after KR-106). One knob,
**MODE** (B): I / II / I+II, thirds of 0..127; **MIX** (H) as Optimist's: 0 the dry itself, 127 dry x 0.863 +
taps x 1.257 (the Juno's IC6 summer). The mid into the ring; two taps in antiphase around 3.5 ms (155 samples
at 44.1 kHz) moved by a triangle (MODE I 0.514 Hz +-47 samples, II 0.843 Hz +-37.5, I+II 7.86 Hz +-5, at
44.1 kHz), each read by 4-point Hermite and low-passed (the BBD's 2nd-order Butterworth, ~9.7 kHz); out
L = l x gd + tap L x gw, R = r x gd + tap R x gw. Optimist runs at 44.1 kHz in Q15: here its integers are
kept as times and Hz at 48 kHz, in float32 (`design.juno_consts`). The triangle is taken at the block's
two ends and the taps moved linearly between (exact but in the block that holds a corner). Its soft
limiter is left out, as Optimist's own header says (below its knee the two are the same).

- **Held to Optimist**: `postref.PostRef.juno` at 44.1 kHz with Optimist's own integers against
  `juno_cho.h` rendered on the host (`scripts/gen_juno_golden.py` -> `test/data/juno_cho_golden.npz`):
  -72 .. -78 dB error on a saw / sine mix, every mode, MIX 127 and 64 (the rest is its Q15 rounding).
- **Memory**: no new DDR or L1. The ring is the slot's post ring (1,024 floats); the ring stride grew
  from 4 KB + 8 to 4 KB + 16 for three mirror words before each ring (the Hermite's four reads at the
  ring's start), 32 x 8 B more inside the gap before the moved TAPE rings. Its six state words and
  scratch are CHOR's (`post.STATE`, `post.C`). Code: `inspost.asm` 4,496 -> 5,674 B (+1,178 B), 342 B
  left of its 0x1800 L2 span (with the 128 B tail).

## The chorus send: TYPE JUNO (2026-11-12)

The send **Chorus** page (FUNC + FX) gets a **TYPE** on its empty place **E**: **STOCK** (first, every project)
or **JUNO**, the same Juno-106 chorus as the JUNO insert, in the stock chorus's slot on the FX bus. With JUNO the
page's **DPTH** is the **MIX** and **SPD** the **MODE** (I / II / I+II); their labels are drawn as MIX / MODE, their
long names and value texts follow (Mix %, I / II / I+II). HPF, WDTH, DEL, REV, VOL keep doing what the bus does with
them (VOL the return's level, DEL / REV its sends on); HPF and WDTH are the stock chorus's own and do nothing to JUNO.

- **Why TYPE is not a stock record** (delay and reverb use their spare stock records 122 / 131): the stock
  parameter table gives the chorus kit slots 25..31, all its knobs'. Record 111 "Chorus Mix Vol." has no slot of its
  own: its index word is 0x1f, the same as 110 "Reverb Send"'s (as 120 "Delay Mix Vol." shares 119's). So TYPE is in
  the **kit's wishes record** (`csrc/wishes`, docs/wishes-record.md "Every item type"): tag **0x0101**, u8 0 STOCK /
  1 JUNO, no field = STOCK (every kit made before, and STOCK removes the field). It travels with the kit as delay /
  reverb TYPE do (copy, kit SAVE / LOAD, project, SysEx). `fxp.c` `chr_get` / `chr_set` are its only reader and writer
  (the playing kit, `0x42c5b9ac`; cached on the kit and `wish_edits`). **The record reaches the stored kit at stock's
  next save of it** (KitActive's mirror on a stock kit edit, kit SAVE, project SAVE); a TYPE turn alone with no save
  after it is lost at power-off. MIX and MODE are DPTH and SPD, stock's, kit-stored.
- **ColdFire** (`csrc/fxpage/fxp.c`): the page is known by stock drawing its DPTH cell (`fxp_cell`, from page.c
  `wr_cell`); knob E's turns are ours there (right JUNO, left STOCK); `fxp_draw` draws TYPE's box and the MIX / MODE
  labels; `fxp_chorus_poll` (page.c `wr_poll`) swaps records 105 / 106's long names and formatters (stock 1.12's own
  pointers as constants). TYPE goes to the DSP as the send pages' twelfth word (`fxp_words` w[11], directory page
  0xEFC; 0 until a value is sent: STOCK).
- **DSP** (`dnfw.inserts.jsend`, `jsend.asm`, L2 `0x200a1800`, sw `0xbd0c00`, 1,976 B in a 4 KB span): the FX bus's
  `CALL 0xb84d5c (DB)` at sw `0x1c1be1` (R4 the chorus's DDR state `0x80459388`, R8 its parameters `0x257950`,
  R12 the bus's I/O descriptor `0x257e6c`, measured in the runner) is retargeted to `wr_jsend`. TYPE not JUNO:
  everything restored, `JUMP 0xb84d5c`, the stock chorus as the bus called it (its state untouched while JUNO ran).
  JUNO: in L / R copied to out L / R, then `post.juno` (the insert's very code) in place there, MIX and MODE from
  the frame image's kit slots 25 / 26 (`0x25ce84` high half, `0x25ce88` low half; 8.8); back by the stock C
  epilogue. Its scratch is the post pass's (that pass has ended when the bus runs); its eight words and its ring
  (1,024 floats, three mirror words) in DDR `0x82550000..0x82551050` (zeros at power-on); a switch to JUNO starts
  from zeros.
- **Checked**: `test/test_jsend.py` (the model against `postref.JsendRef` bit for bit through switches and knob
  moves; STOCK leaves the send to the stock chorus; every register back), `test/test_fxpage.py` (knob E, the word);
  SHARC runner step `jsend` (`scripts/sharc_jsend_step.py`): TYPE STOCK bit-identical to the stock image (outputs,
  registers, every word written but the send's own), TYPE JUNO bit-exact to the reference, registers back, no stray
  DDR write, its cost.

## On the track's bus: FDN8 and XDLY

`dnfw.inserts.bus` (`csrc/waverider/sharc/insbus.asm`, L2 `0x200bc000`, sw `0xbde000`, between the sample
machines' code and PERC's; its state after it to `0x200bfc00`). A reverb or a delay on a voice would lose
its tail with the voice (a stolen slot starts again) and cost once a voice, so FDN8 and XDLY run once a
**track**, on the block the routing makes of it:

- **The hook.** The routing (`0x1c1f1e`, called at sw `0x1c305d`) sums each voice slot's stereo block into
  the block of the track the slot plays (`0x258f68 + 0x100 t`, L 32 floats then R at `+ 0x80`, each voice x
  14.125; docs/link-research.md §5, §7; its loop ends at sw `0x1c1fec`), then sums the tracks' blocks into the
  main bus (`0x25bb68`, from sw `0x1c2038`; measured in the runner, the routing's masks 0), adds the send FX's
  returns and runs the master chain (`CJUMP 0xb8541d` at sw `0x1c215c`, then `0x1c6664`, `0x1cdc30`,
  `0xb82728`, each twice). **The build replaces the routing's first instruction after its per-track loop**
  (sw `0x1c1fef`, `R2 = DM(0x257980)`, `021025008079`, byte-checked on stock 1.12) with `JUMP wr_inbus`: it
  saves R0..R15, I0..I4, I12 and ASTAT, runs each track's bus inserts in place (slot 1, then slot 2),
  restores them, does `R2 = DM(0x257980)` and JUMPs back to sw `0x1c1ff2`. Nothing branches to either
  address (the routing's 48 branches read with selmap).
- **Heard where.** On the main mix, through the master chain as the track is, and on Overbridge's track
  outputs (the output stage `0x1c244d` reads the same blocks). **Not in the send FX**: the sends took their
  taps from the voice blocks before (an insert reverb's tail is not sent to the send reverb). A tail goes on
  after its notes, and after the track is muted (the routing's ramps are on its input).
- **2026-11-11, the User: "xdelay and fdn8 still dont work as insert".** Until then the pass was the target of
  the engine's call of the output stage (sw `0x1c307b`), after the routing had summed the main bus from the
  dry blocks: remoteui measured on the unit the track's Overbridge stream (SPI records) carrying FDN8's tail
  at ~200x the dry level, the main mix only the dry release. The runner's new step 3k3 (`mainmix`,
  `scripts/sharc_mainmix_step.py`) reproduced it on that build (the main bus equal to the blocks before the
  pass, bit for bit, FDN8 and XDLY at MIX 127) and holds the main bus to the blocks after it.
- **The engines are the send FX's own code.** FDN8's and XDLY's programs have a MODE word: the bus pass
  copies the send FX's words aside, copies an instance's words in (FDN8: 105 words and its 49-word variant
  table; XDLY: 35 words), sets MODE 1 and enters `wr_fdn8` / `wr_xdly` as a leaf call; they run one block
  of the instance and return with `JUMP (M14, I12)`; the bus pass copies the instance's words back, and
  at the end the send FX's. The send FX are unchanged (their runner steps, below), at the cost of three
  instructions a call.
- **Instances** (the User, 2026-11-10: as many as memory allows, never at the voices' cost): **8 FDN8**,
  each its own 512 KB ring (DDR `0x82800000 + 0x80000 k`, the LONG layout's size), **4 XDLY**, each two
  2 MB lines (DDR `0x83000000 + 0x400000 k`, 10.9 s each, as the send XDLY's): 20 MB of the 25.5 MB our
  DDR had free above `0x82680000`. The ColdFire gives a slot an instance when it takes the type (the
  lowest free) and keeps it while the slot keeps the type; a slot that finds none free shows **FULL**
  under M.SEL and is sent as OFF (dry). An instance run by another record or type than last time starts
  as a new engine: its words zeroed, its ring or lines set, FDN8's LFO phases at their start, then the
  engine's own switch (FDN8 clears its ring, 32 silent blocks, 21 ms; XDLY reads nothing it has not
  written). Neither instance memory is loaded at power-on.
- **Levels.** The engine gets the track's block x 1/14.125 (a voice's level, as the routing's gain on a
  voice) and its wet comes back x 14.125; MIX: x' = x + (wet - x) MIX. FDN8's knobs are the send reverb's
  struct (PRE, SIZE, DAMP, MOD, HPF, LPF, each / 127); XDLY's: TIME 1 / 127, X 0, TIME 2 / 128, FDBK / 128,
  MOD (the send's HPF) / 127, TONE (LPF) / 127.
- `dnfw.inserts.busref` spells it out; `test/test_inserts_bus.py` holds the DSL model to it bit for bit.

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| M.SEL FDN8 | PRE | SIZE | DAMP | MOD | HPF | LPF | MIX |
| M.SEL XDLY | TIM1 | TIM2 | FDBK | MOD | TONE | | MIX |

## Saving (with the project)

The User (2026-11-10): "works with project save". Stock has no record to hold them (16 tracks x 2 slots
x 8 values), so, as the per-project pools, they keep their own per project slot on the +Drive
(`csrc/inserts/store.c`), following stock's project code:

| stock does | the inserts |
|---|---|
| writes a project slot, `0x40040190(project, slot, cb)` (SAVE and SAVE AS write the slot and the temp slot 128; LOAD, NEW and the OS's autosave the temp slot) | the record of that slot is written from what they hold (hooks.S `ins_pj_write_hook` notes the slot; the UI pass writes) |
| LOAD of slot p (pools' hooks) | record p's values (none: every slot OFF), then record 128 written |
| NEW (into slot q) | every slot OFF, written as record 128 (and q's) |
| - | an edit by the knobs: record 128 written 2 s after the last |
| power-on (stock's temp slot) | record 128 |

Record p (0..127 the projects, 128 the working copy, as stock's temp slot): sectors `0x6e0400 + 2 p + c`,
two copies, one sector each ('DN2I', version 1, p, sequence, the 32 records as type, MIX, the type's six
knobs, a check); written into the older copy, the newer whole copy read: a write cut by power-off leaves
the one before. Between the pools' lists (to `0x6e02ff`) and the library's index (`0x6f0000`). A record
keeps only the type's own knobs: after a LOAD the other types' knobs of a slot are their defaults. The
hook's site is checked byte for byte (`4fefffcc48d77c1c`, then `246f0040286f0038262f003c`); no stock branch
lands inside its 8 bytes (objdump of 1.12's section 3: the references are the calls at `0x400402ba`,
`0x4004034a`, `0x40042ec0` and the branch at `0x40040294`, all to its entry). ERASE MOD DATA does not erase
these sectors yet.

## The guard: the inserts never cost a voice

The User (2026-11-10): the bus inserts "should not affect voices"; the same rule is applied to every
insert. Until now the insert passes ran in the stock tail the guard measures, so a heavy insert lowered
the voices' LIMIT from the next frame on (and a sudden one could run past the frame first). Now
(`dnfw.perc.guard`):

- each pass measures its own time (`INS_T0`, `INS_ACC`, `EMUCLK`), and the stock tail is measured without
  it: the voices' LIMIT is as if no insert ran;
- each insert, before it runs in a block, checks it is expected to end before **INS_DEADLINE = P - TAIL -
  P/8** cycles after the frame's start (the frame less the guard's margin and the stock's own tail), with
  its type's bound (`design.COST`: the runner's cost of one unit x 1.5, the DDR-heavy x 2; FDN8 64,000 since 2026-11-12, 1.2 x its clearing block (53k on the shared scale; 32,000 before, under it),
  XDLY 20,000, CHOR 13,000, TAPE 8,200 ..); one that would not end in time is left out of that block (the
  sound passes dry; its state kept; `INS_SKIPS` counts). Until a frame is measured (and in the runner,
  whose clock stands still) every insert runs.
- **2026-11-11 fix (`guard.ins_start`, `INS_DLP`):** INS_DEADLINE leaves room for the WHOLE stock tail, but only the
  pre pass and a2f run at its start. The post pass runs at the FX sends and the bus pass (FDN8/XDLY) just
  before the output stage, with most of the tail already done, so it was counted twice. The unit's
  telemetry showed it: the bus inserts passed through for thousands of blocks at a 60 % frame, no voice
  skipped. Each pass's deadline now adds back the stock's time done since our voices and before the pass,
  `INS_T0 - OURS_END - INS_ACC`, held to 0 .. TAIL - REST_OUT. REST_OUT is the stretch from the bus pass's end
  to the frame's busy end (the output stage), measured like TAIL. It is always kept in reserve, because
  TAIL can read low: its readings over 0.7 P are not taken. The runner's `insdl` step (moving clock, idle_load's
  AFTER moved, so TAIL is measured) shows the old rule skipping both bus inserts in every block with one
  ANALOG2 voice and the frame ending at 54 % of P; numbers in the step's report.
- Measured on the unit (b5diag): LIMIT about 355,000 and the rest of the DN2 about 43,000 a block, so with
  P about 592,000 the inserts have about 120,000 before the deadline when the voices use all of theirs
  (about three FDN8 at their bound), more when they do not. An FDN8 left out of a block is a gap in its
  tail (a click): the price of never costing a voice.

## JUNO's and CHOR's taps through L1 (2026-11-12)

A tap's reads in a block (JUNO's four a sample, CHOR's two) lie in one span of its ring that the block does not
write (the ring is written after the taps). When that span does not wrap and fits, `post.span` (a leaf
subroutine) copies it once to `post.LINE`, 0x2e5400 (the Monomachine render scratch's IN: the arbiter's
transient 512 B, dead during this pass), and points the tap's ring base there: its inner loop is unchanged, the
same words are read, so the same output (`test_inserts_post`, `test_jsend` against the references; the runner's
inspost, jsend and insall steps). The JUNO send (jsend) takes the same path. Model, shared scale (instructions +
4 L2 + 10 DDR), one voice / 16: JUNO 8,197 -> 6,680 / 104,212 -> 79,990; CHOR 5,546 -> 5,326 / 61,796 ->
58,226. WIDE reads each word once: unchanged.

## Cost, two slots (2026-11-10)

The SHARC runner, each pass called alone (instructions a block; every access charged alike, so DDR's
extra cost on the unit is not in these):

| pass | case | cost |
|---|---|---|
| before the filter | every slot OFF (32 lookups, and the unpack check) | 2,145 |
| | FUZZ / TAPE / FOLD / HARM on 1 voice | 4,967 / 6,605 / 5,345 / 4,299 |
| | the same on 16 voices | 47,312 / 73,520 / 53,360 / 36,624 |
| after the pan | every slot OFF | 1,931 |
| | WIDE 1 / 16 voices | 4,162 / 37,627 |
| | CHOR 1 voice: 1 / 16 slots; 4 voices: 1 / 16 slots | 5,012 / 51,227; 9,679 / 125,899 |
| the track's bus | every slot OFF | 1,091 |
| | one FDN8, clearing / steady (the words swapped in and out included) | 11,210 / 19,194 |
| | one XDLY | 7,909 |
| | 8 FDN8 + 4 XDLY, steady | 161,167 |

A second slot costs what the first does. With every insert OFF the three passes add about 3,300 a block
to the one-slot build's 1,800.

## Checked, and not

- SUB, DIST, GATER, RING on two slots (ins47, 2026-11-10; tests in the session's scratch
  `ports3/ins47/test_ins47.py`): the DSL model equals `dnfw.inserts.ref` bit for bit over 260 blocks (the
  four in slot 1 and in slot 2, the same type in both slots of a track, DIST into FUZZ, TAPE into SUB, slot 2
  alone, types switched in either slot, knobs moved, tempo changes, clock words PLAY / jump / STOP, loud,
  quiet and silent input, the slot map rotating with a track on two voices); two GATERs in one track's
  slots keep their own phases; SUB peaks at f/2 and f/4, RING is the voice times its sine, DIST's shape
  follows the peak (x 10 in, x 10 out), GATER's steps at 120 and 150 BPM and the clock word, each in slot
  1 and slot 2; types the pass does not run (CHOR WIDE FDN8 XDLY, 13..15) untouched; builder subsets.
  `test/test_inserts.py`, `test_inserts_post.py`, `test_inserts_c.py`, `test_inserts_bus.py` pass. Not
  checked: the SHARC runner (step `inserts` covers the tree's four), the unit, the ColdFire page in the
  emulator, a clock word from the ColdFire (none is written).

- `test/test_inserts.py`: the DSL model equals `dnfw.inserts.ref` bit for bit over 120 blocks (two
  FUZZ tracks, knobs moved, the gate, one switched off and on, MIX 0, loud input); tracks with no
  insert, OFF, or a type not built untouched; every insert OFF leaves every buffer.
- SHARC runner step `inserts` (`scripts/sharc_inserts_step.py`), real blocks of the build with PERC
  voices sounding:
  - every insert OFF: every track buffer after the pass is the buffer before it (30 blocks);
  - FUZZ on two tracks: every buffer after the pass is the reference's (40 blocks), the others
    untouched;
  - the pass's cost alone (above).
- `test/test_inserts_post.py`: the post pass's DSL model equals `dnfw.inserts.postref` bit for bit over
  90 blocks (WIDE and CHOR on tracks 1, 2, 5, 16, the slot map rotating them over six slots, track 2 on
  two, knobs moved, one track WIDE -> CHOR, a pre insert's track untouched), every register back.
- SHARC runner step `inspost` (`scripts/sharc_inspost_step.py`), real blocks of the build with PERC voices
  on five slots: every insert OFF leaves every block and register (24 blocks); WIDE and CHOR as the
  reference, bit for bit, with the slot map rotating (40 blocks); the pass's cost (below).
- 2026-11-10, two slots and the bus inserts (sophie-v047-os112-inserts2):
  - `test/test_inserts.py`, `test_inserts_post.py`: the same, with 32 records, both slots on one voice
    (FUZZ into FOLD, TAPE into HARM, WIDE into CHOR), slot 2 alone, the packed values through the DSP's
    unpack (and only on a change);
  - `test/test_inserts_bus.py`: the bus pass's model equals `dnfw.inserts.busref` bit for bit over 70
    blocks (FDN8 half wet, XDLY wet only, FDN8 then XDLY on one track, a FULL slot, an XDLY instance moved
    to another track and started fresh), the send FX's words and every register back, the instances' DDR
    holding the sound and the send reverb's ring untouched;
  - `test/test_inserts_c.py`: ins.c compiled for the host: its packed words are `design.pack`'s, its
    instances given out as the DSP expects, a FULL slot sent as OFF, an unknown type read as OFF;
  - SHARC runner (the build's assembled code): `inserts` (the values sent packed, the pass's own unpack),
    `inspost`, `insbus` (as the test, 70 blocks, bit-exact; every register and the send FX's words back),
    `fdn8` and `xdly` (the send paths still stock's and the references', bit for bit), with decode, guard,
    rotate, stress, tdm, mnm, frame: 101 checks PASS; the control (rr-v0.47-ours-1.12) 46 PASS, every one
    of them passing here too;
  - `scripts/gate_hwrules.py` (now also over FDN8, XDLY, the bus pass and the output call's site): PASS;
  - the ColdFire emulator: the build boots from reset to 800 M instructions with its own DSP image, no
    fault; the three FX pages, FDN8 and XDLY on them (screens in dn2mk2-scratch/inserts2/png);
  - not checked: anything on the unit (the DDR cost, the bus blocks' level, the save hook on a real
    +Drive, the guard's deadline at work), a project saved and loaded in the emulator.
- On the unit (b5 d071dbc, sha `f7cc86f3...`, 2026-11-09): CHOR and WIDE work, so the stereo blocks are
  where the readers read them. Not checked: the cost on the unit,
  the values' packets on the unit's link, the page turning values in the emulator beyond what its
  screenshots show.
