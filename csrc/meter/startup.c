/* The DSP and CLIP labels while the DN2 starts (2026-11-20, the User: "at boot it says !CLIP and !DSP... I suppose
 * it's the boot-up, but can we fix it?"; docs/meter.md, "The labels while the DN2 starts").
 *
 * At power-on the ColdFire's labels see the DSP's first reports: the guard's skips and its load while every voice and
 * every machine is set up (perc2b), and the clip word of our DSP program's first blocks, when stock's buffers (the
 * input's block, the main mix, the send effects) may not have been written yet. None of that is a clip or an overload
 * of the instrument in use. So, as the CPU label is quiet while stock loads (quiet.c), the DSP and CLIP labels are
 * quiet from the load (every boot: this file's words are code data, 0 after every load) until the start-up is over:
 * stock's loading over (QUIET_LOADING gone) AND our DSP program reporting (an idle packet with its load within the
 * last second, smp_dsp_load) without a break for START_SETTLE frames. Every clip stamped during the start-up is
 * forgotten (mix_clip_forget: the CLIP label's 3 s and the MIXER pages' latches); the DSP label's stamp and
 * hysteresis are cleared by its caller (meter.c icons_live). After, the labels are as before: a clip or an overload
 * from then on lights them at once. The skips and the load peak stamped during the start-up need no forgetting: they
 * last half a second (link.c smp_skipped, smp_load_at), less than the settle.
 *
 * An OS upgrade (QUIET_UPGRADE) does not start it again: the labels there are smp_bulk_recent's (meter.c). */

typedef unsigned int u32;

#include "quiet.h"
#include "stamp.h"

#define START_SETTLE 3000u              /* frames (1,500 a second): the DSP reporting 2 s after stock's loading */

#ifndef START_HOST
#define D __attribute__((section(".data")))
#else
#define D
#endif

u32 mtr_start_done D = 0;               /* 1: the start-up is over (until the next load) */
u32 mtr_start_at D = 0;                 /* the stamp the DSP's reports began at with the loading over (0: not yet) */
u32 mtr_start_polls D = 0;              /* (the checks) polls quiet for the start-up */

extern int smp_dsp_load(void);          /* link.c: the DSP's load in percent, -1 with no report in the last second */
extern void mix_clip_forget(void);      /* mixer.c: every clip stamp forgotten */

/* meter.c icons_live, every poll: 1 while the DSP and CLIP labels are quiet for the start-up */
int mtr_starting(u32 f, u32 quiet)
{
    if (mtr_start_done)
        return 0;
    if ((quiet & QUIET_LOADING) || smp_dsp_load() < 0)
        mtr_start_at = 0;               /* stock still loading, or the DSP not (or no longer) reporting: from the top */
    else if (!mtr_start_at)
        mtr_start_at = mtr_stamp(f);
    else if (mtr_age(mtr_start_at, f) >= START_SETTLE)
        mtr_start_done = 1;
    mix_clip_forget();                  /* every poll of the start-up, its last one included */
    mtr_start_polls++;
    return !mtr_start_done;
}
