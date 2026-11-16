# Stock widgets on our pages (2026-11-09)

Our ColdFire pages (PERC's, the Monomachine-style SOPHIE / PLAITS / TB303) draw their controls
with **the DN2's own widget routines** from stock OS 1.12, called with our values, so they look
exactly like the stock TRIG and SYN pages. `csrc/waverider/widgets.h` is the API; any page code
(the FX session's INSERT page, the meter) can include it.

## How stock draws a cell (measured in the 1.12 emulator)

Every stock widget is a per-record draw function taking its value as an argument:
`(functor, value, canvas, x, y, flag)`; it draws into the canvas only. A page's grid calls, for
each of its eight places, the cell routine `0x4006448a`, which looks up the record's widget
descriptor (`0x4243425c + 68 x id`, RAM, built at boot) and calls its draw function at
`(x, y + 7)`, then draws the label. We call the draw functions directly, with functor 0 and
flag 0 (what every stock cell passes); measured to draw correctly with our own values.

## The API (`widgets.h`)

Geometry is stock's: canvas 128 x 64, y counting up from the bottom; place `s` 0..7 at
`x = 24 + 26 (s & 3)`, `y = 27` (top row) or `0`.

| call | what | stock routine |
|---|---|---|
| `wg_knob(c, s, k)` | the dial, k 0..127 | `0x400c0986` (LEN, FREQ, RESO..) |
| `wg_fader(c, s, k)` | the fader | `0x400c0a60` (VEL, LEV1) |
| `wg_toggle(c, s, on)` | the on/off switch | `0x400bc578` (AMP.T, LFO.T) |
| `wg_note(c, s, note)` | the note picker, "C 5" over "(60)" in its box | `0x400c0868` (TRIG's NOTE) |
| `wg_choice(c, s, text)` | a named choice: up to 4 characters in stock's choice box | box `0x40114906`, text `0x4011573c` in retrig LEN's font (stock has no generic choice routine: each choice record draws its own, as retrig LEN `0x400cc418`) |
| `wg_label(c, s, name)` | the cell's label | `0x40115948`, font `0x40291ca0` |
| `wg_left_panel(c, track, name3, lev, label)` | the track box (stock's frame for the track, a 3-letter name where stock writes SYN) and LEV's fader with its label | blit `0x40115adc` of frame `0x40115f88(0x44647db4, track)`, text font `0x44508eb8`; LEV `0x400c0a14` at (-2, 7) |

Rules:
- Call them only inside a page draw, on the canvas that draw was given (stock's canvas is a
  stack object; its address is garbage afterwards).
- Values in the knob's 0..127 (the wrappers shift them to stock's record units, `<< 8`); LEV in
  the record's own units (`GET_VALUE(view, TRACK_LEVEL_ID)`).
- Stock returns pointers in **d0**; our compiler reads pointer results from **a0**. Declare any
  stock routine that returns a pointer as returning `int` and cast (`WG_FRAME`, md_page.c's
  `NOTE_NAME`); calling it as a pointer function reads garbage (the emulator faulted in the blit).

## Our pages on them

- PERC: the eight controls as stock knobs, TYPE (the machine) in a choice box; the track box
  shows the machine's family (its three letters) where stock writes SYN.
- SOPHIE / PLAITS / TB303: knobs; MODL as a choice box (SWRM, KICK); PLAITS' TUNE as a choice box
  in signed semitones (+7, -12, 0: the User, build #3), FINE as a choice box (+28c); the
  track box shows MACHINE SEL's short name (SOP, PLT, 303).
- A p-locked control is inverted (as before). SYN held still puts each value in its label.

Screens: `dn2mk2-scratch/screens-os112/widgets_vs_stock.png` (ours next to stock's TRIG and
WaveTone pages, 1.12 emulator, a snapshot booted on the build). USB: 808 B smaller than b2-tune
(our own knob, label and panel drawing removed). Research notes:
`dn2mk2-scratch/widgets/FINDINGS.md`.

Not known yet: the track box's frames past track 1 (inferred: one per track), the header's
machine-name title, and none of this has run on the instrument.
