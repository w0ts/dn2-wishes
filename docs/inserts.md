# Per-track inserts (OS 1.12 fork, not released)

One insert per track at a time, Overtone's idea (complex-ping/overtone, read only; nothing of its
code taken): **M.SEL** picks it, **MIX** mixes it in (dry / wet), and it has up to six knobs of its
own. The six, in build order: FUZZ, TAPE, FOLD, CHOR, WIDE, HARM. **All six built** (2026-11-09):
FUZZ, TAPE, FOLD and HARM on the mono voice before the filter, CHOR and WIDE on the voice in stereo
after the pan (below, "After the pan").

## The page

Stock 1.12's track [FX] page is full: BR OVER SRR SR.RT / DEL REV CHR OD.RT, one page (measured in
the emulator). So M.SEL and MIX cannot sit on it, as Overtone puts them, without remapping stock's
FX page lists. Instead **the FX key has two pages** (2026-11-09, the User): **FX 1/2** is stock's track
FX page, **FX 2/2** the INSERT page of the active track.

- [FX] on FX 1/2 opens FX 2/2; [FX] on FX 2/2 goes back to FX 1/2; [FX] on any other page (a SEND page
  too) is stock's, to FX 1/2.
- FUNC + [FX] is stock's alone: the three SEND pages (Delay, Reverb, Chorus), never the INSERT page; from
  FX 2/2 it closes it first.
- On each switch the title bar's message line says **FX (1/2)** or **FX (2/2)**, with stock's own routine
  (`SAY` 0x4005628c on the title view's message line, as stock's "Delay (1/3)"; stock's own "FX" on
  entering FX 1/2 is renamed before it is drawn, its slide kept).
- Both pages show stock's page dots at the right edge (`0x4006598a`, two, the current one filled), as
  stock's multi-page pages do.
- NO or any page key closes FX 2/2.

The views are found in the screen's view list (as rec.c's question test): the FX page's class
`0x401e1448`, the title bar's `0x401e1d28` (its +120 is the message line; its text, a std::string at
+0x48), measured in the 1.12 emulator.

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| M.SEL | the insert's knob 1 | 2 | 3 | 4 | 5 | 6 | MIX |

M.SEL turns like a stock multi-choice (2026-11-09, the User: one detent per type was far too
sensitive): a 0..127 value turned as a knob, each type a band of it, `type = value x 7 / 128`
(OFF 0..18, FUZZ 19..36, TAPE 37..54, FOLD 55..73, CHOR 74..91, WIDE 92..109, HARM 110..127).

| insert | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| FUZZ | DRIV | TONE | BIAS | PRE | GATE | LEV |
| TAPE | DRIV | WOW | WRAT | FLUT | AGE | HISS |
| FOLD | AMNT | SYMM | SHPE | TONE | LEV | |
| CHOR | DPTH | RATE | DLY | VOIC | WDTH | FDBK |
| WIDE | WDTH | TIME | BASS | TONE | | |
| HARM | AMNT | FREQ | EVEN | TONE | LEV | |

`csrc/inserts/ins.c` draws the page over the screen (page.c `wr_screen`) with **stock 1.12's own
widgets** (`csrc/waverider/widgets.h`, docs/widgets.md): M.SEL a choice box, the insert's knobs and
MIX stock's dial, each with stock's label; stock's left panel (the track box, LEV) is the FX page's
own, and so is the title bar (pattern, name, tempo), left as stock drew them under ours. It takes its knobs (rec.c `smp_ui_pop` gives every item to
`ins_pop` first, the encoders' pushes too while it is up), as the RECORDER's page does. The labels
follow M.SEL because our code draws them. Each track keeps every insert's knobs, so switching M.SEL and
back keeps them. (An insert a build does not run shows SOON under M.SEL and passes the sound
through; none in this build.)

**Phase A (this build): the values live in the ColdFire's RAM.** They are not saved with the kit
(back to the defaults at power-on), and are not lockable, not reachable by LFOs. Phase B, real
lockable parameters (Overtone's slots, a relocated parameter table), is a separate step.

## The values' way to the DSP

The link (`csrc/sampler/link.c` `smp_tdm`) sends them whenever `ins_gen` moves: 32 words at the
sample pool's directory page `+0xf80` (`0x84000f80`), 3 times (one packet may be lost), after any
recorder command and before a load's next chunk. That page's `0xf80..0x1000` lies after the command
block and inside the directory page, which loads never write past the command block (a static
assert in link.c). Per track 8 bytes: M.SEL, MIX, the active insert's six knobs, 0..127. At
power-on the pool's directory is zeros, so every insert is OFF until the ColdFire's first send.

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
- On the unit (b5 d071dbc, sha `f7cc86f3...`, 2026-11-09): CHOR and WIDE work, so the stereo blocks are
  where the readers read them. Not checked: the cost on the unit,
  the values' packets on the unit's link, the page turning values in the emulator beyond what its
  screenshots show.
