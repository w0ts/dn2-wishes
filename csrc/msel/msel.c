/* MACHINE SEL in two columns (2026-11-11, the User's design E: scratch/lists/E1..E3, approved with continuous
 * lines between the groups).
 *
 * Stock's MachineListView (vtable 0x401dfde8, constructor 0x4005b56e) stays as it is: its rows, its cursor,
 * UP / DOWN / YES / NO / LEFT / RIGHT. Measured in the 1.12 emulator: the view's +420 is the cursor's row
 * (dividers counted), +424 the page (0 the machines, 1 the filter machines), +412 the track's machine type,
 * +416 its filter type. When the screen is drawn (page.c wr_screen, after stock) this draws over everything
 * under the title bar: two columns of six cells over the full width, each a 7 x 5 icon and a name of up to
 * 12 characters in the list's own font (VAL, the record stock draws MACHINE SEL's rows with), the screen of
 * twelve that holds the cursor (cells never change column), the selected cell inverted, the track's machine
 * a dot left of its icon, a continuous line where stock puts its dotted divider, the scrollbar and, under it,
 * the two pages' dots. The rows and names are dnfw.waverider.msel's (wr_gen.h), made from the same lists
 * stock's view is given; the emulator test holds them to stock's.
 *
 * FUNC + SYN (SRC) while it is up: stock closes MACHINE SEL; here it switches the page instead, by handing
 * stock its own RIGHT (to the filters) or LEFT (back), FUNC's bit taken off (msel_key, from rec.c smp_ui_pop).
 *
 * FUNC + turn G on the FLTR page (2026-11-11, the User: "we could switch filter one type with FUNCT + G (with list
 * popup)", "FUNC + turn G opens the list"): the filter types in a list (popup.c wpop_modal), FILTER SEL's rows and
 * names, the track's own lit. The first turn opens it, each further turn moves it (stopping at the ends); FUNC let
 * go, YES or G pushed picks, NO or any other key or knob leaves the type as it was. The pick is what MACHINE SEL's
 * filter page does on YES (0x4005bbbe): the stock commit, only when the type changes. It replaces stock's FUNC + turn
 * on G of the FLTR page only (flt_pop, from rec.c smp_ui_pop); FUNC + push G is stock's while the list is shut.
 */
typedef unsigned int u32;
typedef unsigned char u8;

#include "wr_gen.h"

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define D_TEXT    ((void (*)(void *, const void *, int, int, int, const char *, ...))0x4011573Cu)   /* align 8: inverted */
#define D_BADGE   ((void (*)(void *, int, int, int, int, int))0x40114C34u)  /* -1: inverts */
#define FONT_VT   0x402069DCu
#define FR_VAL    0x40294710u                   /* the list's font (3 x 5), MACHINE SEL's own */
#define F_TITLE   0x44508EF8u                   /* the font object stock's MACHINE SEL title is drawn with */
/* stock's track number for the title (0x4005b7f0): the current track's object, its index */
#define TRK_CUR   ((u32 (*)(void))0x4018AC5Au)
#define TRK_OBJ   ((u32 (*)(u32))0x4003E40Eu)
#define TRK_INDEX ((int (*)(u32))0x40046BFEu)
#define MSEL_VTABLE 0x401DFDE8u
#define V_CURSOR  420
#define V_PAGE    424
#define V_TYPE    412
#define V_FILTER  416
#define K_SRC     2
#define K_UP      11
#define K_LEFT    13
#define K_DOWN    14
#define K_RIGHT   15
#define F_FUNC    0x02                          /* an item's flag while FUNC is held (rec.c) */
/* the FLTR page's view class, measured in the 1.12 emulator (2026-11-11, the screen's view list on [FLTR];
 * SYN's is 0x401D4DB0, AMP's 0x401E2320) */
#define FLTR_VTABLE 0x401E24C4u
/* MACHINE SEL's model (the view's +132) is the UI owner's +0xF4 (rec.c smp_assign); its filter page reads the type
 * with getFilterType(model, track) and commits with (model, track, type, 1, 1), measured in the 1.12 image */
#define FILTER_GET    ((int (*)(u32, int))0x400313A6u)
#define FILTER_COMMIT ((u32 (*)(u32, int, int, int, int))0x40031A56u)
#define IT_KEY    0
#define IT_KNOB   1
#define K_YES     10
#define K_NO      12
#define K_FUNC    17
#define KNOB_G    7
#define K_PUSH_G  47                            /* encoder G pushed (K_ENC_A + 6) */
#define K_TRIG1   25                            /* the sixteen [TRIG] keys: 25..40 (rec.c) */

#define ROWS      6                             /* a column's cells */
#define CELLS     (2 * ROWS)                    /* a screen */
#define COLW      61
#define X0        2
#define TOP       12                            /* the first row's glyph top, from the screen's top */
#define H         64

static const u32 F_LIST[2] = {FONT_VT, FR_VAL};

extern u32 ins_view_of(u32 cls);                /* csrc/inserts/ins.c: the screen's view of a class */
extern int smp_func_held;                       /* rec.c */

static u32 view(void)
{
    return ins_view_of(MSEL_VTABLE);
}

int msel_visible(void)
{
    return view() != 0;
}

static void px(void *c, int x, int y, int on)   /* y from the top, as the mock-ups */
{
    if (x >= 0 && x < 128 && y >= 0 && y < H)
        SET_PIXEL(c, x, H - 1 - y, on);
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int y = y0; y <= y1; y++)
        for (int x = x0; x <= x1; x++)
            px(c, x, y, on);
}

static void cell(void *c, int k, int type, int filters, int sel, int cur)
{
    int x = X0 + (k / ROWS) * COLW, y = TOP + 8 * (k % ROWS);
    if (type < 0) {                             /* a group's divider: one continuous line */
        fill(c, x + 1, y + 2, x + COLW - 4, y + 2, 1);
        return;
    }
    const char *name = filters ? msel_fname[type] : msel_mname[type];
    const u8 *icon = filters ? msel_ficon[type] : msel_micon[type];
    if (sel) {                                  /* the selection: an inverted bar, its corners round */
        fill(c, x - 1, y - 2, x + COLW - 3, y + 5, 1);
        px(c, x - 1, y - 2, 0);
        px(c, x + COLW - 3, y - 2, 0);
        px(c, x - 1, y + 5, 0);
        px(c, x + COLW - 3, y + 5, 0);
    }
    for (int r = 0; r < 5; r++)
        for (int i = 0; i < 7; i++)
            if (icon[r] >> (6 - i) & 1)
                px(c, x + 1 + i, y + r, !sel);
    if (name)
        D_TEXT(c, F_LIST, x + 10, H - 1 - (y + 4), sel ? 8 : 0, "%s", name);
    if (cur) {                                  /* the track's own: a dot left of its icon (selected: a notch) */
        px(c, x - 1, y + 2, !sel);
        if (sel)
            px(c, x, y + 2, 0);
    }
}

void msel_draw(void *c)
{
    u32 v = view();
    if (!v)
        return;
    int page = *(volatile int *)(v + V_PAGE) ? 1 : 0;
    int n = page ? MSEL_FROWS : MSEL_MROWS;
    const signed char *rows = page ? msel_frows : msel_mrows;
    int at = *(volatile int *)(v + V_CURSOR);
    int mine = *(volatile int *)(v + (page ? V_FILTER : V_TYPE));
    if (at < 0 || at >= n)
        at = 0;
    int first = at / CELLS * CELLS;
    fill(c, 0, 7, 127, H - 1, 0);               /* stock's picture, < SYN >, its rows, its scrollbar */
    if (page) {                                 /* the filter page's own title, drawn as stock draws its (0x4005b7d4) */
        fill(c, 0, 0, 127, 6, 0);
        D_TEXT(c, (const void *)F_TITLE, 62, 58, 2, "FILTER SEL \x9b TRACK %d", TRK_INDEX(TRK_OBJ(TRK_CUR())) + 1);
        D_BADGE(c, 0, 57, 127, 63, -1);
    }
    for (int k = 0; k < CELLS && first + k < n; k++) {
        int type = rows[first + k];
        cell(c, k, type, page, first + k == at, type >= 0 && type == mine);
    }
    /* the scrollbar (x 124..127, y 12..47) */
    int t0 = 12, t1 = 47, len = t1 - t0 + 1;
    fill(c, 124, t0, 124, t1, 1);
    fill(c, 127, t0, 127, t1, 1);
    int a = t0 + len * first / n, b = t0 + len * (first + CELLS < n ? first + CELLS : n) / n - 1;
    fill(c, 125, a, 126, b, 1);
    /* the pages' dots under it: the machines, the filters (filled: this one) */
    for (int p = 0; p < 2; p++) {
        int y = 52 + 6 * p;
        if (p == page)
            fill(c, 124, y, 127, y + 3, 1);
        else
            fill(c, 125, y + 1, 126, y + 2, 1);
    }
}

static void ls_key(u32 code);                   /* LIVE SELECT (below) */

/* from rec.c smp_ui_pop, every key item: FUNC + SYN while MACHINE SEL is up becomes stock's RIGHT / LEFT
 * (its own page switch), the press and its release; -> 1 when the item was changed (its code at it[7]) */
int msel_key(u8 *it, u32 code, int down)
{
    static int took __attribute__((section(".data"))) = 0;
    if (down && (code == K_YES || code == K_NO))
        ls_key(code);                           /* LIVE SELECT: then stock's YES / NO as ever */
    if (code != K_SRC)
        return 0;
    u32 v = view();
    if (down && smp_func_held && v) {
        took = *(volatile int *)(v + V_PAGE) ? K_LEFT : K_RIGHT;
    } else if (down || !took)
        return 0;
    it[4] = it[5] = it[6] = 0;
    it[7] = (u8)took;
    it[11] &= (u8)~F_FUNC;
    if (!down)
        took = 0;
    return 1;
}

/* LIVE SELECT (2026-11-12, the User: "preview/load the engine on the arrows, confirm and exit on YES, discard and
 * revert on NO"; a PERSONALIZE row, csrc/msel/live.c, default on). While it is on, in MACHINE SEL (both pages) and in
 * the FUNC + G filter list: the machine (filter) under the cursor is committed once the cursor has rested REST_MS
 * (as stock's YES commits it: 0x4005bb7e, 0x4005bbbe); YES commits what is still pending, then stock's YES closes
 * (the cursor's type is the track's by then); NO puts the type it had at the opening back through the same commit and
 * then the track's whole sound as it was, byte for byte (a commit resets the machine's or filter's parameters to their
 * defaults: measured in the 1.12 emulator, sound +70..+128), and stock's NO closes. Off: stock's YES and NO. */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define SOUND_AT    52                          /* a track's sound: kit + 52 + 1163 t */
#define SOUND_LEN   1163
#define TICK        (*(volatile u32 *)0x466768B0u)   /* the panel module's tick, 0..4095: 120.0 a second on the unit
                                                      (measured 2026-11-14 on r5, docs/live-select.md) */
#define TICK_MASK   0xFFFu
#define TICK_HZ     120                         /* the tick's rate on the unit (docs/live-select.md) */
#define REST_MS     250                         /* the cursor rests this long before its machine is committed */
#define REST        ((REST_MS * TICK_HZ + 500) / 1000)   /* in ticks: 30, 250 ms (150 until now: 1.25 s) */
#define MACHINE_COMMIT ((u32 (*)(u32, int, int, int, int))0x40031880u)
extern u32 smp_machine_commit(u32 model, u32 track, u32 type, u32 a, u32 b);   /* csrc/sampler/rec.c */
#define TYPE_AT     ((int (*)(u32))0x4005B162u) /* the type under MACHINE SEL's cursor (stock's YES reads it) */
#define V_TRACK     128
#define V_MODEL     132

extern int live_on(void);                       /* live.c */

static u8 ls_sound[SOUND_LEN] __attribute__((section(".data")));
static u8 *ls_at __attribute__((section(".data"))) = 0;     /* the saved track's sound (0: none saved) */
static int ls_type __attribute__((section(".data"))) = 0;    /* its machine and filter when saved */
static int ls_filter __attribute__((section(".data"))) = 0;
static int ls_track __attribute__((section(".data"))) = 0;
static u32 ls_v __attribute__((section(".data"))) = 0;       /* the MACHINE SEL view seen open */
static int ls_page __attribute__((section(".data"))) = 0, ls_cur __attribute__((section(".data"))) = 0;
static int ls_due __attribute__((section(".data"))) = 0;     /* a commit waiting for the rest */
static u32 ls_when __attribute__((section(".data"))) = 0;
static u32 ls_mono __attribute__((section(".data"))) = 0, ls_tick __attribute__((section(".data"))) = 0;
u32 ls_commits __attribute__((section(".data"))) = 0;        /* the checks read these */
u32 ls_reverts __attribute__((section(".data"))) = 0;

static u32 ls_now(void)                         /* the tick, unwrapped (every UI pass reads it) */
{
    u32 t = TICK;
    ls_mono += (t - ls_tick) & TICK_MASK;
    ls_tick = t;
    return ls_mono;
}

static void ls_copy(u8 *to, const u8 *from)
{
    for (int i = 0; i < SOUND_LEN; i++)
        to[i] = from[i];
}

static u8 *ls_sound_of(int track)
{
    return KIT_POINTER + SOUND_AT + SOUND_LEN * track;
}

/* the track's sound and types, as the list opens */
static void ls_save(int track, u32 model)
{
    ls_track = track;
    ls_at = ls_sound_of(track);
    ls_copy(ls_sound, ls_at);
    ls_type = ls_at[0xDE];
    ls_filter = FILTER_GET(model, track);
    ls_due = 0;
}

/* NO: the types back through stock's commits, then the sound as it was */
static void ls_revert(u32 model, u32 view)
{
    ls_due = 0;
    if (!ls_at || ls_at != ls_sound_of(ls_track))     /* no save, or another kit since: leave it */
        return;
    if (ls_at[0xDE] != ls_type) {
        if (view)
            *(volatile int *)(view + V_TYPE) = ls_type;
        MACHINE_COMMIT(model, ls_track, ls_type, 1, 1);
    }
    if (FILTER_GET(model, ls_track) != ls_filter) {
        if (view)
            *(volatile int *)(view + V_FILTER) = ls_filter;
        FILTER_COMMIT(model, ls_track, ls_filter, 1, 1);
    }
    ls_copy(ls_at, ls_sound);
    ls_reverts++;
}

/* MACHINE SEL: the cursor's type committed as stock's YES commits it (the view's own record first) */
static void ls_commit(u32 v)
{
    u32 model = *(volatile u32 *)(v + V_MODEL);
    int track = TRK_INDEX(*(volatile u32 *)(v + V_TRACK));
    int t = TYPE_AT(v);
    ls_due = 0;
    if (t < 0)
        return;
    if (*(volatile int *)(v + V_PAGE)) {
        if (t != *(volatile int *)(v + V_FILTER)) {
            *(volatile int *)(v + V_FILTER) = t;
            FILTER_COMMIT(model, track, t, 1, 1);
            ls_commits++;
        }
    } else if (t != *(volatile int *)(v + V_TYPE)) {
        *(volatile int *)(v + V_TYPE) = t;
        smp_machine_commit(model, (u32)track, (u32)t, 1, 1);   /* (our wrapper of stock's: a sample kept, LEN, a
                                         * Monomachine machine's own start values; 2026-11-12, found by mnmdefaults) */
        *(volatile int *)(v + V_FILTER) = FILTER_GET(model, track);
        ls_commits++;
    }
}

static void fp_poll(void);

/* page.c wr_poll, every UI pass */
void msel_poll(void)
{
    u32 now = ls_now();
    fp_poll();
    u32 v = view();
    if (!v) {
        ls_v = 0;
        return;
    }
    int page = *(volatile int *)(v + V_PAGE), cur = *(volatile int *)(v + V_CURSOR);
    if (v != ls_v) {                            /* opened: the sound saved, whatever the setting */
        ls_v = v;
        ls_page = page;
        ls_cur = cur;
        ls_save(TRK_INDEX(*(volatile u32 *)(v + V_TRACK)), *(volatile u32 *)(v + V_MODEL));
        return;
    }
    if (page != ls_page) {                      /* the other page: its cursor is the track's own */
        ls_page = page;
        ls_cur = cur;
        ls_due = 0;
    } else if (cur != ls_cur) {
        ls_cur = cur;
        ls_due = live_on();
        ls_when = now + REST;
    }
    if (ls_due && (int)(now - ls_when) >= 0)
        ls_commit(v);
}

/* from rec.c smp_ui_pop through msel_key: YES and NO while MACHINE SEL is up, before stock has them */
static void ls_key(u32 code)
{
    u32 v = view();
    if (!v || !live_on() || v != ls_v)
        return;
    if (code == K_YES && ls_due)
        ls_commit(v);
    else if (code == K_NO)
        ls_revert(*(volatile u32 *)(v + V_MODEL), v);
}

/* FUNC + turn G on the FLTR page: the filter type's list */
extern void wpop_modal(const char *label, int n, int cur, const char *(*name)(int, int), int arg);
extern int smp_fb_open, smp_lst_open;           /* the folder browser, the sample list (over the page) */

static int fp_open __attribute__((section(".data"))) = 0;
static int fp_at __attribute__((section(".data"))) = 0;      /* the lit row of msel_frows */
static int fp_was __attribute__((section(".data"))) = 0;     /* the track's type when it opened */
static u32 fp_eat __attribute__((section(".data"))) = 0;     /* YES, NO, G pushed: taken, their repeats and release too */

static const char *fp_name(int i, int arg)
{
    (void)arg;
    return msel_fname[msel_frows[i]];
}

static int fp_track(void)
{
    return TRK_INDEX(TRK_OBJ(TRK_CUR()));
}

static u32 fp_model(void)
{
    return TRK_CUR() + 0xF4u;
}

static int fp_due __attribute__((section(".data"))) = 0;      /* LIVE SELECT: a commit waiting for the rest */
static u32 fp_when __attribute__((section(".data"))) = 0;

/* the lit row's type committed, if it is not the track's already */
static void fp_commit(void)
{
    int type = msel_frows[fp_at];
    fp_due = 0;
    if (type != FILTER_GET(fp_model(), fp_track())) {
        FILTER_COMMIT(fp_model(), fp_track(), type, 1, 1);
        ls_commits++;
    }
}

/* PICK: YES, G pushed, FUNC let go (the lit type); DISCARD: NO; OTHER: another key or knob (stock: as it was;
 * LIVE SELECT: what is previewed stays) */
enum { DISCARD, PICK, OTHER };

static void fp_close(int how)
{
    int type = msel_frows[fp_at];
    fp_open = 0;
    wpop_modal(0, 0, 0, 0, 0);
    if (live_on()) {
        if (how == DISCARD)
            ls_revert(fp_model(), 0);
        else if (how == PICK && fp_due)
            fp_commit();
        fp_due = 0;
        return;
    }
    if (how == PICK && type != fp_was)
        FILTER_COMMIT(fp_model(), fp_track(), type, 1, 1);
}

/* msel_poll, every UI pass: a resting cursor's type committed (LIVE SELECT) */
static void fp_poll(void)
{
    if (fp_open && fp_due && (int)(ls_mono - fp_when) >= 0)
        fp_commit();
}

static u32 fp_bit(u32 code)
{
    return code == K_YES ? 1u : code == K_NO ? 2u : code == K_PUSH_G ? 4u
           : code == K_UP ? 8u : code == K_DOWN ? 16u : code == K_LEFT ? 32u : code == K_RIGHT ? 64u : 0u;
}

/* the lit row D on, stopping at the ends (the knob, and the arrows: UP / DOWN one, LEFT / RIGHT a page of five,
 * 2026-11-12, the User: "up and down keys should navigate in the open list (whichever kind); left/right page one
 * page up/down"); LIVE SELECT: committed once it rests */
static void fp_move(int d)
{
    int was = fp_at;
    fp_at += d;
    fp_at = fp_at < 0 ? 0 : fp_at >= MSEL_FROWS ? MSEL_FROWS - 1 : fp_at;
    if (fp_at != was && live_on()) {
        fp_due = 1;
        fp_when = ls_mono + REST;
    }
    wpop_modal("FLT1", MSEL_FROWS, fp_at, fp_name, 0);
}

/* from rec.c smp_ui_pop, every item while no screen of ours is up: -> 1 when the item is the list's (dropped) */
int flt_pop(const u8 *it, u32 code, int down, int func_held)
{
    if (it[0] == IT_KEY && code >= K_TRIG1 && code < K_TRIG1 + 16u)
        return 0;                               /* a [TRIG] key: the list stays, the key does what it does (2026-11-12,
                                                 * the User: "should not close when I press one of the 16 track
                                                 * buttons"; with FUNC held that is stock's FUNC + TRIG) */
    if (it[0] == IT_KEY) {
        u32 b = fp_bit(code);
        if (fp_eat & b) {                       /* a key the list took: its repeats and its release */
            if (!down)
                fp_eat &= ~b;
            else if (fp_open && b >= 8u)        /* an arrow held: on it goes */
                fp_move(code == K_UP ? -1 : code == K_DOWN ? 1 : code == K_LEFT ? -5 : 5);
            return 1;
        }
        if (!fp_open || (!down && code != K_FUNC))
            return 0;
        if (code == K_FUNC) {                   /* FUNC let go: the pick (FUNC goes on to stock) */
            if (!down)
                fp_close(PICK);
            return 0;
        }
        if (b >= 8u) {                          /* an arrow: the list moves */
            fp_eat |= b;
            fp_move(code == K_UP ? -1 : code == K_DOWN ? 1 : code == K_LEFT ? -5 : 5);
            return 1;
        }
        if (b) {
            fp_eat |= b;
            fp_close(code != K_NO ? PICK : DISCARD);
            return 1;
        }
        fp_close(OTHER);                        /* another key: it does what it does */
        return 0;
    }
    if (it[0] != IT_KNOB)
        return 0;
    if (code != KNOB_G) {
        if (fp_open)
            fp_close(OTHER);
        return 0;
    }
    if (!fp_open) {
        if (!func_held || smp_fb_open || smp_lst_open || msel_visible() || !ins_view_of(FLTR_VTABLE))
            return 0;
        fp_was = FILTER_GET(fp_model(), fp_track());
        fp_at = 0;
        for (int i = 0; i < MSEL_FROWS; i++)
            if (msel_frows[i] == fp_was)
                fp_at = i;
        fp_open = 1;
        fp_due = 0;
        ls_save(fp_track(), fp_model());        /* the sound as it was, for NO (LIVE SELECT) */
    } else {
        fp_move((signed char)it[8]);
        return 1;
    }
    wpop_modal("FLT1", MSEL_FROWS, fp_at, fp_name, 0);
    return 1;
}
