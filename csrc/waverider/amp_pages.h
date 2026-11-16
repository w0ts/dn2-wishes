/* The AMP key's pages (2026-11-12, the User: ENV2 "right after the stock envelope page", the scope "one page later";
 * "osc is page 3, and we might move it elsewhere"): stock's AMP page, then ours. A page's place is one constant here;
 * csrc/scope/scope.c steps amp_sub on [AMP] and closes it as the INSERT pages close. */
#ifndef AMP_PAGES_H
#define AMP_PAGES_H

#define AMP_STOCK 0                     /* stock's AMP page (ENV1: its envelope, now also a modulation source) */
#define AMP_ENV2  1                     /* ENV2, csrc/matrix/env2_page.c */
#define AMP_SCOPE 2                     /* the oscilloscope, csrc/scope/scope.c */
#define AMP_PAGES 3

extern int amp_sub;                     /* the AMP page up: AMP_STOCK when none of ours is (scope.c) */

#endif
