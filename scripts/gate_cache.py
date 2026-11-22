"""ship_gate's exact reuse of a step's pass (v0.25; the owner's go-ahead, 2026-10-25).

A gate step's pass is reused only when nothing it read has changed: while it runs, every
Python process of the step notes the files it opens, the directories it lists, the
native libraries it loads and the programs it starts (scripts/gate_trace/sitecustomize.py).
When the step passes, the files it read (not those it wrote) are hashed (sha256) and kept
with its commands. A later gate reuses the pass only if its commands are the same and
every one of those files is byte-identical now -- the build's sections it checked, the
scripts, the models, the emulator and its snapshot, the Python that ran it. Anything else,
including a file that has gone, means the step runs again.

Paths in the gate's own work directory (the build's sections it writes) are kept as
@WORK/..., so a later gate's own copies are what get compared.

2026-11-16 (gate speed): a step's Python reads no byte-code from the tree or the interpreter (it compiles its
own, PYTHONPYCACHEPREFIX inside its trace folder: never an input; the sources it compiled are). Its temporary
files go in a folder made empty for it (TMPDIR); that folder is left out of the record only when every program
the step ran is accounted for (_program_inputs): Python traces itself; gcc (the m68k cross compiler or the host's
cc) has its installation, its include folders' listings and every file each compile and link read, by gcc's and
ld's own account taken as it started (the tracer: gcc -M, ld --trace), put in the record; the cross binutils, and
native code the step built and ran, have every file on their command lines put in it, and that native code must
import no libc call that opens, lists or looks up a file (the tracer: nm -D). Then everything in the folder was
made by the step from its inputs. A step that ran any other program keeps the folder in its record (not reused)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time

SKIP = ("/proc/", "/sys/", "/dev/", "/run/", "/tmp/pytest-")
KEEP = 6                                    # records kept a step
PYCACHE = "pycache"                         # 2026-11-16: inside a step's trace folder, its own byte-code
                                            # (PYTHONPYCACHEPREFIX, ship_gate.run): written and read by the
                                            # step alone, from the sources it read; never an input


def _sha(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def _listing(path: str) -> str | None:
    try:
        return hashlib.sha256("\n".join(sorted(os.listdir(path))).encode()).hexdigest()
    except OSError:
        return None


def _norm(path: str, work: pathlib.Path) -> str:
    w = str(work)
    return "@WORK" + path[len(w):] if path == w or path.startswith(w + os.sep) else path


def _real(path: str, work: pathlib.Path) -> str:
    return str(work) + path[5:] if path.startswith("@WORK") else path


def norm_cmd(cmd, work: pathlib.Path) -> list[str]:
    """A command with this run's work directory written @WORK, wherever it appears in an
    argument (v0.28: the sample link's --steps name its symbols file inside the work
    directory, so its key changed every run and the step was never reused; the file itself
    is traced, @WORK/link16_syms.json, and compared like any input)."""
    w = str(work)
    return [_norm(str(c), work).replace(w + os.sep, "@WORK" + os.sep) for c in cmd]


def _under(path: str, roots) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


# 2026-11-16 (gate speed): the programs a step starts that are not Python (which traces itself). gcc (the m68k cross
# compiler or the host's cc), the cross binutils and native code the step built itself are accounted for below; QUIET
# programs read no file. Any other program leaves the step's own temporary folder in its record (not reused).
CROSS = re.compile(r"[A-Za-z0-9_.]+(?:-[A-Za-z0-9_.]+)+-(gcc|as|ld|objcopy|objdump|nm|readelf)(?:-\d+)?")
GCC = re.compile(r"(?:[A-Za-z0-9_.]+(?:-[A-Za-z0-9_.]+)+-)?(?:gcc|cc)(?:-\d+)?")
QUIET = {"uname"}
PATH_OPTS = {"-T", "-I", "-L", "-include", "-imacros", "-isystem", "-iquote"}   # options whose value is a path


def _run(cmd, cwd=None) -> str | None:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout + r.stderr if r.returncode == 0 else None


def _gcc_own(gcc: str) -> tuple[list[str], list[str]] | None:
    """the files of GCC's own installation (every file under its install and programs folders, and the as and ld
    it runs) and its #include <...> search folders -> (files, folders); None if gcc cannot say"""
    out = _run([gcc, "-print-search-dirs"])
    inc = _run([gcc, "-xc", "-E", "-v", os.devnull])
    if out is None or inc is None:
        return None
    roots = []
    for line in out.splitlines():
        key, _, val = line.partition(": ")
        if key in ("install", "programs"):
            roots += [os.path.realpath(v) for v in val.lstrip("=").split(os.pathsep) if os.path.isdir(v)]
    walked = [(d, fs) for r in set(roots) for d, _, fs in os.walk(r)]
    # every file (a link that leads nowhere is no file: the folders' listings name it) and every folder's listing
    files = {os.path.join(d, f) for d, fs in walked for f in fs if os.path.isfile(os.path.join(d, f))}
    files |= {d + os.sep for d, _ in walked}
    for prog in ("as", "ld"):
        name = (_run([gcc, f"-print-prog-name={prog}"]) or "").strip()
        path = name if os.path.isabs(name) else shutil.which(name or prog)
        if not path:
            return None
        files.add(os.path.realpath(path))
    m = re.search(r"#include <\.\.\.> search starts here:\n(.*?)\nEnd of search list", inc, re.S)
    if not m:
        return None
    return sorted(files), [os.path.realpath(x.strip()) for x in m.group(1).splitlines() if x.strip()]


def _named(argv: list[str], cwd: str, objcopy: bool) -> tuple[list[str], list[str]]:
    """a command line -> (the paths it names as inputs, the paths it writes: -o's, objcopy's second)"""
    named, outs, args, i = [], [], argv[1:], 0
    while i < len(args):
        a = args[i]
        if a == "-o" and i + 1 < len(args):
            outs.append(args[i + 1])
            i += 2
            continue
        if a in PATH_OPTS and i + 1 < len(args):
            named.append(args[i + 1])
            i += 2
            continue
        if a.startswith(("-I", "-L")) and len(a) > 2:
            named.append(a[2:])
        elif not a.startswith("-") and ("/" in a or os.path.exists(os.path.join(cwd, a))):
            named.append(a)                         # (a bare word that is no file is an option's value: -e 0)
        i += 1
    if objcopy and len(named) >= 2:
        outs.append(named.pop())                    # objcopy IN OUT
    return ([os.path.normpath(os.path.join(cwd, x)) for x in named],
            [os.path.normpath(os.path.join(cwd, x)) for x in outs])


def _program_inputs(x_items, pys: set[str], scratch: list[str], gcc_reads: list, gfail: list, natives: dict,
                    dlopened: set[str], written: set[str]) -> dict[str, str] | None:
    """What the step's non-Python programs read, as inputs: gcc's own installation and include folders' listings;
    every file a compile and a link read, by gcc's and ld's own account (taken by the tracer as each started); every
    file named on the command line of gcc, a cross binutils program, or a program the step built. Native code the
    step built (a library it loaded, a program it ran) is accounted for only if it calls nothing that could read or
    find a file (the tracer's nm check). A file that has gone is accounted for only if the step made it (its Python
    wrote it, a command of the step wrote it, or it is in the step's own temporary folder). None if anything is not
    accounted for (then the temporary folder stays in the record)."""
    if gfail or any(v is None or v for v in natives.values()):
        return None
    if any(_under(d, scratch) and d not in natives for d in dlopened):
        return None                                 # a library of the step's own, not checked
    out: dict[str, str] = {}
    gccs: dict[str, tuple | None] = {}
    made = set(written)
    todo = []
    for exe, argv, cwd in x_items:
        prog = exe or (argv[0] if isinstance(argv, list) and argv else "")
        cwd = cwd or os.getcwd()
        path = prog if os.path.isabs(prog) else (os.path.normpath(os.path.join(cwd, prog)) if os.sep in prog
                                                 else shutil.which(prog) or "")
        if path and os.path.realpath(path) in pys:
            continue                                # Python: traced by its own process
        base = os.path.basename(prog)
        if base in QUIET:
            continue
        if not isinstance(argv, list) or not argv:
            return None
        m = CROSS.fullmatch(base)
        own_build = _under(path, scratch) and path in natives
        if not (m or GCC.fullmatch(base) or own_build):
            return None
        named, outs = _named(argv, cwd, bool(m) and m.group(1) == "objcopy")
        made |= set(outs)
        todo += named
        if GCC.fullmatch(base) or (m and m.group(1) == "gcc"):
            real = os.path.realpath(path)
            if real not in gccs:
                gccs[real] = _gcc_own(path)
                if gccs[real] is None:
                    return None
                for f in gccs[real][0]:
                    if f.endswith(os.sep):
                        out.setdefault(f.rstrip(os.sep), "d:" + (_listing(f) or "missing"))
                    else:
                        out[f] = "f:" + (_sha(f) or "missing")
                for d in gccs[real][1]:
                    if os.path.isdir(d):
                        out.setdefault(d, "d:" + (_listing(d) or "missing"))
    for kind, (_cwd, files) in gcc_reads:
        todo += files
        if kind == "gd":
            todo += [os.path.dirname(f) for f in files[:1]]        # the source's folder ("x.h" is looked up there)
    for f in todo:
        if _under(f, scratch) or f in made:
            continue                                # made by the step
        if os.path.isfile(f):
            out[f] = "f:" + (_sha(f) or "missing")
        elif os.path.isdir(f):
            out.setdefault(f, "d:" + (_listing(f) or "missing"))
        elif any(_under(w, [f]) for w in made):
            continue                                # a folder of the step's own (it made what was in it)
        else:
            return None                             # gone, and the step did not make it
    return out


def inputs(trace_dir: pathlib.Path, work: pathlib.Path, logs: pathlib.Path) -> dict[str, str]:
    """The traces under TRACE_DIR -> {path (normalised): 'f:sha' | 'd:sha' | 'x:sha'}."""
    reads, written, dirs, progs, pys = set(), set(), set(), set(), set()
    x_items, scratch, gcc_reads, gfail, natives, dlopened = [], [], [], [], {}, set()
    for t in trace_dir.glob("trace-*.jsonl"):
        for line in t.read_text().splitlines():
            try:
                kind, item = json.loads(line)
            except ValueError:
                continue
            if kind == "r":
                reads.add(item)
            elif kind == "w":
                written.add(item)
            elif kind == "d":
                dirs.add(item)
            elif kind == "x":
                progs.add(item[0] or (item[1][0] if isinstance(item[1], list) and item[1] else ""))
                x_items.append((item[0], item[1], item[2] if len(item) > 2 else None))
            elif kind == "py":
                pys.add(item[0])
            elif kind == "scratch":
                scratch += item
            elif kind in ("gd", "gl"):
                gcc_reads.append((kind, item))
            elif kind == "gd-fail":
                gfail.append(item)
            elif kind == "native":
                natives[item[0]] = item[1]
            elif kind == "native-fail":
                natives[item] = None
            elif kind == "dl":
                dlopened.add(item)
    # 2026-11-16: the step's own temporary folder (ship_gate.run: made empty for the step, TMPDIR) is left out
    # only when every program the step ran is accounted for (_program_inputs: what they read is in the record);
    # what is there was then made by the step, from its inputs. Otherwise it stays in, as before
    extra = _program_inputs(x_items, {os.path.realpath(p) for p in pys}, scratch, gcc_reads, gfail, natives,
                            dlopened, written) if scratch else None
    if extra is not None:
        reads = {r for r in reads if not _under(r, scratch)}
        dirs = {d for d in dirs if not _under(d, scratch)}
    for r in list(reads):                       # a compiled module stands for its source:
        p = pathlib.Path(r)                     # the source is what decides it
        if p.parent.name == "__pycache__" and p.suffix == ".pyc":
            src = p.parent.parent / (p.name.split(".")[0] + ".py")
            if src.is_file():
                reads.add(str(src))
    out = {}
    lg = str(logs)
    for r in sorted(reads - written):
        if r.startswith(SKIP) or r.startswith(lg) or not os.path.isfile(r):
            continue
        h = _sha(r)
        if h:
            out[_norm(r, work)] = "f:" + h
    for d in sorted(dirs):
        if d.startswith(SKIP) or not os.path.isdir(d):
            continue
        h = _listing(d)
        if h:
            out.setdefault(_norm(d, work), "d:" + h)
    for x in sorted(progs | pys):
        if extra is not None and _under(x, scratch):
            continue                                # built by the step and checked (_program_inputs)
        path = x if os.path.isabs(x) else (shutil.which(x) or "")
        h = _sha(path) if path else None
        out[_norm(path or x, work)] = "x:" + (h or "missing")
    for p, h in (extra or {}).items():
        out.setdefault(_norm(p, work), h)
    return out


def _cache(root: pathlib.Path, name: str) -> pathlib.Path:
    slug = "".join(c if c.isalnum() else "_" for c in name)
    return root / "out" / "gate_cache" / f"{slug}.json"


def _common_dir(top: pathlib.Path) -> str | None:
    """the git common directory of the checkout at TOP (a worktree's .git file names it), or None"""
    g = top / ".git"
    try:
        if g.is_dir():
            return str(g.resolve())
        if g.is_file():
            d = pathlib.Path(g.read_text().split("gitdir:", 1)[1].strip())
            c = d / "commondir"
            return str((d / c.read_text().strip()).resolve()) if c.exists() else str(d.resolve())
    except (OSError, IndexError):
        return None
    return None


def _foreign(path: str, root: pathlib.Path) -> bool:
    """v0.47: an input inside ANOTHER checkout of this repository (a sibling worktree): a pass
    recorded there read that checkout's files, so its record says nothing about this one's (a
    cache copied from v046-wt into v047-wt re-hashed v046-wt's own, unchanged, files and
    reused v0.46's unit tests for v0.47's changed tree). Such a record is never reused."""
    rp, base = pathlib.Path(path), root.resolve().parent
    try:
        rel = rp.relative_to(base)
    except ValueError:
        return False
    top = base / rel.parts[0]
    if not rel.parts or top == root.resolve():
        return False
    mine = _common_dir(root.resolve())
    return mine is not None and _common_dir(top) == mine


def lookup(root: pathlib.Path, name: str, cmds, work: pathlib.Path):
    """-> the record whose commands are CMDS and whose every input is unchanged, or None.
    v0.47: a record that read another checkout of this repository is not this tree's."""
    f = _cache(root, name)
    if not f.exists():
        return None
    try:
        records = json.loads(f.read_text())
    except ValueError:
        return None
    for rec in reversed(records):
        if rec.get("cmds") != cmds or not rec.get("inputs"):
            continue
        ok = True
        for path, want in rec["inputs"].items():
            real = _real(path, work)
            if _foreign(real, root):
                ok = False
                break
            kind, _, h = want.partition(":")
            now = (_sha(real) if kind in ("f", "x") else _listing(real)) if os.path.exists(real) else None
            if now != h:
                ok = False
                break
        if ok:
            return rec
    return None


def store(root: pathlib.Path, name: str, cmds, ins: dict[str, str], detail: str, build_sha: str) -> None:
    f = _cache(root, name)
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        records = json.loads(f.read_text()) if f.exists() else []
    except ValueError:
        records = []
    records.append({"cmds": cmds, "inputs": ins, "detail": detail, "build": build_sha,
                    "date": time.strftime("%Y-%m-%dT%H:%M:%S")})
    f.write_text(json.dumps(records[-KEEP:], indent=1))
