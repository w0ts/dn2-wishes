/* The inserts saved with the project (docs/inserts.md "Saving"; 2026-11-10, the User: "works with
 * project save"). Stock has no record for them (16 tracks x 2 slots x 8 values), so, as the per-project
 * pools (csrc/sampler/pools.c), they keep a record of their own per project slot on the +Drive, beside
 * stock's project, following stock's project code:
 *
 *   - every time stock writes a project slot (0x40040190(project, slot, cb): SAVE and SAVE AS write the
 *     slot and the temp slot 128, a LOAD and a NEW write the temp slot, the OS's autosave the temp slot;
 *     hooks.S ins_pj_write_hook notes the slot), the record of that slot is written from what the
 *     inserts hold;
 *   - a LOAD of slot p (pools' hook counters): record p's values are the inserts' (none: the defaults),
 *     then record 128 is written (stock wrote its temp slot before the LOAD's success);
 *   - a NEW: the defaults (every slot OFF), written as record 128 and, for a NEW into a slot, that slot's;
 *   - an edit by the knobs: record 128 (the working copy, as stock's temp slot) written 2 s after the last;
 *   - power-on: record 128, the working copy stock's temp slot also is.
 *
 *   0x6E0400 + 2 p + c   record p (0..127 the projects, 128 the working copy), copy c (0, 1): one sector,
 *                        'DN2I', version, p, sequence, the 32 records (type, MIX, the type's K1..K6),
 *                        its check; written into the older copy, the newer whole copy is read
 *
 * Between the pools' lists (to 0x6E02FF) and the library's index (lib.c, 0x6F0000), in sectors nothing
 * else uses. A record names types by their number for good (dnfw.inserts.design), so a build that knows
 * fewer types reads an unknown one as OFF. Only this file's two buffers and the sectors above are written. */

typedef unsigned int u32;
typedef unsigned char u8;
#define D_ __attribute__((section(".data")))

#define BLK_READ  ((int (*)(u32, u32, void *))0x4012C87Au)       /* pools.c's */
#define BLK_WRITE ((int (*)(u32, u32, const void *))0x4012CA60u)
#define BLK_READY (*(volatile u32 *)0x4461C68Cu)
#define BLK_SECTORS (*(volatile u32 *)0x4461C6B0u)

#define INS_BASE 0x6E0400u
#define INS_N 129
#define INS_WORK 128
#define INS_END (INS_BASE + 2u * (u32)INS_N)
_Static_assert(INS_BASE >= 0x6E0300u && INS_END <= 0x6F0000u,
               "the records lie between the pools' lists and the library's index");
#define MAGIC 0x444E3249u                       /* 'DN2I' */
#define VERSION 1u
#define CHECK_XOR 0x494E5331u
#define REC_WORDS 64u                           /* 32 records x 8 bytes */
#define W_REC 4u
#define W_CHECK (W_REC + REC_WORDS)
#define SETTLE 3000u                            /* smp_periods: 2 s (1,500 a second) */

extern volatile u32 smp_pj_loads, smp_pj_news, smp_pj_begins, smp_pj_ends, smp_pj_last, smp_periods;
extern volatile int smp_pj_slot, smp_pj_newslot;
extern int smp_er_lock;
extern u32 ins_edits;
extern void ins_record(int t, int j, u8 *f);
extern void ins_set_record(int t, int j, const u8 *f);
extern void ins_defaults(void);
extern void ins_loaded(void);

volatile u32 ins_wr_ring[8] D_;                 /* hooks.S: the slots stock wrote, newest at head - 1 */
volatile u32 ins_wr_head D_ = 0;
u32 ins_st_writes D_ = 0, ins_st_loads D_ = 0, ins_st_fails D_ = 0;    /* for the gate */
static u32 sec[128] D_;                         /* one sector */
static int booted D_ = 0;
static u32 wr_tail D_ = 0, seen_loads D_ = 0, seen_news D_ = 0, edits_seen D_ = 0, edits_at D_ = 0;

static int ok(void)
{
    return BLK_READY && BLK_SECTORS >= INS_END && !smp_er_lock;
}

static u32 check(const u32 *w)
{
    u32 a = 1, b = 0;
    const u8 *p = (const u8 *)w;
    for (u32 k = 0; k < 4u * W_CHECK; k++) {
        a += p[k];
        b += a;
    }
    return (b << 16 ^ a) ^ CHECK_XOR;
}

/* copy c of record p into sec: its sequence + 1, or 0 when it is not a whole record of p */
static u32 read_copy(int p, int c)
{
    if (!ok() || BLK_READ(INS_BASE + 2u * (u32)p + (u32)c, 512u, sec) != 0)
        return 0;
    if (sec[0] != MAGIC || sec[1] != VERSION || sec[2] != (u32)p || sec[W_CHECK] != check(sec))
        return 0;
    return sec[3] + 1u;
}

/* record p into the inserts: 1, or 0 (none whole: nothing changed) */
static int load(int p)
{
    u32 a = read_copy(p, 0), b = read_copy(p, 1);
    if (!a && !b)
        return 0;
    if (a > b && read_copy(p, 0) != a)
        return 0;                               /* (sec holds copy 1: copy 0 read again) */
    const u8 *r = (const u8 *)(sec + W_REC);
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++)
            ins_set_record(t, j, r + 8 * (2 * t + j));
    ins_loaded();
    ins_st_loads++;
    return 1;
}

/* the inserts into record p's older copy */
static void save(int p)
{
    if (p < 0 || p >= INS_N || !ok())
        return;
    u32 a = read_copy(p, 0), b = read_copy(p, 1);
    int c = a > b ? 1 : 0;                      /* the older (or a broken one) */
    u32 seq = a > b ? a : b;                    /* the newer's sequence + 1 (0 when there is none) */
    sec[0] = MAGIC;
    sec[1] = VERSION;
    sec[2] = (u32)p;
    sec[3] = seq;
    u8 *r = (u8 *)(sec + W_REC);
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++)
            ins_record(t, j, r + 8 * (2 * t + j));
    sec[W_CHECK] = check(sec);
    for (u32 k = W_CHECK + 1u; k < 128u; k++)
        sec[k] = 0;
    if (BLK_WRITE(INS_BASE + 2u * (u32)p + (u32)c, 512u, sec) == 0)
        ins_st_writes++;
    else
        ins_st_fails++;
}

/* from link.c's UI pass, after the pools' poll (the +Drive up) */
void ins_store_poll(void)
{
    if (!ok())
        return;
    if (!booted) {                              /* power-on: the working copy */
        booted = 1;
        load(INS_WORK);
        seen_loads = seen_news = 0;             /* a LOAD the OS did already: below */
        wr_tail = ins_wr_head;
        edits_seen = ins_edits;
    }
    if (smp_pj_begins != smp_pj_ends)
        return;                                 /* a LOAD under way: after it */
    u32 L = smp_pj_loads, N = smp_pj_news;
    if (L != seen_loads || N != seen_news) {
        seen_loads = L;
        seen_news = N;
        if (smp_pj_last == 2) {                 /* NEW: the defaults */
            ins_defaults();
            ins_loaded();
            if (smp_pj_newslot >= 0 && smp_pj_newslot < 128)
                save(smp_pj_newslot);
        } else {
            int s = smp_pj_slot;
            if (!(s >= 0 && s < 128 && load(s))) {
                ins_defaults();                 /* a project saved before this build: every slot OFF */
                ins_loaded();
            }
        }
        save(INS_WORK);
        wr_tail = ins_wr_head;                  /* stock's writes during it: covered */
        edits_seen = ins_edits;
        return;
    }
    while (wr_tail != ins_wr_head) {            /* stock wrote these slots: ours follow */
        u32 s = ins_wr_ring[wr_tail & 7u];
        wr_tail++;
        if (s < (u32)INS_N)
            save((int)s);
        if (s == INS_WORK)
            edits_seen = ins_edits;
    }
    if (ins_edits != edits_seen) {              /* an edit: the working copy once the knobs settle */
        static u32 last D_ = 0;
        if (ins_edits != last) {                /* (still turning: wait from this edit on) */
            last = ins_edits;
            edits_at = smp_periods;
            return;
        }
        if (smp_periods - edits_at < SETTLE)
            return;
        edits_seen = ins_edits;
        save(INS_WORK);
    }
}
