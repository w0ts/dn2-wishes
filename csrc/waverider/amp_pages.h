/* The AMP key's pages (2026-11-12, the User: ENV2 "right after the stock envelope page"): stock's AMP page, then ENV2.
 * A page's place is one constant here; csrc/scope/scope.c steps amp_sub on [AMP] and closes ENV2's page as the INSERT
 * pages close. 2026-11-19 (the User): the oscilloscope is no longer AMP's third page; it opens on a long press of
 * [TRIG] (csrc/scope/scope.c), and amp_sub says AMP_SCOPE while it is up, so what refuses "a page of ours" (the routes
 * and DEST popups, csrc/matrix) refuses it too. 2026-11-20 (the User): DOWN / UP step the pages too, as on stock's own
 * pages, stopping at the ends (scope.c amp_arrow). */
#ifndef AMP_PAGES_H
#define AMP_PAGES_H

#define AMP_STOCK 0                     /* stock's AMP page (ENV1: its envelope, now also a modulation source) */
#define AMP_ENV2  1                     /* ENV2, csrc/matrix/env2_page.c */
#define AMP_PAGES 2
#define AMP_SCOPE AMP_PAGES             /* not an AMP page: the oscilloscope up, over stock's TRIG page (scope.c) */

extern int amp_sub;                     /* the page of ours up: AMP_STOCK when none is (scope.c) */

#endif
