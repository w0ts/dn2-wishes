/* Knob precision: virtual notches and our popups' slow turns (the User, 2026-11-19; docs/knob-notch.md). OS 1.12.
 *
 * The encoders have no physical detents: the panel sends counts, about 15 records a second (one every 4 ticks of
 * the 60 Hz timer wheel, clamped to +/-30), each carrying the counts turned since the last. Everything here is in
 * those counts. Stock's own integer knobs move one step every 3 counts (the knob step 0x4011364e's divisor), so
 * "a small move" below is 3 counts.
 *
 * The constants are the tuning: change them here, rebuild, nothing else moves. */
#ifndef KNOB_H
#define KNOB_H

typedef unsigned int u32;                               /* (as every C file of ours: identical typedefs) */
typedef unsigned char u8;
typedef unsigned short u16;
typedef int s32;

/* the notch */
#define KN_HOLD        9        /* counts held at the notch once caught: 3 small moves (stock's 3 counts a step) */
#define KN_PASS       12        /* a record of this many counts or more is a fast turn: it passes the notch (12 in
                                 * 1/15 s = 180 counts a second, where stock's integer knobs start to accelerate) */
#define KN_HOLD_END 2250u       /* frames (1,500 a second): a pause of 1.5 s ends a hold */

/* our popups' turns (routes popup, DEST popup, ENV2's page): units moved for a record of D counts */
#define KN_POP_SLOW    4        /* a record of at most this many counts is a slow turn ... */
#define KN_POP_DIV     3        /* ... moving 1 unit every KN_POP_DIV counts (stock's integer knobs' rate) */
#define KN_POP_FAST   12        /* a record of this many counts or more: KN_POP_FAST_MUL units a count; between the two,
                                 * 1 unit a count (the popups' rate before 2026-11-19) */
#define KN_POP_FAST_MUL 2
#define KN_REM_END  3000u       /* frames: a slow turn's leftover counts are kept 2 s (and dropped on a turn back) */

/* (2026-11-20, the User: "if the knob is pressed and moved less than ~3-5 counts, revert the counts") a plain push's
 * own knob turned while held: under this many counts (summed, either way) it is a push that wobbled, not stock's
 * push + turn. Those counts are held back (no value moves) and the routes popup opens at the release; at this many
 * counts they all go on to stock at once (its push + turn's big steps) and no popup opens (csrc/matrix/routes_pop.c) */
#define KN_PUSH_WOBBLE 4

/* the knob of the UI item being handled (1 A .. 8 H), 0 none; its counts (rec.c smp_ui_pop -> kn_item) */
extern u32 kn_cur, kn_tcb;
extern int kn_d;

void kn_item(const u8 *it);
/* a knob-driven write of the value of KEY from OLD to NOW, with its notch at N: -> the value to write. Outside a
 * knob item (CC, NRPN, Overbridge, a load, our own writes) -> NOW as it is */
s32 kn_value(u32 key, s32 old, s32 now, s32 n);
/* stock's records: the notch of record ID (its value at the centre, units of 1/256), -1 none */
s32 kn_centre(u32 id);
/* our popups: the units a record of D counts moves (the current knob's leftover kept) */
int kn_units(int d);
/* a depth (0 .. top, 1/256 units, a route's or the attenuverter's) turned by UNITS whole units: kept on whole units
 * (a fraction is dropped by the first turn), clamped to 0 .. TOP */
s32 kn_whole(s32 dep, int units, s32 top);

#define KN_KEY_LOCK   0x10000u  /* stock's records: a p-lock's key (the record id beside it) */
#define KN_KEY_POP    0x20000u  /* our popups: + (popup << 12) + the row */

#endif
