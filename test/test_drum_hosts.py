"""The table of hosts (2026-11-20, the User: "own page per type"): MONOMACHINE picks its place by ENGN, DRUM (type 56)
by TYPE (dnfw.mnm.machines HOSTS; wr_gen.h mnm_host_*). DRUM's five types each a place of its own (names, choices,
units, starts); the thresholds the ColdFire reads TYPE by give exactly the type the DSP plays; MONOMACHINE's
generated tables byte for byte as on claude/drum before the change (GOLDEN, below)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from dnfw.engines import units as U
from dnfw.engines.drum import drum as D
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.waverider import pages as WP

pytestmark = pytest.mark.skipif(len(MM.MONO_ENGINES) != 5 or D.NAME not in MM.NAMES,
                                reason="a build without MONOMACHINE's five engines or DRUM")

DRUM = MM.HOST_BY_NAME["DRUM"]


def test_two_hosts_monomachine_first_drum_second():
    assert [h.NAME for h in MM.HOSTS] == ["MONOMACHINE", "DRUM"]
    assert [(h.TYPE, h.SEL, h.J) for h in MM.HOSTS] == [(6, "ENGN", 7), (56, "TYPE", 7)]
    assert MM.CF_HOST_PLACES["MONOMACHINE"] == MM.CF_MONO_PLACES == (0, 44, 45, 46, 47)
    assert MM.CF_HOST_PLACES["DRUM"] == (MM.CF_TYPES.index(56),) + tuple(range(48, 55))


def test_drum_has_eight_places_each_its_own_page():
    pl = [MM.CF_ALL[i] for i in MM.CF_HOST_PLACES["DRUM"]]
    assert [P.NAME for P in pl] == ["DRUM KICK", "DRUM CLAP", "DRUM SNAR", "DRUM CRSH", "DRUM CLHH", "DRUM OPHH",
                                    "DRUM RIDE", "DRUM TOM"]
    for t, (P, S) in enumerate(zip(pl, D.PLACES)):
        names = WP.mnm_pnames(P)
        assert names[:8] == S.PNAMES and names[7] == "TYPE" and names[8:8 + len(S.PNAMES2)] == S.PNAMES2
        assert all(n == "---" for n in names[8 + len(S.PNAMES2):])
        assert WP.mnm_pages(P) == 2 and P.HOST == "DRUM" and P.ENGINE == t
        assert WP._choices(P)["TYPE"] == D.TYPES and WP.MNM_WIDGET[WP._ck(P, "TYPE")] == 5 and len(D.TYPES) == 8
        assert WP.MNM_CHOICE_TAGS[WP._ck(P, "TYPE")] == D.TYPE_TAGS
        assert MM.CF_ALL_LIST_NAMES[MM.CF_ALL.index(P)] == ("Drum", "DRM")
        named = WP.mnm_named(MM.CF_ALL.index(P))
        assert all(long_ and long_ != sh for long_, sh in named.values() if sh not in ("-", WP.UNUSED_SHORT))
    assert WP._choices(pl[D.TOM])["RNGE"] == D.RANGES and WP.MNM_WIDGET[("DRUM TOM", "RNGE")] == 5
    assert WP._choices(pl[D.CLAP])["CNT"] == D.COUNTS and WP.MNM_WIDGET[("DRUM CLAP", "CNT")] == 5
    for t in (D.RIDE, D.CRSH):
        assert WP._choices(pl[t])["SET"] == D.SETS and WP.MNM_WIDGET[(pl[t].NAME, "SET")] == 5


def test_every_drum_control_has_a_unit_or_a_choice():
    for i in MM.CF_HOST_PLACES["DRUM"]:
        P = MM.CF_ALL[i]
        for sh in WP.mnm_pnames(P):
            if sh in ("---", "TYPE") or sh in WP._choices(P):
                continue
            assert sh in U.UNITS[P.NAME], (P.NAME, sh)
    assert "DRUM" not in U.UNITS                     # (KICK's moved to its place's key)
    kinds, _at, curves = U.tables([MM.CF_ALL[i] for i in MM.CF_HOST_PLACES["DRUM"]], WP.mnm_pnames)
    assert all(max(c) < 32768 and min(c) >= -32768 for c in curves)


def test_machine_sel_to_drum_starts_kick_and_type_turned_starts_that_type():
    kick = MM.CF_MACHINES[MM.CF_TYPES.index(56)]
    assert kick.NAME == "DRUM KICK" and MM.CF_DEFAULTS[MM.CF_TYPES.index(56)] == D.DEFAULTS
    for t, i in enumerate(MM.CF_HOST_PLACES["DRUM"]):
        P, S = MM.CF_ALL[i], D.PLACES[t]
        words = WP.mnm_default_words(MM.CF_ALL_DEFAULTS[i], P)
        recs = WP.MNM_RECS
        assert words[:8] == [PL.knob_word(x, top, lo) for (_r, _s, lo, top), x in zip(recs[:8], S.DEFAULTS)]
        assert words[8:8 + len(S.DEFAULTS2)] == [PL.knob_word(x, top, lo)
                                                 for (_r, _s, lo, top), x in zip(recs[8:16], S.DEFAULTS2)]
        assert sum((words[7] >> 8) >= th for th in WP.host_thresholds(DRUM)) == t


@pytest.mark.parametrize("host", ["MONOMACHINE", "DRUM"])
def test_the_thresholds_give_the_place_the_dsp_plays_and_the_page_shows(host):
    h = MM.HOST_BY_NAME[host]
    th = WP.host_thresholds(h)
    for v in range(256):
        e = sum(v >= t for t in th)
        assert e == WP.host_dsp_choice(h, v) == WP.host_page_choice(h, v), v


def test_drum_s_dsp_reading_is_its_engine_s():
    """host_dsp_choice (float32, as the DSP) against the plain arithmetic: the record value's knob rounded half up
    (perc.live.knob_word's inverse, the page's), then the engine's type_of"""
    _rid, _slot, _lo, top = WP.MNM_RECS[DRUM.J]
    assert top == 100
    for v in range(top + 1):
        assert WP.host_dsp_choice(DRUM, v) == D.type_of(int(v * 127 / top + 0.5)), v


# -- MONOMACHINE unchanged ------------------------------------------------------------------------------------------
# the generated header's tables, read back from the C text (pages.c_header): every per-place table's rows of the
# 48 places claude/drum had (2e6c8914: the types' 44 and MONOMACHINE's other four engines), the units by their curve
# values, the choice names and tags by name, the names rows of every kind and MONOMACHINE's engines, and
# MONOMACHINE's places and thresholds. sha256 of each part's JSON, measured on claude/drum 2e6c8914's tree with
# this same function (MONOMACHINE's names: wr_mono_*; places, thresholds: mnm_mono_place, mnm_mono_th). 2026-11-20
# (stage 3): DRUM's own place and names row left out (mono_parts), re-measured on 95c764af's tree (before stage 3):
# the same as this tree's.
OLD_PLACES = 48
GOLDEN = {
    "mnm_name_upper": "566b89e8e4bbc91f79c1f51f37042fd30728e8207689ec5d5fa6695bb4b8469c",
    "mnm_name_short": "3363526b44fc90e58df25f52eed0eda413c16f48ef344cb11dc085304f34098c",
    "mnm_npages": "b9395c15bb2a80cca11daa42f97f31a52a6511747a301328936c40faaeded9cd",
    "mnm_labels": "b8021434cf2f1f7e54ffc2a97d8d1fe74d8150bff68df88285e2a02f1b0db976",
    "mnm_choices": "61c26aa94d0d4a1cf0f6df4f330401c47c24bc5f7371bc033502a8fcfd7c2d5e",
    "mnm_order": "97a0f35ec64a892bc6b4253230f9120e517f7a3a1f31b383716c4485df965bb2",
    "mnm_default": "8fc43e001d1bb43b2b7452d5005e13fc1265350e78ffd42314c5befa41985538",
    "mnm_widget": "b408dff8c568be41205424a500cc5c9e14ed31733c0fa9de2f3b19a0d2bf591f",
    "mnm_unit": "4b69dce46d5259f88e1a8e83a921668732f4459f275e964d2879ba0d2ae2bce9",
    "mnm_unit_curve": "ae6ed7331bfa455e1e321b643498225744ac6a21807b0a9f3985a8058eb2b578",
    "mnm_choice_names": "229d315762087e5c1f822aa4cadbcf39de2f64a7c4e82b6ea2b9a898a5bce39f",
    "mnm_tags": "2331db907bed9d240e4f9d7dfd5fd765e8989c121fb1eb887237dda063e591be",
    "wr_named": "2968d41c836c12b40930c2bff0da0493c43e9e0a1c679615542eb783cab5ea01",
    "mono_names": "c971e686b3d8b6db1beabb67be6ae163899cc46eb2279a54d03ae6205b77469e",
    "mono_places": "9863c465ae93f61e90cda3d0dab293c4d18e727faf4e9a0f2b5c1a3630e737b9",
}


def _arrays(txt: str) -> dict[str, list]:
    out = {}
    for m in re.finditer(r"static const [\w\s\*]+?(\w+)((?:\[[^\]]*\])+) = \{", txt):
        out[m.group(1)] = _parse(txt, m.end() - 1)[0]
    return out


def _parse(txt: str, k: int):
    """the brace list at txt[k] -> (nested lists of item strings, the index past it)"""
    assert txt[k] == "{"
    items, cur, k = [], "", k + 1
    while True:
        c = txt[k]
        if c == '"':
            e = txt.index('"', k + 1)
            cur += txt[k:e + 1]
            k = e + 1
        elif c == "{":
            sub, k = _parse(txt, k)
            items.append(sub)
            cur = None
        elif c in ",}":
            if cur is not None and cur.strip():
                items.append(cur.strip())
            cur = ""
            k += 1
            if c == "}":
                return items, k
        else:
            cur = (cur or "") + c
            k += 1


PER_PLACE = ("mnm_name_upper", "mnm_name_short", "mnm_npages", "mnm_labels", "mnm_choices", "mnm_order",
             "mnm_default", "mnm_widget", "mnm_unit")


def mono_parts(hdr: str, places: tuple, mono_names: tuple[str, str], mono_pl: list, mono_th: list) -> dict:
    """2026-11-20 (stage 3): DRUM's own place (KICK's, a type's: index CF_TYPES.index(56)) and its names row are left
    out: KICK's page 2 G (SWHD) is new there; GOLDEN re-measured on 95c764af's tree (before stage 3) with this function"""
    a = _arrays(hdr)
    drum = MM.CF_TYPES.index(56)
    places = tuple(i for i in places if i != drum)
    names, tags, curves = a["mnm_choice_names"], a["mnm_choice_tags"], a["mnm_curves"]
    parts = {k: [a[k][i] for i in places] for k in PER_PLACE}
    parts["mnm_unit_curve"] = [[curves[int(x)] if int(u) & 127 else 0 for x, u in zip(cr, ur)]
                               for cr, ur in ((a["mnm_unit_curve"][i], a["mnm_unit"][i]) for i in places)]
    parts["mnm_choice_names"] = [[names[int(at):int(at) + int(n)] if 0 < int(n) < 200 else n
                                  for at, n in zip(a["mnm_choice_at"][i], a["mnm_choices"][i])] for i in places]
    parts["mnm_tags"] = sorted([int(m), int(j), tags[int(t):int(t) + 5]] for m, j, t in a["mnm_tag_list"]
                               if int(m) in places)
    keep = [i for i, row in enumerate(a["wr_named_short"]) if '"CLKT"' not in row]     # (DRUM's row: KICK's names)
    parts["wr_named"] = [[a["wr_named_long"][i] for i in keep], [a["wr_named_short"][i] for i in keep],
                         a["wr_named_ids"]]
    parts["mono_names"] = [a[mono_names[0]][:4], a[mono_names[1]][:4]]
    parts["mono_places"] = [mono_pl, mono_th]
    return {k: hashlib.sha256(json.dumps(v).encode()).hexdigest() for k, v in parts.items()}


def test_monomachine_s_tables_are_as_before():
    hdr = WP.c_header()
    a = _arrays(hdr)
    n = int(a["mnm_host_n"][0])
    got = mono_parts(hdr, tuple(range(OLD_PLACES)), ("wr_extra_long", "wr_extra_short"),
                     a["mnm_host_place"][:n], a["mnm_host_th"][:n - 1])
    assert {k: v for k, v in got.items() if GOLDEN.get(k) != v} == {}


# -- stage 3 (2026-11-20): the new controls' places, units; TOM's RNGE detents --------------------------------------
def test_stage3_controls_on_their_pages():
    pl = {P.NAME: P for P in (MM.CF_ALL[i] for i in MM.CF_HOST_PLACES["DRUM"])}
    where = {("DRUM KICK", "SWHD"): 8 + 6, ("DRUM SNAR", "WCHR"): 8 + 7, ("DRUM CLHH", "TOP"): 8 + 4,
             ("DRUM CLHH", "DRFT"): 8 + 5, ("DRUM OPHH", "TOP"): 8 + 4, ("DRUM OPHH", "DRFT"): 8 + 5,
             ("DRUM TOM", "RNGE"): 8 + 3}
    for (place, name), j in where.items():
        names = WP.mnm_pnames(pl[place])
        assert names[j] == name, (place, name, names)
        assert name in U.UNITS[place] or name in WP._choices(pl[place])
    # WCHR on page 2 H: PERC's TYPE record (0..127), the DSP's q7
    assert WP.MNM_RECS[15][:2] == tuple(__import__("dnfw.perc.machines", fromlist=["x"]).TYPE_REC)
    snar = D.PLACES[D.SNARE]
    assert snar.DEFAULTS2[7] == 64                    # WCHR's start: the wires as before stage 3


def test_tom_rnge_detents_the_dsp_plays_what_the_page_shows():
    """RNGE (page 2 D, a choice: LOW MID HI, quantised to its detents by the page as JUNO's RNGE): for every value its
    record can hold, the DSP's choice (ref.rnge_of on the float32 value it reads, tom._rnge_oct's arithmetic) is the
    one the page shows ((knob x 3) >> 7, knob = (v 254 + top) / (2 top))"""
    import numpy as np
    from dnfw.engines.drum import ref as R
    _rid, _slot, lo, top = WP.MNM_RECS[8 + 3]
    assert lo == 0
    for v in range(top + 1):
        q = float(np.float32(np.float32(v) * np.float32(1.0 / top)))
        page = (((v * 254 + top) // (2 * top)) * 3) >> 7
        assert R.rnge_of(q) == page, v
    # its three detents: the knob in the middle of each choice's span reads that choice
    for c in range(3):
        k = ((2 * c + 1) * 128) // 6
        assert (k * 3) >> 7 == c


# -- stage 4 (2026-11-20): CLAP, RIDE, CRASH; TYPE's eight spans keep every old project's and preset's type --------
def _old_choice_value(t5: int) -> int:
    """the TYPE record value the page wrote for type T5 of the five (MACHINE SEL's start, a choice through stock's
    setter: the choice's own value, its knob in the middle of its span (2 t + 1) 128 // 10)"""
    _rid, _slot, lo, top = WP.MNM_RECS[DRUM.J]
    return PL.knob_word(((2 * t5 + 1) * 128) // 10, top, lo) >> 8


def test_old_type_values_read_as_their_type():
    """every value a project or a preset made with five types holds (on PERC's 0..100 TYPE record: MACHINE SEL's and a
    TYPE change's start words 9, 30, 50, 70, 90; stock's setter's own values for the choices 9, 30, 50, 70, 91: the
    drumamp step's 0x5b00 for TOM, the DRM presets') reads as the same type on the DSP and the page with eight; the new
    three take the spans no old choice lands in"""
    starts = [_old_choice_value(t) for t in range(5)]
    assert starts == [9, 30, 50, 70, 90]
    for t5, vals in enumerate(zip(starts, (9, 30, 50, 70, 91))):
        name = D.OLD_TYPES[t5]
        for v in vals:
            assert D.TYPES[WP.host_dsp_choice(DRUM, v)] == name == D.TYPES[WP.host_page_choice(DRUM, v)], (name, v)
    assert {D.TYPES[t] for t in range(8)} - set(D.OLD_TYPES) == {"CLAP", "CRSH", "RIDE"}


def test_the_drm_presets_keep_their_types():
    """the 84 DRM presets (presets/DRM): each one's stored TYPE word reads as the type its code names, in the file
    name and the stored name (the User, 2026-11-20: BD SD CH OH TOM CP RD CR), with eight types, and carries its kind's
    stock tag; 01..55 were made
    with five types and keep them (KICK 01..12, SNARE 13..22, CLOSED 23..32, OPEN 33..42, TOM 43..55)"""
    import io
    import pathlib
    import struct
    import zipfile
    from dnfw.wishes import pst as P
    folder = pathlib.Path(__file__).resolve().parents[1] / "presets" / "DRM"
    files = sorted(folder.glob("DRM *.dn2pst"))
    if not files:
        pytest.skip("no presets/DRM in this tree")
    _rid, slot, _lo, _top = WP.MNM_RECS[DRUM.J]
    code = {"BD": "KICK", "SD": "SNAR", "CH": "CLHH", "OH": "OPHH", "TOM": "TOM", "CP": "CLAP", "RD": "RIDE",
            "CR": "CRSH"}
    # the stock tag of each kind (the User, 2026-11-21; no TOM or CLAP tag in the DN2's list: PERCUSSION)
    kind_tag = {"BD": "KICK", "SD": "SNARE", "CH": "HI-HAT", "OH": "HI-HAT", "TOM": "PERCUSSION", "CP": "PERCUSSION",
                "RD": "CYMBAL", "CR": "CYMBAL"}
    old = {range(1, 13): "KICK", range(13, 23): "SNAR", range(23, 33): "CLHH", range(33, 43): "OPHH",
           range(43, 56): "TOM"}
    nums = []
    for f in files:
        num = int(f.name.split(" ")[1])
        z = zipfile.ZipFile(io.BytesIO(f.read_bytes()))
        m = json.loads(z.read("manifest.json"))
        rec = P.body_of(z.read(m["Payload"]))[5:]
        v = struct.unpack_from(">H", rec, 28 + 2 * (slot + 8))[0] >> 8
        t = code[f.name.split(" ")[2].removesuffix(".dn2pst")]
        assert code[m["Payload"].split(" ")[1]] == t, (f.name, m["Payload"])
        assert kind_tag[f.name.split(" ")[2].removesuffix(".dn2pst")] in m["MetaInfo"]["Tags"], (f.name, m["MetaInfo"])
        assert all(t == name for r, name in old.items() if num in r), (f.name, t)
        assert D.TYPES[WP.host_dsp_choice(DRUM, v)] == t == D.TYPES[WP.host_page_choice(DRUM, v)], (f.name, v)
        nums.append(num)
    assert nums == list(range(1, 85))


def test_stage4_controls_on_their_pages():
    pl = {P.NAME: P for P in (MM.CF_ALL[i] for i in MM.CF_HOST_PLACES["DRUM"])}
    for place, p1, p2 in (("DRUM CLAP", ("TUNE", "DCAY", "TONE", "CNT", "SPRD", "TAIL", "DRIV"),
                           ("SNAP", "Q", "HUMN", "GRP", "TLTN", "TATK", "RAMP", "VEL")),
                          ("DRUM RIDE", ("TUNE", "DCAY", "TONE", "BELL", "COLR", "HIT", "DRIV"),
                           ("SET", "SWEL", "ATK", "SNAP", "NOIS", "DRFT", "RIVT", "VEL")),
                          ("DRUM CRSH", ("TUNE", "DCAY", "TONE", "BELL", "COLR", "HIT", "DRIV"),
                           ("SET", "SWEL", "ATK", "SNAP", "NOIS", "DRFT", "RIVT", "VEL"))):
        names = WP.mnm_pnames(pl[place])
        assert names[:8] == p1 + ("TYPE",) and names[8:16] == p2, (place, names)
    # RIDE and CRASH: one page, their own starts
    assert D.PLACES[D.RIDE].DEFAULTS != D.PLACES[D.CRSH].DEFAULTS and U.UNITS["DRUM RIDE"] is U.UNITS["DRUM CRSH"]
