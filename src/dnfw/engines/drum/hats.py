"""DRUM's CLOSED and OPEN HAT in the DSL: dnfw.engines.drum.ref.Hat, operation for operation (its exp2 PERC's, which
the reference copies, so the squares' increments and so their edges are the same to the bit; test/test_drum.py holds
the two within DSL_TOL_DB).

A hit's values are set in the first half after the trig (`hit`, the note is the render's); each half an OPEN voice
looks at its track's choke word (`half`); then 16 samples a half (`sample`): six squares on the 808's six (32-bit
phases, one signed compare a square), the ring-modulated pairs, metal against noise, the band-pass (stmlib's SVF),
the soft clip at gain g with its level held (the type's level in it), the high-pass, the 808's low band, the VCA with
the strike, the retrig's declick, the output held under 0.99. No DC blocker: the band-pass, the high-pass and the low band pass no DC.

THE CHOKE (the User, 2026-11-20): a CLOSED hit writes PERC's block clock (dnfw.perc.program CLOCK_OFF, one more every
block) into its track's word (CHOKE_OFF, 16 words in the Monomachine L2 scratch, the track from the stock's slot map
ROUTE); an OPEN hit keeps the word (S_SEEN) and the clock (S_HIT), and its voice looks each half: the word moved (a
CLOSED hit since), or the word was this very block at the hit (a CLOSED hit earlier in the OPEN's own block) and the
block is over, and its envelope falls in 3 ms (ref.HAT_CHOKE_TAU; ref.choke_block). Voices are rendered the newest
first, so a CLOSED hit chokes the older OPEN voices of its track in the block of its trig. A CLOSED and an OPEN hit in
ONE block (the User: the OPEN is always choked, whatever the slots' render order): from the next block, both orders
(the OPEN rendered first sees the word move then; rendered second, it saw the word at its own block).

State words: DRUM's shared ones (kick.py's numbers) stay common; the rest are KICK's / SNARE's type-specific words
reused (each hat hit sets every word a hat reads), but the drift's walk and the jitter's generator (P_DRIFT, P_JRNG:
words no other type touches, kept from hit to hit as drum_v3's).

STAGE 3 (2026-11-20, drum_v3 Hat3; ref.Hat): the VCA through the swing VCA's diode knee (e: CLOSED from E0 falling
exponentially; OPEN rising in 6 ms, flat for its hold, then a line; xt of an exponential tail at long DCAY; the choke
falls both in 3 ms), the VCA before the high-pass, TOP (a first-difference pre-emphasis, the band toward its
high-pass), DRFT (each half a jitter draw a square, every 16 halves the drift's walk: the squares' increments from
their float words, trunc(inc0 ((1 + drift) + jitter)), the same arithmetic as the reference so the edges agree).
"""

from __future__ import annotations

import math

from ...md import core as MK
from ...mnm import core as C
from ...perc.dsl import Prog
from ..plaits import plaits_drumkit as PD
from ..plaits import plk as K
from . import dmath as M
from . import kick as KI
from . import ref as R
from . import snare as SN
from .dmath import addk, ld, mulk, sv

FS = R.FS
S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG = KI.S_TRIG, KI.S_ON, KI.S_TYPE, KI.S_NOTE, KI.S_RNG
S_UP, S_DC2, S_LAST, S_DK = KI.S_UP, KI.S_DC2, KI.S_LAST, KI.S_DK
SHARED = SN.SHARED

S_PH = (5, 6, 7, 8, 9, 10)                     # the squares' phases (int: the turn x 2^32, offset by half a turn)
S_EX, S_HN, D_HOLDN, D_S1, D_MX, D_XT = 11, 12, 13, 14, 15, 17     # stage 3: the VCA's (S_HN: samples since the hit)
B_SVF, H_SVF, L_SVF = 21, 26, 31               # stmlib Svf words g r h s1 s2: the band, the high-pass, the low band
(S_E, D_M, S_SNAP, D_RING, D_MIX, D_OMM, D_G2, D_COMP, D_LOWB, S_SEEN, D_CHKA, T_X, T_Y, T_VM, T_TR, T_TONE,
 T_FC, T_GAIN, T_Q, D_KA, D_KB, S_HIT) = range(36, 58)
D_E0, D_TOPA, D_BPG, D_HPG, S_X1, D_DSTEP = range(58, 64)
D_INC = tuple(range(64, 70))                   # the squares' increments this half (int)
D_INC0 = tuple(range(70, 76))                  # before DRFT (float: the word x 2^32 before its trunc)
D_JIT = tuple(range(76, 82))                   # each one's jitter amount (DRFT)
P_DRIFT = tuple(range(89, 95))                 # the drift's walk (kept from hit to hit)
P_JRNG = 95                                    # the jitter's generator (seeded at the machine's init)
WORDS = 96
_OWN = (S_PH + (S_EX, S_HN, D_HOLDN, D_S1, D_MX, D_XT) + tuple(range(B_SVF, L_SVF + 5)) + tuple(range(S_E, 82))
        + P_DRIFT + (P_JRNG,))
assert len(set(_OWN)) == len(_OWN) and not set(_OWN) & set(SHARED) and WORDS <= MK.NS
assert D_INC0[0] - D_INC[0] == 6 and D_JIT[0] - D_INC0[0] == 6

TUNE, DCAY, TONE, NOIS, COLR, SNAP, DRIV = range(7)            # page 1 A..G
HPF, Q, LOWB, VEL, TOP, DRFT = range(6)                        # page 2 (q0..q5)
CLHH, OPHH = 4, 5                                              # drum.CLHH, drum.OPHH (asserted there)

SNAP_D = float(R.tau_coef(R.HAT_SNAP_TAU))
CHOKE_D = float(R.tau_coef(R.HAT_CHOKE_TAU))
DK_D = KI.DK_D
ROUTE = 0x257898                               # 16 x s16: the track each voice slot plays (dnfw.inserts.design.ROUTE)
ONE_BITS, SIGN_BIT = 0x3F800000, 0x80000000    # +1.0; +1.0 less the sign bit's word is -1.0


def _inc(p: Prog, lg: float) -> None:
    """F4 = a square's increment as a float: min(2^(warp LG) x f1 / FS x tr, 0.45) x 2^32, warp in T_X, tr in T_TR
    (ref.Hat.trig; its word is its trunc). Clobbers R0-R5, R12, I12."""
    p.fconst(2, lg)
    inc_f2(p)


def inc_f2(p: Prog) -> None:
    """F4 = a square's increment (_inc) for its octaves over the first in F2 (stage 4: the cymbal's, from its SET).
    Clobbers R0-R5, R12, I12."""
    def body():
        ld(p, 3, T_X)
        p.fop(2, 3, "*", 2)
        K.exp2p(p, 4, 2)
        mulk(p, 4, 4, R.HAT_BASE)
        ld(p, 5, T_TR)
        p.fop(4, 4, "*", 5)
        p.fconst(12, R.HAT_INC_TOP)
        p.fop(4, 4, "MIN", 12)
        mulk(p, 4, 4, 2.0 ** 32)
    p.call("dr_hinc", body)


def colr(p: Prog) -> None:
    """COLR (page 1 E, the hats' and the cymbal's): T_X = warp = 1 + (min(c / 0.7, 1) - 0.5) 0.8 (the ratios r^warp),
    D_RING = ring = max((c - 0.7) / 0.3, 0); one copy (a leaf, stage 4). Clobbers R2, R3, R12, I12."""
    def body():
        KI._u(p, 2, COLR)
        mulk(p, 3, 2, 1.0 / 0.7)
        p.fconst(12, 1.0)
        p.fop(3, 3, "MIN", 12)
        addk(p, 3, 3, -0.5)
        mulk(p, 3, 3, 0.8)
        addk(p, 3, 3, 1.0)
        sv(p, T_X, 3)
        addk(p, 2, 2, -0.7)
        mulk(p, 2, 2, 1.0 / 0.3)
        p.fconst(12, 0.0)
        p.fop(2, 2, "MAX", 12)
        sv(p, D_RING, 2)
    p.call("dr_colr", body)


def _choke_word(p: Prog, L) -> None:
    """D_CHKA = the address of this slot's track's choke word, R4 = the word, I1 at it. Clobbers R1-R4, R9, R12."""
    from ...perc import program as PP          # (lazy: program imports the machines)
    p.ld(9, L.perc.C["t"])                     # the voice slot
    p.lsh(1, 9, -1)
    p.lsh(1, 1, 2)
    p.iconst(12, ROUTE)
    p.iop(2, 12, "+", 1)
    p.seti(1, 2)
    p.ldi(3, 0, 1)                             # the slot pair's word: even slot low half, odd high
    p.iconst(12, 1)
    p.iop(1, 9, "AND", 12)
    p.ifz(1, "NE", lambda: p.lsh(3, 3, -16))
    p.iconst(12, 15)
    p.iop(3, 3, "AND", 12)                     # the track, 0..15
    p.lsh(3, 3, 2)
    p.iconst(12, L.scratch + PP.CHOKE_OFF)
    p.iop(3, 12, "+", 3)
    sv(p, D_CHKA, 3)
    p.seti(1, 3)
    p.ldi(4, 0, 1)


def hit_rest(p: Prog, L) -> None:
    """The hit's values (ref.Hat.trig) after the metal's (stage 4: cymbal.metal_hit, the hats' and the cymbal's one
    copy: vm, the pitch, COLR, the squares' increments and phases, NOIS's mix; then this; then DRFT and the declick).
    Clobbers R0-R15, I1, I12."""
    # the type: its decay's span, its level
    ld(p, 0, S_TYPE)
    p.iconst(1, OPHH)

    def span(t: int):
        lo, hi = R.HAT_T60[t]
        p.fconst(10, math.log2(hi / lo))
        p.fconst(11, lo * FS)
        p.fconst(14, R.HAT_GAIN[t])
    p.if_(0, "EQ", 1, lambda: span(1), lambda: span(0), kind="i")
    sv(p, T_GAIN, 14)
    sv(p, T_FC, 10)
    sv(p, T_TONE, 11)
    # the level held: x 1 / ((1 + SNAP) (1 + 1.5 LOWB) (1 + 0.5 ring)) (ref.Hat.trig, HAT_*_HOLD)
    KI._u(p, 2, SNAP)
    mulk(p, 2, 2, R.HAT_SNAP_HOLD)
    addk(p, 2, 2, 1.0)
    KI._q(p, L, 3, LOWB)
    mulk(p, 3, 3, R.HAT_LOWB_HOLD)
    addk(p, 3, 3, 1.0)
    p.fop(4, 2, "*", 3)
    ld(p, 3, D_RING)
    mulk(p, 3, 3, R.HAT_RING_HOLD)
    addk(p, 3, 3, 1.0)
    p.fop(4, 4, "*", 3)
    from ...perc import machines as PM
    PM.recip(p, 5, 4)
    ld(p, 14, T_GAIN)
    p.fop(14, 14, "*", 5)
    sv(p, T_GAIN, 14)
    ld(p, 10, T_FC)
    ld(p, 11, T_TONE)
    # DCAY: T60 = lo (hi / lo)^DCAY (samples, T_X); the VCA (stage 3, ref.Hat.trig): e0 = 4 (0.6 + 0.4 vm)
    KI._u(p, 2, DCAY)
    p.fop(13, 2, "*", 10)
    sv(p, T_X, 11)
    M.exp2(p, 3, 13)
    ld(p, 11, T_X)
    p.fop(3, 3, "*", 11)
    sv(p, T_X, 3)
    ld(p, 2, T_VM)
    mulk(p, 2, 2, 0.4)
    addk(p, 2, 2, 0.6)
    mulk(p, 2, 2, R.E0_TOP)
    sv(p, D_E0, 2)
    # (DCAY's envelope, `vca`: per hit, a choke keeps its words; in the hit's state at the end, T_X kept till there)
    # SNAP: the strike 0 .. 2 x (0.5 + 0.5 vm)
    # TONE: the band at 7.1 kHz x 2^((TONE - 0.5) 3) x 2^((vm - 1) / 2), Q 0.8 .. 8; the high-pass at it x 0.4 .. 1.4,
    # Q 0.75; the low band at 3.44 kHz x 2^((TONE - 0.5) 3), Q 1.5
    KI._u(p, 2, TONE)
    addk(p, 2, 2, -0.5)
    mulk(p, 2, 2, 3.0)
    M.exp2(p, 3, 2)
    sv(p, T_TONE, 3)
    ld(p, 2, T_VM)
    addk(p, 2, 2, -1.0)
    mulk(p, 2, 2, 0.5)
    M.exp2(p, 4, 2)
    ld(p, 3, T_TONE)
    p.fop(4, 4, "*", 3)
    mulk(p, 4, 4, R.HAT_BAND_HZ)
    sv(p, T_FC, 4)
    KI._q(p, L, 2, Q)
    KI._expo(p, 9, 2, 0.8, 8.0)
    sv(p, T_Q, 9)
    p.sti(1, 4, 9)                               # (svf_sets' inputs at I4: 2026-11-21, live knobs)
    ld(p, 4, T_FC)
    p.fconst(12, R.SVF_TOP_HZ)
    p.fop(4, 4, "MIN", 12)
    p.sti(0, 4, 4)
    KI._q(p, L, 2, HPF)
    KI._expo(p, 3, 2, 0.4, 1.4)
    p.ldi(4, 0, 4)
    p.fop(4, 3, "*", 4)
    p.sti(2, 4, 4)
    ld(p, 4, T_TONE)
    mulk(p, 4, 4, R.HAT_LOWB_HZ)
    p.sti(4, 4, 4)
    p.fconst(4, R.HAT_HP_Q)
    p.sti(3, 4, 4)
    p.fconst(4, R.HAT_LOWB_Q)
    p.sti(5, 4, 4)
    assert (H_SVF, L_SVF) == (B_SVF + 5, B_SVF + 10)
    SN.svf_sets(p, L, B_SVF, 3, R.SVF_TOP_HZ)
    # LOWB: 0 .. 2 x the type's level
    KI._q(p, L, 2, LOWB)
    p.fop(2, 2, "+", 2)
    ld(p, 3, T_GAIN)
    p.fop(2, 2, "*", 3)
    sv(p, D_LOWB, 2)
    # DRIV: g = 1 + 20 DRIV^2 (the band x 2 into it: 2 g), its level held (KICK's, at g x max(Q / Q0, 1)) x the type's
    # level
    def held():                                  # the clip's level held at g x max(Q / Q0, 1)
        ld(p, 3, T_Q)
        mulk(p, 3, 3, 1.0 / R.HAT_Q0)
        p.fconst(12, 1.0)
        p.fop(3, 3, "MAX", 12)
        p.fop(2, 2, "*", 3)
    KI.drive_level(p, DRIV, 20.0, D_G2, D_COMP, scale=held)
    ld(p, 2, D_G2)
    p.fop(2, 2, "+", 2)
    sv(p, D_G2, 2)
    ld(p, 2, D_COMP)
    ld(p, 3, T_GAIN)
    p.fop(2, 2, "*", 3)
    sv(p, D_COMP, 2)
    top_drft(p, L)
    # the hit's state (2026-11-21, live knobs: not on a re-read, dmath.on_hit): the VCA (DCAY), SNAP's strike, TOP's
    # last input; the choke: CLOSED writes the block clock into its track's word, OPEN keeps the word and the clock
    def choke():
        vca(p, L)
        KI._u(p, 2, SNAP)
        p.fop(2, 2, "+", 2)
        ld(p, 3, T_VM)
        mulk(p, 3, 3, 0.5)
        addk(p, 3, 3, 0.5)
        p.fop(2, 2, "*", 3)
        sv(p, S_SNAP, 2)
        p.fconst(0, 0.0)
        sv(p, S_X1, 0)
        _choke_word(p, L)
        from ...perc import program as PP          # (lazy: program imports the machines)
        p.ld(5, L.scratch + PP.CLOCK_OFF)
        ld(p, 0, S_TYPE)
        p.iconst(1, OPHH)
        p.if_(0, "EQ", 1, lambda: (sv(p, S_SEEN, 4), sv(p, S_HIT, 5)), lambda: p.sti(0, 1, 5), kind="i")
    M.on_hit(p, choke)


def vca(p: Prog, L) -> None:
    """The VCA's words (ref.Hat.trig), DCAY's T60 (samples) in T_X, e0 in D_E0, DCAY's 0..1 in F2... recomputed: OPEN:
    e 0, the hold trunc(0.234 T60), the line's step e0 / (0.546 T60), the exponential tail's e^(-ln 1000 / (EXP_T60
    T60)) and its share xt = clamp((DCAY - X0) / (X1 - X0), 0, 1); CLOSED: e e0, no hold, e^(-1 / (0.43 T60)), no
    step, no tail. Clobbers R0-R5, R12-R15, I12."""
    p.iconst(0, 0)
    sv(p, S_HN, 0)
    p.fconst(0, 0.0)
    sv(p, S_EX, 0)
    ld(p, 0, S_TYPE)
    p.iconst(1, OPHH)

    def open_():
        p.fconst(2, 0.0)
        sv(p, S_E, 2)
        ld(p, 3, T_X)
        mulk(p, 2, 3, R.OP_HOLD * R.OP_LEN)
        p.trunc(2, 2)
        sv(p, D_HOLDN, 2)
        p.fconst(2, 1.0)
        sv(p, D_M, 2)
        mulk(p, 2, 3, (1.0 - R.OP_HOLD) * R.OP_LEN)
        from ...perc import machines as PM
        PM.recip(p, 4, 2)
        ld(p, 2, D_E0)
        p.fop(4, 2, "*", 4)
        sv(p, D_S1, 4)
        ld(p, 3, T_X)
        mulk(p, 3, 3, R.EXP_T60)
        KI._coef(p, D_MX, 3, -R.LN_THOUSAND)
        KI._u(p, 2, DCAY)
        addk(p, 2, 2, -R.OPEN_X0)
        mulk(p, 2, 2, 1.0 / (R.OPEN_X1 - R.OPEN_X0))
        K.clamp(p, 2, 0.0, 1.0)
        sv(p, D_XT, 2)

    def closed():
        ld(p, 2, D_E0)
        sv(p, S_E, 2)
        p.iconst(2, 0)
        sv(p, D_HOLDN, 2)
        ld(p, 3, T_X)
        mulk(p, 3, 3, R.CL_TAU)
        KI._coef(p, D_M, 3, -1.0)
        p.fconst(2, 0.0)
        sv(p, D_S1, 2)
        sv(p, D_XT, 2)
        p.fconst(2, 1.0)
        sv(p, D_MX, 2)
    p.if_(0, "EQ", 1, open_, closed, kind="i")


def top_drft(p: Prog, L) -> None:
    """TOP (the pre-emphasis 1.5 TOP, the band's shares 1 - TOP and TOP) and DRFT (dr = DRFT x 127 / 64: the drift's
    step 2.5e-4 dr; each square's jitter JIT dr / sqrt(16 a), a its increment / 2^32, by log2 and exp2 as the
    reference). Clobbers R0-R15, I1, I12, n4."""
    KI._q(p, L, 2, TOP)
    sv(p, D_HPG, 2)
    mulk(p, 3, 2, R.TOP_EMPH)
    sv(p, D_TOPA, 3)
    p.fconst(12, 1.0)
    p.fop(3, 12, "-", 2)
    sv(p, D_BPG, 3)


def drft_hit(p: Prog, L) -> None:
    """DRFT at a hit (page 2 F, the hats' and the cymbal's): the drift's step, each square's jitter. Clobbers R0-R15,
    I1, I12, n4."""
    KI._q(p, L, 2, DRFT)
    mulk(p, 2, 2, 127.0 / 64.0)                  # dr
    mulk(p, 3, 2, R.DRIFT_STEP)
    sv(p, D_DSTEP, 3)
    mulk(p, 2, 2, R.JIT)                         # jd
    sv(p, T_Y, 2)
    SN._ptr(p, D_JIT[0])

    def one():
        p.ldi(8, D_INC0[0] - D_JIT[0], 1)
        mulk(p, 8, 8, 16.0 / 2.0 ** 32)
        p.fconst(12, 16.0 / FS)
        p.fop(8, 8, "MAX", 12)
        M.log2(p)                                # F9
        mulk(p, 13, 9, -0.5)
        M.exp2(p, 4, 13)
        ld(p, 2, T_Y)
        p.fop(4, 4, "*", 2)
        p.stpost(1, 4)
    p.loop(L.W["n4"], 6, one)


def half(p: Prog, L) -> None:
    """Each half before its samples. An OPEN voice: its track's choke word moved since its hit, or it was the hit's
    own block and that block is over (ref.choke_block), and its VCA falls in 3 ms (ref.Hat.choke: no hold, e and the
    tail by CHOKE_D, no step). Then DRFT (ref.Hat.half): every 16 halves the drift's walk, (drift + step r) x 0.98 a
    square; each half a jitter draw a square, the increment trunc(inc0 ((1 + drift) + jit r)). Clobbers R0-R15, I1,
    I12, n4."""
    from ...perc import program as PP          # (lazy: program imports the machines)
    ld(p, 0, S_TYPE)
    p.iconst(1, OPHH)

    def look():
        def choke():
            p.iconst(0, 0)
            sv(p, D_HOLDN, 0)
            p.fconst(0, CHOKE_D)
            sv(p, D_M, 0)
            sv(p, D_MX, 0)
            p.fconst(0, 0.0)
            sv(p, D_S1, 0)

        def same_block():                      # the word unmoved: a CLOSED hit in the hit's block, before it?
            ld(p, 1, S_HIT)
            p.if_(3, "EQ", 1, lambda: (p.ld(0, L.scratch + PP.CLOCK_OFF), p.if_(0, "NE", 1, choke, kind="i")),
                  kind="i")
        ld(p, 1, D_CHKA)
        p.seti(1, 1)
        p.ldi(2, 0, 1)
        ld(p, 3, S_SEEN)
        p.if_(2, "NE", 3, choke, same_block, kind="i")
    p.if_(0, "EQ", 1, look, kind="i")
    drft(p, L)


def drft(p: Prog, L) -> None:
    """DRFT each half (the hats' and the cymbal's: one copy, a leaf, stage 4): the drift's walk every 16 halves, a
    jitter draw a square, the increments from their float words (Hat.half). Clobbers R0, R1, R9-R14, I1, I12, n4."""
    p.call("dr_drft", lambda: _drft_body(p, L))


def _drft_body(p: Prog, L) -> None:
    # DRFT: the drift's walk every 16 halves (S_HN a multiple of 256)
    ld(p, 0, S_HN)
    p.iconst(12, R.HALF * R.DRIFT_HALVES - 1)
    p.iop(0, 0, "AND", 12)

    def walk():
        SN._ptr(p, P_DRIFT[0])

        def one():
            M.noise(p, 9, P_JRNG)
            ld(p, 10, D_DSTEP)
            p.fop(9, 10, "*", 9)
            p.ldi(10, 0, 1)
            p.fop(10, 10, "+", 9)
            mulk(p, 10, 10, R.DRIFT_LEAK)
            p.stpost(1, 10)
        p.loop(L.W["n4"], 6, one)
    p.ifz(0, "EQ", walk)
    SN._ptr(p, D_INC0[0])

    def jitter():
        M.noise(p, 9, P_JRNG)
        p.ldi(10, D_JIT[0] - D_INC0[0], 1)
        p.fop(9, 10, "*", 9)                     # j
        p.ldi(10, P_DRIFT[0] - D_INC0[0], 1)
        addk(p, 10, 10, 1.0)
        p.fop(10, 10, "+", 9)
        p.ldi(11, 0, 1)
        p.fop(10, 11, "*", 10)
        p.trunc(10, 10)
        p.sti(D_INC[0] - D_INC0[0], 1, 10)
        p.geti(13, 1)
        p.iconst(12, 4)
        p.iop(13, 12, "+", 13)
        p.seti(1, 13)
    p.loop(L.W["n4"], 6, jitter)


def knee(p: Prog, d: int, e: int) -> None:
    """Fd = the diode's knee at Fe x 1 / knee(E0_TOP) (ref.knee, IK0): o = max(e - V, 0), k = min(o, W),
    k^2 / 2W + (o - k). Clobbers R12-R14."""
    addk(p, 13, e, -R.KNEE_V)
    p.fconst(12, 0.0)
    p.fop(13, 13, "MAX", 12)                     # o
    p.fconst(12, R.KNEE_W)
    p.fop(14, 13, "MIN", 12)                     # k
    p.fop(13, 13, "-", 14)
    p.fop(14, 14, "*", 14)
    mulk(p, 14, 14, 1.0 / (2.0 * R.KNEE_W))
    p.fop(d, 14, "+", 13)
    mulk(p, d, d, R.IK0)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Hat.sample). Clobbers R0-R15, I1, I12."""
    metal(p)
    _after_metal(p, L)


def metal(p: Prog) -> None:
    """F8 = x (T_X too), the metal and the noise (the hats' and the cymbal's: one copy, a leaf, stage 4); F9 = the
    noise's own sample. Clobbers R0-R14, I12."""
    p.call("dr_metal", lambda: _metal_body(p))


def _metal_body(p: Prog) -> None:
    # the six squares: phase += inc (wrapping), +1 under the duty's word, -1 above (F0..F5)
    p.iconst(6, R.HAT_T & 0xFFFFFFFF)
    p.iconst(7, SIGN_BIT)
    for i in range(6):
        ld(p, 8, S_PH[i])
        ld(p, 9, D_INC[i])
        p.iop(8, 8, "+", 9)
        sv(p, S_PH[i], 8)
        p.iconst(i, ONE_BITS)
        p.comp_iop_if(8, 6, "GE", i, i, "-", 7)
    # metal: their mean, toward the ring-modulated pairs' by RING
    p.fop(10, 0, "+", 1)
    for i in range(2, 6):
        p.fop(10, 10, "+", i)
    p.fop(11, 0, "*", 1)
    p.fop(13, 2, "*", 3)
    p.fop(11, 11, "+", 13)
    p.fop(13, 4, "*", 5)
    p.fop(11, 11, "+", 13)
    # x = (the squares' sum KA + the pairs' sum KB) + noise NOIS
    ld(p, 13, D_KA)
    p.fop(10, 10, "*", 13)
    ld(p, 13, D_KB)
    p.fop(11, 11, "*", 13)
    p.fop(10, 10, "+", 11)
    sv(p, T_Y, 10)
    M.noise(p, 9, S_RNG)
    ld(p, 11, D_MIX)
    p.fop(11, 9, "*", 11)
    ld(p, 10, T_Y)
    p.fop(8, 10, "+", 11)
    sv(p, T_X, 8)


def _after_metal(p: Prog, L) -> None:
    # TOP: pre = x + 1.5 TOP (x - x1)
    ld(p, 9, S_X1)
    sv(p, S_X1, 8)
    p.fop(9, 8, "-", 9)
    ld(p, 10, D_TOPA)
    p.fop(9, 10, "*", 9)
    p.fop(8, 8, "+", 9)
    # the band (toward its high-pass by TOP); the soft clip at 2 g, its level held
    SN._ptr(p, B_SVF)
    PD.svf(p)                                    # F9 hp, F10 bp
    ld(p, 11, D_HPG)
    p.fop(9, 9, "*", 11)
    ld(p, 11, D_BPG)
    p.fop(10, 10, "*", 11)
    p.fop(10, 10, "+", 9)
    ld(p, 14, D_G2)
    p.fop(15, 10, "*", 14)
    PD.soft(p)
    ld(p, 14, D_COMP)
    p.fop(15, 15, "*", 14)
    sv(p, T_Y, 15)                               # y
    # the VCA (ref.Hat.gate): in the hold e rises to e0, after it e = max(e m - s1, 0); through the knee; the tail
    ld(p, 0, S_HN)
    ld(p, 1, D_HOLDN)
    ld(p, 5, S_E)

    def rise():
        ld(p, 6, D_E0)
        p.fop(6, 6, "-", 5)
        mulk(p, 6, 6, R.HAT_RISE)
        p.fop(5, 5, "+", 6)

    def fall():
        ld(p, 6, D_M)
        p.fop(5, 5, "*", 6)
        ld(p, 6, D_S1)
        p.fop(5, 5, "-", 6)
        p.fconst(12, 0.0)
        p.fop(5, 5, "MAX", 12)
    p.if_(0, "LT", 1, rise, fall, kind="i")
    sv(p, S_E, 5)
    knee(p, 6, 5)                                # F6 kn

    def ex_held():
        sv(p, S_EX, 6)

    def ex_fall():
        ld(p, 7, S_EX)
        ld(p, 8, D_MX)
        p.fop(7, 7, "*", 8)
        sv(p, S_EX, 7)
    p.if_(0, "LT", 1, ex_held, ex_fall, kind="i")
    ld(p, 7, S_EX)
    p.fop(7, 7, "-", 6)
    ld(p, 8, D_XT)
    p.fop(7, 7, "*", 8)
    p.fop(6, 6, "+", 7)                          # gate
    ld(p, 7, S_SNAP)
    p.fop(6, 6, "+", 7)                          # v = gate + snap
    p.fconst(12, SNAP_D)
    p.fop(7, 7, "*", 12)
    sv(p, S_SNAP, 7)
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    sv(p, S_HN, 0)
    sv(p, T_TR, 6)                               # (v)
    # the high-pass after the VCA (stage 3: the 808's order), the 808's low band of x x LOWB x v
    ld(p, 8, T_Y)
    p.fop(8, 8, "*", 6)
    SN._ptr(p, H_SVF)
    PD.svf(p)                                    # F9 hp
    sv(p, T_Y, 9)
    ld(p, 8, T_X)
    SN._ptr(p, L_SVF)
    PD.svf(p)                                    # F10 bp
    ld(p, 11, D_LOWB)
    p.fop(10, 10, "*", 11)
    ld(p, 11, T_TR)
    p.fop(10, 10, "*", 11)
    ld(p, 9, T_Y)
    p.fop(4, 9, "+", 10)
    # the declick; the output held under 0.99 (a noise burst's rare peak: ref.HAT_TOP)
    ld(p, 6, S_DK)
    p.fop(4, 4, "+", 6)
    p.fconst(12, DK_D)
    p.fop(6, 6, "*", 12)
    sv(p, S_DK, 6)
    from ...perc import program as PP            # 2026-11-20 (clip-inner): a word past the hold: the voice's clip
    K.fabs(p, 12, 4)
    p.fconst(6, R.HAT_TOP)
    PP.clip_flag(p, 12, "GT", 6, 6)
    K.clamp(p, 4, -R.HAT_TOP, R.HAT_TOP)
    sv(p, S_LAST, 4)
    p.stpost(4, 4)
