/* The SYN pages of our machines on the ColdFire: PERC (type 5, docs/perc.md),
 * RESONATOR (6) and CZ (7). (v0.45: the TYPE cell of PING's filter page went with PING.)
 *
 * The layout is Tonverk's Wavefinder page (User Manual OS 1.4.1, p. 94), on a screen of
 * the same size, drawn with our own widgets: encoders A..D are a strip above a picture,
 * E..H a strip below it, and each control is its label with a small indicator, not a
 * dial. (Waverider, type 5 until v0.11, drew its wave there; PERC draws its machine's
 * name.) `docs/waverider-m7-pages.md`, "M8.1".
 *
 * Entered from `wr_grid` (dnfw.waverider.pages) in place of the stock grid
 * `0x40017428(view, canvas)`, on one of our tracks only. It keeps the grid's own
 * tail: the level meter on the left (`view->vtable[184]`) and the page dots on
 * the right (`0x4006598a`). The encoders, the value line in the header, p-locks
 * and SAVE/LOAD are untouched: they go through the page descriptor's record ids,
 * which stay WaveTone's.
 *
 * Coordinates are the canvas's own: 128 x 64, y counting up from the bottom
 * edge (the SYN page's blits place cell row 0 at y 34..51). The header takes
 * the top ten rows, the level meter and track box the left 18 columns.
 *
 * One subject: drawing the page. What the controls are is `wr_gen.h`, generated
 * from dnfw.waverider.pages.
 */
#include "wr_gen.h"

/* DN2_LFO4 (a generation option, on by default since v0.56.2; dnfw.waverider.pages.lfo4_on): our code's side of lfo4 -- the
 * parameter table and the LFO state it moves (REC_BASE, LFO_LIVE, LFO_STRIDE), LFO4's stored values in the wishes
 * record (csrc/wishes/lfo4.c), the cascade with LFO4 both ways (csrc/modulation/cascade.c), and lfo4 in
 * dnfw.mods.SHIPPED (docs/lfo-112-port.md). Off until it has passed its gate steps (6m4); then main asks the User. */

typedef unsigned int u32;
typedef unsigned char u8;

#define GET_VALUE  ((int (*)(void *, u32, u8 *))0x4006538E)   /* (view, id, &flag) */
#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70)  /* (canvas, x, y, on) */
#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define PAGE_COUNT ((int (*)(void *))0x400173CA)
#define PAGE_DOTS  ((void (*)(void *, void *, int, int, int))0x4006598A)
#define IS_DIRTY   ((int (*)(void *))0x4011D5D4u)               /* screen: a redraw due? */
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)              /* screen: ask for one */
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)               /* 1,500 a second */
#define REC_REDRAW 60u                                          /* the recorder's: 25 a second */
#define PH_REDRAW 40u                                           /* v0.40: a playhead's, 37 a second at most */
#define FONT       0x44508ED8u                                  /* the grid's label font */
#define CENTRED    2                                            /* TEXT flag: x is the centre */

/* a parameter record: +8 min, +12 max, +16 default (TUN1: 0x400, 0x7c00, 0x4000) */
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))

/* W2: the record's name pointers, as every stock reader takes them (0x401f83a4 +
 * 60 id, then +0x28 the long name, +0x30 the short one: getLongName 0x400365c8,
 * getShortName 0x400372da, and the eleven places that read +0x30 directly, among
 * them the LFO destination list's row label 0x40105e52) */
#define NAME_LONG(id)  (*(const char **)(REC_BASE + 60u * (id) + 0x28u))
#define NAME_SHORT(id) (*(const char **)(REC_BASE + 60u * (id) + 0x30u))
#define KIT_POINTER (*(unsigned char *volatile *)0x800052A0u)
#define UI_TRACK    (*(volatile u8 *)0x42432A6Cu)

/* 2026-11-09: the list popup (popup.c): a list place offered as it is drawn */
typedef const char *(*wpop_name_fn)(int i, int arg);
extern void wpop_offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg);
extern int wpop_slot_of(int x0, int y0);

/* the strips: four columns of 25 across x 22..121 */
#define COL0  22
#define COLW  25
#define TOP_LABEL_Y 46
#define TOP_BAR_Y   43
#define BOT_BAR_Y   9
#define BOT_LABEL_Y 1
#define BAR_HALF    10

/* the wave, and the position bar under it */
#define WAVE_X  24
#define WAVE_CY 28
#define WAVE_AMP 11
#define POS_Y   15
#define CURSOR_Y (POS_Y - 2)    /* the LFO's position cursor: under the bar (owner) */
#define MARK    3

#define WR_WIDTH 96              /* the picture's width, from WAVE_X */

/* is the active track one of ours? (pages.is_wr's test: the active track's sound,
 * [0x800052a0] + 52 + 1163 t, has machine type 5..12 at +0xDE) -> 1 PERC,
 * 2 RESONATOR, 3 CZ, 4..8 the sample machines (types 8..12, docs/sampler.md), 0 none */
static int wr_active(void)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (t > 15 || !kit)
        return 0;
    signed char m = (signed char)kit[52u + 1163u * t + 0xDEu];
    return m >= 5 && m <= WR_TYPES_LAST ? m - 4 : 0;   /* v0.19: 13 SLICE; v0.26: the Monomachine's 14.. */
}

#if DN2_STOCK_UNITS
int wr_track_ours(void)                         /* the active track's machine is ours (md_page.c stu_fmt) */
{
    return wr_active() != 0;
}
#endif

/* v0.22: the LFOs' destination list (0x4003951e) asks each of the track's 101 slots'
 * record for its modulation mask (0x400dc472) and lists it if the LFO's bit is set. On a
 * track of ours, a WaveTone record our machine does not use (its name made "-" by
 * wr_names) answers 0, and is left out of the list. Every other record, and every other
 * track, as stock. */
#define STOCK_MASK ((u32 (*)(u32))0x400DC472u)

/* 2026-11-11 (owner: "Open 13 closed controls"; docs/modulation-more.md): the thirteen per-voice
 * records stock 1.12 ships with mask 0 are offered with an ordinary parameter's 0x1e00, to every
 * LFO and to MOD SETUP: PTIM, PORT, the amp envelope's DEL, MODE and RSET, and FM TONE's ATRG,
 * ARST, BTRG, BRST, PHRT, KSA, KSB1, KSB2. Only the list changes: the evaluator never reads the
 * mask, and on 1.11 the same thirteen, opened in the table, listed and modulated on the unit
 * (docs/modulation-mask.md, 2026-09-12). Every list goes through this lookup (the builder
 * 0x4003951e is the only reader of a non-DEST record's mask; the step code and the cascades read
 * the DEST records' bits 16..18 only). */
static const unsigned short wr_opened[] = {34, 35, 61, 73, 74, 221, 222, 224, 225, 226, 235, 236, 237};
#define WR_OPEN_MASK 0x1E00u

u32 wr_lfo_mask(u32 rec)
{
    if (rec >= 238u && rec <= 262u && wr_active()) {
        const char *sh = NAME_SHORT(rec);
        if (sh && sh[0] == '-' && sh[1] == 0)
            return 0;
    }
    u32 m = STOCK_MASK(rec);
    if (m == 0)
        for (unsigned k = 0; k < sizeof wr_opened / sizeof wr_opened[0]; k++)
            if (wr_opened[k] == rec)
                return WR_OPEN_MASK;
    return m;
}

/* TYPE's value (0..0x7f00) -> the machine, as the DSP reads it (dnfw.perc.program) */
static int perc_of(int v)
{
    v >>= 8;
    if (v < 0) v = 0;
    if (v > 127) v = 127;
    return (v * PERC_N) >> 7;
}

/* the machine the PERC page last read from TYPE (GET_VALUE, as the page draws it). v0.11
 * read the sound's target array instead, and on the instrument that did not follow TYPE:
 * every machine kept one set of names. */
static int perc_seen __attribute__((section(".data"))) = 0;

/* v0.35: the names follow the ACTIVE track's TYPE, read from its sound in the kit (the value
 * word at +0x14 + 2 slot, as smp_quant reads and the setter writes it). perc_seen alone was
 * the last PERC page drawn: on a stock page (the LFO's), TRK to another PERC track left the
 * first track's names on the DEST list and the header (B10, a tester, v0.30+). The page
 * draw still reads its own view's TYPE (GET_VALUE). */
static int perc_type(void)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (t > 15 || !kit)
        return perc_seen;
    return perc_of((int)*(volatile unsigned short *)(kit + 52u + 1163u * t + 0x14u + 2u * PERC_TYPE_SLOT));
}

/* While the active track is one of ours, WaveTone's records carry our names, so the LFO
 * and modulation destination lists, the LFO page's DEST field, the header's parameter
 * line and our own page all say what the record does on this machine; as soon as it is
 * not, the stock pointers go back. On a PERC track the parameters' names follow TYPE
 * (perc_short / perc_long). Only the two name pointers of the records in wr_named_ids are
 * written, and only on a change. The table is in RAM, and ACR0 (0x4007e020, set at
 * 0x40000564) leaves 0x40000000-0x47ffffff writable: its W bit is clear. */
static const char *stock_long[WR_NAMED] __attribute__((section(".data")));
static const char *stock_short[WR_NAMED] __attribute__((section(".data")));
static int names_on __attribute__((section(".data"))) = -1;

/* the active track's Monomachine place (KIND as is_wr answers it): a host's (MONOMACHINE by ENGN, DRUM by TYPE,
 * 2026-11-20: the word of its SEL in the track's sound, as perc_type reads TYPE's) its choice's place (fmt.c
 * smp_formats), any other machine's own; -1 for any other kind */
int wr_mnm_mi(int kind)
{
    int mi = mnm_index(kind);
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (mnm_host(mi) < 0 || t > 15 || !kit)
        return mi;
    return mnm_live(mi, *(volatile unsigned short *)(kit + 52u + 1163u * t + 0x14u + 2u * mnm_slot[mnm_sel_j(mi)]));
}

static void wr_names(void)
{
    int on = wr_active();
    /* 2026-11-11: MONOMACHINE: one set of names an engine; 2026-11-20: every host's place (DRUM's types): a place
     * past the types' its own row (wr_extra_*), else the kind's. PERC's keys are negative (its machine's) */
    int mi = on > 1 ? wr_mnm_mi(on) : -1;
    int x = mi >= MNM_N0 ? mi - MNM_N0 : -1;
    int key = on == 1 ? -2 - perc_type() : on + 64 * (x + 1);
    if (key == names_on)
        return;
    extern void smp_formats(int kind);
    smp_formats(on);                            /* v0.15: the sample machines' value text */
    for (int k = 0; k < WR_NAMED; k++) {
        u32 id = wr_named_ids[k];
        if (names_on == -1) {                   /* the first call: keep the stock pointers */
            stock_long[k] = NAME_LONG(id);
            stock_short[k] = NAME_SHORT(id);
        }
        const char *l = on ? (x >= 0 ? wr_extra_long[x][k] : wr_named_long[on - 1][k]) : 0;
        const char *sh = on ? (x >= 0 ? wr_extra_short[x][k] : wr_named_short[on - 1][k]) : 0;
        if (on == 1)
            for (int j = 0; j < 8; j++)
                if (perc_param_ids[j] == id) {
                    l = perc_longs[perc_long[-2 - key][j]];
                    sh = perc_short[-2 - key][j];
                }
        NAME_LONG(id) = l ? l : stock_long[k];
        NAME_SHORT(id) = sh ? sh : stock_short[k];
    }
    names_on = key;
}

#if FLT_SETS
static void px(void *c, int x, int y);
/* 2026-11-10: the A2 filter machines (src/dnfw/engines/analog2/filters/pages.py; PING's mechanism, removed in v0.45): while
 * the active track's filter is one of them (types 7..11, the byte at sound+0xDF), Multi-Mode's and the
 * filter envelope's records whose meaning they change carry their names; the stock pointers go back
 * when it is not. The same mechanism as wr_names, on records it does not touch. */
static const char *flt_stock_long[FLT_NAMED] __attribute__((section(".data")));
static const char *flt_stock_short[FLT_NAMED] __attribute__((section(".data")));
static int flt_on __attribute__((section(".data"))) = -2;   /* -2: not yet run */

/* the same records' formatters (the header's value as a knob turns, the SYN-held cells): in Hz, ms, %, the modes'
 * names (csrc/waverider/md_page.c mu_flt, dnfw.engines.units FLT_UNITS); stock's go back with the names */
extern const char *mu_flt(int w, int k);
static const unsigned short flt_fmt_ids[] = FLT_UNIT_IDS;
#define NFFMT ((int)(sizeof flt_fmt_ids / sizeof flt_fmt_ids[0]))
#define RECORD_FMT_AT(id) (*(void **)(REC_BASE + 60u * (id) + 0x34u))
static void *flt_stock_fmt[NFFMT] __attribute__((section(".data")));
static void flt_fmt(int w, int v, char *buf)
{
    int k = (v >> 8) & 0xFF;
    const char *t = mu_flt(w, k > 127 ? 127 : k);
    int n = 0;
    while (t && t[n] && n < 7) {
        buf[n] = t[n];
        n++;
    }
    buf[n] = 0;
}
#define FFN(w) static void flf##w(int v, char *b) { flt_fmt(w, v, b); }
FFN(0) FFN(1) FFN(2) FFN(3) FFN(4) FFN(5) FFN(6) FFN(7) FFN(8)
static void (*const flt_fmts[NFFMT])(int, char *) = {flf0, flf1, flf2, flf3, flf4, flf5, flf6, flf7, flf8};

/* -> which of flt_filters the active track's filter is (0..FLT_SETS-1), or -1 */
static int flt_active(void)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (t > 15 || !kit)
        return -1;
    signed char f = (signed char)kit[52u + 1163u * t + 0xDFu];
    for (int k = 0; k < FLT_SETS; k++)
        if (f == flt_filters[k])
            return k;
    return -1;
}

static void flt_names(void)
{
    int on = flt_active();
    if (on == flt_on)
        return;
    for (int k = 0; k < FLT_NAMED; k++) {
        u32 id = flt_named_ids[k];
        if (flt_on == -2) {                     /* the first call: keep the stock pointers */
            flt_stock_long[k] = NAME_LONG(id);
            flt_stock_short[k] = NAME_SHORT(id);
        }
        const char *l = on >= 0 ? flt_named_long[on][k] : 0;
        const char *sh = on >= 0 ? flt_named_short[on][k] : 0;
        NAME_LONG(id) = l ? l : flt_stock_long[k];
        NAME_SHORT(id) = sh ? sh : flt_stock_short[k];
    }
    for (int k = 0; k < NFFMT; k++) {
        if (flt_on == -2)
            flt_stock_fmt[k] = RECORD_FMT_AT(flt_fmt_ids[k]);
        RECORD_FMT_AT(flt_fmt_ids[k]) = on >= 0 ? (void *)flt_fmts[k] : flt_stock_fmt[k];
    }
    flt_on = on;
}

/* their MODE (record 38) and MOD2 (44) cells as the mode's name, a dot a choice under it */
static void flt_cell(void *view, void *canvas, int x0, int y0, u32 id)
{
    int ti = -1;
    for (int k = 0; k < FLT_TEXT_IDS; k++)
        if (id == flt_text_ids[k])
            ti = k;
    if (ti < 0)
        return;
    int set = flt_active();
    if (set < 0 || !flt_type_count[set][ti])
        return;
    for (int x = x0; x < x0 + 24; x++)
        for (int y = y0 + 8; y < y0 + 24; y++)
            SET_PIXEL(canvas, x, y, 0);
    u8 flag;
    const int *r = RECORD(id);
    int n = flt_type_count[set][ti], span = r[3] - r[2];
    int v = GET_VALUE(view, id, &flag) - r[2];
    int at = span > 0 ? v * n / span : 0;     /* as the DSP: trunc(v / span * n), the top clamped */
    if (at < 0) at = 0;
    if (at >= n) at = n - 1;
    TEXT(canvas, FONT, x0 + 12, y0 + 14, CENTRED, "%.4s", flt_type_text[set][ti][at]);
    for (int j = 0; j < n; j++) {
        int cx = x0 + 12 + (2 * j - (n - 1)) * 3;
        px(canvas, cx, y0 + 10);
        if (j == at) {
            px(canvas, cx, y0 + 11);
            px(canvas, cx + 1, y0 + 10);
            px(canvas, cx + 1, y0 + 11);
        }
    }
}
#endif

/* v0.22: the UI loop's draw of its screen (0x4011d60a(screen, canvas), at 0x4002e4ca),
 * then, while it is up, the RECORDER over all of it (rec.c, smp_page.c) */
#define SCREEN_DRAW ((void (*)(void *, void *))0x4011D60Au)
u32 wr_drawn_at __attribute__((section(".data"), aligned(4))) = 0;    /* the panel tick at the end of the last full draw */
void *wr_screen_obj __attribute__((section(".data"), aligned(4))) = 0;   /* v0.30: its views (rec.c) */
u32 wr_draws __attribute__((section(".data"), aligned(4))) = 0;   /* v0.40: the screen's draws (smp_page.c) */
void wr_screen(void *screen, void *canvas)
{
    wr_screen_obj = screen;
    wr_draws++;
    extern int rec_visible(void);
    extern void rec_screen_draw(void *canvas);
    extern int slc_visible(void);
    extern void slc_draw(void *canvas);
    extern int smp_fb_visible(void);
    extern void smp_fb_draw(void *canvas, int samp);
    extern int smp_samp_of(int track);
    extern unsigned int smp_samp_word(int track);
    extern int smp_list_visible(void);
    extern void smp_list_draw(void *canvas);
    extern void sl_screen(int phase, int covered);      /* parameter slides (csrc/slides) */
    extern void ins_title(void);
    extern void wpop_begin(void);
    extern void wpop_draw(void *canvas);
    wpop_begin();                               /* the list popup: offered as the page draws */
    { extern void fxp_begin(void); fxp_begin(); }   /* the send pages' second page (csrc/fxpage) */
    { extern void vm_begin(void); vm_begin(); }     /* PARA on the VOICE menu's B (csrc/para) */
    ins_title();                                /* the FX key's page names (csrc/inserts) */
    sl_screen(0, 0);
    extern void mv_begin(void);
    mv_begin();                                 /* moving controls: this draw's cells (csrc/modulation) */
    { extern void mxp_draw_begin(void); mxp_draw_begin(); }   /* the routes popup: the page's places anew (csrc/matrix) */
    { extern void ldp_draw_begin(void); ldp_draw_begin(); }   /* the DEST popup: knob D anew (csrc/matrix/dest_pop.c) */
    extern void mv_end(void *canvas, int drew);
    int drew = (IS_DIRTY(screen) & 0xFF) != 0;  /* stock draws only when its byte is set (isDirty: move.b, %d0's low byte only) */
    SCREEN_DRAW(screen, canvas);
    extern int sn_up(void);
    if (sn_up()) {                              /* v0.54: the stock NAME screen: nothing of ours over it */
        sl_screen(1, 1);
        mv_end(canvas, drew);                   /* moving controls: which lines may move alone */
        { extern void scope_end(void *canvas, int clean); scope_end(canvas, 0); }
        { extern void mxp_end(void *canvas, int clean); mxp_end(canvas, 0); }
        wr_drawn_at = *(volatile u32 *)0x466768B0u;   /* the panel tick (wr_poll's turns) */
        return;
    }
    extern int tn_visible(void);                /* v0.61: TUNING (csrc/sampler/tune.c) */
    extern void tn_draw(void *canvas);
    extern void tn_kb_draw(void *canvas);
    extern int pf_visible(void);                /* v0.69: PERFORM (csrc/sampler/perf.c) */
    extern void pf_draw(void *canvas);
    {   /* (2026-11-19: the scope covers TRIG page 2's SLD and SLEN too: E and F are its, not the slides') */
        extern int scope_visible(void);
        sl_screen(1, rec_visible() || slc_visible() || smp_fb_visible() || smp_list_visible() || scope_visible()
                     || tn_visible() || pf_visible());
    }
    if (pf_visible())                           /* v0.69: PERFORM (csrc/sampler/perf.c) */
        pf_draw(canvas);
    else if (tn_visible())                           /* (as REC and SLICE: no list popup, routes or DEST popup under it) */
        tn_draw(canvas);
    else if (rec_visible())
        rec_screen_draw(canvas);
    else if (slc_visible())
        slc_draw(canvas);
    else if (smp_fb_visible())                  /* v0.25: the folder browser (ASSIGN SAMPLE) */
        { extern int smp_fb_browse;             /* (browse only: no track's sample to mark) */
          smp_fb_draw(canvas, smp_fb_browse ? 0 : (int)smp_samp_word(UI_TRACK)); }   /* v0.65: the whole word (its bank) */
    else if (smp_list_visible())                /* v0.25: the sample list, over the title bar too */
        smp_list_draw(canvas);
    else {
        extern int ins_visible(void);
        extern void ins_draw(void *canvas);
        extern void ins_dots(void *canvas);
        extern int scope_visible(void);
        extern void scope_draw(void *canvas);
        extern void scope_dots(void *canvas);
        extern int env2_visible(void);
        extern void env2_draw(void *canvas);
        extern int msel_visible(void);
        extern void msel_draw(void *canvas);
        if (msel_visible()) {                   /* MACHINE SEL in two columns (csrc/msel, 2026-11-11) */
            wpop_begin();
            msel_draw(canvas);
        } else if (ins_visible()) {             /* the per-track inserts' page (csrc/inserts) */
            wpop_begin();                       /* (the stock page under it offers nothing of ours) */
            ins_draw(canvas);
        } else if (scope_visible()) {           /* the oscilloscope, over stock's TRIG page (csrc/scope) */
            wpop_begin();
            scope_draw(canvas);
        } else if (env2_visible()) {            /* AMP's ENV2 page (csrc/matrix/env2_page.c) */
            wpop_begin();
            env2_draw(canvas);
        } else {
            ins_dots(canvas);                   /* stock's FX page: FX 1/2's dots */
            scope_dots(canvas);                 /* stock's AMP page: AMP 1/2's dots */
            { extern void fxp_draw(void *canvas); fxp_draw(canvas); }   /* XDLY's and FDN8's page 1/2, 2/2 */
            { extern void vm_draw(void *canvas); vm_draw(canvas); }     /* PARA on the VOICE menu's B */
            tn_kb_draw(canvas);                 /* v0.61: KB SETUP's H slot (TUNE), when KB SETUP is on top */
            { extern void mix_draw(void *canvas); mix_draw(canvas); }   /* the MIXER pages' meters (csrc/meter/mixer.c) */
        }
        {   /* the item's icon in the title bar while it names the page (csrc/inserts/ins.c; not under a list of ours) */
            extern void ins_title_icon(void *canvas);
            extern int isel_up(void);
            if (!msel_visible() && !isel_up())
                ins_title_icon(canvas);
        }
        wpop_draw(canvas);                      /* the list popup, over the page */
        { extern void mxp_draw(void *canvas); mxp_draw(canvas); }   /* the routes popup, over everything of ours (csrc/matrix) */
        { extern void ldp_draw(void *canvas); ldp_draw(canvas); }   /* the DEST popup, over everything of ours (csrc/matrix) */
    }
    extern void mtr_draw(void *canvas);
    mtr_draw(canvas);                           /* the system meter's box (and the load labels), over everything */
    { extern int ovw_visible(void); extern void ovw_draw(void *canvas); extern void ovw_end(void *canvas, int drew);
      if (ovw_visible()) ovw_draw(canvas);     /* a page key's overview, held a second, over the meter's icons too
                                                 * (its own title bar carries its figures; csrc/inserts/ovw.c) */
      ovw_end(canvas, drew); }                 /* ... its next frames alone over this one (ovw.c) */
    mv_end(canvas, drew);                       /* moving controls: which lines may move alone, the frame complete */
    {   /* the scope's next frames may be drawn alone over this one if nothing of ours drew over it (csrc/scope) */
        extern void scope_end(void *canvas, int clean);
        extern int wpop_shown(void);
        extern int mxp_visible(void);
        extern int ovw_visible(void);
        extern int ldp_visible(void);
        scope_end(canvas, drew && !wpop_shown() && !mxp_visible() && !ldp_visible() && !ovw_visible());
        extern void mxp_end(void *canvas, int clean);   /* the routes popup's moving layer alone, likewise: only the
                                                         * meter's title-bar icons may come after it (csrc/matrix) */
        mxp_end(canvas, drew && !ovw_visible());
        extern int mtr_big;                     /* the mixer meters' updates alone over this frame (csrc/meter/mixer.c) */
        extern void mix_end(void *canvas, int clean);
        mix_end(canvas, drew && !wpop_shown() && !mxp_visible() && !ldp_visible() && !ovw_visible() && !mtr_big);
    }
    {   /* the DEST popup's next frames may be drawn alone over this one if nothing of ours drew over it */
        extern int ovw_visible(void);
        extern void ldp_end(void *canvas, int clean);
        ldp_end(canvas, !ovw_visible());
    }
    wr_drawn_at = *(volatile u32 *)0x466768B0u; /* the panel tick: a knob turning, the next full draw TURN_GAP after this one (wr_poll) */
}

/* ENV2's page is drawn over stock's AMP page in this draw: wr_screen reaches env2_draw (csrc/matrix/env2_page.c
 * env2_amp_draw: stock's knobs and shape are not drawn under it). The same tests, in the same order, as wr_screen's */
int wr_env2_covers(void)
{
    extern int sn_up(void), rec_visible(void), slc_visible(void), smp_fb_visible(void), smp_list_visible(void);
    extern int msel_visible(void), ins_visible(void), scope_visible(void), env2_visible(void);
    extern int tn_visible(void);
    return !sn_up() && !tn_visible() && !rec_visible() && !slc_visible() && !smp_fb_visible() && !smp_list_visible()
           && !msel_visible() && !ins_visible() && !scope_visible() && env2_visible();
}

/* cv_fill (2026-11-17, the User's CPU with notes held: our pages' clears were one stock SET_PIXEL call a pixel, 6,912 for
 * a page): a rectangle of stock's canvas set (ON bit 0 set) or cleared, a column word at a time. The canvas as stock's
 * SET_PIXEL 0x40113e70 reads it: +4 width, +8 height, +12 longs a column, +16 the bits; pixel (x, y) is bit
 * 31 - (y & 31) of long x * stride + (y >> 5). Clipped exactly as SET_PIXEL clips a pixel (0 <= x < width,
 * 0 <= y < height): the same pixels as calling it for every (x, y) of the rectangle, in any order. */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on)
{
    const int *h = (const int *)cv;
    int w = h[1], ht = h[2], stride = h[3];
    u32 *bits = (u32 *)h[4];
    if (x0 < 0)
        x0 = 0;
    if (y0 < 0)
        y0 = 0;
    if (x1 >= w)
        x1 = w - 1;
    if (y1 >= ht)
        y1 = ht - 1;
    if (x0 > x1 || y0 > y1)
        return;
    int k0 = y0 >> 5, k1 = y1 >> 5;
    for (int k = k0; k <= k1; k++) {
        u32 lo = k == k0 ? (u32)(y0 & 31) : 0u, hi = k == k1 ? (u32)(y1 & 31) : 31u;
        u32 m = (0xFFFFFFFFu >> lo) & ~(hi == 31u ? 0u : 0xFFFFFFFFu >> (hi + 1u));
        u32 *p = bits + x0 * stride + k;
        if (on & 1)
            for (int x = x0; x <= x1; x++, p += stride)
                *p |= m;
        else
            for (int x = x0; x <= x1; x++, p += stride)
                *p &= ~m;
    }
}

/* Knob turns drawn together (2026-11-18, the User: "High cpu is bad. Ui lags like crazy"; scratch/unit-now/cpu-spikes.md).
 * Stock's UI loop takes one queue item at a time, and every knob item asks for a full redraw; the redraw comes with
 * the loop's next tick item (0x4002e322: this test, the screen's draw 0x4011d60a, panel_diff). With the audio
 * interrupt at about 84.5 % of the ColdFire, a page's draw and present take about 40 ms of the UI's time: a fast turn's
 * items (one every four panel ticks) then each wait behind a whole draw, and the screen goes on moving 0.5-0.9 s after
 * the hand stops (the coupled emulator, scripts/emu_ui_turns.py: one knob item, one draw, the queue growing).
 * So, while a knob turns (a knob item taken within TURN_LIVE), the full redraw waits:
 *   - until TURN_GAP after the last full draw ended (40 ms between draws at least, plus the draw's own time);
 *   - while a knob's item already waits in the UI queue behind this pass (up to TURN_STALE after the last draw), so
 *     the items taken first are drawn together.
 * Only the drawing waits: every item is taken and its value set as stock sets it, at once. The screen's dirty byte stays
 * set, so a later pass draws (the loop's tick items keep coming), and the last value is always drawn. */
#define UI_QUEUE   ((volatile u32 *)0x4059E214u)   /* the UI queue (0x40001896 / 0x40001928): +4 items waiting, +16 the
                                                    * index mask, +20 the ring of item pointers, +28 the next read */
/* Timed by the panel module's tick (devtest.c: 0x466768b0, 121 a second, wrapping at 4,096), not by the audio frames:
 * the tick runs whatever the audio interrupt does (and in every emulator harness) */
#define PANEL_TICK (*(volatile u32 *)0x466768B0u)
#define TICKS(a, b) (((a) - (b)) & 0xFFFu)
#define TURN_LIVE  36u                          /* ticks: a knob item taken within 300 ms: a turn */
#define TURN_GAP   5u                           /* ticks: 41 ms from the end of a full draw */
#define TURN_STALE 10u                          /* ticks: drawn 83 ms after the last draw, items waiting or not */
u32 wr_turn_held __attribute__((section(".data"), aligned(4))) = 0;   /* redraws held back (the checks) */
static u32 turn_seq __attribute__((section(".data"))) = 0;    /* smp_knob_seq when last seen */
static u32 turn_at __attribute__((section(".data"))) = 0;     /* the tick it moved at */
static u32 turn_live __attribute__((section(".data"))) = 0;   /* a turn going on (cleared once TURN_LIVE has passed,
                                                               * looked at every UI pass: the tick's wrap never
                                                               * brings an old turn back) */

/* a knob turned within TURN_LIVE (csrc/modulation/moving.c: the lines' bookkeeping waits too) */
int wr_turning(void)
{
    extern u32 smp_knob_seq;                    /* rec.c smp_ui_pop: every knob item taken moves it */
    if (smp_knob_seq != turn_seq) {
        turn_seq = smp_knob_seq;
        turn_at = PANEL_TICK;
        turn_live = 1;
    }
    if (turn_live && TICKS(PANEL_TICK, turn_at) >= TURN_LIVE)
        turn_live = 0;
    return (int)turn_live;
}

/* a knob's item (type 1, code 1..8) waits in the UI queue */
static int knob_waiting(void)
{
    volatile u32 *q = UI_QUEUE;
    u32 n = q[1], mask = q[4], rd = q[7];
    const u32 *ring = (const u32 *)q[5];
    if (!ring || n > mask + 1u)
        return 0;
    for (u32 k = 0; k < n && k < 32u; k++) {
        const u8 *it = (const u8 *)ring[(rd + k) & mask];
        if (it && it[0] == 1 && !it[4] && !it[5] && !it[6] && it[7] >= 1 && it[7] <= 8)
            return 1;
    }
    return 0;
}

/* -> 1: this pass's redraw waits. Never more than TURN_PASSES passes in a row, whatever the tick says (should it ever
 * stand still, a turn's redraws still come, one pass in TURN_PASSES + 1) */
#define TURN_PASSES 4u
static u32 turn_row __attribute__((section(".data"))) = 0;    /* passes held in a row */
static int turn_hold(void)
{
    u32 since = TICKS(PANEL_TICK, wr_drawn_at);
    int hold = turn_row < TURN_PASSES
               && (since < TURN_GAP || (since < TURN_STALE && knob_waiting()));
    turn_row = hold ? turn_row + 1u : 0u;
    return hold;
}

/* the last UI pass held a full redraw back for a turn (csrc/modulation/moving.c mv_poll: the lines may go alone
 * meanwhile; BACK is still the frame on the glass) */
int wr_redraw_held(void)
{
    return turn_row != 0;
}

/* the UI loop's redraw test, as stock (and the names kept current, once a loop; and
 * v0.15: the sample link's +Drive copy loaded once the device is up) */
extern void smp_boot(void);

int wr_poll(void *screen)
{
    extern void rec_poll(void);
    extern int rec_visible(void);
    extern void jmp_poll(void);
    extern void smp_er_poll(void);
    extern void mtr_poll(void *screen);
    extern int mtr_big;
    mtr_poll(screen);                           /* the system meter, FUNC tapped then held, every page (csrc/meter) */
    { extern void ovw_poll(void *screen); ovw_poll(screen); }   /* the page keys' overviews, FX's tap (csrc/inserts/ovw.c) */
    extern void wpop_poll(void *screen);
    wpop_poll(screen);                          /* the list popup's redraws (popup.c; 2026-11-19: before the lines, so the
                                                 * polls that draw alone into BACK come last, together) */
    if (!mtr_big) {                             /* (2026-11-19: the meter's box covers the page body: nothing of ours is
                                                 * drawn alone into BACK under it; any key or turn takes it down first) */
        { extern void mv_poll(void *screen); mv_poll(screen); }   /* moving controls: a line moved (csrc/modulation) */
        { extern void scope_poll(void *screen); scope_poll(screen); }   /* the scope's frames, 15 a second */
        { extern void mxp_poll(void *screen); mxp_poll(screen); }   /* the routes popup: FUNC + long push, its redraws (csrc/matrix) */
        { extern void ldp_poll(void *screen); ldp_poll(screen); }   /* the DEST popup: the long NO, its frames (csrc/matrix) */
        { extern void mix_poll(void *screen); mix_poll(screen); }   /* the MIXER pages' meters (csrc/meter/mixer.c) */
    }
    smp_er_poll();                              /* v0.39: ERASE MOD DATA, a step a pass (erase.c) */
    { extern void wish_poll(void); wish_poll(); }   /* the wishes record's cells, read and written (csrc/wishes) */
    { extern void mx_poll(void); mx_poll(); }       /* the matrix's routes laid out for the frame (csrc/matrix) */
    { extern void ins_ui_poll(void); ins_ui_poll(); }   /* the inserts: MIX 0 kept running under a MIX route or lock (csrc/inserts) */
    smp_boot();
    jmp_poll();                                 /* DIRECT JUMP's setting, read and written (csrc/jump) */
    { extern void msel_poll(void); msel_poll(); }   /* LIVE SELECT: MACHINE SEL's resting cursor, FUNC + G (csrc/msel) */
    { extern void ins_title_poll(void); ins_title_poll(); }   /* a page name slid in: its icon with it (csrc/inserts/ins.c) */
    { extern void load_poll(void); load_poll(); }   /* the DSP load budget: each track's cost (csrc/load) */
    rec_poll();
    { extern void mono_poll(void); mono_poll(); }   /* 2026-11-11: a host's SEL turned (MONOMACHINE's ENGN, DRUM's TYPE): that place's start (rec.c) */
    { extern void as_poll(void); as_poll(); }       /* 2026-11-20: AMP ON/OFF's mask for the DSP (csrc/msel/ampsw.c) */
    { extern void hold_poll(void); hold_poll(); }   /* DRONE's HOLD latch (csrc/hold) */
    { extern int dt_poll(void); if (dt_poll()) SET_DIRTY(screen); }   /* the test channel's keys; a redraw turns the glass (csrc/devtest) */
    { extern void sm_poll(void); sm_poll(); }       /* 2026-11-21: SAFE MODE's healthy mark and STOP entry (csrc/safemode) */
    wr_names();
#if FLT_SETS
    flt_names();                                /* the A2 filter machines' FLTR names */
#endif
#if DN2_STOCK_UNITS
    { extern void stu_poll(void); stu_poll(); }    /* stock records' units, a build option (md_page.c) */
#endif
#if DN2_LFO4
    { extern void wish_lfo4_poll(void); wish_lfo4_poll(); }   /* LFO4's values from loaded records (csrc/wishes/lfo4.c) */
#endif
    extern void rvt_poll(void);
    rvt_poll();                                 /* FDN8: the Reverb page's TYPE and names (csrc/fdn8) */
    extern void dlt_poll(void);
    dlt_poll();                                 /* XDLY: the Delay page's TYPE and names (csrc/xdly) */
    extern void fxp_chorus_poll(void);
    fxp_chorus_poll();                          /* the chorus send's JUNO: DPTH / SPD names and values (csrc/fxpage) */
    /* the RECORDER's meter and state move: a redraw asked for as stock asks (the dirty
     * byte), 25 times a second. v0.15..v0.19 answered 1 here without setting the byte:
     * the loop then pushed its other buffer undrawn (0x4011d60a draws only when the byte
     * is set), and the page flashed between the last two screens it had (owner, v0.19) */
    static u32 rec_next __attribute__((section(".data"))) = 0;
    extern void slc_poll(void);
    extern int slc_visible(void);
    extern int slc_busy(void);
    slc_poll();
    static int slc_was __attribute__((section(".data"))) = 0;
    int slc = slc_visible() || slc_busy();      /* v0.23: SLICE's menus, and their notes */
    extern int smp_wants_redraw(void);          /* v0.25: a sample page's moving playhead */
    extern int smp_overlay_dirty;               /* v0.25: the sample list and the browser */
    extern int slc_state;                       /* v0.25: a SLICE/GRID menu opening or moving */
    static int slc_last __attribute__((section(".data"))) = 0;   /* on is drawn at once, not */
    if (smp_overlay_dirty || slc_state != slc_last) {            /* at the next redraw tick */
        smp_overlay_dirty = 0;
        slc_last = slc_state;
        SET_DIRTY(screen);
    }
    if ((rec_visible() || slc || slc_was) && (int)(FRAMES_NOW - rec_next) >= 0) {
        rec_next = FRAMES_NOW + REC_REDRAW;
        SET_DIRTY(screen);
        slc_was = slc;                          /* once more after it closes: the page again */
    }
    /* v0.40: a sample page's playhead (and SLICE / GRID's playing slice): redrawn as soon as
     * its column moves (smp_page.c), 37 a second at most; v0.25..v0.39: 25 a second, and
     * not at all once the page had gone 1.2 s undrawn (the owner: the marker lagged) */
    static u32 ph_next __attribute__((section(".data"))) = 0;
    if (smp_wants_redraw() && (int)(FRAMES_NOW - ph_next) >= 0) {
        ph_next = FRAMES_NOW + PH_REDRAW;
        SET_DIRTY(screen);
    }
    int turning = wr_turning();                 /* (every pass: a turn's start and end seen) */
    int dirty = IS_DIRTY(screen) & 0xFF;        /* (stock tests the low byte: tst.b %d0) */
    if (dirty && turning && turn_hold()) {     /* a knob turning: drawn with the items after it (above) */
        wr_turn_held++;
        return 0;
    }
    if (!turning)
        turn_row = 0;
    {   /* 2026-11-20 (the User: "10 per sec is fine"): on stock's MIXER, its redraws at most 10 a second, a key or a
         * knob at once (csrc/meter/mixer.c) */
        extern u32 mix_dirty(int dirty);
        return (int)mix_dirty(dirty);
    }
}

static void *method(void *obj, int offset)
{
    return *(void **)(*(char **)obj + offset);
}

static void px(void *c, int x, int y)
{
    SET_PIXEL(c, x, y, 1);
}

static void column(void *c, int x, int y0, int y1)
{
    if (y0 > y1) {
        int t = y0; y0 = y1; y1 = t;
    }
    for (int y = y0; y <= y1; y++)
        px(c, x, y);
}

/* A control's value under its label: a dotted track with the value filled in,
 * from the left, or from the centre for a control whose default is the middle
 * of its range (TUNE). A control of a few steps (TBL: 0..0x100) is drawn as
 * that many segments with the current one filled. */
static void indicator(void *c, int cx, int y, u32 id, int v)
{
    const int *r = RECORD(id);
    int lo = r[2], hi = r[3], def = r[4], span = hi - lo;
    if (span <= 0)
        return;
    if (v < lo) v = lo;
    if (v > hi) v = hi;
    int x0 = cx - BAR_HALF, x1 = cx + BAR_HALF;

    if (span % 0x100 == 0 && span / 0x100 < 8) {
        int n = span / 0x100 + 1, at = (v - lo) / 0x100;
        int w = (x1 - x0 + 2) / n;
        for (int k = 0; k < n; k++) {
            int a = x0 + k * w, b = a + w - 2;
            for (int x = a; x <= b; x++) {
                px(c, x, y);
                if (k == at)
                    px(c, x, y + 1);
            }
        }
        return;
    }

    for (int x = x0; x <= x1; x += 2)
        px(c, x, y);
    int at = x0 + (v - lo) * (x1 - x0) / span;
    int from = (2 * def == lo + hi) ? cx : x0;
    column(c, at, y, y + 1);
    for (int x = (from < at ? from : at); x <= (from < at ? at : from); x++)
        px(c, x, y + 1);
}

/* PERC's picture: the machine TYPE selects, its name and what it is, in the middle,
 * with its place among the machines as a row of dots under them */
static void perc_picture(void *c, void *view)
{
    u8 flag;
    int k = perc_of(GET_VALUE(view, PERC_TYPE_ID, &flag));
    TEXT(c, FONT, WAVE_X + WR_WIDTH / 2, 30, CENTRED, "%.6s", perc_machine[k]);
    TEXT(c, FONT, WAVE_X + WR_WIDTH / 2, 20, CENTRED, "%.11s", perc_what[k]);
    for (int j = 0; j < PERC_N; j++) {
        int x = WAVE_X + 12 + j * 3;
        px(c, x, 15);
        if (j == k) {
            px(c, x, 16);
            px(c, x + 1, 15);
            px(c, x + 1, 16);
        }
    }
}

/* v0.26: the Monomachine's machines (types 6, 7: docs/mnm.md), each one page of its eight
 * parameters on PERC's eight records. A parameter's knob (0..127) as the DSP reads it
 * (dnfw.perc.program: p = clamp((value >> 8) - lo, 0, top) / top, knob = p x 127, rounded);
 * an enumerated one shows its choice by name, as the Monomachine's screen does. */
static int mnm_knob_of(int w, int j)            /* the value word -> the knob */
{
    int v = (w >> 8) - mnm_lo[j];
    int top = mnm_top[j];
    v = v < 0 ? 0 : v > top ? top : v;
    return (v * 127 * 2 + top) / (2 * top);
}

static int mnm_knob(void *view, int j)
{
    u8 flag;
    return mnm_knob_of(GET_VALUE(view, perc_param_ids[j], &flag), j);
}

static const char *mnm_text_k(int m, int j, int k);

static const char *mnm_text(void *view, int m, int j)
{
    if (!mnm_choices[m][j])
        return 0;                                   /* a knob */
    return mnm_text_k(m, j, mnm_knob(view, j));
}

static const char *mnm_text_k(int m, int j, int k)  /* machine M's control J at knob K, by name */
{
    static char num[6] __attribute__((section(".data")));
    int n = mnm_choices[m][j];
    if (mnm_cont(n))                                /* v0.60: DYN's 1FRQ / 2FRQ: x.x / x.xx */
        return mnm_cont_text(n, k > 127 ? 127 : k, num);
    if (n == MNM_PCH || n == MNM_FLIST)             /* DENS's PCH2..4, FM+'s listed: the ROM's tables */
        return mnm_choice_names[mnm_choice_at[m][j] + mnm_choice(n, k)];
    int c = (k * n) >> 7;
    if (n == MNM_WAVES || n == 2 * MNM_WAVES) {     /* the ROM waves: S01..S32 (DDRW, DENS: the */
        c &= MNM_WAVES - 1;                         /* Digibank's 64, here the 32 twice) */
        num[0] = 'S'; num[1] = '0' + (c + 1) / 10; num[2] = '0' + (c + 1) % 10; num[3] = 0;
        return num;
    }
    if (MNM_RETIRED(m, j, c))                       /* 2026-11-09: shown as the one before */
        c--;
    return mnm_choice_names[mnm_choice_at[m][j] + c];
}

/* The sample machines (docs/sampler.md). A control's 0..top value, as the DSP reads it
 * (dnfw.sampler.program.ctl). */
static int smp_get(void *view, u32 id)
{
    u8 flag;
    int v = GET_VALUE(view, id, &flag) >> 8;
    const int *r = RECORD(id);
    int lo = r[2] >> 8, top = (r[3] >> 8) - lo;
    v -= lo;
    return v < 0 ? 0 : v > top ? top : v;
}

/* v0.48: STRT, LEN, LOOP's place across W from the whole word, 0..120.00 (dnfw.sampler.program.ctl_pos) */
static int smp_pos(void *view, u32 id, int w)
{
    u8 flag;
    int v = GET_VALUE(view, id, &flag);
    v = v < 0 ? 0 : v > 0x7800 ? 0x7800 : v;
    return v * w / 0x7800;
}

/* the pool's names: the sample link's (csrc/sampler/link.c) once a pool has been sent,
 * the built-in test sounds until then; 0 for a slot the pool does not hold (K from 1) */
extern int smp_count(void);
extern const char *smp_name(int k);

extern int smp_view_bank(void *view), smp_bank_count(int b);
static const char *sound_name(void *view, int k)  /* v0.65: in SAMP's bank */
{
    int b = smp_view_bank(view);
    int n = b ? smp_bank_count(b) : smp_count();
    if (n >= 0)
        return k <= n && k <= 127 ? smp_name(b * 128 + k - 1) : 0;
    return k <= SMP_SOUNDS ? smp_sound[k - 1] : 0;
}

static const char *smp_text(void *view, u32 id, int kind, const char *label)
{
    static char buf[6] __attribute__((section(".data")));
    if (id == SMP_PLAY_ID) {
        int k = smp_get(view, id) * 4 / 128;
        return smp_play[k > 3 ? 3 : k];
    }
    if (id == SMP_SAMP_ID) {
        int k = smp_get(view, id);
        if (k == 0)
            return "OFF";
        const char *nm = sound_name(view, k);
        if (nm && nm[0])
            return nm;
        buf[0] = '0' + k / 100; buf[1] = '0' + k / 10 % 10; buf[2] = '0' + k % 10; buf[3] = 0;
        return buf[0] == '0' ? buf + 1 : buf;
    }
    if (id == SMP_BARS_ID) {                    /* the DSP's index: the thresholds it compares */
        int v = smp_get(view, id), k = 0;
        while (k < 7 && v >= smp_bars_steps[k])
            k++;
        return smp_bars[k];
    }
    if (id == SMP_SEG_ID) {                     /* a segment, 1/n of a bar: 32 >> index (v0.18) */
        int v = smp_get(view, id), k = 0;
        while (k < 7 && v >= smp_seg_steps[k])
            k++;
        int n = 32 >> k;
        buf[0] = 'S';
        if (n >= 100) { buf[1] = '1'; buf[2] = '2'; buf[3] = '8'; buf[4] = 0; }
        else if (n >= 10) { buf[1] = '0' + n / 10; buf[2] = '0' + n % 10; buf[3] = 0; }
        else { buf[1] = '0' + n; buf[2] = 0; }
        return buf;
    }
    if (id == SMP_MODE_ID) {
        int k = smp_get(view, id) * 4 / 128;
        return smp_play[k > 3 ? 3 : k];
    }
    if (kind == SMP_GRID_KIND && id == SMP_GRID_ID) {
        int g = smp_get(view, id) / 24;
        int n = smp_grids[g > 4 ? 4 : g];
        buf[0] = 'G'; buf[1] = '0' + n / 10; buf[2] = '0' + n % 10; buf[3] = 0;
        if (n < 10) { buf[1] = '0' + n; buf[2] = 0; }
        return buf;
    }
    return label;
}

/* the picture: the machine and the sound in the middle; under them the sample as a bar,
 * the part that plays solid (STRT..STRT+LEN, or GRID's slice) and LOOP's point marked */
static void smp_picture(void *c, void *view, int kind)
{
    int k = smp_get(view, SMP_SAMP_ID);
    const char *snd = k == 0 ? "OFF" : sound_name(view, k);
    if (!snd)
        snd = "EMPTY";
    TEXT(c, FONT, WAVE_X + WR_WIDTH / 2, 30, CENTRED, "%.7s", smp_machine[SMP_IDX(kind)]);
    TEXT(c, FONT, WAVE_X + WR_WIDTH / 2, 21, CENTRED, "%.5s", snd);
    int w = WR_WIDTH - 8, x0 = WAVE_X + 4, a, b, loop = -1;
    if (kind == SMP_GRID_KIND) {
        int g = smp_get(view, SMP_GRID_ID) / 24, n = smp_grids[g > 4 ? 4 : g];
        int s = (smp_get(view, SMP_SLICE_ID) >> 1) & (n - 1);
        int len = (smp_get(view, SMP_SLEN_ID) >> 1) + 1;
        a = s * w / n;
        b = (s + len) * w / n;
        for (int j = 0; j <= n && n <= 32; j++)
            px(c, x0 + j * w / n, POS_Y + 2);
    } else if (kind == SMP_WERP_KIND) {         /* the whole sample, its segments ticked */
        int v = smp_get(view, SMP_SEG_ID), j = 0;
        while (j < 7 && v >= smp_seg_steps[j])
            j++;
        int n = 32 >> j;                        /* (per bar; the ticks are drawn up to 32) */
        a = 0;
        b = w;
        for (int i = 0; i <= n && n <= 32; i++)
            px(c, x0 + i * w / n, POS_Y + 2);
    } else {
        a = smp_pos(view, SMP_STRT_ID, w);     /* v0.48: the fine word (fmt.c smp_fine) */
        b = a + smp_pos(view, SMP_LEN_ID, w);
        loop = smp_pos(view, SMP_LOOP_ID, w);
    }
    if (b > w) b = w;
    for (int x = 0; x <= w; x += 2)
        px(c, x0 + x, POS_Y);
    for (int x = a; x <= b; x++) {
        px(c, x0 + x, POS_Y);
        px(c, x0 + x, POS_Y + 1);
    }
    if (loop >= 0) {
        int pmode = smp_get(view, SMP_PLAY_ID) * 4 / 128;
        if (pmode == 1 || pmode == 2)               /* REVL, FWDL: the loop point */
            column(c, x0 + loop, POS_Y - 2, POS_Y + 3);
    }
}

/* Every cell widget of a stock page is drawn by 0x4006448a(view, canvas, x, y, id, ...),
 * and as each one finishes (wr_cell_tail) this is told which: parameter slides draw their
 * marks there, and a stock list offers the list popup (popup_stock.c). (Until v0.44 it also drew
 * PING's TYPE cell as a name; v0.45: PING removed.) */
void wr_cell(void *view, void *canvas, int x0, int y0, u32 id)
{
    extern void sl_cell(void *view, void *canvas, int x, int y, u32 id);
    sl_cell(view, canvas, x0, y0, id);          /* parameter slides: SLD/SLEN on TRIG page 2 */
    extern void rvt_cell(void *view, void *canvas, int x, int y, u32 id);
    rvt_cell(view, canvas, x0, y0, id);         /* FDN8: the Reverb page's TYPE (csrc/fdn8) */
    extern void dlt_cell(void *view, void *canvas, int x, int y, u32 id);
    dlt_cell(view, canvas, x0, y0, id);         /* XDLY: the Delay page's TYPE (csrc/xdly) */
    extern void fxp_cell(u32 id);
    fxp_cell(id);                               /* the Chorus page is up (its TYPE, csrc/fxpage) */
#if FLT_SETS
    flt_cell(view, canvas, x0, y0, id);         /* the A2 filter machines' MODE, MOD2 (2026-11-10) */
#endif
    extern void wpop_stock_cell(void *view, int x0, int y0, u32 id, int ours);
    wpop_stock_cell(view, x0, y0, id, id == 122u || id == 131u);   /* a stock list: the popup (popup_stock.c) */
    extern void mxp_cell(int x0, int y0, u32 id);
    mxp_cell(x0, y0, id);                       /* the routes popup: which parameter each knob turns (csrc/matrix) */
    extern void ldp_cell(int x0, int y0, u32 id);
    ldp_cell(x0, y0, id);                       /* the DEST popup: an LFO's DEST on knob D (csrc/matrix) */
    extern void mv_cell(void *canvas, int x0, int y0, u32 id);
    mv_cell(canvas, x0, y0, id);                /* moving controls: the heard value's line (csrc/modulation) */
}

/* the arrows (popup.c wpop_arrow): TYPE D machines on, the middle of its band of the knob (perc_of's inverse) */
typedef void (*wpop_move_fn)(int d, int arg);
extern void wpop_offer_mv(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg,
                          wpop_move_fn move);
extern int smp_param_put(u32 id, int value, int click);   /* rec.c */

static void perc_move(int d, int arg)
{
    (void)arg;
    int to = perc_type() + d;
    to = to < 0 ? 0 : to >= PERC_N ? PERC_N - 1 : to;
    smp_param_put(PERC_TYPE_ID, ((to * 128 + 64) / PERC_N) << 8, 0);
}

static const char *perc_name(int i, int arg)
{
    (void)arg;
    return perc_machine[i];
}

static const char *perc_tag(int i, int arg)
{
    extern const char *load_tag_md(int i);      /* 2026-11-12: "N VOICES" when fewer than 16 fit (csrc/load) */
    const char *v = load_tag_md(i);
    (void)arg;
    return v ? v : perc_what_upper[i];
}

void wr_page_draw(void *view, void *canvas)
{
    int page = ((int (*)(void *))method(view, 132))(view);
    int kind = wr_active();
    int mi = mnm_index(kind);                   /* v0.26: a Monomachine machine's: one page */
    int mnm = mi >= 0;
    if (mnm && mnm_host(mi) >= 0) {            /* 2026-11-11: MONOMACHINE: its engine's page (ENGN, as the page */
        u8 flag;                                /* draws it), as PERC's follows TYPE; 2026-11-20: DRUM's by TYPE */
        mi = mnm_live(mi, GET_VALUE(view, mnm_rid[mnm_sel_j(mi)], &flag));
    }
    int smp = SMP_IDX(kind) >= 0;   /* a sample machine's (v0.44: BOUNCE's kind 13 too) */
    if (page < 0 || page >= (smp ? 2 : mnm ? mnm_npages[mi] : WR_PAGES))   /* 2026-11-10: DRONE, ANALOG2: 2 */
        page = 0;
    if (kind == 1) {                            /* PERC: the names TYPE has now */
        u8 flag;
        perc_seen = perc_of(GET_VALUE(view, PERC_TYPE_ID, &flag));
    }
    wr_names();
    if (kind == 1)                              /* TYPE: the list popup (popup.c) */
        for (int s = 0; s < 8; s++)
            if (wr_ids[page][s] == PERC_TYPE_ID)
                wpop_offer_mv(s, "TYPE", PERC_N, perc_seen, perc_name, perc_tag, 0, perc_move);
    if (mnm) {                                  /* MODL ..: the list popup (md_page.c) */
        extern void mnm_pop_offer(void *view, int mi, int page);
        mnm_pop_offer(view, mi, page);
    }
    if (kind == 1) {                            /* v0.20: the Machinedrum's own screen */
        extern int md_page_draw(void *view, void *canvas, int page, int type);
        if (md_page_draw(view, canvas, page, perc_seen))
            return;
    }

    if (smp) {                                  /* the DT2's SRC pages 1 and 2 (v0.22: the recorder is FUNC + VOICE) */
        extern void smp_page_draw(void *view, void *canvas, int kind, int wave);
        smp_page_draw(view, canvas, kind, page == 1);
        ((void (*)(void *, void *, int))method(view, 184))(view, canvas, 0);
        int n = PAGE_COUNT(view);
        if (n > 1)
            PAGE_DOTS(view, canvas, n, page, 7);
        return;
    }
    if (mnm) {                                  /* v0.27: the Monomachine's own screen */
        extern int mnm_page_draw(void *view, void *canvas, int mi, int page);
        if (mnm_page_draw(view, canvas, mi, page)) {
            if (mnm_npages[mi] > 1)             /* 2026-11-10: page 2's dots */
                PAGE_DOTS(view, canvas, mnm_npages[mi], page, 7);
            return;
        }
    }
    if (mnm) {                                  /* the Monomachine's grid of eight (no MD OS read) */
        extern void smp_knob_page(void *view, void *canvas, const unsigned short *ids,
                                  const char *const *labels, const char *const *texts);
        const char *labels[8], *texts[8];
        for (int i = 0; i < 8; i++) {
            labels[i] = mnm_labels[mi][i];
            texts[i] = mnm_text(view, mi, i);
        }
        smp_knob_page(view, canvas, perc_param_ids, labels, texts);
        ((void (*)(void *, void *, int))method(view, 184))(view, canvas, 0);
        int n = PAGE_COUNT(view);
        if (n > 1)
            PAGE_DOTS(view, canvas, n, page, 7);
        return;
    }
    if (smp)
        smp_picture(canvas, view, kind);
    else
        perc_picture(canvas, view);

    for (int i = 0; i < 8; i++) {
        int top = i < 4;
        int cx = COL0 + COLW * (i & 3) + COLW / 2;
        u32 id = smp ? smp_ids[SMP_IDX(kind)][i] : wr_ids[page][i];
        const char *label = smp ? "-" : wr_labels[page][i];
        if (id)
            label = NAME_SHORT(id);             /* PERC, samples: the name wr_names gave the record */
        if (smp && id)
            label = smp_text(view, id, kind, label);
        extern int smp_values_held(void);
        char vb[32];
        if (smp_values_held() && id) {             /* v0.35: SYN held: the value (O14) */
            u8 fl;
            vb[0] = 0;
            ((void (*)(int, char *))(*(void **)(REC_BASE + 60u * id + 0x34u)))(GET_VALUE(view, id, &fl), vb);
            vb[6] = 0;
            label = vb;
        }
        TEXT(canvas, FONT, cx, top ? TOP_LABEL_Y : BOT_LABEL_Y, CENTRED, "%.6s", label);
        if (!id || (label[0] == '-' && !label[1]))
            continue;                           /* an empty place, or a parameter this machine lacks */
        u8 flag;
        int set = GET_VALUE(view, id, &flag);
        indicator(canvas, cx, top ? TOP_BAR_Y : BOT_BAR_Y, id, set);
    }

    /* the stock grid's own tail: the level meter, then the page dots */
    ((void (*)(void *, void *, int))method(view, 184))(view, canvas, 0);
    int n = PAGE_COUNT(view);
    if (n > 1)
        PAGE_DOTS(view, canvas, n, page, 7);
}

/* -- 2026-11-17: the SYN and FLTR overviews (csrc/inserts/ovw_draw.c): each track's machine and engine by name, as its
 * sound holds them (the engine as the machine's page names it) ------------------------------------------------------ */
static const char *const ovw_mach4[] = {"FMT", "WAV", "FMD", "SWR", "MID", "", "", "", "ONE", "WRP", "STR", "RPT",
                                        "GRD", "SLC", "", "", "", "FLX"};   /* dnfw.overviews.MACHINE4 */

static int ovw_word(int t, int slot)
{
    return *(volatile unsigned short *)(KIT_POINTER + 52u + 1163u * (u32)t + 0x14u + 2u * (u32)slot);
}

/* track T's Monomachine-style control J by name (its machine's place MI), 0 a knob */
static const char *ovw_choice(int t, int mi, int j)
{
    if (!mnm_choices[mi][j])
        return 0;
    return mnm_text_k(mi, j, mnm_knob_of(ovw_word(t, mnm_slot[j]), j));
}

void wr_ovw_names(int t, const char **mach, const char **eng)
{
    static char md[2][4] __attribute__((section(".data")));
    *mach = *eng = 0;
    if (!KIT_POINTER || t < 0 || t > 15)
        return;
    int ty = (signed char)KIT_POINTER[52u + 1163u * (u32)t + 0xDEu];
    if (ty < 0)
        return;
    if (ty == 5) {                              /* MACHINEDRUM: its machine, "TRX-BD" as TRX over BD */
        const char *n = perc_machine[perc_of(ovw_word(t, PERC_TYPE_SLOT))];
        int i = 0, k = 0;
        while (n[i] && n[i] != '-' && i < 3)
            md[0][i] = n[i], i++;
        md[0][i] = 0;
        if (n[i] == '-')
            i++;
        while (n[i] && k < 3)
            md[1][k++] = n[i++];
        md[1][k] = 0;
        *mach = md[0];
        *eng = md[1];
        return;
    }
    int mi = mnm_index(ty - 4);
    if (mi >= 0) {                              /* ours: MACHINE SEL's short name, the engine its list names */
        int live = mnm_live(mi, ovw_word(t, mnm_slot[mnm_sel_j(mi)]));
        *mach = mnm_name_short[mi];
        if (mnm_host(mi) >= 0)                  /* a host: its SEL's choice (MONOMACHINE's engine, DRUM's type) */
            *eng = ovw_choice(t, live, mnm_sel_j(mi));
        else if (mi == LOAD_MI_PLAITS)
            *eng = ovw_choice(t, mi, LOAD_J_PLAITS);
        else if (mi == LOAD_MI_SOPHIE)
            *eng = ovw_choice(t, mi, LOAD_J_SOPHIE);
        else if (mi == LOAD_MI_A2)
            *eng = ovw_choice(t, mi, LOAD_J_A2);
        return;
    }
    if (ty < (int)(sizeof ovw_mach4 / sizeof ovw_mach4[0]))
        *mach = ovw_mach4[ty];
}

const char *wr_ovw_flt2(int t)                  /* ANALOG 2's own FLT2 on track T, 0 on any other machine */
{
    if (!KIT_POINTER || t < 0 || t > 15)
        return 0;
    int ty = (signed char)KIT_POINTER[52u + 1163u * (u32)t + 0xDEu];
    int mi = ty >= 0 ? mnm_index(ty - 4) : -1;
    return mi >= 0 && mi == LOAD_MI_A2 ? ovw_choice(t, mi, LOAD_J_A2) : 0;
}
