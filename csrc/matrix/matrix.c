/* The modulation matrix: more routes than stock's one per LFO, and two envelopes (the User, 2026-11-11: up to 16 LFO
 * routes a track, LFO1-3 sharing them, stock's route 1 of each LFO counting; ENV1 and ENV2 with four destinations
 * each; docs/matrix.md). OS 1.12.
 *
 * A sound's routes are a field of its wishes record (csrc/wishes, tag WT_MX_ROUTES): four bytes each, the source
 * (0 LFO1, 1 LFO2, 2 LFO3, 3 ENV1, 4 ENV2), the destination slot (25..100, a sound parameter's cell of the voice row),
 * and the depth in stock DEP's units (0..0x7ffe, 0x4000 none). ENV2's settings are another field (WT_MX_ENV:
 * ATK HOLD DEC SUS REL MODE RSET and a byte kept 0, stock's AMP envelope's own records' values; env2_page.c).
 *
 * Heard (mx_eval, from the frame's evaluator call, csrc/modulation/hooks.S mod_eval): after stock's evaluator
 * 0x40137a06 has run every voice row's LFO1-3 and their stock routes, each row steps its two envelopes, then gets its
 * track's routes, the same arithmetic as stock's route 1 (0x40137d6a): cell += mac((depth - 0x4000) x 2, source),
 * clamped to 0..0x7f00. An LFO's output is the one stock's route 1 uses (state + 84, after the fade); an envelope's
 * is its level, 0..0x7fffffff (unipolar: a depth under 0x4000 moves the parameter down). A route into an LFO's own
 * controls (slots 1..24) is not offered: it would come after that LFO has read them (stock's DEST, and
 * csrc/modulation's cascade, still reach them).
 *
 * The envelopes (the User, 2026-11-12: ENV1 IS stock's AMP envelope, still on the amp and now also routable; ENV2 "a
 * clone of env1"): a ColdFire clone of stock's AMP envelope, which runs on the SHARC (section 7) and is not read from
 * there. One pair a voice, stepped once a frame (the DSP's block, 32 samples): ENV1 from the voice row's own AMP
 * cells (ATK 81, HOLD 82, DEC 83, SUS 84, REL 85, MODE 91, RSET 92: what the DSP is sent, LFOs and locks included),
 * ENV2 from the track's record, a trig's ENV2 locks over it (csrc/slides, kinds 3..8). Measured in Elektron's own DSP code (the SHARC runner, scripts/gen_matrix_env.py's
 * table): the attack is linear (ATK a length in samples), the decay and release geometric (a ratio a block), knob
 * by knob. MODE 1 (ADSR): attack, decay to SUS, at the note-off a release to 0. MODE 0 (AHD): attack, HOLD (127 until
 * the note-off), then a decay to 0; a note-off during the attack starts that decay, one during a timed hold is not
 * heard. A note-on with RSET 1 restarts from 0, with RSET 0 the attack goes on from the level reached.
 * The amp's sound is untouched: nothing here is sent to the DSP.
 *
 * Constant cost (the User's choice): every row steps both envelopes and runs all MX_SLOTS routes each frame; an unused
 * route adds 0 into a scratch row of ours instead of a cell, so a frame costs the same with no route as with every
 * route set.
 *
 * Read in the UI pass, never in the frame (mx_poll, from page.c wr_poll): when a record changed (wish_edits) or the
 * kit moved, each track's fields are read from its sound's record and laid out into the track's spare table, which
 * then becomes the live one. The frame reads only those tables. A voice's track is the kit sound it plays (stock
 * keeps the sound a voice plays at 0x800052a8, written with the voice's parameters by 0x4002549c; LFO4 keyed on it
 * on 1.11, measured on the instrument): a voice playing any other sound gets no routes, its envelopes at rest.
 */
#include "../wishes/wish.h"
#include "env_table.h"

typedef signed short s16;
typedef unsigned long mx_addr;          /* an address: 32 bits here, the host's width in the host tests */

#define MX_LFO 15                       /* routes beside stock's three: 16 a track, at least one stock route used */
#define MX_ENVR 4                       /* each envelope's routes */
#define MX_SLOTS (MX_LFO + 2 * MX_ENVR) /* LFO routes 0..14, ENV1's 15..18, ENV2's 19..22 */
#define MX_SRCS 5                       /* LFO1, LFO2, LFO3, ENV1, ENV2 */
#define MX_TOP 0x7F00                   /* the evaluator's clamp (0x40137da2) */
#define MX_DEP_TOP 0x7FFE              /* DEP's top (records 83, 93, 103): a route's depth, as stock's */
#define MX_NONE 0x4000u                 /* a depth that adds nothing */
#define MX_MAGIC 0x4D583034u            /* 'MX04' */
#define ENV_FULL 0x7FFFFFFF
#define ENV_REST 0x100                  /* a fall this close to 0 is over */
#define HOLD_GATE 0xFFFFFFFFu           /* HOLD 127: until the note-off */
enum { E_REST, E_ATK, E_HOLD, E_DEC, E_REL, E_FALL };   /* E_FALL: AHD's decay to 0 */
enum { K_ATK, K_HOLD, K_DEC, K_SUS, K_REL, K_MODE, K_RSET, K_N = 8 };
static const u8 ENV1_SLOT[7] = {81, 82, 83, 84, 85, 91, 92};

#ifndef MX_HOST
#define OUT_B 0x800068E4u               /* the evaluator's first argument: row v's slot s at OUT_B + 34 + 202 v + 2 s */
#define VSOUND ((volatile u32 *)0x800052A8u)    /* the sound voice v plays */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define LFO_OUT(v) ((volatile u8 *)(0x44640C1Cu + 120u * (u32)(v)))    /* LFO l at + 40 l: state + 84 */
#endif

struct mx_e {
    s32 cell;                           /* the cell's byte offset from the row's slot 0, or the scratch row's */
    s32 d1;                             /* (depth - 0x4000) x 2, as stock's route 1 takes DEP */
    s32 src;                            /* the source's byte offset from the row's LFO1 output */
};
struct mx_env {
    s32 level;                          /* 1.31, 0..full scale */
    u32 hold;                           /* samples of HOLD left (HOLD_GATE: until the note-off) */
    u8 stage, on, off, pad;             /* on, off: a note-on / note-off since the last frame */
};
struct mx_tab {
    struct mx_e e[MX_SLOTS];
    u8 env2[K_N];                       /* ENV2's knobs (the record's, else stock's defaults) */
};
struct mx_state {
    u32 magic;
    u32 edits;                          /* wish_edits when the tables were last laid out */
    u32 kit;                            /* the kit they were laid out for */
    u32 compiles, frames;               /* the checks' */
    u32 ons, offs;                      /* note-ons and note-offs the envelopes saw (the checks) */
    u32 sound[16];                      /* the sound track t's table was laid out from */
    u32 live[16];                       /* track t's live table: 0 or 1 */
    struct mx_env env[16][2];           /* each voice's ENV1, ENV2 */
    u8 e2_lock[16][7];                  /* each voice's ENV2 locks from its last trig (K_ order), 0xff none (a row of
                                         * 7: 8 would be indexed at scale 8, which the ColdFire has not) */
    u16 e2_locked;                      /* bit v: voice v's last trig held an ENV2 lock (only those are merged) */
    struct mx_tab tab[16][2];
    struct mx_tab none;                 /* every route unused, the envelopes still */
    s32 env_out[16 * 30];               /* each voice's ENV1, ENV2 levels at [30 v], [30 v + 1]: a row's stride is
                                         * the LFOs' (120 B), so one offset fits every row */
    u16 scratch[16 * 101];              /* where an unused route adds 0: a row's stride, so one offset fits every row */
};
#ifdef MX_HOST                                                          /* test/test_matrix_c.py */
extern struct mx_state mx_host_state;
extern u16 mx_host_rows[];
extern u32 mx_host_kit, mx_host_vsound[16];
extern s32 mx_host_lfo[16 * 30];
#define MX (&mx_host_state)
#define OUT_B ((mx_addr)mx_host_rows)
#define VSOUND mx_host_vsound
#define LFO_OUT(v) ((volatile u8 *)(mx_host_lfo + 30u * (u32)(v)))
#else
#define MX ((struct mx_state *)MX_RAM)
_Static_assert(sizeof(struct mx_state) <= MX_BYTES, "the matrix's tables fit MX_RAM");
#endif

u32 mx_compiles D_ = 0;

static s32 none_cell(void)
{
    return (s32)((mx_addr)MX->scratch - (OUT_B + 34u));
}

static s32 src_of(u32 src)
{
    if (src < 3u)
        return (s32)(40u * src);
    return (s32)((mx_addr)MX->env_out - (mx_addr)LFO_OUT(0)) + (s32)(4u * (src - 3u));
}

static void lay_none(struct mx_tab *t)
{
    for (u32 k = 0; k < MX_SLOTS; k++) {
        t->e[k].cell = none_cell();
        t->e[k].d1 = 0;
        t->e[k].src = 0;
    }
    for (u32 k = 0; k < K_N; k++)
        t->env2[k] = 0;
}

/* a record's routes (VAL, N bytes) and ENV2's knobs (ENV, EN bytes) -> TAB; -> the routes laid out. Anything out of
 * range is left unused; no ENV2 field: stock's AMP defaults (records 62..66, 73, 74: ATK 8, HOLD 127, DEC 32,
 * SUS 96, REL 24, ADSR, RSET on). */
u32 mx_lay(const u8 *val, int n, const u8 *env, int en, struct mx_tab *tab)
{
    static const u8 plain[K_N] = {8, 127, 32, 96, 24, 1, 1, 0};
    u32 lfo = 0, envs[2] = {0, 0};

    lay_none(tab);
    for (int at = 0; at + 4 <= n; at += 4) {
        u32 src = val[at], slot = val[at + 1], dep = (u32)val[at + 2] << 8 | val[at + 3], k;
        if (src >= MX_SRCS || slot < 25u || slot > 100u)
            continue;
        if (src < 3u) {
            if (lfo >= MX_LFO)
                continue;
            k = lfo++;
        } else {
            if (envs[src - 3u] >= MX_ENVR)
                continue;
            k = MX_LFO + MX_ENVR * (src - 3u) + envs[src - 3u]++;
        }
        if (dep > MX_DEP_TOP)
            dep = MX_DEP_TOP;
        tab->e[k].cell = (s32)(2u * slot);
        tab->e[k].d1 = ((s32)dep - (s32)MX_NONE) * 2;
        tab->e[k].src = src_of(src);
    }
    if (en < (int)K_N)
        env = plain;
    for (u32 k = 0; k < K_N; k++)
        tab->env2[k] = (u8)(k == K_MODE || k == K_RSET ? env[k] != 0 : env[k] > 127u ? 127u : env[k]);
    return lfo + envs[0] + envs[1];
}

static void mx_zero(void)
{
    u32 *w = (u32 *)MX;
    for (u32 k = 0; k < sizeof(struct mx_state) / 4; k++)
        w[k] = 0;
    for (u32 v = 0; v < 16u; v++)
        for (u32 j = 0; j < 7u; j++)
            MX->e2_lock[v][j] = 0xFF;
    lay_none(&MX->none);
    for (u32 t = 0; t < 16; t++) {
        lay_none(&MX->tab[t][0]);
        lay_none(&MX->tab[t][1]);
    }
    MX->edits = wish_edits - 1u;        /* the first pass lays everything out */
    MX->magic = MX_MAGIC;
}

/* the UI pass: each track's table laid out again when any record changed or the kit moved */
void mx_poll(void)
{
    u8 buf[4 * MX_SLOTS + 8], env[8];
    u32 kit, edits;

    if (MX->magic != MX_MAGIC)
        mx_zero();
#ifdef MX_HOST
    kit = mx_host_kit;
#else
    kit = (u32)KIT_POINTER;
#endif
    edits = wish_edits;
    if (!kit || (edits == MX->edits && kit == MX->kit))
        return;
    MX->edits = edits;                  /* first: a change meanwhile is seen at the next pass */
    MX->kit = kit;
    for (u32 t = 0; t < 16; t++) {
        u32 sound = kit + 52u + 1163u * t, spare = MX->live[t] ^ 1u;
        int n = wish_get(sound, WT_MX_ROUTES, buf, sizeof buf);
        int en = wish_get(sound, WT_MX_ENV, env, sizeof env);
        mx_lay(buf, n, env, en, &MX->tab[t][spare]);
        MX->live[t] = spare;            /* the frame takes the new table from its next row */
        MX->sound[t] = sound;
    }
    MX->compiles++;
    mx_compiles++;
}

/* the lock applier's trig on voice V (csrc/slides sl_apply): its ENV2 locks (ATK DEC SUS REL MODE RSET, 0xffff none;
 * E2 0: none), which ENV2 takes in place of the record's knobs until the voice's next trig */
void mx_env2_locks(u32 v, const u16 *e2)
{
    static const u8 KNOB[6] = {K_ATK, K_DEC, K_SUS, K_REL, K_MODE, K_RSET};
    if (MX->magic != MX_MAGIC || v > 15u)
        return;
    u32 any = 0;
    for (u32 j = 0; j < 6u; j++) {
        u8 x = (u8)(!e2 || e2[j] > 127u ? 0xFFu : e2[j]);
        MX->e2_lock[v][KNOB[j]] = x;
        any |= x != 0xFFu;
    }
    MX->e2_locked = (u16)(any ? MX->e2_locked | 1u << v : MX->e2_locked & ~(1u << v));
}

/* a note-on on voice V (the frame, csrc/hold hold_len): its envelopes start at the frame's step */
void mx_env_on(u32 v)
{
    if (MX->magic != MX_MAGIC || v > 15u)
        return;
    MX->env[v][0].on = MX->env[v][1].on = 1;
    MX->env[v][0].off = MX->env[v][1].off = 0;
    MX->ons++;
}

/* the frame's note-off word (bit v: voice v's note ends; csrc/hold hold_final): heard at the frame's step */
void mx_env_off(u32 bits)
{
    if (MX->magic != MX_MAGIC || !(bits & 0xFFFFu))
        return;
    for (u32 v = 0; v < 16u; v++, bits >>= 1)
        if (bits & 1u)
            MX->env[v][0].off = MX->env[v][1].off = 1;
    MX->offs++;
}

static inline s32 mx_mac(s32 a, s32 b)
{
#ifdef __m68k__
    s32 r;
    __asm__ volatile ("mac.l %1,%2,%%acc0\n\tmovclr.l %%acc0,%0" : "=d"(r) : "d"(a), "d"(b));
    return r;
#else
    return (s32)(((long long)a * b) >> 31);         /* the host's model of the frame's fractional MACSR */
#endif
}

/* one frame of one envelope, its knobs K (0..127; MODE, RSET 0 / 1); -> its level */
/* D after N samples of a geometric fall at R a sample (the rest of the block after the attack ends inside it) */
static s32 fall_samples(s32 d, s32 r, u32 n)
{
    while (n--)
        d = mx_mac(d, r);
    return d;
}

static s32 env_step(struct mx_env *e, const u8 *k)
{
    s32 x = e->level, s = (s32)ENV_ATK_S[k[K_ATK]];
    s32 inc = s >= ENV_FULL / 32 ? ENV_FULL : s << 5;  /* a block's step (an attack inside one block: full scale) */
    int ahd = !k[K_MODE];

    if (e->on) {                                        /* RSET: from 0, half a sample's step in; else on from the
                                                         * level reached (0 at rest), as the DSP does */
        e->on = 0;
        if (k[K_RSET])
            x = s >> 1;
        e->stage = E_ATK;
    }
    if (e->off) {
        e->off = 0;
        if (ahd ? (e->stage == E_ATK || (e->stage == E_HOLD && e->hold == HOLD_GATE)) : e->stage != E_REST)
            e->stage = ahd ? E_FALL : E_REL;
    }
    switch (e->stage) {
    case E_ATK:
        if (x >= ENV_FULL - inc) {                      /* full scale inside this block: the samples after it go
                                                         * on into the next stage, as the DSP's do */
            u32 used = s == ENV_FULL ? 0u : ((u32)(ENV_FULL - x) + (u32)s - 1u) / (u32)s;   /* ATK 0: none */
            u32 rest = used < 32u ? 32u - used : 0u;
            s32 sus = (s32)(k[K_SUS] * (ENV_FULL / 127u)), r = (s32)ENV_DEC_S[k[K_DEC]];
            x = ENV_FULL;
            if (ahd) {                                  /* AHD: the hold counts from that sample */
                e->hold = ENV_HOLD[k[K_HOLD]];
                e->stage = E_HOLD;
                if (e->hold != HOLD_GATE) {
                    if (e->hold >= rest)
                        e->hold -= rest;
                    else {
                        x = fall_samples(x, r, rest - e->hold);
                        e->hold = 0;
                        e->stage = E_FALL;
                    }
                }
            } else {
                e->stage = E_DEC;
                x = sus + fall_samples(x - sus, r, rest);
            }
        } else
            x += inc;
        break;
    case E_HOLD:
        if (e->hold != HOLD_GATE) {
            if (e->hold >= 32u)
                e->hold -= 32u;
            else {                                      /* it runs out inside this block: the rest falls */
                x = fall_samples(x, (s32)ENV_DEC_S[k[K_DEC]], 32u - e->hold);
                e->hold = 0;
                e->stage = E_FALL;
            }
        }
        break;
    case E_DEC: {
        s32 sus = (s32)(k[K_SUS] * (ENV_FULL / 127u));
        x = sus + mx_mac(x - sus, (s32)ENV_DEC[k[K_DEC]]);
        break;
    }
    case E_REL:
    case E_FALL:
        x = mx_mac(x, (s32)(e->stage == E_REL ? ENV_REL[k[K_REL]] : ENV_DEC[k[K_DEC]]));
        if (x < ENV_REST) {
            x = 0;
            e->stage = E_REST;
        }
        break;
    default:
        x = 0;
    }
    e->level = x;
    return x;
}

/* a source's value on voice V now (the routes popup's moving bar): LFO1-3's output, ENV1's and ENV2's level, 1.31 */
int mx_route_level(u32 v, u32 src)
{
    if (MX->magic != MX_MAGIC || v > 15u || src > 4u)
        return 0;
    return src < 3u ? *(volatile s32 *)(LFO_OUT(v) + 40u * src) : MX->env_out[30u * v + src - 3u];
}

/* the frame, after stock's evaluator: B its first argument (the mirror OUT_B). Every row, both envelopes, every
 * route. */
void mx_eval(mx_addr b)
{
    if (MX->magic != MX_MAGIC)
        return;                         /* no UI pass yet since power-on */
    MX->frames++;
    for (u32 v = 0; v < 16; v++) {
        u32 snd = VSOUND[v], off = snd - (MX->kit + 52u);
        u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;     /* off / 1163, exact for a whole sound 0..15 */
        const struct mx_tab *tab = &MX->none;
        if (t < 16u && snd == MX->sound[t])
            tab = &MX->tab[t][MX->live[t]];
        u8 *row = (u8 *)(b + 34u + 202u * v);
        u8 k1[K_N];
        for (u32 j = 0; j < 7u; j++) {                  /* ENV1: the row's own AMP cells, as the DSP is sent them */
            u32 c = *(volatile u16 *)(row + 2u * ENV1_SLOT[j]) >> 8;
            k1[j] = (u8)(j == K_MODE || j == K_RSET ? c != 0 : c > 127u ? 127u : c);
        }
        MX->env_out[30u * v] = env_step(&MX->env[v][0], k1);
        const u8 *k2 = tab->env2;
        u8 merged[K_N];
        if (MX->e2_locked >> v & 1u) {                  /* ENV2: the trig's locks over the record's knobs */
            const u8 *lk = MX->e2_lock[v];
            for (u32 j = 0; j < 7u; j++)
                merged[j] = lk[j] != 0xFFu ? lk[j] : tab->env2[j];
            merged[7] = 0;
            k2 = merged;
        }
        MX->env_out[30u * v + 1u] = env_step(&MX->env[v][1], k2);
        volatile u8 *lfo = LFO_OUT(v);
        const struct mx_e *e = tab->e;
#ifdef __m68k__
        /* stock's route 1 (0x40137d7e..0x40137db0), instruction for instruction: mac.l under the frame's MACSR
         * (fractional, set by the audio interrupt), the cell sign-extended, the sum clamped to 0..0x7f00 */
        u32 n = MX_SLOTS;
        __asm__ volatile (
            "1:\tmove.l  (%[e])+,%%d0\n\t"           /* the cell's offset */
            "move.l  (%[e])+,%%d1\n\t"                /* (depth - 0x4000) x 2 */
            "move.l  (%[e])+,%%a1\n\t"                /* the source's offset */
            "move.l  (%[lfo],%%a1.l),%%d2\n\t"
            "mac.l   %%d1,%%d2,%%acc0\n\t"
            "movclr.l %%acc0,%%d2\n\t"
            "mvs.w   (%[row],%%d0.l),%%d1\n\t"
            "add.l   %%d1,%%d2\n\t"
            "bpl.s   2f\n\t"
            "clr.l   %%d2\n\t"
            "bra.s   3f\n"
            "2:\tcmp.l   %[top],%%d2\n\t"
            "ble.s   3f\n\t"
            "move.l  %[top],%%d2\n"
            "3:\tmove.w  %%d2,(%[row],%%d0.l)\n\t"
            "subq.l  #1,%[n]\n\t"
            "bne.s   1b"
            : [e] "+a"(e), [n] "+d"(n)
            : [lfo] "a"(lfo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "a1", "cc", "memory");
#else
        for (u32 k = 0; k < MX_SLOTS; k++, e++) {
            volatile s16 *cell = (volatile s16 *)(row + e->cell);
            s32 x = (s32)*cell + mx_mac(e->d1, *(volatile s32 *)(lfo + e->src));
            *cell = (s16)(x < 0 ? 0 : x > MX_TOP ? MX_TOP : x);
        }
#endif
    }
}
