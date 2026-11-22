# Machine types: which number is whose (2026-11-18)

A sound's machine is one signed byte, `sound+0xDE` (saved as the stored sound's byte 244). Upstream (De-Pattern's
dn2mk2) adds machines upward from 18; the User's rule: never change upstream's numbers, ours adapt.

## The numbers since the v0.59 merge

| type | machine | whose |
|---|---|---|
| 0..4 | FM TONE, WAVETONE, FM DRUM, SWARMER, MIDI | Elektron |
| 5 | MACHINEDRUM (PERC) | upstream |
| 6 | MONOMACHINE (SID 6581, DPRO WAVE / DDRW / DENS, VO-6 by ENGN) | ours (upstream's SID 6581) |
| 7, 14, 15, 16 | reserved: upstream's DPRO WAVE, DDRW, DENS, VO-6 (here MONOMACHINE's engines) | |
| 8..13 | ONESHOT, WERP, STRETCH, REPITCH, GRID, SLICE | upstream |
| 17 | FLEX (BOUNCE) | upstream |
| 18, 19, 20 | FM+ STAT, FM+ PAR, FM+ DYN (v0.59) | upstream |
| 21..49 | reserved, free: upstream's next machines | |
| 50 | JUNO | ours |
| 51 | ANALOG 2 | ours |
| 52 | DRONE | ours |
| 53 | SOPHIE | ours |
| 54 | TB-303 | ours |
| 55 | PLAITS | ours |
| 56 | DRUM (2026-11-20: KICK first; docs/drum.md) | ours |

A reserved type has a row in every table (named "Removed", never listed in MACHINE SEL); the DSP sends it to the
MIDI engine's slot, so a track on one is silent.

## What moved, and old projects

| machine | v0.45 .. v0.58.x builds | up-v059, a few hours (never published) | now |
|---|---|---|---|
| PLAITS | 18 | 31 | 55 |
| TB-303 | 19 | 30 | 54 |
| SOPHIE | 20 | 29 | 53 |
| DRONE | 21 | 28 | 52 |
| ANALOG 2 | 22 | 27 | 51 |
| JUNO | 23 | 26 | 50 |

No conversion (the User, 2026-11-18). A sound saved by an earlier build loads by its number: PLAITS, TB-303 and
SOPHIE sounds as FM+ STAT, PAR and DYN; DRONE, ANALOG 2 and JUNO sounds as a reserved type (silent, page empty).
Re-pick the machine by hand. The presets we make are regenerated with the new numbers.

## The limits, measured

- **Stock.** The byte is read signed (`mvs.b`), so 127 at most. Every stock accessor that bounds it (the name
  table, the attribute rows, the stored-sound LOAD) is patched to `moveq #TYPES_LAST` (LOAD: `TYPES_LAST + 2`); a
  `moveq` holds up to 127, so TYPES_LAST can reach 125 with no new kind of patch. The other places the UI asks
  (param_set_slot_to_id, the SYN page accessors, getMachineType, the "is this parameter mine" test) go through our
  shims, which compare with a 32-bit `cmpi.l #TYPES_LAST`. The frame carries the type as a 16-bit word.
- **DSP.** The machine lookup (`LOOKUP16_DM` 0x2DEE04) has 63 words before the sample voices' state at 0x2DEF00:
  types 0..62 (asserted in `dnfw.waverider.dsp`). It holds 56 now.
- **PERC's slot loop** tells a type under 32 by one bit of a mask (as before, the same instructions), and one of
  32 and up by a range, `dnfw.perc.program.OURS_RANGE` (50..55, every one a Monomachine-style machine). A slot of
  ours takes about 6 instructions a block more than at 26..31: at most ~100 cycles of the SHARC's 666,667 a frame
  (0.015 %).
- **The preset ENGINE filter** keeps a bit a list row (22 rows), not a type.
- **Room.** Every type up to the highest has its rows. The machines chunk: 1,906 of 2,048 B (about 29 B a type).
  The pages assembly: 5,132 of 8,192 B; the reserved types share ONE place there (descriptors, labels, title,
  subtitle; `dnfw.waverider.pages.ASM_PLACES`), each a machine of its own keeps its own (without the sharing,
  13,704 B, past its room). The machines chunk is the next limit: room for about four more types.

A new machine of ours takes the next number up (57), or down (49) if upstream's numbers stay far below. DRUM took 56
(2026-11-20), after FM+ in PERC's machine index (dnfw.engines.machines LAST), so every machine keeps its index.
