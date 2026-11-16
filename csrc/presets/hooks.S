| The preset browser's ENGINE filter (csrc/presets/engfilt.c, dnfw.waverider.engfilt): stock 1.12's sites, each
| entered by a jmp (a jsr for the constructor) and continued where it was, stock's replaced instructions replayed.

        .text

| 0x400ac9a8, the preset list's rebuild after the bank test (was: tst.b 1413(%a4) ; beq.s 0x400ac9ba, MIDI's test):
| a4 the view, d3 the slot. No engine set: stock's MIDI test as it was. A set: d0 = eng_match(lib, slot, view),
| then 0x400ac9bc as stock's own test leaves it (d0's byte: keep or not). d0/d1/a0/a1 are free there.
        .globl  eng_test_hook
eng_test_hook:
        tst.l   eng_mask
        bne.s   1f
        tst.b   1413(%a4)
        beq.s   2f
        jmp     0x400AC9AE
2:      jmp     0x400AC9BA
1:      jsr     0x4018E0A8                      | the preset library (stock's a2 here)
        move.l  %a4, -(%sp)
        move.l  %d3, -(%sp)
        move.l  %d0, -(%sp)
        jsr     eng_match
        lea     12(%sp), %sp
        jmp     0x400AC9BC

| 0x400abad8, the FILTER list's builder after its 32 tag rows, before MIDI's (was: move.l (%a2),%d6 ;
| clr.l 52(%sp)): a2 the closure holding the view. One row per engine, as stock makes a tag row (0x400ab9f2):
| three std::functions {heap {view, row}, manager 0x400a9950, invoker} (label, YES, tick) and an empty fourth,
| the item (0x54 B, 0x401173b8(item, f1, f2, f3, f4, -1, 8)) added to the view's list (0x40116bee(view+448, item)),
| the four destroyed (0x40188366). Then the replaced instructions, and on to MIDI's row.
        .globl  eng_rows_hook
eng_rows_hook:
        lea     -40(%sp), %sp
        movem.l %d2-%d7/%a2-%a5, (%sp)
        move.l  (%a2), %a5                      | the view
        moveq   #0, %d7                         | the row
3:      cmp.l   eng_n, %d7
        bge     9f
        lea     -64(%sp), %sp                   | f1 0, f2 16, f3 32, f4 48
        move.l  %sp, %a4
        clr.l   56(%a4)                         | f4: empty (no manager)
        clr.l   60(%a4)
        lea     (%a4), %a3
        move.l  #eng_label, %d2
        bsr     5f
        lea     16(%a4), %a3
        move.l  #eng_toggle, %d2
        bsr     5f
        lea     32(%a4), %a3
        move.l  #eng_tick, %d2
        bsr     5f
        pea     0x54
        jsr     0x40120544                      | operator new
        addq.l  #4, %sp
        move.l  %d0, %d6                        | the item
        moveq   #8, %d0
        move.l  %d0, -(%sp)
        moveq   #-1, %d0
        move.l  %d0, -(%sp)
        pea     48(%a4)
        pea     32(%a4)
        pea     16(%a4)
        pea     (%a4)
        move.l  %d6, -(%sp)
        jsr     0x401173B8
        lea     28(%sp), %sp
        move.l  %d6, -(%sp)
        pea     448(%a5)
        jsr     0x40116BEE
        addq.l  #8, %sp
        pea     48(%a4)
        jsr     0x40188366
        pea     32(%a4)
        jsr     0x40188366
        pea     16(%a4)
        jsr     0x40188366
        pea     (%a4)
        jsr     0x40188366
        lea     16(%sp), %sp
        lea     64(%sp), %sp
        addq.l  #1, %d7
        bra     3b
9:      movem.l (%sp), %d2-%d7/%a2-%a5
        lea     40(%sp), %sp
        move.l  (%a2), %d6
        clr.l   52(%sp)
        jmp     0x400ABADE
| one std::function at a3: invoker d2, closure {a5, d7}
5:      pea     8
        jsr     0x40120544
        addq.l  #4, %sp
        move.l  %d0, %a0
        move.l  %a5, (%a0)
        move.l  %d7, 4(%a0)
        move.l  %d0, (%a3)
        clr.l   4(%a3)
        move.l  #0x400A9950, %d0                | stock's manager for an 8-byte closure
        move.l  %d0, 8(%a3)
        move.l  %d2, 12(%a3)
        rts

| the label invoker: a0 the std::string to construct, 4(%sp) the closure's storage. eng_name(row), then the string
| from it as stock's labels make theirs (0x401ceab8(string, text, &allocator)); d0 = the string, as stock returns it.
        .globl  eng_label
eng_label:
        move.l  %a0, -(%sp)
        move.l  8(%sp), %a1
        move.l  (%a1), %a1
        move.l  4(%a1), -(%sp)
        jsr     eng_name
        addq.l  #4, %sp
        move.l  (%sp), %a0
        subq.l  #4, %sp                         | the allocator's byte
        pea     3(%sp)
        move.l  %d0, -(%sp)
        move.l  %a0, -(%sp)
        jsr     0x401CEAB8
        lea     16(%sp), %sp
        move.l  (%sp)+, %d0
        rts

| 0x400a900e, <CLEAR>'s action (was: movea.l 4(%sp),%a0 ; clr.b %d0): the engines too, then stock's (tags, NO TAG,
| MIDI cleared, the list rebuilt)
        .globl  eng_clear_hook
eng_clear_hook:
        clr.l   eng_mask
        movea.l 4(%sp), %a0
        clr.b   %d0
        jmp     0x400A9014

| 0x400a90de, FILTER's label (was: tst.b 1413(%a1) ; beq.s 0x400a90e8): "*" when an engine is ticked too
        .globl  eng_star_hook
eng_star_hook:
        tst.b   1413(%a1)
        bne.s   1f
        tst.l   eng_mask
        bne.s   1f
        jmp     0x400A90E8
1:      jmp     0x400A90E4

| 0x400ac62c, the view's constructor clearing its filters (was: move.b %d1,1412(%a2) ; move.b %d1,1413(%a2); now
| jsr here + nop): the engines with them
        .globl  eng_ctor_hook
eng_ctor_hook:
        move.b  %d1, 1412(%a2)
        move.b  %d1, 1413(%a2)
        clr.l   eng_mask
        rts
