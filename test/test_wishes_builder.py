"""The Wishes builder page (tools/web/builder.html, builder-worker.js, wishes-verdict.js) and its bundle
(scripts/web_bundle.py --wishes, scripts/wishes_bundle.py).

The rule under test: only a file that a gate record CLEARS can leave the page or the bundler. The
bundler refuses a build without such a record, the site check refuses a folder with any uncleared
file, and the page offers Save only when its build's sha256 is the cleared one."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "tools" / "web"
SHA = "bc9018e3280e263140246a4f372f8ca116cc7f865432ba5e77801645fa9aaece"     # DN2wishes_v0.56.1.syx
OTHER = "b6641ca4" + "0" * 56


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def WB():
    return _load("wishes_bundle", ROOT / "scripts" / "wishes_bundle.py")


def _record(sha: str, **gates: str) -> dict:
    return {"build": "x.syx", "sha256": sha, "date": "2026-11-16T00:00:00",
            "gates": gates or {"preflight": "PASS: ok", "unit": "PASS: 1 passed", "boot": "n/a: NOBOOT"},
            "logs": "/home/someone/logs", "interpreters": {"ColdFire steps": "/home/someone/.venv"}}


# -- the rule, in Python (the bundler, the site check) --

def test_cleared_needs_the_same_sha_and_every_gate_passed(WB):
    assert WB.cleared(_record(SHA), SHA)
    assert not WB.cleared(_record(SHA), OTHER)                       # another file
    assert not WB.cleared(_record(SHA, unit="PASS", emu="FAIL: 3 failed"), SHA)
    assert not WB.cleared({**_record(SHA), "gates": {}}, SHA)        # no gate ran
    assert not WB.cleared(None, SHA)
    assert not WB.cleared(_record(""), "")


def test_the_published_record_carries_no_local_paths(WB):
    pub = WB.public_record(_record(SHA))
    assert set(pub) == {"build", "sha256", "stock", "date", "gates"}
    assert "/home/" not in json.dumps(pub)
    assert WB.cleared(pub, SHA) and pub["gates"]["boot"] == "n/a"


@pytest.mark.parametrize("record", [None, _record(OTHER), _record(SHA, unit="FAIL")])
def test_the_bundler_refuses_a_build_no_record_clears(WB, tmp_path, record, capsys):
    build = tmp_path / "DN2wishes_v0.56.1.syx"
    build.write_bytes(b"\xf0 not cleared \xf7")
    sha = hashlib.sha256(build.read_bytes()).hexdigest()
    if record is not None:
        rec = {**record, "sha256": sha} if record["sha256"] == SHA else record
        pathlib.Path(str(build) + ".gate.json").write_text(json.dumps(rec))
    out = tmp_path / "site"
    assert WB.main([str(build), "0.56.1", "Full", str(out)]) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert not out.exists()                                          # nothing written


def _site(tmp_path: pathlib.Path, gate: bool, tamper: bool = False) -> pathlib.Path:
    out = tmp_path / "wishes"
    (out / "v0.56.1").mkdir(parents=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dn2patch.py", "x = 1\n")
    zb = buf.getvalue()
    (out / "v0.56.1" / "full.zip").write_bytes(zb + (b"!" if tamper else b""))
    entry = {"name": "Full", "file": "DN2wishes_v0.56.1.syx", "sha256": SHA, "zip": "v0.56.1/full.zip",
             "zip_sha256": hashlib.sha256(zb).hexdigest(), "inputs": ["dn2", "dt2", "md"], "gate": None}
    if gate:
        entry["gate"] = "v0.56.1/DN2wishes_v0.56.1.syx.gate.json"
        (out / entry["gate"]).write_text(json.dumps(_record(SHA)))
    (out / "wishes.json").write_text(json.dumps([{"release": "0.56.1", "mod_version": "0.56", "os": "1.12",
                                                  "presets": [entry]}]))
    return out


def test_the_site_check_publishes_only_cleared_files(WB, tmp_path):
    assert WB.check_site(_site(tmp_path / "a", gate=True)) == 0
    assert WB.check_site(_site(tmp_path / "b", gate=False)) == 1     # an --uncleared-test bundle
    assert WB.check_site(_site(tmp_path / "c", gate=True, tamper=True)) == 1
    assert WB.check_site(tmp_path / "none") == 1


def test_web_bundle_dispatches_the_check(tmp_path):
    site = _site(tmp_path, gate=False)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "web_bundle.py"), "--check-site", str(site)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "REFUSED" in r.stdout


# -- the rule, in the page (node) --

def _verdict(js: str):
    if not shutil.which("node"):
        pytest.skip("no node")
    prog = f"const V = require({json.dumps(str(WEB / 'wishes-verdict.js'))});\nconsole.log(JSON.stringify({js}));"
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_page_saves_only_the_cleared_file():
    rec = json.dumps(_record(SHA))
    pre = json.dumps({"sha256": SHA, "gate": "v0.56.1/x.gate.json"})
    ok = _verdict(f"V.verdict({pre}, {rec}, {json.dumps(SHA)})")
    assert ok["save"] is True
    differs = _verdict(f"V.verdict({pre}, {rec}, {json.dumps(OTHER)})")
    assert differs["save"] is False and differs["got"] == OTHER and differs["want"] == SHA
    assert differs["text"].startswith("Not the cleared file; do not flash")
    # no record (v0.56.1 today: "gate": null), or one that does not clear: no Save, whatever the build gives
    for preset, record in ((json.dumps({"sha256": SHA, "gate": None}), "null"),
                           (pre, json.dumps(_record(OTHER))),
                           (pre, json.dumps(_record(SHA, unit="FAIL: 1 failed"))),
                           (pre, json.dumps({**_record(SHA), "gates": {}}))):
        v = _verdict(f"V.verdict({preset}, {record}, {json.dumps(SHA)})")
        assert v["save"] is False and "do not flash" in v["text"], (preset, record)


def test_the_page_wires_save_to_the_verdict_only():
    page = (WEB / "builder.html").read_text()
    assert '<script src="wishes-verdict.js"></script>' in page
    assert page.count("$(\"#save\").disabled = false") == 0           # never enabled outside the verdict
    assert "$(\"#save\").disabled = !v.save;" in page
    assert "if (!v.save) { $(\"#save\").disabled = true; return; }" in page   # checked again at Save
    assert '<link rel="stylesheet" href="wishes.css">' in page and (WEB / "wishes.css").is_file()
    worker = (WEB / "builder-worker.js").read_text()
    assert "pyodide/v0.27.7" in worker and 'loadPackage(["numpy", "lzma"])' in worker
    assert "fetchChecked(d.zip, d.zipSha" in worker and "noboot=True" in worker and "DN2SHA" in worker
    assert "selas" not in worker


def test_the_workflow_is_manual_only_and_checks_the_site():
    wf = (ROOT / ".github" / "workflows" / "wishes-pages.yml").read_text()
    on = wf.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in on and "push" not in on and "schedule" not in on
    assert "web_bundle.py --check-site wishes" in wf
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text()
    assert "push" not in pages.split("\non:", 1)[1].split("\npermissions:", 1)[0]


# -- the 1.12 route: the DN2's own section 7 --

def _dn2_112() -> pathlib.Path | None:
    for p in (os.environ.get("DN2_OS112"), ROOT / "00_Resources" / "00_Firmware" / "Digitone_II_OS1.12_dist.zip",
              ROOT.parent / "Digitone_II_OS1.12.syx"):
        if p and pathlib.Path(p).is_file():
            return pathlib.Path(p)
    return None


def test_dn2patch_takes_section_7_from_the_dn2_file(tmp_path):
    dn2 = _dn2_112()
    if dn2 is None:
        pytest.skip("no Digitone II OS 1.12 file beside the repository (DN2_OS112)")
    P = _load("dn2patch", ROOT / "tools" / "patcher" / "dn2patch.py")
    data = P.unzip(dn2.read_bytes(), (".syx",))
    d = P.dn2_sections(data, tmp_path / "sec")
    body = (d / "section_7_BLOB.bin").read_bytes()
    # scratch/sec112/section_7_BLOB.bin, the folder the gate passes as DT2_SECTIONS
    assert hashlib.sha256(body).hexdigest() == "336e340aa0cdcd34e314cfa44849f709a3134f6bd4cd57dfc7e15702c83115e2"
    with pytest.raises(P.PatchError):
        P.dn2_sections(b"\xf0 not an OS \xf7", tmp_path / "bad")
