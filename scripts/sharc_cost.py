"""2026-11-12: dsp_cost.py's table in the SHARC runner: the assembled code, the stock machines beside ours.

    python scripts/sharc_cost.py --image STOCK.syx --digikit DIGIKIT [--steps cost,stock] [--only NAME,..]
                                 [--json out/dsp_cost/runner_TAG.json]

The same cost (instructions + 4 x L2 + 10 x DDR accesses, docs/dsp-cost.md) and the same block schedule as
scripts/dsp_cost.py, on the section 7 the build ships (sharc_waverider_m5's images, frames and memory counts;
that file is imported, not changed):

  blocks 0..9, track 0 on the engine from block 0, a note on block 1 (`start`: the max of blocks 1, 2) and
  again on block 8 (`trig`: the max of blocks 8, 9); `steady` the mean of blocks 4..7

For each of our voices the runner is split by address (csrc/waverider/sharc/perc.json's instruction offsets
against perc.asm's labels): the voice is the span between the frame guard's two EMUCLK reads around it; the
engine is what runs from a machine's body in an md_<step> dispatch (render, trig, init, host) to that dispatch's
end label, the subroutines it calls included; the host is the rest of the span. The loop around the voices
(PERC's entry to the sample machines' entry, less the voices) is reported per block as `loop`. The sample
machines' voices are smp.asm's guard span (no split). On the same DSP memory at each PERC entry the model
(dsp_cost.py's counter on dnfw.perc.program.voice) runs too: `model` beside `runner`, the calibration.

The stock machines (types 0-3, step `stock`): the whole block (sw 0x1c2712 and all it calls) with track 0 on the
machine, less the same block with track 0 on MIDI (type 4, no render): what a stock voice costs the frame. The
MIDI block itself is reported too (the stock's own floor and our fixed per-block work).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import dsp_cost as DC  # noqa: E402

BLOCKS = 10
START_B, STEADY_B, TRIG_B = (1, 2), (4, 5, 6, 7), (8, 9)
NOTES = (1, 8)
BODY = re.compile(r"^wr_pk_md_(host|init|trig|render)_\d+_\d+$")
END = re.compile(r"^wr_pk_md_(host|init|trig|render)_end_\d+$")


def addresses(name: str):
    """NAME.asm's instructions: [(sw address, text)], and label -> sw address (of the next instruction)"""
    sharc = HERE.parent / "csrc" / "waverider" / "sharc"
    spec = json.loads((sharc / f"{name}.json").read_text(encoding="utf-8"))
    base = int(spec["load_sw"], 0) if isinstance(spec["load_sw"], str) else spec["load_sw"]
    offs = spec["instruction_offsets"]
    ins, labels, pend = [], {}, []
    for line in (sharc / f"{name}.asm").read_text(encoding="utf-8").splitlines():
        t = line.split("//", 1)[0].strip()
        if not t or t.startswith("."):
            continue
        if t.endswith(":"):
            pend.append(t[:-1].rstrip("."))
            continue
        a = base + offs[len(ins)] // 2
        for p in pend:
            labels[p] = a
        pend = []
        ins.append((a, t))
    assert len(ins) == len(offs), f"{name}: {len(offs)} offsets, {len(ins)} instructions"
    return ins, labels


def guard_span(ins) -> tuple[int, int]:
    """the voice's span: the instruction after the guard's first EMUCLK read (`DM(START) = R8` follows it) and
    the second one (`R9 = DM(START)` follows it)"""
    from dnfw.perc import guard as G
    st = f"{G.START:#x}"
    a = b = None
    for k, (addr, t) in enumerate(ins[:-1]):
        if t == "R8 = EMUCLK;":
            nxt = ins[k + 1][1].replace(" ", "").lower()
            if a is None and nxt.startswith(f"dm({st})=r8"):
                a = ins[k + 1][0]
            elif a is not None and b is None and nxt == f"r9=dm({st});":
                b = addr
    assert a is not None and b is not None, "the guard's EMUCLK pair not found"
    return a, b


class Meter:
    """per block: our voices' spans and their engine parts, PERC's and smp's totals; counts (instructions,
    L2, DDR) from the runner's steps and _count_memory"""

    def __init__(self, R, counts):
        self.R, self.counts = R, counts
        ins, lab = addresses("perc")
        self.v0, self.v1 = guard_span(ins)
        self.body = {a for n, a in lab.items() if BODY.match(n)}
        self.end = {a for n, a in lab.items() if END.match(n)}
        self.slot = lab[next(n for n in lab if re.match(r"^wr_pk_slot_\d+$", n))]   # the slots' loop top
        sins, _slab = addresses("smp")
        self.s0, self.s1 = guard_span(sins)
        self.blocks = []
        self.cur = None

    def now(self, r):
        return (r.steps_n, self.counts["L2"], self.counts["DDR"])

    def hooks(self):
        R = self.R
        h = {R.dsp.PERC_SW: self.at_perc, R.dsp.SMP_SW: self.at_smp, R.dsp.PING_SW: self.at_ping,
             self.slot: self.at_slot, self.v0: self.voice_in, self.v1: self.voice_out, self.s0: self.svoice_in, self.s1: self.svoice_out}
        for a in self.body:
            h[a] = self.eng_in
        for a in self.end:
            h[a] = self.eng_out
        return h

    def at_perc(self, r):
        if self.cur is not None and "ping" not in self.cur:
            self.cur["perc_hits"] = self.cur.get("perc_hits", 1) + 1     # (once a block, expected)
            return
        self.counts["on"] = True
        self.cur = {"perc0": self.now(r), "voices": {}, "svoices": {}}
        self.blocks.append(self.cur)

    def at_slot(self, r):
        if self.cur is not None and "slot0" not in self.cur:
            self.cur["slot0"] = self.now(r)    # PERC's entry to here: tables, mnm_ages, the guard's entry

    def at_smp(self, r):
        if self.cur is not None and "smp0" not in self.cur:
            self.cur["smp0"] = self.now(r)

    def at_ping(self, r):
        if self.cur is not None and "ping" not in self.cur:
            self.cur["ping"] = self.now(r)
            self.counts["on"] = False

    def _slot(self, r):
        return self.R.m2.word(r.state, DC_layout().C["t"]) or 0

    def voice_in(self, r):
        self.cur["v"] = {"t": self._slot(r), "a": self.now(r), "eng": [0, 0, 0], "e0": None}

    def eng_in(self, r):
        v = self.cur.get("v") if self.cur else None
        if v is not None and v["e0"] is None:
            v["e0"] = self.now(r)

    def eng_out(self, r):
        v = self.cur.get("v") if self.cur else None
        if v is not None and v["e0"] is not None:
            n = self.now(r)
            for i in range(3):
                v["eng"][i] += n[i] - v["e0"][i]
            v["e0"] = None

    def voice_out(self, r):
        v = self.cur.pop("v", None)
        if v is not None:
            n = self.now(r)
            self.cur["voices"][v["t"]] = {"total": [n[i] - v["a"][i] for i in range(3)], "engine": v["eng"]}

    def svoice_in(self, r):
        self.cur["sv"] = {"t": self.R.m2.word(r.state, _smp_t_word()) or 0, "a": self.now(r)}

    def svoice_out(self, r):
        v = self.cur.pop("sv", None)
        if v is not None:
            n = self.now(r)
            self.cur["svoices"][v["t"]] = [n[i] - v["a"][i] for i in range(3)]


_L = []


def DC_layout():
    if not _L:
        from dnfw.perc import live as PL
        _L.append(PL.layout())
    return _L[0]


def _smp_t_word() -> int:
    from dnfw.sampler import live as SL
    return SL.layout().C["t"]


def summarize(blocks, t: int = 0, sampler: bool = False) -> dict:
    """the runner's start / steady / trig figures for slot T, as dsp_cost.row prints them"""
    def voice(b):
        blk = blocks[b] if b < len(blocks) else {}
        if sampler:
            v = blk.get("svoices", {}).get(t)
            return (v, [0, 0, 0]) if v else ([0, 0, 0], [0, 0, 0])
        v = blk.get("voices", {}).get(t)
        return (v["total"], v["engine"]) if v else ([0, 0, 0], [0, 0, 0])

    def fig(tot, eng):
        host = [tot[i] - eng[i] for i in range(3)]
        return {"instructions": round(tot[0]), "L2": round(tot[1]), "DDR": round(tot[2]), "cost": round(DC.est(tot)),
                "host": round(DC.est(host)), "engine": round(DC.est(eng)),
                "engine_counts": [round(x) for x in eng], "host_counts": [round(x) for x in host]}
    out = {}
    for kind, bs in (("start", START_B), ("trig", TRIG_B)):
        best = max((voice(b) for b in bs), key=lambda v: DC.est(v[0]))
        out[kind] = fig(*best)
    vs = [voice(b) for b in STEADY_B]
    out["steady"] = fig([sum(v[0][i] for v in vs) / len(vs) for i in range(3)],
                        [sum(v[1][i] for v in vs) / len(vs) for i in range(3)])

    def loop(blk):
        if "smp0" not in blk or "slot0" not in blk:
            return None
        pre = [blk["slot0"][i] - blk["perc0"][i] for i in range(3)]
        tot = [blk["smp0"][i] - blk["slot0"][i] for i in range(3)]
        vsum = [sum(v["total"][i] for v in blk["voices"].values()) for i in range(3)]
        smp = [blk["ping"][i] - blk["smp0"][i] for i in range(3)] if "ping" in blk else [0, 0, 0]
        svs = [sum(v[i] for v in blk["svoices"].values()) for i in range(3)]
        return {"entry": round(DC.est(pre)), "slots": round(DC.est([tot[i] - vsum[i] for i in range(3)])),
                "smp_loop": round(DC.est([smp[i] - svs[i] for i in range(3)]))}
    out["loop"] = [loop(blocks[b]) for b in STEADY_B if b < len(blocks)]
    return out


def main(argv=None) -> int:
    import sharc_waverider_m5 as R
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--digikit", type=pathlib.Path, required=True)
    ap.add_argument("--steps", default="cost,stock")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="out/dsp_cost/runner.json")
    a = ap.parse_args(argv)
    steps = set(a.steps.split(","))
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    DC._install()
    t0 = time.time()
    dk = R.m1.Digikit(a.digikit)
    R.fx.bind(str(a.digikit / "tools"))
    R.m4.IMAGE = a.image
    stock = R.m1.dn2_section7(a.image)
    sound, machines = R.m4.init_sound(a.image)
    img = R.Image(dk, R.dsp.section7(stock))
    rep = {"section7_sha256": img.sha, "schedule": {"blocks": BLOCKS, "notes": NOTES, "start": START_B,
                                                    "steady": STEADY_B, "trig": TRIG_B},
           "rows": [], "stock": {}, "errors": []}
    R.OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=R.OUT) as tmp:
        work = pathlib.Path(tmp)
        snap, m2mach = R.snapshot_path(dk, stock, work)
        warm = R.init_on(snap, m2mach, R.Image(dk, img.stream), warm=True)
        counts, undo = R._count_memory()
        try:
            if "cost" in steps:
                for row in engines(R, warm, sound, machines, counts, only):
                    rep["rows"].append(row)
                    if row.get("error"):
                        rep["errors"].append(f"{row['name']}: {row['error']}")
                    _show(row)
            if "loop" in steps:
                rep["loop"] = loop_rows(R, warm, sound, machines, counts)
                for k, v in rep["loop"].items():
                    print(f"  loop {k:22s} {v}", flush=True)
            if "stock" in steps:
                rep["stock"] = stock_rows(R, warm, sound, machines, counts)
                for k, v in rep["stock"].items():
                    print(f"  stock {k:10s} steady {v['steady']:7,d}  trig {v['trig']:7,d}", flush=True)
        finally:
            undo()
    rep["seconds"] = round(time.time() - t0)
    out = pathlib.Path(a.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1))
    ok = not rep["errors"]
    print(f"{'PASS' if ok else 'FAIL'}: {len(rep['rows'])} engines, {len(rep['stock'])} stock, "
          f"{len(rep['errors'])} errors, {rep['seconds']} s -> {out}")
    return 0 if ok else 1


def _show(row) -> None:
    if row.get("error"):
        print(f"  {row['name']}: ERROR {row['error']}", flush=True)
        return
    s, m = row["runner"]["steady"], row.get("model_steady")
    mm = f"  model {m['cost']:7,d} (host {m['host']:6,d})" if m else ""
    print(f"  {row['name']:14s} runner steady {s['cost']:7,d} (host {s['host']:6,d} engine {s['engine']:7,d})  "
          f"trig {row['runner']['trig']['cost']:7,d}  start {row['runner']['start']['cost']:7,d}  "
          f"loop {row['runner']['loop'][0]}{mm}", flush=True)
    if m:
        print("      model buckets:", m["buckets"], flush=True)
        print(f"      runner engine {s['engine_counts']} host {s['host_counts']}; model engine "
              f"{m.get('engine_counts')} host {m.get('host_counts')}", flush=True)


def engines(R, warm, sound, machines, counts, only):
    from dnfw.md import voice as MDV
    from dnfw.mnm import machines as MM
    from dnfw.engines.plaits import plaits as PLT
    from dnfw.sampler import machines as SM
    cases = []
    for k, M in enumerate(MDV.MM.MACHINES):
        cases.append((M.NAME, M.NAME.split("-")[0], lambda k=k: R.perc_words(k), 5, False))
    for k, n in enumerate(MM.NAMES):
        if n == "PLAITS":
            for mi, m in enumerate(PLT.MODELS):
                if not m:                      # the retired choice: it plays WS
                    continue

                def w(k=k, mi=mi):
                    words = R.mnm_words(k)
                    slot, word = DC.plaits_word(mi)
                    words[slot] = word
                    return words
                cases.append(("PLAITS-" + (m or "?"), "PLAITS", w, MM.TYPES[k], False))
        elif n == "DRUM":                      # 2026-11-20: each type at its start and its dearest (dsp_cost's cases)
            import sharc_drum_step as DS
            from dnfw.perc import live as PLx
            from dnfw.perc import machines as PMx

            def dw(t, p1, p2, k=k):
                k1, k2 = DS.knobs_of(t, p1, p2)
                words = R.mnm_words(k, k1)
                for j, x in enumerate(k2.values()):
                    _rid, slot, lo, top = DS.rec2(j)           # (stage 3: page 2 H, SNARE's WCHR)
                    words[slot] = PLx.knob_word(x, top, lo)
                return words
            for dname, case in DS.cost_cases().items():
                cases.append((dname, "DRUM", lambda case=case: dw(*case), MM.TYPES[k], False))
        else:
            fam = "MONOMACHINE" if n in MM.MONO_ENGINES else n
            cases.append((n, fam, lambda k=k: R.mnm_words(k), MM.TYPES[k], False))
    for name in ("ONESHOT", "WERP", "STRETCH", "REPITCH", "GRID", "SLICE"):
        if name in SM.TYPE_OF:
            cases.append((name, "SAMPLE", lambda: R.smp_words({SM.SAMP_REC: 4}), SM.TYPE_OF[name], True))
    for name, fam, words, ty, sampler in cases:
        if only and name not in only:
            continue
        meter = Meter(R, counts)
        model = {}

        def fb(b, words=words, ty=ty):
            f = R.base_frame(sound, machines, t0=ty, trigger=b in NOTES)
            for slot, w in words().items():
                f.param(0, slot, w)
            return f.to_bytes()
        try:
            rr = _run_counted(R, warm, fb, meter, model)
            if not rr["ok"]:
                yield {"name": name, "family": fam, "error": rr.get("halt", "a block did not return")}
                continue
            row = {"name": name, "family": fam, "sampler": sampler,
                   "runner": summarize(meter.blocks, 0, sampler)}
            if model and not sampler:
                st = [model[b] for b in STEADY_B if model.get(b)]
                if st:
                    row["model_steady"] = DC.row("m", fam, {"steady": DC._sum(st, len(st)), "trig": st[0],
                                                            "start": st[0]})["steady"]
            yield row
        except Exception as ex:                # reported, the rest measured
            yield {"name": name, "family": fam, "error": f"{type(ex).__name__}: {ex}"}


def _run_counted(R, warm, fb, meter, model):
    """run_blocks with METER's hooks, the model's voice of slot 0 counted at each PERC entry (run_blocks' own
    model run: its PP.run_voice on the DSP's memory there, before METER's entry hook): MODEL[block] = its counts"""
    PP = R.PP
    orig = PP.run_voice

    def counted(L, read, t, mem=None):
        if t != 0:
            return orig(L, read, t, mem)
        def go():
            nonlocal_res.append(orig(L, read, t, mem))
        nonlocal_res = []
        oinit = DC.dsl.Prog.__init__

        def init(self, *a, **k):
            oinit(self, *a, **k)
            if DC.CNT.prog is None and self.run:
                DC.CNT.prog, DC.CNT.last = self, 0
        DC.dsl.Prog.__init__ = init
        try:
            cnt = DC._measure(go)
        finally:
            DC.dsl.Prog.__init__ = oinit
        model[len(meter.blocks)] = cnt
        return nonlocal_res[0]
    PP.run_voice = counted
    try:
        return R.run_blocks(warm, fb, BLOCKS, extra_hooks=meter.hooks())
    finally:
        PP.run_voice = orig


def loop_rows(R, warm, sound, machines, counts) -> dict:
    """the work around our voices, per block (steady blocks): PERC's entry (tables, mnm_ages, the guard's entry),
    PERC's slot loop less the voices (each voice's guard and the loop's own), the sample machines' loop less theirs
    (the recorder and the fast link among it). Tracks on MIDI except N TRX-BD voices (tracks 0..N-1), or one ONESHOT"""
    from dnfw.sampler import machines as SM
    scen = {"no voice": (4, 0, None), "1 TRX-BD": (5, 1, None), "4 TRX-BD": (5, 4, None),
            "16 TRX-BD": (5, 16, None), "1 ONESHOT": (SM.TYPE_OF["ONESHOT"], 1, "smp")}
    out = {}
    for name, (ty, n, kind) in scen.items():
        meter = Meter(R, counts)
        words = R.perc_words(0) if kind is None else R.smp_words({SM.SAMP_REC: 4})

        def fb(b, ty=ty, n=n, words=words):
            others = {t: ty for t in range(1, n)}
            f = R.base_frame(sound, machines, t0=ty, trigger=b in NOTES, others=others, trigger_others=True)
            for t in range(n):
                for slot, w in words.items():
                    f.param(t, slot, w)
            return f.to_bytes()
        rr = R.run_blocks(warm, fb, BLOCKS, extra_hooks=meter.hooks())
        if not rr["ok"]:
            out[name] = {"error": rr.get("halt")}
            continue
        lp = summarize(meter.blocks)["loop"]
        out[name] = {k: round(sum(x[k] for x in lp) / len(lp)) for k in lp[0]}
        out[name]["voices"] = [len(meter.blocks[b]["voices"]) for b in STEADY_B]
        out[name]["svoices"] = [len(meter.blocks[b]["svoices"]) for b in STEADY_B]
        out[name]["perc_hits"] = [meter.blocks[b].get("perc_hits", 1) for b in STEADY_B]
    return out


def stock_rows(R, warm, sound, machines, counts) -> dict:
    """types 0-3 on track 0 (its own sound page), a note on blocks 1 and 8, against track 0 on MIDI (type 4, no
    render) with the same notes: the whole block's difference is what the stock voice costs (the stock machines
    render every block, note or not). Tracks 1-15 MIDI in both"""
    def per_block(ty):
        def fb(b):
            return R.base_frame(sound, machines, t0=ty, overrides=machines.get(ty, {}), trigger=b in NOTES).to_bytes()
        out, state = [], warm
        for b in range(BLOCKS):
            for k in ("L1", "L2", "DDR"):
                counts[k] = 0
            counts["on"] = True
            rr = R.run_blocks(state, lambda _b, b=b: fb(b), 1)
            counts["on"] = False
            if not rr["ok"]:
                raise RuntimeError(rr.get("halt"))
            out.append(DC.est([rr["instructions"], counts["L2"], counts["DDR"]]))
            state = rr["state"]
        return out
    midi = per_block(4)
    res = {"MIDI (whole block)": {"steady": round(sum(midi[b] for b in STEADY_B) / len(STEADY_B)),
                                  "trig": round(max(midi[b] for b in TRIG_B)),
                                  "start": round(max(midi[b] for b in START_B))}}
    for ty in range(4):
        d = [n - q for n, q in zip(per_block(ty), midi)]
        res[f"type{ty}"] = {"steady": round(sum(d[b] for b in STEADY_B) / len(STEADY_B)),
                            "trig": round(max(d[b] for b in TRIG_B)), "start": round(max(d[b] for b in START_B))}
    return res


if __name__ == "__main__":
    raise SystemExit(main())
