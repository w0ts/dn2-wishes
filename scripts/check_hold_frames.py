"""DRONE's HOLD latch on the real ISR path (2026-11-10): reads the frames scripts/emu_waverider_menu.py wrote
for the steps in docs/drone.md "HOLD, checked" and asserts what the DSP is sent (frame +36, the note-off
mask, bit 0 for track 1's voice 0; +34 the note-on mask):

    python scripts/check_hold_frames.py DIR

DIR holds the frames of one run, named by the steps' `frame:NAME`:
  on_f1 on_f2   a played key down: the note-on (+34 bit 0)
  on_f3         the key up, HOLD ON: no note-off (+36 bit 0 clear)
  on_f4 on_f5   the same key again: no new note-on, and the latch lets go: the note-off (+36 bit 0 set)
  off_f1 off_f3 HOLD OFF (the control): the note-on, then the key up sends the note-off
  rel_f1 rel_f3 HOLD ON, key up (held), then HOLD turned OFF: rel_f4 the note-off
Exit status 0 when every check holds."""
from __future__ import annotations

import pathlib
import struct
import sys


def word(d: pathlib.Path, name: str, off: int) -> int:
    return struct.unpack_from(">H", (d / f"{name}.frame_be.bin").read_bytes(), off)[0]


def main(argv) -> int:
    d = pathlib.Path(argv[1])
    on = lambda n: word(d, n, 34)              # noqa: E731  the voices started this frame (a voice a note: it rotates)
    off = lambda n: word(d, n, 36)             # noqa: E731  the voices released
    v_on, v_off, v_rel = on("on_f1"), on("off_f1"), on("rel_f1")
    checks = {
        "a played key sends its note-on (one voice)": v_on != 0 and v_off != 0 and v_rel != 0,
        "HOLD OFF (control): the key up sends that voice's note-off": off("off_f3") & v_off == v_off,
        "HOLD ON: the key up sends no note-off for the voice": not (off("on_f3") & v_on) and not (off("on_f4") & v_on),
        "HOLD ON: the same key again starts no note": on("on_f5") == 0,
        "HOLD ON: ... and lets the latch go (the note-off)": bool(off("on_f5") & v_on) or bool(off("on_f6") & v_on),
        "HOLD ON then OFF: no note-off while on, the voice's note-off once off": not (off("rel_f3") & v_rel)
        and bool((off("rel_f4") | off("rel_f5")) & v_rel),
    }
    bad = [k for k, v in checks.items() if not v]
    for k, v in checks.items():
        print(("PASS  " if v else "FAIL  ") + k)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
