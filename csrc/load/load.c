/* The DSP load budget at note-on (2026-11-12, the User: "voices are not equal in cost... a big voice uses one voice but
 * blocks the budget of another, and we keep 16 voices"; docs/load-budget.md).
 *
 * All 16 voice slots and stock's VOICES settings stay as they are. Each sounding voice spends its variant's cost
 * (dnfw.load's generated table, wr_gen.h: load_md, load_mnm, load_plaits ...) from one DSP budget, LOAD_AVAIL. At a
 * note-on, before stock's allocator (0x4002a6a2) picks the note's slots, load_pre adds up what the 16 slots cost now:
 *   - a slot whose last owner is a stock-machine track (FM TONE, WAVETONE, FM DRUM, SWARMER): that machine's cost,
 *     always (stock renders every such voice every block, sounding or not: measured, docs/load-budget.md);
 *   - a slot of one of our machines: its track's cost while its key is held, or while the DSP still reports it busy
 *     (its release: the telemetry's per-slot cost, link.c smp_tlm_cost, over LOAD_TAIL); else nothing;
 *   - the send FX and the bus inserts (load_fx).
 * If the new note's voices do not fit, the allocator is made to STEAL rather than take a free slot: for this one
 * call its live masks (the shared pool, and the track's own if it has reserved voices) keep only the held slots, so
 * stock steals the oldest of them by its own STEAL mode and the new note retriggers it (its cost freed at once).
 * load_post puts the hidden free slots back, and if the steal did not free enough (a heavy voice replacing a light
 * one) releases the next oldest held voices with stock's own one-slot note-off, until it fits.
 *
 * A note on a stock machine's track, a kit that fits, and the setting off (SETTINGS > PERSONALIZE, VOICE BUDGET: the
 * settings sector's flag bit 3) leave stock's allocation exactly as it is. The DSP's frame guard stays the safety net.
 * The per-track costs are computed in the UI loop (load_poll); the interrupt only adds them up.
 *
 * 2026-11-13 (the unit, r14b: JUNO with a long release, 16 short notes piled up to 12 sounding voices, the guard then
 * dropped voices and inserts; the budget never stole). Three things were wrong, all fixed here:
 *   - the steal took only HELD slots: released voices still sounding (their release tails, as costly as a held voice)
 *     were never candidates, so a run of short notes always found "nothing held" and took a free slot. Now the
 *     candidates are the slots still sounding (held, or the DSP's cost over LOAD_TAIL), released ones first;
 *   - the room was a fixed LOAD_AVAIL (310,000 less our fixed work): the unit's stock took ~66 % of that kit's frame,
 *     so the guard ran out at ~110,000 of ours. Now, while the DSP reports it (the idle packet's units 58..61, link.c
 *     smp_room_now: each insert pass's room before its deadline as the last packet gave it), a note fits when its cost
 *     and a margin fit in the least of those rooms, less the bus inserts still to run and what notes since that packet
 *     took (load_pend). LOAD_AVAIL stays the fallback while no room is reported;
 *   - a voice's cost was its table value at the default knobs (JUNO 8,815 + its filter; the unit measured ~10,700 a
 *     voice, ~15,000 in its note block): now the larger of that and its track's measured voices (load_meas).
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#include "wr_gen.h"

#define KIT       (*(volatile u32 *)0x800052A0u)
#define SOUND(t)  ((volatile u8 *)(KIT + 52u + 1163u * (u32)(t)))
#define WORD(t, s) (*(volatile u16 *)(KIT + 52u + 1163u * (u32)(t) + 0x14u + 2u * (u32)(s)))
/* the allocator's own state (docs/load-budget.md, OS 1.12): per slot v its voice record (+1 the last owner track,
 * +8 its start stamp, +12 its release stamp), the held slots, the tick, each track's voices a note, the live masks
 * (the shared pool, then each track's reserved slots, then a byte a track: has a reservation) copied from the staging
 * block once a tick (0x4002a414, when 0x4059dafc is set) */
#define VOICE(v)   ((volatile u8 *)(0x40288304u + 20u * (u32)(v)))
#define HELD       (*(volatile u32 *)0x4059DD1Cu)
#define TICK       (*(volatile u32 *)0x4059DB04u)
#define PER_NOTE   ((volatile signed char *)0x4059DA00u)
#define LIVE_POOL  (*(volatile u32 *)0x4059D96Cu)
#define LIVE_MASK  ((volatile u32 *)0x4059D970u)
#define LIVE_HAS   ((volatile u8 *)0x4059D9B0u)
#define TICK_DUE   (*(volatile u32 *)0x4059DAFCu)
#define TICK_COPY  ((void (*)(void))0x4002A414u)
/* stock's one-slot note-off (as at 0x40026df4): the key up, the ISR's gate masks, the voice state, its gate timers */
#define KEY_UP     ((void (*)(u32))0x4002B06Eu)
#define VSTATE     (*(volatile u32 *)0x80005348u)
#define GATE_A     ((volatile u32 *)0x80005220u)
#define GATE_B     ((volatile u32 *)0x80005260u)
#define SET_BUDGET_OFF 8u                       /* the settings sector's flag bit 3, VOICE BUDGET OFF (jump.c keeps bits
                                                 * 0, 1 itself and carries the others; bit 2 LIVE SELECT's) */

extern int set_flag(u32 bit);                   /* jump.c */
extern volatile u16 smp_tlm_cost[16];           /* link.c: the DSP's cost of each slot / 16, the last idle packet's */
extern volatile u16 smp_room_now[4];            /* link.c: each insert pass's room before its deadline, the last packet's:
                                                 * (room + 2^19) / 16, 0xFFFF none (2026-11-13) */
extern volatile u32 smp_room_at;                /* link.c: when they came (periods | 1), 0 never */
extern volatile u32 smp_periods;                /* link.c: the periods (audio ISR calls) */
#define ROOM_FRESH   150u                       /* a room older than 0.1 s is not trusted: LOAD_AVAIL instead */
#define ROOM_MARGIN  6000u                      /* cycles kept free besides a note's half again (its note block costs
                                                 * ~1.4 x its steady blocks: JUNO 15,000 / 10,700 on the unit) */

/* 2026-11-13 (the coupled proof: the budget stole, the guard still skipped): the room a note of NEED (N voices of ONE)
 * asks of the DSP's bus-pass room. The guard admits a voice at its turn only if max(1.5 x its last cost,
 * LOAD_GUARD_FLOOR) still fits before its limit, so the room left after every voice must keep LOAD_GUARD_FLOOR less a
 * voice's own cost free for the last one; then the note itself, half again for its note block, and a margin. */
static int room_asked(u32 need, u32 one)
{
    u32 floor_part = LOAD_GUARD_FLOOR > one ? LOAD_GUARD_FLOOR - one : 0u;
    return (int)(need + need / 2u + floor_part + ROOM_MARGIN);
}
extern u8 ins_sel[16][2];                       /* ins.c: each track's two insert types */
extern int rvt_state, dlt_state;                /* fdn8/ui.c, xdly/ui.c: 1 when the send is FDN8 / XDLY */
extern int fxp_chorus_type(void);               /* fxpage/fxp.c: 1 when the chorus send is JUNO */

u16 load_voice[16] __attribute__((section(".data"))) = {0};   /* a voice of track t (one of ours), cycles; 0 stock, MIDI */
u16 load_stock[16] __attribute__((section(".data"))) = {0};   /* a slot of track t (a stock machine's), cycles, always */
u32 load_fx __attribute__((section(".data"))) = 0;            /* the send FX and the bus inserts */
u32 load_busins __attribute__((section(".data"))) = 0;        /* the bus inserts alone (they run after the rooms' pass) */
u16 load_meas[16] __attribute__((section(".data"))) = {0};    /* track t's voices as the DSP measured them, cycles, the
                                                               * largest lately (eased by 1/64 a UI loop) */
u32 load_pend __attribute__((section(".data"))) = 0;          /* cycles the notes took since the rooms' packet */
u32 load_pend_at __attribute__((section(".data"))) = 0;       /* ... that packet (smp_room_at) */
u32 load_tails __attribute__((section(".data"))) = 0;         /* steals made of released voices still sounding */
u32 load_by_room __attribute__((section(".data"))) = 0;       /* note-ons judged by the DSP's room (not LOAD_AVAIL) */
int load_last_free __attribute__((section(".data"))) = 0;     /* the last note's room (cycles; LOAD_AVAIL's if none) */
u8 load_off __attribute__((section(".data"))) = 0;            /* the setting: 1 off */
/* the checks read these */
u32 load_checks __attribute__((section(".data"))) = 0;        /* note-ons on our tracks looked at */
u32 load_over __attribute__((section(".data"))) = 0;          /* ... that did not fit: made to steal */
u32 load_keyups __attribute__((section(".data"))) = 0;        /* further voices released for a heavy note */
u32 load_last_sum __attribute__((section(".data"))) = 0;      /* the last note's slots' cost before it, and its need */
u32 load_last_need __attribute__((section(".data"))) = 0;
u32 load_sp_min __attribute__((section(".data"))) = 0xFFFFFFFFu;   /* the lowest stack pointer seen in the interrupt */
u32 load_ret __attribute__((section(".data"))) = 0;           /* hooks.S: the call site's return address */
static u32 hid_pool __attribute__((section(".data"))) = 0;    /* the free slots hidden for this call (0: none) */
static u32 hid_mask __attribute__((section(".data"))) = 0;
static int hid_t __attribute__((section(".data"))) = -1;
static u32 need_now __attribute__((section(".data"))) = 0;
static u32 one_now __attribute__((section(".data"))) = 0;
static u32 sum_now __attribute__((section(".data"))) = 0;
static u16 cost_was[16] __attribute__((section(".data"))) = {0};
static u16 voice_was[16] __attribute__((section(".data"))) = {0};

/* -- the UI loop: each track's cost ----------------------------------------------------------------------------- */

static int clampi(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

/* the choice of control J (of N) of track T's Monomachine-style machine, as the DSP reads it: "knob" (trunc(v / top x
 * 128) x N >> 7: MODL) or "frac" (min(N - 1, v N / top): ANALOG 2's page 2) */
static int choice(int t, int j, int n, int frac)
{
    int top = mnm_top[j];
    int v = clampi((WORD(t, mnm_slot[j]) >> 8) - mnm_lo[j], 0, top);
    if (frac)
        return clampi(v * n / top, 0, n - 1);
    return clampi(((v * 128 / top) * n) >> 7, 0, n - 1);
}

/* a voice of track T, cycles; *STOCK set for a stock machine (whose slots cost it always) */
static u32 track_cost(int t, int *stock)
{
    volatile u8 *s = SOUND(t);
    int ty = (signed char)s[0xDE];
    u32 c = 0;
    *stock = 0;
    if (ty >= 0 && ty <= 3) {
        *stock = 1;
        c = load_type[ty];
    } else if (ty == 5) {                       /* MACHINEDRUM: its TYPE picks the machine */
        int v = clampi(WORD(t, LOAD_TYPE_SLOT) >> 8, 0, 127);
        c = load_md[clampi((v * LOAD_MD_N) >> 7, 0, LOAD_MD_N - 1)];
    } else {
        int mi = mnm_index(ty - 4);
        if (mi >= 0 && mi == LOAD_MI_PLAITS)
            c = load_plaits[choice(t, LOAD_J_PLAITS, sizeof load_plaits / sizeof load_plaits[0], 0)];
        else if (mi >= 0 && mi == LOAD_MI_SOPHIE)
            c = load_sophie[choice(t, LOAD_J_SOPHIE, sizeof load_sophie / sizeof load_sophie[0], 0)];
        else if (mi >= 0 && mi == LOAD_MI_A2)
            c = load_a2flt[choice(t, LOAD_J_A2, sizeof load_a2flt / sizeof load_a2flt[0], 1)];
        else if (mi >= 0)                       /* MONOMACHINE: its engine's place (ENGN) */
            c = load_mnm[mnm_live(mi, WORD(t, mnm_slot[MNM_MONO_J]))];
        else if (ty > 0 && ty < 32)
            c = load_type[ty];                  /* the sample machines */
    }
    if (c) {                                    /* the filter, the inserts a voice runs */
        int f = s[0xDF];
        if (f >= 0 && f < 16)
            c += load_filter[f];
        for (int j = 0; j < 2; j++) {
            int y = ins_sel[t][j];
            if (y < 16 && !(LOAD_BUS_MASK & (1u << y)))
                c += load_ins[y];
        }
    }
    return c > 65535u ? 65535u : c;
}

/* page.c wr_poll, once a UI loop: the costs the interrupt adds up */
void load_poll(void)
{
    load_off = (u8)set_flag(SET_BUDGET_OFF);
    if (!KIT)
        return;
    u32 fx = 0;
    u32 meas[16];
    for (int t = 0; t < 16; t++)                /* (a loop: no memset in the chunk) */
        meas[t] = 0;
    for (int v = 0; v < 16; v++) {              /* the DSP's measure of each sounding voice, by its track */
        int own = VOICE(v)[1];
        u32 c = (u32)smp_tlm_cost[v] * 16u;
        if (own <= 15 && smp_tlm_cost[v] > LOAD_TAIL && c > meas[own])
            meas[own] = c;
    }
    for (int t = 0; t < 16; t++) {
        int stock;
        u32 c = track_cost(t, &stock);
        if (c != voice_was[t])                  /* another machine or variant: its old measure is not its own */
            load_meas[t] = 0;
        voice_was[t] = (u16)c;
        load_voice[t] = (u16)(stock ? 0 : c);
        load_stock[t] = (u16)(stock ? c : 0);
        u32 m = load_meas[t];
        m -= m >> 6;
        if (meas[t] > m)
            m = meas[t];
        load_meas[t] = (u16)(m > 65535u ? 65535u : m);
        for (int j = 0; j < 2; j++) {
            int y = ins_sel[t][j];
            if (y < 16 && (LOAD_BUS_MASK & (1u << y)))
                fx += load_bus[y];
        }
    }
    load_busins = fx;
    fx += rvt_state == 1 ? LOAD_SEND_FDN8 : 0;
    fx += dlt_state == 1 ? LOAD_SEND_XDLY : 0;
    fx += fxp_chorus_type() == 1 ? LOAD_SEND_JUNO : 0;
    load_fx = fx;
}

/* how many voices of a variant costing C fit with the kit's stock slots and sends (the lists' tag, informational) */
int load_fit(u32 c)
{
    u32 fixed = load_fx;
    for (int t = 0; t < 16; t++)
        fixed += load_stock[t] ? load_stock[t] : 0;      /* (a stock track: at most its own slots; counted once) */
    if (!c || fixed >= LOAD_AVAIL)
        return fixed >= LOAD_AVAIL ? 0 : LOAD_VOICES;
    u32 n = (LOAD_AVAIL - fixed) / c;
    return n > LOAD_VOICES ? LOAD_VOICES : (int)n;
}

/* -- the interrupt: before and after stock's allocator, at a note-on --------------------------------------------- */

/* a voice of track T, cycles: its table cost, or its track's measured voices when dearer (2026-11-13) */
static u32 voice_cost(int t)
{
    u32 c = load_voice[t];
    return c && load_meas[t] > c ? load_meas[t] : c;
}

/* slot V sounds: held, or released and the DSP still reports it busy (its release tail) */
static int sounding(int v)
{
    return (HELD & (1u << v)) || smp_tlm_cost[v] > LOAD_TAIL;
}

static u32 slot_cost(int v)
{
    int own = VOICE(v)[1];
    if (own > 15)
        return 0;
    if (load_stock[own])
        return load_stock[own];
    if (!sounding(v))
        return 0;
    u32 c = voice_cost(own), m = (u32)smp_tlm_cost[v] * 16u;
    return m > c ? m : c;                       /* (2026-11-13: what the DSP measured, when dearer) */
}

/* the DSP's room now (cycles, may be negative), from the last idle packet: 1 when it is reported and fresh */
static int room_now(int *room)
{
    u32 at = smp_room_at;
    if (!at || (int)(smp_periods - at) > (int)ROOM_FRESH)   /* (signed: at is periods | 1, a period ahead at most) */
        return 0;
    u32 m = smp_room_now[3];                    /* the bus pass's: the last of ours in the frame, all our voices and the
                                                 * earlier insert passes already spent (inserts/bus.py, ins_start 3) */
    if (m == 0xFFFFu)                           /* no deadline known */
        return 0;
    if (load_pend_at != at) {                   /* a new packet: what earlier notes took is in its rooms */
        load_pend_at = at;
        load_pend = 0;
    }
    *room = (int)(m * 16u) - (1 << 19) - (int)load_busins - (int)load_pend;
    return 1;
}

/* the note fits: by the DSP's room while reported (2026-11-13), else by LOAD_AVAIL */
static int fits_now(u32 sum, u32 need, u32 one)
{
    int room;
    if (room_now(&room)) {
        load_by_room++;
        load_last_free = room;
        return room_asked(need, one) <= room;
    }
    load_last_free = (int)LOAD_AVAIL - (int)sum;
    return sum + need <= LOAD_AVAIL;
}

/* hooks.S: A the allocator's nine arguments (track, note, event (1 note-on), ...) */
void load_pre(const u32 *a)
{
    u32 sp;
    __asm__ volatile ("move.l %%sp, %0" : "=r" (sp));
    if (sp < load_sp_min)
        load_sp_min = sp;
    hid_pool = hid_mask = 0;
    hid_t = -1;
    if (load_off || a[2] != 1u || a[0] > 15u)
        return;
    int t = (int)a[0];
    u32 one = voice_cost(t);
    if (!one)                                   /* a stock machine's or MIDI's note: stock's allocation */
        return;
    int n = PER_NOTE[t] > 0 ? PER_NOTE[t] : 1;
    u32 sum = load_fx;
    for (int v = 0; v < 16; v++) {
        u32 c = slot_cost(v);
        cost_was[v] = (u16)c;
        sum += c;
    }
    load_checks++;
    load_last_sum = sum;
    load_last_need = one * (u32)n;
    if (fits_now(sum, one * (u32)n, one)) {
        load_pend += one * (u32)n;              /* (the DSP's next packet will show it) */
        return;
    }
    if (TICK_DUE)                               /* this tick's copy first (the allocator would make it, over ours) */
        TICK_COPY();
    u32 held = HELD, tails = 0;
    for (int v = 0; v < 16; v++) {              /* released voices still sounding, of our machines (2026-11-13) */
        int o = VOICE(v)[1];
        if (!(held & (1u << v)) && o <= 15 && !load_stock[o] && smp_tlm_cost[v] > LOAD_TAIL)
            tails |= 1u << v;
    }
    int own = LIVE_HAS[t] != 0;
    u32 cand = own ? LIVE_MASK[t] : LIVE_POOL;
    u32 keep = cand & tails ? tails : held;     /* a release tail first, else a held voice */
    if (!(cand & keep))                         /* nothing sounding to steal: let it take a free slot (the guard decides) */
        return;
    if (keep == tails)
        load_tails++;
    load_over++;
    need_now = one * (u32)n;
    one_now = one;
    sum_now = sum;
    hid_t = t;
    hid_pool = LIVE_POOL & ~keep;
    LIVE_POOL &= keep;
    if (own) {
        hid_mask = LIVE_MASK[t] & ~keep;
        LIVE_MASK[t] &= keep;
    }
}

/* hooks.S: TAKEN the slots the allocator gave the note, FP the interrupt's frame */
void load_post(u32 taken, u8 *fp)
{
    if (hid_t < 0)
        return;
    LIVE_POOL |= hid_pool & ~taken;             /* the hidden free slots back for the tick's other notes */
    if (hid_mask)
        LIVE_MASK[hid_t] |= hid_mask & ~taken;
    u32 sum = sum_now, freed = 0;
    for (int v = 0; v < 16; v++)
        if (taken & (1u << v)) {
            sum -= cost_was[v];                 /* what the stolen voices cost */
            freed += cost_was[v];
        }
    int room, by_room = room_now(&room);
    u32 now = TICK;
    while (by_room ? room_asked(need_now, one_now) > room + (int)freed
                   : sum + need_now > LOAD_AVAIL) {   /* a heavy note: the next oldest held voices released */
        int best = -1;
        u32 at = 0;
        for (int v = 0; v < 16; v++) {
            u32 b = 1u << v;
            u32 st = *(volatile u32 *)(VOICE(v) + 8);
            int own = VOICE(v)[1];
            if (!(HELD & b) || (taken & b) || !cost_was[v] || st >= now || own > 15 || load_stock[own])
                continue;                       /* (a stock machine's slot costs as much released: not this way) */
            if (best < 0 || st < at) {
                best = v;
                at = st;
            }
        }
        if (best < 0)
            break;
        u32 b = 1u << best;
        KEY_UP((u32)best);
        *(volatile u32 *)(fp - 172) &= ~b;
        *(volatile u32 *)(fp - 164) |= b;
        if (VSTATE & b) {
            *(volatile u32 *)(fp - 160) &= ~b;
            *(volatile u32 *)(fp - 168) |= b;
            VSTATE &= ~b;
        }
        GATE_A[best] = 0;
        GATE_B[best] = 0;
        *(volatile u32 *)(VOICE(best) + 12) = 0;
        sum -= cost_was[best];
        freed += cost_was[best];                /* (its release still sounds a while: the guard covers that) */
        taken |= b;                             /* (not picked twice) */
        load_keyups++;
    }
    load_pend += need_now > freed ? need_now - freed : 0;
    hid_t = -1;
}

/* -- the setting: SETTINGS > PERSONALIZE, VOICE BUDGET (after LIVE SELECT's row, made the same way: csrc/msel/live.c) */

#define NEW       ((u32 (*)(u32))0x40120544u)
#define ITEM_CTOR ((void (*)(u32, void *, void *, void *, void *, int, int))0x401173B8u)
#define MENU_ADD  ((void (*)(u32, u32))0x40116BEEu)
#define FN_DTOR   ((void (*)(void *))0x40188366u)
#define REDRAW    ((void (*)(u32))0x4011CA9Au)
#define MGR4      0x400A983Cu

struct fn { u32 store, pad, mgr, inv; };

extern void set_flag_put(u32 bit, int on);      /* jump.c */
extern char load_label[], load_box[];           /* hooks.S */

u32 load_rows __attribute__((section(".data"))) = 0;

int load_on(void)
{
    return !set_flag(SET_BUDGET_OFF);
}

static void load_put(int on)
{
    if (on != load_on())
        set_flag_put(SET_BUDGET_OFF, !on);
}

const char *load_text(void)
{
    return "VOICE BUDGET";
}

void load_yes(u32 **fd)
{
    load_put(!load_on());
    REDRAW((*fd)[0] + 56);
}

void load_delta(u32 **fd, u32 unused, int delta)
{
    (void)unused;
    load_put(load_on() + delta > 0);
    REDRAW((*fd)[0] + 56);
}

static void fn_make(struct fn *f, u32 inv, u32 view)
{
    u32 *c = (u32 *)NEW(4);
    c[0] = view;
    f->store = (u32)c;
    f->pad = 0;
    f->mgr = MGR4;
    f->inv = inv;
}

/* live.c live_row, after LIVE SELECT's row */
void load_row(u32 view)
{
    struct fn f[4];
    u32 item = NEW(0x54);
    fn_make(&f[0], (u32)load_label, view);
    fn_make(&f[1], (u32)load_yes, view);
    fn_make(&f[2], (u32)load_box, view);
    fn_make(&f[3], (u32)load_delta, view);
    ITEM_CTOR(item, &f[0], &f[1], &f[2], &f[3], -1, 8);
    MENU_ADD(view, item);
    for (int i = 3; i >= 0; i--)
        FN_DTOR(&f[i]);
    load_rows++;
}

/* -- the lists' tag: how many voices of a choice fit (informational) --------------------------------------------- */

#define UI_TRACK_NOW (*(volatile u8 *)0x42432A6Cu)   /* the active track (page.c UI_TRACK) */
static char tagbuf[12] __attribute__((section(".data")));

static const char *fits(u32 c)
{
    int t = UI_TRACK_NOW;
    if (load_off || !c || t > 15 || !KIT)
        return 0;
    volatile u8 *s = SOUND(t);
    int f = s[0xDF];
    if (f >= 0 && f < 16)
        c += load_filter[f];
    for (int j = 0; j < 2; j++) {
        int y = ins_sel[t][j];
        if (y < 16 && !(LOAD_BUS_MASK & (1u << y)))
            c += load_ins[y];
    }
    int n = load_fit(c);
    if (n >= LOAD_VOICES)
        return 0;                               /* all 16 fit: the list's own tag */
    if (n <= 0)
        return "DSP FULL";
    int k = 0;
    if (n >= 10)
        tagbuf[k++] = (char)('0' + n / 10);
    tagbuf[k++] = (char)('0' + n % 10);
    const char *w = n == 1 ? " VOICE" : " VOICES";
    while (*w)
        tagbuf[k++] = *w++;
    tagbuf[k] = 0;
    return tagbuf;
}

/* page.c perc_tag: MACHINEDRUM's TYPE list, machine I */
const char *load_tag_md(int i)
{
    return i >= 0 && i < LOAD_MD_N ? fits(load_md[i]) : 0;
}

/* md_page.c mnm_pop_tag: choice C of control J of Monomachine-style machine MI, where the choice is an engine */
const char *load_tag_mnm(int mi, int j, int c)
{
    if (mi == LOAD_MI_PLAITS && j == LOAD_J_PLAITS && c < (int)(sizeof load_plaits / sizeof load_plaits[0]))
        return fits(load_plaits[c]);
    if (mi == LOAD_MI_SOPHIE && j == LOAD_J_SOPHIE && c < (int)(sizeof load_sophie / sizeof load_sophie[0]))
        return fits(load_sophie[c]);
    if (mi == LOAD_MI_A2 && j == LOAD_J_A2 && c < (int)(sizeof load_a2flt / sizeof load_a2flt[0]))
        return fits(load_a2flt[c]);
    if (MNM_MONO >= 0 && mi == MNM_MONO && j == MNM_MONO_J && c < MNM_MONO_N)
        return fits(load_mnm[mnm_mono_place[c]]);
    return 0;
}

