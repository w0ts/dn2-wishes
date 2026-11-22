/* PARA as one voice (csrc/para/one.c, docs/paraphonic-onevoice.md): a chord per leader slot, its places. */
#ifndef PARA_ONE_H
#define PARA_ONE_H

#define PV_PLACES   10                  /* place 0 the leader's own note, 1..9 the joined ones (8 sound, one fading) */
#ifndef PV_ROW_WORDS
#define PV_ROW_WORDS 6                  /* a slot's row for the DSP: 12 halfwords (the chord, 10 places, a spare) */
#endif
_Static_assert(PV_ROW_WORDS == 6 && 1 + PV_PLACES <= 2 * PV_ROW_WORDS, "the row holds the chord and its places");

#define PV_USED  0x01u                  /* the place has had a note in this chord */
#define PV_HELD  0x02u                  /* its note is held (its key, or its gate timer running) */
#define PV_SOUND 0x04u                  /* it sounds (not dropped for a newer note) */
#define PV_TIMED 0x08u                  /* a sequenced note: it ends by its gate timer, not a key-up */

#define PV_LIVE      1                  /* pv_chord.live: a note of the chord held (joins go to it) */
#define PV_RELEASING 2                  /* nothing held, its note-off sent: its row stays live for the DSP's release
                                         * tail until the DSP reports the slot quiet (2026-11-18) */

typedef struct {
    unsigned char note, flags, seq, pad;
    int len;                            /* its gate timer (as 0x80005220[k] for a slot) */
    unsigned int age, born;             /* its order in the chord; the frame it came */
} pv_entry;

typedef struct {
    unsigned char live, track, seq, pad;
    unsigned int ages;                  /* the chord's notes so far (each place's age) */
    pv_entry e[PV_PLACES];
} pv_chord;

#endif
