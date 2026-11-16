# Wishes

**An unofficial Digitone II mod builder.** Pick which machines and effects go into your mod, then
build the firmware file in your browser from your own Elektron OS files.

**Open it:** https://&lt;user&gt;.github.io/dn2-wishes/builder.html (not published yet)

> **Status (DN2wishes v0.56.1):** only [help.html](help.html) and its style (wishes.css) are in this build. The
> builder page (builder.html, its worker, selas.wasm and the Python build behind it) is being moved onto upstream
> v0.56 separately; this README describes it as it will be.

> **Unofficial.** Wishes is not made, endorsed or supported by Elektron. It is a fork of
> [De-Pattern's dn2mk2](https://github.com/De-Pattern/dn2mk2) (firmware source:
> [dn2mk2-firmware](https://github.com/De-Pattern/dn2mk2-firmware)) with extra machines and effects
> that are not in upstream's releases. For upstream's own cleared builds, use
> [the dn2mk2 patcher](https://de-pattern.github.io/dn2mk2/patcher.html) and
> [their release notes](https://github.com/De-Pattern/dn2mk2-firmware/blob/builds/README.md).
> Report problems with a Wishes build here, not upstream.

## What it does

- **Your own files only.** The page reads your Digitone II OS 1.12 file, the Digitakt II OS 1.16 or
  1.17 file and the Machinedrum UW OS 1.63 file (free downloads from Elektron's support pages),
  and, only for the Monomachine machines, the Monomachine SFX-6/60 OS 1.32B file, in your browser.
  Nothing of Elektron's is in this repository, and nothing is uploaded.
- **Pick the parts.** SOPHIE, PLAITS, TB-303; the Monomachine's SID 6581, DPRO WAVE, DDRW, DENS
  and VO-6 (off in Full: they fit when PLAITS is left out); the FDN8 reverb and the XDLY delay; the
  per-track inserts FUZZ, TAPE, FOLD and HARM. Three bars show the room each choice leaves: DSP
  upload, USB image, and an estimate of DSP time.
- **The same build everywhere.** The page runs the project's Python build (Pyodide) and its SHARC
  assembler (selas, compiled to WebAssembly); the command line runs the same code
  (`scripts/dn2build.py` in the firmware source).

## TESTED, EMULATOR-CHECKED and UNTESTED

- **TESTED**: this exact file (its sha256) has run on a Digitone II, confirmed by hand.
- **EMULATOR-CHECKED**: this exact file passed the project's full emulator gate with no failure
  beyond the clean control build's on the same bench (some steps, boot from reset among them, fail
  for every OS 1.12 build there today). Not proven on hardware; not cleared by upstream.
- **UNTESTED**: any other mix. It passed the page's own checks (both size limits, Elektron's
  sections untouched, integrity and signature) but no gate ran on it.

Only TESTED saves without a confirmation. Whatever the level, back up the +Drive and your projects
first.

A machine left out keeps its machine type reserved: a project with a track on it still loads, the
track is silent and its name shows *Removed*. Leaving the mod: send Elektron's stock OS 1.12 file the
same way.

## Versions

Each Wishes version is a git tag `wishes-vX.Y` with a GitHub release (its browser bundle as assets).
The page lists the versions and builds the one you pick; TESTED presets are per version.
The repository's WISHES.md says how releases are made.

## How to reach the new functions

[help.html](help.html): the key combinations, one card per function.

## Licences

AGPL-3.0-or-later, as dn2mk2 ([LICENSE](LICENSE)). Ported parts keep their notices
([THIRD-PARTY.md](THIRD-PARTY.md)): Mutable Instruments Plaits and Open303 (MIT), Schwung Sophie,
Schwung 303 (GPL-3.0-only), digihealth (GPL-2.0-or-later). The page's assembler is selache's selas
(GPL-3.0, [js216/selache](https://github.com/js216/selache) at 2b26d3b), unmodified; its wrapper's
source is `selas-wasm-source.zip`. Not affiliated with Elektron.
