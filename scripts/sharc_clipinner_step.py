"""The SHARC runner's clipinner step (2026-11-20, clip-inner; the User: "NO DIGITAL CLIPPING. how clear can i make
that?", "a synth with no effect on should not digitally clip and if it does, i want the alert"; test/test_clipinner.py
for the parts, docs/mixmeter.md).

A voice's own clip on the DSP's real code: track 0 on DRONE, note 60 at block 1, blocks run with the engine's own
output stage at work (sharc_waverider_m5.run_blocks), and after each block the guard's CLIPMASK and the packet tdm_tx
left in TDM slots 14..15 (unit 0, unit 1).

- the User's track 5 (2026-11-20, its DRONE's knob words as the DN2's live frame held them: BEAT 81, CHAR 40, ...):
  until 2026-11-21 its knee squashed the sound past 1 dB here; the knee is gone (the User: "just make it quieter! not a
  limiter"), so now no clip packet, CLIPMASK 0 throughout; likewise DPRO-DDRW at its defaults (it clipped in its MIX
  stage until its gain came down, 2026-11-21);
- DPRO-DENS with every knob at 127 (its decimator's limiter holds its output stream at the rails): a clip packet
  (CLIP_MAGIC) with slot 0's bit, CLIPMASK cleared by it, never two clip packets in a row, the idle packet between;
- DRONE at its own start (the machine's defaults) and silence: no clip packet, CLIPMASK 0 throughout (a clean sound
  lights nothing).
"""

from __future__ import annotations

from dnfw.perc import guard as G
from dnfw.sampler import machines as SM

BLOCKS = 240
SHORT = 60                          # DDRW's and DENS' runs (each clipped from its first blocks)
TX_BASE, TX_PAGE_WORD = SM.TDM_TX, SM.TDM_PAGE
ROUTE = 0xA5A                       # the frame's voice slot -> track halfwords
# the DN2's live frame, 2026-11-20 (track 5, DRONE): page 1 (SPRD CPL TOPO CHAR DRFT TONE BEAT DTUN) and page 2 (GLID
# GLTY OCT - - - HOLD) as frame words on PERC's records
USER_T5 = ((0x1D4B, 0x0400, 0x1500, 0x2800, 0x2900, 0x2400, 0x5100, 0x2900),
           (0x0000, 0x4B00, 0x3200, 0x0000, 0x0000, 0x0100, 0x2000))


def _frames(M5, sound, machines, words1=None, words2=None, trig_at=1, silent=False, name="DRONE", knobs=None):
    from dnfw.mnm import machines as MM
    from dnfw.perc import machines as PM
    k = MM.NAMES.index(name)
    over = M5.mnm_words(k, knobs)
    if words1:
        over.update({slot: w for (_r, slot, _lo, _top), w in zip(PM.PARAMS, words1)})

    def fb(b):
        f = M5.base_frame(sound, machines, t0=MM.TYPES[k], overrides=over, note=0x3C00,
                          trigger=(b == trig_at and not silent))
        if words2:
            for (_r, slot, _lo, _top), w in zip(PM.FX_PARAMS, words2):
                f.param(0, slot, w)
        for t in range(16):
            f.put(ROUTE + 2 * t, t)
        return f.to_bytes()
    return fb


def _packet(m2, st) -> tuple[int, int]:
    page = TX_BASE + (((m2.word(st, TX_PAGE_WORD) or 0) & 1) << 11)

    def unit(i):
        w = m2.word(st, page + 4 * (16 * (i >> 1) + 14 + (i & 1))) or 0
        return (w >> 8) & 0xFFFF if (w >> 24) == SM.TDM_TAG else w & 0xFFFF
    return unit(0), unit(1)


def run_one(M5, snap, m2mach, m5img, frames, blocks: int = BLOCKS) -> dict:
    m2 = M5.m2
    state = M5.init_on(snap, m2mach, m5img, warm=True)
    m2.poke(state.state, G.CLIPMASK, 0)          # (as the DSP's words are after its first idle packet)
    m2.poke(state.state, G.CLIP_HIT, 0)
    rows, halt = [], None
    for b in range(blocks):
        res = M5.run_blocks(state, lambda _b, b=b: frames(b), 1)
        if not res.get("ok"):
            halt = f"block {b}: {res.get('halt')}"
            break
        state = res["state"]
        st = state.state
        u0, u1 = _packet(m2, st)
        rows.append({"b": b, "u0": u0, "u1": u1, "mask": (m2.word(st, G.CLIPMASK) or 0) & 0xFFFF,
                     "peak": max((abs(x) for blk in res["perc"] for v in blk.values() for x in v["out"]), default=0.0),
                     "differ": sum(v["out_mismatches"] + v["state_mismatches"] for blk in res["perc"] for v in blk.values())})
    return {"rows": rows, "halt": halt}


def run(M5, snap, m2mach, m5img, sound, machines) -> dict:
    checks, numbers = {}, {}
    runs = {"user_t5": (_frames(M5, sound, machines, *USER_T5), BLOCKS),
            "drone_start": (_frames(M5, sound, machines), BLOCKS),
            "silence": (_frames(M5, sound, machines, silent=True), BLOCKS),
            "ddrw_start": (_frames(M5, sound, machines, name="DPRO-DDRW"), SHORT),
            "dens_127": (_frames(M5, sound, machines, name="DPRO-DENS", knobs=[127] * 8), SHORT)}
    out = {}
    for name, (fb, n) in runs.items():
        out[name] = run_one(M5, snap, m2mach, m5img, fb, n)
        r = out[name]["rows"]
        clips = [x["b"] for x in r if x["u0"] == SM.CLIP_MAGIC]
        numbers[name] = {"blocks": len(r), "halt": out[name]["halt"], "clip_packets": len(clips),
                         "first_clip_block": clips[0] if clips else None,
                         "slots": sorted({s for x in r if x["u0"] == SM.CLIP_MAGIC for s in range(16) if x["u1"] >> s & 1}),
                         "peak": round(max((x["peak"] for x in r), default=0.0), 4)}
    for name, (_fb, n) in runs.items():
        checks[f"{name}: every block runs, the voice bit-exact to the model"] = (
            out[name]["halt"] is None and len(out[name]["rows"]) == n
            and all(x["differ"] == 0 for x in out[name]["rows"]))
    u = out["dens_127"]["rows"]
    cp = [x for x in u if x["u0"] == SM.CLIP_MAGIC]
    checks["DPRO-DENS at all 127: a clip packet with slot 0's bit (its decimator's limiter)"] = (
        bool(cp) and all(x["u1"] == 1 for x in cp))
    checks["... each clip packet clears CLIPMASK, never two in a row, an idle packet between"] = all(
        x["mask"] == 0 for x in cp) and all(not (a["u0"] == SM.CLIP_MAGIC and b["u0"] == SM.CLIP_MAGIC)
                                            for a, b in zip(u, u[1:])) and all(
        x["u0"] in (SM.CLIP_MAGIC, SM.POS_MAGIC) for x in u)
    for name in ("user_t5", "ddrw_start", "drone_start", "silence"):
        r = out[name]["rows"]
        checks[f"{name}: no clip packet, CLIPMASK 0 throughout (a clean sound lights nothing)"] = all(
            x["u0"] != SM.CLIP_MAGIC and x["mask"] == 0 for x in r)
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}
