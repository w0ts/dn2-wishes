/* An LFO's routes as the popups read and write them (routes.c): the first route in stock's DEST and DEP, the others in
 * the record (WT_MX_ROUTES), a muted first route marked in the record. */
#ifndef MX_ROUTES_H
#define MX_ROUTES_H

#define MXR_MUTED 0x80u                 /* matrix.c MX_MUTED */
#define MXR_FIRST 0x40u                 /* matrix.c MX_FIRST: with MXR_MUTED, LFO (byte & 3)'s first route muted */
#define MXR_ROUTES 23                   /* matrix.c MX_SLOTS: the routes laid out */
#define MXR_LFO 15                      /* matrix.c MX_LFO */
#define MXR_POOL 16                     /* the LFOs' shared pool: their DESTs and the record's LFO routes */
#define MXR_BUF (4u * (MXR_ROUTES + 3u))   /* the routes and three marks */
#define MXR_NONE 0x4000u                /* a depth that adds nothing */

extern const u8 mxr_dest_rec[3], mxr_dep_rec[3];
u32 mxr_sound(u32 t);
u32 mxr_stock(u32 t, u32 rid);
void mxr_stock_set(u32 t, u32 rid, u32 value);
int mxr_get(u32 t, u8 *v);
void mxr_put(u32 t, const u8 *v, int n);
u32 mxr_dest(u32 t, u32 l);
u32 mxr_first_dep(u32 t, u32 l);
void mxr_first_set(u32 t, u32 l, u32 dep);
int mxr_is_mark(const u8 *e);
int mxr_mark_at(const u8 *v, int n, u32 l);
int mxr_first_muted(u32 t, u32 l);
int mxr_ctrl_slot(u32 s);
int mxr_drop(u8 *v, int n, int at);
int mxr_mute_first(u32 t, u32 l, int on);
void mxr_drop_first(u32 t, u32 l);
int mxr_settle(u32 t, u32 l);
u32 mxr_pool(u32 t);
u32 mxr_count(const u8 *v, int n, int lfo_only);

#endif
