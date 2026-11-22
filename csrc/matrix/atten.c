/* DEP, an LFO's global attenuverter (the User, 2026-11-19; docs/matrix.md "DEP: the attenuverter"). OS 1.12, LFO1-3.
 *
 * Every route of an LFO (its first route, stock's DEST, and the record's) is heard at its own depth x DEP: DEP -64..+63
 * is -100..+100 % (+63 and above exactly 100 %, stock's own scale below; negative inverts). DEP stays stock's
 * parameter: its cell, p-locks, CC, Overbridge, the plugin, MOD SETUP and an LFO into DEP move the attenuverter.
 * The first route's own depth is the record's (WT_MX_LFO).
 *
 * Two forms of a sound:
 *   - CONVERTED (a sound of the playing kit, W_ATT in its RAM entry, never stored): DEP is the attenuverter A, the
 *     field holds each LFO's first route's depth D (and A as last saved);
 *   - STORED (what the saver writes, and every sound as the loader leaves it, a sound-lock's pool sound): DEP is
 *     C = D x A, what a stock unit plays (the User: "DEP = first route's depth x the attenuverter").
 * The playing kit's sounds are converted in the UI pass (mx_poll -> mxa_convert): a sound with the field (saved by
 * this build) gets A back (its stored DEP is the field's C; changed on a stock unit: A kept, D = DEP / A, the User's
 * Q4 a); a sound without it (an old project, stock's) gets D = DEP and DEP = 100 % (the User: "the old DEP moves into
 * slot 1's depth at load, DEP set to 100 %"), so it is heard bit for bit as before while its DEP is not modulated.
 * The saver (table.c wish_save) writes C into the stored DEP and A into the field.
 *
 * DEP p-locks are the attenuverter's (the User: "we map the depth plock to our attenuverter"): an old project's DEP
 * locks now scale all of that LFO's routes on their steps; a stock unit plays them as DEP (Q3 a).
 */
#include "../wishes/wish.h"
#include "routes.h"

typedef signed short s16;

#define NONE 0x4000
#define DEP_TOP 0x7FFE
#define FULL_A 0x7FFEu                  /* an imported sound's DEP: the top, inside the 100 % band (+63 and above),
                                         * where the smoother's last unit and CC 127 land too */
#define VSOUND ((volatile u32 *)0x800052A8u)
#define VSRC(v, s) ((volatile u16 *)(0x80003B12u + 202u * (v) + 2u * (s)))   /* voice v's row as stock copied it at
                                         * its note (0x4002549c: the sound's 202 bytes from +20), the smoother's source */
#define RECORD(id) ((const int *)(REC_BASE + 60u * (id)))

u32 mxa_converted D_ = 0, mxa_changed D_ = 0, mxa_saved D_ = 0;   /* the checks: sounds converted, of them changed on
                                                                  * a stock unit, stored DEPs written */

static u32 be16(const u8 *p)
{
    return (u32)p[0] << 8 | p[1];
}

static s32 a_of(u32 a)                  /* DEP's cell -> the attenuverter, Q14 (as hooks.S lfo_fast: 100 % from +63) */
{
    a &= 0xFFFFu;
    return a >= 0x7F00u ? 16384 : (s32)a - NONE;
}

/* the DEP a stock unit plays for a first route of DEPTH under the attenuverter A (DEP's cell) */
u32 mxa_compat(u32 depth, u32 a)
{
    s32 c = NONE + (((s32)depth - NONE) * a_of(a) >> 14);
    return (u32)(c < 0 ? 0 : c > DEP_TOP ? DEP_TOP : c);
}

static void set_dep(u32 sound, u32 l, u32 a)    /* the sound's DEP and the rows of the voices playing it */
{
    u32 slot = (u32)RECORD(mxr_dep_rec[l])[1];
    *(volatile u16 *)(sound + 20u + 2u * slot) = (u16)a;
    for (u32 v = 0; v < 16u; v++)
        if (VSOUND[v] == sound)
            *VSRC(v, slot) = (u16)a;
}

/* (2026-11-21) the conversion's DEP, settled: the sound's DEP and, on each voice playing it whose row holds the sound's
 * DEP (no lock, no slide on it: its smoother's source is the old DEP), the smoother's source, state and output all on
 * A at once. Stock's smoother would glide the row from C to A over tens of frames while the first route already plays
 * D: the LFO heard at D x (C .. A), less than its depth (2026-11-20, the parachord agent). Settled, it is heard at
 * D x A = C from the next frame, as before the conversion (bit for bit for an old sound: A = 100 %, D = C) */
#define SM_STATE(v, s) ((volatile s32 *)(0x8000DE60u + 4u * (17u + 101u * (v) + (s))))
#define SM_OUT(v, s) ((volatile u16 *)(0x800068E4u + 2u * (17u + 101u * (v) + (s))))
static void settle_dep(u32 sound, u32 l, u32 a)
{
    u32 slot = (u32)RECORD(mxr_dep_rec[l])[1];
    volatile u16 *dep = (volatile u16 *)(sound + 20u + 2u * slot);
    u32 old = *dep;
    *dep = (u16)a;
    for (u32 v = 0; v < 16u; v++)
        if (VSOUND[v] == sound && *VSRC(v, slot) == old) {
            *VSRC(v, slot) = (u16)a;
            *SM_STATE(v, slot) = (s32)(a << 16);
            *SM_OUT(v, slot) = (u16)a;
        }
}

/* (2026-11-21) a conversion staged by mxa_convert until matrix.c mx_poll commits it, with the track's new table, every
 * interrupt masked (mx_commit): until then the sound is in its stored form (DEP = C, its field already holds A and D,
 * no W_ATT: what a copy, a save or a sound lock reads is consistent) and the frame plays stock's route 1 on it */
static u32 st_sound[16] D_;
static u16 st_a[16][3] D_;
static u8 st_mask[16] D_;               /* bit l: LFO l's DEP to set; 0x80: staged */
static u8 st_changed[16] D_;
#define MXA_FAIL 0xFFFFFFFFu

/* the UI pass (matrix.c mx_poll), the playing kit's track T (SOUND): -> 1 when its DEP is the attenuverter and the
 * field holds its first routes' depths; 0 when it cannot be (its record still on the +Drive, or locked: it plays as
 * stock, DEP its first routes' depth) */
int mxa_convert(u32 t, u32 sound)
{
    if (t < 16u)
        st_mask[t] = 0;                 /* (2026-11-21) nothing staged unless this call stages it */
    struct wish *w = wish_find(sound);
    if (w && (w->flags & W_ATT))
        return 1;
    if (w && (w->flags & (W_WANT | W_LOCKED)))
        return 0;
    u8 f[12], nf[12];
    int fn = wish_get(sound, WT_MX_LFO, f, sizeof f);
    u32 dep[3], changed = 0;
    for (u32 l = 0; l < 3u; l++) {
        u32 slot = (u32)RECORD(mxr_dep_rec[l])[1], a, d;
        dep[l] = *(const u16 *)(sound + 20u + 2u * slot);
        if (fn >= (int)(4u * l + 4u)) {                 /* saved by this build: its stored DEP is C */
            a = be16(f + 4u * l);
            d = be16(f + 4u * l + 2u);
            if (dep[l] != mxa_compat(d, a)) {           /* DEP changed on a stock unit: A kept, D = DEP / A */
                s32 aa = a_of(a);
                if (aa) {
                    s32 x = ((s32)dep[l] - NONE) * 16384 / aa + NONE;
                    d = (u32)(x < 0 ? 0 : x > DEP_TOP ? DEP_TOP : x);
                }
                changed = 1;
            }
        } else {                                        /* an old sound: DEP its first route's depth, DEP 100 % */
            a = FULL_A;
            d = dep[l];
        }
        nf[4u * l] = (u8)(a >> 8);
        nf[4u * l + 1u] = (u8)a;
        nf[4u * l + 2u] = (u8)(d >> 8);
        nf[4u * l + 3u] = (u8)d;
    }
    if (wish_put(sound, WT_MX_LFO, nf, sizeof nf) != 0)
        return 0;
    if (t >= 16u)
        return 0;
    u32 mask = 0x80u;
    for (u32 l = 0; l < 3u; l++) {
        st_a[t][l] = (u16)be16(nf + 4u * l);
        if (dep[l] != st_a[t][l])
            mask |= 1u << l;
    }
    st_sound[t] = sound;
    st_changed[t] = (u8)changed;
    st_mask[t] = (u8)mask;
    return 1;
}

/* matrix.c mx_poll, with the table's lock and every interrupt masked, as track T's new table goes live: a conversion
 * staged for SOUND made real (DEP the attenuverter, the voices settled, W_ATT) -> the LFOs whose DEP it changed
 * (bit l), 0 when none; MXA_FAIL when the staged conversion cannot be made (the sound's entry gone or not readable
 * since: the caller lays its first routes as stock's, MX_PASS, and the next pass converts it again). The record keeps
 * the stored form until then */
u32 mxa_commit(u32 t, u32 sound)
{
    if (t >= 16u || !st_mask[t])
        return 0;
    u32 mask = st_mask[t] & 7u;
    st_mask[t] = 0;
    struct wish *w = wish_find(sound);
    if (st_sound[t] != sound || !w || (w->flags & (W_WANT | W_LOCKED)))
        return MXA_FAIL;
    for (u32 l = 0; l < 3u; l++)
        if (mask & (1u << l))
            settle_dep(sound, l, st_a[t][l]);
    w->flags |= W_ATT;
    mxa_converted++;
    mxa_changed += st_changed[t];
    return mask;
}

/* converted (its DEP the attenuverter, the field its first routes' depths): routes.c, which never converts (only the
 * UI pass does, with the table: mx_poll) */
int mxa_is_converted(u32 sound)
{
    struct wish *w = wish_find(sound);
    return w && (w->flags & W_ATT) && !(w->flags & (W_WANT | W_LOCKED));
}

/* table.c wish_save, before the record is hashed (W, its entry, held under the table's lock): a converted sound is
 * stored as stock reads it, DEP = C (its first route as heard), the field's A the attenuverter now */
void mxa_save(struct wish *w, u8 *stored, u32 live)
{
    u32 at, n;
    if (!(w->flags & W_ATT) || (w->flags & (W_WANT | W_LOCKED)) || !wish_tlv_find(w->rec, w->len, WT_MX_LFO, &at, &n)
        || n < 12u)
        return;
    u8 nf[12];
    for (u32 k = 0; k < 12u; k++)
        nf[k] = w->rec[at + k];
    for (u32 l = 0; l < 3u; l++) {
        u32 slot = (u32)RECORD(mxr_dep_rec[l])[1];
        u32 a = *(const u16 *)(live + 20u + 2u * slot), c = mxa_compat(be16(nf + 4u * l + 2u), a);
        nf[4u * l] = (u8)(a >> 8);
        nf[4u * l + 1u] = (u8)a;
        stored[WL_STORED(29u + l)] = (u8)(c >> 8);      /* LFO1-3 DEP: stored ids 29, 30, 31 (1.12's id -> slot
                                                         * table 0x401fd03c: slots 8, 16, 24) */
        stored[WL_STORED(29u + l) + 1u] = (u8)c;
    }
    int same = 1;
    for (u32 k = 0; k < 12u; k++)
        same &= nf[k] == w->rec[at + k];
    if (!same) {
        int len = wish_tlv_put(w->rec, w->len, WT_MX_LFO, nf, sizeof nf);
        if (len > 0) {
            w->len = (u16)len;
            w->flags |= W_DIRTY;
            w->flags &= (u8)~W_DISK;
            wish_edits++;
        }
    }
    mxa_saved++;
}

/* (2026-11-19) a converted sound copied anywhere but the playing kit (stock's copies: into the pool, a clipboard, a
 * pattern's kit), from table.c's ring: stored there as the saver stores it (DEP = C, the field's A the attenuverter),
 * W_ATT off, so a sound lock on it plays its first routes as heard (stock's route 1, DEP their depth). The playing
 * kit's own (a copy between its tracks) stay converted. matrix.c mx_poll, every UI pass (one compare when none) */
extern u32 wish_att_ring[], wish_att_head, wish_att_tail;
u32 mxa_stored D_ = 0;                  /* the checks: copies stored */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)

static void store_one(u32 sound)
{
    u8 f[12];
    struct wish *w = wish_find(sound);
    if (!w || !(w->flags & W_ATT) || (w->flags & (W_WANT | W_LOCKED))
        || wish_get(sound, WT_MX_LFO, f, sizeof f) != (int)sizeof f)
        return;
    for (u32 l = 0; l < 3u; l++) {
        u32 slot = (u32)RECORD(mxr_dep_rec[l])[1];
        u32 a = *(const u16 *)(sound + 20u + 2u * slot);
        f[4u * l] = (u8)(a >> 8);
        f[4u * l + 1u] = (u8)a;
        set_dep(sound, l, mxa_compat(be16(f + 4u * l + 2u), a));
    }
    wish_put(sound, WT_MX_LFO, f, sizeof f);
    w = wish_find(sound);
    if (w)
        w->flags &= (u8)~W_ATT;
    mxa_stored++;
}

void mxa_moved(void)
{
    u32 kit = (u32)KIT_POINTER;
    while (wish_att_tail != wish_att_head) {
        u32 s = wish_att_ring[wish_att_tail % 32u], off = s - (kit + 52u);
        wish_att_tail++;
        if (kit && off < 16u * 1163u && off % 1163u == 0u)
            continue;                   /* a sound of the playing kit: converted it stays */
        store_one(s);
    }
}
