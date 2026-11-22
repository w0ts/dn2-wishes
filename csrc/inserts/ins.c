/* The per-track inserts' pages and values (docs/inserts.md), OS 1.12.
 *
 * 2026-11-10 (the User): two insert slots a track, and the FX key's pages are three: FX 1/3, stock's
 * track FX page, FX 2/3 the active track's INSERT 1, FX 3/3 its INSERT 2. [FX] steps 1/3 -> 2/3 -> 3/3
 * -> 1/3; [FX] anywhere else is stock's (to FX 1/3); FUNC + [FX] is stock's alone (the three SEND
 * pages, never an INSERT page). On each switch the title bar says "FX (n/3)" with stock's own message
 * line (SAY, as stock's "Delay (1/3)"), and every page shows stock's page dots (three, the current one
 * filled). NO or any page key closes an INSERT page. While one is up its eight knobs are ours (rec.c
 * smp_ui_pop hands every item to ins_pop first) and it draws over the screen with stock's own widgets
 * (page.c wr_screen; csrc/waverider/widgets.h), keeping stock's left panel:
 *
 *     A M.SEL (OFF CHOR DIST FDN8 FOLD FUZZ GATR HARM JUNO RING SUB TAPE WIDE XDLY: A-Z, each a band of 0..127)   B..G the
 *     insert's knobs   H MIX (dry/wet)
 *
 * Each slot keeps every insert's knobs (switching M.SEL and back keeps them). FDN8 and XDLY run on the
 * track's bus (dnfw.inserts.bus), each slot holding one of the DSP's instances (8 FDN8, 4 XDLY) while it
 * keeps the type: a slot that finds none free shows FULL under M.SEL and passes the sound through.
 * The values go to the DSP after the sample pool's command block (dnfw.inserts.design.GEN_OFFSET: a
 * change word, then 32 records of eight 7-bit fields packed in 56 words, design.pack), sent by the link
 * (link.c smp_tdm). They are saved with the project (csrc/inserts/store.c).
 *
 * 2026-11-20 (the User, scratch/mod-live-design.md C, every first option): each track's 14 knobs (each slot's K1..K6,
 * stored fields 0..5, and MIX; M.SEL never) are p-lockable (csrc/slides: kinds K1..K6, MIX, ids 211..217, a step's
 * u16 slot 1 in its low byte, slot 2 in its high byte) and the matrix's destinations 0xC0 + 7 j + i (csrc/matrix:
 * ordinary routes of the track's LFO and envelope routes; the delay-time and jump knobs not offered, ROUTE_OK). The
 * values the DSP gets:
 * - SET (ins_cell, a cell: the knob << 8): the track's last trig's lock (ins_lk, ins_trig at sl_apply) or the knob;
 *   written only in the audio interrupt (ins_trig, ins_period: the UI marks a track ins_dirty);
 * - HEARD: SET + the routes' offset (ins_moff), each track's from its last-played voice (slides' sl_lastv), worked out
 *   by mx_eval in the frame its group is packed next; a voice that left the track holds its last offset (a knob turned
 *   meanwhile is still heard); no voice yet: 0. A knob the slot's type does not route (ROUTE_OK) adds none.
 * - The round-robin (ins_period, every DSP block from link.c smp_tdm): one group of 4 records (2 tracks) packed a block,
 *   every group every 8 blocks (187.5 Hz), the same work with modulation or without; one 58-word packet every 8
 *   blocks after the last group (only commands go first), its change word moved only when the packed words differ
 *   from the last packet's (the DSP unpacks only then, as before). A trig whose locks change a track's SET packs its
 *   group at once and sends the packet in the next block (ins_urgent).
 * - MIX 0 = OFF (mix_off) only when nothing can move MIX: no MIX route (mx_ins_routes) and no MIX lock in the pattern
 *   (ins_keep, the UI pass's scan; and at once by a trig's MIX lock): a locked or modulated 0 is dry, never OFF and on
 *   again (18a).
 */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef short s16;
typedef int s32;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define TEXT      ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573Cu)
#define FONT      0x44508ED8u
#define CENTRED   2
#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY    0
#define IT_KNOB   1
#define IT_DROP   0xFF
#define K_FX      5
#define K_UP      11
#define K_NO      12
#define K_DOWN    14
#define K_FUNC    17
#define KEY_HELD  ((int (*)(u32))0x4011FAC4u)                 /* (code) -> 1 while held (jump.c) */
#define SAY       ((void (*)(void *, void *))0x4005628Cu)     /* a message line's text, its slide in */
#define STR_NEW   ((void (*)(void *, const char *, void *))0x401CEAB8u)   /* std::string(s, alloc) */
#define STR_SET   ((void (*)(void *, const void *))0x401CC46Cu)          /* std::string = (SAY's) */
#define STR_FREE  ((void (*)(void *))0x401CD008u)
#define PAGE_DOTS ((void (*)(void *, void *, int, int, int))0x4006598Au) /* (-, canvas, n, page, 7) */
/* the screen's views (rec.c smp_question_up's walk); classes measured in the 1.12 emulator: the
 * track FX page's view, and the title bar's, whose +120 is the message line SAY writes (its text a
 * std::string at +0x48: "FX" on entering the FX page, "Delay (1/3)" .. on the SEND pages) */
#define FX_PAGE_VTABLE 0x401E1448u
#define TITLE_VTABLE   0x401E1D28u
#define TYPES     14                            /* OFF and the thirteen (dnfw.inserts.design: a type keeps its
                                                 * number for good; 2026-11-10 SUB DIST GATER RING 9..12, Optimist's;
                                                 * 2026-11-12 JUNO 13, Optimist's Juno-106 chorus) */
#define SLOTS     2
#define SUB_DRY   0                             /* SUB's start for DRY (K5), a knob no more (2026-11-11, the User: MIX is the dry / wet): a NEW
                                                 * SUB is the sub alone. The value is still saved, loaded and sent; a project that has one plays as
                                                 * before. Likewise the hidden LEVs: SUB K1, HARM K5, RING K4 (see LABEL) */
#define T_FDN8    7
#define T_XDLY    8
#define N_FDN8    8                             /* the DSP's instances (design.FDN8_INSTANCES, XDLY_INSTANCES) */
#define N_XDLY    4
#define NO_INST   0xFF
#define PAGES     3                             /* FX 1/3 stock's, 2/3 INSERT 1, 3/3 INSERT 2 */
/* 2026-11-10 (the User): M.SEL lists the types A-Z, OFF first. Only the DISPLAY order is sorted: a type's
 * number (ins_sel, the saved record's first byte, the DSP's) never changes. ORDER[position] = type,
 * POS[type] = position; the knob's band, the popup and a loaded project's band all go through them. */
static const u8 ORDER[TYPES] = {0, 4, 10, 7, 3, 1, 11, 6, 13, 12, 9, 2, 5, 8};   /* OFF CHOR DIST FDN8 FOLD FUZZ GATR HARM JUNO RING SUB TAPE WIDE XDLY */
static const u8 POS[TYPES] = {0, 5, 11, 4, 1, 12, 7, 3, 13, 10, 2, 6, 9, 8};
static const u8 BUILT[TYPES] = {1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};   /* what this build runs */

static const char *const NAME[TYPES] = {"OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM", "FDN8", "XDLY",
                                        "SUB", "DIST", "GATR", "RING", "JUNO"};
/* 2026-11-12 (the User: "auto adjust level", "the post gain in the same position everywhere for all distos"): on the
 * distortions PGAIN is place 4 (F) and AUTO place 5 (G), an on/off switch: a turn right sets 127, left 0 (the DSP: on
 * above 63, dnfw.inserts.design.AUTO_ON). HARM's PGAIN is its stored LEV (K5), back on the page */
static const char AUTO_LABEL[] = "AUTO";
static const char *const LABEL[TYPES][6] = {
    {"", "", "", "", "", ""},
    {"DRIV", "TONE", "BIAS", "PRE", "PGAIN", AUTO_LABEL},   /* FUZZ: GATE on page 2 (FIELD) */
    {"DRIV", "WOW", "WRAT", "FLUT", "PGAIN", AUTO_LABEL},   /* TAPE: AGE HISS on page 2 (FIELD) */
    {"AMNT", "SYMM", "SHPE", "TONE", "PGAIN", AUTO_LABEL},
    {"DPTH", "RATE", "DLY", "VOIC", "WDTH", "FDBK"},
    {"WDTH", "TIME", "BASS", "TONE", "", ""},
    {"AMNT", "FREQ", "EVEN", "TONE", "PGAIN", AUTO_LABEL},
    {"PRE", "SIZE", "DAMP", "MOD", "HPF", "LPF"},     /* FDN8 (docs/fdn8.md's knobs) */
    {"TIM1", "TIM2", "FDBK", "MOD", "TONE", ""},      /* XDLY (docs/xdly.md's knobs) */
    {"BAND", "TONE", "OCT", "", "", ""},              /* SUB (docs/inserts.md, ported from Optimist); stored LEV (K1) and DRY (K5) off the page 2026-11-11, so place k is stored field k + 1 (DOFF) */
    {"DRIV", "TONE", "BIAS", "LOW", "PGAIN", AUTO_LABEL},   /* DIST */
    {"DPTH", "PATN", "RATE", "SHPE", "SWNG", ""},     /* GATER */
    {"FREQ", "SHPE", "AM", "", "", ""},              /* RING (LEV, K4, off the page 2026-11-11) */
    {"MODE", "", "", "", "", ""},                    /* JUNO: I / II / I+II (thirds of 0..127); MIX as Optimist's */
};
/* the knob PLACES of a type start at its stored field DOFF (the DSP reads the fields by position, so a hidden first field
 * is skipped on the page, never moved): SUB 1 (LEV hidden), the rest 0. LABEL[y][k] is place k, stored field k + DOFF(y). */
#define DOFF(y) ((y) == 9)
/* 2026-11-13 (the User: PGAIN on F, AUTO on G on every distortion; FUZZ's GATE to a page 2, its values unchanged): the
 * stored field of place k on page PG (0, 1). FUZZ: DRIV TONE BIAS PRE PGAIN (field 5) AUTO (X_AUTO: ins_fza, sent in
 * field 0's bit 4, saved in the MIX byte's bit 7), page 2 GATE (field 4). -1: an empty place. A FUNC tap switches a
 * type with a page 2 between its pages (ins_pop); [FX] goes on to the next FX page, page 1 again. */
#define T_FUZZ    1
#define T_TAPE    2
#define X_AUTO    6                             /* FUZZ's and TAPE's AUTO (ins_fza) */
#define X_TPG     8                             /* TAPE's PGAIN (ins_tpg: knob 64 0 dB, 1 dB a step, 32 .. 95) */
static const char *const LABEL2[TYPES][6] = {
    [T_FUZZ] = {"GATE", "", "", "", "", ""},
    [T_TAPE] = {"AGE", "HISS", "", "", "", ""},
};
static int field_of(int y, int pg, int k)
{
    if (y == T_FUZZ)
        return pg ? (k == 0 ? 4 : -1) : (k < 4 ? k : k == 4 ? 5 : X_AUTO);
    if (y == T_TAPE)                            /* 2026-11-13: PGAIN (new) and AUTO; AGE HISS on page 2 */
        return pg ? (k < 2 ? 4 + k : -1) : (k < 4 ? k : k == 4 ? X_TPG : X_AUTO);
    return pg || !LABEL[y][k][0] ? -1 : k + DOFF(y);
}
static int has_page2(int y)
{
    return LABEL2[y][0] != 0;
}
static const u8 DEFAULT[TYPES][6] = {
    {0, 0, 0, 0, 0, 0}, {64, 90, 0, 30, 0, 100}, {50, 30, 20, 25, 50, 10}, {80, 64, 0, 100, 100, 0},
    {50, 50, 40, 64, 100, 0}, {90, 20, 40, 80, 0, 0}, {50, 70, 64, 80, 100, 0},
    {0, 60, 30, 64, 0, 127}, {60, 70, 60, 0, 98, 0},
    {100, 85, 59, 0, SUB_DRY, 0}, {64, 90, 20, 64, 64, 0}, {127, 64, 64, 20, 0, 0}, {64, 0, 0, 100, 0, 0},
    {0, 0, 0, 0, 0, 0},
};

/* 2026-11-20 (the User, 14a): the stored fields 0..5 (K1..K6) a route may move, by type (bit k: field k). Not: the delay
 * times and the jumps (CHOR DPTH DLY VOIC, WIDE TIME, FDN8 PRE, SUB OCT, GATR PATN RATE, JUNO MODE), the AUTO switches
 * (FOLD HARM DIST field 5; FUZZ's and TAPE's AUTO and TAPE's PGAIN are no field), and the fields off the page (SUB LEV
 * DRY, RING LEV, the empty places). Every one of them is still lockable. MIX is routable on every type that runs. */
static const u8 ROUTE_OK[TYPES] = {0x00, 0x3F, 0x3F, 0x1F, 0x32, 0x0D, 0x1F, 0x3E, 0x1F, 0x06, 0x1F, 0x19, 0x07, 0x00};
#define INS_N    14                             /* a track's knobs: slot j's K1..K6 at 7 j + 0..5, its MIX at 7 j + 6 */
#define I_MIX    6
#define NO_LOCK  0xFF
#define INS_DEST 0xC0u                          /* the matrix's destination of knob i: INS_DEST + i (matrix.c MX_INS_DEST) */
#define GROUPS   8                              /* 4 records (2 tracks) a group, one group a block */
#define URGENT_MAX 2                            /* (2026-11-21, the User: the worst frame) groups a trig changed, packed
                                                 * a block at most besides the round-robin's */
#ifndef INS_FRAMES
#define INS_FRAMES (*(volatile u32 *)0x4058F8D4u)   /* frames since boot, 1,500 a second (the host tests: their own) */
#endif

u8 ins_sel[16][SLOTS] __attribute__((section(".data")));    /* the type (from ins_selv's band) */
u8 ins_selv[16][SLOTS] __attribute__((section(".data")));   /* M.SEL as turned, 0..127: each type a band of it */
u8 ins_mod[16][SLOTS] __attribute__((section(".data")));
u8 ins_fza[16][SLOTS] __attribute__((section(".data")));   /* FUZZ's or TAPE's AUTO (0 / 127; X_AUTO) */
u8 ins_tpg[16][SLOTS] __attribute__((section(".data")));   /* TAPE's PGAIN (X_TPG): 64 + dB, 32 .. 95 */
static int ins_pg __attribute__((section(".data"))) = 0;      /* the INSERT page's page: 0, 1 (page 2) */
static int pg_open __attribute__((section(".data"))) = 0;    /* the page ins_draw opens a new INSERT page on (UP / DOWN
                                                               * from a page 2 to the other slot's page 2: 1) */
static int ins_armed __attribute__((section(".data"))) = 0;   /* FUNC went down on an insert with a page 2 */
u8 ins_inst[16][SLOTS] __attribute__((section(".data")));   /* FDN8 / XDLY: the DSP's instance, NO_INST: FULL */
u8 ins_kv[16][SLOTS][TYPES][6] __attribute__((section(".data")));
u32 ins_gen __attribute__((section(".data"))) = 0;      /* moves on every change: the link sends */
u32 ins_edits __attribute__((section(".data"))) = 0;    /* moves on every edit by the knobs (store.c saves) */
int ins_up __attribute__((section(".data"))) = 0;       /* the INSERT page up: 0 none, 1 or 2 its slot */
static int ins_inited __attribute__((section(".data"))) = 0;
static int title_due __attribute__((section(".data"))) = 0;  /* draws left to rename stock's "FX" */
static int touched __attribute__((section(".data"))) = -1;   /* the knob last turned on this INSERT page (0..5, 7 MIX): its value in its unit */
/* 2026-11-20: the live values (the header's comment) */
u8 ins_lk[16][INS_N] __attribute__((section(".data")));       /* the last trig's locks (0..127), NO_LOCK none */
u16 ins_cell[17][INS_N] __attribute__((section(".data"), aligned(4)));   /* SET as a cell; row 16 (a voice on no track's
                                                               * sound) zeros: mx_eval copies a voice's track's row */
s16 ins_moff[16][INS_N] __attribute__((section(".data")));    /* the routes' offset on SET, held (mx_eval) */
volatile u8 ins_dirty[16] __attribute__((section(".data"), aligned(4)));   /* the UI changed track t: its SET again */
volatile u8 ins_urgent[GROUPS] __attribute__((section(".data"), aligned(4)));   /* a trig changed a group's SET */
u8 ins_keep[16][SLOTS] __attribute__((section(".data")));     /* a MIX route or lock: MIX 0 is no OFF (mix_off) */
volatile u8 ins_hdirty[16] __attribute__((section(".data"), aligned(4)));   /* (2026-11-21) track t's two records'
                                                               * headers (type, instance, AUTO, MIX 0 = OFF) or TAPE's
                                                               * PGAIN may have changed: made again when its group is
                                                               * packed next (pack_group), a byte a track (the UI and the
                                                               * audio interrupt both mark) */
volatile u32 ins_rr __attribute__((section(".data"))) = 0;     /* the next group packed (mx_eval works its offsets out) */
int ins_due __attribute__((section(".data"))) = 0;            /* a packet to send (link.c) */
u32 ins_pkt[2 + 7 * GROUPS] __attribute__((section(".data"))); /* the packet: the change word, 0, the 8 groups */
static int pkt_changed __attribute__((section(".data"))) = 1;  /* words differ from the last packet sent */
u32 ins_chg __attribute__((section(".data"))) = 0;            /* the change word last sent */
u32 ins_pkts __attribute__((section(".data"))) = 0, ins_urgents __attribute__((section(".data"))) = 0;   /* the checks */
u32 ins_trigs __attribute__((section(".data"))) = 0;          /* trigs that changed a track's SET (the checks) */
static u8 hdr_f0[32] __attribute__((section(".data")));         /* a record's field 0 as sent */
static u8 hdr_zero[32] __attribute__((section(".data")));       /* mix_off: every field 0 */
static u8 hdr_rmask[32] __attribute__((section(".data")));      /* the knobs routes move (bit i: knob i of the slot) */
u32 ins_tpg_w[8] __attribute__((section(".data")));            /* TAPE's PGAIN words (ins_tpg_words), as last made */
u32 ins_tpg_gen __attribute__((section(".data"))) = 1;         /* moves when they differ (link.c sends them) */

static void ins_changed_all(void);

/* every slot to its defaults: OFF, MIX 127, every insert's knobs as DEFAULT (power-on, a NEW project) */
void ins_defaults(void)
{
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < SLOTS; j++) {
            ins_sel[t][j] = 0;
            ins_selv[t][j] = 0;
            ins_mod[t][j] = 127;
            ins_fza[t][j] = 0;
            ins_tpg[t][j] = 64;
            ins_inst[t][j] = NO_INST;
            for (int y = 0; y < TYPES; y++)
                for (int k = 0; k < 6; k++)
                    ins_kv[t][j][y][k] = DEFAULT[y][k];
        }
    for (int t = 0; t < 16; t++)
        for (int i = 0; i < INS_N; i++)
            ins_lk[t][i] = NO_LOCK;             /* (a NEW or loaded project: the last trigs' locks forgotten) */
    ins_inited = 1;
    ins_gen++;
    ins_changed_all();
}

static void init(void)
{
    if (!ins_inited)
        ins_defaults();
}

static int instances(int y)                     /* FDN8 / XDLY: the DSP's instances of type Y; 0 others */
{
    return y == T_FDN8 ? N_FDN8 : y == T_XDLY ? N_XDLY : 0;
}

/* slot (t, j) has type Y now: an instance for it (the one it holds if of Y, else the lowest no other
 * slot of Y holds), or NO_INST when every one is taken (FULL) or Y needs none */
static void assign(int t, int j)
{
    int y = ins_sel[t][j], n = instances(y);
    if (!n) {
        ins_inst[t][j] = NO_INST;
        return;
    }
    u32 used = 0;
    for (int u = 0; u < 16; u++)
        for (int i = 0; i < SLOTS; i++)
            if ((u != t || i != j) && ins_sel[u][i] == y && ins_inst[u][i] != NO_INST)
                used |= 1u << ins_inst[u][i];
    if (ins_inst[t][j] != NO_INST && ins_inst[t][j] < n && !(used >> ins_inst[t][j] & 1u))
        return;                                 /* it keeps its own */
    ins_inst[t][j] = NO_INST;
    for (int k = 0; k < n; k++)
        if (!(used >> k & 1u)) {
            ins_inst[t][j] = (u8)k;
            return;
        }
}

/* every FULL slot tries again (an instance may have come free); a slot's own is kept */
static void reassign(void)
{
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < SLOTS; j++)
            if (instances(ins_sel[t][j]) && ins_inst[t][j] == NO_INST)
                assign(t, j);
}

/* the load icons' memory one (csrc/meter/meter.c): a slot of FDN8 / XDLY found no instance free (FULL) */
int ins_full_any(void)
{
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < SLOTS; j++)
            if (ins_sel[t][j] < TYPES && instances(ins_sel[t][j]) && ins_inst[t][j] == NO_INST)
                return 1;
    return 0;
}

/* the voice inserts the pre pass runs (dnfw.inserts.design BUILT: FUZZ TAPE FOLD HARM SUB DIST GATER RING), and slot 1's
 * types that move a voice insert in slot 2 to the track's bus (design.MOVERS: CHOR WIDE JUNO FDN8 XDLY) */
static int is_voice(int y)
{
    return y == 1 || y == 2 || y == 3 || y == 6 || (y >= 9 && y <= 12);
}
static int is_mover(int y)
{
    return y == 4 || y == 5 || y == 13 || y == T_FDN8 || y == T_XDLY;
}
/* the type the DSP gets for slot (t, j): 0 (OFF) for a FULL slot, a type this build does not run, and (2026-11-16, the User:
 * "all insert FX when loaded, are in 'no actual effect position'") a slot at MIX 0. At MIX 0 the DSP's mix
 * x + (wet - x) x 0 gives the dry, measured bit for bit on every type's model, yet the type's code ran in full; sent OFF it
 * costs nothing, and when MIX leaves 0 it starts from silence (the 2026-11-14 rule: a slot that did not run forgets).
 * Kept: slot 1 a MOVER at MIX 0 while slot 2 sends a voice insert, so slot 2 stays on the bus after it (design.moved) */
static int runs(int t, int j)                   /* a type the DSP would run: built, and not FULL */
{
    int y = ins_sel[t][j];
    return y && y < TYPES && BUILT[y] && !(instances(y) && ins_inst[t][j] == NO_INST);
}
static int mix_off(int t, int j)                /* at MIX 0: sent exactly as an OFF slot at MIX 0 (all eight fields 0); not
                                                 * while a MIX route or lock can move it (ins_keep, 2026-11-20) */
{
    if (!runs(t, j) || ins_mod[t][j] != 0 || ins_keep[t][j])
        return 0;
    return !(j == 0 && is_mover(ins_sel[t][j]) && is_voice(ins_sel[t][1]) && runs(t, 1) && !mix_off(t, 1));
}
static int sent_type(int t, int j)
{
    return runs(t, j) && !mix_off(t, j) ? ins_sel[t][j] : 0;
}

/* the inserts overview (ovw.c, dnfw.inserts.overview): slot (t, j) as the DSP has it -- 0 OFF (or a type this build
 * does not run), 1 MIX 0 (sent as OFF: no cost), 2 the DSP runs it (a slot-1 mover kept at MIX 0 included), 3 FULL
 * (an FDN8 / XDLY that found no instance); *type its type */
int ins_slot_state(int t, int j, int *type)
{
    init();
    int y = ins_sel[t][j];
    *type = y < TYPES ? y : 0;
    if (!y || y >= TYPES || !BUILT[y])
        return 0;
    if (instances(y) && ins_inst[t][j] == NO_INST)
        return 3;
    return sent_type(t, j) ? 2 : 1;
}

/* a record's eight fields (dnfw.inserts.design: type | instance << 4, MIX, K1..K6); a FULL slot is OFF; one at MIX 0 is
 * an OFF slot's record at MIX 0, every field 0 (mix_off) */
static void fields(int t, int j, u8 *f)
{
    int y = ins_sel[t][j];
    int s = sent_type(t, j);
    if (mix_off(t, j)) {
        for (int k = 0; k < 8; k++)
            f[k] = 0;
        return;
    }
    f[0] = !s ? 0 : (u8)(s | (instances(s) ? ins_inst[t][j] << 4 : 0));
    if (s && (y == T_FUZZ || y == T_TAPE) && ins_fza[t][j] >= 64)
        f[0] |= 0x10;                           /* FUZZ's or TAPE's AUTO (dnfw.inserts.design.FZ_AUTO_BIT) */
    f[1] = ins_mod[t][j];
    for (int k = 0; k < 6; k++)
        f[2 + k] = ins_kv[t][j][y][k];
}

/* the 58 words the DSP reads from GEN_OFFSET (dnfw.inserts.design.pack, held to it by
 * test/test_inserts_c.py): the change word, a zero, then 8 groups of 7 words, each 4 records' 32
 * fields: word w fields 4w .. 4w+3 in its bits 0..27, fields 28..31 in the 7 words' top nibbles */
void ins_words(u32 *w)
{
    init();
    w[0] = ins_gen;
    w[1] = 0;
    for (int g = 0; g < 8; g++) {
        u8 f[32];
        for (int r = 0; r < 4; r++) {
            int rec = 4 * g + r;
            fields(rec >> 1, rec & 1, f + 8 * r);
        }
        u32 x = (u32)(f[28] & 0x7F) | (u32)(f[29] & 0x7F) << 7 | (u32)(f[30] & 0x7F) << 14 | (u32)(f[31] & 0x7F) << 21;
        for (int k = 0; k < 7; k++)
            w[2 + 7 * g + k] = (u32)(f[4 * k] & 0x7F) | (u32)(f[4 * k + 1] & 0x7F) << 7 | (u32)(f[4 * k + 2] & 0x7F) << 14
                | (u32)(f[4 * k + 3] & 0x7F) << 21 | (x >> (4 * k) & 0xFu) << 28;
    }
}

/* 2026-11-13: TAPE's PGAIN for the DSP (dnfw.inserts.design.TP_PG_DDR; link.c sends them after READY): a byte a record,
 * record i byte i % 4 of word i // 4, 7-bit two's complement dB (0: unity); not TAPE, 0 */
void ins_tpg_words(u32 *w)
{
    init();
    for (int k = 0; k < 8; k++)
        w[k] = 0;
    for (int i = 0; i < 32; i++) {
        int t = i >> 1, j = i & 1;
        if (ins_sel[t][j] == T_TAPE && !mix_off(t, j))   /* (at MIX 0: 0, as an OFF slot's) */
            w[i >> 2] |= (u32)((ins_tpg[t][j] - 64) & 0x7F) << (8 * (i & 3));
    }
}

/* ---- the live values (2026-11-20) ------------------------------------------------------------------------------ */

static void ins_changed_all(void)               /* the UI (or a load): every record's header and SET made again */
{
    for (int t = 0; t < 16; t++) {
        ins_hdirty[t] = 1;
        ins_dirty[t] = 1;
    }
}

/* track T's SET (ins_cell) from its knobs and its last trig's locks -> 1 when a cell changed. The audio interrupt only */
static int cell_track(int t)
{
    u32 diff = 0;
    for (int j = 0; j < SLOTS; j++) {                   /* (2026-11-21) MIX out of the loop: no test a knob */
        int y = ins_sel[t][j] < TYPES ? ins_sel[t][j] : 0;
        const u8 *kv = ins_kv[t][j][y], *lk = ins_lk[t] + 7 * j;
        u16 *c = ins_cell[t] + 7 * j;
        for (int i = 0; i < 6; i++) {
            u16 x = (u16)((u32)(lk[i] != NO_LOCK ? lk[i] : kv[i]) << 8);
            diff |= (u32)(c[i] ^ x);
            c[i] = x;
        }
        u16 x = (u16)((u32)(lk[I_MIX] != NO_LOCK ? lk[I_MIX] : ins_mod[t][j]) << 8);
        diff |= (u32)(c[I_MIX] ^ x);
        c[I_MIX] = x;
    }
    return diff != 0;
}

/* (2026-11-21) track T's two records' headers (field 0, OFF at MIX 0, the routed knobs) and its TAPE's PGAIN bytes, after
 * a change of the types, the instances, AUTO, MIX's OFF or TAPE's PGAIN (ins_hdirty). The audio interrupt, when the
 * track's group is packed next: a track's work, never all 32 records in one block (the worst frame). TAPE's PGAIN keeps
 * its own change word (link.c), moved only when a byte differs */
static void hdr_track(int t)
{
    for (int j = 0; j < SLOTS; j++) {
        int r = 2 * t + j, y = ins_sel[t][j], s = sent_type(t, j), z = mix_off(t, j);
        u32 f0 = 0;
        if (!z && s) {
            f0 = (u32)s | (instances(s) ? (u32)ins_inst[t][j] << 4 : 0u);
            if ((y == T_FUZZ || y == T_TAPE) && ins_fza[t][j] >= 64)
                f0 |= 0x10u;                    /* FUZZ's or TAPE's AUTO (as fields()) */
        }
        hdr_f0[r] = (u8)f0;
        hdr_zero[r] = (u8)z;
        hdr_rmask[r] = (u8)(s && y < TYPES ? ROUTE_OK[y] | 1u << I_MIX : 0);
        u32 b = y == T_TAPE && !z ? (u32)((ins_tpg[t][j] - 64) & 0x7F) : 0u;   /* (as ins_tpg_words) */
        u32 sh = 8u * (u32)(r & 3), w = (ins_tpg_w[r >> 2] & ~(0xFFu << sh)) | b << sh;
        if (w != ins_tpg_w[r >> 2]) {
            ins_tpg_w[r >> 2] = w;
            ins_tpg_gen++;
        }
    }
}

/* records 4G..4G+3's eight fields as the DSP gets them now, two words each of 4 fields (7 bits each: field 0, MIX, K1, K2 |
 * K3..K6; dnfw.inserts.design.pack). A knob its type routes: SET plus the routes' offset, clamped to 0..127 (a cell
 * <= 0: 0, >= 0x7f00: 127, else >> 8); one it does not: SET >> 8; a record at MIX's OFF: both words 0. (2026-11-21, the
 * User's CPU) in assembly: csrc/inserts/hooks.S ins_live4 (the C's clamp was a call a routed knob) */
extern void ins_live4(const u16 *c, const s16 *o, const u8 *zero, const u8 *f0, const u8 *rmask, u32 *v);

#ifndef __m68k__
/* (2026-11-21, combined-67) the host's build (the C tests: test/test_inserts_c.py) has no hooks.S: the C before
 * cff8c1f4, verbatim, as the reference ins_live4 replaced (the ColdFire build compiles none of it) */
/* knob I of record R's cell as the DSP gets it (0..127): SET, plus the routes' offset when its type routes it */
#define LIVE(c, o, m, i) ((m) >> (i) & 1u ? clamp7((s32)(c)[i] + (o)[i]) : (u32)((c)[i] >> 8))
static inline u32 clamp7(s32 x)
{
    return x <= 0 ? 0u : x >= 0x7F00 ? 0x7Fu : (u32)x >> 8;
}

/* record R's eight fields as the DSP gets them now, as two words of 4 fields (7 bits each: field 0, MIX, K1, K2 | K3..K6;
 * dnfw.inserts.design.pack). 2026-11-21: straight into the words (no byte array), the unrouted knobs without a clamp
 * (a cell is 0..0x7F00 already) */
static void live_words(int r, u32 *a, u32 *b)
{
    if (hdr_zero[r]) {
        *a = *b = 0;
        return;
    }
    const u16 *c = ins_cell[r >> 1] + 7 * (r & 1);
    const s16 *o = ins_moff[r >> 1] + 7 * (r & 1);
    u32 m = hdr_rmask[r];
    *a = hdr_f0[r] | LIVE(c, o, m, I_MIX) << 7 | LIVE(c, o, m, 0) << 14 | LIVE(c, o, m, 1) << 21;
    *b = LIVE(c, o, m, 2) | LIVE(c, o, m, 3) << 7 | LIVE(c, o, m, 4) << 14 | LIVE(c, o, m, 5) << 21;
}
#endif

/* group G's 7 words into the packet (the layout of ins_words: words 0..6 fields 4w..4w+3, fields 28..31 the top
 * nibbles) -> 1 when a word changed. Its two tracks' headers first, when marked */
static int pack_group(u32 g)
{
    const volatile u8 *hd = ins_hdirty;
    for (u32 t = 2u * g; t < 2u * g + 2u; t++)
        if (hd[t]) {
            ins_hdirty[t] = 0;                  /* (cleared first: a mark meanwhile makes it again next time) */
            hdr_track((int)t);
        }
    u32 v[8];
#ifdef __m68k__
    ins_live4(ins_cell[2u * g], ins_moff[2u * g], hdr_zero + 4u * g, hdr_f0 + 4u * g, hdr_rmask + 4u * g, v);
#else
    for (int r = 0; r < 4; r++)
        live_words((int)(4u * g) + r, v + 2 * r, v + 2 * r + 1);
#endif
    u32 x = v[7], d = 0;                        /* fields 28..31: the 7 words' top nibbles */
    u32 *w = ins_pkt + 2 + 7 * g;
    for (int k = 0; k < 7; k++, x >>= 4) {
        u32 nw = v[k] | (x & 0xFu) << 28;
        d |= nw ^ w[k];
        w[k] = nw;
    }
    return d != 0;
}

/* every DSP block (link.c smp_tdm, in the audio interrupt): the headers after a change, the tracks the UI changed, one
 * group (ins_rr) packed, the groups a trig changed; the packet due after the last group, or at once after a trig */
void ins_period(void)
{
    init();
    const volatile u32 *dw = (const volatile u32 *)ins_dirty;
    if (dw[0] | dw[1] | dw[2] | dw[3])
        for (int t = 0; t < 16; t++)
            if (ins_dirty[t]) {
                ins_dirty[t] = 0;
                cell_track(t);
            }
    u32 g = ins_rr & (GROUPS - 1);
    if (ins_urgent[g]) {                        /* packed now anyway */
        ins_urgent[g] = 0;
        ins_due = 1;
        ins_urgents++;
    }
    pkt_changed |= pack_group(g);
    const volatile u32 *uw = (const volatile u32 *)ins_urgent;
    if (uw[0] | uw[1]) {                        /* (2026-11-21) at most URGENT_MAX more a block, the next after the
                                                 * round-robin's first: 16 tracks' trigs in 4 blocks, not one */
        u32 n = 0;
        for (u32 i = 1; i < GROUPS && n < URGENT_MAX; i++) {
            u32 k = (g + i) & (GROUPS - 1);
            if (ins_urgent[k]) {
                ins_urgent[k] = 0;
                pkt_changed |= pack_group(k);
                ins_due = 1;
                ins_urgents++;
                n++;
            }
        }
    }
    if (g == GROUPS - 1)
        ins_due = 1;                            /* the fixed phase: after the last group */
    ins_rr = (g + 1) & (GROUPS - 1);
}

/* link.c, sending the packet: its change word moved when its words differ from the last packet's -> the 58 words */
const u32 *ins_take(void)
{
    if (pkt_changed) {
        pkt_changed = 0;
        ins_pkt[0] = ++ins_chg;
    }
    ins_pkt[1] = 0;
    ins_due = 0;
    ins_pkts++;
    return ins_pkt;
}

/* csrc/slides sl_apply (the audio interrupt), a trig on track T: its insert locks (LK: K1..K6, MIX, a byte a slot as the
 * records hold them; 0 none), which the track's inserts take in place of the knobs until its next trig. A changed SET
 * packs its group at once and sends it in the next block. A MIX lock keeps the slot running (ins_keep) from now on */
void ins_trig(u32 t, const u16 *lk)
{
    if (t > 15u || !ins_inited)
        return;
    /* (2026-11-21) the locks taken and SET made in one pass (cell_track's values, the same for every case) */
    static const u16 none[7] = {0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu, 0xFFFFu};
    const u16 *w = lk ? lk : none;
    u8 *l = ins_lk[t];
    u16 *c = ins_cell[t];
    int y0 = ins_sel[t][0] < TYPES ? ins_sel[t][0] : 0, y1 = ins_sel[t][1] < TYPES ? ins_sel[t][1] : 0;
    const u8 *kv0 = ins_kv[t][0][y0], *kv1 = ins_kv[t][1][y1];
    u32 diff = 0;
    for (u32 k = 0; k < 6u; k++) {
        u32 a = w[k] & 0xFFu, b = (u32)w[k] >> 8;
        a = a > 127u ? NO_LOCK : a;
        b = b > 127u ? NO_LOCK : b;
        l[k] = (u8)a;
        l[7 + k] = (u8)b;
        u16 x0 = (u16)((a != NO_LOCK ? a : kv0[k]) << 8), x1 = (u16)((b != NO_LOCK ? b : kv1[k]) << 8);
        diff |= (u32)(c[k] ^ x0) | (u32)(c[7 + k] ^ x1);
        c[k] = x0;
        c[7 + k] = x1;
    }
    u32 a = w[I_MIX] & 0xFFu, b = (u32)w[I_MIX] >> 8;
    a = a > 127u ? NO_LOCK : a;
    b = b > 127u ? NO_LOCK : b;
    l[I_MIX] = (u8)a;
    l[7 + I_MIX] = (u8)b;
    u16 x0 = (u16)((a != NO_LOCK ? a : ins_mod[t][0]) << 8), x1 = (u16)((b != NO_LOCK ? b : ins_mod[t][1]) << 8);
    diff |= (u32)(c[I_MIX] ^ x0) | (u32)(c[7 + I_MIX] ^ x1);
    c[I_MIX] = x0;
    c[7 + I_MIX] = x1;
    if (a != NO_LOCK && !ins_keep[t][0]) {
        ins_keep[t][0] = 1;                     /* the UI pass's scan had not seen it yet */
        ins_hdirty[t] = 1;                      /* (its group is packed at once below: the header with it) */
    }
    if (b != NO_LOCK && !ins_keep[t][1]) {
        ins_keep[t][1] = 1;
        ins_hdirty[t] = 1;
    }
    if (diff) {
        ins_urgent[t >> 1] = 1;
        ins_trigs++;
    }
}

/* the matrix's (matrix.c mx_eval): the group packed next, its two tracks */
u32 ins_next_group(void)
{
    return ins_rr & (GROUPS - 1);
}

/* the UI pass (page.c wr_poll): each slot's ins_keep, a MIX route (the matrix's) or a MIX lock in the UI track's pattern
 * (its lock pool) or now (the last trig's); looked at 5 times a second */
void ins_ui_poll(void)
{
    extern u32 mx_ins_routes(u32 t);            /* matrix.c: bit i, a route into knob i of track t */
    extern u8 *sl_ui_pool(void);
    extern const u8 *sl_ins_record(const u8 *table, u32 t, u32 k);
    static u32 at __attribute__((section(".data"))) = 0;
    u32 now = INS_FRAMES;
    if (!ins_inited || now - at < 300u)
        return;
    at = now;
    const u8 *table = sl_ui_pool();
    for (u32 t = 0; t < 16u; t++) {
        u32 rt = mx_ins_routes(t), lks = 0;
        const u8 *rec = table ? sl_ins_record(table, t, I_MIX) : 0;
        for (u32 s = 0; rec && s < 128u && lks != 3u; s++) {
            u32 w = *(const u16 *)(rec + 2 + 2 * s);
            lks |= ((w & 0xFFu) <= 127u ? 1u : 0u) | ((w >> 8) <= 127u ? 2u : 0u);
        }
        for (u32 j = 0; j < SLOTS; j++) {
            u8 k = (u8)((rt >> (7 * j + I_MIX) & 1u) || (lks >> j & 1u) || ins_lk[t][7 * j + I_MIX] != NO_LOCK);
            if (k != ins_keep[t][j]) {
                ins_keep[t][j] = k;
                ins_hdirty[t] = 1;              /* (2026-11-21) its headers: MIX 0 = OFF or not */
            }
        }
    }
}

/* the place K (0..5: B..G, 6: H MIX) of the INSERT page up -> its knob index i (0..13, 7 j + field), or -1: an empty
 * place, AUTO, TAPE's PGAIN (no stored field) */
static int knob_of_place(int k)
{
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j];
    if (!ins_up || !y || y >= TYPES || k < 0 || k > 6)
        return -1;
    if (k == 6)
        return 7 * j + I_MIX;
    int f = field_of(y, ins_pg, k);
    return f >= 0 && f < 6 ? 7 * j + f : -1;
}

/* the routes popup (csrc/matrix/routes_pop.c) on an INSERT page, encoder K (0 A .. 7 H) pushed: the knob's destination
 * (INS_DEST + i) when routes may move it (ROUTE_OK; MIX always), else 0. *NAME its label */
u32 ins_route_dest(u32 k, const char **name)
{
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j];
    int i = k >= 1u && k <= 7u ? knob_of_place((int)k - 1) : -1;
    if (i < 0)
        return 0;
    int f = i - 7 * j;
    if (f != I_MIX && !(ROUTE_OK[y] >> f & 1u))
        return 0;
    *name = f == I_MIX ? "MIX" : ins_pg ? LABEL2[y][k - 1] : LABEL[y][k - 1];
    return INS_DEST + (u32)i;
}

/* knob I of track T (the routes popup's header and the moving line): what the DSP gets (*HEARD) and the page's knob
 * (*SET), both as cells (<< 8) */
void ins_knob_now(u32 t, u32 i, int *heard, int *set)
{
    t &= 15u;
    i = i < INS_N ? i : 0u;
    u32 j = i / 7u, f = i % 7u, r = 2u * t + j, y = ins_sel[t][j] < TYPES ? ins_sel[t][j] : 0u;
    s32 x = (s32)ins_cell[t][i] + ((hdr_rmask[r] >> f & 1u) ? ins_moff[t][i] : 0);
    x = x < 0 ? 0 : x > 0x7F00 ? 0x7F00 : x;
    *heard = hdr_zero[r] ? 0 : x & 0x7F00;
    *set = (int)(f == I_MIX ? ins_mod[t][j] : ins_kv[t][j][y][f]) << 8;
}

/* store.c's view: slot (t, j)'s record as saved (type, MIX, the type's knobs), and its setting back */
void ins_record(int t, int j, u8 *f)
{
    init();
    int y = ins_sel[t][j];
    f[0] = (u8)y;
    f[1] = (u8)(ins_mod[t][j] | ((y == T_FUZZ || y == T_TAPE) && ins_fza[t][j] >= 64 ? 0x80 : 0));   /* AUTO: MIX's
                                                 * bit 7 (an older build masks it: the insert loads, without AUTO) */
    int s = y == T_TAPE ? ins_tpg[t][j] - 64 : 0;   /* TAPE's PGAIN, 6-bit two's complement dB in K1..K6's bit 7 */
    for (int k = 0; k < 6; k++)
        f[2 + k] = (u8)(ins_kv[t][j][y][k] | ((s >> k) & 1) << 7);
}

void ins_set_record(int t, int j, const u8 *f)
{
    init();
    int y = f[0] < TYPES ? f[0] : 0;            /* a type this build does not know: OFF */
    ins_sel[t][j] = (u8)y;
    ins_selv[t][j] = (u8)((POS[y] * 128 + 64) / TYPES);   /* the middle of its band, by display position */
    ins_mod[t][j] = f[1] & 0x7F;
    if (y == T_FUZZ || y == T_TAPE)
        ins_fza[t][j] = f[1] & 0x80 ? 127 : 0;
    if (y == T_TAPE) {
        int s = 0;
        for (int k = 0; k < 6; k++)
            s |= (f[2 + k] >> 7) << k;
        ins_tpg[t][j] = (u8)(64 + (s >= 32 ? s - 64 : s));
    }
    for (int k = 0; k < 6; k++)
        ins_kv[t][j][y][k] = f[2 + k] & 0x7F;
    ins_inst[t][j] = NO_INST;
}

/* after a whole set of records (a project loaded): instances given out anew, the DSP told */
void ins_loaded(void)
{
    reassign();
    for (int t = 0; t < 16; t++)
        for (int i = 0; i < INS_N; i++)
            ins_lk[t][i] = NO_LOCK;             /* (2026-11-20: the last project's trigs' locks forgotten) */
    ins_gen++;
    ins_changed_all();
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
}

static int clamp(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

static u8 *value_of(int t, int j, int y, int f)  /* a place's value: a stored field, AUTO, TAPE's PGAIN */
{
    return f == X_AUTO ? &ins_fza[t][j] : f == X_TPG ? &ins_tpg[t][j] : &ins_kv[t][j][y][f];
}

/* 2026-11-19 (the User: "auto gain should be off by default on our disto FXs"): a distortion picked starts with AUTO OFF.
 * A slot keeps every type's knobs (ins_kv) and FUZZ and TAPE share its one AUTO (ins_fza), so a pick brought back the
 * ON last set on that slot (that type, or FUZZ for TAPE), even from a project loaded before. Only a pick: a loaded
 * project keeps its stored AUTO (no conversion), and M.SEL moved inside a type's band is no pick */
static int auto_place(int y)                    /* the place of type Y's AUTO on page 1, or -1 */
{
    for (int k = 0; k < 6; k++)
        if (LABEL[y][k] == AUTO_LABEL)
            return k;
    return -1;
}

static void auto_off(int t, int j)
{
    int y = ins_sel[t][j], k = auto_place(y);
    if (k >= 0)
        *value_of(t, j, y, field_of(y, 0, k)) = 0;
}

/* slot (t, j) has just changed its type from WAS (M.SEL turned, INSERT SEL's pick) */
static void picked(int t, int j, int was)
{
    ins_mod[t][j] = 0;                          /* 2026-11-16 (the User, A): a type picked starts at MIX 0, no effect and no DSP
                                                 * (sent as OFF) until MIX is turned up; a loaded project keeps its MIX */
    auto_off(t, j);                             /* 2026-11-19: and a distortion with AUTO OFF */
    if (instances(was) && ins_inst[t][j] != NO_INST)
        ins_inst[t][j] = NO_INST;               /* given back */
    assign(t, j);
    reassign();
}

static void changed(void)
{
    ins_gen++;
    ins_edits++;
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
}

extern u32 sl_ins_held(u32 k, u32 j);          /* csrc/slides: a held trig's lock of slot J (0xff none, 0x10000 none held) */
extern int sl_ins_set(u32 k, u32 j, u32 value);
static int knob_of_place(int k);

/* 2026-11-20 (the User, 10a): a trig held, knob KNOB (2..7 B..G, 8 MIX) turned: the step's lock on every held step, from
 * the lock it holds or else the knob's value (as stock's own locks start). M.SEL, AUTO of FUZZ / TAPE and TAPE's PGAIN
 * are not lockable: turned with a trig held, nothing. A full pool refuses (19a) */
static void lock_turn(int knob, int delta)
{
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j];
    int k = knob == 8 ? 6 : knob - 2, i = knob_of_place(k);
    if (i < 0 || !delta)
        return;
    u32 f = (u32)(i - 7 * j), cur = sl_ins_held(f, (u32)j);
    int o = cur <= 127u ? (int)cur : f == I_MIX ? ins_mod[t][j] : ins_kv[t][j][y][f], x;
    if (f != I_MIX && !ins_pg && LABEL[y][k] == AUTO_LABEL)
        x = delta > 0 ? 127 : 0;                /* a switch, as the knob's own turn */
    else
        x = clamp(o + delta, 0, 127);
    if (x == o && cur <= 127u)
        return;
    sl_ins_set(f, (u32)j, (u32)x);
    touched = k == 6 ? 7 : k;
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
}

static void turn(int knob, int delta)
{
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1;
    if (sl_ins_held(0, 0) != 0x10000u) {        /* a trig held: locks only (2026-11-20) */
        if (knob >= 2)
            lock_turn(knob, delta);
        return;
    }
    if (knob == 1) {
        /* as a stock multi-choice: turned as a 0..127 knob, each type a band of it (about 9 of it
         * for fourteen types, in ORDER: OFF 0..9, CHOR 10..18 .. XDLY 119..127), so a type takes a band
         * of a turn of the range, not one step */
        int was = ins_sel[t][j];
        ins_selv[t][j] = (u8)clamp(ins_selv[t][j] + delta, 0, 127);
        ins_sel[t][j] = ORDER[ins_selv[t][j] * TYPES / 128];
        if (ins_sel[t][j] != was)
            picked(t, j, was);
        ins_changed_all();                      /* (the types, the instances: every header) */
    } else if (knob == 8) {
        ins_mod[t][j] = (u8)clamp(ins_mod[t][j] + delta, 0, 127);
        touched = 7;
        ins_hdirty[t] = 1;                      /* (MIX 0 = OFF: the header) */
    } else {
        touched = knob - 2;
        int y = ins_sel[t][j], f = field_of(y, ins_pg, knob - 2);
        if (y && f >= 0) {
            u8 *v = value_of(t, j, y, f);
            if (!ins_pg && LABEL[y][knob - 2] == AUTO_LABEL)
                *v = delta > 0 ? 127 : delta < 0 ? 0 : *v;   /* a switch */
            else if (f == X_TPG)
                *v = (u8)clamp(*v + delta, 32, 95);   /* -32 .. +31 dB */
            else
                *v = (u8)clamp(*v + delta, 0, 127);
            if (f == X_AUTO || f == X_TPG || LABEL[y][knob - 2] == AUTO_LABEL)
                ins_hdirty[t] = 1;              /* (field 0's AUTO bit, TAPE's PGAIN: the headers) */
        }
    }
    ins_dirty[t] = 1;                           /* (2026-11-20) the track's SET again (ins_period) */
    changed();
}

/* INSERT SEL (csrc/msel/msel.c isel_*, 2026-11-20, the User: "same code/ui as filter and synth engine"): the active
 * track's slot J. Its type; a pick (as M.SEL turned to the middle of that type's band); both slots kept when the page
 * opens and put back on NO with LIVE SELECT on (as MACHINE SEL keeps the machine and the filter, msel.c ls_save); the
 * INSERT page under it switched to slot J (LEFT / RIGHT, as MACHINE SEL's pages) */
static struct {
    u8 sel, selv, mod, fza, tpg, inst, kv[TYPES][6];
} kept[SLOTS] __attribute__((section(".data")));
static int kept_t __attribute__((section(".data"))) = -1;

int ins_isel_type(int j)
{
    init();
    return ins_sel[UI_TRACK & 15][j & 1];
}

void ins_isel_pick(int j, int type)
{
    init();
    int t = UI_TRACK & 15, was = ins_sel[t][j & 1];
    if (type < 0 || type >= TYPES || type == was)
        return;
    ins_sel[t][j & 1] = (u8)type;
    ins_selv[t][j & 1] = (u8)((POS[type] * 128 + 64) / TYPES);   /* the middle of its band, by display position */
    picked(t, j & 1, was);
    ins_changed_all();                          /* (live inserts: every header and SET) */
    changed();
}

void ins_isel_keep(void)
{
    init();
    int t = UI_TRACK & 15;
    kept_t = t;
    for (int j = 0; j < SLOTS; j++) {
        kept[j].sel = ins_sel[t][j];
        kept[j].selv = ins_selv[t][j];
        kept[j].mod = ins_mod[t][j];
        kept[j].fza = ins_fza[t][j];
        kept[j].tpg = ins_tpg[t][j];
        kept[j].inst = ins_inst[t][j];
        for (int y = 0; y < TYPES; y++)
            for (int k = 0; k < 6; k++)
                kept[j].kv[y][k] = ins_kv[t][j][y][k];
    }
}

int ins_isel_back(void)                         /* -> 1 when the slots were put back */
{
    int t = kept_t;
    if (t != (UI_TRACK & 15))                   /* nothing kept, or another track since: left as it is */
        return 0;
    for (int j = 0; j < SLOTS; j++) {
        if (instances(ins_sel[t][j]) && ins_inst[t][j] != NO_INST && ins_sel[t][j] != kept[j].sel)
            ins_inst[t][j] = NO_INST;           /* given back */
        ins_sel[t][j] = kept[j].sel;
        ins_selv[t][j] = kept[j].selv;
        ins_mod[t][j] = kept[j].mod;
        ins_fza[t][j] = kept[j].fza;
        ins_tpg[t][j] = kept[j].tpg;
        for (int y = 0; y < TYPES; y++)
            for (int k = 0; k < 6; k++)
                ins_kv[t][j][y][k] = kept[j].kv[y][k];
    }
    for (int j = 0; j < SLOTS; j++)
        if (kept[j].inst != NO_INST && ins_sel[t][j] == kept[j].sel)
            ins_inst[t][j] = kept[j].inst;      /* its own instance, if no other slot took it since */
    for (int j = 0; j < SLOTS; j++)
        assign(t, j);
    reassign();
    kept_t = -1;
    ins_changed_all();                          /* (live inserts: every header and SET) */
    changed();
    return 1;
}

static void fx_open(int to, int pg);

void ins_isel_show(int j)
{
    if (ins_up && ((ins_up - 1) & 1) != (j & 1))
        fx_open(1 + (j & 1), 0);
}

/* 2026-11-19: FUNC + long push on an INSERT page (csrc/matrix/routes_pop.c mxp_poll; the routes popup is refused here):
 * knob K's place (B..G, the page shown) back to its default, as a stock page's parameter goes back to its record's:
 * AUTO OFF, TAPE's PGAIN 0 dB, a stored field the type's DEFAULT. M.SEL (A) and MIX (H) are left as they are. -> 1 when
 * a place was reset, 0 when not ours (no INSERT page up, A, H, an empty place) */
int ins_knob_reset(int k)
{
    init();
    if (!ins_up || k < 1 || k > 6)
        return 0;
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j], f = field_of(y, ins_pg, k - 1);
    if (!y || f < 0)
        return 0;
    *value_of(t, j, y, f) = f == X_AUTO ? 0 : f == X_TPG ? 64 : DEFAULT[y][f];
    touched = k - 1;
    ins_armed = 0;
    ins_changed_all();
    ins_gen++;
    ins_edits++;
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
    return 1;
}

/* 2026-11-19: FUNC + an encoder's push pressed (routes_pop.c mxp_pop takes the push before ins_pop sees it): FUNC is a
 * modifier now, so its release is no FUNC tap (it switched FUZZ's or TAPE's page under a reset) */
void ins_func_push(void)
{
    ins_armed = 0;
}

static int ram_ok(u32 a)
{
    return a >= 0x40000000u && a < 0x48000000u && !(a & 3);
}

static u32 view_of(u32 cls)                     /* the screen's view of class CLS, or 0 */
{
    extern void *wr_screen_obj;
    u32 s = (u32)wr_screen_obj;
    if (!ram_ok(s))
        return 0;
    u32 node = *(volatile u32 *)(s + 28);
    for (int n = 0; n < 32 && ram_ok(node) && node != s + 20; n++) {
        u32 v = *(volatile u32 *)(node + 8);
        if (ram_ok(v) && *(volatile u32 *)v == cls)
            return v;
        node = *(volatile u32 *)node;
    }
    return 0;
}

u32 ins_view_of(u32 cls)                        /* csrc/scope/scope.c: the AMP page's view */
{
    return view_of(cls);
}

static void *title(void)                        /* the title bar's message line, or 0 */
{
    u32 v = view_of(TITLE_VTABLE);
    u32 m = v ? *(volatile u32 *)(v + 120) : 0;
    return ram_ok(m) ? (void *)m : 0;
}

static void say(const char *text, int slide)    /* slide: as stock's switch; else the text alone */
{
    static u32 str[4] __attribute__((section(".data")));
    static u32 alloc __attribute__((section(".data")));
    void *m = title();
    if (!m)
        return;
    str[0] = str[1] = str[2] = str[3] = 0;
    STR_NEW(str, text, &alloc);
    if (slide)
        SAY(m, str);
    else
        STR_SET((u8 *)m + 0x48, str);
    STR_FREE(str);
}

void ins_say(const char *text, int slide)       /* csrc/scope/scope.c: "ENV2" */
{
    say(text, slide);
}

const char *ins_title_now(void)                 /* the checks: the title bar's text, or 0 */
{
    void *m = title();
    const char *t = m ? *(const char *volatile *)((u8 *)m + 0x48) : 0;
    return t && ram_ok((u32)t & ~3u) ? t : 0;
}

static const char *const PAGE_NAME[PAGES] = {"FX (1/3)", "FX (2/3)", "FX (3/3)"};

/* hooks.S ins_hdr_tail, at the exit of stock's mode header 0x40063f56 (mode, a0 = the std::string
 * it returns): the mode's page name, with " (n/m)" only when the mode has two pages or more. The
 * track FX mode has one, so stock's header for it is a bare "FX", and every route to the page that
 * shows the header (from a SEND page, whose header mode stock keeps) showed "FX". Here a bare "FX"
 * becomes "FX (1/3)", or "FX (2/3)" / "FX (3/3)" while an INSERT page is up: the header as stock
 * would make it for a mode of three pages. No other mode is named "FX".
 * 2026-11-13 (the User): the AMP mode's bare "AMP" becomes "ENV1/AMP", page 1 of AMP's two (csrc/scope/scope.c
 * names the other). No other mode is named "AMP". 2026-11-18: its "Amplitude" too (the name stock shows entering
 * the AMP page from another page): renamed here, the page's first frame says ENV1/AMP, as stock's pages say their
 * names; scope_dots renamed it after that draw, so the bar said it a draw later (12 ticks, emulator,
 * scripts/emu_page_keys.py). */
static int title_is(const char *t, const char *w)
{
    while (*w && *t == *w)
        t++, w++;
    return !*w && !*t;
}

void ins_header(void *s)
{
    extern const char *const amp_title1;        /* csrc/scope/scope.c */
    static u32 str[4] __attribute__((section(".data")));
    static u32 alloc __attribute__((section(".data")));
    const char *t = s && ram_ok((u32)s) ? *(const char *volatile *)s : 0, *name;
    if (!(t && ram_ok((u32)t & ~3u)))
        return;
    if (t[0] == 'F' && t[1] == 'X' && t[2] == 0)
        name = PAGE_NAME[ins_up % PAGES];
    else if ((t[0] == 'A' && t[1] == 'M' && t[2] == 'P' && t[3] == 0) || title_is(t, "Amplitude"))
        name = amp_title1;
    else
        return;
    str[0] = str[1] = str[2] = str[3] = 0;
    STR_NEW(str, name, &alloc);
    STR_SET(s, str);
    STR_FREE(str);
}

/* The item's icon in the title bar (2026-11-20, the User: "also show icon on synth engine and fx and filter engine in title
 * bar"; place A, scratch/fx-icons-titlebar.png): while the title bar's message line shows the page's name (its time left,
 * the line's +0x4C, above 0: scripts/emu_scope.py message_left), on the SYN pages the track's machine's icon, on the FLTR
 * pages its filter's, on an INSERT page the slot's insert's (dnfw.waverider.msel's tables, msel.c msel_icon_of), at the
 * line's right end once it has slid in: x 118..126, rows 1..7 from the top lit, the icon's 7 x 5 unlit in it at x 119, row 2. The pages by
 * their view (one walk of the screen's views): the SYN page's class is the same for every machine (measured 2026-11-20
 * in the 1.12 emulator: FM TONE, WAVETONE, two of ours; not up on FLTR or AMP). Cost (the User is tight on CPU): one
 * walk of the views a screen draw; drawn, nine column words written straight into the canvas (no SET_PIXEL); measured by
 * the titleicon step (scripts/ship_gate.py), ttl_off its control */
#define SYN_VTABLE  0x401D4DB0u
#define FLTR_VTABLE 0x401E24C4u
#define KIT_POINTER (*(u8 *volatile *)0x800052A0u)
u8 ttl_off __attribute__((section(".data"))) = 0;    /* the checks: 1, nothing drawn (the cost's control) */
u32 ttl_draws __attribute__((section(".data"))) = 0;
extern const u8 *msel_icon_of(int kind, int type);     /* csrc/msel/msel.c: 1 a machine, 2 a filter, 3 an insert */

static u32 ttl_tv __attribute__((section(".data"))) = 0;     /* the title bar's view, last found */
static int ttl_kind __attribute__((section(".data"))) = -1, ttl_type __attribute__((section(".data"))) = -1;
static u32 ttl_col[7] __attribute__((section(".data")));     /* that icon's columns, as the canvas's bits 2..6 */
static int ttl_have __attribute__((section(".data"))) = 0;   /* ... it has one */

/* the message line M shows a page name, slid in: its time left (+0x4C) above 0 and its byte +0x54 set, after a slide was
 * seen (+0x54 clear while it slides; measured 2026-11-20, 1.12 emulator: idle 0 / 1; sliding 0x75.. / 0; shown n / 1;
 * the moment a page is switched a draw can see the new time with the idle byte still set: no icon then). The slide is
 * seen by ins_title_poll (every UI pass; it lasts some 16 panel ticks) and by the draws */
/* (2026-11-21, the lineonly step on v0.66.1/v0.67.1: the glass without the icon, a full redraw with it) +0x54 is not
 * clear only while the name slides: measured on every page (MONOMACHINE, ONESHOT, WaveTone; 1.12 emulator), it is clear
 * 4 counts of the time left in every 14 for as long as the name is up (about 0.13 s in 0.46 s). Read every time, it
 * dropped the icon from any full draw in those phases (a knob's redraw: the icon flickered off) and asked a full redraw
 * at each phase's end (8 for one page name). Now the name counts as up from the first clear phase's end until the
 * line's time runs out (a page change while a name is up keeps it, as before: the next page's icon at once) */
static int ttl_slid __attribute__((section(".data"))) = 0;      /* 0 not seen sliding, 1 seen sliding, 2 slid in */
static int ttl_name_up(u32 m)
{
    if (!ram_ok(m) || *(volatile int *)(m + 0x4C) <= 0) {
        ttl_slid = 0;
        return 0;
    }
    if (ttl_slid == 2)
        return 1;
    if (!*(volatile u8 *)(m + 0x54)) {
        ttl_slid = 1;
        return 0;
    }
    if (ttl_slid == 1)
        ttl_slid = 2;
    return ttl_slid == 2;
}

/* page.c wr_poll, every UI pass: a page name has just slid in: one redraw, so its icon comes with it (stock draws the
 * last step of the slide before it marks the line shown: without this the icon waited for the next redraw) */
void ins_title_poll(void)
{
    static int was __attribute__((section(".data"))) = 0;
    if (ttl_off || !ram_ok(ttl_tv) || *(volatile u32 *)ttl_tv != TITLE_VTABLE)
        return;
    int up = ttl_name_up(*(volatile u32 *)(ttl_tv + 120));
    if (up && !was) {
        extern int smp_overlay_dirty;
        smp_overlay_dirty = 1;
    }
    was = up;
}

void ins_title_icon(void *c)
{
    extern void *wr_screen_obj;
    u32 s = (u32)wr_screen_obj;
    if (ttl_off || !ram_ok(s))
        return;
    if (!ram_ok(ttl_tv) || *(volatile u32 *)ttl_tv != TITLE_VTABLE)
        ttl_tv = view_of(TITLE_VTABLE);         /* (the walk only when the one kept is gone) */
    u32 m = ttl_tv ? *(volatile u32 *)(ttl_tv + 120) : 0;
    if (!ttl_name_up(m))
        return;                                 /* no page name up, or not slid in yet: the usual case, a few
                                                 * instructions */
    int kind = 0, t = UI_TRACK & 15, type;
    if (ins_up) {
        kind = 3;
        type = ins_sel[t][(ins_up - 1) & 1];
    } else {
        u32 node = *(volatile u32 *)(s + 28);   /* the page's view: SYN or FLTR */
        for (int n = 0; n < 32 && !kind && ram_ok(node) && node != s + 20; n++) {
            u32 v = *(volatile u32 *)(node + 8);
            if (ram_ok(v))
                kind = *(volatile u32 *)v == SYN_VTABLE ? 1 : *(volatile u32 *)v == FLTR_VTABLE ? 2 : 0;
            node = *(volatile u32 *)node;
        }
        const u8 *snd = KIT_POINTER;
        if (!kind || !snd)
            return;
        snd += 52u + 1163u * (u32)t;
        type = kind == 1 ? (s8)snd[0xDE] : snd[0xDF];
    }
    if (kind != ttl_kind || type != ttl_type) { /* another item: its columns made once */
        const u8 *ic = msel_icon_of(kind, type);
        ttl_kind = kind;
        ttl_type = type;
        for (int i = 0; i < 7; i++) {
            u32 col = 0;
            for (int r = 0; ic && r < 5; r++)
                col |= (u32)(ic[r] >> (6 - i) & 1) << (2 + r);
            ttl_col[i] = ~col;
        }
        ttl_have = ic != 0;
    }
    const int *h = (const int *)c;
    if (!ttl_have || h[1] != 128 || h[2] != 64)
        return;
    /* column x: its word for rows 0..31 from the top is x * stride + 1 (y up 32..63), row r its bit r */
    int st = h[3];
    u32 *w = (u32 *)h[4] + 1 + 118 * st;
    *w |= 0xFEu;
    for (int i = 0; i < 7; i++) {
        w += st;
        *w = (*w | 0xFEu) & ttl_col[i];
    }
    w[st] |= 0xFEu;
    ttl_draws++;
}

int ins_fx_page(void)                           /* stock's track FX page is the page */
{
    return view_of(FX_PAGE_VTABLE) != 0;
}

/* page.c wr_screen, before stock draws: while FX 1/3 is up, any "FX" of stock's in the title bar's
 * message line is renamed "FX (1/3)" (stock puts "FX" there entering the page; from the SEND pages it
 * does not slide it in, so ins_dots slides ours in after the first draw on the page) */
void ins_title(void)
{
    if (ins_up || !(title_due || ins_fx_page()))
        return;
    void *m = title();
    const char *t = m ? *(const char *volatile *)((u8 *)m + 0x48) : 0;
    int fx = t && ram_ok((u32)t & ~3u) && t[0] == 'F' && t[1] == 'X' && t[2] == 0;
    if (fx) {                                   /* stock's "FX": renamed (its slide, if any, kept) */
        say(PAGE_NAME[0], 0);
        title_due = 0;                          /* (2026-11-18) named in this first frame: no slide after it */
    }
    if (title_due && !ins_fx_page())
        title_due--;
}

/* page.c wr_screen, after stock's page, when no page of ours covers it: FX 1/3's dots */
void ins_dots(void *c)
{
    if (!ins_up && ins_fx_page()) {
        PAGE_DOTS(0, c, PAGES, 0, 7);
        if (title_due) {                        /* just entered by FX: "FX (1/3)" slides in (after
                                                 * stock's own draw, which sets the page's header) */
            title_due = 0;
            say(PAGE_NAME[0], 1);
        }
    }
}

/* FX's page TO (0 stock's FX 1/3, 1 INSERT 1, 2 INSERT 2), as [FX] steps to it: the insert's page PG (0 its page 1, as
 * [FX] opens it; 1 its page 2, UP / DOWN among the page 2s), its title slid in */
static void fx_open(int to, int pg)
{
    extern int smp_overlay_dirty;
    ins_pg = pg_open = pg;
    ins_up = to;
    touched = -1;
    smp_overlay_dirty = 1;
    say(PAGE_NAME[to], 1);
}

/* UP / DOWN on the FX pages (2026-11-20, the User: "UP/DOWN should page through the pages of AMP and FX ... like any
 * other pages"). Stock's rule on its own pages, measured in the 1.12 emulator (scripts/emu_updown_pages.py): DOWN the
 * next page, UP the previous one, on the press and on each repeat, stopping at the ends (no wrap); not with FUNC held
 * (stock's FUNC + arrows go on); a trig held, KEYBOARD on, grid recording change nothing. Stock's FX page alone has one
 * page and does nothing with them. A step is [FX]'s own (fx_open). The lists and popups of ours that take the arrows
 * have them before this (rec.c smp_ui_pop), FX held (its overview, a modifier) leaves them to stock.
 * Two sets of pages, never mixed (the User, 2026-11-20: "stays within the FUNC / no-FUNC pages"): the pages [FX] steps
 * (FX 1/3, 2/3, 3/3, each insert on its page 1), and the inserts' page 2s (FUZZ, TAPE: the FUNC tap): from a page 2 the
 * arrows go to the other slot's page 2 when its insert has one, else nowhere.
 * -> 1 when the item is ours: a step, or any arrow while an INSERT page is up (nothing under it moves) */
static int fx_arrow(u32 code)
{
    if (KEY_HELD(K_FUNC) || KEY_HELD(K_FX) || !(ins_up || ins_fx_page()))
        return 0;
    int to = ins_up + (code == K_DOWN ? 1 : -1);
    if (ins_up && ins_pg) {                     /* a page 2: among the page 2s */
        if (to >= 1 && to < PAGES && has_page2(ins_sel[UI_TRACK & 15][(to - 1) & 1]))
            fx_open(to, 1);
        return 1;
    }
    int step = to >= 0 && to < PAGES;
    if (step)
        fx_open(to, 0);
    return step || ins_up;
}

/* from rec.c smp_ui_pop, before its own handling: 1 when the item is ours (it is then dropped) */
int ins_pop(u8 *it)
{
    init();
    u32 code = (u32)it[4] << 24 | (u32)it[5] << 16 | (u32)it[6] << 8 | it[7];
    u32 flags = (u32)it[8] << 24 | (u32)it[9] << 16 | (u32)it[10] << 8 | it[11];
    int press = (flags & 1u) && !(flags & 0x10u);
    extern int smp_overlay_dirty;
    if (ins_up && it[0] == IT_KEY && code >= 41 && code <= 48) {
        ins_armed = 0;
        if (press && code >= 42 && sl_ins_held(0, 0) != 0x10000u) {   /* (2026-11-20) a trig held + a push: that place's
                                                 * lock cleared on the held steps, as stock's trig + push */
            int i = knob_of_place(code == 48 ? 6 : (int)code - 42), j = (ins_up - 1) & 1;
            if (i >= 0) {
                sl_ins_set((u32)(i - 7 * j), (u32)j, 0xFFu);
                smp_overlay_dirty = 1;
            }
        }
        return 1;                               /* an encoder's push (and its release): ours while up, so
                                                 * the stock page under it does not switch to its values */
    }
    /* 2026-11-13 (main: as the send pages' second page, csrc/fxpage/fxp.c): a FUNC TAP (FUNC pressed and released with
     * no other key, push or turn between) switches an insert with a page 2 (FUZZ) between its pages; FUNC goes on to
     * stock as ever */
    if (it[0] == IT_KEY && code == K_FUNC && !(flags & 8u)) {
        if (press)
            ins_armed = ins_up && has_page2(ins_sel[UI_TRACK & 15][(ins_up - 1) & 1]);
        else if (ins_armed && ins_up) {
            ins_armed = 0;
            ins_pg ^= 1;
            touched = -1;
            smp_overlay_dirty = 1;
        }
        return 0;
    }
    if (it[0] == IT_KEY || it[0] == IT_KNOB)    /* any other key, push or turn: FUNC is a modifier now (2026-11-20: */
        ins_armed = 0;                          /* not the queue's other items: in the emulator one comes every 4 panel
                                                 * ticks, and the tap never got through; fxp.c's tap reads keys and knobs
                                                 * alone, as here now) */
    if (it[0] == IT_KEY && press && (code == K_UP || code == K_DOWN))
        return fx_arrow(code);                  /* (a repeat too, as stock's pages step on it) */
    if (it[0] == IT_KEY && press && !(flags & 8u)) {
        if (code == K_FX) {
            extern u32 ovw_pass;                /* ovw.c: a held-back press on stock's FX page, for stock's value
                                                 * view alone; the step comes with the tap played on the release */
            if (ovw_pass == K_FX) {
                ovw_pass = 0;
                if (!ins_up && !ins_fx_page())  /* (2026-11-18) from another page stock enters FX 1/3 on the press: */
                    title_due = 40;             /* its "FX" renamed, as for the tap played before */
                return 0;
            }
            if (KEY_HELD(K_FUNC)) {             /* FUNC + FX: stock's SEND pages, as stock */
                if (ins_up) {
                    ins_up = 0;
                    smp_overlay_dirty = 1;
                }
                title_due = 0;
                return 0;
            }
            if (ins_up || ins_fx_page()) {      /* FX 1/3 -> 2/3 -> 3/3 -> 1/3 (stock's page, under ours) */
                fx_open((ins_up + 1) % PAGES, 0);
                return 1;
            }
            title_due = 40;                     /* stock goes to FX 1/3: its "FX" renamed */
            return 0;
        }
        if (ins_up && code == K_NO) {
            ins_up = 0;
            smp_overlay_dirty = 1;
            return 1;
        }
        /* b6 (the User: VOICE from FX 2/2 showed both screens): every key closes the page but the
         * ones that belong on it (FUNC, YES and the arrows 10..15, the trig keys 25..40, the encoder
         * pushes 41..48); a list of the closing keys missed VOICE (49), the arpeggiator (53), note
         * edit (55) and others, whose stock screens then had the page drawn over them */
        if (ins_up && !(code == K_FUNC || (code >= 10 && code <= 15) || (code >= 25 && code <= 48))) {
            ins_up = 0;                         /* the key does what it does; the page closes */
            smp_overlay_dirty = 1;
        }
        return 0;
    }
    if (ins_up && it[0] == IT_KNOB && code >= 1 && code <= 8) {
        turn((int)code, (s8)it[8]);
        return 1;
    }
    return 0;
}

int ins_visible(void)
{
    return ins_up;
}

#include "../waverider/widgets.h"       /* stock 1.12's own widgets (docs/widgets.md) */
extern int smp_values_held(void);                         /* SYN held (csrc/sampler) */
extern int ovw_fx_held(void);                             /* FX held, as stock's page key held: the values (ovw.c) */
extern const char *mu_ins(int type, int knob, int k);     /* the value in its unit (csrc/waverider/md_page.c) */

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    extern void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on);
    cv_fill(c, x0, y0, x1, y1, on);             /* (2026-11-17) the same pixels a column word at a time: page.c */
}

/* after stock's screen (page.c wr_screen), while an INSERT page is up. Stock's track [FX] page is
 * under it: its title bar (pattern, name, tempo) and left panel (the track box, LEV) are kept as stock
 * drew them; the eight places are ours, drawn with stock's widgets: A M.SEL a choice, B..G the insert's
 * knobs, H MIX a knob, each with stock's label; an unused place is left empty. Under M.SEL: FULL when the
 * slot's FDN8 / XDLY found no instance free (it passes the sound through) */
typedef const char *(*wpop_name_fn)(int i, int arg);
typedef void (*wpop_move_fn)(int d, int arg);
extern void wpop_offer_mv(int slot, const char *label, int n, int cur, wpop_name_fn name, wpop_name_fn tag, int arg,
                          wpop_move_fn move);

/* the arrows (popup.c wpop_arrow): M.SEL D types on in the list's order, to the middle of that type's band, as
 * the knob turned there would */
static void ins_move(int d, int arg)
{
    (void)arg;
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1;
    int to = clamp(POS[ins_sel[t][j]] + d, 0, TYPES - 1);
    turn(1, (to * 128 + 64) / TYPES - ins_selv[t][j]);
}

static const char *ins_name(int i, int arg)
{
    (void)arg;
    return NAME[ORDER[i]];
}

/* M.SEL's box (2026-11-20, the User: the icon in it): stock's choice box (wg_choice), the type's icon (the one table,
 * dnfw.waverider.msel FX_ICONS, csrc/msel/msel.c msel_fx_icon) over its name. Box y .. y+16 (y up from the bottom):
 * the name's rows y+3 .. y+7, the icon's y+9 .. y+13, centred */
extern const u8 *msel_fx_icon(int type);
static void choice_icon(void *c, int y)
{
    int x = wg_x(0), b = wg_y(0) + 7;
    const u8 *ic = msel_fx_icon(y);
    WG_RECT(c, x, b, x + 18, b + 16, 1);
    WG_TEXT(c, (unsigned int)wg_font_choice, x + 9, b + 3, 2, "%.4s", NAME[y]);
    for (int r = 0; r < 5; r++)
        for (int i = 0; i < 7; i++)
            if (ic && (ic[r] >> (6 - i) & 1))
                SET_PIXEL(c, x + 6 + i, b + 13 - r, 1);
}

/* (2026-11-20) a place's marks: a held trig's lock drawn as stock draws a p-lock (the widget's area inverted, as
 * csrc/slides' SLD), and the moving line of knob I (csrc/modulation/moving.c mv_own_knob: heard against the page's
 * value, as our other pages) */
#define LOCK_FILL ((void (*)(void *, int, int, int, int, int))0x40114B22u)   /* (c, x0, y0, x1, y1, -1: inverted) */
static void place_marks(void *c, int s, int i, int locked)
{
    extern void mv_own_knob(void *canvas, int x, int y, int w, u32 key, u32 slot);
    if (i >= 0)
        mv_own_knob(c, wg_x(s) + 1, wg_y(s) + 5, 21, 0x8000u | (u32)i, INS_DEST + (u32)i);
    if (locked)
        LOCK_FILL(c, wg_x(s) - 3, wg_y(s) + 6, wg_x(s) + 21, wg_y(s) + 24, -1);
}

void ins_draw(void *c)
{
    init();
    static int last_up __attribute__((section(".data"))) = 0;
    if (ins_up != last_up) {                    /* another INSERT page: no knob touched yet, its page 1 (its page 2
                                                 * when UP / DOWN came from a page 2: fx_open) */
        last_up = ins_up;
        touched = -1;
        ins_pg = pg_open;
    }
    pg_open = 0;
    extern int isel_up(void);
    extern void isel_draw(void *c);
    if (isel_up()) {                            /* INSERT SEL over the page (csrc/msel/msel.c) */
        isel_draw(c);
        return;
    }
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j];
    fill(c, 22, 0, 127, 53, 0);                 /* the places; stock's title bar and left panel stay */
    choice_icon(c, y);
    wpop_offer_mv(0, "M.SEL", TYPES, POS[y], ins_name, 0, 0, ins_move);   /* the list popup (csrc/waverider/popup.c) */
    wg_label(c, 0, !BUILT[y] ? "SOON" : instances(y) && ins_inst[t][j] == NO_INST ? "FULL" : ins_pg ? "PG 2" : "M.SEL");
    if (!has_page2(y))
        ins_pg = 0;
    for (int k = 0; k < 6; k++) {
        int f = field_of(y, ins_pg, k);         /* the stored field of place k (or FUZZ's AUTO) */
        if (f < 0)
            continue;
        u8 v = *value_of(t, j, y, f);
        u32 lk = f < 6 ? sl_ins_held((u32)f, (u32)j) : 0x10000u;
        if (lk <= 127u)
            v = (u8)lk;                         /* (2026-11-20) a trig held: its lock */
        wg_knob(c, k + 1, v);
        const char *vt = (smp_values_held() || ovw_fx_held() || k == touched) ? mu_ins(y, f, v) : 0;   /* the knob turned last (or SYN held): its value in its unit */
        wg_label(c, k + 1, vt ? vt : ins_pg ? LABEL2[y][k] : LABEL[y][k]);
        place_marks(c, k + 1, f < 6 ? 7 * j + f : -1, lk <= 127u);
    }
    {
        u32 lk = sl_ins_held(I_MIX, (u32)j);
        u8 v = lk <= 127u ? (u8)lk : ins_mod[t][j];
        wg_knob(c, 7, v);
        const char *vt = (smp_values_held() || ovw_fx_held() || touched == 7) ? mu_ins(y, 7, v) : 0;
        wg_label(c, 7, vt ? vt : "MIX");
        place_marks(c, 7, y ? 7 * j + I_MIX : -1, lk <= 127u);
    }
    PAGE_DOTS(0, c, PAGES, ins_up, 7);          /* FX 2/3 or 3/3 */
}
