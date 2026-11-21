"""The Wishes builder page's bundle (tools/web/builder.html; scripts/web_bundle.py --wishes).

    python scripts/web_bundle.py --wishes BUILD.syx RELEASE OUTDIR [--uncleared-test | --local-test SHA256]
    python scripts/web_bundle.py --check-site OUTDIR

One build per release, the whole mod (there is nothing to choose: the User, 2026-11-19, "everything
fits"). BUILD.syx is a cleared OS 1.12 build of this tree (its BUILD.syx.gate.json beside it, CLEARED,
the same sha256). This builds it again the browser's way (tools/patcher/dn2patch.build with
noboot=True, the DN2's own section 7) from Elektron's files, noting every dnfw file it reads; zips
those, dn2patch.py and noboot.py; rebuilds from the zip ALONE in a clean interpreter; and only if
that gives BUILD.syx's sha256 writes OUTDIR/vRELEASE/code-<zip sha>.zip, the gate record (only its
verdicts: no paths) and the release's row in OUTDIR/wishes.json (newest first):

    {"release", "mod_version", "os": "1.12", "file", "sha256", "gate", "zip", "zip_sha256",
     "inputs", "dn2_sha256", "budgets"}

--uncleared-test builds and checks the same pipeline for a build with no clearing record. Its
row has "gate": null: the page then offers no Save, and --check-site (the Pages workflow)
refuses the folder. It is for testing the route, never for publishing.

--local-test SHA256 is --uncleared-test for ONE named TEST build that passed the brick-risk steps (no
machine-readable record exists for it: the coordinator passes the sha256 from the build's .txt, and it is
printed). The build must have exactly that sha256. The row gets "local_test": {"brick_risk_sha256": ...};
the page honours it only on localhost, in a scripts/make_site.sh --preview site, with ?localtest=1, and
make_site.sh without --preview and --check-site both refuse such a row. Never for publishing.

Elektron's files are read from: DN2_OS112 (the Digitone II OS 1.12 .syx or Elektron's .zip,
default ../Digitone_II_OS1.12.syx) and DN2_STOCK_DIR (searched for the Digitakt II OS 1.17 or
1.16, Machinedrum UW OS 1.63 and Monomachine OS 1.32B .syx files, default ../stock).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
STAMP = (2026, 1, 1, 0, 0, 0)
# what the build reads from the environment: never inherited by the clean rebuild
BUILD_ENV = ("DT2_SECTIONS", "DT2_SECTION7", "MD_OS_BIN", "MNM_OS", "DN2MK2_PARTS")
STOCK_NAMES = {"dt2": ("Digitakt_II_OS1.17.syx", "Digitakt_II_OS1.16.syx"),
               "md": ("Elektron_SPS1-1UW_OS1.63.syx",), "mnm": ("Elektron_SFX6-60_OS1.32B.syx",)}


def cleared(record: dict | None, sha: str) -> bool:
    sys.path.insert(0, str(ROOT / "scripts"))
    from web_bundle import cleared as rule
    return rule(record, sha)


def public_record(record: dict) -> dict:
    """What the site publishes of a gate record: the file, its sha256, the date and each gate's
    verdict word. Its logs and interpreters are local paths: never published."""
    known = record.get("known_issues") or {}
    return {"build": record.get("build"), "sha256": record["sha256"], "stock": record.get("stock"),
            "date": record.get("date"),
            "gates": {k: str(v).split(":")[0].split(" ")[0] for k, v in record["gates"].items()},
            "known_issues": sorted(known)}        # the names only (their details hold local paths)


def stock_paths() -> dict[str, pathlib.Path]:
    dn2 = pathlib.Path(os.environ.get("DN2_OS112", ROOT.parent / "Digitone_II_OS1.12.syx"))
    stock = pathlib.Path(os.environ.get("DN2_STOCK_DIR", ROOT.parent / "stock"))
    out = {"dn2": dn2}
    for k, names in STOCK_NAMES.items():
        found = [p for n in names for p in sorted(stock.rglob(n))]
        if found:
            out[k] = found[0]
    return out


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(files):
            z.writestr(zipfile.ZipInfo(name, STAMP), files[name], compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def traced_build(paths: dict[str, pathlib.Path], work: pathlib.Path) -> tuple[str, dict[str, bytes], bool]:
    """The browser's route here, in this process -> (sha256, the zip's files, reads the Monomachine OS?)"""
    for k in BUILD_ENV:
        os.environ.pop(k, None)
    touched: set[str] = set()

    def hook(ev: str, args: tuple) -> None:
        if ev == "open" and isinstance(args[0], str):
            touched.add(os.path.abspath(args[0]))
    sys.path[:0] = [str(SRC), str(ROOT / "tools" / "patcher"), str(ROOT / "scripts")]
    sys.addaudithook(hook)
    import dn2patch
    dn2patch.WORK = work
    sha = dn2patch.build(str(paths["dn2"]), str(paths["dt2"]), str(paths["md"]), str(work / "out.syx"),
                         mnm=str(paths["mnm"]) if "mnm" in paths else None, noboot=True)
    from dnfw.mnm import tables
    files = {pathlib.Path(m.__file__).resolve() for k, m in list(sys.modules.items())
             if k.split(".")[0] == "dnfw" and getattr(m, "__file__", None)}
    files |= {pathlib.Path(p) for p in touched if p.startswith(str(SRC / "dnfw")) and not p.endswith(".pyc")}
    out = {str(f.relative_to(SRC)): f.read_bytes() for f in files}
    out["dn2patch.py"] = (ROOT / "tools" / "patcher" / "dn2patch.py").read_bytes()
    out["noboot.py"] = (ROOT / "scripts" / "noboot.py").read_bytes()
    return sha, out, tables.mnm_os_on()


ISOLATED = """
import sys, pathlib
run = sys.argv[1]
sys.path.insert(0, run + '/code')
import dn2patch
dn2patch.WORK = pathlib.Path(run + '/work')
mnm = sys.argv[5] if len(sys.argv) > 5 else None
print('SHA=' + dn2patch.build(sys.argv[2], sys.argv[3], sys.argv[4], run + '/out.syx', mnm=mnm, noboot=True))
"""


def isolated_rebuild(zbytes: bytes, mod_version: str, paths: dict[str, pathlib.Path], inputs: list[str]) -> str:
    """the zip's build, run as builder-worker.js runs it (the zip in RUN/code, VERSION in RUN, nothing
    from this repository, no build variable inherited) -> its sha256, or the error's last line"""
    env = {k: v for k, v in os.environ.items() if k not in BUILD_ENV}
    with tempfile.TemporaryDirectory() as td:
        run = pathlib.Path(td)
        with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
            z.extractall(run / "code")
        (run / "VERSION").write_text(mod_version + "\n")
        args = [str(paths[k]) for k in inputs]
        r = subprocess.run([sys.executable, "-I", "-c", ISOLATED, str(run), *args], cwd=td, env=env,
                           capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("SHA="):
            return line[4:]
    text = (r.stdout + r.stderr).strip()
    return text.splitlines()[-1] if text else "no output"


def budgets(built: bytes) -> dict:
    """the file's measured room: the DSP upload (section 7 unpacked) and the USB image"""
    sys.path.insert(0, str(SRC))
    from dnfw import safety
    from dnfw.firmware.load import load
    dsp = load(built).container.find(7)
    return {"dsp_upload": {"used": len(dsp.unpack()), "limit": safety.SHARC_MAX_UNPACKED},
            "usb": {"used": safety.usb_upgrade_bytes(built), "limit": safety.USB_UPGRADE_BUFFER}}


ROW_KEYS = ("release", "mod_version", "os", "file", "sha256", "gate", "zip", "zip_sha256", "inputs",
            "dn2_sha256", "budgets")


def main(argv: list[str]) -> int:
    local_sha = None
    if "--local-test" in argv:
        i = argv.index("--local-test")
        local_sha = argv[i + 1].lower() if i + 1 < len(argv) else ""
        if len(local_sha) != 64 or any(c not in "0123456789abcdef" for c in local_sha):
            print("--local-test needs the build's full 64-hex sha256")
            return 2
        argv = argv[:i] + argv[i + 2:]
    test = "--uncleared-test" in argv or local_sha is not None
    args = [a for a in argv if a != "--uncleared-test"]
    if len(args) != 3:
        print(__doc__)
        return 2
    build, release, outdir = pathlib.Path(args[0]), args[1], pathlib.Path(args[2])
    want = hashlib.sha256(build.read_bytes()).hexdigest()
    if local_sha is not None:
        if want != local_sha:
            print(f"REFUSED: {build.name} has sha256 {want}, not the {local_sha} named for the local test")
            return 1
        print(f"LOCAL TEST bundle: {build.name} sha256 {want}, the coordinator's word that its brick-risk steps passed "
              "(not a release clearing). Page honours it on localhost, --preview site, ?localtest=1 only.")
    rec_path = pathlib.Path(str(build) + ".gate.json")
    record = json.loads(rec_path.read_text()) if rec_path.is_file() else None
    if not cleared(record, want) and not test:
        print(f"REFUSED: {build.name} ({want[:16]}...) has no gate record that clears it "
              f"({'no ' + rec_path.name if record is None else rec_path.name + ' does not clear this sha256'}). "
              "Run scripts/ship_gate.py on it first.")
        return 1
    paths = stock_paths()
    missing = [k for k in ("dn2", "dt2", "md") if k not in paths or not paths[k].is_file()]
    if missing:
        print(f"missing Elektron files: {', '.join(missing)} (set DN2_OS112 and DN2_STOCK_DIR)")
        return 1
    mod_version = (ROOT / "VERSION").read_text().strip()
    with tempfile.TemporaryDirectory() as td:
        got, files, reads_mnm = traced_build(paths, pathlib.Path(td))
    if got != want:
        print(f"the browser's route here gives {got}, not {build.name}'s {want}")
        return 1
    inputs = ["dn2", "dt2", "md"] + (["mnm"] if reads_mnm else [])
    if reads_mnm and "mnm" not in paths:
        print("this build reads the Monomachine OS: set DN2_STOCK_DIR to a folder with it")
        return 1
    zbytes = _zip(files)
    iso = isolated_rebuild(zbytes, mod_version, paths, inputs)
    if iso != want:
        print(f"the zip alone does not rebuild {build.name}: {iso}")
        return 1
    from dn2patch import unzip
    dn2_sha = hashlib.sha256(unzip(paths["dn2"].read_bytes(), (".syx",))).hexdigest()
    zsha = hashlib.sha256(zbytes).hexdigest()
    rel = outdir / f"v{release}"
    rel.mkdir(parents=True, exist_ok=True)
    zname = f"code-{zsha[:12]}.zip"
    (rel / zname).write_bytes(zbytes)
    fname = f"DN2wishes_v{release}.syx"
    gate = None
    if cleared(record, want):
        gate = f"v{release}/{fname}.gate.json"
        (outdir / gate).write_text(json.dumps(public_record(record), indent=1) + "\n")
    row = {"release": release, "mod_version": mod_version, "os": "1.12", "file": fname, "sha256": want,
           "gate": gate, "zip": f"v{release}/{zname}", "zip_sha256": zsha, "inputs": inputs,
           "dn2_sha256": dn2_sha, "budgets": budgets(build.read_bytes())}
    if local_sha is not None and gate is None:
        row["local_test"] = {"brick_risk_sha256": want}
    man = outdir / "wishes.json"
    rows = json.loads(man.read_text()) if man.is_file() else []
    rows = [row] + [r for r in rows if r.get("release") != release]
    man.write_text(json.dumps(rows, indent=1) + "\n")
    print(f"{zname}: {len(files)} files, {len(zbytes):,} bytes; the zip alone rebuilds {want[:16]}...; "
          f"inputs {', '.join(inputs)}")
    if gate is None:
        print("NOT CLEARED: no gate record clears this file. The page will offer no Save, and "
              "--check-site refuses this folder.")
    return 0


def check_site(outdir: pathlib.Path) -> int:
    """the Pages workflow's check: wishes.json is a list (an empty list is allowed: the builder then says
    "No release published yet"); every row listed is one build in this format, its zip is there with its
    sha256, and it has a published gate record that clears its sha256. Any miss: exit 1, publish nothing."""
    man = outdir / "wishes.json"
    if not man.is_file():
        print(f"no {man}: nothing cleared to publish")
        return 1
    bad = []
    rows = json.loads(man.read_text())
    if not isinstance(rows, list):
        bad.append("wishes.json is not a list of releases")
        rows = []
    elif not rows:
        print("no release listed yet: the builder will say so")
    for row in rows:
        what = f"v{row.get('release') if isinstance(row, dict) else row}"
        if not isinstance(row, dict) or set(row) != set(ROW_KEYS):
            bad.append(f"{what}: not one build in this bundle's format ({', '.join(ROW_KEYS)})")
            continue
        z = outdir / str(row["zip"])
        if not z.is_file() or hashlib.sha256(z.read_bytes()).hexdigest() != row["zip_sha256"]:
            bad.append(f"{what}: its zip is missing or not the one listed")
        rec = outdir / str(row["gate"]) if row["gate"] else None
        if rec is None or not rec.is_file() or not cleared(json.loads(rec.read_text()), str(row["sha256"])):
            bad.append(f"{what}: no gate record clears {str(row['sha256'])[:16]}...")
    for b in bad:
        print("REFUSED: " + b)
    if not bad:
        print(f"{man}: every release listed is cleared and every zip is the one listed")
    return 1 if bad else 0
