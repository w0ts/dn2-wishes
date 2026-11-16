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


def bus_rows(extra=None, bus=True) -> list[int]:
    rows = {(9, 0): rec(D.FDN8, 0, 127, 10, 90, 30, 64, 0, 127),
            (8, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 40, 90)} if bus else {}
    rows.update(extra or {})
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

    def scenario(name, n_voices, P, par=par, flags=flags, mach=None, extra_tail=0, n_blocks=None):
        """MACH: (type, frame words) of the voices' machine (else ANALOG2); EXTRA_TAIL: cycles added to the stock's
        busy stretch each block (idle_load's AFTER), a heavier stock as on the unit (the study, 2026-11-12)"""
        typ_, words_ = mach or (typ, words)
        nb = n_blocks or blocks_n
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

        hooks = {dsp.PERC_SW: at_perc, m3.DISPATCH: at_dispatch, dsp.INSBUS_SW: at_bus, B.RESUME_SW: at_out}
        hooks.update({x: clock for x in sites})

        def frame(b):
            f = M5.base_frame(sound, machines, t0=typ_, overrides=words_, trigger=False,
                              others={t: typ_ for t in range(1, n_voices)})
            for t in range(n_voices):
                for slot, w in words_.items():
                    f.param(t, slot, w)
                f.header(FR.NOTE, t, (48 + 3 * t) << 8)
                if b == 1:
                    f.trigger(t)
            return f.to_bytes()

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        after = 0
        rows = []
        for b in range(nb):
            b_now["b"] = b
            tap.clear()
            out = M5.run_blocks(state, lambda _b, b=b: frame(b), 1, extra_hooks=hooks)
            if not out.get("ok"):
                return {"ok": False, "halt": str(out.get("halt")), "block": b, "rows": rows}
            state = out["state"]
            end = int(out["instructions"] + S * (4 * counts["L2"] + 10 * counts["DDR"]))
            after += end - tap.get("mark", 0) + extra_tail
            m2.poke(state.state, G.AFTER, after & 0xFFFFFFFF)
            skipped = ((tap.get("skips_out", 0) or 0) - (tap.get("skips_in", 0) or 0)) & 0xFFFFFFFF
            rows.append({"b": b, "mark": tap.get("mark"), "bus_in": tap.get("bus_in"), "bus_out": tap.get("bus_out"),
                         "end": end, "tail": tap.get("tail"), "deadline": tap.get("deadline"),
                         "ins_skipped": skipped, "voice_skips": m2.word(state.state, G.SKIPS),
                         "limit": m2.word(state.state, G.LIMIT),
                         "room": [m2.word(state.state, G.INS_ROOM + 4 * k) for k in range(G.INS_ROOM_PASSES)],
                         "route": [(m2.word(state.state, D.ROUTE + 4 * (k // 2)) >> (16 * (k & 1))) & 0xFFFF
                                   for k in range(16)],
                         "tskip": [m2.word(state.state, G.INS_TSKIP + 4 * k) for k in range(G.INS_TSKIP_WORDS)]})
            for k in range(G.INS_ROOM_PASSES):          # read, then reset, as the idle packet does
                m2.poke(state.state, G.INS_ROOM + 4 * k, G.INS_ROOM_NONE)
            r = rows[-1]
            if os.environ.get("DNFW_INSDL_QUIET"):
                continue
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

    def study():
        """2026-11-12 (main: A09's insert skips on r11f; the User: "juno in any insert => bad"): per machine (ANALOG2,
        the JUNO engine) and per insert type on the voices' tracks (pre and post types, the JUNO chorus included), the
        blocks left out by type and the least room each pass had before its deadline, with the stock's tail as the
        runner measures it and raised by DNFW_INSDL_EXTRA (the unit's stock is heavier). No bus inserts."""
        out = {}
        juno = MMx.NAMES.index("JUNO")
        machs = {"ANALOG2": (typ, words), "JUNO": (MMx.TYPES[juno], M5.mnm_words(juno))}
        extras = [int(x) for x in os.environ.get("DNFW_INSDL_EXTRA", "0,140000").split(",")]
        n_v = int(os.environ.get("DNFW_INSDL_VOICES", "4"))
        kinds = [None] + [t for t in D.BUILT] + [t for t in D.POST]
        if os.environ.get("DNFW_INSDL_KINDS"):
            want = os.environ["DNFW_INSDL_KINDS"].split(",")
            kinds = [k for k in kinds if ("none" if k is None else D.NAMES[k]) in want]
        machs = {k: v for k, v in machs.items() if k in os.environ.get("DNFW_INSDL_MACHS", "ANALOG2,JUNO").split(",")}
        for ex in extras:
            for mname, mach in machs.items():
                for kind in kinds:
                    ins = {} if kind is None else {(t, 0): rec(kind, 0, 100, 64, 64, 64, 64, 64, 64) for t in range(n_v)}
                    p2 = bus_rows(ins, bus=False)
                    name = f"{mname}+{'none' if kind is None else D.NAMES[kind]}@{ex}"
                    res = scenario(name, n_v, 666_667, par=p2, flags=D.flags(p2), mach=mach, extra_tail=ex,
                                   n_blocks=int(os.environ.get("DNFW_INSDL_STUDY_BLOCKS", "12")))
                    if not res["ok"]:
                        out[name] = {"ok": False, "halt": res.get("halt")}
                        continue
                    rows = [r for r in res["rows"] if r["b"] >= 4]
                    t0, t1 = rows[0]["tskip"], rows[-1]["tskip"]
                    by = {(D.NAMES[k] if k < len(D.NAMES) else k): (t1[k] - t0[k]) & 0xFFFFFFFF
                          for k in range(G.INS_TSKIP_WORDS) if t1[k] != t0[k]}
                    def s32(x):
                        return x - (1 << 32) if x & 0x80000000 else x
                    room = [min((s32(r["room"][k]) for r in rows if r["room"][k] != G.INS_ROOM_NONE), default=None)
                            for k in range(G.INS_ROOM_PASSES)]
                    out[name] = {"blocks": len(rows), "skipped": sum(r["ins_skipped"] for r in rows[1:]),
                                 "by_type": by, "room_min": dict(zip(("a2f", "pre", "post", "bus"), room)),
                                 "voice_skips": rows[-1]["voice_skips"], "end_over_P": round(max(r["end"] for r in rows) / 666_667, 3),
                                 "tail": rows[-1]["tail"], "deadline": rows[-1]["deadline"],
                                 "route": rows[-1]["route"]}
                    print(f"    study {name}: {out[name]}", flush=True)
        return out

    if os.environ.get("DNFW_INSDL_STUDY"):
        try:
            return {"ok": True, "checks": {}, "numbers": {"study": study()}}
        finally:
            undo_counts()

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
                # 2026-11-12 (round 13): every block left out is counted under its type (guard.INS_TSKIP)
                t0, t1 = res["rows"][0]["tskip"], res["rows"][-1]["tskip"]
                by_type = {D.NAMES[k] if k < len(D.NAMES) else k: (t1[k] - t0[k]) & 0xFFFFFFFF
                           for k in range(G.INS_TSKIP_WORDS) if t1[k] != t0[k]}
                total = sum(r["ins_skipped"] for r in res["rows"][1:])
                numbers["TIGHT"]["skips_by_type"] = by_type
                # (opt-inserts' gate: the block refused under its type, then held out under 14, faded under 15)
                checks["TIGHT: the per-type counts add up to INS_SKIPS, under FDN8, XDLY and the gate's 14, 15 only"] = (
                    sum(by_type.values()) == total and set(by_type) <= {"FDN8", "XDLY", 14, 15})
            else:
                checks["TIGHT (control): every block returns"] = False
                numbers["TIGHT"] = res
    finally:
        undo_counts()
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
