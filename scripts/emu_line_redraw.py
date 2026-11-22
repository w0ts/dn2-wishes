"""The moving controls' lines updated alone (csrc/modulation/moving.c mv_lines_only, 2026-11-17), in the ColdFire
emulator: what the glass shows must always be what a full redraw would show.

    python scripts/emu_line_redraw.py --build BUILD.syx --snapshot SNAP --work DIR

Between presents BACK (0x402a10cc) is the frame on the glass. Every group sent to the panel controller is followed
(stock's sender 0x40131f04, at 0x40131f0c after the test channel's jmp), so the glass is modelled byte for byte.
After every step of every scenario:
  - the modelled glass equals BACK (inverted while the test channel inverts it, dt_inv);
  - a full redraw forced then (the screen's dirty byte) draws a FRONT byte-identical to that BACK, so it sends
    nothing: the lines moved alone left exactly what a redraw would have drawn.
Scenarios:
  pages     MONOMACHINE's pages, MACHINEDRUM's, ONESHOT's two (the bottom row's lines), WaveTone's SYN and FLTR
            (stock cells and graphs across them): every movable knob's heard value moved three times, then back
            to set past the linger; then only the cells the full draw left clean moved: those must go alone
            (moving.c's parts counter; a full redraw only where one was already due when the poll ran, "due":
            stock's once-a-second redraw of the shown page met the rest step on 2026-11-17). Every cell of these
            pages must be clean (ONESHOT 2/2's top
            row guards with its widget above the line: its label rows hold the waveform's end marker, drawn later)
  change    lines moving while the page changes (SYN, FLTR, AMP taps)
  overlays  over moving lines: the system meter (FUNC tapped, then pressed again and held), the routes popup (a plain push A, closed by A again), the
            inserts overview (FX held 1.3 s, let go): before, while up, after
  invert    the test channel armed (its armed word, found in dt_present's code): the lines' groups go out inverted
  cost      instructions of mv_poll moving every line of MACHINEDRUM's page alone, against the full path for the same move
            (poll + the screen's draw + panel_diff)
  env2      ENV2's page (AMP 2/2) in its MODE ADSR and AHD: no line under ENV2's own knobs (their cells are ENV1's), PAN
            and VOL's clean and alone; ENV1's DEC alone on stock's AMP page (2026-11-18)
  labels    the load labels' blink (csrc/meter/meter.c lbl_alone, 2026-11-19): CPU's label kept live (its event stamp),
            then DSP's too; every quarter second the other phase, with lines moving between: after each the glass is
            BACK; in the lit phase a full redraw draws exactly it in the labels' rows; in the dark phase those rows hold
            exactly the last full draw's pixels (stock's, as on the rest of the screen); once the labels are up every
            blink goes alone (no page draw), a label come or gone takes the full redraw. The UI's instructions (the
            idle loop left out) and the bytes sent, a blink alone against a blink by a full redraw
  bigmeter  the system meter (csrc/meter/meter.c; 2026-11-21 on [TEMPO] held a second): FUNC held alone, a slow double
            tap and FUNC's old tap + hold show nothing; [TEMPO] held a second shows it over the page body, its rows
            named DSP, CPU, RAM (title bar untouched); its quarter-second updates go alone (only changed groups, none when nothing changed); lines
            moving under it change nothing; let go: the page body exactly as before; FUNC + SRC with it up: gone at
            once, MACHINE SEL exactly as a plain FUNC + SRC; an encoder turn with it up: gone at once
  costs     the UI's instructions (wr_poll a pass, the full draw with panel_diff) with the meter down, and with it up
            (its update alone, a full draw): runs on any build, for the comparison with main's
  restart   a restart that keeps the RAM: the clock near 0, the code's data loaded again, MV->next and the meter's
            deadline far ahead, a profile left running: the lines poll and move at once, every block cleared again,
            the profile stopped (2026-11-18)
  locks     (2026-11-20) p-locks playing on WaveTone's FLTR, MONOMACHINE's and ONESHOT's first pages (the voice's
            smoother state and heard value at the lock, the sound untouched): the lines show and go alone, the glass
            as a full redraw at every step, then the step without the locks
Exit 0 and "LINES OK" when every check holds; the facts and costs in WORK/lines.json.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_modulation as EM  # noqa: E402

MV = 0x46AF8000 + 0x500                 # MOD_MOVING_RAM (cpage.py: MOD_RAM + MOD_CASCADE_BYTES)
MV_MAGIC = 0x4D563032                   # 'MV02'
O_ASKS, O_CELLS, CELL, NCELL = 16, 28, 36, 16  # m68k: an int aligns to 2 bytes, struct mv_cell is 36
O_PARTS, O_FULLS, O_GROUPS, O_DIRTY, O_BACK = 604, 608, 612, 616, 620
C_DRAWN, C_CLEAN = 18, 20               # struct mv_cell
FB_BACK = 0x402A10CC
GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions
PANEL_DIFF = 0x40131FD2
SYN, FLTR, AMP, FX = (0, 1), (0, 2), (0, 3), (0, 4)
FUNC, NO, PUSH_A = (2, 0), (1, 3), (5, 0)
TEMPO = (1, 0)                          # [TEMPO], code 9: held a second, the system meter (2026-11-21)
TICK = 1_100_000                        # instructions a panel tick (121 a second)
PAGES = (("MONOMACHINE", 6, (SYN, SYN, SYN)), ("MACHINEDRUM", 5, (SYN,)), ("ONESHOT", 8, (SYN, SYN)),
         ("WAVETONE", 1, (SYN, FLTR)))


class Rig:
    def __init__(self, a, sym, work):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.m, self.sym, self.work = EM.machine(a.build, a.snapshot), sym, work
        m = self.m
        self.panel = Panel(m, png_dir=str(work / "screens"))
        self.knobs, self.screen, self.facts, self.fails = [], None, {}, []
        m.write(EM.UI_TRACK, b"\x00")

        def on_knob(uc, ad, sz, us):
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            self.knobs.append(struct.unpack(">7i", m.read(sp + 4, 28))[1:])     # x, y, w, id, lo, hi

        def on_screen(uc, ad, sz, us):
            self.screen = struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0]

        def on_group(uc, ad, sz, us):           # (column, page, bytes) at sp + 20 past the 16 bytes saved
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            col, page, ptr = struct.unpack(">3I", m.read(sp + 20, 12))
            for k, b in enumerate(m.read(ptr, 8)):
                self.glass[8 * ((col & 0xFF) + k) + (page & 7)] = b
        m.uc.hook_add(UC_HOOK_CODE, on_knob, begin=sym["mv_knob"], end=sym["mv_knob"])
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, us: self.knobs.clear(), begin=sym["mv_begin"], end=sym["mv_begin"])
        m.uc.hook_add(UC_HOOK_CODE, on_screen, begin=sym["wr_screen"], end=sym["wr_screen"])
        m.uc.hook_add(UC_HOOK_CODE, on_group, begin=GROUP_CONT, end=GROUP_CONT)
        # a full redraw the lines take because one was already due (the dirty byte set when mv_poll ran: stock's
        # own once-a-second redraw of the shown page, a title, a popup) is not a line falling back: the lines are
        # drawn by that redraw. Counted apart ("due"): the poll's entry notes the byte, the next poll (or the end of
        # the settle) sees whether that poll asked for the full redraw
        self.due, self._poll = 0, None

        def on_poll(uc, ad, sz, us):
            if self.screen is not None:
                self._resolve()
                self._poll = (m.read(self.screen + 32, 1)[0], m.long(MV + O_FULLS))
        m.uc.hook_add(UC_HOOK_CODE, on_poll, begin=sym["mv_poll"], end=sym["mv_poll"])
        m.flush()
        self.panel.settle(3_000_000)
        EM.frame(m, sym)
        m.write(sym["sl_lastv"], b"\x00")       # track 1 last played voice 1, which plays it
        m.write(EM.OWNER, struct.pack(">I", 0))
        self.glass = bytearray(self.back())     # the glass as the snapshot left it: the last frame presented

    # --- the machine's state -------------------------------------------------------------------------------
    def back(self):
        return bytes(self.m.read(self.m.long(FB_BACK), 1024))

    def mv(self, off):
        return self.m.long(MV + off)

    def inv(self):
        return self.m.long(self.sym["dt_inv"]) != 0 if "dt_inv" in self.sym else False

    def check(self, what, ok, detail=""):
        print(("  ok    " if ok else "  FAIL  ") + what + (f": {detail}" if detail and not ok else ""), flush=True)
        self.facts[what] = bool(ok)
        if not ok:
            self.fails.append(what)

    def settle(self, n=30_000_000):
        self.panel.settle(n)

    def frames(self, n):
        self.m.write(EM.FRAMES, struct.pack(">I", (self.m.long(EM.FRAMES) + n) & 0xFFFFFFFF))

    def png(self, name, buf):
        p = self.work / "screens" / f"{name}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.panel.panel.write_png(bytes(buf), str(p))
        return str(p)

    # --- the heard values -----------------------------------------------------------------------------------
    def movable(self):
        seen, out = set(), []
        for x, y, w, rid, lo, hi in self.knobs:
            s = EM.record(self.m, rid)[1]
            if rid not in seen and 1 <= s <= 100 and hi > lo:
                seen.add(rid)
                out.append((rid, s, lo, hi))
        return out

    def setv(self, s):
        """the value set: the sound's stored cell (2026-11-20, moving.c own_set: a p-lock shows as the line; rest()
        puts the smoother on it too, so a build before that change reads the same)"""
        return EM.u16(self.m, self.m.long(EM.KIT) + 52 + 20 + 2 * s)

    def move(self, frac, which=None):
        """every movable knob of the last draw (or WHICH of them) heard at FRAC of its range"""
        for j, (rid, s, lo, hi) in enumerate(self.movable()):
            if which is not None and j not in which:
                continue
            heard = lo + int((hi - lo) * frac)
            if heard == self.setv(s):
                heard = heard + 0x100 if heard + 0x100 <= hi else heard - 0x100
            EM.w16(self.m, EM.OUT + 2 * EM.idx(0, s), heard)
        self.frames(100)                        # past the 25-a-second limit
        self.settle()

    def rest(self):
        """heard = set on every slot of voice 1, past the 400 ms linger: no line"""
        for s in range(1, 101):
            v = self.setv(s)
            self.m.write(EM.STATE + 4 * EM.idx(0, s), struct.pack(">I", v << 16))   # the smoother settled on it
            EM.w16(self.m, EM.OUT + 2 * EM.idx(0, s), v)
        for _ in range(2):
            self.frames(700)
            self.settle()

    # --- the proof ------------------------------------------------------------------------------------------
    def identity(self, tag):
        """the glass is BACK (inverted while dt_inv); a full redraw now draws exactly BACK"""
        back = self.back()
        want = bytes(b ^ 0xFF for b in back) if self.inv() else back
        self.check(f"{tag}: the glass shows BACK", bytes(self.glass) == want,
                   f"{sum(a != b for a, b in zip(self.glass, want))} bytes differ")
        if self.screen is None:
            self.check(f"{tag}: the screen object seen", False)
            return
        n0 = len(self.panel.capture.frames)
        self.m.write(self.screen + 32, b"\x01")
        self.settle()
        drawn = bytes(self.panel.capture.frames[-1]) if len(self.panel.capture.frames) > n0 else None
        diff = [i for i in range(1024) if drawn is None or drawn[i] != back[i]]
        if diff:
            self.png(f"{tag}-glass", back)
            if drawn:
                self.png(f"{tag}-redraw", drawn)
        self.check(f"{tag}: a full redraw draws exactly the glass", drawn is not None and not diff,
                   "no frame drawn" if drawn is None else
                   f"{len(diff)} bytes, first at columns {sorted({i // 8 for i in diff})[:8]} pages {sorted({i % 8 for i in diff})}")
        back2 = self.back()
        want2 = bytes(b ^ 0xFF for b in back2) if self.inv() else back2
        self.check(f"{tag}: ... and the glass after it is the new BACK", bytes(self.glass) == want2)

    def identity_labels(self, tag, x0, dark_x0=None):
        """the glass is BACK; a full redraw now draws exactly BACK in the lit labels' rows (y 54..62, columns X0..126:
        all that lbl_alone writes; X0 None in the dark phase, where those pixels are stock's). Elsewhere stock's title
        bar has a part that moves with its own timer and asks no redraw (its bottom row): listed, not checked here (the
        other scenarios check the whole screen)"""
        back = self.back()
        want = bytes(b ^ 0xFF for b in back) if self.inv() else back
        self.check(f"{tag}: the glass shows BACK", bytes(self.glass) == want,
                   f"{sum(a != b for a, b in zip(self.glass, want))} bytes differ")
        n0 = len(self.panel.capture.frames)
        self.m.write(self.screen + 32, b"\x01")
        self.settle()
        drawn = bytes(self.panel.capture.frames[-1]) if len(self.panel.capture.frames) > n0 else None
        mask = {6: 0x03, 7: 0xFE}
        lo = 128 if x0 is None else x0
        inside = [i for i in range(1024) if drawn is not None and lo <= i // 8 < 127 and i % 8 in mask
                  and (drawn[i] ^ back[i]) & mask[i % 8]]
        outside = [i for i in range(1024) if drawn is not None and drawn[i] != back[i] and i not in inside]
        self.check(f"{tag}: a full redraw draws exactly the glass in the labels' rows", drawn is not None and not inside,
                   "no frame drawn" if drawn is None else f"{len(inside)} bytes, columns {sorted({i // 8 for i in inside})[:8]}")
        if dark_x0 is not None and drawn is not None:
            # the dark phase: the label rows hold stock's pixels as its last full draw left them; a redraw now may
            # differ only where stock moved its own pixels since (the rows that differ elsewhere on the screen too)
            rows_in = {(i % 8) * 8 + b for i in range(1024) if dark_x0 <= i // 8 < 127 and i % 8 in (6, 7)
                       for b in range(8) if (drawn[i] ^ back[i]) & (0x80 >> b) and 54 <= (i % 8) * 8 + b <= 62}
            rows_out = {(i % 8) * 8 + b for i in range(1024) if i // 8 < dark_x0 and i % 8 in (6, 7)
                        for b in range(8) if (drawn[i] ^ back[i]) & (0x80 >> b)}
            self.check(f"{tag}: the dark phase's label rows differ from a redraw only on rows stock moved outside "
                       f"them too", rows_in <= rows_out, f"rows inside {sorted(rows_in)}, outside {sorted(rows_out)}")
        if outside:
            print(f"    {tag}: elsewhere {len(outside)} bytes differ (stock's own timer; columns "
                  f"{sorted({i // 8 for i in outside})[:6]} pages {sorted({i % 8 for i in outside})})", flush=True)
        back2 = self.back()
        want2 = bytes(b ^ 0xFF for b in back2) if self.inv() else back2
        self.check(f"{tag}: ... and the glass after it is the new BACK", bytes(self.glass) == want2)

    def drawn(self):
        return [struct.unpack(">h", self.m.read(MV + O_CELLS + CELL * k + C_DRAWN, 2))[0] for k in range(NCELL)]

    def dump(self, tag):
        """each cell of the last draw: its place, clean, inverted, the page's pixels under it, and BACK's row"""
        back, gen = self.back(), self.m.read(MV + 24, 1)[0]
        for k in range(NCELL):
            c = MV + O_CELLS + CELL * k
            rid, gen_k, w = struct.unpack(">H", self.m.read(c, 2))[0], self.m.read(c + 3, 1)[0], self.m.read(c + 4, 1)[0]
            if gen_k != gen or not rid:
                continue
            x, y = struct.unpack(">hh", self.m.read(c + 6, 4))
            drawn, clean, inv = struct.unpack(">h", self.m.read(c + 18, 2))[0], self.m.read(c + 20, 1)[0], self.m.read(c + 21, 1)[0]
            under = self.m.long(c + 30)
            row = "".join(str((back[8 * (x + j) + (y >> 3)] >> (7 - (y & 7))) & 1) for j in range(w))
            above = ["".join(str((back[8 * (x + j) + (yy >> 3)] >> (7 - (yy & 7))) & 1) for j in range(w))
                     for yy in range(y + 1, min(y + 19, 64))]
            print(f"    {tag} cell {k}: record {rid} at ({x},{y}) w {w} drawn {drawn} clean {clean} inv {inv} "
                  f"under {under:#010x}\n      row  {row}\n      above {' '.join(above[:6])}", flush=True)

    def clean_moving(self):
        """(record, index in movable()) of each movable knob whose cell the last full draw left clean"""
        gen, out = self.m.read(MV + 24, 1)[0], []
        cells = {}
        for k in range(NCELL):
            c = MV + O_CELLS + CELL * k
            if self.m.read(c + 3, 1)[0] == gen:
                cells[struct.unpack(">H", self.m.read(c, 2))[0]] = self.m.read(c + C_CLEAN, 1)[0]
        for j, (rid, _s, _lo, _hi) in enumerate(self.movable()):
            if cells.get(rid):
                out.append((rid, j))
        return out

    def _resolve(self):
        if self._poll is not None:
            dirty, fulls = self._poll
            if dirty and self.m.long(MV + O_FULLS) > fulls:
                self.due += self.m.long(MV + O_FULLS) - fulls
            self._poll = None

    def counters(self):
        self._resolve()
        out = {k: self.mv(o) for k, o in (("asks", O_ASKS), ("parts", O_PARTS), ("fulls", O_FULLS),
                                          ("groups", O_GROUPS), ("dirty", O_DIRTY))}
        out["due"] = self.due
        return out

    def page(self, key):
        self.knobs.clear()
        self.panel.tap(key)
        # past the page title's flash. 2026-11-21: 40 M passed by the clock's phase alone: the title's name and our
        # icon beside it (ins.c ins_title_icon) are still sliding then, and a build that moved the code by a few
        # bytes failed "at rest" at 39 M, 40 M and 41 M on three different pages (columns 119..125, the icon);
        # 80 M passes on both builds
        self.settle(80_000_000)


def delta(a, b):
    return {k: b[k] - a[k] for k in a}


def scenario_pages(r, rep):
    for name, mtype, keys in PAGES:
        if not EM.ours_machine(r.m, r.panel, mtype):
            r.check(f"{name}: track 1 set to type {mtype}", False)
            continue
        r.rest()
        for n, key in enumerate(keys):
            tag = f"{name} page {n + 1}"
            r.page(key)
            mov = r.movable()
            r.check(f"{tag}: knobs with a line", bool(mov), f"{len(r.knobs)} knobs drawn")
            if not mov:
                continue
            c0 = r.counters()
            r.identity(f"{tag} at rest")
            for step, (frac, which) in enumerate(((0.75, None), (0.5, None), (0.2, set(range(0, 16, 2))))):
                r.move(frac, which)
                if step == 0:
                    shown = sum(d >= 0 for d in r.drawn())
                    r.check(f"{tag}: lines shown", shown >= 1, f"{shown}")
                r.png(f"{tag}-step{step}", r.back())
                r.identity(f"{tag} step {step + 1}")
            r.rest()
            r.identity(f"{tag} back at rest")
            d = delta(c0, r.counters())
            # the cells a full draw left clean, moved by themselves: the lines alone, never a page draw
            clean = r.clean_moving()
            not_clean = [rid for rid, _s, _lo, _hi in mov if rid not in {cid for cid, _j in clean}]
            c1 = r.counters()
            if clean:
                r.move(0.65, {j for _cid, j in clean})
                r.identity(f"{tag} clean cells only")
                r.rest()
            d1 = delta(c1, r.counters())
            rep[tag] = {"knobs": len(mov), **d, "clean_only": d1, "not_clean": not_clean}
            r.check(f"{tag}: every cell's line can move alone", bool(clean) and not not_clean, f"not clean: {not_clean}")
            r.check(f"{tag}: the clean cells' lines moved alone (no page draw of their own)", not clean or
                    (d1["parts"] >= 1 and d1["fulls"] == d1["due"]), f"{d1}")
            if not clean or d1["fulls"] != d1["due"]:
                r.move(0.75)
                r.dump(tag)
                r.rest()
            print(f"    {tag}: {len(mov)} lines, {d}; clean cells alone {d1}; not clean {not_clean}", flush=True)


def scenario_change(r, rep):
    EM.ours_machine(r.m, r.panel, 1)
    r.rest()
    r.page(SYN)
    for n, key in enumerate((FLTR, AMP, SYN, FLTR)):
        r.move(0.3 + 0.15 * n)
        r.page(key)                             # lines still moving: the new page's own
        r.identity(f"page change {n + 1}")
        r.move(0.9 - 0.1 * n)
        r.identity(f"page change {n + 1}, then moved")
    r.rest()
    rep["change"] = r.counters()


def scenario_overlays(r, rep):
    EM.ours_machine(r.m, r.panel, 1)
    r.rest()
    r.page(FLTR)
    r.move(0.6)
    r.identity("overlays: before")
    # the system meter (csrc/meter/meter.c; 2026-11-21 on [TEMPO] held a second, ovw.c). Past the page's title message
    # first (as scenario_bigmeter): the hold now lasts a second, and stock's title slid back to the pattern's name, on
    # its own timer with no redraw asked, right under the meter's going ("meter gone": columns 17.., page 7)
    r.settle(400_000_000)
    meter_up(r)
    r.move(0.25)
    r.identity("meter up (tap + hold)")
    r.move(0.85)
    r.identity("meter up, moved again")
    r.panel.let_go(TEMPO, 20_000_000)
    r.move(0.4)
    r.identity("meter gone")
    # the routes popup: a plain push A let go at once (2026-11-19, the User: opened on the release), A again closes it
    r.panel.tap(PUSH_A, 30_000_000)
    r.check("the routes popup is up (a plain push A)", EM.guest(r.m, r.sym["mxp_visible"]) & 0xFFFFFFFF == 1)
    r.png("routes-popup", r.back())
    r.move(0.7)
    r.identity("routes popup up")
    r.move(0.15)
    r.identity("routes popup up, moved again")
    r.panel.tap(PUSH_A, 60_000_000)             # A pushed again, no turn: closed (NO only mutes the lit row in it:
                                                # the popup stayed up until its 6 s idle close, inside a later
                                                # scenario); past the title bar's message
    r.check("the routes popup is closed (A pushed again)", EM.guest(r.m, r.sym["mxp_visible"]) & 0xFFFFFFFF == 0)
    r.move(0.55)
    r.identity("routes popup closed")
    # the inserts overview: FX held 1.3 s, then let go (no page step)
    if "ovw_up" in r.sym:
        r.panel.hold(FX, 150 * TICK)
        up = r.m.long(r.sym["ovw_up"])            # an int
        r.check("the inserts overview is up", up != 0)
        r.png("overview", r.back())
        r.move(0.35)
        r.identity("overview up")
        r.panel.let_go(FX, 60_000_000)
        r.move(0.8)
        r.identity("overview closed")
    r.rest()
    rep["overlays"] = r.counters()


TAP_GAP = 525                           # frames: 0.35 s (csrc/meter/meter.c), the second press within it
MTR_CPU_W = 7                           # the meter's block: C in permille


def func_tap(r, frames_down=0):
    """FUNC pressed and let go at once (FRAMES_DOWN frames while down)"""
    r.panel.hold(FUNC, 3_000_000)
    if frames_down:
        r.frames(frames_down)
    r.panel.let_go(FUNC, 3_000_000)


def old_gesture(r, gap=200, first_down=0):
    """FUNC tapped, then (GAP frames later) pressed again and held: the meter's gesture until 2026-11-21 (nothing now).
    A second with no input first"""
    r.frames(1500)
    func_tap(r, first_down)
    r.frames(gap)
    r.panel.hold(FUNC, 30_000_000)


def meter_up(r):
    """[TEMPO] held past a second (2026-11-21, the User: "a long press of the METRONOME button"): the meter, held"""
    r.frames(1500)
    r.panel.hold(TEMPO, 200 * TICK)               # (past ovw.c's 121 ticks with room: the UI is busier on some pages)


def body_rows(buf):
    """the page body's pixels, rows 0..53 (pages 0..5 whole, page 6's rows 48..53): what the meter covers"""
    return bytes(buf[i] for i in range(1024) if i % 8 < 6) + bytes(buf[8 * x + 6] & 0xFC for x in range(128))


def title_rows(buf):
    """the title bar's pixels, rows 54..63"""
    return bytes(buf[8 * x + 7] for x in range(128)) + bytes(buf[8 * x + 6] & 0x03 for x in range(128))


# the meter's row words (csrc/meter/meter.c GLYPH, WIDE_M: rows top to bottom, the left column the high bit)
WORD_GLYPHS = {"D": (6, 5, 5, 5, 6), "S": (7, 4, 7, 1, 7), "P": (6, 5, 6, 4, 4), "C": (7, 4, 4, 4, 7),
               "U": (5, 5, 5, 5, 7), "R": (6, 5, 6, 5, 5), "A": (2, 5, 7, 5, 5), "M": (17, 27, 21, 17, 17)}
ROW_WORDS = ("DSP", "CPU", "RAM")       # the rows top to bottom: pages 4-5, 2-3, 0-1
WORD_COLS = 29                          # columns 0..28: the word alone (the figure starts at 29)


def word_rows(buf):
    """-> for each of the meter's rows, whether columns 0..28 hold exactly its word at twice the 3 x 5 glyphs (M 5
    wide), from x 1, 3 rows below the row's top, a column between letters"""
    out = []
    for r, word in enumerate(ROW_WORDS):
        p0 = 4 - 2 * r
        want = set()
        x = 1
        for ch in word:
            g = WORD_GLYPHS[ch]
            w = 5 if ch == "M" else 3
            for row in range(5):
                for c in range(w):
                    if g[row] >> (w - 1 - c) & 1:
                        for d in range(4):
                            want.add((x + 2 * c + (d & 1), 3 + 2 * row + (d >> 1)))
            x += 2 * w + 2
        have = set()
        for xx in range(WORD_COLS):
            for t in range(16):
                y = 8 * p0 + 15 - t
                if buf[8 * xx + (y >> 3)] & (0x80 >> (y & 7)):
                    have.add((xx, t))
        out.append(have == want)
    return out


def scenario_bigmeter(r, rep):
    """2026-11-19 (the User: "could the cpu/dsp/memory meters be bigger, and only come on double click + hold (or one
    click and a half) on the FUNC button?"). On WaveTone's SYN page (stock's own FUNC hold changes nothing there,
    measured on stock 1.12), lines at rest:
      - FUNC held alone, a slow double tap (1,000 frames between), a long first press (900 frames) then a quick second:
        no meter, the glass as before;
      - FUNC tapped and pressed again 200 frames later, held: the meter over the page body (rows 0..53), the title bar
        as before; the glass is BACK and a full redraw draws exactly it;
      - while up, C and D moved: each quarter second's update drawn alone (no page draw), only changed groups sent; lines
        moving under it change nothing on the glass;
      - let go: one full redraw, the page body as before the meter, the glass as a full redraw draws it;
      - FUNC + SRC with the meter up: the meter gone at once and MACHINE SEL exactly as a plain FUNC + SRC opens it; an
        encoder turn with it up: gone at once.
    The UI's instructions: an update alone against a full draw with the meter up"""
    m = r.m
    big = r.sym.get("mtr_big")
    r.check("bigmeter: the build has the big meter (mtr_big)", big is not None)

    def up():
        return bool(m.long(big)) if big is not None else False

    def counts():
        return tuple(m.long(r.sym[k]) if k in r.sym else 0
                     for k in ("mtr_big_alone", "mtr_big_full", "mtr_big_groups", "mtr_big_due"))
    draws = {"n": 0}
    from unicorn import UC_HOOK_CODE
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: draws.__setitem__("n", draws["n"] + 1),
                  begin=r.sym["wr_screen"], end=r.sym["wr_screen"])
    m.flush()
    EM.ours_machine(m, r.panel, 1)
    r.rest()
    r.page(SYN)
    r.settle(400_000_000)                                        # past the page's title message (as env2)
    redraw(r)
    before = r.back()
    out = {}
    # no meter: FUNC held alone, a slow double tap, a long first press
    for name, act in (("FUNC held alone", lambda: (r.frames(1500), r.panel.hold(FUNC, 30_000_000))),
                      ("a slow double tap", lambda: old_gesture(r, gap=1000)),
                      ("FUNC tapped then held (the old gesture)", lambda: old_gesture(r))):
        act()
        r.frames(400)                                            # (a quarter second on: an update would be due)
        r.settle()
        now = r.back()
        r.check(f"bigmeter: {name}: no meter", not up() and now == before,
                f"up {up()}, {sum(a != b for a, b in zip(now, before))} bytes differ")
        r.panel.let_go(FUNC, 20_000_000)
        r.check(f"bigmeter: {name}: the glass as before after the release", r.back() == before
                and bytes(r.glass) == before)
    # the meter: tap + hold
    d0 = draws["n"]
    meter_up(r)
    shown = r.back()
    r.png("bigmeter-up", shown)
    r.check("bigmeter: [TEMPO] held a second: the meter", up() and body_rows(shown) != body_rows(before))
    r.check("bigmeter: the meter leaves the title bar as it was", title_rows(shown) == title_rows(before))
    r.check("bigmeter: the meter came with one full draw", draws["n"] - d0 >= 1, f"{draws['n'] - d0}")
    r.check("bigmeter: its rows are named DSP, CPU, RAM", word_rows(shown) == [True] * 3, f"{word_rows(shown)}")
    r.identity("bigmeter up")
    # its quarter-second updates, alone
    steps = []
    for k, cpu in enumerate((500, 731, 731, 120)):
        m.write(MTR_RAM + 4 * MTR_CPU_W, struct.pack(">I", cpu))
        if k == 3 and "smp_load_peak" in r.sym:                  # D: 628 permille, the clock and the packet's time set
            m.write(r.sym["smp_load_peak"], struct.pack(">I", 628))
            m.write(r.sym["smp_periods"], struct.pack(">I", 0x1000))
            m.write(r.sym["smp_load_seen"], struct.pack(">I", 0xFFF))
        m.flush()
        c0, n0 = counts(), draws["n"]
        r.frames(400)
        r.settle()
        c1 = counts()
        steps.append({"cpu": cpu, "alone": c1[0] - c0[0], "full": c1[1] - c0[1], "groups": c1[2] - c0[2],
                      "due": c1[3] - c0[3], "page_draws": draws["n"] - n0})
        r.png(f"bigmeter-{k}", r.back())
        # alone, or (once) left to a full redraw stock had already asked for (its own, once a second): never one of
        # the meter's own asking
        r.check(f"bigmeter: update {k} (C {cpu} permille) drawn alone (or by a redraw already due), none asked",
                c1[0] + c1[3] > c0[0] + c0[3] and c1[1] == c0[1], f"{steps[-1]}")
        r.identity(f"bigmeter update {k}")
    r.check("bigmeter: an update with nothing changed sends nothing", steps[2]["groups"] == 0, f"{steps}")
    r.check("bigmeter: the updates went alone (at least three of four)", sum(x["alone"] > 0 for x in steps) >= 3,
            f"{steps}")
    # lines moving under it: nothing of them reaches the glass
    g = bytes(r.glass)
    r.move(0.7)
    r.check("bigmeter: lines moving under the meter leave the page body as it was", body_rows(bytes(r.glass)) ==
            body_rows(g))
    r.identity("bigmeter: lines moved under it")
    r.rest()
    # the release: the page back (its release dropped: no TEMPO screen)
    r.panel.let_go(TEMPO, 20_000_000)
    r.settle()
    after = r.back()
    r.png("bigmeter-after", after)
    r.check("bigmeter: let go: the meter gone", not up())
    r.check("bigmeter: let go: the page body exactly as before the meter", body_rows(after) == body_rows(before),
            f"{sum(a != b for a, b in zip(body_rows(after), body_rows(before)))} bytes differ")
    r.identity("bigmeter let go")
    # FUNC + SRC: plain, then with the meter up
    r.panel.hold(FUNC, 3_000_000)
    r.panel.tap((0, 1), 3_000_000)
    r.panel.let_go(FUNC, 10_000_000)
    r.settle(60_000_000)
    plain = r.back()
    r.png("bigmeter-funcsrc-plain", plain)
    r.panel.tap(NO, 60_000_000)
    redraw(r)
    meter_up(r)
    was = up()
    r.panel.hold(FUNC, 3_000_000)                                # (FUNC's press takes it down: another key)
    gone = not up()
    r.panel.tap((0, 1), 3_000_000)
    r.panel.let_go(FUNC, 10_000_000)
    r.panel.let_go(TEMPO, 10_000_000)
    r.settle(60_000_000)
    withm = r.back()
    r.png("bigmeter-funcsrc-meter", withm)
    r.check("bigmeter: FUNC pressed with the meter up: the meter gone at once", was and gone, f"up {was}, gone {gone}")
    r.check("bigmeter: FUNC + SRC with the meter up, then [TEMPO] let go: MACHINE SEL exactly as a plain FUNC + SRC",
            withm == plain and plain != before, f"{sum(a != b for a, b in zip(withm, plain))} bytes differ")
    r.identity("bigmeter: MACHINE SEL")
    r.panel.tap(NO, 60_000_000)
    redraw(r)
    # an encoder turn with it up
    meter_up(r)
    was = up()
    r.m.pc = r.panel.panelin.encoder(r.m.m, r.panel.profile, 2, 1)
    r.settle(10_000_000)                                         # (the knob's item taken: as emu_waverider_menu's spin)
    r.check("bigmeter: an encoder turn with the meter up: gone at once", was and not up(), f"up before {was}, after {up()}")
    r.panel.let_go(TEMPO, 20_000_000)
    r.settle()
    r.identity("bigmeter: after the turn")
    out["updates"] = steps
    rep["bigmeter"] = out
    print(f"    bigmeter: {json.dumps(out)}", flush=True)


POLL_SITE = 0x4002E464                  # stock's redraw test, jsr wr_poll (dnfw.waverider.coldfire POLL_SITE)


def scenario_costs(r, rep):
    """The UI's instructions with the meter down (runs on any build: wr_poll from the jsr at POLL_SITE, wr_screen from
    the layout): every UI pass at rest on WaveTone's SYN page, and full draws forced; with the meter up (when the build
    has it): its quarter-second update alone, and a full draw with the meter"""
    m = r.m
    op, wrpoll = struct.unpack(">HI", m.read(POLL_SITE, 6))
    if op != 0x4EB9:
        r.check("costs: the redraw test's jsr at POLL_SITE", False, f"{op:#x}")
        return
    EM.ours_machine(m, r.panel, 1)
    r.rest()
    r.page(SYN)
    redraw(r)
    poll = EM.Counter(m, wrpoll)
    scr = EM.Counter(m, r.sym["wr_screen"])
    dif = EM.Counter(m, PANEL_DIFF)
    m.flush()
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None    # noqa: E731

    def window(n=60_000_000):
        for c in (poll, scr, dif):
            c.runs.clear()
        r.settle(n)
        return list(poll.runs), list(scr.runs), list(dif.runs)
    out = {}
    p, s, d = window()
    out["down_idle"] = {"passes": len(p), "pass_min": min(p) if p else None, "pass_median": med(p),
                        "pass_max": max(p) if p else None, "page_draws": len(s)}
    fulls = []
    for _ in range(3):
        for c in (poll, scr, dif):
            c.runs.clear()
        m.write(r.screen + 32, b"\x01")
        r.settle(20_000_000)
        if scr.runs:
            fulls.append(scr.runs[-1] + (dif.runs[-1] if dif.runs else 0))
    out["down_full_draw"] = {"draw_and_diff_median": med(fulls), "runs": fulls}
    if "mtr_big" in r.sym:
        meter_up(r)
        r.settle()
        ups = []
        for k, cpu in enumerate((300, 650, 420)):
            m.write(MTR_RAM + 4 * MTR_CPU_W, struct.pack(">I", cpu))
            m.flush()
            r.frames(400)
            p, s, d = window(20_000_000)
            ups.append({"pass_max": max(p) if p else None, "page_draws": len(s)})
        p, s, d = window()
        idle_up = {"passes": len(p), "pass_min": min(p) if p else None, "pass_median": med(p)}
        fulls_up = []
        for _ in range(3):
            for c in (poll, scr, dif):
                c.runs.clear()
            m.write(r.screen + 32, b"\x01")
            r.settle(20_000_000)
            if scr.runs:
                fulls_up.append(scr.runs[-1] + (dif.runs[-1] if dif.runs else 0))
        r.panel.let_go(TEMPO, 20_000_000)
        r.settle()
        out["up_update_alone"] = ups
        out["up_idle"] = idle_up
        out["up_full_draw"] = {"draw_and_diff_median": med(fulls_up), "runs": fulls_up}
    rep["costs"] = out
    print(f"    costs: {json.dumps(out)}", flush=True)


def armed_word(r):
    """dt_present (csrc/devtest/devtest.c) begins want = armed != 0: tst.l of the test channel's armed word"""
    va = r.sym.get("dt_present")
    if va is None:
        return None
    code = r.m.read(va, 32)                     # its first instruction: tst.l armed (then the compare with dt_inv)
    op, ad = struct.unpack(">HI", code[:6])
    return ad if op == 0x4AB9 and ad != r.sym["dt_inv"] and 0x40000000 <= ad < 0x48000000 else None


def scenario_invert(r, rep):
    armed = armed_word(r)
    r.check("the test channel's armed word found in dt_present", armed is not None)
    if armed is None:
        return
    EM.ours_machine(r.m, r.panel, 6)
    r.rest()
    r.page(SYN)
    r.m.write(armed, struct.pack(">I", 1))
    r.settle()
    r.check("armed: the glass inverted (dt_inv)", r.inv())
    for n, frac in enumerate((0.8, 0.3, 0.6)):
        r.move(frac)
        r.identity(f"inverted, step {n + 1}")
    r.m.write(armed, struct.pack(">I", 0))
    r.settle()
    r.check("disarmed: the glass upright again", not r.inv())
    r.move(0.45)
    r.identity("upright again, moved")
    r.rest()
    rep["invert"] = r.counters()


def scenario_cost(r, rep):
    EM.ours_machine(r.m, r.panel, 5)            # MACHINEDRUM: eight knobs on one page, every cell clean
    r.rest()
    r.page(SYN)
    mov = r.movable()
    poll = EM.Counter(r.m, r.sym["mv_poll"])
    scr = EM.Counter(r.m, r.sym["wr_screen"])
    dif = EM.Counter(r.m, PANEL_DIFF)
    r.m.flush()

    def drawn_now():
        return [struct.unpack(">h", r.m.read(MV + O_CELLS + CELL * k + C_DRAWN, 2))[0] for k in range(NCELL)]

    out = {"lines_on_page": len(mov)}
    for mode in ("alone", "full"):
        r.move(0.1)
        for c in (poll, scr, dif):
            c.runs.clear()
        before = drawn_now()
        if mode == "full":                      # the full path for the same move: BACK not taken as the glass
            r.m.write(MV + O_BACK, struct.pack(">I", 0))
        c0 = r.counters()
        r.move(0.9)
        moved = sum(a != b for a, b in zip(before, drawn_now()))
        d = delta(c0, r.counters())
        out[mode] = {"lines_moved": moved, "poll": max(poll.runs) if poll.runs else None,
                     "screen_draw": scr.runs[-1] if scr.runs else 0, "panel_diff": dif.runs[-1] if dif.runs else 0,
                     "counters": d}
    poll.runs.clear()
    r.frames(20)                                # a poll that finds nothing moved
    r.settle(10_000_000)
    out["poll_idle"] = min(poll.runs) if poll.runs else None
    al, fu = out["alone"], out["full"]
    if al["poll"] and fu["poll"] and al["lines_moved"]:
        al["total"] = al["poll"] + al["screen_draw"] + al["panel_diff"]
        fu["total"] = fu["poll"] + fu["screen_draw"] + fu["panel_diff"]
        out["per_line"] = (al["poll"] - (out["poll_idle"] or 0)) // al["lines_moved"]
    # (a page draw in the same window is stock's own, once a second: the lines took no part in it, fulls 0)
    r.check("cost: the move went alone", al["counters"]["parts"] == 1 and al["counters"]["fulls"] == 0, f"{al}")
    r.check("cost: the same move the full way redrew", fu["counters"]["fulls"] == 1 and fu["screen_draw"] > 0, f"{fu}")
    rep["cost"] = out
    print(f"    cost: {json.dumps(out)}", flush=True)
    r.rest()


AMP_SLOT_OF = {62: 81, 63: 82, 64: 83, 65: 84, 66: 85, 73: 91, 74: 92}   # ENV2's fields: stock's AMP records -> slots
PAN_VOL = {71: 89, 72: 90}                                                  # drawn on ENV2's page too: the sound's
ENV_TAG = 0x0011                                                            # WT_MX_ENV
WISH_MAP = (0x47280000, 0x500000)
MX_RAM = 0x476F0000                                                         # the matrix's state (dnfw.waverider.pages)


def live_cells(r):
    """this draw's cells as moving.c keeps them: {record: (x, y, drawn, clean)}"""
    gen, out = r.m.read(MV + 24, 1)[0], {}
    for k in range(NCELL):
        c = MV + O_CELLS + CELL * k
        rid, g = struct.unpack(">H", r.m.read(c, 2))[0], r.m.read(c + 3, 1)[0]
        if g == gen and rid:
            x, y = struct.unpack(">hh", r.m.read(c + 6, 4))
            out[rid] = (x, y, struct.unpack(">h", r.m.read(c + C_DRAWN, 2))[0], r.m.read(c + C_CLEAN, 1)[0])
    return out


def move_slots(r, heard):
    """voice 1's heard row at HEARD {slot: value}, past the 25-a-second limit"""
    for s, v in heard.items():
        EM.w16(r.m, EM.OUT + 2 * EM.idx(0, s), v)
    r.frames(100)
    r.settle()


def alone_or_due(d):
    """the moved lines went alone, or rode a full redraw that was already due when the poll ran (stock's own, once a
    second; a title message's end): never a full redraw of their own"""
    return d["fulls"] == d["due"] and (d["parts"] >= 1 or d["due"] >= 1)


def redraw(r):
    r.m.write(r.screen + 32, b"\x01")
    r.settle(40_000_000)
    r.settle(120_000_000)                               # past any title message of the page (its expiry is a redraw
                                                        # of stock's own, which the identity check would meet halfway)


def scenario_locks(r, rep):
    """(2026-11-20, moving.c own_set) p-locks playing on every movable knob of WaveTone's FLTR page, MONOMACHINE's SYN 1
    and ONESHOT's SYN 1: the voice's smoother state AND its heard value at the locked value (as stock's applier and
    smoother leave them), the sound's stored values untouched: each line shows (on a build with the change), goes
    alone, and after every step the glass is what a full redraw draws; then the next step without the locks"""
    for name, mtype, keys in (("WAVETONE", 1, (FLTR,)), ("MONOMACHINE", 6, (FLTR, SYN)), ("ONESHOT", 8, (FLTR, SYN))):
        if not EM.ours_machine(r.m, r.panel, mtype):
            r.check(f"locks {name}: track 1 set to type {mtype}", False)
            continue
        r.rest()
        for key in keys:
            r.page(key)
        r.rest()
        mov = r.movable()
        tag = f"locks {name}"
        c0 = r.counters()
        for step, frac in enumerate((0.8, 0.3, 0.6)):
            for rid, s, lo, hi in mov:
                v = lo + int((hi - lo) * frac)
                if v == r.setv(s):
                    v = v + 0x100 if v + 0x100 <= hi else v - 0x100
                r.m.write(EM.STATE + 4 * EM.idx(0, s), struct.pack(">I", v << 16))
                EM.w16(r.m, EM.OUT + 2 * EM.idx(0, s), v)
            r.frames(100)
            r.settle()
            if step == 0 and "mxp_per_note" in r.sym:
                shown = sum(d >= 0 for d in r.drawn())
                r.check(f"{tag}: the locked knobs show their lines", shown >= min(len(mov), NCELL) - 1,
                        f"{shown} of {len(mov)}")
            r.png(f"{tag}-step{step}", r.back())
            r.identity(f"{tag} step {step + 1}")
        r.rest()
        r.identity(f"{tag} the step without locks")
        d = delta(c0, r.counters())
        rep[tag] = {"knobs": len(mov), **d}
        if "mxp_per_note" in r.sym:
            r.check(f"{tag}: the lines went alone (no page draw of their own)", alone_or_due(d), f"{d}")
        print(f"    {tag}: {len(mov)} knobs, {d}", flush=True)


def scenario_env2(r, rep):
    """2026-11-18 (scratch/env2-mod.md). ENV2's page (AMP 2/2) draws ENV2's values with stock's AMP records (62..66,
    73, 74), whose voice-row cells are ENV1's (the amp's): ENV2's ATK..REL lines read ENV2's own knob row (the routes
    into ENV2, csrc/matrix mx_e2_knob); (2026-11-20, the User: MODE, RSET, H routable) MODE, RSET and H (G, H are
    ENV2's DEST and its attenuverter, records 78, 83) read it too, G gets none (moving.c mv_knob, env2_page.c
    env2_field_index); the sound's PAN and VOL keep theirs. Only the cells ENV2's page draws are kept, in either MODE (stock's AMP knobs are
    not drawn under it, env2_amp_draw): each one clean, so a moving line goes alone. ENV1's knobs moved ask nothing
    there. ENV1's page (stock's AMP page) keeps DEC's line, alone"""
    from unicorn import UC_PROT_ALL, UcError
    at, n = WISH_MAP
    for page in range(at & ~0xFFFFF, at + n, 0x100000):
        try:
            r.m.uc.mem_map(page, 0x100000, UC_PROT_ALL)
        except UcError:
            pass
    if not EM.ours_machine(r.m, r.panel, 1):
        r.check("env2: track 1 set to WaveTone", False)
        return
    snd = r.m.long(EM.KIT) + 52
    buf = r.m.alloc(16)
    amp_sub = lambda: r.m.long(r.sym["amp_sub"])                                  # noqa: E731
    set_dec = lambda: r.setv(83)                                                  # noqa: E731
    r.rest()
    r.page(SYN)
    r.page(AMP)
    out = {}
    cells = live_cells(r)
    r.check("env2: ENV1's page (stock's AMP page) up", amp_sub() == 0, f"amp_sub {amp_sub()}")
    r.check("env2: ENV1's page keeps DEC's cell, clean", cells.get(64, (0, 0, 0, 0))[3] == 1, f"{cells}")
    c0 = r.counters()
    move_slots(r, {83: min(EM.TOP, set_dec() + 0x2000)})
    r.identity("env2: ENV1's DEC moved")
    d = delta(c0, r.counters())
    r.check("env2: ENV1's DEC line moved alone", d["parts"] >= 1 and d["fulls"] == d["due"], f"{d}")
    out["env1"] = {"cells": cells, "moved": d}
    r.rest()
    r.page(AMP)
    r.settle(400_000_000)                               # past the page's title message ("ENV2")
    redraw(r)
    r.check("env2: ENV2's page up", amp_sub() == 1, f"amp_sub {amp_sub()}")
    for name, env in (("defaults (ADSR)", None), ("AHD", bytes([8, 127, 32, 96, 24, 0, 1, 0])),
                      ("ADSR", bytes([20, 127, 50, 80, 40, 1, 1, 0]))):
        if env is not None:
            r.m.write(buf, env)
            r.m.flush()
            EM.guest(r.m, r.sym["wish_put"], snd, ENV_TAG, buf, len(env))
            redraw(r)
        cells = live_cells(r)
        theirs = sorted(set(cells) & set(AMP_SLOT_OF))
        r.check(f"env2 {name}: ENV2's ATK..REL, MODE and RSET kept (clean)",
                set(theirs) <= {62, 63, 64, 65, 66, 73, 74} and {64, 73, 74} <= set(theirs)
                and all(cells[i][3] == 1 for i in theirs), f"cells {cells}")
        r.check(f"env2 {name}: G and H are ENV2's DEST and DEP (2026-11-19): no line of the sound's PAN, VOL, nor of G;"
                " H's line is ENV2's (2026-11-20)", not (set(cells) & (set(PAN_VOL) | {78})) and 83 in cells,
                f"cells {cells}")
        c0 = r.counters()
        move_slots(r, {83: min(EM.TOP, set_dec() + 0x2000), 81: 0x7000, 84: 0x1000})   # ENV1's knobs moved: no line here
        r.identity(f"env2 {name}: ENV1's knobs moved under ENV2's page")
        d_amp = delta(c0, r.counters())
        r.check(f"env2 {name}: ENV1's moves ask nothing on ENV2's page", d_amp["asks"] == 0, f"{d_amp}")
        from emulib import mxlayout                     # noqa: PLC0415  (MX_MAGIC: 'MX' and the state's size)
        e2row = MX_RAM + mxlayout.of_magic(r.m.long(MX_RAM)).e2row      # ENV2's knob rows (matrix.c e2row[101 v + k];
                                                            # iroute[16] after them); read back through mx_e2_knob below
        e2dec = e2row + 2 * 2                               # ... its DEC
        hs, ss = r.m.alloc(4), r.m.alloc(4)
        for kk in range(8):                                 # the row as a frame with no route into ENV2 leaves it (the
            EM.guest(r.m, r.sym["mx_e2_knob"], 0, kk, hs, ss)   # rig runs no frame): heard = set, past the linger
            EM.w16(r.m, e2row + 2 * kk, r.m.long(ss))
        for _ in range(2):
            r.frames(700)
            r.settle()
        EM.guest(r.m, r.sym["mx_e2_knob"], 0, 2, hs, ss)
        dec_set = r.m.long(ss)
        # control (2026-11-21): the row taken as before iroute (32 bytes on): DEC written there is not heard
        old_dec = e2dec + 2 * 16
        keep = r.m.read(old_dec, 2)
        EM.w16(r.m, old_dec, min(EM.TOP, dec_set + 0x2000))
        EM.guest(r.m, r.sym["mx_e2_knob"], 0, 2, hs, ss)
        r.check(f"env2 {name}: (control) DEC written in the row as taken before iroute is not heard",
                r.m.long(hs) != min(EM.TOP, dec_set + 0x2000), f"heard {r.m.long(hs):#x}")
        r.m.write(old_dec, bytes(keep))
        c0 = r.counters()
        EM.w16(r.m, e2dec, min(EM.TOP, dec_set + 0x2000))   # a route into ENV2's DEC, as the frame leaves its row
        # (2026-11-21: the row is matrix.c's: DEC as mx_e2_knob hears it is the word written. Until now the row was
        # taken as the state's last, which iroute (e1ba31d5) no longer is: the route landed in another cell, ENV2's DEC
        # never moved, and the check failed on v0.66.1 for the harness's sake)
        EM.guest(r.m, r.sym["mx_e2_knob"], 0, 2, hs, ss)
        r.check(f"env2 {name}: the harness's ENV2 row is matrix.c's (DEC heard as written)",
                r.m.long(hs) == min(EM.TOP, dec_set + 0x2000), f"heard {r.m.long(hs):#x}, written "
                f"{min(EM.TOP, dec_set + 0x2000):#x}")
        r.frames(100)
        r.settle()
        r.identity(f"env2 {name}: ENV2's DEC moved")
        d_e2 = delta(c0, r.counters())
        r.check(f"env2 {name}: ENV2's DEC line shown, moved alone (or with a redraw already due)",
                alone_or_due(d_e2) and live_cells(r).get(64, (0, 0, -1, 0))[2] >= 0, f"{d_e2} cells {live_cells(r)}")
        EM.w16(r.m, e2dec, dec_set)
        r.frames(100)                                       # (DEC back where it was: its own move done before PAN, VOL)
        r.settle()
        # 2026-11-21: since 2026-11-19 G and H are ENV2's DEST and DEP on this page (checked above: no PAN, VOL
        # cell), so the sound's PAN and VOL moved ask nothing here. The check before ("PAN and VOL lines moved alone")
        # passed only by DEC's move back landing in its window, and failed once that move was lost (above)
        c0 = r.counters()
        move_slots(r, {89: 0x2000, 90: 0x5000})
        r.identity(f"env2 {name}: PAN and VOL moved")
        d = delta(c0, r.counters())
        r.check(f"env2 {name}: PAN and VOL moved ask nothing on ENV2's page (not drawn there)",
                d["asks"] == 0 and d["parts"] == 0 and d["fulls"] == d["due"], f"{d}")
        out[name] = {"cells": cells, "amp_moved": d_amp, "env2_dec_moved": d_e2, "pan_vol_moved": d}
        r.rest()
    r.page(AMP)                                          # [AMP]: stock's again (AMP 1/2; the scope is no longer an
                                                         # AMP page since 2026-11-19)
    rep["env2"] = out
    print(f"    env2: {json.dumps(out)}", flush=True)


PRF_MAGIC, PRF_AUDIO_GATE, S_RUN, S_STOPPED, SRC_AUDIO = 0x50524631, 0x50524641, 1, 3, 2


MTR_RAM = 0x46AFF000                    # csrc/meter/meter.c's block (pages.METER_RAM): its words
MTR_AT_D, MTR_AT_C, MTR_SHOWN = 25, 26, 28


def scenario_labels(r, rep):
    from unicorn import UC_HOOK_CODE
    m = r.m
    if "mtr_lbl_alone" not in r.sym:
        r.check("labels: the build has the labels' blink alone (mtr_lbl_alone)", False)
        return
    if "mtr_start_done" in r.sym:   # 2026-11-20 (csrc/meter/startup.c): past the start-up's quiet, as on a unit that
        m.write(r.sym["mtr_start_done"], struct.pack(">I", 1))  # has run a while (the emulator's DSP never reports)
        m.flush()
    EM.ours_machine(m, r.panel, 1)
    r.rest()
    r.page(FLTR)
    r.settle(400_000_000)       # past the page's title message (as env2): its expiry is a redraw of stock's own, which
                                # met a label's coming in the dark phase when the scenarios before it ran longer (the
                                # meter's tap + hold in overlays, 2026-11-19; main's build did the same in that order)

    def stamp(*ws):
        f = m.long(EM.FRAMES) | 1
        for w in ws:
            m.write(MTR_RAM + 4 * w, struct.pack(">I", f))
        m.flush()

    def counts():
        return m.long(r.sym["mtr_lbl_alone"]), m.long(r.sym["mtr_lbl_full"])
    seen = {"draws": 0, "groups": 0, "busy": 0}
    import emu_coupled as _EC
    spin = _EC.IDLE_SPIN

    def on_busy(uc, ad, sz, us):
        if ad != spin:
            seen["busy"] += 1
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: seen.__setitem__("draws", seen["draws"] + 1),
                  begin=r.sym["wr_screen"], end=r.sym["wr_screen"])
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: seen.__setitem__("groups", seen["groups"] + 1),
                  begin=GROUP_CONT, end=GROUP_CONT)
    m.flush()
    hb = m.uc.hook_add(UC_HOOK_CODE, on_busy)
    m.flush()
    a0, f0 = counts()
    alone_steps, full_steps = [], []
    last_full = {}
    for step in range(12):
        if step in (0, 6):                                    # a label comes: in the blink's lit phase (meter.c
            f = m.long(EM.FRAMES)                             # icons_lit: lit while (f / 375) is even). Come in the
            if f % 750 >= 375:                                # dark phase, its first poll changes nothing on screen
                r.frames(750 - f % 750)                       # and a full draw of stock's that falls before the lit
                                                              # phase may take it in, so the lit phase then goes alone:
                                                              # where stock's redraw falls in the UI loop decided the
                                                              # check (2026-11-19, the plain push's overlays, frames
                                                              # the same, the UI loop's phase not)
        stamp(MTR_AT_C, *((MTR_AT_D,) if step >= 6 else ()))   # CPU live throughout, DSP from step 6 (a label come)
        if step % 3 == 1:
            r.move(0.3 + 0.05 * step)                         # lines moving between the blinks
        bq = seen["busy"]
        r.settle()                                            # (a settle with no blink: the UI's baseline)
        quiet = seen["busy"] - bq
        r.frames(375)                                         # the other phase of the blink
        a1, f1 = counts()
        d1, g1, b1 = seen["draws"], seen["groups"], seen["busy"]
        r.settle()
        a2, f2 = counts()
        rec = {"step": step, "full_draws": seen["draws"] - d1, "groups": seen["groups"] - g1,
               "ui_instr": seen["busy"] - b1 - quiet}
        if a2 > a1 and f2 == f1:
            alone_steps.append(rec)
        elif f2 > f1:
            full_steps.append(rec)
        shown = m.long(MTR_RAM + 4 * MTR_SHOWN)
        if step in (2, 7):
            r.png(f"labels-{step}", r.back())
        r.identity_labels(f"labels: step {step} (shown {shown:#x})", {0x2: 100, 0x3: 99}.get(shown),
                          dark_x0=(99 if step >= 6 else 100) if shown == 0 else None)
    a3, f3 = counts()
    m.uc.hook_del(hb)
    m.flush()
    r.check("labels: once up, every blink goes alone", a3 - a0 >= 8, f"alone {a3 - a0}, full {f3 - f0}")
    r.check("labels: a label come takes a full redraw", f3 - f0 >= 2, f"full {f3 - f0}")
    stamp()                                                   # (nothing stamped: the labels age out)
    for _ in range(6):
        r.frames(375)
        r.settle()
    r.identity_labels("labels: aged out", None)
    r.rest()
    quiet = [x for x in alone_steps if x["step"] % 3 != 1 and x["full_draws"] == 0]
    fq = [x for x in full_steps if x["step"] % 3 != 1]
    med = lambda xs, k: sorted(x[k] for x in xs)[len(xs) // 2] if xs else None    # noqa: E731
    rep["labels"] = {"alone": a3 - a0, "full": f3 - f0, "alone_steps": alone_steps, "full_steps": full_steps,
                     "blink_alone": {"ui_instr": med(quiet, "ui_instr"), "groups": med(quiet, "groups")},
                     "blink_full": {"ui_instr": med(fq, "ui_instr"), "groups": med(fq, "groups")}}
    print(f"    labels: blinks alone {a3 - a0}, by a full redraw {f3 - f0}; a blink alone: UI instructions "
          f"{med(quiet, 'ui_instr')}, groups {med(quiet, 'groups')} ({10 * (med(quiet, 'groups') or 0)} bytes); by a "
          f"full redraw: {med(fq, 'ui_instr')}, groups {med(fq, 'groups')}", flush=True)


def scenario_restart(r, rep):
    """2026-11-18 (the User: "the bar/line that display is slow ... sometimes it works sometimes not"; on the DN2 after
    a restart MV->next stood 2 h 17 min ahead of the frame clock). A restart that keeps the RAM: FRAMES (stock's BSS)
    starts again near 0, our code's data is loaded again (each block's "cleared since this load" word 0), and the
    blocks above BSS keep the last run's words, MV->next far ahead of the new clock and a profile left running among
    them. Then, at once: the lines poll and move (alone), the meter's block, the matrix's and the cascade's are
    cleared again, and the profile left running is stopped (the audio interrupt records nothing into it)"""
    EM.ours_machine(r.m, r.panel, 1)
    r.rest()
    r.page(SYN)
    mov = r.movable()
    r.move(0.7)
    r.check("restart: lines shown before", any(d >= 0 for d in r.drawn()), f"{r.drawn()}")
    r.rest()
    prof = 0x47700000                                                          # PROF_RAM (dnfw.waverider.pages)
    from unicorn import UC_PROT_ALL, UcError
    try:
        r.m.uc.mem_map(prof, 0x100000, UC_PROT_ALL)
    except UcError:
        pass
    r.m.write(prof, struct.pack(">4I", PRF_MAGIC, S_RUN, SRC_AUDIO, 0))         # magic, state, source, n
    r.m.write(prof + 88, struct.pack(">I", PRF_AUDIO_GATE))
    old = r.m.long(EM.FRAMES)
    r.m.write(MV + 20, struct.pack(">I", (old + 10_000_000) & 0xFFFFFFFF))    # a deadline of the last run, far ahead
    r.m.write(r.sym["mtr_ram"] + 4 * 18, struct.pack(">I", (old + 10_000_000) & 0xFFFFFFFF))   # MTR_DRAW_NEXT
    r.m.write(EM.FRAMES, struct.pack(">I", 1000))                              # the new run's clock
    for w in ("mv_loaded", "mc_loaded", "mtr_loaded", "mx_loaded", "prof_mine"):
        r.m.write(r.sym[w], struct.pack(">I", 0))                              # the code's data, loaded again
    r.m.flush()
    mx0 = r.m.long(r.sym["mx_compiles"])
    redraw(r)                                           # the load's first draw (the cells kept anew)
    r.check("restart: the moving lines' block cleared at this load's first pass", r.mv(4) < 10 and r.mv(12) < 400,
            f"draws {r.mv(4)} polls {r.mv(12)}")
    p0, c0 = r.mv(12), r.counters()
    r.move(0.3)
    r.identity("restart: lines moved after the restart")
    d = delta(c0, r.counters())
    polls = r.mv(12) - p0
    r.check("restart: the lines poll at once", polls >= 1, f"polls {polls}")
    r.check("restart: the moved lines are drawn (alone)", d["parts"] >= 1 and d["fulls"] == d["due"], f"{d}")
    r.check("restart: MV->next no further ahead than one wait", (r.mv(20) - r.m.long(EM.FRAMES)) & 0xFFFFFFFF <= 60,
            f"next {r.mv(20)} clock {r.m.long(EM.FRAMES)}")
    r.check("restart: every block cleared since this load (moving lines, meter, matrix)",
            all(r.m.long(r.sym[w]) == 1 for w in ("mv_loaded", "mtr_loaded", "mx_loaded")),
            str({w: r.m.long(r.sym[w]) for w in ("mv_loaded", "mtr_loaded", "mx_loaded")}))
    dn = r.m.long(r.sym["mtr_ram"] + 4 * 18)
    r.check("restart: the meter's redraw deadline is on the new clock", dn <= r.m.long(EM.FRAMES) + 1500, f"{dn}")
    r.check("restart: the matrix laid its tables out again", r.m.long(r.sym["mx_compiles"]) > mx0)
    EM.frame(r.m, r.sym)                                                       # an audio frame: the cascade's pre-pass
    r.check("restart: the cascade's block cleared since this load", r.m.long(r.sym["mc_loaded"]) == 1)
    fr = r.m.alloc(16)
    EM.guest(r.m, r.sym["prof_audio"], fr)                                     # the audio interrupt's call
    st, n = r.m.long(prof + 4), r.m.long(prof + 12)
    r.check("restart: a profile left running is stopped, nothing recorded",
            st == S_STOPPED and n == 0 and r.m.long(prof + 88) == 0, f"state {st} n {n} gate {r.m.long(prof + 88):#x}")
    r.m.write(prof, struct.pack(">I", 0))                                      # (the block as the rig found it)
    r.rest()
    rep["restart"] = {"polls": polls, "moved": d, "lines": len(mov)}
    print(f"    restart: {json.dumps(rep['restart'])}", flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--scenario", default="pages,change,overlays,invert,cost,env2,labels,bigmeter,costs,restart,locks")
    a = p.parse_args()
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    for need in ("mv_knob", "mv_begin", "mv_poll", "mv_end", "wr_screen", "sl_lastv"):
        if need not in lay:
            print(f"FAIL: {need} not in the build's layout")
            return 1
    r = Rig(a, lay, work)
    rep = {}
    for sc in a.scenario.split(","):
        print(f"  --- {sc} ---", flush=True)
        {"pages": scenario_pages, "change": scenario_change, "overlays": scenario_overlays,
         "invert": scenario_invert, "cost": scenario_cost, "env2": scenario_env2,
         "labels": scenario_labels, "bigmeter": scenario_bigmeter, "costs": scenario_costs,
         "restart": scenario_restart, "locks": scenario_locks}[sc](r, rep)
    r.check("the moving controls' state is MV02 (this layout)", r.mv(0) == MV_MAGIC, f"{r.mv(0):#x}")
    faults = getattr(r.m, "faults", None)
    (work / "lines.json").write_text(json.dumps({"facts": r.facts, "report": rep, "fails": r.fails}, indent=1))
    print("LINES OK" if not r.fails else "LINES FAILED: " + "; ".join(r.fails[:6]))
    return 0 if not r.fails and not faults else 1


if __name__ == "__main__":
    raise SystemExit(main())
