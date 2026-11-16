# Per-track inserts (OS 1.12 fork, not released)

**Two insert slots per track** (2026-11-10, the User; one until then), Overtone's idea
(complex-ping/overtone, read only; nothing of its code taken): in each slot **M.SEL** picks the insert,
**MIX** mixes it in (dry / wet), and it has up to six knobs of its own. The eight, in build order: FUZZ,
TAPE, FOLD, CHOR, WIDE, HARM (2026-11-09), **FDN8 and XDLY** (2026-11-10: the send reverb's and the send
delay's engines, per track). FUZZ, TAPE, FOLD and HARM run on the mono voice before the filter, CHOR and
WIDE on the voice in stereo after the pan (below, "After the pan"), FDN8 and XDLY on the track's own bus
after the routing (below, "On the track's bus"). Within each of those stages slot 1 runs before slot 2;
across them the stage decides (a CHOR in slot 1 and a FUZZ in slot 2: the FUZZ, before the filter, is
heard first).

A type keeps its number for good (OFF 0, FUZZ 1 .. HARM 6, FDN8 7, XDLY 8; ports3's SUB DIST GATER RING
would be 9..12): the saved records name types by number, and a build that does not know a number reads
it as OFF.

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
sensitive): a 0..127 value turned as a knob, each type a band of it, `type = value x 9 / 128`
(OFF 0..14, FUZZ 15..28, TAPE 29..42, FOLD 43..56, CHOR 57..71, WIDE 72..85, HARM 86..99, FDN8 100..113,
XDLY 114..127). A saved record keeps the type; loaded, M.SEL sits in the middle of its band.

| insert | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| FUZZ | DRIV | TONE | BIAS | PRE | GATE | LEV |
| TAPE | DRIV | WOW | WRAT | FLUT | AGE | HISS |
| FOLD | AMNT | SYMM | SHPE | TONE | LEV | |
| CHOR | DPTH | RATE | DLY | VOIC | WDTH | FDBK |
| WIDE | WDTH | TIME | BASS | TONE | | |
| HARM | AMNT | FREQ | EVEN | TONE | LEV | |
| FDN8 | PRE | SIZE | DAMP | MOD | HPF | LPF |
| XDLY | TIM1 | TIM2 | FDBK | MOD | TONE | |

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
change word (`ins_gen`), word 1 zero, then 8 groups of 7 words, each 4 records' 32 fields: word w holds
fields 4w .. 4w+3 in its bits 0..27, fields 28..31 are the 7 words' top nibbles. The pre pass unpacks them
into its table (`design.TABLE`, L2 `0x200afa00`, 32 x 8 words) whenever the change word moved; the three
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

## After the pan: CHOR and WIDE

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

## On the track's bus: FDN8 and XDLY

`dnfw.inserts.bus` (`csrc/waverider/sharc/insbus.asm`, L2 `0x200bc000`, sw `0xbde000`, between the sample
machines' code and PERC's; its state after it to `0x200bfc00`). A reverb or a delay on a voice would lose
its tail with the voice (a stolen slot starts again) and cost once a voice, so FDN8 and XDLY run once a
**track**, on the block the routing makes of it:

- **The hook.** The engine sums each voice slot's stereo block into the block of the track the slot plays
  (`0x1c1f1e`, the routing: `0x258f68 + 0x100 t`, L 32 floats then R at `+ 0x80`, each voice x 14.125;
  docs/link-research.md §5, §7), then calls the output stage with `CJUMP 0x1c244d (DB)` at sw `0x1c307b`
  (`04181c004d24`, byte-checked on stock 1.12). **The build changes only that call's target**, to
  `wr_inbus`, as `wr_inpost`'s: it saves R0..R15, I0..I4, I12 and ASTAT, runs each track's bus inserts in
  place (slot 1, then slot 2), restores them and JUMPs to `0x1c244d`.
- **Heard where.** On the main mix and on Overbridge's track outputs (both come out of `0x1c244d`). **Not
  in the send FX**: the sends took their taps from the voice blocks before (an insert reverb's tail is not
  sent to the send reverb). A tail goes on after its notes, and after the track is muted (the routing's
  ramps are on its input).
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
  its type's bound (`design.COST`: the runner's cost of one unit x 1.5, the DDR-heavy x 2: FDN8 32,000,
  XDLY 20,000, CHOR 13,000, TAPE 8,200 ..); one that would not end in time is left out of that block (the
  sound passes dry; its state kept; `INS_SKIPS` counts). Until a frame is measured (and in the runner,
  whose clock stands still) every insert runs.
- Measured on the unit (b5diag): LIMIT about 355,000 and the rest of the DN2 about 43,000 a block, so with
  P about 592,000 the inserts have about 120,000 before the deadline when the voices use all of theirs
  (about three FDN8 at their bound), more when they do not. An FDN8 left out of a block is a gap in its
  tail (a click): the price of never costing a voice.

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
