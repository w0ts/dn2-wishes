/* PROFILE (test channel command 43, docs/remote-ui-protocol.md): a PC-sampling profiler of the ColdFire,
 * disarmed by default. It records, for each sample, the interrupted PC, the interrupted SR (its IPL says
 * task code, 0, or inside an interrupt, 1..5), the running task's TCB, and how late the sample was taken.
 * The host maps the PCs to functions (tools/dn2tools profile.py) and reports what the CPU spends its
 * time on, the idle task's spin included (docs/remote-ui.md, "The CPU profiler").
 *
 * Two sources, chosen at START:
 *
 *   1 TIMER  DMA timer 0's reference compare, vector 96, at interrupt level 6 (prof.S prof_isr). Measured
 *            in the OS 1.12 image (2026-11-11): DTIM0 is the 132 MHz free-running counter the OS reads at
 *            ten sites (0xfc07000c: the encoder stamps, the meter) and never writes; its interrupt (INTC0
 *            source 32: ICR 0xfc048060, vector 0x40000180) is never set up by stock, whose vector 96 stays
 *            the default handler 0x40001252. The OS's own timers are all taken: PIT0 the time slice, PIT1 a
 *            microsecond delay, PIT2 the timer wheel, PIT3 the display, DTIM1 a sleep, DTIM2 an external
 *            clock count, DTIM3 the UI tick. So the counter keeps running untouched (free run: the
 *            reference does not restart it) and only its compare is used: each sample sets the next
 *            reference at now + period +- jitter. Level 6 is above the audio interrupt (level 5, vector
 *            191), so samples land inside it; level 7 is not used: the context switch (0x40000410) and
 *            others write below SP with the mask at 6, which a non-maskable interrupt would overwrite.
 *            Invisible: code that runs with the mask at 6 or 7 (every 0x2700 critical section, the
 *            level-6 and level-7 handlers: vectors 66, 168, 170, 209, 221). A sample due inside such a
 *            section is taken when it ends; its lateness is recorded (the record's `late`, in DTIM0 ticks).
 *   2 AUDIO  the audio interrupt itself (link hook, csrc/sampler/hooks.S smp_tdm_hook): the PC it
 *            interrupted, every DIV-th frame (1,500 frames a second). A fallback: the audio interrupt's own
 *            time (about half the CPU) and anything at level 5..7 is invisible, and the samples are in
 *            step with the audio frames (work locked to them aliases).
 *
 * START refuses the timer (status 6, the reason in the data) unless DTIM0 is as the boot left it on the
 * unit: running from the bus clock (RST, CLK 01), free running (FRR 0), no reference interrupt or DMA
 * (ORRI 0, DMAEN 0), its INTC source unset (ICR 0) and masked, vector 96 the stock default. STOP (or a full
 * ring) puts every register and the vector back. The ring STOPS when full (it never wraps): CAP samples,
 * then the timer interrupt is switched off by the handler itself.
 *
 * Every word here lives in PROF_RAM (RAM above BSS, declared by dnfw.mods.waverider.ram; the chunk has no
 * BSS), first written by START: before it, STATUS reports the block as never started (no magic). Writes:
 * that block, DTIM0's DTRR / DTER / DTMR.ORRI, INTC0's ICR32 / SIMR / CIMR, vector 96. Nothing else. */
#include "devtest.h"

#define NOJT __attribute__((optimize("no-jump-tables")))

#define FRAMES (*(volatile u32 *)0x4058F8D4u)             /* audio frames, 1,500 a second */
#define CUR_TCB (*(volatile u32 *)0x4664BCDCu)            /* the running task's TCB (csrc/meter/hooks.S) */
#define DTMR0 (*(volatile u16 *)0xFC070000u)
#define DTXMR0 (*(volatile u8 *)0xFC070002u)
#define DTER0 (*(volatile u8 *)0xFC070003u)
#define DTRR0 (*(volatile u32 *)0xFC070004u)
#define DTCN0 (*(volatile u32 *)0xFC07000Cu)
#define ICR32 (*(volatile u8 *)0xFC048060u)               /* INTC0 source 32: DTIM0 */
#define IMRH0 (*(volatile u32 *)0xFC048008u)              /* bit 0: source 32 masked */
#define SIMR0 (*(volatile u8 *)0xFC04801Cu)               /* write 32: mask source 32 */
#define CIMR0 (*(volatile u8 *)0xFC04801Du)               /* write 32: unmask it */
#define VEC96 (*(volatile u32 *)0x40000180u)              /* VBR 0x40000000 (0x400019b0) + 4 * 96 */
#define VEC191 (*(volatile u32 *)0x400002FCu)             /* the audio interrupt's vector */
#define STOCK_DEFAULT 0x40001252u                         /* what 0x40001992 puts in all 256 vectors */
#define AUDIO_ISR 0x40025E36u

#define BUS_HZ 132000000u                                 /* DTIM0's tick (the OS's own 10 s test: 1,319,999,999) */
#define RST 0x0001u
#define FRR 0x0008u
#define ORRI 0x0010u
#define CLK 0x0006u
#define CLK_BUS 0x0002u
#define REF 0x02u
#define LEVEL 6u
#define SRC 32u

#define REC_WORDS 3u                                      /* u32 pc, u32 tcb, u16 sr, u16 late */
#define CAP 65536u
#define HEAD 64u                                          /* words of state before the ring */
#define P ((volatile u32 *)PROF_RAM)
#define RING ((volatile u32 *)PROF_RAM + HEAD)
_Static_assert((HEAD + CAP * REC_WORDS) * 4u <= PROF_BYTES, "the profiler's ring fits its RAM");

enum { W_MAGIC, W_STATE, W_SOURCE, W_N, W_PERIOD, W_DUE, W_LFSR, W_T0, W_T1, W_F0, W_F1, W_ISR_T,
       W_FIRES, W_LATE, W_LATE_MAX, W_DROPPED, W_SAVED_RR, W_SAVED_ICR, W_DIV, W_DIV_N, W_WHY, W_STARTS,
       W_AUDIO_GATE, W_WORDS };
_Static_assert(W_AUDIO_GATE == 22, "hooks.S tests PROF_RAM + 88");
_Static_assert(W_WORDS <= HEAD, "the profiler's state");
#define MAGIC 0x50524631u                                 /* 'PRF1' */
#define AUDIO_GATE 0x50524641u                            /* 'PRFA': hooks.S calls prof_audio while it is here */
enum { S_OFF, S_RUN, S_FULL, S_STOPPED };
enum { SRC_NONE, SRC_TIMER, SRC_AUDIO };
/* START's refusals (status 6, the data's `why`) */
enum { WHY_NONE, WHY_TIMER_OFF, WHY_FRR, WHY_TIMER_USED, WHY_INTC_USED, WHY_VECTOR, WHY_RATE, WHY_SOURCE };

#define ST_OK 0
#define ST_ARGS 2
#define ST_BUSY 5
#define ST_RANGE 6

extern void prof_isr(void);                               /* prof.S */

static inline u32 irq_off(void)
{
    u32 sr;
    __asm__ volatile ("move.w %%sr, %0\n\tmove.w #0x2700, %%sr" : "=d"(sr) : : "memory");
    return sr;
}

static inline void irq_restore(u32 sr)
{
    __asm__ volatile ("move.w %0, %%sr" : : "d"(sr) : "memory");
}

static void put32(u8 *p, u32 v)
{
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
}

static u32 get32(const u8 *p)
{
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

/* the timer interrupt off and everything as START found it (interrupts masked by the caller or at level 6):
 * the source masked first, so a request already latched can never reach the restored default vector */
static void timer_off(void)
{
    SIMR0 = SRC;
    DTMR0 = (u16)(DTMR0 & ~ORRI);
    DTER0 = REF;
    DTRR0 = P[W_SAVED_RR];
    ICR32 = (u8)P[W_SAVED_ICR];
    if (VEC96 == (u32)prof_isr)
        VEC96 = STOCK_DEFAULT;
}

/* (2026-11-18) PROF_RAM outlives a restart that keeps the RAM; the timer, its vector and the frame clock do not. A run
 * left "running" by the last load is not this load's: it is stopped (its samples kept for READ), so the audio
 * interrupt stops recording into it (W_AUDIO_GATE) and START is not refused as busy. prof_mine is code data, 0 after
 * every load; START sets it */
u32 prof_mine __attribute__((section(".data"))) = 0;

static void stale_run_stopped(void)
{
    if (!prof_mine && P[W_MAGIC] == MAGIC && P[W_STATE] == S_RUN) {
        P[W_STATE] = S_STOPPED;
        P[W_AUDIO_GATE] = 0;
    }
}

/* one sample: FRAME is the exception frame (u16 format/vector, u16 SR, u32 PC); LATE in DTIM0 ticks */
static void record(const volatile u16 *frame, u32 late)
{
    if (P[W_STATE] != S_RUN) {
        P[W_DROPPED]++;
        return;
    }
    u32 n = P[W_N];
    volatile u32 *r = RING + n * REC_WORDS;
    r[0] = *(const volatile u32 *)(frame + 2);
    r[1] = CUR_TCB;
    r[2] = (u32)frame[1] << 16 | (late > 0xFFFFu ? 0xFFFFu : late);
    P[W_N] = ++n;
    if (n >= CAP) {                                       /* full: the ring stops */
        P[W_STATE] = S_FULL;
        P[W_AUDIO_GATE] = 0;
        P[W_T1] = DTCN0;
        P[W_F1] = FRAMES;
        if (P[W_SOURCE] == SRC_TIMER)
            timer_off();
    }
}

/* prof.S prof_isr, vector 96, at level 6: DTIM0 reached its reference */
void prof_tick(const volatile u16 *frame)
{
    u32 t = DTCN0;
    DTER0 = REF;                                          /* the request is cleared */
    u32 per = P[W_PERIOD], l = P[W_LFSR];
    l = (l >> 1) ^ (-(l & 1u) & 0xB400u);                 /* 16-bit Galois LFSR: jitter of +-period/16 */
    P[W_LFSR] = l;
    u32 late = t - P[W_DUE];
    u32 due = t + per - (per >> 4) + (((l & 0xFFFFu) >> 8) * (per >> 3) >> 8);   /* no overflow: 255 x 1.65 M */
    P[W_DUE] = due;
    if (P[W_STATE] == S_RUN)
        DTRR0 = due;
    P[W_FIRES]++;
    if (late > per)
        P[W_LATE]++;
    if (late > P[W_LATE_MAX] && late < 0x80000000u)
        P[W_LATE_MAX] = late;
    record(frame, late);
    P[W_ISR_T] += DTCN0 - t;                              /* this handler's own time, its entry and rte aside */
}

/* hooks.S smp_tdm_hook, inside the audio interrupt, while W_AUDIO_GATE holds AUDIO_GATE (a load and a
 * compare a frame otherwise): FRAME is the audio interrupt's exception frame (its link %fp + 4) */
void prof_audio(const volatile u16 *frame)
{
    stale_run_stopped();
    if (P[W_MAGIC] != MAGIC || P[W_STATE] != S_RUN || P[W_SOURCE] != SRC_AUDIO)
        return;                                           /* RAM above BSS holds anything at power-on */
    if (++P[W_DIV_N] < P[W_DIV])
        return;
    P[W_DIV_N] = 0;
    P[W_FIRES]++;
    record(frame, 0);
}

static u32 timer_unusable(void)
{
    u16 m = DTMR0;
    if (!(m & RST) || (m & CLK) != CLK_BUS)
        return WHY_TIMER_OFF;
    if (m & FRR)
        return WHY_FRR;
    if ((m & ORRI) || (DTXMR0 & 0x80u))
        return WHY_TIMER_USED;
    if ((ICR32 & 7u) || !(IMRH0 & 1u))
        return WHY_INTC_USED;
    if (VEC96 != STOCK_DEFAULT && VEC96 != (u32)prof_isr)
        return WHY_VECTOR;
    return WHY_NONE;
}

static u32 start(u32 source, u32 rate)
{
    stale_run_stopped();
    if (P[W_MAGIC] == MAGIC && P[W_STATE] == S_RUN)
        return ST_BUSY;
    if (source != SRC_TIMER && source != SRC_AUDIO) {
        P[W_WHY] = WHY_SOURCE;
        return ST_ARGS;
    }
    if (rate < 10u || rate > (source == SRC_TIMER ? 10000u : 1500u)) {
        P[W_WHY] = WHY_RATE;
        return ST_ARGS;
    }
    u32 why = source == SRC_TIMER ? timer_unusable() : WHY_NONE;
    if (why) {
        if (P[W_MAGIC] != MAGIC) {                        /* the block's first use: a clean status */
            for (u32 k = 0; k < HEAD; k++)
                P[k] = 0;
            P[W_MAGIC] = MAGIC;
        }
        P[W_WHY] = why;
        return ST_RANGE;
    }
    u32 starts = P[W_MAGIC] == MAGIC ? P[W_STARTS] : 0;
    for (u32 k = 0; k < HEAD; k++)
        P[k] = 0;
    P[W_MAGIC] = MAGIC;
    P[W_STARTS] = starts + 1;
    P[W_SOURCE] = source;
    P[W_PERIOD] = source == SRC_TIMER ? BUS_HZ / ((DTMR0 >> 8) + 1u) / rate : BUS_HZ / rate;   /* the prescaler (PS + 1) */
    P[W_DIV] = source == SRC_AUDIO ? 1500u / rate : 0;
    P[W_LFSR] = 0xACE1u ^ (DTCN0 & 0xFFFFu) ^ FRAMES;
    if (!(P[W_LFSR] & 0xFFFFu))
        P[W_LFSR] = 0xACE1u;
    u32 sr = irq_off();
    P[W_T0] = DTCN0;
    P[W_F0] = FRAMES;
    prof_mine = 1;
    P[W_STATE] = S_RUN;
    if (source == SRC_TIMER) {
        P[W_SAVED_RR] = DTRR0;
        P[W_SAVED_ICR] = ICR32;
        VEC96 = (u32)prof_isr;
        P[W_DUE] = DTCN0 + P[W_PERIOD];
        DTRR0 = P[W_DUE];
        DTER0 = REF;                                      /* a REF left from an earlier pass is not a sample */
        ICR32 = LEVEL;
        DTMR0 = (u16)(DTMR0 | ORRI);
        CIMR0 = SRC;
    } else {
        P[W_AUDIO_GATE] = AUDIO_GATE;
    }
    irq_restore(sr);
    return ST_OK;
}

static void stop(void)
{
    stale_run_stopped();
    if (P[W_MAGIC] != MAGIC)
        return;
    u32 sr = irq_off();
    if (P[W_STATE] == S_RUN) {
        P[W_STATE] = S_STOPPED;
        P[W_AUDIO_GATE] = 0;
        P[W_T1] = DTCN0;
        P[W_F1] = FRAMES;
        if (P[W_SOURCE] == SRC_TIMER)
            timer_off();
    }
    irq_restore(sr);
}

/* STATUS: u8 state, u8 source, u8 why, u8 record bytes, then u32 x 17 */
static u32 status(u8 *rp, u32 r)
{
    stale_run_stopped();
    int ok = P[W_MAGIC] == MAGIC;
    u32 running = ok && P[W_STATE] == S_RUN;
    rp[r++] = ok ? (u8)P[W_STATE] : S_OFF;
    rp[r++] = ok ? (u8)P[W_SOURCE] : SRC_NONE;
    rp[r++] = ok ? (u8)P[W_WHY] : WHY_NONE;
    rp[r++] = REC_WORDS * 4u;
    const u32 w[17] = {
        ok ? P[W_N] : 0, CAP, ok ? P[W_PERIOD] : 0,
        ok ? P[W_T0] : 0, running || !ok ? DTCN0 : P[W_T1],
        ok ? P[W_F0] : 0, running || !ok ? FRAMES : P[W_F1],
        ok ? P[W_ISR_T] : 0, ok ? P[W_FIRES] : 0, ok ? P[W_LATE] : 0, ok ? P[W_LATE_MAX] : 0,
        ok ? P[W_DROPPED] : 0,
        (u32)DTMR0 << 16 | (u32)DTXMR0 << 8 | DTER0, DTRR0,
        (u32)ICR32 << 24 | (IMRH0 & 1u) << 16 | (ok ? P[W_STARTS] & 0xFFFFu : 0), VEC96,
        (u32)RING,
    };
    for (u32 k = 0; k < 17; k++) {
        put32(rp + r, w[k]);
        r += 4;
    }
    return r;
}

/* READ u32 from -> u32 samples, u32 from, u8 n (<= 12), n x 12 bytes */
static u32 read_ring(u32 from, u8 *rp, u32 r)
{
    u32 total = P[W_MAGIC] == MAGIC ? P[W_N] : 0;
    if (from > total)
        from = total;
    u32 m = total - from > 12u ? 12u : total - from;
    put32(rp + r, total); r += 4;
    put32(rp + r, from); r += 4;
    rp[r++] = (u8)m;
    for (u32 j = 0; j < m; j++) {
        const volatile u32 *q = RING + (from + j) * REC_WORDS;
        put32(rp + r, q[0]); r += 4;
        put32(rp + r, q[1]); r += 4;
        put32(rp + r, q[2]); r += 4;
    }
    return r;
}

/* the command 43 (devtest.c dt_rx): RQ[3] the sub-command: 0 STATUS, 1 START u8 source u32 rate, 2 STOP,
 * 3 CLEAR, 4 READ u32 from */
NOJT u32 prof_rx(const u8 *rq, u32 n, u8 *rp, u32 r, u8 *st)
{
    u32 sub = n >= 4 ? rq[3] : 0xFFu;
    stale_run_stopped();
    if (sub == 0) {
        return status(rp, r);
    } else if (sub == 1) {
        *st = n >= 9 ? (u8)start(rq[4], get32(rq + 5)) : ST_ARGS;
        return status(rp, r);
    } else if (sub == 2) {
        stop();
        return status(rp, r);
    } else if (sub == 3) {
        if (P[W_MAGIC] == MAGIC && P[W_STATE] == S_RUN)
            *st = ST_BUSY;
        else if (P[W_MAGIC] == MAGIC) {
            P[W_N] = 0;
            P[W_STATE] = S_OFF;
        }
        return status(rp, r);
    } else if (sub == 4 && n >= 8) {
        return read_ring(get32(rq + 4), rp, r);
    }
    *st = ST_ARGS;
    return r;
}
