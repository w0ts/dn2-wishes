"""The stock send FX's hot state in L2 (opt-stock item 1, the User's GO of 2026-11-12; scratch/opt-stock/README.md).

Stock keeps each send FX's state in one DDR struct, addressed from a base. The delay's struct (base 0x8005912c) is
its two 2 MB lines and then its control words (base + 0x400004 .. + 0x400284); the chorus's (base 0x80459388)
follows them, and the delay's tap loop (sw 0xb83f20) reads ten words past its own, into the chorus's: a stock bug
kept exactly by moving both together. The block 0x80459130..0x8045a6cc (5,532 B, ~7,000 accesses a block) goes to
the memory arbiter's L2 allotment, as one piece in the same order:

- the chorus: its base in the FX init (sw 0x1c168f) and the FX bus (sw 0x1c1bd5), and the unpack's write of its
  parameters (sw 0x1c2976, base + 0x1340), re-pointed;
- the delay: its base stays (its lines stay in DDR); the 70 instructions that reach its control words by an
  offset from the base get the offset moved by the same distance, byte offsets (b) and word-scaled ones (w)
  alike. The table is every such immediate of the stock image's L2 code (the sharcdb listing, 2026-11-12); each
  site is byte-checked against stock 1.12 before it is written.
"""

from __future__ import annotations

import struct

from ..image import sharc_object

FX_DDR, FX_BYTES = 0x80459130, 0x159C            # the delay's control words, then the chorus's struct
FX_L2 = 0x20098400                               # the arbiter's allotment 0x20098400..0x2009b400 (docs/memory-map.md)
FX_ALLOT = (0x20098400, 0x2009B400)
CHORUS_DDR, CHORUS_BYTES = 0x80459388, 0x1344
CHORUS_L2 = FX_L2 + (CHORUS_DDR - FX_DDR)
DELTA = (FX_L2 - FX_DDR) & 0xFFFFFFFF            # what every address in the block moves by

CHORUS_SITES = ((0x1C168F, "0f0480459388"),      # R4 = 0x80459388 (the FX init)
                (0x1C1BD5, "0f0480459388"),      # R4 = 0x80459388 (the FX bus, before CALL 0xb84d5c)
                (0x1C2976, "16038045a6c8"))      # I3 = modify(I3, 0x8045a6c8) (the unpack)

DELAY_SITES = (
    (0xb83e7f, "160c00400108", "b"),  # I5 = modify(I4, 0x400108)
    (0xb83e82, "a82400100042", "w"),  # M4 = DM(I4 + 0x100042)
    (0xb83ef8, "1634004001ec", "b"),  # I2 = modify(I4, 0x4001ec)
    (0xb83efb, "160400400004", "b"),  # I4 = modify(I4, 0x400004)
    (0xb83fa3, "a80100100047", "w"),  # R1 = DM(I4 + 0x100047)
    (0xb83fa8, "0f0000400004", "b"),  # R0 = 0x400004
    (0xb83fc2, "160c0040011a", "b"),  # I5 = modify(I4, 0x40011a)
    (0xb83fc9, "160c00400168", "b"),  # I5 = modify(I4, 0x400168)
    (0xb83fd3, "160400400190", "b"),  # I4 = modify(I4, 0x400190)
    (0xb840c8, "160c00400004", "b"),  # I5 = modify(I4, 0x400004)
    (0xb842ae, "162c00400118", "b"),  # I1 = modify(I4, 0x400118)
    (0xb842ba, "a92d0010008e", "w"),  # DM(I4 + 0x10008e) = M13
    (0xb842bd, "a8020010008f", "w"),  # R2 = DM(I4 + 0x10008f)
    (0xb842c5, "a91c00100089", "w"),  # DM(I4 + 0x100089) = I12
    (0xb842ca, "a91c0010008a", "w"),  # DM(I4 + 0x10008a) = I12
    (0xb842cd, "0f2400400118", "b"),  # M4 = 0x400118
    (0xb842d2, "a9020010008b", "w"),  # DM(I4 + 0x10008b) = R2
    (0xb842da, "160c0040011a", "b"),  # I5 = modify(I4, 0x40011a)
    (0xb842df, "162400400004", "b"),  # I0 = modify(I4, 0x400004)
    (0xb842e8, "160c0040010c", "b"),  # I5 = modify(I4, 0x40010c)
    (0xb84325, "a8020010008e", "w"),  # R2 = DM(I4 + 0x10008e)
    (0xb84328, "a8010010008d", "w"),  # R1 = DM(I4 + 0x10008d)
    (0xb84336, "a80200100043", "w"),  # R2 = DM(I4 + 0x100043)
    (0xb84339, "a80100100042", "w"),  # R1 = DM(I4 + 0x100042)
    (0xb84341, "a80200100044", "w"),  # R2 = DM(I4 + 0x100044)
    (0xb843c8, "aa0e00100047", "w"),  # R14 = DM(I5 + 0x100047)
    (0xb843df, "ab1f00100090", "w"),  # DM(I5 + 0x100090) = I15
    (0xb843e2, "ab1f00100091", "w"),  # DM(I5 + 0x100091) = I15
    (0xb843f2, "0f2400100046", "w"),  # M4 = 0x100046
    (0xb843f5, "ab1c0010008d", "w"),  # DM(I5 + 0x10008d) = I12
    (0xb843f8, "ab1c00100095", "w"),  # DM(I5 + 0x100095) = I12
    (0xb843fb, "ab1c00100094", "w"),  # DM(I5 + 0x100094) = I12
    (0xb843fe, "ab1d0010008b", "w"),  # DM(I5 + 0x10008b) = I13
    (0xb84401, "ab1d00100092", "w"),  # DM(I5 + 0x100092) = I13
    (0xb84404, "ab1f0010008c", "w"),  # DM(I5 + 0x10008c) = I15
    (0xb84407, "ab2c0010008f", "w"),  # DM(I5 + 0x10008f) = M12
    (0xb8440a, "ab2c00100096", "w"),  # DM(I5 + 0x100096) = M12
    (0xb8440d, "ab1e0010008a", "w"),  # DM(I5 + 0x10008a) = I14
    (0xb84410, "ab2d0010008e", "w"),  # DM(I5 + 0x10008e) = M13
    (0xb84413, "163500400178", "b"),  # I3 = modify(I5, 0x400178)
    (0xb8449d, "0f0200400120", "b"),  # R2 = 0x400120
    (0xb844ae, "0f0200400140", "b"),  # R2 = 0x400140
    (0xb84519, "160c00400004", "b"),  # I5 = modify(I4, 0x400004)
    (0xb84594, "160400400119", "b"),  # I4 = modify(I4, 0x400119)
    (0xb845d9, "0f0200400120", "b"),  # R2 = 0x400120
    (0xb845de, "160400400119", "b"),  # I4 = modify(I4, 0x400119)
    (0xb845ef, "0f0e00400140", "b"),  # R14 = 0x400140
    (0xb84674, "0f2400400118", "b"),  # M4 = 0x400118
    (0xb84699, "163b00400119", "b"),  # I4 = modify(I3, 0x400119)
    (0xb846aa, "a70000100093", "w"),  # DM(I3 + 0x100093) = R0
    (0xb846ae, "a60100100090", "w"),  # R1 = DM(I3 + 0x100090)
    (0xb846b4, "a60800100042", "w"),  # R8 = DM(I3 + 0x100042)
    (0xb846b9, "a70200100091", "w"),  # DM(I3 + 0x100091) = R2
    (0xb846be, "a60c00100041", "w"),  # R12 = DM(I3 + 0x100041)
    (0xb846c4, "a70200100090", "w"),  # DM(I3 + 0x100090) = R2
    (0xb846d3, "a70100100041", "w"),  # DM(I3 + 0x100041) = R1
    (0xb846d9, "a70100100043", "w"),  # DM(I3 + 0x100043) = R1
    (0xb846dc, "a70200100044", "w"),  # DM(I3 + 0x100044) = R2
    (0xb846e7, "a60200100045", "w"),  # R2 = DM(I3 + 0x100045)
    (0xb846f2, "a70200100045", "w"),  # DM(I3 + 0x100045) = R2
    (0xb84703, "163b004001b0", "b"),  # I4 = modify(I3, 0x4001b0)
    (0xb84714, "a70100100047", "w"),  # DM(I3 + 0x100047) = R1
    (0xb84744, "0f0d00400120", "b"),  # R13 = 0x400120
    (0xb8475a, "0f0e00400140", "b"),  # R14 = 0x400140
    (0xb847ac, "163b004001ec", "b"),  # I4 = modify(I3, 0x4001ec)
    (0xb847fe, "163b00400204", "b"),  # I4 = modify(I3, 0x400204)
    (0xb8486a, "0f0900400004", "b"),  # R9 = 0x400004
    (0xb84870, "0f0a00400120", "b"),  # R10 = 0x400120
    (0xb84882, "0f0b00400084", "b"),  # R11 = 0x400084
    (0xb84888, "0f0d00400140", "b"),  # R13 = 0x400140
)


def _moved(stock_hex: str, add: int) -> tuple[bytes, bytes]:
    imm = int(stock_hex[4:], 16)
    new = bytes.fromhex(stock_hex[:4]) + struct.pack(">I", (imm + add) & 0xFFFFFFFF)
    return sharc_object.load_bytes(bytes.fromhex(stock_hex)), sharc_object.load_bytes(new)


def patches(sw_to_load, l2_sw_to_load) -> list[tuple[int, int, bytes, bytes]]:
    """(sw, load address, stock bytes, new bytes) of every re-pointed instruction"""
    assert DELTA % 4 == 0 and FX_ALLOT[0] <= FX_L2 and FX_L2 + FX_BYTES <= FX_ALLOT[1]
    out = [(sw, sw_to_load(sw), *_moved(h, DELTA)) for sw, h in CHORUS_SITES]
    out += [(sw, l2_sw_to_load(sw), *_moved(h, DELTA if k == "b" else DELTA // 4)) for sw, h, k in DELAY_SITES]
    return out
