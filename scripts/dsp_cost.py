"""2026-11-12: what one voice-block of every engine costs the DSP, and how much of it is the voice host's.

ONE method for every engine (docs/dsp-cost.md, "2026-11-12"): the program's model (dnfw.perc.program.voice and
dnfw.sampler.program.voice in run mode, the same DSL text the build assembles), one voice on track 0:

  cost = instructions + 4 x L2 accesses + 10 x DDR accesses     (docs/dsp-cost.md's scale)

Instructions are the model's steps (memory moves folded into a compute cost nothing, as on the core) plus what
the model leaves out of its steps: every jump the code takes (an if's, the jump over an else, a loop's back jump)
and a subroutine call's own four instructions. Each instruction and memory access is put down to who ran it, by
the Python call stack that emitted it:

  engine   the machine's own code, reached through dnfw.md.voice._each (render, trig, init, and `host`: the
           machine's knob scaling, which is the engine's too)
  host     everything else in the voice: the frame words, the budget and rest bookkeeping, the stream move,
           the resampler and level, the quiet test, PERC's track effects, the output guard

Blocks (schedule()): a fresh voice on the engine, blocks 0..9, notes on blocks 1 and 8; `start` is the dearer of
blocks 1, 2 (the first note: the machine's init), `steady` the mean of blocks 4..7, `trig` the dearer of blocks 8, 9
(a retrigger). The dearer of two, because a Machinedrum voice renders its own block only when its stream asks. The loop
around the voices (dnfw.perc.program.program: the order, the record, the guard, ~100 instructions a voice; and
once a block mnm_ages, ~4,000 for all 16 slots) is not in the model; `--steps loop` counts its straight path from
the emitted text. The stock DN2 machines are the SHARC runner's (`sharc_waverider_m5.py --steps cost`, the
whole_block rows): not modelled here.

Usage:
  python3 scripts/dsp_cost.py --steps cost [--only NAME,..] [--json out/dsp_cost/report.json] [--md FILE]
  python3 scripts/dsp_cost.py --steps host  [--only ..]    the host's buckets per engine (where its cost goes)

Needs MD_OS_BIN (and MNM_OS) as the build does. Exit 0 when every engine was measured (no exception), else 1.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from dnfw.perc import dsl  # noqa: E402

FRAME = 666_667                     # cycles a frame (1 GHz, 1,500 frames a second)
OURS = 310_000                      # what our voices get of it (the guard's LIMIT less the stock's tail; the brief)
BLOCKS, NOTES = 10, (1, 8)          # the schedule (schedule()): blocks 0..9, notes on 1 and 8
START_B, STEADY_B, TRIG_B = (1, 2), (4, 5, 6, 7), (8, 9)
L2_W, DDR_W = 4, 10


def region(a: int) -> int:
    """0 L1, 1 L2, 2 DDR (byte addresses as the program uses them)"""
    a &= 0xFFFFFFFF
    return 2 if a >= 0x80000000 else 1 if 0x20000000 <= a < 0x20200000 else 0


# the host's buckets: the innermost of these functions on the stack names it (module suffix, function)
BUCKETS = (
    (("md.voice", "peak32"), "quiet"), (("perc.program", "listen"), "quiet"),
    (("perc.program", "out_guard"), "out_guard"),
    (("perc.program", "fx"), "fx"),
    (("perc.program", "budget"), "budget"), (("perc.program", "md_rest"), "rest"),
    (("perc.program", "mnm_note"), "note"), (("perc.program", "mono_level"), "level"),
    (("perc.program", "fresh"), "fresh"),
    (("perc.program", "param"), "params"), (("perc.program", "fx_params"), "params"),
    (("md.voice", "inputs"), "inputs"),
    (("md.voice", "advance"), "stream"), (("md.voice", "silent"), "stream"),
    (("md.voice", "block"), "resample"),
    (("perc.program", "voice"), "voice"),
    (("sampler.program", "voice"), "sampler"),
)
_BUCKET = {k: v for k, v in BUCKETS}


class Counter:
    """instructions and accesses by (side, bucket); `on` while a measured block runs"""

    def __init__(self):
        self.on = False
        self.force = None                      # a tag that overrides the stack's (the dispatch)
        self.inside = 0                        # inside a voice() (the harness's own memory moves are not counted)
        self.depth = 0                         # inside a Mem.get (a Mem reading through another counts once)
        self.c = collections.defaultdict(lambda: [0, 0, 0])
        self.prog = None
        self.last = 0

    def tag(self) -> tuple[str, str]:
        if self.force:
            return self.force
        f = sys._getframe(3)
        inner = None
        while f is not None:
            mod = f.f_globals.get("__name__", "")
            name = f.f_code.co_name
            if name == "_each" and "step" in f.f_locals and (mod == "dnfw.md.voice" or f.f_locals.get("p") is not None):
                return ("engine", f.f_locals.get("step", "?"))
            if inner is None and mod.startswith("dnfw."):
                b = _BUCKET.get((mod[5:], name))
                if b is not None:
                    inner = b
            f = f.f_back
        return ("host", inner or "other")

    def steps(self, p) -> None:
        """put the steps P took since the last event down to the current tag"""
        if not self.on or p is not self.prog:
            return
        d = p.steps - self.last
        self.last = p.steps
        if d:
            self.c[self.tag()][0] += d

    def mem(self, a: int) -> None:
        if self.on and self.inside and not self.depth:
            k = region(a)
            if k:
                self.c[self.tag()][k] += 1


CNT = Counter()


class ZeroScale:
    """dnfw.perc.dsl._zero_scale (emit mode's last pass), streamed over run mode: a counted `Rs = 0x0` / `Rs = 0x1`
    whose value is read, before Rs is written again in straight-line code, only by `FLOAT Rx BY Rs` (0) or by a
    lone `Rd = Ra -/+ Rs`, `Rd = Rs + Ra` (1) is dropped from the emitted code: its step is taken back. Any label
    or jump (an if, a loop's top, a call, a dispatch), any other mention of Rs / Fs keeps it."""

    def __init__(self):
        self.pend = {}                         # s -> [k, uses, tag, bad]
        self.last_use = None                   # the register a k=1 use just read (a merge into it: two parts)

    def clear(self) -> None:
        self.pend.clear()
        self.last_use = None

    def load(self, p, d: int, v: int) -> None:
        self.wrote(p, d)
        if v in (0, 1):
            self.pend[d] = [v, 0, CNT.tag() if CNT.on else None, False]

    def wrote(self, p, d: int) -> None:
        e = self.pend.pop(d, None)
        if e is not None and e[1] and not e[3]:
            p.steps -= 1                       # dropped: its step back, to where it was counted
            CNT.last -= 1
            if e[2] is not None and CNT.on and p is CNT.prog:
                CNT.c[e[2]][0] -= 1

    def text(self, p, text: str) -> None:
        import re as _re
        self.last_use = None
        if not self.pend:
            return
        body = text.split("//", 1)[0].strip().rstrip(";")
        for sreg in list(self.pend):
            e = self.pend.get(sreg)
            if e is None:
                continue
            reg = _re.compile(rf"\b[RF]{sreg}\b")
            if not reg.search(body):
                continue
            from dnfw.perc.dsl import _one_form
            lhs, eq, _ = body.partition(" = ")
            np = _one_form(body, str(sreg), "0x0" if e[0] == 0 else "0x1")
            nl, neq, nr = np.partition(" = ")
            if not neq:
                nl, nr = "", np
            if reg.search(nr) or ("DM(" in nl and reg.search(nl)):
                self.pend.pop(sreg)            # read some other way: kept
                continue
            if np != body:
                e[1] += 1
                if e[0] == 1:
                    self.last_use = sreg
            if eq and _re.fullmatch(rf"[RF]{sreg}", lhs.strip()):
                self.wrote(p, sreg)

    def merged(self) -> None:
        """a move just joined the instruction before: a k=1 use there is no longer alone"""
        if self.last_use is not None and self.last_use in self.pend:
            self.pend[self.last_use][3] = True
        self.last_use = None


ZS = ZeroScale()


DISPATCH = 12      # an md_<step> dispatch's instructions run mode leaves out (dnfw.md.voice._each, emit mode): the
                   # bound (R12 =, MIN, PASS, IF GE JUMP), the table's address (LSHIFT, +, R12 =, +, I12 =),
                   # JUMP (M14, I12), the table's JUMP, the body's JUMP to the end


def _install() -> None:
    """patch the DSL's run mode into the emitted code's count, and attribute every step and access:
    - jumps and calls count (an if's conditional jump, the jump over its else, a loop's back jump; a subroutine
      call's R12 =, I12 =, JUMP, JUMP (M14, I12)), and an md_<step> dispatch's DISPATCH instructions;
    - a constant load is left out when the register is known to hold it, as emit mode does (`known`: forgotten
      as emit mode forgets it, by each instruction's text, and at every label: an if's, a loop's top, a call,
      a dispatch)"""
    P = dsl.Prog
    oe, oc, obr, ocall, oloop, oloopr, ohw, omerge, ocompute = (P.e, P._const, P._branch, P.call, P.loop,
                                                                P.loop_r, P.loop_hw, P._merge, P._compute)
    og, op = dsl.Mem.get, dsl.Mem.put

    def e(self, *a, **k):
        r = oe(self, *a, **k)
        if self.run:
            text = a[0] if a else k["text"]
            self._forget(text)
            CNT.steps(self)
            if "JUMP" in text or "CALL" in text:
                ZS.clear()
            else:
                ZS.text(self, text)
        return r

    def c(self, d, v, note):
        if self.run and self.known.get(d) == v:   # emit mode leaves it out: no step, the merge chain kept
            self.r[d] = v
            return None
        r = oc(self, d, v, note)
        if self.run:
            self.known[d] = v
            CNT.steps(self)
            ZS.load(self, d, v)
        return r

    def merge(self, move, load=None, store=None, k=None):
        r = omerge(self, move, load, store, k)
        if r and self.run:
            if load is not None:
                self.known.pop(load, None)
            ZS.merged()
        return r

    def compute(self, d, text, note, srcs=()):
        before = self.steps
        r = ocompute(self, d, text, note, srcs)
        if self.run and self.steps < before:  # the lone move before joined this instruction
            ZS.merged()
        return r

    def br(self, test, cond, then, else_):
        if not self.run:
            return obr(self, test, cond, then, else_)
        self.steps += 1                        # the conditional jump
        CNT.steps(self)
        self.known.clear()
        ZS.clear()
        if test():
            then()
            if else_:
                self.steps += 1                # the jump over the else
                CNT.steps(self)
        elif else_:
            else_()
        self.known.clear()
        ZS.clear()

    def call(self, name, body):
        if not self.run:
            return ocall(self, name, body)
        self.steps += 4                        # R12 =, I12 =, JUMP, JUMP (M14, I12)
        CNT.steps(self)
        self.known.clear()
        ZS.clear()
        r = ocall(self, name, body)
        self.known.clear()
        ZS.clear()
        return r

    def _top(self, body, jump: bool):
        def b():
            self.known.clear()                 # the loop's top label
            ZS.clear()
            body()
            if jump:
                self.steps += 1                # the loop's back jump
                CNT.steps(self)
        return b

    def loop(self, counter, n_from, body, one=12):
        if not self.run:
            return oloop(self, counter, n_from, body, one)
        r = oloop(self, counter, n_from, _top(self, body, True), one)
        self.known.clear()
        ZS.clear()
        return r

    def loop_r(self, counter, n_from, body, one=12):
        if not self.run:
            return oloopr(self, counter, n_from, body, one)
        r = oloopr(self, counter, n_from, _top(self, body, True), one)
        self.known.clear()
        ZS.clear()
        return r

    def loop_hw(self, n_from, body, cnt=12):
        if not self.run:
            return ohw(self, n_from, body, cnt)
        r = ohw(self, n_from, _top(self, body, False), cnt)
        self.known.clear()
        ZS.clear()
        return r

    def get(self, a):
        CNT.mem(a)
        CNT.depth += 1
        try:
            return og(self, a)
        finally:
            CNT.depth -= 1

    def put(self, a, v):
        CNT.mem(a)
        return op(self, a, v)
    P.e, P._const, P._branch, P.call, P.loop, P.loop_r, P.loop_hw, P._merge, P._compute = (
        e, c, br, call, loop, loop_r, loop_hw, merge, compute)
    dsl.Mem.get, dsl.Mem.put = get, put
    from dnfw.md import voice as MDV
    from dnfw.perc import program as PP
    from dnfw.sampler import program as SP
    oeach = MDV._each

    def _each(p, L, step):                     # its run mode, with the dispatch counted (as the host's)
        if not p.run:
            return oeach(p, L, step)
        CNT.force = ("host", "dispatch")
        MDV.K.vw(p, 0, "mach")
        m = s32(p.r[0])
        k = m if 0 <= m < MDV.N_ALL else MDV.N_ALL - 1
        p.steps += DISPATCH + (k != m)         # (R0 = the last machine's index, when out of range)
        CNT.steps(p)
        CNT.force = None
        p.known.clear()
        ZS.clear()
        getattr(MDV.ALL[k], step)(p, L)
        p.known.clear()
        ZS.clear()
    MDV._each = _each
    for mod in (PP, SP):                       # run_voice calls the module's voice: counted inside it only
        def wrapped(*a, _v=mod.voice, **k):
            CNT.inside += 1
            try:
                return _v(*a, **k)
            finally:
                CNT.inside -= 1
        mod.voice = wrapped


def s32(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def _measure(run_block) -> dict:
    """RUN_BLOCK() runs one block: its counts, attributed"""
    CNT.c.clear()
    ZS.clear()
    CNT.on = True
    CNT.prog, CNT.last = None, 0
    try:
        run_block()
    finally:
        CNT.on = False
    return {k: list(v) for k, v in CNT.c.items()}


def _sum(blocks: list[dict], n: int) -> dict:
    out = collections.defaultdict(lambda: [0, 0, 0])
    for b in blocks:
        for k, v in b.items():
            for i in range(3):
                out[k][i] += v[i]
    return {k: [x / n for x in v] for k, v in out.items()}


def est(v) -> float:
    return v[0] + L2_W * v[1] + DDR_W * v[2]


# -- the engines -------------------------------------------------------------------------------------

def cases():
    """(name, family, setup(h)): SETUP puts the harness's track on the engine"""
    from dnfw.md import voice as MDV
    from dnfw.mnm import machines as MM
    from dnfw.engines.plaits import plaits as PLT
    from dnfw.perc import live as PL
    md = MDV.MM.MACHINES

    def md_case(k):
        return lambda h: h.set_controls(k, PL.defaults(md[k].NAME))
    for k, M in enumerate(md):
        yield M.NAME, M.NAME.split("-")[0], md_case(k)
    for k, n in enumerate(MM.NAMES):
        if n == "PLAITS":
            for mi, m in enumerate(PLT.MODELS):
                if not m:                      # the retired choice: it plays WS
                    continue

                def pl(h, mi=mi, k=k):
                    from dnfw.perc import machines as PMx
                    h.set_mnm_voice(k, list(MM.DEFAULTS["PLAITS"]))
                    slot, w = plaits_word(mi)
                    h._half(PMx.frame_offset(slot), w)
                yield "PLAITS-" + (m or "?"), "PLAITS", pl
        elif n in VARIANTS:                    # 2026-11-12 (the load check): each choice of the cost-changing control
            names, rec, kind = VARIANTS[n]()
            for c, cname in enumerate(names):
                def var(h, k=k, c=c, rec=rec, kind=kind, nn=len(names)):
                    from dnfw.perc import machines as PMx
                    _mnm_setup(h, k)
                    slot, w = choice_word(rec, nn, c, kind)
                    h._half(PMx.frame_offset(slot), w)
                yield f"{n}-{cname}", n, var
        else:
            fam = "MONOMACHINE" if n in MM.MONO_ENGINES else n
            yield n, fam, (lambda h, k=k: _mnm_setup(h, k))


def _sophie_models():
    from dnfw.mnm import machines as MM
    from dnfw.engines.sophie import sophie as SO
    from dnfw.perc import machines as PMx
    from dnfw.waverider import pages as PG
    M = MM.MACHINES[MM.NAMES.index("SOPHIE")]
    return PG._choices(M)["MODL"], PMx.PARAMS[SO.MODL_K], "knob"


def _analog2_filters():
    from dnfw.mnm import machines as MM
    from dnfw.engines.analog2 import analog2 as A2
    from dnfw.perc import machines as PMx
    from dnfw.waverider import pages as PG
    M = MM.MACHINES[MM.NAMES.index("ANALOG2")]
    return PG._choices(M)["FLT2"], PMx.FX_PARAMS[A2.PNAMES2.index("FLT2")], "frac"


VARIANTS = {"SOPHIE": _sophie_models, "ANALOG2": _analog2_filters}   # name -> () -> (choice names, record, kind)


def choice_word(rec, n: int, c: int, kind: str = "knob") -> tuple[int, int]:
    """(frame slot, word) of record REC = (rid, slot, lo, top) choosing choice C of N as the DSP reads it: "knob"
    (dnfw.mnm.core.knob: trunc(v / top x 128) x N >> 7: PLAITS', SOPHIE's MODL, the page's choice) or "frac"
    (ANALOG 2's page-2 choices: min(N - 1, trunc(v / top x N))); the record value in the middle of C's range, away
    from float edges"""
    _rid, slot, lo, top = rec
    if kind == "knob":
        vs = [v for v in range(top + 1) if (int(v / top * 128) * n) >> 7 == c]
    else:
        vs = [v for v in range(top + 1) if min(n - 1, int(v / top * n)) == c]
    return slot, (vs[len(vs) // 2] + lo) << 8


def plaits_word(mi: int) -> tuple[int, int]:
    """(frame slot, word) of PLAITS' MODL record choosing model MI as the DSP reads it (dnfw.mnm.core.knob:
    trunc(v / top x 128), then x N >> 7): the record value in the middle of MI's range. (plaits.knob_of(MI) through
    live.knob_word can land on the model below: ADD's knob 40 has no value on a 0..100 record, and plays FM)"""
    from dnfw.engines.plaits import plaits as PLT
    from dnfw.perc import machines as PMx
    _rid, slot, lo, top = PMx.PARAMS[PLT.MODL_K]
    vs = [v for v in range(top + 1) if PLT.model_of(int(v / top * 128)) == mi]
    return slot, (vs[len(vs) // 2] + lo) << 8


def _mnm_setup(h, k: int) -> None:
    """Monomachine voice K at its defaults, as the runner's frame (sharc_waverider_m5.mnm_words) holds them"""
    from dnfw.mnm import machines as MM
    from dnfw.perc import machines as PMx, live as PL
    n = MM.NAMES[k]
    h.set_mnm_voice(k, list(MM.DEFAULTS[n]))
    if n == "DRONE":                           # OCT (page 2) at the start MACHINE SEL writes, not 0 (-3 octaves)
        _rid, slot, lo, top = PMx.FX_PARAMS[2]
        h._half(PMx.frame_offset(slot), PL.knob_word(MM.MACHINES[k].DEFAULTS2[2], top, lo))


def schedule(block) -> dict:
    """BLOCK(trig) runs one block (counted when the counter is on). The schedule sharc_cost.py runs too: blocks
    0..9 on a fresh voice, a note on blocks 1 and 8; start = the dearer of blocks 1, 2, steady = the mean of
    blocks 4..7, trig = the dearer of blocks 8, 9"""
    got = [_measure(lambda b=b: block(b in NOTES)) for b in range(BLOCKS)]

    def dearer(bs):
        return max((got[b] for b in bs), key=lambda c: est([sum(v[i] for v in c.values()) for i in range(3)]))
    return {"start": dearer(START_B), "steady": _sum([got[b] for b in STEADY_B], len(STEADY_B)),
            "trig": dearer(TRIG_B)}


def _first_prog(run):
    """RUN() with the first run-mode Prog it makes as the counted one"""
    orig = dsl.Prog.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        if CNT.prog is None and self.run:
            CNT.prog, CNT.last = self, 0
    dsl.Prog.__init__ = init
    try:
        return run()
    finally:
        dsl.Prog.__init__ = orig


def run_engine(setup) -> dict:
    from dnfw.md import core as MDK
    from dnfw.perc import live as PL
    from dnfw.mnm import dpro as MNP
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    h.words.update(MNP.bench_words(h.L.md.mnm))   # the Digibank stand-in DENS and DDRW read (built at power-on)
    setup(h)
    return schedule(lambda trig: _first_prog(lambda: h.block(note=60, trig=trig)))


def sampler_cases():
    from dnfw.sampler import machines as SM
    for name in ("ONESHOT", "WERP", "STRETCH", "REPITCH", "GRID", "SLICE"):
        if name in SM.TYPE_OF:
            yield name, SM.TYPE_OF[name]


def run_sampler(mtype: int) -> dict:
    from dnfw.sampler import live as SL
    h = SL.Harness()
    h.defaults()
    return schedule(lambda trig: _first_prog(lambda: h.block(mtype, note=60, trig=trig)))


def split(counts: dict) -> dict:
    """{'host': [i, l2, ddr], 'engine': [...], 'buckets': {name: est}}"""
    host, eng = [0, 0, 0], [0, 0, 0]
    buckets = collections.defaultdict(float)
    for (side, b), v in counts.items():
        tgt = host if side == "host" else eng
        for i in range(3):
            tgt[i] += v[i]
        buckets[f"{side}:{b}"] += est(v)
    return {"host": host, "engine": eng, "buckets": dict(buckets)}


def row(name: str, fam: str, r: dict, sampler: bool = False) -> dict:
    out = {"name": name, "family": fam}
    for kind in ("steady", "trig", "start"):
        s = split(r[kind])
        tot = [s["host"][i] + s["engine"][i] for i in range(3)]
        out[kind] = {"instructions": round(tot[0]), "L2": round(tot[1]), "DDR": round(tot[2]),
                     "cost": round(est(tot)), "host": round(est(s["host"])), "engine": round(est(s["engine"])),
                     "host_counts": [round(x) for x in s["host"]], "engine_counts": [round(x) for x in s["engine"]],
                     "buckets": {k: round(v) for k, v in sorted(s["buckets"].items(), key=lambda kv: -kv[1])}}
    st = out["steady"]["cost"]
    out["voices_in_ours"] = int(OURS // st) if st else None
    out["sixteen_of_ours"] = round(16 * st / OURS, 3)
    out["sampler"] = sampler
    return out


# -- the loop around the voices (emitted text; not in the model) -------------------------------------

def loop_overhead() -> dict:
    """the per-slot loop's and mnm_ages' instruction lines, from the assembled text: an upper bound on the
    straight path (every line of the slot loop between its label and the voice's code, and the guard's path)"""
    from dnfw.perc import program as PP, live as PL, dsl as D
    L = PL.layout()
    p = D.Prog("emit", prefix="cost")
    p.spill = L.md.C["ash"]
    PP.mnm_ages(p, L)
    ages = [ln for ln in p.lines if ln.startswith("      ") and not ln.strip().startswith("//")]
    return {"mnm_ages_lines": len(ages)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--steps", default="cost", help="cost (the table), host (+ the host's buckets)")
    ap.add_argument("--only", default="", help="NAME,.. (engine names as the table prints them)")
    ap.add_argument("--json", default="out/dsp_cost/report.json")
    ap.add_argument("--md", default="", help="write the markdown table here")
    a = ap.parse_args()
    steps = set(a.steps.split(","))
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    _install()
    rows, bad = [], []
    t0 = time.time()
    for name, fam, setup in cases():
        if only and name not in only:
            continue
        try:
            rows.append(row(name, fam, run_engine(setup)))
        except Exception as ex:                # one engine's harness problem must not hide the rest: reported, exit 1
            bad.append(f"{name}: {type(ex).__name__}: {ex}")
            print(f"  {name}: ERROR {type(ex).__name__}: {ex}", flush=True)
            continue
        _print(rows[-1], "host" in steps)
    for name, mtype in sampler_cases():
        if only and name not in only:
            continue
        try:
            rows.append(row(name, "SAMPLE", run_sampler(mtype), sampler=True))
        except Exception as ex:
            bad.append(f"{name}: {type(ex).__name__}: {ex}")
            print(f"  {name}: ERROR {type(ex).__name__}: {ex}", flush=True)
            continue
        _print(rows[-1], "host" in steps)
    rep = {"method": "instructions + 4 L2 + 10 DDR, model run mode with jumps/calls", "ours": OURS, "frame": FRAME,
           "rows": rows, "errors": bad, "seconds": round(time.time() - t0, 1)}
    if "loop" in steps:
        rep["loop"] = loop_overhead()
        print("  loop:", rep["loop"])
    if a.json:
        pathlib.Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    if a.md:
        pathlib.Path(a.md).write_text(markdown(rows))
    print(f"{'PASS' if not bad else 'FAIL'}: {len(rows)} engines measured, {len(bad)} errors, {rep['seconds']} s")
    return 0 if not bad else 1


def _print(r: dict, buckets: bool) -> None:
    s, t = r["steady"], r["trig"]
    print(f"  {r['name']:14s} steady {s['cost']:7,d} (host {s['host']:6,d} engine {s['engine']:7,d})  "
          f"trig {t['cost']:7,d} (host {t['host']:6,d})  start {r['start']['cost']:7,d}  "
          f"fit {r['voices_in_ours']}", flush=True)
    if buckets:
        for k, v in s["buckets"].items():
            if v:
                print(f"      {k:22s} {v:7,d}")


def markdown(rows: list[dict]) -> str:
    out = ["| engine | family | steady block | host | engine's own | host share | trig block | start block | "
           "voices in 310k | 16 voices, of 310k |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in sorted(rows, key=lambda r: -r["steady"]["cost"]):
        s = r["steady"]
        share = f"{100 * s['host'] / s['cost']:.0f} %" if s["cost"] else "-"
        host = f"{s['host']:,}" if not r["sampler"] else "(own)"
        eng = f"{s['engine']:,}" if not r["sampler"] else "-"
        out.append(f"| {r['name']} | {r['family']} | {s['cost']:,} | {host} | {eng} | "
                   f"{share if not r['sampler'] else '-'} | {r['trig']['cost']:,} | {r['start']['cost']:,} | "
                   f"{r['voices_in_ours']} | {100 * r['sixteen_of_ours']:.0f} % |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
