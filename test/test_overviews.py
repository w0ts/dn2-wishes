"""The page keys' overviews (csrc/inserts/ovw_draw.c): the C's tables and text rule are the model's
(dnfw.overviews), and the model's pictures keep to the layout."""

import pathlib
import re

from dnfw import overviews as O

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRAW = (ROOT / "csrc/inserts/ovw_draw.c").read_text()
PAGE = (ROOT / "csrc/waverider/page.c").read_text()
OVW = (ROOT / "csrc/inserts/ovw.c").read_text()


def _strings(src: str, name: str) -> list[str]:
    return re.findall(r'"([^"]*)"', re.search(name + r"\[\] = \{(.*?)\};", src, re.S).group(1))


def test_filter_names_are_the_models():
    c = _strings(DRAW, "FILTER3")
    assert {i: n for i, n in enumerate(c) if n} == O.FILTER3
    assert all(len(n) <= 3 and all(ch in O.CHARS for ch in n) for n in c)


def test_machine_names_are_the_models():
    c = _strings(PAGE, "ovw_mach4")
    assert {i: n for i, n in enumerate(c) if n} == O.MACHINE4
    assert all(len(n) <= 3 for n in c)


def test_short3():
    assert [O.short3(s) for s in ("STRG", "SL12", "FUSE", "SWRM", "VO-6", "MDAL", "DDRW", "EQ", "SID")] == \
        ["STR", "S12", "FSE", "SWR", "V-6", "MDL", "DDR", "EQ", "SID"]


def _cells(kind, val):
    return [[(kind, val), (kind, val)] for _ in range(16)]


def test_every_kind_keeps_to_its_cell():
    for kind, val in ((O.DOT, ""), (O.PLAIN, "ABCD"), (O.LIT, "WAV"), (O.FRAME, "PLT"), (O.BLINK, "FUL"),
                      (O.MARKS, 15), (O.COUNT, (23, 4))):
        pic = O.render("L", "R", _cells(kind, val), 3)
        assert len(pic) == 64 and all(len(r) == 128 for r in pic)
        for t in range(16):
            x, rb = 16 * (t % 8), 10 + 27 * (t // 8)
            assert not any(pic[r][x + 15] for r in range(rb + 7, rb + 26)), (kind, t)   # a dark column between cells


def test_amp_marks_the_busiest_and_rounds_up_small_shares():
    left, right, cells = O.amp_cells([0, 2] + [0] * 14, [0, 20_000] + [0] * 13 + [70_000], 40, -1)
    assert cells[15][1] == (O.LIT, "10%") and cells[1][1] == (O.PLAIN, "3%") and cells[0][1][0] == O.DOT
    assert left == "VOICES 2/16" and right == "C 40% D --"
    assert O.pct(1) == 1 and O.pct(0) == 0


def test_every_page_key_has_its_overview_and_taps_stay_stocks():
    for k in ("K_SYN", "K_FLTR", "K_AMP", "K_FX", "K_MOD"):
        assert re.search(rf"#define {k} +\du", OVW)
    body = re.search(r"static int watch_item\(.*?\n\}", OVW, re.S).group(0)
    assert "return 1" not in body                 # SYN, FLTR, MOD: every item goes on to stock


# -- the VOICE key's overview (2026-11-19) ----------------------------------------------------------------------------

def test_voice_modes():
    assert O.voice_mode(51, True, True, 0) == "PAR"         # PARA wins: UNISON is ignored on a PARA track
    assert O.voice_mode(50, False, True, 3) == "UNI"
    assert O.voice_mode(1, False, False, 1) == "MON"
    assert O.voice_mode(1, False, False, 0) == "PLY" and O.voice_mode(0, False, False, 4) == "PLY"
    assert O.voice_mode(4, False, True, 0) == "" and O.voice_mode(-1, False, False, 0) == ""


def test_voice_cells():
    names = ["WAV", "A2", "JUN", "MID"] + [""] * 12
    types = [1, 51, 50, 4] + [-1] * 12
    left, right, cells = O.voice_cells(names, types, [False, True, False, False] + [False] * 12,
                                       [False, False, True, True] + [False] * 12, [0, 2, 0, 5] + [0] * 12, 14)
    assert (left, right) == ("VOICE SETUP", "DYN 14")
    assert cells[0] == [(O.PLAIN, "WAV"), (O.PLAIN, "PLY"), (O.PLAIN, "DYN")]
    assert cells[1] == [(O.PLAIN, "A2"), (O.LIT, "PAR"), (O.PLAIN, "2")]
    assert cells[2] == [(O.PLAIN, "JUN"), (O.FRAME, "UNI"), (O.PLAIN, "DYN")]
    assert cells[3] == [(O.PLAIN, "MID"), (O.DOT, ""), (O.DOT, "")]
    assert cells[4] == [(O.DOT, ""), (O.DOT, ""), (O.DOT, "")]


def test_voice_rows_keep_to_their_cells():
    for kind, val in ((O.DOT, ""), (O.PLAIN, "DYN"), (O.LIT, "PAR"), (O.FRAME, "UNI")):   # (boxes: the mode's row)
        for track in (3, 11):
            low = (O.PLAIN, "16") if kind in (O.LIT, O.FRAME) else (kind, val)
            pic = O.voice_render("VOICE SETUP", "DYN 16", [[(O.PLAIN, "WAV"), (kind, val), low]] * 16, track)
            assert len(pic) == 64 and all(len(r) == 128 for r in pic)
            for t in range(16):
                x, rb = 16 * (t % 8), 10 + 27 * (t // 8)
                assert not any(pic[r][x + 15] for r in range(rb + 6, rb + 27)), (kind, t)   # a dark column
                if t < 8:                                            # clear of the second half's lit number
                    assert not any(pic[36][x:x + 15]) or t + 8 == track, (kind, t)


def test_voice_key_and_labels_are_the_models():
    assert re.search(r"#define K_VOICE +50u", OVW)                 # docs/ui-map.md: VOICE is code 50
    for label in ("PAR", "UNI", "MON", "PLY", "DYN", "VOICE SETUP"):
        assert f'"{label}' in DRAW, label
    body = re.search(r"static int voice_item\(.*?\n\}", OVW, re.S).group(0)
    assert "return 1" not in body and "return drop" in body    # only a hold that showed the overview drops its release
