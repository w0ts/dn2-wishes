/* THE WHITELIST: the only words the test channel may write (SWITCH) and the only ranges it may read
 * (PEEK). Nothing else in devtest.c takes an address from the host. Audit this file.
 *
 * Switches are RAM words the firmware reads at run time; a write is bounded to [min, max] and logged in
 * the trace. The DSP's skip switches (FDN8 QUIET_GATE, the A2 quiet skip, the chain skip, the inserts'
 * deadline guard, ONE_VOICE, CLEAR_SPREAD) are compile-time in the SHARC code: making them run-time
 * words would put a test on the audio path, so they stay build switches (the A/B is two builds). */
#include "devtest.h"

const struct dt_switch dt_switches[DT_SW_N] = {
    [DT_SW_HOLD]    = {"HOLD",    0, 1, 1},     /* DRONE's HOLD latch: off = every HOLD track plays as HOLD OFF */
    [DT_SW_LABELS]  = {"LABELS",  0, 1, 1},     /* the load labels: off = no events (forced ones still show) */
    [DT_SW_ARMTIME] = {"ARMTIME", 30, 1800, 300},   /* injection auto-disarms this many seconds after the last command */
};
/* the words themselves, at their defaults (the same as .def above: test_devtest checks it) */
volatile u32 dt_sw[DT_SW_N] __attribute__((section(".data"))) = {1, 1, 300};

/* PEEK reads (at most 128 bytes a request) only inside these: the DDR the firmware runs in (code, data,
 * BSS: the screen buffers, the panel state, our RAM) and the SRAM's first 64 KB (the frame, the
 * parameter mirrors). The same ranges the read-only USB probe read on the unit (tools/dn2probe.py), and since
 * remoteui-4 the TDM receive window (the probe read 1.11's, 0x4E6DF100; 1.12's is +0x8000). */
const u32 dt_peek_ranges[] = {                 /* lo, hi pairs (walked by pointer, devtest.c) */
    0x40000000u, 0x48000000u,
    0x80000000u, 0x80010000u,
    0x4E6E7100u, 0x4E6E8100u,                   /* the TDM receive window's two halves (eDMA ch 48, OS 1.12; link.c TDM_RX): read only */
};
const u32 dt_peek_n = sizeof dt_peek_ranges / sizeof dt_peek_ranges[0] / 2u;
