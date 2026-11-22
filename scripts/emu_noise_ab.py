"""emu_noise_ab.py --build B --snapshot S (run from the tree, digikit's venv, as the other emu_ scripts): lfowaves' NOIS (0x46780640, from LF_NOISE) against the build's noise_fast, every
input class: colour 0..3 (SPH bits 5..6, bit 7 unused by both), loop 0..31, several instance keys, phases walking
forwards and backwards across wraps and jumps, with the 8-byte state carried. Each call: the same %d0, %d1, %d2-%d7 /
%a2 kept, the same 8 bytes written, the same stack words. Last line PASS or FAIL; instruction counts printed."""
import argparse
import json
import pathlib
import random
import struct
import sys

TREE = pathlib.Path.cwd()
sys.path.insert(0, str(TREE / "scripts"))
sys.path.insert(0, str(TREE / "src"))
import emu_modulation as MO             # noqa: E402

RAM = 0x46740000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    a = p.parse_args()
    from unicorn.m68k_const import (UC_M68K_REG_A2, UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_D2,
                                    UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7)
    from dnfw.waverider import lfofast
    sym = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    old = lfofast.values(None, json.loads((TREE / "src/dnfw/mods/lfowaves_code.json").read_text()))["NOISE"]
    new = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["c_text_symbols"]["noise_fast"]
    m = MO.machine(a.build, a.snapshot)
    keep = (UC_M68K_REG_D2, UC_M68K_REG_D3, UC_M68K_REG_D4, UC_M68K_REG_D5, UC_M68K_REG_D6, UC_M68K_REG_D7,
            UC_M68K_REG_A2)
    rnd = random.Random(1)
    bad, n, cost = [], 0, {"old": 0, "new": 0}

    def run(fn, phase, d1, state_at, state):
        m.write(state_at, state)
        for k, r in enumerate(keep):
            m.uc.reg_write(r, 0x11111111 * (k + 1))
        m.uc.reg_write(UC_M68K_REG_D1, d1)
        m.flush()
        res, c = m.cost(fn, phase)
        regs = tuple(m.uc.reg_read(r) for r in keep)
        return (res & 0xFFFFFFFF, m.uc.reg_read(UC_M68K_REG_D1) & 0xFFFFFFFF, regs,
                bytes(m.read(state_at, 8))), c

    for colour in range(4):
        for loop in list(range(0, 32, 3)) + [30, 31]:
            for key in (0, 1, 511, 1023):
                sph = (colour << 5) | loop
                d1 = (key << 8) | sph
                state_at = RAM + 8 * key
                state = struct.pack(">II", rnd.getrandbits(32) if key == 1023 else 0, rnd.getrandbits(32) if key == 511 else 0)
                phase = rnd.getrandbits(32)
                for i in range(90):
                    step = rnd.choice((1 << 26, 3 << 25, -(1 << 26), 1 << 30, -(3 << 29), rnd.getrandbits(32), 1 << 20))
                    phase = (phase + step) & 0xFFFFFFFF
                    ro, co = run(old, phase, d1, state_at, state)
                    rn, cn = run(new, phase, d1, state_at, state)
                    cost["old"] += co
                    cost["new"] += cn
                    n += 1
                    if ro != rn:
                        bad.append((colour, loop, key, hex(phase), ro, rn))
                    state = ro[3]
    print(f"calls {n}; instructions old {cost['old'] / n:.1f}, new {cost['new'] / n:.1f} a call (all colours)")
    if bad:
        print("first differences:", bad[:4])
        print(f"FAIL: {len(bad)} of {n} differ")
        return 1
    print(f"PASS: noise_fast = NOIS on {n} calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
