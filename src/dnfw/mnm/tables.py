"""The Monomachine-style machines' tables, in the order dnfw.mnm.core.Layout addresses them: signed
Q23 words (the fill's FLOAT w BY -23) that dnfw.md.core ships in zpack after the Machinedrum's.
A leaf module (dnfw.md.core reads it while dnfw.mnm.core imports dnfw.md.core).

First, with one of the Monomachine's own machines in this build (SID 6581, DPRO-WAVE, -DDRW, -DENS,
VO-6: removed 2026-11-08, back 2026-11-11), their tables from the User's Monomachine OS
(dnfw.mnm.rom.packed_words, as at 28eb110's parent); then PLAITS's and JUNO's, each built in its engine's
folder (dnfw.engines.plaits.tables, dnfw.engines.juno.tables; 2026-11-13: moved there from here).
"""

from __future__ import annotations

# our engines' tables, in their folders (2026-11-13): PLAITS's, then JUNO's
from ..engines.juno.tables import (JU_WORDS, JUNO_DRIVE, T_D, T_G1Q, T_ID8, T_K8, T_NZ4,
                                   T_PULL2, T_SUB, juno_drive, juno_values, juno_words)
from ..engines.plaits.tables import PL_TABLES, plaits_words

__all__ = ["JU_WORDS", "JUNO_DRIVE", "MNM_OS_PARTS", "MNM_OS_WORDS", "PL_TABLES", "T_D", "T_G1Q", "T_ID8", "T_K8",
           "T_NZ4", "T_PULL2", "T_SUB", "juno_drive", "juno_values", "juno_words", "mnm_os_on", "mnm_os_words",
           "plaits_words", "table_words"]

# the Monomachine's own machines' words (dnfw.mnm.rom.packed_words; dnfw.mnm.core.MNM_OS_WORDS)
MNM_OS_WORDS = 31871
MNM_OS_PARTS = ("MNM_SID", "MNM_DPRO_WAVE", "MNM_DPRO_DDRW", "MNM_DPRO_DENS", "MNM_VO6")


def mnm_os_on() -> bool:
    """Is one of the Monomachine's own machines in this build (dnfw.builder parts MNM_SID ..
    MNM_VO6)? Their tables then come first."""
    from ..builder import selection
    return any(selection.on(k) for k in MNM_OS_PARTS)


def mnm_os_words() -> tuple[int, ...]:
    """Their words as zpack carries them: the User's Monomachine OS's (dnfw.mnm.rom.packed_words),
    or, without that file (a test run outside the build), zeros in their place, so PLAITS's stay
    where dnfw.mnm.core.Layout puts them (as at 28eb110's parent, the machines then read zeros)."""
    from . import rom
    if not rom.available():
        return (0,) * MNM_OS_WORDS
    words = tuple(rom.packed_words())
    assert len(words) == MNM_OS_WORDS
    return words


def table_words() -> tuple[int, ...]:
    return (mnm_os_words() if mnm_os_on() else ()) + plaits_words() + juno_words()
