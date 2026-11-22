/* SAFE MODE (docs/safe-mode.md): what the kernel chunk (kernel.c) and the normal-boot half (normal.c, in the
 * page renderer's chunk) share. Stock Digitone II OS 1.12 addresses.
 *
 *   RAM mark     SM_MARK, 32 B (in a reserved 256 B), above BSS: read and wiped by the kernel's init at every boot,
 *                written through the uncached alias just before our own soft reset. It lasts one boot.
 *   +Drive       SM_SECTOR, one 512 B record: pending, safe_tries, the build id, a CRC-32.
 *   kernel head  at SM_LOAD (the kernel chunk's first bytes): magic, the build id, the table's place and CRC,
 *                and what this boot's mark said (written by the kernel's init, read by normal.c). */
#ifndef SM_H
#define SM_H

#include <stdint.h>

#define SM_RAM        0x476F8000u           /* dnfw.waverider.pages.SM_RAM: the mark, then the kernel chunk */
#define SM_MARK       SM_RAM
#define SM_MARK_UC    (SM_MARK + 0x08000000u)   /* the same RAM, uncached (MCF5441x ACRs; quickboot's alias) */
#define SM_LOAD       (SM_RAM + 0x100u)      /* the kernel chunk */
#define SM_SECTOR     0x6E0300u              /* the record until v0.69.2; then csrc/include/dmove.h DM_SAFE_NEW (normal.c) */

#define SM_MAGIC_MARK 0x534D4D4Bu            /* 'SMMK' */
#define SM_MAGIC_REC  0x444E3242u            /* 'DN2B' */
#define SM_MAGIC_HEAD 0x534D4B31u            /* 'SMK1' */
#define SM_VERSION    1u

#define SM_KIND_NONE   0u
#define SM_KIND_SAFE   1u                    /* start in SAFE MODE */
#define SM_KIND_NORMAL 2u                    /* NORMAL-ONCE: one normal boot, old failures not counted */

#define SM_TRIES_MAX  2u                     /* SAFE resets in a row without a healthy boot; then a normal boot */
#define SM_HEALTHY    3630u                  /* panel ticks of UI (121 a second on the unit): 30 s */

/* the mark: 32 B */
struct sm_mark {
    uint32_t magic, kind, build, why, spare[3], crc;      /* crc: CRC-32 of the 28 bytes before it */
};

/* the record: the first 32 B of the sector, the rest zero */
struct sm_rec {
    uint32_t magic, version, build, pending, safe_tries, entered, spare, crc;
};

/* what this boot's mark said, in the kernel's .data (the head itself is constant: the RAM guard checks it) */
struct sm_live {
    volatile uint32_t kind;                 /* SM_KIND_*, written by the kernel's init */
    volatile uint32_t applied;              /* 1 when this boot runs as SAFE MODE */
    volatile uint32_t reason;               /* the mark's why: 1 a boot that never became healthy, 2 STOP held */
};

extern struct sm_live sm_live;              /* (kernel.c; question.c reads it) */

/* the kernel chunk's head, at SM_LOAD (kernel.c's sm_head; the build fills build, table_off, table_len, table_crc) */
struct sm_head {
    uint32_t magic, build, table_off, table_len, table_crc;
    struct sm_live *live;
    uint32_t spare[2];
};

static inline uint32_t sm_crc32(const void *p, uint32_t n)
{
    const uint8_t *b = (const uint8_t *)p;
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *b++;
        for (int k = 0; k < 8; k++)
            c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

#endif
