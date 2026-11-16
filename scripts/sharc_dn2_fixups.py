"""Workarounds that let digikit's SHARC runner (work/sharc-emulator, 6f812e9)
run the DN2 1.11 voice path. Each one is a gap in the runner, measured on the
DN2 image, and documented in `docs/for-digikit-sharc-runner-dn2.md` (sections
6 onward) -- that is where a fix belongs; this file only steps around them.

digikit is a tool here (GPL-2.0+): `bind(tools_dir)` imports its modules from
a checkout the caller names, and nothing of it is copied. We call a few of its
private helpers (`_dm_read`, `_lw_load_codes`, ...) rather than re-implement
them, so the semantics stay digikit's own.

The stepping loop is `run(runner, steps, fixups)`. Per instruction a fixup
either does nothing (the runner steps as usual), runs after the step (a
post-fix), or replaces the step outright:

  G1  SIMD PEy is modelled only in Types 2c and 2a_short (compute) and 14a,
      3b and 15a (memory companion). Everything else runs PEx only. We run
      such an instruction twice in SISD: PEy on a copy with R<->S (and the
      other complementary pairs) swapped and the transfer address one
      normal word up, then PEx on the real state, and merge PEy's registers,
      status and companion writes.                              ("simd two-pass")
  G2  `Rn = data32` (Types 17a/17b) in SIMD sets Rn only; the firmware relies on
      Sn getting the same value (control: init's 1024-point sine table comes
      out right only with it).                                   ("simd 17a")
  G3  (LW) register-pair transfers in Types 4b and 3b read Unknown and write
      nothing; Types 3a, 14a, 15a and 15b already do the pair.   ("lw ...")
  G4  L1 normal-word addresses (0x90000..0xe7fff) are used as byte
      addresses, so the math library's coefficient tables read as zero and
      sinf(x) returns x. An immediate NW address loaded into an I register
      is rescaled to its byte image (x4).                        ("nw->byte")
  G5  a 16-bit Type 2c whose parcel is 0xc000..0xc07f decodes as a 32-bit
      Type 2b (the 2b pattern shadows it). At 0x1c0e13 and 0x1c4f4a selache
      and the following code agree on 2c; digikit's reading desynchronises
      the decoder (M1's "unmodelled shifter op at 0x1c4f4a").    ("2b->2c")
  G6  a conditional Type 6a/6b halts ("unsupported Type6b predicate"). The
      predicate is evaluated and the form run unconditionally or skipped.
  G7  Type 13a is decoded but not executed (not met on this path yet).
  G8  a conditional Type 7a (`IF EQ MODIFY(I4, M4)`, in the amp stage
      sw 0xb80345 once a note is on) halts ("unsupported Type7a
      predicate"): only "always" (31) and 0x17 run. Handled as G6.
  G10 Type 8a ignores the (LA) loop-abort bit: `_type_25a_direct` calls the
      transfer without `loop_abort`, although `_transfer` supports it (Type
      9a passes it). A JUMP (LA) out of a DO loop then leaves the loop's
      PC-stack entry behind, and the next RETURN halts ("return target
      differs"). Met in the amp stage sw 0xb80345 at 0xb803ee once a note is
      on. The predicate is evaluated here and, when taken, the loop and PC
      stacks are popped once, as `_apply_loop_abort` does for 9a.
  G11 FEXT (SE) (ShiftImm opcode 0x12, Types 6b/6a) sign-extends the shifted
      source without masking it to the field first: `_signed(src >> pos, len)`
      returns every bit above the field unchanged, so `fext r7 by 0:16 (se)`
      of 0x20204040 gives 0x20204040, not 0x4040. The frame unpack sw 0x1c2712
      splits each 32-bit frame word into two 16-bit parameters this way, so a
      parameter picked up its neighbour as bits 16-31 (Milestone 4, measured
      at 0x1c29fa; control: plain FEXT, opcode 0x10, at 0x1c28fc is right).
      The result register is recomputed after the step.
  G9  (ours, not the runner's) G1's two-pass assumed every memory form names
      its DAG field `i`; the 16-bit Type 3c names it `dmi`. Met in SIMD at
      0x1c2857 in sw 0x1c2712 (Milestone 3).
  G12 (2026-11-14) the 16-bit Types 3d and 4d in SIMD do no PEy companion
      access either (G1). The dispatch latches each voice's note trigger with
      them, two slots a pass over byte cells (sw 0x1c8ef1, 0x1c9ac9 reads
      engine +0x138fc + t, 0x1c9acc writes +0x1390c + t; 0x1c9abd..0x1c9ac6
      clear the masks' cells): PEx took the even slots, the odd slots' notes
      were never latched, so a voice on slot 1, 3, ... never opened its amp.
      Run by the two-pass, the companion one access width on (a byte: +1);
      a store of a register with no PEy complement (the clear stores M13)
      stores the same register there too, as the firmware's stride-2 clear
      of all sixteen cells needs.
  G13 (2026-11-14) Type 7a MODIFY's width selector (w, l): (1, 0) "(nw)"
      scales M by 4, (0, 1) "(sw)" by 2, (0, 0) blank adds M as bytes
      (PRM's BH table). The runner takes blank as normal-word (x 4 under
      assume_nw32). The engine init's per-track loop (sw 0x1c8e1c, I2 +=
      M2 blank at 0x1c8cb8, M2 = 0x70 t) then put track t's DC blocker at
      0x1c0 t: only tracks 0, 4, 8, 12 got one, the others' state landed in
      the next arrays, and a voice on slots 1..15 was silent. Run with the
      scaling off; the warm snapshot is rebuilt with it (INIT_REV). Type 7b
      (32 bits) carries the same selector at the same bits (39, 23), which
      the runner's table leaves undecoded and scales as normal-word: read
      from the raw parcel (the init's I1 += M4 at 0x1c8ca6, blank).
      Only where I + M (unscaled) lands in L1's byte image (G4's region):
      L2 and DDR the runner maps through its own x 4 alias, consistent for
      the stock FX, and there its scaling stays. A one-fix-off bisection
      (2026-11-14) showed G13 outside L1 (L2, DDR) leaves the stock reverb's
      state uncleared (a fresh stock reverb on silence peaked 169, 0.0
      without) and the stock delay's clear undone, while in L1 it is needed:
      the voice chain's stereo blocks (I1 = MODIFY(I0 = 0, M4 = 0x257ee8 +
      0x100 s), where the sends read them on the unit: CHOR and WIDE heard),
      and the stock delay's clear (7b; peak 58k on silence without).
  G14 (2026-11-14) a long-word access's post-modify (Types 4b/3b, G3)
      through an index into L1's normal-word space (its byte image, as G4
      maps it) moves the index by normal words, x 4, not x 8: the per-track
      gain smoothers are 7 words each (written 0x1c apart by the init, walked
      by `R2 = DM(I5, 7) (lw)` at 0x1c99f3 a slot each); at x 8 slot t read
      slot 2t's, slots 1..15 played 4 to 18 dB low and slot 0's smoother
      never took the track's LEVEL (0.787 at 100): slot 0 now reads ~2 dB
      lower, as the frame says. The pre-modify's address keeps x 8.
      2026-11-15 (opt-host, G14 DDR): through a DDR index too. The stock
      chorus's init (L2 sw 0xb84ece, `DM(I4, -13) = R2 (lw)`) steps from
      channel 1's 7-word state to channel 2's, and the chorus walks them 28
      bytes apart (sw 0xb84a1f, MODIFY(I2, 28)); at x 8 channel 2 landed
      before channel 1 (0x8045a674..0x8045a68c instead of 0x8045a6a8..) and
      the chorus's R pass read non-audio state (R return 0.89 on silence).
      PRM p.6-10: (lw) scales as (nw), not by 8, in byte space.
  G16 (2026-11-15, opt-host) Type 6b (shift immediate) in SIMD runs on PEx
      only: G1's two-pass took only forms with a compute[22:16] field, and
      6b's is shiftimm[22:16]. Now it is two-passed too (PRM p.101: the same
      instruction in both PEs), so PEy's shift sets S registers and ASTATY.
      The stock delay (L2 sw 0xb84223..0xb84228, in SIMD) loads N/2 into R2
      and S2, tests `BTST R2 BY 0` and jumps on SZ, which a SIMD branch ANDs
      over both PEs: with ASTATY.SZ never set the jump never went, and the
      extra stage's DM(30,I5) (0xb84235..0xb8423e) wrote over the delay's
      own length and write index (control block +0x100): the stock delay
      was never heard. With G16 it is heard (xdly over 640 blocks), and
      stockout stays bit-identical. Conditional 6b in SIMD still runs PEx
      only (G6's conditional path), and so does Type 6a: neither is
      measured on the DN2 image yet.
  G17 (2026-11-15) G12's rule for every memory form: in SIMD a store of a
      register with no PEy complement (M, I, L, B, ...) stores the same
      register at the companion address too. The output stage 0x1c244d
      clears the per-track buffers 0x259f68 (FLEX's TRK sources, Overbridge's
      raw track channels) with M12 = 0 in SIMD through 15b, 3a and 3b, then
      adds each slot's block x 11.627 into its track's buffer: the runner
      cleared only the even words, so each buffer summed every block it had
      ever received (measured: a WaveTone note's TRK1 0.065, 0.20, 0.36 ..
      1.01 RMS over nine blocks while the slot's block stayed at 0.029; the
      same on stock). A FLEX take of a track recorded that sum, and step 3f
      and TRK_UNITY were calibrated on it (the unit: a GAIN 0 take 17.9 dB
      under its source). 3b and 15a such stores are run by the two-pass;
      the warm snapshot is rebuilt (INIT_REV). Runner step 4k (trkbuf)
      checks the clear: two blocks' markers, only the last one's in the
      buffers.

Two accelerations, each measured against the emulated code it replaces:

  A1  `native_sin`: sw 0x1c10e4 (sinf) as float32(math.sin). <= 1 ulp from
      the routine run in the runner, on 58 inputs.
  A2  `native_additive`: the three 1024-point additive loops of the table
      builder sw 0x1c463b, in the firmware's float32 operation order.
      Compared word for word with the emulated loop on each loop's first
      three entries (see the M2 report).
"""

from __future__ import annotations

import collections
import dataclasses
import math
import os
import struct
import sys

sr = st = fm = seq = None
ACCESS_WIDTHS = UREG_CODES = None
_dm_read = _dm_write = _simd_active = None
Const = _signed = None


def bind(tools_dir: str) -> None:
    """Import digikit's runner from TOOLS_DIR (a checkout's tools/)."""
    global sr, st, fm, seq, ACCESS_WIDTHS, UREG_CODES, _dm_read, _dm_write, _simd_active
    global Const, _signed
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import sharc_run as _sr  # noqa: PLC0415
    import sharc_trace as _st  # noqa: PLC0415
    from sharc_core import forms_move as _fm  # noqa: PLC0415
    from sharc_core import sequencer as _seq  # noqa: PLC0415
    from sharc_core.encoding import ACCESS_WIDTHS as _aw, UREG_CODES as _uc  # noqa: PLC0415
    from sharc_core.memory import _dm_read as _r, _dm_write as _w  # noqa: PLC0415
    from sharc_core.state import _simd_active as _sa  # noqa: PLC0415
    from sharc_core.values import Const as _c, _signed as _s  # noqa: PLC0415
    sr, st, fm, seq = _sr, _st, _fm, _seq
    ACCESS_WIDTHS, UREG_CODES = _aw, _uc
    _dm_read, _dm_write, _simd_active = _r, _w, _sa
    Const, _signed = _c, _s


def F(f, name):
    return fm._field(f, name)


def cond_of(f) -> int:
    try:
        return fm._field(f, "cond")
    except KeyError:
        return 31


# the warm snapshot (sharc_waverider_voice.py's engine init) depends on these fixups: its file name carries this, so
# a snapshot built under older ones is never taken (G13 changed what the init leaves in slots 1..15)
INIT_REV = "_g17"
# a bisection aid: DNFW_FIXUPS_OFF=G12,G13a,G13b,G13d,G14,G14d,G16 runs those as before them (a snapshot built so is named apart)
OFF = {x for x in os.environ.get("DNFW_FIXUPS_OFF", "").split(",") if x}
if OFF:
    INIT_REV += "_off_" + "_".join(sorted(OFF))


def blank_modify(f) -> bool:
    """G13: a Type 7a MODIFY whose width selector (w, l) is (0, 0): no (nw) or (sw)"""
    return not f.get("w") and not f.get("l")


def l1_target(s, f) -> bool:
    """G13's scope: the MODIFY's I + M, unscaled, is inside L1's byte image (G4's region), or I is in DDR
    (2026-11-15, G13 DDR). L2 keeps the runner's scaling (a value not concrete too)"""
    bank = 8 if f.get("g") else 0
    iv = s.uregs.get(16 + ((F(f, "is[2:2]") << 2) | F(f, "is[1:0]")) + bank)
    mv = s.uregs.get(32 + F(f, "m") + bank)
    if not (isinstance(iv, Const) and isinstance(mv, Const)):
        return False
    if DDR_LO <= iv.value < DDR_HI and "G13d" not in OFF:
        # 2026-11-15 (opt-host, G13 DDR): DDR too. The stock chorus's R pass takes its ring pointer as
        # I4 = MODIFY(I0, M4 = 128) (L2 sw 0xb84a16): 128 bytes on from L's, inside the ring; at x 4 it read the
        # filter states past the ring's end (base + 0x1204) as samples. Tried alone on 2026-11-14 it left the stock
        # reverb's clear undone; that run still had G14's x 8 through DDR, which misplaced the init's own steps.
        return True
    return NW_LO * 4 <= (iv.value + mv.value) & 0xFFFFFFFF < NW_HI * 4


def width_7b(insn) -> int:
    """G13: Type 7b's width selector, bits 39 (w) and 23 (l) of the 48-bit layout as in 7a, which the runner's table
    leaves undecoded (bits 23 and 7 of the 32-bit parcel) -> M's scale: blank 1, (sw) 2, (nw) 4"""
    raw = insn.raw if insn.length_bytes == 4 else insn.raw >> 16
    w, l_ = (raw >> 23) & 1, (raw >> 7) & 1
    return 4 if w and not l_ else 2 if l_ else 1


def simd(state) -> bool:
    return _simd_active(state) is True


# forms whose PEy the runner already models (compute, or memory companion)
SIMD_NATIVE = {"2c", "2a_short", "14a", "3b", "15a"}
# memory forms with no PEy companion transfer in the runner
MEM_NO_COMPANION = {"3a", "4a", "4b", "15b", "3c", "3d", "4d"}
# G12: the forms whose companion is one access width on (G1's others: the next word, + 4)
BY_WIDTH = {"3d", "4d"}
# G17: the native companion forms whose store of a register with no PEy complement the runner leaves PEx-only
G17_NATIVE = {"3b", "15a"}
WIDTH_BYTES = {"byte": 1, "byte-sign-extended": 1, "short-word": 2, "short-word-sign-extended": 2}
FLOW = {"12a_imm", "12a_ureg", "11c", "11a", "9a_abs", "9b_abs", "25c_rframe", "9a_rel",
        "25a_direct", "25a_pcrel", "8a_abs", "8a_rel", "13a"}
COND_UNSUPPORTED = {"6b_shiftimm", "6a_mem", "7a"}
COND_NATIVE = {31, 0x17}          # the predicates the runner already runs (0x17: Type 7a only)
MR_PAIRS = (("MRF", "MSF"), ("MRB", "MSB"))     # PEx / PEy multiplier result registers
LOOP_ABORT_FORMS = {"8a_rel", "8a_abs"}
WATCH = COND_UNSUPPORTED | LOOP_ABORT_FORMS | {"3a", "4a", "4b", "3b", "15b", "13a", "17a", "17b", "2b", "7b"}
NW_LO, NW_HI = 0x240000 // 4, 0x3A0000 // 4
DDR_LO, DDR_HI = 0x80000000, 0xA0000000    # external memory (DDR), byte space (G14 DDR)
# PCs whose parcel digikit reads as a 32-bit Type 2b and selache as a 16-bit 2c
AS_2C = {0x1C0E13, 0x1C4F4A}


def _pairs():
    return [(k, k + 80) for k in range(16)] + [
        (UREG_CODES[a], UREG_CODES[b]) for a, b in
        (("ASTATX", "ASTATY"), ("STKYX", "STKYY"), ("USTAT1", "USTAT2"), ("USTAT3", "USTAT4"))]


def swap(u: dict) -> None:
    for a, b in _pairs():
        u[a], u[b] = u[b], u[a]


class COW(dict):
    """An overlay that reads through to BASE and keeps its own writes."""

    def __init__(self, base):
        super().__init__()
        self.base = base

    def __contains__(self, k):
        return dict.__contains__(self, k) or k in self.base

    def __getitem__(self, k):
        if dict.__contains__(self, k):
            return dict.__getitem__(self, k)
        return self.base[k]

    def get(self, k, d=None):
        return self[k] if k in self else d

    def own(self) -> dict:
        return dict(self.items())


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def as_float(v) -> float:
    return struct.unpack("<f", struct.pack("<I", v.value & 0xFFFFFFFF))[0]


def as_const(x: float):
    return Const(struct.unpack("<I", struct.pack("<f", x))[0])


class Fixups:
    def __init__(self):
        self.counts = collections.Counter()
        self.sites = collections.defaultdict(set)
        self.skips: dict[int, int] = {}      # pc -> pc: step over a call and its delay slots
        self.hooks: dict = {}                # pc -> fn(runner); moving the pc replaces the step
        self.last = collections.deque(maxlen=80)
        self.simd_17a = True

    def note(self, what: str, pc: int) -> None:
        self.counts[what] += 1
        self.sites[what].add(pc)

    # -- dispatch ------------------------------------------------------------------
    def pre(self, runner, insn):
        t = insn.type_name
        s = runner.state
        in_simd = simd(s)
        if t not in WATCH and not in_simd:
            return None
        f = insn.fields
        pc = s.pc_sw
        blank = t == "7a" and blank_modify(f) and getattr(s, "assume_nw32", False) and "G13a" not in OFF \
            and l1_target(s, f)
        if in_simd and t in G17_NATIVE and "G17" not in OFF and F(f, "d") and not F(f, "l") \
                and not self.is_long(t, f) and fm._cureg_code(F(f, "ureg")) is None:
            return ("replace", lambda r: self.two_pass(r, insn, memory=True))
        if in_simd and t not in SIMD_NATIVE and t not in ("17a", "17b"):
            if t in MEM_NO_COMPANION and not self.is_long(t, f) and not ("G12" in OFF and t in BY_WIDTH):
                return ("replace", lambda r: self.two_pass(r, insn, memory=True))
            if t in FLOW:
                if "compute[22:16]" in f:
                    return ("replace", lambda r: self.two_pass(r, insn, flow=True))
            elif "compute[22:16]" in f or t in ("5a_move", "5b_move") \
                    or (t == "6b_shiftimm" and cond_of(f) == 31 and "G16" not in OFF):
                return ("replace", lambda r: self.two_pass(r, insn, unscaled=blank))
        if blank and cond_of(f) == 31:
            return ("replace", lambda r: self.unscaled(r, insn))
        if t == "7b" and getattr(s, "assume_nw32", False) and "G13b" not in OFF \
                and l1_target(s, f):
            scale = width_7b(insn)
            if scale != 4:
                return ("replace", lambda r: self.modify_7b(r, insn, scale))
        if t in LOOP_ABORT_FORMS:
            return self.loop_abort(insn, s, pc) if F(f, "a") else None
        if t in ("4b", "3b"):
            return self.long_word(t, f, s, pc)
        if t == "13a":
            return ("replace", lambda r: self._halt(r, insn, "Type 13a is not executed (G7)"))
        if t in ("17a", "17b"):
            return self.imm_17a(t, f, s, pc)
        if t in COND_UNSUPPORTED and cond_of(f) not in (COND_NATIVE if t == "7a" else {31}):
            return ("replace", lambda r: self.conditional(r, insn))
        return None

    def unscaled(self, runner, insn):
        """G13: a MODIFY with no width selector, M added as bytes"""
        out = st._execute(dataclasses.replace(runner.state, assume_nw32=False), insn)
        if len(out) != 1 or out[0].stopped:
            raise sr.Halt("G13 unscaled MODIFY failed", runner.state.pc_sw, insn.type_name,
                          str(out[0].stopped if out else ""))
        runner.state = dataclasses.replace(out[0], assume_nw32=True)
        runner.instructions += 1
        self.note("blank MODIFY unscaled (G13)", runner.state.pc_sw)

    def modify_7b(self, runner, insn, scale):
        """G13: Type 7b MODIFY by its width selector: blank adds M as bytes, (sw) as short words"""
        s = runner.state
        f = insn.fields
        bank = 8 if F(f, "g") else 0
        src = ((F(f, "is[2:2]") << 2) | F(f, "is[1:0]")) + bank
        dst = (((F(f, "is[2:2]") << 2) | F(f, "is[1:0]")) ^ F(f, "idis")) + bank
        mv, lv = s.uregs[32 + F(f, "m") + bank], s.uregs[UREG_CODES["L%d" % src]]
        taken = cond_of(f) == 31 or seq._predicate(s, cond_of(f)) is True
        if scale == 2 and taken and not (isinstance(lv, Const) and lv.value == 0):
            raise sr.Halt("G13: a circular (sw) MODIFY", s.pc_sw, insn.type_name)
        out = st._execute(dataclasses.replace(s, assume_nw32=False), insn)
        if len(out) != 1 or out[0].stopped:
            raise sr.Halt("G13 7b MODIFY failed", s.pc_sw, insn.type_name, str(out[0].stopped if out else ""))
        x = dataclasses.replace(out[0], assume_nw32=True)
        if scale == 2 and taken:
            iv = x.uregs[16 + dst]
            if not (isinstance(iv, Const) and isinstance(mv, Const)):
                raise sr.Halt("G13: (sw) MODIFY on a value not concrete", s.pc_sw, insn.type_name)
            x.uregs[16 + dst] = Const((iv.value + mv.value) & 0xFFFFFFFF)
        runner.state = x
        runner.instructions += 1
        self.note(f"7b MODIFY x{scale} (G13)", s.pc_sw)

    @staticmethod
    def _halt(runner, insn, why):
        raise sr.Halt(why, runner.state.pc_sw, insn.type_name)

    @staticmethod
    def is_long(t, f) -> bool:
        if t in ("4b", "3b"):
            return ACCESS_WIDTHS.get((F(f, "l"), F(f, "x"), F(f, "w"))) == "long-word"
        if t in ("3a", "15b"):
            return bool(F(f, "l"))
        return False

    # -- G2 / G4: Type 17a ------------------------------------------------------------
    def imm_17a(self, t, f, s, pc):
        code = F(f, "ureg")
        if t == "17a":
            value = (F(f, "data[31:16]") << 16) | F(f, "data[15:0]")
        else:                                   # 17b: sign-extended 16-bit
            value = _signed(F(f, "data[15:0]"), 16) & 0xFFFFFFFF
        if self.simd_17a and code < 16 and simd(s):
            def post(r):
                r.state.uregs[code + 80] = Const(value)
                self.note("simd 17a/17b companion (G2)", pc)
            return post
        if t == "17a" and 16 <= code < 32 and NW_LO <= value < NW_HI:
            def post(r):
                r.state.uregs[code] = Const(4 * value)
                self.note("nw->byte I register (G4)", pc)
            return post
        return None

    # -- G6 ----------------------------------------------------------------------------
    def conditional(self, runner, insn):
        s = runner.state
        cond = cond_of(insn.fields)
        if simd(s):
            px, py = seq._predicate_pe(s, cond, "x"), seq._predicate_pe(s, cond, "y")
            if px != py:
                raise sr.Halt("SIMD conditional 6a/6b with differing PEs", s.pc_sw, insn.type_name)
            pred = px
        else:
            pred = seq._predicate(s, cond)
        if pred is None:
            raise sr.Halt("conditional predicate unknown", s.pc_sw, insn.type_name)
        if pred:
            key = [k for k in insn.fields if k.startswith("cond")][0]
            out = st._execute(s, dataclasses.replace(insn, fields={**insn.fields, key: 31}))
            if len(out) != 1 or out[0].stopped:
                raise sr.Halt("conditional emulation failed", s.pc_sw, insn.type_name)
            runner.state = out[0]
        else:
            runner.state = seq._advance(s, insn)[0]
        runner.instructions += 1
        self.note(f"conditional {insn.type_name} ({'G8' if insn.type_name == '7a' else 'G6'})", s.pc_sw)

    # -- G10 -----------------------------------------------------------------------------
    def loop_abort(self, insn, s, pc):
        cond = cond_of(insn.fields)
        pred = True if cond == 31 else seq._predicate(s, cond)
        if pred is None:
            return ("replace", lambda r: self._halt(r, insn, "JUMP (LA) predicate unknown (G10)"))
        if not pred:
            return None

        def post(r):
            seq._apply_loop_abort(r.state)
            self.note("jump (LA) loop abort (G10)", pc)
        return post

    # -- G3 ------------------------------------------------------------------------------
    def long_word(self, t, f, s, pc):
        if not self.is_long(t, f):
            return None
        if cond_of(f) != 31 and seq._predicate(s, cond_of(f)) is not True:
            return None
        if F(f, "g"):
            return None
        iv = s.uregs[16 + F(f, "i")]
        if not isinstance(iv, Const):
            return None
        if t == "4b":
            mod = _signed((F(f, "data[5:5]") << 5) | F(f, "data[4:0]"), 6)
            code = F(f, "dreg")
        else:
            mv = s.uregs[32 + F(f, "m")]
            if not isinstance(mv, Const):
                return None
            mod = _signed(mv.value, 32)
            code = F(f, "ureg")
        addr = iv.value if F(f, "u") else (iv.value + mod * 8) & 0xFFFFFFFF
        # G14: a post-modify's update through an index into L1's normal-word space (its byte image, as G4 maps it)
        # or into DDR counts normal words (x 4), not long words (x 8)
        ireg, new_i = 16 + F(f, "i"), (iv.value + mod * 4) & 0xFFFFFFFF
        in_nw = NW_LO * 4 <= iv.value < NW_HI * 4 or (DDR_LO <= iv.value < DDR_HI and "G14d" not in OFF)

        def index(r):                           # G14: the post-modify's own update, in normal words
            if F(f, "u") and in_nw and "G14" not in OFF:
                r.state.uregs[ireg] = Const(new_i)
        if F(f, "d"):
            _, values = fm._lw_store_pair(dict(s.uregs), code)

            def post(r):
                for k, v in enumerate(values):
                    _dm_write(r.state, addr + 4 * k, 4, v)
                index(r)
                self.note(f"lw store {t} (G3)", pc)
            return post
        codes = fm._lw_load_codes(code)

        def post(r):
            for k, c in enumerate(codes):
                v = _dm_read(r.state, addr + 4 * k, 4)
                if v is not None:
                    r.state.uregs[c] = v
            index(r)
            self.note(f"lw load {t} (G3)", pc)
        return post

    # -- G1 ------------------------------------------------------------------------------
    def two_pass(self, runner, insn, memory=False, flow=False, unscaled=False):
        s = runner.state
        if unscaled:                                # G13 in SIMD: both passes add M as bytes
            s = runner.state = dataclasses.replace(s, assume_nw32=False)
        m1 = UREG_CODES["MODE1"]
        mode1 = s.uregs[m1]
        sisd = Const(mode1.value & ~(1 << 21))
        f = insn.fields
        uy = dict(s.uregs)
        swap(uy)
        uy[m1] = sisd
        comp = False
        if memory:
            # the 16-bit Type 3c names its DAG fields dmi/dmm and is always DM
            idx = (16 + F(f, "dmi")) if "dmi[2:0]" in f else \
                16 + F(f, "i") + (8 if F(f, "g") else 0)
            iv = uy[idx]
            if not isinstance(iv, Const):
                raise sr.Halt("two-pass: I register not concrete", s.pc_sw, insn.type_name)
            step = 4
            if insn.type_name in BY_WIDTH:
                step = WIDTH_BYTES.get(ACCESS_WIDTHS.get((F(f, "l"), F(f, "x"), F(f, "w"))), 4)
            uy[idx] = Const((iv.value + step) & 0xFFFFFFFF)
            code = F(f, "dreg") if "dreg[3:0]" in f else F(f, "ureg")
            comp = fm._cureg_code(code) is not None
        # PEy's multiplier result registers are MSF/MSB: give them to the
        # SISD pass under PEx's names, and take them back afterwards
        sp = dict(s.special)
        for a, b in MR_PAIRS:
            sp[a], sp[b] = s.special.get(b), s.special.get(a)
        sy = dataclasses.replace(s, uregs=uy, trace=[], overlay=COW(s.overlay),
                                 call_stack=list(s.call_stack), loops=list(s.loops),
                                 status_stack=list(s.status_stack), mmrs=dict(s.mmrs),
                                 special={k: v for k, v in sp.items() if v is not None})
        oy = st._execute(sy, insn)
        if not flow:
            s.uregs[m1] = sisd
        ox = st._execute(s, insn)
        if flow and len(ox) == 1 and oy:
            oy = oy[:1]
            oy[0].stopped = None
        if len(ox) != 1 or len(oy) != 1 or ox[0].stopped or oy[0].stopped:
            raise sr.Halt("two-pass SIMD emulation failed", s.pc_sw, insn.type_name,
                          "%s / %s" % (ox[0].stopped if ox else "", oy[0].stopped if oy else ""))
        x, y = ox[0], oy[0]
        swap(y.uregs)
        for _, b in _pairs():
            x.uregs[b] = y.uregs[b]
        if x.uregs[m1] == sisd:
            x.uregs[m1] = mode1
        for a, b in MR_PAIRS:
            if a in y.special:
                x.special[b] = y.special[a]
        # G12: a 3d/4d store of a register with no PEy complement (M13 in the trig cells' clear) stores the same
        # register at the companion address too: the firmware clears the odd cells with it
        # G17: so does every memory form's store of such a register (the output stage's clear of the per-track
        # buffers stores M12 in SIMD through 15b, 3a and 3b: without it their odd words were never cleared)
        if memory and (comp or insn.type_name in BY_WIDTH or "G17" not in OFF) and isinstance(y.overlay, COW):
            own = y.overlay.own()
            if own:
                x.overlay.update(own)
        if unscaled:
            x = dataclasses.replace(x, assume_nw32=True)
        runner.state = x
        runner.instructions += 1
        self.note("simd two-pass (G1)", s.pc_sw)


def as_2c(insn):
    """G5: re-read a mis-sized Type 2b as the 16-bit Type 2c its first parcel is."""
    first = (insn.raw >> 16) & 0xFFFF
    return dataclasses.replace(insn, length_bytes=2, type_name="2c", raw=first,
                               fields={"compute[11:0]": first & 0xFFF}, note="G5: read as 2c")


def run(runner, max_steps: int, fix: Fixups, stop_at=()):
    """Step RUNNER with FIX. -> ("stop", pc, n) | ("halt", Halt, n) | ("max", pc, n)."""
    stop_at = set(stop_at)
    n = 0
    while n < max_steps:
        pc = runner.state.pc_sw
        if pc in stop_at and n:
            return ("stop", pc, n)
        fix.last.append(pc)
        if pc in fix.skips:
            runner.state.pc_sw = fix.skips[pc]
            fix.note("skip", pc)
            continue
        if pc in fix.hooks:
            runner.steps_n = n                  # v0.32: a hook may read the block's count so far
            fix.hooks[pc](runner)
            if runner.state.pc_sw != pc:
                n += 1
                continue
        insn = runner._decode(pc)
        if insn.type_name == "2b" and pc in AS_2C:
            insn = as_2c(insn)
            runner._cache[pc] = insn
            fix.note("2b->2c decode (G5)", pc)
        act = fix.pre(runner, insn)
        g11 = fext_se_fix(runner, insn, fix) if insn.type_name in FEXT_SE_FORMS else None
        if isinstance(act, tuple):
            try:
                act[1](runner)
            except sr.Halt as h:
                return ("halt", h, n)
            if g11:
                g11(runner)
            n += 1
            continue
        try:
            runner.step()
        except sr.Halt as h:
            return ("halt", h, n)
        if act:
            act(runner)
        if g11:
            g11(runner)
        n += 1
    return ("max", runner.state.pc_sw, n)


# -- G11 --------------------------------------------------------------------------------

FEXT_SE_FORMS = {"6b_shiftimm", "6a_mem"}
FEXT_SE = 0x12


def fext_se_fields(fields) -> tuple[int, int, int, int] | None:
    """(rn, rx, position, length) of a ShiftImm FEXT (SE), else None -- the same
    field packing digikit's `_shift_immediate` reads."""
    try:
        field = (fields["shiftimm[22:16]"] << 16) | fields["shiftimm[15:0]"]
    except KeyError:
        return None
    if (field >> 16) & 0x3F != FEXT_SE:
        return None
    data8 = (field >> 8) & 0xFF
    length = (fields.get("dataex[3:0]", 0) << 2) | (data8 >> 6)
    return (field >> 4) & 0xF, field & 0xF, data8 & 0x3F, length


def fext_se(value: int, position: int, length: int) -> int:
    """FEXT Rx BY position:length (SE), 32-bit result."""
    if length == 0:
        return 0
    length = min(length, 32)
    v = (value >> position) & ((1 << length) - 1)
    if v & (1 << (length - 1)):
        v -= 1 << length
    return v & 0xFFFFFFFF


def fext_se_fix(runner, insn, fix: "Fixups"):
    """G11: a post-step that rewrites Rn (and Sn in SIMD) with the masked,
    sign-extended field -- only if the step left the unmasked value there."""
    got = fext_se_fields(insn.fields)
    if got is None:
        return None
    rn, rx, pos, length = got
    s = runner.state
    pairs = [(rn, rx)] + ([(rn + 80, rx + 80)] if simd(s) else [])
    before = {}
    for dst, src in pairs:
        v = s.uregs.get(src)
        if isinstance(v, Const):
            before[dst] = v.value
    if not before:
        return None
    pc = s.pc_sw

    def post(r):
        for dst, src_val in before.items():
            buggy = _signed(src_val >> pos, min(length, 32)) & 0xFFFFFFFF if length else 0
            now = r.state.uregs.get(dst)
            if isinstance(now, Const) and now.value == buggy and buggy != fext_se(src_val, pos, length):
                r.state.uregs[dst] = Const(fext_se(src_val, pos, length))
                fix.note("fext (se) mask (G11)", pc)
    return post


# -- accelerations ---------------------------------------------------------------------

SIN = 0x1C10E4


def native_sin(runner) -> None:
    """A1: sw 0x1c10e4 (sinf: F4 -> F0, both PEs in SIMD) as float32(math.sin)."""
    s = runner.state
    u = s.uregs
    u[0] = as_const(math.sin(as_float(u[4])))
    if simd(s):
        u[80] = as_const(math.sin(as_float(u[84])))
    s.pc_sw = s.call_stack.pop()
    seq._sync_pc_stack(s)


# DO pc -> (first pc after the loop, stack slots (words from I6) of the
# harmonic number, the amplitude, and the running k the loop leaves behind)
ADDITIVE = {
    0x1C47BE: (0x1C47EA, -8, -6, -4),
    0x1C48E2: (0x1C490E, -8, -6, -4),
    0x1C4A0C: (0x1C4A38, -8, -4, -6),
}


def native_additive(runner) -> None:
    """A2: table[k] += a * sinf(h * ((k + 0.5) * 2pi) * 2^-10), k = 0..1023,
    float32 in the firmware's order; PEx does even k and PEy odd k, which is
    the same arithmetic on the same slots."""
    s = runner.state
    after, h_slot, a_slot, k_slot = ADDITIVE[s.pc_sw]
    i6 = s.uregs[UREG_CODES["I6"]].value
    rd = lambda a: _dm_read(s, a, 4).value   # noqa: E731
    fl = lambda w: struct.unpack("<f", struct.pack("<I", w))[0]   # noqa: E731
    h = fl(rd(i6 + 4 * h_slot))
    amp = fl(rd(i6 + 4 * a_slot))
    two_pi = fl(0x40C90FDB)
    base = s.uregs[UREG_CODES["I3"]].value   # each loop starts at I2 = modify(I3, M5)
    for k in range(1024):
        x = f32(f32(f32(k + 0.5) * two_pi) * 2.0 ** -10)
        v = f32(amp * f32(math.sin(f32(h * x))))
        a = base + 4 * k
        _dm_write(s, a, 4, as_const(f32(fl(rd(a)) + v)))
    _dm_write(s, i6 + 4 * k_slot, 4, Const(1024))
    _dm_write(s, i6 + 4 * k_slot + 4, 4, Const(1025))
    s.uregs[UREG_CODES["I2"]] = Const(base + 4096)
    s.pc_sw = after
