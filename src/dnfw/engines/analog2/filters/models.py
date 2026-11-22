# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG 2's five filter models in the DSL (dnfw.perc.dsl), ported from Optimist (GPL-3.0-only,
firmware/src/engines/analog/a2_models.c, and ANALOG 2's own SVF in eng_analog2.c: a2_k, a2_coef,
a2_knee, A2_SVF, a2_filter), for the filter machines (dnfw.engines.analog2.filters.program) and, later, the ANALOG 2
machine in PERC (THIRD-PARTY.md).

`dnfw.engines.analog2.filters.ref` spells out every operation in its order; this module only says where each value
lives. Both run at 44.1 kHz on floats where 1.0 is Optimist's 32768 (its "half scale").

**Units.** The cutoff in Optimist's CUT units, 0..127 (a2m_g's cut >> 8, fractional): 30 Hz x
2^(cut x log2(16000/30) / 127), at most 0.45 FS (one unit = 0.856 semitones). RES 0..127 likewise.

**The interface** (one half, 16 samples, in place): the caller fills the words of a `Ctx`:
`gs` (g at the half's start: the SVF only), `ge` (g at its end), `res`, `mode` (0..4: LP12 LP24
BP HP NOTCH, an integer), `model` (0..4: SVF LADR OTA DIOD MS20, an integer), `buf` (the 16
floats' address), `zp` (the address of the filter's 4 state words), and calls `half`. g comes from
`g_of` (the leaf `a2g`: cut -> tan(pi fc / FS)). `half` clobbers every R register, I0, I2, I3, I12
(and the leaves' I12). The state: 4 floats (the C's s[0], s[1], s[4], s[5]); zeros are rest; the
caller clears them when the model changes (the C's s[7]).

**Against the C** (ref.py's docstring has the list): a division is a reciprocal (a bit seed and
three Newton steps), tan and exp2 are polynomials, the SVF is float (its coefficients exact, not
SVF_G's Q12 table; the states' knees a Pade tanh, not softclip's table), the diode ladder's 4 x 4
system is solved by elimination per sample (Thomas) instead of a full inverse a segment, LADR/OTA
and DIOD and the SVF mix their outputs by table rows. Every model clamps its output to +-32 (the
C's A2M_OUT); the SVF's LP24 clamps its first stage's output to +-2 (the C clamps the second
stage's input).
"""

from __future__ import annotations

import math

from ....perc.dsl import Prog, f32

MODELS = ("SVF", "LADR", "OTA", "DIOD", "MS20")
SVF, LADR, OTA, DIOD, MS20 = range(5)
MODES = ("LP12", "LP24", "BP", "HP", "NOTCH")
N = 16                                    # samples a half (a DN2 block is two)
FS = 44100.0
OCT = 9.0590148                          # A2M_OCT, the C's literal (log2(16000 / 30) is 9.058894)
K_OCT = OCT / 127.0                       # octaves a CUT unit
W0H = 30.0 * math.pi / FS / 2.0           # half the angle of 30 Hz
UMAX = 0.45 * math.pi / 2.0               # half the angle of 0.45 FS
OUT_MAX = 32.0                            # A2M_OUT's bound
LP24_MAX = 2.0                            # a2_lp2's input clamp (65536 / 32768)
K2ND = 5793.0 / 4096.0                    # LP24's second stage damping (Q 0.707)
RECIP_MAGIC = 0x7EF311C7

# exp2 of the fraction (dnfw.fdn8.ref.EXP2_C), tan(u) / u in u^2 on 0..UMAX (fitted, 6e-8 rel)
EXP2_C = (0.9999998807907104, 0.6931546330451965, 0.24014076590538025, 0.055863283574581146,
          0.00894621480256319, 0.0018951073288917542)
TAN_C = (1.0, 0.33333897590637207, 0.13318562507629395, 0.05527566373348236, 0.016902383416891098,
         0.01690998487174511)

# the SVF: damping (Q12 in the C) of RES r: 2 - r 7600/127/4096, and past 100 less (r-100)^2 125/128/4096
SVF_K1 = 7600.0 / 127.0 / 4096.0
SVF_K2 = 125.0 / 128.0 / 4096.0
LADR_K, OTA_K, DIOD_K, MS20_K = 4.6 / 127.0, 4.2 / 127.0, 22.0 / 127.0, 2.3 / 127.0
DIOD_GSC = f32(1.0 / f32(1.196))          # A2D_GSC
DIOD_OUT = f32(1.0 / f32(11.0))

# the mixes, a row a mode. SVF: (cx, cbk, cb1, cl, lim, -lim): out = (cx x + (cbk k + cb1) bp) + cl lp,
# clamped to lim; row 5 is LP24's second stage. LADR/OTA (A2M_LMIX) and DIOD (A2M_DMIX): u y1 y2 y3 y4.
# MS20: (cx, cb, cy, cl): out = ((cx (x + f) - cb 2bp) - cy lp) + cl lp4
SVFMIX = ((0, 0, 0, 1, OUT_MAX, -OUT_MAX), (0, 0, 0, 1, LP24_MAX, -LP24_MAX), (0, 0, 1, 0, OUT_MAX, -OUT_MAX),
          (1, -1, 0, -1, OUT_MAX, -OUT_MAX), (1, -1, 0, 0, OUT_MAX, -OUT_MAX), (0, 0, 0, 1, OUT_MAX, -OUT_MAX))
LMIX = ((0, 0, 1, 0, 0), (0, 0, 0, 0, 1), (0, 0, 4, -8, 4), (1, -2, 1, 0, 0), (1, -2, 2, 0, 0))
DMIX = ((0, 0, 1, 0, 0), (0, 0, 0, 0, 1), (0, 0, -1, 3, -2), (-1, 4, -5, 1, 1), (-1, 4, -7, 3, 0))
MSMIX = ((0, 0, -1, 0), (0, 0, 0, 1), (0, -1, 0, 0), (1, 1, 1, 0), (1, 1, 0, 0))


def kc_float(v) -> float:
    """a KC value as the float the table holds: an int is a bit pattern (the reciprocal's seed)"""
    import struct
    return struct.unpack("<f", struct.pack("<I", v))[0] if isinstance(v, int) else float(v)


def table_layout(models) -> tuple[list[float], dict[str, tuple[int, int]]]:
    """the mix tables the models need, back to back: (floats, {name: (word offset, row words)})"""
    out: list[float] = []
    at: dict[str, tuple[int, int]] = {}
    # 2026-11-21 (a2-juno-fast): the loops' constants first (KC, read through I1 so each load rides on a compute)
    at["kc"] = (0, len(KC))
    out += [kc_float(v) for _n, v in KC]
    want = (("svf", SVFMIX, ("SVF",)), ("lmix", LMIX, ("LADR", "OTA")), ("dmix", DMIX, ("DIOD",)),
            ("msmix", MSMIX, ("MS20",)))
    for name, rows, users in want:
        if any(u in models for u in users):
            at[name] = (len(out), len(rows[0]))
            for r in rows:
                out += [float(x) for x in r]
    return out, at


WORDS = ("gs", "ge", "res", "mode", "model", "buf", "zp", "row", "nst", "k", "a1", "a2", "a3",
         "d1", "d2", "d3", "cbk", "cb1", "cin", "inv", "G", "H", "G4", "ota", "gout", "gd",
         "ip1", "ip2", "ip3", "ip4", "h1", "h2", "h3", "h4", "gp2", "gp3", "Gk", "hh", "dn", "omG",
         "t0", "t1", "t2",
         # 2026-11-21: 1 while the coefficient words already hold this half's (a client that filters two signals with
         # the same words: ANALOG 2's side, then its mid): the ladders, DIOD and MS20 then skip them (_once)
         "cv")


class Ctx:
    """where a client keeps the models' words (SCRATCH: len(WORDS) words) and their mix tables
    (TABLES: table_layout(models)'s floats), and which models it emits"""

    def __init__(self, scratch: int, tables: int, models=MODELS):
        self.C = {w: scratch + 4 * k for k, w in enumerate(WORDS)}
        self.models = tuple(m for m in MODELS if m in models)
        _, at = table_layout(self.models)
        self.T = {name: (tables + 4 * off, 4 * width) for name, (off, width) in at.items()}


SCRATCH_WORDS = len(WORDS)


# -- instruction helpers ----------------------------------------------------------------------
def fabs(p: Prog, d: int, a: int) -> None:
    """Fd = |Fa| (the form pvmix.asm uses)"""
    p.e(f"F{d} = ABS F{a};")
    if p.run:
        p.r[d] = p.r[a] & 0x7FFFFFFF


def mloop(p: Prog, word: int, body) -> None:
    """for (; DM(word); DM(word)--) body(): the count (> 0) already in WORD; BODY may use every register"""
    top = p.label("ml")
    p.place(top)

    def tail():
        p.ld(0, word)
        p.iconst(12, 1)
        p.iop(0, 0, "-", 12)
        p.st(word, 0)
    if p.run:
        assert p.mem.get(word) > 0
        while True:
            body()
            tail()
            if p.r[0] == 0:
                return
    body()
    tail()
    p.jump("NE", top)


def _newton(p: Prog, x: int, r: int, t: int) -> None:
    """Fr = 1 / Fx from the seed in Rr: three steps r = 2r - r (x r). Clobbers Ft."""
    for _ in range(3):
        p.fop(t, x, "*", r)
        p.fop(t, r, "*", t)
        p.fop(r, r, "+", r)
        p.fop(r, r, "-", t)


# -- the leaves ------------------------------------------------------------------------------
def _tanh_body(p: Prog) -> None:
    """F15 = x (27 + x^2) / (27 + 9 x^2), x clamped to +-3 (a2m_tanh). Clobbers R12-R14. (2026-11-20: past +-3 the
    curve is flat: the voice's clip)"""
    p.fconst(12, 3.0)
    _clip(p, 15, "GT", 12)
    p.fop(15, 15, "MIN", 12)
    p.fconst(12, -3.0)
    _clip(p, 15, "LT", 12)
    p.fop(15, 15, "MAX", 12)
    p.fop(13, 15, "*", 15)                       # x^2
    p.fconst(12, 9.0)
    p.fop(14, 12, "*", 13)
    p.fconst(12, 27.0)
    p.fop(14, 12, "+", 14)                       # 27 + 9 x^2
    p.fop(13, 12, "+", 13)
    p.fop(13, 15, "*", 13)                       # x (27 + x^2)
    p.iconst(12, RECIP_MAGIC)
    p.iop(15, 12, "-", 14)
    _newton(p, 14, 15, 12)
    p.fop(15, 13, "*", 15)


def tanh(p: Prog) -> None:
    """F15 = tanh(F15) (Pade). Clobbers R12-R14, I12."""
    p.call("a2th", lambda: _tanh_body(p))


def _recip_body(p: Prog) -> None:
    p.iconst(12, RECIP_MAGIC)
    p.iop(14, 12, "-", 15)
    _newton(p, 15, 14, 12)
    p.fpass(15, 14)


def recip(p: Prog) -> None:
    """F15 = 1 / F15 (F15 > 0). Clobbers R12-R14, I12."""
    p.call("a2rc", lambda: _recip_body(p))


def _poly(p: Prog, d: int, x: int, c) -> None:
    p.fconst(d, c[-1])
    for k in range(len(c) - 2, -1, -1):
        p.fop(d, d, "*", x)
        p.fconst(12, c[k])
        p.fop(d, d, "+", 12)


def _g_body(p: Prog) -> None:
    """F15 = tan(pi fc / FS), fc = min(30 x 2^(F15 OCT / 127), 0.45 FS), F15 clamped to 0..127.
    Clobbers R12-R15."""
    p.fconst(12, 0.0)
    p.fop(15, 15, "MAX", 12)
    p.fconst(12, 127.0)
    p.fop(15, 15, "MIN", 12)
    p.fconst(12, K_OCT)
    p.fop(15, 15, "*", 12)                       # x, 0..9.06
    p.trunc(14, 15)                              # n
    p.iconst(13, 0)
    p.float_(13, 14, 13)
    p.fop(15, 15, "-", 13)                       # its fraction
    _poly(p, 13, 15, EXP2_C)
    p.iconst(12, 127)
    p.iop(14, 12, "+", 14)
    p.lsh(14, 14, 23)                            # 2^n
    p.fop(13, 13, "*", 14)
    p.fconst(12, W0H)
    p.fop(13, 13, "*", 12)
    p.fconst(12, UMAX)
    p.fop(13, 13, "MIN", 12)                     # u: half the angle
    p.fop(14, 13, "*", 13)
    _poly(p, 15, 14, TAN_C)
    p.fop(15, 13, "*", 15)                       # t = tan(u)
    p.fop(14, 15, "*", 15)
    p.fconst(12, 1.0)
    p.fop(14, 12, "-", 14)                       # 1 - t^2
    p.fop(15, 15, "+", 15)                       # 2 t
    p.iconst(12, RECIP_MAGIC)
    p.iop(13, 12, "-", 14)
    _newton(p, 14, 13, 12)
    p.fop(15, 15, "*", 13)                       # tan(2u) = 2t / (1 - t^2)


def g_of(p: Prog) -> None:
    """F15 = g at the cutoff F15 (CUT units). Clobbers R12-R14, I12."""
    p.call("a2g", lambda: _g_body(p))


# -- small pieces ----------------------------------------------------------------------------
def _ld(p, X, d, w):
    p.ld(d, X.C[w], w)


def _st(p, X, w, s):
    p.st(X.C[w], s, w)


def _rowi(p: Prog, X: Ctx, table: str) -> None:
    """I3 = the table's row of `mode`. Clobbers R0, R2, R8, R12."""
    base, width = X.T[table]
    _ld(p, X, 0, "mode")
    p.iconst(8, base)
    for b in range(6):
        if width >> b & 1:
            p.lsh(2, 0, b)
            p.iop(8, 8, "+", 2)
    p.seti(3, 8)


def _clip(p: Prog, x: int, cond: str, b: int) -> None:
    """2026-11-20 (clip-inner; the User: "NO DIGITAL CLIPPING ... if it does, i want the alert"): Fx past the hold in
    Fb (a nonzero word): the voice's clip (perc.program clip_flag)"""
    from ....perc import program as PP
    PP.clip_flag(p, x, cond, b, b)


def _clamp_out(p: Prog, y: int) -> None:
    # (2026-11-20, clip-inner: not flagged: +-32 is 30 dB past anything a voice reaches, and the DSP upload's room is
    # spent on the stages that do engage)
    p.fconst(12, OUT_MAX)
    p.fop(y, y, "MIN", 12)
    p.fconst(12, -OUT_MAX)
    p.fop(y, y, "MAX", 12)


def _loop16(p: Prog, body) -> None:
    p.loop_r(11, N, body)


def _states_in(p: Prog, X: Ctx, regs) -> None:
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    for k, r in enumerate(regs):
        p.ldi(r, k, 2)


def _states_out(p: Prog, X: Ctx, regs) -> None:
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    for k, r in enumerate(regs):
        if r is not None:
            p.sti(k, 2, r)


def _buf_in(p: Prog, X: Ctx) -> None:
    _ld(p, X, 0, "buf")
    p.seti(0, 0)


def _ratio(p: Prog, X: Ctx) -> None:
    """t0 = r = 1 / (1 + ge), G = ge r: the one-pole's G = g / (1 + g)"""
    _ld(p, X, 15, "ge")
    p.fconst(12, 1.0)
    p.fop(15, 12, "+", 15)
    recip(p)
    _st(p, X, "t0", 15)
    _ld(p, X, 14, "ge")
    p.fop(14, 14, "*", 15)
    _st(p, X, "G", 14)


# -- SVF -----------------------------------------------------------------------------------------
def _svf_coef(p: Prog, X: Ctx, g: str, k: int) -> None:
    """F15 = a1 = 1 / (1 + g (g + k)), F14 = a2 = g a1, F13 = a3 = g a2, from the word G, Fk;
    keeps Fk. Clobbers F12."""
    _ld(p, X, 13, g)
    p.fop(15, 13, "+", k)
    p.fop(15, 13, "*", 15)
    p.fconst(12, 1.0)
    p.fop(15, 12, "+", 15)
    recip(p)
    _ld(p, X, 13, g)
    p.fop(14, 13, "*", 15)
    p.fop(13, 13, "*", 14)


def svf_k(p: Prog, X: Ctx, d: int) -> None:
    """Fd = the SVF's damping from res (a2_k, continuous). Clobbers R0, R12."""
    _ld(p, X, 0, "res")
    p.fconst(12, SVF_K1)
    p.fop(d, 0, "*", 12)
    p.fconst(12, 2.0)
    p.fop(d, 12, "-", d)
    p.fconst(12, 100.0)
    p.fop(0, 0, "-", 12)

    def past():
        p.fop(0, 0, "*", 0)
        p.fconst(12, SVF_K2)
        p.fop(0, 0, "*", 12)
        p.fop(d, d, "-", 0)
    p.fconst(12, 0.0)
    p.if_(0, "GT", 12, past)


def _svf_stage(p: Prog, X: Ctx) -> None:
    """one SVF stage over the half: k, row (the mix row's address) and zp set"""
    _ld(p, X, 9, "k")
    _svf_coef(p, X, "gs", 9)
    _st(p, X, "a1", 15)
    _st(p, X, "a2", 14)
    _st(p, X, "a3", 13)
    _svf_coef(p, X, "ge", 9)
    p.fconst(12, 1.0 / N)
    for w, r in (("a1", 15), ("a2", 14), ("a3", 13)):
        _ld(p, X, 10, w)
        p.fop(r, r, "-", 10)
        p.fop(r, r, "*", 12)                     # d = (e - c) / 16
        p.fop(10, 10, "+", r)                    # c += d: sample 0 at 1/16 of the way
        _st(p, X, w, 10)
        _st(p, X, "d" + w[1], r)
    _ld(p, X, 0, "row")
    p.seti(3, 0)
    p.ldi(10, 1, 3)
    p.fop(9, 10, "*", 9)
    p.ldi(10, 2, 3)
    p.fop(9, 9, "+", 10)                         # cb = cbk k + cb1
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    p.ldi(1, 0, 2)                               # ic1
    p.ldi(2, 1, 2)                               # ic2
    for w, r in (("a1", 3), ("a2", 4), ("a3", 5), ("d1", 6), ("d2", 7), ("d3", 8)):
        _ld(p, X, r, w)
    _buf_in(p, X)
    if SSCHED:
        _xi(p, X)
        _kci(p, X, 10)

    def knee(r: int, lim: float) -> None:
        def over():
            p.fpass(10, 15)                      # (2026-11-20: |x| kept, F10 free after the store)
            p.fop(15, 15, "-", 12)
            if lim != 1.0:
                p.fconst(12, 1.0 / lim)
                p.fop(15, 15, "*", 12)
            p.fconst(12, 2.0)
            p.fop(15, 15, "MIN", 12)
            tanh(p)
            if lim != 1.0:
                p.fop(15, 15, "+", 15)
            p.fconst(12, lim)
            p.fop(15, 12, "+", 15)
            p.fconst(12, 1.122)                  # 2026-11-20 (clip-inner): squashed by 1 dB or more: the voice's clip
            p.fop(12, 15, "*", 12)
            _clip(p, 12, "LT", 10)
            p.fconst(12, 0.0)
            p.if_(r, "LT", 12, lambda: p.fop(r, 12, "-", 15), lambda: p.fpass(r, 15))
        fabs(p, 15, r)
        p.fconst(12, lim)
        p.if_(15, "GT", 12, over)

    def fast():
        from ....mnm.sched import Sched
        s = Sched(pairs=MFP)
        s.ld(0, 0, 0)                            # x
        s.sub(10, 0, 2)                          # v3 = x - ic2
        s.mul(13, 3, 1)
        s.mul(14, 4, 10)
        s.add(13, 13, 14)                        # v1 = a1 ic1 + a2 v3
        s.mul(14, 4, 1)
        s.mul(15, 5, 10)
        s.add(14, 14, 15)
        s.add(14, 2, 14)                         # v2 = ic2 + (a2 ic1 + a3 v3)
        s.add(15, 13, 13)
        s.sub(1, 15, 1)                          # ic1 = 2 v1 - ic1
        s.add(15, 14, 14)
        s.sub(2, 15, 2)                          # ic2 = 2 v2 - ic2
        s.ld(10, 0, 3)
        s.mul(10, 10, 0)
        s.mul(15, 9, 13)
        s.add(10, 10, 15)
        s.ld(15, 3, 3)
        s.mul(15, 15, 14)
        s.add(10, 10, 15)                        # (cx x + cb v1) + cl v2
        s.ld(15, 4, 3)
        s.fop(10, 10, "MIN", 15)
        s.ld(15, 5, 3)
        s.fop(10, 10, "MAX", 15)
        s.add(3, 3, 6)                           # (the ramp's steps: read by the next sample only; the knees
        s.add(4, 4, 7)                           # never touch F3-F8)
        s.add(5, 5, 8)
        s.raw(lambda q: fabs(q, 15, 1), (1,), (15,))
        s.ld(12, _kc("k1"), 1)
        s.emit(p)
        p.stpost(0, 10)
        p.if_(15, "GT", 12, lambda: over(1, 1.0))
        fabs(p, 15, 2)
        p.ldi(12, _kc("k2"), 1)
        p.if_(15, "GT", 12, lambda: over(2, 2.0))

    def over(r: int, lim: float) -> None:
        p.fpass(10, 15)
        p.fop(15, 15, "-", 12)
        if lim != 1.0:
            p.fconst(12, 1.0 / lim)
            p.fop(15, 15, "*", 12)
        p.fconst(12, 2.0)
        p.fop(15, 15, "MIN", 12)
        tanh(p)
        if lim != 1.0:
            p.fop(15, 15, "+", 15)
        p.fconst(12, lim)
        p.fop(15, 12, "+", 15)
        p.fconst(12, 1.122)
        p.fop(12, 15, "*", 12)
        _clip(p, 12, "LT", 10)
        p.fconst(12, 0.0)
        p.if_(r, "LT", 12, lambda: p.fop(r, 12, "-", 15), lambda: p.fpass(r, 15))

    def one():
        if SSCHED:
            return fast()
        p.ldi(0, 0, 0)                           # x
        p.fop(10, 0, "-", 2)                     # v3 = x - ic2
        p.fop(13, 3, "*", 1)
        p.fop(14, 4, "*", 10)
        p.fop(13, 13, "+", 14)                   # v1 = a1 ic1 + a2 v3
        p.fop(14, 4, "*", 1)
        p.fop(15, 5, "*", 10)
        p.fop(14, 14, "+", 15)
        p.fop(14, 2, "+", 14)                    # v2 = ic2 + (a2 ic1 + a3 v3)
        p.fop(15, 13, "+", 13)
        p.fop(1, 15, "-", 1)                     # ic1 = 2 v1 - ic1
        p.fop(15, 14, "+", 14)
        p.fop(2, 15, "-", 2)                     # ic2 = 2 v2 - ic2
        p.ldi(10, 0, 3)
        p.fop(10, 10, "*", 0)
        p.fop(15, 9, "*", 13)
        p.fop(10, 10, "+", 15)
        p.ldi(15, 3, 3)
        p.fop(15, 15, "*", 14)
        p.fop(10, 10, "+", 15)                   # (cx x + cb v1) + cl v2
        p.ldi(15, 4, 3)
        p.fop(10, 10, "MIN", 15)
        p.ldi(15, 5, 3)
        p.fop(10, 10, "MAX", 15)
        p.stpost(0, 10)
        knee(1, 1.0)                             # the band state: linear to 1, a knee to 1 + tanh 2
        knee(2, 2.0)                             # the low-pass one: to 2, then 2 + 2 tanh((a - 2) / 2)
        p.fop(3, 3, "+", 6)
        p.fop(4, 4, "+", 7)
        p.fop(5, 5, "+", 8)
    _loop16(p, one)
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    p.sti(0, 2, 1)
    p.sti(1, 2, 2)


SSCHED = True                                    # (perf, 2026-11-21) the SVF stage's loop scheduled; False = as before


def _svf_half(p: Prog, X: Ctx) -> None:
    """the SVF over the half: one stage, two for LP24 (the second at K2ND, its row 5, states zp + 8)"""
    svf_k(p, X, 1)
    _st(p, X, "k", 1)
    base, width = X.T["svf"]
    _rowi(p, X, "svf")
    _st(p, X, "row", 8)
    _ld(p, X, 0, "zp")
    _st(p, X, "t1", 0)                           # the stages move zp; it comes back after
    _ld(p, X, 0, "mode")
    p.iconst(1, 1)
    p.iconst(2, 1)
    p.if_(0, "EQ", 2, lambda: p.iconst(1, 2), kind="i")
    _st(p, X, "nst", 1)

    def stage():
        _svf_stage(p, X)
        p.fconst(1, K2ND)
        _st(p, X, "k", 1)
        p.iconst(1, base + 5 * width)
        _st(p, X, "row", 1)
        _ld(p, X, 8, "zp")
        p.iconst(9, 8)
        p.iop(8, 8, "+", 9)
        _st(p, X, "zp", 8)
    mloop(p, X.C["nst"], stage)
    _ld(p, X, 0, "t1")
    _st(p, X, "zp", 0)


# -- LADR, OTA: the 4-pole ladders (a2m_ladder) ------------------------------------------------
def _once(p: Prog, X: Ctx, body) -> None:
    """BODY (a model's coefficients) unless the word cv says they are set already. Clobbers R0."""
    _ld(p, X, 0, "cv")
    p.ifz(0, "EQ", body)


def _ladder_half(p: Prog, X: Ctx) -> None:
    _once(p, X, lambda: ladder_coefs(p, X))
    ladder_core(p, X)


def ladder_coefs(p: Prog, X: Ctx) -> None:
    """the ladders' words (k, cin, ota, G, t0, H, G4, inv) from ge and res"""
    both = "LADR" in X.models and "OTA" in X.models
    only_ota = "OTA" in X.models and not both

    def consts(kc: float, ota: bool):
        _ld(p, X, 0, "res")
        p.fconst(12, kc)
        p.fop(0, 0, "*", 12)
        _st(p, X, "k", 0)
        if ota:
            p.fconst(12, 0.5)
            p.fop(1, 12, "*", 0)
            p.fconst(12, 1.0)
            p.fop(1, 12, "+", 1)                 # cin = 1 + k / 2
        else:
            p.fconst(1, 1.0)
        _st(p, X, "cin", 1)
        p.iconst(1, 1 if ota else 0)
        _st(p, X, "ota", 1)
    if both:
        _ld(p, X, 0, "model")
        p.iconst(1, OTA)
        p.if_(0, "EQ", 1, lambda: consts(OTA_K, True), lambda: consts(LADR_K, False), kind="i")
    else:
        consts(OTA_K if only_ota else LADR_K, only_ota)
    _ratio(p, X)                                 # G, F14
    p.fconst(12, 1.0)
    p.fop(13, 12, "-", 14)
    _st(p, X, "H", 13)
    p.fop(15, 14, "*", 14)
    p.fop(15, 15, "*", 14)
    p.fop(15, 15, "*", 14)                       # G^4
    _st(p, X, "G4", 15)
    _ld(p, X, 13, "k")
    p.fop(15, 13, "*", 15)
    p.fconst(12, 1.0)
    p.fop(15, 12, "+", 15)
    recip(p)
    _st(p, X, "inv", 15)


def ladder_core(p: Prog, X: Ctx) -> None:
    """The ladders' 16 samples from the words G, H, k, G4, inv, cin, ota, mode, buf, zp (2026-11-12: one leaf
    subroutine, a2lad, its tanh inlined, shared by ANALOG2 and JUNO in PERC; the same operations in the same order
    as before). JUNO's drive d rides on the words: H d, k / d and G4 d give u = x - (k / d) tanh(d (G4 t + S)),
    t = (x - k S) inv unchanged (dnfw.engines.juno.juno). Clobbers every register but I3's caller copy, R12, I12."""
    p.call("a2lad", lambda: _ladder_loop(p, X))


MFP = False                                      # (perf, 2026-11-21) the scheduled loops pair a multiply with an add or
                                                 # subtract (multifunction, dnfw.perc.mf's PROVEN forms); False: none
# ANALOG 2's sine (analog2.SIN_Q, its oscillators' u (1 - u^2) Q(u^2)): kept here, in KC, for its two-sample kernel
A2_SIN_Q = tuple(-c * (32767.0 / 32768.0) for c in (3.14159230309089, -2.0260895597297144, 0.5237673445980027,
                                                    -0.07439094157966462, 0.005918106135584834))
# ANALOG 2's drive curve (analog2.TANH_P, tanh(x) / x in x^2): kept here, in KC, for its two-sample loop (_drive2)
A2_TANH_P = tuple(c * (32767.0 / 32768.0) for c in (0.994438468571122, -0.3077078377445752, 0.08908856172526249,
                                                    -0.01588368865468038, 0.0012091530231845907))
KC = (("k3", 3.0), ("km3", -3.0), ("k9", 9.0), ("k27", 27.0), ("kmag", RECIP_MAGIC), ("kout", OUT_MAX),
      ("koutn", -OUT_MAX), ("k1", 1.0), ("k2", 2.0)) + tuple((f"sq{k}", c) for k, c in enumerate(A2_SIN_Q)) + \
     (("km2", -2.0), ("khalf", 0.5)) + tuple((f"tp{k}", c) for k, c in enumerate(A2_TANH_P))   # (2026-11-21, filt-opt)
LSCHED = True                                    # (perf, 2026-11-21) _ladder_fast; False = the loop as before


def _ladder_loop(p: Prog, X: Ctx) -> None:
    if LSCHED:
        return _ladder_fast(p, X)
    both = "LADR" in X.models and "OTA" in X.models
    only_ota = "OTA" in X.models and not both
    _rowi(p, X, "lmix")
    _states_in(p, X, (1, 2, 3, 4))
    _ld(p, X, 5, "G")
    _ld(p, X, 6, "H")
    _ld(p, X, 7, "k")
    _buf_in(p, X)

    def ota_in():                                # tanh's argument: G4 t + S
        _ld(p, X, 10, "G4")
        p.fop(15, 10, "*", 9)
        p.fop(15, 15, "+", 8)

    def ota_out():                               # u = x - k tanh(G4 t + S)
        p.fop(15, 7, "*", 15)
        p.fop(15, 0, "-", 15)

    def one():
        p.ldi(0, 0, 0)
        _ld(p, X, 8, "cin")
        p.fop(0, 0, "*", 8)                      # x
        p.fop(8, 5, "*", 1)
        p.fop(8, 8, "+", 2)
        p.fop(8, 5, "*", 8)
        p.fop(8, 8, "+", 3)
        p.fop(8, 5, "*", 8)
        p.fop(8, 8, "+", 4)
        p.fop(8, 6, "*", 8)                      # S = H (G (G (G z1 + z2) + z3) + z4)
        p.fop(9, 7, "*", 8)
        p.fop(9, 0, "-", 9)
        _ld(p, X, 10, "inv")
        p.fop(9, 9, "*", 10)                     # t = (x - k S) inv
        if both:                                 # LADR: u = tanh(t)
            _ld(p, X, 10, "ota")
            p.ifz(10, "NE", ota_in, lambda: p.fpass(15, 9))
            _tanh_body(p)
            _ld(p, X, 10, "ota")
            p.ifz(10, "NE", ota_out)
        elif only_ota:
            ota_in()
            _tanh_body(p)
            ota_out()
        else:
            p.fpass(15, 9)
            _tanh_body(p)
        for z, yin, y in ((1, 15, 8), (2, 8, 13), (3, 13, 14), (4, 14, 10)):   # four one-poles
            p.fop(9, yin, "-", z)
            p.fop(9, 9, "*", 5)
            p.fop(y, 9, "+", z)
            p.fop(z, y, "+", 9)
        p.ldi(9, 0, 3)
        p.fop(9, 9, "*", 15)
        for k, y in ((1, 8), (2, 13), (3, 14), (4, 10)):
            p.ldi(12, k, 3)
            p.fop(12, 12, "*", y)
            p.fop(9, 9, "+", 12)
        _clamp_out(p, 9)
        p.stpost(0, 9)
    _loop16(p, one)
    _states_out(p, X, (1, 2, 3, 4))


def _kci(p: Prog, X: Ctx, r: int) -> None:
    """I1 = the constants (KC, the tables' first words). Clobbers Rr."""
    p.iconst(r, X.T["kc"][0])
    p.seti(1, r)


def _kc(name: str) -> int:
    """a constant's offset from I1 (_kci)"""
    return [n for n, _v in KC].index(name)


def _wk(name: str) -> int:
    """a word's offset from I2 (X_MID)"""
    return WORDS.index(name) - X_MID


def _tanh_sched(p: Prog, s):
    """_tanh_body's operations on F15, after the ops already in Sched S (emitted with the first part): its constants
    from the words (LCONSTS, through I2), the two clip flags between scheduled runs. Returns a new Sched holding the
    tail (from the MAX on), for the caller to add to and emit."""
    from ....mnm.sched import Sched
    s.ld(12, _kc("k3"), 1)
    s.emit(p)
    _clip(p, 15, "GT", 12)
    s = Sched(pairs=MFP)
    s.fop(15, 15, "MIN", 12)
    s.ld(12, _kc("km3"), 1)
    s.emit(p)
    _clip(p, 15, "LT", 12)
    s = Sched(pairs=MFP)
    s.fop(15, 15, "MAX", 12)
    _tanh_core(s, True)
    return s


def _tanh_core(s, words: bool) -> None:
    """_tanh_body's operations from x^2 on (F15 clamped): WORDS, its constants from KC through I1 (_kci)"""
    def k(d, name, x):
        if words:
            s.ld(d, _kc(name), 1)
        else:
            s.const(d, x)
    s.mul(13, 15, 15)                            # x^2
    k(12, "k9", 9.0)
    s.mul(14, 12, 13)
    k(12, "k27", 27.0)
    s.add(14, 12, 14)                            # 27 + 9 x^2
    s.add(13, 12, 13)
    s.mul(13, 15, 13)                            # x (27 + x^2)
    if words:
        s.ld(12, _kc("kmag"), 1)
    else:
        s.raw(lambda q: q.iconst(12, RECIP_MAGIC), (), (12,))
    s.raw(lambda q: q.iop(15, 12, "-", 14), (12, 14), (15,))
    for _ in range(3):                           # _newton(14, 15, 12)
        s.mul(12, 14, 15)
        s.mul(12, 15, 12)
        s.add(15, 15, 15)
        s.sub(15, 15, 12)
    s.mul(15, 13, 15)


def _clamp_sched(s, y: int) -> None:
    """_clamp_out's operations, the bounds from the words"""
    s.ld(12, _kc("kout"), 1)
    s.fop(y, y, "MIN", 12)
    s.ld(12, _kc("koutn"), 1)
    s.fop(y, y, "MAX", 12)


def _ladder_fast(p: Prog, X: Ctx) -> None:
    """_ladder_loop's operations on the same values in the same order (so bit for bit), with: the LADR / OTA choice
    made once, outside the loop (a loop each); cin, inv, G4 and the constants (LCONSTS) read through I2 (X_MID), so
    their loads ride on the computes; the straight runs between the clip flags' branches scheduled (dnfw.mnm.sched,
    no multifunction pairs)."""
    from ....mnm.sched import Sched
    both = "LADR" in X.models and "OTA" in X.models
    only_ota = "OTA" in X.models and not both
    w = lambda name: WORDS.index(name) - X_MID   # noqa: E731
    _rowi(p, X, "lmix")
    _states_in(p, X, (1, 2, 3, 4))
    _ld(p, X, 5, "G")
    _ld(p, X, 6, "H")
    _ld(p, X, 7, "k")
    _buf_in(p, X)
    _xi(p, X)
    _kci(p, X, 8)

    def one(ota: bool):
        s = Sched(pairs=MFP)
        s.ld(0, 0, 0)
        s.ld(8, w("cin"), 2)
        s.mul(0, 0, 8)                           # x
        s.mul(8, 5, 1)
        s.add(8, 8, 2)
        s.mul(8, 5, 8)
        s.add(8, 8, 3)
        s.mul(8, 5, 8)
        s.add(8, 8, 4)
        s.mul(8, 6, 8)                           # S = H (G (G (G z1 + z2) + z3) + z4)
        s.mul(9, 7, 8)
        s.sub(9, 0, 9)
        s.ld(10, w("inv"), 2)
        s.mul(9, 9, 10)                          # t = (x - k S) inv
        if ota:                                  # tanh's argument: G4 t + S
            s.ld(10, w("G4"), 2)
            s.mul(15, 10, 9)
            s.add(15, 15, 8)
        else:
            s.raw(lambda q: q.fpass(15, 9), (9,), (15,))
        s = _tanh_sched(p, s)                    # _tanh_body's operations, its constants from the words
        if ota:                                  # u = x - k tanh(G4 t + S)
            s.mul(15, 7, 15)
            s.sub(15, 0, 15)
        for z, yin, y in ((1, 15, 8), (2, 8, 13), (3, 13, 14), (4, 14, 10)):   # four one-poles
            s.sub(9, yin, z)
            s.mul(9, 9, 5)
            s.add(y, 9, z)
            s.add(z, y, 9)
        s.ld(9, 0, 3)
        s.mul(9, 9, 15)
        for k, y in ((1, 8), (2, 13), (3, 14), (4, 10)):
            s.ld(12, k, 3)
            s.mul(12, 12, y)
            s.add(9, 9, 12)
        _clamp_sched(s, 9)
        s.emit(p)
        p.stpost(0, 9)
    if both:
        _ld(p, X, 10, "ota")
        p.ifz(10, "NE", lambda: _loop16(p, lambda: one(True)), lambda: _loop16(p, lambda: one(False)))
    else:
        _loop16(p, lambda: one(only_ota))
    _states_out(p, X, (1, 2, 3, 4))


# -- DIOD: the diode ladder (a2m_diod), its tridiagonal system by elimination ------------------
def _diod_half(p: Prog, X: Ctx) -> None:
    _once(p, X, lambda: _diod_coefs(p, X))
    _diod_run(p, X)


def _diod_coefs(p: Prog, X: Ctx) -> None:
    _ld(p, X, 0, "res")
    p.fconst(12, DIOD_K)
    p.fop(0, 0, "*", 12)
    _st(p, X, "k", 0)
    p.fconst(12, 0.5)
    p.fop(1, 12, "*", 0)
    p.fconst(12, 1.0)
    p.fop(1, 12, "+", 1)
    _st(p, X, "cin", 1)                          # 1 + k / 2
    p.fconst(12, DIOD_OUT)
    p.fop(1, 0, "*", 12)
    p.fconst(12, 1.0)
    p.fop(1, 12, "+", 1)
    _st(p, X, "gout", 1)                         # 1 + k / 11
    _ld(p, X, 0, "ge")
    p.fconst(12, DIOD_GSC)
    p.fop(0, 0, "*", 12)
    _st(p, X, "gd", 0)                           # g / 1.196
    p.fop(1, 0, "+", 0)
    p.fconst(12, 1.0)
    p.fop(1, 12, "+", 1)
    _st(p, X, "t1", 1)                           # the diagonal 1 + 2 g
    p.fop(2, 0, "*", 0)
    _st(p, X, "t2", 2)                           # g^2
    p.fpass(15, 1)
    for i in (1, 2, 3, 4):
        recip(p)
        _st(p, X, f"ip{i}", 15)                  # 1 / pivot i
        _ld(p, X, 0, "gd")
        p.fop(1, 0, "*", 15)
        _st(p, X, "h1" if i == 1 else ("gp%d" % i if i < 4 else "t0"), 1)   # g / pivot
        if i < 4:
            _ld(p, X, 2, "t2")
            p.fop(2, 2, "*", 15)
            if i < 3:
                _ld(p, X, 15, "t1")
            else:
                p.fconst(12, 1.0)
                p.fop(15, 12, "+", 0)            # the last diagonal 1 + g
            p.fop(15, 15, "-", 2)                # the next pivot
    _ld(p, X, 0, "h1")
    _ld(p, X, 1, "gp2")
    p.fop(0, 1, "*", 0)
    _st(p, X, "h2", 0)
    _ld(p, X, 1, "gp3")
    p.fop(0, 1, "*", 0)
    _st(p, X, "h3", 0)
    _ld(p, X, 1, "t0")
    p.fop(0, 1, "*", 0)
    _st(p, X, "h4", 0)                           # q4
    _ld(p, X, 1, "k")
    p.fop(15, 1, "*", 0)
    p.fconst(12, 1.0)
    p.fop(15, 12, "+", 15)
    recip(p)
    _st(p, X, "inv", 15)


def _diod_run(p: Prog, X: Ctx) -> None:
    _rowi(p, X, "dmix")
    _states_in(p, X, (1, 2, 3, 4))
    _ld(p, X, 5, "gd")
    _buf_in(p, X)

    if SCHED:
        _xi(p, X)
        if DKW:
            _kci(p, X, 10)

        def one():
            _diod_sample(p, X)
            p.stpost(0, 10)
        _loop16(p, one)
        _states_out(p, X, (1, 2, 3, 4))
        return

    def one():
        p.ldi(0, 0, 0)
        _ld(p, X, 10, "ip1")
        p.fop(6, 1, "*", 10)                     # e1 = s1 / p1
        for i, e_prev, s, e in ((2, 6, 2, 7), (3, 7, 3, 8), (4, 8, 4, 9)):
            p.fop(e, 5, "*", e_prev)
            p.fop(e, s, "+", e)
            _ld(p, X, 10, f"ip{i}")
            p.fop(e, e, "*", 10)                 # e_i = (s_i + g e_i-1) / p_i
        _ld(p, X, 10, "cin")
        p.fop(15, 0, "*", 10)
        _ld(p, X, 10, "k")
        p.fop(13, 10, "*", 9)
        p.fop(15, 15, "-", 13)
        _ld(p, X, 10, "inv")
        p.fop(15, 15, "*", 10)
        tanh(p)                                  # u = tanh((x cin - k e4) inv)
        for h, e in (("h1", 6), ("h2", 7), ("h3", 8), ("h4", 9)):
            _ld(p, X, 10, h)
            p.fop(10, 10, "*", 15)
            p.fop(e, e, "+", 10)                 # e_i + h_i u (y4 in F9)
        for gp, y, y_next in (("gp3", 8, 9), ("gp2", 7, 8), ("h1", 6, 7)):
            _ld(p, X, 10, gp)
            p.fop(10, 10, "*", y_next)
            p.fop(y, y, "+", 10)                 # y_i = d_i + g / p_i y_i+1
        for s, y in ((1, 6), (2, 7), (3, 8), (4, 9)):
            p.fop(10, y, "+", y)
            p.fop(s, 10, "-", s)                 # s = 2 y - s
        p.ldi(10, 0, 3)
        p.fop(10, 10, "*", 15)
        for k, y in ((1, 6), (2, 7), (3, 8), (4, 9)):
            p.ldi(12, k, 3)
            p.fop(12, 12, "*", y)
            p.fop(10, 10, "+", 12)
        _ld(p, X, 12, "gout")
        p.fop(10, 12, "*", 10)
        _clamp_out(p, 10)
        p.stpost(0, 10)
    _loop16(p, one)
    _states_out(p, X, (1, 2, 3, 4))


SCHED = True                                     # (perf, 2026-11-12) the per-sample loops on dnfw.mnm.sched; False = as before
X_MID = WORDS.index("G")                         # I2 at this word while a scheduled loop runs: every word within -32..31


def _xi(p: Prog, X: Ctx) -> None:
    """I2 = the words' X_MID (the states are in registers by now; _states_out points I2 back). Clobbers R12."""
    p.iconst(12, X.C[WORDS[X_MID]])
    p.seti(2, 12)


DKW = True                                       # (perf, 2026-11-21) DIOD's tanh and bound constants from the words


def _tanh_ops(s) -> None:
    """_tanh_body's operations onto the scheduler S (dnfw.mnm.sched), on F15, the same order and registers"""
    s.const(12, 3.0)
    s.fop(15, 15, "MIN", 12)
    s.const(12, -3.0)
    s.fop(15, 15, "MAX", 12)
    s.mul(13, 15, 15)                            # x^2
    s.const(12, 9.0)
    s.mul(14, 12, 13)
    s.const(12, 27.0)
    s.add(14, 12, 14)                            # 27 + 9 x^2
    s.add(13, 12, 13)
    s.mul(13, 15, 13)                            # x (27 + x^2)
    s.raw(lambda q: q.iconst(12, RECIP_MAGIC), (), (12,))
    s.raw(lambda q: q.iop(15, 12, "-", 14), (12, 14), (15,))
    for _ in range(3):                           # _newton(14, 15, 12)
        s.mul(12, 14, 15)
        s.mul(12, 15, 12)
        s.add(15, 15, 15)
        s.sub(15, 15, 12)
    s.mul(15, 13, 15)


def _diod_sample(p: Prog, X: Ctx) -> None:
    """one sample of _diod_half's loop, F10 its output (not yet stored): the same operations on the same values
    (so bit for bit), each loaded word in a temporary of its own (F10 F12 F13 F14 in turn, never F11, the loop's count, where the plain loop
    reuses F10) and scheduled (dnfw.mnm.sched), so the words' loads, through I2 (_xi), ride on the computes."""
    from ....mnm.sched import Sched
    w = lambda name: WORDS.index(name) - X_MID   # noqa: E731
    tmp = [10, 14, 12]
    s = Sched()
    s.ld(0, 0, 0)
    s.ld(10, w("ip1"), 2)
    s.mul(6, 1, 10)                              # e1 = s1 / p1
    for n, (i, e_prev, st, e) in enumerate(((2, 6, 2, 7), (3, 7, 3, 8), (4, 8, 4, 9))):
        t = tmp[(n + 1) % 3]
        s.ld(t, w(f"ip{i}"), 2)
        s.mul(e, 5, e_prev)
        s.add(e, st, e)
        s.mul(e, e, t)                           # e_i = (s_i + g e_i-1) / p_i
    s.ld(10, w("cin"), 2)
    s.ld(12, w("k"), 2)
    s.ld(14, w("inv"), 2)
    s.mul(15, 0, 10)
    s.mul(13, 12, 9)
    s.sub(15, 15, 13)
    s.mul(15, 15, 14)
    if DKW:                                      # u = tanh((x cin - k e4) inv), a2th's operations inline
        s.ld(12, _kc("k3"), 1)
        s.fop(15, 15, "MIN", 12)
        s.ld(12, _kc("km3"), 1)
        s.fop(15, 15, "MAX", 12)
        _tanh_core(s, True)
    else:
        _tanh_ops(s)
    tmp = [10, 12, 13, 14]
    n = 0
    for h, e in (("h1", 6), ("h2", 7), ("h3", 8), ("h4", 9)):
        t = tmp[n % 4]; n += 1
        s.ld(t, w(h), 2)
        s.mul(t, t, 15)
        s.add(e, e, t)                           # e_i + h_i u (y4 in F9)
    for gp, y, y_next in (("gp3", 8, 9), ("gp2", 7, 8), ("h1", 6, 7)):
        t = tmp[n % 4]; n += 1
        s.ld(t, w(gp), 2)
        s.mul(t, t, y_next)
        s.add(y, y, t)                           # y_i = d_i + g / p_i y_i+1
    for st, y in ((1, 6), (2, 7), (3, 8), (4, 9)):
        t = tmp[n % 4]; n += 1
        s.add(t, y, y)
        s.sub(st, t, st)                         # s = 2 y - s
    s.ld(10, 0, 3)
    s.mul(10, 10, 15)
    for k, y in ((1, 6), (2, 7), (3, 8), (4, 9)):
        t = (12, 13, 14, 12)[k - 1]
        s.ld(t, k, 3)
        s.mul(t, t, y)
        s.add(10, 10, t)
    s.ld(12, w("gout"), 2)
    s.mul(10, 12, 10)
    if DKW:
        _clamp_sched(s, 10)
    else:
        s.const(12, OUT_MAX)
        s.fop(10, 10, "MIN", 12)
        s.const(12, -OUT_MAX)
        s.fop(10, 10, "MAX", 12)
    s.emit(p)


# -- MS20: the Sallen-Key 2-pole (a2m_ms20) ----------------------------------------------------
def _ms20_half(p: Prog, X: Ctx) -> None:
    _once(p, X, lambda: _ms20_coefs(p, X))
    _ms20_run(p, X)


def _ms20_coefs(p: Prog, X: Ctx) -> None:
    _ld(p, X, 0, "res")
    p.fconst(12, MS20_K)
    p.fop(0, 0, "*", 12)
    _st(p, X, "k", 0)
    _ratio(p, X)                                 # G (F14), t0 = 1 / (1 + g) = h
    p.fconst(12, 1.0)
    p.fop(13, 12, "-", 14)
    _st(p, X, "omG", 13)
    _ld(p, X, 0, "k")
    p.fop(15, 0, "*", 14)
    p.fop(15, 15, "*", 13)
    p.fop(15, 12, "-", 15)
    recip(p)
    _st(p, X, "dn", 15)                          # 1 / (1 - k G (1 - G))
    _ld(p, X, 0, "k")
    _ld(p, X, 14, "G")
    p.fop(14, 14, "*", 0)
    _st(p, X, "Gk", 14)


def _ms20_run(p: Prog, X: Ctx) -> None:
    _rowi(p, X, "msmix")
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    p.ldi(1, 0, 2)
    p.ldi(2, 1, 2)
    p.ldi(3, 3, 2)
    _ld(p, X, 4, "G")
    _ld(p, X, 5, "t0")
    _ld(p, X, 6, "k")
    _buf_in(p, X)
    if MSCHED:
        _xi(p, X)
        _kci(p, X, 8)
        _loop16(p, lambda: _ms20_fast(p))
        _ld(p, X, 0, "zp")
        p.seti(2, 0)
        p.sti(0, 2, 1)
        p.sti(1, 2, 2)
        p.sti(3, 2, 3)
        return

    def one():
        p.ldi(0, 0, 0)
        p.fop(7, 4, "*", 0)
        _ld(p, X, 8, "Gk")
        p.fop(8, 8, "*", 2)
        p.fop(8, 1, "-", 8)
        p.fop(8, 8, "*", 5)
        p.fop(7, 7, "+", 8)
        _ld(p, X, 8, "dn")
        p.fop(7, 7, "*", 8)                      # y1, linear
        _ld(p, X, 8, "omG")
        p.fop(15, 8, "*", 7)
        p.fop(9, 2, "*", 5)                      # s2 h
        p.fop(15, 15, "-", 9)
        tanh(p)
        p.fop(15, 6, "*", 15)                    # f = k tanh((1 - G) y1 - s2 h)
        p.fop(7, 0, "+", 15)                     # x + f
        p.fop(8, 4, "*", 7)
        p.fop(10, 1, "*", 5)
        p.fop(8, 8, "+", 10)                     # y1 = G (x + f) + s1 h
        p.fop(10, 4, "*", 8)
        p.fop(10, 10, "+", 9)                    # y2 = G y1 + s2 h
        p.fop(13, 8, "+", 8)
        p.fop(1, 13, "-", 1)
        p.fop(13, 10, "+", 10)
        p.fop(2, 13, "-", 2)
        p.fop(8, 8, "-", 10)
        p.fop(8, 8, "+", 8)                      # 2 bp
        p.fop(13, 10, "-", 3)
        p.fop(13, 13, "*", 4)
        p.fop(14, 13, "+", 3)                    # lp4
        p.fop(3, 14, "+", 13)
        p.ldi(9, 0, 3)
        p.fop(9, 9, "*", 7)
        p.ldi(13, 1, 3)
        p.fop(13, 13, "*", 8)
        p.fop(9, 9, "-", 13)
        p.ldi(13, 2, 3)
        p.fop(13, 13, "*", 10)
        p.fop(9, 9, "-", 13)
        p.ldi(13, 3, 3)
        p.fop(13, 13, "*", 14)
        p.fop(9, 9, "+", 13)
        _clamp_out(p, 9)
        p.stpost(0, 9)
    _loop16(p, one)
    _ld(p, X, 0, "zp")
    p.seti(2, 0)
    p.sti(0, 2, 1)
    p.sti(1, 2, 2)
    p.sti(3, 2, 3)


MSCHED = True                                    # (perf, 2026-11-21) _ms20_fast; False = the loop as before


def _ms20_fast(p: Prog) -> None:
    """one sample of _ms20_half's loop: its operations on the same values in the same order (so bit for bit), the
    words (Gk, dn, omG) and the constants read through I2 so their loads ride on the computes, a2th's operations
    inline, the straight runs scheduled (no multifunction pairs)"""
    from ....mnm.sched import Sched
    s = Sched(pairs=MFP)
    s.ld(0, 0, 0)
    s.mul(7, 4, 0)
    s.ld(8, _wk("Gk"), 2)
    s.mul(8, 8, 2)
    s.sub(8, 1, 8)
    s.mul(8, 8, 5)
    s.add(7, 7, 8)
    s.ld(8, _wk("dn"), 2)
    s.mul(7, 7, 8)                               # y1, linear
    s.ld(8, _wk("omG"), 2)
    s.mul(15, 8, 7)
    s.mul(9, 2, 5)                               # s2 h
    s.sub(15, 15, 9)
    s = _tanh_sched(p, s)
    s.mul(15, 6, 15)                             # f = k tanh((1 - G) y1 - s2 h)
    s.add(7, 0, 15)                              # x + f
    s.mul(8, 4, 7)
    s.mul(10, 1, 5)
    s.add(8, 8, 10)                              # y1 = G (x + f) + s1 h
    s.mul(10, 4, 8)
    s.add(10, 10, 9)                             # y2 = G y1 + s2 h
    s.add(13, 8, 8)
    s.sub(1, 13, 1)
    s.add(13, 10, 10)
    s.sub(2, 13, 2)
    s.sub(8, 8, 10)
    s.add(8, 8, 8)                               # 2 bp
    s.sub(13, 10, 3)
    s.mul(13, 13, 4)
    s.add(14, 13, 3)                             # lp4
    s.add(3, 14, 13)
    s.ld(9, 0, 3)
    s.mul(9, 9, 7)
    for k, y, op in ((1, 8, "-"), (2, 10, "-"), (3, 14, "+")):
        s.ld(13, k, 3)
        s.mul(13, 13, y)
        s.fop(9, 9, op, 13)
    _clamp_sched(s, 9)
    s.emit(p)
    p.stpost(0, 9)


# -- the entry ---------------------------------------------------------------------------------
def half(p: Prog, X: Ctx) -> None:
    """model `model` (one of X.models; another: nothing) over the 16 samples at `buf`, in place"""
    arms = []
    if "SVF" in X.models:
        arms.append(((SVF,), _svf_half))
    if "LADR" in X.models or "OTA" in X.models:
        arms.append((tuple(i for i, m in ((LADR, "LADR"), (OTA, "OTA")) if m in X.models), _ladder_half))
    if "DIOD" in X.models:
        arms.append(((DIOD,), _diod_half))
    if "MS20" in X.models:
        arms.append(((MS20,), _ms20_half))

    def pick(rest):
        if not rest:
            return
        ids, fn = rest[0]
        _ld(p, X, 0, "model")
        if len(ids) == 2:                        # LADR or OTA
            p.iconst(2, 0)
            for i in ids:
                p.iconst(1, i)
                p.if_(0, "EQ", 1, lambda: p.iconst(2, 1), kind="i")
            p.ifz(2, "NE", lambda: fn(p, X), lambda: pick(rest[1:]))
            return
        p.iconst(1, ids[0])
        p.if_(0, "EQ", 1, lambda: fn(p, X), lambda: pick(rest[1:]), kind="i")
    pick(arms)
