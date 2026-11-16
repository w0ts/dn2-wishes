/* The list popup: a parameter of our machines or FX whose value is a list of names (PERC's
 * TYPE, SOPHIE's and PLAITS' MODL, the two INSERT pages' M.SEL, FDN8's and XDLY's TYPE, the
 * sample machines' PLAY / MODE) shows the list round its value while its
 * knob turns, as Optimist's list popup does (optimist firmware/src/ui/optimist/op_preset.c,
 * pop_kind 3; GPL-3.0-only, the User's own, its behaviour borrowed here with credit):
 *
 *   - it opens on the knob's turn (rec.c smp_ui_pop notes which of A..H and when), on the page
 *     that draws that knob's place as a list, the value set as the knob sets it (nothing here
 *     changes a value: the popup only shows it);
 *   - five rows, the value lit in the middle, its neighbours above and below; the list stops at
 *     its ends (blank rows past them, not the other end's names); the header the parameter's
 *     label and the place in the list ("3/13");
 *   - it goes POP_HOLD after the last turn, or at once on any key press (a page key, TRK, a
 *     trig ...);
 *   - a trig held: the page shows the trig's p-lock, and so does the popup (the value it is
 *     given is the one the page draws);
 *   - the turn that opens it moves nothing (2026-11-11, the User: "for all list popup that open
 *     on knob twist for first knob twist only open the popup"): rec.c smp_ui_pop asks
 *     wpop_first_turn before it notes the turn, and takes one detent off that item (the item
 *     goes when it held one); the turns after it, a fast turn's next items included, move the
 *     value as before.
 *
 * Stock OS 1.12 has no such popup (its lists, MachineListView, ModDestListView, are modal menus
 * opened with a key), so it is drawn here, over the page, with stock's own text and pixel
 * routines and the grid's font. Canvas: 128 x 64, y counting up from the bottom; the box covers
 * the eight places (x 21..127, y 0..53), stock's title bar and left panel stay.
 *
 * The pages offer (wpop_offer) each list place as they draw it; wr_screen (page.c) clears the
 * offer before the draw (wpop_begin) and draws the popup last (wpop_draw); wr_poll (wpop_poll)
 * asks for the redraws: one when a knob turns, one when the popup goes.
 *
 * Two parts, each its own switch (cpage.py POPUP_OURS / POPUP_STOCK): WPOP_OURS our machines'
 * and FX's lists (wpop_offer), WPOP_STOCK stock parameters' (popup_stock.c, wpop_offer_stock).
 */
typedef unsigned int u32;
typedef unsigned char u8;

#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70)
#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)       /* 1,500 a second */
#define FONT       0x44508ED8u                          /* the grid's label font (page.c's) */

#define POP_HOLD   2250u                                /* 1.5 s after the last turn (Optimist's toast) */
#define POP_HALF   2                                    /* rows above and below the value: five in all */
#define BOX_X0     21
#define BOX_X1     127
#define BOX_Y1     53                                   /* under stock's title bar (y 54..63) */
#define ROW_H      8
#define ROWS_Y0    2                                    /* the bottom row's base */
#define HEAD_Y     45                                   /* the header's text */
#define RULE_Y     43
#define NAME_X     27
#define TAG_X      64
#define COUNT_X    102                                  /* the place in the list, "13/13" */

typedef const char *(*wpop_name_fn)(int i, int arg);

extern int smp_pop_knob;                                /* rec.c: the last knob turned, 1..8 (A..H) */
extern u32 smp_knob_at;                                 /* ... and when (FRAMES) */
extern u32 smp_knob_seq, smp_key_seq;                   /* rec.c: the turn's and the last key press's place
                                                         * in the UI items' order */

static struct {
    const char *label;
    int n, cur, arg;
    wpop_name_fn name, tag;
} pop __attribute__((section(".data")));
static int pop_offered __attribute__((section(".data"))) = 0;    /* in this draw */
static u32 pop_listing __attribute__((section(".data"))) = 0;    /* the places offered as lists in this draw */
static u32 pop_listed __attribute__((section(".data"))) = 0;     /* ... in the last draw the popup could show on */
static int pop_shown __attribute__((section(".data"))) = 0;      /* drawn in the last draw */
static u32 pop_knob_seen __attribute__((section(".data"))) = 0;  /* smp_knob_seq at the last poll */

/* the knob is turning: the last turn within POP_HOLD, no key pressed since */
static int pop_live(void)
{
    u32 now = FRAMES_NOW;
    return smp_knob_seq && now - smp_knob_at < POP_HOLD && (int)(smp_knob_seq - smp_key_seq) > 0;
}

void wpop_begin(void)
{
    pop_offered = 0;
    pop_listing = pop_listed = 0;                       /* a screen that never reaches wpop_draw lists none */
}

/* rec.c smp_ui_pop, a turn of KNOB (1..8: A..H) before it is noted: -> 1 when the turn opens the
 * popup (the page's place there is a list, and its popup is not up: another knob turned last, or
 * POP_HOLD gone, or a key pressed since) */
int wpop_first_turn(int knob)
{
    if (knob < 1 || knob > 8 || !(pop_listed >> (knob - 1) & 1u))
        return 0;
    return !(smp_pop_knob == knob && pop_live());
}

/* a page draws place SLOT (0..7, knob A..H) as a list of N names, CUR the value (0..N-1, as the
 * page shows it); NAME(i, ARG) the i-th's text, TAG(i, ARG) an optional second column */
static void offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg)
{
    if (n < WPOP_MIN || !name)                          /* (WPOP_MIN: cpage.py POPUP_MIN) */
        return;
    if (slot >= 0 && slot < 8)
        pop_listing |= 1u << slot;
    if (slot != smp_pop_knob - 1 || !pop_live())
        return;
    pop.label = label;
    pop.n = n;
    pop.cur = cur < 0 ? 0 : cur >= n ? n - 1 : cur;
    pop.name = name;
    pop.tag = tag;
    pop.arg = arg;
    pop_offered = 1;
}

/* our machines' and FX's lists (WPOP_OURS) */
void wpop_offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg)
{
#if WPOP_OURS
    offer(slot, label, n, cur, name, tag, arg);
#else
    (void)slot; (void)label; (void)n; (void)cur; (void)name; (void)tag; (void)arg;
#endif
}

/* stock parameters' lists (popup_stock.c, WPOP_STOCK) */
void wpop_offer_stock(int slot, const char *label, int n, int cur, wpop_name_fn name, int arg)
{
    offer(slot, label, n, cur, name, 0, arg);
}

/* the screen's place SLOT from a stock cell's widget at X0, Y0 (page.c wr_cell: the cells are
 * x = 24 + 26 col, the top row at y 27, the bottom at 0) */
int wpop_slot_of(int x0, int y0)
{
    int col = (x0 - 24 + 13) / 26;
    col = col < 0 ? 0 : col > 3 ? 3 : col;
    return col + (y0 < 13 ? 4 : 0);
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
}

/* the canvas, as 0x40113e70 reads it (md_page.c invert): +4 width, +8 height, +12 words a
 * column, +16 the bits (bit 31 - (y & 31) of word y >> 5 of the column) */
static void invert(void *c, int x0, int y0, int x1, int y1)
{
    const int *cv = (const int *)c;
    u32 *bits = (u32 *)cv[4];
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            if (x >= 0 && y >= 0 && x < cv[1] && y < cv[2])
                bits[x * cv[3] + (y >> 5)] ^= 0x80000000u >> (y & 31);
}

/* the box, LABEL and the place in the list in its header, five rows round CUR (NAME_FMT: the
 * names' width) */
static void draw_list(void *c, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag,
                      int arg, const char *name_fmt)
{
    fill(c, BOX_X0, 0, BOX_X1, BOX_Y1, 0);
    fill(c, BOX_X0, 0, BOX_X0, BOX_Y1, 1);              /* the frame */
    fill(c, BOX_X1, 0, BOX_X1, BOX_Y1, 1);
    fill(c, BOX_X0, 0, BOX_X1, 0, 1);
    fill(c, BOX_X0, BOX_Y1, BOX_X1, BOX_Y1, 1);
    TEXT(c, FONT, NAME_X - 2, HEAD_Y, 0, "%.6s", label);
    TEXT(c, FONT, COUNT_X, HEAD_Y, 0, "%d/%d", cur + 1, n);
    for (int x = BOX_X0 + 2; x <= BOX_X1 - 2; x += 2)   /* the rule under the header, dotted */
        SET_PIXEL(c, x, RULE_Y, 1);
    for (int r = 0; r < 2 * POP_HALF + 1; r++) {
        int i = cur - POP_HALF + r;                     /* the top row first */
        int y = ROWS_Y0 + (2 * POP_HALF - r) * ROW_H;
        if (i < 0 || i >= n)
            continue;                                   /* past an end: blank */
        const char *nm = name(i, arg);
        TEXT(c, FONT, NAME_X, y + 1, 0, name_fmt, nm ? nm : "");
        const char *tg = tag ? tag(i, arg) : 0;
        if (tg && tg[0])
            TEXT(c, FONT, TAG_X, y + 1, 0, "%.11s", tg);
        if (i == cur)                                   /* the value: its row lit */
            invert(c, BOX_X0 + 2, y, BOX_X1 - 2, y + ROW_H - 1);
    }
}

/* A list the user moves through (2026-11-11, msel.c's filter type on FUNC + G): drawn in the same
 * box, over the knob's popup, until it is closed (LABEL 0); its names up to 12 characters (no tag
 * column). Closing it ends the knob's popup too, as a key press does: the knob's own list does not
 * follow it onto the page. */
static struct {
    const char *label;
    int n, cur, arg;
    wpop_name_fn name;
} modal __attribute__((section(".data")));
static int modal_dirty __attribute__((section(".data"))) = 0;
extern u32 smp_ui_seq;                                  /* rec.c */

void wpop_modal(const char *label, int n, int cur, wpop_name_fn name, int arg)
{
    if (!label && modal.label)
        smp_key_seq = ++smp_ui_seq;
    modal.label = label;
    modal.n = n;
    modal.cur = cur;
    modal.name = name;
    modal.arg = arg;
    modal_dirty = 1;
}

void wpop_draw(void *c)
{
    pop_listed = pop_listing;
    if (modal.label) {
        draw_list(c, modal.label, modal.n, modal.cur, modal.name, 0, modal.arg, "%.12s");
        return;
    }
    pop_shown = pop_offered && pop_live();
    if (!pop_shown)
        return;
    draw_list(c, pop.label, pop.n, pop.cur, pop.name, pop.tag, pop.arg, "%.8s");
}

/* page.c wr_poll, once a UI loop: a redraw on a knob's turn (so the popup opens even where the
 * value did not move: a list's end), and one when it goes */
void wpop_poll(void *screen)
{
    if (modal_dirty) {                                  /* the list the user moves: opened, moved, closed */
        modal_dirty = 0;
        SET_DIRTY(screen);
    }
    if (smp_knob_seq != pop_knob_seen) {
        pop_knob_seen = smp_knob_seq;
        SET_DIRTY(screen);
    }
    if (pop_shown && !pop_live()) {
        pop_shown = 0;
        SET_DIRTY(screen);
    }
}
