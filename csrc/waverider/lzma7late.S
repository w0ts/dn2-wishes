| 2026-11-11 (lzma-cache, csrc/waverider/lzma7cache.c): the DSP upload moved after the eMMC's set-up.
| Stock 1.12's boot routine calls the uploader 0x400cf4b0 at 0x400cf086 (now three nops), then sets up
| the eMMC driver (0x4012bddc, 0x4012be52, 0x4012c438, 0x4012c620); all its paths then meet at
| 0x400cf0f2, `move.l %d0,0x4243989c` (the driver's result), which becomes `jsr dn7_late`. The
| instruction is replayed, then the uploader runs from here and returns to 0x400cf0f8. Stock reads
| none of d0, d1, a0 or a1 there before writing it (0x400cf0f8 moveq #64,%d0; d1 at 0x400cf13c); the
| uploader is a C function and keeps the others.
        .text
        .globl  dn7_late
dn7_late:
        move.l  %d0, 0x4243989c
        jmp     0x400cf4b0
