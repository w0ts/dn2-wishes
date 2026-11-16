# The list popup (OS 1.12, 2026-11-09; on v0.47 2026-11-10)

A parameter whose value is a list of names shows that list round its value while its knob
turns, as Optimist's list popup does (the User's own firmware, `op_preset.c` pop_kind 3,
GPL-3.0-only: its behaviour borrowed with credit). Stock OS 1.12 has no such popup (its lists,
`MachineListView` and `ModDestListView`, are modal menus opened with a key; `PopupWindow` is a
message box), so it is drawn by our code over the page: `csrc/waverider/popup.c`.

## Behaviour

- Opens on the knob's turn, on the page that draws that knob's place as a list. The knob sets
  the value as before; the popup only shows it.
- Five rows: the value lit in the middle, its neighbours above and below. The list stops at its
  ends (blank rows past them). The header: the parameter's label and the place, "9/12".
- Goes 1.5 s after the last turn, or at once on any key press except FUNC and an encoder's push.
- A trig held: the page shows the trig's p-lock, and so does the popup.
- Covers the eight places (x 21..127, y 0..53); stock's title bar and left panel stay.

## Two parts, each its own switch

`src/dnfw/waverider/cpage.py`: `POPUP_OURS`, `POPUP_STOCK` (the C build's `WPOP_OURS`,
`WPOP_STOCK`). Either ships alone. `POPUP_MIN` (4, the User): a list shorter than that (2 or 3
entries: XDLY's and FDN8's TYPE, RSET, the switches) gets no popup.

**Ours** (`wpop_offer`, from each page's own draw):

| machine / FX | parameter | list |
|---|---|---|
| PERC (page 2, H) | TYPE | the 34 Machinedrum machines, each with its family (TRX-RS RIMSHOT) |
| SOPHIE (G) | MODL | FUSE STAK SPLT SHRD PIPE BOOM KICK |
| PLAITS (G) | MODL | the 12 engines; GRAN's retired slot left out, as the knob steps past it |
| INSERT pages (FX 2/3 and 3/3, A) | M.SEL | OFF FUZZ TAPE FOLD CHOR WIDE HARM FDN8 XDLY |
| Delay page (G) | TYPE | XDLY STOCK (2: no popup with POPUP_MIN 4) |
| Reverb page (G) | TYPE | FDN8 STOCK LONG (3: no popup with POPUP_MIN 4) |
| sample machines | PLAY, MODE | their four modes |

Not lists (left as they are): SOPHIE has no FBMD; TB303's WAVE is a continuous saw..square
blend; PLAITS' TUNE / FINE and the ROM waves S01.. are numbers; the sample machines' SAMP has
its own list (smp_page.c).

**Stock** (`popup_stock.c`, from `page.c` wr_cell, after every stock cell): a record whose range is
whole steps of 0x100, POPUP_MIN to 64 entries, and whose own formatter (record + 0x34) names every entry
(none starts as a number does). Emulator-checked: WaveTone MOD (Off .. Hard Sync), RSET (Off On
Random: 3, none with POPUP_MIN 4), LFO WAVE (TRI SINE SQR SAW EXPO RAMP RAND), LFO MODE (FREE TRIG HOLD ONE HALF). Left
alone: two-way switches (TBL1/2, AMP MODE, FX PRE/POST), numbers (FM algorithm, MULT, speeds),
the multimode filter's TYPE (a continuous record), LFO DEST (stock's own modal list, unchanged).
Pages stock draws without its cell routine (if any) are not reached.

## Plumbing

- `rec.c` smp_ui_pop: the knob turned (`smp_knob_code`, `smp_knob_at`) and the order of the last
  turn and the last key press (`smp_knob_seq`, `smp_key_seq`: the frame counter can stand still
  between two items, and stands still in the emulator until the audio tick runs).
- `page.c` wr_screen: `wpop_begin` before the draw, `wpop_draw` last (before the meter);
  wr_poll: `wpop_poll` asks for a redraw on each turn (so a list's end still opens it) and when
  it goes.
- Emulator checks: dn2mk2-scratch/popups (scen.sh; the frame counter moved on with `addl` to
  close it).
