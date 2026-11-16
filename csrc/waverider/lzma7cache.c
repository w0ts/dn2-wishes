/* 2026-11-11 (lzma-cache): the DSP program decoded once, kept on the +Drive (docs/lzma7.md, "The cache").
 * The User: "lzma is slower", "we have an item to do it once".
 *
 * Stock 1.12 uploads the DSP program (0x400cf4b0) from its boot routine at 0x400cf086, BEFORE the
 * eMMC driver's set-up (0x4012be52, 0x4012c438, 0x4012c620, a few instructions later): the +Drive
 * cannot be read there. So the call moves (coldfire.py): 0x400cf086's jsr becomes three nops, and
 * dn7_late (lzma7late.S) runs it at 0x400cf0f2, where every path of the routine meets after the
 * driver's set-up, before anything else of the boot. dn_depack7 (lzma7.c) then:
 *
 *   - dn7c_load: a valid copy of THIS section 7 on the +Drive -> read into the uploader's buffer,
 *     checked by the shipped CRC-32 (the one the decode itself is checked by), answered;
 *   - otherwise: the decode as before, then dn7c_store writes the copy for the next boot.
 *
 *   C_HDR                 the header: 'DN7C', version, length, CRC-32 of the program (the shipped
 *                         header's), the id (the stored section 7's first 24 bytes: its length, its
 *                         byte sum, the DN7Z header), a CRC-32 of those 40 bytes. Written LAST.
 *   C_DATA .. C_END - 1   the program, whole sectors (the tail past its length: whatever was in the
 *                         buffer, never read as the program)
 *
 * A new firmware changes the id (another stream, another sum or CRC), so the copy is not used and is
 * written again. A copy cut by a power loss, erased (ERASE MOD DATA trims the range; a factory reset
 * and FORMAT +DRIVE never reach it), or damaged fails its header or its CRC, and the boot decodes as
 * before. The +Drive not up, a read or a write that fails: the decode, as before; a write failure only
 * means the next boot decodes again. Only the sectors below and a 512-byte buffer are written. */

#include <stdint.h>

#ifndef DN7C_READ                                    /* the stock block driver (inserts/store.c's) */
#define DN7C_READ ((int (*)(uint32_t, uint32_t, void *))0x4012C87Au)         /* (sector, bytes, buf) -> 0 ok */
#define DN7C_WRITE ((int (*)(uint32_t, uint32_t, const void *))0x4012CA60u)
#define DN7C_READY (*(volatile uint32_t *)0x4461C68Cu)
#define DN7C_SECTORS (*(volatile uint32_t *)0x4461C6B0u)
#endif

#define C_HDR 0x6E8000u
#define C_DATA (C_HDR + 1u)
#define C_ROOM 0xFFFFFu                              /* the uploader's buffer after its 0x03 (DN7_MAX) */
#define C_END (C_DATA + (C_ROOM + 511u) / 512u)      /* 0x6E8801 */
_Static_assert(C_HDR >= 0x6E0502u && C_END <= 0x6F0000u,
               "between the inserts' records (to 0x6E0501) and the library's extension (0x6F0000)");
#define C_MAGIC 0x444E3743u                          /* 'DN7C' */
#define C_VERSION 1u
#define C_ID 24u
#define C_CHECKED 40u                                /* the header's bytes its own CRC covers */
#define C_CHUNK 0x10000u                             /* the driver's largest call (64 KB) */

extern uint32_t dn7_crc32(const uint8_t *p, uint32_t n);

/* what this boot's copy did (for the emulator check and a PEEK on the unit):
 * 0 not tried (the +Drive not up, or a stock section 7), 1 loaded, 2 none valid (dn7c_why: 1 header
 * magic or version, 2 id, 3 length or CRC field, 4 header check, 5 the program's CRC), 3 written,
 * 4 a write failed, 5 a read failed */
volatile uint32_t dn7c_state __attribute__((section(".data"))) = 0;
volatile uint32_t dn7c_why __attribute__((section(".data"))) = 0;
static uint8_t hdr[512] __attribute__((section(".data"), aligned(16)));

static int drive_ok(void)
{
    return DN7C_READY && DN7C_SECTORS >= C_END;
}

static uint32_t whole(uint32_t len)
{
    return (len + 511u) & ~511u;
}

static uint32_t get32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24);
    p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);
    p[3] = (uint8_t)v;
}

/* BYTES (whole sectors) from or to C_DATA, in the driver's 64 KB calls -> 0 ok */
static int span(int write, uint8_t *buf, uint32_t bytes)
{
    for (uint32_t off = 0; off < bytes; off += C_CHUNK) {
        uint32_t n = bytes - off < C_CHUNK ? bytes - off : C_CHUNK;
        int r = write ? DN7C_WRITE(C_DATA + off / 512u, n, buf + off) : DN7C_READ(C_DATA + off / 512u, n, buf + off);
        if (r)
            return -1;
    }
    return 0;
}

static uint32_t header_fault(const uint8_t *id, uint32_t len, uint32_t crc)
{
    if (get32(hdr) != C_MAGIC || get32(hdr + 4) != C_VERSION)
        return 1;
    for (uint32_t i = 0; i < C_ID; i++)
        if (hdr[16 + i] != id[i])
            return 2;
    if (get32(hdr + 8) != len || get32(hdr + 12) != crc)
        return 3;
    if (get32(hdr + C_CHECKED) != dn7_crc32(hdr, C_CHECKED))
        return 4;
    return 0;
}

/* -> 1 when DST holds the program (LEN bytes, CRC-32 CRC) read from the copy of section 7 ID */
int dn7c_load(const uint8_t *id, uint8_t *dst, uint32_t len, uint32_t crc)
{
    if (!drive_ok() || whole(len) > C_ROOM)
        return 0;
    if (DN7C_READ(C_HDR, 512u, hdr)) {
        dn7c_state = 5;
        return 0;
    }
    uint32_t why = header_fault(id, len, crc);
    if (!why) {
        if (span(0, dst, whole(len))) {
            dn7c_state = 5;
            return 0;
        }
        if (dn7_crc32(dst, len) == crc) {
            dn7c_state = 1;
            return 1;
        }
        why = 5;
    }
    dn7c_state = 2;
    dn7c_why = why;
    return 0;
}

/* the program just decoded and checked into DST: the copy for the next boot, its header last */
void dn7c_store(const uint8_t *id, uint8_t *dst, uint32_t len, uint32_t crc)
{
    if (!drive_ok() || whole(len) > C_ROOM)
        return;
    for (uint32_t i = 0; i < 512u; i++)
        hdr[i] = 0;
    if (DN7C_WRITE(C_HDR, 512u, hdr) || span(1, dst, whole(len))) {
        dn7c_state = 4;
        return;
    }
    put32(hdr, C_MAGIC);
    put32(hdr + 4, C_VERSION);
    put32(hdr + 8, len);
    put32(hdr + 12, crc);
    for (uint32_t i = 0; i < C_ID; i++)
        hdr[16 + i] = id[i];
    put32(hdr + C_CHECKED, dn7_crc32(hdr, C_CHECKED));
    dn7c_state = DN7C_WRITE(C_HDR, 512u, hdr) ? 4 : 3;
}
