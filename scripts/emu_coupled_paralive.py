"""paralive: PARA chords played live on the KEYBOARD, through the ColdFire's own UI, ISR and allocator, OS 1.12
(2026-11-18; the unit, v0.59.1: stale chords, members ending a frame after they joined, key-ups that never released a
member; docs/paraphonic-onevoice.md section 10).

Track 3 plays ANALOG 2 (MACHINE SEL's commit) with PARA ON, KEYBOARD on; the trig keys 9..16 (one panel group) are
the notes. The ColdFire runs alone (the coupled harness with dsp=False: the UI, the sequencer and the audio ISR are
the build's own); the DSP's telemetry (its per-slot cost, link.c smp_tlm_cost, and when it came, smp_room_at) is the
one stand-in, written here as an idle packet would write it (check C). Checks, each a FAIL on main f9d570db:

 A  joins: N keys (3, 4, 6, 8) pressed 0, 1, 5 and 20 ms apart (0: one panel message with every key): one chord start
    and N - 1 joins, N notes in the chord's places, every one sounding; after 30 periods held every place still HELD
    (main: the joined notes' HELD went at the next frame: pv_final's "no key held" test read stock's ARP key list)
 B  key-up: a member's key up: that place alone ends (pv_rels + 1), the chord held, no note-off; the leader's key up:
    the chord held, the leader's note-off kept back; the last key up: the chord's note-off goes out (pv_kept clear),
    nothing held, the track's next note starts a new chord
 C  the end: a chord with nothing held stays live for the DSP (its row unchanged) while the DSP reports its slot
    sounding (a release tail), and ends (live 0, its row zero) once a report that came after the release says it is
    quiet (main: live forever, its row read every frame)
 D  pv_dirty: gone (main: 0xFFFF, set and never read or cleared)
 E  the ARP's key list: no ARP, so stock's list (0x4059D868, what 0x4002a3a6 reads) stays empty with keys held (the
    cause of A, measured)
--dsp: the DSP too (the coupled harness's DSP block, its own telemetry): one 3-note chord held, its keys up, the chord
must end by the DSP's own report, its shadows' pool blocks all free again (about 11 s a period: one chord only).
--measure: the audio ISR's instructions a frame (every instruction, by function) at rest after the chords, and with
4 and 16 chords held (the chord table written as N held chords of 4 / 8 notes before every frame: the same state each
frame, on main and on the fix).

Usage (bench, the build's own snapshot):
  python -u scripts/emu_coupled_paralive.py --build X.syx --stock 1.12.syx --snapshot S [--measure] [--json OUT]"""

from __future__ import annotations

import argparse
import bisect
import collections
import importlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
SN = importlib.import_module("emu_coupled_stocknote")       # its smoother model, keys and addresses
EC = importlib.import_module("emu_coupled")

TRACK = 2                                    # track 3 (the gate's parachord track: Multimode filter)
A2 = 51
MOD_AT = 20 + 2 * 37                         # the sound's MOD (PARA) value
ARP_AT = 351                                 # the sound's ARP on byte (0x40029cd4 tstb 351(a1): the list kept only then)
KEYS_LIST = 0x4059D868                       # stock's per-track ARP key list (0x4002a3a6 reads it)
OWNER = 0x80005308
STOCK_HELD = 0x4059DD1C                      # stock's held slots (a key-held note's slot until its key-up)
VSOUND = 0x800052A8
PERIOD_MS = 2 / 3
CHORD, ENTRY, PLACES = 168, 16, 10           # one.h pv_chord
HELD, SOUND, USED = 2, 4, 1
KEY_CODES = list(range(SN.NOTE_KEY, SN.NOTE_KEY + 8))   # trig keys 9..16: one panel group (codes 33..40)
OK: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    OK.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
    return bool(ok)


class Live:
    def __init__(self, a):
        self.c = EC.Coupled(a.build, a.snapshot, a.stock, verbose=False, dsp=a.dsp)
        self.c.watchdog()
        SN.install_smoother_model(self.c)
        self.P = self.c.panel.panelin
        self.lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
        self.down = 0                            # the group's keys held now

    # -- state ---------------------------------------------------------------------------------------------------
    def n(self, name: str) -> int:
        return self.c.long(self.lay[name]) if name in self.lay else -1

    def counts(self) -> dict:
        return {k: self.n("pv_" + k) for k in ("starts", "joins", "rels", "nets", "lens", "drops", "lost", "taken")}

    def chord(self, s: int) -> dict:
        raw = self.c.read(self.lay["pv_ch"] + CHORD * s, CHORD)
        places = []
        for k in range(PLACES):
            note, fl = raw[8 + ENTRY * k], raw[9 + ENTRY * k]
            if fl & USED:
                places.append((note, fl))
        return {"live": raw[0], "track": raw[1], "places": places}

    def cur(self) -> int:
        return self.c.read(self.lay["pv_cur"] + TRACK, 1)[0] - 1

    def frame_row(self, s: int) -> list[int]:
        """the 12 halfwords pv_out wrote into voice S's words 50..61 of the smoother's output (the frame's source),
        as the last ISR left them"""
        return list(struct.unpack(">12H", self.c.read(SN.SM_OUT + 2 * (17 + 101 * s + 50), 24)))

    # -- the panel -----------------------------------------------------------------------------------------------
    def keys(self, codes: list[int], on: bool) -> None:
        """the keys CODES down (or up) in one panel message (the group's other held keys kept)"""
        ch = (codes[0] - 1) // 8
        bits = 0
        for code in codes:
            assert (code - 1) // 8 == ch
            bits |= 1 << ((code - 1) % 8)
        self.down = (self.down | bits) if on else (self.down & ~bits)
        self.c.machine.pc = self.P.buttons(self.c.machine.m, self.c.panel.profile, ch, self.down)

    def tap(self, code: int) -> None:
        ch, bit = divmod(code - 1, 8)
        self.c.machine.pc = self.P.press(self.c.machine.m, self.c.panel.profile, ch, bit)
        self.c.periods(3)
        self.c.machine.pc = self.P.release(self.c.machine.m, self.c.panel.profile, ch, bit)
        self.c.periods(3)

    def setup(self) -> None:
        c = self.c
        c.periods(8)
        owner = c.call(SN.OWNER_FN)[0]
        c.call(self.lay["smp_machine_commit"], owner + 0xF4, TRACK, A2, 1, 1)
        c.periods(2)
        self.snd = c.long(SN.KIT) + 52 + SN.STRIDE * TRACK
        c.poke(self.snd + MOD_AT, struct.pack(">H", 3 << 8))
        c.periods(4)
        ch, bit = divmod(SN.TRK - 1, 8)
        c.machine.pc = self.P.press(c.machine.m, c.panel.profile, ch, bit)
        c.periods(3)
        self.tap(SN.TRIG1 + TRACK)
        c.machine.pc = self.P.release(c.machine.m, c.panel.profile, ch, bit)
        c.periods(4)
        if not c.read(SN.KB_ON, 1)[0]:
            self.tap(SN.KEYBOARD)
        c.periods(4)
        print(f"  track 3: type {c.read(self.snd + 0xDE, 1)[0]}, MOD {c.read(self.snd + MOD_AT, 2).hex()}, ARP byte "
              f"{c.read(self.snd + ARP_AT, 1)[0]}, KEYBOARD {c.read(SN.KB_ON, 1)[0]}", flush=True)

    def telemetry(self, s: int, cost16: int) -> None:
        """an idle packet's telemetry as link.c stores it: slot S's cost / 16, every other slot at rest, now"""
        costs = [0] * 16
        costs[s] = cost16
        self.c.poke(self.lay["smp_tlm_cost"], struct.pack(">16H", *costs))
        self.c.poke(self.lay["smp_room_at"], struct.pack(">I", self.n("smp_periods") | 1))


def one_chord(L: Live, n: int, ms: float, rep: dict) -> None:
    c = L.c
    name = f"{n} notes {ms:g} ms apart"
    codes = KEY_CODES[:n]
    before = L.counts()
    gap = round(ms / PERIOD_MS)
    if gap == 0:
        L.keys(codes, True)
        c.periods(2)
    else:
        for code in codes:
            L.keys([code], True)
            c.periods(gap)
    c.periods(30)
    after = L.counts()
    s = L.cur()
    ch = L.chord(s) if s >= 0 else {"live": 0, "places": []}
    starts, joins = after["starts"] - before["starts"], after["joins"] - before["joins"]
    keys_list = c.long(KEYS_LIST + 4 * TRACK)
    r = {"starts": starts, "joins": joins, "slot": s, "places": ch["places"], "arp_list": keys_list}
    check(f"A {name}: one start, {n - 1} joins, {n} notes sounding",
          starts == 1 and joins == n - 1 and len(ch["places"]) == n and all(f & SOUND for _, f in ch["places"]),
          f"starts {starts}, joins {joins}, slot {s}, places {ch['places']}")
    check(f"A {name}: after 30 periods every note still HELD", len(ch["places"]) == n
          and all(f & HELD for _, f in ch["places"]), f"flags {[f for _, f in ch['places']]}")
    check(f"E {name}: stock's ARP key list empty (no ARP)", keys_list == 0, f"{keys_list:#x}")
    # B: a member's key up, then the leader's, then the rest
    lead_note = ch["places"][0][0] if ch["places"] else None
    member = codes[1]
    rels0 = L.n("pv_rels")
    L.keys([member], False)
    c.periods(4)
    ch1 = L.chord(s) if s >= 0 else {"places": []}
    held1 = [f & HELD != 0 for _, f in ch1["places"]]
    kept = L.n("pv_kept")
    check(f"B {name}: a member's key up ends that note alone", L.n("pv_rels") - rels0 == 1 and len(held1) == n
          and not held1[1] and all(held1[:1] + held1[2:]) and L.cur() == s and not kept & (1 << s),
          f"rels +{L.n('pv_rels') - rels0}, held {held1}, cur {L.cur()}, kept {kept:#x}")
    L.keys([codes[0]], False)
    c.periods(4)
    ch2 = L.chord(s) if s >= 0 else {"places": []}
    held2 = [f & HELD != 0 for _, f in ch2["places"]]
    kept = L.n("pv_kept")
    if n > 2:
        check(f"B {name}: the leader's key up: the chord held, its note-off kept back",
              L.cur() == s and bool(kept & (1 << s)) and not held2[0] and all(held2[2:]),
              f"cur {L.cur()}, kept {kept:#x}, held {held2}")
    L.keys(codes, False)
    c.periods(6)
    ch3 = L.chord(s) if s >= 0 else {"places": []}
    kept = L.n("pv_kept")
    stock_held = c.long(STOCK_HELD)
    check(f"B {name}: the last key up: the note-off out, nothing held, stock's slot let go",
          not kept & (1 << s) and not any(f & HELD for _, f in ch3["places"]) and L.cur() < 0
          and not stock_held & (1 << s), f"kept {kept:#x}, flags {[f for _, f in ch3['places']]}, cur {L.cur()}, "
                                         f"stock's held slots {stock_held:#06x}")
    r.update({"lead": lead_note, "after_member_up": held1, "after_leader_up": held2,
              "rels": L.n("pv_rels") - rels0})
    # C: the end of the chord, by the DSP's reports (one a period, as link.c stores an idle packet's)
    row_live = L.frame_row(s)

    def report(cost16):
        return lambda cc: L.telemetry(s, cost16)
    busy, quiet = 20000 // 16, 200                   # a chord's tail (the unit: 1,446..2,807); at rest (166..230)
    c.periods(30, each=report(busy))
    c.periods(20, each=report(quiet))            # a dip shorter than the 48 quiet reports in a row
    c.periods(4, each=report(busy))
    live_busy, row_busy = L.chord(s)["live"], L.frame_row(s)
    check(f"C {name}: released, the DSP reporting its tail (a 20-report dip in it): the row kept for the DSP",
          live_busy != 0 and row_busy == row_live and row_busy[0] & 0x8000 != 0,
          f"live {live_busy}, row {[hex(x) for x in row_busy[:4]]}..")
    c.periods(60)                                # no report (the telemetry stopped): nothing ends
    live_stale = L.chord(s)["live"]
    c.periods(60, each=report(quiet))
    end = L.chord(s)
    row_end = L.frame_row(s)
    check(f"C {name}: no report: kept; 60 quiet reports in a row: the chord ends, its row zero",
          live_stale != 0 and end["live"] == 0 and not any(row_end),
          f"live {live_stale} then {end['live']}, row {[hex(x) for x in row_end[:4]]}..")
    r.update({"live_busy": live_busy, "live_end": end["live"]})
    rep.setdefault("chords", {})[name] = r
    c.periods(10)


def arp_list(L: Live, rep: dict) -> None:
    """E, the cause: stock's key list (what 0x4002a3a6 reads) fills only with the sound's ARP on"""
    c = L.c
    c.poke(L.snd + ARP_AT, bytes([1]))
    c.periods(4)
    L.keys(KEY_CODES[:2], True)
    c.periods(6)
    on_held = c.long(KEYS_LIST + 4 * TRACK)
    L.keys(KEY_CODES[:2], False)
    c.periods(6)
    on_up = c.long(KEYS_LIST + 4 * TRACK)
    c.poke(L.snd + ARP_AT, bytes([0]))
    c.periods(40)
    rep["arp_list"] = {"held": on_held, "up": on_up}
    check("E the ARP on: stock's key list holds the keys while held, empty after", on_held != 0 and on_up == 0,
          f"held {on_held:#x}, up {on_up:#x}")


# -- the measure ----------------------------------------------------------------------------------------------------

class Count:
    """every instruction of the audio ISR (EC.ISR to its rte), by function (our C chunk's symbols, stock as one)"""
    def __init__(self, L: Live, syms: dict):
        self.L, self.c = L, L.c
        self.addrs = sorted((v, k) for k, v in syms.items())
        self.keys = [a for a, _ in self.addrs]
        self.in_isr = False
        self.pcs: collections.Counter = collections.Counter()
        self.frames = 0

    def start(self) -> None:
        from unicorn import UC_HOOK_CODE
        pcs = self.pcs

        def hk(uc, ad, sz, us):
            if self.in_isr:
                pcs[ad] += 1
        self.h = self.c.uc.hook_add(UC_HOOK_CODE, hk)
        orig = self.c.call

        def call(fn, *args, **kw):
            if fn == EC.ISR:
                self.in_isr = True
                self.frames += 1
                try:
                    return orig(fn, *args, **kw)
                finally:
                    self.in_isr = False
            return orig(fn, *args, **kw)
        self._orig, self.c.call = orig, call
        self.c.machine.flush()

    def stop(self) -> dict:
        self.c.uc.hook_del(self.h)
        self.c.call = self._orig
        self.c.machine.flush()
        stock_end = 0x40000400 + len(self.c.stock3)
        by = collections.Counter()
        for pc, k in self.pcs.items():
            if 0x40000400 <= pc < stock_end:
                by["stock"] += k
                continue
            i = bisect.bisect_right(self.keys, pc) - 1
            by[self.addrs[i][1] if i >= 0 and pc - self.keys[i] < 0x2000 else "other"] += k
        f = max(1, self.frames)
        total = sum(self.pcs.values())
        pv = {k: round(v / f, 1) for k, v in by.items() if k.startswith(("pv_", "held_any", "place_word"))}
        return {"frames": self.frames, "isr_a_frame": round(total / f, 1), "pv_a_frame": round(sum(pv.values()), 1),
                "pv": pv, "top": [(k, round(v / f, 1)) for k, v in by.most_common(12)]}


def held_table(L: Live, chords: int, notes: int) -> tuple[bytes, list[tuple[int, int]]]:
    """the chord table with CHORDS held chords of NOTES key-held notes each (slot s on track s, ANALOG 2, PARA ON)"""
    out = bytearray(16 * CHORD)
    for s in range(chords):
        c = bytearray(CHORD)
        c[0], c[1], c[2] = 1, s, 1
        struct.pack_into(">I", c, 4, notes)
        for k in range(notes):
            e = 8 + ENTRY * k
            c[e], c[e + 1], c[e + 2] = 48 + 3 * k, USED | HELD | SOUND, 1
            struct.pack_into(">iII", c, e + 4, 0, k + 1, 0)
        out[CHORD * s:CHORD * (s + 1)] = c
    return bytes(out), [(s, s) for s in range(chords)]


def measure(L: Live, rep: dict) -> None:
    c = L.c
    wc = json.loads(pathlib.Path(L.args_layout).read_text())
    syms = dict(wc.get("c_text_symbols") or {})
    out = {}
    m = Count(L, syms)
    m.start()
    c.periods(60)
    out["rest after the chords"] = m.stop()
    kit = c.long(SN.KIT)
    for t in range(16):                          # every track ANALOG 2, PARA ON; each voice its track's sound
        snd = kit + 52 + SN.STRIDE * t
        c.poke(snd + 0xDE, bytes([A2]))
        c.poke(snd + MOD_AT, struct.pack(">H", 3 << 8))
    c.poke(OWNER, struct.pack(">16I", *range(16)))
    c.poke(VSOUND, struct.pack(">16I", *[kit + 52 + SN.STRIDE * v for v in range(16)]))
    for chords, notes in ((0, 0), (4, 4), (16, 8)):
        table, _ = held_table(L, chords, notes)

        def each(cc, table=table):
            cc.poke(L.lay["pv_ch"], table)
            cc.poke(L.lay["pv_cur"], bytes(range(1, chords + 1)) + bytes(16 - chords))
        each(c)
        m = Count(L, syms)
        m.start()
        c.periods(40, each=each)
        out[f"{chords} chords of {notes} held (every track ANALOG 2)"] = m.stop()
    for k, v in out.items():
        print(f"  measure, {k}: the ISR {v['isr_a_frame']} instructions a frame, PARA's functions "
              f"{v['pv_a_frame']} {v['pv']}", flush=True)
    rep["measure"] = out


def with_dsp(L: Live, rep: dict, limit: int) -> None:
    """--dsp: one 3-note chord through both processors, the DSP's own telemetry: held 20 periods, its keys up, then
    up to LIMIT periods for the chord to end; the DSP's pool (dnfw.engines.analog2.para FREE, LOST) after"""
    PA = importlib.import_module("dnfw.engines.analog2.para")
    c = L.c
    c.dsp_clock()                                # the DSP's per-slot costs measured (its telemetry), as on the unit
    c.clock_calibrate()
    free0, lost0 = c.dsp_word(PA.FREE), c.dsp_word(PA.LOST)
    codes = KEY_CODES[:3]
    for code in codes:
        L.keys([code], True)
        c.periods(3)
    c.periods(20)
    s = L.cur()
    held_free = c.dsp_word(PA.FREE)
    own = c.dsp_word(PA.OWN + 4 * s) if s >= 0 else 0
    print(f"  dsp: chord on slot {s}, places {L.chord(s)['places'] if s >= 0 else None}, pool free {free0:#06x} -> "
          f"{held_free:#06x}, the slot's shadows {own:#x}, telemetry {L.n('smp_room_at')} / {L.n('smp_periods')}",
          flush=True)
    L.keys(codes, False)
    trace, ended = [], None
    for k in range(limit):
        if not c.period():
            break
        cost = struct.unpack('>H', c.read(L.lay['smp_tlm_cost'] + 2 * s, 2))[0]
        live = L.chord(s)['live']
        trace.append((k, live, cost, L.n('smp_room_at')))
        if live == 0 and ended is None:
            ended = k
        if ended is not None and k >= ended + 12:
            break
    free1, lost1 = c.dsp_word(PA.FREE), c.dsp_word(PA.LOST)
    rep['dsp'] = {'slot': s, 'free': [free0, held_free, free1], 'lost': [lost0, lost1], 'ended_after': ended,
                  'trace': trace}
    print(f"  dsp: trace (period, live, the slot's cost / 16, report at) {trace[::8]}", flush=True)
    check("C (DSP) the chord's shadows took pool blocks while held", s >= 0 and held_free != free0 and own != 0,
          f"free {free0:#06x} -> {held_free:#06x}, shadows {own:#x}")
    check("C (DSP) the keys up: the chord ends by the DSP's own report", ended is not None,
          f"after {ended} periods" if ended is not None else f"not in {limit} periods")
    line = 8000 // 16
    rel = [t for t in trace if t[1] == 2]
    before_end = [t[2] for t in trace if ended is not None and ended - 48 <= t[0] < ended]
    check("C (DSP) the chord kept while the DSP reported its slot over the line, ended only after 48 quiet reports",
          ended is not None and any(t[2] > line for t in rel) and before_end and max(before_end) <= line,
          f"releasing {len(rel)} periods, costs while releasing {sorted(set(t[2] for t in rel))[:6]}.."
          f"{sorted(set(t[2] for t in rel))[-3:]}, the last 48 before the end at most {max(before_end or [0])}")
    check("C (DSP) its pool blocks all free again, no place left out", free1 == free0 and lost1 == lost0,
          f"free {free1:#06x} (before {free0:#06x}), lost {lost0} -> {lost1}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--layout", default=str(REPO / "src/dnfw/mods/waverider_code.json"))
    p.add_argument("--sizes", default="3,4,6,8")
    p.add_argument("--apart", default="0,1,5,20", help="ms between key presses")
    p.add_argument("--measure", action="store_true")
    p.add_argument("--dsp", action="store_true", help="the DSP too: one chord, its end by the DSP's own report")
    p.add_argument("--dsp-limit", type=int, default=900)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    L = Live(a)
    L.args_layout = a.layout
    L.setup()
    rep: dict = {}
    if a.dsp:
        with_dsp(L, rep, a.dsp_limit)
        if a.json:
            pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
        print(f"{sum(OK)} of {len(OK)} checks pass", flush=True)
        print("PASS" if all(OK) else "FAIL", flush=True)
        return 0 if all(OK) else 1
    for n in (int(x) for x in a.sizes.split(",")):
        for ms in (float(x) for x in a.apart.split(",")):
            one_chord(L, n, ms, rep)
            if L.c.halt:
                break
    arp_list(L, rep)
    check("D pv_dirty gone", "pv_dirty" not in L.lay, f"{L.n('pv_dirty'):#x}" if "pv_dirty" in L.lay else "")
    rep["counts"] = L.counts()
    rep["halt"] = L.c.halt
    rep["faults"] = len(L.c.faults())
    check("no halt, no fault", not L.c.halt and not L.c.faults(), f"halt {L.c.halt}, faults {len(L.c.faults())}")
    if a.measure and not L.c.halt:
        measure(L, rep)
    print(f"  counts {rep['counts']}", flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    ok = all(OK)
    print(f"{sum(OK)} of {len(OK)} checks pass", flush=True)
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
