/* 2026-11-22 (v0.69.2): our +Drive data out of upstream's places, once (csrc/include/dmove.h, docs/memory-map.md).
 *
 * The User: "our +Drive data lives where upstream names nothing" (the rule), "go for double safe" (every move copies,
 * even the two that would be rebuilt or ignored), and upstream's own features (its tunings, its bank lists) back at
 * upstream's own places. dm_run() runs the moves once a boot, from pools.c's power-on (after the sample link's RAM
 * check, before the bank lists are read); dm_ok() answers 1 once every move is done, and tune.c and the wishes
 * record keep off the +Drive until it does: nothing reads or writes a place that is still moving.
 *
 * The order: the inserts' move first (inserts/store.c, its own mark: the tunings take its old sectors), then
 *   1 SAFE MODE's record    (old 0x6E0300: copied when it is one; normal.c reads the record to know where)
 *   2 the DSP program's copy (old 0x6E8000: its 2,049 sectors when its header is one; lzma7cache.c likewise)
 *   3 our tunings           (each sector of 0x6E0600.. that is a record ('DN2T'); a 'DN2T' sector at the new place
 *                            with none to copy over it is cleared: a stale upstream record never comes alive)
 *   4 bank lists A          (each project's copy whose header is whole: body, then header; a whole-looking header
 *                            at the new place with nothing copied over it is cleared)
 *   5 the wishes record     (every whole cell of the old 59,392 filed again into the new 92,160 by its hash)
 *   6 bank lists B          (as 4)
 * each bit set in the move record (DM_RECORD) when its move is done; a failed read or write stops there, and the
 * next boot goes on (every move can run again: a copy is the same bytes, a cell already filed is found). The old
 * sectors are only read. ERASE MOD DATA never erases the move record (erase.c). */
#include "../include/dmove.h"

typedef unsigned int u32;
typedef unsigned char u8;
#define D_ __attribute__((section(".data")))

#if !defined(BANK_RAM)
#error "BANK_RAM is passed by the build (dnfw.waverider.cpage)"
#endif

#define BLK_READ  ((int (*)(u32, u32, void *))0x4012C87Au)       /* pools.c's */
#define BLK_WRITE ((int (*)(u32, u32, const void *))0x4012CA60u)
#define BLK_READY (*(volatile u32 *)0x4461C68Cu)
#define BLK_SECTORS (*(volatile u32 *)0x4461C6B0u)
/* the buffer: pools.c's bank list staging (BANK_RAM + 0x80000, 256 KB), unused until the bank lists are read,
 * which waits for this */
#define BUF ((u8 *)(BANK_RAM + 0x80000u))
#define CHUNK 128u                                      /* sectors a call (the driver's 64 KB) */
#define TN_MAGIC 0x444E3254u                            /* 'DN2T' (tune.c) */
#define SM_MAGIC_REC 0x444E3242u                        /* 'DN2B' (safemode/sm.h) */
#define C_MAGIC 0x444E3743u                             /* 'DN7C' (waverider/lzma7cache.c) */
#define BL_MAGIC 0x444E3242u                            /* 'DN2B' (pools.c) */
#define PL_VERSION 1u

extern int smp_er_lock;                                 /* erase.c */
extern int ins_move_now(void);                          /* inserts/store.c: its move, -> 1 done */
extern int wish_file_cell(const u8 *cell);              /* wishes/store.c: a whole old cell filed -> 0 ok */

u32 dm_bits D_ = 0;                                     /* what has moved (the move record's bits) */
u32 dm_tried D_ = 0, dm_runs D_ = 0, dm_fails D_ = 0;   /* (for the gate) */
u32 dm_copied[6] D_ = {0, 0, 0, 0, 0, 0};               /* sectors (cells for the wishes) copied, per move */

static u32 *W(void) { return (u32 *)BUF; }

static int ready(void)
{
    return BLK_READY && BLK_SECTORS > 0x6FF000u && !smp_er_lock;
}

static int rd(u32 s, u32 n) { return BLK_READ(s, 512u * n, BUF); }
static int wr(u32 s, u32 n) { return BLK_WRITE(s, 512u * n, BUF); }

static void zero(u32 words)
{
    for (u32 k = 0; k < words; k++)
        W()[k] = 0;
}

static int set_bit(u32 bit)
{
    zero(128);
    W()[0] = DM_MAGIC;
    W()[1] = ~DM_MAGIC;
    W()[2] = dm_bits | bit;
    W()[3] = W()[2] ^ DM_XOR;
    if (wr(DM_RECORD, 1))
        return -1;
    dm_bits |= bit;
    return 0;
}

static u32 csum(const u8 *p, u32 n)                     /* pools.c's */
{
    u32 a = 1, b = 0;
    for (u32 k = 0; k < n; k++) {
        a += p[k];
        b += a;
    }
    return b << 16 ^ a;
}

/* N sectors OLD -> NEW, in the driver's calls -> 0 ok */
static int span(u32 old, u32 new_, u32 n)
{
    for (u32 o = 0; o < n; o += CHUNK) {
        u32 k = n - o < CHUNK ? n - o : CHUNK;
        if (rd(old + o, k) || wr(new_ + o, k))
            return -1;
    }
    return 0;
}

static int move_safe(void)                              /* 1: the record, when it is one */
{
    if (rd(DM_SAFE_OLD, 1))
        return -1;
    if (W()[0] == SM_MAGIC_REC) {
        if (wr(DM_SAFE_NEW, 1))
            return -1;
        dm_copied[0] = 1;
    }
    return 0;
}

static int move_dsp(void)                               /* 2: the copy, when its header is one */
{
    if (rd(DM_DSP_OLD, 1))
        return -1;
    if (W()[0] != C_MAGIC)
        return 0;
    if (span(DM_DSP_OLD + 1u, DM_DSP_NEW + 1u, DM_DSP_N - 1u) || rd(DM_DSP_OLD, 1) || wr(DM_DSP_NEW, 1))
        return -1;                                      /* (the header last, as lzma7cache.c writes it) */
    dm_copied[1] = DM_DSP_N;
    return 0;
}

static int move_tune(void)                              /* 3: each record sector; a stale one at the new place cleared */
{
    for (u32 k = 0; k < DM_TUNE_N; k++) {
        if (rd(DM_TUNE_OLD + k, 1))
            return -1;
        if (W()[0] == TN_MAGIC) {
            if (wr(DM_TUNE_NEW + k, 1))
                return -1;
            dm_copied[2]++;
            continue;
        }
        if (rd(DM_TUNE_NEW + k, 1))
            return -1;
        if (W()[0] == TN_MAGIC) {
            zero(128);
            if (wr(DM_TUNE_NEW + k, 1))
                return -1;
        }
    }
    return 0;
}

static int bl_whole(int p)                              /* the header in BUF: project P's, whole (any generation) */
{
    const u32 *h = W();
    return h[0] == BL_MAGIC && h[1] == PL_VERSION && h[2] == (u32)p && h[11] == (csum(BUF, 44) ^ 0x424C4B31u);
}

static int move_bl(u32 old, u32 new_, int p0, u32 slot)   /* 4, 6: each whole list (body, then header) */
{
    for (int i = 0; i < 64; i++)
        for (u32 c = 0; c < 2u; c++) {
            u32 at = DM_BL_SPAN * (2u * (u32)i + c);
            if (rd(old + at, 1))
                return -1;
            if (bl_whole(p0 + i)) {
                if (span(old + at + 1u, new_ + at + 1u, DM_BL_SPAN - 1u) || rd(old + at, 1) || wr(new_ + at, 1))
                    return -1;
                dm_copied[slot] += DM_BL_SPAN;
                continue;
            }
            if (rd(new_ + at, 1))
                return -1;
            if (W()[0] == BL_MAGIC) {                   /* (an upstream list there, from its firmware: never ours) */
                zero(128);
                if (wr(new_ + at, 1))
                    return -1;
            }
        }
    return 0;
}

static int move_wish(void)                              /* 5: every whole cell, filed again by its hash */
{
    for (u32 o = 0; o < DM_WISH_OLD_N; o += CHUNK) {
        u32 k = DM_WISH_OLD_N - o < CHUNK ? DM_WISH_OLD_N - o : CHUNK;
        if (rd(DM_WISH_OLD + o, k))
            return -1;
        for (u32 j = 0; j < k; j++) {
            const u8 *cell = BUF + 512u * j;
            if (cell[0] != 'D' || cell[1] != 'N' || cell[2] != '2' || cell[3] != 'W')
                continue;
            int r = wish_file_cell(cell);
            if (r < 0)
                return -1;
            if (r > 0)
                dm_copied[4]++;
        }
    }
    return 0;
}

static void run(void)
{
    dm_runs++;
    if (rd(DM_RECORD, 1))
        return;
    dm_bits = dm_bits_of(W());
    static int (*const step[6])(void) = {move_safe, move_dsp, move_tune, 0, move_wish, 0};
    for (u32 s = 0; s < 6u; s++) {
        u32 bit = 1u << s;
        if (dm_bits & bit)
            continue;
        int r = s == 3 ? move_bl(DM_BLA_OLD, DM_BLA_NEW, 0, 3) : s == 5 ? move_bl(DM_BLB_OLD, DM_BLB_NEW, 64, 5)
                : step[s]();
        if (r || set_bit(bit)) {
            dm_fails++;
            return;
        }
    }
}

/* pools.c's power-on (smp_pl_boot, after the sample link's RAM check, before the bank lists are read): the moves,
 * once a boot -> 1 when everything has moved */
int dm_run(void)
{
    if (dm_bits == DM_ALL)
        return 1;
    if (!dm_tried && ready() && ins_move_now()) {     /* (the inserts' old sectors are the tunings' new ones) */
        dm_tried = 1;
        run();
    }
    return dm_bits == DM_ALL;
}

/* -> 1 when everything has moved (the tunings and the wishes record wait for it; it never runs the moves itself) */
int dm_ok(void)
{
    return dm_bits == DM_ALL;
}
