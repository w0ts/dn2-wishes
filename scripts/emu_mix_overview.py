"""The OUTPUTS overview (FUNC + [MOD] held a second; csrc/inserts/ovw.c, ovw_draw.c mix_view, csrc/meter/mixer.c) in
the ColdFire emulator: the gate step `mixovw`. 2026-11-21 it replaced that day's MIXER overview (the User: "I want to see
what clips. So only what is not float, by definition"; "We have many more track with overbridge"): every fixed-point
output, a bar each (the tracks' and returns' own Overbridge / USB channels, Overbridge / USB main, the analog outputs,
the input, the recorder), its clip mark from the overview's own stamps (mix_ov_clip_at).

    emu_mix_overview.py --build BUILD.syx --snapshot SNAP --work DIR [--stock-snapshot SNAP]

Stock 1.12 (measured, 2026-11-21): FUNC + [MOD] opens the MIXER on the PRESS (Compressor 1/5; on the MIXER the next
page), shows its value view while held, changes nothing on the release. Ours holds the press back and plays the tap
on a release before the second; held the second, the overview; let go, the screen of before.

The emulator runs no DSP: the levels it would send are written into mix_acc at every UI pass (a hook on mix_poll's
entry, as emu_mixmeter.py), the clips as stamps in mix_ov_clip_at; the USB mode (stock's word 0x4058F2A8, its USB OUT
pair at 0x80005362..65) and the recorder's state (rec_state) are held where a step sets them (the same hook, and one on
mix_ovw_get's entry). On the build and its own snapshot:
 1. from a SYN page, FUNC + [MOD] tapped: no overview; the tap played (ovw_mix_taps), the MIXER up on Compressor 1/5
    (stock's view, page 0); again on the MIXER: its next page; FUNC let go before MOD: the MIXER all the same;
 2. Overbridge mode, from the SYN page, FUNC + [MOD] held 1.6 s with fixed levels on all 25 units: the overview is up
    (ovw_up 7), the DSP's levels asked (mix_want), every bar but the recorder's in use, each one's pixels exactly
    dnfw.overviews.mix_px of its own unit's level, and the glass pixel for pixel dnfw.overviews.outs_render with the
    state read back from RAM;
 3. the levels changed while held: within 0.25 s the glass follows (the model again), the old peaks as ticks; the
    redraws alone over the glass (ovw_alone), the takes at most 10.6 a second;
 4. clips stamped for the overview on track 3's channel, return R and the analog outputs, and a MIXER stamp (the CLIP
    label's) on track 6: the marks on track 3, R, OUT L and R alone, "CLIP 3 R OUT" in the title, as the model;
 5. USB audio mode, USB OUT = track 3's pair, the recorder recording: track 3, OUT, IN, REC in use, every other bar
    dotted, USB under the main's pair, as the model; then neither (USB audio off, not recording): OUT and IN alone;
 6. MOD let go: the screen of before the press, pixel for pixel; no MIXER (no tap played);
 7. on the MIXER (Internal Mixer 2/5), held 1.6 s: the overview over it; let go: the MIXER page as before, pixel for
    pixel, its page unchanged;
 8. held 1.6 s, SYN tapped while it is held: no overview after, the SYN page; MOD let go: no MIXER;
 9. the cost with every bar moving at every update: the ColdFire's instructions in ovw_poll, mix_poll and wr_screen (the overview's paint, panel_diff,
    the levels) while the overview is up, in % of the CPU (the unit's ~132 M instructions a second), under 1 %; on the SYN page with
    nothing of ours up, for reference;
10. negative control, stock 1.12 on its own snapshot (ui1200M beside SNAP): FUNC + [MOD] held 1.6 s shows no overview
    (the model's picture differs by more than 300 pixels) and the MIXER came on the press;
 and no fault. Exit 0 and "MIXER OVERVIEW OK" when every fact holds (WORK/mixovw.json, PNGs).
"""

from __future__ import annotations

import argparse
import gc
import json
import pathlib
import random
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_modulation as EM  # noqa: E402

FUNC, MOD, SYN = (2, 0), (0, 5), (0, 1)
MIXER_VIEW = 0x401E292C
FRAMES = 0x4058F8D4
OV_MIX = 7
SETTLE = 1000                           # panel ticks: stock's title back to the pattern's name (it shows the page's or
                                        # the sound's for a few seconds after a page comes)
HOLD = 195                              # panel ticks (121 a second): 1.6 s
UNIT_IPS = 132e6                        # the unit's ColdFire, instructions a second (emu_mixcpu.py)
MIX_CH = 25                             # the DSP's levels units (sampler.machines LV_CH), mix_acc's [2][MIX_CH]
USB_MODE, USB_OUT_ON, USB_OUT_SEL = 0x4058F2A8, 0x80005362, 0x80005364
FACTS: dict[str, bool] = {}
LEVELS = [16384, 12000, 9000, 6000, 4000, 2500, 1500, 900, 500, 300, 180, 100, 76, 60, 0, 20000,
          8000, 2000, 700, 15000, 11000, 5000, 3000, 13000, 9500]


def fact(what: str, ok: bool, detail: str = "") -> None:
    FACTS[what] = bool(ok)
    print(f"  {'ok ' if ok else 'BAD'} {what}" + (f"  ({detail})" if detail and not ok else ""), flush=True)


def rows(g: bytes) -> list[list[int]]:
    return [[g[8 * x + 7 - (r >> 3)] >> (r & 7) & 1 for x in range(128)] for r in range(64)]


def diff(a, b) -> int:
    return sum(1 for y in range(64) for x in range(128) if a[y][x] != b[y][x])


class Rig:
    def __init__(self, build, snapshot, work: pathlib.Path, lay=None):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        if build:
            self.m = EM.machine(build, snapshot)
        else:
            from emulib.machine import Machine
            self.m = Machine(snapshot)
        self.lay = lay
        self.work = work
        work.mkdir(parents=True, exist_ok=True)
        self.p = Panel(self.m, png_dir=str(work))
        self.p.tick_clock(EM.FRAMES)
        self.p.settle(3_000_000)
        for _ in range(40):
            if self.p.frames():
                break
            self.p.settle(10_000_000)
        self.p.run_ticks(60)
        self.levels = [0] * MIX_CH
        self.moving = False
        self.force: dict[int, bytes] = {}    # words held (the USB mode, its USB OUT pair, rec_state)
        if lay:
            def held(uc):
                for va, b in self.force.items():
                    uc.mem_write(va, b)

            def on_poll(uc, ad, sz, us):     # the DSP's levels as its packets would leave them, every pass
                held(uc)
                lv = self.levels
                if self.moving:
                    lv = [random.randrange(0, 16385) for _ in range(MIX_CH)]
                blob = struct.pack(f">{MIX_CH}H", *lv)
                for s in (0, 1):
                    uc.mem_write(lay["mix_acc"] + 2 * MIX_CH * s, blob)
            self.m.uc.hook_add(UC_HOOK_CODE, on_poll, begin=lay["mix_poll"], end=lay["mix_poll"])
            self.m.uc.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, us: held(uc), begin=lay["mix_ovw_get"],
                               end=lay["mix_ovw_get"])
            # (the cost, step 8: hooks in place before the code is translated, as emu_mixcpu.py's; a hook added later
            # is not seen by blocks already translated)
            self.ex, self.ex_on = 0, False

            def every(uc, ad, sz, us):
                if self.ex_on:
                    self.ex += 1
            self.m.uc.hook_add(UC_HOOK_CODE, every)
            self.counters = {n: EM.Counter(self.m, lay[n]) for n in ("ovw_poll", "mix_poll", "wr_screen")}
        self.m.flush()

    def glass(self):
        return rows(EM.glass(self.m))

    def shot(self, name):
        self.p.panel.write_png(EM.glass(self.m), str(self.work / f"{name}.png"))
        return self.glass()

    def long(self, name, k=0):
        return self.m.long(self.lay[name] + 4 * k)

    def wlong(self, va, v):
        self.m.write(va, struct.pack(">I", v & 0xFFFFFFFF))

    def ticks(self, n):
        self.p.run_ticks(n)

    def page(self):
        """stock's MIXER page index (0..4), or -1 (as emu_mixmeter.py)"""
        s = self.long("wr_screen_obj")
        ok = lambda x: 0x40000000 <= x < 0x48000000 and not x & 3          # noqa: E731
        node = self.m.long(s + 28) if ok(s) else 0
        for _ in range(32):
            if not ok(node) or node == s + 20:
                break
            v = self.m.long(node + 8)
            if ok(v) and self.m.long(v) == MIXER_VIEW:
                return self.m.long(v + 0x90)
            node = self.m.long(node)
        return -1

    def tap_func_mod(self, func_first_up=False):
        self.p.press_for(FUNC, 10)
        self.p.press_for(MOD, 8)
        if func_first_up:
            self.p.release_for(FUNC, 4)
            self.p.release_for(MOD, 40)
        else:
            self.p.release_for(MOD, 30)
            self.p.release_for(FUNC, 30)

    def usb(self, mode, out_on=0, sel=(0, 1), rec=0):
        """the USB mode (5 USB audio, 6 Overbridge), its USB OUT pair, the recorder's state, held from now on"""
        self.force = {USB_MODE: struct.pack(">I", mode), USB_OUT_ON: bytes([out_on]),
                      USB_OUT_SEL: bytes([sel[0] & 0xFF, sel[1] & 0xFF]),
                      self.lay["rec_state"]: struct.pack(">i", rec)}
        for va, b in self.force.items():
            self.m.write(va, b)

    def unforce(self, saved):
        self.force = {}
        for va, b in saved.items():
            self.m.write(va, b)

    def syn(self):
        self.p.press_for(SYN, 10)
        self.p.release_for(SYN, 40)


def model(r: Rig, O):
    st = [EM.guest(r.m, r.lay["mix_ovw_get"], ch) & 0xFFFFFFFF for ch in range(O.OUT_CH)]
    usb = EM.guest(r.m, r.lay["mix_ovw_get"], -1) & 0xFFFFFFFF == 5
    lit = [v & 0xFF for v in st]
    hold = [v >> 8 & 0xFF for v in st]
    mark = [v >> 16 & 1 for v in st]
    live = [v >> 17 & 1 for v in st]
    return O.outs_render(lit, hold, mark, live, usb), {"lit": lit, "hold": hold, "mark": mark, "live": live,
                                                       "usb": usb, "title": O.outs_title(mark, usb)}


def clear_stamps(r: Rig):
    for k in range(24):
        r.wlong(r.lay["mix_clip_at"] + 4 * k, 0)
        r.wlong(r.lay["mix_ov_clip_at"] + 4 * k, 0)


def ours(a, work: pathlib.Path, O, lay) -> dict:
    r = Rig(a.build, a.snapshot, work / "ours", lay)
    out = {}
    r.m.write(lay["mtr_start_done"], (1).to_bytes(4, "big"))   # the start-up over, as on a unit running a while
    r.tap_func_mod()                     # (startup.c forgets every clip stamp until the DSP has reported 2 s)
    r.syn()                              # SYN from another page: its page 1 (a SYN tap on a SYN page steps it)
    r.ticks(SETTLE)
    pre = r.shot("o_pre_syn")
    fact("the SYN page is up, no MIXER, no overview", r.page() == -1 and r.long("ovw_up") == 0)

    # 1. taps
    t0 = r.long("ovw_mix_taps")
    r.tap_func_mod()
    tap = r.shot("o_tap")
    fact("FUNC + [MOD] tapped: the tap played, the MIXER up on Compressor 1/5 (page 0), no overview",
         r.long("ovw_mix_taps") == t0 + 1 and r.page() == 0 and r.long("ovw_up") == 0, f"page {r.page()}")
    r.tap_func_mod()
    fact("... again on the MIXER: its next page (2/5)", r.page() == 1, f"page {r.page()}")
    r.syn()
    r.ticks(SETTLE)
    fact("... SYN tapped: the SYN page as before, pixel for pixel", diff(r.glass(), pre) == 0
         and r.page() == -1, f"{diff(r.glass(), pre)} px")
    r.tap_func_mod(func_first_up=True)
    fact("FUNC let go before MOD: the tap played all the same (FUNC held for it), the MIXER up",
         r.page() == 0 and r.long("ovw_mix_taps") == t0 + 3, f"page {r.page()}")
    r.syn()
    out["tap"] = tap

    # 2. Overbridge mode, held 1.6 s, fixed levels
    saved = {va: r.m.read(va, n) for va, n in ((USB_MODE, 4), (USB_OUT_ON, 1), (USB_OUT_SEL, 2),
                                               (lay["rec_state"], 4))}
    r.levels = list(LEVELS)
    clear_stamps(r)
    r.p.skip_frames(6000)
    r.ticks(SETTLE)
    pre = r.shot("o_pre_hold")
    o0, al0, tk0 = r.long("ovw_opens"), r.long("ovw_alone"), r.long("mix_ovw_takes")
    r.usb(6)
    r.p.press_for(FUNC, 10)
    r.p.press_for(MOD, HOLD)
    up = r.long("ovw_up")
    pic, data = model(r, O)
    g = r.shot("o_held")
    want_live = [1] * 24 + [0]
    want_px = [O.mix_px(LEVELS[O.OUT_UNIT[ch]]) if want_live[ch] else 0 for ch in range(O.OUT_CH)]
    fact("held 1.6 s: the OUTPUTS overview up (ovw_up 7), opened once, the DSP's levels asked (mix_want)",
         up == OV_MIX and r.long("ovw_opens") == o0 + 1 and r.long("mix_want") == 1, f"up {up}")
    fact("... Overbridge mode, not recording: every bar in use but the recorder's", data["live"] == want_live,
         str(data["live"]))
    fact("... each bar's pixels as its own unit's level (dnfw.overviews.mix_px)", data["lit"] == want_px,
         f"{data['lit']} vs {want_px}")
    fact("... the glass pixel for pixel the model (dnfw.overviews.outs_render)", diff(g, pic) == 0,
         f"{diff(g, pic)} px")
    out["pic"] = pic
    out["data"] = data

    # 3. levels change while held
    r.levels = [lv // 8 for lv in LEVELS]
    r.ticks(30)
    pic2, data2 = model(r, O)
    g2 = r.shot("o_held_lower")
    fact("levels lowered while held: within 0.25 s the glass the model again, the old peaks as ticks",
         diff(g2, pic2) == 0 and data2["hold"][0] == 38 and data2["lit"][0] < 38 and data2["hold"][23] > data2["lit"][23],
         f"{diff(g2, pic2)} px")
    r.ticks(242)
    tk1 = r.long("mix_ovw_takes")
    per_s = (tk1 - tk0) / ((30 + 242 + HOLD - 121) / 121)
    fact("... redraws alone over the glass (ovw_alone), the levels taken at most 10.6 a second",
         r.long("ovw_alone") > al0 and 8 <= per_s <= 10.6, f"{per_s:.2f}/s, alone {r.long('ovw_alone') - al0}")

    # 4. clips for the overview on track 3's channel, return R and the analog outputs; a MIXER stamp on track 6
    f = r.m.long(FRAMES) | 1
    for k in (2, 17, 20):
        r.wlong(lay["mix_ov_clip_at"] + 4 * k, f)
    r.wlong(lay["mix_clip_at"] + 4 * 5, f)
    r.ticks(30)
    pic3, data3 = model(r, O)
    g3 = r.shot("o_clip")
    want_mark = [1 if ch in (2, 17, 21, 22) else 0 for ch in range(O.OUT_CH)]
    fact("clips on track 3's channel, return R, the analog outputs: those marks alone (not track 6's MIXER stamp), "
         "'CLIP 3 R OUT', as the model", diff(g3, pic3) == 0 and data3["mark"] == want_mark
         and data3["title"] == "CLIP 3 R OUT", f"{diff(g3, pic3)} px {data3['mark']} {data3['title']!r}")
    out["clip"] = data3

    # 5. USB audio mode, USB OUT = track 3's pair (channels 6, 7), recording; then neither
    r.levels = list(LEVELS)
    r.usb(5, 1, (6, 7), 2)
    r.ticks(30)
    pic5, data5 = model(r, O)
    g5 = r.shot("o_usb_rec")
    live5 = [1 if ch in (2, 21, 22, 23, 24) else 0 for ch in range(O.OUT_CH)]
    fact("USB audio, USB OUT = track 3, recording: track 3, OUT, IN, REC in use, the rest dotted, USB, as the model",
         diff(g5, pic5) == 0 and data5["live"] == live5 and data5["usb"]
         and data5["lit"][24] == O.mix_px(LEVELS[24]) and data5["lit"][5] == 0,
         f"{diff(g5, pic5)} px {data5['live']} {data5['lit']}")
    r.usb(0, 0, (0, 1), 0)
    r.ticks(30)
    pic6, data6 = model(r, O)
    g6 = r.shot("o_no_usb")
    fact("no USB audio, not recording: OUT and IN alone in use, as the model",
         diff(g6, pic6) == 0 and data6["live"] == [1 if ch in (21, 22, 23) else 0 for ch in range(O.OUT_CH)]
         and not data6["usb"], f"{diff(g6, pic6)} px {data6['live']}")
    r.unforce(saved)
    r.ticks(15)

    # 5. let go
    t1 = r.long("ovw_mix_taps")
    r.p.release_for(MOD, 30)
    r.p.release_for(FUNC, 30)
    r.ticks(SETTLE)
    after = r.shot("o_released")
    fact("MOD let go: the screen of before the press, pixel for pixel; no MIXER, no tap, no overview",
         diff(after, pre) == 0 and r.page() == -1 and r.long("ovw_mix_taps") == t1 and r.long("ovw_up") == 0,
         f"{diff(after, pre)} px, page {r.page()}")
    clear_stamps(r)

    # 6. over the MIXER
    r.tap_func_mod()
    r.tap_func_mod()
    r.ticks(150)                         # (stock's title back from the page's name)
    pg = r.page()
    mix_pre = r.shot("o_mixer_pre")
    r.p.press_for(FUNC, 10)
    r.p.press_for(MOD, HOLD)
    pic4, _ = model(r, O)
    g4 = r.shot("o_over_mixer")
    fact("on Internal Mixer 2/5, held 1.6 s: the overview over it, as the model",
         pg == 1 and r.long("ovw_up") == OV_MIX and diff(g4, pic4) == 0, f"page {pg}, {diff(g4, pic4)} px")
    r.p.release_for(MOD, 30)
    r.p.release_for(FUNC, 30)
    back = r.shot("o_mixer_back")
    fact("... let go: the MIXER page as before, pixel for pixel, its page unchanged",
         diff(back, mix_pre) == 0 and r.page() == pg, f"{diff(back, mix_pre)} px, page {r.page()}")
    r.syn()

    # 7. another key while held
    pre7 = r.glass()
    r.p.press_for(FUNC, 10)
    r.p.press_for(MOD, 40)
    r.p.press_for(SYN, 10)
    r.p.release_for(SYN, 120)
    mid = r.long("ovw_up")
    r.p.release_for(MOD, 30)
    r.p.release_for(FUNC, 30)
    fact("SYN pressed while FUNC + MOD held: no overview after a second; MOD let go: no MIXER",
         mid == 0 and r.long("ovw_up") == 0 and r.page() == -1, f"up {mid}, page {r.page()}")
    out["pre7"] = diff(pre7, r.glass())

    # 8. the cost, every bar moving at every pass: everything the ColdFire executed in 2 s with the overview up
    # against 2 s on the SYN page with the same levels moving (digikit skips the idle task's spin, so what executes is
    # the load; no audio interrupt runs in the emulator), and our routines' own share (ovw_poll: the frames alone,
    # paint and panel_diff; mix_poll: the levels; wr_screen: a full draw's part of ours)
    def window(ticks):
        d0 = {k: r.long(k) for k in ("ovw_alone", "ovw_fulls", "mix_ovw_takes")}
        runs0 = {k: len(c.runs) for k, c in r.counters.items()}
        r.ex, r.ex_on = 0, True
        r.ticks(ticks)
        r.ex_on = False
        sec = ticks / 121
        ours = sum(sum(c.runs[runs0[k]:]) for k, c in r.counters.items())
        return r.ex / sec, ours / sec, {k: r.long(k) - v for k, v in d0.items()}

    r.moving = True
    r.p.press_for(FUNC, 10)
    r.p.press_for(MOD, 150)
    all_up, ours_up, cnt_up = window(242)
    up8 = r.long("ovw_up")
    r.p.release_for(MOD, 30)
    r.p.release_for(FUNC, 30)
    r.ticks(SETTLE)
    all_syn, ours_syn, _ = window(242)
    r.moving = False
    pct = 100 * (all_up - all_syn) / UNIT_IPS
    out["cost"] = {"all_up_instr_s": all_up, "all_syn_instr_s": all_syn, "ours_up_instr_s": ours_up,
                   "ours_syn_instr_s": ours_syn, "added_pct": round(pct, 3),
                   "ours_up_pct": round(100 * ours_up / UNIT_IPS, 3), "in_2s": cnt_up}
    print(f"  cost: everything executed {all_up:,.0f} instr/s with the overview up, {all_syn:,.0f} on the SYN page: "
          f"+{pct:.3f} % of the CPU; ovw_poll+mix_poll+wr_screen {ours_up:,.0f} instr/s up, {ours_syn:,.0f} on SYN; "
          f"in 2 s up: {cnt_up}", flush=True)
    fact("the cost with every bar moving: the overview adds under 1 % of the CPU; redraws alone, the levels 10 a s",
         up8 == OV_MIX and pct < 1.0 and cnt_up["ovw_alone"] >= 15 and cnt_up["mix_ovw_takes"] <= 22,
         f"{pct:.3f} % {cnt_up}")
    faults = list(getattr(r.m, "faults", []))
    fact("no fault (no guest exception)", not faults, str(faults[:3]))
    r.m = r.p = None
    return out


def stock(a, work: pathlib.Path, ours_out: dict) -> None:
    snap = a.stock_snapshot or str(pathlib.Path(a.snapshot).parent / "ui1200M.snap")
    r = Rig(None, snap, work / "stock")
    r.syn()
    pre = r.shot("s_pre")
    r.p.press_for(FUNC, 10)
    r.p.press_for(MOD, 10)
    press = r.shot("s_press")
    r.p.press_for(MOD, 0)
    r.ticks(HOLD - 10)
    held = r.shot("s_held")
    fact("negative control, stock 1.12: the MIXER on the press; held 1.6 s, no overview (the model's picture differs)",
         diff(press, pre) > 300 and diff(held, ours_out["pic"]) > 300, f"{diff(held, ours_out['pic'])} px")
    tap = ours_out["tap"]
    print(f"  (info) ours' tap screen vs stock's press screen, rows 10..63: "
          f"{sum(1 for y in range(10, 64) for x in range(128) if tap[y][x] != press[y][x])} px", flush=True)


def main() -> int:
    import dnfw.overviews as O
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--stock-snapshot", default=None)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    random.seed(7)
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    need = [k for k in ("ovw_up", "ovw_opens", "ovw_alone", "ovw_mix_taps", "mix_ovw_get", "mix_ovw_takes",
                        "mix_acc", "mix_poll", "mix_want", "mix_clip_at", "mix_ov_clip_at", "rec_state", "mtr_start_done", "wr_screen_obj", "ovw_poll",
                        "wr_screen") if k not in lay]
    if need:
        print(f"MIXER OVERVIEW FAILED: not in the layout: {need}")
        return 1
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    try:
        o = ours(a, work, O, lay)
    except Exception as e:  # a guest fault or a harness error: the step fails with it
        fact(f"ours ran to the end ({type(e).__name__}: {e})", False)
        o = None
    gc.collect()
    if o:
        stock(a, work, o)
    good = bool(FACTS) and all(FACTS.values())
    (work / "mixovw.json").write_text(json.dumps({"facts": FACTS, "cost": (o or {}).get("cost"),
                                                  "model": (o or {}).get("data")}, indent=1))
    print("MIXER OVERVIEW OK" if good else "MIXER OVERVIEW FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
