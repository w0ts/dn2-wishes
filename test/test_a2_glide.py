"""ANALOG 2's page 3: GLID, GLTY, DRONE's mono legato glide (dnfw.engines.analog2.a2glide, 2026-11-11).

The records: page 3 sits on WaveTone records no machine of ours used; GLTY's (TYPE) stock default 0 is OFF, so a
track saved before plays as before. The ColdFire's choice is the DSP's. The glide, played through the DSP program's
model (dnfw.perc.live): off, the oscillators' pitch is the note every block; legato with RATE or TIME it moves
between the notes; a separate note (a note-off between) jumps; GLID 0 jumps.
"""

import pytest

from dnfw.engines.analog2 import a2glide as G, analog2 as A2
from dnfw.mnm import core as MC, machines as MM
from dnfw.perc import live as PL, machines as PM, program as PP
from dnfw.waverider import pages as WP

TYP = {MM.NAMES[k]: t for t, k in PP.MNM_TYPES.items()}
# the stock records (1.11 and 1.12 parameter tables, measured 2026-11-11): id -> (slot, low, high, default)
STOCK = {245: (36, 0, 0x7F00, 0x6400), 259: (46, 0, 0x200, 0), 255: (42, 0, 0x7F00, 0x7F00),
         261: (48, 0, 0x7F00, 0x4000), 262: (49, 0, 0x7F00, 0x4000), 248: (37, 0, 0x300, 0),
         249: (39, 0, 0x200, 0x100), 247: (27, 0, 0x100, 0)}


def test_page3_records_are_free_wavetone_records_with_their_stock_ranges():
    used = {r for r, *_ in PM.PARAMS + PM.FX_PARAMS} | {PM.TYPE_REC[0]}
    assert len(PM.P3_RECS) == 8 and len({r for r, *_ in PM.P3_RECS}) == 8
    for rid, slot, lo, top in PM.P3_RECS:
        assert rid not in used and 238 <= rid <= 262
        s, low, high, _d = STOCK[rid]
        assert (slot, lo, top) == (s, low >> 8, high >> 8)


def test_an_old_track_has_its_glide_off():
    """GLTY is TYPE (259): its stock default 0 is OFF; the DSP's choice of a word 0 is OFF"""
    rid, slot, lo, top = PM.P3_RECS[G.GLTY]
    assert (rid, STOCK[rid][3]) == (259, 0)
    assert WP.MNM_CHOICES["ANALOG2"]["GLTY"][0] == "OFF"


@pytest.mark.parametrize("v", [0, 1, 2])
def test_the_page_shows_the_dsp_choice(v):
    """md_page.c (j >= 8): k = (((v n) / top) 128 + 64) / n, choice (k n) >> 7; the DSP: min(n - 1, trunc(q n))"""
    _rid, _slot, lo, top = PM.P3_RECS[G.GLTY]
    n = len(WP.MNM_CHOICES["ANALOG2"]["GLTY"])
    k = min(127, (((v * n) // top) * 128 + 64) // n)
    assert (k * n) >> 7 == min(n - 1, int((v / top) * n))


def test_three_pages_for_analog2_only():
    for M in MM.CF_ALL:                         # 2026-11-11: MONOMACHINE's places: two (its engine's TUNE on page 2 H)
        # JUNO: two (its page 2, ENV ATK DEC SUS REL PWM RNGE: dnfw.engines.juno.juno PNAMES2, engfolders1 2026-11-16)
        want = 3 if M.NAME == "ANALOG2" else 2 if M.NAME in ("DRONE", "JUNO", "DRUM") or hasattr(M, "HOST") else 1   # DRUM: 2026-11-20
        assert WP.mnm_pages(M) == want, M.NAME
    hdr = WP.mnm_c_header()
    assert "#define MNM_J 24" in hdr
    ai = [M.NAME for M in MM.CF_MACHINES].index("ANALOG2")
    names = WP.mnm_pnames(MM.CF_MACHINES[ai])
    assert len(names) == 24 and names[16:18] == ("GLID", "GLTY") and set(names[18:]) == {"---"}


def test_machine_sel_starts_it_off_with_glid_at_slide_t():
    words = {M.NAME: WP.mnm_default_words(d, M) for d, M in zip(MM.CF_DEFAULTS, MM.CF_MACHINES)}
    a2 = words["ANALOG2"]
    assert len(a2) == 24 and a2[16] == PL.knob_word(54, 127, 0) and a2[17] == 0
    for name, w in words.items():
        if name != "ANALOG2":
            assert w[16:] == [0xFFFF] * 8, name


def _harness(glid: int, glty: int) -> PL.Harness:
    h = PL.Harness()
    h.set_mnm(TYP["ANALOG2"], [0, 0, 0, 0, 127, 0, 0, 64])
    for k, v in ((G.GLID, glid), (G.GLTY, glty)):
        _rid, slot, lo, top = PM.P3_RECS[k]
        h._half(PM.frame_offset(slot), (lo + v) << 8)
    return h


def _cur(h: PL.Harness) -> float:
    a = h.L.md.state + 1024 * h.t + 4 * (MC.K.S0 + A2.GW.CUR)
    return PL.flt(h.mem.get(a))


def _play(glid: int, glty: int, off_at=None, n=40, second=10) -> list[float]:
    """note 72 at block 0, the trig of note 84 at block `second`; a note-off at block `off_at`; CUR each block.
    On the DN2 a trig's pitch reaches the voice one call after it (a2glide.trig): so here too, the note changes the
    block after its trig (the harness itself writes the note cells straight)"""
    h, cur = _harness(glid, glty), []
    for b in range(n):
        h.mem.put(G.NOTE_OFF_WORD, (1 << h.t) if b == off_at else 0)
        h.block(note=72.0 if b <= second else 84.0, trig=b in (0, second))
        cur.append(_cur(h))
    return cur


def _between(cur):
    return [c for c in cur if 72.0 < c < 84.0]


def test_glide_off_is_the_note_every_block():
    for glid, glty in ((30, 0), (0, 2), (0, 0)):
        cur = _play(glid, glty)
        assert not _between(cur) and cur[-1] == 84.0, (glid, glty)


@pytest.mark.parametrize("glty", [1, 2])
def test_a_held_note_glides(glty):
    cur = _play(30, glty)
    mid = _between(cur)
    assert len(mid) >= 3 and cur[-1] == 84.0
    assert mid == sorted(mid)                    # upwards, step by step


@pytest.mark.parametrize("glty", [1, 2])
def test_a_separate_note_jumps(glty):
    assert not _between(_play(30, glty, off_at=5))


def test_time_takes_glids_time():
    """TIME: GLID knob k is 10^(4 k / 127) ms whatever the interval; at knob 30 (8.8 ms) the 12 semitones take
    about 8.8 ms of 32-sample blocks at 44.1 kHz (Optimist's ticks): 12 blocks, give or take one"""
    mid = _between(_play(30, 2))
    assert 10 <= len(mid) <= 13


# -- 2026-11-11, the User: "drone glide should go to minutes" (top 5 minutes), DRONE and ANALOG 2 alike --------------

def test_glid_curve_is_optimists_up_to_a_second_then_reaches_five_minutes():
    for v in range(0, 96):                       # q <= 0.75: 10^(4 q) ms, as before
        assert G.ms_of(v / 127) == pytest.approx(10.0 ** (4.0 * v / 127) if v else 0.0)
    assert G.ms_of(0.75) == pytest.approx(1000.0) and G.ms_of(1.0) == pytest.approx(300_000.0)
    ms = [G.ms_of(v / 127) for v in range(1, 128)]
    assert all(b > a for a, b in zip(ms, ms[1:]))
    assert max(b / a for a, b in zip(ms, ms[1:])) < 1.22   # at most ~22 % a knob step


def test_the_readout_reads_every_knob_exactly():
    from dnfw.engines import units as MU
    for top in MU.GLID_TOPS:
        t = MU.glid_table(top)
        assert len(t) == 128 and t[-1] == 10000 + 3000   # 5 minutes, in tenths of a second
        assert all(b >= a for a, b in zip(t, t[1:]))


def _gst_after_trig(glid_v: int, glty: int, interval: float = 12.0) -> float:
    h = _harness(0, glty)
    _rid, slot, lo, top = PM.P3_RECS[G.GLID]
    h._half(PM.frame_offset(slot), glid_v << 8)
    for b in range(4):
        h.block(note=60.0 if b <= 2 else 60.0 + interval, trig=b in (0, 2))
    a = h.L.md.state + 1024 * h.t + 4 * (MC.K.S0 + A2.GW.GST)
    return PL.flt(h.mem.get(a))


@pytest.mark.parametrize("v", [110, 120, 127])
def test_a_long_time_glide_steps_to_take_its_time(v):
    """TIME: an octave in GLID's time (32-sample blocks at 44.1 kHz); before, a step under 1/4096 semitone was
    raised to one, capping an octave at ~36 s"""
    ms = G.ms_of(v / 127)
    want = 12.0 / (ms * 44.1 / 32.0)
    assert _gst_after_trig(v, G.TIME) == pytest.approx(want, rel=0.03)


def test_a_long_rate_glide_steps_an_octave_in_its_time():
    ms = G.ms_of(1.0)
    assert _gst_after_trig(127, G.RATE, interval=5.0) == pytest.approx(12.0 / (ms * 44.1 / 32.0), rel=0.03)
