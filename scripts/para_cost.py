"""PARA's cost as one voice (2026-11-21), by scripts/dsp_cost.py's method (cost = instructions + 4 L2 + 10 DDR, the
model's own count), on test/test_a2_para.py's harness (imported: the farm's python runs it without pytest).

Since 2026-11-16 a PARA chord plays on ONE slot (docs/paraphonic-onevoice.md): the leader's own note and the joined
ones from its row (csrc/para/one.c pv_out writes it into the voice's frame words 50..61), each joined note a shadow
rendered inside the leader's voice. So this measures that one slot with 1, 2, ... 8 notes in its row, and the PARA
pass (para_prepass) a block, against the same slot with PARA OFF. Until 2026-11-21 it measured the two-voice design
(N slots, members and a leader): with one-voice PARA its ON runs had no roles and equalled the OFF runs.

Each chord: its note on at block 1 with its row (the ColdFire's order: the row rides in the note-on's frame), held.
Its cost is the dearer of the note blocks (1, 2: every shadow starts) and the steady mean (blocks 4..7), the voice
and the pass together. ANALOG 2 at its defaults and at its dearest FLT2 choice (the load table's ANALOG 2 voice), JUNO
at its defaults: the worst case is the dearest of them a note.

    python3 scripts/para_cost.py [--json OUT]          the costs, 0..8 notes
    python3 scripts/para_cost.py --level [--json OUT]  the chords' level (peak, RMS, at the output guard)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "test")]
DC = PARA = PP = T = None                                # dsp_cost, the PARA module, perc.program, test_a2_para
NOTES_MAX = 8                                            # PARA_NOTES (csrc/para/para.h): a chord's sounding notes
OFFS = (0, 4, 7, 11, 14, 16, 19, 23)                     # the chord's notes above the leader's 60
BLOCKS, NOTE_B, STEADY = 10, (1, 2), (4, 5, 6, 7)


def _imports() -> None:
    """the model's modules, after sys.path (a function: the imports stay at a module's top elsewhere)"""
    global DC, PARA, PP, T
    import dsp_cost
    import test_a2_para
    from dnfw.engines.analog2 import para
    from dnfw.perc import program
    DC, PARA, PP, T = dsp_cost, para, program, test_a2_para


def tot(c: dict) -> float:
    return DC.est([sum(v[i] for v in c.values()) for i in range(3)])


class ParaNotEngaged(RuntimeError):
    """a chord's slot did not lead its shadows (no LEADER role, or a place LOST): its cost is not a chord's"""


def _flt2(h, lead: int, choice: str | None) -> None:
    """ANALOG 2's FLT2 at CHOICE on slot LEAD (dsp_cost's word for it); None: the defaults"""
    if choice is None:
        return
    from dnfw.perc import machines as PMx
    names, rec, kind = DC._analog2_filters()
    slot, w = DC.choice_word(rec, len(names), names.index(choice), kind)
    t = h.t
    h.t = lead
    h._half(PMx.frame_offset(slot), w)
    h.t = t


def run(n: int, engine: str = "ANALOG2", flt2: str | None = None) -> dict:
    """slot T.LEAD on ENGINE, note 60 on at block 1 and held; N notes in its row (0: PARA OFF, no row) -> the voice's
    and the PARA pass's costs (note blocks' dearer, steady mean), its role, the places left out"""
    from dnfw.perc.dsl import Prog, bits
    lead = T.LEAD
    h = T.setup([lead], para=PARA.ON_VALUE if n else 0, engine=engine)
    _flt2(h, lead, flt2)
    T.ready(h)
    L = h.L
    voice, pas = [], []
    for b in range(BLOCKS):
        h.mem.put(PP.NOTE_CELLS + 4 * lead, bits(60.0))
        h.mem.put(PP.BUFFERS + 4 * lead, T.BUFS + 0x100 * lead)
        h.mem.put(PP.TRIG_WORD, (h.mem.get(PP.TRIG_WORD) & 0xFFFF) | ((1 << lead) << 16 if b == 1 else 0))
        h.mem.put(L.C["mcost"], 0)
        if b == 1 and n:
            T.write_row(h, lead, {k: (OFFS[k], True, 1) for k in range(n)})
        p = Prog("run", mem=h.mem)
        p.spill = L.md.C["ash"]
        PP.mnm_ages(p, L)                                # (the loop's, outside the count: dsp_cost measures it once)
        pas.append(tot(_measure_pass(p, L)))
        c = DC._measure(lambda: DC._first_prog(lambda: PP.run_voice(L, None, lead, mem=h.mem)))
        voice.append(tot(c))
    both = [voice[b] + pas[b] for b in range(BLOCKS)]
    return {"voice": {"note": round(max(voice[b] for b in NOTE_B)), "steady": round(_mean(voice, STEADY))},
            "pass": {"note": round(max(pas[b] for b in NOTE_B)), "steady": round(_mean(pas, STEADY))},
            "cost": round(max(max(both[b] for b in NOTE_B), _mean(both, STEADY))),
            "role": h.mem.get(PARA.ROLE + 4 * lead) >> PARA.ROLE_SHIFT, "lost": h.mem.get(PARA.LOST)}


def _measure_pass(p, L) -> dict:
    """the PARA pass on P, counted as a voice is (its steps, jumps, L2 and DDR words): P the counted Prog, its
    memory moves counted as inside a voice"""
    def one():
        DC.CNT.prog, DC.CNT.last = p, p.steps
        DC.CNT.inside += 1
        try:
            PP.para_prepass(p, L)
            DC.CNT.steps(p)
        finally:
            DC.CNT.inside -= 1
    return DC._measure(one)


def _mean(xs, bs) -> float:
    return sum(xs[b] for b in bs) / len(bs)


def chords(engine: str, flt2: str | None = None) -> dict:
    """{n: run(n)} for 0 (PARA OFF) .. NOTES_MAX; raises ParaNotEngaged when a chord of 2 or more did not lead"""
    out = {n: run(n, engine, flt2) for n in range(NOTES_MAX + 1)}
    for n in range(2, NOTES_MAX + 1):
        r = out[n]
        if r["role"] != PARA.LEADER or r["lost"]:
            raise ParaNotEngaged(f"{engine} {flt2 or ''} {n} notes: role {r['role']}, {r['lost']} places lost")
    return out


def _cases(engine: str) -> list:
    """the settings measured: ANALOG 2 at its defaults and at its dearest FLT2 (dsp_cost's ANALOG2-<choice>), JUNO
    at its defaults"""
    if engine != "ANALOG2":
        return [None]
    from dnfw import load as LD
    eng = LD.load()["engines"]
    names = DC._analog2_filters()[0]
    return [None, max(names, key=lambda c: eng.get(f"ANALOG2-{c}", 0))]


def table_costs(engine: str = "ANALOG2", report: dict | None = None) -> dict:
    """the load table's PARA costs (scripts/gen_load_table.py; csrc/load/load.c prices a PARA chord's slot of N
    sounding notes as the track's voice + BASE + ADD[N]), x (1 + MARGIN) as every cost of the table:
      base: what PARA ON adds to a one-note voice (the pass watching the slot): a chord of 1 less PARA OFF;
      add:  [0, 0, a2 .. a8]: a chord of N less a chord of 1 (its joined notes' shadows and the pass's share; the
            note block counts every note joining at once, the pass zeroing their pool blocks), each the dearest over
            the settings measured. Not one cost a note: the first joined note costs more than the next ones (the
            shadow loop's own start), so a fit per note would over-price big chords by ~14 %;
      chord: the measured chords (1..8 notes), the dearest setting's, for the record (without MARGIN, PER_VOICE).
    The caller has run dsp_cost._install. REPORT (a dict) gets every run."""
    _imports()
    from dnfw import load as LD
    m = 1 + LD.MARGIN
    base = 0.0
    add = [0.0] * (NOTES_MAX + 1)
    chord = [0] * NOTES_MAX
    for flt2 in _cases(engine):
        r = chords(engine, flt2)
        if report is not None:
            report[f"{engine}{'-' + flt2 if flt2 else ''}"] = r
        base = max(base, r[1]["cost"] - r[0]["cost"])
        add = [add[0]] + [max(add[n], r[n]["cost"] - r[1]["cost"]) for n in range(1, NOTES_MAX + 1)]
        chord = [max(chord[n - 1], r[n]["cost"]) for n in range(1, NOTES_MAX + 1)]
    return {"base": round(max(base, 0) * m), "add": [round(max(x, 0) * m) for x in add], "chord": chord}


LEVEL_BLOCKS, LEVEL_FROM = 120, 20             # the level runs: blocks, and the held part measured (from this block)


def level(n: int, engine: str = "ANALOG2") -> dict:
    """2026-11-15 (the User: "Up to 8"): N notes held on one PARA slot (N = 1, PARA OFF: one note), its 48 kHz
    output over blocks LEVEL_FROM.. (the track's sound before the DN2's own chain): its peak, its RMS, and how many
    samples reach the output guard's limit (perc.program.OUT_LIMIT, which clamps)"""
    import math
    from dnfw.perc.dsl import flt
    lead = T.LEAD
    h = T.setup([lead], para=PARA.ON_VALUE if n > 1 else 0, engine=engine)
    T.ready(h)
    mix = []
    for b in range(LEVEL_BLOCKS):
        if b == 1 and n > 1:
            T.write_row(h, lead, {k: (OFFS[k], True, 1) for k in range(n)})
        out, _roles = T.block(h, [lead], {lead: 60.0}, on=(1 << lead) if b == 1 else 0)
        if b >= LEVEL_FROM:
            mix += [flt(x) for x in out[lead]]
    peak = max(abs(x) for x in mix)
    rms = math.sqrt(sum(x * x for x in mix) / len(mix))
    return {"peak": round(peak, 4), "rms": round(rms, 4),
            "at_guard": sum(1 for x in mix if abs(x) >= PP.OUT_LIMIT), "guard": PP.OUT_LIMIT}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json")
    ap.add_argument("--level", action="store_true", help="the 1..8 note chords' level, not the cost")
    a = ap.parse_args()
    _imports()
    out = {}
    if a.level:
        for engine in ("ANALOG2", "JUNO"):
            for n in range(1, NOTES_MAX + 1):
                r = level(n, engine)
                out[f"{engine}_n{n}"] = r
                print(f"{engine} {n} notes: peak {r['peak']}  rms {r['rms']}  at the guard {r['at_guard']} "
                      f"(+-{r['guard']})", flush=True)
    else:
        DC._install()
        for engine in ("ANALOG2", "JUNO"):
            runs = {}
            t = table_costs(engine, runs)
            for case, r in runs.items():
                for n, x in r.items():
                    print(f"{case} {n} notes{' (PARA OFF)' if n == 0 else ''}: {x}", flush=True)
            print(f"{engine} table: {t}", flush=True)
            out[engine] = {"table": t, "runs": runs}
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
