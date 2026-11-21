#!/usr/bin/env python3
"""The presets' downloads: one zip with every set, one zip per set, the single files and a list, for the presets page.

    presets_zip.py OUTDIR [--src presets]

OUTDIR gets:
  dn2-wishes-presets.zip           every set (dn2-wishes-presets/<SET>/<file>) and presets/README.md
  dn2-wishes-presets-<SET>.zip     one set (dn2-wishes-presets-<SET>/<file>)
  <SET>/<file>.dn2pst              each preset, as it is in presets/
  presets.json                     what presets.html lists: each zip's name, size, sha256 and presets

The same files give the same bytes, on any machine and any day: entries in sorted order, stored (the presets are
zips already; no deflate, so no zlib version can change a byte), one fixed date (1980-01-01, ZIP's first), one set of
attributes (a regular file, rw-r--r--), no comment, no extra field. Standard library only (the Pages workflow runs
it, scripts/make_site.sh).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from presets_sets import SETS  # noqa: E402

STEM = "dn2-wishes-presets"
SUFFIX = ".dn2pst"
DATE = (1980, 1, 1, 0, 0, 0)
ATTR = (0o100644 << 16)


def zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """-> a zip of ENTRIES (name, data), the same bytes for the same entries"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = ATTR
            z.writestr(info, data)
    return buf.getvalue()


def sets_of(src: pathlib.Path) -> list[tuple[object, list[pathlib.Path]]]:
    """-> [(set, its files)] in SETS' order, the sets with files only; a folder no set names is an error"""
    known = {s.folder for s in SETS}
    stray = sorted(d.name for d in src.iterdir() if d.is_dir() and d.name not in known)
    if stray:
        raise SystemExit(f"{src}: folders no set names: {stray} (scripts/presets_sets.py)")
    out = []
    for s in SETS:
        files = sorted((src / s.folder).glob(f"*{SUFFIX}")) if (src / s.folder).is_dir() else []
        if files:
            out.append((s, files))
    return out


def _entry(name: str, data: bytes, title: str, what: str, count: int, presets: list[dict]) -> dict:
    return {"zip": name, "title": title, "what": what, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "count": count, "presets": presets}


def build(src: pathlib.Path, out: pathlib.Path) -> list[dict]:
    """write the zips, the single files and presets.json into OUT; -> the list"""
    sets = sets_of(src)
    out.mkdir(parents=True, exist_ok=True)
    listing, everything = [], [(f"{STEM}/README.md", (src / "README.md").read_bytes())]
    for s, files in sets:
        stem = f"{STEM}-{s.folder}"
        entries = [(f"{stem}/{f.name}", f.read_bytes()) for f in files]
        everything += [(f"{STEM}/{s.folder}/{f.name}", f.read_bytes()) for f in files]
        presets = [{"name": f.stem, "file": f"{s.folder}/{f.name}", "bytes": f.stat().st_size} for f in files]
        data = zip_bytes(entries)
        (out / f"{stem}.zip").write_bytes(data)
        (out / s.folder).mkdir(exist_ok=True)
        for f in files:
            shutil.copyfile(f, out / s.folder / f.name)
        listing.append(_entry(f"{stem}.zip", data, s.title, s.what, len(presets), presets))
    data = zip_bytes(everything)
    (out / f"{STEM}.zip").write_bytes(data)
    total = sum(e["count"] for e in listing)
    listing.insert(0, _entry(f"{STEM}.zip", data, "Every set", "every set in its own folder, with the README",
                                total, []))
    (out / "presets.json").write_text(json.dumps(listing, indent=1) + "\n", encoding="utf-8")
    return listing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--src", type=pathlib.Path, default=ROOT / "presets")
    a = ap.parse_args(argv)
    for e in build(a.src, a.out):
        print(f"{e['zip']:36} {e['bytes']:8} B  {e['count']:3} presets  {e['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
