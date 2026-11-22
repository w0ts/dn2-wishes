/* The mixer meters and the !CLIP label's source (2026-11-20; scratch/mixer-overview.md; the DSP's side:
 * dnfw.sampler.program levels and dac_guard, dnfw.sampler.machines LV_*).
 *
 * The User (2026-11-20): "the alert" (a CLIP label in the title bar, as DSP / CPU / RAM, csrc/meter/meter.c) and "the
 * level and the clip marks on stock's mixer pages"; "remove the dashes on the right of the fader and use this space
 * for the meter". On stock's MIXER (FUNC + [MOD]): Internal Mixer 2/5 (TRK1..8) and 3/5 (TRK9..16) get a meter in each
 * fader's right tick column, FX Mixer 4/5 one beside each send return's fader and the main outputs (L, R) in the empty
 * cell at the top right, External Mixer 5/5 one beside IN LR. Every other pixel stays stock's.
 *
 *   a meter: 3 px wide (the main's 4), 17 rows (the fader's own), 3 dB a row: the top row lit only at full scale (its
 *            stage's: a track's or a return's Overbridge / USB channel, the analog outputs, the input's converter);
 *            a one-row tick at the highest level of the last 3 s;
 *   a latch: a "!" left of the channel (a track's: in place of its left tick column; the main's left of L), lit
 *            once its stage really clipped while that output was in use, until the page has been on the screen 2 s
 *            after the clip (2026-11-20, the User; until then 2 rows above the meter)
 *
 * The clips come every block in the SPI reply's word 6 (the DSP's bits: 0..15 the tracks' Overbridge channels, 16..18
 * the returns', 19 the main mix as Overbridge gets it, 20 the analog outputs, 21 the input, 22 the recorder at its
 * clamp): mix_clip_in (the audio ISR, link.c) stamps each bit whose output is in use now (mix_live: the analog outputs,
 * the input and the recorder always; Overbridge mode: its main (not the tracks' and returns' own channels: the User,
 * 2026-11-20, "only when it matters"); USB audio mode: the USB OUT pair's channels). The peaks come in the DSP's levels packet (link.c, LV_MAGIC) only while a mixer page with meters is up
 * (mix_want: link.c sends LV_WANT to the pool); mix_lvl_in keeps their largest until the page takes them, 10 times a
 * second. The label (meter.c) is lit for 3 s after any stamped clip (mix_clip_recent).
 *
 * Drawing (as the scope's and the labels' blink, page.c): a full draw of stock's page draws every meter of the page
 * (mix_draw, under any popup of ours); mix_end keeps that buffer when nothing of ours drew over it; then mix_poll's
 * updates, 10 a second, write only the meters that changed into BACK and send their 8-pixel groups; a full redraw
 * only when BACK is not that draw's. */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;
#ifdef MIX_HOST
#define D
#else
#define D __attribute__((section(".data")))
#endif

#ifndef MIX_HOST                                /* (test/test_mixmeter.py compiles this file for the host) */
#define FRAMES (*(volatile u32 *)0x4058F8D4u)                     /* 1,500 a second (the audio ISR's) */
#define TICK   (*(volatile u32 *)0x466768B0u)                     /* the panel tick, 121 a second, 0..4095 */
#define REPLY_W6 (*(volatile u32 *)(0x800053A4u + LV_REPLY_AT))   /* the SPI reply's copy, word 6: halves swapped */
#define USB_MODE (*(volatile u32 *)0x4058F2A8u)                   /* stock 1.12's getter 0x40006c4a: 5 USB audio,
                                                                     6 Overbridge */
#define USB_OUT_ON (*(volatile u8 *)0x80005362u)                  /* USB audio: its OUT pair sent (0x400276b8) */
#define USB_OUT_SEL ((volatile signed char *)0x80005364u)         /* ... L's channel, R's (0x400276dc, 0x40027724) */
#define OWNER ((volatile u32 *)0x80005308u)                        /* each voice slot's track (DN2_OWNER_REG; the
                                                                     DSP's ROUTE is made from it) */
#else
extern volatile u32 mix_host_owner[16];
#define OWNER mix_host_owner
#endif
#define MIXER_VIEW 0x401E292Cu                                    /* stock 1.12's MIXER page view (FUNC + [MOD]), its
                                                                     page 0..4 at +0x90 (measured in the emulator) */
#define SET_DIRTY ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY  ((u8 (*)(void *))0x4011D5D4u)                   /* move.b: only %d0's low byte */
#define FB_BACK   (*(u8 *volatile *)0x402A10CCu)                  /* the frame on the glass, between presents */
#define GLASS_GROUP ((void (*)(u32, u32, const u8 *))0x40131F04u) /* (column 0..120, page 0..7, 8 bytes) */
#define GLASS_SHOW  ((void (*)(void))0x40131EECu)
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))

#define BITS 24                                 /* the DSP's clip bits; 23: a voice's own clip whose track is not known
                                                   (mix_inner_in) */
#define BIT_INNER_ANY 23
#define ROWS 17                                 /* a meter's rows: 3 dB each, the top one full scale */
#define POLL_TICKS 12u                          /* an update 10 times a second */
#define HOLD_FRAMES 4500u                       /* the peak tick: 3 s */
#define SEEN_FRAMES 3000u                       /* a latch goes once its page has been up 2 s after the clip */
#define LABEL_FRAMES 4500u                      /* the CLIP label: 3 s after the last clip */

/* the audio ISR's side (link.c) */
#define MIX_CH LV_CH                            /* the DSP's channels: 22, 23 Overbridge / USB main L, R (2026-11-20: the
                                                   DSP's, from TX slots 0, 1 as sent; until then mix_ob_main's), 24 the
                                                   recorder while it records (2026-11-21, the OUTPUTS overview) */
#define CH_OBL 22
#define CH_OBR 23
#define CH_REC 24
_Static_assert(LV_CH == 25, "the DSP's 25 channels: 22, 23 Overbridge / USB main, 24 the recorder");
volatile u16 mix_acc[2][MIX_CH] D;              /* the peaks since the page last took them, two buffers */
volatile u32 mix_sel D = 0;                     /* the buffer the ISR fills */
volatile u32 mix_clip_at[BITS] D;               /* each bit's last clip in use, frames | 1 (0: none) */
volatile u32 mix_live D = 0;                    /* the bits whose output is in use (mix_poll) */
/* 2026-11-21, the OUTPUTS overview (the User: "I want to see what clips. So only what is not float"; "We have many more
 * track with overbridge"): its own stamps, of every fixed-point output in use, the tracks' and returns' own Overbridge
 * channels included in Overbridge mode. The CLIP label and the MIXER pages' "!" keep mix_clip_at and its 2026-11-20
 * rule ("only when it matters": no track's or return's own channel); a voice's own clips (mix_inner_in) are not here */
volatile u32 mix_ov_clip_at[BITS] D;            /* each bit's last clip in use for the overview, frames | 1 (0: none) */
volatile u32 mix_ov_live D = 0;                 /* the bits whose output is in use for the overview (mix_poll) */
volatile u32 mix_want D = 0;                    /* a mixer page with meters is up: the DSP's levels asked (link.c) */
volatile u32 mix_lvl_n D = 0, mix_clip_n D = 0; /* (the checks) levels packets, clip words with a bit in use */

void mix_lvl_in(const u16 *u)                   /* link.c: a levels packet's LV_CH units */
{
    volatile u16 *a = mix_acc[mix_sel & 1u];
    for (int k = 0; k < LV_CH; k++)
        if (u[k] > a[k])
            a[k] = u[k];
    mix_lvl_n++;
}

void mix_clip_in(void)                          /* link.c: every period, the DSP's clip word */
{
    u32 x = REPLY_W6;
    u32 w = x << 16 | x >> 16;                  /* the DSP's 32-bit store arrives low half first */
    if ((w & 0xFF000000u) != LV_REPLY_MAGIC)
        return;
    /* (bit 19, the main mix as Overbridge gets it: since 2026-11-20 the DSP's test of TX slots 0, 1 as sent, the words
     * the ColdFire's mix_ob_main read before; not the MAIN tap, which stock empties of the internal sound when INT TO
     * MAIN keeps it off the analog outputs: the User's "the main OUT level is zero when Overbridge is connected") */
    w &= (1u << BITS) - 1u;
    u32 f = FRAMES | 1u, o = w & mix_ov_live;
    if (o)
        for (int k = 0; k < BITS; k++)
            if (o >> k & 1u)
                mix_ov_clip_at[k] = f;
    w &= mix_live;
    if (!w)
        return;
    for (int k = 0; k < BITS; k++)
        if (w >> k & 1u)
            mix_clip_at[k] = f;
    mix_clip_n++;
}

/* link.c: a clip packet (2026-11-20, clip-inner; the User: "NO DIGITAL CLIPPING ... if it does, i want the alert"):
 * the voice slots one of whose own stages clipped or limited (the DSP's perc.program.clip_note: DRONE's and
 * ANALOG2's knees past 1 dB, PLAITS' Clip16 and Limiter, the Monomachine decimator's and the Machinedrum's limiters,
 * DRUM's drive and hold, the A2 filter models' holds and knees), the tracks of the per-track stages (the inserts' holds and
 * clamps, a track's XDLY loop knee) and the send returns (the send XDLY's loop knee).
 * Each slot's track (OWNER) stamped as its output's clip would be, in use or not (a voice's own clip always matters):
 * the CLIP label, and the track's "!" on its mixer page */
volatile u32 mix_inner_n D = 0, mix_inner_last D = 0;     /* (the checks) clip packets, the last one's tracks */

void mix_inner_in(u32 slots, u32 tracks, u32 rets)   /* ... and the per-track stages' tracks, the sends' returns */
{
    u32 f = FRAMES | 1u, trk = tracks & 0xFFFFu;
    for (int t = 0; t < 16; t++)
        if (trk >> t & 1u)
            mix_clip_at[t] = f;
    for (int r = 0; r < 3; r++)
        if (rets >> r & 1u)
            mix_clip_at[16 + r] = f;
    for (int s = 0; s < 16; s++) {
        if (!(slots >> s & 1u))
            continue;
        u32 t = OWNER[s];
        if (t < 16u) {
            mix_clip_at[t] = f;
            trk |= 1u << t;
        } else
            mix_clip_at[BIT_INNER_ANY] = f;     /* (no track known: the label still lights) */
    }
    mix_inner_last = trk;
    mix_inner_n++;
}

int mix_clip_recent(u32 f)                      /* meter.c: a clip in use within LABEL_FRAMES */
{
    for (int k = 0; k < BITS; k++) {
        u32 at = mix_clip_at[k];
        if (at && (f | 1u) - at < LABEL_FRAMES)
            return 1;
    }
    return 0;
}

void mix_clip_forget(void)                      /* startup.c: the start-up's clips forgotten (label and latches) */
{
    for (int k = 0; k < BITS; k++)
        mix_clip_at[k] = mix_ov_clip_at[k] = 0;
}

/* -- which outputs are in use -------------------------------------------------------------------------------------- */
u32 mix_chan_bit(int c)                      /* an Overbridge / USB channel (0..41) -> its clip bit */
{
    if (c < 0 || c > 41)
        return 0;
    if (c <= 1)
        return 1u << LV_BIT_MAIN_OB;
    if (c <= 33)
        return 1u << ((c - 2) >> 1);
    if (c <= 39)
        return 1u << (16 + ((c - 34) >> 1));
    return 1u << LV_BIT_IN;
}

u32 mix_live_bits(void)
{
    u32 b = 1u << LV_BIT_DAC | 1u << LV_BIT_IN | 1u << LV_BIT_REC;
    u32 mode = USB_MODE;
    if (mode == 6u)                                     /* Overbridge: its main alone. 2026-11-20 (the User: "only when
                                                         * it matters", after a track at LEVEL 100 lit CLIP from its own
                                                         * channel, ~9 dB hotter than its share of the main): the unit
                                                         * sends every track's and return's channel whenever Overbridge
                                                         * is connected (the packet builder copies them all, no channel
                                                         * mask), so which ones the computer uses is not known here.
                                                         * Their meters still show their levels; no "!", no CLIP */
        b |= 1u << LV_BIT_MAIN_OB;
    else if (mode == 5u && USB_OUT_ON) {
        int l = USB_OUT_SEL[0], r = USB_OUT_SEL[1];     /* USB audio: the pair (or its mono sum) it sends */
        b |= mix_chan_bit(l) | mix_chan_bit(l + 1) | mix_chan_bit(r) | mix_chan_bit(r - 1);
    }
    return b;
}

u32 mix_ov_live_bits(u32 live)                  /* the OUTPUTS overview: in Overbridge mode every track's and return's own
                                                   channel too (each a fixed-point output the unit sends) */
{
    return USB_MODE == 6u ? live | 0x7FFFFu : live;
}

/* -- the pages' meters ---------------------------------------------------------------------------------------------- */
typedef struct {
    u8 ch, x, w, top;                           /* the channel, its columns x .. x + w - 1, its top glass row */
    u8 bx, dash;                                /* its "!" (2026-11-20, the User: "a '!' on the left of the channel ...
                                                   when it is clipping"; then "move the ! a few pixels to the left": 1 px):
                                                   columns bx, bx + 1 (0: none), the meter's rows; DASH: stock's tick
                                                   column (dash, dash + 1: its ticks at rows 0, 4, .. 16), blank while the
                                                   "!" shows (0: none) */
} Meter;

/* glass rows from the top: the top row of faders spans rows 13..29, the bottom row 40..56; a track's left tick column
 * is the fader's x - 13, x - 12 (read off stock's pages); the returns' and IN LR's "!" 2 columns left of their faders */
static const Meter PAGE2[8] = {{0, 39, 3, 13, 25, 26}, {1, 65, 3, 13, 51, 52}, {2, 91, 3, 13, 77, 78},
                               {3, 117, 3, 13, 103, 104}, {4, 39, 3, 40, 25, 26}, {5, 65, 3, 40, 51, 52},
                               {6, 91, 3, 40, 77, 78}, {7, 117, 3, 40, 103, 104}};
static const Meter PAGE3[8] = {{8, 39, 3, 13, 25, 26}, {9, 65, 3, 13, 51, 52}, {10, 91, 3, 13, 77, 78},
                               {11, 117, 3, 13, 103, 104}, {12, 39, 3, 40, 25, 26}, {13, 65, 3, 40, 51, 52},
                               {14, 91, 3, 40, 77, 78}, {15, 117, 3, 40, 103, 104}};
static const Meter PAGE4[5] = {{16, 40, 3, 40, 24, 0}, {17, 66, 3, 40, 50, 0}, {18, 92, 3, 40, 76, 0},
                               {19, 106, 4, 13, 101, 0}, {20, 112, 4, 13, 0, 0}};   /* (the main's one "!", with L) */
static const Meter PAGE5[1] = {{21, 40, 3, 13, 24, 0}};
#define OUT_X0 102                              /* FX Mixer 4/5: the empty cell the main's meters take */
#define OUT_X1 120
#define OUT_Y0 12
#define OUT_Y1 30

static const Meter *page_meters(int pg, int *n)
{
    switch (pg) {
    case 1: *n = 8; return PAGE2;
    case 2: *n = 8; return PAGE3;
    case 3: *n = 5; return PAGE4;
    case 4: *n = 1; return PAGE5;
    default: *n = 0; return 0;
    }
}

static u32 ch_bits(int ch)                      /* a meter's clip bits */
{
    if (ch < 19)
        return 1u << ch;
    if (ch < 21)
        return 1u << LV_BIT_DAC | 1u << LV_BIT_MAIN_OB;
    return 1u << LV_BIT_IN;
}

/* 10^((3 j - 51) / 20) x LV_ONE for j = 1..17: a peak at TH[j - 1] or more lights j rows (the 17th: full scale) */
static const u16 TH[ROWS] = {65, 92, 130, 184, 260, 367, 518, 732, 1034, 1460, 2063, 2914, 4115, 5813, 8211,
                             11599, 16384};

int mix_rows_of(u32 peak)
{
    int j = 0;
    while (j < ROWS && peak >= TH[j])
        j++;
    return j;
}

/* 2026-11-21, the OUTPUTS overview (FUNC + [MOD] held a second, csrc/inserts/ovw.c; drawn by ovw_draw.c mix_view; it
 * replaces that day's MIXER overview. The User: "I want to see what clips. So only what is not float, by definition";
 * "We have many more track with overbridge"; scratch/outputs-ovw-mock2.png): every fixed-point output, each a bar of
 * OVW_PX pixels, 48 dB (~1.26 dB a pixel), the top one its own full scale: 10^(-(OVW_PX - k) x 48 / OVW_PX / 20) x
 * LV_ONE for k = 1..OVW_PX (a peak at OTH[k - 1] or more lights k pixels) */
#define OVW_PX 38
#define OVW_CH 25                               /* 0..15 the tracks' own Overbridge / USB channels, 16..18 the returns',
                                                   19, 20 Overbridge / USB main L R, 21, 22 the analog outputs L R, 23
                                                   the input, 24 the recorder */
#define PG_OVW 9                                /* shown_pg: the overview */
static const u8 OV_UNIT[OVW_CH] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, CH_OBL, CH_OBR,
                                   19, 20, 21, CH_REC};      /* each bar's levels-packet unit */
static const u8 OV_BIT[OVW_CH] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, LV_BIT_MAIN_OB,
                                  LV_BIT_MAIN_OB, LV_BIT_DAC, LV_BIT_DAC, LV_BIT_IN, LV_BIT_REC};   /* ... its clip bit */
#define OV_MIX 7                                /* ovw.c ovw_up */
static const u16 OTH[OVW_PX] = {75, 87, 101, 117, 135, 156, 181, 209, 241, 279, 323, 374, 432, 500, 578, 668, 773,
                                894, 1034, 1196, 1383, 1599, 1849, 2139, 2474, 2861, 3309, 3827, 4426, 5119, 5920,
                                6847, 7918, 9158, 10591, 12249, 14166, 16384};
static u8 ov_lit[OVW_CH] D, ov_hold[OVW_CH] D, ov_mark[OVW_CH] D;
static u32 ov_hold_at[OVW_CH] D, ov_ack[OVW_CH] D;
u32 mix_ovw_takes D = 0;                        /* (the checks) the overview's level takes */

static int px_of(u32 peak)
{
    int j = 0;
    while (j < OVW_PX && peak >= OTH[j])
        j++;
    return j;
}

/* each channel's state as last computed, and as last drawn */
static u8 lit[MIX_CH] D, hold[MIX_CH] D, latch[MIX_CH] D;
static u32 hold_at[MIX_CH] D, ack[MIX_CH] D;
static u8 d_lit[MIX_CH] D, d_hold[MIX_CH] D, d_latch[MIX_CH] D;
static u8 *drawn D = 0;                         /* the buffer the last full draw drew the page's meters into (0: none) */
static int drawn_pg D = -1;
static int shown_pg D = -1;                     /* the page up at the last poll (-1: none of ours) */
static u32 shown_at D = 0;                      /* since when (frames) */
static u32 poll_tick D = 0;
u32 mix_alone D = 0, mix_fulls D = 0, mix_groups D = 0;   /* (the checks) updates alone, full redraws asked, groups */
volatile u32 mix_off D = 0;                     /* (the checks: scripts/emu_mixmeter.py) the meters off, stock's page */
u32 mix_why D = 0, mix_draws D = 0;             /* (the checks) why the last update was not alone (1 no buffer, 2 not
                                                   on the glass, 3 another page, 4 a redraw due); full draws with meters */

static int ov_in_use(int ch)                    /* a bar's output in use now: the recorder while it records */
{
    extern int rec_state;
    if (ch == OVW_CH - 1)
        return rec_state == 2;
    return (int)(mix_ov_live >> OV_BIT[ch] & 1u);
}

/* ovw_draw.c mix_view: bar CH's pixels lit, its peak tick (0: none), its clip mark (its output clipped while in use,
 * until the overview has been up 2 s after it), its output in use; CH -1: the USB mode (5 USB audio, 6 Overbridge)
 * -> lit | hold << 8 | mark << 16 | in use << 17 */
u32 mix_ovw_get(int ch)
{
    if (ch < 0)
        return USB_MODE;
    if (ch >= OVW_CH)
        return 0;
    return (u32)ov_lit[ch] | (u32)ov_hold[ch] << 8 | (u32)(ov_mark[ch] != 0) << 16 | (u32)ov_in_use(ch) << 17;
}

static int mixer_any(void)                      /* stock's MIXER up, nothing of ours over it: its page 0..4, else -1 */
{
    extern u32 ins_view_of(u32 cls);
    extern int smp_question_up(void), wpop_shown(void), mxp_visible(void), ldp_visible(void), ovw_visible(void);
    extern int mtr_big;
    u32 v = ins_view_of(MIXER_VIEW);
    if (!v)
        return -1;
    u32 pg = *(volatile u32 *)(v + 0x90);
    if (pg > 4u || smp_question_up() || wpop_shown() || mxp_visible() || ldp_visible() || ovw_visible() || mtr_big)
        return -1;
    return (int)pg;
}

static int mixer_page(void)                     /* ... one with meters: 1..4 (2/5..5/5), else -1 */
{
    int pg = mix_off ? -1 : mixer_any();
    return pg >= 1 ? pg : -1;
}

/* the MIXER overview up over stock's MIXER (FUNC + [MOD] held there): stock's full redraws held as on the MIXER, so
 * the overview (drawn over each) is not drawn 30 times a second */
static int mixer_under_ovw(void)
{
    extern u32 ins_view_of(u32 cls);
    extern int ovw_up;
    return ovw_up == OV_MIX && ins_view_of(MIXER_VIEW) != 0;
}

/* The UI loop's redraw test (page.c wr_poll's answer, which stock's isDirty call at 0x4002e464 takes). 2026-11-20, the
 * User (the CPU on the MIXER: stock redraws its five pages in full 30 times a second, ~3.9 % of the CPU on the unit):
 * "10 per sec is fine even... we want to see what the levels are about and the !. this is not mission critical". On
 * the MIXER, nothing of ours over it, a redraw stock asks for is held until MIX_DRAW_TICKS after the last one (10 a
 * second, whether anything moves or not), except right after a key or knob item (rec.c smp_input_seq): then at once.
 * Stock's flag stays set meanwhile, so the held redraw comes at the next pass due. Everywhere else stock's answer */
#define MIX_DRAW_TICKS 12u                      /* panel ticks (121 a second): a full draw 10 times a second */
static u32 thr_at D = 0, thr_seq D = 0;
u32 mix_held D = 0, mix_let D = 0;              /* (the checks) redraws held, let through on the MIXER */
volatile u32 mix_thr_off D = 0;                 /* (the checks: scripts/emu_mixcpu.py) stock's redraws as they come */

u32 mix_dirty(int dirty)                        /* -> DIRTY, or 0: held */
{
    extern u32 smp_input_seq;
    u32 d = (u32)dirty;
    if (!d || mix_thr_off || (mixer_any() < 0 && !mixer_under_ovw()))
        return d;
    u32 t = TICK, seq = smp_input_seq;
    if (seq != thr_seq || ((t - thr_at) & 0xFFFu) >= MIX_DRAW_TICKS) {
        thr_seq = seq;
        thr_at = t;
        mix_let++;
        return d;
    }
    mix_held++;
    return 0;
}

/* column x, glass rows g0 + r for each bit r of ROWS_M: set to that bit of ON (2026-11-20, the User's CPU on the MIXER:
 * stock redraws these pages in full 30 times a second, and every draw redrew the meters pixel by pixel with put(),
 * ~34,000 instructions for Internal Mixer 2/5's eight; a column's bytes at once, the same pixels) */
static void put_col(u8 *b, int x, int g0, u32 rows_m, u32 on)
{
    u32 sh = (u32)g0 & 7u;
    u32 m = rows_m << sh, v = (on & rows_m) << sh;
    u8 *q = b + 8 * x + (7 - (g0 >> 3));
    for (; m; m >>= 8, v >>= 8, q--) {          /* the next glass page down: the byte before */
        u8 mm = (u8)m;
        *q = (u8)((*q & ~mm) | (v & mm));
    }
}

#define ALL_ROWS ((1u << ROWS) - 1u)

/* bit r (row r of the meter, 0 the top) of each column, exactly as the row-by-row draw before put_col left them */
static void draw_meter(u8 *b, const Meter *m)
{
    int ch = m->ch, n = lit[ch], h = hold[ch];
    u32 on = n > 0 ? ALL_ROWS & ~((1u << (ROWS - n)) - 1u) : 0u;   /* rows ROWS - n .. ROWS - 1: the lit ones */
    if (h > n && h > 0)
        on |= 1u << (ROWS - h);                 /* the peak tick */
    for (int x = m->x; x < m->x + m->w; x++)
        put_col(b, x, m->top, ALL_ROWS, on);
    if (!m->bx)
        return;
    int bang = ch == 19 ? latch[19] || latch[20] : latch[ch];   /* (the main's: either side's bits) */
    /* "!": a stem of 12 rows, 3 dark, a dot of 2; else stock's ticks (rows 0, 4, .. 16) */
    u32 mark = bang ? 0xFFFu | 3u << 15 : 0u, tick = bang ? 0u : 0x11111u;
    if (m->dash) {                              /* (the tick column first: the "!" overlaps its left column) */
        put_col(b, m->dash, m->top, ALL_ROWS, tick);
        put_col(b, m->dash + 1, m->top, ALL_ROWS, tick);
    }
    put_col(b, m->bx, m->top, ALL_ROWS, mark);
    /* bx + 1: on every row when it is not the tick column; else only where the mark is lit (the tick's elsewhere) */
    put_col(b, m->bx + 1, m->top, !m->dash || m->bx + 1 < m->dash ? ALL_ROWS : mark, mark);
}

static const u8 OUT_GLYPHS[3][5] = {{7, 5, 5, 5, 7}, {5, 5, 5, 5, 7}, {7, 2, 2, 2, 2}};   /* O U T, bit 2 left */

static void draw_out_cell(u8 *b)                /* FX Mixer 4/5: the empty cell cleared, OUT under it */
{
    for (int x = OUT_X0; x <= OUT_X1; x++)
        put_col(b, x, OUT_Y0, (1u << (OUT_Y1 - OUT_Y0 + 1)) - 1u, 0u);
    for (int i = 0; i < 3; i++)
        for (int c = 0; c < 3; c++) {
            u32 col = 0;
            for (int r = 0; r < 5; r++)
                col |= (u32)(OUT_GLYPHS[i][r] >> (2 - c) & 1u) << r;
            put_col(b, 105 + 4 * i + c, 31, 0x1Fu, col);
        }
}

static void remember(int pg)
{
    int n;
    const Meter *ms = page_meters(pg, &n);
    for (int i = 0; i < n; i++) {
        int ch = ms[i].ch;
        d_lit[ch] = lit[ch];
        d_hold[ch] = hold[ch];
        d_latch[ch] = latch[ch];
    }
    if (pg == 3) {
        d_latch[19] = latch[19];
        d_latch[20] = latch[20];
    }
}

/* page.c wr_screen: stock's page drawn (no page of ours over it); its meters into the canvas */
void mix_draw(void *canvas)
{
    int pg = mixer_page();
    drawn = 0;
    if (pg < 0)
        return;
    u8 *b = CANVAS_BUF(canvas);
    if (pg == 3)
        draw_out_cell(b);
    int n;
    const Meter *ms = page_meters(pg, &n);
    for (int i = 0; i < n; i++)
        draw_meter(b, &ms[i]);
    remember(pg);
    drawn = b;
    drawn_pg = pg;
    mix_draws++;
}

/* ... the frame complete: CLEAN, nothing of ours drew over the page (else no update alone over it) */
void mix_end(void *canvas, int clean)
{
    if (!clean || !drawn || drawn != CANVAS_BUF(canvas))
        drawn = 0;
}

static void take_levels(u32 f, int ovw)         /* the ISR's peaks since the last take -> each channel's rows (OVW:
                                                   the overview's pixels too) */
{
    u32 s = mix_sel & 1u;
    mix_sel = s ^ 1u;                           /* (a packet the ISR was adding to the old buffer: in the next take) */
    volatile u16 *a = mix_acc[s];
    u32 v[MIX_CH];
    for (int ch = 0; ch < MIX_CH; ch++) {
        v[ch] = a[ch];
        a[ch] = 0;
    }
    if (ovw)                                    /* (the overview: each output alone, in its own scale) */
        for (int ch = 0; ch < OVW_CH; ch++) {
            int k = ov_in_use(ch) ? px_of(v[OV_UNIT[ch]]) : 0;
            ov_lit[ch] = (u8)k;
            if (k >= ov_hold[ch] || f - ov_hold_at[ch] > HOLD_FRAMES) {
                ov_hold[ch] = (u8)k;
                ov_hold_at[ch] = f;
            }
        }
    if (mix_live >> LV_BIT_MAIN_OB & 1u) {      /* OUT: the main outputs in use, each in its own scale, the hotter */
        if (v[CH_OBL] > v[19])
            v[19] = v[CH_OBL];
        if (v[CH_OBR] > v[20])
            v[20] = v[CH_OBR];
    }
    for (int ch = 0; ch < LV_CH; ch++) {
        int n = mix_rows_of(v[ch]);
        lit[ch] = (u8)n;
        if (n >= hold[ch] || f - hold_at[ch] > HOLD_FRAMES) {
            hold[ch] = (u8)n;
            hold_at[ch] = f;
        }
    }
}

static void take_latches(int pg, u32 f)         /* each latch from the stamps; one seen 2 s on its page goes */
{
    int n;
    const Meter *ms = page_meters(pg, &n);
    for (int ch = 0; ch < LV_CH; ch++) {
        u32 bits = ch_bits(ch), at = 0;
        for (int k = 0; k < BITS; k++)
            if (bits >> k & 1u && mix_clip_at[k] && (!at || (int)(mix_clip_at[k] - at) > 0))
                at = mix_clip_at[k];
        int on = at && (int)(at - ack[ch]) > 0;
        if (on) {
            int here = 0;
            for (int i = 0; i < n; i++)
                here |= ms[i].ch == ch;
            u32 from = (int)(at - shown_at) > 0 ? at : shown_at;
            if (here && (f | 1u) - from >= SEEN_FRAMES) {
                ack[ch] = at;
                on = 0;
            }
        }
        latch[ch] = (u8)on;
    }
}

static int alone(void *screen, int pg)          /* the meters that changed into BACK, their groups sent -> done */
{
    u8 *b = drawn;
    mix_why = !b ? 1u : FB_BACK != b ? 2u : drawn_pg != pg ? 3u : (IS_DIRTY(screen) & 0xFF) ? 4u : 0u;
    if (mix_why)
        return 0;
    int n;
    const Meter *ms = page_meters(pg, &n);
    u32 groups[8];                              /* [glass page]: bit = column group */
    for (int p = 0; p < 8; p++)                 /* (no memset in this chunk) */
        groups[p] = 0;
    for (int i = 0; i < n; i++) {
        int ch = ms[i].ch;
        int lat = ch == 19 || ch == 20 ? (latch[19] || latch[20]) != (d_latch[19] || d_latch[20])
                                       : latch[ch] != d_latch[ch];      /* (the main's "!" is drawn with L) */
        if (lit[ch] == d_lit[ch] && hold[ch] == d_hold[ch] && !lat)
            continue;
        draw_meter(b, &ms[i]);
        for (int g = ms[i].top; g < ms[i].top + ROWS; g += 1) {
            int p = 7 - (g >> 3);
            for (int x = ms[i].x; x < ms[i].x + ms[i].w; x++)
                groups[p] |= 1u << (x >> 3);
            if (ms[i].bx) {
                groups[p] |= 1u << (ms[i].bx >> 3);
                groups[p] |= 1u << ((ms[i].bx + 1) >> 3);
            }
            if (ms[i].dash)
                groups[p] |= 1u << ((ms[i].dash + 1) >> 3);
        }
    }
    remember(pg);
    int sent = 0;
    for (u32 p = 0; p < 8u; p++)
        for (u32 c = 0; c < 16u; c++) {
            if (!(groups[p] >> c & 1u))
                continue;
            u32 col = 8u * c;                   /* (c <= 15: column 120 at most) */
            u8 bytes[8];
            for (u32 k = 0; k < 8u; k++)
                bytes[k] = b[8u * (col + k) + p];
            GLASS_GROUP(col, p, bytes);
            sent++;
        }
    if (sent)
        GLASS_SHOW();
    mix_groups += (u32)sent;
    mix_alone++;
    return 1;
}

/* the OUTPUTS overview's marks from its own stamps (mix_ov_clip_at); one seen 2 s on the overview goes */
static void take_ov_marks(u32 f)
{
    for (int ch = 0; ch < OVW_CH; ch++) {
        u32 at = mix_ov_clip_at[OV_BIT[ch]];
        int on = at && (int)(at - ov_ack[ch]) > 0;
        if (on) {
            u32 from = (int)(at - shown_at) > 0 ? at : shown_at;
            if ((f | 1u) - from >= SEEN_FRAMES) {
                ov_ack[ch] = at;
                on = 0;
            }
        }
        ov_mark[ch] = (u8)on;
    }
}

/* page.c wr_poll, every pass (under the big meter's test: nothing of ours alone under its box) */
/* the OUTPUTS overview up (ovw.c, OV_MIX): the DSP's levels asked, taken 10 times a second; ovw.c redraws it at that
 * rate (ovw_draw.c mix_view reads mix_ovw_get). Opened: every bar from zero, the levels from the DSP's next packets */
static void ovw_poll_levels(u32 f)
{
    mix_want = 1;
    if (shown_pg != PG_OVW) {
        shown_pg = PG_OVW;
        shown_at = f | 1u;
        for (int k = 0; k < MIX_CH; k++)
            mix_acc[0][k] = mix_acc[1][k] = 0;
        for (int ch = 0; ch < OVW_CH; ch++)
            ov_lit[ch] = ov_hold[ch] = 0;
        take_ov_marks(f);                       /* (the marks at once, from the first picture) */
        poll_tick = TICK;
        return;
    }
    if (((TICK - poll_tick) & 0xFFFu) < POLL_TICKS)
        return;
    poll_tick = TICK;
    take_levels(f, 1);
    take_ov_marks(f);
    mix_ovw_takes++;
}

void mix_poll(void *screen)
{
    mix_live = mix_live_bits();
    mix_ov_live = mix_ov_live_bits(mix_live);
    u32 f = FRAMES;
    {
        extern int ovw_up;
        if (ovw_up == OV_MIX) {
            ovw_poll_levels(f);
            return;
        }
    }
    int pg = mixer_page();
    if (pg != shown_pg) {
        shown_pg = pg;
        shown_at = f | 1u;
    }
    mix_want = pg > 0;
    if (pg < 0)
        return;
    if (((TICK - poll_tick) & 0xFFFu) < POLL_TICKS)
        return;
    poll_tick = TICK;
    take_levels(f, 0);
    take_latches(pg, f);
    if (alone(screen, pg))
        return;
    if (!drawn || drawn_pg != pg) {             /* the page's meters not drawn yet: one full redraw draws them */
        mix_fulls++;
        SET_DIRTY(screen);
    }
}
