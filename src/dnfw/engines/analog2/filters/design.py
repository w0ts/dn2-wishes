"""ANALOG 2's filters as the DN2's filter machines (docs/a2f.md): which ColdFire filter types exist,
their names, and which this build carries (dnfw.builder.parts: one part a model).

Filter types 7..11 (7 and 8 were SHFT and GRAN until v0.27; a saved sound on them loaded as
Multi-Mode since, and loads as these machines from this build on). Each machine is one model with two
filters in series (filter 1: FREQ RES MODE; filter 2: FRQ2 RES2 MOD2), an attack-decay envelope and
key tracking on both cutoffs (dnfw.ping.pages.A2F_NAMES: the page).
"""

from __future__ import annotations

MODELS = ("SVF", "LADR", "OTA", "DIOD", "MS20")         # Optimist's a2_models.h order (SVF: ANALOG 2's own)
TYPES = {7 + k: m for k, m in enumerate(MODELS)}          # ColdFire filter type -> model
NAMES = {7: ("A2 SVF", "SVF2"), 8: ("A2 Ladder", "LADR"), 9: ("A2 OTA", "OTA"),
         10: ("A2 Diode", "DIOD"), 11: ("A2 MS-20", "MS20")}   # (long, short <= 5), the FLTR list
PART = {t: f"FLT_A2{m}" for t, m in TYPES.items()}        # dnfw.builder.parts keys
MODES = ("LP12", "LP24", "BP", "HP", "NTCH")


def _built() -> tuple[int, ...]:
    from ....builder import selection
    return tuple(t for t in TYPES if selection.on(PART[t]))


BUILT_TYPES = _built()
BUILT_MODELS = tuple(TYPES[t] for t in BUILT_TYPES)
