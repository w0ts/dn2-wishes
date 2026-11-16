/* The load labels' event stamps (meter.c icons_live, mtr_tlm): the frame an event happened, never 0
 * (0: none yet), and its age.
 *
 * The stamp is f | 1, so it is never 0; on an even frame that is f + 1, a frame ahead. Its age is taken
 * from f | 1 too: 0 at the event, never -1. 2026-11-14: the age was f - stamp, which on an even frame
 * wraps to 0xFFFFFFFF, so a label over its limit went dark on every poll that fell on an even frame
 * (and the telemetry's "frames since" read 4,294,967,295 there). An age may be a frame off either way
 * (an even frame's stamp is a frame ahead; an odd one seen from an even frame, a frame behind); the
 * hold is 1,500 frames. */
#ifndef MTR_STAMP_H
#define MTR_STAMP_H

static inline unsigned int mtr_stamp(unsigned int f)
{
    return f | 1u;
}

static inline unsigned int mtr_age(unsigned int at, unsigned int f)
{
    return (f | 1u) - at;
}

#endif
