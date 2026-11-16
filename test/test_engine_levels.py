"""Our engines' levels against the stock synths' (2026-11-12, the User: "compare the engine levels, they should match
approx, don't boost out of the blue"; docs/levels.md).

MEASURED is each engine at its defaults as v0.22 measured MD_LEVEL (docs/md.md): the SHARC runner, track 0 on the init
sound, note 60 at block 1, the amp stage's input (after the stock filter, before the amp), 341 blocks (227 ms), at the
levels the engines had then (LEVELS_THEN). A held synth's band: its RMS within +-2 dB of stock WaveTone's; a hit's: its
peak within +-2 dB of the stock synths' mean peak (WaveTone, FM TONE; FM DRUM and Swarmer do not render in the runner).
The test moves each measured figure by the level the engine has now (dnfw.perc.program) against the one it had then,
and holds it in its band: a level changed later without a new measurement fails here.
"""

from __future__ import annotations

import math

import pytest

from dnfw.perc import program as P

WAVETONE_RMS = -26.4
STOCK_PEAK = (-15.8 + -18.7) / 2                # WaveTone, FM TONE
BAND = 2.0

# engine -> (kind, peak dB, RMS dB) at LEVELS_THEN (gpufarm, main f649683c; PLAITS ADD at MODL knob 41)
MEASURED = {
    "ANALOG2": ("held", -17.8, -23.2), "PLAITS WS": ("held", -18.2, -23.6), "SID 6581": ("held", -18.2, -24.7),
    "PLAITS FM": ("held", -19.6, -24.8), "PLAITS ADD": ("held", -19.4, -28.4), "PLAITS VA": ("held", -20.1, -25.5),
    "DRONE": ("held", -18.2, -25.9), "VO-6": ("held", -18.8, -26.0), "PLAITS NOIS": ("held", -18.2, -27.7),
    "PLAITS SWRM": ("held", -18.0, -28.9), "DPRO-DDRW": ("held", -18.2, -29.3), "DPRO-WAVE": ("held", -19.1, -30.5),
    "DPRO-DENS": ("held", -18.7, -33.0),
    "SOPHIE": ("hit", -21.1, -34.9), "TB303": ("hit", -22.7, -35.4), "PLAITS MDAL": ("hit", -19.5, -33.3),
    "PLAITS SD": ("hit", -19.9, -35.6), "PLAITS HH": ("hit", -21.3, -37.0), "PLAITS PART": ("hit", -17.9, -37.5),
    "PLAITS BD": ("hit", -27.0, -38.0), "PLAITS STRG": ("hit", -27.0, -38.9),
    "JUNO": ("held", -18.0, -25.3),      # 2026-11-12, on r11f (e0868f63) at MD_LEVEL: in band, no LEVEL_DB entry
}
# 2026-11-12, the User on r11f ("bring it back how it was, apply the correction only to the melodic synths"): the drums
# and percussion keep the level they had, whatever their band says
PERCUSSION = ("SOPHIE", "PLAITS BD", "PLAITS SD", "PLAITS HH")
MD_THEN = 1.4
LEVELS_THEN = {"DRONE": 0.7, "SID 6581": 5.4, "DPRO-WAVE": 11.5, "DPRO-DDRW": 0.95, "DPRO-DENS": 2.0, "VO-6": 16.5}


def _now(name: str) -> float:
    if name.startswith("PLAITS "):
        model = name.split()[1]
        return P.MD_LEVEL * P._db(P.PLAITS_LEVEL_DB.get(model, 0.0))
    return P.MNM_LEVELS.get(name, P.MD_LEVEL)


def _then(name: str) -> float:
    return MD_THEN if name.startswith("PLAITS ") else LEVELS_THEN.get(name, MD_THEN)


@pytest.mark.parametrize("name", sorted(n for n in MEASURED if n not in PERCUSSION))
def test_each_engine_sits_in_its_band(name):
    kind, peak, rms = MEASURED[name]
    moved = 20.0 * math.log10(_now(name) / _then(name))
    if kind == "held":
        assert abs(rms + moved - WAVETONE_RMS) <= BAND, f"{name}: RMS {rms + moved:.1f} dB, band {WAVETONE_RMS}+-{BAND}"
    else:
        assert abs(peak + moved - STOCK_PEAK) <= BAND, f"{name}: peak {peak + moved:.1f} dB, band {STOCK_PEAK}+-{BAND}"


@pytest.mark.parametrize("name", PERCUSSION)
def test_the_drums_keep_the_level_they_had(name):
    assert _now(name) == pytest.approx(_then(name), rel=1e-12), name


def test_an_engine_already_in_its_band_keeps_its_level():
    """no boost out of the blue: only the engines measured outside their band moved"""
    for name, (kind, peak, rms) in MEASURED.items():
        inside = abs((rms - WAVETONE_RMS) if kind == "held" else (peak - STOCK_PEAK)) <= BAND
        if inside:
            assert _now(name) == pytest.approx(_then(name), rel=1e-12), name


def _plaits(model: str, blocks: int = 10) -> list[float]:
    from dnfw.mnm import machines as MM
    from dnfw.engines.plaits import plaits as PLT
    from dnfw.perc import live as PL
    h = PL.Harness(2)
    knobs = list(MM.DEFAULTS["PLAITS"])
    knobs[PLT.MODL_K] = PLT.knob_of(PLT.MODELS.index(model))
    h.set_mnm_voice(MM.NAMES.index("PLAITS"), knobs)
    out = []
    for b in range(blocks):
        out += h.block(48.0, trig=b == 0)
    return out


@pytest.mark.parametrize("model", ["STRG", "WS"])
def test_the_plaits_level_is_a_pure_scale_by_model(model, monkeypatch):
    now = _plaits(model)
    monkeypatch.setattr(P, "PLAITS_LEVEL_DB", {})
    then = _plaits(model)
    g = P._db({"STRG": 8.4, "WS": -2.8}[model])
    assert max(abs(x) for x in then) > 1e-4, f"PLAITS {model}: silent"
    for x, y in zip(then, now):
        assert y == pytest.approx(x * g, rel=1e-4, abs=1e-7)

