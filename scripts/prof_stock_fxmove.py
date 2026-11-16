"""Can a stock send FX's DDR state move to L1, word for word? (measuring and proof only; opt-stock item 1)

The chorus keeps its state at DDR 0x80459388 (R4 = the base, from the immediates at sw 0x1c168f in the FX init and
sw 0x1c1bd5 in the FX bus) and the unpack writes its parameters at base + 0x1340 (sw 0x1c2976). The delay's state ends
next to it and READS the chorus's first 0x24 bytes (opt-stock README 2.1). This runs the stock image over the
stockout step's frames (random FX and machine parameters, trigs, silence) twice:

1. **trace**: every read and write of 0x80459000..0x8045b000 by function, and every write to the shared words
   0x80459388..0x804593b0 after init (if the chorus writes them at run time, the delay must see that);
2. **moved**: the same frames with the chorus's block copied to L1 TO before the first block, and R4 (after sw
   0x1c1bd5) and I3 (after sw 0x1c2976) re-pointed there each block; the shared words also stay in DDR as they were.
   After every block: the outputs of sharc_stockout_step equal word for word, all of stock's L1 state equal, the moved
   block equal to the control's DDR block, and no access to the old block but the delay's reads of the shared words.

    bench_ns112.sh TREE python scripts/prof_stock_fxmove.py --image IMG --digikit DK [--blocks 16] [--to 0x308000]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_hotspots as H                                   # noqa: E402
import sharc_stockout_step as SO                                  # noqa: E402

M5, fx, m2, m4 = H.M5, H.fx, H.m2, H.m4
BASE, SPAN = 0x80459388, 0x1348                  # the chorus's words: base .. the unpack's last (0x8045a6c8) + 4
SHARED = (0x80459388, 0x804593B0)                # read by the delay too
WATCH = (0x80459000, 0x8045B000)
R4_AFTER, I3_AFTER = 0x1C1BD8, 0x1C2979          # the instructions after the two immediates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=16)
    ap.add_argument("--to", type=lambda s: int(s, 0), default=0x308000)
    ap.add_argument("--seed", type=int, default=12)
    ap.add_argument("--out", default="out/stock/fxmove.json")
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    B.undo()                                     # our own access wrapper below instead
    conc = sys.modules["sharc_core.memory"]._concrete_address
    cur = {"pc": 0, "on": False, "moved": False}
    trace = collections.defaultdict(lambda: [0, 0, 1 << 40, 0])    # (fn-ish pc, kind) -> n, ..., lo, hi
    old_hits = collections.Counter()
    shared_writes = []
    orig_r, orig_w = fx._dm_read, fx._dm_write

    def note(address, kind):
        ad = conc(address)
        if ad is None or not cur["on"]:
            return
        if WATCH[0] <= ad < WATCH[1]:
            t = trace[(cur["pc"], kind, cur["moved"])]
            t[0] += 1
            t[2], t[3] = min(t[2], ad), max(t[3], ad)
            if cur["moved"] and BASE <= ad < BASE + SPAN and not (kind == "r" and SHARED[0] <= ad < SHARED[1]):
                old_hits[(cur["pc"], kind)] += 1
            if kind == "w" and SHARED[0] <= ad < SHARED[1]:
                shared_writes.append((cur["pc"], ad, cur["moved"]))

    def rd(state, address, width, *x, **k):
        note(address, "r")
        return orig_r(state, address, width, *x, **k)

    def wr(state, address, width, value):
        note(address, "w")
        return orig_w(state, address, width, value)
    for m in list(sys.modules.values()):
        for name, new, o in (("_dm_read", rd, orig_r), ("_dm_write", wr, orig_w)):
            if getattr(m, name, None) is o:
                setattr(m, name, new)

    class Last(list):
        def append(self, pc):
            cur["pc"] = pc

    fb = SO.scenario(B.sound, B.machines, a.seed, a.blocks, globals_random=True, silence=(a.blocks // 2, a.blocks - 3))

    def run(moved):
        state, caps, reply = B.init, [], {}
        cur["moved"] = moved
        if moved:
            for k in range(0, SPAN, 4):
                m2.poke(state.state, a.to + k, m2.word(state.state, BASE + k) or 0)

        def set_r4(r):
            r.state.uregs[fx.UREG_CODES["R4"]] = fx.Const(a.to)

        def set_i3(r):
            i3 = m2.word_reg(r, "I3")
            r.state.uregs[fx.UREG_CODES["I3"]] = fx.Const(i3 - BASE + a.to)

        def at_out(r):
            reply["at"] = m2.word_reg(r, "R12")
        for b in range(a.blocks):
            hooks = {SO.OUTPUT_CALL_SW: at_out}
            if moved:
                hooks.update({R4_AFTER: set_r4, I3_AFTER: set_i3})
            r = m4.unpack_call(state, fb(b))
            f = M5.fixups(hooks)
            f.last = Last()
            cur["on"] = True
            res = fx.run(r, 40_000_000, f)
            cur["on"] = False
            if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
                return caps, f"block {b}: {res[:2]}"
            st = r.state
            o = SO.outputs(m2, st, reply.get("at"))
            o["state"] = tuple((m2.word(st, x) or 0) & 0xFFFFFFFF for x in range(*SO.STATE_L1, 4))
            o["chorus"] = tuple((m2.word(st, (a.to if moved else BASE) + k) or 0) & 0xFFFFFFFF for k in range(0, SPAN, 4))
            caps.append(o)
            state = r
        return caps, None

    ctl, h1 = run(False)
    mov, h2 = run(True)
    res = {"halts": [h1, h2]}
    if not h1 and not h2:
        diff = collections.defaultdict(list)
        for b, (x, y) in enumerate(zip(ctl, mov)):
            for k in x:
                if x[k] != y[k]:
                    n = sum(1 for p, q in zip(x[k], y[k]) if p != q) if x[k] and y[k] else -1
                    diff[k].append((b, n))
        res["differing"] = dict(diff)
    sounding = any(any(w & 0x7FFFFFFF for w in c["FX returns"]) for c in ctl)
    res["control FX returns not silent"] = sounding
    res["old block accessed in the moved run (pc, kind): n"] = {f"{p:#x} {k}": n for (p, k), n in old_hits.items()}
    res["writes to the shared words (pc, address, moved)"] = sorted({(f"{p:#x}", f"{ad:#x}", mv) for p, ad, mv in shared_writes})
    res["accesses by pc (control)"] = {f"{p:#x} {k}": [n, f"{lo:#x}", f"{hi:#x}"]
                                       for (p, k, mv), (n, _, lo, hi) in sorted(trace.items()) if not mv}
    res["ok"] = (not h1 and not h2 and not res["differing"] and not old_hits and sounding)
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "accesses by pc (control)"}, indent=1))
    print("OK" if res["ok"] else "NOT OK")


if __name__ == "__main__":
    main()
