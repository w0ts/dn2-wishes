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
