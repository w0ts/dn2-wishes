"""UP / DOWN on the page keys' pages, in the ColdFire emulator, OS 1.12 (the User, 2026-11-20: "UP/DOWN should page
through the pages of AMP and FX ... like any other pages").

    python scripts/emu_updown_pages.py --snapshot SNAP [--build BUILD.syx] (--json OUT | --work DIR) [--probe] [--stock]

Without --build the snapshot runs as it is (stock 1.12's own ui1200M); with it, the build on its own snapshot (as
scripts/emu_page_keys.py). Keys are pressed as a person presses them: down 8 panel ticks, then let go, with stock's
own key repeats (the panel tick clock, emulib.panel tick_clock).

A page is told by its title bar (the glass's top rows, as text). For each page key (TRIG, SYN, FLTR, MOD, AMP, FX):
its pages are listed by tapping the key again until page 1 comes back; then from page 1 DOWN is tapped as many times,
then UP, and DOWN is held a second (its repeats). The same under each condition: FUNC held, a trig held, KEYBOARD
on, grid recording on. --probe prints what happened and checks nothing (the measurement of stock); without it the
checks run and "UPDOWN OK" ends a pass (WORK/updown.json).

Measured on stock 1.12 (--stock --probe on ui1200M, 2026-11-20): on every page with pages (TRIG 2, SYN 3, FLTR 2, MOD 3,
FUNC + FX's send pages 3) DOWN steps to the next page and UP to the previous one, on the press and on each key repeat
(held a second it runs to the last page), and stops at the ends (the page key wraps; the arrows do not). FUNC + DOWN
steps nothing (stock shows its own box). A trig held, KEYBOARD on and grid recording page as without. Stock's AMP and
FX pages have one page each and do nothing with the arrows. The checks hold every key's pages to that rule (AMP 2
pages and FX 3 on the build, csrc/scope/scope.c amp_arrow, csrc/inserts/ins.c fx_arrow), compare the glass each AMP /
FX step leaves with the glass the page key leaves on the same page, and check that a routes popup of ours (a knob
pushed on AMP 1/2) keeps the arrows. Main before 2026-11-20 fails the AMP and FX checks (the arrows did nothing there).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
import emu_modulation as EM  # noqa: E402

KEYS = {"TRIG": 1, "SYN": 2, "FLTR": 3, "AMP": 4, "FX": 5, "MOD": 6}
YES, UP, NO, LEFT, DOWN, RIGHT, FUNC, KEYBOARD, REC, TRIG1 = 10, 11, 12, 13, 14, 15, 17, 18, 19, 25
ENC_A = 41                              # A's push
INS_FUZZ, INS_TAPE = 1, 2               # csrc/inserts/ins.c T_FUZZ, T_TAPE: the two inserts with a page 2
KB_ON = 0x42432A9C                      # KEYBOARD on (emu_coupled_stocknote.py)
TAP_TICKS, AFTER_TICKS, SETTLE_TICKS = 8, 30, 90
OURS = ("AMP", "FX")                    # the keys with pages of ours: their steps' glass compared with the key's
PAGES = {"TRIG": 2, "SYN": 3, "FLTR": 2, "MOD": 3, "AMP": 2, "FX": 3, "SEND": 3}   # the build's pages, each key
TITLE_ROWS = 10


def key_of(code: int) -> tuple[int, int]:
    return (code - 1) >> 3, (code - 1) & 7


class Rig:
    def __init__(self, a):
        from emulib.machine import Machine
        from emulib.panel import Panel
        self.built = bool(a.build)
        self.m = m = EM.machine(a.build, a.snapshot) if a.build else Machine(a.snapshot)
        self.p = Panel(m, png_dir=str(pathlib.Path(a.json).with_suffix("")) + "_png")
        from emu import panel as P
        self.P = P
        m.flush()
        self.p.tick_clock(EM.FRAMES)
        self.p.settle(3_000_000)
        self.p.run_ticks(60)
        self.lay = {}
        if a.build:
            self.lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]

    def turn(self, enc: int, delta: int) -> None:
        self.m.pc = self.p.panelin.encoder(self.m.m, self.p.profile, enc, delta)
        self.p.run_ticks(AFTER_TICKS)

    def settled(self) -> bytes:
        """the glass once a title's slide and the page's draws are over"""
        self.p.run_ticks(SETTLE_TICKS)
        return self.glass()

    def same(self, a: bytes | None, b: bytes | None) -> bool:
        """the page under the title bar alike (the title itself is compared as text right after each step; read
        seconds later it can differ on a page that did not change: measured, cause not traced)"""
        return a is not None and b is not None and self.P.ascii_art(a)[TITLE_ROWS:] == self.P.ascii_art(b)[TITLE_ROWS:]

    def png(self, buf: bytes, name: str) -> None:
        self.p.png_dir.mkdir(parents=True, exist_ok=True)
        self.P.write_png(buf, str(self.p.png_dir / f"{name}.png"))

    def glass(self) -> bytes:
        return EM.glass(self.m)

    def title(self) -> str:
        return "\n".join(self.P.ascii_art(self.glass())[:TITLE_ROWS])

    def down(self, code: int, ticks: int = 0) -> None:
        self.p.press_for(key_of(code), ticks) if ticks else self._press(code)

    def _press(self, code: int) -> None:
        self.m.pc = self.p.panelin.press(self.m.m, self.p.profile, *key_of(code))

    def up(self, code: int, ticks: int = 0) -> None:
        self.p.release_for(key_of(code), ticks) if ticks else self._release(code)

    def _release(self, code: int) -> None:
        self.m.pc = self.p.panelin.release(self.m.m, self.p.profile, *key_of(code))

    def tap(self, code: int, hold: int = TAP_TICKS, after: int = AFTER_TICKS) -> None:
        self.p.press_for(key_of(code), hold)
        self.p.release_for(key_of(code), after)

    def hold_for(self, code: int, ticks: int, after: int = AFTER_TICKS) -> None:
        self.p.press_for(key_of(code), ticks)
        self.p.release_for(key_of(code), after)


class Pages:
    """the titles seen, numbered in the order they first came"""

    def __init__(self):
        self.titles: list[str] = []

    def id(self, t: str) -> int:
        if t not in self.titles:
            self.titles.append(t)
        return self.titles.index(t)


def func_fx(r: Rig) -> None:
    """FUNC + [FX]: stock's send pages"""
    r.down(FUNC, 4)
    r.tap(KEYS["FX"])
    r.up(FUNC, AFTER_TICKS)


def enter(r: Rig, name: str) -> None:
    """NAME's page 1: another page first (TRIG from SYN, the others from TRIG), then NAME's key (SEND: FUNC + FX)"""
    r.tap(KEYS["SYN"] if name == "TRIG" else KEYS["TRIG"])
    func_fx(r) if name == "SEND" else r.tap(KEYS[name])


def page_key(r: Rig, name: str) -> None:
    func_fx(r) if name == "SEND" else r.tap(KEYS[name])


def cycle(r: Rig, name: str, pg: Pages, shots: dict) -> list[int]:
    """NAME's pages, its key tapped until page 1 is back; SHOTS[page]: the glass settled on it"""
    enter(r, name)
    seq = [pg.id(r.title())]
    shots[seq[0]] = r.settled()
    for _ in range(6):
        page_key(r, name)
        t = pg.id(r.title())
        if t == seq[0]:
            break
        seq.append(t)
        shots[t] = r.settled()
    return seq


def taps(r: Rig, name: str, pg: Pages, code: int, n: int, hold_code: int | None = None, setup=None,
         teardown=None, first: int = 0, shots: list | None = None, downs: int = 0) -> list[int]:
    """from NAME's page 1 (its key tapped FIRST more times; after SETUP, DOWN tapped DOWNS times), CODE tapped N
    times -> the page after each (with HOLD_CODE held throughout: then its release's too); SHOTS gets the glass settled
    after each tap"""
    enter(r, name)
    for _ in range(first):
        page_key(r, name)
    if setup:
        setup()
    for _ in range(downs):
        r.tap(DOWN)
    out = [pg.id(r.title())]
    if hold_code is not None:
        r.down(hold_code, 4)
    for _ in range(n):
        r.tap(code)
        out.append(pg.id(r.title()))
        if shots is not None:
            shots.append(r.settled())
    if hold_code is not None:
        r.up(hold_code, AFTER_TICKS)
        out.append(pg.id(r.title()))
    if teardown:
        teardown()
    return out


def keyboard(r: Rig, rep: dict, name: str) -> None:
    r.tap(KEYBOARD)
    rep.setdefault("keyboard_on", {})[name] = r.m.read(KB_ON, 1)[0]


def measure(r: Rig, rep: dict, names) -> Pages:
    pg = Pages()
    for name in names:
        res: dict = {}
        shots: dict = {}
        res["key"] = cyc = cycle(r, name, pg, shots)
        n = len(cyc) + 1
        mine = name in OURS
        down_shots: list = []
        res["down"] = taps(r, name, pg, DOWN, n, shots=down_shots if mine else None)
        res["up"] = taps(r, name, pg, UP, n)
        up_shots: list = []
        res["up_from_end"] = taps(r, name, pg, UP, n, first=len(cyc) - 1, shots=up_shots if mine else None)
        if mine:                               # the glass a step leaves = the glass the page key left (settled)
            res["down_same_glass"] = [r.same(sh, shots.get(t)) for t, sh in zip(res["down"][1:], down_shots)]
            res["up_same_glass"] = [r.same(sh, shots.get(t)) for t, sh in zip(res["up_from_end"][1:], up_shots)]
            for what, ids, got in (("down", res["down"][1:], down_shots), ("up", res["up_from_end"][1:], up_shots)):
                for i, (t, sh) in enumerate(zip(ids, got)):
                    if not r.same(sh, shots.get(t)):    # the evidence: the step's glass and the key's
                        r.png(sh, f"{name}_{what}{i}_step")
                        r.png(shots.get(t, bytes(1024)), f"{name}_{what}{i}_key")
        enter(r, name)
        r.hold_for(DOWN, 121)
        res["down_held_1s"] = pg.id(r.title())
        res["func_down"] = taps(r, name, pg, DOWN, 2, hold_code=FUNC)
        res["trig_down"] = taps(r, name, pg, DOWN, 2, hold_code=TRIG1)
        res["kb_down"] = taps(r, name, pg, DOWN, 2, setup=lambda: keyboard(r, rep, name), teardown=lambda: r.tap(KEYBOARD))
        # (to the last page by DOWN once KEYBOARD / grid recording is on: their key, pressed on a page of ours, closes
        # it, as every key that is not FUNC, YES, an arrow, a trig or a push does: csrc/inserts/ins.c, scope.c)
        res["kb_up"] = taps(r, name, pg, UP, 2, setup=lambda: r.tap(KEYBOARD), teardown=lambda: r.tap(KEYBOARD),
                            downs=len(cyc) - 1)
        res["grid_down"] = taps(r, name, pg, DOWN, 2, setup=lambda: r.tap(REC), teardown=lambda: r.tap(REC))
        res["grid_up"] = taps(r, name, pg, UP, 2, setup=lambda: r.tap(REC), teardown=lambda: r.tap(REC),
                              downs=len(cyc) - 1)
        rep["pages"][name] = res
        print(f"  {name:5s} {json.dumps(res)}", flush=True)
    if r.lay and "amp_sub" in r.lay:           # a routes popup of ours (a knob pushed on AMP 1/2) takes the arrows
        enter(r, "AMP")
        before = r.settled()
        r.tap(ENC_A)
        opened = not r.same(r.settled(), before)
        r.tap(DOWN)
        r.tap(DOWN)
        sub = r.m.long(r.lay["amp_sub"])
        r.tap(ENC_A)                           # (the same knob pushed: closed, kept)
        r.settled()
        r.tap(DOWN)                            # the popup gone: the arrows page again
        rep["popup"] = {"opened": opened, "amp_sub_after_down": sub, "amp_sub_after_close_down": r.m.long(r.lay["amp_sub"])}
        print(f"  popup {json.dumps(rep['popup'])}", flush=True)
        sets(r, rep, pg)
    return pg


def sets(r: Rig, rep: dict, pg: Pages) -> None:
    """the two sets of pages never mixed (the User, 2026-11-20: "stays within the FUNC / no-FUNC pages: no mixing of
    groups"): on a page 2 (the FUNC tap) the arrows step among the page 2s only.
    The send pages with Delay XDLY and Reverb FDN8 (their TYPE knobs G turned left): titles tell the pages (page 1
    carries the 1/2 tag). The track FX pages with FUZZ in slot 1 and TAPE in slot 2 (ins_sel written: the page's
    structure only), then slot 2 OFF: the glass tells the insert's page 2 ("PG 2" at A)"""
    res: dict = {}

    def delay() -> None:                        # FUNC + FX, then UP to the first send page (stock stops there)
        enter(r, "SEND")
        r.tap(UP)
        r.tap(UP)
    def type_ours() -> None:                    # TYPE (G), right of STOCK: XDLY / FDN8 or LONG (a turn of a click or
        for _ in range(3):                      # two moves nothing here: the knob notches, csrc/knobs, measured)
            r.turn(6, 20)
        r.p.run_ticks(250)
    delay()
    type_ours()
    r.tap(DOWN)
    type_ours()
    res["types"] = [r.m.long(r.lay["dlt_seen"]), r.m.long(r.lay["rvt_seen"])]
    delay()                                     # (the titles as the pages are entered: the turns left TYPE's name)
    d1 = pg.id(r.title())
    r.tap(FUNC)
    d2 = pg.id(r.title())
    delay()
    r.tap(DOWN)
    r1 = pg.id(r.title())
    r.tap(FUNC)
    r2 = pg.id(r.title())
    res["send_pages"] = {"d1": d1, "d2": d2, "r1": r1, "r2": r2}
    delay()
    r.tap(FUNC)
    seq = [pg.id(r.title())]
    for code in (DOWN, DOWN, UP, UP):
        r.tap(code)
        seq.append(pg.id(r.title()))
    res["send_p2"] = seq
    r.tap(FUNC)                                 # back to page 1: stock's arrows
    seq = [pg.id(r.title())]
    for code in (DOWN, UP):
        r.tap(code)
        seq.append(pg.id(r.title()))
    res["send_p1"] = seq
    t = r.m.read(EM.UI_TRACK, 1)[0] & 15
    sel = r.lay["ins_sel"] + 2 * t

    def p2_glass(slot: int) -> bytes:
        enter(r, "FX")
        for _ in range(slot):
            r.tap(KEYS["FX"])
        r.tap(FUNC)
        return r.settled()
    r.m.write(sel, bytes([INS_FUZZ, INS_TAPE]))
    g1, g2 = p2_glass(1), p2_glass(2)
    p2_glass(1)
    r.png(g1, "ins_p2_slot1")
    r.png(g2, "ins_p2_slot2")
    seq = []
    for i, code in enumerate((DOWN, DOWN, UP, UP)):
        r.tap(code)
        g = r.settled()
        seq.append(1 if r.same(g, g1) else 2 if r.same(g, g2) else 0)
        if not seq[-1]:
            r.png(g, f"ins_p2_step{i}")
    res["ins_p2"] = seq
    r.m.write(sel, bytes([INS_FUZZ, 0]))
    g1 = p2_glass(1)
    r.tap(DOWN)
    g = r.settled()
    res["ins_p2_next_none"] = r.same(g, g1)
    if not r.same(g, g1):
        r.png(g1, "ins_none_before")
        r.png(g, "ins_none_after")
    r.m.write(sel, bytes([0, 0]))
    rep["sets"] = res
    print(f"  sets  {json.dumps(res)}", flush=True)


def sets_checks(rep: dict) -> None:
    res = rep.get("sets")
    if res is None:
        EM.check("the sets of pages measured (a build)", False)
        return
    p = res["send_pages"]
    EM.check("send pages: Delay XDLY and Reverb FDN8 / LONG set, four pages told apart", res["types"][0] == 0 and res["types"][1] in (0, 2)
             and len({p["d1"], p["d2"], p["r1"], p["r2"]}) == 4, f"{res['types']} {p}")
    EM.check("send page 2s: DOWN Delay 2 -> Reverb 2, stays (the Chorus has none); UP back to Delay 2, stays",
             res["send_p2"] == [p["d2"], p["r2"], p["r2"], p["d2"], p["d2"]], f"{res['send_p2']}")
    EM.check("send pages 1: stock's steps (Delay -> Reverb -> Delay), no page 2", res["send_p1"] == [p["d1"], p["r1"], p["d1"]],
             f"{res['send_p1']}")
    EM.check("inserts' page 2s (FUZZ, TAPE): DOWN INSERT 1 p2 -> INSERT 2 p2, stays; UP back, stays",
             res["ins_p2"] == [2, 2, 1, 1], f"{res['ins_p2']}")
    EM.check("inserts' page 2s: slot 2 with no page 2: DOWN stays on INSERT 1's page 2", res["ins_p2_next_none"])


def expect(rep: dict, name: str, n_pages: int) -> None:
    """stock's rule (measured on stock 1.12's own pages): DOWN steps to the last page and stays, UP back to page 1 and
    stays, on the press and its repeats; FUNC + DOWN no step; a trig held, KEYBOARD on, grid recording: as without"""
    res = rep["pages"][name]
    p = res["key"]
    n = len(p)
    at = lambda i: p[max(0, min(i, n - 1))]   # noqa: E731
    EM.check(f"{name}: {n_pages} pages on its key", n == n_pages, f"{p}")
    EM.check(f"{name}: DOWN steps page by page, stops on the last", res["down"] == [at(i) for i in range(n + 2)],
             f"{res['down']}")
    EM.check(f"{name}: UP on page 1 stays", res["up"] == [p[0]] * (n + 2), f"{res['up']}")
    EM.check(f"{name}: UP from the last page steps back, stops on page 1",
             res["up_from_end"] == [at(n - 1 - i) for i in range(n + 2)], f"{res['up_from_end']}")
    EM.check(f"{name}: DOWN held a second (its repeats) reaches the last page", res["down_held_1s"] == p[-1],
             f"{res['down_held_1s']}")
    EM.check(f"{name}: FUNC + DOWN steps nothing", res["func_down"][-1] == p[0], f"{res['func_down']}")
    EM.check(f"{name}: DOWN with a trig held steps", res["trig_down"] == [p[0], at(1), at(2), at(2)],
             f"{res['trig_down']}")
    EM.check(f"{name}: DOWN with KEYBOARD on steps", res["kb_down"][1:] == [at(1), at(2)], f"{res['kb_down']}")
    EM.check(f"{name}: UP with KEYBOARD on steps", res["kb_up"][1:] == [at(n - 2), at(n - 3)], f"{res['kb_up']}")
    EM.check(f"{name}: DOWN in grid recording steps", res["grid_down"] == [p[0], at(1), at(2)], f"{res['grid_down']}")
    EM.check(f"{name}: UP in grid recording steps", res["grid_up"] == [p[-1], at(n - 2), at(n - 3)],
             f"{res['grid_up']}")
    if "down_same_glass" in res:
        EM.check(f"{name}: each step's glass = the page key's (title, page, values)",
                 all(res["down_same_glass"]) and all(res["up_same_glass"]),
                 f"down {res['down_same_glass']} up {res['up_same_glass']}")


def checks(rep: dict) -> None:
    for name, n in PAGES.items():
        expect(rep, name, n)
    for name, on in rep.get("keyboard_on", {}).items():
        EM.check(f"{name}: KEYBOARD was on (its flag)", on != 0, f"{on}")
    pop = rep.get("popup")
    EM.check("AMP 1/2: the routes popup (a knob pushed) takes DOWN, the page stays",
             pop is not None and pop["opened"] and pop["amp_sub_after_down"] == 0 and pop["amp_sub_after_close_down"] == 1,
             f"{pop}")
    sets_checks(rep)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", required=True)
    p.add_argument("--build")
    p.add_argument("--stock", action="store_true", help="ignore --build: the snapshot as it is")
    p.add_argument("--json", help="the report (default WORK/updown.json)")
    p.add_argument("--work", help="a folder for the report and the screens")
    p.add_argument("--probe", action="store_true")
    a = p.parse_args()
    if a.stock:
        a.build = None
    if not a.json:
        if not a.work:
            p.error("--json or --work")
        pathlib.Path(a.work).mkdir(parents=True, exist_ok=True)
        a.json = str(pathlib.Path(a.work) / "updown.json")
    r = Rig(a)
    rep: dict = {"build": a.build or "snapshot as it is", "pages": {}}
    pg = measure(r, rep, ("TRIG", "SYN", "FLTR", "MOD", "AMP", "FX", "SEND"))
    rep["titles"] = pg.titles
    for i, t in enumerate(pg.titles):
        print(f"--- title {i}\n{t}", flush=True)
    if not a.probe:
        checks(rep)
        rep["fails"] = EM.FAILS
    pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    if a.probe:
        print("UPDOWN PROBE DONE")
        return 0
    print("UPDOWN OK" if not EM.FAILS else f"UPDOWN FAILED: {len(EM.FAILS)}")
    return 0 if not EM.FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
