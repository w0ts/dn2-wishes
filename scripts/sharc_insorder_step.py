"""The SHARC runner's insorder step (2026-11-11, the User: "i have the feeling insert 2 is BEFORE insert 1",
then "DSP: always run in slot order"): track 1's two insert slots, every kind of pair, in real blocks of
the build. The passes run by stage (pre at the voices, post at the FX sends, bus after the routing), so a
slot 1 of CHOR, WIDE, FDN8 or XDLY with a slot 2 of a voice insert ran slot 2 first; since then slot 2
moves to the bus pass, after slot 1 (dnfw.inserts.design.MOVERS).

Per pair, 8 blocks (the voices put at the routing's entry as sharc_mainmix_step does, FX returns zeroed):
1. the order the DSP enters each point of a block: the pre pass, its one insert (design.INS_ONE_SW; at the
   pre pass, or at the bus pass for a moved slot 2), its exit, the post pass, the routing, the bus pass,
   the FDN8 / XDLY engines, the master chain. Slot 1's insert is entered before slot 2's (a pre type by
   its one insert, a bus type by its engine after the bus pass's entry, a post type by the post pass; two
   voice inserts enter the same code, so their order is held by point 2: the reference runs slot 1 first,
   and its reverse order differs, measured 2026-11-11);
2. every voice buffer after the pre pass is dnfw.inserts.ref's, and every track block after the bus pass is
   dnfw.inserts.busref's, bit for bit (a moved slot 2 left out of the first, run in the second);
3. the moved pairs' track block differs from its input after the bus pass (the moved insert did something).
"""

from __future__ import annotations

import struct

import numpy as np

from dnfw.inserts import bus as B
from dnfw.inserts import busref as BR
from dnfw.inserts import design as D
from dnfw.inserts import ref as R
from dnfw.waverider import dsp

ROUTING_SW, MASTER_SW = 0x1C1F1E, 0x1C215C
VOICES = 0x257EE8
FX_RET = (0x25B868, 0x25BE68)
BLOCKS = 8


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def rec(typ, mix, *k):
    return bytes([typ, mix, *k, *([0] * (6 - len(k)))])


DIST = rec(D.DIST, 127, 127, 127, 127, 127, 127)
SUB = rec(D.SUB, 127, 100, 85, 59, 0, 127)
HARM = rec(D.HARM, 127, 50, 70, 64, 80, 100)
TAPE = rec(D.TAPE, 127, 80, 100, 90, 100, 60, 40)
FDN8 = rec(D.FDN8, 64, 10, 90, 30, 64, 0, 127)                   # MIX 64: a fresh FDN8 is silent at first
XDLY = rec(D.XDLY, 127, 20, 30, 100, 40, 90)
CHOR = rec(D.CHOR, 127, 64, 64, 64, 64, 64, 0)
WIDE = rec(D.WIDE, 127, 64, 64, 64, 64, 64, 64)
CASES = {"DIST|SUB": (DIST, SUB), "SUB|DIST": (SUB, DIST), "DIST|HARM": (DIST, HARM),
         "XDLY|DIST": (XDLY, DIST), "DIST|XDLY": (DIST, XDLY), "FDN8|TAPE": (FDN8, TAPE),
         "CHOR|DIST": (CHOR, DIST), "WIDE|SUB": (WIDE, SUB), "FDN8|CHOR": (FDN8, CHOR),
         "XDLY|FDN8": (XDLY, FDN8), "FDN8|XDLY": (FDN8, XDLY)}


def stage(v: bytes) -> str:
    t = v[0] & 0xF
    return "pre" if t in D.BUILT else "post" if t in D.POST else "bus"


def when(seq: list[str], v: bytes, moved: bool, nth: int = 0) -> int | None:
    """the index in SEQ where record V's insert is entered (a pre type in the pre pass: the NTH one insert,
    the voice slots' inserts in walk order, slot 1 then slot 2 of each)"""
    s, t = stage(v), v[0] & 0xF
    if s == "pre":
        if moved:
            at = seq.index("bus") if "bus" in seq else len(seq)
            return next((k for k in range(at, len(seq)) if seq[k] == "one"), None)
        ones = [k for k, n in enumerate(seq[:seq.index("pre-exit")] if "pre-exit" in seq else seq) if n == "one"]
        return ones[nth] if len(ones) > nth else None
    if s == "post":
        return seq.index("post") if "post" in seq else None
    at = seq.index("bus") if "bus" in seq else len(seq)
    name = "FDN8-engine" if t == D.FDN8 else "XDLY-engine"
    return next((k for k in range(at, len(seq)) if seq[k] == name), None)


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers = {}, {}

    def frames(b):
        return M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                             others={1: 5, 2: 5}, trigger_others=True).to_bytes()

    def words(st, at, n=32):
        return [m2.word(st, at + 4 * j) or 0 for j in range(n)]

    def tracks(st):
        return [(words(st, D.BUS_BLOCKS + 0x100 * t), words(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R))
                for t in range(16)]

    def one_case(s1, s2):
        par1, par2 = bytearray(8 * D.TRACKS), bytearray(8 * D.TRACKS)
        par1[0:8], par2[0:8] = s1, s2
        recs = D.records(bytes(par1), bytes(par2))
        caps = []
        state = M5.init_on(snap, m2mach, m5img, warm=True)
        for b in range(BLOCKS):
            cur = {"seq": []}
            for k, w in enumerate(D.pack(recs, 1 + b)):
                m2.poke(state.state, D.GEN + 4 * k, w)

            def mark(name, extra=None, cur=cur):
                def h(r):
                    cur["seq"].append(name)
                    if extra:
                        extra(r)
                return h

            def at_routing(r, b=b):
                for a in range(FX_RET[0], FX_RET[1], 4):
                    m2.poke(r.state, a, 0)
                for s in range(16):              # voice slots 0 and 3 sound (as sharc_mainmix_step)
                    on = s in (0, 3)
                    for j in range(32):
                        x = 0.02 * (s + 1) * np.sin(0.3 * (32 * b + j)) if on else 0.0
                        m2.poke(r.state, VOICES + 0x100 * s + 4 * j, fb(x))
                        m2.poke(r.state, VOICES + 0x100 * s + 0x80 + 4 * j, fb(-0.5 * x))

            def at_ins(r, cur=cur):
                cur["ptr"] = [m2.word(r.state, D.BUFFERS + 4 * t) for t in range(16)]
                cur["in"] = [words(r.state, cur["ptr"][t]) for t in range(16)]
                cur["route"] = [((m2.word(r.state, D.ROUTE + 4 * (s // 2)) or 0) >> (16 * (s & 1))) & 0xFFFF
                                for s in range(16)]
                cur["tempo"] = m2.word(r.state, D.TEMPO) or 0
                cur["clk"] = m2.word(r.state, D.CLK) or 0

            def at_ping(r, cur=cur):
                if "out" not in cur and "ptr" in cur:
                    cur["out"] = [words(r.state, cur["ptr"][t]) for t in range(16)]

            def at_bus(r, cur=cur):
                cur["bin"] = tracks(r.state)

            def at_resume(r, cur=cur):
                if "bin" in cur and "bout" not in cur:
                    cur["bout"] = tracks(r.state)

            hooks = {ROUTING_SW: mark("routing", at_routing), dsp.INS_SW: mark("pre", at_ins),
                     D.INS_ONE_SW: mark("one"), dsp.PING_SW: mark("pre-exit", at_ping),
                     dsp.POST_SW: mark("post"), dsp.INSBUS_SW: mark("bus", at_bus),
                     B.RESUME_SW: mark("resume", at_resume), D.FDN8_SW: mark("FDN8-engine"),
                     D.XDLY_SW: mark("XDLY-engine"), MASTER_SW: mark("master")}
            out = M5.run_blocks(state, lambda _b, b=b: frames(b), 1, extra_hooks=hooks)
            if not out.get("ok"):
                return caps, recs, {"halt": str(out.get("halt")), "block": b}
            state = out["state"]
            caps.append(cur)
        return caps, recs, {"blocks": len(caps)}

    for name, (s1, s2) in CASES.items():
        caps, recs, info = one_case(s1, s2)
        mv = D.moved(recs, 0)
        ok_run = len(caps) == BLOCKS and all(k in c for c in caps for k in ("in", "out", "bin", "bout"))
        pre_ok = bus_ok = ok_run
        order_ok, changed = ok_run, 0
        pre_ref, bus_ref = R.Ref(), BR.BusRef()
        for c in caps if ok_run else []:
            bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
            pre_ref.block(recs, bufs, c["route"], tempo=c["tempo"], clk=c["clk"])
            pre_ok &= c["out"] == [[fb(x) for x in bufs[t]] for t in range(16)]
            left = [[bf(w) for w in c["bin"][t][0]] for t in range(16)]
            right = [[bf(w) for w in c["bin"][t][1]] for t in range(16)]
            bus_ref.block(recs, left, right, tempo=c["tempo"], clk=c["clk"])
            bus_ok &= [(lo, ro) for lo, ro in c["bout"]] == [([fb(x) for x in left[t]], [fb(x) for x in right[t]])
                                                             for t in range(16)]
            both = stage(s1) == stage(s2) == "pre"           # the first voice playing it: slot 1, then 2
            e1, e2 = when(c["seq"], s1, False), when(c["seq"], s2, mv, 1 if both else 0)
            order_ok &= e1 is not None and e2 is not None and e1 < e2
            changed += sum(1 for j in range(32) if c["bout"][0][0][j] != c["bin"][0][0][j])
        numbers[name] = {"run": info, "moved": mv, "sequence (last block)": caps[-1]["seq"] if caps else None,
                         "track 1 words changed by the bus pass": changed}
        if stage(s1) == "bus" and stage(s2) == "post":  # not moved (the User's choice: a voice insert in
            checks[f"{name}: still by stage, slot 2 (after the pan) before slot 1 (the bus)"] = ok_run and (
                not order_ok)                           # slot 2 only); held so a change shows
        else:
            checks[f"{name}: slot 1 entered before slot 2 in every block"
                   f"{' (slot 2 moved to the bus)' if mv else ''}"] = order_ok
        checks[f"{name}: every voice buffer after the pre pass as dnfw.inserts.ref's"] = pre_ok
        checks[f"{name}: every track block after the bus pass as dnfw.inserts.busref's"] = bus_ok
        if mv:
            checks[f"{name}: the moved insert changes track 1's block on the bus"] = changed > 32
        print(f"    {name}: moved {mv}, order {order_ok}, pre {pre_ok}, bus {bus_ok}, changed {changed}", flush=True)
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
