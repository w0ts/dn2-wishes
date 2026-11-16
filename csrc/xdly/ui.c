/* XDLY's page (docs/xdly.md): the Delay page's TYPE knob and its names, OS 1.12.
 *
 * TYPE is stock's record 122, "Delay FX Routing": kit slot 40, range 0..1 (0x100), default 1,
 * stored with the kit and sent in the frame (word 0xa18; the DSP's frame image 0x25cea4), shown
 * on no page and read by nothing on the DSP: the delay's twin of the reverb's record 131, which
 * FDN8's TYPE uses (csrc/fdn8/ui.c). XDLY's DSP code (dnfw.xdly.program) reads that frame word:
 * 0 is XDLY, 1 the stock delay, so every existing kit (they all carry 1) plays as before.
 *
 * dlt_poll, once a UI loop (page.c wr_poll):
 *  - puts record 122 in the Delay page's empty G position: the page's record list is built at
 *    boot (stock 1.12, 0x400c9f50..) at 0x42433ef4, [113 114 115 116 117 118 0 119 121], and G
 *    (0x42433f0c) is cleared there (0x400c9f68 clr.l). Written again only if it is not 122;
 *  - gives record 122 the names TYPE / "Delay Type" and a value text, STOCK or XDLY;
 *  - while TYPE is XDLY, records 113 115 116 117 118 carry XDLY's long names (the header's, as a
 *    knob turns): Time 1, Time 2, Feedback, Modulation, Tone; stock's go back otherwise. The
 *    knobs' labels (TIME WID FDBK HPF LPF) stay: the FX pages copy their labels when their views
 *    are built at boot (measured for the Reverb page, docs/fdn8.md).
 * The frame word is the big-endian word at 0x80005e60 + 0xa18 (the frame builder's lea at
 * 0x400274ba); once the Delay page has drawn TYPE's cell (dlt_cell), the value it holds is used.
 *
 * dlt_cell (page.c wr_cell): TYPE's cell shows STOCK / XDLY in place of stock's PRE / POST picture.
 */
typedef unsigned int u32;
typedef unsigned short u16;

#define RECORD_AT(id)   (0x401F83A4u + 60u * (id))
#define NAME_LONG(id)   (*(const char **)(RECORD_AT(id) + 0x28u))
#define NAME_SHORT(id)  (*(const char **)(RECORD_AT(id) + 0x30u))
#define RECORD_FMT(id)  (*(void **)(RECORD_AT(id) + 0x34u))
#define DLY_PAGE_G      (*(volatile u32 *)0x42433F0Cu)   /* the Delay page's position G */
#define FRAME_TYPE      (*(volatile u16 *)0x80006878u)   /* the frame (0x80005e60) + 0xa18: k 40 */
#define TYPE_REC        122u
#define GET_VALUE  ((int (*)(void *, u32, unsigned char *))0x4006538E)
#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70)
#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define FONT       0x44508ED8u
#define CENTRED    2
#define N_NAMES    5

static const u16 dlt_ids[N_NAMES] = {113, 115, 116, 117, 118};
static const char *const dlt_long[N_NAMES] = {"Time 1", "Time 2", "Feedback", "Modulation", "Tone"};
static const char *dlt_stock_long[N_NAMES] __attribute__((section(".data")));
int dlt_state __attribute__((section(".data"))) = -1;   /* -1 not yet run, 0 stock, 1 XDLY */
u32 dlt_placed __attribute__((section(".data"))) = 0;   /* times G was written */
int dlt_seen __attribute__((section(".data"))) = -1;    /* TYPE as the page last drew it, -1 not yet */

static void dlt_put(char *buf, const char *s)
{
    int k = 0;
    while (s[k]) {
        buf[k] = s[k];
        k++;
    }
    buf[k] = 0;
}

static void dlt_text(int v, char *buf)
{
    dlt_put(buf, ((v >> 8) & 0xFF) ? "STOCK" : "XDLY");
}

void dlt_poll(void)
{
    int xd = dlt_seen >= 0 ? dlt_seen == 0 : FRAME_TYPE == 0;
    if (DLY_PAGE_G != TYPE_REC) {
        DLY_PAGE_G = TYPE_REC;
        dlt_placed++;
    }
    if (xd == dlt_state)
        return;
    if (dlt_state < 0) {                         /* the first call: keep stock's pointers */
        for (int k = 0; k < N_NAMES; k++)
            dlt_stock_long[k] = NAME_LONG(dlt_ids[k]);
        NAME_LONG(TYPE_REC) = "Delay Type";
        NAME_SHORT(TYPE_REC) = "TYPE";
        RECORD_FMT(TYPE_REC) = (void *)dlt_text;
    }
    for (int k = 0; k < N_NAMES; k++)
        NAME_LONG(dlt_ids[k]) = xd ? dlt_long[k] : dlt_stock_long[k];
    dlt_state = xd;
}

static void dlt_label(void *canvas, int x0, int y0, const char *name)
{
    for (int x = x0; x < x0 + 24; x++)
        for (int y = y0; y < y0 + 8; y++)
            SET_PIXEL(canvas, x, y, 0);
    TEXT(canvas, FONT, x0 + 12, y0, CENTRED, name);
}

/* 2026-11-09: the list popup (csrc/waverider/popup.c), the values' order */
typedef const char *(*wpop_name_fn)(int i, int arg);
extern void wpop_offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg);
extern int wpop_slot_of(int x0, int y0);
static const char *const dlt_list[2] = {"XDLY", "STOCK"};

static const char *dlt_pop_name(int i, int arg)
{
    (void)arg;
    return dlt_list[i];
}

void dlt_cell(void *view, void *canvas, int x0, int y0, u32 id)
{
    if (id != TYPE_REC)
        return;
    unsigned char flag;
    int v = GET_VALUE(view, id, &flag);
    dlt_seen = (v >> 8) & 0xFF ? 1 : 0;
    for (int x = x0; x < x0 + 24; x++)
        for (int y = y0 + 8; y < y0 + 24; y++)
            SET_PIXEL(canvas, x, y, 0);
    TEXT(canvas, FONT, x0 + 12, y0 + 17, CENTRED, dlt_seen ? "STO" : "XDL");
    TEXT(canvas, FONT, x0 + 12, y0 + 9, CENTRED, dlt_seen ? "CK" : "Y");
    dlt_label(canvas, x0, y0, "TYPE");
    wpop_offer(wpop_slot_of(x0, y0), "TYPE", 2, dlt_seen, dlt_pop_name, 0, 0);
}
