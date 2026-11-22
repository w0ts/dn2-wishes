/* The system meter (docs/meter.md), OS 1.12: while [TEMPO] is held past a second (2026-11-21, the User: "a long press
 * of the METRONOME button"; until then FUNC tapped and pressed again, "one click and a half"), on every page, a box over the page body reads the DSP's load, the
 * ColdFire's load and the main heap's used share, a row each:
 *
 *     DSP  42  ########|                (a large figure and a bar of 74 px filled to it; DSP and CPU with a
 *     CPU  61  ###########|             tick at their peak over the last 3 s)
 *     RAM   9  ##
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
 * Nothing is drawn while the meter is down. Called from page.c: mtr_poll (the UI loop's redraw test), mtr_draw
 * (after stock's screen); from rec.c: mtr_key (every UI item, first). */

typedef unsigned int u32;
typedef unsigned char u8;

#include "quiet.h"
#include "stamp.h"

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)   /* (1.11: 0x40113b90) */
#define SET_DIRTY ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY  ((u8 (*)(void *))0x4011D5D4u)                     /* sets only %d0's low byte (move.b): a u8 */
#define FB_BACK   (*(u8 *volatile *)0x402A10CCu)                  /* the frame on the glass, between presents */
#define GLASS_GROUP ((void (*)(u32, u32, const u8 *))0x40131F04u)   /* (column 0..120, page 0..7, 8 bytes) */
#define GLASS_SHOW  ((void (*)(void))0x40131EECu)                  /* the 0xB8 after the groups */
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))                  /* ctor 0x40113e2a: +16 the buffer */
#define FRAMES (*(volatile u32 *)0x4058F8D4u)                      /* 1,500 a second */
#define DTCN0 (*(volatile u32 *)0xFC07000Cu)
#define HEAP_CB ((volatile u32 *)0x4029F0DCu)                      /* (1.11: 0x4029eb9c) */
#define HEAP_MTX ((void *)0x445E2E40u)                             /* (1.11: 0x445e1e40) */
#define LOCK ((void (*)(void *))0x40001608u)
#define UNLOCK ((void (*)(void *))0x4000172Au)

#define WINDOW 750u                     /* frames: half a second */
#define REDRAW 375u                     /* frames: the meter updated 4 times a second while up */
#define LIST_BOUND 4096                 /* one free list's walk, at most (digihealth's) */

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
    MTR_W_AT, MTR_W_T, MTR_W_IDLE, MTR_W_ISR, MTR_W_SW, MTR_HEAP_AT, MTR_DRAW_NEXT, MTR_BIG_WAS,
    MTR_HEAP_TOT, MTR_DPK, MTR_DPK_AT, MTR_CPK, MTR_CPK_AT,                             /* the bars */
    MTR_ICON_AT_D, MTR_ICON_AT_C, MTR_ICON_AT_M, MTR_ICON_SHOWN, MTR_ICON_FORCE, MTR_ICON_HYS,   /* the load icons */
    MTR_QUIET, MTR_CPU_FRESH,                                                           /* the CPU label's quiet */
    MTR_WORDS
};
_Static_assert(MTR_WORDS * 4 <= 256, "the meter's block");
#define MTR_MAGIC 0x4D545231u           /* 'MTR1' */
u32 mtr_loaded __attribute__((section(".data"))) = 0;   /* the block cleared since this load (mtr_poll) */
extern int mtr_big;                     /* the big meter is up (mtr_key, below) */
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
#define big_was MTR[MTR_BIG_WAS]          /* the meter up at the last poll */
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

int mtr_cpu_pct(void)                           /* C in percent, -1 none (the AMP overview, csrc/inserts/ovw_draw.c) */
{
    return MTR[MTR_MAGIC_W] == MTR_MAGIC && mtr_loaded ? pct_of_pm(mtr_cpu) : -1;
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
#define CPU_FRESH     2u                /* windows: after a quiet, the CPU label reads C again only from the
                                         * second half second window, the first wholly after it (2026-11-14) */
#define ICON_DSP_PCT  99                /* the DSP's load, percent: on at this, off under ICON_DSP_OFF.
                                         * 2026-11-10, the unit idle (sequencer stopped) reads D 94 %, so 95 lit it
                                         * there; the skips are what say the time ran out, this only the ceiling */
#define ICON_DSP_OFF  97
#define ICON_HEAP_PCT 90                /* the main heap's used share, percent */
#define ICON_HEAP_EVERY 3000u           /* frames: the heap walked every 2 s for RAM */
#define ICON_X1       126               /* the right-most box's last column */
#define ICON_TEMPO_X0 100               /* the tempo's clock and figure, x 100..126 */
#define ICON_Y0       55                /* the boxes' rows, 55..61 (the title bar is y 54..63) */
#define ICON_CLIP     8u                /* 2026-11-20: CLIP (the mixer meters, csrc/meter/mixer.c): an output in use
                                         * clipped, lit 3 s after (its own hold, mixer.c LABEL_FRAMES) */
#define ICON_ALL      15u

extern int smp_skipped_any(void);
extern int ins_full_any(void);

static inline __attribute__((always_inline)) int heap_pct(void)   /* the main heap's used share, -1 not walked yet
                                        * (inlined as before the big meter: the UI pass's cost with it down unchanged) */
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

/* 2026-11-14, the User: "Disable during firmware upgrade and until loading notification is gone". While
 * stock is busy on purpose (quiet.c: the boot until its "Loading..." is gone, an OS upgrade arriving or
 * being written) the CPU label stays unlit, its hold and its hysteresis cleared; after, it reads C again
 * only from a window wholly after the quiet (CPU_FRESH), never from the load stock had meanwhile. DSP and
 * RAM, and the big meter's C, as before. */
static int cpu_label_live(void)
{
    u32 quiet = mtr_quiet_why();
    MTR[MTR_QUIET] = quiet;
    if (quiet) {
        MTR[MTR_ICON_HYS] &= ~2u;
        MTR[MTR_ICON_AT_C] = 0;
        MTR[MTR_CPU_FRESH] = 0;
        return 0;
    }
    return MTR[MTR_CPU_FRESH] >= CPU_FRESH;
}

static u32 icons_live(u32 f)            /* the icons to show now (bits), the force ones included */
{
    int cpu_live = cpu_label_live();
    extern int mtr_starting(u32 f, u32 quiet);   /* 2026-11-20: DSP and CLIP quiet while the DN2 starts (startup.c) */
    int starting = mtr_starting(f, MTR[MTR_QUIET]);
    if (starting) {
        MTR[MTR_ICON_HYS] &= ~1u;
        MTR[MTR_ICON_AT_D] = 0;
    }
    extern int smp_bulk_recent(void);   /* 2026-11-11: none while an OS upgrade (or a transfer) arrives (link.c) */
    if (smp_bulk_recent())
        return 0;
    extern volatile u32 dt_sw[];        /* the test channel's switch LABELS (csrc/devtest/whitelist.c) */
    u32 ev = !dt_sw[1] ? 0u : (!starting && smp_skipped_any() ? 1u : 0u)
           | (!starting && over(1u, smp_dsp_load(), ICON_DSP_PCT, ICON_DSP_OFF) ? 1u : 0u)
           | (cpu_live && over(2u, mtr_cpu, ICON_CPU_PM, ICON_CPU_OFF) ? 2u : 0u)
           | (ins_full_any() || heap_pct() >= ICON_HEAP_PCT ? 4u : 0u);
    u32 on = 0;
    for (int k = 0; k < 3; k++) {
        if (ev >> k & 1u)
            MTR[MTR_ICON_AT_D + k] = mtr_stamp(f);
        u32 at = MTR[MTR_ICON_AT_D + k];
        if (at && mtr_age(at, f) < ICON_HOLD)     /* stamp.h: never -1 on an even frame */
            on |= 1u << k;
    }
    extern int mix_clip_recent(u32 f);  /* 2026-11-20: CLIP, 3 s after a real clip of an output in use (mixer.c) */
    if (dt_sw[1] && !starting && mix_clip_recent(f))
        on |= ICON_CLIP;
    return on | (MTR[MTR_ICON_FORCE] & ICON_ALL);
}

static u32 icons_lit(u32 f, u32 *live)  /* of those, the ones lit at this moment of the blink (*LIVE: all of them) */
{
    u32 on = icons_live(f), force = MTR[MTR_ICON_FORCE] & ICON_ALL;
    *live = on;
    return (f / ICON_BLINK & 1u) ? force & on : on;
}

static void icons_draw(void *canvas);

/* (2026-11-19, the User's CPU: with !CPU lit C read 88.4 % against 86.7: its blink asked a full redraw 4 times a
 * second; the User: "why not redraw only the part that needs to be redrawn??") the labels' blink without a full draw.
 * Stock's screen has only one way to change: its whole page drawn again (FRONT cleared, every view drawn, then only
 * the changed 8-pixel groups sent); a blink asked for that 4 times a second. Here, at each full draw with no
 * overview (mtr_draw), the label rows' pixels (rows 54..62, from the leftmost box to column 126) are kept in both
 * phases: lit (the labels' own boxes and letters) and dark (stock's pixels there, as that draw drew them: the tempo,
 * the title bar's bottom row). A blink (the same live labels), while no redraw is due and BACK is still that draw's
 * buffer, writes the phase's pixels into BACK and sends only the groups that changed (stock's sender, then its show),
 * as moving.c's lines alone; the next full draw diffs against a BACK that already holds them. The dark phase shows
 * stock's pixels as its last full draw left them, as the rest of the screen does (stock moves its title bar's bottom
 * row on its own timer and redraws it only with its page). A label come or gone, or any doubt: the full redraw. */
#define LBL_X0  64
#define LBL_M6  0x03u                   /* page 6's rows 54, 55 */
#define LBL_M7  0xFEu                   /* page 7's rows 56..62 */
#define LD_ __attribute__((section(".data")))
static u8 lbl_img[2][2 * (128 - LBL_X0)] LD_;   /* [lit, dark][2 x column + page 6 / 7]: the label rows only */
static u8 *lbl_buf LD_ = 0;             /* the buffer they were taken from (0: none; code data: 0 after every load) */
static u32 lbl_on LD_;                  /* the labels the lit phase shows */
static int lbl_x0 LD_;                  /* the leftmost column they cover */
static u32 lbl_live LD_;                /* the live labels at the last poll */
u32 mtr_lbl_alone LD_ = 0, mtr_lbl_full LD_ = 0;   /* (the checks) blinks drawn alone / by a full redraw */

static int icons_left(u32 lit);

static void lbl_take(void *canvas)      /* mtr_draw, FUNC up: both phases' pixels, the canvas left as it was */
{
    extern int ovw_visible(void);
    u8 *b = CANVAS_BUF(canvas);
    u32 shown = MTR[MTR_ICON_SHOWN], on = lbl_live;
    lbl_buf = 0;
    if (ovw_visible() || !on || (on & MTR[MTR_ICON_FORCE]) || (shown != on && shown != 0u))
        return;                         /* (a forced label: the emulator's steady screenshots, every draw full) */
    int x0 = icons_left(on);
    if (x0 < LBL_X0)
        return;
    u8 keep[2 * (128 - LBL_X0)];
    for (int x = x0; x < 128; x++) {
        keep[2 * (x - LBL_X0)] = b[8 * x + 6];
        keep[2 * (x - LBL_X0) + 1] = b[8 * x + 7];
        lbl_img[1][2 * (x - LBL_X0)] = b[8 * x + 6] & LBL_M6;          /* dark: stock's pixels, as drawn */
        lbl_img[1][2 * (x - LBL_X0) + 1] = b[8 * x + 7] & LBL_M7;
    }
    MTR[MTR_ICON_SHOWN] = on;
    icons_draw(canvas);
    for (int x = x0; x < 128; x++) {
        u8 *q = b + 8 * x + 6;
        lbl_img[0][2 * (x - LBL_X0)] = q[0] & LBL_M6;                  /* lit: the labels' own */
        lbl_img[0][2 * (x - LBL_X0) + 1] = q[1] & LBL_M7;
        q[0] = keep[2 * (x - LBL_X0)];
        q[1] = keep[2 * (x - LBL_X0) + 1];
    }
    MTR[MTR_ICON_SHOWN] = shown;
    lbl_on = on;
    lbl_x0 = x0;
    lbl_buf = b;
}

static int lbl_alone(void *screen, u32 lit, u32 live)   /* the phase LIT into BACK alone -> done */
{
    extern int ovw_visible(void);
    u8 *b = lbl_buf;
    if (!b || FB_BACK != b || IS_DIRTY(screen) || ovw_visible() || live != lbl_on
        || (lit != lbl_on && lit != 0u))
        return 0;
    const u8 *img = lbl_img[lit ? 0 : 1];
    u32 sent = 0;                       /* the groups changed: bit (column group - 8) + 8 (page - 6) */
    for (int x = lbl_x0; x < 127; x++) {        /* (column 127: never a label's) */
        u8 *q = b + 8 * x + 6;
        u8 n6 = (u8)((q[0] & ~LBL_M6) | img[2 * (x - LBL_X0)]);
        u8 n7 = (u8)((q[1] & ~LBL_M7) | img[2 * (x - LBL_X0) + 1]);
        if (n6 != q[0]) {
            q[0] = n6;
            sent |= 1u << ((x - LBL_X0) >> 3);
        }
        if (n7 != q[1]) {
            q[1] = n7;
            sent |= 1u << (8 + ((x - LBL_X0) >> 3));
        }
    }
    int n = 0;
    for (u32 g = 0; g < 16u; g++) {
        if (!(sent >> g & 1u))
            continue;
        u32 col = (u32)LBL_X0 + 8u * (g & 7u), page = 6u + (g >> 3);
        u8 bytes[8];
        for (u32 k = 0; k < 8u; k++)
            bytes[k] = b[8u * (col + k) + page];
        GLASS_GROUP(col, page, bytes);
        n++;
    }
    if (n)
        GLASS_SHOW();
    mtr_lbl_alone++;
    return 1;
}

static void icons_poll(void *screen, u32 f)
{
    u32 live, lit = icons_lit(f, &live);
    lbl_live = live;
    if (lit != MTR[MTR_ICON_SHOWN]) {   /* a blink, an icon come or gone: alone (the blink), else one redraw */
        if (lbl_alone(screen, lit, live)) {
            MTR[MTR_ICON_SHOWN] = lit;
            return;
        }
        MTR[MTR_ICON_SHOWN] = lit;
        mtr_lbl_full++;
        SET_DIRTY(screen);
    }
}

static void big_update(void *screen);
static void big_poll(void *screen, u32 f);
static void big_heap(u32 f);
static u8 *big_buf LD_ = 0;             /* the buffer the last full draw drew the meter into (0: none) */

/* the UI loop's redraw test, every pass: the windows; with the meter up its quarter-second update (alone), and a full
 * redraw when it comes and when it goes (stock's screen back whole). (page.c wr_poll reads mtr_big: nothing of ours is
 * drawn alone under the box) */
void mtr_poll(void *screen)
{
    if (MTR[MTR_MAGIC_W] != MTR_MAGIC || !mtr_loaded) {   /* power-on: the block as RAM left it; or a restart that kept
                                                 * it, whose stamps and draw_next are on the old run's clock (FRAMES
                                                 * starts again at 0: a deadline ahead of it waits as long as that run
                                                 * lasted). mtr_loaded is code data: 0 after every load (2026-11-18) */
        mtr_loaded = 1;
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
        if (MTR[MTR_CPU_FRESH] < CPU_FRESH)
            MTR[MTR_CPU_FRESH]++;               /* a window more since the CPU label's last quiet */
    }
    peak(&MTR[MTR_DPK], &MTR[MTR_DPK_AT], smp_dsp_load(), f);
    peak(&MTR[MTR_CPK], &MTR[MTR_CPK_AT], pct_of_pm(mtr_cpu), f);
    u32 up = mtr_big | big_was;                 /* the meter up, or just gone */
    if (up)
        big_heap(f);
    else if (f - heap_at >= ICON_HEAP_EVERY) {
        heap_walk();                            /* every 2 s (RAM's label) */
        heap_at = f;
    }
    icons_poll(screen, f);
    if (up)
        big_poll(screen, f);
}

/* the meter up or just gone (out of the usual pass's way): the heap walked as it comes and then once a second */
static void __attribute__((noinline)) big_heap(u32 f)
{
    u32 big = mtr_big != 0;
    if ((big && (!big_was || f - heap_at >= 2u * WINDOW)) || (!big && f - heap_at >= ICON_HEAP_EVERY)) {
        heap_walk();
        heap_at = f;
    }
}

/* ... and after the labels: one full redraw at its coming and at its going, a quarter-second update alone between */
static void __attribute__((noinline)) big_poll(void *screen, u32 f)
{
    u32 big = mtr_big != 0;
    if (big != big_was) {                       /* come or gone: one full redraw */
        big_was = big;
        big_buf = 0;                            /* (no update alone before the full draw has drawn the box) */
        draw_next = f + REDRAW;
        SET_DIRTY(screen);
    } else if (big && (int)(f - draw_next) >= 0) {
        draw_next = f + REDRAW;
        big_update(screen);                     /* the rows that changed, alone */
    }
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
    if (MTR[MTR_MAGIC_W] != MTR_MAGIC || !mtr_loaded) {   /* the meter has not run yet this load (before its first poll) */
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
        w[8 + k] = MTR[MTR_ICON_AT_D + k] ? mtr_age(MTR[MTR_ICON_AT_D + k], f) : 0xFFFFFFFFu;
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
    {4, 4, 4, 4, 7},    /* 24 L (CLIP) */
    {7, 2, 2, 2, 7},    /* 25 I */
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
    case 'L': return 24;
    case 'I': return 25;
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

/* right to left: RAM, CPU, DSP, CLIP (2026-11-20), then the group's "!" (bit k of LIT: 0 D, 1 C, 2 M, 3 CLIP) */
static const char *const WORD[5] = {"DSP", "CPU", "RAM", "CLIP", "!"};
static const u8 ORDER[5] = {2, 1, 0, 3, 4};

static int icons_left(u32 lit)          /* the leftmost column icons_draw covers for LIT (its boxes, the tempo's place) */
{
    int x = ICON_X1 + 1;
    for (int j = 0; j < 5; j++) {
        int k = ORDER[j], nl = k == 4 ? 1 : k == 3 ? 4 : 3;
        if (k < 4 && !(lit >> k & 1u))
            continue;
        int w = 1;
        for (int i = 0; i < nl; i++)
            w += letter_w(WORD[k][i]) + 1;
        x -= w + 1;
    }
    return x - 1 < ICON_TEMPO_X0 ? x - 1 : ICON_TEMPO_X0;
}

static void icons_draw(void *canvas)
{
    u32 lit = MTR[MTR_ICON_SHOWN];      /* (WORD, ORDER above: one ! for the group, at its left) */
    if (!lit)
        return;
    for (int y = ICON_Y0 - 1; y <= ICON_Y0 + 7; y++)   /* the tempo's place, its clock included, cleared */
        for (int xx = ICON_TEMPO_X0; xx <= ICON_X1; xx++)
            SET_PIXEL(canvas, xx, y, 1);
    int x = ICON_X1 + 1;
    for (int j = 0; j < 5; j++) {
        int k = ORDER[j], nl = k == 4 ? 1 : k == 3 ? 4 : 3;
        if (k < 4 && !(lit >> k & 1u))
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

/* The big meter (2026-11-19, the User: "could the cpu/dsp/memory meters be bigger"). Since 2026-11-21 it comes on
 * [TEMPO] held a second (csrc/inserts/ovw.c: stock acts on [TEMPO]'s release only, so the release of that hold is
 * dropped and stock's TEMPO screen does not come) and goes at [TEMPO]'s release. Any other key's press (or its
 * repeat), a push or an encoder turn takes it down at once and is left as it came (mtr_key).
 *
 * The box: the page body (rows 0..53, under the title bar, which stays stock's with the load labels), black, three rows
 * of 16 px on page boundaries (DSP pages 4-5, CPU 2-3, RAM 0-1): the word and the figure at twice the labels' 3 x 5
 * glyphs, then a bar of BAR_W px filled to the figure, a dotted floor past it, and on DSP and CPU a tick at the 3 s
 * peak; "--" and the floor alone while not known. A full draw (its coming, stock's own redraws while it is up) draws
 * it whole; every REDRAW frames (a quarter second) the rows whose figures changed are drawn again into BACK, the frame on
 * the glass, and only their changed 8-pixel groups sent (stock's sender, as the labels' blink and moving.c's lines);
 * nothing changed, nothing sent. Its going: one full redraw, stock's page back whole. */
#define K_TEMPO   9u
#define F_PRESS   0x01u
#define F_REPEAT  0x08u
#define F_RELEASE 0x10u
int mtr_big LD_ = 0;                    /* the meter up (page.c wr_poll: nothing of ours drawn alone under it) */
u32 mtr_func_ended LD_ = 0;             /* this FUNC release took the meter down (fxp.c: not a tap of its own) */
u32 mtr_big_shows LD_ = 0, mtr_big_alone LD_ = 0, mtr_big_full LD_ = 0, mtr_big_due LD_ = 0;   /* (the checks) */
u32 mtr_big_groups LD_ = 0;

/* rec.c smp_ui_pop, every item first: IT (type, then code, flags (keys) or index, delta (knobs)) read, never changed.
 * 2026-11-21 (the User: "on a long press of the METRONOME button and not FUNC click-and-hold"): the meter comes on
 * [TEMPO] held a second (csrc/inserts/ovw.c sets mtr_big and takes it down at the release); FUNC is stock's again.
 * Any other key's press (or its repeat), a push or an encoder turn takes it down here, as before; [TEMPO]'s own items
 * (its repeats while held) do not. */
void mtr_key(const u8 *it)
{
    if (it[0] > 1u)                             /* keys (0) and knobs (1) only */
        return;
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 fl = it[11];
    mtr_func_ended = 0;                         /* (FUNC no longer ends the meter: fxp.c's taps are all its own) */
    if (it[0] == 0 && code == K_TEMPO)
        return;
    if (it[0] == 0 && (!(fl & F_PRESS) || (fl & F_RELEASE)))
        return;                                 /* another key let go: nothing (it went down before) */
    mtr_big = 0;                                /* another key down (or its repeat), a push, a turn */
}

#define FIG_END 53                      /* the figure, right-aligned, ends before this column (3 digits from x 29, past
                                         * RAM, the widest word, x 1..26) */
#define BAR_X0  53
#define BAR_W   74
static int big_v[3][2] LD_;             /* each row's figure and peak as drawn */

static void big_vals(int v[3][2])
{
    v[0][0] = smp_dsp_load();
    v[0][1] = dpk;
    v[1][0] = pct_of_pm(mtr_cpu);
    v[1][1] = cpk;
    v[2][0] = heap_pct();
    v[2][1] = -1;
}

static void bpx(u8 *img, int x, int t)  /* a row's pixel: x 0..127, t 0..15 from its top */
{
    int ly = 15 - t;
    img[2 * x + (ly >> 3)] |= (u8)(0x80u >> (ly & 7));
}

static void big_glyph(u8 *img, int x, int t, const u8 *g, int w)   /* a W-wide glyph at twice its size, top-left (x, t) */
{
    for (int r = 0; r < 5; r++)
        for (int c = 0; c < w; c++)
            if (g[r] >> (w - 1 - c) & 1u)
                for (int d = 0; d < 4; d++)
                    bpx(img, x + 2 * c + (d & 1), t + 2 * r + (d >> 1));
}

/* row R (0 D, 1 C, 2 M) with V = {figure, peak} into IMG: 2 bytes a column, its lower page then its upper */
static void big_row_img(u8 *img, int r, const int *v)
{
    for (int k = 0; k < 256; k++)
        img[k] = 0;
    static const char *const NAME[3] = {"DSP", "CPU", "RAM"};   /* (the User, 2026-11-19: words, not D / C / M) */
    for (int i = 0, x = 1; i < 3; i++) {
        char ch = NAME[r][i];
        int w = letter_w(ch);                   /* RAM's M 5 wide: a 3-wide M reads as an H */
        big_glyph(img, x, 3, ch == 'M' ? WIDE_M : GLYPH[gi(ch)], w);
        x += 2 * w + 2;
    }
    char b[4];
    int n = percent(b, 0, v[0], 0);
    for (int i = 0; i < n; i++)
        big_glyph(img, FIG_END - 8 * (n - i), 3, GLYPH[gi(b[i])], 3);
    int pct = v[0];
    int fill = pct < 0 ? 0 : pct >= 100 ? BAR_W : (pct * BAR_W + 50) / 100;
    for (int k = 0; k < BAR_W; k++) {
        if (k < fill)
            for (int t = 4; t <= 11; t++)
                bpx(img, BAR_X0 + k, t);
        else if (!(k & 1))
            bpx(img, BAR_X0 + k, 11);           /* the dotted floor */
    }
    if (r < 2 && pct >= 0 && v[1] >= 0) {       /* the 3 s peak's tick, past the bar's height both ways */
        int x = BAR_X0 + (v[1] >= 100 ? BAR_W - 1 : v[1] * BAR_W / 100);
        for (int t = 2; t <= 13; t++)
            bpx(img, x, t);
    }
}

static u32 big_put(u8 *b, int r, const u8 *img) /* row R's image into B -> the groups changed: bit (x >> 3) + 16 page */
{
    int p0 = 4 - 2 * r;
    u32 sent = 0;
    for (int x = 0; x < 128; x++)
        for (int k = 0; k < 2; k++) {
            u8 *q = b + 8 * x + p0 + k;
            if (*q != img[2 * x + k]) {
                *q = img[2 * x + k];
                sent |= 1u << ((x >> 3) + 16 * k);
            }
        }
    return sent;
}

static void big_draw(void *canvas)      /* a full draw: the box whole, into the canvas */
{
    u8 *b = CANVAS_BUF(canvas);
    u8 img[256];
    for (int x = 0; x < 128; x++)
        b[8 * x + 6] &= 0x03u;                  /* rows 48..53 (page 6 but the title bar's 54, 55) */
    big_vals(big_v);
    for (int r = 0; r < 3; r++) {
        big_row_img(img, r, big_v[r]);
        big_put(b, r, img);
    }
    big_buf = b;
    mtr_draws++;
}

static void big_update(void *screen)    /* mtr_poll, a quarter second on: the rows changed, alone, else a full redraw */
{
    extern int ovw_visible(void);
    u8 *b = big_buf;
    if (IS_DIRTY(screen)) {
        mtr_big_due++;                          /* a full redraw already due (stock's own): it draws the meter whole */
        return;
    }
    if (!b || FB_BACK != b || ovw_visible()) {
        mtr_big_full++;
        SET_DIRTY(screen);
        return;
    }
    int v[3][2];
    big_vals(v);
    u8 img[256];
    int n = 0;
    for (int r = 0; r < 3; r++) {
        if (v[r][0] == big_v[r][0] && v[r][1] == big_v[r][1])
            continue;
        big_v[r][0] = v[r][0];
        big_v[r][1] = v[r][1];
        big_row_img(img, r, v[r]);
        u32 sent = big_put(b, r, img);
        for (u32 g = 0; g < 32u; g++) {
            if (!(sent >> g & 1u))
                continue;
            u32 col = 8u * (g & 15u), page = (u32)(4 - 2 * r) + (g >> 4);
            u8 bytes[8];
            for (u32 k = 0; k < 8u; k++)
                bytes[k] = b[8u * (col + k) + page];
            GLASS_GROUP(col, page, bytes);
            n++;
        }
    }
    if (n)
        GLASS_SHOW();
    mtr_big_groups += (u32)n;
    mtr_big_alone++;
}

/* after stock's screen (page.c wr_screen): the load labels (title bar), and the meter's box while it is up */
void mtr_draw(void *canvas)
{
    lbl_take(canvas);                           /* (both phases of the labels' blink, for lbl_alone) */
    icons_draw(canvas);                         /* the load labels */
    if (mtr_big)
        big_draw(canvas);
}
