/* Controls that move, Optimist style (owner, 2026-11-11: "Moving controls"; display.md option A,
 * docs/modulation-more.md). OS 1.12.
 *
 * Every stock parameter cell is drawn as stock draws it, its number the value you set. Under it,
 * in the cell's free bottom row, a 1 px line shows the value HEARD now: filled from the cell's
 * left edge to the value, or from its centre for a parameter whose default is the middle of its
 * range (the centre pixel then always set). The line shows only while the heard value differs
 * from the set one, and stays 400 ms after they meet again, so an LFO crossing the set value does
 * not make it blink. Nothing is drawn on a parameter nothing modulates.
 *
 * Heard and set, per voice (the mirrors are per VOICE: 16 rows of 101 slots, word 17 + 101 v + s;
 * the six-source apply 0x400db390 takes each row's track from OWNER 0x80005308, and the LFO
 * evaluator 0x40137a06 walks the same rows):
 *   heard = OUT 0x800068e4 (the smoother's output, then the six sources and LFO1-3 added),
 *   set   = the smoother's own state STATE 0x8000de60 (16.16; OUT = its rounding before the
 *           sources are added, 0x400db2be), so a knob's glide or a parameter slide (which moves
 *           STATE and OUT together, csrc/slides) is no modulation and draws nothing.
 * The voice is the one the track last played (slides' sl_lastv, set at every note), and only
 * while it still plays that track (OWNER). Before a track's first note, nothing.
 *
 * A cell is one of the track's sound slots when stock's slot -> record map (0x400dc18e, with our
 * machines' hook in it) gives the cell's record back for the record's slot (+0x04): the global
 * FX pages, the MIDI tracks and anything else outside the 101 slots get no line.
 *
 * Our own pages (PERC's, the Monomachine's, the sample machines': md_page.c, smp_page.c) draw their
 * own knobs, not stock cells: each knob calls mv_knob with the row and width its line goes in and the
 * value range its knob spans (the Monomachine's knobs a part of the record's), and gets the same line
 * by the same rules (2026-11-12).
 *
 * Redraws (mv_poll, from page.c wr_poll): the cells of the last draw are kept; the screen is
 * asked for a redraw (stock setDirty) only when a line would now be drawn elsewhere than it is
 * (a pixel's move, appearing, leaving), at most 25 times a second.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define SET_DIRTY ((void (*)(void *))0x4011D5DEu)
#define SLOT_ID   ((u32 (*)(u32, int, int))0x400DC18Eu)        /* (slot, machine, filter) -> record */
#define FRAMES    (*(volatile u32 *)0x4058F8D4u)               /* 1,500 a second */
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))   /* +4 slot, +8 min, +12 max, +16 default */
#define KIT_POINTER (*(unsigned char *volatile *)0x800052A0u)
#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)
#define OWNER     ((volatile u32 *)0x80005308u)
#define STATE     ((volatile u32 *)0x8000DE60u)
#define OUT       ((volatile u16 *)0x800068E4u)
#define IDX(v, s) (17u + 101u * (u32)(v) + (u32)(s))
#define MIDI_TYPE 4

#define LINGER   600u           /* frames: 400 ms */
#define REDRAW   60u            /* frames: 25 a second at most */
#define POLL     15u            /* frames: the cells looked at 100 times a second at most */
#define NCELL    16
#ifndef MV_DY
#define MV_DY    5              /* the line's row from the cell's y: free in every stock cell (225 cells, SYN FLTR AMP FX MOD of the 4 stock machines, emulator 2026-11-11) */
#endif
#define MV_DX    1              /* the line's first column, from the cell's x */
#define MV_W     21             /* its width in pixels */

extern s8 sl_lastv[16];         /* csrc/slides: the voice a track last played on */

struct mv_cell {
    u16 id;
    u8 slot, gen, w, pad;       /* w: the line's width in pixels */
    short x, y;                 /* the line's first pixel */
    int lo, hi;                 /* the values at its two ends */
    short drawn;                /* the line's end column as drawn, -1: no line */
    u32 last;                   /* the last frame heard != set */
};
struct mv_state {
    u32 magic;
    u32 draws, lines, polls, asks;      /* the checks' counters */
    u32 next;                           /* the earliest frame for the next redraw asked */
    u8 gen, n, pad0, pad1;
    struct mv_cell c[NCELL];
};
#define MV ((struct mv_state *)MOD_MOVING_RAM)
#define MV_MAGIC 0x4D563031u            /* 'MV01' */
_Static_assert(sizeof(struct mv_state) <= MOD_MOVING_BYTES, "the moving controls' state fits MOD_RAM");

static void mv_ready(void)
{
    if (MV->magic == MV_MAGIC)
        return;
    u32 *w = (u32 *)MV;
    for (u32 k = 0; k < sizeof(struct mv_state) / 4; k++)
        w[k] = 0;
    MV->magic = MV_MAGIC;
}

/* the UI track's sound -> its machine (-1: none or MIDI) and filter */
static int track_sound(int *filter)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (t > 15 || !kit)
        return -1;
    unsigned char *snd = kit + 52u + 1163u * t;
    int m = (s8)snd[0xDE];
    *filter = (s8)snd[0xDF];
    return m < 0 || m == MIDI_TYPE ? -1 : m;
}

/* the voice row heard for the UI track, -1 none */
static int heard_voice(void)
{
    u8 t = UI_TRACK;
    if (t > 15)
        return -1;
    int v = sl_lastv[t];
    if (v < 0 || v > 15 || OWNER[v] != t)
        return -1;
    return v;
}

/* -> the line's end column (0..MV_W-1) for the cell now, -1 no line; updates its linger */
static int line_at(struct mv_cell *c, int v, u32 now)
{
    if (v < 0)
        return -1;
    u32 i = IDX(v, c->slot);
    int heard = OUT[i];
    int set = (int)((STATE[i] + 0x8000u) >> 16);
    if (heard != set)
        c->last = now;
    else if (!c->last || now - c->last >= LINGER)
        return -1;
    int lo = c->lo, hi = c->hi;
    if (hi <= lo)
        return -1;
    if (heard < lo) heard = lo;
    if (heard > hi) heard = hi;
    return (heard - lo) * (c->w - 1) / (hi - lo);
}

/* the screen is about to draw: the cells it draws now are this generation's */
void mv_begin(void)
{
    mv_ready();
    MV->gen++;
    MV->n = 0;
    MV->draws++;
}

/* a knob of record ID drawn on the canvas: keep it, and draw its line from (x, y), W pixels wide,
 * LO at its left end and HI at its right (record units, 0..0x7f00); from its centre when the
 * record's default is the middle of LO..HI */
void mv_knob(void *canvas, int x, int y, int w, u32 id, int lo, int hi)
{
    mv_ready();
    int filter, m = track_sound(&filter);
    if (m < 0 || id == 0 || id > 320u)
        return;
    u32 slot = (u32)RECORD(id)[1];
    if (slot < 1u || slot > 100u || SLOT_ID(slot, m, filter) != id)
        return;
    struct mv_cell *c = 0;
    for (int k = 0; k < NCELL; k++)                     /* the same parameter keeps its linger */
        if (MV->c[k].id == id) {
            c = &MV->c[k];
            break;
        }
    if (!c) {
        for (int k = 0; k < NCELL && !c; k++)            /* else a place not drawn this time */
            if (MV->c[k].gen != MV->gen)
                c = &MV->c[k];
        if (!c)
            return;
        c->id = (u16)id;
        c->last = 0;
    }
    c->slot = (u8)slot;
    c->gen = MV->gen;
    c->w = (u8)(w < 2 ? 2 : w > 255 ? 255 : w);
    c->x = (short)x;
    c->y = (short)y;
    c->lo = lo;
    c->hi = hi;
    MV->n++;
    int at = line_at(c, heard_voice(), FRAMES);
    c->drawn = (short)at;
    if (at < 0)
        return;
    MV->lines++;
    int from = 2 * RECORD(id)[4] == lo + hi ? (c->w - 1) / 2 : 0;
    int a = from < at ? from : at, b = from < at ? at : from;
    for (int k = a; k <= b; k++)
        SET_PIXEL(canvas, x + k, y, 1);
}

/* a cell laid out as stock's (x0, y0 its corner): the line in its free bottom row, LO..HI across it
 * (md_page.c's PERC and Monomachine cells are stock's widgets at stock's places) */
void mv_cell_span(void *canvas, int x0, int y0, u32 id, int lo, int hi)
{
    mv_knob(canvas, x0 + MV_DX, y0 + MV_DY, MV_W, id, lo, hi);
}

/* after each stock cell (page.c wr_cell): across the record's range */
void mv_cell(void *canvas, int x0, int y0, u32 id)
{
    if (id == 0 || id > 320u)
        return;
    const int *r = RECORD(id);
    mv_cell_span(canvas, x0, y0, id, r[2], r[3]);
}

/* the UI loop's redraw test (page.c wr_poll): a redraw when a shown line would move */
void mv_poll(void *screen)
{
    mv_ready();
    u32 now = FRAMES;
    if ((int)(now - MV->next) < 0)
        return;
    MV->polls++;
    MV->next = now + POLL;
    int v = heard_voice();
    for (int k = 0; k < NCELL; k++) {
        struct mv_cell *c = &MV->c[k];
        if (c->gen != MV->gen || !c->id)
            continue;
        if (line_at(c, v, now) != c->drawn) {
            MV->next = now + REDRAW;
            MV->asks++;
            SET_DIRTY(screen);
            return;
        }
    }
}
