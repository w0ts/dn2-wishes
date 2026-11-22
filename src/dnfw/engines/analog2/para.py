# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG 2's and JUNO's paraphonic mode, PARA, as ONE voice (2026-11-16, the User: "i would rather take one bigger
voice"; docs/paraphonic-onevoice.md; the pilot before it, slot chords: docs/paraphonic.md).

A PARA chord plays on ONE voice slot, its LEADER: the slot stock's allocator gave the chord's first note. The
chord's later notes take no slot (csrc/para/one.c): the ColdFire lists them in the leader's ROW (PV_ROWS, the pool's
DDR, the TDM link writes it: one.h's places), and the leader renders them. Each joined note (a PLACE of the row)
renders from its own state block, a SHADOW: a 1 KB block of the POOL laid out as a slot's words, so the engine's own
per-note part (oscillators, noise, drive: today's member render, the 2026-11-15 design B) runs on it unchanged, with
the leader's knobs, its pitch plus the place's offset, at the leader's stream position. The leader's own render then
adds every shadow's post-drive half to its own before its filter, knee and AMP (the chord's: one filter, one
envelope, the leader's velocity). Its shadows render inside the leader's voice call, so the frame guard and the
budget see one voice a chord.

Each block (`prepass`, after mnm_ages): a slot's note-on (frame +34) starts a new chord on it (its row then waits for
the ColdFire's next chord); a PARA slot (ANALOG 2 or JUNO, PARA ON) adopts its row's chord; every shadow of a place no
longer sounding (dropped for a newer note, the chord gone, the slot given to another note) fades out over FADE_HALVES
halves and is freed; a sounding place without a shadow takes a free block (none free: it is left out, LOST counted);
ROLE[s] = LEADER while the slot owns a shadow or its own note fades (place 0 dropped: "Drop the oldest", the leader
leads on, its own note faded out).

Memory: AREA (L1 F1, zeros in the upload, so after every DSP load): ROLE[16], CSEQ[16] (the chord the slot plays:
its row's seq, VALID, AWAIT while the row still shows the chord before its note-on, the seq then), OWN[16] (this
block: the places with a playing shadow), RROLE (the render's role: MEMBER while a shadow renders, the slot's
otherwise), INIT, FREE (the pool's free blocks), LOST, the shadow loop's words. POOL (L2): POOL_N blocks of 1 KB, each
block's META word (its last, 255, no machine's): in use, owner slot, place, place seq, chord seq, FADE, NEW, offset.
PV_ROWS lives in DDR across a DSP restart: the first block after a load zeroes it (the ColdFire sends rows only once
the tables are READY, after that).
"""

from __future__ import annotations

from ...md import core as MDK
from ...perc import machines as PM
from ...perc.dsl import Prog

AREA = 0x2E0E44                                  # dnfw.waverider.dsp.PARA_DM: L1 F1 (main, the arbiter, 2026-11-15/16)
ROLE = AREA                                      # [16 slots]: the slot's role this block, its own note's FADE
CSEQ = ROLE + 64                                 # [16 slots]: the chord it plays
OWN = CSEQ + 64                                  # [16 slots]: places with a playing shadow (this block)
RROLE = OWN + 64                                 # the render's role
INIT = RROLE + 4                                 # 0 until the first block after a DSP load
FREE = INIT + 4                                  # the pool's free blocks (bit b)
LOST = FREE + 4                                  # places left out for want of a block (counted)
SH_N = LOST + 4                                  # the shadow loop: its count, the block, the leader's pitch and pos
SH_B = SH_N + 4
SH_PITCH = SH_B + 4
SH_POS = SH_PITCH + 4
SH_BIT = SH_POS + 4
WORDS = 3 * 16 + 9
MEMBER, LEADER, DROPPED = 1, 2, 3                # (MEMBER: a shadow's render; slots are LEADER or none since 2026-11-16)
ROLE_SHIFT, LEAD_SHIFT = 24, 16
RENDERED = 1 << 20                               # (unused since 2026-11-16: kept for the callers' asserts)
FADE_SHIFT, FADE_HALVES, FADE_OUT = 21, 6, 7
FADE_MASK = 7 << FADE_SHIFT
PARA_REC = PM.P3_RECS[5]                         # MOD (id 248, slot 37, 0..0x300, default 0): PARA OFF / ON
PITCHES = 8                                      # ON: a chord's notes that play (the ColdFire drops the oldest past 8)
ON_VALUE = 3                                     # what the VOICE menu stores for ON (an older build reads it as its 4 pitches)
ENGINES = ("ANALOG2", "JUNO")
NOTE_ON, NOTE_OFF = 34, 36                       # the frame's note-on and note-off masks (one bit a slot)
assert (PM.FRAME + NOTE_OFF) % 4 == 0 and (PM.FRAME + NOTE_ON) % 4 == 2       # 36 a word's low half, 34 a high
# the pool (2026-11-16, the User's Q5: L2; the place is the arbiter's, docs/memory-map.md)
POOL = 0x200EA000
POOL_N = 16
BLOCK = MDK.MD_STRIDE                            # 1 KB: a slot's words
META = MDK.MD_WORDS - 1                          # word 255: no machine's (dnfw.mnm.core VW ends at 254)
M_USE, M_NEW = 1 << 31, 1 << 15
M_SLOT, M_PLACE, M_PSEQ, M_FADE, M_OFF, M_CSEQ = 0, 4, 8, 12, 16, 24
# the rows (csrc/para/one.h, dnfw.sampler.machines PV_TABLE): PV_ROW_WORDS words a slot, halfword 0 the chord (bit 15
# live, bits 8..11 its seq), halfword 1 + k place k (bits 0..7 its offset from the leader's note, 8 held, 9 sounding,
# 10 used, 12..15 its seq); place 0 the leader's own note
PLACES = 10
P_SOUND, P_USED = 0x200, 0x400
# 2026-11-17 (the User: "shouldnt voice just one dsp voice if one exist already?"; v0.57.1 on the unit: the row came over
# the TDM link a period or more after the leader's note-on, and only the lowest note sounded): the row travels in the
# voice's own frame words, frame slots ROW_SLOT .. ROW_SLOT + 11 (halfword i in slot ROW_SLOT + i), so the DSP never
# sees the voice without its pitches. FM TONE's records (SYN group, frame slots 25..64): none of ours reads 50..61
# (PARAMS, FX_PARAMS, P3_RECS, TYPE_REC: 25..49; VEL_SLOT 62). The ColdFire writes them every frame on a voice whose
# sound is ANALOG 2 or JUNO (csrc/para/one.c pv_out, after the smoother, as the velocity); the pass copies a looked-at
# slot's into its row (DDR) and reads the row as before
ROW_SLOT = 50
C_VALID, C_AWAIT = 1 << 4, 1 << 5


def rows() -> int:
    from ...sampler import machines as SM
    from ...waverider import dsp
    return dsp.SMP_POOL_DDR + SM.PV_TABLE


def row_words() -> int:
    from ...sampler import machines as SM
    return SM.PV_ROW_WORDS


assert POOL % 4 == 0 and META not in MDK.VW.values()


def _frame_half(p: Prog, d: int, off: int, k: int) -> None:
    """Rd = the frame copy's 16-bit word at OFF + Rk bytes. Clobbers R10, R12, R13, I1."""
    p.iconst(12, PM.FRAME + off)
    p.iop(13, 12, "+", k)
    p.iconst(12, 2)
    p.iop(10, 13, "AND", 12)
    p.iconst(12, -4)
    p.iop(13, 13, "AND", 12)
    p.seti(1, 13)
    p.ldi(d, 0, 1)
    p.ifz(10, "NE", lambda: p.lsh(d, d, -16))
    p.iconst(12, 0xFFFF)
    p.iop(d, d, "AND", 12)


def types() -> tuple[int, ...]:
    """the frame's machine types of ENGINES"""
    from ...mnm import machines as MNM
    from ...perc import program as PP
    return tuple(t for t, k in PP.MNM_TYPES.items() if MNM.NAMES[k] in ENGINES)


def _pitches(p: Prog, d: int, u: int, kinds: tuple[int, ...]) -> None:
    """Rd = the chord's pitches on slot Ru: 4 when PARA is ON (any value but 0: 2026-11-15, the User, OFF / ON; an
    older project's 1 or 2 plays as ON); 0 when PARA is off or the slot's machine is not one of KINDS (the frame's
    types). Ru in R8, R9, R14 or R15. Clobbers R10..R13, I1."""
    p.iop(11, u, "+", u)                         # 2 u
    _frame_half(p, d, 148, 11)                   # the slot's machine type

    def para():
        p.lsh(11, u, 7)                          # 146 u: the slot's records
        p.lsh(12, u, 4)
        p.iop(11, 11, "+", 12)
        p.lsh(12, u, 1)
        p.iop(11, 11, "+", 12)
        _frame_half(p, d, PM.frame_offset(PARA_REC[1]), 11)
        p.lsh(d, d, -8)                          # the record's value (0..3 stored)
        p.ifz(d, "NE", lambda: p.iconst(d, PITCHES))
    p.iconst(10, 0)
    for k in kinds:
        p.iconst(12, k)
        p.if_(d, "EQ", 12, lambda: p.iconst(10, 1), kind="i")
    p.ifz(10, "NE", para, lambda: p.iconst(d, 0))


def _at(p: Prog, i: int, base: int, r: int) -> None:
    """Ii = BASE + 4 Rr. Clobbers R12, R13."""
    p.lsh(13, r, 2)
    p.iconst(12, base)
    p.iop(13, 12, "+", 13)
    p.seti(i, 13)


def _step(p: Prog, i: int) -> None:
    """Ii += 4. Clobbers R12, R13."""
    p.geti(12, i)
    p.iconst(13, 4)
    p.iop(12, 12, "+", 13)
    p.seti(i, 12)


def _hw(p: Prog, d: int, s: int, h: int) -> None:
    """Rd = halfword H of slot Rs's row (DDR). Rs in R8..R11, R14, R15. Clobbers R12, R13, I1."""
    _times(p, 13, s, 4 * row_words())
    p.iconst(12, rows() + 4 * (h >> 1))
    p.iop(13, 12, "+", 13)
    p.seti(1, 13)
    p.ldi(d, 0, 1)
    if h & 1:
        p.lsh(d, d, -16)
    p.iconst(12, 0xFFFF)
    p.iop(d, d, "AND", 12)


def _times(p: Prog, d: int, s: int, k: int) -> None:
    """Rd = Rs x K (K a small constant: shifts and adds). Clobbers R12."""
    assert 0 < k < 256
    p.iconst(d, 0)
    for b in range(8):
        if k >> b & 1:
            p.lsh(12, s, b)
            p.iop(d, 12, "+", d)


def _block(p: Prog, d: int, b: int) -> None:
    """Rd = pool block Rb's address. Clobbers R12."""
    p.lsh(d, b, 10)
    p.iconst(12, POOL)
    p.iop(d, 12, "+", d)


def _field(p: Prog, d: int, m: int, shift: int, bits: int) -> None:
    """Rd = (Rm >> SHIFT) & (2^BITS - 1). Clobbers R12."""
    p.lsh(d, m, -shift)
    p.iconst(12, (1 << bits) - 1)
    p.iop(d, d, "AND", 12)


# -- the pass: the chords, the shadows, the roles ---------------------------------------------------------------------

def _first(p: Prog) -> None:
    """the first block after a DSP load: the rows zeroed (DDR keeps an earlier boot's), the pool free, its META words
    zero. Clobbers R0, R12, R13, I1."""
    def go():
        p.iconst(12, rows())
        p.seti(1, 12)
        p.iconst(0, 0)
        p.loop_r(13, 16 * row_words(), lambda: p.stpost(1, 0))
        for b in range(POOL_N):
            p.st(POOL + BLOCK * b + 4 * META, 0)
        p.iconst(0, (1 << POOL_N) - 1)
        p.st(FREE, 0)
        p.iconst(0, 1)
        p.st(INIT, 0)
    p.ld(0, INIT)
    p.ifz(0, "EQ", go)


def _chords(p: Prog, trig_word: int, kinds: tuple[int, ...]) -> None:
    """each slot's chord (CSEQ), OWN cleared, ROLE's role bits cleared (FADE kept while the chord is the same): a note-on
    on the slot waits for a new row; a PARA slot adopts its row's chord; its own note dropped starts its fade. Clobbers
    R0..R15, I0..I2."""
    p.ld(3, trig_word)
    p.lsh(3, 3, -16)                             # R3: the note-ons
    p.ld(15, WATCH)
    p.iop(15, 15, "OR", 3)                       # R15: the slots to look at (a note-on, or watched: _watch)
    p.iconst(9, 0)                               # s
    p.iconst(8, 1)                               # its bit

    def one():
        p.iop(12, 15, "AND", 8)
        p.ifz(12, "NE", lambda: _chord_of(p, kinds))
        p.iconst(12, 1)
        p.iop(9, 12, "+", 9)
        p.iop(8, 8, "+", 8)
    p.loop_r(14, 16, one)


def _row_from_frame(p: Prog) -> None:
    """slot R9's row (DDR) = its frame words ROW_SLOT .. ROW_SLOT + 2 row_words() - 1 (this block's frame). Keeps R3,
    R8, R9, R14, R15. Clobbers R0..R2, R10..R13, I0, I1."""
    assert 2 * row_words() == 12 and ROW_SLOT + 11 < PM.VEL_SLOT
    p.lsh(11, 9, 7)                              # 146 s: the slot's records
    p.lsh(12, 9, 4)
    p.iop(11, 11, "+", 12)
    p.lsh(12, 9, 1)
    p.iop(11, 11, "+", 12)
    _times(p, 2, 9, 4 * row_words())
    p.iconst(12, rows())
    p.iop(2, 12, "+", 2)                         # R2: the row's word j
    for j in range(row_words()):
        _frame_half(p, 0, PM.frame_offset(ROW_SLOT + 2 * j), 11)
        _frame_half(p, 1, PM.frame_offset(ROW_SLOT + 2 * j + 1), 11)
        p.lsh(1, 1, 16)
        p.iop(0, 0, "OR", 1)
        p.seti(0, 2)
        p.sti(0, 0, 0)
        p.iconst(12, 4)
        p.iop(2, 12, "+", 2)


def _chord_of(p: Prog, kinds: tuple[int, ...]) -> None:
    """slot R9 (its bit R8; R3 the note-ons): its chord, OWN cleared, its role bits cleared. Keeps R3, R8, R9, R14, R15.
    Clobbers R0..R2, R4..R7, R10..R13, I0..I2."""
    _row_from_frame(p)
    _at(p, 0, CSEQ, 9)
    p.ldi(6, 0, 0)                           # R6: CSEQ[s]
    _at(p, 2, ROLE, 9)
    p.ldi(7, 0, 2)                           # R7: ROLE[s]
    p.iop(12, 3, "AND", 8)

    def noted():                             # a new note on the slot: the old chord's seq kept, the row awaited
        p.iconst(12, 15)
        p.iop(0, 6, "AND", 12)
        p.lsh(0, 0, 8)
        p.iconst(12, C_AWAIT)
        p.iop(6, 0, "OR", 12)
        p.iconst(7, 0)
    p.ifz(12, "NE", noted)
    _pitches(p, 5, 9, kinds)                 # R5: PARA on this slot (its engine, its value)

    def para():
        _hw(p, 0, 9, 0)                      # the chord
        p.iconst(12, 0x8000)
        p.iop(1, 0, "AND", 12)
        _field(p, 2, 0, 8, 4)                # its seq

        def live():
            p.iconst(12, C_AWAIT)
            p.iop(4, 6, "AND", 12)

            def awaiting():
                _field(p, 4, 6, 8, 4)
                p.if_(2, "NE", 4, lambda: (p.iconst(12, C_VALID), p.iop(6, 2, "OR", 12)), kind="i")

            def adopted():
                p.iconst(12, 15)
                p.iop(4, 6, "AND", 12)
                p.iconst(12, C_VALID)
                p.iop(10, 6, "AND", 12)
                p.ifz(10, "EQ", lambda: p.iconst(4, -1))
                p.if_(2, "NE", 4, lambda: (p.iconst(12, C_VALID), p.iop(6, 2, "OR", 12), p.iconst(7, 0)),
                      kind="i")
            p.ifz(4, "NE", awaiting, adopted)
            p.iconst(12, C_VALID)
            p.iop(4, 6, "AND", 12)

            def own():                       # place 0, the leader's own note: dropped -> its fade starts
                _hw(p, 0, 9, 1)
                p.iconst(12, P_SOUND)
                p.iop(0, 0, "AND", 12)
                p.lsh(1, 7, -FADE_SHIFT)
                p.iconst(12, 7)
                p.iop(1, 1, "AND", 12)
                p.ifz(0, "EQ", lambda: p.ifz(1, "EQ", lambda: (p.iconst(12, FADE_HALVES << FADE_SHIFT),
                                                                 p.iop(7, 7, "OR", 12))))
            p.ifz(4, "NE", own)

        def no_chord():                      # 2026-11-17 (v0.57.1 on the unit: only the chord's lowest note sounded):
            p.iconst(12, C_AWAIT)            # a note-on's AWAIT kept while the row shows no chord yet (the TDM link
            p.iop(4, 6, "AND", 12)           # brings the chord's row a period or more after the note-on's frame), so
            p.ifz(4, "EQ", lambda: p.iconst(6, 0))   # the slot stays watched until it comes; else no chord
            p.iconst(7, 0)
        p.ifz(1, "NE", live, no_chord)
    p.ifz(5, "NE", para, lambda: (p.iconst(6, 0), p.iconst(7, 0)))
    p.sti(0, 0, 6)
    p.iconst(12, FADE_MASK)
    p.iop(7, 7, "AND", 12)                   # role bits cleared
    p.sti(0, 2, 7)
    _at(p, 1, OWN, 9)
    p.iconst(0, 0)
    p.sti(0, 1, 0)


def _leader(p: Prog, s: int) -> None:
    """ROLE[Rs] |= LEADER. Clobbers R12, R13, I1."""
    _at(p, 1, ROLE, s)
    p.ldi(13, 0, 1)
    p.iconst(12, LEADER << ROLE_SHIFT)
    p.iop(13, 13, "OR", 12)
    p.sti(0, 1, 13)


def _shadow_kept_one(p: Prog, rests: tuple[int, int] | None = None) -> None:
    """block R15 (the pool loop's): a shadow in use: its place still sounding in its owner's chord (the same chord, the same note): it plays
    (OWN); else it fades out (FADE_HALVES halves, moved on by its leader's halves); out: freed. Its owner LEADS while
    it is in use. RESTS (the slots' rest counts' address, the count from which a voice rests): a shadow that no longer
    plays and whose owner rests is freed at once (2026-11-18, v0.59.2 on the unit: a resting voice is not rendered, so
    its shadows' fades never moved on and their blocks stayed taken until the slot's next note; the pool ran dry and
    chords played without their members. A resting voice's sound has died away after its AMP: nothing of it is
    heard). Clobbers R0..R15, I0..I2."""
    def one():
        _block(p, 14, 15)
        p.iconst(12, 4 * META)
        p.iop(14, 14, "+", 12)
        p.seti(0, 14)
        p.ldi(11, 0, 0)                          # R11: its META

        def used():
            _field(p, 9, 11, M_SLOT, 4)
            _field(p, 10, 11, M_PLACE, 4)
            _field(p, 4, 11, M_FADE, 3)

            def free_it():
                p.iconst(0, 0)
                p.sti(0, 0, 0)
                p.ld(0, FREE)
                p.iconst(12, 1)
                MDK._shift_r(p, 12, 12, 15)
                p.iop(0, 0, "OR", 12)
                p.st(FREE, 0)

            def live():
                _at(p, 1, CSEQ, 9)
                p.ldi(6, 0, 1)                   # CSEQ[owner]
                p.iconst(5, 0)                   # R5: it plays on
                p.iconst(12, C_VALID)
                p.iop(12, 6, "AND", 12)

                def same_chord():
                    p.iconst(12, 15)
                    p.iop(6, 6, "AND", 12)
                    _field(p, 7, 11, M_CSEQ, 4)

                    def place():
                        p.iconst(12, 1)
                        p.iop(12, 10, "+", 12)
                        p.ipass(13, 12)
                        # Rd = the place's halfword (1 + k): word (1 + k) >> 1, high half when odd
                        p.lsh(12, 13, -1)
                        p.lsh(12, 12, 2)
                        p.ipass(2, 12)
                        _times(p, 1, 9, 4 * row_words())
                        p.ipass(12, 2)
                        p.iop(1, 12, "+", 1)
                        p.iconst(12, rows())
                        p.iop(1, 12, "+", 1)
                        p.seti(1, 1)
                        p.ldi(0, 0, 1)
                        p.iconst(12, 1)
                        p.iop(13, 13, "AND", 12)
                        p.ifz(13, "NE", lambda: p.lsh(0, 0, -16))
                        p.iconst(12, 0xFFFF)
                        p.iop(0, 0, "AND", 12)
                        p.iconst(12, P_SOUND | P_USED)
                        p.iop(1, 0, "AND", 12)
                        _field(p, 2, 0, 12, 4)
                        _field(p, 3, 11, M_PSEQ, 4)
                        p.iconst(12, P_SOUND | P_USED)
                        p.if_(1, "EQ", 12, lambda: p.if_(2, "EQ", 3, lambda: p.iconst(5, 1), kind="i"), kind="i")
                    p.if_(6, "EQ", 7, place, kind="i")
                p.ifz(12, "NE", same_chord)

                def plays():
                    _at(p, 1, OWN, 9)
                    p.ldi(0, 0, 1)
                    p.iconst(12, 1)
                    MDK._shift_r(p, 12, 12, 10)
                    p.iop(0, 0, "OR", 12)
                    p.sti(0, 1, 0)

                def fade():                      # (an early fade keeps its FADE: its leader moves it on)
                    p.ifz(4, "EQ", lambda: (p.iconst(12, FADE_HALVES << M_FADE), p.iop(11, 11, "OR", 12),
                                            p.sti(0, 0, 11)))

                def fades():
                    if rests is None:
                        fade()
                        return
                    _at(p, 1, rests[0], 9)       # the owner's rest count
                    p.ldi(13, 0, 1)
                    p.iconst(12, rests[1])
                    p.if_(13, "GE", 12, free_it, fade, kind="i")
                p.ifz(5, "NE", lambda: p.ifz(4, "EQ", plays, fades), fades)
                _leader(p, 9)
            p.iconst(12, FADE_OUT)
            p.if_(4, "EQ", 12, free_it, live, kind="i")
        p.ifz(11, "NE", used)
    one()


def _loop_pool(p: Prog, body) -> None:
    """body() POOL_N times (its count in a scratch word: the body may use every register; it reads b from SH_BIT)"""
    p.iconst(0, 0)
    p.st(SH_BIT, 0)

    def each():
        p.ld(15, SH_BIT)
        body()
        p.ld(15, SH_BIT)
        p.iconst(12, 1)
        p.iop(15, 12, "+", 15)
        p.st(SH_BIT, 15)
    p.loop(SH_N, POOL_N, each)


def _new_shadows(p: Prog, kinds: tuple[int, ...]) -> None:
    """each PARA slot's chord: a sounding place with no playing shadow takes a free block (the lowest), zeroed as a
    fresh slot's words (no machine, the stream asking for a block), its META a NEW note; none free: LOST. Clobbers
    R0..R15, I0..I2."""
    p.iconst(9, 0)

    def slot():
        _at(p, 0, CSEQ, 9)
        p.ldi(6, 0, 0)
        p.iconst(12, C_VALID)
        p.iop(12, 6, "AND", 12)

        def chord():
            p.iconst(10, 1)                      # k

            def place():
                # R0 = place k's halfword (as in _shadows_kept)
                p.iconst(12, 1)
                p.iop(13, 10, "+", 12)
                p.lsh(12, 13, -1)
                p.lsh(12, 12, 2)
                p.ipass(2, 12)
                _times(p, 1, 9, 4 * row_words())
                p.ipass(12, 2)
                p.iop(1, 12, "+", 1)
                p.iconst(12, rows())
                p.iop(1, 12, "+", 1)
                p.seti(1, 1)
                p.ldi(0, 0, 1)
                p.iconst(12, 1)
                p.iop(13, 13, "AND", 12)
                p.ifz(13, "NE", lambda: p.lsh(0, 0, -16))
                p.iconst(12, 0xFFFF)
                p.iop(0, 0, "AND", 12)
                p.iconst(12, P_SOUND | P_USED)
                p.iop(1, 0, "AND", 12)
                _at(p, 1, OWN, 9)
                p.ldi(2, 0, 1)
                p.iconst(13, 1)
                MDK._shift_r(p, 13, 13, 10)
                p.iop(2, 2, "AND", 13)

                def wants():
                    p.ld(3, FREE)

                    def take():
                        p.iconst(4, 0)           # the lowest free block
                        p.iconst(5, 1)
                        p.iconst(7, -1)

                        def find():
                            p.iop(12, 3, "AND", 5)
                            p.ifz(12, "NE", lambda: p.ifz(7, "LT", lambda: p.ipass(7, 4)))
                            p.iconst(12, 1)
                            p.iop(4, 12, "+", 4)
                            p.lsh(5, 5, 1)
                        p.loop_r(13, POOL_N, find)
                        p.iconst(12, 1)
                        MDK._shift_r(p, 12, 12, 7)
                        p.iop(3, 3, "-", 12)
                        p.st(FREE, 3)
                        _block(p, 4, 7)
                        p.seti(1, 4)
                        p.iconst(5, 0)
                        p.loop_r(13, MDK.MD_WORDS, lambda: p.stpost(1, 5))
                        p.seti(1, 4)
                        p.iconst(5, -1)
                        p.sti(MDK.VW["mach"], 1, 5)
                        from ...md import voice as MDV
                        p.fconst(5, MDV.START)
                        p.sti(MDK.VW["pos"], 1, 5)
                        # META: in use, NEW, the owner, the place, the place's seq, the chord's seq, the offset
                        p.iconst(5, M_USE | M_NEW)
                        p.iop(5, 5, "OR", 9)
                        p.lsh(12, 10, M_PLACE)
                        p.iop(5, 5, "OR", 12)
                        _field(p, 3, 0, 12, 4)
                        p.lsh(3, 3, M_PSEQ)
                        p.iop(5, 5, "OR", 3)
                        p.iconst(12, 15)
                        p.iop(3, 6, "AND", 12)
                        p.lsh(3, 3, M_CSEQ)
                        p.iop(5, 5, "OR", 3)
                        p.iconst(12, 0xFF)
                        p.iop(3, 0, "AND", 12)
                        p.lsh(3, 3, M_OFF)
                        p.iop(5, 5, "OR", 3)
                        p.sti(META, 1, 5)
                        _leader(p, 9)

                    def lost():
                        p.ld(12, LOST)
                        p.iconst(13, 1)
                        p.iop(12, 12, "+", 13)
                        p.st(LOST, 12)
                    p.ifz(3, "NE", take, lost)
                p.iconst(12, P_SOUND | P_USED)
                p.if_(1, "EQ", 12, lambda: p.ifz(2, "EQ", wants), kind="i")
                p.iconst(12, 1)
                p.iop(10, 12, "+", 10)
            p.loop_r(15, PLACES - 1, place)
        p.ifz(12, "NE", chord)
        p.iconst(12, 1)
        p.iop(9, 12, "+", 9)
    p.loop_r(14, 16, slot)
    _ = kinds


def _watch(p: Prog) -> None:
    """each slot whose own note fades (or is out) while its chord plays LEADS (its fade runs in its halves); WATCH =
    the slots with a chord, a role or a fade (the next block's pass looks at those and the note-ons). Clobbers R0,
    R1, R6, R8, R9, R12, R13, R15, I0, I1."""
    p.iconst(9, 0)
    p.iconst(8, 1)
    p.iconst(15, 0)

    def one():
        _at(p, 0, ROLE, 9)
        p.ldi(0, 0, 0)
        p.lsh(1, 0, -FADE_SHIFT)
        p.iconst(12, 7)
        p.iop(1, 1, "AND", 12)
        p.ifz(1, "NE", lambda: _leader(p, 9))
        _at(p, 1, CSEQ, 9)
        p.ldi(6, 0, 1)
        p.iop(0, 0, "OR", 6)
        p.ifz(0, "NE", lambda: p.iop(15, 15, "OR", 8))
        p.iconst(12, 1)
        p.iop(9, 12, "+", 9)
        p.iop(8, 8, "+", 8)
    p.loop_r(14, 16, one)
    p.st(WATCH, 15)


def prepass(p: Prog, trig_word: int, kinds: tuple[int, ...], order_at: int | None = None,
            keys_at: int | None = None, rests: tuple[int, int] | None = None) -> None:
    """the chords, the shadows and the ROLE words for this block (see the module), after mnm_ages. RESTS: the slots'
    rest counts and the resting count (a resting leader's shadows that no longer play are freed at once). ORDER_AT, KEYS_AT:
    (the slot chords' until 2026-11-16, unused). Clobbers R0..R15, I0..I2."""
    _first(p)

    def look():
        _chords(p, trig_word, kinds)
        p.ld(0, FREE)
        p.iconst(12, (1 << POOL_N) - 1)
        p.if_(0, "NE", 12, lambda: _loop_pool(p, lambda: _shadow_kept_one(p, rests)), kind="i")   # (a block in use)
        _new_shadows(p, kinds)
        _watch(p)
    # nothing watched, no note-on, the pool free: nothing to do (a kit with no PARA chord pays this test alone)
    p.ld(0, trig_word)
    p.lsh(0, 0, -16)
    p.ld(1, WATCH)
    p.iop(0, 0, "OR", 1)
    p.ld(1, FREE)
    p.iconst(12, (1 << POOL_N) - 1)
    p.if_(1, "NE", 12, lambda: p.iconst(0, 1), kind="i")
    p.ifz(0, "NE", look)


# -- the voice (PERC's, dnfw.perc.program.voice) -------------------------------------------------------------------

SH_GO = SH_BIT + 4                               # (the render loop's words, after the pass's)
SH_NOTE = SH_GO + 4
WATCH = SH_NOTE + 4                              # the slots the next block's pass looks at (a chord, a shadow, a fade)
WORDS += 3


def role(p: Prog, d: int, t_word: int) -> None:
    """Rd = this slot's ROLE word (the slot in the word T_WORD). Clobbers R12, R13, I1."""
    p.ld(13, t_word)
    p.lsh(13, 13, 2)
    p.iconst(12, ROLE)
    p.iop(13, 12, "+", 13)
    p.seti(1, 13)
    p.ldi(d, 0, 1)


def is_member(p: Prog, d: int, t_word: int) -> None:
    """Rd = 1 while a shadow renders (its output is not used: not resampled), else 0. Clobbers R12."""
    p.ld(d, RROLE)
    p.iconst(12, MEMBER)
    p.if_(d, "EQ", 12, lambda: p.iconst(d, 1), lambda: p.iconst(d, 0), kind="i")
    _ = t_word


def silent_role(p: Prog, d: int, t_word: int) -> None:
    """Rd nonzero when this slot wrote silence for a chord (a slot chord's member or dropped slot until 2026-11-16;
    none since: 0, the ROLE's low bit). Clobbers R12, R13, I1."""
    role(p, d, t_word)
    p.lsh(d, d, 31 - ROLE_SHIFT)
    p.lsh(d, d, -31)


assert MEMBER & 1 and DROPPED & 1 and not LEADER & 1


def quiet_as_leader(p: Prog, scratch: int, rests_off: int) -> None:
    """(the slot chords' member's quiet test until 2026-11-16: no slot is a member since, so R0 is left as it is)"""
    _ = (scratch, rests_off)


def reserve(p: Prog, t_word: int, cost: int, floor: int) -> None:
    """(the frame guard's RESERVE for a slot chord's member until 2026-11-16: none since; R8 as it is)"""
    _ = (t_word, cost, floor)


def _go_from(p: Prog, counter: int, body) -> None:
    """do body() while --counter (the scratch word COUNTER, set by the caller, at least 1; the body may use every
    register), as Prog.loop without its start"""
    top = p.label("pvloop")
    p.place(top)
    if p.run:
        while True:
            body()
            p.ld(0, counter)
            p.dec(0, 0)
            p.st(counter, 0)
            if p.r[0] == 0:
                break
        return
    body()
    p.ld(0, counter)
    p.dec(0, 0)
    p.st(counter, 0)
    p.jump("NE", top)


def renders(p: Prog, L, i3_bias: int, render) -> None:
    """the slot's renders: a LEADER's shadows first (each owned block not faded out, rendered as a member: the
    leader's knobs and type, its pitch plus the place's offset, its stream position; NEW its note), then the slot's
    own. RENDER(p) is the one MDV.block call (its note in R2, its machine in R5): emitted once. L: PERC's layout
    (its C, its md). Leaves I3 and C['mdb'] the slot's. Clobbers everything but I3."""
    from ...mnm import core as MNC
    C = L.C
    role(p, 6, C["t"])
    p.lsh(6, 6, -ROLE_SHIFT)
    p.iconst(12, 3)
    p.iop(6, 6, "AND", 12)
    p.iconst(0, 1)
    p.iconst(1, POOL_N)

    def leads():
        MNC.vw(p, 0, "pitch")
        p.st(SH_PITCH, 0)
        MDK.vw(p, 0, "pos")
        p.st(SH_POS, 0)
        p.iconst(0, POOL_N + 1)
        p.iconst(1, 0)
    p.iconst(12, LEADER)
    p.if_(6, "EQ", 12, leads, kind="i")
    p.st(SH_N, 0)
    p.st(SH_BIT, 1)

    def each():
        p.ld(15, SH_BIT)
        p.iconst(0, 0)
        p.st(SH_GO, 0)

        def own():
            p.ld(9, C["t"])
            p.lsh(12, 9, 10)
            p.iconst(11, L.md.state)
            p.iop(12, 11, "+", 12)
            p.st(L.md.C["mdb"], 12)
            p.iconst(11, 4 * i3_bias)
            p.iop(12, 11, "+", 12)
            p.seti(3, 12, "this slot's Machinedrum words + I3_BIAS", bias=i3_bias)
            role(p, 6, C["t"])
            p.lsh(6, 6, -ROLE_SHIFT)
            p.iconst(12, 3)
            p.iop(6, 6, "AND", 12)
            p.st(RROLE, 6)
            p.ld(0, C["trig"])
            p.st(SH_NOTE, 0)
            p.iconst(0, 1)
            p.st(SH_GO, 0)

        def shadow():
            _block(p, 14, 15)
            p.iconst(12, 4 * META)
            p.iop(13, 14, "+", 12)
            p.seti(0, 13)
            p.ldi(11, 0, 0)
            p.ld(9, C["t"])

            def mine():
                _field(p, 10, 11, M_SLOT, 4)
                _field(p, 4, 11, M_FADE, 3)

                def go():
                    p.st(L.md.C["mdb"], 14)
                    p.iconst(12, 4 * i3_bias)
                    p.iop(12, 14, "+", 12)
                    p.seti(3, 12, "a shadow's words + I3_BIAS", bias=i3_bias)
                    p.ld(0, SH_POS)
                    MDK.vws(p, "pos", 0)
                    _field(p, 1, 11, M_OFF, 8)
                    p.iconst(12, 128)
                    p.if_(1, "GE", 12, lambda: (p.iconst(12, -256), p.iop(1, 12, "+", 1)), kind="i")
                    p.iconst(12, 0)
                    p.float_(1, 1, 12)
                    p.ld(0, SH_PITCH)
                    p.fop(0, 0, "+", 1)
                    MNC.vws(p, "pitch", 0)
                    p.iconst(12, M_NEW)
                    p.iop(0, 11, "AND", 12)
                    p.iop(11, 11, "-", 0)        # NEW once
                    p.sti(0, 0, 11)
                    p.st(SH_NOTE, 0)
                    p.iconst(0, MEMBER)
                    p.st(RROLE, 0)
                    p.iconst(0, 1)
                    p.st(SH_GO, 0)
                p.if_(10, "EQ", 9, lambda: (p.iconst(12, FADE_OUT), p.if_(4, "NE", 12, go, kind="i")), kind="i")
            p.ifz(11, "LT", mine)                # (in use: the sign bit)
        p.iconst(12, POOL_N)
        p.if_(15, "EQ", 12, own, shadow, kind="i")
        p.ld(0, SH_GO)

        def run():
            p.ld(2, SH_NOTE)
            p.ld(5, C["type"])
            render(p)
        p.ifz(0, "NE", run)
        p.ld(15, SH_BIT)
        p.iconst(12, 1)
        p.iop(15, 12, "+", 15)
        p.st(SH_BIT, 15)
    _go_from(p, SH_N, each)


# -- the engine (dnfw.engines.analog2.analog2.half, juno.half) -----------------------------------------------------

def _ramp(p: Prog, fade: int, add: bool) -> None:
    """the 16 samples from I0 times a gain falling linearly from FADE / FADE_HALVES to (FADE - 1) / FADE_HALVES (FADE in
    Rfade, 1..FADE_HALVES), added to them from I1 (ADD; the member's) or in place. Clobbers F0..F2, R12, R15, I0, I1."""
    p.iconst(12, 0)
    p.float_(2, fade, 12)
    p.fconst(1, 1.0 / FADE_HALVES)
    p.fop(2, 2, "*", 1)                          # the gain at the half's start

    def one():
        p.fconst(1, 1.0 / (16 * FADE_HALVES))
        p.fop(2, 2, "-", 1)
        if add:
            p.ldi(0, 0, 0)
            p.ldpost(1, 1)
            p.fop(1, 1, "*", 2)
            p.fop(0, 0, "+", 1)
            p.stpost(0, 0)
        else:
            p.ldi(1, 0, 0)
            p.fop(1, 1, "*", 2)
            p.stpost(0, 1)
    p.loop_r(15, 16, one)


def _fade_on(p: Prog, word: int, at: int) -> None:
    """the ROLE word in Rword (FADE 1..FADE_HALVES) one half on (FADE_OUT after its last), stored at the address in
    Rat (R12 or R13 allowed: I1 is set first). Clobbers R12, R13, I1."""
    p.seti(1, at)
    p.lsh(12, word, -FADE_SHIFT)
    p.iconst(13, 7)
    p.iop(12, 12, "AND", 13)
    p.iconst(13, -1)
    p.iop(12, 13, "+", 12)
    p.ifz(12, "EQ", lambda: p.iconst(12, FADE_OUT))
    p.lsh(12, 12, FADE_SHIFT)
    p.iconst(13, ~FADE_MASK & 0xFFFFFFFF)
    p.iop(word, word, "AND", 13)
    p.iop(word, word, "OR", 12)
    p.sti(0, 1, word)


def _own_fade(p: Prog, L, bv_word: int) -> None:
    """2026-11-15 ("Drop the oldest"): a LEADER whose own note is fading or out (its FADE): this half's own part at b
    faded (_ramp) or zeroed, before its members are added. Clobbers F0..F2, R11..R15, I0, I1."""
    p.ld(14, L.perc.C["t"])
    p.lsh(14, 14, 2)
    p.iconst(12, ROLE)
    p.iop(14, 12, "+", 14)                       # ROLE[t]'s address
    p.seti(1, 14)
    p.ldi(11, 0, 1)
    p.lsh(13, 11, -FADE_SHIFT)
    p.iconst(12, 7)
    p.iop(13, 13, "AND", 12)                     # its FADE

    def faded():
        p.ld(12, bv_word)
        p.seti(0, 12)

        def out():
            p.fconst(0, 0.0)
            p.loop_r(15, 16, lambda: p.stpost(0, 0))

        def fading():
            _ramp(p, 13, add=False)
            _fade_on(p, 11, 14)
        p.iconst(12, FADE_OUT)
        p.if_(13, "EQ", 12, out, fading, kind="i")
    p.ifz(13, "NE", faded)


def add_places(p: Prog, L, bv_word: int) -> None:
    """a LEADER, each half: its own note's fade (_own_fade), then each of its shadows' post-drive half (the same place
    in its stream: the block's words as the leader's are in its own) added to this half's block b (its address in
    the word BV_WORD), a fading one through its fade (_ramp, its META's FADE moved on a half). L: the Monomachine
    layout. Clobbers F0..F2, R4, R8..R15, I0, I1."""
    _own_fade(p, L, bv_word)
    p.ld(10, L.perc.C["t"])
    p.iconst(9, POOL)                            # the block
    p.iconst(8, 0)                               # its offset in the stream: bv - the leader's words
    p.ld(8, bv_word)
    p.ld(12, L.md.C["mdb"])
    p.iop(8, 8, "-", 12)

    def one():
        p.iconst(12, 4 * META)
        p.iop(13, 9, "+", 12)
        p.seti(1, 13)
        p.ldi(11, 0, 1)

        def used():
            _field(p, 14, 11, M_SLOT, 4)

            def mine():
                _field(p, 13, 11, M_FADE, 3)

                def add():
                    p.ld(12, bv_word)
                    p.seti(0, 12)
                    p.iop(12, 9, "+", 8)
                    p.seti(1, 12)

                    def plain():
                        def s1():
                            p.ldi(1, 0, 0)
                            p.ldpost(2, 1)
                            p.fop(1, 1, "+", 2)
                            p.stpost(0, 1)
                        p.loop_r(15, 16, s1)

                    def fading():
                        _ramp(p, 13, add=True)
                        p.iconst(12, 4 * META)
                        p.iop(14, 9, "+", 12)
                        p.seti(1, 14)
                        p.ldi(11, 0, 1)
                        _field(p, 13, 11, M_FADE, 3)
                        p.iconst(12, -1)
                        p.iop(13, 12, "+", 13)
                        p.ifz(13, "EQ", lambda: p.iconst(13, FADE_OUT))
                        p.lsh(13, 13, M_FADE)
                        p.iconst(12, ~(7 << M_FADE) & 0xFFFFFFFF)
                        p.iop(11, 11, "AND", 12)
                        p.iop(11, 11, "OR", 13)
                        p.sti(0, 1, 11)
                    p.ifz(13, "EQ", plain, fading)
                p.iconst(12, FADE_OUT)
                p.if_(13, "NE", 12, add, kind="i")
            p.if_(14, "EQ", 10, mine, kind="i")
        p.ifz(11, "LT", used)
        p.iconst(12, BLOCK)
        p.iop(9, 12, "+", 9)
    p.loop_r(4, POOL_N, one)


def stage(p: Prog, L, body, bv_word: int | None = None) -> None:
    """an engine's shared stage BODY (its filter and what follows), unless a shadow renders (its per-note half stays in
    its stream for its leader); with BV_WORD a LEADER first adds its shadows' halves (add_places). Any other render:
    BODY, as before. L: the Monomachine layout. Clobbers R0, R1, R12, R13, I1 (and add_places' for a leader)."""
    p.ld(0, RROLE)
    if bv_word is not None:
        p.iconst(12, LEADER)
        p.if_(0, "EQ", 12, lambda: add_places(p, L, bv_word), kind="i")
        p.ld(0, RROLE)
    p.iconst(12, MEMBER)
    p.if_(0, "NE", 12, body, kind="i")


def shadow_render(p: Prog, d: int) -> None:
    """Rd nonzero while a shadow renders (an engine leaves out what only the chord's voice does: ANALOG 2's side).
    Clobbers R12."""
    p.ld(d, RROLE)
    p.iconst(12, MEMBER)
    p.if_(d, "EQ", 12, lambda: p.iconst(d, 1), lambda: p.iconst(d, 0), kind="i")
