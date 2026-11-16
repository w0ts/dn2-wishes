"""The chorus SEND's TYPE JUNO (dnfw.inserts.jsend, docs/inserts.md "The chorus send"): the DSL program's model
against dnfw.inserts.postref.JsendRef, bit for bit, through TYPE switches, knob moves and the frame's half words;
TYPE STOCK leaves the send to the stock chorus (out untouched, the state forgotten); every register back as it came.
The SHARC runner's jsend step holds the assembled code to the same reference."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import jsend as J
from dnfw.inserts import postref as R
from dnfw.perc.dsl import Mem

DESC, INP, OUTP = 0x257E6C, 0x25D6C8, 0x25D6D0          # the bus's I/O descriptor and its two pointer pairs
INL, INR, OUTL, OUTR = 0x25A000, 0x25A080, 0x25A100, 0x25A180
MARK = 0x7FC00001


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def setup(m: Mem) -> None:
    m.put(DESC, 32)
    m.put(DESC + 4, INP)
    m.put(DESC + 0xC, OUTP)
    for a, v in ((INP, INL), (INP + 4, INR), (OUTP, OUTL), (OUTP + 4, OUTR)):
        m.put(a, v)


def call(m: Mem, typ: int, dpth: int, spd: int, inl, inr, regs: dict[int, int]):
    m.put(D.JS_TYPE, typ)
    m.put(D.JS_DPTH_WORD, (dpth & 0xFFFF) << 16 | 0x1234)          # the high half; the low half another slot's
    m.put(D.JS_SPD_WORD, 0x5678 << 16 | (spd & 0xFFFF))
    for k in range(32):
        m.put(INL + 4 * k, fbits(inl[k]))
        m.put(INR + 4 * k, fbits(inr[k]))
        m.put(OUTL + 4 * k, MARK)
        m.put(OUTR + 4 * k, MARK)
    went, p = J.model(m, {**regs, 12: DESC})
    out = ([m.get(OUTL + 4 * k) for k in range(32)], [m.get(OUTR + 4 * k) for k in range(32)])
    return went, out, p


def test_model_is_the_reference_through_switches():
    rnd = random.Random(21)
    m, ref = Mem(), R.JsendRef()
    setup(m)
    regs = {k: rnd.getrandbits(32) for k in range(16)}
    plan = [D.JS_JUNO] * 40 + [D.JS_STOCK] * 5 + [D.JS_JUNO] * 30 + [7] * 3 + [D.JS_JUNO] * 10
    for b, typ in enumerate(plan):
        dpth = (127 << 8) if b < 20 else (64 << 8) if b < 60 else 0
        spd = (10 << 8) if b < 30 else (60 << 8) if b < 70 else (127 << 8) | 0x40
        inl = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
        inr = [x * 0.7 + rnd.uniform(-0.1, 0.1) for x in inl]
        went, out, p = call(m, typ, dpth, spd, inl, inr, regs)
        want = ref.block(typ, dpth, spd, inl, inr)
        for k, v in regs.items():
            if k != 12:
                assert p.r[k] == v, f"block {b}: R{k} not back"
        if want is None:
            assert went == "stock", b
            assert out == ([MARK] * 32, [MARK] * 32), f"block {b}: STOCK must leave the send to the stock chorus"
        else:
            assert went == "ours", b
            assert out[0] == [fbits(x) for x in want[0]], f"block {b} left"
            assert out[1] == [fbits(x) for x in want[1]], f"block {b} right"


def test_juno_send_is_a_chorus_not_a_copy():
    """MIX 127 (DPTH 127), MODE I: after the line fills, out differs from in, and L from R"""
    rnd = random.Random(3)
    m = Mem()
    setup(m)
    t = np.arange(32 * 40) / 48000.0
    x = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.01 * np.array([rnd.uniform(-1, 1) for _ in t])
    side = 0.0
    for b in range(40):
        seg = list(x[32 * b:32 * b + 32])
        _, out, _ = call(m, D.JS_JUNO, 127 << 8, 0, seg, seg, {})
        if b >= 20:
            lo = np.array([struct.unpack("<f", struct.pack("<I", w))[0] for w in out[0]])
            ro = np.array([struct.unpack("<f", struct.pack("<I", w))[0] for w in out[1]])
            side += float(np.abs(lo - ro).sum())
    assert side > 0.5
