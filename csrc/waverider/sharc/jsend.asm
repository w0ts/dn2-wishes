// jsend.asm -- JUNO in the stock chorus's slot on the FX bus (docs/inserts.md "The chorus send"). GENERATED
// by scripts/gen_inserts_asm.py from dnfw.inserts.jsend; do not edit by hand.

.SECTION/PM seg_pmco;

.GLOBAL wr_jsend.;
wr_jsend.:
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
      R0 = DM(-0x7bfff104);
      R1 = 0x1;
      COMP(R0, R1);
      IF EQ JUMP 0xbd0c9f;                   // -> wr_js_else_1.
      R2 = -0x7dab0000;
      I4 = R2;
      R9 = 0x0;
      DM(6, I4) = R9;
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
      JUMP 0xb84d5c;                    // the stock chorus, entered as the bus called it
.GLOBAL wr_js_else_1.;
wr_js_else_1.:
      R2 = -0x7dab0000;
      I4 = R2;
      R0 = DM(6, I4);
      R1 = 0x1;
      COMP(R0, R1);
      IF EQ JUMP 0xbd0d1c;                   // -> wr_js_else_2.
      R2 = -0x7dab0000;
      I4 = R2;
      R9 = 0x0;
      DM(0, I4) = R9;
      DM(1, I4) = R9;
      DM(2, I4) = R9;
      DM(3, I4) = R9;
      DM(4, I4) = R9;
      DM(5, I4) = R9;
      R9 = 0x1;
      DM(6, I4) = R9;
      R1 = -0x7daaffb4;
      I0 = R1;
      R0 = 0x0;                         // 0.0
      R11 = 0x40;
.GLOBAL wr_js_loop_3.;
wr_js_loop_3.:
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd0ccc;                   // -> wr_js_loop_3.
      R1 = -0x7fba6c74;
      I0 = R1;
      R11 = 0x44;
.GLOBAL wr_js_loop_4.;
wr_js_loop_4.:
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd0ce7;                   // -> wr_js_loop_4.
      R1 = -0x7fba5ae8;
      I0 = R1;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R1 = -0x7fba5a78;
      I0 = R1;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R13 = -0x7fba5a54;
      R14 = 0x24;
      R11 = 0x6;
.GLOBAL wr_js_loop_5.;
wr_js_loop_5.:
      I0 = R13;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      DM(I0, M6) = F0;
      R13 = R13 + R14, DM(I0, M6) = F0;
      R11 = R11 - 1;
      IF NE JUMP 0xbd0d10;                   // -> wr_js_loop_5.
.GLOBAL wr_js_else_2.;
wr_js_else_2.:
      R2 = -0x7dab0000;
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
      R13 = DM(0x2e4018);
      I4 = R13;
      R14 = DM(1, I4);
      I4 = R14;
      R15 = DM(0, I4);
      I0 = R15;
      R15 = DM(1, I4);
      I1 = R15;
      R13 = DM(0x2e4018);
      I4 = R13;
      R14 = DM(3, I4);
      I4 = R14;
      R15 = DM(0, I4);
      DM(0x2e3f64) = R15;
      I2 = R15;
      R15 = DM(1, I4);
      DM(0x2e3f68) = R15;
      I3 = R15;
      R11 = 0x20;
.GLOBAL wr_js_loop_6.;
wr_js_loop_6.:
      R8 = DM(I0, M6);
      DM(I2, M6) = F8;
      R9 = DM(I1, M6);
      DM(I3, M6) = F9;
      R11 = R11 - 1;
      IF NE JUMP 0xbd0d69;                   // -> wr_js_loop_6.
      R0 = -0x7daaffb4;
      DM(0x2e3f60) = R0;
      R0 = DM(0x25ce84);
      R0 = LSHIFT R0 BY -16;
      R12 = 0xffff;
      R0 = R0 AND R12;
      F0 = FLOAT R0;
      R1 = 0x38010204;                  // 3.075787390116602e-05
      F0 = F0 * F1;
      DM(0x2e3f6c) = R0;
      R0 = DM(0x25ce88);
      R0 = R0 AND R12;
      F0 = FLOAT R0;
      F0 = F0 * F1;
      DM(0x2e3f70) = R0;
      R0 = DM(0x2e3f70);
      R1 = 0x403e8000;                  // 2.9765625
      F0 = F0 * F1;
      R0 = TRUNC F0;
      R2 = 0x167980;
      R3 = 0x3b4ca038;                  // 0.003122342750430107
      R1 = 0x1;
      COMP(R0, R1);
      IF NE JUMP 0xbd0daf;                   // -> wr_js_else_7.
      R2 = 0x24d100;
      R3 = 0x3b2343eb;                  // 0.00249123084358871
.GLOBAL wr_js_else_7.;
wr_js_else_7.:
      R1 = 0x2;
      COMP(R0, R1);
      IF NE JUMP 0xbd0dbb;                   // -> wr_js_else_8.
      R2 = 0x1573c00;
      R3 = 0x39ae2650;                  // 0.00033216411247849464
.GLOBAL wr_js_else_8.;
wr_js_else_8.:
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
.GLOBAL wr_js_loop_9.;
wr_js_loop_9.:
      R0 = DM(0x2e3fd4);
      R1 = DM(0x2e3fd8);
      R6 = DM(0x2e3f60);
      R7 = 0x4;
      R15 = DM(0x2e3f8c);
      R15 = R15 + 1;
      R15 = LSHIFT R15 BY 2;
      R4 = DM(0x2e3fcc);
      I0 = R4;
      R12 = 0xbd0e61;                        // return address - 1: wr_js_ret_10. - 1
      I12 = R12;
      JUMP 0xbd1105;                         // -> wr_js_sub_span.
.GLOBAL wr_js_ret_10.;
wr_js_ret_10.:
      R15 = R15 + R6;
      R6 = PASS R0;
      R3 = 0x3f000000;                  // 0.5
      R11 = 0x10;
.GLOBAL wr_js_loop_11.;
wr_js_loop_11.:
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
      IF NE JUMP 0xbd0e69;                   // -> wr_js_loop_11.
      R0 = DM(0x2e3fd0);
      DM(0x2e3fd4) = R0;
      R0 = DM(0x2e3fc4);
      DM(0x2e3fd8) = R0;
      R0 = 0x2e3ec0;
      DM(0x2e3fcc) = R0;
      R0 = DM(0x2e4044);
      R0 = R0 - 1;
      DM(0x2e4044) = R0;
      IF NE JUMP 0xbd0e43;                   // -> wr_js_loop_9.
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
.GLOBAL wr_js_loop_12.;
wr_js_loop_12.:
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
      IF NE JUMP 0xbd0f10;                   // -> wr_js_loop_12.
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
.GLOBAL wr_js_loop_13.;
wr_js_loop_13.:
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
      IF NE JUMP 0xbd0fed;                   // -> wr_js_loop_13.
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
      R2 = -0x7dab0000;
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
      I12 = DM(M7, I6);
      JUMP (M14, I12) (DB);
      RFRAME;
      NOP;
.GLOBAL wr_js_sub_span.;
wr_js_sub_span.:
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
      IF GE JUMP 0xbd115a;                   // -> wr_js_else_14.
      R12 = 0x1000;
      R14 = R8 + R12;
      R14 = R14 + R13;
      I3 = R14;
      R12 = 0x0;
      R9 = R12 - R8;
      R9 = LSHIFT R9 BY -2;
      R9 = MIN(R9, R11);
      R11 = R11 - R9;
.GLOBAL wr_js_loop_15.;
wr_js_loop_15.:
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R9 = R9 - 1;
      IF NE JUMP 0xbd114f;                   // -> wr_js_loop_15.
      I3 = R13;
      JUMP 0xbd115e;                         // -> wr_js_fi_16.
.GLOBAL wr_js_else_14.;
wr_js_else_14.:
      R14 = R8 + R13;
      I3 = R14;
.GLOBAL wr_js_fi_16.;
wr_js_fi_16.:
      R11 = PASS R11;
      IF EQ JUMP 0xbd1168;                   // -> wr_js_else_17.
.GLOBAL wr_js_loop_18.;
wr_js_loop_18.:
      R14 = DM(I3, M6);
      DM(I4, M6) = F14;
      R11 = R11 - 1;
      IF NE JUMP 0xbd1162;                   // -> wr_js_loop_18.
.GLOBAL wr_js_else_17.;
wr_js_else_17.:
      JUMP (M14, I12);
.wr_jsend..end:
      .type wr_jsend.,STT_FUNC;
