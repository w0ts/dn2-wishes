/* The per-track inserts' page and values (docs/inserts.md), OS 1.12.
 *
 * The FX key's pages are two: FX 1/2, stock's track FX page, and FX 2/2, the INSERT page of the
 * active track (2026-11-09, the User). [FX] on FX 1/2 opens FX 2/2, [FX] on FX 2/2 goes back to
 * FX 1/2, [FX] anywhere else is stock's (to FX 1/2); FUNC + [FX] is stock's alone (the three SEND
 * pages, never the INSERT page). On each switch the title bar says "FX (1/2)" / "FX (2/2)" with
 * stock's own message line (SAY, as stock's "Delay (1/3)"), and both pages show stock's page dots
 * (two, the current one filled). NO or any page key closes FX 2/2. While it is up its eight knobs are ours (rec.c smp_ui_pop hands
 * every item to ins_pop first) and draws over the screen with stock's own widgets (page.c
 * wr_screen; csrc/waverider/widgets.h), keeping stock's left panel:
 *
 *     A M.SEL (OFF FUZZ TAPE FOLD CHOR WIDE HARM, each a band of 0..127)   B..G the insert's six
 *     knobs   H MIX (dry/wet)
 *
 * Each track keeps every insert's knobs (switching M.SEL and back keeps them). The values go to
 * the DSP in the sample pool's directory page (dnfw.inserts.design.PAR, 16 x 8 bytes: M.SEL, MIX,
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
#define K_FUNC    17
#define KEY_HELD  ((int (*)(u32))0x4011FAC4u)                 /* (code) -> 1 while held (jump.c) */
#define SAY       ((void (*)(void *, void *))0x4005628Cu)     /* a message line's text, its slide in */
#define STR_NEW   ((void (*)(void *, const char *, void *))0x401CEAB8u)   /* std::string(s, alloc) */
#define STR_SET   ((void (*)(void *, const void *))0x401CC46Cu)          /* std::string = (SAY's) */
#define STR_FREE  ((void (*)(void *))0x401CD008u)
#define PAGE_DOTS ((void (*)(void *, void *, int, int, int))0x4006598Au) /* (-, canvas, n, page, 7) */
/* the screen's views (rec.c smp_question_up's walk); classes measured in the 1.12 emulator: the
 * track FX page's view, and the title bar's, whose +120 is the message line SAY writes (its text a
 * std::string at +0x48: "FX" on entering the FX page, "Delay (1/3)" .. on the SEND pages) */
#define FX_PAGE_VTABLE 0x401E1448u
#define TITLE_VTABLE   0x401E1D28u
#define TYPES     7                             /* OFF and the six */
static const u8 BUILT[TYPES] = {1, 1, 1, 1, 1, 1, 1};   /* what this build runs (CHOR, WIDE: after the pan) */

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
    {50, 50, 40, 64, 100, 0}, {90, 20, 40, 80, 0, 0}, {50, 70, 64, 80, 100, 0},
};

u8 ins_sel[16] __attribute__((section(".data")));    /* the type (from ins_selv's band) */
u8 ins_selv[16] __attribute__((section(".data")));   /* M.SEL as turned, 0..127: each type a band of it */
u8 ins_mod[16] __attribute__((section(".data")));
u8 ins_kv[16][TYPES][6] __attribute__((section(".data")));
u32 ins_gen __attribute__((section(".data"))) = 0;      /* moves on every change: the link sends */
int ins_up __attribute__((section(".data"))) = 0;       /* the page is up */
static int ins_inited __attribute__((section(".data"))) = 0;
static int title_due __attribute__((section(".data"))) = 0;  /* draws left to rename stock's "FX" */

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

static int ram_ok(u32 a)
{
    return a >= 0x40000000u && a < 0x48000000u && !(a & 3);
}

static u32 view_of(u32 cls)                     /* the screen's view of class CLS, or 0 */
{
    extern void *wr_screen_obj;
    u32 s = (u32)wr_screen_obj;
    if (!ram_ok(s))
        return 0;
    u32 node = *(volatile u32 *)(s + 28);
    for (int n = 0; n < 32 && ram_ok(node) && node != s + 20; n++) {
        u32 v = *(volatile u32 *)(node + 8);
        if (ram_ok(v) && *(volatile u32 *)v == cls)
            return v;
        node = *(volatile u32 *)node;
    }
    return 0;
}

static void *title(void)                        /* the title bar's message line, or 0 */
{
    u32 v = view_of(TITLE_VTABLE);
    u32 m = v ? *(volatile u32 *)(v + 120) : 0;
    return ram_ok(m) ? (void *)m : 0;
}

static void say(const char *text, int slide)    /* slide: as stock's switch; else the text alone */
{
    static u32 str[4] __attribute__((section(".data")));
    static u32 alloc __attribute__((section(".data")));
    void *m = title();
    if (!m)
        return;
    str[0] = str[1] = str[2] = str[3] = 0;
    STR_NEW(str, text, &alloc);
    if (slide)
        SAY(m, str);
    else
        STR_SET((u8 *)m + 0x48, str);
    STR_FREE(str);
}

/* hooks.S ins_hdr_tail, at the exit of stock's mode header 0x40063f56 (mode, a0 = the std::string
 * it returns): the mode's page name, with " (n/m)" only when the mode has two pages or more. The
 * track FX mode has one, so stock's header for it is a bare "FX", and every route to the page that
 * shows the header (from a SEND page, whose header mode stock keeps) showed "FX". Here a bare "FX"
 * becomes "FX (1/2)", or "FX (2/2)" while the INSERT page is up: the header as stock would make
 * it for a mode of two pages. No other mode is named "FX". */
void ins_header(void *s)
{
    static u32 str[4] __attribute__((section(".data")));
    static u32 alloc __attribute__((section(".data")));
    const char *t = s && ram_ok((u32)s) ? *(const char *volatile *)s : 0;
    if (!(t && ram_ok((u32)t & ~3u) && t[0] == 'F' && t[1] == 'X' && t[2] == 0))
        return;
    str[0] = str[1] = str[2] = str[3] = 0;
    STR_NEW(str, ins_up ? "FX (2/2)" : "FX (1/2)", &alloc);
    STR_SET(s, str);
    STR_FREE(str);
}

int ins_fx_page(void)                           /* stock's track FX page is the page */
{
    return view_of(FX_PAGE_VTABLE) != 0;
}

/* page.c wr_screen, before stock draws: while FX 1/2 is up, any "FX" of stock's in the title bar's
 * message line is renamed "FX (1/2)" (stock puts "FX" there entering the page; from the SEND pages it
 * does not slide it in, so ins_dots slides ours in after the first draw on the page) */
void ins_title(void)
{
    if (ins_up || !(title_due || ins_fx_page()))
        return;
    void *m = title();
    const char *t = m ? *(const char *volatile *)((u8 *)m + 0x48) : 0;
    int fx = t && ram_ok((u32)t & ~3u) && t[0] == 'F' && t[1] == 'X' && t[2] == 0;
    if (fx)                                     /* stock's "FX": renamed (its slide, if any, kept) */
        say("FX (1/2)", 0);
    if (title_due && !ins_fx_page())
        title_due--;
}

/* page.c wr_screen, after stock's page, when no page of ours covers it: FX 1/2's dots */
void ins_dots(void *c)
{
    if (!ins_up && ins_fx_page()) {
        PAGE_DOTS(0, c, 2, 0, 7);
        if (title_due) {                        /* just entered by FX: "FX (1/2)" slides in (after
                                                 * stock's own draw, which sets the page's header) */
            title_due = 0;
            say("FX (1/2)", 1);
        }
    }
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
            if (KEY_HELD(K_FUNC)) {             /* FUNC + FX: stock's SEND pages, as stock */
                if (ins_up) {
                    ins_up = 0;
                    smp_overlay_dirty = 1;
                }
                title_due = 0;
                return 0;
            }
            if (ins_up) {                       /* FX 2/2 -> FX 1/2 (stock's page, under ours) */
                ins_up = 0;
                smp_overlay_dirty = 1;
                say("FX (1/2)", 1);
                return 1;
            }
            if (ins_fx_page()) {                /* FX 1/2 -> FX 2/2 */
                ins_up = 1;
                smp_overlay_dirty = 1;
                say("FX (2/2)", 1);
                return 1;
            }
            title_due = 40;                     /* stock goes to FX 1/2: its "FX" renamed */
            return 0;
        }
        if (ins_up && code == K_NO) {
            ins_up = 0;
            smp_overlay_dirty = 1;
            return 1;
        }
        /* b6 (the User: VOICE from FX 2/2 showed both screens): every key closes the page but the
         * ones that belong on it (FUNC, YES and the arrows 10..15, the trig keys 25..40, the encoder
         * pushes 41..48); a list of the closing keys missed VOICE (49), the arpeggiator (53), note
         * edit (55) and others, whose stock screens then had the page drawn over them */
        if (ins_up && !(code == K_FUNC || (code >= 10 && code <= 15) || (code >= 25 && code <= 48))) {
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
 * them; the eight places are ours, drawn with stock's widgets: A M.SEL a choice, B..G the insert's knobs, H MIX a
 * knob, each with stock's label; an unused place is left empty */
void ins_draw(void *c)
{
    init();
    int t = UI_TRACK & 15, y = ins_sel[t];
    fill(c, 22, 0, 127, 53, 0);                 /* the places; stock's title bar and left panel stay */
    wg_choice(c, 0, NAME[y]);
    wg_label(c, 0, BUILT[y] ? "M.SEL" : "SOON");    /* a type a build does not run yet */
    for (int k = 0; k < 6; k++) {
        if (!LABEL[y][k][0])
            continue;
        wg_knob(c, k + 1, ins_kv[t][y][k]);
        wg_label(c, k + 1, LABEL[y][k]);
    }
    wg_knob(c, 7, ins_mod[t]);
    wg_label(c, 7, "MIX");
    PAGE_DOTS(0, c, 2, 1, 7);                   /* FX 2/2 */
}
