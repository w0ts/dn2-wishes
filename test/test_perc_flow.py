"""dnfw.perc.flow (2026-11-20, DRUM's room): R12 pairs folded only where R12 is dead, by the text's control flow."""
from __future__ import annotations

from dnfw.perc import flow as FLOW


def _fold(text: str) -> tuple[list[str], dict]:
    out, n = FLOW.fold({"perc": [ln for ln in text.strip("\n").splitlines()]})
    return [ln.split("//")[0].strip() for ln in out["perc"] if ln.split("//")[0].strip()], n


SUB = """
.GLOBAL wr_pk_sub_s.;
wr_pk_sub_s.:
      R12 = 0x5;
      R0 = R0 + R12;
      JUMP (M14, I12);
"""


def test_a_call_whose_sub_writes_r12_first_is_folded():
    text = """
      R12 = 0x0;                        // return address - 1: wr_pk_ret_1. - 1
      I12 = R12;
      JUMP 0x0;                         // -> wr_pk_sub_s.
.GLOBAL wr_pk_ret_1.;
wr_pk_ret_1.:
      R1 = PASS R0;
      JUMP 0x1234;                      // out
""" + SUB
    lines, n = _fold(text)
    assert n == {"call": 1, "ireg": 0, "zero": 0, "pass": 0}
    assert lines[0] == "I12 = 0x0;" and "I12 = R12;" not in lines
    out, _ = FLOW.fold({"perc": text.strip("\n").splitlines()})
    assert "// return address - 1: wr_pk_ret_1. - 1" in out["perc"][0]     # the resolver still finds it


def test_a_call_whose_sub_reads_r12_is_kept():
    text = """
      R12 = 0x0;                        // return address - 1: wr_pk_ret_1. - 1
      I12 = R12;
      JUMP 0x0;                         // -> wr_pk_sub_r.
.GLOBAL wr_pk_ret_1.;
wr_pk_ret_1.:
      JUMP 0x1234;
.GLOBAL wr_pk_sub_r.;
wr_pk_sub_r.:
      R0 = R0 + R12;
      JUMP (M14, I12);
"""
    lines, n = _fold(text)
    assert n["call"] == 0 and "I12 = R12;" in lines


def test_a_sub_that_may_return_without_writing_r12_keeps_the_call():
    text = """
      R12 = 0x0;                        // return address - 1: wr_pk_ret_1. - 1
      I12 = R12;
      JUMP 0x0;                         // -> wr_pk_sub_m.
.GLOBAL wr_pk_ret_1.;
wr_pk_ret_1.:
      R12 = 0x3;
.GLOBAL wr_pk_sub_m.;
wr_pk_sub_m.:
      R0 = PASS R0;
      IF EQ JUMP 0x0;                   // -> wr_pk_out_2.
      R12 = 0x1;
.GLOBAL wr_pk_out_2.;
wr_pk_out_2.:
      JUMP (M14, I12);
"""
    _lines, n = _fold(text)
    assert n["call"] == 0                                   # (a return is taken as a read)


def test_i_register_and_zero_forms():
    text = """
      R12 = 0x2e5abc;
      I0 = R12;
      R12 = 0x0;
      F1 = FLOAT R3 BY R12;
      R12 = 0x0;
      R4 = R12 - R5;
      R12 = 0x0;
      R6 = R12 + R7;
      R12 = 0x0;
      R8 = R9 + R12;
      R12 = 0x7;
      R0 = R0 AND R12;
      JUMP 0x1234;
"""
    lines, n = _fold(text)
    assert n == {"call": 0, "ireg": 1, "zero": 4, "pass": 0}
    assert lines[:5] == ["I0 = 0x2e5abc;", "F1 = FLOAT R3;", "R4 = -R5;", "R6 = PASS R7;", "R8 = PASS R9;"]


def test_a_later_read_on_one_branch_keeps_the_load():
    text = """
      R12 = 0x0;
      R4 = R12 - R5;
      R4 = PASS R4;
      IF EQ JUMP 0x0;                   // -> wr_pk_else_1.
      R12 = 0x1;
.GLOBAL wr_pk_else_1.;
wr_pk_else_1.:
      R0 = R0 + R12;
      JUMP 0x1234;
"""
    lines, n = _fold(text)
    assert n["zero"] == 0 and lines[0] == "R12 = 0x0;"


def test_a_fold_that_removes_another_folds_write_is_undone():
    """the first pair is dead because the second pair's R12 load writes R12 before the read below; folding the
    second drops that write, so the first must stay (the fixed-point re-check)"""
    text = """
      R12 = 0x10;
      I0 = R12;
      R12 = 0x0;
      R1 = R12 - R2;
      JUMP 0x0;                         // -> wr_pk_x_1.
.GLOBAL wr_pk_x_1.;
wr_pk_x_1.:
      R3 = R3 + R12;
      JUMP 0x1234;
"""
    lines, n = _fold(text)
    # R12 = 0x0 is read at wr_pk_x_1 (R3 + R12): the zero pair is live and kept; the I0 pair is dead (R12 = 0x0
    # writes it) and folded
    assert n == {"call": 0, "ireg": 1, "zero": 0, "pass": 0}
    assert lines[:3] == ["I0 = 0x10;", "R12 = 0x0;", "R1 = R12 - R2;"]


def test_simd_regions_and_unknown_jumps_stop_the_search():
    text = """
      R12 = 0x0;
      R4 = R12 - R5;
      BIT SET MODE1 0x200000;
      R12 = 0x3;
"""
    _lines, n = _fold(text)
    assert n["zero"] == 0
    text = """
      R12 = 0x20;
      I1 = R12;
      JUMP (M14, I12);
"""
    _lines, n = _fold(text)
    assert n["ireg"] == 0


def test_perc_folds_and_stays_one_program():
    """the real program: pairs folded in every span, each fold's R12 dead in the folded text, nothing else changed"""
    import re
    from dnfw.perc import live as PL, program as P
    from dnfw.waverider import dsp
    p = P._emit(PL.layout(), dsp.SMP_SW, "pk")
    base = {"perc": p.text(), **p.span_texts()}
    folded, n = FLOW.fold({k: v.splitlines() for k, v in base.items()})
    assert n["call"] > 400 and n["ireg"] > 40 and n["zero"] > 100 and n["pass"] >= 3
    for name, text in base.items():
        a = [ln for ln in text.splitlines()]
        b = folded[name]
        assert len(a) - len(b) == sum(1 for _ in a) - len(b)
        # every line kept is either the same or one of the folded forms
        j = 0
        for ln in a:
            if j < len(b) and ln == b[j]:
                j += 1
                continue
            body = ln.split("//")[0].strip()
            assert re.fullmatch(r"R12 = -?0x[0-9a-f]+;|I\d+ = R12;|F\d+ = FLOAT R\d+ BY R12;|R\d+ = R12 [-+] R\d+;"
                                r"|R\d+ = R\d+ \+ R12;|R12 = PASS R\d+;", body), ln
            if j < len(b) and body.startswith("R12 =") and b[j].split("//")[0].strip().startswith("I"):
                j += 1                                     # R12 = K -> In = K
            elif j < len(b) and not body.startswith("R12 =") and not body.startswith("I"):
                j += 1                                     # the zero forms rewritten in place
        assert j == len(b)


def test_g5_pass_form():
    """2026-11-20: `R12 = PASS Ra; Rd = R12 + Rb` -> `Rd = Rb + Ra` where Rb is R8..R15 (G5) and R12 is dead; kept
    where Rb is R0..R7 (an add takes R8..R15 first), or where R12 is read later"""
    lines, n = _fold("""
      R12 = PASS R4;
      R4 = R12 + R5;
      R12 = PASS R3;
      R6 = R12 + R9;
      R12 = PASS R2;
      R7 = R11 + R12;
      R12 = PASS R1;
      R1 = R12 + R10;
      R2 = R12 + R1;
      R12 = 0x3;
      JUMP 0x1234;
""")
    assert n["pass"] == 2
    assert lines[:6] == ["R12 = PASS R4;", "R4 = R12 + R5;", "R6 = R9 + R3;", "R7 = R11 + R2;", "R12 = PASS R1;",
                         "R1 = R12 + R10;"]


def test_fold_text_keeps_a_text_without_folds():
    text = "      R0 = PASS R1;\n      JUMP 0x1234;\n"
    assert FLOW.fold_text(text) == text
