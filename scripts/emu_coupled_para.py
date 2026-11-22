"""parachord: a PARA chord through both processors (emu_coupled.py), OS 1.12 (2026-11-17).

v0.57.1 on the unit (a8fbf921): PARA ON, a chord of 2..5 notes took one voice slot, as designed, but only its lowest
note sounded (scratch/unit-now/v571-checks.md). The ColdFire's allocator check (emu_para_onevoice) and the SHARC
runner's para runs (rows poked before the leader's note-on) both passed: neither had the TDM link bring the chord's
row, which came a period or more after the leader's note-on frame. Here the ColdFire and the DSP run together.

ENGINE (JUNO 50, ANALOG 2 51; 23, 22 until 2026-11-18) is put on track 3 by MACHINE SEL's commit, PARA ON in its sound (MOD, the PARA
record), KEYBOARD on, then trig keys pressed one after another (a few periods apart) and held. Checks:
- the chord is ONE voice slot (the track's voices: one);
- the leader's row holds every pressed note, sounding (since 2026-11-17 the row rides in the voice's own frame words,
  csrc/para/one.c pv_out; read here from the DSP's working copy, which the PARA pass fills from the frame);
- every note of the row is heard in the leader's render: its fundamental (Hann-windowed Goertzel over the held
  periods) at least a tenth of the leader's own, and at least 4 x the same band in a PARA OFF run's render of the
  leader's slot (the leader's note alone there: its own harmonics do not count as the others).
Usage (bench):
  python -u scripts/emu_coupled_para.py --build X.syx --stock 1.12.syx --snapshot S [--engine 23] [--json OUT]"""

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
SN = importlib.import_module("emu_coupled_stocknote")       # its smoother model, keys and addresses

TRACK = 2                                    # track 3
MOD_AT = 20 + 2 * 37                         # the sound's MOD (PARA) value (emu_para_onevoice.MOD_AT)
KEYS = (SN.NOTE_KEY, SN.NOTE_KEY + 2, SN.NOTE_KEY + 4)       # three trig keys of the KEYBOARD
APART, HOLD, SKIP = 4, 112, 24               # periods between key presses, held periods, periods left out first
RATE = 48000


def level(x: list[float], f: float) -> float:
    """the Hann-windowed magnitude of X at F Hz (Goertzel), per sample"""
    n = len(x)
    w = 2 * math.cos(2 * math.pi * f / RATE)
    s1 = s2 = 0.0
    for k, v in enumerate(x):
        s0 = v * (0.5 - 0.5 * math.cos(2 * math.pi * k / (n - 1))) + w * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - w * s1 * s2)) / n


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def play(a, para: int) -> dict:
    """one run: ENGINE on track 3, PARA PARA, KEYS pressed APART periods apart and held HOLD periods -> the track's
    voices, each voice's render over the held periods, the leader's row"""
    c = SN.Coupled(a.build, a.snapshot, a.stock, verbose=False)
    c.watchdog()
    SN.install_smoother_model(c)
    P = c.panel.panelin

    def key(code):
        return divmod(code - 1, 8)

    def held(code, on, n=3):
        c.machine.pc = (P.press if on else P.release)(c.machine.m, c.panel.profile, *key(code))
        c.periods(n)

    ks = c.kit_stored                        # (2026-11-20) the kit stored at the resume, as a boot has it (emu_coupled)
    if ks and "deps" in ks:
        print(f"    the kit stored at the resume: {ks['sounds']} sounds, track 3's [LFO, A, D, C] "
              f"{[[hex(y) if j else y for j, y in enumerate(x[1:])] for x in ks['deps'] if x[0] == TRACK]}", flush=True)
    elif ks:
        print(f"    the kit NOT stored at the resume: {ks['skipped']}", flush=True)
    c.periods(8)
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    owner = c.call(SN.OWNER_FN)[0]
    c.call(lay["smp_machine_commit"], owner + 0xF4, TRACK, a.engine, 1, 1)
    c.periods(2)
    kit = c.long(SN.KIT)
    snd = kit + 52 + SN.STRIDE * TRACK
    c.poke(snd + MOD_AT, struct.pack(">H", para << 8))
    c.periods(4)
    held(SN.TRK, True)
    held(SN.TRIG1 + TRACK, True)
    held(SN.TRIG1 + TRACK, False)
    held(SN.TRK, False)
    c.periods(4)
    if not c.read(SN.KB_ON, 1)[0]:
        held(SN.KEYBOARD, True)
        held(SN.KEYBOARD, False)
    renders: dict[int, list[float]] = {}
    down: dict[int, int] = {}                # each key pressed and left held: the group's held keys passed along
    for code in KEYS:                        # (panelin.press sets the whole group of eight: the others held too)
        ch, bit = key(code)
        c.machine.pc = P.press(c.machine.m, c.panel.profile, ch, bit, down.get(ch, 0))
        down[ch] = down.get(ch, 0) | 1 << bit
        c.periods(APART)
    lay_pv = {k: lay[k] for k in ("pv_starts", "pv_joins", "pv_rels", "pv_taken") if k in lay}
    print(f"    after the keys: {', '.join(f'{k} {c.long(v)}' for k, v in lay_pv.items())}, the sound's type "
          f"{c.read(snd + 0xDE, 1)[0]} MOD {c.read(snd + MOD_AT, 2).hex()}", flush=True)
    for k in range(HOLD):
        if not c.period():
            break
        vt = struct.unpack(">16I", c.read(SN.SLOT_TRACK, 64))
        if k >= SKIP:
            for v in range(16):
                if vt[v] == TRACK:
                    renders.setdefault(v, []).extend(c.last_bufs[v])
    SM = importlib.import_module("dnfw.sampler.machines")
    pool = importlib.import_module("dnfw.sampler.live").layout().pool
    rows = {}
    for s in range(16):
        w = [c.dsp_word(pool + SM.PV_TABLE + 4 * (SM.PV_ROW_WORDS * s + j)) for j in range(SM.PV_ROW_WORDS)]
        h = [x for v in w for x in (v & 0xFFFF, v >> 16)]
        if h[0] & 0x8000:
            rows[s] = {"lead": h[0] & 0x7F, "places": [((p & 0xFF) ^ 0x80) - 0x80 for p in h[1:11]
                                                       if p & 0x400 and p & 0x200]}
    print(f"    link: smp_tables {struct.unpack('>i', c.read(lay['smp_tables'], 4))[0]}, pv_ends "
          f"{c.long(lay['pv_ends'])}; the rows' first words {[hex(c.dsp_word(pool + SM.PV_TABLE + 4 * j)) for j in range(12)]}",
          flush=True)
    for code in reversed(KEYS):
        ch, bit = key(code)
        down[ch] &= ~(1 << bit)
        c.machine.pc = P.release(c.machine.m, c.panel.profile, ch, bit, down[ch])
        c.periods(2)
    c.periods(8)
    voices = sorted(v for v, x in renders.items() if max((abs(y) for y in x), default=0.0) > SN.FLOOR)
    return {"voices": voices, "renders": renders, "rows": rows, "halt": c.halt}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--engine", type=int, default=50, help="the machine type: 50 JUNO, 51 ANALOG 2")
    p.add_argument("--layout", default=str(REPO / "src/dnfw/mods/waverider_code.json"))
    p.add_argument("--json", default=None)
    a = p.parse_args()
    on = play(a, 3)
    print(f"  PARA ON: voices {on['voices']}, rows {on['rows']}, halt {on['halt']}", flush=True)
    rep: dict = {"engine": a.engine, "on": {k: on[k] for k in ("voices", "rows", "halt")}}
    ok = not on["halt"] and len(on["voices"]) == 1 and on["voices"][0] in on["rows"]
    lead_slot = on["voices"][0] if on["voices"] else None
    row = on["rows"].get(lead_slot) if lead_slot is not None else None
    ok &= bool(row) and len(row["places"]) == len(KEYS)
    print(("  ok    " if ok else "  FAIL  ") + f"one voice slot, its row holds the {len(KEYS)} notes "
          f"(slot {lead_slot}, row {row})", flush=True)
    if ok:
        off = play(a, 0)
        print(f"  PARA OFF: voices {off['voices']}, halt {off['halt']}", flush=True)
        x = on["renders"][lead_slot]
        y = off["renders"].get(lead_slot) or (off["renders"][off["voices"][0]] if off["voices"] else [])
        base = row["lead"]
        lv = {o: (level(x, hz(base + o)), level(y[:len(x)], hz(base + o)) if y else 0.0) for o in row["places"]}
        lead = lv.get(0, (0.0, 0.0))[0]
        rep["levels"] = {o: [round(v, 6), round(w, 6)] for o, (v, w) in lv.items()}
        for o, (v, w) in sorted(lv.items()):
            good = o == 0 or (v >= 0.1 * lead and v >= 4 * w)
            ok &= lead > 0 and good
            print(("  ok    " if good else "  FAIL  ") + f"note {base + o} (+{o}): {v:.5f} in the chord's render, "
                  f"{w:.5f} in PARA OFF's leader alone, the leader's own {lead:.5f}", flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    print("PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
