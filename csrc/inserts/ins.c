/* The per-track inserts' page and values (docs/inserts.md), OS 1.12.
 *
 * [FX] pressed on the track's FX page opens the INSERT page for the active track; [FX] again, NO,
 * or any page key closes it. While it is up its eight knobs are ours (rec.c smp_ui_pop hands
 * every item to ins_pop first) and draws over the screen with stock's own widgets (page.c
 * wr_screen; csrc/waverider/widgets.h), keeping stock's left panel:
 *
 *     A M.SEL (OFF FUZZ TAPE FOLD CHOR WIDE HARM, each a band of 0..127)   B..G the insert's six
 *     knobs   H MOD (dry/wet)
 *
 * Each track keeps every insert's knobs (switching M.SEL and back keeps them). The values go to
 * the DSP in the sample pool's directory page (dnfw.inserts.design.PAR, 16 x 8 bytes: M.SEL, MOD,
 * the active insert's six), sent by the link (link.c smp_tdm) whenever ins_gen moves.
 * Phase A: the values live in RAM only (not saved with the kit), and are not lockable.
 */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed char s8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define TEXT      ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573Cu)
#define FONT      0x44508ED8u
#define CENTRED   2
#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY    0
#define IT_KNOB   1
#define IT_DROP   0xFF
#define K_FX      5
#define K_NO      12
#define TYPES     7                             /* OFF and the six */
static const u8 BUILT[TYPES] = {1, 1, 1, 1, 0, 0, 1};   /* what this build runs (CHOR, WIDE: not yet) */

static const char *const NAME[TYPES] = {"OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM"};
static const char *const LABEL[TYPES][6] = {
    {"", "", "", "", "", ""},
    {"DRIV", "TONE", "BIAS", "PRE", "GATE", "LEV"},
    {"DRIV", "WOW", "WRAT", "FLUT", "AGE", "HISS"},
    {"AMNT", "SYMM", "SHPE", "TONE", "LEV", ""},
    {"DPTH", "RATE", "DLY", "VOIC", "WDTH", "FDBK"},
    {"WDTH", "TIME", "BASS", "TONE", "", ""},
    {"AMNT", "FREQ", "EVEN", "TONE", "LEV", ""},
};
static const u8 DEFAULT[TYPES][6] = {
    {0, 0, 0, 0, 0, 0}, {64, 90, 0, 30, 0, 100}, {50, 30, 20, 25, 50, 10}, {80, 64, 0, 100, 100, 0},
    {50, 30, 40, 2, 100, 0}, {90, 20, 40, 30, 0, 0}, {50, 70, 64, 80, 100, 0},
};

u8 ins_sel[16] __attribute__((section(".data")));    /* the type (from ins_selv's band) */
u8 ins_selv[16] __attribute__((section(".data")));   /* M.SEL as turned, 0..127: each type a band of it */
u8 ins_mod[16] __attribute__((section(".data")));
u8 ins_kv[16][TYPES][6] __attribute__((section(".data")));
u32 ins_gen __attribute__((section(".data"))) = 0;      /* moves on every change: the link sends */
int ins_up __attribute__((section(".data"))) = 0;       /* the page is up */
static int ins_inited __attribute__((section(".data"))) = 0;
static u32 last_key __attribute__((section(".data"))) = 0;   /* the last page key pressed */

static void init(void)
{
    if (ins_inited)
        return;
    for (int t = 0; t < 16; t++) {
        ins_sel[t] = 0;
        ins_selv[t] = 0;
        ins_mod[t] = 127;
        for (int y = 0; y < TYPES; y++)
            for (int k = 0; k < 6; k++)
                ins_kv[t][y][k] = DEFAULT[y][k];
    }
    ins_inited = 1;
    ins_gen++;
}

/* the 32 words the DSP reads: track t's bytes 8t .. 8t + 7, little-endian words */
void ins_words(u32 *w)
{
    init();
    for (int t = 0; t < 16; t++) {
        u8 b[8];
        int y = ins_sel[t];
        b[0] = (u8)y;
        b[1] = ins_mod[t];
        for (int k = 0; k < 6; k++)
            b[2 + k] = ins_kv[t][y][k];
        w[2 * t] = b[0] | (u32)b[1] << 8 | (u32)b[2] << 16 | (u32)b[3] << 24;
        w[2 * t + 1] = b[4] | (u32)b[5] << 8 | (u32)b[6] << 16 | (u32)b[7] << 24;
    }
}

static int clamp(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

static void turn(int knob, int delta)
{
    int t = UI_TRACK & 15;
    if (knob == 1) {
        /* as a stock multi-choice: turned as a 0..127 knob, each type a band of about 18 of it
         * (OFF 0..18, FUZZ 19..36, .. HARM 110..127), so a type takes a seventh of a turn of the
         * range, not one step; the value is what a p-lock would keep */
        ins_selv[t] = (u8)clamp(ins_selv[t] + delta, 0, 127);
        ins_sel[t] = (u8)(ins_selv[t] * TYPES / 128);
    } else if (knob == 8) {
        ins_mod[t] = (u8)clamp(ins_mod[t] + delta, 0, 127);
    } else {
        int y = ins_sel[t];
        if (y && LABEL[y][knob - 2][0])
            ins_kv[t][y][knob - 2] = (u8)clamp(ins_kv[t][y][knob - 2] + delta, 0, 127);
    }
    ins_gen++;
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
}

/* from rec.c smp_ui_pop, before its own handling: 1 when the item is ours (it is then dropped) */
int ins_pop(u8 *it)
{
    init();
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int press = (flags & 1u) && !(flags & 0x10u);
    extern int smp_overlay_dirty;
    if (ins_up && it[0] == IT_KEY && code >= 41 && code <= 48)
        return 1;                               /* an encoder's push (and its release): ours while up, so
                                                 * the stock page under it does not switch to its values */
    if (it[0] == IT_KEY && press && !(flags & 8u)) {
        if (code == K_FX) {
            int was = last_key;
            last_key = K_FX;
            if (ins_up) {
                ins_up = 0;
                smp_overlay_dirty = 1;
                return 1;                       /* (the FX page shows again) */
            }
            if (was == K_FX) {
                ins_up = 1;
                smp_overlay_dirty = 1;
                return 1;
            }
            return 0;
        }
        if (code <= 9 || (code >= 16 && code <= 24))
            last_key = code;                    /* another page or screen */
        if (ins_up && code == K_NO) {
            ins_up = 0;
            smp_overlay_dirty = 1;
            return 1;
        }
        if (ins_up && (code <= 9 || (code >= 16 && code <= 24))) {
            ins_up = 0;                         /* the key does what it does; the page closes */
            smp_overlay_dirty = 1;
        }
        return 0;
    }
    if (ins_up && it[0] == IT_KNOB && code >= 1 && code <= 8) {
        turn((int)code, (s8)it[8]);
        return 1;
    }
    return 0;
}

int ins_visible(void)
{
    return ins_up;
}

#include "../waverider/widgets.h"       /* stock 1.12's own widgets (docs/widgets.md) */

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
}

/* after stock's screen (page.c wr_screen), while the page is up. Stock's track [FX] page is under
 * it: its title bar (pattern, name, tempo) and left panel (the track box, LEV) are kept as stock drew
 * them; the eight places are ours, drawn with stock's widgets: A M.SEL a choice, B..G the insert's knobs, H MOD a
 * knob, each with stock's label; an unused place is left empty */
void ins_draw(void *c)
{
    init();
    int t = UI_TRACK & 15, y = ins_sel[t];
    fill(c, 22, 0, 127, 53, 0);                 /* the places; stock's title bar and left panel stay */
    wg_choice(c, 0, NAME[y]);
    wg_label(c, 0, BUILT[y] ? "M.SEL" : "SOON");    /* CHOR, WIDE: not in this build yet */
    for (int k = 0; k < 6; k++) {
        if (!LABEL[y][k][0])
            continue;
        wg_knob(c, k + 1, ins_kv[t][y][k]);
        wg_label(c, k + 1, LABEL[y][k]);
    }
    wg_knob(c, 7, ins_mod[t]);
    wg_label(c, 7, "MOD");
}
