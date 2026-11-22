"""The builder's "Flash from this page" step (tools/web/wishes-flash.js, wired in tools/web/builder.html).

It sends an OS image to the Digitone II over USB, so it is held to what Elektron Transfer was recorded
sending (2026-11-21): the same OsUpgradeStart, the same OsUpgradeWrite bytes (2,048-byte chunks, Transfer's
CRC variant), one write waiting for its 0xD1 at a time, and no commit message (the DN2 asks UPGRADE OS NOW?
itself). The checks run in node (scripts/web_flash_check.mjs) against fake DN2s; nothing opens a MIDI port.

The replay needs the recording and the .syx it carried. Neither is tracked (firmware never goes on main; the
recording carries the unit's name), so it runs where they are: WEB_FLASH_CAPTURE / WEB_FLASH_SYX, or the main
checkout's scratch/flash-capture and scratch/flash. Without them that test says so and skips.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "tools" / "web"
HARNESS = ROOT / "scripts" / "web_flash_check.mjs"
SYX_SHA8 = "9b89e2b9"          # DN2wishes v0.65.1, the file the recording carried


def _node(*args: str, timeout: int = 120) -> dict:
    if not shutil.which("node"):
        pytest.skip("no node")
    r = subprocess.run(["node", str(HARNESS), *args], capture_output=True, text=True, timeout=timeout)
    assert r.stdout, r.stderr
    rep = json.loads(r.stdout)
    bad = [f"{c['name']}: {c['detail']}" for c in rep["checks"] if not c["ok"]]
    assert r.returncode == 0 and not bad, "\n".join(bad) or r.stderr
    return rep


def _main_checkout() -> pathlib.Path:
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    return (ROOT / common.stdout.strip()).resolve().parent if common.returncode == 0 else ROOT


def _recording() -> tuple[pathlib.Path, pathlib.Path] | None:
    cap, syx = os.environ.get("WEB_FLASH_CAPTURE"), os.environ.get("WEB_FLASH_SYX")
    if not (cap and syx):
        scratch = _main_checkout() / "scratch"
        caps = sorted((scratch / "flash-capture").glob("capture-*.log"), key=lambda p: p.stat().st_size)
        syxs = sorted((scratch / "flash").glob(f"*_{SYX_SHA8}_*.syx"))
        cap = cap or (str(caps[-1]) if caps else None)          # the full update, not the 3 s probe
        syx = syx or (str(syxs[0]) if syxs else None)
    if cap and syx and pathlib.Path(cap).is_file() and pathlib.Path(syx).is_file():
        return pathlib.Path(cap), pathlib.Path(syx)
    return None


def test_the_protocol_against_a_fake_dn2():
    """CRC variant, framing against recorded bytes, image checks, and every path of a session: clean,
    bad CRC (resend; too many: cancel), device error, timeout, start refused, Abort before and after the
    last chunk, a lost port, the wrong device or OS, an image over 2 MiB, a broken file."""
    rep = _node("synthetic")
    assert len(rep["checks"]) >= 30


def test_the_page_replays_transfers_recorded_update_byte_for_byte():
    rec = _recording()
    if rec is None:
        pytest.skip("the recording or its .syx is not here (set WEB_FLASH_CAPTURE and WEB_FLASH_SYX)")
    rep = _node("replay", str(rec[0]), str(rec[1]), timeout=300)
    assert rep["writes"] == 1245


def test_the_page_offers_the_flash_only_beside_the_cleared_build():
    page = (WEB / "builder.html").read_text(encoding="utf-8")
    assert '<script src="wishes-flash.js"></script>' in page
    # (2026-11-21, the User: connect without waiting for the build) the section shows at load and Connect works;
    # with no build there are no bytes, the image check fails, and Flash stays disabled
    assert '<section id="flashSec" hidden>' in page and '$("#flashSec").hidden = false;' in page
    assert "function flashBytes() { return built ? built.syx : null; }" in page
    assert "fl.img = b ? WishesFlash.checkImage(b) : { ok: false, errors: [] };" in page
    assert '$("#fGo").disabled = !midi || fl.busy || !fl.img.ok' in page
    assert "if (fl.busy || !built || !fl.flasher" in page
    # built is set only by the verdict; the bytes are re-checked right before they are sent
    assert "built = v.save ? { syx, got, r, rec, stock: stockOk ? stock : null } : null;" in page
    assert "if (!(await flashVerified()))" in page
    assert "verdictOf(built.r, built.rec, await hex(built.syx)).save" in page    # no stock flash (the User, 2026-11-22)
    # never a file picked for the flash: the only file inputs are step 1's
    assert page.count('<input type="file"') == 4                       # the four of step 1
    assert "<input type=\"file\"" not in page.split('id="flashSec"', 1)[1].split("</section>", 1)[0]


def test_the_page_never_starts_by_itself():
    page = (WEB / "builder.html").read_text(encoding="utf-8")
    script = page.split("<script>")[1]
    assert script.count("requestMIDIAccess({ sysex: true })") == 1
    assert re.search(r'\$\("#fConnect"\)\.onclick = async \(\) => \{.*?requestMIDIAccess\(\{ sysex: true \}\)', script, re.S)
    assert script.count(".flash(") == 1
    go = script.split('$("#fGo").onclick = async () => {', 1)[1]
    assert go.index("confirm(") < go.index(".flash(")                  # clicked, then confirmed once more
    assert go.index("flashVerified()") < go.index(".flash(")
    for tick in ("+Drive", "Stable power", "Transfer, Overbridge", "DIN MIDI cable", "UPGRADE OS NOW?"):
        assert tick in page.split('id="fChecks"', 1)[1].split("</div>", 1)[0], tick
    assert "every(i => i.checked)" in script and "!(fl.dev && fl.dev.ok)" in script


def test_the_site_carries_the_module(tmp_path):
    out = tmp_path / "site"
    subprocess.run(["bash", str(ROOT / "scripts" / "make_site.sh"), str(out), "--preview"], check=True, capture_output=True)
    assert (out / "wishes-flash.js").read_bytes() == (WEB / "wishes-flash.js").read_bytes()
    assert '<script src="wishes-flash.js"></script>' in (out / "builder.html").read_text(encoding="utf-8")


# -- the local test switch (2026-11-21): a brick-risk-only TEST build, localhost + --preview + ?localtest=1 only --
SHA = "9" * 64
ROW = {"sha256": SHA, "gate": None, "local_test": {"brick_risk_sha256": SHA}}
GOOD = {"hostname": "localhost", "preview": True, "query": "?localtest=1"}


def _switch(release, got, env):
    if not shutil.which("node"):
        pytest.skip("no node")
    js = ("const V=require(%r);const a=JSON.parse(process.argv[1]);"
          "console.log(JSON.stringify(V.verdictLocal(a.r,null,a.got,a.env)))" % str(WEB / "wishes-verdict.js"))
    r = subprocess.run(["node", "-e", js, json.dumps({"r": release, "got": got, "env": env})],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_the_local_test_switch_opens_only_in_a_local_preview():
    assert _switch(ROW, SHA, GOOD)["save"] is True
    for bad in ({**GOOD, "hostname": "w0ts.github.io"}, {**GOOD, "hostname": "localhost.evil.com"},
                {**GOOD, "preview": False}, {**GOOD, "query": ""}, {**GOOD, "query": "?localtest=0"}, None):
        assert _switch(ROW, SHA, bad)["save"] is False, bad
    assert _switch(ROW, "8" * 64, GOOD)["save"] is False                       # not that sha256
    other = {**ROW, "local_test": {"brick_risk_sha256": "8" * 64}}
    assert _switch(other, SHA, GOOD)["save"] is False                          # the row names another file
    assert _switch({"sha256": SHA, "gate": None}, SHA, GOOD)["save"] is False  # a row without local_test


def test_the_public_bundle_refuses_the_switch(tmp_path):
    """a --local-test row never passes the Pages check, and make_site.sh without --preview refuses it"""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import wishes_bundle
    wish = tmp_path / "wishes"
    (wish / "v1").mkdir(parents=True)
    zb = b"zip"
    (wish / "v1" / "code.zip").write_bytes(zb)
    import hashlib
    row = {k: "x" for k in wishes_bundle.ROW_KEYS}
    row.update(release="1", sha256=SHA, gate=None, zip="v1/code.zip", zip_sha256=hashlib.sha256(zb).hexdigest(),
               local_test={"brick_risk_sha256": SHA})
    (wish / "wishes.json").write_text(json.dumps([row]))
    assert wishes_bundle.check_site(wish) == 1
    # make_site.sh in a layout whose wishes/ holds that row: refused without --preview, marker with it
    repo = tmp_path / "repo"
    repo.mkdir()
    for n in ("scripts", "tools", "presets", "docs", "LICENSE", "THIRD-PARTY.md"):
        (repo / n).symlink_to(ROOT / n)
    shutil.copytree(wish, repo / "wishes")
    site = tmp_path / "public"
    r = subprocess.run(["bash", str(repo / "scripts" / "make_site.sh"), str(site)], capture_output=True, text=True)
    assert r.returncode != 0 and "--preview" in r.stderr and not site.exists()
    prev = tmp_path / "preview"
    subprocess.run(["bash", str(repo / "scripts" / "make_site.sh"), str(prev), "--preview"], check=True, capture_output=True)
    assert json.loads((prev / "localtest-preview.json").read_text()) == {"preview": True}
    # a site with an ordinary row never gets the marker
    (repo / "wishes" / "wishes.json").write_text("[]")
    plain = tmp_path / "plain"
    subprocess.run(["bash", str(repo / "scripts" / "make_site.sh"), str(plain), "--preview"], check=True, capture_output=True)
    assert not (plain / "localtest-preview.json").exists()


def test_the_page_shows_the_banner_and_asks_the_marker_only_for_the_switch():
    page = (WEB / "builder.html").read_text(encoding="utf-8")
    assert 'id="testBanner" class="banner err" hidden' in page and "TEST BUILD" in page.split('id="testBanner"')[1][:200]
    assert 'getJson("localtest-preview.json")' in page and "localtest=1" in page
    assert page.count("verdictOf(") >= 3 and "WishesVerdict.verdict(" not in page
