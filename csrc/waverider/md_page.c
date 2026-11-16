/* PERC's pages drawn as the Machinedrum's main screen (docs/md.md, "The page", v0.20).
 *
 * Under the DN2's header (its title, and the value of a knob as it turns): v0.20..v0.43 drew
 * the Machinedrum's main screen here (the MD's knobs, the tempo, the machine line); v0.44
 * lays the page out as the DN2's own SYN pages are, bigger (see "v0.44" below).
 *
 * The small and symbol fonts are the Machinedrum's own,
 * read from the owner's MD OS when the build is made (dnfw.md.ui) and placed in RAM at
 * MDUI_LOAD by the mod; none of it is in this source. Without them (MDUI_LOAD does not
 * hold the blob) md_page_draw returns 0 and page.c draws the page as before.
 *
 *
 * Canvas: 128 x 64, y counting up from the bottom (the MD's own convention too).
 */
#include "wr_gen.h"
#include "widgets.h"                   /* 2026-11-09: stock's own widgets (docs/widgets.md) */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define GET_VALUE ((int (*)(void *, u32, u8 *))0x4006538E)
#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70)
#define RECORD(id) ((const int *)(0x401F83A4u + 60u * (id)))
#define FRAMES (*(volatile u32 *)0x4058F8D4u)                      /* 1,500 a second */
#define UI_TRACK (*(volatile u8 *)0x42432A6Cu)
#define MDUI ((const u8 *)MDUI_LOAD)
#define NAME_SHORT_OF(id) (*(const char **)(0x401F83A4u + 60u * (id) + 0x30u))

enum { SMALL, SYM, BIG };

/* csrc/modulation/moving.c: a modulated control's line, as on stock's pages (2026-11-12) */
extern void mv_cell(void *canvas, int x0, int y0, u32 id);
extern void mv_cell_span(void *canvas, int x0, int y0, u32 id, int lo, int hi);

static int ok(void)
{
    return MDUI[0] == 'M' && MDUI[1] == 'D' && MDUI[2] == 'U' && MDUI[3] == 'I'
           && (MDUI[4] << 8 | MDUI[5]) == MDUI_VERSION;
}

static void put(void *c, int x, int y, int on)
{
    if (x >= 0 && x < 128 && y >= 0 && y < 64)
        SET_PIXEL(c, x, y, on);
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int y = y0; y <= y1; y++)
        for (int x = x0; x <= x1; x++)
            put(c, x, y, on);
}

static const u8 *glyph(int font, int ch)
{
    if (ch < 32 || ch > 127)
        ch = '?';
    return MDUI + MDUI_FONT + MDUI_FONT_BYTES * font + 1 + MDUI_FONT_STRIDE * (ch - 32);
}

static int text_w(int font, const char *s, int n)
{
    int w = 0;
    for (int k = 0; k < n && s[k]; k++)
        w += glyph(font, (u8)s[k])[0] + 1;
    return w;
}

/* text from X, its bottom row at Y; LIT 0 cuts it out of a filled area. -> its width */
static int text(void *c, int font, int x, int y, const char *s, int n, int lit)
{
    int x0 = x, rows = MDUI[MDUI_FONT + MDUI_FONT_BYTES * font];
    for (int k = 0; k < n && s[k]; k++) {
        const u8 *g = glyph(font, (u8)s[k]);
        for (int col = 0; col < g[0]; col++)
            for (int r = 0; r < rows; r++)
                if (g[1 + col] >> r & 1)
                    put(c, x + col, y + r, lit);
        x += g[0] + 1;
    }
    return x - x0;
}

/* v0.34: FUNC held, within two seconds of the DSP's output guard wiping a voice: "V" + the
 * voice (1..16, as VOICE SETUP counts; 'A'..'G' for 10..16 in three characters) + where its
 * memory first went non-finite: D its delay lines, S its stream, X neither (the input or the
 * effects) -> 1; else 0. docs/timing-model.md: the unit says what poisons a voice */
static int blown_text(char *b)
{
    extern int smp_blown_recent(void);
    extern volatile u32 smp_blown_info, smp_blown_where;
    if (!smp_blown_recent())
        return 0;
    u32 t = smp_blown_info & 15u, w = smp_blown_where;
    b[0] = 'V';
    b[1] = t < 9 ? (char)('1' + t) : (char)('A' + t - 9);
    b[2] = w == 0xFFFFu ? 'X' : (w & 0x8000u) ? 'D' : 'S';
    b[3] = 0;
    return 1;
}

static int fmt_int(char *b, int v, int sign)
{
    int n = 0;
    if (v < 0) { b[n++] = '-'; v = -v; }
    else if (sign && v > 0) b[n++] = '+';
    char t[4];
    int k = 0;
    do { t[k++] = (char)('0' + v % 10); v /= 10; } while (v && k < 4);
    while (k)
        b[n++] = t[--k];
    b[n] = 0;
    return n;
}

/* a control's knob position 0..127, as the DSP reads it (dnfw.perc.live: the nearest of
 * the Machinedrum's 128) */
static int knob(void *view, u32 id)
{
    u8 flag;
    const int *r = RECORD(id);
    int lo = r[2] >> 8, top = (r[3] >> 8) - lo;
    int v = (GET_VALUE(view, id, &flag) >> 8) - lo;
    if (top <= 0) return 0;
    if (v < 0) v = 0;
    if (v > top) v = top;
    return (v * 127 + top / 2) / top;
}

/* v0.27: a p-locked control drawn as stock draws it, its cell inverted (owner's photo: a
 * trig held, its locked parameters lit). The stock getter's flag (0x4006538e's third
 * argument) is what the stock grid (0x40017498) tests to draw a cell highlighted. The
 * canvas, as 0x40113e70 reads it: +4 width, +8 height, +12 words a column, +16 the bits
 * (a column's words, bit 31 - (y & 31) of word y >> 5). */
static int locked(void *view, u32 id)
{
    u8 flag = 0;
    if (!id)
        return 0;
    (void)GET_VALUE(view, id, &flag);
    return flag != 0;
}

static void invert(void *c, int x0, int y0, int x1, int y1)
{
    const int *cv = (const int *)c;
    u32 *bits = (u32 *)cv[4];
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            if (x >= 0 && y >= 0 && x < cv[1] && y < cv[2] && y <= 53)
                bits[x * cv[3] + (y >> 5)] ^= 0x80000000u >> (y & 31);
}

/* v0.44 (owner, 2026-11-08: "bigger knobs, a bigger value font; no BPM, no >MNM, no
 * machine line"): the pages laid out as the DN2's own SYN pages are, for reading at a
 * glance. Under the DN2's header (y 54..63, its title: stock's, untouched):
 *
 *   left, x 0..30: the track box (inverted: TRK:nn and the machine's name) over LEV;
 *   right, x 32..127: two rows of four cells 24 wide, each its control (a knob of
 *     radius 8, or a choice's picture and its value) over its name, both names and values
 *     in stock's own grid font (0x4011573c with the font page.c's grid uses).
 *
 * A row is 27 high: the name at its bottom (from base + 2), the control above it (the
 * knob centred at base + 18). The top row's base is 27, the bottom row's 0. The FUNC-held
 * readout (DSP %, CPU %, free heap) is the system meter's, in the title bar's corner
 * (csrc/meter): drawn over stock's header while FUNC is held, never here. */
#define TEXT ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)   /* (1.11: 0x4011545c) */
#define FONT 0x44508ED8u                /* the grid's label font (page.c's FONT) */
#define CENTRED 2
/* 2026-11-09: the cells' geometry, knob, name and lit cell are stock's own (widgets.h; until
 * then drawn here: CELL_X 32, CELL_W 24, a radius-8 knob) */

/* the left column as stock draws it (2026-11-09, docs/widgets.md): the track box (stock's frame
 * for the track, NAME3 where stock writes SYN; the guard's V<n><where> while FUNC is held just
 * after it wiped a voice) and LEV (stock's fader; until 2026-11-10 "CPU" as its label while the DSP
 * left voices out for time, v0.30: now the title bar's DSP label, on every page, csrc/meter) */
static void left_panel(void *view, void *c, const char *name3)
{
    extern int smp_func_held;
    char v[4];
    if (smp_func_held && blown_text(v))
        name3 = v;
    u8 flag;
    wg_left_panel(c, UI_TRACK, name3, GET_VALUE(view, TRACK_LEVEL_ID, &flag), "LEV");
}

/* p-locked: the cell inverted, as stock lights it (its widget and label) */
static void wg_lit(void *c, int s)
{
    invert(c, wg_x(s) - 3, wg_y(s), wg_x(s) + 21, wg_y(s) + 26);
}

/* PAGE 0: the machine's first seven, TYPE; PAGE 1: AMD AMF EQF EQG / FLTF FLTW FLTQ, the machine's eighth
 * (2026-11-11, the User: the engine on page 1 knob H on every machine with engines) */
int md_page_draw(void *view, void *c, int page, int type)
{
    if (!ok() || page < 0 || page > 1 || type < 0 || type >= PERC_N)
        return 0;
    const u8 *mach = MDUI + MDUI_MACH + MDUI_MACH_BYTES * type;
    u32 mnib = (u32)mach[0] << 24 | (u32)mach[1] << 16 | (u32)mach[2] << 8 | mach[3], nib = mnib;
    if (page == 1)
        nib = MD_FX_NIBBLES;
    nib = (nib & ~15u) | (page == 0 ? 1u : (mnib & 15u));   /* H: TYPE always; the eighth where the machine has it */
    fill(c, 0, 0, 127, 53, 0);
    for (int s = 0; s < 8; s++) {
        int n = nib >> (28 - 4 * s) & 15, x0 = wg_x(s), base = wg_y(s);
        u32 id = wr_ids[page][s];
        if (!(n & 1) || !id)
            continue;
        const char *name = NAME_SHORT_OF(id);
        char vb[8];
        extern int smp_values_held(void);
        if (smp_values_held() && id != PERC_TYPE_ID) {     /* v0.35: SYN held: the value (O14) */
            fmt_int(vb, knob(view, id), 0);
            name = vb;
        }
        wg_label(c, s, name);
        if (id == PERC_TYPE_ID) {                       /* TYPE: the machine, not a knob */
            const char *syn = (const char *)mach + 4, *m = (const char *)mach + 7;
            WG_RECT(c, x0, base + 7, x0 + 18, base + 23, 1);
            TEXT(c, FONT, x0 + 9, base + 16, CENTRED, "%.3s", syn);
            text(c, SYM, x0 + (19 - text_w(SYM, m, 2)) / 2, base + 9, m, 2, 1);
        } else {
            wg_knob(c, s, knob(view, id));              /* 2026-11-09: stock's knob */
        }
        mv_cell(c, x0, base, id);                       /* 2026-11-12: the heard value's line (csrc/modulation) */
        if (locked(view, id))                           /* v0.27: p-locked, as stock lights it */
            wg_lit(c, s);
    }
    left_panel(view, c, (const char *)mach + 4);
    return 1;
}

/* -- v0.27: the Monomachine machines' page, drawn as the Monomachine draws it ---------------
 * (owner's screenshots of its manual, docs/mnm-pages-plan.md). The same screen as PERC's
 * (the Monomachine's and the Machinedrum's main screens are one design): the tempo, LEV, the
 * kit box (here the track and the machine's family), the machine line DPRO>WAVE; on the
 * right two rows of four cells, each its control over its name. A knob is the MD's knob. A
 * control with choices (PLAITS' and SOPHIE's MODL) is the same knob, the choice's name in place
 * of the control's (2026-11-09, the User: the Monomachine's own switch, grid, slide and meter
 * pictures, v0.27, were unusable and unreadable at this size). An unused place is left empty. */
/* Sized by their contents, checked against MNM_N: a machine added without its names would
 * otherwise leave a null pointer here, read as text (SOPHIE did, found in the emulator). */
/* v0.44: the machine's name in the track box: mnm_name_upper, generated (dnfw.waverider.pages) */

static int mnm_k(void *view, int j)             /* knob 0..127, as the DSP and page.c read it */
{
    u8 flag;
    int top = mnm_top[j];
    int v = (GET_VALUE(view, mnm_rid[j], &flag) >> 8) - mnm_lo[j];   /* j 0..15: page 2's from 8 */
    v = v < 0 ? 0 : v > top ? top : v;
    return (v * 254 + top) / (2 * top);
}

/* the knob as the page shows control J: page 2's choices as the DSP takes them, trunc(v / top x n) (the
 * knob's 128ths differ), as a knob whose (k n) >> 7 is that choice; the page and its popup both read this */
static int mnm_k_shown(void *view, int mi, int j)
{
    int k = mnm_k(view, j), n = mnm_choices[mi][j];
    if (j >= 8 && n && n != MNM_PCH) {
        u8 fl;
        int v = (GET_VALUE(view, mnm_rid[j], &fl) >> 8) - mnm_lo[j], top = mnm_top[j];
        v = v < 0 ? 0 : v > top ? top : v;
        k = (((v * n) / top) * 128 + 64) / n;
        if (k > 127) k = 127;
    }
    return k;
}

/* 2026-11-10 (the User: no parameter of ours shows a bare 0..127): a control's value in its unit, at most
 * four characters (the cell's label): dnfw.mnm.units, the curve through 17 points 8 knobs apart (the last
 * one at 127). Hz: NNHz, then 0.1k .. 9.9k, NNk; ms: NNms, then 0.1s .. 9.9s, NNs; hundredths of a Hz
 * (BEAT): .NNH, N.NH, then Hz as above; cents NNc, N.Nc; percent NN%, signed +NN%; semitones +1.5, +12 */
static int ucat(char *b, int n, int v)                  /* v >= 0, up to 3 digits */
{
    if (v >= 100) b[n++] = (char)('0' + v / 100 % 10);
    if (v >= 10) b[n++] = (char)('0' + v / 10 % 10);
    b[n++] = (char)('0' + v % 10);
    return n;
}

static const char *const gt_patn[16] = {"16TH", "8TH", "4TH", "HALF", "OFF8", "OF16", "DOT8", "DOT4",
                                        "TRN1", "TRN2", "TRN3", "TRN4", "GALP", "RGAL", "CLAV", "TRSL"};
static const char *const mode5[5] = {"LP12", "LP24", "BP", "HP", "NTCH"};
static const char *const juno3[3] = {"I", "II", "I+II"};
static const char *const gt_rate[8] = {"1/2", "1/4", "1/8", "1/8T", "1/16", "16T", "1/32", "1/64"};

/* No jump table (2026-11-11, MONOMACHINE): GCC turned the kind tests below into one, a table of offsets inside the
 * code; the build's ColdFire check (dnfw.patch.cbuild) reads the code by a linear sweep, which cannot tell such a
 * table from instructions, and once the tables after it moved it read gt_patn's address as a scale-8 move (a
 * misreading: the CPU never decodes it). Compares instead, so the code reads as what runs. */
__attribute__((optimize("no-jump-tables")))
static const char *unit_text_of(int kind, int curve, int k)
{
    static char ub[8] __attribute__((section(".data")));
    if (!(kind & 127))
        return 0;
    if ((kind & 0x80) && k == 0) {
        ub[0] = 'O'; ub[1] = 'F'; ub[2] = 'F'; ub[3] = 0;
        return ub;
    }
    kind &= 127;
    if (kind == MU_PATN)
        return gt_patn[(k * 16) >> 7];
    if (kind == MU_RATE)
        return gt_rate[(k * 8) >> 7];
    if (kind == MU_MODE)
        return mode5[(k * 5) >> 7];
    if (kind == MU_JUNO)                            /* JUNO's MODE (dnfw.inserts.design.JN_MODE_K) */
        return juno3[(k * 3) >> 7];
    if (kind == MU_VOIC) {                          /* CHOR's voices: 1 + trunc(3.99 p) */
        int vv = 1 + (k * 399 / 127) / 100;
        ub[0] = 'V'; ub[1] = (char)('0' + (vv > 4 ? 4 : vv)); ub[2] = 0;
        return ub;
    }
    if (kind == MU_OCT) {
        ub[0] = '-'; ub[1] = k < 64 ? '1' : '2'; ub[2] = 0;   /* 2026-11-11: -1 at the left, -2 right */
        return ub;
    }
    if (kind == MU_GLID) {                          /* 2026-11-11: GLID up to 5 minutes, exact a knob */
        int e = mnm_glid[curve][k > 127 ? 127 : k], n = 0;
#if DN2_STOCK_UNITS
        if (e == 0xFFFF) {                          /* a stock table's "never" (a decay that does not fall) */
            ub[0] = 'I'; ub[1] = 'N'; ub[2] = 'F'; ub[3] = 0;
            return ub;
        }
#endif
        if (e < 100) {
            n = ucat(ub, 0, e);
            ub[n++] = 'm'; ub[n++] = 's';
        } else if (e < 9950) {
            int t = (e + 50) / 100;                 /* tenths of a second */
            n = ucat(ub, 0, t / 10);
            ub[n++] = '.'; ub[n++] = (char)('0' + t % 10); ub[n++] = 's';
        } else if (e < 10595) {                     /* 10000 + tenths of a second: whole seconds to 59 */
            n = ucat(ub, 0, e < 10000 ? 10 : (e - 10000 + 5) / 10);
            ub[n++] = 's';
        } else {
            int t = (e - 10000 + 30) / 60;          /* tenths of a minute */
            n = ucat(ub, 0, t / 10);
            ub[n++] = '.'; ub[n++] = (char)('0' + t % 10); ub[n++] = 'm';
        }
        ub[n] = 0;
        return ub;
    }
    const short *cv = mnm_curves[curve];
    int i = k >> 3, den = i == 15 ? 7 : 8;
    int v = cv[i] + (cv[i + 1] - cv[i]) * (k - 8 * i) / den;       /* the curve's value */
    int n = 0;
    if (kind == MU_PCT) {
        n = ucat(ub, 0, (k * 100 + 63) / 127);
        ub[n++] = '%';
    } else if (kind == MU_SPCT) {
        int d = (k - 64) * 100 / 64;
        d = d > 99 ? 99 : d < -99 ? -99 : d;
        ub[n++] = d < 0 ? '-' : '+';
        n = ucat(ub, n, d < 0 ? -d : d);
        ub[n++] = '%';
    } else if (kind == MU_MS10) {                   /* tenths of a millisecond */
        if (v < 10) {
            ub[0] = '.'; ub[1] = (char)('0' + v); ub[2] = 'm'; ub[3] = 's'; ub[4] = 0;
            return ub;
        }
        v = (v + 5) / 10;                           /* ms */
        if (v < 100) {
            n = ucat(ub, 0, v);
            ub[n++] = 'm'; ub[n++] = 's';
        } else {
            int t = (v + 50) / 100;                 /* tenths of a second */
            n = ucat(ub, 0, t / 10);
            ub[n++] = '.'; ub[n++] = (char)('0' + t % 10); ub[n++] = 's';
        }
    } else if (kind == MU_ST10) {                   /* signed semitones in tenths: +1.5, then +12 */
        int a = v < 0 ? -v : v;
        ub[n++] = v < 0 ? '-' : '+';
        if (!a) {
            ub[n++] = '0';
        } else if (a < 95) {
            n = ucat(ub, n, a / 10);
            ub[n++] = '.'; ub[n++] = (char)('0' + a % 10);
        } else {
            n = ucat(ub, n, (a + 5) / 10);
        }
    } else if (kind == MU_PCTC) {
        n = ucat(ub, 0, v);
        ub[n++] = '%';
    } else if (kind == MU_DB) {
        if (v < 0) { ub[n++] = '-'; v = -v; }
        n = ucat(ub, n, v);
        ub[n++] = 'd'; ub[n++] = 'B';
    } else if (kind == MU_C) {
        n = ucat(ub, 0, k);
        ub[n++] = 'c';
    } else if (kind == MU_C10) {
        n = ucat(ub, 0, v / 10);
        ub[n++] = '.';
        ub[n++] = (char)('0' + v % 10);
        ub[n++] = 'c';
    } else {
        if (kind == MU_HZ100) {
            if (v < 100) {                              /* .NNH */
                ub[0] = '.'; ub[1] = (char)('0' + v / 10); ub[2] = (char)('0' + v % 10); ub[3] = 'H'; ub[4] = 0;
                return ub;
            }
            if (v < 1000) {                             /* N.NH */
                int t = (v + 5) / 10;
                ub[0] = (char)('0' + t / 10); ub[1] = '.'; ub[2] = (char)('0' + t % 10); ub[3] = 'H'; ub[4] = 0;
                return ub;
            }
            v = (v + 50) / 100;                         /* Hz */
            kind = MU_HZ;
        }
        if (kind == MU_HZ) {
            if (v < 100) {
                n = ucat(ub, 0, v);
                ub[n++] = 'H'; ub[n++] = 'z';
            } else if (v < 9950) {
                int t = (v + 50) / 100;                 /* tenths of a kHz */
                n = ucat(ub, 0, t / 10);
                ub[n++] = '.'; ub[n++] = (char)('0' + t % 10); ub[n++] = 'k';
            } else {
                n = ucat(ub, 0, (v + 500) / 1000);
                ub[n++] = 'k';
            }
        } else {                                        /* MU_MS */
            if (v < 100) {
                n = ucat(ub, 0, v);
                ub[n++] = 'm'; ub[n++] = 's';
            } else if (v < 9950) {
                int t = (v + 50) / 100;
                n = ucat(ub, 0, t / 10);
                ub[n++] = '.'; ub[n++] = (char)('0' + t % 10); ub[n++] = 's';
            } else {
                n = ucat(ub, 0, (v + 500) / 1000);
                ub[n++] = 's';
            }
        }
    }
    ub[n] = 0;
    return ub;
}

static const char *mnm_unit_text(int mi, int j, int k)
{
    return unit_text_of(mnm_unit[mi][j], mnm_unit_curve[mi][j], k);
}

/* the A2 filter machines' FLTR records (page.c): which 0..8 of FLT_UNIT_IDS, knob 0..127 */
const char *mu_flt(int w, int k)
{
    if (w < 0 || w >= (int)sizeof flt_unit)
        return 0;
    return unit_text_of(flt_unit[w], flt_unit_curve[w], k > 127 ? 127 : k < 0 ? 0 : k);
}

/* the inserts' knobs (csrc/inserts/ins.c, SYN held): type 0..13, knob 0..5, 7 the MIX; 0 a knob with no unit yet */
const char *mu_ins(int type, int knob, int k)
{
    if (type < 0 || type >= (int)(sizeof ins_unit / sizeof ins_unit[0]) || knob < 0 || knob > 7)
        return 0;
    return unit_text_of(ins_unit[type][knob], ins_unit_curve[type][knob], k > 127 ? 127 : k);
}

#if DN2_STOCK_UNITS
/* 2026-11-11 (the User: proper values on stock pages too, a build option at first): stock records' value texts
 * in their units (dnfw.mnm.units STOCK_UNITS). stu_poll (page.c wr_poll, every loop) puts ours on each listed
 * record whose formatter is stock's own (stu_stock: stock 1.12's address), so a record another part of ours
 * holds (a machine's, FDN8's) is left to it, and one handed back to stock's later gets ours again. The machines'
 * own records (STU_MACHINE_LO..HI) carry these texts only on a stock machine's track; on ours stock's text. */
#define STU_FMT(id) (*(void **)(0x401F83A4u + 60u * (id) + 0x34u))
extern int wr_track_ours(void);

static void stu_fmt(int w, int v, char *buf)
{
    int id = stu_ids[w], k = (v >> 8) & 0xFF;
    const char *t = 0;
    if (!(id >= STU_MACHINE_LO && id <= STU_MACHINE_HI && wr_track_ours()))
        t = unit_text_of(stu_unit[w], stu_unit_curve[w], k > 127 ? 127 : k);
    if (!t) {
        ((void (*)(int, char *))stu_stock[w])(v, buf);
        return;
    }
    int n = 0;
    while (t[n] && n < 7) {
        buf[n] = t[n];
        n++;
    }
    buf[n] = 0;
}
#define STU_DEF(w) static void stu_f##w(int v, char *b) { stu_fmt(w, v, b); }
STU_FNS(STU_DEF)
#define STU_REF(w) stu_f##w,
static void (*const stu_fns[STU_N])(int, char *) = {STU_FNS(STU_REF)};

void stu_poll(void)
{
    for (int w = 0; w < STU_N; w++)
        if ((u32)STU_FMT(stu_ids[w]) == stu_stock[w])
            STU_FMT(stu_ids[w]) = (void *)stu_fns[w];
}
#endif

static int mnm_choice_count(int n)
{
    return n == MNM_PCH ? mnm_pch_idx[127] + 1 : n;
}

static int mnm_choice_of(int n, int k)
{
    return n == MNM_PCH ? mnm_pch_idx[k > 127 ? 127 : k] : (k * n) >> 7;
}

static const char *mnm_value_text(int mi, int j, int c)
{
    int w = mnm_widget[mi][j];
    if (w == MW_SEMIS || w == MW_CENTS) {       /* 2026-11-09: PLAITS' TUNE (+7, -12, 0), FINE (+12c) */
        static char sg[6] __attribute__((section(".data")));
        int v = c - mnm_choices[mi][j] / 2;
        int k = fmt_int(sg, v, 1);              /* the User (build #3): semitones, not the note */
        if (w == MW_CENTS) {
            if (!v) { sg[0] = '+'; sg[1] = '0'; k = 2; }
            sg[k++] = 'c';
            sg[k] = 0;
        }
        return sg;
    }
    static char num[6] __attribute__((section(".data")));
    int n = mnm_choices[mi][j];
    if (n == MNM_WAVES || n == 2 * MNM_WAVES) {
        int w = (c & (MNM_WAVES - 1)) + 1;
        num[0] = 'S'; num[1] = (char)('0' + w / 10); num[2] = (char)('0' + w % 10); num[3] = 0;
        return num;
    }
    if (MNM_RETIRED(mi, j, c))                  /* 2026-11-09: shown as the one before (GRAN: WS) */
        c--;
    return mnm_choice_names[mnm_choice_at[mi][j] + c];
}

/* 2026-11-09: the list popup (popup.c) for a control whose choices are names (SOPHIE's, PLAITS'
 * MODL): the names in the knob's order, a RETIRED one (PLAITS' GRAN) left out, as the knob steps
 * past it. Not TUNE / FINE (numbers) nor a ROM wave's S01.. */
typedef const char *(*wpop_name_fn)(int i, int arg);
extern void wpop_offer(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg);

static int mnm_listed(int mi, int j)
{
    int w = mnm_widget[mi][j], n = mnm_choices[mi][j];
    return n && w != MW_KNOB && w != MW_EMPTY && w != MW_SEMIS && w != MW_CENTS
           && n != MNM_WAVES && n != 2 * MNM_WAVES;
}

static int mnm_retired_at(int mi, int j)        /* the retired choice, or -1 */
{
    int cnt = mnm_choice_count(mnm_choices[mi][j]);
    for (int c = 0; c < cnt; c++)
        if (MNM_RETIRED(mi, j, c))
            return c;
    return -1;
}

static const char *mnm_pop_name(int i, int arg)     /* arg: mi * MNM_J + j; i: a place in the list */
{
    int mi = arg / MNM_J, j = arg % MNM_J, r = mnm_retired_at(mi, j);
    int c = r >= 0 && i >= r ? i + 1 : i;
    return mnm_value_text(mi, j, c);
}

static const char *mnm_pop_tag(int i, int arg)      /* 2026-11-11: the tag beside a choice, as PERC's TYPE list; */
{                                                   /* arg as mnm_pop_name's: mi * MNM_J + j */
    int mi = arg / MNM_J, j = arg % MNM_J, r = mnm_retired_at(mi, j);
    int c = r >= 0 && i >= r ? i + 1 : i;
    extern const char *load_tag_mnm(int mi, int j, int c);     /* 2026-11-12: "N VOICES" when fewer than 16 fit */
    const char *v = load_tag_mnm(mi, j, c);
    if (v)
        return v;
    for (int k = 0; k < MNM_TAG_LISTS; k++)
        if (mnm_tag_list[k][0] == mi && mnm_tag_list[k][1] == j) {
            const char *t = mnm_choice_tags[mnm_tag_list[k][2] + c];
            return t[0] ? t : 0;
        }
    return 0;
}

/* PAGE's knobs (2026-11-11, the User: "on analog2, page 2, E and A are mixed up... popup shows for the
 * wrong knobs": this offered page 1's controls on every page, so on page 2 knob A opened WAVE's list
 * and page 2's own lists never opened) */
void mnm_pop_offer(void *view, int mi, int page)
{
    if (mi < 0 || mi >= MNM_N)
        return;
    int base = page > 0 && page < mnm_npages[mi] ? 8 * page : 0;
    for (int s = 0; s < 8; s++) {
        int j = mnm_order[mi][base + s];       /* 2026-11-11: the control drawn there (its record, the descriptor's) */
        if (!mnm_listed(mi, j))
            continue;
        int n = mnm_choices[mi][j], cnt = mnm_choice_count(n), ch = mnm_choice_of(n, mnm_k_shown(view, mi, j));
        int r = mnm_retired_at(mi, j);
        if (ch > cnt - 1)
            ch = cnt - 1;
        if (r >= 0) {                           /* the list without it; the knob there shows the one before */
            cnt--;
            if (ch >= r)
                ch--;
        }
        wpop_offer(s, mnm_labels[mi][j], cnt, ch, mnm_pop_name, mnm_pop_tag, mi * MNM_J + j);
    }
}

/* the header's value as a control turns, and the SYN-held cells, for the formatter swap (csrc/sampler/fmt.c
 * smp_formats): control J (0..15) of machine MI at knob K: its unit, or its choice's name; 0 for a stock text */
const char *mu_value(int mi, int j, int k)
{
    if (mi < 0 || mi >= MNM_N || j < 0 || j >= MNM_J)
        return 0;
    int w = mnm_widget[mi][j], n = mnm_choices[mi][j];
    if (w == MW_EMPTY)
        return 0;
    if (w == MW_KNOB || !n)
        return mnm_unit_text(mi, j, k);
    int cnt = mnm_choice_count(n), ch = mnm_choice_of(n, k);
    return mnm_value_text(mi, j, ch > cnt - 1 ? cnt - 1 : ch);
}

int mu_has(int mi, int j)
{
    if (mi < 0 || mi >= MNM_N || j < 0 || j >= MNM_J)
        return 0;
    int w = mnm_widget[mi][j];
    return w != MW_EMPTY && (mnm_unit[mi][j] & 127 ? 1 : (w != MW_KNOB && mnm_choices[mi][j] ? 1 : 0));
}

int mnm_page_draw(void *view, void *c, int mi, int page)
{
    if (!ok() || mi < 0 || mi >= MNM_N)
        return 0;
    fill(c, 0, 0, 127, 53, 0);
    int base = page > 0 && page < mnm_npages[mi] ? 8 * page : 0;
    for (int s = 0; s < 8; s++) {
        int j = mnm_order[mi][base + s];       /* 2026-11-11: the control drawn there (its record, the descriptor's) */
        int w = mnm_widget[mi][j];
        const char *name = mnm_labels[mi][j];
        if (w == MW_EMPTY || (name[0] == '-' && !name[1]))
            continue;
        int k = mnm_k_shown(view, mi, j), n = mnm_choices[mi][j];
        char vb[8];
        extern int smp_values_held(void);
        if (smp_values_held()) {                   /* v0.35: SYN held: the value (O14): a knob's */
            if (w == MW_KNOB || !n) {           /* number, a choice's name */
                const char *u = mnm_unit_text(mi, j, k);       /* 2026-11-10: in its unit */
                if (u) {
                    name = u;
                } else {
                    fmt_int(vb, k, 0);
                    name = vb;
                }
            } else {
                int cnt = mnm_choice_count(n), ch = mnm_choice_of(n, k);
                name = mnm_value_text(mi, j, ch > cnt - 1 ? cnt - 1 : ch);
            }
        }
        wg_label(c, s, name);
        /* 2026-11-09, stock's widgets (docs/widgets.md): a choice its text in stock's choice box
         * (MODL: SWRM, TUNE: +7, FINE: +28c), else the knob */
        if (w != MW_KNOB && n) {
            int cnt = mnm_choice_count(n), ch = mnm_choice_of(n, k);
            wg_choice(c, s, mnm_value_text(mi, j, ch > cnt - 1 ? cnt - 1 : ch));
        } else {
            wg_knob(c, s, k);
        }
        mv_cell_span(c, wg_x(s), wg_y(s), mnm_rid[j],   /* 2026-11-12: the heard value's line, across */
                     mnm_lo[j] << 8, (mnm_lo[j] + mnm_top[j]) << 8);   /* the knob's part of the record */
        if (locked(view, mnm_rid[j]))   /* p-locked, as stock lights it */
            wg_lit(c, s);
    }
    left_panel(view, c, mnm_name_short[mi]);
    return 1;
}
