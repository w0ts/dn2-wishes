"""live_cost.py [NAME,..]: what the live note-start knobs cost a voice-block (2026-11-20, scratch/mod-live-design.md
"D (sound)"), in the program's model (dnfw.perc.live.Harness, run mode: the same DSL text the build assembles), one
voice on track 0, its knobs still: for each engine the model's steps of a block on the voice's turn (the re-read)
against the same block with no turn (block_count's word held off the turn), and a trig block's. The difference is
the re-read's own cost (instructions; these routines touch L1 only). Prints one row an engine. Needs MD_OS_BIN (and
MNM_OS) as the build does, PYTHONPATH=src."""

from __future__ import annotations

import sys

from dnfw.engines.analog2 import analog2 as A2
from dnfw.md import core as MDK
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits

NAMES = ("SOPHIE", "TB303", "JUNO", "DRONE")


def _type(name: str) -> int:
    return next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == name)


def steps(name: str, turn: bool, blocks: int = 40) -> list[int]:
    """the steps of each block after a trig at block 0 (and a legato trig at 20 for DRONE's glide), every block a
    turn (TURN) or none"""
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):
        h.words[h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = bits(v)
    h.set_mnm(_type(name), list(MM.DEFAULTS[name]))
    if name == "DRONE":                                    # GLID 0.6: a glide from block 21
        import dnfw.perc.machines as PM
        for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, (0.6, 0.5, 0.5, 0.5, 0.0, 1.0, 0.0)):
            h._half(PM.frame_offset(slot), PL.knob_word(round(x * 127), top, lo))
    base = h.L.md.state >> 10
    out = []
    for b in range(blocks):
        n = (base if turn else base + 5) - 1            # Harness.block adds 1 before the block
        h.mem.put(MDK.BLOCKS_WORD, n & 0xFFFFFFFF)
        s0 = h.steps
        h.block(note=48.0 if b < 21 else 60.0, trig=b in (0, 20))
        out.append(h.steps - s0)
    return out


def main() -> None:
    names = sys.argv[1].split(",") if len(sys.argv) > 1 else NAMES
    print(f"{'engine':8} {'trig':>7} {'steady':>7} {'turn':>7} {'re-read':>8}")
    for name in names:
        on, off = steps(name, True), steps(name, False)
        d = [a - b for a, b in zip(on, off)]
        rows = [k for k in range(2, 40) if k not in (20, 21, 22) and off[k] > 0]
        print(f"{name:8} {max(off[0], off[20]):7} {max(off[k] for k in rows):7} {max(on[k] for k in rows):7} "
              f"{max(d[k] for k in rows):8}")


if __name__ == "__main__":
    main()
