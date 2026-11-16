/* The routes popup: "the routes into this knob" (the User, 2026-11-11: FUNC + push opens it, FUNC + long push resets
 * the parameter; layout A, the moving bar; docs/matrix.md, scratch/modulation/dest-knob.md §1, §7). OS 1.12.
 *
 * FUNC held, an encoder pushed on a sound page: the press is ours. Let go within 0.4 s: the popup opens on that knob's
 * parameter. Still held at 0.6 s: the parameter goes back to its record's default (stock's own setValue). Between
 * the two, nothing.
 *
 * The popup covers the screen. A slim header with the parameter's name; a row a source: LFO1-3, ENV1, ENV2 (MOD
 * SETUP's sources are the next step). A row at depth 0 is an empty line (its icon and name); a
 * route shows its depth and the moving bar: the outline is the reach (0 to the depth, and to minus it for an LFO,
 * which swings both ways), a tall tick the depth, the solid bar the offset the source applies now, on the voice the
 * track last played. The lit row's count: the LFOs' shared pool ("13/16", FULL when it is full and this LFO has no
 * route here), an envelope's own four ("2/4", FULL). At the bottom, LOCKS: this parameter's p-locks on the track's
 * pattern, the 16 steps of the page playing (a filled cell a locked step, the playing step underlined), then a tick
 * a page (filled when the page holds a lock, the page playing underlined); the dest-knob study §6.
 *
 * Turning the knob sets the lit row's depth, live; push-and-turn (or UP / DOWN) moves the lit row. A row turned from 0
 * makes the route: an LFO's stock route 1 first when it is free (DEST, DEP: stock's parameters, so a stock unit plays
 * it), else a route of the record; a route left at 0 is removed when the popup closes. Closed and kept: the same
 * knob pushed, YES, FUNC + push, any key that leaves (it then does what it does), another knob turned (it then turns
 * that knob), 6 s untouched. NO closes and undoes every change the popup made.
 *
 * Refused (the push goes to stock as before): a trig or TRK held, a stock question up, a page of ours up, a MIDI
 * track, a parameter that is no sound parameter of the voice row (slots 25..100).
 */
#include "../wishes/wish.h"

typedef signed char s8;
typedef short s16;

#define SET_PIXEL  ((void (*)(void *, int, int, int))0x40113E70u)
#define TEXT       ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573C)
#define SET_DIRTY  ((void (*)(void *))0x4011D5DEu)
#define FRAMES_NOW (*(volatile u32 *)0x4058F8D4u)       /* 1,500 a second */
#define FONT       0x44508ED8u                          /* the grid's label font (popup.c's) */
#define RECORD(id) ((const int *)(0x401F83A4u + 60u * (id)))   /* +4 slot, +16 default, +0x30 its short name */
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
#define REDRAW     60u                                  /* 25 a second while up (the moving bar) */
#define ROWS       5
#define LFO_CAP    16
#define ENV_CAP    4
#define NONE       0x4000
#define DEP_TOP    0x7FFE

/* our C (rec.c, matrix.c, popup.c, slides) */
extern int smp_func_held;
extern u32 smp_held_lo, smp_held_hi;
extern int smp_question_up(void);
extern int smp_overlay_dirty;
extern s8 sl_lastv[16];
extern int rec_overlay;
extern int amp_sub;
extern int ins_visible(void);
int mx_route_level(u32 v, u32 src);                    /* matrix.c: a source's value on voice V, 1.31 */

static const char *const NAME[ROWS] = {"LFO1", "LFO2", "LFO3", "ENV1", "ENV2"};
static const u8 DEST_REC[3] = {78, 88, 98};             /* LFO1-3 DEST and DEP (stock's records) */
static const u8 DEP_REC[3] = {83, 93, 103};

static struct {
    int up;                                             /* the popup is up */
    u32 knob;                                           /* 0 A .. 7 H */
    u32 rid, slot, track;                               /* its parameter, the row slot it is, the track */
    u32 lit, last;                                      /* the lit row; the frame of the last touch */
    u32 push_at, push_k;                                /* FUNC + push: when, which encoder (+1; 0 none) */
    int reset_done;
    int turned;                                         /* the lit knob turned while pushed (push-and-turn) */
    u8 undo_routes[4 * 23 + 8];                         /* the record's routes when it opened */
    int undo_n;
    u16 undo_dest[3], undo_dep[3];                      /* stock's route 1 of each LFO when it opened */
    u32 next_draw;
} P D_;

/* the checks' counters: FUNC + pushes taken, popups opened, opens refused and why (1 no parameter, 2 refused here,
 * 3 not a sound parameter of the row) */
u32 mxp_pushes D_ = 0, mxp_opens D_ = 0, mxp_refusals D_ = 0, mxp_why D_ = 0, mxp_rid D_ = 0;
u32 mxp_turns D_ = 0, mxp_keys D_ = 0;               /* knob turns and key presses taken while up */
int mxp_detents D_ = 0;                                 /* their detents, summed (the checks) */

/* the page's eight places as the last draw left them (page.c wr_cell): record ids, 0 none */
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

static int routes_get(u32 t, u8 *v)                     /* -> bytes */
{
    int n = wish_get(sound_of(t), WT_MX_ROUTES, v, 4u * 23u + 8u);
    return n < 0 ? 0 : n;
}

/* the row's depth into this slot (NONE: no route), and where it is: 1 stock's route 1, 2 the record's, 0 none */
static u32 row_depth(u32 r, int *where, int *at)
{
    u8 v[4 * 23 + 8];
    int n = routes_get(P.track, v);
    *where = 0;
    *at = -1;
    if (r < 3u && stock_get(P.track, DEST_REC[r]) >> 8 == P.slot) {
        *where = 1;
        return stock_get(P.track, DEP_REC[r]);
    }
    for (int i = 0; i + 4 <= n; i += 4)
        if (v[i] == r && v[i + 1] == P.slot) {
            *where = 2;
            *at = i;
            return (u32)v[i + 2] << 8 | v[i + 3];
        }
    return NONE;
}

/* routes in use: the LFOs' shared pool (stock's route 1s and the record's) or an envelope's */
static u32 used_of(u32 r)
{
    u8 v[4 * 23 + 8];
    int n = routes_get(P.track, v);
    u32 c = 0;
    if (r < 3u) {
        for (u32 l = 0; l < 3u; l++)
            c += stock_get(P.track, DEST_REC[l]) >> 8 != 0u;
        for (int i = 0; i + 4 <= n; i += 4)
            c += v[i] < 3u;
    } else
        for (int i = 0; i + 4 <= n; i += 4)
            c += v[i] == r;
    return c;
}

static int full_for(u32 r)
{
    int where, at;
    if (row_depth(r, &where, &at) != NONE || where)
        return 0;
    return used_of(r) >= (r < 3u ? LFO_CAP : ENV_CAP);
}

static void record_put(u8 *v, int n)
{
    wish_put(sound_of(P.track), WT_MX_ROUTES, v, (u32)n);
}

/* the lit row's depth set to DEP */
static void set_depth(u32 r, u32 dep)
{
    u8 v[4 * 23 + 8];
    int where, at, n = routes_get(P.track, v);
    row_depth(r, &where, &at);
    if (where == 1) {
        stock_set(P.track, DEP_REC[r], dep);
        return;
    }
    if (where == 2) {
        v[at + 2] = (u8)(dep >> 8);
        v[at + 3] = (u8)dep;
        record_put(v, n);
        return;
    }
    if (dep == NONE || full_for(r))
        return;
    if (r < 3u && !(stock_get(P.track, DEST_REC[r]) >> 8)) {     /* route 1 first: a stock unit plays it */
        stock_set(P.track, DEST_REC[r], P.slot << 8);
        stock_set(P.track, DEP_REC[r], dep);
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
    u8 v[4 * 23 + 8];
    int n = routes_get(P.track, v), m = 0;
    for (u32 l = 0; l < 3u; l++)
        if (stock_get(P.track, DEST_REC[l]) >> 8 == P.slot && stock_get(P.track, DEP_REC[l]) == NONE)
            stock_set(P.track, DEST_REC[l], 0);
    for (int i = 0; i + 4 <= n; i += 4)
        if (!(v[i + 1] == P.slot && ((u32)v[i + 2] << 8 | v[i + 3]) == NONE))
            for (int b = 0; b < 4; b++)
                v[m++] = v[i + b];
    if (m != n)
        record_put(v, m);
}

static void undo(void)
{
    for (u32 l = 0; l < 3u; l++) {
        stock_set(P.track, DEST_REC[l], P.undo_dest[l]);
        stock_set(P.track, DEP_REC[l], P.undo_dep[l]);
    }
    record_put(P.undo_routes, P.undo_n);
}

/* --- open, close, the keys -------------------------------------------------------------------- */
static int refused(u32 t)
{
    return (smp_held_lo >> 25 & 0xFFFFu) != 0u                /* a trig held */
           || smp_question_up() || rec_overlay || amp_sub || ins_visible() || midi_track(t);
}

static void open(u32 k)
{
    u32 rid = knob_rid(k), t = UI_TRACK & 15u, slot;
    mxp_rid = rid;
    mxp_why = !rid ? 1u : refused(t) ? 2u : 0u;
    slot = rid ? (u32)RECORD(rid)[1] : 0u;
    if (!mxp_why && (slot < 25u || slot > 100u))
        mxp_why = 3u;
    if (mxp_why) {
        mxp_refusals++;
        return;
    }
    P.knob = k;
    P.rid = rid;
    P.slot = slot;
    P.track = t;
    P.lit = 0;
    P.undo_n = routes_get(t, P.undo_routes);
    for (u32 l = 0; l < 3u; l++) {
        P.undo_dest[l] = (u16)stock_get(t, DEST_REC[l]);
        P.undo_dep[l] = (u16)stock_get(t, DEP_REC[l]);
    }
    P.last = FRAMES_NOW;
    P.up = 1;
    mxp_opens++;
    smp_overlay_dirty = 1;
}

static void close(int keep)
{
    if (!P.up)
        return;
    if (keep)
        drop_zeros();
    else
        undo();
    P.up = 0;
    smp_overlay_dirty = 1;
}

int mxp_visible(void)
{
    return P.up;
}

/* rec.c smp_ui_pop, before the overlays: -> 1 when the item is ours (dropped) */
int mxp_pop(u8 *it)
{
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int press = (flags & F_PRESS) && !(flags & F_RELEASE), release = (flags & F_RELEASE) != 0;

    if (it[0] == IT_KEY && code >= K_PUSH0 && code < K_PUSH0 + 8u) {
        u32 k = code - K_PUSH0;
        if (press && smp_func_held) {                   /* FUNC + push: ours; told apart on its release */
            if (P.up) {
                close(1);
                return 1;
            }
            P.push_at = FRAMES_NOW;
            P.push_k = k + 1u;
            mxp_pushes++;
            P.reset_done = 0;
            return 1;
        }
        if (release && P.push_k == k + 1u) {
            u32 held = FRAMES_NOW - P.push_at;
            P.push_k = 0;
            if (!P.reset_done && held < TAP)
                open(k);
            return 1;
        }
        if (P.up && k == P.knob) {                      /* the same knob pushed and let go, no turn: closed, kept */
            if (press)
                P.turned = 0;
            else if (release && !P.turned)
                close(1);
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
            close(1);
            return 0;
        }
        if (smp_held_hi >> (K_PUSH0 - 32 + P.knob) & 1u) {     /* push-and-turn: the lit row moves */
            P.turned = 1;
            int r = (int)P.lit + (d > 0 ? 1 : d < 0 ? -1 : 0);
            P.lit = (u32)(r < 0 ? 0 : r >= ROWS ? ROWS - 1 : r);
        } else {
            int where, at;
            int dep = (int)row_depth(P.lit, &where, &at) + d * 0x100;
            dep = dep < 0 ? 0 : dep > DEP_TOP ? DEP_TOP : dep;
            set_depth(P.lit, (u32)dep);
        }
        smp_overlay_dirty = 1;
        return 1;
    }
    if (it[0] == IT_KEY && press) {
        mxp_keys++;
        if (code == K_ARROW_UP || code == K_ARROW_DN) {
            int r = (int)P.lit + (code == K_ARROW_DN ? 1 : -1);
            P.lit = (u32)(r < 0 ? 0 : r >= ROWS ? ROWS - 1 : r);
            smp_overlay_dirty = 1;
            return 1;
        }
        if (code == K_YES || code == K_NO) {
            close(code == K_YES);
            return 1;
        }
        if (code == K_FUNC)
            return 0;                                   /* FUNC: held for the next FUNC + push */
        close(1);                                       /* a key that leaves: kept, and the key does its work */
        return 0;
    }
    return code == K_ARROW_UP || code == K_ARROW_DN || code == K_YES || code == K_NO;   /* their releases */
}

/* page.c wr_poll: the long push's reset; while up, closing on its own and the moving bar's redraws */
void mxp_poll(void *screen)
{
    if (P.push_k && !P.reset_done && FRAMES_NOW - P.push_at >= LONG) {
        u32 k = P.push_k - 1u, rid = knob_rid(k), t = UI_TRACK & 15u;
        P.reset_done = 1;
        if (rid && !refused(t))
            stock_set(t, rid, (u32)RECORD(rid)[4]);     /* the record's default, as stock's setValue writes it */
    }
    if (!P.up)
        return;
    if ((UI_TRACK & 15u) != P.track || smp_question_up() || FRAMES_NOW - P.last >= IDLE) {
        close(1);
        return;
    }
    if ((int)(FRAMES_NOW - P.next_draw) >= 0) {
        P.next_draw = FRAMES_NOW + REDRAW;
        SET_DIRTY(screen);
    }
}

/* --- drawing (the canvas counts y up from the bottom) ------------------------------------------ */
static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
}

static void invert(void *c, int x0, int y0, int x1, int y1)  /* as popup.c's */
{
    const int *cv = (const int *)c;
    u32 *bits = (u32 *)cv[4];
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            if (x >= 0 && y >= 0 && x < cv[1] && y < cv[2])
                bits[x * cv[3] + (y >> 5)] ^= 0x80000000u >> (y & 31);
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
                SET_PIXEL(c, x + b, y + 6 - r, 1);
}

/* the moving bar in [x0, x1], its 0 at Z: the reach outline, the depth's tick, the live offset */
static void bar(void *c, int y, int x0, int x1, s32 depth, int both, s32 now)
{
    int z = both ? (x0 + x1) / 2 : x0, half = both ? (x1 - x0) / 2 : x1 - x0;
    int d = (int)((depth * half) / 0x7FFE), o = (int)((now * half) / 0x7FFE);
    int a = z - (both ? (d < 0 ? -d : d) : (d < 0 ? -d : 0)), b = z + (d < 0 ? (both ? -d : 0) : d);
    if (b > a) {                                        /* the outline: the reach */
        fill(c, a, y, b, y, 1);
        fill(c, a, y + 4, b, y + 4, 1);
        fill(c, a, y, a, y + 4, 1);
        fill(c, b, y, b, y + 4, 1);
    }
    fill(c, z + d, y - 1, z + d, y + 5, 1);             /* the depth's tick */
    if (o)                                              /* the offset applied now */
        fill(c, o < 0 ? z + o : z, y + 1, o < 0 ? z : z + o, y + 3, 1);
}

/* LOCKS: this parameter's p-locks on the UI track's pattern (the pool's record of that slot and track, in RAM its
 * head is the mirror slot) */
static void locks_strip(void *c)
{
    u32 ctx = TRACK_CTX(APP()), len, cur, page;
    if (!ctx)
        return;
    void *model = *(void **)(ctx + 44);
    u32 t = *(u32 *)(ctx + 60);
    if (!model || t != P.track)
        return;
    const u8 *table = (const u8 *)((u32 (*)(void *))((*(void ***)model)[10]))(model), *rec = 0;
    len = PATTERN_LEN(ctx);
    if (!table || !len)
        return;
    if (len > 128u)
        len = 128u;
    for (u32 i = 0; i < LOCK_RECS && !rec; i++)
        if (table[LOCK_REC * i] == P.slot && table[LOCK_REC * i + 1] == t)
            rec = table + LOCK_REC * i;
    cur = TRACK_CUR[t] % len;
    page = cur >> 4;
    TEXT(c, FONT, 1, 1, 0, "LOCKS");
    for (u32 s = 0; s < 16u; s++) {                     /* the page playing */
        u32 step = 16u * page + s;
        int x = 30 + 4 * (int)s;
        if (step >= len)
            continue;
        if (rec && *(const u16 *)(rec + 2 + 2 * step) != 0xFFFF)
            fill(c, x, 3, x + 2, 6, 1);
        else
            SET_PIXEL(c, x + 1, 4, 1);
        if (step == cur)
            fill(c, x, 1, x + 2, 1, 1);
    }
    for (u32 pg = 0; pg < (len + 15u) / 16u; pg++) {    /* a tick a page */
        int x = 98 + 3 * (int)pg, any = 0;
        for (u32 s = 16u * pg; rec && s < 16u * pg + 16u && s < len; s++)
            any |= *(const u16 *)(rec + 2 + 2 * s) != 0xFFFF;
        fill(c, x, any ? 3 : 5, x + 1, 6, 1);
        if (pg == page)
            fill(c, x, 1, x + 1, 1, 1);
    }
}

void mxp_draw(void *c)
{
    if (!P.up)
        return;
    fill(c, 0, 0, 127, 63, 0);
    const char *const *nm = (const char *const *)((const u8 *)RECORD(P.rid) + 0x30);
    TEXT(c, FONT, 2, 57, 0, "%.8s", *nm ? *nm : "");
    for (int x = 0; x <= 127; x += 2)
        SET_PIXEL(c, x, 55, 1);
    s32 v = sl_lastv[P.track];
    int live = v >= 0 && v < 16 && OWNER[v] == P.track;
    for (u32 r = 0; r < ROWS; r++) {
        int y = 46 - 9 * (int)r, where, at;
        u32 dep = row_depth(r, &where, &at);
        const u16 *ic = ICON[7];
        if (r < 3u) {
            u32 w = stock_get(P.track, 79u + 10u * r) >> 8;     /* LFOn WAVE (records 79, 89, 99) */
            ic = ICON[w < 7u ? w : 0u];
        }
        icon(c, 1, y, ic);
        TEXT(c, FONT, 13, y, 0, "%s", NAME[r]);
        if (where || r == P.lit) {
            s32 d = (s32)dep - NONE;
            TEXT(c, FONT, 38, y, 0, "%+d", d / 0x100);
            s32 now = live ? (d * (mx_route_level((u32)v, r) >> 16)) >> 15 : 0;   /* 32-bit: |d| < 2^14 */
            bar(c, y + 1, 58, 98, d, r < 3u, now);
        }
        if (r == P.lit) {
            if (full_for(r))
                TEXT(c, FONT, 104, y, 0, "FULL");
            else
                TEXT(c, FONT, 104, y, 0, "%d/%d", (int)used_of(r), r < 3u ? LFO_CAP : ENV_CAP);
            invert(c, 0, y - 1, 127, y + 7);
        }
    }
    locks_strip(c);
}
