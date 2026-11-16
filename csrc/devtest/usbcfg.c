/* REMOTE CONTROL in SETTINGS > SYSTEM > USB CONFIG (2026-11-12, the User's ruling in docs/remote-ui.md): the
 * test channel's screen, keys, switches and memory reads answer only while this entry is ON. Default ON (for
 * now); remembered in the mod's settings sector (jump.c, DN2S flags bit 1 set = OFF); a FACTORY RESET from the
 * startup menu turns it OFF (jump.c jmp_poll).
 *
 * Stock's view (measured in the OS 1.12 image): UsbConfigMenuView::rebuild (0x40104f42) adds its three choices
 * (OVERBRIDGE, USB MIDI, USB AUDIO/MIDI), each a MenuItem (0x54 bytes, constructed by 0x401173b8 from four
 * std::function and -1, 8) handed to the view's vtable slot 8, then puts the cursor back (vtable slot 0x1c,
 * at 0x40105220). Our jmp there (usbcfg.S dt_usb_rebuild) adds a fourth item first, so the cursor may come
 * back to it. The four functions, in the constructor's order:
 *   label  std::string(MenuItem&)                 usbcfg.S dt_usb_label: "REMOTE CONTROL"
 *   yes    void(MenuItem&)                         dt_usb_yes: toggles
 *   draw   void(MenuItem&, Bitmap&, int x, int y)  dt_usb_draw: stock's box, filled while ON (0x40104c88's draw)
 *   turn   void(MenuItem&, int)                    dt_usb_turn: > 0 ON, < 0 OFF
 * Each std::function is {functor storage (8), manager, invoker}; a functor kept as a heap pointer to the view,
 * managed by stock's own manager for the choices' 4-byte functors (0x401048a8: clone and free; the label's,
 * empty, by 0x40104856), so the item copies and frees them exactly as it does the stock ones.
 *
 * While Outbox 8 handles USB, stock draws "THE USB CONFIG IS CURRENTLY BEING HANDLED BY OUTBOX 8" and rebuild
 * adds nothing: neither does ours (the setting stays as it was). */
#include "devtest.h"

#define D __attribute__((section(".data")))

/* operator new: stock returns its pointer in d0, our compiler reads a returned pointer from a0: declared u32, cast
 * (widgets.h, lzma7.c). Declared as a pointer, every functor got a0's leftover and its destruction freed it */
#define OP_NEW ((u32 (*)(u32))0x40120544u)
#define FN_FREE ((void (*)(void *))0x40188366u)                 /* std::function's destructor */
#define MENU_ITEM ((void (*)(void *, void *, void *, void *, void *, int, int))0x401173B8u)
#define MGR_EMPTY ((void *)0x40104856u)                         /* the label lambda's manager (1-byte functor) */
#define MGR_VIEW ((void *)0x401048A8u)                          /* a choice's yes lambda's manager (the view) */
#define BLIT ((void (*)(void *, const void *, int, int, int))0x40115ADCu)
#define BOX_ICONS (*(u8 *volatile *)0x44645D84u)                /* the box: +0 empty, +28 filled */
#define BOX_STRIDE 28
#define REBUILD ((void (*)(void *))0x40104F42u)                 /* UsbConfigMenuView::rebuild: the items again */
#define ITEM_BYTES 0x54u

extern u8 set_remote;                                           /* jump.c: 1 ON, 0 OFF */
extern u8 jmp_dirty;                                            /* jump.c: the settings sector to be written */
extern void dt_usb_label(void);                                 /* usbcfg.S: the label (a std::string by %a0) */

u32 dt_usb_items D = 0;                                         /* items added, for the checks */
u32 dt_usb_changes D = 0;                                       /* the setting changed from the menu */

struct fn { void *store, *pad, *manager, *invoker; };           /* std::function, 16 bytes */

static void *view_of(void **store)                              /* the functor: a heap pointer to the view */
{
    return **(void ***)store;
}

/* a change: written by jmp_poll from the UI loop, and the view rebuilt as stock's choices do after theirs
 * (0x40105256: their YES tail-calls rebuild), which draws it again with the cursor where it was. Rebuild frees
 * the items, this one too: nothing of the item or its functor is touched after it */
static void set(void *view, int on)
{
    if (on == set_remote)
        return;
    set_remote = (u8)on;
    jmp_dirty = 1;
    dt_usb_changes++;
    REBUILD(view);
}

void dt_usb_yes(void **store, void *item)
{
    (void)item;
    void *view = view_of(store);
    set(view, !set_remote);
}

void dt_usb_turn(void **store, void *item, int delta)
{
    (void)item;
    if (delta)
        set(view_of(store), delta > 0);
}

void dt_usb_draw(void **store, void *item, void *bitmap, int x, int y)
{
    (void)store; (void)item;
    BLIT(bitmap, BOX_ICONS + (set_remote ? BOX_STRIDE : 0), x + 11, y, 0);
}

static void make(struct fn *f, void *view, void *manager, void *invoker)
{
    f->pad = 0;
    f->manager = manager;
    f->invoker = invoker;
    if (view) {
        void **p = (void **)OP_NEW(4);
        *p = view;
        f->store = p;
    } else {
        f->store = (void *)OP_NEW(1);
    }
}

/* usbcfg.S dt_usb_rebuild, from UsbConfigMenuView::rebuild after its three choices: the fourth item */
void dt_usb_item(void *view)
{
    struct fn f[4];
    make(&f[0], 0, MGR_EMPTY, (void *)dt_usb_label);
    make(&f[1], view, MGR_VIEW, (void *)dt_usb_yes);
    make(&f[2], view, MGR_VIEW, (void *)dt_usb_draw);
    make(&f[3], view, MGR_VIEW, (void *)dt_usb_turn);
    void *item = (void *)OP_NEW(ITEM_BYTES);
    MENU_ITEM(item, &f[0], &f[1], &f[2], &f[3], -1, 8);
    void (*add)(void *, void *) = (*(void (***)(void *, void *))view)[2];   /* vtable slot 8 */
    add(view, item);
    for (int k = 3; k >= 0; k--)
        FN_FREE(&f[k]);
    dt_usb_items++;
}
