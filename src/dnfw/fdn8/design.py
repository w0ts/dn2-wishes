"""FDN8 at 48 kHz on the Digitone II: the design's numbers (docs/fdn8.md).

FDN8 is the owner's reverb from optimist (firmware/src/fx/reverb/reverb_alt.c, the rvf_*
section, GPL-3.0-only), there at 22.05 kHz in integer arithmetic. Here it runs at the DN2's
48 kHz in float32, in the stock reverb's slot, with the same structure and curves: a
pre-delay, four input allpasses, eight modulated lines read through a first-order allpass
for the fraction, a one-pole damping per line (Jot), a decay gain per line, the 8 x 8
Householder matrix. Every length is optimist's 32 KB ring's (the pool's) at 48/22.05, the
nearest unused prime. The random rounding is gone (float needs none).

This module holds only constants and the ring's layout; dnfw.fdn8.ref is the reference and
dnfw.fdn8.program the DSP code (the DSL), held to the reference bit for bit.
"""

from __future__ import annotations

import math

FS = 48000
BLOCK = 32
S = FS / 22050                                   # optimist's tank ran at 22.05 kHz

# optimist's 32 KB ring (RVL_B) and diffusers, at 22.05 kHz
L22 = (1361, 1499, 1637, 1823, 2039, 2267, 2477, 2579)
A22 = (47, 37, 113, 83)
# the same times at 48 kHz: the nearest unused prime of each (design.primes48 recomputes them)
L48 = (2963, 3259, 3559, 3967, 4441, 4933, 5393, 5623)
A48 = (101, 79, 241, 181)
LREF = 978                                       # optimist's RV_LREF: the damping's reference line

# the modulation: optimist's RV_FEXC 4 .. RV_EXC 8 samples at 22.05 kHz (4 below the knee,
# growing to 8 at SIZE 127), times S; MOD (the GAIN knob) scales it 0 .. 2 (64: optimist's)
FEXC48 = 4 * S
EXC48 = 8 * S
MOD_MAX = 2.0
DEPTH_MAX = EXC48 * MOD_MAX                      # 34.83 samples
CM = 37                                          # a line's read centre past its length
SP = 2 * CM + 2                                  # its span past its length (reads L+1 .. L+SP-1)
# LFO_INC r -> 0.05 x 800^(r/127) Hz (optimist's table); RV_RATES, a line each
RATES_R = (50, 58, 46, 55, 60, 49, 52, 47)
RATES_HZ = tuple(0.05 * 800 ** (r / 127) for r in RATES_R)
LFO_INC = tuple(round(hz * BLOCK / FS * 2 ** 32) for hz in RATES_HZ)   # per block, of 2^32
LFO_PH0 = (0x00000000, 0x9E3779B9, 0x3C6EF372, 0xDAA66D2B, 0x78DDE6E4, 0x1715609D,
           0xB54CDA56, 0x5384540F)               # optimist's: no two lines move together

# SIZE: optimist's curve (RV_KNEE 90, RV_STEPS 110, RV_FRZ8 18, RV_KG 31, RV_INSH 3)
KNEE = 90.0
DBL_PER_STEP = 10.0 / 110.0                      # doublings of the decay time per SIZE step above it
FRZ = 18.0 / 8.0                                 # SIZE 127: this many more doublings (a near-freeze)
KG = 31.0 / 32.0                                 # the loop gains' share of the decay
KT_SCALE = 22050.0 / 48000.0                     # optimist's decay per 22.05 kHz sample -> per 48 kHz sample
# DAMP: optimist's rv_damp cubic for FDN8 (32779, 15872, 28161, -150), Q15
DAMP_C = (32779.0, 15872.0, 28161.0, -150.0)
A_MAX = 31000.0 / 32768.0                        # rv_lpc's clamp of the mean line's coefficient
K22 = 2 - 2 * math.cos(2 * math.pi * 4000 / 22050)   # optimist's RV_K4 (76311 / 2^16)
K48 = 2 - 2 * math.cos(2 * math.pi * 4000 / FS)
T_MAX = 7.0                                      # rv_lpc's clamp: at most 2^7 (21 dB) a pass at 4 kHz
# the send and the wet level (optimist's 13000 / 2^15 and RV_OUT32 7670 << 2 / 2^15)
GIN = 13000.0 / 32768.0
GOUT = 7670.0 / 8192.0
# PRE: a knob of its own here, 0 .. 100 ms, square law
PD_MAX = 4800
# the input filters on the HPF / LPF knobs (one-poles): HPF 20 Hz .. 2 kHz, LPF 200 Hz .. 20 kHz
HPF_LO, LPF_LO, FILT_SPAN = 20.0, 200.0, 100.0

# -- LONG (TYPE 2, 2026-11-09): a bigger, darker room. Every line and diffuser about twice as
# long (the nearest unused primes to 2 x FDN8's), the decay time 1.5 x at the same SIZE, and 1.5 x
# the high-frequency loss a second (Jot's damping per line scaled by its length, then x 1.5)
LONG_X = 2.0
LONG_DECAY = 1.5
LONG_DARK = 1.5


def _primes_near(xs, used) -> tuple[int, ...]:
    def isp(n):
        return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))
    out = []
    for x in xs:
        c = round(x)
        v = next(v for k in range(400) for v in (c - k, c + k) if isp(v) and v not in used)
        used.add(v)
        out.append(v)
    return tuple(out)


_used: set[int] = set(L48 + A48)
L48L = _primes_near([LONG_X * x for x in L48], _used)
A48L = _primes_near([LONG_X * x for x in A48], _used)


# -- the ring (one write index counting down; a line's k-th sample back at base + k) --------
def layout(ls, as_):
    """(RB_A, RB_L, RB_END) for line lengths LS and diffusers AS_ after the pre-delay"""
    ra, rl = [], []
    b = PD_MAX + 1
    for a in as_:
        ra.append(b)
        b += a + 1
    for ln in ls:
        rl.append(b)
        b += ln + SP
    return tuple(ra), tuple(rl), b


RB_PD = 0
RB_A, RB_L, RB_END = layout(L48, A48)
RB_AL, RB_LL, RB_ENDL = layout(L48L, A48L)
RB_0 = RB_A[-1] + A48[-1] + 1
RING_WORDS = 1 << 17                             # 512 KB of float32, a power of two (256 KB until LONG)
RING_MASK = RING_WORDS - 1
assert max(RB_END, RB_ENDL) <= RING_WORDS


def variant(v: int) -> dict:
    """FDN8 (v 1) or LONG (v 2): what differs, as the DSP's active table holds it"""
    ls, as_, ra, rl = (L48, A48, RB_A, RB_L) if v == 1 else (L48L, A48L, RB_AL, RB_LL)
    long_ = v == 2
    return {"L": ls, "A": as_, "RA": ra, "RL": rl,
            "ktv": 1.0 / LONG_DECAY if long_ else 1.0,
            # optimist's line length in its damping (rv_lpc's L / LREF), scaled with the line
            "sl": tuple(L22[k] * (ls[k] / L48[k]) * (LONG_DARK if long_ else 1.0) for k in range(8))}


def primes48() -> tuple[tuple[int, ...], tuple[int, ...]]:
    """L48, A48 recomputed: each optimist length times S, the nearest prime not used yet"""
    def isp(n):
        return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))
    used: set[int] = set()
    out = []
    for x in L22 + A22:
        c = round(x * S)
        v = next(v for k in range(200) for v in (c - k, c + k) if isp(v) and v not in used)
        used.add(v)
        out.append(v)
    return tuple(out[:8]), tuple(out[8:])


assert primes48() == (L48, A48)


# -- the Reverb page's second page (docs/fxpage.md, csrc/fxpage): the ColdFire turns the page's knobs (0..127) into the
# engine's values and sends them in the directory page at EX (after XDLY's: dnfw.xdly.design.EX + 24): the change
# word (0: nothing received yet: the constants), then four float32 words sd f wl wr. Each knob's DEFAULT gives the
# values under which the engine does exactly what it did before (x 1.0, + 0.0, a branch past the width), so a
# project that never touched the page plays bit for bit as before; the instances (inserts) always use those.
EX = 0x84000ED0 + 24
EX_WORDS = 5
DF_DEF = 64                          # DIFF: the diffusers' coefficients (0.75 .. 0.8 / 0.625 .. 0.7) x k / 64, held to 0.95
DF_K = 1.0 / 64.0
DF_MAX = 0.95
WD_DEF = 127                         # WDTH: the lines' spread into out L / R: 127 as the tank has it, 0 mono
WD_K = 1.0 / 127.0
FZ_DEF = 0                           # FREZ: the lines' gains towards 1 (a hold): g x (1 - f) + f, f = k / 127
FZ_K = 1.0 / 127.0


def derive(df: int, wd: int, fz: int):
    """the four float32 values of the page's knobs (csrc/fxpage/fxp_derive.h does the same): sd f wl wr"""
    import numpy as np
    F = np.float32
    sd = F(1.0) if df == DF_DEF else F(df) * F(DF_K)
    f = F(0.0) if fz == FZ_DEF else F(fz) * F(FZ_K)
    if wd == WD_DEF:
        wl, wr = F(1.0), F(0.0)
    else:
        w = F(wd) * F(WD_K)
        wl, wr = (F(1.0) + w) * F(0.5), (F(1.0) - w) * F(0.5)
    return sd, f, wl, wr
