"""The SHARC runner's insdl step (2026-11-11, the User's "XDLY/FDN8 inserts do nothing"; the unit's telemetry:
the bus inserts passed through for time, thousands of blocks, while the frame peaked at ~60-90 % and no voice
was skipped). The insert guard (dnfw.perc.guard.ins_admit) on a moving clock, as on the unit.

The runner's EMUCLK stands still, so elsewhere INS_DEADLINE is never tested: idle_load's AFTER never moves,
TAIL stays 0 and the deadline is P - P/8. Here every read of EMUCLK in our code (perc, smp, inserts, inspost,
insbus, a2f) gets the block's start plus the memory-cost clock (step 3k's: instructions + S x (4 L2 + 10 DDR)),
MARK0 the block's start, MARK our entry, a frame P apart, and after each block idle_load's AFTER moves by the
block's busy stretch from MARK (what the idle task would add on the unit). So tail_limit measures TAIL from
the stock's real work, and the guard decides each insert as on the unit.

Scenarios: FDN8 on track 9's bus and XDLY on track 8's (loud noise in every track's bus block, so FDN8's quiet
gate does not idle), N ANALOG2 voices held from block 1; and a control on a frame too short for the inserts.
Per block: where the bus pass starts and ends, the block's end, TAIL, INS_DEADLINE, INS_SKIPS, the voices'
SKIPS. A bus insert skipped while the frame had room for it is the guard being too eager.
"""

from __future__ import annotations

import os
import random
import struct

from dnfw.inserts import bus as B
from dnfw.inserts import design as D
from dnfw.perc import guard as G
from dnfw.waverider import dsp

SITES = ("perc", "smp", "inserts", "inspost", "insbus", "a2f")


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def rec(typ, inst, mix, *k):
    return [typ | inst << D.TYPE_BITS, mix] + list(k) + [0] * (6 - len(k))


def bus_rows() -> list[int]:
    rows = {(9, 0): rec(D.FDN8, 0, 127, 10, 90, 30, 64, 0, 127),
            (8, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 40, 90)}
    out = bytearray(8 * D.RECORDS)
    for (t, j), v in rows.items():
        out[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
    return list(out)


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    from dnfw.mnm import machines as MMx
    m2, fx, FR, m3 = M5.m2, M5.fx, M5.FR, M5.m3
    S = float(os.environ.get("DNFW_MEM_SCALE", "0.9"))
    blocks_n = int(os.environ.get("DNFW_INSDL_BLOCKS", "24"))
    sites = set()
    for name in SITES:
        sites |= set(M5._after_emuclk(name))
    counts, undo_counts = M5._count_memory()
    k = MMx.NAMES.index("ANALOG2")
    typ = MMx.TYPES[k]
    words = M5.mnm_words(k)
    par = bus_rows()
    flags = D.flags(par)
    rnd = random.Random(11)

    def scenario(name, n_voices, P):
        b_now = {"b": 0}
        tap = {}

        def cycles(r):
            return int(getattr(r, "steps_n", 0) + S * (4 * counts["L2"] + 10 * counts["DDR"]))

        def clock(r):
            r.state.uregs[fx.UREG_CODES["R8"]] = fx.Const(((b_now["b"] + 1) * P + cycles(r)) & 0xFFFFFFFF)

        def at_dispatch(r):
            for x in ("L1", "L2", "DDR"):
                counts[x] = 0
            counts["on"] = True

        def at_perc(r):
            base = (b_now["b"] + 1) * P
            tap["mark"] = cycles(r)
            m2.poke(r.state, G.MARK0, base & 0xFFFFFFFF)
            m2.poke(r.state, G.MARK, (base + tap["mark"]) & 0xFFFFFFFF)

        def at_bus(r):
            tap["bus_in"] = cycles(r)
            tap["deadline"] = m2.word(r.state, G.INS_DEADLINE)
            tap["tail"] = m2.word(r.state, G.TAIL)
            tap["skips_in"] = m2.word(r.state, G.INS_SKIPS)
            st = r.state
            for t in range(16):
                for j in range(32):
                    x = rnd.uniform(-1.0, 1.0)
                    m2.poke(st, D.BUS_BLOCKS + 0x100 * t + 4 * j, fb(x))
                    m2.poke(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j, fb(0.7 * x))
            for i, v in enumerate(par):
                m2.poke(st, D.TABLE + 4 * i, v)
            for i, v in enumerate(flags):
                m2.poke(st, D.FLAGS + 4 * i, v)

        def at_out(r):
            tap["bus_out"] = cycles(r)
            tap["skips_out"] = m2.word(r.state, G.INS_SKIPS)

        hooks = {dsp.PERC_SW: at_perc, m3.DISPATCH: at_dispatch, dsp.INSBUS_SW: at_bus, B.OUT_SW: at_out}
        hooks.update({x: clock for x in sites})

        def frame(b):
            f = M5.base_frame(sound, machines, t0=typ, overrides=words, trigger=False,
                              others={t: typ for t in range(1, n_voices)})
            for t in range(n_voices):
                for slot, w in words.items():
                    f.param(t, slot, w)
                f.header(FR.NOTE, t, (48 + 3 * t) << 8)
                if b == 1:
                    f.trigger(t)
            return f.to_bytes()

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        after = 0
        rows = []
        for b in range(blocks_n):
            b_now["b"] = b
            tap.clear()
            out = M5.run_blocks(state, lambda _b, b=b: frame(b), 1, extra_hooks=hooks)
            if not out.get("ok"):
                return {"ok": False, "halt": str(out.get("halt")), "block": b, "rows": rows}
            state = out["state"]
            end = int(out["instructions"] + S * (4 * counts["L2"] + 10 * counts["DDR"]))
            after += end - tap.get("mark", 0)
            m2.poke(state.state, G.AFTER, after & 0xFFFFFFFF)
            skipped = ((tap.get("skips_out", 0) or 0) - (tap.get("skips_in", 0) or 0)) & 0xFFFFFFFF
            rows.append({"b": b, "mark": tap.get("mark"), "bus_in": tap.get("bus_in"), "bus_out": tap.get("bus_out"),
                         "end": end, "tail": tap.get("tail"), "deadline": tap.get("deadline"),
                         "ins_skipped": skipped, "voice_skips": m2.word(state.state, G.SKIPS),
                         "limit": m2.word(state.state, G.LIMIT)})
            r = rows[-1]
            print(f"      {name} b{b:02d}: mark {r['mark']} bus {r['bus_in']}..{r['bus_out']} end {end} "
                  f"tail {r['tail']} deadline {r['deadline']} ins_skipped {skipped} voice_skips {r['voice_skips']} "
                  f"limit {r['limit']}", flush=True)
        return {"ok": True, "P": P, "rows": rows}

    def summary(res, P):
        rows = [r for r in res["rows"] if r["b"] >= 4]
        room = P - P // 8
        # a skip was too eager if the block would still have ended in time with the skipped inserts at
        # their bound (the heavier, FDN8's, for each)
        eager = sum(1 for r in rows if r["ins_skipped"] and r["end"] + r["ins_skipped"] * D.COST[D.FDN8] <= room)
        return {"P": P, "blocks": len(rows), "ins_skipped": sum(r["ins_skipped"] for r in rows),
                "skipped_with_room": eager, "end_max": max(r["end"] for r in rows),
                "end_over_P_max": round(max(r["end"] for r in rows) / P, 3),
                "bus_in_max": max(r["bus_in"] or 0 for r in rows),
                "after_bus_max": max(r["end"] - (r["bus_out"] or r["end"]) for r in rows), "tail_last": rows[-1]["tail"],
                "deadline_last": rows[-1]["deadline"], "voice_skips": rows[-1]["voice_skips"]}

    checks, numbers = {}, {}
    try:
        P = 666_667
        for name, n in (("A1", 1), ("A4", 4)):
            print(f"    insdl {name}: {n} ANALOG2 voice(s), FDN8 T9 + XDLY T8 on the bus, P {P}", flush=True)
            res = scenario(name, n, P)
            if not res["ok"]:
                checks[f"{name}: every block returns"] = False
                numbers[name] = res
                continue
            numbers[name] = sm = summary(res, P)
            print(f"    {name}: {sm}", flush=True)
            checks[f"{name}: every block returns, no voice skipped"] = sm["voice_skips"] in (0, None)
            checks[f"{name}: no bus insert passed through while the frame had room (end <= P - P/8)"] = (
                sm["skipped_with_room"] == 0)
            checks[f"{name}: the frame ends by P - P/8 with the inserts run"] = sm["end_max"] <= P - P // 8
        # the control: a frame too short for the bus inserts: P - P/8 = where the bus pass starts + half
        # FDN8's bound + what follows the pass (the output stage), so neither fits at its bound; the guard
        # must still leave them out, and every block return
        a4 = numbers.get("A4", {})
        if "end_max" in a4:
            Pt = int((a4["bus_in_max"] + D.COST[D.FDN8] // 2 + a4["after_bus_max"]) * 8 / 7)
            print(f"    insdl TIGHT: 4 voices, P {Pt}", flush=True)
            res = scenario("TIGHT", 4, Pt)
            if res["ok"]:
                numbers["TIGHT"] = sm = summary(res, Pt)
                print(f"    TIGHT: {sm}", flush=True)
                checks["TIGHT (control): the guard leaves bus inserts out when the frame is too short"] = (
                    sm["ins_skipped"] > 0)
            else:
                checks["TIGHT (control): every block returns"] = False
                numbers["TIGHT"] = res
    finally:
        undo_counts()
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
