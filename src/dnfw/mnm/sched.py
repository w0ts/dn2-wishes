"""(perf, 2026-11-12) A list scheduler for straight-line float code: a list of operations in program order (float
multiply / add / subtract / MIN / MAX, a load or a store through I0..I3 at an offset, a constant) packed into as few
SHARC instructions as the dependences allow, each instruction one compute (a single operation, or the multiplier
and the ALU together in the multifunction form's registers: F0-F3 x F4-F7, F8-F11 +- F12-F15) and one memory move,
or a constant load alone. Every operation keeps its operands and its order against every operation it depends on,
so the results are bit for bit those of the operations run one at a time (`Prog.par`: an instruction reads every
operand before it writes). The registers are the caller's: it chooses them so the pairs it wants can form.

    s = Sched()
    s.ld(4, -3, 0); s.mul(8, 0, 4); s.add(9, 8, 12); s.st(-3, 0, 9)
    s.emit(p)
"""

from __future__ import annotations

from ..perc.dsl import Prog

MUL_A, MUL_B = range(0, 4), range(4, 8)
ALU_A, ALU_B = range(8, 12), range(12, 16)


class Op:
    __slots__ = ("kind", "d", "a", "b", "k", "i", "x", "reads", "writes", "mem", "n")

    def __init__(self, kind, d=None, a=None, b=None, k=None, i=None, x=None, reads=None, writes=None):
        self.kind, self.d, self.a, self.b, self.k, self.i, self.x = kind, d, a, b, k, i, x
        self.reads = tuple(reads) if reads is not None else tuple(
            r for r in ((a, b) if kind in ("*", "+", "-", "MIN", "MAX") else (a,) if kind == "st" else ())
            if r is not None)
        self.writes = tuple(writes) if writes is not None else (d,) if d is not None else ()
        self.mem = (i, k) if kind in ("ld", "st") else None


class Sched:
    def __init__(self) -> None:
        self.ops: list[Op] = []

    # -- the operations, in program order ---------------------------------------------
    def mul(self, d: int, a: int, b: int) -> None:
        self.ops.append(Op("*", d, a, b))

    def add(self, d: int, a: int, b: int) -> None:
        self.ops.append(Op("+", d, a, b))

    def sub(self, d: int, a: int, b: int) -> None:
        self.ops.append(Op("-", d, a, b))

    def fop(self, d: int, a: int, op: str, b: int) -> None:
        self.ops.append(Op(op, d, a, b))

    def ld(self, d: int, k: int, i: int) -> None:
        """Fd = DM(k, Ii), k the instruction's offset (-32..31, after Prog.bk)"""
        self.ops.append(Op("ld", d=d, k=k, i=i))

    def st(self, k: int, i: int, s: int) -> None:
        self.ops.append(Op("st", a=s, k=k, i=i))

    def const(self, d: int, x: float) -> None:
        self.ops.append(Op("k", d=d, x=x))

    def raw(self, fn, reads, writes) -> None:
        """any other one instruction (an integer op, TRUNC, FLOAT ..), alone in its instruction: FN(p) emits it;
        READS / WRITES its registers"""
        self.ops.append(Op("k", x=fn, reads=reads, writes=writes))

    # -- scheduling --------------------------------------------------------------------
    def _deps(self):
        """for each op, (pred, strict) pairs: strict = a later instruction, else the same one or later"""
        ops, deps = self.ops, []
        for j, o in enumerate(ops):
            dj = []
            for q in range(j):
                e = ops[q]
                strict = None
                if set(o.reads) & set(e.writes) or set(o.writes) & set(e.writes):
                    strict = True                        # read after write, write after write
                elif set(o.writes) & set(e.reads):
                    strict = False                       # write after read: the same instruction reads first
                if o.mem is not None and e.mem is not None and (o.kind == "st" or e.kind == "st"):
                    if o.mem == e.mem or o.mem[0] != e.mem[0]:   # the same word, or two I registers (may alias)
                        strict = True
                if o.kind == "k" or e.kind == "k":
                    pass
                if strict is not None:
                    dj.append((q, strict))
            deps.append(dj)
        return deps

    @staticmethod
    def _pairable(m: Op, a: Op):
        """the multifunction form of multiply M with ALU op A, its operands swapped where that is the same
        result (both commute), or None"""
        if m.kind != "*" or a.kind not in ("+", "-"):
            return None
        ma = (m.a, m.b) if m.a in MUL_A and m.b in MUL_B else (m.b, m.a) if m.b in MUL_A and m.a in MUL_B else None
        if a.a in ALU_A and a.b in ALU_B:
            aa = (a.a, a.b)
        elif a.kind == "+" and a.b in ALU_A and a.a in ALU_B:
            aa = (a.b, a.a)
        else:
            aa = None
        if ma is None or aa is None or m.d == a.d:
            return None
        return ("*", m.d, *ma), (a.kind, a.d, *aa)

    def emit(self, p: Prog) -> int:
        """schedules and emits; returns the number of instructions"""
        ops, deps = self.ops, self._deps()
        n = len(ops)
        succ = [[] for _ in range(n)]
        for j, dj in enumerate(deps):
            for q, s in dj:
                succ[q].append((j, s))
        prio = [0] * n                                   # the longest chain of strict edges from the op on
        for j in reversed(range(n)):
            prio[j] = 1 + max((prio[q] if s else prio[q] - 1 for q, s in succ[j]), default=0)
        at: dict[int, int] = {}
        cyc = 0
        out = []
        while len(at) < n:
            def ready(j):
                return j not in at and all(q in at and (at[q] < cyc if s else at[q] <= cyc) for q, s in deps[j])
            # an op is placeable in this instruction if every predecessor is in an earlier one, or (non-strict)
            # in this one: predecessors placed in this very cycle count, so re-check as ops go in
            group: list[int] = []

            def ok(j):
                return j not in at and all(q in at and (at[q] < cyc if s else at[q] <= cyc) for q, s in deps[j])
            cand = sorted((j for j in range(n) if ready(j)), key=lambda j: (-prio[j], j))
            if not cand:
                cyc += 1
                continue
            comp = None                                  # ("single", j) or ("pair", jm, ja)
            move = None
            first = cand[0]
            if ops[first].kind == "k":
                at[first] = cyc
                out.append([first])
                cyc += 1
                continue
            writes: set[int] = set()

            def place(j):
                at[j] = cyc
                group.append(j)
                writes.update(ops[j].writes)
            for j in cand:
                o = ops[j]
                if o.kind == "k" or not ok(j) or set(o.writes) & writes:
                    continue
                if o.kind in ("ld", "st"):
                    if move is None and o.i in range(4) and -32 <= o.k < 32:
                        move = j
                        place(j)
                    continue
                if comp is None:
                    # a compute: look for a partner among the ready ones for the multifunction form
                    partner = None
                    for q in cand:
                        if q == j or q in at or ops[q].kind == "k" or not ok(q) or set(ops[q].writes) & (writes | set(o.writes)):
                            continue
                        pr = (self._pairable(o, ops[q]) if o.kind == "*" else
                              self._pairable(ops[q], o) if ops[q].kind == "*" else None)
                        if pr is not None:
                            partner = q
                            break
                    if partner is not None:
                        comp = ("pair", j if o.kind == "*" else partner, partner if o.kind == "*" else j)
                        place(j)
                        place(partner)
                    else:
                        comp = ("single", j)
                        place(j)
            if not group:
                cyc += 1
                continue
            out.append(group)
            cyc += 1
        for group in out:
            self._emit_one(p, group)
        return len(out)

    def _emit_one(self, p: Prog, group: list[int]) -> None:
        ops = self.ops
        if len(group) == 1 and ops[group[0]].kind == "k":
            o = ops[group[0]]
            if callable(o.x):
                o.x(p)
            else:
                p.fconst(o.d, o.x)
            return
        parts = []
        comps = [ops[j] for j in group if ops[j].kind not in ("ld", "st")]
        if len(comps) == 2:
            m = next(o for o in comps if o.kind == "*")
            a = next(o for o in comps if o is not m)
            parts += list(self._pairable(m, a))
        elif comps:
            o = comps[0]
            parts.append(("op", o.d, o.a, o.kind, o.b))
        for j in group:
            o = ops[j]
            if o.kind == "ld":
                parts.append(("ldk", o.d, o.k, o.i))
            elif o.kind == "st":
                parts.append(("stk", o.k, o.i, o.a))
        p.par(*parts)
