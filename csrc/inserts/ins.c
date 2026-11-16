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
 * (link.c smp_tdm) whenever ins_gen moves. They are saved with the project (csrc/inserts/store.c) and are
 * not lockable.
 */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed char s8;

#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)
#define TEXT      ((void (*)(void *, u32, int, int, int, const char *, ...))0x4011573Cu)
#define FONT      0x44508ED8u
#define CENTRED   2
#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)
#define IT_KEY    0
#define IT_KNOB   1
#define IT_DROP   0xFF
#define K_FX      5
#define K_NO      12
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

u8 ins_sel[16][SLOTS] __attribute__((section(".data")));    /* the type (from ins_selv's band) */
u8 ins_selv[16][SLOTS] __attribute__((section(".data")));   /* M.SEL as turned, 0..127: each type a band of it */
u8 ins_mod[16][SLOTS] __attribute__((section(".data")));
u8 ins_fza[16][SLOTS] __attribute__((section(".data")));   /* FUZZ's or TAPE's AUTO (0 / 127; X_AUTO) */
u8 ins_tpg[16][SLOTS] __attribute__((section(".data")));   /* TAPE's PGAIN (X_TPG): 64 + dB, 32 .. 95 */
static int ins_pg __attribute__((section(".data"))) = 0;      /* the INSERT page's page: 0, 1 (page 2) */
static int ins_armed __attribute__((section(".data"))) = 0;   /* FUNC went down on an insert with a page 2 */
u8 ins_inst[16][SLOTS] __attribute__((section(".data")));   /* FDN8 / XDLY: the DSP's instance, NO_INST: FULL */
u8 ins_kv[16][SLOTS][TYPES][6] __attribute__((section(".data")));
u32 ins_gen __attribute__((section(".data"))) = 0;      /* moves on every change: the link sends */
u32 ins_edits __attribute__((section(".data"))) = 0;    /* moves on every edit by the knobs (store.c saves) */
int ins_up __attribute__((section(".data"))) = 0;       /* the INSERT page up: 0 none, 1 or 2 its slot */
static int ins_inited __attribute__((section(".data"))) = 0;
static int title_due __attribute__((section(".data"))) = 0;  /* draws left to rename stock's "FX" */
static int touched __attribute__((section(".data"))) = -1;   /* the knob last turned on this INSERT page (0..5, 7 MIX): its value in its unit */

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
    ins_inited = 1;
    ins_gen++;
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

/* a record's eight fields (dnfw.inserts.design: type | instance << 4, MIX, K1..K6); a FULL slot is OFF */
static void fields(int t, int j, u8 *f)
{
    int y = ins_sel[t][j];
    int full = instances(y) && ins_inst[t][j] == NO_INST;
    f[0] = full || !BUILT[y] ? 0 : (u8)(y | (instances(y) ? ins_inst[t][j] << 4 : 0));
    if ((y == T_FUZZ || y == T_TAPE) && ins_fza[t][j] >= 64)
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
        if (ins_sel[t][j] == T_TAPE)
            w[i >> 2] |= (u32)((ins_tpg[t][j] - 64) & 0x7F) << (8 * (i & 3));
    }
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
    ins_gen++;
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

static void turn(int knob, int delta)
{
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1;
    if (knob == 1) {
        /* as a stock multi-choice: turned as a 0..127 knob, each type a band of it (about 9 of it
         * for fourteen types, in ORDER: OFF 0..9, CHOR 10..18 .. XDLY 119..127), so a type takes a band
         * of a turn of the range, not one step */
        int was = ins_sel[t][j];
        ins_selv[t][j] = (u8)clamp(ins_selv[t][j] + delta, 0, 127);
        ins_sel[t][j] = ORDER[ins_selv[t][j] * TYPES / 128];
        if (ins_sel[t][j] != was) {
            if (instances(was) && ins_inst[t][j] != NO_INST)
                ins_inst[t][j] = NO_INST;       /* given back */
            assign(t, j);
            reassign();
        }
    } else if (knob == 8) {
        ins_mod[t][j] = (u8)clamp(ins_mod[t][j] + delta, 0, 127);
        touched = 7;
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
        }
    }
    ins_gen++;
    ins_edits++;
    extern int smp_overlay_dirty;
    smp_overlay_dirty = 1;
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
 * 2026-11-13 (the User): the AMP mode's bare "AMP" becomes "ENV1/AMP", page 1 of AMP's three (csrc/scope/scope.c
 * names the other two). No other mode is named "AMP". */
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
    else if (t[0] == 'A' && t[1] == 'M' && t[2] == 'P' && t[3] == 0)
        name = amp_title1;
    else
        return;
    str[0] = str[1] = str[2] = str[3] = 0;
    STR_NEW(str, name, &alloc);
    STR_SET(s, str);
    STR_FREE(str);
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
    if (fx)                                     /* stock's "FX": renamed (its slide, if any, kept) */
        say(PAGE_NAME[0], 0);
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
    ins_armed = 0;                              /* any other key, push or turn: FUNC is a modifier now */
    if (it[0] == IT_KEY && press && !(flags & 8u)) {
        if (code == K_FX) {
            if (KEY_HELD(K_FUNC)) {             /* FUNC + FX: stock's SEND pages, as stock */
                if (ins_up) {
                    ins_up = 0;
                    smp_overlay_dirty = 1;
                }
                title_due = 0;
                return 0;
            }
            if (ins_up || ins_fx_page()) {      /* FX 1/3 -> 2/3 -> 3/3 -> 1/3 (stock's page, under ours) */
                ins_pg = 0;
                ins_up = (ins_up + 1) % PAGES;
                smp_overlay_dirty = 1;
                say(PAGE_NAME[ins_up], 1);
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
extern const char *mu_ins(int type, int knob, int k);     /* the value in its unit (csrc/waverider/md_page.c) */

static void fill(void *c, int x0, int y0, int x1, int y1, int on)
{
    for (int x = x0; x <= x1; x++)
        for (int y = y0; y <= y1; y++)
            SET_PIXEL(c, x, y, on);
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

void ins_draw(void *c)
{
    init();
    static int last_up __attribute__((section(".data"))) = 0;
    if (ins_up != last_up) {                    /* another INSERT page: no knob touched yet, its page 1 */
        last_up = ins_up;
        touched = -1;
        ins_pg = 0;
    }
    int t = UI_TRACK & 15, j = (ins_up - 1) & 1, y = ins_sel[t][j];
    fill(c, 22, 0, 127, 53, 0);                 /* the places; stock's title bar and left panel stay */
    wg_choice(c, 0, NAME[y]);
    wpop_offer_mv(0, "M.SEL", TYPES, POS[y], ins_name, 0, 0, ins_move);   /* the list popup (csrc/waverider/popup.c) */
    wg_label(c, 0, !BUILT[y] ? "SOON" : instances(y) && ins_inst[t][j] == NO_INST ? "FULL" : ins_pg ? "PG 2" : "M.SEL");
    if (!has_page2(y))
        ins_pg = 0;
    for (int k = 0; k < 6; k++) {
        int f = field_of(y, ins_pg, k);         /* the stored field of place k (or FUZZ's AUTO) */
        if (f < 0)
            continue;
        u8 v = *value_of(t, j, y, f);
        wg_knob(c, k + 1, v);
        const char *vt = (smp_values_held() || k == touched) ? mu_ins(y, f, v) : 0;   /* the knob turned last (or SYN held): its value in its unit */
        wg_label(c, k + 1, vt ? vt : ins_pg ? LABEL2[y][k] : LABEL[y][k]);
    }
    wg_knob(c, 7, ins_mod[t][j]);
    {
        const char *vt = (smp_values_held() || touched == 7) ? mu_ins(y, 7, ins_mod[t][j]) : 0;
        wg_label(c, 7, vt ? vt : "MIX");
    }
    PAGE_DOTS(0, c, PAGES, ins_up, 7);          /* FX 2/3 or 3/3 */
}
