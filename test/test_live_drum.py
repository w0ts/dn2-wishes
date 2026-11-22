"""DRUM's live knobs (2026-11-21, scratch/mod-live-design.md "D (sound)", rate A): on the voice's turn (each voice
every 16 blocks, dnfw.md.voice.live_turn) drum.half runs the hit's code again with S_TRIG 0 in the block's first half,
the hit's state kept (dmath.on_hit). In the model (the program the SHARC runs bit for bit): unmoved knobs give the same
output with or without the turns, every type; a knob moved mid-hit sets the hit's values a fresh hit at that knob would
have, at the turn, without resetting the sound (envelopes, phases, the filters' state, the CLOSED hat's choke word)."""

from __future__ import annotations

import pytest

from dnfw.engines.drum import clap as CL
from dnfw.engines.drum import cymbal as CY
from dnfw.engines.drum import drum as D
from dnfw.engines.drum import hats as HA
from dnfw.engines.drum import kick as KI
from dnfw.engines.drum import snare as SN
from dnfw.engines.drum import tom as TO
from dnfw.md import core as MDK
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits, flt

pytestmark = pytest.mark.skipif(D.NAME not in MM.NAMES, reason="a build without DRUM")

TYPE = next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == D.NAME)


class H:
    """one slot (0) on DRUM type T at its start; COUNT False: block_count's word never moves (no turns)"""

    def __init__(self, t: int, count: bool = True, k1=None, k2=None):
        self.h = PL.Harness()
        self.h.words[self.h.L.md.C["fill"]] = MDK.Z_N
        P = D.PLACES[t]
        self.k1 = list(P.DEFAULTS) if k1 is None else list(k1)
        self.k2 = list(P.DEFAULTS2) + [0] * (8 - len(P.DEFAULTS2)) if k2 is None else list(k2)
        self.count = count
        self.h.set_mnm(TYPE, self.k1)
        self.page2(self.k2)
        self.base = self.h.L.md.state

    def page2(self, k2) -> None:
        self.k2 = list(k2)
        for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, k2):
            self.h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))

    def page1(self, k1) -> None:
        self.k1 = list(k1)
        self.h.set_mnm(TYPE, self.k1)

    def word(self, k: int) -> int:
        return self.h.mem.get(self.base + 4 * (MDK.S0 + k))

    def turn(self) -> bool:
        n = (self.h.mem.get(MDK.BLOCKS_WORD) + (1 if self.count else 0)) & 0xFFFFFFFF
        return ((n - (self.base >> 10)) & (MDK.LIVE_EVERY - 1)) == 0

    def block(self, note: float = 60.0, trig: bool = False) -> list[float]:
        if not self.count:
            self.h.mem.put(MDK.BLOCKS_WORD, 0x0BAD0001)
        return self.h.block(note=note, trig=trig)


@pytest.mark.parametrize("t", range(D.N_TYPES), ids=D.TYPES)
def test_unmoved_knobs_give_the_same_output_with_or_without_the_turns(t):
    outs = []
    for count in (True, False):
        h = H(t, count)
        out = []
        for b in range(60):
            out += h.block(note=(48.0, 60.0, 55.0)[b // 20], trig=b in (0, 20, 40))
        outs.append([bits(x) for x in out])
    assert outs[0] == outs[1]


def _fresh(t: int, k1, k2, words) -> list[int]:
    """the hit's values (words) of a fresh hit at knobs K1, K2"""
    h = H(t, k1=k1, k2=k2)
    h.block(trig=True)
    return [h.word(w) for w in words]


# (type, page, knob, value, words the knob sets, a state word the re-read must not reset and its value at the hit)
CASES = [
    (D.KICK, 1, KI.DCAY, 110, (KI.D_AMPD, KI.D_NZD), KI.S_AMP),
    (D.KICK, 1, KI.CLKT, 120, (KI.D_CHIRP, KI.D_CLKA, KI.D_CHF0), KI.S_AMP),
    (D.KICK, 2, KI.CLKL, 120, (KI.D_CLKD, KI.D_CHD), KI.S_AMP),
    (D.KICK, 1, KI.DRIV, 127, (KI.D_G, KI.D_COMP, KI.D_ADAA), KI.S_AMP),
    (D.SNARE, 1, SN.DCAY, 120, SN.D_RS, SN.S_RE[0]),
    (D.SNARE, 2, SN.WTON, 120, (SN.W_SVF, SN.Z_SVF), SN.S_RE[0]),
    (D.TOM, 1, TO.DCAY, 120, (TO.D_AMPD, TO.D_NZD), TO.S_AMP),
    (D.TOM, 1, TO.TUNE, 100, (TO.D_F0,), TO.S_AMP),
    (D.CLHH, 1, HA.TONE, 120, (HA.B_SVF, HA.H_SVF, HA.L_SVF), HA.S_PH[0]),
    (D.OPHH, 1, HA.COLR, 120, HA.D_INC0 + (HA.D_KA, HA.D_KB), HA.S_PH[0]),
    (D.CLAP, 1, CL.DCAY, 120, (CL.D_TD, CL.D_FD), CL.S_N),
    (D.RIDE, 1, CY.DCAY, 120, (CY.D_D1, CY.D_D2), CY.S_TL1),
    (D.CRSH, 1, CY.TONE, 20, (CY.D_FB,), CY.S_TL1),
]


@pytest.mark.parametrize("t,page,k,v,words,state", CASES,
                         ids=[f"{D.TYPES[c[0]]}-p{c[1]}.{c[2]}" for c in CASES])
def test_a_knob_moved_mid_hit_sets_a_fresh_hits_values_at_the_turn_and_keeps_the_sound(t, page, k, v, words, state):
    h = H(t)
    k1, k2 = list(h.k1), list(h.k2)
    (k1 if page == 1 else k2)[k] = v
    fresh = _fresh(t, k1, k2, words)
    start = _fresh(t, k1, k2, (state,))[0]       # the state word as a hit leaves it
    at, first, old = 4, None, None
    for b in range(40):
        if b == at:
            (h.page1 if page == 1 else h.page2)(k1 if page == 1 else k2)
        if b >= at and first is None and h.turn():
            first = b
        h.block(trig=b == 0)
        if b == 0:
            old = [h.word(w) for w in words]
            assert old != fresh, "the knob moves no word it is said to set"
        elif first is None:
            assert [h.word(w) for w in words] == old
        else:
            assert [h.word(w) for w in words] == fresh
            assert h.word(state) != start        # the sound goes on: no hit's start
            break
    assert first is not None


@pytest.mark.parametrize("t,svf", [(D.SNARE, SN.W_SVF), (D.CLHH, HA.B_SVF), (D.CLAP, CL.A_SVF), (D.RIDE, CY.A_SVF)],
                         ids=["SNARE", "CLHH", "CLAP", "RIDE"])
def test_a_re_read_keeps_the_filters_state(t, svf):
    """the Svfs' s1 and s2 (its state) go on through a turn: the same as with no turn, knobs unmoved"""
    words = []
    for count in (True, False):
        h = H(t, count)
        ws = []
        for b in range(24):
            h.block(trig=b == 0)
            ws.append((h.word(svf + 3), h.word(svf + 4)))
        words.append(ws)
    assert words[0] == words[1] and any(flt(a) != 0.0 for a, _b in words[0][1:])


def test_the_type_stays_the_hits_and_a_closed_hats_choke_state_is_its_hits():
    h = H(D.CLHH)
    h.block(trig=True)
    k1 = list(h.k1)
    k1[7] = D.type_knob(D.KICK)                  # TYPE moved to KICK mid-hit: the hat goes on
    h.page1(k1)
    seen, hit = h.word(HA.S_SEEN), h.word(HA.S_HIT)
    for _b in range(20):
        h.block()
    assert h.word(D.S_TYPE) == D.CLHH and (h.word(HA.S_SEEN), h.word(HA.S_HIT)) == (seen, hit)
