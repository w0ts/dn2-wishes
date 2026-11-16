# LFO4 and lfowaves on OS 1.12: the port plan (stage 1)

The User (2026-11-14): "Port both", "we can always disable lfo4". Stage 1 was this plan; since then:

- **lfowaves is ported and shipped** (claude/lfowaves-112: `dnfw.mods.SHIPPED`, the gate's step 6m3, r8).
- **The User's two answers** (2026-11-14, through main):
  - (a) LFO4's stored values go **into the wishes record** ("Into the wishes record"): the stored sound's
    lane stays the wishes link. A sound saved by upstream's 1.11 lfo4 carries its LFO4 values in that lane;
    on our series the lane is not a valid link (its check rejects it), so **such a sound loads with LFO4 at
    its defaults**. Its LFO1..3 and everything else load as saved.
  - (d) the cascade **includes LFO4** ("Include"): each LFO, LFO4 among them, modulates the other LFOs'
    controls, one frame late, as LFO1..3 do (csrc/modulation/cascade.c).
- lfo4 is a go in the stages of section 7, behind `DN2_LFO4` (default off until it passes its gate steps; then
  main asks the User to switch it on).
Origin: upstream PR #153 (4c574a66, "lfo4, lfowaves and bootscreen on the platform: all three combine"),
`csrc/lfo4/`, `src/dnfw/mods/lfo4.py`, `src/dnfw/mods/lfowaves.py`, their `*_code.json`, `docs/lfo4-*.md`.
Base: our 1.12 series at 0a85e598 (r6's tree). Every number below was measured on 2026-11-14 unless it says
otherwise: the 1.12 sites with `scripts/port_os112.py`'s own alignment (`Map`, `classify`) against the two stock
images, our side from r6's `waverider_code.json` and `dnfw.mods.waverider.ram()`.

## 1. The stock sites: every one has a proven 1.12 counterpart

| mod | edits | exact in place | exact, moved | moved, only ported operands differ | refused |
|---|---|---|---|---|---|
| lfo4 | 209 | 40 | 99 | 70 (29 in place, 41 moved) | 0 |
| lfowaves | 33 | 3 | 21 | 9 | 0 |

"Only ported operands differ": the 1.11 stock bytes become the 1.12 bytes exactly once each long in them is
translated by `classify` (a code address by its region's delta, a BSS address +0x1000). They are the parameter
table 0x401F7F94 -> 0x401F83A4 (56 of lfo4's), the LFO state arrays (BSS +0x1000) and lfowaves' wave tables
(0x4020B2EC -> 0x4020B7A4 ...). lfowaves' six fills (`from_va`) all move by their region's delta. The literals in
`csrc/lfo4/*`, `lfo4.py`, `lfowaves.py`, `gen_lfo4_code.py` and `gen_lfo_waves_code.py`: 16 same, 15 moved,
3 BSS, 12 outside MAIN OS and BSS (our RAM), **0 refused**. So the port of the sites is `port_os112.py` with
those files added to its list, then `gen_lfo4_code.py` / `gen_lfo_waves_code.py` against 1.12, whose own
stock-bytes guards re-prove each placement.

## 2. RAM and code: no address overlaps ours

| owner | range | what |
|---|---|---|
| lfo4 | 0x46700000 .. 0x46702A00 | LFO state LIVE, SECOND, BACKUP (3 x 2,560 B: 16 tracks x 4 LFOs x 40 B) |
| lfo4 | 0x46800000 .. 0x46802A68 | its C and BSS (CODE chunk) |
| lfo4 | 0x46900000 .. 0x46904D60 | the relocated parameter table (330 records: stock's 320 + its 10) and names |
| lfowaves | 0x46740000 .. 0x46742000 | NOIS state |
| lfowaves | 0x46750000 .. 0x46750310 | the glyph tiles |
| lfowaves | 0x46780000 .. 0x46780A7C | its blob |
| ours | 0x46708000 .. 0x4670869C | the boot-screen stamp (already off 0x46700000: upstream moved it for lfo4) |
| ours | 0x4670C000, 0x4670F000, 0x4670F800 .. 0x4670FBC0 | SYN pages, FLTR shims, machine shims |
| ours | 0x46A40000 .. 0x46A7D018, 0x46AF0000.., 0x46AF8000.., 0x46AFF000.. | page renderer, MD knob, modulation, meter |
| ours | 0x46B00000 .. 0x47000000, 0x47000000.., 0x47100000.., 0x47280000.., 0x476F0000.. | mirror, MD/MnM tables, profiler, wishes, matrix |

No range overlaps. lfo4's two CODE chunks and lfowaves' blob go in the platform's appended area with ours; its
room on 1.12 must be checked with all three (stage 2, the platform's own refusal).

## 3. Edit sites shared with ours

Of lfo4's 209 sites, 2 overlap our 1,118 edits byte for byte, both the stored-sound hooks:

- **LOAD** 0x400DD3E6 (1.11 0x400DD282): ours `wish_load` (and its stub replays `moveq #25,%d2`: machine types
  -1..23 kept); lfo4's `lfo4_load_stub`.
- **SAVE** 0x400DD888 (1.11 0x400DD724): ours `wish_save`; lfo4's `lfo4_save_stub`.

One chained stub each (ours, then lfo4's, then the displaced bytes as ours replays them). lfowaves: none.
Another 19 lfo4 sites sit within 64 B of ours in the same functions (slot_to_id, the attribute rows and name
columns whose bounds we raised 4 -> 23, the page descriptors, the setter's write before smp_quant): separate
bytes, they combine, but the merged image needs its own check of each function.

## 4. Conflicts by meaning (the real work)

1. **The stored sound's lane.** lfo4 keeps LFO4's eight values in stored ids 4, 8, ... 32 (bytes 36..92, the rank
   Elektron leaves unused). Our wishes link uses the same ids 4..28 (`csrc/wishes/wish.h` WL_ID_*;
   `docs/wishes-record.md`: Overtone, and LFO4's, "stay mutually exclusive"). Both cannot live there.
   **Decided (the User): into the wishes record.** LFO4's eight values move into the sound's wishes record (it
   is per sound and already linked), and the lane stays the link. That changes lfo4's `store.c` and adds a
   field to the wishes record (its version). A sound whose LFO4 is at its defaults needs no record for it; one
   whose LFO4 is not gets a record (as an edited route or envelope does). A 1.11 lfo4 sound loads LFO4 at its
   defaults (above).
2. **The parameter table moves.** lfo4 redirects 56 stock references to its copy at 0x46900000 (stock reads
   records there). Our C reads and **writes** stock's table at 0x401F83A4 in ~30 places through 13 local macros
   (fmt.c formatters and the fine ranges, md_page.c STU, page.c names and formatters, smp_page.c, popup_stock.c,
   moving.c, matrix env2_page.c and routes_pop.c, fxpage, fdn8, xdly, slice, rectrig, rec.c). With lfo4 on, our
   runtime writes would land in a table stock no longer reads. One header (`REC_BASE`, chosen at generation)
   and every macro through it. Build-time record edits are carried (lfo4 copies the table from the image it is
   given), if waverider is applied before lfo4.
3. **The LFO state moves.** lfo4 moves LIVE / SECOND / BACKUP from BSS (1.12 0x44640C18 / 0x44640498 /
   0x4463FD18) to 0x46700000 / 0x46701000 / 0x46702000, 160 B a track (four LFOs) instead of 120. Our matrix
   reads LFO outputs at 0x44640C1C + 120 v (`csrc/matrix/matrix.c` LFO_OUT): wrong base and stride under lfo4.
4. **66abc5ad (the cascade, csrc/modulation/cascade.c)** hooks the evaluator 0x40137A06 per LFO and its DEST
   write 0x40137D7A for LFO1..3 ("each LFO modulates the other LFOs' controls"); lfo4 runs LFO4 through the same
   evaluator with its own state. **Decided (the User): include LFO4.** The cascade learns a fourth LFO: its
   shadow cells for LFO4's seven controls, LFO4 in the order (each LFO's write into the others' controls heard
   one frame late, as now), its destination lists offering LFO4's controls to LFO1..3 and theirs to LFO4.
   *How (measured from the sources, 2026-11-14):* lfo4's mask step gives LFO4's destination list the want
   `0x0200`, the staircase's next rung and MOD SETUP's own: by stock's rank rule LFO4 may already target LFO1..3's
   controls, and its write goes through the evaluator's DEST write that the cascade hooks (mod_wb), so it is
   carried one frame late like the others (to be shown in the emulator). The other way, **LFO1..3 into LFO4's
   controls**, is new engine work: LFO4's controls are not mirror slots (a DEST of 101..108 would land in the next
   voice's row), and lfo4 reads them per **track** (csrc/lfo4/bridge.c lfo4_rows) where a modulation is per
   **voice**. It needs LFO4's records offered in LFO1..3's lists (their masks), the cascade's DEST write sending
   slots 101..108 to per-voice LFO4 shadow cells of ours, and LFO4's control reads in the evaluator adding them.
5. **63d69e01 (the 13 opened destinations)**: our mask hook at the destination-list builder tells the asking
   LFO by its page's owner (0xE00 LFO2, 0x600 LFO3, 0x200 MOD SETUP). LFO4's page is a new owner: its list
   would get stock's masks unless the hook knows it.
6. **The [MOD] pages**: lfo4 extends [MOD] navigation by one page (LFO4 on the vacant page). The matrix's
   routes popup and ENV2 page do not use [MOD]; its MOD SETUP rows are read only. No byte conflict; the
   navigation needs one emulator check with both.
7. **lfowaves** touches no site of ours and no RAM of ours. Its seven waves are LFO waveforms: the cascade's
   WAVE clamp (0..6, cascade.c) and the matrix's LFO reads are unaffected by the new shapes' values, but the
   cascade's WAVE range must allow the new waves (to check).

## 5. Switching lfo4 off cleanly

lfo4 stays its own mod in the build's list (`dnfw mods apply ... --mod lfo4`). Our side reads one generation
define, `DN2_LFO4` (as `DN2_STOCK_UNITS` does), for points 2..5: off, the table, the LFO state and the masks are
stock's and the code is byte-identical to today's build (a test checks that, as for STOCK_UNITS). lfowaves can
ship without lfo4 (it is applied first; lfo4 before lfowaves is refused by the platform's order). With lfo4 off,
sounds saved with LFO4 values load and play LFO1..3 (the values sit in the wishes record unread).

## 6. The failing unit tests

On r6's tree (1.12 bench, `-m "not slow"`): `test_mods_platform.py` (in the gate's list) 13 fail,
`test_lfo4_mod.py` 4 fail and 2 error; `test_js_lfo4.py` skips (no node on gpufarm). Two causes only:

- `MAIN OS is 3,192,192 B, shorter than 3,196,288: not Digitone II 1.12` (21 of them): the tests load the 1.11
  image (`STOCK_SYX = ...OS1.11_dist.zip`) while the series' platform is 1.12, and `lfo4_code.json` /
  `lfowaves_code.json` are 1.11's (`"os": "Digitone II 1.11"`, stock_length 0x30B580). They pass once the
  fixtures name 1.12 and the two JSONs are regenerated for 1.12.
- `Regex pattern did not match` (6): the refusal messages the tests expect are 1.11's wording; same fix, then
  re-read each message.

I did not reproduce the gate's count of 7 (this run counts 13 in the gate's own file); every failure seen has
one of the two causes above, and none needs more than the port.

## 7. Effort and risks

| stage | work | estimate |
|---|---|---|
| 2a | port the sources (port_os112 over csrc/lfo4, lfo4.py, lfowaves.py, the gen scripts), regen both JSONs, the tests' fixtures to 1.12 | **done** |
| 2b | lfowaves alone on our series (no shared site): build, its own emulator checks | **done** (claude/lfowaves-112, r8) |
| 2c | `DN2_LFO4`: REC_BASE (~30 sites), matrix LFO_OUT, LOAD/SAVE: **done**, off byte-identical; the mask owner moves to 2d' | |
| 2d | LFO4's values into the wishes record (point 1): **done** (csrc/wishes/lfo4.c, host-tested) | |
| 2d' | the cascade with LFO4 (point 4), both ways: **done**. LFO4 into LFO1..3 by stock's rank and our DEST-write hook; LFO1..3 into LFO4 through per-voice LFO4 cells (cascade.c), lfo4's cascade slot (bridge.c) and three stock bounds raised with DN2_LFO4 (the destination builder's walk 101 -> 109 and its list's room, the evaluator's DEST 100 -> 108; our slot shim answers 101..108) | |
| 2e | gate steps for both mods: **done**, 6m3 lfowaves (`emu_lfowaves.py`) and 6m4 lfo4 (`emu_lfo4.py`: modulating, the cascade both ways, the lists, stock's SAVE/LOAD through the wishes record). The 35 `emu_lfo4_*.py` research harnesses stay 1.11's (not ported: the gate does not run them) | |
| 2f | lfo4's [MOD] page on a snapshot booted on a DN2_LFO4 build: `emu_lfo4.py --scenario page`, in the gate's lfo4 step. On the integrator's probe build (r7 + lfowaves + lfo4 145724fe, DN2_LFO4=1, c82ac04d) and its own snapshot (1.12-c82ac04d5a93): [MOD] walks four pages, "MOD (4/4)" is LFO4's; each of its knobs A..H moves its own LFO4 value in lfo4's table and nothing else; LFO1..3's knobs move their own slots (1, 9, 17) and leave LFO4 alone; a DEP set in lfo4's table is drawn; DEST opens LFO4's destination list (SYN rows) and, as on LFO1's page, a DEST being chosen is dropped when another knob turns. The gate's step 6m4 passes on that build (a partial run). Harness notes: a snapshot holds none of our areas (0x467..-0x47..), so they are installed from the build and lfo4's init entered by hand; only a pushed turn moves a value in the emulator | done 2026-11-14 |

Risks: (1) the lane (point 1), decided: sounds saved by upstream's 1.11 lfo4 read as "not our link" (the check
rejects them), so they load with LFO4 at its defaults on our series (the User accepted this); (2) a missed table writer (point 2) shows
only as a stock page not reflecting ours, so every writer needs an emulator check with lfo4 on; (3) the
platform area's room with all three; (4) the four-LFO stride is in stock's evaluators too (lfo4's tick build
edits "every 120 and 1920"), so any of our code that walks LFO state per voice must be found (matrix found; a
grep for 120 / 1920 near LFO code is stage 2c's first step); (5) none of this has run on hardware on 1.12.
