"""dnfw.perc.mf: the float multifunction compute field, and Prog.par's multifunction lines in run mode."""
import pytest

from dnfw.perc import mf
from dnfw.perc.dsl import Prog


def test_the_firmwares_own_word():
    # stock 1.11 (sw 0x1c7258, a type 3a): F12 = F0 * F7, F8 = F8 + F12 is the compute field 0x58c830
    assert mf.field(12, 0, 7, "+", 8, 8, 12) == 0x58C830


def test_field_round_trip():
    for fm in (0, 5, 15):
        for xm in range(4):
            for ym in range(4, 8):
                for op in ("+", "-", "MAX", "MIN"):
                    for xa in (8, 11):
                        for ya in (12, 15):
                            c = mf.field(fm, xm, ym, op, 3, xa, ya)
                            assert mf.unfield(c) == (fm, xm, ym, op, 3, xa, ya)


def test_text_parses_back_to_the_field():
    assert mf.parse(mf.text(9, 1, 5, "-", 13, 10, 14, "R5 = DM(I1, M6)")) == mf.field(9, 1, 5, "-", 13, 10, 14)
    assert mf.parse("F8 = F2 * F6, F12 = F9 + F13, F13 = F9 - F13;") == mf.field_dual(8, 2, 6, 12, 13, 9, 13)
    assert mf.parse("F8 = F2 * F6;") is None
    assert mf.parse("F12 = MAX(F9, F13);") is None


def test_operand_groups_are_checked():
    for bad in ((12, 4, 7, "+", 8, 8, 12), (12, 0, 3, "+", 8, 8, 12), (12, 0, 7, "+", 8, 4, 12), (12, 0, 7, "+", 8, 8, 9)):
        with pytest.raises(AssertionError):
            mf.field(*bad)


def test_the_alu_reads_the_old_value_of_the_multipliers_result():
    p = Prog("run")
    for r, v in ((0, 2.0), (4, 3.0), (8, 10.0), (12, 100.0)):
        p.fconst(r, v)
    p.par(("*", 12, 0, 4), ("+", 9, 8, 12))      # F12 = F0 * F4 (6), F9 = F8 + F12 (the OLD F12: 110)
    assert p.F(12) == 6.0 and p.F(9) == 110.0


def test_dual_add_subtract():
    p = Prog("run")
    for r, v in ((1, 2.0), (5, 4.0), (9, 7.0), (14, 3.0)):
        p.fconst(r, v)
    p.par(("*", 2, 1, 5), ("+-", 3, 4, 9, 14))
    assert (p.F(2), p.F(3), p.F(4)) == (8.0, 10.0, 4.0)
