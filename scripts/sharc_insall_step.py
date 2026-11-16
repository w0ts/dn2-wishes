"""The SHARC runner's insall step (docs/inserts.md): every mono insert type this build runs
(dnfw.inserts.design.BUILT: FUZZ TAPE FOLD HARM and the ported SUB DIST GATER RING) alone on the
sounding track 0, at its power-on knobs (ins.c DEFAULT, MIX 127) for 12 blocks and then at an
extreme (every knob 127, MIX 127) for 12 more. Per type: every buffer after the pass is
dnfw.inserts.ref's (bit for bit), the track's buffer differs from the dry one in both halves (the
insert does something), and the other tracks are untouched. The result names every type whose
output equals its dry input ("does nothing").

2026-11-10, after the User's "some insert FX do nothing on the unit": step 3i's reference check ran
FUZZ TAPE FOLD HARM only, so SUB DIST GATER RING had never run in the runner.
"""

from __future__ import annotations

import os
import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import ref as R
from dnfw.waverider import dsp

# ins.c DEFAULT[type] (K1..K6), by type number; MIX 127
DEFAULT = {D.FUZZ: (64, 90, 0, 30, 0, 100), D.TAPE: (50, 30, 20, 25, 50, 10), D.FOLD: (80, 64, 0, 100, 100, 0),
           D.HARM: (50, 70, 64, 80, 100, 0), D.SUB: (100, 85, 59, 0, 127, 0), D.DIST: (64, 90, 20, 64, 64, 0),
           D.GATER: (127, 64, 64, 20, 0, 0), D.RING: (64, 0, 0, 100, 0, 0)}


# the extreme half: every knob 127, but RING's AM (127 is the dry by design: "0 ring, 127 the dry")
EXTREME = {D.RING: (127, 127, 64, 127, 0, 0)}
# GATER runs from the tempo and starts on an open step; a test this short never reaches a closed one, so the
# ColdFire's clock word (values word 1: bit 31 playing, bits 0..11 ticks of 1/96 beat) puts its phase on one:
# defaults (PATN 64 -> 6D6D... ) are not closed at 29 ticks at RATE 1/16, so use these two settings
GATER_ROWS = ((127, 16, 64, 20, 0, 0), (127, 127, 127, 127, 0, 0))     # PATN 16: 0x1111, RATE 1/16 | PATN 127: 0x4949, RATE 1/64
GATER_CLK = 0x80000000 | 29                                           # step 1 (1/16) / step 4 (1/64): closed in both patterns


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers, nothing = {}, {}, []

    def frames(b):
        f = M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 24 == 1,
                          others={1: 5, 2: 5, 3: 5, 4: 5}, trigger_others=True)
        return f.to_bytes()

    def blocks(par_of, n):
        caps, cur = [], {}

        def put_par(r):
            par = par_of(len(caps))
            words = list(D.pack(D.records(par), 1 + len(caps)))
            if par[0] == D.GATER:
                words[1] = GATER_CLK
            for k, w in enumerate(words):
                m2.poke(r.state, D.GEN + 4 * k, w)

        def at_ins(r):
            cur.clear()
            cur["par"] = par_of(len(caps))
            cur["tempo"] = m2.word(r.state, D.TEMPO) or 0
            cur["ptr"] = [m2.word(r.state, D.BUFFERS + 4 * t) for t in range(16)]
            cur["in"] = [[m2.word(r.state, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
            cur["route"] = [((m2.word(r.state, D.ROUTE + 4 * (s_ // 2)) or 0) >> (16 * (s_ & 1))) & 0xFFFF
                            for s_ in range(16)]

        def at_ping(r):
            cur["out"] = [[m2.word(r.state, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
            caps.append(dict(cur))

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        for b in range(n):
            put_par(state)
            out = M5.run_blocks(state, lambda _b, b=b: frames(b), 1,
                                extra_hooks={dsp.INS_SW: at_ins, dsp.PING_SW: at_ping})
            if not out.get("ok"):
                return caps, {"halt": out.get("halt"), "block": b}
            state = out["state"]
        return caps, {}

    only = os.environ.get("INSALL_ONLY")
    for typ in D.BUILT:
        name = D.NAMES[typ]
        if only and name not in only.split(","):
            continue

        def par_of(b, typ=typ):
            rows = bytearray(128)
            if typ == D.GATER:
                rows[0:8] = bytes([typ, 127, *GATER_ROWS[b >= 12]])
            else:
                rows[0:8] = bytes([typ, 127, *(DEFAULT[typ] if b < 12 else EXTREME.get(typ, (127,) * 6))])
            return bytes(rows)

        caps, info = blocks(par_of, 24)
        ref = R.Ref()
        exact = bool(caps) and "halt" not in info
        changed = [0, 0]
        heard = [0, 0]
        for b, c in enumerate(caps):
            bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
            ref.block(D.records(c["par"]), bufs, c["route"], tempo=c["tempo"],
                      clk=GATER_CLK if typ == D.GATER else 0)
            exact &= c.get("out") == [[fb(x) for x in bufs[t]] for t in range(16)]
            half = b // 12
            heard[half] += sum(1 for j in range(32) if c["in"][0][j] & 0x7FFFFFFF)
            changed[half] += sum(1 for j in range(32) if c["out"][0][j] != c["in"][0][j])
        checks[f"{name}: every buffer after the pass as dnfw.inserts.ref's (24 blocks, defaults then every knob 127)"] = exact
        checks[f"{name}: track 0 sounds in both halves (the test hears something)"] = min(heard) > 100
        checks[f"{name}: it changes the sound at its defaults (not equal to dry)"] = changed[0] > 20
        checks[f"{name}: it changes the sound at every knob 127 (not equal to dry)"] = changed[1] > 20
        numbers[f"{name}: words changed on track 0 (defaults, extreme); words heard"] = (changed, heard, info)
        if min(changed) <= 20:
            nothing.append(name)
        print(f"    {name}: changed {changed} of heard {heard}", flush=True)
    numbers["types whose output equals the dry signal (does nothing)"] = nothing
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
