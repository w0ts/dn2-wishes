# The AMP scope page: the selected track's oscilloscope

2026-11-11. The User asked for "an Oscilocope page for each track, i would put it as AMP page 2",
"per track, after the inserts", and chose "A, follow overbridge. simple, logical."
The feasibility study is `scratch/scope/feasibility.md` (not in the repo).

## Use

Stock's AMP page has one page. [AMP] on it now steps through three pages (2026-11-12, the User: ENV2 "right
after the stock envelope page", the scope one page later; each place one constant in `csrc/waverider/amp_pages.h`):

- **AMP 1/3** is stock's page, with three page dots added.
- **AMP 2/3** is ENV2 (`docs/matrix.md`).
- **AMP 3/3** is the scope.

The title line says "AMP (n/3)" on each switch. FUNC + [AMP], and [AMP] from any other page, work as on stock.
NO, or any page key, closes the scope (as the INSERT pages do, docs/inserts.md).

While the scope is up, any encoder but G sets the time across the screen: 2, 4, 8, 17, 33 or 67 ms
(100 points, every 1st..32nd sample at 48 kHz). The bottom-right label (H) shows the time.

**Vertical zoom** (2026-11-11, the User: "the oscilo should also have a vertical zoom"): encoder G sets the gain,
x1 x2 x4 x8 x16 or AUTO, its label at G. AUTO takes the largest of those gains that keeps the 100 shown samples
inside the strip, and its label says which ("Ax4"); a sample of exactly half scale stays at Ax1 (x2 would pass full
scale by one step). A sample past the strip is drawn on its top or bottom row. The gain and the time are the page's
own, the same for every track, and not saved (a way of looking, not part of a sound); the gain starts at x1.
The trace starts at the newest rising zero crossing, so a steady sound stands still; it redraws 25 times a second.

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
  The ISR's code before the hook stays stock (`scripts/gate_overbridge.py`).
- A routing slot holds every track routed to it. Normally slot = track.
- The records are copied by stock at each frame's SPI call. That copy and the ISR are not synchronised, so a block can
  be read twice or missed (a glitch in the trace, not in the audio).

**Measured on the unit** (remoteui, 2026-11-11): the records carry track 8 (fields +6 / +9) live with notes,
with and without the Overbridge Engine app. The source flag byte `0x8000536A` read 1.
Tracks 1–6 in the TDM window were not yet read on the unit.

**Measured in the 1.12 emulator** (2026-11-11):
- the AMP key is code 4 (the firmware's name table, `scripts/emu_panel_map.py`);
- the AMP page's view class is `0x401E2320` (the screen's view list on [AMP], `0x401E1448` on [FX]).
