# PARA: paraphonic mode for ANALOG 2 (pilot) and JUNO (2026-11-15)

The User's idea: "Each new note does not trigger a new voice, but add a osc to current voice if there is one?
Cheap(er) chords." The study is docs/paraphonic-study.md; this is its pilot, design A, on ANALOG 2.

The User's choices (2026-11-15, relayed by main): "Yes, start now"; the drive "Per note, before the sum"; the
level "Louder with more notes" (each note at full level, no scaling of the sum).

## What it does

- **The control:** the VOICE menu (the VOICE key: VOICE SETUP), knob B: **PARA OFF / ON** (2026-11-15, the User:
  "i would have expected the para (in voice page) to be on or off ?"; ON: a chord of 4 notes, later notes dropped;
  stored as MOD 3, so an older build plays it as 4 pitches; an older project's 1 or 2 shows and plays as ON), on a track playing a PARA engine (ANALOG 2, JUNO). The User, 2026-11-15: "i would put the voice page, for the
  synth that support it. on B knob". Stock leaves B empty ("---"; a turn of it changes nothing, measured in the
  emulator: top row VOICE STEAL, ---, ---, REUSE; bottom VOICES, UNISON STATE, V.AMNT, SPREAD). On any other track
  the menu is stock's. One step per four detents, as every choice knob, through the knob's own path (setValue: undo,
  the kit and the frame see it). The value is the track's sound's stock record MOD (id 248, frame slot 37,
  0..0x300), whose stock default 0 is OFF, so every saved track plays as before (`csrc/para`).
- **The sound:** on a PARA track, the notes held together play as ONE voice: each note's oscillators, noise and
  drive (as today, per note), summed at full level, then one filter and one soft knee, the first note's (its CUT,
  RES and key tracking from its note).
- **The envelope:** one for the chord, legato: the chord's first note starts the AMP envelope, later notes join
  without restarting it, and the chord releases when its last note ends.
- **Notes past N:** the first N notes of a chord play; later ones are silent until the chord ends.
- **A new chord** starts when a note comes while none of the track's chord's notes is held; the last chord's tail
  plays on beside it.
- **Glide:** each note glides from its own previous note (stock's per voice). ANALOG 2's own GLID / GLTY (page 3)
  stays per voice too.

## JUNO (2026-11-15, main: "go on JUNO PARA next")

The same design, on JUNO's own split: each note's DCO (saw, pulse, sub, noise: `juno._osc`) per note; the ladder
and the VCA (`_ladder`, `_post`) the chord's, on its leader (`para.stage` round them in `juno.half`; the block at the
same word as ANALOG 2's, `bv`). The chord's VCF envelope and its key tracking are the leader's own (JUNO's envelope
and DAC run in its `pitch`, per voice; the ladder reads the leader's). Type 23 in `csrc/para/para.h`: the VOICE
menu's B, HOLD's legato rule and the budget take it as ANALOG 2's.

What it costs (`scripts/para_cost.py`, steady / note block, without PER_VOICE or the margin):

| | 2 notes | 3 notes | 4 notes |
|---|---|---|---|
| a voice, PARA OFF | 7,098 / 7,455 | (each) | (each) |
| a member | 3,336 / 3,693 | 3,336 / 3,693 | 3,336 / 3,693 |
| the leader | 7,744 / 8,102 | 7,966 / 8,323 | 8,186 / 8,544 |
| the chord in all, PARA OFF | 14,196 / 14,912 | 21,294 / 22,367 | 28,388 / 29,820 |
| the chord in all, PARA | 11,080 / 11,795 | 14,640 / 15,711 | 18,196 / 19,625 |

A 4-note JUNO chord costs 36 % less than four voices (ANALOG 2's: 21 %). The budget prices a joining JUNO note at
`LOAD_PARA_JUNO_MEMBER` + `LOAD_PARA_JUNO_ADD` (4,859 + 723 with PER_VOICE and the margin; table key `para_juno`).

Checked (2026-11-15):
- `test/test_a2_para.py`, every test for both engines: a 4-note JUNO chord's leader bit for bit against the same sum
  made from today's pieces (each member's engine with its ladder and VCA taken out); PARA OFF and a chord of one as
  today; the first N play; the chords' rules; a refused member left out; a held chord past the quiet test.
- JUNO with PARA OFF before and after (claude/para 822b3035 against this branch): six model renders, 120 blocks each
  (INIT, a release, pulse + sub + noise, resonance with the envelope and a release, a high note, a low note with
  the HPF), every output word the same.
- The SHARC runner's step `para`, both engines, every check passing (1,519 s): every slot of `PARA_a2`,
  `PARA_a2_off`, `PARA_juno`, `PARA_juno_off` bit-exact to the model; for JUNO as for ANALOG 2, the leader sounds
  and the members are exact silence, the chord held 80 blocks keeps its members, a refused member is left out
  (poisoned or not, the same leader), with room for a voice and a half the members go and the leader plays.
- `scripts/emu_load_budget.py` 19 of 19 (17: a JUNO join priced as a JUNO member).
- `scripts/emu_para_vmenu.py` gains a JUNO track (its B row as ANALOG 2's, a step): not run here (it needs the
  build's own snapshot and the panel's frame clock, the integrator's).

## How (design A: slot groups on the DSP)

Every note still takes a voice slot (the allocator, velocity, glide and steal are stock's). The DSP groups a PARA
track's slots into chords (`dnfw.engines.analog2.para`):

- A chord plays on its **leader**, the slot whose note started it. The other slots (**members**) run ANALOG 2's
  oscillators, noise and drive into their own 44.1 kHz stream, skip their filter, knee and stereo side, and write
  silence to their voice buffer. The leader adds each member's post-drive half to its own (one member at a time,
  in slot order) after its drive, then filters.
- Each slot keeps its own stream position, so two slots would not render an engine block in the same DSP block.
  After its block the leader gives every member its position, so from the next block on they render together.
  The slots run newest first (`mnm_ages`), so the leader (the oldest) runs after its members.
- The DSP tracks which slots are held (the frame's note-on bit at offset 34 sets it, the note-off bit at 36
  clears it) and the chords: per track its current chord's leader, per leader its members, per slot its role
  (`prepass`, after `mnm_ages`, once a block).
- The ColdFire holds a PARA chord's note-offs back (amp +36 and filter-envelope +40 gates) until its last note
  ends, then sends them together (`csrc/hold/hold.c` para_final, in HOLD's hook on the frame's note-off words).
  It tracks held voices itself (note-on to first note-off), not through the gate timers.

Memory (DSP): 49 words, zero after every DSP load (`para.AREA`: L1 F1 0x2E0E44..0x2E0F08, 196 B, main's claim, 2026-11-15). No per-slot memory:
a member's stream is its own.

## Checked

- `test/test_a2_para.py` (the model: several slots in one memory, run as the DSP runs them):
  - a 4-note chord's leader bit for bit against the same sum made from today's own pieces (each member's engine with
    its filter and knee taken out, its post-drive halves added to an unchanged leader's); the members exact zeros;
  - PARA OFF: three slots each play exactly as if alone; a chord of one plays as PARA OFF;
  - the first N play, the rest are dropped; a releasing chord keeps its leader while a new one starts; a taken
    leader hands its chord to its oldest member.
- PARA OFF against r53-r10, untouched: 10 ANALOG 2 scenarios (every filter model, swarm with sync, width and drive,
  both glide types, PWM, noise, high notes; 120 blocks each), every output word the same (scratch golden renders).
- SHARC runner, step `mnm`: every slot of every run bit-exact to the model (the model now runs the slots in the
  DSP's order on one memory, the PARA pass first); runs `PARA_a2` (a 4-note chord on one track: its leader sounds,
  its members exact silence) and `PARA_a2_off` (each slot its own note).
- ColdFire emulator, `scripts/emu_matrix.py` scenario `para` (the gate's step 6x): the note-off rule frame by frame.
- The gate's step `paravmenu` (`scripts/emu_para_vmenu.py`, needs the panel's frame clock, 4c7a49ff): on a stock
  machine's track the VOICE menu as before after turns of B and C; on an ANALOG 2 track only B's label row differs;
  B steps OFF to ON (stored 3) and back, one held push a step; an older project's 1 shows as ON.
- The VOICE menu (`csrc/para/vmenu.c`; the hook `vm_seen_hook` at 0x400285C0 replaces stock's `pea "---"` for B
  with the same push), test builds v0.53-para1..3 in the ColdFire emulator (the integrator, 2026-11-15;
  side-session-notes paraphonic-voice-menu/build*/):
  - on a stock machine's track, the VOICE menu's screen and its screens after pushed turns of B and C are
    byte-identical to stock 1.12's;
  - on an ANALOG 2 track, B's label row reads PARA OFF (clear of the voice circles);
  - turning B: OFF -> 2 -> 3 -> 4, capped at 4, and back to OFF (floor), measured one held push a step (four detents
    each, the UI settled 60 M instructions between holds): MOD 0x0100 0x0200 0x0300 0x0300 0x0300, then 0x0200 0x0100
    0x0000 0x0000, vm_sets 1 2 3 3 3 4 5 6 6, each screen "PARA x" as MOD (side-session-notes
    paraphonic-voice-menu/build-para3/steps/);
  - the harness's later holds stall the UI for their first ~7 detents (no screen, no item): stock's own knob E
    (VOICES) does exactly the same under the same timing (the control run), so it is the harness's or stock's, not
    PARA's.

## Design B: a member is not resampled (2026-11-15, the User: "Do that, skip DDRW/DENS")

A member writes silence over its voice buffer, so what the voice host's resampler (44.1 to 48 kHz, Catmull-Rom,
`dnfw.md.voice._resample`, 1,017 a block) writes there is never heard. A member now skips it: its read position
moves on as the resampler moves it (the same 32 adds of the step, `_position_only`), nothing is read or written,
and its stream (its per-note halves, which its leader adds) is untouched. Its silence is not guarded either: the
output guard would write the same +0.0s and find nothing (a MEMBER's or DROPPED slot, `para.silent_role`). Every
other voice runs both as before (two role tests, ~15 instructions a voice). The quiet test (`peak32` on the
member's stream) stays: a member rests by it as before, and leaving it out is not proven safe.

Cost (`scripts/para_cost.py`, steady / note block; the leader carries its two role tests):

| | ANALOG 2 | JUNO |
|---|---|---|
| a member, design A | 4,148 / 4,770 | 3,336 / 3,693 |
| a member, design B | 3,038 / 3,657 | 2,226 / 2,584 |
| the leader (4 notes) | 7,520 / 8,950 | 8,208 / 8,567 |
| 4 notes, PARA OFF | 25,156 | 28,480 |
| 4 notes, PARA (B) | 16,633 (-34 %) | 14,886 (-48 %) |

The load table's members (`para`, `para_juno`: (start + PER_VOICE) x 1.15): ANALOG 2 6,095 -> 4,817, JUNO 4,859 -> 3,581.

Checked: `test_a2_para.test_design_b_members_skip_the_resampler_and_the_guard_with_the_same_sound` (both engines:
every slot's buffer, role and voice words and the quiet counts the same as with the members resampled, every block
of a held chord past the quiet test and its release; the members cost less); runner step `para` (every slot
bit-exact to the model, the guard and quiet checks as before), also built with voice pairs (`DN2_PAIRS`).

## Cost, the frame guard and the VOICE BUDGET (2026-11-15, main for the User: "will the guard understand this?")

What a chord costs (`scripts/para_cost.py`, dsp_cost's method on the model: instructions + 4 L2 + 10 DDR, ANALOG 2
at its defaults; steady / note block, without PER_VOICE or the margin):

| | 2 notes | 3 notes | 4 notes |
|---|---|---|---|
| a voice, PARA OFF | 6,266 / 6,885 | (each) | (each) |
| a member | 4,132 / 4,752 | 4,132 / 4,752 | 4,132 / 4,752 |
| the leader | 6,940 / 8,108 | 7,255 / 8,641 | 7,442 / 8,873 |
| the PARA pass (once a block) | 896 / 1,861 | 916 / 2,287 | 936 / 2,714 |
| the chord in all, PARA OFF | 12,532 / 13,772 | 18,798 / 20,657 | 25,064 / 27,536 |
| the chord in all, PARA | 11,072 / 12,860 | 15,521 / 18,147 | 19,841 / 23,131 |

The PARA pass costs 228 a block with no chord, and every ANALOG 2 voice about 130 more for its role checks (the
regenerated load table: each `a2flt` entry +150 with the margin).

**The frame guard** (`dnfw.perc.guard.around`) expects each slot at max(1.5 x its last cost, FLOOR 60,000), so
members and leader alike at 60,000; the slots run newest first, a chord's leader last of it. Before this change the
leader was the slot most likely refused under load (the whole chord silent, then, after its strikes, stolen until
its next note), and a refused or resting member's stream words (an earlier pass of its stream) were still added
by the leader: stale audio. Now:
- a member marks its half RENDERED (ROLE bit 20) when it runs; the leader adds only those (`para.add_members`);
- a member is let in only if its leader's expected cost still fits after it (`para.reserve`, the guard's RESERVE
  hook): under load a chord loses members, newest first, and keeps its leader;
- a member's quiet test (`mnm_ages`: 64 blocks of silence in its buffer, no note: rest) takes its leader's count
  (`para.quiet_as_leader`): a member writes silence while its sound is in its leader's, so it rested 43 ms into a
  held chord (the chord thinned to the leader's note; before RENDERED, the leader then added stale words).

**The VOICE BUDGET** (`csrc/load/load.c`) priced every note of a PARA track at the track's dearest measured voice
(its leader's) and each member slot the same: it stole early. Now (`load_pre`, `para_join_cost`):
- a note with none of the track's voices held starts a chord: the track's voice cost, as before;
- a note joining a held chord (fewer than N held): `LOAD_PARA_MEMBER` + `LOAD_PARA_ADD` (6,095 + 1,087 with
  PER_VOICE and the margin, from `scripts/para_cost.py` through `scripts/gen_load_table.py`). It is the newest note,
  so the DSP runs it first: its leader's guard room is the one `room_asked` already keeps for the last voice. While
  the DSP reports its room, the ask is mostly that guard floor (need x 1.5 + FLOOR - need + 6,000), so a member's
  lower price changes the ask little (about 1,400 less than a voice's); by LOAD_AVAIL (no room reported) and in the
  slots' sum it is the full difference;
- a note past N (dropped, not rendered): `LOAD_PARA_DROPPED` (610: its guard and quiet test);
- a PARA track's sounding slot is priced at its own DSP measure (at least a member's), not the track's dearest;
- the budget never releases a PARA chord's voice to make room: HOLD keeps its note-off back while the chord is held.

Checked: `test/test_a2_para.py` (a refused member's words never reach the leader: poisoned or not, the same block;
a held chord keeps its members past the quiet test, which fails without the fix); `test/test_load_budget.py` (8);
`scripts/emu_load_budget.py` 18 of 18 on stock's own allocator (13: a joining note fits as a member where PARA OFF
steals; 14: a dropped note; 15: a new chord; 16: the releases skip a chord's voices); the SHARC runner's step `para`
(also inside `mnm`), 2026-11-15, every check passing:
- `PARA_a2` (80 blocks) and `PARA_a2_off`: every slot, every block, bit-exact to the model;
- held 80 blocks (past the quiet test's 64): at the last block every member RENDERED, its quiet count 0;
- the clock fed from block 6, slot 1 refused (then stolen): the leader's output bit-identical with slot 1's stream
  words poured full of 1000.0 and without, different from the whole chord's every block; members 0 and 2 render in
  the same blocks as with the clock still (a member renders when its stream is due a half, not every block);
- room for a voice and a half (LIMIT_PERC 400,000 less 90,000): the members refused every block, the leader plays.
The full `mnm` run on the same DSP code: every Monomachine machine's runs bit-exact (5,357 s).

## Not in the pilot (follow-ups)

- **Inserts**: done (2026-11-15, main: inserts on members' silent slots could cost more than PARA saves). The
  pre and post voice-insert passes read each slot's ROLE word (set by PERC's prepass earlier in the same block) and
  play a MEMBER's or DROPPED slot's inserts as OFF (`dnfw.inserts.program.para_off`): no cost, and they forget
  (from silence when the slot plays again). The leader's inserts run on the chord, as before. Checked: the models
  against the references with those slots off their track (`test/test_para_inserts.py`), and runner step `para`
  (`scripts/sharc_parains_step.py`, FUZZ pre and CHOR post on the chord's track): every slot after each pass the
  references', the leader bit-identical to a run with the roles hidden from the passes, the members untouched.
- **A leader the guard refuses twice** is stolen like any voice: the chord is silent until its next note (the
  reservation makes it rare: its members go first).
- **WDTH**: the stereo spread comes from the leader's own swarm copies only.
- **Velocity**: the chord plays at its leader's (the AMP's) velocity.
- **A note that joins a running chord** may render one engine block out of step with the leader before the
  leader's position reaches it (a new chord's notes start together).
- **The other engines (the User, 2026-11-15: ANALOG 2, then JUNO; not SOPHIE, not SID 6581).** The chord pass,
  the roles, the stream positions and the members' silence are the engine's own business nowhere: an engine joins
  by its name in `para.ENGINES` and one `para.stage(...)` call round its shared stage in its half, as ANALOG 2's.
  - **JUNO**: done (the section above).
  - **DPRO-DDRW, DPRO-DENS: no PARA** (the User, 2026-11-15, "skip DDRW/DENS", after a measurement: at OS 1
    they have no stage worth sharing, a 16-sample limiter of 204 a block; design A would cost more than it saves,
    design B 2..8 % at most).
  - **DPRO-WAVE: decided later.** Its 4x decimator (3,012 of 10,467 a block) could be shared, but its input is the
    render's one L1 scratch (IN), so each member's 4x halves would need ~8 KB of L1 kept for the leader, and the
    decimator's clamp clips a summed chord (a level choice). Measured on the model 2026-11-15 (side note
    dpro-para-measure-2026-11-15.md): about -13 % at 4 notes with design A, -20 % with A and B.
