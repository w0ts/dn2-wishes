/* AMP ON/OFF for the drum machines (2026-11-20, the User; dnfw.waverider.ampsw, docs/live-select.md "AMP ON/OFF").
 *
 * On stock's AMP page (AMP 1/2), VOL's place (H, record 72) is AMP ON/OFF while the track's machine is a drum
 * (AS_TYPES: MACHINEDRUM, SOPHIE, DRUM; PLAITS on a drum model, BD SD HH, by its MODL word). OFF (the default) bypasses
 * stock's AMP envelope and VOL in the DSP (ampsw.asm): the voice leaves the chain as it reached the AMP stage. ON is
 * stock's AMP and VOL as usual. Every other machine: VOL as stock.
 *
 * The setting is the sound's wishes record field WT_AMP_SW (one byte, AS_ON); OFF is no field, so an old sound, a
 * preset and every new sound read OFF. VOL's own value stays in the sound, untouched: ON plays it again.
 *
 * Entries: as_poll (page.c, every UI pass: the tracks' mask, which link.c sends to the DSP), as_draw (scope.c
 * scope_dots, after stock's AMP page: cell H drawn as AMP), as_pop (rec.c smp_ui_pop, before the routes popups: knob
 * H turned on that page sets the field, right ON, left OFF; H's push toggles it; VOL is not turned, its routes popup
 * not opened). */
#include "../wishes/wish.h"
#include "../waverider/widgets.h"
#include "wr_gen.h"

#define KIT        (*(volatile u32 *)0x800052A0u)
#define SOUND(t)   (KIT + 52u + 1163u * (u32)(t))
#define TYPE_OF(s) ((int)*(volatile signed char *)((s) + 0xDEu))
#define WORD(s, slot) (*(volatile u16 *)((s) + 0x14u + 2u * (u32)(slot)))
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY     0
#define IT_KNOB    1
#define K_ENC_H    48                           /* encoder H pushed (K_ENC_A 41 + 7) */
#define KNOB_H     8

static const signed char as_types[AS_NTYPES] = {AS_TYPES};

u32 as_mask __attribute__((section(".data"))) = 0;      /* bit t: track t's sound is a drum with AMP OFF (link.c) */
u32 as_gen __attribute__((section(".data"))) = 0;       /* moves when as_mask does */
u32 as_turns __attribute__((section(".data"))) = 0;     /* (the checks read these) */
u32 as_draws __attribute__((section(".data"))) = 0;
static u32 seen_edits __attribute__((section(".data"))) = 0xFFFFFFFFu;
static u32 seen_kit __attribute__((section(".data"))) = 0;
static u32 seen_key[16] __attribute__((section(".data")));
static u32 push_eaten __attribute__((section(".data"))) = 0;

/* 1: TYPE on sound S is a drum machine (PLAITS by its MODL) */
int as_drum(int type, u32 s)
{
    for (int k = 0; k < AS_NTYPES; k++)
        if (type == as_types[k])
            return 1;
    if (AS_PLAITS >= 0 && type == AS_PLAITS) {
        int v = (WORD(s, AS_MODL_SLOT) >> 8) - AS_MODL_LO;
        return v >= AS_MODL_DRUM_MIN && v <= AS_MODL_DRUM_MAX;
    }
    return 0;
}

/* 1: sound S's AMP is ON (its field); no field, OFF */
int as_on(u32 s)
{
    u8 v = 0;
    return wish_get(s, WT_AMP_SW, &v, 1) == 1 && v == AS_ON;
}

/* sound S's AMP set ON or OFF (OFF: the field removed) -> 0 */
int as_set(u32 s, int on)
{
    u8 v = AS_ON;
    return wish_put(s, WT_AMP_SW, &v, on ? 1u : 0u);
}

/* page.c, every UI pass: the mask, again when the kit, a track's machine or MODL word, or any record moved */
void as_poll(void)
{
    u32 kit = KIT;
    if (!kit) {
        if (as_mask) {
            as_mask = 0;
            as_gen++;
        }
        return;
    }
    int again = kit != seen_kit || wish_edits != seen_edits;
    for (int t = 0; t < 16; t++) {
        u32 s = SOUND(t), key = (u32)(u8)TYPE_OF(s) << 16 | WORD(s, AS_MODL_SLOT);
        if (key != seen_key[t]) {
            seen_key[t] = key;
            again = 1;
        }
    }
    if (!again)
        return;
    seen_kit = kit;
    seen_edits = wish_edits;
    u32 m = 0;
    for (int t = 0; t < 16; t++) {
        u32 s = SOUND(t);
        if (as_drum(TYPE_OF(s), s) && !as_on(s))
            m |= 1u << t;
    }
    if (m != as_mask) {
        as_mask = m;
        as_gen++;
    }
}

/* the UI track's sound when it is a drum on stock's AMP page (nothing of ours over it), else 0 */
static u32 page_drum(void)
{
    extern int amp_stock_page(void);            /* csrc/scope/scope.c */
    u32 kit = KIT;
    if (!kit || !amp_stock_page())
        return 0;
    u32 s = SOUND(UI_TRACK & 15u);
    return as_drum(TYPE_OF(s), s) ? s : 0;
}

/* scope.c scope_dots, after stock's AMP page: on a drum, cell H is AMP ON/OFF (stock's toggle, AMP.T's) */
void as_draw(void *c)
{
    extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
    u32 s = page_drum();
    if (!s)
        return;
    cv_fill(c, wg_x(AS_VOL_PLACE), wg_y(AS_VOL_PLACE), wg_x(AS_VOL_PLACE) + 25, wg_y(AS_VOL_PLACE) + 26, 0);
    wg_toggle(c, AS_VOL_PLACE, as_on(s));
    wg_label(c, AS_VOL_PLACE, "AMP");
    as_draws++;
}

/* rec.c smp_ui_pop, before the routes popups: 1 when the item is ours (then dropped) */
int as_pop(const u8 *it)
{
    extern int smp_overlay_dirty;
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    if (it[0] == IT_KEY && code == K_ENC_H) {
        int press = (it[11] & 1u) && !(it[11] & 0x10u);
        if (!press) {                           /* the release of a push we took */
            int ours = push_eaten;
            push_eaten = 0;
            return ours;
        }
        u32 s = page_drum();
        if (!s)
            return 0;
        push_eaten = 1;
        if (!(it[11] & 8u)) {                   /* (not a repeat) */
            as_set(s, !as_on(s));
            as_turns++;
            smp_overlay_dirty = 1;
        }
        return 1;
    }
    if (it[0] != IT_KNOB || code != KNOB_H)
        return 0;
    u32 s = page_drum();
    if (!s)
        return 0;
    int d = (signed char)it[8];
    if (d) {
        int on = d > 0;
        if (on != as_on(s))
            as_set(s, on);
        as_turns++;
        smp_overlay_dirty = 1;
    }
    return 1;
}
