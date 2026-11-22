# Hidden functions (dn2-wishes)

Every non-obvious key combination and setting of the custom Digitone II firmware, one line each. Items marked "(unverified)" were read from notes or code but not confirmed on the unit.

## Sound pages & knobs

- **FUNC tap, then press FUNC again and hold it (within 0.35 s, any page)**: the system meter fills the screen under the title bar: rows DSP (DSP load), CPU (ColdFire load) and RAM (memory), each a large figure and a long bar (on DSP and CPU a tick at the last 3 s's peak). It goes when FUNC is let go, or at once when any other key, push or turn comes (which then works as FUNC + it). A plain FUNC hold shows nothing. On the send Delay (XDLY) / Reverb (FDN8, LONG) pages the first tap also switches the page (FUNC tap's own function there). On Monomachine and Machinedrum pages the DSP % also shows in the tempo's place.
- **FUNC + turn (on our machines' controls)**: coarse jump. On the Monomachine TUNE it moves one semitone a click; on sample TUNE it moves 12.00; on a send page 2 it jumps to the next of 0, default, 127.
- **Push + turn (sample STRT / LEN / LOOP)**: whole steps; a plain turn is the fine 0.00..120.00 control.
- **Hold a trig + turn (grid recording on)**: p-lock, as stock. It also works for the ENV2 knobs, and on TRIG page 2 for SLD / SLEN.
- **TRIG page 2: E = SLD, F = SLEN**: hold a trig, turn E right for a parameter slide on that trig, F for the slide's length (1/8 .. 64 steps). Pushing E or F on held steps clears their slides.
- **LFO destination lists**: 13 controls stock hides are offered (PTIM, PORT, amp DEL / MODE / RSET and several FM TONE ones), and each LFO can modulate the other two LFOs' controls.
- **[AMP] repeatedly**: AMP 1/2 (stock, titled ENV1/AMP) -> 2/2 (ENV2) -> 1/2. NO or any page key closes 2/2.
- **UP / DOWN on any page with pages** (stock's rule, now on AMP and FX too): DOWN the next page, UP the previous one, stopping at the first and last (the page key wraps, the arrows do not); held, they keep stepping. They page with a trig held, with KEYBOARD on and in grid recording; FUNC + UP / DOWN stays stock's (no step). AMP: 1/2 <-> 2/2; FX: 1/3 -> 2/3 -> 3/3 (each insert on its page 1, as [FX] opens it). The pages a FUNC tap reaches are a set of their own, never mixed with the others: on an insert's page 2 (FUZZ, TAPE) the arrows go to the other slot's page 2 if its insert has one, else nowhere; on a send page 2 (Delay XDLY, Reverb FDN8 / LONG) to the other send page's page 2 if its TYPE has one, else nowhere. On FUNC + FX's send pages (page 1) they are stock's: Delay -> Reverb -> Chorus. An open list, routes or DEST popup keeps the arrows for itself.
- **Hold [TRIG] one second**: the oscilloscope (titled WAVEFORM) opens over the TRIG page and stays up after [TRIG] is let go; any page key ([TRIG] too), TRK or NO closes it. A short press of [TRIG] is stock's (TRIG page, its two pages on taps). FUNC + [TRIG] is still stock's QUANTIZE.
- **Hold VOICE one second**: every track's machine, voice mode (PAR = PARA ON, UNI = UNISON, MON = one fixed voice, PLY) and VOICES (DYN or the fixed count), the DYN pool in the title. Let go: the screen as before (no VOICE menu). A short press is stock's (the VOICE menu on the release). FUNC + VOICE is still the RECORDER.
- **Scope: any encoder but G**: time across the screen, 2 / 4 / 8 / 17 / 33 / 67 ms. **G** is the vertical zoom x1/8 .. x16 or AUTO (the default). Both are shared by all tracks and kept after power-off.

## Matrix (routes popup)

- **Push a sound knob (no FUNC) and let go**: opens the matrix routes popup for that knob, at the release, if nothing else happened while it was held (no key, no turn of another knob, no trig or other key already held). The pushed knob may wobble: under 4 counts of its own turn while held are ignored (the value does not move) and the popup still opens; 4 counts or more are stock's push + turn. On SYN 1-3 of every machine (ours and FM TONE's included, since 2026-11-20), FLTR 1-2, AMP, FX 1/3, ENV2 (A-D, H) and TRIG 2/2 PTIM / PORT. Stock's own push gestures stay stock's: the value shown in the label on the press, push + NO resets the knob, push + turn takes big steps, a trig held + push clears that trig's lock, LIVE REC's NO + push. Rows LFO1, LFO2, LFO3, ENV1, ENV2 show the depth routed to that knob and a moving bar. Stock's MOD SETUP rows VEL/V, MW/T, PB/T, AT/T, BC/T, KEY/V (/V: read per voice, /T: per track) edit stock's own four entries a source, with the same keys (the depth in stock's MOD SETUP number; NOT IN SETUP where stock's list does not offer the knob). Rows with no route show their source's level now as a dotted line.
- **In the popup: turn the knob**: sets the lit row's depth live. **Push + turn, or UP / DOWN**: moves the lit row. **FUNC + DOWN / FUNC + UP**: jumps the lit row to the next section / back to the first row of its section (or the previous one): the LFO rows, the ENV rows, the MOD SETUP rows, as the rows are shown (used rows first); it stops at the top and bottom. A row left at 0 disappears when the popup closes. Up to 16 LFO routes a track, 4 per envelope; the lit row shows the count (or FULL).
- **In the popup: YES**: unmutes the lit row's route (on an empty row it adds one). **NO** (short): mutes it. **NO held 0.6 s**: deletes the lit row's route. **FUNC + NO**: deletes every route into this knob, ours and stock's MOD SETUP entries. A muted MOD SETUP entry stays in the sound (stock firmware plays it) and is silent here. The popup closes (kept) on the same knob pushed, another knob turned, a leaving key, a track change, or 6 s untouched.
- **FUNC + push**: stock's (the value shown; on a MIDI track it switches CHAN / BANK / PROG / CC VAL on or off; on an LFO page's DEST it opens stock's DEST list). **FUNC + long push (0.6 s) on a knob**: resets that knob to its default (popup closed; never an LFO's DEST). A FUNC + push begun while the popup is up is ignored.
- **LOCKS strip (popup bottom)**: this knob's p-locks, per step, for the pattern page playing.
- **The popup is refused** (the push stays stock's) while a trig is held, a stock question is up, one of our pages, lists or popups is up, on a MIDI track, on the LFO pages and TRIG 1/2, on our own machines' pages, or on a knob that is not a sound parameter.
- **LFO page, push D (DEST)**: our DEST popup, on the press (ENV2's page: push G). **In it: FUNC + DOWN / FUNC + UP**: jumps the lit row to the next section / back to the first row of its section (or the previous one): the LFO's own routes on top, then each of stock's destination categories; it stops at the top and bottom. Plain UP / DOWN: one row.
- **ENV1 = the stock AMP envelope, routable**: nothing to switch on; it is routed from the popup.
- **ENV2 (AMP page 2/2)**: a copy of the amp envelope, routable only. All six ENV2 knobs are p-lockable: grid recording, or hold a trig while turning on AMP 2/2. (HOLD has no knob on the page; MODE ADSR / AHD is on F.)

## List popups & MACHINE SEL

- **Turn a list knob (engine, sub-engine / model, FLT2)**: a five-row list opens round the value. The first turn only opens the popup and moves nothing. It closes by itself 1.5 s after the last turn.
- **16 trig keys (list open)**: the list stays open and the track plays, so you can preview the sound.
- **UP / DOWN (list open)**: one entry. **LEFT / RIGHT**: one page (5 rows). Any other key or encoder closes it.
- **FUNC + turn G on the FLTR page**: opens the filter list (FUNC + G). YES, pushing G or letting go of FUNC keeps the pick; NO or another key / knob leaves the type as it was. A trig key leaves it open (with FUNC held it is stock's FUNC + trig).
- **MACHINE SEL (stock view, two columns)**: LEFT / RIGHT switch between machines and filter engines.
- **FUNC + SYN (SRC) while MACHINE SEL is up**: does the same page switch as RIGHT / LEFT instead of closing it (unverified; read from code only).
- **LIVE SELECT** (ON by default): the machine or filter under the cursor is put on the track about 0.15 s after the cursor rests, no YES needed. **YES** keeps and closes. **NO** puts back the machine, the filter and the whole sound as they were when MACHINE SEL opened. Same on the FUNC + G filter list.
- **AMP ON/OFF on the drum machines**: on MACHINEDRUM, SOPHIE, DRUM and PLAITS' BD / SD / HH, H on the AMP page (VOL's place) is AMP ON/OFF. OFF (the default, every old sound too): the drum bypasses the AMP envelope and VOL, gain exactly 1.0: it decays by itself, trig LEN does not cut it. ON: the AMP page and VOL as stock. Turn H right for ON, left for OFF, or push H. Saved with the sound.

## Inserts / FX

- **[FX] (track FX key)**: FX 1/3 (stock) -> 2/3 (INSERT 1) -> 3/3 (INSERT 2) -> 1/3. NO or a page key closes an insert page. DOWN / UP step the same pages, stopping at 1/3 and 3/3.
- **FUNC + [FX]**: stock's three send pages (Delay, Reverb, Chorus), never an insert page.
- **Insert page: A = M.SEL, B..G = the insert's knobs, H = MIX**. M.SEL is a 0..127 knob split in bands, listed A-Z: OFF CHOR DIST FDN8 FOLD FUZZ GATR HARM JUNO RING SUB TAPE WIDE XDLY. Inserts are saved with the project and cannot be p-locked or LFO'd.
- **DIST, FOLD, HARM, FUZZ, TAPE: knob F = PGAIN, knob G = AUTO LEVEL on / off**: ON keeps the level steady as drive rises; OFF = as before. A turn right is ON, left is OFF.
- **Insert page 2 (FUZZ GATE, TAPE AGE + HISS)**: a FUNC tap (press and release, nothing else) on the insert's page switches page 1 <-> 2 (csrc/inserts/ins.c, since 2026-11-13); [FX] goes on to the next FX page (on its page 1). UP / DOWN on a page 2 go to the other slot's page 2 when it has one.
- **Insert slot order**: slot 1 runs before slot 2. A CHOR / WIDE / FDN8 / XDLY in slot 1 over a voice insert in slot 2 moves slot 2 onto the track bus (the chord is processed as a whole).
- **FDN8 and XDLY inserts**: a slot shows FULL under M.SEL when the DSP has no free instance (8 FDN8, 4 XDLY); it passes the sound through.
- **FUNC tap (press and release, nothing else) on the send Delay page (TYPE XDLY) or send Reverb page (TYPE FDN8 or LONG)**: switches page 1 <-> page 2. Page 1 shows a 1/2 tag. Delay 2: SLEW KNEE WDTH INPT; Reverb 2: DIFF WDTH FREZ.
- **Send Chorus page, E = TYPE**: STOCK or JUNO. With JUNO, DPTH is the MIX and SPD is the MODE (I / II / I+II). It is saved with the kit at stock's next save.

## Sample machines & FLEX

- **FUNC + VOICE**: opens the RECORDER over any page (VOICE alone is still the voice menu). FUNC + VOICE again, or NO, closes it. Page keys close it; a running recording continues.
- **RECORDER: YES**: record now (or stop). **A** SRC, **D** THRES, **F** R.LEN, **G** R.STRT, **H** ARM. R.LEN counts steps at the pattern's scale.
- **After a take, TRIM**: E = START, H = END. **FUNC + YES (held)** plays START..END. YES keeps, **FUNC + NO** drops the take.
- **FILE NAME**: UP / DOWN character, LEFT / RIGHT cursor, **FUNC + NO** deletes, **FUNC + YES** inserts a space, **FUNC + PLAY** clears the name. **While FUNC is held** the name shows a character grid: FUNC + arrows move through it, letting go of FUNC puts the character at the cursor.
- **ASSIGN SAMPLE TO TRACK**: press a [TRIG] key to give that track the take (a non-sample track becomes ONESHOT first).
- **Sample list (turn SAMP)**: it stays open; UP / DOWN or SAMP move, [TRIG] previews. YES or pushing SAMP keeps, NO restores, **FUNC + YES** opens the browser.
- **Browser (PROJECT RAM / +DRIVE)**: **YES** ticks a sample, **RIGHT** opens SAMPLE ACTION (LOAD TO PROJECT, LOAD TO TRK, DELETE, SELECT ALL; MOVE HERE for ticked samples), **NO** goes up a level, **NO held** goes to the top, **FUNC + arrow** jumps a page, a pushed knob pages too. **FUNC + YES** previews the sample under the cursor (on +DRIVE it may toggle an auto preview instead; unverified which).
- **ERASE MOD DATA** (removes everything the mod stored, before going back to stock): sample list, FUNC + YES, cursor on +DRIVE, RIGHT, then YES, YES, YES (the questions are ERASE ALL..., then ARE YOU SURE). NO or LEFT cancels. Restart afterwards.
- **SLICE / GRID page, YES**: the slice menu (CREATE SLICE GRID with SLICES and TR.DET; EDIT SLICE POINTS; ALLOCATE SLICE for linear / random locks). **In the slice editor**: **FUNC + RIGHT** splits, **FUNC + LEFT** removes, **FUNC + YES** previews while held, **FUNC + G** moves the whole slice.
- **KEYBOARD on a SLICE / GRID track (SLCE = NOTE)**: trig key k plays slice k; KEYBOARD + UP / DOWN moves the keys on by 16 slices.
- **FLEX (live buffer machine, MACHINE SEL after SLICE), FUNC + VOICE**: opens FLEX REC; LEFT / RIGHT switch REC TRIGS <-> REC SETUP.
- **FLEX REC TRIGS: [TRIG]**: a one-shot recorder trig (records once, then spent). **FUNC + [TRIG]**: a trig that records every pass. **YES YES** (two within 0.4 s) re-arms spent one-shots (read from code; unverified for FLEX).
- **FLEX REC SETUP: YES**: record now, or at the next Q.REC boundary when set (NO cancels the wait). Settings: SRC, CHAN, BUF (**C**), R.LEN, ARM, Q.REC, **G** GAIN (-24..+38 dB), **H** MUTE (on SRC = a track: takes it out of the mix and its FX sends while FLEX still records it; not stock mute, its LED does not change). Settings are kept per FLEX track.
- **FLEX REC SETUP: FUNC + NO**: CLEAR BUF n? (YES empties the buffer, NO or any key cancels; refused while it records).
- **FLEX: FUNC + YES**: saves the take as a sample (TRIM, FILE NAME, ASSIGN).

## Sequencer / arp / trigs

- **Hold PTN + YES**: DIRECT JUMP ON, a cued pattern (PTN + TRIG) then starts at once from the current position. **Hold PTN + NO**: OFF. Default off, kept across power-off.
- **TB-303 SLIDE**: only acts while the previous note is still held (legato).
- **DRONE glide**: set the track's voice mode to REUSE to get glide between separate trigs.
- **DRONE HOLD (page 2, knob G; unverified)**: HOLD ON keeps the note after key-up; the same key again lets it go; another key plays and releases the others. Since 2026-11-19 notes on other tracks never take a held DRONE note's voice; if every voice they could use is held by DRONE HOLD, such a note plays no voice (as on a muted track).
- **Arp MODE past CYCL: SHUF and RAND (unverified)**: a separate mod, confirmed on a unit in September, but not confirmed to be in this build.

## SYSTEM settings

- **SETTINGS > PERSONALIZE > LIVE SELECT** (last row; ON by default). Your note says SYSTEM row; the code puts it in PERSONALIZE (unverified which is right on the unit).
- **SETTINGS > PERSONALIZE > VOICE BUDGET** (after LIVE SELECT, ON by default): at note-on, if the new voices do not fit the DSP, the oldest held voice is stolen. Engine lists show "N VOICES" or "DSP FULL" beside choices that do not fit.
- **SETTINGS > SYSTEM > USB CONFIG > REMOTE CONTROL** (4th item; YES or a turn toggles; ON by default): off blocks the computer's remote-control channel. FACTORY RESET turns it OFF.
- **DIRECT JUMP** is a setting of the unit, not of a project; see PTN + YES / NO above.

## Engines notes

- **MONOMACHINE**: one machine, engine chosen on page 1 H (SID, WAVE, DDRW, DENS, VO-6); page 2 H is the engine's TUNE. A new engine starts as in MACHINE SEL.
- **MACHINEDRUM (PERC)**: page 2 H = TYPE (the Machinedrum machines, list popup). **SOPHIE / PLAITS**: G = MODL (list popup). PLAITS TUNE is whole semitones, FINE cents.
- **ANALOG 2 page 3**: GLID (glide time, 1 ms to 5 min) and GLTY (OFF / RATE / TIME). Glides only for notes played legato.
- **JUNO** (engine and insert): MODE I / II / I+II. **TB-303**: ACC and SLID are per-step: p-lock them on the steps that accent or slide.
- **Machine tags**: ANALOG 2's FLT2, Machinedrum TYPE, PLAITS / SOPHIE MODL and the Monomachine ENGN lists can show a voice-count tag (VOICE BUDGET).

## After flashing

- **Power the unit off and on once** after flashing a new build. A machine whose tables are new in a build can stay silent on the first boot after the flash (seen once, cause not confirmed on the unit).

## Sources and open points

Used: FIRMWARE.md (v0.4x to v0.52 test lists), docs/matrix.md, live-select.md, popups.md, inserts.md, fxpage.md, jump.md, scope.md, slides.md, sampler.md, flex-design.md, mnm.md, tb303.md, sophie.md, plaits.md, load-budget.md, remote-ui.md, erase-mod-data.md, meter.md, modulation-more.md, arp-hidden-modes.md, and a few comments in csrc/ (msel.c, ins.c, hold.c, rec.c).
Taken as given by you, not in those docs: the matrix popup text, ENV1 / ENV2 notes, list popup keys, inserts' PGAIN / AUTO LEVEL / page 2, TB-303 SLIDE, DRONE REUSE glide, power cycle after flashing.
Seen but not confirmed: FLEX REC SETUP's other knob letters (not listed); DRONE HOLD's location; where LIVE SELECT lives (PERSONALIZE vs SYSTEM); whether FUNC + YES in +DRIVE holds or toggles preview; whether arp SHUF / RAND is in this build; the FUNC + SYN switch in MACHINE SEL; the sample list / browser keys come from older release notes (v0.25 to v0.40) and may have changed since.
