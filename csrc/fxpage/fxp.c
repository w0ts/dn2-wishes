/* The send DELAY and REVERB pages' second page (docs/fxpage.md; 2026-11-11, the User: "fct pressed and
 * release switch sub page"): while the Delay page's TYPE is XDLY, or the Reverb page's FDN8 or LONG, a FUNC TAP
 * (FUNC pressed and released with no other key, push or turn between) switches between page 1, stock's eight
 * places as they are, and page 2, eight more parameters of the engine. A small tag at the title bar's right end
 * says 1/2 or 2/2. STOCK type: no page 2, no tag, stock's page untouched.
 *
 *   - FUNC + turn stays stock's coarse jump on page 1 (we take no item there); on page 2 it jumps the
 *     value to the next of 0, its default, 127 (the direction of the turn);
 *   - FUNC + push (the modulation popup) and FUNC + long push (reset) are keys: they disarm the tap and are
 *     passed on; so does any other key, FUNC + FX (the way the send pages are entered, FUNC still down on
 *     arrival: the press of FX disarms it) and any FUNC + turn;
 *   - the delay's TIME (place A) is on both pages: on page 2 that place is stock's, left as stock drew it and
 *     its knob passed on;
 *   - the values are the project's (csrc/inserts/store.c keeps them beside the inserts': fxp_record,
 *     fxp_set_record), sent to the DSP with the change word in the directory page at 0xED0 (link.c).
 *
 * The page hooks, as the INSERT pages' (csrc/inserts/ins.c): fxp_pop (rec.c smp_ui_pop, before stock sees an
 * item), fxp_begin / fxp_draw (page.c wr_screen), fxp_seen (fdn8/ui.c rvt_cell and xdly/ui.c dlt_cell say which
 * page stock drew and which type it holds).
 *
 * 2026-11-12 (the User): the send CHORUS page's TYPE on its empty place E: STOCK (first) or JUNO (Optimist's
 * Juno-106 chorus, dnfw.inserts.jsend). The chorus has no spare stock record (its kit slots 25..31 are all its
 * knobs'; record 111 "Chorus Mix Vol." shares 110's index), so TYPE is the KIT's wishes record (csrc/wishes, tag
 * 0x0101, u8 0 STOCK / 1 JUNO; no field: STOCK), travelling with the kit as delay / reverb TYPE do; chr_get /
 * chr_set are its only readers and writer. Sent as the twelfth word (w[11]; 0 until sent: STOCK). The page
 * is known by stock drawing its DPTH cell (fxp_cell). With JUNO, DPTH is the MIX and SPD the MODE (I / II / I+II):
 * their values stay stock's, kit-stored; their labels are drawn over and their names and value texts swapped
 * (fxp_chorus_poll; stock 1.12's own pointers as constants, never saved at run time). */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed char s8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#ifndef KEY_HELD                                /* (the host test defines its own) */
#define KEY_HELD  ((int (*)(u32))0x4011FAC4u)
#endif
#define IT_KEY    0
#define IT_KNOB   1
#define K_FUNC    17
#define PAGE_DELAY  1                           /* fxp_seen's and fxp_up's page: the Delay page (XDLY), */
#define PAGE_REVERB 2                           /* the Reverb page (FDN8 / LONG) */
#define CHR_DPTH  105u                          /* the Chorus page's DPTH record: its cell drawn = the page is up */
#define CHR_SPD   106u
#define CHR_TAG   0x0101u                       /* the chorus send's TYPE in the kit's wishes record: 0 STOCK, 1 JUNO */
#ifndef CHR_KIT                                 /* (the host test defines its own) */
#define CHR_KIT   (*(volatile u32 *)0x42C5B9ACu) /* the kit the sequencer plays (wish.h WISH_KIT_PLAYING) */
#endif
extern int wish_get(u32 item, u32 tag, u8 *out, u32 max);              /* csrc/wishes/wish.h */
extern int wish_put(u32 item, u32 tag, const u8 *v, u32 vlen);
extern volatile u32 wish_edits;
#define CHR_PLACE 4                             /* E */

#include "../waverider/widgets.h"
extern int smp_values_held(void);
extern int smp_overlay_dirty;
extern u32 ins_edits;                           /* moves on every edit: store.c saves the working copy */

struct fxp_param {
    const char *label;                          /* 4 characters at most; "" a place with no parameter yet */
    u8 def;                                     /* the knob 0..127 that is the DSP's value of before this page */
};

/* page 2's places A..H of each page; a parameter's mapping is in the DSP (dnfw.xdly / dnfw.fdn8 design) */
#include "fxp_params.h"

u8 fxp_v[2][8] __attribute__((section(".data")));       /* [page - 1][place]: the knobs 0..127 */
u32 fxp_gen __attribute__((section(".data"))) = 0;      /* moves on every change: the link sends */
int fxp_up __attribute__((section(".data"))) = 0;       /* page 2 up: 0 none, PAGE_DELAY or PAGE_REVERB */
static int seen __attribute__((section(".data"))) = 0;  /* the page stock drew this time (0 none, or not ours) */
static int armed __attribute__((section(".data"))) = 0; /* FUNC went down on one of our pages and nothing since */
static int touched __attribute__((section(".data"))) = -1;
static int inited __attribute__((section(".data"))) = 0;
static int chr_seen __attribute__((section(".data"))) = 0;     /* stock drew the Chorus page this time */
static int chr_touched __attribute__((section(".data"))) = 0;
static u32 chr_kit __attribute__((section(".data"))) = 0;       /* chr_get's cache: the kit and wish_edits it read */
static u32 chr_ed __attribute__((section(".data"))) = 0xFFFFFFFFu;
static u8 chr_val __attribute__((section(".data"))) = 0;
static int chr_sent __attribute__((section(".data"))) = 0;     /* the TYPE the last words carried */

/* the playing kit's chorus TYPE (0 STOCK, 1 JUNO): read again only when the kit or a record changed */
static int chr_get(void)
{
    u32 kit = CHR_KIT, ed = wish_edits;
    if (kit != chr_kit || ed != chr_ed) {
        u8 t = 0;
        chr_val = kit && wish_get(kit, CHR_TAG, &t, 1) == 1 && t == 1;
        chr_kit = kit;
        chr_ed = ed;
    }
    return chr_val;
}

/* TYPE V into the playing kit's record (STOCK: the field removed, as a kit that never had one). The record is
 * linked into the stored kit at stock's next save of it (KitActive's mirror, kit SAVE, project SAVE) */
static void chr_set(int v)
{
    u32 kit = CHR_KIT;
    u8 t = (u8)v;
    if (!kit || v == chr_get())
        return;
    wish_put(kit, CHR_TAG, &t, v ? 1u : 0u);
    chr_ed = 0xFFFFFFFFu;                       /* read it back */
}

static const char *text(int page, int i, int v);

static const struct fxp_param *table(int page)
{
    return page == PAGE_DELAY ? fxp_delay : fxp_reverb;
}

/* every value to its default (power-on, a NEW project, a project saved before this build) */
void fxp_defaults(void)
{
    for (int g = 0; g < 2; g++)
        for (int k = 0; k < 8; k++)
            fxp_v[g][k] = table(g + 1)[k].def;
    inited = 1;
    fxp_gen++;
}

static void init(void)
{
    if (!inited)
        fxp_defaults();
}

/* store.c's view: the sixteen bytes as saved, and set back */
void fxp_record(u8 *f)
{
    init();
    for (int g = 0; g < 2; g++)
        for (int k = 0; k < 8; k++)
            f[8 * g + k] = fxp_v[g][k];
}

void fxp_set_record(const u8 *f)
{
    init();
    for (int g = 0; g < 2; g++)
        for (int k = 0; k < 8; k++)
            fxp_v[g][k] = f[8 * g + k] & 0x7F;
    fxp_gen++;
}

/* the words link.c sends to the directory page (design.EX): the Delay engine's change word and its five values
 * (kf kn wl wr sn: the formulas of fxp_derive.h), the Reverb engine's the same way (none yet: change word 0) */
#define FXP_WORDS 12
#include "fxp_derive.h"

static u32 fbits(float f)
{
    union { float f; u32 u; } x;
    x.f = f;
    return x.u;
}

void fxp_words(u32 *w)
{
    init();
    for (int k = 0; k < FXP_WORDS; k++)
        w[k] = 0;
    const u8 *d = fxp_v[0];
    w[0] = fxp_gen;
    w[1] = xd_kf_bits[d[1] & 127];
    float kn = d[2] == XD_KN_DEF ? XD_KNEE_F : (float)d[2] * XD_KN_STEP_F + XD_KN_LO_F;
    w[2] = fbits(kn);
    float wl = 1.0f, wr = 0.0f;
    if (d[3] != XD_WD_DEF) {
        float x = (float)d[3] * XD_WD_K_F;
        wl = (1.0f + x) * 0.5f;
        wr = (1.0f - x) * 0.5f;
    }
    w[3] = fbits(wl);
    w[4] = fbits(wr);
    w[5] = fbits(d[4] == XD_IN_DEF ? 0.0f : ((float)d[4] - 64.0f) * XD_IN_K_F);
    const u8 *r = fxp_v[1];                     /* the Reverb engine's: sd f wl wr (dnfw.fdn8.design.derive) */
    w[6] = fxp_gen;
    w[7] = fbits(r[0] == FD_DF_DEF ? 1.0f : (float)r[0] * FD_DF_K_F);
    w[8] = fbits(r[2] == FD_FZ_DEF ? 0.0f : (float)r[2] * FD_FZ_K_F);
    wl = 1.0f;
    wr = 0.0f;
    if (r[1] != FD_WD_DEF) {
        float x = (float)r[1] * FD_WD_K_F;
        wl = (1.0f + x) * 0.5f;
        wr = (1.0f - x) * 0.5f;
    }
    w[9] = fbits(wl);
    w[10] = fbits(wr);
    w[11] = (u32)chr_get();                     /* the chorus send's TYPE (dnfw.inserts.design.JS_TYPE) */
    chr_sent = (int)w[11];
}

/* page.c wr_poll, once a UI loop: with JUNO, records 105 / 106 named Mix / Mode, their values MIX % and I / II / I+II;
 * stock's names and formatter otherwise (stock 1.12's own: 0x40210a01 "Depth", 0x40210a3b "Speed", 0x400e3030) */
#define REC_AT(id)    (0x401F83A4u + 60u * (id))
#define REC_LONG(id)  (*(const char **)(REC_AT(id) + 0x28u))
#define REC_FMT(id)   (*(void **)(REC_AT(id) + 0x34u))
#define STOCK_FMT     0x400E3030u
static int chr_state __attribute__((section(".data"))) = -1;

static void put(char *b, const char *s)
{
    int k = 0;
    while (s[k]) {
        b[k] = s[k];
        k++;
    }
    b[k] = 0;
}

static void chr_mix(int v, char *b)
{
    if (!chr_get()) {
        ((void (*)(int, char *))STOCK_FMT)(v, b);
        return;
    }
    put(b, text(0, 0, (v >> 8) & 0x7F));
}

static void chr_mode(int v, char *b)
{
    static const char *const m[3] = {"I", "II", "I+II"};
    if (!chr_get()) {
        ((void (*)(int, char *))STOCK_FMT)(v, b);
        return;
    }
    put(b, m[(((v >> 8) & 0x7F) * 3) >> 7]);
}

void fxp_chorus_poll(void)
{
    init();
    int j = chr_get();
    if (j != chr_sent)
        fxp_gen++;                              /* TYPE moved (turned, or another kit / record): the link sends */
    if (j == chr_state)
        return;
    REC_FMT(CHR_DPTH) = (void *)chr_mix;
    REC_FMT(CHR_SPD) = (void *)chr_mode;
    REC_LONG(CHR_DPTH) = j ? "Mix" : (const char *)0x40210A01u;
    REC_LONG(CHR_SPD) = j ? "Mode" : (const char *)0x40210A3Bu;
    chr_state = j;
}

/* 1 when any value is not at its default: the DSP then needs the words (link.c); at the defaults it runs the old constants */
int fxp_active(void)
{
    init();
    for (int g = 0; g < 2; g++)
        for (int k = 0; k < 8; k++)
            if (fxp_v[g][k] != table(g + 1)[k].def)
                return 1;
    return chr_get();
}

/* page.c wr_screen: before stock draws */
void fxp_begin(void)
{
    seen = 0;
    chr_seen = 0;
}

/* page.c wr_cell: stock drew cell ID (the Chorus page's DPTH: that page is up) */
void fxp_cell(u32 id)
{
    if (id == CHR_DPTH)
        chr_seen = 1;
}

int fxp_chorus_type(void)
{
    return chr_get();
}

/* fdn8/ui.c rvt_cell, xdly/ui.c dlt_cell: stock drew the TYPE cell of page PAGE, whose type is ours (1) or stock's (0) */
void fxp_seen(int page, int ours)
{
    seen = ours ? page : 0;
}

int fxp_visible(void)
{
    return fxp_up && fxp_up == seen;
}

static int clamp(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

/* a turn of knob K (1..8) on page 2, DELTA clicks; FUNC held: the jump to the next of 0, the default, 127 */
static void turn(int k, int delta)
{
    int g = fxp_up - 1, i = k - 1;
    const struct fxp_param *p = &table(fxp_up)[i];
    if (!p->label[0])
        return;
    int v = fxp_v[g][i];
    if (KEY_HELD(K_FUNC)) {
        int lo = 0, mid = p->def, hi = 127;
        if (delta > 0)
            v = v < mid ? mid : hi;
        else
            v = v > mid ? mid : lo;
    } else {
        v = clamp(v + delta, 0, 127);
    }
    touched = i;
    if (v != fxp_v[g][i]) {
        fxp_v[g][i] = (u8)v;
        fxp_gen++;
        ins_edits++;
    }
}

/* rec.c smp_ui_pop, after ins_pop: 1 when the item is ours (it is dropped) */
int fxp_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int down = (flags & 1u) && !(flags & 0x10u);
    if (it[0] == IT_KEY) {
        if (code == K_FUNC) {
            if (flags & 8u)
                return 0;                       /* an auto-repeat */
            if (down) {
                armed = seen != 0 || fxp_visible();     /* FUNC went down on one of our pages */
            } else if (armed) {
                armed = 0;                      /* the tap: FUNC up with nothing between */
                if (seen) {
                    fxp_up = fxp_up == seen ? 0 : seen;
                    touched = -1;
                    smp_overlay_dirty = 1;
                }
            }
            return 0;                           /* FUNC goes on to stock, as ever */
        }
        armed = 0;                              /* any other key: FUNC is a modifier now */
        return 0;
    }
    if (it[0] == IT_KNOB) {
        armed = 0;
        if (chr_seen && code == CHR_PLACE + 1) {        /* the Chorus page's TYPE: a turn right JUNO, left STOCK */
            int v = (s8)it[8] > 0 ? 1 : (s8)it[8] < 0 ? 0 : chr_get();
            chr_set(v);
            chr_touched = 1;
            smp_overlay_dirty = 1;
            return 1;
        }
        if (fxp_visible() && code >= 1 && code <= 8 && !(fxp_up == PAGE_DELAY && code == 1)) {
            turn((int)code, (s8)it[8]);
            smp_overlay_dirty = 1;
            return 1;
        }
    }
    return 0;
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
}

#define TAG_X0 103                              /* the title bar's right end (stock's bar is y 54..63) */
#define TAG_Y0 54

/* the small tag, light digits on a dark box in the stock title bar: 1/2 or 2/2 */
static void tag(void *c, int n)
{
    fill(c, TAG_X0, TAG_Y0, 127, 63, 0);
    char s[4] = {(char)('0' + n), '/', '2', 0};
    WG_TEXT(c, 0x44508ED8u, TAG_X0 + 12, TAG_Y0 + 2, 2, "%s", s);   /* the grid's label font (page.c FONT) */
}

/* a place's value in its unit (md_page.c mu_fxp, dnfw.engines.units _fxp_units: 2026-11-13, the User: no bare
 * 0..127): SLEW ms, KNEE dB, INPT signed %, DIFF %; a place without one in % */
extern const char *mu_fxp(int page, int place, int k);

static const char *text(int page, int i, int v)
{
    static char b[8] __attribute__((section(".data")));
    const char *u = page == PAGE_DELAY || page == PAGE_REVERB ? mu_fxp(page - 1, i, v) : 0;   /* (0: JUNO's chorus MIX, a %) */
    if (u)
        return u;
    int pc = (v * 100 + 63) / 127, n = 0;
    if (pc >= 100)
        b[n++] = '1';
    if (pc >= 10)
        b[n++] = (char)('0' + (pc / 10) % 10);
    b[n++] = (char)('0' + pc % 10);
    b[n++] = '%';
    b[n] = 0;
    return b;
}

/* the Chorus page: TYPE at E; with JUNO, A and B relabelled MIX and MODE */
static void chorus_draw(void *c)
{
    int j = chr_get();
    fill(c, wg_x(CHR_PLACE) - 2, wg_y(CHR_PLACE), wg_x(CHR_PLACE) + 24, wg_y(CHR_PLACE) + 26, 0);
    wg_choice(c, CHR_PLACE, j ? "JUNO" : "STCK");
    wg_label(c, CHR_PLACE, "TYPE");
    if (j && !smp_values_held()) {
        wg_label(c, 0, "MIX");
        wg_label(c, 1, "MODE");
    }
}

/* page.c wr_screen, after stock's screen (and the other pages' dots) */
void fxp_draw(void *c)
{
    init();
    if (chr_seen)
        chorus_draw(c);
    if (fxp_up && fxp_up != seen)
        fxp_up = 0;                             /* stock moved to another page (or the TYPE is stock's) */
    if (!seen)
        return;
    if (!fxp_up) {
        tag(c, 1);
        return;
    }
    const struct fxp_param *p = table(fxp_up);
    int g = fxp_up - 1;
    fill(c, 18, 0, 127, 26, 0);                 /* the places (the bottom row's wide cell starts at x 20); the Delay's A (TIME) stays stock's */
    fill(c, fxp_up == PAGE_DELAY ? wg_x(1) - 2 : 22, 27, 127, 53, 0);
    for (int s = 0; s < 8; s++) {
        if (!p[s].label[0] || (fxp_up == PAGE_DELAY && s == 0))
            continue;
        wg_knob(c, s, fxp_v[g][s]);
        const char *vt = (smp_values_held() || s == touched) ? text(fxp_up, s, fxp_v[g][s]) : 0;
        wg_label(c, s, vt ? vt : p[s].label);
    }
                                                /* (2026-11-12, the User: no tag on page 2 "2/2": the page's own title says it) */
}
