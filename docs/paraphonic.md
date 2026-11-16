# PARA: ANALOG 2's paraphonic mode (pilot, 2026-11-15)

The User's idea: "Each new note does not trigger a new voice, but add a osc to current voice if there is one?
Cheap(er) chords." The study is docs/paraphonic-study.md; this is its pilot, design A, on ANALOG 2.

The User's choices (2026-11-15, relayed by main): "Yes, start now"; the drive "Per note, before the sum"; the
level "Louder with more notes" (each note at full level, no scaling of the sum).

## What it does

- **The control:** the VOICE menu (the VOICE key: VOICE SETUP), knob B: **PARA OFF 2 3 4** (how many notes a chord
  takes), on a track playing a PARA engine (ANALOG 2 now). The User, 2026-11-15: "i would put the voice page, for the
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
  B steps PARA 2 3 4 (capped) and back to OFF, one held push a step.
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

- **Inserts** still run on members' (silent) slots.
- **A leader the guard refuses twice** is stolen like any voice: the chord is silent until its next note (the
  reservation makes it rare: its members go first).
- **WDTH**: the stereo spread comes from the leader's own swarm copies only.
- **Velocity**: the chord plays at its leader's (the AMP's) velocity.
- **A note that joins a running chord** may render one engine block out of step with the leader before the
  leader's position reaches it (a new chord's notes start together).
- **The other engines (the User, 2026-11-15: ANALOG 2, then JUNO, then DPRO-WAVE, DDRW, DENS; not SOPHIE, not SID 6581).** The chord pass,
  the roles, the stream positions and the members' silence are the engine's own business nowhere: an engine joins
  by its name in `para.ENGINES` and one `para.stage(...)` call round its shared stage in its half, as ANALOG 2's.
  - **JUNO** fits as is: its half is `_osc` (per note: DCO, sub, noise, its VCF envelope) then `_ladder` and
    `_post` (shared), its block at the same word (ANALOG 2's `bv`), so `stage(p, L, ladder_and_post,
    bv_word=...)`; and its type in `csrc/para/para.h` para_engine (the VOICE menu's B shows PARA for it).
  - **The DPRO machines** do not: their shared stage (`mnm.dec`, DPRO's Digipro stage) reads the
    render's 192-float scratch (IN), not the slot's stream, so a member's per-note part cannot wait in its stream
    for the leader. Either (a) a per-slot buffer for a member's pre-decimator block (16 x 768 B, a claim), or (b) the
    leader runs its members' oscillators itself, on each member's words (the SIMD pairs' way of rendering another
    slot in a slot's turn), no memory. `mnm.dec` (read 2026-11-15) is a polyphase IIR whose
    words are clamped at +-TOP (the 56300's limiter, `sat`): linear below the clamp, so a chord summed before it
    sounds as the notes summed after it until the sum reaches the clamp, where it clips and separate notes would not
    (a level choice for the User, as ANALOG 2's knee). Not measured on sound yet.
