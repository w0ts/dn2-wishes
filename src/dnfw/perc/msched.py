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
ALU's groups; a subtraction is never swapped. 2026-11-12 (plaits-opt): PLAITS MDAL's mode body.

2026-11-14 (insmf, the post inserts): two more kinds, and the I registers as registers:
    ("x", emit, writes, reads, carry)                         one other instruction: EMIT(p) emits it (an integer
                                                              compute, a FLOAT / TRUNC, an I register load); it
                                                              never pairs; CARRY: a memory move may ride on it
                                                              (a plain compute the DSL merges a move into)
Registers here are "F0".."F15" (an R register is its F: the same register) and "I0".."I7": a move reads its I
register and a post-modify move writes it, so an "x" that loads an I register orders the moves around it.
schedule(..., chain=False): moves through one I register are ordered only where they may touch the same word
(their words known from the I register's loads and post-modifies; a store against any move of the same word, or
of a word not known), not all in program order; I_LAT: the slots between an I register's load and its first use
(the core stalls on a DAG register used right after it is written)."""

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


def _ireg(o) -> str:
    return o[4][0] if isinstance(o[4], tuple) else o[4]


def _regs(o) -> tuple[tuple, tuple]:
    """(writes, reads) of O, its I register among them"""
    kind, op, w, r, _ix = o
    if kind != "mov":
        return tuple(w), tuple(r)
    i = _ireg(o)
    return tuple(w) + ((i,) if op in ("ld", "st") else ()), tuple(r) + (i,)


def _words(ops: list) -> list:
    """each move's word: (the I register, its load's number, words on) or None for a non-move"""
    base, on, out = {}, {}, []
    for k, o in enumerate(ops):
        if o[0] == "x":
            for reg in o[2]:
                if reg.startswith("I"):
                    base[reg], on[reg] = k, 0
        if o[0] != "mov":
            out.append(None)
            continue
        i = _ireg(o)
        at = on.get(i, 0) + (o[4][1] if o[1] in ("ldk", "stk") else 0)
        out.append((i, base.get(i, -1), at))
        if o[1] in ("ld", "st"):
            on[i] = on.get(i, 0) + 1
    return out


def schedule(ops: list, chain: bool = True, i_lat: int = 1) -> list[list[int]]:
    """Instruction slots (lists of operation indices) for OPS."""
    n = len(ops)
    deps = [[] for _ in range(n)]
    last_w, reads = {}, {}
    for i, o in enumerate(ops):
        w, r = _regs(o)
        for reg in r:
            if reg in last_w:
                lat = i_lat if reg.startswith("I") and ops[last_w[reg]][0] == "x" else 1
                deps[i].append((last_w[reg], lat))
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
    words = _words(ops)
    for i in range(n):
        if ops[i][0] != "mov":
            continue
        for j in range(i - 1, -1, -1):
            if ops[j][0] != "mov" or _ireg(ops[j]) != _ireg(ops[i]):
                continue
            if chain:
                deps[i].append((j, 1))
                break
            stores = ops[i][1] in ("st", "stk") or ops[j][1] in ("st", "stk")
            same = words[i][1] != words[j][1] or words[i][2] == words[j][2]
            if stores and same:
                deps[i].append((j, 1))
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
        xs = [i for i in comp if ops[i][0] == "x"]
        cands = [(i,) for i in comp]
        for a, b in itertools.combinations(comp, 2):
            al, mu = (a, b) if ops[a][0] == "alu" else (b, a)
            if ops[al][0] == "alu" and ops[mu][0] == "mul" and _alu_pair(ops[al]) and _mul_pair(ops[mu]) \
                    and not set(ops[al][2]) & set(ops[mu][2]) and a not in xs and b not in xs:
                cands.append((a, b))
        cands.sort(key=lambda t: (len(t), sum(prio[i] for i in t), -min(t)), reverse=True)
        pick = list(cands[0]) if cands else []
        ws = {r for i in pick for r in _regs(ops[i])[0]}
        rs = {r for i in pick for r in _regs(ops[i])[1]}
        for m in sorted((i for i in ready if ops[i][0] == "mov"), key=lambda i: i):
            o = ops[m]
            if o[1] in ("ld", "ldk") and set(o[2]) & (ws | rs):
                continue
            if o[1] in ("st", "stk") and set(o[3]) & ws:
                continue
            if _ireg(o) in ws or _ireg(o) in rs:
                continue
            if pick and (_ireg_num(o) not in (0, 1, 2, 3) or (ops[pick[0]][0] == "x" and not ops[pick[0]][4])):
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


_SLOTS: dict = {}


def emit(p, ops: list, chain: bool = True, i_lat: int = 1) -> int:
    """Emit OPS on Prog P in their schedule; returns the instruction count. (A list emitted again, the same
    object (a loop's body in run mode), keeps its schedule.)"""
    key = (id(ops), chain, i_lat)
    if key not in _SLOTS or _SLOTS[key][0] is not ops:
        _SLOTS[key] = (ops, schedule(ops, chain, i_lat))
    slots = _SLOTS[key][1]
    for s in slots:
        comp = [ops[i] for i in s if ops[i][0] != "mov"]
        moves = [ops[i] for i in s if ops[i][0] == "mov"]
        if comp and comp[0][0] == "x":
            comp[0][1](p)                       # the DSL merges a move into it (a plain compute: carry)
            for m in moves:
                _move(p, m)
            continue
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


def _move(p, m) -> None:
    i = _ireg_num(m)
    if m[1] == "ld":
        p.ldpost(_n(m[2][0]), i)
    elif m[1] == "ldk":
        p.ldi(_n(m[2][0]), m[4][1], i)
    elif m[1] == "stk":
        p.sti(m[4][1], i, _n(m[3][0]))
    else:
        p.stpost(i, _n(m[3][0]))
