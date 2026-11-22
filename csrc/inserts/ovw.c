/* The FX and AMP keys on release, and the inserts overview while FX is held (2026-11-17, the User; docs/inserts.md
 * "The FX key on its release"). AMP (the User: "also the AMP pages are broken the same way FX pages are"): the same rule,
 * no overview. They are the two page keys whose pages ours steps on the press; stock's own TRIG, SYN, FLTR and MOD
 * already step on a tap's release and show their values while held (measured in the emulator, stock and ours).
 *
 * The User: "hold longer. and we should not change fx page on press, but on release of the button (and not change page
 * if held long of course)". So:
 *   - FX's press is held back (FUNC + FX is stock's, untouched). On stock's FX page the press goes on to stock alone,
 *     for stock's value view while the key is held (the labels read the values, measured on stock 1.12); our pages'
 *     step does not run on it. On an INSERT page our labels read the values while FX is held.
 *   - Let go before the key repeats (stock's own test of a hold, the MOD key's: the first repeat comes 24 ticks after
 *     the press, 0.2 s on the unit; measured on stock's MOD in the emulator, 20 ticks steps, 28 does not): the tap of
 *     today, played then. v1 (95a560a2) waited a whole second, so on the unit a hold of half a second showed the values
 *     and then stepped the page anyway (the User: "currently goes to next page even for long presses"). Its press and release go in where the panel's go
 *     (stock 0x4011fc8c, as the test channel's keys, csrc/devtest), so every handler (ours: ins_pop's FX 1/3 -> 2/3
 *     -> 3/3, stock's page change, a popup closing) sees exactly the tap it saw on the press before.
 *   - Held one second: the overview, every track's two insert slots (dnfw.inserts.overview has its picture). Let go:
 *     it closes and nothing else happens. Any other key or knob while FX is held closes it and cancels the tap (the
 *     key then does what it does).
 * Time is the panel module's tick (0x466768b0, 121 a second on the unit, 0..4095, wraps), the UI's own hold clock;
 * the emulator moves it without audio frames.
 *
 * 2026-11-17 (the User: "lets try them all, we can revert what we dont like"): the same second's hold on SYN, FLTR and
 * MOD (the LFO pages) and AMP shows their overviews (ovw_draw.c: the machines, the filters, the LFOs and routes, the
 * load). SYN, FLTR and MOD are stock's: stock already steps them on a tap's release and shows their values while held
 * (measured in the emulator, stock and ours: a tap steps, a hold of 0.5 s or 2 s steps nothing on its release). Every
 * item of theirs goes on to stock untouched; this file only watches the hold, draws over stock's value view after the
 * second, and closes on the release (which stock, past its own hold test, takes as a hold: no step).
 *
 * 2026-11-19 (the User): the [TRIG] page key held the same second opens the oscilloscope (csrc/scope/scope.c
 * scope_long) instead of an overview, over stock's TRIG page, and it stays up after the release. [TRIG] is watched as
 * SYN, FLTR and MOD are: every item of it goes on to stock untouched (its page on the press, its values while held),
 * and stock takes the release after the second as a hold's (no step). FUNC held at the press (stock's QUANTIZE), a
 * stock question, the scope already up (the press closes it, scope_pop), or another key or knob during the hold: no
 * scope.
 *
 * 2026-11-19 (the User: "a long-press overview on the VOICE button: which tracks are in which mode -- unison, para --
 * and number of voices"): VOICE held the same second shows every track's machine, mode (PARA, UNISON, MONO, POLY) and
 * VOICES (ovw_draw.c voice_view). Stock 1.12 (measured in the emulator, stock and ours alike): VOICE's press and its
 * hold do nothing (the screen unchanged 3.3 s held); its release opens the VOICE menu (VOICE SETUP), or closes it when
 * it is open, however long the hold (the main key handler's VOICE case, 0x4005ef80, acts on the release bit; FUNC
 * held there: UNISON, ours the RECORDER). So every VOICE item goes on to stock untouched but one: the release of a
 * hold that showed the overview is dropped, and the screen is left as it was before the press (the menu neither opens
 * nor closes). A shorter hold's release, or one where another key or knob came first, is stock's (the menu). FUNC held
 * at the press, a stock question: no overview. Another key or knob while it is up closes it and does what it does.
 *
 * 2026-11-21 (the User: "a MIXER OVERVIEW: all 16 channels at once ... a LONG PRESS of FUNC + MOD"; then "all
 * channels, return and main. we had a mockup": scratch/mixer-overview.md option B): FUNC + [MOD] held a second shows
 * every track's, send return's and the main's live level and clip mark (ovw_draw.c mix_view; the levels and latches
 * from csrc/meter/mixer.c, 10 a second). Stock 1.12 (measured in the emulator, scratch probe_funcmod.py): FUNC + [MOD]
 * opens the MIXER on the PRESS (Compressor 1/5; again on the MIXER: the next page), shows its value view while held
 * and changes nothing on the release. So the press is held back whenever FUNC is down at MOD's press (no stock
 * question): let go before the second, the tap is played (FUNC held through it, ovw_poll mix_play) and stock opens or
 * steps its MIXER as before, a tap's length later; held the second, the overview; let go, the screen of before the
 * press (the User: "release returns to where the User was"). Another key or knob while it is held: no overview, no
 * tap (as FX). Stock's value view of a FUNC + [MOD] hold on the MIXER is given up.
 *
 * 2026-11-21 (the User: "it would make more sense to put the CPU/RAM overview on a long press of the METRONOME button
 * and not FUNC click-and-hold"; the DN2's metronome is METRO on the [TEMPO] screen): [TEMPO] held a second shows the
 * big system meter (csrc/meter/meter.c mtr_big) while it stays held; FUNC alone is stock's again. And (the User:
 * "SAMPLE BROWSER on a long press of PRESET"): [PRESET] held a second opens the sample browser for the active track
 * (rec.c smp_fb_from_preset; browse only, no LOAD TO TRK, on a track with no sample machine); it stays up after the
 * release. Stock 1.12 (measured in the emulator, scratch probe_tempo.py, probe_preset.py): [TEMPO] and [PRESET]
 * act on the RELEASE only (the TEMPO screen, the PRESET / KIT menu; the same after a 1.4 s hold), their press and
 * hold change nothing; FUNC + [TEMPO] is tap tempo, FUNC + [PRESET] PERFORM KIT, both untouched. So they are watched
 * as VOICE is: every item goes on to stock but the release of a hold that showed the meter or opened the browser.
 *
 * rec.c smp_ui_pop calls ovw_key before its own "key we took" bookkeeping (FX's release must reach us); page.c wr_poll
 * calls ovw_poll, wr_screen ovw_draw over everything of ours (the system meter's corner, FUNC held, comes after). */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
#define D __attribute__((section(".data")))

#include "../waverider/amp_pages.h"

#define KEY_HELD      ((int (*)(u32))0x4011FAC4u)                 /* (code) -> 1 while held (ins.c) */
#define PANEL_BUTTONS ((void (*)(u32, u32))0x4011FC8Cu)            /* (channel, mask): the panel's button byte (devtest.c) */
#define PANEL_LAST    ((volatile u8 *)0x445A2E30u)                 /* each channel's last mask */
#define TICK          (*(volatile u32 *)0x466768B0u)               /* the panel tick, 0..4095 */
#define UI_TRACK      (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY        0
#define IT_KNOB       1
#define F_PRESS       0x01u
#define F_REPEAT      0x08u
#define F_RELEASE     0x10u
#define K_TRIG        1u                                          /* the [TRIG] page key: the scope, held */
#define K_SYN         2u
#define K_FLTR        3u
#define K_AMP         4u
#define K_FX          5u
#define K_MOD         6u
#define K_FUNC        17u
#define FUNC_CH       2u                                          /* FUNC: the panel's channel 2, bit 0 */
#define MIX_PLAY_TICKS 3u                                         /* a played FUNC + MOD: its release this many ticks on */
#define K_PRESET      7u                                          /* the sample browser, held */
#define K_TEMPO       9u                                          /* the big system meter, held */
#define K_VOICE       50u                                         /* the VOICE key (docs/ui-map.md; the panel's channel 6, bit 0) */
#define PAGE_CH       0u                                          /* codes 1..8: channel (code - 1) >> 3 = 0, */
#define BIT_OF(code)  ((code) - 1u)                               /* bit (code - 1) & 7 */
#define LONG_TICKS    121u                                        /* one second (the User: "hold longer") */
#define REDRAW_TICKS  30u                                         /* the overview drawn again: FUL, the loads (4 a s) */
#define MIX_REDRAW_TICKS 12u                                      /* the MIXER overview: 10 a second (its levels' rate) */
#define REPLAY_TICKS  60u                                         /* a played tap not seen in half a second: given up */

enum { OWN_NONE, OWN_OURS, OWN_STOCK, OWN_WATCH };   /* WATCH: SYN, FLTR, MOD: stock's, the hold watched */
enum { OV_INS = 1, OV_SYN, OV_FLT, OV_LFO, OV_AMP, OV_VOICE, OV_MIX };  /* ovw_up: which overview (ovw_draw.c) */

/* the frame alone (as the scope's, csrc/scope/scope.c): the panel's buffers and stock's canvas and diff */
#define SET_DIRTY     ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY      ((u8 (*)(void *))0x4011D5D4u)               /* move.b: only %d0's low byte */
#define FB_FRONT      (*(u8 *volatile *)0x402A10C8u)
#define FB_BACK       (*(u8 *volatile *)0x402A10CCu)              /* the frame on the glass, between presents */
#define LOOP_BUF      (*(u8 **)0x4059E1B0u)                       /* the UI loop's canvas buffer: panel_diff's return */
#define CANVAS_NEW    ((void (*)(void *, int, int, u8 *, void *))0x40113E2Au)
#define CANVAS_AID    ((void *)0x4059DDB0u)
#define PANEL_DIFF    ((u32 (*)(void))0x40131FD2u)                /* in %d0: a u32, never a pointer */
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))

static int fx_own D = OWN_NONE;          /* who has the page key that is down */
static u32 hk D = 0;                     /* which: K_SYN .. K_MOD */
static u32 fx_at D = 0;                  /* its press, in ticks */
static int fx_long D = 0;                /* held a second, or another key / knob came: its release does nothing */
static int fx_stock D = 0;               /* the press went on to stock's FX page (its value view) */
static int fx_other D = 0;               /* ... from another page (other_page): stock enters page 1 on the press */
static int ovw_shown D = 0;              /* the overview came this hold (another key closed it: not again) */
static int fx_mod D = 0;                 /* another key or knob came while held: FX a modifier, no overview */
int ovw_up D = 0;                        /* the overview up (OV_*; 0 none; the checks read it) */
static int tap_due D = 0;                /* a tap to play (ovw_poll) */
static int replay D = 0;                 /* items of a played tap still to come (its press, its release) */
static u32 rk D = 0;                     /* ... of this key */
static u32 replay_at D = 0;
static u32 redraw_at D = 0;
static u8 *ovw_back D = 0;               /* the last full draw's buffer, the overview on top of it */
static int voice_drop D = 0;             /* the VOICE overview came this hold: its release is dropped */
u32 ovw_alone D = 0, ovw_fulls D = 0;    /* redraws alone, full redraws asked (the checks) */
u32 ovw_pass D = 0;                      /* ins_pop (K_FX), scope_pop (K_AMP): this press is stock's alone (no step) */
u32 ovw_opens D = 0, ovw_taps D = 0;     /* overviews opened, taps played (the checks) */
int ovw_mix_k D = 0;                     /* FUNC + MOD's press held back: this MOD is the MIXER overview's */
static int mix_play D = 0;               /* a FUNC + MOD tap to play: 1 the press due, 2 the release due */
static int mix_func D = 0;               /* ... FUNC pressed by us for it (the User had let it go) */
static u32 mix_play_at D = 0;
u32 ovw_mix_taps D = 0;
static int tempo_big D = 0;              /* the big meter is up from this [TEMPO] hold */
u32 ovw_tempo_opens D = 0, ovw_preset_opens D = 0;   /* (the checks) long [TEMPO], long [PRESET] */                  /* (the checks) FUNC + MOD taps played */

static u32 ticks_since(u32 at)
{
    return (TICK - at) & 0xFFFu;
}

static void dirty(void)
{
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
}

static void close_overview(void)
{
    if (ovw_up) {
        ovw_up = 0;
        dirty();
    }
}

int ovw_visible(void)
{
    return ovw_up;
}

int ovw_fx_held(void)                    /* ins.c: our FX key down, no overview yet: the INSERT page's values */
{
    return fx_own == OWN_OURS && hk == K_FX && !ovw_up;
}

static int stock_page(u32 code)          /* the key's own stock page is up: its press goes on to stock (values) */
{
    extern int ins_fx_page(void);
    extern int ins_up;
    extern int amp_stock_page(void);     /* csrc/scope/scope.c */
    return code == K_FX ? !ins_up && ins_fx_page() : amp_stock_page();
}

static int page_key(u32 code)             /* TRIG (the scope), SYN, FLTR, AMP, FX, MOD */
{
    return code >= K_TRIG && code <= K_MOD;
}

static int kind_of(u32 code)
{
    return code == K_FX ? OV_INS : code == K_SYN ? OV_SYN : code == K_FLTR ? OV_FLT : code == K_MOD ? OV_LFO
         : code == K_VOICE ? OV_VOICE : OV_AMP;
}

/* TRIG, SYN, FLTR, MOD (stock's: every item goes on): the press noted, the release closes the overview */
static int watch_item(u32 code, u32 flags, int down)
{
    extern int smp_question_up(void);
    extern int scope_visible(void);
    if (down && !(flags & F_REPEAT)) {
        fx_own = KEY_HELD(K_FUNC) || smp_question_up() || (code == K_TRIG && scope_visible()) ? OWN_STOCK : OWN_WATCH;
        hk = code;
        fx_at = TICK;
        fx_long = ovw_shown = fx_mod = 0;
        return 0;
    }
    if (!down) {
        fx_own = OWN_NONE;
        close_overview();
    }
    return 0;
}

static void tempo_down(void)             /* the big meter of a [TEMPO] hold taken down */
{
    extern int mtr_big;
    if (tempo_big) {
        tempo_big = 0;
        mtr_big = 0;
    }
}

/* VOICE, PRESET, TEMPO (stock's: every item goes on but the release of a hold that showed the overview, the big
 * meter or opened the browser) */
static int voice_item(u32 code, u32 flags, int down)
{
    extern int smp_question_up(void);
    if (down && !(flags & F_REPEAT)) {
        fx_own = KEY_HELD(K_FUNC) || smp_question_up() ? OWN_STOCK : OWN_WATCH;
        hk = code;
        fx_at = TICK;
        fx_long = ovw_shown = fx_mod = voice_drop = 0;
        return 0;
    }
    if (down)                            /* its repeats: stock's; once a long [TEMPO] or [PRESET] acted, ours (a
                                          * repeat reads as a press: the browser's page-key test closed it at once) */
        return voice_drop && code != K_VOICE;
    fx_own = OWN_NONE;
    close_overview();
    if (code == K_TEMPO)
        tempo_down();
    int drop = voice_drop;
    voice_drop = 0;
    return drop;
}

/* 2026-11-18 (the User: "the switch to next page on release yes. but coming from another page... it on press down"):
 * neither the key's stock page nor a page of ours of that key is up (FX or AMP from TRIG, SYN, ...). The press, its
 * repeats and its release go on to stock as they come, as TRIG, SYN, FLTR and MOD do: stock enters page 1 on the
 * press, and the release after it steps nothing (stock's own page keys). Held a second, the key's overview still
 * comes (ovw_poll). Before, the press was held back and a tap played after the release: the page came 100 ms later
 * than stock's own (emulator, scripts/emu_page_keys.py: TRIG -> FX 240 ms, TRIG -> FLTR 141 ms) */
static int other_page(u32 code)
{
    extern int ins_fx_page(void);
    extern int ins_up;
    extern int amp_stock_page(void);     /* (the scope up, AMP_SCOPE, is over TRIG's page: another page) */
    return code == K_FX ? !ins_up && !ins_fx_page() : amp_sub != AMP_ENV2 && !amp_stock_page();
}

/* the FX or AMP key's item (press, repeat, release); -> 1 when it is dropped */
static int fx_item(u32 code, u32 flags, int down)
{
    extern int smp_question_up(void);
    if (replay && code == rk) {                        /* a tap we play: on to everyone, as a tap always went */
        replay--;
        return 0;
    }
    if (down && !(flags & F_REPEAT)) {
        if (KEY_HELD(K_FUNC) || smp_question_up()) {
            fx_own = OWN_STOCK;          /* FUNC + FX (the SEND pages), a stock question: stock's, as ever */
            return 0;
        }
        fx_own = OWN_OURS;
        hk = code;
        fx_at = TICK;
        fx_long = 0;
        ovw_shown = 0;
        fx_mod = 0;
        fx_other = other_page(code);
        fx_stock = fx_other || stock_page(code);
        dirty();
        if (fx_stock)
            ovw_pass = code;             /* its stock page (its value view), or another page (page 1): stock's alone */
        return !fx_stock;
    }
    if (down) {                          /* a repeat: the key is held, as stock reads a hold (its first repeat, 24
                                          * ticks, 0.2 s on the unit): its release steps nothing */
        if (fx_own == OWN_OURS)
            fx_long = 1;
        return fx_own == OWN_OURS && !fx_stock;
    }
    int own = fx_own;
    fx_own = OWN_NONE;
    if (own != OWN_OURS)
        return 0;
    int was_long = fx_long || ovw_up;
    close_overview();
    dirty();
    if (!was_long && !fx_other)
        tap_due = 1;                     /* (from another page stock entered page 1 on the press: nothing to play) */
    return !fx_stock;
}

/* MOD with FUNC down at its press (no stock question): the MIXER overview's, every item of it held back; the release
 * of a press that showed no overview and saw no other key plays the tap (ovw_poll) */
static int mix_item(u32 flags, int down)
{
    if (down && !(flags & F_REPEAT)) {
        fx_own = OWN_OURS;
        hk = K_MOD;
        ovw_mix_k = 1;
        fx_at = TICK;
        fx_long = ovw_shown = fx_mod = 0;
        fx_stock = fx_other = 0;
        return 1;
    }
    if (down)
        return 1;                        /* its repeats: stock's value view not shown */
    int tap = !ovw_shown && !ovw_up && !fx_mod;
    fx_own = OWN_NONE;
    ovw_mix_k = 0;
    close_overview();
    if (tap)
        mix_play = 1;
    return 1;
}

/* rec.c smp_ui_pop, every item (not while the RECORDER is up): -> 1 when the item is dropped */
int ovw_key(const u8 *it, u32 code, u32 flags)
{
    int down = (flags & F_PRESS) && !(flags & F_RELEASE);
    /* 2026-11-21: a watched key whose release never came (a stock screen takes some keys' releases itself: MACHINE
     * SEL takes SRC's, measured in the emulator, scripts/emu_line_redraw.py bigmeter) left fx_own set, and every other
     * watched key (VOICE, PRESET, TEMPO) was ignored until that key was pressed again. Another key's press while the
     * watched key is no longer held: the watch is over */
    if (it[0] == IT_KEY && down && !(flags & F_REPEAT) && code != hk && (fx_own == OWN_STOCK || fx_own == OWN_WATCH)
        && !ovw_up && !KEY_HELD(hk))
        fx_own = OWN_NONE;
    if (it[0] == IT_KEY && code == K_MOD) {
        extern int smp_question_up(void);
        if (replay && code == rk) {       /* a FUNC + MOD tap we play: stock's (its MIXER) */
            replay--;
            return 0;
        }
        if (ovw_mix_k)
            return mix_item(flags, down);
        if (fx_own == OWN_NONE && down && !(flags & F_REPEAT) && !mix_play && KEY_HELD(K_FUNC)
            && !smp_question_up())
            return mix_item(flags, down);
    }
    if (it[0] == IT_KEY && (code == K_VOICE || code == K_PRESET || code == K_TEMPO) && (fx_own == OWN_NONE || code == hk))
        return voice_item(code, flags, down);
    if (it[0] == IT_KEY && page_key(code) && ((replay && code == rk) || fx_own == OWN_NONE || code == hk))
        return code == K_FX || code == K_AMP ? fx_item(code, flags, down) : watch_item(code, flags, down);
    if (it[0] == IT_KNOB || (it[0] == IT_KEY && down && !(flags & F_REPEAT))) {
        if (fx_own == OWN_OURS || fx_own == OWN_WATCH)
            fx_long = fx_mod = 1;        /* FX was a modifier: no tap, no overview */
        close_overview();
    }
    return 0;
}

/* the overview's next frame: alone over the glass when the last full draw ended with it on top, that frame is still
 * on the glass and no redraw is due (stock's page is not drawn again under it); else the full redraw */
static void redraw(void *screen)
{
    if (!ovw_back || FB_BACK != ovw_back || (IS_DIRTY(screen) & 0xFFu)) {
        ovw_fulls++;
        dirty();
        return;
    }
    u32 canvas[8];
    CANVAS_NEW(canvas, 128, 64, FB_FRONT, CANVAS_AID);
    extern void ovw_paint(void *c, int kind);
    ovw_paint(canvas, ovw_up);           /* the whole screen: nothing of the frame under it is kept */
    LOOP_BUF = (u8 *)PANEL_DIFF();       /* the loop's canvas buffer: the new FRONT, as its own present leaves it */
    ovw_back = FB_BACK;
    ovw_alone++;
}

/* the FUNC + MOD tap held back (mix_item), played where the panel's keys go in: FUNC down (ours if the User has let it
 * go) and MOD down, then MIX_PLAY_TICKS later MOD up (and our FUNC up), so stock reads FUNC held at MOD's press as a
 * person's FUNC + MOD. Not while MOD is down again on the panel (that press is the User's) */
static void play_mix(void)
{
    u32 sr, bit = 1u << BIT_OF(K_MOD);
    if (mix_play == 1) {
        if (PANEL_LAST[PAGE_CH] & bit) {
            mix_play = 0;
            return;
        }
        __asm__ volatile ("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory");
        u32 f = PANEL_LAST[FUNC_CH];
        mix_func = !(f & 1u);
        if (mix_func)
            PANEL_BUTTONS(FUNC_CH, f | 1u);
        PANEL_BUTTONS(PAGE_CH, PANEL_LAST[PAGE_CH] | bit);
        __asm__ volatile ("move.w %0, %%sr" : : "d"(sr) : "memory");
        replay = 2;
        rk = K_MOD;
        replay_at = mix_play_at = TICK;
        mix_play = 2;
        ovw_mix_taps++;
        return;
    }
    if (ticks_since(mix_play_at) < MIX_PLAY_TICKS)
        return;
    __asm__ volatile ("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory");
    PANEL_BUTTONS(PAGE_CH, PANEL_LAST[PAGE_CH] & ~bit);
    if (mix_func)
        PANEL_BUTTONS(FUNC_CH, PANEL_LAST[FUNC_CH] & ~1u);
    __asm__ volatile ("move.w %0, %%sr" : : "d"(sr) : "memory");
    mix_func = 0;
    mix_play = 0;
}

/* page.c wr_poll, once a UI pass */
void ovw_poll(void *screen)
{
    if (replay && ticks_since(replay_at) > REPLAY_TICKS)
        replay = 0;                      /* never came: the next FX is the panel's own */
    if (mix_play)
        play_mix();
    if (tap_due) {
        tap_due = 0;
        if (!(PANEL_LAST[PAGE_CH] >> BIT_OF(hk) & 1u)) {   /* (down again on the panel: that press is the user's) */
            u32 sr;
            __asm__ volatile ("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory");
            u32 m = PANEL_LAST[PAGE_CH];
            PANEL_BUTTONS(PAGE_CH, m | 1u << BIT_OF(hk));
            PANEL_BUTTONS(PAGE_CH, m);
            __asm__ volatile ("move.w %0, %%sr" : : "d"(sr) : "memory");
            replay = 2;
            rk = hk;
            replay_at = TICK;
            ovw_taps++;
        }
    }
    if ((fx_own == OWN_OURS || fx_own == OWN_WATCH) && !ovw_up && !fx_mod && !ovw_shown
        && ticks_since(fx_at) >= LONG_TICKS) {
        if (KEY_HELD(hk) && hk == K_TRIG) {
            extern int scope_long(void);  /* the scope (csrc/scope/scope.c), up after the release too */
            fx_own = OWN_NONE;
            scope_long();
        } else if (KEY_HELD(hk) && (hk == K_TEMPO || hk == K_PRESET)) {
            fx_long = ovw_shown = voice_drop = 1;   /* (its release: dropped) */
            if (hk == K_TEMPO) {
                extern int mtr_big;
                extern u32 mtr_big_shows;
                mtr_big = tempo_big = 1;  /* the big meter while [TEMPO] stays held (meter.c draws it) */
                mtr_big_shows++;
                ovw_tempo_opens++;
            } else {
                extern void smp_fb_from_preset(void);
                smp_fb_from_preset();     /* the browser (rec.c), up after the release too */
                ovw_preset_opens++;
            }
        } else if (KEY_HELD(hk)) {
            fx_long = 1;                 /* a long hold: no tap on its release */
            ovw_shown = 1;               /* (once a hold) */
            ovw_up = ovw_mix_k ? OV_MIX : kind_of(hk);
            voice_drop = hk == K_VOICE;  /* (its release: dropped, the screen left as before the press) */
            ovw_opens++;
            redraw_at = TICK;
            ovw_back = 0;
            dirty();
        } else {
            fx_own = OWN_NONE;           /* its release went elsewhere: nothing held */
        }
    }
    if (tempo_big) {
        extern int mtr_big;
        if (!mtr_big)
            tempo_big = 0;               /* another key took it down (meter.c mtr_key) */
        else if (!KEY_HELD(K_TEMPO))
            tempo_down();                /* let go (its release item may come later) */
    }
    if (ovw_up && !KEY_HELD(hk)) {
        fx_own = OWN_NONE;
        close_overview();
    }
    if (ovw_up && ovw_up != OV_VOICE
        && ticks_since(redraw_at) >= (ovw_up == OV_MIX ? MIX_REDRAW_TICKS : REDRAW_TICKS)) {   /* (VOICE's: still) */
        redraw_at = TICK;
        redraw(screen);
    }
}

/* page.c wr_screen, after every draw: the overview over everything (its own title bar carries its figures) */
void ovw_draw(void *c)
{
    extern void ovw_paint(void *c, int kind);
    ovw_paint(c, ovw_up);
}

/* page.c wr_screen, at the end of every draw: the next frames may go alone over this one if stock drew it and the
 * overview is on top */
void ovw_end(void *canvas, int drew)
{
    ovw_back = drew && ovw_up ? CANVAS_BUF(canvas) : 0;
}
