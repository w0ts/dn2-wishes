"""The SHARC runner's fdn8 step (docs/fdn8.md): the FX bus's reverb call, sw 0x1c1d11 to its
return at 0x1c1d18, run on the stock section 7 and on the build, block after block.

1. TYPE = stock (k 48 not 0): the build runs the stock reverb, and every block's output,
   every register at the return and every word written are the stock image's, but FDN8's own
   state words (its save area); the stock reverb's writes stay inside its sample buffers and
   a few control words (counted).
2. TYPE = FDN8: after the 32 clearing blocks (the wet silent), each block's output is
   dnfw.fdn8.ref's, bit for bit, over noise, an impulse, knob moves and SIZE 127; the ring
   at the end is the reference's word for word; every register the bus left is back at the
   return; the instructions per block (the DSP cost in the emulator, which charges every
   access alike).
3. The switches: FDN8 -> stock clears the stock reverb's buffers (22 blocks, silent), after
   which the stock reverb on silence gives exactly what a stock reverb that never had input
   gives; stock -> FDN8 again clears the ring, after which FDN8 on silence gives exact zeros.
4. TYPE = LONG (2, the longer lines): from FDN8 (the ring cleared, its table copied), each
   block's output is the reference's, bit for bit, and the ring word for word.
"""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.fdn8 import design as FD
from dnfw.fdn8 import program as FP
from dnfw.fdn8 import ref as FR
from dnfw.waverider import dsp

SITE, BACK = dsp.REVERB_SITE_SW, 0x1C1D18
PAR, IO = 0x257918, 0x257E6C
BUF = 0x83F00000                 # the test's own buffers (DDR, used by nothing)
INL, INR, OUTL, OUTR, PAIRI, PAIRO = (BUF + k * 0x100 for k in range(6))
MARK = 0x7FC00001                # a NaN marker: every output word must be written
REGS = {f"R{k}": (0x01010101 * (k + 3)) & 0xFFFFFFFF for k in range(16)}


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def bf(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def script(n_stock=40, n_fdn=230, seed=7):
    """(TYPE word, in L, in R, six parameters 0..1) per block"""
    rnd = random.Random(seed)
    par = [0.15, 0.6, 0.3, 0.5, 0.05, 0.95]
    out = []
    for b in range(n_stock + n_fdn):
        tw = 0x12340100 if b < n_stock else 0x56780000      # the high half is k 49: not ours
        k = b if b < n_stock else b - n_stock
        noisy = 2 <= k < 8 or (b >= n_stock and 40 <= k < 46)          # (after FDN8's 32 clearing blocks)
        imp = k == (30 if b < n_stock else 50)
        inl = [rnd.uniform(-0.5, 0.5) if noisy else (1.0 if imp and j == 5 else 0.0) for j in range(32)]
        inr = [rnd.uniform(-0.5, 0.5) if noisy else inl[j] for j in range(32)]
        if b >= n_stock and k in (150, 151, 152):
            par = [min(1.0, x + 0.05) for x in par]
        if b >= n_stock and k == 190:
            par = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0]
        if b < n_stock and k == 20:
            par = [0.3, 0.8, 0.6, 0.4, 0.2, 0.7]
        out.append((tw, inl, inr, [float(np.float32(x)) for x in par]))
    return out


def call(M5, r0, tw, inl, inr, par):
    m2, fx = M5.m2, M5.fx
    r = r0.fresh_call(SITE, regs={**REGS, "R4": FR.STOCK_STATE, "R8": PAR, "R12": IO})
    m2.poke(r.state, FP.TYPE_WORD, tw & 0xFFFFFFFF)
    for k in range(32):
        m2.poke(r.state, INL + 4 * k, fb(inl[k]))
        m2.poke(r.state, INR + 4 * k, fb(inr[k]))
        m2.poke(r.state, OUTL + 4 * k, MARK)
        m2.poke(r.state, OUTR + 4 * k, MARK)
    for a, v in ((IO, 32), (IO + 4, PAIRI), (IO + 12, PAIRO), (PAIRI, INL), (PAIRI + 4, INR),
                 (PAIRO, OUTL), (PAIRO + 4, OUTR)):
        m2.poke(r.state, a, v)
    for k, x in enumerate(par):
        m2.poke(r.state, PAR + 4 * k, fb(x))
    m2.poke(r.state, PAR + 0x18, fb(1.0))                 # the bus writes 1.0 there before its call
    entry = dict(r.state.uregs)
    before = dict(r.state.overlay)
    how = fx.run(r, 3_000_000, fx.Fixups(), stop_at=[BACK])
    out = ([m2.word(r.state, OUTL + 4 * k) or 0 for k in range(32)],
           [m2.word(r.state, OUTR + 4 * k) or 0 for k in range(32)])
    wrote = {a for a in r.state.overlay if r.state.overlay.get(a) != before.get(a)}
    return r, how, out, entry, wrote


def own(a: int) -> bool:
    """FDN8's own words (DM byte address or load address)"""
    for x in (a, a - dsp.LOAD_ALIAS):
        if FP.STATE <= x < FP.STATE + FP.STATE_BYTES:
            return True
    return False


def in_test_io(a: int) -> bool:
    return any(BUF <= x < BUF + 0x600 for x in (a, a - dsp.LOAD_ALIAS))


def run(M5, snap, m2mach, m5img, stock_img) -> dict:
    checks, numbers = {}, {}
    seq = script()
    n_stock = 40
    # 1. TYPE = stock: build vs stock image
    rs, rb = M5.init_on(snap, m2mach, stock_img), M5.init_on(snap, m2mach, m5img)
    same_out = same_regs = no_stray = ok = True
    stock_ddr, stray = set(), set()
    cost_stock = []
    for b in range(n_stock):
        tw, inl, inr, par = seq[b]
        rs, hs, os_, _, ws = call(M5, rs, tw, inl, inr, par)
        rb, hb, ob, _, wb = call(M5, rb, tw, inl, inr, par)
        ok &= hs[0] == "stop" and hb[0] == "stop"
        same_out &= os_ == ob
        same_regs &= rs.state.uregs == rb.state.uregs
        diff = {a for a in ws | wb if rs.state.overlay.get(a) != rb.state.overlay.get(a)}
        s = {a for a in diff if not own(a)}
        stray |= s
        no_stray &= not s
        cost_stock.append((hs[2], hb[2]))
        for a in ws:
            x = a if a >= 0x80000000 else a - dsp.LOAD_ALIAS
            if FR.STOCK_STATE <= x < FR.STOCK_STATE + 0x59114:
                stock_ddr.add(x - FR.STOCK_STATE)
    outside = sorted(o for o in stock_ddr if not any(lo <= o < hi for lo, hi in FR.STOCK_BUFS))
    checks["TYPE stock: both images make the call and come back to the bus"] = ok
    checks["TYPE stock: every output word as the stock reverb's (40 blocks: noise, an impulse, knobs moved)"] = same_out
    checks["TYPE stock: every register at the return as stock's"] = same_regs
    checks["TYPE stock: every word written as stock's, but FDN8's own state words"] = no_stray
    numbers["stock: instructions per block (stock image, build): min, max"] = (
        min(c[0] for c in cost_stock), max(c[0] for c in cost_stock),
        min(c[1] for c in cost_stock), max(c[1] for c in cost_stock))
    numbers["stock reverb: words it wrote in its DDR state outside the four sample buffers (offsets)"] = (
        [hex(o) for o in outside[:24]], len(outside))
    numbers["stray words (first 8)"] = [hex(a) for a in sorted(stray)[:8]]
    checks["stock reverb: no sample-buffer write outside the four buffers the switch clears "
           "(its other writes are control words below 0x38 or between the buffers)"] = all(
        o < 0x38 or any(FR.STOCK_BUFS[k][1] <= o < FR.STOCK_BUFS[k + 1][0] for k in range(3)) or o >= 0x58588
        for o in outside)

    # 2. TYPE = FDN8 on the build, against the reference (which also saw the stock blocks)
    ref = FR.Ref()
    for b in range(n_stock):
        tw, inl, inr, par = seq[b]
        ref.block(tw, inl, inr, [np.float32(x) for x in par])
    exact, regs_back, heard = True, True, 0
    first_bad = None
    cost_run, cost_clear = [], []
    for b in range(n_stock, len(seq)):
        tw, inl, inr, par = seq[b]
        rb, hb, ob, entry, wb = call(M5, rb, tw, inl, inr, par)
        want = ref.block(tw, inl, inr, [np.float32(x) for x in par])
        wbits = ([fb(x) for x in want[0]], [fb(x) for x in want[1]])
        if hb[0] != "stop" or ob != wbits:
            exact = False
            first_bad = first_bad or (b, hb[0], [hex(w) for w in ob[0][:4]], [hex(w) for w in wbits[0][:4]])
        keep = {f"R{k}" for k in range(16)} | {"I0", "I1", "I2", "I3", "I5"}
        if any(rb.state.uregs.get(k) != entry.get(k) for k in entry if str(k) in keep):
            regs_back = False
        heard += sum(1 for w in wbits[0] + wbits[1] if w & 0x7FFFFFFF)
        (cost_clear if b - n_stock < FD.RING_WORDS // FR.CHUNK else cost_run).append(hb[2])
    checks["TYPE FDN8: every output word as dnfw.fdn8.ref's (230 blocks: 32 clearing, noise, an impulse, "
           "knob moves, SIZE 127)"] = exact
    checks["TYPE FDN8: the tail is heard (not a run of zeros)"] = heard > 3000
    checks["TYPE FDN8: every R, I0-I3 and I5 register the bus left is back at the return"] = regs_back
    ring = [M5.m2.word(rb.state, dsp.FDN8_RING_DDR + 4 * k) or 0 for k in range(FD.RING_WORDS)]
    checks["TYPE FDN8: the ring, word for word, as the reference's"] = ring == [fb(x) for x in ref.ring]
    numbers["FDN8: first mismatch"] = first_bad
    numbers["FDN8: instructions per block while running: min, mean, max"] = (
        min(cost_run), round(sum(cost_run) / len(cost_run)), max(cost_run))
    numbers["FDN8: instructions per clearing block: min, max"] = (min(cost_clear), max(cost_clear))

    # 3. the switches, on silence
    z = [0.0] * 32
    par = seq[-1][3]
    peak_after, clear_blocks = 0.0, 0
    for b in range(60):
        rb, hb, ob, _, _ = call(M5, rb, 0x100, z, z, par)
        want = ref.block(0x100, z, z, [np.float32(x) for x in par])
        if want != "stock":
            clear_blocks += 1
            checks.setdefault("switch to stock: silent while its buffers clear", True)
            checks["switch to stock: silent while its buffers clear"] &= all(w == 0 for w in ob[0] + ob[1])
        else:
            peak_after = max([peak_after] + [abs(bf(w)) for w in ob[0] + ob[1]])
    rf = M5.init_on(snap, m2mach, stock_img)
    fresh_peak = 0.0
    for b in range(60 - clear_blocks):
        rf, hf, of, _, _ = call(M5, rf, 0x100, z, z, par)
        fresh_peak = max([fresh_peak] + [abs(bf(w)) for w in of[0] + of[1]])
    numbers["switch to stock: clearing blocks; then the stock reverb's peak on silence (build, a stock "
            "reverb that never had input)"] = (clear_blocks, peak_after, fresh_peak)
    checks["switch to stock: 22 clearing blocks, then no old tail (the peak on silence as a fresh stock "
           "reverb's)"] = clear_blocks == FR.STOCK_WORDS // FR.CHUNK and peak_after <= fresh_peak
    zeros = True
    for b in range(40):
        rb, hb, ob, _, _ = call(M5, rb, 0, z, z, par)
        ref.block(0, z, z, [np.float32(x) for x in par])
        zeros &= hb[0] == "stop" and all(w == 0 for w in ob[0] + ob[1])
    checks["switch back to FDN8: its ring cleared (32 blocks), then exact zeros on silence"] = zeros

    # 4. LONG (TYPE 2): from FDN8 (the ring cleared again, the variant's table copied), noise,
    # its tail (its shortest line is 185 blocks), against the reference; the ring word for word
    rnd = random.Random(23)
    exact, heard, cost_long, first_bad = True, 0, [], None
    for b in range(300):
        noisy = 40 <= b < 46
        inl = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
        inr = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
        rb, hb, ob, _, _ = call(M5, rb, 0x9ABC0200, inl, inr, par)
        want = ref.block(0x9ABC0200, inl, inr, [np.float32(x) for x in par])
        wbits = ([fb(x) for x in want[0]], [fb(x) for x in want[1]])
        if hb[0] != "stop" or ob != wbits:
            exact = False
            first_bad = first_bad or (b, hb[0])
        heard += sum(1 for w in wbits[0] + wbits[1] if w & 0x7FFFFFFF)
        if b >= FD.RING_WORDS // FR.CHUNK:
            cost_long.append(hb[2])
    checks["TYPE LONG: every output word as dnfw.fdn8.ref's (300 blocks: 32 clearing from FDN8, noise, "
           "the tail)"] = exact
    checks["TYPE LONG: the tail is heard"] = heard > 3000
    ring = [M5.m2.word(rb.state, dsp.FDN8_RING_DDR + 4 * k) or 0 for k in range(FD.RING_WORDS)]
    checks["TYPE LONG: the ring, word for word, as the reference's"] = ring == [fb(x) for x in ref.ring]
    numbers["LONG: first mismatch"] = first_bad
    numbers["LONG: instructions per block while running: min, mean, max"] = (
        min(cost_long), round(sum(cost_long) / len(cost_long)), max(cost_long))
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
