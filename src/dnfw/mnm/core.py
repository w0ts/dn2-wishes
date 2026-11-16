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


def page3(p: Prog, L, d: int, k: int) -> None:
    """Fd = page-3 control k (0..1) as 0..1: `dnfw.perc.machines.P3_RECS`' first two, read only for a
    machine that has a page 3 (dnfw.perc.program), each clamp(knob - lo, 0, top) / top."""
    p.ld(d, L.perc.C[f"r{k}"])


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

    def __init__(self, perc, scratch: int, tables: int, dt_at: int | None = None,
                 render: int | None = None, interp_at: int | None = None):
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
        self.COMB = tables + 4 * 33 * 512           # SID's combined waveforms (floats), after the waves
        # v0.26, DPRO-DENS / DPRO-DDRW (dnfw.mnm.dpro): scratch after the words, tables after COMB
        at = r + 4 * (592 + 64)
        self.BUF, self.MIX, self.W1, self.W2 = at, at + 4 * 64, at + 4 * 96, at + 4 * 128   # 64, 32, 32, 32
        self.DG = {name: at + 4 * (160 + k) for k, name in enumerate(("w", "l", "j", "c"))}   # the build's cursor
        assert self.DG["c"] + 4 - r == RENDER_BYTES
        # the tables (dnfw.md.core TABLE_LAYOUT 'mnm', dnfw.mnm.tables): with one of the
        # Monomachine's own machines in this build, its ROM's first (dnfw.mnm.rom.packed_words: the
        # waves, COMB, the DPRO tables, VO-6's, as at 28eb110's parent), then PLAITS's
        from .tables import JU_WORDS, PL_TABLES, mnm_os_on
        t = self.COMB + 4 * 4096
        # v0.36: the DPRO tables are where the fill writes them (DT_SRC, DDR, in the run of the
        # Monomachine tables); with DT_AT given (L2), build() copies them there once and every
        # reader reads them there (DDRW's and DENS's busiest DDR reads, docs/dsp-cost.md)
        self.DT_SRC, self.DT = {}, {}
        self.DT_WORDS = sum(n for _, n in DP_TABLES)
        self.DT_FROM = t
        self.DT_AT = dt_at
        u = dt_at if dt_at is not None else t
        for name, n in DP_TABLES:
            self.DT_SRC[name] = t
            self.DT[name] = u
            t += 4 * n
            u += 4 * n
        # v0.52 (speed): the interpolator's table also in L1 (INTERP_AT, with DT_AT: build() copies it
        # there too), where interp reads it
        self.INTERP_AT = interp_at if dt_at is not None else None
        if self.INTERP_AT is not None:
            self.DT["interp"] = self.INTERP_AT
        self.DIGI = tables + DIGI_OFF               # the Digibank stand-in the DSP builds (ints)
        # v0.26, VO-6 (dnfw.mnm.vo6): its tables after the DPRO ones (rom.vo6_words)
        self.VO = {}
        for name, n in VO_TABLES:
            self.VO[name] = t
            t += 4 * n
        assert t - tables == 4 * MNM_OS_WORDS
        self.PL, t = {}, tables + (4 * MNM_OS_WORDS if mnm_os_on() else 0)
        for name, n in PL_TABLES:
            self.PL[name] = t
            t += 4 * n
        self.JU = t                                 # 2026-11-12: JUNO's tables (dnfw.engines.juno.juno), after PLAITS's
        self.TABLES_END = t + 4 * JU_WORDS
        assert self.TABLES_END <= self.DIGI, "the tables run into the Digibank stand-in"


# v0.43: the bytes of the render scratch Layout lays out (IN .. DG), what dsp.MNM_RENDER_BYTES holds
RENDER_BYTES = 4 * (592 + 64 + 164)


# the DPRO tables after COMB (dnfw.mnm.rom.dpro_words, floats as the fill stores them)
DP_TABLES = (("interp", 320), ("dec2", 9), ("hb", 7), ("pch", 128), ("wid", 256), ("br", 256))
# VO-6's tables after them (dnfw.mnm.rom.vo6_words): the gains, the cosines, the pulse shape,
# the AGC's log mantissas, CLEN's terms, the 21 consonants' set-ups (16 words each) and
# renderers (40 words each), these two field-major
VO_TABLES = (("c1", 4 * 0x620), ("cos", 0x614), ("blit", 0x333 - 0x131 + 1), ("log", 256),
             ("clen", 128), ("trig", 21 * 16), ("cons", 21 * 40))
# their words in all (dnfw.mnm.rom.packed_words): the waves as (hi, lo) pairs, COMB, then the rest;
# PLAITS's follow them (2026-11-11: the five back beside PLAITS)
MNM_OS_WORDS = 33 * 512 + 4096 + sum(n for _, n in DP_TABLES) + sum(n for _, n in VO_TABLES)
DIGI_WORDS = 32 * 2048
DIGI_OFF = 0x46000
"""The stand-in's 256 KB (32 x 2048 words, built by the DSP: dnfw.mnm.dpro.build), from the
Monomachine tables' address, beyond their end and PLAITS's (dnfw.waverider.dsp checks it lies
past every table and before the P-I delay lines). Moves with them."""


SC_WORDS = ("n4", "n5", "half", "inner", "shift", "tmp", "tmp2", "ph", "inc", "len", "hlf", "base",
            "minc", "thr", "c", "x0", "bv",
            # DPRO (dnfw.mnm.dpro)
            "b", "bs", "u", "hf", "sh", "msk", "boff", "i0", "fr", "il", "wx", "g", "m", "out", "k",
            "j", "t", "st", "P", "osc", "bit", "cb", "fb", "w", "y1", "n2", "x1", "fd", "rate", "x48",
            "x49", "wb", "sb", "b2", "y2",
            "i4s",              # the render's caller's I4 (dnfw.mnm.machines._render keeps it)
            "gl")               # v0.56: DDRW's glide word from the DN2's host (0: the Monomachine's 1.0)
