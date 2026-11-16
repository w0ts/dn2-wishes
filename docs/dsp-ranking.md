# DSP targets ranked by cycles per frame in typical use (stock and ours together)

Sources: `~/GitHub/dn2mk2-scratch/combined/stock-hotspots.md` (stockhot session: stock 1.12 profile, addresses and
cycle counts only, no Elektron code or bytes), `combined/budget-table.md` (budget session, combined build before
the perf commits), `docs/dsp-perf.md` (this branch). Runner clock (instr + 0.9 x (4 L2 + 10 DDR)), frame 666,667;
the unit reads about 10 % above the runner on a silent frame, DDR-bound items maybe more.

**Typical use assumed (stated so it can be argued with):** 8 of 16 tracks sounding, one machine type, 4 tracks with
one insert (pre or CHOR), A2 filter on 2 tracks, FDN8 + XDLY on the sends. Cycles per frame = per call x calls x
how often active.

| # | target | owner | cycles per frame, typical | can we bypass / skip / replace from our side, what it gains |
|--:|---|---|---:|---|
| 1 | **A2 filter pass** (SVF 157k, MS20 158k, LADR 168k, OTA 177k, DIODE 242k; flat 1 voice or 16) | ours (ports) | 157-242k whenever any track uses one | **Replace**: hand-written SHARC, state in L1, skip empty slots. 2 filtered voices of 16 = 1/8 of the slot work: -130..-200k before any asm; asm 3x on top. Bit-exact to the model where kept. |
| 2 | **Synth voices x 8**: TB303 280-360k, PI-SD/RS 181k (after this branch), PLAITS PART/STRG/MDAL 140-170k, EFM/TRX 80-120k, stock FM TONE 119k, WAVETONE 76k | ours + stock | 76-360k | ours: **replace** (SSF fixed point done for MD; TB303 next, est -25..-35 %; PLAITS poly16's). Stock FM/WT: **skip** idle voices (sound-changing at the edges, listening note), 14.9k/9.5k each. |
| 3 | **Stock send FX** (chorus 61k stays; reverb 85k, delay 29k replaced by FDN8 / XDLY when selected) | stock | 175k at idle, flat | reverb/delay **already bypassed** by our slots; chorus: **skip while cold** (bit-exact only until it has been used; a detector+clear is a declared sound-neutral change): up to -61k. |
| 4 | **Our FDN8 send 42k + XDLY 16k idle**, bus FDN8 33k / XDLY 9k per instance | ours | 58k idle, up to 260k with 8+4 bus inserts | **Skip** on zero input and dead tail (flag): -40k idle; bus passes with all slots OFF now cost ~0.4k (done, `9f692b8c`). |
| 5 | **Stock track buffers in DDR** (87.7k of the dispatch) | stock | 88k | **Replace** (done by stockhot, not by me: `10e0c57a`/`3831c8c7`, bit-exact, -107.9k on a busy mix; not merged here). |
| 6 | **Stock chain for empty/MIDI tracks** (9.2k a track, 3.7k once #5 is in) | stock | 8 x 9.2k = 74k (30k after #5) | **Skip** for tracks that never sounded: bit-exact, but `0x1c8ef1` decode not yet reliable (stockhot: selmap off-boundary). Needs a decoder first. |
| 7 | **CHOR post insert** (17.7k a voice, 2 slots 562k max) x 4 tracks | ours | 71k | **Replace**: state in registers, L1 lines, SIMD L/R; or one CHOR per track bus. -25..-45 %. |
| 8 | **Stock dispatch skeleton** `0x1c8ef1` 39k (15k instr + buffer moves) | stock | 39k | partly #5; the rest needs the decode. |
| 9 | **Pre inserts** (FUZZ 7.1k, TAPE 8.1k, DIST 7.2k, FOLD 6.2k a voice) x 4 | ours | 25-32k | constants to registers, short walk list: -30 %. |
| 10 | **Stock routing** 29k, output + Overbridge packing 18k | stock | 47k | **Skip** silent tracks (routing), Overbridge packing only while streaming: bit-exact on the main out; both need the decode first. |
| 11 | **Resampler** 1.1k a voice x 8 | ours | 9k | near its floor; multifunction blocked by selmap/digikit decode. |
| 12 | **Stock send mixing** 10.2k, unpack 6.5k | stock | 17k | skip gain-0 tracks: bit-exact, low value. |

Done and verified on this branch (before/after in `docs/dsp-perf.md`): MD fixed-point products (EFM/TRX -23..-44 %),
P-I scratch in L1 (PI-SD/RS -46 %), insert-pass walk skip (idle CHOR/WIDE/bus passes ~25k -> ~0.4k).

Work order from this table: #1 (A2 filters), then #2 TB303, #4 FDN8/XDLY idle gate, #7 CHOR, #9 pre inserts; the stock
items #3, #6, #8, #10, #12 wait for a decoder whose instruction boundaries agree with every executed pc
(digikit `sharcdb`; stockhot found selmap off-boundary on `0x1c1738`, `0x1c1f1e`, `0x1c8ef1`) and are the stockhot
session's patches on the stock path, not mine, unless main moves them.
