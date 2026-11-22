"""Live note-start knobs (2026-11-20, scratch/mod-live-design.md "D (sound)", rate A): each voice re-reads its engine's
note-start knobs at a trig and on its turn, one voice slot a DN2 block, each slot every 16 blocks (dnfw.md.voice
live_turn, VW['live']). In the model (the program the SHARC runs bit for bit): the turn's schedule, a knob moved
mid-note taking effect at exactly the turn (SOPHIE DCAY, TB-303 DEC with the accent latched, DRONE GLID mid-glide,
JUNO's ring start), and unmoved knobs giving the same output whether the turns come or not."""

from __future__ import annotations

import pytest

from dnfw.engines.analog2 import analog2 as A2
from dnfw.engines.drone import drone as DR
from dnfw.engines.juno import juno as JU
from dnfw.engines.sophie import sophie as SO
from dnfw.engines.tb303 import tb303 as TB
from dnfw.md import core as MDK
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits, flt

NOTE_OFF_WORD = 0x25C4B0


def _type(name: str) -> int:
    return next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == name)


class H:
    """one slot (0) on engine NAME in PERC's harness; COUNT False: block_count's word never moves (no turns)"""

    def __init__(self, name: str, knobs, knobs2=None, count: bool = True):
        self.h = PL.Harness()
        self.h.words[self.h.L.md.C["fill"]] = MDK.Z_N
        for k, v in enumerate(A2.table_words()):
            self.h.words[self.h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = bits(v)
        self.name, self.count = name, count
        self.h.set_mnm(_type(name), list(knobs))
        if knobs2 is not None:
            self.page2(knobs2)
        self.base = self.h.L.md.state                  # slot 0's words (dnfw.md.core: 1 KB a slot)
        self.blocks = 0

    def page2(self, knobs2) -> None:
        for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, knobs2):
            self.h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))

    def knobs(self, knobs) -> None:
        self.h.set_mnm(_type(self.name), list(knobs))

    def word(self, k: int) -> int:
        """the engine's state word k (dnfw.md.core S0 + k)"""
        return self.h.mem.get(self.base + 4 * (MDK.S0 + k))

    def turn(self) -> bool:
        """whether the block about to run is this slot's turn (live_turn's test on the count it will read)"""
        n = (self.h.mem.get(MDK.BLOCKS_WORD) + (1 if self.count else 0)) & 0xFFFFFFFF
        return ((n - (self.base >> 10)) & (MDK.LIVE_EVERY - 1)) == 0

    def block(self, note: float = 60.0, trig: bool = False) -> list[float]:
        if not self.count:
            self.h.mem.put(MDK.BLOCKS_WORD, 0x0BAD0001)
        self.blocks += 1
        return self.h.block(note=note, trig=trig)


def test_the_turn_comes_once_every_16_blocks_one_slot_a_block():
    h = H("SOPHIE", MM.DEFAULTS["SOPHIE"])
    turns = []
    for b in range(64):
        t = h.turn()
        h.block(trig=b == 0)
        turns.append(t)
        live = h.h.mem.get(h.base + 4 * MDK.VW["live"])
        if b > 0 and t:
            assert live == 0
    at = [b for b, t in enumerate(turns) if t]
    assert len(at) == 4 and all(b - a == 16 for a, b in zip(at, at[1:]))
    # sixteen slots: each block one slot's turn, each slot once in 16 blocks
    slots = [{s for s in range(16) if ((n - ((h.base + 1024 * s) >> 10)) & 15) == 0} for n in range(16)]
    assert all(len(x) == 1 for x in slots) and set().union(*slots) == set(range(16))


def _amul(dcay: int) -> int:
    k = list(MM.DEFAULTS["SOPHIE"])
    k[0] = dcay
    h = H("SOPHIE", k)
    h.block(trig=True)
    return h.word(SO.S_AMUL)


def _moved(name: str, k_from, k_to, word: int, at: int = 5, blocks: int = 60, knobs2=None, note: float = 60.0):
    """the knobs K_FROM at the trig (block 0), K_TO from block AT: the state WORD each block, and the first turn at
    or after AT"""
    h = H(name, k_from, knobs2)
    words, first = [], None
    for b in range(blocks):
        if b == at:
            h.knobs(k_to)
        if b >= at and first is None and h.turn():
            first = b
        h.block(note=note, trig=b == 0)
        words.append(h.word(word))
    return words, first


def test_sophie_dcay_follows_a_knob_moved_mid_note_at_the_turn():
    a, b = _amul(20), _amul(110)
    assert a != b
    k0 = list(MM.DEFAULTS["SOPHIE"])
    k0[0] = 20
    k1 = list(k0)
    k1[0] = 110
    words, first = _moved("SOPHIE", k0, k1, SO.S_AMUL)
    assert first is not None
    # (a turn whose block renders nothing, the stream's 44.1 kHz, waits for the next turn: 16 blocks on)
    changed = next(i for i, w in enumerate(words) if w != a)
    assert changed in (first, first + 16) and all(w == a for w in words[:changed]) and words[changed] == b
    assert all(w == b for w in words[changed:])


def _mc(dec: int, acc: int) -> int:
    k = list(TB.DEFAULTS)
    k[3], k[4] = dec, acc
    h = H("TB303", k)
    h.block(trig=True)
    return h.word(TB.S_MC)


@pytest.mark.parametrize("acc", [0, 100])
def test_tb303_dec_follows_a_knob_moved_mid_note_an_accented_note_keeps_its_200_ms(acc):
    k0 = list(TB.DEFAULTS)
    k0[3], k0[4] = 10, acc
    k1 = list(k0)
    k1[3] = 120
    words, first = _moved("TB303", k0, k1, TB.S_MC)
    a, b = _mc(10, acc), _mc(120, acc)
    if acc:
        assert a == b and all(w == a for w in words)    # the accent's decay, latched with the accent at the trig
        return
    assert a != b
    changed = next(i for i, w in enumerate(words) if w != a)
    assert changed in (first, first + 16) and words[changed] == b and all(w == b for w in words[changed:])


def test_tb303_acc_turned_up_mid_note_is_not_an_accent_until_the_next_trig():
    k0 = list(TB.DEFAULTS)
    k0[3], k0[4] = 10, 0
    k1 = list(k0)
    k1[4] = 127
    words, _first = _moved("TB303", k0, k1, TB.S_MC)
    assert all(w == _mc(10, 0) for w in words)


def _drone_glide(glid_from: float, glid_to: float | None, at: int = 30, blocks: int = 90):
    """DRONE: note 48 from block 0, a legato trig at block 20 and the note 60 from block 21 (the note's word lags the
    trig by a block on the DN2: DRONE acts on it at the second `pitch`), GLID > 0: a glide; GLID GLID_TO from block AT.
    -> S_GST each block, the first turn at or after AT"""
    k2 = list(DR.DEFAULTS2)
    k2[0] = glid_from
    k2 = [round(x * 127) for x in k2]
    h = H("DRONE", DR.DEFAULTS, k2)
    gst, first = [], None
    for b in range(blocks):
        if glid_to is not None and b == at:
            k = list(k2)
            k[0] = round(glid_to * 127)
            h.page2(k)
        if glid_to is not None and b >= at and first is None and h.turn():
            first = b
        h.block(note=48.0 if b < 21 else 60.0, trig=b in (0, 20))
        gst.append(flt(h.word(DR.S_GST)))
    return gst, first, h


def test_drone_glid_moved_mid_glide_changes_its_step_at_the_turn():
    still, _f, _h = _drone_glide(0.7, None)
    assert still[25] > 0 and len(set(still[25:])) == 1          # a glide, its step from its start
    moved, first, _h = _drone_glide(0.7, 0.4)
    assert first is not None
    changed = next(i for i, w in enumerate(moved) if w != still[i])
    assert changed in (first, first + 16)
    assert moved[:changed] == still[:changed]
    assert moved[changed] > still[changed]                    # a shorter glide time: a larger step


def test_drone_glid_turned_to_0_mid_glide_ends_it_at_the_note():
    moved, first, h = _drone_glide(0.9, 0.0)
    changed = next(i for i, w in enumerate(moved) if i > 21 and w == 0.0)
    assert changed in (first, first + 16)
    assert flt(h.word(DR.S_CUR)) == flt(h.word(DR.S_TGT))


def test_juno_res_turned_up_mid_note_starts_the_ring_at_the_turn():
    k0 = list(JU.DEFAULTS)
    k0[0], k0[2], k0[3], k0[5] = 0, 0, 0, 40               # every wave off, RES 40: the ladder stays still
    k1 = list(k0)
    k1[5] = 110
    words, first = _moved("JUNO", k0, k1, JU.S_Z, knobs2=JU.DEFAULTS2)
    assert all(w == 0 for w in words[:first])
    changed = next(i for i, w in enumerate(words) if w != 0)
    assert changed in (first, first + 16)


@pytest.mark.parametrize("name,k2", [("SOPHIE", None), ("TB303", None), ("JUNO", JU.DEFAULTS2),
                                     ("DRONE", tuple(round(x * 127) for x in (0.6, 0.5, 0.5, 0.5, 0.0, 1.0, 0.0)))])
def test_unmoved_knobs_give_the_same_output_with_or_without_the_turns(name, k2):
    outs = []
    for count in (True, False):
        h = H(name, MM.DEFAULTS[name], k2, count=count)
        out = []
        for b in range(70):
            out += h.block(note=(48.0, 60.0, 55.0)[max(0, b - 1) // 25], trig=b in (0, 25, 50))
        outs.append([bits(x) for x in out])
    assert outs[0] == outs[1]
