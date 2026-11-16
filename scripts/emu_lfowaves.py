"""lfowaves on OS 1.12 in the ColdFire emulator: each new wave modulating and drawn (docs/lfo-112-port.md).

    emu_lfowaves.py --build BUILD.syx [--before WITHOUT.syx] [--snapshot SNAP] [--frames N] [--json OUT]

BUILD is our series with lfowaves applied, WITHOUT the same series without it (the control; by default made
from BUILD with lfowaves taken out: its edits back to stock, its chunk and its displaced-instruction record
gone). Both run on the same snapshot; lfowaves' chunk is written as the platform's loader writes it.

modulating  voice row 0's LFO1, SPD fast, DEP full, aimed at mirror slot 67 (FREQ), each WAVE 0..13, run
            through the frame's own path (the smoother, then our mod_eval, which calls stock's evaluator)
            for N frames; the value LFO1 leaves in slot 67 each frame. What must hold: waves 0..6 give the
            same values with and without lfowaves (stock's waves untouched); on BUILD each of 7..13 moves
            (not a constant), no two of 7..13 alike, none like RAND (6) or like what WITHOUT does with the
            same WAVE value (there clamped to 6); every value in 0..0x7f00.
cascade     LFO2 on RAND (WAVE 6) into FREQ, LFO1 into LFO2's WAVE (our cascade, csrc/modulation/cascade.c):
            with LFO1's depth 0 FREQ is the same with and without lfowaves; at full depth it differs, so the
            WAVE LFO2 runs goes past 6 on the build (the evaluator's clamp is 13 there): the cascade does not
            cut the new waves off.
drawn       the LFO1 page ([MOD]) with the active track's LFO1 WAVE set to each value: the WAVE formatter's
            text (record 79, through its formatter, which lfowaves hooks) is the wave's name, and the page's
            pixels differ for every wave (its glyph and SPH's label), SPH mid-way (a wavetable's glyph is
            its frame at POS: WTB1's and WTB2's first frames are the same sine).

Last line PASS or FAIL.
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

import emu_modulation as M                                      # noqa: E402

WAVES = 14                          # stock's 7 (0..6, RAND last) and lfowaves' 7
DEST_SLOT = 67                      # FREQ in a voice row of the mirror (emu_modulation's line scenario)
WAVE_REC, WAVE_SLOT = 79, 5         # LFO1 WAVE: its record and its slot in the sound (1.12 table)
SPH_SLOT, SPH_MID = 6, 0x4000       # LFO1 SPH (record 81): mid-way, where the wavetables' frames differ
                                    # (WTB1's and WTB2's first frames are the same sine, wavetables.py)
SOUND_VALUES = 20                   # a sound's value words from +20, by slot
MOD_KEY = (0, 5)                    # emulib.panel MOD: [MOD], LFO1's page first

checks: list[tuple[str, bool, str]] = []


def check(what, ok, detail=""):
    checks.append((what, bool(ok), detail))
    print(("  ok    " if ok else "  FAIL  ") + what + (f" -- {detail}" if detail else ""), flush=True)


def run_wave(build, snapshot, sym, wave, frames, dest=DEST_SLOT):
    """-> the values LFO1 leaves in DEST each frame, WAVE = wave"""
    m = M.machine(build, snapshot)
    frac = m.alloc(len(M.SET_FRAC))
    m.write(frac, M.SET_FRAC)
    m.flush()
    m.call(frac)
    v, s = 0, M.slot
    setting = {s(1, "SPD"): 0x7000, s(1, "MULT"): 6 << 8, s(1, "FADE"): 0x4000, s(1, "DEST"): dest << 8,
               s(1, "WAVE"): wave << 8, s(1, "SPH"): 0x4000, s(1, "MODE"): 0, s(1, "DEP"): M.TOP,
               s(2, "DEP"): 0, s(3, "DEP"): 0, dest: 0x4000}
    for sl, val in setting.items():
        M.w16(m, M.SRC + 2 * M.idx(v, sl), val)
        m.write(M.STATE + 4 * M.idx(v, sl), struct.pack(">I", val << 16))
        M.w16(m, M.OUT + 2 * M.idx(v, sl), val)
    rate = m.long(M.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out, bad = [], []
    for f in range(frames):
        m.call(M.SMOOTHER, M.SRC)
        m.call(sym["mod_eval"], M.OUT, rate, 1, 1, o1, o2, 0, limit=2_000_000)
        x = M.u16(m, M.OUT + 2 * M.idx(v, dest))
        out.append(x)
        if x > 0x7F00:
            bad.append((f, x))
    return out, bad


def scenario_modulating(a, sym, rep):
    seqs = {}
    for label, build in (("build", a.build), ("without", a.before)):
        for w in range(WAVES):
            out, bad = run_wave(build, a.snapshot, sym, w, a.frames)
            seqs[(label, w)] = out
            if bad:
                check(f"{label} WAVE {w}: every value in 0..0x7f00", False, f"{bad[:3]}")
    same_stock = [w for w in range(7) if seqs[("build", w)] == seqs[("without", w)]]
    check("waves 0..6: the same values with and without lfowaves", len(same_stock) == 7, f"same for {same_stock}")
    moving = {w: (min(seqs[("build", w)]), max(seqs[("build", w)])) for w in range(7, WAVES)}
    check("each new wave 7..13 moves FREQ", all(hi - lo > 0x800 for lo, hi in moving.values()),
          ", ".join(f"{w}: {lo:#06x}..{hi:#06x}" for w, (lo, hi) in moving.items()))
    distinct = len({tuple(seqs[("build", w)]) for w in range(7, WAVES)}) == 7
    check("no two of the new waves alike", distinct)
    not_rand = [w for w in range(7, WAVES) if seqs[("build", w)] in (seqs[("build", 6)], seqs[("without", w)])]
    check("none of them is RAND, nor what the build without lfowaves does with that WAVE", not not_rand,
          f"alike: {not_rand}")
    rep["modulating"] = {"range": {str(w): [f"{lo:#06x}", f"{hi:#06x}"] for w, (lo, hi) in moving.items()},
                         "frames": a.frames}


def run_cascade(build, snapshot, sym, frames, dep1):
    """LFO2 on RAND (WAVE 6) into FREQ; LFO1 at DEP1 into LFO2's WAVE (our cascade, cascade.c) -> FREQ a frame"""
    m = M.machine(build, snapshot)
    frac = m.alloc(len(M.SET_FRAC))
    m.write(frac, M.SET_FRAC)
    m.flush()
    m.call(frac)
    v, s = 0, M.slot
    setting = {s(1, "SPD"): 0x6000, s(1, "MULT"): 4 << 8, s(1, "FADE"): 0x4000, s(1, "DEST"): s(2, "WAVE") << 8,
               s(1, "WAVE"): 1 << 8, s(1, "SPH"): 0, s(1, "MODE"): 0, s(1, "DEP"): dep1,
               s(2, "SPD"): 0x7000, s(2, "MULT"): 6 << 8, s(2, "FADE"): 0x4000, s(2, "DEST"): DEST_SLOT << 8,
               s(2, "WAVE"): 6 << 8, s(2, "SPH"): 0x4000, s(2, "MODE"): 0, s(2, "DEP"): M.TOP,
               s(3, "DEP"): 0, DEST_SLOT: 0x4000}
    for sl, val in setting.items():
        M.w16(m, M.SRC + 2 * M.idx(v, sl), val)
        m.write(M.STATE + 4 * M.idx(v, sl), struct.pack(">I", val << 16))
        M.w16(m, M.OUT + 2 * M.idx(v, sl), val)
    rate = m.long(M.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out = []
    for _ in range(frames):
        m.call(M.SMOOTHER, M.SRC)
        m.call(sym["mod_eval"], M.OUT, rate, 1, 1, o1, o2, 0, limit=2_000_000)
        out.append(M.u16(m, M.OUT + 2 * M.idx(v, DEST_SLOT)))
    return out


def scenario_cascade(a, sym, rep):
    got = {(label, dep): run_cascade(build, a.snapshot, sym, a.frames, dep)
           for label, build in (("build", a.build), ("without", a.before)) for dep in (0, M.TOP)}
    check("LFO1's depth 0: LFO2 on RAND gives the same FREQ with and without lfowaves",
          got[("build", 0)] == got[("without", 0)])
    check("LFO1 into LFO2's WAVE at full depth: FREQ differs from the build without lfowaves "
          "(LFO2 runs waves past 6: the cascade does not cut the new waves off)",
          got[("build", M.TOP)] != got[("without", M.TOP)],
          f"frames differing {sum(x != y for x, y in zip(got[('build', M.TOP)], got[('without', M.TOP)]))} of {a.frames}")
    check("... every FREQ value in 0..0x7f00", all(x <= 0x7F00 for x in got[("build", M.TOP)]))
    rep["cascade"] = {"differing_frames": sum(x != y for x, y in zip(got[("build", M.TOP)], got[("without", M.TOP)]))}


def scenario_drawn(a, sym, rep, names):
    """(LFO1's page opened once with [MOD]; each WAVE then poked and the page asked to redraw: no page change, so
    the count of MOD pages -- three, four with lfo4 -- does not matter)"""
    from emulib.panel import Panel
    shots, texts = {}, {}
    for label, build in (("build", a.build), ("without", a.before)):
        m = M.machine(build, a.snapshot)
        panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/lfowaves").with_suffix("")) + f"_{label}_png")
        panel.settle(20_000_000)
        t = m.read(M.UI_TRACK, 1)[0]
        snd = m.long(M.KIT) + 52 + 1163 * t
        fmt = struct.unpack(">I", m.read(M.RECORDS + 60 * WAVE_REC + 0x34, 4))[0]
        buf = m.alloc(32)
        panel.tap(MOD_KEY)
        panel.settle(20_000_000)
        M.w16(m, snd + SOUND_VALUES + 2 * SPH_SLOT, SPH_MID)
        for w in range(WAVES):
            M.w16(m, snd + SOUND_VALUES + 2 * WAVE_SLOT, w << 8)
            m.write(buf, bytes(32))
            M.guest(m, fmt, w << 8, buf)
            texts[(label, w)] = m.read(buf, 16).split(b"\0")[0].decode("latin1")
            m.write(sym["smp_overlay_dirty"], struct.pack(">i", 1))   # the page redrawn from the sound, LFO1's page kept (1.12
            panel.settle(20_000_000)                    # redraws a poked value only when asked)
            shots[(label, w)] = pathlib.Path(panel.screen(f"wave{w:02d}")).read_bytes()
    new = [texts[("build", w)] for w in range(7, WAVES)]
    check("the WAVE formatter names the new waves", [x.upper() for x in new] == [n.upper() for n in names]
          or all(n.upper() in x.upper() for x, n in zip(new, names)), f"{new} (want {names})")
    check("stock's waves keep their names", [texts[("build", w)] for w in range(7)]
          == [texts[("without", w)] for w in range(7)], f"{[texts[('build', w)] for w in range(7)]}")
    check("the page differs for every wave on the build", len({shots[('build', w)] for w in range(WAVES)}) == WAVES,
          f"{len({shots[('build', w)] for w in range(WAVES)})} different screens of {WAVES}")
    check("stock's waves drawn as without lfowaves", all(shots[("build", w)] == shots[("without", w)] for w in range(7)),
          f"differ: {[w for w in range(7) if shots[('build', w)] != shots[('without', w)]]}")
    rep["drawn"] = {"texts": {f"{k[0]} {k[1]}": v for k, v in texts.items()}}


def without_lfowaves(build: str, out: pathlib.Path) -> str:
    """BUILD with lfowaves taken out, for the emulator only (never a unit): its edits back to stock 1.12's bytes,
    its CODE chunk at 0x46780000 and its displaced-instruction record (getShortName) gone; the rest as built"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.build import build as rebuild
    from dnfw.firmware.build import replacement
    from dnfw.firmware.load import load
    from dnfw.mods import lfowaves, platform
    fw = load(read_image(pathlib.Path(build)))
    base, chunks = platform.split(fw.container.find(3).unpack())
    content = bytearray(base)
    for e in lfowaves.EDITS:
        at, stock, new = e["va"] - lfowaves.BASE, bytes.fromhex(e["stock"]), bytes.fromhex(e["new"])
        if bytes(content[at:at + len(new)]) != new:
            raise SystemExit(f"{e['va']:#010x}: not lfowaves' bytes: is lfowaves in this build?")
        content[at:at + len(stock)] = stock
    kept = []
    for cid, data in chunks:
        if cid == platform.area.CODE and platform.area.CodeChunk.unpack(data).load == lfowaves.RUNTIME_VA:
            continue
        if cid == platform.DISP:
            data = b"".join(data[k:k + 12] for k in range(0, len(data), 12)
                            if struct.unpack_from(">I", data, k)[0] != lfowaves.SHORT_NAME)
            if not data:
                continue
        kept.append((cid, data))
    sec3 = platform.join(bytes(content), kept)
    out.write_bytes(rebuild(fw, {3: replacement(fw, 3, sec3, None)}))
    return str(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--build", required=True)
    p.add_argument("--before", default=None, help="the same build without lfowaves (default: made from BUILD, "
                   "lfowaves taken out)")
    p.add_argument("--snapshot", default=M.SNAP)
    p.add_argument("--frames", type=int, default=300)
    p.add_argument("--scenario", default="modulating,cascade,drawn")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    names = json.loads((HERE.parent / "src/dnfw/mods/lfowaves_code.json").read_text())["waves"]
    if a.before is None:
        a.before = without_lfowaves(a.build, pathlib.Path(a.json or "out/lfowaves").with_suffix(".without-EMUONLY.syx"))
        print(f"  the control: {a.before} (the build, lfowaves taken out)", flush=True)
    rep: dict = {}
    for sc in a.scenario.split(","):
        {"modulating": scenario_modulating, "cascade": scenario_cascade}.get(sc, lambda *_: None)(a, sym, rep)
        if sc == "drawn":
            scenario_drawn(a, sym, rep, names)
    rep["checks"] = [{"what": w, "ok": o, "detail": d} for w, o, d in checks]
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    bad = [w for w, o, _ in checks if not o]
    print("PASS" if not bad else f"FAIL: {bad[0]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
