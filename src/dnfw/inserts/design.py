"""Per-track inserts (docs/inserts.md): the design's numbers.

Two insert slots per track (2026-11-10, the User), each chosen by its M.SEL, mixed in by its MIX
(dry / wet), with up to six knobs of its own. Each runs per voice slot on the track's buffer in our own per-block pass, before the
stock chain (filter, amp, pan): mono, 32 samples, the machine's output (H1, docs additions-scope
§12). Their values come from the ColdFire in the sample pool's directory page: a byte a value,
0..127, 8 bytes a track (M.SEL, MIX, K1..K6).
"""

from __future__ import annotations

import math

FS = 48000
BLOCK = 32
TRACKS = 16

# M.SEL: 0 OFF, then the inserts in their build order (a type is a number 0..15 for good: the saved
# records keep it, so a type added later takes the next number). 2026-11-10: SUB DIST GATER RING
# (ported from Optimist, ports3) take 9..12. The ColdFire's M.SEL is a 0..127 value, each type a band
# of it: type = value x len(NAMES) / 128 (csrc/inserts/ins.c TYPES = len(NAMES))
# 2026-11-12: JUNO (Optimist's Juno-106 chorus, after the pan) takes 13.
OFF, FUZZ, TAPE, FOLD, CHOR, WIDE, HARM, FDN8, XDLY, SUB, DIST, GATER, RING, JUNO = range(14)
NAMES = ("OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM", "FDN8", "XDLY", "SUB", "DIST", "GATER", "RING",
         "JUNO")
PORTS = (SUB, DIST, GATER, RING)                 # Optimist's four: each a builder part (dnfw.builder.parts)
PART = {SUB: "INS_SUB", DIST: "INS_DIST", GATER: "INS_GATER", RING: "INS_RING"}


def _ports_built() -> tuple[int, ...]:
    from ..builder import selection
    return tuple(t for t in PORTS if selection.on(PART[t]))


# the types the pass before the filter runs (mono, per voice): the tree's four, and those of Optimist's
# four this build has (dnfw.builder: a type left out plays as OFF)
BUILT = (FUZZ, TAPE, FOLD, HARM) + _ports_built()
POST = (CHOR, WIDE, JUNO)                        # the types the pass after the pan runs (stereo)
BUS = (FDN8, XDLY)                               # the types the pass on the track's bus runs (dnfw.inserts.bus)
TYPE_BITS = 4                                    # field 0 of a record: type | instance << TYPE_BITS
SLOTS = 2                                        # insert slots a track; slot 1 runs before slot 2 within a stage
RECORDS = TRACKS * SLOTS                         # record 2 t + j: track t's slot j
FIELDS = 8                                       # a record: type | instance << 4, MIX, K1..K6 (0..127 each)

# where the values are: the pool's directory page, after the command block (dnfw.sampler.machines:
# names to 0xc08, the library ids to 0xe0c, the command block 0xf00..0xf18)
POOL_DDR = 0x84000000
PAR_OFFSET = 0xF80
PAR = POOL_DDR + PAR_OFFSET                       # (until 2026-11-10: 16 x 8 bytes, one slot)
# 2026-11-10, two slots: 32 records of eight 7-bit fields do not fit 0xf80..0x1000 as bytes, so they are
# packed (pack()): 8 groups of 4 records, 7 words a group, at PACK_OFFSET; the change word before them
# moves with every send. 0xf18..0x1000 is all that lies after the command block (0xf00 + 6 words) in
# the directory page, which loads never write past the command block.
GEN_OFFSET = 0xF18
PACK_OFFSET = 0xF20
PACK_WORDS = 56
GEN = POOL_DDR + GEN_OFFSET
PACK = POOL_DDR + PACK_OFFSET
assert PACK_OFFSET + 4 * PACK_WORDS == 0x1000 and RECORDS * FIELDS * 7 == 32 * PACK_WORDS
# the bus pass's L2 (dnfw.waverider.dsp.INSBUS_L2_LOAD: the 16 KB between the sample machines' code,
# which ends at 0x200bc000, and PERC's at 0x200be200 (0x200c0000 until 2026-11-12); clear of ports3's 0x200b1800..0x200b6000): its
# code, then its state
BUS_STATE = 0x200BD000                            # (dnfw.waverider.dsp.INSBUS_STATE_L2)
BUS_STATE_END = 0x200BE200                        # PERC's code starts here (dnfw.waverider.dsp.PERC_L2_LOAD)
# the unpacked records, then the last change word: in the pre pass's state (loaded with zeros). 2026-11-11 (perf):
# L1 (0x2e3000 + 0x600; was L2 0x200AFA00, 4 cycles an access): the pre and post passes' state and scratch are in
# L1 0x2e3000..0x2e4050, in the zeros that were PING's state (dnfw.waverider.dsp.INS_STATE_DM, POST_STATE_DM)
TABLE = 0x2E3600
TABLE_BYTES = 4 * (RECORDS * FIELDS + 1)
# 2026-11-10 (perf): after them, three flags the pre pass's unpack sets when the records change: any
# record of a BUILT (pre), POST, BUS type. Each pass skips its 32 records' walk when its flag is 0
# (every record OFF to it: the walk would do nothing). A harness that writes TABLE writes FLAGS too.
FLAGS = TABLE + TABLE_BYTES
FLAG_WORDS = 3
assert FLAGS + 4 * FLAG_WORDS <= 0x2E3A40


# 2026-11-11 (the User: "DSP: always run in slot order"): the passes run by stage (pre, post, bus), so a
# slot 1 of a POST or BUS type with a slot 2 of a BUILT type ran slot 2 first. In that pair slot 2 moves:
# the pre pass leaves it out and the bus pass runs it on the track's block (L and R, each its own state)
# after slot 1, so it acts on the summed voices after the filter, amp and pan. Every other pair as before.
MOVERS = POST + BUS                              # slot 1's types that move a BUILT slot 2 to the bus
INS_ONE_SW = 0xBD6D03                            # the pre pass's one insert (dnfw.inserts.program.one), after
                                                 # its entry's 48-bit JUMP (dnfw.waverider.dsp.INS_SW + 3)
MV_RING_DDR = 0x82540000                         # a moved TAPE's rings: 32 x 2 KB (track t, L 2 t, R 2 t + 1),
                                                 # after the post rings (0x82510000 + 32 x 4,104 B)
MV_INSTANCES = 2 * TRACKS


def field0(table: bytes | list[int], r: int) -> int:
    return int(table[FIELDS * r]) & ((1 << TYPE_BITS) - 1)


def moved(table: bytes | list[int], t: int) -> bool:
    """track T's slot 2 runs on the bus, after slot 1 (MOVERS)"""
    return field0(table, 2 * t) in MOVERS and field0(table, 2 * t + 1) in BUILT


def flags(table: bytes | list[int]) -> list[int]:
    """the FLAGS words for the unpacked records TABLE (32 x 8 fields): any BUILT, any POST, any BUS
    (or a moved slot 2: the bus pass runs it)"""
    types = {field0(table, r) for r in range(RECORDS)}
    out = [int(bool(types & set(g))) for g in (BUILT, POST, BUS)]
    out[2] |= int(any(moved(table, t) for t in range(TRACKS)))
    return out
# the routing's per-track blocks (docs/link-research.md §5, §7: 0x1c1f1e sums each voice slot's stereo
# block, x 14.125, into the block of the track the slot plays): L 32 floats at + 0x100 t, R at + 0x80
BUS_BLOCKS = 0x258F68
BUS_R = 0x80
FDN8_SW, XDLY_SW = 0xBD5000, 0xBD6200                 # the engines' entries (dnfw.waverider.dsp FDN8_SW, XDLY_SW)
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

# -- SUB, DIST, GATER, RING: ported from Optimist (GPL-3.0-only, the User's own), firmware/src/fx/insfx/insfx.c
# (ifx_mod: RING, SUB), firmware/src/fx/fx.c (dist_gains, dist_run: DIST), firmware/src/fx/insfx/gater.c
# (GATER); rewritten here in float32 for the SHARC (docs/inserts.md). Mono, before the filter, in either
# insert slot; each (voice slot, insert slot) its own state.

# SUB: K1 LEV, K2 BAND, K3 TONE, K4 OCT, K5 DRY. An octave down (OCT 64..127: two): a flip-flop on the
# zero crossings of the band under BAND (a one-pole, 110 Hz x 8^p), a Schmitt trigger at 1/8 of its
# envelope (fast up, slow down); a square at that envelope's level (the second flip-flop toggles on the
# first's rising edges), rounded by TONE (a one-pole, 60 Hz x 16^p), x LEV, added to the dry x DRY.
SB_BAND_LO, SB_BAND_SPAN = 110.0, 8.0
SB_TONE_LO, SB_TONE_SPAN = 60.0, 16.0
W_SB = -2 * math.pi * SB_BAND_LO / FS / math.log(2)
LOG2_SB_SPAN = math.log2(SB_BAND_SPAN)
W_ST = -2 * math.pi * SB_TONE_LO / FS / math.log(2)
LOG2_ST_SPAN = math.log2(SB_TONE_SPAN)
SB_UP, SB_DN = 1.0 / 8, 1.0 / 1024                # the envelope: ~0.2 ms up, ~21 ms down (Optimist's >>3, >>10)
SB_THR = 1.0 / 8                                  # the trigger's threshold, of the envelope

# DIST: K1 DRIV, K2 TONE, K3 BIAS, K4 LOW, K5 LEV. Optimist's DIST: the drive relative to the voice's peak
# (a follower, instant up, ~0.35 s down: DRIV means the same clipping on a quiet and a loud note), 0.5x ..
# 48x into FUZZ's clip (its bias, DC blocker and TONE), the band under LOW (a one-pole, 20 Hz x 16^p) kept
# out of the clip and added back dry, then back to the peak's level with a make-up (/ 1.5 min(G, 1)),
# x LEV x 2. It runs FUZZ's sample loop (program.fz_loop) with its own block values.
DS_DRIVE_LO, DS_DRIVE_OCT = 0.5, math.log2(96.0)  # DRIV: 0.5 x 2^(6.58 p), 0.5x .. 48x
DS_FLOOR = 0.1                                    # the peak's floor (near silence is not driven to full)
DS_REL = math.exp(-1.0 / (0.35 * FS))             # the peak's release, a sample
DS_LOW_LO, DS_LOW_SPAN = 20.0, 16.0
W_DL = -2 * math.pi * DS_LOW_LO / FS / math.log(2)
LOG2_DL_SPAN = math.log2(DS_LOW_SPAN)
DS_LEV_MAX = 2.0

# RING: K1 FREQ, K2 SHPE, K3 AM, K4 LEV. The voice times a sine of 26 Hz x 100^p (26 Hz .. 2.6 kHz,
# Optimist's range, an exponential knob); SHPE drives the sine into a clip (x 1 .. 16: towards a square);
# AM lifts the carrier towards 1 (0: ring, 127: the dry); LEV.
RG_LO, RG_SPAN = 26.0, 100.0
LOG2_RG_SPAN = math.log2(RG_SPAN)
RG_PH_PER_HZ = 2 ** 32 / FS                       # a sample's phase step per Hz, of 2^32
RG_SHAPE_MAX = 15.0

# GATER: K1 DPTH, K2 PATN, K3 RATE, K4 SHPE, K5 SWNG. Optimist's trance gate: 16 patterns of 16 steps,
# each step a note value of the tempo; an open step ('x') is a pulse, open to its end, or to its middle
# when the next step is open too; the gain follows open / closed (closed: 1 - DPTH) at a bounded slope
# (SHPE: a ramp of 2^((SHAPE - 127) / 16) / 2 of a step, held to 1 .. 171 ms); SWNG makes each pair's first
# step longer (+ 0 .. 50 %). The phase: Q28 a step, 2^32 the 16 steps (it wraps by itself), run from
# the tempo (the frame's BPM x 120); the ColdFire's clock word (CLK) puts it on the sequencer's place.
GT_PAT = (0xFFFF, 0x5555, 0x1111, 0x0101, 0x4444, 0xAAAA, 0x9249, 0x1041,
          0x6D6D, 0xB6DB, 0xB777, 0xDAB5, 0xDDDD, 0xBBBB, 0x1449, 0x4949)   # Optimist's IGT_PAT, bit k step k
GT_PAT_NAMES = ("16TH", "8TH", "4TH", "HALF", "OFF8", "OF16", "DOT8", "DOT4",
                "TRN1", "TRN2", "TRN3", "TRN4", "GALP", "RGAL", "CLAV", "TRSL")
GT_RATE = (192, 96, 48, 32, 24, 16, 12, 6)        # RATE: a step in ticks of 1/96 beat (a 16th = 24)
GT_RATE_NAMES = ("1/2", "1/4", "1/8", "1/8T", "1/16", "1/16T", "1/32", "1/64")
GT_STEP = 1 << 28
GT_PAIR = 2 * GT_STEP
GT_SWING_MAX = 0.5
GT_SMAX, GT_SMIN = 1.0 / 48, 1.0 / 8192           # the closure's slope a sample (48 .. 8192 samples)
GT_SHAPE_OCT = 127.0 / 16
GT_TOL_TICKS = 2                                  # the clock word moves the phase when it is this far off
FRAME = 0x25C48C                                  # the DSP's frame copy (dnfw.perc.machines.FRAME)
TEMPO = FRAME + 216                               # its word 108: BPM x 120 (dnfw.sampler.program.TEMPO_OFFSET)
TICKS_PER_BPM120 = 1.0 / 112500                   # 1/96-beat ticks a block (32 samples) per BPM x 120
# The ColdFire's clock word: bit 31 playing, bits 0..11 the sequencer's place since PLAY in ticks of 1/96
# beat (a 16th of the pattern's own tempo = 24) modulo GT_WRAP (8 bars: every RATE's 16 steps divide it).
# The pass acts only on a word that changed since the slot last looked: playing, it puts the phase there
# when it is more than GT_TOL_TICKS off; 0 (or a word with bit 31 clear): the phase runs on from the
# tempo (Optimist's stopped behaviour). 2026-11-10, two slots: the values fill 0xf18..0x1000, so the
# clock word is the values' word 1 (GEN + 4, until now sent as zero by ins.c ins_words; ports3 had it at
# 0xf7c, now inside PACK). No ColdFire writes it yet: GATER runs from the tempo.
CLK_OFFSET = GEN_OFFSET + 4
CLK = POOL_DDR + CLK_OFFSET
GT_WRAP = 3072
assert all(GT_WRAP % (16 * d) == 0 for d in GT_RATE)
assert GEN_OFFSET < CLK_OFFSET < PACK_OFFSET

# -- after the pan: the voice in stereo (dnfw.inserts.post). Each voice slot's stereo block, as the
# stock voice chain leaves it for the FX sends (sw 0x1c1738) and the routing (0x1c1f1e): L 32 floats at
# STEREO + 0x100 s, R at + 0x80 (byte addresses; docs/inserts.md "After the pan")
STEREO = 0x257EE8
STEREO_STRIDE = 0x100
STEREO_R = 0x80
POST_RING = 1024                                  # samples a voice slot (21.3 ms), CHOR's or WIDE's
POST_RING_DDR = 0x82510000                        # 32 x (4 KB + 16), after TAPE's rings (post.py: mirror words, then the ring)
POST_RING_STRIDE = 4 * POST_RING + 16             # perf 2026-11-11: CHOR's second tap of a read at the ring's first word;
POST_MIRROR = 3                                   # 2026-11-12: three mirror words of the ring's last (JUNO's 4-point reads)
assert MV_RING_DDR >= POST_RING_DDR + RECORDS * POST_RING_STRIDE    # a moved TAPE's rings after them

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

# JUNO (2026-11-12, the User): Optimist's JUNO CHORUS (firmware/src/fx/junocho/juno_cho.h, GPL-3.0-only: fm-106's
# model of the Juno-106's MN3009 BBD chorus, after KR-106). K1 MODE (I / II / I+II, thirds of 0..127), MIX the
# dry / Juno blend as Optimist's (MIX 127: dry x 0.863 + taps x 1.257). The mid into one line; two taps in antiphase
# around 3.5 ms moved by a triangle LFO, each read by 4-point Hermite and low-passed (the BBD's 2nd-order Butterworth),
# out L = l gd + tap L gw, R = r gd + tap R gw. Optimist runs at 44.1 kHz in Q15: its integers, as times and Hz, here
# at 48 kHz (juno_consts). The triangle is taken at the block's ends and moved linearly across it (exact but in a
# block holding a corner of it).
JN_FS0 = 44100                                    # Optimist's rate
JN_BASE0 = 154                                    # its taps' centre, d (16.16 >> 16); a read is 1 + d samples back
JN_DEPTH0 = (94, 75, 10)                          # x the triangle (-32768 .. 32766) >> 16: +-47 / 37.5 / 5 samples
JN_INC0 = (50098, 82068, 765109)                  # the triangle's phase step a sample, of 2^32 (0.514 / 0.843 / 7.86 Hz)
JN_LP0 = (27066, 11534, 9527)                     # the low-pass's g, a1, a2 (Q15; 2nd-order Butterworth, ~9.7 kHz)
JN_GD, JN_GW = 21209 / 32768, 30892 / 32768       # MIX 127's dry and taps' gains (the Juno's IC6 summer)
JN_MODES = 3
JN_MODE_K = JN_MODES * 127 / 128                  # MODE = trunc(K1 / 127 x this): 0..42 I, 43..85 II, 86..127 I+II


def juno_consts(fs: float = FS) -> dict:
    """Optimist's integers as times and Hz, at FS: base (the taps' centre: a read 1 + base samples back), dep[mode]
    (samples a unit of the triangle, -32768 .. 32766), inc[mode] (the phase step a sample, of 2^32), g, a1, a2 (the
    low-pass: g = tan(pi fc / fs), its fc and damping those Optimist's Q15 values hold at 44.1 kHz)"""
    k = fs / JN_FS0
    g0, a10 = JN_LP0[0] / 32768, JN_LP0[1] / 32768
    wc = math.atan(g0) * JN_FS0                   # pi fc
    damp = (1 / a10 - 1) / g0 - g0                # a1 = 1 / (1 + g (g + damp))
    g = math.tan(wc / fs)
    a1 = 1 / (1 + g * (g + damp))
    if fs == JN_FS0:                              # (at Optimist's own rate: its very values)
        g, a1, a2 = g0, a10, JN_LP0[2] / 32768
    else:
        a2 = g * a1
    return {"base": (1 + JN_BASE0) * k - 1, "dep": tuple(d * k / 65536 for d in JN_DEPTH0),
            "inc": tuple(round(i / k) for i in JN_INC0), "g": g, "a1": a1, "a2": a2}


JN = juno_consts()

# the chorus SEND's TYPE JUNO (dnfw.inserts.jsend, docs/inserts.md "The chorus send"): TYPE the send pages' twelfth
# word (csrc/fxpage fxp_words w[11], sent by link.c at 0xED0 + 44; 0 until sent: STOCK); MIX and MODE the chorus
# page's DPTH and SPD, kit slots 25 and 26 in the DSP's frame image (0x25c48c + 0x9c8 + 2 k: 0x9fa the high half of
# 0x25ce84, 0x9fc the low half of 0x25ce88), 8.8 (knob x 256); its state words and ring in DDR after the moved TAPE rings
JS_TYPE = POOL_DDR + 0xED0 + 4 * 11
JS_STOCK, JS_JUNO = 0, 1
JS_DPTH_WORD, JS_SPD_WORD = 0x25CE84, 0x25CE88
JS_KNOB_K = 1.0 / (127 * 256)
JS_STATE = 0x82550000                             # 8 words: s0..s5, the last TYPE run (then 8 spare)
JS_RING = JS_STATE + 0x40 + 4 * POST_MIRROR       # 1,024 floats, three mirror words before them
JS_END = JS_RING + 4 * POST_RING
assert JS_STATE >= MV_RING_DDR + MV_INSTANCES * 2048 and JS_END <= 0x82800000   # (FDN8_RING_DDR, below)
assert JN["base"] - JN["dep"][0] * 32768 - 3 >= BLOCK    # every read is of an earlier block's samples
assert JN["base"] + JN["dep"][0] * 32768 + 3 < POST_RING - BLOCK


def pack(table: bytes | list[int], gen: int) -> list[int]:
    """the 2 + 56 words the ColdFire sends from GEN_OFFSET (csrc/inserts/ins.c ins_words): the change
    word, a zero (CLK, GATER's clock word: no ColdFire writes it yet), then each group g of 4 records (fields n = 0..31, record 4 g + n // 8, field n % 8):
    word w holds fields 4w .. 4w+3 in its bits 0..27 (7 each); fields 28..31 are X = the words' top
    nibbles (word w's at bit 4w), field 28 + m = X >> 7m. Values past 127 are cut to 7 bits."""
    v = [int(x) & 0x7F for x in table]
    assert len(v) == RECORDS * FIELDS
    out = [gen & 0xFFFFFFFF, 0]
    for g in range(RECORDS * FIELDS // 32):
        f = v[32 * g:32 * g + 32]
        x = f[28] | f[29] << 7 | f[30] << 14 | f[31] << 21
        for w in range(7):
            out.append(f[4 * w] | f[4 * w + 1] << 7 | f[4 * w + 2] << 14 | f[4 * w + 3] << 21
                       | ((x >> 4 * w) & 0xF) << 28)
    return out


def records(par1: bytes, par2: bytes | None = None) -> bytes:
    """slot 1's 16 records (8 bytes a track, as the one-slot layout was) and slot 2's -> the 32 records
    (track t's slot j at 8 (2 t + j))"""
    out = bytearray(8 * RECORDS)
    for j, src in enumerate((par1, par2 or bytes(8 * TRACKS))):
        for t in range(TRACKS):
            out[8 * (2 * t + j):8 * (2 * t + j) + 8] = src[8 * t:8 * t + 8]
    return bytes(out)


def unpack(words: list[int]) -> list[int]:
    """pack's inverse (the DSP's unpack, dnfw.inserts.program): 56 words -> 256 fields"""
    out = []
    for g in range(len(words) // 7):
        x = 0
        for w in range(7):
            a = words[7 * g + w]
            out += [a & 0x7F, (a >> 7) & 0x7F, (a >> 14) & 0x7F, (a >> 21) & 0x7F]
            x = (x >> 4) | (a >> 28) << 24
        out += [x & 0x7F, (x >> 7) & 0x7F, (x >> 14) & 0x7F, (x >> 21) & 0x7F]
    return out


# -- the bus inserts (dnfw.inserts.bus): FDN8 and XDLY per track, on the routing's per-track bus.
# Instances (the User, 2026-11-10: as many as memory allows, never at the voices' cost): each in its
# own DDR, given to a slot by the ColdFire for as long as the slot keeps the type
FDN8_INSTANCES = 8
FDN8_RING_DDR, FDN8_RING_STRIDE = 0x82800000, 0x80000      # 8 x 512 KB (aligned to its size: the ring's mask)
XDLY_INSTANCES = 4
XDLY_LINES_DDR, XDLY_LINES_STRIDE = 0x83000000, 0x400000   # 4 x 4 MB: two lines of 2^19 floats (10.9 s)
assert FDN8_RING_DDR + FDN8_INSTANCES * FDN8_RING_STRIDE <= XDLY_LINES_DDR
assert XDLY_LINES_DDR + XDLY_INSTANCES * XDLY_LINES_STRIDE <= POOL_DDR

# -- the guard (dnfw.perc.guard, "the inserts never cost a voice"): an insert runs in a block only if
# it is expected to end before the frame's insert deadline; the bounds are the runner's cost of one
# unit (docs/inserts.md) x 1.5, x 2 for the DDR-heavy (DDR's cost on the unit is unmeasured)
COST = {FUZZ: 5_700, TAPE: 8_200, FOLD: 6_300, HARM: 4_700, CHOR: 13_000, WIDE: 4_700,
        # FDN8 (2026-11-12, opt-inserts): 32,000 until then, under its own cost: a fresh instance clears its
        # 512 KB ring for 32 blocks, 4,096 DDR writes each (FDN8_MEASURED). The bound must never be under a
        # block's cost, or the guard lets it run past the deadline: 1.2 x the clearing block
        FDN8: 64_000, XDLY: 20_000,
        # SUB DIST GATER RING (2026-11-10, ins47): not run on the runner yet, so the model's steps of one
        # unit (2,143 / 2,946 / 1,610 / 1,836) x 1.2 (the runner read up to 20 % over the model) x 1.5
        SUB: 3_900, DIST: 5_400, GATER: 2_900, RING: 3_400,
        # JUNO (2026-11-12): the runner's 3,530 a voice slot (16 slots 58,926 less 1 slot 5,931, / 15) x 2 (DDR-heavy:
        # eight ring reads and a write a sample)
        JUNO: 7_100}
# FDN8's cost a block as a bus insert, the model on the shared scale (instructions + 4 L2 + 10 DDR accesses,
# docs/dsp-cost.md), one instance less the pass with none: a clearing block (its first 32) and a steady one.
# test_inserts_bus measures the clearing block again and holds COST[FDN8] >= 1.2 x it
FDN8_MEASURED = {"clearing": 53_073, "steady": 32_606}
assert COST[FDN8] >= 1.2 * max(FDN8_MEASURED.values())
