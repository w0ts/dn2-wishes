"""The SHARC runner's inserts step (docs/inserts.md): real blocks of the build (sw 0x1c2712 and the
chain), track 0 a PERC voice retriggered, tracks 1 and 2 PERC voices too; the 16 track buffers
captured at the inserts' entry (dnfw.waverider.dsp.INS_SW) and at PING's (where the pass hands on).

1. Every insert OFF (the pool's value bytes zero, as at power-on): every buffer at PING's entry is
   the buffer at the inserts' entry, bit for bit (the pass changes nothing); the pass's cost.
2. FUZZ on track 0 (and on track 1 with other knobs, track 2 OFF, track 5 a type not built): each
   block, every buffer after the pass is dnfw.inserts.ref's run on the buffers before it, bit for
   bit (the reference keeps its own state across blocks); the pass's cost per block with one and
   with two tracks on (instructions between the two entries).
"""

from __future__ import annotations

import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import ref as R
from dnfw.waverider import dsp


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers = {}, {}

    def route_of(b):
        """the track each voice slot plays at block b: tracks 1, 2, 5, 16 (0, 1, 4, 15) and track 2
        again on a second voice, moving over the five sounding slots every 6 blocks"""
        k = b // 6
        rt = [0xFFFF] * 16
        for j, tr in enumerate((0, 1, 4, 15, 1)):
            rt[(k + j) % 5] = tr
        return rt

    def frames(b, routed=False):
        f = M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                          others={1: 5, 2: 5, 3: 5, 4: 5}, trigger_others=True)
        if routed:
            for s_, tr in enumerate(route_of(b)):
                f.put(0xA5A + 2 * s_, tr)
        return f.to_bytes()

    def blocks(par_of, n, routed=False):
        caps = []
        cur = {}

        def put_par(r):                          # (2026-11-10: packed, a new change word each block, as the
            par = par_of(len(caps))              # link sends them: the pass's own unpack runs every block)
            for k, w in enumerate(D.pack(D.records(par), 1 + len(caps))):
                m2.poke(r.state, D.GEN + 4 * k, w)

        def at_ins(r):
            cur.clear()
            cur["par"] = par_of(len(caps))
            cur["ptr"] = [m2.word(r.state, D.BUFFERS + 4 * t) for t in range(16)]
            cur["in"] = [[m2.word(r.state, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
            cur["route"] = [((m2.word(r.state, D.ROUTE + 4 * (s_ // 2)) or 0) >> (16 * (s_ & 1))) & 0xFFFF
                            for s_ in range(16)]

        def at_ping(r):
            cur["out"] = [[m2.word(r.state, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
            caps.append(dict(cur))

        init = M5.init_on(snap, m2mach, m5img, warm=True)
        # the values go in before each block's run (as the link would have put them)
        state = init
        res = []
        for b in range(n):
            put_par(state)
            out = M5.run_blocks(state, lambda _b, b=b: frames(b, routed), 1,
                                extra_hooks={dsp.INS_SW: at_ins, dsp.PING_SW: at_ping})
            if not out.get("ok"):
                return caps, {"halt": out.get("halt"), "block": b}
            res.append(out["instructions"])
            state = out["state"]
        return caps, {"instructions": res}

    # 1. all OFF
    caps, info = blocks(lambda b: bytes(128), 30)
    same = bool(caps) and all(c.get("out") == c["in"] for c in caps)
    heard = sum(1 for c in caps for t in range(16) for w in c["in"][t] if w & 0x7FFFFFFF)
    checks["every insert OFF: every track buffer after the pass is the buffer before it (30 blocks)"] = same
    checks["the test's tracks sound (not a run of zeros)"] = heard > 500
    numbers["all OFF: run info"] = info if "halt" in info else {"blocks": len(caps)}

    # 2. FUZZ on tracks 0 and 1
    def par_of(b):
        rows = bytearray(128)
        rows[0:8] = bytes([D.FUZZ, 127, 100, 60, 30, 40, 0, 110] if b < 20 else
                          [D.FUZZ, 90, 60, 127, 127, 127, 50, 127])
        rows[8:16] = bytes([D.FUZZ, 64, 127, 20, 0, 0, 20, 100]) if b >= 8 else bytes(8)
        rows[40:48] = bytes([D.WIDE, 127, 127, 127, 127, 127, 127, 127])
        rows[16:24] = bytes([D.TAPE, 127, 90, 110, 100, 110, 80, 60])          # TAPE on track 2
        rows[24:32] = bytes([D.FOLD, 127, 100, 70, 64, 90, 110, 0])            # FOLD on track 3 (silent)
        rows[32:40] = bytes([D.HARM, 127, 127, 50, 64, 100, 110, 0])           # HARM on track 4 (silent)
        if b >= 30:
            rows[16:24] = bytes([D.TAPE, 100, 127, 127, 0, 127, 127, 0])
        return bytes(rows)
    caps, info = blocks(par_of, 40)
    ref = R.Ref()
    exact, first_bad, others_same, changed = bool(caps), None, True, 0
    for b, c in enumerate(caps):
        bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
        ref.block(D.records(c["par"]), bufs, c["route"])
        want = [[fb(x) for x in bufs[t]] for t in range(16)]
        if c.get("out") != want:
            exact = False
            first_bad = first_bad or b
        bare = [s_ for s_ in range(16) if c["route"][s_] > 15
                or c["par"][8 * c["route"][s_]] not in D.BUILT]            # its track has no insert running
        others_same &= all(c["out"][s_] == c["in"][s_] for s_ in bare)
        changed += sum(1 for t in (0, 1, 2, 3, 4) for j in range(32) if c["out"][t][j] != c["in"][t][j])
    checks["FUZZ, TAPE, FOLD, HARM: every buffer after the pass as dnfw.inserts.ref's (40 blocks: FUZZ on "
           "two tracks, TAPE, FOLD and HARM on one each, knobs moved, a track switched on)"] = exact
    checks["FUZZ: the voices whose track has no insert (OFF, a type not built) untouched"] = others_same
    checks["FUZZ: it changes the sound (not a pass-through)"] = changed > 500
    numbers["FUZZ: first mismatch (block)"] = first_bad
    numbers["FUZZ: run info"] = info if "halt" in info else {"blocks": len(caps)}

    # 2b. voices moving: the frame's slot map (0xa5a + 2 s) rotating tracks 1, 2, 5, 16 (and 2 twice)
    # over five slots with different inserts; each slot gets the insert of the track it plays
    def par_routed(b):
        rows = bytearray(128)
        rows[0:8] = bytes([D.FUZZ, 127, 100, 70, 30, 40, 0, 110])
        rows[8:16] = bytes([D.TAPE, 127, 90, 110, 100, 110, 80, 60])
        rows[32:40] = bytes([D.FOLD, 127, 100, 70, 64, 90, 110, 0])
        rows[120:128] = bytes([D.HARM, 127, 127, 50, 64, 100, 110, 0])
        return bytes(rows)
    caps, info = blocks(par_routed, 36, routed=True)
    ref = R.Ref()
    exact, first_bad, rotated, quiet = bool(caps), None, set(), True
    for b, c in enumerate(caps):
        bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
        ref.block(D.records(c["par"]), bufs, c["route"])
        want = [[fb(x) for x in bufs[t]] for t in range(16)]
        if c.get("out") != want:
            exact = False
            first_bad = first_bad or b
        rotated.add(tuple(c["route"][:5]))
        quiet &= all(c["out"][t] == c["in"][t] for t in range(5, 16))
    checks["voices moving: every slot gets the insert of the track it plays, as dnfw.inserts.ref's "
           "(36 blocks, tracks 1 2 5 16 rotating over five slots, track 2 on two at once)"] = exact
    checks["voices moving: the slot map really moved (the DSP's own copy of it)"] = len(rotated) >= 5
    checks["voices moving: the slots playing no track untouched"] = quiet
    numbers["voices moving: first mismatch (block); slot maps seen"] = (first_bad, len(rotated))

    # 3. the pass's cost alone: called at its entry, stopped at PING's, on a state after the blocks
    fx = M5.fx
    base = M5.init_on(snap, m2mach, m5img, warm=True)
    out = M5.run_blocks(base, lambda _b: frames(1), 2)
    cost = {}
    for name, typ, n_on in (("all OFF", D.OFF, 0), ("FUZZ on 1 voice", D.FUZZ, 1), ("FUZZ on 4 voices", D.FUZZ, 4),
                            ("FUZZ on 16 voices", D.FUZZ, 16), ("TAPE on 1 voice", D.TAPE, 1),
                            ("TAPE on 16 voices", D.TAPE, 16), ("FOLD on 1 voice", D.FOLD, 1),
                            ("FOLD on 16 voices", D.FOLD, 16), ("HARM on 1 voice", D.HARM, 1),
                            ("HARM on 16 voices", D.HARM, 16)):
        r = out["state"].fresh_call(dsp.INS_SW, regs={})
        rows = bytearray(128)
        for t in range(n_on):
            rows[8 * t:8 * t + 8] = bytes([typ, 100, 100, 60, 30, 40, 20, 110])
        for k in range(8):                       # slot s plays track s: the cost per voice
            m2.poke(r.state, D.ROUTE + 4 * k, (2 * k) | (2 * k + 1) << 16)
        for k, v in enumerate(D.records(bytes(rows))):   # the unpacked records (no change word moved)
            m2.poke(r.state, D.TABLE + 4 * k, v)
        how = fx.run(r, 3_000_000, fx.Fixups(), stop_at=[dsp.PING_SW])
        cost[name] = (how[0], how[2])
    numbers["the pass alone: instructions a block (stop, count)"] = cost
    checks["the pass alone runs to PING's entry in every case"] = all(v[0] == "stop" for v in cost.values())
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
