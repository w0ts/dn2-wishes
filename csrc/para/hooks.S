| PARA on the VOICE menu (csrc/para/vmenu.c). 0x400285c0, in VoiceMenuView's draw, pushes place B's "---"
| (was: pea 0x402108e1, 6 bytes; now jsr here). The same pointer is left on the stack as the pea left it, and
| vm_seen says the menu was drawn this frame. No register changes (d0 saved and restored); the condition codes
| are not read after the pea (the next instruction, clr.l -(sp), sets them).
        .text
        .globl  vm_seen_hook
vm_seen_hook:
        move.l  %d0, -(%sp)                     | [d0][ret]
        moveq   #1, %d0
        move.l  %d0, vm_seen
        addq.l  #1, vm_hooks                    | (the emulator counts VoiceMenuView's draws)
        move.l  4(%sp), %d0                     | the return address
        move.l  %d0, -(%sp)                     | [ret][d0][ret]
        move.l  #0x402108e1, %d0                | the "---" the pea pushed
        move.l  %d0, 8(%sp)                     | [ret][d0]["---"]
        move.l  4(%sp), %d0                     | d0 back
        move.l  (%sp), 4(%sp)                   | [ret][ret]["---"]
        addq.l  #4, %sp                         | [ret]["---"]
        rts                                     | -> ["---"], as after the pea
