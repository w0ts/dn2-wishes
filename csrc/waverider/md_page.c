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

static int slen(const char *s, int n)
{
    int k = 0;
    while (k < n && s[k])
        k++;
    return k;
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
#define CELL_X 32                       /* the first cell's left edge */
#define CELL_W 24
#define ROW_H 27                        /* a row: the top row's base is ROW_H, the bottom's 0 */
#define KNOB_R 8
#define KNOB_DY 18                      /* the knob's centre over its row's base */
#define NAME_DY 2                       /* the name's y over its row's base (stock's font reaches 2 below its y) */

static int cell_x(int s) { return CELL_X + CELL_W * (s & 3); }
static int row_base(int s) { return s < 4 ? ROW_H : 0; }

/* sin of 0..90 degrees, x 127 */
static const u8 SIN90[91] = {
    0, 2, 4, 7, 9, 11, 13, 15, 18, 20, 22, 24, 26, 29, 31, 33, 35, 37, 39, 41, 43, 46, 48,
    50, 52, 54, 56, 58, 60, 62, 64, 65, 67, 69, 71, 73, 75, 76, 78, 80, 82, 83, 85, 87, 88,
    90, 91, 93, 94, 96, 97, 99, 100, 101, 103, 104, 105, 107, 108, 109, 110, 111, 112, 113,
    114, 115, 116, 117, 118, 119, 119, 120, 121, 121, 122, 123, 123, 124, 124, 125, 125, 125,
    126, 126, 126, 127, 127, 127, 127, 127, 127};

static int isin(int deg)                /* sin(deg) x 127, any degree */
{
    deg %= 360;
    if (deg < 0) deg += 360;
    if (deg <= 90) return SIN90[deg];
    if (deg <= 180) return SIN90[180 - deg];
    if (deg <= 270) return -SIN90[deg - 180];
    return -SIN90[360 - deg];
}

static void line(void *c, int x0, int y0, int x1, int y1);

static void circle(void *c, int cx, int cy, int r)
{
    for (int x = 0, y = r, e = 1 - r; x <= y; x++) {
        put(c, cx + x, cy + y, 1); put(c, cx - x, cy + y, 1); put(c, cx + x, cy - y, 1); put(c, cx - x, cy - y, 1);
        put(c, cx + y, cy + x, 1); put(c, cx - y, cy + x, 1); put(c, cx + y, cy - x, 1); put(c, cx - y, cy - x, 1);
        if (e < 0) e += 2 * x + 3;
        else { e += 2 * (x - y) + 5; y--; }
    }
}

/* a knob of radius 8: its ring, a thick pointer from the centre (7 o'clock at 0, 5 o'clock
 * at 127, as stock's dials turn), a dot at the centre */
static void big_knob(void *c, int cx, int cy, int v)
{
    circle(c, cx, cy, KNOB_R);
    int deg = -135 + (v * 270 + 63) / 127;     /* 0 = straight up, clockwise */
    int dx = (isin(deg) * (KNOB_R - 2) + 63) / 127, dy = (isin(deg + 90) * (KNOB_R - 2) + 63) / 127;
    line(c, cx, cy, cx + dx, cy + dy);
    line(c, cx + (dy ? 1 : 0), cy + (dy ? 0 : 1), cx + dx + (dy ? 1 : 0), cy + dy + (dy ? 0 : 1));
    fill(c, cx - 1, cy - 1, cx + 1, cy + 1, 1);
}

static void cell_name(void *c, int s, const char *name)
{
    TEXT(c, FONT, cell_x(s) + CELL_W / 2, row_base(s) + NAME_DY, CENTRED, "%.4s", name);
}

static void cell_lit(void *c, int s)    /* p-locked: the cell inverted, as stock lights it */
{
    int b = row_base(s);
    invert(c, cell_x(s), b, cell_x(s) + CELL_W - 1, b + ROW_H - 1);
}

/* the left column: the track box (TRK:nn, the machine's name on one or two lines, or the
 * guard's V<n><where> while FUNC is held just after it wiped a voice) and LEV under it */
static void left_panel(void *view, void *c, const char *name)
{
    int t = UI_TRACK;
    fill(c, 0, 29, 30, 53, 1);
    char b[8] = {'T', 'R', 'K', ':', 0, 0, 0, 0};
    b[4] = (char)('0' + (t + 1) / 10);
    b[5] = (char)('0' + (t + 1) % 10);
    text(c, SMALL, (31 - text_w(SMALL, b, 6)) / 2, 46, b, 6, 0);
    extern int smp_func_held;
    char v[4];
    if (smp_func_held && blown_text(v)) {
        text(c, SMALL, (31 - text_w(SMALL, v, 3)) / 2, 38, v, 3, 0);
    } else {
        int len = slen(name, 12), cut = len;
        if (text_w(SMALL, name, len) > 29)     /* two lines, at the last space that fits */
            for (int k = len - 1; k > 0; k--)
                if (name[k] == ' ' && text_w(SMALL, name, k) <= 29) {
                    cut = k;
                    break;
                }
        if (cut == len) {
            text(c, SMALL, (31 - text_w(SMALL, name, len)) / 2, 38, name, len, 0);
        } else {
            const char *n2 = name + cut + 1;
            int l2 = len - cut - 1;
            text(c, SMALL, (31 - text_w(SMALL, name, cut)) / 2, 39, name, cut, 0);
            text(c, SMALL, (31 - text_w(SMALL, n2, l2)) / 2, 32, n2, l2, 0);
        }
    }
    /* LEV: the track's level, a bar between two rows of ticks; "CPU" in its place while
     * the DSP leaves voices out for time (v0.30) */
    extern int smp_skipped_any(void);
    if (smp_skipped_any()) {
        fill(c, 1, 20, 17, 26, 1);
        text(c, SMALL, 3, 21, "CPU", 3, 0);
    } else {
        text(c, SMALL, 3, 21, "LEV", 3, 1);
    }
    for (int y = 1; y <= 17; y += 4) {
        put(c, 2, y, 1); put(c, 3, y, 1);
        put(c, 15, y, 1); put(c, 16, y, 1);
    }
    u8 flag;
    const int *r = RECORD(TRACK_LEVEL_ID);
    int span = r[3] - r[2], lv = GET_VALUE(view, TRACK_LEVEL_ID, &flag) - r[2];
    int h = span > 0 ? lv * 17 / span : 0;
    if (h > 17) h = 17;
    if (h > 0)
        fill(c, 6, 1, 12, h, 1);
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
        int n = nib >> (28 - 4 * s) & 15, x0 = cell_x(s), base = row_base(s);
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
        cell_name(c, s, name);
        if (id == PERC_TYPE_ID) {                       /* TYPE: the machine, not a knob */
            const char *syn = (const char *)mach + 4, *m = (const char *)mach + 7;
            TEXT(c, FONT, x0 + CELL_W / 2, base + 20, CENTRED, "%.3s", syn);
            text(c, SYM, x0 + (CELL_W - text_w(SYM, m, 2)) / 2, base + 11, m, 2, 1);
        } else {
            big_knob(c, x0 + CELL_W / 2, base + KNOB_DY, knob(view, id));
        }
        if (locked(view, id))                           /* v0.27: p-locked, as stock lights it */
            cell_lit(c, s);
    }
    left_panel(view, c, perc_what_upper[type]);
    return 1;
}

/* -- v0.27: the Monomachine machines' page, drawn as the Monomachine draws it ---------------
 * (owner's screenshots of its manual, docs/mnm-pages-plan.md). The same screen as PERC's
 * (the Monomachine's and the Machinedrum's main screens are one design): the tempo, LEV, the
 * kit box (here the track and the machine's family), the machine line DPRO>WAVE; on the
 * right two rows of four cells, each its name over its control. A knob is the MD's knob; a
 * control with choices is drawn as the Monomachine draws it, its choice by name under it:
 *   MW_GRID   a box of rows the marker steps through, left to right, row by row (WAVE, CONS)
 *   MW_SLIDE  a bar sliding along a line (DDRW's WAV1/WAV2, DENS's WAVE)
 *   MW_VU     a needle at the bottom of a box, left to right (DENS's PCH2..4)
 *   MW_SWITCH a round switch, a line through it pointing at the position (SID's, WPRS, SYNC, V-SW)
 * An unused place (---, DENS's chorus) is left empty. */
/* Sized by their contents, checked against MNM_N: a machine added without its names would
 * otherwise leave a null pointer here, read as text (SOPHIE did, found in the emulator). */
/* v0.44: the machine's name in the track box (MACHINE SEL's, in capitals) */
static const char *const mnm_name_upper[] = {"SID 6581", "DPRO WAVE", "DPRO DDRW", "DPRO DENS", "VO-6", "SOPHIE"};
_Static_assert(sizeof mnm_name_upper / sizeof *mnm_name_upper == MNM_N, "mnm_name_upper: one per machine");

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
    static char num[6] __attribute__((section(".data")));
    int n = mnm_choices[mi][j];
    if (n == MNM_WAVES || n == 2 * MNM_WAVES) {
        int w = (c & (MNM_WAVES - 1)) + 1;
        num[0] = 'S'; num[1] = (char)('0' + w / 10); num[2] = (char)('0' + w % 10); num[3] = 0;
        return num;
    }
    return mnm_choice_names[mnm_choice_at[mi][j] + c];
}

static void line(void *c, int x0, int y0, int x1, int y1)
{
    int dx = x1 > x0 ? x1 - x0 : x0 - x1, dy = y1 > y0 ? y1 - y0 : y0 - y1;
    int sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx - dy;
    for (;;) {
        put(c, x0, y0, 1);
        if (x0 == x1 && y0 == y1)
            break;
        int e2 = 2 * err;
        if (e2 > -dy) { err -= dy; x0 += sx; }
        if (e2 < dx) { err += dx; y0 += sy; }
    }
}

static void mnm_widget_draw(void *c, int w, int x0, int ky, int ch, int count)
{
    int last = count > 1 ? count - 1 : 1;
    if (w == MW_GRID) {                         /* rows of dots; the marker steps along them */
        int rows = count > 24 ? 4 : 3, per = (count + rows - 1) / rows;
        int row = ch / per, col = ch % per;
        for (int r = 0; r < rows; r++) {
            int y = ky + 14 - 3 * r;
            for (int x = x0 + 3; x <= x0 + 16; x += 2)
                put(c, x, y, 1);
        }
        int mx = x0 + 3 + (per > 1 ? col * 12 / (per - 1) : 6), my = ky + 14 - 3 * row;
        fill(c, mx, my - 1, mx + 1, my + 1, 1);
    } else if (w == MW_SLIDE) {                 /* a bar along a line */
        for (int x = x0 + 2; x <= x0 + 17; x++)
            put(c, x, ky + 10, 1);
        int bx = x0 + 2 + ch * 15 / last;
        fill(c, bx, ky + 7, bx + 1, ky + 13, 1);
    } else if (w == MW_VU) {                    /* a meter's box, its needle from the bottom */
        for (int x = x0 + 2; x <= x0 + 17; x++)
            put(c, x, ky + 14, 1);
        fill(c, x0 + 2, ky + 11, x0 + 2, ky + 14, 1);
        fill(c, x0 + 17, ky + 11, x0 + 17, ky + 14, 1);
        for (int x = x0 + 4; x <= x0 + 15; x += 3)
            put(c, x, ky + 13, 1);
        int nx = x0 + 3 + ch * 13 / last;
        fill(c, nx, ky + 7, nx, ky + 12, 1);
    } else if (w == MW_SWITCH) {                /* a round switch, a line through it */
        static const signed char dir[5][2] = {{-3, 3}, {-1, 3}, {0, 3}, {1, 3}, {3, 3}};
        int cx = x0 + 10, cy = ky + 10;
        for (int x = 0, y = 4, e = 1 - 4; x <= y; x++) {          /* a circle, radius 4 */
            put(c, cx + x, cy + y, 1); put(c, cx - x, cy + y, 1); put(c, cx + x, cy - y, 1); put(c, cx - x, cy - y, 1);
            put(c, cx + y, cy + x, 1); put(c, cx - y, cy + x, 1); put(c, cx + y, cy - x, 1); put(c, cx - y, cy - x, 1);
            if (e < 0) e += 2 * x + 3;
            else { e += 2 * (x - y) + 5; y--; }
        }
        int d = count > 1 ? ch * 4 / last : 0;
        line(c, cx - dir[d][0], cy - dir[d][1], cx + dir[d][0], cy + dir[d][1]);
    }
}

int mnm_page_draw(void *view, void *c, int mi)
{
    if (!ok() || mi < 0 || mi >= MNM_N)
        return 0;
    fill(c, 0, 0, 127, 53, 0);
    for (int s = 0; s < 8; s++) {
        int x0 = cell_x(s), base = row_base(s);
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
        cell_name(c, s, name);
        if (w == MW_KNOB || !n) {
            big_knob(c, x0 + CELL_W / 2, base + KNOB_DY, k);
        } else {                                /* a choice: its picture over its value */
            int count = mnm_choice_count(n), ch = mnm_choice_of(n, k);
            if (ch > count - 1) ch = count - 1;
            mnm_widget_draw(c, w, x0 + 2, base + 11, ch, count);
            TEXT(c, FONT, x0 + CELL_W / 2, base + 11, CENTRED, "%.4s", mnm_value_text(mi, s, ch));
        }
        if (locked(view, perc_param_ids[s]))   /* p-locked, as stock lights it */
            cell_lit(c, s);
    }
    left_panel(view, c, mnm_name_upper[mi]);
    return 1;
}
