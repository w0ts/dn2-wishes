"""2026-11-12: the cost of what runs beside the voices, on dsp_cost.py's scale (instructions + 4 L2 + 10 DDR, the
model's count made instruction-exact as there): the A2 filter types and the inserts per voice slot, the bus inserts
and the send FX per instance. For the kit load check (the ColdFire's table, scripts/gen_load_table.py).

    python3 scripts/dsp_cost_fx.py [--json out/dsp_cost/fx.json]

Each item: its program's model (the tests' harnesses: test/test_a2f_slots, test_inserts, test_inserts_post,
test_inserts_bus, test_fdn8, test_xdly, test_jsend) run for WARM blocks, then STEADY blocks counted and averaged.
Per voice slot: (cost with N slots on the item - cost with none) / N, N = 4; `idle` is the pass's cost with none.
Per instance: the item on, less the same block with the stock's own in its place (the send FX) or nothing (bus).
Inputs are noise at -6 dBFS (a sounding voice). The stock's own filters, machines and send FX are the runner's
(sharc_cost.py --steps stock), not here.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "test"))
sys.path.insert(0, str(HERE))

import dsp_cost as DC  # noqa: E402

WARM, STEADY, N = 12, 8, 4
WARM_BUS = 40


def gate(mod, name: str) -> None:
    """count only inside MOD.NAME (the program's own run), not the harness's memory moves around it"""
    f = getattr(mod, name)
    if getattr(f, "_gated", False):
        return

    def run(*a, **k):
        DC.CNT.inside += 1
        try:
            return f(*a, **k)
        finally:
            DC.CNT.inside -= 1
    run._gated = True
    setattr(mod, name, run)


@contextlib.contextmanager
def counting():
    """count every Prog step and memory access made inside a gated program while here (each run-mode Prog made
    counts from its start)"""
    DC.CNT.c.clear()
    DC.ZS.clear()
    DC.CNT.on, DC.CNT.prog, DC.CNT.last = True, None, 0
    DC.CNT.multi = {}                      # 2026-11-22: every run Prog counts its own steps (the bus pass's after its
    orig = DC.dsl.Prog.__init__            # engine's returned: copy-out, blend), each kept referenced (no id reuse)

    def init(self, *a, **k):
        orig(self, *a, **k)
        if self.run:                       # a program making several Progs: each counts from its start
            DC.CNT.prog, DC.CNT.last = self, 0
            DC.CNT.multi[id(self)] = [self, 0]
    DC.dsl.Prog.__init__ = init
    try:
        yield
    finally:
        DC.dsl.Prog.__init__ = orig
        DC.CNT.on = False
        DC.CNT.multi = None


def total() -> float:
    v = [0, 0, 0]
    for c in DC.CNT.c.values():
        for i in range(3):
            v[i] += c[i]
    return DC.est(v)


def steady(block, warm: int = WARM) -> float:
    """BLOCK(b) runs block b; the mean cost of the STEADY blocks after WARM (WARM_BUS for the bus inserts: past an
    FDN8 instance's 32 clearing blocks, 2026-11-22; 12 measured a clearing block)"""
    for b in range(warm):
        block(b)
    got = []
    for b in range(warm, warm + STEADY):
        with counting():
            block(b)
        got.append(total())
    return sum(got) / len(got)


def noise(rnd):
    return [rnd.uniform(-0.5, 0.5) for _ in range(32)]


# -- the A2 filters, per voice slot ------------------------------------------------------------------

def a2f() -> dict:
    import test_a2f_slots as T
    from dnfw.engines.analog2.filters import design as DS, live as AL, program as AP
    gate(AP, "run")
    out = {}

    def run(ftype: int | None, n: int) -> float:
        img = AL.Image()
        img.route([0 if s < n else 0x7FFF for s in range(16)])
        if ftype is not None:
            for s in range(n):                  # the frame's filter type, record and note are per voice slot (2026-11-12)
                img.ftype(s, ftype)
                img.record(s, **T.REC)
                img.note(s, 48.0)
        rnd = random.Random(5)

        def block(b):
            img.mem.put(T.P.TRIGW, img.mem.get(T.P.TRIGW) & 0xFFFF)
            if b == 0:
                img.trig(range(n))
            for s in range(16):
                img.buffer(s, noise(rnd) if s < n else [0.0] * 32)
            AL.run(img.mem)
        return steady(block)
    idle = run(None, 0)
    out["(pass, no A2 voice)"] = {"idle": round(idle)}
    for t, name in DS.TYPES.items():
        out["A2 " + name] = {"per_voice": round((run(t, N) - idle) / N), "idle": round(idle)}
    return out


# -- the inserts before the pan (pre) and after it (post), per voice slot -------------------------------

def pre_inserts() -> dict:
    import test_inserts as T
    D = T.D
    gate(T.P, "run")
    out = {}
    route = [2 if s < N else 0x7FFF for s in range(16)]
    rnd = random.Random(3)

    def run(row) -> float:
        m = T.mem0()
        par = T.par_of({} if row is None else {2: row})
        return steady(lambda b: T.call(m, par, [noise(rnd) for _ in range(D.TRACKS)], route))
    idle = run(None)
    for typ in D.BUILT:
        row = [typ, 127, 90, 70, 64, 64, 64, 64]
        out["INS " + D.NAMES[typ]] = {"per_voice": round((run(row) - idle) / N), "idle": round(idle)}
    return out


def post_inserts() -> dict:
    import test_inserts_post as T
    D = T.D
    gate(T.P, "model")
    out = {}
    route = [2 if s < N else 0x7FFF for s in range(16)]
    rnd = random.Random(4)

    def run(typ) -> float:
        m = DC.dsl.Mem()
        rows = bytearray(128)
        if typ is not None:
            rows[16:24] = bytes([typ, 127, 90, 64, 64, 100, 64, 64])
        regs = {k: 0 for k in range(16)}
        return steady(lambda b: T.call(m, bytes(rows), [noise(rnd) for _ in range(16)],
                                       [noise(rnd) for _ in range(16)], route, regs))
    idle = run(None)
    for typ in D.POST:
        out["INS " + D.NAMES[typ]] = {"per_voice": round((run(typ) - idle) / N), "idle": round(idle)}
    return out


# -- the bus inserts and the send FX, per instance ---------------------------------------------------

def bus_inserts() -> dict:
    import test_inserts_bus as T
    D = T.D
    gate(T.B, "model")
    out = {}
    rnd = random.Random(6)

    def run(rows) -> float:
        m = T.mem0()
        par = T.table(rows)
        regs = {k: 0 for k in range(16)}
        return steady(lambda b: T.call(m, par, [noise(rnd) for _ in range(16)], [noise(rnd) for _ in range(16)], regs),
                      WARM_BUS)
    idle = run({})
    for typ in D.BUS:
        cost = run({(2, 0): T.rec(typ, 0, 100, 64, 64, 64, 64, 64, 64)})
        out["BUS " + D.NAMES[typ]] = {"per_instance": round(cost - idle), "idle": round(idle)}
    return out


def sends() -> dict:
    out = {}
    rnd = random.Random(7)
    for mod, name in (("test_fdn8", "SEND FDN8"), ("test_xdly", "SEND XDLY")):
        T = __import__(mod)
        gate(T.P, "run")
        par = [0.3, 0.6, 0.3, 0.5, 0.2, 1.0]

        def run(tw) -> float:
            m = T.mem0()
            return steady(lambda b: T.call(m, tw, noise(rnd), noise(rnd), par))
        out[name] = {"per_instance": round(run(0) - run(0x100))}
    import test_jsend as J
    D = J.D
    gate(J.J, "model")

    def jrun(typ) -> float:
        m = DC.dsl.Mem()
        J.setup(m)
        regs = {k: 0 for k in range(16)}
        return steady(lambda b: J.call(m, typ, 100 << 8, 40 << 8, noise(rnd), noise(rnd), regs))
    out["SEND JUNO"] = {"per_instance": round(jrun(D.JS_JUNO) - jrun(D.JS_STOCK))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default="out/dsp_cost/fx.json")
    a = ap.parse_args()
    DC._install()
    res, bad = {}, []
    for part in (a2f, pre_inserts, post_inserts, bus_inserts, sends):
        try:
            got = part()
        except Exception as ex:                # one part's harness problem must not hide the others: reported, exit 1
            bad.append(f"{part.__name__}: {type(ex).__name__}: {ex}")
            print(f"  {part.__name__}: ERROR {type(ex).__name__}: {ex}", flush=True)
            continue
        for k, v in got.items():
            print(f"  {k:24s} {v}", flush=True)
        res.update(got)
    pathlib.Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.json).write_text(json.dumps({"rows": res, "errors": bad, "n": N, "warm": WARM,
                                                "steady": STEADY}, indent=1))
    print(f"{'PASS' if not bad else 'FAIL'}: {len(res)} items, {len(bad)} errors")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
