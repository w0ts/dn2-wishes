/* The preset browser's ENGINE filter (2026-11-12; dnfw.waverider.engfilt, docs/engine-filter.md).
 *
 * The User: "the engine filter in preset should be like tags. no, add a separate engine filter please." So stock's
 * SORTING menu (PRESET > LOAD / SAVE / MANAGE > [LEFT]) gets a row of its own after FILTER, ENGINE (with FILTER's
 * " *" while an engine is ticked), and YES on it opens its own tick list, built as stock builds FILTER's
 * (0x400ab908): the list emptied, <CLEAR>, one row per MACHINE SEL engine, the cursor on the top row. YES on an
 * engine ticks it and moves down, as on a tag; <CLEAR> clears the engines only; NO leaves as from FILTER's list.
 * Stock's FILTER list stays stock's.
 *
 * In the list's rebuild (0x400ac9a8, hooks.S eng_test_hook) the engines ticked are a set a preset's machine must be
 * in (OR among engines), tested before stock's own MIDI test and so ANDed with the tags, MIDI, NO TAG, the bank and
 * the search. The machine comes from stock's preset index (the library's vtable +28, 0x4012d1cc: entry +32, the
 * stored sound's byte 244 as stock read it at boot or at the slot's last save; -1 for none): no +Drive read is added.
 *
 * Each row is stock's item (0x54 B, ctor 0x401173b8(item, label, action, tick, fourth, -1, 8), added with
 * 0x40116bee(menu, item)) from std::functions of stock's shape {heap closure, manager, invoker}: a closure {view}
 * with a manager that clones 4 bytes (FILTER's own), or {view, row} with stock's tag rows' manager (8 bytes). The
 * set is one mask by machine type; the view's constructor clears it with stock's filters (hooks.S eng_ctor_hook).
 */
typedef unsigned int u32;
typedef unsigned char u8;

#include "wr_gen.h"

#define D_TEXT    ((void (*)(void *, const void *, int, int, int, const char *, ...))0x4011573Cu)
#define F_LIST    0x44508EE0u               /* the font stock's tick is drawn in (0x400a91c0) */
#define TICK      ((const char *)0x40218A75u)   /* stock's tick glyph */
#define NEW       ((u32 (*)(u32))0x40120544u)   /* operator new */
#define ITEM_CTOR ((void (*)(u32, void *, void *, void *, void *, int, int))0x401173B8u)
#define MENU_ADD  ((void (*)(u32, u32))0x40116BEEu)
#define MENU_CLR  ((void (*)(u32))0x40116D10u)
#define MENU_AT   ((void (*)(u32, int, int))0x401168B8u)   /* the cursor on a row (FILTER's list: 0, 0) */
#define MENU_STEP ((void (*)(u32, int))0x40116420u)       /* the cursor a row down, as stock's tag toggle */
#define FN_DTOR   ((void (*)(void *))0x40188366u)
#define MGR4      0x400A983Cu               /* FILTER's action's manager: a 4-byte closure {view} */
#define MGR4_LBL  0x400AA154u               /* FILTER's label's manager, the same shape */
#define MGR8      0x400A9950u               /* stock's tag rows' manager: an 8-byte closure {view, row} */
#define CLEAR_LBL 0x400A8566u               /* stock's "<CLEAR>" label (0x402189b6) */
#define V_MENU    448
#define V_REBUILD 160                       /* the view's vtable: the list rebuilt from its filters */
#define LIB_MACHINE 28

struct fn { u32 store, pad, mgr, inv; };    /* a std::function: its closure's storage, manager, invoker */

u32 eng_mask __attribute__((section(".data"))) = 0;      /* bit r: the engine of row r (eng_types[r]) ticked (2026-11-18:
                                                           a bit a row, not a type: our types are 50..55) */
u32 eng_tests __attribute__((section(".data"))) = 0;     /* presets tested while a set was on (the checks read it) */
u32 eng_lists __attribute__((section(".data"))) = 0;     /* ENGINE lists opened (the checks read it) */
const int eng_n = ENG_N;

/* the invokers, in hooks.S (std::string labels return through %a0) */
extern char eng_label[], eng_title[];

/* a preset's machine through stock's index (its own lock taken inside) */
static int machine_of(u32 lib, int slot)
{
    u32 vt = *(u32 *)lib;
    return ((int (*)(u32, int))*(u32 *)(vt + LIB_MACHINE))(lib, slot);
}

static void rebuild(u32 view)
{
    ((void (*)(u32))*(u32 *)(*(u32 *)view + V_REBUILD))(view);
}

/* the rebuild's test (hooks.S eng_test_hook), only while eng_mask is set: 1 keeps the preset */
int eng_match(u32 lib, int slot)
{
    int t = machine_of(lib, slot);
    eng_tests++;
    if (t < 0)
        return 0;
    for (int r = 0; r < ENG_N; r++)
        if (eng_types[r] == t)
            return (eng_mask >> r) & 1;
    return 0;
}

/* a std::function of stock's shape: a heap closure {view} or {view, row} */
static void fn_make(struct fn *f, u32 mgr, u32 inv, u32 view, int row, int eight)
{
    u32 *c = (u32 *)NEW(eight ? 8 : 4);
    c[0] = view;
    if (eight)
        c[1] = (u32)row;
    f->store = (u32)c;
    f->pad = 0;
    f->mgr = mgr;
    f->inv = inv;
}

/* one item from up to three functions (a fourth always empty), added to the view's menu */
static void add_item(u32 view, struct fn *f)
{
    u32 item = NEW(0x54);
    int i;
    ITEM_CTOR(item, &f[0], &f[1], &f[2], &f[3], -1, 8);
    MENU_ADD(view + V_MENU, item);
    for (i = 3; i >= 0; i--)
        FN_DTOR(&f[i]);
}

static void empty(struct fn *f)
{
    f->store = f->pad = f->mgr = f->inv = 0;
}

/* the ENGINE row's text: FILTER's, "ENGINE *" while an engine is ticked */
const char *eng_title_text(void)
{
    static char t[] __attribute__((section(".data"))) = "ENGINE  ";
    t[7] = eng_mask ? '*' : ' ';
    return t;
}

/* a row's name: MACHINE SEL's, after two spaces as stock's tag rows (0x402375c3) */
const char *eng_name(int row)
{
    static const char unknown[] = "  ?";
    static char buf[16] __attribute__((section(".data")));
    const char *n;
    int i;
    if (row < 0 || row >= ENG_N)
        return unknown;
    n = msel_mname[eng_types[row]];
    buf[0] = buf[1] = ' ';
    for (i = 0; n[i] && i < 13; i++)
        buf[2 + i] = n[i];
    buf[2 + i] = 0;
    return buf;
}

/* YES on <CLEAR>: the engines cleared, the list rebuilt */
void eng_clear(u32 **fd)
{
    eng_mask = 0;
    rebuild((*fd)[0]);
}

/* YES on an engine: in or out of the set, the cursor a row down, the list rebuilt (stock's tag toggle, 0x400a936a) */
void eng_toggle(u32 **fd)
{
    u32 *c = *fd, view = c[0];
    int row = (int)c[1];
    if (row >= 0 && row < ENG_N)
        eng_mask ^= 1u << row;
    MENU_STEP(view + V_MENU, 1);
    rebuild(view);
}

/* the tick left of a ticked engine (stock's, 0x400a919c) */
void eng_tick(u32 **fd, u32 unused, void *canvas, int x, int y)
{
    int row = (int)(*fd)[1];
    (void)unused;
    if (row >= 0 && row < ENG_N && ((eng_mask >> row) & 1))
        D_TEXT(canvas, (const void *)F_LIST, x, y, 0, TICK);
}

/* YES on ENGINE: its list in the view's menu, as stock's FILTER builds its own (0x400ab908) */
void eng_list(u32 **fd)
{
    u32 view = (*fd)[0];
    struct fn f[4];
    int r;
    eng_lists++;
    MENU_CLR(view + V_MENU);
    fn_make(&f[0], MGR4_LBL, CLEAR_LBL, view, 0, 0);
    fn_make(&f[1], MGR4, (u32)eng_clear, view, 0, 0);
    empty(&f[2]);
    empty(&f[3]);
    add_item(view, f);
    for (r = 0; r < ENG_N; r++) {
        fn_make(&f[0], MGR8, (u32)eng_label, view, r, 1);
        fn_make(&f[1], MGR8, (u32)eng_toggle, view, r, 1);
        fn_make(&f[2], MGR8, (u32)eng_tick, view, r, 1);
        empty(&f[3]);
        add_item(view, f);
    }
    MENU_AT(view + V_MENU, 0, 0);
}

/* the SORTING menu's builder after FILTER (hooks.S eng_sort_hook): the ENGINE row */
void eng_sort_row(u32 view)
{
    struct fn f[4];
    fn_make(&f[0], MGR4_LBL, (u32)eng_title, view, 0, 0);
    fn_make(&f[1], MGR4, (u32)eng_list, view, 0, 0);
    empty(&f[2]);
    empty(&f[3]);
    add_item(view, f);
}
