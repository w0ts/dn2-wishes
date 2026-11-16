/* The CPU label's quiet (csrc/meter/quiet.c): why stock is busy on purpose now, read from its own state. */
#ifndef MTR_QUIET_H
#define MTR_QUIET_H

#define QUIET_LOADING 1u                /* the boot (stock's UI not built yet), or stock's "Loading..." up */
#define QUIET_UPGRADE 2u                /* an OS upgrade arriving or being written (Transfer's OsUpgrade RPC) */

unsigned int mtr_quiet_why(void);

#endif
