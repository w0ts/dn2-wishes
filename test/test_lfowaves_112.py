"""lfowaves on OS 1.12 (2026-11-14, the User: "Port both"; docs/lfo-112-port.md) and the DN2_LFO4 option.

lfowaves was ported with scripts/port_os112.py (its sources and generator chain) and regenerated against stock 1.12
(scripts/gen_lfo_waves_code.py); the shipped build applies it after waverider (dnfw.mods.SHIPPED). lfo4 waits:
our code's side of it is behind DN2_LFO4, off by default."""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCK_112 = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.12_dist.zip"
SPEC = json.loads((ROOT / "src/dnfw/mods/lfowaves_code.json").read_text())


def test_the_code_is_for_1_12():
    assert SPEC["os"] == "Digitone II 1.12"
    assert SPEC["stock_length"] == 3196288                 # MAIN OS 1.12 (1.11: 3,192,192)
    assert SPEC["runtime_va"] == 0x46780000
    assert len(SPEC["edits"]) == 33 and SPEC["waves"] == ["STEP", "PULS", "NOIS", "TRAP", "WTB1", "WTB2", "WTB3"]


@pytest.mark.skipif(not STOCK_112.exists(), reason="no stock 1.12 image in 00_Resources")
def test_every_edit_expects_stock_1_12s_bytes_and_every_fill_reads_inside_it():
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    main_os = load(read_image(STOCK_112)).container.find(3).unpack()
    base = 0x40000400
    for e in SPEC["edits"]:
        at = e["va"] - base
        assert main_os[at:at + len(e["stock"]) // 2].hex() == e["stock"], hex(e["va"])
    for f in SPEC["fills"]:
        assert 0 <= f["from_va"] - base and f["from_va"] - base + 4 * f["count"] <= len(main_os), hex(f["from_va"])


def test_its_hand_written_addresses_are_1_12s():
    from dnfw.mods import lfowaves
    # getShortName: the same address in 1.12 (its bytes unchanged there); the hook displaces its first two
    # instructions, move.l 8(%sp),%d0 ; cmpi.l #321,%d0
    edit = next(e for e in SPEC["edits"] if e["va"] == lfowaves.SHORT_NAME)
    assert lfowaves.SHORT_NAME == 0x400372DA and edit["stock"].startswith("202f00080c8000000141")
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import lfo_wave_glyph as g
    assert g.SET_STOCK == bytes.fromhex("068644508b68")    # addi.l #0x44508b68 (BSS +0x1000), an immediate
    assert g.FLAG_STOCK == bytes.fromhex("123658f941ec0033")   # lea 51(%a4): a displacement, not an address


def test_the_shipped_build_applies_lfowaves_after_waverider():
    from dnfw.mods import shipped
    assert shipped({}) == shipped({"DN2_LFO4": "0"}) == ("waverider", "lfowaves")
    patcher = (ROOT / "tools/patcher/dn2patch.py").read_text()
    assert "for mid in SHIPPED" in patcher and '"--mod", "waverider", "-o"' not in patcher
    gate = (ROOT / "scripts/ship_gate.py").read_text()
    assert gate.count("for mid in SHIPPED") == 1 and '("lfowaves", "LFO waveforms' in gate
    assert "for mid in SHIPPED" in (ROOT / "scripts/web_bundle.py").read_text()


def test_dn2_lfo4_is_off_unless_asked(monkeypatch):
    from dnfw.waverider import pages
    monkeypatch.delenv("DN2_LFO4", raising=False)
    assert not pages.lfo4_on()
    monkeypatch.setenv("DN2_LFO4", "0")
    assert not pages.lfo4_on()
    monkeypatch.setenv("DN2_LFO4", "1")
    assert pages.lfo4_on()
    cpage = (ROOT / "src/dnfw/waverider/cpage.py").read_text()
    assert 'if PG.lfo4_on():\n            defines["DN2_LFO4"] = 1' in cpage


def test_dn2_lfo4_on_adds_lfo4_and_its_gate_step():
    from dnfw.mods import shipped
    assert shipped({"DN2_LFO4": "1"}) == ("waverider", "lfowaves", "lfo4")
    gate = (ROOT / "scripts/ship_gate.py").read_text()
    assert '("lfo4", "LFO4: modulating' in gate and "scripts/emu_lfo4.py" in gate
