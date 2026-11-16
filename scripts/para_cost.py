"""PARA's cost per slot, by scripts/dsp_cost.py's method (cost = instructions + 4 L2 + 10 DDR, the model's own count),
on test/test_a2_para.py's harness (copied: the farm's python has no pytest): N slots of ANALOG 2 on track 0 at its defaults, notes on at block 1
and held, PARA OFF vs PARA = N - 1. Each slot's voice() is measured on its own; the PARA pass once a block.

    python3 scripts/para_cost.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
DC = PARA = PP = None                                    # dsp_cost, the PARA module, perc.program (main() imports them)
BUFS = 0x00310000                                        # slot u's 48 kHz buffer (test/test_a2_para.py's harness)


def _imports() -> None:
    """the model's modules, after sys.path (a function: the imports stay at a module's top elsewhere)"""
    global DC, PARA, PP
    import dsp_cost
    from dnfw.engines.analog2 import para
    from dnfw.perc import program
    DC, PARA, PP = dsp_cost, para, program


def _route(h, u: int, track: int) -> None:
    from dnfw.md import voice as MDV
    a = MDV.ROUTE + 4 * (u >> 1)
    w = h.mem.get(a)
    h.mem.put(a, (w & 0xFFFF) | (track << 16) if u & 1 else (w & 0xFFFF0000) | track)


def setup(slots, para: int, engine: str = "ANALOG2"):
    """test/test_a2_para.setup: SLOTS on ENGINE (ANALOG2, JUNO) at its defaults, on track 0, PARA PARA"""
    from dnfw.engines.analog2 import analog2 as A2
    from dnfw.engines.juno import juno as J
    from dnfw.md import core as MDK
    from dnfw.mnm import machines as MM
    from dnfw.perc import live as PL
    from dnfw.perc import machines as PM
    from dnfw.perc.dsl import bits
    kind = next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == engine)
    mod = {"ANALOG2": A2, "JUNO": J}[engine]
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):
        h.words[h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = bits(v)
    for u in slots:
        h.t = u
        h.set_mnm(kind, list(mod.DEFAULTS))
        for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, mod.DEFAULTS2):
            h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
        h._half(PM.frame_offset(PARA.PARA_REC[1]), para << 8)
        _route(h, u, 0)
    h.t = 0
    return h


NOTES = [60.0, 64.0, 67.0, 71.0, 74.0, 77.0, 81.0, 84.0]   # (2026-11-15: up to 8)
BLOCKS, STEADY = 10, (4, 5, 6, 7)


def tot(c: dict) -> float:
    return DC.est([sum(v[i] for v in c.values()) for i in range(3)])


def run(n: int, para: int, engine: str = "ANALOG2") -> dict:
    slots = list(range(n))
    from dnfw.perc.dsl import Prog, bits
    h = setup(slots, para, engine)
    L = h.L
    per = {u: [] for u in slots}
    pre = []
    roles = {}
    for b in range(BLOCKS):
        for u in slots:
            h.mem.put(PP.NOTE_CELLS + 4 * u, bits(NOTES[u]))
            h.mem.put(PP.BUFFERS + 4 * u, BUFS + 0x100 * u)
        on = sum(1 << u for u in slots) if b == 1 else 0
        h.mem.put(PP.TRIG_WORD, (h.mem.get(PP.TRIG_WORD) & 0xFFFF) | (on << 16))
        w = h.mem.get(PARA.PM.FRAME + PARA.NOTE_OFF)
        h.mem.put(PARA.PM.FRAME + PARA.NOTE_OFF, w & 0xFFFF0000)
        h.mem.put(L.C["mcost"], 0)

        # the PARA pass alone (mnm_ages runs outside the count: it is the loop's, measured once in dsp_cost)
        DC.CNT.c.clear()
        DC.ZS.clear()
        DC.CNT.on = False
        p = Prog("run", mem=h.mem)
        p.spill = L.md.C["ash"]
        PP.mnm_ages(p, L)
        s0 = p.steps
        PP.para_prepass(p, L)
        pre.append(p.steps - s0)
        order = [h.mem.get(L.md.mnm.scratch + PP.ORDER_OFF + 4 * k) for k in range(16)]
        for u in order:
            if u in slots:
                c = DC._measure(lambda u=u: DC._first_prog(lambda: PP.run_voice(L, None, u, mem=h.mem)))
                per[u].append(tot(c))
        roles = {u: h.mem.get(PARA.ROLE + 4 * u) >> PARA.ROLE_SHIFT for u in slots}
    return {"start": {u: max(per[u][1], per[u][2]) for u in slots},
            "steady": {u: sum(per[u][b] for b in STEADY) / len(STEADY) for u in slots},
            "prepass_steps": {"start": max(pre[1], pre[2]), "steady": sum(pre[b] for b in STEADY) / len(STEADY)},
            "roles": roles}



def table_costs(engine: str = "ANALOG2") -> dict:
    """the load table's PARA costs (scripts/gen_load_table.py, dnfw.load: a voice's cost is (its dearer block +
    PER_VOICE) x (1 + MARGIN)), from a 4-note chord's start blocks against four voices with PARA off (the caller has
    run dsp_cost._install):
      member:  a note joining a held chord (a member's voice);
      add:     what each member adds to its leader's block and to the PARA pass;
      dropped: a note past the chord's N (not rendered: only its guard and quiet test)"""
    _imports()
    from dnfw import load as LD
    on, off = run(4, PARA.ON_VALUE, engine), run(4, 0, engine)
    member = max(on["start"][u] for u in (0, 1, 2))
    lead_extra = on["start"][3] - max(off["start"].values())
    pass_extra = on["prepass_steps"]["start"] - off["prepass_steps"]["start"]
    m = 1 + LD.MARGIN
    return {"member": round((member + LD.PER_VOICE) * m), "add": round((lead_extra + pass_extra) / 3 * m),
            "dropped": round(LD.PER_VOICE * m)}


LEVEL_BLOCKS, LEVEL_FROM = 120, 20             # the level runs: blocks, and the held part measured (from this block)


def level(n: int, para: int, engine: str = "ANALOG2") -> dict:
    """2026-11-15 (the User: "Up to 8"): N notes held on track 0's slots 0..N-1 (NOTES), PARA PARA: every slot's 48 kHz
    output over blocks LEVEL_FROM.. summed (the track's sound before the DN2's own chain): its peak, its RMS, and how
    many samples reach the output guard's limit (perc.program.OUT_LIMIT, which clamps)"""
    import math
    from dnfw.perc.dsl import Prog, bits, flt
    slots = list(range(n))
    h = setup(slots, para, engine)
    L = h.L
    mix = []
    for b in range(LEVEL_BLOCKS):
        for u in slots:
            h.mem.put(PP.NOTE_CELLS + 4 * u, bits(NOTES[u]))
            h.mem.put(PP.BUFFERS + 4 * u, BUFS + 0x100 * u)
        on = sum(1 << u for u in slots) if b == 1 else 0
        h.mem.put(PP.TRIG_WORD, (h.mem.get(PP.TRIG_WORD) & 0xFFFF) | (on << 16))
        w = h.mem.get(PARA.PM.FRAME + PARA.NOTE_OFF)
        h.mem.put(PARA.PM.FRAME + PARA.NOTE_OFF, w & 0xFFFF0000)
        h.mem.put(L.C["mcost"], 0)
        p = Prog("run", mem=h.mem)
        p.spill = L.md.C["ash"]
        PP.mnm_ages(p, L)
        PP.para_prepass(p, L)
        for u in [h.mem.get(L.md.mnm.scratch + PP.ORDER_OFF + 4 * k) for k in range(16)]:
            if u in slots:
                PP.run_voice(L, None, u, mem=h.mem)
        if b >= LEVEL_FROM:
            mix += [sum(flt(h.mem.get(BUFS + 0x100 * u + 4 * k)) for u in slots) for k in range(32)]
    peak = max(abs(x) for x in mix)
    rms = math.sqrt(sum(x * x for x in mix) / len(mix))
    return {"peak": round(peak, 4), "rms": round(rms, 4),
            "at_guard": sum(1 for x in mix if abs(x) >= PP.OUT_LIMIT), "guard": PP.OUT_LIMIT}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--level", action="store_true", help="the 1..8 note chords' level (PARA ON and OFF), not the cost")
    a = ap.parse_args()
    _imports()
    if a.level:
        out = {}
        for engine in ("ANALOG2", "JUNO"):
            for n in range(1, 9):
                for para in ((0,) if n == 1 else (0, PARA.ON_VALUE)):
                    r = level(n, para, engine)
                    out[f"{engine}_n{n}_para{para}"] = r
                    print(f"{engine} {n} notes PARA {para}: peak {r['peak']}  rms {r['rms']}  at the guard "
                          f"{r['at_guard']} (+-{r['guard']})", flush=True)
        if a.json:
            pathlib.Path(a.json).write_text(json.dumps(out, indent=1))
        return 0
    DC._install()
    out = {}
    for engine, n in ((e, n) for e in ("ANALOG2", "JUNO") for n in range(1, 9)):
        for para in ((0,) if n == 1 else (0, PARA.ON_VALUE)):
            r = run(n, para, engine)
            out[f"{engine}_n{n}_para{para}"] = r
            st, sd = r["start"], r["steady"]
            print(f"{engine} {n} notes PARA {para}: roles {r['roles']}  steady {[round(sd[u]) for u in sorted(sd)]} "
                  f"(sum {round(sum(sd.values()))})  start {[round(st[u]) for u in sorted(st)]} "
                  f"(sum {round(sum(st.values()))})  pass {r['prepass_steps']}", flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
