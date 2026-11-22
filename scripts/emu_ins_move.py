"""2026-11-22 (v0.69.1): the inserts' records move off upstream's sectors, in the ColdFire emulator
(csrc/inserts/store.c move_once): the `insmove` scenario of `emu_waverider_menu.py`'s link16 step, with
the +Drive played by Python (as emu_tune.py and emu_perform.py: the OS's own LOAD runs, ins_store_poll
and pf_poll are called as the UI loop calls them).

Until v0.68.1 the inserts' records were at 0x6E0400 + 2 p + c (to 0x6E0501); upstream's PERFORM (v0.69)
keeps its records at 0x6E0500..0x6E05FF, so ours moved to 0x5FF000 + 2 p + c, the move's mark at
0x5FF102 (the User, 2026-11-22: "move our stuff"). What it checks (each a key of the result's "facts"):

1. power-on with v0.67.5's records at the old place (project 7's two copies, the working copy) and no
   mark: each whole old copy copied byte for byte to the same copy of the same record at the new place,
   the mark written, the old sectors never written; the working copy's inserts loaded;
2. LOAD 7: project 7's inserts, from the newer copy, as v0.67.5 saved them;
3. PERFORM on project 0, whose PERFORM sectors (0x6E0500/1) hold the old working copy: eight empty
   macros (the old record refused), and on project 7 (no record): empty too;
4. a second power-on: the mark found, nothing copied again, nothing written but the working copy;
5. the new records erased (as ERASE MOD DATA does; the mark kept) and a power-on: every slot OFF, the
   old records not brought back;
6. every sector written lies in the new records or is the mark.
"""

from __future__ import annotations

import struct

ACTIVE = 0x405CE899
PJ_LOAD, PJ_GET_PROJECT = 0x40042E6E, 0x4018AC5A
STUB_OPEN, STUB_TEMP = 0x40042B92, 0x40040190
OLD, NEW = 0x6E0400, 0x5FF000                    # inserts/store.c INS_OLD, INS_BASE
MARK = NEW + 2 * 129                             # INS_MARK
MAGIC, CHECK_XOR = 0x444E3249, 0x494E5331
W_REC, W_CHECK = 4, 4 + 64
MACRO = 26                                       # perf.c's struct pf_macro (emu_perform.py)


def check(words):
    a, b = 1, 0
    raw = struct.pack(f">{W_CHECK}I", *words[:W_CHECK])
    for x in raw:
        a = (a + x) & 0xFFFFFFFF
        b = (b + a) & 0xFFFFFFFF
    return (((b << 16) & 0xFFFFFFFF) ^ a) ^ CHECK_XOR


def record(p, seq, slots):
    """a v0.67.5 record sector: SLOTS {(t, j): (type, MIX, K1..K6)}, the rest OFF"""
    w = [MAGIC, 1, p, seq] + [0] * 124
    body = bytearray(256)
    for (t, j), f in slots.items():
        body[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(f)
    w[W_REC:W_REC + 64] = list(struct.unpack(">64I", bytes(body)))
    w[W_CHECK] = check(w)
    return struct.pack(">128I", *w)


def run(cx):
    m, call, disk, io, syms, guest_call = cx["machine"], cx["call"], cx["disk"], cx["io"], cx["syms"], cx["guest_call"]
    scratch = cx["scratch"]
    facts, notes = {}, {}
    wlog = []
    io["log"] = wlog

    def i32(name):
        return struct.unpack(">i", m.read(syms[name], 4))[0]

    def put(name, v):
        m.write(syms[name], struct.pack(">i", v))

    def ins_poll(n=3):
        for _ in range(n):
            call("ins_store_poll")

    def inserts():
        """(type, MIX, K1..K6 of its type) for every track's two slots"""
        sel, mod = m.read(syms["ins_sel"], 32), m.read(syms["ins_mod"], 32)
        kv = m.read(syms["ins_kv"], 16 * 2 * 14 * 6)
        out = {}
        for t in range(16):
            for j in range(2):
                y = sel[2 * t + j]
                at = ((t * 2 + j) * 14 + y) * 6
                out[(t, j)] = (y, mod[2 * t + j]) + tuple(kv[at:at + 6])
        return out

    def want(slots):
        return {(t, j): slots.get((t, j), (0, None))[:2] for t in range(16) for j in range(2)}

    def got_short(ins):
        return {k: (v[0], v[1] if v[0] else None) for k, v in ins.items()}

    def macros():
        raw = m.read(syms["pf"], 8 * MACRO)
        return [(raw[MACRO * k:MACRO * k + 9].split(b"\0")[0], raw[MACRO * k + 10],
                 tuple(raw[MACRO * k + 11 + 3 * j] for j in range(5))) for k in range(8)]

    empty = [(b"", 0, (0xFF,) * 5)] * 8

    def os_load(slot):
        old = (m.read(STUB_OPEN, 4), m.read(STUB_TEMP, 4))
        m.write(STUB_OPEN, bytes.fromhex("70014e75"))
        m.write(STUB_TEMP, bytes.fromhex("70014e75"))
        guest_call(PJ_GET_PROJECT)
        proj = guest_call.returned["d0"]
        m.write(scratch, bytes(32))
        guest_call(PJ_LOAD, proj, slot & 0xFFFFFFFF, scratch, limit=20_000_000)
        m.write(STUB_OPEN, old[0])
        m.write(STUB_TEMP, old[1])
        ins_poll()
        return struct.unpack(">b", m.read(ACTIVE, 1))[0]

    def power_on():
        put("ins_st_booted", 0)
        ins_poll()

    # the +Drive as v0.67.5 left it: project 7 saved twice (copy 1 the newer), the working copy
    p7_old = {(0, 0): (3, 90, 10, 20, 30, 40, 50, 60), (2, 1): (5, 40, 1, 2, 3, 4, 5, 6)}
    p7_new = {(0, 0): (3, 100, 11, 21, 31, 41, 51, 61), (5, 0): (7, 64, 64, 64, 64, 64, 64, 64),
              (15, 1): (2, 127, 0, 127, 0, 127, 0, 127)}
    work = {(1, 0): (4, 80, 9, 8, 7, 6, 5, 4), (9, 1): (6, 33, 12, 34, 56, 78, 90, 100)}
    disk.clear()
    old = {OLD + 2 * 7: record(7, 0, p7_old), OLD + 2 * 7 + 1: record(7, 1, p7_new),
           OLD + 2 * 128: record(128, 4, work)}
    disk.update(old)

    # 1. power-on: the move
    n0 = len(wlog)
    copied0 = i32("ins_st_copied")
    power_on()
    w1 = [s for s, _ in wlog[n0:]]
    copies = {s - OLD + NEW: d for s, d in old.items()}
    same = all(disk.get(s) == d for s, d in copies.items())
    mark = disk.get(MARK, bytes(512))
    mark_ok = struct.unpack(">2I", mark[:8]) == (0x444E324D, 0x444E324D ^ 0xFFFFFFFF)
    notes["1"] = {"writes": [hex(s) for s in w1], "moved": i32("ins_st_moved"), "copied": i32("ins_st_copied") - copied0}
    facts["1 power-on, v0.67.5's records at the old place: each whole copy copied byte for byte, the mark "
          "written, the old sectors not written; the working copy's inserts loaded"] = (
        i32("ins_st_moved") == 1 and i32("ins_st_copied") - copied0 == 3 and same and mark_ok
        and all(disk.get(s) == d for s, d in old.items()) and not [s for s in w1 if OLD <= s < OLD + 0x200]
        and got_short(inserts()) == want(work))

    # 2. LOAD 7: the newer copy's inserts
    a7 = os_load(7)
    ins7 = inserts()
    facts["2 LOAD 7: project 7's inserts from its newer copy, as v0.67.5 saved them"] = (
        a7 == 7 and all(ins7[k] == v for k, v in p7_new.items()) and got_short(ins7) == want(p7_new))

    # 3. PERFORM: project 0's sectors hold the old working copy; project 7 has no record
    put("pf_owner", -2)
    call("pf_poll")
    call("pf_poll")
    pf7 = macros()
    a0 = os_load(0)
    put("pf_owner", -2)
    call("pf_poll")
    call("pf_poll")
    pf0 = macros()
    notes["3"] = {"active": a0, "pf_bad": i32("pf_bad")}
    facts["3 PERFORM: empty on project 7 (no record) and on project 0 (its sectors hold the old working copy)"] = (
        pf7 == empty and a0 == 0 and pf0 == empty)

    # 4. a second power-on: the mark found
    n4 = len(wlog)
    c4 = i32("ins_st_copied")
    power_on()
    w4 = [s for s, _ in wlog[n4:]]
    notes["4"] = {"writes": [hex(s) for s in w4]}
    # (the harness's LOAD counters are not 0 at this power-on, so store.c replays the last LOAD as on a unit whose
    # OS loaded a project before our first pass: the working copy, record 128, is written; nothing else)
    facts["4 a second power-on: the mark found, nothing copied, nothing written but the working copy"] = (
        i32("ins_st_moved") == 2 and i32("ins_st_copied") == c4
        and all(s in (NEW + 256, NEW + 257) for s in w4))

    # 5. the new records erased, the mark kept: every slot OFF, nothing brought back from the old place
    for s in range(NEW, MARK):
        disk.pop(s, None)
    m.write(syms["ins_sel"], bytes(32))         # (RAM at power-on: every slot OFF)
    power_on()
    facts["5 the new records erased (the mark kept) and a power-on: every slot OFF, the old records not back"] = (
        i32("ins_st_moved") == 2 and all(v[0] == 0 for v in inserts().values()))

    # 6. where it wrote
    out = [hex(s) for s, _ in wlog if not NEW <= s <= MARK]
    notes["6"] = {"outside": out[:10]}
    facts["6 every sector written lies in the new records or is the mark"] = not out
    disk.clear()
    return {"facts": facts, "notes": notes, "ok": all(facts.values())}
