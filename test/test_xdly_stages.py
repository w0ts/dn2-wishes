"""XDLY's block with its x / xb first and its words through I3 (dnfw.xdly.program.STAGED, 2026-11-14) against the
sample loop it replaces: the same output and the same memory, word for word, block after block (but FDN8's block
buffers, where the new block keeps its x / xb), over test_xdly's script (the switch, noise, the knee, the knobs
moving, the silent skip) and the second page (the spread, the width, the knee's place)."""

from __future__ import annotations

import importlib
import pathlib
import sys

from dnfw.fdn8 import stages as FS
from dnfw.xdly import program as P

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
T = importlib.import_module("test_xdly")

_X = FS.bufs()[0]
SCRATCH = set(range(_X, _X + FS.BUF_BYTES, 4))


def _block(m, staged: bool, *a):
    old = P.STAGED
    P.STAGED = staged
    try:
        return T.call(m, *a)
    finally:
        P.STAGED = old


def _ab(ex=None, blocks=200):
    ma, mb = T.mem0(), T.mem0()
    if ex:
        T.put_ex(ma, 1, *ex)
        T.put_ex(mb, 1, *ex)
    for b, (tw, inl, inr, par) in enumerate(T.script(blocks=blocks)):
        assert _block(ma, False, tw, inl, inr, par) == _block(mb, True, tw, inl, inr, par), f"{ex} block {b}"
        keys = (set(ma.w) | set(mb.w)) - SCRATCH
        bad = [k for k in keys if ma.get(k) != mb.get(k)]
        assert not bad, f"{ex} block {b}: {sorted(hex(k) for k in bad)[:6]}"


def test_staged_is_the_sample_loop():
    _ab()


def test_staged_second_page():
    for ex in ((90, 30, 40, 100), (10, 127, 0, 64)):
        _ab(ex, blocks=150)
