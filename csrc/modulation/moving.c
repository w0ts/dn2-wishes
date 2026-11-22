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
 *   set   = the UI track's sound's own stored value (sound + 20 + 2 slot, a word a slot, as
 *           csrc/matrix/routes.c reads it; 2026-11-20, the User: "modulation and plock should be
 *           displayed with our line ... but not MOVE the knob"), so a p-lock playing and a parameter
 *           slide of ours (both move STATE and OUT together: the lock applier writes the smoother's
 *           input, csrc/slides moves STATE) show as the line too; but for 300 ms after that stored
 *           value changed (a knob turned, a load, CC) set is the smoother's own state STATE
 *           0x8000de60 (16.16; OUT = its rounding before the sources are added, 0x400db2be), as it
 *           was before: stock's smoother glides a turned knob, and that glide draws nothing.
 *           LFO4's page (DN2_LFO4, slots 101..108): set = lfo4's table for the sound, heard = set
 *           plus what LFO1..3 add to that control on the voice (csrc/modulation/cascade.c).
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
 * Redraws (mv_poll, from page.c wr_poll): the cells of the last draw are kept; a line is updated
 * only when it would now be drawn elsewhere than it is (a pixel's move, appearing, leaving), at
 * most 25 times a second.
 *
 * Only the lines (2026-11-17, the User: "why do we redraw the whole screen? we could redraw only the
 * knob/line?"; docs/display-path.md, "Line-only updates"). Stock's loop draws FRONT whole and
 * panel_diff (0x40131fd2) sends the 8-px groups where it differs from BACK, then swaps them: between
 * presents BACK is exactly the frame on the glass. So when only lines move, mv_poll rewrites each
 * moved line's row in BACK and sends the groups it changed through stock's own sender (0x40131f04,
 * then the 0xB8 show 0x40131eec), with no page draw and no swap; the next full draw diffs against a
 * BACK that already holds them. A cell takes this path only while it is CLEAN, decided at the end of
 * each full draw (mv_end): its line's row holds exactly the page's own pixels there (kept as the line
 * was drawn: a graph across cells) with the line ORed over them (or exactly their inverse: a p-locked
 * cell lit by stock) at the end of the frame, and its guard rows still hash as they did when the line
 * was drawn (or as their inverse): nothing drew over the cell afterwards. The guard rows are its label's under
 * the line (MV_LABEL_ROWS), or, for a cell with no label there (ONESHOT 2/2's top row, where the waveform's
 * end marker is drawn later), its widget's above the line; a cell blank both ways is never clean (a popup, the meter's corner, the RECORDER, the inserts overview, the NAME
 * screen). Any other move asks for the full redraw as before (stock setDirty), as does a move while
 * a redraw is already due or while BACK is not the buffer that frame was drawn into.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define SET_DIRTY ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY  ((u8 (*)(void *))0x4011D5D4u)                 /* sets only %d0's low byte (move.b): a u8 */
#define FB_BACK   (*(u8 *volatile *)0x402A10CCu)              /* the frame on the glass, between presents */
#define GLASS_GROUP ((void (*)(u32, u32, const u8 *))0x40131F04u)   /* (column 0..120, page 0..7, 8 bytes) */
#define GLASS_SHOW  ((void (*)(void))0x40131EECu)              /* the 0xB8 after the groups */
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))              /* ctor 0x40113e2a: +16 the buffer */
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
#define REDRAW   60u            /* frames: 25 a second at most, a full redraw asked */
#define REDRAW_ALONE 25u        /* frames: 60 a second at most, the lines alone (2026-11-18, the User: "the bar/line that
                                 * display is slow": 25 a second at most, and a UI pass about every 33 ms, gave 12-14) */
#define POLL     15u            /* frames: the cells looked at 100 times a second at most */
#define NCELL    16
#ifndef MV_DY
#define MV_DY    5              /* the line's row from the cell's y: free in every stock cell (225 cells, SYN FLTR AMP FX MOD of the 4 stock machines, emulator 2026-11-11) */
#endif
#define MV_DX    1              /* the line's first column, from the cell's x */
#define MV_W     21             /* its width in pixels */
#define MV_LABEL_ROWS 5         /* the guard rows: under the line (the cell's label), else above it (its widget) */
#define E2_LINE  0xE0u          /* a cell's slot from here: ENV2's knob (slot - E2_LINE: ATK..REL, 2026-11-20 MODE RSET H),
                                 * not a voice-row slot */
#define INS_LINE 0xC0u          /* (2026-11-20) INS_LINE .. + 13: an insert's knob of the UI track (csrc/inserts ins_knob_now:
                                 * the DSP's value against the page's), not a voice-row slot */
#define INS_LINES 14u

#define GLIDE    450u           /* frames: 300 ms after the sound's stored value changed (a knob turned, a load, CC),
                                 * "set" is still the smoother's STATE, which glides to it (2026-11-20) */
#define SND_SLOT(snd, s) (*(const u16 *)((snd) + 20u + 2u * (u32)(s)))   /* the sound's cells: +20, a word a slot
                                                                          * (csrc/matrix/routes.c mxr_stock) */
#if DN2_LFO4
#define MV_ID_TOP   330u        /* lfo4's records 321..330 (LFO4's page: slots 101..108; docs/lfo-112-port.md) */
#define MV_SLOT_TOP 108u
#define MV_L4_SLOT0 101u
#define MV_L4_DEST  104u        /* LFO4's DEST: not a value */
#define EXT_FIND ((const u16 *(*)(u32))LFO4_EXT_FIND)   /* lfo4's table: a sound -> its eight values, 0 none */
#define EXT_DEFAULT ((const u16 *)LFO4_EXT_DEFAULT)
#else
#define MV_ID_TOP   320u
#define MV_SLOT_TOP 100u
#define MV_L4_DEST  0u
#endif

extern s8 sl_lastv[16];         /* csrc/slides: the voice a track last played on */

struct mv_cell {
    u16 id;
    u8 slot, gen, w, from;      /* w: the line's width in pixels; from: its fixed end (0, or the centre) */
    short x, y;                 /* the line's first pixel */
    int lo, hi;                 /* the values at its two ends */
    short drawn;                /* the line's end column as drawn, -1: no line */
    u8 clean, inv;              /* clean: its line may be updated alone; inv: the cell is drawn inverted */
    u32 last;                   /* the last frame heard != set */
    u32 hash;                   /* the rows under the line (its label), as the line was drawn */
    u32 under;                  /* the page's own pixels in the line's row (bit k: column k), as the line was drawn */
    u8 above, pad2;             /* the guard rows: 0 the label's under the line, 1 the widget's above it */
};
struct mv_state {
    u32 magic;
    u32 draws, lines, polls, asks;      /* the checks' counters (asks: a line moved, either way) */
    u32 next;                           /* the earliest frame for the next update */
    u8 gen, n, pad0, pad1;
    struct mv_cell c[NCELL];
    u32 parts, fulls, groups, dirty;    /* line-only updates, full redraws asked, groups sent, cells not clean */
    u8 *back;                           /* the buffer the last full draw was drawn into */
    u32 own_at[NCELL];                  /* (2026-11-20) per cell: the frame its sound's stored value last changed, 0 none */
    u16 own[NCELL];                     /* ... and that value as last seen */
};
#define MV ((struct mv_state *)MOD_MOVING_RAM)
#define MV_MAGIC 0x4D563032u            /* 'MV02' */
_Static_assert(sizeof(struct mv_state) <= MOD_MOVING_BYTES, "the moving controls' state fits MOD_RAM");
/* the offsets the emulator checks read (scripts/emu_line_redraw.py; an int aligns to 2 bytes on the ColdFire) */
_Static_assert(sizeof(struct mv_cell) == 36 && __builtin_offsetof(struct mv_cell, drawn) == 18
               && __builtin_offsetof(struct mv_cell, clean) == 20, "mv_cell as the checks read it");
_Static_assert(__builtin_offsetof(struct mv_state, asks) == 16 && __builtin_offsetof(struct mv_state, c) == 28
               && __builtin_offsetof(struct mv_state, parts) == 604 && __builtin_offsetof(struct mv_state, back) == 620,
               "mv_state as the checks read it");

/* MOD_RAM outlives a restart that keeps the RAM (a flash's, a quick power cycle), but the frame clock (FRAMES, stock's
 * BSS) starts again at 0 and the screen's buffers are drawn anew. So the block is trusted only once this load has
 * cleared it: mv_loaded is code data, which every load sets back to 0 (as wishes' wish_ready). (2026-11-18, the User:
 * "the bar/line that display is slow ... sometimes it works sometimes not": on the DN2 after a restart, MV->next was
 * 14,689,142 against a clock of 2,301,111, so mv_poll waited 2 h 17 min and the lines moved only with stock's own
 * redraw, once a second; scratch/env2-mod.md) */
u32 mv_loaded __attribute__((section(".data"))) = 0;

static void mv_ready(void)
{
    if (MV->magic == MV_MAGIC && mv_loaded)
        return;
    mv_loaded = 1;
    u32 *w = (u32 *)MV;
    for (u32 k = 0; k < sizeof(struct mv_state) / 4; k++)
        w[k] = 0;
    MV->magic = MV_MAGIC;
}

/* the panel's buffers: 128 columns of 8 bytes, pixel (x, y) bit 7 - y % 8 of byte 8x + y / 8 (stock's
 * setPixel 0x40113e70, y up from the bottom), the 8-px group of column x and page p its 8 bytes
 * 64 (x / 8) + 8k + p */
static int px_get(const u8 *b, int x, int y)
{
    return (b[8 * x + (y >> 3)] >> (7 - (y & 7))) & 1;
}

/* the pixels of rows y0..y1 (inside 0..63) of columns x..x+w-1 -> a hash */
static u32 area_hash(const u8 *b, int x, int w, int y0, int y1, int flip)
{
    u32 h = 2166136261u;
    for (int k = 0; k < w; k++) {
        const u8 *col = b + 8 * (x + k);
        for (int y = y0; y <= y1; y++) {
            int v = ((col[y >> 3] >> (7 - (y & 7))) & 1) ^ flip;
            h = (h ^ (u32)v) * 16777619u;
        }
    }
    return h;
}

/* the guard rows of a cell: ABOVE 0 the MV_LABEL_ROWS under its line (its label), 1 those above it (its widget),
 * clipped to the screen -> *R0..*R1; -> nonzero when they hold a pixel (an overdraw there would show) */
static int guard_rows(const u8 *buf, const struct mv_cell *c, int above, int *r0, int *r1)
{
    if (above) {
        *r0 = c->y + 1;
        *r1 = c->y + MV_LABEL_ROWS > 63 ? 63 : c->y + MV_LABEL_ROWS;
    } else {
        *r0 = c->y > MV_LABEL_ROWS ? c->y - MV_LABEL_ROWS : 0;
        *r1 = c->y - 1;
    }
    for (int k = 0; k < c->w; k++)
        for (int y = *r0; y <= *r1; y++)
            if (px_get(buf, c->x + k, y))
                return 1;
    return 0;
}

/* the line's pixel at column k of the cell, AT its end column (-1: no line) */
static int line_px(const struct mv_cell *c, int k, int at)
{
    if (at < 0)
        return 0;
    int a = c->from < at ? c->from : at, b = c->from < at ? at : c->from;
    return k >= a && k <= b;
}

/* the row's pixel at column k as a full draw leaves it: the page's own pixel there, or the line's */
static int row_px(const struct mv_cell *c, int k, int at)
{
    return (int)((c->under >> k) & 1u) | line_px(c, k, at);
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

/* the UI track's sound's stored value of SLOT (1..100: its cell; LFO4's 101..108: lfo4's table), -1 none */
static int own_value(u32 slot)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    if (t > 15 || !kit || slot < 1u || slot > MV_SLOT_TOP)     /* ENV2's cells (E2_LINE..): not the sound's */
        return -1;
    const unsigned char *snd = kit + 52u + 1163u * t;
#if DN2_LFO4
    if (slot >= MV_L4_SLOT0) {
        const u16 *v = EXT_FIND((u32)snd);
        return (v ? v : EXT_DEFAULT)[slot - MV_L4_SLOT0];
    }
#endif
    return slot <= 100u ? SND_SLOT(snd, slot) : -1;
}

/* a cell given to a parameter: its stored value as seen now, unchanged */
static void own_reset(struct mv_cell *c, u32 slot)
{
    int k = (int)(c - MV->c), o = own_value(slot);
    MV->own[k] = (u16)(o < 0 ? 0 : o);
    MV->own_at[k] = 0;
}

/* (2026-11-20, the User: "modulation and plock should be displayed with our line ... but not MOVE the knob") "set" is
 * the sound's stored value OWN, so a p-lock playing (the lock applier writes the locked value into the smoother's
 * input, SRC 0x80003af0, and STATE glides to it) and a slide of ours show as the line, as any modulation. Except for
 * GLIDE after OWN changed (a knob turned, a load, CC, Overbridge): stock's smoother glides STATE to the new value, and
 * that glide is no modulation, so "set" is then STATE (GLIDING) as before: no line flashes on every turn */
static int own_set(struct mv_cell *c, int gliding, int own, u32 now)
{
    int k = (int)(c - MV->c);
    if (own < 0)
        return gliding;
    if ((u16)own != MV->own[k]) {
        MV->own[k] = (u16)own;
        MV->own_at[k] = now ? now : 1u;                 /* 0 is "none"; never ahead of NOW (now | 1 was, on an
                                                         * even frame: now - own_at wrapped and the glide drew a line) */
    }
    return MV->own_at[k] && now - MV->own_at[k] < GLIDE ? gliding : own;
}

/* -> the line's end column (0..MV_W-1) for the cell now, -1 no line; updates its linger */
static int line_at(struct mv_cell *c, int v, u32 now)
{
    int heard, set;
    if (c->slot >= INS_LINE && c->slot < INS_LINE + INS_LINES) {   /* (2026-11-20) the track's insert: no voice needed */
        extern void ins_knob_now(u32 t, u32 i, int *heard, int *set);
        ins_knob_now(UI_TRACK & 15u, c->slot - INS_LINE, &heard, &set);
    } else if (v < 0) {
        return -1;
    } else if (c->slot >= E2_LINE) {                           /* ENV2's knob (its page): the matrix's knob row, not the voice
                                                         * row (csrc/matrix/matrix.c mx_e2_knob) */
        extern int mx_e2_knob(u32 v, u32 k, int *heard, int *set);
        if (!mx_e2_knob((u32)v, (u32)(c->slot - E2_LINE), &heard, &set))
            return -1;
#if DN2_LFO4
    } else if (c->slot >= MV_L4_SLOT0) {                /* LFO4's page: its stored value, plus what LFO1..3 add to that
                                                         * control on this voice (csrc/modulation/cascade.c); no smoother */
        extern int mod_l4_carry(u32 v, u32 b);
        set = own_value(c->slot);
        if (set < 0)
            return -1;
        heard = set + mod_l4_carry((u32)v, c->slot - MV_L4_SLOT0);
        heard = heard < 0 ? 0 : heard > 0x7F00 ? 0x7F00 : heard;
#endif
    } else {
        u32 i = IDX(v, c->slot);
        heard = OUT[i];
        set = own_set(c, (int)((STATE[i] + 0x8000u) >> 16), own_value(c->slot), now);
    }
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

static void mv_place(void *canvas, int x, int y, int w, u32 id, u32 slot, int lo, int hi, int centre);

/* (2026-11-20) a knob of our own page that is no record (csrc/inserts: the INSERT pages' knobs): KEY (0x8000 | its index)
 * keeps its linger, SLOT (INS_LINE + its index) is what line_at reads; the line from the left, 0..0x7f00 */
void mv_own_knob(void *canvas, int x, int y, int w, u32 key, u32 slot)
{
    mv_ready();
    if (slot < INS_LINE || slot >= INS_LINE + INS_LINES)
        return;
    mv_place(canvas, x, y, w, key, slot, 0, 0x7F00, 0);
}

/* a knob of record ID drawn on the canvas: keep it, and draw its line from (x, y), W pixels wide,
 * LO at its left end and HI at its right (record units, 0..0x7f00); from its centre when the
 * record's default is the middle of LO..HI */
void mv_knob(void *canvas, int x, int y, int w, u32 id, int lo, int hi)
{
    extern void mxp_cell(int x0, int y0, u32 id);
    mxp_cell(x - MV_DX, y - MV_DY, id);                 /* (2026-11-20) the routes popup: our pages' knobs (they draw
                                                         * their own, never a stock cell) are its places too */
    mv_ready();
    int filter, m = track_sound(&filter);
    if (m < 0 || id == 0 || id > MV_ID_TOP)
        return;
    u32 slot = (u32)RECORD(id)[1];
    if (slot < 1u || slot > MV_SLOT_TOP || slot == MV_L4_DEST || SLOT_ID(slot, m, filter) != id)
        return;
    if (slot == 4u || slot == 12u || slot == 20u)       /* (2026-11-18) LFO1-3 DEST: a muted first route is heard as
                                                         * DEST none (csrc/matrix mx_dmask), not a modulation */
        return;
    extern int env2_field_drawn(u32 id);                /* (2026-11-18) ENV2's page: its knobs are stock's AMP records
                                                         * (62..66, 73, 74) drawn with ENV2's values, and the voice row's
                                                         * cells under those records are ENV1's (the amp's): ENV2's
                                                         * ATK..REL (62..66) read ENV2's own knob row (the routes into
                                                         * ENV2, csrc/matrix); (2026-11-20) MODE, RSET and H too; G none */
    if (env2_field_drawn(id)) {
        extern int env2_field_index(u32 id);
        int f = env2_field_index(id);
        if (f < 0)
            return;
        slot = E2_LINE + (u32)f;
    }
    mv_place(canvas, x, y, w, id, slot, lo, hi, 2 * RECORD(id)[4] == lo + hi);
}

/* a knob kept and its line drawn: KEY the cell's own (a record id, or 0x8000 | an index of ours), SLOT what line_at
 * reads, LO..HI across it, from its centre when CENTRE */
static void mv_place(void *canvas, int x, int y, int w, u32 id, u32 slot, int lo, int hi, int centre)
{
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
        own_reset(c, slot);
    }
    c->slot = (u8)slot;
    c->gen = MV->gen;
    c->w = (u8)(w < 2 ? 2 : w > 255 ? 255 : w);
    c->x = (short)x;
    c->y = (short)y;
    c->lo = lo;
    c->hi = hi;
    c->from = (u8)(centre ? (c->w - 1) / 2 : 0);
    MV->n++;
    /* the line alone later only if its row (32 px at most) and the label's rows under it are on the screen;
     * the page's own pixels in its row are kept (a graph across cells there: a full draw ORs the line over
     * them). The label is the cell's own and drawn before the line; the page's graphs, drawn after the
     * cells, stay above it; anything else that covers the line covers the label or marks the line's row */
    const u8 *buf = CANVAS_BUF(canvas);
    int on = buf && x >= 0 && c->w <= 32 && x + c->w <= 128 && y >= 1 && y <= 63;
    /* (2026-11-18, the User: "High cpu is bad"; scratch/unit-now/cpu-spikes.md) while a knob turns, a cell that shows
     * no line (nothing modulates it, or its linger is over) keeps no bookkeeping (the row's own pixels, the guard rows
     * and their hash, here and in mv_end): it is not clean, and should a line appear on it the full redraw draws it and
     * keeps the cell again. A cell whose line shows keeps it, so its line still goes alone between the turn's full
     * draws (the User: "the bar/line that display is slow"; page.c wr_turning) */
    int at = line_at(c, heard_voice(), FRAMES);
    c->drawn = (short)at;
    extern int wr_turning(void);
    if (on && at < 0 && wr_turning())
        on = 0;
    c->under = 0;
    for (int k = 0; on && k < c->w; k++)
        if (px_get(buf, x + k, y))
            c->under |= 1u << k;
    c->clean = (u8)on;
    if (on) {
        int g0, g1;
        c->above = !guard_rows(buf, c, 0, &g0, &g1);   /* no label under it (ONESHOT 2/2's top row): its widget above */
        if (!guard_rows(buf, c, c->above, &g0, &g1))
            c->clean = 0;                               /* blank both ways: nothing would show an overdraw */
        else
            c->hash = area_hash(buf, x, c->w, g0, g1, 0);
    }
    if (at < 0)
        return;
    MV->lines++;
    for (int k = 0; k < c->w; k++)
        if (line_px(c, k, at))
            SET_PIXEL(canvas, x + k, y, 1);
}

/* the end of a full draw (page.c wr_screen, after everything of ours): DREW, stock's page was drawn
 * this time. Each cell drawn is clean only if nothing drew over it after its line (its row exactly
 * the line, its label's rows as they were), either as drawn or all inverted (a p-locked cell lit) */
void mv_end(void *canvas, int drew)
{
    mv_ready();
    const u8 *buf = CANVAS_BUF(canvas);
    MV->back = drew ? (u8 *)buf : 0;
    for (int j = 0; j < NCELL; j++) {
        struct mv_cell *c = &MV->c[j];
        if (c->gen != MV->gen || !c->id || !c->clean)
            continue;
        int ok0 = 1, ok1 = 1;
        for (int k = 0; k < c->w && (ok0 || ok1); k++) {
            int p = px_get(buf, c->x + k, c->y), want = row_px(c, k, c->drawn);
            ok0 &= p == want;
            ok1 &= p != want;
        }
        int g0, g1;
        guard_rows(buf, c, c->above, &g0, &g1);
        if (ok0 && area_hash(buf, c->x, c->w, g0, g1, 0) != c->hash)
            ok0 = 0;
        if (ok1 && area_hash(buf, c->x, c->w, g0, g1, 1) != c->hash)
            ok1 = 0;
        c->clean = (u8)(drew && (ok0 || ok1));
        c->inv = (u8)(!ok0 && ok1);
    }
    for (int j = 0; j < NCELL; j++) {           /* two lines sharing pixels of a row: neither alone */
        struct mv_cell *c = &MV->c[j];
        if (c->gen != MV->gen || !c->id)
            continue;
        for (int k = j + 1; k < NCELL; k++) {
            struct mv_cell *d = &MV->c[k];
            if (d->gen == MV->gen && d->id && d->y == c->y && d->x < c->x + c->w && c->x < d->x + d->w)
                c->clean = d->clean = 0;
        }
        if (!c->clean)
            MV->dirty++;
    }
}

/* the moved lines rewritten in BACK (the glass's frame) and their changed groups sent; AT: each cell's
 * new end column */
static void mv_lines_only(const short *at)
{
    u8 *b = MV->back;
    u32 sent0 = 0, sent1 = 0, sent2 = 0, sent3 = 0;  /* the 128 groups (16 columns of 8 x 8 pages) changed (no
                                                       * array: gcc would clear it with a memset the chunk lacks) */
    for (int j = 0; j < NCELL; j++) {
        struct mv_cell *c = &MV->c[j];
        if (c->gen != MV->gen || !c->id || at[j] == c->drawn)
            continue;
        int y = c->y, p = y >> 3;
        u8 bit = (u8)(0x80u >> (y & 7));
        for (int k = 0; k < c->w; k++) {
            int x = c->x + k;
            u8 *q = b + 8 * x + p, old = *q;
            u8 nw = (u8)(row_px(c, k, at[j]) ^ c->inv ? old | bit : old & ~bit);
            if (nw != old) {
                *q = nw;
                u32 g = (u32)(x >> 3) + 16u * (u32)p, bit_g = 1u << (g & 31);
                if (g < 32u) sent0 |= bit_g;
                else if (g < 64u) sent1 |= bit_g;
                else if (g < 96u) sent2 |= bit_g;
                else sent3 |= bit_g;
            }
        }
        c->drawn = at[j];
    }
    int n = 0;
    for (u32 g = 0; g < 128u; g++) {
        u32 word = g < 32u ? sent0 : g < 64u ? sent1 : g < 96u ? sent2 : sent3;
        if (!(word & (1u << (g & 31))))
            continue;
        u32 col = 8u * (g & 15u), page = g >> 4;
        u8 bytes[8];
        for (u32 k = 0; k < 8u; k++)
            bytes[k] = b[8u * (col + k) + page];
        GLASS_GROUP(col, page, bytes);
        n++;
    }
    if (n)
        GLASS_SHOW();
    MV->groups += (u32)n;
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
    if (id == 0 || id > MV_ID_TOP)
        return;
    const int *r = RECORD(id);
    mv_cell_span(canvas, x0, y0, id, r[2], r[3]);
}

/* the UI loop's redraw test (page.c wr_poll): a shown line would move -> the lines alone when every
 * moved cell is clean, else the full redraw */
void mv_poll(void *screen)
{
    mv_ready();
    extern int scope_visible(void);             /* the scope covers the page's cells: their lines are not shown, and */
    extern int ovw_visible(void);               /* their moves must not redraw the page under it (csrc/scope); nor */
    if (scope_visible() || ovw_visible())       /* under a page key's overview (csrc/inserts/ovw.c) */
        return;
    extern int mxp_visible(void);               /* the routes popup covers them too (2026-11-18: their moves asked full */
    if (mxp_visible())                          /* redraws under it; csrc/matrix/routes_pop.c) */
        return;
    u32 now = FRAMES;
    if ((u32)(MV->next - now) > REDRAW && (int)(now - MV->next) < 0)
        MV->next = now;                         /* never further ahead than one wait: a deadline is never kept past it */
    if ((int)(now - MV->next) < 0)
        return;
    MV->polls++;
    MV->next = now + POLL;
    /* a full redraw due but held back while a knob turns (page.c wr_redraw_held): BACK is still the glass, and the
     * held draw redraws every line as it is then, so the lines may still go alone meanwhile (the User, 2026-11-18:
     * "the bar/line that display is slow": they waited for the turn's full draws) */
    extern int wr_redraw_held(void);
    int v = heard_voice(), moved = 0,
        alone = MV->back && FB_BACK == MV->back && (!IS_DIRTY(screen) || wr_redraw_held());
    short at[NCELL];
    for (int k = 0; k < NCELL; k++) {
        struct mv_cell *c = &MV->c[k];
        at[k] = c->drawn;
        if (c->gen != MV->gen || !c->id)
            continue;
        at[k] = (short)line_at(c, v, now);
        if (at[k] != c->drawn) {
            moved++;
            alone &= c->clean;
        }
    }
    if (!moved)
        return;
    MV->next = now + REDRAW;
    MV->asks++;
    if (!alone) {
        MV->fulls++;
        SET_DIRTY(screen);
        return;
    }
    MV->next = now + REDRAW_ALONE;              /* a line alone costs a row and its few groups: it may come sooner */
    MV->parts++;
    mv_lines_only(at);
}
