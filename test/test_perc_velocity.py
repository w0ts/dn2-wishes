"""Velocity on our machines (2026-11-12, the User: "like Sophie, and our other synths too"; Schwung's Sophie: dry *= vel/127).

The ColdFire writes each voice's note velocity (vel x 256, its track's VELOCITY cell at the note) into frame slot
dnfw.perc.machines.VEL_SLOT for our machine types (csrc/slides/slide.c); the voice host latches it at the voice's
trig and scales the voice by vel/127 at its output guard. No word (0: an older ColdFire, a slot never played) is full
level, bit for bit as before.
"""

from __future__ import annotations

import pytest

from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as M

BLOCKS = 12


def _voice(kind: str, t: int = 3) -> PL.Harness:
    h = PL.Harness(t)
    if kind == "ANALOG2":                          # its mix tables, as the coordinator loads them (analog2.ctx)
        from dnfw.mnm import analog2 as A2
        from dnfw.perc.dsl import bits
        for k, w in enumerate(A2.table_words()):
            h.mem.put(h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k, bits(w) if isinstance(w, float) else w)
    if kind == "md":
        h.set_controls(M.NAMES.index("TRX-BD"), PL.defaults("TRX-BD"))
    else:
        h.set_mnm_voice(MM.NAMES.index(kind), MM.DEFAULTS[kind])
    return h


def _render(kind: str, vel_at_trig: int | None, vel_later: int | None = None) -> list[float]:
    h = _voice(kind)
    out = []
    for b in range(BLOCKS):
        if b == 0 and vel_at_trig is not None:
            h._half(M.frame_offset(M.VEL_SLOT), vel_at_trig << 8)
        if b == 4 and vel_later is not None:
            h._half(M.frame_offset(M.VEL_SLOT), vel_later << 8)
        out += h.block(60.0, trig=b == 0)
    return out


@pytest.mark.parametrize("kind", ["md", "ANALOG2", "TB303"])
def test_no_velocity_word_and_velocity_127_are_full_level(kind):
    assert _render(kind, None) == _render(kind, 127)


@pytest.mark.parametrize("kind", ["md", "ANALOG2", "TB303"])
def test_velocity_scales_the_voice(kind):
    full, half = _render(kind, 127), _render(kind, 64)
    assert max(abs(x) for x in full) > 1e-3, f"{kind}: silent"
    for x, y in zip(full, half):
        assert y == pytest.approx(x * 64 / 127, rel=1e-5, abs=1e-9)


@pytest.mark.parametrize("kind", ["md", "ANALOG2"])
def test_velocity_is_latched_at_the_note(kind):
    assert _render(kind, 100, vel_later=10) == _render(kind, 100)
