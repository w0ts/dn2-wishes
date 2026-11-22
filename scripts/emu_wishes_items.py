"""The wishes record on kits and patterns under digikit's ColdFire emulator (csrc/wishes/item.c, items.S;
docs/wishes-record.md "Every item type"): stock's own kit and pattern loader and saver, entered directly in the
paused machine, carry an item's record through the four new hooks.

    DT2_SECTIONS=../sec112 DNFW_EMU_FLAGS='{"weakptr": false}' ../digikit/.venv/bin/python -u \\
        scripts/emu_wishes_items.py --build out/b --snapshot <ui800M snapshot of this build> --json out/items.json

The +Drive is played by Python at the stock block driver's entries (emu_erase.py's harness), as in emu_wishes.py.
For each of the kit (live 0x4210d08c + 23,921 n, stored 10,752 B) and the pattern (live 0x4121998c + 122,478 n,
stored 89,088 B):

1. stock's SAVE with no record: the link's place is zeros (written, even over noise);
2. a record put on the item (wish_item, wish_put), stock's SAVE again into a buffer of the same noise: **every
   byte outside the link the same**, the link as test_wishes_items_c.py spells it;
3. stock's LOAD of that into another item: the record there; stock's LOAD of the first: the record gone; and the
   loaded live object byte for byte as with the hook's link zeroed (the link changes nothing stock reads);
4. the live object copied (memcpy, as kit and pattern copy/paste) and cleared (memset) through the wishes stubs:
   the record copied, then dropped;
5. the UI pass writes the cell, whose kind byte names the item type;
6. the pattern's link moves to another unused lock record when its record gets a lock (the body stock writes);
   with all 80 lock records in use, the one with the fewest locked steps gives way to it (the User, 2026-11-12);
7. ERASE's lock up: nothing written; no fault; the lock never found taken.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from emu_erase import Disk, faults, guest_call, harness            # noqa: E402

KIT_LOAD, KIT_SAVE = 0x400DDDB6, 0x400DDFA8
PAT_LOAD, PAT_SAVE = 0x400DE77A, 0x400DE90C
SONG_LOAD, SONG_SAVE = 0x400DEBCE, 0x400DECC6
PS_LOAD, PS_SAVE = 0x400DF050, 0x400DF6DE
SONG0, SONG_BYTES, SONG_STORED, SONG_LANE = 0x423FE67D, 3694, 3072, 2900
PS, PS_BYTES, PS_STORED, PS_LANE = 0x42432A61, 738, 1024, 544
KIT0, KIT_BYTES, KIT_STORED, KIT_LANE = 0x4210D08C, 23921, 10752, 10416
PAT0, PAT_BYTES, PAT_STORED, LOCKS, RECS, REC = 0x4121998C, 122478, 89088, 68148, 80, 258
WI_KIT, WI_PATTERN, WI_SONG, WI_PROJECT = 2, 3, 4, 5
FRAMES = 0x4058F8D4
SCRATCH = 0x47740000                    # our buffers: four stored patterns' room, above the matrix's MX_RAM
WISH_RAM, WISH_MAP = 0x47280000, 0x500000
CELL0, CELLS = 0x5D8000, 92160   # v0.69.2 (csrc/include/dmove.h)
TAG = 0x0100

failures: list[str] = []
report: dict = {"checks": {}, "cost": {}}


def check(name, ok, detail=""):
    report["checks"][name] = {"ok": bool(ok), "detail": detail}
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


from test.test_wishes_c import cell_bytes, spell, xxh32               # noqa: E402 -- one reference, host-tested
from test.test_wishes_items_c import link                              # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--json", default=None)
    p.add_argument("--layout", default=str(HERE.parent / "src/dnfw/mods/waverider_code.json"))
    a = p.parse_args()
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    disk = Disk()
    machine, state = harness(a, disk)
    uc = machine.uc
    from unicorn import UC_PROT_ALL, UcError
    for at, n in ((WISH_RAM, WISH_MAP), (SCRATCH, 0x80000)):
        for page in range(at & ~0xFFFFF, at + n, 0x100000):     # page by page (emu_wishes.py's trap)
            try:
                uc.mem_map(page, 0x100000, UC_PROT_ALL)
            except UcError:
                pass

    def mem(va, n):
        return bytes(uc.mem_read(va, n))

    def i32(name):
        return struct.unpack(">i", mem(lay[name], 4))[0]

    def call(fn, *args):
        return guest_call(machine, fn, *args)

    if "dm_bits" in lay:                        # v0.69.2: a unit whose +Drive moves are done (dmove.c: the record waits for them)
        uc.mem_write(lay["dm_bits"], struct.pack(">I", 0x3F))
    MEMCPY, MEMSET = lay["wish_memcpy_stub"], lay["wish_memset_stub"]
    val, out = SCRATCH, SCRATCH + 0x400
    bufs = [SCRATCH + 0x1000 + 0x16000 * k for k in range(4)]   # 4 x 90,112 B: room for a stored pattern each
    noise = random.Random(7).randbytes(PAT_STORED)

    def get(live):
        n = call(lay["wish_get"], live, TAG, out, 64)
        n = n - (1 << 32) if n & 0x80000000 else n
        return None if n < 0 else mem(out, n)

    def put(live, value):
        uc.mem_write(val, value)
        r = call(lay["wish_put"], live, TAG, val, len(value))
        return r - (1 << 32) if r & 0x80000000 else r

    def item(kind, index):
        return call(lay["wish_item"], kind, index)

    check("wish_item names stock's kits and patterns",
          item(WI_KIT, 0) == KIT0 and item(WI_KIT, 128) == KIT0 + 128 * KIT_BYTES and item(WI_KIT, 129) == 0
          and item(WI_PATTERN, 127) == PAT0 + 127 * PAT_BYTES and item(WI_PATTERN, 128) == 0)

    kit_now, pat_now = struct.unpack(">2I", mem(0x42C5B9AC, 4) + mem(0x42C5B9A0, 4))
    check("the kit playing (0x42c5b9ac) is one of the 129 kits, the pattern (0x42c5b9a0) one of the 128",
          (kit_now - KIT0) % KIT_BYTES == 0 and (kit_now - KIT0) // KIT_BYTES < 129
          and (pat_now - PAT0) % PAT_BYTES == 0 and (pat_now - PAT0) // PAT_BYTES < 128,
          f"kit {kit_now:#x}, pattern {pat_now:#x}")
    report["kit playing"], report["pattern playing"] = kit_now, pat_now

    frames = struct.unpack(">I", mem(FRAMES, 4))[0]

    def flush():
        nonlocal frames
        frames += 1000
        uc.mem_write(FRAMES, struct.pack(">I", frames))
        call(lay["wish_poll"])

    def round_trip(name, kind, a_live, b_live, size, stored_n, save, load, lane_of, carry=True):
        uc.mem_write(bufs[0], noise[:stored_n])
        uc.mem_write(bufs[1], noise[:stored_n])
        call(save, bufs[0], a_live, 0)
        s0 = mem(bufs[0], stored_n)
        lane = lane_of(s0)
        check(f"{name}: SAVE with no record writes zeros where the link goes", s0[lane:lane + 14] == bytes(14),
              f"at {lane}")
        value = f"{name} wish".encode()
        check(f"{name}: wish_put on it", put(a_live, value) == 0)
        call(save, bufs[1], a_live, 0)
        s1 = mem(bufs[1], stored_n)
        diff = [k for k in range(stored_n) if s1[k] != s0[k]]
        check(f"{name}: SAVE with a record: every byte outside the link as stock saved it",
              all(lane <= k < lane + 14 for k in diff), f"differs at {diff[:8]}")
        rec = spell({TAG: value})
        check(f"{name}: the link as test_wishes_items_c spells it", s1[lane:lane + 14] == link(rec),
              s1[lane:lane + 14].hex())
        before = mem(b_live, size)
        call(load, b_live, bufs[1], 0)
        check(f"{name}: LOAD of the linked one into another: the record there", get(b_live) == value)
        loaded = mem(b_live, size)
        call(load, b_live, bufs[0], 0)
        check(f"{name}: LOAD of the one saved without a record: the record gone", get(b_live) is None)
        check(f"{name}: the link changes nothing stock loads (the live bytes the same either way)",
              mem(b_live, size) == loaded, "")
        uc.mem_write(b_live, before)
        if carry:
            call(MEMCPY, b_live, a_live, size)
            check(f"{name}: memcpy of the live object copies its record", get(b_live) == value)
            call(MEMSET, b_live, 0, size)
            check(f"{name}: memset of it drops the record", get(b_live) is None and get(a_live) == value)
            uc.mem_write(b_live, before)
        else:
            call(load, b_live, bufs[1], 0)          # the one live object: its record back for the cell's check
        sector = CELL0 + xxh32(rec, 0x57495348) % CELLS
        flush()
        c = disk.get(sector)
        want = bytearray(cell_bytes(rec))
        want[5] = kind
        a_, b_ = 1, 0
        for x in want[:508]:
            a_ += x
            b_ += a_
        want[508:] = ((((b_ << 16) ^ a_) & 0xFFFFFFFF) ^ 0x57495348).to_bytes(4, "big")
        check(f"{name}: the UI pass writes its cell, kind {kind}", c == bytes(want), f"sector {sector:#x}")
        return s1, lane

    round_trip("kit", WI_KIT, item(WI_KIT, 0), item(WI_KIT, 127), KIT_BYTES, KIT_STORED, KIT_SAVE, KIT_LOAD,
               lambda s: KIT_LANE)

    def pat_lane(s):
        for i in reversed(range(RECS)):
            r = LOCKS + REC * i
            if s[r] == 0xFF and s[r + 1] == 0xFF:
                return r + 2
        return -1

    s1, lane = round_trip("pattern", WI_PATTERN, item(WI_PATTERN, 0), item(WI_PATTERN, 127), PAT_BYTES,
                          PAT_STORED, PAT_SAVE, PAT_LOAD, pat_lane)
    report["pattern lane (stored offset)"] = lane

    round_trip("song", WI_SONG, item(WI_SONG, 1), item(WI_SONG, 16), SONG_BYTES, SONG_STORED, SONG_SAVE,
               SONG_LOAD, lambda s: SONG_LANE)
    # one live project's settings: the second item is the same object, saved without, then loaded with the link
    ps_live = item(WI_PROJECT, 0)
    check("wish_item names the project's settings", ps_live == PS)
    round_trip("project settings", WI_PROJECT, ps_live, ps_live, PS_BYTES, PS_STORED, PS_SAVE, PS_LOAD,
               lambda s: PS_LANE, carry=False)              # 738 B: smaller than a sound, never carried by copy

    # 6. the record that held the link gets a lock: the link moves
    rec_i = (lane - 2 - LOCKS) // REC
    a_live = item(WI_PATTERN, 0)
    live_pool = a_live + 97872
    lr = live_pool + REC * rec_i
    saved_rec = mem(lr, REC)
    uc.mem_write(lr, bytes([3, 2]) + b"\x00\x40" * 128)          # a lock on track 3, parameter 3, every step
    call(PAT_SAVE, bufs[2], a_live, 0)
    s2 = mem(bufs[2], PAT_STORED)
    lane2 = pat_lane(s2)
    check("pattern: a lock in the link's record: stock saves the lock there, the link in the next unused one",
          s2[LOCKS + REC * rec_i + 1] == 2 and lane2 == lane - REC and s2[lane2:lane2 + 14] == s1[lane:lane + 14],
          f"lane {lane2}")
    call(PAT_LOAD, item(WI_PATTERN, 126), bufs[2], 0)
    check("... and LOAD finds it", get(item(WI_PATTERN, 126)) == b"pattern wish")
    uc.mem_write(lr, saved_rec)

    # 6b. every lock record in use: the one with the fewest locked steps gives way to the link (the User, 2026-11-12)
    saved_pool = mem(live_pool, RECS * REC)
    full = b"".join(bytes([3, i % 16]) + (b"\x10\x00" * 2 + b"\xff\xff" * 126 if i == 40 else b"\x10\x00" * 128)
                    for i in range(RECS))
    uc.mem_write(live_pool, full)
    call(PAT_SAVE, bufs[2], a_live, 0)
    s3 = mem(bufs[2], PAT_STORED)
    at40 = LOCKS + REC * 40
    others = all(s3[LOCKS + REC * i + 1] == i % 16 for i in range(RECS) if i != 40)
    dropped = i32("wish_item_dropped") & 0xFFFFFFFF
    check("all 80 lock records in use: the one with the fewest steps (record 40, 2 steps) gives way to the link",
          s3[at40:at40 + 2] == b"\xff\xff" and s3[at40 + 2:at40 + 16] == s1[lane:lane + 14] and others
          and dropped >> 8 == (2 << 8 | 40 % 16), f"dropped {dropped:#x}")
    call(PAT_LOAD, item(WI_PATTERN, 125), bufs[2], 0)
    check("... and LOAD finds the record", get(item(WI_PATTERN, 125)) == b"pattern wish")
    uc.mem_write(live_pool, saved_pool)

    # 7.
    writes = sum(1 for k, *_ in disk.log if k == "W")
    uc.mem_write(lay["smp_er_lock"], struct.pack(">i", 1))
    put(item(WI_KIT, 0), b"kit wish 2")
    call(KIT_SAVE, bufs[3], item(WI_KIT, 0), 0)
    flush()
    check("ERASE's lock up: nothing written", sum(1 for k, *_ in disk.log if k == "W") == writes)
    uc.mem_write(lay["smp_er_lock"], struct.pack(">i", 0))
    check("the item hooks ran", i32("wish_item_loads") >= 6 and i32("wish_item_saves") >= 6,
          f"{i32('wish_item_loads')} loads, {i32('wish_item_saves')} saves")
    got = faults(machine)
    check("no fault", not got, f"{len(got)} fault(s)")
    check("the lock never found taken", i32("wish_reentered") == 0, str(i32("wish_reentered")))
    check("the driver's stubs saw no error", not state.get("errors"), str(state.get("errors"))[:200])
    report["ok"] = not failures
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print("PASS" if not failures else f"FAIL: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    os.environ.setdefault("DNFW_EMU_FLAGS", json.dumps({"weakptr": False}))
    raise SystemExit(main())
