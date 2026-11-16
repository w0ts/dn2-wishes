# The list popup (OS 1.12, 2026-11-09; on v0.47 2026-11-10)

A parameter whose value is a list of names shows that list round its value while its knob
turns, as Optimist's list popup does (the User's own firmware, `op_preset.c` pop_kind 3,
GPL-3.0-only: its behaviour borrowed with credit). Stock OS 1.12 has no such popup (its lists,
`MachineListView` and `ModDestListView`, are modal menus opened with a key; `PopupWindow` is a
message box), so it is drawn by our code over the page: `csrc/waverider/popup.c`.

## Behaviour

- Opens on the knob's turn, on the page that draws that knob's place as a list. The knob sets
  the value as before; the popup only shows it.
- The turn that opens it moves nothing (2026-11-11, the User: "for all list popup that open on
  knob twist for first knob twist only open the popup"): `rec.c` smp_ui_pop asks
  `wpop_first_turn` before noting the turn and takes one detent off that item (a one-detent item
  goes); every later item, a fast turn's included, moves as before. "Opens" means the place was
  offered as a list in the last draw that reached `wpop_draw` and its popup is not up (another
  knob turned last, 1.5 s gone, or a key pressed since). Lists with no popup (POPUP_MIN) are not
  touched; TRIG page 2's slides (E, F) keep their own detents.
- Five rows: the value lit in the middle, its neighbours above and below. The list stops at its
  ends (blank rows past them). The header: the parameter's label and the place, "9/12".
- Goes 1.5 s after the last turn, or at once on any key press except FUNC, an encoder's push, the
  16 [TRIG] keys and the arrows (2026-11-12). Another knob turned shows that knob's list, or none.
- The [TRIG] keys (the User: "the list menu should not close when I press one of the 16 track
  buttons (to preview the sound)"): the popup stays and the key does what it does (the track
  plays). MACHINE SEL is stock's view and already stays open while a trig plays.
- The arrows (the User: "up and down keys should navigate in the open list (whichever kind);
  left/right page one page up/down"): UP / DOWN move the value one entry, LEFT / RIGHT five (the
  popup's rows), stopping at the ends, and keep it up as a turn does (`wpop_arrow`). Each list
  says how it moves: stock lists write the entry's value; our machines' choice controls (the
  Monomachine-family lists, the sample machines' PLAY / MODE) take one click each through
  `smp_quant`'s "one choice a click" (a retired choice stepped past, MONOMACHINE's engine
  started as on the knob); PERC's TYPE the middle of the machine's band; INSERT M.SEL through its
  own knob code. Not with a [TRIG] held (the page then shows that trig's p-lock): the arrows close
  it as before.
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

## A list to pick from: the filter type on FUNC + G (2026-11-11)

The User: "we could switch filter one type with FUNCT + G (with list popup)", "FUNC + turn G opens
the list". On the FLTR page (stock's view class `0x401E24C4`, measured), FUNC held and knob G turned
opens a list of the filter types in the same box (`wpop_modal`, `csrc/msel/msel.c` `flt_pop`):

- FILTER SEL's rows and names (`dnfw.waverider.msel`: MULTI-MODE, LOWPASS 4, LEGACY LP/HP, COMB -,
  COMB +, EQUALIZER, ANALOG SVF .. ANALOG MS-20 as the build carries them), names up to 12
  characters, the header `FLT1` and the place; the track's own type lit when it opens.
- The first turn opens it; each further turn moves it, stopping at the ends.
- FUNC let go, YES or G pushed: that type. NO, another key or another knob: the type stays. The
  key the list took (YES, NO, G pushed, an arrow) is the list's down to its release.
- UP / DOWN one row, LEFT / RIGHT five, a held arrow on (LIVE SELECT: committed once it rests, as
  on the knob). A [TRIG] key leaves it up; with FUNC held that key is stock's FUNC + TRIG (no
  note).
- The pick is MACHINE SEL's filter page's YES (`0x4005bbbe`): stock's commit
  `0x40031a56(model, track, type, 1, 1)`, only when the type changes, with the model MACHINE SEL
  holds (the UI owner's +0xF4) and the current track.
- Only G of the FLTR page: FUNC + turn on any other knob or page is stock's, as is FUNC + push G
  while the list is shut. Closing it ends the knob popup too, as a key press does.

## Plumbing

- `rec.c` smp_ui_pop: the knob turned (`smp_knob_code`, `smp_knob_at`) and the order of the last
  turn and the last key press (`smp_knob_seq`, `smp_key_seq`: the frame counter can stand still
  between two items, and stands still in the emulator until the audio tick runs).
- `page.c` wr_screen: `wpop_begin` before the draw, `wpop_draw` last (before the meter);
  wr_poll: `wpop_poll` asks for a redraw on each turn (so a list's end still opens it) and when
  it goes.
- Emulator checks: dn2mk2-scratch/popups (scen.sh; the frame counter moved on with `addl` to
  close it).
