"""The emulator's answers to the telemetry request (docs/device-tests.md): the replies emu_waverider_menu.py's
`sysex:FILE` step kept (FILE.replies.json) decoded as the harness would, and checked against what the step poked.

    python scripts/check_tlm_replies.py tlm_req.hex.replies.json [--hold-count N] [--hold-seq N]

The emulator runs no DSP and no audio ISR: the DSP's figures and the frame counter are zero or "none"; the
HOLD words are what the step poked. What is checked is the frame's shape: HELLO answers, TLM answers twice with
the magic, the build id, 128 bytes, no fault, and the words that are the ColdFire's own.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

from dn2test import frame  # noqa: E402
from dn2test.unit import parse  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("replies")
    ap.add_argument("--hold-count", type=int, default=None)
    ap.add_argument("--hold-seq", type=int, default=None)
    a = ap.parse_args()
    sent = json.loads(pathlib.Path(a.replies).read_text())
    replies = [parse(bytes.fromhex(h)) for h, port in sent if h]
    check("one reply to each of the three requests", len(replies) == 3 and all(replies), f"{len(replies)} replies")
    if len(replies) != 3 or not all(replies):
        return 1
    hello, t1, t2 = replies
    check("HELLO answers with the sample link's version", hello["cmd"] == 0x81 and hello["status"] == 0
          and int.from_bytes(hello["payload"][:2], "big") >= 7, f"{hello['payload'][:2].hex()}")
    for k, r in enumerate((t1, t2)):
        check(f"TLM {k + 1}: answers, status 0, 128 bytes", r["cmd"] == 0xA0 and r["status"] == 0 and len(r["payload"]) == 128,
              f"cmd {r['cmd']:#x} status {r['status']} {len(r['payload'])} B")
    f1, f2 = frame.decode(t1["payload"]), frame.decode(t2["payload"])
    check("the build id is the 0.47 telemetry frame", f1.build >> 16 == 0x0047, f"{f1.build:#010x}")
    check("two requests, the same frame but the clock (nothing changes by being read)",
          frame.encode(f1)[16:] == frame.encode(f2)[16:], "words 4..31 equal")
    check("the emulator's DSP figures read 'none' or zero (no DSP runs)", f1.d_pm in (None, 0) and f1.voices == 0, f"D {f1.d_pm}, voices {f1.voices}")
    if a.hold_count is not None:
        check("hold_count is the poked word", f1.hold_count == a.hold_count, f"{f1.hold_count}")
    if a.hold_seq is not None:
        check("hold_seq is the poked word", f1.hold_seq == a.hold_seq, f"{f1.hold_seq:#x}")
    print(f"tlm check: {'PASS' if not failures else 'FAIL ' + ', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
