"""REMOTE CONTROL in SETTINGS > SYSTEM > USB CONFIG (csrc/devtest/usbcfg.c, usbcfg.S; 2026-11-12): the one OS 1.12
edit in UsbConfigMenuView::rebuild jmps to dt_usb_rebuild, which replays exactly the stock instructions it replaced
and goes on after them; the setting is bit 1 of the mod's settings sector (jump.c), and a FACTORY RESET (bit 1 of the
boot flags the bootstrap hands MAIN OS) turns it OFF."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
USB_S = (ROOT / "csrc/devtest/usbcfg.S").read_text()
USB_C = (ROOT / "csrc/devtest/usbcfg.c").read_text()
JUMP_C = (ROOT / "csrc/jump/jump.c").read_text()

SITE = 0x40105220                       # rebuild, after its three choices: the cursor put back
REBUILD = (0x40104F42, 0x40105248)      # UsbConfigMenuView::rebuild


def test_rebuild_jumps_to_the_fourth_item():
    found = [e for e in CODE["edits"] if e["va"] == SITE]
    assert len(found) == 1
    assert found[0]["stock"] == "205242a72f06"                  # movea.l (%a2),%a0 ; clr.l -(%sp) ; move.l %d6,-(%sp)
    assert found[0]["new"] == "4ef9" + f"{CODE['c_text_symbols']['dt_usb_rebuild']:08x}"


def test_the_replay_is_the_stock_instructions_and_goes_on_after_the_jmp():
    m = re.search(r"^dt_usb_rebuild:\n((?:\s+.+\n)+?)\s+jmp\s+(0x[0-9A-F]+)", USB_S, re.M)
    assert m
    body = [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.strip()]
    assert body[:3] == ["move.l %a2, -(%sp)", "jsr dt_usb_item", "addq.l #4, %sp"]
    assert body[3:] == ["movea.l (%a2), %a0", "clr.l -(%sp)", "move.l %d6, -(%sp)"]
    assert int(m.group(2), 16) == SITE + 6


def test_no_other_edit_touches_rebuild():
    for e in CODE["edits"]:
        if e["va"] == SITE:
            continue
        lo, hi = e["va"], e["va"] + len(e["new"]) // 2
        assert hi <= REBUILD[0] or lo >= REBUILD[1], hex(e["va"])


def test_the_item_uses_stocks_own_pieces():
    """the constructor, the managers and the box are the ones rebuild's choices use (checked against the image by
    coldfire.py's _need at build time)"""
    for want in ("0x401173B8u", "0x40104856u", "0x401048A8u", "0x40115ADCu", "0x44645D84u", "0x40120544u",
                 "0x40188366u", "ITEM_BYTES 0x54u", "BOX_STRIDE 28", "0x40104F42u"):
        assert want in USB_C, want
    assert 'asciz  "REMOTE CONTROL"' in USB_S
    assert "jsr     0x401CEAB8" in USB_S                       # std::string(s, alloc), as stock's label lambdas


def test_the_setting_lives_in_the_settings_sector_and_a_factory_reset_turns_it_off():
    assert "#define SET_REMOTE_OFF 2u" in JUMP_C                # DN2S flags bit 1 set = OFF: no sector reads ON
    assert "u8 set_remote __attribute__((section(\".data\"))) = 1;" in JUMP_C
    assert "#define BOOT_FLAGS (*(volatile u32 *)0x40287A60u)" in JUMP_C
    assert "#define BOOT_FACTORY_RESET 2u" in JUMP_C
    assert "sector[2] = (jmp_on ? SET_JUMP : 0) | (set_remote ? 0 : SET_REMOTE_OFF);" in JUMP_C
    layout = CODE["layout"]
    for name in ("set_remote", "set_reset_seen", "dt_usb_items", "dt_usb_changes"):
        assert name in layout, name


def test_operator_new_is_read_from_d0():
    """stock answers in d0, GCC reads a returned pointer from a0: a pointer-typed declaration hands every functor
    a0's leftover (measured in the emulator, 2026-11-12: free() then spun on it and the UI stopped at boot)"""
    assert "#define OP_NEW ((u32 (*)(u32))0x40120544u)" in USB_C
    assert not re.search(r"\(\(void \*\(\*\)\(", USB_C)        # no stock call declared as returning a pointer
