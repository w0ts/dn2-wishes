# Room in the DSP upload (2026-11-10, branch sophie-v047-os112-shrink)

The ports (ANALOG 2 and its five A2 filters, DRONE, the SUB / DIST / GATER / RING inserts) do not fit the
DSP program beside v0.47 + inserts2 + recorder + PLAITS poly16 + popups. This is where the bytes go, what
came out without changing a single output word, and what a second load would take.

## The limit is the ColdFire's, not the SHARC's

- MAIN OS's uploader (`0x400cf34c`) mallocs 1 MiB for section 7 as stored, depacks it into a second 1 MiB
  buffer after a one-byte `0x03` header, and checks the length only after the depack has written
  (`dnfw.safety`, rule 4): **1,048,575 bytes unpacked** is the hard ceiling, and going over it overruns the
  ColdFire's heap at boot. **[D]** (read from the code, documented in `safety.py`).
- The SHARC has room: our L2 spans end at the ceiling 0x200EA000 with the non-cacheable window from
  0x200FA000; DDR from 0x80600000 to 0x88000000 (126 MB) holds only rings, the pool and tables. Memory is
  not what runs out; the boot stream that fills it is.
- So the remedies are: fewer bytes in the stream (below), or bytes that reach the DSP another way after
  boot (section *Second load*).

## The byte map

Section 7 = stock's 95 blocks (836,956 B) + ours. Ours, per block group (`dn2mk2-scratch/shrink/bytemap.py`):

| what | v0.47 test base | poly16 base (6e726aac) | this branch |
|---|---:|---:|---:|
| perc.asm (PERC, Machinedrum, Monomachine, PLAITS, TB303, SOPHIE) | 149,584 | 145,624 | **135,804** |
| smp.asm (the sample machines, the recorder's preview) | 22,276 | 21,986 | 21,920 |
| fdn8.asm | 7,382 | 7,384 | 7,304 |
| the DT2 sample reader's coefficients | 6,180 | 6,180 | 6,180 |
| xdly.asm / inserts.asm / inspost.asm / insbus.asm | 4,180 / 4,156 / 3,146 / 2,742 | about the same | 4,150 / 4,094 / 3,056 / 2,602 |
| PERC tables (exp2, tan) / AMD's sine | 4,124 / 1,304 | 4,124 / 1,304 | 2,068 / 0 (shipped) |
| FDN8 state, stubs, lookup, zero fills (16 B each) | ~2,200 | ~2,200 | ~2,200 |
| **section 7 unpacked** | 1,043,962 | 1,039,872 | **1,026,066** |
| **free** | 4,613 | 8,703 | **22,509** |

Inside PERC (`dn2mk2-scratch/shrink/percmap.py`: every emitted line tagged with the Python that wrote
it, sized by selas's own layout), poly16 base -> this branch:

| machine code | bytes before | after |
|---|---:|---:|
| PLAITS (13 engines) | 26,276 | 24,608 |
| P-I RC (Machinedrum ROM machines' shared core) | 22,440 | 21,112 |
| TRX (trx2 / trx1) | 19,788 / 12,180 | 18,666 / 11,668 |
| EFM | 17,588 | 16,034 |
| P-I ML / BD / SD / RS / MA / MT | 9,560 / 5,218 / 5,186 / 4,818 / 1,004 / 572 | 9,066 / 5,070 / 4,836 / 4,436 / 958 / 468 |
| the voice frame (guard, parameters, machine dispatch) | 7,654 | 8,196 (the dispatch tables now count here) |
| TB303 / SOPHIE | 4,584 / 3,668 | 4,222 / 3,252 |

By instruction kind (before): constant loads 7,839 (31 KB: floats and addresses take 48 bits), slot-word
moves through I3 4,694 (3,988 of them 48-bit: offsets past the 6-bit window), absolute scratch moves 1,640
(9.8 KB), the per-step compare chains of the machine dispatch (5 KB). The code compresses to ~40 % with a
plain LZ77 (139 KB -> ~55 KB): it is very repetitive, which is what the second load below would exploit.

## What came out, bit-exact

Every change is in the generators (`dnfw.perc.dsl`, `dnfw.perc.program`, `dnfw.md.voice`,
`dnfw.perc.machines`, a few PLAITS pointer sites); the asm and JSON are regenerated. Bytes are section 7
unpacked; time is the model's steps (instructions) for the worst block of each case.

| change | bytes | DSP time |
|---|---:|---|
| **I3 biased by 96 words** (`program.I3_BIAS`, `Prog.seti(bias=)`, `Prog.bk`): the slot's state words S0..S0+63 now sit in the 6-bit offset window, so their moves are 32-bit, and more of them fold into the compute before them | -6,220 | 2 instructions a voice-block to bias I3, minus the folded moves: less |
| **`Rs = 0` read only by `FLOAT Rx BY Rs`** -> `FLOAT Rx`, the load dropped (`dsl._zero_scale`, emit mode's last pass: straight-line code only, refused at any label, branch or other read) | -1,976 (PERC) | fewer |
| **loop tails count down with DEC** (`Rc = Rc - 1`, stock's 16-bit form) instead of a 1 in R12 and a subtract; the same pass turns `R12 = 1` read only by a lone add / subtract into INC / DEC | -1,108 (PERC) | fewer |
| **the machine dispatch through a table of 48-bit JUMPs** (`md.voice._each`): the index, `JUMP (M14, I12)`, a never-run NOP (hwrules BRANCH-WIN), one JUMP a machine; was a chain of up to 37 compares for each of host / init / trig / render | -688 | up to 36 compares fewer a step |
| the same DSL changes in smp, fdn8, xdly, inserts, inspost, insbus, pvmix | -624 | fewer |
| **PERC's tan and AMD's sine ship over the link at power-on** with the Machinedrum's tables (`perc.machines.shipped_tail`, appended by `md.core.tables_bytes`); PERC's voices never run before those are whole (`C['fill'] < Z_N` keeps every slot silent), exp2 stays (the sample machines read it). USB image +606 B (MAIN OS carries them) | -3,352 | none |
| **total** | **-13,806** | every machine fewer steps a block (below) |

Worst block, model steps, poly16 base -> this branch: TRX 5,688..30,305 -> 5,322..29,823; EFM 16,586..31,717
-> 16,014..30,608; GND ~6,000 -> ~5,600; P-I 14,058..24,487 -> 13,634..23,576; SOPHIE 20,493 -> 19,445;
PLAITS 24,231 -> 23,850; TB303 54,228 -> 49,699. Per case: -111 to -4,529 steps; none more.

### Proof

- **Model golden, base vs this branch** (`dn2mk2-scratch/shrink/golden_all.py`): the PERC program in run mode
  for every Machinedrum type (37 x 5 knob sets), every Monomachine machine (SOPHIE, TB303, PLAITS with
  MODL across all engines, 5 knob sets), 24 blocks with trigs, a type switch and back; the output words
  hashed and the slot's 256 words at the end: **255 / 255 outputs identical, 0 slot-word differences.**
- **Loop tails**: run mode now puts a NaN (`dsl.POISON`) in the register the tail used to leave 1 in; the
  golden is still 255 / 255 identical and the runner compares every model (smp, fdn8, xdly, inserts too)
  with the DSP, so code that read the old 1 would fail there.
- **SHARC runner** on the build (`sharc_waverider_m5.py`: decode map voice guard stress chords garbage
  wipe smp link rec mainrec recwhole pvmix fdn8 xdly inserts inspost insbus tdm stock mnm frame rotate
  poly16): **246 PASS**; its 3 FAILs (PLAITS PART and STRG 16 voices by 0.8 of the frame on the memory
  clock; ONESHOT against the DT2 reader) are the poly16 base's own, the same three in its runs.
- **Encoding census** (`dn2mk2-scratch/shrink/shapes.py`, the skill's `encodecheck` against stock's real
  code): `FLOAT Rx` and `R = R - 1` are stock shapes. The bias makes three compute + move shapes with a
  negative offset that stock never pairs with that compute (`PASS` / `AND` with `DM(-N, I3)`, 16
  instructions); stock folds other computes with negative offsets. The fixed-bit mismatch class
  `R = PASS R, move` was already in the poly16 base (15 there, 11 here).
- `gate_hwrules`: PASS after the NOP (the table's first JUMP was in the indirect JUMP's 48-bit window).
- Unit tests: 74 failed / 527 passed / 183 skipped / 4 errors on base and on this branch, the same tests
  (the environment's: no MD golden outside the bench). Boot from reset 800M: no fault. `dnfw preflight`:
  PASS.

## Not done, and why

- **Immediate ASHIFT** for the 344 `ASHIFT Rx BY R12` with a constant count: selas mis-encodes the
  immediate form, and the LSHIFT one passed both decoders and then faulted on silicon (ILOPI,
  `sharc_waverider_m3.fix_shift_imm`). Not without a unit test.
- **A constant pool** (the top 64 values cover 2,756 of the 3,863 48-bit constant loads, ~5 KB): needs an
  index register for the whole program; I0 is PLAITS poly16's (53 uses in its tightest loops), and a PM
  index (I13) would use `R = PM(k, I)`, which stock has twice. Ask first.
- **The host words W[1..15] in the window too** (~800 moves, ~1.6 KB): a slot layout change that PLAITS'
  pointer arithmetic (W[9..63] as its state) depends on.
- **The DT2 reader's coefficients (6 KB) over the link**: the sample machines and the recorder's preview
  would have to wait for the link at power-on (a behaviour change in the first second).

## Stock's own section 7 (the User: "data that could be compressed, also in original code")

- **Zeros**: stock already stores every zero run as a fill block (37 of its 95 blocks): 0 B to gain.
- **Runs of one non-zero word** (64 B or more): 2,968 B. The loader's fill blocks carry an argument; every
  stock fill has argument 0, and a non-zero fill value is untested on this boot ROM. Not done.
- **Two identical blocks of 67,652 B**: L2 0x2001e888 (A) and 0x200779f8 (B) are byte for byte the same.
  They are int16 data (0, 199, 398, ... up to +-32,440: wavetables). Measured in the runner (a probe on
  the sharc_core's DM reads and writes, stock image, the stock-engine frames: WaveTone, FM Tone, FM Drum,
  Swarmer, every track triggered; `dn2mk2-scratch/shrink/twinprobe.py`): with the default sounds only B is
  read (WaveTone's oscillator, sw 0x1c3aa2..0x1c40bd, through runtime base pointers in I2 / I3); with
  every parameter of those four tracks random each block, **both are read** (A first at sw 0x1c444b);
  **neither is ever written**. No pointer table names either (the base is computed). The DDR blocks
  (283 KB, 55 KB, 9 KB) are likewise read only, from the first block on.
  So the two cannot be merged into one address, but the stream can carry A only and our first-frame
  hook (the entry mark at sw 0x1c9fb9, which runs before the per-block routine) copy A over B: ~17,000
  word moves once at power-on, memory identical from the first frame. **67,636 B** of upload. What is
  not known: whether stock's init (before the first frame, which the runner does not run) reads A or B.
  It needs an emulated init run with the same probe, or a unit test. The biggest lead; ask first.
- **Compressibility** of stock's big blocks (zlib): DDR 283 KB at 0x80467cf4 0.88, L2 code 125 KB 0.43,
  L1 104 KB 0.52, the twins 0.96 each, DDR 55 KB 0.75. Unpacking stock's code on the DSP is the same
  cache question as below, before stock's own code runs: not attempted.
- **The boot animation** is ColdFire code in MAIN OS, not in the DSP's upload: removing it frees USB
  image bytes, not this limit. This build already leaves the intro out (`nointro`) and carries no
  boot-screen stamp or ANIZ / ANZL chunks (`plaits303/build.py`).
- From the ports (their session's measure): ANALOG2 and the A2 filter pass each carry the five filter
  models (~3.4 KB each); one shared copy saves ~3.4 KB.

## The twin table, copied on the DSP (TEST build, 2026-11-10)

The User chose "emulator first, then test". **Emulated**: stock's engine init (sw 0x1c1445, 5.02M
instructions to its return, as the runner's post-init snapshot is made) with the DM probe on both
twins: **no read or write of A or B** (`dn2mk2-scratch/shrink/initprobe.py`; its additive loops run
natively after two emulated entries each, which touched neither; nothing before engine init on the
real start-up, FreeRTOS and the drivers, is emulated). Then the frames: B read, A read with random
parameters, neither written (above).

**The change**: `dsp.drop_twin` turns stock's B block into a fill block (zeros at load) after checking
A and B are the same bytes; `entry_mark.asm` (the hook where the handler calls the per-block routine,
before any machine renders) copies A over B the first time through, 16,913 words, and sets TWIN
(0x2de140, in the zero-filled state block) to `TWN1` so it never copies again; it saves and restores
R9, R10, I0, I1. Every later frame costs it 6 instructions. The runner models the copy when it loads
an image (`_twin_copy`) and step `twin` runs the real hook: B ends as stock's B word for word, TWIN
set, the registers kept, a second pass copies nothing.

**Upload**: 958,518 B unpacked, **90,057 B free**. The USB image hardly changes (the container's packer
already stored the second copy for almost nothing).

**What only the unit can show**: that nothing in the real start-up reads B before the first frame
(the emulator runs engine init only) and that WaveTone sounds as before. The listening test for the
User compares this build with the plain shrink build.

## Second load

What is proven: the ColdFire already sends the DSP data after boot over the fast link (`link.c` K_TABLES,
v0.26: a CODE chunk at 0x47000000, up to 512 KB, into the pool's table area, READY's magic when whole), and
PERC already waits for it. So more data can go that way today (the tables above did).

Code that way, or code compressed inside the stream and unpacked on the DSP, frees far more (PERC alone is
136 KB; ~55 KB compressed), but needs what nothing here has done yet:

1. **Code written by the core and then executed.** The L2 we run from is cacheable for data (the startup's
   non-cacheable window starts at 0x200FA000): the copied words can sit in the data cache while the
   instruction fetch reads L2. It needs a write-back of the data cache (or writes to the non-cacheable
   window and code placed there: 24 KB only) before the first jump, and nothing in this firmware does that
   today. The emulators do not model the caches, so only the unit can prove it.
2. **A start gate**: no jump into the copied code until it is whole (as `fill` gates PERC on the tables).
3. **The USB image**: code shipped from MAIN OS is compressed there as in section 7: about neutral on the
   2 MiB USB budget (25,339 B free now). Compressed in the stream and unpacked by the DSP: no USB cost.
4. **Boot time**: unpacking ~136 KB on the DSP takes a few blocks after power-on (zpack's 29 blocks, 19 ms,
   are the model); PERC is silent until then, as it is now until the tables arrive.

Feasible, with a unit test the User runs first (a probe build that copies a small routine into L2, flushes,
runs it and reports through the reply ring). Not built.

## DRUM's room (2026-11-20, branch claude/drum)

With DRUM's hats the upload had **267 B** left (1,048,308 B unpacked); TOM did not fit. The User: find room first,
bit-exact, no second load.

**Where section 7's bytes are** (`scratch`'s s7map: `dsp.section7` on 1.12's stream, every span through `dsp._blocks`):
stock's blocks 769,304 B (836,956 with the twin B as a fill block); ours 273,378 B: perc.asm 172,224, smp.asm + pvmix
23,192, perc2a 17,900, inserts 8,436, fdn8 8,398, inspost 7,054, the DT2 reader's coefficients 6,160, perc2b 5,996, a2f
5,740, xdly 4,766, insbus 4,340, jsend 2,800, PERC's L1 exp2 2,084, then state and tables under 700 B each; every zero
span is a 16 B fill block. Inside perc (selas's offsets): PLAITS 30,682, the voice frame 17,670, subroutines 13,102,
ANALOG2 11,188, VO-6 8,746, PI-ML 7,376, DRUM 6,958, TB303 4,738, the P-I machines ~4,000 each.

**Done, bit-exact** (each measured with selas on the farm; section 7 **1,048,308 -> 1,042,682 B, 5,893 B left**):

| change | bytes |
|---|---:|
| **R12 loads nothing reads, folded** (`dnfw.perc.flow`): `R12 = ret; I12 = R12` at a leaf call -> `I12 = ret` (550 in PERC), `R12 = K; In = R12` -> `In = K` (82; the stock's own `I5 = 0x25d748` shape), `R12 = 0x0` read only by `FLOAT Rx BY R12` / `R12 - Rx` / `R12 + Rx` -> `FLOAT Rx` / `-Rx` / `PASS Rx` (153); and 118 in smp, fdn8, xdly, inserts, inspost, jsend, a2f. Only where R12 is dead by the text's control flow (every path writes it before any read; a return, an indirect or absolute jump, CALL, a SIMD region count as reads), each fold re-checked in the folded text | -3,654 (PERC -3,170, the others -484) |
| **PERC's DDR exp2 no longer loaded** (`ddr_spans`): the program and the sample machines read its L1 copy since 2026-11-12; no code names 0x81216000..0x81216804, and the model holds no words there either (a read would differ in the runner) | -2,068 |
| (the hats' same-block choke, the clock: docs/drum.md) | +68 |
| (stage 3, 2026-11-20: TOM, the re-voicing; docs/drum.md "Stage 3": section 7 1,046,118 B, **2,457 B left**; perc 175,618, perc2b 5,972) | +3,436 |

**Proof.** Run mode is unchanged (it never loaded R12 for a call); the model holds the DSP to it. For the text: the
resolved objects are the folded text modulo addresses; the folded and unfolded texts differ only at the 903 fold sites
of the three shapes; the unfolded text of the seven other objects is the base commit's asm (nothing else changed) and
PERC's differs from it only by the choke's code; a second liveness check written apart (scratch r12flow.py) finds R12
dead after each folded instruction in the resolved files; test/test_perc_flow.py; and the SHARC runner on the build
(dsp-identity, hwrules, and the steps below).

**Measured, not done** (bigger, or not bit-exact, or not worth it yet: the User decides):

| candidate | bytes | bit-exact | why not now |
|---|---:|---|---|
| a constant pool for the 48-bit loads (`R12 = K; Fn = Fn * F12` alone 1,174 times) | ~5,800 (2026-11-12 study) | yes | reserves an index register for the whole program (I0 is PLAITS'); ask first |
| repeated runs as subroutines, event-only code (EFM host x13, P-I / FM+ init repeats) | ~1,400 | yes | per-machine DSL work; no steady-time cost |
| repeated runs as subroutines, render code (PLAITS' 89-instruction filter x5 1,920, PI-ML x8 1,188, ...: 23 KB upper bound over all repeats >= 10 instructions) | up to ~3,000 for the top two | yes | a call a block or a sample: DSP time |
| one exp2 subroutine for dr_exp2 / pldk_exp2 / plnoise_exp2 / plphy_exp2 (the same 34 instructions, input F13 or F15) | ~370 | yes | a move at ~50 call sites |
| ANALOG 2's mix tables loaded twice (L2 scratch and the a2f L1 state, the same 106 words) | ~400 | yes | a2f's reads to L2 (time) or a first-frame copy |
| `R12 = PASS Ra; Rd = R12 + Rb` -> `Rd = Rb + Ra` (108, where Rb is R8..R15: G5) | ~216 | yes | small; encoding rule G5 |
| the DT2 reader's coefficients (6,144) over the link | 6,144 | no (the first second) | not symmetric (0 of 256 rows mirror another): no half-table |
| stock's runs of one non-zero word as fills | 2,968 | yes | a non-zero fill argument is untested on the boot ROM |
| a second load / code compressed in the stream | 55 KB+ | yes | cache flush and a unit test first (above) |

## CLAP and the cymbals' room (2026-11-20, branch claude/drum)

On the release base claude/v0626 (DRUM stage 3, the mixer meters, UP / DOWN) the upload had **1,485 B** left (section 7
1,047,090 B; smp grew with the meters' levels pass). The User: free ~2,400 B bit-exact first, not the constant pool.

**Done, bit-exact** (commit 0f44c03b; measured with selas on the farm, `s7map`):

| change | bytes |
|---|---:|
| the machines' inits zero their long state runs by a loop (`md.core.zero_words`, 16 words and more: PI-RC / CC / HH's 96, PI-BD / MT / SD / RS / ML, TRX-S2, TB303, PLAITS, SOPHIE, FM+ STAT / PAR / DYN; TB303's first note): perc2b 5,972 -> 4,250 B | -1,902 |
| EFM's hostD lookup one subroutine in the host bodies' span (`efm_hostd`, 14 sites) | -416 |
| one exp2 copy (F15 in, F14 out) for PLAITS' drum kit, ANALOG 2's glide and DRONE (`pldk_exp2`; F15 = F14 after it at their 6 sites, as before) | -242 |
| `dnfw.perc.flow`: `R12 = PASS Ra; Rd = R12 + Rb` -> `Rd = Rb + Ra` (G5, Rb in R8..R15, R12 dead: 3 sites; the 108 in the table above have Rb in R0..R7, where an add cannot take it first) | -6 |
| **total** (section 7 1,047,090 -> 1,044,530 B: **4,045 B left**) | **-2,560** |

**Proof.** The model (run mode, the program the SHARC runner holds the DSP to bit for bit) before and after: every
Machinedrum type (34) and every Monomachine machine (PLAITS on its 13 engines, DRUM on its five types) at four knob sets,
20 blocks with hits and a type switch each way (both machines' inits): **260 of 260 cases identical in every output word
and the whole written memory** (only the init / host / trig paths take more or fewer steps). test/test_perc_flow.py (the
G5 shape). On the room build (aa9416a1): dsp-identity, hwrules, and the SHARC runner's mnm-ma+frame, mnm-mb, mnm-plaits,
mnm-drone, mnm-a2, decode+map+voice+guard: every one PASS (every model bit-exact to the DSP, types 0-4 bit-identical to
stock).

**Then, with CLAP and the cymbals** (commit 38d8b2ad; docs/drum.md "Stage 4"): the host lookups of 18 GND / P-I / TRX /
EFM hosts (`md_pitch0`, `md_pitch1`) and TRX-CH / OH's host words (`trx_hathost`) one copy each in perc2a (-658 B), the
Monomachine half loop two instructions shorter (15 machines), and in DRUM: the hats' and the cymbal's hit one copy, the
decay coefficients and the drive's law one subroutine each with exp_neg's and exp2's copies as tails (`Prog.tail`).
The model before and after: the same 260 cases, every output word identical (DRUM's five old types included). The build
(88d1955f): section 7 1,048,266 B, **309 B left**.

**Measured, not done:** ANALOG 2's mix tables loaded twice (~400 B: a2f's reads to L2 or a first-frame copy); the
render-code repeats (PLAITS' filter x5, PI-ML x8: DSP time); plnoise_exp2 / plphy_exp2 into the shared copy (their call
sites' registers); the constant pool.

## main-next-64's room (2026-11-21, branch claude/dsp-room64)

On main-next-64 (cb1b9fc0) section 7 was 1,047,962 B: **613 B left**, and DRUM (CLAP, RIDE, CRASH, the balances,
CURV, AMP ON/OFF), live-knobs and live-drum need about 2,000 B more. Bit-exact, each measured with selas on the farm
(`s7map`), each its own commit:

| change | bytes | DSP time |
|---|---:|---|
| ANALOG 2 and JUNO read the A2 mix tables from the A2 filter pass's own L1 copy (`analog2.tables_at` = the a2f program's `TABLES`, the same 106 floats); the copy in the Monomachine L2 scratch (`+0x3200..+0x33A8`) is no longer loaded: that span is one zero fill now | -436 | 9 base-pointer loads change address, no instruction added; the reads are L1 reads now (L2 data costs ~4 cycles a read) |
| JUNO's code once: the post pass and the chorus send both ran `post.juno` inline (311 instructions, 1.7 KB twice); now each enters the one copy in inspost.asm (`post.juno_call`, `wr_ip_juno`) and it returns through `C["jret"]` (JUNO calls `span`, which takes I12); jsend.asm 2,768 -> 1,044 B, inspost.asm 7,006 -> 7,034 B | -1,696 | +5 instructions a JUNO insert run (`I12 = ret`, the JUMP, the store, the load, the return), +6 on the send (its return-address load is not folded: an absolute jump counts as a read of R12): at most 16 x 5 + 6 = 86 a block |
| Machinedrum dispatch: two step functions that emit the same text share one body (`md.voice._same_code`, by text now, not only by function): PI-HH's init is PI-CC's (110 instructions), three other inits and two trigs likewise; perc2b 5,972 -> 5,494 B, perc 176,148 -> 176,076 B | -548 | none (the table's JUMP goes to the other copy) |
| **total** (section 7 1,047,962 -> 1,045,282 B: **3,293 B left**) | **-2,680** | |

**Proof.** The tables: the bytes at `tables_at()` in the L1 span are `table_words()` (test_waverider_dsp), and the only
text change in perc.asm is the 9 base addresses. JUNO: the copy's 311 instructions are, word for word, the inline run
of the old inspost.asm and of the old jsend.asm, and the rest of both objects is unchanged but for the call (and
jsend's own `span` copy gone, inspost's `recip` moved); run mode runs `juno()` at the call as before. The dispatch:
each merged pair was the same text in the old perc / perc2b. Then the SHARC runner (every model bit-exact to the DSP)
on each step's build: see the commits.

**Next** (measured, not done): the whole-PERC constant pool (4,628 48-bit constant loads, 958 values, the top 128
cover 3,315 of them: ~6 KB; `DM(k, I6)` is 4 B, `PM(k, I13)` 6 B, so it needs I6: the User approved it on
2026-11-21 once stock's interrupt handlers are shown not to read I6 before saving it); the four dispatch tables as
32-bit address words (~380 B); the register restores on the other exits of fdn8 / xdly (~700 B); perc2a's host
repeats (up to ~1.9 KB in many small calls).

## PERC's constant pool (2026-11-21, branch claude/const-pool; the User approved it)

**At the combined-67 merge (main's option A, 2026-11-21) the pool is 112 words, `0x2E1980..0x2E1B40`, I6 = `0x2E1A60`
(k in -56..55):** up-v067's AMP ON/OFF data took `0x2E1B40..0x2E1C00` first. The text below and its table are the
128-word branch's. Measured at the merge (farm, private selas with patch 0003, on claude/up-v067 79295df4):
3,462 loads moved to the pool (perc 3,178, perc2a 256, perc2b 28; scripts/perc_cpool_check.py against up-v067's text:
the same instructions but those and the 3 I6 instructions); perc 178,728 -> 172,390 B (-6,338), perc2a 18,654 -> 18,142,
perc2b 4,130 -> 4,074; section 7 unpacked 1,048,022 -> 1,041,598 (-6,424; 553 -> 6,977 B left).

A 48-bit immediate load `Rn = 0x...;` whose value is outside the signed 16 bits (those have a 32-bit load already)
becomes `Rn = DM(k, I6);` (32-bit, k in -64..63) when its value is one of the pool's 128 words: the 128 most frequent
such values over perc, perc2a and perc2b (`dnfw.perc.cpool`, a text pass after `dnfw.perc.flow`'s fold, before the jump
resolver). The pool is a 512 B L1 span at `0x2E1A00` (`dsp.PERC_POOL_DM`, the end of hole F2; its words are written by
`scripts/gen_perc_asm.py` to `csrc/waverider/sharc/perc_pool.json`). I6 = `0x2E1B00` while PERC's code runs: wr_perc
saves the caller's I6 with the other registers (`program.SAVE_REGS`, word 28 of the save area, `0x2DDE70`) and sets it;
PERC's one exit (the JUMP on to smp.asm) restores it first, so smp.asm, PING's tail (whose two stock instructions read
the stock frame through I6) and stock see their own I6. Left alone: return-address loads (the resolver fills them),
conditional loads, loads in a compute + move, I / M loads, and the SIMD region (there a DM load also writes S{n}).

| | before (claude/dsp-room64) | after |
|---|---:|---:|
| perc.asm (PERC's L2 span, 179,712 B) | 176,076 | **169,560** (-6,516) |
| perc2a.asm / perc2b.asm | 17,868 / 5,494 | 17,372 / 5,436 |
| the pool (L1, new) | | 512 (+16 B header) |
| **section 7 unpacked** | 1,045,282 (3,293 B left) | **1,038,738 (9,837 B left; -6,544)** |

3,544 loads moved to the pool (perc 3,267, perc2a 248, perc2b 29). DSP time: the same instruction count for every
load (one load for one load, from L1: free in the cost model and the runner) plus 3 instructions a block (I6's save,
set and restore). The model (run mode) never sees the text: unchanged.

**The I6 proof** (stock 1.12's section 7, read with the digikit sharcdb, every instruction checked against selas'
encodings): the interrupt vectors (IVT at sw `0x120000`) go to one dispatcher (`0x1c0a70`; SECI's at `0x1c0acd`), to
fatal stubs (EMUI, PARI, ILOPI) or to reset. Both dispatchers read I6 only to save it (`R12 = I6; DM(3, I7) = R12`) and
restore it on the way out (`I6 = DM(3, I7)`); they enter the handler with `RTS (DB)` without setting I6, so each handler
saves it itself. Every handler the installer (`0xb8b782`, all its call sites) puts in the tables does: `0xb8afe4` and
`0x1c02a4` open with `R0 = I6; I6 = I7; DM(I7, M7) = R0` on both their branches; `0xb8a947` only restores I6; the
default `0xb8b9f2` never reads it and halts. PARI and ILOPI do not touch I6; EMUI (a debugger's) reads `DM(I6)` for its
error record and halts. So no stock interrupt path reads I6 except to save it, and each restores it.

**Proof of the text**: `scripts/perc_cpool_check.py BASE NEW`: the pool build's perc / perc2a / perc2b are the
base's instruction for instruction (addresses aside) but for the 3 I6 instructions and the 3,544 loads, each of which
loads `pool[k + 64]` = its old immediate. `gate_hwrules`: PASS. The SHARC runner on the pool build: see the commit.
