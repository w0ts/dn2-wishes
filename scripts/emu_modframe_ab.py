"""frame_ab.py --a A.syx --b B.syx --snapshot S [--frames N]: the modulation engine's frame (smoother, MOD SETUP, the
evaluator call with mx_eval) on two builds of the same tree layout, from the same worst-case set-up (modprof.configure,
every WAVE in turn), frame by frame: the mirror OUT (16 rows), the cascade's state (MOD_RAM), the LFO states and the
matrix's words must be byte for byte the same. Run from build B's tree. Prints the instructions a frame of each."""
import argparse
import json
import pathlib
import sys

TREE = pathlib.Path.cwd()
sys.path.insert(0, str(TREE / "scripts"))
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emu_matrix as MX                 # noqa: E402
import emu_modulation as MO             # noqa: E402
import emu_modprof as MP                    # noqa: E402

AREAS = ((0x800068E4, 34 + 202 * 16), (0x46AF8000, 0x800), (0x44640C18, 1920), (0x80005308, 64))


def run(build, snap, sym, wave, mode, frames):
    m = MX.setup(build, snap)
    MP.configure(m, sym, wave, mode, True)
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out, cost = [], 0
    for f in range(frames):
        _, a = m.cost(MO.SMOOTHER, MO.SRC)
        _, b = m.cost(MP.MODS_PASS, MO.OUT)
        _, c = m.cost(sym["mod_eval"], MO.OUT, rate, 0xFFFF, 0xFFFF if f % 7 == 0 else 0, o1, o2, 0)
        cost = max(cost, a + b + c)
        out.append(b"".join(bytes(m.read(at, n)) for at, n in AREAS))
    del m
    return out, cost


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--frames", type=int, default=24)
    p.add_argument("--waves", default="0,6,7,9,10,11")
    p.add_argument("--syma", required=True, help="build A's waverider_code.json")
    a = p.parse_args()
    sym = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    syma = json.loads(pathlib.Path(a.syma).read_text())["layout"]
    bad = 0
    for wave in [int(x) for x in a.waves.split(",")]:
        for mode in (0, 2, 4):
            ra, ca = run(a.a, a.snapshot, syma, wave, mode, a.frames)
            rb, cb = run(a.b, a.snapshot, sym, wave, mode, a.frames)
            diff = [f for f in range(a.frames) if ra[f] != rb[f]]
            print(f"wave {wave} mode {mode}: worst frame A {ca}, B {cb} ({cb - ca:+d}); "
                  f"{'the same' if not diff else f'DIFFER at frames {diff[:5]}'}", flush=True)
            bad += bool(diff)
    print("PASS: the same bytes every frame" if not bad else f"FAIL: {bad} cases differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
