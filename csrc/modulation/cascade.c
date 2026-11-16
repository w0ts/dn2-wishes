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
_Static_assert(sizeof(struct mc_state) <= MOD_CASCADE_BYTES, "the cascade's state fits its part of MOD_RAM");

static void mc_zero(void)
{
    u32 *w = (u32 *)MC;
    for (u32 k = 0; k < sizeof(struct mc_state) / 4; k++)
        w[k] = 0;
    MC->magic = MC_MAGIC;
}

/* the frame's start, before the evaluator (hooks.S mod_eval, at 0x400272d4): last frame's lower
 * LFOs' writes into the higher LFOs' controls, added into the mirror */
void mod_eval_pre(void)
{
    if (MC->magic != MC_MAGIC)
        mc_zero();
    MC->frames++;
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
        u32 b = 0;
        if (!(m & 0xFFu)) {                             /* only LFO3's controls: skip LFO2's eight */
            m >>= 8;
            b = 8;
        }
        for (; m; b++, m >>= 1) {
            if (!(m & 1u))
                continue;
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
    u32 k = (dest - 1u) >> 3, f = (dest - 1u) & 7u;
    if (row >= NROWS || dest < 9u || dest > 24u || k <= lfo || f == 3u || MC->magic != MC_MAGIC)
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

u32 mod_lfo_mask(u32 rec, u32 want)
{
    u32 m = wr_lfo_mask(rec);
    u32 j = lfo_of_want(want), k = lfo_of(rec);
    if (j && k && j != k && m && !ui_track_midi())      /* another LFO's control: offered */
        return want;
    return m;
}
