"""The wishes record in the target build (csrc/wishes, docs/wishes-record.md), read from the committed ColdFire code
(src/dnfw/mods/waverider_code.json, which the gate's code-fresh step ties to the sources):

- memcpy and memset stay stock (Overbridge's path); every reference to them names the wishes stub but the four
  in Overbridge's code, and each stub goes on into the stock routine;
- the loader's and saver's sites are each a jump to its stub, over exactly the stock bytes it was read from, and
  each stub replays exactly the bytes its jump displaced and goes on where stock goes on;
- the load site, which also holds waverider's machine-type bound, has one owner: no second edit touches it;
- the RAM the C addresses is the RAM the mod declares.

The C's behaviour is test_wishes_c.py's (compiled for the host)."""

from __future__ import annotations

import pathlib
import re
import struct

from dnfw.mods import waverider
from dnfw.waverider import coldfire as CF
from dnfw.waverider import pages as PG

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = waverider.SPEC
CODE = bytes.fromhex(SPEC["c_chunk"]["code"])
LOAD = SPEC["c_chunk"]["load"]
LAYOUT = SPEC["layout"]
SITES = {  # site, its stock bytes, the stub, the jump's length
    "load": (CF.WISH_LOAD_SITE, CF.WISH_LOAD_STOCK, "wish_load", 6),
    "save": (CF.WISH_SAVE_SITE, CF.WISH_SAVE_STOCK, "wish_save", 8),
}
ROUTINES = {CF.WISH_MEMCPY: "wish_memcpy_stub", CF.WISH_MEMSET: "wish_memset_stub"}


def code_at(va: int, n: int) -> bytes:
    return CODE[va - LOAD:va - LOAD + n]


def edits_over(va: int, n: int) -> list[dict]:
    return [e for e in SPEC["edits"] if e["va"] < va + n and e["va"] + len(e["new"]) // 2 > va]


def test_each_site_is_one_jump_over_its_stock_bytes():
    for name, (site, stock, stub, n) in SITES.items():
        found = edits_over(site, n)
        assert len(found) == 1, (name, found)
        e = found[0]
        assert e["va"] == site and bytes.fromhex(e["stock"]) == stock, name
        new = bytes.fromhex(e["new"])
        assert new[:2] == bytes.fromhex("4ef9") and struct.unpack(">I", new[2:6])[0] == LAYOUT[stub + "_stub"]
        assert new[6:] == (bytes.fromhex("4e71") if n == 8 else b""), name


def test_each_stub_replays_what_it_displaced_and_goes_on_after_it():
    for name, (site, stock, stub, n) in SITES.items():
        at = LAYOUT[stub + "_displaced"]
        want = stock if name == "save" else stock[:4] + bytes([0x74, CF.TYPES_LAST + 2])
        assert code_at(at, len(want)) == want, name
        assert code_at(at + len(want), 6) == bytes.fromhex("4ef9") + struct.pack(">I", site + n), name


def test_the_load_bound_has_one_owner():
    assert CF.LOAD_BOUND == CF.WISH_LOAD_SITE + 4
    assert edits_over(CF.LOAD_BOUND, 2) == edits_over(CF.WISH_LOAD_SITE, 6)
    assert CF.TYPES_LAST + 2 <= 127                                    # a moveq


def test_the_ram_the_c_names_is_declared():
    h = (ROOT / "csrc" / "wishes" / "wish.h").read_text()
    n = {k: int(v.rstrip("u"), 0) for k, v in re.findall(r"#define (WISH_\w+) (\d+u)\b", h)}
    end = (4 * n["WISH_N"] + 2 * n["WISH_N"] * 2 + 2 * n["WISH_CACHE"] + 512 * n["WISH_PEND"] + 512
           + 6 * n["WISH_N"] + n["WISH_ENTRY"] * n["WISH_N"])
    assert end == PG.WISH_BYTES
    ext = [e for e in waverider.ram() if e.start == PG.WISH_RAM]
    assert len(ext) == 1 and ext[0].length == PG.WISH_BYTES
    for other in waverider.ram():
        if other.start != PG.WISH_RAM:
            assert not ext[0].overlaps(other), other


def test_the_memcpy_stub_costs_two_instructions_while_nothing_is_tracked():
    at = LAYOUT["wish_memcpy_stub"]
    n_at = LAYOUT["wish_n"]
    assert code_at(at, 6) == bytes.fromhex("4ab9") + struct.pack(">I", n_at)    # tst.l wish_n
    assert code_at(at + 6, 1) == b"\x67"                                         # beq.s on into stock's memcpy


def test_memcpy_and_memset_stay_stock():
    for routine in ROUTINES:
        assert edits_over(routine, 16) == []


def test_every_reference_but_overbridges_names_the_stub():
    for routine, stub in ROUTINES.items():
        ref = [e for e in SPEC["edits"] if bytes.fromhex(e["stock"]) == struct.pack(">I", routine)]
        assert all(bytes.fromhex(e["new"]) == struct.pack(">I", LAYOUT[stub]) for e in ref)
        kept = [va for va in CF.WISH_KEEP if routine == CF.WISH_MEMCPY]
        assert len(ref) == CF.WISH_REFS[routine] - len(kept)
        assert not {e["va"] for e in ref} & set(CF.WISH_KEEP)


def test_each_stub_goes_on_into_the_stock_routine():
    for routine, stub in ROUTINES.items():
        at = LAYOUT[stub]
        body = code_at(at, 64)
        assert bytes.fromhex("4ef9") + struct.pack(">I", routine) in body, stub
