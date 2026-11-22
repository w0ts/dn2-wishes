"""The DSP load budget at note-on (csrc/load, docs/load-budget.md) on stock 1.12's own voice allocator, in the emulator.

    # inside the bench (bench_ns112.sh: DT2_SECTIONS, digikit at /mnt/d/01_Code/Z_Personal/digikit-up):
    python scripts/emu_load_budget.py [--snapshot S] [--json OUT]

The sequencer does not play under the emulator, so the note-on is entered as the audio interrupt enters it: our hook
(load_alloc_hook, at the ISR's jsr 0x4002a6a2) called with the nine arguments the ISR pushes, a6 a frame of its locals,
on an allocator state laid out here (the staging masks copied to the live ones at the tick, the voice records, the held
slots, the tick). The build's ColdFire edits and chunks are installed over a stock 1.12 UI snapshot (the platform
loader's copies by hand, as scripts/emu_waverider_menu.py does). Each scenario is run twice from the same state, through
the hook and straight into stock's allocator, and compared:

1. the budget fits: the hook changes nothing (the same slots, the same memory as stock's);
2. a stock-only kit (every track a stock machine's): no check at all, stock's result exactly (the setting's job too);
3. the setting off: stock's result exactly;
4. the budget full: the note steals a held voice (the oldest, by stock's own STEAL), never a free slot, and the free
   slots are back in the live pool afterwards;
5. a heavy voice replacing light ones: one stolen and the next oldest released (load_keyups);
6. a track with reserved voices: the steal stays inside its own slots;
7. a chord in one tick: the second note never takes the first's slot;
8. the interrupt's stack: the deepest our code goes below the hook's entry (load_sp_min);
2026-11-13 (the unit, r14b: 16 short JUNO notes with a long release piled up to 12 sounding voices; the budget never
stole, as every voice was released, and judged by a fixed LOAD_AVAIL the unit's stock had long eaten into):
9. released voices still sounding (the DSP's per-slot cost over LOAD_TAIL), little room reported by the DSP: the note
   steals a release tail, never a free slot; stock alone takes a free slot;
10. the same tails with plenty of room reported: stock's result exactly;
11. no room reported (no packet yet): LOAD_AVAIL decides, as before: the same light tails fit, stock's result;
12. a voice's measured cost over its table cost: the measure decides (the note that fits by the table steals).
2026-11-21 (PARA as one voice, csrc/para/one.c: a chord on one slot, its notes in pv_ch; track 0 PARA, one note held):
13. the chord's slot is priced by its sounding notes: the track's voice + LOAD_PARA_BASE + load_para_add[N] (1, 4, 8
    notes), PARA OFF the track's voice;
14. the joined notes count at once: a note on another track that fits beside a chord of 1 steals beside a chord of 4;
15. a PARA note that reaches load_pre (no chord of its track held; a join never gets there) starts a chord: one note;
16. a heavy note's further releases never take a PARA track's voice (HOLD keeps a chord's note-off back); PARA OFF
    takes its next oldest;
17. JUNO: a chord priced by JUNO's own BASE and ADD.
Exit 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

SNAP = "/root/dn2-snapshots/Digitone_II_OS1.11/ui1200M.snap"
ALLOC = 0x4002A6A2
STAGING, LIVE = 0x4059DA34, 0x4059D96C
VOICES, HELD, TICK, DUE = 0x40288304, 0x4059DD1C, 0x4059DB04, 0x4059DAFC
KIT_PTR = 0x800052A0
KEY_UP = 0x4002B06E                           # stock's one-slot note-off
STACK, SCRATCH = 0x44700000, 0x44710000
from unicorn.m68k_const import UC_M68K_REG_A7 as SP_REG  # noqa: E402  (digikit's unicorn: the check's stack)
OK = []
NAMES = ['load_voice', 'load_stock', 'load_fx', 'load_off', 'load_checks', 'load_over', 'load_keyups', 'load_sp_min', 'load_last_sum', 'load_last_need']   # csrc/load/load.c's state (cpage LOAD_ENTRIES)


def check(name, ok, detail=""):
    OK.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


class Emu:
    def __init__(self, snapshot):
        from emu.longrun import build
        self.m, *_ = build(snapshot, unblock=True, softfloat=True, bitmap=True, dsp=True, weakptr=False,
                           slc=True, deferred_components=("timers",))
        self.uc = self.m.uc
        self.ret = STACK + 0x800

    def write(self, va, data):
        from unicorn import UC_PROT_ALL, UcError
        if hasattr(self.m, "write"):
            try:
                self.m.write(va, bytes(data))
                return
            except Exception:              # (outside the machine's map: unicorn's own pages below)
                pass
        try:
            self.uc.mem_write(va, bytes(data))
        except UcError:
            for page in range(va & ~0xFFFFF, va + len(data) + 0x100000, 0x100000):
                try:
                    self.uc.mem_map(page, 0x100000, UC_PROT_ALL)
                except UcError:
                    pass
            self.uc.mem_write(va, bytes(data))

    def read(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def r32(self, va):
        return struct.unpack(">I", self.read(va, 4))[0]

    def w32(self, va, v):
        self.write(va, struct.pack(">I", v & 0xFFFFFFFF))

    def w16(self, va, v):
        self.write(va, struct.pack(">H", v & 0xFFFF))

    def call(self, fn, *args, a6=0):
        """enter FN as a jsr would, interrupts masked; -> (d0, d1)"""
        from unicorn.m68k_const import (UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                        UC_M68K_REG_SR)
        frame = struct.pack(">I", self.ret) + b"".join(struct.pack(">I", a & 0xFFFFFFFF) for a in args)
        self.write(STACK, frame)
        self.uc.reg_write(UC_M68K_REG_A7, STACK)
        self.uc.reg_write(UC_M68K_REG_A6, a6)
        sr = self.uc.reg_read(UC_M68K_REG_SR)
        self.uc.reg_write(UC_M68K_REG_SR, (sr & ~0x0700) | 0x2700)
        try:
            self.uc.emu_start(fn, self.ret, count=5_000_000)
            return self.uc.reg_read(UC_M68K_REG_D0), self.uc.reg_read(UC_M68K_REG_D1)
        finally:
            self.uc.reg_write(UC_M68K_REG_SR, sr)

    def save(self, spans):
        return [(va, self.read(va, n)) for va, n in spans]

    def restore(self, saved):
        for va, data in saved:
            self.write(va, data)


# stock's allocator reverses bits (BITREV Dn, 0x00c0 + n) before its FF1s: digikit emulates FF1 (and MOVEC) but not
# BITREV, so every one in the allocator (objdump of 1.12 0x4002a400..0x4002b300) is done here, as the core does it
BITREV_SITES = (0x4002A730, 0x4002A962, 0x4002A9C8, 0x4002AA02, 0x4002AA36, 0x4002AA80, 0x4002AC4C, 0x4002ACA0,
                0x4002AD12, 0x4002AD98, 0x4002B00C, 0x4002B028)


def bitrev_hooks(e: Emu) -> None:
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    dregs = [getattr(K, f"UC_M68K_REG_D{k}") for k in range(8)]

    def hook(uc, addr, size, data):
        op = struct.unpack(">H", bytes(uc.mem_read(addr, 2)))[0]
        assert op & 0xFFF8 == 0x00C0, hex(op)
        r = dregs[op & 7]
        v = uc.reg_read(r) & 0xFFFFFFFF
        uc.reg_write(r, int(f"{v:032b}"[::-1], 2))
        uc.reg_write(K.UC_M68K_REG_PC, addr + 2)
    for va in BITREV_SITES:
        e.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)


def install(e: Emu) -> dict:
    """the build's MAIN OS edits and chunks (the platform loader's copies) over the snapshot; -> the C symbols"""
    from dnfw.mods import waverider as W
    stock = open(os.path.join(os.environ["DT2_SECTIONS"], "section_3_MAIN_OS.bin"), "rb").read()
    built = W._main_os(stock)
    n = 0
    i = 0
    while i < len(stock):
        if built[i] != stock[i]:
            j = i
            while j < len(stock) and built[j] != stock[j]:
                j += 1
            e.write(0x40000400 + i, built[i:j])
            n += 1
            i = j
        else:
            i += 1
    for load, code, _what in W._chunks():
        e.write(load, code)
    # 2026-11-16: with lfo4 shipped (pages.lfo4_on), the wishes' memcpy / memset stubs go on into lfo4's
    # (csrc/wishes/hooks.S): its CODE chunks too, or the allocator's tick copy (0x4002a414's memcpy) runs into
    # unmapped code (an exception, the crash printer: every scenario's state was then never built)
    from dnfw.waverider import pages as PG
    if PG.lfo4_on():
        from dnfw.mods import lfo4 as L4
        from dnfw.mods import platform as PL
        for _, data in L4._chunks(bytes.fromhex(L4._spec()["blob"])):
            chunk = PL.area.CodeChunk.unpack(data)
            e.write(chunk.load, chunk.image + bytes(chunk.bss))
    if hasattr(e.m, "flush"):
        e.m.flush()
    print(f"  installed {n} edited runs and {len(W._chunks())} chunks", flush=True)
    return {**W.SPEC["layout"], **W.SPEC["c_text_symbols"]}


SPANS = [(STAGING, 0xC8), (LIVE, 0xC8), (VOICES, 20 * 16), (0x40288444, 1036 * 16), (0x4059DB00, 0x220),
         (0x4059DD0C, 0x14), (0x80005220, 64), (0x80005260, 64), (0x80005348, 4), (0x4059D8A8, 4)]
RESET = 0x4002A4D2                            # the allocator's reset: tables cleared, tick 0


class Kit:
    """an allocator state built by stock itself: reset, the masks, then notes played one tick each"""

    def __init__(self, e, sym, cost, stock=(), off=0, reserve=None):
        self.e, self.sym = e, sym
        e.call(RESET)
        pool, masks = 0xFFFF, [0] * 16
        for t, m in (reserve or {}).items():
            masks[t] = m
            pool &= ~m
        blk = bytearray(0xC8)
        struct.pack_into(">I", blk, 0, pool)
        for t in range(16):
            struct.pack_into(">I", blk, 4 + 4 * t, masks[t])
            blk[0x44 + t] = 1 if masks[t] else 0
            blk[0x94 + t] = 1
        e.write(STAGING, blk)
        e.write(LIVE, blk)
        e.w32(DUE, 1)
        for t in range(16):
            e.w16(sym["load_voice"] + 2 * t, 0 if t in stock else cost[t])
            e.w16(sym["load_stock"] + 2 * t, cost[t] if t in stock else 0)
        e.w32(sym["load_fx"], 0)
        e.write(sym["load_off"], bytes([off]))
        e.w32(sym["load_sp_min"], 0xFFFFFFFF)
        # 2026-11-16 (PARA as one voice, csrc/para/one.c): no chord from an earlier scenario (a held chord would take
        # the track's next note before the budget sees it: scripts/emu_para_onevoice.py checks that path)
        if "pv_ch" in sym:
            e.write(sym["pv_ch"], bytes(16 * (8 + 10 * 16)))
            e.write(sym["pv_cur"], bytes(16))
            e.w32(sym["pv_kept"], 0)
        # 2026-11-13: no DSP telemetry yet (no room, no slot costs), nothing measured
        for t in range(16):
            e.w16(sym["load_meas"] + 2 * t, 0)
            e.w16(sym["smp_tlm_cost"] + 2 * t, 0)
        for k in range(4):
            e.w16(sym["smp_room_now"] + 2 * k, 0xFFFF)
        for n in ("smp_room_at", "load_busins", "load_pend", "load_pend_at"):
            e.w32(sym[n], 0)

    def telemetry(self, costs=None, room=None):
        """the DSP's idle packet as link.c keeps it: COSTS {slot: cycles}, ROOM the bus pass's room (cycles; None: none)"""
        e, sym = self.e, self.sym
        for v, c in (costs or {}).items():
            e.w16(sym["smp_tlm_cost"] + 2 * v, c // 16)
        if room is not None:
            e.w16(sym["smp_room_now"] + 2 * 3, (room + (1 << 19)) // 16)
            e.w32(sym["smp_room_at"], e.r32(sym["smp_periods"]) | 1)

    def release(self, slots):
        """stock's own key-up of each slot in SLOTS (their voices go on sounding: release tails)"""
        for v in range(16):
            if slots & (1 << v):
                self.e.call(KEY_UP, v)

    def play(self, t, n, hook=True, new_tick=True):
        """a note-on on track T, note N, in a new tick (or this one): -> the slots given; they stay held"""
        if new_tick:
            self.e.w32(DUE, 1)
        return note(self.e, self.sym, t, n, hook)[0]


def note(e: Emu, sym, t, n=64, via_hook=True):
    """the ISR's note-on call for track T: -> (slots given, older voices, a6 frame)"""
    kit = e.r32(KIT_PTR)
    frame = SCRATCH + 0x400
    e.write(frame - 0x100, bytes(0x100))
    args = (t, n, 1, 0xF, SCRATCH, 0, 0, 0, kit + 52 + 1163 * t)
    d0, d1 = e.call(sym["load_alloc_hook"] if via_hook else ALLOC, *args, a6=frame)
    return d1, d0, frame


def counters(e, sym):
    return {k: e.r32(sym["load_" + k]) for k in ("checks", "over", "keyups", "sp_min", "last_sum", "last_need")}


def twin(e, sym, build, t, n):
    """BUILD() makes a Kit state; the next note on it through the hook and through stock's allocator alone: ->
    (hook's slots, stock's, memory equal)"""
    snap = e.save(SPANS)
    k = build()
    base = e.save(SPANS)
    got = k.play(t, n, True)
    mh = e.save(SPANS)
    e.restore(base)
    ref = k.play(t, n, False)
    ms = e.save(SPANS)
    e.restore(snap)
    return got, ref, mh == ms


A2_TYPE, JUNO_TYPE, MOD_AT = 51, 50, 20 + 2 * 37   # (22, 23 until 2026-11-18)   # the PARA engines' machine type values; the sound's MOD (PARA)


PV_CHORD, PV_ENTRY = 8 + 10 * 16, 16                # csrc/para/one.h: pv_chord (live, track, seq, pad, ages, 10 places)
PV_USED, PV_HELD, PV_SOUND = 0x01, 0x02, 0x04


def para_checks(e: Emu, sym, res) -> None:
    """13..17: PARA as one voice (load.c para_notes, para_chord, slot_cost, load_pre, load_post; 2026-11-21)"""
    from dnfw import load as LD
    t = LD.load()
    pa, pj, avail = t["para"], t["para_juno"], t["avail"]
    snd0 = e.r32(KIT_PTR) + 52                 # track 0's sound
    keep = (e.read(snd0 + 0xDE, 1), e.read(snd0 + MOD_AT, 2))

    def para(v, typ=A2_TYPE):
        e.write(snd0 + 0xDE, bytes([typ]))
        e.write(snd0 + MOD_AT, struct.pack(">H", v << 8))

    def chord_of(slot, track, n):
        """slot SLOT's chord (one.c pv_ch) on TRACK: N places held and sounding"""
        c = bytearray(PV_CHORD)
        c[0], c[1] = 1, track
        for k in range(n):
            struct.pack_into(">BBBBiII", c, 8 + PV_ENTRY * k, 60 + 4 * k, PV_USED | PV_HELD | PV_SOUND, 1, 0, 0, k + 1, 0)
        e.write(sym["pv_ch"] + PV_CHORD * slot, bytes(c))

    def chord(value, n, fill, typ=A2_TYPE, n1=10):
        """track 0 (a voice 10,000): one note held, its slot a chord of N notes; track 1: N1 notes of FILL"""
        def build():
            k = Kit(e, sym, [10000] + [fill] * 15)
            k.lead = k.play(0, 60, hook=False)
            for nn in range(n1):
                k.play(1, 30 + nn, hook=False)
            chord_of(k.lead.bit_length() - 1, 0, n)
            para(value, typ)
            return k
        return build

    def summed(build, tr=1, nn=90):
        """the slots' sum load_pre saw for a note on TR, and whether it stole"""
        snap = e.save(SPANS)
        k = build()
        o0 = counters(e, sym)["over"]
        k.play(tr, nn, True)
        c = counters(e, sym)
        e.restore(snap)
        return c["last_sum"], c["over"] - o0, c["last_need"]
    try:
        off, _, _ = summed(chord(0, 4, 5000))
        one, _, _ = summed(chord(3, 1, 5000))
        four, _, _ = summed(chord(3, 4, 5000))
        eight, _, _ = summed(chord(3, 8, 5000))
        res["para_sums"] = {"off": off, "one": one, "four": four, "eight": eight}
        check("13 a PARA chord's slot is priced as one voice by its notes: voice + BASE + ADD[N]; PARA OFF a voice",
              one - off == pa["base"] and four - off == pa["base"] + pa["add"][4]
              and eight - off == pa["base"] + pa["add"][8],
              f"over PARA OFF: 1 note {one - off}, 4 {four - off}, 8 {eight - off} (table base {pa['base']}, "
              f"add {pa['add']})")
        fill = (avail - 10000 - pa["base"] - pa["add"][4] // 2) // 11   # 10 held + the note: fits by half a chord of 4
        _, over1, _ = summed(chord(3, 1, fill), nn=90)
        _, over4, _ = summed(chord(3, 4, fill), nn=90)
        res["para_fit"] = {"fill": fill, "over_chord1": over1, "over_chord4": over4}
        check("14 the joined notes count at once: a note that fits beside a chord of 1 steals beside a chord of 4",
              over1 == 0 and over4 == 1, f"steals: chord of 1 {over1}, chord of 4 {over4} (track 1 notes {fill})")
        _, _, need = summed(chord(3, 1, 5000), tr=0, nn=67)
        check("15 a PARA note that reaches the budget starts a chord: priced as one note (voice + BASE)",
              need == 10000 + pa["base"], f"need {need} (10,000 + {pa['base']})")

        def heavy(value):
            snap = e.save(SPANS)
            k = Kit(e, sym, [10000] + [20000] * 15)
            k.play(0, 60, hook=False)
            k.play(0, 64, hook=False)
            ch = e.r32(HELD)
            for nn in range(12):
                k.play(1, 30 + nn, hook=False)
            para(value)
            e.w16(sym["load_voice"] + 2 * 2, 60000)       # track 2: a heavy voice
            held0 = e.r32(HELD)
            k0 = counters(e, sym)["keyups"]
            got = k.play(2, 90, True)
            gone = held0 & ~e.r32(HELD) & ~got
            ups = counters(e, sym)["keyups"] - k0
            e.restore(snap)
            return ch, got, gone, ups
        ch, got, gone, ups = heavy(3)
        ch0, got0, gone0, ups0 = heavy(0)
        res["para_heavy"] = {"chord": ch, "took": got, "released": gone, "keyups": ups,
                             "off": {"took": got0, "released": gone0, "keyups": ups0}}
        check("16 a heavy note's further releases never take a PARA track's voice; PARA OFF takes its next oldest",
              ups >= 1 and gone and not (gone & ch) and ups0 >= 1 and (gone0 & ch0),
              f"PARA: released {gone:#06x} (track 0 {ch:#06x}); OFF: released {gone0:#06x}")
        offj, _, _ = summed(chord(0, 4, 5000, typ=JUNO_TYPE))
        fourj, _, _ = summed(chord(3, 4, 5000, typ=JUNO_TYPE))
        check("17 JUNO: a chord of 4 priced by JUNO's costs (voice + its BASE + its ADD[4])",
              fourj - offj == pj["base"] + pj["add"][4], f"{fourj - offj} ({pj['base']} + {pj['add'][4]})")
    finally:
        e.write(snd0 + 0xDE, keep[0])
        e.write(snd0 + MOD_AT, keep[1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=SNAP)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    e = Emu(a.snapshot)
    sym = install(e)
    bitrev_hooks(e)
    res = {}

    def kit(cost, notes, **kw):
        def build():
            k = Kit(e, sym, cost, **kw)
            for tr, nn in notes:
                k.play(tr, nn, hook=False)          # the kit's sounding voices, as stock gave them
            return k
        return build
    # 1. fits: 2 light voices, a light note
    got, ref, same = twin(e, sym, kit([8000] * 16, [(0, 60), (0, 62)]), 2, 64)
    check("1 the budget fits: the same slots and memory as stock's", got == ref and same, f"{got:#06x} / {ref:#06x}")
    # 2. a stock-only kit, heavy: no check at all
    c0 = counters(e, sym)["checks"]
    got, ref, same = twin(e, sym, kit([30000] * 16, [(t % 4, 40 + t) for t in range(15)], stock=set(range(16))), 1, 90)
    check("2 a stock-only kit: stock's result exactly, no check made",
          got == ref and same and counters(e, sym)["checks"] == c0, f"{got:#06x} / {ref:#06x}")
    # 3. the setting off, over budget: stock's result
    got, ref, same = twin(e, sym, kit([40000] * 16, [(0, 40 + k) for k in range(8)], off=1), 1, 90)
    check("3 VOICE BUDGET off: stock's result exactly", got == ref and same, f"{got:#06x} / {ref:#06x}")
    # 4. full: 8 voices of 35,000 held (280,000); a ninth would be 315,000: it steals a held voice, stock alone a free one
    eight = [(0, 40 + k) for k in range(8)]
    build4 = kit([35000] * 16, eight)
    snap = e.save(SPANS)
    k = build4()
    held = e.r32(HELD)
    o0 = counters(e, sym)["over"]
    got = k.play(1, 90, True)
    pool = e.r32(LIVE)
    e.restore(snap)
    k = build4()
    ref = k.play(1, 90, False)
    e.restore(snap)
    check("4 the budget full: the note steals a held voice, stock alone takes a free slot",
          got and not (got & ~held) and ref and not (ref & held) and counters(e, sym)["over"] == o0 + 1,
          f"held {held:#06x}: hook {got:#06x}, stock {ref:#06x}")
    check("4 ... the free slots are back in the live pool", (pool | held) & 0xFFFF == 0xFFFF & ~0 or
          (pool & ~held & 0xFFFF) == (0xFFFF & ~held), f"live pool {pool:#06x}")
    res["full"] = counters(e, sym)
    # 5. heavy replaces light: 14 voices of 20,000 (280,000), a 50,000 note: one stolen, one more released
    cost5 = [20000] * 16
    cost5[1] = 50000
    snap = e.save(SPANS)
    k = kit(cost5, [(0, 30 + k) for k in range(14)])()
    base5 = e.save(SPANS)
    held = e.r32(HELD)
    k0 = counters(e, sym)["keyups"]
    lowest = {"sp": STACK}

    def low(uc, addr, size, data):
        sp = uc.reg_read(SP_REG)
        if sp < lowest["sp"]:
            lowest["sp"] = sp
    from unicorn import UC_HOOK_CODE
    hk = e.uc.hook_add(UC_HOOK_CODE, low)
    got = k.play(1, 90, True)
    deep_hook = STACK - lowest["sp"]
    held_after = e.r32(HELD)
    c = counters(e, sym)
    e.restore(base5)
    lowest["sp"] = STACK
    k.play(1, 90, False)
    deep_stock = STACK - lowest["sp"]
    e.uc.hook_del(hk)
    e.restore(snap)
    check("5 a heavy voice replacing light ones: one stolen, the next oldest released",
          got and not (got & ~held) and c["keyups"] == k0 + 1 and bin(held_after).count("1") == bin(held).count("1") - 1,
          f"took {got:#06x}, released {c['keyups'] - k0}, held {bin(held).count('1')} -> {bin(held_after).count('1')}")
    # 6. a track with reserved voices (track 1: slots 12..15), all four held: the steal stays in them
    rsv = {1: 0xF000}
    snap = e.save(SPANS)
    k = kit([40000] * 16, [(1, 40 + k) for k in range(4)] + [(0, 60 + k) for k in range(3)], reserve=rsv)()
    got = k.play(1, 90, True)
    e.restore(snap)
    check("6 a track with reserved voices steals inside its own", got and not (got & ~0xF000), f"took {got:#06x}")
    # 7. a chord in one tick, over budget: the second note never takes the first's slot
    snap = e.save(SPANS)
    k = build4()
    first = k.play(1, 90, True)
    second = k.play(1, 93, True, new_tick=False)
    e.restore(snap)
    check("7 a chord in one tick: the second note takes another slot", first and second and not (first & second),
          f"{first:#06x} then {second:#06x}")
    # 8. the stack: the deepest the note-on call goes below its entry, through the hook (heavy note: load_pre, stock's
    # allocator, load_post and stock's key-up) against stock's allocator alone on the same state
    check("8 the interrupt's stack: the hook path's depth measured, within 256 bytes of stock's",
          deep_hook - deep_stock <= 256, f"hook {deep_hook} B, stock alone {deep_stock} B, more {deep_hook - deep_stock} B")
    res["stack_depth"] = {"hook": deep_hook, "stock": deep_stock}
    # 9..12 (2026-11-13): release tails and the DSP's room. Track 11 (T12, JUNO on the unit): 11 notes played, then
    # all released; the DSP reports each still sounding at 10,700 (the unit's measure), the table 9,000
    def tails(room, measured=10700, table=9000, meas=0):
        def build():
            k = Kit(e, sym, [table] * 16)
            for nn in range(11):
                k.play(11, 40 + nn, hook=False)
            k.sounding = e.r32(HELD)
            k.release(k.sounding)
            k.telemetry({v: measured for v in range(16) if k.sounding & (1 << v)}, room)
            if meas:
                e.w16(sym["load_meas"] + 2 * 11, meas)
            return k
        return build
    for name, room in (("9", 15000), ("10", 200000)):
        snap = e.save(SPANS)
        k = tails(room)()
        snd, held_now = k.sounding, e.r32(HELD)
        c0 = {n: e.r32(sym[n]) for n in ("load_tails", "load_by_room", "load_over")}
        base = e.save(SPANS)
        got = k.play(11, 90, True)
        c1 = {n: e.r32(sym[n]) for n in ("load_tails", "load_by_room", "load_over")}
        free_seen = e.r32(sym["load_last_free"])
        e.restore(base)
        ref = k.play(11, 90, False)
        e.restore(snap)
        res[f"tails_{name}"] = {"sounding": snd, "held_after_release": held_now, "hook": got, "stock": ref,
                                "free": free_seen - (1 << 32) if free_seen & 0x80000000 else free_seen,
                                **{n: c1[n] - c0[n] for n in c1}}
        if name == "9":
            check("9 release tails, little room: the note steals a sounding tail, stock alone a free slot",
                  held_now == 0 and got and not (got & ~snd) and ref and not (ref & snd) and c1["load_tails"] == c0["load_tails"] + 1
                  and c1["load_by_room"] == c0["load_by_room"] + 1,
                  f"sounding {snd:#06x} (held after release {held_now:#06x}): hook {got:#06x}, stock {ref:#06x}, {res['tails_9']}")
        else:
            check("10 the same tails, plenty of room: stock's result exactly",
                  got == ref and c1["load_over"] == c0["load_over"] and c1["load_by_room"] == c0["load_by_room"] + 1,
                  f"hook {got:#06x}, stock {ref:#06x}")
    got, ref, same = twin(e, sym, tails(None), 11, 90)
    check("11 no room reported: LOAD_AVAIL decides, the light tails fit: stock's result", got == ref and same,
          f"{got:#06x} / {ref:#06x}")
    # 12: the room asked (load.c room_asked: need x 1.5 + FLOOR - one + 6,000): table 6,000 asks 69,000, the track's
    # measured 15,000 asks 73,500; a 71,000 room: the table's would fit, the measure steals (each slot's own last
    # cost 9,000: over LOAD_TAIL, so sounding)
    snap = e.save(SPANS)
    k = tails(71000, measured=9000, table=6000, meas=15000)()
    snd = k.sounding
    t0 = e.r32(sym["load_tails"])
    got = k.play(11, 90, True)
    t1 = e.r32(sym["load_tails"])
    e.restore(snap)
    check("12 a voice measured dearer than its table: the measure decides (it steals)",
          got and not (got & ~snd) and t1 == t0 + 1, f"hook {got:#06x}, sounding {snd:#06x}")
    para_checks(e, sym, res)
    res["pass"] = all(OK)
    print(("PASS" if all(OK) else "FAIL") + f": {sum(OK)} of {len(OK)} checks")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, indent=1))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
