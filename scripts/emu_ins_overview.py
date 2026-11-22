"""The FX and AMP keys on their release, and the inserts overview held (csrc/inserts/ovw.c), in the ColdFire emulator.

    python scripts/emu_ins_overview.py --venv PY --root ROOT --build BUILD_DIR --snapshot SNAP --work DIR

One emulator run (scripts/emu_waverider_menu.py), the panel's own key bytes:
  1. FX pressed on the starting page (another page): FX 1/3 comes on the PRESS, as stock's own page keys (the User,
     2026-11-18: "coming from another page... it on press down"), and its release steps nothing more; held past stock's
     first key repeat (30 ticks) and let go: no step (stock's own hold test, the MOD key's: 20 ticks steps, 28 not).
  2. FX held 0.25 s on stock's FX page: stock's value view (the labels change), no overview, no page step.
  3. All 32 slots set (every type, MIX 0 and up, a slot-1 mover kept at MIX 0, a FULL XDLY), FX held 1.4 s: the
     overview, pixel for pixel dnfw.inserts.overview.render (FUL in either blink phase).
  4. Let go after the overview: it closes, no tap played, the page is the one under it (not FX 2/3).
  5. FX tapped on the FX page: INSERT 1 (FX 2/3), the tap played; held 0.25 s there: our labels read values, and
     let go: no step; tapped: INSERT 2.
  6. FX held a second, then another key (NO): the overview closes; FX's release then steps nothing.
  7. FUNC + FX: stock's SEND page, no tap played, no overview.
  8. AMP: tapped, stock's AMP page; held there, stock's values, no step; held 1.4 s, its own overview (emu_overviews.py) and no step; tapped
     again, our page 2/3 on the release; held 0.25 s there and let go: no step.
  9. No fault.
  10. (2026-11-18) From another page (SYN) too: FX or AMP held past the first repeat: page 1 of the key, its values
     while held (FX: as step 2's), and the release steps nothing more; FX held a second there: the overview, let go: FX 1/3; AMP held 1.4 s: AMP 1/3.
  11. (2026-11-19, the User: "auto gain should be off by default on our disto FXs") AUTO on the distortions: every
     slot's DIST FOLD HARM AUTO and its FUZZ / TAPE AUTO set ON beforehand (as a slot keeps them from an earlier pick
     or project), INSERT 1 up, M.SEL turned by its knob through DIST, FOLD, FUZZ, HARM, TAPE: each picked with AUTO
     OFF; on TAPE and on DIST AUTO turned ON by its knob (G), then FUNC + a long push on G (the frame count moved 1,000,
     0.67 s): OFF again, the page still page 1 (B then turns DRIV, not page 2's AGE).
Exit 0 and "OVERVIEW OK" when every fact holds; the facts are in WORK/overview.json.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from dnfw.inserts import overview as O  # noqa: E402

K_FX, K_FUNC, K_NO, K_AMP = 5, 17, 12, 4
K_SYN = 2                               # stock's SYN key (step 10: another page)
K_PUSH_G = 47                           # encoder G's push (A..H: 41..48)
UI_TRACK, FRAMES = 0x42432A6C, 0x4058F8D4  # the track shown; the frame count (1,500 a second; no audio interrupt here)
DIST, FOLD, HARM, FUZZ, TAPE = 10, 3, 6, 1, 2
AUTO_PICKS = (DIST, FOLD, FUZZ, HARM, TAPE)    # in M.SEL's order (ins.c ORDER), so each pick turns the knob right
AUTO_K6 = (FOLD, HARM, DIST)                    # AUTO in field 5 (K6); FUZZ's and TAPE's in ins_fza
TYPES = 14
POS = {0: 0, 4: 1, 10: 2, 7: 3, 3: 4, 1: 5, 11: 6, 6: 7, 13: 8, 12: 9, 9: 10, 2: 11, 5: 12, 8: 13}   # ins.c POS
TICK = 1_100_000                        # emulator instructions a panel tick (docs: ~1.1 M, 121 ticks a second)
HOLD = 30                               # ticks: past stock's first key repeat (24 ticks, 0.2 s on the unit: 0x4029f0c8),
                                        # the unit's own sequence of a short hold (the User's report on 95a560a2)
SCALE = 6                               # emulib panel.write_png

# (type, MIX, instance) per slot; FDN8 7 / XDLY 8 hold an instance (0xFF: none, FULL)
FDN8, XDLY, NO_INST = 7, 8, 0xFF
SLOTS = [
    [(1, 90, NO_INST), (4, 64, NO_INST)],        # 1  FUZZ, CHOR
    [(10, 100, NO_INST), (0, 127, NO_INST)],     # 2  DIST, OFF
    [(2, 0, NO_INST), (0, 0, NO_INST)],          # 3  TAPE at MIX 0, OFF
    [(0, 127, NO_INST), (0, 127, NO_INST)],      # 4  OFF OFF
    [(FDN8, 40, 0), (3, 0, NO_INST)],            # 5  FDN8, FOLD at MIX 0
    [(9, 127, NO_INST), (12, 0, NO_INST)],       # 6  SUB, RING at MIX 0
    [(4, 0, NO_INST), (6, 70, NO_INST)],         # 7  CHOR at MIX 0 kept (a mover before a voice insert), HARM
    [(13, 80, NO_INST), (XDLY, 50, 0)],          # 8  JUNO, XDLY
    [(6, 70, NO_INST), (11, 0, NO_INST)],        # 9  HARM, GATR at MIX 0
    [(5, 1, NO_INST), (FDN8, 0, 1)],             # 10 WIDE at MIX 1, FDN8 at MIX 0
    [(3, 0, NO_INST), (5, 100, NO_INST)],        # 11 FOLD at MIX 0, WIDE
    [(11, 127, NO_INST), (XDLY, 60, 1)],         # 12 GATR, XDLY
    [(13, 0, NO_INST), (2, 30, NO_INST)],        # 13 JUNO at MIX 0, TAPE
    [(XDLY, 30, 2), (10, 5, NO_INST)],           # 14 XDLY, DIST
    [(XDLY, 45, 3), (1, 127, NO_INST)],          # 15 XDLY, FUZZ
    [(XDLY, 20, NO_INST), (4, 0, NO_INST)],      # 16 XDLY FULL (the DSP has four), CHOR at MIX 0
]
VOICE = {1, 2, 3, 6, 9, 10, 11, 12}             # ins.c is_voice / is_mover
MOVER = {4, 5, 13, FDN8, XDLY}


def expected_states():
    """ins.c ins_slot_state for SLOTS (runs / mix_off / sent_type)"""
    def runs(t, j):
        y, _, inst = SLOTS[t][j]
        return y != 0 and not (y in (FDN8, XDLY) and inst == NO_INST)

    def mix_off(t, j):
        y, mix, _ = SLOTS[t][j]
        if not runs(t, j) or mix != 0:
            return False
        return not (j == 0 and y in MOVER and SLOTS[t][1][0] in VOICE and runs(t, 1) and not mix_off(t, 1))

    st = [[0, 0] for _ in range(16)]
    for t in range(16):
        for j in range(2):
            y, _, inst = SLOTS[t][j]
            if y == 0:
                st[t][j] = O.OFF
            elif y in (FDN8, XDLY) and inst == NO_INST:
                st[t][j] = O.FULL
            else:
                st[t][j] = O.RUNS if runs(t, j) and not mix_off(t, j) else O.MIX0
    return st


def pokes(lay):
    sel = bytes(SLOTS[t][j][0] for t in range(16) for j in range(2))
    mod = bytes(SLOTS[t][j][1] for t in range(16) for j in range(2))
    inst = bytes(SLOTS[t][j][2] for t in range(16) for j in range(2))
    return [f"poke:{lay['ins_sel']:#x}:{sel.hex()}", f"poke:{lay['ins_mod']:#x}:{mod.hex()}",
            f"poke:{lay['ins_inst']:#x}:{inst.hex()}"]


def ticks(n):
    return f"wait:{n * TICK / 1e6:.1f}"


def steps(lay):
    # 2026-11-17: after the snapshot's resume the page composes its next frame only when something on it changes
    # (main 01e1b641's own snapshot: the first frame at 88 M, none at 20 M -> "start" was "(no frame composed)");
    # the first frame's time depends on where the snapshot fell, so wait for it, bounded, as ship_gate's other menu
    # steps do (firstframe)
    s = ["firstframe:300", "wait:10", "png:start",
         f"press:{K_FX}", ticks(10), "png:t1_held", f"release:{K_FX}", ticks(20), "png:t1_fx",           # 1
         f"press:{K_FX}", ticks(HOLD), f"release:{K_FX}", ticks(20), "png:t1_hold"]
    s += [f"press:{K_FX}", ticks(30), "png:t2_values"]                                                # 2
    s += pokes(lay) + [ticks(140), "png:t3_ovw", ticks(60), "png:t3_ovw_b"]                           # 3
    s += [f"release:{K_FX}", ticks(20), "png:t4_after"]                                               # 4
    s += [f"press:{K_FX}", ticks(10), f"release:{K_FX}", ticks(20), "png:t5_ins1",                    # 5
          f"press:{K_FX}", ticks(HOLD), "png:t5_ins_values", f"release:{K_FX}", ticks(20), "png:t5_hold",
          f"press:{K_FX}", ticks(10), f"release:{K_FX}", ticks(20), "png:t5_ins2"]
    s += [f"press:{K_FX}", ticks(140), "png:t6_ovw", f"press:{K_NO}", ticks(5), f"release:{K_NO}", ticks(20),
          "png:t6_closed", f"release:{K_FX}", ticks(20), "png:t6_after"]                              # 6
    s += [f"press:{K_FUNC}", ticks(5), f"press:{K_FX}", ticks(10), f"release:{K_FX}", ticks(5),       # 7
          f"release:{K_FUNC}", ticks(20), "png:t7_send"]
    s += [f"press:{K_AMP}", ticks(10), f"release:{K_AMP}", ticks(20), "png:a1",                       # 8
          f"press:{K_AMP}", ticks(30), "png:a_held", ticks(140), "png:a_long", f"release:{K_AMP}", ticks(20),
          "png:a_rel", f"press:{K_AMP}", ticks(10), f"release:{K_AMP}", ticks(20), "png:a2",
          f"press:{K_AMP}", ticks(HOLD), f"release:{K_AMP}", ticks(20), "png:a2_hold"]
    s += [f"press:{K_SYN}", ticks(10), f"release:{K_SYN}", ticks(20), "png:s9",                     # 10
          f"press:{K_FX}", ticks(HOLD), "png:t10_held", f"release:{K_FX}", ticks(20), "png:t10_hold",
          f"press:{K_SYN}", ticks(10), f"release:{K_SYN}", ticks(20),
          f"press:{K_FX}", ticks(140), "png:t10_ovw", f"release:{K_FX}", ticks(20), "png:t10_after",
          f"press:{K_SYN}", ticks(10), f"release:{K_SYN}", ticks(20),
          f"press:{K_AMP}", ticks(HOLD), f"release:{K_AMP}", ticks(20), "png:a10_hold",
          f"press:{K_SYN}", ticks(10), f"release:{K_SYN}", ticks(20),
          f"press:{K_AMP}", ticks(140), f"release:{K_AMP}", ticks(20), "png:a10_long"]
    s += auto_steps(lay)                                                                              # 11
    return s


def mid(y):
    """M.SEL's value in the middle of type Y's band"""
    return (POS[y] * 128 + 64) // TYPES


def spins(enc, d):
    """D detents on ENC as plain turns of at most 8 each (the recorder step's turns are 3 and 9 detents)"""
    out = []
    while d:
        n = max(-8, min(8, d))
        out += [f"spin:{enc}:{n}"]
        d -= n
    return out


def auto_reads(lay):
    return [f"mem:{lay['ins_sel']:#x}:32", f"mem:{lay['ins_kv']:#x}:{32 * TYPES * 6}", f"mem:{lay['ins_fza']:#x}:32"]


def long_push_g():
    """FUNC + G's push held past 0.6 s (routes_pop.c mxp_poll's LONG), let go"""
    return [f"press:{K_FUNC}", ticks(5), f"press:{K_PUSH_G}", ticks(5), f"addl:{FRAMES:#x}:1000", "wait:15",
            f"release:{K_PUSH_G}", ticks(5), f"release:{K_FUNC}", ticks(20)]


def auto_steps(lay):
    """step 11: AUTO OFF on a pick, and FUNC + long push G -> OFF"""
    kv = bytearray([64] * (32 * TYPES * 6))
    for slot in range(32):
        for y in AUTO_K6:
            kv[(slot * TYPES + y) * 6 + 5] = 127
    s = [f"press:{K_FX}", ticks(10), f"release:{K_FX}", ticks(20),            # FX 1/3 (from AMP: on the press)
         f"press:{K_FX}", ticks(10), f"release:{K_FX}", ticks(20), "png:u_ins1",   # INSERT 1
         f"mem:{UI_TRACK:#x}:1", f"mem:{lay['ins_up']:#x}:4",
         f"poke:{lay['ins_sel']:#x}:{bytes(32).hex()}", f"poke:{lay['ins_selv']:#x}:{bytes(32).hex()}",
         f"poke:{lay['ins_kv']:#x}:{kv.hex()}", f"poke:{lay['ins_fza']:#x}:{bytes([127] * 32).hex()}", ticks(20)]
    s += auto_reads(lay)                                                     # read 0: before any pick
    at = 0
    for y in AUTO_PICKS:                                                     # reads 1..5: each pick
        s += spins(0, mid(y) - at) + [ticks(10)] + auto_reads(lay)
        at = mid(y)
    s += ["spin:6:1", ticks(10)] + auto_reads(lay)                          # read 6: TAPE's AUTO ON (G right)
    s += long_push_g() + auto_reads(lay) + ["png:u_tape_reset"]             # read 7: FUNC + long push G: OFF
    s += ["spin:1:3", ticks(10)] + auto_reads(lay)                          # read 8: B turns DRIV (page 1 kept)
    s += spins(0, mid(DIST) - at) + [ticks(10)] + auto_reads(lay)          # read 9: DIST picked again: OFF
    s += ["spin:6:1", ticks(10)] + auto_reads(lay)                          # read 10: DIST's AUTO ON
    s += long_push_g() + auto_reads(lay) + ["png:u_dist_reset"]             # read 11: OFF
    return s


def auto_facts(lay, mem):
    """step 11's facts from the reads, in order (mem: keys a second read of an address as ADDR@N)"""
    def reads(va):
        return [bytes.fromhex(v) for k, v in mem.items() if k.split("@")[0] == f"{va:#x}"]
    sel, kv, fza = reads(lay["ins_sel"]), reads(lay["ins_kv"]), reads(lay["ins_fza"])
    trk = reads(UI_TRACK)
    if not trk or len(sel) != 12 or len(kv) != 12 or len(fza) != 12:
        return {"11 the AUTO reads were taken": False}, {}
    slot = 2 * (trk[0][0] & 15)                                             # INSERT 1: slot j 0

    def state(i):
        y = sel[i][slot]
        k6 = kv[i][(slot * TYPES + y) * 6 + 5]
        on = fza[i][slot] > 63 if y in (FUZZ, TAPE) else k6 > 63 if y in AUTO_K6 else None
        return y, on, kv[i][(slot * TYPES + y) * 6:(slot * TYPES + y) * 6 + 6].hex()
    st = [state(i) for i in range(12)]
    facts = {"11 INSERT 1 up, every distortion's AUTO ON beforehand": st[0][0] == 0 and fza[0][slot] == 127
             and all(kv[0][(slot * TYPES + y) * 6 + 5] == 127 for y in AUTO_K6)}
    for i, y in enumerate(AUTO_PICKS, 1):
        facts[f"11 M.SEL turned to {('DIST', 'FOLD', 'FUZZ', 'HARM', 'TAPE')[i - 1]}: picked, AUTO OFF"] = \
            st[i][0] == y and st[i][1] is False
    facts["11 TAPE: G turned right: AUTO ON"] = st[6][0] == TAPE and st[6][1] is True
    facts["11 TAPE: FUNC + long push G: AUTO OFF"] = st[7][0] == TAPE and st[7][1] is False
    facts["11 ... FUNC let go: still page 1 (B turns DRIV, not AGE)"] = (
        kv[8][(slot * TYPES + TAPE) * 6] != kv[7][(slot * TYPES + TAPE) * 6]
        and kv[8][(slot * TYPES + TAPE) * 6 + 4] == kv[7][(slot * TYPES + TAPE) * 6 + 4])
    facts["11 DIST picked again: AUTO OFF"] = st[9][0] == DIST and st[9][1] is False
    facts["11 DIST: G turned right: AUTO ON"] = st[10][0] == DIST and st[10][1] is True
    facts["11 DIST: FUNC + long push G: AUTO OFF"] = st[11][0] == DIST and st[11][1] is False
    return facts, {"slot": slot, "states": st}


def bitmap(path):
    from PIL import Image                       # noqa: PLC0415 (the gate's venv has it)
    im = Image.open(path).convert("L")
    return [[1 if im.getpixel((x * SCALE + SCALE // 2, y * SCALE + SCALE // 2)) > 128 else 0 for x in range(128)]
            for y in range(64)]


def body(a):
    """below the title bar (its message slides in and out)"""
    return a[10:]


def diff(a, b):
    return sum(1 for y in range(64) for x in range(128) if a[y][x] != b[y][x])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--venv", default=sys.executable)
    p.add_argument("--root", default=str(HERE.parent))
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    from dnfw.mods import waverider as W        # noqa: PLC0415
    lay = W.SPEC["layout"]
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    js = work / "menu.json"
    cmd = [a.venv, "-u", str(HERE / "emu_waverider_menu.py"), "--root", a.root, "--build", a.build,
           "--snapshot", a.snapshot, "--png-dir", str(work / "screens"), "--json", str(js),
           "--steps", ",".join(steps(lay))]
    r = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
    (work / "menu.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0 or not js.exists():
        print(f"emulator rc {r.returncode}\n{(r.stdout + r.stderr)[-1500:]}")
        return 1
    res = json.loads(js.read_text())
    shots = {k: bitmap(v) for k, v in res["screens"].items() if str(v).endswith(".png")}
    st = expected_states()
    ty = [[SLOTS[t][j][0] for j in range(2)] for t in range(16)]
    best = min(((diff(shots["t3_ovw"], O.render(st, ty, trk, -1, b)), trk, b) for trk in range(16) for b in (True, False)))
    best_b = min(diff(shots["t3_ovw_b"], O.render(st, ty, best[1], -1, b)) for b in (True, False))
    ovw_model = O.render(st, ty, best[1], -1, True)
    facts = {
        "1 FX pressed on another page: FX 1/3 while still held": body(shots["t1_held"]) != body(shots["start"]),
        "1 ... let go: nothing more (FX 1/3)": body(shots["t1_fx"]) == body(shots["t1_held"]),
        "1 held past stock's first repeat (0.25 s) on stock's FX page, let go: no step":
            body(shots["t1_hold"]) == body(shots["t1_fx"]),
        "2 FX held on stock's FX page: stock's value view": shots["t2_values"] != shots["t1_fx"],
        "3 the overview, pixel for pixel": best[0] == 0,
        "3 ... and half a second later (blink, redraw)": best_b == 0,
        "4 let go: closed, the page under it": diff(shots["t4_after"], ovw_model) > 500 and body(shots["t4_after"]) == body(shots["t1_fx"]),
        "5 FX tapped on the FX page: another page (INSERT 1)": shots["t5_ins1"] != shots["t4_after"],
        "5 FX held on INSERT 1: our labels read values": shots["t5_ins_values"] != shots["t5_ins1"],
        "5 ... let go: no step (a hold, as stock reads one)": body(shots["t5_hold"]) == body(shots["t5_ins1"]),
        "5 ... then tapped: INSERT 2": body(shots["t5_ins2"]) != body(shots["t5_ins1"]),
        "6 held a second again: the overview": diff(shots["t6_ovw"], ovw_model) < 200,
        "6 another key closes it": diff(shots["t6_closed"], ovw_model) > 500,
        "6 FX let go after: no step": body(shots["t6_after"]) == body(shots["t6_closed"]),
        "7 FUNC + FX: stock's SEND page": shots["t7_send"] not in (shots["t6_after"], ovw_model),
        "8 AMP tapped: another page": body(shots["a1"]) != body(shots["t7_send"]),
        "8 AMP held on stock's AMP page: its values, no step": body(shots["a_held"]) != body(shots["a1"]),
        "8 AMP held 1.4 s: its own overview (scripts/emu_overviews.py), not the inserts'":
            body(shots["a_long"]) != body(shots["a_held"]) and diff(shots["a_long"], ovw_model) > 500,
        "8 AMP let go after the long hold: no step": body(shots["a_rel"]) == body(shots["a1"]),
        "8 AMP tapped again: our page 2 on the release": body(shots["a2"]) != body(shots["a1"]),
        "8 AMP held 0.25 s on our page 2, let go: no step": body(shots["a2_hold"]) == body(shots["a2"]),
        "10 SYN tapped: another page": body(shots["s9"]) != body(shots["a2_hold"]),
        "10 FX held on another page: FX 1/3 with its values while held (as held on FX 1/3)":
            body(shots["t10_held"]) == body(shots["t2_values"]),
        "10 ... held past the first repeat, let go: FX 1/3, no step": body(shots["t10_hold"]) == body(shots["t1_fx"]),
        "10 FX held a second on another page: the overview": diff(shots["t10_ovw"], ovw_model) < 200,
        "10 ... let go: closed, FX 1/3": body(shots["t10_after"]) == body(shots["t1_fx"]),
        "10 AMP held past the first repeat on another page, let go: AMP 1/3": body(shots["a10_hold"]) == body(shots["a1"]),
        "10 AMP held 1.4 s on another page, let go: AMP 1/3": body(shots["a10_long"]) == body(shots["a1"]),
        "9 no fault": not res.get("faults"),
    }
    af, auto_seen = auto_facts(lay, res.get("memory", {}))
    facts.update(af)
    out = {"facts": facts, "overview_diff": best[0], "overview_track": best[1], "blink_on": best[2],
           "screens": res["screens"], "states": st, "auto": auto_seen}
    (work / "overview.json").write_text(json.dumps(out, indent=1))
    for k, v in facts.items():
        print(f"  {'ok ' if v else 'BAD'} {k}")
    good = all(facts.values())
    print("OVERVIEW OK" if good else "OVERVIEW FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
