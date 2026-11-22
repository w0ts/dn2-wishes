"""PARA on the VOICE key's LED (csrc/para/led.c, docs/leds.md) in the ColdFire emulator: the gate's check.

    emu_voiceled.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--json OUT]

The VOICE key is LED id 8 (phys 7). Stock 1.12 lights it teal (mode 2, palette 131) on the main screen when the active
track's UNISON is on, leaves it to the backlight (1, 1) otherwise, and white (2, 113) while the VOICE menu is open. The
build lights it magenta (2, 91) on a PARA ON track (ANALOG 2 or JUNO, MOD not 0), and only where stock decides.

On the build's own snapshot, the LEDs composed by stock's own compose (0x4002c854, its screen marked as stock marks
it), the panel UART's [0xB9, 7, value] bytes recorded as the driver sends them:

1. the hook: VOICE_LED_SITE holds `jsr pu_voice_led`;
2. on the main screen, against the same build with stock's bytes put back at the site (the negative control), for a
   WaveTone track and an ANALOG 2 track with PARA OFF, UNISON off and on: id 8 and the bytes as stock's ((1, 1) / `b9
   07 01`, (2, 131) / `b9 07 83`);
3. PARA ON (ANALOG 2, then JUNO), UNISON off and on: (2, 91) and `b9 07 5b`; the negative control gives stock's
   (2, 131) there instead (the check sees the hook's absence);
4. a view above that claimed VOICE (MainScreenView's own claimed-mask bit 8, its routine called directly): VOICE left
   unclaimed on a PARA ON track, as stock leaves it;
5. the VOICE menu open (the VOICE key, through the panel) on a PARA ON track: stock's white (2, 113);
6. the refresh, through the UI loop alone (no compose asked by the check): PARA turned ON on the active track ->
   pu_led_marks counts one, the UI composes, (2, 91) and `b9 07 5b`; the machine changed to WaveTone -> one more, the
   backlight back; another track (TRK + TRIG 2) that is PARA ON -> magenta; back to track 1 -> the backlight; an
   unchanged state asks for nothing.

Prints PASS or FAIL with each check; --json writes the numbers.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

LED_MGR, LED_DIRTY, COMPOSE = 0x4018AD9C, 0x4011D5F4, 0x4002C854
MSV_LEDS = 0x40060842                       # MainScreenView's LED routine (this, -, &claimed mask)
MSV_LED_VPTR = 0x401E07B4                   # its LED subobject's vptr; the thunk 0x40060e68 takes 108 off
UNI_GET, UNI_SET, UNI_OBJ, ACTIVE = 0x40029126, 0x4002916C, 0x40030AF8, 0x40046BFE
UART_PUT, LAST_SENT = 0x4000220C, 0x466B8420
VOICE_LED_SITE, VOICE_LED_STOCK = 0x40060D6E, bytes.fromhex("4eb940029126")
WAVETONE, ANALOG2, JUNO = 1, 51, 50
MOD_AT, TYPE_AT = 20 + 2 * 37, 0xDE
PARA_ON = 0x0300
VOICE_KEY, TRK, NO = (6, 0), (1, 7), (1, 3)
TRIG = [(3 + k // 8, k % 8) for k in range(16)]           # [TRIG 1..16], codes 25..40
BACKLIGHT, TEAL, WHITE, MAGENTA = (1, 1), (2, 131), (2, 113), (2, 91)
FAILS: list[str] = []


def check(what: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(what)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--png-dir", default="out/voiceled")
    a = ap.parse_args()
    import emu_modulation as MO
    from emu_waverider_menu import frames_va
    from emulib.panel import Panel
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7
    root = pathlib.Path(__file__).resolve().parent.parent
    sym = json.loads((root / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    need = [n for n in ("pu_voice_led", "pu_led_poll", "pu_led_sets", "pu_led_marks", "wr_screen_obj") if n not in sym]
    if need:
        print(f"FAIL: not in the layout: {need}")
        return 1

    m = MO.machine(a.build, a.snapshot)
    p = Panel(m, png_dir=a.png_dir)
    p.frame_clock(frames_va(root))
    p.settle(3_000_000)
    sent: list[int] = []

    def on_put(uc, addr, size, user):
        sp = uc.reg_read(UC_M68K_REG_A7)
        n, buf = struct.unpack(">II", bytes(uc.mem_read(sp + 4, 8)))
        b = bytes(uc.mem_read(buf, min(n, 8)))
        if len(b) == 3 and b[0] == 0xB9 and b[1] == 7:
            sent.append(b[2])

    m.uc.hook_add(UC_HOOK_CODE, on_put, begin=UART_PUT, end=UART_PUT)
    g = lambda fn, *args: MO.guest(m, fn, *args)          # noqa: E731
    lm = g(LED_MGR)
    screen = m.long(sym["wr_screen_obj"])
    for _ in range(30):                       # the UI's first draw records its screen (page.c wr_screen)
        if screen:
            break
        p.settle(10_000_000)
        screen = m.long(sym["wr_screen_obj"])
    report: dict = {"lm": hex(lm), "screen": hex(screen)}
    if not lm or not screen:
        print(f"FAIL: no LedManager ({lm:#x}) or no screen ({screen:#x}) in the snapshot")
        return 1

    # 1. the hook
    site = m.read(VOICE_LED_SITE, 6)
    hook = bytes.fromhex("4eb9") + struct.pack(">I", sym["pu_voice_led"])
    check("the hook: MainScreenView's UNISON test is jsr pu_voice_led", site == hook, site.hex())

    def find_msv() -> int:
        want = struct.pack(">I", MSV_LED_VPTR)
        for page in range(0x44000000, 0x48000000, 0x100000):
            try:
                blob = m.read(page, 0x100000)
            except Exception:                    # noqa: BLE001
                continue
            i = blob.find(want)
            while i >= 0:
                if i % 2 == 0:
                    return page + i - 108
                i = blob.find(want, i + 1)
        return 0

    msv = find_msv()
    if not msv:
        print("FAIL: MainScreenView not found")
        return 1
    track = g(ACTIVE, m.long(msv + 164))
    uni = g(UNI_OBJ, m.long(msv + 168))
    report.update({"msv": hex(msv), "track": track})
    kit = m.long(MO.KIT)

    def sound(t: int) -> int:
        return kit + 52 + 1163 * t

    def set_track(t: int, mtype: int, mod: int, unison: int) -> None:
        m.write(sound(t) + TYPE_AT, bytes([mtype]))
        m.write(sound(t) + MOD_AT, struct.pack(">H", mod))
        g(UNI_SET, uni, t, unison)

    def led() -> tuple[int, int]:
        return m.long(lm + 40 + 32), m.long(lm + 256 + 32)

    def compose() -> tuple[tuple[int, int], int, list[int]]:
        """stock's compose, its screen marked as stock marks it -> (id 8, phys 7's last value sent, bytes sent)"""
        sent.clear()
        g(LED_DIRTY, screen)
        g(COMPOSE, screen - 64)
        return led(), m.read(LAST_SENT + 7, 1)[0], list(sent)

    def stock_site(on: bool) -> None:
        m.write(VOICE_LED_SITE, VOICE_LED_STOCK if on else hook)
        m.flush()

    def case(mtype: int, mod: int, unison: int) -> tuple:
        set_track(track, mtype, mod, unison)
        compose()                                # from a known LED state: the case before it, sent
        set_track(track, WAVETONE, 0, 0)
        compose()
        set_track(track, mtype, mod, unison)
        return compose()

    # 2. stock's tracks against the negative control
    rows = {}
    for name, mt, mod in (("WaveTone", WAVETONE, 0), ("ANALOG 2 PARA OFF", ANALOG2, 0)):
        for un in (0, 1):
            ours = case(mt, mod, un)
            stock_site(True)
            st = case(mt, mod, un)
            stock_site(False)
            want = (TEAL if un else BACKLIGHT)
            rows[f"{name} unison {un}"] = {"ours": ours, "stock": st}
            check(f"{name}, UNISON {'on' if un else 'off'}: VOICE {ours[0]} as stock's {st[0]}, {want}",
                  ours[0] == st[0] == want and ours[1] == st[1] == want[1], f"ours {ours}, stock {st}")
    # 3. PARA ON
    sets0 = m.long(sym["pu_led_sets"])
    for name, mt in (("ANALOG 2", ANALOG2), ("JUNO", JUNO)):
        for un in (0, 1):
            ours = case(mt, PARA_ON, un)
            rows[f"{name} PARA ON unison {un}"] = {"ours": ours}
            check(f"{name} PARA ON, UNISON {'on' if un else 'off'}: VOICE magenta {MAGENTA}, b9 07 5b sent",
                  ours[0] == MAGENTA and ours[1] == 91 and 91 in ours[2], str(ours))
    check("pu_led_sets counted the magenta ones", m.long(sym["pu_led_sets"]) > sets0,
          f"{sets0} -> {m.long(sym['pu_led_sets'])}")
    stock_site(True)
    neg = case(ANALOG2, PARA_ON, 1)
    stock_site(False)
    rows["negative control PARA ON unison 1"] = {"stock": neg}
    check("negative control: stock's bytes at the site, PARA ON, UNISON on -> stock's teal, not magenta",
          neg[0] == TEAL and 91 not in neg[2], str(neg))

    # 4. a view above claimed VOICE: MainScreenView's routine with its claimed-mask bit 8 set
    set_track(track, ANALOG2, PARA_ON, 1)
    flags = m.alloc(16)
    sets1 = m.long(sym["pu_led_sets"])
    for bit8 in (0, 0x100):
        m.write(flags, struct.pack(">II", bit8, 0))
        g(0x4002C3C6, lm)                         # the compose's clear
        g(MSV_LEDS, msv, 0, flags)
        got = led()
        rows[f"claimed mask {bit8:#x}"] = got
        want = MAGENTA if not bit8 else (0, 0)
        check(f"MainScreenView alone, the claimed mask {bit8:#x}: VOICE {want}", got == want, str(got))
    check("... pu_voice_led never asked with VOICE claimed above (one set for the two calls)",
          m.long(sym["pu_led_sets"]) == sets1 + 1, f"{sets1} -> {m.long(sym['pu_led_sets'])}")

    # 5. the VOICE menu open on a PARA ON track
    set_track(track, ANALOG2, PARA_ON, 0)
    p.tap(VOICE_KEY)
    p.settle(20_000_000)
    p.screen("voice_menu_para_on")
    menu = compose()
    rows["VOICE menu PARA ON"] = menu
    check("VOICE menu open, PARA ON: stock's white (2, 113), b9 07 71", menu[0] == WHITE and menu[1] == 113, str(menu))
    p.tap(NO)                                     # the menu closed
    p.settle(30_000_000)

    # 6. the refresh through the UI loop alone
    def ui(steps: int = 40_000_000) -> tuple:
        sent.clear()
        p.settle(steps)
        return led(), m.read(LAST_SENT + 7, 1)[0], list(sent)

    set_track(track, WAVETONE, 0, 0)
    for t in range(16):
        if t != track:
            set_track(t, WAVETONE, 0, 0)
    base = ui()
    marks0 = m.long(sym["pu_led_marks"])
    set_track(track, ANALOG2, PARA_ON, 0)
    on = ui()
    marks1 = m.long(sym["pu_led_marks"])
    check("PARA turned ON on the active track: one refresh asked, VOICE magenta, b9 07 5b sent",
          marks1 == marks0 + 1 and on[0] == MAGENTA and on[1] == 91 and 91 in on[2], f"marks {marks0}->{marks1}, {on}")
    same = ui()
    check("nothing changed: no refresh asked", m.long(sym["pu_led_marks"]) == marks1, f"{same}")
    m.write(sound(track) + TYPE_AT, bytes([WAVETONE]))   # the machine changed, MOD kept
    off = ui()
    marks2 = m.long(sym["pu_led_marks"])
    check("machine changed to WaveTone (MOD kept): one refresh asked, the backlight back, b9 07 01 sent",
          marks2 == marks1 + 1 and off[0] == BACKLIGHT and off[1] == 1 and 1 in off[2], f"marks {marks1}->{marks2}, {off}")
    other = (track + 1) % 16
    set_track(other, JUNO, PARA_ON, 0)
    p.hold(TRK, 5_000_000)
    p.tap(TRIG[other], 5_000_000)
    p.let_go(TRK, 5_000_000)
    moved = ui()
    t_now = m.read(MO.UI_TRACK, 1)[0]
    check(f"another track (TRK + TRIG {other + 1}), PARA ON: the active track {t_now}, VOICE magenta",
          t_now == other and moved[0] == MAGENTA and moved[1] == 91, f"{moved}")
    p.hold(TRK, 5_000_000)
    p.tap(TRIG[track], 5_000_000)
    p.let_go(TRK, 5_000_000)
    back = ui()
    check(f"back to track {track + 1} (WaveTone): the backlight", m.read(MO.UI_TRACK, 1)[0] == track
          and back[0] == BACKLIGHT and back[1] == 1, f"{back}")
    report.update({"rows": {k: str(v) for k, v in rows.items()}, "base": str(base), "on": str(on), "off": str(off),
                   "moved": str(moved), "back": str(back), "marks": m.long(sym["pu_led_marks"]),
                   "sets": m.long(sym["pu_led_sets"])})
    report["ok"] = not FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS)) if FAILS else "PASS: PARA on the VOICE key's LED (magenta on PARA ON, stock's "
          "elsewhere, the VOICE menu's white kept, refreshed on a change)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
