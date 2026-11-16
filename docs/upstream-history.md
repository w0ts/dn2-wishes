# Upstream's version history (De-Pattern/dn2mk2-firmware)

One section per upstream version, newest first: its date, tag or source commit, the published firmware's sha256 (FIRMWARE.md), the room it leaves in the OS's 2 MiB USB upgrade buffer (measured on the published `.syx` with that tag's `dnfw.safety.usb_upgrade_bytes`), what it brought (FIRMWARE.md's table, its own words), and what it changed for our series. The per-release routine adds the next one (`autobuild/rebase/UPSTREAM.md`; `autobuild.py rebase history TAG`).

## v0.56 · DDRW

- **Released:** 2026-11-15
- **Commit:** tag `v0.56` = `47c95a24`
- **Firmware:** `DN2mod_v0.56_DDRW_OS1.11.syx`, sha256 `820bcb6db96746e1dfcc3ce0c07505b551aaaa33cc4471211907aa5db53c0f29` (the published file's)
- **USB upgrade buffer:** 2,086,155 of 2,097,152 bytes, 10,997 free
- **What it brought:**
  - DDRW: TIME glides between waves (up to ~2 s), BR1/BR2 heard across the whole knob
  - the patcher builds test builds
- **Release note** (`releases/v0.56.md`): DPRO DDRW's TIME and bit reduction now do something you can hear
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.55 · FLEXPOOL

- **Released:** 2026-11-15
- **Commit:** tag `v0.55` = `deddeab5`
- **Firmware:** `DN2mod_v0.55_FLEXPOOL_OS1.11.syx`, sha256 `298b02141fd7847b0a6fcc0a174718e4c3be5e21933ba961753c92e2b16c40dc` (the published file's)
- **USB upgrade buffer:** 2,086,155 of 2,097,152 bytes, 10,997 free
- **What it brought:**
  - the 8 FLEX buffers in every sample machine: SAMP past 127 to B1..B8 (knob, list, p-locks), a track on Bn plays that buffer's take
  - MUTE SRC waits for the first take (no gap)
- **Release note** (`releases/v0.55.md`): The eight FLEX buffers are now at the end of the sample list on every sample machine, so any ONESHOT, WERP, STRETCH, REPITCH, GRID or SLICE track can play a FLEX take. MUTE SRC also waits for the first take before muting
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.54 · NAME

- **Released:** 2026-11-15
- **Commit:** tag `v0.54` = `a900d2d9`
- **Firmware:** `DN2mod_v0.54_NAME_OS1.11.syx`, sha256 `8a3586d20255d6cb22d8f6a8ee841773871834d09280754d0d2ed2889dd12ba3` (the published file's)
- **USB upgrade buffer:** 2,085,347 of 2,097,152 bytes, 11,805 free
- **What it brought:**
  - our names on the Digitone's own NAME screen: a recording's FILE NAME, the browser's RENAME and CREATE FOLDER open stock's naming screen (its keys, FUNC + ARROW edit grid, SETTINGS: RANDOM, copy/paste name)
- **Release note** (`releases/v0.54.md`): Naming your recordings, samples and folders now uses the Digitone's own NAME screen, the same one patterns, sounds and projects use
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.53 · PAGES

- **Released:** 2026-11-13
- **Commit:** tag `v0.53` = `8f42f4fb`
- **Firmware:** `DN2mod_v0.53_PAGES_OS1.11.syx`, sha256 `13c01517cd5b6cc0c0a57639874a01662a096b07e0cb5d24a11fb0bcbc6789e0` (the published file's)
- **USB upgrade buffer:** 2,084,741 of 2,097,152 bytes, 12,411 free
- **What it brought:**
  - FLEX polish: FLEX REC's page LEDs follow its page (NiKo)
  - a switch to FLEX sets trig LEN to INF
  - BUF snaps buffer to buffer, a p-locked BUF shows its number, and BUF locks pick the buffer a trig plays (NiKo)
  - PLAY two detents a mode
  - FUNC + turn moves R.LEN a bar
- **Release note** (`releases/v0.53.md`): FLEX polish: the page LEDs follow FLEX REC's page, a new FLEX track plays its whole take, BUF behaves like a choice and its locks play, PLAY turns quicker, R.LEN snaps to bars
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.52 · MUTE

- **Released:** 2026-11-12
- **Commit:** tag `v0.52` = `eae20937`
- **Firmware:** `DN2mod_v0.52_MUTE_OS1.11.syx`, sha256 `08dd58e75bd5958f21a8fb5866110b847fa92ddfacaad47f867562377ab27a13` (the published file's)
- **USB upgrade buffer:** 2,084,438 of 2,097,152 bytes, 12,714 free
- **What it brought:**
  - FLEX MUTE SRC: REC SETUP's knob H takes the SRC track out of the mix (its level and FX sends) while FLEX still records it
  - the RECORDER's R.LEN counts steps at the pattern's scale (impbox)
- **Release note** (`releases/v0.52.md`): FLEX REC can take its source track out of the mix while it still records it, and the RECORDER's R.LEN now counts steps at the pattern's scale
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.51 · LIGHTER

- **Released:** 2026-11-12
- **Commit:** tag `v0.51` = `0f52c1ec`
- **Firmware:** `DN2mod_v0.51_LIGHTER_OS1.11.syx`, sha256 `c48ad00ff2fc5f873903789dad9aaa58eadcbc1782f0107525e4af726bd3c0ff` (the published file's)
- **USB upgrade buffer:** 2,083,933 of 2,097,152 bytes, 13,219 free
- **What it brought:**
  - lighter Monomachine and Machinedrum machines, not bit for bit (SID -64 %, DDRW -43 %, DENS -40 %, VO-6 -9 %, TRX-CY -33 %, TRX-MA -26 %), so more voices before the guard drops one
  - FLEX REC's settings per track, saved with the kit
  - CLEAR BUF (FUNC + NO)
  - REC SETUP's state in the left column
  - sample TUNE plays its fine values and is drawn as WaveTone's ruler
- **Release note** (`releases/v0.51.md`): Lighter Monomachine and Machinedrum machines (more voices before the DSP guard steps in), FLEX settings per track, CLEAR for a buffer, and sample TUNE that plays its fine values
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.50 · LEVEL

- **Released:** 2026-11-12
- **Commit:** tag `v0.50` = `a235d98d`
- **Firmware:** `DN2mod_v0.50_LEVEL_OS1.11.syx`, sha256 `fabbcc911269bec9d8e9c12fd5118a6733bbbb08eed98af0d2f1ddeaa4b6127c` (the published file's)
- **USB upgrade buffer:** 2,082,822 of 2,097,152 bytes, 14,330 free
- **What it brought:**
  - FLEX takes of a track at the track's level (v0.49's were very quiet)
  - GAIN on REC SETUP (G, -24..+38 dB) with a level meter on H
  - BUF fixed (the take was read 14 slots off) and C BUF on REC SETUP
  - impbox's fixes: TUNE rounds, SMP readable with TRK held, page-2 locks shown, E/F pushed clear SLD/SLEN
  - gate: SHARC step flexlevel, the link steps ~20x faster
- **Release note** (`releases/v0.50.md`): FLEX takes at the source's level, a GAIN knob, and impbox's fixes
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.49 · FLEX

- **Released:** 2026-11-11
- **Commit:** tag `v0.49` = `3e33eef3`
- **Firmware:** `DN2mod_v0.49_FLEX_OS1.11.syx`, sha256 `31c68448759c2f2eea240cbfdb5d60e059caa2b18e3fa7ecede7b8ff65f3de9f` (the published file's)
- **USB upgrade buffer:** 2,081,812 of 2,097,152 bytes, 15,340 free
- **What it brought:**
  - FLEX, the live-buffer machine that replaces BOUNCE: recorder trigs on steps ([TRIG] a one-shot, FUNC + [TRIG] every pass) record a track, IN or MAIN into one of 8 buffers for R.LEN steps, and the FLEX track plays the take with its own notes (ONESHOT's page, BUF 01..08)
  - FLEX REC's two pages (REC TRIGS, REC SETUP)
  - Q.REC
  - old BOUNCE tracks open as FLEX
  - the DSP guard gives sample voices their time first and stops a dropped one cleanly
  - STRT/LEN/LOOP turned mid-note no longer move the playhead
- **Release note** (`releases/v0.49.md`): FLEX, the live-buffer machine that replaces BOUNCE, plus a fairer DSP guard and a steady playhead
- **For us:** (not written yet: add it to FOR_US in autobuild/rebase/lib/history.py; UPSTREAM.md)

## v0.48 · FINE

- **Released:** 2026-11-10
- **Commit:** tag `v0.48` = `7bbe0c85`
- **Firmware:** `DN2mod_v0.48_FINE_OS1.11.syx`, sha256 `8bf7ff0017fba6ea7733059f795a98316a65032425d8b511aa0559297fc53358` (the published file's)
- **USB upgrade buffer:** 2,076,257 of 2,097,152 bytes, 20,895 free
- **What it brought:**
  - STRT/LEN/LOOP as the DT2's fine controls (0.00..120.00, the stock fine knob, push + turn whole steps; the DSP plays from that exact place)
  - THRES fixed (the meter's scale, live while armed)
  - KEYBOARD kept through grid recording
  - turned values shown on the sample pages
  - SLICE's keys as the DT2's
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.48.md`): the fixes from this week's reports, STRT/LEN/LOOP exactly as the DT2 has them, and BOUNCE's code out
- **For us:** BOUNCE's code removed (rectrig.c, emu_rectrig.py; type 17 stays reserved for it: our numbers SOPHIE 20, PLAITS 18, TB303 19 unchanged); STRT/LEN/LOOP fine controls share records 239/258/257 with our units readouts (smp_fine runs last); its value-under-the-knob shares smp_knob_code with our popup (own copy now); the RECORDER panel it polished is replaced by our DT2 screens. Series v0.48 (rr-v0.48-resolved) also stores our section 7 as LZMA (USB room ~159 KB instead of ~12 KB). The Wishes builder is paused (the User, 2026-11-11), outside the series.

## v0.47 · TUNED

- **Released:** 2026-11-09
- **Commit:** tag `v0.47` = `01113e61`
- **Firmware:** `DN2mod_v0.47_TUNED_OS1.11.syx`, sha256 `dda3d00824daf42e62eb1c1797835d363b3af9e02db96169a025653d9f47857b` (the published file's)
- **USB upgrade buffer:** 2,080,802 of 2,097,152 bytes, 16,350 free
- **What it brought:**
  - the Monomachine's TUNE reads -64..+63 (0 in tune), FUNC + turn a semitone at a time
  - the TRIM preview 6 dB quieter (back at v0.37..v0.39's level)
  - the RECORDER's INTO box smaller
  - BOUNCE out of MACHINE SEL (old BOUNCE tracks still load)
  - gate: its reuse cache refuses passes from another worktree
- **Release note** (`releases/v0.47.md`): a small release: the Monomachine's TUNE as the Monomachine shows it, a quieter TRIM preview, and BOUNCE out of MACHINE SEL while it's rebuilt
- **For us:** TRIM preview -6 dB: ours stays at its -12 dB (not stacked); the Monomachine TUNE (signed, FUNC + turn by 32) turned off on SOPHIE/PLAITS/TB303 (step tune); BOUNCE hidden from MACHINE SEL. Series v0.47; ours 1.12 NOBOOT build bdffea50: USB 2,069,591 bytes, 27,561 free.

## v0.46 · KEEPER

- **Released:** 2026-11-09
- **Commit:** tag `v0.46` = `a07ae159`
- **Firmware:** `DN2mod_v0.46_KEEPER_OS1.11.syx`, sha256 `2dc196d8977de107d7b96fb4d87a18cc5a90d5a053678276e0803d84b2fba7c8` (the published file's)
- **USB upgrade buffer:** 2,080,297 of 2,097,152 bytes, 16,855 free
- **What it brought:**
  - recordings (RECORD NOW, a BOUNCE take saved with FUNC + YES) also copied into +DRIVE > RECORDED under their own name
  - FILE NAME up to 35 characters, RENAME long names, a new folder up to 30
  - BOUNCE's BUF reads 1..8
  - gate: the copy with a power cut after every step, a full +Drive, a send mid-copy
- **Release note** (`releases/v0.46.md`): your recordings now land in +DRIVE > RECORDED, like the DT2, and the naming screen takes long names
- **For us:** Two conflicts (link16 scenarios, entry lists); b6 replayed onto it. Series v0.46. Skipped as a base for our builds after v0.47 came out the same day.

## v0.45 · ROOMIER

- **Released:** 2026-11-08
- **Commit:** tag `v0.45` = `95a8830e`
- **Firmware:** `DN2mod_v0.45_ROOMIER_OS1.11.syx`, sha256 `02e4a35ccc66a4f244a21d4676740af7822105482581d81762c26c63075b4542` (the published file's)
- **USB upgrade buffer:** 2,078,984 of 2,097,152 bytes, 18,168 free
- **What it brought:**
  - BOUNCE fixed (v0.44 froze the unit on MACHINE SEL → BOUNCE and at power-on with a BOUNCE track) and back in MACHINE SEL
  - the +Drive library holds 16,384 samples
  - SELECT UNUSED in PROJECT RAM
  - recorder trigs on the [TRIG] LEDs while the BOUNCE REC panel is open
  - SAMP past the last loaded sample no longer plays the last one
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.45.md`): BOUNCE is back and fixed, plus a bigger +Drive library, SELECT UNUSED, recorder trigs on the [TRIG] LEDs, and the SAMP bug where scrolling past your samples kept playing the last one
- **For us:** PING removed upstream: our page/DSP lines for it dropped; machine numbers ruled (BOUNCE keeps 17, SOPHIE 17 -> 20, PLAITS 18, TB303 19); new emu_machine_* gate scripts into port_only.txt. Series v0.45. Skipped by the User as a base for a release of ours.

## v0.44 · BOUNCE

- **Released:** 2026-11-07
- **Commit:** tag `v0.44` = `9b5672b0`
- **Firmware:** `DN2mod_v0.44_BOUNCE_OS1.11.syx`, sha256 `6b912546525ef2a4bf6fba3268a1fd553883ba6f6340e6f4e60fe3680b0f3166` (the published file's)
- **USB upgrade buffer:** 2,085,044 of 2,097,152 bytes, 12,108 free
- **What it brought:**
  - withdrawn (2026-11-08): BOUNCE froze the unit. Use v0.45. BOUNCE, the seventh sample machine: Octatrack-style recorder trigs placed with [TRIG] (FUNC + [TRIG] a one-shot) record into the track's own buffer (8 buffers, two halves each), play the take fitted to its steps at any tempo, switch at Q.PLAY
  - Q.REC
  - FUNC + YES saves the take to the pool and +Drive
  - YES YES re-arms one-shots
  - v0.41's REC trigs, ARM knobs and REC TRIGS page gone
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.44.md`): live sampling redone, the Octatrack's way: a BOUNCE machine whose track records into its own buffer on recorder trigs placed with the [TRIG] keys, plays the take in time at any tempo, and saves it to the pool when you want it. v0.41's REC trigs, the two ARM knobs and the REC TRIGS page are gone.
- **For us:** Withdrawn upstream (BOUNCE froze the unit); never a base of ours.

## v0.43 · ROOM

- **Released:** 2026-11-07
- **Commit:** tag `v0.43` = `d692ad16`
- **Firmware:** `DN2mod_v0.43_ROOM_OS1.11.syx`, sha256 `4089df39f689ff6382a415a1b830b1681f256c638ef9b8e5abc09e3a955920e0` (the published file's)
- **USB upgrade buffer:** 2,083,428 of 2,097,152 bytes, 13,724 free
- **What it brought:**
  - 128 +Drive library folders (folders inside folders past 64; an older library as it was)
  - the Monomachine voices 25-36 % lighter (their render scratch in L1, bit-exact)
  - the gate's boot steps faster
- **Release note** (`releases/v0.43.md`): room on the +Drive and on the DSP: the library holds 128 folders (it stopped at 64), and the Monomachine machines take a quarter to a third less of the DSP, same sound bit for bit.
- **For us:** The base of our series (series v0.43: SOPHIE, the OS 1.12 port, TDM fix, LOAD TO PROJECT queue, meter + MnM pages).

## v0.42 · LEAN

- **Released:** 2026-11-06
- **Commit:** tag `v0.42` = `29aef99c`
- **Firmware:** `DN2mod_v0.42_LEAN_OS1.11.syx`, sha256 `8a8be7ac51e24c3f2b4394e1e1cabc10f3a8847f17c4223eb96836f114027410` (the published file's)
- **USB upgrade buffer:** 2,083,226 of 2,097,152 bytes, 13,926 free
- **What it brought:**
  - Monomachine machines re-coded, bit for bit, lighter on the DSP (DDRW -27%, SID -25%, DENS -21%, VO-6 -18%, WAVE -15%)
  - DDRW's bit reduction exact (all 366 Monomachine references match)
  - Machinedrum voices start clean on a machine change (the PI-HH clicks and loud spikes)
  - the Machinedrum sample reader re-coded, identical
  - GRID/SLICE menus let go of other pages and tracks
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.42.md`): the Monomachine machines re-coded for this firmware: same sound, bit for bit, a good deal lighter on the DSP. DDRW's bit reduction now rounds exactly as a real Monomachine. and the loud spikes and rimshot-like clicks when a voice moves between Machinedrum machines are gone.
- **For us:** Before our series (it starts on v0.43).

## v0.41 · LOOP

- **Released:** 2026-11-06
- **Commit:** tag `v0.41` = `38b7bac2`
- **Firmware:** `DN2mod_v0.41_LOOP_OS1.11.syx`, sha256 `c8a3421962bfe3c4eaa8dc1d61b25ac60c7746a16ec21242114d1a6d87df703f` (the published file's)
- **USB upgrade buffer:** 2,082,822 of 2,097,152 bytes, 14,330 free
- **What it brought:**
  - REC trigs (FUNC + VOICE, hold a step, H: REC 1 / REC 2), armed per track OFF / ONCE / ON
  - two looping buffers REC 1 and REC 2 (SAMP 124, 125) that keep playing while they re-record
  - QPLAY (a take heard from the next boundary) and QREC (RECORD NOW waits for the boundary)
  - the REC TRIGS page
  - slides on our own machines' controls
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.41.md`): Octatrack-style rec trigs with two looping buffers, QREC and QPLAY, slides on our own machines' controls, and fixes from your reports. thanks depaffect, paQ, Pablo and everyone testing.
- **For us:** Before our series (it starts on v0.43).

## v0.40 · NEST

- **Released:** 2026-11-06
- **Commit:** tag `v0.40` = `562db7c4`
- **Firmware:** `DN2mod_v0.40_NEST_OS1.11.syx`, sha256 `a3e59afcdc7319093a58a3e653f839a021b87dd5d156c174212da726beeabf74` (the published file's)
- **USB upgrade buffer:** 2,078,580 of 2,097,152 bytes, 18,572 free
- **What it brought:**
  - Folders inside folders on the +Drive (six levels, browser and import page)
  - SLICE no longer says CANNOT READ IT (a signed time compare), its menus wait and retry, LINKED/UNLINKED start and end
  - SAMP/SLCE p-locks play exactly what is locked
  - slides survive copy, paste and undo
  - the TRIM preview's and sample pages' playheads follow at once
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.40.md`): Folders inside folders on the +Drive, a SLICE editor that reads its sample every time, a recorder that normalises like the DT2, slides that survive copy and paste, and a long list of your reports fixed. thanks takton, ptkrm, paQ, Pablo, mattv0216 and everyone who sent reports.
- **For us:** Before our series (it starts on v0.43).

## v0.39 · SLIDE

- **Released:** 2026-11-03
- **Commit:** tag `v0.39` = `7e8c5b45`
- **Firmware:** `DN2mod_v0.39_SLIDE_OS1.11.syx`, sha256 `cfb66854200e93e7e6a348be7e29980b3d36241c79673775b1aa1a1ae221fd10` (the published file's)
- **USB upgrade buffer:** 2,074,439 of 2,097,152 bytes, 22,713 free
- **What it brought:**
  - Parameter slides (SLD/SLEN, TRIG page 2)
  - resampling records the whole take (it kept ~2 ms, then the empty input)
  - THRES 0 learns its floor
  - +DRIVE look-alike samples matched by identity (">A003" on every row)
  - +DRIVE held arrows, FUNC page, pushed-knob page
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.39.md`): Parameter slides, resampling that records the whole take, a +Drive that tells look-alike samples apart, and s!Rwa²'s own start-up animation. thanks paQ, s!Rwa², and everyone who sent +Drive and recorder reports.
- **For us:** Before our series (it starts on v0.43).

## v0.38 · JUMP

- **Released:** 2026-11-02
- **Commit:** tag `v0.38` = `ee6b3452`
- **Firmware:** `DN2mod_v0.38_JUMP_OS1.11.syx`, sha256 `2ae262f766727f88ea0c2014c0e06a5a9115cbff9c876d961b05bab490ffef48` (the published file's)
- **USB upgrade buffer:** 2,068,682 of 2,097,152 bytes, 28,470 free
- **What it brought:**
  - Direct Jump (PTN + YES/NO)
  - per-project sample pools
  - new samples and recordings play at once (silent until a restart since v0.33)
  - THRES 0 waits for real sound
  - a SLICE/GRID KEYBOARD chord-memory crash
  - gate: 22 live adds + 3 recordings must play, MAIN recording, sample chords, the arp/chord-memory fuzz
- **Release note** (`releases/v0.38.md`): Direct Jump, per-project sample pools, and the fix for silent samples. thanks depaffect, ptkrm, \x0x/ and blskk for the reports.
- **For us:** Before our series (it starts on v0.43).

## v0.37 · INTRO

- **Released:** 2026-11-01
- **Commit:** tag `v0.37` = `459643b0`
- **Firmware:** `DN2mod_v0.37_INTRO_OS1.11.syx`, sha256 `dfd503d8816ad498eea953482984610edb4af239f4a5aa93c5448c6182a07ea0` (the published file's)
- **USB upgrade buffer:** 2,062,521 of 2,097,152 bytes, 34,631 free
- **What it brought:**
  - A start-up animation (a redraw based on s!Rwa²'s design) (59 frames, every one checked in the gate)
  - DDRW lighter (3 voices, same sound)
  - resampling MAIN records the main mix (it gave an empty sample)
  - the sample preview 6 dB down
  - polyphonic sample playback checked (chords on ONESHOT, WERP, SLICE)
- **Release note** (`releases/v0.37.md`): a new start-up animation, a lighter DDRW, and the MAIN resampling fix. big thanks to s!Rwa² for the animation, and to \x0x/ and paQ for the preview report.
- **For us:** Before our series (it starts on v0.43).

## v0.36 · VOICES

- **Released:** 2026-11-01
- **Commit:** tag `v0.36` = `5fce704b`
- **Firmware:** `DN2mod_v0.36_VOICES_OS1.11.syx`, sha256 `8027709cc26236356acb50291726f510d6c8b59e9781aef2456a6c39169ce135` (the published file's)
- **USB upgrade buffer:** 2,060,400 of 2,097,152 bytes, 36,752 free
- **What it brought:**
  - More Monomachine voices: SID, VO-6 and DENS from 2 to 4 at once, DDRW from 1 to 2 (the v0.26 fixed budget gone; the DSP-time guard decides)
  - a voice that doesn't fit is stolen cleanly (silent until its next note) instead of chopping in and out
  - DDRW/DENS's busiest tables in fast memory
  - a four-note chord test per Monomachine machine in the gate
- **Release note** (`releases/v0.36.md`): more Monomachine voices. thanks misterairplane for the report.
- **For us:** Before our series (it starts on v0.43).

## v0.35 · SWEEP

- **Released:** 2026-11-01
- **Commit:** tag `v0.35` = `586292cd`
- **Firmware:** `DN2mod_v0.35_SWEEP_OS1.11.syx`, sha256 `2cf0fae42cf8aacb29e483236f55d9a636edc022f0f176b315367d8875a07a4e` (the published file's)
- **USB upgrade buffer:** 2,060,299 of 2,097,152 bytes, 36,853 free
- **What it brought:**
  - The bug sweep: MACHINE SEL's empty FLTR column after choosing a machine low in the list (v0.33), the +DRIVE preview retriggering while held, SYN held shows our pages' values, LOAD TO PROJ skipping same-length samples, deleted folders left in the list (and the import page can delete folders), PERC's names on another track's LFO page (B10)
  - `dn2diag.py entries`
  - a new gate step that checks the drawn MACHINE SEL columns and SYN pages
- **Release note** (`releases/v0.35.md`): a release of fixes only: the bugs you reported, worked through one by one. thanks flupperich6l, misterairplane, Pablo Se7en, Kokozi, blskk and everyone who posted reports.
- **For us:** Before our series (it starts on v0.43).

## v0.34 · TIMING

- **Released:** 2026-10-31
- **Commit:** tag `v0.34` = `e61829ac`
- **Firmware:** `DN2mod_v0.34_TIMING_OS1.11.syx`, sha256 `22e79856d6ba10a9869a8ec3e44703261371f9366a60c9a72a4bb216ac181cd6` (the published file's)
- **USB upgrade buffer:** 2,059,188 of 2,097,152 bytes, 37,964 free
- **What it brought:**
  - The P-I voices that stayed dead (v0.33's guard never reset a wiped voice): fixed, and the guard now says which voice and whether its delay lines held the NaN (FUNC held: `V1D`/`V1X`; SysEx DIAG)
  - SCAN reads any DSP memory for NaN (`tools/dn2diag.py`)
  - the model's NaN as the core's
  - the gate: the audio interrupt at its real rate preempting our code (fuzz), the guard's wipe (runner 3w), the DSP's memory-cost clock
- **Release note** (`releases/v0.34.md`): the fix for the P-I voices that stayed dead, and the tools to find why they go bad in the first place. thanks misterairplane, Pablo Se7en, blskk and the owner's reports.
- **For us:** Before our series (it starts on v0.43).

## v0.33 · STEADY

- **Released:** 2026-10-30
- **Commit:** tag `v0.33` = `76725740`
- **Firmware:** `DN2mod_v0.33_STEADY_OS1.11.syx`, sha256 `4161fa4cc0c5d755116a889357741e27c3599e6ee8e931382d42f4d28b9f4cef` (the published file's)
- **USB upgrade buffer:** 2,058,481 of 2,097,152 bytes, 38,671 free
- **What it brought:**
  - The freeze hunt: a guard against all audio cutting out (a runaway voice), keys and menus that went dead (SLICE/GRID's YES after MACHINE SEL, keys whose release went elsewhere, the sample list left open on another track), stray DSP reads from a bad sample entry, a garbage-state and worst-case DSP stress test, a UI fuzz in the gate
  - +DRIVE preview (FUNC + YES), MOVE SELECTED, NEW FOLDER
  - PROJECT RAM ticks with YES
  - the recorder: no DEST, SRC/CHAN apart, TRIM zoom
  - slices from C1
  - and more (FIRMWARE.md)
- **Release note** (`releases/v0.33.md`): the stability release. thanks to everyone who reported bugs, especially Moog, CAT, Pablo Se7en, Kokozi, blskk and zuzsw.
- **For us:** Before our series (it starts on v0.43).

## v0.32 · DSP

- **Released:** 2026-10-29
- **Commit:** tag `v0.32` = `bf0f2afa`
- **Firmware:** `DN2mod_v0.32_DSP_OS1.11.syx`, sha256 `a992f5228d13a4a2199cda3252262aeb1f4465fed8bbbc7b51cdfac7495f9289` (the published file's)
- **USB upgrade buffer:** 2,056,057 of 2,097,152 bytes, 41,095 free
- **What it brought:**
  - The DSP-time fix: the Machinedrum and Monomachine voices' working state in the DSP's fast internal memory, a CPU guard that measures the stock's share, a DSP load meter (FUNC held on PERC/Monomachine pages)
  - FUNC + turn on our controls
- **Release note** (`releases/v0.32.md`): this is the big CPU / dropout release. thanks to @complex_ping, whose research notes for his OVERTONE firmware showed us that on the real unit, DSP cost is mostly memory access, not instruction count.
- **For us:** Before our series (it starts on v0.43).

## v0.31 · DRIVE

- **Released:** 2026-10-29
- **Commit:** tag `v0.31` = `3b5792af`
- **Firmware:** `DN2mod_v0.31_DRIVE_OS1.11.syx`, sha256 `9445fa093b86ddaa224969c84f8c49d67fe2fe21f9690ae837705337984bff28` (the published file's)
- **USB upgrade buffer:** 2,055,451 of 2,097,152 bytes, 41,701 free
- **What it brought:**
  - The +Drive library (about 20 GB, folders; LOAD TO PROJECT / LOAD TO TRK in the browser's +DRIVE), sent from the import tool or dn2samples.py
  - the kit's samples load first at power-on (LOADING n%)
  - a finished Machinedrum voice frees its DSP time
  - the browser's NO / NO held / page keys
- **Release note** (`releases/v0.31.md`): 1. power on with samples kept: LOADING n% on a sample track, and the pattern plays while it counts
- **For us:** Before our series (it starts on v0.43).

## v0.30.1 · AMDFIX

- **Released:** 2026-10-29
- **Commit:** source commit `be7a74a3` (no tag)
- **Firmware:** `DN2mod_v0.30.1_AMDFIX_OS1.11.syx`, sha256 `fa681de7a6a9815ded7dc9492fa70e6f6d0b1d8bdb08ad15ef4a0bbcc97ed03f` (the published file's)
- **USB upgrade buffer:** 2,050,805 of 2,097,152 bytes, 46,347 free
- **What it brought:**
  - Hotfix on v0.30: PERC's AMD no longer silences everything until a reboot (the sine it reads is loaded again)
- **For us:** Before our series (it starts on v0.43).

## v0.30 · FIXES

- **Released:** 2026-10-28
- **Commit:** source commit `50dddae5` (no tag)
- **Firmware:** `DN2mod_v0.30_FIXES_OS1.11.syx`, sha256 `55f56c0145eb64d188a076ded6855bbe5c9c0da29854f4decfe98d91773d16e2` (the published file's)
- **USB upgrade buffer:** 2,050,704 of 2,097,152 bytes, 46,448 free
- **What it brought:**
  - Stock Y/N questions (the OS update, the save) answered on every page
  - TRIG + YES is stock's
  - MACHINE SEL keeps SAMP between sample machines
  - the slice marker follows the track's voice
  - LFO depth on SAMP/SLCE
  - and more (FIRMWARE.md)
- **For us:** Before our series (it starts on v0.43).

## v0.29 · VOICES

- **Released:** 2026-10-28
- **Commit:** source commit `9b747fb` (no tag)
- **Firmware:** `DN2mod_v0.29_VOICES_OS1.11.syx`, sha256 `a2a37dd753caffef09b288336384df7c21715e8470712ab3a262013dff6e35f0` (the published file's)
- **USB upgrade buffer:** 2,049,593 of 2,097,152 bytes, 47,559 free
- **What it brought:**
  - Voices play newest first (PERC past 8 voices, Monomachine dead notes under dynamic allocation)
  - a finished Monomachine voice frees its DSP time (the third track silent)
  - multi-select and SELECT ALL/DELETE in the folder browser
  - CLEAR SLICE GRID
  - YES answers the save question on a SLICE/GRID page
- **For us:** Before our series (it starts on v0.43).

## v0.28 · MNM

- **Released:** 2026-10-28
- **Commit:** source commit `2395702` (no tag)
- **Firmware:** `DN2mod_v0.28_MNM_OS1.11.syx`, sha256 `5c4f69fde4008f118b626f4f7f4fa7f4f51de6f538e0812d002aa81e5a057215` (the published file's)
- **USB upgrade buffer:** 2,046,260 of 2,097,152 bytes, 50,892 free
- **What it brought:**
  - The Monomachine machines drawn as the Monomachine's (animated controls), their choice knobs with detents, each machine its own level
  - SHIFT and GRAN removed
  - KEYBOARD's first press of a new slice plays only that slice
- **For us:** Before our series (it starts on v0.43).

## v0.27 · GUARD

- **Released:** 2026-10-27
- **Commit:** source commit `4f25038` (no tag)
- **Firmware:** `DN2mod_v0.27_GUARD_OS1.11.syx`, sha256 `6e5acd44434c7c603318cc02dbbdfd5a69e576cc9600ae3295de90cf8b30c2e5` (the published file's)
- **USB upgrade buffer:** 2,049,189 of 2,097,152 bytes, 47,963 free
- **What it brought:**
  - v0.26 and MNM-1 merged into one line (the five Monomachine machines, without CZ/RESONATOR)
  - the DSP frame-time guard against the audio dropout
  - TRACK + PLAY no longer opens the sample list
  - FILE NAME arrows repeat
  - slice editor moves with FUNC held
  - and more (FIRMWARE.md)
- **For us:** Before our series (it starts on v0.43).

## v0.26 · SLICES

- **Released:** 2026-10-26
- **Commit:** source commit `b752ec4` (no tag)
- **Firmware:** `DN2mod_v0.26_SLICES_OS1.11.syx`, sha256 `4ad096d1aa153063241fef58c8720f2742c54d786fd236995ec03b5e2b745626` (the published file's)
- **USB upgrade buffer:** 2,020,101 of 2,097,152 bytes, 77,051 free
- **What it brought:**
  - The slice editor as the DT2's (FUNC + RIGHT splits, FUNC + LEFT removes, FUNC + YES previews, FUNC + G moves, playhead)
  - KEYBOARD plays slices in order
  - no pop-ups (sample list, slice menus)
  - PLAY/MODE/BARS/GRID four detents a choice
  - browser NO closes
  - name screen FUNC + PLAY clears, grid wraps, cursor moves on
- **For us:** Before our series (it starts on v0.43).

## MNM-1 · MONOMACHINE

- **Released:** 2026-10-26
- **Commit:** no tag, no source commit recorded
- **Firmware:** `DN2mod_MNM-1_MONOMACHINE_OS1.11.syx`, sha256 `daa47def96b036fdd3aeeef66504daf17a0399349c46f765aa395e6d50e37273` (the published file's)
- **USB upgrade buffer:** 2,047,775 of 2,097,152 bytes, 49,377 free
- **What it brought:**
  - A separate line: v0.25 without CZ/RESONATOR, plus the Monomachine's SID 6581, DPRO Wave, DPRO Ddrw, DPRO Dens and VO-6
- **For us:** Before our series (it starts on v0.43).

## v0.25 · BROWSER

- **Released:** 2026-10-26
- **Commit:** source commit `ba3347c` (no tag)
- **Firmware:** `DN2mod_v0.25_BROWSER_OS1.11.syx`, sha256 `bf838003ef8beb29f5903cd5a67f59cae4f6bfebead35ac11877b19cfc2a7f9a` (the published file's)
- **USB upgrade buffer:** 2,019,596 of 2,097,152 bytes, 77,556 free
- **What it brought:**
  - The playhead on the waveform
  - the DT2's sample list and +Drive-style folder browser (SAMPLE ACTION: load, rename, delete)
  - the recorder as the DT2's (RECORDING, NORMALIZING, TRIM with preview, FILE NAME, ASSIGN)
  - GRID/SLICE slice locks
  - KEYBOARD's next 16 slices
  - and more (FIRMWARE.md)
- **For us:** Before our series (it starts on v0.43).

## v0.24 · PI

- **Released:** 2026-10-25
- **Commit:** source commit `7589d67` (no tag)
- **Firmware:** `DN2mod_v0.24_PI_OS1.11.syx`, sha256 `f5853cdb5947204c5ada072f96ea02eb1890a015a2bc151a697b0fe67401d78c` (the published file's)
- **USB upgrade buffer:** 2,013,940 of 2,097,152 bytes, 83,212 free
- **What it brought:**
  - The Machinedrum's nine P-I machines on PERC (PI-BD, SD, MT, ML, MA, RS, RC, CC, HH) from your MD firmware, +6 dB
  - the first hit after choosing an MD machine is now the MD's own
- **For us:** Before our series (it starts on v0.43).

## v0.23 · SLICE

- **Released:** 2026-10-24
- **Commit:** source commit `2f63d3e` (no tag)
- **Firmware:** `DN2mod_v0.23_SLICE_OS1.11.syx`, sha256 `d3468486559f4ad14c378a8b99d875b06ee2be31dde4c6cd69da37d97cc1c5ee` (the published file's)
- **USB upgrade buffer:** 1,999,901 of 2,097,152 bytes, 97,251 free
- **What it brought:**
  - SLICE's own menus (YES: EDIT SLICE POINTS, CREATE SLICE GRID with SLICES 2-64 and TR.DET), the slice editor, SLICES on the trig keys (KEYBOARD, SLCE NOTE)
  - a sample with no slices plays whole
- **For us:** Before our series (it starts on v0.43).

## v0.22 · RECORDER

- **Released:** 2026-10-24
- **Commit:** source commit `e6810ac` (no tag)
- **Firmware:** `DN2mod_v0.22_RECORDER_OS1.11.syx`, sha256 `accc18df58ef54348933a9830d9e9310e4bef521dcd33339fcb8ccf7ed718f94` (the published file's)
- **USB upgrade buffer:** 1,995,356 of 2,097,152 bytes, 101,796 free
- **What it brought:**
  - The RECORDER is its own screen (FUNC + VOICE) with the DT2's TRIM, NAME and ASSIGN steps
  - recordings to any slot
  - 400 MB for samples (after a RAM check at power-on)
  - MD machines +6 dB
  - a browser import tool
  - ONESHOT never goes silent at LEN 0
- **For us:** Before our series (it starts on v0.43).

## v0.21 · KNOBS

- **Released:** 2026-10-23
- **Commit:** source commit `8e3e5e7` (no tag)
- **Firmware:** `DN2mod_v0.21_KNOBS_OS1.11.syx`, sha256 `173948455e1a7668ab0797403e1eb7923dfb69f437ddf8d1c744f9201cfa4094` (the published file's)
- **USB upgrade buffer:** 1,991,417 of 2,097,152 bytes, 105,735 free
- **What it brought:**
  - RESONATOR and CZ PHASE page 1 in the Elektron style: knobs for continuous controls, choices (WAVE, SEL, OCT, MOD, KF, SUS) by name in a box
- **For us:** Before our series (it starts on v0.43).

## v0.20 · FIXES

- **Released:** 2026-10-23
- **Commit:** source commit `61be36e` (no tag)
- **Firmware:** `DN2mod_v0.20_FIXES_OS1.11.syx`, sha256 `e87c23626cc794547e65275176ae7f6cc914d73d86a086a09fa33d717641eb8f` (the published file's)
- **USB upgrade buffer:** 1,991,619 of 2,097,152 bytes, 105,533 free
- **What it brought:**
  - Fixes: the buzz on WaveTone/FM after a sample or PERC track (the link no longer touches the DSP's per-track routing), the RECORDER's flashing, SLICE's pages, the sample list
  - PERC drawn as the Machinedrum's screen
  - sample pages in the DT2's own geometry
- **For us:** Before our series (it starts on v0.43).

## v0.19 · SLICE

- **Released:** 2026-10-23
- **Commit:** source commit `de12fa5` (no tag)
- **Firmware:** `DN2mod_v0.19_SLICE_OS1.11.syx`, sha256 `5bf20c2e9b2d602dd0fd122be459fa43983bfc7904793834b817d401cfd1cf1e` (the published file's)
- **USB upgrade buffer:** 1,988,690 of 2,097,152 bytes, 108,462 free
- **What it brought:**
  - SLICE, the Digitakt II's sixth sample machine: your WAV's cue points (or a grid, or its hits) as up to 64 slices, SLCE / LEN / NOTE mode, slices marked on the waveform
- **For us:** Before our series (it starts on v0.43).

## v0.18 · DT2-ENGINE

- **Released:** 2026-10-23
- **Commit:** source commit `cbf5a1a` (no tag)
- **Firmware:** `DN2mod_v0.18_DT2-ENGINE_OS1.11.syx`, sha256 `8ef50012e8dd0936c93ec5bb504583ca7c53830647ce45a0883d795abb8e6576` (the published file's)
- **USB upgrade buffer:** 1,987,983 of 2,097,152 bytes, 109,169 free
- **What it brought:**
  - The Digitakt II's own sample engine: its interpolator and decimator, its STRETCH, WERP's clock, GRID NOTE mode, BARS 1-8 and SEG 1/32-1/8, no clicks at starts, ends and retriggers
- **For us:** Before our series (it starts on v0.43).

## v0.17 · MACHINEDRUM

- **Released:** 2026-10-22
- **Commit:** source commit `f98caa6` (no tag)
- **Firmware:** `DN2mod_v0.17_MACHINEDRUM_OS1.11.syx`, sha256 `9803119ed145485d8b5c9e1067eaec366b4bb24a8d08128f85634e5936cb878c` (the published file's)
- **USB upgrade buffer:** 1,982,125 of 2,097,152 bytes, 115,027 free
- **What it brought:**
  - PERC is the Machinedrum: its 25 TRX/EFM/GND machines from the MD's own firmware (every reference case matches), TYPE p-lockable as before
- **For us:** Before our series (it starts on v0.43).

## v0.16 · DRIVE

- **Released:** 2026-10-22
- **Commit:** source commit `b502e6d` (no tag)
- **Firmware:** `DN2mod_v0.16_DRIVE_OS1.11.syx`, sha256 `98da318511036ff8acf8349f8f0d83c7052f35270a75774aa8570f0dd665af29` (the published file's)
- **USB upgrade buffer:** 1,961,622 of 2,097,152 bytes, 135,530 free
- **What it brought:**
  - 96 MB of your samples on the +Drive, loaded at power-on over a fast checked link
  - recordings kept after power-off
  - the SAMP name list
  - waveforms for every slot
- **For us:** Before our series (it starts on v0.43).

## v0.15 · RECORDER

- **Released:** 2026-10-22
- **Commit:** source commit `6032b50` (no tag)
- **Firmware:** `DN2mod_v0.15_RECORDER_OS1.11.syx`, sha256 `ac54c048b93474ed8f0bd12abd07966b8589400710de75150f9c59c535df2edf` (the published file's)
- **USB upgrade buffer:** 1,957,986 of 2,097,152 bytes, 139,166 free
- **What it brought:**
  - DT2 SRC pages (knobs, waveform, RECORDER), one encoder click a choice, value names in the header, loops follow the knobs live
  - RECORDER: SRC IN/MAIN/TRK1-16, CHAN, YES records, ARM, R.LEN, R.STRT
- **For us:** Before our series (it starts on v0.43).

## v0.14 · SAMPLING

- **Released:** 2026-10-22
- **Commit:** source commit `eb06398` (no tag)
- **Firmware:** `DN2mod_v0.14_SAMPLING_OS1.11.syx`, sha256 `fd3253d66e16cd72c9ec7dc47e9b149820464a99588333b9cb134fe2beb0ac25` (the published file's)
- **USB upgrade buffer:** 1,955,057 of 2,097,152 bytes, 142,095 free
- **What it brought:**
  - Sampling: page 2 of every sample machine records IN / IN L / IN R / MAIN into SAMP 124-127 (threshold, length)
  - ONESHOT's CFAD heard
- **For us:** Before our series (it starts on v0.43).

## v0.13 · SAMPLER

- **Released:** 2026-10-22
- **Commit:** source commit `602ee63` (no tag)
- **Firmware:** `DN2mod_v0.13_SAMPLER_OS1.11.syx`, sha256 `ae5637c4b5a04661179d7d36d1619901662958c0fa788f2328a7c0f659c61fdb` (the published file's)
- **USB upgrade buffer:** 1,953,542 of 2,097,152 bytes, 143,610 free
- **What it brought:**
  - The Digitakt II's sample machines (ONESHOT, WERP, STRETCH, REPITCH, GRID) with DT2-style pages
  - four test sounds
  - your WAVs over USB, kept on the +Drive
- **For us:** Before our series (it starts on v0.43).

## v0.12 · PERC-FX

- **Released:** 2026-10-21
- **Commit:** source commit `0c682bf` (no tag)
- **Firmware:** `DN2mod_v0.12_PERC-FX_OS1.11.syx`, sha256 `c441b07c26e42a31b77ac3c366724fba7a7c84b5f7fa11ffab410b14a26dbb79` (the published file's)
- **USB upgrade buffer:** 1,915,364 of 2,097,152 bytes, 181,788 free
- **What it brought:**
  - PERC: labels follow TYPE
  - page 1 the machine's 8 parameters
  - page 2 TYPE + Machinedrum effects (AMD AMF EQF EQG FLTF FLTW FLTQ)
  - no stray ring
- **For us:** Before our series (it starts on v0.43).

## v0.11 · PERC

- **Released:** 2026-10-20
- **Commit:** source commit `5ff5e05` (no tag)
- **Firmware:** `DN2mod_v0.11_PERC_OS1.11.syx`, sha256 `9e44b90562348210be34a8edb549599b35306795a94507e5db6ddf340764f13d` (the published file's)
- **USB upgrade buffer:** 1,914,556 of 2,097,152 bytes, 182,596 free
- **What it brought:**
  - PERC: your 24 Ravel drum machines (TRX/EFM/GND) as a machine, TYPE + 8 named parameters
  - Waverider removed
- **For us:** Before our series (it starts on v0.43).

## v0.10 · GRAN

- **Released:** 2026-10-20
- **Commit:** source commit `456d4b9` (no tag)
- **Firmware:** `DN2mod_v0.10_GRAN_OS1.11.syx`, sha256 `fb18ef71eda483bd0592b145fd6b567b340c0317cc8c092fcf52b88ce8400910` (the published file's)
- **USB upgrade buffer:** 2,080,802 of 2,097,152 bytes, 16,350 free
- **What it brought:**
  - No more dead notes on RESONATOR/CZ (voice stealing)
  - PING/SHFT TYPE by name
  - Waverider osc 2 (page 2)
  - GRAN granular filter type
- **For us:** Before our series (it starts on v0.43).

## v0.9 · CZ-release

- **Released:** 2026-10-19
- **Commit:** source commit `b782505` (no tag)
- **Firmware:** `DN2mod_v0.9_CZ-release_OS1.11.syx`, sha256 `850bd00abd6f9f84c112e7ac7d6681339bdcb9e2542286337357e9f7c4a51c2d` (the published file's)
- **USB upgrade buffer:** 2,076,863 of 2,097,152 bytes, 20,289 free
- **What it brought:**
  - CZ's release: the DCW envelope runs on past its sustain step at note-off, as on a real CZ
- **For us:** Before our series (it starts on v0.43).

## v0.8 · CZ

- **Released:** 2026-10-18
- **Commit:** source commit `89b057b` (no tag)
- **Firmware:** `DN2mod_v0.8_CZ_OS1.11.syx`, sha256 `5301fb4169f9d5f97c35109a15216c847e69106b56e06dc571ca4f6562fdf897` (the published file's)
- **USB upgrade buffer:** 2,076,863 of 2,097,152 bytes, 20,289 free
- **What it brought:**
  - Everything in v0.7 (CZ PHASE, RESONATOR, SHIFT, PING, Waverider), sized to fit the USB upgrade: Waverider has 9 tables (BITS, PHAS out)
- **For us:** Before our series (it starts on v0.43).

## v0.7 · CZ

- **Released:** 2026-10-18 · **withdrawn**
- **Commit:** source commit `37fd1f4` (no tag)
- **Firmware:** `DN2mod_v0.7_CZ_OS1.11.syx`, sha256 `0751bb0dfab83d4e9d227db7d1f9eb1ce2a1967b0e93d3db40e5901cf56c4527`
- **USB upgrade buffer:** file not on the builds branch (withdrawn or superseded)
- **What it brought:**
  - CZ PHASE machine (Casio CZ phase distortion), 8-step DCW envelope on pages 2–3, up to 6 voices
- **For us:** Before our series (it starts on v0.43).

## v0.6 · RESONATOR

- **Released:** 2026-10-18 · **withdrawn**
- **Commit:** source commit `8e6854e` (no tag)
- **Firmware:** `DN2mod_v0.6_RESONATOR_OS1.11.syx`, sha256 `920ee105803cd1114770b38bdf94b8de325539c73b31371144795d495f5dd847`
- **USB upgrade buffer:** file not on the builds branch (withdrawn or superseded)
- **What it brought:**
  - RESONATOR machine (Rings-style modal resonator), up to 4 voices
- **For us:** Before our series (it starts on v0.43).

## v0.5 · SHIFT

- **Released:** 2026-10-18 · **withdrawn**
- **Commit:** source commit `be8d0ad` (no tag)
- **Firmware:** `DN2mod_v0.5_SHIFT_OS1.11.syx`, sha256 `1ff987df0d6dd8ef3ed718682bf9e899b1f9af2fe8b71995c29d66a63e315e98`
- **USB upgrade buffer:** file not on the builds branch (withdrawn or superseded)
- **What it brought:**
  - SHIFT filter type (frequency shifter) beside PING
  - DSP memory packed tighter
- **For us:** Before our series (it starts on v0.43).

## v0.4 · PING

- **Released:** 2026-10-13 · **withdrawn**
- **Commit:** source commit `43e4d58` (no tag)
- **Firmware:** `DN2mod_v0.4_PING-filter_OS1.11.syx`, sha256 `86fc590931251776b14b7bad075336177f5b20aca60fc6c8bf557ec892d427dc`
- **USB upgrade buffer:** file not on the builds branch (withdrawn or superseded)
- **What it brought:**
  - PING filter type (SVF / LADR / VCFQ / LPG) on the FLTR page, any machine
- **For us:** Before our series (it starts on v0.43).

## v0.3 · Waverider-W2

- **Released:** 2026-10-11
- **Commit:** source commit `3514819` (no tag)
- **Firmware:** `DN2mod_v0.3_Waverider-W2_OS1.11.syx`, sha256 `8cd7236c2e84b8e931174b91c99f16393cd899b6bcd602ea6de044ffee194da0` (the published file's)
- **USB upgrade buffer:** 2,095,952 of 2,097,152 bytes, 1,200 free
- **What it brought:**
  - Waverider W2: all page-1 controls, built-in scanner, its names in the LFO lists
- **For us:** Before our series (it starts on v0.43).

## v0.2 · Waverider

- **Released:** 2026-10-11
- **Commit:** no tag, no source commit recorded
- **Firmware:** none published
- **USB upgrade buffer:** no published file
- **What it brought:**
  - Waverider W5: 11 tables, POS glide, display that follows the sound
- **For us:** Before our series (it starts on v0.43).

## v0.1 · Waverider

- **Released:** 2026-10-06
- **Commit:** no tag, no source commit recorded
- **Firmware:** none published
- **USB upgrade buffer:** no published file
- **What it brought:**
  - Waverider: a wavetable machine in MACHINE SEL
- **For us:** Before our series (it starts on v0.43).
