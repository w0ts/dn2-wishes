"""trackbuf.asm (docs/stock-hotspots.md item 2): the stock engine's 16 mono track buffers from DDR to L1,
once, from entry_mark.asm's first pass. The pointer tables' layout and the two jumps are checked against
the source and the assembler's instruction offsets."""

import json
import pathlib
import re

from dnfw.waverider import dsp

SHARC = pathlib.Path(__file__).resolve().parent.parent / "csrc" / "waverider" / "sharc"


def _lines(name):
    return [ln.split("//", 1)[0].strip() for ln in (SHARC / f"{name}.asm").read_text().splitlines()]


def test_the_32_pointer_words_are_the_two_stock_tables_pointing_at_the_l1_buffers():
    stores = {}
    value = None
    for ln in _lines("trackbuf"):
        m = re.fullmatch(r"R9 = (0x[0-9a-f]+);", ln)
        if m:
            value = int(m.group(1), 16)
        m = re.fullmatch(r"DM\((0x[0-9a-f]+)\) = R9;", ln)
        if m:
            stores[int(m.group(1), 16)] = value
    want = {}
    for t in range(16):
        new = dsp.TRACKBUF_DM + 0x80 * t
        want[0x254A60 + 4 * t] = new                                  # TRACK_BUFFERS
        want[0x257EA8 + 4 * t] = new                                  # its copy, the output stage's (contiguous)
    want[dsp.TRACKAUX_PTR] = dsp.TRACKAUX_DM                          # the 17th pointer: the extra 256 B block
    assert stores == want and len(stores) == 33


def test_the_copy_reads_the_stock_ddr_buffers_and_writes_the_l1_ones():
    src = " ".join(_lines("trackbuf"))
    assert f"R9 = {dsp.TRACKAUX_DDR:#x}; I0 = R9; R9 = {dsp.TRACKAUX_DM:#x}; I1 = R9; R10 = 0x240;" in src
    # one contiguous run: the extra block, then the 16 buffers, the same layout in both places
    assert dsp.TRACKAUX_DDR + dsp.TRACKAUX_BYTES == dsp.TRACKBUF_DDR and dsp.TRACKAUX_DM + dsp.TRACKAUX_BYTES == dsp.TRACKBUF_DM
    assert (dsp.TRACKAUX_BYTES + dsp.TRACKBUF_BYTES) == 0x240 * 4


def test_the_jumps_land_on_the_instructions_they_name():
    tb = json.loads((SHARC / "trackbuf.json").read_text())
    em = json.loads((SHARC / "entry_mark.json").read_text())
    tb_at = [dsp.TRACKBUF_SW + o // 2 for o in tb["instruction_offsets"]]
    em_at = [dsp.EMARK_SW + o // 2 for o in em["instruction_offsets"]]
    tb_src = [ln for ln in _lines("trackbuf") if ln and not ln.startswith(".") and not ln.endswith(":")]
    em_src = [ln for ln in _lines("entry_mark") if ln and not ln.startswith(".") and not ln.endswith(":")]
    loop = tb_src.index("R9 = DM(I0, M6);")
    assert f"IF NE JUMP {tb_at[loop]:#x};" in tb_src
    restore = em_src.index("I0 = DM(0x2de148);")
    assert f"JUMP {em_at[restore]:#x};" in tb_src
    done = em_src.index("R10 = DM(0x2de144);")
    assert f"IF EQ JUMP {em_at[done]:#x};" in em_src
    assert f"JUMP {dsp.TRACKBUF_SW:#x};" in em_src
    assert em_src.index(f"JUMP {dsp.TRACKBUF_SW:#x};") == em_src.index("DM(0x2de140) = R10;") + 1


def test_the_new_room_is_free_zero_and_inside_the_region():
    assert dsp.REGION[0] <= dsp.TRACKBUF_CODE_DM and dsp.TRACKBUF_DM + dsp.TRACKBUF_BYTES <= dsp.REGION[1]
    n = len(dsp.objects()["trackbuf"])
    assert dsp.TRACKBUF_CODE_DM + n + 64 <= dsp.TRACKAUX_DM
    assert dsp.PING_CODE_DM + len(dsp.objects()["ping"]) + 64 <= dsp.TRACKBUF_CODE_DM
    assert len(dsp.objects()["entry_mark"]) <= dsp.LOOKUP16_DM - 4 - dsp.EMARK_DM
    for _, at, payload in dsp.spans():
        if at - dsp.LOAD_ALIAS == dsp.TRACKAUX_DM:
            assert not any(payload[:dsp.TRACKAUX_BYTES + dsp.TRACKBUF_BYTES])
