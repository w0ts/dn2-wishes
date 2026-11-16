"""VOICE BUDGET (csrc/load) through both processors, with a DSP clock (emu_coupled.Coupled.dsp_clock), OS 1.12.

The unit, r14b, 2026-11-13: T12 a JUNO sound with a long AMP release (scratch/screens-live/t12_sound_r14b.bin), 16 short
notes each released before the next: 12 voices piled up in their release tails, the DSP's guard then skipped voices
and inserts; the budget never stole (it took only held voices, and judged by a fixed LOAD_AVAIL).

Here: the build's ColdFire and DSP together (the build's own snapshot, the stock smoother modelled as stocknote does),
the DSP given a clock whose stock work is raised by EXTRA so an idle frame reads the unit's D (--target-idle, measured
over the first quiet periods), the sound put on the track, then NOTES notes, each held ON periods and released for OFF.
The notes are much closer together than on the unit (the harness runs ~11 s a period), so the tails pile up faster.

Per note: the track's slots, the slots sounding (the DSP's per-slot cost over LOAD_TAIL), the guard's voice skips and
insert refusals since the start, the budget's counters (steals, tails stolen, notes judged by the DSP's room), the model
D. With the fix the expected result is: steals made, and no voice skipped by the guard. --control TRACK plays the same
notes on a stock machine's track instead (the budget must make no check: load_checks unchanged).

Usage (bench):
  python -u scripts/emu_coupled_budget.py --build X.syx --stock 1.12.syx --snapshot S --layout waverider_code.json
         [--track 11] [--sound t12_sound_r14b.bin] [--control 1] [--json OUT]"""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
Coupled = importlib.import_module("emu_coupled").Coupled
SN = importlib.import_module("emu_coupled_stocknote")             # its keys, KIT and the smoother model

LOAD_SYMS = ("load_checks", "load_over", "load_keyups", "load_tails", "load_by_room", "load_last_free", "load_last_need")
TAIL_UNITS = 8000 // 16                                           # dnfw.load.TAIL: a slot still sounding


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--layout", default=str(REPO / "src/dnfw/mods/waverider_code.json"))
    p.add_argument("--track", type=int, default=11, help="0-based (11: T12)")
    p.add_argument("--sound", default=None, help="1,163 bytes: the track's sound (its machine byte included)")
    p.add_argument("--control", type=int, default=None, help="a stock machine's track (0-based) to play instead")
    p.add_argument("--notes", type=int, default=16)
    p.add_argument("--on", type=int, default=6)
    p.add_argument("--off", type=int, default=4)
    p.add_argument("--target-idle", type=float, default=0.69, help="the model D of an idle frame (the unit: ~69 %%)")
    p.add_argument("--extra", type=int, default=None, help="EXTRA cycles (else calibrated to --target-idle)")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    from dnfw.perc import guard as G                               # noqa: PLC0415
    c = Coupled(a.build, a.snapshot, a.stock, verbose=True)
    c.watchdog()
    SN.install_smoother_model(c)
    P = c.panel.panelin
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    syms = {n: lay[n] for n in LOAD_SYMS if n in lay}
    tlm = lay.get("smp_tlm_cost")

    def key(code):
        return divmod(code - 1, 8)

    def held(code, on, n=3):
        c.machine.pc = (P.press if on else P.release)(c.machine.m, c.panel.profile, *key(code))
        c.periods(n)

    def tap(code):
        held(code, True)
        held(code, False)

    ck = c.dsp_clock(extra=0)
    print(f"  DSP clock: {ck['sites']} EMUCLK sites", flush=True)
    c.periods(8)
    t = a.control if a.control is not None else a.track
    kit = c.long(SN.KIT)
    if a.control is None and a.sound:
        snd = pathlib.Path(a.sound).read_bytes()
        assert len(snd) == SN.STRIDE
        owner = c.call(SN.OWNER_FN)[0]
        c.call(lay["smp_machine_commit"], owner + 0xF4, t, snd[SN.SOUND_TYPE], 1, 1)
        c.periods(2)
        c.poke(kit + 52 + SN.STRIDE * t, snd)
        c.periods(2)
    types = [c.read(kit + 52 + SN.STRIDE * k + SN.SOUND_TYPE, 1)[0] for k in range(16)]
    print(f"  machine types, tracks 1..16: {types}; playing track {t + 1}", flush=True)
    held(SN.TRK, True)
    tap(SN.TRIG1 + t)
    held(SN.TRK, False)
    c.periods(4)
    if not c.read(SN.KB_ON, 1)[0]:
        tap(SN.KEYBOARD)
    # calibrate: idle frames' end, EXTRA so they read --target-idle
    ends = []
    for _ in range(6):
        c.period()
        ends.append(ck["end"])
    idle_end = sum(ends[2:]) / len(ends[2:])
    # (EXTRA may be negative: a kit with more stock than the unit's reads less stock time, so an idle frame reads
    # the unit's D)
    ck["extra"] = a.extra if a.extra is not None else int(a.target_idle * ck["P"] - idle_end)
    print(f"  idle end {idle_end:.0f} cycles: EXTRA {ck['extra']} (idle D {(idle_end + ck['extra']) / ck['P']:.3f})", flush=True)
    for _ in range(40):                                            # TAIL and the deadline settle on the new stock
        c.period()

    def state():
        st = {n: c.long(v) for n, v in syms.items()}
        if "load_last_free" in st and st["load_last_free"] & 0x80000000:
            st["load_last_free"] -= 1 << 32
        costs = struct.unpack(">16H", c.read(tlm, 32)) if tlm else (0,) * 16
        vt = struct.unpack(">16I", c.read(SN.SLOT_TRACK, 64))
        return {**st, "sounding": sum(1 for x in costs if x > TAIL_UNITS), "ours_cost": 16 * sum(costs),
                "track_slots": [v for v in range(16) if vt[v] == t],
                "voice_skips": c.dsp_word(G.SKIPS), "ins_skips": c.dsp_word(G.INS_SKIPS),
                "tail": c.dsp_word(G.TAIL), "limit": c.dsp_word(G.LIMIT), "d": round(ck["d"], 3),
                "dsp_packets": c.dsp_packets, "delivered": c.delivered,
                "periods": c.long(lay["smp_periods"]) if "smp_periods" in lay else None,
                "room_at": c.long(lay["smp_room_at"]) if "smp_room_at" in lay else None,
                "room_bus": struct.unpack(">H", c.read(lay["smp_room_now"] + 6, 2))[0] if "smp_room_now" in lay else None}
    s0 = state()
    rows = []
    for n in range(a.notes):
        if c.halt:
            break
        c.machine.pc = P.press(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY))
        c.periods(a.on)
        c.machine.pc = P.release(c.machine.m, c.panel.profile, *key(SN.NOTE_KEY))
        c.periods(a.off)
        s = state()
        rows.append({"note": n + 1, **s})
        print(f"  note {n + 1:2d}: sounding {s['sounding']:2d}, ours {s['ours_cost']:6d}, D {s['d']:.3f}, voice skips "
              f"{s['voice_skips'] - s0['voice_skips']}, ins skips {s['ins_skips'] - s0['ins_skips']}, "
              + ", ".join(f"{k[5:]} {s[k] - s0.get(k, 0) if k != 'load_last_free' else s[k]}" for k in syms)
              + f" | dsp packets {s['dsp_packets']}, periods {s['periods']}, room_at {s['room_at']}, room_bus {s['room_bus']}",
              flush=True)
    last = rows[-1] if rows else s0
    d = {k: last[k] - s0[k] for k in ("voice_skips", "ins_skips") if k in last}
    for k in syms:
        if k != "load_last_free":
            d[k] = last[k] - s0[k]
    rep = {"build": a.build, "track": t, "control": a.control is not None, "types": types, "extra": ck["extra"],
           "idle_end": idle_end, "start": s0, "notes": rows, "deltas": d, "halt": c.halt}
    if a.control is not None:
        ok = d.get("load_checks", 0) == 0 and not c.halt
        verdict = "stock-only control: no budget check made"
    else:
        ok = d.get("voice_skips", 1) == 0 and d.get("load_over", 0) > 0 and not c.halt
        verdict = "the budget steals and the guard skips no voice"
    rep["pass"] = ok
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    print(f"  deltas: {d}", flush=True)
    print(("PASS" if ok else "FAIL") + f": {verdict}" + (f" (halt: {c.halt})" if c.halt else ""), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
