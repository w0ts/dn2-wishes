# The send pages' second page (Delay with XDLY, Reverb with FDN8 / LONG), 2026-11-11

The User: "fct pressed and release switch sub page". On the send DELAY page while its TYPE is XDLY, and on the
send REVERB page while its TYPE is FDN8 or LONG, a **FUNC tap** switches between **page 1** (stock's eight places,
as they are) and **page 2** (eight more, ours). Page 1 carries a small tag at the title bar's right end, **1/2**; page 2 none (2026-11-12, the User: the 2/2 was stuck in the corner).
With TYPE on STOCK there is no page 2, no tag, and stock's page is untouched.

## Gestures

- **The tap**: FUNC pressed and released with no other key, encoder push or turn between. Any other item cancels it:
  FUNC + FX (how the send pages are entered: FUNC is still down when the page appears; the press of FX cancels the
  tap), FUNC + a push (stock's modulation popup, and the long push's reset), FUNC + a turn, FUNC + any key.
- **FUNC + turn** keeps stock's coarse jump on page 1 (we take no item there). On page 2 it jumps the value to the
  next of 0, its default, 127, in the direction of the turn.
- The Delay's **TIME** is on both pages: on page 2 its place (A) is stock's own cell, left as stock drew it, its
  knob passed on to stock.
- Leaving the page (another page, another overlay) closes page 2; the next visit starts on page 1.

## What is on page 2

| page | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| Delay (XDLY) | TIME (stock's) | SLEW | KNEE | WDTH | INPT | | | |
| Reverb (FDN8, LONG) | DIFF | WDTH | FREZ | | | | | |

Each parameter's **default** is the knob whose value makes the engine do exactly what it did before the page
existed (a project that never touched the page plays bit for bit as before; the SHARC runner's xdly and fdn8 steps
at the defaults are the old reference). The inserts' FDN8 / XDLY instances never see the page: they always use the
old constants.

| parameter | knob 0..127 -> value | default |
|---|---|---|
| XDLY SLEW | the times' follow: 1 / (48 x 1000^(k / 127)) a sample, 1 ms .. 1 s (tape bend, or a jump) | 58 = 23.2 ms (optimist's >> 10) |
| XDLY KNEE | the loops' soft knee: 0.3 + k x 0.65 / 127 | 61 = 20000 / 32768 |
| XDLY WDTH | out L = line 1 wl + line 2 wr, out R = line 2 wl + line 1 wr; w = k / 127, wl = (1 + w) / 2, wr = (1 - w) / 2: 0 mono, 127 hard (today's) | 127 |
| XDLY INPT | the lines' inputs: (L + R) / 2 plus / minus s (L - R) / 2 to line 1 / 2, s = (k - 64) / 64: 64 the mono sum (today's), 127 line 1 = L and line 2 = R, 0 swapped | 64 |
| FDN8 DIFF | the diffusers' coefficients (0.75 .. 0.8, 0.625 .. 0.7) x k / 64, held to 0.95 | 64 = x 1.0 |
| FDN8 WDTH | as XDLY's, on the tank's out L / R | 127 |
| FDN8 FREZ | the lines' gains towards 1, g (1 - f) + f, f = k / 127: a hold (the damping filters still act) | 0 |

Not here (a later commit, if it fits): XDLY XFBK, LOCT, MOD2, SYNC; FDN8 MRAT, BASS, ERLY, TILT; LEN needs a table
per line length and stays out.

## The values on screen (2026-11-13, the User: no bare 0..127)

A place's value (SYN held, or the place just turned) reads in its unit, from the same derivation the engine uses
(`dnfw.engines.units` `_fxp_units`, `md_page.c` `mu_fxp`): **SLEW** 1 ms .. 1 s (`1ms`, `32ms`, `1.0s`), **KNEE**
the soft knee's level in dB (0.3 .. 0.95: `-10` .. `0dB`; -10 and under without "dB", four characters), **WDTH**
and **FREZ** %, **INPT** signed % (`+0%` the mono sum), **DIFF** 0..198 % (`100%` = today's diffusers). The Delay's
TIME is stock's cell and record, read by XDLY's page-1 formatter. Display only: the knobs, the saved bytes and the
words sent are unchanged.

## How it works

- **ColdFire** (`csrc/fxpage/fxp.c`, `fxp_params.h`, generated `fxp_derive.h`): the page hooks are the INSERT pages'
  (csrc/inserts): `fxp_pop` is called from rec.c `smp_ui_pop` after `ins_pop` (the item stream: FUNC's press and
  release, every other key, every knob), `fxp_begin` / `fxp_draw` from page.c `wr_screen` (the page overlay and
  the tag are drawn over stock's screen with stock's own widgets), `fxp_seen` from the TYPE cells' draws
  (`rvt_cell`, `dlt_cell`: which page stock drew, and whether its type is ours).
- **Values**: `fxp_v[page][place]` knobs 0..127, **per project** (not per kit): saved in the inserts' record
  sector (`csrc/inserts/store.c`: after the inserts' check the words 'FXP2', the sixteen bytes and their check; a
  record without them, a project saved before, is the defaults; an older build ignores them), the defaults on a NEW.
- **To the DSP**: `fxp_words` turns the knobs into the engines' float32 values (`dnfw.xdly.design.derive`,
  `dnfw.fdn8.design.derive`; the C does the same operations, held to them for every knob by `test/test_fxpage.py`)
  and link.c sends twelve words after each change, three times, to the directory page at 0xED0..0xEFF (the tail of
  what was BOUNCE's buffer directory; BOUNCE is gone from the ColdFire). They are in the mirror's page too, so a load's
  page carries them. XDLY: change word, kf kn wl wr sn; FDN8: change word, sd f wl wr. The change word 0 (nothing
  received yet) is the constants.
- **DSP**: `dnfw.xdly.program.extras` and `dnfw.fdn8.program.extras` copy the words into state words (a send
  only: the instances use the constants) once a block. XDLY: kf and kn replace two constants, the input and the output
  gain a branch each that is not taken at the defaults. FDN8: once a block the diffusers' and the lines' gains are
  rebuilt (x 1.0, + 0.0 at the defaults: the same bits), the output a branch. Models: `ref.py` of each, held bit for
  bit to the DSL programs (test_xdly, test_fdn8) and to the assembled code (SHARC runner steps xdly, fdn8, `second
  page` checks).
- **L2**: XDLY's code span grew from 4.5 to 5.5 KB at FDN8's expense (10 -> 9 KB; fdn8.asm 7,018 B): `dnfw.waverider.dsp`
  FDN8_L2_SPAN 0x2400, XDLY_SW 0xbd6200 (was 0xbd6400).

## Measured / not

See the commit messages and the session notes (`fx-order.md`).
