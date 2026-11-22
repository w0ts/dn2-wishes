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
#include "../include/dmove.h"

#ifndef DN7C_READ                                    /* the stock block driver (inserts/store.c's) */
#define DN7C_READ ((int (*)(uint32_t, uint32_t, void *))0x4012C87Au)         /* (sector, bytes, buf) -> 0 ok */
#define DN7C_WRITE ((int (*)(uint32_t, uint32_t, const void *))0x4012CA60u)
#define DN7C_READY (*(volatile uint32_t *)0x4461C68Cu)
#define DN7C_SECTORS (*(volatile uint32_t *)0x4461C6B0u)
#endif

/* v0.69.2: DM_DSP_NEW (0x5FF200) once dmove.c has moved it, DM_DSP_OLD (0x6E8000) before (csrc/include/dmove.h) */
static uint32_t c_hdr __attribute__((section(".data"))) = 0;                        /* (dn7c_load's place() sets it) */
#define C_HDR c_hdr
#define C_DATA (C_HDR + 1u)
#define C_ROOM 0xFFFFFu                              /* the uploader's buffer after its 0x03 (DN7_MAX) */
#define C_SPAN (1u + (C_ROOM + 511u) / 512u)
#define C_END (C_HDR + C_SPAN)
_Static_assert(C_SPAN == DM_DSP_N, "the copy's sectors: dmove.h's");
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
/* v0.69.2: the +Drive's DMA lands here, outside the C chunk (emulib/ramguard.py: no DMA into a chunk the build
 * places): the unused tail of pools.c's bank list staging (BL_W ends at +0x3A000 of BANK_RAM + 0x80000, BL_H is at
 * +0x40000), one 512-byte slot each: SAFE MODE's record +0x3F000, the DSP copy's header +0x3F200, the inserts +0x3F400 */
#ifdef BANK_RAM
#define hdr ((uint8_t *)(BANK_RAM + 0x80000u + 0x3F200u))
#else
static uint8_t hdr[512] __attribute__((section(".data"), aligned(16)));   /* (the host test) */
#endif

static int drive_ok(void)
{
    return DN7C_READY && DN7C_SECTORS > DM_RECORD && DN7C_SECTORS >= DM_DSP_OLD + DM_DSP_N;
}

/* v0.69.2 (csrc/include/dmove.h): the copy's place. Its bit in the move record: DM_DSP_NEW. Else the move, once, in
 * dn7c_load before the decode (BUF, the uploader's buffer, is free then): the old copy (when its header is one)
 * copied sector for sector through BUF, its header last, the bit set (the other bits kept), then DM_DSP_NEW. Any
 * read or write that fails: the old place, as before. The old sectors are only read. */
volatile uint32_t dn7c_moved __attribute__((section(".data"))) = 0;   /* 1 found moved, 2 moved now (a copy), 3 moved */
static uint32_t get32(const uint8_t *p);
#define C_HALF 1024u                                 /* sectors through BUF at once (C_ROOM holds 2,047) */
static void place(uint8_t *buf)
{
    c_hdr = 0;                                       /* (the move record unread: no copy this boot, neither place) */
    if (DN7C_READ(DM_RECORD, 512u, hdr)) {
        dn7c_state = 5;
        return;
    }
    c_hdr = DM_DSP_OLD;
    uint32_t bits = dm_bits_of((const uint32_t *)hdr);
    if (bits & DM_DSP) {
        c_hdr = DM_DSP_NEW;
        dn7c_moved = 1;
        return;
    }
    if (DN7C_READ(DM_DSP_OLD, 512u, hdr))
        return;
    uint32_t copied = get32(hdr) == C_MAGIC;
    for (uint32_t s = 0; copied && s < DM_DSP_N - 1u; s += C_HALF) {
        uint32_t n = DM_DSP_N - 1u - s < C_HALF ? DM_DSP_N - 1u - s : C_HALF;
        for (uint32_t o = 0; o < n; o += C_CHUNK / 512u) {
            uint32_t k = n - o < C_CHUNK / 512u ? n - o : C_CHUNK / 512u;
            if (DN7C_READ(DM_DSP_OLD + 1u + s + o, 512u * k, buf + 512u * o))
                return;
        }
        for (uint32_t o = 0; o < n; o += C_CHUNK / 512u) {
            uint32_t k = n - o < C_CHUNK / 512u ? n - o : C_CHUNK / 512u;
            if (DN7C_WRITE(DM_DSP_NEW + 1u + s + o, 512u * k, buf + 512u * o))
                return;
        }
    }
    if (copied && (DN7C_READ(DM_DSP_OLD, 512u, hdr) || DN7C_WRITE(DM_DSP_NEW, 512u, hdr)))
        return;
    uint32_t *m = (uint32_t *)hdr;
    for (uint32_t i = 0; i < 128u; i++)
        m[i] = 0;
    m[0] = DM_MAGIC;
    m[1] = ~DM_MAGIC;
    m[2] = bits | DM_DSP;
    m[3] = m[2] ^ DM_XOR;
    if (DN7C_WRITE(DM_RECORD, 512u, hdr))
        return;
    dn7c_moved = copied ? 2u : 3u;
    c_hdr = DM_DSP_NEW;
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
    place(dst);                                      /* v0.69.2: where the copy is (the move, once) */
    if (!c_hdr)
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
    if (!drive_ok() || whole(len) > C_ROOM || !c_hdr)
        return;                                      /* (c_hdr 0: dn7c_load could not tell the place) */
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
