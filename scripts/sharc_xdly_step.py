"""The SHARC runner's xdly step (docs/xdly.md): the FX bus's delay call, sw 0x1c1c58 to its
return at 0x1c1c5f, run on the stock section 7 and on the build, block after block.

1. TYPE = stock (k 40 not 0): the build runs the stock delay, and every block's output, every
   register at the return and every word written are the stock image's, but XDLY's own state
   words; the stock delay's writes in its DDR state stay inside its sample area (which XDLY's
   lines use, and the switch clears) or are its control words below / above it (counted).
2. TYPE = XDLY: each block's output is dnfw.xdly.ref's, bit for bit, over noise, an impulse,
   loud input into FDBK 127 (the knee), knob moves (the times bend); the lines' written words are
   the reference's; every register the bus left is back at the return; the instructions per
   block (the DSP cost in the emulator, which charges every access alike).
3. The switches: XDLY -> stock clears the 4 MB sample area (256 blocks, silent), after which every
   word of it is 0 and the stock delay on silence gives no more than a stock delay that never had
   input; stock -> XDLY gives exact zeros on silence at once (nothing of the lines is read).
"""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.waverider import dsp, stockfx
from dnfw.xdly import design as XD
from dnfw.xdly import program as XP
from dnfw.xdly import ref as XR
import sharc_f32 as F32

SITE, BACK = dsp.DELAY_SITE_SW, 0x1C1C5F     # (the bus pushes the return address - 1, 0x1c1c5e)
PAR, IO = 0x257934, 0x257E6C
BUF = 0x83F00000                 # the test's own buffers (DDR, used by nothing)
INL, INR, OUTL, OUTR, PAIRI, PAIRO = (BUF + k * 0x100 for k in range(6))
MARK = 0x7FC00001
ALIAS = 0x28000000
# the stock delay's output pair starts at 0 (2026-11-14, opt-md, measured): with the NaN marker there, the words it
# wrote came back NaN (it reads the pair before it writes it); XDLY's calls keep the marker (it writes every word)
STOCK_FILL = 0
REGS = {f"R{k}": (0x01010101 * (k + 3)) & 0xFFFFFFFF for k in range(16)}


def alias(a: int) -> int:
    """where the emulator puts what the stock delay stores through its modified pointers: the buffer's BASE at the
    byte-scaled alias 0x28000000 + 4 a, as the stock chorus's (sharc_jsend_step) and the voice chain's
    (docs/inserts.md); on the unit both are the one place. Measured 2026-11-14 (opt-md): with the pair in DDR, its 32
    output words landed contiguously at 0x37c00800.. for OUTL 0x83f00200 (word k at alias(OUTL) + 4 k, not at
    alias(OUTL + 4 k)), and the NaN marker left at OUTL read as "non-finite" in every word"""
    return (ALIAS + 4 * a) & 0xFFFFFFFF


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def bf(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def script(n_stock=40, n_x=200, seed=11):
    """(TYPE word, in L, in R, six parameters) per block"""
    rnd = random.Random(seed)
    par = [0.3, 0.0, 0.5, 0.6, 0.0, 1.0]
    out = []
    for b in range(n_stock + n_x):
        tw = 0x12340100 if b < n_stock else 0x56780000       # the high half is k 41: not ours
        k = b if b < n_stock else b - n_stock
        loud = 2.0 if b >= n_stock and 60 <= k < 64 else 0.5
        noisy = 2 <= k < 8 or (b >= n_stock and (10 <= k < 16 or 60 <= k < 64))
        inl = [rnd.uniform(-loud, loud) if noisy else (1.0 if k == 30 and j == 5 else 0.0) for j in range(32)]
        inr = [rnd.uniform(-loud, loud) if noisy else inl[j] for j in range(32)]
        if b < n_stock and k == 20:
            par = [0.05, 256.0, 0.8, 0.7, 0.2, 0.7]
        if b == n_stock:
            par = [0.1, 0.0, 0.15, 0.6, 0.3, 0.8]
        if b >= n_stock and k == 50:
            par = [0.12, 16384.0, 0.2, 1.0, 0.9, 0.6]
        if b >= n_stock and k in (90, 91, 92, 93):
            par = [par[0] + 0.01, par[1], par[2] - 0.01, 0.4, par[4], par[5]]
        if b >= n_stock and k == 135:
            par = [0.05, 0.0, 1.0, 0.5, 1.0, 1.0]
        out.append((tw, inl, inr, [float(np.float32(x)) for x in par]))
    return out


def call(M5, r0, tw, inl, inr, par, ex=None, fill=MARK):
    m2, fx = M5.m2, M5.fx
    r = r0.fresh_call(SITE, regs={**REGS, "R4": XD.STOCK_STATE, "R8": PAR, "R12": IO})
    m2.poke(r.state, XP.TYPE_WORD, tw & 0xFFFFFFFF)
    for k in range(32):
        m2.poke(r.state, INL + 4 * k, fb(inl[k]))
        m2.poke(r.state, INR + 4 * k, fb(inr[k]))
        for base in (OUTL, OUTR):
            m2.poke(r.state, base + 4 * k, fill)
            m2.poke(r.state, alias(base) + 4 * k, fill)
    for a, v in ((IO, 32), (IO + 4, PAIRI), (IO + 12, PAIRO), (PAIRI, INL), (PAIRI + 4, INR),
                 (PAIRO, OUTL), (PAIRO + 4, OUTR)):
        m2.poke(r.state, a, v)
    for k, x in enumerate(par):
        m2.poke(r.state, PAR + 4 * k, fb(x))
    m2.poke(r.state, PAR + 0x18, fb(1.0))
    if ex is not None:                           # the Delay page's second page (design.EX): the change word, kf kn wl wr sn
        m2.poke(r.state, XD.EX, ex[0])
        for k, v in enumerate(ex[1:6]):
            m2.poke(r.state, XD.EX + 4 * (k + 1), fb(v))
    entry = dict(r.state.uregs)
    before = dict(r.state.overlay)
    how = fx.run(r, 6_000_000, fx.Fixups(), stop_at=[BACK])
    def word(base, k):
        w = m2.word(r.state, base + 4 * k) or 0
        if w != fill:
            return w
        v = m2.word(r.state, alias(base) + 4 * k)       # (0 is a value written there: never `or MARK`)
        return fill if v is None else v
    out = ([word(OUTL, k) for k in range(32)], [word(OUTR, k) for k in range(32)])
    wrote = {a for a in r.state.overlay if r.state.overlay.get(a) != before.get(a)}
    return r, how, out, entry, wrote


def own(a: int) -> bool:
    for x in (a, a - dsp.LOAD_ALIAS):
        if XP.STATE <= x < XP.STATE + XP.STATE_BYTES:
            return True
    return False


def moved(a: int) -> int:
    """2026-11-12 (opt-stock): an address in the build's L2 copy of the stock FX block, where stock has it in DDR"""
    if not stockfx.ENABLED:                      # the move off: the build keeps the block where stock has it
        return a
    return a - dsp.FX_DM + dsp.FX_DDR if dsp.FX_DM <= a < dsp.FX_DM + dsp.FX_BYTES else a


def same_word(M5, rs, rb, a: int) -> bool:
    """the word at A as stock's, A in either image's coordinates (the stock FX block is at FX_DDR in stock's, at
    FX_DM in the build's: dnfw.waverider.stockfx); a pointer into the block, saved on the stack, as stock's when it
    names the same word. (The overlay is kept by byte: the word compared is the one holding A.)"""
    a &= ~3
    if stockfx.ENABLED and dsp.FX_DM <= a < dsp.FX_DM + dsp.FX_BYTES:
        sa, ba = moved(a), a
    elif stockfx.ENABLED and dsp.FX_DDR <= ddr(a) < dsp.FX_DDR + dsp.FX_BYTES:
        sa, ba = ddr(a), ddr(a) - dsp.FX_DDR + dsp.FX_DM
    else:
        sa = ba = a
    sw, bw = M5.m2.word(rs.state, sa), M5.m2.word(rb.state, ba)
    if sw == bw:
        return True
    if sw is None or bw is None:
        return False
    sw, bw = sw & 0xFFFFFFFF, bw & 0xFFFFFFFF
    # a pointer into the block, or one of the delay's re-pointed offsets (base + 0x4000xx) saved on the stack
    return moved(bw) == sw or (bw - sw) & 0xFFFFFFFF in (stockfx.DELTA, stockfx.DELTA // 4)


def same_reg(fx, s, b) -> bool:
    """a register as stock's, or a pointer into the moved FX block where stock's points at the same word"""
    if s == b:
        return True
    return isinstance(s, fx.Const) and isinstance(b, fx.Const) and moved(b.value & 0xFFFFFFFF) == s.value & 0xFFFFFFFF


def ddr(a: int) -> int:
    return a if a >= 0x80000000 else a - dsp.LOAD_ALIAS


def run(M5, snap, m2mach, m5img, stock_img) -> dict:
    checks, numbers = {}, {}
    seq = script()
    n_stock = 40
    # 1. TYPE = stock: build vs stock image
    rs, rb = M5.init_on(snap, m2mach, stock_img), M5.init_on(snap, m2mach, m5img)
    same_out = same_regs = no_stray = ok = True
    outside, stray, cost_stock, heard_stock = set(), set(), [], F32.Ear()
    for b in range(n_stock):
        tw, inl, inr, par = seq[b]
        rs, hs, os_, _, ws = call(M5, rs, tw, inl, inr, par, fill=STOCK_FILL)
        rb, hb, ob, _, wb = call(M5, rb, tw, inl, inr, par, fill=STOCK_FILL)
        ok &= hs[0] == "stop" and hb[0] == "stop"
        same_out &= os_ == ob
        same_regs &= set(rs.state.uregs) == set(rb.state.uregs) and all(
            same_reg(M5.fx, rs.state.uregs[k], rb.state.uregs[k]) for k in rs.state.uregs)
        # compared by value, the stock FX block's words where each image keeps them (2026-11-12, opt-stock)
        diff = {a for a in ws | wb if not same_word(M5, rs, rb, a)}
        s = {a for a in diff if not own(a)}
        stray |= s
        no_stray &= not s
        cost_stock.append((hs[2], hb[2]))
        heard_stock.hear(os_[0] + os_[1])
        for a in ws:
            o = ddr(a) - XD.STOCK_STATE
            if 0 <= o < 0x800000 and not (XD.STOCK_AREA[0] <= o < XD.STOCK_AREA[1]):
                outside.add(o)
    checks["TYPE stock: both images make the call and come back to the bus"] = ok
    checks["TYPE stock: every output word as the stock delay's (40 blocks: noise, an impulse, knobs moved)"] = same_out
    checks["TYPE stock: the stock delay is heard in the test (not a run of zeros), finite"] = heard_stock.ok(200)
    checks["TYPE stock: every register at the return as stock's"] = same_regs
    checks["TYPE stock: every word written as stock's, but XDLY's own state words"] = no_stray
    numbers["stock: instructions per block (stock image, build): min, max"] = (
        min(c[0] for c in cost_stock), max(c[0] for c in cost_stock),
        min(c[1] for c in cost_stock), max(c[1] for c in cost_stock))
    numbers["stock delay: words it wrote in its DDR state outside the sample area (offsets)"] = (
        [hex(o) for o in sorted(outside)[:24]], len(outside))
    numbers["stock delay: output words (finite nonzero, non-finite)"] = repr(heard_stock)
    numbers["stray words (first 8)"] = [hex(a) for a in sorted(stray)[:8]]
    numbers["stock delay: the highest offset it wrote past the area"] = hex(max(outside, default=0))
    # (measured: control words from +0x400008, and one word at +0x5fff04: the same on both images,
    # and XDLY writes neither: checked below)

    # 2. TYPE = XDLY on the build, against the reference
    ref = XR.Ref()
    for b in range(n_stock):
        tw, inl, inr, par = seq[b]
        ref.block(tw, inl, inr, [np.float32(x) for x in par])
    exact, regs_back, heard, first_bad, cost, xd_out = True, True, F32.Ear(), None, [], set()
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
        heard.hear(wbits[0] + wbits[1])
        cost.append(hb[2])
        for a in wb:
            x = ddr(a)
            if 0x80000000 <= x < 0xA0000000 and not (XD.LINE_A <= x < XD.LINE_B + 4 * XD.LINE) \
                    and not BUF <= x < BUF + 0x600:
                xd_out.add(x)
    checks["TYPE XDLY: every output word as dnfw.xdly.ref's (200 blocks: noise, an impulse, the knee, "
           "knob moves, TIME 2 at 10 s)"] = exact
    checks["TYPE XDLY: the repeats are heard (not a run of zeros), finite"] = heard.ok(3000)
    checks["TYPE XDLY: every R, I0-I3 and I5 register the bus left is back at the return"] = regs_back
    n = ref.fill + 4
    lines_ok = True
    for line, base in ((ref.a, XD.LINE_A), (ref.b, XD.LINE_B)):
        idx = [(ref.wp - k) & XD.LINE_MASK for k in range(n)]
        lines_ok &= [M5.m2.word(rb.state, base + 4 * i) or 0 for i in idx] == [fb(line[i]) for i in idx]
    checks["TYPE XDLY: the lines' written words as the reference's"] = lines_ok
    checks["TYPE XDLY: no DDR write outside its two lines (and the test's buffers)"] = not xd_out
    numbers["XDLY: DDR words written outside its lines (first 8)"] = [hex(a) for a in sorted(xd_out)[:8]]
    numbers["XDLY: output words (finite nonzero, non-finite)"] = repr(heard)
    numbers["XDLY: first mismatch"] = first_bad
    numbers["XDLY: instructions per block while running: min, mean, max"] = (
        min(cost), round(sum(cost) / len(cost)), max(cost))

    # 2b. the second page's knobs (SLEW, KNEE, WDTH, INPT) against the reference, from a fresh start: the assembled
    # code is the reference's bit for bit at other values than the defaults (and at them, section 2 above is today's)
    exs = [(1, *XD.derive(*kn)) for kn in ((20, 30, 40, 10), (58, 61, 0, 64), (90, 127, 127, 100))]
    ex_exact, ex_heard, ex_bad = True, F32.Ear(), None
    for exv in exs:
        rx = M5.init_on(snap, m2mach, m5img)
        rref = XR.Ref()
        for b in range(n_stock, n_stock + 70):
            tw, inl, inr, par = seq[b]
            rx, hx, ox, _, _ = call(M5, rx, tw, inl, inr, par, exv)
            want = rref.block(tw, inl, inr, [np.float32(x) for x in par], exv)
            wbits = ([fb(x) for x in want[0]], [fb(x) for x in want[1]])
            if hx[0] != "stop" or ox != wbits:
                ex_exact = False
                ex_bad = ex_bad or (exv[0], b, hx[0])
            ex_heard.hear(wbits[0] + wbits[1])
    checks["TYPE XDLY, second page: every output word as dnfw.xdly.ref's at three settings of SLEW KNEE WDTH INPT "
           "(70 blocks each), heard, finite"] = ex_exact and ex_heard.ok(1000)
    numbers["XDLY second page: first mismatch"] = ex_bad

    # 3. the switches, on silence
    z = [0.0] * 32
    par = seq[-1][3]
    clear_blocks, silent, after, cost_clear, nz = 0, True, [], [], [-1]
    for b in range(XD.STOCK_WORDS // XD.CHUNK + 40):
        want = ref.block(0x100, z, z, [np.float32(x) for x in par])     # (the model first: which fill)
        rb, hb, ob, _, _ = call(M5, rb, 0x100, z, z, par, fill=MARK if want != "stock" else STOCK_FILL)
        if want != "stock":
            clear_blocks += 1
            silent &= all(w == 0 for w in ob[0] + ob[1])
            cost_clear.append(hb[2])
            if clear_blocks == XD.STOCK_WORDS // XD.CHUNK:          # the clear's last block: read it all
                nz = [k for k in range(0, XD.STOCK_WORDS, 61)
                      if (M5.m2.word(rb.state, XD.LINE_A + 4 * k) or 0) != 0]
        else:
            after.extend(bf(w) for w in ob[0] + ob[1])
    rf = M5.init_on(snap, m2mach, stock_img)
    fresh = []
    for b in range(40):
        rf, hf, of, _, _ = call(M5, rf, 0x100, z, z, par, fill=STOCK_FILL)
        fresh.extend(bf(w) for w in of[0] + of[1])
    # NaN in either run fails (M5.V.peak is NaN on any non-finite sample; NaN <= x is False)
    peak_after, fresh_peak = M5.V.peak(after), M5.V.peak(fresh)
    checks["switch to stock: silent while its sample area clears"] = silent
    checks["switch to stock: 256 clearing blocks, then no old tail (the peak on silence as a fresh "
           "stock delay's), finite"] = clear_blocks == XD.STOCK_WORDS // XD.CHUNK and peak_after <= fresh_peak
    checks["switch to stock: the sample area is 0 when the clear ends (every 61st word read)"] = not nz
    numbers["switch to stock: words of the area not 0 after the clear (first 8 word indices)"] = nz[:8]
    numbers["switch to stock: clearing blocks; the stock delay's peak on silence after (build, fresh)"] = (
        clear_blocks, peak_after, fresh_peak)
    numbers["XDLY: instructions per clearing block: min, max"] = (min(cost_clear), max(cost_clear))
    zeros = True
    for b in range(20):
        rb, hb, ob, _, _ = call(M5, rb, 0, z, z, par)
        ref.block(0, z, z, [np.float32(x) for x in par])
        zeros &= hb[0] == "stop" and all(w == 0 for w in ob[0] + ob[1])
    checks["switch back to XDLY: exact zeros on silence at once (nothing of the lines read)"] = zeros
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
