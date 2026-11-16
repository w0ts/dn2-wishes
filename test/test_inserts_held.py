"""The pre pass's held loops (2026-11-14: TAPE in two stages, program.TAPE_STAGED; FUZZ / DIST's fz_loop, FOLD and HARM
with their state in registers, program.FZ_STAGED) against the sample loops they replace: every voice buffer and every
memory word the same, block after block, but TAPE's block scratch (C['k'], C['thr']). TAPE with the delay at its
shortest and longest (WOW and FLUT at 127), the ring's write place crossing its end at every place of a block (the
ring is 16 blocks long), a slot re-starting TAPE (its ring cleared), PGAIN and AUTO; FUZZ with its gate, DIST, FOLD
from triangle to sine, HARM odd to even, SUB one and two octaves down, RING, GATER, knobs moving."""

from __future__ import annotations

import importlib
import pathlib
import random
import sys

from dnfw.inserts import design as D
from dnfw.inserts import program as P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
T = importlib.import_module("test_inserts")

SCRATCH = {P.C["k"], P.C["thr"]}


def _script(blocks: int, seed: int):
    rnd = random.Random(seed)
    rows = {0: [D.TAPE, 127, 127, 127, 127, 127, 127, 127], 1: [D.TAPE, 127, 0, 0, 0, 0, 0, 0],
            2: [D.TAPE | D.FZ_AUTO_BIT, 100, 64, 127, 90, 40, 20, 127], 3: [D.TAPE, 90, 20, 0, 127, 0, 127, 127],
            4: [D.FUZZ, 127, 90, 70, 20, 40, 60, 100], 5: [D.FUZZ | D.FZ_AUTO_BIT, 64, 127, 127, 127, 0, 30, 127],
            6: [D.DIST, 127, 100, 40, 90, 64, 100, 127], 7: [D.FOLD, 127, 90, 40, 0, 100, 100, 0],
            8: [D.FOLD, 100, 127, 127, 127, 60, 127, 127], 9: [D.HARM, 127, 100, 60, 64, 90, 110, 0],
            10: [D.HARM, 64, 127, 127, 0, 127, 127, 127], 11: [D.SUB, 127, 100, 85, 59, 0, 127, 0],
            12: [D.SUB, 90, 127, 20, 127, 127, 40, 0], 13: [D.RING, 127, 90, 64, 100, 127, 0, 0],
            14: [D.RING, 64, 10, 127, 0, 64, 0, 0], 15: [D.GATER, 127, 127, 40, 90, 60, 100, 0]}
    out = []
    for b in range(blocks):
        if b == 30:
            rows[1] = [D.TAPE, 127, 127, 0, 127, 0, 64, 64]    # WOW and FLUT to the top while it runs
        if b == 50:
            rows[3] = [D.FUZZ] + rows[3][1:]                     # TAPE -> FUZZ -> TAPE: its ring cleared
        if b == 53:
            rows[3] = [D.TAPE] + rows[3][1:]
        if b == 40:
            rows[4] = [D.FUZZ, 100, 30, 10, 127, 127, 60, 80]     # the gate on, knobs moved
            rows[7] = [D.FOLD, 127, 30, 100, 64, 30, 90, 0]
            rows[9] = [D.HARM, 64, 127, 127, 0, 127, 127, 0]
            rows[11] = [D.SUB, 127, 30, 127, 90, 127, 127, 0]       # two octaves down
            rows[13] = [D.RING, 127, 127, 0, 127, 30, 0, 0]
            rows[15] = [D.GATER, 100, 64, 127, 20, 127, 0, 0]      # another pattern, rate, shape, swing
        loud = 6.0 if 10 <= b < 13 else 0.7
        bufs = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(D.TRACKS)]
        out.append((T.par_of(rows), bufs))
    return out


def _run(staged: bool, script):
    old = P.TAPE_STAGED, P.FZ_STAGED
    P.TAPE_STAGED = P.FZ_STAGED = staged
    T._GEN[0] = 0
    try:
        m = T.mem0()
        return [T.call(m, par, bufs) for par, bufs in script], m
    finally:
        P.TAPE_STAGED, P.FZ_STAGED = old


def test_held_loops_are_the_sample_loops():
    script = _script(70, 5)
    (oa, ma), (ob, mb) = _run(False, script), _run(True, script)
    for b, (x, y) in enumerate(zip(oa, ob)):
        assert x == y, f"block {b}"
    keys = (set(ma.w) | set(mb.w)) - SCRATCH
    bad = sorted(hex(k) for k in keys if ma.get(k) != mb.get(k))
    assert not bad, bad[:8]
