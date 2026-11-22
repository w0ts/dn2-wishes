/* SAFE MODE's kernel (docs/safe-mode.md): a small CODE chunk, FIRST of the area's CODE chunks, so the platform
 * loader (csrc/runtime/loader.S) calls its init before any other chunk's, before `main`, before the BSS clear and
 * before the caches are on.
 *
 * At every boot the init reads the RAM mark (sm.h SM_MARK) and wipes it, so a mark lasts one boot. The head
 * (sm_head, the chunk's first bytes) keeps what it said for normal.c. With a SAFE mark it turns this boot into
 * SAFE MODE:
 *
 *   1. the unpatch table (appended to this chunk by dnfw.mods.safemode, checked by its CRC-32 first) puts stock
 *      1.12's bytes back over every byte the build changed in MAIN OS, except the two runs the loader is running
 *      in (the start-up call 0x4000053e and the loader's cave 0x4028dfae; the build leaves them out);
 *   2. the overrides, each over the stock bytes it expects (else SAFE MODE is not entered):
 *        O1 0x400cf73a  jsr 0x40136820 (stock's aPLib depack in the DSP uploader) -> jsr sm_refuse7: the uploader
 *                       takes its stock error path, the DSP gets no program (no audio), stock's aPLib never
 *                       reads our LZMA section 7;
 *        O2 0x4002e464  jsr 0x4011d5d4 (the UI loop's isDirty) -> jsr sm_isdirty: stock's isDirty, and once the stock UI
 *                       is up, the question (question.c: YES stays, NO a NORMAL-ONCE mark and our soft reset);
 *        O4 0x400bb4a0  move.l %d0,0x405ce858 -> nops: the empty project is not written over the working state;
 *      and boot flag bit 0 (0x40287a60, the Early Start-up Menu's EMPTY RESET): stock skips the working project's
 *      +Drive read and starts with an empty project;
 *   3. every later CODE chunk's init entry is zeroed in the area, so none of our other inits runs.
 *
 * Nothing here writes the +Drive. A table whose CRC fails, or an override site that is not stock after the table,
 * leaves this boot normal. */

#include "sm.h"

typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;

#define BASE        0x40000400u              /* MAIN OS's image base */
#define STOCK_LEN   0x0030C580u              /* stock 1.12's MAIN OS length: the table never reaches past it */
#define AREA        0x4030C980u              /* the appended DNFW area (still in place: the BSS is not cleared yet) */
#define FLAGS       (*(volatile u32 *)0x40287A60u)
#define CALLS_VA    0x4000053Eu              /* never restored: the loader returns into it */
#define CALLS_LEN   8u
#define CAVE_VA     0x4028DFAEu              /* never restored: the loader runs here */
#define CAVE_LEN    138u

struct sm_live sm_live __attribute__((section(".data"))) = {SM_KIND_NONE, 0, 0};
/* volatile: the build fills build and the table's fields after the link, so the compiler must read them */
const volatile struct sm_head sm_head __attribute__((section(".text.entry"), used)) = {
    SM_MAGIC_HEAD, 0, 0, 0, 0, &sm_live, {0, 0}
};

u32 sm_why __attribute__((section(".data"))) = 0;   /* 0 none; 1 SAFE applied; 2 a bad mark; 3 table CRC; 4 a site
                                                      * not stock; 5 the table malformed */

unsigned int sm_refuse7(void)                     /* O1: the depack's answer that means "no program" */
{
    return 0x100000u;
}

#define ISDIRTY ((int (*)(void *))0x4011D5D4u)
int sm_isdirty(void *screen)                      /* O2: stock's isDirty; the question opens from here */
{
    extern int sm_ask(void *screen);
    int r = ISDIRTY(screen);
    return sm_ask(screen) ? 1 : r;
}

static int overlaps(u32 a, u32 n, u32 b, u32 m)
{
    return a < b + m && b < a + n;
}

/* walk the table: CHECK only (apply 0) or write. -> 0 ok */
static int table(const u8 *t, u32 len, int apply)
{
    u32 pos = 0, i = 0;
    while (i + 3u <= len) {
        u32 gap = (u32)t[i] << 8 | t[i + 1];
        i += 2;
        if (gap == 0xFFFFu) {
            if (i + 4u > len)
                return -1;
            gap = (u32)t[i] << 24 | (u32)t[i + 1] << 16 | (u32)t[i + 2] << 8 | t[i + 3];
            i += 4;
            if (gap == 0xFFFFFFFFu)
                return i == len ? 0 : -1;     /* the end marker, at the end */
        }
        if (i >= len)
            return -1;
        u32 n = t[i++];
        pos += gap;
        if (n == 0 || i + n > len || pos + n > STOCK_LEN
            || overlaps(BASE + pos, n, CALLS_VA, CALLS_LEN) || overlaps(BASE + pos, n, CAVE_VA, CAVE_LEN))
            return -1;
        if (apply) {
            u8 *dst = (u8 *)(BASE + pos);
            for (u32 k = 0; k < n; k++)
                dst[k] = t[i + k];
        }
        i += n;
        pos += n;
    }
    return -1;
}

struct site { u32 va; u8 stock[6]; };
static const struct site sites[3] = {
    {0x400CF73Au, {0x4E, 0xB9, 0x40, 0x13, 0x68, 0x20}},    /* O1 */
    {0x4002E464u, {0x4E, 0xB9, 0x40, 0x11, 0xD5, 0xD4}},    /* O2 */
    {0x400BB4A0u, {0x23, 0xC0, 0x40, 0x5C, 0xE8, 0x58}},    /* O4 */
};

/* the byte at VA once the table is applied: the table's, where a run covers it, else what is there now */
static u8 after_table(const u8 *t, u32 len, u32 va)
{
    u32 pos = 0, i = 0;
    while (i + 3u <= len) {
        u32 gap = (u32)t[i] << 8 | t[i + 1];
        i += 2;
        if (gap == 0xFFFFu) {
            gap = (u32)t[i] << 24 | (u32)t[i + 1] << 16 | (u32)t[i + 2] << 8 | t[i + 3];
            i += 4;
            if (gap == 0xFFFFFFFFu)
                break;
        }
        u32 n = t[i++];
        pos += gap;
        if (va >= BASE + pos && va < BASE + pos + n)
            return t[i + (va - BASE - pos)];
        i += n;
        pos += n;
    }
    return *(const u8 *)va;
}

static int stock_after(const u8 *t, u32 len, const struct site *s)
{
    for (int k = 0; k < 6; k++)
        if (after_table(t, len, s->va + k) != s->stock[k])
            return 0;
    return 1;
}

static void put_jsr(u32 va, u32 to)
{
    u8 *p = (u8 *)va;
    p[0] = 0x4E; p[1] = 0xB9;
    p[2] = to >> 24; p[3] = to >> 16; p[4] = to >> 8; p[5] = to;
}

/* every CODE chunk after this one in the area: its init entry zeroed (the loader reads it after this returns) */
static void later_inits_off(void)
{
    const u8 *a = (const u8 *)AREA;
    if (*(const u32 *)a != 0x444E4657u)       /* 'DNFW' */
        return;
    u32 count = *(const u32 *)(a + 8);
    int after = 0;
    for (u32 e = 0; e < count; e++) {
        const u8 *d = a + 12u + 12u * e;
        if (*(const u32 *)d != 0x434F4445u)   /* 'CODE' */
            continue;
        u32 *chunk = (u32 *)(a + *(const u32 *)(d + 4));
        if (after)
            chunk[3] = 0;                       /* +12: the init entry */
        else if (chunk[0] == SM_LOAD)
            after = 1;
    }
}

static void safe(void)
{
    const u8 *t = (const u8 *)SM_LOAD + sm_head.table_off;
    if (!sm_head.table_len || sm_crc32(t, sm_head.table_len) != sm_head.table_crc) {
        sm_why = 3;
        return;
    }
    if (table(t, sm_head.table_len, 0)) {
        sm_why = 5;
        return;
    }
    for (int k = 0; k < 3; k++)
        if (!stock_after(t, sm_head.table_len, &sites[k])) {   /* checked before a byte is written */
            sm_why = 4;
            return;
        }
    table(t, sm_head.table_len, 1);
    extern int sm_isdirty(void *);
    put_jsr(sites[0].va, (u32)sm_refuse7);
    put_jsr(sites[1].va, (u32)sm_isdirty);
    {
        u8 *p = (u8 *)sites[2].va;
        for (int k = 0; k < 6; k += 2) {
            p[k] = 0x4E; p[k + 1] = 0x71;       /* nop */
        }
    }
    FLAGS |= 1u;                                /* EMPTY RESET: no working project from the +Drive */
    later_inits_off();
    sm_live.applied = 1;
    sm_why = 1;
}

void sm_init(void)
{
    volatile struct sm_mark *m = (volatile struct sm_mark *)SM_MARK;
    struct sm_mark c;
    for (u32 k = 0; k < sizeof c / 4u; k++)
        ((u32 *)&c)[k] = ((volatile u32 *)m)[k];
    for (u32 k = 0; k < sizeof c / 4u; k++)     /* one boot only */
        ((volatile u32 *)m)[k] = 0;
    sm_live.kind = SM_KIND_NONE;
    sm_live.applied = 0;
    sm_live.reason = 0;
    if (c.magic != SM_MAGIC_MARK)
        return;
    if (c.crc != sm_crc32(&c, sizeof c - 4u) || c.build != sm_head.build
        || (c.kind != SM_KIND_SAFE && c.kind != SM_KIND_NORMAL)) {
        sm_why = 2;
        return;
    }
    sm_live.kind = c.kind;
    sm_live.reason = c.why;
    if (c.kind == SM_KIND_SAFE)
        safe();
}
