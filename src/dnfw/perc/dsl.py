"""One program, two backends: SHARC assembly text, and its exact execution in Python.

PERC's DSP code (docs/perc.md) is written once, as calls on a `Prog`. In **emit** mode each
call appends the instruction it stands for to the assembly; in **run** mode it performs
that instruction on a register file and a memory, with the SHARC's semantics for the
forms we use: float32 arithmetic rounded to nearest, FLOAT/TRUNC, 32-bit integer
arithmetic, logical and arithmetic shifts, word loads and stores at byte addresses.

Control flow is structured (`if_`, `loop`): emit mode writes both arms with labels and
`JUMP 0x0; // -> label.` targets (scripts/sharc_resolve_jumps.py fills them in); run mode
evaluates the condition and runs one arm. So the model *is* the program: what the SHARC
runner holds the assembled code to, bit for bit, is this module running the same calls.
That checks the assembler, the encodings and these semantics; whether the program
sounds like the design is checked separately, against the design (test_perc_live.py).

The instruction forms are the ones our other SHARC code already uses (and the gate's
decode step reads every instruction back): no XOR, no integer multiply, no hardware
loops, no CALL; every integer add has R8..R15 as its first operand.
"""

from __future__ import annotations

import math
import re
import struct


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def flt(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


def s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >> 31 else v


def imm(v: int) -> str:
    """A 32-bit literal as selmap prints it: signed when its top bit is set."""
    v &= 0xFFFFFFFF
    return f"-{(1 << 32) - v:#x}" if v >> 31 else f"{v:#x}"


def fimm(x: float) -> str:
    return imm(bits(f32(x)))


COND = {"EQ": lambda c: c == 0, "NE": lambda c: c != 0, "LT": lambda c: c < 0,
        "GE": lambda c: c >= 0, "LE": lambda c: c <= 0, "GT": lambda c: c > 0}
NOT = {"EQ": "NE", "NE": "EQ", "LT": "GE", "GE": "LT", "LE": "GT", "GT": "LE"}


# 2026-11-10 (poly16): the index registers a compute instruction's memory move may use. The gate's
# decode step (selmap) read `compute, R = DM(I4, M6)` and `compute, R = DM(k, I5)` as 4-byte
# instructions (the compute gone) where selas and digikit read 6 bytes: which the silicon follows is
# not known, so a compute's move goes through I0..I3 only (every one of those read alike).
PAR_I = (0, 1, 2, 3)


class Mem:
    """Run mode's memory: word reads and writes at byte addresses; READ supplies what
    this run has not written (the DSP's own memory, in the runner)."""

    def __init__(self, read=None):
        self.w: dict[int, int] = {}
        self.read = read or (lambda a: 0)

    def get(self, a: int) -> int:
        a &= 0xFFFFFFFF
        return self.w[a] if a in self.w else (self.read(a) or 0) & 0xFFFFFFFF

    def put(self, a: int, v: int) -> None:
        self.w[a & 0xFFFFFFFF] = v & 0xFFFFFFFF


class Prog:
    def __init__(self, mode: str = "emit", mem: Mem | None = None, prefix: str = "pk"):
        assert mode in ("emit", "run")
        self.mode, self.mem = mode, mem or Mem()
        self.lines: list[str] = []
        self.r = [0] * 16                 # R0..R15 (F aliases R)
        self.i = [0] * 8                  # I0..I7 (byte addresses)
        self.n_label = 0
        self.prefix = prefix
        self.steps = 0
        self.subs: dict[str, object] = {}       # name -> body, emitted once by emit_subs()
        self.in_sub = False
        self.spill: int | None = None           # a DM word `ash` may use (see ash)
        self.known: dict[int, int] = {}         # emit mode: register -> the constant it holds
        self._alu: int | None = None            # 2026-11-10: the last instruction's ALU result (fop_lt)
        # 2026-11-10 (poly16): the last instruction, if a plain compute a following memory move may
        # ride on (MERGE): (its line's index, text, note, destination register)
        self._mg: tuple | None = None
        # ... and the last instruction, if a lone memory move the next compute may take in (forward):
        # (its sequence number, line index, text, note, the register it loads or None)
        self._mv: tuple | None = None
        self._last_mv: tuple | None = None
        self._seq = 0

    # -- emit helpers -------------------------------------------------------------------
    @property
    def run(self) -> bool:
        return self.mode == "run"

    MERGE = True                               # 2026-11-10: fold a load / store into the compute before it

    def e(self, text: str, note: str = "") -> None:
        self._alu = None
        self._mg = None
        self._last_mv, self._mv = self._mv, None
        self._seq += 1
        if not self.run:
            self._forget(text)
            line = f"      {text}"
            self.lines.append(line.ljust(40) + f"// {note}" if note else line)
        else:
            self.steps += 1

    _DEST = re.compile(r"^[RF](\d+) = ")

    def _forget(self, text: str) -> None:
        """v0.24, emit mode: what TEXT does to the registers known to hold a constant
        (`known`, which lets a constant load that would reload the same value be left
        out). Anything but a plain one-destination R/F write, a store, a compare or an
        I-register load forgets them all."""
        m = self._DEST.match(text)
        if m and "," not in text.split("=", 1)[1].replace(", I", "").replace(", M", "") \
                and "(" not in text.split("=", 1)[0]:
            self.known.pop(int(m.group(1)), None)
        elif text.startswith(("DM(", "COMP(")) or re.match(r"^I\d+ = R\d+;$", text):
            pass
        else:
            self.known.clear()

    def _compute(self, d: int, text: str, note: str, srcs=()) -> None:
        """the instruction just emitted (TEXT, writing Rd from SRCS) is a plain compute: take in the
        lone memory move right before it when that is the same as running them in turn (a load
        into none of its registers; any store, which reads its register before the compute
        writes), else mark it as one the next move may join"""
        if not self.MERGE:
            return
        mv = self._last_mv
        if mv is not None and mv[0] == self._seq - 1 and (mv[4] is None or (mv[4] != d and mv[4] not in srcs)):
            self._last_mv = None
            if self.run:
                self.steps -= 1
            else:
                line, mtext, mnote = mv[1], mv[2], mv[3]
                if line == len(self.lines) - 2:
                    self.lines.pop()
                    body = f"      {text[:-1]}, {mtext[:-1]};"
                    nt = note or mnote
                    self.lines[line] = body.ljust(40) + f"// {nt}" if nt else body
                    if mv[4] is not None:
                        self.known.pop(mv[4], None)
                    return
                self._mg = (len(self.lines) - 1, text, note, d)
            return
        self._mg = (len(self.lines) - 1 if not self.run else None, text, note, d)

    def _lone(self, text: str, note: str, load: int | None, k: int | None = None) -> None:
        """a memory move just emitted on its own: the next compute may take it in"""
        if self.MERGE and (k is None or -32 <= k < 32):
            self._mv = (self._seq, len(self.lines) - 1 if not self.run else None, text, note, load)

    def _merge(self, move: str, load: int | None = None, store: int | None = None, k: int | None = None) -> bool:
        """2026-11-10 (poly16): put MOVE (a DM access through I0..I7: post-modify, or an offset in
        -32..31) into the compute instruction just before it, when that is the same as running
        them one after the other: a load never into the compute's destination, a store never of
        it (the core reads every operand before it writes). Emit mode: one line, `compute,
        move;` (types 3a / 4a); run mode: the move costs no step. True if merged."""
        mg = self._mg
        if mg is None or (k is not None and not -32 <= k < 32):
            return False
        line, text, note, d = mg
        if load == d or store == d:
            return False
        self._mg = None
        if not self.run:
            body = f"      {text[:-1]}, {move[:-1]};"
            self.lines[line] = body.ljust(40) + f"// {note}" if note else body
            if load is not None:
                self.known.pop(load, None)
        return True

    def comment(self, text: str) -> None:
        if not self.run:
            self.lines.append(f"      // {text}")

    def raw(self, text: str) -> None:
        self._mg = self._mv = None
        if not self.run:
            self.known.clear()
            self.lines.append(text)

    def label(self, stem: str) -> str:
        self.n_label += 1
        return f"wr_{self.prefix}_{stem}_{self.n_label}"

    def place(self, name: str) -> None:
        self._mg = self._mv = None
        if not self.run:
            self.known.clear()                 # control can arrive here from elsewhere
            self.lines += [f".GLOBAL {name}.;", f"{name}.:"]

    def jump(self, cond: str, target: str) -> None:
        self._mg = self._mv = None
        if not self.run:
            self.known.clear()
            pre = f"IF {cond} " if cond else ""
            self.lines.append(f"      {pre}JUMP 0x0;".ljust(40) + f"// -> {target}.")

    def jump_abs(self, cond: str, addr: int, note: str) -> None:
        self._mg = self._mv = None
        if not self.run:
            self.known.clear()
            pre = f"IF {cond} " if cond else ""
            self.lines.append(f"      {pre}JUMP {addr:#x};".ljust(40) + f"// {note}")

    # -- registers ----------------------------------------------------------------------
    def F(self, k: int) -> float:
        return flt(self.r[k])

    def setF(self, k: int, x: float) -> None:
        self.r[k] = bits(f32(x))

    def setR(self, k: int, v: int) -> None:
        self.r[k] = v & 0xFFFFFFFF

    # -- constants ----------------------------------------------------------------------
    def fconst(self, d: int, x: float, note: str = "") -> None:
        self._const(d, bits(f32(x)), note or repr(f32(x)))

    def iconst(self, d: int, v: int, note: str = "") -> None:
        self._const(d, v & 0xFFFFFFFF, note)

    def _const(self, d: int, v: int, note: str) -> None:
        """Rd = the 32-bit V. Emit mode leaves the load out when Rd is known to hold V
        already (v0.24: the DSP's 1 MiB upload buffer); run mode loads it either way,
        which changes nothing then, so the model is the same program."""
        if self.run:
            self.steps += 1
            self._mg = None
            self._mv = None
            self._seq += 1
            self.r[d] = v
            return
        if self.known.get(d) == v:
            return
        self.e(f"R{d} = {imm(v)};", note)
        self.known[d] = v

    # -- float -------------------------------------------------------------------------
    def fop(self, d: int, a: int, op: str, b: int, note: str = "") -> None:
        if op in ("MIN", "MAX"):
            self.e(f"F{d} = {op}(F{a}, F{b});", note)
        else:
            self.e(f"F{d} = F{a} {op} F{b};", note)
        self._compute(d, f"F{d} = {op}(F{a}, F{b});" if op in ("MIN", "MAX") else f"F{d} = F{a} {op} F{b};", note, (a, b))
        if op != "*":
            self._alu = 0                       # (set to the result below in run mode)
        if self.run:
            x, y = self.F(a), self.F(b)
            # v0.34: as the core (the PGR's float ALU and multiplier entries, Fx + Fy, MIN,
            # MAX among them): a NaN INPUT gives an all-ones result, whichever operand it
            # is. Python's min(1.0, nan) is 1.0, so until v0.33 the model could clamp a NaN
            # away that the DSP carries on (and the output guard then wipes): the model and
            # the unit disagreed on exactly the case the guard exists for
            if math.isnan(x) or math.isnan(y):
                self.r[d] = 0xFFFFFFFF
                if op != "*":
                    self._alu = self.r[d]
                return
            v = {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                 "MIN": lambda: min(x, y), "MAX": lambda: max(x, y)}[op]()
            self.setF(d, f32(v))
            if op != "*":
                self._alu = self.r[d]

    def fpass(self, d: int, a: int, note: str = "") -> None:
        self.e(f"F{d} = PASS F{a};", note)
        self._compute(d, f"F{d} = PASS F{a};", note, (a,))
        if self.run:
            self.r[d] = self.r[a]

    def trunc(self, d: int, a: int, note: str = "") -> None:
        self.e(f"R{d} = TRUNC F{a};", note)
        self._compute(d, f"R{d} = TRUNC F{a};", note, (a,))
        if self.run:
            x = self.F(a)
            v = int(math.trunc(x)) if math.isfinite(x) else 0
            self.setR(d, max(-(1 << 31), min((1 << 31) - 1, v)))

    def float_(self, d: int, a: int, s: int, note: str = "") -> None:
        """Fd = FLOAT Ra BY Rs: the signed integer Ra times 2^Rs."""
        self.e(f"F{d} = FLOAT R{a} BY R{s};", note)
        self._compute(d, f"F{d} = FLOAT R{a} BY R{s};", note, (a, s))
        if self.run:
            self.setF(d, f32(float(s32(self.r[a])) * 2.0 ** s32(self.r[s])))

    # -- integer ------------------------------------------------------------------------
    def iop(self, d: int, a: int, op: str, b: int, note: str = "") -> None:
        if op == "+":
            assert 8 <= a <= 15, "integer adds take R8..R15 first (docs/waverider-m5-dsp.md, G5)"
        if op in ("MIN", "MAX"):
            self.e(f"R{d} = {op}(R{a}, R{b});", note)
            self._compute(d, f"R{d} = {op}(R{a}, R{b});", note, (a, b))
        else:
            self.e(f"R{d} = R{a} {op} R{b};", note)
            self._compute(d, f"R{d} = R{a} {op} R{b};", note, (a, b))
        if self.run:
            x, y = self.r[a], self.r[b]
            v = {"+": lambda: x + y, "-": lambda: x - y, "AND": lambda: x & y, "OR": lambda: x | y,
                 "MIN": lambda: min(s32(x), s32(y)), "MAX": lambda: max(s32(x), s32(y))}[op]()
            self.setR(d, v)

    def mul_ssf(self, d: int, a: int, b: int, note: str = "") -> None:
        """v0.42: Rd = Ra * Rb (SSF), the fixed-point multiplier: signed fractions, the 64-bit
        product shifted left once, bits 63..32 kept (truncated: no R, so no rounding; PRM
        p.3-9/3-10). For integers: floor(Ra x Rb / 2^31). Never both -2^31 (that wraps)."""
        self.e(f"R{d} = R{a} * R{b} (SSF);", note)
        if self.run:
            x, y = s32(self.r[a]), s32(self.r[b])
            assert not (x == y == -(1 << 31)), "SSF: -1 x -1 wraps"
            self.setR(d, ((x * y) << 1) >> 32)

    def mul_ssi(self, d: int, a: int, b: int, note: str = "") -> None:
        """v0.42: Rd = Ra * Rb (SSI), the multiplier's signed integer form: the product's low
        32 bits (bits 31..0 of the 80-bit result, PRM p.3-10)."""
        self.e(f"R{d} = R{a} * R{b} (SSI);", note)
        if self.run:
            self.setR(d, s32(self.r[a]) * s32(self.r[b]))

    def ipass(self, d: int, a: int, note: str = "") -> None:
        self.e(f"R{d} = PASS R{a};", note)
        self._compute(d, f"R{d} = PASS R{a};", note, (a,))
        if self.run:
            self.r[d] = self.r[a]

    def lsh(self, d: int, a: int, n: int, note: str = "") -> None:
        self.e(f"R{d} = LSHIFT R{a} BY {n};", note)   # (never merged: a shift by an immediate is
                                                    # type 6, its field fixed after selas: fix_shift_imm)
        if self.run:
            x = self.r[a]
            self.setR(d, (x << n) if n >= 0 else (x >> -n))

    def ash(self, d: int, a: int, n: int, note: str = "", keep12: bool = False) -> None:
        """Rd = Ra >> -n, arithmetic. selas mis-encodes the immediate form `ASHIFT Rx BY n`
        (its shifter-op field is not the one the firmware's immediate ASHIFTs carry:
        digikit reads it as "unsupported ShiftImm opcode 0x20", reader.asm), so the count
        goes in a register: R12, the DSL's scratch (the run mode sets it too, so a caller
        that needed R12 kept fails its model), unless d or a is R12 or KEEP12 -- then
        another register, saved to and restored from the word `self.spill`."""
        assert n < 0
        if 12 not in (d, a) and not keep12:
            x = s32(self.r[a]) >> -n if self.run else 0
            self.iconst(12, n)
            self.e(f"R{d} = ASHIFT R{a} BY R12;", note)
            if self.run:
                self.setR(d, x)
            return
        if not self.run:
            assert self.spill is not None, "ash needs Prog.spill"
        t = next(r for r in (13, 14, 15) if r not in (d, a))
        if self.spill is not None:
            self.st(self.spill, t)
        else:
            self.steps += 1
        x = s32(self.r[a]) >> -n if self.run else 0
        self.iconst(t, n)
        self.e(f"R{d} = ASHIFT R{a} BY R{t};", note)
        if self.spill is not None:
            self.ld(t, self.spill)
        else:
            self.steps += 1
        if self.run:
            self.setR(d, x)

    def xor(self, d: int, a: int, b: int, t: int) -> None:
        """Rd = Ra ^ Rb as (Ra | Rb) - (Ra & Rb) (no XOR form in the stock corpus).
        Clobbers Rt; d may equal a."""
        self.iop(t, a, "AND", b)
        self.iop(d, a, "OR", b)
        self.iop(d, d, "-", t)

    # -- memory -------------------------------------------------------------------------
    def ld(self, d: int, addr: int, note: str = "") -> None:
        self.e(f"R{d} = DM({imm(addr)});", note)
        if self.run:
            self.r[d] = self.mem.get(addr)

    def st(self, addr: int, s: int, note: str = "") -> None:
        self.e(f"DM({imm(addr)}) = R{s};", note)
        if self.run:
            self.mem.put(addr, self.r[s])

    def ldi(self, d: int, k: int, i: int, note: str = "") -> None:
        if not (i in PAR_I and self._merge(f"R{d} = DM({k}, I{i});", load=d, k=k)):
            self.e(f"R{d} = DM({k}, I{i});", note)
            if i in PAR_I:
                self._lone(f"R{d} = DM({k}, I{i});", note, d, k)
        if self.run:
            self.r[d] = self.mem.get(self.i[i] + 4 * k)

    def sti(self, k: int, i: int, s: int, note: str = "") -> None:
        if not (i in PAR_I and self._merge(f"DM({k}, I{i}) = R{s};", store=s, k=k)):
            self.e(f"DM({k}, I{i}) = R{s};", note)
            if i in PAR_I:
                self._lone(f"DM({k}, I{i}) = R{s};", note, None, k)
        if self.run:
            self.mem.put(self.i[i] + 4 * k, self.r[s])

    def seti(self, i: int, s: int, note: str = "") -> None:
        self.e(f"I{i} = R{s};", note)
        if self.run:
            self.i[i] = self.r[s]

    def ldm(self, d: int, i: int, note: str = "") -> None:
        """Rd = DM(Ii, M7): load, then Ii one word back (M7 is -1, an ABI constant, 2026-11-10)."""
        if not (i in PAR_I and self._merge(f"R{d} = DM(I{i}, M7);", load=d)):
            self.e(f"R{d} = DM(I{i}, M7);", note)
            if i in PAR_I:
                self._lone(f"R{d} = DM(I{i}, M7);", note, d)
        if self.run:
            self.r[d] = self.mem.get(self.i[i])
            self.i[i] -= 4

    def stm(self, i: int, s: int, note: str = "") -> None:
        """DM(Ii, M7) = Fs: store, then Ii one word back."""
        if not (i in PAR_I and self._merge(f"DM(I{i}, M7) = F{s};", store=s)):
            self.e(f"DM(I{i}, M7) = F{s};", note)
            if i in PAR_I:
                self._lone(f"DM(I{i}, M7) = F{s};", note, None)
        if self.run:
            self.mem.put(self.i[i], self.r[s])
            self.i[i] -= 4

    def geti(self, d: int, i: int, note: str = "") -> None:
        """Rd = Ii (2026-11-10)."""
        self.e(f"R{d} = I{i};", note)
        if self.run:
            self.r[d] = self.i[i] & 0xFFFFFFFF

    def stpost(self, i: int, s: int, note: str = "") -> None:
        """DM(Ii, M6) = Fs: store, then Ii moves one word on (M6 = 1)."""
        if not (i in PAR_I and self._merge(f"DM(I{i}, M6) = F{s};", store=s)):
            self.e(f"DM(I{i}, M6) = F{s};", note)
            if i in PAR_I:
                self._lone(f"DM(I{i}, M6) = F{s};", note, None)
        if self.run:
            self.mem.put(self.i[i], self.r[s])
            self.i[i] += 4

    def ldpost(self, d: int, i: int, note: str = "") -> None:
        if not (i in PAR_I and self._merge(f"R{d} = DM(I{i}, M6);", load=d)):
            self.e(f"R{d} = DM(I{i}, M6);", note)
            if i in PAR_I:
                self._lone(f"R{d} = DM(I{i}, M6);", note, d)
        if self.run:
            self.r[d] = self.mem.get(self.i[i])
            self.i[i] += 4

    # -- 2026-11-10 (poly16): a conditional compute, ABS, plain FLOAT -------------------
    def fop_lt(self, d: int, a: int, op: str, b: int, note: str = "") -> None:
        """`IF LT Fd = Fa op Fb;` right after an ALU op (fop +, -, MIN, MAX) whose result decides:
        LT is AN and not AZ for a float result (PRM p.4-53: negative, not +-0; a NaN with its sign
        bit set too). The caller emits nothing between the two."""
        assert self._alu is not None, "fop_lt must follow an ALU fop directly"
        last = self._alu
        self.e(f"IF LT F{d} = F{a} {op} F{b};", note)
        if self.run and last >> 31 and last & 0x7FFFFFFF:
            x, y = self.F(a), self.F(b)
            if math.isnan(x) or math.isnan(y):
                self.r[d] = 0xFFFFFFFF
            else:
                self.setF(d, f32({"+": x + y, "-": x - y, "*": x * y}[op]))

    def fop_if(self, cond: str, d: int, a: int, op: str, b: int | None = None, note: str = "") -> None:
        """`IF cond Fd = Fa op Fb;` (op PASS: `IF cond Fd = PASS Fa;`) right after an ALU fop, on its
        result's flags (float: AZ for +-0, AN its sign; PRM p.4-53: LT = AN and not AZ, LE = AN or
        AZ, GT and GE their negations, EQ = AZ, NE = not AZ)."""
        assert self._alu is not None, "fop_if must follow an ALU fop directly"
        last = self._alu
        an, az = bool(last >> 31), not last & 0x7FFFFFFF
        lt, le = an and not az, an or az
        take = {"LT": lt, "LE": le, "GT": not le, "GE": not lt, "EQ": az, "NE": not az}[cond]
        if op == "PASS":
            self.e(f"IF {cond} F{d} = PASS F{a};", note)
        else:
            self.e(f"IF {cond} F{d} = F{a} {op} F{b};", note)
        if self.run and take:
            if op == "PASS":
                self.r[d] = self.r[a]
                return
            x, y = self.F(a), self.F(b)
            if math.isnan(x) or math.isnan(y):
                self.r[d] = 0xFFFFFFFF
            else:
                self.setF(d, f32({"+": x + y, "-": x - y, "*": x * y}[op]))

    def fabs_(self, d: int, a: int, note: str = "") -> None:
        """Fd = ABS Fa (a NaN input: all ones, as the core's other float ops)."""
        self.e(f"F{d} = ABS F{a};", note)
        if self.run:
            x = self.F(a)
            self.r[d] = 0xFFFFFFFF if math.isnan(x) else self.r[a] & 0x7FFFFFFF

    def float0(self, d: int, a: int, note: str = "") -> None:
        """Fd = FLOAT Ra (the signed integer, exactly as FLOAT Ra BY 0)."""
        self.e(f"F{d} = FLOAT R{a};", note)
        self._compute(d, f"F{d} = FLOAT R{a};", note, (a,))
        if self.run:
            self.setF(d, f32(float(s32(self.r[a]))))

    # -- parallel instructions (2026-11-10, poly16) -------------------------------------
    def par(self, *ops) -> None:
        """One SHARC instruction doing several things at once: every operand (the stored
        register too) is read before any result is written, as the core does.

        Compute (at most one group):
          ("op", d, a, OP, b)      any one float op (+ - * MIN MAX), any registers;
          ("*", d, a, b) with ("+"|"-", d, a, b), or ("+-", d1, d2, a, b) (Fd1 = a + b,
                                   Fd2 = a - b): the multifunction forms, the multiplier's
                                   operands F0-F3 x F4-F7 and the ALU's F8-F11, F12-F15
                                   (selas does NOT check these: it encodes garbage);
          ("*", ...) or ("+", ...) alone is a single op (any registers).
        Move (at most one, I0-I7): ("ld", d, i) Fd = DM(Ii, M6), Ii one word on; ("st", i, s)
          DM(Ii, M6) = Fs; ("ldk", d, k, i) Fd = DM(k, Ii); ("stk", k, i, s) DM(k, Ii) = Fs,
          -32 <= k < 32."""
        comp = [o for o in ops if o[0] in ("op", "*", "+", "-", "+-")]
        moves = [o for o in ops if o[0] in ("ld", "st", "ldk", "stk")]
        assert len(comp) + len(moves) == len(ops), ops
        assert len(moves) <= 1, "one memory move a compute (no PM bus here)"
        for m in moves:                         # 2026-11-10: I0..I3 only (PAR_I, below)
            i = {"ld": m[2] if len(m) > 2 else None, "st": m[1], "ldk": m[3] if len(m) > 3 else None,
                 "stk": m[2]}[m[0]]
            assert i in PAR_I, f"a compute's move through I{i}: selmap reads it as a 4-byte instruction"
        texts, writes, results = [], [], []
        ops_f = {"+": lambda x, y: x + y, "-": lambda x, y: x - y, "*": lambda x, y: x * y,
                 "MIN": min, "MAX": max}

        def fval(op, a, b):
            x, y = self.F(a), self.F(b)
            if math.isnan(x) or math.isnan(y):
                return 0xFFFFFFFF
            return bits(f32(ops_f[op](x, y)))
        single = len(comp) == 1 and comp[0][0] in ("op", "*", "+", "-")
        if single:
            c = comp[0]
            d, a, op, b = (c[1], c[2], c[3], c[4]) if c[0] == "op" else (c[1], c[2], c[0], c[3])
            assert op in ops_f
            texts.append(f"F{d} = {op}(F{a}, F{b})" if op in ("MIN", "MAX") else f"F{d} = F{a} {op} F{b}")
            writes.append(d)
            if self.run:
                results.append((d, fval(op, a, b)))
        elif comp:
            # 2026-11-10: the gate's decode step: selmap reads selas's `Fm = Fx * Fy, Fa = ...` as
            # `Fm = MRF + Fx * Fy, ...` (a fixed-point multiply-accumulate) where digikit reads a float
            # multiply; which the silicon does is not known: no multifunction compute
            raise AssertionError(f"multifunction computes are refused (selmap / digikit disagree): {comp}")
            mul = [c for c in comp if c[0] == "*"]
            alu = [c for c in comp if c[0] in ("+", "-", "+-")]
            assert len(mul) <= 1 and len(alu) <= 1 and not [c for c in comp if c[0] == "op"], comp
            if mul:
                _, d, a, b = mul[0]
                assert a in range(0, 4) and b in range(4, 8), f"multifunction multiply F{a} * F{b}"
                texts.append(f"F{d} = F{a} * F{b}")
                writes.append(d)
                if self.run:
                    results.append((d, fval("*", a, b)))
            if alu:
                c = alu[0]
                if c[0] == "+-":
                    _, d1, d2, a, b = c
                    assert a in range(8, 12) and b in range(12, 16), f"multifunction F{a} +- F{b}"
                    texts += [f"F{d1} = F{a} + F{b}", f"F{d2} = F{a} - F{b}"]
                    writes += [d1, d2]
                    if self.run:
                        results += [(d1, fval("+", a, b)), (d2, fval("-", a, b))]
                else:
                    op, d, a, b = c
                    assert a in range(8, 12) and b in range(12, 16), f"multifunction F{a} {op} F{b}"
                    texts.append(f"F{d} = F{a} {op} F{b}")
                    writes.append(d)
                    if self.run:
                        results.append((d, fval(op, a, b)))
        load = None
        for m in moves:
            if m[0] in ("ld", "st"):
                i = m[2] if m[0] == "ld" else m[1]
                assert 0 <= i < 8
                if m[0] == "ld":
                    texts.append(f"F{m[1]} = DM(I{i}, M6)")
                    writes.append(m[1])
                    if self.run:
                        load = (m[1], self.mem.get(self.i[i]))
                        self.i[i] += 4
                else:
                    texts.append(f"DM(I{i}, M6) = F{m[2]}")
                    if self.run:
                        self.mem.put(self.i[i], self.r[m[2]])
                        self.i[i] += 4
            else:
                k, i = (m[2], m[3]) if m[0] == "ldk" else (m[1], m[2])
                assert 0 <= i < 8 and -32 <= k < 32
                if m[0] == "ldk":
                    texts.append(f"F{m[1]} = DM({k}, I{i})")
                    writes.append(m[1])
                    if self.run:
                        load = (m[1], self.mem.get(self.i[i] + 4 * k))
                else:
                    texts.append(f"DM({k}, I{i}) = F{m[3]}")
                    if self.run:
                        self.mem.put(self.i[i] + 4 * k, self.r[m[3]])
        assert len(writes) == len(set(writes)), f"two results in one register: {texts}"
        self.e(", ".join(texts) + ";")
        if self.run:
            for d, v in results:
                self.r[d] = v
            if load:
                self.r[load[0]] = load[1]

    # -- structured control flow ------------------------------------------------------
    def _cmp(self, a: int, b: int, kind: str) -> int:
        if kind == "f":
            x, y = self.F(a), self.F(b)
        else:
            x, y = s32(self.r[a]), s32(self.r[b])
        return (x > y) - (x < y)

    def if_(self, a: int, cond: str, b: int, then, else_=None, kind: str = "f") -> None:
        """if (a COND b) then() else else_(). kind 'f': COMP(Fa, Fb); 'i': COMP(Ra, Rb)."""
        self.e(f"COMP({'F' if kind == 'f' else 'R'}{a}, {'F' if kind == 'f' else 'R'}{b});")
        self._branch(lambda: COND[cond](self._cmp(a, b, kind)), cond, then, else_)

    def ifz(self, a: int, cond: str, then, else_=None, kind: str = "i") -> None:
        """if (a COND 0) by PASS (kind 'i': R, 'f': F)."""
        self.e(f"{'R' if kind == 'i' else 'F'}{a} = PASS {'R' if kind == 'i' else 'F'}{a};")

        def test():
            x = s32(self.r[a]) if kind == "i" else self.F(a)
            return COND[cond]((x > 0) - (x < 0))
        self._branch(test, cond, then, else_)

    def _branch(self, test, cond, then, else_) -> None:
        if self.run:
            if test():
                then()
            elif else_:
                else_()
            return
        skip = self.label("else")
        self.jump(NOT[cond], skip)
        then()
        if else_:
            end = self.label("fi")
            self.jump("", end)
            self.place(skip)
            else_()
            self.place(end)
        else:
            self.place(skip)

    def loop(self, counter: int, n_from: int, body, one: int = 12) -> None:
        """for (counter = n_from; counter; counter--) body(). COUNTER is a scratch word
        address (the body may use every register). ONE: a register body() leaves free."""
        self.iconst(0, n_from)
        self.st(counter, 0)
        top = self.label("loop")
        self.place(top)
        if self.run:
            while True:
                body()
                self.ld(0, counter)
                self.iconst(one, 1)
                self.iop(0, 0, "-", one)
                self.st(counter, 0)
                if self.r[0] == 0:
                    break
            return
        body()
        self.ld(0, counter)
        self.iconst(one, 1)
        self.iop(0, 0, "-", one)
        self.st(counter, 0)
        self.jump("NE", top)

    def loop_r(self, counter: int, n_from: int | None, body, one: int = 12) -> None:
        """v0.42: loop() with the count in register COUNTER (no scratch word: two L2 accesses
        an iteration fewer). BODY must leave COUNTER alone (ONE it may use). N_FROM None: the
        count is in COUNTER already, and is not 0."""
        if n_from is not None:
            self.iconst(counter, n_from)
        elif self.run:
            assert s32(self.r[counter]) > 0, "loop_r: a count of 0 or less would run 2^32 times"
        top = self.label("loop")
        self.place(top)
        if self.run:
            while True:
                before = self.r[counter]
                body()
                assert self.r[counter] == before, f"loop_r: the body changed its count R{counter}"
                self.iconst(one, 1)
                self.iop(counter, counter, "-", one)
                if self.r[counter] == 0:
                    break
            return
        body()
        self.iconst(one, 1)
        self.iop(counter, counter, "-", one)
        self.jump("NE", top)

    # -- leaf subroutines ---------------------------------------------------------------
    def call(self, name: str, body) -> None:
        """A leaf subroutine: run mode runs BODY here; emit mode jumps to its one copy with
        the return address - 1 in I12, and the copy ends `JUMP (M14, I12)` (M14 is 1, an
        ABI constant), not delayed. Clobbers R12 and I12 (saved and restored around the
        whole program); BODY must not call."""
        assert not self.in_sub, f"{name}: subroutines are leaves"
        if self.run:
            self.in_sub = True
            body()
            self.in_sub = False
            return
        self.subs.setdefault(name, body)
        ret = self.label("ret")
        self.known.clear()
        self.lines.append("      R12 = 0x0;".ljust(40) + f"// return address - 1: {ret}. - 1")
        self.e("I12 = R12;")
        self.jump("", f"wr_{self.prefix}_sub_{name}")
        self.place(ret)

    def emit_subs(self) -> None:
        for name, body in list(self.subs.items()):
            self.place(f"wr_{self.prefix}_sub_{name}")
            self.in_sub = True
            body()
            self.in_sub = False
            # not delayed: the delayed form, JUMP (M14, I12) (DB), is the compiler's
            # function return, and the SHARC runner holds that form to its call stack
            self.e("JUMP (M14, I12);")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"
