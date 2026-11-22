/* The oscilloscope (docs/scope.md), OS 1.12: the selected track's waveform over stock's TRIG page.
 *
 * 2026-11-11 (the User): "an Oscilocope page for each track, i would put it as AMP page 2", "per track,
 * after the inserts", "A, follow overbridge. simple, logical." Until 2026-11-19 it was AMP's third page.
 * 2026-11-19 (the User): it opens on a LONG press of the [TRIG] page key (held a second, as the page keys' overviews:
 * csrc/inserts/ovw.c watches the hold and calls scope_long), over stock's TRIG page, and stays up until another page
 * is chosen: any page key ([TRIG] itself: closed, TRIG's page as it was), TRK, NO. A short press is stock's own TRIG
 * page, untouched: every [TRIG] item goes on to stock (its page on the press from another page, its step on a tap's
 * release, its values while held); once the scope is up, stock takes the release as a hold's (no step). The scope is
 * no longer an AMP page: [AMP] steps AMP 1/2 (stock's) -> 2/2 (ENV2) -> 1/2 (amp_pages.h). amp_sub says AMP_SCOPE
 * while the scope is up, so what refuses "a page of ours" (the routes and DEST popups) refuses it too.
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
 * 100 of them from the newest rising zero crossing that leaves 100 after it (else the newest 100), 15 times
 * a second (25 until 2026-11-17). Any encoder but G sets the time span (D 1..32: 2..67 ms across).
 *
 * 2026-11-11 (the User): "the oscilo should also have a vertical zoom". Encoder G sets the trace's gain: x1 x2 x4 x8
 * x16, or AUTO (the largest of those that keeps the 100 shown samples inside the strip). 2026-11-18 (the User: "just
 * put 'auto', not A4 A8 etc"): AUTO's label says AUTO whatever gain it took (v1 said it, "Ax4", "A/2"). A sample past
 * the strip is drawn on its top or bottom row. The gain and the span are the page's own, for every track, and not
 * saved: a way of looking, not part of a sound.
 *
 * 2026-11-17 (the User: "the oscilloscope should have autozoom vertical (below X1)"): the gains go down to x1/8 too
 * (x1/8 x1/4 x1/2, shifts, no divide), and AUTO picks among all eight: the largest gain that keeps every shown sample
 * off the strip's top and bottom rows, so a loud trace is never drawn on them. At x1 a full-scale sample
 * reaches exactly the edge row (s16 -32768 -> y 11), so x1/2 is the lowest AUTO ever needs. AUTO holds still: it
 * zooms out at once (the frame a sample would reach an edge row), and in only after ZOOM_IN_HOLD frames in a row in
 * which the shown samples fit the larger gain with an eighth of the strip to spare (then to the largest gain all of
 * those frames allowed).
 *
 * 2026-11-18 (the User: "auto should be default for oscilator and we should rfememebr the values set for it"; one
 * setting for every track, kept after power-off, AUTO until the User changes it): the gain starts at AUTO, and the
 * gain and the time span are kept in the mod's settings sector (csrc/jump/jump.c: its flags word, the same 512 bytes
 * DIRECT JUMP, REMOTE CONTROL, LIVE SELECT and the VOICE BUDGET keep there; no new write path). Bits 4..7 hold the
 * gain (0 AUTO, 1..8 x1/8..x16) and bits 8..10 the span (0 the default 8 ms, 1..6 2..67 ms), so a sector written
 * before, none, a bad one (jump.c's check) or a value out of range reads AUTO and 8 ms. Taken once the sector is read;
 * written a second after the last turn, or when the page closes (one write for a whole turn of the knob).
 *
 * 2026-11-18 (the User: "i still get cpu in osclillo"; on the unit the audio ISR alone takes about 84.5 % of the CPU):
 * the same pixels for less. The tap reads its two (three) words a sample without a test a sample. A frame drawn alone
 * redraws only the trace's columns whose span changed (the labels, the page dots and the cleared strip are already on
 * the frame it is drawn over), with whole-byte writes. When the page title's message runs out, the next frame is a
 * full redraw, so the bar shows its own title (frames drawn alone never touch the title bar).
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;
typedef short s16;
typedef int s32;

#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70u)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY   ((u8 (*)(void *))0x4011D5D4u)               /* move.b: only %d0's low byte (csrc/modulation) */
#define FB_FRONT   (*(u8 *volatile *)0x402A10C8u)              /* the panel's two buffers (docs/display-path.md) */
#define FB_BACK    (*(u8 *volatile *)0x402A10CCu)              /* BACK: the frame on the glass, between presents */
#define LOOP_BUF   (*(u8 **)0x4059E1B0u)                       /* the UI loop's canvas buffer: panel_diff's return */
#define CANVAS_NEW ((void (*)(void *, int, int, u8 *, void *))0x40113E2Au)   /* (canvas, w, h, buffer, its aid) */
#define CANVAS_AID ((void *)0x4059DDB0u)                       /* the loop's: 0x4002e4a6 */
#define PANEL_DIFF ((u32 (*)(void))0x40131FD2u)                /* FRONT's changed groups sent, the swap -> FRONT, in %d0:
                                                                * a u32, never a pointer (gcc reads a pointer from %a0) */
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))
/* the panel UART's ring (UART8 TX, eDMA 35, 4,096 B; 0x4000220c's free-space count): bytes not yet sent */
#define UART_PEND  (*(volatile u32 *)0x4058E5D8u)
#define UART_HEAD  (*(volatile u32 *)0x4058E5D0u)
#define UART_TAIL  (*(volatile u32 *)0x4058E5DCu)
#define TCD_CITER  (*(volatile u16 *)0xFC045474u)
#define TCD_BITER  (*(volatile u16 *)0xFC04547Cu)
#define UART_IDLE  128u                                        /* bytes queued: below, a scope frame may start */
#define RETRY      15u                                         /* frames (10 ms): a frame dropped, looked at again */
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)               /* 1,500 a second */
#define PAGE_DOTS  ((void (*)(void *, void *, int, int, int))0x4006598Au)
#define KEY_HELD   ((int (*)(u32))0x4011FAC4u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY     0
#define IT_KNOB    1
#define K_TRIG     1                            /* the [TRIG] page key */
#define K_AMP      4                            /* the firmware's own name table, 1.12 (scripts/emu_panel_map.py) */
#define K_UP       11
#define K_NO       12
#define K_DOWN     14
#define K_FUNC     17
/* the AMP page's view class, measured in the 1.12 emulator (2026-11-11, the screen's view list on [AMP],
 * 0x401E1448 on [FX] as ins.c's) */
#define AMP_PAGE_VTABLE 0x401E2320u
/* stock's TRIG page's view class (1/2 and 2/2), measured in the 1.12 emulator (2026-11-19, the screen's view list on
 * [TRIG]; QUANTIZE, FUNC + [TRIG], is 0x401E3CB0 alone): the scope opens only over it */
#define TRIG_PAGE_VTABLE 0x401E2180u
#define TDM_RX(h)  ((volatile u32 *)(0x4E6E7100u + ((u32)(h) << 11)))   /* as link.c */
#define RECORDS    0x800053C0u                  /* the SPI reply's copy (0x800053a4 + 0x1c) */
#define REDRAW     100u                         /* frames: 15 a second (the User, 2026-11-17; v1: 60, 25 a second) */
#define RING       256
#define SHOWN      100
#define ZOOMS      6

static const u8 DEC[ZOOMS] = {1, 2, 4, 8, 16, 32};
static const char *const SPAN[ZOOMS] = {"2ms", "4ms", "8ms", "17ms", "33ms", "67ms"};   /* 100 x D / 48 kHz */
#define GAINS      8                            /* x1/8 .. x16 (a shift of gain - GAIN_X1), then AUTO */
#define GAIN_X1    3
#define K_GAIN     7                            /* encoder G: the gain (its label at G, the span's at H) */
static const char *const GAIN_TEXT[GAINS + 1] = {"x1/8", "x1/4", "x1/2", "x1", "x2", "x4", "x8", "x16", "AUTO"};
#define FULL       32768                        /* |sample| x gain below this: off the edge rows */
#define FULL_IN    28672                        /* ... below this (7/8): room to zoom in */
#define ZOOM_IN_HOLD 8                          /* frames (about half a second at 15 a second) */

#include "../waverider/amp_pages.h"

int amp_sub __attribute__((section(".data"))) = AMP_STOCK;   /* the AMP page up (amp_pages.h) */
int scope_up __attribute__((section(".data"))) = 0;            /* the scope up (amp_sub == AMP_SCOPE): the tap runs */
u32 scope_taps __attribute__((section(".data"))) = 0;   /* blocks tapped (the checks read it) */
#define ZOOM_DEFAULT 2                          /* 8 ms */
int scope_zoom __attribute__((section(".data"))) = ZOOM_DEFAULT;   /* the span: 0..ZOOMS-1 (the checks read it) */
#define zoom scope_zoom
int scope_gain __attribute__((section(".data"))) = GAINS;     /* 0..GAINS-1: x1/8..x16; GAINS is AUTO, the default
                                                                * (the checks read it) */
int scope_auto __attribute__((section(".data"))) = -1;        /* the gain AUTO took, -1 none yet (the checks read it) */
static int auto_in __attribute__((section(".data"))) = 0;     /* frames in a row AUTO could zoom in */
static int auto_to __attribute__((section(".data"))) = 0;     /* the largest gain all of them allowed */
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

/* link.c smp_tdm, every period (one block of 32 frames), receive half h. sample()'s values, its tests (track, the
 * slots' justification) taken once a block instead of once a sample.
 * 2026-11-18: and only in the blocks before a frame is due: a frame draws from the newest 256 samples, which 8 x D
 * blocks fill (every Dth of 32 a block), so the blocks before those are never read (LEAD: two blocks to spare). At D 1..8
 * (2..17 ms) that is 10..66 of the 100 blocks between frames; D 16 and 32 read every block. The frame drawn when it is
 * due shows the newest audio as before; a full redraw asked between frames (a stock redraw, a knob) draws the ring the
 * last frame drew. The tap was a third of the page's cost, its reads of the TDM page uncached */
#define LEAD(d)    (8u * (d) + 2u)
void scope_tap(u32 h)
{
    if (!scope_up)
        return;
    u32 d = DEC[zoom];
    if ((int)(next_draw - FRAMES_NOW) > (int)LEAD(d)) {
        phase = 0;                              /* not yet: the ring is filled afresh before the next frame */
        return;
    }
    int t = UI_TRACK & 15;
    u32 f = phase, pos = scope_pos;
    s16 *ring = scope_ring;
    if (t < 6) {
        volatile u32 *rx = TDM_RX(h) + 16u * f + 2u + 2u * (u32)t;
        u32 step = 16u * d;
        if (smp_rx_sh)
            for (; f < 32; f += d, rx += step)
                ring[pos++ & (RING - 1)] = (s16)((((s32)rx[0] >> 8) + ((s32)rx[1] >> 8)) >> 9);
        else
            for (; f < 32; f += d, rx += step)
                ring[pos++ & (RING - 1)] = (s16)((s24(rx[0]) + s24(rx[1])) >> 9);
    } else {
        volatile u16 *s = (volatile u16 *)(RECORDS + 84u * f + 6u * (u32)(t - 6));
        u32 step = 42u * d;                     /* a record is 84 bytes */
        for (; f < 32; f += d, s += step) {
            u32 s0 = s[0], s1 = s[1], s2 = s[2];
            ring[pos++ & (RING - 1)] = (s16)((s24(s0 << 8 | s1 >> 8) + s24((s1 & 0xFFu) << 16 | s2)) >> 9);
        }
    }
    scope_pos = pos;
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

int amp_stock_page(void)                        /* csrc/inserts/ovw.c: stock's AMP page, none of ours over it */
{
    return amp_sub == AMP_STOCK && amp_page();
}

/* the pages' titles (the User, 2026-11-13): stock's AMP page is ENV1 (it is routable, docs/matrix.md), so "ENV1/AMP"
 * (inserts' ins_header renames stock's own "AMP" with it); the page dots say which of AMP's two */
const char *const amp_title1 = "ENV1/AMP";

static void amp_open(int sub)                   /* AMP's page SUB (AMP_STOCK, AMP_ENV2) */
{
    static const char *const TITLE[AMP_PAGES] = {[AMP_STOCK] = "ENV1/AMP", [AMP_ENV2] = "ENV2"};
    amp_sub = sub;
    smp_overlay_dirty = 1;
    ins_say(TITLE[sub], 1);
}

static void scope_close(void)
{
    amp_sub = AMP_STOCK;
    scope_up = 0;
    smp_overlay_dirty = 1;
}

static int trig_page(void)                      /* stock's TRIG page is the page */
{
    return ins_view_of(TRIG_PAGE_VTABLE) != 0;
}

/* ovw.c ovw_poll: [TRIG] held a second (alone: no FUNC, no other key or knob since its press, the scope not up then).
 * The scope opens over stock's TRIG page, never over a question, a popup of ours or anything that is not that page
 * (QUANTIZE, a menu): -> 1 when it opened */
int scope_long(void)
{
    extern int smp_question_up(void), mxp_visible(void), ldp_visible(void), wpop_shown(void);
    if (scope_up || amp_sub != AMP_STOCK || !trig_page() || smp_question_up() || mxp_visible() || ldp_visible()
        || wpop_shown())
        return 0;
    amp_sub = AMP_SCOPE;
    scope_up = 1;
    phase = 0;
    smp_overlay_dirty = 1;
    ins_say("WAVEFORM", 1);
    return 1;
}

/* -- the gain and the span, kept in the settings sector (jump.c; header comment) ---------------------------------- */
extern u32 set_bits;                            /* jump.c: the sector's flags as read; written by jmp_poll when dirty */
extern u8 jmp_dirty;
extern int jmp_loaded;                          /* the sector read (or found absent or bad) */
#define SET_GAIN_SHIFT 4                        /* bits 4..7: 0 AUTO, 1..8 the gains x1/8..x16 */
#define SET_SPAN_SHIFT 8                        /* bits 8..10: 0 the default span, 1..6 the spans 2..67 ms */
#define SET_SCOPE (15u << SET_GAIN_SHIFT | 7u << SET_SPAN_SHIFT)
#define SAVE_HOLD 1500u                         /* frames (1 s) after the last turn: then written */
int scope_set_taken __attribute__((section(".data"))) = 0;    /* the stored values taken (or a knob turned first) */
static int save_due __attribute__((section(".data"))) = 0;
static u32 save_at __attribute__((section(".data"))) = 0;

/* SET_SCOPE's bits as the gain and the span: anything else (a value out of range) reads AUTO and 8 ms */
void scope_settings_from(u32 bits)
{
    u32 g = bits >> SET_GAIN_SHIFT & 15u, z = bits >> SET_SPAN_SHIFT & 7u;
    scope_gain = g >= 1u && g <= GAINS ? (int)g - 1 : GAINS;
    zoom = z >= 1u && z <= ZOOMS ? (int)z - 1 : ZOOM_DEFAULT;
}

static u32 settings_bits(void)
{
    return (scope_gain < GAINS ? (u32)scope_gain + 1u : 0u) << SET_GAIN_SHIFT | ((u32)zoom + 1u) << SET_SPAN_SHIFT;
}

/* scope_poll, every pass of the UI loop: the stored values taken once jump.c has read the sector; a change written
 * SAVE_HOLD after the last turn, or as soon as the page is closed (never before the sector was read: jmp_poll would
 * then write over the other settings without reading them) */
static void settings_poll(void)
{
    if (!scope_set_taken && jmp_loaded) {
        scope_set_taken = 1;
        scope_settings_from(set_bits);
        scope_auto = -1;
        auto_in = 0;
        phase = 0;
        if (scope_up)
            smp_overlay_dirty = 1;
    }
    if (save_due && jmp_loaded && (!scope_up || (int)(FRAMES_NOW - save_at) >= 0)) {
        save_due = 0;
        u32 b = settings_bits();
        if ((set_bits & SET_SCOPE) != b) {
            set_bits = (set_bits & ~SET_SCOPE) | b;
            jmp_dirty = 1;
        }
    }
}

static void settings_changed(void)
{
    scope_set_taken = 1;                        /* the User's value wins over a sector read later */
    save_due = 1;
    save_at = FRAMES_NOW + SAVE_HOLD;
}

extern int env2_turn(u32 knob, int step);       /* csrc/matrix/env2_page.c: a knob on ENV2's page */

/* UP / DOWN on the AMP pages (2026-11-20, the User: "UP/DOWN should page through the pages of AMP and FX ... like any
 * other pages"): stock's rule on its own pages, as csrc/inserts/ins.c fx_arrow (measured in the 1.12 emulator,
 * scripts/emu_updown_pages.py): DOWN the next page, UP the previous one, on the press and each repeat, stopping at the
 * ends; not with FUNC held (stock's) nor AMP held (its overview); a trig held, KEYBOARD, grid recording change nothing.
 * A step is [AMP]'s own (amp_open). Never over the scope (AMP_SCOPE: stock's TRIG page under it takes them, as ever).
 * -> 1 when the item is ours: a step, or any arrow while ENV2's page is up (nothing under it moves) */
static int amp_arrow(u32 code)
{
    if (KEY_HELD(K_FUNC) || KEY_HELD(K_AMP) || !(amp_sub == AMP_ENV2 || amp_stock_page()))
        return 0;
    int to = amp_sub + (code == K_DOWN ? 1 : -1);
    int step = to >= 0 && to < AMP_PAGES;
    if (step)
        amp_open(to);
    return step || amp_sub != AMP_STOCK;
}

/* rec.c smp_ui_pop, after ins_pop: 1 when the item is ours (then dropped) */
int scope_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int press = (flags & 1u) && !(flags & 0x10u);
    if (amp_sub != AMP_STOCK && it[0] == IT_KEY && code >= 41 && code <= 48)
        return 1;                               /* an encoder's push: ours while up */
    if (it[0] == IT_KEY && press && (code == K_UP || code == K_DOWN) && !scope_up)
        return amp_arrow(code);                 /* (a repeat too, as stock's pages step on it) */
    if (it[0] == IT_KEY && press && !(flags & 8u)) {
        extern u32 ovw_pass;                    /* csrc/inserts/ovw.c (2026-11-17): AMP steps on its release; a press
                                                 * on stock's AMP page, or from another page, goes on to stock alone */
        if (scope_up) {                         /* the scope, over stock's TRIG page */
            if (code != K_NO && (code == K_FUNC || (code >= 10 && code <= 15) || (code >= 25 && code <= 48)))
                return 0;                       /* FUNC, YES and the arrows, the trig keys: it stays */
            scope_close();                      /* NO, or a key that leaves: it closes */
            if (code == K_AMP && ovw_pass == K_AMP) {
                ovw_pass = 0;                   /* [AMP]: stock's AMP page, on the press (ovw.c other_page) */
                return 0;
            }
            /* NO, and [TRIG] (stock's TRIG page as it was under the scope: no step on its release) are taken here;
             * FUNC + [TRIG] goes on (stock's QUANTIZE), as every other key */
            return code == K_NO || (code == K_TRIG && !KEY_HELD(K_FUNC));
        }
        if (code == K_AMP && ovw_pass == K_AMP) {
            ovw_pass = 0;
            return 0;
        }
        if (code == K_AMP && !KEY_HELD(K_FUNC) && (amp_sub != AMP_STOCK || amp_page())) {
            amp_open((amp_sub + 1) % AMP_PAGES);        /* AMP 1/2 -> 2/2 -> 1/2 */
            return 1;
        }
        if (amp_sub != AMP_STOCK && (code == K_NO || !(code == K_FUNC || (code >= 10 && code <= 15) || (code >= 25 && code <= 48)))) {
            amp_sub = AMP_STOCK;                /* NO, or a key that leaves: ENV2's page closes */
            smp_overlay_dirty = 1;
            return code == K_NO;
        }
        return 0;
    }
    if (amp_sub == AMP_ENV2 && it[0] == IT_KNOB && code >= 1 && code <= 8) {   /* (2026-11-19, the User) G: ENV2's DEST
                                                 * (the DEST popup opens on it first, dest_pop.c ldp_pop), H: its DEP
                                                 * (attenuverter); PAN and VOL stay on AMP 1/3 */
        if (env2_turn(code - 1, (s8)it[8]))
            smp_overlay_dirty = 1;
        return 1;
    }
    if (scope_up && it[0] == IT_KNOB && code >= 1 && code <= 8) {
        int step = (s8)it[8] > 0 ? 1 : (s8)it[8] < 0 ? -1 : 0;
        if (code == K_GAIN) {
            int g = scope_gain + step;
            scope_gain = g < 0 ? 0 : g > GAINS ? GAINS : g;
            auto_in = 0;                        /* AUTO starts from what the next frame shows */
            scope_auto = -1;
        } else {
            int z = zoom + step;
            zoom = z < 0 ? 0 : z >= ZOOMS ? ZOOMS - 1 : z;
            phase = 0;
        }
        settings_changed();
        smp_overlay_dirty = 1;
        return 1;
    }
    return 0;
}

void scope_draw(void *c);
static void scope_trace_alone(u8 *b);

/* bytes in the panel UART's ring not yet sent, counted as its writer 0x4000220c counts them */
static u32 uart_backlog(void)
{
    u32 inflight = ((u32)(TCD_CITER & 0x7FFFu) - (u32)(TCD_BITER & 0x7FFFu) + (UART_HEAD - UART_TAIL)) & 0xFFFu;
    return inflight + UART_PEND;
}

static u8 *scope_back __attribute__((section(".data"))) = 0;   /* the last full draw's buffer, the scope on top of it */
static u8 *scope_drew __attribute__((section(".data"))) = 0;   /* scope_draw's canvas buffer in the draw going on */
u32 scope_frames __attribute__((section(".data"))) = 0;   /* scope frames: full redraws asked, alone, dropped (the checks) */
u32 scope_alone __attribute__((section(".data"))) = 0;
u32 scope_dropped __attribute__((section(".data"))) = 0;
static int title_msg_drawn __attribute__((section(".data"))) = 0;   /* the last full draw had the title's message up */

#define TITLE_VTABLE 0x401E1D28u                /* the title bar's view class (csrc/inserts/ins.c) */

static int ram_ok(u32 a)
{
    return a >= 0x40000000u && a < 0x48000000u && !(a & 3u);
}

/* the page title's message (amp_open's "WAVEFORM", through stock's message line: the title view's +120) still up: its
 * time left, the word +0x4C, not yet 0 (it counts down every 4 panel ticks; measured in the 1.12 emulator, 2026-11-18,
 * emu_scope.py message_left). Stock's bar draws its own title again once it is 0, but only in a full draw */
static int title_msg_up(void)
{
    u32 v = ins_view_of(TITLE_VTABLE);
    u32 m = v ? *(volatile u32 *)(v + 120) : 0;
    return ram_ok(m) && *(volatile u32 *)(m + 0x4C) != 0;
}

/* page.c wr_screen, at the end of every full draw: the scope may draw its next frames alone over this one only if it
 * drew this frame's scope and nothing of ours drew over it afterwards */
void scope_end(void *canvas, int clean)
{
    u8 *b = CANVAS_BUF(canvas);
    scope_back = clean && scope_drew == b ? b : 0;
    scope_drew = 0;
    title_msg_drawn = scope_back ? title_msg_up() : 0;
}

/* page.c wr_poll: while up, a frame 25 times a second (2026-11-17, the User: "oscilloscope is creating cpu issues",
 * "the ui [is] lagging behind like several seconds").
 * - Never queued behind the panel UART: a frame starts only when its ring is all but empty (UART_IDLE); else it is
 *   dropped and looked at again 10 ms later. UART8 carries 15,625 bytes a second, and a busy trace changes about 52
 *   of the 128 groups (520 B) a frame: 25 frames a second filled the ring, and the UI task waited in the writer's
 *   free-space loop (emulator, the UART at the unit's rate: 99 % of the UART, 4 KB queued, docs/scope.md).
 * - Drawn alone: the frame on the glass (BACK) copied to FRONT, the scope drawn over it (scope_trace_alone, the same
 *   pixels), and stock's panel_diff sends the groups that changed and swaps: stock's TRIG page is not drawn again
 *   under the scope. Only when the last full draw ended with the scope on top (scope_end), that frame is still on the
 *   glass, and no redraw is due; else the full redraw as before. */
void scope_poll(void *screen)
{
    extern int ovw_visible(void);               /* an overview covers the page (csrc/inserts/ovw.c): no frame, alone or full */
    settings_poll();
    if (!scope_up || (int)(FRAMES_NOW - next_draw) < 0 || ovw_visible())
        return;
    if (uart_backlog() >= UART_IDLE) {
        next_draw = FRAMES_NOW + RETRY;
        scope_dropped++;
        return;
    }
    next_draw = FRAMES_NOW + REDRAW;
    scope_frames++;
    /* a full redraw: the glass is not the scope's last frame, a redraw is due (or asked for, smp_overlay_dirty: the
     * labels change), or the title's message ran out since the glass was drawn (2026-11-18: until then "WAVEFORM"
     * stayed on the bar, the frames drawn alone never touching it) */
    if (!scope_back || FB_BACK != scope_back || (IS_DIRTY(screen) & 0xFFu) || smp_overlay_dirty
        || (title_msg_drawn && !title_msg_up())) {
        SET_DIRTY(screen);
        return;
    }
    u8 *front = FB_FRONT;
    const u32 *src = (const u32 *)scope_back;
    volatile u32 *dst = (volatile u32 *)front;  /* (volatile: gcc would call a memcpy the chunk lacks) */
    for (int k = 0; k < 256; k++)
        dst[k] = src[k];
    scope_trace_alone(front);
    LOOP_BUF = (u8 *)PANEL_DIFF();              /* the loop's canvas buffer: the new FRONT, as its own present leaves it */
    scope_back = FB_BACK;                       /* = front: on the glass now */
    scope_alone++;
}

#include "../waverider/widgets.h"

/* the canvas's pixels by bytes: column x is 8 bytes, pixel (x, y) bit 7 - y % 8 of byte 8x + y / 8 (stock's setPixel
 * 0x40113e70, y up from the bottom). The drawing below sets exactly the pixels the SET_PIXEL loops of v1 set */

/* rows 0..53 of columns X0..X1 cleared: bytes 0..5 of each column, and rows 48..53 of byte 6 (rows 54, 55, the title
 * bar's, kept) */
static void clear_strip(u8 *b, int x0, int x1)
{
    for (int x = x0; x <= x1; x++) {
        u8 *col = b + 8 * x;
        *(u32 *)col = 0;
        *(u16 *)(col + 4) = 0;
        col[6] &= 0x03u;
    }
}

/* rows LO..HI (LO <= HI) of column X set */
static void vspan(u8 *b, int x, int lo, int hi)
{
    u8 *col = b + 8 * x;
    for (int k = lo >> 3; k <= hi >> 3; k++) {
        int r0 = lo > 8 * k ? lo & 7 : 0, r1 = hi < 8 * k + 7 ? hi & 7 : 7;
        col[k] |= (u8)((0xFFu >> r0) & (0xFFu << (7 - r1)));
    }
}

#define X0   24                                 /* the trace: x 24..123, y 11..51 (centre 31) */
#define MID  31
#define HALF 20

/* v x 2^k x HALF / 32768, truncated toward zero (as v1's v * g * HALF / 32768 for k >= 0), k -3..4: shifts only */
static int ypix(s16 v, int k)
{
    int m = (int)v * HALF, s = 15 - k;
    if (k > 0)
        m *= 1 << k, s = 15;
    int d = m < 0 ? -(-m >> s) : m >> s;
    int y = MID + d;
    return y < MID - HALF ? MID - HALF : y > MID + HALF ? MID + HALF : y;
}

/* the largest gain (an index) at which PEAK x gain stays below LIMIT */
static int fit(int peak, int limit)
{
    int g = GAINS - 1;
    while (g > 0 && (g >= GAIN_X1 ? peak << (g - GAIN_X1) : peak >> (GAIN_X1 - g)) >= limit)
        g--;
    return g;
}

/* AUTO's gain for this frame: out at once, in after ZOOM_IN_HOLD frames that all allowed it */
static int auto_gain(int peak)
{
    int out = fit(peak, FULL), in = fit(peak, FULL_IN);
    if (scope_auto < 0 || out < scope_auto) {   /* a sample would reach an edge row (or AUTO just taken) */
        scope_auto = out;
        auto_in = 0;
    } else if (in > scope_auto) {
        auto_to = auto_in == 0 || in < auto_to ? in : auto_to;
        if (++auto_in >= ZOOM_IN_HOLD) {
            scope_auto = auto_to;
            auto_in = 0;
        }
    } else
        auto_in = 0;
    return scope_auto;
}

/* the trace on the frame drawn last (on the glass while scope_back is): each column's rows lo..hi */
static u8 span_lo[SHOWN] __attribute__((section(".data")));
static u8 span_hi[SHOWN] __attribute__((section(".data")));

/* this frame's trace from the ring as the ISR left it: each column's rows into LO, HI (AUTO's gain taken) */
static void trace(u8 *lo, u8 *hi)
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
    const s16 *v = snap + start;
    int g = scope_gain;
    if (g == GAINS) {                           /* AUTO: the largest gain the shown samples fit */
        int mx = 0, mn = 0;                     /* (the largest |sample|: max(mx, -mn), one compare a sample less) */
        for (int x = 0; x < SHOWN; x++)
            if (v[x] > mx)
                mx = v[x];
            else if (v[x] < mn)
                mn = v[x];
        g = auto_gain(mx > -mn ? mx : -mn);
    }
    int k = g - GAIN_X1;
    int last = ypix(v[0], k);
    for (int x = 0; x < SHOWN; x++) {
        int y = ypix(v[x], k);
        lo[x] = (u8)(y < last ? y : last);      /* each column joined to the one before */
        hi[x] = (u8)(y < last ? last : y);
        last = y;
    }
}

/* page.c wr_screen, after stock's page (TRIG's, since 2026-11-19), while the scope is up: the places ours, stock's title bar
 * and left panel kept */
void scope_draw(void *c)
{
    u8 *b = CANVAS_BUF(c);
    scope_drew = b;
    trace(span_lo, span_hi);
    clear_strip(b, 18, 127);                    /* from x 18: stock's envelope picture starts at x 21 */
    for (int x = 0; x < SHOWN; x += 4)
        vspan(b, X0 + x, MID, MID);             /* the zero line, dotted */
    for (int x = 0; x < SHOWN; x++)
        vspan(b, X0 + x, span_lo[x], span_hi[x]);
    wg_label(c, 6, GAIN_TEXT[scope_gain]);      /* AUTO says AUTO, whatever gain it took (the User, 2026-11-18) */
    wg_label(c, 7, SPAN[zoom]);                 /* (no page dots: the scope is none of TRIG's pages) */
}

/* rows 11..51 (the trace's) of one column, as scope_draw leaves them: rows LO..HI set, the zero line's dot when DOT,
 * the rest clear; every other row kept. The column's 8 bytes as two big-endian words: row y is bit 31 - y of the
 * first (rows 0..31) or bit 63 - y of the second (rows 32..63), as bit 7 - y % 8 of byte y / 8 */
#define KEEP_HI 0xFFE00000u                     /* rows 0..10 */
#define KEEP_LO 0x00000FFFu                     /* rows 52..63 */
static void column(u8 *col, int lo, int hi, int dot)
{
    u32 *w = (u32 *)col;
    u32 h = lo <= 31 ? (0xFFFFFFFFu >> lo) & (hi >= 31 ? 0xFFFFFFFFu : 0xFFFFFFFFu << (31 - hi)) : 0u;
    u32 l = hi >= 32 ? (0xFFFFFFFFu >> (lo > 32 ? lo - 32 : 0)) & (0xFFFFFFFFu << (63 - hi)) : 0u;
    w[0] = (w[0] & KEEP_HI) | h | (dot ? 1u << (31 - MID) : 0u);
    w[1] = (w[1] & KEEP_LO) | l;
}
_Static_assert(MID == 31 && MID - HALF == 11 && MID + HALF == 51, "column(): the trace's rows are 11..51, the zero line 31");

/* scope_poll, a frame drawn alone over a copy of the frame on the glass (B): only the columns whose span changed are
 * written. Everything else on B is the scope's last frame already: its labels (they change only with a full redraw,
 * smp_overlay_dirty), its page dots, its cleared strip and the trace's unchanged columns. The same pixels as
 * scope_draw's (emu_scope.py --proof checks every byte of every such frame) */
static void scope_trace_alone(u8 *b)
{
    u8 lo[SHOWN], hi[SHOWN];
    trace(lo, hi);
    for (int x = 0; x < SHOWN; x++)
        if (lo[x] != span_lo[x] || hi[x] != span_hi[x]) {
            span_lo[x] = lo[x];
            span_hi[x] = hi[x];
            column(b + 8 * (X0 + x), lo[x], hi[x], (x & 3) == 0);
        }
}

extern const char *ins_title_now(void);         /* csrc/inserts/ins.c */

static int named(const char *t, const char *w)
{
    while (*w && *t == *w)
        t++, w++;
    return !*w && !*t;
}

/* page.c wr_screen, after stock's page when nothing of ours covers it: AMP 1/2's dots, and its title ENV1/AMP over
 * stock's own (1.12 says "Amplitude" on its title line; inserts' ins_header renames a bare "AMP" header).
 * 2026-11-14 (r5 on the unit showed "Amplitude"): the title goes through stock's message call (SAY, slide 1), as
 * AMP 2/2 does in amp_open. Writing the message line's string alone (slide 0) changed what ins_title_now
 * reads, not what the bar draws: stock had already posted "Amplitude". Once posted, the line reads ENV1/AMP, so
 * this runs once per entry. */
void scope_dots(void *c)
{
    if (amp_sub == AMP_STOCK && amp_page()) {
        const char *t = ins_title_now();
        if (t && (named(t, "Amplitude") || named(t, "AMP")))
            ins_say(amp_title1, 1);
        PAGE_DOTS(0, c, AMP_PAGES, AMP_STOCK, 7);
        extern void as_draw(void *c);           /* 2026-11-20: a drum machine's H is AMP ON/OFF (csrc/msel/ampsw.c) */
        as_draw(c);
    }
}
