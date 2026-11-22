# DN2 WISHES

## Using the mod? Go to the site: **[w0ts.github.io/dn2-wishes](https://w0ts.github.io/dn2-wishes/)**

- [About](https://w0ts.github.io/dn2-wishes/): what the mod is, its machines, effects and filters, how to go back to stock.
- [Builder](https://w0ts.github.io/dn2-wishes/builder.html): builds the firmware in your browser from your own
  Elektron files, and flashes it over USB.
- [Help](https://w0ts.github.io/dn2-wishes/help.html), [presets](https://w0ts.github.io/dn2-wishes/presets.html),
  [sample import](https://w0ts.github.io/dn2-wishes/samples.html).

The rest of this page is for developers.

## What this repository is

The source of DN2 Wishes, a custom firmware for the Elektron Digitone II (OS 1.12), built on
[dn2mk2](https://github.com/De-Pattern/dn2mk2-firmware) by De-Pattern (the upstream project). It holds the tools
that take Elektron's OS file apart, the mods (ColdFire code for the UI and the sequencer side, SHARC DSP code for
the engines and effects), the emulators that test them, and the website. Nothing of Elektron's is in it: the
builder reads their firmware from the user's own files.

## Layout

- `src/dnfw/`: the Python package (`dnfw` command): firmware container, sections, symbols, the mods and their
  DSP code generators.
- `csrc/`: the ColdFire C and assembly of the mods.
- `scripts/`: the build, the gate and its steps (`ship_gate.py`), emulator runs, the site (`make_site.sh`).
- `test/`: the unit tests (pytest).
- `tools/web/`: the website's pages (builder, sample import, help, presets; `about.md` is the About page's source).
- `presets/`: the presets the site offers.
- `docs/`: notes and findings; start with `docs/SAFETY.md`.

## Build and test

Python 3.11 or later. The build, the gate and many tests read Elektron's own OS files, which are not in this
repository: the Digitone II OS 1.12 `.syx`, the Digitakt II's DSP section (`DT2_SECTIONS` / `DT2_SECTION7`), the
Machinedrum UW OS 1.63 (`MD_OS_BIN`) and the Monomachine OS 1.32B (`MNM_OS`); without the variables they are looked
for in folders beside the checkout (`src/dnfw/*/rom.py` say where).

    python3 -m pip install -e '.[dev]'
    python3 -m pytest -m 'not slow'                    # the unit tests
    dnfw --help                                        # the firmware tool
    scripts/make_site.sh OUTDIR --preview              # the website, to look at locally

## The safety rule

A build is flashed only after `scripts/ship_gate.py` has printed `CLEARED TO FLASH` on that exact file:

    python3 scripts/ship_gate.py STOCK_OS.syx BUILD.syx      # --list prints the steps

It checks that the parts that bring a unit back (bootstrap, updater) are stock byte for byte, then boots and plays
the build in emulators of both processors (the ColdFire and the SHARC DSP), compares stock's audio bit for bit,
watches every RAM write, and refuses instructions the real chips refuse. A failing check means no flash.
`docs/SAFETY.md` lists each risk and what stops it. Elektron's own DSP code changes only where the output stays
bit-identical to stock (the `stockout` step).

## Contributing

- Report problems with a Wishes build to this repository ([github.com/w0ts/dn2-wishes](https://github.com/w0ts/dn2-wishes)),
  not to upstream or Elektron.
- Changes: a branch and a pull request. A change that adds a risk adds its gate step in the same commit.
- Nothing private in tracked files or commits: `scripts/privacy_check.py` (`docs/privacy.md`).

## Changes

- Ours: [CHANGELOG.md](CHANGELOG.md).
- Upstream's: [docs/upstream-history.md](docs/upstream-history.md) and the
  [dn2mk2 releases](https://github.com/De-Pattern/dn2mk2-firmware/releases).
- What is being built, queued and still open: [TODO.md](TODO.md).

## Licence

[GNU AGPL-3.0-or-later](LICENSE). Ported parts keep their own notices ([THIRD-PARTY.md](THIRD-PARTY.md)).
Not made, endorsed or supported by Elektron; *Digitone*, *Digitakt*, *Machinedrum* and *Monomachine* are
Elektron's trademarks.
