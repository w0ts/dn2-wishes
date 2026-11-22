"""PARA as one voice on stock 1.12's own voice allocator, in the emulator (csrc/para/one.c,
docs/paraphonic-onevoice.md, 2026-11-16).

    # inside the bench (bench_ns112.sh), as scripts/emu_load_budget.py:
    python scripts/emu_para_onevoice.py [--snapshot S] [--json OUT]

The build's ColdFire over a stock 1.12 UI snapshot (emu_load_budget's install); the note-on and key-up calls entered
as the audio ISR enters them: the hook at the note-on's jsr (load_alloc_hook) and at the key-up's (pv_rel_hook) with
the nine arguments the ISR pushes, a2 the event, a6 a frame whose fp-36 is the track's context; hold_final as the
frame hook calls it. Track 0 plays ANALOG 2 with PARA ON unless a check says otherwise. The checks, crash risk first
(the User, 2026-11-16: every note-off route a scenario; the chord's slot kept, "re-home", the riskiest):

 1  a chord's first note takes one slot from stock (its chord starts); UNISON 3 on the track gives it one slot, and
    the UNISON count is back after the call; PARA OFF, the same UNISON gives three
 2  a joining note: no allocator call: no slot, nothing released, stock's allocator state byte for byte as before
 3  nine notes: eight sound, the oldest dropped; still one slot held
 4  a joined note's key-up (the key-up hook): its place ends; stock's state byte for byte as stock's own call leaves it
 5  the leader's own key-up: stock releases its slot; the frame's note-off for it is kept back while joined notes hold
 6  the last joined note's key-up: the chord's note-off goes out in the next frame, and the track's next note starts
    a new chord (a slot from stock)
 7  a sequenced joined note: its gate length as stock computes a slot's, counted down a period a frame; it ends then
 8  the ARP's net (2026-11-18): with the ARP off, stock's ARP key list (0x4059d868, what 0x4002a3a6 reads) is always
    empty, and a key-held joined note stays held (it ends by its key-up, 4); with the ARP on and its list empty, it
    ends at the next frame (the ARP's key-ups never reach the allocator's key-up call); with keys in the list, held
 9  the chord's slot kept: with its own key up (stock sees it free) and every other slot busy, another track's note
    takes another slot; stock alone takes the chord's; the live masks back after the call
10  every candidate a held chord (a track with reserved slots, all leaders): the oldest chord's slot may go; that chord
    ends (counted), nothing stuck
11  stop-all, and PARA turned off mid-chord: every held note ends, the chord's note-off goes out
12  a non-PARA track's note with no chord held anywhere: through the hook = stock's allocator, byte for byte
13  the DSP's row: the chord, each place's offset, held and sounding bits
14  the interrupt's stack: the deepest the join and the start go below the hook's entry, against stock's alone
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

OK: list[bool] = []
REL_TYPE = 0                                    # an event type that is not a note-on (the key-up's call)
KEYS = 0x4059D868                               # each track's keys held (stock's 0x4002a3a6 reads it)
PER_NOTE = 0x4059DA00
STOP_ALL = 0x4058E550
CTX, EVENT = LB.SCRATCH + 0x800, LB.SCRATCH + 0x900
A2_TYPE, MOD_AT, ARP_AT = 51, 20 + 2 * 37, 351   # ANALOG 2: 51 (22 until 2026-11-18)
SPANS = LB.SPANS + [(PER_NOTE, 16), (KEYS, 64), (LB.DUE, 4)]   # (the tick copy due: a join leaves it due, as a muted note)
PV_USED, PV_HELD, PV_SOUND, PV_TIMED = 1, 2, 4, 8
PLACES = 10
ENTRY = 16                                      # one.h pv_entry: note flags seq pad, len, age, born
CHORD = 8 + PLACES * ENTRY                      # live track seq pad, ages, entries


def check(name, ok, detail=""):
    OK.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


class Rig:
    def __init__(self, e, sym):
        self.e, self.sym = e, sym
        self.kit = e.r32(LB.KIT_PTR)

    # -- the ISR's calls -----------------------------------------------------------------------------------------
    def _call(self, fn, args, t, n, length):
        from unicorn.m68k_const import UC_M68K_REG_A2
        e = self.e
        frame = LB.SCRATCH + 0x400
        e.write(frame - 0x100, bytes(0x100))
        e.w32(frame - 36, CTX)
        ctx = bytearray(0x60)
        struct.pack_into(">I", ctx, 44, self.kit + 52 + 1163 * t)     # the sound
        struct.pack_into(">I", ctx, 56, 0)                            # flags: stock's LEN table, the usual path
        e.write(CTX, bytes(ctx))
        ev = bytearray(14)
        ev[2], ev[4], ev[5] = n & 0xFF, length & 0xFF, t
        e.write(EVENT, bytes(ev))
        e.uc.reg_write(UC_M68K_REG_A2, EVENT)
        return e.call(fn, *args, a6=frame)

    def on(self, t, n, length=None, hook=True, new_tick=True):
        """a note-on (LEN byte LENGTH; None: a live note's, no timer): -> (slots given, older voices)"""
        if length is None:
            length = self.live
        if new_tick:
            self.e.w32(LB.DUE, 1)
        args = (t, n, 1, 0xF, LB.SCRATCH, 0, 0, 0, self.kit + 52 + 1163 * t)
        d0, d1 = self._call(self.sym["load_alloc_hook"] if hook else LB.ALLOC, args, t, n, length)
        return d1, d0

    def off(self, t, n, hook=True):
        """a key-up (the ISR's second allocator call): -> (slots released, d0)"""
        args = (t, n, REL_TYPE, 0xF, 0, 0, 0, 0, 0)
        d0, d1 = self._call(self.sym["pv_rel_hook"] if hook else LB.ALLOC, args, t, n, 0)
        return d1, d0

    def frame(self, off36=0, w40=0):
        """the frame hook: hold_final(+36, &+40) -> (+36, +40)"""
        e = self.e
        p = LB.SCRATCH + 0x700
        e.w32(p, w40)
        o, _ = e.call(self.sym["hold_final"], off36, p)
        return o & 0xFFFF_FFFF, e.r32(p)

    # -- the kit ---------------------------------------------------------------------------------------------------
    def reset(self, para=3, unison=None, reserve=None):
        e, sym = self.e, self.sym
        LB.Kit(e, sym, [8000] * 16, reserve=reserve)
        snd = self.kit + 52
        e.write(snd + 0xDE, bytes([A2_TYPE]))
        e.write(snd + MOD_AT, struct.pack(">H", para << 8))
        e.write(sym["pv_ch"], bytes(16 * CHORD))
        e.write(sym["pv_cur"], bytes(16))
        for n in ("pv_kept", "pv_ends", "pv_joins", "pv_starts", "pv_rels", "pv_lens", "pv_nets", "pv_drops",
                  "pv_lost", "pv_hidden", "pv_taken", "para_live", "para_kept", "hold_seq", "hold_rel"):
            e.w32(sym[n], 0)
        e.write(KEYS, bytes(64))
        e.write(self.kit + 52 + ARP_AT, bytes([0]))     # the ARP off: its key list empty, as stock keeps it then
        e.write(PER_NOTE, bytes([unison or 1] + [1] * 15))
        e.write(LB.STAGING + 0x94, bytes([unison or 1] + [1] * 15))   # (the tick copies the staging block's)
        self.live = self.live_len()
        e.w32(STOP_ALL, 0)

    def live_len(self):
        """a LEN byte stock's table maps to no timer (<= 0: a key held, as a live note's): the first such index"""
        for d in range(128):                        # (127: INF, 0 in the table)
            if struct.unpack(">i", self.e.read(0x401D8CE4 + 4 + 4 * d, 4))[0] <= 0:
                return d
        raise SystemExit("no LEN index without a timer in stock's table")

    def chord(self, s):
        raw = self.e.read(self.sym["pv_ch"] + CHORD * s, CHORD)
        live, track, seq = raw[0], raw[1], raw[2]
        places = []
        for k in range(PLACES):
            b = 8 + ENTRY * k
            note, flags, pseq = raw[b], raw[b + 1], raw[b + 2]
            length = struct.unpack(">i", raw[b + 4:b + 8])[0]
            places.append({"note": note, "flags": flags, "seq": pseq, "len": length})
        return {"live": live, "track": track, "seq": seq, "places": places}

    def sounding(self, s):
        return [p["note"] for p in self.chord(s)["places"] if p["flags"] & PV_SOUND]

    def held(self, s):
        return [p["note"] for p in self.chord(s)["places"] if p["flags"] & PV_HELD]

    def count(self, name):
        return self.e.r32(self.sym[name])


def slot_of(m):
    return (m & -m).bit_length() - 1


def scenarios(r: Rig, res: dict) -> None:
    e = r.e
    held = lambda: e.r32(LB.HELD)                      # noqa: E731
    # 1: the first note, and UNISON
    r.reset(unison=3)
    got, _ = r.on(0, 60)
    s = slot_of(got)
    c = r.chord(s) if got else {}
    check("1 a chord's first note takes one slot, with UNISON 3 on the track",
          got and bin(got).count("1") == 1 and c["live"] and c["track"] == 0 and r.count("pv_starts") == 1
          and e.read(PER_NOTE, 1)[0] == 3, f"slots {got:#06x}, UNISON after {e.read(PER_NOTE, 1)[0]}")
    r.reset(para=0, unison=3)
    off3, _ = r.on(0, 60)
    check("1 ... PARA OFF, UNISON 3: three slots, no chord", bin(off3).count("1") == 3 and r.count("pv_starts") == 0,
          f"slots {off3:#06x}")
    # 2: a joining note leaves stock's state as it was
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    e.w32(LB.DUE, 1)                                       # (a new tick, before the state is taken)
    before = e.save(SPANS)
    got, d0 = r.on(0, 64, new_tick=False)
    after = e.save(SPANS)
    check("2 a joining note: no slot, nothing released, stock's allocator state byte for byte",
          got == 0 and d0 == 0 and before == after and r.count("pv_joins") == 1 and 64 in r.held(L),
          f"d1 {got:#06x} d0 {d0:#06x}, joins {r.count('pv_joins')}, held {r.held(L)}")
    res["join"] = r.chord(L)
    # 3: nine notes
    for n in (67, 71, 74, 77, 81, 84, 88):
        r.on(0, n)
    snd = r.sounding(L)
    check("3 nine notes: eight sound, the oldest (the leader's own 60) dropped; one slot held",
          len(snd) == 8 and 60 not in snd and r.count("pv_drops") == 1 and held() == lead,
          f"sounding {sorted(snd)}, held slots {held():#06x}")
    # 4: a joined note's key-up
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    r.on(0, 67)
    base = e.save(SPANS)
    got, d0 = r.off(0, 64)
    hooked = e.save(SPANS)
    e.restore(base)
    ref, d0r = r.off(0, 64, hook=False)
    stock = e.save(SPANS)
    e.restore(hooked)
    res["keyup_diff"] = [(hex(va + i), a[i], b[i]) for (va, a), (_, b) in zip(hooked, stock) for i in range(len(a))
                         if a[i] != b[i]][:12]
    print("   ", res["keyup_diff"])
    check("4 a joined note's key-up: its place ends; stock gives back nothing, its state as its own call leaves it",
          got == 0 and d0 == 0 and ref == 0 and hooked == stock and 64 not in r.held(L) and 67 in r.held(L)
          and r.count("pv_rels") == 1, f"held {r.held(L)}, d1 {got:#x} d0 {d0:#x} stock {ref:#x}, same {hooked == stock}, "
                                         f"rels {r.count('pv_rels')}")
    # 5: the leader's own key-up
    rel, _ = r.off(0, 60)
    o36, o40 = r.frame(off36=rel, w40=rel)
    check("5 the leader's own key-up: stock releases its slot; its note-off kept back while 67 holds",
          rel == lead and not (o36 & lead) and not (o40 & lead) and (r.count("pv_kept") & lead) and r.held(L) == [67],
          f"released {rel:#06x}, +36 {o36:#06x}, kept {r.count('pv_kept'):#06x}")
    # 6: the last one
    r.off(0, 67)
    o36, o40 = r.frame()
    nxt, _ = r.on(0, 72)
    check("6 the last joined key-up: the chord's note-off goes out; the next note starts a new chord (a slot)",
          (o36 & lead) and (o40 & lead) and nxt and r.count("pv_starts") == 2,
          f"+36 {o36:#06x}, next {nxt:#06x}")
    # 7: a sequenced joined note
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64, length=3)
    tbl = 0x401D8CE4
    want = struct.unpack(">i", e.read(tbl + 4 + 4 * 3, 4))[0]
    step = e.r32(0x402A132C)
    p = next(x for x in r.chord(L)["places"] if x["note"] == 64)
    frames = 0
    while 64 in r.held(L) and frames < 100000:
        r.frame()
        frames += 1
    expect = -(-want // step) + 1                          # counted from the frame after it came
    check("7 a sequenced joined note: stock's LEN for a slot, counted a period a frame, it ends then",
          p["len"] == want and p["flags"] & PV_TIMED and frames == expect and r.count("pv_lens") == 1,
          f"len {p['len']} (stock's {want}), step {step}, ended after {frames} frames (expected {expect})")
    # 8: the safety net
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    for _ in range(30):
        r.frame()
    check("8 the ARP off (its list empty, as stock keeps it): a key-held joined note stays held over 30 frames",
          64 in r.held(L) and r.count("pv_nets") == 0, f"held {r.held(L)}, nets {r.count('pv_nets')}")
    e.write(r.kit + 52 + ARP_AT, bytes([1]))
    e.w32(KEYS, 1)
    r.frame()
    held_list = 64 in r.held(L)
    e.w32(KEYS, 0)
    r.frame()
    e.write(r.kit + 52 + ARP_AT, bytes([0]))
    check("8 the ARP on: held while its key list holds a key, ends at the next frame once it is empty",
          held_list and 64 not in r.held(L) and r.count("pv_nets") == 1, f"held {r.held(L)}, nets {r.count('pv_nets')}")
    # 9: the chord's slot kept
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    r.off(0, 60)                                           # stock: the leader's slot free
    for n in range(15):                                    # every other slot held: stock sees only the chord's free
        r.on(1, 30 + n, hook=False)
    busy = held()
    base = e.save(SPANS)
    got, _ = r.on(2, 90)
    pool = e.r32(LB.LIVE)
    hooked = e.save(SPANS)
    e.restore(base)
    ref, _ = r.on(2, 90, hook=False)
    e.restore(hooked)
    res["kept"] = {"leader": lead, "busy": busy, "hook": got, "stock": ref, "pool": pool}
    check("9 the chord's slot kept: another track's note takes another slot, stock alone takes the chord's",
          got and not (got & lead) and ref == lead and (pool & lead) and r.count("pv_hidden") >= 1
          and 64 in r.held(L), f"leader {lead:#06x}: hook {got:#06x}, stock {ref:#06x}, pool after {pool:#06x}")
    # 10: every candidate a held chord
    r.reset(reserve={0: 0x0001})                           # track 0 owns slot 0 only
    a1, _ = r.on(0, 60)
    r.on(0, 64)
    r.off(0, 60)
    r.frame(a1, a1)
    e.write(r.kit + 52 + MOD_AT, struct.pack(">H", 0))     # (PARA OFF for this note: it cannot join, nor go elsewhere)
    t0 = r.count("pv_taken")
    d1, _ = r.on(0, 36)
    stuck = [s for s in range(16) if r.chord(s)["live"] and (d1 >> s) & 1]
    check("10 every candidate a held chord: the oldest chord's slot may go; that chord ends, nothing stuck",
          d1 == a1 and r.count("pv_taken") == t0 + 1 and not stuck, f"took {d1:#06x}, the chord's {a1:#06x}")
    # 11: stop-all, PARA off
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    r.off(0, 60)
    r.frame(lead, lead)
    e.w32(STOP_ALL, 2)
    o36, _ = r.frame()
    e.w32(STOP_ALL, 0)
    check("11 stop-all: every held note ends, the chord's note-off goes out", (o36 & lead) and not r.held(L),
          f"+36 {o36:#06x}, held {r.held(L)}")
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    r.off(0, 60)
    r.frame(lead, lead)
    e.write(r.kit + 52 + MOD_AT, struct.pack(">H", 0))
    o36, _ = r.frame()
    check("11 ... PARA turned off mid-chord: the same", (o36 & lead) and not r.held(L), f"+36 {o36:#06x}")
    # 12: a non-PARA note, no chord: the hook is stock
    r.reset(para=0)
    for n in range(5):
        r.on(3, 40 + n, hook=False)
    base = e.save(SPANS)
    got, d0 = r.on(4, 70)
    hooked = e.save(SPANS)
    e.restore(base)
    ref, d0r = r.on(4, 70, hook=False)
    stock = e.save(SPANS)
    check("12 a note with no chord anywhere: through the hook = stock's allocator, byte for byte",
          (got, d0) == (ref, d0r) and hooked == stock, f"{got:#06x} / {ref:#06x}")
    # 13: the row
    r.reset()
    lead, _ = r.on(0, 60)
    L = slot_of(lead)
    r.on(0, 64)
    r.on(0, 55)
    r.off(0, 64)
    row = LB.SCRATCH + 0x780
    e.call(r.sym["pv_row"], L, row)
    w = [e.r32(row + 4 * j) for j in range(6)]
    h = [w[j // 2] >> (16 * (j & 1)) & 0xFFFF for j in range(12)]
    places = {(x & 0xFF) - (256 if x & 0x80 else 0): x for x in h[1:11] if x & 0x400}
    res["row"] = h
    check("13 the DSP's row: the chord live, its places' offsets (0, +4, -5), held and sounding bits",
          h[0] & 0x8000 and (h[0] & 0x7F) == 60 and set(places) == {0, 4, -5}
          and places[0] & 0x300 == 0x300 and places[4] & 0x300 == 0x200 and places[-5] & 0x300 == 0x300,
          " ".join(f"{x:04x}" for x in h))
    # 14: the stack
    from unicorn import UC_HOOK_CODE
    low = {"sp": LB.STACK}

    def deep(uc, addr, size, data):
        sp = uc.reg_read(LB.SP_REG)
        low["sp"] = min(low["sp"], sp)
    r.reset()
    hk = e.uc.hook_add(UC_HOOK_CODE, deep)
    r.on(0, 60)
    r.on(0, 64)
    r.off(0, 64)
    d_hook = LB.STACK - low["sp"]
    low["sp"] = LB.STACK
    r.on(5, 60, hook=False)
    d_stock = LB.STACK - low["sp"]
    e.uc.hook_del(hk)
    res["stack"] = {"hook": d_hook, "stock": d_stock}
    check("14 the interrupt's stack: the hook paths within 256 bytes of stock's allocator alone",
          d_hook - d_stock <= 256, f"hook {d_hook} B, stock {d_stock} B")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=LB.SNAP)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    e = LB.Emu(a.snapshot)
    sym = LB.install(e)
    LB.bitrev_hooks(e)
    res: dict = {}
    scenarios(Rig(e, sym), res)
    res["pass"] = all(OK)
    print(("PASS" if all(OK) else "FAIL") + f": {sum(OK)} of {len(OK)} checks")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, indent=1))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
