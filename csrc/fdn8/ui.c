/* FDN8's page (docs/fdn8.md): the Reverb page's TYPE knob and its names, OS 1.12.
 *
 * TYPE is stock's record 131, "Reverb FX Routing": kit slot 48, range 0..1 (0x100; widened here
 * to 0..2 for LONG, its top value at record + 0x0c), default 1,
 * stored with the kit and sent in the frame (word 0xa28), shown on no page and read by nothing
 * on the DSP (Digiwerk T3.4 / T6.1 found it; the stock unpack keeps only a byte nobody reads).
 * FDN8's DSP code (dnfw.fdn8.program) reads that frame word: 0 is FDN8, 1 the stock reverb, 2
 * LONG (FDN8 with lines twice as long, a bigger and darker room), so
 * every existing kit (they all carry 1) plays the stock reverb as before.
 *
 * rvt_poll, once a UI loop (page.c wr_poll):
 *  - puts record 131 in the Reverb page's empty G position: the page's record list is built
 *    at boot (0x400c9fca.., stock 1.12) at 0x42433f20, [123 124 125 126 127 128 0 0 130],
 *    and G (0x42433f38) is cleared there (0x400c9fde clr.l). Written again only if it is not 131;
 *  - gives record 131 the names TYPE / "Reverb Type" and a value text, STOCK or FDN8 (its
 *    stock formatter 0x400e3592 says Pre / Post);
 *  - while TYPE is FDN8, records 124-126 carry FDN8's long names (the header's, as a knob
 *    turns): Decay Time -> Size, FB Shelving Freq -> Damping, FB Shelving Gain -> Modulation;
 *    stock's go back otherwise. Their short names (the knobs' labels DEC / FREQ / GAIN) stay:
 *    this page copies its labels when its views are built at boot (measured in the emulator:
 *    a rename later never reached them), so a label could not follow TYPE.
 * The frame buffer is 0x80005e60 on 1.12 as on 1.11 (the frame builder's lea at 0x400274ba,
 * byte-checked on both): TYPE is the big-endian word at +0xa28, what the DSP gets. Once the
 * Reverb page has drawn TYPE's cell (rvt_cell, from page.c wr_cell), the value the page holds
 * is used instead: the same value, and the one the emulator has (it builds no frames).
 *
 * rvt_cell: TYPE's cell shows STOCK / FDN8 (two lines, in the label font) in place of
 * stock's PRE / POST FX picture, as page.c draws PING's TYPE.
 */
typedef unsigned int u32;
typedef unsigned short u16;

#define RECORD_AT(id)   (0x401F83A4u + 60u * (id))
#define NAME_LONG(id)   (*(const char **)(RECORD_AT(id) + 0x28u))
#define NAME_SHORT(id)  (*(const char **)(RECORD_AT(id) + 0x30u))
#define RECORD_FMT(id)  (*(void **)(RECORD_AT(id) + 0x34u))
#define RECORD_MAX(id)  (*(volatile u32 *)(RECORD_AT(id) + 0x0Cu))   /* the top value << 8: 0x100 stock */
#define REV_PAGE_G      (*(volatile u32 *)0x42433F38u)   /* the Reverb page's position G */
#define FRAME_TYPE      (*(volatile u16 *)0x80006888u)   /* the frame (0x80005e60) + 0xa28: k 48 */
#define TYPE_REC        131u
#define GET_VALUE  ((int (*)(void *, u32, unsigned char *))0x4006538E)   /* (view, id, &flag) */
#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70)
#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define FONT       0x44508ED8u
#define CENTRED    2

static const u16 rvt_ids[3] = {124, 125, 126};
static const char *const rvt_long[3] = {"Size", "Damping", "Modulation"};
static const char *rvt_stock_long[3] __attribute__((section(".data")));
int rvt_state __attribute__((section(".data"))) = -1;   /* -1 not yet run, 0 stock, 1 FDN8 */
u32 rvt_placed __attribute__((section(".data"))) = 0;   /* times G was written */
int rvt_seen __attribute__((section(".data"))) = -1;    /* TYPE as the page last drew it (0 FDN8, 1 STOCK,
                                                         * 2 LONG), -1 not yet */

static void rvt_put(char *buf, const char *s)
{
    int k = 0;
    while (s[k]) {
        buf[k] = s[k];
        k++;
    }
    buf[k] = 0;
}

/* the value text of record 131 (v: the raw value, 0, 0x100 or 0x200) */
static void rvt_text(int v, char *buf)
{
    int t = (v >> 8) & 0xFF;
    rvt_put(buf, t == 1 ? "STOCK" : t == 2 ? "LONG" : "FDN8");
}

/* 2026-11-11 (the User: no bare 0..127): while TYPE is FDN8 or LONG the page's six knobs' value texts are the
 * FDN8 insert's units (csrc/waverider/md_page.c mu_ins, dnfw.mnm.units INS_UNITS: the same engine and knob / 127):
 * PRE ms, SIZE %, DAMP %, MOD 0..200 %, HPF / LPF Hz. Ours stay installed from the first poll on and ask, each
 * call, which TYPE the page shows (rvt_seen, as rvt_poll does); STOCK's text is stock's formatter's, at its fixed
 * 1.12 address (read from the records 123..128 of stock 1.12). Not a pointer saved at run time: measured in the
 * emulator, our .data started again (the chunk installed again) while the records still held ours, so the "saved
 * stock" was ours and the formatter called itself until the stack ran out */
#define FDN8_TYPE 7                              /* dnfw.inserts.design FDN8 */
extern const char *mu_ins(int type, int knob, int k);
static const u16 rvu_ids[6] = {123, 124, 125, 126, 127, 128};
static const u32 rvu_stock[6] = {0x400E3030u, 0x400E375Eu, 0x400E3030u, 0x400E3030u, 0x400E3030u, 0x400E3030u};

static void rvu(int knob, int v, char *buf)
{
    if (!(rvt_seen >= 0 ? rvt_seen != 1 : FRAME_TYPE != 0x100)) {
        ((void (*)(int, char *))rvu_stock[knob])(v, buf);
        return;
    }
    const char *t = mu_ins(FDN8_TYPE, knob, (v >> 8) & 0xFF);
    rvt_put(buf, t ? t : "");
}
#define RVU(n) static void rvu##n(int v, char *b) { rvu(n, v, b); }
RVU(0) RVU(1) RVU(2) RVU(3) RVU(4) RVU(5)
static void (*const rvu_fns[6])(int, char *) = {rvu0, rvu1, rvu2, rvu3, rvu4, rvu5};

void rvt_poll(void)
{
    int fdn = rvt_seen >= 0 ? rvt_seen != 1 : FRAME_TYPE != 0x100;
    if (REV_PAGE_G != TYPE_REC) {
        REV_PAGE_G = TYPE_REC;
        rvt_placed++;
    }
    if (fdn == rvt_state)
        return;
    if (rvt_state < 0) {                         /* the first call: keep stock's pointers */
        for (int k = 0; k < 3; k++) {
            rvt_stock_long[k] = NAME_LONG(rvt_ids[k]);
        }
        for (int k = 0; k < 6; k++)
            RECORD_FMT(rvu_ids[k]) = (void *)rvu_fns[k];
        NAME_LONG(TYPE_REC) = "Reverb Type";
        NAME_SHORT(TYPE_REC) = "TYPE";
        RECORD_FMT(TYPE_REC) = (void *)rvt_text;
        RECORD_MAX(TYPE_REC) = 0x200;            /* 0..2: FDN8, STOCK (every kit), LONG */
    }
    for (int k = 0; k < 3; k++)
        NAME_LONG(rvt_ids[k]) = fdn ? rvt_long[k] : rvt_stock_long[k];
    rvt_state = fdn;
}

#define LABEL_DY 0                       /* the label's text row, from the cell's y */

/* a cell's label (x0..x0+23, y0..y0+7) drawn again with NAME (TYPE's: measured in the
 * emulator to sit where stock's label of that position would) */
static void rvt_label(void *canvas, int x0, int y0, const char *name)
{
    for (int x = x0; x < x0 + 24; x++)
        for (int y = y0; y < y0 + 8; y++)
            SET_PIXEL(canvas, x, y, 0);
    TEXT(canvas, FONT, x0 + 12, y0 + LABEL_DY, CENTRED, name);
}

/* page.c wr_cell, after each stock cell widget: TYPE's cell (its widget x0..x0+23,
 * y0+8..y0+23, and its label, in case the views were built before TYPE was named) */
/* 2026-11-09: the list popup (csrc/waverider/popup.c), the values' order */
typedef const char *(*wpop_name_fn)(int i, int arg);
extern void wpop_offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg);
extern int wpop_slot_of(int x0, int y0);
/* 2026-11-11 (the User: "stock should be the first item", the knob's left end): the list's order is
 * STOCK FDN8 LONG; the stored value keeps its meaning (0 FDN8, 1 STOCK, 2 LONG: kits, the frame and the
 * DSP). rvt_pos[stored] is the list position, rvt_val[position] the stored value (the swap of 0 and 1,
 * so one table is both); the knob's step goes through rvt_step (fmt.c smp_quant, the setter's hook). */
static const char *const rvt_list[3] = {"STOCK", "FDN8", "LONG"};
static const unsigned char rvt_pos[3] = {1, 0, 2};

/* TYPE's knob turned by D (its sign: right is +): the next stored value in the list's order; OLD0 the
 * word held (value << 8 | fine) -> the word to write */
int rvt_step(int old0, int d)
{
    int c = (old0 >> 8) & 0xFF;
    int p = rvt_pos[c > 2 ? 1 : c] + (d > 0 ? 1 : -1);
    p = p < 0 ? 0 : p > 2 ? 2 : p;
    return rvt_pos[p] << 8;
}

static const char *rvt_pop_name(int i, int arg)
{
    (void)arg;
    return rvt_list[i];
}

void rvt_cell(void *view, void *canvas, int x0, int y0, u32 id)
{
    if (id != TYPE_REC)
        return;
    unsigned char flag;
    int v = GET_VALUE(view, id, &flag);
    rvt_seen = (v >> 8) & 0xFF;
    if (rvt_seen > 2)
        rvt_seen = 1;
    extern void fxp_seen(int page, int ours);
    fxp_seen(2, rvt_seen != 1);                 /* the page 2 of FDN8 and LONG (csrc/fxpage) */
    for (int x = x0; x < x0 + 24; x++)
        for (int y = y0 + 8; y < y0 + 24; y++)
            SET_PIXEL(canvas, x, y, 0);
    TEXT(canvas, FONT, x0 + 12, y0 + 17, CENTRED, rvt_seen == 1 ? "STO" : rvt_seen == 2 ? "LON" : "FDN");
    TEXT(canvas, FONT, x0 + 12, y0 + 9, CENTRED, rvt_seen == 1 ? "CK" : rvt_seen == 2 ? "G" : "8");
    rvt_label(canvas, x0, y0, "TYPE");
    wpop_offer(wpop_slot_of(x0, y0), "TYPE", 3, rvt_pos[rvt_seen], rvt_pop_name, 0, 0);
}
