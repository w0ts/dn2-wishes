/* An LFO's routes, as the popups read and write them (the User, 2026-11-18: "i would not use the stock modulation
 * destination, we keep it just for backward compatibility ... we save the first one of modulation, it is for
 * compatibility with stock"; design B, "neutralise and mirror"). OS 1.12, LFO1-3.
 *
 * Our matrix is the only source of an LFO's routes; stock's DEST and DEP are the copy of its FIRST route, kept in the
 * sound so that a stock unit, Overbridge and the plugin read the main route as stock does:
 *   - an LFO's first route IS its DEST and DEP (the sound's own cells): a sound loaded with DEST set has its first
 *     route at once (nothing written: an unmodified project stays as it is, byte for byte), and an outside change of
 *     DEST or DEP (a load, the plugin, CC, Overbridge, a DEP or DEST p-lock) is the first route's change;
 *   - its other routes are the record's (WT_MX_ROUTES, matrix.c), 4 bytes each;
 *   - a muted first route keeps DEST and DEP (it is saved as it is: a stock unit plays it) and gets the record's mark
 *     MX_FIRST | MX_MUTED with its LFO and the DEST it muted; each frame, the voices playing that track's sound then
 *     see DEST none for that LFO (matrix.c mx_dmask, hooks.S mods_fast: after MOD SETUP). The mark belongs to that route: a DEST moved from outside plays, put back it is muted again;
 *     a sound-locked voice is not muted;
 *   - live, the first route is added by stock's evaluator from the voice row's DEST and DEP cells, LFO3, LFO2, LFO1,
 *     then the record's routes (mx_eval): the order and the arithmetic of stock's route 1, so a sound without routes
 *     of ours plays bit for bit as before.
 * When an LFO's first route goes (deleted, turned to 0), its next route of the record takes its place in DEST and DEP
 * (its mute as the mark), so the sound keeps its main route on stock firmware. A DEST into an LFO's controls (slots
 * 1..24, LFO4's 101..108) has no route of the record (it would land after that LFO read it): it can only be a first
 * route, it cannot be muted.
 */
#include "../wishes/wish.h"
#include "routes.h"

typedef signed char s8;


#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))   /* +4 slot, +16 default */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_OWNER   ((u32 (*)(void))0x4018AC5Au)
#define PARAM_SET  ((u32 (*)(u32, u32, u32))0x40041A40u)
#define SET_VALUE  ((u32 (*)(u32, u32, u32, u32, u32, u32, u32))0x40037326u)

const u8 mxr_dest_rec[3] = {78, 88, 98};                /* LFO1-3 DEST, DEP (stock's records) */
const u8 mxr_dep_rec[3] = {83, 93, 103};

u32 mxr_sound(u32 t)
{
    u8 *kit = KIT_POINTER;
    return kit && t < 16u ? (u32)kit + 52u + 1163u * t : 0u;
}

u32 mxr_stock(u32 t, u32 rid)                           /* the sound's stored value of a stock record */
{
    u32 s = mxr_sound(t);
    return s ? *(const u16 *)(s + 20u + 2u * (u32)RECORD(rid)[1]) : 0u;   /* the sound's cells: +20, a word a slot */
}

void mxr_stock_set(u32 t, u32 rid, u32 value)           /* as a knob writes it (stock's setValue) */
{
    u32 owner = UI_OWNER(), ps;
    if (!owner || !(ps = PARAM_SET(owner, rid, t)))
        return;
    SET_VALUE(ps, rid, value, t, 0, 0, 1);
}

int mxr_get(u32 t, u8 *v)                               /* the record's routes into V (MXR_BUF) -> bytes */
{
    int n = wish_get(mxr_sound(t), WT_MX_ROUTES, v, MXR_BUF);
    return n < 0 ? 0 : n > (int)MXR_BUF ? (int)MXR_BUF & ~3 : n & ~3;
}

void mxr_put(u32 t, const u8 *v, int n)
{
    wish_put(mxr_sound(t), WT_MX_ROUTES, v, (u32)n);
}

u32 mxr_dest(u32 t, u32 l)
{
    return l < 3u ? mxr_stock(t, mxr_dest_rec[l]) >> 8 : 0u;
}

/* (2026-11-19, the User: DEP is the LFO's global attenuverter; atten.c) LFO L's first route's own depth: the record's
 * (WT_MX_LFO) on a converted sound; on one not converted (its record not read yet, locked) DEP is still its depth */
extern int mxa_is_converted(u32 sound);  /* (2026-11-21) only the UI pass converts (with the table: matrix.c mx_poll) */
u32 mxr_first_dep(u32 t, u32 l)
{
    u8 f[12];
    u32 s = mxr_sound(t);
    if (l > 2u || !s)
        return MXR_NONE;
    if (!mxa_is_converted(s) || wish_get(s, WT_MX_LFO, f, sizeof f) < (int)(4u * l + 4u))
        return mxr_stock(t, mxr_dep_rec[l]);
    return (u32)f[4u * l + 2u] << 8 | f[4u * l + 3u];
}

void mxr_first_set(u32 t, u32 l, u32 dep)
{
    u8 f[12];
    u32 s = mxr_sound(t);
    if (l > 2u || !s)
        return;
    if (!mxa_is_converted(s) || wish_get(s, WT_MX_LFO, f, sizeof f) != (int)sizeof f) {
        mxr_stock_set(t, mxr_dep_rec[l], dep);          /* not converted: DEP is its depth, as stock's */
        return;
    }
    f[4u * l + 2u] = (u8)(dep >> 8);
    f[4u * l + 3u] = (u8)dep;
    wish_put(s, WT_MX_LFO, f, sizeof f);
}

int mxr_is_mark(const u8 *e)
{
    return (e[0] & (MXR_MUTED | MXR_FIRST)) == (MXR_MUTED | MXR_FIRST);
}

int mxr_mark_at(const u8 *v, int n, u32 l)              /* LFO L's mark (its first route muted): its byte, -1 none */
{
    for (int i = 0; i + 4 <= n; i += 4)
        if (mxr_is_mark(v + i) && (v[i] & 3u) == l)
            return i;
    return -1;
}

int mxr_first_muted(u32 t, u32 l)                       /* the mark names the first route DEST is now (a DEST moved
                                                         * from outside is a new route: it plays, matrix.c mx_dmask) */
{
    u8 v[MXR_BUF];
    u32 s = mxr_dest(t, l);
    int at = l < 3u && s ? mxr_mark_at(v, mxr_get(t, v), l) : -1;
    return at >= 0 && v[at + 1] == s;
}

int mxr_ctrl_slot(u32 s)                                /* an LFO's control: never a route of the record */
{
    return (s >= 1u && s <= 24u) || (s >= 101u && s <= 108u);
}

int mxr_drop(u8 *v, int n, int at)                      /* the 4 bytes at AT removed -> bytes */
{
    for (int i = at; i + 4 < n; i++)
        v[i] = v[i + 4];
    return n - 4;
}

/* LFO L's first route muted (ON) or not: the record's mark. -> 1 changed, 0 nothing, -1 it cannot be (no first
 * route, or into an LFO's controls) or the record has no room */
int mxr_mute_first(u32 t, u32 l, int on)
{
    u8 v[MXR_BUF + 4];
    u32 s = mxr_dest(t, l);
    if (l > 2u || !s || mxr_ctrl_slot(s))
        return -1;
    int n = mxr_get(t, v), at = mxr_mark_at(v, n, l);
    if ((at >= 0 && v[at + 1] == s) == !!on)            /* (a mark of another DEST: not this route's) */
        return 0;
    if (on) {
        if (at < 0) {
            if (n + 4 > (int)MXR_BUF)
                return -1;
            at = n;
            n += 4;
        }
        u32 dep = mxr_first_dep(t, l);
        v[at] = (u8)(l | MXR_FIRST | MXR_MUTED);
        v[at + 1] = (u8)s;
        v[at + 2] = (u8)(dep >> 8);
        v[at + 3] = (u8)dep;
    } else
        n = mxr_drop(v, n, at);
    mxr_put(t, v, n);
    return 1;
}

/* LFO L's first route gone (DEST 0, its depth none, the mark dropped), then its next route of the record, if any,
 * takes its place (mxr_settle). (2026-11-19) DEP and its p-locks are the LFO's attenuverter: kept */
void mxr_drop_first(u32 t, u32 l)
{
    u8 v[MXR_BUF];
    if (l > 2u)
        return;
    int n = mxr_get(t, v), at = mxr_mark_at(v, n, l);
    if (at >= 0)
        mxr_put(t, v, mxr_drop(v, n, at));
    mxr_stock_set(t, mxr_dest_rec[l], 0);
    mxr_first_set(t, l, MXR_NONE);
    mxr_settle(t, l);
}

/* With LFO L's DEST free: its first route of the record (in the record's order) moves into DEST and DEP, its mute as
 * the mark; with none, a mark left alone goes. -> 1 when a route moved */
int mxr_settle(u32 t, u32 l)
{
    u8 v[MXR_BUF];
    if (l > 2u || mxr_dest(t, l))
        return 0;
    int n = mxr_get(t, v), at = mxr_mark_at(v, n, l);
    if (at >= 0)
        n = mxr_drop(v, n, at);
    for (int i = 0; i + 4 <= n; i += 4) {
        if (mxr_is_mark(v + i) || (v[i] & ~MXR_MUTED) != l || v[i + 1] < 25u || v[i + 1] > 100u)
            continue;
        u32 slot = v[i + 1], dep = (u32)v[i + 2] << 8 | v[i + 3], muted = v[i] & MXR_MUTED;
        if (muted) {                                    /* the mark in the route's place: the same bytes */
            v[i] = (u8)(l | MXR_FIRST | MXR_MUTED);
        } else
            n = mxr_drop(v, n, i);
        mxr_put(t, v, n);
        mxr_first_set(t, l, dep);
        mxr_stock_set(t, mxr_dest_rec[l], slot << 8);
        return 1;
    }
    if (at >= 0)
        mxr_put(t, v, n);
    return 0;
}

/* the routes of the LFOs' shared pool (16): their DESTs and the record's LFO routes (a mark is not a route) */
u32 mxr_pool(u32 t)
{
    u8 v[MXR_BUF];
    int n = mxr_get(t, v);
    u32 c = 0;
    for (u32 l = 0; l < 3u; l++)
        c += mxr_dest(t, l) != 0u;
    for (int i = 0; i + 4 <= n; i += 4)
        c += !mxr_is_mark(v + i) && (v[i] & ~MXR_MUTED) < 3u;
    return c;
}

/* the record's routes (marks left out): all of them, and the LFOs' */
u32 mxr_count(const u8 *v, int n, int lfo_only)
{
    u32 c = 0;
    for (int i = 0; i + 4 <= n; i += 4)
        if (!mxr_is_mark(v + i))
            c += !lfo_only || (v[i] & ~MXR_MUTED) < 3u;
    return c;
}
