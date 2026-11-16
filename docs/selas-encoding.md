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
  rebuilds selas: on the farm `tools/selache/apply.sh ~/dn2mk2-bench/Z/selache ~/dn2mk2-bench/tools/selache-target`.
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
