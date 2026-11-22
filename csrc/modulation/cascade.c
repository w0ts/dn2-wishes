/* LFOs modulating the LFOs above them (owner, 2026-11-11: "Feedback is okay for lfo";
 * docs/modulation-more.md). The ColdFire half, OS 1.12.
 *
 * Which destinations a list offers (mod_lfo_mask, reached through hooks.S's mod_mask_hook in
 * place of page.c's wr_lfo_mask at the builder's lookup 0x40039570):
 *
 *   stock's rule is a rank: LFO1's controls carry 0xe00, LFO2's 0x600, LFO3's 0x200, and an LFO
 *   lists a record when (want & ~mask) == 0 with want 0x1e00 (LFO1), 0xe00 (LFO2), 0x600 (LFO3),
 *   0x200 (MOD SETUP). So LFO2 may modulate LFO1, LFO3 LFO1 and LFO2, and no LFO the ones above
 *   it or itself. Here every LFO's list also holds the OTHER LFOs' controls (SPD MULT FADE WAVE
 *   SPH MODE DEP; never DEST, nor the SLEW record): LFO1 gets LFO2's and LFO3's, LFO2 gets
 *   LFO3's. An LFO's own controls stay out (no list route to self-modulation; a sound made
 *   elsewhere that holds one plays as on stock: its write lands after the LFO has read).
 *   MOD SETUP's list (0x200) is stock's already (every LFO control).
 *
 * How it is heard (mod_wb_cell, mod_eval_pre): the evaluator 0x40137a06 walks each of the 16
 * voice rows LFO3, LFO2, LFO1, in that order; each LFO reads its controls from the row of the
 * mirror (OUT 0x800068e4, the smoother's output plus the six sources) and adds its value into
 * its DEST cell, clamped to 0..0x7f00. A lower LFO's write into a higher LFO's control comes
 * after that LFO has read it, and the smoother rewrites every cell from its target the next
 * frame, so on stock such a write would never be heard. The write is therefore sent into a
 * shadow cell of ours (the evaluator's own read-add-clamp-store, only the cell moved: hooks.S
 * mod_wb at 0x40137d7a), started from the mirror's value, and what the lower LFOs added there
 * is added into the mirror at the start of the next frame (mod_eval_pre, before the
 * evaluator), clamped as the evaluator clamps. One frame late (1/1500 s), never more: the
 * shadow starts from the mirror again every frame, so nothing accumulates.
 *
 * Bounded: the shadow and the carry are clamped to 0..0x7f00 like every LFO write, and restart
 * every frame; what carries over frames is each LFO's phase, whose step 2(SPD - 0x4000) x rate >>
 * (11 - MULT) stays under 2^31 with MULT clamped to 0..23 (0x40137b34), and its fade, saturated to
 * 0..0x3fffffff (0x40137ca8). WAVE is clamped by the evaluator, to 0..6 (0..13 with lfowaves, whose waves a
 * cascade into WAVE reaches: scripts/emu_lfowaves.py). The evaluator has no division, and is
 * integer and fractional MAC only (docs/modulation-more.md).
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define OUT ((volatile u16 *)0x800068E4u)               /* the mirror the evaluator reads */
#define ROW(v) (17u + 101u * (u32)(v))                  /* a voice row's slot 0 (word index) */
#define NROWS 16
#define TOP 0x7F00                                      /* the evaluator's clamp (0x40137da2) */

/* in MOD_RAM (dnfw.waverider.pages; RAM above BSS, its contents unknown at power-on) */
struct mc_row {
    u16 used;                   /* the cells a lower LFO wrote this frame (bit b: slot 9 + b) */
    u16 init;                   /* the cells started from the mirror this frame */
    u16 sh[16];                 /* the shadow cells of slots 9..24 (LFO2's and LFO3's controls) */
    u16 base[16];               /* what each started from */
};
struct mc_state {
    u32 magic;
    u32 frames;                 /* frames the pre-pass ran (the checks) */
    u32 carried;                /* cells carried into the mirror (the checks) */
    struct mc_row row[NROWS];
    u32 rows;                   /* the rows with a cell written this frame (bit v) */
};
#define MC ((struct mc_state *)MOD_RAM)
#define MC_MAGIC 0x4D433031u    /* 'MC01' */
/* (2026-11-21) hooks.S lfo_fast's inline mod_wb_cell (DN2_LFO4 off) reaches these by number: keep them in step */
_Static_assert(MOD_RAM == MOD_RAM_A && MC_MAGIC == 0x4D433031u, "hooks.S: MOD_RAM_A, MC_MAGIC");
_Static_assert(__builtin_offsetof(struct mc_state, row) == 12u && sizeof(struct mc_row) == 68u
               && __builtin_offsetof(struct mc_row, init) == 2u && __builtin_offsetof(struct mc_row, sh) == 4u
               && __builtin_offsetof(struct mc_row, base) == 36u
               && __builtin_offsetof(struct mc_state, rows) == 12u + 68u * NROWS, "hooks.S: mc_state's layout");
_Static_assert(sizeof(struct mc_state) <= MOD_CASCADE_BYTES, "the cascade's state fits its part of MOD_RAM");

/* (2026-11-18) MOD_RAM outlives a restart that keeps the RAM: the block is trusted only once this load has cleared it
 * (code data, 0 after every load), so no carry of the last run's frame is added into the first frame's mirror */
u32 mc_loaded __attribute__((section(".data"))) = 0;

void mx_pass_all(void);                 /* csrc/matrix/matrix.c */

static void mc_zero(void)
{
    mc_loaded = 1;
    mx_pass_all();                      /* (2026-11-19) the first frame after a load: every first route stock's until
                                         * mx_eval has written its words */
    u32 *w = (u32 *)MC;
    for (u32 k = 0; k < sizeof(struct mc_state) / 4; k++)
        w[k] = 0;
    MC->magic = MC_MAGIC;
}

#if DN2_LFO_HALFRATE
/* 2026-11-19 (the User: "half rate lfo yes, but half rate env, no, we need fast env"; behind DN2_LFO_HALFRATE, on by
 * default since the User ran it on the DN2, DN2_LFO_HALFRATE=0 turns it off): the LFO evaluator (lfo_fast) steps the LFOs of half the voices a frame, the even
 * voices on one frame and the odd ones on the next: always eight voices' LFOs, whatever plays (constant load, so the
 * worst frame drops as much as the idle one). A voice's LFOs step two frames at its turn (lfo_fast's pre-step, then
 * this frame's step); on the frame between, each LFO writes its DEST from its last output as every frame (the
 * smoother rewrites the cells every frame). The envelopes, the matrix (its LFO routes read the outputs every frame),
 * the smoother, MOD SETUP and everything else every frame. A trig or restore of a voice not of this frame waits for
 * its turn (lh_args): at most a frame (0.67 ms) late. */
#define LD_ __attribute__((section(".data")))
u32 lh_n LD_ = 0;                                       /* frames counted */
u16 lh_selw[16] __attribute__((section(".data"), aligned(4)));  /* voice v this frame: 1 its turn, 0 not, 2 its first */
static u32 lh_trig LD_ = 0, lh_rest LD_ = 0;            /* trig / restore bits waiting for their voice's turn */
static u32 lh_l4[4] LD_ = {~0u, ~0u, ~0u, ~0u}, lh_l5[4] LD_ = {~0u, ~0u, ~0u, ~0u};
static u32 lh_o4[4] LD_, lh_o5[4] LD_;
typedef u32 __attribute__((may_alias, aligned(1))) u32u;

/* the byte lists (a voice's byte, -1 none), four bytes a long: a byte the frame left -1 takes the waiting one; this
 * frame's voices (SB: 0xff bytes) get it and wait no more, the others get -1 and keep it waiting (claude/mod-halfrate) */
static inline void lh_lists(const u32u *f, u32 *l, u32 *o, const u32 *selb)
{
    for (u32 i = 0; i < 4u; i++) {
        u32 x = f[i], neg = ((x & 0x80808080u) >> 7) * 0xFFu;      /* 0xff where the frame's byte is -1 (none) */
        u32 y = (x & ~neg) | (l[i] & neg), sb = selb[i];
        o[i] = (y & sb) | ~sb;
        l[i] = (y & ~sb) | sb;
    }
}

/* the frame's schedule, then the evaluator's arguments A (its seven, hooks.S mod_eval's copies): A[2] the voices'
 * trigs, A[3] their restores, A[4] and A[5] their byte lists */
void lh_args(u32 *a)
{
    static const u32 SEL[2] = {0x5555u, 0xAAAAu};
    static const u32 SELB[2][4] = {{0xFF00FF00u, 0xFF00FF00u, 0xFF00FF00u, 0xFF00FF00u},
                                   {0x00FF00FFu, 0x00FF00FFu, 0x00FF00FFu, 0x00FF00FFu}};
    u32 n = ++lh_n, odd = n & 1u, sel = SEL[odd];
    u32 *w = (u32 *)(void *)lh_selw;                    /* (big-endian: voice 2 i in the high half) */
    u32 turn = n > 1u ? 1u : 2u;                        /* 2: the odd voices' first turn (frame 1): no frame skipped */
    for (u32 i = 0; i < 8u; i++)
        w[i] = odd ? turn : 0x00010000u;
    u32 trig = a[2] | lh_trig, rest = a[3] | lh_rest;
    lh_trig = trig & ~sel;
    lh_rest = rest & ~sel;
    a[2] = trig & sel;
    a[3] = rest & sel;
    lh_lists((const u32u *)a[4], lh_l4, lh_o4, SELB[odd]);
    lh_lists((const u32u *)a[5], lh_l5, lh_o5, SELB[odd]);
    a[4] = (u32)lh_o4;
    a[5] = (u32)lh_o5;
}
#endif

#if DN2_LFO4
typedef short s16;
/* 2026-11-14 (docs/lfo-112-port.md 4.4, the User: "Include"): LFO1..3 into LFO4's controls. lfo4 keeps them per
 * track in its own rows (csrc/lfo4/bridge.c), not in the mirror: a DEST of 101..108 would land in the next voice
 * row. So the evaluator's write into one goes to a shadow cell of ours per voice row (mod_wb_cell), started from the
 * value this voice row read last; at the next frame's start what was added there becomes this row's carry
 * (mod_eval_pre), and lfo4 reads, through its cascade slot (lfo4_cascade), a row of this voice row's own: its
 * track's plus the carry (mod_lfo4_row). One frame late, as LFO1..3's own; the carry restarts every frame. */
#define L4_SLOT0 101u                                   /* csrc/lfo4/slots.h: SPD .. DEP */
#define L4_N 8u
#define L4_DEST 3u                                      /* LFO4's DEST: never a destination */
#define L4_CASCADE ((volatile u32 *)LFO4_LFO4_CASCADE)  /* lfo4's slot: magic, function */
#define L4_MAGIC 0x4C433034u                            /* 'LC04' (bridge.c) */
struct l4_row {
    u16 used, init;                                     /* (carry long-aligned at +36: mod_lfo4_row reads it as longs) */
    u16 sh[L4_N], base[L4_N];
    s16 carry[L4_N];                                    /* this frame's, from last frame's writes */
    u16 own[L4_N];                                      /* the row handed to lfo4 */
    const u16 *last;                                    /* the track row this voice row read last */
};
static struct l4_row l4[NROWS] __attribute__((section(".data")));
_Static_assert(L4_N == 8 && __builtin_offsetof(struct l4_row, carry) % 4 == 0 && __builtin_offsetof(struct l4_row, sh) % 4 == 0
               && __builtin_offsetof(struct l4_row, base) % 4 == 0 && sizeof(struct l4_row) % 4 == 0,
               "l4_frame / mod_lfo4_row: sh, base and carry read as longs");
static u32 l4_rows __attribute__((section(".data"))) = 0;  /* rows written this frame (bit v) */
/* 2026-11-16 (v0.56.2's gate: the cascade cost 2,329 a frame, bound 800): rows whose carry is not all zero (bit v).
 * l4_frame walks only l4_rows | these: a row outside both has used = init = 0 (only l4_wb sets them, with its bit in
 * l4_rows) and an all-zero carry, which the walk would leave as it is */
static u32 l4_carry_rows __attribute__((section(".data"))) = 0;
static u16 l4_sink[L4_N] __attribute__((section(".data")));   /* where a write we do not carry goes */
u32 mod_l4_carried __attribute__((section(".data"))) = 0;  /* the checks read these */
u32 mod_l4_rows_given __attribute__((section(".data"))) = 0;

u32 mod_lfo4_row(u32 v, u32 row)
{
    if (v >= NROWS || !row)
        return row;
    struct l4_row *r = &l4[v];
    r->last = (const u16 *)row;
    /* (2026-11-17, the User: the constant cost, the same work faster) the eight carries tested as four longs, the
     * eight clamps unrolled: the same values (carry is long-aligned in the row: offset 36, the struct holds a pointer) */
    typedef u32 __attribute__((may_alias)) u32a;
    const u32a *c4 = (const u32a *)(const void *)r->carry;
    if (!(c4[0] | c4[1] | c4[2] | c4[3]))
        return row;
    const u16 *in = (const u16 *)row;
    int x;
#define L4_ONE(b) (x = (int)in[b] + r->carry[b], r->own[b] = (u16)(x < 0 ? 0 : x > TOP ? TOP : x))
    L4_ONE(0); L4_ONE(1); L4_ONE(2); L4_ONE(3); L4_ONE(4); L4_ONE(5); L4_ONE(6); L4_ONE(7);
#undef L4_ONE
    mod_l4_rows_given++;
    return (u32)r->own;
}

static u32 l4_wb(u32 row, u32 dest)
{
    struct l4_row *r = &l4[row];
    u32 b = dest - L4_SLOT0;
    u16 bit = (u16)(1u << b);
    if (!(r->init & bit)) {
        r->sh[b] = r->base[b] = r->last ? r->last[b] : 0x4000u;
        r->init |= bit;
    }
    r->used |= bit;
    l4_rows |= 1u << row;
    return (u32)r->sh - 2u * L4_SLOT0;                  /* + 2 x DEST: sh[DEST - 101] */
}

static void l4_frame(void)
{
    L4_CASCADE[1] = (u32)mod_lfo4_row;                  /* (each frame: lfo4's BSS may be zeroed again) */
    L4_CASCADE[0] = L4_MAGIC;
    u32 rows = l4_rows;
    l4_rows = 0;
    l4_carry_rows = 0;
    /* (2026-11-17, the User: the same work every frame, whatever is routed) all 16 rows, every frame: a row nobody wrote
     * has used = init = 0 and an all-zero carry (only l4_wb sets them, with its bit in l4_rows), and walking it leaves
     * it so, the state as af466dc5's walk of the written rows left it. Branch-free and unrolled: each carry is
     * sh - base masked by its used bit and the row's written bit; the any-test four longs */
    /* two cells a long (sh, base and carry are long-aligned: +4, +20, +36): sh - base in each 16-bit lane, the lanes'
     * borrows kept apart, ((x | H) - (y & ~H)) ^ ((x ^ ~y) & H), the same as (s16)(sh - base) cell by cell; then
     * masked by the pair's two used bits (bit b: cell b, the first cell the long's high half) */
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    static const u32 PAIR[4] = {0u, 0xFFFF0000u, 0x0000FFFFu, 0xFFFFFFFFu};
#else
    static const u32 PAIR[4] = {0u, 0x0000FFFFu, 0xFFFF0000u, 0xFFFFFFFFu};
#endif
#ifdef __m68k__
    /* (2026-11-18, the User: the same work, faster, bit-exact) the same walk by hand, one row a pass: the row's sh in
     * four registers (one movem), the four carries stored with one movem; d = s ^ (c & H) ^ H, where s = (x | H) -
     * (y & ~H) and c = x ^ y (the C below: (x ^ ~y) & H = (c & H) ^ H); the mask's bit for row v from the row word
     * shifted out (lsr, subx); the row's any-bit from a table of 1 << v */
    static const u32 BIT[NROWS] = {1u, 2u, 4u, 8u, 16u, 32u, 64u, 128u, 256u, 512u, 1024u, 2048u, 4096u, 8192u,
                                   16384u, 32768u};
    _Static_assert(__builtin_offsetof(struct l4_row, used) == 0 && __builtin_offsetof(struct l4_row, init) == 2
                   && __builtin_offsetof(struct l4_row, sh) == 4 && __builtin_offsetof(struct l4_row, base) == 20
                   && __builtin_offsetof(struct l4_row, carry) == 36 && sizeof(struct l4_row) == 72,
                   "l4_frame's walk: the row's layout");
    struct l4_row *r = l4, *const end = l4 + NROWS;
    const u32 *bit = BIT, *pair = PAIR;
    u32 carried = mod_l4_carried;
#define L4_K(k, D) \
        "move.l  " #k "*4+20(%[r]),%%d0\n\t"    /* y = base pair k */ \
        "move.l  " D ",%%d5\n\t" \
        "eor.l   %%d0,%%d5\n\t" \
        "andi.l  #0x80008000,%%d5\n\t"          /* c & H */ \
        "ori.l   #0x80008000," D "\n\t" \
        "andi.l  #0x7FFF7FFF,%%d0\n\t" \
        "sub.l   %%d0," D "\n\t"                 /* s */ \
        "eor.l   %%d5," D "\n\t" \
        "eori.l  #0x80008000," D "\n\t"         /* sh - base, lane by lane */ \
        "moveq   #3,%%d0\n\t" \
        "and.l   %%d6,%%d0\n\t" \
        "lsr.l   #2,%%d6\n\t" \
        "and.l   (%[pair],%%d0.l*4)," D "\n\t"   /* masked by the pair's two used bits */
    __asm__ volatile (
        "move.l  %[rows],%%d7\n"
        "1:\tmovem.l 4(%[r]),%%d1-%%d4\n\t"     /* sh pairs 0..3 */
        "mvz.w   (%[r]),%%d6\n\t"               /* used */
        "beq.s   2f\n\t"
        "addq.l  #1,%[car]\n"                   /* (a row with a used bit: mod_l4_carried) */
        "2:\tlsr.l   #1,%%d7\n\t"
        "subx.l  %%d0,%%d0\n\t"                 /* -(row v written) */
        "and.l   %%d0,%%d6\n\t"                 /* m */
        L4_K(0, "%%d1") L4_K(1, "%%d2") L4_K(2, "%%d3") L4_K(3, "%%d4")
        "movem.l %%d1-%%d4,36(%[r])\n\t"        /* carry */
        "move.l  (%[bit])+,%%d0\n\t"
        "or.l    %%d2,%%d1\n\t"
        "or.l    %%d3,%%d1\n\t"
        "or.l    %%d4,%%d1\n\t"
        "beq.s   3f\n\t"
        "or.l    %%d0,%[crows]\n"               /* any: l4_carry_rows |= 1 << v */
        "3:\tclr.l   (%[r])\n\t"                /* used = init = 0 */
        "lea     72(%[r]),%[r]\n\t"
        "cmpa.l  %[end],%[r]\n\t"
        "bne.w   1b"
        : [r] "+a"(r), [bit] "+a"(bit), [car] "+a"(carried), [crows] "+m"(l4_carry_rows)
        : [rows] "r"(rows), [end] "r"(end), [pair] "a"(pair)
        : "d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "cc", "memory");
#undef L4_K
    mod_l4_carried = carried;
#else
    typedef u32 __attribute__((may_alias)) u32a;
    const u32 H = 0x80008000u;
    for (u32 v = 0; v < NROWS; v++, rows >>= 1) {
        struct l4_row *r = &l4[v];
        u32 m = r->used & (u32)-(int)(rows & 1u);
        const u32a *sh = (const u32a *)(const void *)r->sh, *ba = (const u32a *)(const void *)r->base;
        u32a *ca = (u32a *)(void *)r->carry;
        u32 x, y, d, any = 0;
#define L4_P(k) (x = sh[k], y = ba[k], d = ((x | H) - (y & ~H)) ^ ((x ^ ~y) & H), d &= PAIR[(m >> (2 * (k))) & 3u], \
                 ca[k] = d, any |= d)
        L4_P(0); L4_P(1); L4_P(2); L4_P(3);
#undef L4_P
        if (any)
            l4_carry_rows |= 1u << v;
        if (r->used)
            mod_l4_carried++;
        r->used = 0;
        r->init = 0;
    }
#endif
}

/* (2026-11-20) what LFO1..3 add to LFO4's control B on voice row V this frame (the moving line on LFO4's page,
 * csrc/modulation/moving.c) */
int mod_l4_carry(u32 v, u32 b)
{
    return v < NROWS && b < L4_N ? l4[v].carry[b] : 0;
}
#endif

/* the frame's start, before the evaluator (hooks.S mod_eval, at 0x400272d4): last frame's lower
 * LFOs' writes into the higher LFOs' controls, added into the mirror */
void mod_eval_pre(void)
{
    if (MC->magic != MC_MAGIC || !mc_loaded)
        mc_zero();
    MC->frames++;
#if DN2_LFO4
    l4_frame();
#endif
    u32 rows = MC->rows;                                /* bounded: 16 rows, 2 cells each at most */
    MC->rows = 0;
    for (u32 v = 0; rows; v++, rows >>= 1) {
        if (!(rows & 1u))
            continue;
        struct mc_row *r = &MC->row[v];
        u32 m = r->used;
        r->used = 0;
        r->init = 0;
        volatile u16 *o = OUT + ROW(v) + 9;
        /* (2026-11-21, the User's CPU) the used cells lowest first, as before, each found from its bit at once (a
         * de Bruijn index: bit k of m alone x 0x077cb531 >> 27 -> k), not by stepping through the 16 bits */
        static const u8 DB[32] = {0, 1, 28, 2, 29, 14, 24, 3, 30, 22, 20, 15, 25, 17, 4, 8,
                                  31, 27, 13, 23, 21, 19, 16, 7, 26, 12, 18, 6, 11, 5, 10, 9};
        for (; m; m &= m - 1u) {
            u32 b = DB[((m & (0u - m)) * 0x077CB531u) >> 27];
            int d = (int)r->sh[b] - (int)r->base[b];
            if (!d)
                continue;
            int x = (int)o[b] + d;
            o[b] = (u16)(x < 0 ? 0 : x > TOP ? TOP : x);
            MC->carried++;
        }
    }
}

/* At the evaluator's write (hooks.S mod_wb, only for DEST 9..24): the base its read-add-store
 * uses (cell = base + 2 DEST). LFO (0 LFO1 .. 2 LFO3) writing into a higher LFO's control
 * (never a DEST): our shadow cell; anything else: the mirror row, as stock. */
u32 mod_wb_cell(u32 row, u32 lfo, u32 dest, u32 base)
{
#if DN2_LFO4
    if (dest >= L4_SLOT0 && dest < L4_SLOT0 + L4_N)     /* LFO4's controls (hooks.S lets 101..108 through) */
        return row < NROWS && lfo < 3u && dest - L4_SLOT0 != L4_DEST
               ? l4_wb(row, dest)
               : (u32)l4_sink - 2u * L4_SLOT0;          /* any other: a scratch cell, never the next voice row */
#endif
    u32 k = (dest - 1u) >> 3, f = (dest - 1u) & 7u;
    if (row >= NROWS || dest < 9u || dest > 24u || k <= lfo || f == 3u || MC->magic != MC_MAGIC || !mc_loaded)
        return base;
    struct mc_row *r = &MC->row[row];
    u32 b = dest - 9u;
    u16 bit = (u16)(1u << b);
    if (!(r->init & bit)) {
        r->sh[b] = r->base[b] = ((volatile u16 *)base)[dest];
        r->init |= bit;
    }
    r->used |= bit;
    MC->rows |= 1u << row;
    return (u32)r->sh - 18u;                            /* + 2 x DEST: sh[DEST - 9] */
}

/* the list rule: called with the record and the builder's want (hooks.S mod_mask_hook) */
extern u32 wr_lfo_mask(u32 rec);                        /* page.c: our machines' unused records, the 13 opened */

/* -> the LFO (1..3) a record is a control of, 0 none: SPD MULT FADE WAVE SPH MODE DEP of LFO1
 * 75..83, LFO2 85..93, LFO3 95..103 (DEST 78/88/98 and SLEW 80/90/100 left out); MIDI tracks'
 * MULT records 84/94/104 */
static u32 lfo_of(u32 rec)
{
    if (rec < 75u || rec > 104u)
        return 0;
    u32 k = (rec - 75u) / 10u, f = (rec - 75u) % 10u;
    if (f == 3u || f == 5u)
        return 0;
    return k + 1u;
}

static u32 lfo_of_want(u32 want)
{
    return want == 0x1E00u ? 1u : want == 0x0E00u ? 2u : want == 0x0600u ? 3u : 0u;
}

/* a MIDI track's LFOs run in evaluator B (0x401376bc, its own mirror 0x44617448, called from
 * 0x4012b38a), which mod_wb never sees: its lists stay stock's */
#define KIT_POINTER (*(unsigned char *volatile *)0x800052A0u)
#define UI_TRACK    (*(volatile u8 *)0x42432A6Cu)
#define MIDI_TYPE 4
static int ui_track_midi(void)
{
    u8 t = UI_TRACK;
    unsigned char *kit = KIT_POINTER;
    return t > 15 || !kit || (signed char)kit[52u + 1163u * t + 0xDEu] == MIDI_TYPE;
}

#if DN2_LFO4
#define REC_SLOT(id) (((const int *)(REC_BASE + 60u * (id)))[1])   /* a record's slot (+4) */
#endif

u32 mod_lfo_mask(u32 rec, u32 want)
{
    u32 m = wr_lfo_mask(rec);
    u32 j = lfo_of_want(want), k = lfo_of(rec);
#if DN2_LFO4
    {   /* LFO4's controls (lfo4's records past stock's, slots 101..108 but its DEST): offered to LFO1..3 */
        u32 sl = rec >= 321u && rec <= 330u ? (u32)REC_SLOT(rec) : 0u;   /* ids 321..330: rows 320..329 */
        if (j && sl >= L4_SLOT0 && sl < L4_SLOT0 + L4_N && sl - L4_SLOT0 != L4_DEST && !ui_track_midi())
            return want;
    }
#endif
    if (j && k && j != k && m && !ui_track_midi())      /* another LFO's control: offered */
        return want;
    return m;
}
