/* The DEST popup: "the routes OUT of this LFO" (the User, 2026-11-18: "editing destination in modulation page is cpu.
 * and we need to redo this popup. it does not match our modulation matrix. we need in the popup to have at the top
 * the assigned ones, with their value, same shortcuts with y/n"). The source-side mirror of the routes popup
 * (routes_pop.c). OS 1.12.
 *
 * Opens on an LFO page (LFO1-3, and LFO4 with DN2_LFO4) on every gesture that made stock 1.12's DEST list (the User,
 * 2026-11-18: "i just want ours"; emulator, emu_destpop.py paths): D turned (a fast turn, FUNC or a trig held too: the
 * twist only opens it, as stock's lists, no depth moves), D pushed (the press), a push-and-turn; with a trig held as
 * well (stock set a DEST p-lock there: ours edits the sound's routes). FUNC + push stays stock's: stock's DEST list
 * (2026-11-19: the knob-push survey measured it on stock 1.12; the routes popup took that push until then). On no other
 * gesture is stock's list (its view 0x4010660c) made. Why (emulator, docs/matrix.md "The DEST popup"):
 * stock's list checks a value by building the whole destination list anew (0x40039904 -> the builder 0x4003951e: a
 * virtual lookup per slot, the mask, push_back, then std::sort with two std::map lookups a compare, about 215k
 * instructions), 16 times as it opens and 4 times a row moved: the CPU label lit. Here the list is built once, at the
 * open, by the same walk and in the same order: slot 0 .. the build's own bound (the builder's moveq), the entry of
 * the sound's parameter set (vtable + 80, the object PARAM_SET returns), kept when mod_lfo_mask lets this LFO's want
 * through, then sorted by stock's category rank (0x400dbe4c's page id in the table at 0x4028c504; a page not in it
 * ranks 0, as the std::map's operator[] gives) and then by record id, as stock's comparator 0x4003907e.
 *
 * The routes (routes.c; the User, 2026-11-18: our matrix the only source, stock's DEST and DEP the first route's
 * copy): an LFO's first route is its DEST and DEP, its others are the record's; LFO4 has its DEST alone (lfo4
 * evaluates that one). The rows: this LFO's routes first (the first route, then the record's of this source, muted ones
 * too: each an assigned destination with its value), in the list's order, then the rest of the list in its order (no
 * "None": NO held deletes). A route row: the category, the short name, the depth (stock DEP's units / 256), the moving
 * bar as the routes popup draws it (dotted when muted; LFO4's has no live part); the lit route says DEST (the first
 * route, saved in stock's DEST and DEP), REC or MUTE. Any other row: the category on the first row of its group, the
 * long name. The header: LFOn DEST and the routes in use (LFO1-3 share 16: their DESTs and the record's LFO routes;
 * LFO4 1). The footer: the lit route's long name, or what a turn or YES on the lit row would do (ADD AS DEST, ADD TO
 * MATRIX, FULL, LFO CTRL: 1 ROUTE, LFO4: 1 ROUTE). The order is made at the open and kept until the popup closes.
 *
 * The keys, the routes popup's: D turned sets the lit row's depth (0 removes the route at once; turned from 0 on a
 * row with no route, the route is made: the first route when DEST is free, else a route of the record, while the pool
 * has room); D's push-and-turn, UP, DOWN move the lit row; FUNC + DOWN / FUNC + UP jump it by sections (the LFO's
 * routes, then each of stock's categories; 2026-11-19, the User, as the routes popup's). YES unmutes the lit route, or adds the lit row at +32
 * (ADD_DEP); NO (a tap) mutes it, NO held 0.6 s deletes it, FUNC + NO deletes every route of this LFO. Muted: a route
 * of the record gets MUTED in its source byte, the first route the record's mark (DEST and DEP kept); a first route
 * into an LFO's controls, and LFO4's, say CAN'T MUTE. An LFO's control (slots 1..24, LFO4's 101..108) can only be a
 * first route: with DEST in use, LFO CTRL: 1 ROUTE. The first route deleted: its DEP p-locks on this track freed, DEST
 * 0 and DEP's default, then the LFO's next route of the record moves into DEST and DEP. Closed with everything kept: D
 * pushed alone, any key that leaves (it then does its work), another knob turned (it then turns that knob), a track
 * change, a stock question, 6 s untouched.
 *
 * Drawing (cheap from the start): the popup covers the screen, so after the first full draw its frames are drawn
 * alone, as the scope's (csrc/scope/scope.c): the frame on the glass (BACK) copied to FRONT, only what changed drawn
 * over it (the bars alone at 15 a second while a route moves; everything after a key), stock's panel_diff sends the
 * changed groups. A frame only when the panel UART's ring is all but empty (never queued), at most every 20 ms after a
 * key. A full redraw (stock's page under it) only when stock asked for one or the glass holds another frame.
 */
#include "../wishes/wish.h"
#include "../knobs/knob.h"
#include "routes.h"

#ifndef DN2_LFO4
#define DN2_LFO4 0
#endif

typedef signed char s8;
typedef short s16;

#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define IS_DIRTY   ((u8 (*)(void *))0x4011D5D4u)
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)       /* 1,500 a second */
#define FONT       0x44508ED8u                          /* the grid's label font (routes_pop.c's) */
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))   /* +4 slot, +16 default, +0x28 long, +0x2c page, +0x30 short */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define UI_OWNER   ((u32 (*)(void))0x4018AC5Au)
#define PARAM_SET  ((u32 (*)(u32, u32, u32))0x40041A40u)
#define SET_VALUE  ((u32 (*)(u32, u32, u32, u32, u32, u32, u32))0x40037326u)
#define CATEGORY   ((u32 (*)(u32))0x400DBE4Cu)          /* an entry's page id: stock's comparator's */
#define RANKS      ((const int *)0x4028C504u)           /* the category order: 26 page ids */
#define NRANKS     26
#define WALK_END   (*(const u8 *)0x400395B9u)           /* the builder's moveq #101 (lfo4's 109): its slot bound */
#define OWNER      ((volatile u32 *)0x80005308u)
#define MIDI_TYPE  4
/* the frames drawn alone (scope.c's) */
#define FB_FRONT   (*(u8 *volatile *)0x402A10C8u)
#define FB_BACK    (*(u8 *volatile *)0x402A10CCu)
#define LOOP_BUF   (*(u8 **)0x4059E1B0u)
#define CANVAS_NEW ((void (*)(void *, int, int, u8 *, void *))0x40113E2Au)
#define CANVAS_AID ((void *)0x4059DDB0u)
#define PANEL_DIFF ((u32 (*)(void))0x40131FD2u)
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))
#define UART_IDLE  128u

#define IT_KEY     0
#define IT_KNOB    1
#define F_PRESS    0x01
#define F_REPEAT   0x08                                 /* a held key's repeat (ldp_pop) */
#define F_RELEASE  0x10
#define K_YES      10
#define K_NO       12
#define K_ARROW_UP 11
#define K_ARROW_DN 14
#define K_FUNC     17
#define K_PUSH0    41
#define KNOB_D     3                                    /* DEST's knob on an LFO page */
#define KNOB_G     6                                    /* (2026-11-19) ENV2's DEST on ENV2's page (env2_page.c) */
#define ENV2       4                                    /* P.lfo: ENV2's routes (source 4), every one the record's */
#define ENV_CAP    4

#define LONG       900u                                 /* 0.6 s: NO held deletes */
#define IDLE       9000u                                /* 6 s untouched: closed */
#define BARS       100u                                 /* frames: the bars 15 a second */
#define SOON       30u                                  /* frames: a key's frame at most every 20 ms */
#define RETRY      15u                                  /* frames: the UART busy, looked at again */
#define SAY_TIME   1500u
#define SHOWN      5
#define MAXE       128                                  /* the list's room (stock's LFO4 list: 92) */
#define NONE       0x4000
#define DEP_TOP    0x7FFE
#define ADD_DEP    0x6000                               /* YES on a row with no route: +32 */
#define NONE_REC   19                                   /* stock's "None" entry */

extern int smp_func_held;
extern u32 smp_held_lo, smp_held_hi;
extern int smp_question_up(void);
extern int smp_overlay_dirty;
extern s8 sl_lastv[16];
extern int rec_overlay;
extern int amp_sub;
extern int ins_visible(void);
extern int mxp_visible(void);
extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
int mx_route_level(u32 v, u32 src);
u32 mod_lfo_mask(u32 rec, u32 want);

static const u16 DEST_REC[4] = {78, 88, 98, 324};       /* LFO1-4 DEST and DEP (lfo4's records 324, 329) */
static const u16 DEP_REC[4] = {83, 93, 103, 329};
static const u16 WANT[4] = {0x1E00, 0x0E00, 0x0600, 0x0200};    /* the builder's want (LFO4: lfo4's fourth step) */

struct ldp_state {                                      /* the checks read up .. nroutes (scripts/emu_destpop.py) */
    int up, lfo;
    u32 track, lit, last, n, nroutes;
    u32 no_at;
    int no_down, no_long, turned;
    const char *say;
    u32 say_at;
    u32 next_draw, frame_at;                            /* the next frame due; the last one's */
    int full;                                           /* a frame's every row due (else the bars alone) */
    int said;                                           /* a word drawn: a full frame when it goes */
    u8 *back;                                           /* the frame on the glass is ours (drawn whole by us) */
    u32 knob;                                           /* (2026-11-19) the knob it opened on: D (an LFO), G (ENV2) */
};
struct ldp_state ldp_p D_;
#define P ldp_p

u16 ldp_rows[MAXE] D_ = {0};                            /* the rows while up: entries, the routes first (the checks) */
u32 ldp_opens D_ = 0, ldp_refusals D_ = 0, ldp_turns D_ = 0, ldp_keys D_ = 0, ldp_erased D_ = 0;
u32 ldp_full D_ = 0, ldp_alone D_ = 0, ldp_dropped D_ = 0, ldp_built D_ = 0;   /* frames full, alone, dropped; lists */
u32 ldp_routes_drawn D_ = 0;
int ldp_detents D_ = 0;                                 /* the knob items' detents, summed (the checks) */                            /* the route rows drawn (bit: place on screen) */

/* the page's knob D as the last draw left it (page.c wr_cell): its record id */
static u32 cell_d D_, cell_gen D_, draw_gen D_ = 1;

void ldp_draw_begin(void)
{
    draw_gen++;
}

void ldp_cell(int x0, int y0, u32 id)                   /* page.c wr_cell: knob D's place only (routes_pop.c's map) */
{
    if (y0 >= 13 && x0 >= 24 + 3 * 26 - 13 && x0 <= 24 + 3 * 26 + 12) {
        cell_d = id;
        cell_gen = draw_gen;
    }
}

static int lfo_of_cell(void)                            /* knob D shows an LFO's DEST: 0..3, else -1 */
{
    if (cell_gen != draw_gen && cell_gen + 1u != draw_gen)
        return -1;
    for (int l = 0; l < (DN2_LFO4 ? 4 : 3); l++)
        if (cell_d == DEST_REC[l])
            return l;
    return -1;
}

/* --- the routes: read and written (LFO1-3 through routes.c; LFO4 its own DEST and DEP, lfo4's table) ---------- */
static int midi_track(u32 t)
{
    u8 *kit = KIT_POINTER;
    return !kit || (s8)kit[52u + 1163u * t + 0xDEu] == MIDI_TYPE;
}

static u32 slot_of(u32 e)
{
    return (u32)RECORD(e)[1];
}

#if DN2_LFO4
#define EXT_FIND ((u16 *(*)(u32))LFO4_EXT_FIND)
#define EXT_SET ((void (*)(u32, u32, u32))LFO4_EXT_SET)
#define EXT_DEFAULT ((const u16 *)LFO4_EXT_DEFAULT)
#endif

static u32 param_get(u32 rid)                           /* the popup's track's value of a DEST or DEP record */
{
#if DN2_LFO4
    if (rid >= 321u) {                                  /* lfo4's table: index slot - 101 */
        u32 s = mxr_sound(P.track);
        const u16 *v = s ? EXT_FIND(s) : 0;
        u32 k = slot_of(rid) - 101u;
        return v ? v[k] : EXT_DEFAULT[k];
    }
#endif
    return mxr_stock(P.track, rid);
}

static void param_set(u32 rid, u32 value)
{
#if DN2_LFO4
    if (rid >= 321u) {
        u32 s = mxr_sound(P.track);
        if (s)
            EXT_SET(s, slot_of(rid) - 101u, value);
        return;
    }
#endif
    mxr_stock_set(P.track, rid, value);
}

static u32 dest_slot(void)                              /* ENV2: no DEST of stock's */
{
    return P.lfo == ENV2 ? 0u : param_get(DEST_REC[P.lfo]) >> 8;
}

/* entry E's route from this LFO: its depth (NONE: none) and where (1 the first route: DEST and DEP; 2 the record's
 * at byte AT); MUTED whether it is muted */
static u32 route_of(u32 e, int *where, int *at, int *muted)
{
    u8 v[MXR_BUF];
    u32 s = slot_of(e);
    *where = 0;
    *at = -1;
    *muted = 0;
    if (s && dest_slot() == s) {
        *where = 1;
        *muted = P.lfo < 3 && mxr_first_muted(P.track, (u32)P.lfo);
        return P.lfo < 3 ? mxr_first_dep(P.track, (u32)P.lfo)   /* (2026-11-19) its own depth: DEP is the attenuverter */
                         : param_get(DEP_REC[P.lfo]);           /* LFO4: DEP its one route's depth (the User, Q7) */
    }
    if (P.lfo != 3) {
        int n = mxr_get(P.track, v);
        for (int i = 0; i + 4 <= n; i += 4)
            if (!mxr_is_mark(v + i) && (v[i] & ~MXR_MUTED) == (u32)P.lfo && v[i + 1] == s) {
                *where = 2;
                *at = i;
                *muted = (v[i] & MXR_MUTED) != 0;
                return (u32)v[i + 2] << 8 | v[i + 3];
            }
    }
    return NONE;
}

static u32 env2_used(void)                              /* ENV2's routes of the record (its own four) */
{
    u8 v[MXR_BUF];
    int n = mxr_get(P.track, v);
    u32 c = 0;
    for (int i = 0; i + 4 <= n; i += 4)
        c += !mxr_is_mark(v + i) && (v[i] & ~MXR_MUTED) == (u32)ENV2;
    return c;
}

static u32 pool_used(void)                              /* LFO1-3: their shared 16; LFO4: its DEST; ENV2: its 4 */
{
    return P.lfo == ENV2 ? env2_used() : P.lfo == 3 ? dest_slot() != 0u : mxr_pool(P.track);
}

enum { ADD_DEST = 1, ADD_REC, ADD_CTRL, ADD_ONE, ADD_FULL };

static int add_kind(u32 e)                              /* where a new route to E would go, or why not */
{
    u8 v[MXR_BUF];
    u32 s = slot_of(e);
    if (P.lfo == 3)                                     /* LFO4: its DEST alone (lfo4 evaluates that one) */
        return dest_slot() ? ADD_ONE : ADD_DEST;
    if (P.lfo == ENV2) {                                /* ENV2: the record's, four at most */
        int n = mxr_get(P.track, v);
        return env2_used() >= ENV_CAP || mxr_count(v, n, 0) >= MXR_ROUTES || n + 4 > (int)MXR_BUF ? ADD_FULL : ADD_REC;
    }
    if (pool_used() >= MXR_POOL)
        return ADD_FULL;
    if (!dest_slot())
        return ADD_DEST;
    if (mxr_ctrl_slot(s))                               /* an LFO's control: the first route only */
        return ADD_CTRL;
    int n = mxr_get(P.track, v);
    if (mxr_count(v, n, 1) >= MXR_LFO || mxr_count(v, n, 0) >= MXR_ROUTES || n + 4 > (int)MXR_BUF)
        return ADD_FULL;
    return ADD_REC;
}

static const char *refusal(int k)
{
    return k == ADD_FULL ? "FULL" : k == ADD_CTRL ? "LFO CTRL: 1 ROUTE" : "LFO4: 1 ROUTE";
}

/* the first route deleted: DEST 0, its depth none (LFO4: DEP's default), then the LFO's next route of the record
 * moves into DEST and the first route's depth (routes.c: a stock unit keeps playing its main route). (2026-11-19) DEP
 * and its p-locks are the LFO's attenuverter: kept */
static void del_first(void)
{
    if (P.lfo == 3) {
        param_set(DEST_REC[3], 0);
        param_set(DEP_REC[3], (u32)RECORD(DEP_REC[3])[4]);
        return;
    }
    mxr_drop_first(P.track, (u32)P.lfo);
}

/* the lit row's depth set to DEP (NONE removes the route at once, as in the routes popup) */
static void set_depth(u32 e, u32 dep)
{
    u8 v[MXR_BUF + 4];
    int where, at, muted, n = P.lfo != 3 ? mxr_get(P.track, v) : 0;
    route_of(e, &where, &at, &muted);
    if (where == 1) {
        if (dep == NONE)
            del_first();
        else if (P.lfo < 3)
            mxr_first_set(P.track, (u32)P.lfo, dep);
        else
            param_set(DEP_REC[P.lfo], dep);
        return;
    }
    if (where == 2) {
        if (dep == NONE) {
            mxr_put(P.track, v, mxr_drop(v, n, at));
            return;
        }
        v[at + 2] = (u8)(dep >> 8);
        v[at + 3] = (u8)dep;
        mxr_put(P.track, v, n);
        return;
    }
    if (dep == NONE)
        return;
    int k = add_kind(e);
    if (k == ADD_DEST) {                                /* the first route: DEST and DEP (no mark left from before) */
        if (P.lfo < 3) {
            mxr_mute_first(P.track, (u32)P.lfo, 0);
            mxr_first_set(P.track, (u32)P.lfo, dep);
        } else
            param_set(DEP_REC[P.lfo], dep);
        param_set(DEST_REC[P.lfo], slot_of(e) << 8);
    } else if (k == ADD_REC) {
        v[n] = (u8)P.lfo;
        v[n + 1] = (u8)slot_of(e);
        v[n + 2] = (u8)(dep >> 8);
        v[n + 3] = (u8)dep;
        mxr_put(P.track, v, n + 4);
    }
}

/* -> 1 changed, 0 nothing, -1 this route cannot be muted (into an LFO's controls, LFO4's) */
static int set_mute(u32 e, int on)
{
    u8 v[MXR_BUF];
    int where, at, muted, n;
    route_of(e, &where, &at, &muted);
    if (!where)
        return 0;
    if (where == 1)
        return P.lfo == 3 ? -1 : mxr_mute_first(P.track, (u32)P.lfo, on);
    if (muted == !!on)
        return 0;
    n = mxr_get(P.track, v);
    v[at] = (u8)(on ? v[at] | MXR_MUTED : v[at] & ~MXR_MUTED);
    mxr_put(P.track, v, n);
    return 1;
}

static int del_route(u32 e)
{
    u8 v[MXR_BUF];
    int where, at, muted;
    route_of(e, &where, &at, &muted);
    if (where == 1)
        del_first();
    else if (where == 2)
        mxr_put(P.track, v, mxr_drop(v, mxr_get(P.track, v), at));
    return where != 0;
}

/* FUNC + NO: every route of this LFO, the first and the record's, muted ones too -> how many */
static u32 del_all(void)
{
    u8 v[MXR_BUF];
    u32 c = dest_slot() != 0u;
    if (c) {
        param_set(DEST_REC[P.lfo], 0);
        if (P.lfo < 3)
            mxr_first_set(P.track, (u32)P.lfo, NONE);   /* (2026-11-19) DEP, the attenuverter, kept */
        else
            param_set(DEP_REC[P.lfo], (u32)RECORD(DEP_REC[P.lfo])[4]);
    }
    if (P.lfo != 3) {
        int n = mxr_get(P.track, v), m = 0;
        for (int i = 0; i + 4 <= n; i += 4) {
            int mine = mxr_is_mark(v + i) ? (v[i] & 3u) == (u32)P.lfo : (v[i] & ~MXR_MUTED) == (u32)P.lfo;
            c += mine && !mxr_is_mark(v + i);
            if (!mine)
                for (int b = 0; b < 4; b++)
                    v[m++] = v[i + b];
        }
        if (m != n)
            mxr_put(P.track, v, m);
    }
    return c;
}

/* after an edit: an LFO whose DEST is free takes its next route of the record there (routes.c) */
static void settle(void)
{
    if (P.lfo < 3)
        mxr_settle(P.track, (u32)P.lfo);
}

static void changed(void)                               /* the next frame draws every row */
{
    P.full = 1;
    if ((int)(P.next_draw - (P.frame_at + SOON)) > 0)  /* at most one every SOON frames: never queued */
        P.next_draw = P.frame_at + SOON;
}

static void say(const char *w)
{
    P.say = w;
    P.say_at = FRAMES_NOW + SAY_TIME;
    changed();
}

/* --- the list: built once at the open ---------------------------------------------------------- */
static u32 rank_of(u32 e)
{
    u32 page = CATEGORY(e);
    for (u32 i = 0; i < NRANKS; i++)
        if ((u32)RANKS[i] == page)
            return i;
    return 0;
}

static int own_control(u32 e)                           /* this LFO's own records, any DEST (never a destination) */
{
    u32 s = slot_of(e);
    if (s >= 1u && s <= 24u && (s - 1u) / 8u == (u32)P.lfo)
        return 1;
    if (P.lfo == 3 && e >= 321u)
        return 1;
    for (u32 l = 0; l < 4u; l++)
        if (e == DEST_REC[l])
            return 1;
    return 0;
}

static u32 build(u16 *ent, u32 *key)                    /* -> entries, stock's order */
{
    u32 owner = UI_OWNER(), obj = owner ? PARAM_SET(owner, DEST_REC[0], P.track) : 0u, n = 0, end = WALK_END;
    if (!obj)
        return 0;
    u32 (*lookup)(u32, u32) = (u32 (*)(u32, u32))(*(u32 **)obj)[20];
    for (u32 s = 0; s < end && n < MAXE; s++) {
        u32 e = lookup(obj, s), want = P.lfo == ENV2 ? 0x0200u : WANT[P.lfo];   /* ENV2: MOD SETUP's list, a sound
                                                         * parameter of the voice row only (25..100) */
        if (!e || e == NONE_REC || (~mod_lfo_mask(e, want) & want) || own_control(e)
            || (P.lfo == ENV2 && (slot_of(e) < 25u || slot_of(e) > 100u)))
            continue;
        u32 k = rank_of(e) << 16 | e, i = n;
        while (i > 0 && key[i - 1] > k)                 /* insertion: by rank, then by id (stock's comparator) */
            i--;
        if (i > 0 && key[i - 1] == k)                   /* an entry two slots lead to: listed once */
            continue;
        for (u32 j = n++; j > i; j--) {
            key[j] = key[j - 1];
            ent[j] = ent[j - 1];
        }
        key[i] = k;
        ent[i] = (u16)e;
    }
    ldp_built++;
    return n;
}

static void make_rows(void)                             /* this LFO's routes first, then the rest; each in order */
{
    u16 ent[MAXE];
    u32 key[MAXE], n = build(ent, key), r = 0;
    for (u32 pass = 0; pass < 2u; pass++)
        for (u32 i = 0; i < n; i++) {
            int where, at, muted;
            route_of(ent[i], &where, &at, &muted);
            if ((where != 0) == (pass == 0u))
                ldp_rows[r++] = ent[i];
            if (pass == 0u && where)
                P.nroutes++;
        }
    P.n = r;
}

/* stock's value check of a record (0x40039904, the parameter set's method: every LFO page draw checks each knob's
 * value with it), taken over at its entry (dnfw.waverider.coldfire): for an LFO's DEST stock builds the whole list
 * (0x4003951e: a walk of 101 / 109 slots, then the sort, ~215k instructions) only to look the value's entry up in it.
 * The entry E of the value's slot S is in that list exactly when E is not 0 and passes the list's mask (the builder
 * pushes lookup(s) for each slot whose entry passes; the mask reads the entry alone): so, for S inside the walk, the
 * same answer from one lookup and one mask. Outside it (never met: S is a byte of the cell), and for every other
 * record, stock's own way: the walk for membership (no sort), and 0x40036bac */
#define REC_FLAGS ((u32 (*)(u32))0x400DC472u)           /* a record's flags (+24): bit 18/17/16 LFO1/2/3 DEST */
#define CHECK_OTHER ((u32 (*)(u32, u32, s32))0x40036BACu)
u32 ldp_checks D_ = 0;                                  /* (the checks) DEST values checked here */

u32 ldp_valid(u32 obj, u32 rid, s32 value)
{
    u32 f = REC_FLAGS(rid);
    u32 want = f & 1u << 18 ? 0x1E00u : f & 1u << 17 ? 0x0E00u : f & 1u << 16 ? 0x0600u : 0u;
    if (!want)
        return CHECK_OTHER(obj, rid, value) & 0xFFu;
    u32 (*lookup)(u32, s32) = (u32 (*)(u32, s32))(*(u32 **)obj)[20];
    s32 s = value >> 8, end = (s32)WALK_END;
    u32 e = lookup(obj, s);
    ldp_checks++;
    if (s >= 0 && s < end)
        return e && !(~mod_lfo_mask(e, want) & want);
    for (s32 k = 0; e && k < end; k++)                  /* stock's membership, without the list */
        if (lookup(obj, k) == e && !(~mod_lfo_mask(e, want) & want))
            return 1;
    return 0;
}

/* --- open, close, the keys -------------------------------------------------------------------- */
static int refused(u32 t, int l)
{
    /* (2026-11-18, the User: "i just want ours": a trig held no longer leaves D to stock's list, which set a DEST
     * p-lock there; the popup opens and edits the sound's routes) */
    return smp_question_up() || rec_overlay || (amp_sub && l != ENV2) || ins_visible() || mxp_visible() || midi_track(t);
}

extern int env2_visible(void);
static int env2_up(void)                                /* ENV2's page: G is its DEST (env2_page.c) */
{
    return env2_visible();
}

static int open(void)
{
    int l = env2_up() ? ENV2 : lfo_of_cell();
    u32 t = UI_TRACK & 15u;
    if (l < 0)
        return 0;
    if (refused(t, l)) {
        ldp_refusals++;
        return 0;
    }
    P.lfo = l;
    P.knob = l == ENV2 ? KNOB_G : KNOB_D;
    P.track = t;
    P.nroutes = 0;
    make_rows();
    P.lit = 0;
    P.say = 0;
    P.said = 0;
    P.no_down = 0;
    P.turned = 1;                                       /* the opening push's release closes nothing */
    P.last = FRAMES_NOW;
    P.back = 0;                                         /* the first frame is a full one */
    P.up = 1;
    ldp_opens++;
    smp_overlay_dirty = 1;
    return 1;
}

static void close(void)
{
    P.no_down = 0;
    if (!P.up)
        return;
    P.up = 0;
    P.back = 0;
    smp_overlay_dirty = 1;
}

int ldp_visible(void)
{
    return P.up;
}

static void move_lit(int d)
{
    int r = (int)P.lit + d;
    P.lit = (u32)(r < 0 ? 0 : r >= (int)P.n ? (int)P.n - 1 : r);
    changed();
}

/* (2026-11-19, the User) FUNC + UP / DOWN: the lit row by sections, as the routes popup's (routes_pop.c jump_lit). A
 * section: this LFO's routes on top (the places 0 .. nroutes - 1, as made at the open), then each of stock's DEST
 * categories in the list's order (CATEGORY: the page id stock's list sorts by, and its push-and-turn jumps by). DOWN:
 * the next section's first place (on the last: stays); UP: this section's first place, or the previous section's when
 * already on it (place 0: stays) */
static int starts(u32 pl)                               /* place PL begins a section */
{
    return pl == 0u || pl == P.nroutes || (pl > P.nroutes && CATEGORY(ldp_rows[pl - 1u]) != CATEGORY(ldp_rows[pl]));
}

static void jump_lit(u32 code)
{
    u32 l = P.lit;
    if (!P.n)
        return;
    if (code == K_ARROW_DN) {
        u32 p = l + 1u;
        while (p < P.n && !starts(p))
            p++;
        if (p < P.n)
            P.lit = p;
    } else {
        if (l > 0u && starts(l))
            l--;                                        /* on its section's first place: into the previous one */
        while (l > 0u && !starts(l))
            l--;
        P.lit = l;
    }
    changed();
}

static void arrow(u32 code)                             /* UP or DOWN while up: FUNC held, by sections */
{
    if (smp_func_held)
        jump_lit(code);
    else
        move_lit(code == K_ARROW_DN ? 1 : -1);
}

static void turn(int d)
{
    int where, at, muted;
    u32 e = ldp_rows[P.lit];
    int dep = (int)route_of(e, &where, &at, &muted);
    int k = where ? 0 : add_kind(e);
    if (k >= ADD_CTRL) {
        say(refusal(k));
        return;
    }
    s32 old = dep;                                      /* (2026-11-19, the User: knob precision, csrc/knobs) a slow */
    dep = kn_whole(old, kn_units(d), DEP_TOP);          /* turn 1 unit every 3 counts, whole units, the notch at 0 */
    dep = kn_value(KN_KEY_POP | 0x8000u | (u32)P.lfo << 9 | e, old, dep, NONE);
    if (dep == old)
        return;
    set_depth(e, (u32)dep);
    settle();
    changed();
}

static void yes_key(void)
{
    int where, at, muted, k;
    u32 e = ldp_rows[P.lit];
    route_of(e, &where, &at, &muted);
    if (where) {
        if (set_mute(e, 0) > 0)
            say("UNMUTED");
        return;
    }
    k = add_kind(e);
    if (k >= ADD_CTRL) {
        say(refusal(k));
        return;
    }
    set_depth(e, ADD_DEP);
    settle();
    changed();                                          /* no word (the User, 2026-11-18): the row shows the route */
}

static void no_short(void)
{
    int r = set_mute(ldp_rows[P.lit], 1);
    if (r > 0)
        say("MUTED");
    else if (r < 0)
        say("CAN'T MUTE");
}

static void clear_all(void)
{
    ldp_erased += del_all();
    say("ALL CLEARED");
}

/* rec.c smp_ui_pop, before the routes popup: -> 1 when the item is ours (dropped)
 *
 * A held key's repeats (2026-11-18; routes_pop.c mxp_pop has the whole story): stock's key task sends a held key again
 * 24 panel ticks after its press, then every 8, with bit 3 beside the press's bit 0. v1 took each for a press: a held
 * NO's 0.6 s began again every 8 ticks (the release muted), D held at the open past its first repeat closed the popup
 * on its release (the opening push's "no close" mark cleared), as did a push-and-turn held as long. UP and DOWN step
 * the lit row with their repeats; every other repeat of a key whose press was ours is dropped. */
static int d_ours D_ = 0;                               /* D's push that is down was ours (it opened the popup) */
/* (2026-11-21) no jump table: its data in .text read as code by the build's scale-8 check (cbuild, docs/HANDOFF-second-firmware.md) */
__attribute__((optimize("no-jump-tables")))
int ldp_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int repeat = (flags & F_REPEAT) && !(flags & F_RELEASE);
    int press = (flags & F_PRESS) && !(flags & F_RELEASE) && !repeat, release = (flags & F_RELEASE) != 0;
    u32 kn = P.up ? P.knob : env2_up() ? KNOB_G : KNOB_D;   /* (2026-11-19) D on an LFO page, G on ENV2's */
    int d_held = (smp_held_hi >> (K_PUSH0 - 32 + kn)) & 1u;

    if (it[0] == IT_KEY && code == K_PUSH0 + kn && !press)
        d_ours = repeat && d_ours;                      /* (let go: no longer) */
    if (!P.up) {                                        /* D on an LFO page: ours, never stock's list (the User,
                                                         * 2026-11-18: "the destination for mod page is still the
                                                         * elektron one ... i just want ours"; emu_destpop.py paths) */
        if (it[0] == IT_KNOB && code == kn + 1u)    /* turned (a fast turn, FUNC or a trig held, D pushed too):
                                                         * stock opened its list at the first twist; ours opens, the
                                                         * twist only opens it (no depth moves), as stock's lists */
            return open();
        if (it[0] == IT_KEY && code == K_PUSH0 + kn && press && !smp_func_held)
            return d_ours = open();
        return it[0] == IT_KEY && code == K_PUSH0 + kn && repeat && d_ours;   /* (closed while D is held) */
    }
    P.last = FRAMES_NOW;
    if (it[0] == IT_KEY && code == K_PUSH0 + kn) {  /* D pushed and let go with no turn: closed, kept */
        if (press) {
            P.turned = 0;
            d_ours = 1;
        } else if (release && !P.turned)
            close();
        return 1;                                       /* (a repeat: nothing) */
    }
    if (it[0] == IT_KNOB && code >= 1u && code <= 8u) {
        int d = (s8)it[8];
        ldp_turns++;
        ldp_detents += d;
        if (code != kn + 1u) {                      /* another knob: closed, kept; the turn is stock's */
            close();
            return 0;
        }
        if (d_held) {
            P.turned = 1;
            move_lit(d > 0 ? 1 : d < 0 ? -1 : 0);
        } else if (P.n)
            turn(d);
        return 1;
    }
    if (it[0] == IT_KEY && repeat) {                    /* a held key: UP and DOWN step on (FUNC held: by
                                                         * sections), NO and YES nothing */
        if (code == K_ARROW_UP || code == K_ARROW_DN)
            arrow(code);
        return code == K_ARROW_UP || code == K_ARROW_DN || code == K_YES || code == K_NO;
    }
    if (it[0] == IT_KEY && press) {
        ldp_keys++;
        if (code == K_ARROW_UP || code == K_ARROW_DN) {
            arrow(code);
            return 1;
        }
        if (code == K_NO && smp_func_held) {
            clear_all();
            return 1;
        }
        if (code == K_NO) {
            P.no_at = FRAMES_NOW;
            P.no_down = 1;
            P.no_long = 0;
            return 1;
        }
        if (code == K_YES) {
            if (P.n)
                yes_key();
            return 1;
        }
        if (code == K_FUNC)
            return 0;
        close();
        return 0;
    }
    if (it[0] == IT_KEY && release && code == K_NO && P.no_down) {
        P.no_down = 0;
        if (!P.no_long && P.n)
            no_short();
        return 1;
    }
    return code == K_ARROW_UP || code == K_ARROW_DN || code == K_YES || code == K_NO;
}

/* --- drawing (the canvas counts y up from the bottom) ------------------------------------------ */
/* the routes popup's drawing helpers (routes_pop.c): inversion a column word at a time, a dotted (muted) line, the panel
 * UART's backlog */
void mxp_invert(void *c, int x0, int y0, int x1, int y1);
void mxp_dotted(void *c, int x0, int y0, int x1, int y1);
u32 mxp_uart_backlog(void);
#define invert mxp_invert
#define dotted mxp_dotted

#define BAR_X0 58
#define BAR_X1 98
static void bar(void *c, int y, s32 depth, s32 now, int muted)  /* routes_pop.c's bar, an LFO's (both ways) */
{
    int z = (BAR_X0 + BAR_X1) / 2, half = (BAR_X1 - BAR_X0) / 2;
    int d = (int)((depth * half) / 0x7FFE), o = (int)((now * half) / 0x7FFE), m = d < 0 ? -d : d;
    if (muted) {
        if (m) {
            dotted(c, z - m, y, z + m, y);
            dotted(c, z - m, y + 4, z + m, y + 4);
            dotted(c, z - m, y, z - m, y + 4);
            dotted(c, z + m, y, z + m, y + 4);
        }
        dotted(c, z + d, y - 1, z + d, y + 5);
        return;
    }
    if (m) {
        cv_fill(c, z - m, y, z + m, y, 1);
        cv_fill(c, z - m, y + 4, z + m, y + 4, 1);
        cv_fill(c, z - m, y, z - m, y + 4, 1);
        cv_fill(c, z + m, y, z + m, y + 4, 1);
    }
    cv_fill(c, z + d, y - 1, z + d, y + 5, 1);
    if (o)
        cv_fill(c, o < 0 ? z + o : z, y + 1, o < 0 ? z : z + o, y + 3, 1);
}

static const char *name(u32 e, int field)               /* 10 long, 11 page, 12 short */
{
    const char *s = (const char *)RECORD(e)[field];
    return s ? s : "";
}

static u32 top_row(void)
{
    return P.lit < SHOWN ? 0u : P.lit - (SHOWN - 1u);
}

/* a route row's bar: its live part from the voice the track last played (LFO1-3; LFO4's state is lfo4's) */
static void route_bar(void *c, u32 e, int y)
{
    int where, at, muted;
    s32 d = (s32)route_of(e, &where, &at, &muted) - NONE, now = 0, v = sl_lastv[P.track];
    if (!muted && P.lfo != 3 && v >= 0 && v < 16 && OWNER[v] == P.track)
        now = (d * (mx_route_level((u32)v, (u32)P.lfo) >> 16)) >> 15;
    bar(c, y + 1, d, now, muted);
}

static void draw_row(void *c, u32 pl, u32 top)
{
    u32 e = ldp_rows[pl], k = pl - top;
    int y = 46 - 9 * (int)k, where, at, muted;
    u32 dep = route_of(e, &where, &at, &muted);
    u32 page = CATEGORY(e);
    int first = pl == top || pl == P.nroutes || pl < P.nroutes || where || CATEGORY(ldp_rows[pl - 1]) != page;
    if (first)
        TEXT(c, FONT, 1, y, 0, "%.4s", name(e, 11));
    if (pl < P.nroutes || where) {                      /* a route row (one made below the routes while up too) */
        TEXT(c, FONT, 19, y, 0, "%.5s", name(e, 12));
        if (where) {
            TEXT(c, FONT, 42, y, 0, "%+d", ((s32)dep - NONE) / 0x100);
            route_bar(c, e, y);
            ldp_routes_drawn |= 1u << k;
        }
        if (pl == P.lit)
            TEXT(c, FONT, 104, y, 0, "%s", !where ? "" : muted ? "MUTE" : where == 1 ? "DEST" : "REC");
    } else {
        TEXT(c, FONT, 19, y, 0, "%.27s", name(e, 10));
    }
    if (pl == P.lit)
        invert(c, 0, y - 1, 127, y + 7);
}

static void draw_all(void *c)
{
    u32 top = top_row(), used = pool_used();
    cv_fill(c, 0, 0, 127, 63, 0);
    if (P.lfo == ENV2)
        TEXT(c, FONT, 2, 57, 0, "ENV2 DEST");
    else
        TEXT(c, FONT, 2, 57, 0, "LFO%d DEST", P.lfo + 1);
    TEXT(c, FONT, used >= 10u ? 107 : 111, 57, 0, "%d/%d", (int)used, P.lfo == 3 ? 1 : P.lfo == ENV2 ? ENV_CAP : MXR_POOL);
    for (int x = 0; x <= 127; x += 2) {
        cv_fill(c, x, 55, x, 55, 1);
        cv_fill(c, x, 8, x, 8, 1);
    }
    ldp_routes_drawn = 0;
    for (u32 pl = top; pl < top + SHOWN && pl < P.n; pl++)
        draw_row(c, pl, top);
    if (P.n) {
        u32 e = ldp_rows[P.lit];
        int where, at, muted, k;
        route_of(e, &where, &at, &muted);
        k = where ? 0 : add_kind(e);
        TEXT(c, FONT, 1, 1, 0, "%.31s", where ? name(e, 10) : k == ADD_DEST ? "ADD AS DEST" : k == ADD_REC
             ? "ADD TO MATRIX" : refusal(k));
    }
    P.said = 0;
    if (P.say && (int)(P.say_at - FRAMES_NOW) > 0) {
        cv_fill(c, 28, 24, 99, 38, 0);
        TEXT(c, FONT, 34, 28, 0, "%s", P.say);
        invert(c, 28, 24, 99, 38);
        P.said = 1;
    }
}

static void draw_bars(void *c)                          /* the route rows' bars alone, over the last frame */
{
    u32 top = top_row();
    for (u32 pl = top; pl < top + SHOWN && pl < P.n; pl++) {
        if (!(ldp_routes_drawn >> (pl - top) & 1u))     /* the rows the last full frame drew as routes */
            continue;
        int y = 46 - 9 * (int)(pl - top);
        cv_fill(c, BAR_X0, y, BAR_X1, y + 6, 0);
        route_bar(c, ldp_rows[pl], y);
        if (pl == P.lit)
            invert(c, BAR_X0, y, BAR_X1, y + 6);
    }
}

static int bars_move(void)                              /* a visible route moves (the track's voice playing) */
{
    s32 v = sl_lastv[P.track];
    return P.lfo != 3 && ldp_routes_drawn && v >= 0 && v < 16 && OWNER[v] == P.track;
}

static u8 *drew_buf D_ = 0;

void ldp_draw(void *c)                                  /* page.c wr_screen: a full draw, over everything of ours */
{
    if (!P.up)
        return;
    draw_all(c);
    P.full = 0;
    drew_buf = CANVAS_BUF(c);
    P.frame_at = FRAMES_NOW;
    P.next_draw = FRAMES_NOW + BARS;
    ldp_full++;
}

void ldp_end(void *c, int clean)                        /* page.c wr_screen, last: our frame is the glass's next */
{
    P.back = clean && drew_buf && drew_buf == CANVAS_BUF(c) ? drew_buf : 0;
    drew_buf = 0;
}

static void frame_alone(void *screen)
{
    if (mxp_uart_backlog() >= UART_IDLE) {                  /* never queued behind the panel UART */
        P.next_draw = FRAMES_NOW + RETRY;
        ldp_dropped++;
        return;
    }
    if (!P.back || FB_BACK != P.back || (IS_DIRTY(screen) & 0xFFu)) {
        SET_DIRTY(screen);                              /* the glass holds another frame: a full one */
        P.next_draw = FRAMES_NOW + SOON;
        return;
    }
    u8 *front = FB_FRONT;
    const u32 *src = (const u32 *)P.back;
    volatile u32 *dst = (volatile u32 *)front;
    for (int k = 0; k < 256; k++)
        dst[k] = src[k];
    u32 canvas[8];
    CANVAS_NEW(canvas, 128, 64, front, CANVAS_AID);
    if (P.full)
        draw_all(canvas);
    else
        draw_bars(canvas);
    P.full = 0;
    LOOP_BUF = (u8 *)PANEL_DIFF();
    P.back = FB_BACK;
    ldp_alone++;
    P.frame_at = FRAMES_NOW;
    P.next_draw = FRAMES_NOW + BARS;
}

/* page.c wr_poll: the long NO, closing on its own, the frames */
void ldp_poll(void *screen)
{
    if (!P.up)
        return;
    if (P.no_down && !P.no_long && FRAMES_NOW - P.no_at >= LONG) {
        P.no_long = 1;
        P.last = FRAMES_NOW;
        if (P.n && del_route(ldp_rows[P.lit])) {
            settle();
            ldp_erased++;
            say("DELETED");
        }
    }
    if ((UI_TRACK & 15u) != P.track || smp_question_up() || FRAMES_NOW - P.last >= IDLE) {
        close();
        return;
    }
    if (P.said && (int)(P.say_at - FRAMES_NOW) <= 0)
        changed();                                      /* the word goes */
    if ((int)(FRAMES_NOW - P.next_draw) < 0 || (!P.full && !bars_move()))
        return;
    frame_alone(screen);
}
