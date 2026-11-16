/* page 2's places A..H, Delay and Reverb (included by fxp.c). A label of 4 characters at most; "" a place with no
 * parameter (yet). DEF is the knob 0..127 whose value is exactly what the DSP used before the page existed: the
 * DSP's mapping of every parameter (dnfw.xdly.design, dnfw.fdn8.design) returns that constant at DEF, bit for bit */
static const struct fxp_param fxp_delay[8] = {
    {"TIME", 0},                                /* stock's own, both pages (never drawn or turned by us) */
    {"SLEW", 58},                               /* the times' follow (23.2 ms) */
    {"KNEE", 61},                               /* the loops' soft knee (0.61) */
    {"WDTH", 127},                              /* the two lines' spread: hard left / right */
    {"INPT", 64},                               /* the input balance into the lines: both the mono sum */
    {"", 0},
    {"", 0},
    {"", 0},
};
static const struct fxp_param fxp_reverb[8] = {
    {"DIFF", 64},                               /* the diffusers' coefficients x k / 64 (held to 0.95) */
    {"WDTH", 127},                              /* the lines' spread into out L / R: as the tank has it */
    {"FREZ", 0},                                /* the lines' gains towards 1: a hold */
    {"", 0}, {"", 0}, {"", 0}, {"", 0}, {"", 0},
};
