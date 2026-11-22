| The per-track inserts' ColdFire hook (csrc/inserts/ins.c; docs/inserts.md), OS 1.12.
|
| Stock's mode header 0x40063f56(mode), a0 the std::string it returns, ends at 0x40063fcc:
|     move.l %a3,%d0 ; movea.l (%sp)+,%a2 ; movea.l (%sp)+,%a3 ; addq.l #4,%sp ; rts
| The first three (6 bytes, also the target of its bge for a one-page mode) are now
| `jsr ins_hdr_tail`: ins_header(a3) renames a bare "FX", then the three are replayed and the
| jsr's return (0x40063fd2: addq.l #4,%sp ; rts) finishes as stock. d1, a0, a1 are scratch at
| that exit (stock leaves them as its last calls did); d0 is the string's address, as stock's.

        .text
        .globl  ins_hdr_tail
ins_hdr_tail:
        move.l  %a3, -(%sp)
        jsr     ins_header
        addq.l  #4, %sp
        move.l  %a3, %d0                | the replayed three
        movea.l (%sp)+, %a0             | the jsr's return
        movea.l (%sp)+, %a2
        movea.l (%sp)+, %a3
        jmp     (%a0)

| 2026-11-10, the inserts saved with the project (csrc/inserts/store.c): stock's project write
| 0x40040190(project, slot, cb), its entry (was: lea -52(%sp),%sp ; movem.l %d2-%d4/%a2-%fp,(%sp),
| 8 bytes; the same in 1.11 and 1.12): replayed, then the slot (60(%sp) after them, as stock reads it)
| noted in store.c's ring for the UI pass, and on at 0x40040198. d0, d1, a0 are scratch at a C
| function's entry.
        .globl  ins_pj_write_hook
ins_pj_write_hook:
        lea     -52(%sp), %sp
        movem.l %d2-%d4/%a2-%a6, (%sp)
        move.l  60(%sp), %d0
        move.l  ins_wr_head, %d1
        andi.l  #7, %d1
        lea     ins_wr_ring, %a0
        move.l  %d0, (%a0,%d1.l*4)
        addq.l  #1, ins_wr_head
        jmp     0x40040198

| ---- the inserts' live words (2026-11-21, the User's CPU: "assembly for the most host CPU code") ----------------
| ins_live4(c, o, zero, f0, rmask, v): ins.c live_words for the four records of one group, as the C did it (gcc made
| clamp7 a call a routed knob, and its index arithmetic mulsl): v[2k], v[2k + 1] for record k (0..3) from its 7 cells
| c[14 k ..] (u16: SET << 8), the routes' offsets o[14 k ..] (s16), zero[k] (MIX's OFF: both words 0), f0[k] (field 0)
| and rmask[k] (bit i: knob i routed). A knob routed: clamp7(c + o) (<= 0: 0, >= 0x7f00: 0x7f, else >> 8); not
| routed: c >> 8. Word a = f0 | MIX << 7 | K1 << 14 | K2 << 21, word b = K3 | K4 << 7 | K5 << 14 | K6 << 21.
| C ABI: d0, d1, a0, a1 scratch; the rest kept.
        .macro  LIVE i
        mvz.w   2*\i(%a0), %d0
        btst    #\i, %d3
        beq.s   1f
        mvs.w   2*\i(%a1), %d1
        add.l   %d1, %d0
        ble.s   2f
        cmpi.l  #0x7F00, %d0
        blt.s   1f
        moveq   #0x7F, %d0
        bra.s   3f
2:      moveq   #0, %d0
        bra.s   3f
1:      lsr.l   #8, %d0
3:
        .endm
        .globl  ins_live4
ins_live4:
        lea     -28(%sp), %sp
        movem.l %d2-%d6/%a2-%a3, (%sp)
        movem.l 32(%sp), %a0-%a1                | c, o
        movea.l 52(%sp), %a2                    | v
        movea.l 40(%sp), %a3                    | zero
        moveq   #14, %d5
        moveq   #21, %d6
        moveq   #0, %d2                         | k
4:      tst.b   (%a3,%d2.l)
        beq.s   5f
        clr.l   (%a2)+                          | MIX's OFF: every field 0
        clr.l   (%a2)+
        bra.w   6f
5:      movea.l 48(%sp), %a3                    | rmask[k]
        mvz.b   (%a3,%d2.l), %d3
        movea.l 44(%sp), %a3                    | f0[k]
        mvz.b   (%a3,%d2.l), %d4
        movea.l 40(%sp), %a3
        LIVE    6
        lsl.l   #7, %d0
        or.l    %d0, %d4
        LIVE    0
        lsl.l   %d5, %d0
        or.l    %d0, %d4
        LIVE    1
        lsl.l   %d6, %d0
        or.l    %d0, %d4
        move.l  %d4, (%a2)+
        LIVE    2
        move.l  %d0, %d4
        LIVE    3
        lsl.l   #7, %d0
        or.l    %d0, %d4
        LIVE    4
        lsl.l   %d5, %d0
        or.l    %d0, %d4
        LIVE    5
        lsl.l   %d6, %d0
        or.l    %d0, %d4
        move.l  %d4, (%a2)+
6:      lea     14(%a0), %a0
        lea     14(%a1), %a1
        addq.l  #1, %d2
        cmpi.l  #4, %d2
        bne.w   4b
        movem.l (%sp), %d2-%d6/%a2-%a3
        lea     28(%sp), %sp
        rts
