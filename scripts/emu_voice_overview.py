"""The VOICE key's overview (csrc/inserts/ovw.c, ovw_draw.c voice_view) in the ColdFire emulator: part of the overviews
gate step (scripts/emu_overviews.py runs it).

    emu_voice_overview.py --build BUILD(.syx, or its sections' folder) --snapshot SNAP --work DIR

Stock 1.12 (measured, stock and ours alike, 2026-11-19): VOICE's press and its hold change nothing on the screen (3.3 s
held); its release opens the VOICE menu (VOICE SETUP), or closes it when it is open, however long the hold.

On the build's own snapshot, the panel's own key bytes, keys held as the unit sends them (Panel.tick_clock):
 1. a tap and a 0.5 s hold of VOICE: nothing while held; the release opens the VOICE menu, pixel for pixel stock 1.12's
    (the same steps on stock's own snapshot); a tap closes it: the screen before, pixel for pixel;
 2. the VOICE menu's E (VOICES) turned on track 1: the field stock's getter reads (the overview's source) moves;
 3. a project: track 2 ANALOG 2 PARA ON with 2 fixed voices, track 3 JUNO PARA OFF with UNISON on (active), track 4
    MIDI, track 5 WaveTone with 1 fixed voice, track 6 ANALOG 2 PARA ON and UNISON on, track 7 FM TONE with 4 fixed
    voices. VOICE held 1.3 s: the overview, pixel for pixel dnfw.overviews.voice_render with the data read back from
    RAM (each track's sound, PARA, and UNISON / VOICES / the DYN pool through stock's own getters); the cells as
    expected (PAR, UNI, MID, MON, 2, 4, DYN); 0.6 s later the same, and nothing drawn alone meanwhile;
 4. let go: the screen of before the press, pixel for pixel (no VOICE menu); with the VOICE menu open, held 1.3 s: the
    overview over it; let go: the menu still open, pixel for pixel; a tap closes it;
 5. held 1.3 s again, FLTR tapped: the overview closes and FLTR's page comes as FLTR alone gives it, pixel for pixel;
    VOICE let go: still that page (no menu);
 6. FUNC held, then VOICE held 1.3 s: no overview (the screen FUNC alone gives); VOICE let go: the RECORDER opens
    (FUNC + VOICE, as before); FUNC + VOICE again closes it;
 7. negative control, stock 1.12 on its own snapshot: VOICE held 1.3 s shows no overview (the model's picture of step
    3 differs from its screen by more than 300 pixels: this check fails on stock) and its release opens the menu;
 and no fault (no guest exception). Exit 0 and "VOICE OVERVIEW OK" when every fact holds (WORK/voice.json, PNGs).
"""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

VOICE, FUNC, FLTR, SYN, TRK = (6, 0), (2, 0), (0, 2), (0, 1), (1, 7)
TRIG = [(3 + k // 8, k % 8) for k in range(16)]
KNOB_E = 4
UI_OWNER, VS_HOLDER, VS_OBJ = 0x4018AC5A, 0x4003E41A, 0x40030AF8   # as VoiceMenuView's draw (0x400282c6) reaches it
VS_VOICES, VS_SET_VOICES, VS_POOL = 0x40029054, 0x40029094, 0x40028FFC
VS_UNISON, VS_SET_UNISON = 0x40029126, 0x4002916C
OV_VOICE = 6
TYPE_AT, MOD_AT, PARA_ON = 0xDE, 20 + 2 * 37, 0x0300
WAVETONE, FMTONE, MIDI, ANALOG2, JUNO = 1, 0, 4, 51, 50
# (track, type, PARA on, UNISON on, VOICES: 0 DYN): tracks 2..7; track 3 is made the active one
PROJECT = [(1, ANALOG2, 1, 0, 2), (2, JUNO, 0, 1, 0), (3, MIDI, 0, 0, 0), (4, WAVETONE, 0, 0, 1), (5, ANALOG2, 1, 1, 0),
           (6, FMTONE, 0, 0, 4)]
ACTIVE = 2
HOLD, TAP, AFTER = 160, 20, 30          # panel ticks (121 a second): the overview comes at 121
FACTS: dict[str, bool] = {}


def fact(what: str, ok: bool, detail: str = "") -> None:
    FACTS[what] = bool(ok)
    print(f"  {'ok ' if ok else 'BAD'} {what}" + (f"  ({detail})" if detail and not ok else ""), flush=True)


def s8(v: int) -> int:
    v &= 0xFF
    return v - 256 if v & 0x80 else v


class Rig:
    """a machine on its UI, the panel and a few helpers"""

    def __init__(self, build, snapshot, png_dir):
        import emu_modulation as MO
        from emulib.panel import Panel
        self.MO = MO
        sec3 = None
        if build and pathlib.Path(build).is_dir():
            sec3 = (pathlib.Path(build) / "section_3_MAIN_OS.bin").read_bytes()
            build = None
        if build is None and sec3 is None:      # stock 1.12 on its own snapshot (it booted stock: nothing to put back)
            from emulib.machine import Machine
            self.m = Machine(snapshot)
        else:
            self.m = MO.machine(build, snapshot, sec3_in=sec3)
        self.p = Panel(self.m, png_dir=str(png_dir))
        self.p.tick_clock(MO.FRAMES)
        self.p.settle(3_000_000)
        for _ in range(40):                     # the UI's first frame
            if self.p.frames():
                break
            self.p.settle(10_000_000)
        self.p.run_ticks(60)

    def g(self, fn, *args):
        return self.MO.guest(self.m, fn, *args) & 0xFFFFFFFF

    def shot(self, name):
        import emu_overviews as EO
        path = self.p.screen(name)
        return EO.bitmap(path) if str(path).endswith(".png") else None

    def press(self, key, ticks):
        self.p.press_for(key, ticks)

    def release(self, key, ticks=AFTER):
        self.p.release_for(key, ticks)

    def tap(self, key):
        self.press(key, 10)
        self.release(key, TAP)

    def vs(self):
        return self.g(VS_OBJ, self.g(VS_HOLDER, self.g(UI_OWNER)))

    def word(self, va):
        return self.m.long(va)


def diff(a, b) -> int:
    if a is None or b is None:
        return 1 << 20
    return sum(1 for y in range(64) for x in range(128) if a[y][x] != b[y][x])


def body(a):
    """the screen below the title bar (rows 10..63), padded back to 64 rows"""
    return None if a is None else [[0] * 128 for _ in range(10)] + a[10:]


def short_steps(r: Rig, tag: str) -> dict:
    """step 1 (and its stock twin): tap, 0.5 s hold, each release's menu, a tap closing it"""
    out = {"pre": r.shot(f"{tag}_pre")}
    r.press(VOICE, 20)
    out["tap_held"] = r.shot(f"{tag}_tap_held")
    r.release(VOICE)
    out["tap_menu"] = r.shot(f"{tag}_tap_menu")
    r.tap(VOICE)
    out["tap_closed"] = r.shot(f"{tag}_tap_closed")
    r.press(VOICE, 60)
    out["h05_held"] = r.shot(f"{tag}_h05_held")
    r.release(VOICE)
    out["h05_menu"] = r.shot(f"{tag}_h05_menu")
    r.tap(VOICE)
    out["h05_closed"] = r.shot(f"{tag}_h05_closed")
    return out


def model(r: Rig, O, EO):
    """the overview as dnfw.overviews draws it from RAM read now -> (picture, the data)"""
    MO = r.MO
    kit = r.m.long(MO.KIT)
    vs = r.vs()
    snds = [bytes(r.m.read(kit + 52 + 1163 * t, 1163)) for t in range(16)]
    types = [s8(s[TYPE_AT]) for s in snds]
    names = [EO.syn_names(s)[0] for s in snds]
    para = [ty in (ANALOG2, JUNO) and (struct.unpack_from(">H", s, MOD_AT)[0] >> 8) != 0 for s, ty in zip(snds, types)]
    uni = [bool(r.g(VS_UNISON, vs, t) & 0xFF) for t in range(16)]
    voices = [s8(r.g(VS_VOICES, vs, t)) for t in range(16)]
    pool = s8(r.g(VS_POOL, vs))
    track = r.m.read(MO.UI_TRACK, 1)[0] & 15
    left, right, cells = O.voice_cells(names, types, para, uni, voices, pool)
    data = {"names": names, "types": types, "para": para, "unison": uni, "voices": voices, "pool": pool,
            "track": track, "left": left, "right": right, "cells": cells}
    return O.voice_render(left, right, cells, track), data


def set_project(r: Rig) -> None:
    MO = r.MO
    kit = r.m.long(MO.KIT)
    vs = r.vs()
    for t, ty, para, uni, v in PROJECT:
        r.m.write(kit + 52 + 1163 * t + TYPE_AT, bytes([ty & 0xFF]))
        r.m.write(kit + 52 + 1163 * t + MOD_AT, struct.pack(">H", PARA_ON if para else 0))
        r.g(VS_SET_UNISON, vs, t, uni)
        r.g(VS_SET_VOICES, vs, t, v)
    r.m.flush()
    r.press(TRK, 10)
    r.tap(TRIG[ACTIVE])
    r.release(TRK, AFTER)
    r.p.run_ticks(1000)                 # (the title shows the track's sound name for a few seconds, then the pattern's)


def ours(a, work: pathlib.Path, O, EO, lay) -> dict:
    r = Rig(a.build, a.snapshot, work / "ours")
    sh = short_steps(r, "ours")
    fact("VOICE tapped, held: nothing changes on the screen (as stock)", diff(sh["tap_held"], sh["pre"]) == 0)
    fact("VOICE held 0.5 s: nothing changes on the screen (as stock)", diff(sh["h05_held"], sh["pre"]) == 0)
    fact("... a tap's release and a 0.5 s hold's open the VOICE menu", diff(sh["tap_menu"], sh["pre"]) > 300
         and diff(sh["h05_menu"], sh["tap_menu"]) == 0)
    fact("... a tap closes the menu: the screen before, pixel for pixel", diff(sh["tap_closed"], sh["pre"]) == 0
         and diff(sh["h05_closed"], sh["pre"]) == 0)

    # 2. the VOICE menu's E: the field the overview reads
    vs = r.vs()
    before = s8(r.g(VS_VOICES, vs, 0))
    r.tap(VOICE)
    r.p.push_and_turn(KNOB_E, 1)
    r.p.run_ticks(AFTER)
    menu_e = r.shot("ours_menu_e")
    after = s8(r.g(VS_VOICES, vs, 0))
    r.tap(VOICE)
    r.g(VS_SET_VOICES, vs, 0, 0)                   # (track 1 back to DYN)
    fact("the VOICE menu's E (VOICES) turned: the field stock's getter reads moves", before != after,
         f"{before} -> {after}")

    # 3. the project, the overview held
    set_project(r)
    opens0, alone0 = r.word(lay["ovw_opens"]), r.word(lay["ovw_alone"])
    pre = r.shot("ours_pre")
    r.press(VOICE, HOLD)
    up = r.word(lay["ovw_up"])
    ovw = r.shot("ours_overview")
    pic, data = model(r, O, EO)
    r.p.run_ticks(75)
    ovw2 = r.shot("ours_overview_06s")
    alone1 = r.word(lay["ovw_alone"])
    c = data["cells"]
    fact("VOICE held 1.3 s: the VOICE overview is up (ovw_up)", up == OV_VOICE and r.word(lay["ovw_opens"]) == opens0 + 1,
         f"ovw_up {up}")
    fact("... pixel for pixel dnfw.overviews.voice_render from RAM", diff(ovw, pic) == 0, f"{diff(ovw, pic)} pixels")
    want = {1: ("PAR", "2"), 2: ("UNI", "DYN"), 3: ("", ""), 4: ("MON", "1"), 5: ("PAR", "DYN"), 6: ("PLY", "4")}
    got = {t: (c[t][1][1], c[t][2][1]) for t in want}
    fact("... the cells: PARA ON PAR (also with UNISON on), UNISON UNI, MIDI dots, one voice MON, fixed counts, DYN",
         got == want and c[3][0][1] == "MID" and data["track"] == ACTIVE and c[0][1][1] == "PLY", f"{got} {c[3][0]}")
    fact("... 0.6 s later the same; nothing drawn alone meanwhile (nothing moves)", diff(ovw2, pic) == 0
         and alone1 == alone0)

    # 4. let go
    r.release(VOICE)
    after_rel = r.shot("ours_released")
    fact("VOICE let go: the screen of before the press, pixel for pixel (no menu)", diff(after_rel, pre) == 0
         and r.word(lay["ovw_up"]) == 0, f"{diff(after_rel, pre)} pixels")

    # 4b. over the open VOICE menu: the overview over it; let go, the menu still open (stock's release would close it)
    r.tap(VOICE)
    menu = r.shot("ours_menu_open")
    r.press(VOICE, HOLD)
    over_menu = r.shot("ours_overview_over_menu")
    up4 = r.word(lay["ovw_up"])
    r.release(VOICE)
    menu_after = r.shot("ours_menu_after_overview")
    fact("over the open VOICE menu: the overview, as the model", up4 == OV_VOICE and diff(over_menu, pic) == 0
         and diff(menu, pre) > 300)
    fact("... let go: the VOICE menu still open, pixel for pixel", diff(menu_after, menu) == 0)
    r.tap(VOICE)
    fact("... a tap then closes it: the screen of before", diff(r.shot("ours_menu_closed4"), pre) == 0)

    # 5. another key closes it
    r.tap(FLTR)
    fltr_ref = r.shot("ours_fltr_alone")
    r.tap(SYN)
    pre5 = r.shot("ours_pre5")
    r.press(VOICE, HOLD)
    ovw5 = r.shot("ours_overview5")
    r.press(FLTR, 10)
    r.release(FLTR, TAP)
    closed = r.shot("ours_fltr_in_overview")
    up5 = r.word(lay["ovw_up"])
    r.release(VOICE)
    after5 = r.shot("ours_fltr_voice_released")
    # (below the title bar: stock slides the page's name in, then the pattern's comes back, by the clock)
    fact("held, FLTR tapped: the overview closes, FLTR's page as FLTR alone gives it", diff(ovw5, pic) == 0
         and up5 == 0 and diff(body(closed), body(fltr_ref)) == 0 and diff(body(fltr_ref), body(pre5)) > 300,
         f"{diff(body(closed), body(fltr_ref))}")
    fact("... VOICE let go: still FLTR's page (no menu)", diff(body(after5), body(fltr_ref)) == 0)
    r.tap(SYN)

    # 6. FUNC + VOICE: the RECORDER, no overview
    opens6 = r.word(lay["ovw_opens"])
    r.press(FUNC, 20)
    func_only = r.shot("ours_func_held")
    r.press(VOICE, HOLD)
    fv = r.shot("ours_func_voice_held")
    r.release(VOICE, TAP)
    r.release(FUNC, 60)                 # (0.5 s: a FUNC pressed again within 0.35 s is the system meter's)
    rec_on = r.m.long(lay["rec_overlay"])
    rec_shot = r.shot("ours_recorder")
    r.press(FUNC, 10)
    r.tap(VOICE)
    r.release(FUNC)
    rec_off = r.m.long(lay["rec_overlay"])
    fact("FUNC + VOICE held 1.3 s: no overview (the screen FUNC alone gives)", diff(fv, func_only) == 0
         and r.word(lay["ovw_opens"]) == opens6)
    fact("... let go: the RECORDER opens; FUNC + VOICE again closes it", rec_on == 1 and rec_off == 0
         and diff(rec_shot, func_only) > 300, f"rec {rec_on} -> {rec_off}")
    del menu_e
    out = {"short": {k: v is not None for k, v in sh.items()}, "model": {k: v for k, v in data.items() if k != "cells"},
           "cells": c, "shorts": sh, "pic": pic}
    r.m = r.p = None
    return out


def stock(a, work: pathlib.Path, ours_out: dict) -> None:
    snap = str(pathlib.Path(a.snapshot).parent / "ui1200M.snap")
    r = Rig(None, snap, work / "stock")
    sh = short_steps(r, "stock")
    o = ours_out["shorts"]
    fact("stock 1.12: the same tap and 0.5 s hold, every screen pixel for pixel ours", all(
        diff(sh[k], o[k]) == 0 for k in sh), str({k: diff(sh[k], o[k]) for k in sh}))
    pre = r.shot("stock_pre")
    r.press(VOICE, HOLD)
    held = r.shot("stock_held_13s")
    r.release(VOICE)
    menu = r.shot("stock_released")
    fact("negative control, stock 1.12: held 1.3 s, no overview (the model's picture differs: the check fails there)",
         diff(held, pre) == 0 and diff(held, ours_out["pic"]) > 300, f"{diff(held, ours_out['pic'])} pixels")
    fact("... and its release opens the VOICE menu (what the build drops after the overview)",
         diff(menu, sh["tap_menu"]) == 0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    O = importlib.import_module("dnfw.overviews")
    EO = importlib.import_module("emu_overviews")
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    need = [k for k in ("ovw_up", "ovw_opens", "ovw_alone", "rec_overlay") if k not in lay]
    if need:
        print(f"VOICE OVERVIEW FAILED: not in the layout: {need}")
        return 1
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    o = ours(a, work, O, EO, lay)
    gc.collect()
    stock(a, work, o)
    good = all(FACTS.values())
    (work / "voice.json").write_text(json.dumps({"facts": FACTS, "model": o["model"], "cells": o["cells"]}, indent=1))
    print("VOICE OVERVIEW OK" if good else "VOICE OVERVIEW FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
