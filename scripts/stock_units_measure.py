"""Measure what a stock parameter's knob does, in Elektron's own DSP code run in the SHARC runner
(docs/stock-units.md, phase 2: "what value corresponds to what value with unit").

    python scripts/stock_units_measure.py filter --image STOCK.syx --cf 0 --knob 64 [--reso 0] [--note 36]
    python scripts/stock_units_measure.py env --image STOCK.syx --param atk --knob 64 [--blocks 60]

`filter`: track 0 on WaveTone (its default sound, a note low enough that its harmonics are dense), rendered twice
from the same fresh state: once with no filter (ColdFire filter type 6 -> the DSP's 0), once with filter type CF at
FREQ = KNOB (frame index 67, value knob << 8). Both are read at the amp stage's input (`m5.AMP_STAGE`, after the
filter, before the amp), so the machine's own output is the filter's input in both runs (the render is deterministic:
a fresh state each run). |H| = |out| / |in| at each harmonic (a Hann-windowed DFT at the harmonic's frequency over
the last WINDOW samples, after SKIP blocks for the knob's smoothing). Printed as one JSON line: the harmonics'
frequencies, |H| in dB and its phase (unwrapped along the harmonics), and where the phase passes -90 and -180 degrees
(a 2-pole low-pass's cutoff is its -90 degree point, whatever its resonance; a 4-pole's the -180 degree one).

Runs inside the bench container (scratch/bench/run112.sh), one process a knob value: about 20 blocks a minute.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import sharc_waverider_m5 as m5                 # noqa: E402
from dnfw.waverider import frame as FR           # noqa: E402

FREQ_INDEX, RESO_INDEX = 67, 68
NO_FILTER = 6                                    # ColdFire filter type 6: the DSP's 0, no filter
WAVETONE = 1
FS = 48000.0
# the same input in every run: WaveTone's random parts off (its default sound drifts and has noise, so two renders
# differed): DRIF (record 252 = slot 39) 0, the noise level (256 = slot 43) 0, the oscillators' phase reset (249 =
# slot 36) ON (1; OFF 0, RAND 2)
STEADY = {39: 0x0000, 43: 0x0000, 36: 0x0100}
# a broadband input for the filter: the oscillators' levels (LEV1 241 = slot 28, LEV2 245 = slot 32) 0, the noise
# level 127 and its hold (HOLD 254 = slot 41) 127 so it does not fall; the noise generator starts from the same
# state in each run (a fresh state), so both renders carry the same noise
NOISE = {39: 0x0000, 36: 0x0100, 28: 0x0000, 32: 0x0000, 43: 0x7F00, 41: 0x7F00}


def _setup(a):
    dk = m5.m1.Digikit(a.digikit)
    m5.fx.bind(str(a.digikit / "tools"))
    m5.m4.IMAGE = a.image
    stock = m5.m1.dn2_section7(a.image)
    sound, machines = m5.m4.init_sound(a.image)
    return dk, stock, sound, machines, m5.Image(dk, stock)


def _render(init, sound, machines, cf: int, knob: int, reso: int, note: int, blocks: int, src=STEADY) -> list[float]:
    def frames(b):
        f = m5.base_frame(sound, machines, t0=WAVETONE, note=note << 8, trigger=(b == 1), overrides=src)
        f.header(FR.FILTER, 0, cf)
        f.param(0, FREQ_INDEX, knob << 8)
        f.param(0, RESO_INDEX, reso << 8)
        return f.to_bytes()
    r = m5.run_blocks(init, frames, blocks)
    if not r["ok"]:
        raise SystemExit(f"halted: {r.get('halt')}")
    return list(r["amp_in"])


def _dft(x: list[float], f: float) -> complex:
    n = len(x)
    w = -2.0 * math.pi * f / FS
    s = 0j
    for i, v in enumerate(x):
        h = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / (n - 1))
        s += v * h * complex(math.cos(w * i), math.sin(w * i))
    return s


def filter_cmd(a) -> int:
    dk, stock, sound, machines, img = _setup(a)
    blocks = a.skip + a.window // m5.BLOCK
    with tempfile.TemporaryDirectory() as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, img)
        src = NOISE if a.source == "noise" else STEADY
        x = _render(init, sound, machines, NO_FILTER, a.knob, a.reso, a.note, blocks, src)[-a.window:]
        init = m5.init_on(snap, m2mach, img)
        y = _render(init, sound, machines, a.cf, a.knob, a.reso, a.note, blocks, src)[-a.window:]
    # the frequencies H is read at: the note's harmonics (a tone) or every DFT bin (noise)
    f0 = 440.0 * 2.0 ** ((a.note - 69) / 12.0) if a.source == "tone" else FS / a.window
    pts = []
    k, last, turns = 1, 0.0, 0.0
    xs = []
    while k * f0 < min(a.fmax, FS / 2 * 0.95):
        xs.append((k, _dft(x, k * f0)))
        k += a.step
    floor = max(abs(X) for _k, X in xs) * 10.0 ** (-a.floor_db / 20.0)
    for k, X in xs:                                       # harmonics the input carries (not its near-zeros)
        Y = _dft(y, k * f0)
        if abs(X) > floor:
            h = Y / X
            ph = math.degrees(math.atan2(h.imag, h.real))
            while ph + turns - last > 180.0:          # unwrapped along the harmonics
                turns -= 360.0
            while ph + turns - last < -180.0:
                turns += 360.0
            last = ph + turns
            pts.append((round(k * f0, 2), round(20.0 * math.log10(max(abs(h), 1e-12)), 3), round(last, 2)))
    def crossing(deg):                                   # the first frequency where the phase passes DEG
        for (f1, _d1, p1), (f2, _d2, p2) in zip(pts, pts[1:]):
            if (p1 - deg) * (p2 - deg) <= 0 and p1 != p2:
                return round(f1 + (f2 - f1) * (deg - p1) / (p2 - p1), 2)
        return None
    print(json.dumps({"cf": a.cf, "knob": a.knob, "reso": a.reso, "note": a.note, "f0": round(f0, 3),
                      "phase90_hz": crossing(-90.0), "phase180_hz": crossing(-180.0),
                      "peak_hz": max(pts, key=lambda q: q[1])[0] if pts else None, "h": pts}))
    return 0


AMP_INDEX = {"atk": 81, "hold": 82, "dec": 83, "sus": 84, "rel": 85}


def env_cmd(a) -> int:
    """the amp envelope: track 0 on WaveTone, every amp field at OVERRIDES (attack 0, hold 0, decay 0, sustain 127
    unless named), the one measured at KNOB; the envelope's gain each block = rms(amp out) / rms(amp in) (the amp
    stage's own input and output, so the machine's level cancels). Printed: the gain per block (the law and the time
    are read from it: a linear attack's slope, an exponential decay's ratio a block)"""
    dk, stock, sound, machines, img = _setup(a)
    fields = {"atk": 0, "hold": 0, "dec": 0, "sus": a.sus, "rel": 0}
    fields[a.param] = a.knob
    with tempfile.TemporaryDirectory() as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, img)

        def frames(b):
            f = m5.base_frame(sound, machines, t0=WAVETONE, note=a.note << 8, trigger=(b == 1), overrides=STEADY)
            f.header(FR.FILTER, 0, NO_FILTER)
            for name, v in fields.items():
                f.param(0, AMP_INDEX[name], v << 8)
            return f.to_bytes()
        r = m5.run_blocks(init, frames, a.blocks)
        if not r["ok"]:
            raise SystemExit(f"halted: {r.get('halt')}")
    xi, xo = list(r["amp_in"]), list(r["amp_out"])
    g = []
    for b in range(len(xi) // m5.BLOCK):
        i = math.sqrt(sum(v * v for v in xi[b * m5.BLOCK:(b + 1) * m5.BLOCK]) / m5.BLOCK)
        o = math.sqrt(sum(v * v for v in xo[b * m5.BLOCK:(b + 1) * m5.BLOCK]) / m5.BLOCK)
        g.append(round(o / i, 6) if i > 1e-9 else None)
    # the first blocks sample by sample (an attack shorter than a block): |out| / |in| where the input is not small
    peak = max(abs(v) for v in xi[:4 * m5.BLOCK]) or 1.0
    ramp = [(n, round(abs(xo[n]) / abs(xi[n]), 6)) for n in range(4 * m5.BLOCK) if abs(xi[n]) > 0.2 * peak]
    print(json.dumps({"param": a.param, "knob": a.knob, "block_ms": m5.BLOCK / FS * 1000.0, "gain": g, "ramp": ramp}))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("what", choices=["filter", "env"])
    p.add_argument("--param", choices=sorted(AMP_INDEX), default="atk")
    p.add_argument("--blocks", type=int, default=60)
    p.add_argument("--sus", type=int, default=127, help="the amp sustain while another field is measured")
    p.add_argument("--image", type=pathlib.Path, required=True)
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC", ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--cf", type=int, default=0, help="ColdFire filter type (0 Multimode .. 5 Comb+)")
    p.add_argument("--knob", type=int, required=True)
    p.add_argument("--reso", type=int, default=0)
    p.add_argument("--note", type=int, default=36)
    p.add_argument("--source", choices=["tone", "noise"], default="noise")
    p.add_argument("--skip", type=int, default=32, help="blocks before the window (the knob's smoothing)")
    p.add_argument("--window", type=int, default=4096)
    p.add_argument("--step", type=int, default=1, help="every STEP-th harmonic")
    p.add_argument("--fmax", type=float, default=20000.0)
    p.add_argument("--floor-db", type=float, default=50.0, help="harmonics this far under the input's strongest are left out")
    a = p.parse_args()
    return filter_cmd(a) if a.what == "filter" else env_cmd(a)


if __name__ == "__main__":
    raise SystemExit(main())
