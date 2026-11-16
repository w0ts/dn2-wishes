/* The modulation matrix: more routes than stock's one per LFO (the User, 2026-11-11: up to 16 LFO routes a track,
 * LFO1-3 sharing them, stock's route 1 of each LFO counting; docs/matrix.md). OS 1.12.
 *
 * A sound's routes are a field of its wishes record (csrc/wishes, tag WT_MX_ROUTES): four bytes each, the source
 * (0 LFO1, 1 LFO2, 2 LFO3), the destination slot (25..100, a sound parameter's cell of the voice row), and the
 * depth in stock DEP's units (0..0x7f00, 0x4000 none).
 *
 * Heard (mx_eval, from the frame's evaluator call, csrc/modulation/hooks.S mod_eval): after stock's evaluator
 * 0x40137a06 has run every voice row's LFO1-3 and their stock routes, each row gets its track's routes, the same
 * arithmetic as stock's route 1 (0x40137d6a): cell += mac((depth - 0x4000) x 2, LFO output), clamped to 0..0x7f00.
 * The LFO's output is the one stock's route 1 uses (state + 84, after the fade). A route into an LFO's own controls
 * (slots 1..24) is not offered: it would come after that LFO has read them (stock's DEST, and csrc/modulation's
 * cascade, still reach them).
 *
 * Constant cost (the User's choice): every row runs all MX_SLOTS routes each frame; an unused route adds 0 into a
 * scratch row of ours instead of a cell, so a frame costs the same with no route as with every route set.
 *
 * Read in the UI pass, never in the frame (mx_poll, from page.c wr_poll): when a record changed (wish_edits) or the
 * kit moved, each track's routes are read from its sound's record and laid out into the track's spare table, which
 * then becomes the live one. The frame reads only those tables. A voice's track is the kit sound it plays (stock
 * keeps the sound a voice plays at 0x800052a8, written with the voice's parameters by 0x4002549c; LFO4 keyed on it
 * on 1.11, measured on the instrument): a voice playing any other sound gets no routes.
 */
#include "../wishes/wish.h"

typedef signed short s16;
typedef unsigned long mx_addr;          /* an address: 32 bits here, the host's width in the host tests */

#define MX_LFO 15                       /* routes beside stock's three: 16 a track, at least one stock route used */
#define MX_SLOTS MX_LFO
#define MX_SRCS 3                       /* LFO1, LFO2, LFO3 */
#define MX_TOP 0x7F00                   /* the evaluator's clamp (0x40137da2) */
#define MX_NONE 0x4000u                 /* a depth that adds nothing */
#define MX_MAGIC 0x4D583031u            /* 'MX01' */

#ifndef MX_HOST
#define OUT_B 0x800068E4u               /* the evaluator's first argument: row v's slot s at OUT_B + 34 + 202 v + 2 s */
#define VSOUND ((volatile u32 *)0x800052A8u)    /* the sound voice v plays */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define LFO_OUT(v) ((volatile u8 *)(0x44640C1Cu + 120u * (u32)(v)))    /* LFO l at + 40 l: state + 84 */
#endif

struct mx_e {
    s32 cell;                           /* the cell's byte offset from the row's slot 0, or the scratch row's */
    s32 d1;                             /* (depth - 0x4000) x 2, as stock's route 1 takes DEP */
    u32 src;                            /* the LFO's output, in bytes from LFO1's (40 a LFO) */
};
struct mx_tab {
    struct mx_e e[MX_SLOTS];
};
struct mx_state {
    u32 magic;
    u32 edits;                          /* wish_edits when the tables were last laid out */
    u32 kit;                            /* the kit they were laid out for */
    u32 compiles, frames;               /* the checks' */
    u32 sound[16];                      /* the sound track t's table was laid out from */
    u32 live[16];                       /* track t's live table: 0 or 1 */
    struct mx_tab tab[16][2];
    struct mx_tab none;                 /* every route unused */
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

static void lay_none(struct mx_tab *t)
{
    for (u32 k = 0; k < MX_SLOTS; k++) {
        t->e[k].cell = none_cell();
        t->e[k].d1 = 0;
        t->e[k].src = 0;
    }
}

/* a record's routes (VAL, N bytes) -> TAB; -> the routes laid out. Anything out of range is left unused. */
u32 mx_lay(const u8 *val, int n, struct mx_tab *tab)
{
    u32 k = 0;

    lay_none(tab);
    for (int at = 0; at + 4 <= n && k < MX_SLOTS; at += 4) {
        u32 src = val[at], slot = val[at + 1], dep = (u32)val[at + 2] << 8 | val[at + 3];
        if (src >= MX_SRCS || slot < 25u || slot > 100u)
            continue;
        if (dep > MX_TOP)
            dep = MX_TOP;
        tab->e[k].cell = (s32)(2u * slot);
        tab->e[k].d1 = ((s32)dep - (s32)MX_NONE) * 2;
        tab->e[k].src = 40u * src;
        k++;
    }
    return k;
}

static void mx_zero(void)
{
    u32 *w = (u32 *)MX;
    for (u32 k = 0; k < sizeof(struct mx_state) / 4; k++)
        w[k] = 0;
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
    u8 buf[4 * MX_SLOTS];
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
        mx_lay(buf, n, &MX->tab[t][spare]);
        MX->live[t] = spare;            /* the frame takes the new table from its next row */
        MX->sound[t] = sound;
    }
    MX->compiles++;
    mx_compiles++;
}

#ifndef __m68k__
static s32 mx_mac(s32 a, s32 b)
{
    return (s32)(((long long)a * b) >> 31);         /* the host's model of the frame's fractional MACSR */
}
#endif

/* the frame, after stock's evaluator: B its first argument (the mirror OUT_B). Every row, every route. */
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
        volatile u8 *lfo = LFO_OUT(v);
        u8 *row = (u8 *)(b + 34u + 202u * v);
        const struct mx_e *e = tab->e;
#ifdef __m68k__
        /* stock's route 1 (0x40137d7e..0x40137db0), instruction for instruction: mac.l under the frame's MACSR
         * (fractional, set by the audio interrupt), the cell sign-extended, the sum clamped to 0..0x7f00 */
        u32 n = MX_SLOTS;
        __asm__ volatile (
            "1:\tmove.l  (%[e])+,%%d0\n\t"           /* the cell's offset */
            "move.l  (%[e])+,%%d1\n\t"                /* (depth - 0x4000) x 2 */
            "move.l  (%[e])+,%%a1\n\t"                /* the LFO's output's offset */
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
