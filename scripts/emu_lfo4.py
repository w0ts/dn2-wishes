"""lfo4 on OS 1.12 with our series (DN2_LFO4; docs/lfo-112-port.md) in the ColdFire emulator.

    emu_lfo4.py --build BUILD.syx [--snapshot SNAP] [--frames N] [--scenario modulating,cascade,into4,lists,stored]
                [--json OUT]

BUILD carries waverider (generated with DN2_LFO4), lfowaves and lfo4. The snapshot is one booted on a build without
lfo4, so lfo4's chunk is installed and its init entered by hand, as the platform's loader does at power-on.

modulating  LFO4's eight values set in lfo4's own table (ext_set) for every track's live sound: SPD fast, DEST FREQ
            (mirror slot 67), DEP full; voice row 0's LFO1..3 at depth 0. Through the frame's own path (the smoother,
            our mod_eval, stock's evaluator with lfo4's fourth LFO): FREQ moves; with LFO4's DEP at zero (0x4000: DEP is bipolar) it does not.
cascade     LFO4 aimed at LFO1's SPD, LFO1 aimed at FREQ: LFO1's output differs from the same with LFO4's depth zero
            (the User's "Include", docs/lfo-112-port.md 4.4: LFO4 into LFO1..3).
into4       LFO1 aimed at LFO4's SPD (slot 101), LFO4 aimed at FREQ: LFO4's output differs from LFO1 at depth zero
            (LFO1..3 into LFO4: the raised bounds, the cascade's per-voice LFO4 cells, lfo4's cascade slot).
lists       on WaveTone, LFO1's, LFO2's and LFO3's destination lists offer LFO4's seven controls (SPD MULT FADE WAVE SPH
            MODE DEP: lfo4's records 321..329), never its DEST (324), nor SLEW (its slot is SPH's).
stored      stock's own SAVE of a sound with LFO4 set and stock's own LOAD of it into another track, then the UI
            pass: LFO4's values arrive through the wishes record; a sound saved at LFO4's defaults loads them so.
line        (2026-11-20; --snapshot booted on BUILD) LFO4's page draws the moving line: none at rest, LFO1 aimed at LFO4's
            SPD moves SPD's line alone, gone once LFO1's depth is zero
page        (stage 2f; --snapshot booted on BUILD) [MOD] walks four pages, LFO4's the fourth; its knobs A..H each
            move their own LFO4 value in lfo4's table (pushed turns: the emulator's way to move a value), LFO1..3's
            pages leave it alone; a value set there is drawn.
control     (--build without lfo4: the same setup leaves FREQ still)

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_modulation as M                                      # noqa: E402

FREQ = 67                          # a voice row's FREQ slot (emu_modulation's line scenario)
LFO4 = ("SPD", "MULT", "FADE", "DEST", "WAVE", "SPH", "MODE", "DEP")   # csrc/lfo4/ext.h's order
SOUND = 1163
ZERO_DEPTH = 0x4000                # an LFO's DEP is bipolar: 0x4000 is no depth (0 is full negative)

checks: list[tuple[str, bool, str]] = []


def check(what, ok, detail=""):
    checks.append((what, bool(ok), detail))
    print(("  ok    " if ok else "  FAIL  ") + what + (f" -- {detail}" if detail else ""), flush=True)


def lfo4_machine(build, snapshot):
    """emu_modulation's machine (the build's bytes, its chunks, the UI's return moved), then lfo4's init"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    from dnfw.mods import lfo4, platform
    m = M.machine(build, snapshot)
    sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
    _, chunks = platform.split(sec3)
    inits = [platform.area.CodeChunk.unpack(d).init for c, d in chunks
             if c == platform.area.CODE and platform.area.CodeChunk.unpack(d).load == 0x46800000]
    if not inits:
        raise SystemExit("no lfo4 chunk at 0x46800000 in this build")
    if inits[0]:
        m.call(inits[0])
    return m, lfo4.SPEC["symbols"]


def run(build, snapshot, sym, frames, lfo4_vals, lfo1=None):
    """-> FREQ per frame, voice row 0, with LFO4's values set for every track's sound (and LFO1 as given);
    lfo4_vals None: a build without lfo4 (the control)"""
    if lfo4_vals is None:
        m = M.machine(build, snapshot)
    else:
        m, ext = lfo4_machine(build, snapshot)
        kit = m.long(M.KIT)
        for t in range(16):
            for k, v in enumerate(lfo4_vals):
                m.call(ext["ext_set"], kit + 52 + SOUND * t, k, v)
    frac = m.alloc(len(M.SET_FRAC))
    m.write(frac, M.SET_FRAC)
    m.flush()
    m.call(frac)
    v, s = 0, M.slot
    setting = {s(1, "DEP"): ZERO_DEPTH, s(2, "DEP"): ZERO_DEPTH, s(3, "DEP"): ZERO_DEPTH, FREQ: 0x4000}
    if lfo1:
        setting.update(lfo1)
    for sl, val in setting.items():
        M.w16(m, M.SRC + 2 * M.idx(v, sl), val)
        m.write(M.STATE + 4 * M.idx(v, sl), struct.pack(">I", val << 16))
        M.w16(m, M.OUT + 2 * M.idx(v, sl), val)
    rate = m.long(M.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out = []
    for _ in range(frames):
        m.call(M.SMOOTHER, M.SRC)
        m.call(sym["mod_eval"], M.OUT, rate, 1, 1, o1, o2, 0, limit=2_000_000)
        out.append(M.u16(m, M.OUT + 2 * M.idx(v, FREQ)))
    return out


def vals(**kw):
    d = {"SPD": 0x7000, "MULT": 6 << 8, "FADE": 0x4000, "DEST": FREQ << 8, "WAVE": 0, "SPH": 0x4000, "MODE": 0,
         "DEP": 0x7F00}
    d.update(kw)
    return [d[n] for n in LFO4]


def scenario_modulating(a, sym, rep):
    on = run(a.build, a.snapshot, sym, a.frames, vals())
    off = run(a.build, a.snapshot, sym, a.frames, vals(DEP=ZERO_DEPTH))
    check("LFO4 at full depth on FREQ moves it", max(on) - min(on) > 0x800, f"{min(on):#06x}..{max(on):#06x}")
    check("... and at depth 0 it does not", max(off) == min(off), f"{min(off):#06x}..{max(off):#06x}")
    check("every value in 0..0x7f00", all(x <= 0x7F00 for x in on))
    rep["modulating"] = {"on": [f"{min(on):#06x}", f"{max(on):#06x}"], "off": [f"{min(off):#06x}", f"{max(off):#06x}"]}


def scenario_cascade(a, sym, rep):
    s = M.slot
    lfo1 = {s(1, "SPD"): 0x5000, s(1, "MULT"): 4 << 8, s(1, "FADE"): 0x4000, s(1, "DEST"): FREQ << 8,
            s(1, "WAVE"): 0, s(1, "SPH"): 0, s(1, "MODE"): 0, s(1, "DEP"): 0x7F00}
    on = run(a.build, a.snapshot, sym, a.frames, vals(DEST=s(1, "SPD") << 8), lfo1)
    off = run(a.build, a.snapshot, sym, a.frames, vals(DEST=s(1, "SPD") << 8, DEP=ZERO_DEPTH), lfo1)
    differ = sum(x != y for x, y in zip(on, off))
    check("LFO4 into LFO1's SPD: LFO1's output on FREQ differs from LFO4 at depth 0", differ > a.frames // 4,
          f"frames differing {differ} of {a.frames}")
    rep["cascade"] = {"differing_frames": differ}


def scenario_into4(a, sym, rep):
    """LFO1 aimed at LFO4's SPD (slot 101): what LFO4 adds to FREQ changes, against LFO1 at depth zero"""
    s = M.slot
    lfo1 = {s(1, "SPD"): 0x5000, s(1, "MULT"): 4 << 8, s(1, "FADE"): 0x4000, s(1, "DEST"): 101 << 8,
            s(1, "WAVE"): 0, s(1, "SPH"): 0, s(1, "MODE"): 0, s(1, "DEP"): 0x7F00}
    on = run(a.build, a.snapshot, sym, a.frames, vals(SPD=0x5800), lfo1)
    lfo1[s(1, "DEP")] = ZERO_DEPTH
    off = run(a.build, a.snapshot, sym, a.frames, vals(SPD=0x5800), lfo1)
    differ = sum(x != y for x, y in zip(on, off))
    check("LFO1 into LFO4's SPD: LFO4's output on FREQ differs from LFO1 at depth zero (LFO1..3 into LFO4)",
          differ > a.frames // 4, f"frames differing {differ} of {a.frames}")
    check("... every value in 0..0x7f00", all(x <= 0x7F00 for x in on))
    rep["into4"] = {"differing_frames": differ}


# lfo4's records (dnfw.patch.lfo4records: ids 321..330, rows 320..329, in LFO3's order)
LFO4_IDS = dict(zip(("SPD", "MULT", "FADE", "DEST", "WAVE", "SLEW", "SPH", "MODE", "DEP", "MULT2"), range(321, 331)))
# offered as destinations: as LFO1..3's own controls are (cascade.c lfo_of): never DEST, nor SLEW (its slot is SPH's),
# nor the second MULT (MULT's slot)
LFO4_OFFERED = {LFO4_IDS[n] for n in ("SPD", "MULT", "FADE", "WAVE", "SPH", "MODE", "DEP")}


def scenario_lists(a, sym, rep):
    """the destination lists on WaveTone: LFO1's offers LFO4's controls (lfo4's records), never its DEST"""
    lists = M.lists_of(a.build, a.snapshot)["WAVETONE"]
    for lfo in ("LFO1", "LFO2", "LFO3"):
        got = set(lists[lfo]) & set(LFO4_IDS.values())
        check(f"{lfo}'s list offers LFO4's seven controls, not its DEST", got == LFO4_OFFERED,
              f"listed {sorted(got)}, want {sorted(LFO4_OFFERED)}")
    rep["lists"] = {lfo: sorted(set(lists[lfo]) & set(LFO4_IDS.values())) for lfo in ("LFO1", "LFO2", "LFO3")}


STOCK_LOAD, STOCK_SAVE, STORED = 0x400DD34E, 0x400DD80A, 359   # stock's stored-sound LOAD and SAVE (emu_wishes.py)


def scenario_stored(a, sym, rep):
    """stock's own SAVE of track 2's sound with LFO4 set, stock's own LOAD of it into track 3's, the UI pass's
    wish_lfo4_poll: track 3's LFO4 is track 2's; LOAD of a sound saved with LFO4 at its defaults: track 3's row
    dropped (its defaults). The User's "Into the wishes record" (csrc/wishes/lfo4.c)."""
    from dnfw.waverider import pages
    from unicorn import UC_PROT_ALL, UcError
    code = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text()).get("c_text_symbols", {})
    m, ext = lfo4_machine(a.build, a.snapshot)
    for page in range(pages.WISH_RAM & ~0xFFFFF, pages.WISH_RAM + pages.WISH_BYTES, 0x100000):
        try:
            m.uc.mem_map(page, 0x100000, UC_PROT_ALL)
        except UcError:
            pass
    kit = m.long(M.KIT)
    s2, s3, s4 = (kit + 52 + SOUND * t for t in (1, 2, 3))
    st = m.alloc(2 * 0x200)
    m.write(st, bytes(2 * 0x200))
    want = vals(SPD=0x5800, DEST=FREQ << 8, WAVE=2 << 8, DEP=0x6000)

    def row(key):
        ptr = m.call(ext["ext_find"], key)
        return list(struct.unpack(">8H", m.read(ptr, 16))) if ptr else None
    for k, v in enumerate(want):
        m.call(ext["ext_set"], s2, k, v)
    m.call(ext["ext_drop"], s3)
    m.call(ext["ext_drop"], s4)
    m.call(STOCK_SAVE, st, s2, 0)
    stored = m.read(st, STORED)
    check("stock's SAVE of a sound with LFO4 set: its lane is the wishes link", stored[36] == 0x57,
          f"byte 36 {stored[36]:#04x}")
    m.call(STOCK_LOAD, s3, st)
    before = row(s3)
    m.call(code["wish_lfo4_poll"])
    check("stock's LOAD into track 3, then the UI pass: track 3's LFO4 is track 2's", row(s3) == want,
          f"before the pass {before}, after {row(s3)}, want {want}")
    m.call(STOCK_SAVE, st + 0x200, s4, 0)            # track 4: LFO4 at its defaults, so no link
    m.call(STOCK_LOAD, s3, st + 0x200)
    m.call(code["wish_lfo4_poll"])
    check("LOAD of a sound saved with LFO4 at its defaults: track 3's LFO4 back at its defaults (no row)",
          row(s3) is None, f"{row(s3)}")
    rep["stored"] = {"want": want}


MOD_KEY, NO_KEY = (0, 5), (1, 3)   # emulib.panel MOD, NO


def booted_on(build, snapshot):
    """refuse a snapshot whose MAIN OS is not BUILD's: the page scenario needs one booted on it, where lfo4 built its
    page into stock's UI at power-on. (A snapshot holds none of our areas at 0x467..-0x47..: they are installed from
    the build and lfo4's init entered by hand, as for every scenario here.)"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
    if open(snapshot + ".section_3_MAIN_OS.bin", "rb").read() != sec3:
        raise SystemExit(f"{snapshot} was not booted on {build}: the page scenario needs the build's own snapshot")


def scenario_page(a, sym, rep):
    """(stage 2f, a snapshot booted on BUILD) [MOD] walks four pages, LFO4's the fourth; each of its knobs A..H
    moves its own LFO4 value of the track's sound in lfo4's table and only that one; LFO1..3's pages leave
    lfo4's table alone; a value set in lfo4's table shows on the page"""
    from emulib.panel import Panel
    booted_on(a.build, a.snapshot)
    m, ext = lfo4_machine(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/lfo4").with_suffix("")) + "_page_png")
    panel.settle(20_000_000)
    snd = m.long(M.KIT) + 52 + SOUND * m.read(M.UI_TRACK, 1)[0]
    defaults = list(struct.unpack(">8H", m.read(ext["ext_default"], 16)))

    def row():
        """LFO4's values for the sound in lfo4's table, its defaults when it has no row"""
        ptr = M.guest(m, ext["ext_find"], snd)
        return list(struct.unpack(">8H", m.read(ptr, 16))) if ptr else list(defaults)

    def page(name):
        """the page under its header (the header animates: the page's name, then the sound's)"""
        panel.screen(name)
        return frozenset((x, y) for x, y in panel.panel.lit(bytes(panel.capture.frames[-1])) if y >= 12)

    M.guest(m, ext["ext_drop"], snd)
    shots = []
    for k in range(5):                                  # the pages, before any knob changes them
        panel.tap(MOD_KEY)
        panel.settle(20_000_000)
        shots.append(page(f"mod{k + 1}"))
    check("[MOD] shows four different pages", len(set(shots[:4])) == 4, f"{len(set(shots[:4]))} different of 4")
    check("... and a fifth tap comes back to the first (four pages, not three)", shots[4] == shots[0])
    stock_moved = []
    for k in range(3):                                  # on LFO1..3's pages a knob leaves lfo4's table alone
        v0 = m.read(snd + 20, 220)                      # (and moves the sound's own value: the harness's control)
        panel.push_and_turn(0, 3)
        panel.settle(10_000_000)
        v1 = m.read(snd + 20, 220)
        stock_moved.append([i // 2 for i in range(0, 220, 2) if v0[i:i + 2] != v1[i:i + 2]])
        check(f"[MOD] page {k + 1}: knob A leaves lfo4's table alone", row() == defaults,
              f"{row()}; the sound's slots moved {stock_moved[-1]}")
        panel.tap(MOD_KEY)
        panel.settle(20_000_000)
    moved = {}                                          # on the fourth, LFO4's
    for enc in (0, 1, 2, 4, 5, 6, 7):
        name = LFO4[enc]
        before = row()
        panel.push_and_turn(enc, 3)
        panel.settle(10_000_000)
        after = row()
        moved[name] = [n for n, x, y in zip(LFO4, before, after) if x != y]
        check(f"LFO4's page: knob {'ABCDEFGH'[enc]} moves LFO4's {name} only", moved[name] == [name],
              f"moved {moved[name]}, {before[enc]:#06x} -> {after[enc]:#06x}")
    shot = page("lfo4_turned")
    dep = 0x6000 if row()[LFO4.index("DEP")] != 0x6000 else 0x2000
    M.guest(m, ext["ext_set"], snd, LFO4.index("DEP"), dep)
    m.write(sym["smp_overlay_dirty"], struct.pack(">i", 1))
    panel.settle(20_000_000)
    check(f"a DEP set in lfo4's table ({dep:#06x}) shows on LFO4's page", page("lfo4_dep") != shot)
    # DEST last. 2026-11-18 (the User: "editing destination in modulation page is cpu. and we need to redo this
    # popup"): D's push on an LFO page opens the DEST popup (csrc/matrix/dest_pop.c) in place of stock's DEST list,
    # which is never made (its view 0x4010660c; stock makes it at the press). LFO4's popup holds its one route, its
    # DEST and DEP in lfo4's table: YES on an unused row with DEST in use is refused (LFO4: 1 ROUTE); a long NO on its
    # route deletes it (DEST 0, DEP its default); YES on a row then makes it (DEST that row, DEP +32), only DEST and
    # DEP moved; NO on it says CAN'T MUTE (nothing moves); D pushed alone closes it. (The keys in full: the gate's
    # destpop step, scripts/emu_destpop.py.)
    from emulib.panel import DOWN, ENCODER_PUSH, YES
    from unicorn import UC_HOOK_CODE
    made = []
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: made.append(1), begin=0x4010660C, end=0x4010660C)
    m.flush()

    def popup():
        up, lfo = struct.unpack(">ii", m.read(sym["ldp_p"], 8))
        return up, lfo

    def lit_row():
        lit, n = struct.unpack(">I4xI", m.read(sym["ldp_p"] + 12, 12))
        return struct.unpack(">H", m.read(sym["ldp_rows"] + 2 * lit, 2))[0], n

    def frames_on(n):
        m.write(M.FRAMES, struct.pack(">I", (m.long(M.FRAMES) + n) & 0xFFFFFFFF))
        m.flush()
    panel.tap(ENCODER_PUSH[3])
    panel.settle(20_000_000)
    check("LFO4's page: D's push opens the DEST popup (LFO4's), stock's DEST list never made",
          popup() == (1, 3) and not made, f"popup {popup()}, stock's list made {len(made)}x")
    before = row()
    if before[3] >> 8:                                  # LFO4's route: a long NO deletes it
        panel.hold(NO_KEY, 2_000_000)
        frames_on(1000)
        panel.settle(15_000_000)
        panel.let_go(NO_KEY, 5_000_000)
    deleted = row()
    panel.tap(DOWN)
    target, _ = lit_row()
    panel.tap(YES)
    panel.settle(10_000_000)
    after = row()
    moved["DEST"] = [n for n, x, y in zip(LFO4, deleted, after) if x != y]
    check("LFO4's popup: its route deleted (a long NO), YES on a row makes it there: DEST and DEP (+32) only",
          deleted[3] == 0 and after[3] >> 8 == M.record(m, target)[1] and after[LFO4.index("DEP")] == 0x6000
          and set(moved["DEST"]) <= {"DEST", "DEP"}, f"{before[3]:#06x} -> {deleted[3]:#06x} -> {after[3]:#06x}, "
          f"moved {moved['DEST']}, row {target}")
    kept = row()
    panel.tap(DOWN)
    panel.tap(YES)
    panel.settle(10_000_000)
    check("LFO4's popup: a second route is refused (its one DEST kept)", row() == kept, f"{kept[3]:#06x} -> {row()[3]:#06x}")
    panel.tap(ENCODER_PUSH[3])
    panel.settle(10_000_000)
    check("LFO4's popup: D pushed alone closes it, kept", popup()[0] == 0 and row() == kept and not made,
          f"popup {popup()}, {row()[3]:#06x}")
    panel.screen("lfo4_dest_closed")
    page("lfo4_closed")
    rep["page"] = {"moved": moved, "stock_moved": stock_moved, "row": [f"{x:#06x}" for x in row()]}


def scenario_control(a, sym, rep):
    """(a build without lfo4, --build: the same setup moves nothing)"""
    out = run(a.build, a.snapshot, sym, a.frames, None)
    check("without lfo4, voice row 0's LFOs at depth 0: FREQ still", max(out) == min(out), f"{min(out):#06x}..{max(out):#06x}")


def scenario_line(a, sym, rep):
    """(2026-11-20, the User: LFO4's page gets lines too; csrc/modulation/moving.c, a snapshot booted on BUILD) LFO4's
    page draws its seven controls through mv_knob (never DEST), no line at rest; voice 1's LFO1 aimed at LFO4's SPD
    (slot 101) at full depth, the frame's path run (stock's smoother, the evaluator with the cascade): SPD's line moves
    by itself, the others none; LFO1's depth back to zero: no line past the linger"""
    from emulib.panel import Panel
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    booted_on(a.build, a.snapshot)
    m, ext = lfo4_machine(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/lfo4").with_suffix("")) + "_line_png")
    knobs = []

    def on_knob(uc, ad, sz, us):
        knobs.append(struct.unpack(">7i", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 28))[1:])
    m.uc.hook_add(UC_HOOK_CODE, on_knob, begin=sym["mv_knob"], end=sym["mv_knob"])
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: knobs.clear(), begin=sym["mv_begin"], end=sym["mv_begin"])
    m.flush()
    panel.settle(20_000_000)
    t = m.read(M.UI_TRACK, 1)[0]
    for _ in range(4):                                  # [MOD] four times: LFO4's page
        panel.tap(MOD_KEY)
        panel.settle(30_000_000)
    ids = sorted({k[3] for k in knobs})
    check("LFO4's page: its seven controls drawn through mv_knob", set(LFO4_OFFERED) <= set(ids), f"ids {ids}")
    kn = {k[3]: k for k in knobs}
    spd = kn.get(LFO4_IDS["SPD"])
    if not spd:
        return
    m.write(sym["sl_lastv"] + t, b"\x00")              # the UI track last played voice 1, which plays it
    m.write(M.OWNER, struct.pack(">I", t))
    M.rest_on_sound(m, 0, t)
    s = M.slot
    for k_, val in {s(1, "SPD"): 0x5800, s(1, "MULT"): 4 << 8, s(1, "FADE"): 0x4000, s(1, "DEST"): 101 << 8,
                    s(1, "WAVE"): 0, s(1, "SPH"): 0, s(1, "MODE"): 0, s(1, "DEP"): 0x4000,
                    s(2, "DEP"): 0x4000, s(3, "DEP"): 0x4000}.items():
        M.w16(m, M.SRC + 2 * M.idx(0, k_), val)
        m.write(M.STATE + 4 * M.idx(0, k_), struct.pack(">I", val << 16))
    frac = m.alloc(len(M.SET_FRAC))
    m.write(frac, M.SET_FRAC)
    m.flush()
    M.guest(m, frac)
    rate, o1, o2 = m.long(M.RATE), m.alloc(256), m.alloc(256)

    def run(frames):
        for _ in range(frames):
            M.guest(m, M.SMOOTHER, M.SRC)
            M.guest(m, sym["mod_eval"], M.OUT, rate, 1, 1, o1, o2, 0)
        m.write(M.FRAMES, struct.pack(">I", (m.long(M.FRAMES) + frames) & 0xFFFFFFFF))
        panel.settle(30_000_000)

    def lit(k):
        from emu import panel as P
        x, y, w = k[0], k[1], k[2]
        on = P.lit(M.glass(m))
        return [j for j in range(w) if (x + j, 63 - y) in on]
    run(10)
    run(700)
    rest = {i: lit(k) for i, k in kn.items() if lit(k)}
    check("LFO4's page at rest (LFO1 at depth 0): no line", not rest, f"{rest}")

    def depth(d):
        M.w16(m, M.SRC + 2 * M.idx(0, s(1, "DEP")), d)
        m.write(M.STATE + 4 * M.idx(0, s(1, "DEP")), struct.pack(">I", d << 16))
    depth(0x7F00)
    seen, others = [], set()
    for k in range(6):
        run(150)
        px = lit(spd)
        seen.append((min(px), max(px)) if px else None)
        others |= {i for i, kk in kn.items() if i != LFO4_IDS["SPD"] and lit(kk)}
        panel.screen(f"lfo4-line{k}")
    check("LFO1 -> LFO4's SPD at full depth: SPD's line moves by itself", len({e for e in seen if e}) >= 3, f"{seen}")
    check("... and no other LFO4 control shows a line", not others, f"{sorted(others)}")
    depth(0x4000)
    run(150)
    run(700)
    px = lit(spd)
    check("LFO1's depth back to zero: no line on SPD past the linger", px == [], f"{px}")
    rep["line"] = {"ids": ids, "spd_ends": seen}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", default=M.SNAP)
    p.add_argument("--frames", type=int, default=300)
    p.add_argument("--scenario", default="modulating,cascade,into4,lists,stored")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    rep: dict = {}
    for sc in a.scenario.split(","):
        {"modulating": scenario_modulating, "cascade": scenario_cascade, "control": scenario_control, "into4": scenario_into4,
         "lists": scenario_lists, "stored": scenario_stored, "page": scenario_page,
         "line": scenario_line}[sc](a, sym, rep)
    rep["checks"] = [{"what": w, "ok": o, "detail": d} for w, o, d in checks]
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    bad = [w for w, o, _ in checks if not o]
    print("PASS" if not bad else f"FAIL: {bad[0]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
