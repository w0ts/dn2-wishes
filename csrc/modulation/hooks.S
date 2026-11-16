| LFOs modulating the LFOs above them: the hooks in stock code (csrc/modulation/cascade.c,
| docs/modulation-more.md). Sites: dnfw.waverider.coldfire (MOD_*).

        .text

| The destination-list builder 0x4003951e calls its mask lookup as jsr (%a2) with the record
| on the stack (0x400395a0); its own second argument, want, is then at 60(%sp) here (the
| builder's frame: 44 + its return + the record + our return). In place of page.c's
| wr_lfo_mask at the builder's lea 0x40039570: mod_lfo_mask(record, want).
        .globl  mod_mask_hook
mod_mask_hook:
        move.l  60(%sp), -(%sp)
        move.l  8(%sp), -(%sp)
        jsr     mod_lfo_mask
        addq.l  #8, %sp
        rts

| 0x400272d4 (was: jsr 0x40137a06, the LFO evaluator, its seven arguments on the stack):
| mod_eval_pre, then on into the evaluator with the stack as the caller left it. The caller
| treats d0-d1/a0-a1 as the evaluator's scratch.
        .globl  mod_eval
mod_eval:
        jsr     mod_eval_pre
        jmp     0x40137a06

| 0x40137d7a, the evaluator's write of one LFO into its DEST cell (was: movea.l 52(%sp),%a0 ;
| mvs.w 82(%a4),%d1, 8 bytes; now jsr here + nop). d7 is DEST (0..100, bound-checked), a5 the
| voice row, 52(%sp) here the LFO counter (2 LFO3 .. 0 LFO1), 56(%sp) the row's slot 0.
| a0 comes back as the base the stock read-add-clamp-store uses; d0, the LFO's scaled value
| still to be multiplied, and every other register as it came. A DEST that is not a higher
| LFO's control takes the short way (at most 14 instructions): only a lower LFO's write into a
| higher one's control calls mod_wb_cell, at most twice a voice row (LFO1, LFO2) a frame.
        .globl  mod_wb
mod_wb:
        movea.l 56(%sp), %a0
        moveq   #8, %d1
        cmp.l   %d7, %d1
        bcc.s   1f
        moveq   #24, %d1
        cmp.l   %d7, %d1
        bcs.s   1f
        move.l  %d7, %d1
        subq.l  #1, %d1
        lsr.l   #3, %d1                 | the LFO whose control DEST is (1 LFO2, 2 LFO3)
        cmp.l   52(%sp), %d1
        ble.s   1f                      | not above this one: stock's write, heard this frame
        move.l  %d0, -(%sp)
        move.l  %a1, -(%sp)
        move.l  %a0, -(%sp)
        move.l  %d7, -(%sp)
        move.l  68(%sp), -(%sp)
        move.l  %a5, -(%sp)
        jsr     mod_wb_cell
        lea     16(%sp), %sp
        movea.l %d0, %a0
        movea.l (%sp)+, %a1
        move.l  (%sp)+, %d0
1:      mvs.w   82(%a4), %d1
        rts
