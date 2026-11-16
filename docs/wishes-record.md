# The wishes record: a record of ours beside every sound (OS 1.12)

2026-11-11. The User's option D ("link + blob"), chosen from the study `scratch/modulation/wishes-record.md`.
Phase 1 of the modulation matrix: the record alone, with no field in it yet. The matrix's routes and its two
envelopes are its first fields (phases 2 and 3).

## Why a record of our own

A stored sound is 359 bytes, a live one 1,163, and those sizes are compiled into hundreds of places in stock's
code. So we never grow Elektron's records. A sound's extension lives in a record of ours, as large as we like,
and the sound carries only a 14-byte **link** to it, in bytes stock neither keeps nor reads.

## The three places it lives

| where | what | code |
|---|---|---|
| RAM, `0x47280000` (4,497 KB, `dnfw.waverider.pages.WISH_RAM`) | a sorted index of live-sound addresses, 8,192 entries of 512 B, a hash cache, the queue of cells for the +Drive, a carry's scratch (no limit on the sounds one block copy carries) | `csrc/wishes/table.c` |
| the stored sound's lane, ids 4..28 = bytes 36, 44, .. 84 | the link: `'W'`, link version 1; the record's 64-bit hash (two xxHash32, seeds `WISH` and `N2MX`); its length; a 16-bit check | `table.c` `wish_link_*` |
| +Drive sectors `0x6F0800` .. `0x6FEFFF` | 59,392 cells of one sector: `DN2W`, version, kind, length, the hash, the record (up to 488 B), a check | `csrc/wishes/store.c` |

Left alone in the lane: id 0 (stock's save writes slot 65 there), id 32 / byte 92 (a stock unit's sink slot 0
keeps what stock leaves there), 55/57/59, 242/243, and 354 (a runtime flag in DNX's reading).

## How a sound keeps its record

| event | stock does | the wishes record |
|---|---|---|
| copy/paste of a sound or a track, a preset into a track, kit or pattern copy | `memcpy` of the live object | every caller's `memcpy` reaches `wish_memcpy_stub` first (below): a copy of 1,163 B copies the entry; a larger block carries every tracked sound inside it to the same offset |
| a clear | `memset` | every caller's `memset` reaches `wish_memset_stub` first: every tracked sound inside the block loses its entry |
| any load (pool, kit, project, reload) | `0x400dd34e(live, stored)` | at `0x400dd3e6`, past the value loop: the link read; the record copied from another entry with the same hash, or read from its cell by the UI loop afterwards (the sound plays its stock part until then) |
| any save (unsaved-edit mirror, SAVE, kit, pool) | `0x400dd80a(stored, live)` writes the lane as zeros | at `0x400dd888`, past the value loop: an edited record is hashed again, its link written over the zeros, its cell queued |
| the UI loop (`wr_poll`) | | queued cells written 0.5 s after the last one queued, at once after stock writes a project slot (inserts' hook, `ins_wr_head`); waiting entries resolved; at most 4 sector writes a pass |

**memcpy and memset stay stock** (the User, 2026-11-11: "A: keep Overbridge stock"). Both routines are on
Overbridge's audio path, which the gate proves byte-for-byte stock (`scripts/gate_overbridge.py`, v0.41). So
the routines are not touched; every **reference** to them in MAIN OS names the wishes stub instead: 1,001 in
stock 1.12 (730 `jsr`, 11 `jmp`, 235 `lea` and 25 `move.l #` whose register is called later), less the four in
Overbridge's own code, which copy USB packet pieces (56, 84 and 32 B), 108 B records and a DSP-side block, never a
sound (`coldfire.WISH_KEEP`). 997 operands of 4 bytes. The stub tests whether there can be work, calls the C if
so, and jumps into stock's routine with the caller's stack: 3 instructions more than stock while no sound has a
record, 6 once one has (a copy smaller than a sound).

**One owner for the load site.** Waverider's machine-type bound (`moveq #6,%d2` at `0x400dd3ea`, raised to
`TYPES_LAST + 2`) lies inside the six bytes the load jump displaces. The wishes stub replays the raised bound
(`hooks.S`, `WR_LOAD_BOUND`, passed by `cpage.compile_page`), and the composer makes no other edit there.

**Content-addressed.** A copy holds the same content, so the same hash; an edit makes a new hash, so a copy
edited later never changes the other copies; identical records share one cell; a cell is never rewritten, so a
link can never name different data. A link whose cell is not on this +Drive (a preset from another unit, a power
cut before the cell was written) plays the stock part and keeps its link, so the record is found if it arrives
later.

## Every item type (2026-11-12)

The User: "we need link + blob for every type of item". A kit's or a pattern's record is the same thing as a
sound's: an entry in the same RAM table, **keyed by the live object's address**, holding TLV fields, linked from
the stored object by 14 bytes and filed on the +Drive by its hash (`csrc/wishes/item.c`, `items.S`). The API:

    u32 at = wish_item(WI_KIT, n);           /* n 0..128; WI_PATTERN n 0..127; 0 when out of range */
    wish_get(at, TAG, out, max);             /* as for a sound */
    wish_put(at, TAG, v, vlen);              /* then stock re-saves the item, and the save links it */

`WISH_KIT_PLAYING` (`0x42c5b9ac`) and `WISH_PATTERN_PLAYING` (`0x42c5b9a0`) are the live kit and pattern the
sequencer plays, written by the pattern/kit switch `0x400d93b0`.

| item | live | stored | the link (contiguous: 'W', version, h0, h1, length, check) | why it is free |
|---|---|---|---|---|
| kit | `0x4210d08c + 23,921 n`, 129 (KitActive's array) | 10,752 B | stored 10,416..10,429 | past the terminator `BACEF00C` at 10,411: the saver `0x400ddfa8` writes 0..23 and 28..10,414 and nothing after; the loader `0x400dddb6` reads nothing after |
| pattern | `0x4121998c + 122,478 n`, 128 | 89,088 B | the body of the **last unused** lock record (stored 68,148 + 258 i, + 2) | the lock saver `0x400de87c` writes only an unused record's `FF FF` header; the loader `0x400de682` skips the record whole. Slides' records (ids 200..202) are not `FF FF` and are left alone |
| song | `0x423fe67d + 3,694 n`, 17 (0 the work song, 1..16) | 3,072 B | stored 2,900..2,913 | the saver `0x400decc6` zeroes 2,900..3,071 (memset 172 B), the loader `0x400debce` never reads them |
| project | its settings, 738 B at `0x42432a61` (`WI_PROJECT`, index 0) | 1,024 B (`projectSettingsStorage_v2_t`) | stored 544..557 | the saver `0x400df6de` zeroes 542..1,023, the loader `0x400df050` never reads them |
| sound | (phase 1) | 359 B | lane ids 4..28 | above |

The stored pattern has only 2 B free after its last field (89,086..89,087), so its link lives in the lock pool.
**All 80 lock records in use:** the stock lock record with the fewest locked steps (the last on a tie) gives way to
the link in the stored pattern. It still plays until that pattern is reloaded (`docs/modulation-matrix.md`, "A
pattern's wishes record with every lock record in use"; `wish_item_nolane`, `wish_item_dropped`).

| event | the hook |
|---|---|
| kit LOAD (project, kit library, SysEx, reload) | `0x400ddf52`, after its 16 sounds and MIDI tracks: a3 live, a2 stored |
| kit SAVE (project, kit library, SysEx, KitActive's mirrors) | `0x400de0ce`, before the version word: a2 stored, a3 live |
| pattern LOAD | `0x400de85e`, after its lock pool (a branch target: the jmp replaces the whole `move.l #122474,%d0`): a2 live, d2 stored + 68,148 |
| pattern SAVE | `0x400de9b2`, after its lock pool: d2 stored, d3 live + 97,872 |
| song LOAD / SAVE | `0x400dec52` (a2 live, a3 stored) / `0x400dedb8`, after the tail's memset (a2 stored, live at 40(%sp)) |
| project settings LOAD / SAVE | `0x400df58c` (a2 live, a3 stored; a branch target, replaced whole) / `0x400df89e`, after the tail's zero loop |
| copy, clear | stock's memcpy / memset of the live kit (23,921 B) or pattern (122,478 B): phase 1's stubs carry or drop every entry inside the block, the item's own and its sounds' |

The project settings are 738 B, smaller than a sound: a memcpy of them is not carried (stock moves them only
through their saver and loader, as far as its callers were read). The song's and the settings' links travel inside
the project image, so a project copy, save-as or Transfer of `/projects/N` carries them (the blob stays on this
unit's +Drive, as for sounds).

A pattern SAVE zeroes the first 14 body bytes of every other unused lock record, so an old link never outlives a
lock that took its record. The cell's kind byte holds the item type (1 sound, 2 kit, 3 pattern, 4 song, 5 project). One table serves
every item: about 2,192 sounds, 129 kits and 128 patterns, plus the clipboards, of 8,192 entries.

The global tier stays the `DN2S` sector (one per unit, no link needed); presets travel with their sound. Not driven
yet: a project switch and the ERASE MOD DATA path end to end under the emulator for these items (the hooks' paths
are the ones every project load and save passes; ERASE erases the same cells as for sounds).

## Versioning

A record is fields: tag (u16), length (u16), value, big-endian, **tags strictly ascending** (one spelling per
content). Rules:

1. A tag number is never reused. A field grows only at its end.
2. A field this build does not know is kept byte for byte.
3. Tag bit 15, **must understand**: a record with such a field this build does not know is read-only here
   (`W_LOCKED`): carried and saved with its link unchanged, never edited.
4. Tag bit 14, **tied to the stock part**: dropped when the sound's machine changes (`wish_tlv_drop_machine`;
   no field uses it yet, so no hook calls it yet).
5. A build that does not edit a record never re-spells it: its link stays the same, and an older build loses
   nothing.
6. The cell's version and the link's version change only when their layouts do. A reader that does not know a
   link version ignores the link (plays stock).

## Crash safety

A cell is written whole, once. A cell torn by a power cut fails its check and reads as empty; it can only be the
last of its stretch (the one being added), so no other lookup stops early on it. The link reaches stock's records
through stock's own saver; the cell follows within 0.5 s. **Loss window:** a power cut between an edit's save and
its cell's write loses that one record (its sound plays stock, its link stays). Measured only on the host model
(`test/test_wishes_c.py`); the unit has not run it.

## Who may touch the table, and when

`memcpy` and `memset` run in every task and in interrupts. Every change to the index takes one lock (`tas.b`);
a call that finds it taken does nothing and counts `wish_reentered`. LFO4 measured its own counter at 0 on 1.11;
the driven session must read `wish_reentered` on 1.12. The UI loop's +Drive work holds the lock only while it
fills entries, never across a sector read or write. The audio interrupt never reads this table (the matrix
reads per-track lists the UI task builds, phase 2).

## Stock and other firmware

- **A stock unit** loads a linked sound cleanly (the lane folds onto sink slot 0, id 32 stays 0), plays its stock
  part, and a stock save zeroes the link [M code; 1.11 emulator for LFO4's lane].
- **Overtone 1.2** writes its sound-level words at the same bytes (36 .. 92, `docs/overtone-map.md` 1b). Our
  reader accepts only `'W'`, version 1 and a matching check; 20,000 random Overtone-shaped lanes gave no link
  (`test_a_lane_that_is_not_our_link_is_no_link`), and a false link would still have to name a cell on this
  +Drive. A sound of ours loaded into Overtone would read our link as Overtone words: **Overtone sounds and ours
  stay mutually exclusive**, as LFO4's were.
- **ERASE MOD DATA** erases the cells (job 6 of 9; verified at 64 sectors spread over them). Every link then
  names no cell and every sound plays stock: what "erase mod data" means.

## Known limits

- **A DAW or plugin restore** (Overbridge's plugin, the Elektron app) sends the sound's parameter values. The
  routes and envelopes are not parameters, so that restore brings back the stock part only (LFO route 1, MOD
  SETUP), whatever the hooks. Measured: Overbridge's audio path never reaches the sound loader or saver. How the
  plugin loads a preset stored on the unit goes through function pointers and was not traced statically; any
  stored sound that becomes a live one passes the loader, so its record follows.
- **Elektron Transfer to another unit** carries the link, not the record (phase 5 adds the record to our own
  `.dn2pst` files).

## Not done yet

- Reference lists and collecting cells no link names (59,392 cells; a cell is never freed, so nothing can lose a
  record; needed before the store passes about half full).
- Carrying records in `.dn2pst` presets (phase 5), a SysEx dump of cells, a web-page send.
- The machine-change hook (no field needs it yet).
- **On the unit:** the hooks' paths (pattern switch, undo, clipboard across a project LOAD), `wish_reentered`,
  the cells on a real eMMC. The emulator has no eMMC model.

## Cost (measured in the build, 2026-11-11)

- ColdFire C chunk: **+6,204 B** (171,968 -> 178,172 B of 196,608; the ERASE job included).
- MAIN OS: the loader and saver sites (6 + 8 B) and 997 references of 4 B.
- RAM: 4,604,416 B at `0x47280000..0x476E4200`, 512 KB clear of remoteui's profiler at `0x47100000..0x47200000`
  (`docs/memory-map.md`, RAM above BSS; declared in `dnfw.mods.waverider.ram()`).
- A copy while no sound has a record: **3 instructions** more than stock (`tst.l wish_n; beq; jmp`); a copy
  smaller than a sound once one has: 6. Load and save: a binary search (13 steps at 8,192) when the table holds entries.
