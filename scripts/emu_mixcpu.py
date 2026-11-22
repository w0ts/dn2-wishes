"""The ColdFire's cost of stock's MIXER pages with our meters (csrc/meter/mixer.c), in the ColdFire emulator:

    python scripts/emu_mixcpu.py --build BUILD.syx --snapshot SNAP --work DIR [--seconds 2] [--stock]

digikit's emulator skips the idle task's spin exactly (emu.longrun IdleSpin) and counts what it skipped as run, at
about 1.1 M instructions a panel tick (121 a second: the unit's ~132 M a second). So on each page the instructions
that really executed, over all that ran, are the ColdFire's load there without the audio interrupt (the emulator runs
none, and no DSP): "% of the CPU" below is that share, the audio interrupt's own (~39 % on the unit, docs/meter.md)
not in it. Measured per page, over SECONDS of panel ticks, with the panel UART at the unit's rate (emu_scope's model):
  pct          executed / run, in % of the CPU
  instr_s      instructions executed a second
  screens_s    full draws a second (wr_screen); diff_s: stock's panel_diff calls a second; groups_s: 8-pixel groups sent
  mix_*        mixer.c's own: instructions a second in mix_poll and mix_draw; updates alone, full redraws asked, why
The levels the DSP would send move at every pass (each meter a different level at every 10 Hz update: the worst case,
music playing on every track). With --off the meters are switched off (mix_off): stock's page as it is.
--stock: BUILD is ignored, stock 1.12 on SNAP (stock's own snapshot), its pages reached by the same keys.
Facts in WORK/mixcpu.json; exit 0.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_modulation as EM  # noqa: E402

TICK = 0x466768B0
GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions
PANEL_DIFF = 0x40131FD2
WAIT_LOOP = 0x4000221C                  # the UART ring's free-space wait
RING_HEAD, RING_PEND, RING_TAIL = 0x4058E5D0, 0x4058E5D8, 0x4058E5DC
BYTES_A_TICK = 156_250 / 10 / 121
FUNC, MOD, SYN = (2, 0), (0, 5), (0, 1)
MIXER_VIEW = 0x401E292C
LV_CH, MIX_CH = 22, 25                    # (mixer.c MIX_CH: the DSP's 25 units, 2026-11-21)


class Rig:
    def __init__(self, a, sym, work):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        self.sym, self.a = sym, a
        self.m = m = EM.machine(None if a.stock else a.build, a.snapshot)
        self.pn = Panel(m, png_dir=str(work / "screens"))
        self.pn.tick_clock(EM.FRAMES)
        self.uart_due = None
        self.st = self.zero()
        self.lcg = 12345
        self.counting = False

        def cnt(key):
            def f(uc, ad, sz, us):
                self.st[key] += 1
            return f
        m.uc.hook_add(UC_HOOK_CODE, cnt("groups"), begin=GROUP_CONT, end=GROUP_CONT)
        m.uc.hook_add(UC_HOOK_CODE, cnt("waits"), begin=WAIT_LOOP, end=WAIT_LOOP)
        m.uc.hook_add(UC_HOOK_CODE, cnt("diffs"), begin=PANEL_DIFF, end=PANEL_DIFF)
        self.c = {}
        if not a.stock:
            m.uc.hook_add(UC_HOOK_CODE, cnt("screens"), begin=sym["wr_screen"], end=sym["wr_screen"])
            for name in [n for n in ("mix_poll", "mix_draw", "wr_screen", "wr_poll") if n in sym]:
                self.c[name] = EM.Counter(m, sym[name])

            def on_poll(uc, ad, sz, us):        # the DSP's levels: every meter moves at every update
                lv = []
                for _ in range(MIX_CH):
                    self.lcg = (self.lcg * 1103515245 + 12345) & 0x7FFFFFFF
                    lv.append(65 + (self.lcg >> 8) % 16000)
                blob = struct.pack(f">{MIX_CH}H", *lv)
                for s in (0, 1):
                    uc.mem_write(sym["mix_acc"] + 2 * MIX_CH * s, blob)
            m.uc.hook_add(UC_HOOK_CODE, on_poll, begin=sym["mix_poll"], end=sym["mix_poll"])

        def every(uc, ad, sz, us):              # everything that executes (the idle spin is skipped, not run)
            self.st["exec"] += 1
        m.uc.hook_add(UC_HOOK_CODE, every)
        self._slow_uart()
        m.flush()
        self.pn.settle(3_000_000)

    @staticmethod
    def zero():
        return {"exec": 0, "groups": 0, "waits": 0, "diffs": 0, "screens": 0}

    def _slow_uart(self):                       # (emu_scope.py's model: a transfer completes at the UART's rate)
        ch = self.m.ev.get("edma_tx")
        orig_run, orig_deliver = ch.run, ch.deliver

        def run():
            citer = ch._u16(0x14) & 0x7FFF
            if not citer or self.uart_due is not None:
                return 0
            n = citer * ch._u32(0x08)
            self.uart_due = (self.pn.ticks() + max(1, math.ceil(n / BYTES_A_TICK)), orig_run)
            return 0

        def deliver():
            self._uart_poll()
            return orig_deliver()
        ch.run, ch.deliver = run, deliver

    def _uart_poll(self):
        if self.uart_due is not None and self.pn.ticks() >= self.uart_due[0]:
            fn = self.uart_due[1]
            self.uart_due = None
            fn()

    def ticks(self, n):
        t0 = self.pn.ticks()
        ran = 0
        while self.pn.ticks() - t0 < n:
            ran += self.pn.settle(550_000)
            self._uart_poll()
        return ran

    def long(self, name, k=0):
        return self.m.long(self.sym[name] + 4 * k)

    def page(self):
        if self.a.stock:
            return -2
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

    def func_mod(self):
        self.pn.press_for(FUNC, 10)
        self.pn.press_for(MOD, 6)
        self.pn.release_for(MOD, 30)
        self.pn.release_for(FUNC, 40)

    def response(self, n=4):
        """knob A turned right after a full draw, N times: panel ticks from the turn to the next full draw"""
        out = []
        for k in range(n):
            s0 = self.st["screens"]
            for _ in range(40):                 # until a full draw has just happened
                self.pn.settle(100_000)
                if self.st["screens"] != s0:
                    break
            t0, s1 = self.pn.ticks(), self.st["screens"]
            self.m.pc = self.pn.panelin.encoder(self.m.m, self.pn.profile, 0, 1 if k % 2 == 0 else -1)
            got = None
            for _ in range(200):
                self.pn.settle(100_000)
                self._uart_poll()
                if self.st["screens"] != s1:
                    got = self.pn.ticks() - t0
                    break
            out.append(got)
        return out

    def measure(self, seconds):
        """the load over SECONDS of panel ticks"""
        for c in self.c.values():
            c.runs.clear()
        mix0 = {k: self.long(k) for k in ("mix_alone", "mix_fulls", "mix_groups", "mix_draws")} if not self.a.stock \
            else {}
        whys = {}
        self.st = self.zero()
        ran = 0
        for _ in range(seconds * 11):
            ran += self.ticks(11)
            if not self.a.stock:
                w = self.long("mix_why")
                whys[w] = whys.get(w, 0) + 1
        s = self.st
        out = {"pct": round(100 * s["exec"] / max(1, ran), 2), "instr_s": round(s["exec"] / seconds),
               "ran": ran, "screens_s": round(s["screens"] / seconds, 1), "diffs_s": round(s["diffs"] / seconds, 1),
               "groups_s": round(s["groups"] / seconds, 1), "uart_waits_s": round(s["waits"] / seconds, 1)}
        for k, c in self.c.items():
            out[f"{k}_instr_s"] = round(sum(c.runs) / seconds)
            out[f"{k}_calls_s"] = round(len(c.runs) / seconds, 1)
        for k, v in mix0.items():
            out[f"{k}_s"] = round((self.long(k) - v) / seconds, 1)
        if whys:
            out["mix_why_samples"] = {str(k): v for k, v in sorted(whys.items())}
        return out


# the gate's ceilings (2026-11-20, the User's CPU on the MIXER pages; measured on v0.62.6 9d72c027 before the fix:
# mix_draw 34,000 instructions a draw, the meters +0.9 % of the CPU on Internal Mixer 2/5 with every meter moving, 30
# full draws a second; after: 5,200, +0.3 %; then the User's 10 draws a second, a key or a knob drawn at once)
LIMITS = {"draw_instr": 6000, "added_pct": 0.6, "poll_instr_s": 120_000, "draws_s": 10.6, "response_ticks": 5}


def check_limits(rep, pages) -> None:
    EM.check("every MIXER page with meters measured (2/5, 3/5, 4/5, 5/5)", sorted(pages) == [1, 2, 3, 4],
             str(sorted(pages)))
    for pg, v in sorted(pages.items()):
        EM.check(f"page {pg + 1}/5: a full draw's meters under {LIMITS['draw_instr']} instructions",
                 v["draw_instr"] <= LIMITS["draw_instr"], str(v["draw_instr"]))
        EM.check(f"page {pg + 1}/5: the meters add at most {LIMITS['added_pct']} % of the CPU (all moving)",
                 v["added_pct"] <= LIMITS["added_pct"], str(v["added_pct"]))
        EM.check(f"page {pg + 1}/5: mix_poll under {LIMITS['poll_instr_s']} instructions a second",
                 v["poll_instr_s"] <= LIMITS["poll_instr_s"], str(v["poll_instr_s"]))
    for pg, v in sorted(pages.items()):
        EM.check(f"page {pg + 1}/5: stock's full redraws held to 10 a second (at most {LIMITS['draws_s']})",
                 v["draws_s"] <= LIMITS["draws_s"] and v["draws_s"] >= 9.0, str(v["draws_s"]))
    resp = rep.get("response") or []
    EM.check(f"a knob turned on the MIXER right after a full draw: drawn within {LIMITS['response_ticks']} panel "
             "ticks (not held to the next tenth of a second)", len(resp) >= 3
             and all(t is not None and t <= LIMITS["response_ticks"] for t in resp), str(resp))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", default="out/mixcpu")
    p.add_argument("--seconds", type=int, default=2)
    p.add_argument("--stock", action="store_true")
    p.add_argument("--off", action="store_true", help="the meters off (mix_off)")
    p.add_argument("--usb", type=int, default=6, help="USB mode word (6 Overbridge, 0 none)")
    p.add_argument("--check", action="store_true", help="the gate's ceilings (LIMITS): exit 1 past any")
    a = p.parse_args()
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    r = Rig(a, sym, work)
    m = r.m
    if not a.stock:
        m.write(sym["mix_off"], struct.pack(">I", 1 if a.off else 0))
    m.write(0x4058F2A8, struct.pack(">I", a.usb))
    rep = {"args": vars(a)}

    def shot(name):
        r.pn.panel.write_png(EM.glass(m), str(work / f"{name}.png"))

    r.ticks(60)
    rep["start"] = r.measure(a.seconds)
    shot("start")
    r.pn.press_for(SYN, 6)
    r.pn.release_for(SYN, 60)
    rep["syn"] = r.measure(a.seconds)
    shot("syn")
    seen = []
    pages = {}
    for k in range(6):                          # FUNC + [MOD]: the MIXER, then its pages in turn
        r.func_mod()
        r.ticks(60)
        pg = r.page()
        name = f"mix{k}_pg{pg}"
        if pg in seen and not a.stock:
            break
        seen.append(pg)
        rep[name] = r.measure(a.seconds)
        shot(name)
        print(name, json.dumps(rep[name]), flush=True)
        if not a.stock and not a.off and 1 <= pg <= 4:      # the same page with the meters off: what they add
            m.write(sym["mix_off"], struct.pack(">I", 1))
            r.ticks(30)
            rep[name + "_off"] = r.measure(a.seconds)
            m.write(sym["mix_off"], struct.pack(">I", 0))
            r.ticks(30)
            print(name + "_off", json.dumps(rep[name + "_off"]), flush=True)
            got = rep[name]
            pages[pg] = {"added_pct": round(got["pct"] - rep[name + "_off"]["pct"], 2),
                         "draw_instr": round(got.get("mix_draw_instr_s", 0) / max(1.0, got.get("mix_draw_calls_s", 0))),
                         "poll_instr_s": got.get("mix_poll_instr_s", 0), "draws_s": got.get("screens_s", 0)}
    if not a.stock and pages:                   # a key or knob still redraws at once (the held redraws)
        rep["response"] = r.response()
        print("response", json.dumps(rep["response"]), flush=True)
        m.write(sym["mix_thr_off"], struct.pack(">I", 1))   # (for the record: stock's 30 redraws a second, unheld)
        r.ticks(30)
        rep["unheld"] = r.measure(a.seconds)
        m.write(sym["mix_thr_off"], struct.pack(">I", 0))
        print("unheld", json.dumps(rep["unheld"]), flush=True)
    rep["pages"] = pages
    if a.check:
        check_limits(rep, pages)
    print("start", json.dumps(rep["start"]))
    print("syn", json.dumps(rep["syn"]))
    (work / "mixcpu.json").write_text(json.dumps(rep, indent=1))
    if a.check:
        print("MIXCPU OK" if not EM.FAILS else f"MIXCPU FAILED: {len(EM.FAILS)}")
        return 0 if not EM.FAILS else 1
    print("MIXCPU DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
