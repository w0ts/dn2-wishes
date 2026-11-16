# Third-party notices

`dn_firmware` is licensed under the [GNU AGPL-3.0-or-later](LICENSE). Parts of
it are derived from the projects below. Most are MIT-licensed, which permits their
incorporation into an AGPL work provided their copyright and permission notices
travel with it; digihealth is GPL-2.0-or-later, used under GPL-3.0. Those notices are reproduced here.

What was taken from each is set out in `docs/references.md`, and every module
that ports from one names its source — and, more usefully, names where it
diverges and why.

None of these projects is affiliated with Elektron, and neither is this one.

---

## elektron-firmware-tool

<https://github.com/mischa85/elektron-firmware-tool> — Marcel Bierling.

The reference for the SysEx transport, the ELE3 container, the aPLib codec and
the integrity algorithms. Ported into `src/dnfw/syx/`, `src/dnfw/codec/`,
`src/dnfw/container/`, `src/dnfw/integrity/` and `src/dnfw/firmware/build.py`.

> Copyright (c) 2026 Marcel Bierling

## octa-bt-pt

<https://github.com/bryantysinger/octa-bt-pt> — Bryan Tysinger.

The declarative patch model — patch records carrying the bytes they expect, a
guard that refuses the wrong image, and discovery over `patches/*.py`. Adapted
into `src/dnfw/patch/`.

> Copyright (c) 2026 Bryan Tysinger

## octabam

<https://github.com/sambanks/octabam> — Sam Banks.

The ColdFire V4e disassembly findings that `src/dnfw/cli/disasm.py` and
`docs/mainos-image.md` rest on, including the measurement that radare2's m68k
backend misreads this CPU silently. Its code-cave model is the intended
mechanism for Phase 2. No code has been ported yet; the debt here is to its
measurements and its method.

> Copyright (c) 2026 Sam Banks

## midisc

<https://github.com/bkkbrls-del/midisc> — Sam Banks.

The ColdFire `Asm` encoder (`tools/ot3_asm.py`) and the cave helpers
(`tools/midisc/util.py`) — every instruction encoding checked against a stock
instruction, `.w` branch displacements resolved rather than hand-typed. Ported
into `src/dnfw/patch/coldfire.py` and `src/dnfw/patch/cave.py`. Only the
CPU-level encoding transfers; nothing about the Octatrack's engine or memory
map is carried over.

> Copyright (c) 2026 Sam Banks

## octamax

<https://github.com/mxldyn/octamax> — Maxolydian.

midisc's upstream, credited in midisc's own notice. No code is ported from it
directly; its Octatrack architecture account is used only as a hypothesis to
test against the DN2, never as fact about it.

> Copyright (c) 2025-2026 Maxolydian

---

## Schwung Sophie

<https://github.com/mestela/schwung-sophie> — Matt Estela and digisophie contributors.

The SOPHIE machine's synthesis (`src/dsp/sophie.c`'s voice: carrier, modulators, envelopes,
feedback, noise, the models and the crusher), ported to the DSL in `src/dnfw/engines/sophie/sophie.py`
(`docs/sophie.md` says what was left out).

> Copyright (c) 2026 Matt Estela
> Copyright (c) 2026 digisophie contributors

## Schwung 303 (GPL-3.0-only) and Open303 (MIT)

<https://github.com/charlesvestal/schwung-303> -- Charles Vestal and contributors; its engine
Open303 by Robin Schmidt (`src/dsp/open303/`, MIT), with jc303's Devilfish extensions.

The TB303 machine's voice: Open303's getSample (the oscillator's two shapes, the TB-303 ladder,
the envelopes, the filters, the 4x oversampling and the elliptic decimation filter) and its note
handling, as Schwung 303's plugin.cpp configures it with the Devilfish modifications off and no
drive, ported to the DSL in `src/dnfw/engines/tb303/tb303.py` (`docs/tb303.md` says what changed).
Schwung 303 is GPL-3.0-only; dn2mk2 is AGPL-3.0, which GPL-3.0 section 13 allows combining.

> schwung-303 -- TB-303 emulator for Schwung. Copyright (C) 2026 Charles Vestal and contributors.
> Copyright (C) midilab / jc303 contributors (Devilfish extensions to Open303).
> This program is free software: you can redistribute it and/or modify it under the terms of the
> GNU General Public License as published by the Free Software Foundation, version 3 of the
> License.
>
> Open303: Copyright (c) 2009 Robin Schmidt (www.rs-met.com). Permission is hereby granted, free
> of charge, to any person obtaining a copy of this software and associated documentation files
> (the "Software"), to deal in the Software without restriction, including without limitation
> the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
> the Software, and to permit persons to whom the Software is furnished to do so, subject to the
> following conditions: The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT
> WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

## Mutable Instruments Plaits (MIT)

<https://github.com/pichenettes/eurorack> (`plaits/`, and `stmlib/` from
<https://github.com/pichenettes/stmlib>) -- Emilie Gillet.

The PLAITS machine's two engines, WAVESHAPING and GRANULAR FORMANT
(`plaits/dsp/engine/waveshaping_engine.cc`, `grain_engine.cc`, `dsp/oscillator/oscillator.h`,
`grainlet_oscillator.h`; stmlib's poly-BLEP, parameter interpolator, one-pole filter), ported to
the DSL in `src/dnfw/engines/plaits/plaits.py` (`docs/plaits.md` says what was left out); its tables are
rebuilt from `plaits/resources/lookup_tables.py`'s formulas.

2026-11-09: eleven more of its engines, each in `src/dnfw/engines/plaits/plaits_<name>.py` (`plk.py` their
common ground): VIRTUAL ANALOG, FM, ADDITIVE, SWARM, NOISE, PARTICLE, STRING, MODAL, BASS DRUM,
SNARE DRUM, HI-HAT (`plaits/dsp/engine/*_engine.cc` and the oscillators, noise sources, drums,
physical models, diffuser and downsampler they use; stmlib's Random, SVF, polyblep, delay line).
FM's frequency quantizer is rebuilt from `lookup_tables.py`'s formula.

> Copyright 2016 Emilie Gillet.
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software
> and associated documentation files (the "Software"), to deal in the Software without
> restriction, including without limitation the rights to use, copy, modify, merge, publish,
> distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
> Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or
> substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
> BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
> NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
> DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Optimist (GPL-3.0-only): DRONE, ANALOG 2's filters, JUNO, inserts SUB DIST GATER RING

The User's own synth firmware (`~/GitHub/optimist`, GPL-3.0-only), ported to the DSL (float32 at
44.1 kHz; what changed is in each module's docstring). GPL-3.0-only code combined with this
AGPL-3.0 work, as GPL-3.0 section 13 allows; each module keeps its SPDX line and this credit.

- **DRONE** (`src/dnfw/engines/drone/drone.py`): firmware/src/engines/drone/eng_drone.c, drone_mem.h and
  voice.c's glide; the network after Caravel 0.3.3's DRONE by bonszaimusic
  (<https://github.com/bonszaimusic/caravel>, firmware/src/eng_drone.c, GPL-3.0-only).
- **ANALOG 2's filters** (`src/dnfw/engines/analog2/filters/`): firmware/src/engines/analog/a2_models.c and the SVF of
  eng_analog2.c (eng_analog.c: Copyright (C) 2026 Leo Kuroshita (@kurogedelic), Hügelton Instruments).
- **JUNO** (`src/dnfw/engines/juno/juno.py`, its tables `src/dnfw/engines/juno/juno_data.py`): firmware/src/engines/juno/
  (eng_juno.c, juno_dsp.h, juno_tables.h), itself fm-106 by PatttF (<https://github.com/PatttF/fm-106> at
  `be74757`, GPL-3.0-only), a fixed-point port of Ultramaster KR-106 by Kayrock Screenprinting
  (<https://github.com/kayrockscreenprinting/ultramaster_kr106>, GPL-3.0; its commits are Karl LaRocca's). Neither
  project puts a copyright line in its files: the copyright is their authors'. The tables are KR-106's
  measurements and models (one Juno-106 voice card's cutoff at 93 DAC codes, the resonance's tables, the sub and
  noise levels). A model of the Roland Juno-106; not affiliated with or endorsed by Roland. Roland's factory
  patches are not included.
- **Inserts SUB, DIST, GATER, RING** (`src/dnfw/inserts/`): firmware/src/fx/insfx/insfx.c (ifx_mod),
  firmware/src/fx/fx.c (dist_gains, dist_run), firmware/src/fx/insfx/gater.c (its patterns).

## digihealth (GPL-2.0-or-later)

<https://github.com/irpina/digihealth> -- irpina.

The USB SysEx probe's design: the read-only HELLO / STATS / PEEK protocol, the
8-in-7 packing, the SysEx-router hook, the render timing and the Windows MIDI
port. Adapted for the Digitone II 1.11 in `csrc/usbprobe/`,
`src/dnfw/mods/usbprobe.py`, `scripts/{build,gen,emu}_usbprobe*.py`,
`tools/dn2probe.py`, `tools/winmidi.py` and the live view (`tools/dn2live*`,
`tools/dn2poll.py`, `tools/dn2port.py`, `tools/dn2stats.py`, `tools/dn2log.py`).
Every DN2 address was found again on DN2 1.11 (`docs/usbprobe.md`); none is
digihealth's. Each derived file names this origin in its header.

digihealth is licensed GPL-2.0-or-later (irpina/digihealth `72f0183`). It is used
here under GPL-3.0, which section 13 of the AGPL-3.0 allows to be combined with
this project. Those parts remain under the GPL-3.0's terms.

> Copyright (C) 2026 irpina and contributors

## selache's selas (GPL-3.0), a tool the builder page serves

<https://github.com/js216/selache> -- Jakob Kastelic. Its SHARC+ assembler, selas, assembles our
SHARC sources (`scripts/gen_waverider_sharc.py`); it is a tool, and nothing of it is copied into
the firmware (an assembler's output is not a work derived from the assembler). The modular
builder's page (`docs/builder.md`) runs it in the browser as `selas.wasm`: selache at commit
2b26d3b75c53063575bc5c820fa0d38879335187, unmodified, compiled to WebAssembly through the small
wrapper in `tools/selas-wasm/` (GPL-3.0, like selas). The page serves that wrapper's source beside
`selas.wasm` (`selas-wasm-source.zip`) and links selache's source at that commit, as GPL-3.0
section 6 asks of whoever conveys the binary.

> selache. Copyright (c) 2026 Jakob Kastelic. Licensed under the GNU General Public License,
> version 3.

## The MIT License

They all carry the same terms:

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## Not third-party, and not bundled

**Elektron firmware.** This repository contains none, and never will. `dnfw`
operates on an OS file you obtain yourself from Elektron. No key is stored
here either: the Digitone II signing key is recomputed at run time from
material inside the image you supply, and accepted only when it reproduces that
image's own digest.

**DNX**, the sibling project this one depends on for Digitone data formats,
shares no code with it. It is referenced, not incorporated.

**ems-octakit** (<https://github.com/emuyia/ems-octakit>) ships **no licence**,
so none of its code is used. It was read only for architecture — the idea of
assembling real `.S` with the GNU toolchain into linker-placed caves — and that
general technique, not its expression, informs `src/dnfw/patch/assemble.py`.
