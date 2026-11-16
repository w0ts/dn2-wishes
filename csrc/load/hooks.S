| The DSP load budget at note-on (csrc/load/load.c, docs/load-budget.md).

        .text

| The audio ISR's note-on call of the voice allocator, 0x400269e6 (was: jsr 0x4002a6a2): its nine arguments on the
| stack (track, note, event, ...), a6 the interrupt's frame. load_pre(args) may hide the free slots; the stock allocator
| runs on the same arguments (our return address set aside in load_ret: the interrupt does not nest); load_post(taken,
| fp) puts them back and releases further voices if needed. d0 and d1 leave as the allocator returned them (the slots
| given, and the track's older voices on the note); the caller keeps d2 and d3, which the C code saves.
        .globl  load_alloc_hook
load_alloc_hook:
        pea     4(%sp)
        jsr     load_pre
        addq.l  #4, %sp
        move.l  (%sp)+, load_ret
        jsr     0x4002A6A2
        lea     -8(%sp), %sp
        movem.l %d0-%d1, (%sp)
        move.l  %fp, -(%sp)
        move.l  %d1, -(%sp)
        jsr     load_post
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1
        addq.l  #8, %sp
        move.l  load_ret, -(%sp)
        rts

| VOICE BUDGET's row (load.c load_row), as LIVE SELECT's (csrc/msel/live.S): the label invoker, a0 the std::string
        .globl  load_label
load_label:
        move.l  %a0, -(%sp)
        jsr     load_text
        move.l  (%sp), %a0
        subq.l  #4, %sp
        pea     3(%sp)
        move.l  %d0, -(%sp)
        move.l  %a0, -(%sp)
        jsr     0x401CEAB8
        lea     16(%sp), %sp
        move.l  (%sp)+, %d0
        rts

| the box: stock's toggle box (0x400979be), load_on() in d0 where its getter returns (as live_box)
        .globl  load_box
load_box:
        lea     -12(%sp), %sp
        movem.l %d2-%d4, (%sp)
        move.l  24(%sp), %d2
        move.l  32(%sp), %d4
        move.l  28(%sp), %d3
        addi.l  #11, %d3
        jsr     load_on
        jmp     0x400979DE
