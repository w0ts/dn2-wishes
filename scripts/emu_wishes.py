"""The wishes record under digikit's ColdFire emulator (csrc/wishes, docs/wishes-record.md): the gate's check that
stock's own routines carry a sound's record through the four hooks.

    DT2_SECTIONS=../sec112 DNFW_EMU_FLAGS='{"weakptr": false}' ../digikit/.venv/bin/python -u scripts/emu_wishes.py \\
        --build out/b --snapshot <ui800M snapshot of this build> --json out/wishes.json

The +Drive is played by Python at the stock block driver's entries, as in the erase check (emu_erase.py's harness):
a driver-level model, not an eMMC one. Every routine below is stock's, entered directly in the paused machine:

1. stock's SAVE (0x400dd80a) of a sound with no record: the lane is zeros (as stock writes it);
2. a record put on it (wish_put), stock's SAVE again: **every byte outside the link's lane the same**, the link
   valid, its hash the xxHash32 pair of the record's bytes (recomputed here), one cell queued;
3. stock's LOAD (0x400dd34e) of that stored sound into another track's sound: the record there, read from RAM
   (no sector read); stock's LOAD of the stock-saved one: the record gone;
4. memcpy of a sound (1,163 B) and of three sounds in one block, memset of a sound, entered as every caller but
   Overbridge's now enters them (the wishes stubs, then stock's routines): the records copied, carried to the
   same offsets, dropped;
5. the UI pass (wish_poll) 0.5 s on: the cell on the +Drive, as this script spells a cell;
6. a cell written here (as another unit of ours would have) and a stored sound linking to it: LOAD leaves the
   sound waiting, the UI pass reads the cell, the record is there;
6b. a record given over our SysEx channel (link.c smp_rx, a PUT from USB, as `scripts/wish_pst.py send` frames it)
   to a sound waiting for it with no cell anywhere: the UI pass files it, the sound has it, its cell is queued;
7. ERASE's lock up: nothing written;
8. no fault; the lock never found taken (wish_reentered 0); the cost of each call, in instructions.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "test"))

from emu_erase import Disk, faults, guest_call, harness            # noqa: E402

LOAD, SAVE = 0x400DD34E, 0x400DD80A
KIT, STRIDE, STORED = 0x4210D08C, 1163, 359
FRAMES = 0x4058F8D4
SCRATCH = 0x46A30000                    # (below the C renderer at 0x46a40000) our buffers: four stored sounds, a value, a three-sound block
WISH_RAM, WISH_MAP = 0x47280000, 0x500000
CELL0, CELLS = 0x6F0800, 59392
LANE = [b for at in (36, 44, 52, 60, 68, 76, 84) for b in (at, at + 1)]
TAG, VALUE = 0x0101, b"MATRIX v1"

failures: list[str] = []
report: dict = {"checks": {}, "cost": {}}


def check(name, ok, detail=""):
    report["checks"][name] = {"ok": bool(ok), "detail": detail}
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


from test_wishes_c import cell_bytes, link_bytes, spell, xxh32       # noqa: E402 -- one reference, host-tested


def cell_of(rec: bytes) -> tuple[int, bytes]:
    """-> (sector, the cell) as csrc/wishes/store.c writes it"""
    return CELL0 + xxh32(rec, 0x57495348) % CELLS, cell_bytes(rec)


class Counter:
    def __init__(self, uc):
        from unicorn import UC_HOOK_CODE
        self.n = 0
        self.on = False

        def hit(uc_, address, size, user):
            if self.on:
                self.n += 1
        uc.hook_add(UC_HOOK_CODE, hit)

    def run(self, fn):
        self.n, self.on = 0, True
        try:
            r = fn()
        finally:
            self.on = False
        return r, self.n


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
    for at, n in ((WISH_RAM, WISH_MAP), (SCRATCH, 0x10000)):
        for page in range(at & ~0xFFFFF, at + n, 0x100000):     # page by page: a snapshot may hold one of them
            try:                                                # already (the matrix's UI pass reads MX_RAM)
                uc.mem_map(page, 0x100000, UC_PROT_ALL)
            except UcError:
                pass
    count = Counter(uc)

    def i32(name):
        return struct.unpack(">i", bytes(uc.mem_read(lay[name], 4)))[0]

    def call(fn, *args):
        return count.run(lambda: guest_call(machine, fn, *args))

    MEMCPY, MEMSET = lay["wish_memcpy_stub"], lay["wish_memset_stub"]   # what every caller but Overbridge's calls

    def mem(va, n):
        return bytes(uc.mem_read(va, n))

    snd = [KIT + 52 + STRIDE * t for t in range(8)]
    st = [SCRATCH + 0x200 * k for k in range(4)]
    val = SCRATCH + 0x1000
    out = SCRATCH + 0x1400
    block = SCRATCH + 0x2000                    # three sounds, then three more
    uc.mem_write(val, VALUE)
    for s in st:
        uc.mem_write(s, bytes(STORED))

    def get(sound):
        n = call(lay["wish_get"], sound, TAG, out, 64)[0]
        n = n - (1 << 32) if n & 0x80000000 else n
        return None if n < 0 else mem(out, n)

    # 1-2. SAVE without and with a record
    _, cost_save0 = call(SAVE, st[0], snd[0], 0)
    stock_saved = mem(st[0], STORED)
    check("a sound with no record saves its lane as zeros", all(stock_saved[b] == 0 for b in LANE))
    r, _ = call(lay["wish_put"], snd[0], TAG, val, len(VALUE))
    check("wish_put on track 1's sound", r == 0, f"returned {r}")
    _, cost_save1 = call(SAVE, st[1], snd[0], 0)
    linked = mem(st[1], STORED)
    rec = spell({TAG: VALUE})
    want = link_bytes(rec)
    diff = [k for k in range(STORED) if linked[k] != stock_saved[k]]
    check("SAVE with a record: every byte outside the lane as stock saved it",
          all(k in LANE for k in diff), f"differs at {diff[:12]}")
    check("the link: 'W', version 1, the record's xxHash32 pair, length and check, as this script spells it",
          all(linked[k] == v for k, v in want.items()), linked[36:86].hex())
    check("byte 92 (id 32, a stock unit's sink) left at what stock wrote", linked[92:94] == stock_saved[92:94])
    check("one cell queued", i32("wish_pend_tail") - i32("wish_pend_head") == 1)
    report["cost"]["save, no record (instructions)"] = cost_save0
    report["cost"]["save, a record to hash and link"] = cost_save1

    # 3. LOAD
    reads = sum(1 for k, *_ in disk.log if k == "R")
    _, cost_load1 = call(LOAD, snd[1], st[1])
    check("LOAD of the linked sound into track 2: the record is there", get(snd[1]) == VALUE)
    check("... read from RAM, no sector read", sum(1 for k, *_ in disk.log if k == "R") == reads)
    _, cost_load0 = call(LOAD, snd[1], st[0])
    check("LOAD of the stock-saved sound: the record gone", get(snd[1]) is None)
    report["cost"]["load, a link found in RAM"] = cost_load1
    report["cost"]["load, no link"] = cost_load0

    # 4. memcpy / memset
    _, cost_cp = call(MEMCPY, snd[2], snd[0], STRIDE)
    check("memcpy of a sound copies its record", get(snd[2]) == VALUE)
    _, cost_small = call(MEMCPY, out, val, 202)
    report["cost"]["memcpy of 202 B, a table with entries (whole call)"] = cost_small
    report["cost"]["memcpy of a sound with a record (whole call)"] = cost_cp
    call(MEMCPY, block, snd[0], 3 * STRIDE)
    check("memcpy of three sounds carries both records to the same offsets",
          [get(block + STRIDE * k) for k in range(3)] == [VALUE, None, VALUE])
    call(MEMSET, snd[2], 0, STRIDE)
    check("memset of a sound drops its record", get(snd[2]) is None)
    call(MEMCPY, snd[2], snd[3], STRIDE)
    check("memcpy from a sound with no record leaves none", get(snd[2]) is None)

    # 5. the UI pass writes the cell
    sector, cell = cell_of(rec)
    frames = struct.unpack(">I", mem(FRAMES, 4))[0]
    uc.mem_write(FRAMES, struct.pack(">I", frames + 1000))
    _, cost_poll = call(lay["wish_poll"])
    check("the UI pass 0.5 s on writes the cell where this script spells it", disk.get(sector) == cell,
          f"sector {sector:#x}")
    check("... and nothing outside the cells", all(CELL0 <= s < CELL0 + CELLS for k, s, n in disk.log if k == "W"))
    report["cost"]["UI pass writing one cell (instructions, the driver stubbed)"] = cost_poll

    # 6. a cell from elsewhere, found through its link
    other = spell({TAG: b"from another unit", 0x0200: b"\x01\x02"})
    osector, ocell = cell_of(other)
    disk.put(osector, ocell)
    olink = bytearray(stock_saved)
    for k, v in link_bytes(other).items():
        olink[k] = v
    uc.mem_write(st[3], bytes(olink))
    call(LOAD, snd[4], st[3])
    check("LOAD of a sound linking to a cell not in RAM: it waits (plays stock)", get(snd[4]) is None)
    reads = sum(1 for k, *_ in disk.log if k == "R")
    call(lay["wish_poll"])
    check("the UI pass reads its cell: the record is there", get(snd[4]) == b"from another unit")
    check("... with one sector read", sum(1 for k, *_ in disk.log if k == "R") - reads == 1)

    # 6b. a record given over our SysEx channel
    sys.path.insert(0, str(HERE.parent / "src"))
    from dnfw.wishes import travel as T
    sent = spell({TAG: b"sent over USB"})
    slink = bytearray(stock_saved)
    for k, v in link_bytes(sent).items():
        slink[k] = v
    uc.mem_write(st[2], bytes(slink))
    call(LOAD, snd[5], st[2])
    call(lay["wish_poll"])
    check("a sound linking to a record no cell holds: missing, plays stock", get(snd[5]) is None)
    msg = T.request(0x0123, T.PUT, struct.pack(">H", len(sent)) + sent)
    uc.mem_write(block, msg)
    call(lay["smp_rx"], block, len(msg), 2)                     # 2: USB
    check("PUT over the channel (smp_rx from USB): taken, waiting for the UI pass",
          i32("wish_puts") == 1 and i32("wish_put_wait") == 1, f"puts {i32('wish_puts')}, wait {i32('wish_put_wait')}")
    queued = i32("wish_pend_tail") - i32("wish_pend_head")
    call(lay["wish_poll"])
    check("the UI pass files it: the waiting sound has the record, its cell queued",
          get(snd[5]) == b"sent over USB" and i32("wish_put_wait") == 0
          and i32("wish_pend_tail") - i32("wish_pend_head") == queued + 1)
    call(lay["smp_rx"], block, len(msg), 1)                     # not USB: not ours
    check("the same PUT from a DIN port is not taken", i32("wish_puts") == 1)

    # 7. ERASE's lock
    writes = sum(1 for k, *_ in disk.log if k == "W")
    uc.mem_write(lay["smp_er_lock"], struct.pack(">i", 1))
    uc.mem_write(val, b"MATRIX v2")
    call(lay["wish_put"], snd[0], TAG, val, len(VALUE))
    call(SAVE, st[1], snd[0], 0)
    uc.mem_write(FRAMES, struct.pack(">I", frames + 5000))
    call(lay["wish_poll"])
    check("ERASE's lock up: nothing written", sum(1 for k, *_ in disk.log if k == "W") == writes)
    uc.mem_write(lay["smp_er_lock"], struct.pack(">i", 0))

    # 8.
    got = faults(machine)
    check("no fault", not got, f"{len(got)} fault(s)")
    check("the lock never found taken", i32("wish_reentered") == 0, str(i32("wish_reentered")))
    check("the table never full", i32("wish_full") == 0)
    check("the driver's stubs saw no error", not state.get("errors"), str(state.get("errors"))[:200])
    report["ok"] = not failures
    for k, v in report["cost"].items():
        print(f"  cost  {k}: {v}")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print("PASS" if not failures else f"FAIL: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    os.environ.setdefault("DNFW_EMU_FLAGS", json.dumps({"weakptr": False}))
    raise SystemExit(main())
