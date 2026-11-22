"""ship_gate's tracer (v0.25): with DNFW_GATE_TRACE set, every Python process of a gate
step -- the step itself and any Python it starts -- notes each file it opens (reading or
writing), each directory it lists and each program it runs, one JSON line a new item, in
DNFW_GATE_TRACE/trace-<pid>.jsonl, written as it goes (so a process that ends without
its exit handlers still left its reads). ship_gate.py hashes the files read (not those a
step wrote) and reuses a step's pass only while every one is byte-identical.

Loaded as `sitecustomize` through PYTHONPATH; the system's own sitecustomize, if any,
still runs first."""

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _p in list(sys.path):                           # the system's sitecustomize, if any
    if os.path.abspath(_p or ".") == _here:
        continue
    _f = os.path.join(_p or ".", "sitecustomize.py")
    if os.path.isfile(_f):
        try:
            exec(compile(open(_f, "rb").read(), _f, "exec"), {"__name__": "_system_sitecustomize"})
        except Exception:                           # noqa: BLE001 -- never break the step
            pass
        break

_dir = os.environ.get("DNFW_GATE_TRACE")
if _dir:
    import json

    # left out: the trace folder itself (2026-11-16: with the step's own byte-code, PYTHONPYCACHEPREFIX, which
    # the step's Python wrote and read, from the sources it read)
    _own = tuple({os.path.abspath(_dir).rstrip(os.sep), os.path.realpath(_dir).rstrip(os.sep)})

    def _mine(path):
        return any(path == d or path.startswith(d + os.sep) for d in _own)

    _seen = set()
    _busy = [False]
    _out = [None]

    _SCR = tuple({p.rstrip(os.sep) for d in [os.environ.get("DNFW_GATE_SCRATCH")] if d
                  for p in (os.path.abspath(d), os.path.realpath(d))})
    _SRC = (".c", ".S", ".s", ".i", ".cc", ".cpp")
    # what native code the step built must not call: it would read (or find) files the tracer cannot see
    _FORBID = (r"(__)?(open|open64|openat|openat64|fopen|fopen64|freopen|freopen64|fdopendir|opendir|scandir\w*|creat|"
               r"creat64|dlopen|dlmopen|exec\w*|system|popen|posix_spawn\w*|fork|vfork|clone\w*|syscall|\w*stat|"
               r"\w*stat64|\w*statx|access|faccessat\w*|euidaccess|eaccess|readlink\w*|realpath|name_to_handle_at|"
               r"open_by_handle_at|__open\w*|__xstat\w*|__lxstat\w*|__fxstatat\w*)")

    def _run(cmd, cwd, env):
        import subprocess
        try:
            return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600,
                                  stdin=subprocess.DEVNULL)
        except Exception:                           # noqa: BLE001
            return None

    def _gcc(argv, cwd, env):
        """2026-11-16: a gcc (cross or the host's) about to start, while its inputs exist: by gcc's own account, the
        files its compile will read (the same command with -M, no -c, no -o) -> ["gd", [cwd, files]], and the files
        its link will read (the same link into a file of our own, with ld's --trace) -> ["gl", [cwd, files]];
        ["gd-fail", argv] if gcc cannot say (gate_cache then keeps the step's temporary folder in its record)"""
        import re
        import tempfile
        if not re.fullmatch(r"(?:[A-Za-z0-9_.]+(?:-[A-Za-z0-9_.]+)+-)?(?:gcc|cc)(?:-\d+)?", os.path.basename(argv[0])) \
                or any(a in ("-E", "-M", "-MM", "--version", "-v") or a.startswith("-print") for a in argv[1:]):
            return
        cmd, skip = [], False
        for a in argv:
            if skip:
                skip = False
            elif a == "-o":
                skip = True
            elif a != "-c" and not (a.startswith("-o") and len(a) > 2):
                cmd.append(a)
        if any(a.endswith(_SRC) for a in argv[1:]):
            r = _run(cmd + ["-M"], cwd, env)
            if r is None or r.returncode != 0:
                _note("gd-fail", argv)
                return
            text = r.stdout.replace("\\\n", " ")
            files = [d.replace("\\ ", " ") for line in text.splitlines()
                     for d in re.split(r"(?<!\\)\s+", line.partition(":")[2].strip()) if d]
            _note("gd", [cwd, [os.path.normpath(os.path.join(cwd, f)) for f in files]])
        if not any(a in ("-c", "-S") for a in argv[1:]):
            fd, out = tempfile.mkstemp(prefix="gl-")
            os.close(fd)
            try:
                r = _run(cmd + ["-o", out, "-Wl,--trace"], cwd, env)
            finally:
                os.unlink(out)
            if r is None or r.returncode != 0:
                _note("gd-fail", argv)
                return
            files = [m for line in r.stdout.splitlines() for m in re.findall(r"(/[^\s()]+)", line)]
            _note("gl", [cwd, sorted({os.path.normpath(f) for f in files if os.path.isfile(f)})])

    def _native(path, env):
        """2026-11-16: a native library or program in the step's own temporary folder (built by the step), about to
        be loaded or run: the libc calls it imports that could read or find a file -> ["native", [path, calls]],
        or ["native-fail", path] (gate_cache: a step whose own native code can do so keeps its folder)"""
        import re
        if not _SCR or not any(path == d or path.startswith(d + os.sep) for d in _SCR):
            return
        r = _run(["nm", "-D", "--undefined-only", path], None, env)
        if r is None or r.returncode != 0:
            _note("native-fail", path)
            return
        names = [ln.split()[-1].split("@")[0] for ln in r.stdout.splitlines() if ln.strip()]
        _note("native", [path, sorted({n for n in names if re.fullmatch(_FORBID, n)})])

    def _note(kind, item):
        key = (kind, json.dumps(item))
        if key in _seen:
            return
        _seen.add(key)
        if _out[0] is None:
            _out[0] = os.open(os.path.join(_dir, f"trace-{os.getpid()}.jsonl"),
                              os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.write(_out[0], (json.dumps([kind, item]) + "\n").encode())

    def _hook(event, args):
        if _busy[0]:
            return
        try:
            _busy[0] = True
            if event == "open":
                path, mode, flags = args
                if isinstance(path, int):
                    return
                if isinstance(path, bytes):
                    path = os.fsdecode(path)
                path = os.path.abspath(str(path))
                if _mine(path):
                    return
                writes = (mode is not None and any(c in str(mode) for c in "wax+")) or \
                    (flags is not None and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                _note("w" if writes else "r", path)
            elif event in ("os.listdir", "os.scandir"):
                path = args[0] if args else "."
                if isinstance(path, int):
                    return
                if isinstance(path, bytes):
                    path = os.fsdecode(path)
                _note("d", os.path.abspath(str(path if path is not None else ".")))
            elif event == "ctypes.dlopen":       # native libraries (the emulator's unicorn)
                name = args[0]
                if isinstance(name, bytes):
                    name = os.fsdecode(name)
                if name and os.path.isabs(str(name)):
                    _note("r", str(name))
                    _note("dl", os.path.abspath(str(name)))
                    _native(os.path.abspath(str(name)), None)
            elif event == "subprocess.Popen":
                executable, argv = args[0], args[1]
                cwd = args[2] if len(args) > 2 and args[2] is not None else os.getcwd()
                cwd = os.path.abspath(os.fsdecode(cwd) if isinstance(cwd, bytes) else str(cwd))
                argl = [os.fsdecode(a) if isinstance(a, bytes) else str(a) for a in argv] \
                    if isinstance(argv, (list, tuple)) else str(argv)
                _note("x", [str(executable) if executable else None, argl, cwd])
                if isinstance(argl, list) and argl:
                    env = args[3] if len(args) > 3 else None
                    _gcc(argl, cwd, env)
                    exe = str(executable) if executable else argl[0]
                    _native(os.path.abspath(os.path.join(cwd, exe)) if os.sep in exe else exe, env)
        except Exception:                           # noqa: BLE001
            pass
        finally:
            _busy[0] = False

    def _modules():                                 # what was imported, native ones too
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if f:
                try:
                    _note("r", os.path.abspath(f))
                except Exception:                   # noqa: BLE001
                    pass

    import atexit
    atexit.register(_modules)
    _note("py", [sys.executable, sys.version])
    if os.environ.get("DNFW_GATE_SCRATCH"):         # 2026-11-16: the step's own temporary folder (ship_gate.run)
        _s = os.environ["DNFW_GATE_SCRATCH"]
        _note("scratch", sorted({os.path.abspath(_s), os.path.realpath(_s)}))
    sys.addaudithook(_hook)

# 2026-11-16: the RAM guard (scripts/emulib/ramguard.py) in every emulator step's Python processes:
# no one but the loader changes a chunk the build placed in RAM. Set by ship_gate.py for those steps.
if os.environ.get("DNFW_RAMGUARD"):
    sys.path.append(os.path.dirname(_here))
    try:
        import unicorn as _unicorn                  # noqa: F401 -- a process without it runs no ColdFire
    except ImportError:
        _unicorn = None
    if _unicorn is not None:
        from emulib import ramguard as _ramguard
        _ramguard.install_process(os.environ["DNFW_RAMGUARD"])

# 2026-11-16: the write map (scripts/emulib/writemap.py): scripts/stock_ram_map.py's record of the RAM
# stock writes
if os.environ.get("DNFW_WRITEMAP"):
    if os.path.dirname(_here) not in sys.path:
        sys.path.append(os.path.dirname(_here))
    try:
        import unicorn as _unicorn2                 # noqa: F401
    except ImportError:
        _unicorn2 = None
    if _unicorn2 is not None:
        from emulib import writemap as _writemap
        _writemap.install_process(os.environ["DNFW_WRITEMAP"])

