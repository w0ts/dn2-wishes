"""Knob turns and list popups as the User feels them (2026-11-18, scratch/unit-now/cpu-spikes.md: the audio interrupt
takes about 84.5 % of the ColdFire on the unit, a fast turn puts the UI at 97-100 % and the screen goes on moving
0.5-0.9 s after the hand stops): the coupled emulator (emu_coupled.Coupled, the ColdFire alone: its UI, its audio
interrupt, the sequencer's timer; no DSP block), timing-faithful with the interrupt at --isr-share of each frame, the
panel UART at the unit's rate.

    python scripts/emu_ui_turns.py --build BUILD.syx --snapshot SNAP --stock STOCK.syx --work DIR --action env1-fast

Actions (each from the snapshot, its own process): PAGE-SPEED, PAGE one of env1 (AMP 1/3, knob A), env2 (AMP 2/3,
knob A), lfo1 (MOD, knob A), fltr (FLTR, knob E), syn (SYN, knob C), popup (MOD, knob E: LFO1's WAVE list), and
SPEED fast (40 detents a second, 20 up then 20 down) or slow (10 a second, 10 up, 10 down); insert (FX twice, knob A:
M.SEL, ten detents at 20 a second, then two seconds of rest, twice).

The panel UART: UART8 at 156,250 baud, ten bits a byte, 15,625 bytes a second. digikit's eDMA sends a transfer the
moment it is armed; here it completes once its bytes would have left at that rate (emu_scope.py's model, on the audio
frames' clock), so the firmware's own ring waits as on the unit.

The detents go in where the panel's bytes go (digikit's panelin: UART8, the panel task's encoder sums, one UI item
every four panel ticks at most), as the unit's own encoders do.

Measured (WORK/ACTION.json; times in ms of audio frames, the UART's queue ahead of a frame counted):
  updates      screen changes a second while the hand turns (the title bar's right end masked: the CPU label, tempo)
  draws        full page draws (stock's screen draw) a second while turning
  first_drawn  the first detent -> the first present after its knob item was taken, out of the UART
  catchup      the last detent -> the first present after the LAST knob item was taken, out of the UART: how long
               the screen goes on after the hand stops
  last_item    the last detent -> the UI loop taking the last knob item (the queue's backlog)
  ui_pct       the UI side's share of the frames (the UI's units less the idle loop's passes, digikit's IdleSpin; a
               pass counted as one unit: an approximation, the same on both builds) while turning, and over the turn
               and the 4 s after it; ui_units_action: those units in all
  items        every knob item taken (code, delta), in order; values: the track's sound words and ENV2's knobs (the
               matrix's live table) after each change; frame_hex: the audio frame at rest before the turn and at
               the end (every run of an action ends at the same frame)
Then, 3 s after the action: the glass (modelled from every group sent) must be BACK, and a full redraw forced then
must draw exactly it below the title bar (the title bar's message slides on its own clock; its difference is
reported, not checked). WORK/ACTION_end.png and ACTION_full.png: the two screens.
Exit 0 and "TURNS OK" when those hold with no fault.

scripts/emu_ui_turns.py is a measurement: the gate's lineonly, matrix (popglass) and fuzz steps hold the glass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import struct
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_coupled as EC  # noqa: E402

FB_BACK = 0x402A10CC                    # between presents: the frame on the glass
FB_FRONT = 0x402A10C8                   # the frame drawn, until panel_diff presents it
PANEL_DIFF = 0x40131FD2                 # stock's present: the groups that differ, then the swap
GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions
DRAW_PASS = 0x4002E322                  # stock's UI pass: the redraw test (wr_poll), the screen's draw, panel_diff
SCREEN_DRAW = 0x4011D60A                # the views drawn (wr_screen's stock call)
POP_RET = 0x4002F184                    # the UI loop, back from the queue's receive (the item in d0)
IDLE_SPIN = 0x400CF246                  # the idle task's bra.s *
RING_HEAD, RING_PEND, RING_TAIL = 0x4058E5D0, 0x4058E5D8, 0x4058E5DC
TCD35_CITER, TCD35_BITER = 0xFC045474, 0xFC04547C
UART_BYTES_A_S = 156_250 / 10
FRAMES_A_S = 1500
BYTES_A_PERIOD = UART_BYTES_A_S / FRAMES_A_S
UI_TRACK, KIT = 0x42432A6C, 0x800052A0
MX_RAM = 0x476F0000                     # the matrix's tables (dnfw.waverider.pages.MX_RAM)
WISH_MAP = (0x47280000, 0x500000)       # the wishes record's RAM and the matrix's tables (emu_matrix.WISH_MAP)
SYN, FLTR, AMP, FX, MOD = (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)
MASK = [(x, y) for x in range(88, 128) for y in range(54, 64)]   # the title bar's right end: the CPU label, the tempo

PAGES = {"env1": ((AMP,), 0), "env2": ((AMP, AMP), 0), "lfo1": ((MOD,), 0), "fltr": ((FLTR,), 4),
         "syn": ((SYN,), 2), "popup": ((MOD,), 4), "insert": ((FX, FX), 0)}
SPEEDS = {"fast": (40, 20), "slow": (10, 10)}          # detents a second, detents each way


def page_only(buf):
    """the screen below stock's title bar (rows 0..53): the title bar's message slides in and out on its own clock"""
    b = bytearray(buf)
    for x in range(128):
        b[8 * x + 6] &= 0xFC                    # rows 54, 55 (bits 1, 0 of byte 6)
        b[8 * x + 7] = 0                        # rows 56..63
    return bytes(b)


def masked(buf):
    b = bytearray(buf)
    for x, y in MASK:
        b[8 * x + (y >> 3)] &= ~(0x80 >> (y & 7)) & 0xFF
    return bytes(b)


class Rig:
    def __init__(self, a, lay):
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.a, self.lay, self.K = a, lay, K
        self.c = c = EC.Coupled(a.build, a.snapshot, a.stock, png_dir=str(pathlib.Path(a.work) / "screens"),
                                verbose=True, dsp=False)
        self.m = m = c.machine
        from unicorn import UC_PROT_ALL, UcError
        at, n = WISH_MAP
        for page in range(at & ~0xFFFFF, at + n, 0x100000):     # as emu_matrix.setup: the snapshot may hold one already
            try:
                m.uc.mem_map(page, 0x100000, UC_PROT_ALL)
            except UcError:
                pass
        self.uart_due = None
        self.ev = {"present": 0, "groups": 0, "draws": 0, "passes": 0, "spins": 0}
        self.pops, self.passes, self.draws, self.detents, self.presents = [], [], [], [], []
        self.shown = []
        self.screen = None
        self.glass = None

        def on_group(uc, ad, sz, us):
            self.ev["groups"] += 1
            if self.glass is not None:
                sp = uc.reg_read(K.UC_M68K_REG_A7)
                col, page, ptr = struct.unpack(">3I", m.read(sp + 20, 12))
                for k_, b in enumerate(m.read(ptr, 8)):
                    self.glass[8 * ((col & 0xFF) + k_) + (page & 7)] = b

        def on_diff(uc, ad, sz, us):             # the frame about to be presented: FRONT at panel_diff's entry
            self.ev["present"] += 1
            self.presents.append(c.blocks)
            self.shown.append((c.blocks, hashlib.sha1(masked(bytes(m.read(m.long(FB_FRONT), 1024)))).hexdigest()[:12]))

        def on_pass(uc, ad, sz, us):
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            ret = struct.unpack(">I", m.read(sp, 4))[0]
            self.ev["passes"] += 1
            if len(self.passes) < 20000:
                self.passes.append((c.blocks, ret))

        def on_draw(uc, ad, sz, us):
            self.ev["draws"] += 1
            self.draws.append(c.blocks)

        def on_screen(uc, ad, sz, us):
            self.screen = struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0]

        def on_pop(uc, ad, sz, us):
            it = bytes(m.read(uc.reg_read(K.UC_M68K_REG_D0), 12))
            if len(self.pops) < 20000:
                self.pops.append((c.blocks, it[0], struct.unpack(">I", it[4:8])[0], struct.unpack(">b", it[8:9])[0]))

        def on_spin(uc, ad, sz, us):
            self.ev["spins"] += 1
        for fn, at in ((on_group, GROUP_CONT), (on_diff, PANEL_DIFF), (on_pass, DRAW_PASS), (on_draw, SCREEN_DRAW),
                       (on_screen, lay["wr_screen"]), (on_pop, POP_RET), (on_spin, IDLE_SPIN)):
            m.uc.hook_add(UC_HOOK_CODE, fn, begin=at, end=at)
        self._slow_uart()
        self.stepper = getattr(m.m, "_fast_stepper_obj", None)

    # --- the UART at the unit's rate, on the audio frames' clock ---------------------------------------------
    def _slow_uart(self):
        ch = self.m.ev.get("edma_tx")
        if ch is None:
            raise SystemExit("no eDMA UART channel in this machine (ev['edma_tx'])")
        orig_run, orig_deliver = ch.run, ch.deliver

        def run():
            citer = ch._u16(0x14) & 0x7FFF
            if not citer or self.uart_due is not None:
                return 0
            n = citer * ch._u32(0x08)
            self.uart_due = (self.c.blocks + max(1, math.ceil(n / BYTES_A_PERIOD)), orig_run)
            return 0

        def deliver():
            self._uart_poll()
            return orig_deliver()
        ch.run, ch.deliver = run, deliver

    def _uart_poll(self):
        if self.uart_due is not None and self.c.blocks >= self.uart_due[0]:
            fn = self.uart_due[1]
            self.uart_due = None
            fn()

    def occupancy(self):
        citer = struct.unpack(">H", self.m.read(TCD35_CITER, 2))[0] & 0x7FFF
        biter = struct.unpack(">H", self.m.read(TCD35_BITER, 2))[0] & 0x7FFF
        d1 = ((citer - biter) + (self.m.long(RING_HEAD) - self.m.long(RING_TAIL))) & 0xFFF
        return d1 + self.m.long(RING_PEND)

    # --- time ----------------------------------------------------------------------------------------------
    def back(self):
        return bytes(self.m.read(self.m.long(FB_BACK), 1024))

    def env2(self):
        """the UI track's ENV2 knobs as the frame reads them: the matrix's live table (csrc/matrix/matrix.c struct
        mx_state, [t][live[t]], its env2; live[t] at +92 + 4 t; the offsets from its magic, emulib/mxlayout.py)"""
        from emulib import mxlayout                     # noqa: PLC0415
        L = mxlayout.of_magic(self.m.long(MX_RAM))
        t = self.m.read(UI_TRACK, 1)[0] & 15
        live = self.m.long(MX_RAM + 92 + 4 * t) & 1
        return bytes(self.m.read(MX_RAM + L.tab + L.tab_b * (2 * t + live) + L.env2, 7))

    def sound_values(self):
        kit = self.m.long(KIT)
        t = self.m.read(UI_TRACK, 1)[0] & 15
        return bytes(self.m.read(kit + 52 + 1163 * t + 0x14, 202)) if kit else b""

    def period(self, log=None):
        g0, p0 = self.ev["groups"], self.ev["present"]
        ok = self.c.period()
        self._uart_poll()
        if log is not None and (self.ev["groups"] != g0 or self.ev["present"] != p0):
            log.append((self.c.blocks, self.occupancy(), hashlib.sha1(masked(self.back())).hexdigest()[:12]))
        return ok

    def run(self, n, log=None, each=None):
        for _ in range(n):
            if not self.period(log):
                return False
            if each:
                each()
        return True

    def idle_n(self):
        """the idle loop's passes, run or skipped (digikit's IdleSpin: ev['idle_spins'])"""
        return self.m.ev["idle_spins"]["n"]

    def busy(self):
        """the UI's units less the idle loop's passes (one unit a pass: a skipped pass is credited to the clock as one
        instruction; scenario() reports the raw counts too)"""
        return self.c.ui_units - self.idle_n()

    # --- the panel -------------------------------------------------------------------------------------------
    def tap(self, key, periods=20):
        P, pr = self.c.panel.panelin, self.c.panel.profile
        self.m.pc = P.press(self.m.m, pr, *key)
        self.run(2)
        self.m.pc = P.release(self.m.m, pr, *key)
        self.run(periods)

    def detent(self, knob, d):
        self.detents.append((self.c.blocks, knob, d))
        self.m.pc = self.c.panel.panelin.encoder(self.m.m, self.c.panel.profile, knob, d)


def g(r, name):
    return r.m.long(r.lay[name]) if name in r.lay else None


def scenario(r, action):
    a = r.a
    page, speed = action.split("-") if "-" in action else (action, "pick")
    keys, knob = PAGES[page]
    c = r.c
    c.watchdog()
    r.run(30)                                            # fast timing: the UI settles from the snapshot
    for k in keys:
        r.tap(k, periods=30)
    r.run(60)
    EC.ISR_SHARE_STOPPED = a.isr_share
    if a.frame_units:                                    # a frame of a fixed size (the unit's frame is a fixed time;
        c.frame_units = a.frame_units                    # a build whose interrupt is cheaper leaves the UI more)
    frame_units = c.set_timing("faithful", calibrate=24)
    r.run(int(0.3 * FRAMES_A_S))                         # rest: the page drawn, the knob's rest counter full
    b0, f0, u0, i0 = r.busy(), c.blocks, c.ui_units, r.idle_n()
    r.run(int(0.3 * FRAMES_A_S))
    raw_rest = {"ui_units": c.ui_units - u0, "idle_passes": r.idle_n() - i0, "frames": c.blocks - f0,
                "per_block": r.stepper.per_block if r.stepper else None}
    rest_busy = (r.busy() - b0) / ((c.blocks - f0) / FRAMES_A_S)
    held0 = g(r, "wr_turn_held") or 0
    r.glass = bytearray(r.back())
    log, values = [], []
    v_last = [r.sound_values() + r.env2()]

    def watch():
        v = r.sound_values() + r.env2()
        if v != v_last[0]:
            v_last[0] = v
            values.append(hashlib.sha1(v).hexdigest()[:12])
    r.pops.clear(), r.passes.clear(), r.draws.clear(), r.detents.clear(), r.presents.clear(), r.shown.clear()
    for k in getattr(r, "counters", {}).values():
        k.runs.clear()
    base_hash = hashlib.sha1(masked(r.back())).hexdigest()[:12]
    cap0 = len(c.panel.capture.frames)
    frame_rest = r.c.read(EC.CF_FRAME, 2688).hex()
    t0, busy0, ev0 = c.blocks, r.busy(), dict(r.ev)
    if speed == "pick":                                  # an insert pick: ten detents at 20 a second, rest 2 s, twice
        plan = []
        for rep, d in ((0, 1), (1, -1)):
            base = rep * (int(0.5 * FRAMES_A_S) + 2 * FRAMES_A_S)
            plan += [(base + round(k * FRAMES_A_S / 20), d) for k in range(10)]
    else:
        rate, n = SPEEDS[speed]
        plan = [(round(k * FRAMES_A_S / rate), 1 if k < n else -1) for k in range(2 * n)]
    end_turn = t0 + plan[-1][0]
    for at, d in plan:
        while c.blocks < t0 + at:
            if not r.period(log):
                break
            watch()
        r.detent(knob, d)
    busy_turn, ev_turn, t_turn = r.busy() - busy0, {k: r.ev[k] - ev0[k] for k in r.ev}, c.blocks - t0
    counted = {n: (len(k.runs), sum(k.runs)) for n, k in getattr(r, "counters", {}).items()}
    # after the hand: 4 s, always (every run of an action ends at the same frame: the frames compare)
    while c.blocks - end_turn < 4 * FRAMES_A_S:
        r.period(log)
        watch()
    busy_all, t_all = r.busy() - busy0, c.blocks - t0
    counted_all = {n: (len(k.runs), sum(k.runs)) for n, k in getattr(r, "counters", {}).items()}
    # each present: the frame (FRONT at panel_diff's entry, masked), and when its groups have left the UART (the last
    # period with groups queued before the next present, plus what the ring still held then)
    def out_time(k):
        t = r.shown[k][0]
        nxt = r.shown[k + 1][0] if k + 1 < len(r.shown) else t + 3 * FRAMES_A_S
        mine = [(tt, occ) for tt, occ, _ in log if t <= tt < nxt]
        return (mine[-1][0] + mine[-1][1] / BYTES_A_PERIOD) if mine else float(t)
    ups, last = [], base_hash
    for k, (t, h) in enumerate(r.shown):
        if h != last:
            ups.append((t, out_time(k), h))
            last = h
    first_detent = r.detents[0][0] if r.detents else t0
    last_detent = r.detents[-1][0] if r.detents else t0
    knob_pops = [q[0] for q in r.pops if (q[1] == 1 or q[1] == 255) and 1 <= q[2] <= 8]

    def present_after(t):
        """the first present at or after T, as out of the UART"""
        for k, (tt, _) in enumerate(r.shown):
            if tt >= t:
                return out_time(k)
        return None
    turning = [u for u in ups if first_detent <= u[0] <= last_detent]
    ms = lambda frames: None if frames is None else round(frames * 1000 / FRAMES_A_S, 1)   # noqa: E731
    secs = max(1, t_turn) / FRAMES_A_S
    share = lambda units, frames: round(100.0 * units / (frame_units * max(1, frames)), 2)   # noqa: E731
    fp = present_after(knob_pops[0]) if knob_pops else None
    lp = present_after(knob_pops[-1]) if knob_pops else None
    out = {"action": action, "isr_share": a.isr_share, "frame_units": frame_units, "rest_screen": base_hash,
           "screens": sorted({u[2] for u in ups}),
           "turn_s": round(secs, 3), "detents": len(r.detents), "knob_items": len(knob_pops),
           "updates_a_s": round(len(turning) / secs, 1),
           "first_change_ms": ms(ups[0][1] - first_detent) if ups else None,
           "first_drawn_ms": ms(fp - first_detent) if fp is not None else None,
           "catchup_ms": ms(lp - last_detent) if lp is not None else None,
           "last_item_after_ms": ms(knob_pops[-1] - last_detent) if knob_pops else None,
           "settled_ms": ms(max((u[1] for u in ups), default=last_detent) - last_detent),
           "ui_pct_rest": share(rest_busy / FRAMES_A_S, 1), "ui_pct_turn": share(busy_turn, t_turn),
           "ui_pct_turn_and_after": share(busy_all, t_all), "ui_units_action": round(busy_all),
           "draws_a_s": round(ev_turn["draws"] / secs, 1), "presents_a_s": round(ev_turn["present"] / secs, 1),
           "passes_a_s": round(ev_turn["passes"] / secs, 1), "groups_a_s": round(ev_turn["groups"] / secs, 1),
           "draws_action": len(r.draws),
           "values": values, "values_final": hashlib.sha1(r.sound_values() + r.env2()).hexdigest()[:12],
           "raw_rest": raw_rest, "counted": counted, "counted_all": counted_all, "held": (g(r, "wr_turn_held") or 0) - held0}
    out["env2_final"] = r.env2().hex()
    out["item_types"] = {}
    for p in r.pops:
        out["item_types"][p[1]] = out["item_types"].get(p[1], 0) + 1
    rets = {}
    for _, ret in r.passes:
        rets[hex(ret)] = rets.get(hex(ret), 0) + 1
    out["pass_callers"] = rets
    out["log"] = [(t - t0, occ, h) for t, occ, h in log][:300]
    out["timeline"] = {"detents": [(d[0] - t0, d[2]) for d in r.detents],
                       "pops": [(p[0] - t0, p[1], p[2], p[3]) for p in r.pops if p[1] in (0, 1, 255)][:400],
                       "draws": [d - t0 for d in r.draws][:400],
                       "passes": [q[0] - t0 for q in r.passes][:400],
                       "presents": [q - t0 for q in r.presents][:400],
                       "updates": [(round(u[0] - t0), round(u[1] - t0, 1)) for u in ups][:400]}
    if a.shots:                                          # the distinct screens presented during the action
        seen, k = set(), 0
        for fr in c.panel.capture.frames[cap0:]:
            h = hashlib.sha1(bytes(fr)).hexdigest()[:12]
            if h in seen:
                continue
            seen.add(h)
            c.panel.panel.write_png(bytes(fr), str(pathlib.Path(a.work) / f"{action}_shot{k:02d}_{h}.png"))
            k += 1
            if k >= a.shots:
                break
    # the settled frame: 3 s more (stock's timed value labels and title messages gone), then the audio frame's digest
    r.run(3 * FRAMES_A_S)
    out["frame"] = hashlib.sha1(r.c.read(EC.CF_FRAME, 2688)).hexdigest()[:16]
    out["frame_hex"], out["frame_rest_hex"] = r.c.read(EC.CF_FRAME, 2688).hex(), frame_rest
    out["items"] = [(q[2], q[3]) for q in r.pops if (q[1] == 1 or q[1] == 255) and 1 <= q[2] <= 8]
    # the glass is BACK; a full redraw forced now draws exactly it
    back = r.back()
    out["glass_is_back"] = bytes(r.glass) == back
    pathlib.Path(a.work).mkdir(parents=True, exist_ok=True)
    r.c.panel.panel.write_png(back, str(pathlib.Path(a.work) / f"{action}_end.png"))
    drawn = None
    if r.screen:
        d0, p0 = r.ev["draws"], r.ev["present"]
        r.m.write(r.screen + 32, b"\x01")
        r.m.flush()
        for _ in range(FRAMES_A_S):
            r.period()
            if r.ev["draws"] > d0 and r.ev["present"] > p0:
                break
        r.run(30)
        drawn = r.back()
        r.c.panel.panel.write_png(drawn, str(pathlib.Path(a.work) / f"{action}_full.png"))
    diff = [i for i in range(1024) if drawn is None or drawn[i] != back[i]]
    mdiff = [i for i in range(1024) if drawn is None or masked(drawn)[i] != masked(back)[i]]
    pdiff = [i for i in range(1024) if drawn is None or page_only(drawn)[i] != page_only(back)[i]]
    out["full_redraw_differs"] = len(diff)
    out["full_redraw_differs_masked"] = len(mdiff)
    out["full_redraw_differs_page"] = len(pdiff)
    out["halt"], out["faults"] = c.halt, [str(f) for f in c.faults()[:5]]
    return out


def cost(a, lay) -> dict:
    """--cost: the instructions of one full draw (wr_screen, the views and everything of ours after them) and its present
    (panel_diff), counted exactly in the ColdFire emulator alone (no audio interrupt to land inside them), on each
    page: at rest (a redraw forced) and while a knob turns (a detent, then its draw)"""
    from unicorn import UC_HOOK_CODE, UC_PROT_ALL, UcError
    from unicorn import m68k_const as K
    from emulib.panel import Panel
    import emu_modulation as EM
    out = {}
    for page in a.cost.split(","):
        m = EM.machine(a.build, a.snapshot)
        at, n = WISH_MAP
        for pg in range(at & ~0xFFFFF, at + n, 0x100000):
            try:
                m.uc.mem_map(pg, 0x100000, UC_PROT_ALL)
            except UcError:
                pass
        m.flush()
        panel = Panel(m, png_dir=str(pathlib.Path(a.work) / "cost"))
        from emu.pit import INSTR_PER_SEC
        panel.frame_clock(EM.FRAMES, per_sec=round(1500 * INSTR_PER_SEC / (121 * 1_100_000)))
        screen = {}

        def on_screen(uc, ad, sz, us):
            screen["s"] = struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0]
        m.uc.hook_add(UC_HOOK_CODE, on_screen, begin=lay["wr_screen"], end=lay["wr_screen"])
        cs = {n: EM.Counter(m, lay[n] if n in lay else int(n, 16))
              for n in ("wr_screen", "0x40131FD2", "mv_end", "mv_knob", "wpop_draw", "env2_draw") if n in lay or n[:2] == "0x"}
        panel.settle(3_000_000)
        keys, knob = PAGES[page]
        for k in keys:
            panel.tap(k)
        panel.settle(30_000_000)
        res = {}
        for state in ("rest", "turn"):
            for c_ in cs.values():
                c_.runs.clear()
            for i in range(8):
                if state == "rest":
                    m.write(screen["s"] + 32, b"\x01")
                    m.flush()
                else:
                    m.pc = panel.panelin.encoder(m.m, panel.profile, knob, 1 if i < 4 else -1)
                panel.settle(3_000_000)
            draws = len(cs["wr_screen"].runs)
            res[state] = {"draws": draws, **{n: round(sum(c_.runs) / max(1, draws)) for n, c_ in cs.items()}}
            res[state]["draw_and_present"] = res[state]["wr_screen"] + res[state]["0x40131FD2"]
        panel.screen(f"cost_{page}")
        out[page] = res
        print(f"  cost {page}: {json.dumps(res)}", flush=True)
    return out


# --- moving lines against the value they show (the User, 2026-11-18: "the bar/line that display is slow") --------------
MV = 0x46AF8000 + 0x500                 # MOD_MOVING_RAM (csrc/modulation/moving.c struct mv_state)
MV_CELLS, MV_CELL, MV_PARTS, MV_FULLS = 28, 36, 604, 608
OUT, STATE, OWNER, VSOUND = 0x800068E4, 0x8000DE60, 0x80005308, 0x800052A8
KB_ON, KEYBOARD, NOTE_KEY = 0x42432A9C, 18, 33   # KEYBOARD on (emu_coupled_stocknote.py), its key, a note's key
RECORDS = 0x401F83A4                    # stock's parameter records, 60 bytes each (+4 slot, +8 min, +12 max)
LINES = {                               # page: (the LFO's DEST and DEP records, its SPD, the record it moves, the knob turned)
    "env1": ((78, 83, 75), 64, 0),       # LFO1 -> AMP DEC; turned: A (ATK)
    "fltr": ((78, 83, 75), 67, 5),       # LFO1 -> FREQ; turned: F (RESO)
    "lfo1": ((88, 93, 85), 75, 2),       # LFO2 -> LFO1 SPD; turned: C (FADE)
}


def record_slot(m, rid):
    return struct.unpack(">i", m.read(RECORDS + 60 * rid + 4, 4))[0]


def line_scenario(r, action):
    """a modulated parameter of the page: its heard value (the voice row's OUT, what moving.c reads) moved by the harness
    after every audio frame as a 2 Hz LFO would move it (sine, 30 % of the range either side; the frame's own write is
    overwritten, its set value left), the track's voice playing it (sl_lastv, OWNER). Every frame: the line's end
    column for that value (moving.c line_at's arithmetic) against the one drawn (the cell's drawn). At rest 3 s, then
    1.5 s with another knob of the page turning fast (40 detents a second), then 1.5 s at rest"""
    a, c, m = r.a, r.c, r.m
    page = action.split("-", 1)[1]
    keys, _ = PAGES[page]
    _, target, knob = LINES[page]
    c.watchdog()
    r.run(30)
    for k in keys:
        r.tap(k, periods=30)
    r.run(60)
    t = m.read(UI_TRACK, 1)[0] & 15
    v0 = 0
    m.write(r.lay["sl_lastv"] + t, bytes([v0]))
    m.write(OWNER + 4 * v0, struct.pack(">I", t))
    m.flush()
    EC.ISR_SHARE_STOPPED = a.isr_share
    if a.frame_units:
        c.frame_units = a.frame_units
    c.set_timing("faithful", calibrate=24)
    slot = record_slot(m, target)
    lo_r, hi_r = struct.unpack(">ii", m.read(RECORDS + 60 * target + 8, 8))
    i_ = 17 + 101 * v0 + slot
    out = {"action": action, "target": target, "slot": slot, "track": t}
    phase = [0]

    def lfo():
        st = (struct.unpack(">I", m.read(STATE + 4 * i_, 4))[0] + 0x8000) >> 16
        x = st + 0.3 * (hi_r - lo_r) * math.sin(2 * math.pi * 2.0 * phase[0] / FRAMES_A_S)
        m.write(OUT + 2 * i_, struct.pack(">H", int(max(lo_r, min(hi_r, round(x))))))
        phase[0] += 1
    r.run(int(0.5 * FRAMES_A_S), each=lfo)

    def cell():
        for k in range(16):
            b = bytes(m.read(MV + MV_CELLS + MV_CELL * k, MV_CELL))
            if struct.unpack(">H", b[0:2])[0] == target:
                lo, hi = struct.unpack(">ii", b[10:18])
                return b[4], lo, hi, struct.unpack(">h", b[18:20])[0]
        return None

    def window(frames, turning):
        trues, drawns, errs = [], [], []
        p0, f0, d0 = m.long(MV + MV_PARTS), m.long(MV + MV_FULLS), r.ev["draws"]
        plan = {round(k * FRAMES_A_S / 40): (1 if (k // 10) % 2 == 0 else -1)
                for k in range(int(frames / FRAMES_A_S * 40))} if turning else {}
        start = c.blocks
        for i in range(frames):
            if i in plan:
                r.detent(knob, plan[i])
            r.period()
            lfo()
            cl = cell()
            if cl is None:
                continue
            w, lo, hi, drawn = cl
            heard = struct.unpack(">H", m.read(OUT + 2 * i_, 2))[0]
            st = (struct.unpack(">I", m.read(STATE + 4 * i_, 4))[0] + 0x8000) >> 16
            if hi <= lo:
                continue
            at = (min(max(heard, lo), hi) - lo) * (w - 1) // (hi - lo) if heard != st else -1
            trues.append(at)
            drawns.append(drawn)
            errs.append(abs(at - drawn))
        secs = (c.blocks - start) / FRAMES_A_S
        ch = lambda xs: sum(1 for k in range(1, len(xs)) if xs[k] != xs[k - 1])        # noqa: E731
        return {"value_moves_a_s": round(ch(trues) / secs, 1), "line_moves_a_s": round(ch(drawns) / secs, 1),
                "mean_error_px": round(sum(errs) / max(1, len(errs)), 2),
                "share_off_2px_or_more": round(sum(1 for e in errs if e >= 2) / max(1, len(errs)), 3),
                "max_error_px": max(errs or [0]),
                "line_alone_a_s": round((m.long(MV + MV_PARTS) - p0) / secs, 1),
                "full_asked_a_s": round((m.long(MV + MV_FULLS) - f0) / secs, 1),
                "full_draws_a_s": round((r.ev["draws"] - d0) / secs, 1), "samples": len(errs)}
    out["rest"] = window(3 * FRAMES_A_S, False)
    out["turning"] = window(int(1.5 * FRAMES_A_S), True)
    out["after"] = window(int(1.5 * FRAMES_A_S), False)
    r.c.panel.panel.write_png(r.back(), str(pathlib.Path(a.work) / f"{action}_end.png"))
    out["halt"], out["faults"] = c.halt, [str(f) for f in c.faults()[:5]]
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--action", default="")
    p.add_argument("--cost", default="", help="PAGE,PAGE...: the instructions of a full draw at rest and while turning")
    p.add_argument("--isr-share", type=float, default=0.845)
    p.add_argument("--frame-units", type=float, default=0.0, help="the frame's size in the stepper's units, fixed (else "
                   "the interrupt's measured cost / --isr-share; 30405.8 is main 270de295's, the unit's build)")
    p.add_argument("--shots", type=int, default=0, help="save the first N distinct screens of the action as PNGs")
    p.add_argument("--count", default="", help="FN,FN...: each function's instructions while turning (slow: a hook "
                   "on every instruction inside it)")
    a = p.parse_args()
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    if a.cost:
        res = cost(a, lay)
        (work / "cost.json").write_text(json.dumps(res, indent=1))
        print("COST DONE", flush=True)
        return 0
    t0 = time.perf_counter()
    r = Rig(a, lay)
    import emu_modulation as EM
    r.counters = {n: EM.Counter(r.m, lay[n] if n in lay else int(n, 16)) for n in a.count.split(",")
                  if n and (n in lay or n.startswith("0x"))}
    out = line_scenario(r, a.action) if a.action.startswith("line-") else scenario(r, a.action)
    out["wall_s"] = round(time.perf_counter() - t0)
    (work / f"{a.action}.json").write_text(json.dumps(out, indent=1))
    if a.action.startswith("line-"):
        print(f"  {a.action}: {json.dumps(out)}", flush=True)
        ok = not out["halt"] and not out["faults"] and out["rest"]["samples"] > 0
        print("LINES MEASURED" if ok else "LINES FAILED", flush=True)
        return 0 if ok else 1
    brief = {k: out[k] for k in ("knob_items", "updates_a_s", "first_change_ms", "first_drawn_ms", "catchup_ms",
                                  "last_item_after_ms", "settled_ms", "ui_pct_rest", "ui_pct_turn",
                                  "ui_pct_turn_and_after", "ui_units_action", "draws_a_s", "draws_action", "held",
                                  "counted", "glass_is_back", "full_redraw_differs_page", "full_redraw_differs_masked", "frame", "values_final")}
    print(f"  {a.action}: {json.dumps(brief)}", flush=True)
    ok = out["glass_is_back"] and out["full_redraw_differs_page"] == 0 and not out["halt"] and not out["faults"]
    print("TURNS OK" if ok else "TURNS FAILED", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
