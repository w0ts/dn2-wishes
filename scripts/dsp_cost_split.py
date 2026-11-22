"""docs/paraphonic-study.md (opt-md, 2026-11-14): each engine's OWN cost split by the innermost engine function on the Python
stack (dsp_cost.py's method and schedule; only the attribution is finer). Prints, per engine, steady-block buckets.

    python3 scripts/dsp_cost_split.py OUT.json "NAME,NAME,.."   (from the tree root; MD_OS_BIN / MNM_OS as dsp_cost.py)
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import dsp_cost as DC  # noqa: E402

SKIP = ("dnfw.perc.dsl",)


def finer(self):
    side, b = ORIG(self)
    if side != "engine":
        return side, b
    f = sys._getframe(3)
    while f is not None:
        mod = f.f_globals.get("__name__", "")
        if mod.startswith("dnfw.") and not mod.startswith(SKIP):
            return "engine", f"{b}:{mod[5:]}.{f.f_code.co_name}"
        f = f.f_back
    return side, b


ORIG = DC.Counter.tag
DC.Counter.tag = finer


def main() -> None:
    out_path, only = sys.argv[1], set(sys.argv[2].split(",")) if len(sys.argv) > 2 else set()
    DC._install()
    rows = {}
    for name, fam, setup in DC.cases():
        if only and name not in only:
            continue
        try:
            r = DC.run_engine(setup)
        except Exception as ex:
            rows[name] = {"error": f"{type(ex).__name__}: {ex}"}
            continue
        s = DC.split(r["steady"])
        rows[name] = {"family": fam, "host": round(DC.est(s["host"])), "engine": round(DC.est(s["engine"])),
                      "buckets": {k: round(v) for k, v in sorted(s["buckets"].items(), key=lambda kv: -kv[1])
                                  if k.startswith("engine:") and v >= 50}}
        print(name, rows[name]["host"], rows[name]["engine"], flush=True)
        for k, v in rows[name]["buckets"].items():
            print(f"    {k:60s} {v:7,d}")
    pathlib.Path(out_path).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
