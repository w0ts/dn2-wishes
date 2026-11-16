"""JUNO's tables (dnfw.engines.juno.juno), in the Monomachine-style table run after PLAITS's (dnfw.mnm.tables,
dnfw.mnm.core.Layout.JU). A leaf module, as dnfw.mnm.tables (juno_data read when the words are made).
"""

from __future__ import annotations


def _q23(y: float) -> int:
    return max(-(1 << 23), min((1 << 23) - 1, int(round(y * (1 << 23)))))

# 2026-11-12: JUNO's (dnfw.engines.juno.juno) after PLAITS's (dnfw.mnm.core.Layout.JU): KR-106's cutoff curve (G1Q / 32768),
# by RES 0..127 k / 8, the peak pull / 2, the fitted drive D and 1 / D / 8, by SUB and NOIS their levels (each scaled
# into +-1 for its Q23 word)
T_G1Q, T_K8, T_PULL2, T_D, T_ID8, T_SUB, T_NZ4 = 0, 1025, 1025 + 128, 1025 + 256, 1025 + 384, 1025 + 512, 1025 + 640
JU_WORDS = 1025 + 768
JUNO_DRIVE = ((0, 0.2), (80, 0.2), (110, 0.4), (120, 0.5), (127, 0.5))   # (RES, D): the host fit (scratch/juno-engine)


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


def juno_words() -> tuple[int, ...]:
    """JUNO's tables as signed Q23 words"""
    return tuple(_q23(y) for y in juno_values())
