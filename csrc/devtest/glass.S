| The glass inverted while the test channel is armed (csrc/devtest/devtest.c dt_glass, dt_present): the two
| stock routines whose entries now jmp to C, each replayed here as stock's and continued where the jmp was.
| Called as the stock routines are (the same arguments on the stack, the same return value).

        .text
| 0x40131f04(column, page, bytes): one 8-byte group to the panel controller (was: lea -16(%sp),%sp ;
| movem.l %d2-%d4/%a2,(%sp))
        .globl  dt_glass_stock
dt_glass_stock:
        lea     -16(%sp), %sp
        movem.l %d2-%d4/%a2, (%sp)
        jmp     0x40131F0C

| panel_diff 0x40131fd2: the changed groups of FRONT, the 0xB8, the swap -> the new FRONT (was:
| lea -40(%sp),%sp ; movem.l %d2-%d6/%a2-%a4,(%sp))
        .globl  dt_diff_stock
dt_diff_stock:
        lea     -40(%sp), %sp
        movem.l %d2-%d6/%a2-%a4, (%sp)
        jmp     0x40131FDA
