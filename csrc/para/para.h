/* ANALOG 2's PARA on the ColdFire (docs/paraphonic.md; dnfw.engines.analog2.para): which engines play it, and its
 * value in a track's sound. The value is stock record MOD (id 248, frame slot 37, 0..0x300, default 0): 0 OFF, any
 * other ON (2026-11-15, the User: "i would have expected the para ... to be on or off"): a chord of PARA_NOTES (8,
 * "Up to 8"). ON is stored as 3 (an older build's 4 pitches); an older project's 1 or 2 reads as ON. Read from the sound as page.c and rec.c read a sound's values (sound at [0x800052a0] + 52 +
 * 1163 t, its 16-bit values from +20, the machine type value 101 at +0xDE). */
#ifndef PARA_H
#define PARA_H

#define PARA_KIT          (*(unsigned char *volatile *)0x800052A0u)
#define PARA_SOUND_BASE   52u
#define PARA_SOUND_STRIDE 1163u
#define PARA_SOUND_TYPE   0xDEu
#define PARA_SOUND_VALUES 20u
#define PARA_SLOT         37u                     /* MOD's frame slot */
#define PARA_RECORD       248u                    /* MOD's record id (the knob path's setValue) */

/* the engines PARA plays (dnfw.engines.analog2.para ENGINES; their machine type values, dnfw.mnm.machines
 * ALL_TYPE_SLOTS): ANALOG 2 (22), JUNO (23, 2026-11-15). The User, 2026-11-15: no PARA for SOPHIE, SID 6581, DPRO-DDRW
 * or DPRO-DENS; DPRO-WAVE decided later */
#define PARA_TYPE_A2   22
#define PARA_TYPE_JUNO 23
static inline int para_engine(int type)
{
    return type == PARA_TYPE_A2 || type == PARA_TYPE_JUNO;
}

static inline const unsigned char *para_sound(int t)
{
    unsigned char *kit = PARA_KIT;
    if (t < 0 || t > 15 || !kit)
        return 0;
    return kit + PARA_SOUND_BASE + PARA_SOUND_STRIDE * (unsigned int)t;
}

/* track T's machine type value (-1: no kit) */
static inline int para_type(int t)
{
    const unsigned char *snd = para_sound(t);
    return snd ? (signed char)snd[PARA_SOUND_TYPE] : -1;
}

/* track T plays a PARA engine */
static inline int para_track(int t)
{
    const unsigned char *snd = para_sound(t);
    return snd && para_engine((signed char)snd[PARA_SOUND_TYPE]);
}

#define PARA_ON 3                               /* the value stored for ON (an older build plays it as its 4 notes) */
#define PARA_NOTES 8                            /* ON: a chord's notes (dnfw.engines.analog2.para PITCHES; the User,
                                                 * 2026-11-15: "Up to 8") */

/* track T's PARA value, 0 (OFF) or PARA_ON (any stored value but 0), whatever its engine */
static inline int para_value(int t)
{
    const unsigned char *snd = para_sound(t);
    if (!snd)
        return 0;
    int v = *(const unsigned short *)(snd + PARA_SOUND_VALUES + 2u * PARA_SLOT) >> 8;
    return v ? PARA_ON : 0;
}

#endif
