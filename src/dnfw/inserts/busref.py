"""The bus inserts (FDN8, XDLY per track), the reference: float32 throughout, every operation in the
order the DSP code (dnfw.inserts.bus) does it, so the two agree bit for bit.

    r = BusRef()
    r.block(par_bytes, left, right)   # par_bytes: the 32 records (dnfw.inserts.ref); left / right: the
                                      # 16 tracks' bus blocks, 32 floats each, changed in place

For each record i = 2 t + j in order (track t's slot 1, then slot 2) whose type is FDN8 or XDLY with an
instance in range (field 0 >> 4): the instance's engine (dnfw.fdn8.ref, dnfw.xdly.ref: the send FX's
reference, TYPE 0) on the track's block x G_IN, its parameters from K1..K6 (bus.FDN8_PAR, XDLY_PAR), then
x' = x + (wet x G_OUT - x) MIX. An instance whose record or type differs from the last that ran it starts
fresh: a new engine switched to its type (FDN8: its ring cleared, 32 silent blocks; XDLY: nothing of its
lines read).
"""

from __future__ import annotations

from ..fdn8 import ref as FR
from ..fdn8.ref import F
from ..xdly import ref as XR
from . import bus as B
from . import design as D
from . import ref as R


class BusRef:
    def __init__(self):
        self.fd = [FR.Ref() for _ in range(D.FDN8_INSTANCES)]
        self.xd = [XR.Ref() for _ in range(D.XDLY_INSTANCES)]
        self.owner = [0] * (D.FDN8_INSTANCES + D.XDLY_INSTANCES)
        self.mv = R.Ref()                        # the moved slot 2s: state / ring 2 t (L), 2 t + 1 (R)

    def moved(self, t: int, v: bytes, left, right, tempo: int, clk: int) -> None:
        """2026-11-11 (design.MOVERS): track T's slot 2 V, a BUILT type, on its block x G_IN, L then R
        (dnfw.inserts.ref.Ref.one, as program.one), then x G_OUT back"""
        self.mv.tempo, self.mv.clk = tempo & 0xFFFF, clk & 0xFFFFFFFF
        for side, buf in ((0, left), (1, right)):
            x = [F(s) * F(B.G_IN) for s in buf]
            self.mv.one(2 * t + side, t, v, x)
            for k in range(D.BLOCK):
                buf[k] = F(x[k]) * F(B.G_OUT)

    def block(self, par: bytes, left, right, tempo: int = 0, clk: int = 0) -> None:
        """TEMPO, CLK: as dnfw.inserts.ref.Ref.block's (a moved GATER's)"""
        for i in range(D.RECORDS):
            t = i >> 1
            v = par[8 * i:8 * i + 8]
            sel, inst = v[0] & ((1 << D.TYPE_BITS) - 1), v[0] >> D.TYPE_BITS
            if i & 1 and D.moved(par, t):
                self.moved(t, v, left[t], right[t], tempo, clk)
                continue
            if sel == D.FDN8 and inst < D.FDN8_INSTANCES:
                eng, slot, scales = self.fd[inst], inst, B.FDN8_PAR
            elif sel == D.XDLY and inst < D.XDLY_INSTANCES:
                eng, slot, scales = self.xd[inst], D.FDN8_INSTANCES + inst, B.XDLY_PAR
            else:
                continue
            key = (i + 1) | sel << 8
            if self.owner[slot] != key:           # fresh: a new engine (its switch to its type comes next)
                self.owner[slot] = key
                eng = (FR.Ref if sel == D.FDN8 else XR.Ref)()
                if sel == D.FDN8:
                    self.fd[inst] = eng
                else:
                    self.xd[inst] = eng
            pf = [F(0.0) if f is None else F(v[2 + f]) * F(sc) for f, sc in scales]
            mix = F(v[1]) * F(1 / 127)
            xl = [F(x) * F(B.G_IN) for x in left[t]]
            xr = [F(x) * F(B.G_IN) for x in right[t]]
            wl, wr = eng.block(0, xl, xr, pf)
            for buf, wet in ((left[t], wl), (right[t], wr)):
                for k in range(D.BLOCK):
                    x = F(buf[k])
                    w = F(wet[k]) * F(B.G_OUT)
                    w = w - x
                    w = w * mix
                    buf[k] = x + w
