| sm_snap (2026-11-18, the User's CPU: a step that starts a note on many tracks at once): stock's smoother snap
| 0x400daffc, entered there by a jmp. At a voice's note stock sets the voice's 101 smoother state words (0x8000dea4 +
| 404 x voice) to the voice's new targets << 16, one halfword of %a0 each: a loop of 9 instructions a word (909 a
| call, up to 16 calls in one frame). Here the same 101 words in the same order, 4 instructions each, and the
| registers as stock's loop leaves them: %d0 and %a1 past the last word, %d1 202, %a0 the argument, %d2 restored
| (its move sets the flags last, as stock's does; X is left clear by the address add, as stock's last addq leaves it).
        .text
        .globl  sm_snap
sm_snap:
        move.l  %d2, -(%sp)
        move.l  8(%sp), %d0             | the voice
        movea.l 12(%sp), %a0            | its 101 targets
        move.l  #202, %d1
        muls.l  %d1, %d0
        add.l   %d0, %d0
        addi.l  #0x8000dea4, %d0
        movea.l %d0, %a1
        .rept   101
        move.w  (%a0)+, %d2             | stock: mvs.w (%a0,%d1.l),%d2 ; swap ; clr.w: the same word in the high half
        swap    %d2
        clr.w   %d2
        move.l  %d2, (%a1)+
        .endr
        lea     -202(%a0), %a0
        move.l  %a1, %d0
        move.l  (%sp)+, %d2
        rts
