"""lfo_fast (csrc/modulation/hooks.S): stock's LFO evaluator 0x40137a06 as the shipped build runs it (lfo4's and
lfowaves' edits in it), the same work in fewer ColdFire instructions (2026-11-17, the User: the constant cost, the same work
faster). The copy inlines the stubs it calls or jumps through (lfowaves' a_call and no_phase, lfo4's a4_bottom and
outer, mod_wb, stock's rate routine with its exp2 and 0x40137508), so it must know them word for word: every edit lfo4
and lfowaves make inside the evaluator, and the bytes of every stub the copy inlines, are checked here against what
lfo_fast replays. The addresses it needs (lfo4's state arrays and a4_top, lfowaves' four relocated tables) are read
out of the same edits. Anything different stops the build: lfo_fast would no longer be that evaluator.
"""
from __future__ import annotations

import re

EVAL_VA, EVAL_END = 0x40137A06, 0x40137E0A      # stock's evaluator A, its rts at 0x40137e08
EVAL_ENTRY = bytes.fromhex("4fefffb4122f006b")   # lea -76(%sp),%sp ; move.b 107(%sp),%d1 (untouched by every mod)

# lfo4's edits inside the evaluator: va -> the new bytes, {NAME} an address read out of them
LFO4_EDITS = {
    0x40137A1E: "0a00",
    0x40137A22: "{LIVE}",
    0x40137A28: "{BACKUP}",
    0x40137A40: "{LIVE40}",
    0x40137A65: "03",
    0x40137A78: "4eb9{A4TOP}4e71",
    0x40137AC8: "eb",
    0x40137AD0: "d0",
    0x40137AD4: "{LIVE}",
    0x40137AE0: "eb",
    0x40137AE8: "d0",
    0x40137AEE: "{BACKUP}",
    0x40137DD0: "4eb9{A4BOT}4e71",
    0x40137DDC: "4eb9{OUTER}6014" + "4e71" * 10,
}
# lfowaves': the WAVE bound 6 -> 13, the three value tables relocated, no_phase and a_call jumped to
LFW_EDITS = {
    0x40137B61: "0d",
    0x40137B67: "0d",
    0x40137B6E: "4ef9{NOPHASE}",
    0x40137BC4: "{TA4}",
    0x40137BEE: "{TDC}",
    0x40137BF8: "{TC0}",
    0x40137CDA: "4e",
    0x40137CDC: "{ACALL}",
}
# stock's own words where lfo4 edits (DN2_LFO4 off: lfo_fast replays these; hooks.S LF_LIVE / LF_BACKUP)
STOCK_LIVE, STOCK_BACKUP = 0x44640C18, 0x4463FD18
STOCK_EDITS = {
    0x40137A1C: "487807804879{LIVE}4879{BACKUP}",            # pea 0x780 ; pea LIVE ; pea BACKUP
    0x40137A3E: "43f9{LIVE}",                              # lea LIVE,%a1
    0x40137A64: "7202",                                    # moveq #2,%d1: three LFOs
    0x40137A78: "49ecffde47eb0074",                        # lea -34(%a4),%a4 ; lea 116(%a3),%a3
    0x40137AC6: "2400e78aef884878002890820680{LIVE}",       # the restore's address: 120 a voice
    0x40137ADE: "2400e78aef88487800289082d0880680{BACKUP}",   # the backup's
    0x40137DC2: "53af003045eaffd870ff47ebffd849ecfff0b0af00306600fcaa",          # the bottom
    0x40137DDC: "223c000000ca7e78243c00000099528dd3af0034d5af003cdfaf00387010b08d6600fc52",  # the outer
}
# the stubs lfo_fast inlines, byte for byte ({FN} lfowaves' function table)
A4_BOTTOM = "222f00340c8100000002660a286f003849ecffde600449ecfff0b0af00344e75"
OUTER = "223c000000cad3af0038223c00000099d3af0040223c000000a0d3af003c528d4e75"
A_CALL = "41f9{FN}43ec004e61000038732c004e02810000007f82804ef940137ce0"
KEY = "2009e2880280000003ffe1884e75"                 # a_call's bsr 80f (at +10): +12 + 0x38
NO_PHASE = "752c004c5f826b0442826004756c004e9e804ef940137b74"
# (2026-11-21) lfowaves' NOIS (function table entry 9) and its hash (its bsr at +0x15c), which hooks.S noise_fast
# replays with the same results: checked byte for byte, its address LF_NOISE
NOISE_FN = 9
NOISE = ("4fefffec48d7043c282f0018741ae4ac2001e088e78845f946740000d5c02a0102850000001f262a0004200490920c80ffffffe06c02"
         "52830c80000000206f0253830c850000001f670cb685630842834a806f022605248425430004ed8b888302810000007fea892a016734"
         "0c85000000036736428142822004e4a8610000de76030c8500000001670476069682e6a0d28052820c82000000066ddc2001602420"
         "044282610000b6601a20044282610000ac2200200453804282610000a092802001e2804cd7043c4fef00144e75")
NOISE_HASH_AT = 0x15C
NOISE_HASH = "2602e18be98bd0835280263c9e3779b14c0308002600e08bee8bb780263c85ebca774c0308002600e08bea8bb7804e75"


class LfoFastError(ValueError):
    """lfo4's or lfowaves' code is not what lfo_fast replays."""


def _match(template: str, have: str, found: dict, what: str) -> None:
    pattern = re.escape(template).replace(r"\{", "{").replace(r"\}", "}")
    pattern = re.sub(r"{(\w+)}", lambda m: f"(?P<{m.group(1)}>[0-9a-f]{{8}})", pattern)
    m = re.fullmatch(pattern, have)
    if not m:
        raise LfoFastError(f"{what}: {have} is not {template}")
    for k, v in m.groupdict().items():
        if found.setdefault(k, int(v, 16)) != int(v, 16):
            raise LfoFastError(f"{what}: {k} {v} differs from {found[k]:#x}")


def _edits_in(spec: dict, lo: int, hi: int) -> dict[int, str]:
    return {e["va"]: e["new"] for e in spec["edits"] if lo <= e["va"] < hi}


def values(lfo4_spec: dict | None, lfw_spec: dict, stock=None) -> dict[str, int]:
    """-> the addresses lfo_fast needs, read out of lfo4's and lfowaves' edits; every edit they make in the evaluator,
    and every stub lfo_fast inlines, checked against what it replays. STOCK(va, n): stock's bytes (under lfo4's cave
    pieces); None leaves those two stubs unchecked (the C compile, which has no stock: compose checks them).
    LFO4_SPEC None (2026-11-19, DN2_LFO4 off): stock's evaluator with lfowaves' edits; its LFO state and backup are
    stock's (STOCK_EDITS, checked against stock's bytes when STOCK is given)"""
    found: dict[str, int] = {}
    mods = (("lfo4", lfo4_spec, LFO4_EDITS),) if lfo4_spec is not None else ()
    for name, spec, want in (*mods, ("lfowaves", lfw_spec, LFW_EDITS)):
        have = _edits_in(spec, EVAL_VA, EVAL_END)
        if set(have) != set(want):
            raise LfoFastError(f"{name}'s edits in the evaluator moved: {sorted(map(hex, set(have) ^ set(want)))}")
        for va, template in want.items():
            _match(template, have[va], found, f"{name} {va:#010x}")
    if lfo4_spec is None:
        found.update(LIVE=STOCK_LIVE, BACKUP=STOCK_BACKUP)
        if stock:
            for va, template in STOCK_EDITS.items():
                _match(template, stock(va, len(template.replace("{LIVE}", "0" * 8).replace("{BACKUP}", "0" * 8)) // 2).hex(),
                       found, f"stock {va:#010x}")
    else:
        if found["LIVE40"] != found["LIVE"] + 40:
            raise LfoFastError("lfo4: %a1 is not its live state + 40")
        cave = {}                                 # lfo4's cave, as its edits write it (pieces over stock's bytes)
        for e in lfo4_spec["edits"]:
            for i, b in enumerate(bytes.fromhex(e["new"])):
                cave[e["va"] + i] = b
        for va, template, what in ((found["A4BOT"], A4_BOTTOM, "a4_bottom"), (found["OUTER"], OUTER, "outer"))[:2 if stock else 0]:
            n = len(template) // 2
            under = stock(va, n)
            _match(template, bytes(cave.get(va + i, under[i]) for i in range(n)).hex(), found, f"lfo4's {what}")
    blob, base = bytes.fromhex(lfw_spec["blob"]), lfw_spec["runtime_va"]
    for va, template, what in ((found["ACALL"], A_CALL, "a_call"), (found["ACALL"] + 12 + 0x38, KEY, "a_call's key"),
                               (found["NOPHASE"], NO_PHASE, "no_phase")):
        o = va - base
        _match(template, blob[o:o + len(template.replace("{FN}", "0" * 8)) // 2].hex(), found, f"lfowaves' {what}")
    fn = found["FN"] - base
    noise = int.from_bytes(blob[fn + 4 * NOISE_FN:fn + 4 * NOISE_FN + 4], "big")
    for at, template, what in ((noise, NOISE, "NOIS"), (noise + NOISE_HASH_AT, NOISE_HASH, "NOIS's hash")):
        o = at - base
        if blob[o:o + len(template) // 2].hex() != template:
            raise LfoFastError(f"lfowaves' {what} at {at:#010x} is not what noise_fast replays")
    found["NOISE"] = noise
    return {k: v for k, v in found.items() if k not in ("LIVE40", "A4BOT", "OUTER", "ACALL", "NOPHASE")}


def defines(lfo4_spec: dict, lfw_spec: dict, stock=None) -> dict[str, str]:
    """-> hooks.S's LF_* defines (plain numbers, which the assembler reads)"""
    return {f"LF_{k}": f"{v:#x}" for k, v in values(lfo4_spec, lfw_spec, stock).items()}


def specs() -> tuple[dict | None, dict]:
    """-> lfo4's (None with DN2_LFO4 off) and lfowaves' code specs (the JSONs the shipped build applies after waverider)"""
    from ..mods import lfowaves
    from . import pages
    if not pages.lfo4_on():
        return None, lfowaves.SPEC
    from ..mods import lfo4
    return lfo4.SPEC, lfowaves.SPEC
