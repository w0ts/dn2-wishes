"""Every multifunction word in stock's DSP code, read by three decoders and re-encoded by selas (2026-11-21).

    python scripts/mf_corpus.py STOCK.syx --digikit DIGIKIT/tools [--skill SKILL_SCRIPTS] [--selas PATH]
                                [--synthetic N] [--json OUT]

(On the farm: DNFW_SELMAP / --selas the patched selache's, tools/selache/apply.sh.)

The corpus: stock's code ranges (selas_form_check.CODE_RANGES) walked by selmap's lengths, each instruction decoded
by digikit (`sharc_core.sequencer.decode_at`); kept: those whose 23-bit compute field has bit 22 set (multiply + ALU,
multiply + dual add/subtract, MR moves) and whose length digikit and selmap agree on. A linear walk also reads
data as code, so a word is "code" only by its looks; the tally keeps the categories stock's code really uses apart
from the ones that occur a few times (`rare`), which are mostly data.

For each word:
  ours     dnfw.perc.mfcodec.decode(field): Table 12-12's reading (third decoder)
  selmap   selache's text of the whole instruction: its compute part must read as `ours` (normalised)
  visa     complex-ping's visa.compute(field), when --skill is given: the same
  selas    (1) selmap's full text assembled: stock's bytes exactly, or bytes selmap reads the same (variant);
           (2) `ours` alone assembled: its compute field (care bits, mfcodec.care) equals stock's
--synthetic N: N random fields per category (every op6 of every kind), assembled from `ours`, read back by selmap
and by digikit (its compute field) and by visa.
Exit 1 when a category stock uses (or a synthetic one selas accepts) disagrees anywhere."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.cli.files import read_image            # noqa: E402
from dnfw.firmware.load import load              # noqa: E402
from dnfw.image import bootstream, sharc_object  # noqa: E402
from dnfw.perc import mfcodec as C               # noqa: E402
import selas_form_check as F                     # noqa: E402
import sharc_waverider_m5 as m5                  # noqa: E402
import sharc_waverider_render as m1              # noqa: E402

RARE = 3                                          # a category seen this few times is listed as rare (likely data)


def dk_compute(insn) -> int | None:
    f = insn.fields or {}
    if "compute[22:16]" in f:
        return f["compute[22:16]"] << 16 | f["compute[15:0]"]
    return f.get("compute")


def n(t: str) -> str:
    """one normal form for compute texts of every decoder (the fixed multiply's (SSF)/(SSFR) is text only:
    the category fixes the rounding, no bit carries it)"""
    return m5.norm(t).replace("(ssfr)", "").replace("(ssf)", "")


# lines selas must refuse (an operand outside its group, a fixed form of a float-only ALU half, a dual whose
# subtract reads other operands): each was, or could be, assembled as another instruction without a word
MUST_REFUSE = (
    "F12 = F4 * F7, F8 = F8 + F12", "F12 = F0 * F3, F8 = F8 + F12", "F12 = F0 * F7, F8 = F12 + F12",
    "F12 = F0 * F7, F8 = F8 + F9", "F12 = F0 * F7, F8 = MIN(F8, F9)", "R12 = R0 * R7 (SSF), R8 = MAX(R8, R12)",
    "F12 = F0 * F7, F8 = FLOAT R4 BY R12", "F12 = F0 * F7, R8 = FIX F8 BY R1", "F12 = F0 * F7, F8 = ABS F1",
    "R12 = R0 * R7 (SSFR), R8 = ABS R8", "F12 = F0 * F7, F8 = F8 + F12, F9 = F8 - F2",
    "F12 = F0 * F7, F8 = F8 + F1, F9 = F8 - F1", "F12 = F0 * F7, F8 = F8 + F12, F9 = F9 - F12",
    "F12=F0*F7,F8=F8+F9", "F12 = F0 * F7, F8 = ABS F12",
)


def compute_part(sel_text: str, ours: str) -> bool:
    """does selmap's whole-instruction text contain OURS as its compute (every part, in order)?"""
    s = n(sel_text)
    return all(n(p) in s for p in ours.split(", "))


def stock_words(stock: pathlib.Path, dk, work: pathlib.Path) -> list[dict]:
    stream = load(read_image(stock)).container.find(7).unpack()
    out = []
    for b in bootstream.walk(stream).blocks:
        if not b.has_payload or b.target < F.SW_ALIAS or (b.target - F.SW_ALIAS) % 2:
            continue
        sw0 = (b.target - F.SW_ALIAS) // 2
        if not any(lo <= sw0 < hi for lo, hi in F.CODE_RANGES):
            continue
        payload = stream[b.offset + bootstream.HEADER:b.offset + bootstream.HEADER + b.count]
        padded = payload + b"\0" * 16
        for off, (size, text) in sorted(m5.selmap_text(payload, work).items()):
            insn = dk.decode_at(padded, 0, off // 2)
            c = dk_compute(insn)
            if c is None or not c >> 22 & 1:
                continue
            out.append({"sw": hex(sw0 + off // 2), "type": insn.type_name, "len": size, "dk_len": insn.length_bytes,
                        "adi": F.be_of(payload[off:off + size]), "field": c, "selmap": text})
    return out


def assemble_many(texts: list[str], selas: str, work: pathlib.Path) -> list[str | None]:
    """each text alone -> selas's bytes (hex, MSW first) or None; one selas run, per-line again on an error"""
    if not texts:
        return []
    src, obj = work / "many.asm", work / "many.doj"
    body = [".SECTION/PM seg_pmco;"]
    for k, t in enumerate(texts):
        body += [f".GLOBAL y_{k};", f"y_{k}:", f"      {t};"]
    body += [".GLOBAL y_end;", "y_end:", "      NOP;"]
    src.write_text("\n".join(body) + "\n")
    obj.unlink(missing_ok=True)
    r = m1._wsl(f"{selas} -proc ADSP-21569 -o {m1._wsl_path(obj)} {m1._wsl_path(src)}\n", work)
    if r.returncode or not obj.exists():
        if len(texts) == 1:
            return [None]
        h = len(texts) // 2
        return assemble_many(texts[:h], selas, work) + assemble_many(texts[h:], selas, work)
    data = obj.read_bytes()
    syms = sharc_object.symbols(data)
    try:
        code = sharc_object.code(data, "seg_pmco")
    except sharc_object.ObjectError:              # (a branch to an address selas relocates: not placeable alone)
        if len(texts) == 1:
            return [None]
        h = len(texts) // 2
        return assemble_many(texts[:h], selas, work) + assemble_many(texts[h:], selas, work)
    offs = [2 * syms[f"y_{k}"] for k in range(len(texts))] + [2 * syms["y_end"]]
    return [code[offs[k]:offs[k + 1]].hex() for k in range(len(texts))]


def selmap_of(hexes: list[str], work: pathlib.Path) -> list[str]:
    """selmap's text of each instruction (bytes MSW first, as selas writes them)"""
    out = []
    for h in hexes:
        if h is None:
            out.append(None)
            continue
        out.append(m5.selmap_text(sharc_object.load_bytes(bytes.fromhex(h)), work).get(0, (0, "?"))[1])
    return out


def field_of(hexstr: str) -> int:
    return int(hexstr[-8:], 16) & 0x7FFFFF


def check_stock(words, selas, visa, work) -> dict:
    full = assemble_many([w["selmap"] for w in words], selas, work)
    ours_t = [C.decode(w["field"]) for w in words]
    alone = assemble_many([t if t and C.kind(w["field"]) in ("fixed", "float", "dual-fixed", "dual-float") else "NOP"
                           for w, t in zip(words, ours_t)], selas, work)
    back = selmap_of([h if h != w["adi"] else None for h, w in zip(full, words)], work)
    for w, t, h, a, b in zip(words, ours_t, full, alone, back):
        c = w["field"]
        w["kind"], w["op6"], w["ours"] = C.kind(c), f"{c >> 16 & 0x3F:06b}", t
        w["len_agree"] = w["dk_len"] == w["len"]
        w["selmap_reads_ours"] = t is not None and compute_part(w["selmap"], t)
        if visa is not None:
            w["visa"] = visa.compute(c)
            w["visa_agrees"] = t is not None and n(w["visa"]) == n(t)
        w["selas_full"] = "same" if h == w["adi"] else None if h is None else (
            "variant" if b is not None and F.same(b, w["selmap"]) else "MISMATCH")
        w["selas_full_bytes"] = h
        if w["kind"] in ("fixed", "float", "dual-fixed", "dual-float"):
            w["selas_alone"] = None if a is None else ("same" if field_of(a) & C.care(c) == c & C.care(c)
                                                       else f"MISMATCH {field_of(a):#08x}")
    return tally(words, visa is not None)


def tally(words, with_visa) -> dict:
    by = collections.defaultdict(list)
    for w in words:
        if w["len_agree"]:
            by[(w["kind"], w["op6"], w["type"])].append(w)
    rows = []
    for (k, op6, typ), ws in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0][1])):
        r = {"kind": k, "op6": op6, "type": typ, "count": len(ws), "rare": len(ws) <= RARE,
             "example": f"{ws[0]['sw']} {ws[0]['selmap']}",
             "selmap_reads_ours": sum(w["selmap_reads_ours"] for w in ws),
             "selas_full": dict(collections.Counter(str(w["selas_full"]) for w in ws)),
             "selas_alone": dict(collections.Counter(str(w.get("selas_alone")) for w in ws))}
        if with_visa:
            r["visa_agrees"] = sum(w["visa_agrees"] for w in ws)
        rows.append(r)
    return {"rows": rows, "words": len(words), "len_disagree": sum(not w["len_agree"] for w in words)}


def synthetic(per: int, selas, dk, visa, work) -> list[dict]:
    rnd = random.Random(2026_11_21)
    fields = []
    for op6 in range(64):
        c0 = (1 << 22) | (op6 << 16)
        if C.kind(c0) not in ("fixed", "float", "dual-fixed", "dual-float"):
            continue
        for _ in range(per):
            c = c0 | rnd.getrandbits(16)
            fields.append(c & C.care(c))
    texts = [C.decode(c) for c in fields]
    got = assemble_many(texts, selas, work)
    back = selmap_of(got, work)
    rows = []
    for c, t, h, b in zip(fields, texts, got, back):
        r = {"field": hex(c), "kind": C.kind(c), "op6": f"{c >> 16 & 0x3F:06b}", "ours": t, "selas": h}
        if h is not None:
            f = field_of(h)
            r["selas_field_ok"] = f & C.care(c) == c
            r["selmap"] = b
            r["selmap_reads_ours"] = b is not None and compute_part(b, t)
            data = sharc_object.load_bytes(bytes.fromhex(h)) + b"\0" * 16
            insn = dk.decode_at(data, 0, 0)
            r["digikit_field_ok"] = dk_compute(insn) is not None and dk_compute(insn) & C.care(c) == c
            r["digikit_type"] = insn.type_name
        if visa is not None:
            r["visa_agrees"] = n(visa.compute(c)) == n(t)
        rows.append(r)
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stock", type=pathlib.Path)
    p.add_argument("--digikit", required=True, type=pathlib.Path, help="digikit's tools directory")
    p.add_argument("--skill", type=pathlib.Path, help="complex-ping's skill scripts directory (visa.py)")
    p.add_argument("--selas", default=m1.SELAS)
    p.add_argument("--synthetic", type=int, default=0)
    p.add_argument("--json", type=pathlib.Path)
    a = p.parse_args(argv)
    sys.path.insert(0, str(a.digikit))
    from sharc_core import sequencer as dk           # noqa: PLC0415
    visa = None
    if a.skill:
        sys.path.insert(0, str(a.skill))
        import visa                                   # noqa: PLC0415
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        words = stock_words(a.stock, dk, work)
        res = check_stock(words, a.selas, visa, work)
        syn = synthetic(a.synthetic, a.selas, dk, visa, work) if a.synthetic else []
        accepted = [t for t, h in zip(MUST_REFUSE, assemble_many(list(MUST_REFUSE), a.selas, work)) if h]
    bad = report(res, syn, visa is not None)
    print(f"must-refuse lines: {len(MUST_REFUSE) - len(accepted)} of {len(MUST_REFUSE)} refused")
    for t in accepted:
        print(f"  ACCEPTED (an illegal line assembled): {t}")
    bad += len(accepted)
    if a.json:
        a.json.write_text(json.dumps({"stock": res, "words": words, "synthetic": syn}, indent=1, default=str))
    return 1 if bad else 0


MF_KINDS = ("fixed", "float", "dual-fixed", "dual-float")
MF_TYPES = ("1a", "2a", "3a", "4a")     # the 48-bit compute types: compute alone, with one or two moves


def row_state(r, with_visa) -> str:
    """WRONG: the multifunction field itself (selas alone) differs, or the decoders read a 48-bit compute
    type differently, or selas wrote other bits for a compute-alone / compute + DM move instruction;
    other: selas writes another instruction type's other fields differently (not the multifunction);
    refused / ok / n/a (not a multifunction category, or a field digikit places where selmap reads another form)"""
    if r["kind"] not in MF_KINDS or r["type"] not in MF_TYPES + ("5a_move", "5a_swap", "7a", "9a_abs",
                                                                 "9a_rel", "10a_rel", "11a"):
        return "n/a"
    if any(k.startswith("MISMATCH") for k in r["selas_alone"]):
        return "WRONG"
    decoders = r["selmap_reads_ours"] == r["count"] and (not with_visa or r["visa_agrees"] == r["count"])
    if r["type"] in MF_TYPES and (not decoders or "MISMATCH" in r["selas_full"]):
        return "WRONG"
    if "MISMATCH" in r["selas_full"]:
        return "other"
    return "refused" if set(r["selas_full"]) == {"None"} else "ok"


def report(res, syn, with_visa) -> int:
    print(f"stock: {res['words']} words with compute bit 22 ({res['len_disagree']} where digikit and selmap "
          f"disagree on the length: left out)")
    bad = 0
    for r in res["rows"]:
        st = row_state(r, with_visa)
        bad += st == "WRONG"
        print(f"  {st:9s} {r['kind'] or 'reserved':10s} {r['op6']} {r['type']:8s} x{r['count']:<5d}"
              f"{' rare' if r['rare'] else ''} selmap {r['selmap_reads_ours']}/{r['count']}"
              f"{' visa %d' % r['visa_agrees'] if with_visa else ''} selas {r['selas_full']} alone {r['selas_alone']}"
              f"  e.g. {r['example']}")
    if syn:
        cats = collections.defaultdict(list)
        for r in syn:
            cats[(r["kind"], r["op6"])].append(r)
        print(f"synthetic: {len(syn)} fields")
        for (k, op6), rs in sorted(cats.items(), key=lambda kv: kv[0][1]):
            acc = [r for r in rs if r["selas"] is not None]
            okn = sum(r["selas_field_ok"] and r["selmap_reads_ours"] and r["digikit_field_ok"] for r in acc)
            vis = sum(r.get("visa_agrees", True) for r in rs)
            state = "refused" if not acc else ("ok" if okn == len(acc) == len(rs) and vis == len(rs) else "BAD")
            bad += state == "BAD"
            print(f"  {state:7s} {k:10s} {op6} selas accepted {len(acc)}/{len(rs)}, all three agree {okn}"
                  f"{', visa %d' % vis if with_visa else ''}  e.g. {rs[0]['ours']}"
                  + (f" -> selmap '{acc[0]['selmap']}'" if acc and state == "BAD" else ""))
    return bad


if __name__ == "__main__":
    sys.exit(main())
