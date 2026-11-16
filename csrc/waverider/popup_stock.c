/* The list popup on STOCK parameters (popup.c draws it): a stock page's cell whose record is a
 * short list of names (LFO WAVE, LFO MODE, a filter's or an FX's mode ...), offered as stock
 * draws the cell. A separate part from the popup on our machines (popup.c, WPOP_OURS): either
 * ships alone (cpage.py POPUP_OURS / POPUP_STOCK, the build's WPOP_OURS / WPOP_STOCK).
 *
 * Which records: every cell stock draws passes page.c wr_cell (0x4006448a's exit, the cell's
 * widget at x0, y0 and its record id). A record is a list when
 *   - its range is whole steps of 0x100 (one per entry), POPUP_MIN (4) to 64 entries, and
 *   - stock's own value text for it (the record's formatter, + 0x34, as the header's value line
 *     prints it) names every entry: none starts as a number does (a digit, a sign, a point), so
 *     an algorithm 1..8, a speed 1/16 .. or a note are left alone.
 * The names are stock's formatter's, the label its short name, the value the one the page draws
 * (a held trig's p-lock included). Records our own code shows (FDN8's and XDLY's TYPE, PING's)
 * are offered by their own code, not here.
 */
typedef unsigned int u32;

#define GET_VALUE  ((int (*)(void *, u32, unsigned char *))0x4006538E)
#define RECORD(id) ((const int *)(0x401F83A4u + 60u * (id)))
#define NAME_SHORT(id) (*(const char **)(0x401F83A4u + 60u * (id) + 0x30u))
#define FORMATTER(id)  (*(void (**)(int, char *))(0x401F83A4u + 60u * (id) + 0x34u))
#define ID_LIMIT   1200u                        /* the records' table, generously (ids seen up to ~400) */
#define MAX_LIST   64

typedef const char *(*wpop_name_fn)(int i, int arg);
typedef void (*wpop_move_fn)(int d, int arg);
extern void wpop_offer_stock(int slot, const char *label, int n, int cur, wpop_name_fn name, int arg, wpop_move_fn move);
extern int smp_param_put(u32 id, int value, int click);   /* rec.c */
extern int wpop_slot_of(int x0, int y0);

static u32 seen_id __attribute__((section(".data"))) = 0xFFFFFFFFu;   /* the last record judged */
static int seen_n __attribute__((section(".data"))) = 0;              /* its entries, 0 not a list */

static void (*fmt_of(u32 id))(int, char *)
{
    void (*f)(int, char *) = FORMATTER(id);
    u32 a = (u32)f;
    return a >= 0x40000000u && a < 0x40400000u && !(a & 1u) ? f : 0;   /* code in the OS image */
}

static int numeric(const char *t)
{
    char c = t[0];
    return c == 0 || (c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.';
}

/* -> the entries of record ID if it is a list of names, else 0 (judged once a record) */
static int list_n(u32 id)
{
    if (id == seen_id)
        return seen_n;
    seen_id = id;
    seen_n = 0;
    if (id == 0 || id >= ID_LIMIT || !fmt_of(id))
        return 0;
    const int *r = RECORD(id);
    int span = r[3] - r[2];
    if (span <= 0 || span % 0x100)
        return 0;
    int n = span / 0x100 + 1;
    if (n < WPOP_MIN || n > MAX_LIST)          /* (cpage.py POPUP_MIN: a shorter list, no popup) */
        return 0;
    for (int i = 0; i < n; i++) {
        char b[32];
        b[0] = 0;
        fmt_of(id)(r[2] + i * 0x100, b);
        b[31] = 0;
        if (numeric(b))
            return 0;
    }
    seen_n = n;
    return n;
}

static const char *stock_name(int i, int id)
{
    static char b[32] __attribute__((section(".data")));
    b[0] = 0;
    fmt_of((u32)id)(RECORD(id)[2] + i * 0x100, b);
    b[31] = 0;
    return b;
}

/* the arrows (popup.c wpop_arrow): record ID's value D entries on, as the page shows it (the view of the
 * offer's draw), written as the knob writes it */
static void *pop_view __attribute__((section(".data"))) = 0;

static void stock_move(int d, int id)
{
    unsigned char flag;
    int n = list_n((u32)id), lo = RECORD(id)[2];
    if (!n || !pop_view)
        return;
    int to = (GET_VALUE(pop_view, (u32)id, &flag) - lo) / 0x100 + d;
    to = to < 0 ? 0 : to >= n ? n - 1 : to;
    smp_param_put((u32)id, lo + to * 0x100, 0);
}

/* page.c wr_cell, after each stock cell (OURS: a record our code draws itself) */
void wpop_stock_cell(void *view, int x0, int y0, u32 id, int ours)
{
#if WPOP_STOCK
    if (ours)
        return;
    int n = list_n(id);
    if (!n)
        return;
    unsigned char flag;
    int cur = (GET_VALUE(view, id, &flag) - RECORD(id)[2]) / 0x100;
    pop_view = view;
    wpop_offer_stock(wpop_slot_of(x0, y0), NAME_SHORT(id), n, cur, stock_name, (int)id, stock_move);
#else
    (void)view; (void)x0; (void)y0; (void)id; (void)ours;
#endif
}
