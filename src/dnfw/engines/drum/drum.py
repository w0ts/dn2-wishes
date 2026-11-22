"""DRUM: one synth drum machine, its sub type chosen by TYPE on page 1 H (scratch/drum-engine/design.md; docs/drum.md).

Stage 2a (2026-11-20): KICK, end to end; stage 2b: SNARE (snare.py); stage 2c: CLOSED and OPEN HAT (hats.py, CLOSED
chokes OPEN on its track); stage 3: TOM (tom.py) and the re-voicing (scratch/drum-engine/drum_v3.py: KICK's sigh from
the hit's level and SWHD, SNARE's WCHR, the hats' diode knee, TOP and DRFT, the TR-808's levels); stage 4: CLAP
(clap.py), RIDE and CRASH (cymbal.py: one code, two TYPE entries). One DSP voice: `half` runs the type latched at the
trig.

TYPE's eight types (2026-11-20, stage 4) in eight equal spans, (knob x 8) >> 7, ordered so that every value a project
or a preset made with five types holds (each choice's own value: 9, 30, 50, 70, 91 on PERC's 0..100 TYPE record) still
reads as its type: KICK CLAP SNAR CRSH CLHH OPHH RIDE TOM (the new three in the spans no old choice lands in;
test/test_drum_hosts.py).

One voice per track at 44.1 kHz (PERC's stream), 16-sample halves. The engine's arithmetic: dnfw.engines.drum.dmath;
its reference: dnfw.engines.drum.ref (test/test_drum.py holds the two within DSL_TOL_DB).

Parameters (KICK): TUNE DCAY SWEP SWTM CLIK CLKT DRIV TYPE; page 2: SHAP HOLD SIGH CLKL NOIS VEL SWHD CURV.
"""

from __future__ import annotations

from ...mnm import core as C
from ...perc.dsl import Prog
from . import dmath as M
from . import hats as HA
from . import clap as CL
from . import cymbal as CY
from . import kick as KI
from . import ref as R
from . import snare as SN
from . import tom as TO

NAME, ID = "DRUM", 70
PNAMES = ("TUNE", "DCAY", "SWEP", "SWTM", "CLIK", "CLKT", "DRIV", "TYPE")
PNAMES2 = R.Kick.P2                            # SHAP HOLD SIGH CLKL NOIS VEL SWHD CURV
TYPE_K = 7                                     # page 1 H (PERC's eighth record)
TYPES = ("KICK", "CLAP", "SNAR", "CRSH", "CLHH", "OPHH", "RIDE", "TOM")   # the page's four characters, span order
TYPE_TAGS = ("BASS DRUM", "CLAP", "SNARE DRUM", "CRASH", "CLOSED HAT", "OPEN HAT", "RIDE", "TOM")
N_TYPES = len(TYPES)
KICK, CLAP, SNARE, CRSH, CLHH, OPHH, RIDE, TOM = range(N_TYPES)
OLD_TYPES = ("KICK", "SNAR", "CLHH", "OPHH", "TOM")   # TYPE's five types before stage 4 ((knob x 5) >> 7)


def type_of(knob: int) -> int:
    """TYPE's knob (0..127) -> the type, as the page reads a choice: (knob x n) >> 7"""
    return (knob * N_TYPES) >> 7


def type_knob(t: int) -> int:
    """the knob in the middle of type T's span (MACHINE SEL's start, a type's start)"""
    k = ((2 * t + 1) * 128) // (2 * N_TYPES)
    assert type_of(k) == t
    return k


DEFAULTS = tuple(R.Kick.D1[n] for n in PNAMES[:7]) + (type_knob(KICK),)
DEFAULTS2 = tuple(round(R.Kick.D2[n] * 127) for n in PNAMES2)
assert len(PNAMES2) <= 8 and all(n == m for n, m in zip(PNAMES2, R.Kick.P2))


# 2026-11-20 (the User: "own page per type"): each type's page, as the ColdFire's tables hold a machine (its place,
# picked by TYPE as MONOMACHINE's by ENGN: dnfw.mnm.machines HOSTS). NAME is the place's key in the page tables
# (units, choices, long names: "DRUM KICK" ..); HOST the machine. Page 1 H is TYPE on every type; page 2 is
# PERC's seven page-2 records (q0..q6). On the DSP DRUM is ONE voice: the type is read from TYPE in the engine.
LOW, MID, HI = range(3)                        # TOM's RANGE (page 2 D): its three detents
RANGE_ST = R.RNGE_ST                           # semitones each adds to TUNE (the study's 808 toms)
RANGES = ("LOW", "MID", "HI")
COUNTS = tuple(str(n) for n in range(1, R.CLAP_N + 1))       # CLAP's CNT (page 1 D): its bursts
SETS = ("808", "WIDE", "CLST", "LOW")                       # the cymbals' SET (page 2 A): ref.CYM_SETS
assert len(SETS) == len(R.CYM_SETS) and all(a[:2] == b[:2] for a, b in zip(SETS, R.SET_NAMES))


def _place(t: int, p1: tuple, d1: tuple, p2: tuple, d2: tuple):
    """page 2's eighth (H) is PERC's TYPE record: SNARE's WCHR (q7)"""
    assert len(p1) == 7 and len(d1) == 7 and len(p2) == len(d2) <= 8
    return type("Drum" + TYPES[t].title(), (), {
        "NAME": "DRUM " + TYPES[t], "HOST": NAME, "TYPE": t,
        "PNAMES": p1 + ("TYPE",), "DEFAULTS": d1 + (type_knob(t),),
        "PNAMES2": p2, "DEFAULTS2": d2,
    })


PLACES = (
    _place(KICK, PNAMES[:7], tuple(R.Kick.D1[n] for n in PNAMES[:7]), PNAMES2,
           tuple(round(R.Kick.D2[n] * 127) for n in PNAMES2)),
    # SNARE: its start RICH (4th mode, sizzle; the User 2026-11-20)
    _place(SNARE, R.Snare.P1, tuple(R.Snare.D1[n] for n in R.Snare.P1), R.Snare.P2,
           tuple(round(R.Snare.D2[n] * 127) for n in R.Snare.P2)),
    _place(CLHH, ("TUNE", "DCAY", "TONE", "NOIS", "COLR", "SNAP", "DRIV"), (64, 58, 64, 22, 44, 44, 32),
           ("HPF", "Q", "LOWB", "VEL", "TOP", "DRFT"), (64, 44, 0, 64, 0, 64)),
    _place(OPHH, ("TUNE", "DCAY", "TONE", "NOIS", "COLR", "SNAP", "DRIV"), (64, 55, 64, 22, 44, 44, 32),
           ("HPF", "Q", "LOWB", "VEL", "TOP", "DRFT"), (64, 44, 0, 64, 0, 64)),
    # TOM: RANGE LOW / MID / HI (page 2 D, three detents), TUNE's semitones on top; its start the study's 808 MID
    _place(TOM, R.Tom.P1, tuple(R.Tom.D1[n] for n in R.Tom.P1), R.Tom.P2,
           tuple(round(R.Tom.D2[n] * 127) for n in R.Tom.P2)),
    # stage 4: CLAP (its start the 808 point), RIDE and CRASH (one code, their starts drum_v4's)
    _place(CLAP, R.Clap.P1, tuple(R.Clap.D1[n] for n in R.Clap.P1), R.Clap.P2,
           tuple(round(R.Clap.D2[n] * 127) for n in R.Clap.P2)),
    _place(RIDE, R.Cymbal.P1, tuple(R.Cymbal.STARTS["RIDE"][0][n] for n in R.Cymbal.P1), R.Cymbal.P2,
           tuple(round(R.Cymbal.STARTS["RIDE"][1][n] * 127) for n in R.Cymbal.P2)),
    _place(CRSH, R.Cymbal.P1, tuple(R.Cymbal.STARTS["CRASH"][0][n] for n in R.Cymbal.P1), R.Cymbal.P2,
           tuple(round(R.Cymbal.STARTS["CRASH"][1][n] * 127) for n in R.Cymbal.P2)),
)
PLACES = tuple(sorted(PLACES, key=lambda P: P.TYPE))      # in TYPE's (span) order
PLACE_NAMES = tuple(P.NAME for P in PLACES)
assert (HA.CLHH, HA.OPHH) == (CLHH, OPHH)
for _t, _d1 in ((CLHH, R.Hat.D1), (OPHH, R.Hat.D1_OPEN)):     # the hats' pages and starts: the reference's
    assert PLACES[_t].PNAMES[:7] == R.Hat.P1 and PLACES[_t].DEFAULTS[:7] == tuple(_d1[n] for n in R.Hat.P1)
    assert PLACES[_t].PNAMES2 == R.Hat.P2 and PLACES[_t].DEFAULTS2 == tuple(round(R.Hat.D2[n] * 127) for n in R.Hat.P2)
assert PLACES[KICK].PNAMES == PNAMES and len(set(PLACE_NAMES)) == N_TYPES
assert PLACES[TOM].PNAMES2[R.Tom.P2.index("RNGE")] == "RNGE" and R.Tom.P2.index("RNGE") == TO.RNGE
assert PLACES[SNARE].PNAMES2[7] == "WCHR" and SN.WCHR == 7 and KI.SWHD == 6 and KI.CURV == 7 and (HA.TOP, HA.DRFT) == (4, 5)

S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG = KI.S_TRIG, KI.S_ON, KI.S_TYPE, KI.S_NOTE, KI.S_RNG
SEED = 0x21
WORDS = max(KI.WORDS, SN.WORDS, HA.WORDS, TO.WORDS, CL.WORDS, CY.WORDS)
assert CL.P_RNG2 not in CY._OWN + HA._OWN and not set(range(89, 96)) & set(CL._OWN)   # the kept words
assert WORDS <= 96


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: DRUM takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """every word 0; the generator at Plaits' seed; the ADAA's last antiderivative at F(0)"""
    from ..plaits import plk as K
    K.zero_state(p, 0, WORDS)                 # (a loop: perc2b's room, where every machine's init lives)
    p.iconst(0, SEED)
    M.sv(p, S_RNG, 0)
    p.iconst(0, R.JRNG_SEED)                  # the hats' jitter generator (stage 3)
    M.sv(p, HA.P_JRNG, 0)
    M.sv(p, CL.P_RNG2, 0)                     # CLAP's GRP clapper (stage 4: drum_v4's seed ^ 0x5A5A, the same)
    p.fconst(0, M.SOFT_F0)
    M.sv(p, KI.S_FUP, 0)


def trig(p: Prog, L: C.Layout) -> None:
    """a hit: its values are set in the next half (after `pitch`, so the note is this one's); TYPE latched"""
    p.iconst(0, 1)
    M.sv(p, S_TRIG, 0)
    C.knob(p, 0, TYPE_K)
    p.iconst(1, N_TYPES)
    p.mul_ssi(0, 0, 1)
    p.lsh(0, 0, -7)
    M.sv(p, S_TYPE, 0)


def pitch(p: Prog, L: C.Layout) -> None:
    """S_NOTE = the note (VW pitch, semitones)"""
    C.vw(p, 1, "pitch")
    M.sv(p, S_NOTE, 1)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4: a hit's values first if this half follows a trig (the type latched at the trig: SNARE's, the
    hats', TOM's, CLAP's, the cymbal's or KICK's; re-read on the voice's turn: below); SNARE's and TOM's modes retuned
    each half, an OPEN hat's choke looked at, the hats' and the cymbal's DRFT drawn, the cymbal's body retuned;
    silence before the first hit"""
    assert (CRSH, CLHH, OPHH, RIDE) == (3, 4, 5, 6) and KICK == 0

    def on_type(snare, hat, tom, kick, clap, cym):
        M.ld(p, 0, S_TYPE)
        p.iconst(1, SNARE)

        def other():
            p.iconst(1, TOM)

            def rest():
                p.iconst(1, CLHH)
                p.iop(1, 0, "-", 1)
                p.lsh(1, 1, -1)                # (type - CLHH) >> 1, logical: 0 for CLHH and OPHH alone

                def more():
                    p.iconst(1, CLAP)
                    p.if_(0, "EQ", 1, clap, lambda: p.ifz(0, "EQ", kick, cym), kind="i")
                p.ifz(1, "EQ", hat, more)
            p.if_(0, "EQ", 1, tom, rest, kind="i")
        p.if_(0, "EQ", 1, snare, other, kind="i")

    M.ld(p, 0, S_TRIG)

    def start():                                 # the hats' and the cymbal's hit: one copy (cymbal.metal_hit)
        M.ld(p, 0, S_TYPE)
        p.iconst(1, SNARE)

        def other():
            p.iconst(1, TOM)

            def rest():
                p.iconst(1, CRSH)
                p.iop(1, 0, "-", 1)
                p.lsh(1, 1, -2)                # (type - CRSH) >> 2, logical: 0 for CRSH CLHH OPHH RIDE alone

                def more():
                    p.iconst(1, CLAP)
                    p.if_(0, "EQ", 1, lambda: CL.hit(p, L), lambda: KI.hit(p, L), kind="i")
                p.ifz(1, "EQ", lambda: CY.metal_hit(p, L), more)
            p.if_(0, "EQ", 1, lambda: TO.hit(p, L), rest, kind="i")
        p.if_(0, "EQ", 1, lambda: SN.hit(p, L), other, kind="i")
        p.iconst(0, 0)
        M.sv(p, S_TRIG, 0)
    # 2026-11-21 (live knobs, scratch/mod-live-design.md "D (sound)"): the hit's code also runs with S_TRIG 0 in the
    # first half of the voice's turn (VW live 0: dnfw.md.voice.live_turn, each voice every 16 blocks, ~94 Hz), the
    # hit's state kept (dmath.on_hit): its knobs follow modulation and p-locks while it rings. A hit or a re-read, at
    # most one a block (a trig block's second half: no), so the worst-case voice-block (a hit's) is unchanged.
    from ...md import core as MK
    MK.vw(p, 0, "live")
    p.ld(1, L.W["half"])
    p.iop(0, 0, "OR", 1)                         # 0: the turn's first half
    M.ld(p, 1, S_TRIG)
    p.ifz(1, "NE", lambda: p.iconst(0, 0))       # (a hit)
    p.ifz(0, "EQ", start)
    M.ld(p, 0, S_ON)

    def run():
        def snare():
            SN.half(p, L)
            p.loop(L.W["n4"], 16, lambda: SN.sample(p, L))

        def hat():
            HA.half(p, L)
            p.loop(L.W["n4"], 16, lambda: HA.sample(p, L))

        def tom():
            TO.half(p, L)
            p.loop(L.W["n4"], 16, lambda: TO.sample(p, L))

        def cym():
            CY.half(p, L)
            p.loop(L.W["n4"], 16, lambda: CY.sample(p, L))
        on_type(snare, hat, tom, lambda: p.loop(L.W["n4"], 16, lambda: KI.sample(p, L)),
                lambda: p.loop(L.W["n4"], 16, lambda: CL.sample(p, L)), cym)

    def zeros():
        p.iconst(0, 0)
        for _ in range(16):
            p.stpost(4, 0)
    p.ifz(0, "NE", run, zeros)
