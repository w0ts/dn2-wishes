#!/usr/bin/env python3
"""The presets we publish (presets/): checked for anything private, then copied in from the folder they are made in.

    presets_sync.py SRC [--dest presets] [--prune]   check every .dn2pst in SRC; if all pass, copy them into
                                                     DEST/<SET>/ (only the ones that changed) and refresh the
                                                     table in DEST/README.md. --prune also removes a file of
                                                     DEST that SRC no longer has (without it, it is listed)
    presets_sync.py --check [DEST]                   check the published folder itself: every file passes and
                                                     sits in its set's folder, the README's table is current

A preset is published only when nothing in it can name a person, a unit or a computer (docs/privacy.md), and only
when our tooling made it: the file is a ZIP exactly as Elektron Transfer writes one (no comment, no extra fields,
no entry besides manifest.json and the payload); the manifest carries only Elektron's keys and the sound's tags;
the payload is a new file (+Drive slot 0: a sound saved from a unit's pool carries its slot and is refused); the
only text in the stored sound is its name, in the name field; the machine is one of the set's types, and a sound of
a machine that is not ours is an INIT (named "... INIT"). One failing file and nothing is copied: the problems are
listed, for the User to decide.

A new set (a new machine of ours): one row in presets_sets.py.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import pathlib
import re
import shutil
import struct
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.wishes import pst as P  # noqa: E402
from presets_sets import BY_PREFIX, SETS, Set  # noqa: E402

DEST = ROOT / "presets"
SUFFIX = ".dn2pst"
MAX_BYTES = 64 * 1024
TYPE_AT = 5 + 244            # the body's prefix, then the stored sound's machine byte (docs/machine-types.md)
NAME_AT, NAME_LEN = 5 + 12, 16
MANIFEST_KEYS = {"FormatVersion", "ProductType", "Payload", "FileType", "FirmwareVersion", "MetaInfo"}
DEVICE = bytes.fromhex("020005000f")
TAG = re.compile(r"^[A-Z][A-Z0-9 -]{0,23}$")
TEXT = re.compile(rb"[\x20-\x7e]{4,}")


@dataclasses.dataclass(frozen=True)
class Info:
    file: str
    set: Set
    name: str
    machine: int
    tags: tuple[str, ...]


def _zip_problems(raw: bytes, z: zipfile.ZipFile) -> list[str]:
    bad = []
    if not raw.startswith(b"PK\x03\x04") or raw[-22:-18] != b"PK\x05\x06":
        bad.append("bytes before the ZIP or after its end")
    if z.comment:
        bad.append(f"a ZIP comment {z.comment[:40]!r}")
    for i in z.infolist():
        if i.extra or i.comment:
            bad.append(f"{i.filename}: extra fields or a comment in the ZIP")
        if i.external_attr or i.create_system != 0:
            bad.append(f"{i.filename}: file attributes of a computer (system {i.create_system})")
    return bad


def _manifest_problems(m: dict, names: list[str]) -> list[str]:
    bad = []
    if set(m) != MANIFEST_KEYS:
        bad.append(f"manifest keys {sorted(m)}")
    payload = m.get("Payload")
    if names != ["manifest.json", payload]:
        bad.append(f"ZIP entries {names} (only manifest.json and the payload)")
    if m.get("FormatVersion") != "1.0" or m.get("ProductType") != [] or m.get("FileType") != "Sound":
        bad.append("manifest: not a DN2 sound (FormatVersion / ProductType / FileType)")
    if not re.fullmatch(r"\d+\.\d+[A-Z]?", str(m.get("FirmwareVersion"))):
        bad.append(f"manifest FirmwareVersion {m.get('FirmwareVersion')!r}")
    meta = m.get("MetaInfo")
    if not isinstance(meta, dict) or set(meta) != {"Tags"}:
        bad.append(f"manifest MetaInfo {meta!r} (the tags only)")
    elif not all(isinstance(t, str) and TAG.match(t) for t in meta["Tags"]):
        bad.append(f"manifest tags {meta['Tags']!r}")
    return bad


def _payload_problems(pl: bytes, name: str) -> tuple[list[str], bytes | None]:
    bad = []
    if pl[4:9] != DEVICE or not pl[9:13].isdigit():
        bad.append("payload: not a Digitone II sound")
    kind, ver, slot, _n = struct.unpack_from(">IIII", pl, 13)
    if kind != 3 or ver != 2:
        bad.append(f"payload: kind {kind}, record version {ver} (a DN2 sound: 3, 2)")
    if slot != 0:
        bad.append(f"payload: +Drive slot {slot} (saved from a unit; ours are new files, slot 0)")
    try:
        body = P.body_of(pl)
    except ValueError as e:
        return bad + [f"payload: {e}"], None
    field = body[NAME_AT:NAME_AT + NAME_LEN]
    if field != name.encode("ascii", "replace")[:NAME_LEN].ljust(NAME_LEN, b"\0"):
        bad.append(f"the stored name {field!r} is not the payload's {name!r}")
    rest = body[:NAME_AT] + bytes(NAME_LEN) + body[NAME_AT + NAME_LEN:]
    for run in TEXT.findall(rest):
        bad.append(f"text in the stored sound besides its name: {run[:40]!r}")
    return bad, body


def check_file(path: pathlib.Path) -> tuple[Info | None, list[str]]:
    """-> (what the preset is, every problem found); a preset with problems is never published"""
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        return None, [f"{len(raw)} bytes (a sound is about 1 KB)"]
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        m = json.loads(z.read("manifest.json"))
        pl = z.read(m["Payload"])
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError) as e:
        return None, [f"not a preset file: {e}"]
    name = m["Payload"]
    bad = _zip_problems(raw, z) + _manifest_problems(m, z.namelist())
    more, body = _payload_problems(pl, name)
    bad += more
    prefix = path.name.split(" ")[0]
    s = BY_PREFIX.get(prefix)
    if s is None:
        return None, bad + [f"no set for the prefix {prefix!r} (a new machine: a row in SETS)"]
    if name.split(" ")[0] != prefix:
        bad.append(f"the sound's name {name!r} does not start with {prefix!r}")
    machine = body[TYPE_AT] if body else -1
    if machine not in s.types:
        bad.append(f"machine type {machine}, not the set {s.folder}'s {s.types}")
    if s.init_only and not name.endswith(" INIT"):
        bad.append(f"{name!r}: a sound of a machine that is not ours that is not an INIT (the User's own?)")
    return Info(path.name, s, name, machine, tuple(m["MetaInfo"]["Tags"])), bad


def sources(folder: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in folder.iterdir() if p.suffix == SUFFIX and not p.name.startswith("."))


def check_all(files: list[pathlib.Path]) -> tuple[list[Info], list[str]]:
    infos, problems = [], []
    for f in files:
        info, bad = check_file(f)
        problems += [f"{f.name}: {b}" for b in bad]
        if info:
            infos.append(info)
    return infos, problems


# -- the README's table ------------------------------------------------------------------------------------------
TABLE_START, TABLE_END = "<!-- sets: presets_sync.py writes this table -->", "<!-- /sets -->"


def table(dest: pathlib.Path) -> str:
    rows = ["| folder | sounds | what |", "|---|---|---|"]
    for s in SETS:
        n = len(sources(dest / s.folder)) if (dest / s.folder).is_dir() else 0
        if n:
            rows.append(f"| [`{s.folder}/`]({s.folder}/) | {n} | {s.what} |")
    return "\n".join(rows)


def with_table(readme: str, dest: pathlib.Path) -> str:
    head, rest = readme.split(TABLE_START, 1)
    _old, tail = rest.split(TABLE_END, 1)
    return f"{head}{TABLE_START}\n{table(dest)}\n{TABLE_END}{tail}"


# -- the two modes -----------------------------------------------------------------------------------------------
def sync(src: pathlib.Path, dest: pathlib.Path, prune: bool) -> int:
    infos, problems = check_all(sources(src))
    if problems:
        print(f"{len(problems)} problem(s); nothing copied:", *problems, sep="\n  ")
        return 1
    want = {dest / i.set.folder / i.file: src / i.file for i in infos}
    counts = {"new": 0, "changed": 0, "same": 0}
    for to, frm in sorted(want.items()):
        data = frm.read_bytes()
        state = "same" if to.is_file() and to.read_bytes() == data else "changed" if to.is_file() else "new"
        counts[state] += 1
        if state != "same":
            to.parent.mkdir(parents=True, exist_ok=True)
            to.write_bytes(data)
            print(f"{state:8} {to.relative_to(dest)}")
    for old in sorted(dest.glob(f"*/*{SUFFIX}")):
        if old not in want:
            if prune:
                old.unlink()
                print(f"removed  {old.relative_to(dest)}")
            else:
                print(f"only in {dest.name}/ (kept; --prune removes it): {old.relative_to(dest)}")
    for d in dest.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            shutil.rmtree(d)
    readme = dest / "README.md"
    readme.write_text(with_table(readme.read_text(encoding="utf-8"), dest), encoding="utf-8")
    print(f"{len(infos)} presets checked: {counts['new']} new, {counts['changed']} changed, {counts['same']} the same")
    return 0


def published(dest: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in dest.glob(f"*/*{SUFFIX}"))


def check(dest: pathlib.Path) -> int:
    files = published(dest)
    infos, problems = check_all(files)
    for f, i in zip(files, infos):
        if f.parent.name != i.set.folder:
            problems.append(f"{f.relative_to(dest)}: belongs in {i.set.folder}/")
    stray = [p for p in dest.rglob("*") if p.is_file() and p.suffix != SUFFIX and p != dest / "README.md"]
    problems += [f"{p.relative_to(dest)}: not a preset" for p in stray]
    readme = (dest / "README.md").read_text(encoding="utf-8")
    if with_table(readme, dest) != readme:
        problems.append("README.md: the table is not current (presets_sync.py rewrites it)")
    if problems:
        print(*problems, sep="\n")
        return 1
    print(f"{len(files)} presets in {len(SETS)} sets: clean")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", nargs="?", type=pathlib.Path, help="the folder the presets are made in")
    ap.add_argument("--dest", type=pathlib.Path, default=DEST)
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--check", nargs="?", const=DEST, type=pathlib.Path, metavar="DEST")
    a = ap.parse_args(argv)
    if a.check:
        return check(a.check)
    if not a.src:
        ap.error("SRC or --check")
    return sync(a.src, a.dest, a.prune)


if __name__ == "__main__":
    sys.exit(main())
