/* DRONE's HOLD latch on the ColdFire (2026-11-10, docs/drone.md "HOLD"): Optimist's DRONE holds its
 * note past the key-up and past the trig's length while HOLD is on. The DSP never sees a key-up: the
 * frame ISR sends it as the voice's note-off (frame +36, bit voice), from two places, both kept from
 * coming here while the track is DRONE with HOLD on:
 *  - a sequenced note: its gate timer (0x80005220[voice], set to the note's length at note-on,
 *    0x40026b04, counted down each ISR; at 0 the voice's note-off and it is freed): hold_len gives it
 *    the longest time instead, and hold_poll tops it up while the latch lasts;
 *  - a played key: the ISR releases a track's key-held voices when no key is held on it
 *    (0x40026f80: jsr 0x4002a3a6(track)); hold_keys answers "held" for a latched track.
 * As Optimist's voice.c drone_latch / drone_unlatch (the User: "As Optimist"): the same key again on a
 * latched note lets it go into its release and starts nothing (the note-on is dropped: its bit cleared,
 * its voice freed at the next ISR); another key plays, and the track's other latched voices go (DRONE is
 * one network a track); HOLD OFF lets every latched one go at once (hold_poll; a key-held one by the
 * ISR's own path, so a key still down plays on). The DSP's DRONE sees no note-off for a latched note,
 * so the next note on the voice is legato (it glides). */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
#define D __attribute__((section(".data")))

#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define SOUND_STRIDE 1163u
#define SOUND_BASE 52u
#define SOUND_TYPE 0xDEu
#define SOUND_PARAMS 48u
#define DRONE_TYPE 21                                   /* dnfw.mnm.machines ALL_TYPE_SLOTS */
#define SLOT_HOLD 40                                    /* DRONE's HOLD: page 2's q6, record 253 (frame slot 40) */
#define GATE ((volatile int *)0x80005220u)              /* the voices' amp gate timers */
#define FGATE ((volatile int *)0x80005260u)             /* ... and filter-envelope gate timers */
#define TRACK_VOICES(t) (*(volatile u32 *)(0x40288844u + 1036u * (u32)(t)))   /* the track's voices (0x4002b1b6) */
#define KEYS_HELD ((int (*)(int))0x4002A3A6u)           /* the stock "a key is held on track t" */
#define KEY_VOICES ((u32 (*)(int))0x4002B1B6u)          /* the stock: track t's key-held voices */
#define NOTE16 ((volatile u32 *)0x8000DDA0u)          /* each voice's note << 16 (the note-on, 0x40026a44) */
#define LATCH 0x7FFFFFFF                                 /* the longest gate (counts down ~14,400 a frame) */
#define TOPUP 0x40000000

u32 hold_seq D = 0;                                     /* voices latched from a sequenced note */
u32 hold_key D = 0;                                     /* ... from a played key (its key up, kept by hold_keys) */
u8 hold_trk[16] D;                                      /* ... and their track */
u32 hold_count D = 0;                                   /* latches made (the emulator reads it) */
u32 hold_drops D = 0;                                   /* same-key note-ons dropped (a latch let go) */
u8 hold_note[16] D;                                     /* each voice's note on a latching track */

static int hold_on(int t)
{
    u8 *kit = KIT_POINTER;
    if (t < 0 || t > 15 || !kit)
        return 0;
    const u8 *snd = kit + SOUND_BASE + SOUND_STRIDE * (u32)t;
    if ((signed char)snd[SOUND_TYPE] != DRONE_TYPE)
        return 0;
    return (*(const u16 *)(snd + SOUND_PARAMS + 2u * SLOT_HOLD) >> 8) >= 64u;   /* the page's two-way rule */
}

static void release(int v)
{
    if (GATE[v] > 0)
        GATE[v] = 1;                                     /* the next ISR: its note-off, the voice freed */
    else if (GATE[v] == 0)
        GATE[v] = 1;                                     /* (a key-held voice of a latched track) */
    if (FGATE[v] > 1)
        FGATE[v] = 1;
}

/* at a voice's note-on (the frame ISR, hooks.S): its gate length; v the voice, t its track */
int hold_len(int v, int t, int len)
{
    if (!hold_on(t))
        return len;
    u32 mine = TRACK_VOICES(t);
    u8 note = (u8)(NOTE16[v] >> 16);
    for (int j = 0; j < 16; j++)                         /* the same key again: that latch goes, no new note */
        if (((mine >> j) & 1u) && hold_note[j] == note && (((hold_seq | hold_key) >> j) & 1u)) {
            release(j);
            hold_seq &= ~(1u << j);
            hold_key &= ~(1u << j);
            hold_note[j] = 0xFF;
            hold_drops++;
            return -1;                                   /* hooks.S: the note-on dropped */
        }
    for (int j = 0; j < 16; j++)                         /* the track's other latched voices go */
        if (j != v && ((mine >> j) & 1u) && (((hold_seq | hold_key) >> j) & 1u)) {
            release(j);
            hold_seq &= ~(1u << j);
            hold_key &= ~(1u << j);
        }
    hold_key &= ~(1u << v);                              /* (this voice: a new note now) */
    hold_note[v] = note;
    if (len != 0) {                                      /* a sequenced note: latched by its timer */
        hold_seq |= 1u << v;
        hold_trk[v] = (u8)t;
        hold_count++;
        return LATCH;
    }
    return len;                                          /* a played key: hold_keys keeps it */
}

/* the ISR's key-release test (was jsr 0x4002a3a6(t)): a latched track's keys are "held" */
int hold_keys(int t)
{
    if (KEYS_HELD(t))
        return 1;
    if (!hold_on(t)) {
        hold_key &= ~TRACK_VOICES(t);                    /* (released by the ISR now: no latch left) */
        return 0;
    }
    hold_key |= KEY_VOICES(t);                           /* every key up on a latching track: latched */
    return 1;
}

/* the UI loop (page.c wr_poll): a latch tops its timer up, and lets go when HOLD goes off or the
 * voice is no longer its track's */
void hold_poll(void)
{
    u32 m = hold_seq;
    for (int v = 0; m && v < 16; v++, m >>= 1) {
        if (!(m & 1u))
            continue;
        int t = hold_trk[v];
        int still = (TRACK_VOICES(t) >> v) & 1u;
        if (!still) {
            hold_seq &= ~(1u << v);
        } else if (!hold_on(t)) {
            release(v);
            hold_seq &= ~(1u << v);
        } else if (GATE[v] > 0 && GATE[v] < TOPUP) {
            GATE[v] = LATCH;
            if (FGATE[v] > 0)
                FGATE[v] = LATCH;
        }
    }
}
