/* 2026-11-22 (v0.69.2, the User: "our +Drive data lives where upstream names nothing"; docs/memory-map.md):
 * the +Drive places of what moved, and the move record that says what has moved (csrc/sampler/dmove.c).
 *
 *   what                      until v0.69.1             from v0.69.2
 *   SAFE MODE's boot record   0x6E0300                  0x5FFB00
 *   the DSP program's copy    0x6E8000 .. 0x6E8800      0x5FF200 .. 0x5FFA00
 *   our tunings               0x6E0600 .. 0x6E06FF      0x6E0400 .. 0x6E04FF  (upstream's own tunings place)
 *   bank lists, projects 0..63    0x5E0000 .. 0x5EE7FF  0x6E0600 .. 0x6EEDFF  (upstream's own place)
 *   the wishes record         0x6F0800 .. 0x6FEFFF      0x5D8000 .. 0x5EE7FF  (92,160 cells, was 59,392)
 *   bank lists, 64..127       0x5F0000 .. 0x5FE7FF      0x6F0800 .. 0x6FEFFF  (upstream's own place)
 *   the move record           -                         0x5FFC00 ('DN2V', ~'DN2V', the bits, a check)
 *
 * Each move copies the old place's whole records once (the old sectors only read), in that order (each frees the
 * place the next one takes), then sets its bit in the move record. ERASE MOD DATA never erases the move record. The
 * two that are read before the UI exists (SAFE MODE's record at the eMMC-ready point, the DSP program's copy at the
 * upload) read the move record themselves: its bit set, the new place; else the old one. */
#ifndef DMOVE_H
#define DMOVE_H

#include <stdint.h>

#define DM_RECORD   0x5FFC00u
#define DM_MAGIC    0x444E3256u              /* 'DN2V' */
#define DM_XOR      0x4D4F5645u              /* 'MOVE' */

#define DM_SAFE  0x01u
#define DM_DSP   0x02u
#define DM_TUNE  0x04u
#define DM_BLA   0x08u
#define DM_WISH  0x10u
#define DM_BLB   0x20u
#define DM_ALL   0x3Fu

#define DM_SAFE_OLD 0x6E0300u
#define DM_SAFE_NEW 0x5FFB00u
#define DM_DSP_OLD  0x6E8000u
#define DM_DSP_NEW  0x5FF200u
#define DM_DSP_N    (1u + 2048u)
#define DM_TUNE_OLD 0x6E0600u
#define DM_TUNE_NEW 0x6E0400u
#define DM_TUNE_N   256u
#define DM_BL_SPAN  464u
#define DM_BL_N     (2u * 64u * DM_BL_SPAN)
#define DM_BLA_OLD  0x5E0000u
#define DM_BLA_NEW  0x6E0600u
#define DM_BLB_OLD  0x5F0000u
#define DM_BLB_NEW  0x6F0800u
#define DM_WISH_OLD 0x6F0800u
#define DM_WISH_OLD_N 59392u
#define DM_WISH_NEW 0x5D8000u
#define DM_WISH_NEW_N 92160u

_Static_assert(DM_WISH_NEW + DM_WISH_NEW_N == DM_BLA_OLD + DM_BL_N, "the wishes' new cells end where the old bank lists A did");
_Static_assert(DM_DSP_NEW >= 0x5FF103u && DM_DSP_NEW + DM_DSP_N <= DM_SAFE_NEW && DM_SAFE_NEW < DM_RECORD
               && DM_RECORD < 0x600000u, "past the inserts' mark (0x5FF102), below the pool image");
_Static_assert(DM_TUNE_NEW + DM_TUNE_N <= 0x6E0500u && DM_BLA_NEW + DM_BL_N <= 0x6F0000u
               && DM_BLB_NEW + DM_BL_N <= 0x6FF000u, "upstream's own places (its PERFORM from 0x6E0500)");

/* the move record in BUF (512 B, already read) -> its bits, or 0 when it is not a whole one */
static inline uint32_t dm_bits_of(const uint32_t *buf)
{
    if (buf[0] != DM_MAGIC || buf[1] != ~DM_MAGIC || buf[3] != (buf[2] ^ DM_XOR) || (buf[2] & ~DM_ALL))
        return 0;
    return buf[2];
}

#endif
