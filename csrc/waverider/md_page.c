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
 * after it wiped a voice) and LEV (stock's fader; "CPU" as its label while the DSP leaves voices
 * out for time, v0.30) */
static void left_panel(void *view, void *c, const char *name3)
{
    extern int smp_func_held;
    extern int smp_skipped_any(void);
    char v[4];
    if (smp_func_held && blown_text(v))
        name3 = v;
    u8 flag;
    wg_left_panel(c, UI_TRACK, name3, GET_VALUE(view, TRACK_LEVEL_ID, &flag),
                  smp_skipped_any() ? "CPU" : "LEV");
}

/* p-locked: the cell inverted, as stock lights it (its widget and label) */
static void wg_lit(void *c, int s)
{
    invert(c, wg_x(s) - 3, wg_y(s), wg_x(s) + 21, wg_y(s) + 26);
}

/* PAGE 0: the machine's eight; PAGE 1: AMD AMF EQF EQG / FLTF FLTW FLTQ TYPE */
int md_page_draw(void *view, void *c, int page, int type)
{
    if (!ok() || page < 0 || page > 1 || type < 0 || type >= PERC_N)
        return 0;
    const u8 *mach = MDUI + MDUI_MACH + MDUI_MACH_BYTES * type;
    u32 nib = (u32)mach[0] << 24 | (u32)mach[1] << 16 | (u32)mach[2] << 8 | mach[3];
    if (page == 1)
        nib = MD_FX_NIBBLES;
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
    int v = (GET_VALUE(view, perc_param_ids[j], &flag) >> 8) - mnm_lo[j];
    v = v < 0 ? 0 : v > top ? top : v;
    return (v * 254 + top) / (2 * top);
}

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

int mnm_page_draw(void *view, void *c, int mi)
{
    if (!ok() || mi < 0 || mi >= MNM_N)
        return 0;
    fill(c, 0, 0, 127, 53, 0);
    for (int s = 0; s < 8; s++) {
        int w = mnm_widget[mi][s];
        const char *name = mnm_labels[mi][s];
        if (w == MW_EMPTY || (name[0] == '-' && !name[1]))
            continue;
        int k = mnm_k(view, s), n = mnm_choices[mi][s];
        char vb[8];
        extern int smp_values_held(void);
        if (smp_values_held()) {                   /* v0.35: SYN held: the value (O14): a knob's */
            if (w == MW_KNOB || !n) {           /* number, a choice's name */
                fmt_int(vb, k, 0);
                name = vb;
            } else {
                int cnt = mnm_choice_count(n), ch = mnm_choice_of(n, k);
                name = mnm_value_text(mi, s, ch > cnt - 1 ? cnt - 1 : ch);
            }
        }
        wg_label(c, s, name);
        /* 2026-11-09, stock's widgets (docs/widgets.md): a choice its text in stock's choice box
         * (MODL: SWRM, TUNE: +7, FINE: +28c), else the knob */
        if (w != MW_KNOB && n) {
            int cnt = mnm_choice_count(n), ch = mnm_choice_of(n, k);
            wg_choice(c, s, mnm_value_text(mi, s, ch > cnt - 1 ? cnt - 1 : ch));
        } else {
            wg_knob(c, s, k);
        }
        if (locked(view, perc_param_ids[s]))   /* p-locked, as stock lights it */
            wg_lit(c, s);
    }
    left_panel(view, c, mnm_name_short[mi]);
    return 1;
}
