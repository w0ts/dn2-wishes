"""Every address above BSS a mod's bytes name is RAM the mod declares (`dnfw.mods.ramcheck`).

The platform compares declared RAM pairwise, so a declaration that misses a
range defeats it silently. On 2026-09-30 lfo4's LFO state arrays were missing
from its `ram()`, the boot screen's stamp was placed on them, and the first
flash of the three together raised V04 at 0x46700000.

Each mod is checked on the stock it is for: the shipping mods, lfo4 and lfowaves
are OS 1.12's (docs/os112-port.md, docs/lfo-112-port.md); the standalone mods
not ported are 1.11's (os112-port.md: "Their stock checks refuse 1.12"). So every
mod is applied to both stocks; a refusal (ModError) on one is expected, and every
mod has to apply to one of them.
"""

import pathlib

import pytest

from dnfw.mods import ModError, ramcheck

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCKS = {"1.11": ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist.zip",
          "1.12": ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.12_dist.zip"}


@pytest.fixture(scope="module")
def applied(tmp_path_factory):
    """-> {os: (stock MAIN OS, {mod id: (mod, its MAIN OS)})}, {mod id: [what went wrong that is not a refusal]},
    the mods that applied to a stock (a mod writing no MAIN OS, transients, names no RAM there but still counts)"""
    missing = [v for v, p in STOCKS.items() if not p.exists()]
    if missing:
        pytest.skip(f"Digitone II {', '.join(missing)} not in 00_Resources")
    from dnfw.cli.files import read_image
    from dnfw.cli.mods import REGISTRY, _apply_default
    from dnfw.firmware.load import load
    tmp = tmp_path_factory.mktemp("ramcheck")
    out, errors, took = {}, {}, set()
    for version, path in STOCKS.items():
        fw = load(read_image(path))
        mods = {}
        for mid, mod in REGISTRY.items():
            try:
                result = _apply_default(mod, fw, tmp)
            except ModError:
                continue                               # not this stock's mod: it refuses, as it should
            except Exception as exc:                   # anything else is not a refusal
                errors.setdefault(mid, []).append(f"{version}: {type(exc).__name__}: {exc}")
                continue
            took.add(mid)
            if 3 in result.payloads:
                mods[mid] = (mod, result.payloads[3])
        out[version] = (fw.container.find(3).unpack(), mods)
    return out, errors, took


def test_every_mod_applies_to_a_stock(applied):
    """A mod that applies to neither stock is not checked below, so that is a failure here, not a silent pass."""
    from dnfw.cli.mods import REGISTRY
    _out, errors, took = applied
    assert not errors, errors
    assert [mid for mid in REGISTRY if mid not in took] == []


def _declared(mod, content):
    """the mod's ram(): given the image when its ram() takes one (bootscreen's stamp is per OS: 0x46708000 on 1.11,
    0x4670e000 on 1.12; called bare, it answers 1.12's)"""
    import inspect
    ram = getattr(mod, "ram", list)
    if "firmware" in inspect.signature(ram).parameters:
        class _Staged:
            class container:
                @staticmethod
                def find(_section):
                    class _S:
                        @staticmethod
                        def unpack():
                            return content
                    return _S
        return ram(_Staged)
    return ram()


def test_every_mod_declares_the_ram_it_names(applied):
    out, _errors, _took = applied
    bad = {}
    for version, (stock, mods) in out.items():
        for mid, (mod, content) in mods.items():
            found = ramcheck.undeclared(stock, content, _declared(mod, content),
                                        getattr(mod, "NOT_RAM", ()), getattr(mod, "word_spans", list)())
            if found:
                bad[f"{mid} on {version}"] = [f"0x{at:08x} names 0x{v:08x}" for at, v in found[:8]]
    assert not bad, bad


def test_it_would_have_caught_the_stamp_on_lfo4s_state(applied):
    """lfo4 without its state arrays declared, as it was when the stamp went there (lfo4 is OS 1.12's)."""
    from dnfw.mods import lfo4
    out, _errors, _took = applied
    stock, mods = out["1.12"]
    _, content = mods["lfo4"]
    missing = [x for x in lfo4.ram() if not x.what.startswith("LFO state")]
    found = {v & ~0xFFF for _, v in ramcheck.undeclared(stock, content, missing)}
    assert lfo4.STATE_RAM[0][0] & ~0xFFF in found         # LIVE (0x46808000 since 2026-11-17; 0x46700000 before)


def test_word_spans_still_catch_a_real_address(applied):
    """waverider's word_spans (2026-11-17: its C's text by disassembly, its number tables, the DSP's tables) drop
    words that are not addresses, never one that is: with modulation's RAM left out of the declaration, our C's
    references to it are still reported (the matrix's, 0x476f0000, is above the scan's window)"""
    from dnfw.mods import waverider
    from dnfw.waverider import pages as PG
    out, _errors, _took = applied
    stock, mods = out["1.12"]
    _, content = mods["waverider"]
    missing = [x for x in waverider.ram() if not (x.start == PG.MOD_RAM and x.length == PG.MOD_BYTES)]
    found = ramcheck.undeclared(stock, content, missing, waverider.NOT_RAM if hasattr(waverider, "NOT_RAM") else (),
                                waverider.word_spans())
    assert any(PG.MOD_RAM <= v < PG.MOD_RAM + PG.MOD_BYTES for _, v in found), found[:8]
    assert len(found) == sum(PG.MOD_RAM <= v < PG.MOD_RAM + PG.MOD_BYTES + ramcheck.SLACK for _, v in found)


def _chunk_split(monkeypatch, load, image):
    from dnfw.patch import area
    chunk = area.CodeChunk(load=load, image=bytes(image)).pack()
    monkeypatch.setattr(ramcheck.platform, "split", lambda content: (b"", [(area.CODE, chunk)]))


def test_pieces_of_a_relocated_pointer_are_not_addresses(monkeypatch):
    """The "pointer" rule (the User approved it 2026-11-18 as the root fix for the seam false alarms): in our C's data a
    4-byte read that overlaps one of the link's relocated pointers but does not start on it is pieces of it, not an
    address. (1) an undeclared RAM address as a real (relocated) pointer is reported; (2) the same address as a plain
    number, aligned and not, is reported; (4) the seams inside a pointer table, a 6-byte {pointer, byte} struct (as
    fxp_delay's), an 8-byte {pointer, number} pair, and a number before a pointer are not; (5) without the pointer
    sites every one of those seams is reported"""
    import struct
    load = 0x46A40000
    bad = 0x46C00010                                   # RAM above BSS that nothing declares
    p1, p2 = 0x46A7468C, 0x46A745F7                    # string pointers: p1's low half + p2's high half = 0x468c46a7
    img = bytearray([0xFF] * 96)
    sites = []

    def ptr(off, v):
        struct.pack_into(">I", img, off, v)
        sites.append(load + off)
    ptr(0, p1)                                         # a pointer table: p1, p2
    ptr(4, p2)
    ptr(8, bad)                                        # (1) the undeclared address as a relocated pointer
    ptr(16, p1)                                        # a 6-byte struct {label, def} (+ padding): fxp_delay's
    img[20:22] = b"\x00\x00"
    ptr(24, p1)                                        # an 8-byte {pointer, number} pair
    struct.pack_into(">I", img, 28, 0x00001234)
    struct.pack_into(">H", img, 34, 0x468C)            # a number's low half, then a pointer
    ptr(36, p2)
    struct.pack_into(">I", img, 48, bad)               # (2) the same address as a plain number, aligned
    struct.pack_into(">I", img, 58, bad)               # ... and not
    _chunk_split(monkeypatch, load, img)
    seams = [(load + 2, 0x468C46A7), (load + 18, 0x468C0000), (load + 26, 0x468C0000), (load + 34, 0x468C46A7)]
    for at, v in seams:
        assert struct.unpack_from(">I", img, at - load)[0] == v
    real = [(load + 8, bad), (load + 48, bad), (load + 58, bad)]
    spans = [(s, s + 4, "pointer") for s in sites]
    kept = ramcheck.not_addresses(real + seams, b"", spans)
    assert all(r in kept for r in real), kept                                  # (1), (2)
    assert not any(s in kept for s in seams), kept                             # (4)
    assert all(s in ramcheck.not_addresses(seams, b"", []) for s in seams)     # (5)


def test_an_instruction_operand_is_still_an_address(monkeypatch):
    """(3) of the pointer rule's proof (the User, 2026-11-18): an undeclared RAM address an instruction names (lea
    abs.l) in a code span is reported, beside a relocated pointer; the rule leaves the operand rule as it was"""
    import struct
    from dnfw.image import objdump
    if objdump.find_tool() is None:
        pytest.fail("objdump (the m68k toolchain) is needed: unchecked is not passing")
    load = 0x46A40000
    bad = 0x46C00010
    img = bytearray(16)
    img[0:2] = bytes.fromhex("41f9")                   # lea bad,%a0
    struct.pack_into(">I", img, 2, bad)
    img[6:8] = bytes.fromhex("4e75")                   # rts
    struct.pack_into(">I", img, 8, 0x46A7468C)         # a relocated pointer after the code
    _chunk_split(monkeypatch, load, img)
    kept = ramcheck.not_addresses([(load + 2, bad)], b"", [(load, load + 8, "code"), (load + 8, load + 12, "pointer")])
    assert (load + 2, bad) in kept
