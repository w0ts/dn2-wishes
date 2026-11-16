"""The stereo inserts after the pan (CHOR, WIDE), the reference: float32 throughout, every operation
in the order the DSP code (dnfw.inserts.post) does it, so the two agree bit for bit.

    r = PostRef()
    r.block(par_bytes, left, right, route)   # left / right: the 16 voice slots' 32 floats each,
                                             # changed in place; route as dnfw.inserts.ref

Each voice slot gets the post insert of the track it plays; its state (and its ring) start from zeros
whenever its track or that track's M.SEL changes. A slot whose track's M.SEL is not CHOR or WIDE is
left as it is.

WIDE (K1 WDTH, K2 TIME, K3 BASS, K4 TONE), per sample l, r:
    m = (l + r) / 2;  s = (l - r) / 2;  ring <- m;  d = ring[TIME back]
    lb += (d - lb) ab;  lt += ((d - lb) - lt) ct            (the lows out, TONE)
    s' = s 2 WDTH + lt WDTH;  l' = l + (m + s' - l) mod;  r' = r + (m - s' - r) mod
CHOR (K1 DPTH, K2 RATE, K3 DLY, K4 VOIC, K5 WDTH, K6 FDBK): voices v < 1 + trunc(3.99 VOIC), each
    a delay DLY + DPTH sin(phase + v / 4 turn), moved linearly across the block, read with linear
    interpolation; voice v to the left (v even) or right (v odd) by WDTH (centred alone), x 2 / voices.
    Then per sample: ring <- (l + r) / 2 + FDBK x the wet's mid;  l' = l + (wet l - l) mod.
JUNO (K1 MODE; MIX as Optimist's, design.JN_*): d = base +- tri x dep (L +, R -), the triangle at the block's two
    ends and d moved linearly between; each tap read 1 + d back by 4-point Hermite (Optimist's), low-passed (its
    2nd-order SVF); ring <- (l + r) / 2;  l' = l gd + tap L gw, r' = r gd + tap R gw.
"""

from __future__ import annotations

import numpy as np

from ..fdn8.ref import F, exp2, recip, sine, trunc
from . import design as D
from .ref import Ref

MASK = D.POST_RING - 1


class PostRef:
    def __init__(self):
        self.st = [[0] * 6 for _ in range(D.RECORDS)]        # per (voice slot, insert slot), i = 2 t + j
        self.last = [(0, 0)] * D.RECORDS
        self.ring = [np.zeros(D.POST_RING, F) for _ in range(D.RECORDS)]

    def block(self, par: bytes, left, right, route=None) -> None:
        for i in range(D.RECORDS):
            t, j = i >> 1, i & 1
            tr = t if route is None else route[t] & 0xFFFF
            if tr > 15:
                continue
            v = par[8 * (2 * tr + j):8 * (2 * tr + j) + 8]
            sel = v[0] & ((1 << D.TYPE_BITS) - 1)
            if sel not in D.POST:
                continue
            if (sel, tr) != self.last[i]:
                self.st[i] = [0] * 6
                self.last[i] = (sel, tr)
                self.ring[i][:] = 0
            p = [F(b) * F(1 / 127) for b in v[1:8]]
            if sel == D.WIDE:
                self.wide(i, p, left[t], right[t])
            elif sel == D.JUNO:
                self.juno(i, p, left[t], right[t])
            else:
                self.chor(i, p, left[t], right[t])

    def wide(self, t, p, L, R) -> None:
        """state s0 the ring's write place, s1 the bass one-pole, s2 the tone one-pole"""
        mod, wdth, time, bass, tone, _, _ = p
        s = self.st[t]
        wg = wdth * F(2.0)
        dd = time * F(D.WD_D_SPAN)
        dd = dd + F(D.WD_D_MIN)
        dl = trunc(dd)
        ab = bass * F(D.LOG2_WB_SPAN)
        ab = exp2(ab)
        ab = ab * F(D.W_WB)
        ab = exp2(ab)
        ab = F(1.0) - ab
        ct = Ref.tone_c(tone)
        wp, lb, lt = int(s[0]), F(s[1]), F(s[2])
        ring = self.ring[t]
        for j in range(D.BLOCK):
            l, r = F(L[j]), F(R[j])
            m = l + r
            m = m * F(0.5)
            sd = l - r
            sd = sd * F(0.5)
            wp = (wp + 1) & MASK
            ring[wp] = m
            d = ring[(wp - dl) & MASK]
            u = d - lb
            u = u * ab
            lb = lb + u
            h = d - lb
            w = h - lt
            w = w * ct
            lt = lt + w
            s2 = sd * wg
            q = lt * wdth
            s2 = s2 + q
            lo = m + s2
            ro = m - s2
            lo = lo - l
            lo = lo * mod
            L[j] = l + lo
            ro = ro - r
            ro = ro * mod
            R[j] = r + ro
        s[0], s[1], s[2] = wp, lb, lt

    def chor(self, t, p, L, R) -> None:
        """state s0 the LFO's phase, s1 the ring's write place"""
        mod, dpth, rate, dly, voic, wdth, fdbk = p
        s = self.st[t]
        nvf = voic * F(D.CH_VOICES_K)
        nv = trunc(nvf) + 1
        hz = rate * F(D.LOG2_CR_SPAN)
        hz = exp2(hz)
        hz = hz * F(D.CH_RATE_LO * D.PH_PER_HZ)
        inc = trunc(hz)
        base = dly * F(D.CH_DLY_SPAN)
        base = base + F(D.CH_DLY_MIN)
        dep = dpth * F(D.CH_DEP_MAX)
        fb = fdbk * F(D.CH_FB_MAX)
        k = recip(F(float(nv)))
        k = k * F(2.0)
        ph0 = int(s[0]) & 0xFFFFFFFF
        ph1 = (ph0 + inc) & 0xFFFFFFFF
        wp = int(s[1])
        ring = self.ring[t]
        wl = [F(0.0)] * D.BLOCK
        wr = [F(0.0)] * D.BLOCK
        for v in range(nv):
            off = (v << 30) & 0xFFFFFFFF
            a0 = sine((ph0 + off) & 0xFFFFFFFF)
            a0 = a0 * dep
            a0 = a0 + base
            a1 = sine((ph1 + off) & 0xFFFFFFFF)
            a1 = a1 * dep
            a1 = a1 + base
            step = a1 - a0
            step = step * F(1 / D.BLOCK)
            sg = F(0.0) if nv == 1 else (F(0.5) if v % 2 == 0 else F(-0.5))
            hw = wdth * sg
            gl = F(0.5) + hw
            gr = F(0.5) - hw
            gl = gl * k
            gr = gr * k
            d = a0
            for j in range(D.BLOCK):
                d = d + step
                i = trunc(d)
                fr = d - F(i)
                pos = wp + 1 + j
                y0 = ring[(pos - i) & MASK]
                y1 = ring[(pos - i - 1) & MASK]
                y1 = y1 - y0
                y1 = y1 * fr
                y = y0 + y1
                q = y * gl
                wl[j] = wl[j] + q
                q = y * gr
                wr[j] = wr[j] + q
        for j in range(D.BLOCK):
            l, r = F(L[j]), F(R[j])
            x = l + r
            x = x * F(0.5)
            wm = wl[j] + wr[j]
            wm = wm * F(0.5)
            wm = wm * fb
            x = x + wm
            wp = (wp + 1) & MASK
            ring[wp] = x
            o = wl[j] - l
            o = o * mod
            L[j] = l + o
            o = wr[j] - r
            o = o * mod
            R[j] = r + o
        s[0], s[1] = ph1, wp

    @staticmethod
    def tri(ph: int) -> np.float32:
        """the triangle at the phase PH, less its middle: |(PH >> 16) - 32768| - 16384 (Optimist's, before its x 2)"""
        t = F(float((ph >> 16) - 32768))
        t = abs(t)
        return t - F(16384.0)

    @staticmethod
    def herm(fr, y0, y1, y2, y3) -> np.float32:
        """4-point Hermite between y1 and y2 at fr (Optimist's juno_cho_herm, in float)"""
        h = F(0.5)
        t1 = y1 - y2
        c3 = y3 - y0
        c3 = c3 * h
        u = t1 * h
        u = u + t1
        c3 = c3 + u
        c1 = y2 - y0
        c1 = c1 * h
        c2 = y0 - y1
        c2 = c2 + c1
        c2 = c2 - c3
        o = c3 * fr
        o = o + c2
        o = o * fr
        o = o + c1
        o = o * fr
        return o + y1

    @staticmethod
    def lp(s: list, k: int, x, c: dict) -> np.float32:
        """the low-pass (Optimist's juno_cho_lp, in float): states s[k], s[k + 1]"""
        s0, s1 = F(s[k]), F(s[k + 1])
        v3 = x - s1
        v1 = s0 * F(c["a1"])
        q = v3 * F(c["a2"])
        v1 = v1 + q
        v2 = v1 * F(c["g"])
        v2 = s1 + v2
        q = v1 + v1
        s[k] = q - s0
        q = v2 + v2
        s[k + 1] = q - s1
        return v2

    def juno(self, t, p, L, R, c: dict | None = None) -> None:
        """state s0 the triangle's phase, s1 the ring's write place, s2 s3 the left low-pass, s4 s5 the right;
        C: design.juno_consts (design.JN, 48 kHz)"""
        c = c or D.JN
        mix, mode = p[0], p[1]
        md = trunc(mode * F(D.JN_MODE_K))
        inc, dep2 = c["inc"][md], F(2 * c["dep"][md])
        base = F(c["base"])
        q = mix * F(1 - D.JN_GD)
        gd = F(1.0) - q
        gw = mix * F(D.JN_GW)
        s = self.st[t]
        ph0 = int(s[0]) & 0xFFFFFFFF
        ph1 = (ph0 + D.BLOCK * inc) & 0xFFFFFFFF
        q = self.tri(ph0) * dep2
        dl0 = base + q
        dr0 = base - q
        q = self.tri(ph1) * dep2
        q = base + q
        step = q - dl0
        step = step * F(1 / D.BLOCK)
        nstep = F(0.0) - step
        wp = int(s[1])
        ring = self.ring[t]
        taps = []
        for d, sp in ((dl0, step), (dr0, nstep)):
            w = [F(0.0)] * D.BLOCK
            for j in range(D.BLOCK):
                d = d + sp
                i = trunc(d)
                fr = d - F(i)
                a = wp + 1 + j - i
                w[j] = self.herm(fr, ring[a & MASK], ring[(a - 1) & MASK], ring[(a - 2) & MASK], ring[(a - 3) & MASK])
            taps.append(w)
        st = [F(x) for x in s[2:6]]
        for j in range(D.BLOCK):
            taps[0][j] = self.lp(st, 0, taps[0][j], c)
            taps[1][j] = self.lp(st, 2, taps[1][j], c)
        for j in range(D.BLOCK):
            l, r = F(L[j]), F(R[j])
            x = l + r
            x = x * F(0.5)
            wp = (wp + 1) & MASK
            ring[wp] = x
            o = l * gd
            q = taps[0][j] * gw
            L[j] = o + q
            o = r * gd
            q = taps[1][j] * gw
            R[j] = o + q
        s[0], s[1] = ph1, wp
        s[2:6] = st


class JsendRef:
    """the chorus SEND's JUNO (dnfw.inserts.jsend): TYPE not JUNO -> None (the stock chorus runs; the next JUNO starts
    from zeros), else out L / R = PostRef.juno on in L / R, MIX = DPTH, MODE = SPD (the frame's 8.8 half words)"""

    def __init__(self):
        self.r = PostRef()
        self.on = False

    def block(self, typ: int, dpth_hw: int, spd_hw: int, inl, inr):
        if typ != D.JS_JUNO:
            self.on = False
            return None
        if not self.on:
            self.r.st[0] = [0] * 6
            self.r.ring[0][:] = 0
            self.on = True
        k = F(D.JS_KNOB_K)
        p = [F(float(dpth_hw & 0xFFFF)) * k, F(float(spd_hw & 0xFFFF)) * k] + [F(0.0)] * 5
        L = [F(x) for x in inl]
        R = [F(x) for x in inr]
        self.r.juno(0, p, L, R)
        return L, R
