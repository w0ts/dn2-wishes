| The system meter's ColdFire timing hooks (csrc/meter/meter.c; docs/meter.md), OS 1.12.
| derived from irpina/digihealth (sysinfo.s) through dn2mk2's usbprobe (csrc/usbprobe/timing.S),
| GPL-2.0-or-later, used here under GPL-3.0 within this AGPL-3.0-or-later project.
|
| Two cumulative counters, in DMA timer 0 ticks, that mtr_update (UI task) differences
| twice a second: the time the idle task (prio 1) spends parked at its spin and the time the
| file worker (prio 2, below) runs, credited at the context switch, and the audio ISR's time
| that fell inside such an interval. CPU is
| 1 - (idle - ISR in idle) / elapsed. usbprobe measured this method on the unit (1.11,
| protocol 3, docs/usbprobe.md); every address below is stock 1.12's (byte-checked by
| coldfire.compose: the switch and ISR sites are 1.11's unchanged, BSS +0x1000).

        .equ    DTCN0,       0xfc07000c        | DMA timer 0's counter (read by the OS at ten sites)
        .equ    FRAMES,      0x4058f8d4        | audio frames since boot (1.11: 0x4058e8d4)
        .equ    CUR_TCB,     0x4664bcdc        | the running task's TCB (1.11: 0x4664acdc)
        .equ    IDLE_TCB,    0x4243d900        | the prio-1 task parked after the boot's setup (1.11: 0x4243c900)
        .equ    IDLE_PC,     0x400cf246        | its spin, bra.s * (1.11: 0x400cf0e2)
| 2026-11-17 (the User's DN2, v0.57.1: "!CPU" while a new project is made and loaded): stock's file worker, the one
| task at prio 2 (its TCB's +8 is its ready-table slot, 0x4664bc9c + 4 * prio; read on the unit: TCB 0x42c6a1d0,
| made at run time), runs a project's LOAD, its working-copy write after it, INIT NEW and SAVE. It runs only when
| every task above it waits, so its time is time nobody else wanted: counted as idle, like the idle task's spin
| (the audio ISR inside it still counts as load). Measured on the unit: a LOAD is 100 % for ~17 s with it counted
| as load, 18 % of it the worker's.
        .equ    WORKER_SLOT, 0x4664bca4        | the prio-2 slot of the ready table (1.11: 0x4664aca4)
| The counters live in RAM above BSS, in the meter's own block (METER_RAM, declared by
| dnfw.mods.waverider.ram; offsets as meter.c's MTR_* ), never in the code chunk: they change
| at every context switch, and the engine gate holds every CODE chunk to its image.
        .equ    mtr_t_in,     METER_RAM + 4
        .equ    mtr_isr_idle, METER_RAM + 8
        .equ    mtr_idle,     METER_RAM + 12
        .equ    mtr_i_on,     METER_RAM + 16
        .equ    mtr_i_start,  METER_RAM + 20
        .equ    mtr_switches, METER_RAM + 24

        .text
        .globl  mtr_isr_out
        .globl  mtr_t_in
        .globl  mtr_switch

| The ISR's start time, mtr_t_in, is taken in the sample link's hook at 0x40026098
| (csrc/sampler/hooks.S smp_tdm_hook), the one patch the ISR carries before here: its
| instructions from the entry 0x40025e36 up to that hook are Overbridge's audio path, which
| the build never touches (scripts/gate_overbridge.py). So the ISR time counted is from the
| link hook to the frame count; the entry, register save and transmit fills before it are
| counted as idle when they interrupt the idle task (the CPU figure reads low by their share,
| unmeasured).

| The audio ISR at 0x40027b82 (was: addq.l #1,FRAMES), before its only rte: d0 and d1
| are dead (the next instruction loads d0; d1 is written before it is read). mtr_t_in is
| taken and cleared once a frame, so an exit with no link hook before it (none is known:
| every transmit mode ends at the hook, docs/link-research.md 6c) adds nothing.
mtr_isr_out:
        addq.l  #1, FRAMES              | the instruction this replaced
        move.l  mtr_t_in, %d1
        beq.s   9f                      | no start this frame
        clr.l   mtr_t_in
        move.l  DTCN0, %d0
        sub.l   %d1, %d0                | this frame's ticks from the link hook
        tst.l   mtr_i_on
        beq.s   9f                      | not inside an idle (or worker) interval
        add.l   %d0, mtr_isr_idle       | ISR time inside an idle interval
9:      rts

| The context switch at 0x40000438 (was: move.l #0xffffdfff,%d0). Interrupts are masked;
| a0 is the incoming TCB, a1 and d1 are live, d2-d7/a2-a5 are about to be reloaded from
| the incoming TCB, so they are free. 8(sp) is the outgoing task's resume PC.
mtr_switch:
        addq.l  #1, mtr_switches        | the scheduler is alive
        move.l  DTCN0, %d2
        tst.l   mtr_i_on
        beq.s   1f                      | the outgoing task opened no interval
        move.l  CUR_TCB, %d3            | the outgoing task
        cmpi.l  #IDLE_TCB, %d3
        bne.s   3f                      | the worker: all its time
        move.l  8(%sp), %d4
        cmpi.l  #IDLE_PC, %d4           | the idle task: only time parked at the spin
        bne.s   1f
3:      move.l  %d2, %d4
        sub.l   mtr_i_start, %d4
        add.l   %d4, mtr_idle
1:      clr.l   mtr_i_on
        cmpa.l  #IDLE_TCB, %a0
        beq.s   4f
        move.l  8(%a0), %d4             | the incoming task's ready slot: its priority
        cmpi.l  #WORKER_SLOT, %d4
        bne.s   2f
4:      move.l  %d2, mtr_i_start        | idle or the worker switched in: an interval opens
        moveq   #1, %d2
        move.l  %d2, mtr_i_on
2:      move.l  #0xffffdfff, %d0        | the instruction this replaced
        rts

