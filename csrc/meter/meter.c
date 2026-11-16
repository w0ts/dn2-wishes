/* The system meter (docs/meter.md), OS 1.12: while FUNC is held, on every page, a corner
 * reads the DSP's load, the ColdFire's load and the free ColdFire heap:
 *
 *     D42 C61 H812K
 *
 * - D: the DSP's load in percent, the last half second's peak (link.c smp_dsp_load, from
 *   the SHARC's idle packets, v0.32); "--" while none came in the last second.
 * - C: the ColdFire's load in percent over the last half second: 1 - (idle - ISR inside
 *   idle) / elapsed, from hooks.S's counters (usbprobe's method, measured on the unit).
 * - H: the main buddy heap's free bytes (K, or M from 1000 K), walked under its own lock
 *   as digihealth walks it (sysinfo.s: base of 16-byte units at +4, the free-list heads
 *   at +0xc, the highest order at +0x10; a block counted only when aligned to its order
 *   and its last word is its size, a link followed only through an intact header).
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
    mtr_heap_faults += faults;
    mtr_heap_ok = 1;
}

/* the UI loop's redraw test, every pass: the windows, and a redraw asked for while FUNC is
 * held (and once when it is let go, so stock's screen comes back whole) */
void mtr_poll(void *screen)
{
    if (MTR[MTR_MAGIC_W] != MTR_MAGIC) {        /* power-on: the block as RAM left it */
        for (int k = 1; k < MTR_WORDS; k++)
            MTR[k] = 0;
        mtr_cpu = -1;
        MTR[MTR_MAGIC_W] = MTR_MAGIC;
    }
    u32 f = FRAMES;
    if (!w_at || f - w_at >= WINDOW) {
        cpu_window();
        w_at = f ? f : 1u;
    }
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

static int heap_text(char *b, int n)
{
    if (!mtr_heap_ok) {
        b[n++] = '-';
        b[n++] = '-';
        return n;
    }
    u32 k = mtr_heap >> 10;
    if (k < 1000u) {
        n = put_num(b, n, k);
        b[n++] = 'K';
    } else if (k < 10240u) {                    /* 1.0M .. 9.9M */
        u32 t = (k * 10u) >> 10;
        n = put_num(b, n, t / 10u);
        b[n++] = '.';
        b[n++] = (char)('0' + t % 10u);
        b[n++] = 'M';
    } else {
        n = put_num(b, n, k >> 10);
        b[n++] = 'M';
    }
    return n;
}

/* after stock's screen (page.c wr_screen): the corner, top right, while FUNC is held.
 * The canvas is 128 x 64, y counting up from the bottom. */
void mtr_draw(void *canvas)
{
    if (!smp_func_held)
        return;
    char b[24];
    int n = 0;
    b[n++] = 'D';
    n = percent(b, n, smp_dsp_load(), 0);
    b[n++] = ' ';
    b[n++] = 'C';
    n = percent(b, n, mtr_cpu, 1);
    b[n++] = ' ';
    b[n++] = 'H';
    n = heap_text(b, n);
    int w = 0;
    for (int k = 0; k < n; k++)
        w += b[k] == '.' ? 2 : b[k] == ' ' ? 2 : 4;
    /* stock's look: black text on a white box over the title bar's right end (where stock
     * draws its tempo box, rows 54..63), the box its full height so none of stock's edge
     * shows under it */
    int x0 = 127 - w, y_top = 61;               /* the glyphs' top row */
    for (int y = 54; y <= 63; y++)
        for (int x = x0 - 2; x < 128; x++)
            SET_PIXEL(canvas, x, y, 1);
    int x = x0;
    for (int k = 0; k < n; k++) {
        if (b[k] == ' ') {
            x += 2;
            continue;
        }
        const u8 *g = GLYPH[gi(b[k])];
        int cols = b[k] == '.' ? 1 : 3, shift = b[k] == '.' ? 1 : 0;
        for (int r = 0; r < 5; r++)
            for (int c = 0; c < cols; c++)
                if (g[r] >> (2 - c - shift) & 1)
                    SET_PIXEL(canvas, x + c, y_top - r, 0);
        x += cols + 1;
    }
    mtr_draws++;
}
