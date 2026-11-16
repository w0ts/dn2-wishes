/* The wishes record in RAM: which live sound has a record, and the record (wish.h).
 *
 * **Keyed by the live sound's address**, as LFO4's table on 1.11 (csrc/lfo4/ext.c, which passed on the
 * hardware), so correctness is one question: does every way a live sound moves carry its entry? The ways are
 * stock's memcpy and memset of a sound or of something holding sounds (hooks.S, by range: a kit, a pattern, the
 * pool), and the stored-sound loader and saver (wish_load, wish_save).
 *
 * **A sorted index, not LFO4's hash.** LFO4's 256 entries were too few for 2,192 sounds, and a copy of a block
 * (a kit, a pattern) has to find every tracked sound inside it: a hash table walks all of its slots for that, on
 * every large copy near a tracked sound. Here the keys are kept in ascending order: a lookup is a binary search
 * (13 steps at 8,192), and the sounds inside a block are one run of keys, found by one search and moved as one
 * block. An insert or a drop moves the keys after it (at most 8,192 x 6 B, on a load or an edit, never per frame).
 * Each key names an entry of 512 B in the slab; a copy copies the entry, a drop gives it back to the free stack.
 *
 * **Who calls, and when.** memcpy and memset run in every task and in interrupts. Every mutator here takes
 * wish_busy first; a call that finds it taken (an interrupt's copy while a task is in here) does nothing and
 * counts wish_reentered. LFO4 measured that counter at 0 on 1.11 (scripts/emu_lfo4_boot.py); the gate reads it.
 * The audio interrupt never reads this table: the matrix reads per-track lists the UI task builds. */
#include "wish.h"

#define KEYS ((u32 *)WISH_AT(WISH_O_KEYS))
#define SLOTS ((u16 *)WISH_AT(WISH_O_SLOTS))
#define FREE ((u16 *)WISH_AT(WISH_O_FREE))
#define HCACHE ((u16 *)WISH_AT(WISH_O_HCACHE))
#define NONE 0xFFFFu

u32 wish_n D_ = 0;                      /* keys in the index (hooks.S tests it: 0 = nothing to carry) */
u32 wish_ready D_ = 0;                  /* wish_init has run since power-on (.data is reloaded at boot) */
u8 wish_busy D_ = 0;                    /* the lock: tas.b, one instruction to test and take */
static u32 nfree D_ = 0;
u32 wish_reentered D_ = 0, wish_full D_ = 0;
u32 wish_loads D_ = 0, wish_links_in D_ = 0, wish_saves D_ = 0, wish_links_out D_ = 0;
u32 wish_wants D_ = 0;                  /* entries made from a link alone since store.c last looked */
u32 wish_copies D_ = 0, wish_carries D_ = 0, wish_clears D_ = 0;

void wish_init(void)
{
    u32 k;

    if (wish_ready)
        return;
    for (k = 0; k < WISH_N; k++)
        FREE[k] = (u16)(WISH_N - 1u - k);       /* entry 0 on top */
    nfree = WISH_N;
    for (k = 0; k < WISH_CACHE; k++)
        HCACHE[k] = NONE;
    wish_n = 0;
    wish_ready = 1;
}

struct wish *wish_entry(u32 slot)
{
    return (struct wish *)WISH_AT(WISH_O_SLAB + WISH_ENTRY * slot);
}

u32 wish_slot_of(const struct wish *w)
{
    return (u32)((const u8 *)w - WISH_AT(WISH_O_SLAB)) / WISH_ENTRY;
}

/* the first index whose key is >= key */
static u32 lower(u32 key)
{
    u32 lo = 0, hi = wish_n;

    while (lo < hi) {
        u32 mid = (lo + hi) >> 1;
        if (KEYS[mid] < key)
            lo = mid + 1;
        else
            hi = mid;
    }
    return lo;
}

/* the index's [at, wish_n) moved by `by` places (up when by > 0) */
static void shift(u32 at, s32 by)
{
    u32 k;

    if (by > 0)
        for (k = wish_n; k-- > at;) {
            KEYS[k + (u32)by] = KEYS[k];
            SLOTS[k + (u32)by] = SLOTS[k];
        }
    else
        for (k = at; k < wish_n; k++) {
            KEYS[k - (u32)-by] = KEYS[k];
            SLOTS[k - (u32)-by] = SLOTS[k];
        }
}

static void copy_entry(struct wish *to, const struct wish *from)
{
    const u32 *s = (const u32 *)from;
    u32 *d = (u32 *)to;
    u32 k, words = (12u + from->len + 3u) >> 2;

    for (k = 0; k < words; k++)
        d[k] = s[k];
}

static void clear_entry(struct wish *w)
{
    w->h0 = w->h1 = 0;
    w->len = 0;
    w->flags = 0;
    w->pad = 0;
}

/* -> 1 with the lock, 0 (counted) when another caller holds it: an interrupt's copy, or a task this one interrupted */
int wish_take(void)
{
    int was;

    wish_init();
#ifdef __m68k__
    __asm__ volatile ("tas.b %1\n\tsne %0\n\textb.l %0" : "=d"(was), "+m"(wish_busy) : : "cc");
#else
    was = wish_busy;
    wish_busy = 0x80;
#endif
    if (was) {
        wish_reentered++;
        return 0;
    }
    return 1;
}

void wish_give(void)
{
    wish_busy = 0;
}

#define take wish_take
#define give wish_give

static struct wish *find(u32 sound)
{
    u32 i = lower(sound);

    return i < wish_n && KEYS[i] == sound ? wish_entry(SLOTS[i]) : 0;
}

static struct wish *add(u32 sound)
{
    u32 i = lower(sound);
    struct wish *w;

    if (i < wish_n && KEYS[i] == sound)
        return wish_entry(SLOTS[i]);
    if (!nfree) {
        wish_full++;
        return 0;
    }
    shift(i, 1);
    KEYS[i] = sound;
    SLOTS[i] = FREE[--nfree];
    wish_n++;
    w = wish_entry(SLOTS[i]);
    clear_entry(w);
    return w;
}

/* the index's [i, i + n) removed, their entries freed */
static void remove_run(u32 i, u32 n)
{
    u32 k;

    if (!n)
        return;
    for (k = 0; k < n; k++) {
        clear_entry(wish_entry(SLOTS[i + k]));  /* so the hash cache never answers with it */
        FREE[nfree++] = SLOTS[i + k];
    }
    shift(i + n, -(s32)n);
    wish_n -= n;
}

static void drop(u32 sound)
{
    u32 i = lower(sound);

    if (i < wish_n && KEYS[i] == sound)
        remove_run(i, 1);
}

struct wish *wish_find(u32 sound)
{
    if (!wish_ready || !wish_n)
        return 0;
    return find(sound);
}

struct wish *wish_add(u32 sound)
{
    struct wish *w;

    if (!sound || !take())
        return 0;
    w = add(sound);
    give();
    return w;
}

void wish_drop(u32 sound)
{
    if (!wish_n || !take())
        return;
    drop(sound);
    give();
}

/* one sound copied over another: the copy holds what the source holds, or nothing */
void wish_copy(u32 dst, u32 src)
{
    struct wish *from, *to;

    if (!wish_n || dst == src || !take())
        return;
    wish_copies++;
    from = find(src);
    if (!from)
        drop(dst);
    else if ((to = add(dst)) != 0)
        copy_entry(to, find(src));      /* add() moved keys, not entries: from is still good */
    give();
}

/* a block of N bytes copied from SRC to DST: every tracked sound that starts inside the source is now also at the
 * same offset in the destination, and nothing that was tracked inside the destination is any more. The copies are
 * made before the destination's old entries go, so a source inside the destination (an overlap) is read whole. */
void wish_carry(u32 dst, u32 src, u32 n)
{
    u32 *at = (u32 *)WISH_AT(WISH_O_CARRY);        /* as many as the table holds: no batch limit */
    u16 *made = (u16 *)WISH_AT(WISH_O_CARRY + 4u * WISH_N);
    u32 i, j, k, taken = 0;

    if (!wish_n || dst == src || !n || !take())
        return;
    wish_carries++;
    for (i = lower(src); i < wish_n && KEYS[i] - src < n; i++) {
        if (!nfree) {
            wish_full++;                /* the rest are not carried: counted, never carried wrong */
            break;
        }
        made[taken] = FREE[--nfree];
        copy_entry(wish_entry(made[taken]), wish_entry(SLOTS[i]));
        at[taken++] = dst + (KEYS[i] - src);
    }
    i = lower(dst);
    for (j = i; j < wish_n && KEYS[j] - dst < n; j++)
        ;
    remove_run(i, j - i);
    shift(i, (s32)taken);
    for (k = 0; k < taken; k++) {
        KEYS[i + k] = at[k];
        SLOTS[i + k] = made[k];
    }
    wish_n += taken;
    give();
}

/* N bytes overwritten at AT: no tracked sound starts inside them any more */
void wish_clear(u32 at, u32 n)
{
    u32 i, j;

    if (!wish_n || !n || !take())
        return;
    wish_clears++;
    i = lower(at);
    for (j = i; j < wish_n && KEYS[j] - at < n; j++)
        ;
    remove_run(i, j - i);
    give();
}

/* hooks.S: stock's memcpy(dst, src, n) and memset(dst, fill, n), only when n >= a sound and wish_n != 0 */
void wish_on_memcpy(u32 dst, u32 src, u32 n)
{
    if (n == WISH_SOUND)
        wish_copy(dst, src);
    else
        wish_carry(dst, src, n);
}

void wish_on_memset(u32 dst, u32 fill, u32 n)
{
    (void)fill;
    wish_clear(dst, n);
}

/* -- the hash cache: an entry that holds a record, by its hash (a load finds its record without the +Drive) -- */

void wish_cache_put(const struct wish *w)
{
    if (wish_ready && !(w->flags & (W_DIRTY | W_WANT)))
        HCACHE[w->h0 & (WISH_CACHE - 1u)] = (u16)wish_slot_of(w);
}

/* checked: the slot may since hold another record, or none (its key gone) */
struct wish *wish_cache_get(u32 h0, u32 h1)
{
    u32 s;
    struct wish *w;

    if (!wish_ready || (s = HCACHE[h0 & (WISH_CACHE - 1u)]) == NONE)
        return 0;
    w = wish_entry(s);
    if (w->h0 != h0 || w->h1 != h1 || !w->len || (w->flags & (W_DIRTY | W_WANT)))
        return 0;
    return w;                           /* (a freed entry is cleared: remove_run) */
}

/* -- the link -- */

static u32 get16(const u8 *s, u32 id)
{
    return (u32)s[WL_STORED(id)] << 8 | s[WL_STORED(id) + 1u];
}

static void put16(u8 *s, u32 id, u32 v)
{
    s[WL_STORED(id)] = (u8)(v >> 8);
    s[WL_STORED(id) + 1u] = (u8)v;
}

static u32 check16(u32 head, u32 h0, u32 h1, u32 len)
{
    u32 x = wish_xxh32((const u8 *)0, 0, head ^ h0 ^ (h1 << 7 | h1 >> 25) ^ len << 16);
    return (x ^ x >> 16) & 0xFFFFu;
}

/* -> 1 and the link, 0 when the lane holds none this build reads (stock's zeros, another firmware's bytes, a
 * link version from a later build) */
int wish_link_read(const u8 *stored, u32 *h0, u32 *h1, u32 *len)
{
    u32 head = get16(stored, WL_ID_HEAD);

    if (head != (WL_MAGIC << 8 | WL_VERSION))
        return 0;
    *h0 = get16(stored, WL_ID_HASH) << 16 | get16(stored, WL_ID_HASH + 4u);
    *h1 = get16(stored, WL_ID_HASH + 8u) << 16 | get16(stored, WL_ID_HASH + 12u);
    *len = get16(stored, WL_ID_LEN);
    if (!*len || *len > WISH_MAX || get16(stored, WL_ID_CHECK) != check16(head, *h0, *h1, *len))
        return 0;
    return 1;
}

void wish_link_write(u8 *stored, u32 h0, u32 h1, u32 len)
{
    u32 head = WL_MAGIC << 8 | WL_VERSION;

    put16(stored, WL_ID_HEAD, head);
    put16(stored, WL_ID_HASH, h0 >> 16);
    put16(stored, WL_ID_HASH + 4u, h0);
    put16(stored, WL_ID_HASH + 8u, h1 >> 16);
    put16(stored, WL_ID_HASH + 12u, h1);
    put16(stored, WL_ID_LEN, len);
    put16(stored, WL_ID_CHECK, check16(head, h0, h1, len));
}

/* hooks.S, at the end of stock's stored -> live (0x400dd34e): the loaded sound has the stored sound's record */
void wish_load(u32 live, const u8 *stored)
{
    u32 h0, h1, len;
    struct wish *w;
    const struct wish *have;

    wish_loads++;
    if (!wish_link_read(stored, &h0, &h1, &len)) {
        wish_drop(live);
        return;
    }
    wish_links_in++;
    if (!take())
        return;
    w = add(live);
    if (w) {
        have = wish_cache_get(h0, h1);
        if (have && have != w)
            copy_entry(w, have);
        else if (have != w) {
            clear_entry(w);
            w->h0 = h0;
            w->h1 = h1;
            w->len = (u16)len;
            w->flags = W_WANT | W_DISK;         /* store.c reads the cell */
            wish_wants++;
        }
    }
    give();
}

/* hooks.S, at the end of stock's live -> stored (0x400dd80a): stock has written the lane as zeros; a sound with a
 * record gets its link, and the record goes to the +Drive if it is not there yet */
void wish_save(u8 *stored, u32 live)
{
    struct wish *w;

    wish_saves++;
    if (!wish_n || !take())
        return;
    w = find(live);
    if (w && (w->flags & W_DIRTY)) {
        if (!w->len) {
            drop(live);
            w = 0;
        } else {
            wish_hash(w->rec, w->len, &w->h0, &w->h1);
            w->flags &= (u8)~(W_DIRTY | W_DISK);
        }
    }
    if (w) {
        wish_link_write(stored, w->h0, w->h1, w->len);
        wish_links_out++;
        if (!(w->flags & (W_DISK | W_WANT)) && wish_enqueue(w) == 0)
            w->flags |= W_DISK;
        wish_cache_put(w);
    }
    give();
}
