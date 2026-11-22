/* The page keys' overviews, drawn (2026-11-17, the User: "lets try them all, we can revert what we dont like").
 * csrc/inserts/ovw.c decides when one is up (a page key held a second) and which; this file draws it. The picture of
 * each, pixel for pixel, is dnfw.overviews (and dnfw.inserts.overview for FX's); scripts/emu_overviews.py holds the
 * emulator's screens to it.
 *
 * One layout for all five: the title bar (rows 0..8 lit, a text unlit at each end), tracks 1-8 then 9-16, each a
 * numbers row (the active track lit) over two cell rows, a cell 15 px wide every 16 px, 9 rows tall. A cell is a
 * kind and a text (dnfw.overviews: DOT PLAIN LIT FRAME BLINK MARKS COUNT).
 * VOICE's (2026-11-19, voice_view) has the same title bar and numbers, then three rows a track, 7 px apart.
 *
 * Cost (the User, 2026-11-17: our pages' clears were one stock SET_PIXEL call a pixel): nothing runs while no overview
 * is up. Up, the screen is cleared and the boxes filled a column word at a time (page.c cv_fill), and the letters'
 * pixels set in the canvas's words directly; ovw.c redraws it 4 times a second, alone over the glass when it can (as
 * the scope's frames, csrc/scope). The data is read when it is drawn: every track's sound in the kit, the routes
 * record, the VOICE BUDGET's per-track costs; no state kept. Row 0 is the top (the canvas counts y up from the bottom).
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;

#include "ovw_font.h"
#include "../para/para.h"

#define TICK        (*(volatile u32 *)0x466768B0u)               /* the panel tick (ovw.c) */
#define UI_TRACK    (*(volatile u8 *)0x42432A6Cu)
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define SOUND(t)    (KIT_POINTER + 52u + 1163u * (u32)(t))
#define MUTE_MASK   (*(volatile u32 *)0x80005218u)               /* the global mutes, bit t (docs/mute-research.md) */
#define SOLO_MASK   (*(volatile u32 *)0x8000521Cu)               /* the solos: any set, the others are silent */
#define PTN_MUTE    (*(volatile u16 *)0x4058E888u)               /* the pattern's mutes */
#define BLINK_TICKS 60u                                          /* FUL on / off, half a second each */
#define FRAME_CYCLES 666667u                                     /* the DSP's frame, cycles (dnfw.load) */
#define MIDI_TYPE   4
/* stock's voice setup, as VoiceMenuView's draw (0x400282c6) reads it: the UI's model, its voice setup, and per track the
 * VOICES and UNISON the VOICE menu shows (5 bytes a track: +1 VOICES, +2 bit 7 clear UNISON on), the DYN pool */
#define UI_OWNER    ((u32 (*)(void))0x4018AC5Au)                /* the UI's model (vmenu.c) */
#define VS_HOLDER   ((u32 (*)(u32))0x4003E41Au)                  /* (model) -> what holds the voice setup */
#define VS_OBJ      ((u32 (*)(u32))0x40030AF8u)                  /* (holder) -> the voice setup */
#define VS_VOICES   ((u32 (*)(u32, u32))0x40029054u)             /* (vs, t) -> VOICES: 0 DYN, n fixed (a signed byte) */
#define VS_UNISON   ((u32 (*)(u32, u32))0x40029126u)             /* (vs, t) -> UNISON on (a byte; led.c) */
#define VS_POOL     ((u32 (*)(u32))0x40028FFCu)                  /* (vs) -> the DYN pool: 16 less the fixed voices */

enum { C_DOT, C_PLAIN, C_LIT, C_FRAME, C_BLINK, C_MARKS, C_COUNT, C_BLANK, C_ICON, C_ICON_LIT };   /* ICON: a the FX type */
enum { OV_INS = 1, OV_SYN, OV_FLT, OV_LFO, OV_AMP, OV_VOICE, OV_MIX };  /* ovw.c ovw_up */

struct cell {
    u8 kind, a, m, pad;                  /* MARKS: a the bits; COUNT: a in use, m muted */
    const char *s;
    u32 pad2;                            /* 12 bytes: an 8-byte stride is a scaled index the ColdFire lacks */
};

extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);   /* page.c: y up from the bottom */

/* -- drawing: row 0 the top ---------------------------------------------------------------------------------------- */

static void box(void *c, int x0, int r0, int x1, int r1, int on)
{
    cv_fill(c, x0, 63 - r1, x1, 63 - r0, on);
}

static void px(void *c, int x, int r, int on)  /* one pixel in the canvas's words (as cv_fill reads the canvas) */
{
    const int *h = (const int *)c;
    int y = 63 - r;
    if (x < 0 || x >= h[1] || y < 0 || y >= h[2])
        return;
    u32 *w = (u32 *)h[4] + x * h[3] + (y >> 5), b = 1u << (31 - (y & 31));
    if (on)
        *w |= b;
    else
        *w &= ~b;
}

static void frame(void *c, int x0, int r0, int x1, int r1)
{
    box(c, x0, r0, x1, r0, 1);
    box(c, x0, r1, x1, r1, 1);
    box(c, x0, r0, x0, r1, 1);
    box(c, x1, r0, x1, r1, 1);
}

static void text(void *c, int x, int r, const char *s, int on)
{
    for (; *s; s++, x += 4) {
        int g = 0;
        while (OVW_CHARS[g] && OVW_CHARS[g] != *s)
            g++;
        u32 bits = OVW_CHARS[g] ? OVW_GLYPH[g] : 0;
        for (int y = 0; y < 5; y++)
            for (int k = 0; k < 3; k++)
                if (bits >> (14 - 3 * y - k) & 1u)
                    px(c, x + k, r + y, on);
    }
}

static int width(const char *s)
{
    int n = 0;
    while (s[n])
        n++;
    return 4 * n - 1;
}

static char *num(char *p, int v)         /* v 0..999 */
{
    if (v >= 100)
        *p++ = (char)('0' + v / 100);
    if (v >= 10)
        *p++ = (char)('0' + v / 10 % 10);
    *p++ = (char)('0' + v % 10);
    *p = 0;
    return p;
}

static char *put(char *p, const char *s)
{
    while (*s)
        *p++ = *s++;
    *p = 0;
    return p;
}

/* a cell's text, 3 letters at most (4 letters fill the 16 px pitch and run into the next cell): a longer name loses its
 * first vowel after the first letter, else (two digits at its end) its second letter, else its last
 * (dnfw.overviews.short3: STRG STR, SL12 S12, FUSE FSE) */
static const char *short3(const char *s, char *b)
{
    int n = 0;
    while (s[n])
        n++;
    if (n <= 3)
        return s;
    int drop = n - 1;
    for (int i = n - 1; i >= 1; i--)
        if (s[i] == 'A' || s[i] == 'E' || s[i] == 'I' || s[i] == 'O' || s[i] == 'U')
            drop = i;
    if (drop == n - 1 && !(s[n - 1] == 'A' || s[n - 1] == 'E' || s[n - 1] == 'I' || s[n - 1] == 'O' || s[n - 1] == 'U')
        && s[n - 1] >= '0' && s[n - 1] <= '9' && s[n - 2] >= '0' && s[n - 2] <= '9')
        drop = 1;
    int k = 0;
    for (int i = 0; i < n && k < 3; i++)
        if (i != drop)
            b[k++] = s[i];
    b[k] = 0;
    return b;
}

static void cell(void *c, int x, int r0, const struct cell *e, int blink_on)
{
    char sb[4];
    const char *s = short3(e->s ? e->s : "", sb);
    int tx = x + (15 - width(s)) / 2;
    switch (e->kind) {
    case C_DOT:
        px(c, x + 7, r0 + 4, 1);
        break;
    case C_PLAIN:
        text(c, tx, r0 + 2, s, 1);
        break;
    case C_LIT:
        box(c, x, r0, x + 14, r0 + 8, 1);
        text(c, tx, r0 + 2, s, 0);
        break;
    case C_BLINK:
        if (!blink_on)
            break;
        /* fall through */
    case C_FRAME:
        frame(c, x, r0, x + 14, r0 + 8);
        text(c, tx, r0 + 2, s, 1);
        break;
    case C_MARKS:
        for (int k = 0; k < 4; k++) {
            int mx = x + 2 + 3 * k;
            if (e->a >> k & 1u)
                box(c, mx, r0 + 2, mx + 1, r0 + 6, 1);
            else
                px(c, mx, r0 + 4, 1);
        }
        break;
    case C_ICON_LIT:                     /* (2026-11-20, the User: the FX icons in the overview) a lit box, the */
        box(c, x, r0, x + 14, r0 + 8, 1);    /* insert's icon unlit in its middle */
        /* fall through */
    case C_ICON: {                       /* the icon, lit, in the cell's middle (dnfw.waverider.msel FX_ICONS) */
        extern const u8 *msel_fx_icon(int type);
        const u8 *ic = msel_fx_icon(e->a);
        for (int r = 0; ic && r < 5; r++)
            for (int i = 0; i < 7; i++)
                if (ic[r] >> (6 - i) & 1)
                    px(c, x + 4 + i, r0 + 2 + r, e->kind == C_ICON);
        break;
    }
    case C_COUNT: {
        char b[4];
        if (e->a) {
            num(b, e->a > 99 ? 99 : e->a);
            box(c, x, r0, x + 8, r0 + 8, 1);
            text(c, x + (9 - width(b)) / 2, r0 + 2, b, 0);
        }
        if (e->m) {
            num(b, e->m > 9 ? 9 : e->m);
            text(c, x + 11, r0 + 2, b, 1);
        }
        if (!e->a && !e->m)
            px(c, x + 7, r0 + 4, 1);
        break;
    }
    default:
        break;
    }
}

/* the title bar's two texts and the track numbers (the active one lit), every overview's */
static void head(void *c, const char *left, const char *right)
{
    box(c, 0, 0, 127, 63, 0);
    box(c, 0, 0, 127, 8, 1);
    text(c, 2, 2, left, 0);
    text(c, 126 - width(right), 2, right, 0);
    int cur = UI_TRACK & 15;
    for (int t = 0; t < 16; t++) {
        int x = 16 * (t & 7), rb = 10 + 27 * (t >> 3);
        char s[4];
        num(s, t + 1);
        int tx = x + (15 - width(s)) / 2;
        if (t == cur) {
            box(c, x + 1, rb - 1, x + 14, rb + 5, 1);
            text(c, tx, rb, s, 0);
        } else {
            text(c, tx, rb, s, 1);
        }
    }
}

/* the whole screen: the head, every track's two cells */
static void layout(void *c, const char *left, const char *right, const struct cell (*cells)[2])
{
    head(c, left, right);
    int blink_on = !((TICK / BLINK_TICKS) & 1u);
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++)
            cell(c, 16 * (t & 7), 10 + 27 * (t >> 3) + 7 + 10 * j, &cells[t][j], blink_on);
}

/* -- the five overviews' cells ------------------------------------------------------------------------------------ */

static const char *const NAME3[] = {"", "FUZ", "TAP", "FLD", "CHO", "WID", "HRM", "FDN", "XDL", "SUB", "DST", "GAT",
                                    "RNG", "JUN"};   /* by type number (ins.c NAME); dnfw.inserts.overview.NAME3 */
/* the filter machines by sound+0xDF (dnfw.overviews.FILTER3) */
static const char *const FILTER3[] = {"MLT", "LP4", "EQ", "CB-", "LEG", "CB+", "", "SVF", "LAD", "OTA", "DIO", "M20"};

static int muted(int t)
{
    u32 solo = SOLO_MASK & 0xFFFFu;
    return (MUTE_MASK >> t & 1u) || (PTN_MUTE >> t & 1u) || (solo && !(solo >> t & 1u));
}

static int no_sound(int t)               /* no kit, or a MIDI track */
{
    return !KIT_POINTER || (s8)SOUND(t)[0xDE] < 0 || (s8)SOUND(t)[0xDE] == MIDI_TYPE;
}

static void ins_view(void *c, struct cell (*cells)[2])
{
    extern int ins_slot_state(int t, int j, int *type);   /* 0 OFF, 1 MIX 0, 2 the DSP runs it, 3 FULL */
    extern int smp_dsp_load(void);
    int n = 0;
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++) {
            int y, st = ins_slot_state(t, j, &y);
            struct cell *e = &cells[t][j];
            e->s = y > 0 && y < (int)(sizeof NAME3 / sizeof NAME3[0]) ? NAME3[y] : "";
            e->a = (u8)y;                /* (2026-11-20) a slot that runs, or at MIX 0: its icon, not its letters */
            e->kind = st == 0 ? C_DOT : st == 3 ? C_BLINK : st == 2 ? C_ICON_LIT : C_ICON;
            if (st == 3)
                e->s = "FUL";
            n += st == 2;
        }
    char l[16], r[12], *p = put(l, "INSERTS ");
    p = num(p, n);
    put(p, "/32");
    int d = smp_dsp_load();
    p = put(r, "DSP ");
    if (d >= 0)
        put(num(p, d > 999 ? 999 : d), "%");
    else
        put(p, "--");
    layout(c, l, r, (const struct cell (*)[2])cells);
}

static void syn_view(void *c, struct cell (*cells)[2])
{
    extern void wr_ovw_names(int t, const char **mach, const char **eng);   /* page.c */
    int n = 0;
    for (int t = 0; t < 16; t++) {
        const char *m = 0, *e = 0;
        if (KIT_POINTER)
            wr_ovw_names(t, &m, &e);
        int mu = muted(t);
        n += mu;
        cells[t][0].kind = m && *m ? (mu ? C_FRAME : C_LIT) : C_DOT;
        cells[t][0].s = m;
        cells[t][1].kind = e && *e ? C_PLAIN : C_DOT;
        cells[t][1].s = e;
    }
    char r[12];
    num(put(r, "MUTED "), n);
    layout(c, "MACHINES", r, (const struct cell (*)[2])cells);
}

static void flt_view(void *c, struct cell (*cells)[2])
{
    extern const char *wr_ovw_flt2(int t);   /* page.c: ANALOG 2's own FLT2, 0 on any other machine */
    for (int t = 0; t < 16; t++) {
        if (no_sound(t)) {
            cells[t][0].kind = cells[t][1].kind = C_DOT;
            continue;
        }
        int f = SOUND(t)[0xDF];
        const char *a = f < (int)(sizeof FILTER3 / sizeof FILTER3[0]) ? FILTER3[f] : "";
        const char *b = wr_ovw_flt2(t);
        cells[t][0].kind = *a ? C_LIT : C_DOT;
        cells[t][0].s = a;
        cells[t][1].kind = b ? C_PLAIN : C_DOT;   /* (the User, 2026-11-18: a dot, not BW, on every other machine) */
        cells[t][1].s = b;
    }
    layout(c, "FILTERS", "", (const struct cell (*)[2])cells);
}

static void lfo_view(void *c, struct cell (*cells)[2])
{
    extern int mxp_ovw_counts(u32 t, int *marks, int *active, int *muted);   /* routes_pop.c: -> LFO pool used */
    int pool = 0, mu = 0;
    for (int t = 0; t < 16; t++) {
        int marks = 0, a = 0, m = 0;
        if (!no_sound(t))
            pool += mxp_ovw_counts((u32)t, &marks, &a, &m);
        mu += m;
        cells[t][0].kind = C_MARKS;
        cells[t][0].a = (u8)marks;
        cells[t][1].kind = C_COUNT;
        cells[t][1].a = (u8)(a > 99 ? 99 : a);
        cells[t][1].m = (u8)(m > 99 ? 99 : m);
    }
    char l[20], r[12];
    put(num(put(l, "LFO POOL "), pool > 999 ? 999 : pool), "/256");
    num(put(r, "MUTED "), mu > 999 ? 999 : mu);
    layout(c, l, r, (const struct cell (*)[2])cells);
}

static int pct(u32 cycles)               /* the share of the frame, rounded, at least 1 when anything (dnfw.overviews.pct) */
{
    if (!cycles)
        return 0;
    u32 p = (cycles * 100u + FRAME_CYCLES / 2u) / FRAME_CYCLES;   /* (cycles < 42,000,000: no overflow) */
    return p ? (int)p : 1;
}

static void amp_view(void *c, struct cell (*cells)[2])
{
    extern int load_ovw(int t, u32 *cycles);   /* load.c: track t's voices sounding, its DSP cycles */
    extern int smp_dsp_load(void);
    extern int mtr_cpu_pct(void);              /* meter.c: C, -1 none */
    static char txt[16][2][6] __attribute__((section(".data")));
    u32 cyc[16], top = 0;
    int v[16], nv = 0, busiest = -1;
    for (int t = 0; t < 16; t++) {
        cyc[t] = 0;
        v[t] = load_ovw(t, &cyc[t]);
        cyc[t] = cyc[t] > 40000000u ? 40000000u : cyc[t];
        nv += v[t];
        if (cyc[t] > top) {
            top = cyc[t];
            busiest = t;
        }
    }
    for (int t = 0; t < 16; t++) {
        char *p = num(txt[t][0], v[t] > 16 ? 16 : v[t]);
        put(p, "V");
        cells[t][0].kind = v[t] ? C_PLAIN : C_DOT;
        cells[t][0].s = txt[t][0];
        int q = pct(cyc[t]);
        put(num(txt[t][1], q > 999 ? 999 : q), "%");
        cells[t][1].kind = !q ? C_DOT : t == busiest ? C_LIT : C_PLAIN;
        cells[t][1].s = txt[t][1];
    }
    char l[16], r[20], *p;
    put(num(put(l, "VOICES "), nv > 99 ? 99 : nv), "/16");
    int cp = mtr_cpu_pct(), d = smp_dsp_load();
    p = put(r, "C ");
    p = cp >= 0 ? put(num(p, cp > 999 ? 999 : cp), "%") : put(p, "--");
    p = put(p, " D ");
    if (d >= 0)
        put(num(p, d > 999 ? 999 : d), "%");
    else
        put(p, "--");
    layout(c, l, r, (const struct cell (*)[2])cells);
}

/* -- the VOICE key's overview (2026-11-19, the User: "which tracks are in which mode -- unison, para -- and number of
 * voices"): three rows a track, 7 px apart (dnfw.overviews.voice_render): the machine, the mode, the VOICES ----------- */

/* a 7-row cell at row R: DOT, PLAIN, LIT (a lit box, the text unlit) or FRAME (an outline, the text lit) */
static void cell7(void *c, int x, int r, int kind, const char *s)
{
    char sb[4];
    s = short3(s ? s : "", sb);
    int tx = x + (15 - width(s)) / 2;
    if (kind == C_DOT) {
        px(c, x + 7, r + 3, 1);
    } else if (kind == C_LIT) {
        box(c, x, r, x + 14, r + 6, 1);
        text(c, tx, r + 1, s, 0);
    } else {
        if (kind == C_FRAME)
            frame(c, x, r, x + 14, r + 6);
        text(c, tx, r + 1, s, 1);
    }
}

/* track T's mode: PAR (ANALOG 2 or JUNO with PARA ON; UNISON is ignored there), UNI (UNISON on), MON (one fixed voice),
 * PLY; 0 on a MIDI track or with no machine */
static const char *voice_mode(int t, u32 vs, int v)
{
    int ty = KIT_POINTER ? (s8)SOUND(t)[0xDE] : -1;
    if (ty < 0 || ty == MIDI_TYPE || !vs)
        return 0;
    if (para_track(t) && para_value(t))
        return "PAR";
    if (VS_UNISON(vs, (u32)t) & 0xFFu)
        return "UNI";
    return v == 1 ? "MON" : "PLY";
}

static void voice_view(void *c)
{
    extern void wr_ovw_names(int t, const char **mach, const char **eng);   /* page.c */
    u32 owner = UI_OWNER(), vs = owner ? VS_OBJ(VS_HOLDER(owner)) : 0;
    int pool = vs ? (int)VS_POOL(vs) : 0;
    char r[12];
    num(put(r, "DYN "), pool < 0 ? 0 : pool > 16 ? 16 : pool);
    head(c, "VOICE SETUP", r);
    for (int t = 0; t < 16; t++) {
        int x = 16 * (t & 7), rb = 10 + 27 * (t >> 3);
        const char *m = 0, *e = 0;
        if (KIT_POINTER)
            wr_ovw_names(t, &m, &e);
        cell7(c, x, rb + 6, m && *m ? C_PLAIN : C_DOT, m);
        int v = vs ? (s8)(VS_VOICES(vs, (u32)t) & 0xFFu) : 0;
        const char *mode = voice_mode(t, vs, v);
        if (!mode) {
            cell7(c, x, rb + 13, C_DOT, "");
            cell7(c, x, rb + 20, C_DOT, "");
            continue;
        }
        cell7(c, x, rb + 13, mode[1] == 'A' ? C_LIT : mode[0] == 'U' ? C_FRAME : C_PLAIN, mode);
        char b[4];
        num(b, v > 16 ? 16 : v);
        cell7(c, x, rb + 20, C_PLAIN, v <= 0 ? "DYN" : b);
    }
}

/* 2026-11-21, the OUTPUTS overview (FUNC + [MOD] held a second; it replaces that day's MIXER overview. The User: "I want
 * to see what clips. So only what is not float, by definition"; "We have many more track with overbridge";
 * scratch/outputs-ovw-mock2.png, his OK): every fixed-point output, a bar each, rows 15..52 (38 px, 48 dB, the top pixel
 * its own full scale, csrc/meter/mixer.c OTH): the 16 tracks' own Overbridge / USB channels (3 px on a 4 px pitch from
 * x 1), the send returns D R C, Overbridge / USB main L R, the analog outputs L R, the input, the recorder (4 px each).
 * An output in use: a floor row, its level from the bottom, its peak of the last 3 s a one-row tick; not in use: a
 * dotted column. A clip mark (its output clipped while in use, until the overview has been up 2 s): a block at rows
 * 10..13 above the bar, its group's name white on black on row 59, its name in the title ("CLIP 5 R OUT"). Labels on
 * rows 54, 59. dnfw.overviews.outs_render is the picture, pixel for pixel. */
#define OUT_TOP 15
#define OUT_PX  38
#define OUT_CH  25
static const u8 OUT_X[OUT_CH] = {1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57, 61, 67, 72, 77, 84, 89, 96,
                                 101, 108, 119};
static const char *const OUT_NAME[OUT_CH] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14",
                                             "15", "16", "D", "R", "C", "OB", "OB", "OUT", "OUT", "IN", "REC"};

static int out_group(int ch)             /* 0 TRK, 1 FX, 2 OB, 3 OUT, 4 IN, 5 REC */
{
    return ch < 16 ? 0 : ch < 19 ? 1 : ch < 21 ? 2 : ch < 23 ? 3 : ch - 19;
}

static void mix_view(void *c)
{
    extern u32 mix_ovw_get(int ch);
    static const char *const ROW54[12] = {"1", "8", "16", "D", "R", "C", "L", "R", "L", "R", "IN", "REC"};
    static const u8 ROW54_X[12] = {1, 29, 57, 67, 72, 77, 84, 89, 96, 101, 107, 116};
    static const char *const GRP[5] = {"TRK", "FX", "OB", "OUT", "USB"};
    static const u8 GRP_X[5] = {25, 70, 85, 95, 83};
    int usb = mix_ovw_get(-1) == 5u;
    box(c, 0, 0, 127, 63, 0);
    box(c, 0, 0, 127, 8, 1);
    text(c, 2, 2, "OUTPUTS", 0);
    u32 marks = 0;
    for (int ch = 0; ch < OUT_CH; ch++) {
        u32 v = mix_ovw_get(ch);
        int x = OUT_X[ch], w = ch < 16 ? 3 : 4, bot = OUT_TOP + OUT_PX - 1;
        int n = (int)(v & 0xFFu), h = (int)(v >> 8 & 0xFFu);
        if (v >> 17 & 1u) {
            box(c, x, bot, x + w - 1, bot, 1);
            if (n > 0)
                box(c, x, bot - n + 1, x + w - 1, bot, 1);
            if (h > n)
                box(c, x, bot - h + 1, x + w - 1, bot - h + 1, 1);
        } else {
            for (int r = OUT_TOP + 1; r <= bot; r += 3)
                px(c, x + w / 2, r, 1);
        }
        if (v >> 16 & 1u) {
            box(c, x, 10, x + w - 1, 13, 1);
            marks |= 1u << ch;
        }
    }
    for (int i = 0; i < 12; i++)
        text(c, ROW54_X[i], 54, ROW54[i], 1);
    u32 gm = 0;                          /* (a mask: no array initialiser, no memset in this chunk) */
    for (int ch = 0; ch < OUT_CH; ch++)
        if (marks >> ch & 1u)
            gm |= 1u << out_group(ch);
    for (int g = 0; g < 4; g++) {
        int k = g == 2 && usb ? 4 : g, on = (int)(gm >> g & 1u);
        if (on)
            box(c, GRP_X[k] - 1, 58, GRP_X[k] + width(GRP[k]), 63, 1);
        text(c, GRP_X[k], 59, GRP[k], !on);
    }
    if (!marks)
        return;
    char t[32];
    char *p = put(t, "CLIP");
    for (int ch = 0; ch < OUT_CH; ch++) {
        if (!(marks >> ch & 1u) || ((ch == 20 || ch == 22) && (marks >> (ch - 1) & 1u)))
            continue;                    /* (a pair's name once) */
        const char *m = (ch == 19 || ch == 20) && usb ? GRP[4] : OUT_NAME[ch];
        int len = 0;
        while (m[len])
            len++;
        if (p - t + 1 + len > 20) {
            p = put(p, " +");
            break;
        }
        *p++ = ' ';
        p = put(p, m);
    }
    text(c, 126 - width(t), 2, t, 0);
}

/* page.c wr_screen and ovw.c's frame alone: overview KIND over the whole canvas */
void ovw_paint(void *c, int kind)
{
    if (kind == OV_VOICE) {
        voice_view(c);                   /* (its own rows: no cells kept) */
        return;
    }
    if (kind == OV_MIX) {
        mix_view(c);                     /* (its bars from csrc/meter/mixer.c) */
        return;
    }
    struct cell cells[16][2];
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++) {
            cells[t][j].kind = C_DOT;
            cells[t][j].a = cells[t][j].m = 0;
            cells[t][j].s = "";
        }
    if (kind == OV_SYN)
        syn_view(c, cells);
    else if (kind == OV_FLT)
        flt_view(c, cells);
    else if (kind == OV_LFO)
        lfo_view(c, cells);
    else if (kind == OV_AMP)
        amp_view(c, cells);
    else
        ins_view(c, cells);
}
