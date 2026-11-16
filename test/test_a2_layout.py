"""ANALOG2's knobs (2026-11-11, the User: spread next to the swarm count; the filter type, FLT2, beside CUT and RES;
osc 2's SEMI beside WAV2): drawn where analog2.LAYOUT puts them, each on its own record (display only, so old tracks
keep their values); every other machine as before."""

from __future__ import annotations

from dnfw.mnm import analog2 as A2
from dnfw.waverider import pages as P

M = next(m for m in P._mnm.CF_MACHINES if m.NAME == "ANALOG2")


def _drawn(pg: int) -> list[str]:
    names = P.mnm_pnames(M)
    return [names[j] for j in P.mnm_order(M)[8 * pg:8 * pg + 8]]


def test_pages():
    assert _drawn(0) == ["WAVE", "DTN", "MIX", "NOIS", "FLT2", "CUT", "RES", "KTR"]
    assert _drawn(1) == ["SWRM", "SDTN", "DRFT", "SYNC", "WAV2", "SEMI", "DRV", "WDTH"]
    assert _drawn(2)[:2] == ["GLID", "GLTY"]


def test_records_unchanged():
    """a control's record is the one it had before the layout (its place in mnm_pnames)"""
    names = P.mnm_pnames(M)
    rec = {sh: P.MNM_RECS[j][0] for j, sh in enumerate(names)}
    assert (rec["FLT2"], rec["SDTN"], rec["SEMI"], rec["DRV"], rec["CUT"]) == (253, 250, 246, 260, 256)
    assert A2.PNAMES2 == ("SWRM", "SEMI", "SDTN", "SYNC", "WAV2", "DRFT", "FLT2", "WDTH")
    assert rec["WDTH"] == 252                            # page 2's eighth: TYPE's, stock default 0 (WDTH off)


def test_permutation():
    for m in P._mnm.CF_MACHINES:
        order = P.mnm_order(m)
        assert sorted(order) == list(range(24))
        if not hasattr(m, "LAYOUT"):
            assert order == tuple(range(24))


def test_flt2_is_a_list():
    assert P.MNM_WIDGET[("ANALOG2", "FLT2")] == 5
    assert len(P.MNM_CHOICES["ANALOG2"]["FLT2"]) == 25
    assert P.mnm_named(P._mnm.CF_MACHINES.index(M))[253] == ("Filter 2 Type", "FLT2")
