"""The Digitone II's screen and keys, remotely (a test build; docs/remote-ui.md).

    dn2ui snap [FILE.png]                     one frame -> PNG (prints the path)
    dn2ui mirror [--fps 8] [--png-dir DIR] [--window] [--seconds S]   the live screen: terminal, PNGs, or a window
    dn2ui show                                one frame as text in the terminal
    dn2ui arm | disarm | status               the handshake; the unit disarms itself after ARMTIME s without a command
    dn2ui press FUNC+SRC [--tap-ms 80]        a key or a chord (modifiers held, the last key tapped)
    dn2ui hold PLAY 600                       a key held for 600 ms
    dn2ui turn A +5 [--push]                  an encoder (A..H, LEVEL), with its push held if --push
    dn2ui seq "FUNC+SRC" "turn:A:+3" "wait:0.5" "YES"
    dn2ui wait-for FILE.png|--changed [--timeout 3]
    dn2ui run SCENARIO.json [--out DIR]       a UI scenario file: {"name": ..., "steps": [...]} (docs/remote-ui.md)
    dn2ui keys                                the key names

press / hold / turn / seq arm first if the unit is not armed, and leave it armed (it times out by itself).
Destructive keys and chords are refused (SETTINGS; FUNC with anything but the page keys, arrows, PLAY,
STOP, PAGE, encoder pushes); --allow-destructive lifts that and is DANGEROUS: it can save over a project
or start an OS update. Every event goes to the event log (--log, default ./dn2ui-events.jsonl).
Driving the UI changes the project in RAM: use a scratch project.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

from .. import screen as S
from ..channel import TestChannel
from ..keys import CODES, ENCODERS, Blocked, Keys
from ..unit import NoTestChannel, StatusError
from .common import add_target_args, cost, open_unit


def _snap_name() -> str:
    return time.strftime("dn2-screen-%Y%m%d-%H%M%S.png")


def mirror(ch: TestChannel, a) -> int:
    period = 1.0 / max(0.5, min(a.fps, 20.0))
    end = time.monotonic() + a.seconds if a.seconds else None
    win = None
    if a.window:
        try:
            import tkinter as tk                    # the standard library's, when the Python has Tk
        except ImportError:
            print("this Python has no tkinter: showing the screen in the terminal instead")
        else:
            root = tk.Tk()
            root.title("Digitone II")
            img = tk.PhotoImage(width=S.W * a.scale, height=S.H * a.scale)
            tk.Label(root, image=img).pack()
            win = (root, img)
    png_dir = pathlib.Path(a.png_dir) if a.png_dir else None
    last, n, t_frame = None, 0, []
    try:
        while end is None or time.monotonic() < end:
            t0 = time.monotonic()
            h, whole = ch.screen_hash()
            if whole and h != last:
                frame = ch.screen(fresh=False)
                last = h
                n += 1
                if png_dir:
                    S.write_png(frame, png_dir / f"frame-{n:05d}.png", a.scale)
                if win:
                    root, img = win
                    _tk_put(img, frame, a.scale)
                    root.update()
                elif not png_dir:
                    sys.stdout.write("\x1b[H\x1b[2J" + S.text(frame) + f"\n frame {n}  hash {h:08x}\n")
                    sys.stdout.flush()
            elif win:
                win[0].update()
            t_frame.append(time.monotonic() - t0)
            ch.unit.wait(max(0.0, period - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        pass
    if t_frame:
        print(f"{n} new frames; a poll took {1000 * sum(t_frame) / len(t_frame):.1f} ms on average")
    return 0


def _tk_put(img, frame: bytes, scale: int) -> None:
    px = S.rows(frame)
    data = " ".join("{" + " ".join(("#ffffff" if px[y // scale][x // scale] else "#000000")
                                   for x in range(S.W * scale)) + "}" for y in range(S.H * scale))
    img.put(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_target_args(ap)
    ap.add_argument("--allow-destructive", action="store_true",
                    help="DANGEROUS: lets SETTINGS and FUNC chords through (project save/overwrite, format, OS update)")
    ap.add_argument("--log", default="dn2ui-events.jsonl", help="the event log (JSON lines)")
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--seconds", type=float, default=0.0, help="mirror: stop after this long (0: until Ctrl-C)")
    ap.add_argument("--png-dir", default=None)
    ap.add_argument("--window", action="store_true")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--tap-ms", type=int, default=80)
    ap.add_argument("--push", action="store_true", help="turn: hold the encoder's push while turning")
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--changed", action="store_true", help="wait-for: any change from the current frame")
    ap.add_argument("--out", default=None, help="run: where the snaps go (default: the scenario's name)")
    ap.add_argument("command")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    if a.command == "keys":
        print("keys:", " ".join(CODES), "\nencoders:", " ".join(ENCODERS))
        return 0
    unit = open_unit(a)
    ch = TestChannel(unit)
    keys = Keys(ch, allow_destructive=a.allow_destructive, log=a.log)
    try:
        cmd = a.command
        if cmd in ("press", "hold", "turn", "seq", "run"):
            if not ch.arm_status().armed:
                s = keys.arm()
                print(f"armed (auto-disarm after {s.timeout_s} s without a command)")
        if cmd == "snap":
            path = S.write_png(ch.screen(), a.args[0] if a.args else _snap_name(), a.scale)
            cost(unit, "SCREEN x8", a.quiet)
            print(path.resolve())
        elif cmd == "show":
            print(S.text(ch.screen()))
        elif cmd == "mirror":
            return mirror(ch, a)
        elif cmd == "arm":
            s = keys.arm()
            print(f"armed{' WITH DESTRUCTIVE KEYS ALLOWED' if s.destructive else ''}; auto-disarm after {s.timeout_s} s")
        elif cmd == "disarm":
            keys.disarm()
            print("disarmed")
        elif cmd == "status":
            s = ch.state()
            print(f"armed {s.armed}{' (destructive)' if s.destructive else ''}, {s.seconds_left} s left, held {s.held}, "
                  f"pending {s.pending}")
        elif cmd == "press":
            for combo in a.args:
                keys.press(combo, a.tap_ms)
                cost(unit, f"KEY {combo}", a.quiet)
        elif cmd == "hold":
            keys.hold(a.args[0], int(a.args[1]))
        elif cmd == "turn":
            keys.turn(a.args[0], int(a.args[1]), push=a.push)
        elif cmd == "seq":
            keys.sequence(a.args)
        elif cmd == "run":
            import json
            sc = json.loads(pathlib.Path(a.args[0]).read_text())
            if set(sc) - {"name", "about", "steps"} or not isinstance(sc.get("steps"), list):
                raise SystemExit("a scenario is {\"name\": str, \"about\": str, \"steps\": [str, ...]}")
            out = pathlib.Path(a.out or sc.get("name", "scenario"))
            try:
                shots = keys.sequence(sc["steps"], out_dir=out)
            except AssertionError as e:
                print(f"FAIL {sc.get('name')}: {e}")
                return 1
            print(f"PASS {sc.get('name')}: {len(sc['steps'])} steps; {', '.join(shots) or 'no snaps'}")
        elif cmd == "wait-for":
            if a.changed:
                ref = ch.screen()
                got = keys.wait_for_screen(lambda f: f != ref, a.timeout)
            else:
                want = _load_png(a.args[0], a.scale)
                got = keys.wait_for_screen(want, a.timeout)
            print("matched" if got is not None else "timed out")
            return 0 if got is not None else 1
        else:
            raise SystemExit(f"unknown command {cmd!r} (dn2ui --help)")
    except Blocked as e:
        print(f"REFUSED: {e} (dn2ui --allow-destructive lifts this; dangerous)")
        return 3
    except NoTestChannel as e:
        print(f"no test channel: {e}")
        return 2
    except StatusError as e:
        print(e)
        return 1
    finally:
        unit.close()
    return 0


def _load_png(path: str, scale: int) -> bytes:
    """a PNG this tool wrote (grey, SCALE) -> a frame"""
    import zlib
    data = pathlib.Path(path).read_bytes()
    i, idat, w = 8, b"", 0
    while i < len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        kind = data[i + 4:i + 8]
        if kind == b"IHDR":
            w = int.from_bytes(data[i + 8:i + 12], "big")
        elif kind == b"IDAT":
            idat += data[i + 8:i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(idat)
    sc = w // S.W
    px = [[raw[(y * sc) * (w + 1) + 1 + x * sc] > 127 for x in range(S.W)] for y in range(S.H)]
    return S.from_rows(px)


if __name__ == "__main__":
    raise SystemExit(main())
