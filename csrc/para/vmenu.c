/* PARA on stock's VOICE menu, knob B (2026-11-15, the User: "i would put the voice page, for the synth that
 * support it. on B knob"; docs/paraphonic.md). Stock 1.12's VOICE SETUP (VoiceMenuView, the VOICE key) has eight
 * places: top VOICE STEAL, ---, ---, REUSE (knobs A..D); bottom VOICES, UNISON STATE, V.AMNT, SPREAD (E..H). Its B
 * is an empty place: stock draws "---" there and a turn of B changes nothing (measured in the emulator, 2026-11-15).
 *
 * On a track whose machine plays PARA (para.h: ANALOG 2, JUNO), B is PARA: OFF / ON (2026-11-15, the User: "i would
 * have expected the para (in voice page) to be on or off ?"; ON a chord of up to 8 notes), the track's sound's record MOD (0,
 * or PARA_ON stored; an older project's 1 or 2 shows and plays as ON), set through the knob's own path (setValue:
 * undo, the kit and the frame all see it), one step per four detents as every choice knob. On any other track nothing here draws or takes a turn: the menu is stock's, pixel for pixel.
 *
 * The hooks, as the send pages' (csrc/fxpage): vm_begin / vm_draw (page.c wr_screen, before and after stock's
 * screen), vm_pop (rec.c smp_ui_pop, before stock sees an item), and vm_seen_hook (hooks.S, in VoiceMenuView's draw
 * where it pushes B's "---"): the menu was drawn this frame. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed char s8;

#include "para.h"
#include "../waverider/widgets.h"

#define IT_KNOB 1
#define KNOB_B  2                                       /* knob codes 1..8 = A..H */
#define UI_TRACK (*(volatile u8 *)0x42432A6Cu)
#define FRAMES   (*(volatile u32 *)0x4058F8D4u)         /* rectrig.c's FRAMES: the UI's clock */
#define UI_OWNER  ((u32 (*)(void))0x4018AC5Au)          /* rec.c: the stock knob path */
#define PARAM_SET ((u32 (*)(u32, u32, u32))0x40041A40u)
#define SET_VALUE ((u32 (*)(u32, u32, u32, u32, u32, u32, u32))0x40037326u)
#define FONT_LABEL 0x44508EF8u                          /* VoiceMenuView's labels (VOICE STEAL, ---, REUSE) */
#define B_X0 33                                         /* place B's label row (stock's "---" at x 43, y 27) */
#define B_X1 73
#define B_LABEL_Y 27

u32 vm_seen __attribute__((section(".data"))) = 0;     /* VoiceMenuView drew in the last screen drawn (hooks.S) */
static int acc __attribute__((section(".data"))) = 0;   /* detents toward the next step */
static u32 acc_at __attribute__((section(".data"))) = 0;
u32 vm_sets __attribute__((section(".data"))) = 0;      /* PARA values set (the emulator reads it) */
/* what the emulator reads to see why a turn of B was or was not taken: the screens begun, VoiceMenuView's draws (hooks.S
 * counts them), the knob B items seen, and the last one's answer: 1 taken, 2 the menu not seen in the last screen, 3
 * not a PARA track */
u32 vm_frames __attribute__((section(".data"))) = 0;
u32 vm_hooks __attribute__((section(".data"))) = 0;
u32 vm_bs __attribute__((section(".data"))) = 0;
u32 vm_why __attribute__((section(".data"))) = 0;

extern int smp_overlay_dirty;

/* page.c wr_screen: before stock draws */
void vm_begin(void)
{
    vm_frames++;
    vm_seen = 0;
}

/* the last screen drawn was the VOICE menu (a static menu draws no other screen before the next turn), on a PARA
 * track */
static int ours(void)
{
    return vm_seen && para_track(UI_TRACK);
}

/* rec.c smp_ui_pop: a turn of B on a PARA track's VOICE menu sets PARA (1: the item is ours, dropped) */
int vm_pop(u8 *it)
{
    if (it[0] != IT_KNOB)
        return 0;
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    if (code != KNOB_B)
        return 0;
    vm_bs++;
    if (!ours()) {
        vm_why = vm_seen ? 3 : 2;
        return 0;
    }
    vm_why = 1;
    int delta = (s8)it[8];
    u32 now = FRAMES;
    if (now - acc_at > 3000u || (acc > 0 && delta < 0) || (acc < 0 && delta > 0))
        acc = 0;
    acc_at = now;
    acc += delta;
    int n = acc / 4;
    acc -= n * 4;
    int t = UI_TRACK, on = para_value(t) != 0, v = on + n;
    v = v < 0 ? 0 : v > 1 ? 1 : v;
    if (n && v != on) {
        u32 owner = UI_OWNER();
        u32 ps = owner ? PARAM_SET(owner, PARA_RECORD, (u32)t) : 0;
        if (ps) {
            SET_VALUE(ps, PARA_RECORD, (u32)(v ? PARA_ON : 0) << 8, (u32)t, 0, 0, 1);
            vm_sets++;
        }
    }
    smp_overlay_dirty = 1;
    return 1;
}

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
    cv_fill(c, x0, y0, x1, y1, on);             /* (2026-11-17) the same pixels a column word at a time: page.c */
}

/* page.c wr_screen, after stock's screen: B as PARA, over stock's "---". The menu's middle above B and C is its 16
 * voice circles, so the value goes in B's label row with the name: "PARA OFF" or "PARA ON", centred on B (x 33..73,
 * clear of C's "---" at x 75; the emulator's capture, 2026-11-15) */
void vm_draw(void *c)
{
    if (!vm_seen || !para_track(UI_TRACK))
        return;
    fill(c, B_X0, B_LABEL_Y, B_X1, B_LABEL_Y + 7, 0);                       /* stock's "---" */
    WG_TEXT(c, FONT_LABEL, (B_X0 + B_X1) / 2, B_LABEL_Y, 2, "PARA %s", para_value(UI_TRACK) ? "ON" : "OFF");
}
