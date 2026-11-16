"""The SHARC runner's A2 filter machines step (dnfw.a2f, filter types 7..11): real blocks of the build
(sw 0x1c2712 and the chain), tracks 1..3 PERC voices retriggered, each on one of the filter machines
(FREQ, RES, MODE, FRQ2, RES2, MOD2, the envelope and key tracking set in the frame's sound fields);
at the pass's entry (dnfw.waverider.dsp.A2F_SW) the pass's run-mode model (dnfw.a2f.live.run) runs on
the DSP's own memory, and at PING's entry (where the pass hands on) every word the model wrote must be
the DSP's, bit for bit (the slot buffers and the pass's state; its scratch words may differ).

1. Three tracks on SVF, DIOD and MS20 (track 3 switched to LADR at block 12, track 1 to OTA at 20),
   the cutoffs and modes moved: bit for bit every block; the filters change the sound.
2. Every track on a stock filter: the buffers at PING's entry are the buffers at the pass's entry.
3. The pass's cost per block (instructions between the two entries).
"""

from __future__ import annotations

from dnfw.a2f import live as AL
from dnfw.a2f import program as AP
from dnfw.perc.dsl import Mem
from dnfw.waverider import dsp
from dnfw.waverider import frame as FR

# frame sound indices (dnfw.waverider.frame.RECORD_FIELDS)
I_MODE, I_FREQ, I_RES, I_DEPTH, I_MOD2, I_ATK, I_DEC, I_FRQ2, I_RES2, I_KEYT = 66, 67, 68, 69, 70, 71, 72, 73, 74, 79


def _sound(cut, res, mode, frq2, res2, mod2, atk=10, dec=60, depth=96, keyt=0) -> dict[int, int]:
    """0..127 knobs -> the frame's 16-bit words (0x7f00 = 1.0 for 't', 0x8000 = 1.0 for 'u')"""
    t = lambda k: (k * 0x7F00) // 127
    u = lambda k: (k * 0x8000) // 128
    return {I_MODE: t(mode * 25 + 12), I_FREQ: u(cut), I_RES: u(res), I_DEPTH: u(depth),
            I_MOD2: t(mod2 * 25 + 12), I_ATK: t(atk), I_DEC: t(dec), I_FRQ2: t(frq2), I_RES2: t(res2),
            I_KEYT: keyt * 200}


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers = {}, {}

    def setup(b):
        """track -> (filter type, its sound) at block b"""
        out = {0: (7, _sound(70 if b < 16 else 40, 100, 1, 90, 30, 3))}           # SVF LP24, filter 2 HP
        out[1] = (10 if b < 20 else 9, _sound(55, 120, 0, 100, 60, 2, depth=110))   # DIOD, then OTA
        out[2] = (11 if b < 12 else 8, _sound(80, 127, 4, 50, 110, 0, keyt=64))    # MS20 NOTCH, then LADR
        return out

    def frames(b, on=True):
        f = M5.base_frame(sound, machines, overrides=M5.perc_words(1), trigger=b % 8 == 1,
                          others={1: 5, 2: 5}, trigger_others=True)
        if on:
            for t, (typ, snd) in setup(b).items():
                f.header(FR.FILTER, t, typ)
                for k, v in snd.items():
                    f.param(t, k, v)
        return f.to_bytes()

    def blocks(n, on=True):
        caps, cur = [], {}

        def at_a2f(r):
            cur.clear()
            mem = Mem(read=lambda a, r=r: m2.word(r.state, a) or 0)
            p = AL.run(mem)
            cur["want"] = dict(mem.w) if hasattr(mem, "w") else dict(mem.__dict__.get("m", {}))
            cur["steps"] = p.steps
            cur["ptr"] = [m2.word(r.state, AP.BUFFERS + 4 * s) or 0 for s in range(16)]
            cur["in"] = [[m2.word(r.state, cur["ptr"][s] + 4 * j) or 0 for j in range(32)] for s in range(16)]

        def at_ping(r):
            want = cur.get("want", {})
            scratch = range(AP.SCRATCH, AP.TABLES)
            bad = [a for a, v in want.items() if a not in scratch and (m2.word(r.state, a) or 0) != v]
            cur["bad"] = bad
            cur["out"] = [[m2.word(r.state, cur["ptr"][s] + 4 * j) or 0 for j in range(32)] for s in range(16)]
            caps.append(dict(cur))

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        info = []
        for b in range(n):
            out = M5.run_blocks(state, lambda _b, b=b: frames(b, on), 1,
                                extra_hooks={dsp.A2F_SW: at_a2f, dsp.PING_SW: at_ping})
            if not out.get("ok"):
                return caps, {"halt": out.get("halt"), "block": b}
            info.append(out["instructions"])
            state = out["state"]
        return caps, {"instructions": info}

    caps, info = blocks(28)
    exact = bool(caps) and all(not c.get("bad") for c in caps)
    changed = sum(1 for c in caps for s in range(16) for j in range(32) if c["out"][s][j] != c["in"][s][j])
    checks["filter machines: every word the pass wrote is dnfw.a2f.live's, bit for bit (28 blocks: SVF, "
           "DIOD -> OTA, MS20 -> LADR, cutoffs and modes moved, trigs)"] = exact
    checks["filter machines: they change the sound (not a pass-through)"] = changed > 500
    # 2026-11-10: ONE_VOICE (dnfw.a2f.program): a block filters one voice, the newest note's; the others pass dry
    # 2026-11-11 (perf): ONE_VOICE off: every slot that sounds on a filter machine is filtered (the engine keeps
    # 14-16 slots sounding here: a silent input and zero states are skipped, dnfw.a2f.program._quiet)
    checks["filter machines: " + ("at most one voice is filtered in a block, and one is (ONE_VOICE: the newest note's)"
                                 if AP.ONE_VOICE else "every sounding voice of the three tracks is filtered (at least 3 slots a block)")] = (
        bool(caps) and all((sum(1 for s in range(16) if c["out"][s] != c["in"][s]) == 1 if AP.ONE_VOICE
                            else sum(1 for s in range(16) if c["out"][s] != c["in"][s]) >= 3) or (b < 2)
                           for b, c in enumerate(caps)))
    nfil = [sum(1 for s in range(16) if c["out"][s] != c["in"][s]) for c in caps]
    numbers["filter machines: slots filtered a block (min, max, from block 2)"] = (min(nfil[2:]), max(nfil[2:])) if len(nfil) > 2 else None
    numbers["filter machines: first block with a mismatch, its words"] = next(
        ((b, c["bad"][:6]) for b, c in enumerate(caps) if c.get("bad")), None)
    numbers["filter machines: the model's steps a block (min, max)"] = (
        min(c["steps"] for c in caps), max(c["steps"] for c in caps)) if caps else None
    numbers["filter machines: run info"] = info if "halt" in info else {"blocks": len(caps)}

    caps, info = blocks(10, on=False)
    checks["stock filters: every buffer after the pass is the buffer before it (10 blocks)"] = (
        bool(caps) and all(c["out"] == c["in"] for c in caps))
    numbers["stock filters: run info"] = info if "halt" in info else {"blocks": len(caps)}
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
