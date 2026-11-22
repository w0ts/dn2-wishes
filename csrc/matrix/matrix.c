/* The modulation matrix: more routes than stock's one per LFO, and two envelopes (the User, 2026-11-11: up to 16 LFO
 * routes a track, LFO1-3 sharing them, stock's route 1 of each LFO counting; ENV1 and ENV2 with four destinations
 * each; docs/matrix.md). OS 1.12.
 *
 * A sound's routes are a field of its wishes record (csrc/wishes, tag WT_MX_ROUTES): four bytes each, the source
 * (0 LFO1, 1 LFO2, 2 LFO3, 3 ENV1, 4 ENV2), the destination slot (25..100, a sound parameter's cell of the voice row),
 * and the depth in stock DEP's units (0..0x7ffe, 0x4000 none). A source byte with MX_MUTED (0x80) is a muted route (the
 * routes popup's NO, the User 2026-11-17): laid out in its place as at depth 0x4000 (d1 0: the cells as at depth 0,
 * the same cost; not an idle skip), its depth kept in the record. A build before the flag skips it (a source >= 5). ENV2's settings are another field (WT_MX_ENV:
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
_Static_assert(MX_SLOTS % 2 == 1, "the frame's route loop: one route, then pairs");
#define MX_SRCS 5                       /* LFO1, LFO2, LFO3, ENV1, ENV2 */
#define MX_E2_DEST 0xE0u                /* (2026-11-18, the User) ENV2's knobs as destinations: 0xE0 ATK, 0xE1 HOLD, 0xE2 DEC,
                                         * 0xE3 SUS, 0xE4 REL; (2026-11-20, the User) 0xE5 MODE, 0xE6 RSET, 0xE7 H (its
                                         * attenuverter): 0xE0 + the knob's K_ index. A route of the record only (never an
                                         * LFO's first route: DEST is a voice-row slot for stock); a build before skips them
                                         * (a slot over 100); ENV2 into its own knobs is refused (it would land after
                                         * ENV2 stepped). MODE and RSET are switches, read as ENV1 reads the AMP cells'
                                         * (the high byte not 0: ADSR, RSET on); RSET is read at a note-on only */
#define MX_E2_N 8u                      /* ATK HOLD DEC SUS REL MODE RSET H: ENV2's knob row, a cell each */
#define MX_INS_DEST 0xC0u               /* (2026-11-20, the User: scratch/mod-live-design.md C) the track's inserts' knobs as
                                         * destinations: 0xC0 + 7 j + i, slot j's K1..K6 (i 0..5) and MIX (i 6); a route
                                         * of the record only (never an LFO's first route); a build before skips them (a
                                         * slot over 100, not ENV2's). Each voice's cells sit in its ENV2 knob row after
                                         * ENV2's (MX_INS_CELL..): the track's SET copied in each frame (csrc/inserts
                                         * ins_cell), the routes added; mx_eval works out the offset of each track's
                                         * last-played voice for the group the inserts pack next (ins_moff) */
#define MX_INS_N 14u
#define MX_INS_CELL 8u
_Static_assert(MX_INS_DEST + MX_INS_N <= MX_E2_DEST && MX_INS_DEST > 100u, "the inserts' codes: above the voice row's slots, "
               "below ENV2's");
_Static_assert(MX_INS_CELL >= MX_E2_N && MX_INS_CELL + MX_INS_N <= 101u, "the inserts' cells after ENV2's in the knob row");
#define MX_MUTED 0x80u                  /* a source byte's flag: the route muted (adds 0, costs the same) */
#define MX_FIRST 0x40u                  /* with MX_MUTED: not a route but the mark "LFO l's first route (its DEST and DEP)
                                         * muted" (the DEST popup's NO, the User 2026-11-18); the slot and depth bytes
                                         * hold DEST and DEP as they were (never read). A build before it skips the
                                         * entry (a source >= 5), and plays DEST as stock does */
#define MX_TOP 0x7F00                   /* the evaluator's clamp (0x40137da2) */
#define MX_DEP_TOP 0x7FFE              /* DEP's top (records 83, 93, 103): a route's depth, as stock's */
#define MX_NONE 0x4000u                 /* a depth that adds nothing */
#define MX_MAGIC (0x4D580000u | (u32)sizeof(struct mx_state))   /* 'MX' and the state's size: MX_RAM is not cleared at
                                         * power-on and outlives a flash, so a build whose layout differs lays it out anew */
#define MX_PASS 1                       /* (2026-11-19) a first route's word for "DEP is its depth": lfo_fast then runs
                                         * stock's route 1 itself (a -2 x depth word is even, never 1) */
#define MX_HNONE 1                      /* e2_hm: no H lock (a cell is even, never 1) */
#define ENV_FULL 0x7FFFFFFF
#define ENV_REST 0x100                  /* a fall this close to 0 is over */
#define HOLD_GATE 0xFFFFFFFFu           /* HOLD 127: until the note-off */
enum { E_REST, E_ATK, E_HOLD, E_DEC, E_REL, E_FALL };   /* E_FALL: AHD's decay to 0 */
enum { K_ATK, K_HOLD, K_DEC, K_SUS, K_REL, K_MODE, K_RSET, K_H, K_N = 8 };   /* K_H: the knob row's 8th cell only */

/* ENV_W: the s32 words of a voice's row in env_out, the LFO state's stride, so that the routes' one source offset
 * (src_of: env_out's distance from voice 0's LFO1 output) reaches each voice's own levels from LFO_OUT(v): stock's
 * 120 B (30 words), lfo4's 160 B (40 words) with DN2_LFO4. (2026-11-16: env_out kept stock's 30 words under lfo4,
 * so voice v's ENV1/ENV2 routes read env_out at 160 v bytes, not voice v's levels: the gate's matrix step.) */
#ifdef MX_HOST
#ifndef MX_HOST_LFO_W
#define MX_HOST_LFO_W 30u                /* test/test_matrix_c.py: stock's stride, or lfo4's with -DMX_HOST_LFO_W=40 */
#endif
#define ENV_W MX_HOST_LFO_W
#define LFO_N 3u
#else
#define ENV_W (LFO_STRIDE / 4u)
#define LFO_N (LFO_STRIDE / 40u)        /* the LFOs lfo_fast runs a voice: 3, 4 with lfo4 */
_Static_assert(LFO_STRIDE % 4u == 0u, "the LFO state's stride: whole s32 words");
#endif

#define W_OUT(l) (2u + 10u * (l))      /* (2026-11-19) env_out's row: LFO l's output x DEP, negated (lfo_fast) */
#define W_X1(l) (3u + 10u * (l))       /* ... and its first route's -2 x (depth - 0x4000) (mx_eval) */

#ifndef MX_HOST
#define OUT_B 0x800068E4u               /* the evaluator's first argument: row v's slot s at OUT_B + 34 + 202 v + 2 s */
#define VSOUND ((volatile u32 *)0x800052A8u)    /* the sound voice v plays */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define LFO_OUT(v) ((volatile u8 *)(LFO_LIVE + 4u + LFO_STRIDE * (u32)(v)))   /* LFO l at + 40 l: state + 84 */
/* (LFO_LIVE, LFO_STRIDE: stock's live LFO state, 120 B a voice; lfo4's, 160 B a voice, with DN2_LFO4: cpage) */
#endif

#ifndef DN2_ROUTE8
struct mx_e {
    s32 cell;                           /* the cell's byte offset from the row's slot 0, or the scratch row's */
    s32 d1;                             /* (depth - 0x4000) x 2, as stock's route 1 takes DEP */
    s32 src;                            /* the source's byte offset from the row's LFO1 output */
};
#define E_D1(e) ((e)->d1)
#define E_SET(e, c, d, s) ((e)->cell = (c), (e)->d1 = (d), (e)->src = (s))
#else
/* (2026-11-21, the User's A/B: DN2_ROUTE8, off by default) a route in 8 bytes, the same values: a table 220 B in place
 * of 312 (14 cache lines in place of 20 a voice, every frame read from the DDR). d1 is always even and in
 * -0x7ffc..+0x8000 (dep 0 on an LFO: +0x8000, one past s16), so its half is kept (-0x3ffe..+0x4000) and the frame
 * doubles it (add.l: exact); the source is the offset from the voice's own env_out row (0..92: every source is a
 * word of that row, lfo + src_of == eo + the same word's offset, the same address) */
struct mx_e {
    s32 cell;                           /* as above */
    s16 h;                              /* d1 / 2 */
    s16 src;                            /* the source's byte offset from the voice's env_out row */
};
#define E_D1(e) (2 * (s32)(e)->h)
#define E_SET(e, c, d, s) ((e)->cell = (c), (e)->h = (s16)((d) / 2), (e)->src = (s16)(s))
#endif
struct mx_env {
    s32 level;                          /* 1.31, 0..full scale */
    u32 hold;                           /* samples of HOLD left (HOLD_GATE: until the note-off) */
    u8 stage, on, off, pad;             /* on, off: a note-on / note-off since the last frame */
};
struct mx_tab {
    struct mx_e e[MX_SLOTS];
    u8 env2[K_N - 1];                   /* ENV2's knobs (the record's, else stock's defaults) */
    u8 mute1;                           /* bit l: LFO l's first route muted (the record's MX_FIRST mark; mx_dmask) */
    u16 e2w[MX_E2_N];                   /* (2026-11-18) ENV2's ATK..REL as cells (knob << 8): the frame copies them into
                                         * each voice's knob row (a word a knob, no shifts); (2026-11-20) MODE, RSET (0 or
                                         * 0x100) and H (the knob, 0..127 = -64..+63, << 8) too: 16 bytes, nx1 on 4 */
    s32 nx1[3];                         /* (2026-11-19) each LFO's first route, -2 x (its own depth - 0x4000), the word
                                         * the frame gives each voice of this table (MX_PASS: DEP is the depth, stock's
                                         * route 1: a sound not converted, a sound lock, before the load's first pass) */
} __attribute__((aligned(4)));          /* (2026-11-18) the m68k ABI aligns an s32 at 2: the tables sat at +654, every
                                         * route's longs and env_out (+10026, the ENV routes' source) misaligned, two
                                         * bus accesses each on the ColdFire; now all of them on 4 */
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
    s32 e2_hm[16];                      /* (2026-11-19) each voice's ENV2 H lock from its last trig; (2026-11-20) as its
                                         * cell (the knob << 8: H is routable, its scale taken after the routes), MX_HNONE none */
    u16 e2_locked;                      /* bit v: voice v's last trig held an ENV2 lock (only those are merged) */
    struct mx_tab tab[16][2];
    struct mx_tab none;                 /* every route unused, the envelopes still */
    s32 env_out[16 * ENV_W];            /* each voice's ENV1, ENV2 levels at [ENV_W v], [ENV_W v + 1]: a row's
                                         * stride is the LFOs' (LFO_STRIDE), so one offset fits every row */
    u16 scratch[16 * 101];              /* where an unused route adds 0: a row's stride, so one offset fits every row */
    u16 e2row[16 * 101];                /* (2026-11-18) each voice's ENV2 knobs ATK..REL as cells (0..0x7f00, the knob in the
                                         * high byte): written from the record (or the trig's locks) every frame, the routes
                                         * into ENV2 added, then ENV2 steps from them. A row's stride, as the scratch row.
                                         * (2026-11-20) cells MX_INS_CELL..: the voice's track's inserts (MX_INS_DEST) */
    u16 iroute[16];                     /* (2026-11-20) track t's routes into its inserts' knobs: bit i, knob i (any source,
                                         * muted too: csrc/inserts ins_keep reads MIX's) */
};
_Static_assert(__builtin_offsetof(struct mx_state, tab) % 4u == 0 && __builtin_offsetof(struct mx_state, env_out) % 4u == 0,
               "the route tables and the envelopes' levels long-aligned");
#ifdef MX_HOST                                                          /* test/test_matrix_c.py */
extern struct mx_state mx_host_state;
extern u16 mx_host_rows[];
extern u32 mx_host_kit, mx_host_vsound[16];
extern s32 mx_host_lfo[16 * ENV_W];
#define MX (&mx_host_state)
#define OUT_B ((mx_addr)mx_host_rows)
#define VSOUND mx_host_vsound
#define LFO_OUT(v) ((volatile u8 *)(mx_host_lfo + ENV_W * (u32)(v)))
#else
#define MX ((struct mx_state *)MX_RAM)
_Static_assert(sizeof(struct mx_state) <= MX_BYTES, "the matrix's tables fit MX_RAM");
#endif

u32 mx_compiles D_ = 0;

/* the tracks' first-route masks, LFO by LFO ([l][t]: LFO1's 16, LFO2's, LFO3's), then the sound each track's masks are
 * for ([3][t]): all ones, or 0 where track t's record marks LFO l's first route muted (MX_FIRST) AND the sound's DEST is
 * still the one the mark names (the mark belongs to the route it muted: a DEST moved from outside, by CC, Overbridge or
 * the plugin, plays; put back, it is muted again). MOD SETUP's pass ANDs each voice row's DEST cells, after its sources,
 * with the voice's track's masks (hooks.S mods_fast) when the voice plays that track's sound (a sound-locked voice is
 * not muted: the mark is the track's sound's): a muted first route is DEST none for the frame, its DEST and DEP kept
 * in the sound. The code's own data: all ones (nothing muted) from the load on, before any UI pass */
#define ONES 0xFFFFFFFFu
#define ONES16 ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES, ONES
u32 mx_dmask[4][16] D_ = {{ONES16}, {ONES16}, {ONES16}, {0}};
static u8 mx_mslot[3][16] D_;                           /* the slot each mark names (0: no mark) */
static u32 mx_nmarks D_ = 0;                            /* marks laid out: the UI pass looks at their DESTs */
static u32 mx_laid D_ = 0;                              /* the masks laid out since the code was loaded (MX_RAM's
                                                         * tables can outlive a load: these, the code's data, not) */
#define DEST_SLOT(l) (4u + 8u * (l))                    /* LFO l's DEST cell (the sound's: + 20 + 2 slot, high byte) */

static void mask_marks(u32 kit)                         /* each marked (l, t): muted while the sound's DEST is the mark's */
{
#ifdef MX_HOST
    (void)kit;                                          /* (the host tests have no sounds behind the kit's address) */
#else
    for (u32 l = 0; l < 3u; l++)
        for (u32 t = 0; t < 16u; t++)
            if (mx_mslot[l][t]) {
                const u8 *snd = (const u8 *)(kit + 52u + 1163u * t);
                mx_dmask[l][t] = snd[20u + 2u * DEST_SLOT(l)] == mx_mslot[l][t] ? 0u : 0xFFFFFFFFu;
            }
#endif
}
#undef ONES16
#undef ONES

static s32 none_cell(void)
{
    return (s32)((mx_addr)MX->scratch - (OUT_B + 34u));
}

static s32 e2_cell(u32 k)                               /* ENV2's knob K (K_ATK..K_REL) from a voice row's slot 0 */
{
    return (s32)((mx_addr)&MX->e2row[k] - (OUT_B + 34u));
}

static s32 src_of(u32 src)               /* (2026-11-19) LFO l: its output x DEP, negated (lfo_fast, W_OUT) */
{
#ifdef DN2_ROUTE8
    s32 e = 0;                           /* from the voice's env_out row */
#else
    s32 e = (s32)((mx_addr)MX->env_out - (mx_addr)LFO_OUT(0));
#endif
    return src < 3u ? e + (s32)(4u * W_OUT(src)) : e + (s32)(4u * (src - 3u));
}

/* (2026-11-19, the User: DEP is the LFO's global attenuverter, -64..+63 = -100..+100 %, +63 and above exactly 100 %;
 * docs/matrix.md "DEP: the attenuverter") the scale of a DEP cell A, as hooks.S lfo_fast takes it at stock's DEP read:
 * mx_atab[A >> 7] = -a << 17, a = A - 0x4000 to the table's step (128: exact at every knob step, 0x100), stock's own
 * DEP scale (Q14); 16384 from +63 (0x7f00) up (MOD SETUP's 0x8000.. too), -16383 at the bottom step (M stays in 32
 * bits). So mac(out, M) = floor(-out x a / 2^14): exactly -out at 100 % */
#define MXA_A(i) ((i) == 0 ? -16383 : ((i) << 7) >= 0x7F00 ? 16384 : ((i) << 7) - 0x4000)
#define MXA(i) ((s32)((u32)MXA_A(i) * 0xFFFE0000u))
#define MXA8(i) MXA(i), MXA(i + 1), MXA(i + 2), MXA(i + 3), MXA(i + 4), MXA(i + 5), MXA(i + 6), MXA(i + 7)
#define MXA64(i) MXA8(i), MXA8(i + 8), MXA8(i + 16), MXA8(i + 24), MXA8(i + 32), MXA8(i + 40), MXA8(i + 48), MXA8(i + 56)
const s32 mx_atab[512] = {MXA64(0), MXA64(64), MXA64(128), MXA64(192), MXA64(256), MXA64(320), MXA64(384), MXA64(448)};

s32 mx_m_of(u32 a)
{
    return mx_atab[(a & 0xFFFFu) >> 7];
}

/* our two words beside each LFO's state, in env_out's rows (the LFO state's stride): LFO l at words 2 + 10 l (the
 * scaled output, -out x DEP, written by lfo_fast) and 3 + 10 l (the first route's -2 x (depth - 0x4000), mx_eval);
 * lfo_fast reaches them at mx_kof from its LFO state pointer (%a2: 84(%a2) the output, LFO_OUT(v) + 40 l) */
#ifndef MX_HOST
const u32 mx_kof = (u32)MX_RAM + __builtin_offsetof(struct mx_state, env_out) + 8u + 84u - ((u32)LFO_LIVE + 4u);
#endif
/* route K of TAB. (DN2_ROUTE8) its byte offset hidden from the compiler: an 8-byte stride is otherwise indexed with a
 * scale of 8, a 68020 mode the ColdFire cannot execute (csrc/lfo4/carry.c; scripts/check_coldfire.py) */
static inline struct mx_e *mx_ent(struct mx_tab *tab, u32 k)
{
    u32 off = (u32)sizeof(struct mx_e) * k;
#if defined(__m68k__) && defined(DN2_ROUTE8)
    __asm__("" : "+d"(off));
#endif
    return (struct mx_e *)(void *)((u8 *)tab->e + off);
}

static void lay_none(struct mx_tab *t)
{
    for (u32 k = 0; k < MX_SLOTS; k++)
        E_SET(mx_ent(t, k), none_cell(), 0, 0);
    for (u32 k = 0; k < K_N - 1u; k++)
        t->env2[k] = 0;
    for (u32 k = 0; k < MX_E2_N; k++)
        t->e2w[k] = 0;
    t->e2w[K_H] = 0x7F00;               /* H 100 % (+63), as before: the source exactly -level */
    t->mute1 = 0;
    for (u32 l = 0; l < 3u; l++)
        t->nx1[l] = MX_PASS;            /* a voice on another sound: DEP is its first route's depth, as stock's */
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
        u32 src = val[at] & ~MX_MUTED, slot = val[at + 1], dep = (u32)val[at + 2] << 8 | val[at + 3], k;
        if ((val[at] & (MX_MUTED | MX_FIRST)) == (MX_MUTED | MX_FIRST)) {
            if ((src & ~MX_FIRST) < 3u)         /* LFO l's first route muted: its DEST is not a route of ours */
                tab->mute1 |= (u8)(1u << (src & ~MX_FIRST));
            continue;
        }
        int e2 = slot >= MX_E2_DEST && slot < MX_E2_DEST + MX_E2_N;
        int ins = slot >= MX_INS_DEST && slot < MX_INS_DEST + MX_INS_N;
        if (src >= MX_SRCS || (!e2 && !ins && (slot < 25u || slot > 100u)) || (e2 && src == 4u))
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
        if (val[at] & MX_MUTED)
            dep = MX_NONE;
        s32 d1 = ((s32)dep - (s32)MX_NONE) * 2;
        if (src != 3u)                  /* (2026-11-19) LFO1-3 and ENV2 are heard through their attenuverter: their
                                         * source is -level x DEP (H), so the depth is laid negated: the product is
                                         * stock's route 1's, bit for bit, at 100 % */
            d1 = -d1;
        E_SET(mx_ent(tab, k), e2 ? e2_cell(slot - MX_E2_DEST) : ins ? e2_cell(MX_INS_CELL + slot - MX_INS_DEST) : (s32)(2u * slot),
              d1, src_of(src));
    }
    if (en < (int)K_N)
        env = plain;
    for (u32 k = 0; k < K_N - 1u; k++)
        tab->env2[k] = (u8)(k == K_MODE || k == K_RSET ? env[k] != 0 : env[k] > 127u ? 127u : env[k]);
    for (u32 k = 0; k < K_H; k++)
        tab->e2w[k] = (u16)(tab->env2[k] << 8);
    tab->e2w[K_H] = (u16)((127u - (env[K_N - 1] > 127u ? 127u : env[K_N - 1])) << 8);   /* H: byte 7 is 127 - knob */
    return lfo + envs[0] + envs[1];
}

/* (2026-11-19) each LFO's first route's own depth into TAB: the record's WT_MX_LFO field (F, FN bytes: LFO1-3 each
 * {u16 DEP as saved, u16 the first route's depth}), on a sound that is converted (CONV: its DEP is the attenuverter,
 * atten.c); any other: MX_PASS (DEP is the depth, stock's route 1) */
void mx_lay_first(const u8 *f, int fn, int conv, struct mx_tab *tab)
{
    for (u32 l = 0; l < 3u; l++) {
        if (!conv || fn < (int)(4u * l + 4u)) {
            tab->nx1[l] = MX_PASS;
            continue;
        }
        u32 d = (u32)f[4u * l + 2u] << 8 | f[4u * l + 3u];
        tab->nx1[l] = -2 * ((s32)(d > MX_DEP_TOP ? MX_DEP_TOP : d) - (s32)MX_NONE);
    }
}

/* (2026-11-18) MX_RAM outlives a restart that keeps the RAM (its magic too): the tables, the envelopes and the locks
 * are trusted only once this load's first UI pass has cleared them (code data, 0 after every load): before it the
 * frame adds no route, as at power-on, instead of the last run's routes onto whatever the new load plays */
u32 mx_loaded D_ = 0;                   /* (the host tests and the emulator set it back to 0: a new load) */

static void mx_seed_out(void);

static void mx_zero(void)
{
    mx_loaded = 1;
    s32 keep[16][LFO_N];                /* (2026-11-19) lfo_fast's words (each LFO's output x DEP): LFO4's kept */
    for (u32 v = 0; v < 16u; v++)
        for (u32 l = 0; l < LFO_N; l++)
            keep[v][l] = MX->env_out[ENV_W * v + W_OUT(l)];
    u32 *w = (u32 *)MX;
    for (u32 k = 0; k < sizeof(struct mx_state) / 4; k++)
        w[k] = 0;
    for (u32 v = 0; v < 16u; v++)
        for (u32 l = 0; l < LFO_N; l++)
            MX->env_out[ENV_W * v + W_OUT(l)] = keep[v][l];
    mx_seed_out();
    for (u32 v = 0; v < 16u; v++) {
        for (u32 j = 0; j < 7u; j++)
            MX->e2_lock[v][j] = 0xFF;
        MX->e2_hm[v] = MX_HNONE;
    }
    lay_none(&MX->none);
    for (u32 t = 0; t < 16; t++) {
        lay_none(&MX->tab[t][0]);
        lay_none(&MX->tab[t][1]);
    }
    MX->edits = wish_edits - 1u;        /* the first pass lays everything out */
    MX->magic = MX_MAGIC;
}

int mxa_convert(u32 t, u32 sound);     /* atten.c (the host tests: their own) */
void mxa_moved(void);
#ifndef MX_HOST
u32 mxa_commit(u32 t, u32 sound);

static inline u32 mx_irq_off(void)      /* (csrc/devtest/devtest.c irq_off: the UI task runs in supervisor mode) */
{
    u32 sr;
    __asm__ volatile ("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory");
    return sr;
}

static inline void mx_irq_restore(u32 sr)
{
    __asm__ volatile ("move.w %0, %%sr" : : "d"(sr) : "memory");
}
#endif

static s32 mx_scaled(u32 v, u32 l);

static void mx_x1_words(void);

/* the UI pass: each track's table laid out again when any record changed or the kit moved */
void mx_poll(void)
{
    u8 buf[4 * (MX_SLOTS + 3)], env[8];   /* the routes and the three LFOs' first-route marks */
    u8 first[12];                       /* (2026-11-19) WT_MX_LFO: LFO1-3 {DEP as saved, the first route's depth} */
    u32 kit, edits;

    if (MX->magic != MX_MAGIC || !mx_loaded)
        mx_zero();
#ifndef MX_HOST
    mxa_moved();                        /* (2026-11-19) converted sounds copied out of the kit: stored (atten.c) */
#endif
#ifdef MX_HOST
    kit = mx_host_kit;
#else
    kit = (u32)KIT_POINTER;
#endif
    edits = wish_edits;
    if (kit && mx_nmarks && kit == MX->kit)
        mask_marks(kit);                /* every pass while a mark is laid out: a DEST moved from outside is seen */
    if (!kit || (edits == MX->edits && kit == MX->kit && mx_laid))
        return;
    mx_laid = 1;
    MX->edits = edits;                  /* first: a change meanwhile is seen at the next pass */
    MX->kit = kit;
    for (u32 t = 0; t < 16; t++) {
        u32 sound = kit + 52u + 1163u * t, spare = MX->live[t] ^ 1u;
        int n = wish_get(sound, WT_MX_ROUTES, buf, sizeof buf);
        if (n > (int)sizeof buf)
            n = (int)sizeof buf;        /* (wish_get gives the field's length: never read past what it copied) */
        int en = wish_get(sound, WT_MX_ENV, env, sizeof env);
        mx_lay(buf, n, env, en, &MX->tab[t][spare]);
        int conv = mxa_convert(t, sound);               /* (2026-11-19) atten.c: DEP the attenuverter, its first
                                                         * route's depth in the record (an old sound converted now) */
        mx_lay_first(first, wish_get(sound, WT_MX_LFO, first, sizeof first), conv, &MX->tab[t][spare]);
        for (u32 l = 0; l < 3u; l++) {                  /* the marks' slots (matrix.c MX_FIRST; routes.c) */
            mx_mslot[l][t] = 0;
            mx_dmask[l][t] = 0xFFFFFFFFu;
        }
        u32 ir = 0;
        for (int at = 0; at + 4 <= n; at += 4) {
            if ((buf[at] & (MX_MUTED | MX_FIRST)) == (MX_MUTED | MX_FIRST) && (buf[at] & 3u) < 3u && buf[at + 1])
                mx_mslot[buf[at] & 3u][t] = buf[at + 1];
            else if ((buf[at] & ~MX_MUTED) < MX_SRCS && buf[at + 1] >= MX_INS_DEST && buf[at + 1] < MX_INS_DEST + MX_INS_N)
                ir |= 1u << (buf[at + 1] - MX_INS_DEST);
        }
        MX->iroute[t] = (u16)ir;
#ifndef MX_HOST
        {
            extern void mxs_lay(u32 t, u32 sound);      /* (2026-11-21) MOD SETUP's muted entries (setup.c) */
            mxs_lay(t, sound);
        }
#endif
        mx_dmask[3][t] = sound;
#ifdef MX_HOST
        MX->live[t] = spare;            /* the frame takes the new table from its next row */
        MX->sound[t] = sound;
#else
        /* (2026-11-21) the new table and a conversion staged for its sound (atten.c mxa_commit: DEP the attenuverter,
         * the voices' rows settled on it) go live in one step, every interrupt masked, under the table's lock: no
         * frame sees the converted DEP with stock's route 1 or the new first-route depth with the old DEP. The voices
         * playing the sound get their first routes' words and, for each LFO whose DEP moved, the scaled output as
         * lfo_fast works it out at the LFO's turn (a held half-rate output would keep the old DEP's scale for a frame).
         * The lock held elsewhere (a copy in another task): this track waits for the next pass, as it was */
        if (!wish_take()) {
            mx_laid = 0;                /* every track laid out again at the next pass */
            continue;
        }
        u32 sr = mx_irq_off();
        u32 moved = conv ? mxa_commit(t, sound) : 0;
        if (moved == 0xFFFFFFFFu) {     /* (atten.c MXA_FAIL) not converted after all: DEP is still the depth */
            moved = 0;
            for (u32 l = 0; l < 3u; l++)
                MX->tab[t][spare].nx1[l] = MX_PASS;
            mx_laid = 0;
        }
        MX->live[t] = spare;            /* the frame takes the new table from its next row */
        MX->sound[t] = sound;
        const struct mx_tab *nt = &MX->tab[t][spare];
        for (u32 v = 0; v < 16u; v++)
            if (VSOUND[v] == sound)
                for (u32 l = 0; l < 3u; l++) {
                    MX->env_out[ENV_W * v + W_X1(l)] = nt->nx1[l];
                    if (moved & (1u << l))
                        MX->env_out[ENV_W * v + W_OUT(l)] = mx_scaled(v, l);
                }
        mx_irq_restore(sr);
        wish_give();
#endif
    }
    mx_nmarks = 0;
    for (u32 l = 0; l < 3u; l++)
        for (u32 t = 0; t < 16u; t++)
            mx_nmarks += mx_mslot[l][t] != 0;
    mask_marks(kit);
    MX->compiles++;
    mx_compiles++;
    mx_x1_words();                      /* (2026-11-19) the first routes' words now, as mx_eval writes them each frame */
}

/* the lock applier's trig on voice V (csrc/slides sl_apply): its ENV2 locks (ATK DEC SUS REL MODE RSET H HOLD, slides'
 * kinds 3..10, 0xffff none; E2 0: none), which ENV2 takes in place of the record's knobs until the voice's next trig */
void mx_env2_locks(u32 v, const u16 *e2)
{
    static const u8 KNOB[6] = {K_ATK, K_DEC, K_SUS, K_REL, K_MODE, K_RSET};
    if (MX->magic != MX_MAGIC || !mx_loaded || v > 15u)
        return;
    u32 any = 0;
    for (u32 j = 0; j < 6u; j++) {
        u8 x = (u8)(!e2 || e2[j] > 127u ? 0xFFu : e2[j]);
        MX->e2_lock[v][KNOB[j]] = x;
        any |= x != 0xFFu;
    }
    u32 h = e2 ? e2[6] : 0xFFFFu;       /* (2026-11-19) H, ENV2's attenuverter: the knob 0..127 (slides' 7th kind) */
    MX->e2_hm[v] = h > 127u ? MX_HNONE : (s32)(h << 8);
    any |= h <= 127u;
    u8 hold = (u8)(!e2 || e2[7] > 127u ? 0xFFu : e2[7]);   /* (2026-11-20, the User) HOLD, lockable: slides' 8th kind */
    MX->e2_lock[v][K_HOLD] = hold;
    any |= hold != 0xFFu;
    MX->e2_locked = (u16)(any ? MX->e2_locked | 1u << v : MX->e2_locked & ~(1u << v));
}

/* a note-on on voice V (the frame, csrc/hold hold_len): its envelopes start at the frame's step */
void mx_env_on(u32 v)
{
    if (MX->magic != MX_MAGIC || !mx_loaded || v > 15u)
        return;
    MX->env[v][0].on = MX->env[v][1].on = 1;
    MX->env[v][0].off = MX->env[v][1].off = 0;
    MX->ons++;
}

/* the frame's note-off word (bit v: voice v's note ends; csrc/hold hold_final): heard at the frame's step */
void mx_env_off(u32 bits)
{
    if (MX->magic != MX_MAGIC || !mx_loaded || !(bits & 0xFFFFu))
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

/* (2026-11-19) this load's first UI pass: each voice's LFO1-3 word (its output x DEP, negated) worked out now, as
 * lfo_fast does at the LFO's step, from its output and its row's DEP cell: a held output (half-rate LFOs, not its
 * voice's turn) is heard at its DEP from the first frame, not at the last run's */
static s32 mx_scaled(u32 v, u32 l)      /* voice V's LFO L: its output x its row's DEP cell, negated (lfo_fast's) */
{
    s32 out = *(volatile s32 *)(LFO_OUT(v) + 40u * l);
    u32 dep = ((volatile u16 *)(OUT_B + 34u + 202u * v))[8u + 8u * l];
    return mx_mac(out, mx_m_of(dep));
}

static void mx_seed_out(void)
{
    for (u32 v = 0; v < 16u; v++)
        for (u32 l = 0; l < 3u; l++)
            MX->env_out[ENV_W * v + W_OUT(l)] = mx_scaled(v, l);
}

/* D after N samples of a geometric fall at R a sample (the rest of the block after the attack ends inside it) */
static s32 fall_samples(s32 d, s32 r, u32 n)
{
    for (; n >= 4u; n -= 4u) {                          /* four samples a pass (2026-11-17, the worst frame: every
                                                         * voice's attack ending at once): the same MACs in order */
        d = mx_mac(d, r);
        d = mx_mac(d, r);
        d = mx_mac(d, r);
        d = mx_mac(d, r);
    }
    while (n--)
        d = mx_mac(d, r);
    return d;
}

/* one frame of one envelope, its knobs K (0..127; MODE, RSET 0 / 1); -> its level. (2026-11-18) inlined into
 * mx_eval's voice loop, once for each envelope: the same steps, no call */
/* (2026-11-18) the knobs ATK HOLD DEC SUS REL read where they are, as the high bytes of five consecutive cells (ENV1:
 * the voice row's 81..85, clamped to 127 as before; ENV2: its knob row), each when its stage needs it; MODE and RSET
 * given (0 / 1). No copy of the knobs into an array (the stack) */
#ifdef __m68k__
#define ENV_HI(p, j) (((const u8 *)(p))[2u * (j)])                 /* a cell's high byte: big-endian (no write meets
                                                                     * them while an envelope steps) */
#else
#define ENV_HI(p, j) ((u32)(((const u16 *)(p))[j] >> 8))
#endif
#define EK(j) (clamp ? (ENV_HI(kc, j) > 127u ? 127u : (u32)ENV_HI(kc, j)) : (u32)ENV_HI(kc, j))
static inline __attribute__((always_inline)) s32 env_step(struct mx_env *e, const void *kc, const u32 clamp, u32 mode,
                                                          u32 rset)
{
    s32 x = e->level, s = (s32)ENV_ATK_S[EK(K_ATK)];
    s32 inc = s >= ENV_FULL / 32 ? ENV_FULL : s << 5;  /* a block's step (an attack inside one block: full scale) */
    int ahd = !mode;

    if (e->on) {                                        /* RSET: from 0, half a sample's step in; else on from the
                                                         * level reached (0 at rest), as the DSP does */
        e->on = 0;
        if (rset)
            x = s >> 1;
        e->stage = E_ATK;
    }
    if (e->off) {
        e->off = 0;
        /* (2026-11-20) E_DEC under AHD: only when MODE moved from ADSR during the note (a route or a lock into MODE);
         * the note-off then falls as AHD's would, instead of holding SUS until the next note (not measured on the DSP) */
        if (ahd ? (e->stage == E_ATK || e->stage == E_DEC || (e->stage == E_HOLD && ENV_HOLD[EK(K_HOLD)] == HOLD_GATE))
                : e->stage != E_REST)
            e->stage = ahd ? E_FALL : E_REL;
    }
    switch (e->stage) {
    case E_ATK:
        if (x >= ENV_FULL - inc) {                      /* full scale inside this block: the samples after it go
                                                         * on into the next stage, as the DSP's do */
            u32 used = s == ENV_FULL ? 0u : ((u32)(ENV_FULL - x) + (u32)s - 1u) / (u32)s;   /* ATK 0: none */
            u32 rest = used < 32u ? 32u - used : 0u;
            s32 sus = (s32)(EK(K_SUS) * (ENV_FULL / 127u)), r = (s32)ENV_DEC_S[EK(K_DEC)];
            x = ENV_FULL;
            if (ahd) {                                  /* AHD: the hold counts from that sample (e->hold: the samples
                                                         * held so far, as the DSP's own counter; scripts/measure_amp_hold.py) */
                u32 h = ENV_HOLD[EK(K_HOLD)];
                e->hold = rest;
                e->stage = E_HOLD;
                if (h != HOLD_GATE && rest > h) {
                    x = fall_samples(x, r, rest - h);
                    e->hold = 0;
                    e->stage = E_FALL;
                }
            } else {
                e->stage = E_DEC;
                x = sus + fall_samples(x - sus, r, rest);
            }
        } else
            x += inc;
        break;
    case E_HOLD: {                                      /* (2026-11-18) the samples held so far against HOLD's length NOW,
                                                         * as the DSP compares its counter every sample: a HOLD moved by a
                                                         * route or a lock during the hold is heard at once */
        u32 h = ENV_HOLD[EK(K_HOLD)];
        if (h == HOLD_GATE || e->hold + 32u <= h) {
            if (e->hold < 0xFFFFFF00u)
                e->hold += 32u;
        } else {                                        /* it runs out inside this block (or has already): the rest falls */
            x = fall_samples(x, (s32)ENV_DEC_S[EK(K_DEC)], e->hold >= h ? 32u : e->hold + 32u - h);
            e->hold = 0;
            e->stage = E_FALL;
        }
        break;
    }
    case E_DEC: {
        s32 sus = (s32)(EK(K_SUS) * (ENV_FULL / 127u));
        x = sus + mx_mac(x - sus, (s32)ENV_DEC[EK(K_DEC)]);
        break;
    }
    case E_REL:
    case E_FALL:
        x = mx_mac(x, (s32)(e->stage == E_REL ? ENV_REL[EK(K_REL)] : ENV_DEC[EK(K_DEC)]));
        if (x < ENV_REST) {
            x = 0;
            e->stage = E_REST;
        }
        break;
    case E_REST:                                        /* (listed: the six stages one table jump) */
    default:
        x = 0;
    }
    e->level = x;
    return x;
}
#undef EK

/* a source's value on voice V now (the routes popup's moving bar): LFO1-3's output, ENV1's and ENV2's level, 1.31 */
int mx_route_level(u32 v, u32 src)
{
    if (MX->magic != MX_MAGIC || !mx_loaded || v > 15u || src > 4u)
        return 0;
    if (src == 3u)
        return MX->env_out[ENV_W * v];
    s32 x = MX->env_out[ENV_W * v + (src < 3u ? W_OUT(src) : 1u)];   /* (2026-11-19) as heard: x DEP (H), negated */
    return x == (s32)0x80000000u ? 0x7FFFFFFF : -x;
}

/* (2026-11-20) csrc/inserts' UI pass: track T's routes into its inserts' knobs (bit i, MX_INS_DEST + i), 0 none */
u32 mx_ins_routes(u32 t)
{
    if (MX->magic != MX_MAGIC || !mx_loaded || t > 15u)
        return 0;
    return MX->iroute[t];
}

/* (2026-11-20) the inserts' group packed next (csrc/inserts ins_period): for each of its two tracks, the offset the routes
 * put on the knobs' SET this frame, on the voice the track last played (slides' sl_lastv) while it still plays the
 * track's sound; else held. The cells were SET (ins_cell[t]) when the voice loop began, the same row read here */
extern u16 ins_cell[17][MX_INS_N];
extern s16 ins_moff[16][MX_INS_N];
extern signed char sl_lastv[16];
u32 ins_next_group(void);
static inline __attribute__((always_inline)) void mx_ins_group(const struct mx_state *S, u32 g)
{
    for (u32 t = 2u * g; t < 2u * g + 2u; t++) {
        s32 v = sl_lastv[t];
        if (v < 0 || v > 15 || VSOUND[v] != S->sound[t])
            continue;                           /* no voice yet, or it left the track: the last offsets held */
        const u16 *e = S->e2row + 101u * (u32)v + MX_INS_CELL, *c = ins_cell[t];
        s16 *o = ins_moff[t];
        for (u32 i = 0; i < MX_INS_N; i++)
            o[i] = (s16)((s32)e[i] - (s32)c[i]);
    }
}

/* (2026-11-21) voice V's insert cells (MX_INS_CELL..) <- its track's SET (ins_cell[t], row 16: a voice on no track's
 * sound), before the voice loop (whose routes into them then add to it): V one of the two voices mx_ins_group reads
 * this frame; none (no voice yet: V < 0) nothing */
static inline __attribute__((always_inline)) void mx_ins_cells(struct mx_state *S, s32 v, u32 kit52)
{
    if (v < 0 || v > 15)
        return;
    u32 off = VSOUND[v] - kit52;
    u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;
    typedef u32 u32a2 __attribute__((aligned(2), may_alias));
    const u32a2 *ic = (const u32a2 *)(const void *)ins_cell[t];
    u32a2 *d = (u32a2 *)(void *)(S->e2row + 101u * (u32)v + MX_INS_CELL);
    d[0] = ic[0];
    d[1] = ic[1];
    d[2] = ic[2];
    d[3] = ic[3];
    d[4] = ic[4];
    d[5] = ic[5];
    d[6] = ic[6];
}

/* the frame, after stock's evaluator: B its first argument (the mirror OUT_B). Every row, both envelopes, every
 * route.
 *
 * (2026-11-18, the User: the same work every frame, faster, bit-exact) per voice: the track's table found with one
 * multiply (284 x (2 t + live)), the kit's address read once a frame (mx_poll runs in the UI pass, never inside the
 * frame), ENV1's knobs read as the cells' high bytes, both envelopes stepped inline (no call), and the 23 routes
 * unrolled: each pair's two table rows (cell, d1, source: 24 bytes) in one movem, each route and its clamp as
 * before (stock's route 1), the cell read while the MAC runs. */
#ifndef DN2_ROUTE8
#define MX_TAB_B 312u                   /* sizeof(struct mx_tab) */
#define MX_E_B 12u
#define MX_NX1_OFF 300u
#else
#define MX_TAB_B 220u                   /* (DN2_ROUTE8) 23 routes of 8 bytes */
#define MX_E_B 8u
#define MX_NX1_OFF 208u
#endif
_Static_assert(sizeof(struct mx_tab) == MX_TAB_B && sizeof(struct mx_e) == MX_E_B, "mx_eval: the tables' strides");
_Static_assert(__builtin_offsetof(struct mx_tab, nx1) == MX_NX1_OFF, "the first routes' words long-aligned, at +300 "
               "(+208 with DN2_ROUTE8; scripts/emulib/mxlayout.py)");
#ifdef __m68k__
#define MX_HI(row, slot) (((const volatile u8 *)(row))[2u * (slot)])    /* a cell's high byte: big-endian */
/* one route: C its cell's offset, D (depth - 0x4000) x 2, S the source's offset; N a label stem. In order: the
 * source read, the MAC, the cell read (sign-extended), the product, the clamp to 0..0x7f00, the store */
#define MX_ROUTE(C, D, S, N) \
    "move.l  (%[lfo]," S ".l)," S "\n\t" \
    "mac.l   " D "," S ",%%acc0\n\t" \
    "mvs.w   (%[row]," C ".l)," D "\n\t" \
    "movclr.l %%acc0," S "\n\t" \
    "add.l   " D "," S "\n\t" \
    "bpl.s   1" N "f\n\t" \
    "clr.l   " S "\n\t" \
    "bra.s   2" N "f\n" \
    "1" N ":\tcmp.l   %[top]," S "\n\t" \
    "ble.s   2" N "f\n\t" \
    "move.l  %[top]," S "\n" \
    "2" N ":\tmove.w  " S ",(%[row]," C ".l)\n\t"
#define MX_PAIR(OFF, NA, NB) \
    "movem.l " OFF "(%[e]),%%d0-%%d5\n\t" \
    MX_ROUTE("%%d0", "%%d1", "%%d2", NA) MX_ROUTE("%%d3", "%%d4", "%%d5", NB)
_Static_assert(MX_SLOTS == 23, "mx_eval's unrolled routes: one, then 11 pairs");
/* (DN2_ROUTE8) route K's 8 bytes into C (the cell), D (d1: the half, doubled) and S (the source's offset from the
 * voice's env_out row, which the routes then read at %[lfo] = eo): the same three values MX_ROUTE takes */
#define MX_LD8(OC, OH, OS, C, D, S) \
    "move.l  " OC "(%[e])," C "\n\t" \
    "mvs.w   " OH "(%[e])," D "\n\t" \
    "add.l   " D "," D "\n\t" \
    "mvs.w   " OS "(%[e])," S "\n\t"
#define MX_R8(OC, OH, OS, N) MX_LD8(OC, OH, OS, "%%d0", "%%d1", "%%d2") MX_ROUTE("%%d0", "%%d1", "%%d2", N)
#define MX_R8B(OC, OH, OS, N) MX_LD8(OC, OH, OS, "%%d3", "%%d4", "%%d5") MX_ROUTE("%%d3", "%%d4", "%%d5", N)
#else
#define MX_HI(row, slot) (((const volatile u16 *)(row))[slot] >> 8)
#endif

/* (2026-11-18) the routes in three parts, the envelopes stepped between them: the LFO routes (0..14) first, so ENV1
 * reads the AMP cells as the DSP is sent them, a route of the record into ATK HOLD DEC SUS REL MODE RSET included
 * (before, only stock's: an LFO's first route, MOD SETUP; the amp heard the record's routes and the clone did not;
 * scratch/env2-mod.md). Then ENV1's routes (15..18), from this frame's level as before, ENV2's knobs among their
 * destinations; then ENV2 steps from its knob row (the record's or the trig's knobs, the routes into them added);
 * then ENV2's routes (19..22). The same arithmetic in the same table order: every cell and level is as before unless
 * a route goes into the AMP envelope's cells (ENV1 now follows an LFO's) or into ENV2's knobs. An envelope's routes
 * into the AMP cells still come after ENV1 stepped (docs/matrix.md, Known limits) */
static inline __attribute__((always_inline)) void mx_env1(struct mx_env *ev, s32 *eo, const u8 *row)
{
    eo[0] = env_step(ev, row + 2u * 81u, 1u, MX_HI(row, 91) != 0, MX_HI(row, 92) != 0);
}

/* ENV2's knobs on voice V before the routes: the record's, a trig's locks over them -> K2 (K_N) */
static inline __attribute__((always_inline)) const u8 *mx_e2_knobs(const struct mx_state *S, u32 v,
                                                                     const struct mx_tab *tab, u8 *merged)
{
    if (!(S->e2_locked >> v & 1u))
        return tab->env2;
    const u8 *lk = S->e2_lock[v];
    for (u32 j = 0; j < 7u; j++)
        merged[j] = lk[j] != 0xFFu ? lk[j] : tab->env2[j];
    merged[7] = 0;
    return merged;
}

static inline __attribute__((always_inline)) void mx_env2(struct mx_env *ev, s32 *eo, const u16 *e2)
{
    /* 0..127: the routes clamp the cells to 0..0x7f00. (2026-11-19) The routes' source is the level x H, negated
     * (mx_m_of: exactly -level at 100 %); the envelope's own state is not scaled. (2026-11-20) MODE, RSET and H from
     * the knob row, after the routes into them: MODE and RSET as ENV1 reads its cells (the high byte not 0) */
    eo[1] = mx_mac(env_step(ev + 1, e2, 0u, e2[K_MODE] >= 0x100u, e2[K_RSET] >= 0x100u), mx_m_of(e2[K_H]));
}

/* the routes popup's moving line on ENV2's page (csrc/modulation/moving.c): ENV2's knob K (K_ATK..K_REL) on voice V as
 * heard this frame (*HEARD, the cell) and as set (*SET, the record's or the trig's lock, << 8); -> 0 none */
int mx_e2_knob(u32 v, u32 k, int *heard, int *set)
{
    struct mx_state *const S = MX;
    if (S->magic != MX_MAGIC || !mx_loaded || v > 15u || k >= MX_E2_N)
        return 0;
    u32 snd = VSOUND[v], off = snd - (S->kit + 52u);
    u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;
    const struct mx_tab *tab = t < 16u && snd == S->sound[t]
        ? (const struct mx_tab *)(const void *)((const u8 *)S->tab + MX_TAB_B * (2u * t + S->live[t])) : &S->none;
    u8 merged[K_N];
    if (k == K_H)                       /* (2026-11-20) H: the trig's lock (a cell) or the record's */
        *set = (S->e2_locked >> v & 1u) && S->e2_hm[v] != MX_HNONE ? (int)S->e2_hm[v] : (int)tab->e2w[K_H];
    else
        *set = (int)mx_e2_knobs(S, v, tab, merged)[k] << 8;
    *heard = (int)S->e2row[101u * v + k];
    return 1;
}

/* (2026-11-19) the frame's first call after a load (cascade.c mc_zero, before the evaluator): each voice's first-route
 * words to MX_PASS (stock's route 1, DEP its depth), so lfo_fast never reads a word left in MX_RAM by the last run (or
 * power-on's) before mx_eval has written this frame's */
void mx_pass_all(void)
{
    if (MX->magic == MX_MAGIC && mx_loaded)
        return;                         /* this load's UI pass came first: its words (mx_x1_words) */
    for (u32 v = 0; v < 16u; v++)
        for (u32 l = 0; l < LFO_N; l++)
            MX->env_out[ENV_W * v + W_X1(l)] = MX_PASS;
}

/* (2026-11-19) each voice's first-route words from its track's table, as mx_eval writes them every frame (the UI pass,
 * after a layout: the frame before the next mx_eval reads them) */
static void mx_x1_words(void)
{
    struct mx_state *const S = MX;
    for (u32 v = 0; v < 16u; v++) {
        u32 snd = VSOUND[v], off = snd - (S->kit + 52u);
        u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;
        const struct mx_tab *tab = t < 16u && snd == S->sound[t]
            ? (const struct mx_tab *)(const void *)((const u8 *)S->tab + MX_TAB_B * (2u * t + S->live[t])) : &S->none;
        for (u32 l = 0; l < 3u; l++)
            S->env_out[ENV_W * v + W_X1(l)] = tab->nx1[l];
    }
}

void mx_eval(mx_addr b)
{
    struct mx_state *const S = MX;
    if (S->magic != MX_MAGIC || !mx_loaded) {   /* no UI pass yet since this load: no route of ours; each LFO's first
                                                 * route is stock's (DEP its depth: MX_PASS, lfo_fast reads it) */
        for (u32 v = 0; v < 16u; v++)
            for (u32 l = 0; l < LFO_N; l++)
                S->env_out[ENV_W * v + W_X1(l)] = MX_PASS;
        return;
    }
    S->frames++;
    const u32 kit52 = S->kit + 52u;
    u8 *row = (u8 *)(b + 34u);
#ifndef DN2_ROUTE8
    volatile u8 *lfo = LFO_OUT(0);
#define MX_SRCB lfo                                     /* the routes' sources: from the voice's LFO1 output */
#define MX_LFO_STEP , lfo += 4u * ENV_W
#else
#define MX_SRCB eo                                      /* (DN2_ROUTE8) from the voice's env_out row */
#define MX_LFO_STEP
#endif
    u16 *e2 = S->e2row;
    struct mx_env *ev = S->env[0];                      /* each voice's two envelopes, its levels: pointers stepped */
    s32 *eo = S->env_out;
    /* (2026-11-21, the User's CPU) the inserts' cells are read only by mx_ins_group, on the voice each of its group's
     * two tracks last played (sl_lastv, set by the note path earlier in this same interrupt: unchanged during the
     * frame): only those voices' cells get SET copied in (the same cells, the same offsets; the other voices' insert
     * cells are written by their routes and read by nothing: mx_e2_knob reads ENV2's knobs 0..7 only) */
    const u32 ig = ins_next_group();
    mx_ins_cells(S, sl_lastv[2u * ig], kit52);
    mx_ins_cells(S, sl_lastv[2u * ig + 1u], kit52);
    for (u32 v = 0; v < 16; v++, row += 202u, e2 += 101, ev += 2, eo += ENV_W MX_LFO_STEP) {
        u32 snd = VSOUND[v];
        u32 off = snd - kit52;
        u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;     /* off / 1163, exact for a whole sound 0..15 */
        const struct mx_tab *tab = &S->none;
        if (t < 16u && snd == S->sound[t])
            tab = (const struct mx_tab *)(const void *)((const u8 *)S->tab + MX_TAB_B * (2u * t + S->live[t]));
        eo[W_X1(0)] = tab->nx1[0];                      /* (2026-11-19) each LFO's first route's depth for this voice:
                                                         * lfo_fast reads it next frame (DEP x it) */
        eo[W_X1(1)] = tab->nx1[1];
        eo[W_X1(2)] = tab->nx1[2];
#if LFO_N > 3
        eo[W_X1(3)] = MX_PASS;                          /* LFO4: DEP stays its one route's depth (the User, Q7) */
#endif
        if (!(S->e2_locked >> v & 1u)) {                /* ENV2's knob row: the routes into ENV2 add to it */
            const u16 *w = tab->e2w;
            e2[K_ATK] = w[K_ATK];
            e2[K_HOLD] = w[K_HOLD];
            e2[K_DEC] = w[K_DEC];
            e2[K_SUS] = w[K_SUS];
            e2[K_REL] = w[K_REL];
            e2[K_MODE] = w[K_MODE];                     /* (2026-11-20) MODE, RSET, H: cells too (routable) */
            e2[K_RSET] = w[K_RSET];
            e2[K_H] = w[K_H];
        } else {                                        /* a trig's ENV2 locks over the record's knobs */
            u8 merged[K_N];
            const u8 *k2 = mx_e2_knobs(S, v, tab, merged);
            for (u32 j = 0; j < K_H; j++)
                e2[j] = (u16)(k2[j] << 8);
            e2[K_H] = S->e2_hm[v] != MX_HNONE ? (u16)S->e2_hm[v] : tab->e2w[K_H];
        }
        const struct mx_e *e = tab->e;
#ifdef __m68k__
        /* stock's route 1 (0x40137d7e..0x40137db0) for each route: mac.l under the frame's MACSR (fractional, set by
         * the audio interrupt), the cell sign-extended, the sum clamped to 0..0x7f00; all 23 in table order, ENV1
         * stepped after the LFO routes (0..14), ENV2 after ENV1's (15..18) */
#ifdef DN2_ROUTE8
        /* (DN2_ROUTE8) the same 23 routes in the same order, each loaded from its 8 bytes (MX_LD8), the source read
         * from the voice's env_out row (eo): the same address as lfo + the 12-byte table's source */
        __asm__ volatile (
            MX_R8("0", "4", "6", "00") MX_R8B("8", "12", "14", "01") MX_R8("16", "20", "22", "02")
            MX_R8B("24", "28", "30", "03") MX_R8("32", "36", "38", "04") MX_R8B("40", "44", "46", "05")
            MX_R8("48", "52", "54", "06") MX_R8B("56", "60", "62", "07") MX_R8("64", "68", "70", "08")
            MX_R8B("72", "76", "78", "09") MX_R8("80", "84", "86", "10") MX_R8B("88", "92", "94", "11")
            MX_R8("96", "100", "102", "12") MX_R8B("104", "108", "110", "13") MX_R8("112", "116", "118", "14")
            :
            : [e] "a"(e), [lfo] "a"(eo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
        mx_env1(ev, eo, row);
        __asm__ volatile (
            MX_R8B("120", "124", "126", "15") MX_R8("128", "132", "134", "16") MX_R8B("136", "140", "142", "17")
            MX_R8("144", "148", "150", "18")
            :
            : [e] "a"(e), [lfo] "a"(eo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
        mx_env2(ev, eo, e2);
        __asm__ volatile (
            MX_R8B("152", "156", "158", "19") MX_R8("160", "164", "166", "20") MX_R8B("168", "172", "174", "21")
            MX_R8("176", "180", "182", "22")
            :
            : [e] "a"(e), [lfo] "a"(eo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
#else
        __asm__ volatile (
            "movem.l (%[e]),%%d0-%%d2\n\t"
            MX_ROUTE("%%d0", "%%d1", "%%d2", "00")
            MX_PAIR("12", "01", "02") MX_PAIR("36", "03", "04") MX_PAIR("60", "05", "06")
            MX_PAIR("84", "07", "08") MX_PAIR("108", "09", "10") MX_PAIR("132", "11", "12")
            MX_PAIR("156", "13", "14")
            :
            : [e] "a"(e), [lfo] "a"(lfo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
        mx_env1(ev, eo, row);
        __asm__ volatile (
            MX_PAIR("180", "15", "16") MX_PAIR("204", "17", "18")
            :
            : [e] "a"(e), [lfo] "a"(lfo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
        mx_env2(ev, eo, e2);
        __asm__ volatile (
            MX_PAIR("228", "19", "20") MX_PAIR("252", "21", "22")
            :
            : [e] "a"(e), [lfo] "a"(lfo), [row] "a"(row), [top] "d"((s32)MX_TOP)
            : "d0", "d1", "d2", "d3", "d4", "d5", "cc", "memory");
#endif
#else
        for (u32 k = 0; k < MX_SLOTS; k++, e++) {
            if (k == MX_LFO)
                mx_env1(ev, eo, row);
            if (k == MX_LFO + MX_ENVR)
                mx_env2(ev, eo, e2);
            volatile s16 *cell = (volatile s16 *)(row + e->cell);
            s32 x = (s32)*cell + mx_mac(E_D1(e), *(volatile s32 *)((volatile u8 *)MX_SRCB + e->src));
            *cell = (s16)(x < 0 ? 0 : x > MX_TOP ? MX_TOP : x);
        }
#endif
    }
    mx_ins_group(S, ig);
}

#ifdef DN2_ROUTE_PROBE
/* (2026-11-21, the User: "measure", DN2_ROUTE_PROBE, off by default; ON only in a test build) the cost of reading the
 * route tables from the DDR, for the CPU profile: called from the frame just before mx_eval (hooks.S mod_eval), it
 * finds each voice's table as mx_eval does and reads one long in every 16 bytes of it, and its last long: every cache
 * line the table spans, so mx_eval then finds them in the cache. Its own share of the profile is then the line fills
 * (its instructions are few: 21 reads a voice, 15 with DN2_ROUTE8), and mx_eval's share drops by what they cost it.
 * Writes nothing; the same reads every frame (a voice on no track reads the unused table, as mx_eval does). */
__attribute__((noinline)) void mx_probe(void)
{
    const struct mx_state *const S = MX;
    if (S->magic != MX_MAGIC || !mx_loaded)
        return;                         /* mx_eval reads no table either */
    const u32 kit52 = S->kit + 52u;
    for (u32 v = 0; v < 16u; v++) {
        u32 snd = VSOUND[v], off = snd - kit52;
        u32 t = off < 16u * 1163u ? (off * 3607u) >> 22 : 16u;
        const struct mx_tab *tab = &S->none;
        if (t < 16u && snd == S->sound[t])
            tab = (const struct mx_tab *)(const void *)((const u8 *)S->tab + MX_TAB_B * (2u * t + S->live[t]));
#ifdef __m68k__
        /* one long in every 16 bytes and the last: every line the table spans (tst.l: a read, no write) */
#ifdef DN2_ROUTE8
        __asm__ volatile (
            "tst.l   0(%0)\n\t" "tst.l   16(%0)\n\t" "tst.l   32(%0)\n\t" "tst.l   48(%0)\n\t" "tst.l   64(%0)\n\t" "tst.l   80(%0)\n\t"
            "tst.l   96(%0)\n\t" "tst.l   112(%0)\n\t" "tst.l   128(%0)\n\t" "tst.l   144(%0)\n\t" "tst.l   160(%0)\n\t" "tst.l   176(%0)\n\t"
            "tst.l   192(%0)\n\t" "tst.l   208(%0)\n\t" "tst.l   216(%0)\n\t"
            : : "a"(tab) : "cc");
#else
        __asm__ volatile (
            "tst.l   0(%0)\n\t" "tst.l   16(%0)\n\t" "tst.l   32(%0)\n\t" "tst.l   48(%0)\n\t" "tst.l   64(%0)\n\t" "tst.l   80(%0)\n\t"
            "tst.l   96(%0)\n\t" "tst.l   112(%0)\n\t" "tst.l   128(%0)\n\t" "tst.l   144(%0)\n\t" "tst.l   160(%0)\n\t" "tst.l   176(%0)\n\t"
            "tst.l   192(%0)\n\t" "tst.l   208(%0)\n\t" "tst.l   224(%0)\n\t" "tst.l   240(%0)\n\t" "tst.l   256(%0)\n\t" "tst.l   272(%0)\n\t"
            "tst.l   288(%0)\n\t" "tst.l   304(%0)\n\t" "tst.l   308(%0)\n\t"
            : : "a"(tab) : "cc");
#endif
#else
        const volatile u32 *p = (const volatile u32 *)(const volatile void *)tab;
        for (u32 i = 0; i < MX_TAB_B / 4u; i += 4u)
            (void)p[i];
        (void)p[MX_TAB_B / 4u - 1u];
#endif
    }
}
#endif
