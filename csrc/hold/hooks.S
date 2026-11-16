| DRONE's HOLD (csrc/hold/hold.c). 0x40026afc, the frame ISR's note-on (was: move.l %d2,%d0 ;
| addi.l #1484,%d0 ; move.l %a4,(%a3,%d0.l*4), 12 bytes; now jsr here + 3 nops): d2 the voice, d3 the
| track, a4 the gate length, a3 0x80003af0, d6 the voice's bit. a4 = hold_len(voice, track, a4) (the
| filter's gate, set from a4 at 0x40026ba8, follows); -1 drops the note-on: d6 = 0 (0x40026b0c ORs d6
| into the note-on mask) and a gate of 1. Then the three instructions replayed; d1/a0/a1 as they came.
        .text
        .globl  hold_note_hook
hold_note_hook:
        lea     -12(%sp), %sp
        movem.l %d1/%a0-%a1, (%sp)
        move.l  %a4, -(%sp)
        move.l  %d3, -(%sp)
        move.l  %d2, -(%sp)
        jsr     hold_len
        lea     12(%sp), %sp
        tst.l   %d0
        bpl.s   1f
        moveq   #0, %d6                         | -1: the same key again on a latch: no note-on bit
        moveq   #1, %d0                         | (nor filter/LFO trig, all from d6) and a gate of 1:
1:      movea.l %d0, %a4                        | its voice freed at the next ISR
        movem.l (%sp), %d1/%a0-%a1
        lea     12(%sp), %sp
        move.l  %d2, %d0
        addi.l  #1484, %d0
        move.l  %a4, (%a3,%d0.l*4)
        rts

| The frame ISR's note-off words as composed (2026-11-10): the frame's +36 is the register d3 and its +40
| fp@(-164) (stored at 0x400274ae / 0x400274a8). At 0x40027092 the stock jsr 0x4002b12e follows their
| composition, the ISR's frame pointer %a6 still its own. d3 and -164(%a6) through hold_final (the latched
| voices' bits out, the let-go voices' in), then 0x4002b12e as if called from the ISR (a jmp: its rts
| returns there). d0/d1/a0/a1 as they came.
        .globl  hold_final_hook
hold_final_hook:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        pea     -164(%a6)
        move.l  %d3, -(%sp)
        jsr     hold_final
        addq.l  #8, %sp
        move.l  %d0, %d3
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        jmp     0x4002b12e
