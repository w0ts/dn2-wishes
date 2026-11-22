# selas's encodings against ADI's (2026-11-12)

selas (selache, github.com/js216/selache, GPL-3.0; docs/sharc-selache.md) assembles every object of ours. On
2026-11-12 the runner's decode step showed it writing `MODIFY(I4, M4)` as `0x04240F800000`: selache's
"standard Type 7" layout (I 37:35, M 34:32, condition 27:23, bit 39 clear), a pre-SHARC+ one. In SHARC+ (VISA)
code a Type 7 word with bit 39 clear is the 32-bit Type 7b, so the DSP reads those bytes as
`if gt i7=modify (i0,m1)` (it would rewrite I7, the stack pointer) and the last 16 bits as another instruction.
ADI's own `i4=modify (i4,m6)(nw)` (Digitone II OS 1.12, sw `0x1c04bf`) is `0x04BF30000000`: condition 37:33,
Is {32, 31:30}, Mm 29:27, Id xor Is 26:24, bit 39 set. Nothing shipped used MODIFY (the FDN8 circular-buffer work,
docs/circ-unit-test.md, was the first).

## The fix

- **`tools/selache/0001-sharc-plus-type7a-modify-nw.patch`** (on selache 2b26d3b): `Id=MODIFY (Is,Mm)(NW)` and
  `MODIFY (Is,Mm)(NW)`, with or without a compute, are a new instruction (`DagModifyNw`) in the SHARC+ layout;
  in VISA code a MODIFY without `(NW)` keeps its 32-bit Type 7b (which matches ADI's, e.g. sw `0x1c0724`
  `if ne i5=modify (i4,m0)` = `0x04210193`) and is refused where it would be written as 48 bits; a destination
  other than the source without `(NW)`, silently dropped before, is refused. A selas test holds four forms to
  ADI's words. selache's own tests pass (its one failing doctest fails without the patch too).
- **`tools/selache/apply.sh SELACHE TARGET`** applies our patches to a selache checkout (idempotent) and
  rebuilds selas: on the farm `tools/selache/apply.sh $BENCH/Z/selache $BENCH/tools/selache-target`.
- **`sharc_waverider_m3.check_modify`**: every generator's assembly (`_selas`) refuses a MODIFY in any form but
  `Id=MODIFY (Is,Mm)(NW)`, and holds its bytes to the SHARC+ word computed apart (`modify_nw_word`), whatever
  selas the bench has.

## The cross-check: `scripts/selas_form_check.py STOCK.syx [--selas PATH]`

(On the bench: `runq.py submit --kind runner -- python scripts/selas_form_check.py {STOCK112}`.)

- **(a) ours, read back**: every object the build loads, decoded by selmap, against its source line (the
  runner's decode step covers only PERC, the sample machines, block_count and ping).
- **(b) each form against ADI**: every instruction form our objects use, and up to three stock instructions of
  that form assembled by selas: the same bytes, or bytes selmap reads as the same instruction (a variant), or a
  mismatch.

Today's code (rr-v0.48-ours-1.12 1c76fad3, bench selas and patched selas alike): (a) 17 objects, 54,356
instructions, **0 disagreements**; (b) 118 forms, **0 mismatches**, 272 instances the same bytes, 27 variants,
4 Type 6b shifts by an immediate (`fix_shift_imm` corrects them after selas), 9 forms stock never uses. The
variants: selas writes `comp`, `float`, `trunc`, `and`, `r=dm(i,m)`, `nop` in their 16/32-bit VISA forms where
ADI's code has 48 bits (both valid); and the stock "jumps" it was held to (`jump 0x3e7800`, `if ne jump
0x0f0000` ..) are data in the code blocks decoded as code (targets outside any code), so their extra bits say
nothing. The 9 forms with no stock counterpart (`r=r*r (ssf)` x220, conditional `pass` and `+`, ASTAT's
absolute load, a few multifunction compute + load forms) are held only by (a): selmap reads them as written.
Retired objects (Waverider's `reader`, `machine5`) read back wrong in places (`R0 = DM(I4, M0)` as
`m2=dm (0x14,i4)`) and are not loaded by any build.

SIMD forms (engine-layout's branch `simd`) need this check before they ship.

## Multifunction (multiply + ALU in one instruction): patch 0002 (2026-11-13)

`tools/selache/0002-sharc-plus-multifunction-float-categories.patch` (applied by `tools/selache/apply.sh`, which now
also runs its tests and, given a third argument, rebuilds selmap from the patched decoder). Against the ADSP-2156x
programming reference's Table 12-12 (digikit's `sharcspec/compute_table.json`, `multifn_mul_alu`):

- **selmap read the float categories as fixed-point MRF forms.** `F12 = F0 * F7, F8 = F8 + F12` (category 011000)
  printed as `F12 = MRF + F0 * F7 , ...`; the gate's decode step stripped the `MRF +` to compare. Now: the float
  categories 011000..011111 read as `Fm = Fx * Fy` with their ALU half (+, -, FLOAT BY, FIX BY, average, ABS,
  MAX, MIN); the fixed-point rows 0001xx..0101xx as the table gives them.
- **selas encoded the float average as 011010 (FLOAT BY) and the fixed-point rows one category low**, and read
  no MIN / MAX. Now: average 011100, MAX 011110, MIN 011111, the fixed rows 0001xx..0100xx; an MRF form in float
  is refused (the float multiplier has none).
- **selas dropped a multifunction's ALU half in silence** when its operands were outside the groups (multiplier
  F0-F3 x F4-F7, ALU F8-F11 and F12-F15): the line's error made the parser read it as another form, the
  multiply alone. Now a line whose second half is an ALU operation is a multifunction or an error.

What we emit (`dsl.Prog.par`, float + and - only, its own check `dnfw.perc.mf.verify`) was already right with the
old selas; the fixes are for selmap's reading and for the forms not yet used.

**Proof** (runq, the patched selas and selmap as `DNFW_SELAS` / `DNFW_SELMAP`, a tree whose Monomachine engines use
multifunction): the tree regenerated and assembled with the patched selas (every multifunction line's field
checked by `mf.verify`); `selas_form_check.py`: (a) 17 objects, 54,789 instructions, 0 disagreements (the
multifunction lines now read as written); (b) 126 forms, 287 matched against stock's bytes, 0 mismatched, among
them all seven multiply + add / subtract forms our code uses (alone, with a DM store, with a DM load, through an
offset or a modifier); the runner's decode and Monomachine steps PASS. selache's own tests: selinstr 152,
selas 173 (and 12 new ones on these forms) pass; its one failing doc test fails on the unpatched checkout too.

The shared bench toolchain is not updated by this commit: run `apply.sh` there once the integrator says so.

## Multifunction: the corpus, patch 0003, the wrapper and the gate check (2026-11-21)

**The corpus** (`scripts/mf_corpus.py STOCK.syx --digikit DIGIKIT/tools --skill SKILL/scripts --synthetic 20`, on the
farm with selas and selmap built from tools/selache): stock 1.12's code ranges walked by selmap's lengths, every
instruction digikit decodes with a compute field whose bit 22 is set (2,851 words; a linear walk, so some are data):
each read by digikit, by selmap, by complex-ping's `visa.compute` and by `dnfw.perc.mfcodec` (a third decoder and
encoder written from PGR Table 12-12; `test_perc_mfcodec` holds it to digikit's `compute_table.json`), then
re-encoded by selas twice: selmap's whole line (stock's bytes, or bytes selmap reads the same), and the compute
alone (its field against stock's, on the bits the operation reads, `mfcodec.care`). Plus 20 random fields of every
multifunction category, assembled from mfcodec's text and read back by all three, and 15 lines selas must refuse.

What it found, with patches 0001 + 0002 (the bench's selas of 2026-11-14):

| form | selas | decoders |
|---|---|---|
| float `Fm = Fx * Fy, Fa = FLOAT Rx BY Ry` / `Ra = FIX Fx BY Ry` / `Fa = ABS Fx` (011010, 011011, 011101) | **accepted and written as the multiply alone, in silence** (20/20 synthetic; stock's own in types 1a, 2a, 3a, 5a) | agree |
| multiply + dual add/subtract, the subtract's operands | **never read**: `F9 = F8 - F2` assembled as `F9 = F8 - F12`, in silence | agree |
| 64-bit pairs `F1:0 = F1:0 * F5:4, ...` | read as SIMD notation (`F1:0` -> F1: selache's documented reading), so a different 32-bit operation | - |
| fixed `Rm = MRF - Rx * Ry (SSFR)` (0101xx) | refused (safe) | agree |
| every other float form (+, -, average, MIN, MAX), every dual (fixed and float), every fixed MUL/ALU form | ADI's field, in every instruction type stock uses them in | selmap = digikit = visa = mfcodec, stock and synthetic |

Seen on the way, not multifunction (no object of ours uses them; v0.66.1 scanned, 2026-11-21): selas writes a
compute + ureg move (type 5a), a compute + indirect jump (type 9a: the compute dropped to a 4-byte word), an
`IF .. JUMP (PC, ..), ELSE compute, move` (type 10a) and a type 3 move of an S or B register (bit 40 / 32) other
than ADI does. selmap cannot print an MR data move (`multi opcode 0x00`) and prints the fixed dual's `(SSFR)` as
`(ssf)` (text only: no bit carries it). digikit and selmap disagree on 32-bit (type 2a short) words with bit 22 set;
selas never writes a multifunction in 32 bits (every synthetic one is 48), and `mf.verify` requires 48.

**Patch 0003** (`tools/selache/0003-sharc-plus-multifunction-convert-abs-dual-operands.patch`): FLOAT BY, FIX BY and
ABS as the ALU half (float only; FIX's result an R register) encoded as Table 12-12 gives them; a line whose ALU
half reads as FLOAT / FIX / ABS / an average is a multifunction or an error; a dual's subtract must read the add's
two operands. selache's tests pass (selas 152, selinstr 173; new cases on stock's own words, e.g. sw 0x1c101c
`f7=f0*f7 , r7=fix f11 by r15`). With it the corpus has no multifunction field selas writes differently from ADI,
the synthetic categories all agree, and the 15 must-refuse lines are refused. The bench's shared selas does not
have 0003 yet (`apply.sh` there when the integrator says so); the wrapper below keeps a build safe either way.

**The wrapper** (`dnfw.perc.mf.verify`, run by every `sharc_waverider_m3._selas`): any source line with two compute
operations (`mf.classify`, by its text) must be a form in `mf.PROVEN` — the float multiply with +, -, average,
FLOAT BY, ABS, MIN, MAX, and the float dual add/subtract, the categories digikit's emulator runs (so the SHARC runner
can prove a rewrite) — with no condition and at most one DM load / store through I0..I3; it must assemble to 48
bits and carry exactly the field mfcodec computes from the text. FIX BY (digikit does not run it), every fixed-point
form (digikit runs none) and register pairs are refused.

**The gate check** (`scripts/gate_mf.py BUILD.syx DIGIKIT`, in ship_gate's `hwrules` step as "DSP multifunction
words"): in the build's own section 7, every object of ours (its committed bytes, at its load address): each
multifunction line is a proven form, 48 bits in digikit and in selmap, digikit's field the text's, selmap's text the
text's compute; and no other word carries a multifunction field. v0.66.1 (934b798b): PASS, 17 objects, 503
instructions. One bit flipped in a register or the category of an inspost word: FAIL, naming the line.

XOR (asked the same day): stock 1.12 uses `Rn = Rx XOR Ry` 69 times (67 as the 16-bit short compute); selas writes
all 69 as stock's bytes; selmap and digikit agree; digikit's emulator runs both forms (ALU 0x42, short 1110).
