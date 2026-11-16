"""Our engines in PERC's machine list (dnfw.mnm.machines, upstream's adapter and list): each with its machine
type (MACHINE SEL entry) and its builder part (docs/builder.md). BEFORE comes ahead of the Monomachine's own five
in PERC's machine index, AFTER behind them (2026-11-12: JUNO last), so every machine keeps its index."""

from __future__ import annotations

from .analog2 import analog2
from .drone import drone
from .juno import juno
from .plaits import plaits
from .sophie import sophie
from .tb303 import tb303

# (module, its machine type, its builder part); v0.45 (the User: keep upstream dn2mk2's numbers): SOPHIE 20
# (docs/sophie.md), PLAITS 18, TB303 19; 2026-11-10: DRONE 21, ANALOG2 22; 2026-11-12: JUNO 23
BEFORE = ((sophie, 20, "MNM_SOPHIE"), (plaits, 18, "MNM_PLAITS"), (tb303, 19, "MNM_TB303"),
          (drone, 21, "MNM_DRONE"), (analog2, 22, "MNM_ANALOG2"))
AFTER = ((juno, 23, "MNM_JUNO"),)
