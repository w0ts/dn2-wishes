"""Per-track inserts (docs/inserts.md): the design's numbers.

One insert per track at a time, chosen by M.SEL, mixed in by MIX (dry / wet), with up to six knobs
of its own. Each runs per voice slot on the track's buffer in our own per-block pass, before the
stock chain (filter, amp, pan): mono, 32 samples, the machine's output (H1, docs additions-scope
§12). Their values come from the ColdFire in the sample pool's directory page: a byte a value,
0..127, 8 bytes a track (M.SEL, MIX, K1..K6).
"""

from __future__ import annotations

import math

FS = 48000
BLOCK = 32
TRACKS = 16

# M.SEL: 0 OFF, then the inserts in their build order
OFF, FUZZ, TAPE, FOLD, CHOR, WIDE, HARM = range(7)
NAMES = ("OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM")
BUILT = (FUZZ, TAPE, FOLD, HARM)                 # the types the pass before the filter runs
POST = (CHOR, WIDE)                              # the types the pass after the pan runs (stereo)

# where the values are: the pool's directory page, after the command block (dnfw.sampler.machines:
# names to 0xc08, the library ids to 0xe0c, the command block 0xf00..0xf18)
POOL_DDR = 0x84000000
PAR_OFFSET = 0xF80
PAR = POOL_DDR + PAR_OFFSET                       # 16 x 8 bytes: M.SEL, MIX, K1..K6 (little-endian words)
BUFFERS = 0x254A60                                # the 16 voice slots' buffers (dnfw.perc.program.BUFFERS)
ROUTE = 0x257898                                  # 16 x s16: the track each voice slot plays (the frame's
                                                  # 0xa5a + 2 s, from the ColdFire's slot map 0x80005308;
                                                  # docs/link-research.md §7)

# FUZZ: K1 DRIV, K2 TONE, K3 BIAS, K4 PRE, K5 GATE, K6 LEV
FZ_DRIVE_OCT = 8.0                                # DRIV: 2^(8 p), 0 .. 48 dB into the clip
FZ_TONE_LO, FZ_TONE_SPAN = 300.0, 40.0            # TONE: 300 Hz x 40^p (300 Hz .. 12 kHz)
FZ_BIAS_MAX = 0.6                                 # BIAS: an offset into the clip (even harmonics)
FZ_PRE_MAX = 3.0                                  # PRE: + 3 x the highs above 700 Hz into the clip
FZ_PRE_A = 1.0 - math.exp(-2 * math.pi * 700.0 / FS)
FZ_GATE_MAX = 0.05                                # GATE: below this (-26 dB) the fuzz closes
FZ_ENV_REL = math.exp(-1.0 / (0.04 * FS))         # the gate's follower: 40 ms release
FZ_GATE_K = 1.0 - math.exp(-1.0 / (0.01 * FS))    # the gate's own smoothing, 10 ms
FZ_DC_R = 1.0 - 2 * math.pi * 20.0 / FS           # the DC blocker after the clip: 20 Hz
IN_MAX = 4.0                                      # the input is held to +-4 (a hot machine)
W_TONE = -2 * math.pi * FZ_TONE_LO / FS / math.log(2)
LOG2_TONE_SPAN = math.log2(FZ_TONE_SPAN)

STATE_WORDS = 8                                   # per voice slot: the type's state (words 0..5), the track
                                                  # it last played (6), the last M.SEL (7)

# TAPE: K1 DRIV, K2 WOW, K3 WRAT, K4 FLUT, K5 AGE, K6 HISS. A soft saturation (a Pade tanh, x 1..8
# in), a short delay moved by a slow wow and a faster flutter (the pitch wobble), the high loss of
# age, hiss. Per track a ring of TP_RING samples in DDR (zeros at power-on).
TP_DRIVE_OCT = 3.0                                # DRIV: 2^(3 p), x 1 .. 8 into the saturation
TP_SAT_MAX = 3.0                                  # the Pade tanh's input, held to +-3 (where it is 1)
TP_D0 = 128.0                                     # the delay's centre, samples (2.7 ms)
TP_WOW_MAX = 72.0                                 # WOW: up to 1.5 ms either way
TP_WRAT_LO, TP_WRAT_SPAN = 0.1, 20.0              # WRAT: 0.1 Hz x 20^p (0.1 .. 2 Hz)
TP_FLUT_MAX = 12.0                                # FLUT: up to 0.25 ms either way
TP_FLUT_HZ = 7.3
TP_AGE_HI = 16000.0                               # AGE: the high loss, 16 kHz x 2^(-3 p) (16 .. 2 kHz)
TP_HISS_MAX = 0.03                                # HISS: p^2 x this, white noise
TP_RING = 512                                     # samples a track
TP_RING_DDR = 0x82500000                          # 16 x 2 KB
PH_PER_HZ = BLOCK / FS * 2 ** 32                  # a block's phase step per Hz, of 2^32
TP_FLUT_INC = round(TP_FLUT_HZ * PH_PER_HZ)
W_AGE = -2 * math.pi * TP_AGE_HI / FS / math.log(2)
LOG2_WRAT_SPAN = math.log2(TP_WRAT_SPAN)
LCG_A, LCG_C = 1664525, 1013904223

# FOLD: K1 AMNT, K2 SYMM, K3 SHPE, K4 TONE, K5 LEV. Gain 2^(4 p) (x 1 .. 16) and an offset (SYMM, 64
# none) into a wavefolder: triangle at SHPE 0, sine at 127; a DC blocker, TONE a one-pole, LEV.
FD_GAIN_OCT = 4.0
FD_BIAS_MAX = 1.0                                 # SYMM: (p - 0.5) x 2 x this
FD_OFFSET = 64.0                                  # (keeps the fold's argument positive for TRUNC)
# HARM: K1 AMNT, K2 FREQ, K3 EVEN, K4 TONE, K5 LEV. The band above FREQ (a one-pole high-pass, 500 Hz
# x 16^p) driven x 4 into Chebyshev-like shapers: b^2 (even) and 4 b^3 - 3 b (odd), mixed by EVEN, a
# DC blocker, TONE a one-pole, added to the dry track at AMNT x 0.5, LEV.
HM_FREQ_LO, HM_FREQ_SPAN = 500.0, 16.0
HM_DRIVE = 4.0
HM_AMNT_MAX = 0.5
W_HM = -2 * math.pi * HM_FREQ_LO / FS / math.log(2)
LOG2_HM_SPAN = math.log2(HM_FREQ_SPAN)

# -- after the pan: the voice in stereo (dnfw.inserts.post). Each voice slot's stereo block, as the
# stock voice chain leaves it for the FX sends (sw 0x1c1738) and the routing (0x1c1f1e): L 32 floats at
# STEREO + 0x100 s, R at + 0x80 (byte addresses; docs/inserts.md "After the pan")
STEREO = 0x257EE8
STEREO_STRIDE = 0x100
STEREO_R = 0x80
POST_RING = 1024                                  # samples a voice slot (21.3 ms), CHOR's or WIDE's
POST_RING_DDR = 0x82510000                        # 16 x 4 KB (after TAPE's rings; zeros at power-on)

# WIDE: K1 WDTH, K2 TIME, K3 BASS, K4 TONE. Mid and side; the side times 2 WDTH, plus the mid delayed by
# TIME (0.5 .. 20 ms), high-passed at BASS (40 .. 640 Hz: the lows stay mono) and TONE'd, times WDTH.
WD_D_MIN, WD_D_SPAN = 24.0, 936.0                 # TIME: 24 + 936 p samples
WD_BASS_LO, WD_BASS_SPAN = 40.0, 16.0
W_WB = -2 * math.pi * WD_BASS_LO / FS / math.log(2)
LOG2_WB_SPAN = math.log2(WD_BASS_SPAN)

# CHOR: K1 DPTH, K2 RATE, K3 DLY, K4 VOIC, K5 WDTH, K6 FDBK. One to four voices reading one ring (the
# mid, plus FDBK x the wet), each its own delay DLY + DPTH x a sine a quarter turn from the last, spread
# left / right by WDTH; MIX the dry / wet.
CH_DLY_MIN, CH_DLY_SPAN = 240.0, 480.0            # DLY: 5 .. 15 ms
CH_DEP_MAX = 192.0                                # DPTH: up to 4 ms either way (so a read is >= 48 back)
CH_RATE_LO, CH_RATE_SPAN = 0.05, 100.0            # RATE: 0.05 .. 5 Hz
LOG2_CR_SPAN = math.log2(CH_RATE_SPAN)
CH_VOICES_K = 3.99                                # VOIC: 1 + trunc(3.99 p) voices
CH_FB_MAX = 0.7
assert CH_DLY_MIN - CH_DEP_MAX >= BLOCK + 2       # every read is of an earlier block's samples
assert CH_DLY_MIN + CH_DLY_SPAN + CH_DEP_MAX + BLOCK + 2 < POST_RING
assert WD_D_MIN + WD_D_SPAN < POST_RING
