/* SAFE MODE, the normal boot's half (docs/safe-mode.md), linked into the page renderer's chunk.
 *
 *   sm_late   from dn7_late (lzma7late.S) at 0x400cf0f2, the eMMC-ready point, before the DSP upload and before
 *             any UI, MIDI or +Drive task exists: reads the record (SM_SECTOR). The last boot never became healthy
 *             (pending) -> SAFE mark, record written, our soft reset; else pending = 1, written.
 *   sm_poll   from wr_poll, every UI pass: after SM_HEALTHY panel ticks the record is written with pending = 0,
 *             once. In the first SM_STOP_TICKS, STOP held alone without a break for SM_STOP_HOLD (1 s; no other
 *             key, not the maintenance combination's boot flag) -> SAFE mark, record written with pending = 0, our
 *             soft reset. A tap does nothing here.
 *
 * Everything fails open: no kernel chunk (its head's magic), the +Drive not up, a failed read or a bad record ->
 * a normal boot. Nothing here runs in SAFE MODE: the kernel puts stock's bytes back at dn7_late's and wr_poll's
 * call sites. */

#include "sm.h"
#include "../include/dmove.h"

typedef uint32_t u32;

#define SM_READ   ((int (*)(u32, u32, void *))0x4012C87Au)          /* the stock block driver: 0 ok */
#define SM_WRITE  ((int (*)(u32, u32, const void *))0x4012CA60u)
#define SM_READY  (*(volatile u32 *)0x4461C68Cu)
#define SM_SECTORS (*(volatile u32 *)0x4461C6B0u)
#define SM_TICK   (*(volatile u32 *)0x466768B0u)                     /* the panel module's tick, 0..4095, wraps */
#define SM_FLAGS  (*(volatile u32 *)0x40287A60u)                     /* the boot flags the bootstrap passes */
#define SM_FLAG_MAINT 0x20u                                          /* the maintenance combination (or marker) */
/* the panel's buttons as stock keeps them: one byte a channel of the panel MCU's UART stream, the last state it sent
 * (0x4011fc8c stores it, 0x4011fac6 reads it for "is this key down"). Every button, FUNC included: FUNC never reaches
 * the UI queue as a key item, so rec.c's smp_held_lo cannot see it (measured 2026-11-21: FUNC held, smp_held_lo 0,
 * this byte 0x01). STOP is channel 2, bit 4 (code 21). */
#define SM_KEYS       ((volatile const uint8_t *)0x445A2E30u)
#define SM_KEY_CHANS  8u                                             /* codes 1..64: channels 0..7 */
#define SM_STOP_CHAN  2u
#define SM_STOP_MASK  0x10u
#define SM_STOP_TICKS 360u                                           /* about 3 s of the UI's first passes */
#define SM_STOP_HOLD  121u                                           /* STOP held alone this long: 1 s (121 a second) */


/* v0.69.2: the +Drive's DMA lands here, outside the C chunk (emulib/ramguard.py: no DMA into a chunk the build
 * places): the unused tail of pools.c's bank list staging (BL_W ends at +0x3A000 of BANK_RAM + 0x80000, BL_H is at
 * +0x40000), one 512-byte slot each: SAFE MODE's record +0x3F000, the DSP copy's header +0x3F200, the inserts +0x3F400 */
#define sm_buf ((uint8_t *)(BANK_RAM + 0x80000u + 0x3F000u))
u32 sm_state __attribute__((section(".data"))) = 0;     /* 0 not run, 1 pending written, 2 healthy written,
                                                         * 3 went SAFE, 4 tries spent, 5 no drive, 6 a read failed,
                                                         * 7 a write failed, 8 no kernel, 9 NORMAL-ONCE */
static u32 sm_mono __attribute__((section(".data"))) = 0, sm_last __attribute__((section(".data"))) = 0;
static u32 sm_polls __attribute__((section(".data"))) = 0, sm_done __attribute__((section(".data"))) = 0;
static u32 sm_stop_on __attribute__((section(".data"))) = 0, sm_stop_at __attribute__((section(".data"))) = 0;

static void copy32(void *dst, const void *src, u32 bytes)   /* (no memcpy in this chunk's link) */
{
    volatile u32 *d = (volatile u32 *)dst;
    const u32 *p = (const u32 *)src;
    for (u32 i = 0; i < bytes / 4u; i++)
        d[i] = p[i];
}

static const struct sm_head *head(void)
{
    const struct sm_head *h = (const struct sm_head *)SM_LOAD;
    return h->magic == SM_MAGIC_HEAD ? h : 0;
}

/* v0.69.2 (csrc/include/dmove.h): the record's place. Its bit in the move record: DM_SAFE_NEW. Else the move, once
 * (the first access of the first boot, sm_late): the old record (when it is one) copied to DM_SAFE_NEW, the bit set
 * (the move record's other bits kept), then DM_SAFE_NEW. Any read or write that fails: the old place, as before (the
 * next access tries again). The old sector is only read. */
u32 sm_moved __attribute__((section(".data"))) = 0;     /* 1 found moved, 2 moved now (with a copy), 3 moved now */
static u32 sm_sector(void)
{
    if (SM_READ(DM_RECORD, 512u, sm_buf))
        return 0;                                       /* (unread: neither place, a failed read) */
    u32 bits = dm_bits_of((const uint32_t *)sm_buf);
    if (bits & DM_SAFE) {
        sm_moved = sm_moved ? sm_moved : 1u;
        return DM_SAFE_NEW;
    }
    if (SM_READ(SM_SECTOR, 512u, sm_buf))
        return SM_SECTOR;
    u32 copied = ((const struct sm_rec *)sm_buf)->magic == SM_MAGIC_REC;
    if (copied && SM_WRITE(DM_SAFE_NEW, 512u, sm_buf))
        return SM_SECTOR;
    uint32_t *m = (uint32_t *)sm_buf;
    for (u32 i = 0; i < 128u; i++)
        m[i] = 0;
    m[0] = DM_MAGIC;
    m[1] = ~DM_MAGIC;
    m[2] = bits | DM_SAFE;
    m[3] = m[2] ^ DM_XOR;
    if (SM_WRITE(DM_RECORD, 512u, sm_buf))
        return SM_SECTOR;
    sm_moved = copied ? 2u : 3u;
    return DM_SAFE_NEW;
}

static int drive_ok(void)
{
    return SM_READY && SM_SECTORS > SM_SECTOR && SM_SECTORS > DM_RECORD;
}

/* the record of this build, or a fresh one (another build, garbage, an erased sector) */
static int rec_read(struct sm_rec *r, u32 build)
{
    u32 at = sm_sector();
    if (!at || SM_READ(at, 512u, sm_buf))
        return -1;
    const struct sm_rec *d = (const struct sm_rec *)sm_buf;
    if (d->magic == SM_MAGIC_REC && d->version == SM_VERSION && d->build == build
        && d->crc == sm_crc32(d, sizeof *d - 4u) && d->safe_tries <= SM_TRIES_MAX && d->pending <= 1u)
        copy32(r, d, sizeof *r);
    else {
        u32 *w = (u32 *)r;
        for (u32 i = 0; i < sizeof *r / 4u; i++)
            w[i] = 0;
        r->magic = SM_MAGIC_REC;
        r->version = SM_VERSION;
        r->build = build;
    }
    return 0;
}

static int rec_write(struct sm_rec *r)
{
    r->crc = sm_crc32(r, sizeof *r - 4u);
    for (u32 i = 0; i < 512u; i++)
        sm_buf[i] = 0;
    copy32(sm_buf, r, sizeof *r);
    u32 at = sm_sector();                       /* (it reads into sm_buf: the record is built after) */
    for (u32 i = 0; i < 512u; i++)
        sm_buf[i] = 0;
    copy32(sm_buf, r, sizeof *r);
    return at ? SM_WRITE(at, 512u, sm_buf) : -1;
}

/* the SAFE mark, through the uncached alias (the data cache is copyback), then the soft reset: stock's own
 * (0x40005608: interrupts masked, the bootstrap's reboot marker word cleared, RCR SOFTRST), without its wait */
static void __attribute__((noreturn)) sm_reset_safe(u32 build, u32 why)
{
    struct sm_mark m;
    u32 *w = (u32 *)&m;
    for (u32 i = 0; i < sizeof m / 4u; i++)
        w[i] = 0;
    m.magic = SM_MAGIC_MARK;
    m.kind = SM_KIND_SAFE;
    m.build = build;
    m.why = why;
    m.crc = sm_crc32(&m, sizeof m - 4u);
    volatile u32 *dst = (volatile u32 *)SM_MARK_UC;
    const u32 *src = (const u32 *)&m;
    __asm__ volatile("move.w #0x2700,%%sr" ::: "memory");
    for (u32 i = 0; i < sizeof m / 4u; i++)
        dst[i] = src[i];
    *(volatile u32 *)0x48000000u = 0;
    *(volatile uint8_t *)0xEC090000u = 0x80;
    for (;;)
        ;
}

void sm_late(void)
{
    const struct sm_head *h = head();
    struct sm_rec r;
    if (!h) {
        sm_state = 8;
        return;
    }
    if (!drive_ok()) {
        sm_state = 5;
        return;
    }
    if (rec_read(&r, h->build)) {
        sm_state = 6;
        return;
    }
    if (h->live->kind == SM_KIND_NORMAL) {            /* NO in SAFE MODE: this boot counts afresh */
        r.pending = 1;
        r.safe_tries = 0;
        sm_state = rec_write(&r) ? 7 : 9;
        return;
    }
    if (r.pending && r.safe_tries < SM_TRIES_MAX) {
        r.safe_tries++;
        r.entered++;
        if (rec_write(&r)) {                    /* no record, no SAFE MODE: it could not count its tries */
            sm_state = 7;
            return;
        }
        sm_state = 3;
        sm_reset_safe(h->build, 1u);
    }
    sm_state = r.pending ? 4 : 1;               /* tries spent: a normal boot, still pending */
    r.pending = 1;
    if (rec_write(&r))
        sm_state = 7;
}

static void healthy(const struct sm_head *h)
{
    struct sm_rec r;
    if (!drive_ok() || rec_read(&r, h->build))
        return;
    r.pending = 0;
    r.safe_tries = 0;
    if (!rec_write(&r))
        sm_state = 2;
}

static void stop_entry(const struct sm_head *h)
{
    struct sm_rec r;
    if (!drive_ok() || rec_read(&r, h->build))
        return;
    r.pending = 0;                              /* a power cycle after it starts normally */
    r.safe_tries = 0;
    r.entered++;
    if (rec_write(&r))
        return;
    sm_state = 3;
    sm_reset_safe(h->build, 2u);
}

static int stop_alone(void)                     /* STOP down, and no other button */
{
    for (u32 c = 0; c < SM_KEY_CHANS; c++)
        if (SM_KEYS[c] != (c == SM_STOP_CHAN ? SM_STOP_MASK : 0u))
            return 0;
    return 1;
}

void sm_poll(void)
{
    if (sm_done)
        return;
    const struct sm_head *h = head();
    if (!h) {
        sm_done = 1;
        return;
    }
    u32 t = SM_TICK & 4095u;
    if (sm_polls++)
        sm_mono += (t - sm_last) & 4095u;
    sm_last = t;
    /* 2026-11-21 (main, the User's design: STOP HELD at start-up): STOP alone held without a break for SM_STOP_HOLD
     * ticks, all inside the first SM_STOP_TICKS; a tap (let go sooner, or another key with it) starts nothing and
     * goes to stock as any key does (a STOP pressed once just after power-on to stop a playing pattern) */
    if (sm_mono < SM_STOP_TICKS && stop_alone()
        && !(SM_FLAGS & SM_FLAG_MAINT) && h->live->kind != SM_KIND_NORMAL) {
        if (!sm_stop_on) {
            sm_stop_on = 1;
            sm_stop_at = sm_mono;
        } else if (sm_mono - sm_stop_at >= SM_STOP_HOLD)
            stop_entry(h);
    } else
        sm_stop_on = 0;
    if (sm_mono >= SM_HEALTHY) {
        sm_done = 1;
        healthy(h);
    }
}
