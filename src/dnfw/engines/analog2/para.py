# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG 2's paraphonic mode, PARA (2026-11-15, the User: "Yes, start now"; drive "Per note, before the sum";
level "Louder with more notes"): design A of docs/paraphonic-study.md, slot groups on the DSP (docs/paraphonic.md).

A note still takes a voice slot of its own (the allocator, glide, velocity and steal are stock's). On a track whose
PARA (page 3, stock record MOD: 0 OFF, 1..3 = 2..4 pitches) is on, a CHORD of the track's ANALOG 2 slots plays on its
LEADER, the slot whose note started it: its MEMBERS run their oscillators, noise and drive into their own 44.1 kHz
stream (their filter, knee and side skipped) and write silence to their voice buffer; the leader adds their
post-drive halves to its own, at full level, one member at a time in slot order, before its filter and knee, and
after its block gives the members its stream position, so they move their streams in the same blocks. The first N
of a chord play (N the PARA value + 1: the leader and the members that joined first); the rest are DROPPED: silent,
not rendered.

The chords (CUR, MEM): a note on a PARA track's ANALOG 2 slot joins its track's current chord while one of that
chord's slots is held, else starts a new one (it leads; one block's notes start it on the highest slot, the one the
slot loop runs last of them). A note on any slot first takes it out of every chord; a chord whose leader's slot is
taken goes on under its oldest member (the largest key). A chord keeps its slots through their release (its tail is
the leader's AMP envelope over every member) while a new chord starts on the track. HELD is the DSP's own record of
the held slots: set by the frame's note-on bit (offset 34), cleared by its note-off bit (offset 36: an event, the
block a gate ends; docs/mute-research.md). The ColdFire keeps a chord's note-offs back until its last note ends
(csrc/hold/hold.c para_final), so the chord's envelope is one, legato.

Each block, after `mnm_ages` (`prepass`): HELD, the chords, then each slot's ROLE word: bits 0..15 the members (a
leader's), 16..19 the leader (a member's; a leader's places left while the pass runs), 24..25 the role (MEMBER 1,
LEADER 2, DROPPED 3; 0 plays as always), bit 20 RENDERED (a member's own: its half ran this block; a member the frame
guard refused or that rests is left out of its leader's sum, never its stale words). A slot alone in its chord has no
role: its render is today's, bit for bit. Under load the guard lets a member in only with its leader's room after it
(`reserve`), so a chord loses members, newest first, before its leader.

Memory: AREA (L1 F1 0x2E0E44..0x2E0F08), WORDS words, zeros in the upload, so after every DSP load: HELD, CUR[16 tracks] (the current chord's leader + 1, 0 none), MEM[16
slots] (the members of the chord the slot leads), ROLE[16 slots].
"""

from __future__ import annotations

from ...md import core as MDK
from ...perc import machines as PM
from ...perc.dsl import Prog

AREA = 0x2E0E44                                  # dnfw.waverider.dsp.PARA_DM: L1 F1 (main, the arbiter, 2026-11-15)
ROUTE = 0x257898                                 # dnfw.md.voice.ROUTE (not imported: md.voice imports the engines)
HELD = AREA                                      # the held slots (a bit a slot)
CUR = AREA + 4                                   # [16 tracks]: the track's current chord's leader + 1 (0: none)
MEM = CUR + 64                                   # [16 slots]: the members of the chord the slot leads (0: none)
ROLE = MEM + 64                                  # [16 slots]: the slot's role this block
WORDS = 1 + 16 + 16 + 16
MEMBER, LEADER, DROPPED = 1, 2, 3
ROLE_SHIFT, LEAD_SHIFT = 24, 16                  # a member's leader at bits 16..19; a leader's places left there
RENDERED = 1 << 20                               # a member's own word: its half rendered this block (the guard let it)
PARA_REC = PM.P3_RECS[5]                         # MOD (id 248, slot 37, 0..0x300, default 0): PARA OFF 2 3 4
# the engines PARA plays (2026-11-15, the User: ANALOG 2 first, then JUNO, then the DPRO machines; not SOPHIE, not
# SID 6581): an
# engine joins by its name here and one call of `stage` in its half, round its shared stage (the filter and what
# follows), after its per-note part (oscillators, noise, drive). Its post-per-note half must be at the half's block
# (the word BV_WORD) in its 44.1 kHz stream, as ANALOG 2's and JUNO's are
ENGINES = ("ANALOG2",)
NOTE_ON, NOTE_OFF = 34, 36                       # the frame's note-on and note-off masks (one bit a slot)
assert (PM.FRAME + NOTE_OFF) % 4 == 0 and (PM.FRAME + NOTE_ON) % 4 == 2       # 36 a word's low half, 34 a high


def _route(p: Prog, d: int, u: int) -> None:
    """Rd = the track slot Ru plays (ROUTE: a 16-bit word a slot, even low, odd high). Ru in R8..R15, not R12, R13.
    Clobbers R12, R13, I1."""
    p.lsh(13, u, -1)
    p.lsh(13, 13, 2)
    p.iconst(12, ROUTE)
    p.iop(13, 12, "+", 13)
    p.seti(1, 13)
    p.ldi(d, 0, 1)
    p.iconst(12, 1)
    p.iop(13, u, "AND", 12)
    p.ifz(13, "NE", lambda: p.lsh(d, d, -16))
    p.iconst(12, 0xFFFF)
    p.iop(d, d, "AND", 12)


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
    """Rd = the chord's pitches on slot Ru (PARA 1..3 -> 2..4); 0 when PARA is off or the slot's machine is not one
    of KINDS (the frame's types). Ru in R8, R9, R14 or R15. Clobbers R10..R13, I1."""
    p.iop(11, u, "+", u)                         # 2 u
    _frame_half(p, d, 148, 11)                   # the slot's machine type

    def para():
        p.lsh(11, u, 7)                          # 146 u: the slot's records
        p.lsh(12, u, 4)
        p.iop(11, 11, "+", 12)
        p.lsh(12, u, 1)
        p.iop(11, 11, "+", 12)
        _frame_half(p, d, PM.frame_offset(PARA_REC[1]), 11)
        p.lsh(d, d, -8)                          # 0..3 (the record's 0..0x300)
        p.iconst(12, 3)
        p.iop(d, d, "MIN", 12)
        p.ifz(d, "NE", lambda: (p.iconst(12, 1), p.iop(d, 12, "+", d)))
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


def _held(p: Prog, trig_word: int) -> None:
    """HELD = (HELD | the note-ons) & ~the note-offs; R3 the note-ons, R5 HELD after. Clobbers R4, R6, R12."""
    p.ld(3, trig_word)
    p.lsh(3, 3, -16)
    p.ld(4, PM.FRAME + NOTE_OFF)
    p.iconst(12, 0xFFFF)
    p.iop(4, 4, "AND", 12)
    p.ld(5, HELD)
    p.iop(5, 5, "OR", 3)
    p.iop(6, 5, "AND", 4)
    p.iop(5, 5, "-", 6)
    p.st(HELD, 5)


def _leave(p: Prog, keys_at: int) -> None:
    """slot R9 (its bit R8) leaves every chord: out of every leader's members; if it led one, that chord's oldest
    member (the largest key, mnm_ages') leads it on (its members, the track's current chord if it was): the one the
    slot loop runs last of them; a lone leader leaves its track's current chord. Keeps R3, R5, R8, R9, R15, I0.
    Clobbers R0..R2, R6, R7, R10..R14, I1, I2."""
    p.iconst(12, MEM)
    p.seti(2, 12)

    def out1():
        p.ldi(6, 0, 2)
        p.iop(7, 6, "AND", 8)
        p.iop(6, 6, "-", 7)
        p.sti(0, 2, 6)
        _step(p, 2)
    p.loop_r(14, 16, out1)
    _at(p, 2, MEM, 9)
    p.ldi(6, 0, 2)                               # the members it led
    p.iconst(7, 0)                               # what its track's current chord becomes: 0 (none)

    def hand_on():
        p.iconst(10, 0)                          # j
        p.iconst(11, 1)                          # its bit
        p.iconst(2, 0)                           # the oldest member
        p.iconst(1, -1)                          # its key
        p.iconst(12, keys_at)
        p.seti(1, 12)

        def find():
            p.iop(0, 6, "AND", 11)
            p.ldi(7, 0, 1)

            def older():
                p.if_(7, "GT", 1, lambda: (p.ipass(1, 7), p.ipass(2, 10)), kind="i")
            p.ifz(0, "NE", older)
            p.iconst(12, 1)
            p.iop(10, 12, "+", 10)
            p.iop(11, 11, "+", 11)
            _step(p, 1)
        p.loop_r(14, 16, find)
        p.iconst(7, 0)
        p.iconst(0, 0)
        p.sti(0, 2, 0)                           # MEM[u] = 0
        p.iconst(11, 1)
        MDK._shift_r(p, 11, 11, 2)
        p.iop(6, 6, "-", 11)                     # the others
        p.ipass(10, 2)
        _at(p, 2, MEM, 10)
        p.sti(0, 2, 6)                           # MEM[the new leader]
        p.iconst(12, 1)
        p.iop(7, 12, "+", 10)                    # its track's chord: the new leader + 1
    p.ifz(6, "NE", hand_on)
    p.iconst(12, 1)
    p.iop(1, 12, "+", 9)                         # u + 1
    p.iconst(12, CUR)
    p.seti(2, 12)

    def cur1():
        p.ldi(6, 0, 2)
        p.if_(6, "EQ", 1, lambda: p.sti(0, 2, 7), kind="i")
        _step(p, 2)
    p.loop_r(14, 16, cur1)


def _join(p: Prog, kinds: tuple[int, ...], keys_at: int) -> None:
    """slot I0 (its bit R8) had a note: it leaves every chord (_leave); on a PARA track's ANALOG 2 it joins its
    track's current chord while one of that chord's slots is held (R5 HELD), else it starts a new one, its leader.
    Keeps R3, R5, R8, R15, I0. Clobbers R0..R2, R4, R6, R7, R9..R14, I1, I2."""
    p.geti(9, 0)
    _leave(p, keys_at)
    _route(p, 4, 9)
    _pitches(p, 6, 9, kinds)

    def para():
        _at(p, 2, CUR, 4)
        p.ldi(7, 0, 2)                           # its track's chord: leader + 1

        def start():
            p.iconst(12, 1)
            p.iop(7, 12, "+", 9)
            p.sti(0, 2, 7)                       # CUR[t] = u + 1 (MEM[u] is 0: _leave)

        def maybe():
            p.iconst(12, -1)
            p.iop(10, 12, "+", 7)                # the leader
            _at(p, 1, MEM, 10)
            p.ldi(6, 0, 1)
            p.iconst(11, 1)
            MDK._shift_r(p, 11, 11, 10)
            p.iop(0, 6, "OR", 11)
            p.iop(0, 0, "AND", 5)                # held, the leader or a member

            def join():
                p.iop(6, 6, "OR", 8)
                p.sti(0, 1, 6)
            p.ifz(0, "NE", join, start)
        p.ifz(7, "EQ", start, maybe)
    p.iconst(12, 16)
    p.if_(4, "LT", 12, lambda: p.ifz(6, "NE", para), kind="i")


def _joins(p: Prog, kinds: tuple[int, ...], keys_at: int) -> None:
    """every slot with a note this block (R3's bits) joins (_join), the highest slot first: notes of one block start
    a chord on the highest, the one the slot loop runs last of them (ORDER: the newest first, a tie the lower slot
    first). Clobbers R0..R15, I0..I2."""
    p.iconst(0, 15)
    p.seti(0, 0)
    p.iconst(8, 1 << 15)

    def slot():
        p.iop(12, 3, "AND", 8)
        p.ifz(12, "NE", lambda: _join(p, kinds, keys_at))
        p.lsh(8, 8, -1)
        p.geti(12, 0)
        p.iconst(13, -1)
        p.iop(12, 12, "+", 13)
        p.seti(0, 12)
    p.loop_r(15, 16, slot)


def _clear_roles(p: Prog) -> None:
    """ROLE[16] = 0; R0 = every leader's members ORed (0: no chord of two). Clobbers R6, R12..R14, I1, I2."""
    p.iconst(12, MEM)
    p.seti(1, 12)
    p.iconst(12, ROLE)
    p.seti(2, 12)
    p.iconst(0, 0)

    def one():
        p.ldi(6, 0, 1)
        p.iop(0, 0, "OR", 6)
        p.iconst(6, 0)
        p.sti(0, 2, 6)
        _step(p, 1)
        _step(p, 2)
    p.loop_r(14, 16, one)


def _lead(p: Prog, kinds: tuple[int, ...]) -> None:
    """slot R9 leads the chord MEM[R9] (R6, not 0): with PARA on (N pitches), ROLE[R9] = LEADER, its places left
    (N - 1) at bits 16..19; each member's ROLE = MEMBER and the leader (placed, or dropped, by _place). Keeps R9,
    R15, I0. Clobbers R0..R2, R4..R8, R10..R14, I1, I2."""
    _pitches(p, 5, 9, kinds)

    def on():
        p.iconst(12, -1)
        p.iop(4, 12, "+", 5)                     # N - 1
        p.lsh(4, 4, LEAD_SHIFT)
        p.iconst(12, LEADER << ROLE_SHIFT)
        p.iop(4, 4, "OR", 12)
        _at(p, 2, ROLE, 9)
        p.sti(0, 2, 4)
        p.lsh(4, 9, LEAD_SHIFT)
        p.iconst(12, MEMBER << ROLE_SHIFT)
        p.iop(4, 4, "OR", 12)                    # a member's word
        p.iconst(12, ROLE)
        p.seti(2, 12)
        p.iconst(8, 1)

        def one():
            p.iop(7, 6, "AND", 8)
            p.ifz(7, "NE", lambda: p.sti(0, 2, 4))
            p.iop(8, 8, "+", 8)
            _step(p, 2)
        p.loop_r(14, 16, one)
    p.ifz(5, "NE", on)


def _leaders(p: Prog, kinds: tuple[int, ...]) -> None:
    """_lead for each slot that leads a chord of two or more. Clobbers R0..R15, I0..I2."""
    p.iconst(9, 0)
    p.iconst(12, MEM)
    p.seti(0, 12)

    def one():
        p.ldi(6, 0, 0)
        p.ifz(6, "NE", lambda: _lead(p, kinds))
        p.iconst(12, 1)
        p.iop(9, 12, "+", 9)
        _step(p, 0)
    p.loop_r(15, 16, one)


def _place(p: Prog, order_at: int) -> None:
    """the members placed oldest first (ORDER from its last place): while its leader has places left, a member
    takes one (its bit into the leader's word), else it is DROPPED. Clobbers R0..R15, I0..I2."""
    p.iconst(12, order_at + 4 * 15)
    p.seti(0, 12)

    def one():
        p.ldi(9, 0, 0)                           # u
        _at(p, 2, ROLE, 9)
        p.ldi(6, 0, 2)
        p.lsh(7, 6, -ROLE_SHIFT)
        p.iconst(12, MEMBER)

        def member():
            p.lsh(10, 6, -LEAD_SHIFT)
            p.iconst(12, 15)
            p.iop(10, 10, "AND", 12)             # its leader
            _at(p, 1, ROLE, 10)
            p.ldi(4, 0, 1)
            p.lsh(5, 4, -LEAD_SHIFT)
            p.iconst(12, 15)
            p.iop(5, 5, "AND", 12)               # places left

            def take():
                p.iconst(11, 1)
                MDK._shift_r(p, 11, 11, 9)
                p.iop(4, 4, "OR", 11)
                p.iconst(12, -(1 << LEAD_SHIFT))
                p.iop(4, 12, "+", 4)
                p.sti(0, 1, 4)

            def drop():
                p.iconst(6, DROPPED << ROLE_SHIFT)
                p.sti(0, 2, 6)
            p.ifz(5, "NE", take, drop)
        p.if_(7, "EQ", 12, member, kind="i")
        p.geti(12, 0)
        p.iconst(13, -4)
        p.iop(12, 12, "+", 13)
        p.seti(0, 12)
    p.loop_r(15, 16, one)


def prepass(p: Prog, trig_word: int, kinds: tuple[int, ...], order_at: int, keys_at: int) -> None:
    """HELD, the chords and the ROLE words for this block (see the module), after mnm_ages (ORDER at ORDER_AT, the
    slots' keys at KEYS_AT). Clobbers R0..R15, I0..I2."""
    _held(p, trig_word)
    p.ifz(3, "NE", lambda: _joins(p, kinds, keys_at))
    _clear_roles(p)

    def roles():
        _leaders(p, kinds)
        _place(p, order_at)
    p.ifz(0, "NE", roles)


# -- the voice (PERC's, dnfw.perc.program.voice) -------------------------------------------------------------------

def role(p: Prog, d: int, t_word: int) -> None:
    """Rd = this slot's ROLE word (the slot in the word T_WORD). Clobbers R12, R13, I1."""
    p.ld(13, t_word)
    p.lsh(13, 13, 2)
    p.iconst(12, ROLE)
    p.iop(13, 12, "+", 13)
    p.seti(1, 13)
    p.ldi(d, 0, 1)


def push_position(p: Prog, md_state: int, r: int) -> None:
    """a LEADER (ROLE in Rr), after its block: each member's stream position = its own (I3 its words), so in the next
    block every member moves its stream with the leader's (a member runs earlier, the slots going newest first). Not
    before a member's block: a leader new this block resets its position in its own turn, after the members'.
    Clobbers R8..R14, I1."""
    p.iconst(12, 0xFFFF)
    p.iop(9, r, "AND", 12)                       # the members

    def go():
        MDK.vw(p, 10, "pos")
        p.iconst(11, md_state + 4 * MDK.VW["pos"])
        p.iconst(8, 1)

        def member():
            p.iop(12, 9, "AND", 8)
            p.ifz(12, "NE", lambda: (p.seti(1, 11), p.sti(0, 1, 10)))
            p.iop(8, 8, "+", 8)
            p.iconst(12, 1 << 10)
            p.iop(11, 12, "+", 11)
        p.loop_r(14, 16, member)
    p.ifz(9, "NE", go)



def quiet_as_leader(p: Prog, scratch: int, rests_off: int) -> None:
    """mnm_ages' quiet test (dnfw.perc.program: QUIET_BLOCKS blocks under QUIET_LEVEL in a slot's buffer, no note,
    and the voice rests): a chord's MEMBER writes silence to its buffer while its sound is in its leader's, so it
    would rest 43 ms into a held chord. A member (last block's ROLE: the PARA pass runs after mnm_ages) takes its
    leader's count instead (R0, last block's): it rests when the chord's sound has died away. I5 the slot's scratch
    word (scratch + 4 u); R0 the slot's new count, replaced for a member. Clobbers R7, R12, R13, I1."""
    p.geti(13, 5)
    p.iconst(12, ROLE - scratch)
    p.iop(13, 12, "+", 13)
    p.seti(1, 13)
    p.ldi(13, 0, 1, "its ROLE word")
    p.lsh(7, 13, -ROLE_SHIFT)
    p.iconst(12, 3)
    p.iop(7, 7, "AND", 12)
    p.iconst(12, MEMBER)

    def leaders():
        p.lsh(7, 13, -LEAD_SHIFT)
        p.iconst(12, 15)
        p.iop(7, 7, "AND", 12)
        p.lsh(7, 7, 2)
        p.iconst(12, scratch + rests_off)
        p.iop(7, 12, "+", 7)
        p.seti(1, 7)
        p.ldi(0, 0, 1, "its leader's count")
    p.if_(7, "EQ", 12, leaders, kind="i")


def reserve(p: Prog, t_word: int, cost: int, floor: int) -> None:
    """the frame guard (dnfw.perc.guard.around's RESERVE), a MEMBER: R8 += what its leader is expected to cost,
    max(1.5 x its last cost (COST: the slots' cost words), FLOOR), so a member is let in only while its leader still
    fits after it. Under load a chord loses its members (newest first: the slots run newest first) and keeps its
    leader, which plays the chord; a leader refused would leave the whole chord silent. Keeps R8, I5. Clobbers
    R9..R13, I1."""
    role(p, 9, t_word)
    p.lsh(10, 9, -ROLE_SHIFT)
    p.iconst(12, 3)
    p.iop(10, 10, "AND", 12)
    p.iconst(12, MEMBER)

    def leader():
        p.lsh(10, 9, -LEAD_SHIFT)
        p.iconst(12, 15)
        p.iop(10, 10, "AND", 12)
        p.lsh(10, 10, 2)
        p.iconst(12, cost)
        p.iop(10, 12, "+", 10)
        p.seti(1, 10)
        p.ldi(9, 0, 1, "its leader's last cost")
        p.lsh(10, 9, -1)
        p.iop(9, 9, "+", 10)
        p.iconst(10, floor)
        p.iop(9, 9, "MAX", 10)
        p.iop(8, 8, "+", 9)
    p.if_(10, "EQ", 12, leader, kind="i")


# -- the engine (dnfw.engines.analog2.analog2.half) -----------------------------------------------------------------

def add_members(p: Prog, L, bv_word: int) -> None:
    """a LEADER: each member's post-drive half (the same place in its stream: its words 1 KB x (m - t) from the
    leader's) added to this half's block b (its address in the word BV_WORD), members in slot order; a slot with no
    members leaves b as it is. L: the Monomachine layout. Clobbers F0..F2, R4, R8..R15, I0, I1."""
    role(p, 9, L.perc.C["t"])
    p.iconst(12, 0xFFFF)
    p.iop(9, 9, "AND", 12)                       # the members

    def go():
        p.ld(10, L.perc.C["t"])
        p.lsh(10, 10, 10)                        # 1 KB t
        p.iconst(14, 0)                          # 1 KB m
        p.iconst(8, 1)                           # m's bit

        def member():
            p.iop(12, 9, "AND", 8)

            def add():
                p.ld(13, bv_word)
                p.seti(0, 13)
                p.iop(11, 13, "+", 14)
                p.iop(11, 11, "-", 10)
                p.seti(1, 11)

                def one():
                    p.ldi(1, 0, 0)
                    p.ldpost(2, 1)
                    p.fop(1, 1, "+", 2)
                    p.stpost(0, 1)
                p.loop_r(15, 16, one)

            def rendered():                      # the member ran this block (a refused or resting one did not: its
                p.lsh(11, 14, -8)                # words hold an earlier pass of its stream, never added)
                p.iconst(13, ROLE)
                p.iop(11, 13, "+", 11)
                p.seti(1, 11)
                p.ldi(11, 0, 1)
                p.iconst(13, RENDERED)
                p.iop(11, 11, "AND", 13)
                p.ifz(11, "NE", add)
            p.ifz(12, "NE", rendered)
            p.iop(8, 8, "+", 8)
            p.iconst(12, 1 << 10)
            p.iop(14, 12, "+", 14)
        p.loop_r(4, 16, member)
    p.ifz(9, "NE", go)


def stage(p: Prog, L, body, bv_word: int | None = None) -> None:
    """an engine's shared stage BODY (its filter and what follows), unless this slot is a chord's MEMBER or DROPPED
    (its per-note half stays in its stream for the leader); with BV_WORD a LEADER first adds its members' halves
    (add_members). Any other slot: BODY, as before. L: the Monomachine layout. Clobbers R0, R1, R12, R13, I1 (and
    add_members' for a leader)."""
    role(p, 0, L.perc.C["t"])
    p.lsh(0, 0, -ROLE_SHIFT)
    if bv_word is not None:
        p.iconst(12, LEADER)
        p.if_(0, "EQ", 12, lambda: add_members(p, L, bv_word), kind="i")
        role(p, 0, L.perc.C["t"])
        p.lsh(0, 0, -ROLE_SHIFT)
    p.iconst(1, 0)
    p.iconst(12, MEMBER)

    def member():                                # its half is in its stream: the leader may add it (I1: its word)
        p.ldi(13, 0, 1)
        p.iconst(12, RENDERED)
        p.iop(13, 13, "OR", 12)
        p.sti(0, 1, 13)
        p.iconst(1, 1)
    p.if_(0, "EQ", 12, member, kind="i")
    p.iconst(12, DROPPED)
    p.if_(0, "EQ", 12, lambda: p.iconst(1, 1), kind="i")
    p.ifz(1, "EQ", body)
