# SIMD voice pairs: two voices of one track rendered at once (2026-11-12)

The User: "the most useful use case is clearly the voices of one track". A track's voices play the same
machine, so two of them can be one SIMD pair: PEx renders one, PEy the other (docs/dsp-simd.md on the
`simd` branch: `Prog.simd`). Build option `DN2_PAIRS=TB303,...` names the pairable machines; without it,
nothing of this is emitted and PERC's text is the one before (measured: perc, perc2a and perc2b identical).

## Render ahead (dnfw.perc.pairs)

Upstream's loop runs the voices one by one (guard, host, stream advance, render, resample). When voice A
reaches its render and its machine is pairable, `pairs.render`:

1. looks for its partner B later in this block's ORDER (`_find`);
2. moves B's stream on and renders B (step A: the same scalar render, then A's; step B: one SIMD pair);
3. marks B's slot word 255 with this block's mark (`STAMP + 1`).

At B's own turn, its advance skips the move and the render (done), and the rest of its block runs as
always. B's render is the one its own turn would have run, only earlier, so every voice's output and state
are the same with pairs on and off.

**The partner** is a slot that:

- plays the same machine;
- has no trig (the frame's bit, the slot's waiting trig), no dirty words, no machine change;
- has the frame words and note cell it had at its last render: the snapshot, 16 words a slot. So its host
  would change nothing the render reads.
- has a stream that asks for a block (pos ≥ START);
- is not resting (quiet, rest counter);
- comes later in ORDER and has not already been rendered ahead;
- fits in the time left on the DSP: now + 1.5 × (its last cost + A's) ≤ LIMIT.

So held notes (a chord, a pad) pair, and a voice's note block or knob change renders alone.

## The overload exception

At B's turn the guard admits B even if the frame's time is short (`guard.around(admit=)`), and the
Monomachine budget does not leave it out (`pairs.unskip`). Its render is done and paid for, and leaving it
out would show a moved-on state with a silent block.

This is the one place where pairs on can differ from pairs off: under overload, pairs off might have
skipped B in a block where pairs on plays it. Pairing happens only when the time check (above) says both
fit, so B is admitted only when its cost was already accounted for at A's turn.

## Memory

- L1 F4 (the arbiter juno-engine): 0x2E2500.., our words (STAMP, the search's words) and the snapshots
  (16 × 16 words).
- Slot word 255 of each voice slot: the "rendered ahead" mark.

## The guard's costs

The partner's move and render are timed (EMUCLK around them). They are moved from the voice that ran them
onto the partner (`SHIFT`, applied as the guard stores each voice's measured cost), so each slot's COST word
is its own voice's (opt-host's review). The time check uses each voice's expected cost as the guard reckons
it: max(1.5 × last cost, FLOOR).

## Measured (step A, base e0868f63, DN2_PAIRS=TB303, 2026-11-12)

- **Pairs off:** perc, perc2a and perc2b emitted text identical; test_dsp_claims and test_dsp_regions pass.
- **opt-host's perc_host_identity.py (59 scenarios, model):** 0 differ off and on.
- **PERC code:** 154,100 → 155,702 B (+1,602) with the option; +0 without.
- **SHARC runner, DSP built with pairs on, model run without** (so bit-exact = pairs on equals pairs off):
  - two held TB303 voices: 1 voice rendered ahead per block;
  - a held 4-note chord: 2 per block;
  - a retrigger and a knob turn: those blocks render alone;
  - every voice-block's output and state bit-exact.
- **Worst case (16 TB303 voices, a note on every block: nothing pairs; a moving clock, insdl-style):**
  - mean guard cost per voice, steady blocks: 23,663 / 23,017 / 22,532 with pairs, against 23,016 / 22,374 /
    21,892 without;
  - the search costs **~+640 cycles per voice-block (~+3%)** when nothing pairs.
  - The model mismatches there (777 words) are guard skips under that load, the same in both builds.
- **16 held voices:** 5 voices rendered ahead per block (the time check limits it). Step A has no gain yet, so
  ~+330 cycles per voice.
- **Overload case (two held voices; the guard's LIMIT at 1 for the second voice's admission from block 4):**
  - pairs off: the second voice skipped 12 times;
  - pairs on: it is admitted in every block it paired (2 skips, in the two blocks where no pair formed);
  - the cost words stay per voice: 27,679 and 27,158 against 27,043 without pairs.
- **Nothing of this has run on the unit.** It goes on the unit check list.

## Resume here (paused 2026-11-12: the User is out of credit; step B waits for a go)

1. **Step B, TB303's SIMD pair render.** It needs opt-synths' TB303 commits on main (1288514b vsched, 36ca5929
   KTAB, 7381f0c2 DN2_TB303_2X, 5919bf5c the slide fix). Work:
   - KTAB doubled (each constant twice: in SIMD PEy reads the next word);
   - the render emitted in SIMD form with the slot offsets doubled (the pair area: both voices' 106 render
     words interleaved, in F4's free tail after 0x2E2980 or F2's tail, the arbiter's);
   - a SIMD region per sample (the sample loop's counter cannot run in SIMD);
   - every per-sample branch predicated (~164 diverging a block: BLEP edges, DC, slew).
   Emit only the SIMD form if PERC room is short (a lone voice then runs it with an empty lane).
   It goes where `render()`'s two passes are (RENDER2). Send the arbiter its bytes before committing.
2. **Proof for B:** model bit-identical (a pair's two outputs against two scalar runs), the runner as above,
   and the worst and steady numbers again (main: VOICE BUDGET and the guard right for the worst case).
3. **Scratch tools** (the `pairs` worktree, not committed): `scripts/m5_pairs_scratch.py` (the runner cases:
   pairs, PAIRS_WORST, PAIRS_OVERLOAD) and `scripts/pairs_emit_scratch.py` (off-identity). Run them through runq,
   kind runner; build with DN2_PAIRS, run the runner without it.
4. Study and estimates: shared notes simd-study.md (section 6), simd-pairs-table.txt.
