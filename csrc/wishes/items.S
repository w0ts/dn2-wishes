| The wishes record's hooks at the kit's and the pattern's loader and saver (csrc/wishes/item.c;
| docs/wishes-record.md, "Every item type"), OS 1.12. As hooks.S's at the sound's: each site is a jmp
| here, past stock's own work, where both the live object and the stored one are in registers; the
| scratch registers are kept, the displaced instructions replayed, and stock goes on.
|
|   kit load   0x400ddf52  pea 10264(%a2) ; lea 23840(%a3),%a3          a3 live, a2 stored (8 B: jmp ; nop)
|   kit save   0x400de0ce  moveq #4,%d0 ; move.l %d0,4(%a2)              a3 live, a2 stored (6 B)
|   pat load   0x400de85e  move.l #122474,%d0                            a2 live, d2 stored + 68148 (6 B)
|   pat save   0x400de9b2  movea.l %d2,%a0 ; moveq #4,%d1 ; move.l %d1,(%a0)
|                                                                        d3 live + 97872, d2 stored (6 B)
|   song load  0x400dec52  move.l 3679(%a2),%d1 ; clr.l %d0             a2 live, a3 stored (6 B)
|   song save  0x400dedb8  clr.l (%a2) ; lea 12(%sp),%sp                a2 stored, live at 40(%sp) (6 B)
|   settings load 0x400df58c  move.w 236(%a3),%d1 ; mvs.w %d1,%d0       a2 live, a3 stored (6 B)
|   settings save 0x400df89e  moveq #2,%d0 ; move.l %d0,(%a2) ; moveq #1,%d0   a2 stored, a3 live (6 B)
| The song's and the settings' save sites lie after the stock memset / zero loop over the tail the link
| goes in; 0x400df58c is a branch target (0x400df584) and its jmp replaces the whole instruction there.
| The kit's sites lie after its 16 sounds were loaded or saved (hooks.S's site ran 16 times by then),
| the pattern's after its lock pool. 0x400de85e is a branch target (the lock loader's success test,
| 0x400de852): the jmp replaces that whole instruction, so the branch lands on the jmp.

#define KIT_LOAD 0x400DDF52
#define KIT_SAVE 0x400DE0CE
#define PAT_LOAD 0x400DE85E
#define PAT_SAVE 0x400DE9B2
#define SONG_LOAD 0x400DEC52
#define SONG_SAVE 0x400DEDB8
#define PS_LOAD 0x400DF58C
#define PS_SAVE 0x400DF89E

        .text
        .globl  wish_kit_load_stub
wish_kit_load_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a2, -(%sp)             | stored
        move.l  %a3, -(%sp)             | live
        jsr     wish_kit_load
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        pea     10264(%a2)
        lea     23840(%a3), %a3
        jmp     KIT_LOAD + 8

        .globl  wish_kit_save_stub
wish_kit_save_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | live
        move.l  %a2, -(%sp)             | stored
        jsr     wish_kit_save
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        moveq   #4, %d0
        move.l  %d0, 4(%a2)
        jmp     KIT_SAVE + 6

        .globl  wish_pat_load_stub
wish_pat_load_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %d2, %d0
        sub.l   #68148, %d0
        move.l  %d0, -(%sp)             | stored
        move.l  %a2, -(%sp)             | live
        jsr     wish_pattern_load
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        move.l  #122474, %d0
        jmp     PAT_LOAD + 6

        .globl  wish_pat_save_stub
wish_pat_save_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %d3, %d0
        sub.l   #97872, %d0
        move.l  %d0, -(%sp)             | live
        move.l  %d2, -(%sp)             | stored
        jsr     wish_pattern_save
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        movea.l %d2, %a0
        moveq   #4, %d1
        move.l  %d1, (%a0)
        jmp     PAT_SAVE + 6

        .globl  wish_song_load_stub
wish_song_load_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | stored
        move.l  %a2, -(%sp)             | live
        jsr     wish_song_load
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        move.l  3679(%a2), %d1
        clr.l   %d0
        jmp     SONG_LOAD + 6

        .globl  wish_song_save_stub
wish_song_save_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  56(%sp), -(%sp)         | live: the saver's second argument (40(%sp) at the site)
        move.l  %a2, -(%sp)             | stored
        jsr     wish_song_save
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        clr.l   (%a2)
        lea     12(%sp), %sp
        jmp     SONG_SAVE + 6

        .globl  wish_ps_load_stub
wish_ps_load_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | stored
        move.l  %a2, -(%sp)             | live
        jsr     wish_settings_load
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        move.w  236(%a3), %d1
        mvs.w   %d1, %d0
        jmp     PS_LOAD + 6

        .globl  wish_ps_save_stub
wish_ps_save_stub:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a3, -(%sp)             | live
        move.l  %a2, -(%sp)             | stored
        jsr     wish_settings_save
        addq.l  #8, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        moveq   #2, %d0
        move.l  %d0, (%a2)
        moveq   #1, %d0
        jmp     PS_SAVE + 6
