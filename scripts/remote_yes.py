"""remote_yes.py: answer the DN2's UPGRADE OS NOW? after scripts/flash_cli.py, through the remote UI test channel.

    remote_yes.py shot OUT.png   the DN2's screen as a PNG: look at it, it must read "UPGRADE OS NOW? / CONFIRM Y/N"
    remote_yes.py press          one YES tap, the channel armed destructive for that press, then disarmed

Needs our firmware running with REMOTE CONTROL ON (it does not work from stock 1.12: use flash_cli.py --install
there). Never press without a fresh shot showing the question: a blind YES answers whatever is on screen.
Run with the venv that has mido + python-rtmidi (scratch/remoteui/venv).
"""
import pathlib
import sys
import time

DN2TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "dn2tools" / "src"
USAGE = "usage: remote_yes.py shot OUT.png | press"


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("shot", "press") or (argv[0] == "shot" and len(argv) != 2):
        print(USAGE, file=sys.stderr)
        return 2
    sys.path.insert(0, str(DN2TOOLS))  # dn2tools is not installed in the venv: use the repo's copy
    from dn2tools import protocol as P
    from dn2tools import screen
    from dn2tools.channel import TestChannel
    from dn2tools.keys import CODES
    from dn2tools.unit import MidoUnit

    unit = MidoUnit()
    ch = TestChannel(unit)
    try:
        if argv[0] == "shot":
            print(screen.write_png(ch.screen(), argv[1]))
            return 0
        ch.disarm()
        ch.arm(destructive=True)
        accepted = ch.send_events([P.Event(1, CODES["YES"], 60, 80)])
        time.sleep(0.6)
        ch.disarm()
        print("accepted", accepted)
        return 0 if accepted == 1 else 1
    finally:
        unit.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
