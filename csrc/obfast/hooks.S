| Stock's Overbridge streaming path, the same bytes with less work (OS 1.12; the User 2026-11-18, the rules of
| csrc/stocklink: bit-identical, behind its own flag). Measured on the DN2 (v0.59.1, Overbridge streaming,
| scratch/unit-now/para-cpu/prof/rest2.md): stock's memcpy 0x40134770 takes 8.1 % of the CPU there, almost all of it
| called from the two loops below, a call for every 56, 84 or 32 bytes (96 calls a frame).
|
| 1. obf_build_pair (0x40003264, the whole sample loop of the mode-6 packet builder 0x40003118; 2026-11-21, was its body): each sample of a USB packet
|    entry (140 B) is the receive slots 0..13 of its frame (56 B from the uncached TDM receive half) and its 84 B of
|    reply records, through stock's memcpy twice (its call, its register save, 16-byte blocks). Here both copies
|    straight, in 32-byte movem blocks, then the iteration's own steps (d6 += 84, a4 += 140, d7 += 1); the registers
|    stock's memcpy leaves (d0 the last dst, d1 16, a0/a1 past the last copy's ends) as it leaves them. The edit's
|    bra.s goes to the loop's top (0x40003264), as the loop's own bras did.
| 2. obf_in32 (0x40003492, the frame loop of the Overbridge input 0x40003376): each frame of the DAW's audio, 32 B
|    from the USB buffer into TX slots 0..7 of the transmit half, through stock's memcpy. Here one 32-byte movem,
|    then the loop's d5 += 1; registers as stock's memcpy leaves them; the edit's bra.s to the loop's top 0x40003480.
| A copy whose two areas overlap (|dst - src| under its length) goes through stock's memcpy, as stock: there the
| block size could change its bytes.
| Proofs: scripts/check_stocklink.py obbuild / obin; the gate's linkfast covers these sites too.
|
| Only with DN2_OB_FAST (dnfw.waverider.pages.ob_fast_on, on by default, apart from DN2_STOCK_LINK_FAST so that it
| can be rolled back alone): off, nothing here is built and no stock site is edited.

#if DN2_OB_FAST
MEMCPY  = 0x40134770

        .text
| ---- 1. the packet builder's samples ---------------------------------------------------------------------------
| (2026-11-21, the User's CPU: the whole loop, not each sample) entered by a jmp at the loop's top 0x40003264 (stock:
| move.l %d7,%d0 ; lsl.l #6,%d0 ; add.l 44(%sp),%d0 ; cmp.l %d7,%d3 ; ble.s 0x400032ae), d7 the sample (0 at the first
| entry), d3 the count, a4 the entry, d6 the records, 44(%sp) the receive frames' base. Each sample: its receive frame
| (d7 << 6 + 44(%sp), 56 B to a4) and its 84 B of reply records (d6, to a4 + 56) straight in 32-byte movem blocks, or
| through stock's memcpy twice when either copy overlaps (as before), then the iteration's own steps (d6 += 84,
| a4 += 140, d7 += 1). The registers saved once for the loop (was: once a sample, with a call and a branch a sample).
| Out at 0x400032ae as stock leaves the loop: d0 = d7 << 6 + 44(%sp); after a sample d1 16, a0 / a1 past the last
| copy's ends (stock's memcpy's); none: d1, a0, a1 untouched.
        .globl  obf_build_pair
obf_build_pair:
        lea     -28(%sp), %sp
        movem.l %d2-%d5/%a2-%a3/%a5, (%sp)      | d3 (the count) at 4(%sp); the builder's 44(%sp) at 72(%sp)
1:      cmp.l   4(%sp), %d7                     | stock: cmp.l %d7,%d3 ; ble.s (the count <= d7: out)
        bge.w   9f
        move.l  %d7, %d0                        | the receive frame
        lsl.l   #6, %d0
        add.l   72(%sp), %d0
        move.l  %a4, %d1                        | an overlap of copy 1: |a4 - d0| < 56
        sub.l   %d0, %d1
        bpl.s   2f
        neg.l   %d1
2:      cmpi.l  #56, %d1
        bcs.w   8f
        move.l  %a4, %d1                        | of copy 2: |a4 + 56 - d6| < 84
        addi.l  #56, %d1
        sub.l   %d6, %d1
        bpl.s   3f
        neg.l   %d1
3:      cmpi.l  #84, %d1
        bcs.w   8f
        movea.l %d0, %a0                        | 56 bytes: 32 + 24
        movem.l (%a0), %d1-%d5/%a2-%a3/%a5
        movem.l %d1-%d5/%a2-%a3/%a5, (%a4)
        movem.l 32(%a0), %d1-%d5/%a2
        movem.l %d1-%d5/%a2, 32(%a4)
        movea.l %d6, %a0                        | 84 bytes: 32 + 32 + 20
        lea     56(%a4), %a1
        movem.l (%a0), %d1-%d5/%a2-%a3/%a5
        movem.l %d1-%d5/%a2-%a3/%a5, (%a1)
        movem.l 32(%a0), %d1-%d5/%a2-%a3/%a5
        movem.l %d1-%d5/%a2-%a3/%a5, 32(%a1)
        movem.l 64(%a0), %d1-%d5
        movem.l %d1-%d5, 64(%a1)
        moveq   #16, %d1                        | stock's memcpy after the second copy: d1 16, a0 and a1 past the ends
        lea     84(%a0), %a0
        lea     84(%a1), %a1
        bra.s   7f
8:      pea     0x38                            | an overlap: stock's two calls, as stock makes them
        move.l  %d0, -(%sp)
        move.l  %a4, -(%sp)
        jsr     MEMCPY
        pea     0x54
        move.l  %d6, -(%sp)
        pea     56(%a4)
        jsr     MEMCPY
        lea     24(%sp), %sp
7:      addi.l  #84, %d6                        | the iteration's own steps (0x40003286..0x40003290)
        lea     140(%a4), %a4
        addq.l  #1, %d7
        bra.w   1b
9:      movem.l (%sp), %d2-%d5/%a2-%a3/%a5
        lea     28(%sp), %sp
        move.l  %d7, %d0                        | as stock's loop top leaves d0
        lsl.l   #6, %d0
        add.l   44(%sp), %d0
        jmp     0x400032AE

| ---- 2. the Overbridge input's frame ---------------------------------------------------------------------------
| in: d0 the frame's TX slots (dst), a1 its 32 B in the USB buffer (src), d5 the frame
        .globl  obf_in32
obf_in32:
        move.l  %d0, %d1                        | an overlap: |d0 - a1| < 32
        sub.l   %a1, %d1
        bpl.s   1f
        neg.l   %d1
1:      cmpi.l  #32, %d1
        bcs.s   8f
        lea     -28(%sp), %sp
        movem.l %d2-%d5/%a2-%a3/%a5, (%sp)
        movea.l %a1, %a0
        movea.l %d0, %a1
        movem.l (%a0), %d1-%d5/%a2-%a3/%a5
        movem.l %d1-%d5/%a2-%a3/%a5, (%a1)
        movem.l (%sp), %d2-%d5/%a2-%a3/%a5
        lea     28(%sp), %sp
        moveq   #16, %d1                        | stock's memcpy after it: d0 dst, d1 16, a0/a1 past the ends
        lea     32(%a0), %a0
        lea     32(%a1), %a1
        bra.s   9f
8:      pea     0x20                            | an overlap: stock's call
        move.l  %a1, -(%sp)
        move.l  %d0, -(%sp)
        jsr     MEMCPY
        lea     12(%sp), %sp
9:      addq.l  #1, %d5                         | the loop's own step (0x4000349c)
        rts

| ---- 3. the Overbridge input's clear --------------------------------------------------------------------------
| (2026-11-21, the User's CPU: stock's clear 0x4013419c took 2.4-2.8 % of the CPU on the unit in mode 6, Overbridge
| connected, streaming or not; an emulator trace of the interrupt found its two 2 KB callers: this one and
| csrc/stocklink skl_rxclr) entered by a jsr at 0x40003414 in place of stock's jsr 0x4013419c (a4, d2 << 6): the
| transmit half's first d2 frames zeroed. A whole number of 64 B (n > 0) at a long-aligned address: two 32-byte
| movem of 8 zero registers a turn, ascending (stock: 4 clr.l and a 2-instruction loop a 16 B); then stock's
| registers and flags as its clear leaves them for n a multiple of 16 (d0 0 from -16 + 16, d1 16, a0 the end). Any
| other n or address: stock's clear.
        .globl  obf_clr
obf_clr:
        movea.l 4(%sp), %a0                     | dst
        move.l  8(%sp), %d0                     | n
        moveq   #63, %d1
        and.l   %d0, %d1
        bne.s   8f                              | not whole 64 B
        tst.l   %d0
        ble.s   8f                              | nothing to clear (stock: no store)
        move.l  %a0, %d1
        andi.l  #3, %d1
        bne.s   8f                              | not long-aligned
        lea     -28(%sp), %sp
        movem.l %d2-%d7/%a1, (%sp)
        lea     (%a0,%d0.l), %a1                | the end
        moveq   #0, %d0
        moveq   #0, %d1
        moveq   #0, %d2
        moveq   #0, %d3
        moveq   #0, %d4
        moveq   #0, %d5
        moveq   #0, %d6
        moveq   #0, %d7
1:      movem.l %d0-%d7, (%a0)
        movem.l %d0-%d7, 32(%a0)
        lea     64(%a0), %a0
        cmpa.l  %a1, %a0
        bne.s   1b
        movem.l (%sp), %d2-%d7/%a1
        lea     28(%sp), %sp
        moveq   #16, %d1                        | stock's last two: sub.l %d1,%d0 (-16), then add.l %d1,%d0: 0, its
        moveq   #-16, %d0                       | flags (Z, C, X set)
        add.l   %d1, %d0
        rts
8:      jmp     0x4013419C
#endif
