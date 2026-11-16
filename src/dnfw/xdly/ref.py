"""XDLY at 48 kHz, the reference: float32 throughout, every operation in the order the DSP code
(dnfw.xdly.program) does it, so the two agree bit for bit (the SHARC runner holds the assembled
code to this module). numpy's float32 does the arithmetic, not the DSL's model.

    r = Ref()
    out = r.block(type_word, in_l, in_r, params)   # -> (out_l, out_r) or "stock"

`params` are the stock delay's parameter struct as the stock unpack leaves it at 0x257934
(design.P_*): TIME (knob / 127), X (the raw word), WID (knob / 128), FDBK (knob / 128), HPF and
LPF (knob / 127). With TYPE = XDLY: TIME is TIME 1, WID TIME 2, FDBK the feedback, HPF the
cross modulation, LPF the loops' tone; X is not used. The TYPE word is the frame's k 40 (Delay FX
Routing): 0 is XDLY, anything else the stock delay (every kit stores 1).

Optimist's kernel (fx/insfx/xdly.c ifx_xdly_run), per sample, in float:
    x = (l + r) / 2
    da += (ta - da) KF;  db += (tb - db) KF          (the TIMEs followed, ~23 ms)
    fa += (ya - fa) c;   ia = knee(x + fa g)          (the loop's one-pole, its feedback, the clip)
    fb += (yb - fb) c;   ib = knee(x + fb g)
    write ia, ib;  q: zeros written in a row on both; fill: samples written (<= LINE)
    ya' = tap(A, da (1 + yb md)),  yb' = tap(B, db (1 + ya md))   (each moved by the other's last)
    out L = ya', out R = yb'  (the wet; the bus's VOL mixes it, as for the stock delay)
tap: linear between two samples, 0 past what was written since XDLY started (so a start needs
no clearing). knee: linear to 20000 / 32768, above it optimist's tanh knee (softclip of twice
the excess, halved; its table saturates at tanh 2), then clamped to 1. Once both lines hold only
zeros (q = LINE) and a block's input is silent, the block is skipped (its output 0).
Here also: a loop one-pole below FLUSH is set to 0, so a tail ends at exact 0 and nothing ever
reaches the denormal range (optimist rounds toward 0 for the same reason).
"""

from __future__ import annotations

import math

import numpy as np

from ..fdn8.ref import F, bits, exp2, recip, trunc
from . import design as D

FLUSH = F(1e-20)
LOG2E2 = 2.0 / math.log(2)                 # tanh z = 1 - 2 / (2^(z 2 log2 e) + 1)


def tanh(z) -> np.float32:
    e = z * F(LOG2E2)
    e = exp2(e)
    e = e + F(1.0)
    e = recip(e)
    e = e * F(2.0)
    return F(1.0) - e


def knee(v, kn=None) -> np.float32:
    kn = F(D.KNEE) if kn is None else kn
    a = max(v, F(0.0) - v)
    if a > kn:
        z = a - kn
        z = z * F(2.0)
        z = min(z, F(2.0))
        t = tanh(z)
        t = t * F(0.5)
        a = t + kn
        a = min(a, F(1.0))
        return a if v > F(0.0) else F(0.0) - a
    return v


class Ref:
    def __init__(self):
        self.a = np.zeros(D.LINE, F)
        self.b = np.zeros(D.LINE, F)
        self.wp = self.fill = self.q = 0
        self.da = self.db = self.ya = self.yb = self.fa = self.fb = F(0)
        self.ta = self.tb = self.md = self.g = self.c = F(0)
        self.kf, self.kn, self.wl, self.wr, self.sn = F(D.KF), F(D.KNEE), F(1.0), F(0.0), F(0.0)
        self.cur = 0                              # 0 the stock delay, 1 XDLY
        self.clr = 0
        self.pos = 0
        self.cleared: list[tuple[int, int]] = []  # (word, words) of the stock area the clears asked for

    def extras(self, ex) -> None:
        """the second page's values (design.EX): ex None, or its change word 0, the constants (every instance);
        else (change word, kf, kn, wl, wr, sn) as the ColdFire sends them (design.derive)"""
        if ex is None or not ex[0]:
            self.kf, self.kn, self.wl, self.wr, self.sn = F(D.KF), F(D.KNEE), F(1.0), F(0.0), F(0.0)
        else:
            self.kf, self.kn, self.wl, self.wr, self.sn = (F(x) for x in ex[1:6])

    def params(self, par, ex=None) -> None:
        self.extras(ex)
        pr = [min(max(F(x), F(0.0)), F(1.0)) for x in par]
        t = pr[D.P_TIME] * F(D.LOG2_TSPAN)
        t = t + F(D.LOG2_TMIN)
        self.ta = exp2(t)
        w = pr[D.P_WID] * F(D.WID_TO_KNOB)
        w = min(w, F(1.0))
        w = w * F(D.LOG2_TSPAN)
        w = w + F(D.LOG2_TMIN)
        self.tb = exp2(w)
        self.md = pr[D.P_HPF] * F(D.MOD_GAIN)
        self.g = pr[D.P_FDBK] * F(D.FB_MAX)
        c = pr[D.P_LPF] * F(D.LOG2_TONE_SPAN)
        c = exp2(c)
        c = c * F(D.W_TONE)
        c = exp2(c)
        self.c = F(1.0) - c

    def start(self) -> None:
        self.fill = self.q = 0
        self.ya = self.yb = self.fa = self.fb = F(0)
        self.da, self.db = self.ta, self.tb

    def loop_in(self, x, f, y):
        f2 = y - f
        f2 = f2 * self.c
        f = f + f2
        if max(f, F(0.0) - f) < FLUSH:
            f = F(0.0)
        v = f * self.g
        v = x + v
        return f, knee(v, self.kn)

    def tap(self, line, d) -> np.float32:
        i = trunc(d)
        if i >= self.fill:
            return F(0.0)
        fr = d - F(i)
        y0 = line[(self.wp - i) & D.LINE_MASK]
        y1 = line[(self.wp - i - 1) & D.LINE_MASK] if i + 1 < self.fill else F(0.0)
        y1 = y1 - y0
        y1 = y1 * fr
        return y0 + y1

    def moved(self, d, y) -> np.float32:
        m = y * self.md
        m = m * d
        m = d + m
        m = max(m, F(D.D_LO))
        return min(m, F(D.D_HI))

    def run(self, inl, inr):
        if self.q >= D.LINE and not any(F(x) != 0 for x in inl) and not any(F(x) != 0 for x in inr):
            return [F(0)] * D.BLOCK, [F(0)] * D.BLOCK
        outl, outr = [], []
        for k in range(D.BLOCK):
            l, r = F(inl[k]), F(inr[k])
            dd = l - r
            x = l + r
            x = x * F(0.5)
            if self.sn != F(0.0):
                d = dd * F(0.5)
                d = d * self.sn
                xa, xb = x + d, x - d
            else:
                xa = xb = x
            t = self.ta - self.da
            t = t * self.kf
            self.da = self.da + t
            t = self.tb - self.db
            t = t * self.kf
            self.db = self.db + t
            self.fa, ia = self.loop_in(xa, self.fa, self.ya)
            self.fb, ib = self.loop_in(xb, self.fb, self.yb)
            self.wp = (self.wp + 1) & D.LINE_MASK
            self.a[self.wp] = ia
            self.b[self.wp] = ib
            if ia != F(0) or ib != F(0):
                self.q = 0
            elif self.q < D.LINE:
                self.q += 1
            if self.fill < D.LINE:
                self.fill += 1
            na = self.tap(self.a, self.moved(self.da, self.yb))
            nb = self.tap(self.b, self.moved(self.db, self.ya))
            self.ya, self.yb = na, nb
            if self.wr != F(0.0):
                ol = na * self.wl
                ol = ol + nb * self.wr
                orr = nb * self.wl
                orr = orr + na * self.wr
                na, nb = ol, orr
            outl.append(na)
            outr.append(nb)
        return outl, outr

    def block(self, type_word: int, inl, inr, par, ex=None):
        t = 1 if (type_word & 0xFFFF) == 0 else 0
        if t != self.cur:
            self.cur, self.pos = t, 0
            self.clr = 0 if t else D.STOCK_WORDS
            if t:
                self.params(par, ex)
                self.start()
        if self.clr:
            n = min(D.CHUNK, self.clr)
            self.cleared.append((self.pos, n))
            for line, lo in ((self.a, self.pos), (self.b, self.pos - D.LINE)):
                a0, a1 = max(lo, 0), min(lo + n, D.LINE)
                if a0 < a1:
                    line[a0:a1] = 0
            self.pos += n
            self.clr -= n
            return [F(0)] * D.BLOCK, [F(0)] * D.BLOCK
        if not self.cur:
            return "stock"
        self.params(par, ex)
        return self.run(inl, inr)


def lines_word(r: Ref, addr: int) -> int:
    """the reference's line word at a DDR byte address (for the runner's check)"""
    off = (addr - D.LINE_A) // 4
    return bits(r.a[off] if off < D.LINE else r.b[off - D.LINE])
