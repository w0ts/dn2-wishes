| The DSP load budget at note-on (csrc/load/load.c, docs/load-budget.md).

        .text

| The audio ISR's note-on call of the voice allocator, 0x400269e6 (was: jsr 0x4002a6a2): its nine arguments on the
| stack (track, note, event, ...), a6 the interrupt's frame. load_pre(args) may hide the free slots; the stock allocator
| runs on the same arguments (our return address set aside in load_ret: the interrupt does not nest); load_post(taken,
| fp) puts them back and releases further voices if needed. d0 and d1 leave as the allocator returned them (the slots
| given, and the track's older voices on the note); the caller keeps d2 and d3, which the C code saves.
|
| 2026-11-16 (PARA as one voice, csrc/para/one.c): first pv_pre(args, a2 the event, fp): 1 when the note joined its
| track's held chord: then no allocator at all, d0 = d1 = 0, the ISR's own "no slot" path (0x400269fa, as a muted
| track's note); 2 likewise when every candidate slot is latched by DRONE HOLD for another track (2026-11-19, hold.c
| hold_locked). Else pv_pre may hide the held chords' slots and the other tracks' DRONE HOLD latches and set a PARA
| track's UNISON to one for this call, and pv_post(taken, args, a2, fp) puts them back and starts the chord, after load_post. a2 (the event) is the ISR's,
| kept by every C call.
        .globl  load_alloc_hook
load_alloc_hook:
        move.l  %fp, -(%sp)
        move.l  %a2, -(%sp)
        pea     12(%sp)                         | the arguments, after [a2][fp][ret]
        jsr     pv_pre
        lea     12(%sp), %sp
        tst.l   %d0
        beq.s   1f
        moveq   #0, %d0                         | joined: no slot given, none of the track's released
        moveq   #0, %d1
        rts
1:      pea     4(%sp)
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
        move.l  %fp, -(%sp)                     | [fp][d0][d1][args]
        move.l  %a2, -(%sp)                     | [a2][fp][d0][d1][args]
        pea     16(%sp)                         | [&args][a2][fp][d0][d1][args]
        move.l  16(%sp), -(%sp)                 | [d1][&args][a2][fp][d0][d1][args]
        jsr     pv_post
        lea     16(%sp), %sp
        movem.l (%sp), %d0-%d1
        addq.l  #8, %sp
        move.l  load_ret, -(%sp)
        rts

| 2026-11-16 (PARA as one voice): the ISR's key-up call of the allocator, 0x40026d86 (was: jsr 0x4002a6a2), its nine
| arguments pushed (track, note, type, ...). pv_rel(args) ends a joined note of the track's chords (stock finds no
| slot for it and returns d0 = d1 = 0, 0x4002afbc), then the allocator as stock calls it, returning to the ISR.
        .globl  pv_rel_hook
pv_rel_hook:
        pea     4(%sp)
        jsr     pv_rel
        addq.l  #4, %sp
        jmp     0x4002A6A2

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
