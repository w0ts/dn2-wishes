/* AMP page 2: the selected track's oscilloscope (docs/scope.md), OS 1.12.
 *
 * 2026-11-11 (the User): "an Oscilocope page for each track, i would put it as AMP page 2", "per track,
 * after the inserts", "A, follow overbridge. simple, logical." Stock AMP has one page; [AMP] on it now
 * steps AMP 1/2 (stock's) -> 2/2 (this scope) -> 1/2. FUNC + [AMP] and [AMP] from another page are
 * stock's. NO or any page key closes the scope, as the INSERT pages (csrc/inserts/ins.c).
 *
 * The audio is what Overbridge's track outputs carry (docs/link-research.md §2, §5): the DSP's output
 * stage 0x1c244d writes every block, for every track, either the routing's block after the inserts (A,
 * 0x258f68: post-chain) or the raw panned track (B) by Overbridge's own setting; tracks 1-6 L/R in the TDM
 * receive slots 2..13 (32 frames, 24 bits), tracks 7-16 L/R in the SPI reply's records (record n is sample
 * n: 84 B, a pair of channels as three shorts). Measured on the unit (remoteui, 2026-11-11): the records
 * move with notes, with and without the Overbridge app. The scope only reads; nothing is changed on
 * Overbridge's path (the ISR's code before our hook stays stock: scripts/gate_overbridge.py).
 *
 * smp_tdm (csrc/sampler/link.c, the audio ISR's hook, 1,500 a second) calls scope_tap while the page is up:
 * every Dth sample of the track (L+R)/2, the top 16 of its 24 bits, into a ring of 256. The page draws
 * 100 of them from the newest rising zero crossing that leaves 100 after it (else the newest 100), 25 times
 * a second. Any encoder but G sets the time span (D 1..32: 2..67 ms across).
 *
 * 2026-11-11 (the User): "the oscilo should also have a vertical zoom". Encoder G sets the trace's gain: x1 x2 x4 x8
 * x16, or AUTO (the largest of those that keeps the 100 shown samples inside the strip; its label says the gain it
 * took, "Ax4"). A sample past the strip is drawn on its top or bottom row. The gain and the span are the page's own,
 * for every track, and not saved: a way of looking, not part of a sound.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;
typedef short s16;
typedef int s32;

#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70u)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)               /* 1,500 a second */
#define PAGE_DOTS  ((void (*)(void *, void *, int, int, int))0x4006598Au)
#define KEY_HELD   ((int (*)(u32))0x4011FAC4u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY     0
#define IT_KNOB    1
#define K_AMP      4                            /* the firmware's own name table, 1.12 (scripts/emu_panel_map.py) */
#define K_NO       12
#define K_FUNC     17
/* the AMP page's view class, measured in the 1.12 emulator (2026-11-11, the screen's view list on [AMP],
 * 0x401E1448 on [FX] as ins.c's) */
#define AMP_PAGE_VTABLE 0x401E2320u
#define TDM_RX(h)  ((volatile u32 *)(0x4E6E7100u + ((u32)(h) << 11)))   /* as link.c */
#define RECORDS    0x800053C0u                  /* the SPI reply's copy (0x800053a4 + 0x1c) */
#define REDRAW     60u                          /* frames: 25 a second */
#define RING       256
#define SHOWN      100
#define ZOOMS      6

static const u8 DEC[ZOOMS] = {1, 2, 4, 8, 16, 32};
static const char *const SPAN[ZOOMS] = {"2ms", "4ms", "8ms", "17ms", "33ms", "67ms"};   /* 100 x D / 48 kHz */
#define GAINS      5                            /* x1 .. x16, then AUTO */
#define K_GAIN     7                            /* encoder G: the gain (its label at G, the span's at H) */
static const char *const GAIN_TEXT[GAINS + 1] = {"x1", "x2", "x4", "x8", "x16", "AUTO"};
static const char *const AUTO_TEXT[GAINS] = {"Ax1", "Ax2", "Ax4", "Ax8", "Ax16"};

int scope_up __attribute__((section(".data"))) = 0;
u32 scope_taps __attribute__((section(".data"))) = 0;   /* blocks tapped (the checks read it) */
static int zoom __attribute__((section(".data"))) = 2;
static int gain __attribute__((section(".data"))) = 0;      /* x1; GAINS is AUTO */
s16 scope_ring[RING] __attribute__((section(".data")));
u32 scope_pos __attribute__((section(".data"))) = 0;
static u32 phase __attribute__((section(".data"))) = 0;
static u32 next_draw __attribute__((section(".data"))) = 0;

extern int smp_overlay_dirty;
extern u32 ins_view_of(u32 cls);                /* csrc/inserts/ins.c */
extern void ins_say(const char *text, int slide);
extern u32 smp_rx_sh;                           /* link.c: the receive slots' justification, 0 or 8 */

static s32 s24(u32 w)                           /* a 24-bit two's complement value */
{
    return (s32)(w << 8) >> 8;
}

/* track t's sample f of this block, (L + R) / 2, its top 16 bits */
static s16 sample(int t, u32 h, int f)
{
    s32 l, r;
    if (t < 6) {
        volatile u32 *rx = TDM_RX(h);
        u32 a = rx[16 * f + 2 + 2 * t], b = rx[16 * f + 3 + 2 * t];
        l = smp_rx_sh ? (s32)a >> 8 : s24(a);
        r = smp_rx_sh ? (s32)b >> 8 : s24(b);
    } else {
        volatile u16 *s = (volatile u16 *)(RECORDS + 84u * (u32)f + 6u * (u32)(t - 6));
        u32 s0 = s[0], s1 = s[1], s2 = s[2];
        l = s24(s0 << 8 | s1 >> 8);
        r = s24((s1 & 0xFFu) << 16 | s2);
    }
    return (s16)((l + r) >> 9);
}

/* link.c smp_tdm, every period (one block of 32 frames), receive half h */
void scope_tap(u32 h)
{
    if (!scope_up)
        return;
    int t = UI_TRACK & 15;
    u32 d = DEC[zoom], f = phase;
    for (; f < 32; f += d)
        scope_ring[scope_pos++ & (RING - 1)] = sample(t, h, (int)f);
    phase = f - 32;
    scope_taps++;
}

int scope_visible(void)
{
    return scope_up;
}

static int amp_page(void)                       /* stock's AMP page is the page */
{
    return ins_view_of(AMP_PAGE_VTABLE) != 0;
}

static void scope_open(int up)
{
    scope_up = up;
    phase = 0;
    smp_overlay_dirty = 1;
    ins_say(up ? "AMP (2/2)" : "AMP (1/2)", 1);
}

/* rec.c smp_ui_pop, after ins_pop: 1 when the item is ours (then dropped) */
int scope_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int press = (flags & 1u) && !(flags & 0x10u);
    if (scope_up && it[0] == IT_KEY && code >= 41 && code <= 48)
        return 1;                               /* an encoder's push: ours while up */
    if (it[0] == IT_KEY && press && !(flags & 8u)) {
        if (code == K_AMP && !KEY_HELD(K_FUNC) && (scope_up || amp_page())) {
            scope_open(!scope_up);                    /* AMP 1/2 <-> 2/2 */
            return 1;
        }
        if (scope_up && (code == K_NO || !(code == K_FUNC || (code >= 10 && code <= 15) || (code >= 25 && code <= 48)))) {
            scope_up = 0;                       /* NO, or a key that leaves: the page closes */
            smp_overlay_dirty = 1;
            return code == K_NO;
        }
        return 0;
    }
    if (scope_up && it[0] == IT_KNOB && code >= 1 && code <= 8) {
        int step = (s8)it[8] > 0 ? 1 : (s8)it[8] < 0 ? -1 : 0;
        if (code == K_GAIN) {
            int g = gain + step;
            gain = g < 0 ? 0 : g > GAINS ? GAINS : g;
        } else {
            int z = zoom + step;
            zoom = z < 0 ? 0 : z >= ZOOMS ? ZOOMS - 1 : z;
            phase = 0;
        }
        smp_overlay_dirty = 1;
        return 1;
    }
    return 0;
}

/* page.c wr_poll: while up, a redraw 25 times a second */
void scope_poll(void *screen)
{
    if (scope_up && (int)(FRAMES_NOW - next_draw) >= 0) {
        next_draw = FRAMES_NOW + REDRAW;
        SET_DIRTY(screen);
    }
}

#include "../waverider/widgets.h"

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
}

#define X0   24                                 /* the trace: x 24..123, y 11..51 (centre 31) */
#define MID  31
#define HALF 20

static int ypix(s16 v, int g)                   /* g: the gain, 1..16 */
{
    int y = MID + (int)v * g * HALF / 32768;
    return y < MID - HALF ? MID - HALF : y > MID + HALF ? MID + HALF : y;
}

/* page.c wr_screen, after stock's AMP page, while the scope is up: the places ours, stock's title bar
 * and left panel kept */
void scope_draw(void *c)
{
    static s16 snap[RING] __attribute__((section(".data")));
    u32 end = scope_pos;                              /* the ring as the ISR left it (a sample may move under us) */
    for (int i = 0; i < RING; i++)
        snap[i] = scope_ring[(end + (u32)i) & (RING - 1)];   /* oldest first */
    int start = RING - SHOWN;                   /* the newest rising zero crossing with 100 after it */
    for (int i = RING - SHOWN; i > 0; i--)
        if (snap[i - 1] < 0 && snap[i] >= 0) {
            start = i;
            break;
        }
    int g = 1 << (gain < GAINS ? gain : 0), peak = 0;
    if (gain == GAINS) {                        /* AUTO: the largest gain the shown samples fit */
        for (int x = 0; x < SHOWN; x++) {
            int a = snap[start + x] < 0 ? -snap[start + x] : snap[start + x];
            peak = a > peak ? a : peak;
        }
        for (g = 16; g > 1 && peak * g > 32767; g >>= 1)
            ;
    }
    fill(c, 18, 0, 127, 53, 0);                 /* from x 18: stock's envelope picture starts at x 21 */
    for (int x = 0; x < SHOWN; x += 4)
        SET_PIXEL(c, X0 + x, MID, 1);           /* the zero line, dotted */
    int last = ypix(snap[start], g);
    for (int x = 0; x < SHOWN; x++) {
        int y = ypix(snap[start + x], g), lo = y < last ? y : last, hi = y < last ? last : y;
        for (int v = lo; v <= hi; v++)          /* each column joined to the one before */
            SET_PIXEL(c, X0 + x, v, 1);
        last = y;
    }
    wg_label(c, 6, gain == GAINS ? AUTO_TEXT[g == 16 ? 4 : g == 8 ? 3 : g == 4 ? 2 : g == 2 ? 1 : 0]
                                 : GAIN_TEXT[gain]);
    wg_label(c, 7, SPAN[zoom]);
    PAGE_DOTS(0, c, 2, 1, 7);
}

/* page.c wr_screen, after stock's page when nothing of ours covers it: AMP 1/2's dots */
void scope_dots(void *c)
{
    if (!scope_up && amp_page())
        PAGE_DOTS(0, c, 2, 0, 7);
}
