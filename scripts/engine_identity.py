"""2026-11-21 (eng-simd): an engine re-coded must give the same output words, bit for bit. Each engine named runs in
PERC's harness (dnfw.perc.live, the model the SHARC runner holds the DSP to) as scripts/dsp_cost.py sets it up, at its
default and at settings of its records drawn from a fixed seed (each record at its bottom, top or a random value,
the record that picks the engine kept, as the cost survey's sweep does), 48 blocks with notes and retriggers; each
run's output words are hashed (sha256).

    python scripts/engine_identity.py record OUT.json NAME,NAME..     # before the re-code
    python scripts/engine_identity.py check REF.json NAME,NAME..      # after: every run identical
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import dsp_cost as DC        # noqa: E402

SETTINGS, BLOCKS, NOTES = 8, 48, {1: 60.0, 9: 67.0, 20: 48.0, 33: 72.0}


def _protected(fam: str) -> set[int]:
    """the record that picks the engine (left as the case set it): the cost survey's sweep.protected"""
    from dnfw.perc import machines as PMx
    if fam == "PLAITS":
        from dnfw.engines.plaits import plaits as PLT
        return {PMx.PARAMS[PLT.MODL_K][1]}
    if fam == "SOPHIE":
        from dnfw.engines.sophie import sophie as SO
        return {PMx.PARAMS[SO.MODL_K][1]}
    if fam == "ANALOG2":
        from dnfw.engines.analog2 import analog2 as A2
        return {PMx.FX_PARAMS[A2.PNAMES2.index("FLT2")][1]}
    if fam == "MONOMACHINE":
        return {PMx.PARAMS[7][1]}
    return set()


def _vary(h, fam: str, rnd: random.Random) -> None:
    """every record (pages 1, 2 and page 3's read ones) at its bottom, top or a random value: the sweep's variant"""
    from dnfw.perc import machines as PMx
    prot = _protected(fam)
    for _rid, slot, lo, top in list(PMx.PARAMS) + list(PMx.FX_PARAMS) + list(PMx.P3_RECS[:PMx.P3_READ]):
        if slot in prot:
            continue
        c = rnd.random()
        v = 0 if c < 0.25 else top if c < 0.5 else rnd.randint(0, top)
        h._half(PMx.frame_offset(slot), (v + lo) << 8)


def run(name: str, fam, setup) -> dict:
    from dnfw.md import core as MDK
    from dnfw.mnm import dpro as MNP
    from dnfw.perc import live as PL
    out = {}
    for k in range(SETTINGS):
        rnd = random.Random(f"engine_identity/{name}/{k}")
        h = PL.Harness()
        h.words[h.L.md.C["fill"]] = MDK.Z_N
        h.words.update(MNP.bench_words(h.L.md.mnm))
        setup(h)
        if k:
            _vary(h, fam, rnd)
        dig = hashlib.sha256()
        note = 60.0
        for blk in range(BLOCKS):
            trig = blk in NOTES
            note = NOTES.get(blk, note)
            words = h.block(note=note, trig=trig)
            dig.update(b"".join(struct.pack("<f", x) for x in words))
        out[str(k)] = dig.hexdigest()
    return out


def main() -> int:
    mode, path, names = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3].split(",")
    DC._install()
    cases = {n: (f, s) for n, f, s in DC.cases()}
    res = {n: run(n, *cases[n]) for n in names}
    for n in names:
        print(f"{n}: {len(res[n])} runs", flush=True)
    if mode == "record":
        old = json.loads(path.read_text()) if path.exists() else {}
        old.update(res)
        path.write_text(json.dumps(old, indent=1))
        print(f"recorded {path}")
        return 0
    ref = json.loads(path.read_text())
    bad = [f"{n} {k}" for n in names for k, h in res[n].items() if ref.get(n, {}).get(k) != h]
    print(("PASS" if not bad else "FAIL") + f": {sum(len(v) for v in res.values())} runs, {len(bad)} differ "
          + " ".join(bad[:10]))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
