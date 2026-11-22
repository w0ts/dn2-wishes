"""The sets of presets we publish (presets/<folder>/): which machines, which file prefixes. Standard library only:
scripts/presets_zip.py runs in the Pages workflow, where the project is not installed. A new machine of ours is one
row here (presets_sync.py refuses a prefix with no row)."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Set:
    folder: str                # presets/<folder>/, and the zip's name
    title: str
    types: tuple[int, ...]     # the machine types its sounds may use (docs/machine-types.md)
    prefixes: tuple[str, ...]  # the file names' first word
    what: str
    init_only: bool = False    # machines that are not ours: INIT sounds only


SETS = (
    Set("AN2", "ANALOG 2", (51,), ("AN2",), "ANALOG 2 (type 51): an INIT and sounds after Optimist's factory presets"),
    Set("DRN", "DRONE", (52,), ("DRN",), "DRONE (type 52): an INIT and sounds after Optimist's factory presets"),
    Set("JUN", "JUNO", (50,), ("JUN",),
        "JUNO (type 50): the Juno-106 voice, an INIT and sounds after Optimist's JUNO presets"),
    Set("SPH", "SOPHIE", (53,), ("SPH",),
        "SOPHIE (type 53): an INIT and drum sounds after Schwung Sophie's factory kit"),
    Set("303", "TB-303", (54,), ("303",), "TB-303 (type 54): an INIT and acid sounds after Optimist's ACID presets"),
    Set("PLT", "PLAITS", (55,), ("PLT",), "PLAITS (type 55): an INIT and sounds after Optimist's PLAITS presets"),
    Set("DRM", "DRUM", (56,), ("DRM",),
        "DRUM (type 56): KICK, SNARE, CLOSED and OPEN HAT, TOM, CLAP, RIDE and CRASH sounds (TYPE on page 1 H), "
        "named by kind (BD SD CH OH TOM CP RD CR); a name ending +DS, +FZ, +FD or +TP wants the DIST, FUZZ, FOLD or TAPE insert on its track (the project's, not the sound's)"),
    Set("MD", "MACHINEDRUM", (5,), ("MD",),
        "MACHINEDRUM (type 5, PERC): an INIT and drum sounds of the Machinedrum models"),
    Set("MNM", "MONOMACHINE", (6,), ("MNM",),
        "MONOMACHINE (type 6): an INIT and sounds of each engine (SID, WAVE, DDRW, DENS, VO-6)"),
    Set("INIT", "INIT of the other machines", (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 17, 18, 19, 20),
        ("FMT", "WVT", "FMD", "SWM", "ONE", "WRP", "STR", "RPT", "GRD", "SLC", "FLX", "FMP", "DT2"),
        "an INIT sound for each machine that is not ours: Elektron's FM TONE, WAVETONE, FM DRUM, SWARMER; "
        "upstream's ONESHOT, WERP, STRETCH, REPITCH, GRID, SLICE, FLEX and FM+ STAT / PAR / DYN", init_only=True),
)
BY_PREFIX = {p: s for s in SETS for p in s.prefixes}
BY_FOLDER = {s.folder: s for s in SETS}
