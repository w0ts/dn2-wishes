/* PARA on the VOICE key's LED (2026-11-19, the User: "if the current track is paraphonic ... we should colour the
 * button pink"; magenta 91, as bright as stock's UNISON teal; stock's white while the VOICE menu is open).
 * docs/leds.md has the study (the VOICE key) and the LED path.
 *
 * Stock 1.12 (read from the disassembly, measured in the emulator):
 *   - the VOICE key is LED id 8 (phys 7; the firmware's LED name table 0x401f393c);
 *   - MainScreenView's LED routine (0x40060842) lights it teal (mode 2, palette 131) when the active track's UNISON
 *     is on: `if (!(claimed & bit 8) && 0x40029126(x, t)) LED_SET(lm, 8, 2, 131)` (0x40060d54..0x40060dbe);
 *     otherwise nobody claims it and the compose gives it the backlight (1, 1);
 *   - VoiceMenuView (0x40028990) lights it white (2, 113) while its menu is up, and claims it first.
 *
 * pu_voice_led replaces that one UNISON test (coldfire.py VOICE_LED_SITE, `jsr 0x40029126`, same arguments). On a
 * PARA ON track (para.h: ANALOG 2 or JUNO, MOD not 0) it lights VOICE magenta (2, 91) itself and answers "unison
 * off", so stock lights nothing more; on any other track it answers what stock's test answers. So it decides only
 * where stock decides: the VOICE menu's white and any view above that claimed VOICE stay stock's, and teal stays on
 * every track that is not PARA (UNISON is ignored on a PARA track).
 *
 * pu_led_poll (rt_poll, every UI pass, beside bn_led_poll): the LEDs are composed only when the screen asks
 * (its +33). When the active track's PARA state changes (PARA turned, a sound or kit loaded, undo, a machine
 * change, another track), it asks (stock's LED_DIRTY), once a change. Nothing runs per audio frame. */
typedef unsigned int u32;
typedef unsigned char u8;

#include "para.h"

#define LED_MGR    ((u32 (*)(void))0x4018AD9Cu)
#define LED_SET    ((void (*)(u32, u32, u32, u32))0x4002C318u)
#define LED_DIRTY  ((void (*)(void *))0x4011D5F4u)
#define UNISON_GET ((u32 (*)(u32, u32))0x40029126u)    /* stock: track t's UNISON on (x = the kit's voice setup) */
#define UI_TRACK   (*(volatile u8 *)0x42432A6Cu)         /* the active track (vmenu.c) */
#define LED_VOICE  8u
#define LED_STEADY 2u
#define PARA_MAGENTA 91u                                /* palette: magenta 82..97; 91 = 32/0/32 at LED INTENSITY's middle */

u32 pu_led_sets __attribute__((section(".data"))) = 0;   /* VOICE lit magenta (the emulator reads it) */
u32 pu_led_marks __attribute__((section(".data"))) = 0;  /* refreshes asked */
u32 pu_led_state __attribute__((section(".data"))) = 0xFFu;   /* the active track's PARA state last seen (0xFF: none) */

static int para_on(u32 t)
{
    return t < 16 && para_track((int)t) && para_value((int)t) != 0;
}

/* in place of MainScreenView's jsr 0x40029126(x, t): its answer, tested as a byte */
u32 pu_voice_led(u32 x, u32 t)
{
    if (para_on(t)) {
        u32 lm = LED_MGR();
        if (lm) {
            LED_SET(lm, LED_VOICE, LED_STEADY, PARA_MAGENTA);
            pu_led_sets++;
        }
        return 0;
    }
    return UNISON_GET(x, t);
}

void pu_led_poll(void)
{
    extern void *wr_screen_obj;
    u32 s = (u32)para_on(UI_TRACK);
    if (s != pu_led_state && wr_screen_obj) {
        pu_led_state = s;
        LED_DIRTY(wr_screen_obj);
        pu_led_marks++;
    }
}
