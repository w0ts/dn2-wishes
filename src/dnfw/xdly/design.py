"""XDLY's design constants (docs/xdly.md): optimist's cross-modulated dual delay
(firmware/src/fx/insfx/xdly.c, GPL-3.0-only, the owner's; after the SOMA LYRA-8's idea) at the
DN2's 48 kHz, in float32, with lines in DDR long enough for seconds.

Optimist (44.1 kHz, Q15): two lines of 16384 samples (0.37 s) whose outputs move each other's
time at the audio rate; TIME 1 / TIME 2 exponential 1 ms .. the line, followed over ~23 ms; MOD
moves each line's time by the other's last output, up to half its time either way; FDBK up to
1.05 into a soft knee (20000 / 32768) and a clamp, a fixed one-pole (~7 kHz) in each loop.
Here: lines of 2^19 samples (10.9 s at 48 kHz), TIMEs 1 ms .. 10 s, in the stock delay's own DDR
(its 4 MB sample area; one of the two plays at a time); the loops' one-pole on the
LPF knob (200 Hz .. 20 kHz; optimist's 7 kHz is about LPF 98).
"""

from __future__ import annotations

import math

FS = 48000
BLOCK = 32

LINE = 1 << 19                       # each line, samples (float32): 2 MB, 10.9 s
LINE_MASK = LINE - 1
T_MIN = 48.0                         # TIME 0: 1 ms
T_MAX = 480000.0                     # TIME 127: 10 s
D_LO, D_HI = 2.0, float(LINE - 3)    # a modulated time is kept inside the line (optimist: 2 .. M - 2)
KF = 1.0 / 1114.0                    # the times' follow a sample: optimist's >> 10 at 44.1 kHz (23.2 ms)
KNEE = 20000.0 / 32768.0             # the soft knee into the lines
FB_MAX = 270.0 * 128.0 / 32768.0     # FDBK (the stock word, knob / 128) x this: optimist's v x 270 / 2^15
MOD_GAIN = 0.5 * 127.0 * 258.0 / 32768.0   # MOD (HPF's word, knob / 127) x this: half the time at 127
TONE_LO, TONE_SPAN = 200.0, 100.0    # the loops' one-pole: 200 Hz x 100^LPF

LOG2_TMIN = math.log2(T_MIN)
LOG2_TSPAN = math.log2(T_MAX / T_MIN)
WID_TO_KNOB = 128.0 / 127.0          # WID's word is knob / 128; TIME 2 spans knob 0 .. 127 as TIME 1
W_TONE = -2 * math.pi * TONE_LO / FS / math.log(2)
LOG2_TONE_SPAN = math.log2(TONE_SPAN)

# the stock delay's parameter struct (0x257934, the bus's R8), measured in the runner: frame
# word 0x9c8 + 2 k for kit slot k, k 32 TIME .. 37 LPF
P_TIME, P_X, P_WID, P_FDBK, P_HPF, P_LPF = range(6)

# the stock delay (the bus's CALL at sw 0x1c1c58: R4 its DDR state, R8 its parameter struct,
# R12 the bus's I/O descriptor, as for the reverb); its sample area, measured in the runner:
# state + 4 .. + 0x400004 (its filters and other words from + 0x400004 on, its first word below)
STOCK_STATE = 0x8005912C
STOCK_AREA = (0x4, 0x400004)
STOCK_WORDS = (STOCK_AREA[1] - STOCK_AREA[0]) // 4
LINE_A = STOCK_STATE + STOCK_AREA[0]
LINE_B = LINE_A + 4 * LINE
assert 2 * LINE == STOCK_WORDS
CHUNK = 4096                         # words cleared a block when the stock delay comes back

# -- the Delay page's second page (docs/fxpage.md, csrc/fxpage): the ColdFire turns the page's knobs (0..127) into
# the engine's values, with the formulas below (csrc/fxpage/fxp_derive.h, held to derive() by test/test_fxpage.py),
# and sends them in the directory page at EX: the change word (0: nothing received yet: the constants), then five
# float32 words kf kn wl wr sn. Each knob's DEFAULT is the knob whose values are exactly the constants above (so a
# project that never touched the page plays bit for bit as before); the instances (inserts) always use the constants.
EX = 0x84000ED0
EX_WORDS = 6
SL_DEF = 58                          # SLEW: the times' follow KF; knob k: 1 / (48 x 1000^(k / 127)) (1 ms .. 1 s)
KN_DEF = 61                          # KNEE: the soft knee; knob k: 0.3 + k x 0.65 / 127
KN_LO, KN_STEP = 0.3, 0.65 / 127.0
WD_DEF = 127                         # WDTH: the lines' spread into out L / R: 127 hard (L = line 1), 0 mono
WD_K = 1.0 / 127.0
IN_DEF = 64                          # INPT: the lines' inputs, (L + R) / 2 each (64), towards L / R (127), swapped (0)
IN_K = 1.0 / 64.0


def derive(sl: int, kn: int, wd: int, inp: int):
    """the five float32 values of the page's knobs (the ColdFire's fxp_derive.h does the same, operation for operation):
    kf kn wl wr sn"""
    import numpy as np
    F = np.float32
    kf = F(KF) if sl == SL_DEF else F(1.0 / (SL_T0 * 1000.0 ** (sl / 127.0)))
    k = F(KNEE) if kn == KN_DEF else F(kn) * F(KN_STEP) + F(KN_LO)
    if wd == WD_DEF:
        wl, wr = F(1.0), F(0.0)
    else:
        w = F(wd) * F(WD_K)
        wl, wr = (F(1.0) + w) * F(0.5), (F(1.0) - w) * F(0.5)
    sn = F(0.0) if inp == IN_DEF else (F(inp) - F(64.0)) * F(IN_K)
    return kf, k, wl, wr, sn


SL_T0 = 48.0
