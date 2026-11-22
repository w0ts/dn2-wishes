| The sample link's hooks in stock code (csrc/sampler/link.c, docs/sampler.md): each
| replaces a few bytes with a `jsr` here, calls the C, and replays what it replaced.
| (v0.20: the frame builder's hook is gone: the frame is stock's again.)

        .text
        .globl  smp_rx_hook

| The SysEx router 0x4012194e at 0x4012197a (was: lea 0x40207f9e,%a3), once per F0
| message other than F0 7E, in the MIDI input task: a0 = a1 = the message, d1 its
| length, d2 its source; those must survive, and d0, d3, a2 are free (the USB probe's
| hook site, docs/usbprobe.md). smp_rx(msg, len, source) only reads the message.
smp_rx_hook:
        lea     -20(%sp), %sp
        movem.l %d0-%d2/%a0-%a1, (%sp)
        move.l  %d2, -(%sp)
        move.l  %d1, -(%sp)
        move.l  %a0, -(%sp)
        jsr     smp_rx
        lea     12(%sp), %sp
        movem.l (%sp), %d0-%d2/%a0-%a1
        lea     20(%sp), %sp
        lea     0x40207f9e, %a3
        rts

| The parameter setter 0x40037b74 at 0x40037be6 (was: movea.l %d0,%a0 ; move.w
| %d3,0x14(%a0,%d2.l*2)), where a turn's value is written into the sound: d0 the sound,
| d2 the slot, d3 the value (values[] at sound + 0x14; objdump prints the 0x14 as "14"). smp_quant (fmt.c) may move the value to the next
| choice of a sample machine's control; d3 leaves as what was written, a0 as d0, every
| other register as it came (the setter goes on to pass d0 and d3 along).
        .globl  smp_quant_hook
smp_quant_hook:
        lea     -12(%sp), %sp
        movem.l %d0-%d1/%a1, (%sp)
        move.l  %d4, -(%sp)                     | v0.32: the record id (the setter's d4)
        move.l  %d3, -(%sp)
        move.l  %d2, -(%sp)
        move.l  %d0, -(%sp)
        jsr     smp_quant
        lea     16(%sp), %sp
        move.l  %d0, %d3
        movem.l (%sp), %d0-%d1/%a1
        lea     12(%sp), %sp
        movea.l %d0, %a0
        move.w  %d3, 0x14(%a0,%d2.l*2)
        rts

| 2026-11-11, the kit setter 0x40037d86 at 0x40037df6 (was: movea.l %d0,%a0 ; move.w %d3,(%a0,%d2.l*2)), the
| Reverb and Delay pages' TYPE (records 131, 122): d0 the value words, d2 the slot, d3 the value, d4 the record
| id. fx_type_quant (fmt.c) may move the value to the next entry of the list's order; d3 leaves as what was
| written, a0 as d0, every other register as it came (the setter goes on to compare d4 and pass d3 along).
        .globl  fx_type_hook
fx_type_hook:
        lea     -12(%sp), %sp
        movem.l %d0-%d1/%a1, (%sp)
        move.l  %d4, -(%sp)
        move.l  %d3, -(%sp)
        move.l  %d2, -(%sp)
        move.l  %d0, -(%sp)
        jsr     fx_type_knob                    | (2026-11-19: fx_type_quant, then the knob notch)
        lea     16(%sp), %sp
        move.l  %d0, %d3
        movem.l (%sp), %d0-%d1/%a1
        lea     12(%sp), %sp
        movea.l %d0, %a0
        move.w  %d3, (%a0,%d2.l*2)
        rts

| The SSI audio ISR 0x40025e36 at 0x40026098 (was: move.l %fp,%d2 ; addi.l #-72,%d2, 8
| bytes; now jsr here and a nop), v0.16: every mode's transmit fill has ended there
| (docs/link-research.md 6c), so smp_tdm(h) writes our packet into slots 8..15 of the
| transmit half h = %fp@(-56) and reads the DSP's from slots 14..15 of the receive half.
| Every register lives on in the ISR, so every one C may touch is kept; d2 leaves as the
| two replayed instructions leave it (the ISR pushes it next).
        .globl  smp_tdm_hook
smp_tdm_hook:
        lea     -20(%sp), %sp
        movem.l %d0-%d2/%a0-%a1, (%sp)
        move.l  0xfc07000c, %d0         | the system meter (csrc/meter): the ISR's time from here
        move.l  %d0, METER_RAM + 4      | mtr_t_in (its entry 0x40025e36..here is Overbridge's path: untouched)
#if DN2_STOCK_LINK_FAST
        move.l  smp_tdm_sent, -(%sp)    | (stocklink: whether smp_tdm sends a packet this frame)
#endif
        move.l  -56(%fp), -(%sp)
        jsr     smp_tdm
        addq.l  #4, %sp
#if DN2_STOCK_LINK_FAST
        move.l  (%sp)+, %d0
        sub.l   smp_tdm_sent, %d0       | 0: nothing sent
        move.l  %d0, -(%sp)
        move.l  -56(%fp), -(%sp)
        jsr     skl_tx_after            | csrc/stocklink: the transmit half's clears, after the packet
        addq.l  #8, %sp
#endif
        move.l  PROF_RAM + 88, %d0      | 2026-11-11, the profiler's AUDIO source (csrc/devtest/prof.c W_AUDIO_GATE)
        cmpi.l  #0x50524641, %d0        | 'PRFA' only while it runs: a load and a compare a frame otherwise
        bne.s   1f
        pea     4(%fp)                  | the ISR's exception frame (0x40025e36: link %fp,#-236)
        jsr     prof_audio
        addq.l  #4, %sp
1:      movem.l (%sp), %d0-%d2/%a0-%a1
        lea     20(%sp), %sp
        move.l  %fp, %d2
        addi.l  #-72, %d2
        rts

| v0.38, per-project pools (csrc/sampler/pools.c, docs/project-pools.md): four detours in the
| OS's project code, each entered by a `jmp` (so the stack is as the stock code left it),
| each replaying what it replaced and going on where it left off. They only count and note
| the slot, in the OS's own task; pools.c's poll does the work in the UI task. Each bumps
| smp_blank_req too: the audio ISR's next packets empty the DSP's directory at once, so no
| sample track plays a sample of the old pool while the new one is set up.
|
| ProjectManager's load 0x40042E6E(project, slot, cb), its entry (was: lea -36(%sp),%sp ;
| movem.l %d2-%d5/%a2,(%sp)): a LOAD begins (it may fail: smp_pj_ends says when it is over)
        .globl  smp_pj_begin_hook
smp_pj_begin_hook:
        lea     -36(%sp), %sp
        movem.l %d2-%d5/%a2, (%sp)
        addq.l  #1, smp_pj_begins
        addq.l  #1, smp_blank_req
        jmp     0x40042E76

| .. at 0x40042ED2, reached only when the load and the temp slot's write both succeeded, d5
| the slot (was: move.l %d5,-(%sp) ; move.l %d3,-(%sp) ; jsr 0x4003EB62, the slot set): the
| slot is set as stock sets it, then noted. d0 (the setter's answer) is dead from here (the
| stock code overwrites it at 0x40042EE6); the two pushes stay for 0x40042EE2's lea to pop.
        .globl  smp_pj_loaded_hook
smp_pj_loaded_hook:
        move.l  %d5, -(%sp)
        move.l  %d3, -(%sp)
        jsr     0x4003EB62
        move.l  %d5, smp_pj_slot
        moveq   #1, %d0
        move.l  %d0, smp_pj_last
        addq.l  #1, smp_pj_loads
        jmp     0x40042EDA

| .. its exit 0x40042EE6 (was: move.b %d4,%d0 ; movem.l (%sp),%d2-%d5/%a2 ; lea 36(%sp),%sp,
| then rts at 0x40042EF0): the LOAD is over, whatever came of it. The count first, so the
| move.b sets the flags as stock's did.
        .globl  smp_pj_end_hook
smp_pj_end_hook:
        addq.l  #1, smp_pj_ends
        move.b  %d4, %d0
        movem.l (%sp), %d2-%d5/%a2
        lea     36(%sp), %sp
        rts

| NEW 0x400428C0(project, slot) where it sets the slot, 0x40042AF0 (was: move.l 12(%fp),(%sp) ;
| move.l %a2,-(%sp) ; jsr 0x4003EB62): the slot set as stock sets it, then noted (12(%fp) is
| the slot: -1 for the NEW menu and CLEAR, the slot for a LOAD of an empty one). d0 is dead
| from here (0x40042AFE's call overwrites it before anything reads it).
        .globl  smp_pj_new_hook
smp_pj_new_hook:
        move.l  12(%fp), (%sp)
        move.l  %a2, -(%sp)
        jsr     0x4003EB62
        move.l  12(%fp), %d0
        move.l  %d0, smp_pj_newslot
        moveq   #2, %d0
        move.l  %d0, smp_pj_last
        addq.l  #1, smp_pj_news
        addq.l  #1, smp_blank_req
        jmp     0x40042AFA

| v0.48 (owner, 2026-11-09: KEYBOARD mode should survive grid recording). The RECORD key's
| handler (0x40072cee.., a2 the handler) toggles grid recording (0x40055d72) and then asks
| whether it is now on (jsr 0x40055cca(rec) at 0x40072d74 and 0x40072dca): when it is, stock
| keeps KEYBOARD's state in a2@(136) and turns KEYBOARD off (0x40047002(kbd, 0), kbd =
| a2@(116)). Stock gives it back only when a held RECORD is let go (0x40072e62); a second
| RECORD press that turns grid recording off left KEYBOARD off. Here, in place of that jsr:
| the same question; when the answer is "off" and KEYBOARD was on when grid recording began,
| KEYBOARD is turned back on exactly as stock's own release path does (clear a2@(136), then
| 0x40047002(kbd, 1)). d0 leaves as stock's answer; d1, a0, a1 are scratch at both sites
| (the caller pops the argument and tests d0 next); every other register as it came.
        .globl  kb_rec_hook
kb_rec_hook:
        move.l  4(%sp), -(%sp)                  | rec (the caller's argument)
        jsr     0x40055cca                      | is grid recording on now?
        addq.l  #4, %sp
        tst.b   %d0
        bne.s   1f                              | on: stock goes on to keep and clear KEYBOARD
        tst.b   136(%a2)
        beq.s   1f                              | KEYBOARD was off when it began: nothing to give back
        clr.b   136(%a2)
        moveq   #1, %d0
        move.l  %d0, -(%sp)
        move.l  116(%a2), -(%sp)
        jsr     0x40047002                      | KEYBOARD on again (stock's release path's call)
        addq.l  #8, %sp
        moveq   #0, %d0                         | stock's answer: off
1:      rts

| v0.65 PROJECT RAM banks (docs/banks.md): the per-frame driver's jsr 0x40137a06 at 0x400272d4 (the
| LFOs, once a frame for every track, seven arguments on the stack). Here: the caller's return
| put aside, so the arguments lie where the evaluator expects them; the evaluator; then
| smp_lfo_fix (link.c) puts each sample voice's bank back from its target (an LFO's raw offset
| on SAMP's word moves its low byte, the bank); d0 as the evaluator left it, the return back.
| The caller pops the arguments itself (lea 28(%sp),%sp). The audio interrupt does not nest.
        .globl  smp_lfo_hook
smp_lfo_hook:
        move.l  (%sp)+, smp_lfo_ret
        jsr     0x40137a06
        lea     -12(%sp), %sp
        movem.l %d0-%d1/%a0, (%sp)
        jsr     smp_lfo_fix
        movem.l (%sp), %d0-%d1/%a0
        lea     12(%sp), %sp
        move.l  smp_lfo_ret, -(%sp)
        rts
        .data
        .align  4
smp_lfo_ret:
        .long   0
        .text

| ---- smp_tdm's packet words (2026-11-21, the User's CPU: "assembly for the most host CPU code") ------------------
| tdm_units(q, src, nn, job, sum, tag) -> sum: link.c smp_tdm's RX_WORDS (124) words into the transmit half, word j as
| unit 4 + 2 j (its low half) and 5 + 2 j (its high half), each TAG | the half (TDM slots 8..15 of the frame rows: unit
| i at row i >> 3, slot 8 + (i & 7)); Q the place of unit 4 (row 0, slot 12). Words 0..NN-1 from SRC (longs) or, SRC
| 0, from JOB (little-endian, bytewise: le32), the rest 0. The stores in the C's order (unit 4, 5, 6, ...), the sum of
| every half added to SUM (mod 2^32). gcc kept its loop's values on the stack: ~25 instructions a word, here ~13.
| C ABI: d0, d1, a0, a1 scratch.
        .macro  TDMW                    | the word in %d1 -> its two units; %d4 words left in the row
        mvz.w   %d1, %d5
        add.l   %d5, %d0
        or.l    %d3, %d5
        move.l  %d5, (%a0)+
        clr.w   %d1
        swap    %d1
        add.l   %d1, %d0
        or.l    %d3, %d1
        move.l  %d1, (%a0)+
        subq.l  #1, %d4
        bne.s   9f
        lea     32(%a0), %a0            | slot 16 -> the next row's slot 8
        moveq   #4, %d4
9:
        .endm
        .globl  tdm_units
tdm_units:
        lea     -20(%sp), %sp
        movem.l %d2-%d5/%a2, (%sp)
        movem.l 24(%sp), %a0-%a1                | q, src
        move.l  32(%sp), %d2                    | nn
        movea.l 36(%sp), %a2                    | job
        move.l  40(%sp), %d0                    | sum
        move.l  44(%sp), %d3                    | tag
        moveq   #2, %d4                         | row 0: units 4..7
        moveq   #124, %d1
        cmp.l   %d1, %d2
        bls.s   1f
        move.l  %d1, %d2                        | (at most the 124)
1:      move.l  %d2, -(%sp)                     | the zeros after: 124 - nn
        tst.l   %d2
        beq.s   5f
        move.l  %a1, %d1
        beq.s   3f
2:      move.l  (%a1)+, %d1                     | from SRC
        TDMW
        subq.l  #1, %d2
        bne.s   2b
        bra.s   5f
3:      mvz.b   3(%a2), %d1                     | from JOB: le32
        lsl.l   #8, %d1
        mvz.b   2(%a2), %d5
        or.l    %d5, %d1
        lsl.l   #8, %d1
        mvz.b   1(%a2), %d5
        or.l    %d5, %d1
        lsl.l   #8, %d1
        mvz.b   (%a2), %d5
        or.l    %d5, %d1
        addq.l  #4, %a2
        TDMW
        subq.l  #1, %d2
        bne.s   3b
5:      moveq   #124, %d2
        sub.l   (%sp)+, %d2
        beq.s   7f
6:      moveq   #0, %d1                         | the rest: 0
        TDMW
        subq.l  #1, %d2
        bne.s   6b
7:      movem.l (%sp), %d2-%d5/%a2
        lea     20(%sp), %sp
        rts
