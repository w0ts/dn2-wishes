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
 *   0x5FF000 + 2 p + c   record p (0..127 the projects, 128 the working copy), copy c (0, 1): one sector,
 *                        'DN2I', version, p, sequence, the 32 records (type, MIX, the type's K1..K6),
 *                        its check; written into the older copy, the newer whole copy is read
 *   0x5FF102             the move's mark ('DN2M'): the records were copied from their old place
 *
 * 2026-11-22 (v0.69.1, the User: "move our stuff"): until v0.68.1 the records were at 0x6E0400 + 2 p + c
 * (0x6E0400..0x6E0501), sectors upstream gives its tunings (0x6E0400) and PERFORM (0x6E0500..0x6E05FF). They
 * now sit past the bank lists (0x5F0000..0x5FE7FF), below the pool image (0x600000): sectors upstream never
 * names (docs/memory-map.md, "+Drive"). The first time the +Drive is up without the mark, every whole old
 * copy is copied, byte for byte, to the same copy of the same record here, then the mark is written; the old
 * sectors are only read, never written, and never read again once the mark is there (ERASE MOD DATA erases
 * the records, not the mark, so an erase does not bring the old ones back). A record names types by their number for good (dnfw.inserts.design), so a build that knows
 * fewer types reads an unknown one as OFF. Only this file's two buffers and the sectors above are written. */

typedef unsigned int u32;
typedef unsigned char u8;
#define D_ __attribute__((section(".data")))

#define BLK_READ  ((int (*)(u32, u32, void *))0x4012C87Au)       /* pools.c's */
#define BLK_WRITE ((int (*)(u32, u32, const void *))0x4012CA60u)
#define BLK_READY (*(volatile u32 *)0x4461C68Cu)
#define BLK_SECTORS (*(volatile u32 *)0x4461C6B0u)

#define INS_BASE 0x5FF000u
#define INS_N 129
#define INS_WORK 128
#define INS_END (INS_BASE + 2u * (u32)INS_N)
#define INS_MARK INS_END                        /* the move's mark, outside ERASE MOD DATA's records */
#define INS_OLD 0x6E0400u                       /* until v0.68.1: read once, for the move */
_Static_assert(INS_BASE >= 0x5F0000u + 2u * 64u * 464u && INS_MARK < 0x600000u,
               "past the bank lists (pools.c BL_END2), below the pool image (link.c STORE_SECTOR)");
#define MAGIC 0x444E3249u                       /* 'DN2I' */
#define MOVE_MAGIC 0x444E324Du                  /* 'DN2M' */
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
/* 2026-11-11: the send pages' second page (csrc/fxpage) rides in the same sector, after the inserts' check:
 * 'FXP2', the sixteen values (four words), its own check. A record without it (a project saved before) is
 * the defaults; an older build reads the record as before and ignores it. */
extern void fxp_record(u8 *f);
extern void fxp_set_record(const u8 *f);
extern void fxp_defaults(void);
#define FXP_MAGIC 0x46585032u
#define W_FXP (W_CHECK + 1u)                    /* magic, 4 words of values, check */
static u32 fxp_check(const u32 *w)
{
    return (w[W_FXP + 1] + 3u * w[W_FXP + 2] + 5u * w[W_FXP + 3] + 7u * w[W_FXP + 4]) ^ CHECK_XOR;
}

volatile u32 ins_wr_ring[8] D_;                 /* hooks.S: the slots stock wrote, newest at head - 1 */
volatile u32 ins_wr_head D_ = 0;
u32 ins_st_writes D_ = 0, ins_st_loads D_ = 0, ins_st_fails D_ = 0;    /* for the gate */
u32 ins_st_moved D_ = 0, ins_st_copied D_ = 0;  /* the move: 1 done (2: found done), the copies made */
/* v0.69.2: the +Drive's DMA lands here, outside the C chunk (emulib/ramguard.py: no DMA into a chunk the build
 * places): the unused tail of pools.c's bank list staging (BL_W ends at +0x3A000 of BANK_RAM + 0x80000, BL_H is at
 * +0x40000), one 512-byte slot each: SAFE MODE's record +0x3F000, the DSP copy's header +0x3F200, the inserts +0x3F400 */
#define sec ((u32 *)(BANK_RAM + 0x80000u + 0x3F400u))
int ins_st_booted D_ = 0;                       /* (the gate's power cycle sets it to 0) */
static u32 wr_tail D_ = 0, seen_loads D_ = 0, seen_news D_ = 0, edits_seen D_ = 0, edits_at D_ = 0;

static int ok(void)
{
    return BLK_READY && BLK_SECTORS > INS_MARK && !smp_er_lock;
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

/* copy c of record p at BASE into sec: its sequence + 1, or 0 when it is not a whole record of p */
static u32 read_at(u32 base, int p, int c)
{
    if (!ok() || BLK_READ(base + 2u * (u32)p + (u32)c, 512u, sec) != 0)
        return 0;
    if (sec[0] != MAGIC || sec[1] != VERSION || sec[2] != (u32)p || sec[W_CHECK] != check(sec))
        return 0;
    return sec[3] + 1u;
}

static u32 read_copy(int p, int c)
{
    return read_at(INS_BASE, p, c);
}

/* the move (2026-11-22): once, the old place's whole copies to the new place, then the mark */
static void move_once(void)
{
    if (ins_st_moved)
        return;
    if (BLK_READ(INS_MARK, 512u, sec) == 0 && sec[0] == MOVE_MAGIC && sec[1] == ~MOVE_MAGIC) {
        ins_st_moved = 2;
        return;
    }
    for (int p = 0; p < INS_N; p++)
        for (int c = 0; c < 2; c++) {
            if (!read_at(INS_OLD, p, c))
                continue;                       /* (no whole record there: an upstream record, PERFORM's) */
            if (BLK_WRITE(INS_BASE + 2u * (u32)p + (u32)c, 512u, sec) != 0) {
                ins_st_fails++;
                return;                         /* (no mark: the next power-on tries again) */
            }
            ins_st_copied++;
        }
    for (u32 k = 0; k < 128u; k++)
        sec[k] = 0;
    sec[0] = MOVE_MAGIC;
    sec[1] = ~MOVE_MAGIC;
    sec[2] = ins_st_copied;
    if (BLK_WRITE(INS_MARK, 512u, sec) == 0)
        ins_st_moved = 1;
    else
        ins_st_fails++;
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
    if (sec[W_FXP] == FXP_MAGIC && sec[W_FXP + 5] == fxp_check(sec))
        fxp_set_record((const u8 *)(sec + W_FXP + 1));
    else
        fxp_defaults();
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
    sec[W_FXP] = FXP_MAGIC;
    fxp_record((u8 *)(sec + W_FXP + 1));
    sec[W_FXP + 5] = fxp_check(sec);
    if (BLK_WRITE(INS_BASE + 2u * (u32)p + (u32)c, 512u, sec) == 0)
        ins_st_writes++;
    else
        ins_st_fails++;
}

/* 2026-11-22 (dmove.c): the move asked for before the others (the tunings take its old sectors) -> 1 done */
int ins_move_now(void)
{
    if (!ok())
        return 0;
    move_once();
    return ins_st_moved != 0;
}

/* from link.c's UI pass, after the pools' poll (the +Drive up) */
void ins_store_poll(void)
{
    if (!ok())
        return;
    if (!ins_st_booted) {                       /* power-on: the working copy */
        ins_st_booted = 1;
        ins_st_moved = 0;
        move_once();                            /* 2026-11-22: the records' old place, once */
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
            fxp_defaults();
            ins_loaded();
            if (smp_pj_newslot >= 0 && smp_pj_newslot < 128)
                save(smp_pj_newslot);
        } else {
            int s = smp_pj_slot;
            if (!(s >= 0 && s < 128 && load(s))) {
                ins_defaults();                 /* a project saved before this build: every slot OFF */
                fxp_defaults();
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
