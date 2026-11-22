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
|
| DN2_LFO4 (2026-11-16, v0.56.2's `overbridge` step): lfo4 carries its own table through the same two routines. Its
| entry hooks are left out on our series (dnfw.mods.lfo4 MEMORY_SITES: memcpy is on Overbridge's audio path), so these
| stubs go on into lfo4's instead of into stock's: lfo4_memcpy_stub / lfo4_memset_stub (csrc/lfo4/hooks.S) test,
| carry, replay the two instructions their jump used to displace and continue at entry + 8, which is stock's routine
| entered as the caller entered it. Every caller that reached lfo4 before still does, in the same order (ours, then
| lfo4's); only Overbridge's own references (WISH_KEEP, WISH_HOOKED) do not, and they copy audio, never a sound.
#if DN2_LFO4
#define MEMCPY_ON LFO4_MEMCPY_STUB_VA
#define MEMSET_ON LFO4_MEMSET_STUB_VA
#else
#define MEMCPY_ON MEMCPY
#define MEMSET_ON MEMSET
#endif
#define LOAD_SITE 0x400DD3E6
#define SAVE_SITE 0x400DD888

        .text
#if DN2_LFO4
| 2026-11-17 (the User's CPU: the worst case, 70 copies a frame): one stub for both carries, then the copy itself.
| The size is tested once; ours is carried when our table holds a sound, then lfo4's when its table does (the
| order and the conditions of the two stubs this replaces: ours, then lfo4_memcpy_stub). The copy is stock's
| memcpy's (0x40134770, which stays stock for Overbridge) in 32-byte blocks instead of 16, then longs, then
| bytes, front to back: the same bytes land for any copy whose destination does not start inside its own source
| (checked over every copy the emulator's runs make: scripts in the cpu75 notes), and %d0 comes back as dst.
| Registers: d0, d1, a0, a1 as stock's (scratch); d2-d7 / a2 saved around the blocks.
        .globl  wish_memcpy_stub
wish_memcpy_stub:
        move.l  12(%sp), %d0
        cmp.l   #SOUND_BYTES, %d0
        bcs.s   wish_memcpy_copy        | smaller than a sound: neither table's
        tst.l   wish_n
        beq.s   1f                      | nothing of ours tracked
        move.l  12(%sp), -(%sp)         | n
        move.l  12(%sp), -(%sp)         | src
        move.l  12(%sp), -(%sp)         | dst
        jsr     wish_on_memcpy
        lea     12(%sp), %sp
1:      tst.l   LFO4_EXT_LIVE_VA
        beq.s   wish_memcpy_copy        | nothing of lfo4's tracked
        move.l  12(%sp), -(%sp)
        move.l  12(%sp), -(%sp)
        move.l  12(%sp), -(%sp)
        jsr     LFO4_ON_MEMCPY_VA
        lea     12(%sp), %sp
        .globl  wish_memcpy_copy
wish_memcpy_copy:
        movea.l 4(%sp), %a1             | dst
        movea.l 8(%sp), %a0             | src
        move.l  12(%sp), %d0            | n
        moveq   #32, %d1
        sub.l   %d1, %d0
        blt.s   4f                      | under 32 bytes: no block
        lea     -28(%sp), %sp
        movem.l %d2-%d7/%a2, (%sp)
2:      movem.l (%a0), %d1-%d7/%a2
        lea     32(%a0), %a0
        movem.l %d1-%d7/%a2, (%a1)
        lea     32(%a1), %a1
        subi.l  #32, %d0
        bge.s   2b
        movem.l (%sp), %d2-%d7/%a2
        lea     28(%sp), %sp
4:      moveq   #28, %d1
        add.l   %d1, %d0                | what is left, less 4
        bra.s   6f
5:      move.l  (%a0)+, (%a1)+
        subq.l  #4, %d0
6:      bge.s   5b
        addq.l  #4, %d0
        ble.s   8f
7:      move.b  (%a0)+, (%a1)+
        subq.l  #1, %d0
        bgt.s   7b
8:      move.l  4(%sp), %d0
        rts
#else
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
        jmp     MEMCPY_ON
#endif

| 2026-11-18 (the User's CPU, constant load: the same copies, fewer instructions). The audio interrupt's voice loop
| (0x400274fa, once a voice, 16 a frame) copies four runs of the voice's smoothed row (%a5) into its DSP frame record
| (%a4) through memcpy (%d4, the stub above): 82, 28 and 26 bytes, then 10 (rows +84 / +166 / +194 / +224 into the
| record's +218 / +300 / +328 / +354: the first three one run of 136 bytes, the record's 146 bytes one run). Entered by
| a jsr in place of the four calls (dnfw.waverider.coldfire VOICE_COPY_SITE); the same bytes in the same order, the
| row and the record apart (0x800068e4.. and 0x80005e60..); then the loop's own steps (%a5 += 202, %a4 += 146).
| %d0, %d1, %a0, %a1 left as the fourth memcpy left them: dst, 28, src + 10, dst + 10.
        .globl  wish_voice_copy
wish_voice_copy:
        lea     84(%a5), %a0
        lea     218(%a4), %a1
        .rept   34
        move.l  (%a0)+, (%a1)+
        .endr
        lea     224(%a5), %a0
        lea     354(%a4), %a1
        move.l  %a1, %d0
        move.l  (%a0)+, (%a1)+
        move.l  (%a0)+, (%a1)+
        move.w  (%a0)+, (%a1)+
        moveq   #28, %d1
        lea     202(%a5), %a5
        lea     146(%a4), %a4
        rts

| 2026-11-18 (the same): just past that loop the interrupt copies 18, 16, 22 and 16 bytes through memcpy, one run of 72
| (its %a2 + 3330 into 0x80006868: the source 0x80003af0.. and the destination apart), then steps %a2 by 3402 and pops
| their arguments. Entered by a jsr in place of the four (POST_COPY_SITE); %d0, %d1, %a0, %a1 as the fourth memcpy
| left them (0x800068a0, 28, src end, 0x800068b0).
        .globl  wish_post_copy
wish_post_copy:
        lea     3330(%a2), %a0
        lea     0x80006868, %a1
        .rept   18
        move.l  (%a0)+, (%a1)+
        .endr
        move.l  #0x800068a0, %d0
        moveq   #28, %d1
        lea     3402(%a2), %a2
        rts

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
        jmp     MEMSET_ON

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
