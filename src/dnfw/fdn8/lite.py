"""The bus inserts' FDN8, HALF (2026-11-22, the User's pick after the A/B in scratch/fdn8-bus-ab): the reference.

The send FDN8 (dnfw.fdn8.ref.Ref) is unchanged. The bus inserts' instances (MODE 1, dnfw.inserts.bus) run TYPE 3
"HALF" (design.variant(3)): the tank at 24 kHz, 16 samples a block, with input diffusers 0 and 2 only, between a
19-tap half-band decimator and two half-band interpolators. float32 throughout, every operation in the order the
DSP code (dnfw.fdn8.program / stages, MODE 1) does it, so the two agree bit for bit.

    r = BusRef()                         # one instance
    out_l, out_r = r.block(0, in_l, in_r, par)

Per block: the 32 sums L + R (48 kHz) after the decimator's 17 kept from the last block, Z[0..48]; output j (0..15)
is Z[c] hc + sum_q (Z[c - 1 - 2q] + Z[c + 1 + 2q]) c_q, c = 9 + 2 j (the half-band's centre and its five side
pairs; its even side taps are zero). Then 16 samples of the tank exactly as Ref.run does 32 (design.variant(3)'s
lines, two diffusers), the lines' L / R sums (before GOUT) into a buffer after the 9 kept from the last block, B[0..24];
for each tank sample i (m = 9 + i) two outputs: B[m - 5] G (G = GOUT), then sum_q (B[m - 4 + q] + B[m - 5 - q]) k_q,
k_q = 2 c_q GOUT (the half-band's odd phase, its x 2 for the zeros stuffed between the tank's samples).

The sound (the User's A/B, 2026-11-22): the wet's top at ~9 kHz (-0.1 dB at 8 kHz, -6 dB at 12 kHz), the same decay
time (+2 %, the lengths' primes), a little less smear on sharp hits (two diffusers).
"""

from __future__ import annotations

import numpy as np

from . import design as D
from . import ref as R
from .ref import F

HB_P = 5                                          # side pairs: a 19-tap half-band


def halfband(p: int = HB_P, beta: float = 5.0) -> np.ndarray:
    """a (4p - 1)-tap half-band low-pass, Kaiser-windowed sinc, DC gain 1 (float64)"""
    n = 4 * p - 1
    k = np.arange(n) - (n - 1) / 2
    h = np.sinc(k / 2) / 2 * np.kaiser(n, beta)
    return h / h.sum()


_HB = halfband()
_MID = len(_HB) // 2
assert all(abs(_HB[_MID + 2 * j]) < 1e-12 for j in range(1, HB_P))
HC = float(F(_HB[_MID]))                          # the centre tap
HQ = tuple(float(F(_HB[_MID + 2 * q + 1])) for q in range(HB_P))          # the side taps, nearest first
GO = float(F(D.GOUT))
KQ = tuple(float(F(2.0 * _HB[_MID + 2 * q + 1] * D.GOUT)) for q in range(HB_P))
DEC_HIST = 4 * HB_P - 3                           # 17 sums kept
INT_HIST = 2 * HB_P - 1                           # 9 tank samples kept
NB = D.BLOCK // 2
G_IN = 1 / 14.125                                 # the bus pass's input gain (dnfw.inserts.bus.G_IN), which the DSP
                                                  # applies in the decimator's sums (the reference gets x G_IN already)


class BusRef(R.Ref):
    def __init__(self):
        super().__init__()
        self.dh = [F(0)] * DEC_HIST
        self.ih = {0: [F(0)] * INT_HIST, 1: [F(0)] * INT_HIST}

    def kind(self, tw: int) -> int:
        return 3 if tw == 0 else 0

    def run(self, inl, inr):
        if self.cur != 3:
            return super().run(inl, inr)
        ro = self.lfo()
        g1x = self.g1 * self.sd
        g1x = min(g1x, F(D.DF_MAX))
        g2x = self.g2 * self.sd
        g2x = min(g2x, F(D.DF_MAX))
        omf = F(1.0) - self.f
        gx = []
        for k in range(8):
            t = self.g[k] * omf
            gx.append(t + self.f)
        gd = (g1x, g1x, g2x, g2x)
        xd = self.decimate(inl, inr)
        ls_, rs_ = [], []
        for j in range(NB):
            xin = xd[j] * self.gh
            t = xin - self.hs
            t = self.ah * t
            self.hs = self.hs + t
            x = xin - self.hs
            t = x - self.ls
            t = self.al * t
            self.ls = self.ls + t
            x = self.ls
            self.wr(D.RB_PD, x)
            x = self.rd(D.RB_PD + self.pd)
            for k in D.HALF_DIFF:
                b = self.rd(self.vt["RA"][k] + self.vt["A"][k])
                v = gd[k] * b
                v = x + v
                self.wr(self.vt["RA"][k], v)
                w = gd[k] * v
                x = b - w
            f = []
            for k in range(8):
                u0 = self.rd(ro[k])
                u1 = self.rd(ro[k] + 1)
                t = u0 - self.ap[k]
                t = self.eta[k] * t
                o = u1 + t
                self.ap[k] = o
                t = self.lp[k] - o
                t = self.c[k] * t
                lp = o + t
                self.lp[k] = lp
                fk = lp * gx[k]
                f.append(fk)
                s = fk if k == 0 else s + fk
                if k == 0:
                    l = o
                elif k == 1:
                    r = o
                elif k in (2, 6):
                    l = l - o
                elif k in (3, 7):
                    r = r - o
                elif k == 4:
                    l = l + o
                else:
                    r = r + o
            s = s * F(0.25)
            for k in range(8):
                w = s - f[k]
                w = w + x if k % 2 == 0 else w - x
                self.wr(self.vt["RL"][k], w)
            ls_.append(l)
            rs_.append(r)
            self.p = (self.p - 1) & R.M32
        assert self.wdr == F(0.0), "the bus instances never widen (extras' defaults)"
        return self.interp(0, ls_), self.interp(1, rs_)

    def decimate(self, inl, inr) -> list:
        z = self.dh + [F(inl[n]) + F(inr[n]) for n in range(D.BLOCK)]
        out = []
        for j in range(NB):
            c = 9 + 2 * j                         # the 19 taps Z[c - 9 .. c + 9] (newest: xs[2 j + 1] at Z[18 + 2 j])
            acc = z[c] * F(HC)
            for q in range(HB_P):
                t = z[c - 1 - 2 * q] + z[c + 1 + 2 * q]
                t = t * F(HQ[q])
                acc = acc + t
            out.append(acc)
        self.dh = z[D.BLOCK:]
        return out

    def interp(self, ch: int, ys) -> list:
        b = self.ih[ch] + list(ys)
        out = []
        for i in range(NB):
            m = INT_HIST + i
            out.append(b[m - 5] * F(GO))
            t = b[m - 4] + b[m - 5]
            acc = t * F(KQ[0])
            for q in range(1, HB_P):
                t = b[m - 4 + q] + b[m - 5 - q]
                t = t * F(KQ[q])
                acc = acc + t
            out.append(acc)
        self.ih[ch] = b[NB:]
        return out
