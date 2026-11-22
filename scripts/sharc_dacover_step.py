"""The SHARC runner's dacover step (2026-11-20, the mixer meters; scratch/mixer-overview.md): what the analog
outputs get for a main-mix sample at or over full scale, on stock and on the build.

The driver converts the main mix (MIX_BUF, L 32 floats then R) for the codec in 0x1c9d3f (`R0 = FIX F1 BY R2`, R2 =
31, into the DAC page 0x2c0478 + (DM(0x268a38) << 8), L R interleaved), then every arm ends at 0x1c9e29, which
negates the page's 64 words as integers (`R1 = -R2`). Neither switches the ALU's saturation (MODE1.ALUSAT, 0 from
boot); the SHARC+ PRM's FIX page (digikit's sharc_core/floats.py implements it verbatim): with saturation off, a
result that overflows is all ones. So on stock an over reaches the DAC as -(-1) = 1, about silence, and exactly -1.0
as -(0x80000000) = 0x80000000, the wrong sign.

The build (dnfw.sampler.program.dac_guard, at wr_pvmix, after the preview and MON) holds every main-mix word to
+-DAC_TOP (the largest float under 1.0) before the stock conversion, so an over becomes a clean clip, and keeps each
side's peak (|x| before the hold) for the meters (the User, 2026-11-20: "yes", under the
stock-code rule: only samples at or over full scale change, Overbridge and USB untouched).

Checks, from the driver's call site (sw 0x1c9fd2) to the end of the negate (sw 0x1c9e43), stock and build run on the
same mix:
- stock: every in-range word is -FIX(x); the overs are the PRM's all-ones result negated (1), -1.0 is 0x80000000
  (the measurement: the runner sees stock's dropout, so the build's change is seen to be needed);
- build: every word of an in-range sample bit-identical to stock's; every over at full scale with its own sign
  (0x80000080 for a positive over after the negate, 0x7fffff80 for a negative one), -1.0 included; a NaN as stock
  has it; each side's peak as the model's; a block with no over bit-identical to stock's.
"""

from __future__ import annotations

import os
import struct

from dnfw.sampler import machines as SM
from dnfw.sampler import program as SP
from dnfw.sampler import live as SL
from dnfw.waverider import dsp

DAC_BASE, PAGE_WORD = 0x2C0478, 0x268A38
NEGATE_END = 0x1C9E43                        # after 0x1c9e29's SIMD loop and its MODE1 write
CALL_TARGET, BACK_IN_DRIVER = 0x1C9D3F, 0x1C9FDB


def fbits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def ffrom(w: int) -> float:
    return struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0]


def s32(w: int) -> int:
    w &= 0xFFFFFFFF
    return w - (1 << 32) if w >= 1 << 31 else w


OVERS_L = [1.5, -1.5, 1.0, -1.0, 0.99, -0.99, SM.DAC_TOP, -SM.DAC_TOP, 1.0000001, -1.0000001, 3.0, -3.0, 0.5, -0.5,
           float("nan")]


def mixes():
    """(name, 64 words L then R): one with overs on both sides, one in range"""
    over_l = OVERS_L + [0.01 * k - 0.15 for k in range(32 - len(OVERS_L))]
    over_r = [-0.5 * x for x in over_l]
    over_r[20], over_r[21] = 2.0, -1.25
    calm = [0.02 * k - 0.3 for k in range(64)]
    return [("overs", [fbits(x) for x in over_l + over_r]), ("in range", [fbits(x) for x in calm])]


def fix31(x: float) -> int | None:
    """FIX x BY 31, round to nearest even; None when it overflows (or x is a NaN: all ones too)"""
    if x != x:
        return None
    v = round(x * 2.0 ** 31)
    return v if -(1 << 31) <= v <= (1 << 31) - 1 else None


def stock_word(x: float) -> int:
    """the DAC word stock writes for x, as the PRM says (ALUSAT 0): overflow -> all ones, then an integer negate
    that wraps"""
    v = fix31(x)
    v = -1 if v is None else v
    return (-v) & 0xFFFFFFFF


def run(M5, snap, m2mach, m5img, stockimg) -> dict:
    m2, fx = M5.m2, M5.fx
    L = SL.layout()
    C = L.C
    regs = {f"R{k}": 0x01010101 * (k + 1) for k in range(16)}
    regs.update({"I1": 0x2DF000, "R2": 0x00C0FFEE})
    measure_only = bool(os.environ.get("DACOVER_MEASURE"))

    def one(image, mix, build: bool):
        page = DAC_BASE + (1 << 8)                       # the driver's R4: the DAC page (DM(0x268a38) = 1)
        r = M5.init_on(snap, m2mach, image).fresh_call(dsp.PVMIX_SITE_SW, regs={**regs, "R4": page, "R13": 4})
        for k in range(64):
            m2.poke(r.state, SM.MIX_BUF + 4 * k, mix[k])
        m2.poke(r.state, C["pvn"], 0)                     # no preview
        m2.poke(r.state, SM.REC_MON, 0)
        m2.poke(r.state, PAGE_WORD, 1)
        for k in range(64):
            m2.poke(r.state, page + 4 * k, 0x5EED0000 + k)
        fxs = fx.Fixups()
        how = fx.run(r, 400000, fxs, stop_at=[CALL_TARGET])
        if how[0] == "stop" and build:
            if r.state.call_stack and r.state.call_stack[-1] == dsp.PVMIX_SW + (len(dsp.pvmix_object()) - 6) // 2:
                r.state.call_stack[-1] = BACK_IN_DRIVER
        if how[0] == "stop":
            how = fx.run(r, 400000, fxs, stop_at=[NEGATE_END])
        words = [(m2.word(r.state, page + 4 * k) or 0) & 0xFFFFFFFF for k in range(64)]
        dac = {"L": words[0::2], "R": words[1::2]}
        extra = {}
        if build:
            extra = {"L": m2.word(r.state, SP.LK["dpkl"]) or 0, "R": m2.word(r.state, SP.LK["dpkr"]) or 0}
        return how, dac, extra

    checks, numbers = {}, {}
    for name, mix in mixes():
        xs = {"L": [ffrom(w) for w in mix[:32]], "R": [ffrom(w) for w in mix[32:]]}
        hs, ds, _ = one(stockimg, mix, False)
        checks[f"{name}: stock reaches the end of the negate"] = hs[0] == "stop"
        want_s = {side: [stock_word(x) for x in xs[side]] for side in "LR"}
        checks[f"{name}: stock's DAC words as the PRM reads (FIX overflow all ones, integer negate)"] = (
            hs[0] == "stop" and ds == want_s)
        overs = [(side, k, x) for side in "LR" for k, x in enumerate(xs[side]) if fix31(x) is None or x <= -1.0]
        numbers[f"{name}: stock"] = {f"{side}{k} {x:+.8g}": f"{ds[side][k]:#010x}" for side, k, x in overs}
        if overs:
            checks[f"{name}: stock writes ~0 (|word| <= 1) for every over, -1.0 as 0x80000000"] = hs[0] == "stop" and all(
                (ds[side][k] == 0x80000000) if x == -1.0 else abs(s32(ds[side][k])) <= 1 for side, k, x in overs)
        if measure_only:
            continue
        hb, db, extra = one(m5img, mix, True)
        checks[f"{name}: the build reaches the end of the negate"] = hb[0] == "stop"
        top = SM.DAC_TOP
        ok_in = ok_over = True
        for side in "LR":
            for k, x in enumerate(xs[side]):
                if x != x:                      # a NaN: held as it is (MIN / MAX keep it), stock's word
                    ok_in &= db[side][k] == ds[side][k]
                elif abs(x) <= top:
                    ok_in &= db[side][k] == ds[side][k]
                else:
                    ok_over &= db[side][k] == stock_word(top if x > 0 else -top)
        checks[f"{name}: the build's words for every sample under full scale are stock's"] = hb[0] == "stop" and ok_in
        checks[f"{name}: every over a clean full-scale clip with its own sign"] = hb[0] == "stop" and ok_over

        def want_peak(side):
            v = xs[side]
            if any(x != x for x in v):
                return None                     # NaN
            return fbits(max(abs(x) for x in v))
        ok_pk = all((want_peak(side) == extra.get(side)) if want_peak(side) is not None
                    else ((extra.get(side, 0) & 0x7F800000) == 0x7F800000 and extra.get(side, 0) & 0x7FFFFF)
                    for side in "LR")
        checks[f"{name}: each side's peak |x| before the hold kept for the meters (a NaN: NaN)"] = ok_pk
        if not overs:
            checks[f"{name}: no over: the build's page is stock's, word for word"] = hb[0] == "stop" and db == ds
        numbers[f"{name}: build"] = {f"{side}{k} {x:+.8g}": f"{db[side][k]:#010x}" for side, k, x in overs}
        numbers[f"{name}: build peaks L / R"] = [f"{extra.get('L', 0):#010x}", f"{extra.get('R', 0):#010x}"]
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
