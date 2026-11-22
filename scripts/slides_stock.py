"""The slides step's stock comparison with SLIDE off (scripts/emu_slides.py, the ship gate's "parameter slides").

Every frame of the SLIDE-off runs, the whole smoother STATE (1,734 longs) and its output OUT (1,734 words) of the
build must equal stock's. One difference is declared, as `stockout` declares the User's decided differences:

**Half-rate LFOs** (DN2_LFO_HALFRATE, the User 2026-11-19, csrc/modulation/cascade.c lh_args): a voice's LFOs step
on its turn (every second frame); on the frame between, each LFO writes its DEST cell from its last output. So on a
frame that is not voice v's turn (lh_selw[v] == 0, read from the build after that frame), the OUT cells v's LFOs write
may differ from stock's: the cell at v's row + DEST for each of LFO1..3 (DEST in the row's slots 4, 12 and 20, high
byte, as the evaluator reads it). Measured on v0.62.5 (dabd3360): exactly those cells (DEST 44, 25 and 35 on every
voice), on exactly those frames, nothing in STATE. Everything else is compared exactly: STATE always, every other OUT
word, and every OUT word on a voice's turn (lh_selw 1 or 2). A build without half-rate (no turns recorded) is
compared exactly, word for word.
"""

from __future__ import annotations

import base64
import struct
import zlib

N = 1734                        # the mirror's words: 17 + 101 rows of 17 (16 voices and the FX row)
ROW0, ROW = 17, 101             # word index of voice v, slot s: 17 + 101 v + s
VOICES = 16                     # lh_selw's voices (the FX row has no LFO turn)
DEST_SLOTS = (4, 12, 20)        # LFO1..3 DEST (src/dnfw/slides.py DEST_SLOTS): the slot in the high byte


def pack(state_out: bytes) -> str:
    """a frame's STATE (4 N bytes) and OUT (2 N bytes) as the report carries them"""
    return base64.b64encode(zlib.compress(state_out)).decode()


def unpack(text: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    raw = zlib.decompress(base64.b64decode(text))
    if len(raw) != 6 * N:
        raise ValueError(f"a frame of {len(raw)} bytes, not {6 * N}")
    return struct.unpack(f">{N}i", raw[:4 * N]), struct.unpack(f">{N}H", raw[4 * N:])


def lfo_cells(out: tuple[int, ...], v: int) -> set[int]:
    """the OUT words voice V's LFO1..3 write: its row + DEST (DEST from stock's frame)"""
    base = ROW0 + ROW * v
    cells = set()
    for d in DEST_SLOTS:
        cell = base + (out[base + d] >> 8)
        if cell < N:
            cells.add(cell)
    return cells


def where(i: int) -> str:
    if i < ROW0:
        return f"word {i}"
    v, s = divmod(i - ROW0, ROW)
    return f"voice {v} slot {s}"


def compare(build: list[str], stock: list[str], turns: list[list[int]] | None) -> tuple[list[str], dict]:
    """BUILD's and STOCK's frames (pack()), TURNS the build's lh_selw after each frame (None: no half-rate).
    -> (the differences not declared, a summary)"""
    bad: list[str] = []
    declared: dict[str, int] = {}
    if len(build) != len(stock) or (turns is not None and len(turns) != len(build)):
        return [f"frames: build {len(build)}, stock {len(stock)}, turns {None if turns is None else len(turns)}"], {}
    for f, (b, s) in enumerate(zip(build, stock)):
        if b == s:
            continue
        sb, ob = unpack(b)
        ss, os_ = unpack(s)
        allowed: set[int] = set()
        if turns is not None:
            for v in range(VOICES):
                if turns[f][v] == 0:                    # not voice v's turn: its LFOs held their last output
                    allowed |= lfo_cells(os_, v)
        for i in range(N):
            if sb[i] != ss[i]:
                bad.append(f"frame {f}: STATE {where(i)} {sb[i]:#x}, stock {ss[i]:#x}")
            if ob[i] != os_[i]:
                if i in allowed:
                    declared[where(i)] = declared.get(where(i), 0) + 1
                else:
                    bad.append(f"frame {f}: OUT {where(i)} {ob[i]:#x}, stock {os_[i]:#x}")
    return bad, {"declared_cells": len(declared), "declared_words": sum(declared.values()),
                 "cells": sorted(declared)[:8]}


def negative_control(stock: list[str], turns: list[list[int]]) -> list[str]:
    """compare() on stock's own frames with words changed: a STATE word, an OUT word no LFO writes (FREQ, slot 67, of
    a voice off its turn), and an LFO cell on its voice's turn must each fail; an LFO cell off its voice's turn must
    pass. -> what did not behave so"""
    wrong = []
    f = next((k for k, t in enumerate(turns) if 0 in t[:VOICES] and any(x for x in t[:VOICES])), None)
    if f is None:
        return ["no frame with a voice on its turn and one off it"]
    st, out = unpack(stock[f])
    off = turns[f].index(0)
    on = next(v for v in range(VOICES) if turns[f][v])

    def changed(state_i=None, out_i=None):
        s2, o2 = list(st), list(out)
        if state_i is not None:
            s2[state_i] ^= 1
        if out_i is not None:
            o2[out_i] ^= 1
        frames = list(stock)
        frames[f] = pack(struct.pack(f">{N}i", *s2) + struct.pack(f">{N}H", *o2))
        return compare(frames, stock, turns)[0]
    on_cell, off_cell = min(lfo_cells(out, on)), min(lfo_cells(out, off))
    freq = ROW0 + ROW * off + 67
    if freq in lfo_cells(out, off):
        wrong.append("FREQ is an LFO cell here: pick another word")
    if not changed(state_i=ROW0 + ROW * off + 67):
        wrong.append("a STATE word changed passed")
    if not changed(out_i=freq):
        wrong.append(f"OUT {where(freq)} (no LFO) changed passed")
    if not changed(out_i=on_cell):
        wrong.append(f"OUT {where(on_cell)} changed on its voice's turn passed")
    if changed(out_i=off_cell):
        wrong.append(f"OUT {where(off_cell)} changed off its voice's turn failed")
    return wrong
