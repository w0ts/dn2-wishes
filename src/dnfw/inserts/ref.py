"""The inserts at 48 kHz, the reference: float32 throughout, every operation in the order the DSP
code (dnfw.inserts.program) does it, so the two agree bit for bit (the SHARC runner holds the
assembled code to this module).

    r = Ref()
    r.block(par_bytes, buffers, route)   # par_bytes: the records, 32 x 8 bytes (track t's slot j at
                                         # 8 (2 t + j): type | instance << 4, MIX, K1..K6),
                                         # buffers: the 16 voice slots' 32 floats, changed in place;
                                         # route: the track each slot plays (default slot s plays
                                         # track s; a value past 15 plays none)
Each voice slot gets the inserts of the track it plays (a track on several voices gets them on each),
slot 1 then slot 2; a (voice slot, insert slot)'s state starts from zeros whenever its track or that
insert slot's type changes.

FUZZ (K1 DRIV, K2 TONE, K3 BIAS, K4 PRE, K5 GATE, K6 LEV), per sample x:
    x = clamp(x, -4, 4)
    lp += (x - lp) a700;  xe = x + (x - lp) pre          (pre-emphasis: the highs pushed in)
    env = max(|x|, env r);  gg += ((env > thr or thr = 0) - gg) k     (the gate, on the output)
    v = clamp(xe g + b, -1, 1);  y = 1.5 v - 0.5 v^3 - (1.5 b - 0.5 b^3)   (the clip, its offset out)
    d = y - dx + R dy;  dx = y;  dy = d                    (the DC blocker)
    t += (d - t) c                                         (TONE)
    x' = x + (t lev gg - x) mod
A track whose M.SEL changes starts its insert from zeros.

SUB, DIST, GATER and RING (2026-11-09) are ported from Optimist (GPL-3.0-only, the User's own):
firmware/src/fx/insfx/insfx.c (ifx_mod: RING, SUB), firmware/src/fx/fx.c (dist_gains, dist_run: DIST),
firmware/src/fx/insfx/gater.c (GATER, its patterns IGT_PAT); rewritten here in float32, what changed in
docs/inserts.md. DIST runs FUZZ's sample loop (fz_loop) with its own block values. 2026-11-10: types
9..12 on the two-slot design, in either slot, each (voice slot, insert slot) its own state; GATER's
clock word at design.CLK (the values' word 1).
"""

from __future__ import annotations

import numpy as np

from ..fdn8.ref import F, exp2, recip, sine, sqrt, trunc
from . import design as D


class Ref:
    def __init__(self):
        self.st = [[F(0)] * D.STATE_WORDS for _ in range(D.RECORDS)]
        self.last = [(0, 0)] * D.RECORDS         # per (voice slot, insert slot): (type, track) it last ran
        self.ring = [np.zeros(D.TP_RING, F) for _ in range(D.RECORDS)]
        self.au = [[F(0), F(0)] for _ in range(D.RECORDS)]   # AUTO's powers (design.AUTO_L2): Pin, Pout

    def block(self, par: bytes, bufs, route=None, tempo: int = 0, clk: int = 0) -> None:
        """TEMPO: the frame's BPM x 120 (0: 120 BPM); CLK: the ColdFire's clock word (design.CLK)"""
        self.tempo, self.clk = tempo & 0xFFFF, clk & 0xFFFFFFFF
        for i in range(D.RECORDS):                 # i = 2 t + j: voice slot t, insert slot j
            t, j = i >> 1, i & 1
            tr = t if route is None else route[t] & 0xFFFF
            if tr > 15:
                continue
            if j == 1 and D.moved(par, tr):     # 2026-11-11: the bus pass runs it (dnfw.inserts.busref)
                continue
            self.one(i, tr, par[8 * (2 * tr + j):8 * (2 * tr + j) + 8], bufs[t])

    def one(self, k: int, tr: int, v: bytes, buf) -> None:
        """record V (played by track TR) over BUF in place, with state / ring K (program.one)"""
        sel = v[0] & ((1 << D.TYPE_BITS) - 1)
        if sel not in D.BUILT:
            return
        if (sel, tr) != self.last[k]:
            self.st[k] = [F(0)] * D.STATE_WORDS
            self.au[k] = [F(0), F(0)]
            self.last[k] = (sel, tr)
            if sel == D.TAPE:
                self.ring[k][:] = 0
        p = [F(b) * F(1 / 127) for b in v[1:8]]
        self.k = k
        if sel == D.FUZZ:
            self.fuzz(self.st[k], p, buf)
        elif sel == D.TAPE:
            self.tape(k, self.st[k], p, buf)
        elif sel == D.FOLD:
            self.fold(self.st[k], p, buf)
        elif sel == D.HARM:
            self.harm(self.st[k], p, buf)
        elif sel == D.SUB:
            self.sub(self.st[k], p, buf)
        elif sel == D.DIST:
            self.dist(self.st[k], p, buf)
        elif sel == D.GATER:
            self.gater(self.st[k], p, buf)
        elif sel == D.RING:
            self.ring_mod(self.st[k], p, buf)

    def auto_gain(self, on, t) -> np.float32:
        """AUTO's gain for this block (program.auto_pre): 1.0 off, else T x sqrt(Pin / Pout)"""
        a = self.au[self.k]
        pi = max(a[0], F(D.AUTO_FLOOR))
        po = max(a[1], F(D.AUTO_FLOOR))
        r = recip(po)
        r = r * pi
        r = max(r, F(D.AUTO_R_MIN))
        r = min(r, F(D.AUTO_R_MAX))
        c = sqrt(r)
        c = c * t
        return c if on else F(1.0)

    def auto_end(self, si, so) -> None:
        """the block's sums of squares into the powers (program.auto_post)"""
        a = self.au[self.k]
        for n, x in ((0, si), (1, so)):
            m = x * F(1 / 32)
            d = m - a[n]
            d = d * F(D.AUTO_A)
            a[n] = a[n] + d

    def fuzz(self, s, p, buf) -> None:
        mod, drv, tone, bias, pre, gate, lev = p
        g = drv * F(D.FZ_DRIVE_OCT)
        g = exp2(g)
        k = pre * F(D.FZ_PRE_MAX)
        thr = gate * F(D.FZ_GATE_MAX)
        v = dict(g=g, k=k, thr=thr, pa=F(D.FZ_PRE_A), rel=F(D.FZ_ENV_REL), a1=F(1.0), lv=lev, kl=F(0.0),
                 au=False, at=F(0.0))
        self.fz_loop(s, v, tone, bias, mod, buf)

    def dist(self, s, p, buf) -> None:
        """DIST: FUZZ's loop, the drive over the peak (s1, the follower), the low band dry (s0)"""
        mod, drv, tone, bias, low, lev, auto = p
        gd = drv * F(D.DS_DRIVE_OCT)
        gd = exp2(gd)
        gd = gd * F(D.DS_DRIVE_LO)
        pk = max(F(s[1]), F(D.DS_FLOOR))
        g = recip(pk)
        g = gd * g
        m = min(gd, F(1.0))
        m = m * F(1.5)
        m = recip(m)
        lv = lev * F(D.DS_LEV_MAX)
        lv = lv * pk
        lv = lv * m
        pa = self.pole_c(low, D.W_DL, D.LOG2_DL_SPAN)
        v = dict(g=g, k=F(1.0), thr=F(0.0), pa=pa, rel=F(D.DS_REL), a1=F(0.0), lv=lv, kl=F(1.0),
                 au=auto > F(D.AUTO_ON), at=lev * F(D.DS_LEV_MAX))
        self.fz_loop(s, v, tone, bias, mod, buf)

    def fz_loop(self, s, v, tone, bias, mod, buf) -> None:
        """FUZZ's and DIST's sample loop; state s0 lp, s1 env, s2 gg, s3 dx, s4 dy, s5 tl"""
        g, k, thr, pa, rel, a1, lev, kl = (v[n] for n in ("g", "k", "thr", "pa", "rel", "a1", "lv", "kl"))
        c = self.tone_c(tone)
        b = bias * F(D.FZ_BIAS_MAX)
        y0 = b * b
        y0 = y0 * b
        y0 = y0 * F(0.5)
        b15 = b * F(1.5)
        y0 = b15 - y0
        lp, env, gg, dx, dy, tl = s[0], s[1], s[2], s[3], s[4], s[5]
        ac = self.auto_gain(v["au"], v["at"])
        si = so = F(0.0)
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            u = x - lp
            u = u * pa
            lp = lp + u
            h = x - lp
            h = h * k
            xe = x * a1
            xe = xe + h
            a = max(x, F(0.0) - x)
            env = env * rel
            env = max(a, env)
            tg = F(1.0)
            if thr > F(0.0) and not env > thr:
                tg = F(0.0)
            tg = tg - gg
            tg = tg * F(D.FZ_GATE_K)
            gg = gg + tg
            vv = xe * g
            vv = vv + b
            vv = max(vv, F(-1.0))
            vv = min(vv, F(1.0))
            v3 = vv * vv
            v3 = v3 * vv
            v3 = v3 * F(0.5)
            y = vv * F(1.5)
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
            lo = lp * kl
            o = o + lo
            si = si + x * x
            so = so + o * o
            o = o * ac
            o = o - x
            o = o * mod
            buf[j] = x + o
        s[0], s[1], s[2], s[3], s[4], s[5] = lp, env, gg, dx, dy, tl
        self.auto_end(si, so)

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
    def pole_c(p, w, l2) -> np.float32:
        """a one-pole's coefficient at f_lo x span^p (w = -2 pi f_lo / FS / ln 2, l2 = log2(span))"""
        c = p * F(l2)
        c = exp2(c)
        c = c * F(w)
        c = exp2(c)
        return F(1.0) - c

    @classmethod
    def tone_c(cls, p) -> np.float32:
        """a one-pole's coefficient at 300 Hz x 40^p (FUZZ's TONE)"""
        return cls.pole_c(p, D.W_TONE, D.LOG2_TONE_SPAN)

    def fold(self, s, p, buf) -> None:
        """FOLD: state s0 dx, s1 dy (the DC blocker), s2 the tone one-pole"""
        mod, amnt, symm, shpe, tone, lev, auto = p
        g = amnt * F(D.FD_GAIN_OCT)
        g = exp2(g)
        b = symm - F(0.5)
        b = b * F(2 * D.FD_BIAS_MAX)
        c = self.tone_c(tone)
        dx, dy, tl = s[0], s[1], s[2]
        ac = self.auto_gain(auto > F(D.AUTO_ON), lev)
        si = so = F(0.0)
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
            si = si + x * x
            so = so + o * o
            o = o * ac
            o = o - x
            o = o * mod
            buf[j] = x + o
        s[0], s[1], s[2] = dx, dy, tl
        self.auto_end(si, so)

    def harm(self, s, p, buf) -> None:
        """HARM: state s0 the band's one-pole, s1 dx, s2 dy, s3 the tone one-pole"""
        mod, amnt, freq, even, tone, lev, auto = p
        a = freq * F(D.LOG2_HM_SPAN)
        a = exp2(a)
        a = a * F(D.W_HM)
        a = exp2(a)
        a = F(1.0) - a
        c = self.tone_c(tone)
        k = amnt * F(D.HM_AMNT_MAX)
        lp, dx, dy, tl = s[0], s[1], s[2], s[3]
        ac = self.auto_gain(auto > F(D.AUTO_ON), lev)
        si = so = F(0.0)
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
            si = si + x * x
            so = so + y * y
            y = y * ac
            y = y - x
            y = y * mod
            buf[j] = x + y
        s[0], s[1], s[2], s[3] = lp, dx, dy, tl
        self.auto_end(si, so)

    def sub(self, s, p, buf) -> None:
        """SUB: state s0 the band's one-pole, s1 its envelope, s2 the rounded square, s3 the flip-flop,
        s4 the trigger (armed 0, fired 1), s5 the second flip-flop (two octaves)"""
        mod, lev, band, tone, octv, dry, _ = p
        a = self.pole_c(band, D.W_SB, D.LOG2_SB_SPAN)
        c = self.pole_c(tone, D.W_ST, D.LOG2_ST_SPAN)
        o = F(1.0) if octv >= F(0.5) else F(0.0)
        lp, e, l1, f1, tr, f2 = s[0], s[1], s[2], s[3], s[4], s[5]
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            u = x - lp
            u = u * a
            lp = lp + u
            al = max(lp, F(0.0) - lp)
            d = al - e
            kk = F(D.SB_UP) if al > e else F(D.SB_DN)
            d = d * kk
            e = e + d
            th = e * F(D.SB_THR)
            if tr == F(0.0):
                if lp > th:
                    f1 = F(1.0) - f1
                    tr = F(1.0)
                    if f1 > F(0.5):
                        f2 = F(1.0) - f2
            else:
                nth = F(0.0) - th
                if lp < nth:
                    tr = F(0.0)
            q = f2 - f1
            q = q * o
            q = f1 + q
            q = q * F(2.0)
            q = q - F(1.0)
            q = e * q
            w = q - l1
            w = w * c
            l1 = l1 + w
            y = x * dry
            z = l1 * lev
            y = y + z
            y = y - x
            y = y * mod
            buf[j] = x + y
        s[0], s[1], s[2], s[3], s[4], s[5] = lp, e, l1, f1, tr, f2

    def ring_mod(self, s, p, buf) -> None:
        """RING: state s0 the carrier's phase (of 2^32)"""
        mod, freq, shpe, am, lev, _, _ = p
        hz = freq * F(D.LOG2_RG_SPAN)
        hz = exp2(hz)
        hz = hz * F(D.RG_LO * D.RG_PH_PER_HZ)
        inc = trunc(hz)
        sh = shpe * F(D.RG_SHAPE_MAX)
        sh = sh + F(1.0)
        ph = int(s[0]) & 0xFFFFFFFF
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            c = sine(ph)
            ph = (ph + inc) & 0xFFFFFFFF
            c = c * sh
            c = max(c, F(-1.0))
            c = min(c, F(1.0))
            t = F(1.0) - c
            t = t * am
            c = c + t
            y = x * c
            y = y * lev
            y = y - x
            y = y * mod
            buf[j] = x + y
        s[0] = ph

    def gater(self, s, p, buf) -> None:
        """GATER: state s0 the phase (Q28 a step, 2^32 the 16 steps), s1 the closure (0 open .. DPTH),
        s2 the clock word it last saw"""
        mod, dpth, patn, rate, shpe, swng, _ = p
        bpm = self.tempo if self.tempo else 120 * 120
        tpb = F(bpm) * F(D.TICKS_PER_BPM120)
        r = min(trunc(rate * F(len(D.GT_RATE))), len(D.GT_RATE) - 1)
        inv = F(1.0 / D.GT_RATE[r])
        ds = tpb * inv                               # steps a block
        ds = ds * F(2.0 ** 23)
        incs = trunc(ds)                             # a sample's step, Q28
        sl = F(float(incs) * 2.0 ** -27)
        ex = F(1.0) - shpe
        ex = ex * F(D.GT_SHAPE_OCT)
        ex = exp2(ex)
        sl = sl * ex
        sl = max(sl, F(D.GT_SMIN))
        sl = min(sl, F(D.GT_SMAX))
        nsl = F(0.0) - sl
        pat = D.GT_PAT[min(trunc(patn * F(16.0)), 15)]
        nx = ((pat >> 1) | (pat << 15)) & 0xFFFF
        b1 = swng * F(D.GT_SWING_MAX)
        b1 = b1 + F(1.0)
        b1 = trunc(b1 * F(float(D.GT_STEP)))
        h0 = b1 >> 1
        h1 = h0 + D.GT_STEP
        ph = int(s[0]) & 0xFFFFFFFF
        w = self.clk
        if w != (int(s[2]) & 0xFFFFFFFF):
            s[2] = w
            if w >> 31:
                tf = F(float(w & 0xFFF)) * inv
                n = trunc(tf)
                f = tf - F(n)
                f = f * F(float(D.GT_STEP))
                tgt = ((n << 28) + trunc(f)) & 0xFFFFFFFF
                tol = inv * F(D.GT_TOL_TICKS * float(D.GT_STEP))
                tol = trunc(tol)
                dv = (ph - tgt) & 0xFFFFFFFF
                dv = dv - (1 << 32) if dv >> 31 else dv
                if dv > tol or dv < -tol:
                    ph = tgt
        c = F(s[1])
        for j in range(D.BLOCK):
            x = F(buf[j])
            x = max(x, F(-D.IN_MAX))
            x = min(x, F(D.IN_MAX))
            q = ph & (D.GT_PAIR - 1)
            k = (ph >> 28) & 14
            if q < b1:
                end, full = h0, b1
            else:
                k += 1
                end, full = h1, D.GT_PAIR
            m = 1 << k
            if not nx & m:
                end = full
            tg = dpth
            if pat & m and q < end:
                tg = F(0.0)
            tg = tg - c
            tg = min(tg, sl)
            tg = max(tg, nsl)
            c = c + tg
            g = F(1.0) - c
            y = x * g
            y = y - x
            y = y * mod
            buf[j] = x + y
            ph = (ph + incs) & 0xFFFFFFFF
        s[0], s[1] = ph, c
