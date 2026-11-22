"""The moving line shows p-locks (2026-11-20, the User: "modulation and plock should be displayed with our line ... but
not MOVE the knob"; csrc/modulation/moving.c own_set). emu_modulation.py's scenario "locks".

The sequencer does not play in the emulator, so a locked step is played as the note block plays it, with stock's own
routines (as scripts/emu_slides.py): the track's sound into voice 1's mirror block (SYNC 0x4002549c), a lock table with
one lock, stock's builder (0x400d874c) and its applier (0x400db1f6: the locked value into the smoother's input SRC); the
next step without the lock: stock's undo (0x400db0a8: the locked slots back to the sound). Between them the frame's
parameter path by hand (stock's smoother, the six sources, the LFOs), and the UI runs (its polls redraw the lines).

On each case (a stock page: WaveTone's FLTR, FREQ; one of our machines' pages: TB-303's SYN 1; a sample machine's page:
ONESHOT's SYN 1):
  - at rest (the voice synced to the sound, the smoother settled, no route into the page): no line;
  - the locked step played: a build with the change draws the line at the locked value (exactly moving.c's line), a
    build before it draws none (the line's "set" was the smoother's state, which the lock moves); either way the sound's
    stored value and the knob's own pixels (the cell above the line's row) do not change: the knob never moves;
  - the next step without the lock: the smoother back on the sound's value; the line still there 300 ms after heard
    met set, gone 433 ms after (the 400 ms linger).
And a knob turned (FREQ, the stock page): stock's smoother glides the voice to the new value; no line at any poll
during the turn and after it (the 300 ms in which "set" is still the smoother's state).
"""

from __future__ import annotations

import struct

SYNC, UNDO, BITMAP_CLEAR = 0x4002549C, 0x400DB0A8, 0x400DB1B6
BUILD, APPLY = 0x400D874C, 0x400DB1F6
REC, RECS, INDEX, COUNTS = 258, 80, 20640, 22256
TABLE_BYTES = COUNTS + 2048
LIST_BYTES = 20 + 202 * 8
SOUND = 1163
MV = 0x46AF8000 + 0x500                 # MOD_MOVING_RAM
FLTR, SYN = (0, 2), (0, 1)
SKIP_IDS = (254, 256)                   # a sample machine's PLAY and SAMP: no lock of those here (a sample load)
CASES = (("WAVETONE", 1, 36), ("TB303", 54, None), ("ONESHOT", 8, None))   # (name, type, record or the first knob)


class Rig:
    def __init__(self, EM, a, sym):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.EM, self.sym = EM, sym
        self.m = m = EM.machine(a.build, a.snapshot)
        self.panel = Panel(m, png_dir=str(__import__("pathlib").Path(a.json or "out/modulation").with_suffix(""))
                           + "_locks_png")
        self.knobs = []
        m.write(EM.UI_TRACK, b"\x00")

        def on_knob(uc, ad, sz, us):
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            self.knobs.append(struct.unpack(">7i", m.read(sp + 4, 28))[1:])     # x, y, w, id, lo, hi
        m.uc.hook_add(UC_HOOK_CODE, on_knob, begin=sym["mv_knob"], end=sym["mv_knob"])
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, us: self.knobs.clear(), begin=sym["mv_begin"],
                      end=sym["mv_begin"])
        m.flush()
        self.panel.settle(3_000_000)
        frac = m.alloc(len(EM.SET_FRAC))
        m.write(frac, EM.SET_FRAC)
        m.flush()
        EM.guest(m, frac)
        self.rate, self.o1, self.o2 = m.long(EM.RATE), m.alloc(256), m.alloc(256)
        m.write(sym["sl_lastv"], b"\x00")       # track 1 last played voice 1, which plays it
        m.write(EM.OWNER, struct.pack(">I", 0))

    # --- the voice and the sound ------------------------------------------------------------------------------
    def snd(self):
        return self.m.long(self.EM.KIT) + 52

    def own(self, s):
        return self.EM.u16(self.m, self.snd() + 20 + 2 * s)

    def src(self, s):
        return self.EM.u16(self.m, self.EM.SRC + 2 * self.EM.idx(0, s))

    def out(self, s):
        return self.EM.u16(self.m, self.EM.OUT + 2 * self.EM.idx(0, s))

    def no_routes(self):
        """no LFO DEST and no MOD SETUP route on track 1's sound: nothing modulates (the six sources, the LFOs)"""
        EM, m, snd = self.EM, self.m, self.snd()
        for rid in EM.DESTS:
            m.write(snd + 20 + 2 * EM.record(m, rid)[1], b"\0\0")
        m.write(snd + 230, bytes(96))
        m.flush()

    def at_rest(self):
        """voice 1 plays track 1's sound (stock's SYNC), its smoother settled there -> the slots 1..100 where the voice's
        input is not the sound's stored cell"""
        EM, m = self.EM, self.m
        m.write(EM.OWNER, struct.pack(">I", 0))
        EM.guest(m, SYNC, self.snd(), 0)
        EM.guest(m, BITMAP_CLEAR, 0)
        differ = []
        for s in range(1, 101):
            v = self.src(s)
            m.write(EM.STATE + 4 * EM.idx(0, s), struct.pack(">I", v << 16))
            EM.w16(m, EM.OUT + 2 * EM.idx(0, s), v)
            if v != self.own(s):
                differ.append(s)
        m.flush()
        return differ

    def run(self, frames, settle=30_000_000):
        """FRAMES audio frames' parameter path (smoother, six sources, LFOs), the frame clock moved, the UI run"""
        EM, m = self.EM, self.m
        for _ in range(frames):
            EM.guest(m, EM.SMOOTHER, EM.SRC)
            EM.guest(m, self.sym["smp_mod_apply"], EM.OUT)
            EM.guest(m, self.sym["mod_eval"], EM.OUT, self.rate, 0, 0, self.o1, self.o2, 0)
        m.write(EM.FRAMES, struct.pack(">I", (m.long(EM.FRAMES) + frames) & 0xFFFFFFFF))
        self.panel.settle(settle)

    def lock(self, s, value):
        """a step of track 1 with one lock (slot S = VALUE) played on voice 1: stock's builder and applier"""
        m, EM = self.m, self.EM
        table = m.alloc(TABLE_BYTES)
        m.write(table, b"\xff" * (REC * RECS))
        m.write(table + INDEX, b"\xff" * (16 * 101))
        m.write(table, bytes([s, 0]) + b"\xff\xff" * 128)
        m.write(table + INDEX + s, bytes([0]))
        m.write(table + 2, struct.pack(">H", value))           # step 0
        lst = m.alloc(LIST_BYTES)
        m.write(lst, b"\x5a" * LIST_BYTES)
        m.flush()
        EM.guest(m, BUILD, 0, lst, table, self.snd() + 48, 0, 0, 0)
        EM.guest(m, APPLY, 0, lst, EM.SRC)

    def unlock(self):
        """the next step, no lock: stock's undo puts the locked slots back to the sound"""
        self.EM.guest(self.m, UNDO, 0, self.EM.SRC, self.snd())

    # --- the screen ---------------------------------------------------------------------------------------------
    def row_lit(self, x, y, w):
        from emu import panel as P
        lit = P.lit(self.EM.glass(self.m))
        return [k for k in range(w) if (x + k, 63 - y) in lit]

    def cell_pixels(self, x, y, w):
        """the knob's own pixels: its cell above the line's row (18 rows)"""
        from emu import panel as P
        lit = P.lit(self.EM.glass(self.m))
        return sorted((xx, yy) for xx in range(x, x + w) for yy in range(63 - min(63, y + 18), 63 - y) if (xx, yy) in lit)

    def page(self, key):
        self.knobs.clear()
        self.panel.tap(key)
        self.panel.settle(40_000_000)


def want_line(EM, m, rid, lo, hi, w, heard):
    at = (min(max(heard, lo), hi) - lo) * (w - 1) // (hi - lo)
    frm = (w - 1) // 2 if 2 * EM.record(m, rid)[4] == lo + hi else 0
    return list(range(min(frm, at), max(frm, at) + 1))


def one_case(r, new, name, mtype, want_rid, rep, shots):
    EM, m = r.EM, r.m
    if not EM.ours_machine(m, r.panel, mtype):
        EM.check(f"locks {name}: track 1 set to type {mtype}", False)
        return None
    r.no_routes()
    r.page(FLTR)
    if mtype != 1:
        r.page(SYN)
    knobs = {k[3]: k for k in r.knobs}
    pick = [k for k in r.knobs if (k[3] == want_rid if want_rid else
                                   k[3] not in SKIP_IDS and 1 <= EM.record(m, k[3])[1] <= 100 and k[5] > k[4])]
    EM.check(f"locks {name}: a knob to lock on the page", bool(pick), f"{sorted(knobs)}")
    if not pick:
        return None
    x, y, w, rid, lo, hi = pick[0]
    s = EM.record(m, rid)[1]
    differ = r.at_rest()
    EM.check(f"locks {name}: the voice synced to the sound plays the sound's stored value on slot {s}", s not in differ,
             f"slots where it differs {differ}")
    r.run(200)
    for _ in range(2):
        m.write(EM.FRAMES, struct.pack(">I", (m.long(EM.FRAMES) + 700) & 0xFFFFFFFF))
        r.panel.settle(30_000_000)
    rest_px, knob0, stored = r.row_lit(x, y, w), r.cell_pixels(x, y, w), r.own(s)
    shots[f"{name}-rest"] = r.panel.screen(f"locks-{name}-rest")
    EM.check(f"locks {name}: record {rid} (slot {s}) at rest: no line", rest_px == [],
             f"lit {rest_px}, heard {r.out(s):#06x}, stored {stored:#06x}")
    # the locked step
    span = hi - lo
    value = lo + (span * 3 // 4 if abs(lo + span * 3 // 4 - stored) > span // 8 else span // 4)
    if mtype != 8 and mtype != 1:
        value &= ~0xFF                                          # (a Monomachine knob's unit: the record's high byte)
    r.lock(s, value)
    EM.check(f"locks {name}: stock's applier wrote the lock into the voice's input", r.src(s) == value,
             f"SRC {r.src(s):#06x}, the lock {value:#06x}")
    r.run(150)
    px, want = r.row_lit(x, y, w), want_line(EM, m, rid, lo, hi, w, value)
    shots[f"{name}-locked"] = r.panel.screen(f"locks-{name}-locked")
    if new:
        EM.check(f"locks {name}: the locked step plays: the line at the locked value {value:#06x}", px == want,
                 f"lit {px}, want {want[0]}..{want[-1]}, heard {r.out(s):#06x}")
    else:
        EM.check(f"locks {name}: (before the change) the locked step plays: no line", px == [],
                 f"lit {px}, heard {r.out(s):#06x}")
    EM.check(f"locks {name}: the lock leaves the sound's stored value as it was", r.own(s) == stored,
             f"{r.own(s):#06x} vs {stored:#06x}")
    knob1 = r.cell_pixels(x, y, w)
    EM.check(f"locks {name}: the knob itself does not move (its cell's pixels above the line as at rest)",
             knob1 == knob0, f"{len(set(knob0) ^ set(knob1))} pixels differ")
    # the next step, no lock: back to the sound's value
    r.unlock()
    EM.check(f"locks {name}: stock's undo put the sound's value back", r.src(s) == stored, f"{r.src(s):#06x}")
    met = None
    for k in range(40):
        r.run(30, 8_000_000)
        if r.out(s) == stored:
            met = 30 * (k + 1)
            break
    EM.check(f"locks {name}: the smoother back on the sound's value", met is not None, f"heard {r.out(s):#06x}")
    m.write(EM.FRAMES, struct.pack(">I", (m.long(EM.FRAMES) + 420) & 0xFFFFFFFF))
    r.panel.settle(30_000_000)
    px_in = r.row_lit(x, y, w)
    m.write(EM.FRAMES, struct.pack(">I", (m.long(EM.FRAMES) + 230) & 0xFFFFFFFF))
    r.panel.settle(30_000_000)
    px_out = r.row_lit(x, y, w)
    if new:
        EM.check(f"locks {name}: the step after: the line still there 300 ms after heard met set", bool(px_in),
                 f"lit {px_in}")
    EM.check(f"locks {name}: the step after: no line 433 ms after heard met set", px_out == [], f"lit {px_out}")
    return {"record": rid, "slot": s, "line": [x, y, w], "range": [lo, hi], "stored": stored, "lock": value,
            "lit_locked": px, "frames_to_meet": met, "differ_at_rest": differ}


def turn_case(r, new, rep):
    """FREQ turned on WaveTone's FLTR page while voice 1 plays: no line at any poll during the turn and after it"""
    EM, m, panel = r.EM, r.m, r.panel
    EM.ours_machine(m, panel, 1)
    r.no_routes()
    r.page(FLTR)
    pick = [k for k in r.knobs if k[3] == 36]
    if not pick:
        EM.check("locks turn: FREQ on the FLTR page", False)
        return None
    x, y, w, rid, lo, hi = pick[0]
    s = EM.record(m, rid)[1]
    knob = (x - 1 - 24 + 13) // 26 + (4 if y - 5 < 13 else 0)
    stored = r.own(s)
    if stored > 0x6000:                                         # room to turn it up
        m.write(r.snd() + 20 + 2 * s, struct.pack(">H", 0x3000))
        m.flush()
        stored = 0x3000
    r.at_rest()
    r.run(100)
    m.write(EM.FRAMES, struct.pack(">I", (m.long(EM.FRAMES) + 700) & 0xFFFFFFFF))
    panel.settle(30_000_000)
    lines0, seen, srcs = m.long(MV + 8), [], []
    for _ in range(12):
        m.pc = panel.panelin.encoder(m.m, panel.profile, knob, 4)
        panel.settle(4_000_000)
        r.run(20, 6_000_000)
        seen.append(r.row_lit(x, y, w))
        srcs.append(r.src(s))
    turned = r.own(s)
    for _ in range(30):
        r.run(30, 6_000_000)
        seen.append(r.row_lit(x, y, w))
    lit = [p for p in seen if p]
    EM.check("locks turn: the turn moved FREQ's stored value", turned != stored, f"{stored:#06x} -> {turned:#06x}")
    EM.check("locks turn: the turn reached the voice's input (stock's mirror update)", srcs[-1] == turned,
             f"SRC {srcs[-1]:#06x}, stored {turned:#06x}")
    EM.check("locks turn: no line at any poll during the turn and after it (the glide is no modulation)", not lit,
             f"{len(lit)} of {len(seen)} polls showed a line, first {lit[:2]}; lines drawn {m.long(MV + 8) - lines0}")
    return {"stored": [stored, turned], "src": srcs, "polls": len(seen), "polls_with_line": len(lit)}


def scenario_locks(EM, a, report, sym):
    new = "mxp_per_note" in sym                                 # the build with the change (2026-11-20)
    print(f"    the build {'shows' if new else 'predates'} p-locks with the line", flush=True)
    r = Rig(EM, a, sym)
    rep, shots = {"new": new}, {}
    for name, mtype, rid in CASES:
        rep[name] = one_case(r, new, name, mtype, rid, rep, shots)
    rep["turn"] = turn_case(r, new, rep)
    rep["screens"] = shots
    report["locks"] = rep
