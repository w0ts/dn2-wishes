# PARA as one bigger voice (2026-11-16)

The User, on v0.56.2b: "para still takes two voices for two notes?", then "i would rather take one bigger voice."
Today (docs/paraphonic.md, design B) every note of a PARA chord still takes a voice slot from stock's allocator; the
DSP only shares the filter and envelope. This is the design for a chord that holds **one** slot. Stage 1 only:
no build, nothing changed in the firmware. Claude wrote it; the User decides the questions at the end.

Tags: **[D]** read in stock 1.12's disassembly (objdump of section 3, base 0x40000400) this session; **[M]**
measured this session; **[E]** an estimate, not measured; **[I]** inferred, to check in stage 2.

## 1. What stock 1.12 does today

### Where a note-on picks its slot

- The audio ISR handles each note event of the tick. A note-on calls the allocator at **0x400269e6**
  (`jsr 0x4002a6a2`) with nine arguments: track, note, the event's type (1 note-on), 15, &unison-count, and four
  track fields [D]. Our VOICE BUDGET already wraps this exact call (`csrc/load/hooks.S` `load_alloc_hook`).
- The allocator returns **d1 = the slots given** (one, or several with UNISON) and **d0 = the track's older voices
  on the same note** (REUSE / retrigger), which the ISR releases with stock's one-slot note-off 0x4002b06e
  (0x40026c4a..0x40026c9e) [D].
- The allocator's state [D, names from csrc/load/load.c]: per slot a 20-byte record at 0x40288304 (+1 owner track,
  +8 start stamp, +12 release stamp), the held slots 0x4059dd1c, the tick 0x4059db04, the voices a note gets per
  track (UNISON) 0x4059da00, the live masks (shared pool 0x4059d96c, each track's reserved slots 0x4059d970 =
  VOICES, 0x4059d9b0 "track has a reservation"), copied from staging once a tick (0x4002a414), and per (track, note)
  the slots playing it, 0x40288444 + 1036 t + 4 n [D].

### How the frame tells the DSP which slot plays which note

For each slot k in d1 the ISR (0x40026a00..0x40026c46) writes [D]:

| what | where |
|---|---|
| slot -> track | 0x80005308[k] (the frame sends it as the DSP's routing word, docs/link-research.md) |
| KEY (note << 16, transposed) | 0x8000dda0[k] |
| velocity | 0x8000dd40[k] (word) |
| UNISON detune of this copy | 0x4058f894[k] (table 0x401d5f80 x copy index) |
| gate length (LEN) | 0x80005220[k] (= 0x80003af0 + 4 (1484 + k)); filter gate 0x80005260[k] with FLT.T |
| the sound's values | copied into slot k's parameter block (0x400db0a8 / 0x400db1b6) |
| note-on bit | ISR local fp-172 bit k -> frame +34 |

At the frame's end the masks become frame +34 (note on), +36 (note off), +38 / +40 (filter envelope)
(docs/mute-research.md). The DSP sees slots, never notes: a note that has no slot cannot reach it.

### How VOICES, VOICE STEAL, REUSE and UNISON act

- **VOICES**: a track with reserved voices allocates from its own mask 0x4059d970[t], else from the shared pool [D].
- **VOICE STEAL**: with no free slot in the mask, the allocator takes a sounding one by its STEAL mode (CYCLE: the
  oldest start stamp; TRACK: the track's own) [I, from load.c and emu_load_budget scenario 4].
- **REUSE / retrigger**: the same note already playing on the track comes back in d0 and is released [D].
- **UNISON**: the allocator gives the note several slots (count at fp-72); the ISR gives each its detune [D].

### How a note ends

- A live key-up: the ISR calls the same allocator at **0x40026d86** with the event's type not 1; it looks up
  0x40288444[t][n], releases those slots and returns them in d1; the ISR sets their note-off bits [D].
- A sequenced trig: its slot's gate timer 0x80005220[k] counts down 14,400 a period (0x40025f18); at 0 the slot's
  note-off and 0x4002b06e [D].
- A third note-off route at 0x40026cee reads another (track, note) slot table, 0x405903a0 + 2 (128 t + n) [D];
  what fills it is not decoded yet [stage 2].
- **A muted track's note-on skips allocation altogether** (the ISR jumps to 0x40026e50: no slot, no note bit, no
  timer; docs/mute-research.md) [D]. So "a note-on with no slot" is a state stock already makes every day.

## 2. The design: a joining note takes no slot

```
 ColdFire (audio ISR)                                     DSP (each block)
 --------------------                                     ----------------
 note-on, track t ──► load_alloc_hook (0x400269e6)
                        │
         PARA ON and t's chord held? ──no──► stock allocator ──► slot L ──► frame (+34, KEY, routing)
                        │ yes                                                │
                        ▼                                                    ▼
          no allocator call, d0 = d1 = 0                       slot L = the chord's LEADER:
          (stock state as a muted note)                         its own note from the frame (KEY,
                        │                                       glide, LFO, transpose, detune)
                        ▼                                                    │
          chord list of L (ColdFire RAM):                                    ▼
          up to 8 notes: note, held, LEN timer   ──► TDM link ──►  chord list of L (DSP): 8 offsets
                        ▲                          (link.c,          + held / fade bits
                        │                           slots 8..15)                 │
 key-up ──► 0x40026d86 hook: drop the note                                       ▼
 LEN timer at 0 (hold_final, each frame): drop it         leader renders each note's oscillators,
 last note gone ──► L's note-off (HOLD, as today)         noise, drive from its own per-note state,
                                                           sums them, one filter, knee, AMP envelope
                                                           ──► one voice buffer, one slot
```

- **The chord's first note** is allocated by stock as any note: it becomes the leader slot L.
- **A later note while the chord is held** (PARA ON, ANALOG 2 or JUNO): `load_alloc_hook` does not call the
  allocator and returns d0 = d1 = 0. The ISR then takes its "no slot" path (0x400269fa `beq 0x40026c4a`, d2 = 0,
  next event) [D]. Our C adds the note to L's chord list with its gate length, computed as stock computes it
  (0x40026a48..0x40026a82: the event's LEN byte or the sound's, through table 0x401d8ce4 or 0x40288044) [D; the
  hook must be given a2, the event, which is live at the call].
- **Pitch**: each note's pitch on the DSP is the leader's own pitch plus (its note - the leader's note) semitones.
  So stock's pitch path (transpose, LFO, pitch modulation, UNISON detune, glide of the leader) moves the whole chord.
- **Velocity**: the chord plays at its leader's (as today).
- **The DSP** gets each leader's list (8 notes as semitone offsets, a held bit each) over the ColdFire-to-DSP TDM
  link (link.c: slots 8..15, which stock never fills). Not the frame: writing unused-looking frame words broke stock
  voices once (v0.14..v0.19, link.c).
- **The leader renders every note**: for each listed note, its oscillators, noise and drive from that note's own
  state, summed at full level ("Louder with more notes", as today), then the chord's filter, knee and AMP envelope.
  No members, no member streams, no add pass. The note states live in a pool (8 chords x 8 notes, about 32 words a
  note for ANALOG 2: 8 KB) [E: claim to be placed in the L1/L2 table, docs/dsp-room.md].

### Note-off per note, drop the oldest, a full chord

- A key-up of a joined note: a new hook on the second allocator call, **0x40026d86** (the same wrapper shape as
  `load_alloc_hook`), drops the note from its chord before stock looks it up; stock then finds no slot for it and
  returns nothing [D: 0x4002a6c4..0x4002a6e0, an empty entry branches to 0x4002afbc; its return value to check].
- A sequenced joined note: its own timer in the chord list, counted down 14,400 a period in HOLD's per-frame hook
  (`hold_final`), as stock's 0x40025f18 does for slots.
- The leader's own note ending: L keeps playing the chord (its note fades out, as today's drop of a leader's note);
  L's note-off is held back by HOLD (`para_final`, as today) until the list is empty.
- A 9th note: the list keeps the newest 8; the oldest fades over 6 halves (today's FADE) and its state slot is reused
  after the fade (so 9 states a chord).
- A note already in the chord, played again: that note restarts (no new entry).
- Kit / project load, stop-all (frame +36 = 0xffff): every chord list is cleared.

### UNISON and VOICE STEAL

- **VOICE STEAL**: the chord is one slot, so a steal takes the whole chord (its notes still held are dropped,
  silent until played again), as stock steals one voice.
- **UNISON**: stock gives the first note U slots, each with its detune. Choice for the User (question 2): each unison
  slot leads a copy of the whole chord (U x the cost), or PARA plays the chord on one slot only.

## 3. DSP cost

Measured today, members as slots (`scripts/para_cost.py` on this branch, 2026-11-16, the farm; dsp_cost's method:
instructions + 4 L2 + 10 DDR; steady blocks, ANALOG 2 / JUNO at their defaults, without the 530 a slot the guard
and quiet test cost outside the voice) [M]:

| | ANALOG 2 | JUNO |
|---|---|---|
| a voice, PARA OFF | 6,288 | 7,120 |
| a member slot | 3,038 | 2,226 |
| the leader, 2 / 4 / 8 notes | 7,015 / 7,578 / 8,513 | 7,800 / 8,266 / 9,215 |
| the PARA pass a block, 8 notes | 1,549 | 1,549 |
| 8 notes, PARA OFF (8 slots) | 50,319 | 56,969 |
| 8 notes, PARA today (8 slots) | 29,778 + 1,549 | 24,793 + 1,549 |
| the same with 530 a slot | 35,567 | 30,582 |

One voice, estimated [E]: each joined note costs about what a member costs now (its oscillators, noise and drive),
less its slot's own work (stream positions, quiet test, 530 guard and quiet outside the voice), plus loading and
storing its state from the pool (~400 in L2):

| | ANALOG 2 | JUNO |
|---|---|---|
| a joined note | ~3,000..3,400 | ~2,200..2,600 |
| the chord, 8 notes, one slot | ~28,000..31,000 | ~23,000..26,000 |
| against today's 8 slots (with 530 a slot) | ~-10..-20 % | ~-15..-25 % |

So the gain is **slots, not DSP time**: about the same cycles in one slot instead of eight. Against the per-voice
budget: the frame guard expects a slot at max(1.5 x its last cost, 60,000); an 8-note ANALOG 2 leader's note block
is ~36,000 [E], so its expectation stays at the 60,000 floor, where today a chord reserves 8 x 60,000. The VOICE
BUDGET prices a joining note as the per-note add on the leader's slot (`para_join_cost`, regenerated table).

## 4. Stock instructions touched

| site | today | stage 2 |
|---|---|---|
| 0x400269e6 `jsr 0x4002a6a2` (note-on) | already ours (VOICE BUDGET's hook) | the hook also skips the call for a joining note (d0 = d1 = 0), passes a2 to the C |
| 0x40026d86 `jsr 0x4002a6a2` (note-off by note) | stock | **new hook**, the same 6-byte jsr replaced, same wrapper |
| HOLD's note-off hook (frame +36 / +40, `csrc/hold`) | ours | per-note LEN timers and the chord's final note-off |
| 0x40026cee route (table 0x405903a0) | stock | decode first; hook at 0x40026d02 (8 bytes, 2 instructions) only if it carries notes we must end |
| the allocator 0x4002a6a2..0x4002b300 | stock | **not touched** |

Nothing in the allocator itself changes, and nothing in the frame. The gate's rules: `coldfire` (ISA of the new
hook), `rammap` (only our own .data grows: the chord lists, ~16 x 8 x 4 B), `overbridge` (no frame word touched),
`stockout` (a stock machine's note never enters the PARA path: the hook returns at once, as VOICE BUDGET does).

## 5. Risks

1. **A missed note-off is a stuck chord.** A joined note has no slot, so only our code ends it. Every route must be
   covered: key-up (0x40026d86), LEN (our timer), the 0x40026cee route, stop-all, kit load, PARA turned OFF, the
   track's machine changed, the leader stolen. Each gets an emulator scenario (`scripts/emu_load_budget.py` style).
2. **The audio ISR.** Both hooks run in the interrupt. The note-on hook's stack today is 116 bytes below the call
   (stock's allocator 164); the join path adds a list insert. To measure as VOICE BUDGET did.
3. **One basket.** A refused leader silences the whole chord (today the members go first and the leader keeps
   playing). The guard's lower reservation (60,000 for the chord, not 8 x) makes a refusal rarer [E].
4. **The link.** The chord lists share the TDM link with sample loading; a joined note may start one period late
   [E]. To measure; the frame is not an option (above).
5. **Note states in DSP memory** (~8 KB for 8 chords): a claim in the L1/L2 table; a 9th concurrent chord plays its
   leader's note only [E].
6. **Brick risk**: low and the same kind as VOICE BUDGET's: one more stock jsr redirected in the ISR, the allocator
   untouched, and "a note with no slot" is the muted-track state stock already handles. The RAM guard and the
   brick-risk emulator steps of `ship_gate.py` run on it like any build.

## 6. What the User would see

- **VOICES / voice LEDs**: a PARA chord lights one voice and uses one of the track's VOICES; 16 chords fit where
  today 2 chords of 8 notes fill the machine.
- **VOICE STEAL**: steals whole chords (the oldest chord by CYCLE).
- **Sound**: as today (filter, envelope, drop the oldest at 8, louder with more notes); joined notes follow the
  leader's pitch modulation and transpose.
- **Glide**: today each note glides from its own previous note (stock's per slot). With one voice the leader glides;
  joined notes start at their pitch (question 3).

## 7. Stage 2, if the User says go

Claude does, in order, each step its own commit and gate step: the 0x40026cee route decoded; the ColdFire hooks and
chord lists with emulator scenarios for every note-off route (step 1 alone is a test build: no audible change, the
lists logged by telemetry); the DSP leader loop and pool in the model, bit-exact runner step against today's chord
sum; the budget table; then the full gate. Estimated several days of sessions. The User flashes only a cleared build.

## 8. Built (stage 2, 2026-11-16; the User: "yes, do it all")

The User's answers: UNISON is ignored on a PARA track (the chord stays on one slot); the leader glides the chord, a
joined note starts at its pitch; "re-home": the chord's slot is never taken while the chord holds a note (Claude
built it so: hiding the slot from the allocator gives the same result as moving the notes, without re-creating
stock's per-slot note-on in our code; only when every candidate slot is a held chord does the oldest chord go).

**ColdFire** (`csrc/para/one.c`, `one.h`; hooks in `csrc/load/hooks.S`):
- `pv_pre` (in `load_alloc_hook`, the note-on's allocator call 0x400269e6): a note on a PARA track whose current
  chord holds a note joins it: no allocator call, d0 = d1 = 0 (the ISR's own "no slot" path, a muted note's state).
  Otherwise the held chords' slots are hidden from the live masks for this call (put back in `pv_post`) and a PARA
  track's UNISON count is one for the call.
- `pv_post`: the slot given starts a chord (place 0 the leader's own note); a slot taken from a held chord all the
  same ends that chord (counted, `pv_taken`).
- `pv_rel` (`pv_rel_hook`, the key-up's allocator call 0x40026d86, the one new stock site): a joined note's key-up.
- `pv_final` (HOLD's frame hook, replacing the slot chords' `para_final`): the joined notes' gate timers (stock's
  LEN for a slot, counted as 0x40025f18 counts a slot's), the no-key safety net (a key-held joined note ends when
  stock says no key is held on the track), stop-all, PARA off or the slot lost; the leader's note-off kept back
  while the chord holds a note, sent when none does.
- A chord: 10 places (the leader's own note and 9 joined; 8 sound, the oldest dropped past 8, one may fade).
- The rows (`pv_row`): 6 words a slot, sent by the TDM link (`csrc/sampler/link.c`, first after a command, twice)
  into the pool's DDR at `PV_TABLE` (`dnfw.sampler.machines`: the slice area's unused 32 KB), once the tables are
  READY.

**DSP** (`dnfw.engines.analog2.para`):
- `prepass` (each block, after `mnm_ages`): the first block after a load zeroes the rows (DDR keeps an earlier
  boot's); a slot's note-on waits for a new row (the old chord's row is not taken again); a PARA slot adopts its
  row's chord; each shadow whose place no longer sounds fades out over 6 halves and is freed; a sounding place without
  a shadow takes a free pool block (none free: left out, `LOST` counted); ROLE = LEADER while the slot owns a shadow
  or its own note fades.
- `renders` (PERC's `voice`, one `MDV.block` call site): a LEADER renders each shadow first (its block as a slot's
  words: the leader's knobs and type, the leader's pitch plus the place's offset, the leader's stream position; no
  output), then itself; the engine's `stage` (ANALOG 2, JUNO) skips the shared stage on a shadow and adds the
  shadows' halves on the leader (`add_places`). A shadow has no stereo side (ANALOG 2's WDTH stays the leader's).
- The frame guard and the budget see one voice a chord: the shadows render inside the leader's voice call.

Memory: L1 F1 `0x2E0E44..0x2E0F30` (59 words, the claim to `0x2E1000`); the pool 16 x 1 KB in L2 at `0x200EA000`
(the User's Q5: "16 KB pool in L2", from the User's 64 KB reserve above PERC); the rows in DDR (pool + `PV_TABLE`, 384 B).

**Cost, measured** (`scripts/para_onevoice_cost.py`, dsp_cost's method: instructions + 4 L2 + 10 DDR; the chord's one
slot a block, the pool in L2; without the 530 a slot the guard and quiet test cost outside the voice):

| | ANALOG 2 steady / note block | JUNO steady / note block |
|---|---|---|
| 1 note (PARA ON, alone) | 6,272 / 6,893 | 7,122 / 7,480 |
| 2 notes, one slot | 11,631 / 14,066 | 11,381 / 12,455 |
| 4 notes, one slot | 20,462 / 25,639 | 17,988 / 20,494 |
| 8 notes, one slot | 37,916 / 48,550 | 31,210 / 36,590 |
| 8 notes, PARA OFF (8 slots, para_cost) | 50,319 | 56,969 |
| 8 notes, the slot chords before (8 slots + 8 x 530) | 35,567 | 30,582 |

A joined note costs ~4,520 (ANALOG 2) / ~3,440 (JUNO) a block: a member's render plus its words in L2 (the Q5
estimate, ~1,220). The PARA pass: 13 instructions a block with nothing watched (424 before), ~1,200 with a PARA slot,
~2,100 with an 8-note chord, ~8,000 in a block where 7 notes join (their blocks zeroed). The frame guard expects a
slot at max(1.5 x its last cost, 60,000): an 8-note ANALOG 2 chord's note block (48,550) fits under its floor.

**Checked:**
- `scripts/emu_para_onevoice.py` (gate step `paravoice`, a brick-risk step): 16 of 16 on stock's own allocator:
  the first note and UNISON; a join leaves stock's allocator state byte for byte; nine notes; a joined key-up (stock's
  state as its own call leaves it); the leader's key-up kept back; the last key-up sends the chord's note-off; a
  sequenced joined note ends after stock's LEN for a slot (843,750 / 9,720 a period: 88 frames, as expected); the
  safety net; the chord's slot kept (stock alone takes it); every candidate a held chord; stop-all; PARA off; a
  non-PARA note byte for byte stock's; the row; the stack (164 B, stock's 164 B).
- `scripts/emu_load_budget.py` 20 of 20 (its install now carries lfo4's chunks: since lfo4 shipped, every
  scenario had crashed in the tick's memcpy, an exception in unmapped code).
- `test/test_a2_para.py` 22 of 22 (both engines): a chord on one slot bit for bit against the sum made from today's
  own pieces; PARA off and a chord of one as today; a dropped place fades and frees its block; the leader's own note
  dropped; a new note waits for a new chord; more places than the pool; the first block zeroes the rows.
- The SHARC runner, step `para` (`scripts/sharc_para_step.py`): see the session's numbers.

Not done / known:
- VOICE BUDGET: a joined note does not pass `load_pre` (it takes no slot); the leader's measured cost (the DSP's)
  carries it, a few blocks late; the frame guard stays the net. `para_join_cost`'s join branch is now reached only
  in a corner (a PARA note whose chord is not its track's current one).
- Velocity: the chord plays at its leader's. Glide: joined notes start at their pitch.
- The inserts' and the voice pairs' member rules (`para_off`, `no_chord`) are kept but never fire (no slot is a
  member).

## 9. The row rides in the voice's own frame (2026-11-17)

**What broke.** v0.57.1 on the unit (a8fbf921, scratch/unit-now/v571-checks.md): a PARA chord of 2..5 notes took one
voice slot, as designed, but only its lowest note sounded. The rows went over the TDM link (section 8), which brings
a row a period or more after the leader's note-on frame, and only once the sample tables are READY:
- the DSP's pass zeroed the slot's chord word when the leader's note-on found no chord in its row, and a slot with no
  chord word was never looked at again (`_chord_of`), so the row that came later was never read;
- on the coupled emulator the row never came at all: `smp_tables` was still 1 (the tables sending), and the link
  sends rows only at 2.
The runner and the model always had the row in place before the note-on, so they passed.

**The change** (the User: "shouldnt voice just one dsp voice if one exist already?"): the row travels with the voice.
- The ColdFire (`csrc/para/one.c` `pv_out`, called every frame from `sl_smooth` after the smoother, as the velocity
  is) writes each ANALOG 2 or JUNO voice's row into its own frame words: halfword i in frame slot 50 + i (50..61).
  These are FM TONE's records (SYN group); none of our machines reads them (ours: 25..49 and the velocity's 62).
  Stock voices are not written (the v0.14..v0.19 lesson above: only our machine types' voices).
- The DSP's pass copies a looked-at slot's frame words into its row (`_row_from_frame`) and reads the row as before.
  A note-on and its chord now come in the same frame. Should a row ever come later, the slot keeps waiting for it
  (AWAIT kept while the row shows no chord).
- The link no longer carries rows (`csrc/sampler/link.c` back to its shape before PARA).

**Checks added.**
- Model: a row 1 and 3 blocks after the note-on still makes the chord; the frame slots are none of ours.
- Runner (`sharc_para_step.py`): every note's fundamental in the leader's render (Goertzel, 4 x PARA OFF's, a tenth
  of the leader's own), with the row on time and 3 blocks late (PVL).
- Gate step `parachord` (`scripts/emu_coupled_para.py`): a 3-note PARA chord on JUNO and on ANALOG 2 through both
  processors; one slot, the row, every note heard. On a8fbf921 it fails (no row).

## 10. Chords that never ended, members a frame long, key-ups that matched nothing (2026-11-18)

**On the unit** (v0.59.1, read-only telemetry and PEEK, `scratch/unit-now/para-cpu/`): after playing, all 16 `pv_ch`
on T1 read live with nothing held, and every frame `pv_final`, `pv_on`, stock's 0x4002a3a6 and `pv_row` ran for them:
about 10.5 % of the CPU at rest. `pv_nets` equalled `pv_joins` (57 of 57, later 65 of 65) and `pv_rels` stayed 0;
in a held 4-note chord only the leader's place read HELD.

**Causes, measured** (`scripts/emu_coupled_paralive.py` on main f9d570db, the ColdFire's own UI, ISR and allocator,
the KEYBOARD's trig keys):
- stock's 0x4002a3a6, which `pv_final` took for "a key is held on track t", tests the ARP's key list (0x4059d868 +
  4 t). 0x40029cd4 adds a key to it only when the sound's ARP is on (byte 351); with the ARP off it stays empty while
  keys are held (measured: 0; with byte 351 set, the list holds the keys while held). So the safety net ended every
  joined key-held note at the next frame; its key-up then found nothing held (`pv_rels` 0); the chord then held only
  its leader, and the leader's key-up sent the whole chord's note-off while the other keys were still down.
- `pv_final` cleared `pv_cur` when a chord's last note ended but never its `live`: only a new note on its slot ended it.
- `pv_dirty` was set everywhere and read nowhere since the rows left the TDM link (section 9).

Not reproduced: the unit's 4-note chord that gave 1 start + 2 joins (chord3). Every chord here, 3, 4, 6 and 8 keys
pressed 0, 1, 5 and 20 ms apart, gave 1 start and N - 1 joins; on the unit the fourth note-on never reached the
allocator's hook (starts + joins counted 3), so it was lost before PARA's code (not found).

**The fix** (`csrc/para/one.c`):
- a joined key-held note ends by its own key-up (`pv_rel`); the net runs only with the ARP on (its key-ups go to the
  ARP's list, 0x40029fa6, never to the allocator's key-up call), when that list is empty;
- a chord with nothing held, its note-off sent, RELEASES (`live` 2): its row stays as it is, so the DSP plays its
  notes through the release tail; it ends (`live` 0, its row zero, the DSP's shadows fade and free their pool blocks)
  once the DSP's reports (`smp_tlm_cost`, one a period) say its slot is quiet 48 times in a row (32 ms), each report
  fresh and made at least 8 periods after the release. Quiet: at most 8,000 cycles a block, the telemetry's own
  "sounding" line (link.c TLM_SOUNDING). On the unit an ANALOG 2 PARA slot at rest after its chord read 166..230
  (/ 16), a held 3-4 note chord 1,446..2,807 with single dips to ~309; a chord of two notes or more costs 11,631
  cycles and up until the DSP rests the voice, one note alone ~6,272 (under the line, but with no other note to keep).
  LOAD_TAIL (2,000 cycles) is under the unit's rest cost: it would never have ended a chord. No report (the telemetry
  stopped): the chord stays releasing, as main kept it. Stop-all, PARA off or the slot lost end it at once, as before;
- `pv_dirty` removed;
- the row (the User, 2026-11-18: the same work every frame): `pv_out` writes every ANALOG 2 / JUNO voice's row
  straight into its frame words, each place by masks without branches, bit for bit the row as before; `pv_final`
  reads a chord's sound once and calls stock's 0x4002a3a6 only with the ARP on.

**ColdFire instructions per audio frame** (the ISR's every instruction counted in the emulator, by function; the
chord table written before each frame so main and the fix see the same state):

| | main f9d570db: ISR / PARA's | the fix: ISR / PARA's |
|---|---|---|
| at rest after 17 chords played (16 slots' chords left live on main) | 44,612 / 9,597 | 38,191 / 3,331 |
| every track ANALOG 2, no chord | 39,712 / 4,697 | 38,295 / 3,321 |
| 4 chords of 4 notes held | 40,686 / 5,769 | 38,833 / 3,929 |
| 16 chords of 8 notes held (the worst case) | 45,332 / 10,329 | 41,378 / 6,329 |

On the unit, main's PARA functions at rest with 16 stale chords measured about 10.5 % of the CPU and about 5.1 % with
none live (after a power cycle); at the same rate per instruction (an estimate, not measured on the unit) the fix's
3,321..3,331 are about 3.6 % of the CPU, and the worst case's 6,329 about 6.9 % (main's 10,329: about 11.3 %).

**Checks**: gate step `paralive` (`scripts/emu_coupled_paralive.py`, ColdFire): 131 checks, 65 fail on main f9d570db (A held, B key-ups, C end, D). `paravoice`
check 8 now says the ARP rule (the ARP off: held over 30 frames; on: ends once its list is empty).

## 11. The DSP's pool leaked: chords without their members (2026-11-18, v0.59.2)

**On the unit** (v0.59.2 = section 10's fix, read-only, `scratch/unit-now/para-cpu/rec592a.jsonl`): chords sounded
fewer notes than the keys held. On the ColdFire every member joined and stayed HELD, every key-up matched, every chord
ended; but the chord slot's DSP cost (its telemetry) was the same for 1, 4 and 5 notes (~1,460 / 16), where the
coupled emulator, with a fresh pool, measures 449 for one note and 1,590 for five (all five pitches heard).

**Cause** (read in the DSP's program, proven in its model): a shadow's pool block is freed only when its fade reaches
the end, and the fade moved on only inside its leader's render (`add_places`). After its release the voice RESTS
(MNM_QUIET_BLOCKS of silence after the DN2 AMP: no render at all), so the shadows of a released chord stayed fading
with their blocks taken until that slot's next note. Stock's allocator hands the next chords other slots: after about
5 chords the 16 blocks were gone and later chords played their leader's note alone (LOST). Section 10 made it certain
(the row ends only once the DSP reports the slot quiet, after the rest); v0.59.1 leaked the same way (its chords never
ended).

**Fix** (`dnfw.engines.analog2.para` `_shadow_kept_one`, the per-block pass): a shadow that no longer plays and whose
leader rests is freed at once (the leader's sound has died away after its AMP: nothing of it can be heard); else it
fades as before. The pass reads the leader's rest count (`program.py` passes `RESTS_OFF`, `MNM_QUIET_BLOCKS`). Cost: a
test and a branch per fading shadow per block in the pass, nothing in a voice's render.

**Check**: `test/test_a2_para.py::test_chord_after_chord_each_released_to_rest_renders_every_member` (both engines, the
gate's `unit` step): 24 chords of 3..6 notes on 8 slots in turn, each held, let go, its AMP closed, the voice left to
rest, its row ended: every member has its shadow, nothing LOST, the pool whole between chords. On main-next ce8e92c9
it fails: the pool is empty from the 5th chord and the chords on fresh slots get no member.
