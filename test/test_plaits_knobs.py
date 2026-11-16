"""PLAITS' MODL knob: every model's knob_of is a knob the unit can hold, the page shows that model there, and the
DSP plays it (2026-11-12: knob_of(ADD) was 40, a knob no value of MODL's 0..100 record reaches; the harness's nearest
value played FM)."""

from __future__ import annotations

from dnfw.mnm import plaits as PLT
from dnfw.perc import live as PL
from dnfw.perc import machines as PM


def test_every_models_knob_is_reachable_and_maps_back():
    _rid, _slot, lo, top = PM.PARAMS[PLT.MODL_K]
    for m in range(PLT.N_MODELS):
        k = PLT.knob_of(m)
        assert PLT.model_of(k) == m, (m, k)
        v = PLT.knob_value(k)
        assert v is not None, f"model {m}: knob {k} has no value on MODL's record"
        assert PL.knob_word(k, top, lo) == (v + lo) << 8, (m, k, v)       # the harness stores that value
        assert PLT.dsp_model(v) == m, (m, k, v)


def test_the_page_and_the_dsp_agree_on_every_value():
    _rid, _slot, _lo, top = PM.PARAMS[PLT.MODL_K]
    for v in range(top + 1):
        assert PLT.model_of(int(v / top * 127 + 0.5)) == PLT.dsp_model(v), v


def test_add_is_41():
    assert PLT.knob_of(PLT.MODELS.index("ADD")) == 41
    assert PLT.knob_of(PLT.MODELS.index("FM")) == 30
