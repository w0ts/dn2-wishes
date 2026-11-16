| The profiler's timer interrupt (csrc/devtest/prof.c, docs/remote-ui.md "The CPU profiler"): vector 96,
| DMA timer 0's reference compare, at level 6; installed by PROFILE START, put back by STOP.
| On entry SP points at the exception frame (u16 format/vector, u16 SR, u32 PC); the C's scratch
| registers (d0, d1, a0, a1) are kept, prof_tick reads the frame and returns, rte resumes the
| interrupted code with its SR.

        .text
        .globl  prof_isr
prof_isr:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        pea     16(%sp)                 | the frame
        jsr     prof_tick
        addq.l  #4, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        rte
