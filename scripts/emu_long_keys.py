"""[TEMPO] and [PRESET] held a second (csrc/inserts/ovw.c; 2026-11-21) in the ColdFire emulator: the gate step `longkeys`.

    emu_long_keys.py --build BUILD.syx --snapshot SNAP --work DIR [--stock-snapshot SNAP]

The User: "put the CPU/RAM overview on a long press of the METRONOME button and not FUNC click-and-hold" (the DN2's
metronome is METRO on the [TEMPO] screen) and "SAMPLE BROWSER on a long press of PRESET". Stock 1.12 (measured,
2026-11-21): [TEMPO] and [PRESET] act on the RELEASE only (the TEMPO screen, the PRESET / KIT menu; the same after a
1.4 s hold); their press and hold change nothing; FUNC + [TEMPO] is tap tempo, FUNC + [PRESET] PERFORM KIT.

On the build and its own snapshot, from a SYN page, and stock 1.12 on its own snapshot (ui1200M beside SNAP):
 1. [TEMPO] tapped, and held 0.5 s: nothing while held; the release opens the TEMPO screen, pixel for pixel stock's
    (the same steps on stock); a tap closes it: the screen before;
 2. [TEMPO] held 1.3 s: the system meter up (mtr_big, ovw_tempo_opens) over the page; let go: gone, the screen before
    (no TEMPO screen: the release dropped); FUNC tapped then held (the old gesture): no meter;
 3. FUNC + [TEMPO]: tap tempo, pixel for pixel stock's; no meter;
 4. [PRESET] tapped, and held 0.5 s: the PRESET / KIT menu on the release, pixel for pixel stock's; a tap closes it;
 5. [PRESET] held 1.3 s on a track with a sample machine (sound+0xDE 8): the sample browser open (smp_fb_open) for the
    track (LOAD TRK offered: 5 actions on a sample in PROJECT RAM); let go: the browser still up, the screen unchanged
    (no PRESET menu); NO closes it, the screen before;
 6. the same on a track with no sample machine (FM TONE): browse only (smp_fb_browse), no LOAD TRK in either store's
    action list; NO closes it;
 7. FUNC + [PRESET]: PERFORM KIT toggled, pixel for pixel stock's, no browser (and again: back as it was);
 8. negative control, stock 1.12: [TEMPO] and [PRESET] held 1.3 s: no meter, no browser (the screen unchanged while
    held, the model's meter or browser screen differs), their release the TEMPO screen and the PRESET menu;
 and no fault. Exit 0 and "LONG KEYS OK" when every fact holds (WORK/longkeys.json, PNGs).
"""

from __future__ import annotations

import argparse
import gc
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_mix_overview as MO  # noqa: E402  (its Rig, rows, diff)
from emulib.panel import NO  # noqa: E402

FUNC, SYN, TEMPO, PRESET = (2, 0), (0, 1), (1, 0), (0, 6)
KIT_PTR, UI_TRACK = 0x800052A0, 0x42432A6C
HOLD, HALF, SETTLE = 160, 60, 1000      # panel ticks (121 a second)
FACTS: dict[str, bool] = {}


def fact(what: str, ok: bool, detail: str = "") -> None:
    FACTS[what] = bool(ok)
    print(f"  {'ok ' if ok else 'BAD'} {what}" + (f"  ({detail})" if detail and not ok else ""), flush=True)


def rig(build, snapshot, work, lay=None):
    r = MO.Rig(build, snapshot, work)
    r.lay = lay
    return r


def tap(r, key, after=40):
    r.p.press_for(key, 8)
    r.p.release_for(key, after)


def to_syn(r):
    tap(r, SYN, 40)
    r.ticks(SETTLE)


def stock_like_steps(r, tag) -> dict:
    """the steps run alike on ours and on stock: taps, half-second holds, FUNC + key"""
    out = {}
    to_syn(r)
    out["pre"] = r.shot(f"{tag}_pre")
    for name, key in (("tempo", TEMPO), ("preset", PRESET)):
        tap(r, key, 60)
        out[f"{name}_tap"] = r.shot(f"{tag}_{name}_tap")
        tap(r, key, 60)
        r.ticks(SETTLE)
        out[f"{name}_tap_closed"] = r.shot(f"{tag}_{name}_tap_closed")
        r.p.press_for(key, HALF)
        out[f"{name}_h05_held"] = r.shot(f"{tag}_{name}_h05_held")
        r.p.release_for(key, 60)
        out[f"{name}_h05"] = r.shot(f"{tag}_{name}_h05")
        tap(r, key, 60)
        r.ticks(SETTLE)
        out[f"{name}_h05_closed"] = r.shot(f"{tag}_{name}_h05_closed")
    r.p.press_for(FUNC, 10)
    tap(r, TEMPO, 20)
    r.p.release_for(FUNC, 20)
    out["func_tempo"] = r.shot(f"{tag}_func_tempo")
    to_syn(r)
    r.p.press_for(FUNC, 10)
    tap(r, PRESET, 20)
    r.p.release_for(FUNC, 20)
    out["func_preset"] = r.shot(f"{tag}_func_preset")
    r.p.press_for(FUNC, 10)
    tap(r, PRESET, 20)
    r.p.release_for(FUNC, 20)
    to_syn(r)
    out["end"] = r.shot(f"{tag}_end")
    return out


def held_steps(r, tag) -> dict:
    """[TEMPO] and [PRESET] held 1.3 s, from the SYN page"""
    out = {}
    to_syn(r)
    out["pre"] = r.shot(f"{tag}_hpre")
    r.p.press_for(TEMPO, HOLD)
    out["tempo_held"] = r.shot(f"{tag}_tempo_held")
    r.p.release_for(TEMPO, 60)
    r.ticks(SETTLE)
    out["tempo_after"] = r.shot(f"{tag}_tempo_after")
    tap(r, NO, 40)                       # (stock: its TEMPO screen closed by NO)
    to_syn(r)
    out["pre2"] = r.shot(f"{tag}_hpre2")
    r.p.press_for(PRESET, HOLD)
    out["preset_held"] = r.shot(f"{tag}_preset_held")
    r.p.release_for(PRESET, 60)
    out["preset_after"] = r.shot(f"{tag}_preset_after")
    return out


def set_type(r, ty: int) -> int:
    kit = r.m.long(KIT_PTR)
    t = r.m.read(UI_TRACK, 1)[0] & 15
    va = kit + 52 + 1163 * t + 0xDE
    old = r.m.read(va, 1)[0]
    r.m.write(va, bytes([ty & 0xFF]))
    r.m.flush()
    return old


def actions(r, store: int) -> list[int]:
    lay = r.lay
    keep = r.m.long(lay["smp_fb_store"])
    r.wlong(lay["smp_fb_store"], store)
    n = MO.EM.guest(r.m, lay["smp_fb_nactions"], 0) & 0xFFFFFFFF
    acts = [MO.EM.guest(r.m, lay["smp_fb_action"], 0, a) & 0xFF for a in range(n)]
    r.wlong(lay["smp_fb_store"], keep)
    return acts


def close_browser(r) -> bool:
    for _ in range(6):
        if not r.m.long(r.lay["smp_fb_open"]):
            return True
        tap(r, NO, 40)
    return not r.m.long(r.lay["smp_fb_open"])


def ours(a, work, lay) -> dict:
    r = rig(a.build, a.snapshot, work / "ours", lay)
    r.m.write(lay["mtr_start_done"], (1).to_bytes(4, "big"))
    sh = stock_like_steps(r, "o")
    D = MO.diff
    fact("[TEMPO] tapped: the TEMPO screen on the release; a tap closes it, the screen before",
         D(sh["tempo_tap"], sh["pre"]) > 300 and D(sh["tempo_tap_closed"], sh["pre"]) == 0)
    fact("[TEMPO] held 0.5 s: nothing while held; its release the TEMPO screen",
         D(sh["tempo_h05_held"], sh["pre"]) == 0 and D(sh["tempo_h05"], sh["tempo_tap"]) == 0)
    fact("[PRESET] tapped: the PRESET / KIT menu on the release; a tap closes it, the screen before",
         D(sh["preset_tap"], sh["pre"]) > 300 and D(sh["preset_tap_closed"], sh["pre"]) == 0)
    fact("[PRESET] held 0.5 s: nothing while held; its release the menu",
         D(sh["preset_h05_held"], sh["pre"]) == 0 and D(sh["preset_h05"], sh["preset_tap"]) == 0)
    up0 = r.long("mtr_big")
    fact("FUNC + [TEMPO] (tap tempo), FUNC + [PRESET] (PERFORM KIT): no meter, no browser",
         up0 == 0 and r.long("smp_fb_open") == 0)

    # 2. the meter
    to_syn(r)
    pre = r.shot("o_m_pre")
    t0, s0 = r.long("ovw_tempo_opens"), r.long("mtr_big_shows")
    r.p.press_for(TEMPO, HOLD)
    held = r.shot("o_m_held")
    big = r.long("mtr_big")
    fact("[TEMPO] held 1.3 s: the system meter up over the page (mtr_big, opened once)",
         big == 1 and r.long("ovw_tempo_opens") == t0 + 1 and r.long("mtr_big_shows") == s0 + 1
         and D(held, pre) > 300, f"mtr_big {big}")
    r.p.release_for(TEMPO, 60)
    r.ticks(SETTLE)
    after = r.shot("o_m_after")
    fact("... let go: the meter gone, the screen before (no TEMPO screen: the release dropped)",
         r.long("mtr_big") == 0 and D(after, pre) == 0, f"{D(after, pre)} px")
    r.p.press_for(FUNC, 8)
    r.p.release_for(FUNC, 15)
    r.p.press_for(FUNC, 40)
    old = r.long("mtr_big")
    r.p.release_for(FUNC, 40)
    fact("FUNC tapped then held (the old gesture): no meter", old == 0)

    # 5. the browser on a sample track
    keep_ty = set_type(r, 8)
    to_syn(r)
    pre5 = r.shot("o_b_pre")
    p0 = r.long("ovw_preset_opens")
    r.p.press_for(PRESET, HOLD)
    bheld = r.shot("o_b_held")
    opened = r.long("smp_fb_open") == 1 and r.long("smp_fb_browse") == 0 and r.long("ovw_preset_opens") == p0 + 1
    r.p.release_for(PRESET, 60)
    bafter = r.shot("o_b_after")
    acts_ram = actions(r, 0)
    fact("[PRESET] held 1.3 s on a sample track: the browser for the track (LOAD TRK offered)",
         opened and D(bheld, pre5) > 300 and 0 in acts_ram and len(acts_ram) == 5, f"{acts_ram}")
    fact("... let go: the browser still up, the screen unchanged (no PRESET menu)",
         r.long("smp_fb_open") == 1 and D(bafter, bheld) == 0, f"{D(bafter, bheld)} px")
    closed = close_browser(r)
    r.ticks(SETTLE)
    fact("... NO closes it: the screen before", closed and D(r.shot("o_b_closed"), pre5) == 0)

    # 6. browse only
    set_type(r, 0)
    to_syn(r)
    r.p.press_for(PRESET, HOLD)
    r.p.release_for(PRESET, 60)
    r.shot("o_bb_after")
    acts_ram, acts_lib = actions(r, 0), actions(r, 1)
    fact("[PRESET] held 1.3 s on an FM TONE track: browse only (no LOAD TRK in either store)",
         r.long("smp_fb_open") == 1 and r.long("smp_fb_browse") == 1 and 0 not in acts_ram and 0 not in acts_lib
         and len(acts_ram) == 4, f"ram {acts_ram} lib {acts_lib}")
    fact("... NO closes it", close_browser(r))
    set_type(r, keep_ty)
    faults = list(getattr(r.m, "faults", []))
    fact("no fault (no guest exception)", not faults, str(faults[:3]))
    r.m = r.p = None
    return sh


def stock(a, work, o) -> None:
    snap = a.stock_snapshot or str(pathlib.Path(a.snapshot).parent / "ui1200M.snap")
    r = rig(None, snap, work / "stock")
    sh = stock_like_steps(r, "s")
    D = MO.diff
    keys = [k for k in sh if k not in ("pre", "end")]

    def cmp(k):                          # FUNC held: our load labels in the title bar's right end (meter.c, as ever)
        if not k.startswith("func_"):
            return D(sh[k], o[k])
        return sum(1 for y in range(64) for x in range(128) if (y >= 10 or x < 96) and sh[k][y][x] != o[k][y][x])
    fact("stock 1.12: the same taps, half-second holds, FUNC + [TEMPO] and FUNC + [PRESET]: every screen pixel for "
         "pixel ours (with FUNC held, but for our load labels' corner)", all(cmp(k) == 0 for k in keys),
         str({k: cmp(k) for k in keys}))
    h = held_steps(r, "s")
    fact("negative control, stock 1.12: [TEMPO] held 1.3 s changes nothing while held (no meter); its release the "
         "TEMPO screen", D(h["tempo_held"], h["pre"]) == 0 and D(h["tempo_after"], sh["tempo_tap"]) == 0)
    fact("negative control, stock 1.12: [PRESET] held 1.3 s changes nothing while held (no browser); its release the "
         "PRESET / KIT menu", D(h["preset_held"], h["pre2"]) == 0 and D(h["preset_after"], sh["preset_tap"]) == 0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--stock-snapshot", default=None)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    need = [k for k in ("ovw_tempo_opens", "ovw_preset_opens", "mtr_big", "mtr_big_shows", "mtr_start_done",
                        "smp_fb_open", "smp_fb_browse", "smp_fb_store", "smp_fb_nactions", "smp_fb_action")
            if k not in lay]
    if need:
        print(f"LONG KEYS FAILED: not in the layout: {need}")
        return 1
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        o = ours(a, work, lay)
    except Exception as e:  # a guest fault or a harness error: the step fails with it
        fact(f"ours ran to the end ({type(e).__name__}: {e})", False)
        o = None
    gc.collect()
    if o:
        stock(a, work, o)
    good = bool(FACTS) and all(FACTS.values())
    (work / "longkeys.json").write_text(json.dumps({"facts": FACTS}, indent=1))
    print("LONG KEYS OK" if good else "LONG KEYS FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
