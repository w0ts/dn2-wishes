# The mixer meters and the CLIP label (2026-11-20)

The User: "if we do the alert, we don't do the overview page"; chose (scratch/mixer-overview.md): the CLIP label and
meters with clip marks on stock's MIXER pages; "remove the dashes on the right of the fader and use this space for
the meter"; levels and clip marks, 3 dB a row, 10 a second, a peak tick, a latch; the label 3 s after the last clip,
a latch until its page has been on the screen 2 s; only outputs in use; and the analog outputs' overs as a clean clip.

## What it shows

- **MIXER (FUNC + [MOD]), Internal Mixer 2/5 and 3/5:** each track's fader keeps its left tick scale; the right one
  is the track's meter (3 px, the fader's 17 rows, 3 dB a row). The top row lights only at full scale of the track's
  Overbridge / USB channel. A one-row tick holds the highest level of the last 3 s. Two rows above the meter, the
  latch: lit once that output really clipped while it was in use. Since 2026-11-20 (the User: "a '!' on the left of
  the channel ... when it is clipping"; "move the ! a few pixels to the left": 1 px, the User's pick) the latch is a
  "!" one column left of the fader's left tick column, that column blank while it shows (stock's ticks there
  otherwise); the mark above the meter is gone. Beside the returns, IN LR and OUT L it sits 3 columns left of the
  fader (2 of OUT L's meter).
- **FX Mixer 4/5:** a meter beside each send return's fader (DEL, REV, CHR; their Overbridge / USB channels), a "!"
  two columns left of each fader; the empty cell at the top right shows OUT L and R: the main outputs in use, each in
  its own scale, the hotter (the analog outputs; with Overbridge, or USB audio sending the main, Overbridge / USB main
  as its own TDM words carry it), one "!" left of L.
  2026-11-20, the User on the unit: "the main OUT level is zero when Overbridge is connected". Stock keeps the internal
  sound off the analog main (frame word +0xa7e, from INT TO MAIN and the USB state: measured in the runner, the codec's
  mix 0x268438 empty while Overbridge's main carries the mix), so the analog peaks were truly zero; the DSP's main clip
  bit came from the same mix. Overbridge / USB main is now read from TX slots 0, 1 as sent: first by the ColdFire
  (mix_ob_main, every audio period: 1.56 % of the CPU in Overbridge mode on the unit), since the same evening by the DSP
  (sampler.program ob_peaks, in wr_pvmix after the preview's add: each side's largest |word| >> 8; its clip bit 19 at
  0x7fffff, its peaks the levels packet's units 22, 23).
- **External Mixer 5/5:** a meter beside IN LR (the input at its converter's full scale), its "!" left of the fader.
- **The title bar:** CLIP (beside DSP, CPU, RAM; csrc/meter/meter.c) for 3 s after any clip of an output in use. With
  DSP, CPU and RAM lit too, its blink is drawn by full redraws (the labels then start left of the alone-blink's
  columns).

Outputs in use: the analog outputs, the input and the recorder (while it records) always; Overbridge's main in
Overbridge mode (USB CONFIG); in USB audio mode the channels of its USB OUT pair. A track's or a return's own
Overbridge channel lights nothing (2026-11-20, the User: "only when it matters", after a track at LEVEL 100 / AMP VOL
100 lit CLIP from its own channel, which runs ~9 dB hotter than its share of the main): the unit sends all of them
whenever Overbridge is connected (its packet builder copies every channel each frame, no channel mask seen), so it
cannot tell which ones the plugin streams. Their meters still show their levels.

## A voice's own clips (2026-11-20, clip-inner)

The User, after DRONE on track 5 sounded distorted with no alert: "NO DIGITAL CLIPPING. how clear can i make that?",
"a synth with no effect on should not digitally clip and if it does, i want the alert". So a stage inside a voice that
clips or limits lights CLIP and that track's "!" too, whatever outputs are in use:

| stage | lights when | where |
|---|---|---|
| PLAITS' Clip16 (VA FM ADD BD SD HH, and after the Limiter) | a word past +-1 | engines/plaits/plaits.py `_post` |
| PLAITS' Limiter (SWRM NOIS PART STRG MDAL) | its peak past 1.122 (1 dB) | the same |
| DRUM's drive (KICK SNARE TOM HATS; PLAITS BD's overdrive) | the soft clip's input past +-3, where the curve is flat | plaits_drumkit.py `soft`, drum/dmath.py `soft_antider` |
| DRUM HATS' output hold (0.99) | a word past it | drum/hats.py |
| the Machinedrum's and Monomachine's 56300 limiter on their output (every MD machine, SID, DPRO, VO-6, FM+) | a stream word at TOP or -1.0 exactly, where the voice reads it | md/voice.py `_resample` |
| PERC's soft clip (rv_dsp.h sat) | its input past +-3, where it is flat | perc/machines.py `_sat_body` |
| the A2 filter models (ANALOG2's, JUNO's ladder, the filter machines 7..11) | the Pade tanh's input past +-3, the SVF state knees squashing by 1 dB | engines/analog2/filters/models.py |
| the inserts (per track): the input hold (+-4), FUZZ's and DIST's clamp at +-1, TAPE's input hold and its curve's flat (+-3) | a word past the hold | inserts/program.py |
| XDLY's loop knee (the send, or a track's bus insert) | squashing by 1 dB (or held at 1.0) | xdly/program.py `knee` |

How: a stage inside a voice stores a nonzero word in `perc.guard.CLIP_HIT` (a compare in the branch the stage already
takes over its threshold, or a compare before a branch-free clamp); `out_guard`'s `clip_note` turns it into the slot's
bit in `CLIPMASK`. A stage outside the voices (the A2 filter machines' pass, the inserts, the bus inserts, the send
delay) hands it on at once with `clip_note_track`: its track's bit in `CLIPTRK`, or bit 16 + r for send return r.
tdm_tx sends both in a clip packet (`CLIP_MAGIC` 0x5A36: unit 1 the slots, unit 2 the tracks, unit 3 the returns) in
place of an idle packet, never two in a row, and clears them; link.c hands it to mixer.c `mix_inner_in`, which stamps
each slot's track (stock's voice owner table 0x80005308, from which the DSP's ROUTE is made; bit 23 when no track is
known: the label only), each track and each return. Checks: test/test_clipinner.py (each stage's threshold, the packet,
the masks), test_mixmeter (mix_inner_in), the runner's `clipinner` step (DPRO-DENS at all 127 lights it on the DSP's
own code; the User's track 5 DRONE, DDRW and DRONE at their starts and silence do not), the emulator's `mixmeter` step (in Overbridge mode a clip packet
lights the track's "!" and the label).

**No limiter, levels instead (2026-11-21).** The User: "just make it quieter! not a limiter... a synth in its normal
settings must not clip. and if it happens the !clip should display"; "Yes, all of them". DRONE's and ANALOG 2's soft
knees (Optimist's protection for its Q15 output) are gone; DPRO-DDRW's MIX gain is 1.5 on the DN2 (the Monomachine's 4
put two full waves at 2.64 into its limiter: it clipped at its defaults); TB-303, ANALOG 2, JUNO and DRONE come down by
perc.program `HEADROOM_DB`, so at the worst knob setting found, one note, track LEVEL and AMP VOL at 127, Overbridge's
main stays 1 dB under full scale (docs/levels.md). What can still clip inside a voice lights CLIP as above.

Not flagged, for the DSP upload's 1 MiB (a flag costs three instructions a site; the ~120 limiter sites inside the
Machinedrum's machines alone took 3.3 KB of the 1.5 KB left): the 56300 limiter inside a machine (where it shapes an
oscillator or an envelope: only the output's is), the A2 filters' +-32 output hold (30 dB past anything a voice
reaches). Not flagged, as tone: SOPHIE's output x / (1 + |x|) and the drives' smooth curves (DRUM below +-3, ANALOG2 DRV, the ladders'
tanh below +-3, FOLD, HARM): tone, never flat. PERC's out_guard +-8 (a voice there clips the main first).

## Where clipping is real (scratch/mixer-overview.md has the whole path)

Everything inside the DSP is float; only the fixed-point stages clip:

| stage | full scale | how it clips |
|---|---|---|
| analog outputs (MAIN OUT, headphones) | main mix 1.0 | stock: FIX BY 31 with ALUSAT off, then an integer negate: an over reached the DAC as ~0, -1.0 as the wrong sign (step dacover measures it on stock). Now held to the largest float under 1.0 first (wr_pvmix's dac_guard): a clean clip |
| Overbridge / USB (TDM slots, SPI records) | main mix 0.70; a track's or return's block x 1 / 0.7 at 1.0 | the output stage turns ALUSAT on: a clean clip |
| the recorder | its clamp | a clean clip |
| the input | its converter | analog |

Measured in the runner (step levels, MEASURE): a voice block at 0.01 reaches the main bus at 0.141 (x 14.125), the
main mix after the master chain (the runner's frame) at 0.159, Overbridge's main at 0.227 (x 1 / 0.7) and the
track's own Overbridge channel at 0.661 (x 3.2768 x 1 / 0.7): a track's channel is about 9 dB hotter than its share of
Overbridge's main there, so it clips first.

## How

- **DSP** (dnfw.sampler.program `levels`, in wr_smp before the link's packet; `dac_guard` in wr_pvmix): each block,
  from the output stage's last blocks, the peak |x| of every stage in its own scale, and the clip bits; the bits to
  the SPI reply's word 6 (bytes 0x18..0x1b: neither stock nor ours wrote them) as `0xC5000000 | this block's | the last
  block's`; the peaks into a levels packet (`LV_MAGIC` 0x5A35 in TDM slots 14..15, in place of every 4th idle packet)
  only while the ColdFire asks (`LV_WANT` at the pool's READY page + 0x120). Cost: about 3,300 instructions a block
  for the peaks (23 blocks of 64 words, two instructions a word in a hardware loop), about 450 for the hold (DSP
  instructions, estimated from the code; the runner's cost step to measure).
- **ColdFire** (csrc/meter/mixer.c; link.c reads the reply word every period and the levels packets; page.c draws):
  the meters drawn with stock's full draws of those pages and updated alone 10 times a second (only the meters that
  changed, their 8-pixel groups sent); never over a popup of ours, a stock question, an overview or the big meter.
  (Stock asks a full redraw of the MIXER at every UI pass, so the updates alone hardly run there: the meters change with
  the full draws, held to 10 a second since 2026-11-20, "The CPU" below.)
- **Checks:** runner steps `dacover` (stock's dropout, the build's clean clip, every word under full scale stock's)
  and `levels` (each clip bit exactly when the output stage saturated that channel's words; the model's peaks, bits,
  packets; sources A and B); test/test_mixmeter.py (the C compiled for the host; the DSP's model); the emulator step
  `mixmeter` (stock's pixels kept outside the meters, the model's meters inside, updates alone equal to full redraws,
  the latches' and the label's timing, the outputs in use).

## The CPU (2026-11-20, the User: "cpu is 94%", "we need to optimise mixer pages")

Measured on the unit (v0.62.6, Overbridge on, nothing playing, PC profiler 15 s each): meter C 68.0 % on a SYN page,
74.9 % on Internal Mixer 2/5. The UI task 4.7 % -> 9.3 % of the CPU: stock's code +3.85 % (stock redraws its five MIXER
pages in full 30 times a second, also in stock 1.12; elsewhere only when something changes), ours +0.8 % (every one of
those draws redrew all the meters pixel by pixel). Fixes:
- the meters drawn a column's bytes at a time (put_col): ~34,000 -> ~5,200 instructions a draw, the same pixels;
- stock's MIXER redraws held to 10 a second (the User: "10 per sec is fine even... we want to see what the levels are
  about and the !"): page.c wr_poll's answer through mixer.c mix_dirty; a key or knob item (rec.c smp_input_seq) is
  drawn at once; the meters and the "!" change at that rate;
- Overbridge main's peaks and clip from the DSP (above): the ColdFire reads no TDM words for them.
Gate step `mixcpu` (scripts/emu_mixcpu.py --check): in the emulator (no audio interrupt), on 2/5..5/5 with every meter
moving, full draws at 9..10.6 a second, a knob turned right after a draw drawn within 5 panel ticks, a full draw's
meters under 6,000 instructions, the meters' own cost (on against off) under 0.6 % of the CPU, mix_poll under 120,000
instructions a second.

Not verified on hardware: the dropout as heard and its fix; the meters' movement with real audio (the emulator has no
DSP); the panel UART's load with all meters moving (an update sends at most the changed meters' groups).

## The OUTPUTS overview (2026-11-21, FUNC + [MOD] held a second)

The User first asked for "a MIXER OVERVIEW: all 16 channels at once ... a LONG PRESS of FUNC + MOD". The same day it
became the OUTPUTS overview: "I want to see what clips. So only what is not float, by definition", "Replacing what we
had there", "We have many more track with overbridge" (scratch/outputs-ovw-mock2.png, his OK). No per-track mark for a
track alone feeding an output ("too complicated"); a voice's own clips (clip-inner) are not on it.

- **Keys** (csrc/inserts/ovw.c `mix_item`, `play_mix`). Stock 1.12 opens the MIXER on FUNC + [MOD]'s **press**
  (Compressor 1/5; on the MIXER the next page), shows its value view while held and does nothing on the release
  (measured in the emulator). Ours holds the press back whenever FUNC is down at MOD's press: let go before a second,
  the tap is played where the panel's keys go in (FUNC held through it, pressed by us if the User had let it go
  first) and stock opens or steps its MIXER as before, a tap's length later; held a second, the overview; let go, the
  screen of before the press (over the MIXER: the MIXER page as it was). Another key or knob while held: no overview,
  no tap. Given up: stock's value view of a FUNC + [MOD] hold on the MIXER.
- **Picture** (ovw_draw.c `mix_view`, model `dnfw.overviews.outs_render`): the title bar (OUTPUTS; on the right CLIP
  and the names of the outputs whose mark is lit: "CLIP 5 R OUT", a pair's name once, "+" past 20 characters), 25 bars,
  rows 15..52 (38 px, 48 dB, ~1.26 dB a pixel, the top pixel full scale in that output's own scale):

  | bar | x | level (levels packet unit) | clip mark (DSP clip bit) | in use |
  |---|---|---|---|---|
  | tracks 1-16, their own Overbridge / USB channels | 1 + 4 t, 3 px | 0..15 (L and R together) | 0..15 | Overbridge mode; USB audio: the USB OUT pair's |
  | the send returns D R C | 67, 72, 77 | 16..18 | 16..18 | the same |
  | Overbridge / USB main L R | 84, 89 | 22, 23 (TX slots 0, 1 as sent) | 19 (one for both) | Overbridge mode; USB audio with the main as its pair |
  | the analog outputs L R (MAIN OUT, headphones) | 96, 101 | 19, 20 (dac_guard) | 20 (one for both) | always |
  | the input | 108 | 21 (L and R together) | 21 | always |
  | the recorder | 119 | 24 (its block peak, rpk) | 22 | while it records (rec_state 2) |

  An output in use: a floor row, its level from the bottom, its peak of the last 3 s a one-row tick; not in use: a
  dotted column. Its clip mark: a block at rows 10..13, lit when its bit came while that output was in use, until the
  overview has been up 2 s after the clip; the group's name (TRK FX OB OUT; USB in USB audio mode) white on black on
  row 59. Labels 1 8 16 D R C L R L R IN REC on row 54.
- **Its own stamps** (csrc/meter/mixer.c): `mix_clip_in` stamps `mix_ov_clip_at` with every bit whose output is in use
  for the overview (`mix_ov_live`: `mix_live`, and in Overbridge mode every track's and return's own channel); the
  CLIP label and the MIXER pages' "!" keep `mix_clip_at` and the 2026-11-20 rule above (no track's or return's own
  channel). Every pair (a track's L and R, the main's, the analog outputs', the input's) has one clip bit: a mark
  cannot say which side. The input's channels 40, 41 take the input's bit, the converter's test at IN_TOP, not a test
  of the Overbridge words (the same thing if the input reaches them at unity: inferred, not measured).
- **The recorder's level** (2026-11-21): the DSP's `levels` keeps the recorder's block peak (`rpk`) in `lpk24` while it
  records, held under LV_TOP (LV_CH 25; the link's last free scratch word); its clamp REC_TOP is its full scale.
- **Levels** (`ovw_poll_levels`): while it is up the DSP's levels are asked (`mix_want`) and taken 10 times a second
  (from zero at each opening); ovw.c redraws it at the same rate, alone over the glass (paint into FRONT, stock's
  panel_diff sends the changed groups). Over stock's MIXER, stock's full redraws are held to 10 a second as on the
  MIXER (`mix_dirty`). Nothing runs while it is closed but the stamps (one AND in `mix_clip_in`).
- **Gate:** `mixovw` (scripts/emu_mix_overview.py): taps open and step stock's MIXER; held, the overview as the model
  in Overbridge mode, USB audio mode with a track's pair and the recorder recording, and with neither; the marks from
  the overview's stamps alone (a MIXER stamp lights none); the screen of before on the release; another key; the cost
  with every bar moving; stock 1.12 as the negative control. test/test_mixmeter.py: the stamps' split, the bars in use,
  the recorder's peak in the DSP's model.

Not verified on hardware: the levels and marks with real audio (the emulator has no DSP; the runner's `levels` step
checks the DSP's packet with the recorder idle, its peak only in the model); Overbridge mode as the unit sets it.
