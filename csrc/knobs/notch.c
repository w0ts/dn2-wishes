/* Virtual notches on bipolar values, and our popups' slow turns (the User, 2026-11-19: "make the knobs less reactive
 * when I turn them slower ... it is very hard to reach zero ... I would prefer virtual notch"; docs/knob-notch.md).
 * OS 1.12. The constants are in knob.h.
 *
 * - rec.c smp_ui_pop calls kn_item for every UI item: a knob item (A..H) becomes the knob being handled until the
 *   next item is taken. Only writes made while a knob item is handled are knob-driven: CC, NRPN, Overbridge, loads,
 *   the sequencer and our own code write outside one and are never notched.
 * - A knob-driven write that crosses the notch (or lands on it) from elsewhere is written as the notch, unless the
 *   record that drove it carried KN_PASS counts or more (a fast turn passes). Then the next KN_HOLD counts turned the
 *   same way keep it there; a turn back, a pause of KN_HOLD_END or another value (another page, row or record)
 *   ends the hold. Starting at the notch moves at once (the User, D2: free from rest).
 * - Stock's values: fmt.c smp_quant (the sound setter's write) and fx_type_quant (the kit setter's), and p-locks
 *   through kn_lock_snd / kn_lock_kit (the sound and kit parameter sets' LOCK_SET in their vtables, the User, D4).
 * - Our popups (routes, DEST, ENV2's page) turn through kn_units and kn_whole, then kn_value at their zero.
 *
 * Cost: a few compares per UI item and per knob-driven write; nothing per frame. */
#include "knob.h"

#ifdef __m68k__
#define D_ __attribute__((section(".data")))
#else
#define D_
#endif

typedef signed char s8;

#ifdef __m68k__
#define FRAMES  (*(volatile u32 *)0x4058F8D4u)          /* the UI's clock, 1,500 a second */
#else
u32 kn_host_frames;                                     /* the host tests (test/test_knob_c.py) set the clock */
#define FRAMES  kn_host_frames
#endif
#ifdef __m68k__
#define CUR_TCB (*(volatile u32 *)0x4664BCDCu)          /* the running task's TCB (csrc/meter/hooks.S) */
#else
#define CUR_TCB 0u
#endif
#define IT_KNOB 1

struct kn {
    u32 key;                    /* the value caught on its notch (0 none) */
    s32 on;                     /* a hold running */
    s32 hold;                   /* counts of it left */
    s32 stay;                   /* this item is inside the hold: its write stays on the notch */
    s32 dir;                    /* the way it was caught: +1, -1 */
    u32 at;                     /* when it was caught or last turned while held */
    s32 rem;                    /* our popups: a slow turn's leftover counts */
    u32 rem_at;
};
static struct kn ks[8] D_;
u32 kn_cur D_ = 0, kn_tcb D_ = 0;                       /* the knob item being handled, by which task */
int kn_d D_ = 0;
u32 kn_items D_ = 0, kn_seen D_ = 0, kn_catches D_ = 0, kn_held D_ = 0, kn_passes D_ = 0, kn_releases D_ = 0;
u32 kn_locks D_ = 0;            /* knob-driven p-lock writes seen (the checks) */

static void let_go(struct kn *k)
{
    k->on = k->stay = 0;
    kn_releases++;
}

void kn_item(const u8 *it)
{
    kn_cur = 0;
    if (!it || it[0] != IT_KNOB)
        return;
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    if (code < 1u || code > 8u)
        return;
    int d = (s8)it[8];
    kn_cur = code;
    kn_d = d;
    kn_tcb = CUR_TCB;
    kn_items++;
    struct kn *k = &ks[code - 1u];
    k->stay = 0;
    if (!k->on || !d)
        return;
    if (FRAMES - k->at > KN_HOLD_END || (d > 0 ? 1 : -1) != k->dir) {
        let_go(k);                                      /* a pause or a turn back: let go */
        return;
    }
    k->hold -= d > 0 ? d : -d;                          /* turned on the same way: KN_HOLD counts stay, the next moves */
    k->at = FRAMES;
    if (k->hold < 0)
        let_go(k);
    else
        k->stay = 1;
}

s32 kn_value(u32 key, s32 old, s32 now, s32 n)
{
    if (!kn_cur || n < 0 || CUR_TCB != kn_tcb)
        return now;                                     /* no knob item handled, or another task's write */
    struct kn *k = &ks[kn_cur - 1u];
    kn_seen++;
    if (k->key != key)
        k->on = k->stay = 0;                            /* another value under this knob: no hold */
    else if (k->stay) {
        kn_held++;
        return n;                                       /* held: the value stays on its notch */
    }
    if (old == n || now == old)
        return now;                                     /* from the notch (free), or no move */
    if (!((old < n && now >= n) || (old > n && now <= n)))
        return now;                                     /* not reaching it */
    if (kn_d >= KN_PASS || kn_d <= -KN_PASS) {
        kn_passes++;
        return now;                                     /* a fast turn goes through */
    }
    k->key = key;
    k->on = 1;
    k->stay = 1;                                        /* (the rest of this item's write: on the notch) */
    k->hold = KN_HOLD;
    k->dir = now > old ? 1 : -1;
    k->at = FRAMES;
    kn_catches++;
    return n;
}

int kn_units(int d)
{
    if (!kn_cur)
        return d;
    struct kn *k = &ks[kn_cur - 1u];
    int a = d < 0 ? -d : d;
    if (a >= KN_POP_FAST) {
        k->rem = 0;
        return d * KN_POP_FAST_MUL;
    }
    if (a > KN_POP_SLOW) {
        k->rem = 0;
        return d;
    }
    if (FRAMES - k->rem_at > KN_REM_END || (k->rem > 0 && d < 0) || (k->rem < 0 && d > 0))
        k->rem = 0;
    k->rem_at = FRAMES;
    k->rem += d;
    int u = k->rem / KN_POP_DIV;                        /* (toward zero: the leftover keeps its sign) */
    k->rem -= u * KN_POP_DIV;
    return u;
}

s32 kn_whole(s32 dep, int units, s32 top)
{
    if (!units)
        return dep;
    s32 v = (dep & ~0xFF) + units * 0x100;
    return v < 0 ? 0 : v > top ? top : v;
}

/* the stock records with a centre (1.12's formatters, scratch/knob-precision.md §1): 64.00 unless named */
static const u16 CENTRE64[] = {
    29, 30, 31,                                         /* chord NOT2..NOT4 */
    42, 49, 70, 71,                                     /* EQ GAIN, filter ENV, BAL, PAN */
    75, 77, 83, 85, 87, 93, 95, 97, 103,                /* LFO1-3 SPD, FADE, DEP (the attenuverter) */
    115, 136, 137, 138,                                 /* delay WID, ext-in BAL, LPAN, RPAN (kit) */
    157, 207,                                           /* sidechain SCF (kit), FM MIX */
    208, 209, 210, 211,                                 /* FM ratio offsets COFF AOFF B1OF B2OF */
    227, 228, 229, 230, 231, 232, 233, 234,             /* FM macro offsets */
    238, 242, 263, 293,                                 /* TUNE (WAVETONE TUN1 TUN2, FM DRUM, SWARMER) */
    307,                                                /* retrig VFAD */
};

s32 kn_centre(u32 id)
{
    for (u32 i = 0; i < sizeof CENTRE64 / sizeof CENTRE64[0]; i++)
        if (CENTRE64[i] == id)
            return 0x4000;
    switch (id) {
    case 204: return 0x3F00;                            /* FM HARM: 63 */
    case 163: return 0x2000;                            /* MIDI PB: 32.00 */
    case 246: case 250: return 0x3200;                  /* WAVETONE OFS1 OFS2: 50.00 */
    case 313: case 314: case 315: return 0x7F00;        /* euclid rotations: 127 */
    default: return -1;
    }
}

#ifdef __m68k__
/* p-locks (the User, D4: notched too): the sound and kit parameter sets' LOCK_SET (vtables 0x401dbc0c + 68,
 * 0x401dbc94 + 68), (this, record id, value, step). The old value is the lock's (LOCK_GET, + 64), or the base value
 * when the step has no lock yet */
#define SLOT_OF  ((s32 (*)(u32))0x400DBE28u)
typedef s32 (*get_fn)(u32, u32, u32);
typedef u32 (*set_fn)(u32, u32, u32, u32);

static u32 lock_set(u32 self, u32 id, u32 value, u32 step, u32 get, u32 set, u32 base_off)
{
    s32 n = kn_cur ? kn_centre(id) : -1;
    if (n >= 0) {
        s32 old = ((get_fn)get)(self, id, step);
        if (old < 0 || old > 0xFFFF) {                  /* no lock on that step yet: the base value */
            s32 slot = SLOT_OF(id);                     /* (as the setters: the values from self + 16's vtable + 40) */
            u32 in = *(volatile u32 *)(self + 16u), vals = 0;
            if (in >= 0x40000000u)
                vals = (*(u32 (**)(u32))(*(volatile u32 *)in + 40u))(in);
            old = slot >= 0 && slot <= 100 && vals >= 0x40000000u ? *(volatile u16 *)(vals + base_off + 2u * (u32)slot)
                                                                  : -1;
        }
        kn_locks++;
        if (old >= 0)
            value = (u32)kn_value(id | KN_KEY_LOCK, old, (s32)(value & 0xFFFFu), n);
    }
    return ((set_fn)set)(self, id, value, step);
}

u32 kn_lock_snd(u32 self, u32 id, u32 value, u32 step)
{
    return lock_set(self, id, value, step, 0x40037C52u, 0x40037CB6u, 0x14u);
}

u32 kn_lock_kit(u32 self, u32 id, u32 value, u32 step)
{
    return lock_set(self, id, value, step, 0x40037F48u, 0x40037FACu, 0u);
}
#endif
