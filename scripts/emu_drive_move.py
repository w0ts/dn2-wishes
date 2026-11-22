"""2026-11-22 (v0.69.2): our +Drive data out of upstream's places, in the ColdFire emulator (csrc/sampler/dmove.c,
csrc/include/dmove.h): the `drivemove` scenario of `emu_waverider_menu.py`'s link16 step, the +Drive played by Python.

A +Drive as v0.69.1 left it: the inserts already moved (their mark), SAFE MODE's record at 0x6E0300, the DSP
program's copy at 0x6E8000, our tunings at 0x6E0600, bank lists at 0x5E0000 / 0x5F0000, the wishes record's cells at
0x6F0800 (59,392); and, at the new places, what must not come alive: a stale tunings record and an upstream-looking
bank list header with nothing copied over them. Then dm_run(), as pools.c's power-on runs it. What it checks (each a
key of the result's "facts"; SAFE MODE's record and the DSP copy move at the boot itself, normal.c and lzma7cache.c,
checked by the safeboot step's part m and test_lzma7cache.py; here dmove.c's own copies of them, for a boot whose
early move could not write):

1. every move done: the move record's six bits, dm_ok() 1;
2. SAFE MODE's record copied to 0x5FFB00 byte for byte;
3. the DSP program's copy (header and its 2,048 sectors) copied to 0x5FF200 sector for sector;
4. our tunings' record sectors copied to 0x6E0400 (upstream's place), the stale record there with nothing copied
   over it cleared, the other sectors there (the inserts' old records) left as they were;
5. bank lists A: each whole list copied to 0x6E0600.. (body and header), the stale header with nothing over it
   cleared;
6. the wishes record: every whole cell of the old table filed again by its hash into the 92,160 cells at 0x5D8000,
   byte for byte; a broken cell not copied;
7. bank lists B: as 5, at 0x6F0800..;
8. the old places never written, and every write inside a new place or the move record;
9. a second power-on: the move record read, nothing copied, nothing written.
"""

from __future__ import annotations

import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "test"))

from test_wishes_c import cell_bytes, xxh32   # noqa: E402 -- the cells as store.c writes them, host-tested

DM, DM_MAGIC, DM_XOR = 0x5FFC00, 0x444E3256, 0x4D4F5645
INS_MARK = 0x5FF102
SAFE_OLD, SAFE_NEW = 0x6E0300, 0x5FFB00
DSP_OLD, DSP_NEW, DSP_N = 0x6E8000, 0x5FF200, 1 + 2048
TUNE_OLD, TUNE_NEW, TUNE_N = 0x6E0600, 0x6E0400, 256
SPAN, BL_N = 464, 2 * 64 * 464
BLA_OLD, BLA_NEW, BLB_OLD, BLB_NEW = 0x5E0000, 0x6E0600, 0x5F0000, 0x6F0800
WISH_OLD, WISH_OLD_N, WISH_NEW, WISH_NEW_N = 0x6F0800, 59392, 0x5D8000, 92160
NEW_PLACES = ((SAFE_NEW, SAFE_NEW + 1), (DSP_NEW, DSP_NEW + DSP_N), (TUNE_NEW, TUNE_NEW + TUNE_N),
              (BLA_NEW, BLA_NEW + BL_N), (BLB_NEW, BLB_NEW + BL_N), (WISH_NEW, WISH_NEW + WISH_NEW_N), (DM, DM + 1))
OLD_PLACES = ((SAFE_OLD, SAFE_OLD + 1), (DSP_OLD, DSP_OLD + DSP_N), (TUNE_OLD, TUNE_OLD + TUNE_N),
              (BLA_OLD, BLA_OLD + BL_N), (BLB_OLD, BLB_OLD + BL_N), (WISH_OLD, WISH_OLD + WISH_OLD_N))


def u32s(*w) -> bytes:
    return struct.pack(f">{len(w)}I", *w).ljust(512, b"\0")


def csum(b: bytes) -> int:
    a, s = 1, 0
    for x in b:
        a = (a + x) & 0xFFFFFFFF
        s = (s + a) & 0xFFFFFFFF
    return ((s << 16) & 0xFFFFFFFF) ^ a


def bl_header(p: int, seq: int, gen: int = 1) -> bytes:
    h = bytearray(struct.pack(">11I", 0x444E3242, 1, p, seq, gen, 0x1234, 0, 0, 0, 0, 0))
    h += struct.pack(">I", csum(bytes(h)) ^ 0x424C4B31)
    return bytes(h).ljust(512, b"\0")


def run(cx):
    m, call, disk, io, syms = cx["machine"], cx["call"], cx["disk"], cx["io"], cx["syms"]
    facts, notes = {}, {}
    wlog = []

    def u32(name):
        return struct.unpack(">I", m.read(syms[name], 4))[0]

    def put(name, v):
        m.write(syms[name], struct.pack(">I", v))

    def sectors(log):
        return [s + k for s, d in log for k in range(len(d) // 512)]

    def junk(seed, n=512):
        return bytes((seed * 131 + k * 7) & 0xFF for k in range(n))

    disk.clear()
    disk[INS_MARK] = u32s(0x444E324D, 0x444E324D ^ 0xFFFFFFFF, 0)          # the inserts moved (v0.69.1)
    # SAFE MODE's record, the DSP copy (its header, three data sectors of 2,048, the last one)
    disk[SAFE_OLD] = u32s(0x444E3242, 1, 0x12345678, 0, 0, 0, 0, 0xCAFEF00D)
    disk[DSP_OLD] = u32s(0x444E3743, 1, 300_000, 0xABCDEF01) + b""
    for k in (1, 2, 1000, 2048):
        disk[DSP_OLD + k] = junk(k)
    # our tunings: three records; a stale one at the new place with none over it; the inserts' old record there
    tune = {3: u32s(0x444E3254, 1, 1, 7), 14: u32s(0x444E3254, 1, 7, 2), 255: u32s(0x444E3254, 1, 127, 9)}
    for k, b in tune.items():
        disk[TUNE_OLD + k] = b
    disk[TUNE_NEW + 40] = u32s(0x444E3254, 1, 20, 1)                      # an upstream record, never ours
    ins_old = u32s(0x444E3249, 1, 5, 3)
    disk[TUNE_NEW + 10] = ins_old                                          # (the inserts' old record 5)
    # bank lists: A, project 3 copy 0 whole; B, project 70 copy 1 whole; a broken header (A, project 4 copy 0);
    # an upstream-looking header at the new place of A's project 9 copy 1 with nothing to copy over it
    def put_list(base, i, c, p):
        at = base + SPAN * (2 * i + c)
        disk[at] = bl_header(p, 5)
        for k in (1, 2, SPAN - 1):
            disk[at + k] = junk(p * 10 + k)
        return at
    a3 = put_list(BLA_OLD, 3, 0, 3)
    b70 = put_list(BLB_OLD, 70 - 64, 1, 70)
    bad = bytearray(bl_header(4, 1))
    bad[44] ^= 1
    disk[BLA_OLD + SPAN * 8] = bytes(bad)
    stale_bl = BLA_NEW + SPAN * (2 * 9 + 1)
    disk[stale_bl] = bl_header(9, 3)
    # the wishes record: five cells filed by the old table's rule, one broken
    recs = [bytes([i]) * (20 + 11 * i) for i in range(5)]
    for r in recs:
        disk[WISH_OLD + xxh32(r, 0x57495348) % WISH_OLD_N] = cell_bytes(r)
    broken = bytearray(cell_bytes(b"\x77" * 40))
    broken[100] ^= 1
    disk[WISH_OLD + 9] = bytes(broken)
    before = dict(disk)

    io["log"] = wlog
    put("dm_bits", 0)
    put("dm_tried", 0)
    call("dm_run")
    ok = struct.unpack(">i", m.read(syms["dm_bits"], 4))[0] == 0x3F
    dmrec = disk.get(DM, b"")
    bits = struct.unpack(">4I", dmrec[:16]) if len(dmrec) >= 16 else None
    notes["1"] = {"dm_bits": u32("dm_bits"), "runs": u32("dm_runs"), "fails": u32("dm_fails"),
                  "copied": list(struct.unpack(">6I", m.read(syms["dm_copied"], 24))), "record": dmrec[:16].hex()}
    facts["1 every move done: the move record's six bits"] = (
        ok and bits is not None and bits[0] == DM_MAGIC and bits[2] == 0x3F and bits[3] == 0x3F ^ DM_XOR)
    facts["2 SAFE MODE's record copied to 0x5FFB00"] = disk.get(SAFE_NEW) == before[SAFE_OLD]
    facts["3 the DSP program's copy copied to 0x5FF200, sector for sector"] = all(
        disk.get(DSP_NEW + k, bytes(512)) == before.get(DSP_OLD + k, bytes(512)) for k in range(DSP_N))
    facts["4 our tunings at 0x6E0400 (upstream's place): records copied, the stale one cleared, the rest as it was"] = (
        all(disk.get(TUNE_NEW + k) == b for k, b in tune.items()) and disk.get(TUNE_NEW + 40) == bytes(512)
        and disk.get(TUNE_NEW + 10) == ins_old)
    a3n = a3 - BLA_OLD + BLA_NEW
    facts["5 bank lists A at 0x6E0600: the whole list copied, the broken one not, the stale header cleared"] = (
        all(disk.get(a3n + k, bytes(512)) == before.get(a3 + k, bytes(512)) for k in range(SPAN))
        and disk.get(BLA_NEW + SPAN * 8, bytes(512)) == bytes(512) and disk.get(stale_bl) == bytes(512))
    cells_ok = all(disk.get(WISH_NEW + xxh32(r, 0x57495348) % WISH_NEW_N) == cell_bytes(r) for r in recs)
    newcells = [s for s in disk if WISH_NEW <= s < WISH_NEW + WISH_NEW_N and disk[s][:4] == b"DN2W"]
    facts["6 the wishes record: every whole cell filed again by its hash into 92,160 cells, the broken one not"] = (
        cells_ok and len(newcells) == len(recs))
    b70n = b70 - BLB_OLD + BLB_NEW
    facts["7 bank lists B at 0x6F0800: the whole list copied"] = all(
        disk.get(b70n + k, bytes(512)) == before.get(b70 + k, bytes(512)) for k in range(SPAN))
    wrote = sectors(wlog)
    old_w = [hex(s) for s in wrote if any(a <= s < b for a, b in OLD_PLACES) and not any(a <= s < b for a, b in NEW_PLACES)]
    out_w = [hex(s) for s in wrote if not any(a <= s < b for a, b in NEW_PLACES)]
    notes["8"] = {"old": old_w[:6], "outside": out_w[:6], "writes": len(wrote)}
    unchanged = all(disk.get(s) == before[s] for s in before
                    if any(a <= s < b for a, b in OLD_PLACES) and not any(a <= s < b for a, b in NEW_PLACES))
    facts["8 the old places no new place covers never written (their bytes as they were), every write in a new place or the record"] = (
        not old_w and not out_w and unchanged)

    n9 = len(wlog)
    put("dm_bits", 0)
    put("dm_tried", 0)
    call("dm_run")
    facts["9 a second power-on: the move record read, every bit, nothing written"] = (
        u32("dm_bits") == 0x3F and len(wlog) == n9)
    io.pop("log", None)
    disk.clear()
    return {"facts": facts, "notes": notes, "ok": all(facts.values())}
