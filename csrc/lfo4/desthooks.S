/* `lfo4-dest`'s two stubs: the gate the browser opens behind, and its mask.
 *
 * Its own file, for the reason `valuehooks.S` states -- an assembly file is
 * linked whole, so a stub placed beside others is compiled into every build
 * that has no interest in the site it patches.
 *
 * Six sites in the image compare an entry against 78, 88 and 98, and five
 * choose a capability mask from bits 18, 17 and 16. `emu_lfo4_dest.py` opened
 * the browser on all four MOD pages and found that **one** of each runs. These
 * are that one of each.
 */
#include "dn2_111.h"
#include "slots.h"

/* The last of the three compares, and a fourth behind it.
 *
 * The gate is woven through the prologue -- `moveq #78,%d1` is the function's
 * second instruction, before the arguments are loaded -- so the twenty-two
 * bytes are not contiguous and cannot be replaced as one. They do not need to
 * be: 78 and 88 are tested and taken before this point, and what is left is
 * `moveb #98,%d1 ; cmpl %d0,%d1 ; bne`, eight bytes with both exits in them.
 *
 * `%d0` holds the entry. `%d1` is the stock code's scratch and is dead on both
 * exits -- the accept path's first instruction is `movel %d0,%d1`, and the
 * decline path never reads it -- so this stub need preserve neither.
 */
    .globl  lfo4_dest_stub
lfo4_dest_stub:
    cmp.l   #98,%d0
    beq.s   lfo4_dest_yes
    cmp.l   #LFO4_E_DEST,%d0
    beq.s   lfo4_dest_yes
    jmp     DN2_DEST_DECLINE
lfo4_dest_yes:
    jmp     DN2_DEST_ACCEPT

/* The mask cascade, transcribed with a fourth step.
 *
 * The firmware's is thirty-four bytes and every branch converges on
 * `DN2_DEST_MASK_AFTER`, so the whole of it is replaced rather than hooked.
 * The first three steps are its own, instruction for instruction, including
 * the `movew` that writes only the low half of a `%d0` the `movel` above it
 * has already cleared.
 *
 * The fourth is the staircase's own next step: bit 15 of the record's `+44`,
 * which is what `lfo4records.DEST_FLAGS` writes, selecting `0x0200`, which is
 * the mask that admits LFO3's eight records on top of everything LFO3 itself
 * may target. Nothing in the shipping firmware ever passes it.
 *
 * `%d1` holds the flags and is not written here. `%d0` is the answer.
 */
    .globl  lfo4_dest_mask
lfo4_dest_mask:
    move.l  #0x1e00,%d0
    btst    #18,%d1
    bne.s   lfo4_dest_mask_done
    move.w  #0x0e00,%d0
    btst    #17,%d1
    bne.s   lfo4_dest_mask_done
    move.w  #0x0600,%d0
    btst    #16,%d1
    bne.s   lfo4_dest_mask_done
    move.w  #DN2_DEST_MASK4,%d0
    btst    #DN2_DEST_FLAG_BIT,%d1
    bne.s   lfo4_dest_mask_done
    clr.l   %d0
lfo4_dest_mask_done:
    jmp     DN2_DEST_MASK_AFTER

/* The DEST list opener's own cascade, with the same fourth step (2026-11-17).
 *
 * Measured (emu_dest_probe, build 49df7194): of stock's eight 18/17/16 cascades only the one at 0x400672FE runs
 * when the DEST list opens, with the record's flags in %d0 (LFO1 0x40000, LFO4 0x8000). lfo4 relocated its table
 * read but left the cascade three steps long, so LFO4's 0x8000 set no mask: the list opened unfiltered, with no
 * MODn header and its highlight not on the value (the User's DN2, v0.57.1). Its forty-eight bytes are replaced
 * and every branch converges on DN2_LIST_MASK_AFTER. The three steps are stock's, register for register (%a1,
 * %d0, %a0 written as stock writes them); the fourth is the staircase's next: bit 15 -> 0x0200 into -28(%fp),
 * through %a0 as the 0x0600 step does (%a0 is dead there: the next call clobbers it).
 */
    .globl  lfo4_list_mask
lfo4_list_mask:
    btst    #18,%d0
    beq.s   1f
    movea.w #0x1e00,%a1
    move.l  %a1,-28(%fp)
    jmp     DN2_LIST_MASK_AFTER
1:  btst    #17,%d0
    beq.s   2f
    move.l  #0x0e00,%d0
    move.l  %d0,-28(%fp)
    jmp     DN2_LIST_MASK_AFTER
2:  btst    #16,%d0
    beq.s   3f
    movea.w #0x0600,%a0
    move.l  %a0,-28(%fp)
    jmp     DN2_LIST_MASK_AFTER
3:  btst    #DN2_DEST_FLAG_BIT,%d0
    beq.s   4f
    movea.w #DN2_DEST_MASK4,%a0
    move.l  %a0,-28(%fp)
4:  jmp     DN2_LIST_MASK_AFTER

/* The DEST list's header, with a fourth group name (2026-11-18).
 *
 * The header (0x40106CDC..) names the list's group from its mask (a2@(224)): 0x1e00 "MOD1", 0x0e00 "MOD2", 0x0600
 * "MOD3", anything else its own label (a2@(228)). With lfo4_list_mask LFO4's list carries 0x0200, so this adds
 * "MOD4". It replaces `cmpil #0x600,%d0 ; bne` (8 bytes at 0x40106CF0): 0x0600 goes on to stock's MOD3 case, 0x0200
 * does what that case does with "MOD4" (the separator appended through %a4, then the name pushed for the join),
 * anything else goes to stock's last case. %d0 holds the mask; the registers are stock's on every exit.
 */
    .globl  lfo4_hdr_stub
lfo4_hdr_stub:
    cmp.l   #0x0600,%d0
    bne.s   1f
    jmp     DN2_HDR_MOD3
1:  cmp.l   #DN2_DEST_MASK4,%d0
    bne.s   2f
    pea     DN2_HDR_SEP
    move.l  %d3,-(%sp)
    jsr     %a4@
    pea     lfo4_mod4_name
    jmp     DN2_HDR_JOIN
2:  jmp     DN2_HDR_OTHER

    .section .rodata
    .globl  lfo4_mod4_name
lfo4_mod4_name:
    .asciz  "MOD4"
    .text
