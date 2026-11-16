/* 2026-11-11 (lzma-dsp): section 7, the DSP program, stored as LZMA (docs/lzma7.md).
 *
 * MAIN OS's SHARC uploader (0x400cf4b0) reads section 7 from flash into a 1 MiB buffer,
 * writes 0x03 at the start of a second 1 MiB buffer and depacks after it with stock's aPLib
 * routine, `0x40136820(src, dst) -> length` (src is the stored section: [u32 stream length]
 * [u32 byte sum], then the stream). Its call at 0x400cf73a calls dn_depack7 instead, with the
 * same arguments and the same answer:
 *
 *   - a stream that does not start with DN7_MAGIC is stock's: handed to 0x40136820 as is;
 *   - ours is the 16-byte header below, then a raw LZMA1 stream. It decodes into dst, at
 *     most DN7_MAX bytes (the second buffer's room after the 0x03), and is answered only if
 *     the decoded length and the CRC-32 of the output match the header. Anything else (a bad
 *     header, props out of range, a short or corrupt stream, a CRC mismatch) answers
 *     DN7_REFUSE, which the uploader's own bound (length + 1 > 1 MiB) turns into its stock
 *     error path: both buffers freed, the DSP left in reset, MAIN OS, the UI and USB going on.
 *
 *   header (big-endian): 'DN7Z', unpacked length, LZMA props byte ((pb * 5 + lp) * 9 + lc),
 *   three zero bytes, CRC-32 (IEEE, the zlib one) of the unpacked bytes.
 *
 * The decoder needs no RAM but the output (the dictionary is dst itself) and its probability
 * table (lc + lp <= 3: 16 KB), taken from stock's heap for the call and given back (no heap:
 * refused, 7). No flash is written. dnfw.container.section packs the same
 * format (dnfw.container.section.compress_lzma7) and unpacks it for every tool. */

#include <stdint.h>

#define DN7_MAGIC 0x444E375Au              /* 'DN7Z' */
#define DN7_MAX 0xFFFFFu                   /* the uploader's buffer, after its 0x03 */
#define DN7_REFUSE 0x100000                /* length + 1 > 1 MiB: stock's error path */
#define LC_LP_MAX 3
#define NPROBS (1846 + (0x300 << LC_LP_MAX))

typedef long (*depack_fn)(const uint8_t *src, uint8_t *dst);
/* stock's malloc answers in d0; GCC's m68k ABI reads a pointer result from a0, so the call is
 * typed as returning an integer and the pointer made from it */
typedef uint32_t (*malloc_fn)(uint32_t size);
typedef void (*free_fn)(void *p);
#ifndef DN7_STOCK_DEPACK
#define DN7_STOCK_DEPACK ((depack_fn)0x40136820u)   /* stock's aPLib depack(src, dst) */
#endif
#ifndef DN7_MALLOC                                   /* stock's malloc / free: the uploader's own */
#define DN7_MALLOC ((malloc_fn)0x401202c8u)         /* buffers come from them (0x400cf6b6, 0x400cf7b8) */
#define DN7_FREE ((free_fn)0x401204ceu)
#endif

/* what the last call did (for the emulator check and a PEEK on the unit):
 * 0 never called, 1 handed to stock, 2 decoded and checked, 3.. refused (the reason).
 * In .data: the page renderer's chunk has no BSS (nothing zeroes it). */
volatile uint32_t dn7_status __attribute__((section(".data"))) = 0;
volatile uint32_t dn7_length __attribute__((section(".data"))) = 0;
/* the probability table, NPROBS words (16 KB), from the heap for the one call */
static uint16_t *probs __attribute__((section(".data"))) = 0;

#define TOP (1u << 24)
#define NBITS 11
#define ONE (1u << NBITS)
#define MOVE 5

typedef struct {
    const uint8_t *in, *end;
    uint32_t range, code;
} rc_t;

static uint32_t next_byte(rc_t *r)
{
    return r->in < r->end ? *r->in++ : 0;
}

static uint32_t bit(rc_t *r, uint16_t *p)
{
    uint32_t bound = (r->range >> NBITS) * *p, b;
    if (r->code < bound) {
        r->range = bound;
        *p += (ONE - *p) >> MOVE;
        b = 0;
    } else {
        r->range -= bound;
        r->code -= bound;
        *p -= *p >> MOVE;
        b = 1;
    }
    if (r->range < TOP) {
        r->range <<= 8;
        r->code = (r->code << 8) | next_byte(r);
    }
    return b;
}

static uint32_t direct(rc_t *r, int n)
{
    uint32_t v = 0;
    while (n--) {
        r->range >>= 1;
        uint32_t t = (r->code - r->range) >> 31;
        r->code -= r->range & (t - 1);
        v = (v << 1) | (1 - t);
        if (r->range < TOP) {
            r->range <<= 8;
            r->code = (r->code << 8) | next_byte(r);
        }
    }
    return v;
}

static uint32_t tree(rc_t *r, uint16_t *p, int n)
{
    uint32_t m = 1;
    for (int i = 0; i < n; i++)
        m = (m << 1) | bit(r, p + m);
    return m - (1u << n);
}

static uint32_t rtree(rc_t *r, uint16_t *p, int n)
{
    uint32_t m = 1, s = 0;
    for (int i = 0; i < n; i++) {
        uint32_t b = bit(r, p + m);
        m = (m << 1) | b;
        s |= b << i;
    }
    return s;
}

enum {
    IS_MATCH = 0, IS_REP = 192, IS_REP0 = 204, IS_REP1 = 216, IS_REP2 = 228, IS_REP0L = 240,
    SLOT = 432, SPEC = 688, ALIGN = 802, LEN = 818, REPLEN = 1332, LIT = 1846
};

static uint32_t length(rc_t *r, uint16_t *p, uint32_t pos)
{
    if (!bit(r, p))
        return tree(r, p + 2 + pos * 8, 3);
    if (!bit(r, p + 1))
        return 8 + tree(r, p + 130 + pos * 8, 3);
    return 16 + tree(r, p + 258, 8);
}

/* -> bytes written (stops at OUTLEN), or -1 on a match before the start of the output */
static long lzma_decode(const uint8_t *in, uint32_t inlen, uint8_t *out, uint32_t outlen,
                        uint32_t lc, uint32_t lp, uint32_t pb)
{
    uint32_t n = 1846 + (0x300u << (lc + lp)), o = 0;
    for (uint32_t i = 0; i < n; i++)
        probs[i] = ONE / 2;
    if (inlen < 5)
        return -1;
    rc_t r = {in + 5, in + inlen, 0xFFFFFFFFu, 0};
    for (int i = 1; i < 5; i++)
        r.code = (r.code << 8) | in[i];
    uint32_t rep0 = 0, rep1 = 0, rep2 = 0, rep3 = 0, state = 0;
    uint32_t pbm = (1u << pb) - 1, lpm = (1u << lp) - 1;
    while (o < outlen) {
        uint32_t ps = o & pbm;
        if (!bit(&r, probs + IS_MATCH + (state << 4) + ps)) {
            uint32_t prev = o ? out[o - 1] : 0;
            uint16_t *lit = probs + LIT + 0x300 * (((o & lpm) << lc) + (prev >> (8 - lc)));
            uint32_t s = 1;
            if (state >= 7) {
                uint32_t mb = out[o - rep0 - 1];
                do {
                    uint32_t m = (mb >> 7) & 1, b;
                    mb <<= 1;
                    b = bit(&r, lit + ((1 + m) << 8) + s);
                    s = (s << 1) | b;
                    if (m != b)
                        break;
                } while (s < 0x100);
            }
            while (s < 0x100)
                s = (s << 1) | bit(&r, lit + s);
            out[o++] = (uint8_t)s;
            state = state < 4 ? 0 : state < 10 ? state - 3 : state - 6;
            continue;
        }
        uint32_t len;
        if (bit(&r, probs + IS_REP + state)) {
            if (!o)
                return -1;
            if (!bit(&r, probs + IS_REP0 + state)) {
                if (!bit(&r, probs + IS_REP0L + (state << 4) + ps)) {
                    state = state < 7 ? 9 : 11;
                    out[o] = out[o - rep0 - 1];
                    o++;
                    continue;
                }
            } else {
                uint32_t d;
                if (!bit(&r, probs + IS_REP1 + state)) {
                    d = rep1;
                } else {
                    if (!bit(&r, probs + IS_REP2 + state)) {
                        d = rep2;
                    } else {
                        d = rep3;
                        rep3 = rep2;
                    }
                    rep2 = rep1;
                }
                rep1 = rep0;
                rep0 = d;
            }
            len = length(&r, probs + REPLEN, ps);
            state = state < 7 ? 8 : 11;
        } else {
            rep3 = rep2;
            rep2 = rep1;
            rep1 = rep0;
            len = length(&r, probs + LEN, ps);
            state = state < 7 ? 7 : 10;
            uint32_t ls = len < 4 ? len : 3;
            uint32_t slot = tree(&r, probs + SLOT + (ls << 6), 6);
            if (slot < 4) {
                rep0 = slot;
            } else {
                int nd = (int)(slot >> 1) - 1;
                rep0 = (2 | (slot & 1)) << nd;
                if (slot < 14) {
                    rep0 += rtree(&r, probs + SPEC + rep0 - slot - 1, nd);
                } else {
                    rep0 += direct(&r, nd - 4) << 4;
                    rep0 += rtree(&r, probs + ALIGN, 4);
                }
                if (rep0 == 0xFFFFFFFFu)
                    break;                          /* the end marker */
            }
            if (rep0 >= o)
                return -1;
        }
        len += 2;
        while (len-- && o < outlen) {
            out[o] = out[o - rep0 - 1];
            o++;
        }
    }
    return (long)o;
}

static const uint32_t crc_nibble[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
    0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu, 0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

static uint32_t crc32(const uint8_t *p, uint32_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *p++;
        c = (c >> 4) ^ crc_nibble[c & 15];
        c = (c >> 4) ^ crc_nibble[c & 15];
    }
    return ~c;
}

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static long refuse(uint32_t why)
{
    dn7_status = why;
    return DN7_REFUSE;
}

long dn_depack7(const uint8_t *src, uint8_t *dst)
{
    const uint8_t *h = src + 8;                     /* after the section's [length][sum] */
    uint32_t stream = be32(src);
    if (stream < 16 || be32(h) != DN7_MAGIC) {
        dn7_status = 1;
        return DN7_STOCK_DEPACK(src, dst);
    }
    uint32_t outlen = be32(h + 4), props = h[8], want = be32(h + 12);
    uint32_t lc = props % 9, lp = (props / 9) % 5, pb = props / 45;
    if (outlen == 0 || outlen > DN7_MAX)
        return refuse(3);
    if (props >= 225 || lc + lp > LC_LP_MAX || h[9] || h[10] || h[11])
        return refuse(4);
    probs = (uint16_t *)(uintptr_t)DN7_MALLOC(NPROBS * sizeof(uint16_t));
    if (!probs)
        return refuse(7);
    long got = lzma_decode(h + 16, stream - 16, dst, outlen, lc, lp, pb);
    DN7_FREE(probs);
    probs = 0;
    if (got != (long)outlen)
        return refuse(5);
    if (crc32(dst, outlen) != want)
        return refuse(6);
    dn7_status = 2;
    dn7_length = outlen;
    return (long)outlen;
}
