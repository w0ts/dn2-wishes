"""The page keys' overviews (SYN, FLTR, MOD, AMP held a second; csrc/inserts/ovw.c, ovw_draw.c) in the ColdFire emulator.

    python scripts/emu_overviews.py --venv PY --root ROOT --build BUILD_DIR --snapshot SNAP --work DIR

One emulator run (scripts/emu_waverider_menu.py), the panel's own key bytes. Before the holds the kit is given known
data: tracks 2-16 other machines, filters and engines (the bytes MACHINE SEL and the knobs write), two tracks muted,
stock DESTs on three LFOs, four voice slots sounding with the DSP's per-slot costs. Then, for each of SYN, FLTR, MOD
and AMP in turn:
  1. tapped: the page changes on the release (stock's own step, untouched);
  2. held 0.5 s: stock's value view (the screen changes), no overview; let go: no step;
  3. held 1.3 s: the overview, pixel for pixel dnfw.overviews.render with the data read back from the emulator's RAM
     (the sounds, the voice records, the per-slot costs, the VOICE BUDGET's stock costs); again 0.5 s later (redrawn);
  4. let go: closed, no step (the page of step 1).
After SYN's turn, SYN held a second and NO pressed: closed; let go, the page changed as stock 1.12's does for the same
keys from its SYN page (a second run, stock on its own snapshot). The overview's redraws went alone over the
glass at least once (ovw_alone), and no fault. Then the VOICE key's overview (scripts/emu_voice_overview.py: stock's
VOICE menu on a tap or a 0.5 s hold, pixel for pixel stock 1.12's; held 1.3 s its overview as the model; its release
leaving the screen as before; another key closing it; FUNC + VOICE the RECORDER; stock 1.12 as the negative control). Exit 0 and "OVERVIEWS OK" when every fact holds (WORK/overviews.json).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
O = importlib.import_module("dnfw.overviews")   # (after the path: the tree's own dnfw)

K_SYN, K_FLTR, K_AMP, K_MOD, K_NO = 2, 3, 4, 6, 12
TICK = 1_100_000                        # emulator instructions a panel tick (121 ticks a second)
SCALE = 6
SOUND_STRIDE, SOUND_AT = 1163, 52
KIT_POINTER = 0x800052A0
MUTE, SOLO, PTN_MUTE = 0x80005218, 0x8000521C, 0x4058E888
VOICES, HELD = 0x40288304, 0x4059DD1C   # load.c VOICE(v) (+1 the owner track), the held slots
UI_TRACK = 0x42432A6C
LFO_DEST_SLOTS = (4, 12, 20)            # LFO1-3 DEST's slots (records 78, 88, 98; read back and checked below)
REC_TAIL = 2000 // 16                   # dnfw.load TAIL: a slot's cost / 16 over this is sounding

# (track, type, filter, engine word): machines, filters and engines given to tracks 2..16 (index 1..15)
KIT = [(1, 1, 1, None), (2, 2, 2, None), (3, 3, 3, None), (4, 4, 0, None), (5, 5, 0, 0x2000), (6, 6, 4, 0x7F00),
       (7, 18, 5, 0x4000), (8, 20, 7, 0x0000), (9, 22, 8, 0x5000), (10, 23, 9, None), (11, 19, 10, None),
       (12, 21, 11, None), (13, 8, 0, None), (14, 17, 0, None), (15, 12, 1, None)]
MUTED_BITS = (1 << 3) | (1 << 9)
LFO_SET = [(2, 0), (5, 1), (5, 2)]      # (track, LFO): a stock DEST set (slot value 0x0500: DEST 5)
SLOTS_SOUNDING = [(0, 7, 0x0400, 1), (1, 7, 0x0400, 0), (2, 9, 0x1000, 1), (3, 1, 0, 1)]   # (slot, track, cost, held)


def ticks(n: float) -> str:
    return f"wait:{n * TICK / 1e6:.1f}"


# -- the model's names, from dnfw's own tables (what page.c reads from wr_gen.h) ---------------------------------------

def _tables():
    return tuple(importlib.import_module(m) for m in ("dnfw.waverider.pages", "dnfw.mnm.machines",
                                                         "dnfw.perc.machines", "dnfw.perc.program"))


def _word(snd: bytes, slot: int) -> int:
    return struct.unpack_from(">H", snd, 0x14 + 2 * slot)[0]


def _choice(PG, M, snd: bytes, name: str) -> str:
    """M's control NAME on this sound, as page.c mnm_text names it ("" a knob)"""
    names = PG._choices(M).get(name, 0)
    if not isinstance(names, tuple):
        return ""
    j = PG.mnm_pnames(M).index(name)
    _rid, slot, lo, top = PG.MNM_RECS[j][:4]
    v = min(max((_word(snd, slot) >> 8) - lo, 0), top)
    k = (v * 127 * 2 + top) // (2 * top)
    c = (k * len(names)) >> 7
    if names[c] == "":
        c -= 1
    return names[c]


def syn_names(snd: bytes) -> tuple[str, str]:
    PG, MM, P = _tables()[:3]
    ty = struct.unpack_from(">b", snd, 0xDE)[0]
    if ty < 0:
        return "", ""
    if ty == 5:
        v = min(max(_word(snd, P.TYPE_REC[1]) >> 8, 0), 127)
        fam, _, eng = P.NAMES[(v * P.N) >> 7].partition("-")
        return fam[:3], eng[:3]
    kind = ty - 4
    if kind in PG.MNM_KINDS:
        mi = PG.MNM_KINDS.index(kind)
        mach = MM.CF_ALL_LIST_NAMES[mi][1].upper()
        M = MM.CF_ALL[mi]
        h = MM.HOST_BY_NAME.get(getattr(M, "HOST", None))
        if h is not None and mi == MM.CF_HOST_PLACES[h.NAME][0]:   # a host (MONOMACHINE, DRUM): its SEL's place
            w = _word(snd, PG.MNM_RECS[h.J][1]) >> 8
            e = sum(w >= t for t in PG.host_thresholds(h))
            live = MM.CF_ALL[MM.CF_HOST_PLACES[h.NAME][e]]
            return mach, _choice(PG, live, snd, PG.mnm_pnames(live)[h.J])
        for name, sh in (("PLAITS", "MODL"), ("SOPHIE", "MODL"), ("ANALOG2", "FLT2")):
            if M.NAME == name:
                return mach, _choice(PG, M, snd, sh)
        return mach, ""
    return O.MACHINE4.get(ty, ""), ""


def flt_names(snd: bytes) -> tuple[str, str]:
    PG, MM = _tables()[:2]
    ty = struct.unpack_from(">b", snd, 0xDE)[0]
    if ty < 0 or ty == 4:
        return "", ""
    a = O.FILTER3.get(snd[0xDF], "")
    kind = ty - 4
    if kind in PG.MNM_KINDS and MM.CF_ALL[PG.MNM_KINDS.index(kind)].NAME == "ANALOG2":
        return a, _choice(PG, MM.CF_ALL[PG.MNM_KINDS.index(kind)], snd, "FLT2")
    return a, ""


def stock_lfo(snd: bytes) -> tuple[int, int]:
    """LFO1-3 with a stock DEST -> (bits, count). (The routes record of the snapshot's kit is empty: checked by the
    count's agreement; LFO4 at its defaults: no DEST.)"""
    bits = sum(1 << l for l, s in enumerate(LFO_DEST_SLOTS) if _word(snd, s) >> 8)
    return bits, bin(bits).count("1")


# -- the run --------------------------------------------------------------------------------------------------------

def pokes(lay) -> list[str]:
    PG, MM, P = _tables()[:3]
    out = []
    for t, ty, f, w in KIT:
        out += [f"psound:{t}:0xde:{ty & 0xFF:02x}{f:02x}"]
        if w is None:
            continue
        if ty == 5:
            slot = P.TYPE_REC[1]
        else:
            M = MM.CF_ALL[PG.MNM_KINDS.index(ty - 4)]
            name = {"PLAITS": "MODL", "SOPHIE": "MODL", "ANALOG2": "FLT2"}.get(M.NAME)
            slot = PG.MNM_RECS[MM.MONO_ENGINE_K if name is None else PG.mnm_pnames(M).index(name)][1]
        out.append(f"psound:{t}:{0x14 + 2 * slot:#x}:{w:04x}")
    for t, lfo in LFO_SET:
        out.append(f"psound:{t}:{0x14 + 2 * LFO_DEST_SLOTS[lfo]:#x}:0500")
    out += [f"poke:{MUTE:#x}:{MUTED_BITS:08x}", f"poke:{SOLO:#x}:00000000", f"poke:{PTN_MUTE:#x}:0000"]
    held = 0
    for v, t, cost, h in SLOTS_SOUNDING:
        out += [f"poke:{VOICES + 20 * v + 1:#x}:{t:02x}", f"poke:{lay['smp_tlm_cost'] + 2 * v:#x}:{cost:04x}"]
        held |= h << v
    out.append(f"poke:{HELD:#x}:{held:08x}")
    return out


def reads(lay) -> list[str]:
    """what the model needs, read when the overview is up"""
    return ["sounds", f"mem:{VOICES:#x}:320", f"mem:{HELD:#x}:4", f"mem:{lay['smp_tlm_cost']:#x}:32",
            f"mem:{lay['load_stock']:#x}:32", f"mem:{UI_TRACK:#x}:1", f"mem:{MUTE:#x}:8", f"mem:{PTN_MUTE:#x}:2"]


KEYS = (("syn", K_SYN), ("fltr", K_FLTR), ("mod", K_MOD), ("amp", K_AMP))


def steps(lay) -> list[str]:
    s = ["firstframe:300", "wait:10", "png:start", f"mem:{lay['ovw_alone']:#x}:4"]
    s += pokes(lay) + [ticks(10)]
    for n, k in KEYS:
        s += [f"png:{n}_pre", f"press:{k}", ticks(10), f"release:{k}", ticks(20), f"png:{n}_tap",
              f"press:{k}", ticks(60), f"png:{n}_h05", f"release:{k}", ticks(20), f"png:{n}_r05",
              f"press:{k}", ticks(150), f"png:{n}_ovw"] + reads(lay) + [
              ticks(60), f"png:{n}_ovw2", f"release:{k}", ticks(20), f"png:{n}_after"]
        if n == "syn":                          # on SYN's page: held a second, NO, let go (as stock_steps)
            s += NO_SEQ
    s += [f"mem:{lay['ovw_alone']:#x}:4", f"mem:{lay['ovw_opens']:#x}:4"]
    return s


# SYN held a second, NO tapped, SYN let go, from SYN's page; the same on stock (stock_steps): NO acts on stock's page
NO_SEQ = ["png:no_pre", f"press:{K_SYN}", ticks(150), "png:no_ovw", f"press:{K_NO}", ticks(5), f"release:{K_NO}",
          ticks(20), "png:no_closed", f"release:{K_SYN}", ticks(20), "png:no_after"]


def stock_steps() -> list[str]:
    return ["firstframe:300", "wait:10", f"press:{K_SYN}", ticks(10), f"release:{K_SYN}", ticks(20)] + NO_SEQ


def model(n: str, m: dict) -> tuple[list, int]:
    """the overview NAME as dnfw.overviews draws it from the RAM read while it was up -> (picture, title's x end
    compared: AMP's C is the meter's, not modelled)"""
    snds = [bytes.fromhex(m["sounds"])[SOUND_STRIDE * t:SOUND_STRIDE * (t + 1)] for t in range(16)]
    track = bytes.fromhex(m[f"{UI_TRACK:#x}"])[0] & 15
    mute, solo = struct.unpack(">II", bytes.fromhex(m[f"{MUTE:#x}"]))
    ptn = struct.unpack(">H", bytes.fromhex(m[f"{PTN_MUTE:#x}"]))[0]
    muted = [bool((mute | ptn) >> t & 1 or (solo & 0xFFFF and not solo >> t & 1)) for t in range(16)]
    x1 = 128
    if n == "syn":
        left, right, cells = O.syn_cells([syn_names(s) for s in snds], muted)
    elif n == "fltr":
        left, right, cells = O.flt_cells([flt_names(s) for s in snds])
    elif n == "mod":
        nomidi = [struct.unpack_from(">b", s, 0xDE)[0] not in (-1, 4) and struct.unpack_from(">b", s, 0xDE)[0] >= 0
                  for s in snds]
        lf = [stock_lfo(s) if ok else (0, 0) for s, ok in zip(snds, nomidi)]
        left, right, cells = O.lfo_cells([b for b, _ in lf], [c for _, c in lf], [0] * 16, sum(c for _, c in lf))
    else:
        owners = [bytes.fromhex(m[f"{VOICES:#x}"])[20 * v + 1] for v in range(16)]
        held = struct.unpack(">I", bytes.fromhex(m[f"{HELD:#x}"]))[0]
        cost = struct.unpack(">16H", bytes.fromhex(m[f"{lay_g['smp_tlm_cost']:#x}"]))
        stock = struct.unpack(">16H", bytes.fromhex(m[f"{lay_g['load_stock']:#x}"]))
        voices, cyc = [0] * 16, [0] * 16
        for v in range(16):
            t = owners[v]
            if t > 15:
                continue
            busy = cost[v] > REC_TAIL
            voices[t] += busy or bool(held >> v & 1)
            cyc[t] += stock[t] if stock[t] else (cost[v] * 16 if busy else 0)
        left, right, cells = O.amp_cells(voices, cyc, -1, -1)
        x1 = 64                                 # the title's right end: the meter's C (not modelled), D
    return O.render(left, right, cells, track), x1


lay_g: dict = {}


def bitmap(path):
    Image = importlib.import_module("PIL.Image")   # the gate's venv has it
    im = Image.open(path).convert("L")
    return [[1 if im.getpixel((x * SCALE + SCALE // 2, y * SCALE + SCALE // 2)) > 128 else 0 for x in range(128)]
            for y in range(64)]


def body(a):
    return a[10:]


def diff(a, b, x1: int = 128) -> int:
    return sum(1 for y in range(len(a)) for x in range(x1) if a[y][x] != b[y][x])


def run_emu(a, work: pathlib.Path, name: str, st: list[str], stock: bool = False) -> dict:
    js = work / f"{name}.json"
    target = (["--stock", "--snapshot", str(pathlib.Path(a.snapshot).parent / "ui1200M.snap")] if stock
              else ["--build", a.build, "--snapshot", a.snapshot])   # stock 1.12 on its own snapshot, beside the build's
    cmd = [a.venv, "-u", str(HERE / "emu_waverider_menu.py"), "--root", a.root, *target,
           "--png-dir", str(work / name), "--json", str(js), "--steps", ",".join(st)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
    (work / f"{name}.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0 or not js.exists():
        raise SystemExit(f"emulator rc {r.returncode}\n{(r.stdout + r.stderr)[-1500:]}")
    return json.loads(js.read_text())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--venv", default=sys.executable)
    p.add_argument("--root", default=str(HERE.parent))
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--work", required=True)
    a = p.parse_args()
    lay = importlib.import_module("dnfw.mods.waverider").SPEC["layout"]
    work = pathlib.Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    lay_g.update(lay)
    res = run_emu(a, work, "run", steps(lay))
    shots = {k: bitmap(v) for k, v in res["screens"].items() if str(v).endswith(".png")}
    mems = res.get("mems") or res.get("memory") or {}
    facts, diffs = {}, {}
    order = list(mems.items())
    for n, _k in KEYS:
        def g(x: str, n: str = n) -> list:
            return shots[f"{n}_{x}"]
        # the RAM read while this overview was up: the reads() keys, the last of each before ITS png (in order)
        m = _reads_for(order, n)
        pic, x1 = model(n, m)
        d1, d2 = diff(g("ovw"), pic, x1), diff(g("ovw2"), pic, x1)
        diffs[n] = (d1, d2)
        facts[f"{n} tapped: the page changes on the release"] = body(g("tap")) != body(g("pre"))
        facts[f"{n} held 0.5 s: the value view, no overview"] = g("h05") != g("tap") and diff(g("h05"), pic) > 300
        facts[f"{n} ... let go: no step"] = body(g("r05")) == body(g("tap"))
        facts[f"{n} held 1.3 s: the overview, pixel for pixel"] = d1 == 0
        facts[f"{n} ... redrawn 0.5 s later, the same"] = d2 == 0
        facts[f"{n} let go: closed, no step"] = body(g("after")) == body(g("tap"))
    facts["SYN held, NO: the overview closes"] = diff(shots["no_closed"], shots["no_ovw"]) > 300
    # (stock's own SYN + NO acts on its page: 98 pixels on stock and ours alike, measured; the release adds nothing)
    st = run_emu(a, work, "stock", stock_steps(), stock=True)
    ss = {k: bitmap(v) for k, v in st["screens"].items() if str(v).endswith(".png")}
    ours_no, stock_no = diff(body(shots["no_after"]), body(shots["no_pre"])), diff(body(ss["no_after"]), body(ss["no_pre"]))
    facts["... SYN let go after: what stock's SYN + NO does (the same pixels change)"] = ours_no == stock_no
    diffs["no"] = (ours_no, stock_no)
    alone = [int(v, 16) for k, v in order if k.startswith(f"{lay['ovw_alone']:#x}")]
    facts["the redraws went alone over the glass"] = len(alone) == 2 and alone[1] > alone[0]
    facts["no fault"] = not res.get("faults")
    # 2026-11-19: VOICE held a second, its overview (csrc/inserts/ovw.c, scripts/emu_voice_overview.py)
    vr = subprocess.run([a.venv, "-u", str(HERE / "emu_voice_overview.py"), "--build", a.build, "--snapshot", a.snapshot,
                         "--work", str(work / "voice")], capture_output=True, text=True, env=os.environ.copy())
    (work / "voice.log").write_text(vr.stdout + vr.stderr)
    print("\n".join(ln for ln in vr.stdout.splitlines() if ln.startswith("  ")))
    facts["VOICE: stock's menu on a tap; held a second, its overview (emu_voice_overview.py)"] = (
        vr.returncode == 0 and "VOICE OVERVIEW OK" in vr.stdout)
    out = {"facts": facts, "diffs": diffs, "screens": res["screens"], "alone": alone}
    (work / "overviews.json").write_text(json.dumps(out, indent=1))
    for k, v in facts.items():
        print(f"  {'ok ' if v else 'BAD'} {k}")
    good = all(facts.values())
    print("OVERVIEWS OK" if good else f"OVERVIEWS FAILED {diffs}")
    return 0 if good else 1


def _reads_for(order: list, n: str) -> dict:
    """the reads() taken while overview N was up: the k-th group of them (KEYS' order), by key prefix"""
    idx = [i for i, (k, _v) in enumerate(order) if k.startswith("sounds")]
    k = [x for x, _ in KEYS].index(n)
    i0 = idx[k]
    out = {}
    for key, v in order[i0:i0 + 8]:
        out[key.split("@")[0]] = v
    return out


if __name__ == "__main__":
    sys.exit(main())
