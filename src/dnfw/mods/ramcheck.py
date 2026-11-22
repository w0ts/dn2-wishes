"""Every address above BSS a mod's bytes name must be RAM the mod declares.

The RAM above BSS (`0x466b74d0`..`0x48000000`) belongs to no one: the firmware
never addresses it, so every mod that uses it picks its addresses by hand and
declares them (`ram()`), and the platform compares the declarations. A
declaration that misses a range is invisible to that comparison. On 2026-09-30
lfo4's LFO state arrays at `0x46700000` were written by its edits but not
declared, the boot screen's stamp was placed on top of them, and the instrument
raised V04 at `0x46700000`.

So this reads the bytes instead of trusting the list. It applies the mod alone
to stock, takes every changed run of MAIN OS and every `CODE` chunk image, and
finds each word-aligned 32-bit value in that window. A value is accounted for
when it falls inside the mod's own `ram()` or inside the platform's data window.
Two idioms name an address just outside a range without using it: a base
minus a field offset (lfo4's table accessors hold `0x468fffcc`, the relocated
table less 52, as stock holds its own table less 52) and an end pointer a loop
compares against. So a value within `SLACK` bytes of a declared range counts as
that range's. The scan stops at `0x47000000`: nothing is placed above it, and
the stack descends from `0x48000000`.

What is left is reported: a missing declaration, or bytes that only look like an
address (two instructions, ASCII). A mod lists the second kind in `NOT_RAM`,
each with the place it was disassembled at, so the next change to the mod is
checked afresh rather than waved through.

One subject: that comparison. Applying the mod is the caller's business.
"""

from __future__ import annotations

import struct

from . import RAM, platform
from ..patch import area

LO, HI = 0x466B74D0, 0x47000000           # OS 1.11's BSS end
LO_112 = 0x466B84D0                         # OS 1.12's (its BSS moved +0x1000: scripts/port_os112.py)
SLACK = 64


def _lo(stock: bytes) -> int:
    """the end of the stock image's own BSS: 1.12's, or 1.11's (2026-11-17: LO was 1.11's for every image)"""
    return LO_112 if platform.spec_for(stock) is platform.SPEC else LO


def _words(data: bytes, base: int, lo_ram: int = LO) -> list[tuple[int, int]]:
    """(address of the word, its value) for every value in the window."""
    out = []
    for at in range(0, len(data) - 3, 2):
        v = struct.unpack_from(">I", data, at)[0]
        if lo_ram <= v < HI:
            out.append((base + at, v))
    return out


def named(stock: bytes, content: bytes) -> list[tuple[int, int]]:
    """Addresses above BSS that CONTENT names and STOCK does not."""
    found = []
    lo_ram = _lo(stock)
    n = len(stock)
    i = 0
    while i < n:
        if stock[i] == content[i]:
            i += 1
            continue
        j = i
        while j < n and stock[j] != content[j]:
            j += 1
        lo, hi = max(0, i - 3) & ~1, min(n, j + 3)        # a word straddling the run
        found += [(platform.BASE + a, v) for a, v in _words(bytes(content[lo:hi]), lo, lo_ram)
                  if not (lo_ram <= struct.unpack_from(">I", stock, a)[0] < HI)]
        i = j
    if len(content) > platform.spec_for(content)["stock_length"]:
        for cid, data in platform.split(content)[1]:
            if cid == area.CODE:
                code = area.CodeChunk.unpack(data)
                found += _words(code.image, code.load, lo_ram)
    return sorted(set(found))


def undeclared(stock: bytes, content: bytes, ram, not_ram=(), spans=()) -> list[tuple[int, int]]:
    """(where, value) for each named address no declared range holds.

    NOT_RAM: the places (`where`) a mod has shown not to hold an address.
    SPANS: a mod's `word_spans()` (`not_addresses`): its code spans, read by disassembly, and its opaque ones."""
    ranges = [(x.start, x.end) for x in list(ram) + platform.ram() if x.section == RAM]
    skip = set(not_ram)
    found = [(at, v) for at, v in named(stock, content)
             if at not in skip and not any(lo - SLACK <= v < hi + SLACK for lo, hi in ranges)]
    return not_addresses(found, content, spans) if spans and found else found


# 2026-11-17: a mod whose code is generated (waverider's C, a new layout every build) cannot list its non-addresses
# by hand. Its `word_spans()` says where its chunks hold code and where data no ColdFire instruction reads as
# a pointer, and a word is dropped only when that is shown, never when it is merely unknown:
#   "code" (lo, hi): disassembled from lo (compiled code: a linear sweep is in step); a word inside it counts
#     only when the instruction holding it names the value as an operand (an absolute address, an immediate);
#     one that starts an instruction (0x4680.. is not.l %d0) or sits in another operand is not an address;
#   "opaque" (lo, hi): bytes another processor reads (the DSP's tables): no ColdFire address in them;
#   "pointer" (p, p + 4): one of the link's 32-bit absolute relocations in our C's data, a pointer the linker filled
#     in. A word that overlaps it but does not start on it is pieces of that pointer (its halves with a neighbour's,
#     a struct's other fields or padding), never an address, and is not counted; the pointer itself is checked as
#     anywhere (its target must be declared). The User approved this rule 2026-11-18 as the root fix for the seam
#     false alarms (it replaces the pointer-table-only rule: fxp_delay's 6-byte {label, def} entries read
#     0x468c0000 at a pointer's low half + def + padding);
#   anywhere else: a word inside a printable run of 6 bytes or more, or of 4 or more ending in NUL (a C string,
#     "Flex\0"), is text, not an address.
def not_addresses(found, content: bytes, spans) -> list[tuple[int, int]]:
    images = [(c.load, c.image) for cid, data in platform.split(content)[1] if cid == area.CODE
              for c in [area.CodeChunk.unpack(data)]]
    named_in_code = {}
    for lo, hi, kind in spans:
        if kind == "code" and any(lo <= at < hi for at, _ in found):
            named_in_code.update(_operands(images, lo, hi))
    pointers = {lo for lo, _hi, kind in spans if kind == "pointer"}
    out = []
    for at, v in found:
        if any(p in pointers for p in range(at - 3, at + 4) if p != at):
            continue                            # pieces of a relocated pointer (the User, 2026-11-18)
        hit = next(((lo, k) for lo, hi, k in spans if k != "pointer" and lo <= at and at + 4 <= hi), None)
        span = hit[1] if hit else None
        if span == "opaque":
            continue
        if span == "code":
            if v in named_in_code.get(at, ()):
                out.append((at, v))
            continue
        if not _in_text(images, at):
            out.append((at, v))
    return out


def _bytes_at(images, lo: int, hi: int) -> bytes | None:
    for load, img in images:
        if load <= lo and hi <= load + len(img):
            return img[lo - load:hi - load]
    return None


def _operands(images, lo: int, hi: int) -> dict[int, set[int]]:
    """{where: {values}}: each 32-bit value an instruction in [lo, hi) carries as an operand, by its place"""
    import re                                                    # noqa: PLC0415
    from ..image import objdump                                  # noqa: PLC0415
    data = _bytes_at(images, lo, hi)
    if data is None:
        raise ValueError(f"no chunk holds the code span {lo:#010x}..{hi:#010x}")
    out: dict[int, set[int]] = {}
    for ins in objdump.disassemble(data, lo):
        vals = {int(h, 16) for h in re.findall(r"0x([0-9a-fA-F]{8})\b", ins.text)}
        vals |= {int(d) & 0xFFFFFFFF for d in re.findall(r"#(-?\d{6,})", ins.text)}
        for k in range(ins.address + 2, ins.address + len(ins.data) - 3, 2):
            v = struct.unpack_from(">I", ins.data, k - ins.address)[0]
            if v in vals:
                out.setdefault(k, set()).add(v)
    return out


def _in_text(images, at: int) -> bool:
    """the 4 bytes at AT lie in a run of printable ASCII 6 bytes or longer"""
    for load, img in images:
        if load <= at < load + len(img):
            i = at - load
            if not all(32 <= b < 127 for b in img[i:i + 4]):
                return False
            a, b = i, i + 4
            while a > 0 and 32 <= img[a - 1] < 127:
                a -= 1
            while b < len(img) and 32 <= img[b] < 127:
                b += 1
            return b - a >= 6 or (b - a >= 4 and b < len(img) and img[b] == 0)   # or a C string ("Flex\0")
    return False
