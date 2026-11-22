"""The SHARC+ multifunction compute field (bit 22 set), every category: decode to text, encode from text.

Written from the ADSP-2146x/2156x programming reference, Table 12-12 (MUL/ALU, fixed and float) and Table 12-1 /
PRM ch.25 (multiply with dual add/subtract), as digikit transcribed them (`sharcspec/compute_table.json`,
`multifn_mul_alu`, `multi_function_selector`; test_perc_mfcodec holds this module to that file when it is there).
It is a third reading beside selas/selmap (selache) and digikit, used to check both (scripts/mf_corpus.py) and our
own objects (scripts/gate_mf.py).

The 23-bit field: bit 22 = 1, op6 = bits 21:16, then
    MUL/ALU          15:12 Rm, 11:8 Ra, 7:6 Rxm (R0-R3), 5:4 Rym (R4-R7), 3:2 Rxa (R8-R11), 1:0 Rya (R12-R15)
    MUL + dual ALU   op6 = 1 f ssss (f: float, ssss: Rs), the rest as MUL/ALU
op6 categories (everything else is reserved, `decode` answers None):
    0mmmaa  fixed MUL/ALU, mmmm 0001..0101 (below), aa 00 +, 01 -, 10 average
    011aaa  float MUL/ALU, the multiply always Fm = Fxm * Fym, aaa (FLOAT_ALU)
    10ssss  fixed multiply + dual add/subtract;  11ssss  the same in float
    00000D  MR data move (not a multifunction; decoded, never encoded here)
    00xx11  64-bit float MUL/ALU (register pairs; decoded as such, never encoded here)
Text is selas's syntax (`F12 = F0 * F7, F8 = F8 + F12`), one space round operators, ", " between the parts."""

from __future__ import annotations

import re

FIXED_MUL = {
    0b0001: "R{m} = R{xm} * R{ym} (SSFR)",
    0b0010: "MRF = MRF + R{xm} * R{ym} (SSF)",
    0b0011: "R{m} = MRF + R{xm} * R{ym} (SSFR)",
    0b0100: "MRF = MRF - R{xm} * R{ym} (SSF)",
    0b0101: "R{m} = MRF - R{xm} * R{ym} (SSFR)",
}
FIXED_ALU = {0b00: "R{a} = R{xa} + R{ya}", 0b01: "R{a} = R{xa} - R{ya}", 0b10: "R{a} = (R{xa} + R{ya})/2"}
FLOAT_ALU = {
    0b000: "F{a} = F{xa} + F{ya}",
    0b001: "F{a} = F{xa} - F{ya}",
    0b010: "F{a} = FLOAT R{xa} BY R{ya}",
    0b011: "R{a} = FIX F{xa} BY R{ya}",
    0b100: "F{a} = (F{xa} + F{ya})/2",
    0b101: "F{a} = ABS F{xa}",
    0b110: "F{a} = MAX(F{xa}, F{ya})",
    0b111: "F{a} = MIN(F{xa}, F{ya})",
}
MR_REGS = ("MR0F", "MR1F", "MR2F", None, "MR0B", "MR1B", "MR2B", None)


def regs(c: int) -> dict[str, int]:
    """the register fields of a MUL/ALU or dual field"""
    return {"m": c >> 12 & 15, "a": c >> 8 & 15, "xm": c >> 6 & 3, "ym": 4 + (c >> 4 & 3),
            "xa": 8 + (c >> 2 & 3), "ya": 12 + (c & 3)}


def kind(c: int) -> str | None:
    """'fixed', 'float', 'dual-fixed', 'dual-float', 'mr-move', 'float64' or None (reserved / not bit 22)"""
    if not c >> 22 & 1:
        return None
    op6 = c >> 16 & 0x3F
    if op6 >= 0x20:
        return "dual-float" if op6 & 0x10 else "dual-fixed"
    if op6 >= 0x18:
        return "float"
    if op6 in (0, 1):
        return "mr-move"
    if op6 & 3 == 3 and op6 >> 4 == 0:
        return "float64"
    if (op6 >> 2) in FIXED_MUL and (op6 & 3) in FIXED_ALU:
        return "fixed"
    return None


def decode(c: int) -> str | None:
    """the compute field's text, or None when the category is reserved"""
    k = kind(c)
    if k is None:
        return None
    op6, r = c >> 16 & 0x3F, regs(c)
    if k == "float":
        return f"F{r['m']} = F{r['xm']} * F{r['ym']}, " + FLOAT_ALU[op6 & 7].format(**r)
    if k == "fixed":
        return FIXED_MUL[op6 >> 2].format(**r) + ", " + FIXED_ALU[op6 & 3].format(**r)
    if k.startswith("dual"):
        p, s = ("F", "") if k == "dual-float" else ("R", " (SSFR)")
        return (f"{p}{r['m']} = {p}{r['xm']} * {p}{r['ym']}{s}, {p}{r['a']} = {p}{r['xa']} + {p}{r['ya']}, "
                f"{p}{op6 & 15} = {p}{r['xa']} - {p}{r['ya']}")
    if k == "mr-move":
        mr = MR_REGS[c >> 12 & 7]
        if mr is None or c & 0x8FF:
            return None
        return f"{mr} = R{r['a']}" if op6 & 1 else f"R{r['a']} = {mr}"
    return f"FLOAT64 MULTIFUNCTION {c:#08x}"


def care(c: int) -> int:
    """the bits of field C the operation reads: an MRF destination has no Rm (15:12), ABS no Rya (1:0)"""
    k, op6 = kind(c), c >> 16 & 0x3F
    mask = 0x7FFFFF
    if k == "fixed" and (op6 >> 2) in (0b0010, 0b0100):
        mask &= ~0xF000
    if k == "float" and op6 & 7 == 0b101:
        mask &= ~0x3
    return mask


def _rx(template: str) -> re.Pattern:
    """a FIXED_MUL / FIXED_ALU / FLOAT_ALU template -> a regex with a named group per register"""
    t = re.escape(template)
    for name in ("xm", "ym", "xa", "ya", "m", "a"):
        t = t.replace(re.escape("{" + name + "}"), f"(?P<{name}>\\d+)")
    return re.compile(t.replace(r"\ ", r"\s*").replace(",", r"\s*,"))


_GROUP = {"xm": range(0, 4), "ym": range(4, 8), "xa": range(8, 12), "ya": range(12, 16),
          "m": range(16), "a": range(16), "s": range(16)}


def _field(op6: int, r: dict[str, int]) -> int:
    for k, v in r.items():
        if v not in _GROUP[k]:
            raise ValueError(f"register {k} = {v} outside its group {_GROUP[k]}")
    return ((1 << 22) | (op6 << 16) | (r.get("m", 0) << 12) | (r.get("a", 0) << 8) | (r.get("xm", 0) << 6)
            | ((r.get("ym", 4) - 4) << 4) | ((r.get("xa", 8) - 8) << 2) | (r.get("ya", 12) - 12))


def _match_two(mul_t: str, alu_t: str, text: str) -> dict[str, int] | None:
    m = re.fullmatch(_rx(mul_t).pattern + r"\s*,\s*" + _rx(alu_t).pattern, text, re.I)
    return None if m is None else {k: int(v) for k, v in m.groupdict().items()}


_DUAL = re.compile(r"([RF])(?P<m>\d+)\s*=\s*\1(?P<xm>\d+)\s*\*\s*\1(?P<ym>\d+)(?P<ssfr>\s*\(SSFR\))?\s*,\s*"
                   r"\1(?P<a>\d+)\s*=\s*\1(?P<xa>\d+)\s*\+\s*\1(?P<ya>\d+)\s*,\s*"
                   r"\1(?P<s>\d+)\s*=\s*\1(?P<xa2>\d+)\s*-\s*\1(?P<ya2>\d+)", re.I)


def encode(text: str) -> int:
    """the compute field of TEXT (a multifunction compute alone, `decode`'s form; spacing and case free).
    ValueError when TEXT is not one, or names a register outside its group (never a silent other reading)."""
    t = text.strip().rstrip(";").strip()
    d = _DUAL.fullmatch(t)
    if d:
        g = {k: int(v) for k, v in d.groupdict().items() if k != "ssfr" and v is not None}
        fl = d.group(1).upper() == "F"
        if (g.pop("xa2"), g.pop("ya2")) != (g["xa"], g["ya"]):
            raise ValueError(f"dual add / subtract of different operands: {text}")
        if fl == bool(d.group("ssfr")):
            raise ValueError(f"(SSFR) belongs to the fixed form only: {text}")
        s = g.pop("s")
        if s not in _GROUP["s"]:
            raise ValueError(text)
        return _field((0b110000 if fl else 0b100000) | s, g)
    for aaa, alu_t in FLOAT_ALU.items():
        r = _match_two("F{m} = F{xm} * F{ym}", alu_t, t)
        if r is not None:
            return _field(0b011000 | aaa, r)
    for mmmm, mul_t in FIXED_MUL.items():
        for aa, alu_t in FIXED_ALU.items():
            r = _match_two(mul_t, alu_t, t)
            if r is not None:
                return _field(mmmm << 2 | aa, r)
    raise ValueError(f"not a multifunction compute: {text}")
