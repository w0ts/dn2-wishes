"""ANALOG 2's sound picks (2026-11-21) never peak above the sound before them (the User: no digital clipping; B never
above A at any setting). The parts that can be checked without a render: DRV's degree-4 tanh never above the degree-8
curve before it, at any input (float32, as the DSP); the side's level never above the level before the low-RES trim."""

from __future__ import annotations

import numpy as np

from dnfw.engines.analog2 import analog2 as A2


def _horner32(c, x):
    x = np.asarray(x, dtype=np.float32)
    s = x * x
    acc = np.full_like(x, np.float32(c[-1]))
    for ck in c[-2::-1]:
        acc = acc * s + np.float32(ck)
    return x * acc


def test_drive_tanh_never_above_the_old_curve():
    x = np.linspace(0.0, 2.0, 2_000_001, dtype=np.float32)
    new = _horner32(A2.TANH_P, x)
    old = _horner32(tuple(c * A2.TOP15 for c in A2.TANH_P8), x)
    assert float(np.max(new - old)) <= 0.0
    assert float(np.max(old - new)) < 1.1e-3                       # within 1.08e-3 of the old curve
    x64 = np.linspace(0.0, 2.0, 200_001)
    assert float(np.min(np.diff(x64 * np.polyval(A2.TANH_P[::-1], x64 * x64)))) > 0.0   # rising
    assert float(new[-1]) <= float(old[-1])                        # the clamp's top (x = 2): not louder


def test_drive_tanh_odd_and_small_signal_gain():
    x = np.float32(1e-3)
    assert _horner32(A2.TANH_P, -x) == -_horner32(A2.TANH_P, x)
    assert 0.99 < float(_horner32(A2.TANH_P, x) / x) <= 1.0


# the side trims a CUT sweep needed at low RES (B's stereo peak down to A's; peak grid 2026-11-21), per model: RES -> trim
NEEDED = {"LADR": {0: 0.835, 5: 0.975, 10: 0.995, 15: 0.99},
          "OTA": {0: 0.83, 5: 0.96},
          "DIOD": {0: 0.91, 5: 0.88, 10: 0.905, 15: 0.97}}


def test_side_low_res_trim_under_every_needed_trim():
    for res_need in NEEDED.values():
        for res, need in res_need.items():
            assert min(1.0, A2.SIDE12_LOW0 + A2.SIDE12_LOWK * res) <= need - 0.01, (res, need)
    assert A2.SIDE12_LOW0 + A2.SIDE12_LOWK * 25 >= 1.0                 # full level from RES 25


def test_side_level_under_the_least_needed_trim():
    """the full peak grid's least needed trim was 0.99 (MS20 LP24 RES 20 .. 30, DRV 127): the side's level stays under"""
    assert A2.SIDE12_LEVEL <= 0.98
