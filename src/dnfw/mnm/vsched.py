"""(perf, 2026-11-12) A list scheduler with virtual registers for straight-line SHARC float code.

The caller writes its operations in program order on virtual values (float multiply / add / subtract / MIN /
MAX, loads and stores through I0..I3 at an offset, constants, a conditional compute after the ALU op that sets
its flags, any other lone instruction). The scheduler packs them into as few instructions as the dependences
allow (one compute an instruction: a single operation, or the multiplier and the ALU together in the
multifunction form, F0-F3 x F4-F7 and F8-F11 +- F12-F15; one memory move an instruction; a constant from a table
rides as a move, else loads alone), and assigns the physical registers as it goes, choosing each value's
register class from the operation that will consume it. Every operation keeps its operands and its order against
every operation it depends on (`Prog.par`: an instruction reads every operand before it writes), so the results
are bit for bit those of the operations run one at a time in program order.

    s = VS(p, ktab=KTab(...))
    x = s.ld(0, -3); y = s.f("*", x, s.k(0.5)); s.st(0, -3, y)
    s.emit()
"""

from __future__ import annotations

from ..perc.dsl import Prog, bits, f32

MUL_A, MUL_B, ALU_A, ALU_B = range(0, 4), range(4, 8), range(8, 12), range(12, 16)
PAIR_OPS = ("+", "-")


class KTab:
    """A table of 32-bit constants in memory, read by a move: WINDOWS maps an I register to the table index its
    offset 0 points at (an offset -32..31 reaches 64 entries). Entries are appended as they are first asked for;
    `words` lists them for whoever fills the table."""

    def __init__(self, windows: dict[int, int]):
        self.windows = dict(windows)
        self.words: list[int] = []
        self.index: dict[int, int] = {}
        self.cap = 64 * len(windows)
        self.frozen = False                      # True: a word not in the table loads as an immediate

    def at(self, w: int) -> tuple[int, int] | None:
        """(I register, offset) of word W, or None when it is past every window"""
        if w not in self.index:
            if self.frozen or len(self.words) >= self.cap:
                return None
            self.index[w] = len(self.words)
            self.words.append(w)
        n = self.index[w]
        for i, base in self.windows.items():
            if -32 <= n - base < 32:
                return i, n - base
        return None


class Deadlock(AssertionError):
    pass


class Op:
    __slots__ = ("kind", "op", "d", "srcs", "i", "k", "x", "fn", "cond", "flag", "n", "lone", "alu", "mul", "wishes")

    def __init__(self, kind, op=None, d=None, srcs=(), i=None, k=None, x=None, fn=None, cond=None, flag=None,
                 wishes=None):
        self.kind, self.op, self.d, self.srcs = kind, op, d, list(srcs)
        self.i, self.k, self.x, self.fn, self.cond, self.flag = i, k, x, fn, cond, flag
        self.wishes = wishes or {}
        self.lone = kind in ("raw", "if", "k", "br")
        self.alu = kind == "f" and op != "*"
        self.mul = kind == "f" and op == "*"


class VS:
    RESERVE = 6                                  # registers a load or constant leaves free unless it completes an op's operands
    MOVE_WINDOW = 96                             # how far ahead (ops) a load, store or constant may be taken from
    NEAR = 24                                    # how far ahead a load that completes no op's operands may be taken from
    ORDER = 0                                    # candidates by program order (an op's index less ORDER x its critical path)
    STRICT = True                                # a value waits for a register of its class (while anything else can go)
    TRACE = False
    HALVE = True
    PLENTY = 5                                   # free registers above which the whole window is open
    TIGHT = 20                                   # the window while they are scarce

    def __init__(self, p: Prog, ktab: KTab | None = None, window: int = 48, reserved=()):
        self.p, self.ktab, self.window = p, ktab, window
        self.ops: list[Op] = []
        self.nv = 0
        self.reserved = set(reserved)
        self.trace: list = []
        self.stats = {"instr": 0, "pairs": 0, "moves": 0, "lone": 0, "imm": 0, "mul": 0, "alu": 0, "nolone": 0,
                      "ops": 0, "miss": 0}

    # -- the operations, in program order --------------------------------------------------
    def v(self) -> int:
        self.nv += 1
        return self.nv - 1

    def f(self, op: str, a: int, b: int) -> int:
        assert op in ("+", "-", "*", "MIN", "MAX")
        d = self.v()
        self.ops.append(Op("f", op, d, (a, b)))
        return d

    def ld(self, i: int, k: int) -> int:
        assert -32 <= k < 32 and i in range(4)
        d = self.v()
        self.ops.append(Op("ld", d=d, i=i, k=k))
        return d

    def st(self, i: int, k: int, a: int) -> None:
        assert -32 <= k < 32 and i in range(4)
        self.ops.append(Op("st", srcs=(a,), i=i, k=k))

    def k(self, x: float) -> int:
        """a float constant: from the table as a move when there is one, else an immediate load alone"""
        return self._const(bits(f32(x)), x)

    def ki(self, n: int) -> int:
        return self._const(n & 0xFFFFFFFF, None)

    def _const(self, word: int, x) -> int:
        d = self.v()
        at = self.ktab.at(word) if self.ktab is not None else None
        if at is not None:
            self.ops.append(Op("ld", d=d, i=at[0], k=at[1], x=word))
        else:
            self.ops.append(Op("k", d=d, x=None if x is None else x, k=word))
        return d

    def raw(self, fn, srcs=(), write: bool = True, wishes=None) -> int | None:
        """one instruction of any other kind, alone: FN(p, d, *srcs) emits it on the physical registers;
        WISHES {source index: registers} where the instruction form needs a register class"""
        d = self.v() if write else None
        self.ops.append(Op("raw", d=d, srcs=srcs, fn=fn, wishes=wishes))
        return d

    def flag(self, op: str, a: int, b: int) -> int:
        """an ALU + or - whose flags the `iff` right after it (in program order) decides on; its value is usable"""
        assert op in PAIR_OPS
        d = self.v()
        self.ops.append(Op("f", op, d, (a, b), flag=True))
        return d

    def iff(self, cond: str, d_old: int, a: int, op: str = "PASS", b: int | None = None, kind: str = "f") -> int:
        """IF COND Fd = Fa op Fb (op PASS: Fa; KIND 'i': Rd = Ra op Rb, integer), Fd the register of D_OLD,
        which dies here: the value is D_OLD unless COND. Must come right after a `flag`."""
        assert self.ops and self.ops[-1].flag, "iff must follow flag"
        d = self.v()
        srcs = (d_old, a) if op == "PASS" else (d_old, a, b)
        self.ops.append(Op("if", op, d, srcs, cond=cond, flag=len(self.ops) - 1, x=kind,
                           wishes={1: list(range(8, 16))} if kind == "i" and op == "+" else None))
        return d

    def branch(self, cond: str, dmod: int, reads, body, temps: int = 2) -> int:
        """IF COND JUMP to a block out of line that reads the values READS, changes DMOD in its register and
        comes back: BODY(p, regs, temps) emits it on the physical registers (REGS those of DMOD then READS,
        TEMPS registers free at that point). Must come right after a `flag`; the value is DMOD unless COND.
        Emit mode puts the blocks where `flush` is called (after the loop they sit in); run mode runs BODY
        here when COND holds."""
        assert self.ops and self.ops[-1].flag, "branch must follow flag"
        d = self.v()
        self.ops.append(Op("br", d=d, srcs=(dmod, *reads), fn=body, cond=cond, flag=len(self.ops) - 1, x=temps))
        return d

    DEFERRED: list = []                          # (block label, return label, body, regs, temps) to flush

    @classmethod
    def flush(cls, p: Prog) -> None:
        """emit mode: the out-of-line blocks, each ending with a jump back"""
        for blk, ret, body, regs, temps in cls.DEFERRED:
            p.place(blk)
            body(p, regs, temps)
            p.jump("", ret)
        cls.DEFERRED.clear()

    # -- scheduling ---------------------------------------------------------------------------
    def _deps(self):
        ops = self.ops
        n = len(ops)
        defs: dict[int, int] = {}
        uses: dict[int, list[int]] = {}
        last_st: dict[tuple, int] = {}
        lds_since: dict[tuple, list[int]] = {}
        deps = [[] for _ in range(n)]            # (pred, strict): strict = an earlier instruction
        for j, o in enumerate(ops):
            for s in o.srcs:
                deps[j].append((defs[s], True))
            if o.kind in ("if", "br"):           # writes d_old's register: every other reader of d_old first
                for q in uses.get(o.srcs[0], []):
                    deps[j].append((q, True))
                deps[j].append((o.flag, True))
            for s in o.srcs:
                uses.setdefault(s, []).append(j)
            if o.kind in ("ld", "st"):
                key = (o.i, o.k)
                if o.kind == "ld":
                    if key in last_st:
                        deps[j].append((last_st[key], True))
                    lds_since.setdefault(key, []).append(j)
                else:
                    for q in lds_since.pop(key, []):
                        deps[j].append((q, True))
                    if key in last_st:
                        deps[j].append((last_st[key], True))
                    last_st[key] = j
            if o.d is not None:
                defs[o.d] = j
        return deps, uses

    @staticmethod
    def _pairable(m: Op, a: Op, regmap):
        """the multifunction form of multiply M and ALU op A on their physical registers, or None"""
        ma, mb = (regmap[s] for s in m.srcs)
        if not (ma in MUL_A and mb in MUL_B):
            if mb in MUL_A and ma in MUL_B:
                ma, mb = mb, ma
            else:
                return None
        aa, ab = (regmap[s] for s in a.srcs)
        if not (aa in ALU_A and ab in ALU_B):
            if a.op == "+" and ab in ALU_A and aa in ALU_B:
                aa, ab = ab, aa
            else:
                return None
        return (ma, mb), (aa, ab)

    CACHE: dict = {}                             # key -> (the schedule, the registers, the stats): the same
                                                 # operations schedule the same way (run mode asks every sample)

    def emit(self, key=None) -> int:
        """schedules (the window halved on a deadlock: greedy hoisting into 16 registers) and emits; KEY names
        a region whose schedule is kept for the next time its operations are the same"""
        if key is not None and key in self.CACHE:
            lines, preg, stats, sig = self.CACHE[key]
            if sig == self._signature():
                self.stats.update(stats)
                self._emit(lines, preg)
                return self.stats["instr"]
        window, move_window = self.window, self.MOVE_WINDOW
        reserve = self.RESERVE
        while True:
            try:
                lines, preg = self._schedule(window, move_window, reserve)
                break
            except Deadlock:
                if not self.HALVE:
                    raise
                if reserve < 12:                 # first fewer registers for loads ahead, then a shorter window
                    reserve += 2
                    continue
                if window <= 4:
                    raise
                window, move_window, reserve = max(4, window // 2), max(4, move_window // 2), self.RESERVE
        if key is not None:
            self.CACHE[key] = (lines, preg, dict(self.stats), self._signature())
        self._emit(lines, preg)
        return self.stats["instr"]

    def _signature(self) -> tuple:
        return tuple((o.kind, o.op, o.d, tuple(o.srcs), o.i, o.k, o.cond, o.flag) for o in self.ops)

    def _schedule(self, window: int, move_window: int, reserve: int):
        ops = self.ops
        n = len(ops)
        deps, uses = self._deps()
        defs = {o.d: j for j, o in enumerate(ops) if o.d is not None}
        succ = [[] for _ in range(n)]
        for j, dj in enumerate(deps):
            for q, _s in dj:
                succ[q].append(j)
        prio = [0] * n
        for j in reversed(range(n)):
            prio[j] = 1 + max((prio[q] for q in succ[j]), default=0)
        uses_left = {v: len(uses.get(v, [])) for v in range(self.nv)}
        at: dict[int, int] = {}
        phys: dict[int, int] = {}
        free = [r for r in range(16) if r not in self.reserved]
        cyc = 0
        first = 0
        rank: dict[int, int] = {}
        forced: int | None = None
        stall = 0
        lines: list[list] = []

        def ready(j, c):
            return j not in at and all(q in at and at[q] < c for q, _s in deps[j])

        def need(v: int) -> list[int] | None:
            """the registers value V must go to (an instruction form's own need), or None"""
            for q in uses.get(v, []):
                o = ops[q]
                if o.kind in ("raw", "if") and o.wishes and v in o.srcs and o.srcs.index(v) in o.wishes:
                    return list(o.wishes[o.srcs.index(v)])
            return None

        def wish(v: int, placed: set[int]) -> list[int]:
            """the register classes value V should go to, from its first consumer"""
            for q in uses.get(v, []):
                o = ops[q]
                if o.kind != "f" or o.op in ("MIN", "MAX"):
                    return []
                a, b = o.srcs
                other = b if a == v else a
                if o.op == "*":
                    cls = (MUL_A, MUL_B)
                elif o.op == "-":
                    return list(ALU_A if a == v else ALU_B)
                else:
                    cls = (ALU_A, ALU_B)
                r = phys.get(other)
                if r is not None and other not in placed:
                    if r in cls[0]:
                        return list(cls[1])
                    if r in cls[1]:
                        return list(cls[0])
                    return []
                return list(cls[0]) + list(cls[1])
            return []

        def pick(v: int, avail: list[int], taken: set[int], relaxed: bool = False) -> int | None:
            must = need(v)
            if must is not None:
                m = [r for r in must if r in avail and r not in taken]
                return m[0] if m else None
            wanted = wish(v, set())
            w = [r for r in wanted if r in avail and r not in taken]
            if w:
                return w[0]
            if wanted and self.STRICT and not relaxed:
                return None                      # wait for a register of its class rather than lose the pairing
            rest = [r for r in avail if r not in taken]
            return rest[0] if rest else None

        def enables(j: int, group: list[int]) -> bool:
            """the value op J defines completes the operands of its first consumer (an operand that is itself a
            load or constant still to go counts: it can follow at once)"""
            o = ops[j]
            if o.d is None:
                return True
            have = set(phys) | {ops[q].d for q in group if ops[q].d is not None} | {o.d}
            for q in uses.get(o.d, []):
                return all(s in have or ops[defs[s]].kind in ("ld", "k") for s in ops[q].srcs)
            return False

        def roomy(j: int, group: list[int]) -> bool:
            """a load or constant may take a register: it completes an op's operands, or enough registers stay
            free and it is near (in program order) the first op still to go"""
            if rank[j] > move_window:
                return False
            taken = len([q for q in group if ops[q].d is not None])
            room = len(free) + len(dying(group + [j])) - taken
            if enables(j, group):
                return room > 0
            return room > reserve and rank[j] <= self.NEAR

        def dying(group: list[int]) -> list[int]:
            cnt: dict[int, int] = {}
            for j in group:
                for s in ops[j].srcs:
                    cnt[s] = cnt.get(s, 0) + 1
            return [phys[v] for v, c in cnt.items() if uses_left[v] == c]

        def pairable(m: Op, a: Op):
            return self._pairable(m, a, phys)

        def place(group: list[int], regs: dict[int, int]):
            nonlocal cyc
            for j in group:
                at[j] = cyc
                for s in ops[j].srcs:
                    uses_left[s] -= 1
            for j in group:
                for s in ops[j].srcs:
                    if uses_left[s] == 0 and s in phys:
                        r = phys.pop(s)
                        if r not in free:
                            free.append(r)
            for j in group:
                o = ops[j]
                if o.d is not None:
                    r = regs[j]
                    phys[o.d] = r
                    if r in free:
                        free.remove(r)
                    if uses_left[o.d] == 0:        # a value nobody reads (a flag's): its register is free again
                        phys.pop(o.d)
                        free.append(r)
            free.sort()

        while len(at) < n:
            while first < n and first in at:
                first += 1
            if forced is not None:
                j = forced
                o = ops[j]
                forced = None
                d_old = o.srcs[0]
                assert uses_left[d_old] == o.srcs.count(d_old), "iff: d_old must die at the iff"
                r = phys[d_old]
                if o.kind == "br":
                    busy = {phys[s] for s in o.srcs}
                    temps = [t for t in free if t not in busy][:o.x]
                    assert len(temps) == o.x, "branch: too few free registers for its block"
                    lines.append(("br", j, {j: r}, temps))
                else:
                    lines.append(("if", j, {j: r}))
                place([j], {j: r})
                cyc += 1
                continue
            # the first WINDOW unscheduled ops; fewer while registers are scarce (ops far ahead start new chains,
            # which hold registers: the near ones finish chains and free them)
            eff = window if len(free) > self.PLENTY else self.TIGHT if len(free) > 2 else 6
            pend = [j for j in range(first, n) if j not in at][:eff]
            rank = {j: q for q, j in enumerate(pend)}
            cand = [j for j in pend if ready(j, cyc)]
            if self.ORDER:
                cand.sort(key=lambda j: (j - self.ORDER * prio[j], j))
            else:
                cand.sort(key=lambda j: (-prio[j], j))
            for relaxed in (False, True):        # the reserve holds only while something else can go
                group = []
                regs = {}
                comp = []
                move = None
                lone = None
                for j in cand:
                    o = ops[j]
                    if o.kind in ("if", "br"):
                        continue                 # only ever forced
                    if o.flag and (j + 1 >= n or not all(q in at and at[q] <= cyc for q, _s in deps[j + 1] if q != j)):
                        continue                 # its iff could not follow next cycle
                    if o.flag and ops[j + 1].kind == "br" and len(free) + len(dying([j])) < ops[j + 1].x + 2:
                        continue                 # its block needs free registers
                    if o.lone:
                        if not group:
                            if o.kind == "k" and not (roomy(j, group) or (relaxed and free)):
                                continue
                            avail = free + dying([j])
                            if o.d is None:
                                lone = j
                                break
                            r = pick(o.d, avail, set(), relaxed)
                            if r is None:
                                continue
                            lone = j
                            regs[j] = r
                            break
                        continue
                    if o.kind in ("ld", "st"):
                        if move is not None or (rank[j] > move_window and not relaxed):
                            continue
                        if o.kind == "ld":
                            if not (roomy(j, group) or (relaxed and len(free) + len(dying(group)) > len(regs))):
                                continue
                            taken = set(regs.values())
                            r = pick(o.d, free + dying(group + [j]), taken, relaxed)
                            if r is None:
                                continue
                            regs[j] = r
                        move = j
                        group.append(j)
                        continue
                    # a float op
                    if len(comp) >= 2 or (len(comp) == 1 and (o.alu == ops[comp[0]].alu or o.op in ("MIN", "MAX")
                                                            or ops[comp[0]].op in ("MIN", "MAX"))):
                        continue
                    if comp:
                        m, a = (ops[comp[0]], o) if ops[comp[0]].mul else (o, ops[comp[0]])
                        if pairable(m, a) is None:
                            continue
                        if o.flag and ops[comp[0]].flag:
                            continue
                    taken = set(regs.values())
                    r = pick(o.d, free + dying(group + [j]), taken, relaxed)
                    if r is None:
                        continue
                    regs[j] = r
                    comp.append(j)
                    group.append(j)
                if group or lone is not None:
                    break
            if self.TRACE:
                rd = [j for j in cand if ops[j].kind == "f"]
                self.trace.append((cyc, [(j, ops[j].kind, ops[j].op, regs.get(j), [phys.get(s) for s in ops[j].srcs])
                                         for j in (group if group else [lone] if lone is not None else [])],
                                   len(cand), [(j, ops[j].op, [phys.get(s) for s in ops[j].srcs]) for j in rd[:6]],
                                   sorted(free)))
            if lone is not None:
                lines.append(("lone", lone, regs))
                place([lone], regs)
                o = ops[lone]
                if o.flag:
                    forced = lone + 1
                cyc += 1
                stall = 0
                continue
            if not group:
                stall += 1
                if stall >= 4:
                    live = []
                    for v, r in sorted(phys.items(), key=lambda t: t[1]):
                        q = next((i for i, o in enumerate(ops) if o.d == v), None)
                        cons = [(u, ops[u].kind, ops[u].op, u in at) for u in uses.get(v, [])]
                        live.append(f"  F{r} = v{v} (op {q} {ops[q].kind} {ops[q].op}) uses {cons}")
                    raise Deadlock(f"vsched: stuck at op {first} ({ops[first].kind} {ops[first].op}), "
                                   f"live {len(phys)}, cycle {cyc}, scheduled {len(at)}/{n}\n" + "\n".join(live))
                cyc += 1
                continue
            stall = 0
            lines.append(("par", list(group), dict(regs)))
            place(group, regs)
            for j in group:
                if ops[j].flag:
                    forced = j + 1
            cyc += 1
        self.stats["mul"] = sum(1 for o in ops if o.mul)
        self.stats["alu"] = sum(1 for o in ops if o.alu)
        self.stats["nolone"] = sum(1 for o in ops if o.lone)
        self.stats["ops"] = n
        self.stats["kld"] = sum(1 for o in ops if o.kind == "ld" and o.x is not None)
        self.stats["sld"] = sum(1 for o in ops if o.kind == "ld" and o.x is None)
        self.stats["st"] = sum(1 for o in ops if o.kind == "st")
        self.stats["window"] = window
        self.stats["reserve"] = reserve
        self.stats["cp"] = max(prio)
        preg: dict[int, int] = {}                 # value -> its register, for the emitter
        for line in lines:
            kind, what, regs = line[:3]
            group = what if kind == "par" else [what]
            for j in group:
                if ops[j].d is not None:
                    preg[ops[j].d] = regs[j]
        return lines, preg

    def _emit(self, lines, preg) -> None:
        p, ops = self.p, self.ops
        for line in lines:
            kind, what, regs = line[:3]
            group = what if kind == "par" else [what]
            if kind == "br":
                o = ops[what]
                regl = [regs[what]] + [preg[s] for s in o.srcs[1:]]
                if p.run:
                    last = p._alu
                    assert last is not None, "branch must follow an ALU op"
                    an, az = bool(last >> 31), not last & 0x7FFFFFFF
                    lt, le = an and not az, an or az
                    take = {"LT": lt, "LE": le, "GT": not le, "GE": not lt, "EQ": az, "NE": not az}[o.cond]
                    p.steps += 1                 # the conditional jump
                    if take:
                        o.fn(p, regl, line[3])
                        p.steps += 1             # the jump back
                else:
                    blk, ret = p.label("blk"), p.label("ret")
                    p.jump(o.cond, blk)
                    p.place(ret)
                    self.DEFERRED.append((blk, ret, o.fn, regl, line[3]))
                self.stats["lone"] += 1
            elif kind == "if":
                o = ops[what]
                r = regs[what]
                if o.x == "i":
                    p.iop_if(o.cond, r, preg[o.srcs[1]], o.op, preg[o.srcs[2]])
                elif o.op == "PASS":
                    p.fop_if(o.cond, r, preg[o.srcs[1]], "PASS")
                else:
                    p.fop_if(o.cond, r, preg[o.srcs[1]], o.op, preg[o.srcs[2]])
                self.stats["lone"] += 1
            elif kind == "lone":
                o = ops[what]
                if o.kind == "raw":
                    o.fn(p, *([regs[what]] if o.d is not None else []), *(preg[s] for s in o.srcs))
                    self.stats["lone"] += 1
                elif o.kind == "k":
                    p.iconst(regs[what], o.k)
                    self.stats["imm"] += 1
                else:
                    assert False, o.kind
            else:
                parts = []
                comps = [j for j in group if ops[j].kind == "f"]
                if len(comps) == 2:
                    m, a = (comps[0], comps[1]) if ops[comps[0]].mul else (comps[1], comps[0])
                    (ma, mb), (aa, ab) = self._pairable(ops[m], ops[a], preg)
                    parts += [("*", regs[m], ma, mb), (ops[a].op, regs[a], aa, ab)]
                    self.stats["pairs"] += 1
                elif comps:
                    o = ops[comps[0]]
                    parts.append(("op", regs[comps[0]], preg[o.srcs[0]], o.op, preg[o.srcs[1]]))
                for j in group:
                    o = ops[j]
                    if o.kind == "ld":
                        parts.append(("ldk", regs[j], o.k, o.i))
                        self.stats["moves"] += 1
                    elif o.kind == "st":
                        parts.append(("stk", o.k, o.i, preg[o.srcs[0]]))
                        self.stats["moves"] += 1
                p.par(*parts)
                if any(ops[j].flag for j in comps):
                    pass
            self.stats["instr"] += 1
        return self.stats["instr"]
