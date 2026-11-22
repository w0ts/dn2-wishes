// inspost.asm -- the stereo inserts after the pan, CHOR and WIDE (docs/inserts.md). GENERATED
// by scripts/gen_inserts_asm.py from dnfw.inserts.post; do not edit by hand.

.SECTION/PM seg_pmco;

.GLOBAL wr_inpost.;
wr_inpost.:
      DM(0x2e3fe8) = R0;
      DM(0x2e3fec) = R1;
      DM(0x2e3ff0) = R2;
      DM(0x2e3ff4) = R3;
      DM(0x2e3ff8) = R4;
      DM(0x2e3ffc) = R5;
      DM(0x2e4000) = R6;
      DM(0x2e4004) = R7;
      DM(0x2e4008) = R8;
      DM(0x2e400c) = R9;
      DM(0x2e4010) = R10;
      DM(0x2e4014) = R11;
      DM(0x2e4018) = R12;
      DM(0x2e401c) = R13;
      DM(0x2e4020) = R14;
      DM(0x2e4024) = R15;
      DM(0x2e4028) = I0;
      DM(0x2e402c) = I1;
      DM(0x2e4030) = I2;
      DM(0x2e4034) = I3;
      DM(0x2e4038) = I4;
      DM(0x2e403c) = I12;
      DM(0x2e4040) = ASTAT;
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
      IF EQ JUMP 0xbd7eeb;                   // -> wr_ip_isz_1.
      R9 = R9 + R8;                     // no longer to come
.GLOBAL wr_ip_isz_1.;
wr_ip_isz_1.:
      DM(0x2ddff0) = R9;
      R9 = PASS R9;
      IF EQ JUMP 0xbd7f02;                   // -> wr_ip_irz_2.
      R8 = EMUCLK;
      R8 = R9 - R8;                     // the room before this pass's deadline ..
      R9 = DM(0x2de13c);
      R8 = R8 + R9;                     // .. from here, in the frame
      R9 = DM(0x2e1748);
      R8 = MIN(R8, R9);
      DM(0x2e1748) = R8;
.GLOBAL wr_ip_irz_2.;
wr_ip_irz_2.:
      R0 = DM(0x2e3a08);
      R0 = PASS R0;
      IF EQ JUMP 0xbd87bc;                   // -> wr_ip_else_3.
      R0 = 0x0;
      DM(0x2e3f50) = R0;
      R0 = 0x20;
      DM(0x2e3f44) = R0;
.GLOBAL wr_ip_slot_4.;
wr_ip_slot_4.:
      R0 = DM(0x2e3f50);
      R1 = LSHIFT R0 BY -1;
      DM(0x2e3f40) = R1;
      R12 = 0x1;
      R1 = R0 AND R12;
      DM(0x2e3f54) = R1;
      R1 = DM(0x2e3f54);
      R1 = PASS R1;
      IF NE JUMP 0xbd7ff7;                   // -> wr_ip_else_5.
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY 7;
      R2 = LSHIFT R0 BY 4;
      R12 = 0x200b1b00;
      R3 = R12 + R1;
      R12 = PASS R3;
      R3 = R12 + R2;
      I4 = R3;
      R5 = DM(33, I4);
      R6 = 0x3f000000;                  // 0.5
      COMP(F5, F6);
      IF LE JUMP 0xbd7ff3;                   // -> wr_ip_else_6.
      R6 = 0x0;                         // 0.0
      DM(33, I4) = R6;
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY 8;
      R12 = 0x257ee8;
      R1 = R12 + R1;
      I0 = R1;
      I2 = R1;
      R12 = 0x80;
      R1 = R12 + R1;
      I1 = R1;
      I3 = R1;
      R7 = 0x0;                         // 0.0
      R0 = 0x20;
      DM(0x2e4044) = R0;
.GLOBAL wr_ip_loop_7.;
wr_ip_loop_7.:
      R8 = DM(I0, M6);
      R9 = DM(I1, M6);
      F8 = F8 + F9;
      R10 = 0x0;                        // 0.0
      F10 = F10 - F8;
      F8 = MAX(F8, F10);
      F7 = F7 + F8;
      R0 = DM(0x2e4044);
      R0 = R0 - 1;
      DM(0x2e4044) = R0;
      IF NE JUMP 0xbd7f68;                   // -> wr_ip_loop_7.
      R12 = 0x3f000000;                 // 0.5
      F7 = F7 * F12;
      R6 = DM(32, I4);
      R12 = 0x3089705f;                 // 9.999999717180685e-10
      F6 = MAX(F6, F12);
      R12 = 0x7ef311c7;
      R8 = R12 - R6;
      F13 = F6 * F8;
      R12 = 0x40000000;                 // 2.0
      F13 = F12 - F13;
      F8 = F8 * F13;
      F13 = F6 * F8;
      F13 = F12 - F13;
      F8 = F8 * F13;
      F13 = F6 * F8;
      F13 = F12 - F13;
      F8 = F8 * F13;
      F7 = F7 * F8;
      R12 = 0x40800000;                 // 4.0
      F7 = MIN(F7, F12);
      R9 = DM(34, I4);
      DM(34, I4) = R7;
      F10 = F7 - F9;
      R12 = 0x3d000000;                 // 0.03125
      F10 = F10 * F12;
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY 8;
      R12 = 0x257ee8;
      R1 = R12 + R1;
      I0 = R1;
      I2 = R1;
      R12 = 0x80;
      R1 = R12 + R1;
      I1 = R1;
      I3 = R1;
      R1 = DM(0x2e3f40);
      R2 = LSHIFT R1 BY 7;
      R3 = LSHIFT R1 BY 4;
      R12 = 0x200b1b00;
      R2 = R12 + R2;
      R12 = PASS R2;
      R2 = R12 + R3;
      I4 = R2;
      R0 = 0x20;
      DM(0x2e4044) = R0;
.GLOBAL wr_ip_loop_8.;
wr_ip_loop_8.:
      F9 = F9 + F10;
      R5 = DM(I4, M6);
      F5 = F5 * F9, R6 = DM(I0, M6);
      F6 = F6 + F5;
      DM(I2, M6) = F6;
      R6 = DM(I1, M6);
      F6 = F6 - F5;
      DM(I3, M6) = F6;
      R0 = DM(0x2e4044);
      R0 = R0 - 1;
      DM(0x2e4044) = R0;
      IF NE JUMP 0xbd7fdc;                   // -> wr_ip_loop_8.
      JUMP 0xbd7ff7;                         // -> wr_ip_fi_9.
.GLOBAL wr_ip_else_6.;
wr_ip_else_6.:
      R6 = 0x0;                         // 0.0
      DM(34, I4) = R6;
.GLOBAL wr_ip_fi_9.;
wr_ip_fi_9.:
.GLOBAL wr_ip_else_5.;
wr_ip_else_5.:
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY -1;
      R1 = LSHIFT R1 BY 2;
      R12 = 0x257898;
      R2 = R12 + R1;
      I4 = R2;
      R3 = DM(0, I4);
      R12 = 0x1;
      R1 = R0 AND R12;
      R1 = PASS R1;
      IF EQ JUMP 0xbd8014;                   // -> wr_ip_else_10.
      R3 = LSHIFT R3 BY -16;
.GLOBAL wr_ip_else_10.;
wr_ip_else_10.:
      R12 = 0xffff;
      R3 = R3 AND R12;
      DM(0x2e3f48) = R3;
      R5 = 0x0;
      R3 = DM(0x2e3f48);
      R12 = 0xf;
      COMP(R3, R12);
      IF GT JUMP 0xbd8045;                   // -> wr_ip_else_11.
      R0 = DM(0x2e3f48);
      R1 = LSHIFT R0 BY 6;
      R0 = DM(0x2e3f54);
      R0 = LSHIFT R0 BY 5;
      R12 = PASS R1;
      R1 = R12 + R0;
      R12 = 0x2e3600;
      R2 = R12 + R1;
      DM(0x2e3f58) = R2;
      I4 = R2;
      R3 = DM(0, I4);
      R12 = 0xf;
      R5 = R3 AND R12;
.GLOBAL wr_ip_else_11.;
wr_ip_else_11.:
      DM(0x2e3f4c) = R5;
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY 2;
      R12 = 0x2e0e44;
      R1 = R12 + R1;
      I4 = R1;
      R0 = DM(0, I4);
      R0 = LSHIFT R0 BY 7;
      R0 = LSHIFT R0 BY -31;
      R0 = PASS R0;
      IF EQ JUMP 0xbd8066;                   // -> wr_ip_else_12.
      R1 = 0x0;
      DM(0x2e3f4c) = R1;
.GLOBAL wr_ip_else_12.;
wr_ip_else_12.:
      R5 = DM(0x2e3f4c);
      R12 = 0xf;
      R6 = MIN(R5, R12);
      R7 = 0x1;
      F7 = FLOAT R7 BY R6;
      R7 = TRUNC F7;
      R12 = 0x2030;
      R7 = R7 AND R12;
      R7 = PASS R7;
      IF EQ JUMP 0xbd8794;                   // -> wr_ip_else_13.
      R0 = DM(0x2e3f50);
      R1 = LSHIFT R0 BY 5;
      R12 = 0x2e3a40;
      R2 = R12 + R1;
      DM(0x2e3f5c) = R2;
      R8 = LSHIFT R0 BY 12;
      R9 = LSHIFT R0 BY 4;
      R8 = R8 + R9;
      R12 = -0x7daefff4;
      R1 = R12 + R8;
      DM(0x2e3f60) = R1;
      R12 = 0x200a7440;
      R1 = R12 + R9;
      DM(0x200a7640) = R1;
      R0 = DM(0x2e3f40);
      R1 = LSHIFT R0 BY 8;
      R12 = 0x257ee8;
      R1 = R12 + R1;
      DM(0x2e3f64) = R1;
      R12 = 0x80;
      R1 = R12 + R1;
      DM(0x2e3f68) = R1;
      R2 = DM(0x2e3f5c);
      I4 = R2;
      R7 = DM(7, I4);
      R6 = DM(6, I4);
      R5 = DM(0x2e3f4c);
      R8 = DM(0x2e3f48);
      R9 = 0x0;
      COMP(R7, R5);
      IF EQ JUMP 0xbd80cb;                   // -> wr_ip_else_14.
      R9 = 0x1;
.GLOBAL wr_ip_else_14.;
wr_ip_else_14.:
      COMP(R6, R8);
      IF EQ JUMP 0xbd80d1;                   // -> wr_ip_else_15.
      R9 = 0x1;
.GLOBAL wr_ip_else_15.;
wr_ip_else_15.:
      R9 = PASS R9;
      IF EQ JUMP 0xbd8107;                   // -> wr_ip_else_16.
      R2 = DM(0x2e3f5c);
      I4 = R2;
      R9 = 0x0;
      DM(0, I4) = R9;
      DM(1, I4) = R9;
      DM(2, I4) = R9;
      DM(3, I4) = R9;
      DM(4, I4) = R9;
      DM(5, I4) = R9;
      R8 = DM(0x2e3f48);
      R5 = DM(0x2e3f4c);
      DM(6, I4) = R8;
      DM(7, I4) = R5;
      R2 = DM(0x200a7640);
      I4 = R2;
      DM(0, I4) = R9;
      DM(1, I4) = R9;
      DM(2, I4) = R9;
      DM(3, I4) = R9;
      R12 = 0xbd8106;                        // return address - 1: wr_ip_ret_17. - 1
      I12 = R12;
      JUMP 0xbd8b2d;                         // -> wr_ip_sub_ring0.
.GLOBAL wr_ip_ret_17.;
wr_ip_ret_17.:
.GLOBAL wr_ip_else_16.;
wr_ip_else_16.:
      R2 = DM(0x2e3f5c);
      I4 = R2;
      R8 = DM(0, I4);
      DM(0x2e3f88) = R8;
      R8 = DM(1, I4);
      DM(0x2e3f8c) = R8;
      R8 = DM(2, I4);
      DM(0x2e3f90) = R8;
      R8 = DM(3, I4);
      DM(0x2e3f94) = R8;
      R8 = DM(4, I4);
      DM(0x2e3f98) = R8;
      R8 = DM(5, I4);
      DM(0x2e3f9c) = R8;
      R2 = DM(0x2e3f58);
      R12 = 0x4;
      R2 = R12 + R2;
      I4 = R2;
      R2 = 0x2e3f6c;
      I1 = R2;
      R11 = 0x7;
.GLOBAL wr_ip_loop_18.;
wr_ip_loop_18.:
      R8 = DM(I4, M6);
      F8 = FLOAT R8;
      R9 = 0x3c010204;                  // 0.007874015718698502
      F8 = F8 * F9;
      DM(I1, M6) = F8;
      R11 = R11 - 1;
      IF NE JUMP 0xbd813a;                   // -> wr_ip_loop_18.
      R5 = DM(0x2e3f4c);
      R6 = 0x5;
      COMP(R5, R6);
      IF NE JUMP 0xbd8157;                   // -> wr_ip_else_19.
      R1 = 0x125c;
      DM(0x200a7644) = R1;
      JUMP 0xbd816d;                         // -> wr_ip_fi_20.
.GLOBAL wr_ip_else_19.;
wr_ip_else_19.:
      R5 = DM(0x2e3f4c);
      R6 = 0xd;
      COMP(R5, R6);
      IF NE JUMP 0xbd8168;                   // -> wr_ip_else_21.
      R1 = 0x1644;
      DM(0x200a7644) = R1;
      JUMP 0xbd816d;                         // -> wr_ip_fi_22.
.GLOBAL wr_ip_else_21.;
wr_ip_else_21.:
      R1 = 0x2c88;
      DM(0x200a7644) = R1;
.GLOBAL wr_ip_fi_22.;
wr_ip_fi_22.:
.GLOBAL wr_ip_fi_20.;
wr_ip_fi_20.:
      R2 = DM(0x2e3f64);
      I0 = R2;
      R0 = DM(0, I0);
      DM(0x200a7650) = R0;
      R1 = DM(31, I0);
      DM(0x200a7654) = R1;
      R2 = DM(0x2e3f68);
      I0 = R2;
      R0 = DM(0, I0);
      DM(0x200a7658) = R0;
      R1 = DM(31, I0);
      DM(0x200a765c) = R1;
      R9 = 0x1;
      R10 = DM(0x2ddff0);
      R10 = PASS R10;
      IF EQ JUMP 0xbd81a6;                   // -> wr_ip_else_23.
      R8 = EMUCLK;
      R9 = DM(0x2de13c);
      R8 = R8 - R9;
      R9 = DM(0x200a7644);
      R8 = R8 + R9;
      R9 = 0x1;
      COMP(R8, R10);
      IF LE JUMP 0xbd81a6;                   // -> wr_ip_else_24.
      R9 = 0x0;
.GLOBAL wr_ip_else_24.;
wr_ip_else_24.:
.GLOBAL wr_ip_else_23.;
wr_ip_else_23.:
      R2 = DM(0x200a7640);
      I4 = R2;
      R3 = DM(2, I4);
      R9 = PASS R9;
      IF EQ JUMP 0xbd81c7;                   // -> wr_ip_else_25.
      R0 = 0x0;
      R3 = PASS R3;
      IF EQ JUMP 0xbd81c4;                   // -> wr_ip_else_26.
      R12 = 0x1;
      R3 = R3 - R12;
      DM(2, I4) = R3;
      R0 = 0x3;
      R3 = PASS R3;
      IF NE JUMP 0xbd81c4;                   // -> wr_ip_else_27.
      R0 = 0x1;
.GLOBAL wr_ip_else_27.;
wr_ip_else_27.:
.GLOBAL wr_ip_else_26.;
wr_ip_else_26.:
      JUMP 0xbd81d3;                         // -> wr_ip_fi_28.
.GLOBAL wr_ip_else_25.;
wr_ip_else_25.:
      R0 = 0x3;
      R3 = PASS R3;
      IF NE JUMP 0xbd81cf;                   // -> wr_ip_else_29.
      R0 = 0x2;
.GLOBAL wr_ip_else_29.;
wr_ip_else_29.:
      R3 = 0x40;
      DM(2, I4) = R3;
.GLOBAL wr_ip_fi_28.;
wr_ip_fi_28.:
      DM(0x200a7648) = R0;
      R1 = 0x2;
      COMP(R0, R1);
      IF LT JUMP 0xbd820d;                   // -> wr_ip_else_30.
      R8 = DM(0x2de0f4);
      R9 = 0x1;
      R8 = R8 + R9;
      DM(0x2de0f4) = R8;
      R1 = 0xe;
      R2 = 0x2;
      COMP(R0, R2);
      IF NE JUMP 0xbd81f0;                   // -> wr_ip_else_31.
      R1 = DM(0x2e3f4c);
.GLOBAL wr_ip_else_31.;
wr_ip_else_31.:
      R2 = 0x4;
      COMP(R0, R2);
      IF NE JUMP 0xbd81f8;                   // -> wr_ip_else_32.
      R1 = 0xf;
.GLOBAL wr_ip_else_32.;
wr_ip_else_32.:
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
.GLOBAL wr_ip_else_30.;
wr_ip_else_30.:
      R0 = DM(0x200a7648);
      R1 = 0x2;
      COMP(R0, R1);
      IF GE JUMP 0xbd86b8;                   // -> wr_ip_else_33.
      R0 = DM(0x200a7648);
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbd823b;                   // -> wr_ip_else_34.
      R0 = 0x0;
      DM(0x2e3f88) = R0;
      DM(0x2e3f8c) = R0;
      DM(0x2e3f90) = R0;
      DM(0x2e3f94) = R0;
      DM(0x2e3f98) = R0;
      DM(0x2e3f9c) = R0;
      R12 = 0xbd823a;                        // return address - 1: wr_ip_ret_35. - 1
      I12 = R12;
      JUMP 0xbd8b2d;                         // -> wr_ip_sub_ring0.
.GLOBAL wr_ip_ret_35.;
wr_ip_ret_35.:
.GLOBAL wr_ip_else_34.;
wr_ip_else_34.:
      R5 = DM(0x2e3f4c);
      R6 = 0x5;
      COMP(R5, R6);
      IF NE JUMP 0xbd83d4;                   // -> wr_ip_else_36.
      R0 = DM(0x2e3f70);
      R1 = 0x40000000;                  // 2.0
      F0 = F0 * F1;
      DM(0x2e3fa0) = R0;
      R0 = DM(0x2e3f74);
      R1 = 0x446a0000;                  // 936.0
      F0 = F0 * F1;
      R1 = 0x41c00000;                  // 24.0
      F0 = F0 + F1;
      R0 = TRUNC F0;
      DM(0x2e3fa4) = R0;
      R0 = DM(0x2e3f78);
      R1 = 0x40800000;                  // 4.0
      F0 = F0 * F1;
      I12 = 0xbd826a;                        // return address - 1: wr_ip_ret_37. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_37.;
wr_ip_ret_37.:
      R1 = -0x44087903;                 // -0.0075539336539804935
      F0 = F0 * F1;
      I12 = 0xbd8274;                        // return address - 1: wr_ip_ret_38. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_38.;
wr_ip_ret_38.:
      R1 = 0x3f800000;                  // 1.0
      F0 = F1 - F0;
      DM(0x2e3fa8) = R0;
      R0 = DM(0x2e3f7c);
      R1 = 0x40aa4d3c;                  // 5.321928024291992
      F0 = F0 * F1;
      I12 = 0xbd8289;                        // return address - 1: wr_ip_ret_39. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_39.;
wr_ip_ret_39.:
      R1 = -0x4297f173;                 // -0.05665450170636177
      F0 = F0 * F1;
      I12 = 0xbd8293;                        // return address - 1: wr_ip_ret_40. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_40.;
wr_ip_ret_40.:
      R1 = 0x3f800000;                  // 1.0
      F0 = F1 - F0;
      DM(0x2e3fac) = R0;
      R9 = DM(0x2e3f88);
      R13 = DM(0x2e3f60);
      R8 = R9 + 1;
      R12 = 0x3ff;
      R8 = R8 AND R12;
      R8 = LSHIFT R8 BY 2;
      R8 = R13 + R8;
      I2 = R8;
      R12 = 0x20;
      R7 = R12 + R9;
      R12 = 0x3ff;
      R7 = R7 AND R12;
      DM(0x2e3f88) = R7;
      R7 = LSHIFT R7 BY 2;
      R7 = R13 + R7;
      R12 = 0x1;
      R15 = R12 + R9;
      R15 = LSHIFT R15 BY 2;
      R8 = DM(0x2e3fa4);
      R8 = LSHIFT R8 BY 2;
      R15 = R15 - R8;
      R4 = DM(0x2e3f64);
      I0 = R4;
      R4 = DM(0x2e3f68);
      I1 = R4;
      R4 = 0x2e3ec0;
      I3 = R4;
      R4 = 0x3f000000;                  // 0.5
      R5 = DM(0x2e3fa0);
      R11 = 0x7;
.GLOBAL wr_ip_loop_41.;
wr_ip_loop_41.:
      R8 = DM(I0, M6);
      R12 = DM(I1, M6);
      F2 = F8 - F12;
      F2 = F2 * F4, F10 = F8 + F12;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F10 = F10 * F4;
      F6 = F2 * F5, DM(I2, M6) = F10;
      DM(-32, I3) = R10;
      DM(I3, M6) = F6;
      R11 = R11 - 1;
      IF NE JUMP 0xbd82e1;                   // -> wr_ip_loop_41.
      R8 = DM(I0, M6);
      R12 = DM(I1, M6);
      F2 = F8 - F12;
      F2 = F2 * F4, F10 = F8 + F12;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F6 = F2 * F5, F8 = DM(I0, M6);
      F10 = F10 * F4, F12 = DM(I1, M6);
      F2 = F8 - F12, DM(I2, M6) = F10;
      F2 = F2 * F4, DM(-32, I3) = F10;
      F10 = F8 + F12, DM(I3, M6) = F6;
      F10 = F10 * F4;
      I2 = R7;
      F6 = F2 * F5, DM(I2, M6) = F10;
      DM(-32, I3) = R10;
      DM(I3, M6) = F6;
      R4 = DM(0x2e3f64);
      I0 = R4;
      R4 = DM(0x2e3f68);
      I1 = R4;
      R4 = 0x2e3e40;
      I2 = R4;
      R4 = 0x2e3ec0;
      I3 = R4;
      R14 = 0xffc;
      R8 = R15 AND R14;
      R9 = R13 + R8;
      I4 = R9;
      R15 = PASS R13;
      R12 = 0x1000;
      R13 = R12 - R8;
      R13 = LSHIFT R13 BY -2;
      R12 = 0x20;
      R13 = MIN(R13, R12);
      R14 = R12 - R13;
      R0 = DM(0x2e3f6c);
      R3 = DM(0x2e3fa8);
      R4 = DM(0x2e3fac);
      R5 = DM(0x2e3f70);
      R6 = DM(0x2e3f8c);
      R7 = DM(0x2e3f90);
      R10 = 0x2;
.GLOBAL wr_ip_loop_42.;
wr_ip_loop_42.:
      R11 = PASS R13;
      R11 = PASS R11;
      IF EQ JUMP 0xbd83c4;                   // -> wr_ip_else_43.
.GLOBAL wr_ip_loop_44.;
wr_ip_loop_44.:
      R8 = DM(I4, M6);
      F9 = F8 - F6;
      F9 = F9 * F3;
      F6 = F6 + F9;
      F8 = F8 - F6;
      F8 = F8 - F7;
      F8 = F8 * F4;
      F7 = F7 + F8;
      F9 = F7 * F5, R1 = DM(I3, M6);
      F1 = F1 + F9, R2 = DM(I2, M6);
      F8 = F2 + F1;
      F9 = F2 - F1, R12 = DM(0, I0);
      F8 = F8 - F12;
      F8 = F8 * F0;
      F8 = F12 + F8, R12 = DM(0, I1);
      F9 = F9 - F12, DM(I0, M6) = F8;
      F9 = F9 * F0;
      F9 = F12 + F9;
      DM(I1, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd83a0;                   // -> wr_ip_loop_44.
.GLOBAL wr_ip_else_43.;
wr_ip_else_43.:
      I4 = R15;
      R13 = PASS R14;
      R10 = R10 - 1;
      IF NE JUMP 0xbd839b;                   // -> wr_ip_loop_42.
      DM(0x2e3f8c) = R6;
      DM(0x2e3f90) = R7;
      JUMP 0xbd86b8;                         // -> wr_ip_fi_45.
.GLOBAL wr_ip_else_36.;
wr_ip_else_36.:
      R5 = DM(0x2e3f4c);
      R6 = 0xd;
      COMP(R5, R6);
      IF NE JUMP 0xbd83e6;                   // -> wr_ip_else_46.
      I12 = 0xbd83e2;                        // return address - 1: wr_ip_jret_47. - 1
      JUMP 0xbd8824;                         // -> wr_ip_juno.
.GLOBAL wr_ip_jret_47.;
wr_ip_jret_47.:
      JUMP 0xbd86b8;                         // -> wr_ip_fi_48.
.GLOBAL wr_ip_else_46.;
wr_ip_else_46.:
      R0 = DM(0x2e3f7c);
      R1 = 0x407f5c29;                  // 3.990000009536743
      F0 = F0 * F1;
      R0 = TRUNC F0;
      R0 = R0 + 1;
      DM(0x2e3fb0) = R0;
      R1 = -0x1;
      F0 = FLOAT R0 BY R1;
      R12 = 0xbd83fe;                        // return address - 1: wr_ip_ret_49. - 1
      I12 = R12;
      JUMP 0xbd8b7e;                         // -> wr_ip_sub_recip.
.GLOBAL wr_ip_ret_49.;
wr_ip_ret_49.:
      DM(0x2e3fc4) = R0;
      R0 = DM(0x2e3f74);
      R1 = 0x40d49a78;                  // 6.643856048583984
      F0 = F0 * F1;
      I12 = 0xbd840e;                        // return address - 1: wr_ip_ret_50. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_50.;
wr_ip_ret_50.:
      R1 = 0x480bcf65;                  // 143165.578125
      F0 = F0 * F1;
      R0 = TRUNC F0;
      R8 = DM(0x2e3f88);
      DM(0x2e3fc8) = R8;
      R0 = R8 + R0;
      DM(0x2e3f88) = R0;
      R0 = DM(0x2e3f78);
      R1 = 0x43f00000;                  // 480.0
      F0 = F0 * F1;
      R1 = 0x43700000;                  // 240.0
      F0 = F0 + F1;
      DM(0x2e3fb8) = R0;
      R0 = DM(0x2e3f70);
      R1 = 0x43400000;                  // 192.0
      F0 = F0 * F1;
      DM(0x2e3fbc) = R0;
      R0 = DM(0x2e3f84);
      R1 = -0x3f5e1d8b;                 // -5.05889368057251
      F0 = F0 * F1;
      I12 = 0xbd8444;                        // return address - 1: wr_ip_ret_51. - 1
      JUMP 0xbd8b44;                         // -> wr_ip_sub_exp2.
.GLOBAL wr_ip_ret_51.;
wr_ip_ret_51.:
      R1 = 0x3f7ffffe;                  // 0.9999998807907104
      F0 = F1 - F0;
      DM(0x2e3fc0) = R0;
      R8 = DM(0x2e3f60);
      R12 = 0xffc;
      R9 = R8 + R12;
      I2 = R9;
      R9 = DM(0, I2);
      I2 = R8;
      DM(-1, I2) = R9;
      R4 = 0x2e3e40;
      I0 = R4;
      R0 = 0x0;                         // 0.0
      R11 = 0x8;
.GLOBAL wr_ip_loop_52.;
wr_ip_loop_52.:
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8465;                   // -> wr_ip_loop_52.
      R0 = 0x0;
      DM(0x2e3fcc) = R0;
      R10 = DM(0x2e3fb0);
.GLOBAL wr_ip_loop_53.;
wr_ip_loop_53.:
      R0 = DM(0x2e3fcc);
      R0 = LSHIFT R0 BY 30;
      R12 = DM(0x2e3fc8);
      R0 = R12 + R0;
      R12 = 0xbd848b;                        // return address - 1: wr_ip_ret_54. - 1
      I12 = R12;
      JUMP 0xbd8b98;                         // -> wr_ip_sub_sine.
.GLOBAL wr_ip_ret_54.;
wr_ip_ret_54.:
      R1 = DM(0x2e3fbc);
      F0 = F0 * F1;
      R1 = DM(0x2e3fb8);
      F0 = F0 + F1;
      DM(0x2e3fd0) = R0;
      R0 = DM(0x2e3fcc);
      R0 = LSHIFT R0 BY 30;
      R12 = DM(0x2e3f88);
      R0 = R12 + R0;
      R12 = 0xbd84a9;                        // return address - 1: wr_ip_ret_55. - 1
      I12 = R12;
      JUMP 0xbd8b98;                         // -> wr_ip_sub_sine.
.GLOBAL wr_ip_ret_55.;
wr_ip_ret_55.:
      R1 = DM(0x2e3fbc);
      F0 = F0 * F1;
      R1 = DM(0x2e3fb8);
      F0 = F0 + F1;
      DM(0x2e3fd8) = R0;
      R1 = DM(0x2e3fd0);
      DM(0x2e3fd4) = R1;
      R0 = DM(0x2e3fd8);
      F0 = F0 - F1;
      R1 = 0x3d000000;                  // 0.03125
      F0 = F0 * F1;
      DM(0x2e3fd8) = R0;
      R5 = 0x3f000000;                  // 0.5
      R0 = DM(0x2e3fcc);
      R1 = 0x1;
      R0 = R0 AND R1;
      R0 = PASS R0;
      IF EQ JUMP 0xbd84d6;                   // -> wr_ip_else_56.
      R5 = -0x41000000;                 // -0.5
.GLOBAL wr_ip_else_56.;
wr_ip_else_56.:
      R0 = DM(0x2e3fb0);
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbd84e1;                   // -> wr_ip_else_57.
      R5 = 0x0;                         // 0.0
.GLOBAL wr_ip_else_57.;
wr_ip_else_57.:
      R1 = DM(0x2e3f80);
      F5 = F1 * F5;
      R4 = DM(0x2e3fc4);
      R1 = 0x3f000000;                  // 0.5
      F2 = F1 + F5;
      F2 = F2 * F4;
      DM(0x2e3fdc) = R2;
      F2 = F1 - F5;
      F2 = F2 * F4;
      DM(0x2e3fe0) = R2;
      R7 = DM(0x2e3f8c);
      R7 = R7 + 1;
      DM(0x2e3fe4) = R7;
      R4 = 0x2e3e40;
      I0 = R4;
      R4 = 0x2e3ec0;
      I1 = R4;
      R0 = DM(0x2e3fd4);
      R1 = DM(0x2e3fd8);
      R2 = DM(0x2e3fdc);
      R3 = DM(0x2e3fe0);
      R6 = DM(0x2e3f60);
      R7 = 0x4;
      R15 = DM(0x2e3fe4);
      R15 = LSHIFT R15 BY 2;
      I12 = 0xbd8525;                        // return address - 1: wr_ip_ret_58. - 1
      JUMP 0xbd8bd4;                         // -> wr_ip_sub_span.
.GLOBAL wr_ip_ret_58.;
wr_ip_ret_58.:
      R15 = R15 + R6;
      R11 = 0x8;
.GLOBAL wr_ip_loop_59.;
wr_ip_loop_59.:
      F0 = F0 + F1, F14 = DM(0, I0);
      R4 = TRUNC F0;
      R8 = LSHIFT R4 BY 2;
      R8 = R15 - R8;
      I2 = R8;
      F12 = FLOAT R4, R13 = DM(0, I2);
      F8 = F0 - F12, F5 = DM(-1, I2);
      F5 = F5 - F13;
      F12 = F5 * F8;
      F4 = F13 + F12, F8 = DM(0, I1);
      F12 = F4 * F3;
      F9 = F2 * F4, F8 = F8 + F12;
      F0 = F0 + F1, DM(I1, M6) = F8;
      R4 = TRUNC F0;
      R15 = R15 + R7;
      R8 = LSHIFT R4 BY 2;
      R8 = R15 - R8;
      I2 = R8;
      F12 = FLOAT R4, R13 = DM(0, I2);
      F8 = F0 - F12, F5 = DM(-1, I2);
      F5 = F5 - F13;
      F12 = F5 * F8;
      F4 = F13 + F12, F8 = DM(0, I1);
      F12 = F3 * F4, F14 = F9 + F14;
      F9 = F2 * F4, F8 = F8 + F12, DM(I0, M6) = F14;
      F0 = F0 + F1, F14 = DM(0, I0);
      R4 = TRUNC F0, DM(I1, M6) = F8;
      R15 = R15 + R7;
      R8 = LSHIFT R4 BY 2;
      R8 = R15 - R8;
      I2 = R8;
      F12 = FLOAT R4, R13 = DM(0, I2);
      F8 = F0 - F12, F5 = DM(-1, I2);
      F5 = F5 - F13;
      F12 = F5 * F8;
      F4 = F13 + F12, F8 = DM(0, I1);
      F12 = F3 * F4, F14 = F9 + F14;
      F9 = F2 * F4, F8 = F8 + F12, DM(I0, M6) = F14;
      F0 = F0 + F1, F14 = DM(0, I0);
      R4 = TRUNC F0, DM(I1, M6) = F8;
      R15 = R15 + R7;
      R8 = LSHIFT R4 BY 2;
      R8 = R15 - R8;
      I2 = R8;
      F12 = FLOAT R4, R13 = DM(0, I2);
      F8 = F0 - F12, F5 = DM(-1, I2);
      F5 = F5 - F13;
      F12 = F5 * F8;
      F14 = F14 + F9, F8 = DM(0, I1);
      F4 = F13 + F12, DM(I0, M6) = F14;
      F9 = F4 * F2, F14 = DM(0, I0);
      F12 = F3 * F4, F14 = F9 + F14;
      F8 = F8 + F12, DM(I0, M6) = F14;
      R15 = R15 + R7, DM(I1, M6) = F8;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8529;                   // -> wr_ip_loop_59.
      R0 = DM(0x2e3fcc);
      R12 = 0x1;
      R0 = R12 + R0;
      DM(0x2e3fcc) = R0;
      R10 = R10 - 1;
      IF NE JUMP 0xbd8479;                   // -> wr_ip_loop_53.
      R4 = DM(0x2e3f64);
      I0 = R4;
      R4 = DM(0x2e3f68);
      I1 = R4;
      R4 = 0x2e3ec0;
      I3 = R4;
      R9 = DM(0x2e3f8c);
      R13 = DM(0x2e3f60);
      R8 = R9 + 1;
      R12 = 0x3ff;
      R8 = R8 AND R12;
      R8 = LSHIFT R8 BY 2;
      R8 = R13 + R8;
      I2 = R8;
      R12 = 0x20;
      R7 = R12 + R9;
      R12 = 0x3ff;
      R7 = R7 AND R12;
      DM(0x2e3f8c) = R7;
      R7 = LSHIFT R7 BY 2;
      R7 = R13 + R7;
      R6 = DM(0x2e3f6c);
      R4 = 0x3f000000;                  // 0.5
      R5 = DM(0x2e3fc0);
      R11 = 0x7;
.GLOBAL wr_ip_loop_60.;
wr_ip_loop_60.:
      R8 = DM(0, I0);
      R14 = DM(0, I1);
      F3 = F8 + F14, F12 = DM(-32, I3);
      F2 = F12 - F8, F10 = DM(I3, M6);
      F13 = F2 * F6, F1 = F10 + F12;
      F1 = F1 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F15 = F1 * F5, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F8 = DM(0, I0);
      F1 = F14 + F13, F10 = DM(I3, M6);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F13 = F2 * F6, F1 = F10 + F12, F14 = DM(0, I1);
      F9 = F3 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F1 = F1 * F4, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15, F10 = DM(I3, M6);
      F15 = F1 * F5, F3 = F8 + F14, DM(I2, M6) = F9;
      F1 = F14 + F13, F8 = DM(0, I0);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F13 = F2 * F6, F1 = F10 + F12, F14 = DM(0, I1);
      F9 = F3 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F1 = F1 * F4, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15, F10 = DM(I3, M6);
      F15 = F1 * F5, F3 = F8 + F14, DM(I2, M6) = F9;
      F1 = F14 + F13, F8 = DM(0, I0);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F9 = F3 * F4, F1 = F10 + F12, F14 = DM(0, I1);
      F13 = F2 * F6, F9 = F9 + F15;
      F1 = F1 * F4, F3 = F8 + F14, DM(I2, M6) = F9;
      F9 = F3 * F4, F13 = F8 + F13;
      F15 = F1 * F5, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15;
      F1 = F14 + F13, DM(I2, M6) = F9;
      DM(I1, M6) = F1;
      R11 = R11 - 1;
      IF NE JUMP 0xbd85fa;                   // -> wr_ip_loop_60.
      R8 = DM(0, I0);
      R14 = DM(0, I1);
      F3 = F8 + F14, F12 = DM(-32, I3);
      F2 = F12 - F8, F10 = DM(I3, M6);
      F13 = F2 * F6, F1 = F10 + F12;
      F1 = F1 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F15 = F1 * F5, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F8 = DM(0, I0);
      F1 = F14 + F13, F10 = DM(I3, M6);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F13 = F2 * F6, F1 = F10 + F12, F14 = DM(0, I1);
      F9 = F3 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F1 = F1 * F4, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15, F10 = DM(I3, M6);
      F15 = F1 * F5, F3 = F8 + F14, DM(I2, M6) = F9;
      F1 = F14 + F13, F8 = DM(0, I0);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F13 = F2 * F6, F1 = F10 + F12, F14 = DM(0, I1);
      F9 = F3 * F4, F13 = F8 + F13, F12 = DM(-32, I3);
      F1 = F1 * F4, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15, F10 = DM(I3, M6);
      F15 = F1 * F5, F3 = F8 + F14, DM(I2, M6) = F9;
      F1 = F14 + F13, F8 = DM(0, I0);
      F2 = F12 - F8, DM(I1, M6) = F1;
      F9 = F3 * F4, F1 = F10 + F12, F14 = DM(0, I1);
      F13 = F2 * F6, F9 = F9 + F15;
      F1 = F1 * F4, F3 = F8 + F14, DM(I2, M6) = F9;
      F9 = F3 * F4, F13 = F8 + F13;
      F15 = F1 * F5, F0 = F10 - F14, DM(I0, M6) = F13;
      F13 = F0 * F6, F9 = F9 + F15;
      I2 = R7;
      F1 = F14 + F13, DM(I2, M6) = F9;
      DM(I1, M6) = F1;
.GLOBAL wr_ip_fi_48.;
wr_ip_fi_48.:
.GLOBAL wr_ip_fi_45.;
wr_ip_fi_45.:
.GLOBAL wr_ip_else_33.;
wr_ip_else_33.:
      R0 = DM(0x2e3f64);
      DM(0x200a764c) = R0;
      R2 = DM(0x200a7640);
      I4 = R2;
      R3 = DM(0x200a7648);
      R1 = 0x2;
      COMP(R3, R1);
      IF LT JUMP 0xbd86e8;                   // -> wr_ip_else_61.
      R1 = 0x2;
      COMP(R3, R1);
      IF NE JUMP 0xbd86dc;                   // -> wr_ip_else_62.
      R0 = DM(0, I4);
      R12 = 0xbd86db;                        // return address - 1: wr_ip_ret_63. - 1
      I12 = R12;
      JUMP 0xbd8c5b;                         // -> wr_ip_sub_ins_ramp.
.GLOBAL wr_ip_ret_63.;
wr_ip_ret_63.:
.GLOBAL wr_ip_else_62.;
wr_ip_else_62.:
      R0 = 0x0;                         // 0.0
      R2 = DM(0x200a7640);
      I4 = R2;
      DM(0, I4) = R0;
      JUMP 0xbd8713;                         // -> wr_ip_fi_64.
.GLOBAL wr_ip_else_61.;
wr_ip_else_61.:
      R1 = 0x1;
      COMP(R3, R1);
      IF NE JUMP 0xbd8701;                   // -> wr_ip_else_65.
      R2 = DM(0x200a764c);
      I0 = R2;
      R1 = DM(0, I0);
      R0 = DM(0x200a7650);
      F0 = F0 - F1;
      R12 = 0xbd8700;                        // return address - 1: wr_ip_ret_66. - 1
      I12 = R12;
      JUMP 0xbd8c5b;                         // -> wr_ip_sub_ins_ramp.
.GLOBAL wr_ip_ret_66.;
wr_ip_ret_66.:
.GLOBAL wr_ip_else_65.;
wr_ip_else_65.:
      R2 = DM(0x200a764c);
      I0 = R2;
      R0 = DM(31, I0);
      R1 = DM(0x200a7654);
      F0 = F0 - F1;
      R2 = DM(0x200a7640);
      I4 = R2;
      DM(0, I4) = R0;
.GLOBAL wr_ip_fi_64.;
wr_ip_fi_64.:
      R0 = DM(0x2e3f68);
      DM(0x200a764c) = R0;
      R2 = DM(0x200a7640);
      I4 = R2;
      R3 = DM(0x200a7648);
      R1 = 0x2;
      COMP(R3, R1);
      IF LT JUMP 0xbd8743;                   // -> wr_ip_else_67.
      R1 = 0x2;
      COMP(R3, R1);
      IF NE JUMP 0xbd8737;                   // -> wr_ip_else_68.
      R0 = DM(1, I4);
      R12 = 0xbd8736;                        // return address - 1: wr_ip_ret_69. - 1
      I12 = R12;
      JUMP 0xbd8c5b;                         // -> wr_ip_sub_ins_ramp.
.GLOBAL wr_ip_ret_69.;
wr_ip_ret_69.:
.GLOBAL wr_ip_else_68.;
wr_ip_else_68.:
      R0 = 0x0;                         // 0.0
      R2 = DM(0x200a7640);
      I4 = R2;
      DM(1, I4) = R0;
      JUMP 0xbd876e;                         // -> wr_ip_fi_70.
.GLOBAL wr_ip_else_67.;
wr_ip_else_67.:
      R1 = 0x1;
      COMP(R3, R1);
      IF NE JUMP 0xbd875c;                   // -> wr_ip_else_71.
      R2 = DM(0x200a764c);
      I0 = R2;
      R1 = DM(0, I0);
      R0 = DM(0x200a7658);
      F0 = F0 - F1;
      R12 = 0xbd875b;                        // return address - 1: wr_ip_ret_72. - 1
      I12 = R12;
      JUMP 0xbd8c5b;                         // -> wr_ip_sub_ins_ramp.
.GLOBAL wr_ip_ret_72.;
wr_ip_ret_72.:
.GLOBAL wr_ip_else_71.;
wr_ip_else_71.:
      R2 = DM(0x200a764c);
      I0 = R2;
      R0 = DM(31, I0);
      R1 = DM(0x200a765c);
      F0 = F0 - F1;
      R2 = DM(0x200a7640);
      I4 = R2;
      DM(1, I4) = R0;
.GLOBAL wr_ip_fi_70.;
wr_ip_fi_70.:
      R2 = DM(0x2e3f5c);
      I4 = R2;
      R8 = DM(0x2e3f88);
      DM(0, I4) = R8;
      R8 = DM(0x2e3f8c);
      DM(1, I4) = R8;
      R8 = DM(0x2e3f90);
      DM(2, I4) = R8;
      R8 = DM(0x2e3f94);
      DM(3, I4) = R8;
      R8 = DM(0x2e3f98);
      DM(4, I4) = R8;
      R8 = DM(0x2e3f9c);
      DM(5, I4) = R8;
      JUMP 0xbd87a5;                         // -> wr_ip_fi_73.
.GLOBAL wr_ip_else_13.;
wr_ip_else_13.:
      R0 = DM(0x2e3f50);
      R1 = LSHIFT R0 BY 5;
      R12 = 0x2e3a5c;
      R2 = R12 + R1;
      I4 = R2;
      R0 = 0x0;
      DM(0, I4) = R0;
.GLOBAL wr_ip_fi_73.;
wr_ip_fi_73.:
      R0 = DM(0x2e3f50);
      R12 = 0x1;
      R0 = R12 + R0;
      DM(0x2e3f50) = R0;
      R0 = DM(0x2e3f44);
      R0 = R0 - R12;
      DM(0x2e3f44) = R0;
      IF NE JUMP 0xbd7f13;                   // -> wr_ip_slot_4.
      JUMP 0xbd87cf;                         // -> wr_ip_fi_74.
.GLOBAL wr_ip_else_3.;
wr_ip_else_3.:
      R1 = 0x2e3a5c;
      R0 = 0x0;
      R13 = 0x20;
      R11 = 0x20;
.GLOBAL wr_ip_loop_75.;
wr_ip_loop_75.:
      I4 = R1;
      DM(0, I4) = R0;
      R1 = R13 + R1;
      R11 = R11 - 1;
      IF NE JUMP 0xbd87c5;                   // -> wr_ip_loop_75.
.GLOBAL wr_ip_fi_74.;
wr_ip_fi_74.:
      R8 = EMUCLK;
      R9 = DM(0x2de0f0);
      R8 = R8 - R9;                     // this pass's time
      R9 = DM(0x2de0ec);
      R8 = R8 + R9;
      DM(0x2de0ec) = R8;
      ASTAT = DM(0x2e4040);
      I0 = DM(0x2e4028);
      I1 = DM(0x2e402c);
      I2 = DM(0x2e4030);
      I3 = DM(0x2e4034);
      I4 = DM(0x2e4038);
      I12 = DM(0x2e403c);
      R0 = DM(0x2e3fe8);
      R1 = DM(0x2e3fec);
      R2 = DM(0x2e3ff0);
      R3 = DM(0x2e3ff4);
      R4 = DM(0x2e3ff8);
      R5 = DM(0x2e3ffc);
      R6 = DM(0x2e4000);
      R7 = DM(0x2e4004);
      R8 = DM(0x2e4008);
      R9 = DM(0x2e400c);
      R10 = DM(0x2e4010);
      R11 = DM(0x2e4014);
      R12 = DM(0x2e4018);
      R13 = DM(0x2e401c);
      R14 = DM(0x2e4020);
      R15 = DM(0x2e4024);
      JUMP 0x1c1738;                    // the FX sends, entered as the engine called them
.GLOBAL wr_ip_juno.;
wr_ip_juno.:
      DM(0x2e404c) = I12;
      R0 = DM(0x2e3f70);
      R1 = 0x403e8000;                  // 2.9765625
      F0 = F0 * F1;
      R0 = TRUNC F0;
      R2 = 0x167980;
      R3 = 0x3b4ca038;                  // 0.003122342750430107
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbd8842;                   // -> wr_ip_else_76.
      R2 = 0x24d100;
      R3 = 0x3b2343eb;                  // 0.00249123084358871
.GLOBAL wr_ip_else_76.;
wr_ip_else_76.:
      R1 = 0x2;
      COMP(R0, R1);
      IF NE JUMP 0xbd884e;                   // -> wr_ip_else_77.
      R2 = 0x1573c00;
      R3 = 0x39ae2650;                  // 0.00033216411247849464
.GLOBAL wr_ip_else_77.;
wr_ip_else_77.:
      DM(0x2e3fbc) = R3;
      R8 = DM(0x2e3f88);
      R9 = R8 + R2;
      DM(0x2e3f88) = R9;
      R4 = LSHIFT R8 BY -16;
      R12 = 0x8000;
      R4 = R4 - R12;
      F4 = FLOAT R4;
      F4 = ABS F4;
      R12 = 0x46800000;                 // 16384.0
      F4 = F4 - F12;
      R3 = DM(0x2e3fbc);
      F4 = F4 * F3;
      R5 = 0x4327b51e;                  // 167.70748901367188
      F6 = F5 + F4;
      DM(0x2e3fd4) = R6;
      F7 = F5 - F4;
      DM(0x2e3fd0) = R7;
      R4 = LSHIFT R9 BY -16;
      R12 = 0x8000;
      R4 = R4 - R12;
      F4 = FLOAT R4;
      F4 = ABS F4;
      R12 = 0x46800000;                 // 16384.0
      F4 = F4 - F12;
      R3 = DM(0x2e3fbc);
      F4 = F4 * F3;
      F4 = F5 + F4;
      F4 = F4 - F6;
      R12 = 0x3d000000;                 // 0.03125
      F4 = F4 * F12;
      DM(0x2e3fd8) = R4;
      R12 = 0x0;                        // 0.0
      F4 = F12 - F4;
      DM(0x2e3fc4) = R4;
      R0 = DM(0x2e3f6c);
      R1 = 0x3eb49c00;                  // 0.352752685546875
      F1 = F0 * F1;
      R2 = 0x3f800000;                  // 1.0
      F2 = F2 - F1;
      DM(0x2e3fdc) = R2;
      R1 = 0x3f715800;                  // 0.9427490234375
      F1 = F0 * F1;
      DM(0x2e3fe0) = R1;
      R8 = DM(0x2e3f60);
      R12 = 0xff4;
      R9 = R8 + R12;
      I2 = R9;
      R9 = DM(0, I2);
      R10 = DM(1, I2);
      R13 = DM(2, I2);
      I2 = R8;
      DM(-3, I2) = R9;
      DM(-2, I2) = R10;
      DM(-1, I2) = R13;
      R0 = 0x2e3e40;
      DM(0x2e3fcc) = R0;
      R0 = 0x2;
      DM(0x2e4044) = R0;
.GLOBAL wr_ip_loop_78.;
wr_ip_loop_78.:
      R0 = DM(0x2e3fd4);
      R1 = DM(0x2e3fd8);
      R6 = DM(0x2e3f60);
      R7 = 0x4;
      R15 = DM(0x2e3f8c);
      R15 = R15 + 1;
      R15 = LSHIFT R15 BY 2;
      R4 = DM(0x2e3fcc);
      I0 = R4;
      I12 = 0xbd88f2;                        // return address - 1: wr_ip_ret_79. - 1
      JUMP 0xbd8bd4;                         // -> wr_ip_sub_span.
.GLOBAL wr_ip_ret_79.;
wr_ip_ret_79.:
      R15 = R15 + R6;
      R6 = PASS R0;
      R3 = 0x3f000000;                  // 0.5
      R11 = 0x10;
.GLOBAL wr_ip_loop_80.;
wr_ip_loop_80.:
      F6 = F6 + F1;
      R14 = TRUNC F6;
      R12 = LSHIFT R14 BY 2;
      R4 = R15 - R12;
      I2 = R4;
      F0 = FLOAT R14, R8 = DM(0, I2);
      F2 = F6 - F0, F12 = DM(-1, I2);
      F13 = F8 - F12, F5 = DM(-2, I2);
      F9 = F12 - F5, F10 = DM(-3, I2);
      F4 = F10 - F8;
      F14 = F9 * F3;
      F10 = F3 * F4, F14 = F9 + F14;
      F5 = F5 - F8;
      F5 = F3 * F5, F10 = F10 + F14;
      F14 = F13 + F5;
      F13 = F14 - F10;
      F9 = F10 * F2;
      F8 = F9 + F13;
      F9 = F8 * F2;
      F0 = F9 + F5;
      F6 = F6 + F1;
      F9 = F0 * F2;
      R14 = TRUNC F6;
      F9 = F9 + F12;
      R15 = R15 + R7, DM(I0, M6) = F9;
      R12 = LSHIFT R14 BY 2;
      R4 = R15 - R12;
      I2 = R4;
      F0 = FLOAT R14, R8 = DM(0, I2);
      F2 = F6 - F0, F12 = DM(-1, I2);
      F13 = F8 - F12, F5 = DM(-2, I2);
      F9 = F12 - F5, F10 = DM(-3, I2);
      F4 = F10 - F8;
      F14 = F9 * F3;
      F10 = F3 * F4, F14 = F9 + F14;
      F5 = F5 - F8;
      F5 = F3 * F5, F10 = F10 + F14;
      F14 = F13 + F5;
      F13 = F14 - F10;
      F9 = F10 * F2;
      F8 = F9 + F13;
      F9 = F8 * F2;
      F0 = F9 + F5;
      F9 = F0 * F2;
      F9 = F9 + F12;
      R15 = R15 + R7, DM(I0, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd88fa;                   // -> wr_ip_loop_80.
      R0 = DM(0x2e3fd0);
      DM(0x2e3fd4) = R0;
      R0 = DM(0x2e3fc4);
      DM(0x2e3fd8) = R0;
      R0 = 0x2e3ec0;
      DM(0x2e3fcc) = R0;
      R0 = DM(0x2e4044);
      R0 = R0 - 1;
      DM(0x2e4044) = R0;
      IF NE JUMP 0xbd88d6;                   // -> wr_ip_loop_78.
      R0 = DM(0x2e3f90);
      R14 = DM(0x2e3f94);
      R2 = DM(0x2e3f98);
      R15 = DM(0x2e3f9c);
      R4 = 0x3ec6f621;                  // 0.3885965645313263
      R6 = 0x3e9260dd;                  // 0.2858952581882477
      R7 = 0x3f3c57a3;                  // 0.7357122302055359
      R8 = 0x2e3e40;
      I0 = R8;
      R8 = 0x2e3ec0;
      I1 = R8;
      R11 = 0x8;
.GLOBAL wr_ip_loop_81.;
wr_ip_loop_81.:
      F12 = F0 * F4, F9 = DM(0, I0);
      F8 = F2 * F4, F1 = F9 - F14, F10 = DM(0, I1);
      F9 = F1 * F6, F3 = F10 - F15;
      F13 = F3 * F6, F1 = F9 + F12;
      F9 = F1 * F7, F3 = F8 + F13;
      F8 = F3 * F7, F12 = F9 + F14;
      F9 = F12 + F12, DM(I0, M6) = F12;
      F14 = F9 - F14;
      F9 = F3 + F3;
      F1 = F1 + F1;
      F2 = F9 - F2;
      F0 = F1 - F0, F9 = DM(0, I0);
      F12 = F0 * F4, F1 = F9 - F14;
      F9 = F1 * F6, F5 = F8 + F15;
      F8 = F2 * F4, F1 = F9 + F12, DM(I1, M6) = F5;
      F13 = F5 + F5, F10 = DM(0, I1);
      F15 = F13 - F15;
      F9 = F1 * F7, F3 = F10 - F15;
      F13 = F3 * F6, F12 = F9 + F14;
      F9 = F12 + F12, DM(I0, M6) = F12;
      F3 = F8 + F13;
      F8 = F3 * F7, F14 = F9 - F14;
      F9 = F3 + F3;
      F1 = F1 + F1;
      F2 = F9 - F2;
      F0 = F1 - F0, F9 = DM(0, I0);
      F12 = F0 * F4, F5 = F8 + F15;
      F8 = F2 * F4, F1 = F9 - F14, DM(I1, M6) = F5;
      F13 = F5 + F5, F10 = DM(0, I1);
      F9 = F1 * F6;
      F15 = F13 - F15;
      F1 = F12 + F9;
      F9 = F1 * F7, F3 = F10 - F15;
      F13 = F3 * F6, F12 = F9 + F14;
      F9 = F12 + F12, DM(I0, M6) = F12;
      F3 = F8 + F13;
      F8 = F3 * F7, F14 = F9 - F14;
      F9 = F3 + F3;
      F1 = F1 + F1;
      F5 = F15 + F8;
      F2 = F9 - F2, DM(I1, M6) = F5;
      F0 = F1 - F0, F9 = DM(0, I0);
      F12 = F0 * F4, F1 = F9 - F14, F10 = DM(0, I1);
      F13 = F5 + F5;
      F15 = F13 - F15;
      F9 = F1 * F6, F3 = F10 - F15;
      F8 = F2 * F4, F1 = F9 + F12;
      F13 = F3 * F6;
      F9 = F1 * F7, F3 = F8 + F13;
      F8 = F3 * F7, F12 = F9 + F14;
      F9 = F12 + F12, DM(I0, M6) = F12;
      F5 = F15 + F8;
      F14 = F9 - F14, DM(I1, M6) = F5;
      F1 = F1 + F1;
      F9 = F3 + F3;
      F13 = F5 + F5;
      F0 = F1 - F0;
      F2 = F9 - F2;
      F15 = F13 - F15;
      R11 = R11 - 1;
      IF NE JUMP 0xbd89a1;                   // -> wr_ip_loop_81.
      DM(0x2e3f90) = R0;
      DM(0x2e3f94) = R14;
      DM(0x2e3f98) = R2;
      DM(0x2e3f9c) = R15;
      R4 = DM(0x2e3f64);
      I0 = R4;
      R4 = DM(0x2e3f68);
      I1 = R4;
      R4 = 0x2e3ec0;
      I3 = R4;
      R9 = DM(0x2e3f8c);
      R13 = DM(0x2e3f60);
      R8 = R9 + 1;
      R12 = 0x3ff;
      R8 = R8 AND R12;
      R8 = LSHIFT R8 BY 2;
      R8 = R13 + R8;
      I2 = R8;
      R12 = 0x20;
      R7 = R12 + R9;
      R12 = 0x3ff;
      R7 = R7 AND R12;
      DM(0x2e3f8c) = R7;
      R7 = LSHIFT R7 BY 2;
      R7 = R13 + R7;
      R5 = DM(0x2e3fdc);
      R6 = DM(0x2e3fe0);
      R4 = 0x3f000000;                  // 0.5
      R11 = 0x7;
.GLOBAL wr_ip_loop_82.;
wr_ip_loop_82.:
      R10 = DM(0, I0);
      F14 = F10 * F5, F15 = DM(0, I1);
      F1 = F10 + F15, F0 = DM(-32, I3);
      F9 = F0 * F6, F2 = DM(I3, M6);
      F13 = F2 * F6, F12 = F9 + F14, F0 = DM(-32, I3);
      F9 = F0 * F6, DM(I0, M6) = F12;
      F12 = F15 * F5, F10 = DM(0, I0);
      F15 = F12 + F13, F2 = DM(I3, M6);
      F14 = F10 * F5, DM(I1, M6) = F15;
      F8 = F1 * F4, F12 = F9 + F14, F15 = DM(0, I1);
      F13 = F2 * F6, F1 = F10 + F15, DM(I2, M6) = F8;
      F8 = F1 * F4, DM(I0, M6) = F12;
      F12 = F15 * F5, DM(I2, M6) = F8;
      F15 = F12 + F13, F10 = DM(0, I0);
      F14 = F10 * F5, DM(I1, M6) = F15;
      R15 = DM(0, I1);
      F1 = F10 + F15, F0 = DM(-32, I3);
      F9 = F0 * F6, F2 = DM(I3, M6);
      F13 = F2 * F6, F12 = F9 + F14, F0 = DM(-32, I3);
      F9 = F0 * F6, DM(I0, M6) = F12;
      F12 = F15 * F5, F10 = DM(0, I0);
      F15 = F12 + F13, F2 = DM(I3, M6);
      F14 = F10 * F5, DM(I1, M6) = F15;
      F8 = F1 * F4, F12 = F9 + F14, F15 = DM(0, I1);
      F13 = F2 * F6, F1 = F10 + F15, DM(I2, M6) = F8;
      F8 = F1 * F4, DM(I0, M6) = F12;
      F12 = F15 * F5, DM(I2, M6) = F8;
      F15 = F12 + F13;
      DM(I1, M6) = F15;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8a7e;                   // -> wr_ip_loop_82.
      R10 = DM(0, I0);
      F14 = F10 * F5, F15 = DM(0, I1);
      F1 = F10 + F15, F0 = DM(-32, I3);
      F9 = F0 * F6, F2 = DM(I3, M6);
      F13 = F2 * F6, F12 = F9 + F14, F0 = DM(-32, I3);
      F9 = F0 * F6, DM(I0, M6) = F12;
      F12 = F15 * F5, F10 = DM(0, I0);
      F15 = F12 + F13, F2 = DM(I3, M6);
      F14 = F10 * F5, DM(I1, M6) = F15;
      F8 = F1 * F4, F12 = F9 + F14, F15 = DM(0, I1);
      F13 = F2 * F6, F1 = F10 + F15, DM(I2, M6) = F8;
      F8 = F1 * F4, DM(I0, M6) = F12;
      F12 = F15 * F5, DM(I2, M6) = F8;
      F15 = F12 + F13, F10 = DM(0, I0);
      F14 = F10 * F5, DM(I1, M6) = F15;
      R15 = DM(0, I1);
      F1 = F10 + F15, F0 = DM(-32, I3);
      F9 = F0 * F6, F2 = DM(I3, M6);
      F13 = F2 * F6, F12 = F9 + F14, F0 = DM(-32, I3);
      F9 = F0 * F6, DM(I0, M6) = F12;
      F12 = F15 * F5, F10 = DM(0, I0);
      F15 = F12 + F13, F2 = DM(I3, M6);
      F14 = F10 * F5, DM(I1, M6) = F15;
      F8 = F1 * F4, F12 = F9 + F14, F15 = DM(0, I1);
      F13 = F2 * F6, F1 = F10 + F15, DM(I2, M6) = F8;
      F8 = F1 * F4, DM(I0, M6) = F12;
      F12 = F15 * F5;
      I2 = R7;
      F15 = F12 + F13, DM(I2, M6) = F8;
      DM(I1, M6) = F15;
      I12 = DM(0x2e404c);
      JUMP (M14, I12);
.GLOBAL wr_ip_sub_ring0.;
wr_ip_sub_ring0.:
      R1 = DM(0x2e3f60);
      I0 = R1;
      R0 = 0x0;                         // 0.0
      R11 = 0x80;
.GLOBAL wr_ip_loop_83.;
wr_ip_loop_83.:
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8b36;                   // -> wr_ip_loop_83.
      JUMP (M14, I12);
.GLOBAL wr_ip_sub_exp2.;
wr_ip_sub_exp2.:
      R1 = -0x3d380000;                 // -100.0
      F0 = MAX(F0, F1);
      R1 = TRUNC F0;
      F2 = FLOAT R1;
      COMP(F2, F0);
      IF LE JUMP 0xbd8b56;                   // -> wr_ip_else_84.
      R1 = R1 - 1;
      R3 = 0x3f800000;                  // 1.0
      F2 = F2 - F3;
.GLOBAL wr_ip_else_84.;
wr_ip_else_84.:
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
.GLOBAL wr_ip_sub_recip.;
wr_ip_sub_recip.:
      R1 = 0x7ef311c3;
      R1 = R1 - R0;
      R3 = 0x40000000;                  // 2.0
      F2 = F0 * F1;
      F2 = F3 - F2;
      F1 = F1 * F2;
      F2 = F0 * F1;
      F2 = F3 - F2;
      F1 = F1 * F2;
      F2 = F0 * F1;
      F2 = F3 - F2;
      F1 = F1 * F2;
      F0 = PASS F1;
      JUMP (M14, I12);
.GLOBAL wr_ip_sub_sine.;
wr_ip_sub_sine.:
      R1 = -0x1f;
      F0 = FLOAT R0 BY R1;
      R1 = 0x3f000000;                  // 0.5
      COMP(F0, F1);
      IF LE JUMP 0xbd8bab;                   // -> wr_ip_else_85.
      R2 = 0x3f800000;                  // 1.0
      F0 = F2 - F0;
      JUMP 0xbd8bb7;                         // -> wr_ip_fi_86.
.GLOBAL wr_ip_else_85.;
wr_ip_else_85.:
      R1 = -0x41000000;                 // -0.5
      COMP(F0, F1);
      IF GE JUMP 0xbd8bb7;                   // -> wr_ip_else_87.
      R2 = -0x40800000;                 // -1.0
      F0 = F2 - F0;
.GLOBAL wr_ip_else_87.;
wr_ip_else_87.:
.GLOBAL wr_ip_fi_86.;
wr_ip_fi_86.:
      F2 = F0 * F0;
      R1 = 0x3d9f81e9;                  // 0.0778845027089119
      F1 = F1 * F2;
      R3 = -0x40e6cfad;                 // -0.5983936190605164
      F1 = F1 + F3;
      F1 = F1 * F2;
      R3 = 0x402334b4;                  // 2.5500917434692383
      F1 = F1 + F3;
      F1 = F1 * F2;
      R3 = -0x3f5aa21d;                 // -5.167710781097412
      F1 = F1 + F3;
      F1 = F1 * F2;
      R3 = 0x40490fdb;                  // 3.1415927410125732
      F1 = F1 + F3;
      F0 = F1 * F0;
      JUMP (M14, I12);
.GLOBAL wr_ip_sub_span.;
wr_ip_sub_span.:
      F8 = F0 + F1;
      R12 = 0x42000000;                 // 32.0
      F9 = F1 * F12;
      F9 = F0 + F9;
      F13 = MIN(F8, F9);
      F14 = MAX(F8, F9);
      R13 = TRUNC F13;
      R14 = TRUNC F14;
      R14 = R14 + 1;
      R13 = R13 - 1;
      R14 = LSHIFT R14 BY 2;
      R8 = R15 - R14;
      R12 = 0xc;
      R8 = R8 - R12;
      R13 = LSHIFT R13 BY 2;
      R9 = R15 - R13;
      R12 = 0x7c;
      R9 = R9 + R12;
      R11 = R9 - R8;
      R11 = LSHIFT R11 BY -2;
      R11 = R11 + 1;
      R12 = 0x30;
      R11 = MIN(R11, R12);
      R13 = PASS R6;
      R12 = 0x2e5400;
      I4 = R12;
      R6 = R12 - R8;
      R8 = PASS R8;
      IF GE JUMP 0xbd8c3e;                   // -> wr_ip_else_88.
      R12 = 0x1000;
      R14 = R8 + R12;
      R14 = R14 + R13;
      I3 = R14;
      R9 = -R8;
      R9 = LSHIFT R9 BY -2;
      R9 = MIN(R9, R11);
      R11 = R11 - R9;
      R8 = LSHIFT R9 BY 2;
      R12 = 0x2e5400;
      R8 = R12 + R8;
      R12 = 0x3;
      R9 = R12 + R9;
      R9 = LSHIFT R9 BY -2;
.GLOBAL wr_ip_loop_89.;
wr_ip_loop_89.:
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R9 = R9 - 1;
      IF NE JUMP 0xbd8c2b;                   // -> wr_ip_loop_89.
      I3 = R13;
      I4 = R8;
      JUMP 0xbd8c42;                         // -> wr_ip_fi_90.
.GLOBAL wr_ip_else_88.;
wr_ip_else_88.:
      R14 = R8 + R13;
      I3 = R14;
.GLOBAL wr_ip_fi_90.;
wr_ip_fi_90.:
      R11 = PASS R11;
      IF EQ JUMP 0xbd8c59;                   // -> wr_ip_else_91.
      R12 = 0x3;
      R11 = R12 + R11;
      R11 = LSHIFT R11 BY -2;
.GLOBAL wr_ip_loop_92.;
wr_ip_loop_92.:
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8c4d;                   // -> wr_ip_loop_92.
.GLOBAL wr_ip_else_91.;
wr_ip_else_91.:
      JUMP (M14, I12);
.GLOBAL wr_ip_sub_ins_ramp.;
wr_ip_sub_ins_ramp.:
      R1 = 0x3d000000;                  // 0.03125
      F1 = F0 * F1;
      R2 = DM(0x200a764c);
      I0 = R2;
      I1 = R2;
      R11 = 0x20;
.GLOBAL wr_ip_loop_93.;
wr_ip_loop_93.:
      F0 = F0 - F1, R2 = DM(I0, M6);
      F2 = F2 + F0;
      DM(I1, M6) = F2;
      R11 = R11 - 1;
      IF NE JUMP 0xbd8c69;                   // -> wr_ip_loop_93.
      JUMP (M14, I12);
.wr_inpost..end:
      .type wr_inpost.,STT_FUNC;
