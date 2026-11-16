# SIMD in our DSP code (2026-11-12)

The SHARC has two processing elements: PEx (registers R0..R15) and PEy (S0..S15). With MODE1.PEYEN set
(SIMD mode), every instruction runs on both at once. A memory move into or out of an R register also moves the
matching S register, from or to the next word (Ia + 1, a normal word). Two independent computations that run
the same instructions on data one word apart cost the instructions of one.

## In the DSL: `Prog.simd(body)`

```python
p.simd(lambda: body(p))       # BIT SET MODE1 PEYEN; NOP; body; BIT CLR MODE1 PEYEN; NOP
```

- **BODY is straight-line**: no `if_`, `loop*`, `jump` or `call`, no constant load (`fconst`/`iconst`: whether
  `Rn = data32` reaches Sn is only inferred from the firmware), no I/M/L/B register write, no mode write. The
  DSL refuses these (`SIMD_REFUSE`, `_no_simd`), in emit mode and in run mode.
- **Data for PEy is the next word.** Every value PEy needs comes from memory through a move inside BODY. A
  constant goes in memory twice (or once in each lane's slot); the S registers start each region as POISON (a
  NaN), so a lane that uses a register it did not load gives a different output, and the model tests see it.
- **Same operations per lane, in the same order**, so each lane's floats are the scalar program's, bit for
  bit. A sum across lanes (two modes into one output) must still be done in the scalar order. Do it after the
  region, in SISD (PLAITS MDAL's `_batch_sum`).
- **Run mode** runs BODY twice: on PEx, then on PEy from the same I registers with the memory one word on. It
  holds it to what the core does in one pass: the same instruction text on both lanes, the same I registers
  after, and neither lane touching a word the other wrote. `steps` counts the instructions once.
- **Moves** that work: `ldi`/`sti` (`DM(k, Ii)`), `ldpost`/`stpost`, `par`'s and msched's `ld`/`ldk`/`st`/`stk`.
  For stepping over interleaved pairs, use offsets (`2 k`), not M6 post-modify (one word).
- **Cost**: the body once, plus 4 (the switch and its NOPs). The NOPs are conservative: the MODE1 effect
  latency of the stock's own sequence is not checked.

## The proof for a change

1. The model, bit for bit: the engine's output words over many knob settings, notes and retriggers, the same
   before and after (scratch `model_bits.py` in the simd session: sha256 per case).
2. The SHARC runner, with the emitted code bit-exact to the model (`run_blocks`/`perc_exact`) and the decode
   step (digikit and selmap read every new instruction alike).
3. `scripts/dsp_cost.py` (opt-host's) before and after.

## The SHARC runner's SIMD

digikit runs PEy itself in only five instruction forms. Our `scripts/sharc_dn2_fixups.py` "G1 two-pass" runs
the rest: PEy on a copy with R and S swapped and the moves a word on, then PEx. It is a stand-in, not a model
(`docs/for-digikit-sharc-runner-dn2.md` sections 6, 7 and 12). Known gaps:

- a conditional 6a/6b whose lanes differ halts;
- a SIMD branch whose lanes disagree is not handled;
- MRF/MSF are only partly per lane;
- broadcast loads are absent.

**Our SIMD has not run on the unit.**

## First use: PLAITS MDAL (two modes at once)

Modes m and m + 1 on PEx and PEy:

- their states are already neighbours in the slot;
- `coefs` interleaves their coefficients (a pair's fields at `2 x field + lane`);
- the excitation row holds each sample twice;
- each mode writes its 16 outputs to its own column of the O rows;
- `_batch_sum` adds each batch of 4 in Plaits' order.

Measured (2026-11-12, base 2f122922):

- the model is bit-identical over 8 knob settings × 60 blocks;
- `dsp_cost.py` steady: engine 15,914 → 12,562, voice 18,243 → 14,891;
- code +79 instructions (+524 bytes).
