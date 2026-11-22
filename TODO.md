# DN2 WISHES — TODO

What is being built, what is queued and what is still open. Updated 2026-11-22.
Finished work is in [CHANGELOG.md](CHANGELOG.md).

## In progress

- **FILTER 2.** A second filter on every voice, after the stock filter, on the FLTR page's third
  page (3/3).
    - DSP part: done, and proven bit-exact against its model.
    - ColdFire part (the page, the parameters, saving): being built.
- **A cheaper bus FDN8 reverb.** The tank runs at 24 kHz, with 2 diffusers.
    - Measured on the unit: 20 to 25 % cheaper; 4 bus FDN8s run at once.
    - Being built: the frame guard's cost for it, to match the new cost.
    - Then: the DSP's hardware loops and long-word access to the delay lines, aiming for 8 at once.
      The result must stay bit-exact.
- **Dual boot.** SAFE MODE runs Elektron's stock DSP program, from a copy on the +Drive that the
  builder page sends. Stage 2 is being built.

## Open checks on the unit

- v0.69.2: a second power-on after the first one makes no new copies on the +Drive.
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
