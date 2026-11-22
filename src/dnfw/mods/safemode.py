"""SAFE MODE (docs/safe-mode.md): the kernel CODE chunk with its unpatch table, applied LAST.

After every other shipped mod has written MAIN OS, this one diffs it against stock 1.12 (`dnfw.safemode`), appends
the table to the kernel chunk (`safemode_code.json`, from `scripts/gen_safemode_code.py`: csrc/safemode/kernel.c
and question.c, linked at SM_LOAD), fills the kernel's head (the build id, the table's place, length and CRC-32)
and places the chunk FIRST among the area's CODE chunks, so the platform loader calls its init before any other.

The normal-boot half (csrc/safemode/normal.c) is in waverider's page-renderer chunk; it finds the kernel by its
head's magic and does nothing without it.
"""

from __future__ import annotations

import json
import pathlib
import struct

from . import RAM, Extent, ModError, Result
from . import platform
from .. import safemode as T

ID = "safemode"
NAME = "SAFE MODE"
SUMMARY = "STOP held alone at power-on: stock 1.12 put back from the unpatch table, and an OS update over USB (docs/safe-mode.md)."
DEVICE = 0x15                      # Digitone II
SECTION = 3
APPLY_LAST = True                          # the table must see every other mod's bytes
SPEC = json.loads((pathlib.Path(__file__).with_name("safemode_code.json")).read_text())
SM_RAM = 0x476F8000                        # dnfw.waverider.pages.SM_RAM (asserted there against its neighbours)
SM_BYTES = 0x8000
HEAD = ">5I"                               # magic, build, table_off, table_len, table_crc (csrc/safemode/sm.h)
MAGIC = 0x534D4B31


def extents(firmware=None) -> list[Extent]:
    return platform.extents(1)             # the appended area (the platform owns it; shared by design)


def ram() -> list[Extent]:
    return [Extent(RAM, SM_RAM, SM_BYTES, "SAFE MODE: the RAM mark (256 B), then the kernel chunk", ID)]


def _stock(firmware) -> bytes:
    """stock 1.12's MAIN OS: the input image's own section 3 (mods apply stages the others' bytes over it)"""
    original = getattr(firmware, "_o", firmware)
    s = original.container.find(SECTION).unpack()
    if s is None or len(s) != T.STOCK_LEN:
        raise ModError("SAFE MODE needs stock Digitone II 1.12 as the input image (its MAIN OS is the table's source)")
    return s


def chunk(stock: bytes, built: bytes, others: list[tuple[bytes, bytes]]) -> tuple[bytes, dict]:
    """-> (the kernel CODE chunk, facts), for BUILT (MAIN OS without the area) and the area's OTHER chunks"""
    table = T.build_table(stock, built)
    image = bytearray(bytes.fromhex(SPEC["code"]))
    if struct.unpack_from(">I", image, 0)[0] != MAGIC:
        raise ModError("safemode_code.json: the kernel's head is not at its first bytes")
    if SPEC["bss"]:
        raise ModError("safemode_code.json: the kernel has BSS; the table is appended where it would be")
    off = len(image)
    build = T.crc(built + b"".join(cid + data for cid, data in others))
    struct.pack_into(HEAD, image, 0, MAGIC, build, off, len(table), T.crc(table))
    image += table
    if SPEC["load"] + len(image) > SM_RAM + SM_BYTES:
        raise ModError(f"the kernel and its table ({len(image):,} B) pass SAFE MODE's RAM")
    code = platform.area.CodeChunk(SPEC["load"], bytes(image), 0, SPEC["init"]).pack()
    return code, {"table_bytes": len(table), "runs": len(T.decode(table)), "build": build}


def apply(firmware) -> Result:
    cf = firmware.container.find(SECTION)
    if cf is None:
        raise ModError("image has no MAIN OS")
    base, chunks = platform.split(cf.unpack())
    if any(cid == platform.area.CODE and platform.area.CodeChunk.unpack(d).load == SPEC["load"] for cid, d in chunks):
        raise ModError("SAFE MODE's kernel is already in this image")
    code, facts = chunk(_stock(firmware), base, chunks)
    data = [c for c in chunks if c[0] != platform.area.CODE]
    codes = [c for c in chunks if c[0] == platform.area.CODE]
    content = platform.join(base, data + [(platform.area.CODE, code)] + codes)   # the kernel: first CODE chunk
    return Result(payloads={SECTION: content},
                  extents=extents(firmware),
                  notes=[f"SAFE MODE: kernel at 0x{SPEC['load']:08x}, unpatch table {facts['runs']:,} runs, "
                         f"{facts['table_bytes']:,} B, build id 0x{facts['build']:08x}"])
