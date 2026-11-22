/* SAFE MODE's question (docs/safe-mode.md, C4), asked once the stock UI runs, on stock 1.12's own ConfirmWindow
 * (constructor 0x40112d0e, class 0x4020671c), built as stock builds "SAVE ALL ...?" (0x4005f75c..0x4005f852) and
 * "UPGRADE OS NOW?" (0x40109990..), and opened over MainScreenView as csrc/sampler/rec.c's sn_open opens the
 * NAME screen:
 *
 *   1. the shared block and the window in one allocation (0x8c B): {_Sp_counted_ptr_inplace<ConfirmWindow>
 *      0x401dd7e4, use 1, weak 1, the window at +16};
 *   2. ConfirmWindow(window, &title, &line, &answer, 0): two std::strings and a std::function<void(bool)> (8 bytes
 *      of functor, its manager, its invoker); the window keeps its own copy of the function (the manager's clone);
 *   3. View::open(MainScreenView, shared_ptr{window, block}, 0) (0x4011cb9e), then our shared count dropped.
 *
 * The window takes the YES and NO keys itself and calls the function with the answer (stock's invoker 0x401089fc
 * reads it as the low byte of a 32-bit argument):
 *   YES  -> nothing: the stock UI stays, in SAFE MODE.
 *   NO   -> the NORMAL-ONCE mark (through the uncached alias) and our soft reset: one normal boot whose earlier
 *           failures are not counted (normal.c's sm_late). Nothing is written to the +Drive here.
 * No answer: SAFE MODE goes on with the question up.
 *
 * Asked once per SAFE boot, at the first UI pass where MainScreenView exists and is this screen's (its +44); anything
 * else not as expected leaves it unasked (SAFE MODE still runs, as YES). */

#include "sm.h"

typedef uint32_t u32;

#define Q_NEW        ((u32 (*)(u32))0x40120544u)                                /* operator new (d0) */
#define Q_STR        ((void (*)(void *, const char *, void *))0x401CEAB8u)      /* std::string(const char *, alloc) */
#define Q_STR_FREE   ((void (*)(void *))0x401CD008u)                            /* ~std::string */
#define Q_FN_FREE    ((void (*)(void *))0x40188366u)                            /* ~std::function */
#define Q_WINDOW     ((void (*)(void *, void *, void *, void *, int))0x40112D0Eu)   /* ConfirmWindow::ConfirmWindow */
#define Q_OPEN       ((void (*)(void *, void *, int))0x4011CB9Eu)               /* View::open(child shared_ptr, 0) */
#define Q_COUNT_FREE ((void (*)(void *))0x401883ACu)                            /* ~__shared_count */
#define Q_MAIN_VIEW  0x44648980u                                                /* MainScreenView's shared_ptr */
#define Q_BLOCK_VT   0x401DD7E4u                                                /* _Sp_counted_ptr_inplace<ConfirmWindow> */
#define Q_BYTES      0x8Cu                                                      /* the block (16) and the window */

u32 sm_asked __attribute__((section(".data"))) = 0;    /* 0 not yet, 1 open, 2 YES, 3 NO; 4 not asked (no main view
                                                        * of this screen, or no memory) */

static int ram_ok(u32 a)
{
    return a >= 0x40000000u && a < 0x48000000u && !(a & 3u);
}

/* NO: the NORMAL-ONCE mark, then stock's soft reset (0x40005608's: interrupts masked, the bootstrap's reboot
 * marker word cleared, RCR SOFTRST), as normal.c's sm_reset_safe */
static void __attribute__((noreturn)) normal_once(void)
{
    struct sm_mark m;
    u32 *w = (u32 *)&m;
    for (u32 i = 0; i < sizeof m / 4u; i++)
        w[i] = 0;
    m.magic = SM_MAGIC_MARK;
    m.kind = SM_KIND_NORMAL;
    m.build = ((const volatile struct sm_head *)SM_LOAD)->build;
    m.why = 3u;
    m.crc = sm_crc32(&m, sizeof m - 4u);
    volatile u32 *dst = (volatile u32 *)SM_MARK_UC;
    __asm__ volatile("move.w #0x2700,%%sr" ::: "memory");
    for (u32 i = 0; i < sizeof m / 4u; i++)
        dst[i] = w[i];
    *(volatile u32 *)0x48000000u = 0;
    *(volatile uint8_t *)0xEC090000u = 0x80;
    for (;;)
        ;
}

static void answer(void *functor, u32 yes)              /* the std::function's invoker */
{
    (void)functor;
    if (yes & 0xFFu) {
        sm_asked = 2;
        return;
    }
    sm_asked = 3;
    normal_once();
}

static int manage(u32 *dest, const u32 *src, int op)    /* its manager: an empty functor kept in place */
{
    if (op == 0)                                         /* __get_type_info: none */
        dest[0] = 0;
    else if (op == 1)                                    /* __get_functor_ptr */
        dest[0] = (u32)src;
    else if (op == 2) {                                  /* __clone_functor */
        dest[0] = src[0];
        dest[1] = src[1];
    }
    return 0;                                            /* (3, __destroy_functor: nothing to free) */
}

static void ask(void *screen)
{
    u32 main_view = *(volatile u32 *)Q_MAIN_VIEW;
    if (!ram_ok(main_view) || *(volatile u32 *)(main_view + 44u) != (u32)screen)
        return;                                          /* not up yet: the next pass tries again */
    u32 *blk = (u32 *)Q_NEW(Q_BYTES);
    if (!ram_ok((u32)blk)) {
        sm_asked = 4;
        return;
    }
    blk[0] = Q_BLOCK_VT;
    blk[1] = 1;                                          /* use */
    blk[2] = 1;                                          /* weak */
    blk[3] = (u32)blk + 16u;                             /* the window, in place */
    char alloc = 0;
    u32 s_title = 0, s_line = 0;
    u32 fn[4];                                           /* std::function: 8 bytes of functor, manager, invoker */
    fn[0] = 0;
    fn[1] = 0;
    fn[2] = (u32)manage;
    fn[3] = (u32)answer;
    u32 why = sm_live.reason;
    Q_STR(&s_title, why == 2u ? "STOP HELD AT START" : "LAST START FAILED", &alloc);   /* (stock: 21 a line) */
    Q_STR(&s_line, "START SAFE MODE? Y/N", &alloc);
    Q_WINDOW(blk + 4, &s_title, &s_line, fn, 0);
    Q_STR_FREE(&s_line);
    Q_STR_FREE(&s_title);
    Q_FN_FREE(fn);
    u32 sp[2];                                           /* shared_ptr<View>: ConfirmWindow's View is at +0 */
    sp[0] = (u32)blk + 16u;
    sp[1] = (u32)blk;
    sm_asked = 1;
    Q_OPEN((void *)main_view, sp, 0);
    Q_COUNT_FREE(&sp[1]);
}

/* from sm_isdirty, every UI pass in SAFE MODE: 1 when the question was just opened (draw now) */
int sm_ask(void *screen)
{
    if (sm_asked || !sm_live.applied)
        return 0;
    ask(screen);
    return sm_asked == 1;
}
