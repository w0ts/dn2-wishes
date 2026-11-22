"""The modulation frame on a build with DN2_ROUTE8 off (A) and on (B), byte for byte (2026-11-21, claude/route-meas:
the route tables in 8 bytes a route, csrc/matrix/matrix.c).

    emu_route8_ab.py --a A.syx --syma A_code.json --b B.syx --snapshot S [--frames N] [--seeds 1,2,3]

Run from build B's tree (DN2_ROUTE8=1 when its code was generated). The set-up and each frame are
scripts/emu_insframe_ab.py's (every voice's three LFOs moving, every track 23 routes into voice cells, ENV2 and the
inserts' knobs, all 32 insert records on, ENV2 locks, trigs, last-played voices moved). After each frame these must be
the same on A and B: the mirror OUT (16 rows), MOD_RAM, the LFO states, OWNER, the inserts' state, and struct mx_state
less its layout: the header (all but the magic, which holds the state's size), every table as values (each route's
cell (one outside the voice row as its place in the scratch row or the ENV2 knob rows), d1 and source as an offset in
the voice's env_out row; ENV2's knobs, the first-route marks, the knob cells and
the first routes' words as bytes), then env_out, the scratch row, the ENV2 knob rows and iroute byte for byte (the insert
cells of voices mx_ins_group does not read this frame left out, as emu_insframe_ab.py leaves them). Prints the
instructions a frame of mod_eval (which holds mx_eval: the one part that differs) on each build."""
from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

TREE = pathlib.Path.cwd()
sys.path.insert(0, str(TREE / "scripts"))
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emu_insframe_ab as IA            # noqa: E402
from emulib import mxlayout             # noqa: E402

SLOTS = 23
ROW0 = 0x800068E4 + 34                  # matrix.c OUT_B + 34: a route's cell is an offset from the voice row's slot 0


class Run(IA.Run):
    def __init__(self, build, snap, sym, seed):
        super().__init__(build, snap, sym, seed)
        from dnfw.waverider import pages
        self.L = mxlayout.of_size(self.size)
        lfo0 = pages.lfo4_moved()["LFO_LIVE"] + 4                       # matrix.c LFO_OUT(0)
        self.eoff = (self.mx + self.L.env_out - lfo0) & 0xFFFFFFFF      # the 12-byte table's source base

    def where(self, cell: int) -> int:
        """a cell outside the voice row (the scratch row, the ENV2 knob rows: in MX_RAM, whose layout moves them) as
        its area and its offset in it; a row cell 0"""
        if 0 <= cell < 202:
            return 0
        a = (cell + ROW0) & 0xFFFFFFFF
        rel = a - self.mx
        if self.L.e2row <= rel < self.L.iroute:
            return 0xE0000000 | (rel - self.L.e2row)
        if self.L.scratch <= rel < self.L.e2row:
            return 0x50000000 | (rel - self.L.scratch)
        return 0xBAD00000 | (cell & 0xFFFFF)

    def tables(self, mx: bytes) -> bytes:
        L, out = self.L, []
        for i in range(33):                                             # tab[16][2], then none
            base = L.tab + i * L.tab_b
            for k in range(SLOTS):
                at = base + L.entry * k
                if L.entry == 12:
                    cell, d1, src = struct.unpack_from(">iii", mx, at)
                    if src:                                             # a used route's: from env_out's row
                        src = (src - self.eoff) & 0xFFFFFFFF
                        src = src - (1 << 32) if src >= 1 << 31 else src
                else:
                    cell, h, src = struct.unpack_from(">ihh", mx, at)
                    d1 = 2 * h
                out.append(struct.pack(">iIi", cell if 0 <= cell < 202 else 0, self.where(cell), d1) + struct.pack(">i", src))
            out.append(mx[base + SLOTS * L.entry:base + L.tab_b])       # env2, mute1, e2w, nx1
        return b"".join(out)

    def state(self, vs):
        parts = super().state(vs)
        k = len(IA.AREAS)
        mx, L = parts[k], self.L
        parts[k] = mx[4:L.tab]                                          # the header, not the magic
        parts.insert(k + 1, self.tables(mx))
        parts.insert(k + 2, mx[L.env_out:])
        return parts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--syma", required=True, help="build A's waverider_code.json")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--frames", type=int, default=200)
    p.add_argument("--seeds", default="1,2,3")
    a = p.parse_args()
    sym = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    syma = json.loads(pathlib.Path(a.syma).read_text())["layout"]
    bad = 0
    names = ([f"area {at:#x}" for at, _ in IA.AREAS] + ["mx_state header", "mx_state tables (values)",
             "mx_state env_out .. iroute", "insert cells read"] + [s for s, _ in IA.INS_SYMS])
    for seed in [int(x) for x in a.seeds.split(",")]:
        ra, rb = Run(a.a, a.snapshot, syma, seed), Run(a.b, a.snapshot, sym, seed)
        print(f"seed {seed}: A entry {ra.L.entry} B, table {ra.L.tab_b} B; B entry {rb.L.entry} B, table {rb.L.tab_b} B",
              flush=True)
        if ra.L.lfo_w != rb.L.lfo_w:
            raise SystemExit("A and B differ in DN2_LFO4: not an A/B of DN2_ROUTE8")
        first = None
        for f in range(a.frames):
            x, y = ra.frame(f), rb.frame(f)
            if x != y and first is None:
                k = next(i for i in range(min(len(x), len(y))) if x[i] != y[i]) if len(x) == len(y) else -1
                first = (f, names[k] if 0 <= k < len(names) else f"part {k} (lengths {len(x)}/{len(y)})")
                if names[k:k + 1] == ["mx_state tables (values)"]:
                    rec = 16 * SLOTS + ra.L.tab_b - SLOTS * ra.L.entry      # one table's values
                    i = next(j for j in range(len(x[k])) if x[k][j] != y[k][j])
                    tb, at = divmod(i, rec)
                    print(f"  table {tb} byte {at}: A {x[k][tb * rec:(tb + 1) * rec].hex()}\n"
                          f"  {'':{len(str(tb)) + 7}}B {y[k][tb * rec:(tb + 1) * rec].hex()}", flush=True)
        for lab, r in (("A", ra), ("B", rb)):
            print(f"seed {seed} {lab}: mod_eval worst {max(r.cost_mx)} mean {sum(r.cost_mx) / len(r.cost_mx):.0f}",
                  flush=True)
        print(f"seed {seed}: {a.frames} frames, " + ("the same" if first is None else f"DIFFER first at frame {first}"),
              flush=True)
        bad += first is not None
        del ra, rb
    print("PASS: the same bytes every frame" if not bad else f"FAIL: {bad} seeds differ")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
