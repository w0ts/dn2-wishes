/* The system meter (docs/meter.md), OS 1.12: while FUNC is held, on every page, a corner
 * reads the DSP's load, the ColdFire's load and the free ColdFire heap:
 *
 *     D42   C61   M9      (each figure over a bar of 16 px, filled to it; D and C with a
 *     ####| ###|  #       tick at their peak over the last 3 s)
 *
 * - D: the DSP's load in percent, the last half second's peak (link.c smp_dsp_load, from
 *   the SHARC's idle packets, v0.32); "--" while none came in the last second.
 * - C: the ColdFire's load in percent over the last half second: 1 - (idle - ISR inside
 *   idle) / elapsed, from hooks.S's counters (usbprobe's method, measured on the unit).
 * - M: the main buddy heap's used share in percent: 1 - free / total. Free is walked under
 *   the heap's own lock as digihealth walks it (sysinfo.s: base of 16-byte units at +4,
 *   the free-list heads at +0xc, the highest order at +0x10; a block counted only when
 *   aligned to its order and its last word is its size, a link followed only through an
 *   intact header); the total is the descriptor's +0x14, in units (stock 1.12: 0x200000,
 *   32 MB, = 2^(the top order 21); measured in the emulator).
 *
 * Nothing is drawn, and nothing walked, while FUNC is up. One subject: the three figures
 * and their corner. Called from page.c: mtr_poll (the UI loop's redraw test) and
 * mtr_draw (after stock's screen). */

typedef unsigned int u32;
typedef unsigned char u8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)   /* (1.11: 0x40113b90) */
#define SET_DIRTY ((void (*)(void *))0x4011D5DEu)
#define FRAMES (*(volatile u32 *)0x4058F8D4u)                      /* 1,500 a second */
#define DTCN0 (*(volatile u32 *)0xFC07000Cu)
#define HEAP_CB ((volatile u32 *)0x4029F0DCu)                      /* (1.11: 0x4029eb9c) */
#define HEAP_MTX ((void *)0x445E2E40u)                             /* (1.11: 0x445e1e40) */
#define LOCK ((void (*)(void *))0x40001608u)
#define UNLOCK ((void (*)(void *))0x4000172Au)

#define WINDOW 750u                     /* frames: half a second */
#define REDRAW 375u                     /* frames: the corner redrawn 4 times a second */
#define LIST_BOUND 4096                 /* one free list's walk, at most (digihealth's) */

extern int smp_func_held;
extern int smp_dsp_load(void);

/* The meter's state, in its own block of RAM above BSS (METER_RAM, 256 B, declared by
 * dnfw.mods.waverider.ram), never in the code chunk: hooks.S's counters change at every
 * context switch and the engine gate holds every CODE chunk to its image. RAM above BSS
 * holds whatever it held at power-on, so the first poll zeroes the block (MTR_MAGIC). */
#define MTR ((volatile u32 *)METER_RAM)
enum {
    MTR_MAGIC_W, MTR_T_IN, MTR_ISR_IDLE, MTR_IDLE, MTR_I_ON, MTR_I_START, MTR_SWITCHES,   /* hooks.S's */
    MTR_CPU, MTR_HEAP, MTR_HEAP_OK, MTR_HEAP_FAULTS, MTR_DRAWS,                         /* the figures */
    MTR_W_AT, MTR_W_T, MTR_W_IDLE, MTR_W_ISR, MTR_W_SW, MTR_HEAP_AT, MTR_DRAW_NEXT, MTR_HELD_WAS,
    MTR_HEAP_TOT, MTR_DPK, MTR_DPK_AT, MTR_CPK, MTR_CPK_AT,                             /* the bars */
    MTR_WORDS
};
_Static_assert(MTR_WORDS * 4 <= 256, "the meter's block");
#define MTR_MAGIC 0x4D545231u           /* 'MTR1' */
#define mtr_cpu (*(volatile int *)&MTR[MTR_CPU])
#define mtr_heap MTR[MTR_HEAP]
#define mtr_heap_ok MTR[MTR_HEAP_OK]
#define mtr_heap_faults MTR[MTR_HEAP_FAULTS]
#define mtr_draws MTR[MTR_DRAWS]
#define mtr_idle MTR[MTR_IDLE]
#define mtr_isr_idle MTR[MTR_ISR_IDLE]
#define mtr_switches MTR[MTR_SWITCHES]
#define w_at MTR[MTR_W_AT]
#define w_t MTR[MTR_W_T]
#define w_idle MTR[MTR_W_IDLE]
#define w_isr MTR[MTR_W_ISR]
#define w_sw MTR[MTR_W_SW]
#define heap_at MTR[MTR_HEAP_AT]
#define draw_next MTR[MTR_DRAW_NEXT]
#define held_was MTR[MTR_HELD_WAS]
#define mtr_heap_tot MTR[MTR_HEAP_TOT]
#define dpk (*(volatile int *)&MTR[MTR_DPK])
#define dpk_at MTR[MTR_DPK_AT]
#define cpk (*(volatile int *)&MTR[MTR_CPK])
#define cpk_at MTR[MTR_CPK_AT]
#define PEAK_HOLD 4500u                 /* frames: a peak tick stays 3 s */

static void cpu_window(void)
{
    u32 now = DTCN0, idle = mtr_idle, isr = mtr_isr_idle, sw = mtr_switches;
    u32 dt = now - w_t, di = idle - w_idle, dr = isr - w_isr;
    if (w_at && sw != w_sw && dt >= 1000u) {   /* the scheduler ran and the clock moved */
        u32 parked = di > dr ? di - dr : 0u;
        u32 pm = parked / (dt / 1000u);
        mtr_cpu = pm >= 1000u ? 0 : (int)(1000u - pm);
    }
    w_t = now, w_idle = idle, w_isr = isr, w_sw = sw;
}

static void heap_walk(void)
{
    const u8 *base = (const u8 *)HEAP_CB[1];
    const int *heads = (const int *)HEAP_CB[3];
    int top = (int)HEAP_CB[4];
    if (!base || !heads || top < 0)
        return;                                 /* the heap not set up yet */
    LOCK(HEAP_MTX);
    u32 units = 0, faults = 0;
    if (top > 31)
        top = 31;
    for (int order = 0; order <= top; order++) {
        int b = heads[order];
        u32 size = 1u << order;
        for (int n = LIST_BOUND; b >= 0 && n > 0; n--) {
            const u32 *h = (const u32 *)(base + ((u32)b << 4));
            if (((u32)b & (size - 1u))
                    || *(const u32 *)(base + (((u32)b + size) << 4) - 4) != size
                    || h[0] != ~(h[1] + h[2])) {
                faults++;                       /* a walk cut short by a failed check */
                break;
            }
            units += size;
            b = (int)h[2];
        }
    }
    UNLOCK(HEAP_MTX);
    mtr_heap = units << 4;
    mtr_heap_tot = HEAP_CB[5] << 4;             /* the heap's size, its units at +0x14 */
    mtr_heap_faults += faults;
    mtr_heap_ok = 1;
}

static int pct_of_pm(int pm)                    /* permille -> percent, -1 kept */
{
    return pm < 0 ? -1 : (pm + 5) / 10;
}

/* a peak held PEAK_HOLD frames, then following the figure down; -1 (no figure) once it
 * has aged out */
static void peak(volatile u32 *pk, volatile u32 *at, int v, u32 f)
{
    if ((v >= 0 && v >= (int)*pk) || f - *at > PEAK_HOLD) {
        *pk = (u32)v;
        *at = f;
    }
}

/* the UI loop's redraw test, every pass: the windows, and a redraw asked for while FUNC is
 * held (and once when it is let go, so stock's screen comes back whole) */
void mtr_poll(void *screen)
{
    if (MTR[MTR_MAGIC_W] != MTR_MAGIC) {        /* power-on: the block as RAM left it */
        for (int k = 1; k < MTR_WORDS; k++)
            MTR[k] = 0;
        mtr_cpu = -1;
        dpk = cpk = -1;
        MTR[MTR_MAGIC_W] = MTR_MAGIC;
    }
    u32 f = FRAMES;
    if (!w_at || f - w_at >= WINDOW) {
        cpu_window();
        w_at = f ? f : 1u;
    }
    peak(&MTR[MTR_DPK], &MTR[MTR_DPK_AT], smp_dsp_load(), f);
    peak(&MTR[MTR_CPK], &MTR[MTR_CPK_AT], pct_of_pm(mtr_cpu), f);
    u32 held = smp_func_held != 0;
    if (held && (!held_was || f - heap_at >= 2u * WINDOW)) {
        heap_walk();                            /* at the press, then once a second */
        heap_at = f;
    }
    if (held != held_was || (held && (int)(f - draw_next) >= 0)) {
        draw_next = f + REDRAW;
        SET_DIRTY(screen);
    }
    held_was = held;
}

/* 3 x 5 glyphs, rows top to bottom, bit 2 the left column */
static const u8 GLYPH[][5] = {
    {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7}, {7, 1, 3, 1, 7}, {5, 5, 7, 1, 1},
    {7, 4, 7, 1, 7}, {7, 4, 7, 5, 7}, {7, 1, 1, 2, 2}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 7},
    {6, 5, 5, 5, 6},    /* 10 D */
    {7, 4, 4, 4, 7},    /* 11 C */
    {5, 5, 7, 5, 5},    /* 12 H */
    {5, 5, 6, 5, 5},    /* 13 K */
    {5, 7, 7, 5, 5},    /* 14 M */
    {0, 0, 7, 0, 0},    /* 15 - */
    {0, 0, 0, 0, 2},    /* 16 . */
    {0, 0, 0, 0, 0},    /* 17 space */
};

static int gi(char ch)
{
    if (ch >= '0' && ch <= '9')
        return ch - '0';
    switch (ch) {
    case 'D': return 10;
    case 'C': return 11;
    case 'H': return 12;
    case 'K': return 13;
    case 'M': return 14;
    case '-': return 15;
    case '.': return 16;
    default: return 17;
    }
}

static int put_num(char *b, int n, u32 v)      /* decimal, no leading zeros */
{
    char t[10];
    int k = 0;
    do {
        t[k++] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v && k < 10);
    while (k)
        b[n++] = t[--k];
    return n;
}

static int percent(char *b, int n, int pm_or_pct, int is_pm)
{
    if (pm_or_pct < 0) {
        b[n++] = '-';
        b[n++] = '-';
        return n;
    }
    u32 p = is_pm ? ((u32)pm_or_pct + 5u) / 10u : (u32)pm_or_pct;
    return put_num(b, n, p > 999u ? 999u : p);
}

static void glyphs(void *canvas, int x, int y_top, const char *b, int n)
{
    for (int k = 0; k < n; k++) {
        const u8 *g = GLYPH[gi(b[k])];
        for (int r = 0; r < 5; r++)
            for (int c = 0; c < 3; c++)
                if (g[r] >> (2 - c) & 1)
                    SET_PIXEL(canvas, x + c, y_top - r, 0);
        x += 4;
    }
}

#define COL_W 16                        /* a column: a letter and 3 digits; its bar */
#define COL_GAP 2
#define BOX_X0 (128 - 3 * COL_W - 2 * COL_GAP)   /* 76 */

/* one column at x: LETTER and the percent (rows 63..59); two rows lower a bar (rows 56..54,
 * 16 px) filled to the percent, the rest a dotted floor, and a tick (rows 57..54) at the
 * peak PK; no bar fill and no tick while the figure is unknown ("--") */
static void column(void *canvas, int x, char letter, int pct, int pk)
{
    char b[4];
    int n = 0;
    b[n++] = letter;
    n = percent(b, n, pct, 0);
    glyphs(canvas, x, 63, b, n);
    int fill = pct < 0 ? 0 : (pct > 100 ? COL_W : (pct * COL_W + 50) / 100);
    for (int k = 0; k < COL_W; k++) {
        if (k < fill)
            for (int y = 54; y <= 56; y++)
                SET_PIXEL(canvas, x + k, y, 0);
        else if (!(k & 1))
            SET_PIXEL(canvas, x + k, 54, 0);
    }
    if (pct >= 0 && pk >= 0) {
        int t = pk >= 100 ? COL_W - 1 : pk * COL_W / 100;
        for (int y = 54; y <= 57; y++)
            SET_PIXEL(canvas, x + t, y, 0);
    }
}

/* after stock's screen (page.c wr_screen): the corner, top right, while FUNC is held: a
 * white box over the title bar's right end (rows 54..63, where stock draws its tempo box,
 * its full height so none of stock's edge shows under it), three columns in black. The
 * canvas is 128 x 64, y counting up from the bottom. */
void mtr_draw(void *canvas)
{
    if (!smp_func_held)
        return;
    for (int y = 54; y <= 63; y++)
        for (int x = BOX_X0 - 2; x < 128; x++)
            SET_PIXEL(canvas, x, y, 1);
    int mem = -1;
    if (mtr_heap_ok && mtr_heap_tot >= mtr_heap && mtr_heap_tot >= 100u) {
        u32 used = mtr_heap_tot - mtr_heap;
        mem = (int)((used / (mtr_heap_tot / 100u) > 100u) ? 100u : used / (mtr_heap_tot / 100u));
    }
    column(canvas, BOX_X0, 'D', smp_dsp_load(), dpk);
    column(canvas, BOX_X0 + COL_W + COL_GAP, 'C', pct_of_pm(mtr_cpu), cpk);
    column(canvas, BOX_X0 + 2 * (COL_W + COL_GAP), 'M', mem, -1);
    mtr_draws++;
}
