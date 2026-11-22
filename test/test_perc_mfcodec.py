"""dnfw.perc.mfcodec (the multifunction field from PGR Table 12-12) and mf's refusing wrapper (2026-11-21)."""
import json
import os
import pathlib
import random

import pytest

from dnfw.perc import mf, mfcodec as C

MF_KINDS = ("fixed", "float", "dual-fixed", "dual-float")


def _table() -> dict | None:
    """digikit's transcription of the reference (compute_table.json), when a checkout is at hand"""
    for d in (os.environ.get("DNFW_DIGIKIT_SHARC"), pathlib.Path(__file__).resolve().parents[2] / "digikit-wt-sharcemu",
              pathlib.Path(__file__).resolve().parents[1] / "scratch/bench/digikit-wt-sharcemu"):
        if d and (p := pathlib.Path(d) / "tools/sharcspec/compute_table.json").exists():
            return json.loads(p.read_text())
    return None


def test_stock_words():
    # stock 1.12's own words (scripts/mf_corpus.py): sw 0x1c101c, 0x1c0cd0 (ABS: Fya unused), and the 1.11 one
    assert C.decode(0x5B773F) == "F7 = F0 * F7, R7 = FIX F11 BY R15"
    assert C.decode(0x5D683E) == "F6 = F0 * F7, F8 = ABS F11"
    assert C.encode("F12 = F0 * F7, F8 = F8 + F12") == 0x58C830 == mf.field(12, 0, 7, "+", 8, 8, 12)
    assert C.encode("F8 = F2 * F6, F12 = F9 + F13, F13 = F9 - F13") == mf.field_dual(8, 2, 6, 12, 13, 9, 13)


def test_round_trip_every_category():
    rnd = random.Random(7)
    for op6 in range(64):
        for _ in range(64):
            c = (1 << 22) | (op6 << 16) | rnd.getrandbits(16)
            if C.kind(c) in MF_KINDS:
                c &= C.care(c)
                assert C.encode(C.decode(c)) == c, (hex(c), C.decode(c))


def test_reserved_and_not_multifunction():
    assert C.kind(0x042312) is None                      # R3 = R1 XOR R2: single function
    for op6 in (0b000010, 0b010011, 0b010111):
        assert C.decode((1 << 22) | (op6 << 16)) is None
    assert C.kind((1 << 22) | (0b000111 << 16)) == "float64"


def test_group_errors_are_errors():
    for bad in ("F12 = F4 * F7, F8 = F8 + F12", "F12 = F0 * F7, F8 = F8 + F9",
                "F12 = F0 * F7, F8 = F8 + F12, F9 = F8 - F13", "R12 = R0 * R7, R8 = R8 + R12, R9 = R8 - R12",
                "F12 = F0 * F7"):
        with pytest.raises(ValueError):
            C.encode(bad)


def _norm(s: str) -> str:
    return s.replace(" ", "").replace("(SSFR)", "").replace("(SSF)", "")


def test_against_digikits_table():
    t = _table()
    if t is None:
        pytest.skip("no digikit checkout (compute_table.json)")
    for row in t["multifn_mul_alu"]["rows"]:
        op6 = int(row["opcode_21_16"], 2)
        ours = C.decode((1 << 22) | (op6 << 16) | 0xC830)
        want = (row["syntax"].upper().replace("R3-0", "R0").replace("R7-4", "R7").replace("F3-0", "F0")
                .replace("F7-4", "F7").replace("RXA", "R8").replace("RYA", "R12").replace("FXA", "F8")
                .replace("FYA", "F12").replace("RM", "R12").replace("FM", "F12").replace("RA", "R8")
                .replace("FA", "F8"))
        assert _norm(ours) == _norm(want), (row, ours)


def test_wrapper_proves_only_the_proven():
    ok = ["F12 = F0 * F7, F8 = F8 + F12;", "F13 = F1 * F5, F3 = F11 - F14, DM(-2, I1) = F5;",
          "F12 = F0 * F7, F8 = ABS F11;", "F12 = F0 * F7, F8 = FLOAT R8 BY R12, F1 = DM(I3, M6);",
          "F8 = F2 * F6, F12 = F9 + F13, F13 = F9 - F13;", "F12 = F0 * F7, F8 = MIN(F8, F12);"]
    for line in ok:
        assert mf.classify(line) is not None
        mf.check_line(line)
    refused = ["F12 = F0 * F7, R8 = FIX F8 BY R12;",                  # digikit does not run FIX BY
               "R12 = R0 * R7 (SSFR), R8 = R8 + R12;",                # no fixed-point form is run by digikit
               "IF NE F12 = F0 * F7, F8 = F8 + F12;",                 # a condition
               "F12 = F0 * F7, F8 = F8 + F12, DM(I4, M6) = F1;",      # a move through I4..I7
               "F12 = F0 * F7, F8 = F8 + F12, I4 = R2;",              # a ureg move (type 5)
               "F12 = F0 * F7, F8 = F8 + F9;"]                        # outside the groups
    for line in refused:
        with pytest.raises(AssertionError):
            mf.check_line(line)
    for single in ("F4 = F4 * F12, R5 = DM(18, I3);", "R1 = R1 XOR R2, R4 = DM(1, I0);", "F2 = F2 + F3;"):
        assert mf.classify(single) is None


def test_verify_catches_a_dropped_alu_half():
    line = "F12 = F0 * F7, F8 = ABS F11;"
    dropped = bytes.fromhex("0100") + (0x130C07).to_bytes(4, "big")           # the multiply alone
    with pytest.raises(AssertionError):
        mf.verify(dropped, [0], [line])
    good = bytes.fromhex("0100") + C.encode(line).to_bytes(4, "big")
    assert mf.verify(good, [0], [line]) == [0]
