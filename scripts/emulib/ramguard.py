"""The RAM guard: no one but our loader writes over the chunks the build places in RAM
(2026-11-16, after the combined build 7f7e7d6c crashed the unit at every boot).

On OS 1.12, stock's +Drive read (0x4012c87a) reads through a 64 KiB bounce buffer at 0x4e6f9300 (the
uncached alias of 0x466f9300) whenever its destination is unaligned or its length is not whole sectors.
The boot-screen stamp sat at 0x46708000, under that buffer: a large SD read at power-on overwrote it
and the intro called the garbage (EXCEPTION, Line-F, PC 0x46708000). The emulator never showed it: its
0x4e... pages are not the same memory as 0x46..., and the bounce buffer's writes are eDMA, which the
emulator does from Python (`uc.mem_write`), where no Unicorn write hook sees them.

The guard closes both holes, for every chunk the build places (the gate writes the list,
`chunks_file()`, to DNFW_RAMGUARD), in every Python process of an emulator step that runs a ColdFire
(the gate's sitecustomize installs it):

  * a byte of a chunk is *armed* once it holds the build's byte: from the first emu_start (a snapshot
    step: the harness loaded the chunks already), or the moment the loader writes it (a boot from
    reset). A byte never armed is never checked: a stock run, a NOBOOT build without the stamp.
  * CPU writes into a chunk's constant span (code and constants) that change an armed byte fail;
  * CPU writes into the chunk's uncached alias (+0x08000000) that change an armed byte fail, the
    whole chunk, state included: on the instrument the alias is the same memory;
  * writes from the emulator's own peripherals (any `uc.mem_write` called from digikit's `emu.`
    modules once the run started: eDMA, eSDHC) into a chunk or its alias that change an armed byte
    fail, the whole chunk, state included;
  * when the emulator is released (its last reference dropped), or when the process ends for one still
    alive, every armed byte of every constant span is compared again. (2026-11-16, v0.56.2: the guard
    holds no reference to the emulator, so a harness that makes many in turn -- emu_lfowaves.py makes 34
    -- frees each as before; holding all of them to the process's end ran lfowaves past 15 GB.)

A failure prints `CODEGUARD FAIL ...` (ship_gate fails the step that printed it) and exits 98. With
DNFW_RAMGUARD_LOG=FILE each process appends one JSON line (chunks, armed bytes, writes seen), the
evidence the guard ran.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import struct
import sys
import weakref

EXIT = 98
ALIAS = 0x08000000                       # 0x4e... is the uncached alias of 0x46... (MCF5441x ACRs)
OURS_LO, OURS_HI = 0x46000000, 0x48000000


def chunks_file(rows: list[dict], path) -> None:
    """The gate's side: write the build's chunks. rows: {name, load, code (hex), const_end}, const_end
    the end of the part no one may change (code, constants); the rest is the chunk's own state."""
    with open(path, "w") as f:
        json.dump(rows, f)


def build_rows(content: bytes | None = None) -> list[dict]:
    """-> every chunk the build in this tree places in RAM, with its bytes: dnfw.mods.waverider's
    content chunks and the boot-screen stamp. The constant span of each: the C chunk to the end of its
    rodata, the stamp to its BSS (zst); the others whole (code, descriptors, names, fonts, tables).

    CONTENT (the build's MAIN OS, 2026-11-17): also every other CODE chunk of its area, with the image's own
    bytes (lfowaves' runtime, lfo4's C and its relocated table, filled from the image at apply time), no
    constant span (only DMA and alias writes fail: their writable parts are not known here); and, when it
    carries lfo4, its three LFO state arrays as `no_dma` rows: any DMA or uncached-alias write into them
    fails, whatever it writes (they sat under stock 1.12's +Drive bounce buffer until 2026-11-17)."""
    from dnfw.mods import bootscreen, waverider          # noqa: PLC0415
    lay = waverider.SPEC.get("layout", {})
    rows = []
    for load, code, what in waverider._chunks():          # noqa: SLF001 -- the loader's own list
        end = load + len(code)
        if load == lay.get("c_load"):
            end = lay.get("c_rodata_end", lay["c_text_end"])     # an older layout: its code alone
        rows.append({"name": what, "load": load, "code": code.hex(), "const_end": end})
    s = bootscreen.SPEC
    stamp = bytes.fromhex(s["code"])
    rows.append({"name": "the boot-screen stamp", "load": s["load"], "code": stamp.hex(),
                 "const_end": s.get("zst", s["load"] + len(stamp))})
    if content is not None:
        rows += _image_rows(content, {r["load"] for r in rows})
    return rows


def _image_rows(content: bytes, have: set[int]) -> list[dict]:
    """the area's other CODE chunks, and lfo4's state arrays when the image carries lfo4's C"""
    from dnfw.mods import lfo4, platform                 # noqa: PLC0415
    from dnfw.patch import area                          # noqa: PLC0415
    rows, loads = [], set()
    for cid, data in platform.split(content)[1] if len(content) > platform.spec_for(content)["stock_length"] else []:
        if cid != area.CODE:
            continue
        c = area.CodeChunk.unpack(data)
        loads.add(c.load)
        if c.load not in have:
            from dnfw.mods import safemode                # noqa: PLC0415  (2026-11-21: its head, code, constants)
            const = safemode.SPEC["const_end"] if c.load == safemode.SPEC["load"] else c.load
            rows.append({"name": f"the image's code chunk at {c.load:#010x}", "load": c.load,
                         "code": c.image.hex(), "const_end": const})
    if any(e.start in loads for e in lfo4.ram()[len(lfo4.STATE_RAM):]):   # lfo4's chunks: the build carries lfo4
        rows += [{"name": what, "load": va, "code": bytes(n).hex(), "const_end": va, "no_dma": True}
                 for va, n, what in lfo4.STATE_RAM]
    return rows


class Guard:
    def __init__(self, rows: list[dict]):
        self.rows = [(r["name"], r["load"], bytes.fromhex(r["code"]), r["const_end"]) for r in rows]
        self.no_dma = [bool(r.get("no_dma")) for r in rows]
        self.armed = [bytearray(len(c)) for _, _, c, _ in self.rows]
        self.bad: list[dict] = []
        self.n_bad = 0
        self.writes = 0
        self.started = False
        self.uc_ref = None                   # a weak reference: the guard never keeps the emulator alive
        self.uc_strong = None                # (only where the engine cannot be read by its handle: _raw_reader)
        self.uch = None                      # the engine's handle, read at its release
        self.closed = False

    def _read(self, addr: int, n: int) -> bytes:
        uc = self.uc_ref() if self.uc_ref is not None else None
        if uc is not None:
            return bytes(uc.mem_read(addr, n))
        return _RAW_READ(self.uch, addr, n)

    # -- where an address falls -------------------------------------------------------------
    def _hit(self, addr: int, size: int):
        """-> [(row index, offset in chunk, offset in the write, count, alias?)]"""
        out = []
        for i, (_, lo, code, _) in enumerate(self.rows):
            for alias in (False, True):
                base = lo + (ALIAS if alias else 0)
                a, b = max(addr, base), min(addr + size, base + len(code))
                if a < b:
                    out.append((i, a - base, a - addr, b - a, alias))
        return out

    def _check(self, addr: int, data: bytes, how: str, pc=None, uc=None):
        for i, off, at, n, alias in self._hit(addr, len(data)):
            name, lo, code, cend = self.rows[i]
            arm = self.armed[i]
            if self.no_dma[i] and (alias or how == "dma"):     # state no DMA or alias write may reach
                self._fail(name, lo + off + (ALIAS if alias else 0), how, pc, data[at], 0, uc)
                continue
            for k in range(n):
                j, v = off + k, data[at + k]
                if v == code[j]:
                    if not alias and how == "cpu":
                        arm[j] = 1                    # the loader (or anyone) wrote the build's byte
                    continue
                if not arm[j]:
                    continue
                strict = alias or how == "dma" or lo + j < cend
                if not strict:
                    continue                          # the chunk's own state, written by the CPU
                if not alias and how == "cpu":
                    arm[j] = 0                        # report a run once, not per byte after
                self._fail(name, lo + j + (ALIAS if alias else 0), how, pc, v, code[j], uc)
                break

    def _fail(self, name, addr, how, pc, got, want, uc=None):
        self.n_bad += 1
        if len(self.bad) < 8:
            rec = {"chunk": name, "address": f"{addr:#010x}", "by": how, "wrote": f"{got:#04x}",
                   "build": f"{want:#04x}"}
            if pc is not None:
                rec["pc"] = f"{pc:#010x}"
                rec["callers"] = self._callers(uc)
            self.bad.append(rec)

    def _callers(self, uc):
        from unicorn import m68k_const as K             # noqa: PLC0415
        try:
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            words = struct.unpack(">32I", bytes(uc.mem_read(sp, 128)))
        except Exception:                                # noqa: BLE001
            return []
        return [f"{v:#010x}" for v in words if 0x40000400 <= v < 0x40400000 or OURS_LO <= v < OURS_HI][:6]

    # -- installation -------------------------------------------------------------------------
    def first_start(self, uc) -> None:
        """At the first emu_start: arm what already holds the build's bytes, hook the CPU's writes."""
        from unicorn import UC_HOOK_MEM_WRITE           # noqa: PLC0415
        from unicorn import m68k_const as K             # noqa: PLC0415
        self.started = True
        for i, (_, lo, code, _) in enumerate(self.rows):
            try:                                         # loaded whole by a harness: armed. Anything less
                got = bytes(uc.mem_read(lo, len(code)))  # (zeroed RAM matching the build's zero bytes, a
            except Exception:                            # noqa: BLE001 -- stock run) arms only as the
                continue                                 # loader writes it, byte by byte
            if got == code:
                self.armed[i][:] = b"\x01" * len(code)

        def wrote(uc, access, address, size, value, user):
            self.writes += 1
            data = (value & ((1 << 8 * size) - 1)).to_bytes(size, "big")
            self._check(address, data, "cpu", uc.reg_read(K.UC_M68K_REG_PC), uc)

        for _, lo, code, _ in self.rows:
            for base in (lo, lo + ALIAS):
                uc.hook_add(UC_HOOK_MEM_WRITE, wrote, begin=base, end=base + len(code) - 1)

    def host_write(self, addr: int, data: bytes, dma: bool) -> None:
        """uc.mem_write. DMA (the emulator's peripherals, once the run started): checked. Anyone else
        (a harness loading the build's chunks, a test poking a value): arms the bytes it writes equal to
        the build's, disarms those it changes, never fails."""
        data = bytes(data)
        if dma:
            if self.started:
                self._check(addr, data, "dma")
            return
        for i, off, at, n, alias in self._hit(addr, len(data)):
            if alias:
                continue
            code, arm = self.rows[i][2], self.armed[i]
            for k in range(n):
                arm[off + k] = 1 if data[at + k] == code[off + k] else 0

    def at_exit(self) -> None:
        """The end of this emulator's run: its release, or the process's end while it is alive."""
        if self.closed:
            return
        self.closed = True
        if self.started:
            for i, (name, lo, code, cend) in enumerate(self.rows):
                arm = self.armed[i]
                try:
                    got = self._read(lo, cend - lo)
                except Exception:                        # noqa: BLE001
                    continue
                for j in range(cend - lo):
                    if arm[j] and got[j] != code[j]:
                        self._fail(name, lo + j, "unseen (the end of the run)", None, got[j], code[j])
                        break
        log = os.environ.get("DNFW_RAMGUARD_LOG")
        if log:
            with open(log, "a") as f:
                f.write(json.dumps({"argv": sys.argv[:3], "started": self.started, "writes": self.writes,
                                    "armed": {n: sum(a) for (n, _, _, _), a in zip(self.rows, self.armed)},
                                    "failed": self.n_bad}) + "\n")
        if self.n_bad:
            sys.stdout.flush()
            print(f"CODEGUARD FAIL: {self.n_bad} write(s) changed a chunk the build placed in RAM "
                  f"(emulib/ramguard.py): {json.dumps(self.bad)}", flush=True)
            sys.stderr.flush()
            os._exit(EXIT)


def install_process(path: str) -> None:
    """From sitecustomize: guard every m68k Unicorn this process starts. The first m68k Uc that runs
    is the ColdFire; a second one gets its own guard."""
    import unicorn                                       # noqa: PLC0415

    rows = json.load(open(path))
    guards: list[Guard] = []
    orig_start, orig_write = unicorn.Uc.emu_start, unicorn.Uc.mem_write

    def _attach(uc):
        g = Guard(rows)
        g.uc_ref = weakref.ref(uc)
        g.uch = uc._uch                                  # noqa: SLF001
        if _RAW_READ is None:                            # the engine not readable by its handle: kept to the end
            g.uc_strong = uc
        else:
            by_handle[_handle_key(uc._uch)] = g          # noqa: SLF001
        if not guards:                                   # registered after Unicorn's own finalizer (made with
            atexit.register(lambda: [x.at_exit() for x in guards])   # the Uc): atexit runs it first, while
        guards.append(g)                                 # the engine is still open
        uc._dnfw_ramguard = g
        return g

    def emu_start(self, *a, **k):
        g = getattr(self, "_dnfw_ramguard", None)
        if getattr(self, "_arch", None) == unicorn.UC_ARCH_M68K:
            if g is None:
                g = _attach(self)
            if not g.started:
                g.first_start(self)
        return orig_start(self, *a, **k)

    def mem_write(self, address, data, *a, **k):
        g = getattr(self, "_dnfw_ramguard", None)
        if g is None and getattr(self, "_arch", None) == unicorn.UC_ARCH_M68K:
            g = _attach(self)
        if g is not None:
            g.host_write(address, data, _from_emulator())
        return orig_write(self, address, data, *a, **k)

    by_handle: dict[int, Guard] = {}
    orig_release = unicorn.Uc.release_handle

    def release_handle(uch):
        # Unicorn's finalizer, before uc_close: the emulator is finished (its object is gone). Compare now,
        # while the engine is still open, and let it go
        g = by_handle.pop(_handle_key(uch), None)
        if g is not None:
            g.at_exit()
            if g in guards:
                guards.remove(g)
        return orig_release(uch)

    unicorn.Uc.release_handle = staticmethod(release_handle)
    unicorn.Uc.emu_start = emu_start
    unicorn.Uc.mem_write = mem_write


def _handle_key(uch) -> int:
    return uch.value if isinstance(uch, ctypes.c_void_p) else int(uch or 0)


def _raw_reader():
    """-> read(uch, addr, n) through Unicorn's library by the engine's handle (the binding's own uc_mem_read),
    or None where that binding is not there: then each emulator is held to the process's end, as before"""
    try:
        from unicorn.unicorn_py3.unicorn import uclib    # noqa: PLC0415
    except Exception:                                    # noqa: BLE001
        return None

    def read(uch, addr: int, n: int) -> bytes:
        buf = ctypes.create_string_buffer(n)
        if uclib.uc_mem_read(uch, addr, buf, n) != 0:
            raise RuntimeError(f"uc_mem_read {addr:#x}+{n} failed")
        return bytes(buf.raw)
    return read


_RAW_READ = _raw_reader()


def _from_emulator() -> bool:
    """True when the caller of uc.mem_write is digikit's emulator (emu.*): a peripheral's DMA, not a
    harness loading code or a test poking a value."""
    f = sys._getframe(2)                                 # noqa: SLF001
    name = f.f_globals.get("__name__", "")
    return name.startswith("emu.") and name not in ("emu.checkpoint", "emu.longrun", "emu.boot")
