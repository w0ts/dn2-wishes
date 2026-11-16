"""Cross-check dnfw.perc.mf against the stock DSP code (perf, 2026-11-11).

    python scripts/mf_firmware_check.py SECTION7.bin --digikit DIGIKIT_CHECKOUT --selmap PATH

Walks the stock section 7 with selmap's instruction offsets, decodes each with digikit, and for every instruction
whose selmap text is a float dual add / subtract (`fM=fX*fY , fA=fB+fC , fS=fB-fC`) checks that mf.field_dual builds
exactly digikit's compute field from the text's registers; and lists the plain `Fm = Fx * Fy, Fa = Fb + Fc`
(category 011000) instances whose ALU reads the multiplier's destination (the dot-product idiom). Prints the counts;
exit 1 on any mismatch. A linear sweep also decodes data, so the numbers are of 'looks like', not of 'executes'."""
import argparse
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from dnfw.perc import mf  # noqa: E402

DUAL = re.compile(r"f(\d+)=f(\d+)\*f(\d+)\s*,\s*f(\d+)=f(\d+)\+f(\d+)\s*,\s*f(\d+)=f(\d+)-f(\d+)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("section7")
    ap.add_argument("--digikit", required=True)
    ap.add_argument("--selmap", default="/root/selmap-target/release/selmap")
    a = ap.parse_args()
    sys.path.insert(0, str(pathlib.Path(a.digikit) / "tools"))
    import sharc_trace as st  # noqa: PLC0415
    data = pathlib.Path(a.section7).read_bytes()
    out = subprocess.run([a.selmap], input=data, capture_output=True).stdout.decode()
    padded = data + b"\0" * 16
    dual = ok = idiom = 0
    bad = []
    for ln in out.splitlines():
        p = ln.split("\t", 2)
        if len(p) != 3:
            continue
        off, text = int(p[0]), p[2].replace(" ", "")
        i = st.decode_at(padded, 0, off // 2)
        f = i.fields or {}
        c = (f["compute[22:16]"] << 16 | f["compute[15:0]"]) if "compute[22:16]" in f else f.get("compute")
        if c is None:
            continue
        m = DUAL.search(text)
        if m and 0 <= int(m.group(2)) < 4 and 4 <= int(m.group(3)) < 8 and c >> 22 & 1:
            g = [int(x) for x in m.groups()]
            if g[4] == g[7] and g[5] == g[8] and 8 <= g[4] < 12 and 12 <= g[5] < 16:
                dual += 1
                want = mf.field_dual(g[0], g[1], g[2], g[3], g[6], g[4], g[5])
                if want == c:
                    ok += 1
                else:
                    bad.append((off, hex(c), hex(want), text))
        if c >> 16 == 0x58:
            fm, xm, ym, _, fa, xa, ya = mf.unfield(c)
            if fm in (xa, ya):
                idiom += 1
    print(f"dual add/subtract instances {dual}, field_dual equals digikit's compute field in {ok}; "
          f"category 011000 whose ALU reads the multiplier's result: {idiom}")
    for b in bad[:10]:
        print("MISMATCH", b)
    return 1 if bad or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
