/* The routes popup: "the routes into this knob" (the User, 2026-11-11; layout A, the moving bar; docs/matrix.md,
 * scratch/modulation/dest-knob.md §1, §7). OS 1.12.
 *
 * (2026-11-19, the User) A PLAIN push opens it, on the push's RELEASE, only when nothing else happened while the knob
 * was held: no key pressed (NO, YES, a trig, any other), no encoder turned, and no key already held at the press (LIVE
 * REC's NO + push, a trig held + push). Stock has every item of the push as before: its peek (the value in the label)
 * shows on the press, push + NO resets on NO's release, push + turn takes big steps, a trig held + push clears the
 * lock; any of those cancels the popup. FUNC + push is stock's everywhere again (the peek; a MIDI track's on / off of
 * CHAN, BANK, PROG, CC VAL; an LFO DEST's list). FUNC + a push still held at 0.6 s resets the parameter to its record's
 * default (stock's own setValue), as before, but never an LFO's DEST (stock's FUNC + push opened its list there).
 *
 * The popup covers the screen. A slim header with the parameter's name (and PER NOTE at its right on a control read
 * only at the note's start, 2026-11-20: TB-303 ACC SLID, DRONE HOLD, ...; pages.py MNM_PER_NOTE); a row a source: LFO1-3, ENV1, ENV2, then MOD
 * SETUP's VEL MW PB AT BC KEY, five rows shown at a time (the list scrolls with the lit row). A row with no route is
 * an empty line (its icon and name); a route shows its depth and the moving bar: the outline is the reach (0 to the
 * depth, and to minus it for an LFO, which swings both ways), a tall tick the depth, the solid bar the offset the
 * source applies now, on the voice the track last played. The lit row's count: the LFOs' shared pool ("13/16", FULL
 * when it is full and this LFO has no route here), an envelope's own four ("2/4", FULL). At the bottom, LOCKS: this
 * parameter's p-locks on the track's pattern, the 16 steps of the page playing (a filled cell a locked step, the
 * playing step underlined), then a tick a page (filled when the page holds a lock, the page playing underlined); the
 * dest-knob study §6.
 *
 * MOD SETUP's rows (2026-11-21, the User: "like other rows!"; csrc/matrix/setup.c): stock's own entries, edited with the
 * same keys as our rows, each edit through stock's own MOD SETUP object (setDepth, setEntry: stock's page, undo,
 * Overbridge and saving see it). A row shows its source's entry into this slot (two of one source are merged, depths
 * summed, when the popup touches them), its depth in stock's own MOD SETUP number (the depth word / 256, two decimals
 * cut toward 0: "1.90", "-2.05", measured on stock's pages), the moving bar as stock's kernel (0x400db340) applies it,
 * and its name says whose value it reads: VEL/V and KEY/V the voice's, MW/T PB/T AT/T BC/T the track's. The lit row's
 * count is its source's own four ("2/4", FULL). A turn from 0 adds an entry in the source's first free place, refused
 * with NOT IN SETUP where stock's MOD SETUP list does not offer the parameter (ENV2's and the inserts' knobs never);
 * to 0 the entry goes. A muted entry stays in the sound (stock firmware plays it) and lands with depth 0 in the voices'
 * copies (setup.c mxs_copy).
 *
 * The rows with no route here (2026-11-21, the User) show their source's level now as a dimmed line (every other
 * pixel), on the voice the track last played: what an LFO or envelope is doing before it is routed. It moves at half
 * the bars' rate (7.5 times a second), only its pixels sent; it never moves the knob.
 *
 * The rows' order (the User, 2026-11-17: "the used modulation are on top of the list (ordered the same way)"; MOD
 * SETUP's rows sorted too): the rows with a route into this slot first, in the usual order (LFO1-3, ENV1, ENV2, VEL MW
 * PB AT BC KEY), then the others in the same order. A route at depth 0 counts as unused. The order is made when the
 * popup opens and kept until it closes, so no row moves under the lit bar while a depth is turned (to or from 0), a
 * route muted or deleted; it is made anew at the next open. A muted route counts as unused. A row is a source through
 * the order table (mxp_order), never by its place on screen.
 *
 * The keys while up (the User, 2026-11-17): YES unmutes the lit row's route (on an empty row it adds one at +32, the
 * User 2026-11-18), NO (a tap) mutes it, NO held 0.6 s deletes
 * it (an empty row: nothing); FUNC + NO deletes every route of ours into this parameter. Deleted: a route of the
 * record goes; stock's route 1 gets its DEST 0 and DEP's default back, and its DEP p-locks on this track are freed
 * (the pool's record made as stock's free ones are). A muted route keeps its depth (shown, the bar dotted, the lit row
 * says MUTE) and applies nothing: MUTED in the record's source byte, laid with d1 0 by matrix.c (the same cost);
 * stock's route 1 muted moves into the record. MOD SETUP's rows: the same keys (setup.c). A short word on screen says what was
 * done. There is no undo.
 *
 * FUNC + UP / FUNC + DOWN (the User, 2026-11-19) jump the lit row by sections: a section is a run of places whose rows
 * are of one kind (LFO1-3; ENV1, ENV2; MOD SETUP's six) in the order shown (mxp_order), so a sorted popup can hold a
 * kind twice (LFO2 | ENV1 | PB | LFO1 LFO3 | ENV2 | VEL ...). FUNC + DOWN: the next run's first place; FUNC + UP: this
 * run's first place, or the previous run's when already on it. At the ends it stays (no wrap). A held FUNC + arrow
 * jumps on with the key's repeats, as a held arrow steps on. Every UP / DOWN item is ours while up; FUNC's own items go
 * on to stock as before.
 *
 * Turning the knob sets the lit row's depth, live; push-and-turn (or UP / DOWN) moves the lit row. A row turned from 0
 * makes the route: an LFO's stock route 1 first when it is free (DEST, DEP: stock's parameters, so a stock unit plays
 * it), else a route of the record. A route turned to 0 goes at once (the row empty, the counts down; the unit,
 * 2026-11-17). Closed, everything kept: the same knob pushed, any key that leaves (it then does what it does), another
 * knob turned (it then turns that knob), a track change, 6 s untouched. A FUNC + push begun while up is ignored (no
 * close, no reset): FUNC + long push resets a parameter outside the popup only.
 *
 * Refused (the push stays stock's alone): a trig or TRK held, a stock question up, a page, list or popup of ours up, a
 * MIDI track, a parameter that is no sound parameter of the voice row (a record of a sound page, 0..15, at slot
 * 25..100; 2026-11-19: TRIG 1/2's FILL is a trig record, page 29, slot 25, and opened a popup titled FILL).
 */
#include "../wishes/wish.h"
#include "../knobs/knob.h"
#include "routes.h"
#include "setup.h"

typedef signed char s8;
typedef short s16;

#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)       /* 1,500 a second */
#define FONT       0x44508ED8u                          /* the grid's label font (popup.c's) */
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))   /* +4 slot, +16 default, +0x30 its short name */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define UI_OWNER   ((u32 (*)(void))0x4018AC5Au)
#define PARAM_SET  ((u32 (*)(u32, u32, u32))0x40041A40u)
#define SET_VALUE  ((u32 (*)(u32, u32, u32, u32, u32, u32, u32))0x40037326u)
#define OUT        ((volatile u16 *)0x800068E4u)
#define OWNER      ((volatile u32 *)0x80005308u)
#define MIDI_TYPE  4
#define APP        ((u32 (*)(void))0x4018AC5Au)
#define TRACK_CTX  ((u32 (*)(u32))0x4003EFDEu)
#define PATTERN_LEN ((u32 (*)(u32))0x4004F896u)
#define TRACK_CUR  ((volatile u8 *)0x42C5B984u)         /* each track's playing step (csrc/slides) */
#define LOCK_RECS  80                                   /* the pattern's lock pool: {u8 slot, u8 track, u16[128]} */
#define LOCK_REC   258

#define IT_KEY     0
#define IT_KNOB    1
#define F_PRESS    0x01
#define F_REPEAT   0x08                                 /* a held key's repeat (below) */
#define F_RELEASE  0x10
#define K_YES      10
#define K_NO       12
#define K_ARROW_UP 11
#define K_ARROW_DN 14
#define K_FUNC     17
#define K_PUSH0    41                                   /* encoder A's push .. H's 48 */

#define TAP        600u                                 /* 0.4 s: a push let go before this opens the popup */
#define LONG       900u                                 /* 0.6 s: still held, the parameter is reset */
#define IDLE       9000u                                /* 6 s untouched: closed */
#define REDRAW     100u                                 /* the moving layer looked at 15 times a second (v1: a full
                                                         * redraw 25 times a second; the scope's rate, 2026-11-18) */
#define SAY_TIME   1500u                                /* 1 s: DELETED, ALL CLEARED, NOT IN SETUP */
#define OWN_ROWS   5                                    /* LFO1-3, ENV1, ENV2: the record's (and DEST / DEP) */
#define ROWS       11                                   /* then MOD SETUP's six: stock's entries (setup.c) */
#define SHOWN      5                                    /* the rows on screen */
#define LFO_CAP    16
#define ENV_CAP    4
#define NONE       0x4000
#define MUTED      0x80                                 /* a record route's source byte: muted (matrix.c MX_MUTED) */
#define DEP_TOP    0x7FFE
#define YES_DEPTH  32                                   /* YES on an empty row: its new route's depth */
#define E2_DEST    0xE0u                                /* (2026-11-18) ENV2's ATK..REL as destinations (matrix.c
                                                         * MX_E2_DEST): the popup on ENV2's page, its slot 0xE0 + the knob;
                                                         * (2026-11-20) MODE 0xE5, RSET 0xE6, H 0xE7 too */
#define E2_N       8u
#define E2_ROW     4u                                   /* the ENV2 row: never into ENV2's own knobs */
#define AMP_ENV2_PAGE 1                                 /* csrc/waverider/amp_pages.h AMP_ENV2 */

/* our C (rec.c, matrix.c, popup.c, slides) */
extern int smp_func_held;
extern u32 smp_held_lo, smp_held_hi;
extern int smp_question_up(void);
extern int smp_overlay_dirty;
extern s8 sl_lastv[16];
extern int rec_overlay;
extern int amp_sub;
extern int ins_visible(void);
extern int ins_knob_reset(int k);                      /* csrc/inserts/ins.c: an INSERT page's place to its default */
extern u32 ins_route_dest(u32 k, const char **name);    /* ... an INSERT page's knob K: its destination (INS_DEST..), 0 none */
extern const u8 *sl_ins_record(const u8 *table, u32 t, u32 k);   /* csrc/slides: the inserts' kind K record of track T */
#define INS_DEST   0xC0u                                /* (2026-11-20) the inserts' knobs (matrix.c MX_INS_DEST): 0xC0 + 7 j
                                                         * + i, slot j's K1..K6 and MIX */
#define INS_N      14u
int mx_route_level(u32 v, u32 src);                    /* matrix.c: a source's value on voice V, 1.31 */

static const char *const NAME[ROWS] = {"LFO1", "LFO2", "LFO3", "ENV1", "ENV2", "VEL", "MW", "PB", "AT", "BC", "KEY"};
static const u8 DEST_REC[3] = {78, 88, 98};             /* LFO1-3 DEST and DEP (stock's records) */
static const u8 DEP_REC[3] = {83, 93, 103};

static struct {
    int up;                                             /* the popup is up */
    u32 knob;                                           /* 0 A .. 7 H */
    u32 rid, slot, track;                               /* its parameter, the row slot it is, the track */
    u32 last;                                           /* the last touch's frame */
    u32 push_at, push_k;                                /* FUNC + push (stock's): when, which encoder (+1; 0 none), for
                                                         * the long push's reset */
    u32 plain_k;                                        /* a plain push held that may open the popup at its release
                                                         * (+1; 0 none, or cancelled: mxp_seen) */
    int plain_d;                                        /* its own knob's counts held back while held (KN_PUSH_WOBBLE) */
    u32 plain_rid;                                      /* its place's record at the press (open at the release) */
    int reset_done;
    u32 ign_k;                                          /* a FUNC + push begun while up (+1): its release ignored */
    u32 no_at;                                          /* NO pressed while up: when (a long NO deletes) */
    int no_down, no_long;                               /* NO held; its long action done */
    int turned;                                         /* the lit knob turned while pushed (push-and-turn) */
    u32 next_draw;
    const char *say;                                    /* the word on screen, until SAY_AT */
    u32 say_at;
    const char *iname;                                  /* (2026-11-20) an insert's knob: its label (P.rid 0) */
} P D_;

/* the rows' order while up, made at the open: place -> source row (0 LFO1 .. 4 ENV2, 5 VEL .. 10 KEY); the checks
 * read it */
u8 mxp_order[ROWS] D_ = {0};
#define SRC(place) ((u32)mxp_order[place])
u32 mxp_lit D_ = 0;                                     /* the lit row: a place in mxp_order (the checks read it) */

/* the checks' counters: FUNC + pushes seen, popups opened, opens refused and why (1 no parameter, 2 refused here,
 * 3 not a sound parameter of the row) */
u32 mxp_pushes D_ = 0, mxp_opens D_ = 0, mxp_refusals D_ = 0, mxp_why D_ = 0, mxp_rid D_ = 0;
u32 mxp_turns D_ = 0, mxp_keys D_ = 0;               /* knob turns and key presses taken while up */
u32 mxp_erased D_ = 0;                                  /* routes a FUNC + long push deleted (the checks) */
u32 mxp_plains D_ = 0, mxp_cancels D_ = 0;              /* (2026-11-19) plain pushes that could open, and those cancelled
                                                         * by a key, a turn or another item while held (the checks) */
u32 mxp_wobbles D_ = 0;                                 /* (2026-11-20) knob items of a plain push's own knob held back
                                                         * (under KN_PUSH_WOBBLE counts: the checks) */
int mxp_detents D_ = 0;                                 /* their detents, summed (the checks) */

#define PLACES_AT  180u                                 /* a stock page view's places: their offset in the view */
#define PLACE_SIZE 20u                                  /* ... and their size (mxp_placed) */

/* the page's eight places as the last draw left them (page.c wr_cell, pages.py wr_place_tail, moving.c mv_knob): record
 * ids, 0 none */
static u32 cell_rid[8] D_;
static u32 cell_gen[8] D_;
static u32 draw_gen D_ = 1;

void mxp_draw_begin(void)                               /* page.c wr_screen, before stock's page draws */
{
    draw_gen++;
}

void mxp_cell(int x0, int y0, u32 id)                   /* page.c wr_cell: a stock cell drawn */
{
    int col, p;
    if (x0 < 24 - 13 || x0 > 24 + 3 * 26 + 12)          /* the eight places only: not the left panel's LEV (x -2) */
        return;
    col = (x0 - 24 + 13) / 26;
    p = col + (y0 < 13 ? 4 : 0);
    cell_rid[p] = id;
    cell_gen[p] = draw_gen;
}

/* (2026-11-20) pages.py wr_place_tail: stock's place drawer 0x400169de(view, canvas, x, y, id, value, place, ...) as
 * each place is drawn, every stock machine's: FM TONE's own widgets (which never reach the cell widget, so wr_cell and
 * mxp_cell never saw them) and at their own x (53 71 89 105 on SYN 1, 45 65 85 105 on SYN 2: off the usual columns).
 * PLACE is the view's own: 20-byte entries from VIEW + 180, A..D the top row, E..H the bottom, LEV the ninth (emulator,
 * WaveTone and FM TONE, 2026-11-20); anything else is left */
void mxp_placed(u32 view, u32 id, u32 place)
{
    u32 off = place - view - PLACES_AT;
    if (off % PLACE_SIZE || off / PLACE_SIZE >= 8u)
        return;
    cell_rid[off / PLACE_SIZE] = id;
    cell_gen[off / PLACE_SIZE] = draw_gen;
}

/* (2026-11-20, the User: the knobs that stay per note "say 'per note' in the routes popup") the controls read only at a
 * note's start, as the page drew them (md_page.c from pages.py MNM_PER_NOTE: by the machine and its engine, which share
 * slots; smp_page.c): the last eight reported, with their draw */
static u32 note_rid[8] D_, note_gen[8] D_, note_at D_ = 0;
static u32 note_opens D_ = 0;                           /* mxp_opens when the popup's own flag was taken */
u32 mxp_per_note D_ = 0;                                /* the popup up says PER NOTE (the checks read it) */

void mxp_note(u32 id)
{
    note_rid[note_at & 7u] = id;
    note_gen[note_at & 7u] = draw_gen;
    note_at++;
}

static int note_of(u32 rid)                             /* RID was drawn as a per-note control by the last draw */
{
    for (u32 k = 0; k < 8u; k++)
        if (rid && note_rid[k] == rid && (note_gen[k] == draw_gen || note_gen[k] + 1u == draw_gen))
            return 1;
    return 0;
}

static u32 knob_rid(u32 k)
{
    return k < 8u && (cell_gen[k] == draw_gen || cell_gen[k] + 1u == draw_gen) ? cell_rid[k] : 0u;
}

/* --- the routes: read and written ------------------------------------------------------------- */
static u32 sound_of(u32 t)
{
    u8 *kit = KIT_POINTER;
    return kit && t < 16u ? (u32)kit + 52u + 1163u * t : 0u;
}

static int midi_track(u32 t)
{
    u8 *kit = KIT_POINTER;
    return !kit || (s8)kit[52u + 1163u * t + 0xDEu] == MIDI_TYPE;
}

static u32 stock_get(u32 t, u32 rid)                    /* a stock parameter of track T's sound, its stored value */
{
    u32 s = sound_of(t);
    return s ? *(const u16 *)(s + 20u + 2u * (u32)RECORD(rid)[1]) : 0u;  /* the sound's parameters: +20, a word a slot */
}

static void stock_set(u32 t, u32 rid, u32 value)
{
    u32 owner = UI_OWNER(), ps;
    if (!owner || !(ps = PARAM_SET(owner, rid, t)))
        return;
    SET_VALUE(ps, rid, value, t, 0, 0, 1);
}

static int routes_get(u32 t, u8 *v)                     /* -> bytes (routes.c: the routes and the first routes' marks) */
{
    return mxr_get(t, v);
}

/* the row's depth into this slot (NONE: no route), and where it is: 1 stock's route 1, 2 the record's (MUTED in its
 * source byte when muted), 0 none */
static u32 row_depth(u32 r, int *where, int *at)
{
    u8 v[MXR_BUF + 4];
    int n = routes_get(P.track, v);
    *where = 0;
    *at = -1;
    if (r < 3u && stock_get(P.track, DEST_REC[r]) >> 8 == P.slot) {
        *where = 1;
        return mxr_first_dep(P.track, r);               /* (2026-11-19) its own depth (DEP: the attenuverter) */
    }
    for (int i = 0; i + 4 <= n; i += 4)
        if ((v[i] & ~MUTED) == r && v[i + 1] == P.slot) {
            *where = 2;
            *at = i;
            return (u32)v[i + 2] << 8 | v[i + 3];
        }
    return NONE;
}

static int row_muted(u32 r)                             /* the row's route is muted (the record's MUTED, or the first
                                                         * route's mark: routes.c) */
{
    u8 v[MXR_BUF + 4];
    int where, at;
    row_depth(r, &where, &at);
    if (where == 1)
        return mxr_first_muted(P.track, r);
    if (where != 2)
        return 0;
    routes_get(P.track, v);
    return (v[at] & MUTED) != 0;
}

/* routes in use: the LFOs' shared pool (stock's route 1s and the record's), an envelope's, a MOD SETUP source's */
static u32 used_of(u32 r)
{
    u8 v[MXR_BUF + 4];
    if (r >= OWN_ROWS)
        return mxs_used(P.track, r - OWN_ROWS);
    int n = routes_get(P.track, v);
    u32 c = 0;
    if (r < 3u)
        c = mxr_pool(P.track);                          /* their DESTs and the record's LFO routes (a mark is none) */
    else
        for (int i = 0; i + 4 <= n; i += 4)
            c += (v[i] & ~MUTED) == r;
    return c;
}

/* the LFO overview (MOD held a second; csrc/inserts/ovw_draw.c): track T's LFOs that modulate (bit l: LFO l+1 has
 * stock's DEST, or an unmuted route of the record; bit 3 LFO4's DEST), its routes in use (stock's route 1s with a
 * DEST, the record's unmuted, LFOs and envelopes) and muted; -> the LFO pool it uses (as used_of counts it) */
int mxp_ovw_counts(u32 t, int *marks, int *active, int *muted)
{
    u8 v[MXR_BUF + 4];
    int n = routes_get(t, v), m = 0, a = 0, mu = 0, pool = 0;
    for (u32 l = 0; l < 3u; l++)
        if (stock_get(t, DEST_REC[l]) >> 8 != 0u) {     /* the first route: muted by the record's mark (routes.c) */
            pool++;
            int at = mxr_mark_at(v, n, l);
            if (at >= 0 && v[at + 1] == stock_get(t, DEST_REC[l]) >> 8)   /* the mark is this DEST's */
                mu++;
            else {
                m |= 1 << l;
                a++;
            }
        }
    for (int i = 0; i + 4 <= n; i += 4) {
        u32 src = v[i] & ~MUTED;
        if (mxr_is_mark(v + i))
            continue;
        pool += src < 3u;
        if (v[i] & MUTED) {
            mu++;
        } else {
            a++;
            if (src < 3u)
                m |= 1 << src;
        }
    }
#if DN2_LFO4
    {
        const u16 *e = ((u16 * (*)(u32))LFO4_EXT_FIND)(sound_of(t));
        u16 d = e ? e[3] : ((const u16 *)LFO4_EXT_DEFAULT)[3];   /* SPD MULT FADE DEST ... (csrc/lfo4/ext.h) */
        if (d >> 8)
            m |= 8;
    }
#endif
    *marks = m;
    *active = a;
    *muted = mu;
    return pool;
}

static int full_for(u32 r)
{
    int where, at;
    if (r >= OWN_ROWS)                                  /* MOD SETUP: its four places, none into this slot */
        return mxs_find(P.track, r - OWN_ROWS, P.slot) < 0 && mxs_used(P.track, r - OWN_ROWS) >= MXS_PLACES;
    if (row_depth(r, &where, &at) != NONE || where)
        return 0;
    return used_of(r) >= (r < 3u ? LFO_CAP : ENV_CAP);
}

static void record_put(u8 *v, int n)
{
    wish_put(sound_of(P.track), WT_MX_ROUTES, v, (u32)n);
}

/* the lit row's depth set to DEP. At 0 (NONE) the route goes at once (the User, 2026-11-17, on the unit: a row at 0
 * still drew its value, its tick and its count): stock's route 1 gets DEST 0 (its DEP left at 0, its locks kept), a
 * record's route is dropped; the row is then empty everywhere, the pool counts drop and stock's knob mark goes. NO
 * (FUNC + NO) brings it back with the rest. A muted route keeps its mute while its depth is turned. */
static void say(const char *w);
static void set_depth(u32 r, u32 dep)
{
    u8 v[MXR_BUF + 4];
    int where, at, n = routes_get(P.track, v);
    row_depth(r, &where, &at);
    if (where == 1) {                                   /* the first route: DEP; at 0 it goes, the LFO's next route of
                                                         * the record takes DEST and DEP (routes.c) */
        if (dep == NONE)
            mxr_drop_first(P.track, r);
        else
            mxr_first_set(P.track, r, dep);
        return;
    }
    if (where == 2) {
        if (dep == NONE) {
            for (int i = at; i + 4 < n; i++)
                v[i] = v[i + 4];
            record_put(v, n - 4);
            return;
        }
        v[at + 2] = (u8)(dep >> 8);
        v[at + 3] = (u8)dep;
        record_put(v, n);
        return;
    }
    if (dep == NONE || full_for(r))
        return;
    if (r == E2_ROW && P.slot >= E2_DEST) {             /* ENV2 into its own knobs: it would land after ENV2 stepped */
        say("NOT ITSELF");
        return;
    }
    if (r < 3u && P.slot <= 100u && !(stock_get(P.track, DEST_REC[r]) >> 8)) {   /* the first route: DEST and DEP (a
                                                                 * stock unit plays it; never ENV2's knobs, which stock
                                                                 * has not), no mark left from before */
        mxr_mute_first(P.track, r, 0);
        mxr_first_set(P.track, r, dep);
        stock_set(P.track, DEST_REC[r], P.slot << 8);
        return;
    }
    if (n + 4 > (int)sizeof v)
        return;
    v[n] = (u8)r;
    v[n + 1] = (u8)P.slot;
    v[n + 2] = (u8)(dep >> 8);
    v[n + 3] = (u8)dep;
    record_put(v, n + 4);
}

/* closing: the routes left at 0 go */
static void drop_zeros(void)
{
    u8 v[MXR_BUF + 4];
    int n, m = 0;
    for (u32 l = 0; l < 3u; l++)
        if (stock_get(P.track, DEST_REC[l]) >> 8 == P.slot && mxr_first_dep(P.track, l) == NONE)
            mxr_drop_first(P.track, l);
    n = routes_get(P.track, v);
    for (int i = 0; i + 4 <= n; i += 4)
        if (!(v[i + 1] == P.slot && ((u32)v[i + 2] << 8 | v[i + 3]) == NONE))
            for (int b = 0; b < 4; b++)
                v[m++] = v[i + b];
    if (m != n)
        record_put(v, m);
}

/* the row's route muted (ON 1) or unmuted: a route of the record gets MUTED in its source byte (matrix.c mx_lay lays
 * it in its slot with d1 0: the cells as at depth 0, the cost unchanged); the first route (stock's DEST and DEP) the
 * record's mark, DEST and DEP kept (routes.c; 2026-11-18, the User: the matrix the only source, DEST and DEP its copy).
 * -> 1 when something changed */
static int set_mute(u32 r, int on)
{
    u8 v[MXR_BUF + 4];
    int where, at, n = routes_get(P.track, v);
    u32 dep = row_depth(r, &where, &at);
    if (!where || dep == NONE)
        return 0;
    if (where == 1)
        return mxr_mute_first(P.track, r, on) > 0;
    if (!(v[at] & MUTED) == !on)
        return 0;
    v[at] = (u8)(on ? v[at] | MUTED : v[at] & ~MUTED);
    record_put(v, n);
    if (r < 3u)
        mxr_settle(P.track, r);                         /* an LFO with DEST free: its first route of the record there */
    return 1;
}

/* the UI track's pattern lock pool (80 records {u8 slot, u8 track, u16[128]}, in RAM a record's slot is the mirror
 * slot), 0 when the track is not the popup's */
static u8 *lock_pool(void)
{
    u32 ctx = TRACK_CTX(APP());
    if (!ctx)
        return 0;
    void *model = *(void **)(ctx + 44);
    if (!model || *(u32 *)(ctx + 60) != P.track)
        return 0;
    return (u8 *)((u32 (*)(void *))((*(void ***)model)[10]))(model);
}

/* row R's route into this slot deleted -> 1 when there was one */
static int del_route(u32 r)
{
    u8 v[MXR_BUF + 4];
    int where, at, n = routes_get(P.track, v);
    row_depth(r, &where, &at);
    if (where == 1) {                                   /* the first route: routes.c (DEST 0, its depth none, the LFO's
                                                         * next route of the record there); (2026-11-19) DEP and its
                                                         * p-locks are the LFO's attenuverter: kept */
        mxr_drop_first(P.track, r);
    } else if (where == 2) {
        for (int i = at; i + 4 < n; i++)
            v[i] = v[i + 4];
        record_put(v, n - 4);
    }
    return where != 0;
}

static void say(const char *w)
{
    P.say = w;
    P.say_at = FRAMES_NOW + SAY_TIME;
    smp_overlay_dirty = 1;
}

/* a long NO (0.6 s held): the lit row's route deleted (an empty row: nothing) */
static void erase(void)
{
    if (SRC(mxp_lit) >= OWN_ROWS) {
        if (mxs_delete(P.track, SRC(mxp_lit) - OWN_ROWS, P.slot)) {
            mxp_erased++;
            say("DELETED");
        }
        return;
    }
    if (del_route(SRC(mxp_lit))) {
        mxp_erased++;
        say("DELETED");
    }
}

/* FUNC + NO (the User, 2026-11-17: "funct +no to delete all modulation for that knob"): every route of ours into this
 * slot deleted, muted ones too; (2026-11-21, the User) MOD SETUP's entries into it too */
static void clear_all(void)
{
    for (u32 r = 0; r < OWN_ROWS; r++)
        mxp_erased += (u32)del_route(r);
    for (u32 j = 0; j < MXS_SOURCES; j++)
        mxp_erased += (u32)mxs_delete(P.track, j, P.slot);
    say("ALL CLEARED");
}

/* a MOD SETUP edit's answer (setup.c MXS_) on screen */
static void setup_said(int r)
{
    if (r == -MXS_FULL)
        say("FULL");
    else if (r == -MXS_NOT_IN)
        say("NOT IN SETUP");
    else if (r == -MXS_NO_ROOM)
        say("NO ROOM");
    else if (r < 0)
        say("NO SETUP");
}

/* the lit MOD SETUP row turned by D counts: its depth word in stock's units, 1.00 (0x100) a unit as our rows' (the
 * notch at 0; kn_whole's range 0 .. 65,280 is the word + 32,768) */
#define SETUP_ZERO 0x8000
static void setup_turn(u32 r, int d)
{
    int n;
    u32 j = r - OWN_ROWS;
    s32 w = mxs_sum(P.track, j, P.slot, &n);
    w = w > MXS_TOP ? MXS_TOP : w < MXS_BOTTOM ? MXS_BOTTOM : w;
    s32 old = w + SETUP_ZERO, dep = kn_whole(old, kn_units(d), MXS_TOP + SETUP_ZERO);
    dep = kn_value(KN_KEY_POP | P.slot << 6 | r, old, dep, SETUP_ZERO);
    if (dep != old)
        setup_said(mxs_set(P.track, j, P.slot, dep - SETUP_ZERO));
}

/* --- MOD SETUP's entries (stock's; setup.c edits them) ------------------------------------------ */
/* A sound keeps them from byte 222 (153 bytes, copied whole into the voice's descriptor record at each note:
 * 0x4002549c): from +230 six lists of four {s16 depth, s16 slot}, in the order VEL PB MW BC AT KEY (2026-11-21,
 * measured on stock's six pages; until then MW's and PB's rows read each other's list: setup.c mxs_list). The kernel
 * (0x400db390) adds value x depth / 2048 to the slot's cell, list l's value from MOD_VAL[l]: VEL by voice, the next
 * four by the voice's track, KEY by voice (a long, >> 8, less 15360). */
#define MOD_LIST mxs_list                               /* row VEL MW PB AT BC KEY -> the sound's list */
static const u32 MOD_VAL[5] = {0x8000DD40u, 0x8000DE40u, 0x8000DE20u, 0x8000DE00u, 0x8000DDE0u};
#define MOD_KEY    ((volatile s32 *)0x8000DDA0u)
#define MOD_FULL   32512                                /* a source's top (0x7f00) */

s32 mxp_setup_dep D_ = 0;                               /* the checks: the lit MOD SETUP row's depth as drawn */
u32 mxp_setup_hint D_ = 0;                              /* the checks: the lit MOD SETUP row's source + 1 (hint) */
u32 mxp_rows_drawn D_ = 0;                              /* the checks: our rows drawn with a route (bit: source row) */
u32 mxp_setup_rows D_ = 0;                              /* the MOD SETUP rows drawn with a route (bit j: row 5 + j) */

static s32 mod_depth(u32 j, int *any)                   /* row 5 + J: its entries into this slot, summed */
{
    int n;
    s32 d = mxs_sum(P.track, j, P.slot, &n);
    *any = n > 0;
    return d;
}

static int mod_both(u32 j)                              /* row 5 + J swings both ways: PB, KEY */
{
    return j == 2u || j == 5u;
}

static s32 mod_value(u32 j, u32 v)                      /* row 5 + J's source now, on voice V */
{
    u32 l = MOD_LIST[j];
    if (l == 5u)
        return (MOD_KEY[v] >> 8) - 15360;
    return ((volatile s16 *)MOD_VAL[l < 5u ? l : 0u])[l ? OWNER[v] & 15u : v];
}

/* --- the rows' order --------------------------------------------------------------------------- */
static int row_used(u32 r)                              /* a route into this slot, at a depth other than 0 */
{
    int where, at, any;
    if (r < OWN_ROWS)
        return row_depth(r, &where, &at) != NONE && !row_muted(r);
    return mod_depth(r - OWN_ROWS, &any) != 0 && !mxs_muted(P.track, r - OWN_ROWS, P.slot);
}

static void make_order(void)                            /* the used rows first, then the others; each in usual order */
{
    u32 n = 0, used = 0;
    for (u32 r = 0; r < ROWS; r++)
        used |= (u32)row_used(r) << r;
    for (u32 pass = 0; pass < 2u; pass++)
        for (u32 r = 0; r < ROWS; r++)
            if ((used >> r & 1u) == (pass == 0u))
                mxp_order[n++] = (u8)r;
}

/* --- open, close, the keys -------------------------------------------------------------------- */
static int refused_but_ins(u32 t)
{
    return (smp_held_lo >> 25 & 0xFFFFu) != 0u                /* a trig held */
           || smp_question_up() || rec_overlay || (amp_sub && amp_sub != AMP_ENV2_PAGE) || midi_track(t);
}

static int refused(u32 t)
{
    return refused_but_ins(t) || ins_visible();
}

/* (2026-11-19) a screen, list or popup of ours (or a stock screen ours knows) over the page: the cells the page drew
 * under it are not what the knobs turn now. A plain push opens nothing there (FUNC + push never did: a page of ours) */
static int covered(void)
{
    extern int sn_up(void), tn_visible(void), tn_kb_up(void), slc_visible(void), smp_fb_visible(void);
    extern int smp_list_visible(void), msel_visible(void), scope_visible(void), wpop_shown(void), ldp_visible(void);
    extern int ovw_visible(void), fxp_visible(void), rec_visible(void);
    extern int mtr_big;
    return sn_up() || tn_visible() || tn_kb_up() || slc_visible() || smp_fb_visible() || smp_list_visible()
           || msel_visible() || scope_visible() || wpop_shown() || ldp_visible() || ovw_visible() || fxp_visible()
           || rec_visible() || mtr_big;
}

#define SOUND_PAGES 16u                                 /* a record's page id (+0): 0..15 the sound's own pages (SYN,
                                                         * the filter types, AMP, FLTR, PORTAMENTO, the sends;
                                                         * docs/parameter-set-tables.md); 16.. FX and globals, MIDI,
                                                         * the LFOs, 29 the trig page (FILL: slot 25) */

/* (2026-11-18, the User) on ENV2's page its knobs ATK HOLD DEC SUS REL are ENV2's own destinations (0xE0 + the knob):
 * their records are stock's AMP ones (62..66), whose voice-row cells are ENV1's; (2026-11-20, the User) MODE, RSET (73,
 * 74) and H (83, drawn as LFO1's DEP) too: 0xE5, 0xE6, 0xE7. G (ENV2's DEST): none. -> the slot, 0 none, or the
 * record's own */
static u32 slot_of(u32 rid)
{
    extern int env2_field_drawn_page(u32 id);           /* env2_page.c: ID is one of ENV2's own on its page */
    extern int env2_field_index(u32 id);
    if (amp_sub == AMP_ENV2_PAGE && env2_field_drawn_page(rid)) {
        int f = env2_field_index(rid);
        return f >= 0 && (u32)f < E2_N ? E2_DEST + (u32)f : 0u;
    }
    return (u32)RECORD(rid)[1];
}

/* -> why the popup cannot open now on knob K's record RID (0: it can; 1 no parameter, 2 refused here, 3 not a sound
 * parameter of the row), kept in mxp_why, the record in mxp_rid; its row slot in *SLOT. (2026-11-20, live inserts) on an
 * INSERT page knob K's destination instead (ins.c: 0xC0 + 7 j + i; none for M.SEL, AUTO, TAPE's PGAIN and the
 * delay-time and jump knobs, ROUTE_OK), its label in *INAME, no record */
static u32 why_not(u32 k, u32 rid, u32 *slot, const char **iname)
{
    u32 t = UI_TRACK & 15u, why;
    *iname = 0;
    if (ins_visible()) {
        *slot = ins_route_dest(k, iname);
        mxp_rid = 0;
        mxp_why = !*slot ? 3u : refused_but_ins(t) || covered() ? 2u : 0u;
        return mxp_why;
    }
    why = !rid ? 1u : refused(t) || covered() ? 2u : 0u;
    *slot = rid ? slot_of(rid) : 0u;
    if (!why && !(*slot >= E2_DEST && *slot < E2_DEST + E2_N)
        && (*slot < 25u || *slot > 100u || (u32)RECORD(rid)[0] >= SOUND_PAGES))
        why = 3u;
    mxp_rid = rid;
    mxp_why = why;
    return why;
}

/* knob K's popup on record RID: the one its place had when the push began (P.plain_rid; 2026-11-20: the place is read
 * at the press, before the redraws the push itself brings, stock's peek among them) */
static void open(u32 k, u32 rid)
{
    u32 t = UI_TRACK & 15u, slot;
    const char *iname;
    if (why_not(k, rid, &slot, &iname)) {
        mxp_refusals++;
        return;
    }
    P.knob = k;
    P.rid = rid;
    P.slot = slot;
    P.iname = iname;
    P.track = t;
    mxp_lit = 0;
    make_order();                                       /* fixed until the popup closes */
    P.say = 0;
    P.last = FRAMES_NOW;
    P.up = 1;
    mxp_opens++;
    smp_overlay_dirty = 1;
}

static void close(void)                                 /* every change is kept (no undo key: the User, 2026-11-17) */
{
    P.no_down = 0;
    if (!P.up)
        return;
    drop_zeros();
    P.up = 0;
    smp_overlay_dirty = 1;
}

int mxp_visible(void)
{
    return P.up;
}

static void step_lit(u32 code)                          /* UP or DOWN: the lit row one up or down */
{
    int r = (int)mxp_lit + (code == K_ARROW_DN ? 1 : -1);
    mxp_lit = (u32)(r < 0 ? 0 : r >= ROWS ? ROWS - 1 : r);
    smp_overlay_dirty = 1;
}

/* a row's section: 0 the LFOs, 1 the envelopes, 2 MOD SETUP's */
static u32 section_of(u32 place)
{
    u32 r = SRC(place);
    return r < 3u ? 0u : r < OWN_ROWS ? 1u : 2u;
}

/* FUNC + UP or DOWN (the User, 2026-11-19): the lit row to the previous / next section, a section being a run of
 * places whose rows are of one kind, as the rows are shown (sorted at the open). DOWN: the next run's first place (on
 * the last run: stays). UP: this run's first place, or the previous run's when already on it (place 0: stays). */
static void jump_lit(u32 code)
{
    u32 l = mxp_lit;
    if (code == K_ARROW_DN) {
        while (l + 1u < ROWS && section_of(l + 1u) == section_of(l))
            l++;
        if (l + 1u < ROWS)
            mxp_lit = l + 1u;
    } else {
        if (l > 0u && section_of(l - 1u) != section_of(l))
            l--;                                        /* on its run's first place: into the previous run */
        while (l > 0u && section_of(l - 1u) == section_of(l))
            l--;
        mxp_lit = l;
    }
    smp_overlay_dirty = 1;
}

static void arrow(u32 code)                             /* UP or DOWN while up: FUNC held, by sections */
{
    if (smp_func_held)
        jump_lit(code);
    else
        step_lit(code);
}

/* rec.c smp_ui_pop, every item first, before anything of ours may take it: while a plain push is held, any other key's
 * item or another encoder's turn cancels its popup (2026-11-19, the User: "only if nothing else happened while the knob
 * was held").
 *
 * Its own knob's turn (2026-11-20, the User: "I could not get it to work"; "if the knob moves (even by one) while
 * pressed, it doesn't work"): a pushed encoder wobbles. Counts summed under KN_PUSH_WOBBLE either way are held back:
 * the item is dropped (-> 1), so no value moves and the popup still opens at the release. The item that reaches
 * KN_PUSH_WOBBLE carries every count held back (stock's push + turn, its big steps, from the first count) and cancels
 * the popup. Otherwise the item is read, never changed (-> 0) */
int mxp_seen(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    if (!P.plain_k)
        return 0;
    if (it[0] == IT_KNOB && code == P.plain_k) {
        int d = P.plain_d + (s8)it[8];
        if (d > -KN_PUSH_WOBBLE && d < KN_PUSH_WOBBLE) {
            P.plain_d = d;
            mxp_wobbles++;
            return 1;
        }
        it[8] = (u8)(s8)d;                              /* |d| <= KN_PUSH_WOBBLE - 1 + 30 (the panel's clamp) */
        P.plain_k = 0;
        P.plain_d = 0;
        mxp_cancels++;
        return 0;
    }
    if (it[0] == IT_KNOB || (it[0] == IT_KEY && code != K_PUSH0 + P.plain_k - 1u)) {
        P.plain_k = 0;                                  /* (its counts held back stay unsent: under a stock step) */
        P.plain_d = 0;
        mxp_cancels++;
    }
    return 0;
}

/* rec.c smp_ui_pop, before the overlays: -> 1 when the item is ours (dropped)
 *
 * A held key's repeats (2026-11-18, the User: "holding NO also only mutes"): while a key stays down, stock's key task
 * (0x4011f8bc, each panel tick) sends it again, the first 24 ticks after the press (0.2 s on the unit), then every 8,
 * with bit 3 set BESIDE the press's own bit 0 (and FUNC's bit 1). v1 read bit 0 alone as a press, so each repeat began
 * the key's work anew: a held NO's 0.6 s restarted every 8 ticks and its release muted; FUNC + a held push never
 * reached its reset and its release opened the popup; a push-and-turn held past the first repeat closed the popup on
 * its release. A repeat is a press only for UP and DOWN (the lit row steps with them, as stock's lists' arrows); every
 * other repeat of a key whose press was ours is dropped, the rest go on to stock as before. */
int mxp_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int repeat = (flags & F_REPEAT) && !(flags & F_RELEASE);
    int press = (flags & F_PRESS) && !(flags & F_RELEASE) && !repeat, release = (flags & F_RELEASE) != 0;

    if (it[0] == IT_KEY && code >= K_PUSH0 && code < K_PUSH0 + 8u) {
        u32 k = code - K_PUSH0;
        if (repeat)                                     /* a held push: its press began what it does */
            return P.ign_k == k + 1u || (P.up && k == P.knob);
        if (press && smp_func_held) {                   /* FUNC + push: stock's (2026-11-19, the User); timed for the
                                                         * long push's reset (mxp_poll) */
            mxp_pushes++;
            P.plain_k = 0;
            if (P.up) {                                 /* begun while up: ignored, its release too (the User, */
                P.ign_k = k + 1u;                       /* 2026-11-17: a bounced push closed the popup, then reset */
                return 1;                               /* the parameter) */
            }
            P.push_at = FRAMES_NOW;
            P.push_k = k + 1u;
            P.reset_done = 0;
            return 0;
        }
        if (release && P.ign_k == k + 1u) {
            P.ign_k = 0;
            return 1;
        }
        if (release && P.push_k == k + 1u) {
            P.push_k = 0;
            return 0;
        }
        if (press && !P.up) {                           /* a plain push: stock's (its peek, push + NO, big steps); it
                                                         * may open the popup at its release, if no other key is down
                                                         * now (LIVE REC's NO + push, a trig + push), the popup can
                                                         * open on this knob now (else stock's push as it is, its turns
                                                         * untouched) and nothing comes while it is held (mxp_seen) */
            u32 others = smp_held_lo | (smp_held_hi & ~(1u << (K_PUSH0 - 32u + k))), slot;
            P.plain_k = 0;
            P.plain_d = 0;
            if (others)
                return 0;
            const char *iname;
            if (why_not(k, knob_rid(k), &slot, &iname)) {
                mxp_refusals++;
                return 0;
            }
            P.plain_k = k + 1u;
            P.plain_rid = mxp_rid;
            mxp_plains++;
            return 0;
        }
        if (release && P.plain_k == k + 1u) {           /* let go with nothing else: the popup (or a refusal); the
                                                         * release goes on to stock (its knob let go) */
            P.plain_k = 0;
            if (!P.up)
                open(k, P.plain_rid);
            return 0;
        }
        if (P.up && k == P.knob) {                      /* the same knob pushed and let go, no turn: closed, kept */
            if (press)
                P.turned = 0;
            else if (release && !P.turned)
                close();
            return 1;
        }
        return 0;
    }
    if (!P.up)
        return 0;
    P.last = FRAMES_NOW;
    if (it[0] == IT_KNOB && code >= 1u && code <= 8u) {
        int d = (s8)it[8];
        mxp_turns++;
        mxp_detents += d;
        if (code - 1u != P.knob) {                      /* another knob: closed, kept; the turn is stock's */
            close();
            return 0;
        }
        if (smp_held_hi >> (K_PUSH0 - 32 + P.knob) & 1u) {     /* push-and-turn: the lit row moves */
            P.turned = 1;
            int r = (int)mxp_lit + (d > 0 ? 1 : d < 0 ? -1 : 0);
            mxp_lit = (u32)(r < 0 ? 0 : r >= ROWS ? ROWS - 1 : r);
        } else if (SRC(mxp_lit) >= OWN_ROWS) {          /* (2026-11-21) MOD SETUP: stock's entry (setup.c) */
            setup_turn(SRC(mxp_lit), d);
        } else {                                        /* (2026-11-19, the User: knob precision, csrc/knobs) a slow */
            int where, at;                              /* turn 1 unit every 3 counts, whole units, the notch at 0 */
            s32 old = (s32)row_depth(SRC(mxp_lit), &where, &at);
            s32 dep = kn_whole(old, kn_units(d), DEP_TOP);
            dep = kn_value(KN_KEY_POP | P.slot << 6 | SRC(mxp_lit), old, dep, NONE);
            if (dep != old)
                set_depth(SRC(mxp_lit), (u32)dep);
        }
        smp_overlay_dirty = 1;
        return 1;
    }
    if (it[0] == IT_KEY && repeat) {                    /* a held key: UP and DOWN step on, NO and YES nothing */
        if (code == K_ARROW_UP || code == K_ARROW_DN)
            arrow(code);
        return code == K_ARROW_UP || code == K_ARROW_DN || code == K_YES || code == K_NO;
    }
    if (it[0] == IT_KEY && press) {
        mxp_keys++;
        if (code == K_ARROW_UP || code == K_ARROW_DN) {
            arrow(code);
            return 1;
        }
        if (code == K_NO && smp_func_held) {            /* FUNC + NO: every route into this parameter deleted */
            clear_all();
            return 1;
        }
        if (code == K_NO) {                             /* NO: mute at the release, delete when held (mxp_poll) */
            P.no_at = FRAMES_NOW;
            P.no_down = 1;
            P.no_long = 0;
            return 1;
        }
        if (code == K_YES) {                            /* YES: the lit row's route unmuted; on an empty row a route */
            int where, at;                              /* at +32 (the User, 2026-11-18: as the LFO DEST popup; the */
            u32 r = SRC(mxp_lit);                       /* knob then sets it; route 1 first, as a turn from 0) */
            if (r >= OWN_ROWS) {                        /* (2026-11-21) MOD SETUP: unmute, or a new entry at +32 */
                u32 j = r - OWN_ROWS;
                if (mxs_find(P.track, j, P.slot) < 0)
                    setup_said(mxs_set(P.track, j, P.slot, YES_DEPTH * 0x100));
                else if (mxs_mute(P.track, j, P.slot, 0) > 0)
                    say("UNMUTED");
                smp_overlay_dirty = 1;
            } else if (row_depth(r, &where, &at) == NONE || !where) {
                if (full_for(r))
                    say("FULL");
                else {
                    set_depth(r, NONE + YES_DEPTH * 0x100u);
                    smp_overlay_dirty = 1;              /* the row shows it (the User: no ADDED box over the rows) */
                }
            } else if (set_mute(r, 0))
                say("UNMUTED");
            return 1;
        }
        if (code == K_FUNC)
            return 0;                                   /* FUNC: held for the next FUNC + push */
        close();                                       /* a key that leaves: kept, and the key does its work */
        return 0;
    }
    if (it[0] == IT_KEY && release && code == K_NO && P.no_down) {     /* a short NO: the lit row's route muted */
        P.no_down = 0;
        if (!P.no_long) {
            int m = SRC(mxp_lit) >= OWN_ROWS ? mxs_mute(P.track, SRC(mxp_lit) - OWN_ROWS, P.slot, 1)
                                             : set_mute(SRC(mxp_lit), 1);
            if (m > 0)
                say("MUTED");
            else
                setup_said(m);
        }
        return 1;
    }
    return code == K_ARROW_UP || code == K_ARROW_DN || code == K_YES || code == K_NO;   /* their releases */
}

/* --- the redraws (2026-11-18, the User: "mod matrix popup => cpu warning") ----------------------------------------
 * v1 asked stock for a full redraw 25 times a second while up: stock's page drawn under the popup, the popup drawn a
 * pixel a call, panel_diff over the whole screen; and the moving controls' lines hidden under it asked for more. Now:
 * - The popup's frame is two layers: the STILL layer (the header, each row's icon, name, depth, the bar's reach and
 *   tick, a muted bar, the lit row's word, "LOCKS") and the MOVING one (each bar's live offset, the LOCKS cells and
 *   their playing step and page), then the lit row inverted. They share no pixel (rows are 9 apart and each row's
 *   pixels stay in its own 9; LOCKS's cells in rows 1..6, its word left of them), so drawing the still layer, then the
 *   moving one, then the inversion sets exactly the pixels v1's draw set row by row.
 * - A full draw (stock's, as before) keeps the still layer (rows 0..53 of the canvas, STILL) and what the moving layer
 *   showed (drawn). mxp_end, at the end of that draw, keeps its buffer when nothing of ours drew over rows 0..53 after
 *   the popup (the inserts overview; the system meter draws only in the title bar, rows 54..63).
 * - 15 times a second the moving layer is worked out again (mxp_dyn). The same: nothing is drawn. Changed, while that
 *   frame is still on the glass (BACK) and no redraw is due: the frame is made again from STILL, the moving layer and
 *   the inversion in FRONT (the scratch buffer stock clears before every draw), its rows 0..53 copied into BACK where
 *   they differ, and only those 8-px groups sent (stock's sender 0x40131f04, then the 0xB8 show: the line-only
 *   method, csrc/modulation/moving.c). The title bar is left as the full draw left it.
 * - Not while the panel UART still holds 128 bytes or more (looked at again 10 ms later), as the scope.
 * - Anything else (a key, a knob, the word on screen, LOCKS appearing or going) asks for the full redraw as before. */
#define GLASS_GROUP ((void (*)(u32, u32, const u8 *))0x40131F04u)   /* (column 0..120, page 0..7, 8 bytes) */
#define GLASS_SHOW  ((void (*)(void))0x40131EECu)
#define IS_DIRTY   ((u8 (*)(void *))0x4011D5D4u)        /* move.b: only %d0's low byte (csrc/modulation) */
#define FB_FRONT   (*(u8 *volatile *)0x402A10C8u)
#define FB_BACK    (*(u8 *volatile *)0x402A10CCu)
#define CANVAS_NEW ((void (*)(void *, int, int, u8 *, void *))0x40113E2Au)
#define CANVAS_AID ((void *)0x4059DDB0u)
#define CANVAS_BUF(cv) (*(u8 **)((u8 *)(cv) + 16))
#define UART_PEND  (*(volatile u32 *)0x4058E5D8u)       /* the panel UART's ring (csrc/scope/scope.c) */
#define UART_HEAD  (*(volatile u32 *)0x4058E5D0u)
#define UART_TAIL  (*(volatile u32 *)0x4058E5DCu)
#define TCD_CITER  (*(volatile u16 *)0xFC045474u)
#define TCD_BITER  (*(volatile u16 *)0xFC04547Cu)
#define UART_IDLE  128u
#define RETRY      15u                                  /* frames: 10 ms */
#define STILL_ROWS 54                                   /* rows 0..53: the popup's own; 54..63 the title bar */

struct mxp_place {                                      /* a row on screen, as the last full draw laid it out */
    s16 kind;                                           /* 0 no live bar, 1 a route of ours, 2 a MOD SETUP row, 3 a
                                                         * row with no route: its source's level, dimmed */
    s16 r, both, y, x0, x1;                             /* its source; the bar's 0 in the middle; its y, columns */
    s32 d;                                              /* the depth the live offset is worked out from */
};
struct mxp_dyn {                                        /* the moving layer: what decides its pixels */
    s32 o[SHOWN];                                       /* each bar's live offset, in pixels */
    s32 shown, len, cur, page, cells, pages, say;       /* LOCKS: shown, the pattern's length, the playing step, its
                                                         * page, that page's locked steps, the pages holding one;
                                                         * the word on screen up */
};
#define DYN_WORDS  ((int)(sizeof(struct mxp_dyn) / 4))

static struct mxp_place place[SHOWN] D_;
static s32 lit_y D_ = -1;                               /* the lit row's y (-1: none on screen) */
static u32 still[2 * 128] D_;                           /* the still layer of the last full draw (STILL_ROWS used) */
static int still_ok D_ = 0;
static struct mxp_dyn drawn D_;                         /* the moving layer the glass shows */
static u8 *drew_buf D_ = 0;                             /* mxp_draw's canvas buffer in the draw going on */
static u8 *alone_back D_ = 0;                           /* that draw's buffer, if the popup was left on top */
u32 mxp_fulls D_ = 0, mxp_parts D_ = 0, mxp_same D_ = 0, mxp_dropped D_ = 0, mxp_groups D_ = 0;   /* the checks */
static s32 dim_o[SHOWN] D_;
u32 mxp_ticks D_ = 0, mxp_dims D_ = 0;                 /* the moving layer's passes; the dimmed levels worked out */

u32 mxp_uart_backlog(void)                              /* bytes in the panel UART's ring not yet sent (scope.c; the
                                                         * DEST popup's too, dest_pop.c) */
{
    u32 inflight = ((u32)(TCD_CITER & 0x7FFFu) - (u32)(TCD_BITER & 0x7FFFu) + (UART_HEAD - UART_TAIL)) & 0xFFFu;
    return inflight + UART_PEND;
}

static void dyn_copy(struct mxp_dyn *to, const struct mxp_dyn *from)   /* (word by word: no memcpy in the chunk) */
{
    volatile s32 *t = (volatile s32 *)to;
    const s32 *f = (const s32 *)from;
    for (int k = 0; k < DYN_WORDS; k++)
        t[k] = f[k];
}

static int dyn_same(const struct mxp_dyn *a, const struct mxp_dyn *b)
{
    const volatile s32 *x = (const volatile s32 *)a, *y = (const volatile s32 *)b;
    for (int k = 0; k < DYN_WORDS; k++)
        if (x[k] != y[k])
            return 0;
    return 1;
}

/* page.c wr_poll: the long push's reset (outside the popup only); while up, the long NO's delete, closing on its own
 * and the moving layer's updates */
static void mxp_dyn(struct mxp_dyn *st, int all);
static void alone(const struct mxp_dyn *st);
void mxp_poll(void *screen)
{
    if (P.push_k && !P.reset_done && FRAMES_NOW - P.push_at >= LONG) {
        u32 k = P.push_k - 1u, rid = knob_rid(k), t = UI_TRACK & 15u;
        P.reset_done = 1;
        extern int env2_reset(u32 id);                  /* env2_page.c: ENV2's own knob on its page -> its default */
        if (!P.up && ins_visible())                     /* (2026-11-19) an INSERT page: the insert's place (ins.c; AUTO OFF) */
            ins_knob_reset((int)k);
        else if (!P.up && rid && rid != DEST_REC[0] && rid != DEST_REC[1] && rid != DEST_REC[2] && !refused(t)
                 && !env2_reset(rid))                   /* (2026-11-19: never an LFO's DEST, where stock's FUNC + push
                                                         * opens its list) */   /* the record's default, as stock's setValue writes it;
                                                         * (2026-11-19, the User) an LFO's DEP, the attenuverter: 100 % */
            stock_set(t, rid, rid == DEP_REC[0] || rid == DEP_REC[1] || rid == DEP_REC[2] ? 0x7FFEu
                              : (u32)RECORD(rid)[4]);
    }
    if (!P.up)
        return;
    if (P.no_down && !P.no_long && FRAMES_NOW - P.no_at >= LONG) {   /* a long NO: the lit row's route deleted */
        P.no_long = 1;
        P.last = FRAMES_NOW;
        erase();
    }
    if ((UI_TRACK & 15u) != P.track || smp_question_up() || FRAMES_NOW - P.last >= IDLE) {
        close();
        return;
    }
    if ((int)(FRAMES_NOW - P.next_draw) < 0)
        return;
    if (mxp_uart_backlog() >= UART_IDLE) {                  /* never queued behind the panel UART */
        P.next_draw = FRAMES_NOW + RETRY;
        mxp_dropped++;
        return;
    }
    P.next_draw = FRAMES_NOW + REDRAW;
    struct mxp_dyn st;
    mxp_dyn(&st, !(mxp_ticks++ & 1u));                 /* (the dimmed levels every other pass) */
    int same = dyn_same(&st, &drawn);
    mxp_same += (u32)same;
    if (!alone_back || FB_BACK != alone_back || (IS_DIRTY(screen) & 0xFFu) || smp_overlay_dirty || st.say
        || st.shown != drawn.shown) {                   /* (smp_overlay_dirty: a key changed the popup, its full
                                                         * redraw comes in this pass: nothing drawn from the old one) */
        if (same)
            return;
        mxp_fulls++;
        SET_DIRTY(screen);
        return;
    }
    alone(&st);                                         /* (2026-11-21, the User: the same work every pass, moving or
                                                         * not: made again and compared, only changed groups sent) */
    dyn_copy(&drawn, &st);
    mxp_parts++;
}

/* page.c wr_screen, at the end of every full draw: CLEAN when nothing of ours drew over rows 0..53 after the popup */
void mxp_end(void *canvas, int clean)
{
    u8 *b = CANVAS_BUF(canvas);
    alone_back = clean && still_ok && drew_buf == b ? b : 0;
    drew_buf = 0;
}

/* --- drawing (the canvas counts y up from the bottom) ------------------------------------------ */
static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
    cv_fill(c, x0, y0, x1, y1, on);             /* (2026-11-17) the same pixels a column word at a time: page.c */
}

/* a pixel set, straight in the canvas's words: stock's SET_PIXEL (0x40113e70) with ON 1, its clip included (page.c
 * cv_fill: +4 width, +8 height, +12 longs a column, +16 the bits; pixel (x, y) bit 31 - (y & 31) of long
 * x * stride + (y >> 5)) */
static void px(void *c, int x, int y)
{
    const int *cv = (const int *)c;
    if (x >= 0 && y >= 0 && x < cv[1] && y < cv[2])
        ((u32 *)cv[4])[x * cv[3] + (y >> 5)] |= 0x80000000u >> (y & 31);
}

void mxp_invert(void *c, int x0, int y0, int x1, int y1)    /* as popup.c's, a column word at a time (dest_pop.c too) */
{
    const int *cv = (const int *)c;
    u32 *bits = (u32 *)cv[4];
    x0 = x0 < 0 ? 0 : x0;
    y0 = y0 < 0 ? 0 : y0;
    x1 = x1 >= cv[1] ? cv[1] - 1 : x1;
    y1 = y1 >= cv[2] ? cv[2] - 1 : y1;
    for (int k = y0 >> 5; x0 <= x1 && y0 <= y1 && k <= y1 >> 5; k++) {
        u32 lo = k == y0 >> 5 ? (u32)(y0 & 31) : 0u, hi = k == y1 >> 5 ? (u32)(y1 & 31) : 31u;
        u32 m = (0xFFFFFFFFu >> lo) & ~(hi == 31u ? 0u : 0xFFFFFFFFu >> (hi + 1u));
        for (int x = x0; x <= x1; x++)
            bits[x * cv[3] + k] ^= m;
    }
}

/* the icons, 9 x 7, a row a byte pair (bit 8 the left column), top row first: the LFOs by stock's WAVE (TRI SINE SQR
 * SAW EXPO RAMP RAND), an envelope by its outline (scratch/modulation/mockups/src/icons.py) */
static const u16 ICON[8][7] = {
    {0x020, 0x050, 0x050, 0x111, 0x00A, 0x00A, 0x004},  /* TRI */
    {0x0C0, 0x120, 0x120, 0x010, 0x009, 0x009, 0x006},  /* SINE */
    {0x1E3, 0x122, 0x122, 0x122, 0x122, 0x122, 0x13E},  /* SQR */
    {0x010, 0x030, 0x050, 0x090, 0x111, 0x112, 0x10C},  /* SAW */
    {0x001, 0x001, 0x003, 0x005, 0x009, 0x031, 0x1C1},  /* EXPO */
    {0x01F, 0x020, 0x040, 0x080, 0x100, 0x100, 0x100},  /* RAMP */
    {0x070, 0x050, 0x1D0, 0x113, 0x112, 0x11E, 0x000},  /* RAND */
    {0x040, 0x0A0, 0x110, 0x10F, 0x101, 0x101, 0x101},  /* an envelope */
};

static void icon(void *c, int x, int y, const u16 *ic)
{
    for (int r = 0; r < 7; r++)
        for (int b = 0; b < 9; b++)
            if (ic[r] >> (8 - b) & 1u)
                px(c, x + b, y + 6 - r);
}

/* a muted route's bar: the outline and the tick dotted, no live offset */
void mxp_dotted(void *c, int x0, int y0, int x1, int y1)   /* every other pixel: a muted bar (dest_pop.c too) */
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            if (!((x + y) & 1))
                px(c, x, y);
}

static void bar_muted(void *c, int y, int x0, int x1, s32 depth, int both)
{
    int z = both ? (x0 + x1) / 2 : x0, half = both ? (x1 - x0) / 2 : x1 - x0;
    int d = (int)((depth * half) / 0x7FFE), m = d < 0 ? -d : d;
    int a = both ? z - m : (d < 0 ? z + d : z), b = both ? z + m : (d < 0 ? z : z + d);
    if (b > a) {
        mxp_dotted(c, a, y, b, y);
        mxp_dotted(c, a, y + 4, b, y + 4);
        mxp_dotted(c, a, y, a, y + 4);
        mxp_dotted(c, b, y, b, y + 4);
    }
    mxp_dotted(c, z + d, y - 1, z + d, y + 5);
}

/* the moving bar in [x0, x1], its 0 at Z: the reach outline and the depth's tick (still); the live offset is the
 * moving layer's (bar_offset) */
static void bar(void *c, int y, int x0, int x1, s32 depth, int both)
{
    int z = both ? (x0 + x1) / 2 : x0, half = both ? (x1 - x0) / 2 : x1 - x0;
    int d = (int)((depth * half) / 0x7FFE);
    int a = z - (both ? (d < 0 ? -d : d) : (d < 0 ? -d : 0)), b = z + (d < 0 ? (both ? -d : 0) : d);
    if (b > a) {                                        /* the outline: the reach */
        fill(c, a, y, b, y, 1);
        fill(c, a, y + 4, b, y + 4, 1);
        fill(c, a, y, a, y + 4, 1);
        fill(c, b, y, b, y + 4, 1);
    }
    fill(c, z + d, y - 1, z + d, y + 5, 1);             /* the depth's tick */
}

static int offset_px(const struct mxp_place *p, s32 now)   /* the offset applied now, in pixels */
{
    int half = p->both ? (p->x1 - p->x0) / 2 : p->x1 - p->x0;
    return (int)((now * half) / 0x7FFE);
}

static void bar_offset(void *c, const struct mxp_place *p, int o)
{
    int z = p->both ? (p->x0 + p->x1) / 2 : p->x0;
    if (o)
        fill(c, o < 0 ? z + o : z, p->y + 1, o < 0 ? z : z + o, p->y + 3, 1);
}

static void lay(int i, int kind, u32 r, int y, int x0, int x1, int both, s32 d)
{
    struct mxp_place *p = &place[i];
    p->kind = (s16)kind;
    p->r = (s16)r;
    p->y = (s16)y;
    p->x0 = (s16)x0;
    p->x1 = (s16)x1;
    p->both = (s16)both;
    p->d = d;
}

/* stock's MOD SETUP number for a depth word: word / 256 with two decimals, cut toward 0 (stock's pages: 0x01e7 "1.90",
 * 0xfdf1 "-2.05", 0x0021 "0.12", 0x0d48 "13.28"; measured 2026-11-21) */
static void stock_num(char *b, s32 w)
{
    u32 a = (u32)(w < 0 ? -w : w), i = a >> 8, f = ((a & 0xFFu) * 100u) >> 8, k = 0;
    char dg[4];
    if (w < 0)
        *b++ = '-';
    do {
        dg[k++] = (char)('0' + i % 10u);
        i /= 10u;
    } while (i && k < 4u);
    while (k)
        *b++ = dg[--k];
    *b++ = '.';
    *b++ = (char)('0' + f / 10u);
    *b++ = (char)('0' + f % 10u);
    *b = 0;
}

/* a MOD SETUP row (source R): its name and whose value it reads (/V the voice's, /T the track's: the User, 2026-11-21);
 * with an entry, its depth in stock's number and the bar as the kernel applies it (in the LFO rows' units: half the
 * cells' reach), dotted when muted; without, the source's level dimmed (the moving layer); lit, its count (n/4, FULL)
 * or MUTE at the right, as our rows */
#define SETUP_NUM  35                                   /* "-128.00": 7 letters of 4 pixels, to x 62 */
#define SETUP_X0   66                                   /* its bar: 66 .. 98, its 0 in the middle (a unipolar source's
                                                         * negative depth reaches left from there, never over the
                                                         * number) */
#define SETUP_MID  82
static void mod_row(void *c, int i, u32 r, int y, int lit)
{
    int any;
    u32 j = r - OWN_ROWS;
    s32 d = mod_depth(j, &any);
    int muted = any && mxs_muted(P.track, j, P.slot), both = mod_both(j), x0 = both ? SETUP_X0 : SETUP_MID;
    TEXT(c, FONT, 13, y, 0, "%s/%s", NAME[r], j == 0u || j == 5u ? "V" : "T");
    if (any) {                                          /* x / 4096 in 32 bits: four routes' depth reaches 2^17 */
        char num[12];
        s32 reach = ((d >> 4) * MOD_FULL) >> 8;
        reach = reach > DEP_TOP ? DEP_TOP : reach < -DEP_TOP ? -DEP_TOP : reach;
        stock_num(num, d);
        TEXT(c, FONT, SETUP_NUM, y, 0, "%s", num);
        if (muted)
            bar_muted(c, y + 1, x0, 98, reach, both);
        else {
            bar(c, y + 1, x0, 98, reach, both);
            lay(i, 2, r, y + 1, x0, 98, both, d);
        }
        mxp_setup_rows |= 1u << j;
    } else
        lay(i, 3, r, y + 1, x0, 98, both, 0);
    if (lit) {
        mxp_setup_dep = any ? d : 0;
        mxp_setup_hint = r + 1u;
        if (muted)
            TEXT(c, FONT, 104, y, 0, "MUTE");
        else if (full_for(r))
            TEXT(c, FONT, 104, y, 0, "FULL");
        else
            TEXT(c, FONT, 104, y, 0, "%d/%d", (int)used_of(r), (int)MXS_PLACES);
    }
}

/* LOCKS: this parameter's p-locks on the UI track's pattern (the pool's record of that slot and track, in RAM its
 * head is the mirror slot), as the moving layer shows them */
static void locks_dyn(struct mxp_dyn *st)
{
    u32 ctx = TRACK_CTX(APP()), len, cur, page;
    const u8 *table = lock_pool(), *rec = 0;
    st->shown = st->len = st->cur = st->page = st->cells = st->pages = 0;
    if (!ctx)
        return;
    len = PATTERN_LEN(ctx);
    if (!table || !len)
        return;
    if (len > 128u)
        len = 128u;
    u32 shift = 0, mask = 0xFFFFu;                      /* (2026-11-20) an insert's knob: its kind's record of ours, the
                                                         * slot's byte of each step */
    int ins = P.slot >= INS_DEST && P.slot < INS_DEST + INS_N;
    if (ins) {
        rec = sl_ins_record(table, P.track, (P.slot - INS_DEST) % 7u);
        shift = 8u * ((P.slot - INS_DEST) / 7u);
        mask = 0xFFu;
    }
    for (u32 i = 0; i < LOCK_RECS && !rec && !ins; i++)
        if (table[LOCK_REC * i] == P.slot && table[LOCK_REC * i + 1] == P.track)
            rec = table + LOCK_REC * i;
    cur = TRACK_CUR[P.track] % len;
    page = cur >> 4;
    st->shown = 1;
    st->len = (s32)len;
    st->cur = (s32)cur;
    st->page = (s32)page;
#define LOCKED(st) (((u32)*(const u16 *)(rec + 2 + 2 * (st)) >> shift & mask) != mask)
    for (u32 s = 0; rec && s < 16u; s++)
        if (16u * page + s < len && LOCKED(16u * page + s))
            st->cells |= 1 << s;
    for (u32 s = 0; rec && s < len; s++)
        if (LOCKED(s))
            st->pages |= 1 << (s >> 4);
#undef LOCKED
}

static void locks_draw(void *c, const struct mxp_dyn *st)
{
    if (!st->shown)
        return;
    for (int s = 0; s < 16; s++) {                      /* the page playing */
        int step = 16 * st->page + s, x = 30 + 4 * s;
        if (step >= st->len)
            continue;
        if (st->cells >> s & 1)
            fill(c, x, 3, x + 2, 6, 1);
        else
            px(c, x + 1, 4);
        if (step == st->cur)
            fill(c, x, 1, x + 2, 1, 1);
    }
    for (int pg = 0; pg < (st->len + 15) / 16; pg++) {  /* a tick a page */
        int x = 98 + 3 * pg;
        fill(c, x, st->pages >> pg & 1 ? 3 : 5, x + 1, 6, 1);
        if (pg == st->page)
            fill(c, x, 1, x + 1, 1, 1);
    }
}

/* (2026-11-21, the User: "keep it slow update, low CPU") a row with no route: its source's level now, worked out every
 * other pass of the moving layer (7.5 a second), whatever it is, and held between */

static s32 source_now(u32 r, s32 v)                     /* row R's source on voice V, in the bars' units (0x7ffe full) */
{
    s32 x;
    if (r < OWN_ROWS)
        return mx_route_level((u32)v, r) >> 16;
    x = mod_value(r - OWN_ROWS, (u32)v);
    return x > DEP_TOP ? DEP_TOP : x < -DEP_TOP ? -DEP_TOP : x;
}

/* the moving layer now: each laid-out bar's live offset (on the voice the track last played), the dimmed levels (ALL:
 * now, else on even passes), LOCKS, the word */
static void mxp_dyn(struct mxp_dyn *st, int all)
{
    s32 v = sl_lastv[P.track];
    int live = v >= 0 && v < 16 && OWNER[v] == P.track;
    for (int i = 0; i < SHOWN; i++) {
        const struct mxp_place *p = &place[i];
        s32 now = 0;
        if (live && p->kind == 1)                       /* 32-bit: |d| < 2^14 */
            now = (p->d * (mx_route_level((u32)v, (u32)p->r) >> 16)) >> 15;
        else if (live && p->kind == 2) {
            now = ((mod_value((u32)p->r - OWN_ROWS, (u32)v) >> 4) * p->d) >> 8;
            now = now > DEP_TOP ? DEP_TOP : now < -DEP_TOP ? -DEP_TOP : now;
        }
        if (p->kind == 3) {
            if (all) {
                dim_o[i] = live ? offset_px(p, source_now((u32)p->r, v)) : 0;
                mxp_dims++;
            }
            st->o[i] = dim_o[i];
        } else
            st->o[i] = p->kind ? offset_px(p, now) : 0;
    }
    locks_dyn(st);
    st->say = P.say && (int)(P.say_at - FRAMES_NOW) > 0;
}

static void dyn_draw(void *c, const struct mxp_dyn *st)  /* the moving layer, then the lit row inverted */
{
    for (int i = 0; i < SHOWN; i++)
        if (place[i].kind == 3) {                       /* a dimmed level: every other pixel of the row's middle line */
            const struct mxp_place *p = &place[i];
            int z = p->both ? (p->x0 + p->x1) / 2 : p->x0, o = st->o[i];
            if (o)
                mxp_dotted(c, o < 0 ? z + o : z, p->y + 2, o < 0 ? z : z + o, p->y + 2);
        } else if (place[i].kind)
            bar_offset(c, &place[i], st->o[i]);
    locks_draw(c, st);
    if (lit_y >= 0)
        mxp_invert(c, 0, lit_y - 1, 127, lit_y + 7);
}

/* the frame made again in FRONT (the still layer, the moving one), its rows 0..53 copied into BACK (the glass's frame)
 * where they differ, and those groups sent */
static void alone(const struct mxp_dyn *st)
{
    u8 *front = FB_FRONT, *back = FB_BACK;
    volatile u32 *f = (volatile u32 *)front;
    for (int k = 0; k < 2 * 128; k++)
        f[k] = still[k];
    u32 canvas[8];
    CANVAS_NEW(canvas, 128, 64, front, CANVAS_AID);
    dyn_draw(canvas, st);
    u32 sent0 = 0, sent1 = 0, sent2 = 0, sent3 = 0;     /* the 128 groups changed (no array: no memset) */
    for (int x = 0; x < 128; x++)
        for (int pg = 0; pg < 7; pg++) {                /* pages 0..6: rows 0..55, of page 6 rows 48..53 only */
            u8 *q = back + 8 * x + pg;
            u8 m = pg < 6 ? 0xFFu : 0xFCu, nw = (u8)((*q & ~m) | (front[8 * x + pg] & m));
            if (nw == *q)
                continue;
            *q = nw;
            u32 g = (u32)(x >> 3) + 16u * (u32)pg, bit = 1u << (g & 31);
            if (g < 32u) sent0 |= bit;
            else if (g < 64u) sent1 |= bit;
            else if (g < 96u) sent2 |= bit;
            else sent3 |= bit;
        }
    int n = 0;
    for (u32 g = 0; g < 128u; g++) {
        u32 word = g < 32u ? sent0 : g < 64u ? sent1 : g < 96u ? sent2 : sent3;
        if (!(word & (1u << (g & 31))))
            continue;
        u32 col = 8u * (g & 15u), page = g >> 4;
        u8 bytes[8];
        for (u32 k = 0; k < 8u; k++)
            bytes[k] = back[8u * (col + k) + page];
        GLASS_GROUP(col, page, bytes);
        n++;
    }
    if (n)
        GLASS_SHOW();
    mxp_groups += (u32)n;
}

void mxp_draw(void *c)
{
    if (!P.up)
        return;
    fill(c, 0, 0, 127, 63, 0);
    if (P.iname)                                        /* (2026-11-20) an insert's knob: INSERT 1's or 2's, its label */
        TEXT(c, FONT, 2, 57, 0, "INSERT %d %.8s", (int)((P.slot - INS_DEST) / 7u) + 1, P.iname);
    else {
        const char *const *nm = (const char *const *)((const u8 *)RECORD(P.rid) + 0x30);
        TEXT(c, FONT, 2, 57, 0, "%s%.8s", P.slot >= E2_DEST ? "ENV2 " : "", *nm ? *nm : "");
    }
    if (note_opens != mxp_opens) {                      /* taken once an open, from the page drawn under it */
        note_opens = mxp_opens;
        mxp_per_note = (u32)note_of(P.rid);
    }
    if (mxp_per_note)
        TEXT(c, FONT, 86, 57, 0, "PER NOTE");          /* (2026-11-20) a control read only at the note's start */
    for (int x = 0; x <= 127; x += 2)
        px(c, x, 55);
    u32 top = mxp_lit < SHOWN ? 0u : mxp_lit - (SHOWN - 1u);
    mxp_setup_rows = 0;
    mxp_setup_hint = 0;
    mxp_rows_drawn = 0;
    lit_y = -1;
    for (u32 pl = top; pl < top + SHOWN; pl++) {        /* PL the place on screen, R its source: the still layer */
        u32 r = SRC(pl);
        int i = (int)(pl - top), y = 46 - 9 * i, where, at;
        place[i].kind = 0;
        if (pl == mxp_lit)
            lit_y = y;
        if (r >= OWN_ROWS) {
            mod_row(c, i, r, y, pl == mxp_lit);
            continue;
        }
        u32 dep = row_depth(r, &where, &at);
        const u16 *ic = ICON[7];
        if (r < 3u) {
            u32 w = stock_get(P.track, 79u + 10u * r) >> 8;     /* LFOn WAVE (records 79, 89, 99) */
            ic = ICON[w < 7u ? w : 0u];
        }
        icon(c, 1, y, ic);
        TEXT(c, FONT, 13, y, 0, "%s", NAME[r]);
        int muted = row_muted(r);
        if (where && dep != NONE) {                     /* a route; at depth 0 the row is empty, as with none */
            s32 d = (s32)dep - NONE;
            TEXT(c, FONT, 38, y, 0, "%+d", d / 0x100);
            if (muted)                                  /* muted: its depth kept, the bar dotted, nothing applied */
                bar_muted(c, y + 1, 58, 98, d, r < 3u);
            else {
                bar(c, y + 1, 58, 98, d, r < 3u);
                lay(i, 1, r, y + 1, 58, 98, r < 3u, d);
            }
            mxp_rows_drawn |= 1u << r;
        } else if (!where || dep == NONE)               /* (2026-11-21) no route: the source's level, dimmed */
            lay(i, 3, r, y + 1, 58, 98, r < 3u, 0);
        if (pl == mxp_lit) {
            if (muted)
                TEXT(c, FONT, 104, y, 0, "MUTE");
            else if (full_for(r))
                TEXT(c, FONT, 104, y, 0, "FULL");
            else
                TEXT(c, FONT, 104, y, 0, "%d/%d", (int)used_of(r), r < 3u ? LFO_CAP : ENV_CAP);
        }
    }
    struct mxp_dyn st;
    mxp_dyn(&st, 1);
    if (st.shown)
        TEXT(c, FONT, 1, 1, 0, "LOCKS");
    const int *cv = (const int *)c;
    still_ok = !st.say && cv[1] == 128 && cv[2] == 64 && cv[3] == 2;
    if (still_ok) {                                     /* the still layer kept (the word on screen: never alone) */
        const u32 *bits = (const u32 *)cv[4];
        volatile u32 *k = still;
        for (int w = 0; w < 2 * 128; w++)
            k[w] = bits[w];
    }
    dyn_draw(c, &st);
    dyn_copy(&drawn, &st);
    drew_buf = CANVAS_BUF(c);
    if (st.say) {                                       /* what a key did */
        fill(c, 28, 24, 99, 38, 0);
        TEXT(c, FONT, 34, 28, 0, "%s", P.say);
        mxp_invert(c, 28, 24, 99, 38);
    }
}
