"""The SHARC runner's per-block call (scripts/sharc_waverider_m4.unpack_call, 2026-11-12, opt-md): every block is
entered from the caller's same I7, the first block's. A block's run stops on the routine's return jump, before its
delay slots restore I7, so the I7 a finished block leaves is its own frame's; taken from there, the software stack
sank 288 bytes a block and every run longer than ~351 blocks halted ("return target ... differs from recorded
return"). This pins the carried I7 without the emulator: a stand-in runner whose blocks each leave I7 lower."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m4 as m4  # noqa: E402


class _State:
    def __init__(self, i7):
        self.i7 = i7
        self.mem = {}


class _Runner:
    """fresh_call records the registers it was given; the block it starts leaves I7 288 bytes lower, as the
    emulator's runs did."""

    def __init__(self, i7):
        self.state = _State(i7)
        self.calls = []

    def fresh_call(self, pc, regs, return_address):
        r = _Runner(regs["I7"] - 272)          # the frame the routine left when the run stopped
        r.calls = self.calls + [dict(regs)]
        return r


def test_every_block_is_entered_from_the_first_blocks_i7(monkeypatch):
    monkeypatch.setattr(m4.m2, "word", lambda s, a: s.mem.get(a, 0))
    monkeypatch.setattr(m4.m2, "word_reg", lambda r, name: r.state.i7)
    monkeypatch.setattr(m4.m2, "poke", lambda s, a, v: s.mem.__setitem__(a, v))
    r = _Runner(0x2FFFB8)
    for _ in range(500):                       # well past the old halt at ~351 blocks
        r = m4.unpack_call(r, b"\0" * 8)
    assert {c["I6"] for c in r.calls} == {0x2FFFB8}
    assert {c["I7"] for c in r.calls} == {0x2FFFB8 - 16}
