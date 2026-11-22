# The modulation matrix (OS 1.12)

More routes than stock's one per LFO. Decided by the User, 2026-11-11:

- up to **16 LFO routes a track**, shared by LFO1-3; each LFO's first route is stock's DEST and DEP (2026-11-18: kept
  for stock firmware, our matrix the only source: "An LFO's first route" below);
- ENV1 and ENV2 (phase 3) with four destinations each. 2026-11-12, the User: ENV1 **is** stock's AMP envelope (still on
  the amp, now also routable); ENV2 is "just a clone of env1", routed only;
- MOD SETUP keeps stock's four per source;
- a **constant-cost** evaluator: a frame costs the same whatever is routed;
- the popup (phase 4): a plain push opens it on a parameter at the release (2026-11-19; until then FUNC + short push),
  FUNC + long push (0.6 s) resets the parameter;
  layout A, a moving bar, a LOCKS strip, "13/16" and FULL.

Phases: 1 the wishes record (`docs/wishes-record.md`), **2 the evaluator (this page)**, 3 the envelopes and their
MOD pages, 4 the popup, 5 presets and Transfer carrying the record.

## Where the routes live

A sound's routes are one field of its wishes record, tag `WT_MX_ROUTES` (0x0010, neither must-understand nor tied to
the machine), four bytes a route:

| byte | |
|---|---|
| 0 | the source: 0 LFO1, 1 LFO2, 2 LFO3, 3 ENV1, 4 ENV2 |
| 1 | the destination: a slot of the voice row, 25..100 (a sound parameter) |
| 2-3 | the depth, big-endian, in stock DEP's units: 0..0x7ffe (DEP's own range), 0x4000 adds nothing |

At most 15 LFO routes are laid out (16 a track, at least one of them stock's route 1) and four for each envelope.
Anything out of range is skipped. A route into an LFO's own controls (slots 1..24) is not offered: it would land after that LFO has read
them. Stock's DEST, and the cascade (`docs/modulation-more.md`), still reach them.

## An LFO's first route: stock's DEST and DEP (2026-11-18; its depth moved into the record on 2026-11-19, below)

The User: "i would not use the stock modulation destination, we keep it just for backward compatibility but that's
all. (so we import it into our matrix, but dont use it). and we save the first one of modulation, it is for
compatibility with stock." Design B ("neutralise and mirror", the User's choice), as built (`csrc/matrix/routes.c`):

- **Our matrix is the only source of an LFO's routes.** An LFO's **first route is its DEST and DEP** (the sound's own
  cells); its other routes are the record's. A sound loaded with DEST set has its first route at once (the import is
  that reading: nothing is written, so an unmodified project stays as it is, byte for byte), and an outside change of
  DEST or DEP (a load, the plugin, CC, Overbridge, a DEP or DEST p-lock) is the first route's change. Saving writes
  the first route as stock reads it (it is DEST and DEP): a stock unit plays each LFO's main route.
- **Live**, the first route is added by stock's evaluator from the voice row's DEST and DEP cells, LFO3, LFO2, LFO1,
  then the record's routes (`mx_eval`): stock's order and arithmetic, so DEP and DEST p-locks, CC, Overbridge
  automation and an LFO on DEP work as on stock. Measured: the whole mirror (16 voice rows) equal frame by frame to
  main-next's for 600 frames with DESTs of every kind, DEP and DEST p-locks moving, with and without routes of the
  record (`rr/lfo-dest-popup` `stockonly.py`, build 71e2169e against ours).
- **A muted first route** keeps DEST and DEP (saved as they are: a stock unit plays it) and gets the record's mark: a
  4-byte entry `MX_FIRST | MX_MUTED | l` (0xC0 + LFO), its slot and depth bytes DEST and DEP as they were. A build
  before it skips the entry (a source of 5 or more) and plays DEST. `mx_poll` lays each track's marks out as masks
  (`mx_dmask[l][t]`: all ones, or 0) and keeps the sound each track's masks are for; MOD SETUP's pass (`mods_fast`),
  after a voice row's sources and its key track, ANDs the row's three DEST cells with its voice's track's masks
  (stock's own track word `0x80005308[v]`) when the voice plays that track's sound: a muted first route is DEST none
  for the frame whatever MOD SETUP added (its write lands in slot 0, as stock's DEST none does).
- **The mark belongs to the route it muted** (2026-11-18, the checks of the edge cases, gate `destpop` `edges`):
  - a DEST changed from outside (CC, Overbridge, the plugin: the sound's DEST written) is a new first route: it plays,
    unmuted; put back to the marked slot, it is muted again. `mx_poll` compares each marked LFO's DEST with its mark
    at every UI pass while a mark is laid out (a mark costs the UI pass a few compares; none, nothing). The popups
    show it so (the route muted only while DEST is the mark's), and a DEST or DEP p-lock is the same first route;
  - a sound-locked voice (a voice of the track playing another sound) is not muted: the mark is the track's sound's,
    as the record's routes are (a voice on another sound hears none);
  - MOD SETUP routed into an LFO's DEST (stock's MOD SETUP list offers none; a sound made elsewhere can hold one):
    the mask comes after MOD SETUP, so a muted first route is never heard through it (the User, 2026-11-18; checked
    at depths +0x0400, +0x2000, +0x7fff and -0x2000).
- **Deleted** (a long NO, turned to 0; 2026-11-19: DEP and its p-locks, the attenuverter's, are kept, the depth set to none): DEST 0, then the LFO's
  next route of the record (in the record's order) moves into DEST and DEP, its mute as the mark: the sound keeps a
  main route for stock firmware. A route added while DEST is free is the first route.
- **An LFO's controls** (slots 1..24, LFO4's 101..108) have no route of the record (it would land after that LFO read
  them): such a route can only be a first route, and cannot be muted. A second one while DEST is in use is refused
  (LFO CTRL: 1 ROUTE). **LFO4** keeps its own DEST, the one route lfo4 evaluates (a matrix source for LFO4 is a later
  step).
- **Cost**, the frame's parameter path (`rr/lfo-dest-popup` `smcost.py`: the smoother, MOD SETUP, the evaluator call;
  main f4faca86 against ours): every voice on its track's own sound 44,959 -> 45,168 (+209; smoother 12,327 ->
  12,264, MOD SETUP 7,357 -> 7,629); every voice on another sound 47,431 -> 47,480 (+49, the worst frame of both). The
  same with every first route muted, but for the evaluator's clamp branches (+14). `mods_fast`, a voice row's three
  DEST cells ANDed after its sources, the voice's sound compared; `sm_fast`'s copy of the DEST words unrolled
  (stock's loop, the same words, 63 instructions fewer); the evaluator and `mx_eval` unchanged.

## DEP: the LFO's global attenuverter (2026-11-19)

The User: "LFO DEP becomes a GLOBAL ATTENUVERTER for that LFO: every route of the LFO (its first route = stock DEST,
and the record's routes) is heard at route depth x DEP", -64..+63 = -100..+100 % (negative inverts), default 100 %;
"what is done to old lfo is applied/converted as modulation slot 1"; "we map the depth plock to our attenuverter"
(`csrc/matrix/atten.c`, `csrc/modulation/hooks.S` lfo_fast, `matrix.c`):

- **DEP is stock's parameter, now the attenuverter**: its cell, p-locks, CC, Overbridge, the plugin, MOD SETUP into
  DEP and an LFO into DEP all move it, per voice, per frame (they all land in the voice row's DEP cell, which
  lfo_fast reads where stock read DEP). The scale is stock's own DEP scale, a = DEP - 0x4000 (Q14), from a 512-entry
  table by DEP >> 7 (`mx_atab`: exact at every knob step, 0x100); **+63 and above (0x7f00..) is exactly 100 %**
  (MOD SETUP's 0x8000.. too); DEP 0 is -16383/16384.
- **The first route's own depth is the record's**: `WT_MX_LFO` (0x0013), LFO1-3 `{u16 DEP as saved, u16 depth}`. The
  popups read and write it (`routes.c` `mxr_first_dep` / `mxr_first_set`); DEST stays stock's cell. Deleting a first
  route no longer touches DEP or its p-locks (they are the LFO's). FUNC + long push on DEP: 100 % (0x7ffe).
- **Heard** (`lfo_fast`, at each LFO's step; with half-rate LFOs at its voice's turn, a held output keeping its
  scale): M = `mx_atab[DEP >> 7]` = -a << 17, `-out x DEP` = mac(out, M) into our word beside the LFO state
  (`mx_kof`: env_out's row, word 2 + 10 l), the record's routes' source (their depths laid negated, `mx_lay`): at 100 %
  exactly -out, so mac(-d1, -out) = mac(d1, out), stock's route 1 bit for bit. The first route stays stock's write in
  stock's place and order: -2 x (its depth - 0x4000) (word 3 + 10 l, written by `mx_eval` for each voice from its
  track's table) on -out x DEP. That word 1 (`MX_PASS`: a sound not converted, a voice on a sound lock, LFO4, the
  frames before the load's first UI pass) runs stock's route 1 itself, DEP its depth. The frame's first call after a load sets every
  such word to `MX_PASS` (`mx_pass_all`, from the cascade's `mc_zero`); the load's first UI pass works each voice's
  scaled output out from its row (`mx_seed_out`), so a held output is right from the first frame.
- **Two forms of a sound**: converted (a sound of the playing kit; `W_ATT` in its RAM entry): DEP the attenuverter A,
  the depths in the field; stored (what the saver writes, every sound as the loader leaves it, a sound lock's): DEP =
  C = depth x A, what a stock unit plays. The UI pass converts the playing kit's sounds (`mx_poll` -> `mxa_convert`):
  with the field, A back (stored DEP = the field's C; changed on a stock unit: A kept, the depth = DEP / A, the User's
  Q4 a); without (an old project, stock's): the depth = DEP, DEP = 100 % (0x7ffe). The saver (`wish_save` ->
  `mxa_save`) writes C into the stored DEP (stored ids 29..31) and A into the field. An old project's sound is stored
  again byte for byte (C = its old DEP) plus our link.
- **The conversion goes live in one step** (2026-11-21): `mxa_convert` writes the field and stages A; `mx_poll`, with
  the wishes table's lock and every interrupt masked, makes the track's new table live and commits it (`mxa_commit`:
  DEP = A in the sound; on each voice playing it whose row holds the sound's DEP, the smoother's source, state and
  output on A; `W_ATT`), with the voices' first-route words and, for each LFO whose DEP moved, its scaled output. Until
  then the sound is in the stored form. Before, stock's smoother glided the row's DEP from C to A while the first route
  already played D: the LFO heard at D x (C .. A) for tens of frames (gate `matrix`, `attslide`: converted mid-play,
  old sounds bit for bit, saved ones within C's rounding; the build before fails it by up to 28,884 on a cell). Only the
  UI pass converts (`routes.c` asks `mxa_is_converted`). A kit sound copied while the table is locked keeps its record
  and `W_ATT` (csrc/wishes/table.c's queue; `attcopy`).
- **Old projects** (no field): bit for bit as before while DEP is not modulated (gate `matrix`, `attexact`). DEP
  p-locks, MOD SETUP into DEP and an LFO into DEP now move the attenuverter: on those steps or voices every route of
  the LFO is scaled (the first route: depth x (100 % + the change), where stock added the change to the depth).
- **ENV2's H** is ENV2's attenuverter: `WT_MX_ENV` byte 7 = 127 - the knob (0, every record before, = 100 %),
  lockable (stored id 209, RAM head 0x59); its routes' source is -level x H (`mx_eval`, exactly -level at 100 %).
- **Cost** (coupled emulator, the build's own snapshot, 300 audio interrupts, `rr/dep-atten` cpuprof, against
  mod-faster 20bccdfa): idle 37,298 -> 37,787 instructions a frame (+489: lfo_fast +288, mx_eval +193), busy
  38,585 -> 39,041 (+456); about 0.8 % of the CPU, the same idle and busy.

## How a route is heard

Stock's evaluator `0x40137a06` walks the 16 voice rows. For each row it runs LFO3, then LFO2, then LFO1, and adds
each LFO's route 1 into its DEST cell (`0x40137d6a`):

    cell = clamp(cell + mac((DEP - 0x4000) x 2, out), 0, 0x7f00)

`out` is the LFO's output after its fade, kept at its state + 84. Row v's LFO l is at `0x44640C1C + 120 v + 40 l`
[measured in the 1.12 bytes]. A row's cells are at B + 34 + 202 v + 2 slot, with B the evaluator's first argument
(the mirror OUT, `0x800068e4`).

The frame's evaluator call (`0x400272d4`) is modulation's `mod_eval` (`csrc/modulation/hooks.S`). It runs the
cascade's pre-pass, then stock's evaluator with the caller's seven arguments, then `mx_eval(B)`
(`csrc/matrix/matrix.c`). That adds each row's routes with stock's own instruction (`mac.l`, then `movclr.l`, under
the frame's fractional MACSR), clamping after each route as stock does. A route at depth D is heard exactly as stock's
route 1 at DEP D. The gate step `matrix` (`scripts/emu_matrix.py`) checks this frame by frame on every row, and with
three routes into one slot listed in stock's order (LFO3, LFO2, LFO1).

**A voice's track** is the kit sound it plays. Stock writes the sound a voice plays at `0x800052a8[v]`
(`0x4002549c`, the same call that copies the sound's parameters into the voice's row; LFO4 keyed on it on 1.11,
measured on the instrument). The frame takes (sound - kit - 52) / 1163, a multiply exact for every whole sound,
and checks the sound against that track's. A voice on any other sound gets no routes.

**Constant cost.** Every row runs all 15 routes every frame. An unused route adds 0 into a scratch row of ours, at
an offset that fits every row, so no route and every route take the same instructions. The clamp's two branches are
the only difference.

**The same work, faster (2026-11-18).** The 23 routes are unrolled: each pair's two table rows (cell, d1, source:
24 bytes) come in one `movem.l`, and each route's cell is read while its `mac.l` runs; each route and its clamp are
stock's route 1 as before, in table order. Both envelopes are stepped inline (no call). The tables and `env_out`
are long-aligned (the m68k ABI aligns an `s32` at 2: they sat at +654 and +10026, so every route's longs were two bus
accesses). Emulator, `mod_eval` a frame (`rr/mx-faster` `mxprof.py`, worst.py's states): `mx_eval` + `env_step`
7,793 -> 5,506 instructions idle, 7,977 -> 5,710 worst; misaligned accesses 1,168 -> 177 a frame (the matrix's
1,136 -> 0). The cells and envelopes are bit-exact with the earlier code (random-state comparison in the emulator).

## The envelopes (phase 3)

Stock's AMP envelope runs on the SHARC (section 7), and the ColdFire cannot read it. ENV1 and ENV2 are a **ColdFire
clone** of it (the User's choice A), one pair a voice, stepped once a frame in `mx_eval` (one DSP block, 32
samples) after the LFO routes and before the envelopes' own routes. The amp's own envelope is untouched; nothing is
sent to the DSP.

- **ENV1** takes its knobs from the voice row's own AMP cells every frame: ATK 81, HOLD 82, DEC 83, SUS 84,
  REL 85, MODE 91, RSET 92. Those are what the DSP is sent, so LFO modulation and p-locks of the AMP page reach
  ENV1 as they reach the amp. (2026-11-18) That includes the record's LFO routes into those cells: ENV1 steps after
  them (routes 0..14), so it reads the cells as the DSP is sent them. Before, it stepped before every route and heard
  only stock's (an LFO's first route, MOD SETUP), while the amp heard the record's too (`scratch/env2-mod.md`;
  `test/test_matrix_c.py`). Every cell and level is as before unless an LFO route of the record goes into these cells.
- **ENV2** takes the same seven from the sound's wishes record (`WT_MX_ENV` 0x0011: ATK HOLD DEC SUS REL MODE
  RSET, a byte kept 0). With no field it uses stock's own defaults (records 62..66, 73, 74: ATK 8, HOLD 127, DEC 32,
  SUS 96, REL 24, ADSR, RSET on).
- **ENV2's locks** (the User: "Yes, p-lockable", all six; 2026-11-19 H, 2026-11-20 HOLD): with grid recording on and a trig held, a knob on ENV2's
  page sets that step's lock on every held step, as stock's own knobs do; the page shows the held trig's values, a
  lock drawn as stock draws one. The locks are records of the pattern's lock pool of ours, kinds 3..8 of slides'
  (`csrc/slides`, table-driven since): stored ids 203..208 (ATK DEC SUS REL MODE RSET; `docs/lock-id-table.md`),
  RAM heads 0x53..0x58. They are kept, cleared, copied and pasted (page and trig) with slides' own; the lock list's
  tail carries the step's six values (`sl_build`), and at the trig (`sl_apply`) they become that voice's ENV2 knobs
  until its next trig, over the record's. A full pool refuses a lock, as stock does. Stock firmware drops them on
  LOAD and keeps everything else (as slides).
- **Note-on and note-off** come from DRONE HOLD's hooks, which every note passes through: `hold_len` (a note that
  plays, not one HOLD drops) and `hold_final` (the frame's composed amp note-off word, `+36`).

**Measured in Elektron's own DSP code** (the SHARC runner; the level is the DSP's word `0x2547c8`, found by searching
its memory for the amp's measured gain; `csrc/matrix/amp_env.json`, `scripts/gen_matrix_env.py` ->
`csrc/matrix/env_table.h`):

| stage | law | measured |
|---|---|---|
| attack | linear, a length in samples | all 128 knobs: the level after n blocks is s (32 n + 0.5) from a reset, to 6e-7; s = 1/33, 1/48, 1/67, 1/90 for knobs 5..8; knobs 0..4 end inside the first block |
| decay | geometric toward SUS, a ratio a block | all 128 knobs, the same ratio over 3 blocks to 3e-7; knob 127 does not fall; DEC 40 gives the 1,742 ms (60 dB) of `docs/stock-units.md` |
| release | geometric toward 0 | all 128 knobs: the same table as the decay's, to the last bit of the DSP's float |
| MODE 1 (ADSR, the default) | attack, decay to SUS, at the note-off a release from the level reached | |
| MODE 0 (AHD) | attack, HOLD, then a decay to 0 at DEC's rate; SUS and REL unused | a note-off in the attack starts the decay; HOLD 127 (the default) lasts until the note-off; HOLD 0 none; a timed hold is not ended by a note-off |
| RSET | 1: a note-on restarts from 0; 0: the attack goes on from the level reached | |

Knobs 8 and 9 give the same values in every table, as do 12 and 13, and 17 and 18: the DSP steps its own curve.
Its memory holds no table of these (L1, L2 and DDR searched), so the clone's tables are the measurements.

**Checked:** the C against the model on the host (`test/test_matrix_c.py`, every case), the target's C against the
model in the ColdFire emulator through HOLD's own hooks (gate step `matrix`, its `env` scenario), and the model
against stock's own envelope in the SHARC runner, block by block (`scripts/sharc_matrix_env.py`, gate step
`envclone`).

## The AMP pages

[AMP] on stock's AMP page now steps AMP 1/2 (stock's) -> 2/2 (ENV2) -> 1/2 (2026-11-19: the scope left AMP's pages; it
opens on a long [TRIG], docs/scope.md). Their titles (the User, 2026-11-13): **ENV1/AMP**, **ENV2**; the page dots say
which of two. Stock's own header for the
AMP mode, a bare "AMP", is renamed ENV1/AMP by inserts' header hook (`ins_header`, as it names FX's pages), so only
that page's title changes, nowhere else stock writes "AMP". The gate's `matrix` step (`titles`) reads each back from
the title bar and checks it ends clear of the screen's right edge. Each page's place is
one constant in `csrc/waverider/amp_pages.h` (the User: the scope "might move elsewhere"). ENV2's page
(`csrc/matrix/env2_page.c`) is drawn by stock's own AMP page code with ENV2's values (the User, 2026-11-13: "why is
ENV2 not like ENV1"): stock's draw (`0x4006dfb6`) walks the 8 places, each place's record id from the table of the
envelope's MODE (`0x400c25d8`, 14 AHD / 15 ADSR), its knob drawn by the page's own method (+180), then the shape
(`0x40065766` AHD, `0x4006594c` ADSR, from plain values). ENV2's page makes the same calls on stock's AMP page object
with ENV2's MODE and values: the same knobs, labels, lock look and shape preview. The places (read in 1.12): ADSR
A ATK, B DEC, C SUS, D REL, E RSET, F MODE; AHD A ATK, B HOLD, C DEC, E RSET, F MODE (D empty). G and H (records 71,
72: PAN, VOL) are the sound's, not ENV2's: drawn with the sound's values as stock draws them, and turned by stock's
page beneath, as on AMP 1/2. HOLD (AHD) is lockable too since 2026-11-20 (stored id 210, below). The gate's
`matrix` step (`env2page`) sets ENV2 to the sound's own envelope and checks ENV2's page is stock's AMP page pixel for
pixel below the title bar (but for the page dots), in ADSR and AHD.

**ENV2's knobs as destinations (2026-11-18, the User).** ATK HOLD DEC SUS REL (not MODE, RSET) are destinations of
the record's routes: 0xE0 ATK, 0xE1 HOLD, 0xE2 DEC, 0xE3 SUS, 0xE4 REL, in the same 4-byte route entry. A build before
skips them (a slot over 100). Each voice has an ENV2 knob row in MX_RAM (`e2row`, a voice row's stride, as the scratch
row): every frame the record's knobs (or the trig's ENV2 locks) are written there, the routes into ENV2 add to it as to
any cell, then ENV2 steps from its high bytes. The frame's order: the LFO routes (0..14), ENV1 steps, ENV1's routes
(15..18), ENV2 steps, ENV2's routes (19..22): an LFO or ENV1 can move ENV2's knobs in the same frame; ENV2 into its own
knobs is refused (it would land after ENV2 stepped). The same work every frame; bit-exact for a sound with no route
into ENV2 (`test/test_matrix_c.py`). Such a route is never an LFO's first route (DEST is a voice-row slot for stock), so
stock firmware never plays it; it counts in the LFOs' shared 16 (or ENV1's 4). Chosen from the routes popup on ENV2's
page: FUNC + push on ATK..REL opens it on "ENV2 DEC" etc.; the ENV2 row says NOT ITSELF; FUNC + long push resets
ENV2's own knob (`env2_reset`). MOD SETUP into ENV2's knobs: not now. The moving lines under ENV2's ATK..REL show the
knob as ENV2 hears it (`mx_e2_knob`); PAN and VOL keep theirs (their records are the sound's).
Gates: `matrix` (`env2pop`), `lineonly` (`env2`).

**MODE, RSET and H as destinations; HOLD lockable (2026-11-20, the User, after the audit `scratch/modlock-audit.md`).**
0xE5 MODE, 0xE6 RSET, 0xE7 H (ENV2's attenuverter): the knob row has eight cells, 0xE0 + the clone's knob index (ATK
HOLD DEC SUS REL MODE RSET H). The frame writes all eight from the record (H as its knob, 0..127 = -64..+63, << 8) or
the trig's locks, the routes add to them, then ENV2 reads MODE and RSET as ENV1 reads the AMP cells (the high byte not
0: ADSR, RSET on; so a route from AHD to ADSR needs only a small push up, and back down from ADSR a push of the whole
step) and takes H's scale from the cell (`mx_m_of`), after the routes. RSET is read at a note-on only, MODE every
frame. A MODE moved from ADSR to AHD during the decay: the note-off still ends the note (it falls at DEC's rate as
AHD's decay); before, that stage had no note-off in AHD and would have held SUS until the next note. ENV1 shares that
step: an LFO into the AMP's MODE (stock's) now ends the same way; what Elektron's DSP does then is not measured. The
routes popup opens on MODE, RSET and H on ENV2's page ("ENV2 MODE", "ENV2 RSET", "ENV2 DEP"); their moving lines are
ENV2's knob row's, as ATK..REL's. **HOLD's lock**: stored id 210, RAM head 0x5A (slides' kinds, the 8th ENV2 kind;
`docs/lock-id-table.md`); the lock list's tail carries eight ENV2 values (32 bytes of the 36 free). The same work for
every sound: three cells more a voice copied, H's table read every frame (about 16 x 6 instructions a frame, not
measured on the unit); bit-exact for a sound with no route into MODE, RSET or H (`test/test_matrix_c.py`).

## The routes popup (phase 4)

`csrc/matrix/routes_pop.c`, the owner's layout A (`scratch/modulation/dest-knob.md` §1, §7 and its mock-ups):

- **A plain push** (2026-11-19, the User) on a sound page opens it, on the push's **release**, only when nothing else
  happened while the knob was held: no other key's item (NO, YES, FUNC, a trig, any key), no turn of another encoder
  (`mxp_seen`, called first for every item in `rec.c` `smp_ui_pop`), and no key already down at the press (LIVE REC's
  NO + push, a trig held + push). It is armed at the press only where it can open (the same checks as the open).
- **The pushed knob's wobble** (2026-11-20, the User: "if the knob moves (even by one) while pressed, it doesn't
  work"; one count already moved stock's push + turn a big step): `mxp_seen` holds back the pushed knob's own items
  while their counts summed stay under `KN_PUSH_WOBBLE` (4, `csrc/knobs/knob.h`) either way: they are dropped before
  anything sees them, the value never moves, and the popup opens at the release. The item that reaches 4 carries
  every count held back to stock at once (push + turn's big steps, from the first count) and cancels the popup. A
  push that is not armed (FUNC, a trig or another key held, a page where it cannot open) passes every count as
  before. Every item of the push goes on to stock as before: stock's peek (the value in the
  label) shows on the press, push + NO resets on NO's release, push + turn takes big steps, a trig + push clears that
  trig's lock; each of those cancels the popup. A long plain push opens at its release too (stock does nothing more on
  a long push). The knob's parameter is the one drawn in that place in the page's last draw, read at the press
  (`knob_rid`; the left panel's LEV is not a place), told by stock's place drawer `0x400169de`'s exit (`pages.py`
  `wr_place_tail` -> `mxp_placed`, every stock machine's places, by the view's own place: 20-byte entries from the view
  + 180; FM TONE's own widgets never reach the cell widget `0x4006448a` and lie off the usual columns), by the cell
  widget's exit
  (`page.c` `wr_cell`) and by our pages' knobs (`moving.c` `mv_knob`: our machines' and the sample machines' pages
  draw their own). Until 2026-11-20 only the cell widget told it: SYN 1 and 2 of FM TONE and of every machine of ours
  found no parameter and nothing opened (the User: "I could not get it to work").
- **FUNC + push is stock's** (2026-11-19, the User; the knob-push survey, `scratch/knob-push-survey.md`): the peek;
  on a MIDI track the on / off of CHAN, BANK, PROG, CC VAL...; on an LFO's DEST stock's list. Until then `mxp_pop`
  took every FUNC + push press before knowing whether the popup would be refused, and the MIDI on / off and the DEST
  list were lost. **FUNC + a push still held at 0.6 s** resets the parameter to its record's default (stock's own
  `setValue`, as a knob writes it; an LFO's DEP: 100 %); never an LFO's DEST, where stock's FUNC + push opens its
  list. Stock's peek is the only other thing a FUNC + push does on a sound page, so the reset takes nothing from stock.
- **The screen:** a slim header with the parameter's name, then a row a source: LFO1-3 (their icon is their WAVE),
  ENV1, ENV2. A row at depth 0 is an empty line; a route shows its depth (DEP's units, -64..+63) and the moving bar
  (the outline the reach, a tick the depth, the solid bar the offset the source applies now on the voice the track
  last played). The lit row shows its count: the LFOs' shared pool "n/16", an envelope's "n/4", FULL.
- **Sections** (the User, 2026-11-19): FUNC + DOWN moves the lit row to the first row of the next section, FUNC + UP
  to the first row of its own section (of the previous one when it is already there); at the top and bottom it stays
  (no wrap). A section is a run of rows of one kind as the rows are shown (sorted at the open): the LFOs (LFO1-3), the
  envelopes (ENV1, ENV2), MOD SETUP's (VEL MW PB AT BC KEY). With routes on LFO2, ENV1 and PB the rows are LFO2 | ENV1
  | PB | LFO1 LFO3 | ENV2 | VEL MW AT BC KEY: six sections. A held FUNC + DOWN / UP jumps on with the key's repeats.
  Every UP / DOWN item is the popup's while it is up (none reaches stock); FUNC alone and FUNC with the other keys do
  what they did.
- **Turning speed and the notch** (2026-11-19, `docs/knob-notch.md`): a slow turn (records of 4 counts or less) moves
  1 unit every 3 counts, faster 1 a count, a fast one 2 a count; depths are kept on whole units, so 0 is always
  reachable; turned across 0 a route stops there (deleted) for the next 9 counts the same way. The same in the DEST
  popup and on ENV2's knobs (H, the attenuverter, notched at 0); LFO DEP has stock's knob with the notch at 0.
- **Editing:** turning the knob sets the lit row's depth live; push-and-turn (or UP/DOWN) moves the lit row. Turned
  from 0, an LFO's row becomes its first route when DEST is free (DEST and DEP, so a stock unit plays it), else a
  route of the record. **Turned to 0, the route goes at once** (the User on the unit, 2026-11-17: a row at 0 still
  drew its value, its tick and the pool count until the close): a first route goes as deleted (DEST 0, DEP's
  default, the LFO's next route of the record into DEST and DEP; its DEP locks kept), a record's route is dropped;
  the row is empty, the counts drop, stock's own knob mark goes.
- **Add** (the User, 2026-11-18, as the LFO DEST popup): YES on an empty row of ours adds its route at +32 (the knob
  then sets it), placed as a turn from 0 places it (an LFO's first route when its DEST is free). The row shows it, with
  no word over the rows (the User: no ADDED box); FULL when the pool is full and nothing can be added.
- **Redraws** (2026-11-18, the User: "mod matrix popup => cpu warning"): the popup is drawn whole only when something
  of it changes by a key or knob; its moving bars and LOCKS' playing step are worked out 15 times a second and, when
  they changed, only their groups are sent, from the kept still layer (`csrc/matrix/routes_pop.c`, the line-only
  method of docs/display-path.md). The moving controls' lines under it no longer ask for redraws. Gate: `emu_matrix.py`
  popglass (the glass against a forced full redraw after every update), popcost (the cost).
- **Mute** (the User, 2026-11-17: "yes: unmute the row, no: mutes it"): NO (a tap) mutes the lit row's route, YES
  unmutes it. A muted route keeps its depth and applies nothing: the record's source byte carries `MX_MUTED` (0x80) and
  `mx_lay` lays the route in its place with d1 0, the cells exactly as at depth 0 and the same cost (no idle skip).
  An LFO's first route (2026-11-18) keeps DEST and DEP and gets the record's mark ("An LFO's first route" above);
  a route of the record unmuted while its LFO's DEST is free becomes the first route. A muted row shows its
  depth with a dotted bar and no live offset; the lit one says MUTE. It still counts in the pool and sorts as unused.
  A build before the flag skips such a route (a source of 5 or more): a muted route stays silent there.
- **Deleting** (the User, 2026-11-17: "or long no reset ... simpler", "funct +no to delete all modulation for that
  knob"): NO held 0.6 s deletes the lit row's route (an empty row: nothing); FUNC + NO deletes every route of ours into
  this parameter, muted ones too. A route of the record goes; a first route gets DEST 0 and DEP's default back (then
  the LFO's next route of the record takes DEST and the depth; 2026-11-19: DEP's p-locks are the attenuverter's and kept; until then they were freed: the lock pool's record written as stock's free ones are: slot 0xff, track
  0xff, 128 x 0xffff, the shape of 76 of 80 records in 1.12's pool). "DELETED" or "ALL CLEARED" shows for a second.
  There is no undo. **Not measured:** whether stock keeps other bookkeeping of its lock pool than the records (a lock
  freed here was only checked in the emulator, not on the unit).
- **Held keys** (2026-11-18, the User: "holding NO also only mutes"): while a key stays down, stock's key task
  (0x4011f8bc) sends it again, 24 panel ticks after the press (0.2 s), then every 8, with bit 3 set beside the
  press's bit 0 (measured on the unit: NO held 1 s, 13 items `code 12 flags 0x09`, the sixth `0x29`; 0x4029f0c8 = 24,
  0x4029f0c4 = 8). v1 read bit 0 alone as a press, so every repeat began the key again: a held NO's 0.6 s restarted
  every 8 ticks and its release muted (seen on the unit), FUNC + a held push never reset and its release opened the
  popup, a push-and-turn (and, in the DEST popup, D held at the open) held past 0.2 s closed the popup on its release.
  Now a repeat moves only UP and DOWN (the lit row steps with it, as stock's lists); any other repeat of a key whose
  press was ours is dropped. The emulator checks it with the keys held in panel ticks, stock's own repeats coming
  (emu_matrix and emu_destpop, scenario hold; `Panel.tick_clock`).
- **FUNC + push while up** is ignored, long or short, its release too: no close, no reset (the unit, 2026-11-17: a
  FUNC + long push inside left the popup and reset the parameter; a bounced push is the likely cause, not measured).
  FUNC + long push resets a parameter only with the popup closed.
- **Closing**, always kept: the same knob pushed (no turn), another knob turned, any key that leaves, a track change, a
  stock question, 6 s untouched.
- **Refused** (the push stays stock's alone): a trig held, a stock question, a page, list or popup of ours over the
  page (REC, SLICE, TUNING, KB SETUP's, the sample list and browser, MACHINE SEL, the inserts, the scope, a list popup,
  the DEST popup, an overview, the send pages' page 2, the big meter), a MIDI track, a parameter that is not a sound
  parameter of the voice row: its record's page id 16 or more (FX and globals, MIDI, the LFOs, 29 the trig page) or a
  slot outside 25..100; ENV2's own knobs on its page excepted. TRIG 1/2's FILL is a trig record at slot 25 (page 29)
  and opened a popup titled FILL until the page id was checked (2026-11-19). On ENV2's page G (ENV2's DEST) a plain
  push opens the DEST popup on the press, as before; its routes popup is no longer reached (it was by FUNC + push).

- **LOCKS** (the bottom line): this parameter's p-locks on the track's pattern (the pool's record of its slot and
  track): the 16 steps of the page playing, a filled cell a locked step and the playing step underlined, then a tick
  a page, tall when that page holds a lock, the page playing underlined.

- **MOD SETUP's rows** (VEL MW PB AT BC KEY, after ENV2; five rows are shown, the list scrolls with the lit row).
  2026-11-21, the User: "like other rows!" (`csrc/matrix/setup.c`, `setup.S`; design `scratch/setup-rows-design.md`,
  his answers to its six questions): stock's own entries, edited with our rows' keys, each edit through stock's own MOD
  SETUP object, so stock's MOD SETUP pages, undo, Overbridge and saving see it:
  - **The row** shows its source's entry into this parameter: its depth in stock's own MOD SETUP number (the word / 256,
    two decimals cut toward 0, as stock's pages print it: `0x01e7` 1.90, `0xfdf1` -2.05, `0x0d48` 13.28; -128.00 ..
    127.00), the bar as stock's kernel applies it (0 in the middle of its span: PB and KEY swing both ways, a negative
    depth of the others reaches left), dotted when muted. Its name says whose value it reads: `VEL/V` and `KEY/V` the
    voice's, `MW/T` `PB/T` `AT/T` `BC/T` the track's. The lit row: its source's own count of four ("2/4"), FULL, MUTE.
  - **Turn**: the depth, 1.00 a unit as our rows' (the notch at 0). From none, a new entry in the source's first free
    place (stock's setEntry); to 0, the entry goes, its place freed; otherwise stock's setDepth (its clamp -32768 ..
    32512). **YES**: on an empty row a new entry at +32.00, on a muted one unmute. **NO** (a tap): mute. **NO held 0.6
    s**: delete. **FUNC + NO**: every route of ours AND every MOD SETUP entry into this parameter deleted.
  - **Four a source** (stock's): with four places in use and none into this parameter, FULL; nothing written.
  - **Two entries of one source into the same parameter** (stock allows it): merged into the first when the popup
    touches them (a turn, YES, NO), the depths summed (stock's clamp), the others deleted.
  - **NOT IN SETUP**: a parameter stock's MOD SETUP list does not offer (its list entry for the slot is a record, not
    None, and passes the builder's mask for want 0x200, the same test as the DEST popup's `ldp_valid`; ENV2's and the
    inserts' knobs never) shows the row; a turn or YES is refused with NOT IN SETUP.
  - **Mute** (option A): the entry stays in the sound, untouched (stock firmware plays it, stock's page shows it); the
    record holds a mark (`WT_MX_SETUP`, 0x0015: `{list << 2 | place, slot, depth}`, 4 bytes a mark) of the entry as it
    was muted. The voices read MOD SETUP from their own 153-byte copies (`0x8000487c + 153 v`), which stock writes in
    two places only: a note (`0x4002549c`, the sound given to a voice) and an edit (`0x4002591e`, every voice of the
    track, after each setValue). Both load memcpy into `%a3` once (`lea 0x40134770,%a3` at `0x400254f0` and
    `0x4002594c`, which the wishes build had pointed at `wish_memcpy_stub`); those two `lea` now name `mxs_copy`: a
    153-byte copy is made there, each entry equal to its track's mark landing with depth 0 (a branchless mask, the same
    instructions marked or not, each long written once whole), any other size goes on to `wish_memcpy_stub` as before.
    The kernel then adds nothing for it, exactly as for that entry at depth 0. The frame is unchanged: `mods_fast` is
    not touched. A mark belongs to the entry it muted: changed from outside (stock's page, Overbridge) it no longer
    equals the mark and plays; put back, it is muted again (compared at every copy). A voice on a sound not the kit's
    (a sound lock's) is never muted. Muting, unmuting and a mark laid out by the UI pass (a load, undo) call stock's
    `0x4002591e` so the voices copy again at once.
  - **Measured** (`scripts/emu_setuprows.py`, gate step `setuprows`; claude/setup-rows on claude/up-v066): with no mark,
    60 frames x 16 voice rows bit for bit the base build's; MOD SETUP's pass 6,447 instructions on both; the note's copy
    (`0x4002549c`) 670 -> 824 instructions (+154 a note-on, marked or not: 0.27 % of one frame's CPU, 16 note-ons in
    one frame 4.2 % of that frame), the edit's copy into 16 voices 1,587 -> 4,003 (the UI task, after a setValue).
- **The rows with no route** (2026-11-21, the User: "so the User sees what each LFO and envelope is doing before routing
  it"; "keep it slow update, low CPU"): each row of the five shown with no route into this parameter (an LFO, an
  envelope, a MOD SETUP source) draws its source's level now on the voice the track last played as a dimmed line
  (every other pixel, the row's middle, from the bar's 0), in the moving layer: worked out every other pass of it (7.5
  a second), the same work whatever moves, and sent as the bars are (only the changed 8-pixel groups, never a full
  redraw; it never moves the knob). The moving layer is now made again and compared at every pass, moving or not (no
  idle skip). Measured (`emu_matrix.py popcost`, MW moving): the popup's poll 464,265 -> 486,065 instructions a second
  (+0.025 % of the CPU).

- **The rows' order** (the User, 2026-11-17: "the used modulation are on top of the list (ordered the same way)";
  MOD SETUP's rows sorted too, read only): the rows with a route into this parameter come first, in the usual order
  (LFO1-3, ENV1, ENV2, VEL MW PB AT BC KEY), then the rows without one, in the same order. A route at depth 0 counts
  as unused, a muted route too. The order is made when the popup opens and kept while it is up: a depth turned to or
  from 0, a route muted or deleted, moves no row under the lit bar; the next open sorts anew. The popup opens with the first row lit (a used
  one, when there is one). Turning, deleting and the counts act on the lit row's source through the order table
  (`mxp_order`, a place -> a source), never on its place on screen. Checked by the matrix step's `popsort` scenario
  (`scripts/emu_matrix.py`).

### Where stock keeps MOD SETUP (1.12, read in the bytes)

A sound's 153 bytes from byte 222 are its MOD SETUP: at each note `0x4002549c` copies them whole into the voice's
descriptor record (`0x80003af0 + 3468 + 153 v`), and so does `0x4002591e` for every voice of the track after an edit.
From +230 (+8): six lists of four `{s16 depth, s16 slot}`, 16 bytes a list, in the order **VEL PB MW BC AT KEY**
(2026-11-21, measured on stock 1.12's six MOD SETUP pages, SETUP > KEY TRACKING / VELOCITY MOD / AFTERTOUCH / PITCH
BEND / MOD WHEEL / BREATH CONTROLLER: the page titled MOD WHEEL shows the list at +262, PITCH BEND the one at +246,
AFTERTOUCH +294; BC +278 and KEY +310 by the sound object's attach order, `0x4004afec`, whose others match the pages.
Until then the popup's MW and PB rows read each other's list). The driver `0x400db390` runs the kernel `0x400db340` on
each list before the LFOs' evaluator: cell + value x depth / 2048, saturated. List l's value: VEL `0x8000dd40[v]`, then
`0x8000de40` (PB), `0x8000de20` (MW), `0x8000de00` (BC), `0x8000dde0` (AT) indexed by the voice's track
(`0x80005308[v]`), KEY `0x8000dda0[v]` (a long, >> 8, less 15360). Stored on the card as three bytes a target
(`0x400dd4cc`: the depth word, then a dest byte mapped to the slot by `0x400dce24`).

Stock's MOD SETUP page prints the depth word / 256 with two decimals, cut toward 0 (factory sounds hold 32512 = 127.00
and -32768 = -128.00); its knob moves the word by 1 a count. Its objects (2026-11-21): the track's sound object is the
kit object's +108 + 960 t (`UI_OWNER() + 0x160 + 960 t`, its storage pointer at +16 the kit's sound), each list a value
of it with the same interface (VEL's a ModConfig, vtable `0x401df2f8`, at +80; the others ValueWithMirror<modTarget_t[4]>,
`0x40200478`, at MW +220, PB +372, BC +524, AT +676, KEY +828): +16 setEntry(i, {depth, slot}), +32 setTarget(i, id),
+36 getTarget(i), +40 setDepth(i, depth), +44 getDepth(i). Each set ends in the value's change (undo, Overbridge) and
stock's copy into the voices.

## The DEST popup (2026-11-18)

The User: "editing destination in modulation page is cpu. and we need to redo this popup. it does not match our
modulation matrix. we need in the popup to have at the top the assigned ones, with their value, same shortcuts with
y/n". `csrc/matrix/dest_pop.c`, on `routes.c`:

- **Why it was slow** (emulator): stock checks a DEST value by building the whole destination list (`0x40039904` ->
  the builder `0x4003951e`: a virtual lookup per slot, the mask, push_back, then std::sort with two std::map lookups a
  compare, ~215k instructions) and looking the value's entry up in it. Every LFO page draw checks each knob's value so
  (`0x400645ce`), and stock's list made one at the press, 16 as it opened, 4 a row moved.
- **The value check** is taken over at its entry (`ldp_valid`): the entry of the value's slot is in that list exactly
  when it is not 0 and passes the list's mask (the builder pushes each slot's entry that passes; the mask reads the
  entry alone), so one lookup and one mask give stock's answer. Every other record goes through stock's own
  `0x40036bac`. The gate's `destpop` step (`valid`): every slot 0..127 of LFO1-3's DEST on three machines answered as
  stock's list says, no list built.
- **Opens** on every gesture that made stock's DEST list on an LFO page (LFO1-3, LFO4), in its place (the User,
  2026-11-18: "the destination for mod page is still the elektron one ... i just want ours"): D turned (one detent, a
  fast turn, with FUNC held, with a trig held), D pushed (stock made its list at the press), a push-and-turn, a trig
  held + push. The twist that opens it only opens it (no depth moves), as stock's lists. With a trig held it edits
  the sound's routes (stock set a DEST p-lock there; DEST p-locks already set still play). FUNC + push stays
  stock's: stock's DEST list (2026-11-19: the knob-push survey measured that list on stock 1.12; the routes popup had
  taken that push, so nothing opened; FUNC + a long push never resets a DEST). On every other gesture stock's list (its
  view `0x4010660c`) is never made: the gate's `destpop` step (`paths`) runs every gesture on LFO1's and LFO4's pages. The list is built once, by stock's walk and order (category rank, then record id), "None" and the LFO's own
  controls left out.
- **The rows**: the LFO's routes first (the first route, then the record's, muted ones too), in the list's order, then
  the rest. A route row: category, short name, depth, the moving bar (dotted when muted); the lit one says DEST, REC or
  MUTE. The header: LFOn DEST and the pool (n/16; LFO4 n/1). The footer: the lit route's long name, or what a turn or
  YES would do (ADD AS DEST, ADD TO MATRIX, FULL, LFO CTRL: 1 ROUTE, LFO4: 1 ROUTE). The order is kept while up.
- **Keys** (the routes popup's): D turned sets the lit row's depth (0 removes it; from 0 it adds the route); D's
  push-and-turn, UP, DOWN move the lit row; YES unmutes, or adds the lit row at +32; NO mutes (CAN'T MUTE for a first
  route into an LFO's controls and LFO4's); NO held 0.6 s deletes; FUNC + NO deletes every route of the LFO.
  **FUNC + DOWN / FUNC + UP** (2026-11-19, the User, as the routes popup's) jump the lit row by sections: this LFO's
  routes on top (the rows as made at the open), then each of stock's DEST categories in the list's order (the page id
  stock's list sorts by, `0x400dbe4c`, and its push-and-turn jumps by). DOWN: the next section's first row (on the
  last: stays); UP: this section's first row, or the previous section's when already there (the top: stays). A held
  FUNC + arrow jumps on with the key's repeats; every UP / DOWN item is the popup's while it is up. Gate: `destpop`
  (`jump`). Closed,
  kept: D pushed alone, a key that leaves, another knob, a track change, a stock question, 6 s untouched.
- **Drawing**: whole frames only after a change; the bars alone over the glass's last frame 15 a second while a route
  moves, never queued behind the panel UART.

## Read in the UI pass, never in the frame

`mx_poll` (from `page.c` `wr_poll`) lays the tables out again when any record changed (`wish_edits`, counted at every
change to an entry: made, copied, cleared, put, read from its cell) or when the kit moved. Each track's routes go into
its spare table, which then becomes the live one; the frame takes it from its next row. The frame never takes the
record's lock and never looks a sound up.

## RAM

`MX_RAM` `0x476F0000`, 16 KB (`dnfw.waverider.pages`, `docs/memory-map.md`): each track's table twice, an empty
table, the scratch row (16 x 101 words). It outlives a restart that keeps the RAM, magic and all (2026-11-18): it is
trusted only once this load's first UI pass has cleared it (`mx_loaded`, code data, 0 after every load). Until then the
frame adds no route, as at power-on. The same rule holds for every block of ours above BSS (`docs/memory-map.md`).

**The tables are read from the DDR every frame (2026-11-21).** The ColdFire's data cache is 8 KB (NXP MCF54418 data
sheet); `mx_eval` alone touches about 8 KB a frame (16 tables of 312 B, the envelopes, `env_out`, the ENV2 rows), and the
rest of the audio interrupt and the UI run between frames, so its table reads miss. The on-chip SRAM
(`0x80000000..0x80010000`) has no room: stock 1.12 uses all of it (`.data`, a 23,360 B area it clears at
`0x80008000`, eDMA buffers at `0x80001a20..0x80003af0`); only 1,664 B at `0x8000f980` were never touched in the
emulator walks, which is not proof and not enough room. Two build switches measure the cost on the instrument; both are
off by default and the same values reach every cell either way:

- `DN2_ROUTE8=1`: a route in 8 bytes (`cell`, d1 / 2 as s16, the source as an offset in the voice's `env_out` row),
  a table 220 B (14 cache lines a voice in place of 20), 4 more instructions a route. `scripts/emu_route8_ab.py`
  proves the frame identical byte for byte against the 12-byte build.
- `DN2_ROUTE_PROBE=1` (a test build's): `mx_probe`, called just before `mx_eval`, reads one long in every 16 bytes of
  each voice's table; in the CPU profile its share is what the line fills cost, and `mx_eval`'s share drops by as much.

The harnesses read `struct mx_state`'s offsets from its magic (`scripts/emulib/mxlayout.py`): the size differs with
`DN2_ROUTE8` and `DN2_LFO4`.

## Known limits

- ENV1 and ENV2 step once a frame (32 samples): where a stage ends inside a block, the clone is one block behind
  the DSP for that block. They also hear a note one frame before the DSP does.
- An envelope's own routes into the AMP envelope's cells (ENV1 into the amp's DEC, ENV2 into its ATK) come after the
  envelopes stepped: the amp hears them, ENV1 does not.
- (2026-11-18) HOLD 1..126 in AHD mode measured in Elektron's DSP code (`scripts/measure_amp_hold.py`, every knob to the
  sample: HOLD 1 14 samples, 4 144, 16 3,085, 64 88,206, 126 470,679 = 9.8 s; some neighbours equal, as the DSP has
  them; `amp_env.json`). The clone counts the samples held and compares them with HOLD's length every block, as the DSP
  compares its counter every sample, so a HOLD moved during the hold (a route, a lock) is heard at once, to the block.
  On 1.12 HOLD is not on the AMP page; its default is 127 (until the note-off).

- A voice playing a sound other than its track's kit sound (a sound lock) hears no routes of ours. Stock's route 1
  still plays.
- The depths are the record's, not modulated: stock's DEP is a cell of the row (LFOs and the six sources can move
  it), a route's depth is fixed.
- A route's slot means what that slot means on the sound's machine. The routes are kept when the machine changes
  (the field is not tied to the machine). What stock does with DEST then is not checked here.
