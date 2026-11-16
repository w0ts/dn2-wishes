"""Sounds from the unit played by the sequencer through both processors (emu_coupled.py), OS 1.12: each track's level.

For the User's sounds (a track's 1,163-byte kit sound, its machine byte included, e.g. scratch/unit-now/r3/
drone_sound_r14b_T6.bin): put on their tracks (direct: MACHINE SEL's commit, then the sound written into the kit),
a trig on step 1 of each --trig track (UI: [TRK] + [TRIG t], RECORD, [TRIG 1], RECORD), the pattern STEPS long
(direct); --hold TRACK: its KEYBOARD note pressed first and held throughout; then PLAY. Per period, each track's
voices (the ColdFire's slot -> track table) and their block after the chain; per track at the end: the voices, peak
and RMS (dBFS of that block) over the periods after its first sound. So a held track can be measured alone and with
another track playing beside it (the unit, r14b: DRONE ~-30 dB, gone when anything else plays).

Every voice slot sounds here since the runner's G12-G14 and the warm snapshot built under them (until then only
slot 0 did, so a run measured the voice it played first); the held note, played first, is on slot 0.

Usage (bench):
  python -u scripts/emu_coupled_seqnote.py --build X.syx --stock 1.12.syx --snapshot S
         --sound 5:drone_sound_r14b_T6.bin --hold 5 [--trig 1] [--steps 4] [--periods 96] [--json OUT]"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
Coupled = importlib.import_module("emu_coupled").Coupled
SN = importlib.import_module("emu_coupled_stocknote")             # its keys, KIT, the smoother model

SEQ_PATTERN, PAT_LENGTH, SEQ_PLAYING = 0x42C5B9A0, 122196, 0x42C5B918   # (emu_fine_seq.py)
K_RECORD, K_PLAY, K_STOP = 19, 20, 21


def db(x: float) -> float:
    return round(20 * math.log10(x), 2) if x > 0 else -999.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--layout", default=str(REPO / "src/dnfw/mods/waverider_code.json"))
    p.add_argument("--sound", action="append", default=[], help="TRACK:FILE (0-based track)")
    p.add_argument("--machine", action="append", default=[], help="TRACK:TYPE, MACHINE SEL's commit only (0-based)")
    p.add_argument("--trig", action="append", type=int, default=[], help="a track (0-based) with a trig on step 1")
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--periods", type=int, default=96)
    p.add_argument("--hold", type=int, default=None, help="a track (0-based) whose KEYBOARD note is played first "
                                                           "(voice slot 0) and held throughout")
    p.add_argument("--with", dest="with_", type=int, default=None,
                   help="another track (0-based): with the held note still down, [TRK] + [TRIG t] and a second "
                        "KEYBOARD note held there (the sequencer does not start here: PLAY leaves it stopped)")
    p.add_argument("--with-after", type=int, default=24, help="periods the held note plays alone first")
    p.add_argument("--stale-tail", action="store_true", help="--clock: keep the guard's tail as the uncalibrated frames set it")
    p.add_argument("--clock", type=float, default=None, help="give the DSP a clock (emu_coupled.dsp_clock) calibrated so "
                                                           "an idle frame reads this D (the unit: ~0.69); the guard's "
                                                           "skips reported")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    c = Coupled(a.build, a.snapshot, a.stock, verbose=True)
    c.watchdog()
    SN.install_smoother_model(c)
    P = c.panel.panelin
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]

    def key(code):
        return divmod(code - 1, 8)

    def held(code, on, n=3):
        c.machine.pc = (P.press if on else P.release)(c.machine.m, c.panel.profile, *key(code))
        c.periods(n)

    def tap(code):
        held(code, True)
        held(code, False)

    c.periods(8)
    kit = c.long(SN.KIT)
    owner = c.call(SN.OWNER_FN)[0]
    for spec in a.sound:
        t, path = spec.split(":", 1)
        t = int(t)
        snd = pathlib.Path(path).read_bytes()
        assert len(snd) == SN.STRIDE, f"{path}: {len(snd)} bytes, not {SN.STRIDE}"
        c.call(lay["smp_machine_commit"], owner + 0xF4, t, snd[SN.SOUND_TYPE], 1, 1)
        c.periods(2)
        c.poke(kit + 52 + SN.STRIDE * t, snd)
        c.periods(2)
    G = ck = None
    if a.clock is not None:                                       # the DSP's time (emu_coupled_budget.py's calibration)
        from dnfw.perc import guard as G                          # noqa: PLC0415, N812
        ck = c.dsp_clock(extra=0)
        c.periods(4)
        idle_end = c.clock_calibrate(a.clock) if not a.stale_tail else None
        if a.stale_tail:                                          # as before 2026-11-14: the tail learned uncalibrated
            ends = []
            for _ in range(6):
                c.period()
                ends.append(ck["end"])
            idle_end = sum(ends[2:]) / len(ends[2:])
            ck["extra"] = int(a.clock * ck["P"] - idle_end)
        print(f"  DSP clock: idle end {idle_end:.0f} cycles, EXTRA {ck['extra']} (idle D {a.clock})", flush=True)
        c.periods(20)
    for spec in a.machine:                                        # our machine at MACHINE SEL's starts (no sound file)
        t, ty = (int(x) for x in spec.split(":"))
        c.call(lay["smp_machine_commit"], owner + 0xF4, t, ty, 1, 1)
        c.periods(2)
    pat = c.long(SEQ_PATTERN)
    c.poke(pat + PAT_LENGTH, struct.pack(">H", a.steps))
    types = [c.read(kit + 52 + SN.STRIDE * k + SN.SOUND_TYPE, 1)[0] for k in range(16)]
    print(f"  machine types, tracks 1..16: {types}; trigs on tracks {[t + 1 for t in a.trig]}, {a.steps} steps", flush=True)
    if c.read(SN.KB_ON, 1)[0]:
        tap(SN.KEYBOARD)                                          # (the TRIG keys place trigs only with it off)
    for t in a.trig:
        held(SN.TRK, True)
        tap(SN.TRIG1 + t)
        held(SN.TRK, False)
        c.periods(4)
        tap(K_RECORD)
        tap(SN.TRIG1)                                             # a trig on step 1
        tap(K_RECORD)
    if a.hold is not None:                                        # the first note: voice slot 0, held throughout
        held(SN.TRK, True)
        tap(SN.TRIG1 + a.hold)
        held(SN.TRK, False)
        c.periods(4)
        if not c.read(SN.KB_ON, 1)[0]:
            tap(SN.KEYBOARD)
        c.machine.pc = P.press(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY))
        c.periods(4)
    if a.trig:
        tap(K_PLAY)
    tracks = list(dict.fromkeys(([a.hold] if a.hold is not None else []) + ([a.with_] if a.with_ is not None else [])
                                + a.trig))
    acc = {t: {"voices": set(), "peak": 0.0, "sq": 0.0, "n": 0, "first": None} for t in tracks}
    rows, clocks = [], []
    for k in range(a.periods):
        if a.with_ is not None and k == a.with_after:             # the held note stays down; another track's too
            held(SN.TRK, True)                                    # (these 9 periods are not measured)
            tap(SN.TRIG1 + a.with_)
            held(SN.TRK, False)
            c.machine.pc = P.press(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY + 2))
            print(f"  p{k:3d}: track {a.with_ + 1}'s note pressed, track {a.hold + 1}'s still held", flush=True)
        if not c.period():
            break
        vt = struct.unpack(">16I", c.read(SN.SLOT_TRACK, 64))
        row = {}
        for t in tracks:
            vs = [v for v in range(16) if vt[v] == t]
            pk = max((abs(x) for v in vs for x in c.last_bufs[v]), default=0.0)
            if vs and acc[t]["first"] is None and pk > 0:
                acc[t]["first"] = k
            if acc[t]["first"] is not None:
                acc[t]["voices"] |= set(vs)
                acc[t]["peak"] = max(acc[t]["peak"], pk)
                for v in vs:
                    acc[t]["sq"] += sum(x * x for x in c.last_bufs[v])
                acc[t]["n"] += 32
            row[t] = (vs, round(pk, 5))
        rows.append(row)
        clk = None
        if G is not None:
            clk = {"d": round(ck["d"], 3), "voice_skips": c.dsp_word(G.SKIPS), "ins_skips": c.dsp_word(G.INS_SKIPS),
                   "limit": c.dsp_word(G.LIMIT), "limit_perc": c.dsp_word(G.LIMIT_PERC), "tail": c.dsp_word(G.TAIL),
                   "period": c.dsp_word(G.PERIOD), "reserve": c.dsp_word(G.RESERVE), "mark0": c.dsp_word(G.MARK0),
                   "entry": (c.dsp_word(G.MARK) - c.dsp_word(G.MARK0)) & 0xFFFFFFFF,
                   "ours_end": (c.dsp_word(G.OURS_END) - c.dsp_word(G.MARK0)) & 0xFFFFFFFF,
                   "cost_slot0": c.dsp_word(G.COST_PERC), "start": (c.dsp_word(G.START) - c.dsp_word(G.MARK0)) & 0xFFFFFFFF}
        clocks.append(clk)
        if clk and (k < 4 or k % 8 == 0):
            print(f"  p{k:3d} guard: " + ", ".join(f"{n} {v}" for n, v in clk.items()), flush=True)
        if k % 8 == 0:
            print(f"  p{k:3d}: " + "; ".join(f"track {t + 1} voices {vs} peak {pk}" for t, (vs, pk) in row.items())
                  + f" | slot tracks {list(vt)}, playing {c.read(SEQ_PLAYING, 1)[0]}"
                  + (f" | D {clk['d']}, guard voice skips {clk['voice_skips']}, insert skips {clk['ins_skips']}"
                     if clk else ""), flush=True)
    if a.with_ is not None:
        c.machine.pc = P.release(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY + 2))
        c.periods(1)
    if a.hold is not None:
        c.machine.pc = P.release(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY))
    if a.trig:
        tap(K_STOP)
    rep = {"build": a.build, "sounds": a.sound, "trigs": a.trig, "hold": a.hold, "types": types,
           "tracks": {}, "rows": rows, "clocks": clocks, "halt": c.halt}
    for t, s in acc.items():
        rms = math.sqrt(s["sq"] / s["n"]) if s["n"] else 0.0
        rep["tracks"][t + 1] = {"type": types[t], "voices": sorted(s["voices"]), "first_period": s["first"],
                                "peak_db": db(s["peak"]), "rms_db": db(rms)}
        print(f"  track {t + 1} (type {types[t]}): voices {sorted(s['voices'])}, from period {s['first']}, "
              f"peak {db(s['peak'])} dB, RMS {db(rms)} dB", flush=True)
    if a.hold is not None:                                        # the held track's level by stretch of periods
        series = [r[a.hold][1] for r in rows if a.hold in r]
        for lo in range(0, len(series), 16):
            part = series[lo:lo + 16]
            clk = clocks[min(lo + 15, len(clocks) - 1)]
            print(f"  track {a.hold + 1}, periods {lo}..{lo + len(part) - 1} (from the measuring start): "
                  f"peak {db(max(part, default=0))} dB"
                  + (f"; by its end D {clk['d']}, guard voice skips {clk['voice_skips']}, insert skips "
                     f"{clk['ins_skips']}" if clk else ""), flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    print(f"  halt: {c.halt}", flush=True)
    return 0 if not c.halt else 1


if __name__ == "__main__":
    raise SystemExit(main())
