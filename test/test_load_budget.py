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
    # 2026-11-16 (PARA as one voice, csrc/para/one.c): pv_pre first; a joining note returns with no slot (d0 = d1 = 0)
    assert b[:5] == ["move.l %fp, -(%sp)", "move.l %a2, -(%sp)", "pea 12(%sp)", "jsr pv_pre", "lea 12(%sp), %sp"]
    j = b.index("1:      pea 4(%sp)") if "1:      pea 4(%sp)" in b else b.index("1: pea 4(%sp)")
    assert b[5:j] == ["tst.l %d0", "beq.s 1f", "moveq #0, %d0", "moveq #0, %d1", "rts"]
    assert b[j + 1:j + 4] == ["jsr load_pre", "addq.l #4, %sp", "move.l (%sp)+, load_ret"]
    assert "jsr 0x4002A6A2" in b
    assert b.index("lea -8(%sp), %sp") < b.index("movem.l %d0-%d1, (%sp)") < b.index("jsr load_post") < b.index("jsr pv_post")
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


def test_a_para_chord_is_priced_as_one_voice_by_its_notes():
    # 2026-11-21: PARA as one voice (csrc/para/one.c): a chord's slot renders every sounding note, so it costs its
    # track's voice + BASE + ADD[N] (scripts/para_cost.py, the one-voice chords measured: until then the table kept the
    # two-voice design's member costs, which priced a chord's slot as one member). A join never reaches load_pre; a
    # PARA note that does starts a chord: one note. A PARA chord's slot is never released for another note
    t = LD.load()
    h = LD.c_header(t)
    for key, pre in (("para", "LOAD_PARA"), ("para_juno", "LOAD_PARA_JUNO")):
        p = t[key]
        add, chord = p["add"], p["chord"]
        assert f"#define {pre}_BASE {p['base']}u" in h
        assert len(add) == 9 and add[0] == add[1] == 0 and len(chord) == 8
        assert all(a < b for a, b in zip(add[1:], add[2:])), add          # each joined note costs more
        assert 0 < p["base"] < add[2]
        m = 1 + LD.MARGIN
        for n in range(2, 9):              # a chord of 1 + ADD[N] covers the dearest chord of N measured (x margin)
            assert round(chord[0] * m) + add[n] >= round(chord[n - 1] * m) - 1, (key, n)
    assert "load_para_add[" in h and "load_para_juno_add[" in h and "#define LOAD_PARA_NOTES 8" in h
    assert "para_join_cost" not in LOAD_C and "LOAD_PARA_MEMBER" not in LOAD_C
    pre_ = re.search(r"void load_pre\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "if (para_on_track(t))" in pre_ and "one = para_chord(t, 1);" in pre_
    assert "para_on_track(own) ? para_chord(own, para_notes(v, own)) : voice_cost(own)" in LOAD_C
    notes = re.search(r"static int para_notes\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "PV_SOUND" in notes and "c->track == (u8)t" in notes
    assert "_Static_assert(LOAD_PARA_NOTES == PARA_NOTES" in LOAD_C
    assert "|| para_on_track(own) || (lat & b))" in LOAD_C   # never released by the budget (nor a HOLD latch, v0.64)


def test_the_table_covers_every_place_the_firmware_has():
    # 2026-11-21: table.json held 15 places for the firmware's 55 (places renumbered, DRUM's types added, not
    # regenerated): VOICE BUDGET read load_mnm past its end for JUNO, DRONE, TB303, DRUM, MONOMACHINE's engines 2-5
    from dnfw.mnm import machines as MM
    t = LD.load()
    names = [M.NAME for M in MM.CF_ALL]
    assert t["mnm_names"] == names, "table.json is stale: run scripts/gen_load_table.py"
    assert len(t["mnm"]) == len(names)
    for name, cost in zip(names, t["mnm"]):
        assert (cost == 0) == (name == "REMOVED"), name          # a place with no cost would be a free voice
    for name in ("JUNO", "DRONE", "TB303", *MM.MONO_ENGINES):
        assert t["mnm"][names.index(name)] == t["engines"][name], name
    for M in MM.CF_ALL:                                          # DRUM's types: the dearer of start and worst
        if getattr(M, "HOST", "") == "DRUM":
            case = M.NAME.replace(" ", "-")
            assert t["mnm"][names.index(M.NAME)] == max(t["engines"][case], t["engines"][case + "-WORST"]), M.NAME
    assert t["mono"] == [t["engines"][n] for n in MM.MONO_ENGINES]


def test_the_coldfire_reads_the_place_table_bounded_and_refuses_a_stale_one():
    from dnfw.mnm import machines as MM
    t = LD.load()
    h = LD.c_header(t)
    assert f"#define LOAD_MNM_N {len(MM.CF_ALL)} " in h
    assert f"#define LOAD_MNM_MAX {max(t['mnm'])}u" in h
    assert "typedef char load_mnm_covers_every_place[(LOAD_MNM_N == MNM_N) ? 1 : -1];" in h   # (MNM_N: pages.c_header)
    assert LOAD_C.count("load_mnm[") == 1                        # the one read, in mnm_cost
    cost = re.search(r"static u32 mnm_cost\(int p\)\n{\n(.*?)\n}\n", LOAD_C, re.S).group(1)
    assert "p >= 0 && p < LOAD_MNM_N ? load_mnm[p] : LOAD_MNM_MAX" in cost
    stale = dict(t, mnm=t["mnm"][:15], mnm_names=t["mnm_names"][:15])
    try:
        LD.c_header(stale)
    except ValueError as e:
        assert "gen_load_table" in str(e)
    else:
        raise AssertionError("a stale table must stop the build")
