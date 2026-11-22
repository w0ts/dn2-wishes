"""The SHARC runner's pitrack step (2026-11-14, delay leaks; the User: "Fix all, start fresh"): a P-I voice handed
to another track starts its delay lines from silence (dnfw.md.voice.new_track).

Voice slot 0 on PERC PI-BD at its defaults (the frame's track arrays are the voice slots'). Run A: slot 0 plays
track 0's note (block 1) and rings, then the slot map (0xa5a) hands slot 0 to track 1, whose note starts at block
HAND. Run B: slot 0 plays no track until then, then track 1's note the same way (a voice that never rang). The same machine, so no
machine change cleared the lines before the fix: A's note on track 1 had track 0's ring in its lines.

1. A rang: slot 0's P-I delay lines hold track 0's ring before the hand-over (not zeros).
2. From the hand-over on, slot 0's delay lines in A hold only what the new note wrote: as many non-zero words as
   B's (within 8; the voice's other state words carry over, so the write position, and the output, are not B's
   word for word), where without the fix they held track 0's whole ring (~1,050 words).
"""

from __future__ import annotations

from dnfw.inserts import design as D
from dnfw.md import core as K
from dnfw.waverider import dsp

PI_BD = 25                                       # dnfw.perc.machines.NAMES
HAND = 14
N = HAND + 8


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    m2 = M5.m2
    checks, numbers = {}, {}
    pi = M5.perc_words(PI_BD)

    def frames(b, ring_first):                   # (the frame's track arrays are the voice slots'; 0xa5a + 2 s the
        f = M5.base_frame(sound, machines, overrides=pi)   # track slot s plays, seen by the DSP a block later)
        tr = (0 if ring_first else 0xFFFF) if b < HAND - 2 else 1
        for s_ in range(16):
            f.put(0xA5A + 2 * s_, tr if s_ == 0 else 0xFFFF)
        if (ring_first and b == 1) or b == HAND:
            f.trigger(0)                         # voice slot 0's notes: track 0's, then track 1's
        return f.to_bytes()

    def lines(st):
        # (2026-11-16: slot 0's lines in L1 block 2, dsp.MD_DELAY_L1, 6 KB a slot)
        return [m2.word(st, dsp.MD_DELAY_L1 + 4 * k) or 0 for k in range(dsp.MD_DELAY_STRIDE // 4)]

    def play(ring_first):
        caps = []

        def at_ins(r):
            q = m2.word(r.state, D.BUFFERS)
            outs = [[m2.word(r.state, q + 4 * j) or 0 for j in range(32)]]
            caps.append({"out": outs[0], "lines": lines(r.state)})

        state = M5.init_on(snap, m2mach, m5img, warm=True)
        for b in range(N):
            out = M5.run_blocks(state, lambda _b, b=b: frames(b, ring_first), 1, extra_hooks={dsp.INS_SW: at_ins})
            if not out.get("ok"):
                return caps, {"halt": str(out.get("halt")), "block": b}
            state = out["state"]
        return caps, {"blocks": len(caps)}

    a, ia = play(True)
    b, ib = play(False)
    ok = len(a) == N and len(b) == N
    checks["A rang: slot 0's P-I delay lines hold track 0's ring before the hand-over"] = (
        ok and any(a[HAND - 1]["lines"]))
    nz = [(sum(1 for w in a[k]["lines"] if w), sum(1 for w in b[k]["lines"] if w)) if ok else (0, 0)
          for k in range(N)]
    checks["handed to track 1: from the hand-over slot 0's delay lines hold only what the new note wrote (non-zero "
           "words within 8 of a never-rung voice's), not track 0's ring"] = (
        ok and all(nz[k][0] <= nz[k][1] + 8 for k in range(HAND, N)))
    checks["track 1's note sounds (not a run of zeros)"] = ok and any(w & 0x7FFFFFFF for k in range(HAND, N)
                                                                       for w in b[k]["out"])
    numbers["lines non-zero (A, B) from the block before the hand-over"] = nz[HAND - 1:]
    numbers["run info (A, B)"] = (ia, ib)
    print("PITRACK", numbers["lines non-zero (A, B) from the block before the hand-over"])
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
