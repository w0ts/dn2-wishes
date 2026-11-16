"""VOICE BUDGET (csrc/load, docs/load-budget.md): the note-on hook, the generated cost table, the setting.

The behaviour is held by the emulator check (scripts/emu_load_budget.py, stock's own allocator); these hold the
pieces it relies on."""

from __future__ import annotations

import json
import pathlib
import re

from dnfw import load as LD
from dnfw.waverider import coldfire as CF

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
HOOKS = (ROOT / "csrc/load/hooks.S").read_text()
LOAD_C = (ROOT / "csrc/load/load.c").read_text()
LIVE_C = (ROOT / "csrc/msel/live.c").read_text()


def _body(label: str) -> list[str]:
    m = re.search(rf"^{label}:\n(.*?)(?=^\s+\.globl|\Z)", HOOKS, re.M | re.S)
    assert m, label
    return [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.split("|")[0].strip()]


def test_the_note_on_hook_replaces_only_the_allocators_call():
    found = [e for e in CODE["edits"] if e["va"] == CF.LOAD_ALLOC_SITE]
    assert len(found) == 1
    e = found[0]
    assert e["stock"] == CF.LOAD_ALLOC_STOCK.hex() == "4eb94002a6a2"
    assert e["new"] == "4eb9" + f"{CODE['c_text_symbols']['load_alloc_hook']:08x}"


def test_the_stub_calls_stocks_allocator_and_keeps_its_two_masks():
    b = _body("load_alloc_hook")
    assert b[:4] == ["pea 4(%sp)", "jsr load_pre", "addq.l #4, %sp", "move.l (%sp)+, load_ret"]
    assert "jsr 0x4002A6A2" in b
    assert b.index("lea -8(%sp), %sp") < b.index("movem.l %d0-%d1, (%sp)") < b.index("jsr load_post")
    assert b[-4:] == ["movem.l (%sp), %d0-%d1", "addq.l #8, %sp", "move.l load_ret, -(%sp)", "rts"]


def test_stock_tracks_and_the_setting_leave_stocks_allocation_alone():
    pre = re.search(r"void load_pre\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "if (load_off || a[2] != 1u || a[0] > 15u)" in pre          # off, a note-off, no track: nothing
    assert "if (!one)" in pre                                          # a stock machine's or MIDI's note: nothing
    assert pre.index("if (fits_now(sum, one * (u32)n, one))") < pre.index("LIVE_POOL &= keep;")


def test_release_tails_are_stolen_first_and_the_dsp_room_decides():
    # 2026-11-13 (the unit, r14b: 16 short JUNO notes with a long release, 12 sounding, the budget never stole)
    pre = re.search(r"void load_pre\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "u32 keep = cand & tails ? tails : held;" in pre           # a release tail first, else a held voice
    assert "smp_tlm_cost[v] > LOAD_TAIL" in pre                       # a tail: the DSP still reports it busy
    assert LD.TAIL * 16 == 2000                                        # over the idle slots, under every release tail
    room = re.search(r"static int room_now\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "smp_room_now[3]" in room and "ROOM_FRESH" in room          # the bus pass's room, the last packet's
    assert "- (int)load_busins - (int)load_pend" in room
    fits = re.search(r"static int fits_now\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "return sum + need <= LOAD_AVAIL;" in fits                  # the fallback while no room is reported
    link = (ROOT / "csrc/sampler/link.c").read_text()
    assert "smp_room_now[t] = v[58 + t];" in link and "smp_room_at = periods | 1u;" in link


def test_the_setting_is_a_personalize_row_default_on():
    assert "#define SET_BUDGET_OFF 8u" in LOAD_C                       # bit 3 (bit 2 LIVE SELECT, bit 1 REMOTE CONTROL)
    assert "return !set_flag(SET_BUDGET_OFF);" in LOAD_C
    assert "load_row(view);" in LIVE_C                                 # after LIVE SELECT's row
    assert _body("load_box")[-2:] == ["jsr load_on", "jmp 0x400979DE"]


def test_the_table_is_generated_and_fits_the_coldfires_words():
    t = LD.load()
    h = LD.c_header(t)
    assert f"#define LOAD_AVAIL {LD.OURS - LD.FIXED}u" in h
    for k in ("md", "mnm", "plaits", "sophie", "a2flt", "mono"):
        assert t[k] and all(0 < v < 65536 for v in t[k] if v), k
    assert len(t["md"]) == 34 and len(t["plaits"]) == 13 and len(t["sophie"]) == 7 and len(t["a2flt"]) == 25
    assert t["send"]["FDN8"] > t["send"]["XDLY"] > 0


def test_the_room_asked_keeps_the_guards_floor_free():
    # 2026-11-13 (the coupled proof): the guard expects a voice at max(1.5 x its cost, FLOOR) at its turn
    from dnfw.perc import guard as G
    assert f"#define LOAD_GUARD_FLOOR {G.FLOOR}u" in LD.c_header(LD.load())
    asked = re.search(r"static int room_asked\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "LOAD_GUARD_FLOOR - one" in asked and "need + need / 2u + floor_part + ROOM_MARGIN" in asked


def test_a_para_chords_notes_are_priced_as_the_dsp_plays_them():
    # 2026-11-15 (main, for the User): PARA (ANALOG 2, JUNO). A note joining a held chord costs a member's voice and what it
    # adds to its leader (the newest note: the DSP runs it first, its leader's guard room is room_asked's); in a full
    # chord too (2026-11-15, the User: "Drop the oldest": the new note plays, the oldest stops); with none held it starts
    # a chord at the track's voice cost. A PARA track's slot is its own measure
    p, pj = LD.load()["para"], LD.load()["para_juno"]
    h = LD.c_header(LD.load())
    for k, name in (("member", "LOAD_PARA_MEMBER"), ("add", "LOAD_PARA_ADD"), ("dropped", "LOAD_PARA_DROPPED")):
        assert f"#define {name} {p[k]}u" in h
    for k, name in (("member", "LOAD_PARA_JUNO_MEMBER"), ("add", "LOAD_PARA_JUNO_ADD")):
        assert f"#define {name} {pj[k]}u" in h
    assert pj["dropped"] == p["dropped"] < pj["add"] < pj["member"]
    assert pj["member"] + pj["add"] < LD.load()["engines"]["JUNO"]
    assert p["dropped"] == round(LD.PER_VOICE * (1 + LD.MARGIN))
    assert p["dropped"] < p["add"] < p["member"] and p["member"] + p["add"] < min(LD.load()["a2flt"])
    join = re.search(r"static u32 para_join_cost\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "LOAD_PARA_DROPPED" not in join and "PARA_NOTES" not in join
    assert "para_member(t) + (para_type(t) == PARA_TYPE_JUNO ? LOAD_PARA_JUNO_ADD : LOAD_PARA_ADD)" in join
    pre = re.search(r"void load_pre\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "one = para_join_cost(t, one);" in pre
    assert "para_on_track(own) ? para_member(own) : voice_cost(own)" in LOAD_C
    assert "|| para_on_track(own))" in LOAD_C          # never released by the budget: hold.c keeps its note-off back
