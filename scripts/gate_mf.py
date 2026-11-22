"""Every multifunction word in a build's DSP code is the instruction its generator meant (2026-11-21).

    python scripts/gate_mf.py BUILD.syx DIGIKIT_CHECKOUT

For every object of ours the build loads (gate_hwrules.ranges: PERC and its spans, the sample machines, the
inserts, FDN8, ...), read from the BUILD's own section 7 at its load address, instruction by instruction (the
object's committed offsets):

  - a source line with two compute operations (dnfw.perc.mf.classify) must be a proven form (mf.check_line: the
    categories digikit's emulator runs, one DM move through I0..I3 at most), 48 bits in both decoders, digikit's
    compute field must be the one dnfw.perc.mfcodec computes from the text (the bits the operation reads), and
    selmap's text of the build's bytes must read that compute;
  - any word digikit decodes with a multifunction compute field (bit 22) must come from such a line: selas never
    gets to turn another line into a multifunction one.
  - the object's bytes in the build must be its committed object's (else the offsets say nothing).

PASS (exit 0) with the counts, or FAIL (exit 1) with each disagreement. DNFW_SELMAP names selmap (selache's
decoder, built from tools/selache's patches)."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.image import sharc_object              # noqa: E402
from dnfw.perc import mf, mfcodec                # noqa: E402

SHARC = ROOT / "csrc" / "waverider" / "sharc"


def dk_compute(insn) -> int | None:
    f = insn.fields or {}
    if "compute[22:16]" in f:
        return f["compute[22:16]"] << 16 | f["compute[15:0]"]
    return f.get("compute")


def sel_reads(text: str, c: int) -> bool:
    """does selmap's TEXT of the instruction carry the compute mfcodec reads from C (every part, in order)?"""
    import sharc_waverider_m5 as m5                # noqa: PLC0415
    s = m5.norm(text).replace("(ssfr)", "").replace("(ssf)", "")
    return all(m5.norm(p).replace("(ssfr)", "").replace("(ssf)", "") in s for p in mfcodec.decode(c).split(", "))


def check_object(name, load_sw, memory, dk, work) -> tuple[int, list[str]]:
    import sharc_waverider_m5 as m5                # noqa: PLC0415
    spec = json.loads((SHARC / f"{name}.json").read_text(encoding="utf-8"))
    obj = sharc_object.load_bytes(bytes.fromhex(spec["object_parcels_be"]))
    offs = spec["instruction_offsets"]
    lines = [ln for ln in (SHARC / f"{name}.asm").read_text(encoding="utf-8").splitlines()
             if (t := ln.split("//", 1)[0].strip()) and not t.startswith(".") and not t.endswith(":")]
    if name == "pvmix":                            # (its last three instructions are stock's call, placed by dsp)
        from dnfw.waverider import dsp             # noqa: PLC0415
        obj = dsp.pvmix_object()
    built = memory.read_sw(load_sw, len(obj))
    bad, n = [], 0
    if built != obj:
        return 0, [f"{name}: the build's bytes at {load_sw:#x} are not the committed object's"]
    sel = m5.selmap_text(obj, work)
    for k, off in enumerate(offs):
        end = offs[k + 1] if k + 1 < len(offs) else len(obj)
        line = lines[k] if k < len(lines) else "?"
        insn = dk.st.decode_at(memory, None, load_sw + off // 2)
        c = dk_compute(insn)
        is_mf_word = c is not None and c >> 22 & 1
        where = f"{name}+{off} (sw {load_sw + off // 2:#x}) '{line.strip()}'"
        if mf.classify(line) is None:
            if is_mf_word:
                bad.append(f"{where}: digikit reads a multifunction field {c:#08x} ({mfcodec.decode(c)}) "
                           "in a line that has none")
            continue
        n += 1
        try:
            want = mf.check_line(line)
        except AssertionError as e:
            bad.append(f"{where}: {e}")
            continue
        size, text = sel.get(off, (0, "?"))
        care = mfcodec.care(want)
        if not (end - off == 6 and insn.length_bytes == 6 and size == 6):
            bad.append(f"{where}: lengths object {end - off}, digikit {insn.length_bytes}, selmap {size} (want 6)")
        elif c is None or c & care != want & care:
            bad.append(f"{where}: digikit's compute {c if c is None else hex(c)}, the text's {want:#08x}")
        elif not sel_reads(text, want):
            bad.append(f"{where}: selmap reads '{text}', not '{mfcodec.decode(want)}'")
    return n, bad


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    build, digikit = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    import gate_hwrules as H                       # noqa: PLC0415
    import sharc_waverider_render as m1            # noqa: PLC0415
    dk = m1.Digikit(digikit)
    memory = dk.ldr.LoadedMemory.from_stream(H.section7(build))
    total, bad, objs = 0, [], 0
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        for lo, _hi, what in H.ranges():
            if not what.endswith(".asm"):
                continue
            n, b = check_object(what[:-4], lo, memory, dk, work)
            total, objs = total + n, objs + 1
            bad += b
    if bad:
        print(f"FAIL: {len(bad)} multifunction disagreement(s) in {objs} objects:")
        for line in bad[:60]:
            print("  " + line)
        return 1
    print(f"PASS: {objs} objects, {total} multifunction instructions: each a proven form, 48 bits in both "
          f"decoders, digikit's field and selmap's text the generator's; no other word carries one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
