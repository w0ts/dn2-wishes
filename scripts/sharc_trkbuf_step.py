"""The SHARC runner's trkbuf step (2026-11-15, the unit: a FLEX take with SRC TRK13, then TRK15, recorded silence on
stock machines; MAIN takes worked).

FLEX's TRK sources (dnfw.sampler.program, the recorder) and Overbridge's raw track channels read the per-track
buffers B (`0x259f68 + 0x100 k`). The output stage `0x1c244d` fills bucket route[s] from each voice slot s's mono
buffer, through the pointer table `0x257ea8 + 4 s` (16 contiguous words; stock's init copies it from `0x254a60`).
trackbuf.asm moves those buffers to L1 and re-points both tables, once, from entry_mark.asm's first pass. Until
2026-11-15 it wrote the copy as if interleaved: 2 of 16 buckets right, the rest another slot's or silence.

The runner's other steps call the per-block routine directly and never pass entry_mark.asm, and they sound voice
slot 0 only, so none saw it. Here, per image, three blocks of WaveTone on every track; the build first runs
wr_emark's first pass (TWIN cleared) as the firmware does. At the output stage's call of the third block: route[s]
= s for all 16 slots, the retrigger flags 0, and a marker (s + 1) / 64 in the 32 words of the buffer slot s's chain
writes (DM 0x254a60 + 4 s). Then:

- stock: bucket s holds its marker x 11.627 (the B gain), all 16 (the probe's own check);
- the build: all 16 buckets bit-identical to stock's, and the pointer table at 0x257ea8 the 16 L1 buffers in order;
- control: the build with the pre-2026-11-15 layout written back after the first pass must be seen (buckets differ).
"""

from __future__ import annotations

import struct

from dnfw.waverider import dsp

OUTPUT_CALL_SW = 0x1C307B                       # the engine's call of the output stage 0x1c244d
CALL_SITE_RETURN = 0x1C9FBC                     # wr_emark returns here (the handler's call site)
TWIN_WORD = 0x2DE140                            # 0: entry_mark.asm's first pass
ROUTE, FLAGS, PTR_A, PTR_B, BUCKETS = 0x257898, 0x2578B8, 0x254A60, 0x257EA8, 0x259F68
GAIN_B = 11.627
BLOCKS = 3


def _f2w(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _w2f(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def _old_layout(t: int) -> int:
    return PTR_B + 0x10 * (t // 2) + 4 * (t % 2)


def _first_pass(M5, r) -> None:
    M5.m2.poke(r.state, TWIN_WORD, 0)
    r.state.pc_sw = dsp.EMARK_SW
    res = M5.fx.run(r, 2_000_000, M5.fixups({}), stop_at=(CALL_SITE_RETURN,))
    if res[0] != "stop":
        raise RuntimeError(f"the first pass did not return to the call site: {res[:2]}")


def _run(M5, init, sound, machines, *, first_pass: bool, old_layout: bool) -> dict:
    m2, m4, fx = M5.m2, M5.m4, M5.fx
    frame = M5.base_frame(sound, machines, t0=1, others={t: 1 for t in range(1, 16)}).to_bytes()
    seen = {"armed": False}

    def at_output(r):
        if not seen["armed"]:
            return
        st = r.state
        for s in range(0, 16, 2):
            m2.poke(st, ROUTE + 2 * s, s | (s + 1) << 16)
        for k in range(4):
            m2.poke(st, FLAGS + 4 * k, 0)
        seen["ptr_a"] = [m2.word(st, PTR_A + 4 * s) or 0 for s in range(16)]
        seen["ptr_b"] = [m2.word(st, PTR_B + 4 * s) or 0 for s in range(16)]
        for s in range(16):
            for k in range(32):
                m2.poke(st, seen["ptr_a"][s] + 4 * k, _f2w((s + 1) / 64.0))
        seen["poked"] = True

    state = init
    for b in range(BLOCKS):
        r = m4.unpack_call(state, frame)
        if first_pass and b == 0:
            _first_pass(M5, r)
            if old_layout:
                for t in range(16):
                    m2.poke(r.state, _old_layout(t), dsp.TRACKBUF_DM + 0x80 * t)
            r = m4.unpack_call(r, frame)
        seen["armed"] = b == BLOCKS - 1
        res = fx.run(r, 40_000_000, M5.fixups({OUTPUT_CALL_SW: at_output}))
        if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
            return {"ok": False, "halt": f"block {b}: {res[:2]}"}
        state = r
    st = state.state
    buckets = [[(m2.word(st, BUCKETS + 0x100 * s + 4 * k) or 0) & 0xFFFFFFFF for k in range(32)] for s in range(16)]
    return {"ok": bool(seen.get("poked")), "buckets": buckets, "ptr_a": seen.get("ptr_a"), "ptr_b": seen.get("ptr_b")}


def run(M5, snap, m2mach, m5img, stockimg, sound, machines) -> dict:
    import sharc_stockout_step as SO
    runs = {
        "stock": _run(M5, M5.init_on(snap, m2mach, SO.fresh(stockimg), warm=True), sound, machines,
                      first_pass=False, old_layout=False),
        "build": _run(M5, M5.init_on(snap, m2mach, SO.fresh(m5img), warm=True), sound, machines,
                      first_pass=True, old_layout=False),
        "control": _run(M5, M5.init_on(snap, m2mach, SO.fresh(m5img), warm=True), sound, machines,
                        first_pass=True, old_layout=True),
    }
    ok = all(v["ok"] for v in runs.values())
    s, b, c = (runs[k].get("buckets") for k in ("stock", "build", "control"))

    def marker_ok(s_buckets, slot):
        want = (slot + 1) / 64.0 * GAIN_B
        return all(abs(_w2f(w) - want) < 1e-3 * want for w in s_buckets[slot])

    stock_marked = sum(marker_ok(s, k) for k in range(16)) if ok else 0
    same = [k for k in range(16) if b[k] == s[k]] if ok else []
    ctl_same = [k for k in range(16) if c[k] == s[k]] if ok else []
    l1 = [dsp.TRACKBUF_DM + 0x80 * t for t in range(16)]
    checks = {
        "the three runs (stock, build, control) return every block and reach the output stage": ok,
        "stock: every bucket holds its own slot's marker x 11.627, 16 of 16": stock_marked == 16,
        "build after trackbuf.asm's first pass: the pointer tables at 0x254a60 and 0x257ea8 are the L1 buffers in order":
            ok and runs["build"]["ptr_a"] == l1 and runs["build"]["ptr_b"] == l1,
        "build: the 16 TRK buckets (0x259f68 + 0x100 k, FLEX's TRK sources) bit-identical to stock's, 16 of 16":
            len(same) == 16,
        "control (the pre-2026-11-15 interleaved table written back): the comparison sees it": ok and len(ctl_same) < 16,
    }
    numbers = {"stock buckets with their marker": stock_marked, "build buckets equal to stock": len(same),
               "control buckets equal to stock": len(ctl_same),
               "build bucket 0 first word": f"{_w2f(b[0][0]) if ok else None}"}
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
