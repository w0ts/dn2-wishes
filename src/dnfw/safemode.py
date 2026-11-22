"""SAFE MODE's unpatch table and its checks (docs/safe-mode.md).

The table holds stock 1.12's bytes for every run of MAIN OS (inside stock's length) that a build changed, except
the two runs the platform loader is running in when SAFE MODE's kernel applies the table (`NEVER`). Format:

    per run   u16 gap (from the end of the previous run; 0xFFFF then a u32 when it is 0xFFFF or more),
              u8 length (1..255; a longer run is split), the stock bytes
    end       0xFFFF, 0xFFFFFFFF

`apply` is the kernel's walk in Python (csrc/safemode/kernel.c `table`), for the build's checks and the gate's
`safeboot-table` step. Pure Python: the in-browser patcher runs it too.
"""

from __future__ import annotations

import struct
import zlib

BASE = 0x40000400
STOCK_LEN = 0x0030C580                    # stock 1.12's MAIN OS
# runs never restored: the start-up call the loader returns into, and the loader's own cave (dnfw.mods.platform)
NEVER = ((0x4000053E, 8, "the start-up call (jsr loader; nop): the loader returns to 0x40000544"),
         (0x4028DFAE, 138, "the platform loader's cave: the loader is running there"))
# the overrides SAFE MODE writes after the table, over these stock bytes (kernel.c `sites`, and boot flag bit 0)
OVERRIDES = ((0x400CF73A, "4eb940136820", "O1: the DSP upload's depack -> sm_refuse7"),
             (0x4002E464, "4eb94011d5d4", "O2: the UI loop's isDirty -> sm_isdirty (the question)"),
             (0x400BB4A0, "23c0405ce858", "O4: the empty project not written over the working state"))
FLAGS_VA = 0x40287A60
END = b"\xff\xff\xff\xff\xff\xff"


class TableError(ValueError):
    """A table that does not decode, or reaches where it must not."""


def _never(off: int, n: int) -> bool:
    va = BASE + off
    return any(va < s + ln and s < va + n for s, ln, _ in NEVER)


def runs(stock: bytes, built: bytes) -> list[tuple[int, int]]:
    """[(offset, length)] where BUILT differs from STOCK inside stock's length, the NEVER runs left out"""
    out, i, n = [], 0, min(len(stock), STOCK_LEN)
    while i < n:
        if built[i] == stock[i]:
            i += 1
            continue
        j = i
        while j < n and built[j] != stock[j]:
            j += 1
        for k in range(i, j):                  # split around the NEVER runs, byte by byte (they are short)
            if _never(k, 1):
                continue
            if out and out[-1][0] + out[-1][1] == k:
                out[-1] = (out[-1][0], out[-1][1] + 1)
            else:
                out.append((k, 1))
        i = j
    return out


def encode(stock: bytes, rs: list[tuple[int, int]]) -> bytes:
    t, pos = bytearray(), 0
    for off, n in rs:
        while n:
            ln = min(255, n)
            gap = off - pos
            t += struct.pack(">HI", 0xFFFF, gap) if gap >= 0xFFFF else struct.pack(">H", gap)
            t.append(ln)
            t += stock[off:off + ln]
            pos, off, n = off + ln, off + ln, n - ln
    return bytes(t + END)


def build_table(stock: bytes, built: bytes) -> bytes:
    if len(stock) != STOCK_LEN:
        raise TableError(f"stock MAIN OS is {len(stock):,} B, not 1.12's {STOCK_LEN:,}")
    return encode(stock, runs(stock, built))


def decode(table: bytes) -> list[tuple[int, bytes]]:
    """-> [(offset, stock bytes)]; refuses what the kernel would refuse"""
    out, pos, i = [], 0, 0
    while True:
        if i + 2 > len(table):
            raise TableError("cut before the end marker")
        gap = struct.unpack_from(">H", table, i)[0]
        i += 2
        if gap == 0xFFFF:
            if i + 4 > len(table):
                raise TableError("cut inside a long gap")
            gap = struct.unpack_from(">I", table, i)[0]
            i += 4
            if gap == 0xFFFFFFFF:
                if i != len(table):
                    raise TableError("bytes after the end marker")
                return out
        if i >= len(table):
            raise TableError("cut before a length")
        n = table[i]
        i += 1
        pos += gap
        if not n or i + n > len(table) or pos + n > STOCK_LEN:
            raise TableError(f"a run at +0x{pos:x} of {n} B is out of bounds")
        if _never(pos, n):
            raise TableError(f"a run at 0x{BASE + pos:08x} reaches a run that is never restored")
        out.append((pos, table[i:i + n]))
        i += n
        pos += n


def apply(built: bytes, table: bytes) -> bytes:
    content = bytearray(built[:STOCK_LEN])
    for off, data in decode(table):
        content[off:off + len(data)] = data
    return bytes(content)


def crc(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def check(stock: bytes, built: bytes, table: bytes) -> list[tuple[bool, str, str]]:
    """The table against this build: what SAFE MODE runs is stock 1.12, except exactly the NEVER runs."""
    out = []
    try:
        restored = apply(built, table)
    except TableError as exc:
        return [(False, "the table decodes", str(exc))]
    out.append((True, "the table decodes", f"{len(decode(table)):,} runs, {len(table):,} B"))
    diff = [i for i in range(STOCK_LEN) if restored[i] != stock[i]]
    allowed = all(_never(i, 1) for i in diff)
    left = sorted({next(s for s, ln, _ in NEVER if s <= BASE + i < s + ln) for i in diff}) if allowed else []
    out.append((allowed, "table applied = stock 1.12 except the never-restored runs",
                f"{len(diff)} B differ, all inside {[hex(x) for x in left]}" if allowed
                else f"{len(diff)} B differ outside them, first 0x{BASE + next(i for i in diff if not _never(i, 1)):08x}"))
    for va, want, what in OVERRIDES:
        at = va - BASE
        got = restored[at:at + 6].hex()
        out.append((got == want, f"{what}: stock under the override", got))
    return out
