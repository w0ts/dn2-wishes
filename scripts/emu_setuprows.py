"""The routes popup's MOD SETUP rows made editable (csrc/matrix/setup.c, routes_pop.c; docs/matrix.md "MOD SETUP's rows",
the User 2026-11-21: "like other rows!") on the ColdFire emulator, OS 1.12.

    emu_setuprows.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--scenario ...] [--json OUT]
                     [--base BASE.syx --base-snapshot <its snapshot>]

edit    the popup on track 1's FREQ (FLTR), through the keys: a turn on VEL's row writes stock's depth word through
        stock's own object (its setEntry / setDepth run: the sound and every voice of the track hold it), the entry in
        the source's first free place; YES on MW's row adds one at +32 there; FULL at 4 (PB's four places in use: YES
        and a turn add nothing); a long NO deletes VEL's (its place freed); NO mutes MW's (the sound unchanged, the
        voices' copies at depth 0, the record's mark), YES unmutes it; two AT entries into FREQ merged by a turn (one
        entry, the depths summed and turned); FUNC + NO deletes ours and MOD SETUP's into FREQ.
offers  NOT IN SETUP: for every slot, the popup's answer (mxs_offers) is stock's MOD SETUP list's (the builder called by
        hand, want 0x200); on ENV2's page (its ATK, slot 0xE0) a turn and YES on VEL's row add nothing.
frame   the frame's parameter path (the smoother, MOD SETUP, the evaluator call) on 16 voices of track 1: stock's copy
        into the voices with no mark is the sound's bytes; a muted entry is heard exactly as that entry at depth 0, the
        sound unchanged; unmuted, as before; an entry changed from outside plays, put back it is muted again; the note's
        copy (0x4002549c) is masked too; a sound not the kit's never.
exact   (--base) with no mark, the same frames as the base build, bit for bit; the copies' and the frame's
        instructions on both (the cost).
look    the popup's screens (routes, MOD SETUP rows with an entry and a muted one, the dimmed levels on the rows with no
        route) -> *_png/look_*.png

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_matrix as MX                                             # noqa: E402 -- its machine, popup rig, frames
import emu_modulation as MO                                         # noqa: E402

SETUP_TAG = 0x0015                      # WT_MX_SETUP (csrc/matrix/setup.c)
LIST = (0, 2, 1, 4, 3, 5)               # row VEL MW PB AT BC KEY -> the sound's list (setup.c mxs_list)
VEL, MW, PB, AT, BC, KEY = range(6)
ROW0 = 5                                # the popup's first MOD SETUP row (routes_pop.c OWN_ROWS)
FREQ = 67
VREC = 0x8000487C                       # the voices' MOD SETUP copies: + 153 v (stock's 0x4002549c, 0x4002591e)
MIRROR_COPY, NOTE_COPY = 0x4002591E, 0x4002549C
MODS = 0x400DB390
# stock's MOD SETUP objects' setEntry and setDepth (VEL's ModConfig, the five others' ValueWithMirror)
SET_ENTRY, SET_DEPTH = (0x40056D48, 0x400F55D2), (0x40056DF0, 0x400F568A)
VALUES = (0x8000DD40, 0x8000DE40, 0x8000DE20, 0x8000DE00, 0x8000DDE0)   # list l's value (mods_fast), KEY at 0x8000dda0
FAILS = MX.FAILS
check = MX.check


def entries(m, snd, j):
    """the sound's four {depth, slot} of row J"""
    return [struct.unpack(">hh", m.read(snd + 230 + 16 * LIST[j] + 4 * p, 4)) for p in range(4)]


def put_entries(m, snd, j, es):
    m.write(snd + 230 + 16 * LIST[j], b"".join(struct.pack(">hh", d, s) for d, s in es))
    m.flush()


def voice_entries(m, v, j):
    return [struct.unpack(">hh", m.read(VREC + 153 * v + 8 + 16 * LIST[j] + 4 * p, 4)) for p in range(4)]


class Calls:
    """calls of stock's MOD SETUP setters (code hooks at their entries)"""

    def __init__(self, m):
        from unicorn import UC_HOOK_CODE
        self.n = {"entry": 0, "depth": 0}
        for name, vas in (("entry", SET_ENTRY), ("depth", SET_DEPTH)):
            for va in vas:
                m.uc.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, us, k=name: self.n.__setitem__(k, self.n[k] + 1),
                              begin=va, end=va)
        m.flush()

    def take(self):
        n = dict(self.n)
        self.n = {"entry": 0, "depth": 0}
        return n


def pop_rig(a, sym, what):
    """emu_matrix's popup bench on FREQ, every MOD SETUP list cleared of FREQ; voices 1-4 on track 1, voice 1 its last;
    -> the rig with to_row(r), marks(), mute keys"""
    from emulib.panel import DOWN, UP
    r = MX.popup_rig(a, sym, what)
    if r is None:
        return None
    m = r.m
    for v in range(16):
        m.write(MO.OWNER + 4 * v, struct.pack(">I", 0 if v < 4 else 1))
    m.write(sym["sl_lastv"], b"\x00")
    m.flush()
    r.sym = sym
    buf = m.alloc(128)

    def to_row(row):
        order = list(m.read(sym["mxp_order"], 11))
        want = order.index(row)
        for _ in range(30):
            lit = m.long(sym["mxp_lit"])
            if lit == want:
                return True
            r.panel.tap(DOWN if lit < want else UP, after=3_000_000)
        return m.long(sym["mxp_lit"]) == want

    def marks():
        n = MO.guest(m, sym["wish_get"], r.snd, SETUP_TAG, buf, 128) & 0xFFFFFFFF
        return bytes(m.read(buf, n)) if n < 128 else b""
    r.to_row, r.marks = to_row, marks
    r.calls = Calls(m)
    return r


def scenario_edit(a, report, sym):
    from emulib.panel import NO, YES
    r = pop_rig(a, sym, "edit")
    if r is None:
        return
    m, snd = r.m, r.snd
    rep = {}
    put_entries(m, snd, VEL, [(0x0100, 40), (0, 0), (0, 0), (0, 0)])        # VEL: place 1 the first free one
    put_entries(m, snd, MW, [(0, 0)] * 4)
    put_entries(m, snd, PB, [(0x0200, 30), (0x0300, 31), (0x0400, 32), (0x0500, 33)])   # PB full
    put_entries(m, snd, AT, [(0x0400, FREQ), (0x0100, 41), (0x0600, FREQ), (0, 0)])     # AT twice into FREQ
    r.open(100)
    check("edit: the popup is up", r.visible() == 1)
    # a turn on VEL's row: stock's setEntry (a new entry), then setDepth
    r.calls.take()
    check("edit: VEL's row lit", r.to_row(ROW0 + VEL))
    took = r.turn(1, 1)
    vel = entries(m, snd, VEL)
    calls = r.calls.take()
    rep["turn"] = {"took": took, "vel": vel, "calls": calls}
    check("edit: a turn from 0 adds VEL's entry into FREQ in its first free place (place 2), in whole units",
          vel[0] == (0x0100, 40) and vel[1][1] == FREQ and vel[1][0] == 0x100 * took and vel[2:] == [(0, 0)] * 2,
          f"{vel} (took {took})")
    check("edit: ... through stock's own MOD SETUP object (its setEntry / setDepth ran)", calls["entry"] + calls["depth"] >= 1,
          str(calls))
    ve = voice_entries(m, 0, VEL)
    check("edit: ... and stock copied it into the track's voices", ve == vel, f"{ve}")
    r.turn(1, 1)
    vel2 = entries(m, snd, VEL)
    calls = r.calls.take()
    check("edit: a second turn writes the depth word through setDepth", vel2[1][0] > vel[1][0] and calls["depth"] >= 1,
          f"{vel2[1]} {calls}")
    r.panel.screen("edit_vel")
    # YES on MW's empty row: +32
    check("edit: MW's row lit", r.to_row(ROW0 + MW))
    r.panel.tap(YES)
    mw = entries(m, snd, MW)
    check("edit: YES on MW's empty row adds its entry at +32 (0x2000) in its first place", mw[0] == (0x2000, FREQ)
          and mw[1:] == [(0, 0)] * 3, f"{mw}")
    r.quiet()
    # mute: NO, the sound unchanged, the voices' copies at depth 0, a mark; YES unmutes
    r.panel.tap(NO)
    r.quiet()
    mw_m, vm, vo = entries(m, snd, MW), voice_entries(m, 0, MW), voice_entries(m, 5, MW)
    rep["mute"] = {"sound": mw_m, "voice1": vm, "voice6": vo, "marks": r.marks().hex()}
    check("edit: NO mutes MW's entry: the sound unchanged (stock firmware plays it)", mw_m == mw, f"{mw_m}")
    check("edit: ... the record holds its mark", r.marks() == bytes([LIST[MW] << 2 | 0, FREQ, 0x20, 0x00]),
          r.marks().hex())
    check("edit: ... the track's voices copy it at depth 0 (heard as 0)", vm[0] == (0, FREQ), f"{vm}")
    r.panel.screen("edit_mw_muted")
    r.panel.tap(YES)
    r.quiet()
    vm2 = voice_entries(m, 0, MW)
    check("edit: YES unmutes it: the mark gone, the voices hear it again", vm2[0] == (0x2000, FREQ) and r.marks() == b"",
          f"{vm2} {r.marks().hex()}")
    # FULL: PB's four places in use
    check("edit: PB's row lit", r.to_row(ROW0 + PB))
    pb0 = entries(m, snd, PB)
    r.calls.take()
    r.panel.tap(YES)
    r.quiet()
    r.turn(1, 1)
    r.quiet()
    check("edit: PB full (4/4): YES and a turn add nothing, nothing written", entries(m, snd, PB) == pb0
          and r.calls.take() == {"entry": 0, "depth": 0}, f"{entries(m, snd, PB)}")
    r.panel.screen("edit_pb_full")
    # a long NO deletes VEL's entry: its place freed
    check("edit: VEL's row lit again", r.to_row(ROW0 + VEL))
    r.long_no()
    r.quiet()
    vel3 = entries(m, snd, VEL)
    check("edit: a long NO deletes VEL's entry, its place freed (the other entry kept)",
          vel3 == [(0x0100, 40), (0, 0), (0, 0), (0, 0)], f"{vel3}")
    # duplicates: AT's two entries into FREQ merged by a turn
    check("edit: AT's row lit", r.to_row(ROW0 + AT))
    took = r.turn(1, 1)
    at = entries(m, snd, AT)
    rep["merge"] = at
    check("edit: AT's two entries into FREQ merged into the first, the depths summed and turned (0x0A00 + the turn)",
          at[0] == (0x0A00 + 0x100 * took, FREQ) and at[1] == (0x0100, 41) and at[2] == (0, 0), f"{at} (took {took})")
    # FUNC + NO: ours and MOD SETUP's into FREQ
    MX.put_routes(m, sym, 0, [(3, FREQ, 0x5000)], call=lambda *x: MO.guest(m, *x))   # ENV1 -> FREQ
    put_entries(m, snd, KEY, [(0x0300, FREQ), (0, 0), (0, 0), (0, 0)])
    r.func_no()
    r.quiet()
    left = [(j, e) for j in range(6) for e in entries(m, snd, j) if e[1] == FREQ]
    check("edit: FUNC + NO deletes ours and every MOD SETUP entry into FREQ (the others kept)",
          not left and not r.routes() and entries(m, snd, AT)[1] == (0x0100, 41) and entries(m, snd, PB) == pb0,
          f"left {left}, routes {r.routes()}")
    check("edit: the popup still up", r.visible() == 1)
    report["edit"] = rep


def scenario_offers(a, report, sym):
    import emu_destpop as DP
    from emulib.panel import YES
    r = pop_rig(a, sym, "offers")
    if r is None:
        return
    m = r.m
    listed = {MO.record(m, e)[1] for e in DP.stock_list(r, 0x0200)}
    listed.discard(0)                                   # (a record at slot 0 in stock's list: never a knob's slot)
    ours = {s for s in range(1, 128) if MO.guest(m, sym["mxs_offers"], 0, s) & 0xFF}
    report["offers"] = {"stock": len(listed), "ours": len(ours)}
    check("offers: the popup's MOD SETUP list is stock's (want 0x200), slot for slot",
          ours == listed and len(listed) > 30, f"stock {len(listed)}, ours {len(ours)}, differ {sorted(ours ^ listed)[:12]}")
    gc.collect()
    e = MX.env2_rig(a, sym, "offers_env2")
    if e is None:
        return
    m, snd = e.m, e.m.long(MO.KIT) + 52
    put_entries(m, snd, VEL, [(0, 0)] * 4)
    e.open()
    check("offers: the popup is up on ENV2's ATK", MO.guest(m, sym["mxp_visible"]) & 1 == 1)
    order = list(m.read(sym["mxp_order"], 11))
    from emulib.panel import DOWN
    for _ in range(order.index(ROW0 + VEL)):
        e.panel.tap(DOWN, after=3_000_000)
    e.panel.tap(YES)
    e.panel.settle(10_000_000)
    e.panel.screen("offers_env2_yes")
    check("offers: YES on VEL's row into ENV2's ATK adds nothing (NOT IN SETUP)", entries(m, snd, VEL) == [(0, 0)] * 4,
          f"{entries(m, snd, VEL)}")


# --- the frame ------------------------------------------------------------------------------------
def frame_machine(build, snapshot, sym, lists):
    """16 voices on track 1's kit sound, its MOD SETUP lists LISTS {row: entries}, each source non-zero; stock's copy
    into the voices made"""
    gc.collect()
    m = MX.setup(build, snapshot)
    snd = MX.sound(m, 0)
    for v in range(16):
        m.write(MX.VSOUND + 4 * v, struct.pack(">I", snd))
        m.write(MO.OWNER + 4 * v, struct.pack(">I", 0))
        for s in (30, 40, 50, 60, FREQ, 70, 80):
            MX.set_cell(m, v, s, 0x2000 + 0x300 * (v % 5) + 0x100 * (s % 7))
        for l in (1, 2, 3):
            MX.set_lfo(m, v, l, 0, 4, 0, MX.ATT_FULL)
    m.write(VALUES[0], struct.pack(">16h", *[0x1000 + 0x700 * v for v in range(16)]))
    for va, val in zip(VALUES[1:], (0x3000, 0x5800, 0x2400, 0x6100)):
        m.write(va, struct.pack(">16h", *([val] * 16)))
    m.write(0x8000DDA0, struct.pack(">16i", *[(15360 + 0x40 * (v - 8)) << 8 for v in range(16)]))
    for j, es in lists.items():
        put_entries(m, snd, j, es)
    m.flush()
    m.call(sym["mx_poll"])
    m.call(MIRROR_COPY, snd, 0)
    return m, snd


LISTS = {VEL: [(0x3000, FREQ), (-0x2000, 70), (0, 0), (0, 0)], MW: [(0x1800, FREQ), (0, 0), (0, 0), (0, 0)],
         AT: [(0x0900, 40), (0, 0), (0x2200, 50), (0, 0)], KEY: [(0, 0), (0, 0), (0x0800, 30), (0, 0)]}


def MX_run_rows(m, sym, n):
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out = []
    for _ in range(n):
        m.call(MO.SMOOTHER, MO.SRC)
        m.call(MODS, MO.OUT)
        m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
        out.append(bytes(m.read(MO.OUT + 34, 202 * 16)))
    return out


def put_marks(m, sym, ms):
    """the record's marks MS [(row, place, slot, depth)] (none: the field removed), then the UI pass lays them out"""
    val = b"".join(struct.pack(">BBh", LIST[j] << 2 | p, s, d) for j, p, s, d in ms)
    buf = m.alloc(max(len(val), 4))
    m.write(buf, val)
    m.flush()
    m.call(sym["wish_put"], MX.sound(m, 0), SETUP_TAG, buf, len(val))
    m.call(sym["mx_poll"])


def scenario_frame(a, report, sym):
    n = min(a.frames, 60)
    rep = {}
    mp, _ = frame_machine(a.build, a.snapshot, sym, LISTS)
    plain = MX_run_rows(mp, sym, n)
    del mp
    gc.collect()
    m, snd = frame_machine(a.build, a.snapshot, sym, LISTS)
    same = all(bytes(m.read(VREC + 153 * v, 153)) == bytes(m.read(snd + 222, 153)) for v in range(16))
    check("frame: with no mark, stock's copy into the voices is the sound's MOD SETUP bytes", same)
    sound0 = bytes(m.read(snd + 222, 153))
    put_marks(m, sym, [(MW, 0, FREQ, 0x1800), (AT, 2, 50, 0x2200)])
    check("frame: the marks leave the sound unchanged", bytes(m.read(snd + 222, 153)) == sound0)
    vm = voice_entries(m, 3, MW)[0], voice_entries(m, 3, AT)[2]
    check("frame: the voices' copies hold the marked entries at depth 0", vm == ((0, FREQ), (0, 50)), f"{vm}")
    muted = MX_run_rows(m, sym, n)
    zero = dict(LISTS)
    zero[MW] = [(0, FREQ)] + LISTS[MW][1:]
    zero[AT] = LISTS[AT][:2] + [(0, 50), (0, 0)]
    mz, _ = frame_machine(a.build, a.snapshot, sym, zero)
    zf = MX_run_rows(mz, sym, n)
    d = [f for f in range(n) if muted[f] != zf[f]]
    moved = sum(1 for f in range(n) if muted[f] != plain[f])
    check("frame: a muted entry is heard exactly as that entry at depth 0, every row, every frame", not d and moved > 0,
          f"{len(d)} of {n} frames differ; muted vs unmuted differ in {moved}")
    # outside change: MW's depth changed in the sound (stock's page, Overbridge), stock's copy: it plays
    MO.w16(m, snd + 230 + 16 * LIST[MW], 0x1900)
    m.flush()
    m.call(MIRROR_COPY, snd, 0)
    check("frame: an entry changed from outside no longer matches its mark: it plays",
          voice_entries(m, 3, MW)[0] == (0x1900, FREQ), f"{voice_entries(m, 3, MW)[0]}")
    MO.w16(m, snd + 230 + 16 * LIST[MW], 0x1800)
    m.flush()
    m.call(MIRROR_COPY, snd, 0)
    check("frame: put back as marked, muted again", voice_entries(m, 3, MW)[0] == (0, FREQ))
    # the note's copy (0x4002549c(sound, voice)): masked too
    m.write(VREC + 153 * 7, bytes(153))
    m.flush()
    m.call(NOTE_COPY, snd, 7)
    nv = voice_entries(m, 7, MW)[0], voice_entries(m, 7, VEL)[0]
    check("frame: the note's copy (0x4002549c) lands the muted entry at depth 0, the others as they are",
          nv == ((0, FREQ), (0x3000, FREQ)), f"{nv}")
    # a sound not the kit's (a sound lock's): never masked
    other = m.alloc(1163)
    m.write(other, bytes(m.read(snd, 1163)))
    dst = m.alloc(160)
    m.flush()
    m.call(sym["mxs_copy"], dst, other + 222, 153)
    check("frame: a sound not the kit's (a lock's) is copied as it is, unmasked",
          bytes(m.read(dst, 153)) == bytes(m.read(other + 222, 153)))
    put_marks(m, sym, [])
    back = all(voice_entries(m, v, MW)[0] == (0x1800, FREQ) and voice_entries(m, v, AT)[2] == (0x2200, 50)
               for v in range(16))
    check("frame: the marks removed, the voices hear the entries again", back)
    rep["frames"] = n
    rep["copies"] = m.long(sym["mxs_copies"])
    report["frame"] = rep


def frame_digest(build, snapshot, sym, n):
    m, snd = frame_machine(build, snapshot, sym, LISTS)
    fr = MX_run_rows(m, sym, n)
    _, copy = m.cost(MIRROR_COPY, snd, 0)               # stock's copy into the track's 16 voices (an edit)
    _, note = m.cost(NOTE_COPY, snd, 5)                 # a note's (the sound given to voice 6)
    _, frame_cost = m.cost(MODS, MO.OUT)
    return (hashlib.sha256(b"".join(fr)).hexdigest(), {"edit_copy_16_voices": copy, "note_copy": note,
                                                       "mods_pass": frame_cost})


def scenario_exact(a, report, sym):
    if not a.base:
        check("exact: --base given", False)
        return
    n = min(a.frames, 60)
    ours, cost_o = frame_digest(a.build, a.snapshot, sym, n)
    base_sym = json.loads(pathlib.Path(a.base_layout).read_text())["layout"] if a.base_layout else sym
    gc.collect()
    base, cost_b = frame_digest(a.base, a.base_snapshot, base_sym, n)
    report["exact"] = {"ours": ours, "base": base, "cost_ours": cost_o, "cost_base": cost_b, "frames": n}
    print(f"    exact: {json.dumps(report['exact'])}", flush=True)
    check(f"exact: with no mark, {n} frames x 16 rows bit for bit the base build's", ours == base)
    check("exact: MOD SETUP's pass (the frame) the same instructions as the base", cost_o["mods_pass"] == cost_b["mods_pass"],
          f"{cost_o['mods_pass']} / {cost_b['mods_pass']}")


def scenario_look(a, report, sym):
    """the screens for scratch/setup-rows.png"""
    from emulib.panel import DOWN, NO
    r = pop_rig(a, sym, "look")
    if r is None:
        return
    m, snd = r.m, r.snd
    dest = MO.record(m, 78)[1]
    m.write(snd + 20 + 2 * dest, struct.pack(">H", FREQ << 8))                   # LFO1 -> FREQ
    put_entries(m, snd, VEL, [(0x1E00, FREQ), (0, 0), (0, 0), (0, 0)])           # VEL 30.00
    put_entries(m, snd, MW, [(-0x0C80, FREQ), (0x0100, 40), (0, 0), (0, 0)])     # MW -12.50 (muted below)
    for v in range(4):                                                           # the sources' levels now
        for l in range(3):
            MX.set_out(m, sym, v, l, [0x50000000, -0x30000000, 0x18000000][l])
    m.write(VALUES[0], struct.pack(">h", 0x5A00))
    m.write(0x8000DE20, struct.pack(">h", 0x4000))
    m.write(0x8000DE40, struct.pack(">h", -0x2000))
    m.write(0x8000DDE0, struct.pack(">h", 0x6000))
    m.flush()
    r.open(100)
    check("look: the popup is up", r.visible() == 1)
    r.to_row(ROW0 + MW)
    r.panel.tap(NO)
    r.quiet()
    shots = []
    for name, row in (("top", 0), ("setup", ROW0 + MW), ("bottom", ROW0 + KEY)):
        r.to_row(row)
        r.quiet()
        p = pathlib.Path(str(pathlib.Path(a.json or "out/setuprows").with_suffix("")) + "_png") / f"look_{name}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        r.panel.panel.write_png(bytes(m.read(m.long(0x402A10CC), 1024)), str(p))
        shots.append(str(p))
    report["look"] = {"shots": shots, "dims": m.long(sym["mxp_dims"]), "ticks": m.long(sym["mxp_ticks"])}
    check("look: the dimmed levels were worked out", m.long(sym["mxp_dims"]) > 0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--base", default=None)
    p.add_argument("--base-snapshot", default=None)
    p.add_argument("--base-layout", default=None, help="the base build's waverider_code.json (its mod_eval, mx_poll)")
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--scenario", default="edit,offers,frame,look")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report: dict = {}
    run = {"edit": scenario_edit, "offers": scenario_offers, "frame": scenario_frame, "exact": scenario_exact,
           "look": scenario_look}
    for name in a.scenario.split(","):
        print(f"== {name}", flush=True)
        try:
            run[name](a, report, sym)
        except Exception as e:                          # noqa: BLE001 -- a scenario that broke is a failure
            import traceback
            traceback.print_exc()
            check(f"{name}: ran to its end", False, repr(e)[:300])
        gc.collect()
    report["fails"] = FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print("PASS" if not FAILS else f"FAIL: {len(FAILS)} checks: " + "; ".join(FAILS)[:600], flush=True)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
