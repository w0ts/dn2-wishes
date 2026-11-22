"""AMP ON/OFF for the drum machines (2026-11-20, the User; csrc/msel/ampsw.c, docs/live-select.md "AMP ON/OFF").

On stock's AMP page, VOL's place becomes AMP ON/OFF on the drum machines. OFF (the default) bypasses stock's AMP
envelope and VOL in the DSP: the voice leaves the chain exactly as it reached the AMP stage (gain 1.0 bit for bit).
ON is stock's AMP and VOL as usual. Every other machine keeps VOL as stock.

Which machines are drums is one table here, by machine NAME, so a drum machine added later gets it once it is in
the build: DRUM_NAMES (our Monomachine-style modules), MACHINEDRUM (PERC, type 5), and PLAITS on one of its drum
models (PLAITS_DRUM_MODELS, by MODL's record value: the DSP's choice, dnfw.engines.plaits.dsp_model).

The setting is a field of the sound's wishes record (TAG, one byte, 1 = ON). OFF is no field: an old sound, a preset
and every new sound read OFF.

The DSP half (DSP: `asm_text`, its two hooks in sw 0x1c8ef1 placed by dnfw.waverider.dsp): the ColdFire sends one
word, MAGIC | a bit per track whose sound is a drum with AMP OFF (csrc/msel/ampsw.c as_poll, csrc/sampler/link.c),
to the pool's READY page (POOL_OFF). Hook A, before the per-slot AMP loop (sw 0x1c99b4), points the entry of the
chain's buffer table of each voice slot playing such a track (the slot map ROUTE, as the frame carries it) at a scratch
buffer of ours (DUMMY); stock's AMP stage and VOL's loop then run as stock (their state moves on as stock's) on the
scratch; hook B, after VOL's loop (sw 0x1c9a3a), puts the table back from its copy (TABLE_COPY). The slot's buffer is
untouched from the AMP stage's call to the end of VOL's loop. Which slots: by the slot's track (the track's own sound
decides); a voice on a sound lock plays its track's setting (docs/live-select.md: known limit).
"""
from __future__ import annotations

PERC_TYPE = 5                                   # MACHINEDRUM (dnfw.perc.program.MACHINE_TYPE)
DRUM_NAMES = ("SOPHIE", "DRUM")                 # our drum machines by module NAME (DRUM: when the build has it)
PLAITS_NAME = "PLAITS"
PLAITS_DRUM_MODELS = ("BD", "SD", "HH")

TAG = 0x0014                                    # csrc/wishes/wish.h WT_AMP_SW: 1 byte, 1 = ON; no field = OFF
ON = 1
VOL_REC = 72                                    # the place AMP takes on stock's AMP page: VOL (record 72, place H)
VOL_PLACE = 7

# the ColdFire -> DSP word: in the pool's READY page after the mixer meters' LV_WANT word (dnfw.sampler.machines;
# K_READY zeroes that page at every boot, so the word is sent after it, csrc/sampler/link.c)
MAGIC = 0x414D0000                              # 'AM' in the high half; the low half the tracks' OFF bits


def pool_off() -> int:
    from ..sampler import machines as SM
    off = SM.LV_WANT_OFF + 4
    assert off < SM.TABLE_READY + 512
    return off


# -- the DSP's hooks (sw 0x1c8ef1, Elektron's per-slot chain; docs/live-select.md) -----------------------------------
SITE_A_SW = 0x1C99B4                            # R15 = DM(I6 - 33); I5 = DM(I6 - 24): before the AMP loop (sw 0x1c99bf)
SITE_A_DISPLACED = ("R15 = DM(-33, I6);", "I5 = DM(-24, I6);")
SITE_A_RESUME = 0x1C99B8
SITE_B_SW = 0x1C9A3A                            # R1 = 0x4f800000: after VOL's loop (sw 0x1c99ed .. 0x1c9a31)
SITE_B_DISPLACED = "R1 = 0x4f800000;"
SITE_B_RESUME = 0x1C9A3D
ROUTE = 0x257898                                # the slot map: halfword s = the track slot s plays (frame 0xa5a + 2 s)

# the code in L2's gap after PI-RS's strike table, before fdn8.asm (test/test_dsp_claims.py), 128 B of NOPs after it;
# the data in L1 (F2's tail, 0x2E1B40..0x2E1C00)
CODE_L2_LOAD, CODE_SPAN = 0x200A9C90, 0x200AA000 - 0x200A9C90
CODE_SW = 0xB80000 + (CODE_L2_LOAD - 0x20000000) // 2
DATA_DM = 0x2E1B40
SV = DATA_DM                                    # 4 words: hook A's saved registers
SV_B = DATA_DM + 0x10                           # 3 words: hook B's
SV_ASTAT = DATA_DM + 0x20
DUMMY = DATA_DM + 0x40                          # 32 floats: the AMP stage's and VOL's output for a bypassed slot
END = DUMMY + 0x80
assert END == 0x2E1C00
TABLE_COPY = 0x257EA8                           # the chain's buffer table's copy (trackbuf.asm: both hold the same)
ENTRY_B_SW = CODE_SW                            # hook B is the object's start; hook A's entry: its label wr_asw_a


def drum_types() -> list[int]:
    """the machine types that are drum machines in this build (PLAITS apart: by its model)"""
    from ..mnm import machines as MM
    built = dict(zip((M.NAME for M in MM.MODULES), MM.TYPE_SLOTS))
    return [PERC_TYPE] + sorted(t for n, t in built.items() if n in DRUM_NAMES)


def plaits() -> tuple[int, int, int, int, int] | None:
    """-> (PLAITS' type, MODL's slot, its record's lo, the lowest and highest record value on a drum model), or None
    without PLAITS. MODL's value v = (word >> 8) - lo plays dsp_model(v); the drum models are one run at its top."""
    from ..engines.plaits import plaits as P
    from ..mnm import machines as MM
    from ..perc import machines as PM
    built = dict(zip((M.NAME for M in MM.MODULES), MM.TYPE_SLOTS))
    if PLAITS_NAME not in built:
        return None
    _rid, slot, lo, top = PM.PARAMS[P.MODL_K]
    drums = {P.MODELS.index(m) for m in PLAITS_DRUM_MODELS}
    vals = [v for v in range(top + 1) if P.dsp_model(v) in drums]
    assert vals == list(range(vals[0], top + 1)), "PLAITS' drum models: one run of MODL's values, at its top"
    assert all(P.model_of(int(v / top * 127 + 0.5)) in drums for v in vals), "the page shows a drum model there too"
    assert P.model_of(int((vals[0] - 1) / top * 127 + 0.5)) not in drums
    return built[PLAITS_NAME], slot, lo, vals[0], vals[-1]


def is_drum(mtype: int, modl_word: int) -> bool:
    """the model of csrc/msel/ampsw.c as_drum: MTYPE a drum machine (PLAITS by its MODL word)"""
    if mtype in drum_types():
        return True
    pl = plaits()
    if pl and mtype == pl[0]:
        return pl[3] <= (modl_word >> 8) - pl[2] <= pl[4]
    return False


def c_header() -> str:
    types = drum_types()
    pl = plaits() or (-1, 0, 0, 1, 0)
    out = ["/* AMP ON/OFF for the drum machines (dnfw.waverider.ampsw) */",
           f"#define AS_TYPES {', '.join(map(str, types))}", f"#define AS_NTYPES {len(types)}",
           f"#define AS_PLAITS {pl[0]}", f"#define AS_MODL_SLOT {pl[1]}", f"#define AS_MODL_LO {pl[2]}",
           f"#define AS_MODL_DRUM_MIN {pl[3]}", f"#define AS_MODL_DRUM_MAX {pl[4]}",
           f"#define AS_ON {ON}", f"#define AS_VOL_REC {VOL_REC}u",
           f"#define AS_VOL_PLACE {VOL_PLACE}"]          # (AS_MAGIC, AS_POOL_OFF: cpage.py's defines, link.c's too)
    return "\n".join(out) + "\n"


def asm_text() -> str:
    """csrc/waverider/sharc/ampsw.asm (scripts/gen_ampsw_asm.py), its jump targets left for sharc_resolve_jumps.
    Small on purpose: every byte is the DSP upload's (docs/dsp-room.md). Hook A uses R1, R2, R14, R15, I5 and the
    flags unsaved: stock writes each after the site before it reads it (R15 and I5 by the displaced loads, R14 and R2
    by the next instructions, R1 at the loop's top after R4 = PASS R15 set the flags)"""
    from ..waverider import dsp
    pool = dsp.SMP_POOL_DDR + pool_off()
    o = ["// ampsw.asm -- AMP ON/OFF for the drum machines (dnfw.waverider.ampsw, docs/live-select.md). GENERATED by",
         "// scripts/gen_ampsw_asm.py from dnfw.waverider.ampsw; do not edit by hand.",
         "//",
         "// Two hooks in Elektron's per-slot chain (sw 0x1c8ef1). A (sw 0x1c99b4, before the AMP loop): each slot whose",
         "// track (the slot map ROUTE) has its bit in the ColdFire's word (MAGIC | the tracks whose sound is a drum with AMP",
         "// OFF): its entry of the chain's buffer table -> DUMMY. B (sw 0x1c9a3a, after VOL's loop): the table back from",
         "// its copy (TABLE_COPY, the same 16 addresses: engine init copies it, trackbuf.asm writes both). Stock's AMP",
         "// stage and VOL run as stock on DUMMY: the slot's own buffer leaves the chain as it reached the AMP stage.",
         "",
         ".SECTION/PM seg_pmco;",
         "",
         ".GLOBAL wr_asw_b.;",
         "wr_asw_b.:",
         f"      DM({SV_ASTAT:#x}) = ASTAT;        // (the CALL after the site reads the flags float() set)",
         f"      DM({SV_B:#x}) = R2;",
         f"      DM({SV_B + 4:#x}) = I0;",
         f"      DM({SV_B + 8:#x}) = I1;",
         f"      I0 = {TABLE_COPY:#x};",
         "      I1 = DM(-24, I6);                 // the chain's buffer table",
         "      R1 = 0x10;                        // (R1: the displaced instruction sets it after)",
         ".GLOBAL wr_asw_bslot.;",
         "wr_asw_bslot.:",
         "      R2 = DM(I0, M6);",
         "      DM(I1, M6) = R2;",
         "      R1 = R1 - 1;",
         "      IF NE JUMP 0x0;                   // -> wr_asw_bslot.",
         f"      R2 = DM({SV_B:#x});",
         f"      I0 = DM({SV_B + 4:#x});",
         f"      I1 = DM({SV_B + 8:#x});",
         f"      ASTAT = DM({SV_ASTAT:#x});",
         f"      {SITE_B_DISPLACED}                // the instruction the JUMP took the place of",
         f"      JUMP {SITE_B_RESUME:#x};",
         "",
         ".GLOBAL wr_asw_a.;",
         "wr_asw_a.:",
         f"      I5 = {SV:#x};",
         "      DM(0, I5) = R3;",
         "      DM(1, I5) = R5;",
         f"      DM({SV + 2:#x}) = I0;",           # (absolute: a DAG1 register is never stored through I5, DAG1 too:
         f"      DM({SV + 3:#x}) = I1;",           #  PRM types 3/15, hwrules DAG-SAME)
         f"      R14 = DM({pool:#x});               // the ColdFire's word",
         "      R1 = LSHIFT R14 BY -16;",
         f"      R2 = {MAGIC >> 16:#x};",
         "      COMP(R1, R2);",
         "      IF NE R14 = R14 - R14;            // (no word yet: nothing)",
         "      R2 = 0xffff;",
         "      R14 = R14 AND R2;",
         "      IF EQ JUMP 0x0;                   // -> wr_asw_aout.",
         f"      I0 = {ROUTE:#x};",
         "      I1 = DM(-24, I6);                 // the chain's buffer table",
         f"      R3 = {DUMMY:#x};",
         "      R5 = 0x1;",
         "      R15 = 0x8;",
         ".GLOBAL wr_asw_pair.;",
         "wr_asw_pair.:",
         "      R1 = DM(I0, M6);                  // two slots' tracks: the shift takes the low 8 bits"]
    for half in (0, 1):
        if half:
            o += ["      R1 = LSHIFT R1 BY -16;"]
        o += ["      R2 = LSHIFT R5 BY R1;",
              "      R2 = R2 AND R14;                  // the track's bit",
              "      R2 = DM(0, I1);",
              "      IF NE R2 = PASS R3;",
              "      DM(I1, M6) = R2;"]
    o += ["      R15 = R15 - 1;",
          "      IF NE JUMP 0x0;                   // -> wr_asw_pair.",
          ".GLOBAL wr_asw_aout.;",
          "wr_asw_aout.:",
          "      R3 = DM(0, I5);",
          "      R5 = DM(1, I5);",
          "      I0 = DM(2, I5);",
          "      I1 = DM(3, I5);",
          f"      {SITE_A_DISPLACED[0]}               // the two instructions the JUMP took the place of",
          f"      {SITE_A_DISPLACED[1]}",
          f"      JUMP {SITE_A_RESUME:#x};",
          ".wr_asw_b..end:",
          "      .type wr_asw_b.,STT_FUNC;"]
    return "\n".join(o) + "\n"
