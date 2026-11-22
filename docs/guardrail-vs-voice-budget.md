# Upstream's v0.69 guardrail against our VOICE BUDGET

2026-11-22, for the v0.69 merge. The User's rule: *"compare the designs; if theirs can cover everything we need
(filters x2 [filter 2 is coming: per-voice, ~4.7-7.7k a voice], inserts, paraphonic, etc.), take it; if theirs is
better than ours and we can make it support what we need, take it; otherwise keep ours"*.

Sources: upstream `v0.69:docs/guardrail.md`, `v0.69:src/dnfw/sampler/guardrail.py`, `v0.69:csrc/sampler/guard.c`;
ours `docs/load-budget.md`, `csrc/load/load.c`, `src/dnfw/load/table.json` (with claude/a2f-budget e7c2a375 merged).
Everything below is read from those files unless it says "measured". Nothing here was run on our build.

## The two designs

| | upstream's guardrail (v0.69) | our VOICE BUDGET (since 2026-11-12) |
|---|---|---|
| When it decides | MACHINE SEL's commit (`smp_machine_commit` asks `gr_allowed`) | every note-on, in the audio interrupt, before stock's allocator (`0x400269e6`) |
| What it decides | refuses a machine for a track, with a 2 s box "DSP LIMIT" | which slot a note takes: fits, or steals a sounding slot (release tails first, then the oldest held), more releases if one steal is not enough |
| Unit of pricing | the **kit**: each track's machine `weight` = per-voice cost x a fixed voice count (Monomachine/FM+ 2, every other 1); the sum against LIMIT 320,000; every track counted as sounding | the **slot**: what each of the 16 slots spends now (stock machine slots always; ours while held or while the DSP reports them busy) plus the send FX and bus inserts, against the DSP's measured room |
| Polyphony | not seen: a track counts 1 or 2 voices whatever it plays | seen: each sounding slot is priced |
| Room | a constant: LIMIT from the frame guard's 0.6 of the frame (401,040), less 30,000 of dispatch | the DSP's own report of the room left (idle packet unit 61, `smp_room_now`), `LOAD_AVAIL` 298,615 as the fallback |
| Stock machines | weigh 0 (assumed inside a fixed 416,000) | priced every block (runner: FM TONE ~15,000 a slot, WAVETONE ~9,300, rendered whether a note plays or not) |
| Cost source | a static table, per voice, measured on upstream's v0.69 DSP program on the SHARC runner's memory clock | a static table (`dsp_cost.py`, instructions, x 1.15) **and** the DSP's measured cost per track and per slot (`load_meas`, `smp_tlm_cost`): the dearer wins |
| Never blocks a pick, only a note | no: refuses picks | yes: MACHINE SEL is never refused; the lists show "N VOICES" / "DSP FULL" as information |
| Setting | always on | SETTINGS > PERSONALIZE > VOICE BUDGET, default on |

## What each one prices

| Cost | upstream | ours |
|---|---|---|
| Upstream's machines (PERC, SID, DPRO x3, VO-6, FM+ x3, sample machines, FLEX) | yes, one weight a type (PERC at its dearest family) | yes; PERC per Machinedrum machine (34 costs), MONOMACHINE per engine, the sample machines per type |
| **Our engines** (JUNO 50, ANALOG 2 51, DRONE 52, SOPHIE 53, TB-303 54, PLAITS 55, DRUM 56) | **no**: `PER_VOICE` stops at type 20; ours weigh 0 | yes, per choice: PLAITS' 13 models, SOPHIE's 7, DRUM's 7 types, ANALOG 2's 25 FLT2 filters |
| **A2 filter types** (the FLTR page's SVF, LADR, OTA, DIOD, MS20) | no | yes, per filtered voice (`filter` row: 6,019..7,716 since e7c2a375) |
| **Filter 2** (coming: per voice, ~4.7-7.7k) | no place for it (a weight is per machine type) | one more per-voice row next to `filter` (the same path the A2 filter types take) |
| **Inserts** (per track, per voice) | no | yes (`ins`: 11 types, 3,006..7,135 a voice) |
| **Bus inserts, FDN8 / XDLY / JUNO chorus sends** | no | yes (`bus`, `send`: FDN8 17,615, XDLY 7,622, JUNO 4,907) |
| **PARA** (a chord on one slot) | no (a track is 1 or 2 voices) | yes: `para` / `para_juno` base + add[N] by the chord's sounding notes |
| DRONE HOLD latches | no | yes (never stolen; latched slots hidden from other tracks' notes) |
| The frame guard's skips | it sizes LIMIT so the guard should skip nothing; the guard stays the backstop | it keeps the guard's FLOOR free (`room_asked` = 1.5 x need + (FLOOR - one) + 6k) so the guard should skip nothing; the guard stays the backstop |
| Release tails | no (a kit total) | yes (tails over `LOAD_TAIL` priced and stolen first) |

## Where theirs is better

Their per-voice costs are taken on the runner's **memory clock** (instructions + 0.9 x (4 x L2 + 10 x DDR)), "as the
frame guard sees them". Our table counts instructions (x 1.15) and leans on the DSP's live measure to correct it.
Side by side (per voice; theirs on upstream's v0.69 DSP program, ours `table.json` on ours; **different programs, not
re-measured on ours**):

| machine | upstream (memory clock) | ours (table) | ratio |
|---|---:|---:|---:|
| DPRO DENS | 58,339 | 8,349 | 7.0 |
| VO-6 | 46,210 | 22,376 | 2.1 |
| PERC (dearest) | 45,035 | 17,945 | 2.5 |
| DPRO DDRW | 31,685 | 14,539 | 2.2 |
| FM+ PAR | 29,731 | 19,034 | 1.6 |
| DPRO WAVE | 27,337 | 13,039 | 2.1 |
| FM+ STAT | 22,010 | 13,902 | 1.6 |
| FM+ DYN | 21,976 | 13,982 | 1.6 |
| SID 6581 | 18,915 | 8,217 | 2.3 |
| ONESHOT | 28,913 | 31,577 | 0.9 |
| WERP | 29,376 | 36,845 | 0.8 |
| STRETCH | 11,278 | 19,768 | 0.6 |

If their memory-clock numbers hold on our program, our table under-prices the memory-heavy synth engines by 1.6..7x
(the sample machines are close or over). The live correction (`load_meas`, the slot's own DSP cost, the DSP's room)
covers that after a note has played; the first notes of a kit rely on the table. **Not measured on our build.** This
part is worth taking: re-measure `table.json` on the runner's memory clock (their method, `--steps stress`'s slope from
2 to 6 voices) for every place, ours included.

## Can theirs cover what we need?

No:
- It does not know our seven engines (they weigh 0), the A2 filter types, filter 2, inserts, the bus and send FX, or
  PARA. Each would need a weight, but a weight is per machine type: a per-voice cost that depends on the track's
  filter, inserts or chord size has no place in it without turning the kit total into what `load.c` already computes.
- It prices a kit, not the notes: a JUNO or ANALOG 2 track playing 8 voices counts as 1; a sparse kit of heavy
  machines that never play together is refused although it would fit (its own doc's first limit).
- It refuses picks. Ours never refuses a machine; it decides per note and steals the oldest sound. The User's own
  sparse project with a DRONE held (v0.62.4) is the case a kit total misjudges either way.

Could theirs be made to support it? Only by pricing per track per voice with the live room, which is ours.

## Recommendation

1. **Keep ours** (VOICE BUDGET). Do not take upstream's guardrail into the build: `guard.c`, `guard_tab.h`, the
   `gr_allowed` call in `smp_machine_commit`, the box in `wr_screen`, the `guardrail` gate step. With ours on, its
   kit refusal would add a second, coarser decision that knows none of our engines.
2. **Take their cost method** as a follow-up: re-measure `src/dnfw/load/table.json` on the runner's memory clock
   (their `stress` slope), so the table's first guess is what the frame guard sees. A separate task, not this merge.
3. **Keep the useful runner checks**: their `stress` parts H/H2/H3/I check that the frame guard leaves no voice out
   under a known load; they can stay as runner checks of the frame guard on our program with expectations re-derived
   on our build (not as a check of their weights).
4. Their machines-step change (the other tracks back to FM TONE before the picks) exists only because their
   guardrail refuses picks; without the guardrail it is not needed, but it does no harm and keeps our step closer to
   upstream's.
