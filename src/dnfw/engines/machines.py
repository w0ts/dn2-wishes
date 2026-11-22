"""Our engines in PERC's machine list (dnfw.mnm.machines, upstream's adapter and list): each with its machine
type (MACHINE SEL entry) and its builder part (docs/builder.md). BEFORE comes ahead of the Monomachine's own five
in PERC's machine index, AFTER behind them (2026-11-12: JUNO last), so every machine keeps its index."""

from __future__ import annotations

from .analog2 import analog2
from .drum import drum
from .drone import drone
from .juno import juno
from .plaits import plaits
from .sophie import sophie
from .tb303 import tb303

# (module, its machine type, its builder part).
# 2026-11-18 (upstream v0.59 took 18, 19, 20 for FM+ STAT, PAR, DYN; the User: never change upstream's machine ids,
# ours move to a block far from where upstream adds machines; the User, the same day: 50..55): JUNO 50, ANALOG2 51,
# DRONE 52, SOPHIE 53, TB303 54, PLAITS 55; 21..49 are upstream's to come (reserved here). PERC's slot loop tells
# ours by a range (dnfw.perc.program OURS_RANGE), the preset ENGINE filter by its rows, so nothing limits them to
# 32 (docs/machine-types.md). No conversion: a sound saved by an earlier build on 18..23 loads as what upstream has
# there (18..20 FM+, 21..23 nothing: silent, "Removed").
# Before (v0.45 .. v0.58.x): SOPHIE 20, PLAITS 18, TB303 19; DRONE 21, ANALOG2 22 (2026-11-10); JUNO 23 (2026-11-12);
# 26..31 on the up-v059 branch for a few hours of 2026-11-18 (never in a published build)
TOP = 56
BEFORE = ((sophie, 53, "MNM_SOPHIE"), (plaits, 55, "MNM_PLAITS"), (tb303, 54, "MNM_TB303"),
          (drone, 52, "MNM_DRONE"), (analog2, 51, "MNM_ANALOG2"))
AFTER = ((juno, 50, "MNM_JUNO"),)
# 2026-11-20: DRUM (56, the next of ours) after FM+ (dnfw.mnm.machines), so every machine already here keeps its index
LAST = ((drum, 56, "MNM_DRUM"),)
# the numbers our builds used before 2026-11-18 (docs/machine-types.md; nothing reads them)
MOVED = {"PLAITS": (18, 55), "TB303": (19, 54), "SOPHIE": (20, 53), "DRONE": (21, 52), "ANALOG2": (22, 51),
         "JUNO": (23, 50)}


def type_of(name: str) -> int:
    """our engine NAME's machine type (PLAITS, TB303, SOPHIE, DRONE, ANALOG2, JUNO)"""
    for M, t, _p in BEFORE + AFTER + LAST:
        if M.NAME == name:
            return t
    raise KeyError(name)
