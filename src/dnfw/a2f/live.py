# SPDX-License-Identifier: AGPL-3.0-or-later
"""The filter machines' pass in run mode: the contract a2f.asm is held to, bit for bit (ported from
Optimist, GPL-3.0-only: firmware/src/engines/analog/a2_models.c, eng_analog2.c).

`run(mem)` runs dnfw.a2f.program's calls in Python on MEM (a dnfw.perc.dsl.Mem: what it has not
written it reads through its `read`, so the SHARC runner step passes the DSP's own memory there and
compares every word the pass wrote). It reads:

- the frame copy at 0x25c48c: the filter types (+180 + 2 t, s16), TRIG_NOTE (+34, bit t);
- the track records (0x2554b8 + 0x234 t): the floats at +0x1c8..+0x208 (dnfw.a2f.program's R_*);
- the slot map (0x257898 + 2 s, s16), the buffers' pointers (0x254a60 + 4 s) and their 32 floats;
- the note cells (0x254b14 + 4 t, float semitones);
- its own state (program.STATE: 16 slots x 64 bytes, its words, the mix tables of state_bytes()).

`image(...)` builds such a memory for the tests: a synthetic frame, records, map, buffers and notes.
"""

from __future__ import annotations

import struct

from ..perc.dsl import Mem, Prog, bits
from . import program as P

BUF_AT = 0x2D0000                          # where image() puts the 16 slots' buffers (a free test spot)


def run(mem: Mem, models=None) -> Prog:
    """one block of the pass on MEM; -> the Prog (its .steps: the instructions run)"""
    return P.run(mem, models)


def state_words(models=None) -> dict[int, int]:
    raw = P.state_bytes(models)
    return {P.STATE + 4 * k: v for k, (v,) in enumerate(struct.iter_unpack("<I", raw)) if v}


class Image:
    """a synthetic memory for the pass: Image().mem is a Mem; set its pieces, then run(img.mem)"""

    def __init__(self, models=None):
        self.mem = Mem()
        for a, v in state_words(models).items():
            self.mem.put(a, v)
        for s in range(16):
            self.mem.put(P.BUFFERS + 4 * s, BUF_AT + 128 * s)
        self.route([0x7FFF] * 16)

    def _half(self, base: int, i: int, v: int) -> None:
        a = base + 4 * (i >> 1)
        w = self.mem.get(a)
        w = (w & 0xFFFF) | (v & 0xFFFF) << 16 if i & 1 else (w & 0xFFFF0000) | (v & 0xFFFF)
        self.mem.put(a, w)

    def route(self, tracks) -> None:
        """slot s plays tracks[s] (0x7fff: nothing)"""
        for s, t in enumerate(tracks):
            self._half(P.ROUTE, s, t)

    def ftype(self, track: int, cf_type: int) -> None:
        self._half(P.FTYPE, track, cf_type)

    def record(self, track: int, **vals: float) -> None:
        """the track's record floats by name: mode1 freq res mode2 atk dec frq2 res2 env key"""
        rec = P.RECORDS + P.RECORD_STRIDE * track
        for name, v in vals.items():
            self.mem.put(rec + getattr(P, "R_" + name.upper()), bits(v))

    def note(self, track: int, semis: float) -> None:
        self.mem.put(P.NOTES + 4 * track, bits(semis))

    def trig(self, tracks=()) -> None:
        w = self.mem.get(P.TRIGW) & 0xFFFF
        for t in tracks:
            w |= 1 << (16 + t)
        self.mem.put(P.TRIGW, w)

    def buffer(self, slot: int, xs) -> None:
        for i, x in enumerate(xs):
            self.mem.put(BUF_AT + 128 * slot + 4 * i, bits(x))

    def read_buffer(self, slot: int) -> list[float]:
        return [struct.unpack("<f", struct.pack("<I", self.mem.get(BUF_AT + 128 * slot + 4 * i)))[0]
                for i in range(32)]
