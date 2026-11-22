"""A voice's own clips and limiters (2026-11-20, clip-inner; the User: "NO DIGITAL CLIPPING. how clear can i make
that?", "a synth with no effect on should not digitally clip and if it does, i want the alert"; docs/mixmeter.md).

The DSP's side, run as the model over a memory of its own: a stage that clips sets guard.CLIP_HIT, out_guard's
clip_note turns it into the slot's bit in guard.CLIPMASK, and tdm_tx sends the mask in a clip packet in place of an
idle packet (never two in a row), then clears it. Each engine's own flag (PLAITS' Limiter and Clip16,
the Monomachine decimator's limiter, DRUM's drive and hold) against the stage's own threshold. The ColdFire's side is
test_mixmeter's (mix_inner_in); the voices at real settings the runner's (step clipinner)."""

from __future__ import annotations

import math

from dnfw.perc import guard as G
from dnfw.perc import program as PP
from dnfw.perc.dsl import Mem, Prog, bits, f32, flt
from dnfw.sampler import live as SL
from dnfw.sampler import machines as SM
from dnfw.sampler import program as SP


def _unit(mem: Mem, i: int) -> int:
    """unit I of the packet tdm_tx wrote this block (TAG << 24 | v << 8, or right-justified: the 16-bit value)"""
    page = SM.TDM_TX + ((mem.get(SM.TDM_PAGE) & 1) << 11)
    w = mem.get(page + 4 * (16 * (i >> 1) + 14 + (i & 1)))
    return (w >> 8) & 0xFFFF if (w >> 24) == SM.TDM_TAG else w & 0xFFFF


def _tx(mem: Mem) -> None:
    p = Prog("run", mem=mem)
    SP.tdm_tx(p, SL.layout())


def test_the_guard_words_fit():
    from dnfw.perc import machines as PM
    from dnfw.waverider import dsp
    assert G.CLIP_HIT == G.GUARD + 0xF8 and G.CLIPMASK == G.GUARD + 0xFC and G.END <= 0x2DE100
    assert dsp.PERC_SCRATCH_DM + 4 * len(PM.SC_WORDS) <= G.CLIPTRK and G.CLIPTRK + 8 <= G.INS_LO
    assert SM.CLIP_MAGIC not in (SM.TX_MAGIC, SM.POS_MAGIC, SM.LV_MAGIC, SM.RX_MAGIC)
    assert "lsc" in SM.LINK_WORDS


def test_a_clip_packet_carries_the_mask_once_then_idle():
    mem = Mem(lambda a: 0)
    mem.put(G.CLIPMASK, 1 << 4 | 1 << 11)
    _tx(mem)
    assert _unit(mem, 0) == SM.CLIP_MAGIC and _unit(mem, 1) == 1 << 4 | 1 << 11
    assert mem.get(G.CLIPMASK) == 0
    mem.put(G.CLIPMASK, 1 << 2)                       # a clip at once again: an idle packet between
    _tx(mem)
    assert _unit(mem, 0) == SM.POS_MAGIC
    assert mem.get(G.CLIPMASK) == 1 << 2              # (kept for the next block)
    _tx(mem)
    assert _unit(mem, 0) == SM.CLIP_MAGIC and _unit(mem, 1) == 1 << 2
    _tx(mem)                                          # nothing clipped: idle packets
    assert _unit(mem, 0) == SM.POS_MAGIC
    _tx(mem)
    assert _unit(mem, 0) == SM.POS_MAGIC


def test_the_clip_packet_carries_tracks_and_returns():
    mem = Mem(lambda a: 0)
    mem.put(G.CLIPTRK, 1 << 3 | 1 << (G.CLIPTRK_RET + 0))
    _tx(mem)
    assert _unit(mem, 0) == SM.CLIP_MAGIC and _unit(mem, 1) == 0 and _unit(mem, 2) == 1 << 3 and _unit(mem, 3) == 1
    assert mem.get(G.CLIPTRK) == 0


def _note_track(mem: Mem, word: int, tr: int | None, bit: int | None = None) -> None:
    mem.put(word, tr or 0)
    p = Prog("run", mem=mem)
    PP.clip_note_track(p, word if bit is None else None, bit=bit)


def test_clip_note_track_sets_the_tracks_or_the_returns_bit():
    W = 0x2D0000                                     # (a word of the caller's: the track)
    mem = Mem(lambda a: 0)
    _note_track(mem, W, 6)
    assert mem.get(G.CLIPTRK) == 0                   # nothing clipped
    mem.put(G.CLIP_HIT, 1)
    _note_track(mem, W, 6)
    assert mem.get(G.CLIPTRK) == 1 << 6 and mem.get(G.CLIP_HIT) == 0
    mem.put(G.CLIP_HIT, 1)
    _note_track(mem, W, None, bit=G.CLIPTRK_RET)
    assert mem.get(G.CLIPTRK) == 1 << 6 | 1 << 16


def test_the_voice_stream_check_is_emitted_once():
    """the Machinedrum's and Monomachine's 56300 limiter: a stream word at TOP or -1.0 exactly, checked where the voice
    reads its stream (dnfw.md.voice._resample), not at each of the limiter's sites"""
    from dnfw.md import voice as MDV
    import inspect
    src = inspect.getsource(MDV._resample)
    assert "clip_flag(p, 1, \"EQ\", 12, 12)" in src and src.count("clip_flag(") == 2


def test_a2_filter_tanh_flag():
    from dnfw.engines.analog2.filters import models as AM
    for x, want in ((2.0, False), (3.5, True), (-4.0, True)):
        mem = Mem(lambda a: 0)
        p = Prog("run", mem=mem)
        p.r[15] = bits(f32(x))
        AM._tanh_body(p)
        assert bool(mem.get(G.CLIP_HIT)) == want, x


def test_insert_input_hold_flags():
    from dnfw.inserts import design as ID
    from dnfw.inserts import program as IP
    for x, want in ((1.0, False), (ID.IN_MAX + 0.5, True), (-ID.IN_MAX - 1.0, True)):
        mem = Mem(lambda a: 0)
        p = Prog("run", mem=mem)
        p.i[0] = 0x2D1000
        mem.put(0x2D1000, bits(f32(x)))
        IP.clamp_in(p)
        assert bool(mem.get(G.CLIP_HIT)) == want, x


def test_a_levels_packet_comes_first_and_the_mask_waits():
    mem = Mem(lambda a: 0)
    L = SL.layout()
    mem.put(L.pool + SM.LV_WANT_OFF, SM.LV_WANT)
    mem.put(G.CLIPMASK, 1 << 7)
    seen = []
    for _ in range(8):
        _tx(mem)
        seen.append(_unit(mem, 0))
    assert seen.count(SM.LV_MAGIC) == 2
    assert seen.count(SM.CLIP_MAGIC) == 1 and mem.get(G.CLIPMASK) == 0
    assert all(a != SM.CLIP_MAGIC or b != SM.CLIP_MAGIC for a, b in zip(seen, seen[1:]))


def _note(mem: Mem, t: int) -> None:
    L = PP.M.layout() if hasattr(PP.M, "layout") else None
    from dnfw.perc import live as PL
    C = PL.layout().C
    mem.put(C["t"], t)
    p = Prog("run", mem=mem)
    PP.clip_note(p, C)


def test_clip_note_sets_the_slots_bit_and_clears_the_hit():
    mem = Mem(lambda a: 0)
    mem.put(G.CLIPMASK, 1 << 1)
    _note(mem, 9)                                    # nothing clipped: nothing
    assert mem.get(G.CLIPMASK) == 1 << 1
    mem.put(G.CLIP_HIT, bits(f32(0.97)))
    _note(mem, 9)
    assert mem.get(G.CLIPMASK) == 1 << 1 | 1 << 9 and mem.get(G.CLIP_HIT) == 0
    _note(mem, 0)                                    # the next voice: its own
    assert mem.get(G.CLIPMASK) == 1 << 1 | 1 << 9


def _flag(fn, regs: dict) -> int:
    """run FN(p) with the given F registers; -> CLIP_HIT after it"""
    mem = Mem(lambda a: 0)
    p = Prog("run", mem=mem)
    for r, x in regs.items():
        p.r[r] = bits(f32(x))
    fn(p)
    return mem.get(G.CLIP_HIT)


def test_drone_and_analog2_have_no_knee():
    """2026-11-21 (the User: "just make it quieter! not a limiter"): DRONE's and ANALOG 2's soft knees are gone (their
    levels keep them clear of the outputs instead): nothing left to flag"""
    from dnfw.engines.analog2 import analog2 as A
    from dnfw.engines.drone import drone as D
    for mod in (A, D):
        assert not hasattr(mod, "KNEE") and not hasattr(mod, "CLIP_AT")
    assert not hasattr(D, "_knee")


def test_plaits_clip16_and_limiter_flags():
    from dnfw.engines.plaits import plaits as PL
    assert not _flag(PL._clip16_flag, {0: 0.999, 1: -0.999})
    assert _flag(PL._clip16_flag, {0: 1.01, 1: 0.0})
    assert _flag(PL._clip16_flag, {0: 0.2, 1: -1.3})
    assert not _flag(PL._limit_flag, {7: 1.1})
    assert _flag(PL._limit_flag, {7: 1.2})


def test_drum_soft_clip_flags_only_past_its_flat():
    from dnfw.engines.plaits import plaits_drumkit as PD
    for x, want in ((2.9, False), (-2.9, False), (3.2, True), (-5.0, True)):
        mem = Mem(lambda a: 0)
        p = Prog("run", mem=mem)
        p.r[15] = bits(f32(x))
        PD.soft(p)
        assert bool(mem.get(G.CLIP_HIT)) == want, x
        assert abs(p.F(15)) <= 1.0
