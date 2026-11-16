/* DRONE's HOLD latch on the ColdFire (2026-11-10, docs/drone.md "HOLD"): Optimist's DRONE holds its
 * note past the key-up and past the trig's length while HOLD is on. The DSP never sees a key-up: the
 * frame ISR sends it as the voice's note-off (frame +36, bit voice). Whatever ends a note (a key up, the
 * gate timer of a sequenced note, a voice taken) ORs its bit into one word of the ISR's frame (fp@(-164)),
 * composed at 0x4002708e (+36 in d3, +40 in fp@(-164)); hold_final_hook (hooks.S, at the jsr after it) clears the bits of the latched
 * voices there, so the DSP's voice stays gated (its amp, DRONE's gate) while the DN2 frees its own
 * (measured in the emulator, 2026-11-10: the earlier hooks on the key-held test and the gate timers were
 * not on the played key's release path: the note-off went out with HOLD on).
 *  - hold_len, at a voice's note-on (hooks.S hold_note_hook): on a DRONE track with HOLD on the voice
 *    is latched. The same key again lets that latch go (its note-off goes out) and starts nothing (the
 *    note-on is dropped); another key plays and the track's other latched voices go (DRONE is one
 *    network a track), as Optimist's voice.c drone_latch / drone_unlatch (the User: "As Optimist").
 *  - hold_final: every frame, HOLD off on a latched voice's track lets it go; the released voices'
 *    note-offs are ORed in, the latched voices' taken out.
 * The DSP's DRONE sees no note-off for a latched note, so the next note on the voice is legato. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
#define D __attribute__((section(".data")))

#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define SOUND_STRIDE 1163u
#define SOUND_BASE 52u
#define SOUND_TYPE 0xDEu
#define SOUND_PARAMS 20u                                /* the sound's 16-bit values from +20 (value 101 is +0xDE; page.c, rec.c read them so) */
#define DRONE_TYPE 21                                   /* dnfw.mnm.machines ALL_TYPE_SLOTS */
#define SLOT_HOLD 40                                    /* DRONE's HOLD: page 2's q6, record 253 (frame slot 40) */
#define KEYS_HELD ((int (*)(int))0x4002A3A6u)           /* the stock "a key is held on track t" */
#define NOTE16 ((volatile u32 *)0x8000DDA0u)          /* each voice's note << 16 (the note-on, 0x40026a44) */

u32 hold_seq D = 0;                                     /* the latched voices (bit v) */
u32 hold_key D = 0;                                     /* (unused: the layout's name) */
u8 hold_trk[16] D;                                      /* each latched voice's track */
u32 hold_count D = 0;                                   /* latches made (the emulator reads it) */
u32 hold_drops D = 0;                                   /* same-key note-ons dropped (a latch let go) */
u8 hold_note[16] D;                                     /* each latched voice's note */
u32 hold_rel D = 0;                                     /* latches let go, their note-offs to send in the next frame */

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

/* at a voice's note-on (the frame ISR, hooks.S): its gate length; v the voice, t its track */
int hold_len(int v, int t, int len)
{
    u32 bit = 1u << v;
    if (!hold_on(t)) {
        hold_seq &= ~bit;                                /* (a voice another note takes) */
        return len;
    }
    u8 note = (u8)(NOTE16[v] >> 16);
    for (int j = 0; j < 16; j++)                         /* the same key again: that latch goes, no new note */
        if (((hold_seq >> j) & 1u) && hold_trk[j] == t && hold_note[j] == note) {
            hold_rel |= 1u << j;
            hold_seq &= ~(1u << j);
            hold_drops++;
            return -1;                                   /* hooks.S: the note-on dropped */
        }
    for (int j = 0; j < 16; j++)                         /* the track's other latched voices go */
        if (j != v && ((hold_seq >> j) & 1u) && hold_trk[j] == t) {
            hold_rel |= 1u << j;
            hold_seq &= ~(1u << j);
        }
    hold_seq |= bit;
    hold_trk[v] = (u8)t;
    hold_note[v] = note;
    hold_count++;
    return len;
}

/* the ISR's key-release test (was jsr 0x4002a3a6(t)): stock's answer */
int hold_keys(int t)
{
    return KEYS_HELD(t);
}

/* the UI loop (page.c wr_poll): nothing to do (the latches are looked after in hold_final) */
void hold_poll(void)
{
}

/* the frame ISR's two note-off words as composed, once a frame (hooks.S hold_final_hook): the frame's +36
 * (the amp's note-off, the one DRONE's gate reads) is the register d3 there (0x4002706a..0x40027082, stored
 * at 0x400274ae), its +40 (the filter envelope's) fp@(-164). The latched voices' bits out, the voices let
 * go in; HOLD off on a latched voice's track lets it go. -> the new +36 */
u32 hold_final(u32 off36, u32 *w40)
{
    u32 m = hold_seq;
    for (int v = 0; m && v < 16; v++, m >>= 1)
        if ((m & 1u) && !hold_on(hold_trk[v])) {
            hold_rel |= 1u << v;
            hold_seq &= ~(1u << v);
        }
    *w40 = (*w40 & ~hold_seq) | hold_rel;
    off36 = (off36 & ~hold_seq) | hold_rel;
    hold_rel = 0;
    return off36;
}
