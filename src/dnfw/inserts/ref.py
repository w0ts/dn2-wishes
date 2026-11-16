"""The inserts at 48 kHz, the reference: float32 throughout, every operation in the order the DSP
code (dnfw.inserts.program) does it, so the two agree bit for bit (the SHARC runner holds the
assembled code to this module).

    r = Ref()
    r.block(par_bytes, buffers, route)   # par_bytes: 128 bytes (16 tracks x M.SEL MIX K1..K6),
                                         # buffers: the 16 voice slots' 32 floats, changed in place;
                                         # route: the track each slot plays (default slot s plays
                                         # track s; a value past 15 plays none)
Each voice slot gets the insert of the track it plays (a track on several voices gets it on each);
a slot's state starts from zeros whenever its track or that track's M.SEL changes.

FUZZ (K1 DRIV, K2 TONE, K3 BIAS, K4 PRE, K5 GATE, K6 LEV), per sample x:
    x = clamp(x, -4, 4)
    lp += (x - lp) a700;  xe = x + (x - lp) pre          (pre-emphasis: the highs pushed in)
    env = max(|x|, env r);  gg += ((env > thr or thr = 0) - gg) k     (the gate, on the output)
    v = clamp(xe g + b, -1, 1);  y = 1.5 v - 0.5 v^3 - (1.5 b - 0.5 b^3)   (the clip, its offset out)
    d = y - dx + R dy;  dx = y;  dy = d                    (the DC blocker)
    t += (d - t) c                                         (TONE)
    x' = x + (t lev gg - x) mod
A track whose M.SEL changes starts its insert from zeros.
"""

from __future__ import annotations

import numpy as np

from ..fdn8.ref import F, exp2, recip, sine, trunc
from . import design as D


class Ref:
    def __init__(self):
        self.st = [[F(0)] * D.STATE_WORDS for _ in range(D.TRACKS)]
        self.last = [(0, 0)] * D.TRACKS          # per slot: (M.SEL, track) it last ran
        self.ring = [np.zeros(D.TP_RING, F) for _ in range(D.TRACKS)]

    def block(self, par: bytes, bufs, route=None) -> None:
        for t in range(D.TRACKS):                  # t: the voice slot
            tr = t if route is None else route[t] & 0xFFFF
            if tr > 15:
                continue
            v = par[8 * tr:8 * tr + 8]
            sel = v[0]
            if sel not in D.BUILT:
                continue
            if (sel, tr) != self.last[t]:
                self.st[t] = [F(0)] * D.STATE_WORDS
                self.last[t] = (sel, tr)
                if sel == D.TAPE:
                    self.ring[t][:] = 0
            p = [F(b) * F(1 / 127) for b in v[1:8]]
            if sel == D.FUZZ:
                self.fuzz(self.st[t], p, bufs[t])
            elif sel == D.TAPE:
                self.tape(t, self.st[t], p, bufs[t])
            elif sel == D.FOLD:
                self.fold(self.st[t], p, bufs[t])
            elif sel == D.HARM:
                self.harm(self.st[t], p, bufs[t])

    def fuzz(self, s, p, buf) -> None:
        mod, drv, tone, bias, pre, gate, lev = p
        g = drv * F(D.FZ_DRIVE_OCT)
        g = exp2(g)
        c = tone * F(D.LOG2_TONE_SPAN)
        c = exp2(c)
        c = c * F(D.W_TONE)
        c = exp2(c)
        c = F(1.0) - c
        b = bias * F(D.FZ_BIAS_MAX)
        y0 = b * b
        y0 = y0 * b
        y0 = y0 * F(0.5)
        b15 = b * F(1.5)
        y0 = b15 - y0
        k = pre * F(D.FZ_PRE_MAX)
        thr = gate * F(D.FZ_GATE_MAX)
        lp, env, gg, dx, dy, tl = s[0], s[1], s[2], s[3], s[4], s[5]
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            u = x - lp
            u = u * F(D.FZ_PRE_A)
            lp = lp + u
            h = x - lp
            h = h * k
            xe = x + h
            a = max(x, F(0.0) - x)
            env = env * F(D.FZ_ENV_REL)
            env = max(a, env)
            tg = F(1.0)
            if thr > F(0.0) and not env > thr:
                tg = F(0.0)
            tg = tg - gg
            tg = tg * F(D.FZ_GATE_K)
            gg = gg + tg
            v = xe * g
            v = v + b
            v = max(v, F(-1.0))
            v = min(v, F(1.0))
            v3 = v * v
            v3 = v3 * v
            v3 = v3 * F(0.5)
            y = v * F(1.5)
            y = y - v3
            y = y - y0
            d = y - dx
            r = dy * F(D.FZ_DC_R)
            d = d + r
            dx, dy = y, d
            w = d - tl
            w = w * c
            tl = tl + w
            o = tl * lev
            o = o * gg
            o = o - x
            o = o * mod
            buf[j] = x + o
        s[0], s[1], s[2], s[3], s[4], s[5] = lp, env, gg, dx, dy, tl

    def tape(self, t, s, p, buf) -> None:
        """TAPE: state s0 the age one-pole, s1 / s2 the wow / flutter phases, s3 the delay at the
        last block's end (0: none yet), s4 the noise, s5 the ring's write place"""
        mod, drv, wow, wrat, flut, age, hiss = p
        gd = drv * F(D.TP_DRIVE_OCT)
        gd = exp2(gd)
        wd = wow * F(D.TP_WOW_MAX)
        fd = flut * F(D.TP_FLUT_MAX)
        hz = wrat * F(D.LOG2_WRAT_SPAN)
        hz = exp2(hz)
        hz = hz * F(D.TP_WRAT_LO * D.PH_PER_HZ)
        inc = trunc(hz)
        phw = (int(s[1]) + inc) & 0xFFFFFFFF
        phf = (int(s[2]) + D.TP_FLUT_INC) & 0xFFFFFFFF
        d1 = sine(phw)
        d1 = d1 * wd
        sf = sine(phf)
        sf = sf * fd
        d1 = d1 + sf
        d1 = d1 + F(D.TP_D0)
        d0 = F(s[3])
        if d0 == F(0.0):
            d0 = d1
        step = d1 - d0
        step = step * F(1 / D.BLOCK)
        c = age * F(-3.0)
        c = exp2(c)
        c = c * F(D.W_AGE)
        c = exp2(c)
        c = F(1.0) - c
        lvl = hiss * hiss
        lvl = lvl * F(D.TP_HISS_MAX)
        lp, seed, wp = s[0], int(s[4]), int(s[5])
        ring = self.ring[t]
        d = d0
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            xs = x * gd
            xs = max(xs, F(-D.TP_SAT_MAX))
            xs = min(xs, F(D.TP_SAT_MAX))
            t2 = xs * xs
            num = t2 + F(27.0)
            num = num * xs
            den = t2 * F(9.0)
            den = den + F(27.0)
            y = num * recip(den)
            wp = (wp + 1) & (D.TP_RING - 1)
            ring[wp] = y
            d = d + step
            i = trunc(d)
            fr = d - F(i)
            y0 = ring[(wp - i) & (D.TP_RING - 1)]
            y1 = ring[(wp - i - 1) & (D.TP_RING - 1)]
            y1 = y1 - y0
            y1 = y1 * fr
            r = y0 + y1
            u = r - lp
            u = u * c
            lp = lp + u
            seed = (seed * D.LCG_A + D.LCG_C) & 0xFFFFFFFF
            n = F(float(seed - (1 << 32) if seed >> 31 else seed) * 2.0 ** -31)
            n = n * lvl
            o = lp + n
            o = o - x
            o = o * mod
            buf[j] = x + o
        s[0], s[1], s[2], s[3], s[4], s[5] = lp, phw, phf, d1, seed, wp

    @staticmethod
    def tone_c(p) -> np.float32:
        """a one-pole's coefficient at 300 Hz x 40^p (FUZZ's TONE)"""
        c = p * F(D.LOG2_TONE_SPAN)
        c = exp2(c)
        c = c * F(D.W_TONE)
        c = exp2(c)
        return F(1.0) - c

    def fold(self, s, p, buf) -> None:
        """FOLD: state s0 dx, s1 dy (the DC blocker), s2 the tone one-pole"""
        mod, amnt, symm, shpe, tone, lev, _ = p
        g = amnt * F(D.FD_GAIN_OCT)
        g = exp2(g)
        b = symm - F(0.5)
        b = b * F(2 * D.FD_BIAS_MAX)
        c = self.tone_c(tone)
        dx, dy, tl = s[0], s[1], s[2]
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            v = x * g
            v = v + b
            u = v * F(0.25)
            u = u + F(0.25 + D.FD_OFFSET)
            i = trunc(u)
            fr = u - F(i)
            a = fr - F(0.5)
            a = max(a, F(0.0) - a)
            tri = a * F(4.0)
            tri = tri - F(1.0)
            ph = trunc(fr * F(2.0 ** 31))
            ph = ((ph << 1) - (1 << 30)) & 0xFFFFFFFF
            sn = sine(ph)
            sn = sn - tri
            sn = sn * shpe
            y = tri + sn
            d = y - dx
            r = dy * F(D.FZ_DC_R)
            d = d + r
            dx, dy = y, d
            w = d - tl
            w = w * c
            tl = tl + w
            o = tl * lev
            o = o - x
            o = o * mod
            buf[j] = x + o
        s[0], s[1], s[2] = dx, dy, tl

    def harm(self, s, p, buf) -> None:
        """HARM: state s0 the band's one-pole, s1 dx, s2 dy, s3 the tone one-pole"""
        mod, amnt, freq, even, tone, lev, _ = p
        a = freq * F(D.LOG2_HM_SPAN)
        a = exp2(a)
        a = a * F(D.W_HM)
        a = exp2(a)
        a = F(1.0) - a
        c = self.tone_c(tone)
        k = amnt * F(D.HM_AMNT_MAX)
        lp, dx, dy, tl = s[0], s[1], s[2], s[3]
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            u = x - lp
            u = u * a
            lp = lp + u
            bnd = x - lp
            bnd = bnd * F(D.HM_DRIVE)
            bnd = max(bnd, F(-1.0))
            bnd = min(bnd, F(1.0))
            e = bnd * bnd
            o = e * bnd
            o = o * F(4.0)
            t3 = bnd * F(3.0)
            o = o - t3
            e = e - o
            e = e * even
            h = o + e
            d = h - dx
            r = dy * F(D.FZ_DC_R)
            d = d + r
            dx, dy = h, d
            w = d - tl
            w = w * c
            tl = tl + w
            y = tl * k
            y = x + y
            y = y * lev
            y = y - x
            y = y * mod
            buf[j] = x + y
        s[0], s[1], s[2], s[3] = lp, dx, dy, tl
