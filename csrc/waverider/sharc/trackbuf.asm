// trackbuf.asm -- the stock engine's 16 mono track buffers, from DDR to L1 (stock-hotspots item 2).
//
// Our own code, assembled with selache's `selas` (GPL-3.0, used as a tool and never linked in).
//
// The stock engine renders and filters every track through a 128-byte buffer of 32 floats. The 16
// buffers sit in DDR (0x804acf90 + 0x80 t) and the voice chain touches each word about 19 times a
// block: 9,745 of the idle block's 9,857 voice-dispatch DDR accesses (docs/stock-hotspots.md). Two
// tables hold their addresses and nothing else does (scanned in L1 and L2 after init and after two
// blocks, 32 words): DM 0x254a60 + 4 t, and a copy at 0x257ea8 + 0x10 (t / 2) + 4 (t % 2). This
// copies the 512 words to the same layout in L1 (0x2e1d00, the 2 KB that PING's state held until it was
// removed, zero-filled in the stream) and writes the 32 addresses.
//
// It runs once, from entry_mark.asm's first pass (TWIN still 0), before the per-block routine's first
// call, so engine init has made the tables and the buffers hold what init left. Same data, same
// order, a different memory: every output of the engine is the same word for word
// (scripts/prof_stock_relocate.py). It uses R9, R10, I0 and I1, which entry_mark.asm has saved, and
// jumps back into it (wr_emark's restore of I0 and I1).
//
// PLACEMENT IS FIXED: this code loads at PM sw 0x170800 (L1 block 1, byte 0x2e1000).

.SECTION/PM seg_pmco;

.GLOBAL wr_trackbuf.;
wr_trackbuf.:
      R9 = 0x804ace90;                  // the extra block and the buffers in DDR
      I0 = R9;
      R9 = 0x2e1c00;                    // and in L1
      I1 = R9;
      R10 = 0x240;                      // 576 words
.GLOBAL wr_trackbuf_copy.;
wr_trackbuf_copy.:
      R9 = DM(I0, M6);
      DM(I1, M6) = R9;
      R10 = R10 - 1;
      IF NE JUMP 0x17080c;                   // -> wr_trackbuf_copy.
      R9 = 0x2e1d00;
      DM(0x254a60) = R9;
      DM(0x257ea8) = R9;
      R9 = 0x2e1d80;
      DM(0x254a64) = R9;
      DM(0x257eac) = R9;
      R9 = 0x2e1e00;
      DM(0x254a68) = R9;
      DM(0x257eb8) = R9;
      R9 = 0x2e1e80;
      DM(0x254a6c) = R9;
      DM(0x257ebc) = R9;
      R9 = 0x2e1f00;
      DM(0x254a70) = R9;
      DM(0x257ec8) = R9;
      R9 = 0x2e1f80;
      DM(0x254a74) = R9;
      DM(0x257ecc) = R9;
      R9 = 0x2e2000;
      DM(0x254a78) = R9;
      DM(0x257ed8) = R9;
      R9 = 0x2e2080;
      DM(0x254a7c) = R9;
      DM(0x257edc) = R9;
      R9 = 0x2e2100;
      DM(0x254a80) = R9;
      DM(0x257ee8) = R9;
      R9 = 0x2e2180;
      DM(0x254a84) = R9;
      DM(0x257eec) = R9;
      R9 = 0x2e2200;
      DM(0x254a88) = R9;
      DM(0x257ef8) = R9;
      R9 = 0x2e2280;
      DM(0x254a8c) = R9;
      DM(0x257efc) = R9;
      R9 = 0x2e2300;
      DM(0x254a90) = R9;
      DM(0x257f08) = R9;
      R9 = 0x2e2380;
      DM(0x254a94) = R9;
      DM(0x257f0c) = R9;
      R9 = 0x2e2400;
      DM(0x254a98) = R9;
      DM(0x257f18) = R9;
      R9 = 0x2e2480;
      DM(0x254a9c) = R9;
      DM(0x257f1c) = R9;
      R9 = 0x2e1c00;
      DM(0x254aa0) = R9;                // the 17th pointer: the extra block
      JUMP 0x16f6b1;                    // wr_emark's restore of I0 and I1
.wr_trackbuf..end:
