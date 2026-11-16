# A2 filter machines: cost per voice, 2026-11-11 (branch sophie-v047-os112-a2fperf, off ports 614df38e)

**The 17-36 % of a frame per voice (72-135k instructions) was the pass filtering all 16 slots, before ONE_VOICE.**
With ONE_VOICE (the newest note's voice only) the runner's `a2f` step measures 7,398-8,300 model steps a block
(native profile, one voice, two filters in series, 2 halves x 16 samples: SVF 6,242, LADR 7,398, OTA 7,666,
DIOD 9,014, MS20 6,990 instructions). Lifting ONE_VOICE costs about that per filtered voice (16 voices: 100-145k).

## Done
- `c81690f4`: the pass's state, scratch and mix tables from L2 (0x200b5800, 4 cycles an access, 1,000-1,900
  accesses a voice) to the free 2 KB at the L1 region's start (0x2dd600). Est per voice (instr + 0.9 x 4 x L2):
  SVF 10,252 -> 6,242 (-39 %), LADR 11,271 -> 7,398 (-34 %), OTA 11,770 -> 7,666 (-35 %), DIOD 15,940 -> 9,014
  (-43 %), MS20 10,618 -> 6,990 (-34 %). Bit-exact: output hash of all five models over 400 blocks (2 voices,
  random knobs, trigs) identical to the ports head; runner step `a2f` PASS; preflight, code-fresh, rebuild,
  dsp-identity, hwrules, symbols, coldfire, overbridge PASS on a build of the tree. `test_waverider_dsp.py`
  has 2 failures on the ports head too (ddr spans, inserts hand on to PING), unchanged by this.

## Where the rest goes (SVF, one voice, 6.2k instr)
per-sample loop 2,688 (42 a sample) + knees 576; slot walks and half setup ~800; coefficient setup per half
(g_of, reciprocals) ~700; controls/envelope ~400. The loop is already register-allocated; hoisting constants
and hardware loops would give about 15-25 % bit-exact. A 3x is not reachable by scalar scheduling.

## What blocks the hand-written 3x
Multifunction (multiply || add) and SIMD would roughly halve the float-heavy loops, but the DSL refuses
multifunction computes (`dsl.Prog.par`): selmap reads selas's `Fm = Fx * Fy, Fa = ...` as `Fm = MRF + Fx * Fy`,
digikit as a float multiply, and the silicon's reading is not established. Settling that (against the ADSP-2156x
ISA reference or by finding the same encodings in the stock stream's float loops) is the enabling task for
every float-heavy target (TB303, CHOR, TAPE, PLAITS MDAL). SIMD (MODE1) is untested on the unit.
