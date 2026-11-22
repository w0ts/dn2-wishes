"""The SHARC runner's sendfx step (2026-11-14, main: "the runner's full blocks never carry signal through the send
FX"): real voices, their REV / DEL / CHO sends up, sound passing through the three send FX inside full engine blocks.

**Why the other steps never heard the sends.** The voice chain writes each voice slot's stereo block with
`I1 = MODIFY(I0, M4)`, M4 = 0x257ee8 + 0x100 s. Until the runner's G13 (2026-11-14) the emulator scaled that modifier
by 4 and put the block at 0x95fba0 + 0x400 s, so the sends summed zeros and the FX returns stayed 0; this step's
first version (claude/sendfx e4fe9dcb) copied the blocks across at the sends' call. With G13 (and G12's odd-slot
latch, G16's SIMD shift on PEy) the block is where the unit has it and nothing is copied: the sends' levels, the
three FX, their returns and the main mix are the image's own code on the frame's own words.

Per block, at each FX's call (chorus sw 0x1c1be1, delay 0x1c1c58, reverb 0x1c1d11) the input pair the bus's I/O
descriptor (0x257e6c + 4) points to, at its return (0x1c1be8, 0x1c1c5f, 0x1c1d18) the output pair (+ 0xc), and at
the output stage's call (sw 0x1c307b) the main mix (0x268438) and the FX return area (0x25b068..0x25b868): words as
bit patterns (NaN included).

1. **stock**: one voice, WAVETONE on track 0, every send at 0x7f00, the FX types on stock values, the kit's FX and
   master words random (stock-valid), a note every 12 blocks. (One voice: the runner sets up voice slot 0's chain
   only; a stock voice on another slot reads NaN in its stereo block, measured 2026-11-14 on 1.12.) The build's run and the stock image's
   are bit-identical, every block, every word above. Each FX's wet sounds (its output above FLOOR in at least
   MIN_SOUNDING blocks) and stays finite and below CEILING.
2. **ours**: one voice, PI-SD on track 0, every send up, the send FX on the build's own
   types (reverb FDN8, delay XDLY: the routing knobs on 0; chorus JUNO: the send pages' TYPE word), enough blocks for
   FDN8's wet (its 31 clearing blocks and its delay lines). Stock has no such FX, so the reference is a recorded run
   of a reference build (`sharc_sendfx_ref.json`, keyed by the stock image's section 7): per block, the digests of
   every word above. The same floor and ceiling.
3. **control**: one bit of the reverb's output in one block of the build's stock run, flipped as it returns: the
   comparison must see it (the captures are read from the memory the FX wrote, and the comparison reads them).

`SENDFX_RECORD=1` writes this run's scenario 2 digests into `sharc_sendfx_ref.json` (for the reference build only;
a changed reference is a declared sound change and goes to main first). The step then fails, so a recording run never
clears a build. `SENDFX_ONLY=stock|ours|control` runs one scenario (while a step is built).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import random
import struct

from dnfw.inserts import design as D
from dnfw.waverider import dsp
from dnfw.waverider import frame as FR

HERE = pathlib.Path(__file__).resolve().parent
REF_FILE = HERE / "sharc_sendfx_ref.json"

SENDS_SW = dsp.SENDS_SITE_SW                     # the engine's call of the sends: copy the voices' stereo here
FX_SITES = {"chorus": (dsp.CHORUS_SITE_SW, 0x1C1BE8), "delay": (dsp.DELAY_SITE_SW, 0x1C1C5F),
            "reverb": (dsp.REVERB_SITE_SW, 0x1C1D18)}
IO = 0x257E6C                                    # the bus's I/O descriptor: + 4 {in L, in R}, + 0xc {out L, out R}
OUTPUT_CALL_SW = 0x1C307B
MAIN = (0x268438, 64)
FX_RETURNS = (0x25B068, 0x800 // 4)
SEND_SLOTS = (86, 87, 88)                        # the three per-track FX sends (mirror slots 88 / 86 / 87)
FRAME_COPY = 0x25C48C
FX_TYPE_OFFSETS = (0x25CEB4 - FRAME_COPY, 0x25CEA4 - FRAME_COPY)    # k 48 (reverb), k 40 (delay): 0 = ours
TAIL_FREE = list(range(FR.SLOT_BASE + FR.SLOT_STRIDE * FR.TRACKS, 0xA5A, 2))
FLOOR, CEILING, MIN_SOUNDING = 1e-4, 16.0, 8
# 2026-11-16: the stock delay starts at its snapshot length (18,744 samples, state + 0x400104) and eases toward its TIME
# by ~0.3 % a block (measured: 18,744 at block 0, 15,699 at block 55, TIME 0), so its first repeat would come near
# block 240, past this scenario's 96 blocks: its wet read exact zeros. Both images start the delay at DELAY_START_LEN
# (the same two words, the length and its smoothed float, poked before the delay's first call, as if the knob had settled long ago) with TIME 0, so the
# repeats come within the run.
DELAY_TIME_WORD = 0x9C8 + 2 * 32                 # frame word of kit slot 32 (dnfw.xdly.design: k 32 TIME)
DELAY_LEN = 0x8005912C + 0x400104                # the stock delay's length word (dnfw.xdly.design.STOCK_STATE + ..)
DELAY_LEN_F = 0x8005912C + 0x400240              # its smoothed length, float32, which the int follows each block
                                                 # (measured: 18,682.7 -> 18,621.6 -> 18,560.6; poking the int alone is undone)
DELAY_START_LEN = 1024
BLOCKS_STOCK, BLOCKS_OURS = 96, 176
CONTROL_BLOCK = 20
KEYS = ("chorus in", "chorus out", "delay in", "delay out", "reverb in", "reverb out", "main", "FX returns")


def f32(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def digest(words) -> str:
    return hashlib.sha256(struct.pack(f"<{len(words)}I", *words)).hexdigest()[:24]


def tail_words(seed: int, ours: bool) -> dict[int, int]:
    """the kit's FX and master words: stock-valid, away from both ends; the FX types stock (STOCK) or ours"""
    rnd = random.Random(seed)
    out = {o: rnd.randrange(0x1000, 0x6001) for o in TAIL_FREE}
    for o in FX_TYPE_OFFSETS:
        out[o] = 0 if ours else rnd.randrange(4, 0x80) << 8
    if not ours:
        out[DELAY_TIME_WORD] = 0                 # the stock delay's TIME at its shortest (with DELAY_START_LEN)
    return out


def stock_frames(M5, sound, machines, seed: int, blocks: int):
    """scenario 1: one voice, WAVETONE on track 0 (the runner sets up voice slot 0's chain only: a stock voice on
    another slot reads NaN there, measured 2026-11-14), every send up, a note every 12 blocks"""
    glob = tail_words(seed, ours=False)
    sends = {s: 0x7F00 for s in SEND_SLOTS}

    def build(b):
        f = M5.base_frame(sound, machines, t0=1, overrides=sends, trigger=b % 12 == 1)
        for o, v in glob.items():
            f.put(o, v)
        return f.to_bytes()
    frames = [build(b) for b in range(blocks)]
    return lambda b: frames[b]


def ours_frames(M5, sound, machines, seed: int, blocks: int):
    """scenario 2: one voice, PI-SD on track 0 (voice slot 0), every send up, the FX types ours, a note every 12
    blocks"""
    from dnfw.perc import machines as PM
    glob = tail_words(seed, ours=True)
    words = {**M5.perc_words(PM.NAMES.index("PI-SD")), **{s: 0x7F00 for s in SEND_SLOTS}}

    def build(b):
        f = M5.base_frame(sound, machines, t0=5, overrides=words, trigger=b % 12 == 1)
        for o, v in glob.items():
            f.put(o, v)
        return f.to_bytes()
    frames = [build(b) for b in range(blocks)]
    return lambda b: frames[b]


def run_scenario(M5, init, frames, blocks: int, *, juno: bool = False, flip_at: int | None = None,
                 delay_len: int | None = None) -> dict:
    """BLOCKS full blocks from INIT; per block the captures (KEYS -> words)"""
    m2 = M5.m2
    state, caps = init, []

    def pair(st, at):
        p = m2.word(st, at) or 0
        a_l, a_r = m2.word(st, p) or 0, m2.word(st, p + 4) or 0
        return tuple((m2.word(st, a + 4 * k) or 0) & 0xFFFFFFFF for a in (a_l, a_r) for k in range(32))

    for b in range(blocks):
        cur = {}

        def at_sends(r):
            # (2026-11-16: no copy. The runner's G13 puts the voice chain's stereo where the sends read it, as on
            # the unit; copying 0x95fba0 across, as this step did before G13, wrote zeros over the voices)
            cur["sends"] = cur.get("sends", 0) + 1

        hooks = {SENDS_SW: at_sends}
        for name, (site, back) in FX_SITES.items():
            def at_site(r, name=name):
                if name == "chorus" and juno:
                    m2.poke(r.state, D.JS_TYPE, D.JS_JUNO)      # as the ColdFire's send pages carry it
                if name == "delay" and delay_len is not None and b == 0:
                    m2.poke(r.state, DELAY_LEN, delay_len)
                    m2.poke(r.state, DELAY_LEN_F, struct.unpack("<I", struct.pack("<f", float(delay_len)))[0])
                cur[f"{name} in"] = pair(r.state, IO + 4)

            def at_back(r, name=name):
                if name == "reverb" and flip_at == b:
                    p = m2.word(r.state, IO + 12) or 0
                    a = m2.word(r.state, p) or 0
                    m2.poke(r.state, a, (m2.word(r.state, a) or 0) ^ 0x00400000)
                cur[f"{name} out"] = pair(r.state, IO + 12)
            hooks[site], hooks[back] = at_site, at_back

        def at_out(r):
            st = r.state
            cur["main"] = tuple((m2.word(st, MAIN[0] + 4 * k) or 0) & 0xFFFFFFFF for k in range(MAIN[1]))
            cur["FX returns"] = tuple((m2.word(st, FX_RETURNS[0] + 4 * k) or 0) & 0xFFFFFFFF
                                      for k in range(FX_RETURNS[1]))
        hooks[OUTPUT_CALL_SW] = at_out
        res = M5.run_blocks(state, lambda _b, b=b: frames(b), 1, extra_hooks=hooks)
        if not res.get("ok"):
            return {"caps": caps, "halt": f"block {b}: {res.get('halt')}"}
        state = res["state"]
        missing = [k for k in KEYS if k not in cur]
        if missing or cur.get("sends") != 1:
            return {"caps": caps, "halt": f"block {b}: not reached: {missing or 'the sends ' + str(cur.get('sends'))}"}
        caps.append({k: cur[k] for k in KEYS})
    return {"caps": caps, "halt": None}


def levels(caps) -> dict:
    """per FX: the blocks whose output is above FLOOR, the loudest word, every word finite and below CEILING"""
    out = {}
    for name in FX_SITES:
        peaks, bad = [], 0
        for c in caps:
            xs = [f32(w) for w in c[f"{name} out"]]
            bad += sum(1 for x in xs if not math.isfinite(x) or abs(x) >= CEILING)
            peaks.append(max((abs(x) for x in xs if math.isfinite(x)), default=0.0))
        ins = max((abs(f32(w)) for c in caps for w in c[f"{name} in"] if math.isfinite(f32(w))), default=0.0)
        out[name] = {"sounding blocks": sum(1 for p in peaks if p > FLOOR), "max": round(max(peaks, default=0.0), 6),
                     "max in": round(ins, 6), "non-finite or >= ceiling": bad,
                     "first sounding": next((b for b, p in enumerate(peaks) if p > FLOOR), None)}
    return out


def level_checks(prefix: str, lv: dict) -> dict:
    return {f"{prefix}: the {n} send's wet sounds (> {FLOOR:g} in >= {MIN_SOUNDING} blocks), finite and < {CEILING:g}":
            v["sounding blocks"] >= MIN_SOUNDING and v["non-finite or >= ceiling"] == 0 for n, v in lv.items()}


def compare(a_caps, b_caps) -> dict:
    """KEY -> the blocks where the two runs differ"""
    diff = {}
    for key in KEYS:
        bad = [b for b, (x, y) in enumerate(zip(a_caps, b_caps)) if x[key] != y[key]]
        if bad:
            diff[key] = bad
    return diff


def digests(caps) -> list[dict]:
    return [{k: digest(c[k]) for k in KEYS} for c in caps]


def run(M5, snap, m2mach, m5img, stockimg, sound, machines) -> dict:
    from dnfw.waverider import stockfx
    # DELAY_LEN is the stock delay's DDR control word; with opt-stock's move on, the build keeps it in L2 elsewhere
    assert not stockfx.ENABLED, "sendfx pokes the stock delay's length in DDR: teach it the L2 move first"
    import sharc_stockout_step as SO
    only = os.environ.get("SENDFX_ONLY")
    checks, numbers = {}, {}

    if only in (None, "stock", "control"):
        fb = stock_frames(M5, sound, machines, 11, BLOCKS_STOCK)
        runs = {}
        for which, img in (("stock", stockimg), ("build", m5img)):
            runs[which] = run_scenario(M5, M5.init_on(snap, m2mach, SO.fresh(img)), fb, BLOCKS_STOCK,
                                       delay_len=DELAY_START_LEN)
        s, d = runs["stock"], runs["build"]
        both = s["halt"] is None and d["halt"] is None
        checks["stock: both images return every block, every FX called and returned"] = both
        diff = compare(s["caps"], d["caps"]) if both else {"halt": [s["halt"], d["halt"]]}
        lv = levels(d["caps"]) if both else {}
        if only != "control":
            checks["stock: sends' inputs, the three FX's outputs, main mix and FX returns bit-identical to stock, "
                   "every block"] = both and not diff
            checks.update(level_checks("stock", lv) if both else {"stock: levels": False})
            numbers["stock"] = {"blocks": BLOCKS_STOCK, "differing (capture: blocks)": diff, "levels": lv}
        if only in (None, "control"):
            c = run_scenario(M5, M5.init_on(snap, m2mach, SO.fresh(m5img)), fb, CONTROL_BLOCK + 2, flip_at=CONTROL_BLOCK,
                             delay_len=DELAY_START_LEN)
            cd = compare(s["caps"], c["caps"]) if both and c["halt"] is None else {}
            checks[f"control: one bit of the reverb's output flipped in block {CONTROL_BLOCK} is seen"] = (
                CONTROL_BLOCK in cd.get("reverb out", []))
            numbers["control"] = {"differing (capture: blocks)": cd, "halt": c["halt"]}

    if only in (None, "ours"):
        fb = ours_frames(M5, sound, machines, 13, BLOCKS_OURS)
        o = run_scenario(M5, M5.init_on(snap, m2mach, m5img, warm=True), fb, BLOCKS_OURS, juno=True)
        ok = o["halt"] is None
        checks["ours: the build returns every block, every FX called and returned"] = ok
        got = digests(o["caps"]) if ok else []
        lv = levels(o["caps"]) if ok else {}
        checks.update(level_checks("ours", lv) if ok else {"ours: levels": False})
        refs = json.loads(REF_FILE.read_text()) if REF_FILE.exists() else {}
        key = stockimg.sha
        if os.environ.get("SENDFX_RECORD") and ok:
            refs[key] = {"blocks": BLOCKS_OURS, "made_by": os.environ.get("SENDFX_RECORD"), "digests": got}
            REF_FILE.write_text(json.dumps(refs, indent=0) + "\n")
            checks["ours: recorded as the reference (a recording run never clears a build)"] = False
        ref = refs.get(key)
        # 2026-11-21 (in the gate): no reference recorded for this stock image -> only reported (the sound checks above
        # still hold ours); one recorded -> every block bit-identical to it
        numbers["ours: a reference is recorded for this stock image"] = ref is not None
        bad = {}
        if ref is not None and ok:
            for b, (x, y) in enumerate(zip(got, ref["digests"])):
                for k in KEYS:
                    if x[k] != y.get(k):
                        bad.setdefault(k, []).append(b)
            checks["ours: every block's captures bit-identical to the reference build's"] = (
                not bad and len(got) == len(ref["digests"]))
        numbers["ours"] = {"blocks": BLOCKS_OURS, "halt": o["halt"], "levels": lv,
                           "differing from the reference (capture: blocks)": bad,
                           "reference made by": (ref or {}).get("made_by")}
    return {"ok": bool(checks) and all(checks.values()), "checks": checks, "numbers": numbers}
