/* ANALOG 2's PARA on the ColdFire (docs/paraphonic.md; dnfw.engines.analog2.para): which engines play it, and its
 * value in a track's sound. The value is stock record MOD (id 248, frame slot 37, 0..0x300, default 0): 0 OFF, 1..3
 * = 2..4 pitches. Read from the sound as page.c and rec.c read a sound's values (sound at [0x800052a0] + 52 +
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
 * ALL_TYPE_SLOTS): ANALOG 2 (22). JUNO, then the DPRO machines, join here with their DSP side (the User, 2026-11-15:
 * no PARA for SOPHIE or SID 6581) */
static inline int para_engine(int type)
{
    return type == 22;
}

static inline const unsigned char *para_sound(int t)
{
    unsigned char *kit = PARA_KIT;
    if (t < 0 || t > 15 || !kit)
        return 0;
    return kit + PARA_SOUND_BASE + PARA_SOUND_STRIDE * (unsigned int)t;
}

/* track T plays a PARA engine */
static inline int para_track(int t)
{
    const unsigned char *snd = para_sound(t);
    return snd && para_engine((signed char)snd[PARA_SOUND_TYPE]);
}

/* track T's PARA value, 0 (OFF) .. 3, whatever its engine */
static inline int para_value(int t)
{
    const unsigned char *snd = para_sound(t);
    if (!snd)
        return 0;
    int v = *(const unsigned short *)(snd + PARA_SOUND_VALUES + 2u * PARA_SLOT) >> 8;
    return v > 3 ? 3 : v;
}

#endif
