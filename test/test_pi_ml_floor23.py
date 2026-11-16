"""PI-ML's branch-free floor (pi_ml.floor23r, opt-md 2026-11-12) against the floor it replaced (floor23), in run
mode, bit for bit, over the whole range a valid state reaches: the 56300 accumulator, |a| < 256 (docs/md.md).

Declared difference outside it: for a <= -256 the old form's TRUNC saturates at -2^31 and its - 1 wraps to
+2^31 - 1 (+256); floor23r gives -256. Only garbage state gets there."""

import random
import struct

from dnfw.md import pi_ml as M
from dnfw.perc.dsl import Prog


def _bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _both(word: int) -> tuple[int, int]:
    out = []
    for fn in (M.floor23, M.floor23r):
        p = Prog("run")
        if fn is M.floor23r:
            M.consts(p)
        p.r[8] = word
        fn(p, 10, 8, 13, 14)
        out.append(p.r[10])
    return out[0], out[1]


def _cases(n: int) -> list[int]:
    rnd = random.Random(23)
    words = [0, 0x80000000, 1, 0x80000001, _bits(-255.99998), _bits(255.99998), _bits(-1.0), _bits(1.0)]
    for _ in range(n):
        r = rnd.random()
        if r < 0.4:
            words.append(_bits(rnd.uniform(-256.0, 256.0)))
        elif r < 0.7:
            words.append(_bits(rnd.uniform(-2.0, 2.0)))
        else:                                    # on and one ulp beside the 2^-23 grid
            k = rnd.randrange(-(1 << 31) + 1, 1 << 31)
            b = _bits(k * 2.0 ** -23) + rnd.choice((-1, 0, 1))
            words.append(b & 0xFFFFFFFF)
    return words


def test_floor23r_is_floor23_over_the_accumulators_range():
    bad = []
    for w in _cases(20000):
        x = struct.unpack("<f", struct.pack("<I", w))[0]
        if not abs(x) < 256.0:
            continue
        a, b = _both(w)
        if a != b:
            bad.append((hex(w), hex(a), hex(b)))
    assert not bad, bad[:10]
