"""ship_gate's own process writes its byte-code into out/ship_gate_pycache, never into the tree (2026-11-17).

v0.56.3's full run: the gate's untraced first steps imported dnfw and made src/dnfw/params/__pycache__. The
traced steps' records hold that folder's listing (made in the phase-1 copies, which never ran those steps),
so every SHARC part, the coupled steps and the unit tests ran again although nothing they read had changed.
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHIP_GATE = ROOT / "scripts" / "ship_gate.py"


def _run(code: str, tmp_path: pathlib.Path) -> str:
    """CODE in a fresh interpreter whose __main__ is ship_gate's top (up to its first dnfw import)"""
    src = SHIP_GATE.read_text()
    top = src[:src.index("from dnfw import safety")]
    script = tmp_path / "top.py"
    script.write_text(top.replace("pathlib.Path(__file__)", f"pathlib.Path({str(SHIP_GATE)!r})") + code)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")}
    out = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, check=True)
    return out.stdout


def test_gate_byte_code_goes_to_out(tmp_path):
    out = _run("import os, sys\nprint(sys.pycache_prefix)\nprint(os.environ['PYTHONPYCACHEPREFIX'])\n", tmp_path)
    want = str(ROOT / "out" / "ship_gate_pycache")
    assert out.split() == [want, want]


def test_set_before_the_first_import_from_the_tree():
    """the prefix is set before ship_gate imports dnfw or gate_cache (else their .pyc land in src/, scripts/)"""
    src = SHIP_GATE.read_text()
    at = src.index("sys.pycache_prefix = str(PYCACHE)")
    assert at < src.index("from dnfw import safety")
    assert at < src.index("import gate_cache")


def test_control_without_the_prefix(tmp_path):
    """control: a plain interpreter (no prefix) writes beside the source, the case the gate now avoids"""
    out = _run("", tmp_path)
    assert out == ""
    plain = subprocess.run([sys.executable, "-c", "import sys; print(sys.pycache_prefix)"],
                           env={k: v for k, v in os.environ.items() if k != "PYTHONPYCACHEPREFIX"},
                           capture_output=True, text=True, check=True)
    assert plain.stdout.strip() == "None"
