"""tools/web/help.html (the hidden functions page) against this tree: its parts are the builder's parts
(src/dnfw/builder/parts.py), its groups hold every part of their kind, and every key a card lights is one the
schematic draws."""
from __future__ import annotations

import json
import pathlib
import re

from dnfw.builder import parts as P

WEB = pathlib.Path(__file__).resolve().parents[1] / "tools/web"
PAGE = (WEB / "help.html").read_text(encoding="utf-8")
SCRIPT = PAGE.split("<script>")[1].split("</script>")[0]


def _block(name: str) -> str:
    m = re.search(rf"^const {name} = (.*?)^[\]}}];?\n", SCRIPT, re.S | re.M)
    assert m, name
    return m.group(0)


def _groups() -> dict[str, list[str]]:
    m = re.search(r"^const GROUP = (\{.*?\});$", SCRIPT, re.M)
    assert m
    return json.loads(m.group(1))


def _cards() -> list[str]:
    return re.findall(r"^\s*\{ t: .*?\] \},?$", _block("CARDS"), re.S | re.M)


def test_the_page_uses_its_stylesheet_and_no_page_this_build_lacks():
    assert 'href="wishes.css"' in PAGE and (WEB / "wishes.css").is_file()
    for href in re.findall(r'href="([^"#:]+)"', PAGE):
        assert (WEB / href).is_file(), href


def test_groups_hold_every_part_of_their_kind():
    groups = _groups()
    assert groups["INS_*"] == [p.key for p in P.PARTS if p.group == "inserts"]
    assert groups["FX_*"] == [p.key for p in P.PARTS if p.group == "fx"]


def test_every_card_part_is_a_part_or_a_group():
    groups = _groups()
    cards = _cards()
    assert len(cards) >= 25
    for card in cards:
        part = re.search(r'part: "([^"]+)"', card)
        if part:
            assert part.group(1) in P.BY_KEY or part.group(1) in groups, part.group(1)


def test_every_lit_key_is_drawn():
    drawn = set(re.findall(r'\["(\w+)", "', _block("KEYS"))) | {"ENC" + e for e in "ABCDEFGH"} | {"TRIG"} \
        | {f"TRIG{i}" for i in range(1, 17)}
    for card in _cards():
        keys = re.search(r"keys: \[([^\]]*)\]", card)
        assert keys, card[:60]
        for key in re.findall(r'"(\w+)"', keys.group(1)):
            assert key in drawn, key
