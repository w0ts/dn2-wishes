/* The RECORDER as the Digitakt II's own SAMPLING screens, call for call (docs/recorder-dt2.md).
 *
 * Each page below is the DT2 1.16 view's display list, traced in the emulator (SamplerView's
 * draw 0x40021de0, its AssignPrompt 0x40018be6 and NameView): the same stock drawing routines
 * at the same places with the same fonts and sprites, here at their DN2 1.12 addresses (the
 * widget library is one SDK on both: DT2 0x40112380.. = DN2 + 0x1c54, checked byte for byte;
 * the fonts and sprite bitmaps are in DN2 1.12's image unchanged). The values are ours
 * (rec.c): SRC, CHAN, THRES, INTO (in the DT2's MON place), R.LEN, R.STRT, ARM.
 *
 * Canvas 128 x 64, y counting up from the bottom. Colours: 1 lit, 0 dark, -1 inverted.
 */
#include "wr_gen.h"                           /* SMP_REC_SOURCES, smp_rec_src (dnfw.waverider.pages) */

typedef unsigned int u32;
typedef unsigned char u8;

/* the stock routines (DT2 1.16 address in brackets) */
#define D_TEXT   ((void (*)(void *, const void *, int, int, int, const char *, ...))0x4011573Cu)   /* [0x40113ae8] font object; align 0 left, 2 centre, 4 right, 8 inverted */
#define D_TITLE  ((void (*)(void *, u32, int, int, int, int, const char *))0x401153F8u)          /* [0x401137a4] font record, the big title */
#define D_TEXTS  ((void (*)(void *, u32, int, int, int, const char *))0x401156F8u)               /* [0x40113aa4] font record, plain */
#define D_VLINE  ((void (*)(void *, int, int, int, int))0x401141BCu)                             /* [0x40112568] x, y0, y1, colour */
#define D_RECT   ((void (*)(void *, int, int, int, int, int))0x40114906u)                        /* [0x40112cb2] outline */
#define D_RECT2  ((void (*)(void *, int, int, int, int, int))0x401147F0u)                        /* [0x40112b9c] AssignPrompt's outline */
#define D_DOTBOX ((void (*)(void *, int, int, int, int, int))0x40114AA2u)                        /* [0x40112e4e] dotted outline */
#define D_FILL   ((void (*)(void *, int, int, int, int, int))0x40114B22u)                        /* [0x40112ece] */
#define D_BADGE  ((void (*)(void *, int, int, int, int, int))0x40114C34u)                        /* [0x40112fe0] rounded fill */
#define D_BLIT   ((void (*)(void *, const void *, int, int, int))0x40115ADCu)                    /* [0x40113e88] */
#define D_PIXEL  ((void (*)(void *, int, int, int))0x40113E70u)

/* the fonts: records [DT2] -> DN2 1.12, and font objects {vtable, record} as the DT2 builds them */
#define FR_BIG  0x4028FFDCu                     /* [0x402a4f6c] RECORDER */
#define FR_LBL  0x40291CA0u                     /* [0x402a6c30] the labels */
#define FR_VAL  0x40294710u                     /* [0x402a96a0] the values */
#define FR_NAME 0x40290DD0u                     /* [0x402a5d60] FILE NAME's name */
#define FONT_VT 0x402069DCu                     /* [0x4021cb58] */
static const u32 F_LBL[2] = {FONT_VT, FR_LBL};
static const u32 F_VAL[2] = {FONT_VT, FR_VAL};
static const u32 F_NAME[2] = {FONT_VT, FR_NAME};

/* the sprites: stock frame objects {vtable, w, h, 1, columns, mask, 0}, a 32-bit word a column;
 * the DT2's RAM frames built from these same bitmaps, found in DN2 1.12's image */
#define FRAME_VT 0x402069C4u                    /* [0x4021cb40] */
static const u32 S_ARM_OFF[7] = {FRAME_VT, 17, 9, 1, 0x402A1C3Cu, 0x402A1BF8u, 0};
static const u32 S_ARM_ON[7]  = {FRAME_VT, 17, 9, 1, 0x402A1C80u, 0x402A1BF8u, 0};
static const u32 S_TRIM_L[7]  = {FRAME_VT, 4, 5, 1, 0x402F2610u, 0x402A1D8Cu, 0};
static const u32 S_TRIM_R[7]  = {FRAME_VT, 4, 5, 1, 0x402F0324u, 0x402A1D8Cu, 0};
static const u32 S_SPK[7]     = {FRAME_VT, 7, 5, 1, 0x402F02F8u, 0x402A692Cu, 0};
static const u32 S_PLAY[7]    = {FRAME_VT, 12, 9, 1, 0x402EB274u, 0x402A1BF8u, 0};
static const u32 S_PENCIL[7]  = {FRAME_VT, 9, 9, 1, 0x402A532Cu, 0x402A1BB0u, 0};
static const u32 S_DOTS[7]    = {FRAME_VT, 11, 2, 1, 0x402BD0F4u, 0x402BD0C8u, 0};

#define CTL_FRAME ((volatile unsigned short *)0x80005E60u)
#define TEMPO_WORD 108
#define DT2_MAX_FRAMES 3168000u                 /* 66 s at 48 kHz: the most the DT2 shows, and our DSP takes */

extern int rec_src, rec_chan, rec_thres, rec_dest, rec_rlen, rec_rstrt, rec_state, rec_peak, rec_link;
extern u32 rec_frames, rec_heard, rec_room, rec_wave_span;
extern u8 rec_wave[];
extern int rec_phase, trim_slot, nm_cur, nm_max, trim_zoom, smp_func_held;
extern u32 trim_n, trim_s, trim_e, trim_pos;
extern char nm_text[36];
extern int smp_slot_empty(int k);
extern const u8 *smp_overview(int k);           /* 100 columns over the slot (link.c) */
extern const u8 *smp_hires(void);               /* 1,024 columns over the analysed slot (link.c) */
extern int smp_analysis(int *pct);
extern int smp_analysis_slot(void);
extern int trim_head_x;                         /* smp_page.c: the playhead's column, for the checks */
extern int rec_pv_frame(void);
extern int smp_norm_state(void);
extern int smp_work_pct(void);

static int meter_px(int v)                      /* level 0..32767 -> 0..61 px, about 60 dB */
{
    int x = 0, t = 32767;
    while (t > 32 && v < t) {
        t >>= 1;
        x++;
    }
    int pos = 61 - x * 61 / 10;
    return pos < 0 ? 0 : pos;
}

/* the header: RECORDER, the input meter (a lit box, the level cut out of it in dark: CHAN L+R
 * both bars, L the top one, R the bottom one) and THRES's tick through it, inverted */
static int pk_hold __attribute__((section(".data"))) = 0;
static void header(void *c, int heard)
{
    D_TITLE(c, FR_BIG, 0, 54, 0, -1, "RECORDER");
    D_BADGE(c, 64, 54, 127, 63, 1);
    int lv = heard ? meter_px(rec_peak) : 0;
    pk_hold = lv >= pk_hold ? lv : pk_hold - 1;
    for (int bar = 0; bar < 2; bar++) {
        if ((rec_chan == 1 && bar == 1) || (rec_chan == 2 && bar == 0))
            continue;
        int y0 = bar ? 55 : 60, y1 = bar ? 57 : 62;
        if (lv > 4)
            D_FILL(c, 66, y0, lv + 63, y1, 0);
        if (pk_hold > 4)
            D_FILL(c, pk_hold + 64, y0, pk_hold + 64, y1, 0);
    }
    D_VLINE(c, 65 + (rec_thres > 127 ? 63 : rec_thres / 2), 54, 63, -1);
}

static void value2(void *c, int x, int y, const char *a, const char *b)   /* one value, or two lines */
{
    if (b) {
        D_TEXT(c, F_VAL, x, y + 3, 2, "%s", a);
        D_TEXT(c, F_VAL, x, y - 3, 2, "%s", b);
    } else
        D_TEXT(c, F_VAL, x, y, 2, "%s", a);
}

static u32 rlen_frames(void)                    /* R.LEN's frames: MAX the room, else its steps */
{
    if (rec_rlen <= 0) {
        u32 f = rec_room / 2u;
        return f > DT2_MAX_FRAMES ? DT2_MAX_FRAMES : f;
    }
    u32 bpm120 = CTL_FRAME[TEMPO_WORD];
    if (bpm120 < 1200)
        bpm120 = 14400;
    u32 f = (u32)rec_rlen * (86400000u / bpm120);
    return f > DT2_MAX_FRAMES ? DT2_MAX_FRAMES : f;
}

/* the RECORD NOW box (C): the DT2's, or why YES cannot record now */
static void rec_box(void *c, int heard)
{
    D_DOTBOX(c, 64, 31, 96, 47, 1);
    const char *a = 0, *b = 0;
    if (!heard || rec_link < 0) {               /* (v0.48: BOUNCE's QREC wait and REC trig takes are gone) */
        a = "NO DSP";
        b = !heard ? "STATUS" : "LINK";
    } else if (rec_room < 0x10000u) {
        a = smp_slot_empty(rec_dest < 0 ? 0 : rec_dest) ? "NO ROOM" : "NO SLOT";
        b = "FREE";
    }
    if (a) {                                    /* two lines inside the box, clear of its dots */
        D_TEXT(c, F_VAL, 80, 40, 2, "%s", a);
        D_TEXT(c, F_VAL, 80, 34, 2, "%s", b);
        return;
    }
    D_BADGE(c, 73, 25, 87, 37, 1);
    D_TEXT(c, F_VAL, 75, 29, 8, "%s", "YES");
    D_TEXT(c, F_VAL, 67, 40, 0, "%s", "REC");
    D_TEXT(c, F_VAL, 81, 40, 0, "%s", "NOW!");
    D_VLINE(c, 69, 29, 33, 1);
    D_VLINE(c, 70, 30, 32, 1);
    D_VLINE(c, 90, 30, 32, 1);
    D_VLINE(c, 91, 29, 33, 1);
}

/* THRES in dB (2026-11-13, the User: no bare 0..127): the level rec.c thr_word arms at, full scale x
 * 2^(-(120 - t) / 12): -0.502 dB a step, 0 dB at 120; under 12 its floor of 64 (-54 dB); 0 the -60 dB floor */
static int thres_db(int t)
{
    if (t <= 0)
        return -60;
    if (t < 12)
        return -54;
    return -(((120 - (t > 120 ? 120 : t)) * 502 + 500) / 1000);
}

/* the RECORDER (DT2 SamplerView, idle): eight places, values over labels */
static void main_page(void *c, int heard)
{
    static const char *const CHAN[3] = {"L+R", "L", "R"};
    header(c, heard);
    int s = rec_src < 0 ? 0 : rec_src > SMP_REC_SOURCES - 1 ? SMP_REC_SOURCES - 1 : rec_src;
    value2(c, 16, 39, smp_rec_src[s], 0);
    D_TEXT(c, F_LBL, 16, 27, 2, "%s", "SRC");
    value2(c, 48, 39, "MONO", CHAN[rec_chan < 0 ? 0 : rec_chan > 2 ? 2 : rec_chan]);
    D_TEXT(c, F_LBL, 48, 27, 2, "%s", "CHAN");
    rec_box(c, heard);
    D_TEXT(c, F_VAL, 112, 39, 2, "%ddB", thres_db(rec_thres));
    D_TEXT(c, F_LBL, 112, 27, 2, "%s", "THRES");
    if (rec_dest >= 0) {                        /* E: INTO, the slot the take goes into (the DT2's MON place) */
        D_TEXT(c, F_VAL, 15, 15, 2, "%s", "SAMP");
        D_TEXT(c, F_VAL, 15, 9, 2, "%d", rec_dest + 1);
    } else
        D_TEXT(c, F_VAL, 15, 12, 2, "%s", "N/A");
    D_TEXT(c, F_LBL, 16, 0, 2, "%s", "INTO");
    if (rec_rlen <= 0)
        D_TEXT(c, F_VAL, 48, 15, 2, "%s", "MAX");
    else
        D_TEXT(c, F_VAL, 48, 15, 2, "%d STP", rec_rlen);      /* 2026-11-11: "128 STEPS" was 2 px wider than its column */
    u32 f = rlen_frames();
    D_TEXT(c, F_VAL, 48, 9, 2, "%02d:%02d", (int)(f / 48000u), (int)(f % 48000u / 480u));
    D_TEXT(c, F_LBL, 48, 0, 2, "%s", "R.LEN");
    D_TEXT(c, F_VAL, 80, 12, 2, "%s", rec_rstrt ? "PLAY" : "THRES");
    D_TEXT(c, F_LBL, 81, 0, 2, "%s", "R.STRT");
    D_PIXEL(c, 97, 2, 1);
    D_PIXEL(c, 99, 2, 1);
    D_BLIT(c, rec_state == 1 || rec_state == 2 ? S_ARM_ON : S_ARM_OFF, 112, 14, 1);
    D_TEXT(c, F_LBL, 112, 0, 2, "%s", "ARM");
}

/* one mono lane, the DT2's (0x4001fe12): a column per x in 1..W (<= 126) about y 30, +-19,
 * inverted, normalised to the loudest column; PK 0..255 a column */
static void lane(void *c, const u8 *pk, int w)
{
    int top = 1;
    for (int x = 0; x < w; x++)
        if (pk[x] > top)
            top = pk[x];
    for (int x = 0; x < w; x++) {
        int a = pk[x] * 19 / top;
        D_VLINE(c, x + 1, 30 - a, 30 + a, -1);
    }
}

/* RECORDING (SamplerView's state 2): the header, the frame, the take as it comes in, the line */
static void recording_page(void *c, int heard)
{
    header(c, heard);
    D_TEXT(c, F_VAL, 0, 0, 0, "%s", "RECORDING");   /* (the DT2 blinks it; kept lit) */
    D_TEXT(c, F_VAL, 64, 0, 2, "%02d:%02d", (int)(rec_frames / 48000u), (int)(rec_frames % 48000u / 480u));
    D_TEXT(c, F_VAL, 127, 0, 4, "%s", "YES: STOP");
    D_RECT(c, 0, 8, 127, 50, 1);
    D_VLINE(c, 127, 9, 49, 1);
    u32 cols = rec_frames / (rec_wave_span ? rec_wave_span : 1u) + 1u;   /* rec.c's 120 columns so far */
    int n = cols > 120u ? 120 : (int)cols, w = n * 126 / 120;
    u8 pk[126];
    for (int x = 0; x < w; x++)
        pk[x] = rec_wave[x * 120 / 126];
    lane(c, pk, w);
}

/* TRIM's columns: the 126 peaks of [A, A + SPAN) out of the slot's 100-column overview, or
 * zoomed out of the analysis' 1,024 columns; -> 0 nothing to show */
static int trim_peaks(u8 *pk, u32 a, u32 span, u32 n)
{
    const u8 *src = smp_overview(trim_slot);
    u32 cols = 100u;
    if (trim_zoom > 0 && smp_analysis(0) == 2 && smp_analysis_slot() == trim_slot) {
        src = smp_hires();
        cols = 1024u;
    }
    if (!src)
        return 0;
    for (int x = 0; x < 126; x++) {
        u32 f0 = a + (u32)x * (span / 126u), f1 = f0 + span / 126u;
        u32 c0 = f0 * cols / n, c1 = f1 * cols / n;
        int p = 0;
        for (u32 k = c0; k <= c1 && k < cols; k++)
            if (src[k] > p)
                p = src[k];
        pk[x] = (u8)p;
    }
    return 1;
}

static int trim_x(u32 f, u32 a, u32 span)       /* a frame's column 1..126, or -1 out of view */
{
    if (f < a || f > a + span)
        return -1;
    return 1 + (int)((f - a) * 125u / (span ? span : 1u));
}

/* TRIM (SamplerView after a take): the keys bar, the preview mode, the waveform with the cut
 * away ends inverted, the controls along the bottom */
static void trim_page(void *c)
{
    D_BLIT(c, S_TRIM_L, 5, 0, 0);
    D_BLIT(c, S_TRIM_R, 119, 0, 0);
    D_TEXTS(c, FR_LBL, 12, 0, -1, "TRIM");
    D_TEXTS(c, FR_LBL, 38, 0, -1, trim_zoom == 1 ? "2X" : trim_zoom == 2 ? "4X" : trim_zoom == 3 ? "8X" : "ZOOM");
    D_TEXTS(c, FR_LBL, 73, 0, -1, "POS");
    D_TEXTS(c, FR_LBL, 100, 0, -1, "TRIM");
    D_FILL(c, 0, 55, 95, 63, 0);
    D_TEXT(c, F_VAL, 3, 57, 0, "%s", "Y:SAVE");
    D_TEXT(c, F_VAL, 32, 57, 0, "%s", "Fn+N:DEL");
    D_TEXT(c, F_VAL, 67, 57, 0, "%s", "Fn+Y:");
    D_BLIT(c, S_SPK, 86, 57, 0);
    D_BADGE(c, 0, 55, 95, 63, -1);
    D_BLIT(c, S_PLAY, 106, 55, 0);
    D_RECT(c, 0, 9, 127, 51, 1);
    D_VLINE(c, 127, 10, 50, 1);
    u32 n = trim_n ? trim_n : 1u, span = trim_zoom > 0 ? n >> trim_zoom : n, a = trim_zoom > 0 ? trim_pos : 0u;
    if (!span)
        span = 1u;
    u8 pk[126];
    if (trim_peaks(pk, a, span, n))
        lane(c, pk, 126);
    int sx = trim_s <= a ? 1 : trim_x(trim_s, a, span), ex = trim_e >= a + span ? 126 : trim_x(trim_e, a, span);
    if (sx < 0)                                 /* START past the window: all of it cut away */
        sx = 127;
    if (ex < 0)
        ex = 0;
    if (sx > 1)                                 /* outside START..END: inverted */
        D_FILL(c, 1, 10, sx - 1 < 126 ? sx - 1 : 126, 50, -1);
    if (ex < 126)
        D_FILL(c, ex + 1 > 1 ? ex + 1 : 1, 10, 126, 50, -1);
    int f = rec_pv_frame();                     /* the preview's place: a column, inverted */
    int fx = f >= 0 ? trim_x((u32)f, a, span) : -1;
    trim_head_x = fx;
    if (fx > 0)
        D_VLINE(c, fx, 9, 51, -1);
}

/* ASSIGN (the DT2's AssignPrompt over TRIM) */
static void assign_page(void *c)
{
    trim_page(c);
    D_FILL(c, 6, 15, 120, 45, 0);
    D_RECT2(c, 7, 16, 119, 44, 1);
    D_TEXT(c, F_LBL, 13, 33, 0, "%s", "ASSIGN SAMPLE TO TRACK?");
    D_TEXT(c, F_VAL, 23, 23, 0, "%s", "TRG 1-16");
    D_TEXT(c, F_VAL, 77, 23, 0, "%s", "NO:SKIP");
    D_BLIT(c, S_DOTS, 55, 26, 0);
    D_BLIT(c, S_DOTS, 55, 23, 0);
}

/* FILE NAME (the DT2's NameView): the title, the name with the cursor's letter inverted, the keys */
#define NM_VIEW_DT2 20
static int nm_first __attribute__((section(".data"))) = 0;
static void name_page(void *c)
{
    char t[2];
    D_TEXT(c, F_LBL, 50, 58, 8, "%s", "FILE NAME");
    D_BLIT(c, S_PENCIL, 38, 56, 0);
    if (nm_cur < nm_first)
        nm_first = nm_cur;
    if (nm_cur >= nm_first + NM_VIEW_DT2)
        nm_first = nm_cur - NM_VIEW_DT2 + 1;
    for (int v = 0; v < NM_VIEW_DT2 && nm_first + v < nm_max; v++) {
        int j = nm_first + v;
        t[0] = nm_text[j] ? nm_text[j] : ' ';
        t[1] = 0;
        D_TEXT(c, F_NAME, 4 + 6 * v, 38, j == nm_cur ? 8 : 0, "%s", t);
    }
    D_RECT(c, 0, 34, 127, 47, -1);
    D_TEXT(c, F_VAL, 0, 18, 0, "%s", "FUNC+ARROW:EDIT");
    D_TEXT(c, F_VAL, 0, 12, 0, "%s", "FUNC+NO:DELETE");
    D_TEXT(c, F_VAL, 0, 6, 0, "%s", "FUNC+YES:INSERT");
    D_TEXT(c, F_VAL, 0, 0, 0, "%s", "YES:SAVE");
    D_TEXT(c, F_VAL, 64, 12, 0, "%s", "U/D:CHAR +/-");
    D_TEXT(c, F_VAL, 64, 6, 0, "%s", "L/R:MOVE CURSOR");
    D_TEXT(c, F_VAL, 64, 0, 0, "%s", "NO:ABORT");
    if (nm_first + NM_VIEW_DT2 < nm_max)
        D_TEXT(c, F_NAME, 120, 28, 0, "%s", ">>");
}

/* SAVING / NORMALIZING (the DT2's line, our progress under it) */
static void work_page(void *c)
{
    D_TEXT(c, F_VAL, 64, 28, 2, "%s", smp_norm_state() ? "NORMALIZING..." : "SAVING...");
    int pct = smp_work_pct();
    D_RECT(c, 24, 18, 103, 22, 1);
    if (pct > 0)
        D_FILL(c, 25, 19, 25 + (pct > 100 ? 100 : pct) * 77 / 100, 21, 1);
}

/* -> 1 drawn (the DT2's page for this phase/state); 0: the caller's (the BOUNCE panel, the name grid) */
int rec_dt2_draw(void *c, int heard, int bounce)
{
    if (rec_phase == 1) {
        trim_page(c);
        return 1;
    }
    if (rec_phase == 2) {
        if (smp_func_held)
            return 0;
        name_page(c);
        return 1;
    }
    if (rec_phase == 3) {
        assign_page(c);
        return 1;
    }
    if (rec_phase) {
        work_page(c);
        return 1;
    }
    if (bounce)
        return 0;
    if (heard && rec_state == 2) {
        recording_page(c, heard);
        return 1;
    }
    main_page(c, heard);
    return 1;
}
