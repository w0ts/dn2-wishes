"""PERC's constant pool (2026-11-21, DSP room; the User approved it the same day).

A 48-bit immediate load `Rn = 0x...;` becomes the 32-bit `Rn = DM(k, I6);` when its value is one of the pool's
112 words: 2 bytes less in the DSP upload and in PERC's L2 spans each time, the same 32 bits in Rn, the same
instruction count. I6 holds POOL_I6 while PERC's code runs: wr_perc saves the caller's I6 with the other
registers (program.SAVE_REGS) and sets it, and the one exit (the JUMP on to smp.asm) restores it first, so
smp.asm, PING's tail (whose stock instructions read the stock frame through I6) and stock see their own I6.
PERC never used I6 (docs/dsp-perf.md: I6 / I7 are the C frame and stack). Stock's interrupt paths read I6
only to save it and restore it before they return (docs/dsp-room.md, "the I6 proof").

The pass runs on the emitted text after dnfw.perc.flow's fold, over the three spans at once (one pool), before
the jump resolver. Left as they are:
- values that fit in 16 bits, signed (-32768..32767): their load is 32-bit already (selas' short form);
- loads with a comment naming a label (`return address - 1: ...`): the resolver fills their value in;
- conditional loads (`IF ...`), loads in a compute + move, I / M / other register loads;
- the SIMD region (BIT SET MODE1 PEYEN .. BIT CLR): there a DM load writes S{n} from the next word as well.
Run mode never sees the text, so the model (which the SHARC runner holds the DSP to) is unchanged.
"""

from __future__ import annotations

import collections
import re

POOL_DM = 0x2E1980               # L1 block 1, hole F2 after the bus XDLY stores, to AMP ON/OFF's data at 0x2E1B40: 112 words
POOL_WORDS = 112                 # (128 in claude/const-pool; 112 at the combined-67 merge, main's option A, 2026-11-21)
POOL_I6 = POOL_DM + 4 * (POOL_WORDS // 2)    # DM(k, I6), k in -56..55 (inside the 32-bit form's 7-bit offset)
SIMD_ON, SIMD_OFF = "BIT SET MODE1 0x200000;", "BIT CLR MODE1 0x200000;"
LOAD = re.compile(r"^(      R(\d+) = )(-?0x[0-9a-f]+);(\s*//.*)?$")


def _value(text: str) -> int:
    return int(text, 16) & 0xFFFFFFFF


def eligible(lines: list[str]) -> list[tuple[int, int]]:
    """(line index, 32-bit value) of every load the pool may take"""
    out, simd = [], False
    for k, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith(SIMD_ON):
            simd = True
        elif s.startswith(SIMD_OFF):
            simd = False
        m = LOAD.match(ln)
        if not m or simd:
            continue
        if m.group(4) and "wr_" in m.group(4):
            continue
        v = _value(m.group(3))
        if v < 0x8000 or v >= 0xFFFF8000:          # a 16-bit signed value has a 32-bit load already: no gain
            continue
        out.append((k, v))
    assert not simd, "a SIMD region with no end"
    return out


def choose(texts: dict[str, list[str]]) -> list[int]:
    """the pool: the POOL_WORDS most frequent eligible values (ties by value), padded with zeros"""
    count = collections.Counter(v for lines in texts.values() for _k, v in eligible(lines))
    words = sorted(count, key=lambda v: (-count[v], v))[:POOL_WORDS]
    return words + [0] * (POOL_WORDS - len(words))


def apply(texts: dict[str, list[str]]) -> tuple[dict[str, list[str]], list[int], int]:
    """(the texts with the pool's loads, the pool's words, how many loads moved to the pool)"""
    words = choose(texts)
    at = {}
    for j, v in enumerate(words):
        at.setdefault(v, j - POOL_WORDS // 2)
    out, moved = {}, 0
    for name, lines in texts.items():
        new = list(lines)
        for k, v in eligible(lines):
            if v in at:                      # (any word that holds v serves; the padding zeros too)
                m = LOAD.match(lines[k])
                note = f"   // {m.group(3)} (the pool)"
                new[k] = f"{m.group(1)}DM({at[v]}, I6);".ljust(40) + note
                moved += 1
        out[name] = new
    return out, words, moved
