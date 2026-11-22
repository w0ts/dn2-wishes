"""DRONE HOLD's latched voice on stock 1.12's own voice allocator, in the emulator (csrc/hold/hold.c; the User,
2026-11-19, v0.62.4: "playing voices killed the DRONE HOLD voice ... cannot happen", "it happened on a very sparse
project", "one kick kills the drone held voice").

    # inside the bench (bench_ns112.sh), as scripts/emu_para_onevoice.py:
    python scripts/emu_drone_hold.py [--snapshot S] [--json OUT]

The rule: a voice held by DRONE HOLD is never taken or silenced by another note: not by stock's allocator (a free slot
or a steal), not by the VOICE BUDGET. Only its own rules end it (hold.c): the same key again, another key on its own
track, HOLD turned off (or the track no longer DRONE).

The killing path (read on the unit 2026-11-19 and in stock's allocator, 0x4002aa6e..0x4002aaa6): HOLD keeps the DSP's
voice gated by taking the voice's bit out of the frame's note-off words, but stock's own voice state is released at
the key-up like any other note. To stock the latched slot is FREE, and a note-on takes the free slot of its candidates
with the OLDEST release stamp (+12 of the voice record): once the other free slots were used after the drone's key-up
(a sparse project's kick walking the slots, the unit: T9's note 60 on slots 1..15), the next note on any track takes
the drone's slot; hold_len_of sees a track without HOLD and drops the latch: the drone's slot plays the kick.

The ISR's calls entered as it enters them (emu_para_onevoice's Rig): the note-on's allocator call through
load_alloc_hook (pv_pre, the budget, stock, pv_post), then hold_len for each slot given (the ISR's 0x40026afc hook,
with the slot's KEY written first, as 0x40026a44 does); the key-up through pv_rel_hook; the frame's note-off words
through hold_final. A model of the DSP: each slot's note-on as the frame sends it (not a dropped one), each note-off
that goes out. "The drone sounds" = its slot's last note-on is the drone's and no note-off went out for it since.

 1  one kick (the User's case): the drone latched on slot X and its key up, the other slots used since (another
    track's notes, released), ONE note on the kick's track: it takes another slot, the drone sounds; stock's
    allocator alone takes X (the killing path, shown on the same state)
 2  sixteen kicks after the drone's key-up, each released: none takes X, every one gets a slot, the drone sounds
 3  the pool full: the 15 other slots held by other tracks' keys, one more note on another track: it steals one of
    them (stock's CYCLE: the oldest), never X; the drone sounds
 4  nothing but latched drones among a note's candidates (two slots reserved by a track, the 14 others latched by 14
    DRONE tracks): another track's note gets no slot (the ISR's no-slot path, as a muted track's note), nothing
    else changes, every drone sounds
 5  the drone's own track: another key plays (the old latch's note-off goes out, the new note latched), the same key
    again lets it go and starts nothing: the allocator's state as stock's alone leaves it, byte for byte
 6  HOLD turned off: the latch's note-off goes out at the next frame, and the next kick may take X again (the hook =
    stock, byte for byte)
 7  the negative control: no latch anywhere (the drone track's HOLD OFF): a kick through the hook = stock's allocator
    alone, byte for byte (the same slot, the same memory)
 8  the VOICE BUDGET: the latched slot still sounding (the DSP's cost over LOAD_TAIL), little room: the budget's steal
    takes another track's voice, never X; with the drone's key still down, a heavy note's further releases never
    release X (stock keeps it held)
 9  the interrupt's stack: the hook path with a latch within 256 bytes of stock's allocator alone

v0.64.1 merge (2026-11-20): upstream v0.64's HOLD (PTN + KEYBOARD) is stock's own sustain on every track. A note let go
under sustain keeps its slot HELD in stock's state (its note-off kept in the track's list, 0x445ff6f0 + 8 t, never
reaching the ISR), so stock's allocator takes it once the pool is full (CYCLE: the oldest held) and the VOICE BUDGET
may steal or release it. hold.c counts such slots as latches (one mechanism with DRONE HOLD's). Here the sustain is
stock's state as the UI leaves it: the track's flag (0x445ff6e0 + t) set, its list not empty, its key never up at the
ISR.
10  the pool full (the sustained pad's slot the oldest held, 15 keys held on other tracks): one more note on another
    track steals a held key's slot, never the sustained one; stock's allocator alone takes the sustained slot (the
    killing path, on the same state)
11  every candidate sustained by other tracks (T16 owns 2 slots, 14 tracks each a sustained note): another track's
    note gets no slot; the sustained track's own next note takes one of its own (as stock's)
12  the VOICE BUDGET (no room): its steal takes another track's held voice, never the sustained one; a heavy note's
    further releases never release it
13  sustain off (the flag clear), or on with nothing kept: the hook = stock's allocator alone, byte for byte
14  sustain and DRONE HOLD together: both latches kept from a third track's notes
Exit 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import emu_load_budget as LB  # noqa: E402
import emu_para_onevoice as PV  # noqa: E402

OK: list[bool] = []
DRONE_TYPE = 52                                  # hold.c DRONE_TYPE (dnfw.mnm.machines)
OTHER_TYPE = 5                                   # MACHINEDRUM: one of ours, not DRONE, not a PARA engine
HOLD_AT = 20 + 2 * 40                            # hold.c SLOT_HOLD: the sound's 16-bit value 40
NOTE16 = 0x8000DDA0                              # each slot's KEY (note << 16), the ISR writes it before hold_len
SPANS = PV.SPANS + [(NOTE16, 64)]
TICK_COPY = 0x4002A414                           # stock's tick copy of the staging masks (load.c TICK_COPY)
DRONE, KICK, PAD = 4, 8, 2                       # the unit's tracks: T5 the drone, T9 the kick (MACHINEDRUM), T3 a pad


def check(name, ok, detail=""):
    OK.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


def bits(m):
    return [v for v in range(16) if m >> v & 1]


class Rig(PV.Rig):
    """PV.Rig with DRONE HOLD: hold_len after each note-on's slots, and a model of what the DSP was sent"""

    def reset(self, reserve=None, drones=(DRONE,), hold=True):
        e, sym = self.e, self.sym
        LB.Kit(e, sym, [8000] * 16, reserve=reserve)
        for t in range(16):
            snd = self.kit + 52 + 1163 * t
            e.write(snd + 0xDE, bytes([DRONE_TYPE if t in drones else OTHER_TYPE]))
            e.write(snd + HOLD_AT, struct.pack(">H", (127 if hold else 0) << 8))
            e.write(snd + PV.ARP_AT, bytes([0]))
            e.write(snd + PV.MOD_AT, struct.pack(">H", 0))
        e.write(sym["pv_ch"], bytes(16 * PV.CHORD))
        e.write(sym["pv_cur"], bytes(16))
        for n in ("pv_kept", "pv_hidden", "pv_taken", "para_live", "para_kept", "hold_seq", "hold_rel", "hold_count",
                  "hold_drops"):
            e.w32(sym[n], 0)
        for n in ("hold_lock", "hold_nosl"):               # (the fix's counters: absent before it)
            if n in sym:
                e.w32(sym[n], 0)
        if "dt_sw" in sym:
            e.w32(sym["dt_sw"], 1)                         # the test channel's switch HOLD on (its default)
        e.write(PV.KEYS, bytes(64))
        e.write(PV.PER_NOTE, bytes([1] * 16))
        e.write(LB.STAGING + 0x94, bytes([1] * 16))
        e.w32(PV.STOP_ALL, 0)
        self.live = self.live_len()
        self.dsp = [None] * 16                             # each slot's note as the DSP was last sent it: (track, note)

    def hold(self, t, on):
        self.e.write(self.kit + 52 + 1163 * t + HOLD_AT, struct.pack(">H", (127 if on else 0) << 8))

    def play(self, t, n, hook=True):
        """a live note-on: the allocator call, then hold_len for each slot given -> (slots, slots whose note-on goes
        out). Each event in a later tick (the stamps' clock: stock's 0x4059db04, +16 an event)"""
        self.tick()
        return self.play_now(t, n, hook)

    def tick(self):
        self.e.w32(LB.TICK, self.e.r32(LB.TICK) + 16)

    def play_now(self, t, n, hook=True):
        """play() in the current tick"""
        got, _ = self.on(t, n, hook=hook)
        sent = 0
        for v in bits(got):
            self.e.w32(NOTE16 + 4 * v, n << 16)
            r, _ = self.e.call(self.sym["hold_len"], v, t, 0)
            if r & 0x8000_0000 == 0:                       # (-1: the same key again, the note-on dropped)
                sent |= 1 << v
                self.dsp[v] = (t, n)
        return got, sent

    def frame_out(self, off36=0):
        """a frame with these note-offs composed: -> the +36 that goes out (each of its slots' notes ended)"""
        o, _ = self.frame(off36, off36)
        for v in bits(o):
            self.dsp[v] = None
        return o

    def key_up(self, t, n):
        self.e.w32(LB.TICK, self.e.r32(LB.TICK) + 16)
        rel, _ = self.off(t, n)
        return rel, self.frame_out(rel)

    def tap(self, t, n):
        """a short note: on, then its key-up"""
        got, _ = self.play(t, n)
        self.key_up(t, n)
        return got

    def latched(self):
        return self.e.r32(self.sym["hold_seq"])

    def drone_sounds(self, x, t=DRONE, n=60):
        return self.dsp[x] == (t, n) and (self.latched() >> x & 1) == 1


def drone_up(r: Rig, n=60):
    """the drone's note played and its key up: -> its slot X (latched, still sounding)"""
    got, sent = r.play(DRONE, n)
    x = PV.slot_of(got)
    _, out = r.key_up(DRONE, n)
    return x, got, sent, out


def scenarios(r: Rig, res: dict) -> None:
    e = r.e
    held = lambda: e.r32(LB.HELD)                          # noqa: E731
    # 1: one kick
    r.reset()
    x, got, sent, out = drone_up(r)
    for k in range(15):                                    # the pad's notes since: the other slots used, released
        r.tap(PAD, 40 + k)
    r.tick()
    base = e.save(SPANS)
    pool0 = e.r32(LB.LIVE)
    ref, _ = r.on(KICK, 36, hook=False)                    # stock's allocator alone, on the same state
    e.restore(base)
    kick, ksent = r.play_now(KICK, 36)
    pool1 = e.r32(LB.LIVE)
    res["one_kick"] = {"drone": x, "stock": ref, "hook": kick, "latched": r.latched(), "pool": [pool0, pool1]}
    print(f"  (the drone on slot {x}; stock alone gives the kick {ref:#06x}, the hook {kick:#06x})", flush=True)
    check("1 one kick: the drone latched, its key up (its note-off kept back), the other slots used since: the kick "
          "takes another slot and the drone sounds",
          got and sent == got and not (out >> x & 1) and kick and not (kick >> x & 1) and r.drone_sounds(x)
          and (pool1 >> x & 1) == (pool0 >> x & 1),                       # (hidden for the call only)
          f"drone slot {x}, kick {kick:#06x}, latched {r.latched():#06x}, DSP slot {x}: {r.dsp[x]}")
    check("1 ... the killing path: on the same state stock's allocator alone gives the kick the drone's slot",
          ref == 1 << x, f"stock {ref:#06x}")
    # 2: sixteen kicks
    r.reset()
    x, *_ = drone_up(r)
    given = []
    for k in range(16):
        given.append(r.tap(KICK, 36))
    res["sixteen"] = {"drone": x, "kicks": given}
    check("2 sixteen kicks after the drone's key-up, each released: none takes the drone's slot, each gets one",
          all(g and not (g >> x & 1) for g in given) and r.drone_sounds(x),
          f"drone {x}, kicks {' '.join(f'{g:x}' for g in given)}")
    # 3: the pool full
    r.reset()
    x, *_ = drone_up(r)
    others = [t for t in range(16) if t not in (DRONE, KICK)]
    for k in range(15):                                    # 15 keys held on other tracks (14 tracks, one twice)
        r.play(others[k % len(others)], 50 + k)
    busy = held()
    got, _ = r.play(KICK, 36)
    res["full"] = {"drone": x, "held": busy, "kick": got}
    check("3 the pool full (15 keys held elsewhere): one more note steals a held one, never the drone's",
          bin(busy).count("1") == 15 and not (busy >> x & 1) and got and (got & busy) and not (got >> x & 1)
          and r.drone_sounds(x), f"drone {x}, held {busy:#06x}, the note {got:#06x}")
    # 4: nothing but latched drones among the candidates
    drones = tuple(t for t in range(16) if t not in (14, 15))
    r.reset(reserve={15: 0x0003}, drones=drones)           # T16 owns slots 0, 1; T1..T14 DRONE with HOLD
    xs = {}
    for t in drones:
        g, _ = r.play(t, 60)
        r.key_up(t, 60)
        xs[t] = PV.slot_of(g)
    lat = r.latched()
    r.tick()
    base = e.save(SPANS)
    got, d0 = r.on(14, 36)                                 # T15: no reservation, no latch of its own
    after = e.save(SPANS)
    nosl = e.r32(r.sym["hold_nosl"]) if "hold_nosl" in r.sym else None
    e.restore(base)
    e.w32(LB.DUE, 1)                                       # (as Rig.on sets it)
    e.call(TICK_COPY)                                      # what the tick's copy alone leaves (stock's allocator makes
    copied = e.save(SPANS)                                 # it first thing, pv_pre before the hide)
    e.restore(after)
    same = [va for (va, a), (_, b) in zip(copied, after) if a != b]
    res["all_latched"] = {"latched": lat, "slots": xs, "note": got, "nosl": nosl,
                          "changed": [hex(va) for va in same]}
    check("4 every candidate a latched drone (T16 owns 2 slots, 14 drones latched): another track's note gets no "
          "slot, every drone sounds",
          lat == 0xFFFC and got == 0 and d0 == 0 and all(r.drone_sounds(s, t) for t, s in xs.items()),
          f"latched {lat:#06x}, the note {got:#06x}, no-slot count {nosl}")
    check("4 ... the allocator's state as the tick's copy alone leaves it (no slot, no record, no held bit)",
          not same, f"differs at {', '.join(hex(v) for v in same) or 'nothing'}")
    # 5: the drone's own track
    r.reset()
    x, *_ = drone_up(r)
    r.tick()
    base = e.save(SPANS)
    ref, _ = r.on(DRONE, 64, hook=False)
    stock = e.save(SPANS)
    e.restore(base)
    got, sent = r.play_now(DRONE, 64)
    hooked = e.save(SPANS)
    y = PV.slot_of(got)
    o = r.frame_out()
    moved = r.latched() == 1 << y and (y == x or o >> x & 1) and r.dsp[y] == (DRONE, 64)
    alloc_same = [a for a, b in zip(stock, hooked) if a[0] not in (NOTE16,)] == \
                 [b for a, b in zip(stock, hooked) if a[0] not in (NOTE16,)]
    check("5 the drone's own track, another key: it plays, the old latch goes, the new note latched; the allocator "
          "as stock's alone", moved and got == ref and alloc_same,
          f"old {x}, new {y}, latched {r.latched():#06x}, frame +36 {o:#06x}, stock {ref:#06x}")
    got2, sent2 = r.play(DRONE, 64)
    o2 = r.frame_out()
    r.off(DRONE, 64)
    check("5 ... the same key again: no note-on, the latch let go (its note-off goes out)",
          sent2 == 0 and r.latched() == 0 and (o2 >> y & 1) and r.dsp[y] is None,
          f"slots {got2:#06x}, sent {sent2:#06x}, +36 {o2:#06x}")
    # 6: HOLD turned off
    r.reset()
    x, *_ = drone_up(r)
    for k in range(15):
        r.tap(PAD, 40 + k)
    r.hold(DRONE, False)
    o = r.frame_out()
    r.tick()
    base = e.save(SPANS)
    ref, _ = r.on(KICK, 36, hook=False)
    stock = e.save(SPANS)
    e.restore(base)
    got, _ = r.on(KICK, 36)
    hooked = e.save(SPANS)
    check("6 HOLD turned off: the latch's note-off goes out at the next frame; the next kick as stock's alone (the "
          "drone's slot free again)", (o >> x & 1) and r.latched() == 0 and got == ref and ref == 1 << x
          and hooked == stock, f"+36 {o:#06x}, kick {got:#06x}, stock {ref:#06x}")
    # 7: the negative control
    r.reset(hold=False)
    for k in range(4):
        r.tap(DRONE, 60 + k)
        r.tap(PAD, 40 + k)
    r.tick()
    base = e.save(SPANS)
    ref, d0r = r.on(KICK, 36, hook=False)
    stock = e.save(SPANS)
    e.restore(base)
    got, d0 = r.on(KICK, 36)
    hooked = e.save(SPANS)
    check("7 no latch anywhere (HOLD OFF): a kick through the hook = stock's allocator alone, byte for byte",
          (got, d0) == (ref, d0r) and hooked == stock and r.latched() == 0, f"{got:#06x} / {ref:#06x}")
    # 8: the VOICE BUDGET
    r.reset()
    k8 = LB.Kit.__new__(LB.Kit)
    k8.e, k8.sym = e, r.sym
    x, *_ = drone_up(r)
    pad, _ = r.play(PAD, 40)                               # a held voice on another track
    k8.telemetry({x: 20000, PV.slot_of(pad): 20000}, room=0)   # both sounding; no room for anything
    over0 = r.count("load_over")
    got, _ = r.play(KICK, 36)
    res["budget"] = {"drone": x, "pad": pad, "kick": got, "over": r.count("load_over") - over0}
    check("8 the VOICE BUDGET made to steal (no room, the drone's slot a sounding release tail): it takes the pad's "
          "held voice, never the drone's", r.count("load_over") > over0 and got == pad and r.drone_sounds(x),
          f"drone {x}, pad {pad:#06x}, kick {got:#06x}")
    r.reset()
    k8 = LB.Kit.__new__(LB.Kit)
    k8.e, k8.sym = e, r.sym
    dg, _ = r.play(DRONE, 60)                              # the drone's key still down: held and latched
    x = PV.slot_of(dg)
    pads = [r.play(PAD, 40 + k)[0] for k in range(3)]
    k8.telemetry({**{x: 20000}, **{PV.slot_of(p): 20000 for p in pads}}, room=-200000)
    ku0 = r.count("load_keyups")
    got, _ = r.play(KICK, 36)
    o = r.frame_out()
    res["budget_keyups"] = {"drone": x, "pads": pads, "kick": got, "keyups": r.count("load_keyups") - ku0,
                            "held": held()}
    check("8 ... a heavy note's further releases (the drone's key down, the oldest held voice) never release the "
          "drone: stock keeps it held, the drone sounds",
          (held() >> x & 1) and not (got >> x & 1) and not (o >> x & 1) and r.drone_sounds(x),
          f"drone {x}, kick {got:#06x}, keyups {r.count('load_keyups') - ku0}, held {held():#06x}")
    # 9: the stack
    from unicorn import UC_HOOK_CODE
    low = {"sp": LB.STACK}

    def deep(uc, addr, size, data):
        low["sp"] = min(low["sp"], uc.reg_read(LB.SP_REG))
    r.reset()
    drone_up(r)
    hk = e.uc.hook_add(UC_HOOK_CODE, deep)
    r.on(KICK, 36)
    d_hook = LB.STACK - low["sp"]
    low["sp"] = LB.STACK
    r.on(PAD, 40, hook=False)
    d_stock = LB.STACK - low["sp"]
    e.uc.hook_del(hk)
    res["stack"] = {"hook": d_hook, "stock": d_stock}
    check("9 the interrupt's stack: the hook path with a latch within 256 bytes of stock's allocator alone",
          d_hook - d_stock <= 256, f"hook {d_hook} B, stock {d_stock} B")


SUS_ON, SUS_KEPT = 0x445FF6E0, 0x445FF6F0          # stock 1.12's sustain flags and kept lists (hold.c)


def sustain(r: Rig, t, on, kept=True):
    """stock's sustain on track T as the UI leaves it: the flag, and the kept list's head (not followed by hold.c;
    any non-zero head is a note kept)"""
    r.e.write(SUS_ON + t, bytes([1 if on else 0]))
    r.e.w32(SUS_KEPT + 8 * t, 0x44F00000 + 16 * t if on and kept else 0)


def sus_clear(r: Rig):
    r.e.write(SUS_ON, bytes(16))
    r.e.write(SUS_KEPT, bytes(128))


def sus_scenarios(r: Rig, res: dict) -> None:
    e = r.e
    held = lambda: e.r32(LB.HELD)                          # noqa: E731
    others = [t for t in range(16) if t not in (PAD, KICK)]
    # 10: the pool full
    r.reset(drones=())
    sus_clear(r)
    pg, _ = r.play(PAD, 40)                                # the pad's note, then HOLD: its key-up kept by stock
    x = PV.slot_of(pg)
    sustain(r, PAD, True)
    for k in range(15):
        r.play(others[k % len(others)], 50 + k)            # 15 keys held on other tracks, after the pad's note
    busy = held()
    r.tick()
    base = e.save(SPANS)
    ref, _ = r.on(KICK, 36, hook=False)
    e.restore(base)
    seen0 = r.count("hold_sus_seen")
    got, _ = r.play_now(KICK, 36)
    res["sus_full"] = {"pad": x, "held": busy, "stock": ref, "hook": got}
    check("10 HOLD: the pool full (the sustained pad's slot the oldest held, 15 keys held elsewhere): one more note "
          "steals a held key's slot, never the sustained one",
          busy == 0xFFFF and got and not (got >> x & 1) and (held() >> x & 1) and r.count("hold_sus_seen") > seen0,
          f"pad {x}, held {busy:#06x}, the note {got:#06x}")
    check("10 ... the killing path: on the same state stock's allocator alone takes the sustained slot",
          ref == 1 << x, f"stock {ref:#06x}")
    # 11: every candidate sustained by other tracks
    tracks = tuple(t for t in range(16) if t not in (14, 15))
    r.reset(reserve={15: 0x0003}, drones=())
    sus_clear(r)
    xs = {}
    for t in tracks:
        g, _ = r.play(t, 60)
        xs[t] = PV.slot_of(g)
        sustain(r, t, True)
    r.tick()
    base = e.save(SPANS)
    got, d0 = r.on(14, 36)
    e.restore(base)
    own, _ = r.on(tracks[0], 61)
    res["sus_all"] = {"slots": xs, "note": got, "own": own}
    check("11 HOLD: every candidate sustained by other tracks: another track's note gets no slot",
          got == 0 and d0 == 0 and all(held() >> s & 1 for s in xs.values()), f"the note {got:#06x}")
    check("11 ... the sustained track's own next note takes one of its own slots (as stock's)",
          own and own & (1 << xs[tracks[0]]) == own, f"own {own:#06x}, its slot {xs[tracks[0]]}")
    # 12: the VOICE BUDGET
    r.reset(drones=())
    sus_clear(r)
    k8 = LB.Kit.__new__(LB.Kit)
    k8.e, k8.sym = e, r.sym
    pg, _ = r.play(PAD, 40)
    x = PV.slot_of(pg)
    sustain(r, PAD, True)
    other, _ = r.play(3, 45)                               # a held key on another track, after the pad
    k8.telemetry({x: 20000, PV.slot_of(other): 20000}, room=0)
    over0 = r.count("load_over")
    got, _ = r.play(KICK, 36)
    check("12 HOLD: the VOICE BUDGET made to steal (no room): it takes the other held key's voice, never the "
          "sustained one", r.count("load_over") > over0 and got == other and (held() >> x & 1),
          f"pad {x}, other {other:#06x}, kick {got:#06x}")
    r.reset(drones=())
    sus_clear(r)
    k8 = LB.Kit.__new__(LB.Kit)
    k8.e, k8.sym = e, r.sym
    pg, _ = r.play(PAD, 40)
    x = PV.slot_of(pg)
    sustain(r, PAD, True)
    pads = [r.play(3, 45 + k)[0] for k in range(3)]
    k8.telemetry({**{x: 20000}, **{PV.slot_of(p): 20000 for p in pads}}, room=-200000)
    got, _ = r.play(KICK, 36)
    o = r.frame_out()
    check("12 ... a heavy note's further releases never release the sustained voice (the oldest held)",
          (held() >> x & 1) and not (got >> x & 1) and not (o >> x & 1), f"pad {x}, kick {got:#06x}, held {held():#06x}")
    # 13: sustain off, or on with nothing kept: the hook = stock
    for name, on, kept in (("off", False, False), ("on, nothing kept", True, False)):
        r.reset(drones=())
        sus_clear(r)
        pg, _ = r.play(PAD, 40)
        sustain(r, PAD, on, kept)
        for k in range(15):
            r.play(others[k % len(others)], 50 + k)
        r.tick()
        base = e.save(SPANS)
        ref, d0r = r.on(KICK, 36, hook=False)
        stock = e.save(SPANS)
        e.restore(base)
        got, d0 = r.on(KICK, 36)
        hooked = e.save(SPANS)
        check(f"13 HOLD {name}: a note through the hook = stock's allocator alone, byte for byte",
              (got, d0) == (ref, d0r) and hooked == stock, f"{got:#06x} / {ref:#06x}")
    # 14: sustain and DRONE HOLD together
    r.reset()
    sus_clear(r)
    x, *_ = drone_up(r)
    pg, _ = r.play(PAD, 40)
    y = PV.slot_of(pg)
    sustain(r, PAD, True)
    rest = [t for t in range(16) if t not in (DRONE, PAD, KICK)]
    for k in range(14):
        r.play(rest[k % len(rest)], 50 + k)
    got, _ = r.play(KICK, 36)
    check("14 HOLD and DRONE HOLD together (the pool full): a third track's note takes neither latch",
          got and not (got >> x & 1) and not (got >> y & 1) and r.drone_sounds(x) and (held() >> y & 1),
          f"drone {x}, pad {y}, the note {got:#06x}")
    sus_clear(r)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=LB.SNAP)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    e = LB.Emu(a.snapshot)
    sym = LB.install(e)
    LB.bitrev_hooks(e)
    res: dict = {}
    rig = Rig(e, sym)
    scenarios(rig, res)
    sus_scenarios(rig, res)
    res["pass"] = all(OK)
    print(("PASS" if all(OK) else "FAIL") + f": {sum(OK)} of {len(OK)} checks")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, indent=1))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
