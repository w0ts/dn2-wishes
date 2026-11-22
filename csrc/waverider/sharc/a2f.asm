// a2f.asm -- ANALOG 2's filters as filter machines (dnfw.engines.analog2.filters). GENERATED from
// dnfw.engines.analog2.filters.program; do not edit by hand.

.SECTION/PM seg_pmco;

.GLOBAL wr_a2f.;
wr_a2f.:
      R0 = 0x0;
      DM(0x2dda60) = R0;
      R0 = 0x14;
      DM(0x2dda70) = R0;
      R0 = 0x0;
      DM(0x2dda00) = R0;
      R0 = 0x10;
      DM(0x2dda04) = R0;
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
      IF EQ JUMP 0xbd923a;                   // -> wr_a2f_isz_1.
      R9 = R9 + R8;                     // no longer to come
.GLOBAL wr_a2f_isz_1.;
wr_a2f_isz_1.:
      DM(0x2ddff0) = R9;
      R9 = PASS R9;
      IF EQ JUMP 0xbd9251;                   // -> wr_a2f_irz_2.
      R8 = EMUCLK;
      R8 = R9 - R8;                     // the room before this pass's deadline ..
      R9 = DM(0x2de13c);
      R8 = R8 + R9;                     // .. from here, in the frame
      R9 = DM(0x2e1740);
      R8 = MIN(R8, R9);
      DM(0x2e1740) = R8;
.GLOBAL wr_a2f_irz_2.;
wr_a2f_irz_2.:
      R0 = 0x0;
      DM(0x2dda00) = R0;
      R0 = 0x10;
      DM(0x2dda04) = R0;
.GLOBAL wr_a2f_ml_3.;
wr_a2f_ml_3.:
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY 6;
      R12 = 0x2dd600;
      R1 = R12 + R1;
      DM(0x2dda0c) = R1;
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY -1;
      R1 = LSHIFT R1 BY 2;
      R12 = 0x257898;
      R2 = R12 + R1;
      I4 = R2;
      R3 = DM(0, I4);
      R12 = 0x1;
      R1 = R0 AND R12;
      R1 = PASS R1;
      IF EQ JUMP 0xbd9286;                   // -> wr_a2f_else_4.
      R3 = LSHIFT R3 BY -16;
.GLOBAL wr_a2f_else_4.;
wr_a2f_else_4.:
      R12 = 0xffff;
      R3 = R3 AND R12;
      DM(0x2dda08) = R3;
      R5 = 0x0;
      R12 = 0xf;
      COMP(R3, R12);
      IF GT JUMP 0xbd92e1;                   // -> wr_a2f_else_5.
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY -1;
      R1 = LSHIFT R1 BY 2;
      R12 = 0x25c540;
      R2 = R12 + R1;
      I4 = R2;
      R4 = DM(0, I4);
      R12 = 0x1;
      R1 = R0 AND R12;
      R1 = PASS R1;
      IF EQ JUMP 0xbd92b2;                   // -> wr_a2f_else_6.
      R4 = LSHIFT R4 BY -16;
.GLOBAL wr_a2f_else_6.;
wr_a2f_else_6.:
      R12 = 0xffff;
      R4 = R4 AND R12;
      R12 = 0x7;
      R4 = R4 - R12;
      R6 = 0x0;
      COMP(R4, R6);
      IF NE JUMP 0xbd92c1;                   // -> wr_a2f_else_7.
      R5 = 0x1;
.GLOBAL wr_a2f_else_7.;
wr_a2f_else_7.:
      R6 = 0x1;
      COMP(R4, R6);
      IF NE JUMP 0xbd92c9;                   // -> wr_a2f_else_8.
      R5 = 0x2;
.GLOBAL wr_a2f_else_8.;
wr_a2f_else_8.:
      R6 = 0x2;
      COMP(R4, R6);
      IF NE JUMP 0xbd92d1;                   // -> wr_a2f_else_9.
      R5 = 0x3;
.GLOBAL wr_a2f_else_9.;
wr_a2f_else_9.:
      R6 = 0x3;
      COMP(R4, R6);
      IF NE JUMP 0xbd92d9;                   // -> wr_a2f_else_10.
      R5 = 0x4;
.GLOBAL wr_a2f_else_10.;
wr_a2f_else_10.:
      R6 = 0x4;
      COMP(R4, R6);
      IF NE JUMP 0xbd92e1;                   // -> wr_a2f_else_11.
      R5 = 0x5;
.GLOBAL wr_a2f_else_11.;
wr_a2f_else_11.:
.GLOBAL wr_a2f_else_5.;
wr_a2f_else_5.:
      R0 = DM(0x2dda0c);
      I2 = R0;
      R5 = PASS R5;
      IF NE JUMP 0xbd92f1;                   // -> wr_a2f_else_12.
      R0 = 0x0;
      DM(12, I2) = R0;
      JUMP 0xbd9b74;                         // -> wr_a2f_fi_13.
.GLOBAL wr_a2f_else_12.;
wr_a2f_else_12.:
      DM(0x2dda50) = R5;
      R6 = DM(12, I2);
      R7 = DM(13, I2);
      R8 = DM(0x2dda08);
      R9 = 0x0;
      COMP(R6, R5);
      IF EQ JUMP 0xbd9303;                   // -> wr_a2f_else_14.
      R9 = 0x1;
.GLOBAL wr_a2f_else_14.;
wr_a2f_else_14.:
      COMP(R7, R8);
      IF EQ JUMP 0xbd9309;                   // -> wr_a2f_else_15.
      R9 = 0x1;
.GLOBAL wr_a2f_else_15.;
wr_a2f_else_15.:
      R9 = PASS R9;
      IF EQ JUMP 0xbd9329;                   // -> wr_a2f_else_16.
      R0 = DM(0x2dda0c);
      I3 = R0;
      R8 = 0x0;
      R11 = 0x10;
.GLOBAL wr_a2f_loop_17.;
wr_a2f_loop_17.:
      DM(I3, M6) = F8;
      R11 = R11 - 1;
      IF NE JUMP 0xbd9316;                   // -> wr_a2f_loop_17.
      R8 = -0x40800000;                 // -1.0
      DM(4, I2) = R8;
      DM(9, I2) = R8;
      DM(12, I2) = R5;
      R8 = DM(0x2dda08);
      DM(13, I2) = R8;
.GLOBAL wr_a2f_else_16.;
wr_a2f_else_16.:
      R8 = DM(0x2dda50);
      R9 = 0x1;
      COMP(R8, R9);
      IF NE JUMP 0xbd9337;                   // -> wr_a2f_else_18.
      R10 = 0x0;
      DM(0x2dda88) = R10;
.GLOBAL wr_a2f_else_18.;
wr_a2f_else_18.:
      R9 = 0x2;
      COMP(R8, R9);
      IF NE JUMP 0xbd9342;                   // -> wr_a2f_else_19.
      R10 = 0x0;
      DM(0x2dda88) = R10;
.GLOBAL wr_a2f_else_19.;
wr_a2f_else_19.:
      R9 = 0x3;
      COMP(R8, R9);
      IF NE JUMP 0xbd934d;                   // -> wr_a2f_else_20.
      R10 = 0x0;
      DM(0x2dda88) = R10;
.GLOBAL wr_a2f_else_20.;
wr_a2f_else_20.:
      R9 = 0x4;
      COMP(R8, R9);
      IF NE JUMP 0xbd9358;                   // -> wr_a2f_else_21.
      R10 = 0x2ee0;
      DM(0x2dda88) = R10;
.GLOBAL wr_a2f_else_21.;
wr_a2f_else_21.:
      R9 = 0x5;
      COMP(R8, R9);
      IF NE JUMP 0xbd9363;                   // -> wr_a2f_else_22.
      R10 = 0x0;
      DM(0x2dda88) = R10;
.GLOBAL wr_a2f_else_22.;
wr_a2f_else_22.:
      R10 = DM(0x2ddff0);
      R10 = PASS R10;
      IF EQ JUMP 0xbd9384;                   // -> wr_a2f_a2go_23.
      R8 = EMUCLK;
      R9 = DM(0x2de13c);
      R8 = R8 - R9;                     // into the frame
      R9 = DM(0x2dda88);
      R8 = R8 + R9;                     // and this model's bound
      COMP(R8, R10);
      IF LE JUMP 0xbd9384;                   // -> wr_a2f_a2go_23.
      R8 = DM(0x2de0f4);
      R9 = 0x1;
      R8 = R8 + R9;
      DM(0x2de0f4) = R8;
      JUMP 0xbd9b74;                         // -> wr_a2f_a2done_24.
.GLOBAL wr_a2f_a2go_23.;
wr_a2f_a2go_23.:
      R8 = DM(0x2dda50);
      R12 = -0x1;
      R8 = R8 + R12;
      DM(0x2ddaa8) = R8;
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY 9;
      R2 = LSHIFT R0 BY 5;
      R8 = 0x0;
      R8 = R8 + R1;
      R8 = R8 + R2;
      R2 = LSHIFT R0 BY 4;
      R8 = R8 + R2;
      R2 = LSHIFT R0 BY 2;
      R8 = R8 + R2;
      R12 = 0x2554b8;
      R8 = R12 + R8;
      I4 = R8;
      R5 = DM(115, I4);
      R12 = 0x43000000;                 // 128.0
      F5 = F5 * F12;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda54) = R5;
      R5 = DM(116, I4);
      R12 = 0x43000000;                 // 128.0
      F5 = F5 * F12;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda58) = R5;
      R5 = DM(114, I4);
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x3f800000;                 // 1.0
      F5 = MIN(F5, F12);
      R12 = 0x40a00000;                 // 5.0
      F5 = F5 * F12;
      R5 = TRUNC F5;
      R12 = 0x4;
      R5 = MIN(R5, R12);
      DM(0x2dda5c) = R5;
      R5 = DM(126, I4);
      R12 = 0x42fe0000;                 // 127.0
      F5 = F5 * F12;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda64) = R5;
      R5 = DM(127, I4);
      R12 = 0x42fe0000;                 // 127.0
      F5 = F5 * F12;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda68) = R5;
      R5 = DM(123, I4);
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x3f800000;                 // 1.0
      F5 = MIN(F5, F12);
      R12 = 0x40a00000;                 // 5.0
      F5 = F5 * F12;
      R5 = TRUNC F5;
      R12 = 0x4;
      R5 = MIN(R5, R12);
      DM(0x2dda6c) = R5;
      R5 = DM(129, I4);
      R12 = 0x3f000000;                 // 0.5
      F5 = F5 - F12;
      R12 = 0x43283aef;                 // 168.23020935058594
      F5 = F5 * F12;
      DM(0x2dda20) = R5;
      R5 = DM(130, I4);
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x40000000;                 // 2.0
      F5 = MIN(F5, F12);
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY 2;
      R12 = 0x254b14;
      R1 = R12 + R1;
      I1 = R1;
      R6 = DM(0, I1);
      R7 = LSHIFT R6 BY -23;
      R12 = 0xff;
      R7 = R7 AND R12;
      COMP(R7, R12);
      IF NE JUMP 0xbd945f;                   // -> wr_a2f_else_25.
      R6 = 0x0;
      JUMP 0xbd9465;                         // -> wr_a2f_fi_26.
.GLOBAL wr_a2f_else_25.;
wr_a2f_else_25.:
      R6 = PASS R6;
      IF GE JUMP 0xbd9465;                   // -> wr_a2f_else_27.
      R6 = 0x0;
.GLOBAL wr_a2f_else_27.;
wr_a2f_else_27.:
.GLOBAL wr_a2f_fi_26.;
wr_a2f_fi_26.:
      R12 = 0x42700000;                 // 60.0
      F6 = F6 - F12;
      F5 = F5 * F6;
      R12 = 0x3f9589b8;                 // 1.1682653427124023
      F5 = F5 * F12;
      DM(0x2dda1c) = R5;
      R0 = DM(124, I4);
      R12 = 0x0;                        // 0.0
      F0 = MAX(F0, F12);
      R12 = 0x3f800000;                 // 1.0
      F0 = MIN(F0, F12);
      R1 = -0x3ec08c26;                 // -11.965784072875977
      F0 = F0 * F1;
      R1 = 0x3fedfaf7;                  // 1.859221339225769
      F0 = F1 + F0;
      I12 = 0xbd948b;                        // return address - 1: wr_a2f_ret_28. - 1
      JUMP 0xbd9bb3;                         // -> wr_a2f_sub_exp2.
.GLOBAL wr_a2f_ret_28.;
wr_a2f_ret_28.:
      DM(0x2dda48) = R0;
      R0 = DM(125, I4);
      R12 = 0x0;                        // 0.0
      F0 = MAX(F0, F12);
      R12 = 0x3f800000;                 // 1.0
      F0 = MIN(F0, F12);
      R1 = -0x3ebb6588;                 // -12.287712097167969
      F0 = F0 * F1;
      I12 = 0xbd94a4;                        // return address - 1: wr_a2f_ret_29. - 1
      JUMP 0xbd9bb3;                         // -> wr_a2f_sub_exp2.
.GLOBAL wr_a2f_ret_29.;
wr_a2f_ret_29.:
      R1 = -0x4065e735;                 // -1.2038816213607788
      F0 = F0 * F1;
      I12 = 0xbd94ae;                        // return address - 1: wr_a2f_ret_30. - 1
      JUMP 0xbd9bb3;                         // -> wr_a2f_sub_exp2.
.GLOBAL wr_a2f_ret_30.;
wr_a2f_ret_30.:
      DM(0x2dda4c) = R0;
      R0 = DM(0x2dda0c);
      I2 = R0;
      R0 = DM(0x25c4ac);
      R0 = LSHIFT R0 BY -16;
      R2 = DM(0x2dda00);
      R1 = 0x1;
      R1 = LSHIFT R1 BY R2;
      R0 = R0 AND R1;
      R0 = PASS R0;
      IF EQ JUMP 0xbd94cd;                   // -> wr_a2f_else_31.
      R0 = 0x1;
      DM(11, I2) = R0;
.GLOBAL wr_a2f_else_31.;
wr_a2f_else_31.:
      R1 = DM(10, I2);
      R2 = DM(11, I2);
      R3 = DM(0x2dda48);
      R4 = DM(0x2dda4c);
      R2 = PASS R2;
      IF EQ JUMP 0xbd94ea;                   // -> wr_a2f_else_32.
      F1 = F1 + F3;
      R12 = 0x3f800000;                 // 1.0
      COMP(F1, F12);
      IF LT JUMP 0xbd94e7;                   // -> wr_a2f_else_33.
      F1 = PASS F12;
      R2 = 0x0;
.GLOBAL wr_a2f_else_33.;
wr_a2f_else_33.:
      JUMP 0xbd94eb;                         // -> wr_a2f_fi_34.
.GLOBAL wr_a2f_else_32.;
wr_a2f_else_32.:
      F1 = F1 * F4;
.GLOBAL wr_a2f_fi_34.;
wr_a2f_fi_34.:
      DM(0x2dda14) = R1;
      R2 = PASS R2;
      IF EQ JUMP 0xbd9501;                   // -> wr_a2f_else_35.
      F1 = F1 + F3;
      R12 = 0x3f800000;                 // 1.0
      COMP(F1, F12);
      IF LT JUMP 0xbd94fe;                   // -> wr_a2f_else_36.
      F1 = PASS F12;
      R2 = 0x0;
.GLOBAL wr_a2f_else_36.;
wr_a2f_else_36.:
      JUMP 0xbd9502;                         // -> wr_a2f_fi_37.
.GLOBAL wr_a2f_else_35.;
wr_a2f_else_35.:
      F1 = F1 * F4;
.GLOBAL wr_a2f_fi_37.;
wr_a2f_fi_37.:
      DM(0x2dda18) = R1;
      R0 = DM(0x2dda0c);
      I2 = R0;
      DM(10, I2) = R1;
      DM(11, I2) = R2;
      R0 = DM(0x2dda00);
      R1 = LSHIFT R0 BY 2;
      R12 = 0x254a60;
      R1 = R12 + R1;
      I1 = R1;
      R0 = DM(0, I1);
      DM(0x2dda24) = R0;
      R0 = 0x2dda54;
      DM(0x2dda28) = R0;
      R0 = 0x2;
      DM(0x2dda2c) = R0;
.GLOBAL wr_a2f_ml_38.;
wr_a2f_ml_38.:
      R8 = DM(0x2dda28);
      I1 = R8;
      R7 = DM(0, I1);
      R6 = DM(0x2dda1c);
      F7 = F7 + F6;
      R5 = DM(0x2dda20);
      R6 = DM(0x2dda14);
      F5 = F5 * F6;
      F5 = F7 + F5;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda40) = R5;
      R5 = DM(0x2dda20);
      R6 = DM(0x2dda18);
      F5 = F5 * F6;
      F5 = F7 + F5;
      R12 = 0x0;                        // 0.0
      F5 = MAX(F5, F12);
      R12 = 0x42fe0000;                 // 127.0
      F5 = MIN(F5, F12);
      DM(0x2dda44) = R5;
      R8 = DM(0x2dda28);
      I1 = R8;
      R0 = DM(1, I1);
      DM(0x2ddaa0) = R0;
      R0 = DM(2, I1);
      DM(0x2ddaa4) = R0;
      R0 = DM(3, I1);
      R8 = DM(0x2dda0c);
      R8 = R8 + R0;
      DM(0x2ddab0) = R8;
      I2 = R8;
      R0 = DM(4, I2);
      R5 = DM(0x2dda44);
      R12 = 0x0;                        // 0.0
      COMP(F0, F12);
      IF GE JUMP 0xbd9587;                   // -> wr_a2f_else_39.
      F0 = PASS F5;
.GLOBAL wr_a2f_else_39.;
wr_a2f_else_39.:
      DM(0x2dda34) = R0;
      DM(4, I2) = R5;
      R9 = 0x0;
      R8 = DM(0x2ddab0);
      I3 = R8;
      R11 = 0x4;
.GLOBAL wr_a2f_loop_40.;
wr_a2f_loop_40.:
      R0 = DM(I3, M6);
      R12 = 0x7fffffff;
      R0 = R0 AND R12;
      R12 = 0x461c4000;
      COMP(R0, R12);
      IF LT JUMP 0xbd95a3;                   // -> wr_a2f_else_41.
      R9 = 0x1;
.GLOBAL wr_a2f_else_41.;
wr_a2f_else_41.:
      R11 = R11 - 1;
      IF NE JUMP 0xbd9595;                   // -> wr_a2f_loop_40.
      R9 = PASS R9;
      IF EQ JUMP 0xbd95b5;                   // -> wr_a2f_else_42.
      R0 = 0x0;
      DM(0, I2) = R0;
      DM(1, I2) = R0;
      DM(2, I2) = R0;
      DM(3, I2) = R0;
.GLOBAL wr_a2f_else_42.;
wr_a2f_else_42.:
      R0 = DM(0x2ddaa8);
      R1 = 0x0;
      COMP(R0, R1);
      IF NE JUMP 0xbd95ca;                   // -> wr_a2f_else_43.
      R15 = DM(0x2dda34);
      I12 = 0xbd95c6;                        // return address - 1: wr_a2f_ret_44. - 1
      JUMP 0xbd9bed;                         // -> wr_a2f_sub_a2g.
.GLOBAL wr_a2f_ret_44.;
wr_a2f_ret_44.:
      DM(0x2dda34) = R15;
.GLOBAL wr_a2f_else_43.;
wr_a2f_else_43.:
      R15 = DM(0x2dda40);
      I12 = 0xbd95d2;                        // return address - 1: wr_a2f_ret_45. - 1
      JUMP 0xbd9bed;                         // -> wr_a2f_sub_a2g.
.GLOBAL wr_a2f_ret_45.;
wr_a2f_ret_45.:
      DM(0x2dda38) = R15;
      R15 = DM(0x2dda44);
      I12 = 0xbd95de;                        // return address - 1: wr_a2f_ret_46. - 1
      JUMP 0xbd9bed;                         // -> wr_a2f_sub_a2g.
.GLOBAL wr_a2f_ret_46.;
wr_a2f_ret_46.:
      DM(0x2dda3c) = R15;
      R0 = DM(0x2dda24);
      DM(0x2ddaac) = R0;
      R0 = 0x2;
      DM(0x2dda30) = R0;
      R8 = DM(0x2ddab0);
      I3 = R8;
      R9 = 0x0;
      R11 = 0x4;
.GLOBAL wr_a2f_loop_47.;
wr_a2f_loop_47.:
      R0 = DM(I3, M6);
      R9 = R9 OR R0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd95f6;                   // -> wr_a2f_loop_47.
      R8 = DM(0x2dda24);
      I3 = R8;
      R11 = 0x20;
.GLOBAL wr_a2f_loop_48.;
wr_a2f_loop_48.:
      R0 = DM(I3, M6);
      R9 = R9 OR R0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd9603;                   // -> wr_a2f_loop_48.
      DM(0x2dda94) = R9;
.GLOBAL wr_a2f_ml_49.;
wr_a2f_ml_49.:
      R0 = DM(0x2dda34);
      DM(0x2dda98) = R0;
      R0 = DM(0x2dda38);
      DM(0x2dda9c) = R0;
      R0 = DM(0x2dda94);
      R0 = PASS R0;
      IF EQ JUMP 0xbd9b35;                   // -> wr_a2f_else_50.
      R0 = DM(0x2ddaa8);                // model
      R1 = 0x0;
      COMP(R0, R1);
      IF NE JUMP 0xbd97d7;                   // -> wr_a2f_else_51.
      R0 = DM(0x2ddaa0);                // res
      R12 = 0x3c6f5ebd;                 // 0.01460998971015215
      F1 = F0 * F12;
      R12 = 0x40000000;                 // 2.0
      F1 = F12 - F1;
      R12 = 0x42c80000;                 // 100.0
      F0 = F0 - F12;
      R12 = 0x0;                        // 0.0
      COMP(F0, F12);
      IF LE JUMP 0xbd9645;                   // -> wr_a2f_else_52.
      F0 = F0 * F0;
      R12 = 0x397a0000;                 // 0.0002384185791015625
      F0 = F0 * F12;
      F1 = F1 - F0;
.GLOBAL wr_a2f_else_52.;
wr_a2f_else_52.:
      DM(0x2ddabc) = R1;                // k
      R0 = DM(0x2ddaa4);                // mode
      R8 = 0x2ddb9c;
      R2 = LSHIFT R0 BY 3;
      R8 = R8 + R2;
      R2 = LSHIFT R0 BY 4;
      R8 = R8 + R2;
      I3 = R8;
      DM(0x2ddab4) = R8;                // row
      R0 = DM(0x2ddab0);                // zp
      DM(0x2ddb3c) = R0;                // t1
      R0 = DM(0x2ddaa4);                // mode
      R1 = 0x1;
      R2 = 0x1;
      COMP(R0, R2);
      IF NE JUMP 0xbd966e;                   // -> wr_a2f_else_53.
      R1 = 0x2;
.GLOBAL wr_a2f_else_53.;
wr_a2f_else_53.:
      DM(0x2ddab8) = R1;                // nst
.GLOBAL wr_a2f_ml_54.;
wr_a2f_ml_54.:
      R9 = DM(0x2ddabc);                // k
      R13 = DM(0x2dda98);               // gs
      F15 = F13 + F9;
      F15 = F13 * F15;
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      I12 = 0xbd9685;                        // return address - 1: wr_a2f_ret_55. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_55.;
wr_a2f_ret_55.:
      R13 = DM(0x2dda98);               // gs
      F14 = F13 * F15;
      F13 = F13 * F14;
      DM(0x2ddac0) = R15;               // a1
      DM(0x2ddac4) = R14;               // a2
      DM(0x2ddac8) = R13;               // a3
      R13 = DM(0x2dda9c);               // ge
      F15 = F13 + F9;
      F15 = F13 * F15;
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      I12 = 0xbd96a6;                        // return address - 1: wr_a2f_ret_56. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_56.;
wr_a2f_ret_56.:
      R13 = DM(0x2dda9c);               // ge
      F14 = F13 * F15;
      F13 = F13 * F14;
      R12 = 0x3d800000;                 // 0.0625
      R10 = DM(0x2ddac0);               // a1
      F15 = F15 - F10;
      F15 = F15 * F12;
      F10 = F10 + F15;
      DM(0x2ddac0) = R10;               // a1
      DM(0x2ddacc) = R15;               // d1
      R10 = DM(0x2ddac4);               // a2
      F14 = F14 - F10;
      F14 = F14 * F12;
      F10 = F10 + F14;
      DM(0x2ddac4) = R10;               // a2
      DM(0x2ddad0) = R14;               // d2
      R10 = DM(0x2ddac8);               // a3
      F13 = F13 - F10;
      F13 = F13 * F12;
      F10 = F10 + F13;
      DM(0x2ddac8) = R10;               // a3
      DM(0x2ddad4) = R13;               // d3
      R0 = DM(0x2ddab4);                // row
      I3 = R0;
      R10 = DM(1, I3);
      F9 = F10 * F9, R10 = DM(2, I3);
      F9 = F9 + F10;
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      R1 = DM(0, I2);
      R2 = DM(1, I2);
      R3 = DM(0x2ddac0);                // a1
      R4 = DM(0x2ddac4);                // a2
      R5 = DM(0x2ddac8);                // a3
      R6 = DM(0x2ddacc);                // d1
      R7 = DM(0x2ddad0);                // d2
      R8 = DM(0x2ddad4);                // d3
      R0 = DM(0x2ddaac);                // buf
      I0 = R0;
      I2 = 0x2ddae8;
      R10 = 0x2ddb48;
      I1 = R10;
      R11 = 0x10;
.GLOBAL wr_a2f_loop_57.;
wr_a2f_loop_57.:
      F13 = F3 * F1, F0 = DM(0, I0);
      F10 = F0 - F2, F12 = DM(7, I1);
      F14 = F4 * F10;
      F13 = F13 + F14;
      F14 = F4 * F1;
      F15 = F5 * F10, F10 = DM(0, I3);
      F14 = F14 + F15;
      F14 = F2 + F14;
      F15 = F13 + F13;
      F1 = F15 - F1;
      F15 = F14 + F14;
      F2 = F15 - F2;
      F10 = F10 * F0;
      F15 = F9 * F13;
      F10 = F10 + F15, F15 = DM(3, I3);
      F15 = F15 * F14;
      F10 = F10 + F15, F15 = DM(4, I3);
      F10 = MIN(F10, F15), F15 = DM(5, I3);
      F10 = MAX(F10, F15);
      F3 = F3 + F6;
      F4 = F4 + F7;
      F5 = F5 + F8;
      F15 = ABS F1;
      DM(I0, M6) = F10;
      COMP(F15, F12);
      IF LE JUMP 0xbd9767;                   // -> wr_a2f_else_58.
      F10 = PASS F15;
      F15 = F15 - F12;
      R12 = 0x40000000;                 // 2.0
      F15 = MIN(F15, F12);
      I12 = 0xbd9748;                        // return address - 1: wr_a2f_ret_59. - 1
      JUMP 0xbd9c86;                         // -> wr_a2f_sub_a2th.
.GLOBAL wr_a2f_ret_59.;
wr_a2f_ret_59.:
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      R12 = 0x3f8f9db2;                 // 1.121999979019165
      F12 = F15 * F12;
      COMP(F12, F10);
      IF GE JUMP 0xbd975a;                   // -> wr_a2f_else_60.
      DM(0x2de0f8) = R10;
.GLOBAL wr_a2f_else_60.;
wr_a2f_else_60.:
      R12 = 0x0;                        // 0.0
      COMP(F1, F12);
      IF GE JUMP 0xbd9765;                   // -> wr_a2f_else_61.
      F1 = F12 - F15;
      JUMP 0xbd9767;                         // -> wr_a2f_fi_62.
.GLOBAL wr_a2f_else_61.;
wr_a2f_else_61.:
      F1 = PASS F15;
.GLOBAL wr_a2f_fi_62.;
wr_a2f_fi_62.:
.GLOBAL wr_a2f_else_58.;
wr_a2f_else_58.:
      F15 = ABS F2;
      R12 = DM(8, I1);
      COMP(F15, F12);
      IF LE JUMP 0xbd97a0;                   // -> wr_a2f_else_63.
      F10 = PASS F15;
      F15 = F15 - F12;
      R12 = 0x3f000000;                 // 0.5
      F15 = F15 * F12;
      R12 = 0x40000000;                 // 2.0
      F15 = MIN(F15, F12);
      I12 = 0xbd9780;                        // return address - 1: wr_a2f_ret_64. - 1
      JUMP 0xbd9c86;                         // -> wr_a2f_sub_a2th.
.GLOBAL wr_a2f_ret_64.;
wr_a2f_ret_64.:
      F15 = F15 + F15;
      R12 = 0x40000000;                 // 2.0
      F15 = F12 + F15;
      R12 = 0x3f8f9db2;                 // 1.121999979019165
      F12 = F15 * F12;
      COMP(F12, F10);
      IF GE JUMP 0xbd9793;                   // -> wr_a2f_else_65.
      DM(0x2de0f8) = R10;
.GLOBAL wr_a2f_else_65.;
wr_a2f_else_65.:
      R12 = 0x0;                        // 0.0
      COMP(F2, F12);
      IF GE JUMP 0xbd979e;                   // -> wr_a2f_else_66.
      F2 = F12 - F15;
      JUMP 0xbd97a0;                         // -> wr_a2f_fi_67.
.GLOBAL wr_a2f_else_66.;
wr_a2f_else_66.:
      F2 = PASS F15;
.GLOBAL wr_a2f_fi_67.;
wr_a2f_fi_67.:
.GLOBAL wr_a2f_else_63.;
wr_a2f_else_63.:
      R11 = R11 - 1;
      IF NE JUMP 0xbd9709;                   // -> wr_a2f_loop_57.
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      DM(0, I2) = R1;
      DM(1, I2) = R2;
      R1 = 0x3fb50800;                  // 1.414306640625
      DM(0x2ddabc) = R1;                // k
      R1 = 0x2ddc14;
      DM(0x2ddab4) = R1;                // row
      R8 = DM(0x2ddab0);                // zp
      R9 = 0x8;
      R8 = R8 + R9;
      DM(0x2ddab0) = R8;                // zp
      R0 = DM(0x2ddab8);
      R12 = 0x1;
      R0 = R0 - R12;
      DM(0x2ddab8) = R0;
      IF NE JUMP 0xbd9671;                   // -> wr_a2f_ml_54.
      R0 = DM(0x2ddb3c);                // t1
      DM(0x2ddab0) = R0;                // zp
      JUMP 0xbd9b35;                         // -> wr_a2f_fi_68.
.GLOBAL wr_a2f_else_51.;
wr_a2f_else_51.:
      R0 = DM(0x2ddaa8);                // model
      R2 = 0x0;
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbd97e4;                   // -> wr_a2f_else_69.
      R2 = 0x1;
.GLOBAL wr_a2f_else_69.;
wr_a2f_else_69.:
      R1 = 0x2;
      COMP(R0, R1);
      IF NE JUMP 0xbd97ec;                   // -> wr_a2f_else_70.
      R2 = 0x1;
.GLOBAL wr_a2f_else_70.;
wr_a2f_else_70.:
      R2 = PASS R2;
      IF EQ JUMP 0xbd9874;                   // -> wr_a2f_else_71.
      R0 = DM(0x2ddb44);                // cv
      R0 = PASS R0;
      IF NE JUMP 0xbd986b;                   // -> wr_a2f_else_72.
      R0 = DM(0x2ddaa8);                // model
      R1 = 0x2;
      COMP(R0, R1);
      IF NE JUMP 0xbd981f;                   // -> wr_a2f_else_73.
      R0 = DM(0x2ddaa0);                // res
      R12 = 0x3d077551;                 // 0.03307086601853371
      F0 = F0 * F12;
      DM(0x2ddabc) = R0;                // k
      R12 = 0x3f000000;                 // 0.5
      F1 = F12 * F0;
      R12 = 0x3f800000;                 // 1.0
      F1 = F12 + F1;
      DM(0x2ddae0) = R1;                // cin
      R1 = 0x1;
      DM(0x2ddaf4) = R1;                // ota
      JUMP 0xbd9834;                         // -> wr_a2f_fi_74.
.GLOBAL wr_a2f_else_73.;
wr_a2f_else_73.:
      R0 = DM(0x2ddaa0);                // res
      R12 = 0x3d145beb;                 // 0.03622047230601311
      F0 = F0 * F12;
      DM(0x2ddabc) = R0;                // k
      R1 = 0x3f800000;                  // 1.0
      DM(0x2ddae0) = R1;                // cin
      R1 = 0x0;
      DM(0x2ddaf4) = R1;                // ota
.GLOBAL wr_a2f_fi_74.;
wr_a2f_fi_74.:
      R15 = DM(0x2dda9c);               // ge
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      I12 = 0xbd9841;                        // return address - 1: wr_a2f_ret_75. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_75.;
wr_a2f_ret_75.:
      DM(0x2ddb38) = R15;               // t0
      R14 = DM(0x2dda9c);               // ge
      F14 = F14 * F15;
      DM(0x2ddae8) = R14;               // G
      R12 = 0x3f800000;                 // 1.0
      F13 = F12 - F14;
      DM(0x2ddaec) = R13;               // H
      F15 = F14 * F14;
      F15 = F15 * F14;
      F15 = F15 * F14;
      DM(0x2ddaf0) = R15;               // G4
      R13 = DM(0x2ddabc);               // k
      F15 = F13 * F15;
      F15 = F12 + F15;
      I12 = 0xbd9867;                        // return address - 1: wr_a2f_ret_76. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_76.;
wr_a2f_ret_76.:
      DM(0x2ddae4) = R15;               // inv
.GLOBAL wr_a2f_else_72.;
wr_a2f_else_72.:
      I12 = 0xbd9870;                        // return address - 1: wr_a2f_ret_77. - 1
      JUMP 0xbd9cc9;                         // -> wr_a2f_sub_a2lad.
.GLOBAL wr_a2f_ret_77.;
wr_a2f_ret_77.:
      JUMP 0xbd9b35;                         // -> wr_a2f_fi_78.
.GLOBAL wr_a2f_else_71.;
wr_a2f_else_71.:
      R0 = DM(0x2ddaa8);                // model
      R1 = 0x3;
      COMP(R0, R1);
      IF NE JUMP 0xbd9a21;                   // -> wr_a2f_else_79.
      R0 = DM(0x2ddb44);                // cv
      R0 = PASS R0;
      IF NE JUMP 0xbd994f;                   // -> wr_a2f_else_80.
      R0 = DM(0x2ddaa0);                // res
      R12 = 0x3e3162c6;                 // 0.17322835326194763
      F0 = F0 * F12;
      DM(0x2ddabc) = R0;                // k
      R12 = 0x3f000000;                 // 0.5
      F1 = F12 * F0;
      R12 = 0x3f800000;                 // 1.0
      F1 = F12 + F1;
      DM(0x2ddae0) = R1;                // cin
      R12 = 0x3dba2e8c;                 // 0.09090909361839294
      F1 = F0 * F12;
      R12 = 0x3f800000;                 // 1.0
      F1 = F12 + F1;
      DM(0x2ddaf8) = R1;                // gout
      R0 = DM(0x2dda9c);                // ge
      R12 = 0x3f560bfd;                 // 0.8361204266548157
      F0 = F0 * F12;
      DM(0x2ddafc) = R0;                // gd
      F1 = F0 + F0;
      R12 = 0x3f800000;                 // 1.0
      F1 = F12 + F1;
      DM(0x2ddb3c) = R1;                // t1
      F2 = F0 * F0;
      DM(0x2ddb40) = R2;                // t2
      F15 = PASS F1;
      I12 = 0xbd98c8;                        // return address - 1: wr_a2f_ret_81. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_81.;
wr_a2f_ret_81.:
      DM(0x2ddb00) = R15;               // ip1
      R0 = DM(0x2ddafc);                // gd
      F1 = F0 * F15;
      DM(0x2ddb10) = R1;                // h1
      R2 = DM(0x2ddb40);                // t2
      F2 = F2 * F15;
      R15 = DM(0x2ddb3c);               // t1
      F15 = F15 - F2;
      I12 = 0xbd98e1;                        // return address - 1: wr_a2f_ret_82. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_82.;
wr_a2f_ret_82.:
      DM(0x2ddb04) = R15;               // ip2
      R0 = DM(0x2ddafc);                // gd
      F1 = F0 * F15;
      DM(0x2ddb20) = R1;                // gp2
      R2 = DM(0x2ddb40);                // t2
      F2 = F2 * F15;
      R15 = DM(0x2ddb3c);               // t1
      F15 = F15 - F2;
      I12 = 0xbd98fa;                        // return address - 1: wr_a2f_ret_83. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_83.;
wr_a2f_ret_83.:
      DM(0x2ddb08) = R15;               // ip3
      R0 = DM(0x2ddafc);                // gd
      F1 = F0 * F15;
      DM(0x2ddb24) = R1;                // gp3
      R2 = DM(0x2ddb40);                // t2
      F2 = F2 * F15;
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F0;
      F15 = F15 - F2;
      I12 = 0xbd9915;                        // return address - 1: wr_a2f_ret_84. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_84.;
wr_a2f_ret_84.:
      DM(0x2ddb0c) = R15;               // ip4
      R0 = DM(0x2ddafc);                // gd
      F1 = F0 * F15;
      DM(0x2ddb38) = R1;                // t0
      R0 = DM(0x2ddb10);                // h1
      R1 = DM(0x2ddb20);                // gp2
      F0 = F1 * F0;
      DM(0x2ddb14) = R0;                // h2
      R1 = DM(0x2ddb24);                // gp3
      F0 = F1 * F0;
      DM(0x2ddb18) = R0;                // h3
      R1 = DM(0x2ddb38);                // t0
      F0 = F1 * F0;
      DM(0x2ddb1c) = R0;                // h4
      R1 = DM(0x2ddabc);                // k
      F15 = F1 * F0;
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      I12 = 0xbd994b;                        // return address - 1: wr_a2f_ret_85. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_85.;
wr_a2f_ret_85.:
      DM(0x2ddae4) = R15;               // inv
.GLOBAL wr_a2f_else_80.;
wr_a2f_else_80.:
      R0 = DM(0x2ddaa4);                // mode
      R8 = 0x2ddc90;
      R2 = LSHIFT R0 BY 2;
      R8 = R8 + R2;
      R2 = LSHIFT R0 BY 4;
      R8 = R8 + R2;
      I3 = R8;
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      R1 = DM(0, I2);
      R2 = DM(1, I2);
      R3 = DM(2, I2);
      R4 = DM(3, I2);
      R5 = DM(0x2ddafc);                // gd
      R0 = DM(0x2ddaac);                // buf
      I0 = R0;
      I2 = 0x2ddae8;
      R10 = 0x2ddb48;
      I1 = R10;
      R11 = 0x10;
.GLOBAL wr_a2f_loop_86.;
wr_a2f_loop_86.:
      F10 = DM(6, I2);
      F6 = F1 * F10, F14 = DM(7, I2);
      F7 = F5 * F6, F12 = DM(8, I2);
      F7 = F2 + F7, F10 = DM(9, I2);
      F7 = F7 * F14, F0 = DM(0, I0);
      F8 = F5 * F7, F14 = DM(-1, I2);
      F8 = F3 + F8;
      F8 = F8 * F12, F12 = DM(-11, I2);
      F9 = F5 * F8;
      F9 = F4 + F9;
      F9 = F9 * F10, F10 = DM(-2, I2);
      F15 = F0 * F10, F10 = DM(10, I2);
      F13 = F12 * F9, F12 = DM(0, I1);
      F15 = F15 - F13;
      F15 = F15 * F14;
      F15 = MIN(F15, F12), F12 = DM(1, I1);
      F15 = MAX(F15, F12), F12 = DM(2, I1);
      F13 = F15 * F15;
      F14 = F12 * F13, F12 = DM(3, I1);
      F14 = F12 + F14;
      F13 = F12 + F13, F12 = DM(4, I1);
      F13 = F15 * F13;
      R15 = R12 - R14;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15, F14 = DM(13, I2);
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12, F12 = DM(11, I2);
      F15 = F13 * F15, F13 = DM(12, I2);
      F10 = F10 * F15;
      F14 = F14 * F15;
      F6 = F6 + F10, F10 = DM(15, I2);
      F13 = F13 * F15;
      F9 = F9 + F14;
      F12 = F12 * F15;
      F8 = F8 + F13, F13 = DM(10, I2);
      F10 = F10 * F9;
      F7 = F7 + F12, F12 = DM(14, I2);
      F8 = F8 + F10;
      F12 = F12 * F8;
      F7 = F7 + F12;
      F13 = F13 * F7;
      F10 = F7 + F7;
      F12 = F8 + F8;
      F6 = F6 + F13;
      F2 = F10 - F2, F10 = DM(0, I3);
      F3 = F12 - F3, F12 = DM(1, I3);
      F13 = F9 + F9;
      F14 = F6 + F6;
      F4 = F13 - F4, F13 = DM(2, I3);
      F10 = F10 * F15;
      F12 = F12 * F6;
      F1 = F14 - F1, F14 = DM(3, I3);
      F10 = F10 + F12, F12 = DM(4, I3);
      F13 = F13 * F7;
      F10 = F10 + F13;
      F14 = F14 * F8;
      F10 = F10 + F14;
      F12 = F12 * F9;
      F10 = F10 + F12, F12 = DM(4, I2);
      F10 = F12 * F10, F12 = DM(5, I1);
      F10 = MIN(F10, F12), F12 = DM(6, I1);
      F10 = MAX(F10, F12);
      DM(I0, M6) = F10;
      R11 = R11 - 1;
      IF NE JUMP 0xbd997e;                   // -> wr_a2f_loop_86.
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      DM(0, I2) = R1;
      DM(1, I2) = R2;
      DM(2, I2) = R3;
      DM(3, I2) = R4;
      JUMP 0xbd9b35;                         // -> wr_a2f_fi_87.
.GLOBAL wr_a2f_else_79.;
wr_a2f_else_79.:
      R0 = DM(0x2ddaa8);                // model
      R1 = 0x4;
      COMP(R0, R1);
      IF NE JUMP 0xbd9b35;                   // -> wr_a2f_else_88.
      R0 = DM(0x2ddb44);                // cv
      R0 = PASS R0;
      IF NE JUMP 0xbd9a76;                   // -> wr_a2f_else_89.
      R0 = DM(0x2ddaa0);                // res
      R12 = 0x3c945beb;                 // 0.018110236153006554
      F0 = F0 * F12;
      DM(0x2ddabc) = R0;                // k
      R15 = DM(0x2dda9c);               // ge
      R12 = 0x3f800000;                 // 1.0
      F15 = F12 + F15;
      I12 = 0xbd9a48;                        // return address - 1: wr_a2f_ret_90. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_90.;
wr_a2f_ret_90.:
      DM(0x2ddb38) = R15;               // t0
      R14 = DM(0x2dda9c);               // ge
      F14 = F14 * F15;
      DM(0x2ddae8) = R14;               // G
      R12 = 0x3f800000;                 // 1.0
      F13 = F12 - F14;
      DM(0x2ddb34) = R13;               // omG
      R0 = DM(0x2ddabc);                // k
      F15 = F0 * F14;
      F15 = F15 * F13;
      F15 = F12 - F15;
      I12 = 0xbd9a68;                        // return address - 1: wr_a2f_ret_91. - 1
      JUMP 0xbd9c6b;                         // -> wr_a2f_sub_a2rc.
.GLOBAL wr_a2f_ret_91.;
wr_a2f_ret_91.:
      DM(0x2ddb30) = R15;               // dn
      R0 = DM(0x2ddabc);                // k
      R14 = DM(0x2ddae8);               // G
      F14 = F14 * F0;
      DM(0x2ddb28) = R14;               // Gk
.GLOBAL wr_a2f_else_89.;
wr_a2f_else_89.:
      R0 = DM(0x2ddaa4);                // mode
      R8 = 0x2ddcf4;
      R2 = LSHIFT R0 BY 4;
      R8 = R8 + R2;
      I3 = R8;
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      R1 = DM(0, I2);
      R2 = DM(1, I2);
      R3 = DM(3, I2);
      R4 = DM(0x2ddae8);                // G
      R5 = DM(0x2ddb38);                // t0
      R6 = DM(0x2ddabc);                // k
      R0 = DM(0x2ddaac);                // buf
      I0 = R0;
      I2 = 0x2ddae8;
      R8 = 0x2ddb48;
      I1 = R8;
      R11 = 0x10;
.GLOBAL wr_a2f_loop_92.;
wr_a2f_loop_92.:
      F9 = F2 * F5, F8 = DM(16, I2);
      F8 = F8 * F2, F0 = DM(0, I0);
      F8 = F1 - F8, F12 = DM(0, I1);
      F7 = F4 * F0;
      F8 = F8 * F5;
      F7 = F7 + F8, F8 = DM(18, I2);
      F7 = F7 * F8, F8 = DM(19, I2);
      F15 = F8 * F7;
      F15 = F15 - F9;
      COMP(F15, F12);
      IF LE JUMP 0xbd9ac1;                   // -> wr_a2f_else_93.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_93.;
wr_a2f_else_93.:
      F15 = MIN(F15, F12), F12 = DM(1, I1);
      COMP(F15, F12);
      IF GE JUMP 0xbd9acb;                   // -> wr_a2f_else_94.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_94.;
wr_a2f_else_94.:
      F15 = MAX(F15, F12), F12 = DM(2, I1);
      F13 = F15 * F15;
      F14 = F12 * F13, F12 = DM(3, I1);
      F14 = F12 + F14;
      F13 = F12 + F13, F12 = DM(4, I1);
      F13 = F15 * F13;
      R15 = R12 - R14;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12, F12 = DM(5, I1);
      F15 = F13 * F15;
      F15 = F6 * F15;
      F7 = F0 + F15;
      F8 = F4 * F7;
      F10 = F1 * F5;
      F8 = F8 + F10;
      F10 = F4 * F8;
      F10 = F10 + F9, F9 = DM(0, I3);
      F13 = F8 + F8;
      F1 = F13 - F1;
      F13 = F10 + F10;
      F2 = F13 - F2;
      F13 = F10 - F3;
      F13 = F13 * F4;
      F8 = F8 - F10;
      F14 = F13 + F3;
      F8 = F8 + F8;
      F3 = F14 + F13, F13 = DM(1, I3);
      F9 = F9 * F7;
      F13 = F13 * F8;
      F9 = F9 - F13, F13 = DM(2, I3);
      F13 = F13 * F10;
      F9 = F9 - F13, F13 = DM(3, I3);
      F13 = F13 * F14;
      F9 = F9 + F13;
      F9 = MIN(F9, F12), F12 = DM(6, I1);
      F9 = MAX(F9, F12);
      DM(I0, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd9aa5;                   // -> wr_a2f_loop_92.
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      DM(0, I2) = R1;
      DM(1, I2) = R2;
      DM(3, I2) = R3;
      JUMP 0xbd9b35;                         // -> wr_a2f_fi_95.
.GLOBAL wr_a2f_else_88.;
wr_a2f_else_88.:
.GLOBAL wr_a2f_fi_95.;
wr_a2f_fi_95.:
.GLOBAL wr_a2f_fi_87.;
wr_a2f_fi_87.:
.GLOBAL wr_a2f_fi_78.;
wr_a2f_fi_78.:
.GLOBAL wr_a2f_fi_68.;
wr_a2f_fi_68.:
.GLOBAL wr_a2f_else_50.;
wr_a2f_else_50.:
      R0 = DM(0x2dda38);
      DM(0x2dda34) = R0;
      R0 = DM(0x2dda3c);
      DM(0x2dda38) = R0;
      R8 = DM(0x2ddaac);
      R9 = 0x40;
      R8 = R8 + R9;
      DM(0x2ddaac) = R8;
      R0 = DM(0x2dda30);
      R12 = 0x1;
      R0 = R0 - R12;
      DM(0x2dda30) = R0;
      IF NE JUMP 0xbd960c;                   // -> wr_a2f_ml_49.
      R8 = DM(0x2dda28);
      R9 = 0x10;
      R8 = R8 + R9;
      DM(0x2dda28) = R8;
      R0 = DM(0x2dda2c);
      R12 = 0x1;
      R0 = R0 - R12;
      DM(0x2dda2c) = R0;
      IF NE JUMP 0xbd952b;                   // -> wr_a2f_ml_38.
      R8 = DM(0x2dda8c);
      R9 = 0x1;
      R8 = R8 + R9;
      DM(0x2dda8c) = R8;
.GLOBAL wr_a2f_a2done_24.;
wr_a2f_a2done_24.:
.GLOBAL wr_a2f_fi_13.;
wr_a2f_fi_13.:
      R0 = DM(0x2de0f8);
      R0 = PASS R0;
      IF EQ JUMP 0xbd9b8e;                   // -> wr_a2f_else_96.
      R1 = 0x1;
      R12 = DM(0x2dda08);
      R1 = LSHIFT R1 BY R12;
      R12 = DM(0x2ddfe8);
      R1 = R1 OR R12;
      DM(0x2ddfe8) = R1;
      R1 = 0x0;
      DM(0x2de0f8) = R1;
.GLOBAL wr_a2f_else_96.;
wr_a2f_else_96.:
      R8 = DM(0x2dda00);
      R9 = 0x1;
      R8 = R8 + R9;
      DM(0x2dda00) = R8;
      R0 = DM(0x2dda04);
      R12 = 0x1;
      R0 = R0 - R12;
      DM(0x2dda04) = R0;
      IF NE JUMP 0xbd925b;                   // -> wr_a2f_ml_3.
      R8 = EMUCLK;
      R9 = DM(0x2de0f0);
      R8 = R8 - R9;                     // this pass's time
      R9 = DM(0x2de0ec);
      R8 = R8 + R9;
      DM(0x2de0ec) = R8;
      JUMP 0x170280;                    // ping.asm's wr_ping (it returns to the stock chain)
.GLOBAL wr_a2f_sub_exp2.;
wr_a2f_sub_exp2.:
      R1 = -0x3d380000;                 // -100.0
      F0 = MAX(F0, F1);
      R1 = TRUNC F0;
      F2 = FLOAT R1;
      COMP(F2, F0);
      IF LE JUMP 0xbd9bc5;                   // -> wr_a2f_else_97.
      R1 = R1 - 1;
      R3 = 0x3f800000;                  // 1.0
      F2 = F2 - F3;
.GLOBAL wr_a2f_else_97.;
wr_a2f_else_97.:
      F2 = F0 - F2;
      R0 = 0x3af86540;                  // 0.0018951073288917542
      F0 = F0 * F2;
      R3 = 0x3c129325;                  // 0.00894621480256319
      F0 = F0 + F3;
      F0 = F0 * F2;
      R3 = 0x3d64d0e6;                  // 0.055863283574581146
      F0 = F0 + F3;
      F0 = F0 * F2;
      R3 = 0x3e75e776;                  // 0.24014076590538025
      F0 = F0 + F3;
      F0 = F0 * F2;
      R3 = 0x3f317295;                  // 0.6931546330451965
      F0 = F0 + F3;
      F0 = F0 * F2;
      R3 = 0x3f7ffffe;                  // 0.9999998807907104
      F0 = F0 + F3;
      R12 = 0x7f;
      R1 = R12 + R1;
      R1 = LSHIFT R1 BY 23;
      F0 = F0 * F1;
      JUMP (M14, I12);
.GLOBAL wr_a2f_sub_a2g.;
wr_a2f_sub_a2g.:
      R12 = 0x0;                        // 0.0
      F15 = MAX(F15, F12);
      R12 = 0x42fe0000;                 // 127.0
      F15 = MIN(F15, F12);
      R12 = 0x3d9215e5;                 // 0.07133082300424576
      F15 = F15 * F12;
      R14 = TRUNC F15;
      F13 = FLOAT R14;
      F15 = F15 - F13;
      R13 = 0x3af86540;                 // 0.0018951073288917542
      F13 = F13 * F15;
      R12 = 0x3c129325;                 // 0.00894621480256319
      F13 = F13 + F12;
      F13 = F13 * F15;
      R12 = 0x3d64d0e6;                 // 0.055863283574581146
      F13 = F13 + F12;
      F13 = F13 * F15;
      R12 = 0x3e75e776;                 // 0.24014076590538025
      F13 = F13 + F12;
      F13 = F13 * F15;
      R12 = 0x3f317295;                 // 0.6931546330451965
      F13 = F13 + F12;
      F13 = F13 * F15;
      R12 = 0x3f7ffffe;                 // 0.9999998807907104
      F13 = F13 + F12;
      R12 = 0x7f;
      R14 = R12 + R14;
      R14 = LSHIFT R14 BY 23;
      F13 = F13 * F14;
      R12 = 0x3a8c0f39;                 // 0.0010685689048841596
      F13 = F13 * F12;
      R12 = 0x3f34f4ab;                 // 0.7068583369255066
      F13 = MIN(F13, F12);
      F14 = F13 * F13;
      R15 = 0x3c8a86cf;                 // 0.01690998487174511
      F15 = F15 * F14;
      R12 = 0x3c8a76de;                 // 0.016902383416891098
      F15 = F15 + F12;
      F15 = F15 * F14;
      R12 = 0x3d6268bc;                 // 0.05527566373348236
      F15 = F15 + F12;
      F15 = F15 * F14;
      R12 = 0x3e0861d0;                 // 0.13318562507629395
      F15 = F15 + F12;
      F15 = F15 * F14;
      R12 = 0x3eaaab68;                 // 0.33333897590637207
      F15 = F15 + F12;
      F15 = F15 * F14;
      R12 = 0x3f800000;                 // 1.0
      F15 = F15 + F12;
      F15 = F13 * F15;
      F14 = F15 * F15;
      F14 = F12 - F14;
      F15 = F15 + F15;
      R12 = 0x7ef311c7;
      R13 = R12 - R14;
      F12 = F14 * F13;
      F12 = F13 * F12;
      F13 = F13 + F13;
      F13 = F13 - F12;
      F12 = F14 * F13;
      F12 = F13 * F12;
      F13 = F13 + F13;
      F13 = F13 - F12;
      F12 = F14 * F13;
      F12 = F13 * F12;
      F13 = F13 + F13;
      F13 = F13 - F12;
      F15 = F15 * F13;
      JUMP (M14, I12);
.GLOBAL wr_a2f_sub_a2rc.;
wr_a2f_sub_a2rc.:
      R12 = 0x7ef311c7;
      R14 = R12 - R15;
      F12 = F15 * F14;
      F12 = F14 * F12;
      F14 = F14 + F14;
      F14 = F14 - F12;
      F12 = F15 * F14;
      F12 = F14 * F12;
      F14 = F14 + F14;
      F14 = F14 - F12;
      F12 = F15 * F14;
      F12 = F14 * F12;
      F14 = F14 + F14;
      F14 = F14 - F12;
      F15 = PASS F14;
      JUMP (M14, I12);
.GLOBAL wr_a2f_sub_a2th.;
wr_a2f_sub_a2th.:
      R12 = 0x40400000;                 // 3.0
      COMP(F15, F12);
      IF LE JUMP 0xbd9c90;                   // -> wr_a2f_else_98.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_98.;
wr_a2f_else_98.:
      F15 = MIN(F15, F12);
      R12 = -0x3fc00000;                // -3.0
      COMP(F15, F12);
      IF GE JUMP 0xbd9c9c;                   // -> wr_a2f_else_99.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_99.;
wr_a2f_else_99.:
      F15 = MAX(F15, F12);
      F13 = F15 * F15;
      R12 = 0x41100000;                 // 9.0
      F14 = F12 * F13;
      R12 = 0x41d80000;                 // 27.0
      F14 = F12 + F14;
      F13 = F12 + F13;
      F13 = F15 * F13;
      R12 = 0x7ef311c7;
      R15 = R12 - R14;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F15 = F13 * F15;
      JUMP (M14, I12);
.GLOBAL wr_a2f_sub_a2lad.;
wr_a2f_sub_a2lad.:
      R0 = DM(0x2ddaa4);                // mode
      R8 = 0x2ddc2c;
      R2 = LSHIFT R0 BY 2;
      R8 = R8 + R2;
      R2 = LSHIFT R0 BY 4;
      R8 = R8 + R2;
      I3 = R8;
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      R1 = DM(0, I2);
      R2 = DM(1, I2);
      R3 = DM(2, I2);
      R4 = DM(3, I2);
      R5 = DM(0x2ddae8);                // G
      R6 = DM(0x2ddaec);                // H
      R7 = DM(0x2ddabc);                // k
      R0 = DM(0x2ddaac);                // buf
      I0 = R0;
      I2 = 0x2ddae8;
      R8 = 0x2ddb48;
      I1 = R8;
      R10 = DM(0x2ddaf4);               // ota
      R10 = PASS R10;
      IF EQ JUMP 0xbd9d99;                   // -> wr_a2f_else_100.
      R11 = 0x10;
.GLOBAL wr_a2f_loop_101.;
wr_a2f_loop_101.:
      F0 = DM(0, I0);
      F8 = DM(-2, I2);
      F0 = F0 * F8, F10 = DM(-1, I2);
      F8 = F5 * F1, F12 = DM(0, I1);
      F8 = F8 + F2;
      F8 = F5 * F8;
      F8 = F8 + F3;
      F8 = F5 * F8;
      F8 = F8 + F4;
      F8 = F6 * F8;
      F9 = F7 * F8;
      F9 = F0 - F9;
      F9 = F9 * F10, F10 = DM(2, I2);
      F15 = F10 * F9;
      F15 = F15 + F8;
      COMP(F15, F12);
      IF LE JUMP 0xbd9d29;                   // -> wr_a2f_else_102.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_102.;
wr_a2f_else_102.:
      F15 = MIN(F15, F12), F12 = DM(1, I1);
      COMP(F15, F12);
      IF GE JUMP 0xbd9d33;                   // -> wr_a2f_else_103.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_103.;
wr_a2f_else_103.:
      F15 = MAX(F15, F12), F12 = DM(2, I1);
      F13 = F15 * F15;
      F14 = F12 * F13, F12 = DM(3, I1);
      F14 = F12 + F14;
      F13 = F12 + F13, F12 = DM(4, I1);
      F13 = F15 * F13;
      R15 = R12 - R14;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12, F12 = DM(1, I3);
      F15 = F13 * F15;
      F15 = F7 * F15;
      F15 = F0 - F15;
      F9 = F15 - F1;
      F9 = F9 * F5;
      F8 = F9 + F1;
      F1 = F8 + F9;
      F9 = F8 - F2;
      F9 = F9 * F5;
      F13 = F9 + F2;
      F2 = F13 + F9;
      F9 = F13 - F3;
      F9 = F9 * F5;
      F14 = F9 + F3;
      F3 = F14 + F9;
      F9 = F14 - F4;
      F9 = F9 * F5;
      F10 = F9 + F4;
      F4 = F10 + F9, F9 = DM(0, I3);
      F9 = F9 * F15;
      F12 = F12 * F8;
      F9 = F9 + F12, F12 = DM(2, I3);
      F12 = F12 * F13;
      F9 = F9 + F12, F12 = DM(3, I3);
      F12 = F12 * F14;
      F9 = F9 + F12, F12 = DM(4, I3);
      F12 = F12 * F10;
      F9 = F9 + F12, F12 = DM(5, I1);
      F9 = MIN(F9, F12), F12 = DM(6, I1);
      F9 = MAX(F9, F12);
      DM(I0, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd9d05;                   // -> wr_a2f_loop_101.
      JUMP 0xbd9e25;                         // -> wr_a2f_fi_104.
.GLOBAL wr_a2f_else_100.;
wr_a2f_else_100.:
      R11 = 0x10;
.GLOBAL wr_a2f_loop_105.;
wr_a2f_loop_105.:
      F0 = DM(0, I0);
      F8 = DM(-2, I2);
      F0 = F0 * F8, F10 = DM(-1, I2);
      F8 = F5 * F1, F12 = DM(0, I1);
      F8 = F8 + F2;
      F8 = F5 * F8;
      F8 = F8 + F3;
      F8 = F5 * F8;
      F8 = F8 + F4;
      F8 = F6 * F8;
      F9 = F7 * F8;
      F9 = F0 - F9;
      F9 = F9 * F10;
      F15 = PASS F9;
      COMP(F15, F12);
      IF LE JUMP 0xbd9dbc;                   // -> wr_a2f_else_106.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_106.;
wr_a2f_else_106.:
      F15 = MIN(F15, F12), F12 = DM(1, I1);
      COMP(F15, F12);
      IF GE JUMP 0xbd9dc6;                   // -> wr_a2f_else_107.
      DM(0x2de0f8) = R12;
.GLOBAL wr_a2f_else_107.;
wr_a2f_else_107.:
      F15 = MAX(F15, F12), F12 = DM(2, I1);
      F13 = F15 * F15;
      F14 = F12 * F13, F12 = DM(3, I1);
      F14 = F12 + F14;
      F13 = F12 + F13, F12 = DM(4, I1);
      F13 = F15 * F13;
      R15 = R12 - R14;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12;
      F12 = F14 * F15;
      F12 = F15 * F12;
      F15 = F15 + F15;
      F15 = F15 - F12, F12 = DM(1, I3);
      F15 = F13 * F15;
      F9 = F15 - F1;
      F9 = F9 * F5;
      F8 = F9 + F1;
      F1 = F8 + F9;
      F9 = F8 - F2;
      F9 = F9 * F5;
      F13 = F9 + F2;
      F2 = F13 + F9;
      F9 = F13 - F3;
      F9 = F9 * F5;
      F14 = F9 + F3;
      F3 = F14 + F9;
      F9 = F14 - F4;
      F9 = F9 * F5;
      F10 = F9 + F4;
      F4 = F10 + F9, F9 = DM(0, I3);
      F9 = F9 * F15;
      F12 = F12 * F8;
      F9 = F9 + F12, F12 = DM(2, I3);
      F12 = F12 * F13;
      F9 = F9 + F12, F12 = DM(3, I3);
      F12 = F12 * F14;
      F9 = F9 + F12, F12 = DM(4, I3);
      F12 = F12 * F10;
      F9 = F9 + F12, F12 = DM(5, I1);
      F9 = MIN(F9, F12), F12 = DM(6, I1);
      F9 = MAX(F9, F12);
      DM(I0, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd9d9b;                   // -> wr_a2f_loop_105.
.GLOBAL wr_a2f_fi_104.;
wr_a2f_fi_104.:
      R0 = DM(0x2ddab0);                // zp
      I2 = R0;
      DM(0, I2) = R1;
      DM(1, I2) = R2;
      DM(2, I2) = R3;
      DM(3, I2) = R4;
      JUMP (M14, I12);
.wr_a2f..end:
      .type wr_a2f.,STT_FUNC;
