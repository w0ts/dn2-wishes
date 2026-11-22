# The oscilloscope: the selected track's waveform, on a long [TRIG]

2026-11-11. The User asked for "an Oscilocope page for each track, i would put it as AMP page 2",
"per track, after the inserts", and chose "A, follow overbridge. simple, logical."
The feasibility study is `scratch/scope/feasibility.md` (not in the repo).
2026-11-19 (the User): it opens on a long press of the [TRIG] parameter-page key, no longer from [AMP].

## Use

- **Hold [TRIG] one second**: the scope opens over stock's TRIG page, titled WAVEFORM, and stays up after [TRIG] is
  let go. The second is the page keys' own hold (the overviews' `LONG_TICKS`, `csrc/inserts/ovw.c`, 121 panel ticks;
  the User chose 1 s over 0.6 s, 2026-11-19, so stock's values show for most of a second first).
- **A short press of [TRIG] is stock's, unchanged**: every [TRIG] item goes on to stock as it comes. From another
  page stock's TRIG page comes on the press; on TRIG's page a tap steps 1/2 <-> 2/2 on its release; held, stock shows
  its values. Nothing is held back or played again: the short press reaches stock exactly when it did. Once the scope
  is up, stock takes [TRIG]'s release as a hold's (stock never steps on a hold's release), so the page under the scope
  is the one [TRIG] showed.
- **It stays up until another page is chosen**: any page key (TRIG, SYN, FLTR, AMP, FX, MOD), TRK, or NO.
  [AMP] goes to stock's AMP page on the press, as from any other page. [TRIG] (a tap) closes it and leaves stock's
  TRIG page as it was under it (that press and its release are not stock's: no step). NO is taken (not stock's).
  FUNC, YES, the arrows and the 16 trig keys leave it up.
- **No scope** when FUNC is held at the press (FUNC + [TRIG] is stock's QUANTIZE), a stock question is up, a knob is
  turned or another key pressed while [TRIG] is held (the hold then is stock's alone), the page under is not stock's
  TRIG page (view class `0x401E2180`; a menu, QUANTIZE), or a list, routes or DEST popup is up.
- **[AMP]** steps two pages again: AMP 1/2 (stock's, titled ENV1/AMP) -> 2/2 (ENV2) -> 1/2, two page dots
  (`csrc/waverider/amp_pages.h`, AMP_PAGES 2). FUNC + [AMP], and [AMP] from any other page, work as on stock.

The scope keeps everything else: AUTO first, the gain and the time kept after power-off, the encoders, the cost
(below). It draws no page dots (it is none of TRIG's pages); stock's title bar and left panel stay. While it is up,
`amp_sub` says `AMP_SCOPE`, so the routes popup (a plain push) and the DEST popup refuse it as they refuse every page of ours,
and TRIG page 2's SLD / SLEN (E, F) are covered (`sl_screen`): E and F are the scope's.

### What stock 1.12 does with [TRIG] (measured 2026-11-19)

In the 1.12 emulator, stock's own UI snapshot (`ui1200M`, no build), panel ticks at 121 a second, the glass saved at
each step (`scope-trig-scratch/tools/trigprobe.py`, not in the repo):

| gesture | stock 1.12 |
|---|---|
| [TRIG] from another page (SYN) | "Trig Parameters (1/2)" on the press |
| [TRIG] held | from the first key repeat (24 ticks, 0.2 s; seen at 0.25 s) the value view: VEL 100, LEN 1/16, LEV 100 in place of the labels, as long as it is held (0.6, 1, 2 s: the same); nothing else happens |
| let go after a hold | the labels back, no step |
| a tap on TRIG's page | steps on the release: "Retrig Parameters (2/2)", a tap again: 1/2 |
| FUNC + [TRIG] (tap or hold) | the QUANTIZE popup (TRACK n % on E, PATTERN % on H; view `0x401E3CB0` alone) |
| a trig held + [TRIG] | TRIG's page as without the trig; held, the same value view |
| [TRIG] held + a trig tapped | nothing changes on screen (the value view stays) |

So a long [TRIG] cuts stock's value view short after a second (the same as the overviews do on SYN, FLTR, AMP, FX and
MOD); no other stock gesture uses the hold. Our build adds nothing else on [TRIG].

**Where the short press reaches stock.** Stock's own: on the press from another page, on the release on TRIG's page.
Holding the press back until the release (as FX and AMP did until 2026-11-18) was not needed: the scope opens over
the page stock drew on the press, so nothing flickers and nothing is drawn twice. Before the scope opens stock draws
its page (on the press) and its value view (at 0.2 s), as it always does; that is stock's cost, not ours.

While the scope is up, any encoder but G sets the time across the screen: 2, 4, 8, 17, 33 or 67 ms
(100 points, every 1st..32nd sample at 48 kHz). The bottom-right label (H) shows the time.

**Vertical zoom** (2026-11-11, the User: "the oscilo should also have a vertical zoom"; 2026-11-17: "the
oscilloscope should have autozoom vertical (below X1)"): encoder G sets the gain, x1/8 x1/4 x1/2 x1 x2 x4 x8 x16 or
AUTO, its label at G. The gains below x1 are shifts (no divide per sample). AUTO takes the largest of the eight gains
that keeps every shown sample off the strip's top and bottom rows. Its label says AUTO whatever gain it took (2026-11-18,
the User: "just put 'auto', not A4 A8 etc"; until then "A/2", "Ax4"). At x1 a
full-scale sample reaches exactly the edge row, so a loud signal takes x1/2 and is never drawn on the edge rows in AUTO;
x1/2 is the lowest gain AUTO ever needs (x1/4 and x1/8 are there for G). A sample past the strip is drawn on its top or
bottom row (the manual gains).

AUTO holds still: it zooms out at once, on the first frame whose samples would reach an edge row, and zooms in only
after 8 frames in a row (about half a second) in which the shown samples fit a larger gain with an eighth of the strip
to spare, then to the largest gain all 8 frames allowed. The gain and the time are the page's own, the same for every
track (a way of looking, not part of a sound).

**AUTO first, and kept** (2026-11-18, the User: "auto should be default for oscilator and we should rfememebr the values
set for it"; one setting for every track, kept after power-off, AUTO until the User changes it). What the User can set
on the page, and what is kept:

| setting | how | first value | kept in the settings sector |
|---|---|---|---|
| gain | encoder G | AUTO | flags bits 4..7: 0 AUTO, 1..8 x1/8..x16 |
| time across the screen | any encoder but G | 8 ms | flags bits 8..10: 0 8 ms, 1..6 2..67 ms |

Both live in the mod's settings sector on the +Drive (`csrc/jump/jump.c`, sector 0x6FF000: the same 512 bytes, flags
word and check that DIRECT JUMP, REMOTE CONTROL, LIVE SELECT and the VOICE BUDGET use; no other write path). `jmp_poll`
reads the sector once the +Drive is up; the scope takes its two values then. A change is written once, a second after
the last turn (or when the page closes), never a write a detent. No sector, a bad one (its check fails) or a value out
of range reads AUTO and 8 ms. A FACTORY RESET keeps them, as it keeps DIRECT JUMP, LIVE SELECT and the VOICE BUDGET
(only REMOTE CONTROL is turned off by it, jump.c). Page changes and track changes do not touch them (TRK closes the scope,
as any page key does; a long [TRIG] after shows the same gain and time). Proven in the emulator (`emu_scope.py --proof`,
gate step `scope`): set, page out and in, track changed, a power-on (the snapshot afresh with the sector the first run
wrote), the values and G's label back; AUTO and 8 ms with no sector, a bad check, a value out of range; kept with
LIVE SELECT's bit by a FACTORY RESET.
The trace starts at the newest rising zero crossing, so a steady sound stands still; it redraws 15 times a second.

## What it shows

It shows the selected track exactly as Overbridge's track output carries it. The DSP's output stage (`0x1c244d`)
writes that every block, whether or not an Overbridge host is connected (measured on the unit, below).
Overbridge's own setting picks the signal:

- **A:** the routing's per-track block after every insert, voice and bus (FDN8, XDLY);
- **B:** the raw panned track.

The scope shows (L + R) / 2, the top 16 of the 24 bits, at full scale ±1. The send FX (delay, reverb, chorus) are not in a
track's output.

## Where the audio is read

`docs/link-research.md` §2 and §5.

| track | where | how |
|---|---|---|
| 1–6 | the TDM receive half `h` the audio ISR is on (`0x4E6E7100 + (h<<11)` on 1.12) | slots 2 + 2t (L) and 3 + 2t (R), frame f at `16 f`; justification as our link's packets (`smp_rx_sh`) |
| 7–16 | the SPI reply's records `0x800053C0 + 84 f` | channel pair t − 6 at byte 6 (t − 6): three shorts s0 s1 s2, L = s0 << 8 \| s1 >> 8, R = (s1 & 0xFF) << 16 \| s2 (24-bit) |

Notes:

- `scope_tap` (csrc/scope/scope.c) runs from `smp_tdm`, our hook in the audio ISR, once a block (1,500 a second),
  but only while the page is up. It writes every Dth sample into a 256-sample ring, and only reads Overbridge's buffers.
  Since 2026-11-18 it reads only in the 8 x D + 2 blocks before a frame is due (the blocks that fill the ring
  afresh; at 2..17 ms that is 10..66 of the 100 blocks between frames, at 33 and 67 ms every block).
  The ISR's code before the hook stays stock (`scripts/gate_overbridge.py`).
- A routing slot holds every track routed to it. Normally slot = track.
- The records are copied by stock at each frame's SPI call. That copy and the ISR are not synchronised, so a block can
  be read twice or missed (a glitch in the trace, not in the audio).

**Measured on the unit** (remoteui, 2026-11-11): the records carry track 8 (fields +6 / +9) live with notes,
with and without the Overbridge Engine app. The source flag byte `0x8000536A` read 1.
Tracks 1–6 in the TDM window were not yet read on the unit.

**Measured in the 1.12 emulator** (2026-11-11):
- the AMP key is code 4 (the firmware's name table, `scripts/emu_panel_map.py`);
- the AMP page's view class is `0x401E2320` (the screen's view list on [AMP], `0x401E1448` on [FX]);
- (2026-11-19) stock's TRIG page's is `0x401E2180` (1/2 and 2/2 alike), QUANTIZE's `0x401E3CB0`, SYN's `0x401D4DB0`.

## The scope's frames alone, never queued behind the panel UART (2026-11-17)

The User: "oscilloscope is creating cpu issues", and with the scope up "the ui [is] lagging behind like several
seconds".

**The panel UART is the bottleneck.** Every frame's changed 8-px groups go to the panel controller over UART8 at
156,250 baud, ten bits a byte: 15,625 bytes a second, through a 4,096-byte ring. When the ring is full, its writer
(`0x4000220c`) waits in a loop in the UI task, so keys queue behind it. Measured in the emulator
(`scripts/emu_scope.py`), with the UART drained at that rate (digikit's model sends instantly) and the scope fed
full-scale noise:
- each frame changes about 52 groups (520 bytes);
- at 25 frames a second that is 15,423 bytes a second, 99 % of the UART;
- the ring stayed full (mean 2,955 bytes queued, peak 4,096: the screen 0.2–0.26 s behind), and the UI task spent
  its time in that wait loop.

In the emulator the UI loop wakes on a 30 Hz tick, so a 40 ms period gives 15 frames a second: 64 % of the UART,
no backlog. The emulator also gives the UI about five times the CPU the unit leaves it. So it does not reproduce
seconds of lag; that wants a reading on the unit.

**What changed** (`csrc/scope/scope.c`):

1. **A frame starts only when the UART ring is all but empty** (`UART_IDLE`, 128 bytes, counted as the writer
   counts them). Otherwise the frame is dropped and looked at again 10 ms later: frames are never queued, and the UI
   task never waits in the writer.
2. **Drawn alone.** BACK (the frame on the glass) is copied to FRONT, the scope is drawn over it, and stock's
   `panel_diff` sends the changed groups and swaps. Stock's page (AMP's then, TRIG's since 2026-11-19) is not drawn again under the scope.
   - This only happens when the last full draw ended with the scope on top (`scope_end`: no list popup, routes popup
     or inserts overview over it), that frame is still on the glass, and no redraw is due. Otherwise the full redraw
     runs as before.
   - `panel_diff` returns the new FRONT in `%d0`. Declared as returning a pointer, gcc reads `%a0`, and the loop's
     canvas buffer became 0 (the first build, sc1: wild reads at 0x96 and up).
   - The moving-control lines hidden under the scope no longer ask for redraws.
3. **Drawn by bytes.** The strip is cleared with word writes, and each column's span of the trace is set as one
   byte mask per 8 rows. These are the same pixels v1's `SET_PIXEL` loops set.

**The rate** is 15 frames a second (`REDRAW` 100 audio frames; the User, 2026-11-17; 25 before).

**Measured** (emulator, the UART at the unit's rate, every build on the same clock). The key-to-screen delay runs
from encoder G's detent until the glass shows its new label, plus the time the bytes queued ahead of it take to
leave the UART:

| | scope instructions a second (noise / sine) | key to screen (noise / sine) |
|---|---|---|
| v1 at 25/s | 2.85 M / 2.69 M | 75 / 57 ms |
| v1's drawing at 15/s | 2.41 M / 2.33 M | 75 / 57 ms |
| now at 15/s | 0.67 M / 0.60 M | 75 / 58 ms |

Per frame: `scope_draw` 86,736 -> 19,065 (noise), 76,077 -> 15,683 (sine); a whole frame 176,905 + 12,987 (the page
draw + `panel_diff`) -> 34,490, all in `scope_poll`. The emulator's UI loop delivers 15 frames a second at "25" (it
wakes on a 30 Hz tick, a 40 ms period lands on every second pass) and 12-13 at 15/s. So the UART is not saturated
there, and the delay is the same for all three; with noise the new build dropped 1.3 frames a second.

**Proof (gate step `scope`, `emu_scope.py --proof`, noise):**
- every frame drawn alone has, in the strip (x 18..123, y 11..53), exactly the pixels v1's drawing gives for the
  same ring;
- every eighth frame, a full redraw forced then draws a frame byte-identical to the glass.

## Lighter still, the same pixels (2026-11-18)

The User: "i still get cpu in osclillo". Our !CPU label lights at C >= 90 % over 0.5 s, and on the unit the audio ISR
alone takes about 84.5 % of the CPU at rest (measured on the User's DN2, 2026-11-18): the page must stay light.
On the unit at rest the scope page read 82.6 %, other pages 80.8-81.6 %.

**Measured** on the coupled emulator (`scratch/scope-cpu/scopecost.py`, not in the repo: the ColdFire's ISR and UI on the build's own
snapshot, faithful timing, 2 s profiled, track 1 fed through its TDM receive slots). Instructions a second the scope
page costs over stock's AMP page at rest (the scope's UI routines counted inclusively, the tap in the ISR):

| feed | build | a frame drawn alone | scope part of a full draw | tap (ISR) | a second (15 frames) | est. % of the CPU |
|---|---|---|---|---|---|---|
| noise | main 493bad7e | 63,000 | 23,400 | 417,000 | 1.28 M | 1.5 % |
| noise | now | 51,100 | 25,000 | 131,000 | 0.85 M | 1.0 % |
| sine | main 493bad7e | 43,000 | 19,500 | 417,000 | 1.02 M | 1.2 % |
| sine | now | 32,200 | 21,400 | 127,000 | 0.59 M | 0.7 % |

% of the CPU: the emulator's ISR on stock's AMP page (49,109 instructions a frame, 73.7 M a second) taken as the
unit's 84.5 %, so about 0.87 M instructions a second per 1 % (an estimate: the snapshot's project is not the User's).
The DSP frames the ColdFire built were the same, frame for frame, on both builds (digest `d9b8e095` on the scope page,
`41bdcbee` on the AMP page): nothing but the drawing changed.

What changed (`csrc/scope/scope.c`):
1. **The tap** reads its words without a test a sample, and only in the 8 x D + 2 blocks before a frame is due:
   285 -> 87 instructions a block on average at 8 ms, and two thirds fewer uncached reads of the TDM page.
2. **A frame drawn alone** writes only the trace's columns whose rows changed, two words a column; it draws no label
   and no page dots (they are on the frame it is drawn over and change only in a full redraw). The full draw is
   v1's, as before.
3. **AUTO's peak** is one max and one min a sample.

What is left of a frame drawn alone is mostly stock's: `panel_diff` and the panel UART's writer (`0x4000220c`, its
mutex and the eDMA interrupt) send the changed 8-pixel groups, about 34,000 instructions for a noisy trace (52 groups)
and about half that for a steady tone. That is the price of a moving trace at 15 frames a second; it falls only with
fewer frames or fewer changed pixels, not with the same pixels. Not measured: the unit itself (C on the scope page),
and how much the uncached reads the tap no longer makes were worth there.

**The title.** amp_open posts "WAVEFORM" through stock's message line, and frames drawn alone never touch the title
bar. Another session saw "WAVEFORM" stay on the glass after the message ran out (12 s unchanged, claude/cpu-cuts,
2026-11-18). Here it did not reproduce: on main and on this build, in 8 openings at different moments
(`scratch/scope-cpu/titleprobe2.py`) and in the proof runs, stock asked for a full redraw 3 ticks after the message ran
out, and that redraw put the bar's own title back. So the bar no longer depends on that: `scope_end` notes whether a
full draw had the message up, and the first due frame after it ran out is a full redraw. What made it stay in the
other session's run was not found.

**Proof, stricter (gate step `scope`):**
- every frame drawn alone, as it goes to `panel_diff`, is the last full draw's frame byte for byte, but for the strip,
  which is exactly the model's (the control `brokenscopeid`, one byte at column 2 in frames drawn alone, passed the old
  proof; built on this code it fails all 112 such frames, and the first full-redraw check);
- the title's message runs out and, with nothing asked, a full redraw then draws exactly the glass;
- the glass a full redraw draws, after: the gains (x16, x1, x1/8), AUTO loud, quiet and loud again, a page change
  (SYN and back), a track change (TRK + TRIG 2: TRK closes the scope; a long [TRIG] back) and track 1 again;
- AUTO the first gain; the settings kept over the page and track change and a power-on (above).
- (2026-11-19, `trig_keys`) the keys: NO closes it and leaves stock's TRIG page; a tap on TRIG's page steps it on the
  release (nothing moves on the press) and back, never the scope; [TRIG] from SYN shows TRIG's page on the press;
  held 0.6 s, no scope and no step on the release; held, no scope before a second and the scope (amp_sub AMP_SCOPE)
  at a second, still up after the release, over TRIG's page, and a full redraw then draws the glass; [TRIG] tapped
  while up closes it with TRIG's page as it was (no step); SYN, AMP (stock's AMP page, amp_sub 0) and FX close it on
  their press; [AMP] steps 1/2 -> 2/2 -> 1/2 -> 2/2 -> 1/2, never the scope; a long [TRIG] from ENV2 opens it; FUNC +
  [TRIG] held is stock's QUANTIZE, no scope; a knob turned while [TRIG] is held, no scope. Every check opens the scope
  by the long press (the settings over a power-on too). On main ca9b7798 (388264b8) it fails at the first one: a long
  [TRIG] did not open the scope.
