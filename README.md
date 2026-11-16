# DN2 WISHES

Custom firmware for the Elektron Digitone II, OS 1.12. Built on
[dn2mk2](https://github.com/De-Pattern/dn2mk2-firmware) by De-Pattern.

## From dn2mk2

- Digitakt II sample machines: ONESHOT, WERP, STRETCH, REPITCH, GRID, SLICE, sample browser,
  recorder, FLEX.
- PERC: the Machinedrum's TRX, EFM, GND and P-I machines.
- Monomachine machines: SID 6581, DPRO WAVE, DPRO DDRW, DPRO DENS, VO-6, polyphonic.

## Added in DN2 WISHES

- OS 1.12 support.
- Machines: JUNO, ANALOG (filters SVF, LADR, OTA, DIODE, MS-20), TB-303, PLAITS, SOPHIE, DRONE.
- Paraphonic mode on ANALOG and JUNO (VOICE page, knob B): a chord through one filter.
- Insert effects: FUZZ, TAPE, FOLD, CHOR, WIDE, HARM, FDN8, XDLY, SUB, DIST, GATER,
  RING, JUNO.
- Modulation matrix.
- Seven new LFO waveforms.
- MACHINE SEL in two columns, engine row in the preset browser, LIVE SELECT.
- List popups, units on parameter values, oscilloscope page.
- Velocity on the Machinedrum and Monomachine machines.
- Voice budget: new notes take the voice of an old one before the DSP runs out of time.
- Faster DSP code for the sample, Machinedrum and Monomachine machines, sound unchanged.

## Builds

Every build, with its status, sha256 and known issues: [CHANGELOG.md](CHANGELOG.md).
A build is released only when `scripts/ship_gate.py` prints `CLEARED TO FLASH` on that file.
No build is published yet.

## Recovery

Back to stock: send Elektron's `Digitone_II_OS1.12.syx` with Transfer. If it does not boot:
hold [FUNC] while powering on, press [TRIG 4], and send the stock OS with Transfer's
*Legacy OS upgrade mode* over a 5-pin DIN MIDI cable. See `docs/SAFETY.md`.

Not made or supported by Elektron. Flash at your own risk. Back up your +Drive first.

## Credits

- [dn2mk2](https://github.com/De-Pattern/dn2mk2-firmware) by De-Pattern, and
  [dn2_firmware_explore](https://github.com/xrcstrecords/dn2_firmware_explore) by Ángel Linares.
- Engines: [Mutable Instruments Plaits](https://github.com/pichenettes/eurorack),
  [Open303](https://github.com/charlesvestal/schwung-303),
  [Schwung Sophie](https://github.com/mestela/schwung-sophie), Optimist (DRONE, ANALOG
  filters, JUNO, SUB, DIST, GATER, RING).
- Tools: [digikit](https://github.com/m-dwyer/digikit), [selache](https://github.com/js216/selache).
  The rest in [THIRD-PARTY.md](THIRD-PARTY.md).

*Digitone*, *Digitakt*, *Machinedrum* and *Monomachine* are Elektron's trademarks.

## Licence

[GNU AGPL-3.0-or-later](LICENSE).
