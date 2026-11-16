"""Waverider's DSP half: every edit Milestone 5 makes to section 7 (the SHARC boot
stream), applied from committed artefacts. `docs/waverider-m5-dsp.md` has the
evidence for each.

    section7(stock) -> the modified boot stream
    section7_idle_only(stock) -> stock plus the idle-time stub alone (patch 4), for
                       measuring the stock engine with nothing of Waverider in it
    placements()    -> what goes where, for a report or a mod's extents

**What it does to DN2 1.11's section 7:**

1. **Adds boot blocks** in L1 block 1's free tail, byte `0x2dd600..0x2e7000`
   (Milestone 5c; M5 used L1 block 2, which silenced the instrument --
   `docs/waverider-dsp-silence.md`): `reader_m5.asm` (sw `0x16eb00`),
   `machine5_live.asm` (sw `0x16ed00`), a zeroed state block (save area, counters,
   16 reader blocks), the 129-entry increment table, the wavetable directory, and
   two original 16 x 512 int16 tables. Every payload is zero-padded to the next
   span, so the region is written end to end: each code span has >= 64 bytes of
   zeros (NOPs) after it and no byte of the region is left unwritten.
2. **Enters the type-5 loop**: the two instructions at sw `0x1c9448` (after the
   Swarmer render loop in `sw 0x1c8ef1`) become `JUMP 0x16f600` and a 16-bit NOP.
   `block_count.asm` there counts the block into reply word 2 and jumps to the loop
   at `0x16ed00`, which re-executes the two instructions before it jumps back to
   `0x1c944c`. (Until the block counter, the JUMP went straight to `0x16ed00`.)
3. **Lets a type-5 frame through**: the frame-nibble -> machine-type lookup
   `0x25d748[5]` becomes 5 (stock 0, FM Tone).
4. **Times the idle task** (`idle_load.asm`, sw `0x16f500`): the back edge of
   FreeRTOS's idle loop, `jump (pc,-0x10)` at sw `0xb88abb` in L2, becomes
   `JUMP 0x16f500`; the stub adds the idle task's own cycles to a running total in
   reply word 1 and jumps back to `0xb88aab`. The SHARC's load is then
   1 - idle / elapsed (`docs/sharc-load.md`).

**What it does not do, on purpose:**

- It does **not** raise `min(R2, 4)` at `0x1c294c` (Milestones 3-4 did). Measured:
  that clamp's input is the frame's per-track field at offset `84 + 2t`, not the
  machine type, which reaches the record through the lookup alone.
- It does **not** touch the per-type setup table `0x8052db90`: the dispatch indexes
  it only after `compu(type, 5)`, so type 5 already takes the no-setup arm that
  MIDI's entry `[4]` also points to (`0x1c90d4`).

Every stock byte it replaces is checked first, and every added span is checked to
lie outside every block of the stock stream (loaded or filled). This module is pure:
bytes in, bytes out.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct

from ..image import bootstream, sharc_object
from . import live
from ..builder import selection as _sel     # dnfw.builder: FX_FDN8 / FX_XDLY off -> the stock hook, no code

STOCK_SHA256 = "336e340aa0cdcd34e314cfa44849f709a3134f6bd4cd57dfc7e15702c83115e2"
LOAD_ALIAS = 0x28000000          # boot-stream load address = LOAD_ALIAS + DM byte address
CODE = pathlib.Path(__file__).with_name("sharc_code.json")

# L1 block 1's free tail (DM byte addresses). Block 1 is 0x2c0000..0x2f0000; the
# stock stream's last byte in it is 0x2dd52c, and the startup enables the DM cache,
# which is carved from the top of block 1 (16 KB at size code 0, the size the
# startup writes; see docs/waverider-dsp-silence.md). REGION ends 36 KB below the
# block's top, so it stays clear of a 16 KB or a 32 KB DM cache.
REGION = (0x2DD600, 0x2EB000)                # 2026-11-10 (poly16): + the voices' slots (MD_STATE_DM); W5: tables to DDR; W2: + the scanner; PING: + its code, state, tables; SHFT: + state, tables; RESONATOR: + code, scratch, tables
STOCK_BLOCK1_END = 0x2DD52C
DM_CACHE_32K = 0x2E8000                      # the lowest byte a 32 KB DM cache would own
# 2026-11-10 (poly16): the startup's DM cache is 16 KB (size code 0, decoded in
# docs/waverider-dsp-silence.md, "The startup cache configuration": 0x2ec000..0x2effff, the same
# code that leaves block 3's top 16 KB to the I-cache), so REGION may reach 4 KB below it
DM_CACHE_16K = 0x2EC000                      # the lowest byte the startup's 16 KB DM cache owns
REGION_CACHE_GAP = 0x1000
CODE_SPAN = 0x400                            # each code object is padded to this
STATE_DM, STATE_BYTES = 0x2DDE00, 0x380      # save area, PERC's scratch, idle_load's state
# PERC (v0.11, docs/perc.md): machine type 5, in Waverider's former place. Its code is
# too big for L1 (about 26 KB), so it runs from L2, above everything the stock stream
# loads (scripts/sharc_l2_ceiling.py: neither the engine's init nor any stock machine
# touches L2 above the image's end) and well below the startup's non-cacheable window
# 0x200fa000..0x200fdfff; the I-cache (enabled by the startup, docs/waverider-dsp-silence.md)
# serves it. Its voices' state and scratch stay in L1, its tables in DDR.
# 2026-11-12 (the User, option b of scratch/perc-room): PERC starts 7.5 KB lower, at 0x200BE200 (0x200C0000 since
# v0.11): the L2 under it was unused past the bus pass's state (with the moved inserts' state it ends at 0x200BE100),
# and PERC with ANALOG 2's WDTH and PLAITS PART/STRG at 16 voices (176,550 B) no longer fit 168 KB. The ceiling
# 0x200EA000 stays.
PERC_L2_LOAD = 0x200BE200
PERC_L2_SPAN = 0x2BE00                       # 175.5 KB (2026-11-12, from 0x200be200); 168 KB (2026-11-11: 169,538 B of code with SID, the DPRO machines and VO-6 back; its end is the L2 ceiling 0x200ea000); 160 KB (v0.45 + b4, 2026-11-09: 150,710 B of code, BOUNCE's type and v0.45's PERC changes; 147 KB PLAITS VA+FM+ADD+SWARM+NOISE+PART+STRING+MODAL+BD+SD+HH, 2026-11-09: 149,892 B of code; VA 131,794; TB303: 128,282 B; PLAITS 123,128; 118,986 without SID, the DPRO machines and VO-6, 2026-11-08;
                                             # 142 KB SOPHIE, 140 KB v0.24..v0.42, 80 KB v0.17..v0.23). The span is zero-padded into
                                             # the DSP upload, so it is kept to the code
PERC_SW = 0xB80000 + (PERC_L2_LOAD - 0x20000000) // 2       # 0xbdf100 (0xbe0000 until 2026-11-12)
L2_IMAGE_END = 0x2008823C                    # the stock stream's last L2 byte
L2_NOCACHE = 0x200FA000                      # the startup's non-cacheable L2 window starts here
PERC_SCRATCH_DM = 0x2DDE80                   # 55 words (dnfw.perc.machines.SC_WORDS)
PERC_STATE_DM, PERC_STATE_STRIDE = 0x2DE180, 128             # 16 voices x 32 words
PERC_TABLES_DDR = 0x81216000                 # dnfw.perc.machines.tables_bytes
# 2026-11-12 (perf, opt-synths; docs/memory-map.md's DSP claims, holes F1 and F3): L1 copies of what PERC's voices
# look up every sample, which the program reads instead of the DDR originals (those stay, as does the link's
# shipping): exp2 (513 words) in F1. The hole was zeros in the upload already (spans() pads), so the upload is the
# same size. (tan stays in DDR: F3 is the bus FDN8 instances' stores, dnfw.inserts.bus.FD_L1 0x2E4050..0x2E53D0.) The sine is stock's own L1 sine S1 (STOCK_SINE_DM: 257 f32, sin(2 pi k / 256),
# loaded by stock's boot stream into block 0 and never written at run time, the runner's write-watch): the User's
# merge of SHFT's sine into it, 26 of its words one ulp apart.
PERC_EXP2_DM = 0x2E0640                      # .. 0x2E0E44
STOCK_SINE_DM, STOCK_SINE_N = 0x25D980, 257
# the Machinedrum machines (v0.17, docs/md.md): their tables (the sine, which the DSP fills
# itself, then the host's and DSP2's tables, read from the owner's MD firmware at build
# time), and 16 slots x 1 KB of words
MD_TABLES_DDR = 0x82000000
# v0.32: the voices' working state out of DDR into L2 (docs/others-dn2-research.md: on the
# unit a DDR access costs several times its instruction; L2 0x20088400..0x200B0000 is proven
# on units, by complex-ping's mods, and nothing of the stock's touches L2 above its image,
# scripts/sharc_l2_ceiling.py). The Machinedrum's 16 slots x 1 KB (the Monomachine voices
# keep theirs in the same slots), then the Monomachine's shared scratch (and the voice order
# in its tail). The P-I delay lines (128 KB, too big for the room) stay in DDR, at the
# address they always had, now loaded with zeros at power-on too.
MD_STATE_L2 = 0x200A0000                     # until 2026-11-10: now MD_STATE_DM (the room is left unused)
# 2026-11-10 (poly16, the User: 16 PLAITS voices on every engine): the 16 slots x 1 KB out of L2
# into L1 block 1, above XDLY's state: every voice reads and writes its slot words all through its
# block (a PLAITS voice 1,100 .. 3,000 accesses a block), and an L1 access costs no more than its
# instruction (dnfw/docs dsp-cost.md). Zeros at power-on: a fill block, nothing in the upload.
MD_STATE_DM = 0x2E7000
MNM_SCRATCH_L2 = 0x200A4000
MNM_SCRATCH_BYTES = 0x4000
# v0.36: the DPRO tables (DDRW's and DENS's busiest DDR reads, dnfw.mnm.core DP_TABLES: 976
# words), copied here from the Monomachine tables by the Digibank build, once
MNM_DT_L2 = MNM_SCRATCH_L2 + MNM_SCRATCH_BYTES        # 0x200A8000
MNM_DT_BYTES = 0x1000
# v0.37: the main mix, as the master mix call takes it, for the recorder's MAIN (sampler.machines.MAIN_TAP)
MAIN_TAP_L2 = MNM_DT_L2 + MNM_DT_BYTES                 # 0x200A9000
MAIN_TAP_BYTES = 0x200
MD_DELAY_DDR = 0x82200000                    # 16 slots x core.PI_DELAY_STRIDE
# FDN8 (docs/fdn8.md, dnfw.fdn8): the reverb in the stock reverb's slot. Its code in L2 after the
# main mix's tap (inside 0x20088400..0x200b0000, the range complex-ping's mods proved on units),
# its state in L1 block 1's last 3 KB (after the Monomachine's render scratch), its ring in
# DDR (256 KB of float32, zeros at power-on). The FX bus's CJUMP to the stock reverb (sw
# 0x1c1d11) gets wr_fdn8 as its target; wr_fdn8 JUMPs on to the stock reverb unless TYPE (k 48)
# asks for FDN8.
FDN8_L2_LOAD = 0x200AA000
FDN8_L2_SPAN = 0x2400                        # 9 KB (2026-11-11: 10 KB until the send pages' second page: its code went to XDLY's; fdn8.asm 7,018 B; 16 KB until XDLY took the rest)
FDN8_SW = 0xB80000 + (FDN8_L2_LOAD - 0x20000000) // 2       # 0xbd5000
FDN8_STATE_DM = 0x2E6400
FDN8_RING_DDR = 0x82400000
FDN8_RING_BYTES = 0x80000                   # 512 KB (256 KB until LONG)
# XDLY (docs/xdly.md, dnfw.xdly): optimist's cross-modulated dual delay in the stock delay's slot.
# Its code in L2 after FDN8's (up to 0x200b0000, the range proven on units), its words in the last
# 512 B of FDN8's L1 block, its two lines in the stock delay's own 4 MB sample area in DDR. The FX
# bus's call of the stock delay (sw 0x1c1c58) gets wr_xdly as its target; wr_xdly JUMPs on to the
# stock delay unless TYPE (k 40, Delay FX Routing) asks for XDLY.
XDLY_L2_LOAD = FDN8_L2_LOAD + FDN8_L2_SPAN   # 0x200ac400
XDLY_L2_SPAN = 0x200ADA00 - XDLY_L2_LOAD     # 5.5 KB (4.5 KB until 2026-11-11) (2026-11-10: 0x600 to the inserts, SUB DIST GATER RING; xdly.asm 4,148 B)
XDLY_SW = 0xB80000 + (XDLY_L2_LOAD - 0x20000000) // 2       # 0xbd6200
XDLY_STATE_DM = 0x2E6E00
DELAY_SITE_SW = 0x1C1C58                     # the FX bus: CALL 0xb8482c (DB), then its two pushes
DELAY_SITE_STOCK = bytes.fromhex("0418b8002c48")
STOCK_DELAY_SW = 0xB8482C
# the per-track inserts (docs/inserts.md, dnfw.inserts): their pass in L2 after FDN8's span (inside
# the range proven on units; XDLY's branch ends its span here), their state after the code. smp.asm's
# tail JUMPs to wr_ins, which JUMPs on to PING.
INS_L2_LOAD = 0x200ADA00                     # 2026-11-10 (0x200AE000 until the four ports)
INS_L2_SPAN = 0x1C00                         # the code (0x1b00 until 2026-11-11: one, the bus pass's moved inserts); 0x1800 until
                                             # 2026-11-10: two slots' state and the unpacked records need the room)
INS_SW = 0xB80000 + (INS_L2_LOAD - 0x20000000) // 2          # 0xbd7000
INS_STATE_DM = 0x2E3000                                      # 2026-11-11 (perf): L1, in the zeros after the shared tail (was L2 0x200af400)
# the stereo inserts after the pan (docs/inserts.md "After the pan", dnfw.inserts.post): their code in
# L2 after the inserts' state (below the sample machines' span), their state after the code, their rings
# in DDR. The engine's call of the FX sends (sw 0x1c3054) gets wr_inpost as its target; wr_inpost JUMPs on
# to the sends.
POST_L2_LOAD = 0x200B0000
POST_L2_SPAN = 0x1800                        # the code (4,078 B since 2026-11-11, the unrolled loops; 0x1000 before; the L2 from 0x200b1800 to the sample machines' is unused)
POST_SW = 0xB80000 + (POST_L2_LOAD - 0x20000000) // 2        # 0xbd8000
# 2026-11-09: DRONE's BEAT side blocks at 0x200b1800 (dnfw.inserts.post.SIDE_L2, 0x900 B); the A2 filter
# machines' pass (dnfw.a2f.program): its code, then its state
A2F_L2_LOAD = 0x200B2400
A2F_L2_SPAN = 0x3400                          # the code; then the state (dnfw.a2f.program.STATE)
A2F_STATE_DM = REGION[0]                      # 2026-11-11 (perf): the state in L1, the free 2 KB at the region's start
                                              # (was L2 0x200b5800: every word an L2 access, 4 cycles)
A2F_SW = 0xB80000 + (A2F_L2_LOAD - 0x20000000) // 2
POST_STATE_DM = 0x2E3A40                                     # L1 too (was L2 0x200b1000): to 0x2e4044
SENDS_SITE_SW = 0x1C3054                     # the engine: CJUMP 0x1c1738 (DB), then its two pushes
SENDS_SITE_STOCK = bytes.fromhex("04181c003817")
# 2026-11-10: the bus inserts (docs/inserts.md "On the track's bus", dnfw.inserts.bus): FDN8 and XDLY per
# track on the routing's per-track blocks. 2026-11-11: the routing's first instruction after its per-track
# loop (sw 0x1c1fef) becomes JUMP wr_inbus, which does that instruction and JUMPs back to sw 0x1c1ff2, so
# the main bus is summed from the blocks after the inserts (until then the engine's call of the output
# stage, sw 0x1c307b, had wr_inbus as its target: the main mix never heard them). Its code in the
# 8.5 KB between the sample machines' (to 0x200bc000) and PERC's (0x200be200); its state after it (the
# instances' stores, not loaded); each instance's DDR in dnfw.inserts.design (FDN8_RING_DDR,
# XDLY_LINES_DDR), not loaded either (a fresh instance clears, or never reads, what it has not written)
INSBUS_L2_LOAD = 0x200BC000
INSBUS_L2_SPAN = 0x1000                      # (0xc00 until 2026-11-11: the unrolled copy loops, insbus.asm 3,154 B)
INSBUS_SW = 0xB80000 + (INSBUS_L2_LOAD - 0x20000000) // 2    # 0xbde000
INSBUS_STATE_L2 = INSBUS_L2_LOAD + INSBUS_L2_SPAN            # 0x200bd000
# 2026-11-12: the chorus SEND's TYPE JUNO (dnfw.inserts.jsend, docs/inserts.md "The chorus send"): its code in L2 in
# the old MD state room after opt-samples' 0x200a0000..0x200a1800 (claimed in docs/memory-map.md's SHARC list); the
# FX bus's CALL of the stock chorus retargeted to it; its scratch is the post pass's (L1), its words and ring in DDR
JSEND_L2_LOAD = 0x200A1800
JSEND_L2_SPAN = 0x1000
JSEND_SW = 0xB80000 + (JSEND_L2_LOAD - 0x20000000) // 2       # 0xbd0c00
CHORUS_SITE_SW = 0x1C1BE1                    # the FX bus: CALL 0xb84d5c (DB), then its two pushes
CHORUS_SITE_STOCK = bytes.fromhex("0418b8005c4d")
assert JSEND_L2_LOAD + JSEND_L2_SPAN <= MNM_SCRATCH_L2
# 2026-11-12 (perc-layout, scratch/perc-layout/README.md; claimed with the DSP memory arbiter, dsp-claims): PERC's code
# that only events run (the machines' knob scaling `host` and `init` steps, and three subroutines: dnfw.md.voice
# STEP_SPAN, dnfw.perc.program SUB_SPAN; on the SHARC runner, 88 cases, not one of their instructions ran in a steady
# block) in the last free L2 inside the floor, so PERC's own span keeps the code every block runs. The same L2 SRAM
# and I-cache as PERC's span: the same cost. name -> (load address, span, sw address)
PERC2A_L2_LOAD, PERC2A_L2_SPAN = 0x2009B400, 0x4C00          # to 0x200a0000 (SMP_TABLES_L2): host bodies
PERC2B_L2_LOAD, PERC2B_L2_SPAN = 0x200A2800, 0x1800          # after JSEND's, to MNM_SCRATCH_L2: init bodies
PERC_SPANS = {name: (at, span, 0xB80000 + (at - 0x20000000) // 2)
              for name, at, span in (("perc2a", PERC2A_L2_LOAD, PERC2A_L2_SPAN),
                                     ("perc2b", PERC2B_L2_LOAD, PERC2B_L2_SPAN))}
assert JSEND_L2_LOAD + JSEND_L2_SPAN <= PERC2B_L2_LOAD and PERC2B_L2_LOAD + PERC2B_L2_SPAN <= MNM_SCRATCH_L2
ROUTE_SITE_SW = 0x1C1FEF                     # the routing, after its per-track loop: R2 = DM(0x257980)
ROUTE_SITE_STOCK = bytes.fromhex("021025008079")
ROUTE_RESUME_SW = 0x1C1FF2
# 2026-11-10: the L2 code spans are loaded as the code and 128 bytes of zeros, not padded to the span
# (each span's zeros counted in the 1 MiB DSP upload); what lies between is loaded with nothing. 128:
# the hardware rule BRANCH-12 (scripts/gate_hwrules.py) wants 12 valid 48-bit instructions (36 parcels,
# 72 bytes) after every branch, the code's last one included
L2_TAIL = 128
REVERB_SITE_SW = 0x1C1D11                    # the FX bus: CJUMP 0xb836bc (DB), then its two pushes
REVERB_SITE_STOCK = bytes.fromhex("0418b800bc36")
STOCK_REVERB_SW = 0xB836BC
# the sample machines (v0.13, docs/sampler.md): code in L2 after PERC's span, voices and
# scratch in L1 (Waverider's former loop room), the sample pool in DDR from 64 MB in
# 2026-11-09 (PLAITS' eleven engines took PERC's code past 144 KB): the sample machines' code moved
# below PERC, after FDN8's code (0x200aa000..0x200ae000), so PERC's span can grow up to the
# non-cacheable window's 64 KB margin (the User's choice for this limit, 2026-11-08: move the
# sample code down). Until then it followed PERC's span:
SMP_L2_LOAD = 0x200B6000                     # 0x200e0400 (PLAITS VA; 0x200df800 TB303; 0x200de400 PLAITS; 0x200dd400 2026-11-08; 0x200e3800 SOPHIE; 0x200e3000 v0.24..v0.42; 0x200d4000 v0.17..v0.23, 0x200d0000 until v0.16)
SMP_L2_SPAN = 0x6000                         # v0.28: 24 KB (the re-latch took the code past 19 KB; 20 KB v0.18..v0.27, 32 KB until v0.16)
SMP_SW = 0xB80000 + (SMP_L2_LOAD - 0x20000000) // 2          # 0xbdb000 (below PERC, 2026-11-09; 0xbf0200 PLAITS VA; 0xbefc00 TB303; 0xbef200 PLAITS; 0xbeea00 2026-11-08; 0xbf1c00 SOPHIE; 0xbf1800 v0.24..v0.42; 0xbea000 v0.17..v0.23)
PVMIX_L2_LOAD = SMP_L2_LOAD + SMP_L2_SPAN - 0x400           # v0.25: pvmix.asm (wr_pvmix)
PVMIX_SW = 0xB80000 + (PVMIX_L2_LOAD - 0x20000000) // 2
SMP_STATE_DM, SMP_STATE_STRIDE = 0x2DEF00, 128  # 16 voices x 128 bytes (v0.15)
SMP_SCRATCH_DM = 0x2DF700                    # after 16 x 128 bytes of state (v0.15)
SMP_SCRATCH_BYTES = 0x100                    # dnfw.sampler.program.SC_WORDS must fit (test_waverider_dsp)
SMP_STAGE_DM = SMP_SCRATCH_DM + SMP_SCRATCH_BYTES   # the recorder's block (dnfw.sampler.machines.REC_STAGE)
SMP_LINK_DM = SMP_STAGE_DM + 0x80            # the fast link's scratch, then its packet buffer (v0.16)
SMP_POOL_DDR = 0x84000000                    # the pool's directory, then its frames
# v0.18: the DT2 reader's coefficients (dnfw.sampler.program.tables_bytes, from the owner's
# DT2 image) in DDR; each voice's decimator (12 words) in L1, where Waverider's loop was.
# 2026-11-12 (opt-samples, 16 voices with room to spare): every 96 kHz sample reads a row of six
# and every output sample the decimator's four, 640 DDR reads a voice-block. The interpolator's
# 256 x 6 now lie in L2, in the room the Machinedrum slots left (MD_STATE_L2, unused since
# 2026-11-10), the decimator's four and the gain in L1 after the voices' decimators (the 128 B
# below RELATCH, free since v0.28)
SMP_TABLES_DDR = 0x81218000                             # until 2026-11-12
SMP_TABLES_L2 = 0x200A0000                              # 6,144 B, to 0x200a1800 (MNM_SCRATCH_L2 is 0x200a4000)
assert PERC2A_L2_LOAD + PERC2A_L2_SPAN <= SMP_TABLES_L2   # perc-layout's span 2a ends where these start
SMP_DEC_DM = SMP_LINK_DM + 0x500                        # 16 x 48 bytes, to 0x2e0080 (W2_RND_DM is 0x2e0100)
SMP_DTAB_DM = SMP_DEC_DM + 16 * 48                      # 0x2e0080: 20 B (sampler.program.RELATCH is 0x2e0100)
# 2026-11-12: the reader's taps through an L1 line (sampler.program.LINE_WORDS, 24 words), its tag the word
# before it, its switch the word before that: in the rest of that room (zeros at power-on; a render sets
# both before it reads the line)
SMP_LINE_DM = SMP_DTAB_DM + 0x20                        # 0x2e00a0..0x2e0100
# W2's random table (dnfw.waverider.live.rnd_table): Waverider is gone (v0.11), but
# RESONATOR, CZ and GRAN read it here
W2_RND_DM = 0x2E0100                                         # 256 float32 in [0, 1)
# v0.50: the recorder's GAIN (dnfw.sampler.machines.REC_GAIN): a buffer take's dB index (0: none,
# the RECORDER's v0.49 scaling) and its factor. v0.50 put them at 0x2e0080; v0.52 merge: that room is
# SMP_DTAB_DM's now, so they are the sample machines' scratch words 'rgain' and 'rgfac' (zeros at load)
REC_GAIN_DM = SMP_SCRATCH_DM + 0xF4                         # 0x2df7f4, 2 words
# PING (docs/ping.md): its code (entered from machine5_live's tail), 16 x 128 bytes
# of state, a few words of scratch, then its tables (dnfw.ping.live.tables_bytes).
# v0.45: PING removed. Only its code address stays in use (ping.asm, now the shared tail);
# PING_STATE_DM, PING_T_DM and PING_TABLES_DDR are no longer loaded or read by anything
# shipped, and are kept only for the retired generators (gen_ping/gran_asm's helpers).
PING_CODE_DM, PING_CODE_SPAN = 0x2E0500, 0x1800
PING_SW = PING_CODE_DM // 2                                  # 0x170280
# 2026-11-10 (stock-hotspots item 2, docs/stock-hotspots.md): the stock engine's 16 mono track buffers
# (128 B each, 32 floats) from DDR to L1: trackbuf.asm, run once from entry_mark.asm's first pass,
# copies them to TRACKBUF_DM (the 2 KB PING's state held, zeros in the stream) and re-points the two
# tables that hold their addresses. Its code is in the free span between ping.asm's tail and there.
TRACKBUF_CODE_DM = 0x2E1000
TRACKBUF_SW = TRACKBUF_CODE_DM // 2                          # 0x170800
TRACKBUF_DM, TRACKBUF_BYTES = 0x2E1D00, 16 * 128             # to 0x2e2500
TRACKBUF_DDR = 0x804ACF90                                    # where the stock puts them
TRACKAUX_DM, TRACKAUX_DDR, TRACKAUX_BYTES = 0x2E1C00, 0x804ACE90, 0x100   # the extra 256 B just below them
TRACKAUX_PTR = 0x254AA0                                      # the one word that holds its address
PING_STATE_DM = PING_CODE_DM + PING_CODE_SPAN                # 0x2e1d00
PING_T_DM = PING_STATE_DM + 16 * 128                         # 0x2e2500: t, then scratch
# GRAN (v0.10): PING's and SHFT's tables moved to DDR, so GRAN's code takes theirs
# in L1 (0x2e2540, where PING's tables were) and its state SHFT's (0x2e4b00)
PING_TABLES_DDR = 0x81210000
GRAN_CODE_DM = PING_T_DM + 0x40                              # 0x2e2540
GRAN_SW = GRAN_CODE_DM // 2                                  # 0x1712a0
GRAN_SCRATCH_DM = 0x2E3A00                                   # 32 words, after GRAN's code
# SHFT (docs/shft.md): its code is in ping.asm; 16 x 256 bytes of state (zeros, so a
# fill block in the stream); its sine and pow2 tables (dnfw.shft.live) in DDR
SHFT_STATE_DM, SHFT_STATE_STRIDE = 0x2E3B00, 256             # after GRAN's code
SHFT_TABLES_DDR = 0x81212000
# GRAN (docs/gran.md, filter type 8): 16 x 128 bytes of state in L1, its tables and
# 16 ring buffers of 32768 float32 (128 KB a track, zeros: a fill block) in DDR
GRAN_STATE_DM, GRAN_STATE_STRIDE = SHFT_STATE_DM + 16 * SHFT_STATE_STRIDE, 128   # 0x2e4b00
# v0.43: the Monomachine machines' render scratch (dnfw.mnm.core.Layout: the decimator's input,
# SID's phases, the coefficients, the words, DPRO's buffers) out of L2 into L1 after GRAN's state:
# every Monomachine voice reads and writes it all through its block (SID about 7,000 accesses,
# DDRW 6,800, docs/dsp-cost.md), and an L1 access costs no more than its instruction. The
# bookkeeping (keys, costs, the voice order, rests, strikes) stays at MNM_SCRATCH_L2.
MNM_RENDER_DM = 0x2E5400
MNM_RENDER_BYTES = 0x1000                                    # to 0x2e6400 (core.RENDER_BYTES used)
GRAN_TABLES_DDR = 0x81214000
GRAN_BUF_DDR, GRAN_BUF_STRIDE = 0x81400000, 0x20000
# v0.26: RESONATOR and CZ are gone (their types are the Monomachine machines', in PERC's
# voice: docs/mnm.md); their L1 code and scratch are zeros, their DDR the Monomachine's:
# its scratch (the decimator's buffers), then 16 slots' own state, 2 KB each

# its tables (from the owner's Monomachine OS) are decoded with the Machinedrum's, after
# the sine (dnfw.md.core.TABLE_LAYOUT["mnm"]), from what the ColdFire sends at power-on

DDR_FLOOR = 0x80600000                       # nothing of ours below this in DDR
IDLE_DM = 0x2DEA00                           # idle_load.asm
IDLE_SW = IDLE_DM // 2                       # 0x16f500
IDLE_STATE_DM = 0x2DE100                     # its save area and counters (state block tail)
COUNT_DM = 0x2DEC00                          # block_count.asm, after idle_load.asm
COUNT_SW = COUNT_DM // 2                     # 0x16f600: the entry JUMP's target, which goes on to PERC
EMARK_DM = 0x2DED00                          # entry_mark.asm: EMUCLK as the handler calls 0x1c2712
EMARK_SW = EMARK_DM // 2                     # 0x16f680
L2_LOAD, L2_SW = 0x20000000, 0xB80000        # L2 code: load address 0x20000000 is sw 0xb80000

# stock sites
ENTRY_SW = 0x1C9448                          # i5=dm(-0x18,i6); r10=dm(-0x22,i6)
ENTRY_STOCK = bytes.fromhex("089ce80a089c5e05")
NOP16 = bytes.fromhex("0100")                # the firmware's own 16-bit NOP (sw 0x1c9447)
LOOKUP_DM = 0x25D748                         # frame nibble -> machine type, 8 words
LOOKUP_STOCK = (0, 1, 2, 3, 4, 0, 0, 0)
MACHINE6 = 6                                 # RESONATOR: lookup[6] = 6 (stock 0, FM Tone)
MACHINE7 = 7                                 # CZ: lookup[7] = 7 (stock 0, FM Tone)
# v0.13: the lookup moves to a 16-entry copy in our region (the frame field indexes it
# unmasked, sw 0x1c295d `R2 = DM(I5, M0)` after `I5 = 0x25d748` at sw 0x1c2958), so the
# machine types can grow past 8. The word before it is 0, as stock's is (0x25d744), so a
# frame value of -1 reads FM Tone as before. Types with no engine read 0 (FM Tone).
LOOKUP_SITE_SW = 0x1C2958                    # I5 = 0x25d748
LOOKUP_SITE_STOCK = bytes.fromhex("0f150025d748")   # parcels, MSW first
LOOKUP16_DM = 0x2DEE04                       # 16 words; 0x2dee00 is the [-1] guard (0)
from ..mnm import machines as _mnm_types    # noqa: E402
from ..sampler import machines as _smp_types
MACHINE_TYPES = max(16, max(_mnm_types.CF_TYPES) + 1, max(_smp_types.TYPES) + 1)   # v0.26: 17 with a Monomachine machine at 16; v0.44: BOUNCE at 17; the reserved types too
SMP_ENGINE_SLOT = 5                          # the engine slot the sample machines borrow
SMP_TYPES = _smp_types.TYPES                 # ONESHOT WERP STRETCH REPITCH GRID SLICE (v0.19); v0.44 BOUNCE (17)
ENGINES = {5: "PERC", 8: "ONESHOT", 12: "GRID"}   # types with an engine of ours
MNM_TYPES = _mnm_types.TYPES                 # v0.26: the Monomachine machines (PERC's voice, so PERC's slot)
RESERVED_TYPES = tuple(_mnm_types.RESERVED)   # a machine this build leaves out (dnfw.builder; the five removed
                                             # 2026-11-08 until 2026-11-11): the MIDI engine's slot, silent
MIDI_ENGINE_SLOT = 4                         # stock's MIDI machine: the DSP renders nothing for it

IDLE_SITE_SW = 0xB88ABB                      # prvIdleTask's back edge: jump (pc,-0x10)
IDLE_SITE_STOCK = bytes.fromhex("3e07ff00f0ff")
IDLE_RETURN_SW = 0xB88AAB                    # the loop's top: call prvCheckTasksWaitingTermination
CALL_SITE_SW = 0x1C9FB9                      # the handler's `r4 = 0x268438` before `cjump 0x1c2712`
CALL_SITE_STOCK = bytes.fromhex("040f26003884")
# v0.25: the recorder's preview (dnfw.sampler.program.pvmix). The per-block driver's call of
# 0x1c9d3f (the main mix into the SPORT page): `CJUMP 0x1c9d3f (DB)` and its two delay-slot
# pushes, 18 bytes from sw 0x1c9fd2. The site becomes `JUMP PVMIX_SW`; wr_pvmix ends with
# these same three instructions (absolute: the call, its pushes and its return are stock's).
PVMIX_SITE_SW = 0x1C9FD2
PVMIX_SITE_STOCK = bytes.fromhex("04181c003f9dfe5f00814d18c09f1c00da9f")
PVMIX_ROOM = 0x400                           # its place: the last 1 KB of the sample machines' L2 span


class DspError(ValueError):
    pass


def lookup16() -> bytes:
    """the relocated machine lookup: [-1] = 0, then type -> engine slot: the stock five
    and ours as themselves, the sample machines (8..12) to 5 -- PERC's slot, so the stock
    code takes the one path for them the runner and the instrument have proven (the
    record's +0x1b4 copy indexes 8-entry tables at sw 0x1c299f and in the render code; 8
    and above would read past them). PERC and the sample machines tell themselves apart by
    the frame's own type word; one whose machine has no renderer yet stays silent on that
    slot. A removed machine's reserved type (2026-11-08) reads 4, the MIDI machine's: the DSP
    renders nothing for it, so the track is silent (exactly 0 in the SHARC runner). In PERC's
    slot it would have had the stock render for that slot (peak 0.02: what PERC does not
    claim is not silent there), as engine 0 FM Tone. Any other type reads 0 (FM Tone), as
    stock answers 5-7."""
    table = [t if t < 5 or t in ENGINES and t < 8 else
             MIDI_ENGINE_SLOT if t in RESERVED_TYPES else
             SMP_ENGINE_SLOT if t in SMP_TYPES or t in MNM_TYPES else 0
             for t in range(MACHINE_TYPES)]
    return struct.pack(f"<{1 + MACHINE_TYPES}I", 0, *table)


def sw_to_load(sw: int) -> int:
    return LOAD_ALIAS + 2 * sw


def dm_to_load(dm: int) -> int:
    return LOAD_ALIAS + dm


def l2_sw_to_load(sw: int) -> int:
    return L2_LOAD + 2 * (sw - L2_SW)


def _code() -> dict:
    if not CODE.exists():
        raise DspError(f"{CODE.name} is missing: run scripts/gen_waverider_sharc.py")
    return json.loads(CODE.read_text(encoding="utf-8"))


def objects() -> dict[str, bytes]:
    """The committed SHARC objects: PERC, the entry JUMP, the stubs, the filters, the machines."""
    spec = _code()
    return {name: sharc_object.load_bytes(bytes.fromhex(spec[name]["object_parcels_be"]))
            for name in ("perc", "perc2a", "perc2b", "smp", "entry_jump", "idle_load", "idle_jump", "block_count",
                         "entry_mark", "emark_jump", "lookup_ptr", "ping", "trackbuf",
                         "pvmix", "pvmix_jump", "fdn8", "xdly", "inserts", "inspost", "insbus", "insbus_jump", "a2f",
                         "jsend")
            if name in spec}


def pvmix_object() -> bytes:
    """wr_pvmix with its last three instructions (48-bit placeholders) replaced by the
    stock's own call of 0x1c9d3f and its delay-slot pushes (section7 checks the stock has
    exactly these at PVMIX_SITE_SW)"""
    code = objects()["pvmix"]
    site = PVMIX_SITE_STOCK
    from ..sampler.program import PVMIX_TAIL
    code, after = code[:-6], code[-6:]          # the JUMP back to the driver stays
    tail = code[-len(PVMIX_SITE_STOCK):]
    for k, w in enumerate(PVMIX_TAIL):
        c = tail[6 * k:6 * k + 6]               # `R0 = imm32` (17a): its low parcels the immediate
        if c[2:4] != (w >> 16).to_bytes(2, "little") or c[4:6] != (w & 0xFFFF).to_bytes(2, "little"):
            raise DspError(f"pvmix.asm's last instructions are not its placeholders ({tail.hex()})")
    return code[:-len(PVMIX_SITE_STOCK)] + site + after


def _ins_state_spans() -> list[tuple[str, int, bytes]]:
    """the pre and post insert passes' state in L1 (2026-11-11, perf: they were in L2). Not all zeros: the pre
    pass's holds GATER's rate and pattern tables (ports), which perf's zero fill did not load"""
    from ..inserts import post as ins_post
    from ..inserts import program as ins_program
    return [("the inserts' state: 32 records' words, GATER's tables, the unpacked records, the flags (L1)",
             INS_STATE_DM, ins_program.state_bytes()),
            ("the stereo inserts' state (L1)", POST_STATE_DM, ins_post.state_bytes())]


def _a2f_state_span(obj) -> tuple[str, int, bytes]:
    """the region's first 2 KB: the A2 filters' state and mix tables when that pass is built (2026-11-11,
    perf: they were in L2), else free since v0.11 (Waverider's reader and osc 2; zeros)"""
    if "a2f" not in obj:
        return ("free since v0.11 (Waverider's reader and osc 2; zeros)", REGION[0], b"")
    from ..a2f import program as a2f_program
    st = a2f_program.state_bytes()
    assert a2f_program.STATE == A2F_STATE_DM and len(st) <= 0x800 and A2F_STATE_DM + 0x800 <= STATE_DM
    return ("the A2 filters' state and mix tables (L1)", A2F_STATE_DM, st)


def spans() -> list[tuple[str, int, bytes]]:
    """(what, load address, payload) of every block this adds, in stream order.

    Each payload is zero-padded up to the next span's start (the last to REGION's
    end), so the region is written end to end and every code object is followed by
    at least 64 bytes of zeros (a zero word is a NOP)."""
    raw = _raw_spans()
    out = []
    for k, (what, at, payload) in enumerate(raw):
        end = raw[k + 1][1] if k + 1 < len(raw) else REGION[1]
        if len(payload) > end - at:
            raise DspError(f"{what} ({len(payload)} bytes) does not fit before {end:#x}")
        if "asm" in what and end - at - len(payload) < 64:
            raise DspError(f"{what} leaves fewer than 64 bytes of NOP padding")
        out.append((what, dm_to_load(at), payload + bytes(end - at - len(payload))))
    return out


def _raw_spans() -> list[tuple[str, int, bytes]]:
    """spans()' blocks before their padding: (what, DM address, payload), in address order"""
    obj = objects()
    return [
        _a2f_state_span(obj),
        ("state: save area, PERC scratch, idle_load's counters (zeros)", STATE_DM, bytes(STATE_BYTES)),
        ("PERC state: 16 voices x 128 bytes (zeros)", PERC_STATE_DM, bytes(16 * PERC_STATE_STRIDE)),
        ("idle_load.asm (wr_idle)", IDLE_DM, obj["idle_load"]),
        ("block_count.asm (wr_count)", COUNT_DM, obj["block_count"]),
        ("entry_mark.asm (wr_emark)", EMARK_DM, obj["entry_mark"]),
        ("machine lookup, 16 types ([-1] guard, then the table; v0.13)", LOOKUP16_DM - 4, lookup16()),
        ("sample machines' state: 16 voices x 128 bytes (zeros)", SMP_STATE_DM, bytes(16 * SMP_STATE_STRIDE)),
        ("sample machines' scratch (zeros)", SMP_SCRATCH_DM, bytes(SMP_SCRATCH_BYTES)),
        ("the recorder's staging block: 32 floats (zeros)", SMP_STAGE_DM, bytes(0x80)),
        ("the fast link's scratch and packet buffer (zeros; v0.16)", SMP_LINK_DM, bytes(0x500)),
        ("sample machines' decimators: 16 voices x 48 bytes (zeros; v0.18), then the decimator's four"
         " coefficients and the gain (2026-11-12)", SMP_DEC_DM, bytes(16 * 48) + _smp_tables()[-_smp_dtab():]),
        # v0.45: PING removed: ping.asm is the shared tail alone (still at PING_SW; every
        # machine of ours returns through it). PING's state span went with it; the stub pads
        # with zeros to REGION's end, so those bytes still load as zeros.
        ("ping.asm (wr_ping: the shared tail)", PING_CODE_DM, obj["ping"]),
        ("PERC's exp2 table, its L1 copy (2026-11-12)", PERC_EXP2_DM, _perc_exp2()),
        ("trackbuf.asm (wr_trackbuf: the stock track buffers to L1, once)", TRACKBUF_CODE_DM, obj["trackbuf"]),
        ("the stock track buffers in L1 (zeros; 256 B extra block, then 16 x 128 B)", TRACKAUX_DM,
         bytes(TRACKAUX_BYTES + TRACKBUF_BYTES)),
        *_ins_state_spans(),
        ("FDN8 state: its words, the LFOs' phases, the stock buffers' chunk table", FDN8_STATE_DM, _fdn8_state()),
        ("XDLY state: its words (zeros)", XDLY_STATE_DM, _xdly_state()),
        ("Machinedrum / Monomachine voices: 16 slots x 1 KB (zeros; L2 until 2026-11-10)", MD_STATE_DM,
         bytes(16 * _md_core().MD_STRIDE)),
    ]


def _perc_exp2() -> bytes:
    from ..perc import machines as PM
    data, at = PM.tables_bytes()
    out = data[at["exp2"]:at["tan"]]
    assert PERC_EXP2_DM + len(out) <= TRACKBUF_CODE_DM
    return out


def stock_sine() -> bytes:
    """stock's L1 sine S1 as its boot stream loads it (DT2_SECTIONS' section 7; 1.11 and 1.12 are the same)"""
    import os
    import pathlib
    from ..image import bootstream as BS
    data = pathlib.Path(os.environ["DT2_SECTIONS"], "section_7_BLOB.bin").read_bytes()
    return BS.read_span(data, dm_to_load(STOCK_SINE_DM), 4 * STOCK_SINE_N)


def _fdn8_state() -> bytes:
    if not _sel.on("FX_FDN8"):
        return b""
    from ..fdn8 import program as fdn8_program
    assert fdn8_program.STATE == FDN8_STATE_DM and fdn8_program.RING == FDN8_RING_DDR
    assert FDN8_STATE_DM >= MNM_RENDER_DM + MNM_RENDER_BYTES
    return fdn8_program.state_bytes()


def _xdly_state() -> bytes:
    if not _sel.on("FX_XDLY"):
        return b""
    from ..xdly import program as xdly_program
    from ..fdn8 import program as fdn8_program
    assert xdly_program.STATE == XDLY_STATE_DM
    assert fdn8_program.STATE + fdn8_program.STATE_BYTES <= XDLY_STATE_DM
    return xdly_program.state_bytes()


def delay_call() -> bytes:
    """the FX bus's CALL at DELAY_SITE_SW with wr_xdly as its target: the same instruction
    (parcels 0x1804, then the 24-bit address), only the address changed; the stock call when
    this build has no XDLY (dnfw.builder)"""
    if not _sel.on("FX_XDLY"):
        return DELAY_SITE_STOCK
    if XDLY_SW >> 24:
        raise DspError("wr_xdly is beyond a 24-bit address")
    return DELAY_SITE_STOCK[:2] + struct.pack("<HH", XDLY_SW >> 16, XDLY_SW & 0xFFFF)


def chorus_call() -> bytes:
    """the FX bus's CALL at CHORUS_SITE_SW with wr_jsend as its target: the same instruction (parcels 0x1804, then the
    24-bit address), only the address changed (2026-11-12, the chorus send's TYPE JUNO)"""
    if JSEND_SW >> 24:
        raise DspError("wr_jsend is beyond a 24-bit address")
    return CHORUS_SITE_STOCK[:2] + struct.pack("<HH", JSEND_SW >> 16, JSEND_SW & 0xFFFF)


def _ins():
    from ..inserts import design as ins_design
    return ins_design


def sends_cjump() -> bytes:
    """the engine's CJUMP at SENDS_SITE_SW with wr_inpost as its target: the same instruction
    (type 8a CJUMP (DB), parcels 0x1804, then the 24-bit address), only the address changed"""
    if POST_SW >> 24:
        raise DspError("wr_inpost is beyond a 24-bit address")
    return SENDS_SITE_STOCK[:2] + struct.pack("<HH", POST_SW >> 16, POST_SW & 0xFFFF)


def reverb_cjump() -> bytes:
    """the FX bus's CJUMP at REVERB_SITE_SW with wr_fdn8 as its target: the same instruction
    (type 8a CJUMP (DB), parcels 0x1804, then the 24-bit address), only the address changed; the
    stock CJUMP when this build has no FDN8 (dnfw.builder)"""
    if not _sel.on("FX_FDN8"):
        return REVERB_SITE_STOCK
    if FDN8_SW >> 24:
        raise DspError("wr_fdn8 is beyond a 24-bit address")
    return REVERB_SITE_STOCK[:2] + struct.pack("<HH", FDN8_SW >> 16, FDN8_SW & 0xFFFF)


def _shft_tables() -> bytes:
    from ..shft import live as shft_live
    return shft_live.tables_bytes()[0]


def _md_core():
    from ..md import core
    return core


def _perc_tables() -> bytes:
    from ..perc import machines as perc_machines
    return perc_machines.stream_tables()


def _digibank_room() -> None:
    """DDRW's and DENS's Digibank stand-in (built by the DSP, never shipped: dnfw.mnm.core DIGI)
    must lie past the Machinedrum and Monomachine tables and before the P-I delay lines."""
    from ..mnm import core as MNC
    mdc = _md_core()
    at = MD_TABLES_DDR + mdc.TABLE_LAYOUT["mnm"][0] + MNC.DIGI_OFF
    end = at + 4 * MNC.DIGI_WORDS
    if at < MD_TABLES_DDR + mdc.TABLE_LAYOUT["_end"][0] or end > MD_DELAY_DDR:
        raise DspError(f"the Digibank stand-in {at:#x}..{end:#x} overlaps the tables or the delay lines")


def _dpro_on() -> bool:
    """DPRO-DDRW or -DENS in this build (2026-11-11: back): the Digibank stand-in and the DPRO
    tables' L2 room"""
    return bool({"DPRO-DDRW", "DPRO-DENS"} & set(_mnm_types.NAMES))


def ddr_spans() -> list[tuple[str, int, bytes]]:
    """(what, load address, payload) of each DDR span (load address = address): the
    machines' and filters' state (zeros, so fill blocks) and tables."""
    if _dpro_on():
        _digibank_room()
    return [
        # (v0.45: "PING tables" at PING_TABLES_DDR dropped with PING)
        # v0.31: PERC's amp modulation (AMD) reads SHFT's sine here (dnfw.perc.live.layout).
        # v0.28 dropped this span with SHFT, so AMD read whatever the DDR held: on the
        # instrument any AMD above 0 silenced everything until a reboot (users' reports on
        # v0.29 and v0.30). The sine only; test_waverider_dsp checks every table PERC reads
        # is loaded by a span.
        # 2026-11-10 (shrink): AMD's sine and PERC's tan ship over the link (perc.machines.shipped_tail)
        ("PERC tables (exp2; the sample machines read it too)", PERC_TABLES_DDR, _perc_tables()),
        ("Machinedrum sine and tables (zeros: the DSP decodes them; v0.24)", MD_TABLES_DDR,
         bytes(_md_core().TABLE_LAYOUT[_md_core().SHIPPED][0])),
        # v0.26: what ships (the host's pitch table and zpack) comes over the fast link from
        # the ColdFire at power-on (dnfw.mods.waverider's table chunk): not in this stream
        ("Machinedrum P-I delay lines: 16 slots x 8 KB (zeros; v0.32)", MD_DELAY_DDR,
         bytes(16 * _md_core().PI_DELAY_STRIDE)),
        ("FDN8's ring: 64 K float32 (zeros)", FDN8_RING_DDR, bytes(FDN8_RING_BYTES)),
        ("the inserts' TAPE rings: 16 tracks x 512 float32 (zeros)", _ins().TP_RING_DDR, bytes(16 * 4 * _ins().TP_RING)),
        ("the post inserts' rings (CHOR, WIDE): 16 voice slots x 1024 float32 (zeros)", _ins().POST_RING_DDR,
         bytes(16 * 4 * _ins().POST_RING)),
        ("the chorus send's JUNO: its words and ring (zeros; 2026-11-12)", _ins().JS_STATE,
         bytes(_ins().JS_END - _ins().JS_STATE)),
        ("sample pool: its empty directory's magic and count (v0.17: no test sounds; the +Drive's load in)",
         SMP_POOL_DDR, _smp_pool()[:8]),
        ("sample pool: the rest of its directory and names (zeros)", SMP_POOL_DDR + 8,
         bytes(len(_smp_pool()) - 8))]


def _perc_sine() -> bytes:
    from ..shft import live as SL
    data, at = SL.tables_bytes()
    return data[at["sin"]:at["pow2"]]


def _smp_tables() -> bytes:
    from ..sampler import program as smp_program
    return smp_program.tables_bytes()


def _smp_dtab() -> int:
    from ..sampler import program as smp_program
    assert len(_smp_tables()) == smp_program.POLY_BYTES + smp_program.DTAB_BYTES
    return smp_program.DTAB_BYTES


def _smp_pool() -> bytes:
    from ..sampler import live as smp_live
    # v0.17: the Machinedrum's tables needed the DSP image's room, and since v0.16 the
    # +Drive holds the owner's own samples: the build ships an empty pool (the runner puts
    # the test sounds in itself, as the ColdFire's loader would)
    return smp_live.pool_bytes([], SMP_POOL_DDR)


def l2_spans() -> list[tuple[str, int, bytes]]:
    """(what, load address, payload) of what goes in L2: PERC's code, then the sample
    machines', each zero-padded to its span (so at least 64 bytes of NOPs after it)."""
    obj = objects()
    out = []
    for what, name, at, span in (("perc.asm (wr_perc), in L2", "perc", PERC_L2_LOAD, PERC_L2_SPAN),
                                 *((f"{n}.asm (PERC's event code), in L2", n, a, sp)
                                   for n, (a, sp, _sw) in PERC_SPANS.items() if n in obj),
                                 ("smp.asm (wr_smp), in L2", "smp", SMP_L2_LOAD, SMP_L2_SPAN)):
        code = obj[name]
        if name == "smp":                       # v0.25: wr_pvmix in the span's last 1 KB
            room = PVMIX_L2_LOAD - at
            pv = pvmix_object()
            if room - len(code) < 64 or PVMIX_ROOM - len(pv) < 64:
                raise DspError(f"smp.asm ({len(code)} bytes) or pvmix.asm ({len(pv)}) leaves fewer than "
                               "64 bytes of its room")
            out.append((what, at, code + bytes(room - len(code)) + pv + bytes(PVMIX_ROOM - len(pv))))
            continue
        if span - len(code) < 64:
            raise DspError(f"{name}.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
        out.append((what, at, code + bytes(span - len(code))))
    # v0.32: the voices' working state (zeros)
    out.append(("Monomachine scratch and the voice order, in L2 (zeros; v0.32; ANALOG2's mix tables)",
                MNM_SCRATCH_L2, _mnm_scratch()))
    if _dpro_on():
        out.append(("the DPRO tables' room in L2 (zeros, filled by the build; v0.36)", MNM_DT_L2,
                    bytes(MNM_DT_BYTES)))
    out.append(("the main mix's tap for the recorder's MAIN, in L2 (zeros; v0.37)", MAIN_TAP_L2,
                bytes(MAIN_TAP_BYTES)))
    # 2026-11-12: the DT2 sample reader's interpolator rows (DDR v0.18 .. 2026-11-11)
    poly = _smp_tables()[:-_smp_dtab()]
    assert SMP_TABLES_L2 + len(poly) <= MNM_SCRATCH_L2 and MD_STATE_L2 <= SMP_TABLES_L2
    out.append(("the DT2 sample reader's interpolator coefficients, in L2 (from the owner's DT2 image)",
                SMP_TABLES_L2, poly))
    code = obj["fdn8"]
    if FDN8_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"fdn8.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("fdn8.asm (wr_fdn8), in L2", FDN8_L2_LOAD, code + bytes(L2_TAIL)))
    code = obj["xdly"]
    if XDLY_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"xdly.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("xdly.asm (wr_xdly), in L2", XDLY_L2_LOAD, code + bytes(L2_TAIL)))
    code = obj["inserts"]
    if INS_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"inserts.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("inserts.asm (wr_ins), in L2", INS_L2_LOAD, code + bytes(L2_TAIL)))
    from ..inserts import program as ins_program
    assert ins_program.STATE == INS_STATE_DM
    code = obj["inspost"]
    if POST_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"inspost.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("inspost.asm (wr_inpost), in L2", POST_L2_LOAD, code + bytes(L2_TAIL)))
    from ..inserts import post as ins_post
    assert ins_post.STATE == POST_STATE_DM
    # both states are zeros in L1, inside the shared tail's zero fill (spans(): ping.asm's payload runs to FDN8's
    # state), clear of ping.asm's code and of FDN8's state and the Monomachine render scratch
    assert PING_CODE_DM + 0x400 <= INS_STATE_DM
    assert INS_STATE_DM + len(ins_program.state_bytes()) <= POST_STATE_DM
    assert POST_STATE_DM + len(ins_post.state_bytes()) <= MNM_RENDER_DM
    code = obj["jsend"]
    if JSEND_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"jsend.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("jsend.asm (wr_jsend: the chorus send's JUNO), in L2", JSEND_L2_LOAD, code + bytes(L2_TAIL)))
    code = obj["insbus"]
    if INSBUS_L2_SPAN - len(code) < L2_TAIL:
        raise DspError(f"insbus.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
    out.append(("insbus.asm (wr_inbus), in L2", INSBUS_L2_LOAD, code + bytes(L2_TAIL)))
    from ..inserts import bus as ins_bus
    assert ins_bus.STATE == INSBUS_STATE_L2 and ins_bus.END <= PERC_L2_LOAD
    assert (ins_bus.SITE_SW, ins_bus.RESUME_SW) == (ROUTE_SITE_SW, ROUTE_RESUME_SW)
    assert SMP_L2_LOAD + SMP_L2_SPAN <= INSBUS_L2_LOAD
    assert (_ins().FDN8_SW, _ins().XDLY_SW, _ins().BUS_STATE) == (FDN8_SW, XDLY_SW, INSBUS_STATE_L2)
    out.append(("the bus inserts' head: each instance's owner (zeros), the engines' I/O descriptor",
                INSBUS_STATE_L2, ins_bus.state_bytes()))
    # 2026-11-11: a moved slot 2's state (dnfw.inserts.bus.MV_STATE), zeros at power-on (a fill block): its
    # first run then starts fresh; and its entry, the pre pass's one insert after the pass's 48-bit JUMP
    assert _ins().INS_ONE_SW == INS_SW + 3
    out.append(("the moved inserts' state (zeros), in L2", ins_bus.MV_STATE,
                bytes(ins_bus.MV_END - ins_bus.MV_STATE)))
    if "a2f" in obj:                             # 2026-11-09: the A2 filter machines' pass (dnfw.a2f)
        from ..a2f import program as a2f_program
        code = obj["a2f"]
        assert a2f_program.STATE == A2F_STATE_DM and A2F_STATE_DM + 0x800 <= STATE_DM
        if A2F_L2_SPAN - len(code) < 64:
            raise DspError(f"a2f.asm ({len(code)} bytes) leaves fewer than 64 bytes of its L2 span")
        out.append(("a2f.asm (wr_a2f), in L2", A2F_L2_LOAD, code + bytes(A2F_L2_SPAN - len(code))))
    if ins_post._beat_built():                   # 2026-11-09: DRONE's BEAT side blocks (dnfw.mnm.drone)
        assert ins_post.SIDE_L2 + ins_post.SIDE_BYTES <= A2F_L2_LOAD
        out.append(("DRONE's BEAT side blocks: 16 slots x 36 words (zeros)", ins_post.SIDE_L2,
                    bytes(ins_post.SIDE_BYTES)))
    return out


def _mnm_scratch() -> bytes:
    """the Monomachine L2 scratch: zeros, but for ANALOG2's filter mix tables at its TABLES_OFF
    (2026-11-09; dnfw.mnm.analog2.ctx: nothing writes there at run time)"""
    raw = bytearray(MNM_SCRATCH_BYTES)
    from ..mnm import machines as _mm
    if "ANALOG2" in _mm.NAMES or "JUNO" in _mm.NAMES:        # 2026-11-12: JUNO's ladder reads them too
        from ..mnm import analog2 as A2
        from ..perc import program as _pp
        words = A2.table_words()
        assert A2.TABLES_OFF >= _pp.BOUNDS_OFF + 4 * 16 and A2.TABLES_OFF + 4 * len(words) <= MNM_SCRATCH_BYTES
        struct.pack_into(f"<{len(words)}f", raw, A2.TABLES_OFF, *words)
    return bytes(raw)


def _check_l2(stock: bytes, span_list) -> None:
    blocks = [b for b in bootstream.walk(stock).blocks if b.count]
    for what, at, payload in span_list:
        lo, hi = at, at + len(payload)
        if lo < L2_IMAGE_END + 0x10000 or hi > L2_NOCACHE - 0x10000:
            raise DspError(f"{what} at {lo:#x}..{hi:#x} is outside {L2_IMAGE_END + 0x10000:#x}.."
                           f"{L2_NOCACHE - 0x10000:#x} (64 KB clear of the stock image and the "
                           "non-cacheable window)")
        for b in blocks:
            if b.target < hi and lo < b.target + b.count:
                raise DspError(f"{what} overlaps the stock block at {b.target:#x}")
    for b in blocks:
        if 0x20000000 <= b.target < 0x20100000 and b.target + b.count > L2_IMAGE_END:
            raise DspError(f"the stock block at {b.target:#x} ends past L2_IMAGE_END")
    # 2026-11-12 (perc-layout): and ours clear of each other (PERC's three code spans sit between others' spans)
    ours = sorted((at, at + len(payload), what) for what, at, payload in span_list)
    for (_l0, h0, w0), (l1, _h1, w1) in zip(ours, ours[1:]):
        if l1 < h0:
            raise DspError(f"{w0} and {w1} overlap")


def _gran_tables() -> bytes:
    from ..grain import live as gran_live
    return gran_live.tables_bytes()[0]


def _check_ddr(stock: bytes, span_list) -> None:
    blocks = [b for b in bootstream.walk(stock).blocks if b.count]
    for what, at, payload in span_list:
        lo, hi = at, at + len(payload)
        if lo < DDR_FLOOR or hi > 0x88000000:
            raise DspError(f"{what} at {lo:#x} is outside {DDR_FLOOR:#x}..0x88000000")
        for b in blocks:
            if b.target < hi and lo < b.target + b.count:
                raise DspError(f"{what} overlaps the stock block at {b.target:#x}")
    ordered = sorted((at, at + len(p), w) for w, at, p in span_list)
    for (a0, a1, w0), (b0, b1, w1) in zip(ordered, ordered[1:]):
        if b0 < a1:
            raise DspError(f"{w0} and {w1} overlap")


def placements() -> list[dict]:
    out = [{"what": what, "load_address": f"{at:#010x}", "dm_byte": f"{at - LOAD_ALIAS:#08x}",
            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
           for what, at, payload in spans() + ddr_spans() + l2_spans()]
    obj = objects()
    out += [{"what": f"patch: entry JUMP {COUNT_SW:#x} (the block counter, then PERC) + NOP at sw 0x1c9448",
             "load_address": f"{sw_to_load(ENTRY_SW):#010x}",
             "bytes": len(obj["entry_jump"]) + len(NOP16),
             "stock": ENTRY_STOCK.hex(), "new": (obj["entry_jump"] + NOP16).hex()},
            {"what": f"patch: the machine lookup's base at sw {LOOKUP_SITE_SW:#x}, I5 = 0x25d748 -> "
                     f"{LOOKUP16_DM:#x} (16 types)",
             "load_address": f"{sw_to_load(LOOKUP_SITE_SW):#010x}", "bytes": 6,
             "stock": sharc_object.load_bytes(LOOKUP_SITE_STOCK).hex(), "new": obj["lookup_ptr"].hex()},
            {"what": f"patch: the idle loop's back edge at sw {IDLE_SITE_SW:#x} -> JUMP {IDLE_SW:#x}",
             "load_address": f"{l2_sw_to_load(IDLE_SITE_SW):#010x}", "bytes": len(obj["idle_jump"]),
             "stock": IDLE_SITE_STOCK.hex(), "new": obj["idle_jump"].hex()},
            {"what": f"patch: the driver's call of 0x1c9d3f at sw {PVMIX_SITE_SW:#x} -> JUMP {PVMIX_SW:#x} "
                     "(the recorder's preview, then the same call)",
             "load_address": f"{sw_to_load(PVMIX_SITE_SW):#010x}", "bytes": len(PVMIX_SITE_STOCK),
             "stock": PVMIX_SITE_STOCK.hex(), "new": (obj["pvmix_jump"] + PVMIX_SITE_STOCK[6:]).hex()},
            {"what": f"patch: the FX bus's CJUMP to the stock reverb at sw {REVERB_SITE_SW:#x} -> target {FDN8_SW:#x} "
                     "(FDN8, which JUMPs on to the stock reverb when TYPE asks for it)",
             "load_address": f"{sw_to_load(REVERB_SITE_SW):#010x}", "bytes": len(REVERB_SITE_STOCK),
             "stock": REVERB_SITE_STOCK.hex(), "new": reverb_cjump().hex()},
            {"what": f"patch: the FX bus's call of the stock delay at sw {DELAY_SITE_SW:#x} -> target {XDLY_SW:#x} "
                     "(XDLY, which JUMPs on to the stock delay when TYPE asks for it)",
             "load_address": f"{sw_to_load(DELAY_SITE_SW):#010x}", "bytes": len(DELAY_SITE_STOCK),
             "stock": DELAY_SITE_STOCK.hex(), "new": delay_call().hex()},
            {"what": f"patch: the FX bus's call of the stock chorus at sw {CHORUS_SITE_SW:#x} -> target {JSEND_SW:#x} "
                     "(the chorus send's JUNO, which JUMPs on to the stock chorus when TYPE asks for it)",
             "load_address": f"{sw_to_load(CHORUS_SITE_SW):#010x}", "bytes": len(CHORUS_SITE_STOCK),
             "stock": CHORUS_SITE_STOCK.hex(), "new": chorus_call().hex()},
            {"what": f"patch: the engine's call of the FX sends at sw {SENDS_SITE_SW:#x} -> target {POST_SW:#x} "
                     "(the post inserts, which JUMP on to the sends)",
             "load_address": f"{sw_to_load(SENDS_SITE_SW):#010x}", "bytes": len(SENDS_SITE_STOCK),
             "stock": SENDS_SITE_STOCK.hex(), "new": sends_cjump().hex()},
            {"what": f"patch: the routing after its per-track loop at sw {ROUTE_SITE_SW:#x} -> JUMP {INSBUS_SW:#x} "
                     f"(wr_inbus, which does the instruction it replaced and JUMPs back to {ROUTE_RESUME_SW:#x})",
             "load_address": f"{sw_to_load(ROUTE_SITE_SW):#010x}", "bytes": len(ROUTE_SITE_STOCK),
             "stock": ROUTE_SITE_STOCK.hex(), "new": obj["insbus_jump"].hex()}]
    return out


def _check_free(stock: bytes, span_list) -> None:
    blocks = [b for b in bootstream.walk(stock).blocks if b.count]
    for what, at, payload in span_list:
        lo, hi = at, at + len(payload)
        if not (dm_to_load(REGION[0]) <= lo and hi <= dm_to_load(REGION[1])):
            raise DspError(f"{what} at {lo:#x} leaves the block-1 region {REGION}")
        for b in blocks:
            if b.target < hi and lo < b.target + b.count:
                raise DspError(f"{what} at {lo:#x}+{len(payload):#x} overlaps the stock "
                               f"block at {b.target:#x}+{b.count:#x}")
    if not (STOCK_BLOCK1_END <= REGION[0] and REGION[1] <= DM_CACHE_16K - REGION_CACHE_GAP):
        raise DspError(f"the region {REGION} is not between block 1's last stock byte and 4 KB under the DM cache")
    ordered = sorted((at, at + len(p), w) for w, at, p in span_list)
    for (a0, a1, w0), (b0, b1, w1) in zip(ordered, ordered[1:]):
        if b0 < a1:
            raise DspError(f"{w0} and {w1} overlap")


IDLE_STATE_BYTES = 0x40                      # idle: saves, LAST, total, passes, BEFORE, AFTER; count: blocks, saves, MARK; MARK0


def idle_spans() -> list[tuple[str, int, bytes]]:
    """The idle stub's own blocks: its zeroed state, and its code padded to table 0."""
    code = objects()["idle_load"]
    end = COUNT_DM                           # block_count.asm follows (W5: tables are in DDR)
    if end - IDLE_DM - len(code) < 64:
        raise DspError("idle_load.asm leaves fewer than 64 bytes of NOP padding")
    return [("idle_load state (zeros)", dm_to_load(IDLE_STATE_DM), bytes(IDLE_STATE_BYTES)),
            ("idle_load.asm (wr_idle)", dm_to_load(IDLE_DM), code + bytes(end - IDLE_DM - len(code)))]


def _check_stock(stock: bytes) -> None:
    digest = hashlib.sha256(stock).hexdigest()
    if digest != STOCK_SHA256:
        raise DspError(f"section 7 sha256 {digest[:12]}... is not stock DN2 1.11's "
                       f"({STOCK_SHA256[:12]}...)")


def _check_idle_site(stock: bytes, obj: dict) -> None:
    if len(obj["idle_jump"]) != len(IDLE_SITE_STOCK):
        raise DspError(f"the idle JUMP is {len(obj['idle_jump'])} bytes, not {len(IDLE_SITE_STOCK)}")
    if bootstream.read_span(stock, l2_sw_to_load(IDLE_SITE_SW), len(IDLE_SITE_STOCK)) != IDLE_SITE_STOCK:
        raise DspError("sw 0xb88abb is not the stock idle loop's `jump (pc,-0x10)`")


# A run of zeros this long or longer inside a payload goes into the stream as a fill
# block (16 bytes, no payload) instead of as bytes. The stock stream does exactly this
# into the same L1 block (e.g. 36 bytes at 0x2dd328): the memory after boot is the
# same, byte for byte, and the stream is shorter -- the DSP upload budget is the
# stream's length (2026-10-14).
FILL_MIN = 64


def _blocks(at: int, payload: bytes) -> bytes:
    """`payload` at load address `at`, as payload blocks with every 4-aligned run of
    at least FILL_MIN zero bytes as a fill block."""
    out, i, n, start = [], 0, len(payload), 0
    while i < n:
        if i % 4 == 0 and payload[i] == 0:
            j = i
            while j < n and payload[j] == 0:
                j += 1
            k = i + ((j - i) // 4) * 4           # whole words only
            if k - i >= FILL_MIN:
                if start < i:
                    out.append(bootstream.block(at + start, payload[start:i]))
                out.append(bootstream.block(at + i, flags=bootstream.FLAG_FILL, count=k - i))
                start = i = k
                continue
            i = max(j, i + 1)
        else:
            i += 1
    if start < n:
        out.append(bootstream.block(at + start, payload[start:]))
    return b"".join(out)


# 2026-11-10 (shrink): stock's stream loads one 67,652 B table (int16, WaveTone's) twice, at L2
# TWIN_A and TWIN_B, byte for byte the same; both are read, neither is written (docs/dsp-room.md).
# The build loads A only and zero-fills B; entry_mark.asm copies A over B the first time the
# handler calls the per-block routine (TWIN_FLAG_DM == 0 as the state block loads), before any
# read: engine init, which runs earlier, touches neither (measured in the runner).
TWIN_A, TWIN_B, TWIN_BYTES = 0x2001E888, 0x200779F8, 67652
TWIN_FLAG_DM, TWIN_MAGIC = 0x2DE140, 0x54574E31                # entry_mark.asm's TWIN word, "TWN1"


def drop_twin(stream: bytes) -> bytes:
    """STREAM with the block at TWIN_B (the same bytes as TWIN_A's) turned into a fill block."""
    w = bootstream.walk(stream)
    a = [b for b in w.blocks if b.has_payload and b.target == TWIN_A and b.count == TWIN_BYTES]
    b = [x for x in w.blocks if x.has_payload and x.target == TWIN_B and x.count == TWIN_BYTES]
    if len(a) != 1 or len(b) != 1:
        raise DspError("the twin tables are not one block each at 0x2001e888 and 0x200779f8")
    pa = stream[a[0].payload_at:a[0].payload_at + TWIN_BYTES]
    pb = stream[b[0].payload_at:b[0].payload_at + TWIN_BYTES]
    if pa != pb:
        raise DspError("the twin tables differ: B cannot be copied from A")
    hb = b[0].offset                                             # its header
    fill = bootstream.block(TWIN_B, flags=bootstream.FLAG_FILL, count=TWIN_BYTES)
    return stream[:hb] + fill + stream[b[0].payload_at + TWIN_BYTES:]


def _finish(out: bytearray) -> bytes:
    result = bytes(out)
    walked = bootstream.walk(result)
    if not walked.complete or walked.stopped_at != len(result):
        raise DspError(f"the result does not walk as a boot stream ({walked.reason})")
    return result


# 2026-11-12 (the memory arbiter, after PERC's tan was given L1 0x2e4080 inside the bus FDN8 stores, inserts.bus.FD_L1,
# a run-time area no span showed: spans() pads each block to the next, so its zeros hid the stores): every area of ours
# the DSP touches, loaded or not, at its real extent. section7() refuses two that overlap; a sub-area (a named part of
# a container, e.g. the Monomachine L2 scratch's words) must lie inside its container and clear of its siblings.
def regions() -> list[tuple[str, int, int, str]]:
    """(what, lo, hi, container: "" for a top-level area) of every L1 / L2 / DDR area of ours, byte addresses"""
    from ..inserts import bus as ins_bus, design as ins_d
    from ..mnm import analog2 as A2, plk
    from ..perc import machines as PM, program as PP
    from ..sampler import machines as SM, program as SP
    mdc = _md_core()
    out: list[tuple[str, int, int, str]] = []

    def area(what, lo, n, container=""):
        out.append((what, lo, lo + n, container))
    # L1: the loaded blocks (a code object with the 64 B of NOPs its jumps may run into), then the run-time areas
    for what, at, payload in _raw_spans():
        area(what, at, len(payload) + (64 if "asm" in what else 0))
    area("SLICE / GRID relatch words (sampler.program.RELATCH)", SP.RELATCH, 16 * 16)
    if "SMP_LINE_DM" in globals():
        area("the sample reader's taps line (SMP_LINE_DM - 8)", SMP_LINE_DM - 8, 0x2E0100 - (SMP_LINE_DM - 8))
    area("the bus FDN8 instances' stores (inserts.bus.FD_L1)", ins_bus.FD_L1, ins_d.FDN8_INSTANCES * ins_bus.FD_L1_BYTES)
    area("the Monomachine render scratch", MNM_RENDER_DM, MNM_RENDER_BYTES)
    # L2: the loaded code and state, then the run-time areas
    for what, at, payload in l2_spans():
        area(what, at, len(payload))
    area("the bus inserts' scratch and stores (inserts.bus HEAD_END..MV_STATE)", ins_bus.HEAD_END,
         ins_bus.MV_STATE - ins_bus.HEAD_END)
    scr = "Monomachine scratch and the voice order, in L2 (zeros; v0.32; ANALOG2's mix tables)"
    scr = next((w for w, _a, _p in l2_spans() if w.startswith("Monomachine scratch")), scr)
    mnm = MNM_SCRATCH_L2
    words = [("the budget sums (CUM_OFF)", getattr(PP, "CUM_OFF", None), 64), ("the keys", PP.MNM_KEYS_OFF, 64),
             ("the costs", PP.MNM_COSTS_OFF, 64), ("the voice order", PP.ORDER_OFF, 0x50),
             ("the rests", PP.RESTS_OFF, 64), ("the strikes", PP.STRIKES_OFF, 64), ("the bounds", PP.BOUNDS_OFF, 64),
             ("the slot counter", PP.SLOT_N, 4), ("ANALOG 2's mix tables", A2.TABLES_OFF, 4 * len(A2.table_words())),
             ("the velocities (VEL_OFF)", getattr(PP, "VEL_OFF", None), 64)]
    for what, off, n in words:
        if off is not None:
            area(what, mnm + off, n, scr)
    # DDR: the loaded spans (the pool's header lies inside the pool: its sub-area), then the run-time areas
    pool = "the sample pool"
    for what, at, payload in ddr_spans():
        area(what, at, len(payload), pool if SMP_POOL_DDR <= at < SMP_POOL_DDR + SM.POOL_BYTES else "")
    area("the link's shipped tables (perc.machines.shipped_tail)", MD_TABLES_DDR + mdc.TABLE_LAYOUT["_end"][0],
         len(PM.shipped_tail()))
    if _dpro_on():
        from ..mnm import core as MNC
        area("DDRW's and DENS's Digibank stand-in", MD_TABLES_DDR + mdc.TABLE_LAYOUT["mnm"][0] + MNC.DIGI_OFF,
             4 * MNC.DIGI_WORDS)
    area("the moved inserts' rings (MV_RING_DDR)", ins_d.MV_RING_DDR, ins_d.MV_INSTANCES * 2048)
    area("PLAITS' big buffers (plk.BIG_DDR)", plk.BIG_DDR, 16 * plk.BIG_STRIDE)
    area("the bus FDN8 instances' rings", ins_d.FDN8_RING_DDR, ins_d.FDN8_INSTANCES * ins_d.FDN8_RING_STRIDE)
    area("the bus XDLY instances' lines", ins_d.XDLY_LINES_DDR, ins_d.XDLY_INSTANCES * ins_d.XDLY_LINES_STRIDE)
    area(pool, SMP_POOL_DDR, SM.POOL_BYTES)
    return out


def check_regions() -> None:
    """refuse two areas of ours that overlap (regions()), by real extent"""
    reg = regions()
    tops = sorted((lo, hi, w) for w, lo, hi, c in reg if not c)
    for (a0, a1, w0), (b0, b1, w1) in zip(tops, tops[1:]):
        if b0 < a1:
            raise DspError(f"{w0} ({a0:#x}..{a1:#x}) and {w1} ({b0:#x}..{b1:#x}) overlap")
    for cont in {c for *_r, c in reg if c}:
        box = [(lo, hi) for w, lo, hi, c in reg if w == cont and not c]
        if not box:
            raise DspError(f"{cont}: no such area for its sub-areas")
        kids = sorted((lo, hi, w) for w, lo, hi, c in reg if c == cont)
        for lo, hi, w in kids:
            if not (box[0][0] <= lo and hi <= box[0][1]):
                raise DspError(f"{w} ({lo:#x}..{hi:#x}) leaves {cont}")
        for (a0, a1, w0), (b0, b1, w1) in zip(kids, kids[1:]):
            if b0 < a1:
                raise DspError(f"{w0} ({a0:#x}..{a1:#x}) and {w1} ({b0:#x}..{b1:#x}) overlap in {cont}")


def section7_idle_only(stock: bytes) -> bytes:
    """Stock DN2 1.11's section 7 plus the idle-time stub and nothing else: the stock
    engine, measured. Refuses anything but stock."""
    _check_stock(stock)
    obj = objects()
    _check_idle_site(stock, obj)
    added = idle_spans()
    _check_free(stock, added)
    out = bytearray(bootstream.insert_before_final(
        stock, b"".join(bootstream.block(at, payload) for _, at, payload in added)))
    bootstream.write_span(out, l2_sw_to_load(IDLE_SITE_SW), obj["idle_jump"])
    return _finish(out)


def section7(stock: bytes) -> bytes:
    """DN2 1.11's section 7 -> the mod's. Refuses anything else."""
    digest = hashlib.sha256(stock).hexdigest()
    if digest != STOCK_SHA256:
        raise DspError(f"section 7 sha256 {digest[:12]}... is not stock DN2 1.11's "
                       f"({STOCK_SHA256[:12]}...)")
    obj = objects()
    entry = obj["entry_jump"] + NOP16
    if len(entry) != len(ENTRY_STOCK):
        raise DspError(f"the entry patch is {len(entry)} bytes, not {len(ENTRY_STOCK)}")
    if bootstream.read_span(stock, sw_to_load(ENTRY_SW), len(ENTRY_STOCK)) != ENTRY_STOCK:
        raise DspError("sw 0x1c9448 is not the stock `i5=dm(-0x18,i6); r10=dm(-0x22,i6)`")
    if len(obj["idle_jump"]) != len(IDLE_SITE_STOCK):
        raise DspError(f"the idle JUMP is {len(obj['idle_jump'])} bytes, not {len(IDLE_SITE_STOCK)}")
    if bootstream.read_span(stock, l2_sw_to_load(IDLE_SITE_SW), len(IDLE_SITE_STOCK)) != IDLE_SITE_STOCK:
        raise DspError("sw 0xb88abb is not the stock idle loop's `jump (pc,-0x10)`")
    if bootstream.read_span(stock, sw_to_load(CALL_SITE_SW), len(CALL_SITE_STOCK)) != CALL_SITE_STOCK:
        raise DspError("sw 0x1c9fb9 is not the stock `r4 = 0x268438`")
    if bootstream.read_span(stock, sw_to_load(PVMIX_SITE_SW), len(PVMIX_SITE_STOCK)) != PVMIX_SITE_STOCK:
        raise DspError("sw 0x1c9fd2 is not the stock `CJUMP 0x1c9d3f (DB)` and its two pushes")
    if len(obj["pvmix_jump"]) != 6:
        raise DspError("the preview's JUMP is not one 48-bit instruction")
    if bootstream.read_span(stock, sw_to_load(REVERB_SITE_SW), len(REVERB_SITE_STOCK)) != REVERB_SITE_STOCK:
        raise DspError("sw 0x1c1d11 is not the stock `CJUMP 0xb836bc (DB)`")
    if bootstream.read_span(stock, sw_to_load(DELAY_SITE_SW), len(DELAY_SITE_STOCK)) != DELAY_SITE_STOCK:
        raise DspError("sw 0x1c1c58 is not the stock `CALL 0xb8482c (DB)`")
    if bootstream.read_span(stock, sw_to_load(CHORUS_SITE_SW), len(CHORUS_SITE_STOCK)) != CHORUS_SITE_STOCK:
        raise DspError("sw 0x1c1be1 is not the stock `CALL 0xb84d5c (DB)`")
    if bootstream.read_span(stock, sw_to_load(SENDS_SITE_SW), len(SENDS_SITE_STOCK)) != SENDS_SITE_STOCK:
        raise DspError("sw 0x1c3054 is not the stock `CJUMP 0x1c1738 (DB)`")
    if bootstream.read_span(stock, sw_to_load(ROUTE_SITE_SW), len(ROUTE_SITE_STOCK)) != ROUTE_SITE_STOCK:
        raise DspError("sw 0x1c1fef is not the stock `R2 = DM(0x257980)`")
    if len(obj["insbus_jump"]) != len(ROUTE_SITE_STOCK):
        raise DspError(f"the bus pass's JUMP is {len(obj['insbus_jump'])} bytes, not {len(ROUTE_SITE_STOCK)}")
    if len(obj["emark_jump"]) != len(CALL_SITE_STOCK):
        raise DspError(f"the entry-mark JUMP is {len(obj['emark_jump'])} bytes, not {len(CALL_SITE_STOCK)}")
    lookup = struct.unpack("<8I", bootstream.read_span(stock, dm_to_load(LOOKUP_DM), 32))
    if lookup != LOOKUP_STOCK:
        raise DspError(f"the machine lookup is {lookup}, not stock {LOOKUP_STOCK}")
    if bootstream.read_span(stock, sw_to_load(LOOKUP_SITE_SW), 6) != sharc_object.load_bytes(LOOKUP_SITE_STOCK):
        raise DspError("sw 0x1c2958 is not the stock `I5 = 0x25d748`")
    if len(obj["lookup_ptr"]) != 6:
        raise DspError("the lookup pointer patch is not one 48-bit instruction")
    added = spans()
    _check_free(stock, added)
    ddr = ddr_spans()
    _check_ddr(stock, ddr)
    l2 = l2_spans()
    _check_l2(stock, l2)
    check_regions()

    out = bytearray(bootstream.insert_before_final(
        stock, b"".join(_blocks(at, payload) for _, at, payload in added + ddr + l2)))
    bootstream.write_span(out, sw_to_load(ENTRY_SW), entry)
    bootstream.write_span(out, sw_to_load(LOOKUP_SITE_SW), obj["lookup_ptr"])
    bootstream.write_span(out, l2_sw_to_load(IDLE_SITE_SW), obj["idle_jump"])
    bootstream.write_span(out, sw_to_load(CALL_SITE_SW), obj["emark_jump"])
    bootstream.write_span(out, sw_to_load(PVMIX_SITE_SW), obj["pvmix_jump"])
    bootstream.write_span(out, sw_to_load(REVERB_SITE_SW), reverb_cjump())
    bootstream.write_span(out, sw_to_load(DELAY_SITE_SW), delay_call())
    bootstream.write_span(out, sw_to_load(SENDS_SITE_SW), sends_cjump())
    bootstream.write_span(out, sw_to_load(CHORUS_SITE_SW), chorus_call())
    bootstream.write_span(out, sw_to_load(ROUTE_SITE_SW), obj["insbus_jump"])
    result = drop_twin(bytes(out))            # 2026-11-10: entry_mark.asm copies A over B
    walked = bootstream.walk(result)
    if not walked.complete or walked.stopped_at != len(result):
        raise DspError(f"the result does not walk as a boot stream ({walked.reason})")
    return result
