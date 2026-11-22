"""The page keys' latency in the ColdFire emulator, OS 1.12, with the panel UART at the unit's rate (the User,
2026-11-18: "switching to amp and FX page is slower than other pages").

    python scripts/emu_page_keys.py --snapshot SNAP [--build BUILD.syx] --json OUT [--hold-ticks 8]

Without --build the snapshot runs as it is (stock 1.12's own ui1200M); with it, as scripts/emu_scope.py runs a build
(its own snapshot, EM.machine).

Each key is tapped as a person taps it: pressed, held HOLD panel ticks (8: 66 ms, well before the first repeat at 24),
let go. From another page first (TRIG from SYN, the others from TRIG), then for AMP and FX the same key again on their
own page (AMP 2/2; FX 2/3, 3/3 when the build has them; the scope left AMP on 2026-11-19). For each tap:
  press_ms, release_ms  from the press (and from the release) until the new page has fully left the UART: the panel
                        tick of the last change of BACK (the frame on the glass) plus the bytes still queued then,
                        drained at UART8's 15,625 bytes a second
  draws                 the screen's full draws (0x4011d60a with its dirty byte set) from the press until then, and
                        their instructions with panel_diff's (the CPU the step took; the unit has about a fifth of the
                        emulator's UI CPU, so on the unit these are what the latency grows with)
  groups                8-px groups sent in that time
The UART is modelled as emu_scope.py's Rig models it (a transfer completes once its bytes would have left).
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
FB_BACK = 0x402A10CC
GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions (emu_scope.py)
PANEL_DIFF = 0x40131FD2
SCREEN_DRAW = 0x4011D60A                # (screen, canvas): draws only when the screen's byte +32 is set
RING_HEAD, RING_PEND, RING_TAIL = 0x4058E5D0, 0x4058E5D8, 0x4058E5DC
TCD35_CITER, TCD35_BITER = 0xFC045474, 0xFC04547C
BYTES_A_TICK = 156_250 / 10 / 121
KEYS = {"TRIG": 1, "SYN": 2, "FLTR": 3, "AMP": 4, "FX": 5, "MOD": 6}    # the firmware's codes (ovw.c, scope.c, panel.py)
QUIET = 40                              # ticks with no change and an empty UART: the page is out


class Rig:
    def __init__(self, a):
        from emulib.machine import Machine
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.a = a
        self.m = m = EM.machine(a.build, a.snapshot) if a.build else Machine(a.snapshot)
        self.panel = Panel(m, png_dir=str(pathlib.Path(a.json).with_suffix("")) + "_png")
        self.tick_last, self.ticks, self.uart_due = None, 0, None
        self.groups = 0
        self.draws = []                 # (tick, instructions) of each full draw
        self.diffs = []
        draw = {"n": 0, "h": None, "ret": None, "full": False}

        def on_group(uc, ad, sz, us):
            self.groups += 1
        m.uc.hook_add(UC_HOOK_CODE, on_group, begin=GROUP_CONT, end=GROUP_CONT)

        def counter(entry, sink, full_test=None):
            st = {"n": 0, "h": None, "ret": None, "keep": True}

            def tick(uc, ad, sz, us):
                if ad == st["ret"]:
                    uc.hook_del(st["h"])
                    st["h"] = None
                    if st["keep"]:
                        sink.append((self.ticks, st["n"]))
                else:
                    st["n"] += 1

            def enter(uc, ad, sz, us):
                if st["h"] is None:
                    sp = uc.reg_read(K.UC_M68K_REG_A7)
                    st["ret"] = struct.unpack(">I", bytes(uc.mem_read(sp, 4)))[0]
                    st["n"] = 0
                    st["keep"] = full_test(uc, sp) if full_test else True
                    st["h"] = uc.hook_add(UC_HOOK_CODE, tick)
            m.uc.hook_add(UC_HOOK_CODE, enter, begin=entry, end=entry)

        def full(uc, sp):                                       # the screen's dirty byte (+32) set: a full draw
            screen = struct.unpack(">I", bytes(uc.mem_read(sp + 4, 4)))[0]
            return bytes(uc.mem_read(screen + 32, 1))[0] != 0
        counter(SCREEN_DRAW, self.draws, full)
        self.trace = []                 # (tick, what): our ovw_key's items and ovw_poll's replays (a build only)
        if a.build:
            lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]

            def on_key(uc, ad, sz, us):
                sp = uc.reg_read(K.UC_M68K_REG_A7)
                code, flags = struct.unpack(">II", bytes(uc.mem_read(sp + 8, 8)))
                self.trace.append((self.ticks, f"key {code} {flags:#x}"))
            if "ovw_key" in lay:
                m.uc.hook_add(UC_HOOK_CODE, on_key, begin=lay["ovw_key"], end=lay["ovw_key"])
            if "ovw_taps" in lay:
                self.taps_va = lay["ovw_taps"]
        counter(PANEL_DIFF, self.diffs)
        self._slow_uart()
        m.flush()
        from emu.pit import INSTR_PER_SEC
        self.panel.frame_clock(EM.FRAMES, per_sec=round(1500 * INSTR_PER_SEC / (121 * 1_100_000)))
        self.panel.settle(3_000_000)

    def now(self):
        t = self.m.long(TICK) & 0xFFF
        if self.tick_last is not None:
            self.ticks += (t - self.tick_last) & 0xFFF
        self.tick_last = t
        return self.ticks

    def run_ticks(self, n):
        for _ in range(n):
            self.panel.settle(1_100_000)
            self.now()
            self._uart_poll()

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
            self.uart_due = (self.now() + max(1, math.ceil(n / BYTES_A_TICK)), orig_run)
            return 0

        def deliver():                          # time read here too: a raw settle never calls now() (emu_scope.py,
            self.now()                          # 2026-11-19)
            self._uart_poll()
            return orig_deliver()
        ch.run, ch.deliver = run, deliver

    def _uart_poll(self):
        if self.uart_due is not None and self.ticks >= self.uart_due[0]:
            fn = self.uart_due[1]
            self.uart_due = None
            fn()

    def occupancy(self):
        citer = struct.unpack(">H", self.m.read(TCD35_CITER, 2))[0] & 0x7FFF
        biter = struct.unpack(">H", self.m.read(TCD35_BITER, 2))[0] & 0x7FFF
        d1 = ((citer - biter) + (self.m.long(RING_HEAD) - self.m.long(RING_TAIL))) & 0xFFF
        return d1 + self.m.long(RING_PEND)

    def back(self):
        return bytes(self.m.read(self.m.long(FB_BACK), 1024))

    def settle_out(self, limit=121 * 4):
        """run until the glass has not changed for QUIET ticks with the UART empty -> the time the last change was
        out (ticks, fractional), or None"""
        last, out, quiet, pending = self.back(), None, 0, False
        self.changes = []
        for _ in range(limit):
            self.run_ticks(1)
            b, occ = self.back(), self.occupancy()
            if b != last:                       # a frame swapped in: out once the bytes queued now have left
                self.changes.append((self.ticks, sum(1 for i in range(1024) if b[i] != last[i])))
                if self.a.shots and len(self.changes) <= 3:
                    self.panel.panel.write_png(b, f"{self.a.shots}_{self.shot_name}_c{len(self.changes)}.png")
                last, quiet, pending = b, 0, True
                out = self.ticks + occ / BYTES_A_TICK
            elif pending and occ:               # (a byte sent later on its own, not a frame's, is not counted)
                out = self.ticks + occ / BYTES_A_TICK
                quiet = 0
            else:
                pending = pending and occ > 0
                quiet += 1
                if quiet >= QUIET:
                    return out
        return out

    shot_name = "x"

    def tap(self, code, hold):
        ch, bit = (code - 1) >> 3, (code - 1) & 7
        p = self.panel
        self.settle_out()                                       # nothing moving before the press
        g0, d0, f0 = self.groups, len(self.draws), len(self.diffs)
        before = self.back()
        t0 = self.now()
        self.m.pc = p.panelin.press(self.m.m, p.profile, ch, bit)
        self.run_ticks(hold)
        t1 = self.now()
        self.m.pc = p.panelin.release(self.m.m, p.profile, ch, bit)
        out = self.settle_out()
        changed = self.back() != before
        draws = self.draws[d0:]
        tr0 = [(t - t0, w) for t, w in self.trace if t >= t0]
        self.trace.clear()
        diffs = self.diffs[f0:]
        res = {"changed": changed,
               "press_ms": round((out - t0) * 1000 / 121, 1) if out is not None else None,
               "release_ms": round((out - t1) * 1000 / 121, 1) if out is not None else None,
               "draws": len(draws), "draws_before_release": sum(1 for t, _ in draws if t < t1),
               "draw_instr": sum(n for _, n in draws), "diff_instr": sum(n for _, n in diffs),
               "groups": self.groups - g0, "changes": [(t - t0, n) for t, n in self.changes],
               "draw_ticks": [t - t0 for t, _ in draws], "trace": tr0}
        return res


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True)
    p.add_argument("--build")
    p.add_argument("--json", required=True)
    p.add_argument("--hold-ticks", type=int, default=8)
    p.add_argument("--shots", help="each change's glass saved as SHOTS_<key>_cN.png (the first round)")
    p.add_argument("--rounds", type=int, default=2, help="each tap measured this many times (the mean is reported)")
    a = p.parse_args()
    r = Rig(a)
    rep = {"build": a.build or "snapshot as it is", "hold_ticks": a.hold_ticks, "taps": {}}
    plan = [("TRIG", "SYN"), ("SYN", "TRIG"), ("FLTR", "TRIG"), ("MOD", "TRIG"), ("AMP", "TRIG"), ("AMP 2", None),
            ("FX", "TRIG"), ("FX 2", None), ("FX 3", None)]
    for rnd in range(a.rounds):
        for name, frm in plan:
            key = name.split()[0]
            if frm:
                r.tap(KEYS[frm], a.hold_ticks)
            r.shot_name = name.replace(" ", "") if rnd == 0 else "x"
            res = r.tap(KEYS[key], a.hold_ticks)
            r.panel.panel.write_png(r.back(), str(pathlib.Path(a.json).with_suffix("")) + f"_{name.replace(' ', '')}_{rnd}.png")
            print(f"  round {rnd} {name:6s} {json.dumps(res)}", flush=True)
            rep["taps"].setdefault(name, []).append(res)
    summary = {}
    for name, runs in rep["taps"].items():
        ok = [x for x in runs if x["press_ms"] is not None]
        summary[name] = {k: round(sum(x[k] for x in ok) / len(ok), 1) if ok else None
                         for k in ("press_ms", "release_ms", "draws", "draw_instr", "diff_instr", "groups")}
        summary[name]["changed"] = all(x["changed"] for x in runs)
    rep["summary"] = summary
    for name, s in summary.items():
        print(f"  {name:6s} {json.dumps(s)}")
    pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    print("PAGEKEYS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
