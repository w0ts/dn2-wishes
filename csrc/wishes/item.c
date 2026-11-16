/* The wishes record beyond sounds: kits and patterns (docs/wishes-record.md, "Every item type"; the User,
 * 2026-11-12: "we need link+blob for every type of item").
 *
 * A sound's record is keyed by the live sound's address (table.c). Every other item is keyed the same way, by
 * its live object's address, in the same table: so the same memcpy / memset hooks carry a kit's or a pattern's
 * record when stock copies or clears the object (a kit is 23,921 B, a pattern 122,478 B: both are larger than a
 * sound, so the stubs hand them to wish_carry / wish_clear), and wish_get / wish_put work on any item. What is
 * new per item type is where its 14-byte link lives in the stored object, and the hooks at its loader and saver.
 *
 *   type     live                          stored          the link (14 B, contiguous)
 *   kit      0x4210d08c + 23,921 n, n<129  10,752 B        stored 10,416: past the terminator BACEF00C at
 *                                                          10,411, in 10,415..10,751, which stock's saver
 *                                                          0x400ddfa8 never writes and its loader 0x400dddb6
 *                                                          never reads
 *   pattern  0x4121998c + 122,478 n        89,088 B        the body of the last unused lock record (stored
 *                                                          68,148 + 258 i, header FF FF): stock's lock saver
 *                                                          0x400de87c writes only an unused record's header, and
 *                                                          its loader 0x400de682 skips the record whole;
 *                                                          with all 80 in use, the one with the fewest
 *                                                          locked steps gives way (give_way)
 *   song     0x423fe67d + 3,694 n, n<17    3,072 B         stored 2,900: the saver 0x400decc6 zeroes 2,900..3,071,
 *            (0 the work song, 1..16)                      the loader 0x400debce never reads them
 *   project  0x42432a61 (its settings,     1,024 B         stored 544: the saver 0x400df6de zeroes 542..1,023,
 *            738 B), n = 0                                 the loader 0x400df050 never reads them
 *
 * The link: 'W', version 1, h0, h1 (big-endian), the record's length (u16), a 16-bit check over the twelve bytes
 * before it (the sound link's check, table.c). It is spelled through the sound link's own reader and writer, on
 * a lane-shaped scratch: one spelling of the rules, one place that resolves a link (wish_load / wish_save).
 *
 * An entry's `pad` byte holds its item type (0 = a sound, as phase 1 leaves it), so the cell on the +Drive can
 * say what it holds. */
#include "wish.h"

#define KIT0 0x4210D08Cu
#define KIT_BYTES 23921u
#define KITS 129u                               /* ArrayValueWithMirror<kit_t, kitStorage_v4_t, 129> */
#define KIT_LANE 10416u
#define KIT_STORED 10752u
_Static_assert(KIT_LANE >= 10415u && KIT_LANE + WI_LINK <= KIT_STORED, "the kit's link lies past its terminator");

#define PAT0 0x4121998Cu
#define PAT_BYTES 122478u
#define PATS 128u
#define LOCKS 68148u                            /* the stored lock pool: 80 records of 258 B */
#define LOCK_RECS 80u
#define LOCK_REC 258u
_Static_assert(LOCKS + LOCK_RECS * LOCK_REC == 88788u, "the lock pool ends where the pattern's tail begins");

#define SONG0 0x423FE67Du                      /* the work song; songs 1..16 follow it */
#define SONG_BYTES 3694u
#define SONGS 17u
#define SONG_LANE 2900u
#define SONG_STORED 3072u
_Static_assert(SONG_LANE + WI_LINK <= SONG_STORED, "the song's link lies in its zeroed tail");

#define PROJECT_SETTINGS 0x42432A61u
#define PS_LANE 544u
#define PS_STORED 1024u
_Static_assert(PS_LANE >= 542u && PS_LANE + WI_LINK <= PS_STORED, "the settings' link lies in their zeroed tail");

u32 wish_item_loads D_ = 0, wish_item_saves D_ = 0, wish_item_nolane D_ = 0;
u32 wish_item_dropped D_ = 0xFFFFFFFFu;         /* the last lock record dropped: steps << 16 | track << 8 | id */

/* the live object of TYPE number INDEX -> its address, 0 when there is none */
u32 wish_item(u32 type, u32 index)
{
    if (type == WI_KIT && index < KITS)
        return KIT0 + KIT_BYTES * index;
    if (type == WI_PATTERN && index < PATS)
        return PAT0 + PAT_BYTES * index;
    if (type == WI_SONG && index < SONGS)
        return SONG0 + SONG_BYTES * index;
    if (type == WI_PROJECT && index == 0)
        return PROJECT_SETTINGS;
    return 0;
}

/* the lane-shaped scratch <-> the contiguous link */
static void lane_from(u8 *lane, const u8 *link)
{
    u32 id, k = 0;

    for (id = WL_ID_HEAD; id <= WL_ID_CHECK; id += 4u, k += 2u) {
        lane[WL_STORED(id)] = link[k];
        lane[WL_STORED(id) + 1u] = link[k + 1u];
    }
}

static void lane_to(u8 *link, const u8 *lane)
{
    u32 id, k = 0;

    for (id = WL_ID_HEAD; id <= WL_ID_CHECK; id += 4u, k += 2u) {
        link[k] = lane[WL_STORED(id)];
        link[k + 1u] = lane[WL_STORED(id) + 1u];
    }
}

static void mark(u32 live, u32 type)
{
    struct wish *w = wish_find(live);

    if (w)
        w->pad = (u8)type;
}

/* stored -> live: the item has the record its link names, or none */
static void item_load(u32 type, u32 live, const u8 *link)
{
    u8 lane[WL_STORED(WL_ID_CHECK) + 2u];
    u32 k;

    wish_item_loads++;
    for (k = 0; k < sizeof lane; k++)
        lane[k] = 0;
    if (link)
        lane_from(lane, link);
    wish_load(live, lane);
    mark(live, type);
}

/* live -> stored: the item's link (zeros when it has no record) */
static void item_save(u32 type, u8 *link, u32 live)
{
    u8 lane[WL_STORED(WL_ID_CHECK) + 2u];
    u32 k;

    wish_item_saves++;
    for (k = 0; k < sizeof lane; k++)
        lane[k] = 0;
    mark(live, type);
    wish_save(lane, live);
    lane_to(link, lane);
}

/* -- the kit -- */

void wish_kit_load(u32 live, const u8 *stored)
{
    item_load(WI_KIT, live, stored + KIT_LANE);
}

void wish_kit_save(u8 *stored, u32 live)
{
    item_save(WI_KIT, stored + KIT_LANE, live);
}

/* -- the song and the project's settings: the link in the tail stock's saver zeroes and its loader never reads -- */

void wish_song_load(u32 live, const u8 *stored)
{
    item_load(WI_SONG, live, stored + SONG_LANE);
}

void wish_song_save(u8 *stored, u32 live)
{
    item_save(WI_SONG, stored + SONG_LANE, live);
}

void wish_settings_load(u32 live, const u8 *stored)
{
    item_load(WI_PROJECT, live, stored + PS_LANE);
}

void wish_settings_save(u8 *stored, u32 live)
{
    item_save(WI_PROJECT, stored + PS_LANE, live);
}

/* -- the pattern: the link in an unused lock record's body -- */

static int unused(const u8 *rec)
{
    return rec[0] == 0xFFu && rec[1] == 0xFFu;
}

void wish_pattern_load(u32 live, const u8 *stored)
{
    const u8 *pool = stored + LOCKS;
    u32 i, h0, h1, len;
    u8 lane[WL_STORED(WL_ID_CHECK) + 2u];
    u32 k;

    for (i = LOCK_RECS; i-- > 0;) {
        const u8 *rec = pool + LOCK_REC * i;
        if (!unused(rec))
            continue;
        for (k = 0; k < sizeof lane; k++)
            lane[k] = 0;
        lane_from(lane, rec + 2);
        if (wish_link_read(lane, &h0, &h1, &len)) {
            item_load(WI_PATTERN, live, rec + 2);
            return;
        }
    }
    item_load(WI_PATTERN, live, 0);
}

/* a stock lock record (id 0..106, track 0..15; slides' ids 200..202 are not stock's) -> its locked steps */
static int stock_lock(const u8 *rec)
{
    return rec[0] <= 106u && rec[1] <= 15u;
}

static u32 steps(const u8 *rec)
{
    u32 s, n = 0;

    for (s = 0; s < 128u; s++)
        n += !(rec[2 + 2 * s] == 0xFFu && rec[3 + 2 * s] == 0xFFu);
    return n;
}

/* every lock record in use (the User, 2026-11-12: "delete one plock? no one will notice"): the stored copy of the
 * one that matters least gives way to the link: the fewest locked steps, the last of those. It stays in RAM until
 * the pattern is reloaded. -> that record, or 0 when none is stock's */
static u8 *give_way(u8 *pool)
{
    u8 *pick = 0;
    u32 i, n, best = 0xFFFFFFFFu;

    for (i = 0; i < LOCK_RECS; i++) {
        u8 *rec = pool + LOCK_REC * i;
        if (!stock_lock(rec) || (n = steps(rec)) > best)
            continue;
        best = n;
        pick = rec;
    }
    if (pick) {
        wish_item_dropped = best << 16 | (u32)pick[1] << 8 | pick[0];
        pick[0] = pick[1] = 0xFFu;
    }
    return pick;
}

void wish_pattern_save(u8 *stored, u32 live)
{
    u8 *pool = stored + LOCKS, *last = 0;
    u8 link[WI_LINK];
    u32 i, k;

    for (i = 0; i < LOCK_RECS; i++) {
        u8 *rec = pool + LOCK_REC * i;
        if (!unused(rec))
            continue;
        for (k = 0; k < WI_LINK; k++)
            rec[2 + k] = 0;                     /* no other unused record keeps an old link */
        last = rec;
    }
    item_save(WI_PATTERN, link, live);
    if (!link[0])
        return;
    if (!last) {
        wish_item_nolane++;                     /* 80 locks in use: one gives way, or (none stock's) RAM only */
        last = give_way(pool);
    }
    if (last)
        for (k = 0; k < WI_LINK; k++)
            last[2 + k] = link[k];
}
