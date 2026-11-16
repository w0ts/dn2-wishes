/* When stock is busy on purpose, the CPU label stays unlit (docs/meter.md, "The CPU label while stock
 * loads or upgrades"). 2026-11-14, the User: "Disable during firmware upgrade and until loading
 * notification is gone". Two stock 1.12 states, read only (each traced in stock 1.12's code,
 * docs/meter.md; the 1.11 addresses noted below are where 1.11 has the same references, counted):
 *
 * - LOADING. Stock's view at *0x44648980 (a singleton, its weak_ptr's object; 0 until stock's UI is
 *   built) polls two worker objects' ready byte (+28) in the lambda 0x4005e28a: not ready, it counts
 *   view+504 up and at 2 posts "Loading..." on the title's message line (SAY 0x4005628c); from 3 on
 *   the view animates its loading mark (view+508 cycling 0..9, 0x4005bd70; -1 while there is none,
 *   drawn at 0x4005d5c8); ready, it zeroes view+504 and sets view+508 to -1. The message line is
 *   the singleton at *0x446488c8: its text a std::string at +72, shown while its countdown at +76 is
 *   above 0 (0x40055bac; ticked down at 0x40055b7e). Loading: the view not built yet (the boot), or
 *   view+504 not 0, or view+508 not -1, or the message line showing "Loading...". The view is held
 *   through a weak_ptr (its control block at *0x44648984, +4 the use count; the getter 0x4018ea30 builds
 *   a new view when it is 0): a view no one holds any more is not read (its memory may be reused).
 * - UPGRADING. Stock's MIDI RPC dispatcher is a static at 0x445fb5cc (built at its first message,
 *   guard 0x445fb6a8; 1.11: 0x445fa5cc); +4 is its OsUpgradeState, the only one stock makes. Its +4
 *   is the upgrade's state: 1 started (OsUpgradeStart, 0x4012989e), 2 receiving (the first
 *   OsUpgradeWrite, 0x40129f36), 3 the image received and checked, written to flash (0x4012a10a);
 *   0 none, 5 failed or cancelled. Upgrading: 1, 2 or 3. This is Transfer's route (docs/usb-upgrade-
 *   limit.md); the bootloader's OS UPGRADE runs without this OS, and no meter.
 *
 * Pure reads, no hooks: mtr_quiet_why() -> QUIET_LOADING | QUIET_UPGRADE. The host test
 * (test/test_meter_quiet.py) reads a model of that memory through QUIET_RD32. */

typedef unsigned int u32;

#include "quiet.h"

#ifndef QUIET_RD32
#define QUIET_RD32(a) (*(volatile u32 *)(a))
#endif

#define LOAD_VIEW    0x44648980u        /* the loading view's pointer (1.11: 0x44647980) */
#define LOAD_CB      0x44648984u        /* ... its weak_ptr's control block (+4: the use count) */
#define CB_USES      4u
#define MSG_LINE     0x446488C8u        /* the title's message line's pointer (1.11: 0x446478c8) */
#define RPC_STATE    0x445FB5D0u        /* the RPC dispatcher's OsUpgradeState pointer (0x445fb5cc + 4; 1.11: 0x445fa5d0) */
#define V_POLLS      504u               /* view: polls not ready in a row */
#define V_MARK       508u               /* view: the loading mark's phase, -1 none */
#define M_TEXT       72u                /* message line: its std::string (its first word: the text) */
#define M_COUNT      76u                /* message line: frames it still shows */
#define U_STATE      4u                 /* OsUpgradeState: the state */

static int ram_ok(u32 a)
{
    return a >= 0x40000000u && a < 0x48000000u && !(a & 3u);
}

static int is_loading_text(u32 t)       /* "Loading...", stock's own text (0x402161d7) */
{
    static const char want[] = "Loading...";
    if (t < 0x40000000u || t >= 0x48000000u)
        return 0;
    for (u32 k = 0; k < sizeof want; k++) {
        u32 w = QUIET_RD32((t + k) & ~3u);
        char c = (char)(w >> (24u - 8u * ((t + k) & 3u)));
        if (c != want[k])
            return 0;
    }
    return 1;
}

u32 mtr_quiet_why(void)
{
    u32 why = 0;
    u32 st = QUIET_RD32(RPC_STATE);
    if (ram_ok(st)) {
        u32 s = QUIET_RD32(st + U_STATE);
        if (s >= 1u && s <= 3u)
            why |= QUIET_UPGRADE;
    }
    u32 cb = QUIET_RD32(LOAD_CB);
    if (!ram_ok(cb)) {
        why |= QUIET_LOADING;                   /* the view never built: the boot */
    } else if ((int)QUIET_RD32(cb + CB_USES) > 0) {     /* held: its memory is the view's */
        u32 v = QUIET_RD32(LOAD_VIEW);
        if (!ram_ok(v) || QUIET_RD32(v + V_POLLS) != 0u || (int)QUIET_RD32(v + V_MARK) >= 0)
            why |= QUIET_LOADING;
    }
    u32 m = QUIET_RD32(MSG_LINE);
    if (ram_ok(m) && (int)QUIET_RD32(m + M_COUNT) > 0 && is_loading_text(QUIET_RD32(m + M_TEXT)))
        why |= QUIET_LOADING;
    return why;
}
