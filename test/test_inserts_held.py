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
from dnfw.perc import guard as G

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
T = importlib.import_module("test_inserts")

# (2026-11-21, fx-opt2) guard.CLIPTRK too: the clip alerts (clip-inner, 2026-11-20) were added to the held loops only,
# never to the sample loops this test holds them to (it failed on combined-67 for that word alone); the TAPE_MF test
# below compares the alerts block by block; C['y0'] too: the held loops' dead per-sample store, which the msched loops
# (FOLD_MF) leave out (every reader of the word writes it first)
SCRATCH = {P.C["k"], P.C["thr"], P.C["y0"], G.CLIPTRK}


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


def _run_flags(flags: dict, script):
    old = {k: getattr(P, k) for k in flags}
    for k, v in flags.items():
        setattr(P, k, v)
    T._GEN[0] = 0
    try:
        m = T.mem0()
        out = []
        for par, bufs in script:                 # each block's outputs and its clip alerts (CLIPTRK read, then cleared)
            out.append((T.call(m, par, bufs), m.get(G.CLIPTRK), m.get(G.CLIP_HIT)))
            m.put(G.CLIPTRK, 0)
        return out, m
    finally:
        for k, v in old.items():
            setattr(P, k, v)


def _odd_script(blocks: int, seed: int):
    """_script's, with +-inf and NaN samples in a few blocks (every track) and a silent stretch"""
    out = []
    for b, (par, bufs) in enumerate(_script(blocks, seed)):
        if b in (12, 31, 47):
            bufs = [list(x) for x in bufs]
            for t in range(D.TRACKS):
                bufs[t][3 + t % 7] = float("inf")
                bufs[t][11] = float("-inf")
                bufs[t][20 + t % 5] = float("nan")
        if 60 <= b < 64:
            bufs = [[0.0] * 32 for _ in range(D.TRACKS)]
        out.append((par, bufs))
    return out


def _same(a, b, scratch=frozenset()):
    (oa, ma), (ob, mb) = a, b
    for k, (x, y) in enumerate(zip(oa, ob)):
        assert x == y, f"block {k}"
    keys = (set(ma.w) | set(mb.w)) - set(scratch)
    bad = sorted(hex(k) for k in keys if ma.get(k) != mb.get(k))
    assert not bad, bad[:8]


def test_tape_multifunction_is_the_sample_loop():
    """2026-11-21 (fx-opt2): program.TAPE_MF (both stages as msched code, stage 1's clips once a block) against
    _tape_sat / _tape_read: every buffer, each block's clip alerts and every memory word, inf / NaN inputs included"""
    script = _odd_script(80, 9)
    a = _run_flags({"TAPE_STAGED": True, "TAPE_MF": False}, script)
    assert any(c for _o, c, _h in a[0]), "the script must make TAPE clip"
    _same(a, _run_flags({"TAPE_STAGED": True, "TAPE_MF": True}, script))


def test_fold_multifunction_is_the_held_loop():
    """2026-11-21 (fx-opt2): program.FOLD_MF (FOLD's held sample as msched code, two a pass, the sine branch-free, the
    input clip once a block) against _fold_sample: every buffer, each block's clip alerts and every memory word but the
    held loop's dead per-sample stores (C['k'], C['y0'], C['thr'], never read before the next writer sets them)"""
    script = _odd_script(80, 11)
    a = _run_flags({"FOLD_MF": False}, script)
    _same(a, _run_flags({"FOLD_MF": True}, script), SCRATCH)


def test_harm_multifunction_is_the_held_loop():
    """2026-11-21 (fx-opt2): program.HARM_MF against _harm_sample, as the FOLD test"""
    script = _odd_script(80, 13)
    a = _run_flags({"HARM_MF": False}, script)
    _same(a, _run_flags({"HARM_MF": True}, script), SCRATCH)


def test_ring_multifunction_is_the_held_loop():
    """2026-11-21 (fx-opt2): program.RING_MF against _ring_sample, as the FOLD test"""
    script = _odd_script(80, 17)
    a = _run_flags({"RING_MF": False}, script)
    _same(a, _run_flags({"RING_MF": True}, script), SCRATCH)


def test_the_multifunction_maps_give_no_live_value_a_shared_register():
    for sym, regs, carried in ((P.FOLD_SYM, P.FD, P.FOLD_CARRIED), (P.HARM_SYM, P.HD, P.HARM_CARRIED),
                               (P.RING_SYM, P.RD, P.RING_CARRIED)):
        assert not P.mf_conflicts(sym, regs, carried)
        assert "F11" not in {regs[v] for o in sym for v in o[2] + o[3] if not v.startswith("I")}   # the loop's count
