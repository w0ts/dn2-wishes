/* PARA as one voice on the ColdFire (2026-11-16, the User: "i would rather take one bigger voice";
 * docs/paraphonic-onevoice.md). On a PARA track (para.h: ANALOG 2, JUNO, PARA ON) the notes held together play
 * on ONE voice slot: the chord's first note takes a slot from stock's allocator (the LEADER); every later note
 * while the chord is held takes none. It goes into the leader's chord list instead, and the DSP renders it on the
 * leader (dnfw.engines.analog2.para, the list read from the voice's own frame words, pv_out).
 *
 * Stock's own state for a note that takes no slot is the state a muted track's note leaves (the ISR's "no slot"
 * path, 0x400269fa beq 0x40026c4a with d0 = d1 = 0; docs/mute-research.md): no voice record, no held bit, no gate
 * timer, no note bit. So everything about a joined note is ours:
 *   - pv_pre (load_alloc_hook, the note-on's allocator call 0x400269e6): a joining note -> 1, the allocator is not
 *     called; otherwise the leaders still held are hidden from the allocator's live masks for this call (a chord's
 *     slot is never taken while it is held: the User's "re-home", 2026-11-16), and on a PARA track UNISON's voices a
 *     note are set to one for the call (the User: "all the note ... use ONE voice");
 *   - pv_post (after the allocator): the masks and UNISON back; the slot given starts a new chord; a held chord
 *     whose slot was taken all the same (TRACK steal, or every slot a held leader) ends;
 *   - pv_rel (pv_rel_hook, the key-up's allocator call 0x40026d86): a joined note's key-up (stock finds no slot);
 *   - pv_final (hold_final, once a frame, the note-off words): the joined notes' gate timers (as 0x40025f18 counts a
 *     slot's), the ARP's safety net (below), stop-all, PARA turned off; the leader's own note-off kept back while its
 *     chord holds a note, and sent when none is held; then the chord RELEASES (its row still live: the DSP renders
 *     its notes through the release tail) until the DSP reports its slot quiet, and ends;
 *   - pv_out (slide.c's sl_smooth, every frame): each PARA engine voice's row in its own frame words (2026-11-17;
 *     until then the TDM link sent the rows to the pool's DDR, a period or more after the voice's note-on).
 * Nothing here changes stock's allocator or its tables; the masks and UNISON count are put back in the same call.
 *
 * 2026-11-18 (v0.59.1 on the unit: chords never ended, members ended a frame after they joined, a key-up never
 * released a member; docs/paraphonic-onevoice.md section 10, scripts/emu_coupled_paralive.py):
 *   - stock's 0x4002a3a6 (KEYS_HELD) is not "a key is held on track t": it reads the ARP's key list (0x4059d868),
 *     which 0x40029cd4 fills only when the sound's ARP is on (byte 351). With the ARP off it is always 0, so the old
 *     safety net ended every joined key-held note at the next frame (pv_nets = pv_joins on the unit), and pv_rel then
 *     found nothing held. A joined note now ends by its own key-up (pv_rel); the net runs only with the ARP on (whose
 *     key-ups never reach the allocator call 0x40026d86: 0x40029fa6 takes them), when the ARP's list is empty;
 *   - a chord with nothing held ended only when its slot took another note: every frame pv_final, pv_on and stock's
 *     KEYS_HELD ran for it, and its places kept their shadows' DSP pool blocks (16 for all chords; read from the
 *     DSP's code, not measured on the unit: a new chord's notes then find none, a likely part of "only 2 or 3
 *     notes"). It now releases, then ends once the DSP's reports (link.c smp_tlm_cost) say its slot is quiet;
 *   - pv_dirty (set, never read: the TDM link's row sending, gone 2026-11-17) is gone;
 *   - the row: the same work for every PARA engine voice every frame (the User, 2026-11-18: constant load), written
 *     straight into the frame words, its places without branches; bit for bit the row as before. */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef signed char s8;
#define D __attribute__((section(".data")))

#include "para.h"
#include "one.h"

/* stock 1.12 (docs/load-budget.md, docs/paraphonic-onevoice.md) */
#define VOICE(v)    ((volatile u8 *)(0x40288304u + 20u * (u32)(v)))   /* +8 the voice's start stamp */
#define PER_NOTE    ((volatile s8 *)0x4059DA00u)                       /* UNISON: each track's voices a note */
#define LIVE_POOL   (*(volatile u32 *)0x4059D96Cu)
#define LIVE_MASK   ((volatile u32 *)0x4059D970u)
#define LIVE_HAS    ((volatile u8 *)0x4059D9B0u)
#define TICK_DUE    (*(volatile u32 *)0x4059DAFCu)
#define TICK_COPY   ((void (*)(void))0x4002A414u)
#define OWNER       ((volatile u32 *)0x80005308u)                      /* each slot's track */
#define PERIOD      (*(volatile u32 *)0x402A132Cu)                     /* a gate timer's step a period (0x40025f1c) */
#define STOP_ALL    (*(volatile u32 *)0x4058E550u)                     /* 2: stop-all (docs/mute-research.md) */
#define KEYS_HELD   ((int (*)(int))0x4002A3A6u)                        /* the ARP's key list of track t not empty */
#define SOUND_ARP   351                                                /* the sound's ARP on (0x40029cd4 tstb 351(a1)) */
#define LEN_TRACK   0x40288044u                                        /* the gate length tables (0x40026a56..a82) */
#define LEN_STOCK   0x401D8CE4u
#define LEN_MAP     ((u8 *volatile *)0x4058F8D8u)
#define CTX_FLAGS   56
#define CTX_SOUND   44
#define CTX_INDEX   16
#define FLAG_LENMAP (1u << 19)
#define FLAG_OTHER  (1u << 17)                                         /* the other note path (0x40026586): not ours */

pv_chord pv_ch[16] D;                                   /* a chord per slot (its leader); live PV_LIVE or PV_RELEASING */
u8 pv_cur[16] D;                                        /* each track's current chord: its leader + 1, 0 none */
u32 pv_kept D = 0;                                      /* leaders whose own note-off is kept back */
u32 pv_ends D = 0;                                      /* chords ended by the DSP's report (released, then quiet) */
u32 pv_now D = 0;                                       /* the frames counted (pv_final) */
static u32 pv_relat[16] D;                              /* when each chord began to release (smp_periods) */
static u8 pv_quiet[16] D;                               /* each releasing chord's quiet reports in a row */
extern volatile u16 smp_tlm_cost[16];                   /* link.c: the DSP's cost of each slot / 16, its last report */
extern volatile u32 smp_room_at;                        /* link.c: when that report came (periods | 1), 0 never */
extern volatile u32 smp_periods;                        /* link.c: its periods */
/* a releasing chord ends once its slot reports quiet PV_QUIET_N frames in a row, each report made PV_TAIL_WAIT periods
 * or more after the release and at most PV_FRESH periods old. Quiet: the DSP's cost of the slot at most PV_QUIET_COST
 * (/ 16), the telemetry's own "sounding" line (link.c TLM_SOUNDING, 8,000 cycles a block). Measured on the unit
 * (v0.59.1, scratch/unit-now/para-cpu chord2/chord3): an ANALOG 2 PARA slot at rest after its chord 166..230, a held
 * chord of 3-4 notes 1,446..2,807, with single reports of ~309 inside a held chord (so: in a row); one PARA note alone
 * costs about 392 (6,272 cycles, docs/paraphonic-onevoice.md section 8), under the line, but a chord of one note has
 * no other note for the DSP to keep (ending it changes nothing the DSP renders but its own row's chord word); two
 * notes and more (11,631 cycles and up) are over it until the DSP rests the voice. LOAD_TAIL (2,000 cycles) is under
 * the unit's rest cost, so it would never end a chord */
#define PV_TAIL_WAIT  8                                 /* (5 ms) */
#define PV_QUIET_N    48                                /* (32 ms of reports) */
#define PV_FRESH      4
#define PV_QUIET_COST (8000u / 16u)
u32 pv_joins D = 0, pv_starts D = 0, pv_rels D = 0, pv_lens D = 0, pv_nets D = 0, pv_drops D = 0, pv_lost D = 0;
u32 pv_hidden D = 0, pv_taken D = 0;                    /* the emulator reads them */
static u32 hid_pool D = 0, hid_mask D = 0;
static int hid_t D = -1;
static s8 unison D = 0;

static int pv_on(int t)
{
    return para_track(t) && para_value(t) != 0;
}

static int held_any(const pv_chord *c)
{
    for (int k = 0; k < PV_PLACES; k++)
        if (c->e[k].flags & PV_HELD)
            return 1;
    return 0;
}

/* the leaders whose chord holds a note. 2026-11-18 (the User's CPU: a step that starts a note on many tracks calls
 * this once a note): the 16 slots written out, a slot whose chord is not live costs a test and a branch (the loop
 * was 7 instructions a slot); the same slots asked in the same order, the same mask */
#define PV_LEAD(s) if (pv_ch[s].live && held_any(&pv_ch[s])) m |= 1u << (s);
u32 pv_leaders(void)
{
    u32 m = 0;
    PV_LEAD(0) PV_LEAD(1) PV_LEAD(2) PV_LEAD(3) PV_LEAD(4) PV_LEAD(5) PV_LEAD(6) PV_LEAD(7)
    PV_LEAD(8) PV_LEAD(9) PV_LEAD(10) PV_LEAD(11) PV_LEAD(12) PV_LEAD(13) PV_LEAD(14) PV_LEAD(15)
    return m;
}
#undef PV_LEAD

static inline __attribute__((always_inline)) void chord_end(int s)   /* (inline: pv_post writes its slots out) */
{
    pv_chord *c = &pv_ch[s];
    if (c->live && pv_cur[c->track] == s + 1)
        pv_cur[c->track] = 0;
    c->live = 0;
    for (int k = 0; k < PV_PLACES; k++)
        c->e[k].flags = 0;
    pv_kept &= ~(1u << s);
}

/* a note's gate length, as the ISR computes it for a slot (0x40026a48..0x40026a82): the event's LEN byte, else the
 * sound's, through the track's table or stock's. <= 0: no timer (a key held) */
static int len_of(const u8 *ev, const u8 *ctx)
{
    int d = (s8)ev[4];
    if (d < 0)
        d = (s8)(*(u8 *const *)(ctx + CTX_SOUND))[1153];
    const u32 *tbl;
    if (*(const u32 *)(ctx + CTX_FLAGS) & FLAG_LENMAP) {
        d = (s8)LEN_MAP[*(const u32 *)(ctx + CTX_INDEX)][354];
        tbl = (const u32 *)LEN_TRACK;
    } else {
        tbl = (const u32 *)LEN_STOCK;
    }
    return (int)tbl[1 + d];
}

/* the oldest of the chord's sounding notes, its place (-1 none) */
static int oldest(const pv_chord *c)
{
    int best = -1;
    for (int k = 0; k < PV_PLACES; k++)
        if ((c->e[k].flags & PV_SOUND) && (best < 0 || (int)(c->e[k].age - c->e[best].age) < 0))
            best = k;
    return best;
}

static int sounding(const pv_chord *c)
{
    int n = 0;
    for (int k = 0; k < PV_PLACES; k++)
        n += (c->e[k].flags & PV_SOUND) != 0;
    return n;
}

/* a free place for a joined note (1..): never sounding, else dropped longest ago, else the oldest */
static int free_place(const pv_chord *c)
{
    int best = -1;
    for (int k = 1; k < PV_PLACES; k++) {
        const pv_entry *e = &c->e[k];
        if (!(e->flags & PV_SOUND) && !(e->flags & PV_HELD)) {
            if (!(e->flags & PV_USED))
                return k;
            if (best < 0 || (int)(e->age - c->e[best].age) < 0)
                best = k;
        }
    }
    return best;
}

/* a note joins chord S (track T): the same note again restarts its place; else a free place, the chord's oldest
 * sounding note dropped when PARA_NOTES sound already (2026-11-15, the User: "Drop the oldest") */
static void join(int s, int note, int len)
{
    pv_chord *c = &pv_ch[s];
    int k = -1;
    for (int j = 0; j < PV_PLACES; j++)
        if ((c->e[j].flags & PV_USED) && c->e[j].note == note) {
            k = j;
            break;
        }
    if (k < 0) {
        if (sounding(c) >= PARA_NOTES) {
            int o = oldest(c);
            if (o >= 0) {
                c->e[o].flags &= ~(PV_SOUND | PV_HELD);
                pv_drops++;
            }
        }
        k = free_place(c);
        if (k < 0) {                                    /* (every place sounding or fading: the oldest again) */
            k = oldest(c);
            pv_lost++;
            if (k <= 0)
                return;
        }
    }
    pv_entry *e = &c->e[k];
    e->note = (u8)note;
    e->flags = PV_USED | PV_HELD | PV_SOUND | (len > 0 ? PV_TIMED : 0);
    e->seq = (u8)((e->seq + 1u) & 15u);
    e->len = len;
    e->age = ++c->ages;
    e->born = pv_now;
}

extern u32 hold_locked(int t);                          /* hold.c: the slots DRONE HOLD latched for other tracks */
extern u32 hold_lock, hold_nosl;

/* load_alloc_hook: A the allocator's nine arguments (track, note, event type (1 note-on), ...), EV the event, FP
 * the ISR's frame. -> 1: the note joined its track's chord, 2 (2026-11-19): every candidate slot latched by DRONE
 * HOLD for another track; either way the allocator is not called (the ISR's no-slot path) */
int pv_pre(const u32 *a, const u8 *ev, const u8 *fp)
{
    hid_t = -1;
    hid_pool = hid_mask = 0;
    if (a[2] != 1u || a[0] > 15u)
        return 0;
    int t = (int)a[0];
    const u8 *ctx = *(u8 *const *)(fp - 36);
    if (pv_on(t) && !(*(const u32 *)(ctx + CTX_FLAGS) & FLAG_OTHER)) {
        int s = (int)pv_cur[t] - 1;
        if (s >= 0 && pv_ch[s].live && OWNER[s] == (u32)t && held_any(&pv_ch[s])) {
            join(s, (int)(s8)a[1], len_of(ev, ctx));
            pv_joins++;
            return 1;
        }
    }
    if (TICK_DUE)                                       /* this tick's copy first (the allocator would make it, over ours) */
        TICK_COPY();
    u32 lead = pv_leaders();
    u32 lock = hold_locked(t);                          /* 2026-11-19: DRONE HOLD's latches of other tracks, never taken */
    if (lead | lock) {                                  /* a held chord's slot is not taken (the User: "re-home") */
        int own = LIVE_HAS[t] != 0;
        u32 cand = own ? LIVE_MASK[t] : LIVE_POOL;
        if (lock) {
            hold_lock++;
            if ((cand & lock) && !(cand & ~lock)) {     /* nothing but latches: no slot (the ISR's no-slot path) */
                hold_nosl++;
                return 2;
            }
            cand &= ~lock;
        }
        if (!(cand & ~lead)) {                          /* every candidate a held chord: the oldest may go */
            int best = -1;
            u32 at = 0;
            for (int v = 0; v < 16; v++)
                if ((cand & lead & (1u << v))
                    && (best < 0 || (int)(*(volatile u32 *)(VOICE(v) + 8) - at) < 0)) {
                    best = v;
                    at = *(volatile u32 *)(VOICE(v) + 8);
                }
            if (best >= 0)
                lead &= ~(1u << best);
        }
        u32 hide = lead | lock;
        hid_t = t;
        hid_pool = LIVE_POOL & hide;
        LIVE_POOL &= ~hide;
        if (own) {
            hid_mask = LIVE_MASK[t] & hide;
            LIVE_MASK[t] &= ~hide;
        }
        if ((hid_pool | hid_mask) & lead)
            pv_hidden++;
    }
    unison = 0;
    if (pv_on(t) && PER_NOTE[t] > 1) {                  /* PARA: one voice a chord, whatever UNISON says */
        unison = PER_NOTE[t];
        PER_NOTE[t] = 1;
    }
    return 0;
}

/* a taken slot's chord ends (pv_post): inline, so a taken slot costs no call (the worst case, every slot taken, no
 * dearer than the loop was) */
static inline __attribute__((always_inline)) void leave(int s)
{
    if (held_any(&pv_ch[s]))
        pv_taken++;
    chord_end(s);
}

/* load_alloc_hook, after the allocator: TAKEN the slots it gave, A its arguments, EV the event, FP the ISR's frame */
void pv_post(u32 taken, const u32 *a, const u8 *ev, const u8 *fp)
{
    int t = (int)a[0];
    if (hid_t >= 0) {
        LIVE_POOL |= hid_pool & ~taken;
        if (hid_mask)
            LIVE_MASK[hid_t] |= hid_mask & ~taken;
        hid_t = -1;
    }
    if (unison) {
        PER_NOTE[t] = unison;
        unison = 0;
    }
    if (a[2] != 1u || t < 0 || t > 15)
        return;
    /* a slot that takes a new note leaves its chord (2026-11-18, the User's CPU: the 16 slots written out, a slot
     * not taken costs a bit test and a branch; the same slots in the same order, the same work for a taken one) */
#define PV_TAKE(s) if ((taken & (1u << (s))) && pv_ch[s].live) leave(s);
    PV_TAKE(0) PV_TAKE(1) PV_TAKE(2) PV_TAKE(3) PV_TAKE(4) PV_TAKE(5) PV_TAKE(6) PV_TAKE(7)
    PV_TAKE(8) PV_TAKE(9) PV_TAKE(10) PV_TAKE(11) PV_TAKE(12) PV_TAKE(13) PV_TAKE(14) PV_TAKE(15)
#undef PV_TAKE
    const u8 *ctx = *(u8 *const *)(fp - 36);
    if (!taken || !pv_on(t) || (*(const u32 *)(ctx + CTX_FLAGS) & FLAG_OTHER))
        return;
    int s = 0;
    while (!(taken & (1u << s)))                        /* (one slot: UNISON is one on a PARA track) */
        s++;
    pv_chord *c = &pv_ch[s];
    c->live = PV_LIVE;
    c->track = (u8)t;
    c->seq = (u8)((c->seq + 1u) & 15u);
    c->ages = 0;
    for (int k = 0; k < PV_PLACES; k++)
        c->e[k].flags = 0;
    pv_entry *e = &c->e[0];                             /* place 0: the leader's own note (its gate is stock's) */
    e->note = (u8)(s8)a[1];
    e->flags = PV_USED | PV_HELD | PV_SOUND;
    e->seq = (u8)((e->seq + 1u) & 15u);
    e->len = 0;
    e->age = ++c->ages;
    e->born = pv_now;
    pv_cur[t] = (u8)(s + 1);
    pv_kept &= ~(1u << s);
    pv_starts++;
    (void)ev;
}

/* pv_rel_hook: the key-up's allocator call (0x40026d86), before stock: A its arguments (track, note, type not 1).
 * A joined note of the track's held chords no longer held (stock then finds no slot for it and gives back nothing) */
void pv_rel(const u32 *a)
{
    if (a[0] > 15u)
        return;
    int t = (int)a[0], note = (int)(s8)a[1];
    for (int s = 0; s < 16; s++) {
        pv_chord *c = &pv_ch[s];
        if (c->live != PV_LIVE || c->track != t)
            continue;
        for (int k = 1; k < PV_PLACES; k++)
            if ((c->e[k].flags & PV_HELD) && c->e[k].note == note) {   /* (timed or not: stock releases a slot so) */
                c->e[k].flags &= ~PV_HELD;
                pv_rels++;
            }
    }
}

/* a releasing chord's slot: one more quiet report in a row (PV_QUIET_N of them: the chord's tail is over), or a busy
 * one (the count starts again). A report older than PV_FRESH periods or made before the release counts neither way */
static inline __attribute__((always_inline)) int tail_over(int s)
{
    u32 at = smp_room_at;
    if ((int)(at - pv_relat[s]) < PV_TAIL_WAIT || smp_periods - at > PV_FRESH)
        return 0;
    if (smp_tlm_cost[s] > PV_QUIET_COST) {
        pv_quiet[s] = 0;
        return 0;
    }
    return ++pv_quiet[s] >= PV_QUIET_N;
}

/* hold_final, once a frame: OFF36 the frame's note-off word (+36), W40 the filter's (+40). -> the new +36 */
u32 pv_final(u32 off36, u32 *w40)
{
    pv_now++;
    int stop = STOP_ALL == 2;
    for (int s = 0; s < 16; s++) {
        pv_chord *c = &pv_ch[s];
        if (!c->live)
            continue;
        if (c->live != PV_LIVE) {                       /* releasing: it ends when the DSP says its slot is quiet */
            if (tail_over(s)) {
                chord_end(s);
                pv_ends++;
            }
            continue;
        }
        u32 b = 1u << s;
        int t = c->track;
        const u8 *snd = para_sound(t);                  /* (pv_on, the sound read once) */
        int on = snd && para_engine((s8)snd[PARA_SOUND_TYPE])
                 && *(const u16 *)(snd + PARA_SOUND_VALUES + 2u * PARA_SLOT) >> 8;
        u32 held = 0;
        int gone = stop || !on || OWNER[s] != (u32)t;   /* stop-all, PARA off, the machine changed, the slot lost */
        if (gone) {
            for (int k = 0; k < PV_PLACES; k++)
                c->e[k].flags &= ~PV_HELD;
        } else {
            if (off36 & b)                              /* the leader's own note ended (its key, its gate, a release) */
                c->e[0].flags &= ~PV_HELD;
            held = c->e[0].flags & PV_HELD;
            /* the ARP's net: with the ARP on, its notes' key-ups go to the ARP's list (0x40029fa6), never to the
             * allocator's key-up call: a key-held joined note ends when that list is empty */
            int net = snd[SOUND_ARP] && !KEYS_HELD(t);
            for (int k = 1; k < PV_PLACES; k++) {
                pv_entry *e = &c->e[k];
                u32 f = e->flags;
                if (!(f & PV_HELD))
                    continue;
                if (f & PV_TIMED) {                     /* a sequenced note: its gate timer (0x40025f18's step) */
                    if (e->born != pv_now - 1u) {       /* (counted from the next frame on, as a slot's) */
                        e->len -= (int)PERIOD;
                        if (e->len <= 0) {
                            f &= ~PV_HELD;
                            pv_lens++;
                        }
                    }
                } else if (net) {
                    f &= ~PV_HELD;
                    pv_nets++;
                }
                e->flags = (u8)f;
                held |= f & PV_HELD;
            }
        }
        if (held) {                                     /* the chord plays on: the leader's note-off kept back */
            if (off36 & b)
                pv_kept |= b;
            off36 &= ~b;
            *w40 &= ~b;
            continue;
        }
        if (pv_cur[t] == s + 1)
            pv_cur[t] = 0;                              /* (no further joins: the next note starts a chord) */
        if (pv_kept & b) {                              /* every note ended: the chord's note-off now */
            off36 |= b;
            *w40 |= b;
            pv_kept &= ~b;
        }
        if (gone) {
            chord_end(s);                               /* (its row zero: the DSP's shadows fade out) */
        } else {
            c->live = PV_RELEASING;                     /* its row as it is: the DSP plays the release tail */
            pv_relat[s] = smp_periods;
            pv_quiet[s] = 0;
        }
    }
    return off36;
}

/* the DSP's row of chord C (dnfw.engines.analog2.para PV_TABLE), halfword i into O[i], 2 PV_ROW_WORDS halfwords:
 * halfword 0 the chord (bit 15 live, its seq, the leader's note), then each place's (offset from the leader's note,
 * held, sounding, used, seq), then a spare 0. Every place the same instructions, no branch (the User, 2026-11-18: the
 * same work every frame, live chord or not): a place never used gives 0 by its USED mask, and so does every place of
 * a chord not live (its flags all 0: chord_end and the start clear them, .data starts at 0; the 2026-11-17 code's
 * "live ?" test per place is that mask). Bit for bit the row of 2026-11-17's
 * place_word: off & 0xFF | HELD 0x100 | SOUND 0x200 | USED 0x400 | seq << 12, HELD << 7 = 0x100, SOUND << 7 = 0x200 */
_Static_assert(PV_HELD << 7 == 0x100u && PV_SOUND << 7 == 0x200u && PV_USED == 1u && PV_PLACES == 10,
               "the row's place bits from the flags");
static inline __attribute__((always_inline)) void row_out(const pv_chord *c, volatile u16 *o)
{
    u32 live = -(u32)(c->live != 0);
    u32 n0 = c->e[0].note;
    o[0] = (u16)((0x8000u | ((u32)c->seq << 8) | (n0 & 0x7Fu)) & live);
#define PV_PLACE(k) { const pv_entry *e = &c->e[k]; u32 f = e->flags; \
        o[1 + (k)] = (u16)(((((u32)e->note - n0) & 0xFFu) | ((f & (PV_HELD | PV_SOUND)) << 7) | 0x400u \
                            | ((u32)e->seq << 12)) & -(f & PV_USED)); }
    PV_PLACE(0) PV_PLACE(1) PV_PLACE(2) PV_PLACE(3) PV_PLACE(4)
    PV_PLACE(5) PV_PLACE(6) PV_PLACE(7) PV_PLACE(8) PV_PLACE(9)
#undef PV_PLACE
    o[11] = 0;
}

/* 2026-11-17 (the User: "shouldnt voice just one dsp voice if one exist already?"; v0.57.1 on the unit: the row came
 * over the TDM link a period or more after the leader's note-on, and only the lowest note sounded): every frame, after
 * the smoother (sl_smooth, as the velocity), each voice whose sound is ANALOG 2 or JUNO gets its row in its own frame
 * words: halfword i in frame slot PV_ROW_SLOT + i (FM TONE's records; none of our machines reads them,
 * dnfw.engines.analog2.para ROW_SLOT). The DSP reads the voice and its pitches from the same frame. OUT: the
 * smoother's output (the frame's source), word 17 + 101 v + slot */
#define PV_ROW_SLOT 50u
#define PV_VSOUND(v) (*(u8 *volatile *)(0x800052A8u + 4u * (u32)(v)))   /* voice -> sound */
/* (2026-11-19, the User's CPU: 4 % of it on the unit with every voice on ANALOG 2 and no chord) the same words, by
 * the chord's state: a live chord's row without the live mask (it is all ones); a chord not live whose places were
 * never used (every place's USED clear, live 0: row_out's every word is 0) as twelve zeros, without reading its
 * places' notes; anything else row_out's way. Bit for bit row_out's words in any state; a live chord's row a few
 * instructions cheaper than before (the worst frame, 16 chords, goes down too) */
static inline __attribute__((always_inline)) void places_out(const pv_chord *c, volatile u16 *o, u32 n0)
{
#define PV_PLACE(k) { const pv_entry *e = &c->e[k]; u32 f = e->flags; \
        o[1 + (k)] = (u16)(((((u32)e->note - n0) & 0xFFu) | ((f & (PV_HELD | PV_SOUND)) << 7) | 0x400u \
                            | ((u32)e->seq << 12)) & -(f & PV_USED)); }
    PV_PLACE(0) PV_PLACE(1) PV_PLACE(2) PV_PLACE(3) PV_PLACE(4)
    PV_PLACE(5) PV_PLACE(6) PV_PLACE(7) PV_PLACE(8) PV_PLACE(9)
#undef PV_PLACE
    o[11] = 0;
}

void pv_out(volatile u16 *out)
{
    volatile u16 *o = out + 17u + PV_ROW_SLOT;
    const pv_chord *c = pv_ch;
    for (int v = 0; v < 16; v++, o += 101, c++) {
        const u8 *snd = PV_VSOUND(v);
        if (!snd || !para_engine((s8)snd[PARA_SOUND_TYPE]))
            continue;
        u32 n0 = c->e[0].note;
        if (c->live) {
            o[0] = (u16)(0x8000u | ((u32)c->seq << 8) | (n0 & 0x7Fu));
            places_out(c, o, n0);
        } else if ((c->e[0].flags | c->e[1].flags | c->e[2].flags | c->e[3].flags | c->e[4].flags | c->e[5].flags
                    | c->e[6].flags | c->e[7].flags | c->e[8].flags | c->e[9].flags) & PV_USED) {
            o[0] = 0;
            places_out(c, o, n0);
        } else {
            o[0] = 0; o[1] = 0; o[2] = 0; o[3] = 0; o[4] = 0; o[5] = 0;
            o[6] = 0; o[7] = 0; o[8] = 0; o[9] = 0; o[10] = 0; o[11] = 0;
        }
    }
}

/* slot S's row as PV_ROW_WORDS words (halfword 2 j low, 2 j + 1 high): the emulator's check reads it so */
void pv_row(int s, u32 *w)
{
    u16 h[2 * PV_ROW_WORDS];
    row_out(&pv_ch[s], h);
    for (int j = 0; j < PV_ROW_WORDS; j++)
        w[j] = (u32)h[2 * j] | (u32)h[2 * j + 1] << 16;
}
