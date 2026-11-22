"""The MIXER pages' meters and the CLIP label (csrc/meter/mixer.c, meter.c; scratch/mixer-overview.md) in the ColdFire
emulator, on the build and its own snapshot:

    python scripts/emu_mixmeter.py --build BUILD.syx --snapshot SNAP [--work DIR]

The emulator runs no audio ISR and no DSP: the levels the DSP would send are written into mix_acc at every UI pass (a
hook on mix_poll's entry), the clips through the ISR's own routine (mix_clip_in, called as a guest with the reply word
set) or as stamps; FRAMES follows the panel tick (tick_clock), moved on by skip_frames where seconds must pass.

Checks:
- on Internal Mixer 2/5 and 3/5, FX Mixer 4/5 and External Mixer 5/5 (FUNC + [MOD]), the glass is stock's page (the
  same build with the meters off, mix_off) with exactly the model's meters drawn in (python, below: each meter's 17
  rows at 3 dB, its peak tick, its latch; FX Mixer's main cell cleared, OUT and the Overbridge ticks): every other
  pixel stock's;
- an update alone (mix_alone up, no full redraw asked) leaves the glass exactly what a full redraw then draws;
- Compressor 1/5, a SYN page and the TEMPO screen over 2/5: the glass the same with the meters on and off; the DSP's
  levels asked (mix_want) on 2/5..5/5 only;
- a latch: shown after a clip, still 1 s on, gone 2 s after it with its page up; a clip while another page is up
  stays until its page has been up 2 s;
- the CLIP label: in the title bar exactly as the forced label draws it while a clip in use is under 3 s old, gone
  after; never for a clip of an output not in use (mix_clip_in drops it);
- which outputs are in use (mix_live): the analog outputs, the input, the recorder; + Overbridge's main in Overbridge
  mode (not the tracks' and returns' own channels: 2026-11-20, "only when it matters"); + the USB OUT pair's channels
  in USB audio mode (stock's selection bytes);
- mix_lvl_in keeps each channel's largest unit.
Exit 0 and "MIXMETER OK" when every check holds; WORK/mixmeter.json the facts.
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

FB_BACK = 0x402A10CC
SET_DIRTY = 0x4011D5DE
METER_FORCE = 0x74                              # meter.c MTR_ICON_FORCE (METER_RAM + 0x74)
USB_MODE, USB_OUT_ON, USB_OUT_SEL = 0x4058F2A8, 0x80005362, 0x80005364
REPLY_W6 = 0x800053A4 + 0x18
OWNER = 0x80005308                              # each voice slot's track (mixer.c mix_inner_in)
BITS = 24                                       # mixer.c: the DSP's 23 clip bits, then a voice's with no track known
MIXER_VIEW = 0x401E292C
FUNC, MOD, TEMPO, SYN = (2, 0), (0, 5), (1, 0), (0, 1)
LV_CH, MIX_CH, ROWS = 25, 25, 17               # (mixer.c: the DSP's 25: 22, 23 Overbridge / USB main L, R, 24 the recorder)
LV_REPLY_MAGIC = 0xC5000000
# panel ticks for a change to reach the glass on a MIXER page: a level take every 12 ticks (mix_poll) and, since
# 2026-11-20, stock's full redraws held to one every 12 ticks (mix_dirty), each on its own phase: up to 24 ticks. (14
# covered one period only and passed by the phase alone; 2026-11-21, the MIXER overview's held-back FUNC + MOD tap
# moved the pages' arrival by a few ticks and a latch's going showed one period late)
UPDATE_TICKS = 26
TH = [65, 92, 130, 184, 260, 367, 518, 732, 1034, 1460, 2063, 2914, 4115, 5813, 8211, 11599, 16384]
# (channel, x, width, top row, the "!" column (0: none), stock's ticks there)
# (the "!" 1 px left of the tick column, 2026-11-20, the User: "move the ! a few pixels to the left"; DASH: the tick
# column, blank while the "!" shows)
_TRK = [(39, 13, 25), (65, 13, 51), (91, 13, 77), (117, 13, 103), (39, 40, 25), (65, 40, 51), (91, 40, 77),
        (117, 40, 103)]
PAGES = {1: [(k, x, 3, top, bx, bx + 1) for k, (x, top, bx) in enumerate(_TRK)],
         2: [(8 + k, x, 3, top, bx, bx + 1) for k, (x, top, bx) in enumerate(_TRK)],
         3: [(16, 40, 3, 40, 24, 0), (17, 66, 3, 40, 50, 0), (18, 92, 3, 40, 76, 0), (19, 106, 4, 13, 101, 0),
             (20, 112, 4, 13, 0, 0)],
         4: [(21, 40, 3, 13, 24, 0)]}
OUT_GLYPHS = [(7, 5, 5, 5, 7), (5, 5, 5, 5, 7), (7, 2, 2, 2, 2)]


def rows_of(peak: int) -> int:
    return sum(1 for t in TH if peak >= t)


def bit(g: bytes | bytearray, x: int, row: int) -> int:
    return g[8 * x + 7 - (row >> 3)] >> (row & 7) & 1


def put(g: bytearray, x: int, row: int, on: int) -> None:
    i, m = 8 * x + 7 - (row >> 3), 1 << (row & 7)
    g[i] = g[i] | m if on else g[i] & ~m & 0xFF


def model(stock: bytes, pg: int, lit, hold, latch) -> bytes:
    """the page as mixer.c draws it over STOCK"""
    g = bytearray(stock)
    if pg == 3:
        for x in range(102, 121):
            for r in range(12, 31):
                put(g, x, r, 0)
        for i, gl in enumerate(OUT_GLYPHS):
            for r in range(5):
                for c in range(3):
                    put(g, 105 + 4 * i + c, 31 + r, gl[r] >> (2 - c) & 1)
    for ch, x0, w, top, bx, dash in PAGES[pg]:
        n, h = lit[ch], hold[ch]
        for r in range(ROWS):
            level = ROWS - r
            on = n >= level or (h == level and h > n)
            for x in range(x0, x0 + w):
                put(g, x, top + r, on)
        if bx:
            bang = (latch[19] or latch[20]) if ch == 19 else latch[ch]
            cols = {bx, bx + 1} | ({dash, dash + 1} if dash else set())
            for r in range(ROWS):
                for x in cols:
                    if bang:
                        on = x in (bx, bx + 1) and (r < 12 or r >= 15)
                    else:
                        on = bool(dash) and x in (dash, dash + 1) and r % 4 == 0
                    put(g, x, top + r, on)
    return bytes(g)


def body(g: bytes) -> bytes:
    """the glass below the title bar (rows 10..63): rows 0..9 cleared"""
    out = bytearray(g)
    for x in range(128):
        out[8 * x + 7] = 0
        out[8 * x + 6] &= ~0x03 & 0xFF
    return bytes(out)


def mask(pg: int) -> set:
    """the pixels mixer.c may draw on page PG"""
    out = set()
    for ch, x0, w, top, bx, dash in PAGES[pg]:
        for x in [*range(x0, x0 + w), *((bx, bx + 1) if bx else ()), *((dash, dash + 1) if dash else ())]:
            for r in range(top, top + ROWS):
                out.add((x, r))
    if pg == 3:
        for x in range(102, 121):
            for r in range(11, 36):
                out.add((x, r))
    return out


class Rig:
    def __init__(self, a, sym, work):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        self.sym = sym
        self.m = m = EM.machine(a.build, a.snapshot)
        self.pn = Panel(m, png_dir=str(work / "screens"))
        self.pn.tick_clock(EM.FRAMES)
        self.pn.settle(3_000_000)
        self.levels = [0] * LV_CH
        self.feed = True

        def on_poll(uc, ad, sz, us):        # the DSP's levels, as its packets would leave them, at every pass
            if self.feed:
                blob = struct.pack(f">{MIX_CH}H", *(list(self.levels) + [0] * MIX_CH)[:MIX_CH])
                for s in (0, 1):
                    uc.mem_write(sym["mix_acc"] + 2 * MIX_CH * s, blob)
        m.uc.hook_add(UC_HOOK_CODE, on_poll, begin=sym["mix_poll"], end=sym["mix_poll"])
        m.flush()

    def long(self, name, k=0):
        return self.m.long(self.sym[name] + 4 * k)

    def wlong(self, va, v):
        self.m.write(va, struct.pack(">I", v & 0xFFFFFFFF))

    def glass(self):
        return EM.glass(self.m)

    def ticks(self, n):
        self.pn.run_ticks(n)

    def page(self):
        """the MIXER page's index (0..4), or -1"""
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

    def goto(self, pg):
        for _ in range(7):
            if self.page() == pg:
                return True
            self.func_mod()
        return self.page() == pg

    def redraw(self):
        """a full redraw now (2026-11-20: stock's MIXER redraws are held to 10 a second, mixer.c mix_dirty; the held
        redraws are emu_mixcpu.py's to check: here the redraw is let through, as a key would)"""
        thr = self.sym.get("mix_thr_off")
        if thr is not None:
            self.wlong(thr, 1)
        EM.guest(self.m, SET_DIRTY, self.long("wr_screen_obj"))
        self.ticks(4)
        if thr is not None:
            self.wlong(thr, 0)

    def off(self, on: bool):
        self.wlong(self.sym["mix_off"], 1 if on else 0)


def startup(r, sym, shot, rep):
    """2026-11-20, the User: "at boot it says !CLIP and !DSP... can we fix it?" (csrc/meter/startup.c). From the
    snapshot with the start-up's words as at a load (0): the DSP not reporting, then reporting with stock's loading
    over; a clip in use (the analog outputs) and the DSP's load at 100 % stay unlit and the clip is forgotten until the
    DSP has reported 2 s; then a load over 99 % lights DSP and a clip lights CLIP at once, each as the forced label
    draws it. Leaves the start-up over (as on a unit running a while) and the DSP's load fields as it found them."""
    m = r.m
    if "mtr_start_done" not in sym:
        EM.check("the build has the start-up's quiet (mtr_start_done)", False)
        return
    force_va = sym["mtr_ram"] + METER_FORCE
    keep = {k: r.long(k) for k in ("smp_load_peak", "smp_load_at", "smp_load_seen")}
    per = r.long("smp_periods")

    def title_bar():
        g = r.glass()
        return bytes(g[8 * x + 7] for x in range(56, 128)) + bytes(g[8 * x + 6] & 0x03 for x in range(56, 128))

    def blink_on():
        for _ in range(60):
            if not (m.long(EM.FRAMES) // 375) & 1:
                return
            r.ticks(1)

    def bar_now():
        blink_on()
        r.redraw()
        return title_bar()

    def clip_dac():
        w = LV_REPLY_MAGIC | 1 << 20
        r.wlong(REPLY_W6, (w & 0xFFFF) << 16 | w >> 16)
        EM.guest(m, sym["mix_clip_in"])
        return r.long("mix_clip_at", 20) != 0

    def load(permille, seen):
        r.wlong(sym["smp_load_peak"], permille)
        r.wlong(sym["smp_load_at"], per)
        r.wlong(sym["smp_load_seen"], (per | 1) if seen else 0)

    def forced(bits):
        r.wlong(force_va, bits)
        out = bar_now()
        r.wlong(force_va, 0)
        return out

    r.wlong(force_va, 0)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    load(1000, False)
    r.wlong(sym["mtr_start_done"], 0)                   # as at a load (code data: 0)
    r.wlong(sym["mtr_start_at"], 0)
    r.pn.skip_frames(5000)
    r.ticks(4)
    bare = bar_now()
    p0 = r.long("mtr_start_polls")
    got = {"stamped (DSP silent)": clip_dac()}
    r.ticks(3)
    got["forgotten (DSP silent)"] = r.long("mix_clip_at", 20) == 0
    got["bar (DSP silent)"] = bar_now() == bare
    diag = {}

    def note(tag):                                      # (the detail of a failure)
        diag[tag] = {k: r.long(k) for k in ("mtr_start_done", "mtr_start_at", "mtr_start_polls", "smp_periods",
                                             "smp_load_seen")}
        diag[tag]["frames"] = m.long(EM.FRAMES)
        diag[tag]["quiet"] = m.long(sym["mtr_ram"] + 0x7C)
    def poll():                                         # until the labels' poll has run again (it does not run
        n = r.long("mtr_start_polls")                   # at every panel tick in the emulator: measured 3 in 1,600
        for _ in range(60):                             # frames)
            r.ticks(2)
            if r.long("mtr_start_polls") != n:
                return True
        return False
    note("silent")
    load(1000, True)                                    # the DSP reports, at 100 %
    got["polled"] = poll()
    note("reporting")
    at0 = r.long("mtr_start_at")
    r.pn.skip_frames(1500)                              # 1 s of it
    poll()
    got["stamped (1 s)"] = clip_dac()
    poll()
    got["forgotten (1 s)"] = r.long("mix_clip_at", 20) == 0
    got["bar (1 s)"] = bar_now() == bare
    shot("startup_quiet")
    note("1 s")
    got["still starting (1 s)"] = r.long("mtr_start_done") == 0 and at0 != 0
    got["polls quiet"] = r.long("mtr_start_polls") > p0
    r.pn.skip_frames(1600)                              # past 2 s of reports
    poll()
    note("2 s")
    got["over after 2 s"] = r.long("mtr_start_done") == 1
    d_live = bar_now()
    shot("startup_over_dsp")
    got["DSP lit at 100 % after, as forced"] = d_live != bare and d_live == forced(1)
    load(500, True)                                     # back under: DSP's second of hold, then nothing
    r.pn.skip_frames(1600)
    r.ticks(4)
    got["DSP gone under 99 %"] = bar_now() == bare
    clip_dac()
    r.ticks(2)
    c_live = bar_now()
    shot("startup_over_clip")
    got["CLIP lit after, as forced"] = c_live != bare and c_live == forced(8)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    for k, v in keep.items():
        r.wlong(sym[k], v)
    r.ticks(2)
    rep["startup"] = got
    rep["startup_diag"] = diag
    EM.check("start-up: a clip and a 100 % DSP load unlit (the clip forgotten) while the DSP is silent and for 2 s of "
             "its reports; after, DSP and CLIP lit at once, as the forced labels", all(got.values()),
             json.dumps(got) + " " + json.dumps(diag))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", default="out/mixmeter")
    a = p.parse_args()
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    r = Rig(a, sym, work)
    m = r.m
    rep = {}

    def shot(name):
        r.pn.panel.write_png(r.glass(), str(work / f"{name}.png"))

    startup(r, sym, shot, rep)

    # outputs in use, before anything: mode 0 (no USB audio), Overbridge, USB audio with its OUT pair
    base = 1 << 20 | 1 << 21 | 1 << 22
    live = {}
    for name, mode, on, sel in (("none", 0, 0, (0, 1)), ("overbridge", 6, 0, (0, 1)), ("usb T1", 5, 1, (2, 3)),
                                ("usb main", 5, 1, (0, 1)), ("usb off", 5, 0, (2, 3)), ("usb ret2", 5, 1, (36, 37))):
        r.wlong(USB_MODE, mode)
        m.write(USB_OUT_ON, bytes([on]))
        m.write(USB_OUT_SEL, bytes([sel[0] & 0xFF, sel[1] & 0xFF]))
        live[name] = EM.guest(m, sym["mix_live_bits"]) & 0xFFFFFFFF     # (at once: stock rewrites the bytes)
    want_live = {"none": base, "overbridge": base | 1 << 19, "usb T1": base | 1, "usb main": base | 1 << 19,
                 "usb off": base, "usb ret2": base | 1 << 17}
    rep["live"] = {k: f"{v:#x}" for k, v in live.items()}
    EM.check("the outputs in use (mix_live): analog, input, recorder; Overbridge its main; USB audio its pair",
             live == want_live, json.dumps(rep["live"]))
    r.wlong(USB_MODE, 0)
    m.write(USB_OUT_ON, bytes([0]))

    # mix_clip_in: only bits of outputs in use, only with the magic
    def clip_in(bits, magic=LV_REPLY_MAGIC):
        w = magic | bits
        r.wlong(REPLY_W6, (w & 0xFFFF) << 16 | w >> 16)           # the DSP's store, halves swapped
        EM.guest(m, sym["mix_clip_in"])
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.ticks(2)                                   # (mix_live recomputed: mode 0)
    clip_in(1 << 3 | 1 << 20)
    at = [r.long("mix_clip_at", k) for k in range(23)]
    EM.check("mix_clip_in: the analog outputs' clip stamped, a track's dropped (not in use)", at[20] != 0 and at[3] == 0)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    clip_in(1 << 20, magic=0)
    EM.check("mix_clip_in: a word without the magic ignored", all(r.long("mix_clip_at", k) == 0 for k in range(BITS)))

    # mix_lvl_in keeps the largest
    for s in (0, 1):
        m.write(sym["mix_acc"] + 2 * MIX_CH * s, bytes(2 * MIX_CH))
    r.feed = False
    sel = r.long("mix_sel") & 1
    buf = 0x46FF0000
    try:
        m.write(buf, bytes(64))
    except Exception:                           # noqa: BLE001
        buf = sym["mix_acc"] + 0x400
    m.write(buf, struct.pack(f">{LV_CH}H", *[100 * (k + 1) for k in range(LV_CH)]))
    EM.guest(m, sym["mix_lvl_in"], buf)
    m.write(buf, struct.pack(f">{LV_CH}H", *[3000 - 100 * k for k in range(LV_CH)]))
    EM.guest(m, sym["mix_lvl_in"], buf)
    got = struct.unpack(f">{LV_CH}H", m.read(sym["mix_acc"] + 2 * MIX_CH * sel, 2 * LV_CH))
    EM.check("mix_lvl_in keeps each channel's largest unit",
             list(got) == [max(100 * (k + 1), 3000 - 100 * k) for k in range(LV_CH)])
    r.feed = True

    # a page that is not one of ours: on and off the same
    def same_on_off(what):
        r.off(False)
        r.redraw()
        on = r.glass()
        r.off(True)
        r.redraw()
        off = r.glass()
        r.off(False)
        return on == off

    r.levels = [16384] * LV_CH
    EM.check("a SYN page: the glass the same with the meters on and off", same_on_off("syn"))
    EM.check("not on a mixer page: no levels asked", r.long("mix_want") == 0)
    EM.check("the MIXER: Compressor 1/5 reached", r.goto(0))
    EM.check("Compressor 1/5: the same on and off; no levels asked", same_on_off("comp") and r.long("mix_want") == 0)

    # each page: stock's glass + the model's meters, an update alone, the full redraw after it
    levels = [16384 if k % 5 == 0 else TH[(3 * k) % ROWS] for k in range(LV_CH)]
    for pg, title in ((1, "Internal Mixer 2/5"), (2, "Internal Mixer 3/5"), (3, "FX Mixer 4/5"),
                      (4, "External Mixer 5/5")):
        if not r.goto(pg):
            EM.check(f"{title} reached", False)
            continue
        r.levels = [0] * LV_CH
        r.ticks(30)
        r.pn.skip_frames(5000)                   # every peak tick let go (3 s), then a poll at 0
        r.ticks(30)
        r.off(True)
        r.redraw()
        stock = r.glass()
        shot(f"p{pg}_stock")
        r.off(False)
        r.levels = levels
        r.ticks(30)                              # (a poll: no buffer yet -> a full redraw draws the meters)
        r.ticks(30)
        g1 = r.glass()
        shot(f"p{pg}_meters")
        lit = [rows_of(v) for v in levels]
        want = model(stock, pg, lit, lit, [0] * LV_CH)
        outside = [(x, row) for x in range(128) for row in range(64) if (x, row) not in mask(pg)
                   and bit(g1, x, row) != bit(stock, x, row)]
        EM.check(f"{title}: every pixel outside the meters stock's", not outside, str(outside[:6]))
        EM.check(f"{title}: the meters as the model draws them", g1 == want,
                 f"{sum(1 for i in range(1024) if g1[i] != want[i])} bytes differ")
        EM.check(f"{title}: the DSP's levels asked", r.long("mix_want") == 1)
        # an update: levels down, the tick holds the 3 s peak; alone when stock's page is not being drawn anyway (stock
        # 1.12 draws its MIXER pages again on its own, many times a second: then its next full draw carries them)
        n_alone, n_full, n_grp = r.long("mix_alone"), r.long("mix_fulls"), r.long("mix_groups")
        low = [TH[2] if k % 2 else 0 for k in range(LV_CH)]
        r.levels = low
        r.ticks(UPDATE_TICKS)
        g2 = r.glass()
        want2 = model(stock, pg, [rows_of(v) for v in low], lit, [0] * LV_CH)
        EM.check(f"{title}: within a poll the levels down on the glass, the peak ticks held, no full redraw of ours",
                 g2 == want2 and r.long("mix_fulls") == n_full,
                 f"alone {r.long('mix_alone') - n_alone} full {r.long('mix_fulls') - n_full} why {r.long('mix_why')} "
                 f"differ {sum(1 for i in range(1024) if g2[i] != want2[i])}")
        rep.setdefault("updates alone / groups", {})[title] = [r.long("mix_alone") - n_alone,
                                                               r.long("mix_groups") - n_grp]
        r.redraw()
        EM.check(f"{title}: a full redraw then draws the same glass", r.glass() == g2)
        # the meters add no full draw: stock's own rate with them off and on (a second each)
        rates = []
        for off in (True, False):
            r.off(off)
            r.ticks(10)
            d0 = r.long("wr_draws")
            r.ticks(121)
            rates.append(r.long("wr_draws") - d0)
        r.off(False)
        rep.setdefault("full draws a second, meters off / on", {})[title] = rates
        EM.check(f"{title}: the meters add no full draw (stock's own rate off and on)", rates[1] <= rates[0] + 2,
                 str(rates))
        r.levels = [0] * LV_CH

    # the TEMPO screen over 2/5: nothing of ours over it
    r.goto(1)
    r.pn.press_for(TEMPO, 6)
    r.pn.release_for(TEMPO, 40)
    EM.check("the TEMPO screen over Internal Mixer 2/5: the same with the meters on and off", same_on_off("tempo"))
    shot("tempo_over_2")
    r.pn.press_for(TEMPO, 6)
    r.pn.release_for(TEMPO, 40)

    # Overbridge / USB main (the User, 2026-11-20: "the main OUT level is zero when Overbridge is connected": the analog
    # main is empty of the internal sound in Overbridge mode): its peaks are the DSP's channels 22, 23 and its clip the
    # DSP's bit 19, both from TX slots 0, 1 as sent (sampler.program ob_peaks; the ColdFire read the words itself until
    # the same day, mix_ob_main, 1.56 % of the CPU): bit 19 kept only while that output is in use
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.feed = False
    r.wlong(USB_MODE, 0)
    r.ticks(2)                                   # (mix_live recomputed: no Overbridge)
    clip_in(1 << 19)
    EM.check("Overbridge / USB main not in use: the DSP's bit 19 dropped", r.long("mix_clip_at", 19) == 0)
    r.wlong(USB_MODE, 6)
    r.ticks(2)
    clip_in(1 << 19)
    EM.check("Overbridge mode: the DSP's bit 19 (its main at full scale as sent) stamped", r.long("mix_clip_at", 19) != 0)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.feed = True
    r.wlong(USB_MODE, 6)
    r.goto(3)
    r.levels = [0] * 22 + [16384, TH[10]]        # the analog main silent, Overbridge's main at full scale and -18 dB
    r.pn.skip_frames(5000)
    r.ticks(30)
    r.ticks(UPDATE_TICKS)
    lit = [0] * MIX_CH
    lit[19], lit[20] = 17, rows_of(TH[10])
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.ticks(UPDATE_TICKS)
    r.off(True)
    r.redraw()
    stock4 = r.glass()
    r.off(False)
    r.redraw()
    want = model(stock4, 3, lit, lit, [0] * MIX_CH)
    EM.check("Overbridge mode, the analog main silent: OUT shows Overbridge's main", r.glass() == want)
    shot("p3_out_overbridge")
    r.wlong(USB_MODE, 0)
    r.pn.skip_frames(5000)
    r.ticks(30)
    r.ticks(UPDATE_TICKS)
    r.redraw()
    EM.check("Overbridge off: OUT shows the analog main alone (silent here)",
             r.glass() == model(stock4, 3, [0] * MIX_CH, [0] * MIX_CH, [0] * MIX_CH))
    r.levels = [0] * LV_CH

    # every page with every channel clipped (every channel's clip stamped as the ISR stamps one in use: since 2026-11-20
    # no mode has them all in use): the "!"s; the screenshots
    r.wlong(USB_MODE, 6)
    clip_levels = [16384] * LV_CH
    for pg, title in ((1, "Internal Mixer 2/5"), (2, "Internal Mixer 3/5"), (3, "FX Mixer 4/5"),
                      (4, "External Mixer 5/5")):
        r.goto(pg)
        r.levels = [0] * LV_CH
        r.pn.skip_frames(5000)
        r.ticks(30)
        r.off(True)
        r.redraw()
        stock = r.glass()
        r.off(False)
        r.levels = clip_levels
        for k in range(BITS):
            r.wlong(sym["mix_clip_at"] + 4 * k, (m.long(EM.FRAMES) | 1))
        r.ticks(UPDATE_TICKS)
        r.ticks(UPDATE_TICKS)
        r.redraw()
        lit = [17] * MIX_CH
        want = body(model(stock, pg, lit, lit, [1] * MIX_CH))
        g = body(r.glass())                      # (below the title bar: the CLIP label comes and goes with the clips)
        EM.check(f"{title}: every channel clipped: each meter full, each '!' lit, every other pixel stock's",
                 g == want, f"{sum(1 for i in range(1024) if g[i] != want[i])} bytes differ")
        shot(f"p{pg}_clipped")
    r.levels = [0] * LV_CH
    r.wlong(USB_MODE, 0)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.pn.skip_frames(5000)
    r.ticks(20)

    # latches: a clip in use on 2/5's TRK3 (bit 2), stamped as the ISR stamps one in use (USB audio with TRK3 as its
    # OUT pair; stock rewrites the selection bytes at once, so the stamp is written)
    def clip_trk3():
        r.wlong(sym["mix_clip_at"] + 4 * 2, (m.long(EM.FRAMES) | 1))
    r.goto(1)
    r.ticks(20)
    r.levels = [0] * LV_CH

    def latched(bx=77, top=13):                  # TRK3's "!", 1 px left of its tick column: rows no tick lights
        g = r.glass()
        return all(bit(g, xx, rr) for xx in (bx, bx + 1) for rr in (top + 1, top + 5, top + 15)) and not bit(g, bx, top + 13)
    clip_trk3()
    r.ticks(UPDATE_TICKS)
    EM.check("a clip in use: TRK3's latch shown", latched())
    shot("latch_on")
    r.pn.skip_frames(1500)
    r.ticks(UPDATE_TICKS)
    EM.check("... still 1 s after", latched())
    r.pn.skip_frames(1700)
    r.ticks(UPDATE_TICKS)
    EM.check("... gone 2 s after, its page up", not latched())
    r.goto(2)
    r.ticks(UPDATE_TICKS)
    clip_trk3()                              # while 3/5 is up
    r.pn.skip_frames(4000)
    r.ticks(UPDATE_TICKS)
    r.goto(1)
    r.ticks(UPDATE_TICKS)
    EM.check("a clip while another page was up: shown when its page comes", latched())
    r.pn.skip_frames(1500)
    r.ticks(UPDATE_TICKS)
    EM.check("... still 1 s after", latched())
    r.pn.skip_frames(1700)
    r.ticks(UPDATE_TICKS)
    EM.check("... gone 2 s after its page came", not latched())

    # the CLIP label: as the forced label, for 3 s after a clip in use; never for one not in use
    def title_bar():
        g = r.glass()
        return bytes(g[8 * x + 7] for x in range(56, 128)) + bytes(g[8 * x + 6] & 0x03 for x in range(56, 128))

    def blink_on():
        for _ in range(60):
            if not (m.long(EM.FRAMES) // 375) & 1:
                return
            r.ticks(1)
    r.wlong(sym["mtr_ram"] + METER_FORCE, 0) if "mtr_ram" in sym else None
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.pn.skip_frames(5000)
    r.redraw()
    bare = title_bar()
    clip_in(1 << 20)
    blink_on()
    r.ticks(2)
    r.redraw()
    live_bar = title_bar()
    shot("label_on")
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    force_va = sym.get("mtr_ram", 0x46AFF000) + METER_FORCE
    r.wlong(force_va, 8)
    blink_on()
    r.redraw()
    forced = title_bar()
    r.wlong(force_va, 0)
    EM.check("the CLIP label: lit after a clip in use, as the forced label draws it", live_bar == forced and live_bar != bare)
    clip_in(1 << 20)
    r.pn.skip_frames(4600)
    r.ticks(4)
    r.redraw()
    EM.check("... gone 3 s after the clip", title_bar() == bare)
    r.wlong(USB_MODE, 0)
    r.ticks(3)
    clip_in(1 << 5)                              # a track's Overbridge channel, Overbridge off
    blink_on()
    r.redraw()
    EM.check("no label for a clip of an output not in use", title_bar() == bare)

    def bar_now():
        blink_on()
        r.redraw()
        return title_bar()

    # 2026-11-20 (the User: "only when it matters"; a track at LEVEL 100 lit CLIP from its own Overbridge channel):
    # Overbridge mode, a hot track and a hot return alone: not stamped, no label, no "!"; its main over: CLIP and OUT's "!"
    m.write(USB_OUT_ON, bytes([0]))
    r.wlong(USB_MODE, 6)
    r.goto(1)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.pn.skip_frames(5000)
    r.ticks(20)
    bare1 = bar_now()
    clip_in(1 << 2 | 1 << 16)                    # TRK3's and DEL's own channels
    r.ticks(UPDATE_TICKS)
    hot = {"not stamped": r.long("mix_clip_at", 2) == 0 and r.long("mix_clip_at", 16) == 0,
           "no '!' on TRK3": not latched()}
    hot["no label"] = bar_now() == bare1
    shot("ob_hot_track")
    r.goto(3)
    r.ticks(UPDATE_TICKS)
    bare3 = bar_now()
    r.wlong(force_va, 8)
    forced3 = bar_now()
    r.wlong(force_va, 0)
    r.wlong(sym["mix_clip_at"] + 4 * 19, (m.long(EM.FRAMES) | 1))   # as mix_clip_in stamps Overbridge's main over
    r.ticks(UPDATE_TICKS)
    hot["main over: OUT's '!'"] = latched(101, 13)
    hot["main over: the label"] = bar_now() == forced3 != bare3
    shot("ob_main_over")
    rep["ob_only_main"] = hot
    EM.check("Overbridge mode: a hot track or return alone lights nothing; its main over lights CLIP and OUT's '!'",
             all(hot.values()), json.dumps(hot))
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)

    # 2026-11-20 (clip-inner; the User: "NO DIGITAL CLIPPING ... if it does, i want the alert"): a voice's own clip
    # (a clip packet, mix_inner_in with its slots, as link.c calls it), still in Overbridge mode, where the track's own
    # channel lights nothing: the slot's track (stock's voice owner table) gets its "!" and the label lights; a packet
    # with no slot lights nothing
    r.goto(1)
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.pn.skip_frames(5000)
    r.ticks(20)
    bare1 = bar_now()
    saved = [m.long(OWNER + 4 * v) for v in range(16)]
    for v in range(16):
        r.wlong(OWNER + 4 * v, (v + 4) % 16)                      # slot 0 plays T5 (track 4)
    EM.guest(m, sym["mix_inner_in"], 0, 0, 0)
    r.ticks(UPDATE_TICKS)
    inner = {"an empty packet: nothing": not any(r.long("mix_clip_at", k) for k in range(BITS)) and bar_now() == bare1}
    EM.guest(m, sym["mix_inner_in"], 1 << 0, 0, 0)
    r.ticks(UPDATE_TICKS)
    inner["slot 0's clip: T5 stamped"] = r.long("mix_clip_at", 4) != 0
    inner["T5's '!' on 2/5"] = latched(25, 40)
    inner["no other track's '!' (TRK3)"] = not latched()
    inner["the label"] = bar_now() != bare1
    shot("inner_t5")
    rep["inner"] = inner
    EM.check("a voice's own clip (clip packet): its track's '!' and the CLIP label, in Overbridge mode too",
             all(inner.values()), json.dumps(inner))
    for v in range(16):
        r.wlong(OWNER + 4 * v, saved[v])
    for k in range(BITS):
        r.wlong(sym["mix_clip_at"] + 4 * k, 0)
    r.wlong(USB_MODE, 0)

    rep["fails"] = EM.FAILS
    (work / "mixmeter.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    if EM.FAILS:
        print(f"MIXMETER FAIL ({len(EM.FAILS)})")
        return 1
    print("MIXMETER OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
