// insbus.asm -- the bus inserts FDN8 and XDLY per track (docs/inserts.md). GENERATED
// by scripts/gen_inserts_asm.py from dnfw.inserts.bus; do not edit by hand.

.SECTION/PM seg_pmco;

.GLOBAL wr_inbus.;
wr_inbus.:
      DM(0x2e5744) = R0;
      DM(0x2e5748) = R1;
      DM(0x2e574c) = R2;
      DM(0x2e5750) = R3;
      DM(0x2e5754) = R4;
      DM(0x2e5758) = R5;
      DM(0x2e575c) = R6;
      DM(0x2e5760) = R7;
      DM(0x2e5764) = R8;
      DM(0x2e5768) = R9;
      DM(0x2e576c) = R10;
      DM(0x2e5770) = R11;
      DM(0x2e5774) = R12;
      DM(0x2e5778) = R13;
      DM(0x2e577c) = R14;
      DM(0x2e5780) = R15;
      DM(0x2e5784) = I0;
      DM(0x2e5788) = I1;
      DM(0x2e578c) = I2;
      DM(0x2e5790) = I3;
      DM(0x2e5794) = I4;
      DM(0x2e5798) = I12;
      DM(0x2e579c) = ASTAT;
      R8 = EMUCLK;                      // the inserts' time: this pass from here
      DM(0x2de0f0) = R8;
      R9 = DM(0x2de028);
      R8 = R8 - R9;                     // since our voices ..
      R9 = DM(0x2de0ec);
      R8 = R8 - R9;                     // .. the stock's time done before this pass
      R9 = DM(0x2ddff8);
      R8 = R8 + R9;
      R9 = DM(0x2de01c);
      R8 = MIN(R8, R9);
      R9 = DM(0x2ddff8);
      R8 = R8 - R9;                     // held to TAIL - REST_OUT: the output stage is always to come
      R9 = 0x0;
      R8 = MAX(R8, R9);
      R9 = DM(0x2de0e8);
      R9 = PASS R9;
      IF EQ JUMP 0xbde06b;                   // -> wr_ib_isz_1.
      R9 = R9 + R8;                     // no longer to come
.GLOBAL wr_ib_isz_1.;
wr_ib_isz_1.:
      DM(0x2ddff0) = R9;
      R9 = PASS R9;
      IF EQ JUMP 0xbde082;                   // -> wr_ib_irz_2.
      R8 = EMUCLK;
      R8 = R9 - R8;                     // the room before this pass's deadline ..
      R9 = DM(0x2de13c);
      R8 = R8 + R9;                     // .. from here, in the frame
      R9 = DM(0x2e174c);
      R8 = MIN(R8, R9);
      DM(0x2e174c) = R8;
.GLOBAL wr_ib_irz_2.;
wr_ib_irz_2.:
      R0 = DM(0x200bd1e0);
      R0 = R0 - 1;
      DM(0x200bd1e0) = R0;
      R0 = DM(0x2e3a0c);
      R0 = PASS R0;
      IF EQ JUMP 0xbde7ea;                   // -> wr_ib_else_3.
      R0 = 0x0;
      DM(0x2e54c0) = R0;
      R0 = 0x2e54d0;
      DM(0x2e54c4) = R0;
      R0 = 0x0;
      DM(0x2e54c8) = R0;
      R0 = 0x2e54d8;
      DM(0x2e54cc) = R0;
      R0 = 0x2e54e0;
      DM(0x2e54d0) = R0;
      R0 = 0x2e5560;
      DM(0x2e54d4) = R0;
      R0 = 0x2e55e0;
      DM(0x2e54d8) = R0;
      R0 = 0x2e5660;
      DM(0x2e54dc) = R0;
      R0 = 0x0;
      DM(0x2e5718) = R0;
      DM(0x2e571c) = R0;
      DM(0x2e5700) = R0;
      R0 = 0x20;
      DM(0x2e3474) = R0;
.GLOBAL wr_ib_trk_4.;
wr_ib_trk_4.:
      R0 = DM(0x2e5700);
      R1 = LSHIFT R0 BY -1;
      DM(0x2e5704) = R1;
      R0 = DM(0x2e5700);
      R1 = LSHIFT R0 BY 5;
      R12 = 0x2e3600;
      R2 = R12 + R1;
      DM(0x2e570c) = R2;
      I4 = R2;
      R3 = DM(0, I4);
      R12 = 0xf;
      R5 = R3 AND R12;
      DM(0x2e5710) = R5;
      R3 = LSHIFT R3 BY -4;
      DM(0x2e5714) = R3;
      R0 = 0x0;
      DM(0x2e5740) = R0;
      R5 = DM(0x2e5710);
      R6 = 0x7;
      R7 = 0x8;
      COMP(R5, R6);
      IF NE JUMP 0xbde125;                   // -> wr_ib_else_5.
      R3 = DM(0x2e5714);
      R12 = 0x8;
      COMP(R3, R12);
      IF GE JUMP 0xbde122;                   // -> wr_ib_else_6.
      R0 = 0x1;
      DM(0x2e5740) = R0;
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 4;
      R12 = 0x200bde00;
      R1 = R12 + R0;
      DM(0x2e5738) = R1;
.GLOBAL wr_ib_else_6.;
wr_ib_else_6.:
      JUMP 0xbde14f;                         // -> wr_ib_fi_7.
.GLOBAL wr_ib_else_5.;
wr_ib_else_5.:
      R5 = DM(0x2e5710);
      R7 = 0x8;
      COMP(R5, R7);
      IF NE JUMP 0xbde14f;                   // -> wr_ib_else_8.
      R3 = DM(0x2e5714);
      R12 = 0x4;
      COMP(R3, R12);
      IF GE JUMP 0xbde14f;                   // -> wr_ib_else_9.
      R1 = 0x4a9c;
      DM(0x2e5734) = R1;
      R0 = 0x2;
      DM(0x2e5740) = R0;
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 4;
      R12 = 0x200bde80;
      R1 = R12 + R0;
      DM(0x2e5738) = R1;
.GLOBAL wr_ib_else_9.;
wr_ib_else_9.:
.GLOBAL wr_ib_else_8.;
wr_ib_else_8.:
.GLOBAL wr_ib_fi_7.;
wr_ib_fi_7.:
      R0 = DM(0x2e5740);
      R0 = PASS R0;
      IF EQ JUMP 0xbde5fe;                   // -> wr_ib_else_10.
      R0 = DM(0x2e5738);
      I4 = R0;
      R3 = DM(2, I4);
      R0 = LSHIFT R0 BY -2;
      R12 = 0x1808da30;
      R0 = R12 + R0;
      I4 = R0;
      R1 = DM(0x200bd1e0);
      R2 = DM(0, I4);
      DM(0, I4) = R1;
      R2 = R2 - 1;
      COMP(R2, R1);
      IF EQ JUMP 0xbde175;                   // -> wr_ib_else_11.
      R3 = 0x1;
.GLOBAL wr_ib_else_11.;
wr_ib_else_11.:
      R3 = PASS R3;
      IF EQ JUMP 0xbde17d;                   // -> wr_ib_else_12.
      R0 = 0x0;
      DM(-12, I4) = R0;
.GLOBAL wr_ib_else_12.;
wr_ib_else_12.:
      R0 = DM(0x2e5740);
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbde1cf;                   // -> wr_ib_else_13.
      R0 = DM(0x2e5714);
      R12 = 0x184;
      R0 = R0 * R12 (SSI);
      R12 = 0x2e4050;
      R0 = R12 + R0;
      DM(0x2e5720) = R0;
      R2 = DM(0x2e5720);
      I4 = R2;
      R0 = DM(2, I4);
      R1 = 0x4844;
      R0 = PASS R0;
      IF EQ JUMP 0xbde1a5;                   // -> wr_ib_else_14.
      R1 = 0x101d0;
.GLOBAL wr_ib_else_14.;
wr_ib_else_14.:
      DM(0x2e5734) = R1;
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 2;
      R12 = 0x200bd180;
      R0 = R12 + R0;
      I4 = R0;
      R8 = DM(0x2e5700);
      R12 = 0x1;
      R1 = R8 + R12;
      R2 = DM(0x2e5710);
      R2 = LSHIFT R2 BY 8;
      R1 = R1 OR R2;
      R3 = DM(0, I4);
      COMP(R1, R3);
      IF EQ JUMP 0xbde1cf;                   // -> wr_ib_else_15.
      R1 = 0x101d0;
      DM(0x2e5734) = R1;
.GLOBAL wr_ib_else_15.;
wr_ib_else_15.:
.GLOBAL wr_ib_else_13.;
wr_ib_else_13.:
      R0 = DM(0x2e5704);
      R1 = LSHIFT R0 BY 8;
      R12 = 0x258f68;
      R1 = R12 + R1;
      DM(0x2e5724) = R1;
      R12 = 0x80;
      R1 = R12 + R1;
      DM(0x2e5728) = R1;
      R9 = 0x1;
      R10 = DM(0x2ddff0);
      R10 = PASS R10;
      IF EQ JUMP 0xbde1ff;                   // -> wr_ib_else_16.
      R8 = EMUCLK;
      R9 = DM(0x2de13c);
      R8 = R8 - R9;
      R9 = DM(0x2e5734);
      R8 = R8 + R9;
      R9 = 0x1;
      COMP(R8, R10);
      IF LE JUMP 0xbde1ff;                   // -> wr_ib_else_17.
      R9 = 0x0;
.GLOBAL wr_ib_else_17.;
wr_ib_else_17.:
.GLOBAL wr_ib_else_16.;
wr_ib_else_16.:
      R2 = DM(0x2e5738);
      I4 = R2;
      R3 = DM(2, I4);
      R9 = PASS R9;
      IF EQ JUMP 0xbde220;                   // -> wr_ib_else_18.
      R0 = 0x0;
      R3 = PASS R3;
      IF EQ JUMP 0xbde21d;                   // -> wr_ib_else_19.
      R12 = 0x1;
      R3 = R3 - R12;
      DM(2, I4) = R3;
      R0 = 0x3;
      R3 = PASS R3;
      IF NE JUMP 0xbde21d;                   // -> wr_ib_else_20.
      R0 = 0x1;
.GLOBAL wr_ib_else_20.;
wr_ib_else_20.:
.GLOBAL wr_ib_else_19.;
wr_ib_else_19.:
      JUMP 0xbde23a;                         // -> wr_ib_fi_21.
.GLOBAL wr_ib_else_18.;
wr_ib_else_18.:
      R0 = 0x3;
      R3 = PASS R3;
      IF NE JUMP 0xbde236;                   // -> wr_ib_else_22.
      R0 = 0x2;
      R1 = DM(0x2de010);
      R1 = LSHIFT R1 BY -4;
      R1 = R10 + R1;
      COMP(R8, R1);
      IF GT JUMP 0xbde236;                   // -> wr_ib_else_23.
      R0 = 0x4;
.GLOBAL wr_ib_else_23.;
wr_ib_else_23.:
.GLOBAL wr_ib_else_22.;
wr_ib_else_22.:
      R3 = 0x40;
      DM(2, I4) = R3;
.GLOBAL wr_ib_fi_21.;
wr_ib_fi_21.:
      DM(0x2e573c) = R0;
      R1 = 0x2;
      COMP(R0, R1);
      IF LT JUMP 0xbde274;                   // -> wr_ib_else_24.
      R8 = DM(0x2de0f4);
      R9 = 0x1;
      R8 = R8 + R9;
      DM(0x2de0f4) = R8;
      R1 = 0xe;
      R2 = 0x2;
      COMP(R0, R2);
      IF NE JUMP 0xbde257;                   // -> wr_ib_else_25.
      R1 = DM(0x2e5710);
.GLOBAL wr_ib_else_25.;
wr_ib_else_25.:
      R2 = 0x4;
      COMP(R0, R2);
      IF NE JUMP 0xbde25f;                   // -> wr_ib_else_26.
      R1 = 0xf;
.GLOBAL wr_ib_else_26.;
wr_ib_else_26.:
      R12 = 0xf;
      R9 = R1 AND R12;
      R9 = LSHIFT R9 BY 2;
      R12 = 0x2e1700;
      R9 = R12 + R9;
      I4 = R9;
      R8 = DM(0, I4);
      R12 = 0x1;
      R8 = R8 + R12;
      DM(0, I4) = R8;
.GLOBAL wr_ib_else_24.;
wr_ib_else_24.:
      R0 = DM(0x2e573c);
      R1 = 0x4;
      COMP(R0, R1);
      IF NE JUMP 0xbde27f;                   // -> wr_ib_else_27.
      R0 = 0x0;
.GLOBAL wr_ib_else_27.;
wr_ib_else_27.:
      R1 = 0x2;
      COMP(R0, R1);
      IF GE JUMP 0xbde5fe;                   // -> wr_ib_else_28.
      R0 = DM(0x2e5740);
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbde407;                   // -> wr_ib_else_29.
      R0 = DM(0x2e5718);
      R0 = PASS R0;
      IF NE JUMP 0xbde2d8;                   // -> wr_ib_else_30.
      R0 = 0x2e6400;
      I0 = R0;
      R0 = 0x2e57a0;
      I1 = R0;
      R11 = 0xc;
      R12 = 0xbde2a8;                        // return address - 1: wr_ib_ret_31. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_31.;
wr_ib_ret_31.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = 0x2e672c;
      I0 = R0;
      R0 = 0x2e5924;
      I1 = R0;
      R11 = 0x8;
      R12 = 0xbde2be;                        // return address - 1: wr_ib_ret_32. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_32.;
wr_ib_ret_32.:
      R0 = 0x2e6a2c;
      I0 = R0;
      R0 = 0x2e672c;
      I1 = R0;
      R11 = 0x8;
      R12 = 0xbde2d2;                        // return address - 1: wr_ib_ret_33. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_33.;
wr_ib_ret_33.:
      R0 = 0x1;
      DM(0x2e5718) = R0;
.GLOBAL wr_ib_else_30.;
wr_ib_else_30.:
      R0 = DM(0x2e5714);
      R12 = 0x184;
      R0 = R0 * R12 (SSI);
      R12 = 0x2e4050;
      R0 = R12 + R0;
      DM(0x2e5720) = R0;
      R0 = DM(0x2e5720);
      I0 = R0;
      R0 = 0x2e6400;
      I1 = R0;
      R11 = 0xc;
      R12 = 0xbde2fa;                        // return address - 1: wr_ib_ret_34. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_34.;
wr_ib_ret_34.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 2;
      R12 = 0x200bd180;
      R0 = R12 + R0;
      I4 = R0;
      R8 = DM(0x2e5700);
      R12 = 0x1;
      R1 = R8 + R12;
      R2 = DM(0x2e5710);
      R2 = LSHIFT R2 BY 8;
      R1 = R1 OR R2;
      R3 = DM(0, I4);
      COMP(R1, R3);
      IF EQ JUMP 0xbde36b;                   // -> wr_ib_else_35.
      DM(0, I4) = R1;
      R0 = 0x2e6400;
      I0 = R0;
      R0 = 0x0;
      R11 = 0x61;
.GLOBAL wr_ib_loop_36.;
wr_ib_loop_36.:
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde329;                   // -> wr_ib_loop_36.
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 19;
      R12 = -0x7d800000;
      R0 = R12 + R0;
      DM(0x2e6400) = R0;
      R0 = 0x0;
      DM(0x2e6440) = R0;
      R0 = -0x61c88647;
      DM(0x2e6444) = R0;
      R0 = 0x3c6ef372;
      DM(0x2e6448) = R0;
      R0 = -0x255992d5;
      DM(0x2e644c) = R0;
      R0 = 0x78dde6e4;
      DM(0x2e6450) = R0;
      R0 = 0x1715609d;
      DM(0x2e6454) = R0;
      R0 = -0x4ab325aa;
      DM(0x2e6458) = R0;
      R0 = 0x5384540f;
      DM(0x2e645c) = R0;
.GLOBAL wr_ib_else_35.;
wr_ib_else_35.:
      R2 = DM(0x2e570c);
      I4 = R2;
      R8 = DM(2, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56e0) = R8;
      R8 = DM(3, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56e4) = R8;
      R8 = DM(4, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56e8) = R8;
      R8 = DM(5, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56ec) = R8;
      R8 = DM(6, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56f0) = R8;
      R8 = DM(7, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56f4) = R8;
      R8 = DM(1, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e572c) = R8;
      R0 = 0x2e56e0;
      DM(0x2e6594) = R0;
      R0 = 0x2e54c0;
      DM(0x2e6590) = R0;
      R0 = 0x1;
      DM(0x2e6584) = R0;
      R0 = DM(0x2e5724);
      DM(0x2e54d0) = R0;
      R0 = DM(0x2e5728);
      DM(0x2e54d4) = R0;
      R12 = 0xbde3e1;                        // return address - 1: wr_ib_eret_37. - 1
      I12 = R12;
      JUMP 0xbd5000;                    // the engine, MODE 1 (it returns with JUMP (M14, I12))
.GLOBAL wr_ib_eret_37.;
wr_ib_eret_37.:
      R0 = 0x2e54e0;
      DM(0x2e54d0) = R0;
      R0 = 0x2e5560;
      DM(0x2e54d4) = R0;
      R0 = 0x2e6400;
      I0 = R0;
      R0 = DM(0x2e5720);
      I1 = R0;
      R11 = 0xc;
      R12 = 0xbde401;                        // return address - 1: wr_ib_ret_38. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_38.;
wr_ib_ret_38.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      JUMP 0xbde548;                         // -> wr_ib_fi_39.
.GLOBAL wr_ib_else_29.;
wr_ib_else_29.:
      R0 = DM(0x2e571c);
      R0 = PASS R0;
      IF NE JUMP 0xbde42d;                   // -> wr_ib_else_40.
      R0 = 0x2e6e00;
      I0 = R0;
      R0 = 0x2e5a24;
      I1 = R0;
      R11 = 0x4;
      R12 = 0xbde421;                        // return address - 1: wr_ib_ret_41. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_41.;
wr_ib_ret_41.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = 0x1;
      DM(0x2e571c) = R0;
.GLOBAL wr_ib_else_40.;
wr_ib_else_40.:
      R0 = DM(0x2e5714);
      R12 = 0x8c;
      R0 = R0 * R12 (SSI);
      R12 = 0x2e1750;
      R0 = R12 + R0;
      DM(0x2e5720) = R0;
      R0 = DM(0x2e5720);
      I0 = R0;
      R0 = 0x2e6e00;
      I1 = R0;
      R11 = 0x4;
      R12 = 0xbde44f;                        // return address - 1: wr_ib_ret_42. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_42.;
wr_ib_ret_42.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 2;
      R12 = 0x200bd1a0;
      R0 = R12 + R0;
      I4 = R0;
      R8 = DM(0x2e5700);
      R12 = 0x1;
      R1 = R8 + R12;
      R2 = DM(0x2e5710);
      R2 = LSHIFT R2 BY 8;
      R1 = R1 OR R2;
      R3 = DM(0, I4);
      COMP(R1, R3);
      IF EQ JUMP 0xbde49d;                   // -> wr_ib_else_43.
      DM(0, I4) = R1;
      R0 = 0x2e6e00;
      I0 = R0;
      R0 = 0x0;
      R11 = 0x23;
.GLOBAL wr_ib_loop_44.;
wr_ib_loop_44.:
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde482;                   // -> wr_ib_loop_44.
      R0 = DM(0x2e5714);
      R0 = LSHIFT R0 BY 22;
      R12 = -0x7d000000;
      R0 = R12 + R0;
      DM(0x2e6e00) = R0;
      R12 = 0x200000;
      R0 = R12 + R0;
      DM(0x2e6e04) = R0;
.GLOBAL wr_ib_else_43.;
wr_ib_else_43.:
      R2 = DM(0x2e570c);
      I4 = R2;
      R8 = DM(2, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56e0) = R8;
      R8 = 0x0;                         // 0.0
      DM(0x2e56e4) = R8;
      R8 = DM(3, I4);
      F8 = FLOAT R8;
      R9 = 0x3c000000;                  // 0.0078125
      F8 = F8 * F9;
      DM(0x2e56e8) = R8;
      R8 = DM(4, I4);
      F8 = FLOAT R8;
      R9 = 0x3c000000;                  // 0.0078125
      F8 = F8 * F9;
      DM(0x2e56ec) = R8;
      R8 = DM(5, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56f0) = R8;
      R8 = DM(6, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e56f4) = R8;
      R8 = DM(1, I4);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(0x2e572c) = R8;
      R0 = 0x2e56e0;
      DM(0x2e6e1c) = R0;
      R0 = 0x2e54c0;
      DM(0x2e6e20) = R0;
      R0 = 0x1;
      DM(0x2e6e08) = R0;
      R0 = DM(0x2e5724);
      I0 = R0;
      R0 = 0x2e54e0;
      I1 = R0;
      R2 = 0x3d90fdbc;                  // 0.07079645991325378
      R11 = 0x20;
.GLOBAL wr_ib_loop_45.;
wr_ib_loop_45.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde509;                   // -> wr_ib_loop_45.
      R0 = DM(0x2e5728);
      I0 = R0;
      R0 = 0x2e5560;
      I1 = R0;
      R2 = 0x3d90fdbc;                  // 0.07079645991325378
      R11 = 0x20;
.GLOBAL wr_ib_loop_46.;
wr_ib_loop_46.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde51f;                   // -> wr_ib_loop_46.
      R12 = 0xbde52d;                        // return address - 1: wr_ib_eret_47. - 1
      I12 = R12;
      JUMP 0xbd9f00;                    // the engine, MODE 1 (it returns with JUMP (M14, I12))
.GLOBAL wr_ib_eret_47.;
wr_ib_eret_47.:
      R0 = 0x2e6e00;
      I0 = R0;
      R0 = DM(0x2e5720);
      I1 = R0;
      R11 = 0x4;
      R12 = 0xbde541;                        // return address - 1: wr_ib_ret_48. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_48.;
wr_ib_ret_48.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
.GLOBAL wr_ib_fi_39.;
wr_ib_fi_39.:
      R8 = 0x3f800000;                  // 1.0
      R7 = 0x0;                         // 0.0
      R13 = DM(0x2e573c);
      R12 = 0x1;
      COMP(R13, R12);
      IF NE JUMP 0xbde55c;                   // -> wr_ib_else_49.
      R8 = 0x3d000000;                  // 0.03125
      R7 = 0x3d000000;                  // 0.03125
.GLOBAL wr_ib_else_49.;
wr_ib_else_49.:
      R12 = 0x4;
      COMP(R13, R12);
      IF NE JUMP 0xbde568;                   // -> wr_ib_else_50.
      R8 = 0x3f780000;                  // 0.96875
      R7 = -0x43000000;                 // -0.03125
.GLOBAL wr_ib_else_50.;
wr_ib_else_50.:
      F7 = PASS F7;
      IF NE JUMP 0xbde5b6;                   // -> wr_ib_else_51.
      R0 = DM(0x2e5724);
      I0 = R0;
      I1 = R0;
      R0 = 0x2e55e0;
      I2 = R0;
      R4 = 0x41620000;                  // 14.125
      R5 = DM(0x2e572c);
      F6 = PASS F8;
      F3 = F5 * F6;
      R11 = 0x20;
.GLOBAL wr_ib_loop_52.;
wr_ib_loop_52.:
      R0 = DM(I0, M6);
      R1 = DM(I2, M6);
      F1 = F1 * F4;
      F1 = F1 - F0;
      F1 = F1 * F3;
      F0 = F0 + F1;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde585;                   // -> wr_ib_loop_52.
      R0 = DM(0x2e5728);
      I0 = R0;
      I1 = R0;
      R0 = 0x2e5660;
      I2 = R0;
      R4 = 0x41620000;                  // 14.125
      R5 = DM(0x2e572c);
      F6 = PASS F8;
      F3 = F5 * F6;
      R11 = 0x20;
.GLOBAL wr_ib_loop_53.;
wr_ib_loop_53.:
      R0 = DM(I0, M6);
      R1 = DM(I2, M6);
      F1 = F1 * F4;
      F1 = F1 - F0;
      F1 = F1 * F3;
      F0 = F0 + F1;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde5a8;                   // -> wr_ib_loop_53.
      JUMP 0xbde5fe;                         // -> wr_ib_fi_54.
.GLOBAL wr_ib_else_51.;
wr_ib_else_51.:
      R0 = DM(0x2e5724);
      I0 = R0;
      I1 = R0;
      R0 = 0x2e55e0;
      I2 = R0;
      R4 = 0x41620000;                  // 14.125
      R5 = DM(0x2e572c);
      F6 = PASS F8;
      R11 = 0x20;
.GLOBAL wr_ib_loop_55.;
wr_ib_loop_55.:
      R0 = DM(I0, M6);
      R1 = DM(I2, M6);
      F1 = F1 * F4;
      F1 = F1 - F0;
      F3 = F5 * F6;
      F6 = F6 + F7;
      F1 = F1 * F3;
      F0 = F0 + F1;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde5cc;                   // -> wr_ib_loop_55.
      R0 = DM(0x2e5728);
      I0 = R0;
      I1 = R0;
      R0 = 0x2e5660;
      I2 = R0;
      R4 = 0x41620000;                  // 14.125
      R5 = DM(0x2e572c);
      F6 = PASS F8;
      R11 = 0x20;
.GLOBAL wr_ib_loop_56.;
wr_ib_loop_56.:
      R0 = DM(I0, M6);
      R1 = DM(I2, M6);
      F1 = F1 * F4;
      F1 = F1 - F0;
      F3 = F5 * F6;
      F6 = F6 + F7;
      F1 = F1 * F3;
      F0 = F0 + F1;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde5f0;                   // -> wr_ib_loop_56.
.GLOBAL wr_ib_fi_54.;
wr_ib_fi_54.:
.GLOBAL wr_ib_else_28.;
wr_ib_else_28.:
.GLOBAL wr_ib_else_10.;
wr_ib_else_10.:
      R0 = DM(0x2e5700);
      R12 = 0x1;
      R0 = R0 AND R12;
      R0 = PASS R0;
      IF EQ JUMP 0xbde781;                   // -> wr_ib_else_57.
      R3 = DM(0x2e5710);
      R12 = 0xf;
      R8 = MIN(R3, R12);
      R4 = 0x1;
      F4 = FLOAT R4 BY R8;
      R4 = TRUNC F4;
      R12 = 0x1e4e;
      R4 = R4 AND R12;
      R4 = PASS R4;
      IF EQ JUMP 0xbde76e;                   // -> wr_ib_else_58.
      R2 = DM(0x2e570c);
      R12 = 0x20;
      R2 = R2 - R12;
      I4 = R2;
      R3 = DM(0, I4);
      R12 = 0xf;
      R3 = R3 AND R12;
      R8 = MIN(R3, R12);
      R4 = 0x1;
      F4 = FLOAT R4 BY R8;
      R4 = TRUNC F4;
      R12 = 0x21b0;
      R4 = R4 AND R12;
      R4 = PASS R4;
      IF EQ JUMP 0xbde758;                   // -> wr_ib_else_59.
      R10 = DM(0x2ddff0);
      R10 = PASS R10;
      IF EQ JUMP 0xbde66d;                   // -> wr_ib_iago_60.
      R8 = EMUCLK;
      R9 = DM(0x2de13c);
      R8 = R8 - R9;                     // into the frame
      R9 = 0x3908;
      R8 = R8 + R9;                     // and this insert's bound
      COMP(R8, R10);
      IF LE JUMP 0xbde66d;                   // -> wr_ib_iago_60.
      R8 = DM(0x2de0f4);
      R8 = R8 + 1;
      DM(0x2de0f4) = R8;
      R9 = DM(0x2e5710);
      R12 = 0xf;
      R9 = R9 AND R12;
      R9 = LSHIFT R9 BY 2;
      R12 = 0x2e1700;
      R9 = R12 + R9;
      I4 = R9;
      R8 = DM(0, I4);
      R12 = 0x1;
      R8 = R8 + R12;
      DM(0, I4) = R8;
      JUMP 0xbde755;                         // -> wr_ib_iadone_61.
.GLOBAL wr_ib_iago_60.;
wr_ib_iago_60.:
      R0 = DM(0x2e5704);
      R1 = LSHIFT R0 BY 8;
      R12 = 0x258f68;
      R1 = R12 + R1;
      DM(0x2e5724) = R1;
      R12 = 0x80;
      R1 = R12 + R1;
      DM(0x2e5728) = R1;
      R0 = DM(0x2e5724);
      I0 = R0;
      R0 = 0x2e54e0;
      I1 = R0;
      R2 = 0x3d90fdbc;                  // 0.07079645991325378
      R11 = 0x20;
.GLOBAL wr_ib_loop_62.;
wr_ib_loop_62.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde691;                   // -> wr_ib_loop_62.
      R0 = DM(0x2e5728);
      I0 = R0;
      R0 = 0x2e5560;
      I1 = R0;
      R2 = 0x3d90fdbc;                  // 0.07079645991325378
      R11 = 0x20;
.GLOBAL wr_ib_loop_63.;
wr_ib_loop_63.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde6a7;                   // -> wr_ib_loop_63.
      R0 = DM(0x2e5704);
      R0 = LSHIFT R0 BY 1;
      R1 = LSHIFT R0 BY 5;
      R12 = 0x200bd600;
      R1 = R12 + R1;
      DM(0x2e3414) = R1;
      R1 = LSHIFT R0 BY 11;
      R12 = -0x7dac0000;
      R1 = R12 + R1;
      DM(0x2e3488) = R1;
      R1 = 0x2e54e0;
      DM(0x2e3418) = R1;
      R1 = DM(0x2e5704);
      DM(0x2e3490) = R1;
      R1 = DM(0x2e5710);
      DM(0x2e348c) = R1;
      R1 = DM(0x2e570c);
      DM(0x2e340c) = R1;
      R12 = 0xbde6ea;                        // return address - 1: wr_ib_oret_64. - 1
      DM(0x2e34d0) = R12;
      JUMP 0xbd6c03;                    // the pre pass's one insert (program.one)
.GLOBAL wr_ib_oret_64.;
wr_ib_oret_64.:
      R0 = DM(0x2e5704);
      R0 = LSHIFT R0 BY 1;
      R0 = R0 + 1;
      R1 = LSHIFT R0 BY 5;
      R12 = 0x200bd600;
      R1 = R12 + R1;
      DM(0x2e3414) = R1;
      R1 = LSHIFT R0 BY 11;
      R12 = -0x7dac0000;
      R1 = R12 + R1;
      DM(0x2e3488) = R1;
      R1 = 0x2e5560;
      DM(0x2e3418) = R1;
      R1 = DM(0x2e5704);
      DM(0x2e3490) = R1;
      R1 = DM(0x2e5710);
      DM(0x2e348c) = R1;
      R1 = DM(0x2e570c);
      DM(0x2e340c) = R1;
      R12 = 0xbde728;                        // return address - 1: wr_ib_oret_65. - 1
      DM(0x2e34d0) = R12;
      JUMP 0xbd6c03;                    // the pre pass's one insert (program.one)
.GLOBAL wr_ib_oret_65.;
wr_ib_oret_65.:
      R0 = 0x2e54e0;
      I0 = R0;
      R0 = DM(0x2e5724);
      I1 = R0;
      R2 = 0x41620000;                  // 14.125
      R11 = 0x20;
.GLOBAL wr_ib_loop_66.;
wr_ib_loop_66.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde738;                   // -> wr_ib_loop_66.
      R0 = 0x2e5560;
      I0 = R0;
      R0 = DM(0x2e5728);
      I1 = R0;
      R2 = 0x41620000;                  // 14.125
      R11 = 0x20;
.GLOBAL wr_ib_loop_67.;
wr_ib_loop_67.:
      R0 = DM(I0, M6);
      F0 = F0 * F2;
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde74e;                   // -> wr_ib_loop_67.
.GLOBAL wr_ib_iadone_61.;
wr_ib_iadone_61.:
      JUMP 0xbde76b;                         // -> wr_ib_fi_68.
.GLOBAL wr_ib_else_59.;
wr_ib_else_59.:
      R0 = DM(0x2e5704);
      R1 = LSHIFT R0 BY 6;
      R12 = 0x200bd61c;
      R2 = R12 + R1;
      I4 = R2;
      R0 = 0x0;
      DM(0, I4) = R0;
      DM(8, I4) = R0;
.GLOBAL wr_ib_fi_68.;
wr_ib_fi_68.:
      JUMP 0xbde781;                         // -> wr_ib_fi_69.
.GLOBAL wr_ib_else_58.;
wr_ib_else_58.:
      R0 = DM(0x2e5704);
      R1 = LSHIFT R0 BY 6;
      R12 = 0x200bd61c;
      R2 = R12 + R1;
      I4 = R2;
      R0 = 0x0;
      DM(0, I4) = R0;
      DM(8, I4) = R0;
.GLOBAL wr_ib_fi_69.;
wr_ib_fi_69.:
.GLOBAL wr_ib_else_57.;
wr_ib_else_57.:
      R0 = DM(0x2e5700);
      R12 = 0x1;
      R0 = R12 + R0;
      DM(0x2e5700) = R0;
      R0 = DM(0x2e3474);
      R0 = R0 - R12;
      DM(0x2e3474) = R0;
      IF NE JUMP 0xbde0ce;                   // -> wr_ib_trk_4.
      R0 = DM(0x2e5718);
      R0 = PASS R0;
      IF EQ JUMP 0xbde7c6;                   // -> wr_ib_else_70.
      R0 = 0x2e57a0;
      I0 = R0;
      R0 = 0x2e6400;
      I1 = R0;
      R11 = 0xc;
      R12 = 0xbde7af;                        // return address - 1: wr_ib_ret_71. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_71.;
wr_ib_ret_71.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = 0x2e5924;
      I0 = R0;
      R0 = 0x2e672c;
      I1 = R0;
      R11 = 0x8;
      R12 = 0xbde7c5;                        // return address - 1: wr_ib_ret_72. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_72.;
wr_ib_ret_72.:
.GLOBAL wr_ib_else_70.;
wr_ib_else_70.:
      R0 = DM(0x2e571c);
      R0 = PASS R0;
      IF EQ JUMP 0xbde7e7;                   // -> wr_ib_else_73.
      R0 = 0x2e5a24;
      I0 = R0;
      R0 = 0x2e6e00;
      I1 = R0;
      R11 = 0x4;
      R12 = 0xbde7e0;                        // return address - 1: wr_ib_ret_74. - 1
      I12 = R12;
      JUMP 0xbde858;                         // -> wr_ib_sub_copy8.
.GLOBAL wr_ib_ret_74.;
wr_ib_ret_74.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
.GLOBAL wr_ib_else_73.;
wr_ib_else_73.:
      JUMP 0xbde7fd;                         // -> wr_ib_fi_75.
.GLOBAL wr_ib_else_3.;
wr_ib_else_3.:
      R1 = 0x200bd61c;
      R0 = 0x0;
      R13 = 0x20;
      R11 = 0x20;
.GLOBAL wr_ib_loop_76.;
wr_ib_loop_76.:
      I4 = R1;
      DM(0, I4) = R0;
      R1 = R13 + R1;
      R11 = R11 - 1;
      IF NE JUMP 0xbde7f3;                   // -> wr_ib_loop_76.
.GLOBAL wr_ib_fi_75.;
wr_ib_fi_75.:
      R8 = EMUCLK;
      DM(0x2ddff4) = R8;
      R9 = DM(0x2de0f0);
      R8 = R8 - R9;                     // this pass's time
      R9 = DM(0x2de0ec);
      R8 = R8 + R9;
      DM(0x2de0ec) = R8;
      ASTAT = DM(0x2e579c);
      I0 = DM(0x2e5784);
      I1 = DM(0x2e5788);
      I2 = DM(0x2e578c);
      I3 = DM(0x2e5790);
      I4 = DM(0x2e5794);
      I12 = DM(0x2e5798);
      R0 = DM(0x2e5744);
      R1 = DM(0x2e5748);
      R2 = DM(0x2e574c);
      R3 = DM(0x2e5750);
      R4 = DM(0x2e5754);
      R5 = DM(0x2e5758);
      R6 = DM(0x2e575c);
      R7 = DM(0x2e5760);
      R8 = DM(0x2e5764);
      R9 = DM(0x2e5768);
      R10 = DM(0x2e576c);
      R11 = DM(0x2e5770);
      R12 = DM(0x2e5774);
      R13 = DM(0x2e5778);
      R14 = DM(0x2e577c);
      R15 = DM(0x2e5780);
      R2 = DM(0x257980);                // the routing's instruction the JUMP took the place of
      JUMP 0x1c1ff2;                    // back into the routing: it sums the tracks' blocks into the main bus next
.GLOBAL wr_ib_sub_copy8.;
wr_ib_sub_copy8.:
.GLOBAL wr_ib_loop_77.;
wr_ib_loop_77.:
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R0 = DM(I0, M6);
      DM(I1, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbde858;                   // -> wr_ib_loop_77.
      JUMP (M14, I12);
.wr_inbus..end:
      .type wr_inbus.,STT_FUNC;
