| The preset browser's ENGINE filter (csrc/presets/engfilt.c, dnfw.waverider.engfilt): stock 1.12's sites, each
| entered by a jmp (a jsr for the constructor) and continued where it was, stock's replaced instructions replayed.

        .text

| 0x400ac9a8, the preset list's rebuild after the bank test (was: tst.b 1413(%a4) ; beq.s 0x400ac9ba, MIDI's test):
| a4 the view, d3 the slot. An engine set: eng_match(lib, slot); a preset out of it goes to 0x400ac9bc with d0 = 0,
| as stock's own failed test leaves it. Then (no set, or in it) stock's MIDI test as it was. d0/d1/a0/a1 are free.
        .globl  eng_test_hook
eng_test_hook:
        tst.l   eng_mask
        beq.s   3f
        jsr     0x4018E0A8                      | the preset library (stock's a2 here)
        move.l  %d3, -(%sp)
        move.l  %d0, -(%sp)
        jsr     eng_match
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   3f
        jmp     0x400AC9BC
3:      tst.b   1413(%a4)
        beq.s   2f
        jmp     0x400AC9AE
2:      jmp     0x400AC9BA

| 0x400ad194, the SORTING menu's builder after FILTER's row, before SEARCH's (was: pea 4 ; clr.l -56(%fp)): a2 the
| view. eng_sort_row(view) adds ENGINE's row; then the replaced instructions, and on to SEARCH's row.
        .globl  eng_sort_hook
eng_sort_hook:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a2, -(%sp)
        jsr     eng_sort_row
        addq.l  #4, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        pea     4
        clr.l   -56(%fp)
        jmp     0x400AD19C

| the label invokers: a0 the std::string to construct, 4(%sp) the closure's storage; the text, then the string from it
| as stock's labels make theirs (0x401ceab8(string, text, &allocator)); d0 = the string, as stock returns it.
        .globl  eng_label
eng_label:
        move.l  %a0, -(%sp)
        move.l  8(%sp), %a1
        move.l  (%a1), %a1
        move.l  4(%a1), -(%sp)
        jsr     eng_name                        | the row's name
        addq.l  #4, %sp
        bra.s   1f
        .globl  eng_title
eng_title:
        move.l  %a0, -(%sp)
        jsr     eng_title_text                  | "ENGINE *" / "ENGINE  "
1:      move.l  (%sp), %a0
        subq.l  #4, %sp                         | the allocator's byte
        pea     3(%sp)
        move.l  %d0, -(%sp)
        move.l  %a0, -(%sp)
        jsr     0x401CEAB8
        lea     16(%sp), %sp
        move.l  (%sp)+, %d0
        rts

| 0x400ac62c, the view's constructor clearing its filters (was: move.b %d1,1412(%a2) ; move.b %d1,1413(%a2); now
| jsr here + nop): the engines with them
        .globl  eng_ctor_hook
eng_ctor_hook:
        move.b  %d1, 1412(%a2)
        move.b  %d1, 1413(%a2)
        clr.l   eng_mask
        rts
