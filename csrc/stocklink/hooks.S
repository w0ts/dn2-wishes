| Stock's DSP link and USB passes in the audio interrupt, the same bytes with less work (OS 1.12; the study
| scratch/dup-study.md, the User 2026-11-18: items 1, 2, 3). Each is entered by a jmp (jsr for the installer) at a
| whole stock instruction, replays what the jump displaced where needed, and leaves memory, the stack above its
| entry, the peripherals and every register the interrupt reads afterwards as stock's instructions leave them.
| Proofs: test/stocklink/ (unicorn harnesses: stock's code and ours on the same random inputs, every byte and
| every peripheral write compared, with negative controls).
|
| 1. skl_fill (0x400cfa5a in the SPI frame routine 0x400cf922, after its eDMA set-up, before the DMA start): the
|    staging buffer 0x80002510 of the DSPI's eDMA (ch 29) holds a PUSHR long an entry: command 0x8001 above a data
|    word. Stock writes the command and copies the data 7 instructions an entry (1,344 entries), then the command
|    alone into entries 1,344..1,373, then turns the last one's command into 0x0801 (CONT off, EOQ on). Here, for
|    the interrupt's frame (2,688 bytes, the boot's length 2,748): each data entry as one long (the command kept in
|    the register's high half), 2 instructions an entry; the tail commands stored; the same bytes. No state: every
|    byte stock writes is written each call. Any other length: stock's own instructions (replayed, then 0x400cfa62).
| 2. The TDM transmit half (0x4e6e8100 + h << 11, 2 KB uncached): outside mode 6 stock clears it whole every frame
|    (0x4013419c), then the USB-in loop (mode 5, while 0x80005366 is set) writes two slot columns and smp_tdm (our
|    link) may write slots 8..15 of every frame. Here a half is cleared only where something wrote since its last
|    clear: skl_tx_dirty[h] holds the columns (16 slots, 32 frames each) written at the half's last use; the clears
|    are made after smp_tdm (skl_tx_after), of the dirty columns this frame does not write again. A half nothing can
|    vouch for (power-on, mode 6 = Overbridge wrote it, a USB-in slot outside 0..15, the audio interrupt installed
|    again after the service one: skl_isr_install) is cleared whole, as stock. The same words at DMA time.
| 3. skl_usbout (0x400276b2, mode 5 USB audio out): stock calls the getter 0x400253d0 128 times a frame: slots A,
|    A+1 (loop 1) and B-1, B (loop 2) of each of the 32 frames, each an uncached read. Here each distinct channel is
|    read once a frame, and the partner channels are not read at all in stereo (their weight d4 is 0: the MAC is
|    still made, with 0 in the register: the same accumulator and flags). The MAC operations, their order and the
|    stores' order are stock's.

| 7. skl_rcopy (0x400cf956, the same routine's copy of the previous frame's reply, 2,748 B, 0x80001a20 ->
|    0x800053a4): stock's memcpy 0x40134770 in 32-byte blocks instead of 16, then longs, then bytes, its registers
|    left as stock's leaves them (d0 dst, d1 16, a0/a1 past the ends); stock's own routine for a copy under 32 bytes
|    or whose two areas overlap (there the block size could change the bytes).
|
| All of it only with DN2_STOCK_LINK_FAST (dnfw.waverider.pages.stock_link_fast_on, on by default; the User
| 2026-11-18: "allow if bit identical yes and add a flag to switch back if needed"): off, nothing here is built, no
| stock site is edited and smp_tdm_hook is main's.

#if DN2_STOCK_LINK_FAST
        .text

| ---- 1. the SPI frame's staging fill --------------------------------------------------------------------------
| in: a2 the frame's length (arg 1), a3 the frame (arg 2), d1 L = min(boot length, 2800). d0/d2/a0/a1 free (the
| routine saved d2/a2/a3; after 0x400cfab4 only d0 is written before they are restored).
        .globl  skl_fill
skl_fill:
        cmpa.l  #2688, %a2
        bne.w   9f
        cmpi.l  #2748, %d1
        bne.w   9f
        lea     0x80002510, %a0
        move.l  #0x80010000, %d0                | the command 0x8001 in the high half
        moveq   #84, %d2                        | 1,344 entries: 84 x 16
1:
        .rept   16
        move.w  (%a3)+, %d0
        move.l  %d0, (%a0)+
        .endr
        subq.l  #1, %d2
        bne.w   1b
        move.w  #0x8001, %d0                    | entries 1,344..1,372: the command only (their data halves kept)
        .irp    k, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28
        move.w  %d0, 4*\k(%a0)
        .endr
        move.w  #0x0801, %d0                    | entry 1,373, the last: CONT off, EOQ on
        move.w  %d0, 4*29(%a0)
        jmp     0x400CFAB4                      | the DMA start, as stock
9:      move.l  %a2, %d0                        | any other length: stock's (the two instructions the jmp displaced)
        cmpa.l  #2800, %a2
        jmp     0x400CFA62                      | (ble.s on these flags)

| ---- 7. the reply copy -----------------------------------------------------------------------------------------
MEMCPY  = 0x40134770
| in: the caller's return, dst, src, n (stock's memcpy's arguments, jsr'd at 0x400cf956)
        .globl  skl_rcopy
skl_rcopy:
        movea.l 4(%sp), %a1                     | dst
        movea.l 8(%sp), %a0                     | src
        move.l  12(%sp), %d0                    | n
        moveq   #32, %d1
        cmp.l   %d1, %d0
        blt.s   8f                              | under 32 bytes: stock's
        move.l  %a1, %d1                        | the areas overlap (dst - src or src - dst under n): stock's
        sub.l   %a0, %d1
        bpl.s   1f
        neg.l   %d1
1:      cmp.l   %d0, %d1
        bcs.s   8f
        lea     -28(%sp), %sp
        movem.l %d2-%d7/%a2, (%sp)
        moveq   #32, %d1
        sub.l   %d1, %d0
2:      movem.l (%a0), %d1-%d7/%a2
        lea     32(%a0), %a0
        movem.l %d1-%d7/%a2, (%a1)
        lea     32(%a1), %a1
        subi.l  #32, %d0
        bge.s   2b
        movem.l (%sp), %d2-%d7/%a2
        lea     28(%sp), %sp
        moveq   #28, %d1
        add.l   %d1, %d0                        | what is left, less 4
        bra.s   4f
3:      move.l  (%a0)+, (%a1)+
        subq.l  #4, %d0
4:      bge.s   3b
        addq.l  #4, %d0
        ble.s   6f
5:      move.b  (%a0)+, (%a1)+
        subq.l  #1, %d0
        bgt.s   5b
6:      moveq   #16, %d1                        | as stock's leaves it
        move.l  4(%sp), %d0                     | dst
        rts
8:      jmp     MEMCPY                          | (the stack as the caller left it: stock's returns there)

| ---- 2. the transmit half's clears ----------------------------------------------------------------------------
TX      = 0x4E6E8100
CLEAR   = 0x4013419C                            | stock's clear (dst, n): longs; after 2 KB d0 = 0, d1 = 16, a0 the end

| skl_clr: the half H (d0, 0 or 1) is to be cleared as stock clears it. A half nobody vouches for: stock's clear,
| now (stock's order). Else its dirty columns are noted, to clear after smp_tdm. Keeps all but d0/d1/a0.
skl_clr:
        move.l  %d0, skl_tx_h
        moveq   #1, %d1
        move.l  %d1, skl_tx_armed
        moveq   #0, %d1
        move.l  %d1, skl_tx_written
        move.l  skl_tx_unknown, %d1
        btst    %d0, %d1
        beq.w   1f
        bclr    %d0, %d1
        move.l  %d1, skl_tx_unknown
        moveq   #0, %d1
        move.l  %d1, skl_tx_pending
        lea     skl_tx_dirty, %a0
        move.l  %d1, (%a0,%d0.l*4)
        moveq   #11, %d1
        lsl.l   %d1, %d0
        addi.l  #TX, %d0
        movea.l %d0, %a0                        | (2026-11-21, the User's CPU) stock's clear's 512 long stores, in its
        lea     -24(%sp), %sp                   | order, 8 a movem (stock: 4 clr.l and a 2-instruction loop a 16 B);
        movem.l %d2-%d7, (%sp)                  | then its registers: d0 = 0, d1 = 16, a0 = the half's end
        moveq   #0, %d0
        moveq   #0, %d1
        moveq   #0, %d2
        moveq   #0, %d3
        moveq   #0, %d4
        moveq   #0, %d5
        moveq   #0, %d6
        moveq   #0, %d7
        .irp    k, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63
        movem.l %d0-%d7, 32*\k(%a0)
        .endr
        lea     0x800(%a0), %a0
        movem.l (%sp), %d2-%d7
        lea     24(%sp), %sp
        moveq   #16, %d1
        rts
1:      lea     skl_tx_dirty, %a0
        move.l  (%a0,%d0.l*4), %d1
        move.l  %d1, skl_tx_pending
        rts

| skl_cols: zero the columns D1 (bit c: slot c, all 32 frames) of half D0. Keeps all but d0/d1/a0.
skl_cols:
        lsl.l   #8, %d0
        lsl.l   #3, %d0
        addi.l  #TX, %d0
        movea.l %d0, %a0
        moveq   #0, %d0
1:      tst.l   %d1
        beq.w   9f
        lsr.l   #1, %d1
        bcc.w   5f
        .irp    f, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31
        move.l  %d0, 64*\f(%a0)
        .endr
5:      addq.l  #4, %a0
        bra.w   1b
9:      rts

| the registers stock's clear leaves for the code after it (d0 = 0, d1 = 16, a0 = the half's end), from d0 = H
skl_clr_regs:
        moveq   #11, %d1
        lsl.l   %d1, %d0
        addi.l  #TX + 0x800, %d0
        movea.l %d0, %a0
        moveq   #0, %d0
        moveq   #16, %d1
        rts

| 0x40025f66 (was: move.l -56(%fp),%d0 ; moveq #11,%d1): mode 5. Stock: clear (the half), 0x40003ede(0x4664bf4c,
| 32), the mode again; still 5 and the USB-in flag set: slot A (0x80005367) and B (0x80005368) of each frame <- the
| USB-in samples >> 8. Then 0x40026098. The clear's two arguments pushed as stock's (they stay under the next call's
| and are popped with them).
        .globl  skl_mode5
skl_mode5:
        move.l  -56(%fp), %d0
        bsr.w   skl_clr
        move.l  -56(%fp), %d0
        moveq   #11, %d1
        lsl.l   %d1, %d0
        addi.l  #TX, %d0
        pea     0x800
        move.l  %d0, -(%sp)
        move.l  -56(%fp), %d0
        bsr.w   skl_clr_regs
        pea     0x20
        pea     0x4664BF4C
        jsr     0x40003EDE
        jsr     (%a2)                           | the mode (a2 = 0x40006c4a, d5 = 5: stock's)
        lea     16(%sp), %sp
        cmp.l   %d0, %d5
        bne.w   8f
        tst.b   0x80005366
        beq.w   8f
        | the columns the loop writes; a slot outside 0..15 lands elsewhere: the pending clears now (stock's order:
        | zeros before the samples), and nobody vouches for either half from here
        mvs.b   0x80005367, %d3                 | A
        mvs.b   0x80005368, %d4                 | B
        moveq   #15, %d2
        cmp.l   %d3, %d2
        bcs.s   5f                              | (unsigned: also below 0)
        cmp.l   %d4, %d2
        bcs.s   5f
        moveq   #0, %d2
        bset    %d3, %d2
        bset    %d4, %d2
        move.l  %d2, skl_tx_written
        bra.s   6f
5:      move.l  skl_tx_pending, %d1
        move.l  skl_tx_h, %d0
        bsr.w   skl_cols
        moveq   #0, %d2
        move.l  %d2, skl_tx_pending
        moveq   #3, %d2
        move.l  %d2, skl_tx_unknown
        | stock's loop (0x40025fa6..0x40026000), its registers as it leaves them
6:      move.l  -56(%fp), %d0
        moveq   #9, %d2
        mvs.b   0x80005368, %d1
        lea     0x4664BF4C, %a1
        lsl.l   %d2, %d0
        mvs.b   0x80005367, %d2
        lea     0x4664BF50, %a0
        add.l   %d0, %d2
        add.l   %d0, %d1
        lsl.l   #2, %d2
        lsl.l   #2, %d1
        clr.l   %d0
        addi.l  #TX, %d2
        addi.l  #TX, %d1
7:      move.l  %d0, %d4
        movea.l %d2, %a2
        lsl.l   #3, %d4
        move.l  (%a1,%d0.l), %d3
        asr.l   #8, %d3
        movea.l %d1, %a3
        move.l  %d3, (%a2,%d4.l)
        move.l  (%a0,%d0.l), %d3
        asr.l   #8, %d3
        addq.l  #8, %d0
        move.l  %d3, (%a3,%d4.l)
        cmpi.l  #256, %d0
        bne.s   7b
8:      jmp     0x40026098

| 0x40026080 (was: moveq #11,%d4 ; lsl.l %d4,%d1 ; pea 0x800): neither mode 5 nor 6: stock clears the half (d1 = H)
| and goes on at 0x40026098 (d4 = 11, the clear's registers).
        .globl  skl_modex
skl_modex:
        move.l  %d1, %d0
        bsr.w   skl_clr
        move.l  -56(%fp), %d0
        bsr.w   skl_clr_regs
        moveq   #11, %d4
        jmp     0x40026098

| after smp_tdm (csrc/sampler/hooks.S smp_tdm_hook): skl_tx_after(h, sent). A frame that did not come through skl_clr
| (mode 6: Overbridge wrote the half): nobody vouches for that half. Else: a packet sent fills slots 8..15 of every
| frame (link.c's 256 units, RX_WORDS 124); the dirty columns not written this frame are cleared now; the columns
| written this frame become the half's dirty ones. C ABI: d0/d1/a0/a1 free.
        .globl  skl_tx_after
skl_tx_after:
        move.l  4(%sp), %d0                     | h
        tst.l   skl_tx_armed
        bne.s   1f
        move.l  skl_tx_unknown, %d1
        bset    %d0, %d1
        move.l  %d1, skl_tx_unknown
        rts
1:      moveq   #0, %d1
        move.l  %d1, skl_tx_armed
        move.l  skl_tx_written, %d1
        tst.l   8(%sp)
        beq.s   2f
        ori.l   #0xFF00, %d1
2:      move.l  skl_tx_h, %d0
        lea     skl_tx_dirty, %a0
        move.l  %d1, (%a0,%d0.l*4)
        not.l   %d1
        and.l   skl_tx_pending, %d1             | to clear: dirty before, not written now
        moveq   #0, %d0
        move.l  %d0, skl_tx_pending
        move.l  skl_tx_h, %d0
        bra.w   skl_cols                        | (its rts returns to the hook)

| 0x40025576 (was: move.l #0x40025e36,%d0): the audio interrupt installed (power-on, or back from the service
| interrupt 0x400d10f4, which writes the transmit halves itself): nobody vouches for either half.
        .globl  skl_isr_install
skl_isr_install:
        moveq   #3, %d0
        move.l  %d0, skl_tx_unknown
        moveq   #0, %d0
        move.l  %d0, skl_tx_armed
        move.l  #0x40025E36, %d0
        rts

| ---- 8. mode 6's receive-half clear ---------------------------------------------------------------------------
| (2026-11-21, the User's CPU: stock's clear 0x4013419c, 2.4-2.8 % of the CPU on the unit in mode 6, Overbridge
| connected, streaming or not; found by an emulator trace of the interrupt, through stock's indirect jsr (%a2)) at
| 0x400279e8 (was: move.l -56(%fp),%d0 ; moveq #11,%d3 ; pea 0x800): stock then clears the receive half
| (0x4e6e7100 + H << 11, 2 KB, uncached) and the 84 B at 0x800053c0, each through jsr (%a2), a2 = 0x4013419c. Here
| the half as 64 movem.l of 8 zero registers (its 512 long stores ascending, as stock's), the 84 B as 3 movem; the
| four arguments stock pushed left on the stack, its registers and flags as its second clear leaves them (d0 0 from
| -4 + 4, d1 16, a0 0x80005414, a2 0x4013419c, d3 11); on at 0x40027a10.
RX_HALF = 0x4E6E7100
        .globl  skl_rxclr
skl_rxclr:
        move.l  -56(%fp), %d0
        moveq   #11, %d3
        pea     0x800
        lsl.l   %d3, %d0
        addi.l  #RX_HALF, %d0
        move.l  %d0, -(%sp)
        movea.l %d0, %a0
        lea     -20(%sp), %sp
        movem.l %d2/%d4-%d7, (%sp)
        moveq   #0, %d0
        moveq   #0, %d1
        moveq   #0, %d2
        moveq   #0, %d3
        moveq   #0, %d4
        moveq   #0, %d5
        moveq   #0, %d6
        moveq   #0, %d7
        .irp    k, 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63
        movem.l %d0-%d7, 32*\k(%a0)
        .endr
        lea     0x800053C0, %a0
        movem.l %d0-%d7, (%a0)
        movem.l %d0-%d7, 32(%a0)
        movem.l %d0-%d4, 64(%a0)
        movem.l (%sp), %d2/%d4-%d7
        lea     20(%sp), %sp
        pea     0x54
        pea     0x800053C0
        lea     0x80005414, %a0
        lea     0x4013419C, %a2
        moveq   #11, %d3
        moveq   #16, %d1
        moveq   #-4, %d0                        | stock's last: addq.l #4,%d0 on -4: 0, Z C X set
        addq.l  #4, %d0
        jmp     0x40027A10

| ---- 3. mode 5's USB audio out ---------------------------------------------------------------------------------
GETTER  = 0x400253D0
RXB     = 0x4E6E7100
OUT1    = 0x4664C074
| in: d0 = 5, d5 = 5, a2 = 0x40006c4a; fp the interrupt's. Out at 0x40027768 with stock's registers but d6 (dead
| there: written before read up to the rte) and, in stereo, nothing read for the partners.
| The frame on the stack: 0 nd (distinct channels), 4..19 their channels, 20..35 their bases (0: through stock's
| getter), 36..51 the operands' slots (x1, y1, x2, y2: an index 0..4, 4 the zero), 52..71 v[0..4], 72.. the loop-2
| operands (32 x 8 B).
        .equ    F_ND, 0
        .equ    F_CH, 4
        .equ    F_BASE, 20
        .equ    F_IX, 36
        .equ    F_V, 52
        .equ    F_L2, 72
        .equ    F_SIZE, 72 + 256
        .globl  skl_usbout
skl_usbout:
        lea     OUT1, %a4
        tst.b   0x80005362
        bne.s   1f
        clr.l   %d0                             | not streaming: stock's clear of both channels (0x4002777e)
        lea     OUT1 + 4, %a0
2:      clr.l   (%a4,%d0.l)
        clr.l   (%a0,%d0.l)
        addq.l  #8, %d0
        cmpi.l  #256, %d0
        bne.s   2b
        jmp     0x40027768
1:      tst.b   0x80005363
        bne.s   3f
        move.l  #0x80000000, %d3
        clr.l   %d4
        bra.s   4f
3:      move.l  #0xC0000000, %d3
        move.l  %d3, %d4
4:      lea     -F_SIZE(%sp), %sp
        movea.l %sp, %a3                        | the frame
        clr.l   F_ND(%a3)
        clr.l   F_V+16(%a3)                     | v[4] = 0: the operand for a weight of 0
        mvs.b   0x80005364, %d5                 | A
        move.l  %d5, %d0
        bsr.w   skl_ch                          | x1 <- A
        move.l  %d0, F_IX+0(%a3)
        moveq   #4, %d0
        tst.l   %d4
        beq.s   5f
        move.l  %d5, %d0
        addq.l  #1, %d0
        bsr.w   skl_ch                          | y1 <- A + 1 (mono only)
5:      move.l  %d0, F_IX+4(%a3)
        mvs.b   0x80005365, %d5                 | B
        move.l  %d5, %d0
        bsr.w   skl_ch                          | x2 <- B
        move.l  %d0, F_IX+8(%a3)
        moveq   #4, %d0
        tst.l   %d4
        beq.s   6f
        move.l  %d5, %d0
        subq.l  #1, %d0
        bsr.w   skl_ch                          | y2 <- B - 1 (mono only)
6:      move.l  %d0, F_IX+12(%a3)
        | loop 1: per frame the distinct channels read once, then stock's two MACs (A's by d3, A+1's by d4), the store
        clr.l   %d2                             | the frame i
7:      bsr.w   skl_reads
        move.l  F_IX+0(%a3), %d0
        move.l  F_V(%a3,%d0.l*4), %d6
        move.l  F_IX+4(%a3), %d0
        move.l  F_V(%a3,%d0.l*4), %d0
        msac.l  %d3, %d6, %acc0
        msac.l  %d4, %d0, %acc0
        movclr.l %acc0, %d0
        move.l  %d2, %d1
        lsl.l   #3, %d1
        move.l  %d0, (%a4,%d1.l)
        move.l  F_IX+8(%a3), %d0                | loop 2's operands kept for its pass
        move.l  F_V(%a3,%d0.l*4), %d0
        move.l  %d0, F_L2(%a3,%d1.l)
        move.l  F_IX+12(%a3), %d0
        move.l  F_V(%a3,%d0.l*4), %d0
        move.l  %d0, F_L2+4(%a3,%d1.l)
        addq.l  #1, %d2
        moveq   #32, %d0
        cmp.l   %d2, %d0
        bne.s   7b
        | loop 2: B's by d3, then B-1's by d4 (stock's order), the store at 0x4664c078 + 8 i
        lea     OUT1 + 4, %a2
        clr.l   %d2
8:      move.l  %d2, %d1
        lsl.l   #3, %d1
        move.l  F_L2(%a3,%d1.l), %d0
        move.l  F_L2+4(%a3,%d1.l), %d6
        addq.l  #8, %a2
        msac.l  %d3, %d0, %acc0
        msac.l  %d4, %d6, %acc0
        movclr.l %acc0, %d0
        move.l  %d0, -8(%a2)
        addq.l  #1, %d2
        moveq   #32, %d1
        cmp.l   %d2, %d1
        bne.s   8b
        | stock's registers after its last getter call (B, frame 31): a0, a1; d5 = B, d7 = B - 1, a3 the getter
        move.l  %d5, %d7
        subq.l  #1, %d7
        moveq   #13, %d6
        cmp.l   %d5, %d6
        blt.s   9f
        lea     RXB, %a0
        lea     -56(%fp), %a1
        bra.s   10f
9:      lea     0x800053A4, %a0
        move.l  %d5, %d6
        addi.l  #-14, %d6
        asr.l   #1, %d6
        movea.l %d6, %a1
        adda.l  %d6, %a1
        adda.l  %d6, %a1                        | 3 x ((B - 14) >> 1), as the getter's lea
10:     lea     F_SIZE(%sp), %sp
        lea     GETTER, %a3
        jmp     0x40027768

| skl_ch: channel D0 -> its index among this frame's distinct channels (added when new). Keeps d2-d7/a2-a4.
skl_ch:
        move.l  F_ND+4(%sp), %d1                | (the frame is at 4(%sp): our return address under it)
        lea     4(%sp), %a0
        moveq   #0, %d6
        bra.s   2f
1:      cmp.l   F_CH(%a0,%d6.l*4), %d0
        beq.s   9f
        addq.l  #1, %d6
2:      cmp.l   %d1, %d6
        bne.s   1b
        move.l  %d0, F_CH(%a0,%d6.l*4)          | new: its base, or 0 for stock's getter (channels 14 and up)
        addq.l  #1, %d1
        move.l  %d1, F_ND(%a0)
        moveq   #13, %d1
        cmp.l   %d0, %d1
        blt.s   3f
        move.l  -56(%fp), %d1                   | the getter's address: RXB + 4 (ch + 16 (i + 32 h)), here i = 0
        lsl.l   #5, %d1
        lsl.l   #4, %d1
        add.l   %d0, %d1
        lsl.l   #2, %d1
        addi.l  #RXB, %d1
        move.l  %d1, F_BASE(%a0,%d6.l*4)
        bra.s   9f
3:      clr.l   F_BASE(%a0,%d6.l*4)
9:      move.l  %d6, %d0
        rts

| skl_reads: frame D2's distinct channels into v[]: an uncached read << 8 (the getter's), or stock's getter
skl_reads:
        lea     4(%sp), %a0
        move.l  F_ND(%a0), %d6
        subq.l  #1, %d6
1:      move.l  F_BASE(%a0,%d6.l*4), %d0
        beq.s   2f
        move.l  %d2, %d1
        lsl.l   #6, %d1
        movea.l %d0, %a1
        move.l  (%a1,%d1.l), %d0
        lsl.l   #8, %d0
        move.l  %d0, F_V(%a0,%d6.l*4)
        bra.s   3f
2:      move.l  %d6, -(%sp)
        move.l  %a0, -(%sp)
        move.l  %d2, -(%sp)                     | the frame
        move.l  F_CH(%a0,%d6.l*4), -(%sp)       | the channel
        lea     -56(%fp), %a1
        jsr     GETTER
        addq.l  #8, %sp
        movea.l (%sp)+, %a0
        move.l  (%sp)+, %d6
        move.l  %d0, F_V(%a0,%d6.l*4)
3:      subq.l  #1, %d6
        bge.s   1b
        rts

        .data
        .align  2
        .globl  skl_tx_dirty, skl_tx_unknown, skl_tx_pending, skl_tx_written, skl_tx_armed, skl_tx_h
skl_tx_dirty:   .long   0, 0                    | per half: the columns written at its last use (bit c: slot c)
skl_tx_unknown: .long   3                       | bit h: half h must be cleared whole (power-on: both)
skl_tx_pending: .long   0                       | this frame's half: its dirty columns, to clear after smp_tdm
skl_tx_written: .long   0                       | this frame's half: the columns written
skl_tx_armed:   .long   0                       | 1 from skl_clr to skl_tx_after (a frame that cleared)
skl_tx_h:       .long   0
#endif
