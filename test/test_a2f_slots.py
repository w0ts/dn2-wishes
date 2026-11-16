"""The A2 filter pass reads each voice slot's own frame data (2026-11-12, the User's clicks on a poly ANALOG 2 track).

The trig bits (frame +34), the filter types (frame 180 + 2 n), the records (0x2554b8 + 0x234 n) and the note cells
(0x254b14 + 4 n) are per voice SLOT, as PERC reads them. The pass indexed them by the TRACK the slot plays: on a
poly track (T9, track index 8) every voice took slot 8's trig bit, so a note on slot 8 restarted the filter
envelope of every sounding voice of the track (a click once a pattern loop), and a note on any other slot never
started its own.
"""

from __future__ import annotations

import math

from dnfw.a2f import design as DS
from dnfw.a2f import live as AL
from dnfw.a2f import program as P

TRACK = 8                                       # T9
LADR = DS.TYPES.index("LADR") if "LADR" in DS.TYPES else 8
REC = dict(mode1=0.2, freq=0.49, res=0.73, mode2=0.1, atk=0.05, dec=0.09, frq2=0.5, res2=0.3, env=1.0, key=0.0)


def _image(slots=(3, 8, 9), rec8=None):
    img = AL.Image()
    route = [0x7FFF] * 16
    for s in slots:
        route[s] = TRACK
    img.route(route)
    for s in slots:
        img.ftype(s, LADR)
        img.record(s, **(rec8 if (rec8 is not None and s == 8) else REC))
        img.note(s, 48.0)
    return img


def _render(img, trigs, blocks=32, slot=3):
    """slot SLOT's output per block; TRIGS = {block: [slots]}; a held sine on SLOT, silence elsewhere"""
    out, ph = [], 0.0
    for b in range(blocks):
        img.mem.put(P.TRIGW, img.mem.get(P.TRIGW) & 0xFFFF)
        img.trig(trigs.get(b, ()))
        xs = []
        for _ in range(32):
            ph += 2 * math.pi * 110 / 48000.0
            xs.append(0.5 * math.sin(ph) + 0.25 * math.sin(3 * ph))
        img.buffer(slot, xs)
        for s in range(16):
            if s != slot:
                img.buffer(s, [0.0] * 32)
        AL.run(img.mem)
        out.append(img.read_buffer(slot))
    return out


def test_a_note_on_another_slot_of_the_track_leaves_a_sounding_voice_alone():
    held = _render(_image(), {0: [3]})
    other = _render(_image(), {0: [3], 20: [8]})
    assert other == held, "a trig on slot 8 changed slot 3's filter (its envelope restarted)"


def test_a_note_starts_its_own_slots_envelope():
    trig = _render(_image(), {0: [3]})
    none = _render(_image(), {})
    assert trig[:4] != none[:4], "a trig on slot 3 did not start slot 3's filter envelope"


def test_a_slot_reads_its_own_record():
    own = _render(_image(), {0: [3]})
    changed8 = _render(_image(rec8=dict(REC, freq=0.95, res=0.1)), {0: [3]})
    assert own == changed8, "slot 3's filter followed slot 8's record"


# the User, 2026-11-12: "if I play the sound of track 10 and 9, and 9 many times, the sound [of track 10] changes"
T10_REC = dict(REC, freq=0.3, res=0.4, env=0.8)
T9_REC = dict(REC, freq=0.9, res=0.95, env=1.0)


def _two_tracks(t9_rec=T9_REC):
    """slot 0 plays T10 (track index 9), slots 1..15 play T9 (track index 8), each slot with its own track's sound"""
    img = AL.Image()
    img.route([9] + [TRACK] * 15)
    for s in range(16):
        img.ftype(s, LADR)
        img.record(s, **(T10_REC if s == 0 else t9_rec))
        img.note(s, 55.0 if s == 0 else 48.0)
    return img


def test_notes_of_another_track_leave_a_held_voice_alone():
    alone = _render(_two_tracks(), {0: [0]}, blocks=40, slot=0)
    t9 = {0: [0], **{1 + 2 * k: [1 + k] for k in range(15)}}            # a T9 note on every slot 1..15
    with_t9 = _render(_two_tracks(), t9, blocks=40, slot=0)
    assert with_t9 == alone, "T9's notes (the one on slot 9 = T10's track index) changed T10's held voice"


def test_another_tracks_sound_on_the_slot_of_my_track_index_does_not_change_mine():
    a = _render(_two_tracks(), {0: [0]}, blocks=24, slot=0)
    b = _render(_two_tracks(t9_rec=dict(T9_REC, freq=0.1, res=0.0, env=0.5)), {0: [0]}, blocks=24, slot=0)
    assert a == b, "T10's voice followed the record of slot 9 (a T9 voice)"
