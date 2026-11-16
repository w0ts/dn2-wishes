"""The Monomachine-style machines' tables, in the order dnfw.mnm.core.Layout addresses them: signed
Q23 words (the fill's FLOAT w BY -23) that dnfw.md.core ships in zpack after the Machinedrum's.
A leaf module (dnfw.md.core reads it while dnfw.mnm.core imports dnfw.md.core).

First, with one of the Monomachine's own machines in this build (SID 6581, DPRO-WAVE, -DDRW, -DENS,
VO-6: removed 2026-11-08, back 2026-11-11), their tables from the User's Monomachine OS
(dnfw.mnm.rom.packed_words, as at 28eb110's parent); then PLAITS's, built here from formulas.

PLAITS (dnfw.mnm.plaits): WS's five shapes (5 x 257) and the fold (516), Plaits'
resources/lookup_tables.py formulas (MIT, THIRD-PARTY.md); 2026-11-09, FM's (dnfw.mnm.plaits_fm):
lut_fm_frequency_quantizer / 64 (130) and the 4x downsampler's FIR (7).
"""

from __future__ import annotations

import math

# (name, words) in Layout's order (dnfw.mnm.core.Layout.PL)
PL_TABLES = (("ws", 5 * 257), ("fold", 516), ("fm", 130 + 7))
# 2026-11-12: JUNO's (dnfw.mnm.juno) after PLAITS's (dnfw.mnm.core.Layout.JU): KR-106's cutoff curve (G1Q / 32768),
# by RES 0..127 k / 8, the peak pull / 2, the fitted drive D and 1 / D / 8, by SUB and NOIS their levels (each scaled
# into +-1 for its Q23 word)
T_G1Q, T_K8, T_PULL2, T_D, T_ID8, T_SUB, T_NZ4 = 0, 1025, 1025 + 128, 1025 + 256, 1025 + 384, 1025 + 512, 1025 + 640
JU_WORDS = 1025 + 768
JUNO_DRIVE = ((0, 0.2), (80, 0.2), (110, 0.4), (120, 0.5), (127, 0.5))   # (RES, D): the host fit (scratch/juno-engine)


# -- the tables (plaits/resources/lookup_tables.py's formulas), as zpack carries them ------------
def _ws_shapes() -> list[list[int]]:
    """Plaits' ws_inverse_tan, ws_inverse_sin, ws_linear, ws_bump, ws_double_bump: 257 int16
    each (Tides' waveshaper, mirrored about the middle)."""
    n = 128
    xs = [k / n for k in range(n + 1)]
    tan_ = [math.atan(8 * math.cos(math.pi * x)) for x in xs]
    scale = max(tan_)
    fade = [min(1.0, 4.0 - 4.0 * x) for x in xs]
    shapes = (
        [math.acos(math.tan(scale * (1.0 - 2.0 * x)) / 8.0) / math.pi for x in xs],
        [math.acos(1 - 2 * x) / math.pi for x in xs],
        xs,
        [(1.0 - math.cos(math.pi * x * 1.5)) * (1.0 - math.cos(math.pi * f)) / 4.5
         for x, f in zip(xs, fade)],
        [math.sin(math.pi * x * 1.5) for x in xs])

    def flip(v):
        return [int(round(y * 32767.0)) for y in [-y for y in v[n:0:-1]] + list(v)]
    return [flip(v) for v in shapes]


def _fold() -> list[float]:
    """Plaits' lut_fold: 516 points, the bipolar fold normalised to 1."""
    n = 512
    x = [k / (n / 2.0) - 1.0 for k in range(n + 4)]
    x[-1] = x[-2]
    v = [math.sin(8 * math.pi * u) * math.exp(-u * u * 4) ** 2
         + math.atan(3 * u) * (1 - math.exp(-u * u * 4) ** 2) for u in x]
    m = max(abs(y) for y in v)
    return [y / m for y in v]


def _fm() -> list[float]:
    """FM's table (dnfw.mnm.plaits_fm.table, kept here: this module is a leaf): lookup_tables.py's
    fm_frequency_quantizer (its ratios, three points each, the widest gaps halved to 128, two
    more) / 64, then the 4x downsampler's FIR as f0 f1 f2 f3 f2 f1 f0."""
    r = [0.5, 0.5 * 2 ** (16 / 1200.0), math.sqrt(2) / 2, math.pi / 4, 1.0, 2 ** (16 / 1200.0),
         math.sqrt(2), math.pi / 2, 7.0 / 4, 2, 2 * 2 ** (16 / 1200.0), 9.0 / 4, 11.0 / 4,
         2 * math.sqrt(2), 3, math.pi, math.sqrt(3) * 2, 4, math.sqrt(2) * 3, math.pi * 3 / 2, 5,
         math.sqrt(2) * 4, 8]
    scale = []
    for x in r:
        scale += [12 * math.log2(x)] * 3
    while len(scale) < 128:
        d = [b - a for a, b in zip(scale, scale[1:])]
        gap = d.index(max(d))
        scale = scale[:gap + 1] + [(scale[gap] + scale[gap + 1]) / 2] + scale[gap + 1:]
    scale += [scale[-1], scale[-1]]
    fir = (0.02442415, 0.09297315, 0.16712938, 0.21547332)
    return [x / 64.0 for x in scale] + [fir[k] for k in (0, 1, 2, 3, 2, 1, 0)]


def _q23(y: float) -> int:
    return max(-(1 << 23), min((1 << 23) - 1, int(round(y * (1 << 23)))))


def plaits_words() -> tuple[int, ...]:
    """PL_TABLES' words (signed Q23, the fill's FLOAT w BY -23): the shapes x 256 (exact),
    the fold rounded (its 1.0 as the largest Q23 word)."""
    out = [y * 256 for row in _ws_shapes() for y in row]
    out += [_q23(y) for y in _fold()]
    out += [_q23(y) for y in _fm()]
    return tuple(out)


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


def juno_drive(res: int) -> float:
    """JUNO's saturation drive D at RES 0..127 (JUNO_DRIVE, linear between)"""
    for (r0, d0), (r1, d1) in zip(JUNO_DRIVE, JUNO_DRIVE[1:]):
        if res <= r1:
            return d0 + (d1 - d0) * (res - r0) / (r1 - r0)
    return JUNO_DRIVE[-1][1]


def juno_values() -> list[float]:
    """JUNO's tables as the DSP reads them (floats; zpack carries each as a Q23 word)"""
    from . import juno_data as JD
    out = [g / 32768.0 for g in JD.G1Q]
    out += [k / 4096.0 / 8.0 for k in JD.RES_K]
    out += [v / 4096.0 / 2.0 for v in JD.PEAK_PULL]
    out += [juno_drive(r) for r in range(128)]
    out += [1.0 / juno_drive(r) / 8.0 for r in range(128)]
    out += [v * 0.75 / 32768.0 for v in JD.SUB_LEVEL]
    out += [v * 91000.0 / 2.0 ** 30 / 4.0 for v in JD.NOISE_LEVEL]
    assert len(out) == JU_WORDS and all(-1.0 <= x < 1.0 for x in out)
    return out


def juno_words() -> tuple[int, ...]:
    """JUNO's tables as signed Q23 words"""
    return tuple(_q23(y) for y in juno_values())


def table_words() -> tuple[int, ...]:
    return (mnm_os_words() if mnm_os_on() else ()) + plaits_words() + juno_words()
