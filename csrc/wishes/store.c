/* The wishes record on the +Drive (wish.h): one cell per record, filed under the record's hash.
 *
 *   0x5D8000 .. 0x5EE7FF   92,160 cells of one sector (v0.69.2; 59,392 at 0x6F0800.. until v0.69.1, upstream's bank
 *                          lists' place: filed again here by dmove.c, once), below the pool image, past the
 *                          factory buffer: sectors upstream never names (csrc/include/dmove.h)
 *
 *   a cell:  +0 'DN2W'  +4 version  +5 kind (1 a sound's record, 2 a kit's, 3 a pattern's: item.c)  +6 length  +8 h0  +12 h1  +16 generation (0)
 *            +20 the record (up to 488 B)  +508 its check
 *
 * **Where a record goes:** cell (h0 mod 59,392), then the next ones, the first that is empty or already holds
 * it. A lookup walks the same cells and stops at the first empty one: no index is read at power-on, and a record
 * costs one sector read to find (a few in a crowded stretch).
 *
 * **Crash safety (docs/wishes-record.md "Order of writes"):** a cell is written whole, once, and never again while
 * a link may name it; a cell torn by a power cut fails its check and reads as empty, and it can only be the last of
 * its stretch (the cell being added), so no lookup of another record stops early on it. The link that names a
 * record is written by stock's own saver into stock's own records; the cell follows within SETTLE of the last edit
 * (and at once when stock writes a project slot). A power cut in between loses that one record: its link names no
 * cell, the sound plays its stock part, and the link is kept in case the record arrives later.
 *
 * Collecting cells no link names any more (reference lists, generations) is not done yet: 59,392 cells last a long
 * time, and a cell is never freed, so nothing can lose a record.
 *
 * Every write here waits for the +Drive, for ERASE MOD DATA (smp_er_lock), and runs from the UI loop (wr_poll),
 * as inserts' and the pools' writes (csrc/inserts/store.c, csrc/sampler/pools.c).
 *
 * **Travel** (phase 5, docs/wishes-record.md "Travel"): a record sent over our SysEx channel (link.c, PUT 12) is
 * filed as a save files one, and every sound waiting for it gets it; a record asked for by its hash (GET 13) is
 * answered from RAM, or read from its cell by the UI loop and answered when asked again. The MIDI task only fills a
 * mailbox and reads under the table's lock; the UI loop does the rest. */
#include "wish.h"

#ifndef WISH_BLK_READ
#define WISH_BLK_READ(s, n, p) ((int (*)(u32, u32, void *))0x4012C87Au)(s, n, p)       /* pools.c's */
#define WISH_BLK_WRITE(s, n, p) ((int (*)(u32, u32, const void *))0x4012CA60u)(s, n, p)
#define WISH_BLK_READY (*(volatile u32 *)0x4461C68Cu)
#define WISH_BLK_SECTORS (*(volatile u32 *)0x4461C6B0u)
#define WISH_FRAMES (*(volatile u32 *)0x4058F8D4u)                                       /* 1,500 a second */
#endif

#define CELL0 0x5D8000u
#define CELLS 92160u
#define CELL_END (CELL0 + CELLS)
_Static_assert(CELL0 >= 0x5D8000u && CELL_END <= 0x5EE800u,
               "the cells lie past the factory buffer, where the old bank lists A were (csrc/include/dmove.h)");
#define MAGIC 0x444E3257u                       /* 'DN2W' */
#define VERSION 1u
#define KIND_SOUND 1u
#define CHECK_XOR 0x57495348u
#define HEAD 20u
#define AT_CHECK 508u
_Static_assert(HEAD + WISH_MAX == AT_CHECK, "a record fills a cell to its check");
#define PROBE 64u                               /* cells one lookup walks at most */
#define SETTLE 750u                             /* 0.5 s after the last queued record */
#define PER_PASS 4u                             /* sector writes (each with its reads) in one UI pass */

extern int smp_er_lock;                         /* erase.c */
extern volatile u32 ins_wr_head;                /* csrc/inserts/hooks.S: stock wrote a project slot */

u32 wish_cells_written D_ = 0, wish_cells_found D_ = 0, wish_cells_read D_ = 0;
u32 wish_resolved D_ = 0, wish_missing D_ = 0, wish_pend_lost D_ = 0, wish_io_fails D_ = 0;
/* the queue: wish_save (any task) adds at the tail, wish_poll (the UI loop) writes from the head; each moves only
 * its own index, so neither needs the lock. Full: tail - head == WISH_PEND */
volatile u32 wish_pend_head D_ = 0, wish_pend_tail D_ = 0;
static u32 pend_at D_ = 0;                      /* when the last record was queued (frames) */
static u32 pj_seen D_ = 0;
static u32 requeue D_ = 0;                      /* a record linked but not queued (the queue was full): look again */

#define IO WISH_AT(WISH_O_IO)
#define PCELL(k) WISH_AT(WISH_O_PCELLS + 512u * ((k) % WISH_PEND))

static u32 get32(const u8 *p)
{
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

static void put32(u8 *p, u32 v)
{
    p[0] = (u8)(v >> 24);
    p[1] = (u8)(v >> 16);
    p[2] = (u8)(v >> 8);
    p[3] = (u8)v;
}

static u32 check(const u8 *p)
{
    u32 a = 1, b = 0, k;

    for (k = 0; k < AT_CHECK; k++) {
        a += p[k];
        b += a;
    }
    return (b << 16 ^ a) ^ CHECK_XOR;
}

#ifndef WISH_DM_OK
extern int dm_ok(void);                         /* csrc/sampler/dmove.c: every +Drive move done (v0.69.2) */
#define WISH_DM_OK() dm_ok()
#endif

static int ok(void)
{
    return WISH_BLK_READY && WISH_BLK_SECTORS >= CELL_END && !smp_er_lock && WISH_DM_OK();
}

/* -> 1 when P is a whole cell of a version this build reads */
static int cell_valid(const u8 *p)
{
    return get32(p) == MAGIC && p[4] == VERSION && (u32)(p[6] << 8 | p[7]) <= WISH_MAX
           && get32(p + AT_CHECK) == check(p);
}

static void cell_make(u8 *p, const struct wish *w)
{
    u32 k;

    for (k = 0; k < 512u; k++)
        p[k] = 0;
    put32(p, MAGIC);
    p[4] = VERSION;
    p[5] = w->pad ? w->pad : KIND_SOUND;      /* item.c: the item type (a sound's entry keeps pad 0) */
    p[6] = (u8)(w->len >> 8);
    p[7] = (u8)w->len;
    put32(p + 8, w->h0);
    put32(p + 12, w->h1);
    for (k = 0; k < w->len; k++)
        p[HEAD + k] = w->rec[k];
    put32(p + AT_CHECK, check(p));
}

/* the record queued for the +Drive (a copy: the entry may change again before it is written) -> 0, or -1 */
int wish_enqueue(const struct wish *w)
{
    u32 k;

    for (k = wish_pend_head; k != wish_pend_tail; k++)
        if (get32(PCELL(k) + 8) == w->h0 && get32(PCELL(k) + 12) == w->h1)
            return 0;
    if (wish_pend_tail - wish_pend_head >= WISH_PEND) {
        wish_pend_lost++;
        requeue = 1;                            /* its entry stays without W_DISK: wish_poll queues it later */
        return -1;
    }
    cell_make(PCELL(wish_pend_tail), w);
    pend_at = WISH_FRAMES;
    wish_pend_tail++;                           /* last: the cell is whole before the reader can see it */
    return 0;
}

static u32 cell_of(u32 h0, u32 i)
{
    return CELL0 + (h0 % CELLS + i) % CELLS;
}

/* the queued cell P on the +Drive -> 1 done (written, or already there), 0 not now (an error: tried again later) */
static int write_cell(const u8 *p)
{
    u32 h0 = get32(p + 8), h1 = get32(p + 12), i;

    for (i = 0; i < PROBE; i++) {
        u32 s = cell_of(h0, i);
        if (WISH_BLK_READ(s, 512u, IO) != 0) {
            wish_io_fails++;
            return 0;
        }
        wish_cells_read++;
        if (cell_valid(IO)) {
            if (get32(IO + 8) == h0 && get32(IO + 12) == h1) {
                wish_cells_found++;
                return 1;
            }
            continue;
        }
        if (WISH_BLK_WRITE(s, 512u, p) != 0) {
            wish_io_fails++;
            return 0;
        }
        wish_cells_written++;
        return 1;
    }
    wish_pend_lost++;                           /* PROBE full cells in a row: the store wants collecting */
    return 1;
}

/* 2026-11-22 (dmove.c): a cell of the old table, filed into this one by its hash -> 1 filed (or already here),
 * 0 not a whole cell (skipped), -1 a read or write failed */
int wish_file_cell(const u8 *p)
{
    if (!cell_valid(p))
        return 0;
    u32 w0 = wish_io_fails;
    write_cell(p);
    return wish_io_fails != w0 ? -1 : 1;
}

/* every entry waiting for H0:H1 gets the record in IO (or, when FOUND is 0, is marked missing); under the lock,
 * which is not held across a read (a save in another task must never find it taken for long) -> 0 when the lock was
 * taken (nothing done) */
static int fill(u32 h0, u32 h1, int found)
{
    const u16 *slots = (const u16 *)WISH_AT(WISH_O_SLOTS);
    u32 k, n = found ? (u32)(IO[6] << 8 | IO[7]) : 0;

    if (!wish_take())
        return 0;                               /* tried again next pass */
    for (k = 0; k < wish_n; k++) {
        struct wish *w = wish_entry(slots[k]);
        u32 b;
        if (!(w->flags & W_WANT) || w->h0 != h0 || w->h1 != h1)
            continue;
        if (!found || n != w->len) {
            w->flags |= W_MISSING;
            continue;
        }
        for (b = 0; b < n; b++)
            w->rec[b] = IO[HEAD + b];
        w->flags = W_DISK | (wish_tlv_locked(w->rec, w->len) ? W_LOCKED : 0);
        wish_cache_put(w);
        wish_edits++;
    }
    wish_give();
    return 1;
}

/* the first entry still waiting for its record: its cell read -> 1 done, 0 not now. The walk reads the index
 * without the lock; fill() checks each entry again under it */
static int resolve_one(void)
{
    const u16 *slots = (const u16 *)WISH_AT(WISH_O_SLOTS);
    u32 k, i;

    for (k = 0; k < wish_n; k++) {
        struct wish *w = wish_entry(slots[k]);
        u32 h0, h1;
        if ((w->flags & (W_WANT | W_MISSING)) != W_WANT)
            continue;
        h0 = w->h0;
        h1 = w->h1;
        for (i = 0; i < PROBE; i++) {
            if (WISH_BLK_READ(cell_of(h0, i), 512u, IO) != 0) {
                wish_io_fails++;
                return 0;
            }
            wish_cells_read++;
            if (!cell_valid(IO))
                break;                          /* the end of its stretch: not on this +Drive */
            if (get32(IO + 8) == h0 && get32(IO + 12) == h1 && wish_hash_ok(IO + HEAD, IO[6] << 8 | IO[7], h0, h1)) {
                wish_resolved++;
                fill(h0, h1, 1);
                return 1;
            }
        }
        wish_missing++;
        fill(h0, h1, 0);
        return 1;
    }
    wish_wants = 0;                             /* none left */
    return 1;
}

/* every entry linked (hashed, not waiting) but not on the +Drive queued again, once the queue has room */
static void queue_again(void)
{
    const u16 *slots = (const u16 *)WISH_AT(WISH_O_SLOTS);
    u32 k;

    if (!wish_take())
        return;
    requeue = 0;
    for (k = 0; k < wish_n; k++) {
        struct wish *w = wish_entry(slots[k]);
        if (w->len && !(w->flags & (W_DISK | W_WANT | W_DIRTY)) && wish_enqueue(w) == 0)
            w->flags |= W_DISK;
    }
    wish_give();
}

/* --- travel: PUT and GET over our SysEx channel (link.c smp_rx, commands 12 and 13) ------------------------- */
#define CMD_PUT 12u
#define CMD_GET 13u
#define GET_CHUNK 128u                          /* a reply's bytes of record (link.c's reply buffer: 160) */

static struct wish put_w D_;                    /* a PUT's record, until the UI loop files it */
static struct wish got_w D_;                    /* a GET's record, read from its cell by the UI loop */
volatile u32 wish_put_wait D_ = 0;              /* 1: put_w waits for the UI loop */
volatile u32 wish_got_state D_ = 0;             /* got_w: 1 to be read, 2 read, 3 on no cell of this +Drive */
u32 wish_puts D_ = 0, wish_gets D_ = 0;

/* PUT u16 length, the record -> h0, h1 (the hash it is filed under). 1: not a record; 3: not now (no table yet);
 * 5: the last PUT is not filed yet (ask again) */
static u32 put_rx(const u8 *a, u32 k, u8 *rp, u32 r, u8 *st)
{
    u32 len = k >= 2u ? (u32)(a[0] << 8 | a[1]) : 0u, b;

    if (!len || len > WISH_MAX || k != 2u + len || !wish_tlv_valid(a + 2, len)) {
        *st = 1;
        return r;
    }
    if (!wish_ready || wish_put_wait) {
        *st = wish_ready ? 5 : 3;
        return r;
    }
    for (b = 0; b < len; b++)
        put_w.rec[b] = a[2 + b];
    put_w.len = (u16)len;
    put_w.flags = 0;
    wish_hash(put_w.rec, len, &put_w.h0, &put_w.h1);
    wish_puts++;
    wish_put_wait = 1;                          /* last: whole before the UI loop looks */
    put32(rp + r, put_w.h0);
    put32(rp + r + 4, put_w.h1);
    return r + 8;
}

/* GET h0, h1, u16 offset -> u16 length, u16 offset, up to GET_CHUNK bytes of the record from OFFSET. 1: bad
 * arguments; 3: no cell of this +Drive holds it; 5: being read from the +Drive (ask again) */
static u32 get_rx(const u8 *a, u32 k, u8 *rp, u32 r, u8 *st)
{
    u32 h0, h1, off, len = 0, b;
    const u8 *rec = 0;

    if (k != 10u) {
        *st = 1;
        return r;
    }
    h0 = get32(a);
    h1 = get32(a + 4);
    off = (u32)(a[8] << 8 | a[9]);
    if (wish_take()) {                          /* a sound in RAM holds it: copied under the lock */
        const struct wish *w = wish_cache_get(h0, h1);
        if (w && w->h0 == h0 && w->h1 == h1 && w->len && !(w->flags & (W_DIRTY | W_WANT)) && off <= w->len) {
            len = w->len;
            for (b = off; b < len && b < off + GET_CHUNK; b++)
                rp[r + 4u + b - off] = w->rec[b];
            rec = w->rec;
        }
        wish_give();
    }
    if (!rec && wish_got_state == 2u && got_w.h0 == h0 && got_w.h1 == h1 && off <= got_w.len) {
        len = got_w.len;
        for (b = off; b < len && b < off + GET_CHUNK; b++)
            rp[r + 4u + b - off] = got_w.rec[b];
        rec = got_w.rec;
    }
    if (!rec) {
        int same = got_w.h0 == h0 && got_w.h1 == h1;
        if (same && wish_got_state == 3u) {
            *st = 3;
        } else {
            if (wish_got_state != 1u && !(same && wish_got_state == 2u)) {   /* one read at a time */
                got_w.h0 = h0;
                got_w.h1 = h1;
                wish_got_state = 1;
            }
            *st = (same && wish_got_state == 2u) ? 1 : 5;                     /* 2: OFFSET past its end */
        }
        return r;
    }
    wish_gets++;
    rp[r] = (u8)(len >> 8);
    rp[r + 1] = (u8)len;
    rp[r + 2] = (u8)(off >> 8);
    rp[r + 3] = (u8)off;
    return r + 4u + (len - off < GET_CHUNK ? len - off : GET_CHUNK);
}

/* link.c smp_rx: commands 12 (PUT) and 13 (GET); RQ the request (seq, cmd, arguments), N its bytes */
u32 wish_rx(u32 cmd, const u8 *rq, u32 n, u8 *rp, u32 r, u8 *st)
{
    if (n < 3u) {
        *st = 1;
        return r;
    }
    return cmd == CMD_PUT ? put_rx(rq + 3, n - 3u, rp, r, st) : get_rx(rq + 3, n - 3u, rp, r, st);
}

/* the UI loop's part: a PUT filed (queued for its cell, and given to every sound waiting for it); a GET's cell read */
static void travel_poll(void)
{
    u32 i;

    if (wish_put_wait && wish_enqueue(&put_w) == 0) {
        cell_make(IO, &put_w);
        if (fill(put_w.h0, put_w.h1, 1))
            wish_put_wait = 0;                  /* else: the lock was taken, filed again next pass (queued once) */
    }
    if (wish_got_state != 1u)
        return;
    for (i = 0; i < PROBE; i++) {
        if (WISH_BLK_READ(cell_of(got_w.h0, i), 512u, IO) != 0) {
            wish_io_fails++;
            return;                             /* tried again next pass */
        }
        wish_cells_read++;
        if (!cell_valid(IO))
            break;
        if (get32(IO + 8) == got_w.h0 && get32(IO + 12) == got_w.h1
            && wish_hash_ok(IO + HEAD, IO[6] << 8 | IO[7], got_w.h0, got_w.h1)) {
            got_w.len = (u16)(IO[6] << 8 | IO[7]);
            for (i = 0; i < got_w.len; i++)
                got_w.rec[i] = IO[HEAD + i];
            wish_got_state = 2;
            return;
        }
    }
    wish_got_state = 3;
}

/* from the UI loop (page.c's wr_poll), every pass */
void wish_poll(void)
{
    u32 done = 0;

    if (!wish_ready || !ok())
        return;
    travel_poll();
    if (requeue && wish_pend_tail - wish_pend_head < WISH_PEND / 2u)
        queue_again();
    if (wish_pend_head == wish_pend_tail) {
        pj_seen = ins_wr_head;
    } else if ((u32)(WISH_FRAMES - pend_at) >= SETTLE || ins_wr_head != pj_seen) {
        while (wish_pend_head != wish_pend_tail && done < PER_PASS) {
            if (!write_cell(PCELL(wish_pend_head)))
                break;
            wish_pend_head++;
            done++;
        }
    }
    while (wish_wants && done < PER_PASS) {
        if (!resolve_one())
            break;
        done++;
    }
}
