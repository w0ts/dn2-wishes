# Per-track inserts (OS 1.12 fork, not released)

One insert per track at a time, Overtone's idea (complex-ping/overtone, read only; nothing of its
code taken): **M.SEL** picks it, **MOD** mixes it in (dry / wet), and it has up to six knobs of its
own. The six planned, in build order: FUZZ, TAPE, FOLD, CHOR, WIDE, HARM. **Built: FUZZ, TAPE, FOLD, HARM.** CHOR and WIDE need stereo, so they need the post-pan hook (below, not built yet).

## The page

Stock 1.12's track [FX] page is full: BR OVER SRR SR.RT / DEL REV CHR OD.RT, one page (measured in
the emulator). So M.SEL and MOD cannot sit on it, as Overtone puts them, without remapping stock's
FX page lists. Instead, **pressing [FX] again on the FX page opens the INSERT page** of the active
track. [FX] once more, NO, or any page key closes it.

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| M.SEL | the insert's knob 1 | 2 | 3 | 4 | 5 | 6 | MOD |

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
MOD stock's dial, each with stock's label; stock's left panel (the track box, LEV) is the FX page's
own, and so is the title bar (pattern, name, tempo), left as stock drew them under ours. It takes its knobs (rec.c `smp_ui_pop` gives every item to
`ins_pop` first, the encoders' pushes too while it is up), as the RECORDER's page does. The labels
follow M.SEL because our code draws them. Each track keeps every insert's knobs, so switching M.SEL and
back keeps them. An insert this build does not run yet shows SOON under M.SEL and passes the sound
through.

**Phase A (this build): the values live in the ColdFire's RAM.** They are not saved with the kit
(back to the defaults at power-on), and are not lockable, not reachable by LFOs. Phase B, real
lockable parameters (Overtone's slots, a relocated parameter table), is a separate step.

## The values' way to the DSP

The link (`csrc/sampler/link.c` `smp_tdm`) sends them whenever `ins_gen` moves: 32 words at the
sample pool's directory page `+0xf80` (`0x84000f80`), 3 times (one packet may be lost), after any
recorder command and before a load's next chunk. That page's `0xf80..0x1000` lies after the command
block and inside the directory page, which loads never write past the command block (a static
assert in link.c). Per track 8 bytes: M.SEL, MOD, the active insert's six knobs, 0..127. At
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
LEV the output level; MOD the dry / wet.

**TAPE**: DRIV x 1..8 into a soft saturation (a Pade tanh, x (27 + x^2) / (27 + 9 x^2), its input
held to +-3); a short delay per track (a 512-sample ring in DDR `0x82500000` + 2 KB t, zeros at
power-on and cleared whenever a track switches to TAPE) read 2.7 ms back, moved by the wow (WOW up to
1.5 ms either way at WRAT 0.1 .. 2 Hz) and a 7.3 Hz flutter (FLUT up to 0.25 ms), linear between two
samples, the move ramped across each block; AGE the high loss, a one-pole at 16 kHz x 2^(-3 AGE)
(16 .. 2 kHz); HISS white noise (a linear congruential generator) at HISS^2 x 0.03; MOD the dry / wet.

**FOLD**: AMNT gain x 1..16 and SYMM an offset (64 none) into a wavefolder, triangle at SHPE 0 and
sine at 127 (the sine from the same fold's phase); a 20 Hz DC blocker; TONE a one-pole (300 Hz ..
12 kHz); LEV; MOD.

**HARM**: the band above FREQ (a one-pole high-pass, 500 Hz .. 8 kHz) driven x 4 into b^2 (even) and
4 b^3 - 3 b (odd), mixed by EVEN; a DC blocker; TONE a one-pole; added to the dry track at AMNT x 0.5;
LEV; MOD.

**Cost** (the SHARC runner, the pass called alone, slot s playing track s): per **voice**, since each
voice slot playing a track with an insert runs it (a chord on one track costs one insert a voice).

| | one voice | sixteen voices |
|---|---|---|
| every insert OFF (the 16 slots' track lookups) | 941 | |
| FUZZ | 3,772 | 46,252 (about 7 % of a frame) |
| TAPE | 5,410 | 72,460 (about 11 %) |
| FOLD | 4,150 | 52,300 (about 8 %) |
| HARM | 3,104 | 35,564 (about 5 %) |

**Budget** (the build of a673e70 + FOLD/HARM): USB image 2,061,410 of 2,097,152 B (35,742 free),
DSP upload 1,019,056 of 1,048,575 B (29,519 free).

## Not built yet: CHOR and WIDE

Both need the voice in stereo, so after the pan, before the sends: the FX bus's call at sw
`0x1c3054` (`04181c003817`, byte-checked on stock 1.12) retargeted to our pass, which JUMPs on to
`0x1c1738`, as FDN8's call is (additions-scope §12.2, H3). Its register contract is not read yet. On the unit
the guard counts it with the rest; the meter's D shows it. Unmeasured on the unit.

## Checked, and not

- `test/test_inserts.py`: the DSL model equals `dnfw.inserts.ref` bit for bit over 120 blocks (two
  FUZZ tracks, knobs moved, the gate, one switched off and on, MOD 0, loud input); tracks with no
  insert, OFF, or a type not built untouched; every insert OFF leaves every buffer.
- SHARC runner step `inserts` (`scripts/sharc_inserts_step.py`), real blocks of the build with PERC
  voices sounding:
  - every insert OFF: every track buffer after the pass is the buffer before it (30 blocks);
  - FUZZ on two tracks: every buffer after the pass is the reference's (40 blocks), the others
    untouched;
  - the pass's cost alone (above).
- Not checked: the unit (the sound, the cost), the values' packets on the unit's link, the page
  turning values in the emulator beyond what its screenshots show.
