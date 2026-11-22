"""MONOMACHINE (2026-11-11, the User: "i think one mono machine makes sense. and we should have uniformity about where
we put the sub engine knob. so that it is logical and aligned with machinedrum"): the Monomachine's five ports as one
machine on type 6, its engine on page 1 H (docs/mnm.md)."""

from __future__ import annotations

import pytest

from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc.dsl import flt
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.waverider import coldfire as CF
from dnfw.waverider import msel
from dnfw.waverider import pages as WP

pytestmark = pytest.mark.skipif(len(MM.MONO_ENGINES) != 5, reason="a build without all five engines")


def test_one_machine_on_type_6_the_others_reserved():
    assert MM.MONO_ENGINES == ("SID 6581", "DPRO-WAVE", "DPRO-DDRW", "DPRO-DENS", "VO-6")
    assert [t for t in CF.LIST_NEW if t in (6, 7, 14, 15, 16)] == [6]
    assert msel.machine_names()[6] == "MONOMACHINE" and msel.machine_icons()[6] == msel.OWNER_ICONS["SID"]   # v0.68.1: the owner's SID icon
    assert all(t in MM.RESERVED and CF.MACHINE_NAMES[t] == MM.REMOVED_NAMES for t in (7, 14, 15, 16))
    assert [MM.TYPES[MM.NAMES.index(n)] for n in MM.MONO_ENGINES] == [6] * 5
    assert PP.MNM_TYPES[6] == MM.MONO_FIRST and not {7, 14, 15, 16} & set(PP.MNM_TYPES)


def test_engn_on_page_1_h_with_its_list_and_tags_the_engine_s_controls_elsewhere():
    for e, M in zip(range(5), (MM.CF_ALL[i] for i in MM.CF_MONO_PLACES)):
        V = MM.MACHINES[MM.MONO_FIRST + e]
        names = WP.mnm_pnames(M)
        assert names[:7] == V.PNAMES[:7] and names[7] == "ENGN"           # A..G the engine's, H the engine
        assert names[15] == "TUNE" and V.PNAMES[7] == "TUNE"              # TUNE on page 2 H, not on H
        assert WP._choices(M)["ENGN"] == ("SID", "WAVE", "DDRW", "DENS", "VO-6")
        assert WP.MNM_WIDGET[WP._ck(M, "ENGN")] == 5
        tags = WP.MNM_CHOICE_TAGS[WP._ck(M, "ENGN")]
        assert len(tags) == 5 and all(0 < len(t) <= WP.TAG_MAX for t in tags)
    hdr = WP.mnm_c_header()
    assert f"#define MNM_MONO {MM.CF_MONO}" in hdr and "#define MNM_MONO_J 7 " in hdr


def test_the_dsp_reads_the_engine_the_page_shows():
    """PP.MONO_THRESHOLDS against md_page.c: knob = (v 254 + top) / (2 top), choice = (knob n) >> 7, v clamped"""
    _rid, _slot, lo, top = PM.PARAMS[MM.MONO_ENGINE_K]
    for v in range(256):
        c = min(v, top)
        page = (((c * 254 + top) // (2 * top)) * 5) >> 7
        assert sum(v >= t for t in PP.MONO_THRESHOLDS) == min(page, 4), v


def test_machine_sel_and_an_engine_change_start_the_engine():
    """each place's start is its engine's own (DEFAULTS), ENGN on that engine, TUNE on page 2 H"""
    for e, (i, n) in enumerate(zip(MM.CF_MONO_PLACES, MM.MONO_ENGINES)):
        M, d = MM.CF_ALL[i], MM.CF_ALL_DEFAULTS[i]
        words = WP.mnm_default_words(d, M)
        own = PL.mnm_slot_words(MM.NAMES.index(n), MM.DEFAULTS[n])
        for j, (_rid, slot, _lo, _top) in enumerate(WP.MNM_RECS[:16]):
            if slot in own:
                assert words[j] == own[slot], (n, j)
        assert sum((words[7] >> 8) >= t for t in PP.MONO_THRESHOLDS) == e


def test_engn_picks_the_voice_at_the_next_note():
    """the model (perc.live): a track on SID, ENGN turned to VO-6 with no note: the voice plays SID on; the next note
    is VO-6's (the voice's machine, as a new PERC TYPE's), and the level and cost are the engine's"""
    from dnfw.md import core as MDK
    from dnfw.md import voice as MDV
    from dnfw.mnm import dpro
    from dnfw.mnm import rom as MROM
    if not MROM.available():
        pytest.skip("needs the owner's Monomachine OS")
    sid, vo6 = MM.NAMES.index("SID 6581"), MM.NAMES.index("VO-6")
    h = PL.Harness()
    h.words.update(dpro.bench_words(h.L.md.mnm))
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    mach = h.L.md.state + 4 * MDK.VW["mach"]          # slot 0's machine (md.voice VW)

    def idx(k):
        return MDV.N + k                               # PERC's machine index of Monomachine voice k
    h.set_mnm_voice(sid, MM.DEFAULTS["SID 6581"])
    for b in range(3):
        h.block(trig=b == 0)
    assert h.mem.get(mach) == idx(sid)
    assert h.mem.get(h.L.C["mnm"]) == sid + 1
    h.set_mnm_voice(vo6, MM.DEFAULTS["VO-6"])
    for b in range(3):
        h.block()
    assert h.mem.get(mach) == idx(sid)                 # no note yet: SID plays on, at SID's level
    assert h.mem.get(h.L.C["mnm"]) == vo6 + 1
    assert flt(h.mem.get(h.L.C["lev"])) == pytest.approx(PP.MNM_LEVELS["SID 6581"])
    h.block(trig=True)
    h.block()
    assert h.mem.get(mach) == idx(vo6)
    assert flt(h.mem.get(h.L.C["lev"])) == pytest.approx(PP.MNM_LEVELS["VO-6"])
