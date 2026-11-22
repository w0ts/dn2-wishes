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
| mod_eval_pre, then the evaluator with the caller's seven arguments pushed again, then the
| matrix's routes (csrc/matrix mx_eval(B), B the first argument, still on the stack: the
| evaluator writes only its own locals), then (v0.65.1) smp_lfo_fix. The caller treats
| d0-d1/a0-a1 as the evaluator's scratch.
        .globl  mod_eval
mod_eval:
        jsr     mod_eval_pre
        lea     -28(%sp), %sp
        move.l  32(%sp), (%sp)
        move.l  36(%sp), 4(%sp)
        move.l  40(%sp), 8(%sp)
        move.l  44(%sp), 12(%sp)
        move.l  48(%sp), 16(%sp)
        move.l  52(%sp), 20(%sp)
        move.l  56(%sp), 24(%sp)
#if DN2_LFO_HALFRATE
        pea     (%sp)                   | (DN2_LFO_HALFRATE) this frame's voices; a trig or restore of a voice not of
        jsr     lh_args                 | this frame waits for its turn (cascade.c): the evaluator's copies of the
        addq.l  #4, %sp                 | arguments, never the frame's
#endif
        jsr     0x40137a06
#if DN2_ROUTE_PROBE
        jsr     mx_probe                | (DN2_ROUTE_PROBE, a test build's) the route tables' line fills, alone in
                                        | the profile (csrc/matrix/matrix.c); d0-d1/a0-a1 its scratch
#endif
        jsr     mx_eval
        jsr     smp_lfo_fix             | v0.65 banks (csrc/sampler/link.c): each sample voice's SAMP keeps its bank after
        lea     28(%sp), %sp            | the LFOs and the routes (upstream hooks this site with smp_lfo_hook; ours is here)
        rts

| 0x40137d7a, the evaluator's write of one LFO into its DEST cell (was: movea.l 52(%sp),%a0 ;
| mvs.w 82(%a4),%d1, 8 bytes; now jsr here + nop). d7 is DEST (0..100, bound-checked), a5 the
| voice row, 52(%sp) here the LFO counter (2 LFO3 .. 0 LFO1), 56(%sp) the row's slot 0.
| a0 comes back as the base the stock read-add-clamp-store uses; d0, the LFO's scaled value
| still to be multiplied, and every other register as it came. A DEST that is not a higher
| LFO's control takes the short way (at most 14 instructions): only a lower LFO's write into a
| higher one's control calls mod_wb_cell, at most twice a voice row (LFO1, LFO2) a frame.
        .globl  mod_wb
mod_wb:
        cmpi.l  #127, %d7               | (2026-11-17, the User: the worst case) the DEST's kind from a table, one read
        bhi.s   0f                      | instead of up to five compares: every path as short or shorter; past
        lea     mod_wb_kind, %a0        | the table, stock's write (as past 108 before)
        move.b  (%a0,%d7.l), %d1
        movea.l 56(%sp), %a0
        beq.s   1f                      | 0: stock's write (0..8, 25..100, past 108)
        bpl.s   3f                      | 1: 101..108, LFO4's controls (DN2_LFO4): mod_wb_cell
        move.l  %d7, %d1                | -1: 9..24, an LFO's control
        subq.l  #1, %d1
        lsr.l   #3, %d1                 | the LFO whose control DEST is (1 LFO2, 2 LFO3)
        cmp.l   52(%sp), %d1
        ble.s   1f                      | not above this one: stock's write, heard this frame
3:      move.l  %d0, -(%sp)
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
0:      movea.l 56(%sp), %a0            | past the table: stock's write
        mvs.w   82(%a4), %d1
        rts

| sm_fast (2026-11-17, the User: the constant cost, the same work faster): stock's parameter smoother 0x400db28e,
| entered there by a jmp. Its own instruction words, in its order: the prologue, then its loop body (two cells,
| the EMAC's fractional one-pole over 1,734 cells: 867 bodies, of which 840 run: item 6 below) once, 102 times eight,
| seven and 2 times eight, the count and branch once an eight (stock: once a body, 867 times); then of its block copy
| of 2,448 bytes (0x80007670 <- the source + 3,468) the 352 that are read (item 5 below), with %d1 left as stock's
| memcpy leaves it, and its
| own tail (the 16 rows' three LFO DEST words, unrolled, the return value 0x800068e4).
        .globl  sm_fast
sm_fast:
        .word   0x4fef, 0xffe4          | lea    -28(%sp),%sp
        .word   0x48d7, 0x0c7c          | movem.l %d2-%d6/%a2-%a3,(%sp)
        .word   0x266f, 0x0020          | movea.l 32(%sp),%a3
        .word   0x2a3c, 0x7c29, 0x0000  | move.l #0x7c290000,%d5
        .word   0x204b                  | movea.l %a3,%a0
        .word   0x2c3c, 0x03d7, 0x0000  | move.l #0x03d70000,%d6
        .word   0x43f9, 0x8000, 0xde60  | lea    0x8000de60,%a1
        .word   0x45f9, 0x8000, 0x68e4  | lea    0x800068e4,%a2
        .word   0x243c, 0x0000, 0x8000  | move.l #0x8000,%d2
        .word   0x2222                  | move.l -(%a2),%d1
        .word   0x2018                  | move.l (%a0)+,%d0
        .macro  SMB                     | one body: two cells (stock's loop body, word for word)
        .word   0xa891, 0x00c6          | mac.w  %d6u,%d0u,(%a1),%d4,%acc0
        .word   0xa805, 0x0800          | mac.l  %d5,%d4,%acc0
        .word   0x24c1                  | move.l %d1,(%a2)+
        .word   0xa029, 0x0046, 0x0004  | mac.w  %d6u,%d0l,4(%a1),%d0,%acc1
        .word   0xa018, 0x0805          | mac.l  %d5,%d0,(%a0)+,%d0,%acc1
        .word   0xa1c1                  | movclr.l %acc0,%d1
        .word   0x22c1                  | move.l %d1,(%a1)+
        .word   0xa3c4                  | movclr.l %acc1,%d4
        .word   0x22c4                  | move.l %d4,(%a1)+
        .word   0xd882                  | add.l  %d2,%d4
        .word   0x4844                  | swap   %d4
        .word   0xd282                  | add.l  %d2,%d1
        .word   0x3204                  | move.w %d4,%d1
        .endm
| (2026-11-18, the User's CPU, dup study item 6) only the bodies whose cells someone reads: the head and the 16
| rows and the global row's cell 0 (cells 0..1633, bodies 0..816), the global row's cells 25..70 (bodies 829..851). Left out, every frame: the
| global row's cells 1..24 (bodies 817..828) and 71..100 (bodies 852..866), which no code reads, OUT word or
| state (traced idle and busy on main 270de295: their only reader is this smoother; stock's 0x400db156 only
| writes them). Their OUT words and states keep what they hold; every other word the same as stock's, every frame.
        SMB
        move.l  #102, %d3               | bodies 1..816: 102 passes of eight
1:
        .rept   8
        SMB
        .endr
        subq.l  #1, %d3
        bne.w   1b
        move.l  %d1, (%a2)+             | body 816's pair out
        lea     44(%a2), %a2            | to pair 828's OUT word, as the prologue's -(%a2): read and written
        move.l  (%a2), %d1              | back the same by body 829
        lea     96(%a1), %a1            | the states of pairs 817..828 passed
        lea     44(%a0), %a0            | the sources of pairs 818..828 passed (817's is in %d0)
        move.l  (%a0)+, %d0             | pair 829's source
        .rept   7                       | bodies 829..835
        SMB
        .endr
        moveq   #2, %d3                 | bodies 836..851: two passes of eight
2:
        .rept   8
        SMB
        .endr
        subq.l  #1, %d3
        bne.w   2b
        .word   0x24c1                  | move.l %d1,(%a2)+
| (2026-11-18, the User's CPU, dup study item 5) of stock's block copy of the 16 MOD SETUP records (153 bytes each,
| 0x80007670 <- the source + 3,468), only the bytes someone reads in the copy: 6..7 (the interrupt, 0x400272e2 and
| 0x40027316), 104..107 (the LFO evaluator, lfo_fast as stock's 0x40137aac / 0x40137b0c), 112..128 (the pitch path
| 0x40138944: 112, 113, 117, 121, 125). mods_fast, the copy's only other reader, reads the source's records (the
| same bytes: nothing writes them between this copy and it). 352 bytes of 2,448, every frame (constant cost); the
| rest of the copy keeps what it holds (traced idle and busy on main 270de295: no other reader, interrupt or task).
| The same bytes land as stock's front-to-back copy (the two blocks apart). Odd records' words and longs are
| misaligned, as stock's own reads of them are. (2026-11-19) the same with DN2_LFO4 off: lfo4's code only adds readers.
        lea     3468(%a3), %a0
        lea     0x80007670, %a1
        .irp    r,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        move.w  153*\r+6(%a0), 153*\r+6(%a1)
        move.l  153*\r+104(%a0), 153*\r+104(%a1)
        move.b  153*\r+112(%a0), 153*\r+112(%a1)
        move.l  153*\r+113(%a0), 153*\r+113(%a1)
        move.l  153*\r+117(%a0), 153*\r+117(%a1)
        move.l  153*\r+121(%a0), 153*\r+121(%a1)
        move.l  153*\r+125(%a0), 153*\r+125(%a1)
        .endr
        moveq   #16, %d1                | as stock's memcpy leaves it
| stock's copy of the 16 rows' three LFO DEST words (its loop: 2: move.w 42(%a1),(%a0) ; lea 202(%a1),%a1 ;
| move.w -144(%a1),16(%a0) ; move.w -128(%a1),32(%a0) ; lea 202(%a0),%a0 ; cmpa.l #0x800075ae,%a0 ; bne.s 2b), unrolled
| (2026-11-18): the same words, %a0 and %a1 left as stock's loop leaves them. (A muted first route's mask is applied
| after MOD SETUP, mods_fast.)
        lea     0x8000690e, %a0
        .irp    v,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        move.w  42+202*\v(%a3), 202*\v(%a0)
        move.w  58+202*\v(%a3), 16+202*\v(%a0)
        move.w  74+202*\v(%a3), 32+202*\v(%a0)
        .endr
        lea     0x800075ae, %a0
        lea     16*202(%a3), %a1
        .word   0x4cd7, 0x0c7c          | movem.l (%sp),%d2-%d6/%a2-%a3
        .word   0x203c, 0x8000, 0x68e4  | move.l #0x800068e4,%d0
        .word   0x4fef, 0x001c          | lea    28(%sp),%sp
        .word   0x4e75                  | rts

| mods_fast (2026-11-17, the User: the constant cost, the same work faster): stock's MOD SETUP pass 0x400db390, entered
| there by a jmp. Every voice row: its five sources (0x8000dd40, then 0x8000de40/de20/de00/dde0 indexed by the voice's
| word at 0x80005308) each through stock's kernel 0x400db340 over four destinations, then its key-track block, as
| stock: the kernel's instructions in its order (the index sign-extended by movea.w as mvs.w does), no push, save, call
| or return.
| (2026-11-19, the User's CPU: the same work, fewer instructions) the 24 kernels of a voice row unrolled (MK): no count
| or branch a kernel; the six lists (3476..3571 past the record: four longs each, one after the other) walked by one
| pointer, so each list's first long is the one the kernel before it loaded in its msac (stock reads it a second time:
| the same long, as no kernel writes there: its writes go into the voice row, at a MOD SETUP slot 0..100); the row's
| address and the tables' base (0x8000de00, the four at +0x40/+0x20/0/-0x20; the key track at 0x8000dda0 + 4 v as
| 0x60(%fp) indexed) kept in registers; 0x40000000 in %d0 (sub.l / add.l in place of subi / addi: the same values and
| flags). The key track's four bodies (MKK) as stock's key-track block: its product doubled four times, saturated.
| The same reads of every source and cell, the same writes in the same order. Prologue, mask block, epilogue as
| before; %d0 left 32 as stock's loop leaves it.
        .macro  MK                      | stock's kernel body (0x400db340), once
        movea.w %d6, %a3                | mvs.w %d2,%d3 (sign-extended the same)
        msac.w  %d1l, %d6u, (%a1)+, %d6, %acc0
        mvz.w   (%a0,%a3.l*2), %d7
        swap    %d7
        sub.l   %d0, %d7                | subi.l #0x40000000,%d7
        movclr.l %acc0, %d5
        sub.l   %d5, %d7
        sats.l  %d7
        add.l   %d7, %d7
        sats.l  %d7
        asr.l   #1, %d7
        add.l   %d0, %d7                | addi.l #0x40000000,%d7
        swap    %d7
        move.w  %d7, (%a0,%a3.l*2)
        .endm
        .macro  MK4
        MK
        MK
        MK
        MK
        .endm
        .macro  MKK                     | stock's key-track body: its product doubled four times, saturated each
        movea.w %d6, %a3                | time (add.l ; sats.l), before the subtraction
        msac.w  %d1l, %d6u, (%a1)+, %d6, %acc0
        mvz.w   (%a0,%a3.l*2), %d7
        swap    %d7
        sub.l   %d0, %d7
        movclr.l %acc0, %d5
        add.l   %d5, %d5
        sats.l  %d5
        add.l   %d5, %d5
        sats.l  %d5
        add.l   %d5, %d5
        sats.l  %d5
        add.l   %d5, %d5
        sats.l  %d5
        sub.l   %d5, %d7
        sats.l  %d7
        add.l   %d7, %d7
        sats.l  %d7
        asr.l   #1, %d7
        add.l   %d0, %d7
        swap    %d7
        move.w  %d7, (%a0,%a3.l*2)
        .endm
        .globl  mods_fast
mods_fast:
        .word   0x4fef, 0xffc4          | lea    -60(%sp),%sp
        .word   0x48d7, 0x7cfc          | movem.l %d2-%d7/%a2-%fp,(%sp)
        move.l  64(%sp), %d2            | the rows (stock: movea.l 64(%sp),%a2 ; move.l %a2,%d2)
        .word   0x4283                  | clr.l  %d3
| (2026-11-18, dup study item 5) the MOD SETUP lists read in their source, 0x80003af0 + 3,468 (sm_fast's argument, at
| 0x4002717e), not in sm_fast's copy at the rows + 3,468 (this pass's argument is sm_fast's return, 0x800068e4): the
| same bytes, as sm_fast copies them in the same interrupt just before; sm_fast copies only what stock reads.
        lea     0x80003AF0, %a2
        .word   0x0682, 0x0000, 0x0022  | addi.l #34,%d2
        .word   0x4bf9, 0x8000, 0x5308  | lea    0x80005308,%a5
        lea     0x8000DE00, %a4         | the four indexed sources' tables: +0x40, +0x20, 0, -0x20
        .word   0x4df9, 0x8000, 0xdd40  | lea    0x8000dd40,%fp
        move.l  #0x40000000, %d0
1:      movea.l %d2, %a0                | the row's slot 0
        mvs.w   (%fp,%d3.l), %d1        | the first source: the row's own
        move.l  (%a5)+, %d4             | the voice's index into the other four
        lea     3476(%a2), %a1          | the six lists, one after the other
        move.l  (%a1)+, %d6
        MK4
        mvs.w   0x40(%a4,%d4.l*2), %d1  | 0x8000de40
        MK4
        mvs.w   0x20(%a4,%d4.l*2), %d1  | 0x8000de20
        MK4
        mvs.w   (%a4,%d4.l*2), %d1      | 0x8000de00
        MK4
        mvs.w   -0x20(%a4,%d4.l*2), %d1 | 0x8000dde0
        MK4
        move.l  0x60(%fp,%d3.l*2), %d1  | stock's key-track block: move.l (0x8000dda0 + 4 v),%d1
        asr.l   #8, %d1
        addi.l  #-15360, %d1
        MKK
        MKK
        MKK
        MKK
| (2026-11-18, the User: our matrix the only live source of LFO routes, stock's DEST and DEP the first route's copy) the
| voice row's three LFO DEST cells, after every MOD SETUP source and the key track: a voice playing its track's sound
| (stock's track word 0x80005308[v], kept to 0..15; the sound 0x800052a8[v] the one mx_poll laid that track out for)
| has each ANDed with its track's mask (csrc/matrix mx_dmask): all ones, the cell as it is; 0, LFO l's first route
| muted, DEST none for this frame whatever MOD SETUP added (its write lands in slot 0, as stock's DEST none). The same
| instructions muted or not; a sound-locked voice is left as stock's.
        move.l  -4(%a5), %d1            | the voice's track (%a5 is past its word)
        andi.l  #15, %d1
        lea     0x800052A8, %a0
        move.l  (%a0,%d3.l*2), %d4      | the sound it plays (%d3: 2 v)
        lea     mx_dmask+128, %a1       | LFO3's masks (LFO1's at -128, LFO2's at -64, the tracks' sounds at +64)
        cmp.l   64(%a1,%d1.l*4), %d4
        bne.s   8f
        movea.l %d2, %a0                | the row's slot 0
        mvz.w   8(%a0), %d5             | LFO1 DEST (slot 4)
        and.l   -128(%a1,%d1.l*4), %d5
        move.w  %d5, 8(%a0)
        mvz.w   24(%a0), %d5            | LFO2 DEST (slot 12)
        and.l   -64(%a1,%d1.l*4), %d5
        move.w  %d5, 24(%a0)
        mvz.w   40(%a0), %d5            | LFO3 DEST (slot 20)
        and.l   0(%a1,%d1.l*4), %d5
        move.w  %d5, 40(%a0)
8:      .word   0x5483                  | addq.l #2,%d3
        .word   0x0682, 0x0000, 0x00ca  | addi.l #202,%d2
        .word   0x45ea, 0x0099          | lea    153(%a2),%a2
        cmpi.l  #32, %d3
        bne.w   1b
        .word   0x7020                  | moveq  #32,%d0 (as stock's loop leaves it)
        .word   0x4cd7, 0x7cfc          | movem.l (%sp),%d2-%d7/%a2-%fp
        .word   0x4fef, 0x003c          | lea    60(%sp),%sp
        .word   0x4e75                  | rts

| lfo_fast (2026-11-17, the User: the constant cost, the same work faster): stock's LFO evaluator A 0x40137a06 as the
| shipped build runs it (with DN2_LFO4 lfo4's four LFOs a voice, else stock's three; lfowaves' shapes, mod_wb), entered
| there by a jmp. Its instructions
| in its order, word for word where stock's, with what it called or jumped through inline (dnfw.waverider.lfofast checks
| every one of them against what is here, and reads the LF_ addresses out of lfo4's and lfowaves' edits):
|  - the restore/backup addresses (the LFO's 40 bytes: %a0, %d1) are worked out only on the path that copies them
|    (stock: at every LFO's top; nothing else reads them before they are written again);
|  - the rate routine 0x4013748c with its exp2 0x401346c0, and 0x40137508 (twice): their instructions here, no push,
|    call or return; the rate's MACSR check every LFO as stock (a wrong mode: stock's routine called, as stock);
|  - lfowaves' no_phase and a_call (with its key), lfo4's a4_bottom and outer, mod_wb: inline. lfo4's a4_top (the C
|    row refresh) is still called, the stack where it was. mod_wb's DEST past 127 test goes: DEST is 0..108 there.
| The same LFOs every frame (64; 48 without lfo4), the same calls of the wave functions, the copies and lfo4's refresh.
| (2026-11-19, the User's CPU: the same work, fewer instructions) the MAC's mode read once a call (no code the evaluator
| reaches writes MACSR: our chunks, lfowaves and lfo4 hold no move to MACSR; a wrong mode still goes to stock's rate
| routine, which then sees the same registers); WAVE's clamp and lfowaves' no_phase test from one table (lf_wave, by
| WAVE's signed byte); the instance key's address part in three instructions; the DEST read once into %d7; ACT
| (117(%a2)) cleared in place; the held output read only on its way. Without DN2_LFO4 (2026-11-19, the User: LFO4
| behind its flag): stock's own evaluator (three LFOs, 120-byte states at 0x44640c18, its copy addresses, top, bottom
| and outer) with the same cuts.
#if DN2_LFO4
#define LF_STEP_SH 5                    /* an LFO state 160 B a voice: 128 + 32 */
#define LF_STEP_OP add.l
#else
#define LF_STEP_SH 3                    /* stock's 120 B a voice: 128 - 8 */
#define LF_STEP_OP sub.l
#define LF_LIVE 0x44640c18              /* stock's LFO state and its backup (dnfw.waverider.lfofast checks stock's) */
#define LF_BACKUP 0x4463fd18
#endif
        .globl  lfo_fast
lfo_fast:
        .word   0x4fef, 0xffb4          | lea    -76(%sp),%sp
        .word   0x122f, 0x006b          | move.b 107(%sp),%d1
        .word   0x48d7, 0x7cfc          | movem.l %d2-%d7/%a2-%fp,(%sp)
        .word   0x242f, 0x0050          | move.l 80(%sp),%d2
        .word   0x1f41, 0x004b          | move.b %d1,75(%sp)
        beq     .Lf_noback
#if DN2_LFO4
        pea     0xa00                   | lfo4: 2,560 bytes, live -> backup
#else
        pea     0x780                   | stock: 1,920 bytes, live -> backup
#endif
        pea     LF_LIVE
        pea     LF_BACKUP
        jsr     wish_memcpy_stub
        lea     12(%sp), %sp
.Lf_noback:
        .word   0x2042                  | movea.l %d2,%a0
        .word   0x9bcd                  | suba.l %a5,%a5
        .word   0x41e8, 0x0022          | lea    34(%a0),%a0
#if DN2_LFO4
        lea     LF_LIVE+40, %a1         | lfo4: +40, so %a2@(80) reaches LFO index 3
#else
        lea     LF_LIVE, %a1
#endif
        .word   0x2f48, 0x0034          | move.l %a0,52(%sp)
        .word   0x2f42, 0x003c          | move.l %d2,60(%sp)
        .word   0x2f49, 0x0038          | move.l %a1,56(%sp)
        mvz.b   75(%sp), %d0            | stock asks at every LFO's top: 75(%sp) set, or 92(%sp) (the voices to
        or.l    92(%sp), %d0            | restore or back up) not 0? Both are the call's own, never written:
        sne     %d0                     | asked once here, the answer in the frame's free byte 74(%sp)
        move.b  %d0, 74(%sp)
        move.l  %macsr, %d0             | the rate routine's MACSR test (stock: every LFO), once: 0 in the frame's
        andi.l  #0xf0, %d0              | free byte 73(%sp) when the mode is stock's 0x20
        subi.l  #32, %d0
        move.b  %d0, 73(%sp)
.Lf_voice:
#if DN2_LFO_HALFRATE
        lea     lh_selw, %a0            | (DN2_LFO_HALFRATE) this voice's LFOs stepped this frame? (cascade.c lh_args:
        move.w  (%a0,%a5.l*2), %d0      | 1 its turn, 0 not, 2 its first turn) -> the frame's free byte 72: 0 its turn,
        subq.l  #1, %d0                 | 0xff not (each LFO writes only its DEST, from its last output), 1 its first
        move.b  %d0, 72(%sp)            | turn (no frame skipped before it)
#endif
        .word   0x220d                  | move.l %a5,%d1
        .word   0x7401                  | moveq  #1,%d2
        .word   0x2e2f, 0x005c          | move.l 92(%sp),%d7
        .word   0xe2a7                  | asr.l  %d1,%d7
        .word   0x2a2f, 0x0058          | move.l 88(%sp),%d5
        .word   0xe2a5                  | asr.l  %d1,%d5
        .word   0x286f, 0x0034          | movea.l 52(%sp),%a4
#if DN2_LFO4
        .word   0x7203                  | moveq  #3,%d1 (lfo4: four LFOs)
#else
        .word   0x7202                  | moveq  #2,%d1
#endif
        .word   0x266f, 0x0038          | movea.l 56(%sp),%a3
        .word   0x2f47, 0x0040          | move.l %d7,64(%sp)
        .word   0xca82                  | and.l  %d2,%d5
        .word   0xc5af, 0x0040          | and.l  %d2,64(%sp)
        .word   0x246f, 0x0038          | movea.l 56(%sp),%a2
#if DN2_LFO4
        jsr     LF_A4TOP                | lfo4's a4_top: LFO4's row (the C refresh), %a3 += 116
#else
        .word   0x49ec, 0xffde          | lea    -34(%a4),%a4
        .word   0x47eb, 0x0074          | lea    116(%a3),%a3
#endif
        .word   0x2f41, 0x0030          | move.l %d1,48(%sp)
.Lf_lfo:
#if DN2_LFO_HALFRATE
        tst.b   72(%sp)
        bmi     .Lh_lfo
#endif
        tst.b   74(%sp)                 | stock: tst.b 75(%sp) ; bne ; tst.l 92(%sp) ; beq (the same answer)
        beq     .Lf_keep
        .word   0x226f, 0x003c          | movea.l 60(%sp),%a1
        .word   0x4aa9, 0x0df4          | tst.l  3572(%a1)
        beq     .Lf_keep
        move.l  48(%sp), %d0            | stock's LFO top: %a0 = the LFO's 40 bytes, %d1 = %a2 + 80
        move.l  %d0, %d1
        .word   0xeb88                  | lsl.l  #5,%d0
        .word   0xe789                  | lsl.l  #3,%d1
        .word   0x2041                  | movea.l %d1,%a0
        .word   0x220a                  | move.l %a2,%d1
        .word   0xd1c0                  | adda.l %d0,%a0
        .word   0x0681, 0x0000, 0x0050  | addi.l #80,%d1
        .word   0x226f, 0x0060          | movea.l 96(%sp),%a1
        .word   0x7131, 0xd800          | mvs.b  (%a1,%a5.l),%d0
        bge     .Lf_back
        .word   0x226f, 0x0064          | movea.l 100(%sp),%a1
        .word   0x7131, 0xd800          | mvs.b  (%a1,%a5.l),%d0
        blt     .Lf_copied
        .word   0x2400                  | move.l %d0,%d2
        lsl.l   #LF_STEP_SH, %d2        | lfo4: lsl #5 (stock #3)
        .word   0xef88                  | lsl.l  #7,%d0
        .word   0x4878, 0x0028          | pea    0x28
        LF_STEP_OP %d2, %d0             | lfo4: add (160 a voice; stock sub, 120)
        addi.l  #LF_LIVE, %d0
        .word   0x4870, 0x0800          | pea    (%a0,%d0.l)
        bra     .Lf_copy
.Lf_back:
        .word   0x2400                  | move.l %d0,%d2
        lsl.l   #LF_STEP_SH, %d2
        .word   0xef88                  | lsl.l  #7,%d0
        .word   0x4878, 0x0028          | pea    0x28
        LF_STEP_OP %d2, %d0
        .word   0xd088                  | add.l  %a0,%d0
        addi.l  #LF_BACKUP, %d0
        .word   0x2f00                  | move.l %d0,-(%sp)
.Lf_copy:
        .word   0x2f01                  | move.l %d1,-(%sp)
        jsr     wish_memcpy_stub
        .word   0x4fef, 0x000c          | lea    12(%sp),%sp
.Lf_copied:
        .word   0x4aaf, 0x0040          | tst.l  64(%sp)
        beq     .Lf_keep
        .word   0x206f, 0x003c          | movea.l 60(%sp),%a0
        .word   0x7002                  | moveq  #2,%d0
        .word   0xb0a8, 0x0df4          | cmp.l  3572(%a0),%d0
        bne     .Lf_clr
.Lf_keep:
        .word   0x2f45, 0x002c          | move.l %d5,44(%sp)
.Lf_par:
        .word   0x7d6c, 0x0044          | mvs.w  68(%a4),%d6
        .word   0x712c, 0x0046          | mvs.b  70(%a4),%d0 (MULT; stock then clamps: below 0 -> 0, above 23 -> 23;
        .word   0x0686, 0xffff, 0xc000  | addi.l #-16384,%d6  12..23 -> -12 with 14400, else 84(%sp))
        .word   0xdc86                  | add.l  %d6,%d6
        lea     lf_mult, %a0            | (2026-11-18, the User's CPU) the clamp's result by MULT's byte, 0x80 set
        mvz.b   (%a0,%d0.l), %d0        | for 14400 (by the signed byte: lf_mult is the table's middle): the same
                                        | %d0 and %d1, 4 instructions fewer (%a0 and stock's
        bclr    #7, %d0                 | %d2 = 11 are dead here: both written before they are read again)
        beq.s   3f
        .word   0x223c, 0x0000, 0x3840  | move.l #14400,%d1
        bra.s   5f
3:      .word   0x222f, 0x0054          | move.l 84(%sp),%d1
5:      .word   0x772c, 0x004c          | mvs.b  76(%a4),%d3 (WAVE; stock then clamps: below 0 -> 0, above 13 -> 13)
        lea     lf_wave, %a0            | (2026-11-19) the clamp's result by WAVE's signed byte, 0x80 set where
        mvz.b   (%a0,%d3.l), %d3        | lfowaves' no_phase finds a stock shape (WAVE < 7: SPH its start phase)
        .word   0x4c01, 0x6800          | muls.l %d1,%d6
        .word   0x7e0b                  | moveq  #11,%d7
        .word   0x756c, 0x004e          | mvs.w  78(%a4),%d2 (SPH)
        bclr    #7, %d3
        bne.s   2f                      | a stock shape: SPH
        .word   0x4282                  | clr.l  %d2 (STP or PLS ...: none)
2:      .word   0x9e80                  | sub.l  %d0,%d7
        .word   0x716c, 0x0048          | mvs.w  72(%a4),%d0
        .word   0x2f42, 0x0044          | move.l %d2,68(%sp)
        .word   0xeea6                  | asr.l  %d7,%d6
        | the rate routine 0x4013748c (its argument %d0 = mvs.w 72(%a4)), inline
        tst.b   73(%sp)                 | its MACSR test, read at the call's start
        bne     .Lf_rate_stock
        .word   0x7540                  | mvs.w  %d0,%d2
        .word   0x203c, 0x4000, 0x0000  | move.l #0x40000000,%d0
        .word   0x2202                  | move.l %d2,%d1
        .word   0x0681, 0xffff, 0xc000  | addi.l #-16384,%d1
        beq     .Lf_rated
        .word   0x700e                  | moveq  #14,%d0
        .word   0x4a81                  | tst.l  %d1
        ble.s   1f
        .word   0xe1aa                  | lsl.l  %d0,%d2
        .word   0x0682, 0xdf00, 0x0000  | addi.l #-553648128,%d2
        .word   0x2002                  | exp2 0x401346c0 of %d2: move.l %d2,%d0
        .word   0x2200                  | move.l %d0,%d1
        .word   0xef88                  | lsl.l  #7,%d0
        .word   0x08c0, 0x001f          | bset   #31,%d0
        .word   0xe288                  | lsr.l  #1,%d0
        .word   0xa000, 0x0800          | mac.l  %d0,%d0,%acc0
        .word   0x7018                  | moveq  #24,%d0
        .word   0xe0a1                  | asr.l  %d0,%d1
        .word   0x207c, 0x5555, 0x5556  | movea.l #0x55555556,%a0
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0xa040, 0x0800          | mac.l  %d0,%a0,%acc0
        .word   0x4481                  | neg.l  %d1
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0xd080                  | add.l  %d0,%d0
        .word   0xd088                  | add.l  %a0,%d0
        .word   0xe2a8                  | lsr.l  %d1,%d0
        .word   0x4480                  | neg.l  %d0
        bra.s   2f
1:      .word   0xe1a9                  | lsl.l  %d0,%d1
        .word   0x0681, 0xff00, 0x0000  | addi.l #-16777216,%d1
        .word   0x2001                  | exp2 0x401346c0 of %d1: move.l %d1,%d0
        .word   0xef88                  | lsl.l  #7,%d0
        .word   0x08c0, 0x001f          | bset   #31,%d0
        .word   0xe288                  | lsr.l  #1,%d0
        .word   0xa000, 0x0800          | mac.l  %d0,%d0,%acc0
        .word   0x7018                  | moveq  #24,%d0
        .word   0xe0a1                  | asr.l  %d0,%d1
        .word   0x207c, 0x5555, 0x5556  | movea.l #0x55555556,%a0
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0xa040, 0x0800          | mac.l  %d0,%a0,%acc0
        .word   0x4481                  | neg.l  %d1
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0xd080                  | add.l  %d0,%d0
        .word   0xd088                  | add.l  %a0,%d0
        .word   0xe2a8                  | lsr.l  %d1,%d0
2:      .word   0x223c, 0x1c20, 0x0000  | move.l #471859200,%d1
        .word   0xa001, 0x0800          | mac.l  %d1,%d0,%acc0
        .word   0xa1c0                  | movclr.l %acc0,%d0
.Lf_rated:
#if DN2_LFO_HALFRATE
        tst.b   72(%sp)
        bne     .Lh_pre_end             | its first turn: no frame skipped
| (DN2_LFO_HALFRATE, the User 2026-11-19: "half rate lfo yes, but half rate env, no") a voice's LFOs step every second
| frame: before this frame's step, the frame it skipped, as stock's evaluator steps an LFO on a frame with no trig
| (from claude/mod-halfrate): the phase (%d6 a frame), its half-way and end holds (HALF, ONE), the wrap, the hold
| cleared (FREE, TRIG), the trig flag cleared, the fade (%d0 a frame, kept to 0..0x3fffffff), and for RND the sample
| when the phase moved past 86,400,000 (stock's random step) and the smoothing toward it. No output, no DEST write.
| %d0, %d3, %d5, %d6, %a2..%a5 kept; %d1, %d2, %d4, %d7, %a0, %a1 written again below.
        mvs.b   80(%a4), %d4            | MODE
        move.l  80(%a2), %d1            | the phase
        move.l  %d1, %d2
        add.l   %d6, %d2                | + a frame's step
        addi.l  #-691200000, %d1
        move.l  %d2, %d7
        addi.l  #-691200000, %d7
        eor.l   %d1, %d7
        bge.s   1f                      | not past half-way
        tst.b   117(%a2)
        bne.s   1f
        tst.b   (%a3)
        bne.s   1f
        moveq   #4, %d7
        cmp.l   %d4, %d7
        bne.s   1f
        lea     LF_TA4, %a0             | HALF: held at half-way
        move.l  (%a0,%d3.l*4), %d1
        move.l  %d1, 84(%a2)
        move.b  #1, (%a3)
1:      cmpi.l  #1382399999, %d2
        bls.s   3f
        tst.b   117(%a2)
        bne.s   2f
        tst.b   (%a3)
        bne.s   2f
        moveq   #3, %d1
        cmp.l   %d4, %d1
        bne.s   2f
        lea     LF_TDC, %a1             | ONE: held at the end
        tst.l   %d6
        blt.s   4f
        lea     LF_TC0, %a1
4:      move.l  (%a1,%d3.l*4), %d1
        move.l  %d1, 84(%a2)
        move.b  #1, (%a3)
2:      tst.l   %d6
        blt.s   5f
        addi.l  #-1382400000, %d2
        bra.s   3f
5:      addi.l  #1382400000, %d2
3:      moveq   #1, %d1
        cmp.l   %d4, %d1
        bcs.s   6f
        clr.b   (%a3)
6:      clr.b   117(%a2)
        move.l  %d2, 80(%a2)
        move.l  96(%a2), %d1            | the fade
        add.l   %d0, %d1
        bge.s   7f
        clr.l   %d1
        bra.s   8f
7:      cmpi.l  #1073741823, %d1
        ble.s   8f
        move.l  #1073741823, %d1
8:      move.l  %d1, 96(%a2)
        moveq   #6, %d1
        cmp.l   %d3, %d1
        bne.w   .Lh_pre_end
        tst.b   (%a3)                   | RND: held, no sample
        bne.s   9f
        tst.l   %d6
        blt.s   1f
        move.l  %d2, %d1
        sub.l   100(%a2), %d1
        bra.s   2f
1:      move.l  100(%a2), %d1
        sub.l   %d2, %d1
2:      cmpi.l  #86399999, %d1
        bls.s   9f
        move.l  %d2, 100(%a2)
        move.l  %d0, -(%sp)
        jsr     0x4013767c              | stock's random step
        move.l  %d0, 88(%a2)
        move.l  (%sp)+, %d0
9:      mvs.w   78(%a4), %d1            | the smoothing (stock's, SPH's table entry)
        asr.l   #8, %d1
        lea     0x4020b810, %a0
        move.l  (%a0,%d1.l*4), %d1
        move.l  #2147483647, %d7
        sub.l   %d1, %d7
        movea.l 88(%a2), %a0
        movea.l 92(%a2), %a1
        mac.l   %a0, %d7, %acc0
        mac.l   %a1, %d1, %acc0
        movclr.l %acc0, %d7
        move.l  %d7, 92(%a2)
.Lh_pre_end:
#endif
        .word   0x732c, 0x0050          | mvs.b  80(%a4),%d1
        .word   0x2406                  | move.l %d6,%d2
        .word   0x206a, 0x0050          | movea.l 80(%a2),%a0
        .word   0xd488                  | add.l  %a0,%d2
        .word   0xd1fc, 0xd6cd, 0x2000  | adda.l #-691200000,%a0
        .word   0x7941                  | mvs.w  %d1,%d4
        .word   0x2c41                  | movea.l %d1,%fp
        .word   0x2e02                  | move.l %d2,%d7
        .word   0x2208                  | move.l %a0,%d1
        .word   0x0687, 0xd6cd, 0x2000  | addi.l #-691200000,%d7
        .word   0xb387                  | eor.l  %d1,%d7
        .word   0xd0aa, 0x0060          | add.l  96(%a2),%d0
        .word   0x4a87                  | tst.l  %d7
        bge.s   1f
        .word   0x4a2a, 0x0075          | tst.b  117(%a2)
        bne.s   1f
        .word   0x4a13                  | tst.b  (%a3)
        bne.s   1f
        .word   0x7e04                  | moveq  #4,%d7
        .word   0xbe84                  | cmp.l  %d4,%d7
        bne.s   1f
        lea     LF_TA4, %a0             | lfowaves' table for 0x4020b7a4
        .word   0x41f0, 0x3c00          | lea    (%a0,%d3.l*4),%a0
        .word   0x2550, 0x0054          | move.l (%a0),84(%a2)
        .word   0x16bc, 0x0001          | move.b #1,(%a3)
1:      .word   0x0c82, 0x5265, 0xbfff  | cmpi.l #1382399999,%d2
        bls     .Lf_wrapped
        .word   0x4a2a, 0x0075          | tst.b  117(%a2)
        bne.s   2f
        .word   0x4a13                  | tst.b  (%a3)
        bne.s   2f
        .word   0x7203                  | moveq  #3,%d1
        .word   0xb284                  | cmp.l  %d4,%d1
        bne.s   2f
        lea     LF_TDC, %a1             | lfowaves' table for 0x4020b7dc
        .word   0x4a86                  | tst.l  %d6
        blt.s   1f
        lea     LF_TC0, %a1             | lfowaves' table for 0x4020b7c0
1:      .word   0x2071, 0x3c00          | movea.l (%a1,%d3.l*4),%a0
        .word   0x2548, 0x0054          | move.l %a0,84(%a2)
        .word   0x16bc, 0x0001          | move.b #1,(%a3)
2:      .word   0x4a86                  | tst.l  %d6
        blt.s   3f
        .word   0x0682, 0xad9a, 0x4000  | addi.l #-1382400000,%d2
        bra     .Lf_wrapped
3:      .word   0x0682, 0x5265, 0xc000  | addi.l #1382400000,%d2
.Lf_wrapped:
        .word   0x7201                  | moveq  #1,%d1
        .word   0xb284                  | cmp.l  %d4,%d1
        bcs.s   1f
        .word   0x4213                  | clr.b  (%a3)
1:      clr.b   117(%a2)                | stock: clr.b %d7 ; move.b %d7,117(%a2) (%d7 written again before it is read)
        .word   0x4aaf, 0x002c          | tst.l  44(%sp)
        beq     .Lf_nof
        .word   0x7201                  | moveq  #1,%d1
        .word   0xb284                  | cmp.l  %d4,%d1
        beq.s   1f
        .word   0x220e                  | move.l %fp,%d1
        .word   0x5781                  | subq.l #3,%d1
        .word   0x73c1                  | mvz.w  %d1,%d1
        .word   0x7e01                  | moveq  #1,%d7
        .word   0xbe81                  | cmp.l  %d1,%d7
        bcs     .Lf_mode
1:      .word   0x7006                  | moveq  #6,%d0
        .word   0xb083                  | cmp.l  %d3,%d0
        beq.s   1f
        .word   0x242f, 0x0044          | move.l 68(%sp),%d2
        .word   0x203c, 0x5265, 0xc000  | move.l #1382400000,%d0
        .word   0x4842                  | swap   %d2
        .word   0x4242                  | clr.w  %d2
        .word   0xa400, 0x0800          | mac.l  %d0,%d2,%acc0
        .word   0xa1c2                  | movclr.l %acc0,%d2
        bra.s   2f
1:      .word   0x4282                  | clr.l  %d2
2:      .word   0x7e01                  | moveq  #1,%d7
        .word   0x736c, 0x0048          | mvs.w  72(%a4),%d1
        .word   0x203c, 0x3fff, 0xffff  | 0x40137508 of %d1, inline: move.l #0x3fffffff,%d0
        cmpi.l  #16383, %d1
        bgt.s   1f
        .word   0x4280                  | clr.l  %d0
1:      .word   0x4213                  | clr.b  (%a3)
        .word   0x1547, 0x0075          | move.b %d7,117(%a2)
.Lf_mode:
        .word   0x4a84                  | tst.l  %d4
        bne     .Lf_mode2
        .word   0x4213                  | clr.b  (%a3)
        .word   0x716c, 0x0048          | mvs.w  72(%a4),%d0
        cmpi.l  #16383, %d0             | 0x40137508 of %d0, inline
        bgt     .Lf_sat
        .word   0x4280                  | clr.l  %d0
.Lf_nof:
        .word   0x4287                  | clr.l  %d7
.Lf_fade:
        .word   0x2542, 0x0050          | move.l %d2,80(%a2)
        .word   0x2c40                  | movea.l %d0,%fp
        .word   0x4a80                  | tst.l  %d0
        bge.s   1f
        .word   0x9dce                  | suba.l %fp,%fp
        bra.s   2f
1:      .word   0x0c80, 0x3fff, 0xffff  | cmpi.l #1073741823,%d0
        ble.s   2f
        .word   0x2c7c, 0x3fff, 0xffff  | movea.l #1073741823,%fp
2:      .word   0x254e, 0x0060          | move.l %fp,96(%a2)
        .word   0x4a13                  | tst.b  (%a3) (stock reads 84(%a2) into %d0 first: only the held way keeps it)
        beq.s   1f
        .word   0x4a87                  | tst.l  %d7
        beq     .Lf_held
1:      .word   0x7006                  | moveq  #6,%d0
        .word   0xb083                  | cmp.l  %d3,%d0
        beq     .Lf_rnd
        .word   0x203c, 0x636b, 0xa875  | move.l #1667999861,%d0
        .word   0xa400, 0x0800          | mac.l  %d0,%d2,%acc0
        .word   0xa1c2                  | movclr.l %acc0,%d2
        .word   0xe58a                  | lsl.l  #2,%d2
        lea     LF_FN, %a0              | lfowaves' a_call, inline: its function table,
        .word   0x43ec, 0x004e          | lea    78(%a4),%a1 (&SPH)
        .word   0x2009                  | move.l %a1,%d0 (the instance key: ((%a1 >> 1) & 1023) << 8,
        lsl.l   #7, %d0                 | as (%a1 << 7) & 0x3ff00)
        andi.l  #0x3ff00, %d0
        .word   0x732c, 0x004e          | mvs.b  78(%a4),%d1 (SPH)
        .word   0x0281, 0x0000, 0x007f  | andi.l #0x7f,%d1
        .word   0x8280                  | or.l   %d0,%d1
        .word   0x2070, 0x3c00          | movea.l (%a0,%d3.l*4),%a0
        cmpa.l  #LF_NOISE, %a0          | (2026-11-21, the User's CPU) lfowaves' NOIS: the same values from noise_fast
        bne.s   1f                      | (below; dnfw.waverider.lfofast checks NOIS's bytes are what it replays)
        lea     noise_fast, %a0
1:      .word   0x2f02                  | move.l %d2,-(%sp)
        .word   0x4e90                  | jsr    (%a0)
        .word   0x588f                  | addq.l #4,%sp
.Lf_out:
        .word   0x2540, 0x005c          | move.l %d0,92(%a2)
        .word   0x4a13                  | tst.b  (%a3)
        beq.s   1f
        .word   0x4a87                  | tst.l  %d7
        beq.s   2f
1:      .word   0xa00e, 0x0800          | mac.l  %fp,%d0,%acc0
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0xd080                  | add.l  %d0,%d0
        .word   0x2540, 0x0054          | move.l %d0,84(%a2)
2:
| (2026-11-19, the User: DEP is the LFO's global attenuverter; docs/matrix.md "DEP: the attenuverter") every route of
| this LFO is heard at its own depth x DEP. When the LFO steps (with DN2_LFO_HALFRATE, at its voice's turn: a held
| output keeps the scale of its last turn), its output is scaled by M from the DEP cell as stock reads it (every source
| of DEP in it: p-locks, CC, Overbridge, MOD SETUP, an earlier LFO): mx_atab by DEP >> 7, -a << 17 with a = DEP - 0x4000
| (stock's own DEP scale; exact at every knob step, 0x100), +63 and above (and MOD SETUP's 0x8000..) exactly 100 %
| (-2^31: exactly -out), DEP 0 -16383. -out x DEP goes into our word beside the LFO state (matrix.c mx_kof: env_out's
| row, word 2 + 10 l), the record's routes' source (their depths laid negated). The first route (below): -2 x (its
| own depth - 0x4000) from word 3 + 10 l (mx_eval) on it: stock's product at 100 %; that word 1 (a sound not
| converted, a sound lock, LFO4, before the load's first UI pass): stock's route 1 itself, DEP its depth. %fp, %a0,
| %d1 and %d7 are free here (written before they are read again); %d0 keeps the output.
        movea.l mx_kof, %fp
        mvz.w   82(%a4), %d7            | DEP
        lsr.l   #7, %d7
        lea     mx_atab, %a0
        move.l  (%a0,%d7.l*4), %d1      | M
        mac.l   %d1, %d0, %acc0
        movclr.l %acc0, %d1             | -out x DEP
        move.l  %d1, (%a2,%fp.l)
.Lf_dest:                               | (a held output's way: %fp = mx_kof, .Lh_lfo)
        mvs.b   74(%a4), %d7            | DEST (stock: mvs.b 74(%a4),%d2 ; mvs.w %d2,%d7: %d2 dead here)
#if DN2_LFO4
        .word   0x726c                  | moveq  #108,%d1 (lfo4: DEST up to 108)
#else
        .word   0x7264                  | moveq  #100,%d1
#endif
        .word   0x2547, 0x0068          | move.l %d7,104(%a2)
        .word   0xb287                  | cmp.l  %d7,%d1
        bcs     .Lf_nodest
        lea     mod_wb_kind, %a0        | mod_wb, inline (DEST is 0..108 here, 0..100 without lfo4): the DEST's kind
        move.b  (%a0,%d7.l), %d1
        movea.l 52(%sp), %a0
        beq.w   2f                      | 0: stock's write
        bpl.s   1f                      | 1: LFO4's controls: mod_wb_cell
        move.l  %d7, %d1                | -1: an LFO's control
        subq.l  #1, %d1
        lsr.l   #3, %d1
        cmp.l   48(%sp), %d1
        ble.w   2f                      | not above this one: stock's write
1:
#if DN2_LFO4
        move.l  %d0, -(%sp)
        move.l  %a1, -(%sp)
        move.l  %a0, -(%sp)
        move.l  %d7, -(%sp)
        move.l  64(%sp), -(%sp)         | the LFO counter (48(%sp) before the four pushes)
        move.l  %a5, -(%sp)
        jsr     mod_wb_cell
        lea     16(%sp), %sp
        movea.l %d0, %a0
        movea.l (%sp)+, %a1
        move.l  (%sp)+, %d0
#else
| (2026-11-21, the User's CPU) cascade.c mod_wb_cell, inline, the same steps: here DEST is 9..24 (an LFO's control)
| and above this LFO, the row (%a5) 0..15; a DEST that is its LFO's own DEST (f 3) or the state not loaded: %a0 kept
| (stock's write); else the shadow cell, started from the mirror's cell (%a0 + 2 DEST) at its first write this frame,
| marked used, the row marked, %a0 = the shadow row - 18. %d1-%d3 are free here (written before they are read
| again), %fp is mx_kof again after it; %d0 and %a1 untouched.
        moveq   #7, %d2
        and.l   %d7, %d2
        subq.l  #4, %d2                 | f = (DEST - 1) & 7 == 3: DEST & 7 == 4
        beq.s   2f
        move.l  MOD_RAM_A, %d1          | MC_MAGIC, and this load's clear done (mc_loaded)
        cmpi.l  #0x4D433031, %d1
        bne.s   2f
        tst.l   mc_loaded
        beq.s   2f
        move.l  %a5, %d1                | the row: MOD_RAM + 12 + 68 v
        lsl.l   #2, %d1
        move.l  %d1, %d2
        lsl.l   #4, %d2
        add.l   %d2, %d1
        lea     MOD_RAM_A + 12, %fp
        adda.l  %d1, %fp
        moveq   #-9, %d2
        add.l   %d7, %d2                | b = DEST - 9
        moveq   #1, %d1
        lsl.l   %d2, %d1                | its bit
        mvz.w   2(%fp), %d3             | init
        and.l   %d1, %d3
        bne.s   3f
        move.w  (%a0,%d7.l*2), %d3      | the mirror's cell: sh[b] = base[b] = it
        move.w  %d3, 4(%fp,%d2.l*2)
        move.w  %d3, 36(%fp,%d2.l*2)
        mvz.w   2(%fp), %d3
        or.l    %d1, %d3
        move.w  %d3, 2(%fp)
3:      mvz.w   (%fp), %d3              | used |= bit
        or.l    %d1, %d3
        move.w  %d3, (%fp)
        moveq   #1, %d1                 | rows |= 1 << v
        move.l  %a5, %d2
        lsl.l   %d2, %d1
        or.l    %d1, MOD_RAM_A + 12 + 68 * 16
        lea     -14(%fp), %a0           | sh - 18 (+ 2 DEST: sh[DEST - 9])
        movea.l mx_kof, %fp
#endif
2:      move.l  4(%a2,%fp.l), %d1       | (2026-11-19) this voice's first route: -2 x (its depth - 0x4000) (mx_eval)
        btst    #0, %d1
        bne     .Ld_stock               | 1: DEP is its depth (stock's route 1, below)
        move.l  (%a2,%fp.l), %d0        | on -out x DEP: stock's product at 100 %
        .word   0x4df0, 0x7a00          | lea    (%a0,%d7.l*2),%fp
.Ld_mac:
        .word   0xa001, 0x0800          | mac.l  %d1,%d0,%acc0
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0x2540, 0x006c          | move.l %d0,108(%a2)
        .word   0x7356                  | mvs.w  (%fp),%d1
        .word   0xd081                  | add.l  %d1,%d0
        bpl.s   1f
        .word   0x4280                  | clr.l  %d0
        bra.s   2f
1:      .word   0x0c80, 0x0000, 0x7f00  | cmpi.l #32512,%d0
        ble.s   2f
        .word   0x203c, 0x0000, 0x7f00  | move.l #32512,%d0
2:      .word   0x3c80                  | move.w %d0,(%fp)
.Lf_nodest:
        .word   0x4a13                  | tst.b  (%a3)
        beq.s   1f
        .word   0x42aa, 0x0070          | clr.l  112(%a2)
        bra.s   2f
1:      .word   0x256a, 0x0050, 0x0070  | move.l 80(%a2),112(%a2)
2:
#if DN2_LFO4
        .word   0x53af, 0x0030          | subq.l #1,48(%sp)
        .word   0x45ea, 0xffd8          | lea    -40(%a2),%a2
        .word   0x47eb, 0xffd8          | lea    -40(%a3),%a3
        move.l  48(%sp), %d1            | lfo4's a4_bottom, inline: the next LFO's row cells
        subq.l  #2, %d1
        beq.s   1f                      | LFO4 done: LFO3, at the row's
        .word   0x49ec, 0xfff0          | lea    -16(%a4),%a4
        addq.l  #3, %d1
        bne     .Lf_lfo                 | the counter not yet -1
        bra.s   2f
1:      .word   0x286f, 0x0034          | movea.l 52(%sp),%a4
        .word   0x49ec, 0xffde          | lea    -34(%a4),%a4
        bra     .Lf_lfo
2:      .word   0x223c, 0x0000, 0x00ca  | lfo4's outer, inline: move.l #202,%d1
        .word   0xd3af, 0x0034          | add.l  %d1,52(%sp)
        .word   0x223c, 0x0000, 0x0099  | move.l #153,%d1
        .word   0xd3af, 0x003c          | add.l  %d1,60(%sp)
        .word   0x223c, 0x0000, 0x00a0  | move.l #160,%d1
        .word   0xd3af, 0x0038          | add.l  %d1,56(%sp)
        .word   0x528d                  | addq.l #1,%a5
        .word   0x7010                  | moveq  #16,%d0
        .word   0xb08d                  | cmp.l  %a5,%d0
        bne     .Lf_voice
#else
        .word   0x53af, 0x0030          | subq.l #1,48(%sp) (stock's bottom and outer, word for word)
        .word   0x45ea, 0xffd8          | lea    -40(%a2),%a2
        .word   0x70ff                  | moveq  #-1,%d0
        .word   0x47eb, 0xffd8          | lea    -40(%a3),%a3
        .word   0x49ec, 0xfff0          | lea    -16(%a4),%a4
        .word   0xb0af, 0x0030          | cmp.l  48(%sp),%d0
        bne     .Lf_lfo
        .word   0x223c, 0x0000, 0x00ca  | move.l #202,%d1
        .word   0x7e78                  | moveq  #120,%d7
        .word   0x243c, 0x0000, 0x0099  | move.l #153,%d2
        .word   0x528d                  | addq.l #1,%a5
        .word   0xd3af, 0x0034          | add.l  %d1,52(%sp)
        .word   0xd5af, 0x003c          | add.l  %d2,60(%sp)
        .word   0xdfaf, 0x0038          | add.l  %d7,56(%sp)
        .word   0x7010                  | moveq  #16,%d0
        .word   0xb08d                  | cmp.l  %a5,%d0
        bne     .Lf_voice
#endif
        .word   0x4cd7, 0x7cfc          | movem.l (%sp),%d2-%d7/%a2-%fp
        .word   0x4fef, 0x004c          | lea    76(%sp),%sp
        .word   0x4e75                  | rts
| the ways stock takes less often, out of the common way's line (each goes back where stock goes)
.Lf_clr:
        .word   0x42af, 0x002c          | clr.l  44(%sp)
        bra     .Lf_par
.Lf_sat:
        .word   0x203c, 0x3fff, 0xffff  | move.l #0x3fffffff,%d0
        bra     .Lf_nof
.Lf_mode2:
        .word   0x7202                  | moveq  #2,%d1
        .word   0xb284                  | cmp.l  %d4,%d1
        bne     .Lf_nof
        .word   0x16bc, 0x0001          | move.b #1,(%a3)
        .word   0x7e01                  | moveq  #1,%d7
        bra     .Lf_fade
.Lf_rnd:
        .word   0x4a86                  | tst.l  %d6
        blt.s   1f
        .word   0x2002                  | move.l %d2,%d0
        .word   0x90aa, 0x0064          | sub.l  100(%a2),%d0
        bra.s   2f
1:      .word   0x202a, 0x0064          | move.l 100(%a2),%d0
        .word   0x9082                  | sub.l  %d2,%d0
2:      .word   0x0c80, 0x0526, 0x5bff  | cmpi.l #86399999,%d0
        bhi.s   1f
        .word   0x4a84                  | tst.l  %d4
        beq     .Lf_smooth
        .word   0x4aaf, 0x002c          | tst.l  44(%sp)
        beq     .Lf_smooth
1:      .word   0x2542, 0x0064          | move.l %d2,100(%a2)
        jsr     0x4013767c              | stock's random step
        .word   0x2540, 0x0058          | move.l %d0,88(%a2)
        bra     .Lf_smooth
.Lf_held:
        .word   0x202a, 0x0054          | move.l 84(%a2),%d0
        .word   0x7206                  | moveq  #6,%d1
        .word   0xb283                  | cmp.l  %d3,%d1
        bne     .Lf_out
.Lf_smooth:
        .word   0x202f, 0x0044          | move.l 68(%sp),%d0
        .word   0xe080                  | asr.l  #8,%d0
        .word   0x41f9, 0x4020, 0xb810  | lea    0x4020b810,%a0
        .word   0x226a, 0x005c          | movea.l 92(%a2),%a1
        .word   0x2230, 0x0c00          | move.l (%a0,%d0.l*4),%d1
        .word   0x203c, 0x7fff, 0xffff  | move.l #2147483647,%d0
        .word   0x206a, 0x0058          | movea.l 88(%a2),%a0
        .word   0x9081                  | sub.l  %d1,%d0
        .word   0xa008, 0x0800          | mac.l  %a0,%d0,%acc0
        .word   0xa209, 0x0800          | mac.l  %a1,%d1,%acc0
        .word   0xa1c0                  | movclr.l %acc0,%d0
        .word   0x2540, 0x0054          | move.l %d0,84(%a2)
        bra     .Lf_out
| (2026-11-19) the first route as stock's route 1, DEP its depth (stock's words): a sound not converted, a voice on a
| sound lock, LFO4, the frames before the load's first UI pass (matrix.c MX_PASS)
.Ld_stock:
        .word   0x736c, 0x0052          | mvs.w  82(%a4),%d1
        .word   0x4df0, 0x7a00          | lea    (%a0,%d7.l*2),%fp
        .word   0x0681, 0xffff, 0xc000  | addi.l #-16384,%d1
        .word   0xd281                  | add.l  %d1,%d1
        bra     .Ld_mac
#if DN2_LFO_HALFRATE
.Lh_lfo:                                | (DN2_LFO_HALFRATE) not this voice's turn: the LFO's output as its last turn
        move.l  84(%a2), %d0            | left it, into its DEST (stock's write, mod_wb, the clamp) as every frame
        movea.l mx_kof, %fp             | (2026-11-19) its scaled output as its last turn left it (mx_kof's word)
        bra     .Lf_dest
#endif
| a wrong MACSR mode: stock's rate routine, which reports it as stock does
.Lf_rate_stock:
        .word   0xa981                  | move.l %macsr,%d1 (the registers as stock's test leaves them)
        .word   0x0281, 0x0000, 0x00f0  | andi.l #0xf0,%d1
        .word   0x7e20                  | moveq  #32,%d7
        .word   0x2f00                  | move.l %d0,-(%sp)
        jsr     0x4013748c
        .word   0x588f                  | addq.l #4,%sp
        bra     .Lf_rated

| mod_wb's DEST kinds, 0..127: 0 stock's write, -1 an LFO's control (9..24), 1 LFO4's (101..108, DN2_LFO4)
        .section .rodata
| lfo_fast's MULT clamp by MULT's signed byte (mvs.b, as stock reads it; lf_mult is entry 0, -128..-1 before it): the
| shift's base 0..11, 0x80 when the multiplier is 14400 (MULT 12..23, and above 23 clamped to 23); below 0: 0 with
| 84(%sp), as stock's code
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        .byte   0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
lf_mult:
        .byte   0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x80, 0x81, 0x82, 0x83
        .byte   0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
        .byte   0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b, 0x8b
| lfo_fast's WAVE clamp by WAVE's signed byte (lf_wave entry 0, -128..-1 before it): 0..13 (below 0: 0, above 13: 13,
| as stock's code with lfowaves' bound), 0x80 set when WAVE < 7 (lfowaves' no_phase: a stock shape, SPH its start phase)
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
        .byte   0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80
lf_wave:
        .byte   0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
        .byte   0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d, 0x0d
mod_wb_kind:
        .byte   0, 0, 0, 0, 0, 0, 0, 0, 0
        .byte   -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1
        .fill   76, 1, 0
#if DN2_LFO4
        .byte   1, 1, 1, 1, 1, 1, 1, 1
#else
        .byte   0, 0, 0, 0, 0, 0, 0, 0
#endif
        .fill   19, 1, 0
        .text

| noise_fast (2026-11-21, the User: "we are tight in CPU"): lfowaves' NOIS (scripts/build_lfo_waveshapes.py, noise and
| its hash 90:) with the same result in %d0 and %d1, the same 8 bytes of state written, %d2-%d7/%a2 kept: the hash
| inline (the octave's stream offset (k << 12) + 1 as one add, the shifts by 15 and 13 from registers), pink's and
| brown's six octaves unrolled (the weights' shifts as immediates). The sums are the same words in another order of
| addition (mod 2^32: the same). lfo_fast calls it in place of NOIS (dnfw.waverider.lfofast: NOIS's bytes checked).
        .macro  NH add                  | %d0 = hash(%d0 + add): x *= 0x9e3779b1 ; x ^= x >> 15 ; x *= 0x85ebca77 ;
        addi.l  #\add, %d0              | x ^= x >> 13
        muls.l  %d3, %d0
        move.l  %d0, %d2
        lsr.l   %d6, %d2
        eor.l   %d2, %d0
        muls.l  %d5, %d0
        move.l  %d0, %d2
        lsr.l   %d7, %d2
        eor.l   %d2, %d0
        .endm
        .macro  NOCT k, w               | octave K at weight W into the sum %d1
        move.l  %d4, %d0
        .if \k
        lsr.l   #\k, %d0
        .endif
        NH      (\k << 12) + 1
        asr.l   #\w, %d0
        .if \k
        add.l   %d0, %d1
        .else
        move.l  %d0, %d1
        .endif
        .endm
        .globl  noise_fast
noise_fast:
        lea     -28(%sp), %sp
        movem.l %d2-%d7/%a2, (%sp)
        move.l  32(%sp), %d4            | the phase
        moveq   #26, %d2
        lsr.l   %d2, %d4                | step 0..63
        move.l  %d1, %d0
        lsr.l   #8, %d0                 | the instance key
        lsl.l   #3, %d0
        lea     0x46740000, %a2         | lfowaves' NOISE_RAM: this LFO's 8 bytes
        adda.l  %d0, %a2
        move.l  %d1, %d5
        andi.l  #31, %d5                | loop field
        move.l  4(%a2), %d3             | cycle
        move.l  %d4, %d0
        sub.l   (%a2), %d0              | step - last
        cmpi.l  #-32, %d0
        bge.s   1f
        addq.l  #1, %d3
1:      cmpi.l  #32, %d0
        ble.s   2f
        subq.l  #1, %d3
2:      cmpi.l  #31, %d5
        beq.s   4f
        cmp.l   %d5, %d3
        bls.s   4f
        clr.l   %d3
        tst.l   %d0
        ble.s   4f
        move.l  %d5, %d3
4:      move.l  %d4, (%a2)
        move.l  %d3, 4(%a2)
        lsl.l   #6, %d3
        or.l    %d3, %d4                | n = cycle << 6 | step
        andi.l  #0x7f, %d1
        lsr.l   #5, %d1                 | colour 0..3
        move.l  #0x9e3779b1, %d3
        move.l  #0x85ebca77, %d5
        moveq   #15, %d6
        moveq   #13, %d7
        tst.l   %d1
        beq.w   10f
        cmpi.l  #3, %d1
        beq.w   30f
        cmpi.l  #1, %d1
        bne.w   20f
        NOCT    0, 3                    | pink: equal weight
        NOCT    1, 3
        NOCT    2, 3
        NOCT    3, 3
        NOCT    4, 3
        NOCT    5, 3
        move.l  %d1, %d0
        bra.w   99f
20:     NOCT    0, 6                    | brown: 2^-(6 - k)
        NOCT    1, 5
        NOCT    2, 4
        NOCT    3, 3
        NOCT    4, 2
        NOCT    5, 1
        move.l  %d1, %d0
        bra.s   99f
10:     move.l  %d4, %d0                | white (%d1 stays 0, as NOIS leaves it)
        NH      1
        bra.s   99f
30:     move.l  %d4, %d0                | violet
        NH      1
        move.l  %d0, %d1
        move.l  %d4, %d0
        subq.l  #1, %d0
        NH      1
        sub.l   %d0, %d1
        move.l  %d1, %d0
        asr.l   #1, %d0
99:     movem.l (%sp), %d2-%d7/%a2
        lea     28(%sp), %sp
        rts
