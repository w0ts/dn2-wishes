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
 * shows the held trig's value as locked, as stock's knob shows a lock. HOLD (AHD only) has no lock kind: with a trig
 * held it does nothing. A full lock pool refuses a lock, as stock's own.
 */
#include "../wishes/wish.h"
#include "../waverider/amp_pages.h"
#include "../waverider/widgets.h"

typedef signed char s8;

#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define RECORD(id) ((const int *)(0x401F83A4u + 60u * (id)))   /* +16 the default (units of 0x100) */
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

enum { F_ATK, F_HOLD, F_DEC, F_SUS, F_REL, F_MODE, F_RSET, F_N = 8 };
static const u8 REC_OF[7] = {62, 63, 64, 65, 66, 73, 74};

/* a record id -> ENV2's field, -1 none */
static int field_of(u32 id)
{
    for (int f = 0; f < 7; f++)
        if (REC_OF[f] == id)
            return f;
    return -1;
}

/* a field -> its lock kind (slides: ATK DEC SUS REL MODE RSET), -1 none (HOLD) */
static const s8 KIND_OF[7] = {0, -1, 1, 2, 3, 4, 5};

/* place P's record id on ENV2's page, by ENV2's MODE: stock's own table; 0 none */
static u32 place_id(u32 mode, u32 p)
{
    u32 t = p < 8u ? PLACES(mode ? 15u : 14u) : 0u;
    return t ? *(const u32 *)(t + 8u + 4u * p) : 0u;
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
    v[7] = 0;
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
    u32 lk = kind >= 0 ? sl_e2_held((u32)kind) : sl_e2_held(0);
    if (lk != 0x10000u) {                               /* a trig held: its lock (from the sound's value) */
        if (kind < 0)
            return 0;                                   /* HOLD: no lock kind */
        int x = (int)(lk != 0xFFFFu ? lk : v[f]) + step;
        x = x < 0 ? 0 : x > top ? top : x;
        return sl_e2_set((u32)kind, (u32)x);
    }
    int x = (int)v[f] + step;
    x = x < 0 ? 0 : x > top ? top : x;
    if (x == v[f])
        return 0;
    v[f] = (u8)x;
    return wish_put(sound, WT_MX_ENV, v, F_N) == 0;
}

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
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
    for (u32 f = 0; f < 7u; f++) {                      /* a trig held: its locks shown */
        u32 lk = KIND_OF[f] >= 0 ? sl_e2_held((u32)KIND_OF[f]) : 0x10000u;
        if (lk != 0x10000u && lk != 0xFFFFu) {
            v[f] = (u8)lk;
            locked[f] = 1;
        }
    }
    knob_fn knob = (knob_fn)(*(const u32 *const *)page)[180 / 4];
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
            s32 val = f >= 0 ? (s32)v[f] << 8 : VALUE_OF(page, id, &lk);  /* ENV2's, or the sound's as stock's */
            if (f >= 0)
                lk = locked[f];
            u32 hi = lk ? 1u : HILITE(page + 148u, place) & 0xFFu;
            knob(page, c, x, y, id, val, ANIM(page + 148u, place), lk, hi, id < 68u || id > 74u, 0);
        }
    if (v[F_MODE])
        SHAPE_ADSR(page, c, 0, 0, v[F_ATK] << 8, v[F_DEC] << 8, v[F_SUS] << 8, v[F_REL] << 8);
    else
        SHAPE_AHD(page, c, 0, 0, v[F_ATK] << 8, v[F_HOLD] << 8, v[F_DEC] << 8, 0);
    PAGE_DOTS(0, c, AMP_PAGES, AMP_ENV2, 7);
}
