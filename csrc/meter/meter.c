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
extern volatile u32 smp_load_peak;

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
    MTR_ICON_AT_D, MTR_ICON_AT_C, MTR_ICON_AT_M, MTR_ICON_SHOWN, MTR_ICON_FORCE, MTR_ICON_HYS,   /* the load icons */
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

/* The load labels (2026-11-10, the User: "a little shark/cpu/memory icon blinking when we are over
 * dsp/cpu/memory, on the right of the title bar"; then, the drawn icons not working: "CPU / DSP /
 * RAM"): at the title bar's right end, on every page, a word in a black box for each limit hit,
 * shown while it is and ICON_HOLD after, blinking at 2 Hz; the lit ones packed to the right, over
 * the tempo (it comes back when they go):
 *   DSP: the DSP's guard left a voice out for time (link.c smp_skipped_any; until now the PERC /
 *     Monomachine pages' "CPU" under LEV, which this replaces), or its load at ICON_DSP_PCT;
 *   CPU: the ColdFire's load over the last half second at ICON_CPU_PM (cpu_window);
 *   RAM: an FDN8 / XDLY insert found no instance free (FULL, ins.c), or the main heap
 *     ICON_HEAP_PCT used (walked every ICON_HEAP_EVERY, FUNC up or down).
 * MTR_ICON_FORCE (bit 0 D, 1 C, 2 M) shows an icon steadily: the emulator's screenshots (it runs
 * no DSP and no audio ISR, and its frame counter stands still). The FUNC meter covers them. */
#define ICON_HOLD     1500u             /* frames: a second after the last event */
#define ICON_BLINK    375u              /* frames: on a quarter second, off a quarter: 2 Hz */
#define ICON_CPU_PM   900               /* the ColdFire's load, permille: on at this, off under ICON_CPU_OFF */
#define ICON_CPU_OFF  850
#define ICON_DSP_PCT  99                /* the DSP's load, percent: on at this, off under ICON_DSP_OFF.
                                         * 2026-11-10, the unit idle (sequencer stopped) reads D 94 %, so 95 lit it
                                         * there; the skips are what say the time ran out, this only the ceiling */
#define ICON_DSP_OFF  97
#define ICON_HEAP_PCT 90                /* the main heap's used share, percent */
#define ICON_HEAP_EVERY 3000u           /* frames: the heap walked every 2 s for RAM */
#define ICON_X1       126               /* the right-most box's last column */
#define ICON_TEMPO_X0 100               /* the tempo's clock and figure, x 100..126 */
#define ICON_Y0       55                /* the boxes' rows, 55..61 (the title bar is y 54..63) */

extern int smp_skipped_any(void);
extern int ins_full_any(void);

static int heap_pct(void)              /* the main heap's used share, -1 not walked yet */
{
    if (!mtr_heap_ok || mtr_heap_tot < mtr_heap || mtr_heap_tot < 100u)
        return -1;
    u32 used = mtr_heap_tot - mtr_heap, pc = used / (mtr_heap_tot / 100u);
    return pc > 100u ? 100 : (int)pc;
}

static u32 over(u32 bit, int v, int on, int off)    /* a level with hysteresis: on at ON, off under OFF */
{
    u32 h = MTR[MTR_ICON_HYS];
    if (v >= on)
        h |= bit;
    else if (v < off)
        h &= ~bit;
    MTR[MTR_ICON_HYS] = h;
    return h & bit;
}

static u32 icons_live(u32 f)            /* the icons to show now (bits), the force ones included */
{
    extern int smp_bulk_recent(void);   /* 2026-11-11: none while an OS upgrade (or a transfer) arrives (link.c) */
    if (smp_bulk_recent())
        return 0;
    extern volatile u32 dt_sw[];        /* the test channel's switch LABELS (csrc/devtest/whitelist.c) */
    u32 ev = !dt_sw[1] ? 0u : (smp_skipped_any() ? 1u : 0u)
           | (over(1u, smp_dsp_load(), ICON_DSP_PCT, ICON_DSP_OFF) ? 1u : 0u)
           | (over(2u, mtr_cpu, ICON_CPU_PM, ICON_CPU_OFF) ? 2u : 0u)
           | (ins_full_any() || heap_pct() >= ICON_HEAP_PCT ? 4u : 0u);
    u32 on = 0;
    for (int k = 0; k < 3; k++) {
        if (ev >> k & 1u)
            MTR[MTR_ICON_AT_D + k] = f | 1u;
        u32 at = MTR[MTR_ICON_AT_D + k];
        if (at && f - at < ICON_HOLD)
            on |= 1u << k;
    }
    return on | (MTR[MTR_ICON_FORCE] & 7u);
}

static u32 icons_lit(u32 f)             /* of those, the ones lit at this moment of the blink */
{
    u32 on = icons_live(f), force = MTR[MTR_ICON_FORCE] & 7u;
    return (f / ICON_BLINK & 1u) ? force & on : on;
}

static void icons_draw(void *canvas);

static void icons_poll(void *screen, u32 f)
{
    u32 lit = icons_lit(f);
    if (lit != MTR[MTR_ICON_SHOWN]) {   /* a blink, an icon come or gone: one redraw */
        MTR[MTR_ICON_SHOWN] = lit;
        SET_DIRTY(screen);
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
    if ((held && (!held_was || f - heap_at >= 2u * WINDOW)) || (!held && f - heap_at >= ICON_HEAP_EVERY)) {
        heap_walk();                            /* at the press, then once a second; FUNC up: every 2 s (RAM's label) */
        heap_at = f;
    }
    icons_poll(screen, f);
    if (held != held_was || (held && (int)(f - draw_next) >= 0)) {
        draw_next = f + REDRAW;
        SET_DIRTY(screen);
    }
    held_was = held;
}

/* The telemetry frame's share (link.c, SysEx 32 TLM; docs/device-tests.md): the figures above as
 * 11 words, read only (nothing here is written, none of the icon logic runs: icons_live stamps
 * and moves hysteresis, this only reads what it left):
 *   w[0] D now, permille (0xFFFFFFFF: no figure)   w[1] D peak, percent (0xFFFFFFFF: none)
 *   w[2] C now, permille (0xFFFFFFFF: none)        w[3] C peak, percent
 *   w[4] heap used, bytes   w[5] heap total   w[6] heap walk faults
 *   w[7] label bits: lit now (bit 0 D, 1 C, 2 M), the hysteresis bits << 8, the forced << 16
 *   w[8..10] frames since each label's last event (D, C, M), 0xFFFFFFFF never */
void mtr_tlm(u32 *w)
{
    u32 f = FRAMES;
    if (MTR[MTR_MAGIC_W] != MTR_MAGIC) {            /* the meter has not run yet (before the first poll) */
        for (int k = 0; k < 11; k++)
            w[k] = 0xFFFFFFFFu;
        w[7] = 0;
        return;
    }
    int d = smp_dsp_load();
    w[0] = d < 0 ? 0xFFFFFFFFu : smp_load_peak;
    w[1] = dpk < 0 ? 0xFFFFFFFFu : (u32)dpk;
    w[2] = mtr_cpu < 0 ? 0xFFFFFFFFu : (u32)mtr_cpu;
    w[3] = cpk < 0 ? 0xFFFFFFFFu : (u32)cpk;
    w[4] = mtr_heap_ok ? (mtr_heap_tot > mtr_heap ? mtr_heap_tot - mtr_heap : 0u) : 0xFFFFFFFFu;
    w[5] = mtr_heap_ok ? mtr_heap_tot : 0xFFFFFFFFu;
    w[6] = mtr_heap_faults;
    w[7] = (MTR[MTR_ICON_SHOWN] & 7u) | (MTR[MTR_ICON_HYS] & 7u) << 8 | (MTR[MTR_ICON_FORCE] & 7u) << 16;
    for (int k = 0; k < 3; k++)
        w[8 + k] = MTR[MTR_ICON_AT_D + k] ? f - MTR[MTR_ICON_AT_D + k] : 0xFFFFFFFFu;
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
    {6, 5, 6, 4, 4},    /* 18 P (the load labels) */
    {7, 4, 7, 1, 7},    /* 19 S */
    {5, 5, 5, 5, 7},    /* 20 U */
    {6, 5, 6, 5, 5},    /* 21 R */
    {2, 5, 7, 5, 5},    /* 22 A */
    {1, 1, 1, 0, 1},    /* 23 ! (1 wide) */
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
    case 'P': return 18;
    case 'S': return 19;
    case 'U': return 20;
    case 'R': return 21;
    case 'A': return 22;
    case '!': return 23;
    default: return 17;
    }
}

/* the lit labels, packed to the right of the title bar: a black box, the word lit in it (3 x 5
 * letters; RAM's M 5 wide, a 3-wide M reads as an H) */
static const u8 WIDE_M[5] = {17, 27, 21, 17, 17};

static int letter_w(char ch)
{
    return ch == 'M' ? 5 : ch == '!' ? 1 : 3;
}

static void icons_draw(void *canvas)
{
    static const char *const WORD[4] = {"DSP", "CPU", "RAM", "!"};   /* one ! for the group, at its left */
    u32 lit = MTR[MTR_ICON_SHOWN];
    if (!lit)
        return;
    for (int y = ICON_Y0 - 1; y <= ICON_Y0 + 7; y++)   /* the tempo's place, its clock included, cleared */
        for (int xx = ICON_TEMPO_X0; xx <= ICON_X1; xx++)
            SET_PIXEL(canvas, xx, y, 1);
    int x = ICON_X1 + 1;
    for (int j = 0; j < 4; j++) {
        int k = j < 3 ? 2 - j : 3, nl = k == 3 ? 1 : 3;
        if (k < 3 && !(lit >> k & 1u))
            continue;
        int w = 1;
        for (int i = 0; i < nl; i++)
            w += letter_w(WORD[k][i]) + 1;     /* each letter and the column after it */
        x -= w + 1;
        for (int c = -1; c <= w; c++)          /* the bar's colour round it, the tempo under it hidden */
            for (int y = ICON_Y0 - 1; y <= ICON_Y0 + 7; y++)
                SET_PIXEL(canvas, x + c, y, c < 0 || c == w || y < ICON_Y0 || y > ICON_Y0 + 6);
        int lx = x + 1;
        for (int i = 0; i < nl; i++) {
            char ch = WORD[k][i];
            int lw = letter_w(ch);
            const u8 *g = ch == 'M' ? WIDE_M : GLYPH[gi(ch)];
            for (int r = 0; r < 5; r++)
                for (int b = 0; b < lw; b++)
                    if (g[r] >> (lw - 1 - b) & 1u)
                        SET_PIXEL(canvas, lx + b, ICON_Y0 + 5 - r, 1);
            lx += lw + 1;
        }
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
    if (!smp_func_held) {
        icons_draw(canvas);              /* the load icons, while FUNC is up */
        return;
    }
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
