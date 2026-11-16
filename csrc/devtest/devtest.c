/* The test channel on the ColdFire (2026-11-11, docs/remote-ui.md; the wire format is
 * docs/remote-ui-protocol.md). A TEST BUILD only: it lets a computer on USB read the unit and, once
 * armed, press its keys. Nothing here writes flash, storage or the frame.
 *
 *   dt_rx    the SysEx commands 33..42, from link.c smp_rx (the MIDI input task). Reads, the switch
 *            words (whitelist.c), the arm handshake, and the key events queued for dt_poll.
 *   dt_poll  once a UI pass (page.c wr_poll, the UI task): plays the queued key and encoder events when
 *            they fall due, lets every key go at its time, disarms after ARMTIME seconds of silence.
 *
 * The keys go in where the panel's own bytes go (measured in the OS 1.12 image, 2026-11-11): the panel
 * controller's UART8 bytes reach the callback 0x4011ffbc, which hands a button byte (tag 2, a channel's
 * whole 8-bit state) to 0x4011fc8c(channel, mask) and an encoder byte (tag 3, a signed delta) to
 * 0x4011ff0c(channel, delta). Those two compare with the channel's last state (0x445a2e30 + channel)
 * and post the UI's events through the OS queue (0x40001896, which masks interrupts itself and signals
 * the UI task by the forced software interrupt). dt_poll calls the same two with interrupts masked, so
 * no UART interrupt runs them halfway through ours; the injected bit is ORed into (or cleared from) the
 * channel's real state, so a key held on the panel stays held.
 *
 * Time is the panel module's tick (0x466768b0, bumped by its timer callback 0x4011f8bc), the clock the
 * UI's hold and double-press tests use. It WRAPS: the callback takes 4,096 off it once it passes 4,095
 * (0x4011f9aa; about every 34 s on the unit, 121 ticks a second, measured 2026-11-11), so everything here runs
 * on `mono`, the tick unwrapped (stepped every UI pass, far more often than a wrap). Its rate is measured
 * against the audio frames (1,500 a second) once they run; until then it is taken as 1,000 a second (the
 * emulator runs no audio interrupt). */
#include "devtest.h"

#define D __attribute__((section(".data")))
#define NOJT __attribute__((optimize("no-jump-tables")))

#define FRAMES (*(volatile u32 *)0x4058F8D4u)                     /* audio frames, 1,500 a second */
#define TICK (*(volatile u32 *)0x466768B0u)                       /* the panel module's tick, 0..4095 */
#define TICK_MASK 0xFFFu
/* the panel's two buffers' pointers. panel_diff (0x40131fd2) diffs the just-drawn FRONT against BACK, sends the
 * changes to the glass, and swaps them: from then until its next swap BACK is the frame on the glass, untouched,
 * and FRONT the one being drawn (a copy of FRONT can be a frame paused half drawn, which no tear check sees) */
#define FB_FRONT (*(u8 *volatile *)0x402A10C8u)
#define FB_BACK (*(u8 *volatile *)0x402A10CCu)
#define PANEL_BUTTONS ((void (*)(u32, u32))0x4011FC8Cu)           /* (channel, the channel's mask) */
#define PANEL_ENCODER ((void (*)(u32, int))0x4011FF0Cu)           /* (encoder 0..8, signed delta) */
#define PANEL_LAST ((volatile u8 *)0x445A2E30u)                   /* each channel's last mask */
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
#define SOUND_STRIDE 1163u
#define SOUND_BASE 52u
#define SOUND_TYPE 0xDEu

#define FB_BYTES 1024u
#define CHUNK 128u
#define NCHUNK (FB_BYTES / CHUNK)
#define CODES 55u                                /* button codes 1..54 */
#define FUNC_CODE 17u
#define SETTINGS_CODE 8u
#define PEND 16u                                 /* queued events */
#define TRACE_N 64u                              /* the trace ring (a power of two) */
#define MAX_MS 10000u                            /* the longest delay or hold an event may ask */
#define ENC_MAX 30                               /* the firmware clamps a flushed delta to +-30 */

/* capability bits (BUILDINFO): which commands this build answers */
#define CAP_TLM      (1u << 0)
#define CAP_INFO     (1u << 1)
#define CAP_SWITCH   (1u << 2)
#define CAP_PEEK     (1u << 3)
#define CAP_COUNTERS (1u << 4)
#define CAP_TRACE    (1u << 5)
#define CAP_STATE    (1u << 6)
#define CAP_SCREEN   (1u << 7)
#define CAP_ARM      (1u << 8)
#define CAP_KEY      (1u << 9)
#define CAPS (CAP_TLM | CAP_INFO | CAP_SWITCH | CAP_PEEK | CAP_COUNTERS | CAP_TRACE | CAP_STATE | CAP_SCREEN | CAP_ARM | CAP_KEY)

/* statuses (the reply's fourth byte) */
#define ST_OK 0
#define ST_ARGS 2                                /* bad arguments, an unknown sub-command */
#define ST_UNARMED 3
#define ST_REFUSED 4
#define ST_BUSY 5
#define ST_RANGE 6                               /* outside the whitelist */

/* trace kinds */
#define TR_ARM 1
#define TR_DISARM 2                              /* a: 0 asked, 1 timed out */
#define TR_DOWN 3
#define TR_UP 4
#define TR_ENC 5
#define TR_SWITCH 6
#define TR_REFUSED 7                             /* a: the code, b: why (1 SETTINGS, 2 not with FUNC, 3 FUNC over a held key) */
#define TR_RESET 8
#define TR_TORN 9

static const char build_label[16] = "remoteui-4";
static const u8 wire6[6] = {1, 0, 4, 5, 6, 7};   /* codes 49..54 (LEVEL, VOICE, ARP, PLUS, STACK, MINUS): channel 6's bits */

/* keys that may go down while FUNC is held, unless armed for destructive use: the page keys (TRIG..MOD),
 * the arrows, PLAY, STOP, PAGE, the encoder pushes. FUNC with anything else (YES, NO, PRESET, SETTINGS,
 * RECORD, PTN, SONG, KEYBOARD, TEMPO, TRK, the trigs, ...) is refused: the saving and clearing chords. */
static int func_ok(u32 code)
{
    return (code >= 1 && code <= 6) || code == 11 || code == 13 || code == 14 || code == 15
        || code == 20 || code == 21 || code == 22 || (code >= 41 && code <= 48);
}

static u32 armed D = 0, arm_flags D = 0, nonce D = 0, nonce_at D = 0, last_cmd D = 0;
static u32 tps D = 1000;                         /* ticks a second, measured (dt_poll) */
static u32 mono D = 0, mono_tick D = 0;          /* the tick unwrapped, and the tick it was stepped at */
static u32 cal_f D = 0, cal_t D = 0;
/* the queue: written by dt_rx (MIDI task), played by dt_poll (UI task); a slot with p_kind 0 is free */
static u32 p_due[PEND] D;
static u8 p_kind[PEND] D, p_code[PEND] D;
static u16 p_val[PEND] D;
static u32 p_order[PEND] D, p_next D = 0;        /* the order the events came in */
static u32 rel_at[CODES] D;                      /* each injected key's release tick, 0 not held */
static u32 held_lo D = 0, held_hi D = 0;         /* injected keys down: codes 1..32, 33..54 */
/* counters (COUNTERS; RESET zeroes them) */
#define C_CMDS 0
#define C_REFUSED 1
#define C_DOWN 2
#define C_UP 3
#define C_ENC 4
#define C_ARMS 5
#define C_DISARMS 6
#define C_TIMEOUTS 7
#define C_SNAPS 8
#define C_TORN 9
#define C_SWRITES 10
#define C_DSPMAX 11
#define C_N 12
static u32 cnt[C_N] D;
static u32 tr_at[TRACE_N] D, tr_ev[TRACE_N] D, tr_n D = 0;
static u8 snap[FB_BYTES] D;
static u32 snap_seq D = 0, snap_hash D = 0, snap_ok D = 0;
static u8 snap_tries D = 0, snap_which D = 0;

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

static u32 clock_now(void)                       /* the unwrapped tick now (either task) */
{
    u32 sr = irq_off();
    u32 m = mono + ((TICK - mono_tick) & TICK_MASK);
    irq_restore(sr);
    return m;
}

static void clock_step(void)                     /* dt_poll, every UI pass */
{
    u32 sr = irq_off();
    u32 t = TICK;
    mono += (t - mono_tick) & TICK_MASK;
    mono_tick = t;
    irq_restore(sr);
}

static void put32(u8 *p, u32 v)
{
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
}

static u32 get32(const u8 *p)
{
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

static void trace(u32 kind, u32 a, u32 b)
{
    u32 sr = irq_off();
    u32 k = tr_n & (TRACE_N - 1u);
    tr_at[k] = clock_now();
    tr_ev[k] = kind << 24 | (a & 0xFFu) << 16 | (b & 0xFFFFu);
    tr_n++;
    irq_restore(sr);
}

static u32 ms_ticks(u32 ms)                       /* ms (<= MAX_MS) -> ticks at the measured rate */
{
    return (ms * tps + 500u) / 1000u;
}

static int wire(u32 code, u32 *ch, u32 *bit)     /* a button code -> its panel channel and bit */
{
    if (code >= 1 && code <= 48) {
        *ch = (code - 1u) >> 3;
        *bit = (code - 1u) & 7u;
        return 1;
    }
    if (code >= 49 && code <= 54) {
        *ch = 6;
        *bit = wire6[code - 49u];
        return 1;
    }
    return 0;
}

static int is_held(u32 code)
{
    return code <= 32 ? (held_lo >> (code - 1u)) & 1u : (held_hi >> (code - 33u)) & 1u;
}

static void set_held(u32 code, int on)
{
    u32 *w = code <= 32 ? &held_lo : &held_hi;
    u32 b = 1u << (code <= 32 ? code - 1u : code - 33u);
    *w = on ? *w | b : *w & ~b;
}

/* a key down or up, as the panel would send it: the channel's real state with this one bit changed */
static void button(u32 code, int down)
{
    u32 ch, bit;
    if (!wire(code, &ch, &bit))
        return;
    u32 sr = irq_off();
    u32 m = PANEL_LAST[ch];
    m = down ? m | (1u << bit) : m & ~(1u << bit);
    PANEL_BUTTONS(ch, m);
    irq_restore(sr);
}

static int func_down(void)                      /* FUNC held, on the panel or by us */
{
    return is_held(FUNC_CODE) || (PANEL_LAST[2] & 1u) != 0;
}

/* -> 0 a key may go down now, else why not (the TR_REFUSED reasons) */
static u32 refuse(u32 code)
{
    if (arm_flags & 1u)                          /* armed with --allow-destructive (the User's own) */
        return 0;
    if (code == SETTINGS_CODE)
        return 1;
    if (func_down() && code != FUNC_CODE && !func_ok(code))
        return 2;
    if (code == FUNC_CODE)
        for (u32 c = 1; c < CODES; c++)
            if (c != FUNC_CODE && is_held(c) && !func_ok(c))
                return 3;
    return 0;
}

static void release_all(void)
{
    for (u32 c = 1; c < CODES; c++)
        if (is_held(c)) {
            button(c, 0);
            set_held(c, 0);
            rel_at[c] = 0;
            cnt[C_UP]++;
            trace(TR_UP, c, 0);
        }
    u32 sr = irq_off();
    for (u32 k = 0; k < PEND; k++)
        p_kind[k] = 0;
    irq_restore(sr);
}

/* disarmed: no event is queued or played from here; dt_poll (the UI task, the only one that presses or
 * lets go) lets every key go on its next pass */
static void disarm(u32 why)
{
    if (!armed)
        return;
    armed = 0;
    arm_flags = 0;
    cnt[why ? C_TIMEOUTS : C_DISARMS]++;
    trace(TR_DISARM, why, 0);
}

static void play(u32 k)                          /* one queued event, due now */
{
    u32 kind = p_kind[k], code = p_code[k], val = p_val[k];
    if (kind == 1) {                             /* press: down now, up after VAL ms */
        u32 why = refuse(code);
        if (why) {
            cnt[C_REFUSED]++;
            trace(TR_REFUSED, code, why);
        } else {
            if (!is_held(code))
                button(code, 1);
            set_held(code, 1);
            rel_at[code] = (clock_now() + ms_ticks(val)) | 1u;
            cnt[C_DOWN]++;
            trace(TR_DOWN, code, val);
        }
    } else if (kind == 2) {                      /* encoder: VAL a signed delta */
        int d = (int)(short)val;
        u32 sr = irq_off();
        PANEL_ENCODER(code, d);
        irq_restore(sr);
        cnt[C_ENC]++;
        trace(TR_ENC, code, val);
    } else if (kind == 3 && is_held(code)) {     /* release now */
        button(code, 0);
        set_held(code, 0);
        rel_at[code] = 0;
        cnt[C_UP]++;
        trace(TR_UP, code, 0);
    }
}

NOJT void dt_poll(void)
{
    extern int smp_dsp_load(void);
    clock_step();
    u32 now = mono, f = FRAMES;
    if (f - cal_f >= 1500u * 4u) {               /* the tick's rate against the audio frames, every 4 s */
        if (cal_f && now - cal_t < 2000000u && f - cal_f < 1500u * 60u) {   /* not after a long gap (overflow) */
            u32 r = (now - cal_t) * 1500u / (f - cal_f);
            if (r >= 10u && r <= 400000u)
                tps = r;
        }
        cal_f = f;
        cal_t = now;
    }
    int d = smp_dsp_load();
    if (d > (int)cnt[C_DSPMAX])
        cnt[C_DSPMAX] = (u32)d;
    if ((int)(now - last_cmd) >= (int)(dt_sw[DT_SW_ARMTIME] * tps))
        disarm(1);
    if (!armed) {
        if (held_lo | held_hi)
            release_all();
        else
            for (u32 k = 0; k < PEND; k++)
                p_kind[k] = 0;
        return;
    }
    while (armed) {                              /* the due events, earliest due first, then as they came */
        u32 best = PEND, bd = 0, bo = 0;
        for (u32 k = 0; k < PEND; k++)
            if (p_kind[k] && (int)(now - p_due[k]) >= 0
                && (best == PEND || (int)(p_due[k] - bd) < 0 || (p_due[k] == bd && (int)(p_order[k] - bo) < 0))) {
                best = k;
                bd = p_due[k];
                bo = p_order[k];
            }
        if (best == PEND)
            break;
        play(best);
        p_kind[best] = 0;
    }
    for (u32 c = 1; c < CODES; c++)              /* every key goes up at its time */
        if (is_held(c) && (int)(now - rel_at[c]) >= 0) {
            button(c, 0);
            set_held(c, 0);
            rel_at[c] = 0;
            cnt[C_UP]++;
            trace(TR_UP, c, 0);
        }
}

static u32 hash(const u8 *p)                     /* FNV-1a */
{
    u32 h = 0x811C9DC5u;
    for (u32 k = 0; k < FB_BYTES; k++)
        h = (h ^ p[k]) * 0x01000193u;
    return h;
}

/* a whole frame: WHICH 0 the glass's (BACK), 1 the one being drawn (FRONT); two reads must agree and the
 * pointer stay (a swap during the copy) */
static void take_snap(u32 which)
{
    snap_ok = 0;
    for (u32 t = 1; t <= 4; t++) {
        u8 *p = which ? FB_FRONT : FB_BACK;
        if ((u32)p < 0x40000000u || (u32)p > 0x48000000u - FB_BYTES)
            break;
        for (u32 k = 0; k < FB_BYTES; k++)
            snap[k] = p[k];
        u32 h = hash(snap);
        if ((which ? FB_FRONT : FB_BACK) == p && hash(p) == h) {
            snap_hash = h;
            snap_ok = 1;
            snap_tries = (u8)t;
            break;
        }
        cnt[C_TORN]++;
        trace(TR_TORN, t, 0);
    }
    snap_which = (u8)which;
    snap_seq++;
    cnt[C_SNAPS]++;
}

static int peek_ok(u32 a, u32 n)
{
    const u32 *r = dt_peek_ranges;
    for (u32 k = 0; k < dt_peek_n; k++, r += 2)
        if (a >= r[0] && a < r[1] && n <= r[1] - a)
            return 1;
    return 0;
}

static u32 keys_in(const u8 *rq, u32 n, u8 *rp, u32 r, u8 *st)   /* KEY: u8 count, count x 6 bytes */
{
    u32 m = n >= 4 ? rq[3] : 0;
    if (!armed) {
        *st = ST_UNARMED;
        return r;
    }
    if (m < 1 || m > PEND || n < 4u + 6u * m) {
        *st = ST_ARGS;
        return r;
    }
    u32 free = 0;
    for (u32 k = 0; k < PEND; k++)
        free += p_kind[k] == 0;
    const u8 *e = rq + 4;
    for (u32 j = 0; j < m; j++, e += 6) {        /* all checked before any is queued */
        u32 kind = e[0], code = e[1], at = (u32)e[2] << 8 | e[3], val = (u32)e[4] << 8 | e[5];
        u32 ch, bit;
        int bad = at > MAX_MS || kind < 1 || kind > 3;
        if (kind == 1 || kind == 3)
            bad |= !wire(code, &ch, &bit) || (kind == 1 && (val < 1 || val > MAX_MS));
        if (kind == 2)
            bad |= code > 8 || (int)(short)val < -ENC_MAX || (int)(short)val > ENC_MAX || val == 0;
        if (bad) {
            *st = ST_ARGS;
            rp[r++] = (u8)j;
            return r;
        }
        if (kind == 1 && code == SETTINGS_CODE && !(arm_flags & 1u)) {
            *st = ST_REFUSED;
            cnt[C_REFUSED]++;
            trace(TR_REFUSED, code, 1);
            rp[r++] = (u8)j;
            return r;
        }
    }
    if (free < m) {
        *st = ST_BUSY;
        rp[r++] = (u8)free;
        return r;
    }
    u32 now = clock_now();
    e = rq + 4;
    u32 sr = irq_off();
    for (u32 j = 0, k = 0; j < m; j++, e += 6) {
        while (p_kind[k])
            k++;
        p_due[k] = now + ms_ticks((u32)e[2] << 8 | e[3]);
        p_code[k] = e[1];
        p_val[k] = (u16)((u32)e[4] << 8 | e[5]);
        p_order[k] = p_next++;
        p_kind[k] = e[0];
    }
    irq_restore(sr);
    last_cmd = now;
    rp[r++] = (u8)m;
    rp[r++] = (u8)(free - m);
    return r;
}

/* the commands 33..42 (link.c smp_rx: RQ its N bytes, the reply's data from RP + R, room to 160; ST the
 * status byte) -> the reply's length */
NOJT u32 dt_rx(u32 cmd, const u8 *rq, u32 n, u8 *rp, u32 r, u8 *st)
{
    u32 sub = n >= 4 ? rq[3] : 0xFFu;
    cnt[C_CMDS]++;
    if (cmd == 33) {                             /* BUILDINFO */
        put32(rp + r, 0x44544231u); r += 4;      /* 'DTB1' */
        rp[r++] = 0; rp[r++] = DT_PROTO;
        rp[r++] = 0x01; rp[r++] = 0x12;          /* OS 1.12 */
        put32(rp + r, CAPS); r += 4;
        rp[r++] = DT_SW_N;
        rp[r++] = 128; rp[r++] = 64;             /* the screen, 1 bpp */
        rp[r++] = NCHUNK;
        for (u32 k = 0; k < 16; k++)
            rp[r++] = (u8)build_label[k];
        put32(rp + r, tps); r += 4;
    } else if (cmd == 34) {                      /* SWITCH: 0 INFO k, 1 GET all, 2 SET k u32 */
        u32 k = n >= 5 ? rq[4] : 0xFFu;
        if (sub == 0 && k < DT_SW_N) {
            const struct dt_switch *s = &dt_switches[k];
            rp[r++] = (u8)k;
            for (u32 c = 0; c < 8; c++)
                rp[r++] = (u8)s->name[c];
            put32(rp + r, dt_sw[k]); r += 4;
            put32(rp + r, s->min); r += 4;
            put32(rp + r, s->max); r += 4;
            put32(rp + r, s->def); r += 4;
        } else if (sub == 1) {
            rp[r++] = DT_SW_N;
            for (u32 j = 0; j < DT_SW_N; j++) {
                put32(rp + r, dt_sw[j]); r += 4;
            }
        } else if (sub == 2 && k < DT_SW_N && n >= 9) {
            u32 v = get32(rq + 5);
            const struct dt_switch *s = &dt_switches[k];
            if (v < s->min || v > s->max) {
                *st = ST_RANGE;
            } else {
                dt_sw[k] = v;
                cnt[C_SWRITES]++;
                trace(TR_SWITCH, k, v);
            }
            rp[r++] = (u8)k;
            put32(rp + r, dt_sw[k]); r += 4;
        } else {
            *st = ST_ARGS;
        }
    } else if (cmd == 35) {                      /* PEEK: u32 address, u8 bytes (1..128) */
        u32 a = n >= 8 ? get32(rq + 3) : 0, len = n >= 8 ? rq[7] : 0;
        if (n < 8 || len < 1 || len > CHUNK) {
            *st = ST_ARGS;
        } else if (!peek_ok(a, len)) {
            *st = ST_RANGE;
        } else {
            put32(rp + r, a); r += 4;
            const volatile u8 *p = (const volatile u8 *)a;
            for (u32 k = 0; k < len; k++)
                rp[r++] = p[k];
        }
    } else if (cmd == 36) {                      /* COUNTERS: 0 read, 1 read and reset */
        if (sub > 1) {
            *st = ST_ARGS;
        } else {
            rp[r++] = C_N;
            for (u32 k = 0; k < C_N; k++) {
                put32(rp + r, cnt[k]); r += 4;
            }
            put32(rp + r, tr_n); r += 4;
            put32(rp + r, clock_now()); r += 4;
            put32(rp + r, FRAMES); r += 4;
            if (sub == 1) {
                for (u32 k = 0; k < C_N; k++)
                    cnt[k] = 0;
                trace(TR_RESET, 0, 0);
            }
        }
    } else if (cmd == 37) {                      /* TRACE: u32 from -> u32 total, u8 count, count x 8 bytes */
        u32 from = n >= 7 ? get32(rq + 3) : 0, total = tr_n;
        if (total - from > TRACE_N || (int)(total - from) < 0)
            from = total - (total < TRACE_N ? total : TRACE_N);
        u32 m = total - from > 16u ? 16u : total - from;
        put32(rp + r, total); r += 4;
        put32(rp + r, from); r += 4;
        rp[r++] = (u8)m;
        for (u32 j = 0; j < m; j++) {
            u32 k = (from + j) & (TRACE_N - 1u);
            put32(rp + r, tr_at[k]); r += 4;
            put32(rp + r, tr_ev[k]); r += 4;
        }
    } else if (cmd == 38) {                      /* STATE */
        extern u8 ins_sel[16][2];
        put32(rp + r, FRAMES); r += 4;
        put32(rp + r, clock_now()); r += 4;
        put32(rp + r, tps); r += 4;
        rp[r++] = (u8)armed;
        rp[r++] = (u8)arm_flags;
        u32 left = 0;
        if (armed) {
            u32 gone = (clock_now() - last_cmd) / (tps ? tps : 1000u);
            left = gone < dt_sw[DT_SW_ARMTIME] ? dt_sw[DT_SW_ARMTIME] - gone : 0;
        }
        rp[r++] = (u8)(left >> 8); rp[r++] = (u8)left;
        put32(rp + r, held_lo); r += 4;
        put32(rp + r, held_hi); r += 4;
        u32 pend = 0;
        for (u32 k = 0; k < PEND; k++)
            pend += p_kind[k] != 0;
        rp[r++] = (u8)pend;
        for (u32 c = 0; c < 7; c++)
            rp[r++] = PANEL_LAST[c];
        u8 *kit = KIT_POINTER;
        int kit_ok = (u32)kit >= 0x40000000u && (u32)kit < 0x48000000u - 16u * SOUND_STRIDE - SOUND_BASE;
        for (u32 t = 0; t < 16; t++)
            rp[r++] = kit_ok ? kit[SOUND_BASE + SOUND_STRIDE * t + SOUND_TYPE] : 0xFFu;
        for (u32 t = 0; t < 16; t++) {
            rp[r++] = ins_sel[t][0];
            rp[r++] = ins_sel[t][1];
        }
        put32(rp + r, (u32)FB_FRONT); r += 4;
        put32(rp + r, (u32)FB_BACK); r += 4;
    } else if (cmd == 40) {                      /* SCREEN: u8 flags (bit 0 the frame being drawn, bit 1 new frame), u8 chunk */
        u32 flags = sub, ch = n >= 5 ? rq[4] : 0xFFu;
        if (n < 5 || flags > 3 || (ch >= NCHUNK && ch != 0xFFu)) {
            *st = ST_ARGS;
        } else {
            if ((flags & 2u) || !snap_seq || snap_which != (flags & 1u))
                take_snap(flags & 1u);
            rp[r++] = (u8)ch;
            rp[r++] = NCHUNK;
            rp[r++] = snap_tries;
            rp[r++] = (u8)snap_ok;
            put32(rp + r, snap_seq); r += 4;
            put32(rp + r, snap_hash); r += 4;
            if (ch < NCHUNK)
                for (u32 k = 0; k < CHUNK; k++)
                    rp[r++] = snap[ch * CHUNK + k];
        }
    } else if (cmd == 41) {                      /* ARM: 0 ask (-> nonce), 1 'ARM!' nonce flags, 2 disarm, 3 status */
        u32 now = clock_now();
        if (sub == 0) {
            nonce = (now * 0x9E3779B1u) ^ (FRAMES << 7) ^ (cnt[C_CMDS] * 0x85EBCA6Bu) ^ snap_hash;
            nonce |= 1u;
            nonce_at = now;
            put32(rp + r, nonce); r += 4;
        } else if (sub == 1) {
            int ok = n >= 13 && rq[4] == 'A' && rq[5] == 'R' && rq[6] == 'M' && rq[7] == '!'
                     && nonce && get32(rq + 8) == nonce && (now - nonce_at) <= 10u * tps;
            nonce = 0;                           /* one try a nonce */
            if (!ok) {
                *st = ST_REFUSED;
                cnt[C_REFUSED]++;
            } else {
                arm_flags = rq[12] & 1u;
                last_cmd = now;
                if (!armed) {
                    armed = 1;
                    cnt[C_ARMS]++;
                    trace(TR_ARM, arm_flags, 0);
                }
            }
        } else if (sub == 2) {
            disarm(0);
        } else if (sub != 3) {
            *st = ST_ARGS;
        }
        if (sub == 3 && armed)
            last_cmd = now;                      /* a status keeps it armed */
        rp[r++] = (u8)armed;
        rp[r++] = (u8)arm_flags;
        put32(rp + r, dt_sw[DT_SW_ARMTIME]); r += 4;
    } else if (cmd == 42) {                      /* KEY */
        r = keys_in(rq, n, rp, r, st);
    } else {
        *st = ST_ARGS;
    }
    return r;
}
