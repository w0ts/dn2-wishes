/* MOD SETUP's entries edited from the routes popup (the User, 2026-11-21: "like other rows!"; scratch/setup-rows-design.md,
 * docs/matrix.md "MOD SETUP's rows"). OS 1.12.
 *
 * Stock's own entries, edited through stock's own objects. A sound holds six lists of four {s16 depth, s16 slot} from
 * byte 230, in the order VEL PB MW BC AT KEY (measured 2026-11-21 on stock's six MOD SETUP pages: the page titled MOD
 * WHEEL shows the list at +262, PITCH BEND the one at +246). Each list is a value of the track's sound object (the kit
 * object's +108 + 960 t, stock's 0x40031dc2 loop; 0x4004afec attaches each to its list): VEL's a ModConfig (vtable
 * 0x401df2f8), the five others a ValueWithMirror<modTarget_t[4]> (0x40200478), both the same interface. Its slots, as
 * stock's MOD SETUP page calls them (0x401081d2): +16 setEntry(i, {depth, slot}), +40 setDepth(i, depth) (clamped to
 * -32768 .. 32512), each followed by the value's change (+16 of its own vtable: undo, Overbridge, the mirror) and
 * stock's copy of the sound's 153 MOD SETUP bytes into every voice of the track (0x4002591e). So stock's pages, undo,
 * Overbridge and saving see exactly what the popup did. The object is found from UI_OWNER (+0x160 + 960 t, the kit
 * object's sound objects) and taken only when its storage pointer (+16) is the track's sound and its vtable one of the
 * two: anything else refuses (never met).
 *
 * Mute (the User, 2026-11-21: option A). The entry stays in the sound, untouched: stock firmware plays it. The record
 * holds a mark (WT_MX_SETUP: {list << 2 | place, slot, depth}, 4 bytes a mark) of the entry as it was muted. The voices
 * read MOD SETUP from their own 153-byte copies (0x8000487c + 153 v), which stock writes at two places only: a note
 * (0x4002549c, the sound given to voice v) and an edit (0x4002591e, every voice of the track). Both copy through
 * mxs_copy (setup.S; their `lea memcpy,%a3` point there): the same bytes as stock's copy, but an entry that equals its track's
 * mark lands with depth 0, the kernel then adds nothing (as stock's depth 0). The same work for every copy, muted or
 * not, and nothing added to the frame (mods_fast unchanged). A mark belongs to the entry it muted: an entry changed from
 * outside (stock's page, Overbridge) no longer equals it and plays, put back it is muted again (the comparison is made
 * at each copy). A sound-locked voice (its sound not the kit's) is never muted. */
#include "../wishes/wish.h"
#include "routes.h"
#include "setup.h"

typedef signed char s8;
typedef short s16;

#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define UI_OWNER    ((u32 (*)(void))0x4018AC5Au)
#define PARAM_SET   ((u32 (*)(u32, u32, u32))0x40041A40u)
#define MIRROR_COPY ((u32 (*)(u32, u32))0x4002591Eu)    /* stock: the sound's MOD SETUP into each voice of track T */
#define WALK_END    (*(const u8 *)0x400395B9u)          /* the list builder's slot bound (dest_pop.c) */
#define WT_MX_SETUP 0x0015u
#define SOUND0      0x160u                              /* UI_OWNER's sound objects: + 960 t */
#define SOUND_OBJ   960u
#define VT_VEL      0x401DF2F8u                         /* VEL's interface vtable (ModConfig) */
#define VT_MOD      0x40200478u                         /* the five others' */
#define NONE_REC    19u                                 /* stock's "None" record */
#define SETUP_WANT  0x0200u                             /* the list builder's want for MOD SETUP (0x40107d9c) */

u32 mod_lfo_mask(u32 rec, u32 want);

const u8 mxs_list[MXS_SOURCES] = {0, 2, 1, 4, 3, 5};    /* row VEL MW PB AT BC KEY -> the list */
static const u16 IOFF[MXS_SOURCES] = {80, 220, 372, 676, 524, 828};   /* each row's interface in the sound object */

/* the marks laid out: track t's 24 entries (list-major), each the entry as muted ({depth, slot}), 0 none (an entry 0
 * lands as 0 either way); row 16: no track (a sound not the kit's). Read by mxs_copy (setup.S), in the audio interrupt too */
u32 mxs_mark[17][24] D_;
u32 mxs_copies D_ = 0, mxs_refresh D_ = 0;              /* the checks: copies made (setup.S), voices refreshed */
static int lay(u32 t, u32 sound);

/* --- the entries, read from the sound ------------------------------------------------------- */
static const u8 *list_of(u32 t, u32 j)
{
    u32 s = mxr_sound(t);
    return s && j < MXS_SOURCES ? (const u8 *)(s + 230u + 16u * mxs_list[j]) : 0;
}

int mxs_entry(u32 t, u32 j, u32 p, s32 *depth)
{
    const u8 *l = list_of(t, j);
    *depth = 0;
    if (!l || p >= MXS_PLACES)
        return 0;
    *depth = (s16)(l[4u * p] << 8 | l[4u * p + 1u]);
    return (s16)(l[4u * p + 2u] << 8 | l[4u * p + 3u]);
}

int mxs_find(u32 t, u32 j, u32 slot)
{
    s32 d;
    for (u32 p = 0; p < MXS_PLACES; p++)
        if (slot && (u32)mxs_entry(t, j, p, &d) == slot)
            return (int)p;
    return -1;
}

s32 mxs_sum(u32 t, u32 j, u32 slot, int *n)
{
    s32 d, sum = 0;
    *n = 0;
    for (u32 p = 0; p < MXS_PLACES; p++)
        if (slot && (u32)mxs_entry(t, j, p, &d) == slot) {
            sum += d;
            (*n)++;
        }
    return sum;
}

u32 mxs_used(u32 t, u32 j)
{
    s32 d;
    u32 c = 0;
    for (u32 p = 0; p < MXS_PLACES; p++)
        c += mxs_entry(t, j, p, &d) != 0;
    return c;
}

/* stock's MOD SETUP list offers SLOT: its entry is a record (not None) that passes the list's mask, as stock's
 * builder pushes it (dest_pop.c ldp_valid; our mask hook mod_lfo_mask, as the builder asks it) */
int mxs_offers(u32 t, u32 slot)
{
    u32 owner = UI_OWNER(), obj = owner ? PARAM_SET(owner, mxr_dest_rec[0], t) : 0u;
    if (!obj || slot < 1u || slot >= (u32)WALK_END)
        return 0;
    u32 e = ((u32 (*)(u32, u32))(*(u32 **)obj)[20])(obj, slot);
    return e && e != NONE_REC && !(~mod_lfo_mask(e, SETUP_WANT) & SETUP_WANT);
}

/* --- stock's object -------------------------------------------------------------------------- */
static u32 iface(u32 t, u32 j)
{
    u32 owner = UI_OWNER(), snd = mxr_sound(t);
    if (!owner || !snd || j >= MXS_SOURCES)
        return 0;
    u32 so = owner + SOUND0 + SOUND_OBJ * t, i = so + IOFF[j], vt = *(const u32 *)i;
    if (*(const u32 *)(so + 16u) != snd || vt != (j ? VT_MOD : VT_VEL))
        return 0;
    return i;
}

#define VCALL(i, off) ((void (*)(u32, u32, u32))(*(u32 **)(i))[(off) / 4u])

static int set_entry(u32 t, u32 j, u32 p, u32 slot, s32 w)    /* stock's setEntry: {depth, slot} at once */
{
    u32 i = iface(t, j);
    if (!i)
        return -MXS_NO_OBJ;
    VCALL(i, 16u)(i, p, (u32)w << 16 | (slot & 0xFFFFu));
    return MXS_OK;
}

static int set_depth(u32 t, u32 j, u32 p, s32 w)        /* stock's setDepth (its clamp) */
{
    u32 i = iface(t, j);
    if (!i)
        return -MXS_NO_OBJ;
    VCALL(i, 40u)(i, p, (u32)w);
    return MXS_OK;
}

/* --- the marks -------------------------------------------------------------------------------- */
#define MARKS_MAX (4u * MXS_SOURCES * MXS_PLACES)
static int marks_get(u32 t, u8 *v)
{
    int n = wish_get(mxr_sound(t), WT_MX_SETUP, v, MARKS_MAX);
    return n < 0 ? 0 : n > (int)MARKS_MAX ? (int)MARKS_MAX : n & ~3;
}

static int mark_at(const u8 *v, int n, u32 list, u32 p)
{
    for (int i = 0; i + 4 <= n; i += 4)
        if (v[i] == (u8)(list << 2 | p))
            return i;
    return -1;
}

/* the voices of track T copy the sound again (stock's copy, through mxs_copy): a mark made or gone heard at once */
static void refresh(u32 t)
{
    u32 s = mxr_sound(t);
    if (!s)
        return;
    if (!lay(t, s)) {                                   /* (lay copied when the marks changed) */
        MIRROR_COPY(s, t);
        mxs_refresh++;
    }
}

/* (list, place)'s mark: set to the entry {W, SLOT} (ON), or removed -> 0, or < 0 no room */
static int mark_put(u32 t, u32 j, u32 p, int on, u32 slot, s32 w)
{
    u8 v[MARKS_MAX + 4];
    int n = marks_get(t, v), at = mark_at(v, n, mxs_list[j], p);
    if (!on) {
        if (at < 0)
            return 0;
        for (int i = at; i + 4 < n; i++)
            v[i] = v[i + 4];
        n -= 4;
    } else {
        if (at < 0) {
            if (n + 4 > (int)MARKS_MAX)
                return -MXS_NO_ROOM;
            at = n;
            n += 4;
        }
        v[at] = (u8)(mxs_list[j] << 2 | p);
        v[at + 1] = (u8)slot;
        v[at + 2] = (u8)((u32)w >> 8);
        v[at + 3] = (u8)w;
    }
    if (wish_put(mxr_sound(t), WT_MX_SETUP, v, (u32)n) < 0)
        return -MXS_NO_ROOM;
    return 0;
}

static int place_muted(u32 t, u32 j, u32 p)
{
    u8 v[MARKS_MAX + 4];
    s32 w;
    int slot = mxs_entry(t, j, p, &w), n = marks_get(t, v), at = mark_at(v, n, mxs_list[j], p);
    return at >= 0 && slot && v[at + 1] == (u8)slot && (s16)(v[at + 2] << 8 | v[at + 3]) == w;
}

int mxs_muted(u32 t, u32 j, u32 slot)
{
    int p = mxs_find(t, j, slot);
    return p >= 0 && place_muted(t, j, (u32)p);
}

/* track T's marks from its record: each mark's entry, {depth, slot} as a long; laid only for a list and place that
 * exist and a slot that is not 0 */
void mxs_lay(u32 t, u32 sound)
{
    lay(t, sound);
}

static int lay(u32 t, u32 sound)                        /* -> 1 when the marks changed (the voices then copied) */
{
    u8 v[MARKS_MAX + 4];
    u32 m[24];
    if (t >= 16u)
        return 0;
    for (u32 e = 0; e < 24u; e++)
        m[e] = 0;
    int n = wish_get(sound, WT_MX_SETUP, v, MARKS_MAX);
    n = n < 0 ? 0 : n > (int)MARKS_MAX ? (int)MARKS_MAX : n & ~3;
    for (int i = 0; i + 4 <= n; i += 4)
        if (v[i] < 24u && v[i + 1])
            m[v[i]] = (u32)v[i + 2] << 24 | (u32)v[i + 3] << 16 | v[i + 1];
    int changed = 0;
    for (u32 e = 0; e < 24u; e++)
        if (mxs_mark[t][e] != m[e]) {
            mxs_mark[t][e] = m[e];
            changed = 1;
        }
    if (changed && sound == mxr_sound(t)) {             /* (a load, undo, a copy: the voices copy again) */
        MIRROR_COPY(sound, t);
        mxs_refresh++;
    }
    return changed;
}

/* --- the edits -------------------------------------------------------------------------------- */
/* (the User, 2026-11-21: "merge them into one (sum of depths) when the popup touches them") the entries of J into SLOT
 * made one: their depths summed (stock's clamp) into the first, the others deleted; muted if the first was */
int mxs_merge(u32 t, u32 j, u32 slot)
{
    int first = mxs_find(t, j, slot), n;
    if (first < 0)
        return -1;
    s32 sum = mxs_sum(t, j, slot, &n), d;
    if (n < 2)
        return first;
    int muted = place_muted(t, j, (u32)first);
    for (u32 p = (u32)first + 1u; p < MXS_PLACES; p++)
        if ((u32)mxs_entry(t, j, p, &d) == slot) {
            mark_put(t, j, p, 0, 0, 0);
            set_entry(t, j, p, 0, 0);
        }
    sum = sum > MXS_TOP ? MXS_TOP : sum < MXS_BOTTOM ? MXS_BOTTOM : sum;
    if (muted)
        mark_put(t, j, (u32)first, 1, slot, sum);
    set_depth(t, j, (u32)first, sum);
    if (muted)
        refresh(t);
    return first;
}

int mxs_set(u32 t, u32 j, u32 slot, s32 w)
{
    s32 d;
    int p = mxs_merge(t, j, slot);
    w = w > MXS_TOP ? MXS_TOP : w < MXS_BOTTOM ? MXS_BOTTOM : w;
    if (p >= 0) {
        if (!w)                                         /* to 0: the entry goes (its place freed), as a route */
            return mxs_delete(t, j, slot) ? MXS_OK : -MXS_NO_OBJ;
        if (place_muted(t, j, (u32)p) && mark_put(t, j, (u32)p, 1, slot, w) < 0)
            return -MXS_NO_ROOM;                        /* a muted entry keeps its mute while turned */
        int r = set_depth(t, j, (u32)p, w);
        refresh(t);
        return r;
    }
    if (!w)
        return MXS_OK;
    if (!mxs_offers(t, slot))
        return -MXS_NOT_IN;
    for (u32 q = 0; q < MXS_PLACES; q++)
        if (!mxs_entry(t, j, q, &d)) {                  /* the source's first free place */
            mark_put(t, j, q, 0, 0, 0);                 /* (no mark left from before) */
            return set_entry(t, j, q, slot, w);
        }
    return -MXS_FULL;
}

int mxs_delete(u32 t, u32 j, u32 slot)
{
    s32 d;
    int c = 0;
    for (u32 p = 0; p < MXS_PLACES; p++)
        if (slot && (u32)mxs_entry(t, j, p, &d) == slot) {
            mark_put(t, j, p, 0, 0, 0);
            set_entry(t, j, p, 0, 0);
            c++;
        }
    if (c)
        refresh(t);
    return c;
}

int mxs_mute(u32 t, u32 j, u32 slot, int on)
{
    int p = mxs_merge(t, j, slot);
    s32 w;
    if (p < 0)
        return 0;
    if (place_muted(t, j, (u32)p) == !!on)
        return 0;
    mxs_entry(t, j, (u32)p, &w);
    int r = mark_put(t, j, (u32)p, on, slot, w);
    if (r < 0)
        return r;
    refresh(t);
    return 1;
}
