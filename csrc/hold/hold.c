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
    extern volatile u32 dt_sw[];                         /* the test channel's switch HOLD (csrc/devtest/whitelist.c) */
    u8 *kit = KIT_POINTER;
    if (t < 0 || t > 15 || !kit || !dt_sw[0])
        return 0;
    const u8 *snd = kit + SOUND_BASE + SOUND_STRIDE * (u32)t;
    if ((signed char)snd[SOUND_TYPE] != DRONE_TYPE)
        return 0;
    return (*(const u16 *)(snd + SOUND_PARAMS + 2u * SLOT_HOLD) >> 8) >= 64u;   /* the page's two-way rule */
}

/* PARA (ANALOG 2, JUNO; 2026-11-15, dnfw.engines.analog2.para): the DSP plays a chord on the chord's oldest voice, so the
 * chord's envelopes are that voice's, and a PARA track's notes end together. A voice of such a track whose note-off
 * comes while another of the track's voices is held keeps its amp gate (+36) and filter gate (+40) open (para_kept);
 * once none of the track's voices is held, every kept voice's note-off goes out (legato: one envelope a chord, the
 * pilot's). Held, as the DSP's own HELD: from a voice's note-on until its note-off first comes (para_live), so it
 * does not depend on how the gate timers run for a live key. A kept voice that takes a new note leaves para_kept; a
 * track whose PARA goes off lets its kept voices go. */
#include "../para/para.h"                              /* para_track, para_value: the engines and the value */
#define OWNER ((volatile u32 *)0x80005308u)             /* each voice's track (DN2_OWNER_REG) */

u32 para_live D = 0;                                    /* the held voices (bit v) */
u32 para_kept D = 0;                                    /* voices whose note-off is held back */
u32 para_count D = 0;                                   /* frames that held a note-off back (the emulator reads it) */

static int para_on(int t)
{
    return para_track(t) && para_value(t) != 0;
}

/* a note that plays on voice v: held, and no longer kept */
static void para_note(int v)
{
    para_live |= 1u << v;
    para_kept &= ~(1u << v);
}

/* the frame's note-off words (hold_final): each PARA track's note-offs held back while one of its voices is held,
 * and let go together when none is. -> the new +36 */
static u32 para_final(u32 off36, u32 *w40)
{
    para_live &= ~off36;
    u32 seen = 0;
    for (int v = 0; v < 16; v++) {
        u32 t = OWNER[v];
        if (t > 15u || ((seen >> t) & 1u))
            continue;
        seen |= 1u << t;
        u32 mine = 0;
        for (int j = 0; j < 16; j++)
            if (OWNER[j] == t)
                mine |= 1u << j;
        u32 go;
        if (para_on((int)t) && (para_live & mine)) {
            u32 keep = off36 & mine;
            if (keep & ~para_kept)
                para_count++;
            para_kept |= keep;
            go = 0;
        } else {
            go = para_kept & mine;
            para_kept &= ~mine;
        }
        off36 = (off36 & ~(para_kept & mine)) | go;
        *w40 = (*w40 & ~(para_kept & mine)) | go;
    }
    return off36;
}

/* at a voice's note-on (the frame ISR, hooks.S): its gate length; v the voice, t its track. A note that plays
 * (not dropped) restarts the voice's envelopes (csrc/matrix) */
static int hold_len_of(int v, int t, int len);
int hold_len(int v, int t, int len)
{
    extern void mx_env_on(u32 v);
    int r = hold_len_of(v, t, len);
    if (r >= 0) {
        mx_env_on((u32)v);
        para_note(v);
    }
    return r;
}

static int hold_len_of(int v, int t, int len)
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
    off36 = para_final(off36, w40);                              /* PARA: a chord's notes end together */
    { extern void mx_env_off(u32 bits); mx_env_off(off36); }     /* the voices' envelopes released (csrc/matrix) */
    return off36;
}
