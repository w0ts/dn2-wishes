/* AMP's ENV2 page (amp_pages.h AMP_ENV2; the User, 2026-11-12: ENV2 is "just a clone of env1 (how it is today)",
 * routed only; docs/matrix.md). OS 1.12.
 *
 * Drawn by stock's own AMP page code, with ENV2's values (the User, 2026-11-13: "why is ENV2 not like ENV1 (no shape
 * preview, knobs)"): stock's AMP draw (0x4006dfb6) walks the 8 places, takes each place's record id from the table
 * of the envelope's MODE (0x400c25d8: 14 AHD, 15 ADSR), its value from the sound (0x4006538e) and draws its knob
 * with the page's own method (+180), then the shape (0x40065766 AHD, 0x4006594c ADSR, from plain values). Here the
 * same walk on stock's AMP page object, the ids from ENV2's MODE and the values ENV2's: so the same knobs, labels,
 * lock look and shape. The places (measured in 1.12): ADSR A ATK, B DEC, C SUS, D REL, E RSET, F MODE; AHD A ATK,
 * B HOLD, C DEC, D none, E RSET, F MODE; G and H (records 71, 72: PAN, VOL) are the sound's, not ENV2's: drawn with
 * the sound's values as stock draws them (stock's getter), and their knobs left to stock's page beneath (scope.c). The values are a field of the track's sound's wishes record (WT_MX_ENV: ATK HOLD DEC SUS
 * REL MODE RSET, then a byte kept 0), saved with the sound; no record yet: stock's own defaults (each record's +16).
 *
 * Lockable (2026-11-12, the User: "Yes, p-lockable", ATK DEC SUS REL MODE RSET): a trig held, a knob turned sets
 * that step's lock on every held step (csrc/slides sl_e2_set: a lock record of ours, ids 203..208), and the page
 * shows the held trig's value as locked, as stock's knob shows a lock. (2026-11-20, the User) HOLD (AHD only) too: id
 * 210. A full lock pool refuses a lock, as stock's own.
 */
#include "../wishes/wish.h"
#include "../knobs/knob.h"
#include "../waverider/amp_pages.h"
#include "../waverider/widgets.h"

typedef signed char s8;

#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))   /* +16 the default (units of 0x100) */
#define PAGE_DOTS  ((void (*)(void *, void *, int, int, int))0x4006598Au)
#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70u)
#define AMP_PAGE_VTABLE 0x401E2320u
#define PLACES     ((u32 (*)(u32))0x400C25D8u)          /* (14 AHD, 15 ADSR) -> +8: the 8 places' record ids */
#define HILITE     ((u32 (*)(u32, u32))0x40113838u)     /* (page + 148, place): stock's highlight */
#define ANIM       ((u32 (*)(u32, u32))0x40113626u)     /* (page + 148, place): stock's knob animation */
#define EMPTY      0x446462A8u                          /* the sheet stock blits for a place with no record */
#define VALUE_OF   ((s32 (*)(u32, u32, u8 *))0x4006538Eu)   /* (page, id, &locked): stock's value of a place */
#define SHAPE_AHD  ((void (*)(u32, void *, int, int, s32, s32, s32, s32))0x40065766u)   /* ATK HOLD DEC 0 */
#define SHAPE_ADSR ((void (*)(u32, void *, int, int, s32, s32, s32, s32))0x4006594Cu)   /* ATK DEC SUS REL */
typedef void (*knob_fn)(u32, void *, int, int, u32, s32, u32, u32, u32, u32, u32);
extern u32 ins_view_of(u32 cls);                        /* csrc/inserts/ins.c */

enum { F_ATK, F_HOLD, F_DEC, F_SUS, F_REL, F_MODE, F_RSET, F_H, F_N = 8 };
/* (2026-11-19, the User) G and H: ENV2's DEST (our DEST popup for ENV2's routes, dest_pop.c) and DEP (ENV2's
 * attenuverter, byte 7 of the field as 127 - the knob: 0, every record before, is +63 = 100 %), drawn as stock's LFO1
 * DEST and DEP knobs (records 78, 83: their labels and texts). The sound's PAN and VOL stay on AMP 1/3 */
#define REC_G 78u
#define REC_H 83u
static const u8 REC_OF[8] = {62, 63, 64, 65, 66, 73, 74, REC_H};

/* a record id -> ENV2's field, -1 none */
static int field_of(u32 id)
{
    for (int f = 0; f < 8; f++)
        if (REC_OF[f] == id)
            return f;
    return -1;
}

/* G's value: the slot of ENV2's first route in the record (its order), 0 none (the User, Q8) */
static u32 env2_first_slot(u32 sound)
{
    u8 r[4u * 26u];
    int n = wish_get(sound, WT_MX_ROUTES, r, sizeof r);
    for (int i = 0; i + 4 <= n && i + 4 <= (int)sizeof r; i += 4)
        if ((r[i] & 0x7Fu) == 4u && r[i + 1] >= 25u && r[i + 1] <= 100u)
            return r[i + 1];
    return 0;
}

/* a field -> its lock kind (slides: ATK DEC SUS REL MODE RSET H HOLD; 2026-11-20, the User: HOLD lockable, id 210) */
static const s8 KIND_OF[8] = {0, 7, 1, 2, 3, 4, 5, 6};

/* place P's record id on ENV2's page, by ENV2's MODE: stock's own table; G and H ours; 0 none */
static u32 place_id(u32 mode, u32 p)
{
    if (p == 6u || p == 7u)
        return p == 6u ? REC_G : REC_H;
    u32 t = p < 8u ? PLACES(mode ? 15u : 14u) : 0u;
    return t ? *(const u32 *)(t + 8u + 4u * p) : 0u;
}

static int knob_of(const u8 *v, u32 f)  /* the field's knob value 0..127 (H stored as 127 - the knob) */
{
    return f == F_H ? 127 - (v[F_H] > 127u ? 127 : v[F_H]) : v[f];
}

static u32 sound_of_ui(void)
{
    u8 *kit = KIT_POINTER;
    return kit ? (u32)kit + 52u + 1163u * (UI_TRACK & 15u) : 0;
}

/* the track's ENV2: its record's field, else stock's defaults */
void env2_get(u32 sound, u8 *v)
{
    if (wish_get(sound, WT_MX_ENV, v, F_N) == F_N)
        return;
    for (u32 f = 0; f < 7u; f++)
        v[f] = (u8)(RECORD(REC_OF[f])[4] >> 8);
    v[F_H] = 0;                                         /* H 100 % */
}

int env2_visible(void)
{
    return amp_sub == AMP_ENV2;
}

extern u32 sl_e2_held(u32 j);                           /* csrc/slides: a held trig's lock, 0x10000 none held */
extern int sl_e2_set(u32 j, u32 value);

/* scope.c scope_pop: knob K (0 A .. 7 H) turned STEP detents -> 1 when a value changed */
int env2_turn(u32 k, int step)
{
    u32 sound = sound_of_ui();
    u8 v[F_N];

    if (!sound || k >= 8u || !step)
        return 0;
    env2_get(sound, v);
    u32 id = place_id(v[F_MODE], k);
    if (field_of(id) < 0)
        return 0;                                       /* none, or the sound's own (stock's page turns those) */
    u32 f = (u32)field_of(id);
    int top = (f == F_MODE || f == F_RSET) ? 1 : 127, kind = KIND_OF[f];
    /* (2026-11-19, the User: knob precision, csrc/knobs) the 0..127 knobs turn as our popups: a slow turn 1 every 3
     * counts; H (the attenuverter, 64 its 0) has the notch at 0 */
    int units = top == 1 ? step : kn_units(step);
    u32 lk = kind >= 0 ? sl_e2_held((u32)kind) : sl_e2_held(0);
    if (lk != 0x10000u) {                               /* a trig held: its lock (from the sound's value) */
        if (kind < 0)
            return 0;                                   /* (every field has a kind since 2026-11-20) */
        int o = lk != 0xFFFFu ? (int)lk : knob_of(v, f), x = o + units;
        x = x < 0 ? 0 : x > top ? top : x;
        if (f == F_H)
            x = kn_value(KN_KEY_POP | 0x4000u | KN_KEY_LOCK, o, x, 64);
        if (x == o && lk != 0xFFFFu)
            return 0;                                   /* (no lock yet: made at the value, as before) */
        return sl_e2_set((u32)kind, (u32)x);
    }
    int x = knob_of(v, f) + units;
    x = x < 0 ? 0 : x > top ? top : x;
    if (f == F_H)
        x = kn_value(KN_KEY_POP | 0x4000u, knob_of(v, f), x, 64);
    if (x == knob_of(v, f))
        return 0;
    v[f] = (u8)(f == F_H ? 127 - x : x);
    return wish_put(sound, WT_MX_ENV, v, F_N) == 0;
}

/* (2026-11-18, the User: "Ui lags like crazy"; scratch/unit-now/cpu-spikes.md: ENV2's page 4-5 screen updates a second
 * while a knob turns, stock's AMP page 9-11) stock's AMP page view's draw (its vtable + 0x10, 0x4006dfb6: the eight
 * knobs, the shape, then the level meter, vtable + 184) comes here (dnfw.waverider.coldfire AMP_DRAW_SLOT). While
 * ENV2's page is drawn over it (page.c wr_env2_covers: env2_draw clears x 18..127, y 0..53 and draws its own knobs and
 * shape there), stock's knobs and shape are not drawn under it: only the meter, as stock's draw ends. The same pixels
 * (everything stock's knobs and shape draw is in that rectangle), half the drawing. Any other time, stock's */
#define AMP_DRAW ((void (*)(u32, void *))0x4006DFB6u)
void env2_amp_draw(u32 view, void *canvas)
{
    extern int wr_env2_covers(void);
    if (!wr_env2_covers()) {
        AMP_DRAW(view, canvas);
        return;
    }
    ((void (*)(u32, void *, int))(*(const u32 *const *)view)[184 / 4])(view, canvas, 0);
}

/* (2026-11-18) while env2_draw draws ENV2's own knobs: their records are stock's AMP ones (62..66, 73, 74), and every
 * stock cell passes page.c wr_cell, where the moving lines (csrc/modulation/moving.c mv_knob) read the voice row's
 * cell of that record: ENV1's (the amp's), not ENV2's. ENV2's knobs are no destination (docs/matrix.md), so they get
 * no line; the sound's PAN and VOL, drawn in the same walk, keep theirs */
static u32 env2_drawing __attribute__((section(".data"))) = 0;

int env2_field_drawn(u32 id)
{
    return env2_drawing && (field_of(id) >= 0 || id == REC_G);
}

/* (2026-11-20) ID drawn as one of ENV2's own knobs -> its field (F_ATK .. F_H: ENV2's destination 0xE0 + it in the
 * matrix, matrix.c K_ order), -1 none (G, the sound's, or not ENV2's page) */
int env2_field_index(u32 id)
{
    return field_of(id);
}

/* the routes popup (csrc/matrix/routes_pop.c), on ENV2's page: ID is one of ENV2's own knobs there */
int env2_field_drawn_page(u32 id)
{
    return env2_visible() && (field_of(id) >= 0 || id == REC_G);
}

/* FUNC + long push on ENV2's page (routes_pop.c): ENV2's own knob back to its default (stock's record's, as ENV2 has
 * with no field); -> 1 when ID was ENV2's, 0 for stock to reset (PAN, VOL) */
int env2_reset(u32 id)
{
    u32 sound = sound_of_ui();
    int f = field_of(id);
    u8 v[F_N];
    if (env2_visible() && id == REC_G)
        return 1;                                       /* G: no default (its routes are the popup's) */
    if (!env2_visible() || f < 0 || !sound)
        return 0;
    env2_get(sound, v);
    u32 def = (u32)(RECORD(REC_OF[f])[4] >> 8);
    v[f] = (u8)(f == F_H ? 0 : f == F_MODE || f == F_RSET ? def != 0 : def > 127u ? 127u : def);   /* H: 100 % */
    wish_put(sound, WT_MX_ENV, v, F_N);
    return 1;
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
    cv_fill(c, x0, y0, x1, y1, on);             /* (2026-11-17) the same pixels a column word at a time: page.c */
}

/* page.c wr_screen, after stock's AMP page, while ENV2's is up: stock's places and shape drawn again with ENV2's
 * values (stock's own walk, 0x4006dfb6, on its page object); stock's title bar and left panel kept */
void env2_draw(void *c)
{
    u32 sound = sound_of_ui(), page = ins_view_of(AMP_PAGE_VTABLE);
    u8 v[F_N], locked[F_N] = {0};

    fill(c, 18, 0, 127, 53, 0);
    if (!sound || !page)
        return;
    env2_get(sound, v);
    for (u32 f = 0; f < 8u; f++) {                      /* a trig held: its locks shown */
        u32 lk = KIND_OF[f] >= 0 ? sl_e2_held((u32)KIND_OF[f]) : 0x10000u;
        if (lk != 0x10000u && lk != 0xFFFFu) {
            v[f] = (u8)(f == F_H ? 127u - lk : lk);
            locked[f] = 1;
        }
    }
    knob_fn knob = (knob_fn)(*(const u32 *const *)page)[180 / 4];
    env2_drawing = 1;                                   /* (moving.c: no line under ENV2's own knobs) */
    for (u32 col = 0; col < 4u; col++)
        for (u32 row = 0; row < 2u; row++) {
            u32 place = col + 4u * row, id = place_id(v[F_MODE], place);
            int x = 24 + 26 * (int)col, y = row ? 0 : 27;
            if (!id) {
                WG_BLIT(c, (const void *)EMPTY, x + 1, y + 7, 0);
                continue;
            }
            int f = field_of(id);
            u8 lk = 0;
            s32 val = id == REC_G ? (s32)(env2_first_slot(sound) << 8)        /* G: ENV2's first route */
                      : f >= 0 ? (s32)knob_of(v, (u32)f) << 8 : VALUE_OF(page, id, &lk);
            if (f >= 0)
                lk = locked[f];
            u32 hi = lk ? 1u : HILITE(page + 148u, place) & 0xFFu;
            knob(page, c, x, y, id, val, ANIM(page + 148u, place), lk, hi, id < 68u || id > 74u, 0);
        }
    env2_drawing = 0;
    if (v[F_MODE])
        SHAPE_ADSR(page, c, 0, 0, v[F_ATK] << 8, v[F_DEC] << 8, v[F_SUS] << 8, v[F_REL] << 8);
    else
        SHAPE_AHD(page, c, 0, 0, v[F_ATK] << 8, v[F_HOLD] << 8, v[F_DEC] << 8, 0);
    PAGE_DOTS(0, c, AMP_PAGES, AMP_ENV2, 7);
}
