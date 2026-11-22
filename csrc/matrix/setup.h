/* MOD SETUP's entries as the routes popup edits them (csrc/matrix/setup.c, docs/matrix.md "MOD SETUP's rows"). */
#ifndef MX_SETUP_H
#define MX_SETUP_H

#define MXS_SOURCES 6u                  /* VEL MW PB AT BC KEY: the popup's rows 5..10 */
#define MXS_PLACES 4u                   /* stock's four entries a source */
#define MXS_TOP 32512                   /* stock's depth word: -32768 .. 32512 (setDepth's clamp) */
#define MXS_BOTTOM (-32768)

/* the popup's row J (0 VEL .. 5 KEY) -> the sound's list (VEL PB MW BC AT KEY from byte 230) */
extern const u8 mxs_list[MXS_SOURCES];
/* -> results of an edit */
#define MXS_OK 0
#define MXS_FULL 1                      /* four entries already: no room for a new one */
#define MXS_NOT_IN 2                    /* stock's MOD SETUP list does not offer this parameter */
#define MXS_NO_OBJ 3                    /* stock's MOD SETUP object not found (never met) */
#define MXS_NO_ROOM 4                   /* the record had no room for a mark */

int mxs_entry(u32 t, u32 j, u32 p, s32 *depth);        /* -> the slot of place P (0: free), its depth word */
int mxs_find(u32 t, u32 j, u32 slot);                   /* -> the first place into SLOT, -1 none */
s32 mxs_sum(u32 t, u32 j, u32 slot, int *n);            /* the depths into SLOT summed, N entries */
u32 mxs_used(u32 t, u32 j);                             /* places in use (of 4) */
int mxs_offers(u32 t, u32 slot);                        /* stock's MOD SETUP list offers SLOT */
int mxs_merge(u32 t, u32 j, u32 slot);                  /* two or more entries into SLOT made one -> its place */
int mxs_set(u32 t, u32 j, u32 slot, s32 w);             /* SLOT's depth W (0: deleted; from none: added) -> MXS_ */
int mxs_delete(u32 t, u32 j, u32 slot);                 /* every entry of J into SLOT deleted -> how many */
int mxs_muted(u32 t, u32 j, u32 slot);                  /* the entry into SLOT is muted (its mark matches it) */
int mxs_mute(u32 t, u32 j, u32 slot, int on);           /* -> 1 changed, 0 nothing, -MXS_ refused */
void mxs_lay(u32 t, u32 sound);                         /* the marks of track T laid out (matrix.c mx_poll) */
#endif
