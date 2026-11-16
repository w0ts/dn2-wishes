"""Every Machinedrum machine renders word for word as upstream's v0.52 source does (scripts/md_source_identity.py; the
reference test/data/md_source_v052.json was recorded in a git archive of v0.52). 2026-11-13: a half-merge (v0.52's
float TRX filters with the perf pass's integer coefficients) left TRX-CY and TRX-CH/OH silent and S2, MA, CB wrong,
and no other step saw it. A change that is meant to change a machine's sound records a new reference with it."""

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import md_source_identity as MI  # noqa: E402

REF = json.loads((ROOT / "test" / "data" / "md_source_v052.json").read_text())["machines"]


@pytest.mark.parametrize("name", sorted(REF))
def test_machine_renders_as_v052(name):
    if not os.environ.get("MD_OS_BIN") and not (ROOT.parent / "md163" / "md_uw_os1.63.bin").exists():
        pytest.fail("the Machinedrum's OS is needed (MD_OS_BIN, docs/md.md): unchecked is not passing")
    bad = MI.check(REF, [name])
    assert not bad, bad


def test_every_machine_has_a_reference():
    assert sorted(REF) == sorted(MI.machines())
