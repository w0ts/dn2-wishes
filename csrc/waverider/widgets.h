/* Stock DN2 OS 1.12's own page widgets, called with our values (docs/widgets.md).
 *
 * Every stock widget is a per-record draw function whose value comes in as an argument
 * (measured in the 1.12 emulator, 2026-11-09: they draw into the canvas only, read nothing
 * else): (functor, value << 8, canvas, x, y, flag). We pass functor 0 and flag 0, as every
 * stock cell does. Call them only from inside a page draw, on the canvas it was given (stock's
 * canvas is a stack object).
 *
 * Geometry (stock's): the canvas is 128 x 64, y counting up from the bottom; eight cells,
 * column c at x = 24 + 26 c, the top row at y = 27, the bottom at 0; a cell's widget at
 * (x, y + 7), its label centred at (x + 9, y). The left panel: the track box at (0, 27), LEV's
 * fader at (-2, 7), its label at (7, 0).
 */
#ifndef WR_WIDGETS_H
#define WR_WIDGETS_H

typedef void (*wg_draw_fn)(const void *, int, void *, int, int, int);

#define WG_KNOB   ((wg_draw_fn)0x400C0986)      /* the dial: LEN, FREQ, RESO .. */
#define WG_FADER  ((wg_draw_fn)0x400C0A60)      /* VEL, LEV1 */
#define WG_LEVF   ((wg_draw_fn)0x400C0A14)      /* the left panel's LEV */
#define WG_TOGGLE ((wg_draw_fn)0x400BC578)      /* AMP.T, LFO.T: value 0 / 1 << 8 */
#define WG_NOTE   ((wg_draw_fn)0x400C0868)      /* NOTE: "C 5" over "(60)" in its box */
#define WG_RECT   ((void (*)(void *, int, int, int, int, int))0x40114906)
#define WG_TEXT   ((void (*)(void *, unsigned int, int, int, int, const char *, ...))0x4011573C)
#define WG_LABEL  ((void (*)(void *, unsigned int, int, int, int, int, const char *, const char *, ...))0x40115948)
#define WG_BLIT   ((void (*)(void *, const void *, int, int, int))0x40115ADC)
/* stock returns its pointers in d0, our compiler reads a0: declared int, cast */
#define WG_FRAME(sheet, i, sc) ((const void *)((int (*)(unsigned int, int, int))0x40115F88)((sheet), (i), (sc)))

#define WG_FONT_LABEL 0x40291CA0u               /* the cells' labels (via WG_LABEL) */
#define WG_FONT_TRACK 0x44508EB8u               /* the track box's "SYN" */
#define WG_SHEET_TRACK 0x44647DB4u              /* the track box, a frame per track */

static inline int wg_x(int s) { return 24 + 26 * (s & 3); }
static inline int wg_y(int s) { return s < 4 ? 27 : 0; }

/* a cell's label (4 characters), stock's font and place */
static inline void wg_label(void *c, int s, const char *name)
{
    WG_LABEL(c, WG_FONT_LABEL, wg_x(s) + 9, wg_y(s), 1, 0, "XXXX", "%s", name);
}

static inline void wg_knob(void *c, int s, int k)       /* k 0..127 */
{
    WG_KNOB(0, k << 8, c, wg_x(s), wg_y(s) + 7, 0);
}

static inline void wg_fader(void *c, int s, int k)
{
    WG_FADER(0, k << 8, c, wg_x(s), wg_y(s) + 7, 0);
}

static inline void wg_toggle(void *c, int s, int on)
{
    WG_TOGGLE(0, on ? 0x100 : 0, c, wg_x(s), wg_y(s) + 7, 0);
}

static inline void wg_note(void *c, int s, int note)    /* MIDI note 0..127 */
{
    WG_NOTE(0, (note < 0 ? 0 : note > 127 ? 127 : note) << 8, c, wg_x(s), wg_y(s) + 7, 0);
}

/* a named choice (stock has no generic one: its choice records each draw their text in a box,
 * as retrig LEN's 0x400cc418 does): the text centred in that box */
static const unsigned int wg_font_choice[2] = {0x402069DCu, 0x402941A4u};   /* retrig LEN's font object */

static inline void wg_choice(void *c, int s, const char *text)
{
    int x = wg_x(s), y = wg_y(s) + 7;
    WG_RECT(c, x, y, x + 18, y + 16, 1);
    WG_TEXT(c, (unsigned int)wg_font_choice, x + 9, y + 6, 2, "%.4s", text);
}

/* the left panel: the track box (stock's frame for the track, our 3-letter name where stock
 * writes SYN / MID) and LEV (value 0..0x7f00, the record's units) with its label */
static inline void wg_left_panel(void *c, int track, const char *name, int lev, const char *lev_label)
{
    WG_BLIT(c, WG_FRAME(WG_SHEET_TRACK, track, 0), 0, 27, 0);
    WG_TEXT(c, WG_FONT_TRACK, 7, 43, 2, "%.3s", name);
    WG_LEVF(0, lev, c, -2, 7, 0);
    WG_LABEL(c, WG_FONT_LABEL, 7, 0, 1, 0, "XXXX", "%s", lev_label);
}

#endif
