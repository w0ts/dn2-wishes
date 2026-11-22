# DN2 WISHES — TODO

What is being built, what is queued and what is still open. Updated 2026-11-22.
Finished work is in [CHANGELOG.md](CHANGELOG.md).

## In progress

- **FILTER 2.** A second filter on every voice, after the stock filter, on the FLTR page's third
  page (3/3).
    - DSP part and ColdFire part (the page, p-locks, modulation routes, saving): built and checked
      in the emulator; a test build is on the unit being checked. Not built yet: FILTER 2 in an
      LFO's DEST list, and trig copy/paste of its locks.
- **Bus FDN8 toward 8 at once.** The cheaper bus FDN8 (24 kHz tank, 2 diffusers; 20 to 25 % cheaper
  on the unit, 4 at once) is done, with the frame guard's cost set to what the unit measured.
  Being built: the DSP's hardware loops and long-word access to the delay lines, bit-exact, to
  fit more at once.
- **MACHINE SEL icons for the six DT2 sample machines** (ONESHOT, WERP, STRETCH, REPITCH, GRID,
  SLICE), each its own, based on the waveform: drawn (and on the About page); in the next build.
- **Dual boot.** SAFE MODE runs Elektron's stock DSP program, from a copy on the +Drive that the
  builder page sends. Stage 2 is being built.

## Open checks on the unit

- After a power-on, the remote channel's build identity read 0 and "not ready", and the highest
  DSP load since boot read 100 %. Cause not found; nothing visible went wrong.
- "!CLIP" was seen with nothing playing. Cause not found.
- Filter envelope ATK: check by ear.
- FLEX take levels: measured on the SHARC runner only, not yet on the unit.
- PLAITS MDAL: check by ear after the speed work.

## Queued

- Measure the VOICE BUDGET cost table again, with the memory-clock method.
- Update all frame-guard costs together, once the speed work is in (the FDN8s', the inserts' and
  every engine's).
- More speed work, worst case only, never by skipping work when it is quiet, ranked by gain:
    - our engines, filters and effects first, then the ColdFire's hot paths;
    - two samples at once (SIMD) in the oscillators (gain not measured yet);
    - Elektron's own DSP code, kept bit-identical;
    - the goal: 16 voices with room on every engine.
- ANALOG 2 and JUNO: proposed sound changes that would make them cheaper, with A/B recordings.
  Nothing goes into a build unless chosen by ear.
- Measurements only the unit can make: the stock filter's and AMP envelope's units, the send FX
  and master parameters.

## Open questions

- A delay echo sometimes heard where none should be ("ghost delay"). Every known cause was fixed
  and checked in the emulator; a recording of it on the unit is still needed.
