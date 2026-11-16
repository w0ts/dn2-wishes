"""A list scheduler for straight-line float code: the same operations, in an order that puts a multiply and an add
or subtract into one multifunction instruction where the SHARC allows it (dnfw.perc.mf: the multiply's operands
F0-F3 x F4-F7, the ALU's F8-F11 and F12-F15), and a memory move (through I0..I3) on a compute.

An operation is (kind, op, writes, reads, ireg):
    ("alu", "+" | "-" | "MIN" | "MAX", (d,), (a, b), None)   Fd = Fa op Fb
    ("mul", "*", (d,), (a, b), None)                          Fd = Fa * Fb
    ("mov", "ld", (d,), (), i)                                Fd = DM(Ii, M6), Ii one word on
    ("mov", "ldk", (d,), (), (i, k))                          Fd = DM(k, Ii)
    ("mov", "st", (), (s,), i)                                DM(Ii, M6) = Fs, Ii one word on
    ("mov", "stk", (), (s,), (i, k))                          DM(k, Ii) = Fs (2026-11-12, simd)
Registers are "F0".."F15". Each value is computed exactly as written: the schedule only reorders within what the
dependencies allow (a read after the write it needs, a write after every earlier read of the register (the same
instruction is fine: the core reads every operand before it writes), writes in program order, the moves through
one I register in program order), so the run gives the same floats, bit for bit, as the program order. Additions
are commutative (IEEE: a + b and b + a are the same bits), so a pair may swap an addition's operands to meet the
ALU's groups; a subtraction is never swapped. 2026-11-12 (plaits-opt): PLAITS MDAL's mode body."""

from __future__ import annotations

import itertools

_XM = {f"F{i}" for i in range(4)}
_YM = {f"F{i}" for i in range(4, 8)}
_XA = {f"F{i}" for i in range(8, 12)}
_YA = {f"F{i}" for i in range(12, 16)}


def _n(r: str) -> int:
    return int(r[1:])


def _mul_pair(o):
    a, b = o[3]
    if a in _XM and b in _YM:
        return a, b
    if b in _XM and a in _YM:
        return b, a
    return None


def _alu_pair(o):
    a, b = o[3]
    if o[1] == "-":
        return (a, b) if a in _XA and b in _YA else None
    if o[1] != "+":
        return None
    if a in _XA and b in _YA:
        return a, b
    if b in _XA and a in _YA:
        return b, a
    return None


def schedule(ops: list) -> list[list[int]]:
    """Instruction slots (lists of operation indices) for OPS."""
    n = len(ops)
    deps = [[] for _ in range(n)]
    last_w, reads = {}, {}
    for i, (kind, _op, w, r, _ix) in enumerate(ops):
        for reg in r:
            if reg in last_w:
                deps[i].append((last_w[reg], 1))
        for reg in w:
            if reg in last_w:
                deps[i].append((last_w[reg], 1))
            for j in reads.get(reg, ()):
                deps[i].append((j, 0))
        for reg in r:
            reads.setdefault(reg, []).append(i)
        for reg in w:
            last_w[reg] = i
            reads[reg] = []
    ireg = lambda o: o[4][0] if isinstance(o[4], tuple) else o[4]
    for i in range(n):
        if ops[i][0] == "mov":
            for j in range(i - 1, -1, -1):
                if ops[j][0] == "mov" and ireg(ops[j]) == ireg(ops[i]):
                    deps[i].append((j, 1))
                    break
    succ = [[] for _ in range(n)]
    for i in range(n):
        for j, d in deps[i]:
            succ[j].append((i, d))
    prio = [0] * n
    for i in range(n - 1, -1, -1):
        prio[i] = max([prio[s] + d for s, d in succ[i]] + [0]) + (ops[i][0] != "mov")
    when = [None] * n
    slots, c, done = [], 0, 0
    while done < n:
        ready = [i for i in range(n) if when[i] is None
                 and all(when[j] is not None and when[j] + d <= c for j, d in deps[i])]
        comp = sorted((i for i in ready if ops[i][0] != "mov"), key=lambda i: (-prio[i], i))
        cands = [(i,) for i in comp]
        for a, b in itertools.combinations(comp, 2):
            al, mu = (a, b) if ops[a][0] == "alu" else (b, a)
            if ops[al][0] == "alu" and ops[mu][0] == "mul" and _alu_pair(ops[al]) and _mul_pair(ops[mu]) \
                    and not set(ops[al][2]) & set(ops[mu][2]):
                cands.append((a, b))
        cands.sort(key=lambda t: (len(t), sum(prio[i] for i in t), -min(t)), reverse=True)
        pick = list(cands[0]) if cands else []
        ws = {r for i in pick for r in ops[i][2]}
        rs = {r for i in pick for r in ops[i][3]}
        for m in sorted((i for i in ready if ops[i][0] == "mov"), key=lambda i: i):
            o = ops[m]
            if o[1] in ("ld", "ldk") and set(o[2]) & (ws | rs):
                continue
            if o[1] in ("st", "stk") and set(o[3]) & ws:
                continue
            if pick and _ireg_num(o) not in (0, 1, 2, 3):
                continue
            pick.append(m)
            break
        assert pick, "no operation ready: a dependency cycle"
        for i in pick:
            when[i] = c
            done += 1
        slots.append(pick)
        c += 1
    return slots


def _ireg_num(o) -> int:
    ix = o[4][0] if isinstance(o[4], tuple) else o[4]
    return int(ix[1:])


def emit(p, ops: list) -> int:
    """Emit OPS on Prog P in their schedule; returns the instruction count."""
    slots = schedule(ops)
    for s in slots:
        comp = [ops[i] for i in s if ops[i][0] != "mov"]
        moves = [ops[i] for i in s if ops[i][0] == "mov"]
        parts = []
        if len(comp) == 2:
            al = next(o for o in comp if o[0] == "alu")
            mu = next(o for o in comp if o[0] == "mul")
            a, b = _mul_pair(mu)
            parts.append(("*", _n(mu[2][0]), _n(a), _n(b)))
            x, y = _alu_pair(al)
            parts.append((al[1], _n(al[2][0]), _n(x), _n(y)))
        elif comp:
            o = comp[0]
            parts.append(("op", _n(o[2][0]), _n(o[3][0]), o[1], _n(o[3][1])))
        for m in moves:
            if m[1] == "ld":
                parts.append(("ld", _n(m[2][0]), _ireg_num(m)))
            elif m[1] == "ldk":
                parts.append(("ldk", _n(m[2][0]), m[4][1], _ireg_num(m)))
            elif m[1] == "stk":
                parts.append(("stk", m[4][1], _ireg_num(m), _n(m[3][0])))
            else:
                parts.append(("st", _ireg_num(m), _n(m[3][0])))
        if len(parts) == 1 and parts[0][0] == "op":
            _, d, a, op, b = parts[0]
            p.fop(d, a, op, b)
        elif len(parts) == 1 and parts[0][0] == "ld":
            p.ldpost(parts[0][1], parts[0][2])
        elif len(parts) == 1 and parts[0][0] == "ldk":
            p.ldi(parts[0][1], parts[0][2], parts[0][3])
        elif len(parts) == 1 and parts[0][0] == "stk":
            p.sti(parts[0][1], parts[0][2], parts[0][3])
        elif len(parts) == 1 and parts[0][0] == "st":
            p.stpost(parts[0][1], parts[0][2])
        else:
            p.par(*parts)
    return len(slots)
