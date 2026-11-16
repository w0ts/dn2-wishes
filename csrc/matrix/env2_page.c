/* AMP's ENV2 page (amp_pages.h AMP_ENV2; the User, 2026-11-12: ENV2 is "just a clone of env1 (how it is today)",
 * routed only; docs/matrix.md). OS 1.12.
 *
 * Laid out as stock's AMP page lays out its envelope: A ATK, B DEC, C SUS, D REL, E RSET, F MODE (stock's places and
 * records 62, 64, 65, 66, 74, 73). HOLD (record 63) is not on stock's 1.12 page either; ENV2 keeps it at stock's
 * default. The values are a field of the track's sound's wishes record (WT_MX_ENV: ATK HOLD DEC SUS REL MODE RSET,
 * then a byte kept 0), saved with the sound; no record yet: stock's own defaults (each record's +16).
 *
 * Lockable (2026-11-12, the User: "Yes, p-lockable", all six): a trig held, a knob turned sets that step's lock on every
 * held step (csrc/slides sl_e2_set: a lock record of ours, ids 203..208), and the page shows the held trig's value,
 * a lock drawn as stock draws one (its widget's area inverted). A full lock pool refuses it, as stock's own.
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
#define LOCK_FILL  ((void (*)(void *, int, int, int, int, int))0x40114B22u)   /* (c, x0, y0, x1, y1, -1): inverted */

enum { F_ATK, F_HOLD, F_DEC, F_SUS, F_REL, F_MODE, F_RSET, F_N = 8 };
static const u8 REC_OF[7] = {62, 63, 64, 65, 66, 73, 74};

/* knob A.. -> the field it turns, its label, its top */
static const u8 FIELD_OF[6] = {F_ATK, F_DEC, F_SUS, F_REL, F_RSET, F_MODE};
static const char *const LABEL[6] = {"ATK", "DEC", "SUS", "REL", "RSET", "MODE"};

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
static const u8 LOCK_OF[6] = {0, 1, 2, 3, 5, 4};        /* knob A.. -> the lock kind (ATK DEC SUS REL MODE RSET) */

/* scope.c scope_pop: knob K (0 A .. 7 H) turned STEP detents -> 1 when a value changed */
int env2_turn(u32 k, int step)
{
    u32 sound = sound_of_ui();
    u8 v[F_N];

    if (!sound || k >= 6u || !step)
        return 0;
    env2_get(sound, v);
    u32 f = FIELD_OF[k];
    int top = (f == F_MODE || f == F_RSET) ? 1 : 127;
    u32 lk = sl_e2_held(LOCK_OF[k]);
    if (lk != 0x10000u) {                               /* a trig held: its lock (from the sound's value) */
        int x = (int)(lk != 0xFFFFu ? lk : v[f]) + step;
        x = x < 0 ? 0 : x > top ? top : x;
        return sl_e2_set(LOCK_OF[k], (u32)x);
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

/* page.c wr_screen, after stock's AMP page, while ENV2's is up: the places ours, stock's title bar and left panel
 * kept */
void env2_draw(void *c)
{
    u32 sound = sound_of_ui();
    u8 v[F_N];

    fill(c, 18, 0, 127, 53, 0);
    if (!sound)
        return;
    env2_get(sound, v);
    int locked[6];
    for (u32 k = 0; k < 6u; k++) {                      /* a trig held: its locks shown */
        u32 lk = sl_e2_held(LOCK_OF[k]);
        locked[k] = lk != 0x10000u && lk != 0xFFFFu;
        if (locked[k])
            v[FIELD_OF[k]] = (u8)lk;
    }
    for (u32 k = 0; k < 4u; k++)
        wg_knob(c, (int)k, v[FIELD_OF[k]]);
    wg_toggle(c, 4, v[F_RSET]);
    wg_choice(c, 5, v[F_MODE] ? "ADSR" : "AHD");
    for (u32 k = 0; k < 6u; k++) {
        wg_label(c, (int)k, LABEL[k]);
        if (locked[k])                                  /* stock's p-lock look: the widget's area inverted */
            LOCK_FILL(c, wg_x((int)k) - 3, wg_y((int)k) + 6, wg_x((int)k) + 21, wg_y((int)k) + 24, -1);
    }
    PAGE_DOTS(0, c, AMP_PAGES, AMP_ENV2, 7);
}
