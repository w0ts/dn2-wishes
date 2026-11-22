"""The SHARC runner's levels step (2026-11-20, the mixer meters; scratch/mixer-overview.md; sampler.program.levels,
dac_guard; sampler.machines LV_*).

Blocks on the build with the engine's own output stage at work: at the routing's entry every voice slot s (routed to
track s by the frame) gets a sine of its own amplitude, every stock track buffer (the raw track B) one of another,
the three send returns (both their A and B blocks) their own; some tracks and returns past Overbridge's full scale,
some under, a NaN in one; between blocks the driver's master-mix call (wr_pvmix, dac_guard) runs on a main mix with
and without overs, and the input block is set, at and under its top. Two runs: the frame's source flag (+0xa7a) on A
(the routing's blocks) with the ColdFire asking for levels (LV_WANT in the pool), and on B without.

Checks, each block against what the block before left (levels reads the output stage's last blocks):
- truth: a track's or a return's clip bit is set exactly when the output stage saturated one of its channel's words
  that block (TX slots 2..13, the reply's records for the rest: what Overbridge and USB carry);
- every clip bit and every kept peak as an independent model (float32, numpy-free) of the same buffers: tracks and
  returns x OB_GAIN, the analog outputs' peaks (dac_guard, each side), the input against IN_TOP, the main mix as
  Overbridge gets it (2026-11-20: TX slots 0, 1 as sent, max |w >> 8|, at 0x7fffff a clip; its peaks units 22, 23),
  held under LV_TOP (a NaN: LV_TOP, and a clip);
- the reply's word 6, both pages: LV_REPLY_MAGIC | this block's bits | the last block's;
- asked: a levels packet (LV_MAGIC) in TDM slots 14..15 every LV_EVERY-th block, its units the peaks kept since the
  last one (x LV_ONE, truncated), the peaks then zero; the blocks between carry the idle packet (POS_MAGIC); not
  asked: never a levels packet, the count at 0;
- the main mix as the codec gets it: under full scale stock's words (dacover checks the words; here the hold).

MEASURE (LEVELS_MEASURE=1): the scales from a voice block to the outputs (scratch/mixer-overview.md, measurement 2).
"""

from __future__ import annotations

import math
import os
import struct

from dnfw.sampler import machines as SM
from dnfw.sampler import program as SP
from dnfw.waverider import dsp

ROUTING_SW = 0x1C1F1E
MASTER_CALL_SW = 0x1C215C
OUTPUT_CALL_SW = 0x1C307B
VOICES = 0x257EE8
MAIN_BUS = 0x25BB68
MIX = SM.MIX_BUF
FX_RET = (0x25B068, 0x25B868)
TX_BASE, TX_PAGE_WORD = SM.TDM_TX, SM.TDM_PAGE
SRC_FLAG = 0xA7A
ROUTE = 0xA5A                       # the frame's voice slot -> track halfwords
PTRS = 0x257EA8                     # the output stage's track buffer pointers (B's source)
RECORDS = 0x1C
DAC_PAGE = 0x2C0478
BLOCKS = 10
# 2026-11-21 (the send FX's own returns): the three per-track sends and the kit's FX and master words as sendfx's stock
# scenario has them (sharc_sendfx_step.tail_words: stock-valid, the reverb and delay on stock types, the delay's TIME
# at its shortest; with the words at 0, as base_frame leaves them, the returns stayed silent: measured 2026-11-21)
SEND_SEED = 11
RET_FLOOR = 1e-4


def bf(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def s32(w: int) -> int:
    w &= 0xFFFFFFFF
    return w - (1 << 32) if w >= 1 << 31 else w


G = bf(SM.OB_GAIN_BITS)


def measure(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    out = {}
    for flag in (1, 0):
        for amp in (0.01, 0.05):
            state = M5.init_on(snap, m2mach, m5img, warm=True)
            rows = []
            for b in range(4):
                cur = {}

                def at_routing(r, b=b):
                    for a in range(*FX_RET, 4):
                        m2.poke(r.state, a, 0)
                    for s in range(16):
                        for j in range(32):
                            x = amp * math.sin(0.2 * (32 * b + j)) if s == 0 else 0.0
                            m2.poke(r.state, VOICES + 0x100 * s + 4 * j, fb(x))
                            m2.poke(r.state, VOICES + 0x100 * s + 0x80 + 4 * j, fb(x))

                def at_master(r):
                    cur["bus"] = max(abs(bf(m2.word(r.state, MAIN_BUS + 4 * j))) for j in range(64))

                def frames(_b):
                    f = M5.base_frame(sound, machines)
                    f.put(SRC_FLAG, flag)
                    return f.to_bytes()
                res = M5.run_blocks(state, frames, 1, extra_hooks={ROUTING_SW: at_routing, MASTER_CALL_SW: at_master})
                if not res.get("ok"):
                    out[f"flag {flag} amp {amp}"] = {"halt": str(res.get("halt"))}
                    break
                state = res["state"]
                st = state.state
                page = TX_BASE + (((m2.word(st, TX_PAGE_WORD) or 0) & 1) << 11)

                def tx(s, st=st, page=page):
                    return max(abs(s32(m2.word(st, page + 64 * f + 4 * s) or 0)) for f in range(32)) / 2.0 ** 31
                mix = max(abs(bf(m2.word(st, MIX + 4 * j))) for j in range(64))
                rows.append({"block": b, "voice_peak": amp, "main_bus": cur.get("bus"), "main_mix": mix,
                             "ob_main": tx(0), "ob_track1": tx(2)})
            out[f"flag {flag} amp {amp}"] = rows
    return {"ok": True, "checks": {"measured": True}, "numbers": out}


# -- the test --------------------------------------------------------------------------------------------------------

def amp_voice(t: int, b: int) -> float:
    """track t's voice sine: Overbridge's track A channel is ~66 x this (3.2768 x 14.125 x 1.4286): 0.0151 is its top"""
    return (0.004 + 0.0012 * t) * (1.0 + 0.25 * (b % 3))


def amp_raw(t: int, b: int) -> float:
    """track t's raw buffer (B's source; B = x 11.627, Overbridge x 1.4286: ~16.6 x this): 0.060 is its top"""
    return (0.02 + 0.004 * t) * (1.0 + 0.2 * (b % 2))


def amp_ret(r: int, b: int) -> float:
    return (0.4, 0.69, 0.75)[r] * (1.0 + 0.05 * (b % 2))


def mix_of(b: int) -> list[float]:
    """the main mix the driver's call gets after block b: L 32 then R 32"""
    peak_l = (0.6, 1.25, 0.9, 1.0)[b % 4]
    peak_r = (0.5, 0.7, -1.5, 0.3)[b % 4]
    out = [peak_l * math.sin(0.37 * j + b) for j in range(32)] + [0.5 * peak_r * math.sin(0.21 * j) for j in range(32)]
    out[5] = peak_l
    out[37] = peak_r
    return out


def in_of(b: int) -> list[float]:
    top = (0.3, 0.99995, 0.9998, -1.0)[b % 4]
    out = [0.5 * top * math.cos(0.11 * j) for j in range(64)]
    out[9] = top
    return out


def maxabs(ws) -> float:
    """the largest |x| of the words WS as float32, NaN if any is one"""
    xs = [bf(w) for w in ws]
    if any(x != x for x in xs):
        return float("nan")
    return max(abs(x) for x in xs)


def take(peak: float, top: float) -> tuple[bool, float]:
    """(clipped, kept): as _lv_take: not (peak < top) clips (a NaN too); kept held under LV_TOP"""
    clip = not (peak < top)
    kept = peak if peak < f32(SM.LV_TOP) else f32(SM.LV_TOP)
    return clip, kept


def short(m2, st, o: int) -> int:
    w = m2.word(st, o & ~3) or 0
    return (w >> 16) & 0xFFFF if o & 2 else w & 0xFFFF


def channel_saturated(m2, st, page: int, reply: int, k: int) -> bool:
    """Overbridge channel K's words this block hold full scale (the output stage's FIX saturated)"""
    if k <= 13:
        ws = [(m2.word(st, page + 64 * f + 4 * k) or 0) & 0xFFFFFFFF for f in range(32)]
        return any(w in (0x7FFFFFFF, 0x80000000) for w in ws)
    pair, odd = divmod(k - 14, 2)
    for f in range(32):
        o = reply + RECORDS + 84 * f + 6 * pair
        s0, s1, s2 = short(m2, st, o), short(m2, st, o + 2), short(m2, st, o + 4)
        v = ((s1 & 0xFF) << 16 | s2) if odd else (s0 << 8 | s1 >> 8)
        if v in (0x7FFFFF, 0x800000):
            return True
    return False


def run_scenario(M5, snap, m2mach, m5img, sound, machines, flag: int, asked: bool, nan_at: int,
                 sends: int | None = None) -> tuple[dict, dict]:
    """SENDS (2026-11-21, the gate gap "the runner's full blocks do not model the send-FX path"): None, the returns
    are the harness's sines (as before); a level, the returns are what the send FX made: a WAVETONE voice on track 0
    (voice slot 0, the one whose chain the runner sets up), triggered every third block, its three sends at SENDS, the
    kit's FX and master words as sendfx's stock scenario (stock FX types), and nothing written over the returns"""
    import sharc_sendfx_step as SF                 # noqa: PLC0415
    m2, fx = M5.m2, M5.fx
    fx_words = SF.tail_words(SEND_SEED, ours=False)
    K = SP.LK
    checks, numbers = {}, {"blocks": []}
    state = M5.init_on(snap, m2mach, m5img, warm=True)
    if asked:
        m2.poke(state.state, dsp.SMP_POOL_DDR + SM.LV_WANT_OFF, SM.LV_WANT)
    rets = [((SP.LV_RET_A if flag else SP.LV_RET_B) + SP.LV_RET_STRIDE * r) for r in range(3)]
    prev_bits, kept, last, halt = 0, [0.0] * SM.LV_CH, None, None
    lcnt = 0
    per = {"truth": True, "bits": True, "peaks": True, "reply": True, "packets": True, "idle": True}
    seen = {"clipped": 0, "clean": 0, "nan": 0, "returns sounding": 0, "returns not finite": 0}
    for b in range(BLOCKS):
        cur = {}

        def at_routing(r, b=b):
            st = r.state
            for s in range(16):
                a = amp_voice(s, b)
                for j in range(32):
                    x = a * math.sin(0.3 * (32 * b + j) + s)
                    if s == 9 and b == nan_at and j == 7:
                        x = float("nan")
                    m2.poke(st, VOICES + 0x100 * s + 4 * j, fb(x))
                    m2.poke(st, VOICES + 0x100 * s + 0x80 + 4 * j, fb(-0.8 * x))
                tb = m2.word(st, PTRS + 4 * s) or 0
                a = amp_raw(s, b)
                for j in range(32):
                    m2.poke(st, tb + 4 * j, fb(a * math.sin(0.17 * (32 * b + j) + 2 * s)))
            if sends is not None:
                return                      # (the returns: the send FX's own)
            for a0 in range(*FX_RET, 4):
                m2.poke(st, a0, 0)
            for r_ in range(3):
                a = amp_ret(r_, b)
                for base in (SP.LV_RET_A + SP.LV_RET_STRIDE * r_, SP.LV_RET_B + SP.LV_RET_STRIDE * r_):
                    for j in range(64):
                        m2.poke(st, base + 4 * j, fb(a * math.sin(0.23 * j + r_ + b)))

        def at_out(r):
            cur["reply"] = m2.word_reg(r, "R12")

        def frames(_b, b=b):
            if sends is None:
                f = M5.base_frame(sound, machines)
            else:
                f = M5.base_frame(sound, machines, t0=1, overrides={s_: sends for s_ in SF.SEND_SLOTS},
                                  trigger=b % 3 == 0)
                for o, v in fx_words.items():
                    f.put(o, v)
            f.put(SRC_FLAG, flag)
            for t in range(16):
                f.put(ROUTE + 2 * t, t)
            return f.to_bytes()
        res = M5.run_blocks(state, frames, 1, extra_hooks={ROUTING_SW: at_routing, OUTPUT_CALL_SW: at_out})
        if not res.get("ok"):
            halt = f"block {b}: {res.get('halt')}"
            break
        state = res["state"]
        st = state.state
        row = {"block": b}
        if b > 0:                           # this block's levels read what block b - 1 left (expect, below)
            bits = (m2.word(st, K["lprev"]) or 0) & 0xFFFFFFFF
            row["bits"] = f"{bits:#08x}"
            per["bits"] &= bits == want_bits
            per["truth"] &= (bits & 0x7FFFF & ~nan_bits) == truth_bits & ~nan_bits   # (a NaN FIXes to all ones)
            seen["clipped"] += bool(truth_bits)
            seen["clean"] += truth_bits != 0x7FFFF
            seen["nan"] += bool(nan_bits & bits)
            got_kept = [bf(m2.word(st, K[f"lpk{k}"])) for k in range(SM.LV_CH)]
            for k in range(SM.LV_CH):
                kept[k] = max(kept[k], exp_kept[k])
            sent = asked and (lcnt + 1) % SM.LV_EVERY == 0 and lcnt + 1 > 0
            if asked and lcnt == 0:
                kept = [0.0] * SM.LV_CH     # the peaks start afresh with the asking (after this block's)
            unit0 = (m2.word(st, SM.LINK_BUF) or 0) & 0xFFFF
            page = TX_BASE + (((m2.word(st, TX_PAGE_WORD) or 0) & 1) << 11)
            w0 = m2.word(st, page + 4 * 14) or 0
            wire = (w0 >> 8) & 0xFFFF if (w0 >> 24) == SM.TDM_TAG else w0 & 0xFFFF
            if sent:
                units = [(m2.word(st, SM.LINK_BUF + 4 * (1 + k)) or 0) & 0xFFFF for k in range(SM.LV_CH)]
                want_units = [int(f32(kp * SM.LV_ONE)) for kp in kept]
                per["packets"] &= unit0 == SM.LV_MAGIC and wire == SM.LV_MAGIC and units == want_units
                per["packets"] &= all(x == 0.0 for x in got_kept)
                row["packet"] = units
                kept = [0.0] * SM.LV_CH
            else:
                per["idle"] &= unit0 == SM.POS_MAGIC and wire == SM.POS_MAGIC
                per["peaks"] &= all(fb(a) == fb(e) for a, e in zip(got_kept, kept))
            if asked:
                lcnt += 1
            per["idle"] &= (m2.word(st, K["lcnt"]) or 0) == lcnt
            reply = [(m2.word(st, pg + SM.LV_REPLY_AT) or 0) & 0xFFFFFFFF for pg in SM.REPLY_PAGES]
            per["reply"] &= reply == [SM.LV_REPLY_MAGIC | bits | prev_bits] * 2
            prev_bits = bits
        if b == 0 and asked:                # block 0's levels packet path: asked from its start, the count 1 and the
            lcnt = 1                        # peaks started afresh (after its own, the snapshot's)
            kept = [0.0] * SM.LV_CH
        numbers["blocks"].append(row)
        # what this block left, as the next block's levels must read it: the model and the truth
        page = TX_BASE + (((m2.word(st, TX_PAGE_WORD) or 0) & 1) << 11)
        reply = cur.get("reply") or 0
        want_bits = truth_bits = nan_bits = 0
        exp_kept = [0.0] * SM.LV_CH
        for t in range(16):
            base = (SP.LV_TRK_A if flag else SP.LV_TRK_B) + 0x100 * t
            pk = maxabs([m2.word(st, base + 4 * j) or 0 for j in range(64)])
            clip, kp = take(f32(pk * G) if pk == pk else pk, 1.0)
            want_bits |= clip << t
            nan_bits |= (pk != pk) << t
            exp_kept[t] = kp
            if channel_saturated(m2, st, page, reply, 2 + 2 * t) or channel_saturated(m2, st, page, reply, 3 + 2 * t):
                truth_bits |= 1 << t
        ret_pk = []
        for r_ in range(3):
            pk = maxabs([m2.word(st, rets[r_] + 4 * j) or 0 for j in range(64)])
            ret_pk.append(pk)
            clip, kp = take(f32(pk * G), 1.0)
            want_bits |= clip << (16 + r_)
            exp_kept[16 + r_] = kp
            if channel_saturated(m2, st, page, reply, 34 + 2 * r_) or channel_saturated(m2, st, page, reply, 35 + 2 * r_):
                truth_bits |= 1 << (16 + r_)
        seen["returns sounding"] += any(p == p and p > RET_FLOOR for p in ret_pk)
        seen.setdefault("return peaks", []).append([round(p, 7) if p == p else "nan" for p in ret_pk])
        seen["returns not finite"] += any(not math.isfinite(p) for p in ret_pk)
        # the driver's master-mix call after this block, on a mix of our own; the input block
        mix = mix_of(b)
        for j in range(64):
            m2.poke(st, MIX + 4 * j, fb(mix[j]))
        inb = in_of(b)
        for j in range(64):
            m2.poke(st, SM.IN_BUF + 4 * j, fb(inb[j]))
        idx = m2.word(st, 0x268A38) or 0
        # 2026-11-20: Overbridge / USB main as sent (TX slots 0, 1 of this block's page, sampler.program ob_peaks): in odd
        # blocks words of our own (one at full scale every 4th block, the negative top in another), else the engine's
        tx_pg = TX_BASE + ((idx & 1) << 11)
        if b % 2:
            for j in range(32):
                for s_ in (0, 1):
                    w = int(0x30000000 * math.sin(0.4 * j + s_ + b))
                    if j == 5 and s_ == b % 2 and b % 4 == 1:
                        w = 0x7FFFFFFF
                    if j == 9 and s_ == 1 and b % 4 == 3:
                        w = -0x80000000
                    m2.poke(st, tx_pg + 64 * j + 4 * s_, w & 0xFFFFFFFF)
        r = state.fresh_call(dsp.PVMIX_SITE_SW, regs={"R4": DAC_PAGE + (idx << 8), "R13": 4})
        how = fx.run(r, 400000, fx.Fixups(), stop_at=[0x1C9D3F])
        if how[0] == "stop":
            if r.state.call_stack and r.state.call_stack[-1] == dsp.PVMIX_SW + (len(dsp.pvmix_object()) - 6) // 2:
                r.state.call_stack[-1] = 0x1C9FDB
            how = fx.run(r, 400000, fx.Fixups(), stop_at=[0x1C9FDB])
        if how[0] != "stop":
            halt = f"the master-mix call: {how[0]} at block {b}"
            break
        state = r
        st = state.state
        ob = []
        for s_ in (0, 1):                   # the words as sent (after the preview's add): max |w >> 8|
            ob.append(max(abs(s32(m2.word(st, tx_pg + 64 * j + 4 * s_) or 0) >> 8) for j in range(32)))
        per.setdefault("ob", True)
        per["ob"] &= [(m2.word(st, K["dobl"]) or 0), (m2.word(st, K["dobr"]) or 0)] == ob
        want_bits |= (max(ob) >= 0x7FFFFF) << SM.LV_BIT_MAIN_OB
        seen.setdefault("ob_clip", 0)
        seen["ob_clip"] += max(ob) >= 0x7FFFFF
        exp_kept[22], exp_kept[23] = f32(ob[0] / 2 ** 23), f32(ob[1] / 2 ** 23)
        for k, side in ((19, mix[:32]), (20, mix[32:])):
            pk = max(abs(f32(x)) for x in side)
            clip, kp = take(pk, 1.0)
            want_bits |= clip << SM.LV_BIT_DAC
            exp_kept[k] = kp
        clip, kp = take(max(abs(f32(x)) for x in inb), f32(SM.IN_TOP))
        want_bits |= clip << SM.LV_BIT_IN
        exp_kept[21] = kp
        held = [bf(m2.word(st, MIX + 4 * j)) for j in range(64)]
        per.setdefault("hold", True)
        per["hold"] &= all(fb(h) == fb(x if abs(f32(x)) <= SM.DAC_TOP else math.copysign(SM.DAC_TOP, x))
                           for h, x in zip(held, (f32(v) for v in mix)))
        truth_bits &= 0x7FFFF
    ok = halt is None
    name = f"source {'A' if flag else 'B'}, {'asked' if asked else 'not asked'}"
    if sends is not None:
        name += f", the returns from the send FX (sends {sends:#06x})"
    checks[f"{name}: {BLOCKS} blocks and the master-mix call between them run"] = ok
    checks[f"{name}: a track's or return's clip bit exactly when its Overbridge channel's words saturated"] = (
        ok and per["truth"])
    checks[f"{name}: every clip bit as the model's (tracks, returns, main to Overbridge, analog outputs, input)"] = (
        ok and per["bits"])
    checks[f"{name}: the kept peaks as the model's between packets"] = ok and per["peaks"]
    checks[f"{name}: Overbridge / USB main's peaks as sent (TX slots 0, 1, max |w >> 8|), some blocks at full scale"] = (
        ok and per.get("ob", False) and seen.get("ob_clip", 0) > 0)
    checks[f"{name}: the reply's word 6 in both pages: magic | this block's bits | the last block's"] = ok and per["reply"]
    if asked:
        checks[f"{name}: a levels packet every {SM.LV_EVERY}th block, units the kept peaks x LV_ONE, then zero"] = (
            ok and per["packets"])
    checks[f"{name}: every other block's packet the idle one; the count as the model's"] = ok and per["idle"]
    checks[f"{name}: the main mix held to +-DAC_TOP, every word under it unchanged"] = ok and per.get("hold", False)
    checks[f"{name}: (control) the outputs saturated in some blocks and not all channels in any"] = (
        ok and seen["clipped"] > 0 and seen["clean"] > 0)
    if sends:
        checks[f"{name}: the send FX's returns sound (> {RET_FLOOR:g}) in some block, finite in every block"] = (
            ok and seen["returns sounding"] > 0 and seen["returns not finite"] == 0)
    if nan_at < BLOCKS and flag:
        checks[f"{name}: a NaN in a track's block is a clip bit"] = ok and seen["nan"] > 0
    numbers["halt"] = halt
    numbers["seen"] = seen
    return checks, numbers


def run(M5, snap, m2mach, m5img, stockimg, sound, machines) -> dict:
    if os.environ.get("LEVELS_MEASURE"):
        return measure(M5, snap, m2mach, m5img, sound, machines)
    checks, numbers = {}, {}
    for flag, asked, nan_at, sends in ((1, True, 5, None), (0, False, 3, None),
                                       (1, True, BLOCKS, 0x7F00), (1, True, BLOCKS, 0)):
        c, n = run_scenario(M5, snap, m2mach, m5img, sound, machines, flag, asked, nan_at, sends)
        checks.update(c)
        numbers[f"source {'A' if flag else 'B'}" + ("" if sends is None else f", sends {sends:#06x}")] = n
    # control (2026-11-21): the voice's sends reach the returns: with its sends at 0 they differ (with them at 0 the
    # returns still sound: measured 2026-11-21, cause not measured; the other voices' blocks the harness writes may feed
    # their sends)
    up, zero = (numbers[f"source A, sends {v:#06x}"]["seen"].get("return peaks") for v in (0x7F00, 0))
    checks["source A: (control) the voice's sends at 0 give other returns than at 0x7f00 (the send path carries it)"] = (
        bool(up) and bool(zero) and up != zero)
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
