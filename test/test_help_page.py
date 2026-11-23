"""tools/web/help.html (the hidden functions page) against this tree: every key a card lights is one the
schematic draws, no card is tied to a part (one build, everything in it: the User, 2026-11-19), and the
version shown is the published release's, never a number written into the page."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "tools/web"
PAGE = (WEB / "help.html").read_text(encoding="utf-8")
SCRIPT = PAGE.split("<script>")[1].split("</script>")[0]


def _block(name: str) -> str:
    m = re.search(rf"^const {name} = (.*?)^[\]}}];?\n", SCRIPT, re.S | re.M)
    assert m, name
    return m.group(0)


def _cards() -> list[str]:
    return re.findall(r"^\s*\{ t: .*?\] \},?$", _block("CARDS"), re.S | re.M)


def _site(tmp: pathlib.Path) -> pathlib.Path:
    """The pages as GitHub Pages serves them (scripts/make_site.sh, the workflow's own layout)."""
    out = tmp / "site"
    subprocess.run(["bash", str(ROOT / "scripts/make_site.sh"), str(out), "--preview"], check=True,
                   capture_output=True)
    return out


def test_the_page_uses_its_stylesheet_and_no_page_this_build_lacks(tmp_path: pathlib.Path):
    assert 'href="wishes.css"' in PAGE and (WEB / "wishes.css").is_file()
    site = _site(tmp_path)
    for href in re.findall(r'href="([^"#:]+)"', PAGE):
        assert (site / href).exists(), href


def test_every_page_has_the_tabs_and_they_lead_to_pages(tmp_path: pathlib.Path):
    """About, Builder, Sample import, Presets and Help each carry the same tab bar under the title "w0ts / Wishes"
    (no DN2: the User, 2026-11-23), and each tab opens the right page in the served layout (About is the front page)."""
    site = _site(tmp_path)
    want = {"about.html": "Wishes · About", "builder.html": "Wishes · Builder", "samples.html": "Wishes · Sample import",
            "presets.html": "Wishes · Presets", "help.html": "Wishes · Hidden functions"}
    labels = ["About", "Builder", "Sample import", "Presets", "Help"]
    for page in want:
        html = (site / page).read_text(encoding="utf-8")
        assert '<a href="https://w0ts.github.io/">w0ts</a> / Wishes</h1>' in html, page
        nav = re.search(r'<nav class="site" aria-label="Wishes pages">(.*?)</nav>', html, re.S)
        assert nav, page
        assert re.findall(r'<a href="[a-z]+\.html"(?: aria-current="page")?>([^<]+)</a>', nav.group(1)) == labels, page
        for href, title in want.items():
            assert f'href="{href}"' in nav.group(1), (page, href)
            assert f"<title>w0ts / {title}</title>" in (site / href).read_text(encoding="utf-8"), (page, href)
        assert nav.group(1).count('aria-current="page"') == 1, page


def test_no_card_is_tied_to_a_part():
    cards = _cards()
    assert len(cards) >= 25
    for card in cards:
        assert "part:" not in card, card[:60]
    assert "?off=" not in PAGE and "partOff" not in SCRIPT


def test_the_version_comes_from_the_published_release():
    sub = re.search(r'<p class="sub">(.*?)</p>', PAGE, re.S).group(1)
    assert not re.search(r"v\d+\.\d+", sub), sub                 # no stale number written in
    assert 'DN2wishes<span id="ver"></span>' in sub
    assert 'fetch("wishes/wishes.json"' in SCRIPT


def test_every_lit_key_is_drawn():
    drawn = set(re.findall(r'\["(\w+)", "', _block("KEYS"))) | {"ENC" + e for e in "ABCDEFGH"} | {"TRIG"} \
        | {f"TRIG{i}" for i in range(1, 17)}
    for card in _cards():
        keys = re.search(r"keys: \[([^\]]*)\]", card)
        assert keys, card[:60]
        for key in re.findall(r'"(\w+)"', keys.group(1)):
            assert key in drawn, key
