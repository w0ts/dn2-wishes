"""Package the LFO4 release build as a `dnfw` mod.

    python scripts/gen_lfo4_code.py

LFO4 is C (`csrc/lfo4/`), compiled and linked by `build_lfo4_browser.py`. The
C stays the source; this runs that build's own composition (`RELEASE`) on the
user's stock 1.12 image and writes what it changed as data -- the same pattern
as `gen_lfo_waves_code.py`:

- `edits`: every in-image run the build changes, with the **stock bytes it
  expects** (a guard: the mod refuses an image that differs) and the new bytes;
- `blob`: the appended area (loader, compiled C, relocated parameter table),
  **with the table blanked**. The relocated table is 320 stock records plus
  LFO4's ten, which are LFO3's with five fields rewritten; all of it is rebuilt
  from the user's own image at apply time (`dnfw.patch.paramtable.records`,
  `dnfw.patch.lfo4records.build`), so no stock table contents ship.

It then applies the result to stock and checks it is **byte-identical** to the
build it came from, so the mod is exactly what was gated.

Outputs `src/dnfw/mods/lfo4_code.json` and `site/js/mods/lfo4-code.js`, the
same data for the browser tool page (`site/js/mods/lfo4.js` applies it).
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_lfo4_bridge as bridge                         # noqa: E402
import build_lfo4_browser as release                       # noqa: E402
import build_lfo4_table as table                           # noqa: E402
from dnfw.patch import area, lfo4records, paramtable       # noqa: E402

OUT_JSON = ROOT / "src/dnfw/mods/lfo4_code.json"
OUT_JS = ROOT / "site/js/mods/lfo4-code.js"


def main() -> int:
    stock = bridge.load(bridge.read_image(bridge.STOCK)).container.find(bridge.MAIN_OS).unpack()
    # The mod composes through the platform's data (src/dnfw/mods/platform_code.json, written by
    # gen_platform_code.py). A tree whose platform data is another OS's cannot apply the mod at all, so the parity
    # check below would fail; say why before building (2026-11-14: a clean tree at 1b38bb81 still had 1.11's).
    from dnfw.mods import platform
    if platform.STOCK_LENGTH != len(stock):
        raise SystemExit(f"src/dnfw/mods/platform_code.json is {platform.SPEC.get('os', '?')}'s "
                         f"({platform.STOCK_LENGTH:,} B MAIN OS) but stock is {len(stock):,} B: "
                         "run scripts/gen_platform_code.py first, then this")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        rc = bridge.main(out=tmp / "build", syx=tmp / "lfo4.syx", **release.RELEASE)
        if rc:
            return rc
        content = (tmp / "build/section_3_MAIN_OS.bin").read_bytes()
        built_syms = json.loads((tmp / "build/symbols.json").read_text())

    n = len(stock)
    edits, i = [], 0
    while i < n:
        if stock[i] == content[i]:
            i += 1
            continue
        j = i
        while j < n and stock[j] != content[j]:
            j += 1
        edits.append({"va": release.BASE + i, "stock": stock[i:j].hex(), "new": content[i:j].hex()})
        i = j

    blob = bytearray(content[n:])
    records = table._records(stock)
    at = bytes(blob).find(records)
    if at < 0 or bytes(blob).find(records, at + 1) >= 0:
        raise SystemExit("the relocated table is not in the appended area exactly once")
    stock_part = paramtable.RECORD * (paramtable.COUNT + lfo4records.GROUP_SIZE)
    blob[at:at + stock_part] = bytes(stock_part)

    code = {
        "os": "Digitone II 1.12",
        "stock_length": n,
        "area_va": area.AREA_VA,
        "table_va": table.TABLE_VA,
        "table_offset": at,
        "table_records": paramtable.COUNT + lfo4records.GROUP_SIZE,
        # 2026-11-14 (docs/lfo-112-port.md 4.1): what our code calls in lfo4's chunk with DN2_LFO4 -- LFO4's values
        # go to and from the sound's wishes record through lfo4's own table
        "symbols": {k: int(built_syms[k], 16) for k in ("ext_find", "ext_set", "ext_drop", "ext_default", "lfo4_cascade")},
        "edits": edits,
        "blob": bytes(blob).hex(),
    }

    # Parity: the mod, applied to stock, is the build. Nothing is written until it holds.
    from dnfw.mods import lfo4
    lfo4.SPEC = code
    rebuilt = lfo4.compose(stock)
    # (2026-11-14: the mod leaves its two stored-sound hooks out, the wishes record's sites on our series: the build
    # it must reproduce is this one with those two edits back to stock's bytes)
    content = bytearray(content)
    for e in edits:
        if lfo4._store_hook(e):
            pos = e["va"] - release.BASE
            content[pos:pos + len(e["stock"]) // 2] = bytes.fromhex(e["stock"])
    content = bytes(content)
    if rebuilt != content:
        raise SystemExit("the packaged mod does not reproduce the build byte for byte")
    OUT_JSON.write_text(json.dumps(code, indent=1) + "\n", newline="\n")
    OUT_JS.write_text("// Generated by scripts/gen_lfo4_code.py -- do not edit by hand.\n"
                      "export const CODE = " + json.dumps(code, indent=1) + ";\n",
                      newline="\n")
    print(f"{len(edits)} edits ({sum(len(e['stock']) // 2 for e in edits):,} B), "
          f"appended {len(blob):,} B with the {stock_part:,} B table blanked at +{at:#x}; "
          f"reproduces the build byte for byte")
    print(f"  wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"  wrote {OUT_JS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
