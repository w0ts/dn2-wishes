"""The SHARC runner's mainmix step (2026-11-11, the User: "xdelay and fdn8 still dont work as insert"): does a
bus insert (FDN8, XDLY: dnfw.inserts.bus) reach the main mix, not only the track's Overbridge stream?

The routing (sw 0x1c1f1e) sums each voice slot's stereo block (0x257ee8 + 0x100 s) into its track's block
(design.BUS_BLOCKS + 0x100 t, the loop ending at sw 0x1c1fec), then sums the tracks' blocks into the main bus
(0x25bb68, L 32 floats, R at + 0x80, measured here; the loop at sw 0x1c2038), adds the send FX's returns and enters the
master chain (CJUMP 0xb8541d at sw 0x1c215c). The output stage (0x1c244d) sends each track's block to
Overbridge. So a bus insert is on the main mix only if it runs between the two loops: until 2026-11-11 it
ran at the output stage's call, and this step measured the main bus equal to the blocks BEFORE the pass, bit
for bit (FDN8 and XDLY at MIX 127, four sounding blocks).

This step puts its own sound in the voice blocks at the routing's entry (the emulator writes the voice chain's
blocks elsewhere: sharc_inspost_step), FDN8 or XDLY at MIX 127 on track 0 (every voice routes to slot 0 in the
runner's frames), and compares the main bus at the master chain's call with the sum of the tracks' blocks
before the bus pass and after it.
"""

from __future__ import annotations

import struct

import numpy as np

from dnfw.inserts import bus as B
from dnfw.inserts import design as D
from dnfw.waverider import dsp

ROUTING_SW = 0x1C1F1E
MASTER_CALL_SW = 0x1C215C                       # CJUMP 0xb8541d (DB): the main bus is summed by here
VOICES = 0x257EE8
MAIN_BUS = 0x25BB68                             # measured: the tracks' sum (routing masks 0)
FX_RET = (0x25B868, 0x25BE68)                   # the send FX's returns (their path is not modelled: zeroed)
BURST, BLOCKS = 32, 80                          # the burst's first block, the blocks run


def bf(w) -> float:
    return float(np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]))


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(np.float32(x))))[0]


def rec(typ, mix, *k):
    return [typ, mix] + list(k) + [0] * (6 - len(k))


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers = {}, {}
    exit_sw = B.RESUME_SW                       # where the bus pass hands back

    def frames(b):
        return M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                             others={1: 5, 2: 5}, trigger_others=True).to_bytes()

    def floats(st, at, n=32):
        return [bf(m2.word(st, at + 4 * j)) for j in range(n)]

    def tracks(st):
        return [(floats(st, D.BUS_BLOCKS + 0x100 * t), floats(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R))
                for t in range(16)]

    def blocks(row, n):
        caps, cur = [], {}

        def at_routing(r):
            cur.clear()
            b = len(caps)
            for a in range(FX_RET[0], FX_RET[1], 4):
                m2.poke(r.state, a, 0)
            for s in range(16):                 # slots 0 and 3 sound: a burst, blocks 32..35 (a fresh FDN8
                on = s in (0, 3) and BURST <= b < BURST + 4     # instance clears its rings first)
                for j in range(32):
                    x = 0.02 * (s + 1) * np.sin(0.3 * (32 * b + j)) if on else 0.0
                    m2.poke(r.state, VOICES + 0x100 * s + 4 * j, fb(x))
                    m2.poke(r.state, VOICES + 0x100 * s + 0x80 + 4 * j, fb(-0.5 * x))

        def at_pass(r):
            par = bytearray(8 * D.RECORDS)
            if row:
                par[0:8] = bytes(row)
            for k, v in enumerate(par):
                m2.poke(r.state, D.TABLE + 4 * k, v)
            for k, v in enumerate(D.flags(bytes(par))):
                m2.poke(r.state, D.FLAGS + 4 * k, v)
            cur["in"] = tracks(r.state)

        def at_exit(r):
            if "in" in cur and "out" not in cur:
                cur["out"] = tracks(r.state)

        def at_master(r):
            if "main" not in cur:
                cur["main"] = (floats(r.state, MAIN_BUS), floats(r.state, MAIN_BUS + 0x80))

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        hooks = {ROUTING_SW: at_routing, dsp.INSBUS_SW: at_pass, exit_sw: at_exit, MASTER_CALL_SW: at_master}
        for b in range(n):
            out = M5.run_blocks(state, lambda _b, b=b: frames(b), 1, extra_hooks=hooks)
            if not out.get("ok"):
                return caps, {"halt": str(out.get("halt")), "block": b}
            state = out["state"]
            caps.append(dict(cur))              # whichever came first, the master call or the bus pass
        return caps, {"blocks": len(caps)}

    def compare(caps):
        """per block: |main - sum(tracks after the pass)| and |main - sum(tracks before it)|, L and R"""
        rows = []
        for c in caps:
            if "main" not in c or "in" not in c or "out" not in c:
                rows.append({"missing": sorted(k for k in ("main", "in", "out") if k not in c)})
                continue
            d_out = d_in = wet = 0.0
            for side in (0, 1):
                for j in range(32):
                    s_out = sum(c["out"][t][side][j] for t in range(16))
                    s_in = sum(c["in"][t][side][j] for t in range(16))
                    m = c["main"][side][j]
                    d_out = max(d_out, abs(m - s_out))
                    d_in = max(d_in, abs(m - s_in))
                    wet = max(wet, abs(s_out - s_in))
            rows.append({"main vs after": d_out, "main vs before": d_in, "insert changed": wet,
                         "max in": max(abs(x) for t in range(16) for sd in (0, 1) for x in c["in"][t][sd]),
                         "max after": max(abs(x) for t in range(16) for sd in (0, 1) for x in c["out"][t][sd]),
                         "max main": max(abs(x) for sd in (0, 1) for x in c["main"][sd])})
        return rows

    for name, row in (("FDN8 MIX 127", rec(D.FDN8, 127, 10, 90, 30, 64, 0, 127)),
                      ("FDN8 MIX 64", rec(D.FDN8, 64, 10, 90, 30, 64, 0, 127)),
                      ("XDLY MIX 127", rec(D.XDLY, 127, 20, 30, 100, 40, 90))):
        caps, info = blocks(row, BLOCKS)
        rows = compare(caps)
        fin = [r for r in rows if "missing" not in r and r["main vs after"] == r["main vs after"]]
        tail = [r for r in fin if r["max in"] == 0.0 and r["max after"] > 1e-3]
        numbers[name] = {"run": info, "finite blocks": len(fin), "tail blocks (input silent, wet on)": len(tail),
                         "worst main vs after": max((r["main vs after"] for r in fin), default=None),
                         "loudest tail in main": max((r["max main"] for r in tail), default=None),
                         "first blocks": rows[:3]}
        sounding = [r for r in fin if r["max in"] > 0.0]
        checks[f"{name} on track 0: the main bus at the master chain is the sum of the tracks' blocks AFTER the "
               f"bus pass in every block, and the insert changed every sounding block"] = (
            len(fin) == BLOCKS and len(sounding) >= 4
            and all(r["main vs after"] <= 1e-4 * max(1.0, r["max main"]) for r in fin)
            and all(r["insert changed"] > 1e-3 for r in sounding))
        if name.startswith("XDLY"):              # (FDN8's wet: none within the run, a fresh instance clearing first)
            checks[f"{name}: its tail (the input silent, the wet on) is in the main bus"] = (
                len(tail) >= 3 and all(r["max main"] > 1e-3 for r in tail))
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
