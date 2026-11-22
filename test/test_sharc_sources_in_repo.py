"""Every SHARC program the build places has its source in the repository, byte for byte (2026-11-17).

src/dnfw/waverider/sharc_code.json names each placed program's source (`source`) and the sha256 that source had
when it was assembled (`source_sha256`). Nineteen of them (a2f, fdn8, insbus, inserts, inspost, jsend, perc2a,
perc2b, xdly, trackbuf.json) were written only by a regen run and never committed: a fresh checkout failed four
tests with FileNotFoundError while every regenerated tree passed. Generated sources are committed like the rest;
this fails, with the file's name, whenever one is missing or differs from what was assembled.
"""

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "src/dnfw/waverider/sharc_code.json").read_text())
PLACED = {k: v for k, v in SPEC.items() if isinstance(v, dict) and "source_sha256" in v}


def test_every_placed_program_has_its_source_in_the_repository():
    missing = [v["source"] for v in PLACED.values() if not (ROOT / v["source"]).is_file()]
    assert not missing, f"generated SHARC sources not in the repository (commit them): {missing}"


def test_every_source_is_the_one_that_was_assembled():
    stale = [v["source"] for v in PLACED.values() if (ROOT / v["source"]).is_file()
             and hashlib.sha256((ROOT / v["source"]).read_bytes()).hexdigest() != v["source_sha256"]]
    assert not stale, f"SHARC sources differ from what sharc_code.json assembled (regenerate): {stale}"


def test_every_source_has_its_assembled_object_beside_it():
    missing = [v["source"] for v in PLACED.values()
               if not (ROOT / v["source"]).with_suffix(".json").is_file()]
    assert not missing, f"assembled objects (.json) not in the repository beside: {missing}"
