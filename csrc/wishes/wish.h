/* The wishes record: a record of ours beside every stock sound (docs/wishes-record.md; the User's option D,
 * 2026-11-11: "link + blob").
 *
 * A stored sound is 359 bytes and every stock path that moves one is compiled code we cannot widen, so a sound's
 * extension (the matrix's routes, its two envelopes, later features) never goes inside it. Instead:
 *
 *   - **in RAM**, a side table keyed by the live sound's address (table.c), carried by the hooks at stock's
 *     memcpy / memset (as LFO4's on 1.11), filled by the stored-sound loader and read by the saver (hooks.S);
 *   - **in the stored sound**, a 14-byte link in the lane stock neither keeps nor reads (ids 4..28 = stored bytes
 *     36, 44, .. 84): 'W', the link's version, the record's 64-bit hash, its length and a 16-bit check;
 *   - **on the +Drive**, the record itself, in a cell of ours filed under that hash (store.c), written once and
 *     never changed, so a link can never name different data and a copy is a copy of the same hash.
 *
 * A record is a list of fields, tag u16, length u16, value, sorted by tag (tlv.c): the same content is always the
 * same bytes, so the same hash. Tag bit 15: must understand (a build that does not know it keeps the record but
 * will not edit it); bit 14: depends on the stock part (dropped when the sound's machine changes). Unknown tags are
 * kept verbatim. A tag number is never reused; a field grows only at its end. */
#ifndef WISH_H
#define WISH_H

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;
#ifdef __m68k__
#define D_ __attribute__((section(".data")))
#else
#define D_                              /* the host tests */
#endif

#define WISH_SOUND 1163u                /* a live sound's bytes (pea.w 0x48b, 32 sites) */
#define WISH_N 8192u                    /* sounds with a record: 2,192 live, the pool, clipboards and undo */
#define WISH_MAX 488u                   /* a record's bytes: what one +Drive cell holds */
#define WISH_ENTRY 512u                 /* an entry in RAM: the header below, then the record */
#define WISH_CACHE 16384u               /* hash -> an entry that holds it (a lookup, never trusted unchecked) */
#define WISH_PEND 512u                  /* cells waiting for the +Drive (a ring: one writer, one reader) */

/* The RAM above BSS that holds it all (dnfw.waverider.pages.WISH_RAM, declared in dnfw.mods.waverider.ram(),
 * docs/memory-map.md): nothing zeroes it at
 * power-on, so table.c's wish_init sets up what it reads before the first entry is made. */
#ifdef WISH_HOST                                                        /* test/test_wishes.py */
extern u8 wish_host_area[];
extern u32 host_shift_moves;                                            /* keys table.c's shift() moved */
#define WISH_AREA wish_host_area
#define WISH_SHIFT_MOVED() (host_shift_moves++)
#define WISH_DM_OK() 1                                                  /* (no +Drive moves on the host) */
#elif !defined(WISH_AREA)
#error "WISH_AREA: dnfw.waverider.pages.WISH_RAM, passed by cpage.compile_page"
#endif
#ifndef WISH_SHIFT_MOVED
#define WISH_SHIFT_MOVED() ((void)0)                                    /* counted on the host only */
#endif
#define WISH_AT(o) ((u8 *)(WISH_AREA) + (o))
#define WISH_O_KEYS   0u                                                /* u32[WISH_N], ascending */
#define WISH_O_SLOTS  (WISH_O_KEYS + 4u * WISH_N)                       /* u16[WISH_N]: key k's entry */
#define WISH_O_FREE   (WISH_O_SLOTS + 2u * WISH_N)                      /* u16[WISH_N]: free entries, a stack */
#define WISH_O_HCACHE (WISH_O_FREE + 2u * WISH_N)                       /* u16[WISH_CACHE], 0xffff empty */
#define WISH_O_PCELLS (WISH_O_HCACHE + 2u * WISH_CACHE)                 /* WISH_PEND x 512 B, cells to write */
#define WISH_O_IO     (WISH_O_PCELLS + 512u * WISH_PEND)                /* one sector, read and written */
#define WISH_O_CARRY  (WISH_O_IO + 512u)                                /* u32[WISH_N] + u16[WISH_N]: a carry's copies */
#define WISH_O_SLAB   (WISH_O_CARRY + 6u * WISH_N)                      /* WISH_N x WISH_ENTRY */
#define WISH_O_END    (WISH_O_SLAB + WISH_ENTRY * WISH_N)
#define WISH_BYTES WISH_O_END                                          /* 4,497 KB: dnfw.waverider.pages.WISH_BYTES */

/* An entry. The record bytes follow the header; `len` 0 never stays in the table (an empty record is no record). */
struct wish {
    u32 h0, h1;                         /* the record's hash, valid unless DIRTY */
    u16 len;                            /* the record's bytes */
    u8 flags;
    u8 pad;
    u8 rec[WISH_MAX];
};
#define W_DIRTY   0x01                  /* edited since its hash was taken: the next save re-hashes it */
#define W_DISK    0x02                  /* its cell is on the +Drive, or queued for it */
#define W_WANT    0x04                  /* only the link is known: the record is read from the +Drive (store.c) */
#define W_MISSING 0x08                  /* ... and no cell holds it: it plays stock, the link is kept */
#define W_LOCKED  0x10                  /* a must-understand field this build does not know: no edits */
#define W_ATT     0x20                  /* (2026-11-19, csrc/matrix/atten.c) RAM only: this live sound's DEPs are the LFOs'
                                         * attenuverters (converted); the loader leaves a sound stored (DEP = C) */

/* The link, in the stored sound: lane id k is stored bytes 28 + 2k, big-endian, at any alignment. */
#define WL_MAGIC 0x57u                  /* 'W' */
#define WL_VERSION 1u
#define WL_ID_HEAD 4u                   /* 'W', version */
#define WL_ID_HASH 8u                   /* 8, 12, 16, 20: h0 hi, h0 lo, h1 hi, h1 lo */
#define WL_ID_LEN 24u
#define WL_ID_CHECK 28u                 /* over the twelve bytes above */
#define WL_STORED(id) (28u + 2u * (id))

/* Tags (tlv.c). Bit 15 must understand, bit 14 tied to the stock part; the rest the field's number, never reused. */
#define WT_MUST 0x8000u
#define WT_MACHINE 0x4000u
#define WT_MX_ROUTES 0x0010u           /* the matrix's routes (csrc/matrix/matrix.c, docs/matrix.md) */
#define WT_MX_ENV 0x0011u              /* ENV2: ATK HOLD DEC SUS REL MODE RSET, a byte kept 0 (csrc/matrix/env2_page.c) */
#define WT_LFO4 0x0012u                /* LFO4: SPD MULT FADE DEST WAVE SPH MODE DEP, 8 x u16 (csrc/wishes/lfo4.c) */
#define WT_MX_LFO 0x0013u              /* LFO1-3 {u16 DEP as saved, u16 the first route's depth} (csrc/matrix/atten.c) */
#define WT_AMP_SW 0x0014u              /* AMP ON/OFF on the drum machines: 1 byte, 1 = ON; no field = OFF (csrc/msel/ampsw.c) */

/* table.c */
extern u8 wish_busy;
extern u32 wish_n, wish_ready, wish_reentered, wish_full;
extern u32 wish_q_head, wish_q_tail, wish_queued, wish_q_max;   /* (2026-11-21) copies queued for the lock's holder */
extern u32 wish_wants;
extern u32 wish_loads, wish_links_in, wish_saves, wish_links_out, wish_copies, wish_carries, wish_clears;
extern volatile u32 wish_edits;        /* any entry's record changed (made, copied, cleared, put, read): the matrix re-reads */
void wish_init(void);
int wish_take(void);
void wish_give(void);
struct wish *wish_find(u32 sound);
struct wish *wish_add(u32 sound);
void wish_drop(u32 sound);
void wish_copy(u32 dst, u32 src);
void wish_carry(u32 dst, u32 src, u32 n);
void wish_clear(u32 at, u32 n);
struct wish *wish_entry(u32 slot);
u32 wish_slot_of(const struct wish *w);
void wish_cache_put(const struct wish *w);
struct wish *wish_cache_get(u32 h0, u32 h1);
void wish_load(u32 live, const u8 *stored);
#if DN2_LFO4                                   /* lfo4.c */
void wish_lfo4_save(u32 live);
void wish_lfo4_load(u32 live, int linked);
void wish_lfo4_poll(void);
#endif
void wish_save(u8 *stored, u32 live);
void mxa_save(struct wish *w, u8 *stored, u32 live);                  /* csrc/matrix/atten.c */
int wish_link_read(const u8 *stored, u32 *h0, u32 *h1, u32 *len);
void wish_link_write(u8 *stored, u32 h0, u32 h1, u32 len);

/* tlv.c */
u32 wish_xxh32(const u8 *p, u32 n, u32 seed);
void wish_hash(const u8 *rec, u32 len, u32 *h0, u32 *h1);
int wish_hash_ok(const u8 *rec, u32 len, u32 h0, u32 h1);
int wish_tlv_valid(const u8 *rec, u32 len);
int wish_tlv_find(const u8 *rec, u32 len, u32 tag, u32 *at, u32 *vlen);
int wish_tlv_put(u8 *rec, u32 len, u32 tag, const u8 *v, u32 vlen);   /* -> the new length, or -1 */
int wish_tlv_locked(const u8 *rec, u32 len);
u32 wish_tlv_drop_machine(u8 *rec, u32 len);
int wish_get(u32 sound, u32 tag, u8 *out, u32 max);                   /* -> the value's bytes, or -1 */
int wish_put(u32 sound, u32 tag, const u8 *v, u32 vlen);              /* vlen 0 removes; -> 0, or < 0 */
int wish_known(u32 tag);

/* item.c: kits and patterns, keyed by their live object's address as sounds are (docs/wishes-record.md, "Every
 * item type"). An entry's `pad` is its item type (0: a sound, as phase 1 makes it); the cell's kind byte too. */
#define WI_SOUND 1u
#define WI_KIT 2u
#define WI_PATTERN 3u
#define WI_SONG 4u                      /* index 0 the work song, 1..16 the songs */
#define WI_PROJECT 5u                   /* index 0: the project's settings (one live project) */
#define WI_LINK 14u                     /* 'W', version, h0, h1, length, check: the sound link's words, in a row */
extern u32 wish_item_loads, wish_item_saves, wish_item_nolane, wish_item_dropped;
u32 wish_item(u32 type, u32 index);    /* -> the live object's address (then wish_get / wish_put on it), or 0 */
/* the live kit the sequencer plays: written by the pattern/kit switch 0x400d93b0 (kit 128 when 0x42432b75 bit 0
 * is set) and four more sites, read by the engine (16 references in 1.12) */
#define WISH_KIT_PLAYING (*(volatile u32 *)0x42C5B9ACu)
#define WISH_PATTERN_PLAYING (*(volatile u32 *)0x42C5B9A0u)
void wish_kit_load(u32 live, const u8 *stored);
void wish_kit_save(u8 *stored, u32 live);
void wish_pattern_load(u32 live, const u8 *stored);
void wish_pattern_save(u8 *stored, u32 live);
void wish_song_load(u32 live, const u8 *stored);
void wish_song_save(u8 *stored, u32 live);
void wish_settings_load(u32 live, const u8 *stored);
void wish_settings_save(u8 *stored, u32 live);

/* store.c */
extern u32 wish_cells_written, wish_cells_found, wish_cells_read, wish_resolved, wish_missing;
extern volatile u32 wish_pend_head, wish_pend_tail;
extern u32 wish_pend_lost, wish_io_fails;
extern volatile u32 wish_put_wait, wish_got_state;
extern u32 wish_puts, wish_gets;
int wish_enqueue(const struct wish *w);
void wish_poll(void);
u32 wish_rx(u32 cmd, const u8 *rq, u32 n, u8 *rp, u32 r, u8 *st);   /* link.c: PUT 12, GET 13 */

#endif
