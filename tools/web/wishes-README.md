# Wishes

**An unofficial Digitone II mod, built in your browser** from your own Elektron OS files.

> **Unofficial.** Wishes is not made, endorsed or supported by Elektron. It is a fork of
> [De-Pattern's dn2mk2](https://github.com/De-Pattern/dn2mk2) (firmware source:
> [dn2mk2-firmware](https://github.com/De-Pattern/dn2mk2-firmware)) with extra machines and effects
> that are not in upstream's releases. For upstream's own cleared builds, use
> [the dn2mk2 patcher](https://de-pattern.github.io/dn2mk2/patcher.html) and
> [their release notes](https://github.com/De-Pattern/dn2mk2-firmware/blob/builds/README.md).
> Report problems with a Wishes build here, not upstream.

## What it does

- **One build per release, the whole mod.** There is nothing to choose: every machine and effect
  of the release is in it, and it fits.
- **Your own files only.** The page reads your Digitone II OS 1.12 file, the Digitakt II OS 1.16 or
  1.17 file, the Machinedrum UW OS 1.63 file and the Monomachine SFX-6/60 OS 1.32B file (free
  downloads from Elektron's support pages), in your browser. Nothing of Elektron's is in this
  repository, and nothing is uploaded.
- **Only the cleared file can be saved.** The page runs the project's Python build (Pyodide) and
  offers Save only when the result is byte for byte the file the project's gate cleared for that
  release. Anything else: "do not flash".
- **Flashing:** back up the +Drive and your projects with Elektron Transfer, send the saved .syx
  with Transfer, switch the Digitone II off and on once. Back to stock: send Elektron's own
  Digitone II OS 1.12 file the same way (ERASE MOD DATA first removes what the mod stored).

## How to reach the new functions

[help.html](help.html): the key combinations, one card per function.

## Licences

AGPL-3.0-or-later, as dn2mk2 ([LICENSE](LICENSE)). Ported parts keep their notices
([THIRD-PARTY.md](THIRD-PARTY.md)). Not affiliated with Elektron.
