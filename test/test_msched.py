"""dnfw.perc.msched (2026-11-14, insmf): random op lists (float adds, subtracts and multiplies, FLOAT and I
register loads as "x" ops, loads and stores through I0..I3, post-modified and at offsets) run by the DSL's model in
program order and as msched emits them give the same registers, I registers and memory, bit for bit; chain=False
too (moves through one I register ordered only where they may touch the same word)."""

from __future__ import annotations

import random
import struct

import pytest

from dnfw.perc import msched as MS
from dnfw.perc.dsl import Mem, Prog

BUF = {0: 0x2E5000, 1: 0x2E5200, 2: 0x2E5400, 3: 0x2E5600}


def _x(tag, emit, w, r, carry=True):
    emit.tag = tag
    return ("x", emit, w, r, carry)


def _ops(rnd: random.Random, n: int) -> list:
    ops = []
    reg = lambda: f"F{rnd.randrange(16)}"
    for _ in range(n):
        k = rnd.random()
        if k < 0.25:
            ops.append(("alu", rnd.choice("+-"), (reg(),), (reg(), reg()), None))
        elif k < 0.45:
            ops.append(("mul", "*", (reg(),), (reg(), reg()), None))
        elif k < 0.55:
            d, a = rnd.randrange(16), rnd.randrange(16)          # (FLOAT: never a NaN, which fop and par differ on)
            ops.append(_x("float", lambda p, d=d, a=a: p.float0(d, a), (f"F{d}",), (f"F{a}",)))
        elif k < 0.6:
            i, base = rnd.randrange(4), rnd.randrange(-8, 8)
            ops.append(_x("seti", lambda p, i=i, base=base: (p.iconst(15, BUF[i] + 4 * base), p.seti(i, 15)),
                          (f"I{i}", "F15"), (), False))
        elif k < 0.8:
            i = f"I{rnd.randrange(4)}"
            ops.append(("mov", "ldk", (reg(),), (), (i, rnd.randrange(-6, 6))) if rnd.random() < 0.5
                       else ("mov", "ld", (reg(),), (), i))
        else:
            i = f"I{rnd.randrange(4)}"
            ops.append(("mov", "stk", (), (reg(),), (i, rnd.randrange(-6, 6))) if rnd.random() < 0.5
                       else ("mov", "st", (), (reg(),), i))
    return ops


def _seq(p: Prog, ops: list) -> None:
    for o in ops:
        if o[0] == "x":
            o[1](p)
        elif o[0] == "mov":
            MS._move(p, o)
        else:
            p.fop(int(o[2][0][1:]), int(o[3][0][1:]), o[1], int(o[3][1][1:]))


def _fresh(seed: int) -> Prog:
    rnd = random.Random(seed)
    m = Mem()
    for a in range(0x2E4F00, 0x2E5800, 4):
        m.put(a, struct.unpack("<I", struct.pack("<f", rnd.uniform(-2, 2)))[0])
    p = Prog("run", mem=m)
    for k in range(16):
        p.r[k] = struct.unpack("<I", struct.pack("<f", rnd.uniform(-2, 2)))[0]
    for i, a in BUF.items():
        p.i[i] = a
    return p


@pytest.mark.parametrize("chain", [True, False])
def test_the_schedule_is_the_program_order(chain):
    rnd = random.Random(14)
    for case in range(300):
        ops = _ops(rnd, rnd.randrange(8, 40))
        a, b = _fresh(case), _fresh(case)
        _seq(a, ops)
        MS.emit(b, ops, chain=chain)
        assert a.r == b.r and a.i == b.i and a.mem.w == b.mem.w, f"case {case}"


def test_a_move_never_rides_on_an_instruction_that_writes_its_i_register():
    ops = [_x("seti", lambda p: p.seti(2, 9), ("I2",), ("F9",), False),
           ("mov", "ldk", ("F8",), (), ("I2", 0)),
           ("alu", "+", ("F10",), ("F8", "F12"), None)]
    slots = MS.schedule(ops, chain=False)
    assert slots[0] == [0] and 1 in slots[1]


def test_chain_false_lets_reads_of_other_words_pass_a_store():
    ops = [("alu", "+", ("F8",), ("F9", "F12"), None),
           ("mov", "stk", (), ("F8",), ("I0", 0)),
           ("mov", "ldk", ("F1",), (), ("I0", 1)),
           ("mul", "*", ("F2",), ("F1", "F4"), None)]
    assert len(MS.schedule(ops, chain=False)) < len(MS.schedule(ops, chain=True))
