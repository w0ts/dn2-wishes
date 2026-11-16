"""dnfw.perc.dsl's SIMD region (Prog.simd, 2026-11-12): each lane the scalar program's floats, PEy a word on."""

import pytest

from dnfw.perc.dsl import POISON, Mem, Prog, SIMD_OFF, SIMD_ON, bits, f32, flt

BASE = 0x1000


def _prog(words):
    mem = Mem()
    for k, x in enumerate(words):
        mem.put(BASE + 4 * k, bits(f32(x)))
    p = Prog("run", mem)
    p.i[1] = BASE
    return p, mem


def _w(mem, k):
    return mem.get(BASE + 4 * k)


def _mul_body(p):
    p.ldi(0, 0, 1)                   # PEx word 0, PEy word 1
    p.ldi(1, 2, 1)                   # PEx word 2, PEy word 3
    p.fop(2, 0, "*", 1)
    p.sti(4, 1, 2)                   # PEx word 4, PEy word 5


def test_each_lane_is_the_scalar_program():
    xs = [1.25, -3.5, 0.1, 7.0]
    p, mem = _prog(xs)
    p.simd(lambda: _mul_body(p))
    assert _w(mem, 4) == bits(f32(f32(xs[0]) * f32(xs[2])))
    assert _w(mem, 5) == bits(f32(f32(xs[1]) * f32(xs[3])))
    assert flt(p.r[2]) == f32(f32(xs[0]) * f32(xs[2]))
    assert flt(p.s[2]) == f32(f32(xs[1]) * f32(xs[3]))
    assert p.i[1] == BASE


def test_one_step_an_instruction_for_both_lanes():
    p, _ = _prog([1.0, 2.0, 3.0, 4.0])
    p.simd(lambda: _mul_body(p))
    assert p.steps == 4 + 4          # the body, and BIT SET + NOP, BIT CLR + NOP


def test_emit_wraps_the_body_in_the_mode_switch():
    p = Prog("emit")
    p.simd(lambda: _mul_body(p))
    text = [ln.split("//")[0].strip() for ln in p.lines]
    assert text[0] == SIMD_ON and text[1] == "NOP;"
    assert text[-2] == SIMD_OFF and text[-1] == "NOP;"
    assert sum(1 for t in text if "DM(" in t) == 3


@pytest.mark.parametrize("bad", [
    lambda p: p.fconst(0, 1.0),
    lambda p: p.iconst(0, 4),
    lambda p: p.seti(1, 0),
    lambda p: p.if_(0, "LT", 1, lambda: p.fop(2, 0, "+", 1)),
])
def test_refused_in_a_region(bad):
    p, _ = _prog([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(AssertionError):
        p.simd(lambda: bad(p))


def test_refused_in_a_region_in_emit_mode_too():
    p = Prog("emit")
    with pytest.raises(AssertionError):
        p.simd(lambda: p.seti(1, 0))


def test_a_lane_writing_a_word_the_other_reads_is_refused():
    p, _ = _prog([1.0, 2.0, 3.0, 4.0])

    def body():
        p.ldi(0, 0, 1)               # PEy reads word 1
        p.sti(1, 1, 0)               # PEx writes word 1
    with pytest.raises(AssertionError, match="share words"):
        p.simd(body)


def test_pey_reading_a_register_it_did_not_load_is_poison():
    p, mem = _prog([1.0, 2.0, 3.0, 4.0])
    p.fconst(5, 2.0)                 # R5 only: PEy's S5 is not set by a scalar constant

    def body():
        p.ldi(0, 0, 1)
        p.fop(2, 0, "*", 5)
        p.sti(4, 1, 2)
    p.simd(body)
    assert _w(mem, 4) == bits(2.0)
    assert _w(mem, 5) == 0xFFFFFFFF  # NaN in, the core's all-ones NaN out


def test_s_registers_are_poisoned_at_each_region():
    p, _ = _prog([1.0, 2.0, 3.0, 4.0])
    p.simd(lambda: _mul_body(p))
    assert flt(p.s[2]) == 8.0
    p.simd(lambda: p.fpass(3, 2))    # S2 from the region before: not trusted
    assert p.s[3] in (POISON, 0xFFFFFFFF)
    assert flt(p.r[3]) == 3.0
