"""SHARC float multifunction compute (`Fm = Fx * Fy, Fa = Fb op Fc`, one cycle): our own encoder.

selas encodes the legal forms (operand groups below) itself, and the same word as the firmware's (0x58c830 for
`F12 = F0 * F7, F8 = F8 + F12`); an illegal group it silently assembles as the multiply alone, without a word of
complaint. `verify` (called from sharc_waverider_m3._selas) therefore checks every multifunction line's compute
field, the low 23 bits of the last 32-bit word of the instruction, against `field`, a second encoding.

The encoding (PGR Table 12-12, digikit's compute_table.json; both give the 6-bit multifunction category):
    bit 22 = 1, bits 21:16 = category, 15:12 Fm, 11:8 Fa, 7:6 Fxm (F0-F3), 5:4 Fym (F4-F7),
    3:2 Fxa (F8-F11), 1:0 Fya (F12-F15)
    category 011000  Fm = Fxm * Fym, Fa = Fxa + Fya        011001 ... Fxa - Fya
             011110  ... MAX(Fxa, Fya)                     011111 ... MIN(Fxa, Fya)
Both operands of the multiply read before either result is written (the ALU sees the OLD value of Fm).

2026-11-21 (scripts/mf_corpus.py over every multifunction word of stock 1.12, plus synthetic ones): selmap and digikit
read every category alike; selas (with tools/selache patch 0003) writes every one ADI's way, but an unpatched selas
drops an ABS / FLOAT BY / FIX BY half and reads a dual's subtract operands as the add's, in silence. `verify` refuses
any line with two compute operations that is not a PROVEN form, whatever selas the bench has."""

from __future__ import annotations

import re

from . import mfcodec

CATEGORY = {"+": 0b011000, "-": 0b011001, "MAX": 0b011110, "MIN": 0b011111}
_NAME = {v: k for k, v in CATEGORY.items()}

_DUAL = re.compile(
    r"^\s*F(\d+) = F(\d+) \* F(\d+), F(\d+) = F(\d+) \+ F(\d+), F(\d+) = F(\d+) - F(\d+)(?:, (.*))?;")
_LINE = re.compile(
    r"^\s*F(\d+) = F(\d+) \* F(\d+), F(\d+) = (?:F(\d+) ([+-]) F(\d+)|(MIN|MAX)\(F(\d+), F(\d+)\))"
    r"(?:, (.*))?;")


def field(fm: int, xm: int, ym: int, op: str, fa: int, xa: int, ya: int) -> int:
    """The 23-bit compute field of `Fm = Fxm * Fym, Fa = Fxa op Fya`."""
    assert op in CATEGORY, op
    assert 0 <= fm < 16 and 0 <= fa < 16
    assert 0 <= xm < 4 and 4 <= ym < 8, f"multiplier operands are F0-F3 x F4-F7: F{xm} * F{ym}"
    assert 8 <= xa < 12 and 12 <= ya < 16, f"ALU operands are F8-F11, F12-F15: F{xa}, F{ya}"
    return ((1 << 22) | (CATEGORY[op] << 16) | (fm << 12) | (fa << 8) | (xm << 6) | ((ym - 4) << 4)
            | ((xa - 8) << 2) | (ya - 12))


def field_dual(fm: int, xm: int, ym: int, fa: int, fs: int, xa: int, ya: int) -> int:
    """`Fm = Fxm * Fym, Fa = Fxa + Fya, Fs = Fxa - Fya`: category 11 + Fs (the firmware's dual add/subtract)."""
    assert 0 <= fm < 16 and 0 <= fa < 16 and 0 <= fs < 16
    assert 0 <= xm < 4 and 4 <= ym < 8 and 8 <= xa < 12 and 12 <= ya < 16
    return ((1 << 22) | (0b110000 << 16) | (fs << 16) | (fm << 12) | (fa << 8) | (xm << 6) | ((ym - 4) << 4)
            | ((xa - 8) << 2) | (ya - 12))


def unfield(c: int) -> tuple[int, int, int, str, int, int, int]:
    """The inverse: (fm, xm, ym, op, fa, xa, ya) of a compute field of these categories."""
    assert c >> 22 & 1 and (c >> 16 & 0x3F) in _NAME, hex(c)
    return (c >> 12 & 15, c >> 6 & 3, 4 + (c >> 4 & 3), _NAME[c >> 16 & 0x3F], c >> 8 & 15,
            8 + (c >> 2 & 3), 12 + (c & 3))


def text(fm: int, xm: int, ym: int, op: str, fa: int, xa: int, ya: int, move: str = "") -> str:
    alu = f"F{fa} = MIN(F{xa}, F{ya})" if op == "MIN" else f"F{fa} = MAX(F{xa}, F{ya})" if op == "MAX" \
        else f"F{fa} = F{xa} {op} F{ya}"
    return f"F{fm} = F{xm} * F{ym}, {alu}" + (f", {move}" if move else "") + ";"


def parse(line: str) -> int | None:
    """The compute field of a source line written in full (`text`'s form), else None."""
    d = _DUAL.match(line.split("//", 1)[0])
    if d:
        g = [int(x) for x in d.groups()[:9]]
        assert g[4] == g[7] and g[5] == g[8], f"dual add / subtract of different operands: {line.strip()}"
        return field_dual(g[0], g[1], g[2], g[3], g[6], g[4], g[5])
    m = _LINE.match(line.split("//", 1)[0])
    if not m:
        return None
    g = m.groups()
    fm, xm, ym, fa = int(g[0]), int(g[1]), int(g[2]), int(g[3])
    if g[7]:
        return field(fm, xm, ym, g[7], fa, int(g[8]), int(g[9]))
    return field(fm, xm, ym, g[5], fa, int(g[4]), int(g[6]))


# -- the refusing wrapper (2026-11-21, scripts/mf_corpus.py, docs/selas-encoding.md "Multifunction: the corpus") --

# The categories a build may carry: each read alike by selmap, digikit and dnfw.perc.mfcodec on stock's words and on
# synthetic ones, encoded by selas (patch 0003) as Analog Devices' tools do, AND run by digikit's emulator (so the
# SHARC runner can prove a rewrite bit-exact). Not here: FIX BY (011011, digikit does not run it), every fixed
# point form (0xxxxx: digikit runs none), the 64-bit pair forms (selas reads `F1:0` as SIMD notation).
PROVEN = frozenset({0b011000, 0b011001, 0b011010, 0b011100, 0b011101, 0b011110, 0b011111}
                   | {0b110000 | s for s in range(16)})
_MOVE = re.compile(r"^(?:[RF]\d+\s*=\s*DM\((?:I[0-3],\s*M[0-7]|-?\d+,\s*I[0-3])\)"
                   r"|DM\((?:I[0-3],\s*M[0-7]|-?\d+,\s*I[0-3])\)\s*=\s*[RF]\d+)$", re.I)
_NOT_COMPUTE = re.compile(r"DM\(|PM\(|MODIFY|BITREV|<->|\bJUMP\b|\bCALL\b|\bRTS\b|\bRTI\b|\bDO\b", re.I)
_ALU = re.compile(r"[-+*]|\b(?:MIN|MAX|ABS|FLOAT|FIX|PASS|AND|OR|XOR|NOT|COMP|SCALB|LOGB|MANT|RND|TRUNC|RECIPS|"
                  r"RSQRTS|CLIP|COPYSIGN|ASHIFT|LSHIFT|ROT|FEXT|FDEP|BCLR|BSET|BTGL|BTST|SAT)\b", re.I)


def _parts(code: str) -> list[str]:
    """the comma-separated parts of an instruction, commas inside parentheses kept"""
    out, depth, cur = [], 0, ""
    for ch in code:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def classify(line: str) -> tuple[str, list[str]] | None:
    """(the multifunction compute text, the other parts) of a source line that holds two or more compute
    operations, else None. A line is judged by its text, never by how selas happened to read it."""
    code = line.split("//", 1)[0].strip().rstrip(";").strip()
    parts = _parts(code)
    comp = [p for p in parts if "=" in p and not _NOT_COMPUTE.search(p) and _ALU.search(p.split("=", 1)[1])]
    if len(comp) < 2:
        return None
    return ", ".join(comp), [p for p in parts if p not in comp]


def check_line(line: str) -> int:
    """the compute field a multifunction LINE must assemble to; AssertionError when the line is not one a build
    may carry (category outside PROVEN, a condition, a move other than one DM load / store through I0..I3)"""
    mfc, rest = classify(line)
    try:
        c = mfcodec.encode(mfc)
    except ValueError as e:
        raise AssertionError(f"multifunction line not encodable by dnfw.perc.mfcodec: {line.strip()} ({e})")
    op6 = c >> 16 & 0x3F
    assert op6 in PROVEN, (f"multifunction category {op6:06b} ({mfcodec.kind(c)}) is not proven: "
                           f"{line.strip()} (dnfw.perc.mf.PROVEN)")
    assert len(rest) <= 1 and all(_MOVE.match(p) for p in rest), \
        f"multifunction with a part not proven (one DM load / store through I0..I3 at most): {line.strip()}"
    assert ":" not in line.split("//", 1)[0], f"register pairs in a multifunction line: {line.strip()}"
    return c


def verify(be: bytes, offs: list[int], lines: list[str]) -> list[int]:
    """BE: selas's code (object byte order); OFFS: the byte offset of each instruction; LINES: the source text of
    each. Every line that holds two compute operations (`classify`) must be a proven multifunction form
    (`check_line`), assemble to 48 bits, and carry exactly the compute field dnfw.perc.mfcodec computes from its
    text (the bits the operation reads, mfcodec.care): an independent second encoding, whatever selas the bench
    has (an unpatched selas drops an ABS or FLOAT BY half, or reads a dual's subtract operands as the add's).
    Returns the indices of those lines; anything else raises."""
    found = []
    ends = offs[1:] + [len(be)]
    for k, (o, e, line) in enumerate(zip(offs, ends, lines)):
        if classify(line) is None:
            continue
        c = check_line(line)
        old = parse(line)
        assert old is None or old == c, f"two encodings of {line.strip()}: {old:#x} vs {c:#x}"
        assert e - o == 6, f"multifunction line assembled as {e - o} bytes: {line.strip()}"
        got = int.from_bytes(be[e - 4:e], "big") & 0x7FFFFF
        care = mfcodec.care(c)
        assert got & care == c & care, f"selas encoded {line.strip()} as compute {got:#x}, not {c:#x}"
        found.append(k)
    return found
