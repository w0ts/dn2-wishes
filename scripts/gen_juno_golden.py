"""Write test/data/juno_cho_golden.npz: Optimist's JUNO CHORUS (firmware/src/fx/junocho/juno_cho.h, the User's own,
GPL-3.0-only) rendered on the host at its own rate (44.1 kHz), so the tests can hold dnfw.inserts.postref's JUNO
(design.juno_consts(44100)) to it without Optimist's tree.

    python scripts/gen_juno_golden.py [OPTIMIST_ROOT]

The signal (golden_input) goes in as L = R, through juno_cho_st (the line fed the mid, each side its own dry), its
WIDE build (32-bit line, as Optimist builds it), MODE I / II / I+II at MIX 127, and I at MIX 64. Out: int32, 1.0 = 32768.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "test" / "data" / "juno_cho_golden.npz"
N = 32 * 64                                       # 2,048 samples a case
CASES = [(0, 127), (1, 127), (2, 127), (0, 64)]
HOST = r"""
#include <stdio.h>
#include <stdlib.h>
#define JUNO_CHO_WIDE
#include "juno_cho.h"
int main(int argc, char **argv)
{
    static int32_t line[JUNO_CHO_LEN], l[32], r[32], buf[64];
    juno_cho_t c = {line, 0, 0, {{0, 0}, {0, 0}}};
    uint32_t mode = (uint32_t)atoi(argv[1]), mix = (uint32_t)atoi(argv[2]);
    size_t n;
    while ((n = fread(buf, 8, 32, stdin)) > 0) {
        for (size_t i = 0; i < n; i++) l[i] = buf[2 * i], r[i] = buf[2 * i + 1];
        juno_cho_st(&c, mode, mix, l, r, (uint32_t)n, 0);
        for (size_t i = 0; i < n; i++) buf[2 * i] = l[i], buf[2 * i + 1] = r[i];
        fwrite(buf, 8, n, stdout);
    }
    return 0;
}
"""


def golden_input() -> np.ndarray:
    """the int32 test signal (1.0 = 32768): two detuned saws and a sine, about -6 dB"""
    t = np.arange(N, dtype=np.float64) / 44100.0
    saw = lambda f: 2.0 * ((t * f) % 1.0) - 1.0      # noqa: E731
    x = 0.22 * saw(220.0) + 0.18 * saw(331.5) + 0.15 * np.sin(2 * np.pi * 97.0 * t)
    return np.round(x * 32768.0).astype(np.int32)


def main(argv: list[str]) -> int:
    src = pathlib.Path(argv[0] if argv else pathlib.Path.home() / "GitHub" / "optimist") / "firmware/src/fx/junocho"
    h = src / "juno_cho.h"
    sha = hashlib.sha256(h.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        c, exe = pathlib.Path(tmp) / "host.c", pathlib.Path(tmp) / "host"
        c.write_text(HOST)
        subprocess.run(["cc", "-O2", "-I", str(src), "-o", str(exe), str(c)], check=True)
        x = golden_input()
        raw = np.stack([x, x], 1).astype("<i4").tobytes()
        outs = {}
        for mode, mix in CASES:
            got = subprocess.run([str(exe), str(mode), str(mix)], input=raw, capture_output=True, check=True).stdout
            outs[f"m{mode}_x{mix}"] = np.frombuffer(got, "<i4").reshape(-1, 2)
    np.savez_compressed(OUT, juno_cho_sha256=np.array(sha), **outs)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} B) from juno_cho.h {sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
