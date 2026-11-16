"""DRONE's OCT (2026-11-11, the User: "drone: we need an octave knob"): page 2's third place (q2, the EQF
record, 0..100), -3..+3 octaves as trunc(7 q2) - 3 on the DSP (dnfw.mnm.drone._target), seven named
choices on the ColdFire (md_page.c: page 2 computes the choice as the DSP does). A project saved before
OCT existed holds the record's start (DEFAULTS2's 0.5) and must play at octave 0."""

from __future__ import annotations

from dnfw.mnm import drone as D
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.waverider import pages as WP

J = 8 + 2                                        # the control: page 2, third place


def _rec():
    return WP.MNM_RECS[J]                        # (rid, slot, lo, top)


def _dsp_octave(v: int) -> int:
    """the DSP's octave for the record value V (dnfw.mnm.drone._target on q2 = v / top)"""
    _rid, _slot, lo, top = _rec()
    q = min(max(v - lo, 0), top) / top
    return min(int(7.0 * q), 6) - 3


def _cf_choice(v: int) -> int:
    """md_page.c mnm_page_draw on page 2: k = ((v n / top) 128 + 64) / n, then (k n) >> 7"""
    _rid, _slot, lo, top = _rec()
    n = 7
    v = min(max(v - lo, 0), top)
    k = min(((v * n) // top * 128 + 64) // n, 127)
    return (k * n) >> 7


def test_oct_is_page_2s_third_place_on_the_eqf_record():
    assert D.PNAMES2[2] == "OCT"
    assert _rec()[0] == 250 and _rec()[2:] == (0, 100)
    M = MM.CF_MACHINES[[m.NAME for m in MM.CF_MACHINES].index("DRONE")]
    assert WP.mnm_pnames(M)[J] == "OCT"


def test_oct_reads_in_octaves_within_the_cell():
    names = WP.MNM_CHOICES["DRONE"]["OCT"]
    assert names == ("-3oc", "-2oc", "-1oc", "0oct", "+1oc", "+2oc", "+3oc")
    assert all(len(n) <= 4 for n in names)       # mnm_choice_names[..][5]
    assert WP.MNM_WIDGET[("DRONE", "OCT")] == 5


def test_an_old_project_plays_at_octave_0():
    _rid, _slot, lo, top = _rec()
    assert D.DEFAULTS2[2] == 0.5
    word = PL.knob_word(int(round(D.DEFAULTS2[2] * 127)), top, lo)   # what MACHINE SEL wrote (mnm_default)
    assert _dsp_octave(word >> 8) == 0
    assert _dsp_octave(50) == 0                  # the record's own start (0x3200)


def test_the_page_shows_the_octave_the_dsp_plays():
    for v in range(0, 101):
        assert _cf_choice(v) - 3 == _dsp_octave(v), v
    assert {_dsp_octave(v) for v in range(101)} == set(range(-3, 4))
