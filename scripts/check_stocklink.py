"""csrc/stocklink against stock: the same bytes, under Unicorn (the coupled emulator never reaches this code: the
DSPI never reports a transfer done there, and no USB host streams).

    python scripts/check_stocklink.py dev SECTION_3 BASE_CODE.json OURS_CODE.json {CHECK|all} [--n N] [--seed S]
                                      [--negative]
    python scripts/check_stocklink.py gate STOCK_SECTION_3 BUILD_SECTION_3 CODE.json [--seed S]   (the gate's linkfast)

dev: two machines, stock 1.12's MAIN OS with BASE's waverider edits and chunks (main, before csrc/stocklink), and the
same with OURS'. gate: the build's own section 3 (every mod's edits), and the same with each stocklink site
(dnfw.waverider.coldfire STOCKLINK_SITES) put back to stock's bytes, both with CODE's chunks; every site the build
edits must be covered by a check that runs, with its negative controls; a build with no site edited
(DN2_STOCK_LINK_FAST off) has nothing to prove. Each trial seeds both machines with the same random memory, runs the
same stock entry in both, and compares: every byte either wrote (outside the waverider chunks, whose layouts may
differ, and the stack below the final sp: dead), the ordered list of peripheral writes (0xec000000.., 0xfc000000..),
the registers the code after reads, and for the MAC the accumulator, its extension and MACSR. It counts the
instructions each side ran, and the uncached (DDR alias) loads and stores.

  fill    0x400cf922 (the SPI frame routine, the staging fill and the reply copy) with random frames, staging,
          lengths, boot lengths (a DSP restart sets it again), DSPI states, reply copies or none
  rcopy   the reply copy alone: stock's memcpy against skl_rcopy, random areas, lengths and overlaps; every register
  tx      the audio interrupt's transmit-fill part (0x40025f56 .. after the smp_tdm hook) over runs of frames: modes
          5, 6 (Overbridge) and others switched at random (also between the two mode reads), the USB-in flag and its
          slot bytes (outside 0..15 too), packets sent or not, halves alternating or not, the interrupt re-installed
          after garbage in both halves (the service interrupt), the SSI init's clear; the halves after every frame
  obbuild the mode-6 packet builder 0x40003118 (csrc/obfast): random receive halves, records, packet state and
          USB controller registers, three frames a trial, overlapping areas too
  obin    the Overbridge input 0x40003376 (csrc/obfast): random USB receive descriptor chains and buffers, the state,
          three frames a trial, a buffer over the transmit half too
  rxclr   mode 6's receive-half clear (0x400279e8 .. 0x40027a10, csrc/stocklink skl_rxclr): the half H (2 KB) and
          the 84 B at 0x800053c0, random halves, SRAM and H; every register, the flags, the arguments left pushed
          (obin also covers csrc/obfast obf_clr, the Overbridge input's transmit-half clear, 2026-11-21)
  usbout  mode 5's USB out (0x400276a2 .. 0x40027768): the stream flag, mono flag and both channel bytes over their
          whole range, both halves, random receive halves and reply records, a random accumulator and MACSR mode

--negative runs each with deliberate faults in ours and must find a difference (else the check proves nothing).
Exit 0 only if every trial matched (and every fault was found).
"""
from __future__ import annotations

import argparse
import json
import random
import struct

from unicorn import UC_ARCH_M68K, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MODE_BIG_ENDIAN, Uc
from unicorn.m68k_const import (UC_CPU_M68K_CFV4E, UC_M68K_REG_A0, UC_M68K_REG_A6, UC_M68K_REG_A7, UC_M68K_REG_D0,
                                UC_M68K_REG_PC, UC_M68K_REG_SR)

BASE = 0x40000400
DREG = [UC_M68K_REG_D0 + i for i in range(8)]
AREG = [UC_M68K_REG_A0 + i for i in range(8)]
SCRATCH = 0x47F00000                     # our harness code and the stack (inside the mapped RAM, no build uses it)
STACK_TOP = 0x47FF0000
FP_FRAME = STACK_TOP + 0x1000            # the interrupt's frame (fp), above the stacks
HALT = SCRATCH                           # a nop: every run stops here
SNIP = SCRATCH + 0x100                   # MAC snippets
PERIPH = ((0xEC000000, 0xEC100000), (0xFC000000, 0xFD000000))
RAM = ((0x40000000, 0x48000000), (0x4E000000, 0x50000000), (0x80000000, 0x80010000))
TX, RX = 0x4E6E8100, 0x4E6E7100


class Machine:
    def __init__(self, img: bytes, code: dict, name: str):
        """IMG: section 3 as this machine runs it; CODE: the waverider chunks loaded beside it"""
        self.name, self.code = name, code
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        for lo, hi in RAM + PERIPH:
            uc.mem_map(lo, hi - lo)
        uc.mem_write(BASE, bytes(img))
        self.chunks = []
        for k in ("chunk", "c_chunk", "machines_chunk", "flt_chunk"):
            if k in code:
                b = bytes.fromhex(code[k]["code"])
                uc.mem_write(code[k]["load"], b)
                self.chunks.append((code[k]["load"], code[k]["load"] + len(b) + 0x40000))   # + its BSS (generous)
        uc.mem_write(HALT, b"\x4e\x71" * 8)
        # MAC snippets: set acc0 = d1, macsr = d2 (then halt); read acc0 -> d0, macsr -> d1, accext01 -> d3
        uc.mem_write(SNIP, bytes.fromhex("a101a902") + b"\x4e\xf9" + struct.pack(">I", HALT))
        uc.mem_write(SNIP + 0x20, bytes.fromhex("a180a981ab83") + b"\x4e\xf9" + struct.pack(">I", HALT))
        self.writes, self.pwrites, self.count, self.unc_w, self.unc_r = {}, [], 0, 0, 0
        self.hooks = {}
        uc.hook_add(UC_HOOK_MEM_WRITE, self._w)
        uc.hook_add(UC_HOOK_MEM_READ, self._r, begin=0x4E000000, end=0x4FFFFFFF)
        uc.hook_add(UC_HOOK_CODE, self._c)

    def sym(self, s):
        return self.code["c_text_symbols"].get(s) or self.code["layout"][s]

    def _w(self, uc, access, addr, size, value, data):
        for lo, hi in PERIPH:
            if lo <= addr < hi:
                self.pwrites.append((addr, size, value & ((1 << 8 * size) - 1)))
                return
        if 0x4E000000 <= addr < 0x50000000:
            self.unc_w += 1                              # an uncached (DDR alias) store
        for i in range(size):
            self.writes[addr + i] = 1

    def _r(self, uc, access, addr, size, value, data):
        self.unc_r += 1                                  # an uncached (DDR alias) load

    def _c(self, uc, addr, size, data):
        self.count += 1
        h = self.hooks.get(addr)
        if h:
            h(self)

    def run(self, start, until, limit=5_000_000):
        try:
            self.uc.emu_start(start, until, count=limit)
        except Exception as e:                           # noqa: BLE001  (where, for the report)
            pc = self.uc.reg_read(UC_M68K_REG_PC)
            regs = " ".join(f"{v:#x}" for v in self.regs())
            raise RuntimeError(f"{self.name}: {e} at pc {pc:#x} (from {start:#x}); d0-d7 a0-a7 {regs}") from e
        pc = self.uc.reg_read(UC_M68K_REG_PC)
        assert pc == until, f"{self.name}: stopped at {pc:#x}, not {until:#x}"

    def ret(self):
        """emulate an rts from the hook at a function's entry"""
        sp = self.uc.reg_read(UC_M68K_REG_A7)
        ra = struct.unpack(">I", self.uc.mem_read(sp, 4))[0]
        self.uc.reg_write(UC_M68K_REG_A7, sp + 4)
        self.uc.reg_write(UC_M68K_REG_PC, ra)

    def long(self, a):
        return struct.unpack(">I", self.uc.mem_read(a, 4))[0]

    def put(self, a, b):
        self.uc.mem_write(a, b)

    def regs(self):
        return [self.uc.reg_read(r) & 0xFFFFFFFF for r in DREG + AREG]

    def mac(self):
        self.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x100)
        keep = self.regs()
        self.run(SNIP + 0x20, HALT)
        out = (self.uc.reg_read(DREG[0]) & 0xFFFFFFFF, self.uc.reg_read(DREG[1]) & 0xFFFFFFFF,
               self.uc.reg_read(DREG[3]) & 0xFFFFFFFF)
        for r, v in zip(DREG + AREG, keep):
            self.uc.reg_write(r, v)
        return out

    def set_mac(self, acc, macsr):
        self.uc.reg_write(DREG[1], acc)
        self.uc.reg_write(DREG[2], macsr)
        self.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x100)
        self.run(SNIP, HALT)

    def begin(self):
        self.writes, self.pwrites, self.count, self.unc_w, self.unc_r = {}, [], 0, 0, 0

    def ours(self, a):
        return any(lo <= a < hi for lo, hi in self.chunks)


def applied(sec3: bytes, code: dict) -> bytes:
    """stock's section 3 with CODE's waverider edits"""
    img = bytearray(sec3)
    for e in code["edits"]:
        at = e["va"] - BASE
        old, new = bytes.fromhex(e["stock"]), bytes.fromhex(e["new"])
        assert bytes(img[at:at + len(old)]) == old, f"{e['va']:#x} not stock"
        img[at:at + len(new)] = new
    return bytes(img)


class Pair:
    def __init__(self, img_base, code_base, img_ours, code_ours):
        self.args = (img_base, code_base, img_ours, code_ours)
        self.m = [Machine(img_base, code_base, "main"), Machine(img_ours, code_ours, "ours")]

    def fresh(self):
        return Pair(*self.args)

    def both(self, f):
        return [f(m) for m in self.m]

    def put(self, a, b):
        for m in self.m:
            m.put(a, b)

    def compare(self, what, regs_skip=(), sp_floor=None):
        """-> a list of differences (empty: the same)"""
        a, b = self.m
        diffs = []
        addrs = sorted(x for x in set(a.writes) | set(b.writes) if not a.ours(x) and not b.ours(x)
                       and not (sp_floor is not None and SCRATCH <= x < sp_floor))
        # the bytes either side wrote, read back from both (runs of consecutive addresses)
        i = 0
        while i < len(addrs):
            j = i
            while j + 1 < len(addrs) and addrs[j + 1] == addrs[j] + 1 and j - i < 4096:
                j += 1
            lo, n = addrs[i], addrs[j] - addrs[i] + 1
            x, y = bytes(a.uc.mem_read(lo, n)), bytes(b.uc.mem_read(lo, n))
            if x != y:
                k = next(t for t in range(n) if x[t] != y[t])
                diffs.append(f"{what}: memory {lo + k:#x}: main {x[k]:02x} ours {y[k]:02x}")
                break
            i = j + 1
        if a.pwrites != b.pwrites:
            diffs.append(f"{what}: peripheral writes differ ({len(a.pwrites)} / {len(b.pwrites)}): "
                         f"{next((p, q) for p, q in zip(a.pwrites + [None], b.pwrites + [None]) if p != q)}")
        ra, rb = a.regs(), b.regs()
        names = [f"d{i}" for i in range(8)] + [f"a{i}" for i in range(8)]
        for n_, x, y in zip(names, ra, rb):
            if n_ not in regs_skip and x != y:
                diffs.append(f"{what}: {n_} main {x:#x} ours {y:#x}")
        return diffs


CHECKS: dict = {}                                        # name -> (check, its negative controls)


def rbytes(rng, n):
    return rng.getrandbits(8 * n).to_bytes(n, "big") if n else b""


# ---- 1. the SPI frame routine --------------------------------------------------------------------------------
def check_fill(p: Pair, rng, n, neg=False):
    bad, counts = 0, [0, 0, 0, 0, 0]
    if neg:                                              # a fault: the last entry's command left as 0x8001
        o = p.m[1]
        at = o.sym("skl_fill")
        code = bytes(o.uc.mem_read(at, 0x200))
        k = code.find(bytes.fromhex("303c0801"))         # move.w #0x0801,%d0
        o.put(at + k, bytes.fromhex("303c8001"))
    for t in range(n):
        p.put(0x80000000, rbytes(rng, 0x10000))          # the SRAM: frame, staging, reply buffers
        boot = rng.choice([2748, 2748, 2748, 2800, 2900, 2688, 1000, 0, rng.randrange(0, 4000)])
        p.put(0x42441958, struct.pack(">I", boot))
        sr = rng.getrandbits(32) | (1 << 28) if rng.random() < 0.85 else rng.getrandbits(32) & ~(1 << 28)
        p.put(0xEC03802C, struct.pack(">I", sr))
        p.put(0xEC038000, rbytes(rng, 4))
        ln = rng.choice([2688, 2688, 2688, 2688, 2800, 2000, 1344, 0, rng.randrange(0, 2801)])
        args = (ln, 0x80005E60, rng.choice([2748, 0, 100]), rng.choice([0x800053A4, 0]))
        for m in p.m:
            m.begin()
            sp = STACK_TOP - 0x1000
            m.put(sp, struct.pack(">IIIII", HALT, *args))
            for r in DREG + AREG[:6]:
                m.uc.reg_write(r, 0x11110000 + r)
            m.uc.reg_write(UC_M68K_REG_A6, FP_FRAME)
            m.uc.reg_write(UC_M68K_REG_A7, sp)
            m.run(0x400CF922, HALT)
        d = p.compare(f"fill trial {t} (len {ln}, boot {boot}, done {sr >> 28 & 1})", regs_skip=("d1", "a0", "a1"),
                      sp_floor=STACK_TOP - 0x1000)
        if d:
            bad += 1
            if bad <= 5:
                print("  " + "\n  ".join(d))
        if ln == 2688 and boot == 2748 and sr >> 28 & 1 and args[3]:
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
            counts[3] += p.m[0].unc_w + p.m[0].unc_r
            counts[4] += p.m[1].unc_w + p.m[1].unc_r
    return bad, counts


CHECKS["fill"] = (check_fill, [True])


def check_rcopy(p: Pair, rng, n, neg=False):
    bad, counts = 0, [0, 0, 0, 0, 0]
    o = p.m[1]
    if neg:                                              # a fault: the last byte of a copy not made
        at = o.sym("skl_rcopy")
        code = bytes(o.uc.mem_read(at, 0x100))
        k = code.find(bytes.fromhex("12d8"))             # move.b (%a0)+,(%a1)+
        o.put(at + k, bytes.fromhex("5288"))             # addq.l #1,%a0 (the store dropped)
    for t in range(n):
        p.put(0x80000000, rbytes(rng, 0x10000))
        n_ = rng.choice([2748, 2748, 2748, 0, 1, 31, 32, 33, 35, 64, 100, 2749, 2800, rng.randrange(0, 4000)])
        src = 0x80000000 + rng.randrange(0, 0x3000) * rng.choice([1, 1, 2]) // 2 * 2 + rng.choice([0, 0, 1, 2, 3])
        dst = rng.choice([src + rng.randrange(-64, 65), 0x80000000 + rng.randrange(0, 0x7000),
                          0x80000000 + rng.randrange(0, 0x7000) + rng.choice([1, 2, 3])])
        dst = max(dst, 0x80000000)                       # (inside the SRAM: an overlap below its start is not one)
        if rng.random() < 0.4:
            src, dst = 0x80001A20, 0x800053A4
        for m, entry in zip(p.m, (0x40134770, p.m[1].sym("skl_rcopy"))):
            m.begin()
            sp = STACK_TOP - 0x1000
            m.put(sp, struct.pack(">IIII", HALT, dst, src, n_))
            for r in DREG + AREG[:7]:
                m.uc.reg_write(r, 0x44440000 + r)
            m.uc.reg_write(UC_M68K_REG_A7, sp)
            m.run(entry, HALT)
        d = p.compare(f"rcopy trial {t} (dst {dst:#x}, src {src:#x}, n {n_})", sp_floor=STACK_TOP - 0x1000)
        if d:
            bad += 1
            if bad <= 5:
                print("  " + "\n  ".join(d))
        if n_ == 2748 and dst == 0x800053A4:
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
    return bad, counts


CHECKS["rcopy"] = (check_rcopy, [True])


# ---- 2. the transmit half --------------------------------------------------------------------------------------
class TxWorld:
    """the scripted parts every frame: 0x40003ede (USB-in), 0x40003376 (Overbridge in), 0x4013831c, smp_tdm"""
    def __init__(self, p: Pair, rng):
        self.p, self.rng, self.plan = p, rng, {}
        for m in p.m:
            m.hooks[0x40003EDE] = self.usbin
            m.hooks[0x40003376] = self.obin
            m.hooks[0x4013831C] = lambda m_: m_.ret()
            m.hooks[m.sym("smp_tdm")] = self.tdm

    def usbin(self, m):
        m.put(0x4664BF4C, self.plan["usbin"])
        if self.plan.get("mode2") is not None:
            m.put(0x4058F2A8, struct.pack(">I", self.plan["mode2"]))
        m.ret()

    def obin(self, m):
        sp = m.uc.reg_read(UC_M68K_REG_A7)
        half = m.long(sp + 4)
        for f, data in self.plan["ob"]:
            m.put(half + 64 * f, data)
        m.ret()

    def tdm(self, m):
        if self.plan["send"]:
            h = self.plan["h"]
            for i, u in enumerate(self.plan["packet"]):
                m.put(TX + (h << 11) + 4 * (16 * (i >> 3) + 8 + (i & 7)), struct.pack(">I", u))
            s = m.sym("smp_tdm_sent")
            m.put(s, struct.pack(">I", (m.long(s) + 1) & 0xFFFFFFFF))
        m.ret()


def check_tx(p: Pair, rng, frames, neg=None):
    w = TxWorld(p, rng)
    o = p.m[1]
    if neg == "after":                                   # a fault: the deferred clears never made
        at = o.sym("skl_tx_after")
        o.put(at, b"\x4e\x75")
    elif neg == "install":                               # a fault: the re-install vouches for the halves
        at = o.sym("skl_isr_install")
        o.put(at + 2, b"\x4e\x71" * 3)
    elif neg == "column":                                # a fault: a column's 32 clears start one frame late
        code = bytes(o.uc.mem_read(o.sym("skl_mode5") - 0x400, 0x800))
        k = code.find(bytes.fromhex("2080214000402140"))  # move.l %d0,(%a0) ; move.l %d0,64(%a0) ; ...
        if k < 0:
            raise SystemExit("negative control: the clear's pattern not found")
        o.put(o.sym("skl_mode5") - 0x400 + k, b"\x4e\x71")
    bad, counts, h = 0, [0, 0, 0, 0, 0], 0
    p.put(TX, rbytes(rng, 0x1000))                       # power-on: whatever the halves hold
    for t in range(frames):
        ev = rng.random()
        if ev < 0.03:                                    # the service interrupt wrote both halves, then the audio
            p.put(TX, rbytes(rng, 0x1000))              # interrupt is installed again
            for m in p.m:
                m.begin()
                m.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x100)
                m.run(0x40025576, 0x40025582)
        elif ev < 0.05:                                  # the SSI's init clears both halves
            p.put(TX, bytes(0x1000))
        h = h ^ 1 if rng.random() < 0.95 else h
        mode = rng.choices([5, 6, 4, 0, 7], [70, 12, 8, 5, 5])[0]
        flag = rng.random() < 0.6
        a = rng.choice([0, 1, 2, 3, 0, 1, 6, 7, 8, 15, 14, 9]) if rng.random() < 0.95 else rng.randrange(-128, 128)
        b = rng.choice([1, 0, 2, 3, 1, 7, 8, 15, 12]) if rng.random() < 0.95 else rng.randrange(-128, 128)
        w.plan = {"h": h, "usbin": rbytes(rng, 256), "send": rng.random() < 0.4,
                  "packet": [rng.getrandbits(32) for _ in range(256)],
                  "mode2": rng.choice([5, 6, 4]) if rng.random() < 0.05 else None,
                  "ob": [(f, rbytes(rng, 32 if rng.random() < 0.7 else 64)) for f in range(32) if rng.random() < 0.5]}
        p.put(0x4058F2A8, struct.pack(">I", mode))
        p.put(0x80005366, bytes([flag, a & 0xFF, b & 0xFF]))
        p.put(0x4058F884, rbytes(rng, 4))
        for m in p.m:
            m.begin()
            m.put(FP_FRAME - 56, struct.pack(">I", h))
            m.uc.reg_write(UC_M68K_REG_A6, FP_FRAME)
            m.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x2000)
            for r in DREG + AREG[:6]:
                m.uc.reg_write(r, 0x22220000 + r)
            m.run(0x40025F56, 0x400260A0)
        d = p.compare(f"tx frame {t} (h {h}, mode {mode}, flag {flag:d}, A {a}, B {b}, send {w.plan['send']:d})",
                      sp_floor=STACK_TOP - 0x2000)
        x, y = (bytes(m.uc.mem_read(TX, 0x1000)) for m in p.m)
        if x != y:
            k = next(i for i in range(0x1000) if x[i] != y[i])
            d.append(f"tx frame {t}: transmit halves differ at {TX + k:#x}")
        if d:
            bad += 1
            if bad <= 5:
                print("  " + "\n  ".join(d))
            p.m[1].put(TX, x)                            # carry on from main's halves (one fault, one report)
        if mode == 5:
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
            counts[3] += p.m[0].unc_w + p.m[0].unc_r
            counts[4] += p.m[1].unc_w + p.m[1].unc_r
    return bad, counts


CHECKS["tx"] = (check_tx, ["after", "install", "column"])


# ---- 3. mode 5's USB out --------------------------------------------------------------------------------------
FIXED = None                                             # --usb A,B,MONO: one setting only (for its counts)


def check_usbout(p: Pair, rng, n, neg=False):
    bad, counts = 0, [0, 0, 0, 0, 0]
    if neg:                                              # a fault: loop 2 reads A's value in place of B's
        o = p.m[1]
        at = o.sym("skl_usbout")
        code = bytes(o.uc.mem_read(at, 0x200))
        k = code.find(bytes.fromhex("202b002c"))         # move.l F_IX+8(%a3),%d0
        o.put(at + k, bytes.fromhex("202b0024"))         # ... F_IX+0
    for t in range(n):
        p.put(RX, rbytes(rng, 0x1000))
        p.put(0x800053A4, rbytes(rng, 2748))
        h = rng.randrange(2)
        stream = rng.random() < 0.9
        mono = rng.random() < 0.4
        if rng.random() < 0.8:
            a = rng.choice([0, 0, 0, 1, 2, 4, 6, 12, 13, 14, 15, 20, 40])
            b = rng.choice([a + 1, a + 1, a, a + 2, a - 1, 1, 0, 13, 14, 15, 16])
        else:
            a, b = rng.randrange(-128, 128), rng.randrange(-128, 128)
        b = max(-128, min(127, b))
        if FIXED:
            a, b, mono, stream = FIXED[0], FIXED[1], FIXED[2], True
        p.put(0x80005362, bytes([stream * rng.randrange(1, 256), mono * rng.randrange(1, 256), a & 0xFF, b & 0xFF]))
        p.put(0x4058F2A8, struct.pack(">I", 5))
        acc = rng.getrandbits(32)
        macsr = rng.choice([0x20, 0x20, 0x20, 0x00, 0x60, 0xA0, 0x30, 0x40])
        for m in p.m:
            m.begin()
            m.set_mac(acc, macsr)
            m.begin()
            m.put(FP_FRAME - 56, struct.pack(">I", h))
            m.uc.reg_write(UC_M68K_REG_A6, FP_FRAME)
            m.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x2000)
            for r in DREG + AREG[:6]:
                m.uc.reg_write(r, 0x33330000 + r)
            m.run(0x400276A2, 0x40027768)
        d = p.compare(f"usbout trial {t} (stream {stream:d}, mono {mono:d}, A {a}, B {b}, h {h}, macsr {macsr:#x})",
                      regs_skip=("d6",), sp_floor=STACK_TOP - 0x2000)
        ma, mb = p.m[0].mac(), p.m[1].mac()
        if ma != mb:
            d.append(f"usbout trial {t}: acc0/macsr/accext main {ma} ours {mb}")
        if d:
            bad += 1
            if bad <= 5:
                print("  " + "\n  ".join(d))
        if stream:
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
            counts[3] += p.m[0].unc_w + p.m[0].unc_r
            counts[4] += p.m[1].unc_w + p.m[1].unc_r
    return bad, counts


CHECKS["usbout"] = (check_usbout, [True])


# ---- csrc/obfast: the Overbridge path ------------------------------------------------------------------------
OBG = 0x40306000                                          # the Overbridge streaming state's globals (0x40306010..)


def ob_globals(p: Pair, rng):
    """the builder's and the input's state: random, in the ranges the code keeps it in (indices masked as it masks)"""
    p.put(OBG, bytes(0x300))                             # (pointers among them: set below, the rest 0)
    put = lambda a, v: p.put(a, struct.pack(">I", v & 0xFFFFFFFF))          # noqa: E731
    put(0x40306290, rng.getrandbits(32))
    put(0x40306040, rng.randrange(4))                   # (a ring of four, 0x40306050 + 128 x it)
    put(0x40306010, rng.getrandbits(32))
    put(0x4030629C, rng.random() < 0.95)
    put(0x40306284, rng.random() < 0.3)
    put(0x40306298, rng.random() < 0.85)
    put(0x4030625C, rng.random() < 0.3)
    for a in (0x4664BF48, 0x40306268, 0x40306258):
        put(a, rng.randrange(0, 4))
    put(0x40306278, rng.choice([0, 0, rng.randrange(-3, 41)]))
    cnt = rng.randrange(0, 7)
    put(0x40306024, cnt)
    put(0x40306020, 0x80008C00 + 1012 * rng.randrange(16) if cnt or rng.random() < 0.5 else 0)
    put(0x40306038, rng.randrange(16))
    put(0x4030603C, rng.randrange(32))
    put(0x40306034, rng.randrange(16))
    put(0x40306030, rng.randrange(16))
    p.put(0x4664BF0C, rbytes(rng, 4))
    # the input: a chain of USB receive descriptors (byte 7 0: filled), each with its buffer (byte 0 the frames)
    n = rng.randrange(1, 4)
    for i in range(n):
        d, buf = 0x80009F00 + 64 * i, 0x8000A400 + 0x400 * i
        if rng.random() < 0.25:                          # a buffer over the transmit half: the copy's areas overlap
            buf = TX + rng.choice([0, 0x800]) - 20 + 64 * rng.randrange(0, 4) + rng.randrange(-15, 16) * 2
        p.put(d + 7, bytes([0 if rng.random() < 0.9 else 0x80]))
        put(d + 48, buf)
        put(d + 52, 0x80009F00 + 64 * (i + 1) if i + 1 < n else 0)
        p.put(buf, bytes([rng.randrange(1, 41), rng.randrange(256)]))
        p.put(buf + 20, rbytes(rng, 40 * 32))
    put(0x40306264, 0x80009F00 if rng.random() < 0.95 else 0)
    put(0x40306260, 0x80009F00 + 64 * (n - 1))           # the chain's tail (0x40002eac appends there)
    put(0x40306294, rng.random() < 0.5)
    put(0x4030627C, rng.random() < 0.3)
    put(0x40306274, rng.randrange(0, 41))
    put(0x40306018, rng.randrange(0, 3))
    put(0x40306014, 0 if rng.random() < 0.8 else rng.randrange(-2, 10))   # (> 0: frames skipped, no copy)
    put(0x40306254, rng.random() < 0.3)
    put(0x40306250, rng.randrange(0, 20))
    p.put(0xFC0B0140, rbytes(rng, 16 * 4))               # the USB controller's registers (0xfc0b0140..)
    p.put(0x80000000, bytes(0x800))                      # the endpoints' queue heads (0x401d0a4c: 0x80000000 + ..):
    if rng.random() < 0.3:                               # empty, or one queued transfer descriptor in our area
        p.put(0x800001C0 + 48, struct.pack(">II", 0x80009E00, 0x80009E00))
        p.put(0x80009E00, struct.pack(">II", 1, rng.getrandbits(15)) + bytes(56))


def ob_patch(o: Machine, sym: str, find: str, put: str):
    at = o.sym(sym)
    code = bytes(o.uc.mem_read(at, 0x200))
    k = code.find(bytes.fromhex(find))
    if k < 0:
        raise SystemExit(f"negative control: {find} not found in {sym}")
    o.put(at + k, bytes.fromhex(put))


def ob_call(p: Pair, entry: int, args: tuple, tag: str):
    for m in p.m:
        m.begin()
        sp = STACK_TOP - 0x2000
        m.put(sp, struct.pack(">I" + "I" * len(args), HALT, *args))
        for r in DREG + AREG[:7]:
            m.uc.reg_write(r, 0x55550000 + r)
        m.uc.reg_write(UC_M68K_REG_SR, 0x2500)          # supervisor, the audio interrupt's mask
        m.uc.reg_write(UC_M68K_REG_A7, sp)
        m.run(entry, HALT)
    return p.compare(tag, sp_floor=STACK_TOP - 0x2000)


def check_obbuild(p: Pair, rng, n, neg=None):
    """the mode-6 packet builder 0x40003118 (args: the receive half, the records, a header source or 0, the frames),
    three frames a trial on the same state"""
    bad, counts = 0, [0, 0, 0, 0, 0]
    runs = ob_count(p.m[1], "obf_build_pair")
    if neg == "data":                                    # a fault: the records' last long not copied
        ob_patch(p.m[1], "obf_build_pair", "48e9003e0040", "48e9001e0040")
    elif neg == "overlap":                               # a fault: copy 1's overlap test never true
        ob_patch(p.m[1], "obf_build_pair", "0c8100000038", "0c8100000000")
    for t in range(n):
        p.put(0x80000000, rbytes(rng, 0x10000))
        p.put(RX, rbytes(rng, 0x1000))
        ob_globals(p, rng)
        for f in range(3):
            h = rng.randrange(2)
            buf = p.m[0].long(0x40306020) or 0x80008C00
            here = buf + 20 + 140 * p.m[0].long(0x40306024)  # where the next entry goes
            rec = 0x800053C0
            if rng.random() < 0.15:                      # records over the packet buffer: copy 2 overlaps
                rec = here + 56 + rng.randrange(-100, 100) * 2
            rx = RX + 0x800 * h
            if rng.random() < 0.1:                       # a receive frame over the packet buffer: copy 1 overlaps
                rx = here + rng.randrange(-60, 60) * 2
            hdr = rng.choice([0, 0, 0x80006000])
            d = ob_call(p, 0x40003118, (rx, rec, hdr, rng.choice([32, 32, 32, 7, 0, rng.randrange(0, 41)])),
                        f"obbuild trial {t} frame {f}")
            if d:
                bad += 1
                if bad <= 5:
                    print("  " + "\n  ".join(d))
                break
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
            counts[3] += p.m[0].unc_w + p.m[0].unc_r
            counts[4] += p.m[1].unc_w + p.m[1].unc_r
    print(f"  (obf_build_pair ran {runs[0]} times in these trials)", flush=True)
    return bad, counts


CHECKS["obbuild"] = (check_obbuild, ["data", "overlap"])


def ob_count(o: Machine, sym: str) -> list:
    """count the runs of our routine SYM (and so of the stock copies it stands for) in machine O"""
    n = [0]
    if sym in o.code.get("c_text_symbols", {}):
        o.hooks[o.sym(sym)] = lambda m: n.__setitem__(0, n[0] + 1)
    return n


def check_obin(p: Pair, rng, n, neg=None):
    """the Overbridge input 0x40003376 (args: the transmit half, a status pointer or 0, a position pointer or 0, the
    frames), three frames a trial on the same state"""
    bad, counts = 0, [0, 0, 0, 0, 0]
    runs = ob_count(p.m[1], "obf_in32")
    if neg == "data":                                    # a fault: a frame's last long not copied
        ob_patch(p.m[1], "obf_in32", "48d12c3e", "48d10c3e")
    elif neg == "overlap":                               # a fault: the overlap test never true
        ob_patch(p.m[1], "obf_in32", "0c8100000020", "0c8100000000")
    elif neg == "clear":                                 # a fault: (2026-11-21) obf_clr's first movem stores 7 longs
        ob_patch(p.m[1], "obf_clr", "48d000ff", "48d0007f")
    for t in range(n):
        p.put(0x80000000, rbytes(rng, 0x10000))
        p.put(TX, rbytes(rng, 0x1000))
        ob_globals(p, rng)
        for f in range(3):
            h = rng.randrange(2)
            args = (TX + 0x800 * h, rng.choice([0, 0x80006100]), rng.choice([0, 0x80006200]),
                    rng.choice([32, 32, 32, 7, 0, rng.randrange(0, 41)]))
            d = ob_call(p, 0x40003376, args, f"obin trial {t} frame {f}")
            if d:
                bad += 1
                if bad <= 5:
                    print("  " + "\n  ".join(d))
                break
            counts[0] += p.m[0].count
            counts[1] += p.m[1].count
            counts[2] += 1
            counts[3] += p.m[0].unc_w + p.m[0].unc_r
            counts[4] += p.m[1].unc_w + p.m[1].unc_r
    print(f"  (obf_in32 ran {runs[0]} times in these trials)", flush=True)
    return bad, counts


CHECKS["obin"] = (check_obin, ["data", "overlap", "clear"])


# ---- 8. mode 6's receive-half clear (skl_rxclr) ---------------------------------------------------------------
def check_rxclr(p: Pair, rng, n, neg=False):
    """0x400279e8 .. 0x40027a10: stock's two clears through jsr (%a2) (the receive half H, 2 KB; 84 B at
    0x800053c0) against skl_rxclr: random halves, SRAM and registers; every register, the four arguments left"""
    bad, counts = 0, [0, 0, 0, 0, 0]
    if neg:                                              # a fault: the 84 B's last long not cleared
        ob_patch(p.m[1], "skl_rxclr", "48e8001f0040", "48e8000f0040")
    for t in range(n):
        p.put(RX, rbytes(rng, 0x1000))
        p.put(0x80005000, rbytes(rng, 0x800))
        h = rng.choice([0, 1, 0, 1, 0, 1, 2, 3])
        for m in p.m:
            m.begin()
            m.put(FP_FRAME - 56, struct.pack(">I", h))
            m.uc.reg_write(UC_M68K_REG_SR, 0x2500)      # (first: a write of SR may switch the stack pointer)
            m.uc.reg_write(UC_M68K_REG_A6, FP_FRAME)
            m.uc.reg_write(UC_M68K_REG_A7, STACK_TOP - 0x2000)
            for r in DREG + AREG[:6]:
                m.uc.reg_write(r, 0x66660000 + r + 0x100 * t)
            m.run(0x400279E8, 0x40027A10)
        d = p.compare(f"rxclr trial {t} (h {h})", sp_floor=STACK_TOP - 0x2000 - 16)
        sa, sb = (m.uc.reg_read(UC_M68K_REG_SR) & 0x1F for m in p.m)
        if sa != sb:
            d.append(f"rxclr trial {t}: flags main {sa:#x} ours {sb:#x}")
        if d:
            bad += 1
            if bad <= 5:
                print("  " + "\n  ".join(d))
        counts[0] += p.m[0].count
        counts[1] += p.m[1].count
        counts[2] += 1
        counts[3] += p.m[0].unc_w + p.m[0].unc_r
        counts[4] += p.m[1].unc_w + p.m[1].unc_r
    return bad, counts


CHECKS["rxclr"] = (check_rxclr, [True])


# each stocklink site (dnfw.waverider.coldfire STOCKLINK_SITES, by symbol) -> the checks that prove it
SITE_CHECKS = {"skl_fill": ("fill",), "skl_rcopy": ("fill", "rcopy"), "skl_mode5": ("tx",), "skl_modex": ("tx",),
               "skl_isr_install": ("tx",), "skl_usbout": ("usbout",),
               "obf_build_pair": ("obbuild",), "obf_in32": ("obin",), "skl_rxclr": ("rxclr",), "obf_clr": ("obin",)}
GATE_N = {"fill": 600, "rcopy": 2000, "tx": 4000, "usbout": 800, "obbuild": 1500, "obin": 1500, "rxclr": 600}


def run_checks(make, names, n, seed, negative) -> bool:
    ok = True
    for what in names:
        fn, faults = CHECKS[what]
        rng = random.Random(seed)
        bad, counts = fn(make(), rng, n or GATE_N[what])
        k = max(1, counts[2])
        print(f"{what}: {n or GATE_N[what]} trials, {bad} differing; instructions a call in the common case "
              f"({counts[2]} calls): main {counts[0] / k:.0f}, ours {counts[1] / k:.0f}; uncached loads + stores "
              f"main {counts[3] / k:.0f}, ours {counts[4] / k:.0f}", flush=True)
        ok &= bad == 0
        if negative:
            for f in faults:
                nb, _ = fn(make(), random.Random(seed + 7), min(n or GATE_N[what], 400), f)
                print(f"{what}: negative control {f}: {nb} differing (must be > 0)", flush=True)
                ok &= nb > 0
    return ok


def gate(stock3: bytes, build3: bytes, code: dict, seed: int) -> bool:
    """the gate's linkfast: every stocklink site the build edits, proved against the same build with it put back"""
    from dnfw.waverider.coldfire import declared_sites, site_bytes     # noqa: PLC0415
    syms = code.get("c_text_symbols", {})
    base, names, on = bytearray(build3), [], []
    for va, stock_hex, sym, call, _what, tail in declared_sites():
        at, want = va - BASE, bytes.fromhex(stock_hex)
        have = build3[at:at + len(want)]
        if have == want:
            continue
        shape = site_bytes(stock_hex, syms.get(sym, 0), call, tail)
        if sym not in syms or have != shape:
            print(f"FAIL: {va:#x} ({sym}) is neither stock's bytes nor the jump to {sym} the code map names")
            return False
        if sym not in SITE_CHECKS:
            print(f"FAIL: {va:#x} ({sym}) has no check here")
            return False
        base[at:at + len(want)] = want
        on.append(f"{va:#x} {sym}")
        names += [c for c in SITE_CHECKS[sym] if c not in names]
    if not on:
        print("PASS: no declared site in this build (DN2_STOCK_LINK_FAST and DN2_OB_FAST off): nothing to prove")
        return True
    print(f"{len(on)} declared sites on: " + ", ".join(on), flush=True)
    ok = run_checks(lambda: Pair(bytes(base), code, build3, code), [c for c in CHECKS if c in names], 0, seed, True)
    print(("PASS" if ok else "FAIL") + f": {len(on)} sites, checks {', '.join(c for c in CHECKS if c in names)}: "
          + ("the same bytes as stock's, every fault found" if ok else "a difference, or a fault not found"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    d = sub.add_parser("dev")
    d.add_argument("sec3")
    d.add_argument("base")
    d.add_argument("ours")
    d.add_argument("what", choices=[*CHECKS, "all"])
    d.add_argument("--n", type=int, default=0)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--negative", action="store_true")
    d.add_argument("--usb", default=None, help="usbout: A,B,MONO fixed (one setting's counts)")
    g = sub.add_parser("gate")
    g.add_argument("stock3")
    g.add_argument("build3")
    g.add_argument("code")
    g.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.mode == "gate":
        ok = gate(open(a.stock3, "rb").read(), open(a.build3, "rb").read(), json.load(open(a.code)), a.seed)
        return 0 if ok else 1
    if a.usb:
        global FIXED
        FIXED = tuple(int(x) for x in a.usb.split(","))
    sec3 = open(a.sec3, "rb").read()
    base, ours = json.load(open(a.base)), json.load(open(a.ours))
    ib, io = applied(sec3, base), applied(sec3, ours)
    ok = run_checks(lambda: Pair(ib, base, io, ours), list(CHECKS) if a.what == "all" else [a.what], a.n, a.seed,
                    a.negative)
    print("ALL SAME" if ok else "DIFFERENCES FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
