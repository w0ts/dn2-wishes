"""The AMP page's oscilloscope (csrc/scope/scope.c) in the ColdFire emulator: its cost, the UI's latency while it is
up, and (with --proof) its frames byte for byte.

    python scripts/emu_scope.py --build BUILD.syx --snapshot SNAP --work DIR [--seconds 3] [--uart real|instant]

The emulator has no audio interrupt, so the scope's ring (scope_ring, scope_pos) is fed by the harness: a moving
waveform (a sine with harmonics whose phase advances, and a burst of noise) written every 40 ms of panel ticks.

--uart real (the default) models the panel UART as the unit has it: UART8 at 156,250 baud, ten bits a byte, about
129 bytes a panel tick (121 ticks a second). digikit's eDMA model (emu/edma.py) runs each transfer the moment it is
armed, so in the emulator the display never waits; here a transfer completes only once its bytes would have left at
that rate, so the firmware's own ring logic (0x4000220c's free-space wait) waits as on the unit.

Measured, the scope page against WaveTone's SYN page (no scope), each over SECONDS of panel ticks:
  frames      full draws (wr_screen) a second; scope frames drawn; groups sent a frame and bytes a second
  cost        instructions a frame: wr_screen (the page draw), scope_draw, panel_diff
  uart        the UART ring's fill (bytes queued), mean and peak; ticks the UI task spent in the free-space wait
  latency     encoder G turned (the scope's gain, a knob on the SYN page): panel ticks until the UI task pops the
              item (smp_ui_pop), and until a frame drawn after it has left on the UART
Exit 0 and "SCOPE OK" when every check of --proof holds (or, without --proof, when it ran); facts in WORK/scope.json.

--proof also checks the vertical zoom (2026-11-17, the User: "the oscilloscope should have autozoom vertical (below
X1)"): G stepped through every gain x1/8..x16 and AUTO, each frame's strip pixel for pixel as the model draws it at
that gain (x1..x16 as v1 drew them); AUTO on a full-scale signal takes a gain below x1 and no frame has a trace pixel
on the strip's top or bottom row; on a quiet one it goes back up (to x16), only after its hold; loud again, it zooms
out on the first frame. AUTO's label (G's, 2026-11-18) is the same pixels at every gain it takes, and no manual gain's.

--shot NAME (no checks): a full-scale signal at the gain G is turned to, the glass saved as WORK/NAME.png (--turns N: G N
detents from the build's first gain: AUTO since 2026-11-18, so 0 is AUTO and -5 is x1; v1 started at x1, so 5 is AUTO
there). --layout takes another build's waverider_code.json (v1's, for the before).

--proof also (2026-11-18): every frame drawn alone, as it goes to panel_diff, is the last full draw's frame byte for
byte but for the strip, which is the model's (a control writing one byte at column 2 in those frames passed before);
the page title's message runs out and the bar shows its own title again with nothing asked; the glass a full redraw
draws after the gains, AUTO loud, quiet and loud again, a page change and a track change; AUTO the first gain; the gain
and the span kept over the page change, the track change and a power-on (the snapshot afresh, the settings sector
served from what the first run wrote: one write, a second after the turns), AUTO and 8 ms with no sector, a bad one or
values out of range, kept by a FACTORY RESET as the other settings are.

2026-11-19 (the User): the scope opens on [TRIG] held a second (open_scope), over stock's TRIG page, no longer from
[AMP]. --proof also (trig_keys): a short [TRIG] is stock's TRIG page (on the press from another page, a step on a tap's
release on it, no step after a hold of 0.6 s), the scope not before the second and up after it, staying up after the
release; [TRIG], SYN, AMP, FX and NO close it; [AMP] steps two pages, never the scope; FUNC + [TRIG] is QUANTIZE; a
knob turned while [TRIG] is held cancels it.
"""

from __future__ import annotations

import argparse
import gc
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
FB_FRONT, FB_BACK = 0x402A10C8, 0x402A10CC
GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions
PANEL_DIFF = 0x40131FD2
WAIT_LOOP = 0x4000221C                  # the UART ring's free-space wait
RING_HEAD, RING_PEND, RING_TAIL = 0x4058E5D0, 0x4058E5D8, 0x4058E5DC
TCD35_CITER, TCD35_BITER = 0xFC045474, 0xFC04547C
BYTES_A_TICK = 156_250 / 10 / 121       # UART8, 10 bits a byte, 121 panel ticks a second
SYN, AMP = (0, 1), (0, 3)
TRIGK, FX, NO_KEY, FUNC = (0, 0), (0, 4), (1, 3), (2, 0)        # the [TRIG] page key (code 1), FX 5, NO 12, FUNC 17
LONG = 121                                      # ovw.c LONG_TICKS: a page key held a second (the User, 2026-11-19)
# stock 1.12's page views (the screen's view list, as ins.c view_of walks it; measured in the emulator, 2026-11-19)
TRIG_VIEW, AMP_VIEW, SYN_VIEW, QUANT_VIEW = 0x401E2180, 0x401E2320, 0x401D4DB0, 0x401E3CB0
AMP_SCOPE = 2                                   # amp_pages.h: amp_sub while the scope is up
ENC_G = 6
RING, SHOWN = 256, 100


class Rig:
    def __init__(self, a, sym, work):
        from emulib.panel import Panel
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.sym, self.work, self.a = sym, work, a
        self.m = m = EM.machine(a.build, a.snapshot)
        self.panel = Panel(m, png_dir=str(work / "screens"))
        self.K = K
        self.tick_last, self.ticks = None, 0
        self.stats = self._zero()
        self.pops = []
        self.uart_due = None
        self.fed_tick, self.lcg = 0, 12345

        def on_screen(uc, ad, sz, us):
            self.stats["screens"] += 1

        def on_group(uc, ad, sz, us):
            self.stats["groups"] += 1

        def on_wait(uc, ad, sz, us):
            self.stats["waits"] += 1

        def on_pop(uc, ad, sz, us):
            self.pops.append(self.now())
        m.uc.hook_add(UC_HOOK_CODE, on_screen, begin=sym["wr_screen"], end=sym["wr_screen"])
        m.uc.hook_add(UC_HOOK_CODE, on_group, begin=GROUP_CONT, end=GROUP_CONT)
        m.uc.hook_add(UC_HOOK_CODE, on_wait, begin=WAIT_LOOP, end=WAIT_LOOP)
        m.uc.hook_add(UC_HOOK_CODE, on_pop, begin=sym["smp_ui_pop"], end=sym["smp_ui_pop"])
        self.c_screen = EM.Counter(m, sym["wr_screen"])
        self.c_scope = EM.Counter(m, sym["scope_draw"])
        self.c_diff = EM.Counter(m, PANEL_DIFF)
        self.c_poll = EM.Counter(m, sym["scope_poll"])
        self.screen = None
        # 2026-11-18 (the gate gap: a control writing one byte at column 2 in frames drawn alone passed): the frame
        # every full draw ends with (scope_end's canvas, when the scope may draw alone over it), and every frame drawn
        # alone, as it goes to panel_diff, checked byte for byte against it: the strip as the model draws it, every
        # other pixel the full draw's
        self.ref, self.alone_checks = None, []
        # 2026-11-19: each frame drawn alone as it went to panel_diff, with the gain, AUTO's choice, the ring and pos
        # it was drawn from (next_frames: a G turn landing later in the same tick changed them before its sample)
        self.alone_seen = []
        poll = sym.get("scope_poll")

        def on_end(uc, ad, sz, us):
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            canvas, clean = struct.unpack(">Ii", m.read(sp + 4, 8))
            self.ref = bytes(m.read(m.long(canvas + 16), 1024)) if clean else None

        def on_diff(uc, ad, sz, us):
            ret = m.long(uc.reg_read(K.UC_M68K_REG_A7))
            if poll is not None and poll <= ret < poll + 0x400:
                self.check_alone()
        if "scope_end" in sym:
            m.uc.hook_add(UC_HOOK_CODE, on_end, begin=sym["scope_end"], end=sym["scope_end"])
        m.uc.hook_add(UC_HOOK_CODE, on_diff, begin=PANEL_DIFF, end=PANEL_DIFF)

        def on_screen_arg(uc, ad, sz, us):
            self.screen = struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0]
        m.uc.hook_add(UC_HOOK_CODE, on_screen_arg, begin=sym["wr_screen"], end=sym["wr_screen"])
        # 2026-11-21: every write of the scope's own code in its place (scripts/scope_area.py)
        self.area = None
        if getattr(a, "chunk", None) and "scope_poll" in sym:
            import scope_area                   # noqa: PLC0415
            self.area = scope_area.AreaWatch(m, K, sym, a.chunk, PANEL_DIFF, FB_FRONT)
        if a.uart == "real":
            self._slow_uart()
        m.flush()
        m.write(EM.UI_TRACK, b"\x00")
        # the audio frames move with the instructions (the scope's 25/s timer counts them), on the same clock as the
        # panel tick the UART model drains by: 1,500 frames per 121 ticks of about 1.1 M instructions (digikit's
        # INSTR_PER_SEC is 4.68 M, the panel tick's ~133 M a second: 1,500 a second of the former ran the scope's
        # timer 28 times too fast against the UART)
        from emu.pit import INSTR_PER_SEC
        self.panel.frame_clock(EM.FRAMES, per_sec=round(1500 * INSTR_PER_SEC / (121 * 1_100_000)))
        self.panel.settle(3_000_000)

    def gain_k(self):
        """the shift the frame was drawn at: the gain, or the one AUTO took"""
        gain = struct.unpack(">i", self.m.read(self.sym["scope_gain"], 4))[0]
        auto = struct.unpack(">i", self.m.read(self.sym["scope_auto"], 4))[0]
        return (auto if gain == GAINS else gain) - GAIN_X1

    def check_alone(self):
        """a frame drawn alone, in FRONT before panel_diff sends it: the last full draw's frame with the strip as the
        model draws it from the ring now, every byte"""
        front = bytes(self.m.read(self.m.long(FB_FRONT), 1024))
        ring = list(struct.unpack(f">{RING}h", bytes(self.m.read(self.sym["scope_ring"], 2 * RING))))
        pos = self.m.long(self.sym["scope_pos"])
        gain = struct.unpack(">i", self.m.read(self.sym["scope_gain"], 4))[0]
        auto = struct.unpack(">i", self.m.read(self.sym["scope_auto"], 4))[0]
        self.alone_seen.append((gain, auto, ring, pos, self.gain_k(), front))
        if self.ref is None:
            self.alone_checks.append(["no full draw ended with the scope on top before this frame"])
            return
        want = expected_frame(self.ref, model_strip(ring, pos, self.gain_k()))
        diff = [i for i in range(1024) if want[i] != front[i]]
        self.alone_checks.append([f"{len(diff)} bytes differ from the full draw's frame with the model's strip "
                                  f"(columns {sorted({i // 8 for i in diff})[:8]})"] if diff else [])

    @staticmethod
    def _zero():
        return {"screens": 0, "groups": 0, "waits": 0, "occ": [], "frames_fed": 0}

    # --- time: the panel tick, unwrapped ---------------------------------------------------------------------
    def now(self):
        t = self.m.long(TICK) & 0xFFF
        if self.tick_last is not None:
            self.ticks += (t - self.tick_last) & 0xFFF
        self.tick_last = t
        return self.ticks

    def run_ticks(self, n):
        """about N panel ticks (1.1 M instructions each), the UART moving at its own rate"""
        for _ in range(n):
            self.panel.settle(1_100_000)
            self.now()
            self._uart_poll()
            self.stats["occ"].append(self.occupancy())

    # --- the UART at the unit's rate --------------------------------------------------------------------------
    def _slow_uart(self):
        ch = self.m.ev.get("edma_tx")
        if ch is None:
            raise SystemExit("no eDMA UART channel in this machine (ev['edma_tx'])")
        orig_run, orig_deliver = ch.run, ch.deliver

        def run():                              # armed: it completes once its bytes would have left
            citer = ch._u16(0x14) & 0x7FFF
            if not citer or self.uart_due is not None:
                return 0
            n = citer * ch._u32(0x08)
            self.uart_due = (self.now() + max(1, math.ceil(n / BYTES_A_TICK)), orig_run)
            return 0

        def deliver():                          # the firmware's free-space wait: time read here too (2026-11-19:
            self.now()                          # identity's settle and other raw settles never called now(), so a
            self._uart_poll()                   # transfer due in them never completed and the UI task sat in the
            return orig_deliver()               # wait to the end: "the full redraw asked for did not run")
        ch.run, ch.deliver = run, deliver

    def _uart_poll(self):
        if self.uart_due is not None and self.ticks >= self.uart_due[0]:
            fn = self.uart_due[1]
            self.uart_due = None
            fn()

    def occupancy(self):
        """bytes in the UART ring not yet sent, as 0x4000220c counts them"""
        citer = struct.unpack(">H", self.m.read(TCD35_CITER, 2))[0] & 0x7FFF
        biter = struct.unpack(">H", self.m.read(TCD35_BITER, 2))[0] & 0x7FFF
        d1 = ((citer - biter) + (self.m.long(RING_HEAD) - self.m.long(RING_TAIL))) & 0xFFF
        return d1 + self.m.long(RING_PEND)

    # --- the scope's input ------------------------------------------------------------------------------------
    def feed(self, k):
        """the ring as 64 samples of the ISR's tap would leave it. sine: a sine with a harmonic, its phase moving,
        every fifth frame a noise burst. noise: full-scale noise (every column of the trace spans most of the strip:
        the most groups a frame, the busy-audio case)"""
        pos = self.m.long(self.sym["scope_pos"])
        ring = bytearray(self.m.read(self.sym["scope_ring"], 2 * RING))
        for i in range(64):
            j = pos + i
            if self.a.feed == "loud":            # full scale and past it (clipped): -32768 and 32767 reached
                v = max(-1.0, min(1.0, 1.3 * math.sin(2 * math.pi * (j / 37.0) + k * 0.7)))
                struct.pack_into(">h", ring, 2 * ((pos + i) % RING), max(-32768, min(32767, round(v * 32768))))
                continue
            if self.a.feed == "quiet":           # 4 % of full scale: AUTO's x16 fits it
                v = 0.04 * math.sin(2 * math.pi * (j / 37.0) + k * 0.7)
            elif self.a.feed == "noise":
                self.lcg = (self.lcg * 1103515245 + 12345) & 0x7FFFFFFF
                v = (self.lcg / 0x3FFFFFFF) - 1.0
            else:
                ph = 2 * math.pi * (j / 37.0) + k * 0.7
                v = 0.6 * math.sin(ph) + 0.25 * math.sin(3 * ph + k)
                if k % 5 == 4 and 20 <= i < 30:
                    v += 0.3 * math.sin(j * 2.1)
            struct.pack_into(">h", ring, 2 * ((pos + i) % RING), int(max(-1.0, min(1.0, v)) * 30000))
        self.m.write(self.sym["scope_ring"], bytes(ring))
        self.m.write(self.sym["scope_pos"], struct.pack(">I", (pos + 64) & 0xFFFFFFFF))
        self.stats["frames_fed"] += 1

    def run_fed(self, ticks):
        for _ in range(ticks):
            if self.fed_tick % 5 == 0:          # every 40 ms
                self.feed(self.fed_tick // 5)
            self.fed_tick += 1
            self.run_ticks(1)

    # --- pages ------------------------------------------------------------------------------------------------
    def tap(self, key):
        self.panel.tap(key)
        self.run_ticks(30)

    def press(self, key, ticks):
        """KEY pressed and held TICKS panel ticks (the ring fed; stock's key task sends its repeats meanwhile)"""
        self.m.pc = self.panel.panelin.press(self.m.m, self.panel.profile, *key)
        self.run_fed(ticks)

    def release(self, key, ticks=30):
        self.m.pc = self.panel.panelin.release(self.m.m, self.panel.profile, *key)
        self.run_fed(ticks)

    def up(self):
        return self.m.long(self.sym["scope_up"]) != 0

    def open_scope(self):
        """2026-11-19 (the User): the scope opens on a long press of the [TRIG] page key (held a second, LONG)"""
        if not self.up():
            self.press(TRIGK, LONG + 24)
            self.release(TRIGK)
        return self.up()

    def turn_g(self, delta=1):
        """encoder G one detent: -> the tick it went in"""
        t = self.now()
        self.panel.m.pc = self.panel.panelin.encoder(self.m.m, self.panel.profile, ENC_G, delta)
        return t


def measure(r, label, seconds):
    for c in (r.c_screen, r.c_scope, r.c_diff, r.c_poll):
        c.runs.clear()
    r.stats = r._zero()
    k0 = {n: r.m.long(r.sym[n]) for n in ("scope_frames", "scope_alone", "scope_dropped") if n in r.sym}
    r.run_fed(int(121 * seconds))
    k1 = {n: r.m.long(r.sym[n]) - v for n, v in k0.items()}
    st = r.stats
    s = seconds
    out = {"screens_a_s": round(st["screens"] / s, 1), "groups_a_frame": round(st["groups"] / max(1, st["screens"]), 1),
           "bytes_a_s": round(st["groups"] * 10 / s), "uart_capacity_a_s": round(BYTES_A_TICK * 121),
           "occ_mean": round(sum(st["occ"]) / max(1, len(st["occ"]))), "occ_peak": max(st["occ"] or [0]),
           "wait_hits": st["waits"],
           "instr_screen": round(sum(r.c_screen.runs) / max(1, len(r.c_screen.runs))),
           "instr_scope_draw": round(sum(r.c_scope.runs) / max(1, len(r.c_scope.runs))) if r.c_scope.runs else 0,
           "instr_panel_diff": round(sum(r.c_diff.runs) / max(1, len(r.c_diff.runs))),
           "instr_a_s": round((sum(r.c_screen.runs) + sum(r.c_diff.runs) + sum(r.c_poll.runs)) / s),
           "instr_scope_poll_max": max(r.c_poll.runs or [0]),
           "scope_counts_a_s": {n: round(v / s, 1) for n, v in k1.items()}}
    # the key-to-screen delay: G turned one detent (on the scope page its gain: G's label changes; on the SYN page a
    # knob), then the panel ticks until the glass shows it, plus the time the bytes queued ahead of it take to leave
    # the UART (the queue is in order: the change is on the panel once they have gone)
    def sig():
        back = bytes(r.m.read(r.m.long(FB_BACK), 1024))
        return back[0::8] if label == "scope page" else back       # the scope page: rows 0..7, its labels
    r.pops.clear()
    before = sig()
    t0 = r.turn_g(-1)                         # (from AUTO, the default, down: G's label changes)
    popped = shown = None
    for _ in range(int(121 * 4)):
        r.run_fed(1)
        if popped is None:
            later = [t for t in r.pops if t >= t0]
            popped = later[0] - t0 if later else None
        if sig() != before:
            shown = r.ticks - t0 + r.occupancy() / BYTES_A_TICK
            break
    out["latency_pop_ms"] = round(popped * 1000 / 121) if popped is not None else None
    out["key_to_screen_ms"] = round(shown * 1000 / 121) if shown is not None else None
    # a fast turn: G 30 detents, one a tick (a quick spin of the knob); its items' pops counted and how long the
    # last one waited after the last detent went in
    r.pops.clear()
    first = r.now()
    for _ in range(30):
        r.turn_g(-1)
        r.run_fed(1)
    last_in = r.now()
    for _ in range(int(121 * 6)):
        n_before = len(r.pops)
        r.run_fed(3)
        if len(r.pops) == n_before and r.ticks - last_in > 60:
            break
    pops = [t for t in r.pops if t >= first]
    out["burst_pops"] = len(pops)
    out["burst_last_pop_after_ms"] = round((pops[-1] - last_in) * 1000 / 121) if pops else None
    print(f"    {label}: {json.dumps(out)}", flush=True)
    return out


X0, MID, HALF = 24, 31, 20


def model_strip(ring, pos, k=0):
    """v1's scope_draw (SET_PIXEL loops) at gain 2^K (K -3..4; v1's gains are K 0..4), as pixels lit in x 18..123,
    y 11..53: -> set of (x, y)"""
    snap = [ring[(pos + i) % RING] for i in range(RING)]
    start = RING - SHOWN
    for i in range(RING - SHOWN, 0, -1):
        if snap[i - 1] < 0 <= snap[i]:
            start = i
            break

    lit = set()
    for x in range(0, SHOWN, 4):
        lit.add((X0 + x, MID))

    def yp(v):                                  # C: MID + v * 2^k * HALF / 32768, truncating toward zero, clamped
        q = v * HALF
        t = abs(q) * 2 ** k // 32768 if k >= 0 else abs(q) // (32768 << -k)
        y = MID + (t if q >= 0 else -t)
        return max(MID - HALF, min(MID + HALF, y))
    last = yp(snap[start])
    for x in range(SHOWN):
        y = yp(snap[start + x])
        for v in range(min(y, last), max(y, last) + 1):
            lit.add((X0 + x, v))
        last = y
    return {(x, y) for x, y in lit if 18 <= x <= 123 and 11 <= y <= 53}


STRIP_X, STRIP_Y = (18, 123), (11, 53)          # the strip the checks compare with the model


def expected_frame(ref, lit):
    """REF (a full draw's frame) with the strip's pixels as LIT (a set of (x, y)), every other byte REF's"""
    out = bytearray(ref)
    for x in range(STRIP_X[0], STRIP_X[1] + 1):
        for y in range(STRIP_Y[0], STRIP_Y[1] + 1):
            i, bit = 8 * x + (y >> 3), 0x80 >> (y & 7)
            out[i] = (out[i] | bit) if (x, y) in lit else (out[i] & ~bit)
    return bytes(out)


def back_strip(buf):
    return {(x, y) for x in range(18, 124) for y in range(11, 54) if (buf[8 * x + (y >> 3)] >> (7 - (y & 7))) & 1}


TITLE_VTABLE = 0x401E1D28               # the title bar's view class (csrc/inserts/ins.c)


def message_left(r):
    """the title bar's message time left, or None: stock's message line (ins.c title(): the title view's +120), its
    word +0x4C counting down every 4 panel ticks to 0 (measured 2026-11-18, claude/cpu-cuts: 0x6f after the scope
    page opened). Read the way ins.c's view_of walks the screen's views"""
    m = r.m
    ok = lambda a: 0x40000000 <= a < 0x48000000 and not a & 3                    # noqa: E731
    s = m.long(r.sym["wr_screen_obj"])
    if not ok(s):
        return None
    node = m.long(s + 28)
    for _ in range(32):
        if not ok(node) or node == s + 20:
            return None
        v = m.long(node + 8)
        if ok(v) and m.long(v) == TITLE_VTABLE:
            msg = m.long(v + 120)
            return m.long(msg + 0x4C) if ok(msg) else None
        node = m.long(node)
    return None


def fed_ticks(r, n):
    for _ in range(n):
        if r.fed_tick % 5 == 0:
            r.feed(r.fed_tick // 5)
        r.fed_tick += 1
        r.run_ticks(1)


def message_out(r, limit_ticks=121 * 10):
    """the scope page's title, posted as stock's message (amp_open: "WAVEFORM"), runs out on stock's clock (~3.7 s
    after the page opens). Until 2026-11-18 the glass kept it (frames drawn alone never touch the bar; measured, 12 s
    unchanged) until something else asked for a full redraw. -> the ticks until it ran out, or None"""
    for k in range(limit_ticks):
        left = message_left(r)
        if left == 0:
            return k
        if left is None:
            return None
        fed_ticks(r, 1)
    return None


def identity(r, fails, what, png=True):
    """a full redraw forced now (stock's dirty byte) must draw exactly the frame on the glass"""
    if not r.screen:
        fails.append(f"{what}: no screen object seen")
        return
    back = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    n0, s0 = len(r.panel.capture.frames), r.stats["screens"]
    r.m.write(r.screen + 32, b"\x01")
    r.panel.settle(30_000_000)                  # (the ring is not fed meanwhile: every frame draws the same)
    drawn = bytes(r.panel.capture.frames[-1]) if len(r.panel.capture.frames) > n0 else None
    r.identities += 1
    if r.stats["screens"] == s0:
        fails.append(f"{what}: the full redraw asked for did not run")
    if drawn != back:
        diff = [i for i in range(1024) if drawn is None or drawn[i] != back[i]]
        fails.append(f"{what}: a full redraw differs from the glass in {len(diff)} bytes "
                     f"(columns {sorted({i // 8 for i in diff})[:6]})")
        if png:
            tag = "".join(ch if ch.isalnum() else "_" for ch in what)[:40]
            r.panel.panel.write_png(back, str(pathlib.Path(r.a.work) / f"proof_{tag}_glass.png"))
            if drawn:
                r.panel.panel.write_png(drawn, str(pathlib.Path(r.a.work) / f"proof_{tag}_full.png"))


def alone_fails(r, since=0):
    """the frames drawn alone since SINCE that differ from their full draw's frame with the model's strip"""
    return [f"frame drawn alone {i}: {f[0]}" for i, f in enumerate(r.alone_checks[since:], since) if f]


def proof(r, rep):
    """the title's message runs out and the bar shows its own title again; every scope frame's strip as v1 drew it
    (at the gain it was drawn at); every frame drawn alone the last full draw's frame but for the strip; every eighth
    frame, a full redraw the same as the glass"""
    fails, frames_seen = [], 0
    r.identities = 0
    if "wr_screen_obj" in r.sym:
        went = message_out(r)
        rep["title_message_ticks"] = went
        print(f"    the title's message ran out after {went} ticks", flush=True)
        if went is None:
            fails.append("the page title's message never ran out (or its line was not found)")
        else:
            fed_ticks(r, 40)                    # (two frames or more: the title must be back without being asked)
            r.panel.panel.write_png(bytes(r.m.read(r.m.long(FB_BACK), 1024)), str(pathlib.Path(r.a.work) / "title_after.png"))
            identity(r, fails, "the title's message ran out")
    last_alone = r.m.long(r.sym["scope_alone"])
    for _step in range(int(121 * 4)):
        fed_ticks(r, 1)
        n = r.m.long(r.sym["scope_alone"])
        if n != last_alone:                                 # a frame drawn alone (in the poll, on the ring now)
            last_alone = n
            ring = list(struct.unpack(f">{RING}h", bytes(r.m.read(r.sym["scope_ring"], 2 * RING))))
            pos = r.m.long(r.sym["scope_pos"])
            back = bytes(r.m.read(r.m.long(FB_BACK), 1024))
            want, got = model_strip(ring, pos, r.gain_k()), back_strip(back)
            frames_seen += 1
            if want != got:
                fails.append(f"frame {frames_seen}: strip differs from v1's drawing in {len(want ^ got)} pixels")
            if frames_seen % 8 == 0:                        # every eighth: a full redraw must draw this very frame
                identity(r, fails, f"frame {frames_seen}")
                last_alone = r.m.long(r.sym["scope_alone"])
    alone = alone_fails(r)
    fails += alone
    rep["proof"] = {"frames_checked": frames_seen, "full_redraws_compared": r.identities,
                    "alone_frames_checked": len(r.alone_checks), "alone_fails": len(alone), "fails": fails[:10],
                    "alone": r.m.long(r.sym["scope_alone"]), "dropped": r.m.long(r.sym["scope_dropped"])}
    print(f"    proof: {json.dumps(rep['proof'])}", flush=True)
    return not fails and frames_seen >= 30 and r.identities >= 5 and rep["proof"]["alone"] > 0 and len(r.alone_checks) >= 30


GAINS, GAIN_X1, HOLD = 8, 3, 8                  # scope.c: x1/8..x16 then AUTO; ZOOM_IN_HOLD frames
EDGE_ROWS = (MID - HALF, MID + HALF)
LABEL_X0, LABEL_X1 = 74, 98                     # G's label (wg_label slot 6: centred at x 85, rows 0..7)
GAIN_NAMES = ["x1/8", "x1/4", "x1/2", "x1", "x2", "x4", "x8", "x16", "AUTO"]


def next_frames(r, n, limit_ticks=121 * 6):
    """run until N more frames are drawn alone: -> [(scope_gain, scope_auto, strip, model k, edge pixels)]"""
    out, last, seen = [], r.m.long(r.sym["scope_alone"]), len(r.alone_seen)
    for _ in range(limit_ticks):
        if len(out) >= n:
            break
        if r.fed_tick % 5 == 0:
            r.feed(r.fed_tick // 5)
        r.fed_tick += 1
        r.run_ticks(1)
        a = r.m.long(r.sym["scope_alone"])
        if a == last:
            continue
        last = a
        # 2026-11-19: every frame drawn alone in this tick, as it went to panel_diff, against the model at the gain
        # it was drawn at (sampled at the end of the tick, a G turn landing after the frame had already moved the gain
        # or reset AUTO's choice: "gain x8: the strip differs" for a frame drawn at x16); the tick's entry is its last
        drawn, seen = r.alone_seen[seen:], len(r.alone_seen)
        if not drawn:                           # (never seen: every frame drawn alone goes through panel_diff)
            out.append((-1, -1, False, 0, 0, b"", r.scope_draws() if hasattr(r, "scope_draws") else 0))
            continue
        same = all(back_strip(f) == model_strip(rg, ps, kk) for _g, _a, rg, ps, kk, f in drawn)
        gain, auto, _ring, _pos, k, frame = drawn[-1]
        got = back_strip(frame)
        edge = sum(1 for x, y in got if X0 <= x < X0 + SHOWN and y in EDGE_ROWS)
        out.append((gain, auto, same, k, edge, frame[8 * LABEL_X0:8 * LABEL_X1:8],
                    r.scope_draws() if hasattr(r, "scope_draws") else 0))
    return out


def autozoom(r, rep):
    """the gains below x1 and AUTO's choice among all of them (scope.c, 2026-11-17)"""
    fails, steps = [], []
    for need in ("scope_gain", "scope_auto"):
        if need not in r.sym:
            rep["autozoom"] = {"fails": [f"{need} not in the build's layout"]}
            return False
    r.a.feed = "sine"
    seen = set()
    labels = {}
    n_alone0 = len(r.alone_checks)
    # every frame the scope draws, alone or in a full redraw, runs AUTO's choice (scope.c auto_gain);
    # next_frames sees only the ones drawn alone, so the hold is counted in all of them (2026-11-18: a full
    # redraw in the quiet window, after AMP entered its page on the press, made it look one frame short): the full
    # draws' scope_draw calls (not the ones from scope_poll: v1 drew its frames alone through it too) and scope_alone
    # (since 2026-11-18 a frame drawn alone does not call scope_draw)
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    r.scope_full = 0
    poll = r.sym["scope_poll"]

    def on_draw(uc, ad, sz, us):
        ret = r.m.long(uc.reg_read(K.UC_M68K_REG_A7))
        if not poll <= ret < poll + 0x400:
            r.scope_full += 1
    r.m.uc.hook_add(UC_HOOK_CODE, on_draw, begin=r.sym["scope_draw"], end=r.sym["scope_draw"])
    r.m.flush()                                         # (a code hook sees only blocks translated after it)
    r.scope_draws = lambda: r.scope_full + r.m.long(r.sym["scope_alone"])            # noqa: E731

    def turn(delta):
        r.turn_g(delta)
        fr = next_frames(r, 2)
        if not fr:
            fails.append(f"G {delta:+d}: no frame drawn alone")
            return None
        g = fr[-1][0]
        seen.add(g)
        steps.append(GAIN_NAMES[g])
        labels[g] = fr[-1][5]
        for gg, au, same, k, _edge, _lab, _n in fr:
            if not same:
                fails.append(f"gain {GAIN_NAMES[gg]} (x2^{k}): the strip differs from the model")
        return g
    g0 = struct.unpack(">i", r.m.read(r.sym["scope_gain"], 4))[0]
    if g0 != GAINS:                                     # 2026-11-18 (the User: "auto should be default")
        fails.append(f"the gain starts at {GAIN_NAMES[g0] if 0 <= g0 <= GAINS else g0}, not AUTO")
    if turn(+1) != GAINS:
        fails.append("G up past AUTO left AUTO")
    for want in range(GAINS - 1, -1, -1):               # down through x16 to x1/8
        if turn(-1) != want:
            fails.append(f"G down: {steps[-1:]} where {GAIN_NAMES[want]} was due")
        if want in (GAINS - 1, GAIN_X1, 0):
            identity(r, fails, f"gain {GAIN_NAMES[want]}")
    if turn(-1) != 0:
        fails.append("G down past x1/8 left x1/8")
    for want in range(1, GAINS + 1):                    # up through x16 to AUTO
        if turn(+1) != want:
            fails.append(f"G up: {steps[-1:]} where {GAIN_NAMES[want]} was due")
    if seen != set(range(GAINS + 1)):
        fails.append(f"gains reached {sorted(seen)}, not all of 0..{GAINS}")
    # AUTO, a full-scale signal: below x1 at once, never on an edge row, steady
    r.a.feed = "loud"
    loud = next_frames(r, 24)
    autos = [f[1] for f in loud]
    if not loud or autos[-1] >= GAIN_X1:
        fails.append(f"AUTO on full scale took {[GAIN_NAMES[a] for a in autos[-1:]]}, not below x1")
    flips = sum(1 for a, b in zip(autos[4:], autos[5:]) if a != b)
    if flips:
        fails.append(f"AUTO on a steady full-scale signal changed {flips} times")
    identity(r, fails, "AUTO loud")
    for i, (gg, au, same, k, edge, _lab, _n) in enumerate(loud):
        if edge:
            fails.append(f"AUTO full scale, frame {i}: {edge} trace pixels on an edge row")
        if not same:
            fails.append(f"AUTO full scale, frame {i}: the strip differs from the model at x2^{k}")
    # quiet: back up to x16, only after the hold
    r.a.feed = "quiet"
    d0 = r.scope_draws()
    quiet = next_frames(r, 40)
    qa = [f[1] for f in quiet]
    rise = next((i for i, a in enumerate(qa) if a > autos[-1]), None) if loud else None
    if not qa or qa[-1] != GAINS - 1:
        fails.append(f"AUTO on a quiet signal ended at {[GAIN_NAMES[a] for a in qa[-1:]]}, not x16")
    rise_draws = quiet[rise][6] - d0 if rise is not None else None
    if rise is not None and rise_draws < HOLD:
        fails.append(f"AUTO zoomed in after {rise_draws} frames drawn, before its hold of {HOLD}")
    if any(not f[2] for f in quiet):
        fails.append("AUTO quiet: a strip differs from the model")
    identity(r, fails, "AUTO quiet")
    # loud again: out on the first frame that shows it, never an edge pixel
    r.a.feed = "loud"
    again = next_frames(r, 12)
    edges = [f[4] for f in again]
    if any(edges):
        fails.append(f"AUTO loud again: trace pixels on an edge row {edges}")
    if not again or again[-1][1] >= GAIN_X1:
        fails.append("AUTO loud again did not go below x1")
    next_frames(r, 6)
    identity(r, fails, "AUTO loud again")
    fails += alone_fails(r, n_alone0)
    # AUTO's label (2026-11-18, the User: "just put 'auto', not A4 A8 etc"): the same pixels whatever gain AUTO took,
    # and none of a manual gain's label
    auto_labels = {f[5] for f in loud + quiet + again if f[0] == GAINS} | ({labels[GAINS]} if GAINS in labels else set())
    took = {f[1] for f in loud + quiet + again if f[0] == GAINS}
    if len(auto_labels) != 1:
        fails.append(f"AUTO's label changed with its gain ({len(auto_labels)} different labels over gains {sorted(took)})")
    elif len(took) < 2:
        fails.append(f"AUTO took only gains {sorted(took)}: its label was not seen at two gains")
    if auto_labels and any(labels.get(g) in auto_labels for g in range(GAINS)):
        fails.append("AUTO's label is a manual gain's label")
    if len({labels.get(g) for g in range(GAINS) if g in labels}) != len([g for g in range(GAINS) if g in labels]):
        fails.append("two manual gains share a label")
    rep["autozoom"] = {"auto_label_gains": sorted(took), "auto_labels": len(auto_labels), "steps": steps, "loud_auto": [GAIN_NAMES[a] for a in autos],
                       "quiet_auto": [GAIN_NAMES[a] for a in qa], "quiet_zoom_in_frame": rise, "quiet_zoom_in_draws": rise_draws,
                       "again_auto": [GAIN_NAMES[f[1]] for f in again], "again_edge_pixels": edges, "fails": fails[:12]}
    print(f"    autozoom: {json.dumps(rep['autozoom'])}", flush=True)
    return not fails


TRK, TRIG = (1, 7), [(3 + k // 8, k % 8) for k in range(16)]      # codes 16, 25..40 (emu_coupled_stocknote)
ENC_SPAN = 7                                    # encoder H: the time span (any encoder but G)


def state(r):
    """the scope's settings: (gain, span)"""
    return (struct.unpack(">i", r.m.read(r.sym["scope_gain"], 4))[0],
            struct.unpack(">i", r.m.read(r.sym["scope_zoom"], 4))[0] if "scope_zoom" in r.sym else None)


def change_track(r, n):
    """TRK held, TRIG N (1-based), TRK let go"""
    r.panel.hold(TRK, 3_000_000)
    r.panel.tap(TRIG[n - 1], after=2_000_000)
    r.panel.let_go(TRK, 3_000_000)
    r.run_ticks(30)


def title_back(r, fails, what):
    """2026-11-21 (the gate gap "the scope page's expired title stays on screen"): after WHAT, the title bar's message
    (if one is up) runs out, two frames or more pass with nothing asked, and a full redraw then draws exactly the glass
    (stock's bar draws its own title again only in a full draw: a glass still showing the message fails here).
    Control: when a message was up, the glass while it was must differ from the glass after in the title bar (rows
    56..63), so the comparison above would see a title left standing. -> the ticks the message took, or None"""
    left = message_left(r)
    stale = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    went = message_out(r)
    if went is None and message_left(r) is not None:
        fails.append(f"{what}: the title's message never ran out")
        return None
    fed_ticks(r, 40)
    next_frames(r, 2)                           # (the glass then a frame of the ring as it is: as sequences() does)
    identity(r, fails, f"{what}, the title's message run out")
    r.title_checks = getattr(r, "title_checks", 0) + 1
    if left:
        now = bytes(r.m.read(r.m.long(FB_BACK), 1024))
        bar = [i for i in range(1024) if i % 8 == 7 and stale[i] != now[i]]
        if not bar:
            fails.append(f"{what}: (control) the glass with the message up is the glass after it in the title bar: "
                         "a title left standing would not be seen")
        r.title_controls = getattr(r, "title_controls", 0) + bool(bar)
    print(f"    {what}: message left {left}, ran out after {went} ticks", flush=True)
    return went


def area(r, rep):
    """2026-11-21 (scripts/scope_area.py): every write the scope's code made in the runs before (the proof, autozoom,
    the sequences, the keys) in its place; then the control: a stub's writes outside it at the next full draw, seen"""
    w = r.area
    if w is None:
        rep["area"] = {"fails": ["no write watch (the build's C chunk or scope_poll unknown)"]}
        print("    area: FAIL no write watch", flush=True)
        return False
    fails = list(w.fails)
    counts = dict(w.counts)
    if counts["draws"] < 20 or counts["alone"] < 20:
        fails.append(f"too few windows watched: {counts}")
    w.control()
    if not r.up():
        r.open_scope()
    if r.screen:
        r.m.write(r.screen + 32, b"\x01")       # a full draw asked (stock's dirty byte)
    for _ in range(60):
        r.run_ticks(1)
        if w.control_seen is not None and w.win is None:
            break
    seen_both, reported = w.control_result()
    if not seen_both:
        fails.append(f"control: a write of free RAM and a pixel at column 2 in scope_draw not both seen ({reported})")
    rep["area"] = {"windows": counts, "stock PCs": sorted(hex(p) for p in w.stock_pcs)[:12], "fails": fails[:10],
                   "control": reported[:8]}
    print(f"    area: {json.dumps(rep['area'])}", flush=True)
    return not fails


def sequences(r, rep):
    """2026-11-18: the settings the User set kept over a page change and a track change (the same for every track),
    and after each, the glass a full redraw draws"""
    fails = []
    n0 = len(r.alone_checks)
    r.a.feed = "sine"
    r.turn_g(-1)                                # AUTO -> x16 (or wherever autozoom left it: one detent down)
    r.run_fed(20)
    r.panel.m.pc = r.panel.panelin.encoder(r.m.m, r.panel.profile, ENC_SPAN, 1)
    r.run_fed(20)
    want = state(r)
    next_frames(r, 4)
    identity(r, fails, "gain and span set")
    title_back(r, fails, "gain and span set")
    r.tap(SYN)                                  # page out
    if r.m.long(r.sym["scope_up"]):
        fails.append("SYN did not close the scope page")
    if not r.open_scope():
        fails.append("the scope page did not open again")
    next_frames(r, 4)
    if state(r) != want:
        fails.append(f"page out and in: settings {state(r)}, not {want}")
    identity(r, fails, "page out and in")
    title_back(r, fails, "page out and in")
    change_track(r, 2)
    up = r.m.long(r.sym["scope_up"])
    if not up and not r.open_scope():
        fails.append("the scope page did not open on track 2")
    track = r.m.read(EM.UI_TRACK, 1)[0]
    next_frames(r, 4)
    if state(r) != want:
        fails.append(f"track change: settings {state(r)}, not {want}")
    identity(r, fails, "track change")
    title_back(r, fails, "track change")
    change_track(r, 1)
    if not r.m.long(r.sym["scope_up"]):
        r.open_scope()
    next_frames(r, 4)
    identity(r, fails, "track 1 again")
    title_back(r, fails, "track 1 again")
    fails += alone_fails(r, n0)
    rep["sequences"] = {"settings": want, "track_after_change": track, "scope_up_after_trk": up, "fails": fails[:10]}
    print(f"    sequences: {json.dumps(rep['sequences'])}", flush=True)
    return not fails


def views(r):
    """the classes (vtables) of the screen's views, as ins.c view_of walks them"""
    m = r.m
    ok = lambda a: 0x40000000 <= a < 0x48000000 and not a & 3                    # noqa: E731
    s = m.long(r.sym["wr_screen_obj"])
    out, node = [], m.long(s + 28) if ok(s) else 0
    for _ in range(32):
        if not ok(node) or node == s + 20:
            break
        v = m.long(node + 8)
        if ok(v):
            out.append(m.long(v))
        node = m.long(node)
    return out


def body(r):
    """the glass below the title bar: rows 0..47 of every column (bytes 0..5 of its 8; y counts up from the bottom)"""
    b = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    return bytes(b[8 * x + k] for x in range(128) for k in range(6))


def trig_keys(r, rep):
    """2026-11-19 (the User): the scope opens on a long press of the [TRIG] page key (held a second, as the page keys'
    overviews), over stock's TRIG page, and stays up until another page is chosen; a short press is stock's TRIG page,
    unchanged (stock enters it on the press from another page and steps 1/2 <-> 2/2 on a tap's release on it; held, it
    shows its values and steps nothing). The scope is no longer an AMP page: [AMP] steps AMP 1/2 (stock's) -> 2/2 (ENV2)
    -> 1/2. FUNC + [TRIG] stays stock's QUANTIZE; a knob turned while [TRIG] is held cancels the long press"""
    fails, log = [], []
    n0 = len(r.alone_checks)
    amp_sub = lambda: r.m.long(r.sym["amp_sub"])                                  # noqa: E731

    def note(what, ok, detail=""):
        log.append(f"{'ok' if ok else 'FAIL'} {what}")
        if not ok:
            fails.append(f"{what}{': ' + detail if detail else ''}")

    def tap(key, hold=8):
        r.press(key, hold)
        r.release(key, 40)

    # NO closes the scope; under it, stock's TRIG page
    if not r.up():
        r.open_scope()
    note("the scope up before the keys' checks", r.up())
    tap(NO_KEY)
    note("NO closes the scope", not r.up() and amp_sub() == 0, f"scope_up {r.up()} amp_sub {amp_sub()}")
    note("under it, stock's TRIG page", TRIG_VIEW in views(r), f"views {[hex(v) for v in views(r)]}")
    t1 = body(r)
    # a short press on TRIG's page: stock's step on the release, both ways, never the scope
    r.press(TRIGK, 6)
    same_on_press = body(r) == t1
    r.release(TRIGK, 40)
    t2 = body(r)
    note("a tap on TRIG's page: nothing moves on the press (stock steps on the release)", same_on_press)
    note("a tap on TRIG's page: stock's other TRIG page on the release, no scope", t2 != t1 and not r.up()
         and TRIG_VIEW in views(r))
    tap(TRIGK)
    note("a second tap: TRIG's first page again", body(r) == t1 and not r.up())
    # from another page: stock's TRIG page on the press
    tap(SYN)
    note("SYN's page", SYN_VIEW in views(r) and not r.up())
    r.press(TRIGK, 6)
    note("[TRIG] from SYN: stock's TRIG page on the press", TRIG_VIEW in views(r) and not r.up(),
         f"views {[hex(v) for v in views(r)]}")
    r.release(TRIGK, 40)
    t_from = body(r)
    note("[TRIG] from SYN let go: still TRIG's page, no scope", TRIG_VIEW in views(r) and not r.up())
    # held 0.6 s: stock's values, no scope, no step on the release
    r.press(TRIGK, 73)
    note("[TRIG] held 0.6 s: no scope", not r.up())
    r.release(TRIGK, 40)
    note("[TRIG] held 0.6 s, let go: no scope, no step", not r.up() and body(r) == t_from)
    # held a second: the scope, over stock's TRIG page; it stays after the release
    r.press(TRIGK, LONG - 12)
    early = r.up()
    r.run_fed(36)
    held = r.up()
    note("[TRIG] held: no scope before a second", not early)
    note("[TRIG] held a second: the scope up", held and amp_sub() == AMP_SCOPE, f"scope_up {held} amp_sub {amp_sub()}")
    r.release(TRIGK, 40)
    note("[TRIG] let go after the long press: the scope stays up, over TRIG's page",
         r.up() and TRIG_VIEW in views(r))
    next_frames(r, 3)
    identity(r, fails, "opened by a long [TRIG]")
    # [TRIG] tapped while up: closed, TRIG's page as it was (no step)
    tap(TRIGK)
    note("[TRIG] tapped while up: the scope closes, TRIG's page as it was (no step)", not r.up() and body(r) == t_from,
         f"scope_up {r.up()}")
    # page keys leave
    for name, key, view in (("SYN", SYN, SYN_VIEW), ("AMP", AMP, AMP_VIEW), ("FX", FX, None)):
        note(f"long [TRIG] before {name}", r.open_scope())
        r.press(key, 6)
        on_press = r.up()
        r.release(key, 40)
        note(f"{name} while up: the scope closes on the press", not on_press and not r.up())
        if view:
            note(f"{name} while up: stock's {name} page", view in views(r), f"views {[hex(v) for v in views(r)]}")
        if name == "AMP":
            note("AMP while up: AMP 1/2 (stock's AMP page, none of ours)", amp_sub() == 0, f"amp_sub {amp_sub()}")
    # [AMP]: two pages, stock's and ENV2's, never the scope
    tap(AMP)
    seen = []
    for _ in range(4):
        tap(AMP)
        seen.append((amp_sub(), r.up(), AMP_VIEW in views(r)))
    note("[AMP] steps AMP 1/2 -> 2/2 -> 1/2, never the scope",
         seen == [(1, False, True), (0, False, True), (1, False, True), (0, False, True)], f"(amp_sub, scope, AMP view) {seen}")
    tap(AMP)                                            # ENV2 up: a long [TRIG] closes it and opens the scope
    note("ENV2 up", amp_sub() == 1)
    note("a long [TRIG] from ENV2: the scope", r.open_scope() and TRIG_VIEW in views(r))
    tap(NO_KEY)
    # FUNC + [TRIG] held: stock's QUANTIZE, never the scope
    tap(SYN)
    r.press(FUNC, 10)
    r.press(TRIGK, LONG + 30)
    quant = QUANT_VIEW in views(r)
    up = r.up()
    r.release(TRIGK, 20)
    r.release(FUNC, 40)
    note("FUNC + [TRIG] held: stock's QUANTIZE, no scope", quant and not up and not r.up(),
         f"views {[hex(v) for v in views(r)]} scope {up}")
    tap(NO_KEY)
    if QUANT_VIEW in views(r):
        tap(NO_KEY)
    # a knob turned while [TRIG] is held: no scope
    tap(SYN)
    r.press(TRIGK, 30)
    r.turn_g(1)
    r.run_fed(LONG)
    up = r.up()
    r.release(TRIGK, 40)
    note("[TRIG] held, a knob turned, held on past a second: no scope", not up and not r.up())
    fails += alone_fails(r, n0)
    rep["trig_keys"] = {"log": log, "fails": fails[:12]}
    print(f"    trig_keys: {json.dumps(rep['trig_keys'])}", flush=True)
    return not fails


# -- the settings kept over a power-off (jump.c's settings sector, csrc/scope/scope.c) ---------------------------------
BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS = 0x4012C87A, 0x4012CA60, 0x4461C68C, 0x4461C6B0
SET_SECTOR, SET_MAGIC, SET_VERSION = 0x6FF000, 0x444E3253, 1
BOOT_FLAGS = 0x40287A60                         # bit 1: the startup menu's FACTORY RESET (jump.c)


def sector(bits):
    """a good settings sector holding flags BITS (jump.c's layout and check)"""
    w = [SET_MAGIC, SET_VERSION, bits & 0xFFFFFFFF, 0] + [0] * 124
    w[3] = (~w[0] ^ w[1] ^ w[2]) & 0xFFFFFFFF
    return struct.pack(">128I", *w)


def disk_rig(a, lay, work, disk, factory=False):
    """a power-on: the snapshot afresh, the +Drive served from DISK (sector -> 512 bytes; the emulator's own device is
    15 MB and reads zeros), the UI loop reading the settings sector as it does at boot"""
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    r = Rig(a, lay, work)
    m = r.m
    io = {"reads": [], "writes": []}

    def blk(uc, address, size, user):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        sec, n, buf = struct.unpack(">3I", bytes(uc.mem_read(sp + 4, 12)))
        if address == BLK_READ:
            io["reads"].append(sec)
            uc.mem_write(buf, b"".join(disk.get(sec + k, bytes(512)) for k in range(n // 512)))
        else:
            io["writes"].append(sec)
            data = bytes(uc.mem_read(buf, n))
            for k in range(n // 512):
                disk[sec + k] = data[512 * k:512 * k + 512]
    for va in (BLK_READ, BLK_WRITE):
        m.write(va, bytes.fromhex("70004e75"))          # moveq #0,%d0 ; rts: the hook does the work
        m.uc.hook_add(UC_HOOK_CODE, blk, begin=va, end=va)
    for name, n in (("jmp_loaded", 4), ("jmp_dirty", 1), ("set_bits", 4), ("scope_set_taken", 4)):
        m.write(lay[name], bytes(n))            # as the loader leaves them (.data), the sector not read yet
    if factory:
        m.write(BOOT_FLAGS, struct.pack(">I", m.long(BOOT_FLAGS) | 2))
    m.write(BLK_READY, struct.pack(">I", 1))
    m.write(BLK_SECTORS, struct.pack(">I", 0x3A00000))
    m.flush()
    r.io = io
    for _ in range(40):                         # the UI loop reads the sector, scope.c takes its values
        r.run_ticks(5)
        if m.long(lay["jmp_loaded"]) and m.long(lay["scope_set_taken"]):
            break
    return r


def persist(a, lay, work, rep):
    """2026-11-18 (the User: "auto should be default for oscilator and we should rfememebr the values set for it"):
    AUTO and 8 ms with no sector, a bad one or values out of range; the gain and the span set on the page are written
    to the settings sector (once, not a write a detent) and come back after a power-on, the page's own pixels with
    them; a FACTORY RESET keeps them, as it keeps DIRECT JUMP, LIVE SELECT and the VOICE BUDGET (jump.c)"""
    fails, out = [], {}
    default = (GAINS, 2)

    def boot(name, disk, factory=False):
        r = disk_rig(a, lay, work, disk, factory)
        st = state(r)
        out[name] = {"settings": [GAIN_NAMES[st[0]] if 0 <= st[0] <= GAINS else st[0], st[1]],
                     "set_bits": f"{r.m.long(lay['set_bits']):#x}", "taken": r.m.long(lay["scope_set_taken"])}
        if not r.m.long(lay["scope_set_taken"]):
            fails.append(f"{name}: the stored settings were never taken")
        return r, st

    disk = {}
    r, st = boot("no sector", disk)
    if st != default:
        fails.append(f"no sector: {st}, not AUTO and 8 ms")
    EM.ours_machine(r.m, r.panel, 1)
    r.tap(SYN)
    if not r.open_scope():
        fails.append("the scope page did not open")
    w0 = len(r.io["writes"])
    for _ in range(3):                          # G three detents: AUTO -> x16 -> x8 -> x4
        r.turn_g(-1)
        r.run_fed(3)
    r.panel.m.pc = r.panel.panelin.encoder(r.m.m, r.panel.profile, ENC_SPAN, 1)
    r.run_fed(3)                                # the span: 8 -> 17 ms
    # 2026-11-19: the UI takes the turn once it is out of the page draw the gain turns asked for (it waits there on
    # the panel UART); measured on 3c0ef6a8 it landed on the 4th tick (33 ms), on 91c8a9d3 on the 3rd. Waited for
    # here, up to a second; a turn that never lands still fails below
    span_ticks = 3
    while state(r)[1] == 2 and span_ticks < 121:
        r.run_fed(1)
        span_ticks += 1
    out["span_landed_ticks"] = span_ticks
    want = state(r)
    if not (0 <= want[0] < GAINS and want[1] == 3):
        fails.append(f"the turns gave {want}: not a manual gain and 17 ms")
    early = len(r.io["writes"]) - w0
    r.run_fed(121 * 2)                          # a second after the last turn: written
    writes = len(r.io["writes"]) - w0
    out["writes_during_turns"], out["writes_after"] = early, writes
    if early or writes != 1:
        fails.append(f"settings writes: {early} during the turns, {writes} in all (one wanted, after them)")
    shot_set = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    r.panel.panel.write_png(shot_set, str(pathlib.Path(work) / "persist_set.png"))
    r.tap(SYN)
    change_track(r, 3)
    r.open_scope()
    if state(r) != want:
        fails.append(f"page and track change: {state(r)}, not {want}")
    good = disk.get(SET_SECTOR)
    out["sector"] = good[:16].hex() if good else None
    if not good or good[:8] != struct.pack(">II", SET_MAGIC, SET_VERSION):
        fails.append("the settings sector was not written")
    del r
    gc.collect()
    r, st = boot("power-on", dict(disk))
    if st != want:
        fails.append(f"power-on: {st}, not {want}")
    EM.ours_machine(r.m, r.panel, 1)
    r.tap(SYN)
    r.open_scope()
    r.run_fed(121)
    glass = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    r.panel.panel.write_png(glass, str(pathlib.Path(work) / "persist_after_power_on.png"))
    if glass[8 * LABEL_X0:8 * LABEL_X1:8] != shot_set[8 * LABEL_X0:8 * LABEL_X1:8]:
        fails.append("power-on: G's label is not the one set before")
    del r
    bits = struct.unpack(">I", good[8:12])[0] if good else 0
    bad = bytearray(good or sector(0))
    bad[15] ^= 0x5A                             # the check word broken
    gc.collect()
    for name, dk, fac, exp in (("bad check", {SET_SECTOR: bytes(bad)}, False, default),
                               ("gain out of range", {SET_SECTOR: sector((bits & ~0x7F0) | 12 << 4 | 7 << 8)}, False,
                                default),
                               ("factory reset", {SET_SECTOR: sector(bits | 4)}, True, want)):
        r, st = boot(name, dk, fac)
        if st != exp:
            fails.append(f"{name}: {st}, not {exp}")
        if name == "factory reset" and not r.m.long(lay["set_bits"]) & 4:
            fails.append("factory reset: LIVE SELECT's bit not kept beside ours")
        del r
        gc.collect()
    out["fails"] = fails[:10]
    rep["persist"] = out
    print(f"    persist: {json.dumps(out)}", flush=True)
    return not fails


def shot(r, a, work):
    """AUTO (or G A.TURNS detents from x1), a full-scale signal, the glass as WORK/NAME.png"""
    for _ in range(abs(a.turns)):
        r.turn_g(1 if a.turns > 0 else -1)
        r.run_fed(20)
    a.feed = "loud"
    r.run_fed(121 * 2)
    back = bytes(r.m.read(r.m.long(FB_BACK), 1024))
    path = work / f"{a.shot}.png"
    r.panel.panel.write_png(back, str(path))
    edge = sum(1 for x, y in back_strip(back) if X0 <= x < X0 + SHOWN and y in EDGE_ROWS)
    print(f"    shot {path}: {edge} trace pixels on the strip's top and bottom rows", flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--seconds", type=float, default=3.0)
    p.add_argument("--uart", choices=("real", "instant"), default="real")
    p.add_argument("--feed", choices=("sine", "noise", "loud", "quiet"), default="sine")
    p.add_argument("--shot", help="save the glass of AUTO on a full-scale signal as WORK/SHOT.png (no checks)")
    p.add_argument("--turns", type=int, default=0, help="--shot: G detents from the build's first gain (AUTO since "
                   "2026-11-18; v1's x1: 5 for AUTO)")
    p.add_argument("--layout", help="another build's waverider_code.json (--shot of v1)")
    p.add_argument("--proof", action="store_true", help="the frames byte for byte (the gate step)")
    a = p.parse_args()
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    code_json = json.loads(pathlib.Path(a.layout or HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())
    lay = code_json["layout"]
    cc = code_json.get("c_chunk") or {}
    a.chunk = ((cc["load"], cc["load"] + len(cc["code"]) // 2)          # (scope_area: the C chunk, scope.c's state in it;
               if a.proof and "load" in cc else None)                   # its code a hex string)
    for need in ("scope_draw", "scope_ring", "scope_pos", "scope_up", "smp_ui_pop", "wr_screen"):
        if need not in lay:
            print(f"FAIL: {need} not in the build's layout")
            return 1
    r = Rig(a, lay, work)
    rep = {"uart": a.uart, "feed": a.feed}
    if not EM.ours_machine(r.m, r.panel, 1):
        print("FAIL: track 1 to WaveTone")
        return 1
    r.tap(SYN)
    rep["syn"] = measure(r, "SYN page (no scope)", a.seconds)
    ok = r.open_scope()
    print(f"    scope up: {ok}", flush=True)
    if not ok:
        print("FAIL: the scope page did not open")
        return 1
    if a.shot:
        shot(r, a, work)
        return 0
    if a.proof:
        good = proof(r, rep)
        good = autozoom(r, rep) and good
        good = sequences(r, rep) and good
        good = trig_keys(r, rep) and good
        good = area(r, rep) and good          # (last on this rig: its control leaves a pixel on the glass)
        if "scope_set_taken" in lay:
            del r
            gc.collect()
            good = persist(a, lay, work, rep) and good
        else:
            rep["persist"] = {"fails": ["scope_set_taken not in the build's layout"]}
            good = False
        (work / "scope.json").write_text(json.dumps(rep, indent=1))
        print("SCOPE OK" if good else "SCOPE FAILED")
        return 0 if good else 1
    rep["scope"] = measure(r, "scope page", a.seconds)
    (work / "scope.json").write_text(json.dumps(rep, indent=1))
    print("SCOPE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
