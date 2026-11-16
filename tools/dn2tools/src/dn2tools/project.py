"""The project the User prepares on the unit (docs/device-tests.md): which machine, filter, insert and
HOLD each track carries, and the MIDI channel each track listens on. The harness cannot set any of
these (no parameter CC is sent); it only needs to know them to choose what to play and what to expect."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

FILTERS = ("SVF", "LADR", "OTA", "DIOD", "MS20")        # the A2 filter machines 7..11
INSERTS = ("XDLY", "FDN8", "CHOR")


@dataclass(frozen=True)
class Track:
    number: int                 # 1..16
    channel: int                # 0..15 on the wire (the track's MIDI channel, default = the track number)
    machine: str
    filter: str | None = None   # an A2 filter on the track's FLTR page
    insert: str | None = None   # XDLY or FDN8 engaged as the track's insert
    hold: bool = False          # DRONE's HOLD on
    glide: bool = False         # DRONE's GLID long
    reference: bool = False     # the dry reference for the audio comparisons: the same kind of sound, no filter, no insert
    key: str | None = None      # the runner budget table's row for the machine (bench calibration), e.g. PLAITS:WS

    @property
    def label(self) -> str:
        return f"T{self.number} {self.machine}" + (f" {self.filter}" if self.filter else "") \
            + (f" +{self.insert}" if self.insert else "") + (" HOLD" if self.hold else "") + (" GLID" if self.glide else "")


@dataclass(frozen=True)
class Project:
    name: str
    tracks: tuple[Track, ...]

    def where(self, pred) -> tuple[Track, ...]:
        return tuple(t for t in self.tracks if pred(t))

    @staticmethod
    def from_dict(d: dict) -> "Project":
        tracks = []
        for key, v in sorted(d["tracks"].items(), key=lambda kv: int(kv[0])):
            n = int(key)
            if not 1 <= n <= 16:
                raise ValueError(f"track {n}: 1..16")
            ch = int(v.get("channel", n))
            if not 1 <= ch <= 16:
                raise ValueError(f"track {n}: channel {ch}: 1..16")
            flt, ins = v.get("filter"), v.get("insert")
            if flt is not None and flt not in FILTERS:
                raise ValueError(f"track {n}: filter {flt!r}: one of {FILTERS}")
            if ins is not None and ins not in INSERTS:
                raise ValueError(f"track {n}: insert {ins!r}: one of {INSERTS}")
            tracks.append(Track(n, ch - 1, v["machine"], flt, ins, bool(v.get("hold")), bool(v.get("glide")), bool(v.get("reference")), v.get("key")))
        return Project(d.get("name", "project"), tuple(tracks))

    @staticmethod
    def load(path: str | pathlib.Path) -> "Project":
        return Project.from_dict(json.loads(pathlib.Path(path).read_text()))
