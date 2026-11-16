"""2026-11-12: write src/dnfw/load/table.json, the kit load check's cost table, from the model's measurements.

    python3 scripts/gen_load_table.py [--check]

Measures every engine and its cost-changing choices (scripts/dsp_cost.py's cases) and what runs beside the voices
(scripts/dsp_cost_fx.py), then writes the table dnfw.load.c_header() turns into the ColdFire's arrays. --check
measures again and compares with the committed table: exit 1 when they differ (an engine changed: regenerate).
About two minutes. Needs MD_OS_BIN, MNM_OS, DT2_SECTION7 and DT2_SECTIONS as the build does.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import dsp_cost as DC  # noqa: E402
import dsp_cost_fx as FX  # noqa: E402
from dnfw import load as LD  # noqa: E402


def engines() -> dict[str, int]:
    """dsp_cost name -> the table's cost a voice"""
    out = {}
    for name, fam, setup in DC.cases():
        out[name] = LD.per_voice(DC.row(name, fam, DC.run_engine(setup)))
        print(f"  {name:16s} {out[name]:6,d}", flush=True)
    for name, ty in DC.sampler_cases():
        out[name] = LD.per_voice(DC.row(name, "SAMPLE", DC.run_sampler(ty), sampler=True))
        print(f"  {name:16s} {out[name]:6,d}", flush=True)
    return out


def fx() -> dict[str, dict]:
    out = {}
    for part in (FX.a2f, FX.pre_inserts, FX.post_inserts, FX.bus_inserts, FX.sends):
        out.update(part())
    return out


def table(eng: dict, fxr: dict) -> dict:
    import para_cost as PC                    # (scripts/, on sys.path above)
    from dnfw.engines.analog2.filters import design as A2D
    from dnfw.inserts import design as ID
    from dnfw.md import voice as MDV
    from dnfw.mnm import machines as MM
    from dnfw.engines.plaits import plaits as PLT
    from dnfw.sampler import machines as SM
    from dnfw.waverider import pages as PG

    def m(x: float) -> int:
        return round(x * (1 + LD.MARGIN))

    def choices(mach: str, ctl: str) -> tuple:
        return PG._choices(MM.MACHINES[MM.NAMES.index(mach)])[ctl]
    sophie = [eng[f"SOPHIE-{n}"] for n in choices("SOPHIE", "MODL")]
    a2flt = [eng[f"ANALOG2-{n}"] for n in choices("ANALOG2", "FLT2")]
    plaits = [eng[f"PLAITS-{n or PLT.MODELS[0]}"] for n in PLT.MODELS]      # the retired choice plays WS
    mono = [eng[n] for n in MM.MONO_ENGINES]
    var = {"SOPHIE": max(sophie), "ANALOG2": max(a2flt), "PLAITS": max(plaits)}
    mnm = [var.get(M.NAME, eng.get(M.NAME, 0)) if M.NAME != "REMOVED" else 0 for M in MM.CF_ALL]
    types = {t: m(LD.STOCK[t]) for t in LD.STOCK}
    types.update({ty: eng[n] for n, ty in SM.TYPE_OF.items() if n in eng})
    return {
        "method": "dnfw.load: per voice (max(steady, trig) + PER_VOICE) x (1 + MARGIN); fx x (1 + MARGIN)",
        "margin": LD.MARGIN, "per_voice": LD.PER_VOICE, "avail": LD.AVAIL, "fixed": LD.FIXED, "ours": LD.OURS,
        "md": [eng[M.NAME] for M in MDV.MM.MACHINES],
        "mnm": mnm, "mnm_names": [M.NAME for M in MM.CF_ALL],
        "plaits": plaits, "sophie": sophie, "a2flt": a2flt, "mono": mono,
        "type": {str(k): v for k, v in sorted(types.items())},
        "filter": {str(t): m(fxr[f"A2 {n}"]["per_voice"]) for t, n in A2D.TYPES.items()},
        "ins": {str(t): m(fxr[f"INS {ID.NAMES[t]}"]["per_voice"]) for t in range(len(ID.NAMES))
                if f"INS {ID.NAMES[t]}" in fxr},
        "bus": {str(t): m(fxr[f"BUS {ID.NAMES[t]}"]["per_instance"]) for t in range(len(ID.NAMES))
                if f"BUS {ID.NAMES[t]}" in fxr},
        "send": {k: m(fxr[f"SEND {k}"]["per_instance"]) for k in ("FDN8", "XDLY", "JUNO")},
        "engines": eng,
        "para": PC.table_costs(),             # 2026-11-15: ANALOG 2's PARA chords (a joining note, a dropped one)
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    DC._install()
    t = table(engines(), fx())
    text = json.dumps(t, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = LD.TABLE.exists() and LD.TABLE.read_text() == text
        print("PASS: the committed table is current" if same else "FAIL: the table is stale: regenerate")
        return 0 if same else 1
    LD.TABLE.write_text(text)
    LD.c_header(t)                            # (asserts every cost fits the ColdFire's u16)
    print(f"wrote {LD.TABLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
