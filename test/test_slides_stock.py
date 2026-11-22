"""2026-11-20 (the User): the slides step's stock comparison with SLIDE off (scripts/slides_stock.py). Exact, word for
word, but for the one declared difference: a half-rate LFO's cell (its voice row + DEST) on a frame that is not its
voice's turn. With its negative controls: a STATE word, an OUT word no LFO writes, an LFO cell on its voice's turn."""

from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import slides_stock as SS                                       # noqa: E402

N, DESTS = SS.N, (44, 25, 35)                                   # v0.62.5's snapshot: LFO1..3 DEST on every voice


def idx(v, s):
    return SS.ROW0 + SS.ROW * v + s


def frame(changes=()):
    """stock's frame: the LFO DEST cells set, a ramp elsewhere; CHANGES (kind, index) flipped"""
    st = [i * 3 for i in range(N)]
    out = [i & 0x7FFF for i in range(N)]
    for v in range(17):
        for d_slot, d in zip(SS.DEST_SLOTS, DESTS):
            out[idx(v, d_slot)] = d << 8
    for kind, i in changes:
        if kind == "state":
            st[i] ^= 1
        else:
            out[i] ^= 1
    return SS.pack(struct.pack(f">{N}i", *st) + struct.pack(f">{N}H", *out))


TURNS = [[1 if v % 2 == f % 2 else 0 for v in range(16)] for f in range(4)]   # even voices' turn on even frames
STOCK = [frame() for _ in range(4)]


def test_equal_frames_pass_with_and_without_turns():
    assert SS.compare(STOCK, list(STOCK), TURNS)[0] == []
    assert SS.compare(STOCK, list(STOCK), None)[0] == []


def test_lfo_cell_off_its_turn_is_declared():
    build = list(STOCK)
    build[0] = frame([("out", idx(1, 44)), ("out", idx(3, 25)), ("out", idx(15, 35))])  # odd voices: off on frame 0
    bad, summary = SS.compare(build, STOCK, TURNS)
    assert bad == [] and summary["declared_words"] == 3


def test_lfo_cell_on_its_turn_fails():
    build = list(STOCK)
    build[0] = frame([("out", idx(2, 44))])                     # voice 2: its turn on frame 0
    assert SS.compare(build, STOCK, TURNS)[0]


def test_without_half_rate_every_difference_fails():
    build = list(STOCK)
    build[0] = frame([("out", idx(1, 44))])
    assert SS.compare(build, STOCK, None)[0]


def test_other_words_fail():
    for change in (("out", idx(1, 67)), ("state", idx(1, 44)), ("out", idx(1, 4)), ("out", 3)):
        build = list(STOCK)
        build[1] = frame([change])
        assert SS.compare(build, STOCK, TURNS)[0], change


def test_frame_count_mismatch_fails():
    assert SS.compare(STOCK[:3], STOCK, TURNS)[0]


def test_negative_control_behaves():
    assert SS.negative_control(STOCK, TURNS) == []


def test_negative_control_needs_mixed_turns():
    assert SS.negative_control(STOCK, [[1] * 16] * 4)
