"""The DSP load budget at note-on (csrc/load, docs/load-budget.md) on stock 1.12's own voice allocator, in the emulator.

    # inside the bench (bench_ns112.sh: DT2_SECTIONS, digikit at /mnt/d/01_Code/Z_Personal/digikit-up):
    python scripts/emu_load_budget.py [--snapshot S] [--json OUT]

The sequencer does not play under the emulator, so the note-on is entered as the audio interrupt enters it: our hook
(load_alloc_hook, at the ISR's jsr 0x4002a6a2) called with the nine arguments the ISR pushes, a6 a frame of its locals,
on an allocator state laid out here (the staging masks copied to the live ones at the tick, the voice records, the held
slots, the tick). The build's ColdFire edits and chunks are installed over a stock 1.12 UI snapshot (the platform
loader's copies by hand, as scripts/emu_waverider_menu.py does). Each scenario is run twice from the same state, through
the hook and straight into stock's allocator, and compared:

1. the budget fits: the hook changes nothing (the same slots, the same memory as stock's);
2. a stock-only kit (every track a stock machine's): no check at all, stock's result exactly (the setting's job too);
3. the setting off: stock's result exactly;
4. the budget full: the note steals a held voice (the oldest, by stock's own STEAL), never a free slot, and the free
   slots are back in the live pool afterwards;
5. a heavy voice replacing light ones: one stolen and the next oldest released (load_keyups);
6. a track with reserved voices: the steal stays inside its own slots;
7. a chord in one tick: the second note never takes the first's slot;
8. the interrupt's stack: the deepest our code goes below the hook's entry (load_sp_min).
Exit 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

SNAP = "/root/dn2-snapshots/Digitone_II_OS1.11/ui1200M.snap"
ALLOC = 0x4002A6A2
STAGING, LIVE = 0x4059DA34, 0x4059D96C
VOICES, HELD, TICK, DUE = 0x40288304, 0x4059DD1C, 0x4059DB04, 0x4059DAFC
KIT_PTR = 0x800052A0
STACK, SCRATCH = 0x44700000, 0x44710000
from unicorn.m68k_const import UC_M68K_REG_A7 as SP_REG  # noqa: E402  (digikit's unicorn: the check's stack)
OK = []
NAMES = ['load_voice', 'load_stock', 'load_fx', 'load_off', 'load_checks', 'load_over', 'load_keyups', 'load_sp_min', 'load_last_sum', 'load_last_need']   # csrc/load/load.c's state (cpage LOAD_ENTRIES)


def check(name, ok, detail=""):
    OK.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


class Emu:
    def __init__(self, snapshot):
        from emu.longrun import build
        self.m, *_ = build(snapshot, unblock=True, softfloat=True, bitmap=True, dsp=True, weakptr=False,
                           slc=True, deferred_components=("timers",))
        self.uc = self.m.uc
        self.ret = STACK + 0x800

    def write(self, va, data):
        from unicorn import UC_PROT_ALL, UcError
        if hasattr(self.m, "write"):
            try:
                self.m.write(va, bytes(data))
                return
            except Exception:              # (outside the machine's map: unicorn's own pages below)
                pass
        try:
            self.uc.mem_write(va, bytes(data))
        except UcError:
            for page in range(va & ~0xFFFFF, va + len(data) + 0x100000, 0x100000):
                try:
                    self.uc.mem_map(page, 0x100000, UC_PROT_ALL)
                except UcError:
                    pass
            self.uc.mem_write(va, bytes(data))

    def read(self, va, n):
        return bytes(self.uc.mem_read(va, n))

    def r32(self, va):
        return struct.unpack(">I", self.read(va, 4))[0]

    def w32(self, va, v):
        self.write(va, struct.pack(">I", v & 0xFFFFFFFF))

    def w16(self, va, v):
        self.write(va, struct.pack(">H", v & 0xFFFF))

    def call(self, fn, *args, a6=0):
        """enter FN as a jsr would, interrupts masked; -> (d0, d1)"""
        from unicorn.m68k_const import (UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D1,
                                        UC_M68K_REG_SR)
        frame = struct.pack(">I", self.ret) + b"".join(struct.pack(">I", a & 0xFFFFFFFF) for a in args)
        self.write(STACK, frame)
        self.uc.reg_write(UC_M68K_REG_A7, STACK)
        self.uc.reg_write(UC_M68K_REG_A6, a6)
        sr = self.uc.reg_read(UC_M68K_REG_SR)
        self.uc.reg_write(UC_M68K_REG_SR, (sr & ~0x0700) | 0x2700)
        try:
            self.uc.emu_start(fn, self.ret, count=5_000_000)
            return self.uc.reg_read(UC_M68K_REG_D0), self.uc.reg_read(UC_M68K_REG_D1)
        finally:
            self.uc.reg_write(UC_M68K_REG_SR, sr)

    def save(self, spans):
        return [(va, self.read(va, n)) for va, n in spans]

    def restore(self, saved):
        for va, data in saved:
            self.write(va, data)


# stock's allocator reverses bits (BITREV Dn, 0x00c0 + n) before its FF1s: digikit emulates FF1 (and MOVEC) but not
# BITREV, so every one in the allocator (objdump of 1.12 0x4002a400..0x4002b300) is done here, as the core does it
BITREV_SITES = (0x4002A730, 0x4002A962, 0x4002A9C8, 0x4002AA02, 0x4002AA36, 0x4002AA80, 0x4002AC4C, 0x4002ACA0,
                0x4002AD12, 0x4002AD98, 0x4002B00C, 0x4002B028)


def bitrev_hooks(e: Emu) -> None:
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    dregs = [getattr(K, f"UC_M68K_REG_D{k}") for k in range(8)]

    def hook(uc, addr, size, data):
        op = struct.unpack(">H", bytes(uc.mem_read(addr, 2)))[0]
        assert op & 0xFFF8 == 0x00C0, hex(op)
        r = dregs[op & 7]
        v = uc.reg_read(r) & 0xFFFFFFFF
        uc.reg_write(r, int(f"{v:032b}"[::-1], 2))
        uc.reg_write(K.UC_M68K_REG_PC, addr + 2)
    for va in BITREV_SITES:
        e.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)


def install(e: Emu) -> dict:
    """the build's MAIN OS edits and chunks (the platform loader's copies) over the snapshot; -> the C symbols"""
    from dnfw.mods import waverider as W
    stock = open(os.path.join(os.environ["DT2_SECTIONS"], "section_3_MAIN_OS.bin"), "rb").read()
    built = W._main_os(stock)
    n = 0
    i = 0
    while i < len(stock):
        if built[i] != stock[i]:
            j = i
            while j < len(stock) and built[j] != stock[j]:
                j += 1
            e.write(0x40000400 + i, built[i:j])
            n += 1
            i = j
        else:
            i += 1
    for load, code, _what in W._chunks():
        e.write(load, code)
    if hasattr(e.m, "flush"):
        e.m.flush()
    print(f"  installed {n} edited runs and {len(W._chunks())} chunks", flush=True)
    return {**W.SPEC["layout"], **W.SPEC["c_text_symbols"]}


SPANS = [(STAGING, 0xC8), (LIVE, 0xC8), (VOICES, 20 * 16), (0x40288444, 1036 * 16), (0x4059DB00, 0x220),
         (0x4059DD0C, 0x14), (0x80005220, 64), (0x80005260, 64), (0x80005348, 4), (0x4059D8A8, 4)]
RESET = 0x4002A4D2                            # the allocator's reset: tables cleared, tick 0


class Kit:
    """an allocator state built by stock itself: reset, the masks, then notes played one tick each"""

    def __init__(self, e, sym, cost, stock=(), off=0, reserve=None):
        self.e, self.sym = e, sym
        e.call(RESET)
        pool, masks = 0xFFFF, [0] * 16
        for t, m in (reserve or {}).items():
            masks[t] = m
            pool &= ~m
        blk = bytearray(0xC8)
        struct.pack_into(">I", blk, 0, pool)
        for t in range(16):
            struct.pack_into(">I", blk, 4 + 4 * t, masks[t])
            blk[0x44 + t] = 1 if masks[t] else 0
            blk[0x94 + t] = 1
        e.write(STAGING, blk)
        e.write(LIVE, blk)
        e.w32(DUE, 1)
        for t in range(16):
            e.w16(sym["load_voice"] + 2 * t, 0 if t in stock else cost[t])
            e.w16(sym["load_stock"] + 2 * t, cost[t] if t in stock else 0)
        e.w32(sym["load_fx"], 0)
        e.write(sym["load_off"], bytes([off]))
        e.w32(sym["load_sp_min"], 0xFFFFFFFF)

    def play(self, t, n, hook=True, new_tick=True):
        """a note-on on track T, note N, in a new tick (or this one): -> the slots given; they stay held"""
        if new_tick:
            self.e.w32(DUE, 1)
        return note(self.e, self.sym, t, n, hook)[0]


def note(e: Emu, sym, t, n=64, via_hook=True):
    """the ISR's note-on call for track T: -> (slots given, older voices, a6 frame)"""
    kit = e.r32(KIT_PTR)
    frame = SCRATCH + 0x400
    e.write(frame - 0x100, bytes(0x100))
    args = (t, n, 1, 0xF, SCRATCH, 0, 0, 0, kit + 52 + 1163 * t)
    d0, d1 = e.call(sym["load_alloc_hook"] if via_hook else ALLOC, *args, a6=frame)
    return d1, d0, frame


def counters(e, sym):
    return {k: e.r32(sym["load_" + k]) for k in ("checks", "over", "keyups", "sp_min", "last_sum", "last_need")}


def twin(e, sym, build, t, n):
    """BUILD() makes a Kit state; the next note on it through the hook and through stock's allocator alone: ->
    (hook's slots, stock's, memory equal)"""
    snap = e.save(SPANS)
    k = build()
    base = e.save(SPANS)
    got = k.play(t, n, True)
    mh = e.save(SPANS)
    e.restore(base)
    ref = k.play(t, n, False)
    ms = e.save(SPANS)
    e.restore(snap)
    return got, ref, mh == ms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=SNAP)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    e = Emu(a.snapshot)
    sym = install(e)
    bitrev_hooks(e)
    res = {}

    def kit(cost, notes, **kw):
        def build():
            k = Kit(e, sym, cost, **kw)
            for tr, nn in notes:
                k.play(tr, nn, hook=False)          # the kit's sounding voices, as stock gave them
            return k
        return build
    # 1. fits: 2 light voices, a light note
    got, ref, same = twin(e, sym, kit([8000] * 16, [(0, 60), (0, 62)]), 2, 64)
    check("1 the budget fits: the same slots and memory as stock's", got == ref and same, f"{got:#06x} / {ref:#06x}")
    # 2. a stock-only kit, heavy: no check at all
    c0 = counters(e, sym)["checks"]
    got, ref, same = twin(e, sym, kit([30000] * 16, [(t % 4, 40 + t) for t in range(15)], stock=set(range(16))), 1, 90)
    check("2 a stock-only kit: stock's result exactly, no check made",
          got == ref and same and counters(e, sym)["checks"] == c0, f"{got:#06x} / {ref:#06x}")
    # 3. the setting off, over budget: stock's result
    got, ref, same = twin(e, sym, kit([40000] * 16, [(0, 40 + k) for k in range(8)], off=1), 1, 90)
    check("3 VOICE BUDGET off: stock's result exactly", got == ref and same, f"{got:#06x} / {ref:#06x}")
    # 4. full: 8 voices of 35,000 held (280,000); a ninth would be 315,000: it steals a held voice, stock alone a free one
    eight = [(0, 40 + k) for k in range(8)]
    build4 = kit([35000] * 16, eight)
    snap = e.save(SPANS)
    k = build4()
    held = e.r32(HELD)
    o0 = counters(e, sym)["over"]
    got = k.play(1, 90, True)
    pool = e.r32(LIVE)
    e.restore(snap)
    k = build4()
    ref = k.play(1, 90, False)
    e.restore(snap)
    check("4 the budget full: the note steals a held voice, stock alone takes a free slot",
          got and not (got & ~held) and ref and not (ref & held) and counters(e, sym)["over"] == o0 + 1,
          f"held {held:#06x}: hook {got:#06x}, stock {ref:#06x}")
    check("4 ... the free slots are back in the live pool", (pool | held) & 0xFFFF == 0xFFFF & ~0 or
          (pool & ~held & 0xFFFF) == (0xFFFF & ~held), f"live pool {pool:#06x}")
    res["full"] = counters(e, sym)
    # 5. heavy replaces light: 14 voices of 20,000 (280,000), a 50,000 note: one stolen, one more released
    cost5 = [20000] * 16
    cost5[1] = 50000
    snap = e.save(SPANS)
    k = kit(cost5, [(0, 30 + k) for k in range(14)])()
    base5 = e.save(SPANS)
    held = e.r32(HELD)
    k0 = counters(e, sym)["keyups"]
    lowest = {"sp": STACK}

    def low(uc, addr, size, data):
        sp = uc.reg_read(SP_REG)
        if sp < lowest["sp"]:
            lowest["sp"] = sp
    from unicorn import UC_HOOK_CODE
    hk = e.uc.hook_add(UC_HOOK_CODE, low)
    got = k.play(1, 90, True)
    deep_hook = STACK - lowest["sp"]
    held_after = e.r32(HELD)
    c = counters(e, sym)
    e.restore(base5)
    lowest["sp"] = STACK
    k.play(1, 90, False)
    deep_stock = STACK - lowest["sp"]
    e.uc.hook_del(hk)
    e.restore(snap)
    check("5 a heavy voice replacing light ones: one stolen, the next oldest released",
          got and not (got & ~held) and c["keyups"] == k0 + 1 and bin(held_after).count("1") == bin(held).count("1") - 1,
          f"took {got:#06x}, released {c['keyups'] - k0}, held {bin(held).count('1')} -> {bin(held_after).count('1')}")
    # 6. a track with reserved voices (track 1: slots 12..15), all four held: the steal stays in them
    rsv = {1: 0xF000}
    snap = e.save(SPANS)
    k = kit([40000] * 16, [(1, 40 + k) for k in range(4)] + [(0, 60 + k) for k in range(3)], reserve=rsv)()
    got = k.play(1, 90, True)
    e.restore(snap)
    check("6 a track with reserved voices steals inside its own", got and not (got & ~0xF000), f"took {got:#06x}")
    # 7. a chord in one tick, over budget: the second note never takes the first's slot
    snap = e.save(SPANS)
    k = build4()
    first = k.play(1, 90, True)
    second = k.play(1, 93, True, new_tick=False)
    e.restore(snap)
    check("7 a chord in one tick: the second note takes another slot", first and second and not (first & second),
          f"{first:#06x} then {second:#06x}")
    # 8. the stack: the deepest the note-on call goes below its entry, through the hook (heavy note: load_pre, stock's
    # allocator, load_post and stock's key-up) against stock's allocator alone on the same state
    check("8 the interrupt's stack: the hook path's depth measured, within 256 bytes of stock's",
          deep_hook - deep_stock <= 256, f"hook {deep_hook} B, stock alone {deep_stock} B, more {deep_hook - deep_stock} B")
    res["stack_depth"] = {"hook": deep_hook, "stock": deep_stock}
    res["pass"] = all(OK)
    print(("PASS" if all(OK) else "FAIL") + f": {sum(OK)} of {len(OK)} checks")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, indent=1))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
