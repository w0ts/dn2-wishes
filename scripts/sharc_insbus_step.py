"""The SHARC runner's insbus step (docs/inserts.md "On the track's bus"): real blocks of the build, PERC
voices sounding, the engine's call of the output stage (sw 0x1c307b) landing in wr_inbus
(dnfw.waverider.dsp.INSBUS_SW), which JUMPs on to 0x1c244d (dnfw.inserts.bus.OUT_SW). Each track's bus
block (design.BUS_BLOCKS + 0x100 t) captured at both entries.

**The test's bus blocks.** The routing (0x1c1f1e) sums the voices' stereo blocks, which the emulator writes
elsewhere (sharc_inspost_step's docstring), so in the runner the track blocks hold no voice. This step puts
its own sound in them (seeded noise, a burst then silence) at wr_inbus's entry, as the routing would have,
and the unpacked records (design.TABLE) the pre pass would have left.

1. Every insert OFF: every track's block at 0x1c244d's entry is the block at the pass's entry, and every
   register the engine passed (R0..R15, I0..I4, I12) is back as it came.
2. FDN8 and XDLY in both slots of several tracks (bus_test.rows_at's script: half wet, wet only, FDN8 then
   XDLY on one track, a FULL slot, an XDLY instance moved to another track): every block every track's
   block as dnfw.inserts.busref's, bit for bit; the tracks with no bus insert untouched; the send FX's own
   words (FDN8's and XDLY's) as they were; every register back.
3. The pass alone: OFF, one FDN8 (a clearing block, then steady), one XDLY, eight FDN8 + four XDLY.
"""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.fdn8 import program as FP
from dnfw.inserts import bus as B
from dnfw.inserts import busref as R
from dnfw.inserts import design as D
from dnfw.waverider import dsp
from dnfw.xdly import program as XP

KEEP = [f"R{k}" for k in range(16)] + [f"I{i}" for i in B.SAVE_I]


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def rec(typ, inst, mix, *k):
    return [typ | inst << D.TYPE_BITS, mix] + list(k) + [0] * (6 - len(k))


def rows_at(b: int) -> bytes:
    rows = {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127),
            (1, 1): rec(D.XDLY, 1, 127, 20, 30, 100, 40, 90),
            (2, 0): rec(D.FDN8, 1, 127, 0, 120, 60, 127, 30, 100),
            (2, 1): rec(D.XDLY, 0, 90, 5, 8, 127, 100, 60),
            (4, 0): rec(D.FUZZ, 0, 127, 127, 127, 127, 127, 127),
            (5, 1): rec(D.FDN8, 9, 127, 64, 64, 64, 64, 64, 64)}
    if b >= 45:
        rows[(0, 0)] = rec(D.FDN8, 0, 64, 10, 126, 90, 0, 0, 127)
    if b >= 50:
        del rows[(2, 1)]
        rows[(6, 0)] = rec(D.XDLY, 0, 127, 40, 40, 60, 0, 127)
    out = bytearray(8 * D.RECORDS)
    for (t, j), v in rows.items():
        out[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
    return bytes(out)


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2, fx = M5.m2, M5.fx
    checks, numbers = {}, {}
    rnd = random.Random(7)

    def regs(r):
        out = {}
        for n in KEEP:
            v = r.state.uregs.get(fx.UREG_CODES[n])
            out[n] = getattr(v, "value", None)
        return out

    def blocks_of(st):
        lo = [[m2.word(st, D.BUS_BLOCKS + 0x100 * t + 4 * j) or 0 for j in range(32)] for t in range(16)]
        ro = [[m2.word(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j) or 0 for j in range(32)] for t in range(16)]
        return lo, ro

    def send_words(st):
        return ([m2.word(st, FP.STATE + 4 * k) for k in range(FP.DYN_WORDS)]
                + [m2.word(st, FP.ACT + 4 * k) for k in range(FP.NV)]
                + [m2.word(st, XP.STATE + 4 * k) for k in range(XP.DYN_WORDS)])

    def frames(b):
        return M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                             others={1: 5, 2: 5}, trigger_others=True).to_bytes()

    def blocks(par_of, n):
        caps, cur = [], {}

        def at_bus(r):
            st = r.state
            b = len(caps)
            loud = 0.0 if b >= n - 8 else 2.0
            for t in range(16):
                for j in range(32):
                    x = rnd.uniform(-loud, loud)
                    m2.poke(st, D.BUS_BLOCKS + 0x100 * t + 4 * j, fb(np.float32(x)))
                    m2.poke(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j, fb(np.float32(x * 0.7)))
            for k, v in enumerate(par_of(b)):
                m2.poke(st, D.TABLE + 4 * k, v)
            cur.clear()
            cur["par"] = par_of(b)
            cur["in"] = blocks_of(st)
            cur["regs_in"] = regs(r)
            cur["send_in"] = send_words(st)

        def at_out(r):
            if "in" in cur and "out" not in cur:
                cur["out"] = blocks_of(r.state)
                cur["regs_out"] = regs(r)
                cur["send_out"] = send_words(r.state)
                caps.append(dict(cur))

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        for b in range(n):
            out = M5.run_blocks(state, lambda _b, b=b: frames(b), 1,
                                extra_hooks={dsp.INSBUS_SW: at_bus, B.OUT_SW: at_out})
            if not out.get("ok"):
                return caps, {"halt": str(out.get("halt")), "block": b}
            state = out["state"]
        return caps, {"blocks": len(caps)}

    # 1. all OFF
    caps, info = blocks(lambda b: bytes(8 * D.RECORDS), 12)
    checks["every bus insert OFF: every track's block at the output stage's entry is the block at the "
           "pass's entry (12 blocks)"] = bool(caps) and all(c["out"] == c["in"] for c in caps)
    checks["every bus insert OFF: R0..R15, I0..I4, I12 at the output stage's entry as the engine passed "
           "them"] = bool(caps) and all(c["regs_out"] == c["regs_in"] and None not in c["regs_in"].values()
                                        for c in caps)
    numbers["all OFF"] = info

    # 2. FDN8 and XDLY, two slots, instances moving
    caps, info = blocks(rows_at, 70)
    ref = R.BusRef()
    exact, first_bad, bare_same, regs_back, send_same, changed = bool(caps), None, True, True, True, 0
    for b, c in enumerate(caps):
        lin = [[bf(w) for w in c["in"][0][t]] for t in range(16)]
        rin = [[bf(w) for w in c["in"][1][t]] for t in range(16)]
        ref.block(c["par"], lin, rin)
        want = ([[fb(x) for x in row] for row in lin], [[fb(x) for x in row] for row in rin])
        if c["out"][0] != want[0] or c["out"][1] != want[1]:
            exact = False
            first_bad = first_bad if first_bad is not None else b
        for t in (3, 4, 5, 7, 15):
            bare_same &= c["out"][0][t] == c["in"][0][t] and c["out"][1][t] == c["in"][1][t]
        regs_back &= c["regs_out"] == c["regs_in"]
        send_same &= c["send_out"] == c["send_in"]
        changed += sum(1 for t in (0, 1, 2) for j in range(32) if c["out"][0][t][j] != c["in"][0][t][j])
    checks["FDN8, XDLY: every track's block after the pass as dnfw.inserts.busref's (70 blocks; two slots, "
           "FDN8 then XDLY on one track, a FULL slot, an XDLY instance moved to another track)"] = exact
    checks["FDN8, XDLY: the tracks with no bus insert (or a FULL slot) untouched"] = bare_same
    checks["FDN8, XDLY: every register the engine passed back at the output stage's entry"] = regs_back
    checks["FDN8, XDLY: the send FX's own words (FDN8's, XDLY's) as they were"] = send_same
    checks["FDN8, XDLY: they change the sound (not a pass-through)"] = changed > 1000
    numbers["FDN8, XDLY: first mismatch (block)"] = first_bad
    numbers["FDN8, XDLY: run info"] = info

    # 3. the pass alone
    base = M5.init_on(snap, m2mach, m5img, warm=True)
    out = M5.run_blocks(base, lambda _b: frames(1), 2)
    cost = {}
    for name, rows, calls in (("all OFF", {}, 1),
                              ("FDN8 x1, clearing", {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)}, 1),
                              ("FDN8 x1, steady", {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)}, 34),
                              ("XDLY x1", {(0, 0): rec(D.XDLY, 0, 127, 60, 70, 60, 0, 98)}, 3),
                              ("FDN8 x8 + XDLY x4, steady",
                               {**{(t, 0): rec(D.FDN8, t, 64, 10, 90, 30, 64, 0, 127) for t in range(8)},
                                **{(8 + t, 1): rec(D.XDLY, t, 127, 60, 70, 60, 0, 98) for t in range(4)}}, 34)):
        par = bytearray(8 * D.RECORDS)
        for (t, j), v in rows.items():
            par[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
        r, res = None, None
        for k_call in range(calls):
            r = (out["state"] if r is None else r).fresh_call(dsp.INSBUS_SW, regs={})
            for k, v in enumerate(par):
                m2.poke(r.state, D.TABLE + 4 * k, v)
            for t in range(16):
                for j in range(64):
                    m2.poke(r.state, D.BUS_BLOCKS + 0x100 * t + 4 * j, fb(np.float32(0.1 * ((j % 7) - 3))))
            how = fx.run(r, 20_000_000, fx.Fixups(), stop_at=[B.OUT_SW])
            res = (how[0], how[2])
            if how[0] != "stop":
                break
        cost[name] = res
    numbers["the pass alone: instructions a block, the last call (stop, count)"] = cost
    checks["the pass alone runs to the output stage's entry in every case"] = all(v[0] == "stop" for v in cost.values())
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
