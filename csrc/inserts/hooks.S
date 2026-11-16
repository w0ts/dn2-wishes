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
