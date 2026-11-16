"""The SHARC runner's inspost step (docs/inserts.md "After the pan"): real blocks of the build, PERC voices
on five voice slots, the engine's call of the FX sends (sw 0x1c3054) landing in wr_inpost
(dnfw.waverider.dsp.POST_SW), which JUMPs on to the sends (0x1c1738). Each voice slot's stereo block
(design.STEREO) captured at both entries.

**The voice chain's stereo.** The voice chain writes each slot's stereo block with `I1 = MODIFY(I0, M4)`,
I0 = 0, M4 = 0x257ee8 + 0x100 s (sw 0x1c9af6 .. 0x1c9b21), where the FX sends (0x1c179d .., 0x1c1884) and the
routing (0x1c1fb0) read it. Until 2026-11-14 the runner scaled that blank modifier by 4 and put the block at
0x95fba0 + 0x400 s, so this step copied it across at wr_inpost's entry; the runner's G13
(scripts/sharc_dn2_fixups.py: MODIFY's blank width selector is bytes) puts it where the unit has it, and the
copy is gone (it copied the now-empty 0x95fba0 over the voices).

1. Every insert OFF: every slot's block at the sends' entry is the block at wr_inpost's entry, and every
   register the engine passed (R0..R15, I0..I4, I12) is back as it came.
2. WIDE, CHOR and JUNO on tracks 1, 2, 5, 16 (and a pre insert on track 4), the slot map rotating them over six
   voice slots (track 2 on two at once), knobs moved, a track switched from WIDE to CHOR: each block every
   slot as dnfw.inserts.postref's, bit for bit; the slots whose track has no post insert untouched.
2b. (2026-11-14, the User: "Fix all, start fresh") a post insert that did not run starts from silence: track 1's
   CHOR on voice slot 0, the slot handed to track 3 (no insert) and back, track 1's M.SEL OFF and back, every post
   insert OFF (no walk) and back; the slot's input silenced from each return: postref's bit for bit, exact zeros.
3. The pass alone, per voice: OFF, WIDE, CHOR with one and four voices, JUNO, on 1 and 16 slots.
"""

from __future__ import annotations

import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import post as P
from dnfw.inserts import postref as R
from dnfw.waverider import dsp
import sharc_f32 as F32

KEEP = [f"R{k}" for k in range(16)] + [f"I{i}" for i in P.SAVE_I]


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2, fx = M5.m2, M5.fx
    checks, numbers = {}, {}

    def regs(r):
        out = {}
        for n in KEEP:
            v = r.state.uregs.get(fx.UREG_CODES[n])
            out[n] = getattr(v, "value", None)
        return out

    def stereo(st):
        lo = [[m2.word(st, D.STEREO + D.STEREO_STRIDE * s + 4 * j) or 0 for j in range(32)] for s in range(16)]
        ro = [[m2.word(st, D.STEREO + D.STEREO_STRIDE * s + D.STEREO_R + 4 * j) or 0 for j in range(32)]
              for s in range(16)]
        return lo, ro

    def route_of(b):
        rt = [0xFFFF] * 16
        for j, tr in enumerate((0, 1, 4, 15, 1, 3)):
            rt[(b // 6 + j) % 6] = tr
        return rt

    def frames(b, routed):
        f = M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                          others={1: 5, 2: 5, 3: 5, 4: 5, 5: 5}, trigger_others=True)
        if routed:
            for s_, tr in enumerate(routed(b) if callable(routed) else route_of(b)):
                f.put(0xA5A + 2 * s_, tr)
        return f.to_bytes()

    def blocks(par_of, n, routed, silent=None):
        caps, cur = [], {}

        def at_post(r):
            st = r.state
            if silent is not None and silent(len(caps)):   # silent input: the voices' blocks zeroed where the sends read
                for s_ in range(16):
                    for j in range(32):
                        m2.poke(st, D.STEREO + D.STEREO_STRIDE * s_ + 4 * j, 0)
                        m2.poke(st, D.STEREO + D.STEREO_STRIDE * s_ + D.STEREO_R + 4 * j, 0)
            for k, v in enumerate(D.records(par_of(len(caps)))):   # the pre pass's unpacked records
                m2.poke(st, D.TABLE + 4 * k, v)
            for k, v in enumerate(D.flags(D.records(par_of(len(caps))))):   # its flags (perf, 2026-11-10)
                m2.poke(st, D.FLAGS + 4 * k, v)
            cur.clear()
            cur["par"] = par_of(len(caps))
            cur["in"] = stereo(st)
            cur["route"] = [((m2.word(st, D.ROUTE + 4 * (s_ // 2)) or 0) >> (16 * (s_ & 1))) & 0xFFFF
                            for s_ in range(16)]
            cur["regs_in"] = regs(r)

        def at_sends(r):
            if "in" in cur and "out" not in cur:
                cur["out"] = stereo(r.state)
                cur["regs_out"] = regs(r)
                caps.append(dict(cur))

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        for b in range(n):
            out = M5.run_blocks(state, lambda _b, b=b: frames(b, routed), 1,
                                extra_hooks={dsp.POST_SW: at_post, P.SENDS_SW: at_sends})
            if not out.get("ok"):
                return caps, {"halt": str(out.get("halt")), "block": b}
            state = out["state"]
        return caps, {"blocks": len(caps)}

    # 1. all OFF
    caps, info = blocks(lambda b: bytes(128), 24, False)
    checks["every insert OFF: every slot's stereo block at the sends' entry is the block at the pass's "
           "entry (24 blocks)"] = bool(caps) and all(c["out"] == c["in"] for c in caps)
    checks["every insert OFF: R0..R15, I0..I4, I12 at the sends' entry as the engine passed them"] = (
        bool(caps) and all(c["regs_out"] == c["regs_in"] and None not in c["regs_in"].values() for c in caps))
    heard = F32.Ear().hear(w for c in caps for s_ in range(16) for w in c["in"][0][s_] + c["in"][1][s_])
    checks["the test's voices sound in stereo (not a run of zeros), finite"] = heard.ok(500)
    numbers["all OFF"] = info

    # 2. WIDE and CHOR with voices moving
    def par_of(b):
        rows = bytearray(128)
        rows[0:8] = bytes([D.WIDE, 127, 100, 60, 40, 80, 0, 0])
        rows[8:16] = bytes([D.CHOR, 90, 80, 50, 60, 127, 100, 60])
        rows[32:40] = bytes([D.CHOR, 127, 127, 127, 0, 0, 0, 127])
        rows[120:128] = bytes([D.WIDE, 64, 0, 127, 127, 0, 0, 0])
        rows[24:32] = bytes([D.FUZZ, 127, 127, 127, 127, 127, 127, 127])
        if b >= 16:
            rows[8:16] = bytes([D.CHOR, 127, 30, 127, 20, 40, 0, 127])
        if b >= 28:
            rows[0:8] = bytes([D.CHOR, 127, 60, 60, 60, 127, 64, 90])
        if b >= 20:                                  # 2026-11-12: JUNO, MODE I+II, then II
            rows[120:128] = bytes([D.JUNO, 127, 110, 0, 0, 0, 0, 0])
        if b >= 34:
            rows[120:128] = bytes([D.JUNO, 80, 60, 0, 0, 0, 0, 0])
            rows[32:40] = bytes([D.JUNO, 127, 0, 0, 0, 0, 0, 0])
        return bytes(rows)
    caps, info = blocks(par_of, 40, True)
    ref = R.PostRef()
    exact, first_bad, bare_same, regs_back, changed, maps = bool(caps), None, True, True, 0, set()
    for b, c in enumerate(caps):
        lin = [[bf(w) for w in c["in"][0][s_]] for s_ in range(16)]
        rin = [[bf(w) for w in c["in"][1][s_]] for s_ in range(16)]
        ref.block(D.records(c["par"]), lin, rin, c["route"])
        want = ([[fb(x) for x in row] for row in lin], [[fb(x) for x in row] for row in rin])
        if c["out"][0] != want[0] or c["out"][1] != want[1]:
            exact = False
            first_bad = first_bad if first_bad is not None else b
        for s_ in range(16):
            tr = c["route"][s_]
            if tr > 15 or c["par"][8 * tr] not in D.POST:
                bare_same &= c["out"][0][s_] == c["in"][0][s_] and c["out"][1][s_] == c["in"][1][s_]
        regs_back &= c["regs_out"] == c["regs_in"]
        changed += sum(1 for s_ in range(16) for j in range(32) if c["out"][0][s_][j] != c["in"][0][s_][j])
        maps.add(tuple(c["route"][:6]))
    checks["WIDE, CHOR, JUNO: every slot after the pass as dnfw.inserts.postref's (40 blocks; tracks 1 2 5 16 "
           "rotating over six slots, track 2 on two, knobs moved, track 1 WIDE -> CHOR, track 16 WIDE -> JUNO "
           "I+II -> II, track 5 CHOR -> JUNO I)"] = exact
    checks["WIDE, CHOR: the slots whose track has no post insert untouched"] = bare_same
    checks["WIDE, CHOR: every register the engine passed back at the sends' entry"] = regs_back
    checks["WIDE, CHOR: they change the sound (not a pass-through)"] = changed > 500
    checks["WIDE, CHOR: the slot map really moved (the DSP's own copy)"] = len(maps) >= 5
    numbers["WIDE, CHOR: first mismatch (block); slot maps seen"] = (first_bad, len(maps))
    numbers["WIDE, CHOR: run info"] = info

    # 2b. a post insert that did not run starts from silence
    def back_par(b):
        rows = bytearray(128)
        rows[0:8] = bytes([D.CHOR, 127, 90, 80, 50, 60, 127, 100])          # track 1
        rows[40:48] = bytes([D.WIDE, 64, 0, 127, 127, 0, 0, 0])              # track 6: the pass walks
        if 30 <= b < 34:
            rows[0:8] = bytes(8)                                             # track 1 OFF, then back
        if 46 <= b < 50:
            rows = bytearray(128)                                            # nothing: no walk, then back
        return bytes(rows)

    def back_route(b):
        rt = [0xFFFF] * 16
        rt[0] = 2 if 14 <= b < 18 else 0                                     # slot 0: track 1, 3, 1
        rt[3] = 5
        return rt
    back_quiet = [range(18, 23), range(34, 39), range(50, 55)]
    caps, info = blocks(back_par, 56, back_route, silent=lambda b: any(b in w for w in back_quiet))
    ref = R.PostRef()
    exact, first_bad, played, quiet = len(caps) == 56, None, False, True
    for b, c in enumerate(caps):
        lin = [[bf(w) for w in c["in"][0][s_]] for s_ in range(16)]
        rin = [[bf(w) for w in c["in"][1][s_]] for s_ in range(16)]
        ref.block(D.records(c["par"]), lin, rin, c["route"])
        want = ([[fb(x) for x in row] for row in lin], [[fb(x) for x in row] for row in rin])
        if c["out"][0] != want[0] or c["out"][1] != want[1]:
            exact = False
            first_bad = first_bad if first_bad is not None else b
        if b < 14:
            played |= c["out"][0][0] != c["in"][0][0]
        if any(b in w for w in back_quiet):
            quiet &= not any(c["out"][0][0] + c["out"][1][0])
    checks["did not run, back: every slot as dnfw.inserts.postref's (56 blocks: slot 0 to another track and "
           "back, track 1 OFF and back, no walk and back)"] = exact
    checks["did not run, back: track 1's CHOR changed slot 0's sound before"] = played
    checks["did not run, back: exact zeros on slot 0 after each return, silent input (no old ring)"] = quiet
    numbers["did not run, back: first mismatch (block)"] = first_bad
    numbers["did not run, back: run info"] = info

    # 3. the pass alone
    base = M5.init_on(snap, m2mach, m5img, warm=True)
    out = M5.run_blocks(base, lambda _b: frames(1, False), 2)
    cost = {}
    for name, row, n_on in (("all OFF", [D.OFF] + [0] * 7, 0),
                            ("WIDE on 1 voice", [D.WIDE, 100, 100, 60, 60, 60, 0, 0], 1),
                            ("WIDE on 16 voices", [D.WIDE, 100, 100, 60, 60, 60, 0, 0], 16),
                            ("CHOR 1 voice, on 1 slot", [D.CHOR, 100, 100, 60, 60, 0, 60, 60], 1),
                            ("CHOR 1 voice, on 16 slots", [D.CHOR, 100, 100, 60, 60, 0, 60, 60], 16),
                            ("CHOR 4 voices, on 1 slot", [D.CHOR, 100, 100, 60, 60, 127, 60, 60], 1),
                            ("CHOR 4 voices, on 16 slots", [D.CHOR, 100, 100, 60, 60, 127, 60, 60], 16),
                            ("JUNO I, on 1 slot", [D.JUNO, 127, 0, 0, 0, 0, 0, 0], 1),
                            ("JUNO I+II, on 1 slot", [D.JUNO, 127, 127, 0, 0, 0, 0, 0], 1),
                            ("JUNO I, on 16 slots", [D.JUNO, 127, 0, 0, 0, 0, 0, 0], 16)):
        rows = bytearray(128)
        for t in range(n_on):
            rows[8 * t:8 * t + 8] = bytes(row)
        res = None
        for k_call in range(2):                      # the second call: the steady cost (no ring cleared)
            r = (out["state"] if k_call == 0 else r).fresh_call(dsp.POST_SW, regs={})
            for k in range(8):
                m2.poke(r.state, D.ROUTE + 4 * k, (2 * k) | (2 * k + 1) << 16)
            for k, v in enumerate(D.records(bytes(rows))):
                m2.poke(r.state, D.TABLE + 4 * k, v)
            for k, v in enumerate(D.flags(D.records(bytes(rows)))):   # its flags (perf, 2026-11-10)
                m2.poke(r.state, D.FLAGS + 4 * k, v)
            how = fx.run(r, 3_000_000, fx.Fixups(), stop_at=[P.SENDS_SW])
            res = (how[0], how[2])
            if how[0] != "stop":
                break
        cost[name] = res
    numbers["the pass alone: instructions a block, steady (stop, count)"] = cost
    checks["the pass alone runs to the sends' entry in every case"] = all(v[0] == "stop" for v in cost.values())
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
