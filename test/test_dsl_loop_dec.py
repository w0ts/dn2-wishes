"""dnfw.perc.dsl loop_r counts down by `Rc = Rc - 1;` (dec, the 16-bit form) and sets no register
to 1, whatever ONE is (2026-11-10, shrink): with ONE the counter itself (PR #3's ec046958 case) it
runs every pass, not one; with another ONE that register is left alone in the code (run mode
poisons it, so a body that relied on it being 1 fails)."""

from __future__ import annotations

from dnfw.perc.dsl import Mem, Prog


def _count(one: int) -> tuple[int, list[str]]:
    runs = []
    r = Prog("run", mem=Mem(lambda a: 0))
    r.iconst(9, 0)
    r.loop_r(0, 5, lambda: (runs.append(1), r.iconst(9, 7)), one=one)
    e = Prog("emit")
    e.loop_r(0, 5, lambda: e.iconst(9, 7), one=one)
    return len(runs), [t.split("//", 1)[0].strip() for t in e.text().splitlines()]


def _sets_to_one(code: list[str], reg: int) -> bool:
    return any(t.startswith(f"R{reg} = 1;") or t.startswith(f"R{reg} = 0x1;") for t in code)


def test_one_the_counter_steps_by_dec():
    n, code = _count(0)
    assert n == 5
    assert "R0 = R0 - 1;" in code
    assert not _sets_to_one(code, 0) and "R0 = R0 - R0;" not in code


def test_another_one_steps_by_dec_too_and_is_left_alone():
    n, code = _count(12)
    assert n == 5
    assert "R0 = R0 - 1;" in code
    assert not _sets_to_one(code, 12) and "R0 = R0 - R12;" not in code
