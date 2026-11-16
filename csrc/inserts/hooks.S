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
