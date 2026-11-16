"""PARA on the VOICE menu's knob B (csrc/para/vmenu.c, docs/paraphonic.md) in the ColdFire emulator: the gate's check.

    emu_para_vmenu.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--json OUT] [--png-dir DIR]

On the build's own snapshot, with the panel's frame clock (emulib.panel.Panel.frame_clock: without it the screen does
not redraw after a turn), the VOICE key (panel code 49) on track 0:

1. a stock machine's track (WaveTone, type 1): pushed turns of B and C leave the screen, the sound's MOD record and
   vm_sets as they were (stock's empty places stay stock's);
2. an ANALOG 2 track (type 22), MOD 0: the screen differs from (1)'s only inside B's label row (x 33..73, y 27..34),
   where PARA OFF is drawn;
3. one held push of B a step (the harness passes about one step a hold, stock's own knob E too; measured
   2026-11-15), four detents each. PARA is OFF / ON (2026-11-15, the User; ON stored as 0x0300, a chord of up to 8): right
   three times -> MOD 0x0300 0x0300 0x0300, the screen then differs from OFF's inside B's row only (PARA ON); left
   twice -> 0x0000 0x0000; vm_sets counts the one step up and the one down;
4. a JUNO track (type 23, 2026-11-15), MOD 0: the screen the ANALOG 2 track's (PARA OFF in B's row); one held push
   of B right sets MOD 0x0300 and draws PARA ON as on the ANALOG 2 track; one left sets 0x0000, the screen as before;
5. an older project's value (MOD 0x0100, 2 pitches then) on an ANALOG 2 track: the screen is a fresh PARA ON track's
   (MOD 0x0300), and one held push of B left sets MOD 0x0000.

Built from the integrator's driver (side-session-notes paraphonic-voice-menu/build-para3/para_vmenu3.py). Prints PASS
or FAIL with each check; --json writes the numbers.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

VOICE = (6, 0)                                                       # panel code 49
ENC_B, ENC_C = 1, 2
MOD_AT = 20 + 2 * 37                                                 # the sound's MOD (PARA) value
WAVETONE, ANALOG2, JUNO = 1, 22, 23
B_ROW = (33, 27, 73, 34)                                             # B's label row (x0, y0, x1, y1), bottom-up
STEPS_RIGHT = (0x0300, 0x0300, 0x0300)                              # OFF -> ON (stored 3), held at ON
STEPS_LEFT = (0x0000, 0x0000)                                        # ON -> OFF, held at OFF
HOLD_GAP = 60_000_000          # the UI settled between holds (the integrator, 2026-11-15: shorter, a later hold's
                               # first ~7 detents never arrive, stock's knob E too; with it every hold gives all 4)
FAILS: list[str] = []


def check(what: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(what)


def frame(p) -> bytes:                       # p: an emulib.panel.Panel
    if not p.capture or not p.capture.frames:
        raise SystemExit("FAIL: no frame composed (the frame clock?)")
    return bytes(p.capture.frames[-1])


def outside_b_row(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """the pixels (x, y bottom-up, as the canvas draws) lit in one frame and not the other, outside B's label row
    (emu.panel.lit: the frame's lit pixels, y from the top)"""
    from emu import panel as EP
    diff = set(EP.lit(a)) ^ set(EP.lit(b))
    out = [(x, EP.H - 1 - y) for x, y in sorted(diff)]
    return [(x, y) for x, y in out if not (B_ROW[0] <= x <= B_ROW[2] and B_ROW[1] <= y <= B_ROW[3])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--png-dir", default="out/para_vmenu")
    a = ap.parse_args()
    import emu_modulation as MO                                      # its machine recipe (scripts/, on sys.path)
    from emulib.panel import ENCODER_PUSH, SETTLE, Panel
    root = pathlib.Path(__file__).resolve().parent.parent
    sym = json.loads((root / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    need = [n for n in ("vm_sets", "vm_seen") if n not in sym]
    if need:
        print(f"FAIL: not in the layout: {need}")
        return 1
    if not hasattr(Panel, "frame_clock"):
        print("FAIL: emulib.panel.Panel has no frame_clock (4c7a49ff): the screen would not redraw after a turn")
        return 1
    from emu_waverider_menu import frames_va

    def setup(machine_type: int, mod0: int = 0):
        m = MO.machine(a.build, a.snapshot)
        p = Panel(m, png_dir=a.png_dir)
        p.frame_clock(frames_va(root))
        p.settle(3_000_000)
        s = m.long(MO.KIT) + 52
        m.write(s + 0xDE, bytes([machine_type]))
        m.write(s + MOD_AT, struct.pack(">H", mod0))
        m.flush()
        p.tap(VOICE)
        p.settle(20_000_000)
        return m, p, s

    def mod(m, s) -> int:
        return struct.unpack(">H", m.read(s + MOD_AT, 2))[0]

    def held_turn(m, p, enc: int, delta: int, n: int) -> None:
        dwell = SETTLE // 2
        p.hold(ENCODER_PUSH[enc], dwell)
        for _ in range(n):
            m.pc = p.panelin.encoder(m.m, p.profile, enc, delta)
            p.settle(dwell)
        p.let_go(ENCODER_PUSH[enc], dwell)
        p.settle(HOLD_GAP)

    report: dict = {}
    # 1. a stock machine's track
    m, p, s = setup(WAVETONE)
    stock_screen = frame(p)
    p.screen("1_stock_voice")
    held_turn(m, p, ENC_B, +1, 4)
    held_turn(m, p, ENC_C, +1, 4)
    after = frame(p)
    p.screen("1_stock_after_BC")
    check("stock track: B and C turned, the screen as before", after == stock_screen)
    check("stock track: MOD and vm_sets untouched", mod(m, s) == 0 and m.long(sym["vm_sets"]) == 0,
          f"MOD {mod(m, s):#06x}, vm_sets {m.long(sym['vm_sets'])}")
    # 2. an ANALOG 2 track
    m, p, s = setup(ANALOG2)
    para_screen = frame(p)
    p.screen("2_para_voice")
    diff = outside_b_row(stock_screen, para_screen)
    check("ANALOG 2 track: the screen as the stock track's but inside B's label row", not diff,
          f"{len(diff)} pixels outside, first {diff[:4]}")
    check("ANALOG 2 track: B's label row drawn (PARA OFF)", para_screen != stock_screen)
    # 3. one hold a step
    got_r, got_l = [], []
    for _ in STEPS_RIGHT:
        held_turn(m, p, ENC_B, +1, 4)
        got_r.append(mod(m, s))
    on_screen = frame(p)
    p.screen("3_para_right")
    for _ in STEPS_LEFT:
        held_turn(m, p, ENC_B, -1, 4)
        got_l.append(mod(m, s))
    p.screen("3_para_left")
    check("B right, a step a hold: PARA ON (stored 0x0300), held at ON", tuple(got_r) == STEPS_RIGHT,
          str([hex(v) for v in got_r]))
    check("B left, a step a hold: PARA OFF, held at OFF", tuple(got_l) == STEPS_LEFT, str([hex(v) for v in got_l]))
    check("vm_sets: one step up, one down", m.long(sym["vm_sets"]) == 2, str(m.long(sym["vm_sets"])))
    on_diff = outside_b_row(para_screen, on_screen)
    check("PARA ON: the screen differs from OFF's only inside B's label row, and does differ", not on_diff
          and on_screen != para_screen, f"{len(on_diff)} pixels outside")
    # 4. a JUNO track
    m, p, s = setup(JUNO)
    juno_screen = frame(p)
    p.screen("4_juno_voice")
    check("JUNO track: the screen as the ANALOG 2 track's (PARA OFF in B's row)", juno_screen == para_screen)
    held_turn(m, p, ENC_B, +1, 4)
    check("JUNO track: B right, a step: PARA ON", mod(m, s) == 0x0300, hex(mod(m, s)))
    juno_on = frame(p)
    p.screen("4_juno_on")
    check("JUNO track: PARA ON drawn as on the ANALOG 2 track", juno_on == on_screen)
    held_turn(m, p, ENC_B, -1, 4)
    check("JUNO track: B left, a step: PARA OFF, the screen as before", mod(m, s) == 0x0000
          and frame(p) == juno_screen, hex(mod(m, s)))
    report["juno"] = {"on": juno_on == on_screen, "mod_after_left": hex(mod(m, s))}
    # 5. an older project's value, against a fresh ON (stored 0x0300)
    m, p, s = setup(ANALOG2, 0x0300)
    fresh_on = frame(p)
    m, p, s = setup(ANALOG2, 0x0100)
    old_screen = frame(p)
    p.screen("5_old_value")
    check("an older project's MOD 0x0100 (2 pitches then): drawn as PARA ON (a fresh ON track's screen)",
          old_screen == fresh_on and fresh_on != para_screen)
    held_turn(m, p, ENC_B, -1, 4)
    check("... B left, a step: PARA OFF", mod(m, s) == 0x0000, hex(mod(m, s)))
    report.update({"right": [hex(v) for v in got_r], "left": [hex(v) for v in got_l],
                   "vm_sets": m.long(sym["vm_sets"]), "outside_b_row": len(diff)})
    report["ok"] = not FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS)) if FAILS else "PASS: PARA on the VOICE menu (stock places as stock's, B OFF / ON, older values ON)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
