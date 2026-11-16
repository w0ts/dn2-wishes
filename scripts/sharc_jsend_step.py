"""The SHARC runner's jsend step (docs/inserts.md "The chorus send"): the FX bus's chorus call, sw 0x1c1be1 to its
return at 0x1c1be8 (the bus pushes 0x1c1be7, as it does 0x1c1c5e for the delay), run on the stock section 7 and on the
build, block after block.

1. TYPE STOCK (the send pages' word 11 is 0, as it is until the ColdFire sends one): the build runs the stock chorus:
   every block's output, every register at the return and every word written are the stock image's, but the send's
   own state words (dnfw.inserts.design.JS_STATE).
2. TYPE JUNO: each block's output is dnfw.inserts.postref.JsendRef's, bit for bit (noise, a sine, an impulse; DPTH
   and SPD moved, MODE I / II / I+II), through a switch to STOCK and back (a fresh start); every R, I0-I3 and I5
   register the bus left is back at the return; no DDR write outside the send's words and ring (and the test's
   buffers); the instructions per block (the emulator charges every access alike).
3. STOCK -> JUNO -> STOCK (the User, 2026-11-14: "start fresh"): back on STOCK after noise and a JUNO stretch, the
   stock chorus on silence gives what one never fed the noise gives (its ring and filter states were zeroed at the
   switch to JUNO, dnfw.inserts.jsend.stock_fresh), and it sounds again on the noise.
"""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import postref as R
from dnfw.waverider import dsp
import sharc_f32 as F32

SITE, BACK = dsp.CHORUS_SITE_SW, 0x1C1BE8
STATE, PAR, IO = 0x80459388, 0x257950, 0x257E6C          # the bus's R4, R8, R12 at this call (measured)
# the bus's own buffers at this call (measured: the descriptor's pairs point at them), and the pairs' own words
INL, INR, OUTL, OUTR = 0x25B568, 0x25B5E8, 0x25B668, 0x25B6E8
PAIRI, PAIRO = 0x25D6C8, 0x25D6D0
BUF, BUF_END = 0x25B568, 0x25B768
# the emulator writes what the stock chorus stores through its modified pointers at the byte-scaled alias
# 0x28000000 + 4 a (docs/inserts.md "After the pan": the voice chain's stereo blocks, the same scaling); on the unit
# both are the one place. Its output is read at either, whichever moved.
ALIAS = 0x28000000
MARK = 0x7FC00001
REGS = {f"R{k}": (0x01010101 * (k + 5)) & 0xFFFFFFFF for k in range(16)}


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def script(n=160, seed=17):
    """(TYPE, DPTH half word, SPD half word, in L, in R) per block: STOCK 30, then JUNO with knob moves, STOCK 6,
    JUNO again"""
    rnd = random.Random(seed)
    out = []
    t = np.arange(32 * n) / 48000.0
    sine = 0.4 * np.sin(2 * np.pi * 330.0 * t)
    for b in range(n):
        typ = D.JS_STOCK if b < 30 or 110 <= b < 116 else D.JS_JUNO
        dpth = (127 << 8) if b < 70 else (40 << 8) | 0x80 if b < 130 else 0
        spd = (10 << 8) if b < 60 else (64 << 8) if b < 90 else (127 << 8)
        if 40 <= b < 50 or b < 10:
            inl = [rnd.uniform(-0.6, 0.6) for _ in range(32)]
            inr = [rnd.uniform(-0.6, 0.6) for _ in range(32)]
        elif b == 100:
            inl = [1.0 if j == 3 else 0.0 for j in range(32)]
            inr = inl[:]
        else:
            inl = list(sine[32 * b:32 * b + 32])
            inr = [0.5 * x for x in inl]
        out.append((typ, dpth, spd, inl, inr))
    return out


def call(M5, r0, typ, dpth, spd, inl, inr):
    m2, fx = M5.m2, M5.fx
    r = r0.fresh_call(SITE, regs={**REGS, "R4": STATE, "R8": PAR, "R12": IO})
    m2.poke(r.state, D.JS_TYPE, typ)
    m2.poke(r.state, D.JS_DPTH_WORD, (dpth & 0xFFFF) << 16 | 0x2A00)      # the low half is another kit slot's
    m2.poke(r.state, D.JS_SPD_WORD, 0x3B00 << 16 | (spd & 0xFFFF))
    for k in range(32):
        m2.poke(r.state, INL + 4 * k, fb(inl[k]))
        m2.poke(r.state, INR + 4 * k, fb(inr[k]))
        for a in (OUTL + 4 * k, OUTR + 4 * k):
            m2.poke(r.state, a, MARK)
            m2.poke(r.state, ALIAS + 4 * a, MARK)
    for a, v in ((IO, 32), (IO + 4, PAIRI), (IO + 12, PAIRO), (PAIRI, INL), (PAIRI + 4, INR),
                 (PAIRO, OUTL), (PAIRO + 4, OUTR)):
        m2.poke(r.state, a, v)
    entry = dict(r.state.uregs)
    before = dict(r.state.overlay)
    how = fx.run(r, 6_000_000, fx.Fixups(), stop_at=[BACK])
    def word(a):
        w = m2.word(r.state, a) or 0
        if w != MARK:
            return w
        v = m2.word(r.state, ALIAS + 4 * a)            # (0 is a value written there: never `or MARK`)
        return MARK if v is None else v
    out = ([word(OUTL + 4 * k) for k in range(32)], [word(OUTR + 4 * k) for k in range(32)])
    wrote = {a for a in r.state.overlay if r.state.overlay.get(a) != before.get(a)}
    return r, how, out, entry, wrote


def ddr(a: int) -> int:
    return a if a >= 0x80000000 else a - dsp.LOAD_ALIAS


def own(a: int) -> bool:
    """the send's own: its DDR words and ring, and the post pass's scratch it saves the registers in (L1, rewritten
    by that pass every block)"""
    from dnfw.inserts import post as P
    if D.JS_STATE <= ddr(a) < D.JS_END:
        return True
    from dnfw.inserts import jsend as JS
    if any(lo <= ddr(a) < hi for lo, hi in JS.stock_words()):
        return True
    lo, hi = P.STATE, P.STATE + len(P.state_bytes())
    return any(lo <= x < hi for x in (a, a - dsp.LOAD_ALIAS, (a - ALIAS) // 4))


def _f(w: int) -> float:
    return struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0]


def _path(M5, snap, m2mach, img, first, knobs, n=40):
    """an instance: N blocks of STOCK on FIRST (per block), N of JUNO, then N of STOCK on silence -> (its state,
    its outputs back on STOCK, the stock chorus's struct words after JUNO, every call came back)"""
    zero = [0.0] * 32
    r = M5.init_on(snap, m2mach, img)
    ok = True
    for b in range(n):
        r, how, *_ = call(M5, r, D.JS_STOCK, *knobs, first[b], [0.5 * x for x in first[b]])
        ok &= how[0] == "stop"
    for b in range(n):
        r, how, *_ = call(M5, r, D.JS_JUNO, *knobs, zero, zero)
        ok &= how[0] == "stop"
    words = {a: M5.m2.word(r.state, a) or 0 for a in range(STATE, STATE + 0x1344, 4)}
    back = []
    for b in range(n):
        r, how, out, _, _ = call(M5, r, D.JS_STOCK, *knobs, zero, zero)
        ok &= how[0] == "stop"
        back.append(out)
    return r, back, words, ok


def comeback(M5, snap, m2mach, m5img) -> tuple[dict, dict]:
    """STOCK -> JUNO -> STOCK (the User, 2026-11-14: "start fresh"): 40 blocks of noise on the stock chorus, 40 of
    JUNO, then the stock chorus again on silence, against the same path with silence where the noise was (the same
    LFO and knob smoothing, never fed: it gives exact zeros). Before the fix the ring came back (0.45 for 9 blocks)."""
    checks, numbers = {}, {}
    rnd = random.Random(5)
    noise = [[rnd.uniform(-0.6, 0.6) for _ in range(32)] for _ in range(40)]
    knobs = (127 << 8, 64 << 8)
    r, back, fed, ok = _path(M5, snap, m2mach, m5img, noise, knobs)
    _, quiet, never, ok2 = _path(M5, snap, m2mach, m5img, [[0.0] * 32] * 40, knobs)
    diff = [max(abs(_f(x) - _f(y)) for cx, cy in zip(o, q) for x, y in zip(cx, cy)) for o, q in zip(back, quiet)]
    left = [a for a in sorted(fed) if fed[a] != never[a]]
    numbers["back on STOCK: largest difference from the never-fed path, per block (first 12)"] = [
        f"{d:.3g}" for d in diff[:12]]
    numbers["back on STOCK: largest difference over 40 blocks"] = f"{max(diff):.3g}"
    numbers["stock chorus struct words that differ from the never-fed path after JUNO"] = [
        (hex(a), hex(fed[a]), hex(never[a])) for a in left[:12]]
    checks["STOCK -> JUNO -> STOCK: the calls come back to the bus"] = ok and ok2
    checks["STOCK -> JUNO -> STOCK: back on STOCK on silence, within 1e-6 of a stock chorus never fed the noise "
           "(40 blocks: not the ring or filter states it held before JUNO)"] = max(diff) <= 1e-6
    heard = 0
    for b in range(10):
        r, how, out, _, _ = call(M5, r, D.JS_STOCK, *knobs, noise[b], noise[b])
        heard += sum(1 for w in out[0] + out[1] if w & 0x7FFFFFFF and w != MARK)
    checks["STOCK -> JUNO -> STOCK: the stock chorus sounds again when the noise comes back"] = heard > 200
    return checks, numbers

def run(M5, snap, m2mach, m5img, stock_img) -> dict:
    checks, numbers = {}, {}
    seq = script()
    n_stock = 30
    rs, rb = M5.init_on(snap, m2mach, stock_img), M5.init_on(snap, m2mach, m5img)
    same_out = same_regs = no_stray = ok = True
    stray, cost_stock, heard_stock = set(), [], F32.Ear()
    for b in range(n_stock):
        typ, dp, sp, inl, inr = seq[b]
        rs, hs, os_, _, ws = call(M5, rs, typ, dp, sp, inl, inr)
        rb, hb, ob, _, wb = call(M5, rb, typ, dp, sp, inl, inr)
        ok &= hs[0] == "stop" and hb[0] == "stop"
        same_out &= os_ == ob
        same_regs &= rs.state.uregs == rb.state.uregs
        diff = {a for a in ws | wb if rs.state.overlay.get(a) != rb.state.overlay.get(a)}
        s = {a for a in diff if not own(a)}
        stray |= s
        no_stray &= not s
        cost_stock.append((hs[2], hb[2]))
        heard_stock.hear(w for w in os_[0] + os_[1] if w != MARK)     # (MARK: a word the chorus left untouched)
    checks["TYPE STOCK: both images make the call and come back to the bus"] = ok
    checks["TYPE STOCK: every output word as the stock chorus's (30 blocks: noise, a sine)"] = same_out
    checks["TYPE STOCK: the stock chorus writes its output in the test (not untouched), finite"] = heard_stock.ok(200)
    checks["TYPE STOCK: every register at the return as stock's"] = same_regs
    checks["TYPE STOCK: every word written as stock's, but the send's own words"] = no_stray
    numbers["stock: instructions per block (stock image, build): min, max"] = (
        min(c[0] for c in cost_stock), max(c[0] for c in cost_stock),
        min(c[1] for c in cost_stock), max(c[1] for c in cost_stock))
    numbers["stray words (first 8)"] = [hex(a) for a in sorted(stray)[:8]]

    ref = R.JsendRef()
    for b in range(n_stock):
        ref.block(*seq[b])
    exact, regs_back, heard, first_bad, cost, outside, side = True, True, F32.Ear(), None, [], set(), 0.0
    for b in range(n_stock, len(seq)):
        typ, dp, sp, inl, inr = seq[b]
        rb, hb, ob, entry, wb = call(M5, rb, typ, dp, sp, inl, inr)
        want = ref.block(typ, dp, sp, inl, inr)
        if want is None:
            exact &= hb[0] == "stop"
            continue
        wbits = ([fb(x) for x in want[0]], [fb(x) for x in want[1]])
        if hb[0] != "stop" or ob != wbits:
            exact = False
            first_bad = first_bad or (b, hb[0], [hex(w) for w in ob[0][:4]], [hex(w) for w in wbits[0][:4]])
        keep = {f"R{k}" for k in range(16)} | {"I0", "I1", "I2", "I3", "I5"}
        if any(rb.state.uregs.get(k) != entry.get(k) for k in entry if str(k) in keep):
            regs_back = False
        heard.hear(wbits[0] + wbits[1])
        side += float(sum(abs(a - c) for a, c in zip(want[0], want[1])))
        cost.append(hb[2])
        for a in wb:
            x = ddr(a)
            if 0x80000000 <= x < 0xA0000000 and not own(x):
                outside.add(x)
    checks["TYPE JUNO: every output word as dnfw.inserts.postref.JsendRef's (130 blocks: noise, a sine, an impulse; "
           "DPTH and SPD moved, MODE I / II / I+II; a switch to STOCK and back)"] = exact
    checks["TYPE JUNO: the chorus is heard, in stereo (not a run of zeros, L not R), finite"] = heard.ok(3000) and side > 1.0
    checks["TYPE JUNO: every R, I0-I3 and I5 register the bus left is back at the return"] = regs_back
    checks["TYPE JUNO: no DDR write outside the send's words and ring (and the test's buffers)"] = not outside
    numbers["JUNO: first mismatch"] = first_bad
    numbers["JUNO: DDR words written outside its own (first 8)"] = [hex(a) for a in sorted(outside)[:8]]
    numbers["JUNO: instructions per block (the first is a fresh start: the ring cleared): min, mean, max"] = (
        min(cost), round(sum(cost) / len(cost)), max(cost))
    c, n = comeback(M5, snap, m2mach, m5img)
    checks.update(c)
    numbers.update(n)
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
