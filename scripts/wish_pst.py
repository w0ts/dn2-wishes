"""Wishes records in .dn2pst preset files: see what a preset carries, take its record from the unit, give it to a unit.

    wish_pst.py info  FILE.dn2pst ...          the sound's link, and whether the file carries the record it names
    wish_pst.py fetch FILE.dn2pst [-o OUT]     the record the link names, asked of the unit (GET), put in the file
    wish_pst.py send  FILE.dn2pst ...          the file's records given to the unit (PUT): sounds waiting for them
                                               (a preset sent by Transfer before or after) find them by their hash

Transfer sends a preset's sound (and its link); this sends the record beside it, over our SysEx channel (USB, a
build of ours; stock firmware does not answer). docs/wishes-record.md "Travel".
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from dnfw.wishes import pst as P          # noqa: E402
from dnfw.wishes import travel as T       # noqa: E402


def info(files: list[str]) -> int:
    for f in files:
        p = P.Preset(pathlib.Path(f).read_bytes())
        link = p.link()
        if not link:
            print(f"{f}: no link (a stock sound)")
            continue
        has = "carries it" if p.record() else "does not carry it"
        print(f"{f}: link {link.h0:08x}{link.h1:08x}, {link.length} bytes; the file {has}"
              f" ({len(p.records())} record(s) in {P.ENTRY})")
    return 0


def fetch(f: str, out: str | None, port: str) -> int:
    path = pathlib.Path(f)
    p = P.Preset(path.read_bytes())
    link = p.link()
    if not link:
        print(f"{f}: no link: nothing to fetch")
        return 1
    rec = T.Unit(T.mido_exchange(port)).get(link)
    if rec is None:
        print(f"{f}: the unit has no record {link.h0:08x}{link.h1:08x} (no sound holds it, no cell of its +Drive)")
        return 1
    keep = [r for r in p.records() if r != rec]
    dest = pathlib.Path(out) if out else path
    dest.write_bytes(p.with_records(keep + [rec]))
    print(f"{dest}: {len(rec)} bytes of record added")
    return 0


def send(files: list[str], port: str) -> int:
    unit = T.Unit(T.mido_exchange(port))
    for f in files:
        for rec in P.Preset(pathlib.Path(f).read_bytes()).records():
            h0, h1 = unit.put(rec)
            print(f"{f}: record {h0:08x}{h1:08x} ({len(rec)} bytes) given to the unit")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("cmd", choices=("info", "fetch", "send"))
    a.add_argument("files", nargs="+")
    a.add_argument("-o", "--out", help="fetch: write here instead of over the file")
    a.add_argument("--port", default="Elektron Digitone II", help="a part of the MIDI port's name")
    args = a.parse_args()
    if args.cmd == "info":
        return info(args.files)
    if args.cmd == "fetch":
        if len(args.files) != 1 and args.out:
            a.error("-o takes one file")
        return max(fetch(f, args.out, args.port) for f in args.files)
    return send(args.files, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
