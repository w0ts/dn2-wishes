# What each engine costs the DSP, one method for all (2026-11-12, main f649683c)

**The method** (`python3 scripts/dsp_cost.py --steps cost[,host] [--only NAME,..]`, about a minute for all 61):
one voice of the engine on track 0, run in the program's model (`dnfw.perc.program.voice`; the sample machines'
`dnfw.sampler.program.voice`), on the unit's memory map (track buffers in L1, as `trackbuf.asm` puts them). Cost =
instructions + 4 x L2 + 10 x DDR accesses, as below. The model's count is made instruction-exact: emit mode's
constant elision and its zero-scale pass are mirrored, every jump, call and the engine dispatch counted.
Blocks: a fresh voice, notes on blocks 1 and 8; **steady** the mean of blocks 4..7, **trig** the dearer of 8, 9 (a
retrigger), **start** the dearer of 1, 2 (the first note: the machine's init). **Host** is everything in the voice
but the engine (the frame's records, the stream move, the resampler and level, the quiet test, the budget, the
track effects, the output guard); **engine** is the machine's own code (render, trig, init and its knob scaling),
told apart by the call stack. Report: `out/dsp_cost/report.json`; `--md FILE` writes the table.

**Checked against the assembled code** (`scripts/sharc_cost.py`, the SHARC runner, split by perc.json's addresses):
engines equal to +-2 for TRX-CY, EFM-CY, GND-IM, PI-SD, SOPHIE, PLAITS ADD and MDAL, SID, DDRW, VO-6 (TB303 +129 and
ANALOG2 +636 in the runner: its frames carry page-2/3 words the model's harness leaves at 0; not chased); host the
model's + 36 (the guard's own instructions inside the measured span) + 960 (the runner never runs `trackbuf.asm`,
so its track buffers stay in DDR: 96 accesses a voice the unit does not make).

**Around the voices** (runner, main, per block; not in the table): PERC's entry 4,846 with no voice of ours
(`mnm_ages` for 16 slots, the guard's entry), the slot loop 1,305, the sample machines' loop 8,115 (the recorder and
the fast link): **~14,300 a block, fixed**. Each voice adds ~330 to the slot loop (its guard) and ~520 to the entry
(`mnm_ages`' quiet test of its buffer, ~320 of it the runner's DDR buffers): **~530 a voice on the unit**.
The "~14,700 for the voice" noted in MNM_COST's comments is not the host's per-voice cost: the host is ~2,400 a
voice; the ~14,300 is the block's fixed work, paid once whatever the voice count.

**The stock machines** (runner, the whole block with track 0 on the machine less the same with it on MIDI):
FM TONE 14,626, FM DRUM 10,998, WAVETONE 9,980, SWARMER 5,228 a block (they render every block, note or not).

**16 voices with room** (the brief: our voices get ~310,000 a frame): 16 x (steady + 530) + 14,300 <= 310,000 needs
steady <= ~17,950; at 75 % of it (232,500), **steady <= ~13,100 a voice-block**. "voices in 310k" below is 310,000 /
steady (no fixed work): an upper bound.

| engine | family | steady | host | engine's own | host share | trig | start | voices in 310k | 16 voices, of 310k | steady after opt-host | voices after |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VO-6 | MONOMACHINE | 35,312 | 2,423 | 32,888 | 7 % | 34,529 | 40,661 | 8 | 182 % | 34,830 | 8 |
| DPRO-DDRW | MONOMACHINE | 33,618 | 2,419 | 31,199 | 7 % | 33,665 | 33,931 | 9 | 174 % | 33,137 | 9 |
| TB303 | TB303 | 29,013 | 2,329 | 26,684 | 8 % | 29,194 | 29,478 | 10 | 150 % | 28,544 | 10 |
| SID 6581 | MONOMACHINE | 28,440 | 2,415 | 26,025 | 8 % | 28,513 | 28,592 | 10 | 147 % | 27,959 | 11 |
| DPRO-DENS | MONOMACHINE | 20,731 | 2,421 | 18,310 | 12 % | 20,794 | 20,991 | 14 | 107 % | 20,250 | 15 |
| PLAITS-MDAL | PLAITS | 20,499 | 2,329 | 18,170 | 11 % | 20,636 | 20,817 | 15 | 106 % | 20,030 | 15 |
| WERP | SAMPLE | 19,965 | (own) | - | - | 40,039 | 20,422 | 15 | 103 % | 19,965 | 15 |
| REPITCH | SAMPLE | 19,754 | (own) | - | - | 40,086 | 20,326 | 15 | 102 % | 19,754 | 15 |
| ONESHOT | SAMPLE | 19,592 | (own) | - | - | 39,552 | 19,896 | 15 | 101 % | 19,592 | 15 |
| SLICE | SAMPLE | 19,468 | (own) | - | - | 39,405 | 19,884 | 15 | 100 % | 19,468 | 15 |
| GRID | SAMPLE | 19,463 | (own) | - | - | 39,495 | 19,979 | 15 | 100 % | 19,463 | 15 |
| TRX-CY | TRX | 18,326 | 2,429 | 15,896 | 13 % | 19,993 | 20,729 | 16 | 95 % | 17,838 | 17 |
| DPRO-WAVE | MONOMACHINE | 18,146 | 2,417 | 15,730 | 13 % | 18,219 | 18,295 | 17 | 94 % | 17,666 | 17 |
| PLAITS-STRG | PLAITS | 17,902 | 2,330 | 15,572 | 13 % | 16,376 | 14,301 | 17 | 92 % | 17,434 | 17 |
| EFM-CY | EFM | 17,571 | 2,429 | 15,142 | 14 % | 17,803 | 18,018 | 17 | 91 % | 17,084 | 18 |
| SOPHIE | SOPHIE | 17,254 | 2,329 | 14,926 | 13 % | 17,469 | 17,577 | 17 | 89 % | 16,786 | 18 |
| PI-ML | PI | 17,182 | 2,429 | 14,752 | 14 % | 17,285 | 17,557 | 18 | 89 % | 16,694 | 18 |
| PI-SD | PI | 17,057 | 2,429 | 14,628 | 14 % | 17,201 | 17,383 | 18 | 88 % | 16,570 | 18 |
| PI-CC | PI | 16,692 | 2,429 | 14,264 | 15 % | 18,090 | 19,951 | 18 | 86 % | 16,206 | 19 |
| PI-RS | PI | 16,685 | 2,429 | 14,256 | 15 % | 16,810 | 16,973 | 18 | 86 % | 16,198 | 19 |
| PI-RC | PI | 16,654 | 2,429 | 14,225 | 15 % | 17,040 | 18,922 | 18 | 86 % | 16,167 | 19 |
| PI-MT | PI | 16,525 | 2,429 | 14,096 | 15 % | 16,658 | 16,836 | 18 | 85 % | 16,038 | 19 |
| PLAITS-FM | PLAITS | 16,511 | 2,329 | 14,182 | 14 % | 16,580 | 16,748 | 18 | 85 % | 16,042 | 19 |
| PI-HH | PI | 15,152 | 2,429 | 12,722 | 16 % | 16,463 | 18,297 | 20 | 78 % | 14,664 | 21 |
| PLAITS-ADD | PLAITS | 14,775 | 2,329 | 12,446 | 16 % | 14,844 | 15,202 | 20 | 76 % | 14,306 | 21 |
| PI-BD | PI | 14,562 | 2,429 | 12,133 | 17 % | 14,680 | 14,848 | 21 | 75 % | 14,075 | 22 |
| PLAITS-PART | PLAITS | 14,061 | 2,331 | 11,730 | 17 % | 14,130 | 14,356 | 22 | 73 % | 13,592 | 22 |
| TRX-S2 | TRX | 13,677 | 2,429 | 11,248 | 18 % | 13,678 | 5,492 | 22 | 71 % | 13,190 | 23 |
| TRX-CH | TRX | 13,560 | 2,429 | 11,130 | 18 % | 14,213 | 14,622 | 22 | 70 % | 13,072 | 23 |
| TRX-OH | TRX | 13,560 | 2,429 | 11,130 | 18 % | 14,228 | 14,652 | 22 | 70 % | 13,072 | 23 |
| EFM-RS | EFM | 13,327 | 2,429 | 10,898 | 18 % | 13,523 | 13,707 | 23 | 69 % | 12,840 | 24 |
| EFM-CB | EFM | 13,323 | 2,429 | 10,894 | 18 % | 13,512 | 13,689 | 23 | 69 % | 12,836 | 24 |
| TRX-MA | TRX | 12,619 | 2,429 | 10,190 | 19 % | 13,491 | 13,810 | 24 | 65 % | 12,132 | 25 |
| PLAITS-SD | PLAITS | 12,215 | 2,329 | 9,886 | 19 % | 12,482 | 12,781 | 25 | 63 % | 11,746 | 26 |
| PLAITS-SWRM | PLAITS | 12,090 | 2,329 | 9,762 | 19 % | 12,659 | 13,311 | 25 | 62 % | 11,622 | 26 |
| TRX-CP | TRX | 11,563 | 2,429 | 9,134 | 21 % | 12,277 | 13,010 | 26 | 60 % | 11,076 | 27 |
| EFM-SD | EFM | 10,871 | 2,429 | 8,442 | 22 % | 11,060 | 11,237 | 28 | 56 % | 10,384 | 29 |
| PLAITS-BD | PLAITS | 10,828 | 2,329 | 8,499 | 22 % | 10,842 | 10,391 | 28 | 56 % | 10,359 | 29 |
| PLAITS-WS | PLAITS | 10,442 | 2,329 | 8,113 | 22 % | 10,558 | 10,648 | 29 | 54 % | 9,973 | 31 |
| EFM-HH | EFM | 10,349 | 2,429 | 7,920 | 23 % | 10,541 | 10,721 | 29 | 53 % | 9,862 | 31 |
| DRONE | DRONE | 10,103 | 2,488 | 7,615 | 25 % | 9,978 | 11,638 | 30 | 52 % | 9,548 | 32 |
| EFM-CP | EFM | 10,040 | 2,429 | 7,611 | 24 % | 10,222 | 10,396 | 30 | 52 % | 9,553 | 32 |
| EFM-XT | EFM | 9,951 | 2,429 | 7,522 | 24 % | 10,132 | 10,298 | 31 | 51 % | 9,464 | 32 |
| PLAITS-VA | PLAITS | 9,737 | 2,329 | 7,408 | 24 % | 9,718 | 9,896 | 31 | 50 % | 9,268 | 33 |
| PLAITS-NOIS | PLAITS | 8,795 | 2,329 | 6,466 | 26 % | 8,894 | 9,068 | 35 | 45 % | 8,326 | 37 |
| PLAITS-HH | PLAITS | 8,749 | 2,329 | 6,420 | 27 % | 8,856 | 9,067 | 35 | 45 % | 8,280 | 37 |
| EFM-BD | EFM | 8,627 | 2,429 | 6,198 | 28 % | 8,807 | 8,975 | 35 | 44 % | 8,140 | 38 |
| STRETCH | SAMPLE | 8,192 | (own) | - | - | 16,738 | 8,540 | 37 | 42 % | 8,192 | 37 |
| TRX-CB | TRX | 8,131 | 2,430 | 5,702 | 30 % | 3,451 | 3,995 | 38 | 42 % | 7,644 | 40 |
| TRX-SD | TRX | 7,780 | 2,429 | 5,351 | 31 % | 8,005 | 8,217 | 39 | 40 % | 7,293 | 42 |
| TRX-RS | TRX | 7,609 | 2,429 | 5,180 | 32 % | 7,762 | 7,784 | 40 | 39 % | 7,122 | 43 |
| PI-MA | PI | 7,526 | 2,429 | 5,097 | 32 % | 7,748 | 7,971 | 41 | 39 % | 7,039 | 44 |
| TRX-B2 | TRX | 6,611 | 2,429 | 4,182 | 37 % | 6,845 | 6,937 | 46 | 34 % | 6,124 | 50 |
| ANALOG2 | ANALOG2 | 6,541 | 2,533 | 4,008 | 39 % | 6,656 | 7,066 | 47 | 34 % | 5,962 | 51 |
| TRX-CL | TRX | 5,956 | 2,429 | 3,526 | 41 % | 6,104 | 6,255 | 52 | 31 % | 5,468 | 56 |
| TRX-BD | TRX | 4,184 | 2,429 | 1,755 | 58 % | 4,184 | 3,305 | 74 | 22 % | 3,697 | 83 |
| TRX-XT | TRX | 4,072 | 2,429 | 1,644 | 60 % | 3,187 | 2,964 | 76 | 21 % | 3,586 | 86 |
| TRX-XC | TRX | 4,072 | 2,429 | 1,644 | 60 % | 2,818 | 2,962 | 76 | 21 % | 3,586 | 86 |
| GND-SN | GND | 3,623 | 2,429 | 1,194 | 67 % | 3,727 | 3,832 | 85 | 19 % | 3,136 | 98 |
| GND-NS | GND | 3,139 | 2,429 | 710 | 77 % | 3,193 | 3,255 | 98 | 16 % | 2,652 | 116 |
| GND-IM | GND | 2,821 | 2,431 | 390 | 86 % | 2,966 | 3,047 | 109 | 15 % | 2,334 | 132 |

(steady after opt-host: the host changes of the next section, engines untouched.)

## The voice host cut (opt-host, 2026-11-12, commit bf2639fd, bit-identical)

Every PERC voice (Machinedrum, Monomachine, SOPHIE, PLAITS, TB303, DRONE, ANALOG 2) is 469..579 cheaper a block:
host 2,429 -> 1,942 (Machinedrum), 2,329 -> 1,860 (the others), -20 %; `mnm_ages` 4,906 -> ~2,350 a block (model,
16 slots, one voice). The same operations on the same values, reordered or held in registers:

| part | before | after | how |
|---|---:|---:|---|
| resampler (32 samples) | 1,174 | 1,017 | the four stream loads ride on computes, 4.0 held in F7, the sample stored through I2 beside the position's add: 36 -> 31 a sample |
| frame records (MD 16, others 9) | 368 / 222 | 154 / 84 | `frame_regs` / `frame_byte`: I1, I0 and two shift counts set once a voice (a record's half depends only on its offset and the slot's parity), not half()'s address arithmetic each record |
| output guard | 226 | 178 | the samples alternately in R0 / R2 through I1: the next load and the store ride on computes |
| track effects (MD, all off) | 109 | 55 | the AM step's exp2 only when AM is on (only the AM pass reads it) |
| quiet test (peak32) | 146 | 122 | the next word loaded beside the MAX, through I1 (also in mnm_ages' listen) |
| knob inputs | 112 | 84 | the four constants in registers |
| Monomachine budget | 141 | 22 | one word: `mnm_ages` sums the costs in key order (CUM_OFF, free L2 scratch) in a block with a Monomachine slot |
| mnm_ages' order | ~2,900 | ~1,300 | six keys at a time in registers, a compare and a conditional add each (new DSL op `comp_iop_if`, the stock's `IF cond R = R +- R` form): 48 L2 key reads, not 256 |
| mnm_ages' slots | ~2,000 | ~1,000 | ours / Monomachine by one bit of two masks, slot index in I0, count in R15 (the L2 words left as before) |
| slot loop (16 slots) | - | -~20 a slot | the record pointer it set (read by nothing) gone; PERC or Monomachine by one bit (VOICE_MASK) |

Code: perc.asm 39,264 -> 38,946 instructions, 170,102 bytes (about 1.8 KB freed in PERC's L2 span).
Proof: `scripts/perc_host_identity.py` (every engine through mnm_ages + the voice, three voices at once on both
slot parities, notes, knobs, effects, a machine change, rests, a NaN wipe, every type word on the other tracks;
outputs and the voices' state hashed): 58 of 58 identical to main. Unit tests test_perc_live, test_perc_mf,
test_md, test_mnm: the same 448 pass and the same 4 fail on main. Hardware rules on the regenerated section 7: PASS.
On the regenerated tree (the farm, 2026-11-12): runner decode, map, voice, guard, garbage, wipe 50/50 PASS; mnm,
frame, stress, chords, smp 51 PASS and 1 FAIL, `v0.18: ONESHOT plays KICK from the pool` (sample machines), which
fails the same on main f649683c (smp step run there). Measured in the runner after: TRX-CY's host 3,425 -> 2,938
(runner map), PERC's entry 4,846 -> 2,317 with no voice and 13,128 -> 10,199 with 16, the slot loop 1,305 -> 953
and 6,617 -> 6,265: with 16 voices ~11,100 a block less for the host and the loop around it.

What is left in the host (after): the resampler 1,017 (31 a sample; multifunction would need a new register plan),
the stream's move 145 (35 words copied a block; a ring would change the voice's state layout), the output guard
178, the voice's own set-up ~160. Not ours: the sample machines' loop (8,115 a block, the recorder and link).

## What each machine costs the DSP (v0.39 source, measured 2026-11-03; v0.33 table below it)

One voice of each machine sounding, eight blocks after its note, in the SHARC runner
(`scripts/sharc_waverider_m5.py --steps cost`, step 3c), less a run with nothing sounding.
Per block (32 samples): the instructions our code runs, and its memory accesses by where they
land. On the unit an access to L2 costs several instruction times and one to DDR about ten
(complex-ping's measurements, `docs/others-dn2-research.md`); the estimate is instructions +
4 x L2 + 10 x DDR, against the frame's 666,667 cycles. It is an estimate: the unit's meter
(FUNC held on a PERC or Monomachine page) is the measure.

| machine | instructions | L2 accesses | DDR accesses | estimate | of the frame |
|---|---|---|---|---|---|
| SID 6581 | 29,507 | 7,046 | 0 | 57,691 | 8.7 % |
| DPRO-DDRW | 25,876 | 6,839 | 217 | 55,402 | 8.3 % |
| VO-6 | 30,838 | 3,845 | 171 | 47,928 | 7.2 % |
| PI-SD | 15,033 | 110 | 1,803 | 33,503 | 5.0 % |
| PI-RS | 14,766 | 108 | 1,779 | 32,988 | 4.9 % |
| TRX-CY | 20,646 | 2,434 | 144 | 31,822 | 4.8 % |
| EFM-CY | 20,224 | 2,246 | 188 | 31,088 | 4.7 % |
| DPRO-DENS | 14,259 | 3,681 | 162 | 30,603 | 4.6 % |
| DPRO-WAVE | 13,179 | 2,728 | 187 | 25,961 | 3.9 % |
| TRX-MA | 15,091 | 2,347 | 0 | 24,479 | 3.7 % |
| PI-MT | 13,924 | 497 | 783 | 23,742 | 3.6 % |
| TRX-CP | 15,175 | 1,985 | 0 | 23,115 | 3.5 % |
| TRX-S2 | 15,426 | 1,629 | 37 | 22,312 | 3.3 % |
| PI-BD | 11,755 | 478 | 729 | 20,957 | 3.1 % |
| EFM-CB | 13,004 | 1,757 | 92 | 20,952 | 3.1 % |
| PI-ML | 14,060 | 1,073 | 68 | 19,032 | 2.9 % |
| EFM-RS | 11,372 | 1,660 | 92 | 18,932 | 2.8 % |
| TRX-OH | 11,691 | 1,268 | 141 | 18,173 | 2.7 % |
| TRX-CH | 11,685 | 1,268 | 141 | 18,167 | 2.7 % |
| WERP | 5,320 | 0 | 1,253 | 17,850 | 2.7 % |
| REPITCH | 5,211 | 0 | 1,253 | 17,741 | 2.7 % |
| ONESHOT | 5,001 | 0 | 1,253 | 17,531 | 2.6 % |
| SLICE | 4,948 | 0 | 1,254 | 17,488 | 2.6 % |
| GRID | 4,913 | 0 | 1,253 | 17,443 | 2.6 % |
| PI-CC | 8,575 | 136 | 807 | 17,189 | 2.6 % |
| PI-RC | 8,337 | 126 | 787 | 16,711 | 2.5 % |
| EFM-CP | 10,376 | 1,300 | 44 | 16,016 | 2.4 % |
| PI-HH | 7,382 | 134 | 783 | 15,748 | 2.4 % |
| EFM-SD | 9,402 | 1,439 | 44 | 15,598 | 2.3 % |
| EFM-XT | 9,943 | 1,220 | 44 | 15,263 | 2.3 % |
| EFM-HH | 8,617 | 1,149 | 68 | 13,893 | 2.1 % |
| EFM-BD | 8,775 | 1,025 | 44 | 13,315 | 2.0 % |
| PI-MA | 7,366 | 529 | 0 | 9,482 | 1.4 % |
| TRX-CB | 5,404 | 791 | 21 | 8,778 | 1.3 % |
| TRX-SD | 3,558 | 265 | 70 | 5,318 | 0.8 % |
| TRX-CL | 2,707 | 489 | 23 | 4,893 | 0.7 % |
| TRX-RS | 3,729 | 159 | 47 | 4,835 | 0.7 % |
| TRX-B2 | 3,194 | 133 | 20 | 3,926 | 0.6 % |
| TRX-BD | 902 | 108 | 36 | 1,694 | 0.3 % |
| GND-SN | 875 | 145 | 20 | 1,655 | 0.2 % |
| STRETCH | 1,650 | 0 | 0 | 1,650 | 0.2 % |
| GND-NS | 753 | 188 | 0 | 1,505 | 0.2 % |
| TRX-XT | 879 | 67 | 16 | 1,307 | 0.2 % |
| TRX-XC | 886 | 66 | 12 | 1,270 | 0.2 % |
| GND-IM | 491 | 86 | 0 | 835 | 0.1 % |

(Negative counts are under the empty run's and shown as 0; the sample machines' L2 count is
under it too, STRETCH's whole row. The empty run: 15,152 instructions, 943 L2, 420 DDR. Run:
`python3 scripts/sharc_waverider_m5.py --image ../Digitone_II_OS1.11.syx --steps cost --tag before`,
6,693 s; report `out/waverider/m5_report_before.json`.)

## The sample reader's coefficients out of DDR (2026-11-12)

The DT2 reader (ONESHOT, REPITCH, GRID, SLICE, WERP) reads a row of six interpolator coefficients for
every 96 kHz sample and the decimator's four for every output sample, all from DDR until now: most of
the 1,253 DDR accesses a block above were those, not the sample's taps. The interpolator's 256 x 6
(6,144 B) now load into L2 at `dsp.SMP_TABLES_L2` (0x200a0000, the room the Machinedrum slots left on
2026-11-10, inside the range proven on units); the decimator's four and the LEV make-up gain (20 B)
into L1 at `dsp.SMP_DTAB_DM` (0x2e0080, the free words after the voices' decimators). The same words,
the same instructions: the sample machines' WAVs from the runner's `smp` step are byte-identical
before and after, and every block of every run is bit-exact to the model. One voice, a block, on the
OS 1.12 bench (`DNFW_COST_ONLY=smp ... --steps cost`, the runner's own estimate):

| machine | instructions | L2 | DDR before -> after | estimate before -> after |
|---|---|---|---|---|
| ONESHOT | 6,620 | 0 -> 669 | 1,253 -> 131 | 19,138 -> 10,606 (-45 %) |
| WERP | 6,951 | 0 -> 669 | 1,253 -> 131 | 19,469 -> 10,937 |
| REPITCH | 6,829 | 0 -> 669 | 1,253 -> 131 | 19,347 -> 10,815 |
| GRID | 6,546 | 0 -> 669 | 1,253 -> 131 | 19,064 -> 10,532 |
| SLICE | 6,580 | 0 -> 669 | 1,254 -> 132 | 19,108 -> 10,576 |
| STRETCH | 3,464 | 0 | 0 | 2,522 (unchanged: it reads with two taps, no coefficients) |

(Negative counts under the empty run's shown as 0. The DDR left, about 130 a block, is the samples'
own taps: the test sounds are int16, four words a 96 kHz sample.)

**Then the taps through an L1 line** (`sampler.program.line`, `dsp.SMP_LINE_DM`): when all six taps lie
inside the window, the render reads them from 24 words copied from the pool, refilled from the taps'
first word only when they are not all in it, and forgotten at each render (nothing writes the pool
while a voice renders). At more than `LINE_MAX` (2) frames a 96 kHz sample the line would refill nearly
every sample, so such a render reads the pool as before. The same words: the WAVs are byte-identical
again, every block bit-exact to the model, and the model with the line against without it gives the
same output word for word (60 random cases: the five machines, both formats, play modes, loops,
pitches, retriggers). Same run as above:

| machine | instructions | DDR (the voice's, total) | estimate after the coefficients -> with the line |
|---|---|---|---|
| ONESHOT | 6,620 -> 7,400 | 552 -> 146 | 10,606 -> 7,326 |
| WERP | 6,951 -> 7,731 | 552 -> 146 | 10,937 -> 7,657 |
| REPITCH | 6,829 -> 7,609 | 552 -> 146 | 10,815 -> 7,535 |
| GRID | 6,546 -> 7,326 | 552 -> 146 | 10,532 -> 7,252 |
| SLICE | 6,580 -> 7,361 | 553 -> 147 | 10,576 -> 7,297 |

(The empty run reads 421 DDR words a block; the voice's own are the run's less nothing, so a sounding
voice now reads fewer than the empty run counts and the table's DDR column would be negative.) By pitch,
in the model (ONESHOT, a block, DDR counted as 10): int16 saves 1,621 up to an octave above the
sample's rate, 1,039 at +2.5 octaves; float32 2,610 .. 1,446; past `LINE_MAX` the switch costs 135.

**A note's block** (model, ONESHOT): a fresh note costs about a steady block (+3 %); a note on a
voice still sounding costs 2.05 x, because the old note is rendered once more, fading out under the
new one (the DT2's second voice for a retrigger). Both renders are in the output, so this stays: with
the two changes above that block is about 15k on the estimate, and sixteen at once about 240k of the
roughly 310k our voices get.

**The program's own block** (the recorder and the fast link, before the slot loop, every block
whether a sample voice plays or not): the recorder's 32 frames (the input meter's peak, the staged
block) and the link's 64-unit packet (playheads, the guard's telemetry, its check, out to the TDM
page) kept their counters and indices in memory and recomputed each address. They now run on
register counts and running pointers: the same words written (the model, old against new, on 200
random states including recording, armed, new commands and a busy SEND: no word differs) and the same
cost every block, only less of it. The runner's empty run, our code with no voice sounding:
14,605 -> 11,201 instructions a block, L1 accesses 2,573 -> 1,458 (model: recorder 1,566 -> 934,
the idle packet 3,641 -> about 1,000).

## v0.43: the Monomachine render scratch in L1 (2026-11-07)

The Monomachine machines' render scratch (the decimator's input, SID's phases, the coefficients,
the words, DPRO's buffers: 3,280 bytes) moved from L2 to L1 block 1's tail (`dsp.MNM_RENDER_DM`,
0x2e5400); the bookkeeping (keys, costs, the voice order, rests, strikes) stays in L2. The same
instructions, every output word the same (the SHARC runner's mnm part: every block of every run
bit-exact to the model). One voice, a block, `DNFW_COST_ONLY=mnm ... --steps cost`:

| machine | instructions | L2 accesses v0.42 -> v0.43 | estimate v0.42 -> v0.43 | of the frame |
|---|---|---|---|---|
| SID 6581 | 22,108 | 3,219 -> 82 | 34,954 -> 22,406 (-36 %) | 8.4 % -> 5.4 % |
| VO-6 | 25,365 | 3,560 -> 280 | 41,315 -> 28,195 (-32 %) | 9.9 % -> 6.8 % |
| DPRO-DENS | 11,087 | 2,299 -> 633 | 21,903 -> 15,239 (-30 %) | 5.3 % -> 3.7 % |
| DPRO-WAVE | 10,946 | 1,772 -> 269 | 19,904 -> 13,892 (-30 %) | 4.8 % -> 3.3 % |
| DPRO-DDRW | 18,697 | 3,202 -> 1,139 | 33,675 -> 25,423 (-25 %) | 8.1 % -> 6.1 % |

(The estimate counts an L2 access as 4 instructions and a DDR one as 10, as above; the frame is
416,000 cycles.) DDRW's and DENS's remaining L2 reads are the DPRO tables (v0.36); WAVE's DDR
reads its samples.

## The Monomachine machines since v0.33

| machine | v0.33 estimate | now | DDR accesses v0.33 -> now | what changed |
|---|---|---|---|---|
| DPRO-DDRW | 108,076 (16.2 %) | 55,402 (8.3 %) | 2,380 -> 217 | v0.36 its 976 table words in L2; v0.37 level B skipped where its weight is 0 |
| DPRO-DENS | 33,569 (5.0 %) | 30,603 (4.6 %) | 657 -> 162 | v0.36 the same tables in L2 |
| DPRO-WAVE | 25,961 (3.9 %) | 25,961 (3.9 %) | 187 -> 187 | nothing |
| SID 6581 | 57,661 (8.6 %) | 57,691 (8.7 %) | 0 -> 0 | nothing (rounding of the empty run) |
| VO-6 | 47,928 (7.2 %) | 47,928 (7.2 %) | 171 -> 171 | nothing |

## What it says (2026-11-03, the v0.40 L2 item)

- **The DPRO machines' DDR reads are no longer their cost.** What is left in DDR is the
  wave samples themselves: DDRW 217 accesses a block (2,170 of its 55,402, 3.9 %), DENS 162
  (5.3 %), DPRO WAVE 187 (7.2 %). Moved to L2 (4 instead of 10 each) they would save at most
  1,302 / 972 / 1,122 cycles a voice-block, 0.2 % of the frame each: no voice more on any of them.
  Their cost now is instructions and L2 (DDRW: 25,876 + 4 x 6,839, its render scratch in L2).
- **The tables do not fit the room anyway.** The v0.33 note below said the Monomachine tables are
  31,871 *bytes*; they are 31,871 *words* (`rom.table_words()`: WAVE's samples 16,896, SID's
  combined waves 4,096, DPRO's 976, VO-6's 9,903), 124.5 KB. What DDRW and DENS read is the
  Digibank stand-in the DSP builds at power-on, 32 x 2,048 words, 256 KB; DPRO WAVE reads its
  16,896 samples (66 KB). The proven L2 room left is 0x200A9200..0x200B0000, 28,160 bytes
  (0x200A8000..0x200A9000 holds the v0.36 DPRO tables, 0x200A9000..0x200A9200 the v0.37 MAIN
  tap). The Digibank's top mip levels (L >= 4, 124 words a wave, 16 KB) would fit, but a
  note uses them only above about 690 Hz (the cost run's C4 reads level 2); levels >= 3 need
  32,256 bytes. So no change was made for v0.40.
- **Where the next saving is**: the L2 accesses (DDRW 6,839, SID 7,046, DENS 3,681 a block:
  the render scratch and the voice slots, L2 since v0.32) and the instructions. L1 room, not L2,
  would cut those.
- **P-I's delay lines** (PI-SD, PI-RS: about 1,800 DDR accesses a block) are 128 KB: they
  do not fit L2. Shorter lines for the machines that need little would.
- **The sample machines** read their samples from DDR (1,250 accesses: the reader's taps);
  that is where samples live, and it is the DT2's own cost.

## v0.33's table (2026-10-30)

| machine | instructions | L2 accesses | DDR accesses | estimate | of the frame |
|---|---|---|---|---|---|
| DPRO-DDRW | 44,128 | 10,037 | 2,380 | 108,076 | 16.2 % |
| SID 6581 | 29,507 | 7,046 | 0 | 57,661 | 8.6 % |
| VO-6 | 30,838 | 3,845 | 171 | 47,928 | 7.2 % |
| DPRO-DENS | 14,259 | 3,185 | 657 | 33,569 | 5.0 % |
| PI-SD | 15,033 | 109 | 1,803 | 33,499 | 5.0 % |
| PI-RS | 14,766 | 108 | 1,779 | 32,988 | 4.9 % |
| TRX-CY | 20,645 | 2,434 | 144 | 31,821 | 4.8 % |
| EFM-CY | 20,224 | 2,245 | 188 | 31,084 | 4.7 % |
| DPRO-WAVE | 13,179 | 2,728 | 187 | 25,961 | 3.9 % |
| TRX-MA | 15,091 | 2,347 | 0 | 24,449 | 3.7 % |
| PI-MT | 13,924 | 497 | 783 | 23,742 | 3.6 % |
| TRX-CP | 15,175 | 1,985 | 0 | 23,085 | 3.5 % |
| TRX-S2 | 15,426 | 1,629 | 37 | 22,312 | 3.3 % |
| PI-BD | 11,755 | 478 | 729 | 20,957 | 3.1 % |
| EFM-CB | 13,004 | 1,757 | 92 | 20,952 | 3.1 % |
| PI-ML | 14,060 | 1,073 | 68 | 19,032 | 2.9 % |
| EFM-RS | 11,372 | 1,660 | 92 | 18,932 | 2.8 % |
| TRX-OH | 11,691 | 1,268 | 141 | 18,173 | 2.7 % |
| TRX-CH | 11,685 | 1,268 | 141 | 18,167 | 2.7 % |
| WERP | 5,841 | 0 | 1,317 | 17,647 | 2.6 % |
| REPITCH | 5,732 | 0 | 1,317 | 17,538 | 2.6 % |
| ONESHOT | 5,522 | 0 | 1,317 | 17,328 | 2.6 % |
| SLICE | 5,469 | 0 | 1,318 | 17,285 | 2.6 % |
| GRID | 5,434 | 0 | 1,317 | 17,240 | 2.6 % |
| PI-CC | 8,575 | 136 | 807 | 17,189 | 2.6 % |
| PI-RC | 8,337 | 126 | 787 | 16,711 | 2.5 % |
| EFM-CP | 10,376 | 1,300 | 44 | 16,016 | 2.4 % |
| PI-HH | 7,382 | 134 | 783 | 15,748 | 2.4 % |
| EFM-SD | 9,402 | 1,439 | 44 | 15,598 | 2.3 % |
| EFM-XT | 9,943 | 1,220 | 44 | 15,263 | 2.3 % |
| EFM-HH | 8,617 | 1,149 | 68 | 13,893 | 2.1 % |
| EFM-BD | 8,775 | 1,025 | 44 | 13,315 | 2.0 % |
| PI-MA | 7,366 | 529 | 0 | 9,442 | 1.4 % |
| TRX-CB | 5,404 | 790 | 21 | 8,774 | 1.3 % |
| TRX-SD | 3,558 | 264 | 70 | 5,314 | 0.8 % |
| TRX-CL | 2,706 | 489 | 23 | 4,892 | 0.7 % |
| TRX-RS | 3,728 | 159 | 47 | 4,834 | 0.7 % |
| TRX-B2 | 3,194 | 133 | 20 | 3,926 | 0.6 % |
| TRX-BD | 902 | 108 | 36 | 1,694 | 0.3 % |
| GND-SN | 875 | 145 | 20 | 1,655 | 0.2 % |
| GND-NS | 753 | 188 | 0 | 1,465 | 0.2 % |
| TRX-XT | 879 | 67 | 16 | 1,307 | 0.2 % |
| TRX-XC | 885 | 66 | 12 | 1,269 | 0.2 % |
| GND-IM | 491 | 86 | 0 | 795 | 0.1 % |
| STRETCH | 2,171 | 0 | 0 | 517 | 0.1 % |

(Negative counts are under the empty run's and shown as 0. STRETCH's single voice here
plays little of its sample at this tempo, so it reads almost nothing.)

## What it said (v0.33)

- **DPRO DDRW is the heaviest machine** by far: about 2,400 DDR accesses a block, its
  wavetables (the Monomachine's tables live in DDR, decoded there by the DSP at power-on).
  DENS and DPRO WAVE read the same tables. **Next**: those tables (31,871 bytes -- words, in fact: see above) fit the 32 KB
  of proven L2 left above the Monomachine scratch (0x200A8000..0x200B0000). Moving them means
  copying them there once decoded, and the Monomachine voices reading from there: a change to
  the voices' generated code and the decoder, with its own checks, kept out of v0.33 so this
  release stays the stability one.
- **P-I's delay lines** (PI-SD, PI-RS: about 1,800 DDR accesses a block) are 128 KB: they
  do not fit L2. Shorter lines for the machines that need little would.
- **SID** is L2-heavy (7,000 accesses): its state, now in L2 (v0.32). It was DDR before.
- **The sample machines** read their samples from DDR (1,300 accesses: the reader's taps);
  that is where samples live, and it is the DT2's own cost.
- The rest of the Machinedrum machines are light: TRX-BD, GND and the TRX-XT/XC family cost
  under 0.3 % of the frame each.

## The worst cases (step 3s, v0.33)

With the clock made to move (three cycles an instruction): sixteen P-I voices with every
control moving each block, sixteen VO-6 and DENS voices likewise, and one track retriggered
every block beside fifteen sounding voices. In every block our voices were done by 0.56,
0.42 and 0.58 of the frame, the guard leaving 189, 73 and 131 voice-blocks out, every buffer
finite. Before any of it the voices' state was also filled with NaN and with random words
(step 3g): every machine came through, finite.
