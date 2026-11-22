"""SAFE MODE (docs/safe-mode.md): the unpatch table, the kernel chunk's placement, and the constants every half shares."""

from __future__ import annotations

import pathlib
import random
import re
import struct

import pytest

from dnfw import safemode as T
from dnfw.mods import platform, safemode as M

ROOT = pathlib.Path(__file__).resolve().parents[1]
CS = ROOT / "csrc" / "safemode"


def _pair(seed=1, n=400):
    rng = random.Random(seed)
    stock = bytes(rng.randrange(256) for _ in range(T.STOCK_LEN))
    built = bytearray(stock)
    for _ in range(n):
        at = rng.randrange(0, T.STOCK_LEN - 600)
        for k in range(rng.choice((1, 4, 6, 300))):
            built[at + k] ^= 0x5A
    for va, ln, _ in T.NEVER:                     # the build always changes the loader's two runs
        for k in range(ln):
            built[va - T.BASE + k] ^= 0xFF
    built[T.STOCK_LEN - 1] ^= 1                   # the last byte, and a long gap before it
    return stock, bytes(built)


def test_the_table_gives_stock_back_except_the_never_runs():
    stock, built = _pair()
    table = T.build_table(stock, built)
    restored = T.apply(built, table)
    diff = [i for i in range(T.STOCK_LEN) if restored[i] != stock[i]]
    assert diff and all(T._never(i, 1) for i in diff)
    assert sum(ln for _, ln, _ in T.NEVER) == len(diff)
    assert table.endswith(T.END)
    assert all(T.check(stock, built, table)[k][0] for k in (0, 1))


def test_runs_longer_than_255_and_long_gaps_are_split():
    stock = bytes(T.STOCK_LEN)
    built = bytearray(stock)
    built[0x1000:0x1000 + 700] = b"\x01" * 700    # one run of 700 B (clear of the start-up call at +0x13e)
    built[0x200000] = 2                            # a gap past 0xFFFF
    table = T.build_table(stock, bytes(built))
    runs = T.decode(table)
    assert [len(d) for _, d in runs] == [255, 255, 190, 1]
    assert runs[-1][0] == 0x200000
    assert T.apply(bytes(built), table) == stock


@pytest.mark.parametrize("bad", ["cut", "trailing", "never", "past"])
def test_a_bad_table_is_refused(bad):
    stock, built = _pair(2, 20)
    table = T.build_table(stock, built)
    if bad == "cut":
        table = table[:-3]
    elif bad == "trailing":
        table += b"\0"
    elif bad == "never":                           # a run onto the start-up call
        off = T.NEVER[0][0] - T.BASE
        table = struct.pack(">HIB", 0xFFFF, off, 8) + bytes(8) + T.END
    else:
        table = struct.pack(">HIB", 0xFFFF, T.STOCK_LEN - 2, 8) + bytes(8) + T.END
    with pytest.raises(T.TableError):
        T.decode(table)
    assert not T.check(stock, built, table)[0][0]


def test_check_finds_a_table_that_leaves_a_byte_of_ours():
    stock, built = _pair(3, 10)
    rs = T.runs(stock, built)
    table = T.encode(stock, rs[1:])                # the first run left out
    res = T.check(stock, built, table)
    assert res[0][0] and not res[1][0]


def test_the_kernel_is_placed_first_among_code_chunks_with_its_head_filled():
    stock, built = _pair(4, 30)
    other = platform.area.CodeChunk(0x46900000, b"\x4e\x75" * 8, 0, 0x46900000).pack()
    data = (b"BOOT", b"x" * 16)
    code, facts = M.chunk(stock, built, [data, (platform.area.CODE, other)])
    k = platform.area.CodeChunk.unpack(code)
    magic, build, off, n, crc = struct.unpack_from(M.HEAD, k.image, 0)
    assert (k.load, k.bss, k.init) == (M.SPEC["load"], 0, M.SPEC["init"])
    assert magic == M.MAGIC and off == len(bytes.fromhex(M.SPEC["code"])) and T.crc(k.image[off:off + n]) == crc
    assert T.apply(built, k.image[off:off + n]) == T.apply(built, T.build_table(stock, built))
    assert facts["build"] == build


def test_the_shared_constants_agree():
    h = (CS / "sm.h").read_text()
    kernel = (CS / "kernel.c").read_text()
    erase = (ROOT / "csrc/sampler/erase.c").read_text()
    assert f"#define SM_RAM        0x{M.SM_RAM:08X}u" in h
    dm = (ROOT / "csrc/include/dmove.h").read_text()     # v0.69.2: the record moved (normal.c), erase.c follows it
    assert "#define SM_SECTOR     0x6E0300u" in h and "#define DM_SAFE_OLD 0x6E0300u" in dm
    assert "#define DM_SAFE_NEW 0x5FFB00u" in dm and "#define SB_AT 0x5FFB00u" in erase
    assert "SM_LOAD       (SM_RAM + 0x100u)" in h and M.SPEC["load"] == M.SM_RAM + 0x100
    assert re.search(r"0x476F8100", (ROOT / "scripts/gen_safemode_code.py").read_text())
    for va, stock, _ in T.OVERRIDES:            # the kernel checks the same stock bytes the gate does
        bs = ", ".join(f"0x{b:02X}" for b in bytes.fromhex(stock))
        assert f"{{0x{va:08X}u, {{{bs}}}}}" in kernel, hex(va)
    for va, ln, _ in T.NEVER:
        assert f"0x{va:08X}u" in kernel and f"{ln}u" in kernel
    assert f"0x{T.STOCK_LEN:08X}u" in kernel and f"0x{T.BASE + T.STOCK_LEN:08X}u" in kernel


def test_safemode_is_shipped_last():
    from dnfw.mods import shipped
    assert shipped({})[-1] == "safemode" and shipped({"DN2_LFO4": "1"})[-1] == "safemode"
    assert M.APPLY_LAST


def test_the_question_uses_the_stock_calls_rec_c_proves_and_stock_line_widths():
    """question.c opens stock's ConfirmWindow with the same 1.12 calls rec.c's NAME screen uses (gated there), its
    texts fit stock's question lines (21 characters: "SAVE ALL PATTERNS AND"), and its answer only reads the bool's
    low byte (stock's invoker 0x401089fc: tst.b of the argument's last byte)"""
    q = (CS / "question.c").read_text()
    rec = (ROOT / "csrc/sampler/rec.c").read_text()
    for name, va in (("NEW", "0x40120544u"), ("STR", "0x401CEAB8u"), ("STR_FREE", "0x401CD008u"),
                     ("FN_FREE", "0x40188366u"), ("OPEN", "0x4011CB9Eu"), ("COUNT_FREE", "0x401883ACu"),
                     ("MAIN_VIEW", "0x44648980u")):
        assert re.search(rf"#define Q_{name}\s.*{va}", q) and re.search(rf"#define SN_{name}\s.*{va}", rec), name
    assert "0x40112D0Eu" in q and "0x401DD7E4u" in q and "#define Q_BYTES      0x8Cu" in q
    texts = re.findall(r'Q_STR\(&s_\w+, (?:why == 2u \? )?"([^"]+)"(?: : "([^"]+)")?', q)
    flat = [t for pair in texts for t in pair if t]
    assert len(flat) == 3 and all(len(t) <= 21 for t in flat), flat
    assert "yes & 0xFFu" in q
    assert "volatile uint32_t reason;" in (CS / "sm.h").read_text()
    assert "sm_asked" in M.SPEC["symbols"]


def test_the_stop_entry_reads_stock_button_state_not_the_ui_queue():
    """FUNC never reaches the UI queue as a key item (measured), so "STOP alone" is read from stock's own button bytes"""
    n = (CS / "normal.c").read_text()
    assert "#define SM_KEYS       ((volatile const uint8_t *)0x445A2E30u)" in n
    assert "SM_STOP_CHAN  2u" in n and "SM_STOP_MASK  0x10u" in n and "smp_held_lo ==" not in n
