"""The Monomachine machines' common ground on the DN2's DSP (docs/mnm.md).

They run inside PERC's voice (dnfw.md.voice): a slot's words at I3 as the Machinedrum
machines', the 44.1 kHz stream and its resampler shared. The Monomachine renders 16 frames a
block (2,756.25 blocks a second); a PERC block is 32 samples, so `render` is two of them.

Numbers. The Monomachine's DSP56303 works in 24-bit fractions; here a Q23 word is the float
w / 2^23, as for the Machinedrum (dnfw.md.core). Its phases are kept as 32-bit integers where
the 56300 keeps 48-bit ones (the fraction's low bits dropped), and its rounding (MACR) and
truncations are not reproduced bit for bit: test/test_mnm.py holds every machine to the
Monomachine's own output (its DSP code in an emulator) within a bound.

A slot's words (dnfw.md.core): W[1..8] the eight parameters, each knob / 128 (the
Monomachine's word, knob << 16, as a Q23 fraction); S0.. the machine's state; and the
voice's words below. The parameters are those of the knob positions 0..127.
"""

from __future__ import annotations

from ..md import core as K
from ..perc.dsl import Prog

Q23 = K.Q23
TOP = K.TOP
RATE = 44100.0
FRAMES = 16                                   # a Monomachine block
# the voice's own words for these machines (dnfw.md.core.VW ends at 245)
VW = dict(A=246, F=247, pre=248, pitch=249, i1=250, i2=251, i3=252, i4=253, i5=254)
P0 = 1                                        # W[1..8]: the parameters


def par(p: Prog, d: int, k: int) -> None:
    """Fd = parameter k (0..7) as the Monomachine's Q23 word."""
    K.w(p, d, P0 + k)


def page2(p: Prog, L, d: int, k: int) -> None:
    """Fd = page-2 control k (0..6) as 0..1: PERC's page-2 records (the Machinedrum's track-FX
    records, `dnfw.perc.machines.FX_PARAMS`, which PERC applies only to its own machines), each
    clamp(knob - lo, 0, top) / top. L is the Monomachine layout (its `perc` holds the words)."""
    p.ld(d, L.perc.C[f"q{k}"])


def st(p: Prog, d: int, k: int) -> None:
    K.s(p, d, k)


def sts(p: Prog, k: int, s: int) -> None:
    K.ss(p, k, s)


def vw(p: Prog, d: int, name: str) -> None:
    p.ldi(d, VW[name], 3)


def vws(p: Prog, name: str, s: int) -> None:
    p.sti(VW[name], 3, s)


def knob(p: Prog, d: int, k: int, t: int = 12) -> None:
    """Rd = parameter k's knob position (0..127), an integer."""
    par(p, d, k)
    p.fconst(t, 128.0)
    p.fop(d, d, "*", t)
    p.trunc(d, d)


def sat(p: Prog, x: int, t: int = 12) -> None:
    K.sat(p, x, t)


class Layout:
    """Where the Monomachine voices' shared buffers and tables are (DDR): IN, a render's
    internal samples (up to 192); C, the decimators' coefficients; the tables (`tables`)."""

    def __init__(self, perc, scratch: int, tables: int, render: int | None = None):
        self.perc, self.md = perc, perc.md          # PERC's layout (its EXP2, RECIP) and its MD voices'
        self.scratch, self.tables = scratch, tables
        # v0.43: the render scratch (IN .. DG, RENDER_BYTES) at RENDER (L1) when given; the
        # bookkeeping (perc.program's keys, costs, order, rests, strikes) stays at SCRATCH
        self.render = r = scratch if render is None else render
        self.IN = r                           # 192 floats: the decimator's input
        self.XB = r + 4 * 192                 # 192 ints: SID's phases
        self.YB = r + 4 * 384                 # 192 ints
        self.COEF = r + 4 * 576               # 10 floats
        self.W = {name: r + 4 * (592 + k) for k, name in enumerate(SC_WORDS)}
        # the render scratch keeps the removed machines' places (RENDER_BYTES, dsp.MNM_RENDER_BYTES:
        # what follows it in L1, FDN8's state among it, stays where it is)
        at = r + 4 * (592 + 64)
        self.BUF, self.MIX, self.W1, self.W2 = at, at + 4 * 64, at + 4 * 96, at + 4 * 128   # 64, 32, 32, 32
        self.DG = {name: at + 4 * (160 + k) for k, name in enumerate(("w", "l", "j", "c"))}
        assert self.DG["c"] + 4 - r == RENDER_BYTES
        # the tables (dnfw.md.core TABLE_LAYOUT 'mnm', dnfw.mnm.tables): PLAITS's (SID's, the DPRO
        # machines' and VO-6's until 2026-11-08)
        from .tables import PL_TABLES
        self.PL, t = {}, tables
        for name, n in PL_TABLES:
            self.PL[name] = t
            t += 4 * n


# v0.43: the bytes of the render scratch Layout lays out (IN .. DG), what dsp.MNM_RENDER_BYTES holds
RENDER_BYTES = 4 * (592 + 64 + 164)


SC_WORDS = ("n4", "n5", "half", "inner", "shift", "tmp", "tmp2", "ph", "inc", "len", "hlf", "base",
            "minc", "thr", "c", "x0", "bv",
            # DPRO (dnfw.mnm.dpro)
            "b", "bs", "u", "hf", "sh", "msk", "boff", "i0", "fr", "il", "wx", "g", "m", "out", "k",
            "j", "t", "st", "P", "osc", "bit", "cb", "fb", "w", "y1", "n2", "x1", "fd", "rate", "x48",
            "x49", "wb", "sb", "b2", "y2",
            "i4s",              # the render's caller's I4 (dnfw.mnm.machines._render keeps it)
            "gl")               # v0.56: DDRW's glide word from the DN2's host (0: the Monomachine's 1.0)
