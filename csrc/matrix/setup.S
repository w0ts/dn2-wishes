| MOD SETUP's copies into the voices (csrc/matrix/setup.c, docs/matrix.md "MOD SETUP's rows", 2026-11-21).
|
| Stock's two copies of a sound's 153 MOD SETUP bytes into a voice's (0x4002549c: a note; 0x4002591e: an edit, every
| voice of the track) call memcpy through %a3, loaded once by `lea 0x40134770,%a3` (0x400254f0, 0x4002594c), which the
| wishes build points at its copy (wish_memcpy_stub). Those two `lea` point here: a copy of 153 bytes (MOD SETUP's) is
| copied below (a muted entry lands with depth 0), any other (0x4002549c's 202-byte parameter copy first) goes on to
| wish_memcpy_stub as before. Stock's memcpy's convention: (dst, src, n) on the stack, d0 dst on return, d0 d1 a0 a1
| scratch.

        .text
| (2026-11-21, the User's rule: the same work muted or not) the copy itself, as stock's: 8 bytes, the 24 entries, the
| 49 bytes after them, each long written once, whole (the audio interrupt never sees half of one: 0x4002591e runs in the
| UI task). An entry equal to its track's mark (mxs_mark[t][e]: {depth, slot}, 0 none) lands with depth 0: the mask
| is 0x0000ffff where they are equal, all ones where not, made without a branch (sub, neg, subx). The track is the
| source's place in the kit (src - 222 - kit - 52 = 1163 t, t < 16); any other sound (a lock's, a clipboard's) takes
| row 16, no marks. 7 instructions an entry, every copy.
        .globl  mxs_copy
mxs_copy:
        move.l  12(%sp), %d0            | n
        cmpi.l  #153, %d0
        beq.s   1f
        jmp     wish_memcpy_stub        | (any other size: stock's memcpy as before; absolute, the stub is out of a
1:      lea     -8(%sp), %sp            | 16-bit branch's reach once more of ours lies between, 2026-11-21 combined-67)
        movem.l %d2/%a2, (%sp)
        movea.l 12(%sp), %a1            | dst
        movea.l 16(%sp), %a0            | src
        move.l  %a0, %d0
        move.l  0x800052A0, %d1         | the kit
        beq.s   9f
        sub.l   %d1, %d0
        subi.l  #274, %d0               | src - 222 - kit - 52
        move.l  %d0, %d1
        move.l  #1163, %d2
        divu.l  %d2, %d1                | t (unsigned: a sound below the kit is far past 16)
        mulu.l  %d1, %d2
        cmp.l   %d0, %d2
        bne.s   9f
        moveq   #16, %d2
        cmp.l   %d2, %d1
        bcs.s   8f
9:      moveq   #16, %d1
8:      move.l  %d1, %d2                | 96 t
        lsl.l   #5, %d1
        lsl.l   #6, %d2
        add.l   %d2, %d1
        lea     mxs_mark, %a2
        adda.l  %d1, %a2
        move.l  (%a0)+, (%a1)+
        move.l  (%a0)+, (%a1)+
        .rept   24
        move.l  (%a0)+, %d0
        move.l  %d0, %d1
        sub.l   (%a2)+, %d1
        neg.l   %d1
        subx.l  %d1, %d1
        ori.l   #0xFFFF, %d1
        and.l   %d0, %d1
        move.l  %d1, (%a1)+
        .endr
        .rept   12
        move.l  (%a0)+, (%a1)+
        .endr
        move.b  (%a0), (%a1)
        addq.l  #1, mxs_copies
        move.l  12(%sp), %d0            | dst, as memcpy returns it
        movem.l (%sp), %d2/%a2
        lea     8(%sp), %sp
        rts
