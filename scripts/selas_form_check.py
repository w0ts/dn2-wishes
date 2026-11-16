"""Is selas encoding what ADI's tools would? (2026-11-12, after selas wrote MODIFY(I4,M4) in a layout the SHARC+
reads as `if gt i7=modify (i0,m1)`: docs/selas-encoding.md)

    python scripts/selas_form_check.py STOCK.syx [--selas PATH] [--json OUT]

Two checks, on the farm bench (selas and selmap are there):

(a) **ours, read back**: every object of ours (csrc/waverider/sharc/*.json), decoded by selmap (selache's own
    SHARC+ disassembler), against its source line -- the runner's decode step, which covers only PERC, the sample
    machines, block_count and ping, over every object.
(b) **each form, against ADI**: every instruction form our objects use (selmap's text with register numbers and
    constants abstracted, DAG1 and DAG2 apart), and for each up to three instructions of the same form in the stock
    DSP code (compiled by ADI's tools): their text assembled by selas, its bytes against stock's. A form stock never
    uses is listed (nothing to compare it with). Branches are compared too (selas puts relative targets in the word
    as stock does); forms selmap prints as opcodes only (`alu opcode 0x80`) cannot be assembled and are listed.

Exit 1 if (a) or (b) finds a mismatch. Known and corrected after selas (by the build): Type 6b shifts by an
immediate (sharc_waverider_m3.fix_shift_imm), reported apart.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.cli.files import read_image            # noqa: E402
from dnfw.firmware.load import load              # noqa: E402
from dnfw.image import bootstream, sharc_object  # noqa: E402
import sharc_waverider_m5 as m5                  # noqa: E402
import sharc_waverider_render as m1              # noqa: E402

SHARC = ROOT / "csrc" / "waverider" / "sharc"
SW_ALIAS = 0x28000000
CODE_RANGES = ((0x1C0000, 0x1E0000), (0xB80000, 0xC00000))     # where stock's code is (the rest of the blocks: data)
PER_FORM = 3


def be_of(le: bytes) -> str:
    """stock's bytes (16-bit parcels, little-endian) -> the parcels MSW first, as selas's objects hold them"""
    return b"".join(le[i:i + 2][::-1] for i in range(0, len(le), 2)).hex()


def form(text: str) -> str:
    """selmap's text -> its form: numbers out, register numbers out but DAG1 / DAG2 kept apart"""
    t = text.lower()
    t = re.sub(r"\b([im])(\d+)\b", lambda m: m.group(1) + ("#" if int(m.group(2)) < 8 else "%"), t)
    t = re.sub(r"\b([rfsbl])(\d+)\b", r"\1#", t)
    t = re.sub(r"-?0x[0-9a-f]+|-?\b\d+\b", "N", t)
    return re.sub(r"\s+", " ", t).strip()


def stock_code(stock: pathlib.Path, work: pathlib.Path) -> list[tuple[int, str, str]]:
    """(sw, bytes MSW first, selmap text) of every instruction in stock's code ranges"""
    stream = load(read_image(stock)).container.find(7).unpack()
    out = []
    for b in bootstream.walk(stream).blocks:
        if not b.has_payload or b.target < SW_ALIAS or (b.target - SW_ALIAS) % 2:
            continue
        sw0 = (b.target - SW_ALIAS) // 2
        if not any(lo <= sw0 < hi for lo, hi in CODE_RANGES):
            continue
        payload = stream[b.offset + bootstream.HEADER:b.offset + bootstream.HEADER + b.count]
        for off, (size, t) in sorted(m5.selmap_text(payload, work).items()):
            out.append((sw0 + off // 2, be_of(payload[off:off + size]), t))
    return out


def _shipped() -> set[str] | None:
    """the objects the build loads (dnfw.waverider.dsp.objects, PERC's spans), or None if dsp cannot be imported"""
    try:
        from dnfw.waverider import dsp
        return set(dsp.objects()) | set(getattr(dsp, "PERC_SPANS", {}))
    except Exception:
        return None


def same(a: str, b: str) -> bool:
    """two texts of one instruction (the decode step's norm), ASTAT = ASTATX, a constant signed or not"""
    def n(t):
        t = m5.norm(t).replace("astatx", "astat")
        return re.sub(r"=(-?)0x([0-9a-f]+)$", lambda m: "=%#x" % ((-1 if m.group(1) else 1) * int(m.group(2), 16)
                                                                  & 0xFFFFFFFF), t)
    return n(a) == n(b)


def our_objects() -> dict[str, tuple[bytes, list[int], list[str]]]:
    """name -> (code, instruction offsets, source lines) of every object the build loads"""
    out = {}
    shipped = _shipped()
    for spec_path in sorted(SHARC.glob("*.json")):
        if shipped is not None and spec_path.stem not in shipped:
            continue
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if "object_parcels_be" not in spec or "instruction_offsets" not in spec:
            continue
        src = SHARC / f"{spec_path.stem}.asm"
        if not src.exists():
            continue
        lines = [ln for ln in src.read_text(encoding="utf-8").splitlines()
                 if (t := ln.split("//", 1)[0].strip()) and not t.startswith(".") and not t.endswith(":")]
        out[spec_path.stem] = (sharc_object.load_bytes(bytes.fromhex(spec["object_parcels_be"])),
                               spec["instruction_offsets"], lines)
    return out


def read_back(objs, work) -> tuple[dict, dict[str, list[tuple[str, str]]]]:
    """(a): -> ({name: [disagreement]}, {form: [(our text, where)]})"""
    bad, forms = {}, collections.defaultdict(list)
    for name, (code, offs, lines) in objs.items():
        sel = m5.selmap_text(code, work)
        bad[name] = []
        for k, off in enumerate(offs):
            end = offs[k + 1] if k + 1 < len(offs) else len(code)
            n, text = sel.get(off, (0, "?"))
            forms[form(text)].append((text, f"{name}+{off}"))
            want = m5.norm(lines[k]) if k < len(lines) else "?"
            got = m5.norm(text.replace("=mrf+", "="))
            ok = (got.startswith(want.split("do")[0] + "do") if ("do" in want and "until" in want)
                  else same(text.replace("=mrf+", "="), lines[k] if k < len(lines) else "?"))
            if n != end - off or not ok:
                bad[name].append(f"+{off} selmap {n}B '{text}' vs source '{lines[k].strip() if k < len(lines) else '?'}'")
    return bad, forms


def assemble_one(text: str, selas: str, work: pathlib.Path) -> str | None:
    """selas TEXT alone -> its bytes MSW first (None: selas refused it)"""
    src = work / "one.asm"
    obj = work / "one.doj"
    obj.unlink(missing_ok=True)
    src.write_text(f".SECTION/PM seg_pmco;\n      {text};\n")
    r = m1._wsl(f"{selas} -proc ADSP-21569 -o {m1._wsl_path(obj)} {m1._wsl_path(src)}\n", work)
    if r.returncode or not obj.exists():
        return None
    try:
        return sharc_object.code(obj.read_bytes(), "seg_pmco").hex()
    except Exception:
        return None


def against_adi(forms, stock, selas, work) -> dict:
    """(b): each of our forms -> stock's instances, assembled by selas, against stock's bytes"""
    by_form = collections.defaultdict(list)
    for sw, be, t in stock:
        by_form[form(t)].append((sw, be, t))
    res = {"matched": [], "variant": [], "mismatched": [], "no_stock": [], "not_assemblable": [], "shift_imm": []}
    for f, ours in sorted(forms.items()):
        inst = by_form.get(f, [])
        if not inst:
            res["no_stock"].append({"form": f, "ours": ours[0][0], "where": ours[0][1], "count": len(ours)})
            continue
        for sw, be, t in inst[:PER_FORM]:
            got = assemble_one(t, selas, work)
            row = {"form": f, "stock_sw": hex(sw), "text": t, "adi": be, "selas": got, "ours_count": len(ours)}
            if got is None:
                res["not_assemblable"].append(row)
            elif got == be:
                res["matched"].append(row)
            elif "lshift" in t or "ashift" in t:
                res["shift_imm"].append(row)
            else:
                # other bytes: the same instruction in another width or with a bit selmap does not show, or another
                # instruction? selas's bytes read back by selmap decide (as the decode step reads ours)
                back = m5.selmap_text(sharc_object.load_bytes(bytes.fromhex(got)), work).get(0, (0, "?"))[1]
                row["selas_reads"] = back
                res["variant" if same(back, t) else "mismatched"].append(row)
    return res


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stock", type=pathlib.Path)
    p.add_argument("--selas", default=m1.SELAS)
    p.add_argument("--json", type=pathlib.Path)
    a = p.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        objs = our_objects()
        bad, forms = read_back(objs, work)
        stock = stock_code(a.stock, work)
        res = against_adi(forms, stock, a.selas, work)
    n_bad = sum(len(v) for v in bad.values())
    print(f"(a) ours read back: {len(objs)} objects, {sum(len(o[1]) for o in objs.values())} instructions, "
          f"{n_bad} disagreements")
    for name, v in bad.items():
        for line in v[:12]:
            print(f"    {name} {line}")
        if len(v) > 12:
            print(f"    {name} ... {len(v) - 12} more")
    print(f"(b) {len(forms)} forms of ours; stock instructions {len(stock)}")
    for k in ("matched", "variant", "mismatched", "shift_imm", "not_assemblable", "no_stock"):
        print(f"    {k}: {len(res[k])}")
    for row in res["mismatched"]:
        print(f"    MISMATCH {row['form']!r}: stock {row['stock_sw']} '{row['text']}' ADI {row['adi']} selas {row['selas']}"
              f" = '{row.get('selas_reads')}' (ours x{row['ours_count']})")
    for row in res["no_stock"]:
        print(f"    no stock form: {row['form']!r} e.g. '{row['ours']}' at {row['where']} (x{row['count']})")
    if a.json:
        a.json.write_text(json.dumps({"read_back": bad, "against_adi": res}, indent=1))
    return 1 if n_bad or res["mismatched"] else 0


if __name__ == "__main__":
    sys.exit(main())
