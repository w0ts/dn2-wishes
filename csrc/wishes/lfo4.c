/* LFO4's stored values in the wishes record (DN2_LFO4 only; docs/lfo-112-port.md 4.1, the User 2026-11-14: "Into
 * the wishes record").
 *
 * lfo4 keeps LFO4's eight values (SPD MULT FADE DEST WAVE SPH MODE DEP) in its own table keyed by the live sound's
 * address (csrc/lfo4/ext.c), carried in RAM by its own memcpy / memset hooks. On 1.11 it stored them in the stored
 * sound's lane (ids 4..32); on our series that lane is the wishes link, so lfo4's two stored-sound hooks are left
 * out of the build (dnfw.mods.lfo4) and the values travel in a field of the sound's wishes record instead:
 *
 *   - **save** (wish_save, before it hashes): LFO4's values as lfo4's table holds them for the live sound become the
 *     record's WT_LFO4 field; a sound whose LFO4 is at its defaults has no field (and no record for it alone);
 *   - **load** (wish_load): a sound with no link has LFO4 at its defaults at once (lfo4's row dropped: a stock sound,
 *     or one saved by upstream's 1.11 lfo4, whose lane is not a link); a linked one is queued, and the poll (page.c
 *     wr_poll, every UI pass) gives lfo4's table the field once the record is in RAM (store.c may read its cell
 *     later), or the defaults when it has none or its cell is missing.
 *
 * Values go into lfo4's table one at a time through its own ext_set, each of which bumps its generation, so the
 * audio side's cached row (csrc/lfo4/bridge.c) is never left on a half-written one. WT_LFO4 is not must-understand:
 * a build without lfo4 keeps the field as it is, so turning lfo4 off and on again loses nothing. */
#include "wish.h"

#if DN2_LFO4
#define LFO4_N 8u
#define LFO4_PEND 64u

#define EXT_FIND ((u16 *(*)(u32))LFO4_EXT_FIND)
#define EXT_SET ((void (*)(u32, u32, u32))LFO4_EXT_SET)
#define EXT_DROP ((void (*)(u32))LFO4_EXT_DROP)
#define EXT_DEFAULT ((const u16 *)LFO4_EXT_DEFAULT)

static u32 pend[LFO4_PEND] D_;
static u32 npend D_ = 0;
u32 wish_lfo4_out D_ = 0, wish_lfo4_in D_ = 0, wish_lfo4_reset D_ = 0, wish_lfo4_lost D_ = 0;

/* wish_save, first: the record's field from lfo4's table */
void wish_lfo4_save(u32 live)
{
    const u16 *v = EXT_FIND(live);
    u8 b[2u * LFO4_N];
    u32 k, differs = 0;

    for (k = 0; k < LFO4_N; k++) {
        u16 x = v ? v[k] : EXT_DEFAULT[k];
        differs |= x != EXT_DEFAULT[k];
        b[2u * k] = (u8)(x >> 8);
        b[2u * k + 1u] = (u8)x;
    }
    if (differs) {
        if (wish_put(live, WT_LFO4, b, sizeof b) == 0)
            wish_lfo4_out++;
        else
            wish_lfo4_lost++;               /* its record not yet read, or full: the link keeps the last one */
    } else if (wish_find(live)) {
        wish_put(live, WT_LFO4, 0, 0);      /* back at its defaults: no field */
    }
}

/* wish_load: a sound with no link plays LFO4 at its defaults; a linked one waits for its record */
void wish_lfo4_load(u32 live, int linked)
{
    u32 k;

    if (!linked) {
        EXT_DROP(live);
        wish_lfo4_reset++;
        return;
    }
    for (k = 0; k < npend; k++)
        if (pend[k] == live)
            return;
    if (npend < LFO4_PEND)
        pend[npend++] = live;
    else
        wish_lfo4_lost++;
}

/* page.c wr_poll: every linked sound whose record is in RAM gets its LFO4 values */
void wish_lfo4_poll(void)
{
    u32 k = 0;

    while (k < npend) {
        u32 live = pend[k], j;
        struct wish *w = wish_find(live);
        u8 b[2u * LFO4_N];

        if (w && (w->flags & W_WANT) && !(w->flags & W_MISSING)) {
            k++;                            /* its cell still to be read */
            continue;
        }
        if (w && !(w->flags & W_MISSING) && wish_get(live, WT_LFO4, b, sizeof b) == (int)sizeof b) {
            for (j = 0; j < LFO4_N; j++)
                EXT_SET(live, j, (u32)b[2u * j] << 8 | b[2u * j + 1u]);
            wish_lfo4_in++;
        } else {
            EXT_DROP(live);
            wish_lfo4_reset++;
        }
        pend[k] = pend[--npend];
    }
}
#endif
