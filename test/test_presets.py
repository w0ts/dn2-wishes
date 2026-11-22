"""presets/ (the sounds we publish) and its downloads: every file passes the privacy check and sits in its set's
folder; presets_sync.py refuses what could be private and copies nothing then; presets_zip.py gives the same bytes
from the same files; the presets page lists only files the site serves."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import presets_sets as SETS  # noqa: E402
import presets_sync as S  # noqa: E402
import presets_zip as Z  # noqa: E402

PRESETS = ROOT / "presets"
WEB = ROOT / "tools/web"
GOOD = PRESETS / "MD" / "MD INIT.dn2pst"
TRAILER = bytes.fromhex("aaa1daaa")


# -- a preset made by hand: one LZ4 block of literals only (a valid block), the CRC and trailer as Transfer's ------
def _payload(head: bytes, body: bytes) -> bytes:
    n = len(body) - 15
    block = bytes([0xF0]) + b"\xff" * (n // 255) + bytes([n % 255]) + body
    chain = struct.pack(">I", len(block)) + block + b"\0\0\0\0"
    return head + chain + struct.pack(">II", zlib.crc32(chain, 0xFFFFFFFF), len(chain)) + TRAILER


def _preset(name: str = "MD INIT", body: bytes | None = None, slot: int = 0, manifest: dict | None = None,
            comment: bytes = b"", machine: int | None = None) -> bytes:
    z = zipfile.ZipFile(GOOD)
    m = json.loads(z.read("manifest.json"))
    pl = z.read(m["Payload"])
    body = bytearray(body if body is not None else S.P.body_of(pl))
    body[S.NAME_AT:S.NAME_AT + S.NAME_LEN] = name.encode()[:16].ljust(16, b"\0")
    if machine is not None:
        body[S.TYPE_AT] = machine
    head = pl[:21] + struct.pack(">I", slot) + pl[25:31]
    m = {**m, "Payload": name, **(manifest or {})}
    return _zip([("manifest.json", json.dumps(m, indent=2).encode()), (name, _payload(head, bytes(body)))], comment)


def _zip(entries: list[tuple[str, bytes]], comment: bytes = b"") -> bytes:
    """a ZIP as Transfer writes one (zipfile would give its entries a computer's file attributes)"""
    out, central = bytearray(), bytearray()
    for name, data in entries:
        nb, crc, off = name.encode(), zlib.crc32(data), len(out)
        out += struct.pack("<IHHHHHIIIHH", 0x04034B50, 10, 0x800, 0, 0, 0x5B74, crc, len(data), len(data), len(nb), 0)
        out += nb + data
        central += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 10, 0x800, 0, 0, 0x5B74, crc, len(data),
                               len(data), len(nb), 0, 0, 0, 0, 0, off) + nb
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(entries), len(entries), len(central), len(out), len(comment))
    return bytes(out + central + end + comment)


def _problems(tmp: pathlib.Path, file: str, raw: bytes) -> list[str]:
    (tmp / file).write_bytes(raw)
    return S.check_file(tmp / file)[1]


# -- the published folder ---------------------------------------------------------------------------------------
def test_the_published_presets_are_clean_and_in_their_folders():
    assert S.check(PRESETS) == 0
    files = S.published(PRESETS)
    assert len(files) >= 100
    for f in files:
        info, bad = S.check_file(f)
        assert not bad, (f, bad)
        assert f.parent.name == info.set.folder


def test_every_set_folder_is_a_set_and_the_prefixes_are_unique():
    folders = {d.name for d in PRESETS.iterdir() if d.is_dir()}
    assert folders <= set(SETS.BY_FOLDER)
    prefixes = [p for s in SETS.SETS for p in s.prefixes]
    assert len(prefixes) == len(set(prefixes))


# -- the check refuses what could be private ----------------------------------------------------------------------
def test_a_preset_made_like_ours_passes(tmp_path):
    assert _problems(tmp_path, "MD INIT.dn2pst", _preset()) == []


@pytest.mark.parametrize("why, kw, file", [
    ("text", {"body": None}, "MD INIT.dn2pst"),
    ("slot", {"slot": 17}, "MD INIT.dn2pst"),
    ("manifest", {"manifest": {"Author": "someone"}}, "MD INIT.dn2pst"),
    ("tags", {"manifest": {"MetaInfo": {"Tags": ["BASS"], "Device": "x"}}}, "MD INIT.dn2pst"),
    ("comment", {"comment": b"made on someone's computer"}, "MD INIT.dn2pst"),
    ("prefix", {"name": "XYZ INIT"}, "XYZ 00 XYZ INIT.dn2pst"),
    ("machine", {"machine": 51}, "MD INIT.dn2pst"),
    ("not an INIT", {"name": "FMT MY PAD", "machine": 0}, "FMT 01 MY PAD.dn2pst"),
])
def test_the_check_refuses(tmp_path, why, kw, file):
    if why == "text":
        body = bytearray(S.P.body_of(zipfile.ZipFile(GOOD).read("MD INIT")))
        body[200:216] = b"SOMEONES MACBOOK"
        kw = {"body": bytes(body)}
    assert _problems(tmp_path, file, _preset(**kw)), why


def test_an_extra_zip_entry_is_refused(tmp_path):
    z = zipfile.ZipFile(io.BytesIO(_preset()))
    raw = _zip([(n, z.read(n)) for n in z.namelist()] + [("notes.txt", b"a note")])
    assert any("ZIP entries" in p for p in _problems(tmp_path, "MD INIT.dn2pst", raw))


# -- the sync -----------------------------------------------------------------------------------------------------
def _dest(tmp: pathlib.Path) -> pathlib.Path:
    dest = tmp / "dest"
    dest.mkdir()
    shutil.copyfile(PRESETS / "README.md", dest / "README.md")
    return dest


def test_sync_copies_into_the_sets_and_writes_the_table(tmp_path):
    src, dest = tmp_path / "src", _dest(tmp_path)
    src.mkdir()
    for f in (GOOD, PRESETS / "INIT" / "FMT 00 FMT INIT.dn2pst"):
        shutil.copyfile(f, src / f.name)
    (src / ".DS_Store").write_bytes(b"\0")
    assert S.sync(src, dest, prune=False) == 0
    assert (dest / "MD" / GOOD.name).read_bytes() == GOOD.read_bytes()
    assert (dest / "INIT" / "FMT 00 FMT INIT.dn2pst").is_file()
    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert "| [`MD/`](MD/) | 1 |" in readme and "| [`INIT/`](INIT/) | 1 |" in readme and "`AN2/`" not in readme
    assert S.check(dest) == 0
    (src / GOOD.name).unlink()
    assert S.sync(src, dest, prune=False) == 0 and (dest / "MD" / GOOD.name).is_file()
    assert S.sync(src, dest, prune=True) == 0 and not (dest / "MD").exists()


def test_one_bad_file_and_nothing_is_copied(tmp_path):
    src, dest = tmp_path / "src", _dest(tmp_path)
    src.mkdir()
    shutil.copyfile(GOOD, src / GOOD.name)
    (src / "MD SNARE.dn2pst").write_bytes(_preset("MD SNARE", slot=3))
    before = (dest / "README.md").read_bytes()
    assert S.sync(src, dest, prune=False) == 1
    assert sorted(p.name for p in dest.iterdir()) == ["README.md"]
    assert (dest / "README.md").read_bytes() == before


# -- the zips -----------------------------------------------------------------------------------------------------
def _tree(d: pathlib.Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_the_zips_are_the_same_bytes_from_the_same_files(tmp_path):
    copy = tmp_path / "presets"
    shutil.copytree(PRESETS, copy)
    first = _tree(_built(copy, tmp_path / "a"))
    for p in copy.rglob("*"):
        os.utime(p, (1_000_000_000, 1_000_000_000))
    second = _tree(_built(copy, tmp_path / "b"))
    assert first == second
    z = zipfile.ZipFile(io.BytesIO(first["dn2-wishes-presets.zip"]))
    names = z.namelist()
    assert names == sorted(names)
    for i in z.infolist():
        assert i.date_time == Z.DATE and i.compress_type == zipfile.ZIP_STORED and not i.extra and not i.comment


def _built(src: pathlib.Path, out: pathlib.Path) -> pathlib.Path:
    Z.build(src, out)
    return out


def test_each_zip_holds_its_set_exactly(tmp_path):
    out = _built(PRESETS, tmp_path / "out")
    listing = json.loads((out / "presets.json").read_text(encoding="utf-8"))
    every = zipfile.ZipFile(out / listing[0]["zip"])
    want_all = {f"{Z.STEM}/README.md": (PRESETS / "README.md").read_bytes()}
    for e in listing[1:]:
        folder = e["zip"][len(Z.STEM) + 1:-len(".zip")]
        files = sorted((PRESETS / folder).glob("*.dn2pst"))
        z = zipfile.ZipFile(out / e["zip"])
        assert {n: z.read(n) for n in z.namelist()} == {f"{Z.STEM}-{folder}/{f.name}": f.read_bytes() for f in files}
        assert e["count"] == len(files) == len(e["presets"])
        want_all |= {f"{Z.STEM}/{folder}/{f.name}": f.read_bytes() for f in files}
    assert {n: every.read(n) for n in every.namelist()} == want_all
    assert listing[0]["count"] == len(S.published(PRESETS))


# -- the page -----------------------------------------------------------------------------------------------------
def test_the_page_lists_only_what_the_site_serves(tmp_path):
    site = tmp_path / "site"
    subprocess.run(["bash", str(ROOT / "scripts/make_site.sh"), str(site), "--preview"], check=True,
                   capture_output=True)
    page = (site / "presets.html").read_text(encoding="utf-8")
    assert 'fetch("presets/presets.json"' in page
    listing = json.loads((site / "presets" / "presets.json").read_text(encoding="utf-8"))
    assert listing and listing[0]["zip"] == f"{Z.STEM}.zip"
    for e in listing:
        data = (site / "presets" / e["zip"]).read_bytes()
        assert len(data) == e["bytes"] and hashlib.sha256(data).hexdigest() == e["sha256"]
        for p in e["presets"]:
            assert (site / "presets" / p["file"]).read_bytes() == (PRESETS / p["file"]).read_bytes()


def test_the_readme_links_the_presets_page():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://w0ts.github.io/dn2-wishes/presets.html" in readme
    assert "presets.html" in (WEB / "builder.html").read_text(encoding="utf-8")
