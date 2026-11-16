| The wishes record's hooks (csrc/wishes/wish.h; docs/wishes-record.md), OS 1.12: LFO4's on 1.11
| (csrc/lfo4/hooks.S) as to what they see, but memcpy and memset are reached through their callers.
|
| memcpy 0x40134770 and memset 0x401347b8 stay stock, byte for byte: they are on Overbridge's audio path
| (scripts/gate_overbridge.py). Instead every reference to them in MAIN OS -- jsr, jmp, lea, move.l #, 1,001
| of them -- names these stubs (dnfw.waverider.coldfire WISH_KEEP: the User, 2026-11-11, "A: keep
| Overbridge stock"), except the four in Overbridge's own code, which copy audio and never a sound. A stub
| is entered as the routine would be (the caller's return, then dst, src or fill, n), calls C only when
| there can be work (the table holds a sound, and the block is a sound or larger), and goes on into
| stock's routine with the stack as the caller left it: 3 instructions more than stock (table empty) or 6.
| No register is saved: the C keeps the convention stock's callers expect, and the routine loads its own.
|
| The stored-sound loader 0x400dd34e and saver 0x400dd80a, just past their value loops, where the live
| sound and the stored one are in a2 / a3 (in opposite roles) and d0, d1, a0, a1 are live:
|   load  0x400dd3e6  mvs.b 28(%a2),%d0 ; moveq #6,%d2          a2 live, a3 stored (6 bytes: jmp)
|   save  0x400dd888  mvs.b 54(%a2),%d0 ; move.l (%a0,%d0*4),%d0  a2 stored, a3 live (8 bytes: jmp ; nop)
| **One owner for the load site.** Waverider raises the machine-type bound there (`moveq #6,%d2` ->
| `moveq #WR_LOAD_BOUND,%d2`: our machine types load as themselves, dnfw.waverider.coldfire LOAD_BOUND), and
| that `moveq` is inside the 6 bytes this jump displaces, so the stub replays waverider's version and the
| composer makes no edit of its own there (test/test_wishes.py checks the replayed bytes).

#define SOUND_BYTES 1163
#define MEMCPY 0x40134770
#define MEMSET 0x401347B8
#define LOAD_SITE 0x400DD3E6
#define SAVE_SITE 0x400DD888

        .text
        .globl  wish_memcpy_stub
wish_memcpy_stub:
        tst.l   wish_n
        beq.s   wish_memcpy_stock       | nothing tracked: nothing to carry
        move.l  12(%sp), %d0
        cmp.l   #SOUND_BYTES, %d0
        bcs.s   wish_memcpy_stock       | smaller than a sound: not ours
        move.l  12(%sp), -(%sp)         | n
        move.l  12(%sp), -(%sp)         | src
        move.l  12(%sp), -(%sp)         | dst
        jsr     wish_on_memcpy
        lea     12(%sp), %sp
wish_memcpy_stock:
        jmp     MEMCPY

        .globl  wish_memset_stub
wish_memset_stub:
        tst.l   wish_n
        beq.s   wish_memset_stock
        move.l  12(%sp), %d1
        cmp.l   #SOUND_BYTES, %d1
        bcs.s   wish_memset_stock
        move.l  12(%sp), -(%sp)         | n
        move.l  12(%sp), -(%sp)         | fill
        move.l  12(%sp), -(%sp)         | dst
        jsr     wish_on_memset
        lea     12(%sp), %sp
wish_memset_stock:
        jmp     MEMSET

        .globl  wish_load_stub
wish_load_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | stored
        move.l  %a2, -(%sp)             | live
        jsr     wish_load
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        .globl  wish_load_displaced
wish_load_displaced:
        mvs.b   28(%a2), %d0
        moveq   #WR_LOAD_BOUND, %d2
        jmp     LOAD_SITE + 6

        .globl  wish_save_stub
wish_save_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | live
        move.l  %a2, -(%sp)             | stored
        jsr     wish_save
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        .globl  wish_save_displaced
wish_save_displaced:
        mvs.b   54(%a2), %d0
        move.l  (%a0,%d0.l*4), %d0
        jmp     SAVE_SITE + 8
