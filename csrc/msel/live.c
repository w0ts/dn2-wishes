/* LIVE SELECT's setting (2026-11-12; msel.c does what it says): a row of stock's SETTINGS > PERSONALIZE,
 * the last, made as stock makes its own toggles there (PersonalizeMenuView, constructor 0x40097eac; LIVE REC
 * OVERDUB's row 0x40098446): an item (ctor 0x401173b8) of four std::functions, the label, YES (the value flipped),
 * the box (stock's own drawing, 0x400979be, with our value) and LEFT / RIGHT / the knob (+-1, clamped), added to the
 * view's menu (0x40116bee(view, item)); each change redraws the view (0x4011ca9a(view + 56)) as stock's do.
 *
 * The value lives in the mod's settings sector (csrc/jump/jump.c, 0x6FF000) as a flag that turns it OFF, so a unit
 * without the sector, or one whose sector predates the setting, has it on (the User: default ON).
 */
typedef unsigned int u32;

#define NEW       ((u32 (*)(u32))0x40120544u)
#define ITEM_CTOR ((void (*)(u32, void *, void *, void *, void *, int, int))0x401173B8u)
#define MENU_ADD  ((void (*)(u32, u32))0x40116BEEu)
#define FN_DTOR   ((void (*)(void *))0x40188366u)
#define REDRAW    ((void (*)(u32))0x4011CA9Au)
#define MGR4      0x400A983Cu               /* a manager that clones a 4-byte closure {view} (FILTER's, presets) */
#define SET_LIVE_OFF 4u                     /* the settings sector's flag bit 2 (jump.c; bit 1 is REMOTE CONTROL's) */

struct fn { u32 store, pad, mgr, inv; };    /* a std::function: its closure's storage, manager, invoker */

extern int set_flag(u32 bit);               /* jump.c */
extern void set_flag_put(u32 bit, int on);
extern char live_label[], live_box[];       /* live.S: the label (a std::string) and stock's box with our value */

u32 live_rows __attribute__((section(".data"))) = 0;      /* rows made (the checks read it) */

int live_on(void)
{
    return !set_flag(SET_LIVE_OFF);
}

static void live_put(int on)
{
    if (on != live_on())
        set_flag_put(SET_LIVE_OFF, !on);
}

const char *live_text(void)
{
    return "LIVE SELECT";
}

/* YES on the row: flipped */
void live_yes(u32 **fd)
{
    live_put(!live_on());
    REDRAW((*fd)[0] + 56);
}

/* LEFT / RIGHT / the knob: +-1, clamped to off..on (stock's, 0x40096956) */
void live_delta(u32 **fd, u32 unused, int delta)
{
    int v = live_on() + delta;
    (void)unused;
    live_put(v > 0);
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

/* live.S live_menu_hook: the row, at the end of PERSONALIZE's constructor */
void live_row(u32 view)
{
    struct fn f[4];
    u32 item = NEW(0x54);
    int i;
    fn_make(&f[0], (u32)live_label, view);
    fn_make(&f[1], (u32)live_yes, view);
    fn_make(&f[2], (u32)live_box, view);
    fn_make(&f[3], (u32)live_delta, view);
    ITEM_CTOR(item, &f[0], &f[1], &f[2], &f[3], -1, 8);
    MENU_ADD(view, item);
    for (i = 3; i >= 0; i--)
        FN_DTOR(&f[i]);
    live_rows++;
    { extern void load_row(u32); load_row(view); }   /* 2026-11-12: VOICE BUDGET's row after it (csrc/load) */
}
