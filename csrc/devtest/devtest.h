/* The test channel (docs/remote-ui.md, spec docs/remote-ui-protocol.md): SysEx commands 33..42 on the
 * sample link's channel (link.c smp_rx), a TEST BUILD only. Read-only telemetry, whitelisted runtime
 * switches, the screen's readout, and key / encoder injection (disarmed at boot). */
#ifndef DEVTEST_H
#define DEVTEST_H

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define DT_PROTO 1                              /* the test channel's protocol version (BUILDINFO) */

/* the runtime switches (whitelist.c dt_switches: name, bounds, default; the only words SWITCH writes) */
#define DT_SW_HOLD     0                        /* DRONE's HOLD latch (hold.c hold_on): 0 off, 1 on */
#define DT_SW_LABELS   1                        /* the load labels' events (meter.c icons_live): 0 off, 1 on */
#define DT_SW_ARMTIME  2                        /* seconds without a command before injection disarms */
#define DT_SW_N        3

extern volatile u32 dt_sw[DT_SW_N];

struct dt_switch { char name[8]; u32 min, max, def; };
extern const struct dt_switch dt_switches[DT_SW_N];
extern const u32 dt_peek_ranges[];              /* lo, hi pairs */
extern const u32 dt_peek_n;                     /* pairs */

#endif
