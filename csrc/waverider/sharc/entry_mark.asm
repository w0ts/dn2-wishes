// entry_mark.asm -- EMUCLK as the per-frame handler calls the per-block routine.
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never
// linked in).
//
// The handler calls the per-block routine sw 0x1c2712 from sw 0x1c9fbc (`cjump 0x1c2712
// (db)`), after loading its first argument at sw 0x1c9fb9: `r4 = 0x268438`. The build
// replaces that one 48-bit load with `JUMP 0x16f680`; this stores EMUCLK as MARK0,
// performs the load it displaced, and jumps back to the cjump. idle_load.asm splits each
// busy stretch at MARK0 (the handler, and whatever it waits on, before the call) and at
// block_count.asm's MARK (the machine dispatch's splice).
//
// 2026-11-10 (shrink, the twin tables): stock's stream loads the same 67,652 B of int16
// tables twice, at L2 0x2001e888 (A) and 0x200779f8 (B); both are read (WaveTone's
// oscillator), neither is ever written (dn2mk2 docs/dsp-room.md). The build ships A only
// and zero-fills B; the first time through here (TWIN still 0, as the state block
// loads), this copies A over B, 16,913 words, before the per-block routine's first call:
// engine init, which runs before, never touches either (measured in the runner). TWIN is
// then TWIN_MAGIC and the copy never runs again.
//
// It uses R9, R10, I0 and I1, each saved to its own word: R4, R8 and R12 are the call's
// arguments.
//
// PLACEMENT IS FIXED: this code loads at PM sw 0x16f680 (L1 block 1, byte 0x2ded00).
//
// DM (byte addresses, in the state block the build zero-fills):
//   0x2de138  save: R9
//   0x2de13c  MARK0
//   0x2de140  TWIN: 0, then TWIN_MAGIC once B holds A's words
//   0x2de144  save: R10
//   0x2de148  save: I0
//   0x2de14c  save: I1
//
// 2026-11-10 (stock-hotspots item 2): on that same first pass, after the twin copy, a JUMP to
// trackbuf.asm (sw 0x170800), which moves the stock engine's 16 track buffers from DDR to L1 and
// jumps back to the restore of I0 and I1 (sw 0x16f6b1).

.SECTION/PM seg_pmco;

.GLOBAL wr_emark.;
wr_emark.:
      DM(0x2de138) = R9;
      R9 = DM(0x2de140);
      DM(0x2de144) = R10;
      R10 = 0x54574e31;                 // TWIN_MAGIC ("TWN1")
      COMP(R9, R10);
      IF EQ JUMP 0x16f6b7;                   // -> wr_emark_done.
      DM(0x2de148) = I0;
      DM(0x2de14c) = I1;
      R9 = 0x2001e888;                  // A
      I0 = R9;
      R9 = 0x200779f8;                  // B
      I1 = R9;
      R10 = 0x4211;                     // 16,913 words
.GLOBAL wr_emark_copy.;
wr_emark_copy.:
      R9 = DM(I0, M6);
      DM(I1, M6) = R9;
      R10 = R10 - 1;
      IF NE JUMP 0x16f6a2;                   // -> wr_emark_copy.
      R10 = 0x54574e31;
      DM(0x2de140) = R10;               // TWIN
      JUMP 0x170800;                    // trackbuf.asm: the track buffers to L1; it returns to the restore below
      I0 = DM(0x2de148);
      I1 = DM(0x2de14c);
.GLOBAL wr_emark_done.;
wr_emark_done.:
      R10 = DM(0x2de144);
      R9 = EMUCLK;
      DM(0x2de13c) = R9;                // MARK0
      R9 = DM(0x2de138);
      R4 = 0x268438;                    // the displaced load
      JUMP 0x1c9fbc;                    // back to the call
.wr_emark..end:
