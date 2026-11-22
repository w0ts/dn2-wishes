"""AMP ON/OFF for the drum machines (csrc/msel/ampsw.c, dnfw.waverider.ampsw, docs/live-select.md "AMP ON/OFF"): the
drum table, the record field, the ColdFire -> DSP word, the DSP's two hooks as placed, the C's entries and the gate steps
that drive them (scripts/emu_amp_switch.py, scripts/sharc_ampsw_step.py)."""

from __future__ import annotations

import json
import pathlib
import re

from dnfw.waverider import ampsw as AS

ROOT = pathlib.Path(__file__).resolve().parents[1]
C = (ROOT / "csrc/msel/ampsw.c").read_text()


def test_the_drum_machines_by_name():
    from dnfw.mnm import machines as MM
    built = dict(zip((M.NAME for M in MM.MODULES), MM.TYPE_SLOTS))
    types = AS.drum_types()
    assert types[0] == AS.PERC_TYPE == 5
    assert set(types[1:]) == {built[n] for n in AS.DRUM_NAMES if n in built}
    pl = AS.plaits()
    assert pl is not None and pl[0] == built["PLAITS"]
    ty, slot, lo, dmin, dmax = pl
    assert AS.is_drum(ty, (lo + dmin) << 8) and AS.is_drum(ty, (lo + dmax) << 8 | 0xFF)
    assert not AS.is_drum(ty, (lo + dmin - 1) << 8)
    assert not any(AS.is_drum(t, 0) for t in (0, 1, 2, 3, 4, 6, built["TB303"], built["ANALOG2"], built["JUNO"]))


def test_the_field():
    wish = (ROOT / "csrc/wishes/wish.h").read_text()
    tags = {int(v, 16): n for n, v in re.findall(r"#define (WT_[A-Z0-9_]+) (0x[0-9a-fA-F]+)u", wish)}
    assert tags[AS.TAG] == "WT_AMP_SW" and AS.TAG & 0xC000 == 0     # neither must-understand nor tied to the machine
    assert sum(1 for t in tags if t == AS.TAG) == 1 and AS.ON == 1
    assert "wish_put(s, WT_AMP_SW, &v, on ? 1u : 0u)" in C           # OFF: the field removed (old sounds read OFF)
    assert "wish_get(s, WT_AMP_SW, &v, 1) == 1 && v == AS_ON" in C


def test_the_c_header():
    head = AS.c_header()
    pl = AS.plaits()
    assert f"#define AS_TYPES {', '.join(map(str, AS.drum_types()))}" in head
    assert f"#define AS_PLAITS {pl[0]}" in head and f"#define AS_MODL_SLOT {pl[1]}" in head
    assert f"#define AS_MODL_DRUM_MIN {pl[3]}" in head and f"#define AS_MODL_DRUM_MAX {pl[4]}" in head
    assert f"#define AS_VOL_PLACE {AS.VOL_PLACE}" in head


def test_the_word_for_the_dsp():
    from dnfw.sampler import machines as SM
    off = AS.pool_off()
    assert off == SM.LV_WANT_OFF + 4 and SM.TABLE_READY + 0x120 < off < SM.TABLE_READY + 512
    assert AS.MAGIC & 0xFFFF == 0 and AS.MAGIC >> 16
    cp = (ROOT / "src/dnfw/waverider/cpage.py").read_text()
    assert 'defines["AS_POOL_OFF"]' in cp and 'defines["AS_MAGIC"]' in cp
    link = (ROOT / "csrc/sampler/link.c").read_text()
    assert "off = AS_POOL_OFF / 4u;" in link and "asw_w = AS_MAGIC | m;" in link
    assert "smp_tables == 2" in link[link.index("extern u32 as_mask;"):link.index("asw_w = AS_MAGIC | m;")]


def test_the_c_entries():
    page = (ROOT / "csrc/waverider/page.c").read_text()
    assert "as_poll();" in page
    assert "as_draw(c);" in (ROOT / "csrc/scope/scope.c").read_text()
    rec = (ROOT / "csrc/sampler/rec.c").read_text()
    assert rec.index("if (as_pop(it))") < rec.index("if (ldp_pop(it))") < rec.index("if (mxp_pop(it))")
    for leftover in ("da_drum", "da_commit", "da_poll", "da_modl", "da_loaded", "da_keep", "da_back"):
        for f in ("csrc/sampler/rec.c", "csrc/sampler/fmt.c", "csrc/msel/msel.c", "csrc/waverider/page.c",
                  "csrc/wishes/table.c"):
            assert leftover not in (ROOT / f).read_text(), (leftover, f)
    assert not (ROOT / "csrc/msel/drumamp.c").exists()


def test_the_dsp_hooks():
    from dnfw.waverider import dsp
    asm = (ROOT / "csrc/waverider/sharc/ampsw.asm").read_text()
    strip = re.compile(r"(JUMP\s+)0x[0-9a-f]+(;\s*//\s*->)")
    assert strip.sub(r"\g<1>0x0\2", asm) == AS.asm_text()             # generated; only the targets resolved
    code = json.loads((ROOT / "src/dnfw/waverider/sharc_code.json").read_text())
    assert code["ampsw"]["load_sw"] == hex(AS.CODE_SW)
    lines = [ln.split("//")[0].strip() for ln in asm.splitlines()]
    body = [ln for ln in lines if ln and not ln.startswith(".") and not ln.endswith(":")]
    assert lines.index("wr_asw_b.:") < lines.index("wr_asw_a.:")       # B the object's start (ENTRY_B_SW)
    assert AS.ENTRY_B_SW == AS.CODE_SW and obj_b_target(code) == AS.CODE_SW
    assert f"JUMP {AS.SITE_A_RESUME:#x};" in body and f"JUMP {AS.SITE_B_RESUME:#x};" in body
    assert all(x in body for x in AS.SITE_A_DISPLACED) and AS.SITE_B_DISPLACED in body
    obj = dsp.objects()
    assert len(obj["ampsw_a_jump"]) == 6 and len(obj["ampsw_b_jump"]) == 6
    assert len(obj["ampsw"]) + dsp.L2_TAIL <= AS.CODE_SPAN
    pl = {x["what"].split(" at sw ")[1].split()[0]: x for x in dsp.placements() if "AMP ON/OFF's hook" in x["what"]}
    assert set(pl) == {hex(AS.SITE_A_SW), hex(AS.SITE_B_SW)}
    assert pl[hex(AS.SITE_A_SW)]["stock"] == dsp.AMPSW_A_STOCK.hex() and pl[hex(AS.SITE_B_SW)]["stock"] == dsp.AMPSW_B_STOCK.hex()
    assert any(w.startswith("AMP ON/OFF's words") for w, *_r in dsp.regions())
    assert AS.DUMMY + 128 == AS.END == dsp.TRACKAUX_DM                  # the scratch buffer: 32 floats, ours alone


def obj_b_target(code) -> int:
    """the JUMP at sw 0x1c9a3a's target, from its committed source line"""
    return int(code["ampsw_b_jump"]["source"].split()[1].rstrip(";"), 16)


def test_the_gate_steps():
    gate = (ROOT / "scripts/ship_gate.py").read_text()
    assert '("drumamp", "AMP ON/OFF on the drum machines: H on the AMP page, the field, the DSP\'s mask (ColdFire)")' in gate
    assert '("ampdsp", "AMP ON/OFF: OFF unity bit for bit, ON and every other slot stock\'s (SHARC runner)")' in gate
    assert '"scripts/emu_amp_switch.py"' in gate and '"scripts/sharc_ampsw_step.py"' in gate
    times = json.loads((ROOT / "scripts/gate_times.json").read_text())
    assert "drumamp" in times["steps"] and "ampdsp" in times["steps"]
    so = (ROOT / "scripts/sharc_stockout_step.py").read_text()
    assert "AMP ON/OFF" in so and "sharc_ampsw_step.py" in so
