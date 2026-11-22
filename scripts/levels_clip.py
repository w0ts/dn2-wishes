"""How hot each machine runs against each output's clip point (2026-11-21, docs/levels-clip.md; the User: "are our
engines designed too hot?").  Measurement only: the SHARC runner on the tree's own DSP; no engine or trim changed.

Track 0, one machine, its default sound; a note (or a 4-note chord: four voice slots, all routed to track 0 as the
frame's route words are zero), note on at block 1, BLOCKS blocks, one runner call a block so the outputs can be read
after each block.  Scenario: track LEVEL (frame header 116), AMP VOL (slot 90), VEL (slot 62, our types; -1 = the
init sound's own).  Per case, the largest |x| over the blocks of

  perc_out          PERC's output words (our Monomachine / Machinedrum / PLAITS machines), before the stock chain
  amp_in / amp_out  track 0's buffer at the amp stage's input / output (the runner's taps)
  voice             the voice blocks at the routing's entry, summed over the slots (the track's channel), L and R
  bus               the main bus 0x25bb68 at the master mix's call
  mix               the main mix MIX_BUF after the block (after the master chain)
  tx                TDM TX words after the block (both pages): slots 0/1 Overbridge main, 2/3 track 1's own channel,
                    the largest |word| / 2^31 and the number of saturated words (0x7fffffff / 0x80000000)

    python scripts/levels_clip.py --image STOCK.syx --scen L100V100 [--only SUBSTR] [--shard I/N] [--out F.json]
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, "scripts")
sys.path.insert(0, "src")
import sharc_levels_step as LV                      # noqa: E402
import sharc_waverider_m5 as M                      # noqa: E402
from dnfw.engines.plaits import plaits as PLT       # noqa: E402
from dnfw.mnm import machines as MM                 # noqa: E402
from dnfw.perc import machines as PM                # noqa: E402
from dnfw.sampler import machines as SM             # noqa: E402
from dnfw.waverider import frame as FR              # noqa: E402

VOL_SLOT, VEL_SLOT = 90, PM.VEL_SLOT
NOTES = (0x3C00, 0x4000, 0x4300, 0x4800)            # C4 E4 G4 C5
SCENARIOS = {"L100V100": (100, 100, -1), "KIT": (100, -1, -1), "MAX": (127, 127, 127)}
STOCK = {0: "FM TONE", 1: "WAVETONE", 2: "FM DRUM", 3: "SWARMER"}
SYNTHS = ("JUNO", "TB303", "DPRO-DENS", "DPRO-WAVE", "ANALOG2", "DRONE", "VO-6", "SID 6581", "SOPHIE")
PLAITS_MODELS = ("VA", "WS", "FM", "STRG", "MDAL", "BD")
MD = ("TRX-BD", "TRX-SD", "EFM-BD", "EFM-SD", "PI-BD", "PI-SD")
SAT = (0x7FFFFFFF, 0x80000000)


def cases() -> list[dict]:
    out: list[dict] = []
    for t, name in STOCK.items():
        for n in ((1, 4) if t in (0, 1, 3) else (1,)):
            out.append({"name": f"stock {name}", "type": t, "spec": None, "ours": False, "voices": n})
    for name in SYNTHS:
        if name in MM.NAMES:
            k = MM.NAMES.index(name)
            for n in (1, 4):
                out.append({"name": name, "type": MM.TYPES[k], "spec": ("mnm", k), "ours": True, "voices": n})
    pk = MM.NAMES.index("PLAITS")
    for model in PLAITS_MODELS:
        if model in PLT.MODELS:
            out.append({"name": f"PLAITS {model}", "type": MM.TYPES[pk], "spec": ("plaits", pk, model), "ours": True,
                        "voices": 1})
    for name in MD:
        if name in PM.NAMES:
            out.append({"name": f"MD {name}", "type": 5, "spec": ("perc", PM.NAMES.index(name)), "ours": True,
                        "voices": 1})
    out.append({"name": "SMP ONESHOT", "type": SM.TYPE_OF["ONESHOT"], "spec": ("smp",), "ours": True, "voices": 1})
    return out


def words_of(spec, machines, typ) -> dict:
    if spec is None:
        return dict(machines.get(typ, {}))
    if spec[0] == "mnm":
        return M.mnm_words(spec[1], None)
    if spec[0] == "plaits":
        knobs = list(MM.DEFAULTS["PLAITS"])
        knobs[PLT.MODL_K] = PLT.knob_of(PLT.MODELS.index(spec[2]))
        return M.mnm_words(spec[1], knobs)
    if spec[0] == "perc":
        return M.perc_words(spec[1])
    if spec[0] == "smp":
        return M.smp_words()
    raise ValueError(spec)


def maxabs(xs) -> tuple[float, int]:
    nan = sum(1 for x in xs if x != x)
    return max((abs(x) for x in xs if x == x), default=0.0), nan


def run_case(init, sound, machines, c: dict, blocks: int, level: int, vol: int, vel: int) -> dict:
    m2 = M.m2
    typ, n, ours = c["type"], c["voices"], c["ours"]
    words = words_of(c["spec"], machines, typ)
    seen = {"voice": 0.0, "bus": 0.0, "mix": 0.0, "nan": 0, "amp_in": 0.0, "amp_out": 0.0,
            "tx": {k: 0.0 for k in range(4)}, "sat": {k: 0 for k in range(4)}, "voice_blocks": [], "perc_out": 0.0}
    used = {}

    def at_routing(r):
        st = r.state
        L = [sum(LV.bf(m2.word(st, LV.VOICES + 0x100 * s + 4 * j)) for s in range(n)) for j in range(32)]
        R = [sum(LV.bf(m2.word(st, LV.VOICES + 0x100 * s + 0x80 + 4 * j)) for s in range(n)) for j in range(32)]
        p, nan = maxabs(L + R)
        seen["voice"], seen["nan"] = max(seen["voice"], p), seen["nan"] + nan
        seen["voice_blocks"].append(round(p, 6))

    def at_master(r):
        p, nan = maxabs([LV.bf(m2.word(r.state, LV.MAIN_BUS + 4 * j)) for j in range(64)])
        seen["bus"], seen["nan"] = max(seen["bus"], p), seen["nan"] + nan

    state = init
    for b in range(blocks):
        def fb(_b, b=b):
            f = M.base_frame(sound, machines, t0=typ, overrides=words, trigger=False,
                             others={t: typ for t in range(1, n)} if n > 1 else None)
            f.put(LV.SRC_FLAG, 1)                                    # Overbridge's track channels from A
            for t in range(n):
                for slot, w in words.items():
                    f.param(t, slot, w)
                f.header(FR.NOTE, t, NOTES[t] if n > 1 else NOTES[0])
                f.header(FR.LEVEL, t, level << 8)
                if vol >= 0:
                    f.param(t, VOL_SLOT, vol << 8)
                if ours and vel >= 0:
                    f.param(t, VEL_SLOT, vel << 8)
                if b == 1:
                    f.trigger(t)
            if not used:
                used.update({"level": f.get(FR.header_offset(FR.LEVEL, 0)) >> 8,
                             "vol": f.get(FR.slot_offset(0, VOL_SLOT)) >> 8,
                             "vel": f.get(FR.slot_offset(0, VEL_SLOT)) >> 8})
            return f.to_bytes()
        rr = M.run_blocks(state, fb, 1, extra_hooks={LV.ROUTING_SW: at_routing, LV.MASTER_CALL_SW: at_master})
        if not rr["ok"]:
            return {"ok": False, "halt": str(rr.get("halt")), "block": b}
        state = rr["state"]
        st = state.state
        p, nan = maxabs(rr["amp_in"])
        seen["amp_in"] = max(seen["amp_in"], p)
        p, nan2 = maxabs(rr["amp_out"])
        seen["amp_out"], seen["nan"] = max(seen["amp_out"], p), seen["nan"] + nan + nan2
        for blk in rr.get("perc", []):
            for v in blk.values():
                seen["perc_out"] = max(seen["perc_out"], maxabs(v.get("out", []))[0])
        p, nan = maxabs([LV.bf(m2.word(st, LV.MIX + 4 * j)) for j in range(64)])
        seen["mix"], seen["nan"] = max(seen["mix"], p), seen["nan"] + nan
        for pg in (0, 1):
            page = LV.TX_BASE + (pg << 11)
            for s in range(4):
                ws = [(m2.word(st, page + 64 * fr + 4 * s) or 0) & 0xFFFFFFFF for fr in range(32)]
                seen["tx"][s] = max(seen["tx"][s], max(abs(LV.s32(w)) for w in ws) / 2.0 ** 31)
                seen["sat"][s] += sum(1 for w in ws if w in SAT)
    return {"ok": True, **seen, "used": used, "blocks": blocks}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=pathlib.Path)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path("/mnt/d/01_Code/Z_Personal/digikit-wt-sharcemu"))
    p.add_argument("--scen", default="L100V100", choices=sorted(SCENARIOS))
    p.add_argument("--only", default="")
    p.add_argument("--shard", default="0/1")
    p.add_argument("--blocks", type=int, default=80)
    p.add_argument("--out", type=pathlib.Path)
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    level, vol, vel = SCENARIOS[a.scen]
    cs = [c for c in cases() if a.only in f"{c['name']} x{c['voices']}"]
    i, n = map(int, a.shard.split("/"))
    cs = cs[i::n]
    if a.list:
        for c in cs:
            print(f"{c['name']} x{c['voices']} type {c['type']}")
        return 0
    dk = M.m1.Digikit(a.digikit)
    M.fx.bind(str(a.digikit / "tools"))
    M.m4.IMAGE = a.image
    stock = M.m1.dn2_section7(a.image)
    sound, machines = M.m4.init_sound(a.image)
    results = []
    with tempfile.TemporaryDirectory(dir=M.OUT) as tmp:
        snap, m2mach = M.snapshot_path(dk, stock, pathlib.Path(tmp))
        img = M.Image(dk, M.dsp.section7(stock))
        for c in cs:
            t0 = time.perf_counter()
            init = M.init_on(snap, m2mach, M.Image(dk, img.stream), warm=True)
            r = run_case(init, sound, machines, c, a.blocks, level, vol, vel)
            r.update({"name": c["name"], "voices": c["voices"], "scen": a.scen,
                      "secs": round(time.perf_counter() - t0)})
            print(json.dumps({k: r.get(k) for k in ("name", "voices", "scen", "ok", "voice", "bus", "mix", "tx", "sat",
                                                    "amp_out", "perc_out", "nan", "used", "secs", "halt")}), flush=True)
            results.append(r)
            if a.out:
                a.out.write_text(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
