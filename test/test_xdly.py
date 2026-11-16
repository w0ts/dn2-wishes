"""XDLY (docs/xdly.md): the DSL program's model against the reference, bit for bit, the lines
word for word, and the design's numbers. The SHARC runner's xdly step holds the assembled code
to the same reference."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.perc.dsl import Mem
from dnfw.xdly import design as D
from dnfw.xdly import program as P
from dnfw.xdly import ref as R

PAR, IO = 0x257934, 0x257E6C
BUF = 0x83F00000
INL, INR, OUTL, OUTR, PAIRI, PAIRO = (BUF + k * 0x100 for k in range(6))


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def mem0() -> Mem:
    m = Mem()
    st = P.state_bytes()                         # (2026-11-10: the lines' bases are words now)
    for k in range(0, len(st), 4):
        m.put(P.STATE + k, struct.unpack_from("<I", st, k)[0])
    for a, v in ((IO, 32), (IO + 4, PAIRI), (IO + 12, PAIRO), (PAIRI, INL), (PAIRI + 4, INR),
                 (PAIRO, OUTL), (PAIRO + 4, OUTR)):
        m.put(a, v)
    return m


def call(m: Mem, type_word: int, inl, inr, par):
    m.put(P.TYPE_WORD, type_word)
    for k in range(32):
        m.put(INL + 4 * k, fbits(inl[k]))
        m.put(INR + 4 * k, fbits(inr[k]))
        m.put(OUTL + 4 * k, 0x7FC00001)
        m.put(OUTR + 4 * k, 0x7FC00001)
    for k, x in enumerate(par):
        m.put(PAR + 4 * k, fbits(x))
    m.put(P.C["went"], 0)
    went, _ = P.run(m, {4: D.STOCK_STATE, 8: PAR, 12: IO})
    if went == "stock":
        return "stock"
    return ([m.get(OUTL + 4 * k) for k in range(32)], [m.get(OUTR + 4 * k) for k in range(32)])


def as_bits(out):
    if isinstance(out, str):
        return out
    return ([fbits(x) for x in out[0]], [fbits(x) for x in out[1]])


SKIP_AT = 150                    # q forced to LINE in both (the skip after 10.9 s of silence)


def script(seed=2, blocks=200):
    """stock, a switch to XDLY, noise and an impulse, loud input into FDBK 127 (the knee), the
    knobs moving (the times bend), the silent skip; the switch back is test_switch_back's"""
    rnd = random.Random(seed)
    par = [0.1, 0.0, 0.15, 0.6, 0.3, 0.8]
    out = []
    for b in range(blocks):
        tw = 0x100 if b < 3 else 0x77000000    # (the high half is k 41, the reverb's PRE: not ours)
        loud = 2.0 if 60 <= b < 64 else 0.5
        if 10 <= b < 16 or 60 <= b < 64 or b == SKIP_AT + 1:
            inl = [rnd.uniform(-loud, loud) for _ in range(32)]
            inr = [rnd.uniform(-loud, loud) for _ in range(32)]
        else:
            inl = [1.0 if (b == 30 and j == 7) else 0.0 for j in range(32)]
            inr = list(inl)
        if b == 50:
            par = [0.12, 16384.0, 0.2, 1.0, 0.9, 0.6]     # FDBK 127+, MOD high, X raw (not used)
        if b in (90, 91, 92, 93):
            par = [par[0] + 0.01, par[1], par[2] - 0.01, 0.4, par[4], par[5]]
        if b == 120:
            par = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]         # the ends: 1 ms, no feedback, no MOD
        if b == 135:
            par = [0.05, 0.0, 1.0, 0.5, 1.0, 1.0]        # TIME 2 at 10 s (past what was written)
        out.append((tw, inl, inr, [np.float32(x) for x in par]))
    return out


def test_design_numbers():
    assert 2 * D.LINE * 4 == D.STOCK_AREA[1] - D.STOCK_AREA[0]
    assert D.LINE_B + 4 * D.LINE == D.STOCK_STATE + D.STOCK_AREA[1]
    assert abs(float(R.exp2(np.float32(D.LOG2_TMIN + D.LOG2_TSPAN))) - D.T_MAX) < 1.0
    assert D.T_MAX * (1 + D.MOD_GAIN) > D.D_HI     # MOD at 127 reaches the line's end: clamped


def test_model_is_the_reference():
    m, r = mem0(), R.Ref()
    heard = 0
    for b, (tw, inl, inr, par) in enumerate(script()):
        if b == SKIP_AT:
            r.q = D.LINE
            m.put(P.C["q"], D.LINE)
        got = call(m, tw, inl, inr, par)
        want = as_bits(r.block(tw, inl, inr, par))
        assert got == want, f"block {b}"
        if not isinstance(want, str):
            heard += sum(1 for w in want[0] + want[1] if w & 0x7FFFFFFF)
    assert heard > 3000
    n = r.fill + 4
    for line, base in ((r.a, D.LINE_A), (r.b, D.LINE_B)):
        idx = [(r.wp - k) & D.LINE_MASK for k in range(n)]
        assert [m.get(base + 4 * i) for i in idx] == [fbits(line[i]) for i in idx]


def test_switch_back_clears_the_stock_area():
    m, r = mem0(), R.Ref()
    seq = script(blocks=40)
    for tw, inl, inr, par in seq:
        call(m, tw, inl, inr, par)
        r.block(tw, inl, inr, par)
    zeros = ([0] * 32, [0] * 32)
    par = seq[-1][3]
    for b in range(D.STOCK_WORDS // D.CHUNK):
        assert call(m, 0x100, [0.5] * 32, [0.5] * 32, par) == zeros, f"clearing block {b}"
        assert as_bits(r.block(0x100, [0.5] * 32, [0.5] * 32, par)) == zeros
    assert call(m, 0x100, [0.5] * 32, [0.5] * 32, par) == "stock"
    assert r.block(0x100, [0.5] * 32, [0.5] * 32, par) == "stock"
    written = [w for w in range(D.LINE_A, D.LINE_B + 4 * D.LINE, 4) if m.get(w)]
    assert written == []
    assert [c[0] for c in r.cleared] == list(range(0, D.STOCK_WORDS, D.CHUNK))


def test_knee():
    for v in (0.0, 0.3, -0.6, 0.62, -0.9, 1.5, -3.0, 10.0):
        k = float(R.knee(np.float32(v)))
        a = abs(v)
        want = a if a <= D.KNEE else min(1.0, D.KNEE + 0.5 * np.tanh(min(2 * (a - D.KNEE), 2.0)))
        assert abs(abs(k) - want) < 2e-6 and (k <= 0) == (v <= 0)


def put_ex(m: Mem, gen: int, sl: int, kn: int, wd: int, inp: int):
    """the Delay page's second page as the ColdFire sends it (design.EX): the change word, then design.derive's five
    float words; -> (the words, for the reference)"""
    vals = D.derive(sl, kn, wd, inp)
    m.put(D.EX, gen)
    for k, v in enumerate(vals):
        m.put(D.EX + 4 * (k + 1), fbits(v))
    return (gen, *vals)


def test_second_page_model_is_the_reference():
    """every setting of the page's four knobs, the model of the DSL program against the reference, bit for bit"""
    for knobs in ((20, 30, 40, 10), (0, 0, 0, 0), (127, 127, 127, 127), (58, 61, 0, 64), (58, 61, 127, 64),
                  (58, 61, 127, 100), (90, 80, 64, 64)):
        m, r = mem0(), R.Ref()
        ex = put_ex(m, 1, *knobs)
        heard = 0
        for b, (tw, inl, inr, par) in enumerate(script(blocks=80)):
            got = call(m, tw, inl, inr, par)
            want = as_bits(r.block(tw, inl, inr, par, ex))
            assert got == want, f"{knobs} block {b}"
            if not isinstance(want, str):
                heard += sum(1 for w in want[0] + want[1] if w & 0x7FFFFFFF)
        assert heard > 300, knobs


def test_second_page_defaults_are_todays_bits():
    """the defaults, and a change word 0 (nothing sent yet), are exactly the engine without the page"""
    base = None
    for ex in (None, (1, *D.derive(D.SL_DEF, D.KN_DEF, D.WD_DEF, D.IN_DEF)), (0, 1, 2, 3, 4, 5)):
        r = R.Ref()
        outs = []
        for tw, inl, inr, par in script(blocks=80):
            outs.append(as_bits(r.block(tw, inl, inr, par, ex)))
        base = base or outs
        assert outs == base
    # the instances (MODE 1, im != 0) ignore the page even when words are there; a send reads it
    from dnfw.perc.dsl import Prog
    for im, want in ((1, (D.KF, D.KNEE, 1.0, 0.0, 0.0)), (0, None)):
        m = mem0()
        put_ex(m, 1, 20, 30, 40, 10)
        m.put(P.C["im"], im)
        p = Prog("run", mem=m)
        P.extras(p)
        got = tuple(np.frombuffer(struct.pack("<I", m.get(P.C[n])), "<f")[0] for n in ("kf", "kn", "wl", "wr", "sn"))
        if want:
            assert got == tuple(np.float32(x) for x in want)
        else:
            assert got != tuple(np.float32(x) for x in (D.KF, D.KNEE, 1.0, 0.0, 0.0))
