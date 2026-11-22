"""The routes popup says PER NOTE on a control read only at the note's start (2026-11-20, the User: the knobs that stay
per note "say 'per note' in the routes popup"; csrc/matrix/routes_pop.c mxp_note, pages.py MNM_PER_NOTE). emu_matrix.py's
scenario "pernote".

On TB-303's SYN page 1 (md_page.c, our Monomachine page code): the page reports exactly two such controls (ACC and SLID),
by the machine's own table (its engine's: the Monomachine's and DRUM's engines share slots); a plain push on each opens
the popup with PER NOTE right of its header (the flag and the pixels there); on CUT (not one of them) the popup has
nothing there. On DRUM (KICK, SYN page 1): TYPE is one, TUNE is not. On ONESHOT's page 1: SAMP is one.
"""

from __future__ import annotations

import pathlib
import struct

SYN, FLTR = (0, 1), (0, 2)
HEADER_X = 86                           # routes_pop.c: PER NOTE's x
CASES = (("TB303", 54, 2), ("DRUM", 56, None), ("ONESHOT", 8, None))   # (name, type, controls reported, None: any)


def header_lit(MO, m):
    """the lit pixels right of the header's name: columns HEADER_X..127, the header's rows (57..63 from the bottom)"""
    from emu import panel as P
    lit = P.lit(MO.glass(m))
    return sum(1 for x in range(HEADER_X, 128) for y in range(0, 7) if (x, y) in lit)


def scenario_pernote(MX, a, report, sym):
    from emulib.panel import ENCODER_PUSH, Panel
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    MO, check = MX.MO, MX.check
    m = MX.setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_pernote_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    if "mxp_note" not in sym:
        check("pernote: the build reports per-note controls (mxp_note)", False)
        return
    knobs, notes = [], []

    def on_knob(uc, ad, sz, us):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        knobs.append(struct.unpack(">7i", m.read(sp + 4, 28))[1:])         # x, y, w, id, lo, hi

    def on_note(uc, ad, sz, us):
        notes.append(struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0])

    def on_begin(uc, ad, sz, us):
        knobs.clear()
        notes.clear()
    m.uc.hook_add(UC_HOOK_CODE, on_knob, begin=sym["mv_knob"], end=sym["mv_knob"])
    m.uc.hook_add(UC_HOOK_CODE, on_note, begin=sym["mxp_note"], end=sym["mxp_note"])
    m.uc.hook_add(UC_HOOK_CODE, on_begin, begin=sym["mv_begin"], end=sym["mv_begin"])
    m.flush()
    panel.tick_clock(MO.FRAMES)
    vis = lambda: MO.guest(m, sym["mxp_visible"]) & 0xFFFFFFFF                     # noqa: E731
    rep = {}

    def push(k):
        """a plain push of K -> (popup up, its PER NOTE flag, the lit pixels where PER NOTE goes)"""
        p = ENCODER_PUSH[k]
        panel.press_for(p, 8)
        panel.release_for(p, 30)
        panel.settle(20_000_000)
        out = (vis(), m.long(sym["mxp_per_note"]), header_lit(MO, m))
        return out

    def shut(k):
        if vis():
            panel.press_for(ENCODER_PUSH[k], 4)
            panel.release_for(ENCODER_PUSH[k], 20)
        panel.skip_frames(1600)
        panel.run_ticks(10)

    for name, mtype, count in CASES:
        if not MO.ours_machine(m, panel, mtype):
            check(f"pernote {name}: track 1 set to type {mtype}", False)
            continue
        panel.tap(FLTR)
        panel.settle(30_000_000)
        panel.tap(SYN)
        panel.settle(40_000_000)
        noted = sorted(set(notes))
        places = {}
        for x, y, _w, rid, _lo, _hi in knobs:
            places.setdefault((x - 1 - 24 + 13) // 26 + (4 if y - 5 < 13 else 0), rid)
        check(f"pernote {name}: the page reports its per-note controls" + (f" ({count})" if count else ""),
              bool(noted) and (count is None or len(noted) == count), f"{noted} of {sorted(places.items())}")
        per = [k for k, rid in sorted(places.items()) if rid in noted]
        live = [k for k, rid in sorted(places.items()) if rid not in noted and 25 <= MO.record(m, rid)[1] <= 100]
        res = {"noted": noted, "places": places}
        for tag, ks, want in (("per note", per[:2], 1), ("live", live[:1], 0)):
            for k in ks:
                up, flag, lit = push(k)
                shot = panel.screen(f"pernote-{name}-{k}")
                if not up:
                    check(f"pernote {name}: knob {k} (record {places[k]}): the popup opens on a plain push", False,
                          f"why {m.long(sym['mxp_why'])}")
                    continue
                check(f"pernote {name}: knob {k} (record {places[k]}, {tag}): PER NOTE {'shown' if want else 'not shown'}",
                      flag == want and (lit > 0) == bool(want), f"flag {flag}, {lit} pixels lit right of the header")
                res[k] = {"flag": flag, "lit": lit, "screen": shot}
                shut(k)
        rep[name] = res
    report["pernote"] = rep
