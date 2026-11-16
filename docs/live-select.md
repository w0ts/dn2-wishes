# LIVE SELECT

2026-11-12. `csrc/msel/msel.c` (the behaviour), `csrc/msel/live.c` + `live.S` (the setting's row),
`csrc/jump/jump.c` (the settings sector's flags), `test/test_live_select.py`.

The User: *"why do we need YES for the engine to load/preview, and YES again to confirm? Can we have a
preference: preview/load the engine on the arrows, confirm and exit on YES, discard and revert on NO?
(same for filters)"*.

## What the User gets

**SETTINGS > PERSONALIZE** (stock's preferences, beside SYSTEM, whose rows are only submenus) has a last
row, **LIVE SELECT**, with stock's own toggle box. YES,
LEFT/RIGHT or the knob change it. It is **on** by default: it is kept in the mod's settings sector
(`0x6FF000`, DIRECT JUMP's) as flag bit 2 = *off* (bit 1 is REMOTE CONTROL's, usb-config), so a unit without the sector, or with an older
sector, has it on.

While it is on:

- **MACHINE SEL**, both pages (machines and filters): the machine (or filter) under the cursor is put on
  the track once the cursor has rested 250 ms (30 ticks of the panel tick, 120.0 a second on the unit; it was 150 ticks, 1.25 s, until 2026-11-14:
  measured on the unit on r5, key to commit 1.32 s +-3 ms over 5 tries). Arrows and the knob both count.
  - YES commits anything still pending, then closes (stock's YES on the track's own row).
  - NO puts back the machine and the filter the track had when MACHINE SEL opened, then the whole sound
    (1,163 bytes) as it was, and closes.
- **FUNC + G filter list** (the FLTR page): the same. YES, pushing G or letting go of FUNC keeps the
  filter, and NO reverts. Another key or knob closes the list and keeps what is previewed.
- Off: stock's MACHINE SEL (YES commits, NO closes) and the list as before.

## Why NO restores the whole sound

Measured on stock 1.12 in the emulator: a machine commit (`0x40031880`, the commit stock's YES makes,
about 9,000 ColdFire instructions) resets the machine's parameter block to its defaults. That is sound
+70..+128 (28 bytes changed, among them a knob just turned). Committing the old machine back brings its
defaults, not the User's values (23 bytes still differed). So NO first puts the types back through
stock's commits (the voice gets its machine and filter as stock gives them), then copies the saved
sound over the track's sound. A filter commit (`0x40031a56`) changes only the filter type (sound +0xDF);
the filter's parameters stay (measured: MULTI-MODE → LOWPASS 4). The same save/restore covers it.

## Measured in the 1.12 emulator

The build is the integrator's regenerated series `rr-v0.48-ours-1.12` (cfbb41a0) plus these commits;
the build's own snapshot. Proof sheet: `live-select-proof.png` in the session notes.

| step | result |
|---|---|
| PERSONALIZE | LIVE SELECT is its last row, ticked (on) |
| MACHINE SEL on WAVETONE, DOWN, rest | SWARMER on the track (`sound+0xDE` 3, 10 bytes of the sound changed) |
| two more DOWN, rest | MONOMACHINE (6) |
| NO | WAVETONE (1), the sound **identical byte for byte** to the one at open (0 of 1,163 differ) |
| reopen, DOWN, rest, YES | SWARMER kept, MACHINE SEL closed |
| FLTR page, DOWN, rest | filter 1 (only +0xDF changed); NO: back, identical |
| FUNC+G list, turn, rest | filter 1; NO: back, identical |
| LIVE SELECT off (YES on the row) | sector flag 2 set; MACHINE SEL: a resting cursor commits nothing (stock) |
| faults | none |

## Not verified

- On the unit: the audio during a switch. Each preview switches the voice exactly as a stock YES does,
  just more often. **Unit check, logged for later:** play a held note and a running pattern while
  scrolling MACHINE SEL with LIVE SELECT on; listen for clicks or dropouts at each switch, and after NO.
- A voice already sounding when NO restores the sound keeps what it had until its next note (the
  sound's values reach a voice at its note-on, `0x4002549c`).
