"""The gate's static SAFE MODE step (docs/safe-mode.md): what SAFE MODE would run on this build is stock 1.12.

    python scripts/safeboot_table.py STOCK.syx BUILD.syx [--json OUT]

Checks, on the build's own bytes:
  - the kernel is the area's FIRST CODE chunk, at SM_LOAD, its code exactly safemode_code.json's (the sources'),
    no BSS, its init the spec's, the chunk inside SAFE MODE's RAM;
  - its head: magic, the table where the head says, its CRC-32, the build id of this build;
  - the table applied to the build's MAIN OS gives stock 1.12 byte for byte, except exactly the two runs the loader
    is running in (dnfw.safemode.NEVER);
  - each override site (O1, O2, O4) holds stock's bytes once the table is applied;
  - the start-up call and the loader's cave are the platform's (never restored, so they must be what the loader is).
Exit 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dnfw import safemode as T                       # noqa: E402
from dnfw.cli.files import read_image                # noqa: E402
from dnfw.firmware.load import load                  # noqa: E402
from dnfw.mods import platform, safemode as M        # noqa: E402


def checks(stock3: bytes, sec3: bytes) -> list[tuple[bool, str, str]]:
    out = []
    base, chunks = platform.split(sec3)
    codes = [(i, platform.area.CodeChunk.unpack(d)) for i, (cid, d) in enumerate(chunks) if cid == platform.area.CODE]
    if not codes:
        return [(False, "the area has CODE chunks", "none")]
    first = codes[0][1]
    out.append((first.load == M.SPEC["load"], "the kernel is the first CODE chunk", f"first at 0x{first.load:08x}"))
    k = next((c for _, c in codes if c.load == M.SPEC["load"]), None)
    if k is None:
        return out + [(False, "the kernel chunk is in the area", "not found")]
    code = bytes.fromhex(M.SPEC["code"])
    out.append((k.image[20:len(code)] == code[20:], "the kernel's code is safemode_code.json's",
                f"{len(code):,} B (the head's first 20 B are the build's)"))
    out.append((k.bss == 0 and k.init == M.SPEC["init"], "no BSS, the spec's init entry",
                f"bss {k.bss}, init 0x{k.init:08x}"))
    out.append((M.SM_RAM + 0x100 <= k.load and k.load + len(k.image) <= M.SM_RAM + M.SM_BYTES,
                "the chunk inside SAFE MODE's RAM", f"0x{k.load:08x}..0x{k.load + len(k.image):08x}"))
    magic, build, off, n, crc = struct.unpack_from(M.HEAD, k.image, 0)
    table = k.image[off:off + n]
    out.append((magic == M.MAGIC and off == len(code) and off + n <= len(k.image) < off + n + 4, "the head: magic, the table's place",
                f"table at +{off}, {n:,} B"))
    out.append((T.crc(table) == crc, "the table's CRC-32", f"0x{crc:08x}"))
    others = [c for c in chunks if not (c[0] == platform.area.CODE and platform.area.CodeChunk.unpack(c[1]).load
                                         == M.SPEC["load"])]
    want_build = T.crc(base + b"".join(cid + data for cid, data in others))
    out.append((build == want_build, "the build id is this build's", f"0x{build:08x}"))
    out += T.check(stock3, base, table)
    spec = platform.SPEC
    at = spec["calls_va"] - platform.BASE
    out.append((base[at:at + len(spec["hook"]) // 2].hex() == spec["hook"], "the start-up call is the platform's",
                f"0x{spec['calls_va']:08x}"))
    link = spec["link_va"] - platform.BASE
    loader = bytes.fromhex(spec["loader"])
    out.append((base[link:link + len(loader)] == loader, "the loader's cave holds the platform loader",
                f"0x{spec['link_va']:08x}, {len(loader)} B"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stock", type=pathlib.Path)
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()
    stock3 = load(read_image(a.stock)).container.find(3).unpack()
    sec3 = load(read_image(a.build)).container.find(3).unpack()
    res = checks(stock3, sec3)
    for ok, what, detail in res:
        print(("  ok    " if ok else "  FAIL  ") + what + (f"  ({detail})" if detail else ""))
    bad = [w for ok, w, _ in res if not ok]
    print(f"{len(res) - len(bad)}/{len(res)} checks pass" + ("" if not bad else ": DO NOT FLASH"))
    if a.json:
        a.json.write_text(json.dumps([{"ok": ok, "what": w, "detail": d} for ok, w, d in res], indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
