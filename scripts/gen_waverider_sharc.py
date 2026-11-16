"""Package Waverider's SHARC objects for `dnfw.waverider.dsp` (Milestone 5).

    python scripts/gen_waverider_sharc.py [--assemble]

`dnfw.waverider.dsp` applies committed objects, never an assembler, so the mod runs
anywhere. This writes `src/dnfw/waverider/sharc_code.json` from:

- every object under `csrc/waverider/sharc/` the build ships (PERC, the filters, the
  machines, the stubs) -- each (re)written from its `.asm` with selas when `--assemble`;
- the entry `JUMP 0x180200;`, one selas-assembled instruction (`--assemble`), or
  the previous `sharc_code.json`'s copy.

Each object carries its source's sha256 (LF-normalised), and without `--assemble` a
source that no longer matches its committed object is refused, as the Milestone 3/4
gates do. selache (GPL-3.0) is a tool here; nothing of it is copied.
"""

from __future__ import annotations

import argparse
import importlib
import hashlib
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from dnfw.waverider import dsp  # noqa: E402

SHARC = ROOT / "csrc" / "waverider" / "sharc"
TOOLCHAIN = "selache selas -proc ADSP-21569 (js216/selache 2b26d3b, GPL-3.0, WSL)"
ENTRY_LINE = f"JUMP {dsp.COUNT_SW:#x};"           # the block counter, which goes on to PERC
IDLE_LINE = f"JUMP {dsp.IDLE_SW:#x};"
EMARK_LINE = f"JUMP {dsp.EMARK_SW:#x};"
LOOKUP_LINE = f"I5 = {dsp.LOOKUP16_DM:#x};"
PVMIX_LINE = f"JUMP {dsp.PVMIX_SW:#x};"           # v0.25: the driver's call of 0x1c9d3f, via the preview        # the machine lookup's base (v0.13)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def committed(name: str) -> dict:
    src, obj = SHARC / f"{name}.asm", SHARC / f"{name}.json"
    spec = json.loads(obj.read_text(encoding="utf-8"))
    if spec["source_sha256"] != sha(src):
        raise SystemExit(f"{obj.name} is stale for {src.name}: rerun with --assemble")
    return spec


def assemble(name: str, load_sw: int, work: pathlib.Path) -> dict:
    import sharc_waverider_m3 as m3  # noqa: PLC0415  (needs WSL only when assembling)
    src = SHARC / f"{name}.asm"
    be, offsets = m3._selas(src, work)
    spec = {"source": src.relative_to(ROOT).as_posix(), "source_sha256": sha(src),
            "toolchain": TOOLCHAIN, "section": "seg_pmco", "load_sw": hex(load_sw),
            "object_parcels_be": be.hex(), "instruction_offsets": offsets}
    (SHARC / f"{name}.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8",
                                        newline="\n")
    return spec


def one_jump(line: str, at_sw: int, work: pathlib.Path) -> dict:
    import sharc_waverider_m3 as m3  # noqa: PLC0415
    be, _ = m3._selas_line(line, work)
    return {"source": line, "toolchain": TOOLCHAIN, "at_sw": hex(at_sw), "object_parcels_be": be.hex()}


def _a2f_built() -> bool:
    """the A2 filter machines' pass is in this build (dnfw.a2f.design, the builder's choice)"""
    return bool(importlib.import_module("dnfw.a2f.design").BUILT_MODELS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--assemble", action="store_true")
    a = ap.parse_args(argv)
    old = json.loads(dsp.CODE.read_text(encoding="utf-8")) if dsp.CODE.exists() else {}
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        if a.assemble:
            perc = assemble("perc", dsp.PERC_SW, work)
            smp = assemble("smp", dsp.SMP_SW, work)
            idle = assemble("idle_load", dsp.IDLE_SW, work)
            count = assemble("block_count", dsp.COUNT_SW, work)
            emark = assemble("entry_mark", dsp.EMARK_SW, work)
            ping = assemble("ping", dsp.PING_SW, work)
            trackbuf = assemble("trackbuf", dsp.TRACKBUF_SW, work)
            pvmix = assemble("pvmix", dsp.PVMIX_SW, work)
            fdn8 = assemble("fdn8", dsp.FDN8_SW, work)
            xdly = assemble("xdly", dsp.XDLY_SW, work)
            inserts = assemble("inserts", dsp.INS_SW, work)
            inspost = assemble("inspost", dsp.POST_SW, work)
            insbus = assemble("insbus", dsp.INSBUS_SW, work)
            a2f = assemble("a2f", dsp.A2F_SW, work) if _a2f_built() else None
            pjump = one_jump(PVMIX_LINE, dsp.PVMIX_SITE_SW, work)
            ejump = one_jump(EMARK_LINE, dsp.CALL_SITE_SW, work)
            lptr = one_jump(LOOKUP_LINE, dsp.LOOKUP_SITE_SW, work)
            jump = one_jump(ENTRY_LINE, dsp.ENTRY_SW, work)
            ijump = one_jump(IDLE_LINE, dsp.IDLE_SITE_SW, work)
        else:
            perc = committed("perc")
            smp = committed("smp")
            idle = committed("idle_load")
            count = committed("block_count")
            emark = committed("entry_mark")
            ping = committed("ping")
            trackbuf = committed("trackbuf")
            pvmix = committed("pvmix")
            fdn8 = committed("fdn8")
            xdly = committed("xdly")
            inserts = committed("inserts")
            inspost = committed("inspost")
            insbus = committed("insbus")
            a2f = committed("a2f") if _a2f_built() else None
            pjump = old["pvmix_jump"]
            ejump = old["emark_jump"]
            lptr = old["lookup_ptr"]
            if "entry_jump" not in old or "idle_jump" not in old:
                raise SystemExit("no entry or idle JUMP committed yet: run with --assemble")
            jump, ijump = old["entry_jump"], old["idle_jump"]
    spec = {"note": "generated by scripts/gen_waverider_sharc.py; do not edit",
            "perc": {k: v for k, v in perc.items() if k != "instruction_offsets"},
            "smp": {k: v for k, v in smp.items() if k != "instruction_offsets"},
            "entry_jump": jump,
            "idle_load": {k: v for k, v in idle.items() if k != "instruction_offsets"},
            "idle_jump": ijump,
            "block_count": {k: v for k, v in count.items() if k != "instruction_offsets"},
            "entry_mark": {k: v for k, v in emark.items() if k != "instruction_offsets"},
            "emark_jump": ejump,
            "lookup_ptr": lptr,
            "ping": {k: v for k, v in ping.items() if k != "instruction_offsets"},
            "trackbuf": {k: v for k, v in trackbuf.items() if k != "instruction_offsets"},
            "pvmix": {k: v for k, v in pvmix.items() if k != "instruction_offsets"},
            "pvmix_jump": pjump,
            "fdn8": {k: v for k, v in fdn8.items() if k != "instruction_offsets"},
            "xdly": {k: v for k, v in xdly.items() if k != "instruction_offsets"},
            "inserts": {k: v for k, v in inserts.items() if k != "instruction_offsets"},
            "inspost": {k: v for k, v in inspost.items() if k != "instruction_offsets"},
            "insbus": {k: v for k, v in insbus.items() if k != "instruction_offsets"}}
    if a2f is not None:                                  # 2026-11-09: the A2 filter machines' pass (dnfw.a2f)
        spec["a2f"] = {k: v for k, v in a2f.items() if k != "instruction_offsets"}
    dsp.CODE.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {dsp.CODE.relative_to(ROOT)}: perc {len(perc['object_parcels_be']) // 2} B, ping {len(ping['object_parcels_be']) // 2} B, entry {len(jump['object_parcels_be']) // 2} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
