| REMOTE CONTROL in USB CONFIG (csrc/devtest/usbcfg.c): the jmp in UsbConfigMenuView::rebuild and the label's
| invoker (a std::string returned through %a0, which C cannot say).

        .text
| rebuild 0x40104f42 at 0x40105220, its three choices added (was: movea.l (%a2),%a0 ; clr.l -(%sp) ;
| move.l %d6,-(%sp), then the cursor put back through the view's vtable slot 0x1c). %a2 the view, %d6 the cursor;
| d0, d1, a0, a1 are dead here (a0 is written next).
        .globl  dt_usb_rebuild
dt_usb_rebuild:
        move.l  %a2, -(%sp)
        jsr     dt_usb_item
        addq.l  #4, %sp
        movea.l (%a2), %a0
        clr.l   -(%sp)
        move.l  %d6, -(%sp)
        jmp     0x40105226

| the label: std::string("REMOTE CONTROL") into %a0, as stock's 0x40104782 builds "OVERBRIDGE"
        .globl  dt_usb_label
dt_usb_label:
        link.w  %fp, #-4
        move.l  %d2, -(%sp)
        pea     -1(%fp)                         | the allocator
        pea     dt_usb_name
        move.l  %a0, %d2
        move.l  %a0, -(%sp)
        jsr     0x401CEAB8                      | std::string(s, alloc)
        lea     12(%sp), %sp
        move.l  %d2, %d0
        move.l  -8(%fp), %d2
        unlk    %fp
        rts

dt_usb_name:
        .asciz  "REMOTE CONTROL"
        .align  2
