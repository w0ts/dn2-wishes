# CUE / preview on the headphones: study (2026-11-12)

**The User's wish:** *"CUE / preview: mute a track on the main out and Overbridge but still hear it
on the headphones."*

Study only: no build, no unit access. Sources: stock OS 1.11/1.12 section 7 as already read in
this repo (`docs/link-research.md`, `docs/waverider-dsp-silence.md`, `docs/waverider-dsp-compare.md`,
`docs/sampler.md`), digikit's findings on the same SHARC driver, the board's part list
(`docs/hardware.md`), and the codec's published specification. Tags as elsewhere: [D] read in
the code, [M] measured, [I] inferred, [O] open.

## Verdict: not possible on the Digitone's own headphones

**The headphones are a copy of the main out made after the DAC.** The DSP produces exactly one
stereo analog signal; nothing in firmware can make the headphone jack differ from MAIN OUT L/R.

### Evidence

1. **One codec, two DAC channels.** The board carries one audio codec, U14 = **AKM AK4621EF**
   (`docs/hardware.md`, read off PCBA0109B). The AK4621 is a 24-bit **2-channel ADC + 2-channel
   DAC** codec (AKM MS1258-E; distributor listings "2ADC / 2DAC"). The ADSP-21569 has no
   analog outputs and the ColdFire carries no audio DAC on this board. So the board has two
   analog output channels in total, and MAIN OUT L/R and the headphones both come from them
   through analog stages (the headphone amplifier is a separate part not identified on the
   photographs) [D for the part, I for the analog split].
2. **The SHARC writes 2 DAC words per sample.** The codec ring is built at sw `0x1ca167`:
   two descriptors `0x2c0878` ↔ `0x2c0894`, pages `0x2c0478` / `0x2c0578`, **256 bytes = 64 words
   = 32 frames × 2 channels** (digikit: "2-descriptor rings of 0x40 words") [D]. The opener's
   device argument R4 = 4 selects the SPORT4 A half (DAI1 SP0A, DMA10) [D for the arguments, I for
   the device name]. SPORT4 B (DMA11) is the codec ADC, `0x2c0678` / `0x2c0778` [D].
3. **One writer, one source.** In the engine's block (cmd 3, arm `0x1c9f0f`), after the per-block
   routine sw `0x1c2712`, the driver calls **sw `0x1c9d3f`**: `lcntr = 0x20`, L from `0x268438`,
   R from `0x2684b8` (the master mix), `fix … by 31`, interleaved L/R into
   `0x2c0478 + (DM(0x268a38) << 8)` [D]. Every arm then ends at sw `0x1c9e29`, which negates the
   page's **64** words [D]. Cmd 0/1 write silence; cmd 2 (service passthrough) writes TDM RX
   slots 0/1 to the same two channels [D]. No other writer of the DAC pages exists in stock.
   The 750 Hz stuck tone (`docs/waverider-dsp-silence.md`, 48,000 / 64 = two 32-frame pages
   replayed, L ≈ R) is the hardware's own confirmation of a 2-page × 32-stereo-frame ring [M].
4. **No headphone source register.** With one stereo DAC there is nothing for a register to
   select: whatever the AK4621's control port offers (format, power, de-emphasis, attenuation),
   it cannot make a second pair. Its control-port writes were not located in either core (no
   prior reading names them) [O, and moot for the verdict]. The manual says the same from the
   outside: `INT TO MAIN` feeds "MAIN OUT and HEADPHONES OUT" and the main volume sets both
   (`docs/ideas-backlog.md`, cueing).

### Where each output takes its signal (stock)

| output | path | source |
|---|---|---|
| MAIN OUT L/R and HEADPHONES | SPORT4 A → AK4621 DAC → analog | `0x268438` / `0x2684b8` (master mix) via sw `0x1c9d3f` |
| Overbridge / USB main L/R | SPORT0 A TDM TX **slots 0, 1** → ColdFire SSI0 → USB | the same master mix, via the output stage sw `0x1c244d` loop A (`0x1c266c`), × 1.4286 |
| Overbridge tracks, FX returns, input | TDM TX slots 2..13 (channel table `0x25d760`, k = 2..41; mode 6 multiplexes the 42 channels) | track stereo blocks `0x258f68 + 0x100 t` (A, after routing) or `0x259f68 + 0x100 t` (B, raw), chosen by frame word `+0xa7a` |
| TDM slots 14, 15 | never written by stock | (the mod's sample link) |

The one split the hardware **does** allow is analog vs. Overbridge: the DAC page and TX slots
0/1 are written separately, from the same mix. The mod already uses it (wr_pvmix adds the
+Drive preview to the DAC page at the call of `0x1c9d3f`; the OS 1.12 branch also adds it to
TX 0/1, after depaffect's v0.42 report).

## What can be done instead

Ordered by how close each comes to the wish.

### W1. Split cue on the two DAC channels (the DJ mixer's "split cue")

MAIN OUT **L** = the main mix folded to mono, MAIN OUT **R** = the cue (the cued tracks only).
On headphones: main in the left ear, cue in the right. Overbridge main stays the full stereo
mix without the cued tracks.

- **Catch:** MAIN OUT R carries the cue, so the PA must be fed from **MAIN OUT L only, in mono**.
  This is a performance mode the User switches on, not a default. Whether that is acceptable is
  the User's call.
- **DSP change:** one hook at the driver's call of `0x1c9d3f` (sw `0x1c9fd2`), chained with
  wr_pvmix (the same site): before the conversion, write `L = (mixL + mixR) / 2`,
  `R = Σ cued tracks' stereo blocks folded to mono` into a scratch pair and have `0x1c9d3f`
  convert that (or convert ourselves and skip the call). The main mix at `0x268438` itself is
  not touched, so TX 0/1 (Overbridge main) and the recorder's MAIN tap are unchanged.
- **Removing the cued tracks from main and Overbridge main:** reuse stock's per-track
  **AUDIO ROUTING TO MAIN** bit (manual 13.6): it already takes a track out of the master mix,
  and Overbridge's per-track channels still carry a track routed off the main (the per-track
  monitoring setup in `docs/user-reports.md` W3). The cue reads the track's stereo block
  `0x258f68 + 0x100 t` (L at +0, R at +0x80) [D for the addresses; I that block A still holds
  the track when TO MAIN is off: to measure in the runner before building].
- **Cost per 32-sample block** (estimate, SHARC instructions): mono fold 32 × ~3 ≈ 100; each cued
  track 32 × 2 adds ≈ 70 (SIMD pairs would halve it); mask test 16 × ~3 ≈ 50. **One cued track
  ≈ 220, all 16 ≈ 1,300**, against the 298,615 cycles a block `LOAD_AVAIL`
  (`docs/load-budget.md`): under 0.5 %. Zero when no track is cued (one mask test, then the
  stock call). Memory: ~40 instructions of code and a 64-word scratch in L2.
- **Touches stock code:** the 18-byte site at sw `0x1c9fd2` (already wr_pvmix's; the cue goes
  inside wr_pvmix, not a second patch). The DAC output differs from stock only while a cue is on;
  `stockout` compares the mix, TX pages and records, which stay bit-identical, so the gate's rule
  holds with the DAC page declared as differing only when the cue mask ≠ 0. That declaration is
  the User's decision under the stock-code rule (CLAUDE.md).

### W2. Cue over Overbridge / USB: ColdFire only, no DSP change

Turn a track's TO MAIN off with a key combination; listen to its own Overbridge channel (or a
USB OUT `L:Tn R:Tm` pair in USB audio mode, pre-fader if chosen) on the computer's headphones;
the same combination puts it back. Main out, the Digitone's headphones and Overbridge main all
lose the track; the computer hears it alone. This is route 1 of the September cueing entry,
never started. Cost: none on the DSP.

### W3. Outbox 8 pair (only for an Outbox owner)

Route the cued tracks to an Outbox 8 output pair (`OUTBOX 8 ROUTING CONFIG`), headphones on
that pair. MAIN OS only, as W2; needs the Outbox's routing calls read.

### Not the wish, but possible: analog-only or Overbridge-only mute

Because the DAC page and TX 0/1 are written apart, a track can be taken out of the analog
outputs while kept in Overbridge main, or the reverse (the same hook as W1, subtracting the
track from one side). This does not give a private headphone mix.

## The CUE flag (for W1 or W2)

- **Storage:** a 16-bit run-time mask in the mod's own ColdFire RAM, one bit per track, **not
  saved** in the project or kit (no file format change; a power cycle clears it, as a DJ cue
  should). It drives stock's TO MAIN bit for that track and, for W1, is sent to the DSP in one
  free halfword of the 2,688-byte frame (to be allocated against `dnfw.waverider.frame` and the
  link's claims; bytes past `0xa80` are not sent).
- **Keys:** proposal: in MUTE mode, **FUNC + [TRIG n]** toggles track n's cue; the cued trig LED
  shows a distinct colour, and the stock mute is unaffected. Stock's own binding for FUNC + trig
  in mute mode has not been checked [O]: read the mute-mode key handler (`docs/mute-research.md`)
  before choosing. An alternative that cannot collide: a CUE page under FUNC + MUTE.
- **Where stock's TO MAIN bit lives** and how it reaches the DSP mix (`0x1c1f1e`) is not yet
  read [O]: the next reading is the `AudioRoutingMenuView` handler on the ColdFire.

## Follow-up: cue through the USB port as HOST (2026-11-12)

The User: *"is audio via USB out possible, as host?"*: the Digitone as USB host, driving a
class-compliant headphone dongle or interface as the cue output.

**Short answer: not with the hardware as it ships.** The chip could do it; the port and stock's
setup are device-only, and the Outbox 8 shows Elektron put the host role in the accessory.
A host build is conceivable only with a non-standard cable that injects 5 V, an unidentified
PHY that has to support host mode, and a USB host stack written from scratch, and it would give
up Overbridge, USB MIDI and the Outbox while it runs.

### (1) The controller and the mode stock runs

- The MCF5441x has a **dual-role (host / device / OTG) USB module** and a separate
  **host-only module**, sharing one 8-bit ULPI port (NXP MCF54418 data sheet, family feature
  list) [D, data sheet].
- Stock MAIN OS 1.12 references **only one register block, `0xFC0B0000`**: 154 immediates in
  `0x400030a2..0x40007028`, the USB driver and Overbridge's packet code, plus one at `0x4028217a`.
  It uses the device-only registers ENDPTSETUPSTAT `+0x1ac`, ENDPTPRIME `+0x1b0`, ENDPTFLUSH
  `+0x1b4`, ENDPTSTAT `+0x1b8`, ENDPTCOMPLETE `+0x1bc` and ENDPTCTRLn `+0x1c0..+0x1cc`, so this is the
  dual-role module. No immediate names any other USB block [D, byte scan of section 3].
- **USBMODE (`+0x1a8`) is written once, at `0x40005d10`: `moveq #30,d1; move.l d1,0xfc0b01a8`
  = 0x1E**, so CM = 2 (**device controller**), plus the ES, SLOM and SDIS bits [D].
- **PORTSC (`+0x184`) at `0x40006d1e..0x40006d30`**: PTS = 10 (`and #0x3fffffff; bset #31`),
  an **external ULPI PHY** (high speed, which Overbridge's channel count needs). At `0x40005d1e`
  bit 24 (PFSC, force full speed) is set or cleared from a setting [D for the writes; I for the
  field names, which follow the ChipIdea/EHCI layout this module uses].
- **ULPI viewport (`+0x170`)**: two references only (`0x40006b1e` writes `0x48000000`, a
  wake/run with no register address; `0x40006b34` polls it). **Stock never writes a PHY
  register**: no DrvVbus, no host pull-downs, so the PHY stays in its default device role [D].
- **OTGSC (`+0x1a4`)**: written only with `0x08000000` (B-session-valid interrupt enable,
  `0x40006d84`) and its status clear (`0x40005e6c`); the interrupt tests BSV (bit 11) to call
  connect or disconnect (`0x40005e44..0x40005e5c`). **The DN2 senses VBUS as an input. It never
  drives it (VC), never enables the ID pull-up (IDPU) and never reads ID** [D].
- **The Outbox 8 is the host, the DN2 its device.** Section 8 (the Outbox's firmware) carries
  `USB Host delay` / `device has attached` / `USB PD Task` (`docs/firmware-sections.md`). MAIN OS
  shows `THE USB CONFIG IS CURRENTLY BEING HANDLED BY OUTBOX 8` (`0x4021f67a`) and
  `OUTBOX 8 CONNECTED` (`0x40213e0e`). So the DN2 needs no host mode even for its own accessory [D].

### (2) The board

- **Connector: USB Type-B** per retail specifications ("Hi-Speed USB 2.0", "USB Type-B port for
  audio and MIDI") [I, not Elektron's own sheet; the User can confirm by looking]. A Type-B
  receptacle is a device connector by the USB specification: **no ID pin, VBUS is an input**, and
  there are no CC pins (that is USB-C).
- **VBUS supply:** nothing in stock drives one (above), and no 5 V switch, charge pump or PD
  part is identified on the board photographs (`docs/hardware.md` lists no USB parts at all; the
  ULPI PHY itself is not identified) [O]. A dongle on that port would need **5 V injected from
  outside** (a Y cable or powered adapter) and a **non-standard B-plug to A-socket cable**.
- **PHY host support** (15 kΩ pull-downs on D+/D−, its OTG Control register) depends on the
  unidentified PHY part [O]: a photograph of the chip by the USB connector names it.

### (3) If it were done anyway: what a minimal host would take

- **Mode:** a run-time "CUE HOST" mode that resets the module to USBMODE CM = 3 (host), sets the
  PHY's pull-downs over the ULPI viewport, and goes back to stock's device setup on exit and at
  every boot. Stock's device stack must not run meanwhile, so **Overbridge, USB MIDI, USB audio
  and the Outbox are off for the whole time it is in use**.
- **Stack (ColdFire C, from scratch, none in stock):** port reset and speed detection; the
  asynchronous schedule for control transfers (enumeration, GET_DESCRIPTOR, SET_CONFIGURATION,
  SET_INTERFACE alt 1, the UAC1 endpoint or UAC2 clock-source sampling-rate request); a descriptor
  parser for the first stereo 16/24-bit 48 kHz OUT alternate setting; the periodic schedule with
  isochronous descriptors: siTD for a full-speed dongle (192 B per 1 ms frame at 16 bit), iTD for
  a high-speed one (24 B per 125 µs). **Estimate: 8-15 KB of code, 2-4 KB of descriptor/buffer
  RAM**, no hub support, one device, UAC1 first (most dongles), UAC2 later.
- **Clock:** the dongle (adaptive or synchronous) follows the DN2's USB SOF, not the DN2's audio
  clock, so the ColdFire has to match rates: insert or drop a sample every few seconds, or an
  explicit-feedback endpoint for asynchronous devices. A drop/insert with a short crossfade is
  enough for cue.
- **CPU:** one interrupt per USB frame copying ~200 B: a few µs per ms at 250 MHz, **under 1 %**
  of the ColdFire [I, not measured].
- **The cue signal from the DSP:** the SHARC → ColdFire TDM link has 16 slots. Stock writes
  0..13 (main, tracks, FX returns, input by the channel table); the mod's sample link uses
  slots 8..15 on frames without Overbridge data and 14..15 on the receive side
  (`docs/overbridge.md`). **In host mode Overbridge cannot run**, so the Overbridge track slots
  (2..13) are idle and a cue pair can ride in two of them chosen against the link's claims.
  DSP cost: the W1 cue sum (≈ 70 instructions per cued track per block) plus `fix by 31` into
  two slots (≈ 70 per block); the ColdFire reads the receive window `0x4E6DF100` it already
  DMAs. With Overbridge running there is no free pair without moving the sample link.
- **Risk to the unit:** low for the firmware path (run time only, stock device setup at every
  boot, and the updater/bootstrap sections are not touched). The electrical side (5 V fed into
  the port, a forced host mode on an unknown PHY) is a hardware question nobody here has
  measured. **Not recommended** without the PHY's part number and the User's explicit go.

### Does W2 (cue over Overbridge / USB) already cover it?

Mostly, and without new hardware or a host stack. The DN2 is already a **class-compliant USB
audio device** (`USB AUDIO/MIDI` in USB CONFIG) whose `USB OUT` can carry one or two tracks as
L/R, pre- or post-fader. So **any USB host with headphones** (a laptop, or a phone or tablet with
an OTG adapter and a monitoring app) becomes the cue output: TO MAIN off for the cued track (the
W2 key combination), its USB pair on the host's headphones. What W2 cannot give is a cue with
**nothing but the Digitone and headphones**. On the DN2 alone that is only W1's split cue.

## Next step

Main / the User decide between W1 (headphone split cue, main out mono from L) and W2 (cue on
the computer over Overbridge, no DSP work). Then, for either: read the TO MAIN storage and its
frame path (ColdFire), and check stock's FUNC + trig in mute mode. For W1 add one runner step
that shows block A still carries a track with TO MAIN off, before any build.

## Sources

- `docs/link-research.md` §2 (rings, dispatch, channel table), `docs/waverider-dsp-silence.md`
  (`0x1c9d3f`, the 750 Hz ring), `docs/waverider-dsp-compare.md` §4 (descriptors),
  `docs/sampler.md` (wr_pvmix and the Overbridge preview), `docs/hardware.md` (U14).
- digikit `docs/findings/07-emulator.md` (SPORT4A/B rings of 0x40 words, `0x1c9d3f` interleaved
  L/R Q31).
- AK4621 specification: [electronicsdatasheets.com](https://electronicsdatasheets.com/download/74494.pdf?format=pdf),
  [Arrow listing](https://www.arrow.com/en/products/ak4621ef/asahi-kasei-microdevices-corporation),
  [embeddedrelated](https://www.embeddedrelated.com/parts/p/AK4621EF) ("2ch ADC / 2ch DAC").
- USB follow-up: stock MAIN OS 1.12 section 3 (`scratch/sec112/section_3_MAIN_OS.bin`, image base
  `0x40000400`), byte scan for `0xFC0Axxxx..0xFC0Bxxxx` immediates and hand decode of the writes
  above; MCF5441x USB modules: [NXP MCF54418 data sheet](https://cache.nxp.com/docs/en/data-sheet/MCF54418.pdf);
  the DN2's connector: [Musician's Friend listing](https://www.musiciansfriend.com/keyboards-midi/elektron-digitone-ii-16-track-polyphonic-digital-synthesizer),
  [Gear4music listing](https://gear4music.com/us/en/Keyboards-and-Pianos/Elektron-Digitone-II-Polyphonic-Digital-Synthesizer/6RM3).
