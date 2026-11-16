/* The preset browser's ENGINE filter (2026-11-12; dnfw.waverider.engfilt, docs/engine-filter.md).
 *
 * Stock's FILTER list (PRESET > LOAD / MANAGE > [LEFT] > FILTER) is <CLEAR>, the 32 tags, MIDI and NO TAG, each a
 * tick row. Tags combine with AND (0x400ac914); MIDI keeps the presets whose machine is MIDI (0x400ac9a8, after the
 * bank). Here one tick row per MACHINE SEL engine joins them, after the tags and before MIDI (hooks.S eng_rows_hook):
 * the engines ticked, MIDI with them when it is ticked, are a set a preset's machine must be in (OR among engines,
 * AND with the tags, the bank and the search). <CLEAR> clears them, FILTER's "*" counts them.
 *
 * The machine comes from stock's own preset index (the library's vtable +28, 0x4012d1cc: entry +32, the stored
 * sound's byte 244 as stock read it at boot or at the slot's last save; -1 for none), so no +Drive read is added.
 * Measured in the 1.12 emulator: lib entry 0 HIDDEN TEARS 0, BD AYE 1, BD NOISPUMP 2, SYNTHVAG 3.
 *
 * The rows' std::functions are stock's shape for its tag rows (0x400ab9f2): an 8-byte closure {view, row} on the
 * heap, stock's manager for it (0x400a9950), these invokers. The set is one mask by machine type, for the session
 * (stock rebuilds the view, and clears its own filters, in its constructor: hooks.S eng_ctor_hook clears it there).
 */
typedef unsigned int u32;
typedef unsigned char u8;

#include "wr_gen.h"

#define D_TEXT    ((void (*)(void *, const void *, int, int, int, const char *, ...))0x4011573Cu)
#define F_LIST    0x44508EE0u               /* the font stock's tick is drawn in (0x400a91c0) */
#define TICK      ((const char *)0x40218A75u)   /* stock's tick glyph */
#define MENU_STEP ((void (*)(u32, int))0x40116420u)  /* the cursor a row down, as stock's tag toggle (0x400a938c) */
#define V_MIDI    1413
#define V_MENU    448
#define V_REBUILD 160                       /* the view's vtable: the list rebuilt from its filters */
#define LIB_MACHINE 28
#define MIDI      4

u32 eng_mask __attribute__((section(".data"))) = 0;      /* bit t: machine type t ticked */
u32 eng_tests __attribute__((section(".data"))) = 0;     /* presets tested while a set was on (the checks read it) */
const int eng_n = ENG_N;                                  /* the rows hooks.S makes */

/* a preset's machine through stock's index (its own lock taken inside) */
static int machine_of(u32 lib, int slot)
{
    u32 vt = *(u32 *)lib;
    return ((int (*)(u32, int))*(u32 *)(vt + LIB_MACHINE))(lib, slot);
}

/* the rebuild's test (hooks.S eng_test_hook), only while eng_mask is set: 1 keeps the preset */
int eng_match(u32 lib, int slot, u32 view)
{
    u32 set = eng_mask | (*(u8 *)(view + V_MIDI) ? 1u << MIDI : 0);
    int t = machine_of(lib, slot);
    eng_tests++;
    return t >= 0 && t < 32 && ((set >> t) & 1);
}

/* the row's name, for the label invoker (hooks.S eng_label): MACHINE SEL's */
const char *eng_name(int row)
{
    static const char unknown[] = "  ?";
    static char buf[16] __attribute__((section(".data")));
    const char *n;
    int i;
    if (row < 0 || row >= ENG_N)
        return unknown;
    n = msel_mname[eng_types[row]];
    buf[0] = buf[1] = ' ';                  /* stock's tag rows: two spaces, then the name (0x402375c3) */
    for (i = 0; n[i] && i < 13; i++)
        buf[2 + i] = n[i];
    buf[2 + i] = 0;
    return buf;
}

/* YES on a row: its engine in or out of the set, the cursor a row down, the list rebuilt (stock's tag toggle,
 * 0x400a936a) */
void eng_toggle(u32 **fd)
{
    u32 *c = *fd, view = c[0];
    int row = (int)c[1];
    if (row >= 0 && row < ENG_N)
        eng_mask ^= 1u << eng_types[row];
    MENU_STEP(view + V_MENU, 1);
    ((void (*)(u32))*(u32 *)(*(u32 *)view + V_REBUILD))(view);
}

/* the tick left of a ticked row (stock's, 0x400a919c) */
void eng_tick(u32 **fd, u32 unused, void *canvas, int x, int y)
{
    int row = (int)(*fd)[1];
    (void)unused;
    if (row >= 0 && row < ENG_N && ((eng_mask >> eng_types[row]) & 1))
        D_TEXT(canvas, (const void *)F_LIST, x, y, 0, TICK);
}
