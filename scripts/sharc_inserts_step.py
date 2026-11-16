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

    def blocks(par_of, n, routed=False, frames_fn=None, fixed_gen=False, tpg=None):
        caps = []
        cur = {}

        def put_par(r):                          # (2026-11-10: packed, a new change word each block, as the
            par = par_of(len(caps))              # link sends them: the pass's own unpack runs every block)
            for k, w in enumerate(D.pack(D.records(par), 1 if fixed_gen else 1 + len(caps))):
                m2.poke(r.state, D.GEN + 4 * k, w)
            for k, w in enumerate(tpg or []):        # (2026-11-13: TAPE's PGAIN bytes, as link.c sends them)
                m2.poke(r.state, D.TP_PG_DDR + 4 * k, w)

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
            out = M5.run_blocks(state, (lambda _b, b=b: frames_fn(b)) if frames_fn else (lambda _b, b=b: frames(b, routed)), 1,
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
        rows[8:16] = bytes([D.FUZZ | (D.FZ_AUTO_BIT if b >= 25 else 0), 64, 127, 20, 0, 0, 20, 100]) if b >= 8 else bytes(8)
        # (2026-11-13: FUZZ's AUTO, field 0's bit 4, switched on at block 25)
        rows[40:48] = bytes([D.WIDE, 127, 127, 127, 127, 127, 127, 127])
        rows[16:24] = bytes([D.TAPE | (D.FZ_AUTO_BIT if b >= 30 else 0), 127, 90, 110, 100, 110, 80, 60])   # TAPE on
        # track 2 (2026-11-13: its PGAIN -6 dB, below, and AUTO from block 30)
        rows[24:32] = bytes([D.FOLD, 127, 100, 70, 64, 90, 110, 0])            # FOLD on track 3 (silent)
        rows[32:40] = bytes([D.HARM, 127, 127, 50, 64, 100, 110, 0])           # HARM on track 4 (silent)
        if b >= 30:
            rows[16:24] = bytes([D.TAPE | D.FZ_AUTO_BIT, 100, 127, 127, 0, 127, 127, 0])
        return bytes(rows)
    tpg = [0] * D.TP_PG_WORDS
    tpg[1] = (-6) & 0x7F                         # record 4 (track 2's slot 1): word 1, byte 0
    caps, info = blocks(par_of, 40, tpg=tpg)
    ref = R.Ref()
    ref.tpg[4] = (-6) & 0x7F
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

    # 2c. 2026-11-12 (opt-host's measure on A09: T9 owns slots 2..15, so its DIST ran 14 times a block, sounding or
    # not): slots 2..15 on track 10's DIST, one of them sounding; the silent ones skip it once at rest (program.quiet,
    # DIST's gate smoothing ~250 blocks into silence): every buffer still the reference's, the pass's instructions down
    def frames_q(b):
        f = M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                          others={2: 5}, trigger_others=True)
        for s_ in range(16):
            f.put(0xA5A + 2 * s_, s_ if s_ < 2 else 9)
        return f.to_bytes()

    def par_q(b):
        rows = bytearray(128)
        rows[72:80] = bytes([D.DIST, 127, 90, 90, 20, 64, 64, 0])
        return bytes(rows)
    caps, info = blocks(par_q, 300, frames_fn=frames_q, fixed_gen=True)   # (the link moves it only on an edit:
                                                                          # ins.c ins_gen; quiet's mark needs that)
    ref = R.Ref()
    exact, first_bad = bool(caps), None
    for b, c in enumerate(caps):
        bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
        ref.block(D.records(c["par"]), bufs, c["route"])
        if c.get("out") != [[fb(x) for x in bufs[t]] for t in range(16)]:
            exact = False
            first_bad = first_bad if first_bad is not None else b
    ins = info.get("instructions") or [0]
    early, late = sum(ins[5:25]) / 20, sum(ins[-20:]) / 20
    zero_in = [sum(1 for s_ in range(16) if c["route"][s_] == 9 and not any(w & 0xFFFFFFFF for w in c["in"][s_]))
               for c in caps[-3:]]
    print(f"    quiet: instructions a block {round(early)} (blocks 5..24), {round(late)} (the last 20); slots on track "
          f"10 with all-zero input in the last 3 blocks {zero_in}; first mismatch {first_bad}", flush=True)
    for s_ in (2, 3, 7, 15):                     # what a silent slot's buffer holds: its size, and whether it is the
        c0, c1 = caps[-2], caps[-1]              # last block's output (a buffer no voice rewrites)
        mx = max(abs(float(bf(w))) for w in c1["in"][s_])
        print(f"    quiet: slot {s_} max |in| {mx:.3g}; in == last block's out: {c1['in'][s_] == c0['out'][s_]}; "
              f"in == last block's in: {c1['in'][s_] == c0['in'][s_]}; ptr {c1['ptr'][s_]:#x}", flush=True)
    mapped = sum(1 for s_ in range(16) if caps and caps[-1]["route"][s_] == 9)
    checks["14 slots on one DIST track, one sounding: every buffer as dnfw.inserts.ref's (300 blocks; the silent "
           "slots skip DIST once at rest)"] = exact and mapped == 14
    checks["14 slots on one DIST track: the block's instructions fall once the silent slots are at rest"] = late < early - 20_000
    numbers["quiet: instructions a block, blocks 5..24 and the last 20; first mismatch"] = (round(early), round(late), first_bad)

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
        for k, v in enumerate(D.flags(D.records(bytes(rows)))):   # its flags (perf, 2026-11-10)
            m2.poke(r.state, D.FLAGS + 4 * k, v)
        how = fx.run(r, 3_000_000, fx.Fixups(), stop_at=[dsp.PING_SW])
        cost[name] = (how[0], how[2])
    numbers["the pass alone: instructions a block (stop, count)"] = cost
    checks["the pass alone runs to PING's entry in every case"] = all(v[0] == "stop" for v in cost.values())
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
