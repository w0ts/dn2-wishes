| LIVE SELECT's row in SETTINGS > PERSONALIZE (csrc/msel/live.c).

        .text

| 0x400987a2, the end of PersonalizeMenuView's constructor, after its last row (was: movem.l 24(%sp),%d2-%d6/%a2-%a6;
| lea 128(%sp),%sp ; rts, entered by a jmp): a4 the view. live_row(view), then stock's epilogue.
        .globl  live_menu_hook
live_menu_hook:
        move.l  %a4, -(%sp)
        jsr     live_row
        addq.l  #4, %sp
        movem.l 24(%sp), %d2-%d6/%a2-%a6
        lea     128(%sp), %sp
        rts

| the label invoker: a0 the std::string to construct; live_text(), then the string as stock's labels make theirs
| (0x401ceab8(string, text, &allocator)); d0 = the string
        .globl  live_label
live_label:
        move.l  %a0, -(%sp)
        jsr     live_text
        move.l  (%sp), %a0
        subq.l  #4, %sp
        pea     3(%sp)
        move.l  %d0, -(%sp)
        move.l  %a0, -(%sp)
        jsr     0x401CEAB8
        lea     16(%sp), %sp
        move.l  (%sp)+, %d0
        rts

| the box: stock's toggle box (0x400979be) with our value in place of its getter's (0x400bba6c): its first five
| instructions replayed, live_on() in d0, then on at 0x400979de where stock's getter returns
        .globl  live_box
live_box:
        lea     -12(%sp), %sp
        movem.l %d2-%d4, (%sp)
        move.l  24(%sp), %d2
        move.l  32(%sp), %d4
        move.l  28(%sp), %d3
        addi.l  #11, %d3
        jsr     live_on
        jmp     0x400979DE
