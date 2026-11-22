# A paraphonic mode for our synths: feasibility study (2026-11-14, opt-md)

The User's idea: *"Each new note does not trigger a new voice, but add a osc to current voice if there is one?
Cheap(er) chords."*

This is a study only. No firmware changed, and nothing here was tried on the unit. Costs come from the program's
model, measured on r52-r5 (464361e2) with `scripts/dsp_cost_split.py`. That script is `scripts/dsp_cost.py`'s
method and schedule (steady block, cycles = instructions + 4 L2 + 10 DDR), with the engine's own cost split by
the innermost engine function. Where something is inferred and not measured, it says so.

## Summary

- **Where it pays.** Paraphony pays where a voice is **cheap oscillators into a dear shared stage**:
  - ANALOG 2 and JUNO (the filter is 70-80 % of the engine);
  - SID and the DPRO machines (the MNM output decimator / Digipro stage, 3,000-4,400 a voice).
  
  On these, a 4-note chord costs **42-66 %** of four voices today (table below). On the oscillator-only models
  (PLAITS, SOPHIE) and the unsplit ones (VO-6, TB303, DRONE), it saves only the voice host: 86-95 %.
- **Recommended design: "A, slot groups on the DSP".** Leave the ColdFire's note-on path alone. Each chord note
  still takes a voice slot, with its own NOTE word, gate bits, velocity and glide, all already in the frame. On a
  track set to PARA, the DSP renders the track's sounding slots as one voice: N oscillators into one filter and one
  output slot. The other slots render nothing.
  
  This needs:
  - no new per-pitch frame words;
  - no allocator hook;
  - one per-track PARA word;
  - one ColdFire rule, for the shared envelope's gate.
- **Recommended pilot: ANALOG 2, 2-4 pitches, legato envelope.** About 3-4 days. The unit is the only place to
  hear it: the SHARC runner sets up voice slot 0 alone, so it cannot test a slot group yet (see Risks).

## 1. Per synth: the split and the cost of a chord

`osc` is what one pitch needs again: the oscillator code, run once per pitch. `shared` is the rest of the engine,
run once per voice. That is the filter, the per-voice envelope and DAC, and the decimator. `host` is the voice
host (frame records, stream, resampler, level, guard), 1,930-2,035 a voice.

Each voice also pays **~530** around it (the slot loop's guard and `mnm_ages`' quiet test; docs/dsp-cost.md).

The formulas:
- today, N notes = N × (engine + host + 530);
- para, N notes = host + 530 + shared + N × osc + (N − 1) × 680.

The 680 is a follower slot's own 530 plus about 150 to find its leader and skip. That 150 is an estimate.

| engine | engine | host | osc (per pitch) | shared | 2 notes: today → para | 3 notes | 4 notes |
|---|---:|---:|---:|---:|---|---|---|
| ANALOG2-SL12 | 4,119 | 2,035 | 1,201 | 2,918 | 13,368 → 8,565 (64 %) | 20,052 → 10,446 (52 %) | 26,736 → 12,327 (46 %) |
| ANALOG2-SL24 | 5,957 | 2,035 | 1,201 | 4,756 | 17,044 → 10,403 (61 %) | 25,566 → 12,284 (48 %) | 34,088 → 14,165 (42 %) |
| ANALOG2-LL24 | 5,607 | 2,035 | 1,201 | 4,406 | 16,344 → 10,053 (62 %) | 24,516 → 11,934 (49 %) | 32,688 → 13,815 (42 %) |
| ANALOG2-ML24 | 5,303 | 2,035 | 1,201 | 4,102 | 15,736 → 9,749 (62 %) | 23,604 → 11,630 (49 %) | 31,472 → 13,511 (43 %) |
| JUNO | 4,998 | 2,018 | 1,075 | 3,923 | 15,092 → 9,301 (62 %) | 22,638 → 11,056 (49 %) | 30,184 → 12,811 (42 %) |
| SID 6581 | 4,245 | 2,003 | 1,016 | 3,229 | 13,556 → 8,474 (63 %) | 20,334 → 10,170 (50 %) | 27,112 → 11,866 (44 %) |
| DPRO-WAVE | 8,436 | 2,005 | 5,272 | 3,164 | 21,942 → 16,923 (77 %) | 32,913 → 22,875 (70 %) | 43,884 → 28,827 (66 %) |
| DPRO-DDRW | 9,884 | 2,007 | 5,480 | 4,404 | 24,842 → 18,581 (75 %) | 37,263 → 24,741 (66 %) | 49,684 → 30,901 (62 %) |
| DPRO-DENS | 4,455 | 2,009 | 2,256 | 2,199 | 13,988 → 9,930 (71 %) | 20,982 → 12,866 (61 %) | 27,976 → 15,802 (56 %) |
| DRONE | 6,639 | 2,012 | (whole) | - | 18,362 → 16,500 (90 %) | 27,543 → 23,819 (86 %) | 36,724 → 31,138 (85 %) |
| PLAITS-VA | 7,387 | 1,953 | (whole) | - | 19,740 → 17,937 (91 %) | 29,610 → 26,004 (88 %) | 39,480 → 34,071 (86 %) |
| PLAITS-WS | 8,092 | 1,955 | (whole) | - | 21,154 → 19,349 (91 %) | 31,731 → 28,121 (89 %) | 42,308 → 36,893 (87 %) |
| PLAITS-ADD / FM / MDAL / STRG | 12,425-16,590 | ~1,955 | (whole) | - | 94-95 % | 92-94 % | 91-93 % |
| SOPHIE (FUSE, STAK) | 10,190-13,483 | 1,929 | (whole) | - | 93-94 % | 91-93 % | 89-92 % |
| TB303 | 11,262 | 1,931 | (not split) | - | 94 % | 91 % | 90 % |
| VO-6 | 17,801 | 2,011 | (not split) | - | 95 % | 94 % | 93 % |

What each split is (the measured functions):

- **ANALOG 2.**
  - osc: `analog2.analog2`: both oscillators, the swarm copies, sync, noise, mix and drive (1,201).
  - shared: the filter models (`analog2.filters.models`: 2,131 for SVF LP12, 3,300-4,000 for the 24 dB models)
    plus the per-voice soft knee.
  - Sound: summing the pitches before the filter is the paraphonic sound itself, as on a Mono/Poly or a Matriarch.
  - Drive before the filter is per pitch today, as code. Run on the sum, it intermodulates. Keep it per pitch
    (in `osc`) to stay closest to today, or move it after the sum as a deliberate choice.
- **JUNO.**
  - osc: `juno.juno` (979: DCO, sub, noise and the VCF env/DAC, counted per pitch as an upper bound) plus 96.
  - shared: the ladder (`analog2.filters.models`, 3,392).
  - The amplitude is the DN2's AMP page (the stock voice chain), not JUNO's code.
  - The Juno's own VCF envelope belongs in `shared` (one envelope a voice). That makes para a little cheaper
    than the table.
- **SID 6581, DPRO-WAVE.**
  - osc: `mnm.sid` + `mnm.wave` (1,016), and `mnm.wave` (5,272).
  - shared: `mnm.dec` (3,002 each), the Monomachine output stage.
  - **Inferred, not measured:** if `mnm.dec` is linear (a decimating filter), summing before it gives the same
    sound as N voices summed after it, minus the per-voice AMP. Check by reading `dnfw.mnm.dec` before a pilot on
    these.
- **DPRO-DDRW, DPRO-DENS.**
  - osc: `mnm.ddrw` (5,480), `mnm.dens` (2,256).
  - shared: `mnm.dpro` (3,788 / 1,952), the Digipro common stage.
  - Whether it is linear and per-voice: unverified.
- **PLAITS, SOPHIE.**
  - Each model is a whole oscillator or resonator. STRG and MDAL are resonators struck per note, so they cannot
    be shared.
  - Para only saves the host and slot: about 1,800 a pitch.
- **TB303, DRONE, VO-6.**
  - Not split here. TB303's render is one scheduled block (`mnm.vsched`, 9,984) with the oscillator and the
    diode filter interleaved, so it needs per-operation tags in the scheduler. DRONE (`mnm.sched` 3,360,
    `drone` 2,132) and VO-6 (`vo6`, formant bank and excitation) the same.
  - The table's figure (whole engine per pitch) is the worst case.

**Two costs the table leaves out, both in para's favour.**
- **Per-voice inserts.**
  - Pre inserts run per mapped voice slot, silent ones included (memory "insert skips = all mapped slots").
  - Their guard bounds are 2,900-34,700 a slot (`dnfw.inserts.design.COST`: CHOR 13,000, JUNO 7,100,
    FDN8 34,700).
  - Today an N-note chord on a track with an insert pays it N times. Para with one output slot pays once, if the
    insert pass skips follower slots, which is an easy rule since they are silent.
- **The stock voice chain per slot.** This is the DN2's filter, AMP envelope and pan after our engine. Design A
  keeps it running on every slot (followers on silence), so no saving there. Its cost per slot is not measured
  here.

**The cost model:** `scripts/dsp_cost.py` (docs/dsp-cost.md). These figures are from the current tree, so some
differ from docs/dsp-cost.md's 2026-11-12 table; for example VO-6 is now 17,801.

## 2. The ColdFire side: the note path

These facts come from the repo's docs and csrc. File and address references are as found; the read was
delegated to a subagent and is not re-verified line by line here.

**Stock note-on.** For each note, in the frame ISR, in address order:

| address | what |
|---|---|
| 0x400268f8 | calls the voice trigger 0x400db524 |
| 0x400269e6 | `jsr 0x4002a6a2`, the allocator (the VOICE BUDGET's hook, `csrc/load/hooks.S`, `load.c` 288-396) |
| 0x40026a3c | OWNER `0x80005308[v]` = track |
| 0x40026a44 | NOTE16 `0x8000dda0[v]` = note << 16 |
| 0x40026ac0 | velocity, the cell `0x8000dd40 + 2v` |
| 0x40026afc | gate length into `0x80005220[v]` (HOLD's hook) |
| 0x40026b0c | the note-on mask bit |
| 0x40026ba8 | the filter gate |
| 0x40026bac | `sl_pre(v, t)`, the glide and velocity latch (`csrc/slides/slide.c`) |

- **The velocity cell is per voice.** The agent found docs that say per track. That is settled: the cell is per
  VOICE, proved on claude/mdvel-r5 (dcaf1eae), so docs/modulation-matrix.md's "by track" is stale.
- **Chords.** One allocator call per note, sequencer chord or MIDI. Notes in the same tick never steal each
  other's slots (docs/load-budget.md).
- **STEAL / VOICE MODE.** Stock's steal: CYCLE (oldest) or TRACK, plus REUSE, mono and retrigger
  (docs/load-budget.md). The VOICE BUDGET narrows LIVE_POOL / LIVE_MASK[t] around the allocator call, then may
  release tails over LOAD_TAIL (2,000) to keep FLOOR free.

**Note-off.**
- Per-voice bit masks. The gate timer `0x80005220[k]` -= 14,400 each ISR; at 0 it calls `0x4002b06e(k)` (KEY_UP).
- The frame's amp-off word is composed at 0x4002706a..0x4002708e. HOLD hooks `jsr 0x4002b12e` at 0x40027092
  (`hold_final`) to edit those bits.
- The note of each voice stays in NOTE16[v], so a pitch can be told apart by voice or by note.
- Not traced: where a single live key-up picks its voice inside a held chord (0x40137d3c).

**What each design asks of the ColdFire.**

- **Design A (recommended): DSP slot groups.**
  - The allocator stays stock: each chord note gets its own slot, NOTE, velocity, gate, glide (slide.c), steal
    and budget path, exactly as today.
  - The ColdFire needs only two things:
    1. **A per-track PARA word** in the frame. A spare page record (a page-2/3 choice on the engines that have
       one), or a word on the send pages (the fxpage directory 0xED0). Which record is free is an audit per
       engine, not done here.
    2. **The envelope gate rule** (section 4): HOLD's precedent at 0x40027092. While any slot of a PARA track's
       group is held, keep the output slot's amp-off bit clear. Release it with the last one.
  - **The VOICE BUDGET** charges every slot at the engine's full cost (PER_NOTE, `voice_cost(t)`). On a PARA
    track the followers cost about `osc + 680`. The budget must charge that, or it steals voices it does not need
    to. This is a table change in `load.c`, not a new hook.
- **Design B: one slot, extra pitches written into it** (main's framing: "keep the new note off a new slot").
  - The allocator hook at 0x400269e6 would have to return the track's sounding slot instead of a new one. The
    budget hook can narrow the masks; it does not skip the allocation (`load.c`).
  - The ISR's per-voice block then rewrites OWNER, NOTE16, velocity and gate for that slot. So the newest pitch
    replaces the slot's main note. Our hook keeps a pitch list per voice, and the older pitches go out in new
    frame words.
  - Note-off per pitch needs our own key-up mapping (HOLD's matching through NOTE16 is the precedent). The slot's
    gate ends with the last pitch.
  - Gains over A: it frees voice slots (chords no longer use up the 16) and runs the stock chain once.
  - Costs over A: the riskiest ColdFire change in the series (the allocator's return value, the ISR's per-voice
    block on a reused slot, steal of a slot that holds several pitches), new frame words, and per-pitch
    velocity and glide rebuilt by hand.

## 3. Frame words and DSP memory

**Design A needs no per-pitch words.**
- Each pitch is a slot, with:
  - NOTE: header `2 + 2v`, the DSP's note cell `0x254b14 + 4v`;
  - velocity: header `52 + 2v`, slot 62 for ours;
  - the note-on / amp-off / filter masks: 34 / 36 / 38 / 40, one bit per slot;
  - OWNER: routing word `0xa5a + 2v`.
- The DSP finds a track's group from OWNER.
- It needs one PARA word per track (above). It could also carry N_MAX (2-4), the envelope mode (section 4) and
  the drive placement, packed in one record.

**Design B needs per-voice pitch and gate words.** Up to 4 pitches × 16 voices = 64 half-words, plus gates.
- Frame candidates (docs/link-research.md):
  - the frame padding 2688..2747: 30 words, too few for 4 × 16;
  - "32 spare frame bytes";
  - the tail 2554..2649, unverified (docs/waverider-feasibility.md);
  - no free-word audit per engine exists.
- The DDR link pages (link.c, the fxpage directory 0xED0..0xEFF, already taken) could carry them, with a frame of
  latency. Not ideal for note timing.

**DSP memory (claims go through main).**
- Design A needs **none for the oscillators**. Each follower's oscillator phase and glide stay in its own slot's
  state, which the leader reads and writes. The engines keep per-slot state at `PERC_L.state + 128 slot` (PERC)
  and the MNM / A2 per-slot areas.
- Per track it needs one word: the current output slot and the group's mask, rebuilt every block.
- Design B needs N phase sets inside one voice's state. ANALOG 2's per-voice state would grow by about 3 words a
  pitch, and some engines' state blocks may not have the room (not checked).

## 4. The envelope and glide

On the DN2 the amplitude envelope is the stock voice chain's AMP, per slot. JUNO's own header says so: "no VCA
curve (the DN2's AMP envelope)". The filter envelopes are per voice too: the DN2's filter envelope is stock, per
slot; JUNO has its VCF ADSR inside the engine; ANALOG 2's header names no envelope of its own (not checked further). So "one envelope for the chord" means
**the output slot's** AMP and filter envelopes. The options:

- **Legato (one envelope, mono-synth style).**
  - What: the first note triggers it; further notes join without retriggering; it releases when the last note is
    released.
  - Needs: the ColdFire gate rule (keep the output slot's amp-off bit clear while any slot of the group is held).
    The output slot stays the group's first slot until the group empties. If stock steals that slot, the next
    oldest takes over (one envelope jump).
- **Retrigger (each new note restarts it).**
  - What: every new note retriggers the shared envelope, as a paraphonic Korg Poly-800 does in its "single" mode.
  - Needs: the output slot is the newest held slot, whose envelope just started. When it is released and older
    notes are held, the output falls back to the next newest, whose envelope sits in sustain: a level step, like
    a mono synth's last-note priority. No ColdFire change at all.
- **Setting.** One PARA record with the values OFF / LEGATO / RETRIG. Retrigger comes first (no ColdFire work);
  legato follows with the gate rule.
- **Not paraphonic:** an envelope per pitch into one filter would be a plain poly synth with a shared filter. It
  needs per-pitch VCAs in our engine, which costs about what para saves. Not recommended.
- **Glide per oscillator comes free in design A.** Each slot has its own glide and slide (slide.c per voice), so
  each pitch glides from its own previous note. Design B would have to rebuild glide per pitch in the hook.
  ANALOG 2's own legato glide (page 3, a2glide) stays per voice, so in para it would glide the group's newest
  pitch only. Leave it as is in the pilot.

## 5. Effort, risks, pilot

**Effort, design A.**

| stage | what | effort |
|---|---|---|
| A1 | DSP: group by OWNER on PARA tracks; the leader renders N oscillators (ANALOG 2's `osc` per pitch, phases from each slot's state) into one filter; followers write silence and skip; the bit-exact model plus runner tests for the single-pitch case (PARA OFF identical to today, bit for bit) | 1.5-2 days |
| A2 | ColdFire: the PARA record (UI page and frame word), retrigger mode | 0.5-1 day |
| A3 | ColdFire: legato gate rule (HOLD-style edit at 0x40027092) | 0.5-1 day |
| A4 | VOICE BUDGET: a follower's cost on PARA tracks | 0.5 day |
| A5 | inserts: skip follower slots | 0.5 day |
| A6 | per further engine (JUNO, SID, DPRO-WAVE): its `osc` per pitch | 0.5-1 day each |

**Effort, design B.** About 2-3 weeks. The allocator hook, the frame words, per-pitch key-up, velocity and glide,
steal semantics, and a full emulator suite for the note path.

**Risks.**
- **Testing.** The SHARC runner sets up voice slot 0's chain only (memory "coupled: only voice slot 0"; runner gap
  G12). A note on slot 1+ is silent or NaN there. A slot group cannot be heard in the runner today:
  - the DSP side can be proven bit-exact in the model;
  - the group's sound only on the unit (with the User's OK);
  - or after G12 is fixed. The same gap blocks the sendfx gate step, so fixing G12 pays twice.
- **The stock chain on followers.** Design A keeps paying it on silent slots. If it is dear, design B's single
  slot gains more. Measure it in the runner, on slot 0 alone, before choosing.
- **Steal and budget.** A stolen follower drops its pitch, which is acceptable. A stolen output slot moves the
  output (an envelope jump). The budget must know para costs (A4), or it steals too eagerly.
- **The sound.** Sum level: N pitches into one filter can clip the drive and filter where N voices would not.
  Scale the sum by 1/√N or leave it to the user (a choice for the User). ANALOG 2's drive is per pitch in the
  pilot, so it stays as close as possible to today.
- **Same sound when PARA is OFF.** It must be bit-identical to today on every engine. The model and runner tests
  hold it (A1).

**Recommended pilot.** ANALOG 2 (any filter model), design A, PARA = OFF / RETRIG (A1 + A2 + A4 + A5), then
LEGATO (A3).
- Why ANALOG 2: its oscillator code is cleanly separate from its filter (1,201 against 2,900-4,800). A
  paraphonic analog synth is the sound people expect. Its 4-note chord drops from about 26,700-34,100 to about
  12,300-14,200 cycles. With an insert on the track, it saves the insert three times over as well.
- JUNO next (the same filter code), then SID / DPRO-WAVE once `mnm.dec`'s linearity is checked.

**Reproduce the split:** `python3 scripts/dsp_cost_split.py OUT.json "ANALOG2-SL24,JUNO,..."` (env as
dsp_cost.py: MD_OS_BIN, MNM_OS). About 3 minutes for the 20 engines above, one thread.
