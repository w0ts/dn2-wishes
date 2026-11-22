"""FDN8 at 48 kHz, the reference: float32 throughout, every operation in the order the DSP
code (dnfw.fdn8.program) does it, so the two agree bit for bit (the SHARC runner checks the
assembled code against this module). numpy's float32 does the arithmetic (IEEE single,
rounded to nearest), not the DSL's own model, so the check compares two implementations.

    r = Ref()
    out = r.block(type_word, in_l, in_r, params)   # -> (out_l, out_r) or "stock"

`params` are the reverb's parameter struct as the stock unpack leaves it at 0x257918
(+0 PRE, +4 DEC, +8 FREQ, +0xc GAIN, +0x10 HPF, +0x14 LPF: knob / 127, smoothed): with
TYPE = FDN8, PRE is the pre-delay, DEC the SIZE, FREQ the DAMP, GAIN the modulation, HPF and
LPF the input filters. The TYPE word is the frame's k 48 (Reverb FX Routing): 0 is FDN8,
anything else the stock reverb (every kit stores 1).

The design's arithmetic, and where it comes from (optimist reverb_alt.c rvf_params, rv_lfo,
rv_step; rev_math.c rv_exp2n):
- SIZE s = DEC x 127, through design.SIZE_MAP (the knob's travel, identity up to 90): below the knee (90) the ROOM's decay kt(s) = (14647 - 135 s + s^2 (23109
  - 44 s) / 2^16) / 2^24 log2 per 22.05 kHz sample; above it the decay time doubles every 11
  steps, and 2.25 doublings more from 126 to 127 (optimist: a step at 127; here linear over
  the last step, as the knob is smoothed). Each line's gain 2^(-kt' (L + CM)), kt' = kt x
  22050/48000 x 31/32 x 2^(-doublings).
- DAMP d = FREQ x 127: optimist's cubic gives the mean line's one-pole coefficient a; each line's
  c gives at 4 kHz the mean's loss (in dB, at 22.05 kHz) times its length / 978 times the
  decay's slowing (rv_lpc), solved here at 48 kHz: 1 + K48 q = (1 + K22 a / (1 - a)^2)^(sc),
  c = 2q / (2q + 1 + sqrt(4q + 1)).
- The modulation (MOD = GAIN x 2): 4 .. 8 samples at 22.05 kHz (growing above the knee) x
  48/22.05 x MOD; each line's read D + eta (optimist's first-order allpass for the fraction,
  its series for (1 - f) / (1 + f)).
- The diffusers 0.75 / 0.625, growing to 0.8 / 0.7 above the knee; the send 13000 / 2^15,
  2^(-doublings / 8) above it; the wet 7670 / 2^13.
- PRE: 0 .. 100 ms (square law); HPF 20 Hz .. 2 kHz and LPF 200 Hz .. 20 kHz, one-poles.
The approximations (exp2, log2, 1/x, sqrt, the LFO's sine) are fixed polynomials and Newton
steps, the same here as on the DSP.
"""

from __future__ import annotations

import math
import struct

import numpy as np

from . import design as D

F = np.float32
M32 = 0xFFFFFFFF
# 2^f on [0, 1), log2(1 + t) on [0, 1), sin(pi y) / y in y^2 on [-0.5, 0.5]: least squares on
# Chebyshev nodes, as float32 (errors 1.2e-7, 3.2e-7, 1.9e-8)
EXP2_C = (0.9999998807907104, 0.6931546330451965, 0.24014076590538025, 0.055863283574581146,
          0.00894621480256319, 0.0018951073288917542)
LOG2_C = (3.1969781844054523e-07, 1.4426521062850952, -0.7203866243362427, 0.4724995195865631,
          -0.3231159448623657, 0.19042083621025085, -0.07684872299432755, 0.014778721146285534)
SIN_C = (3.1415927410125732, -5.167710781097412, 2.5500917434692383, -0.5983936190605164,
         0.0778845027089119)
RECIP_MAGIC = 0x7EF311C3
RSQRT_MAGIC = 0x5F3759DF
NEWTON = 3

# derived constants, float32 (the DSP code loads these same values)
K_KT = D.K_KT                                    # (design's since 2026-11-22: the active table carries them, HALF its own)
LOG2_100 = math.log2(D.FILT_SPAN)
W_HPF, W_LPF, DEP_GROW = D.W_HPF, D.W_LPF, D.DEP_GROW
CHUNK = 4096                                     # words cleared a block after a switch (the stock buffers; FDN8 / LONG
                                                 # until 2026-11-21)
# 2026-11-21 (fx-fast): FDN8 / LONG clear only the ring's window a fresh engine reads before it writes: every access is at
# p + off, 0 <= off < RB_END (stages.py), and p counts down, so a word enters at offset 0 (written first) unless it lay in
# [p, p + RB_END) when the engine started. The same CLEAR_BLOCKS silent blocks as before (the same output), each
# clearing WIN[type] words from p rounded down to 16 (so 32 x WIN >= RB_END + 15); the ring's other words keep what
# they held (never read before written). False: the whole ring, CHUNK a block (the A/B reference).
WINDOW_CLEAR = True
CLEAR_BLOCKS = D.RING_WORDS // CHUNK             # 32
WIN = {1: 1264, 2: 2352, 3: 672}                 # FDN8, LONG, HALF (the bus inserts): words a clearing block
assert all(w % 16 == 0 and CLEAR_BLOCKS * w >= e + 15
           for w, e in ((WIN[1], D.RB_END), (WIN[2], D.RB_ENDL), (WIN[3], D.RB_ENDH)))
# the stock reverb's sample buffers in its DDR state (0x80000018; notes of Digiwerk T3.4 3.3,
# measured again by the runner's fdn8 step): pre-delay, 8 diffusers, the two tank sets
STOCK_STATE = 0x80000018
STOCK_BUFS = ((0x38, 0x10038), (0x10218, 0x18218), (0x182E8, 0x382E8), (0x38588, 0x58588))
STOCK_WORDS = sum(b - a for a, b in STOCK_BUFS) // 4


def bits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def flt(b: int) -> np.float32:
    return F(struct.unpack("<f", struct.pack("<I", b & M32))[0])


def s32(v: int) -> int:
    v &= M32
    return v - (1 << 32) if v >> 31 else v


def trunc(x) -> int:
    return int(math.trunc(float(x)))


def poly(c, t) -> np.float32:
    """Horner, the top coefficient first: ((c_n t + c_n-1) t + ...) t + c_0"""
    p = F(c[-1])
    for k in range(len(c) - 2, -1, -1):
        p = p * t
        p = p + F(c[k])
    return p


def exp2(x) -> np.float32:
    """2^x for -100 <= x <= 7 (clamped below): 2^floor(x) built in the exponent bits, times
    the polynomial of the fraction"""
    x = max(F(x), F(-100.0))
    n = trunc(x)
    if F(n) > x:
        n -= 1
    f = x - F(n)
    return poly(EXP2_C, f) * flt((n + 127) << 23)


def log2(y) -> np.float32:
    """log2(y) for y >= 1: the exponent, plus the polynomial of the mantissa - 1"""
    b = bits(y)
    e = (b >> 23) - 127
    m = flt((b & 0x7FFFFF) | 0x3F800000)
    t = m - F(1.0)
    return F(e) + poly(LOG2_C, t)


def recip(x) -> np.float32:
    """1/x for normal x > 0: the bit guess, then NEWTON steps r (2 - x r)"""
    r = flt(RECIP_MAGIC - bits(x))
    for _ in range(NEWTON):
        t = x * r
        t = F(2.0) - t
        r = r * t
    return r


def sqrt(x) -> np.float32:
    """sqrt(x) for x >= 1: x / sqrt(x) by the bit guess of 1/sqrt(x) and NEWTON steps"""
    y = flt(RSQRT_MAGIC - (bits(x) >> 1))
    h = x * F(0.5)
    for _ in range(NEWTON):
        t = y * y
        t = h * t
        t = F(1.5) - t
        y = y * t
    return x * y


def sine(ph: int) -> np.float32:
    """sin(2 pi ph / 2^32): y in [-1, 1) half-turns, folded into [-0.5, 0.5], an odd polynomial"""
    y = F(float(s32(ph)) * 2.0 ** -31)
    if y > F(0.5):
        y = F(1.0) - y
    elif y < F(-0.5):
        y = F(-1.0) - y
    z = y * y
    return poly(SIN_C, z) * y


def size_map(s) -> np.float32:
    """the knob's SIZE -> optimist's (design.SIZE_MAP): the hinges summed, then added (s exactly below the knee),
    held to 127 (the knob's top exactly where it was)"""
    acc = F(0.0)
    for p, c in D.SIZE_HINGES:
        t = s - F(p)
        t = max(t, F(0.0))
        t = t * F(c)
        acc = acc + t
    s = s + acc
    return min(s, F(127.0))


class Ref:
    def __init__(self):
        self.ring = np.zeros(D.RING_WORDS, F)
        self.p = 0
        self.ph = list(D.LFO_PH0)
        self.ap = [F(0)] * 8
        self.lp = [F(0)] * 8
        self.hs = self.ls = F(0)
        self.last: list[int] | None = None
        self.cur = 0                                 # 0 the stock reverb, 1 FDN8, 2 LONG
        self.vt = D.variant(1)
        self.clr = 0                                 # words still to clear for the type switched to
        self.pos = 0
        self.g = [F(0)] * 8
        self.c = [F(0)] * 8
        self.dq = self.g1 = self.g2 = self.gh = self.ah = self.al = F(0)
        self.pd = 0
        self.sd, self.f, self.wdl, self.wdr = F(1.0), F(0.0), F(1.0), F(0.0)
        self.cleared: list[tuple[int, int]] = []      # (DDR address, words) the stock clears asked for

    # -- the parameters, when one changed --------------------------------------------------
    def params(self, par) -> None:
        pr = [min(max(F(x), F(0.0)), F(1.0)) for x in par]
        s = pr[1] * F(127.0)
        d = pr[2] * F(127.0)
        s = size_map(s)
        y = max(s - F(D.KNEE), F(0.0))
        sk = s - y
        t = F(44.0) * sk
        t = F(23109.0) - t
        t = t * sk
        t = t * sk
        t = t * F(1 / 65536)
        u = F(135.0) * sk
        kt = F(14647.0) - u
        kt = kt + t
        kt = kt * F(self.vt["kkt"])
        e = y * F(D.DBL_PER_STEP)
        fz = s - F(126.0)
        fz = min(max(fz, F(0.0)), F(1.0))
        fz = fz * F(D.FRZ)
        e = e + fz
        rho = exp2(F(0.0) - e)
        ktr = kt * rho
        ktr = ktr * F(self.vt["ktv"])
        for k in range(8):
            self.g[k] = exp2(ktr * F(-(self.vt["L"][k] + self.vt["cm"])))
        c0, c1, c2, c3 = D.DAMP_C
        w = F(c3) * d
        w = F(c2) - w
        dd = d * d
        w = w * dd
        w = w * F(1 / 65536)
        kq = d * F(c1 / 256)
        kq = F(c0) - kq
        kq = kq - w
        kq = min(max(kq, F(1.0)), F(32767.0))
        a = kq * F(1 / 32768)
        a = F(1.0) - a
        a = min(a, F(D.A_MAX))
        om = F(1.0) - a
        om = om * om
        q = a * recip(om)
        z = q * F(D.K22)
        z = z + F(1.0)
        v = log2(z)
        rl = rho * F(1 / D.LREF)
        for k in range(8):
            sc = rl * F(self.vt["sl"][k])
            tt = v * sc
            tt = min(tt, F(D.T_MAX))
            pp = exp2(tt)
            qq = pp - F(1.0)
            qq = qq * F(self.vt["kinv"])
            tq = qq + qq
            f4 = qq * F(4.0)
            f4 = f4 + F(1.0)
            den = tq + F(1.0)
            den = den + sqrt(f4)
            self.c[k] = tq * recip(den)
        dg = y * F(self.vt["dgrow"])
        dg = dg + F(self.vt["fexc"])
        m = pr[3] * F(D.MOD_MAX)
        self.dq = dg * m
        pp = pr[0] * pr[0]
        pp = pp * F(float(self.vt["pd"]))
        self.pd = min(trunc(pp), self.vt["pd"])
        self.g1 = y * F(0.05 / 37) + F(0.75)
        self.g2 = y * F(0.075 / 37) + F(0.625)
        x = e * F(-0.125)
        self.gh = exp2(x) * F(D.GIN * 0.5)
        w = pr[4] * F(LOG2_100)
        w = exp2(w) * F(self.vt["whp"])
        self.ah = F(1.0) - exp2(w)
        w = pr[5] * F(LOG2_100)
        w = exp2(w) * F(self.vt["wlp"])
        self.al = F(1.0) - exp2(w)

    def extras(self, ex) -> None:
        """the second page's values (design.EX): ex None, or its change word 0, the constants (every instance); else
        (change word, sd, f, wl, wr) as the ColdFire sends them (design.derive)"""
        if ex is None or not ex[0]:
            self.sd, self.f, self.wdl, self.wdr = F(1.0), F(0.0), F(1.0), F(0.0)
        else:
            self.sd, self.f, self.wdl, self.wdr = (F(x) for x in ex[1:5])

    # -- per block: the lines' reads -------------------------------------------------------
    def lfo(self) -> list[int]:
        ro = []
        self.eta = []
        for k in range(8):
            self.ph[k] = (self.ph[k] + D.LFO_INC[k]) & M32
            sn = sine(self.ph[k])
            t = self.dq * sn
            t = t + F(self.vt["L"][k] + self.vt["cm"] - 0.5)
            dk = trunc(t)
            fr = t - F(dk)
            h = fr - F(0.5)
            h = h * F(0.5)
            e2 = h * h
            e1 = F(1.0) - h
            e1 = e1 + e2
            eta = h * e1
            self.eta.append(F(0.0) - eta)
            ro.append(self.vt["RL"][k] + dk)
        return ro

    def rd(self, off: int) -> np.float32:
        return self.ring[(self.p + off) & D.RING_MASK]

    def wr(self, off: int, v) -> None:
        self.ring[(self.p + off) & D.RING_MASK] = v

    def run(self, inl, inr):
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
        outl, outr = [], []
        for j in range(D.BLOCK):
            xs = F(inl[j]) + F(inr[j])
            xin = xs * self.gh
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
            for k in range(4):
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
            lg = l * F(D.GOUT)
            rg = r * F(D.GOUT)
            if self.wdr != F(0.0):
                ol = lg * self.wdl
                ol = ol + rg * self.wdr
                orr = rg * self.wdl
                orr = orr + lg * self.wdr
                lg, rg = ol, orr
            outl.append(lg)
            outr.append(rg)
            self.p = (self.p - 1) & M32
        return outl, outr

    # -- the slot's call: the stock reverb, a switch's clearing, or FDN8 --------------------
    def kind(self, tw: int) -> int:
        """the type a TYPE word asks for: 1 FDN8 (0), 2 LONG (0x200), else 0 the stock reverb"""
        return 1 if tw == 0 else 2 if tw == 0x200 else 0

    def block(self, type_word: int, inl, inr, par, ex=None):
        tw = type_word & 0xFFFF
        t = self.kind(tw)
        if t != self.cur:
            self.cur, self.pos = t, 0
            self.clr = (CLEAR_BLOCKS * WIN[t] if WINDOW_CLEAR else D.RING_WORDS) if t else STOCK_WORDS
            if t:
                self.vt = D.variant(t)
                self.ap, self.lp = [F(0)] * 8, [F(0)] * 8
                self.hs = self.ls = F(0)
                self.last = None
        if self.clr:
            n = min(WIN[self.cur] if self.cur and WINDOW_CLEAR else CHUNK, self.clr)
            if self.cur and WINDOW_CLEAR:
                s = (self.p & D.RING_MASK & ~15) + self.pos
                self.ring[[(s + k) & D.RING_MASK for k in range(n)]] = 0
            elif self.cur:
                self.ring[self.pos:self.pos + n] = 0
            else:
                self.cleared.append((self.pos, n))
            self.pos += n
            self.clr -= n
            return [F(0)] * D.BLOCK, [F(0)] * D.BLOCK
        if not self.cur:
            return "stock"
        self.extras(ex)
        pw = [bits(x) for x in par]
        if pw != self.last:
            self.params(par)
            self.last = pw
        return self.run(inl, inr)
