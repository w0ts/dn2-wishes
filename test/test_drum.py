"""DRUM (machine type 56, dnfw.engines.drum): its place in the registry, and each type in the model (the program the
SHARC runs bit for bit) against its reference (dnfw.engines.drum.ref) within DSL_TOL_DB, at its start, its named points
and its dearest corner; every random corner finite and under 1.0; the choke; a retrig. Stage 3 (2026-11-20): the
re-voiced points (scratch/drum-engine/drum_v3.py), the new knobs (SWHD, WCHR, TOP, DRFT, TOM's RNGE), soft hits."""

from __future__ import annotations

import random
import struct

import numpy as np
import pytest

from dnfw.engines.drum import drum as DR
from dnfw.engines.drum import ref as REF
from dnfw.md import core as MDK
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP

# the model's sines (PERC's 256-point table), e^x and log2 (dmath) against numpy's: the error of the whole hit,
# against its peak (measured 2026-11-20; see test_kick_model_matches_reference)
DSL_TOL_DB = -60.0


def _type() -> int:
    return MM.TYPES[MM.NAMES.index("DRUM")]


def _rec2(k: int) -> tuple:
    """page-2 control k's record (id, frame slot, lo, top): PERC's page-2 records, the eighth (H) its TYPE record
    (0..127, read into q7: SNARE's WCHR)"""
    return PM.FX_PARAMS[k] if k < 7 else PM.TYPE_REC + (0, 127)


def _q(x: int, k: int) -> float:
    """page-2 control k at knob x as the DSP reads it: the record's value (live.knob_word) x 1 / top, float32"""
    _rid, _slot, lo, top = _rec2(k)
    v = (PL.knob_word(x, top, lo) >> 8) - lo
    return float(np.float32(np.float32(v) * np.float32(1.0 / top)))


def render_model(p1: dict, p2: dict, hits, blocks: int, t: int = DR.KICK, then=None, at=None,
                 vel: int = 127) -> np.ndarray:
    """the machine's own 44.1 kHz stream (OUT0, before PERC's resampler and level), HITS = {block: note}, type T;
    THEN = (block, type, page 1, page 2): that type's knobs and a hit from that block on. AT (a list): each render's
    DN2 block (the stream is 44.1 kHz: 32 samples a render, a render in about 11 of 12 DN2 blocks)"""
    P = DR.PLACES[t]
    k = MM.NAMES.index("DRUM")
    M = MM.MACHINES[k]
    render0 = M.render
    out = []
    blk = [0]

    def render(p, L):
        x = render0(p, L)
        if at is not None:
            at.append(blk[0])
        out.extend(struct.unpack("<f", struct.pack("<I", p.mem.get(p.i[3] - 4 * PP.I3_BIAS + 4 * (MDK.OUT0 + j))))[0]
                   for j in range(32))
        return x
    M.render = render
    try:
        h = PL.Harness()
        knobs = [p1[n] for n in P.PNAMES[:7]] + [DR.type_knob(t)]
        h.set_mnm(_type(), knobs)
        for j, n in enumerate(P.PNAMES2):
            _rid, slot, lo, top = _rec2(j)
            h._half(PM.frame_offset(slot), PL.knob_word(p2[n], top, lo))
        h._half(PM.frame_offset(PM.VEL_SLOT), vel << 8)       # the note's velocity (perc.program.vel_latch)
        for b in range(blocks):
            blk[0] = b
            if then and b == then[0]:
                P2 = DR.PLACES[then[1]]
                h.set_mnm(_type(), [then[2][n] for n in P2.PNAMES[:7]] + [DR.type_knob(then[1])])
                for j, n in enumerate(P2.PNAMES2):
                    _rid, slot, lo, top = _rec2(j)
                    h._half(PM.frame_offset(slot), PL.knob_word(then[3][n], top, lo))
                hits = {**hits, b: 60.0}
            note = hits.get(b)
            h.block(60.0 if note is None else note, note is not None)
    finally:
        M.render = render0
    return np.array(out, dtype=np.float32)


def _k1(x: int, k: int) -> int:
    """page-1 knob X of record k as the DSP reads it: the nearest value its record holds (PERC's A and B records
    span 0..120: knobs 9, 27, 45, 63, 82, 100, 118 read as their neighbours; live.knob_word)"""
    _rid, _slot, lo, top = PM.PARAMS[k]
    return int(((PL.knob_word(x, top, lo) >> 8) - lo) / top * 127 + 0.5)


def render_ref(p1: dict, p2: dict, hits, blocks: int, t: int = DR.KICK, vel: int = 127) -> np.ndarray:
    P = DR.PLACES[t]
    p1 = {n: _k1(p1[n], j) for j, n in enumerate(P.PNAMES[:7])}
    q2 = {n: _q(p2[n], j) for j, n in enumerate(P.PNAMES2)}
    return REF.render(p1, q2, hits=[(b * 32 / REF.FS, n, vel / 127) for b, n in hits.items()],
                      seconds=blocks * 32 / REF.FS,
                      kind=KINDS[t])


KINDS = {DR.KICK: "KICK", DR.CLAP: "CLAP", DR.SNARE: "SNARE", DR.CRSH: "CRASH", DR.CLHH: "CLHH", DR.OPHH: "OPHH",
         DR.RIDE: "RIDE", DR.TOM: "TOM"}


def _err_db(a: np.ndarray, b: np.ndarray) -> float:
    pk = float(np.abs(b).max())
    return 20 * np.log10(float(np.abs(a - b).max()) / pk + 1e-30) if pk > 0 else -999.0


START1 = dict(zip(DR.PNAMES[:7], DR.DEFAULTS[:7]))
START2 = dict(zip(DR.PNAMES2, DR.DEFAULTS2))
CASES = {
    "start": ({}, {}),
    "tick": (dict(TUNE=127, DCAY=0, SWEP=30, SWTM=10, CLIK=55, CLKT=70, DRIV=10), dict(HOLD=0, CLKL=15, NOIS=0)),
    "808 long": (dict(TUNE=55, DCAY=106, SWEP=23, SWTM=44, CLIK=7, CLKT=38, DRIV=5),
                 dict(SHAP=0, HOLD=0, SIGH=64, CLKL=29, NOIS=0)),
    "chirp click": (dict(DCAY=70, SWEP=55, SWTM=45, CLIK=30, CLKT=100, DRIV=55), dict(SHAP=20, HOLD=25, CLKL=35)),
    "full chirp, hard drive": (dict(TUNE=49, DCAY=85, SWEP=95, SWTM=75, CLIK=35, CLKT=127, DRIV=127), dict(HOLD=60)),
    "held, driven": (dict(DCAY=127, SWEP=0, CLIK=0, DRIV=100), dict(HOLD=127, SIGH=0, NOIS=0, SHAP=60)),
    # stage 3 (drum_v3): the sigh from the hit's level (808 BOOM's drive), the 909 re-voiced (SWHD 16 ms, HOLD 40 ms),
    # TECHNO re-voiced, every knob at its top (SWHD 30 ms)
    "808 boom": (dict(TUNE=48, DCAY=115, SWEP=32, SWTM=45, CLIK=10, CLKT=36, DRIV=42),
                 dict(SHAP=0, HOLD=30, SIGH=64, NOIS=0)),
    "909 re-voiced": (dict(TUNE=51, DCAY=82, SWEP=21, SWTM=65, CLIK=24, CLKT=67, DRIV=26),
                      dict(SHAP=17, HOLD=51, SIGH=13, CLKL=34, NOIS=10, VEL=64, SWHD=68)),
    "techno re-voiced": (dict(DCAY=70, SWEP=55, SWTM=45, CLIK=30, CLKT=100, DRIV=55), dict(SHAP=20, HOLD=44, CLKL=35)),
    "worst": ({n: 127 for n in DR.PNAMES[:7]}, {n: 127 for n in DR.PNAMES2}),
    # stage 5: CLIK at its ends (body+noise only, the click only), CURV a line and the concave
    "no click": (dict(CLIK=0), {}),
    "click only": (dict(CLIK=127, CLKT=40), dict(CLKL=40)),
    "curv line": (dict(SWEP=80, SWTM=70), dict(CURV=0)),
    "curv concave": (dict(SWEP=80, SWTM=70), dict(CURV=127, SWHD=20)),
}


def test_registry():
    k = MM.NAMES.index("DRUM")
    assert MM.TYPES[k] == 56 and 56 not in MM.RESERVED and PP.OURS_RANGE == (50, 56)
    assert MM.MACHINES[k].PNAMES == DR.PNAMES and MM.MACHINES[k].PNAMES2 == DR.PNAMES2
    assert [DR.type_of(DR.type_knob(t)) for t in range(DR.N_TYPES)] == list(range(DR.N_TYPES))


@pytest.mark.parametrize("case", list(CASES))
def test_kick_model_matches_reference(case):
    p1, p2 = CASES[case]
    p1, p2 = {**START1, **p1}, {**START2, **p2}
    blocks = 60
    hits = {0: 60.0}
    a = render_model(p1, p2, hits, blocks)
    b = render_ref(p1, p2, hits, blocks)[:len(a)]
    assert np.isfinite(a).all() and float(np.abs(b).max()) > 0.05
    e = _err_db(a, b)
    print(f"{case}: model vs reference {e:.1f} dB under the peak")
    assert e < DSL_TOL_DB, (case, e)


def test_kick_random_corners_are_finite_and_bounded():
    rng = random.Random(7)
    for _ in range(6):
        p1 = {n: rng.randint(0, 127) for n in DR.PNAMES[:7]}
        p2 = {n: rng.randint(0, 127) for n in DR.PNAMES2}
        a = render_model(p1, p2, {0: float(rng.randint(36, 84))}, 40, vel=rng.choice((127, rng.randint(1, 127))))
        assert np.isfinite(a).all() and float(np.abs(a).max()) < 1.0, (p1, p2, float(np.abs(a).max()))


# SNARE (stage 2b): its start (RICH) and stage 1b's spectrum points (scratch/drum-engine/banks.py SNARE_SPECTRUM,
# as DN2 knobs; RING gone), the clap-snare's bursts, the dearest corner
SN = DR.PLACES[DR.SNARE]
SN_START1 = dict(zip(SN.PNAMES[:7], SN.DEFAULTS[:7]))
SN_START2 = dict(zip(SN.PNAMES2, SN.DEFAULTS2))
SNARE_CASES = {
    "start (RICH)": ({}, {}),
    "808": (dict(TUNE=64, DCAY=57, TONE=33, MODE=0, SNAP=33, NOIS=64, DRIV=19),
            dict(WIRE=48, GLID=13, BUZZ=0, WTON=76, WATK=22, SIZZ=0)),
    "909": (dict(TUNE=69, DCAY=57, TONE=52, MODE=0, SNAP=67, NOIS=95, DRIV=57),
            dict(WIRE=68, GLID=44, BUZZ=13, WTON=95, WATK=22, SIZZ=0)),
    "acoustic": (dict(TUNE=58, DCAY=66, TONE=52, MODE=127, SNAP=57, NOIS=83, DRIV=25),
                 dict(WIRE=63, GLID=64, BUZZ=76, WTON=64, WATK=31, SIZZ=0)),
    "loose": (dict(TUNE=53, DCAY=80, TONE=105, MODE=127, SNAP=70, NOIS=90, DRIV=25),
              dict(WIRE=85, GLID=75, BUZZ=90, WTON=55, WATK=50, SIZZ=40)),
    "trap clap-snare": (dict(TUNE=70, DCAY=35, TONE=50, MODE=20, SNAP=60, NOIS=110, DRIV=35),
                        dict(WIRE=70, GLID=44, BUZZ=0, WTON=80, WATK=120, SIZZ=50)),
    "rim / clicky": (dict(TUNE=95, DCAY=15, TONE=60, MODE=30, SNAP=127, NOIS=35, DRIV=30),
                     dict(WIRE=30, GLID=44, BUZZ=44, WTON=95, WATK=22, SIZZ=0)),
    "worst": ({n: 127 for n in SN.PNAMES[:7]}, {n: 127 for n in SN.PNAMES2}),
    # stage 3 (drum_v3): WCHR's ends on the start, the 808 and 909 re-voiced, the dearest with WCHR at the 909's end
    "RICH WCHR 0": ({}, dict(WCHR=0)),
    "RICH WCHR 127": ({}, dict(WCHR=127)),
    "808 re-voiced": (dict(TUNE=64, DCAY=69, TONE=40, MODE=18, SNAP=40, NOIS=38, DRIV=5),
                      dict(WIRE=75, GLID=0, BUZZ=0, WTON=11, WATK=0, SIZZ=0, VEL=64, WCHR=127)),
    "909 re-voiced": (dict(TUNE=75, DCAY=56, TONE=40, MODE=127, SNAP=45, NOIS=100, DRIV=10),
                      dict(WIRE=94, GLID=48, BUZZ=0, WTON=44, WATK=0, SIZZ=0, VEL=64, WCHR=0)),
    "worst WCHR 0": ({n: 127 for n in SN.PNAMES[:7]}, {**{n: 127 for n in SN.PNAMES2}, "WCHR": 0}),
}


@pytest.mark.parametrize("case", list(SNARE_CASES))
def test_snare_model_matches_reference(case):
    p1, p2 = SNARE_CASES[case]
    p1, p2 = {**SN_START1, **p1}, {**SN_START2, **p2}
    blocks = 60
    hits = {0: 60.0}
    a = render_model(p1, p2, hits, blocks, DR.SNARE)
    b = render_ref(p1, p2, hits, blocks, DR.SNARE)[:len(a)]
    assert np.isfinite(a).all() and float(np.abs(b).max()) > 0.05
    e = _err_db(a, b)
    print(f"SNARE {case}: model vs reference {e:.1f} dB under the peak, peak {float(np.abs(a).max()):.3f}")
    assert e < DSL_TOL_DB, (case, e)


def test_snare_random_corners_are_finite_and_bounded():
    rng = random.Random(8)
    for _ in range(6):
        p1 = {n: rng.randint(0, 127) for n in SN.PNAMES[:7]}
        p2 = {n: rng.randint(0, 127) for n in SN.PNAMES2}
        a = render_model(p1, p2, {0: float(rng.randint(36, 84))}, 40, DR.SNARE,
                         vel=rng.choice((127, rng.randint(1, 127))))
        assert np.isfinite(a).all() and float(np.abs(a).max()) <= 1.0, (p1, p2, float(np.abs(a).max()))


def test_reference_sine_is_percs():
    """ref.sinp (the reference's copy, numpy alone) is PERC's sine polynomial, value for value"""
    from dnfw.engines.plaits import plk
    assert REF.SIN_POLY == plk.SIN_POLY
    rng = random.Random(3)
    for _ in range(2000):
        x = float(np.float32(rng.uniform(0.0, 0.7)))
        assert float(REF.sinp(x)) == plk.ref_sinp(x), x


# CLOSED and OPEN HAT (stage 2c): their starts and stage 1b's spectrum points (scratch/drum-engine/banks.py
# HATS_SPECTRUM, as DN2 knobs), the dearest corner; random corners under 1.0; the choke (two slots on one track, the
# model against the reference, and a control on two tracks); a CLOSED trig on a sounding OPEN hit on one voice
CH, OH = DR.PLACES[DR.CLHH], DR.PLACES[DR.OPHH]
HAT_CASES = {
    "CLHH start (808)": (DR.CLHH, {}, {}),
    "CLHH tick": (DR.CLHH, dict(DCAY=0, TONE=85, NOIS=50, SNAP=110), dict(HPF=90)),
    "CLHH thin": (DR.CLHH, dict(DCAY=35, TONE=100, NOIS=60), dict(HPF=100, Q=20)),
    "CLHH 909-like": (DR.CLHH, dict(DCAY=55, TONE=75, NOIS=100, COLR=30, SNAP=60, DRIV=20), dict(Q=15)),
    "CLHH acoustic-like (ring, low band)": (DR.CLHH, dict(DCAY=45, TONE=60, NOIS=70, COLR=115, SNAP=80),
                                            dict(Q=25, LOWB=60)),
    "CLHH worst": (DR.CLHH, {n: 127 for n in CH.PNAMES[:7]}, {n: 127 for n in CH.PNAMES2}),
    "OPHH start (808)": (DR.OPHH, {}, {}),
    "OPHH washy": (DR.OPHH, dict(DCAY=95, TONE=50, NOIS=60, COLR=127, DRIV=40), dict(Q=10, LOWB=50)),
    "OPHH worst": (DR.OPHH, {n: 127 for n in OH.PNAMES[:7]}, {n: 127 for n in OH.PNAMES2}),
    # stage 3 (drum_v3): the 808s re-voiced (TOP), DRFT's ends, TOP's top; OPEN's line (TRASHY, just past OPEN_X0)
    # and its exponential tail (DCAY 110, past OPEN_X1)
    "CLHH 808 re-voiced": (DR.CLHH, dict(DCAY=75), dict(TOP=42)),
    "CLHH DRFT 0": (DR.CLHH, {}, dict(DRFT=0)),
    "CLHH DRFT 127, TOP 127": (DR.CLHH, {}, dict(DRFT=127, TOP=127)),
    "OPHH 808 re-voiced": (DR.OPHH, dict(DCAY=66, TONE=56), dict(TOP=10)),
    "OPHH trashy": (DR.OPHH, dict(DCAY=81, NOIS=51, DRIV=64), {}),
    "OPHH long (exponential tail)": (DR.OPHH, dict(DCAY=110), {}),
}


def _hat_knobs(t: int, p1: dict, p2: dict) -> tuple[dict, dict]:
    P = DR.PLACES[t]
    return ({**dict(zip(P.PNAMES[:7], P.DEFAULTS[:7])), **p1}, {**dict(zip(P.PNAMES2, P.DEFAULTS2)), **p2})


@pytest.mark.parametrize("case", list(HAT_CASES))
def test_hat_model_matches_reference(case):
    t, p1, p2 = HAT_CASES[case]
    p1, p2 = _hat_knobs(t, p1, p2)
    blocks = 60
    a = render_model(p1, p2, {0: 60.0}, blocks, t)
    b = render_ref(p1, p2, {0: 60.0}, blocks, t)[:len(a)]
    assert np.isfinite(a).all() and float(np.abs(b).max()) > 0.05
    e = _err_db(a, b)
    print(f"{case}: model vs reference {e:.1f} dB under the peak, peak {float(np.abs(a).max()):.3f}")
    assert e < DSL_TOL_DB, (case, e)


def test_hat_random_corners_are_finite_and_under_one():
    rng = random.Random(9)
    for k in range(8):
        t = (DR.CLHH, DR.OPHH)[k % 2]
        P = DR.PLACES[t]
        p1 = {n: rng.randint(0, 127) for n in P.PNAMES[:7]}
        p2 = {n: rng.randint(0, 127) for n in P.PNAMES2}
        a = render_model(p1, p2, {0: float(rng.randint(36, 84))}, 40, t, vel=rng.choice((127, rng.randint(1, 127))))
        assert np.isfinite(a).all() and float(np.abs(a).max()) < 1.0, (t, p1, p2, float(np.abs(a).max()))


def test_hat_reference_corners_under_one(monkeypatch):
    """the reference (within -110 dB of the model) WITHOUT its output's hold (ref.HAT_TOP, 0.99): 400 random corners
    (knobs at their ends or anywhere, notes 0..127, velocities, the noise anywhere in its sequence) and every
    stacking corner (SNAP, NOIS, DRIV, LOWB, Q, COLR at their ends, TONE low / mid / high, HPF 0): the engine's output
    under 1.0 by its levels alone (the hold is for the noise's rare peaks beyond them)"""
    import itertools
    monkeypatch.setattr(REF, "HAT_TOP", 100.0)
    rng = random.Random(10)
    corners = [(rng.random() < 0.5, {n: rng.choice((0, 127, rng.randint(0, 127))) for n in REF.Hat.P1},
                {n: rng.choice((0.0, 1.0, rng.randint(0, 127) / 127)) for n in REF.Hat.P2},
                float(rng.randint(0, 127)), rng.choice((1.0, rng.random())), rng.getrandbits(32)) for _ in range(400)]
    for v in itertools.product((0, 127), repeat=6):
        for tone in (0, 64, 127):
            corners.append((bool(v[5]), dict(SNAP=v[0], NOIS=v[1], DRIV=v[2], TONE=tone, COLR=v[3] or 44, DCAY=127),
                            dict(LOWB=v[4] / 127, Q=float(v[5] or v[4]) / 127, HPF=0.0, VEL=1.0), 60.0, 1.0, 0x21))
    top = 0.0
    for o, p1, p2, note, vel, seed in corners:
        h = REF.Hat(p1, p2, seed=seed, open_=o)
        h.trig(note, vel)
        top = max(top, float(np.abs(h.render(1200)).max()))
    print(f"the hats' reference corners (no output hold): peak {top:.3f}")
    assert top < 1.0


def test_reference_exp2_is_percs():
    from dnfw.engines.plaits import plk
    from dnfw.perc.dsl import Prog
    assert REF.EXP2_POLY == plk._poly_exp2()
    rng = random.Random(4)
    for _ in range(500):
        x = float(np.float32(rng.uniform(-12.0, 4.0)))
        p = Prog("run")
        p.fconst(2, x)
        plk.exp2p(p, 3, 2)
        assert float(REF.exp2p(x)) == p.F(3), x


def _two_slots(p1o: dict, p2o: dict, p1c: dict, p2c: dict, at: int, blocks: int, tracks=(0, 0), open_at: int = 0,
               open_slot: int = 0, cut_block: int | None = None):
    """an OPEN hit (block OPEN_AT, on slot OPEN_SLOT) and a CLOSED hit (block AT, on the other slot), slot s on track
    TRACKS[s] (the stock's slot map, ROUTE), one memory; each block PERC's block clock one more (CLOCK_OFF, as the
    program's entry sets it) and the voices rendered as PERC orders them: the newest first, a tie (both hit in that
    block) by slot. -> the OPEN voice's engine output (OUT0) from its hit, the CLOSED's from its hit, and the sample of
    the OPEN's stream where block CUT_BLOCK (default: the CLOSED hit's) starts"""
    from dnfw.engines.drum import hats as HA
    k = MM.NAMES.index("DRUM")
    M = MM.MACHINES[k]
    render0 = M.render
    cs = 1 - open_slot
    hit = {open_slot: open_at, cs: at}
    out = {open_slot: [], cs: []}
    cur = []

    def render(p, L):
        x = render0(p, L)
        s, b = cur
        if b >= hit[s]:                             # (a slot before its hit: silence, not kept)
            out[s].append((b, [struct.unpack("<f", struct.pack("<I", p.mem.get(p.i[3] - 4 * PP.I3_BIAS
                                                                                + 4 * (MDK.OUT0 + j))))[0]
                                for j in range(32)]))
        return x
    M.render = render
    try:
        hs = [PL.Harness(0), PL.Harness(1)]
        hs[1].mem = hs[0].mem
        mem = hs[0].mem
        mem.put(HA.ROUTE, tracks[0] | (tracks[1] << 16))
        for h, t, p1, p2 in ((hs[open_slot], DR.OPHH, p1o, p2o), (hs[cs], DR.CLHH, p1c, p2c)):
            P = DR.PLACES[t]
            h.set_mnm(_type(), [p1[n] for n in P.PNAMES[:7]] + [DR.type_knob(t)])
            for j, n in enumerate(P.PNAMES2):
                _rid, slot, lo, top = _rec2(j)
                h._half(PM.frame_offset(slot), PL.knob_word(p2[n], top, lo))
        clock = hs[0].L.md.mnm.scratch + PP.CLOCK_OFF
        for b in range(blocks):
            mem.put(clock, b + 1)
            age = {s: (b - hit[s] if b >= hit[s] else 1 << 20) for s in (0, 1)}
            for s in sorted((0, 1), key=lambda s: age[s] * 16 + s):
                cur[:] = [s, b]
                hs[s].block(60.0, b == hit[s])
    finally:
        M.render = render0
    o, c = (np.array([x for _b, r in out[s] for x in r], dtype=np.float32) for s in (open_slot, cs))
    return o, c, 32 * sum(1 for b, _r in out[open_slot] if b < (at if cut_block is None else cut_block))


def _hat_refs(po, pc, n_open: int, n_closed: int, choke_at: int | None):
    """the reference's OPEN (choked at its sample CHOKE_AT, None: never) and CLOSED outputs"""
    q2o = {n: _q(po[1][n], j) for j, n in enumerate(OH.PNAMES2)}
    q2c = {n: _q(pc[1][n], j) for j, n in enumerate(CH.PNAMES2)}
    ro = REF.OpenHat({n: _k1(v, j) for j, (n, v) in enumerate(po[0].items())}, q2o)
    ro.trig(60.0, 1.0)
    if choke_at is None:
        ref_o = ro.render(n_open)
    else:
        ref_o = np.concatenate([ro.render(choke_at), (ro.choke(), ro.render(n_open - choke_at))[1]])
    rc = REF.Hat({n: _k1(v, j) for j, (n, v) in enumerate(pc[0].items())}, q2c)
    rc.trig(60.0, 1.0)
    return ref_o, rc.render(n_closed)


def test_hat_choke_two_slots():
    """a CLOSED hit on slot 1 chokes the OPEN hit sounding on slot 0 of the same track from the CLOSED's trig block
    (the reference's choke there), within 3 ms; on another track the OPEN rings on"""
    po, pc = _hat_knobs(DR.OPHH, dict(DCAY=100), {}), _hat_knobs(DR.CLHH, {}, {})
    at, blocks = 20, 60
    o, c, cut = _two_slots(*po, *pc, at, blocks)
    o2, c2, _cut = _two_slots(*po, *pc, at, blocks, tracks=(0, 1))
    # the reference: the OPEN voice choked at the CLOSED's first sample (REF.choke_block(0, at) == at)
    assert REF.choke_block(0, at) == at
    ref_o, ref_c = _hat_refs(po, pc, len(o), len(c), cut)
    e_o, e_c = _err_db(o, ref_o), _err_db(c, ref_c)
    print(f"choke: OPEN model vs reference {e_o:.1f} dB, CLOSED {e_c:.1f} dB")
    assert e_o < DSL_TOL_DB and e_c < DSL_TOL_DB
    ms3 = int(0.003 * REF.FS)
    late = slice(cut + 10 * 32, cut + 20 * 32)               # 7 .. 15 ms after the CLOSED hit
    assert len(o) == len(o2) and np.array_equal(o[:cut], o2[:cut]) and np.array_equal(c, c2)
    r_choked = float(np.sqrt(np.mean(o[late].astype(float) ** 2)))
    r_free = float(np.sqrt(np.mean(o2[late].astype(float) ** 2)))
    print(f"choke: the OPEN voice 7..15 ms after: {20 * np.log10(r_choked / r_free):.1f} dB against another track's")
    assert r_choked < 0.1 * r_free                          # (tau 3 ms: -20 dB at 7 ms, -43 dB at 15)
    env = np.abs(o[cut + ms3: cut + ms3 + 32]).max() / np.abs(o2[cut + ms3: cut + ms3 + 32]).max()
    assert env < 0.5, env                                   # 3 ms on: already under half (tau 3 ms: -8.7 dB)


@pytest.mark.parametrize("open_slot", (0, 1))
def test_hat_choke_same_block_either_order(open_slot):
    """the User (2026-11-20): a CLOSED and an OPEN hit on one track in ONE block -> the OPEN is always choked, whatever
    the slots' render order (slot 0 OPEN: it renders first; slot 1 OPEN: the CLOSED renders first): from the next
    block (ref.choke_block), the two orders the same to the bit; the CLOSED as alone; on two tracks no choke"""
    po, pc = _hat_knobs(DR.OPHH, dict(DCAY=100), {}), _hat_knobs(DR.CLHH, {}, {})
    at, blocks = 6, 40
    cb = REF.choke_block(at, at)
    o, c, cut = _two_slots(*po, *pc, at, blocks, open_at=at, open_slot=open_slot, cut_block=cb)
    o_other, c_other, _ = _two_slots(*po, *pc, at, blocks, open_at=at, open_slot=1 - open_slot, cut_block=cb)
    tr = (0, 1) if open_slot == 0 else (1, 0)
    o2, c2, _ = _two_slots(*po, *pc, at, blocks, tracks=tr, open_at=at, open_slot=open_slot, cut_block=cb)
    assert cut == 32                                        # the OPEN's hit block, then choked
    assert np.array_equal(o, o_other) and np.array_equal(c, c_other), "the render order changed the outputs"
    assert np.array_equal(c, c2) and np.array_equal(o[:cut], o2[:cut]) and not np.array_equal(o, o2)
    ref_o, ref_c = _hat_refs(po, pc, len(o), len(c), cut)
    e_o, e_c = _err_db(o, ref_o), _err_db(c, ref_c)
    ref_free, _rc = _hat_refs(po, pc, len(o2), len(c2), None)
    e_free = _err_db(o2, ref_free)
    print(f"same-block choke (OPEN on slot {open_slot}): OPEN vs reference {e_o:.1f} dB, CLOSED {e_c:.1f} dB, "
          f"two tracks' OPEN {e_free:.1f} dB")
    assert e_o < DSL_TOL_DB and e_c < DSL_TOL_DB and e_free < DSL_TOL_DB
    late = slice(cut + 10 * 32, cut + 20 * 32)
    r_choked = float(np.sqrt(np.mean(o[late].astype(float) ** 2)))
    r_free = float(np.sqrt(np.mean(o2[late].astype(float) ** 2)))
    assert r_choked < 0.1 * r_free, (r_choked, r_free)


def test_choke_block_rule():
    assert REF.choke_block(3, 10) == 10 and REF.choke_block(10, 10) == 11 and REF.choke_block(10, 3) is None


def test_hat_closed_retrig_on_open_one_voice():
    """one voice: a CLOSED trig on a sounding OPEN hit takes the voice (the OPEN's last sample fades in 1 ms)"""
    po, pc = _hat_knobs(DR.OPHH, dict(DCAY=100), {}), _hat_knobs(DR.CLHH, {}, {})
    at, blocks = 12, 40
    renders = []
    a = render_model(po[0], po[1], {0: 60.0}, blocks, DR.OPHH, then=(at, DR.CLHH, *pc), at=renders)
    cut = 32 * sum(1 for b in renders if b < at)
    q2o = {n: _q(po[1][n], j) for j, n in enumerate(OH.PNAMES2)}
    q2c = {n: _q(pc[1][n], j) for j, n in enumerate(CH.PNAMES2)}
    ro = REF.OpenHat({n: _k1(v, j) for j, (n, v) in enumerate(po[0].items())}, q2o)
    ro.trig(60.0, 1.0)
    first = ro.render(cut)
    rc = REF.Hat({n: _k1(v, j) for j, (n, v) in enumerate(pc[0].items())}, q2c)
    rc.noise.s, rc.on, rc.last = ro.noise.s, True, ro.last
    rc.jrng.s, rc.drift = ro.jrng.s, list(ro.drift)          # (stage 3: the voice's DRFT generator and walk go on)
    rc.trig(60.0, 1.0)
    b = np.concatenate([first, rc.render(len(a) - cut)])
    e = _err_db(a, b)
    print(f"OPEN then CLOSED on one voice: model vs reference {e:.1f} dB")
    assert e < DSL_TOL_DB
    fresh = REF.Hat({n: _k1(v, j) for j, (n, v) in enumerate(pc[0].items())}, q2c)
    fresh.noise.s = ro.noise.s
    fresh.jrng.s, fresh.drift = ro.jrng.s, list(ro.drift)
    fresh.trig(60.0, 1.0)
    # the cut sound's last sample carries on under the new hit (the declick), falling in 1 ms
    assert abs(float(a[cut]) - float(fresh.render(1)[0]) - float(first[-1])) < 1e-4


# TOM (stage 3, 2026-11-20): drum_v3's Tom3 with KICK's drive level, its DC out and the declick, RNGE LOW / MID / HI
# (page 2 D). Its start (the study's re-voiced 808 MID), the study's 808 LO / HI, 909 LO / MID / HI and CONGA, RNGE's
# detents, the synth / electro point (SHAP's triangle), every knob at its top (MODE 127: the membrane's ratios) and with
# MODE 0 (the 909's partials)
TM = DR.PLACES[DR.TOM]


def _tk(st: int) -> int:
    return round((0.5 + st / 48.0) * 127)


T808 = (dict(SWEP=21, TONE=0, NOIS=15, SNAP=10, DRIV=0), dict(SWTM=64, SHAP=0))
T909 = (dict(SWEP=25, TONE=115, NOIS=0, SNAP=80, DRIV=30), dict(SWTM=87, MODE=0, SHAP=127))
TOM_CASES = {
    "start (808 MID)": ({}, {}),
    "808 LO": ({**T808[0], "TUNE": _tk(-3), "DCAY": 77}, T808[1]),
    "808 HI": ({**T808[0], "TUNE": _tk(10), "DCAY": 67}, T808[1]),
    "RNGE LOW": ({}, dict(RNGE=0)),
    "RNGE HI": ({}, dict(RNGE=127)),
    "909 LO": ({**T909[0], "TUNE": _tk(-8), "DCAY": 94}, T909[1]),
    "909 MID": ({**T909[0], "TUNE": _tk(-1), "DCAY": 80}, T909[1]),
    "909 HI": ({**T909[0], "TUNE": _tk(3), "DCAY": 81}, T909[1]),
    "808 conga": (dict(TUNE=_tk(17), SWEP=13, DCAY=54, TONE=0, NOIS=0, SNAP=10, DRIV=0), dict(SWTM=64, SHAP=0)),
    "electro": (dict(TUNE=56, DCAY=55, SWEP=118, TONE=10, NOIS=20, DRIV=40), dict(SWTM=30, SHAP=30)),
    "worst": ({n: 127 for n in TM.PNAMES[:7]}, {n: 127 for n in TM.PNAMES2}),
    "worst MODE 0": ({n: 127 for n in TM.PNAMES[:7]}, {**{n: 127 for n in TM.PNAMES2}, "MODE": 0}),
}


def _tom_knobs(p1: dict, p2: dict) -> tuple[dict, dict]:
    return ({**dict(zip(TM.PNAMES[:7], TM.DEFAULTS[:7])), **p1}, {**dict(zip(TM.PNAMES2, TM.DEFAULTS2)), **p2})


@pytest.mark.parametrize("case", list(TOM_CASES))
def test_tom_model_matches_reference(case):
    p1, p2 = _tom_knobs(*TOM_CASES[case])
    blocks = 60
    a = render_model(p1, p2, {0: 60.0}, blocks, DR.TOM)
    b = render_ref(p1, p2, {0: 60.0}, blocks, DR.TOM)[:len(a)]
    assert np.isfinite(a).all() and float(np.abs(b).max()) > 0.05
    e = _err_db(a, b)
    print(f"TOM {case}: model vs reference {e:.1f} dB under the peak, peak {float(np.abs(a).max()):.3f}")
    assert e < DSL_TOL_DB, (case, e)


def test_tom_random_corners_are_finite_and_under_one():
    rng = random.Random(11)
    for _ in range(8):
        p1 = {n: rng.randint(0, 127) for n in TM.PNAMES[:7]}
        p2 = {n: rng.randint(0, 127) for n in TM.PNAMES2}
        a = render_model(p1, p2, {0: float(rng.randint(36, 84))}, 40, DR.TOM, vel=rng.choice((127, rng.randint(1, 127))))
        assert np.isfinite(a).all() and float(np.abs(a).max()) < 1.0, (p1, p2, float(np.abs(a).max()))


def test_tom_rnge_detents_shift_the_pitch():
    """RNGE's three detents: LOW / MID / HI the start's pitch -6.5 / 0 / +6.25 semitones (the reference's f0)"""
    f = []
    for x in (0, 64, 127):
        t = REF.Tom(dict(zip(TM.PNAMES[:7], TM.DEFAULTS[:7])), {**dict(zip(TM.PNAMES2, (v / 127 for v in TM.DEFAULTS2))),
                                                                 "RNGE": _q(x, TM.PNAMES2.index("RNGE"))})
        t.trig(60.0, 1.0)
        f.append(float(t.f0))
    st = [12 * np.log2(x / f[1]) for x in f]
    assert abs(st[0] + 6.5) < 1e-3 and abs(st[2] - 6.25) < 1e-3, st


# soft hits (stage 3: the clip sees the velocity; KICK's sigh follows the hit's level; the hats' knee by velocity)
@pytest.mark.parametrize("t", [DR.KICK, DR.SNARE, DR.CLHH, DR.OPHH, DR.TOM])
def test_soft_hit_matches_reference(t):
    P = DR.PLACES[t]
    p1, p2 = dict(zip(P.PNAMES[:7], P.DEFAULTS[:7])), dict(zip(P.PNAMES2, P.DEFAULTS2))
    if t == DR.KICK:
        p1, p2 = {**p1, **CASES["808 boom"][0]}, {**p2, **CASES["808 boom"][1], "VEL": 127}
    a = render_model(p1, p2, {0: 60.0}, 50, t, vel=40)
    b = render_ref(p1, p2, {0: 60.0}, 50, t, vel=40)[:len(a)]
    full = render_model(p1, p2, {0: 60.0}, 50, t)
    e = _err_db(a, b)
    print(f"{DR.TYPES[t]} at velocity 40: model vs reference {e:.1f} dB, peak {float(np.abs(a).max()):.3f} "
          f"(full {float(np.abs(full).max()):.3f})")
    assert e < DSL_TOL_DB and float(np.abs(a).max()) <= float(np.abs(full).max())


# STAGE 4 (2026-11-20): CLAP, RIDE and CRASH (scratch/drum-engine/drum_v4.py; the presets to be: README "Stage 4"), each
# against its reference (ref.Clap / ref.Cymbal, float32, the DSP's arithmetic) at its start, the preset points, every
# knob at its top; random corners finite and under 1.0; soft hits
CP = DR.PLACES[DR.CLAP]
CLAP_CASES = {
    "808 (start)": ({}, {}),
    "909": (dict(TUNE=61, DCAY=41, TONE=64, CNT=56, SPRD=76, TAIL=27, DRIV=22), dict(SNAP=53, Q=59, TATK=0, RAMP=104)),
    "tight": (dict(TUNE=69, DCAY=20, CNT=40, SPRD=30, TAIL=50), dict(SNAP=90, Q=50)),
    "snap (one burst)": (dict(TUNE=87, DCAY=15, TONE=80, CNT=0, TAIL=30), dict(SNAP=110, Q=75, TATK=0)),
    "big group": (dict(DCAY=60, TONE=60, CNT=72, SPRD=70, TAIL=85), dict(Q=30, HUMN=90, GRP=110)),
    "room": (dict(DCAY=100, CNT=56, TAIL=110), dict(TLTN=44, TATK=90, HUMN=30)),
    "wide flam": (dict(CNT=100, SPRD=100, DCAY=50), dict(HUMN=70, SNAP=60)),
    "trap": (dict(TUNE=71, DCAY=36, TONE=100, CNT=48, SPRD=45, TAIL=70, DRIV=45), dict(Q=40, SNAP=75, GRP=50, HUMN=40)),
    "dark": (dict(TUNE=45, DCAY=55, TONE=20), dict(Q=50, TLTN=40)),
    "worst": ({**{n: 127 for n in CP.PNAMES[:7]}, "TAIL": 64}, {n: 127 for n in CP.PNAMES2}),   # (TAIL's centre: both)
}
RIDE_CASES = {
    "808 (start)": ({}, {}),
    "ping": (dict(BELL=70, HIT=25, TONE=70, DCAY=70), dict(SNAP=100, SWEL=0, NOIS=0)),
    "bell": (dict(TUNE=50, BELL=118, DCAY=80, HIT=30, COLR=30), dict(SNAP=30)),
    "dark jazz (LOW)": (dict(TONE=40, DCAY=85, BELL=35, HIT=40, COLR=70), dict(SET=96, DRFT=110, NOIS=25, SWEL=25)),
    "sizzle (rivets)": (dict(TONE=40, DCAY=92, BELL=35, HIT=40, COLR=70),
                        dict(SET=96, DRFT=110, NOIS=25, SWEL=25, RIVT=95)),
    "wash (WIDE)": (dict(COLR=105, TONE=70, HIT=85, BELL=10, DCAY=85), dict(SET=32, NOIS=40, SWEL=35)),
    "trash (CLUSTER)": (dict(COLR=110, DRIV=70, TONE=60), dict(SET=64)),
    "worst": ({n: 127 for n in DR.PLACES[DR.RIDE].PNAMES[:7]}, {n: 127 for n in DR.PLACES[DR.RIDE].PNAMES2}),
}
CRASH_CASES = {
    "crash (start)": ({}, {}),
    "long": (dict(DCAY=108, HIT=100), dict(SWEL=80)),
    "splash": (dict(TUNE=82, DCAY=45, HIT=55, TONE=92, BELL=0), dict(SWEL=40)),
    "china (CLUSTER)": (dict(TUNE=56, COLR=120, DRIV=75, TONE=50, DCAY=70, HIT=50, BELL=25),
                        dict(SET=64, SWEL=30, NOIS=20)),
    "reverse (ATK)": (dict(DCAY=10, HIT=10), dict(ATK=110, SNAP=0, SWEL=0)),
    "gong (LOW)": (dict(TUNE=32, DCAY=115, HIT=40, BELL=70, TONE=30), dict(SET=96, SWEL=100)),
    "worst": ({n: 127 for n in DR.PLACES[DR.CRSH].PNAMES[:7]}, {n: 127 for n in DR.PLACES[DR.CRSH].PNAMES2}),
}
V4_CASES = [(DR.CLAP, k) for k in CLAP_CASES] + [(DR.RIDE, k) for k in RIDE_CASES] + [(DR.CRSH, k) for k in CRASH_CASES]


def _v4_knobs(t: int, p1: dict, p2: dict) -> tuple[dict, dict]:
    P = DR.PLACES[t]
    return ({**dict(zip(P.PNAMES[:7], P.DEFAULTS[:7])), **p1}, {**dict(zip(P.PNAMES2, P.DEFAULTS2)), **p2})


@pytest.mark.parametrize("t,case", V4_CASES)
def test_v4_model_matches_reference(t, case):
    cases = {DR.CLAP: CLAP_CASES, DR.RIDE: RIDE_CASES, DR.CRSH: CRASH_CASES}[t]
    p1, p2 = _v4_knobs(t, *cases[case])
    blocks = 90
    a = render_model(p1, p2, {0: 60.0}, blocks, t)
    b = render_ref(p1, p2, {0: 60.0}, blocks, t)[:len(a)]
    assert np.isfinite(a).all() and float(np.abs(b).max()) > (1e-5 if p2.get("ATK") else 0.01)   # (ATK: a swell)
    e = _err_db(a, b)
    print(f"{DR.TYPES[t]} {case}: model vs reference {e:.1f} dB under the peak, peak {float(np.abs(a).max()):.3f}")
    assert e < DSL_TOL_DB, (case, e)


@pytest.mark.parametrize("t", [DR.CLAP, DR.RIDE, DR.CRSH])
def test_v4_random_corners_are_finite_and_under_one(t):
    P = DR.PLACES[t]
    rng = random.Random(17 + t)
    for _ in range(6):
        p1 = {n: rng.randint(0, 127) for n in P.PNAMES[:7]}
        p2 = {n: rng.randint(0, 127) for n in P.PNAMES2}
        a = render_model(p1, p2, {0: float(rng.randint(36, 84))}, 40, t, vel=rng.choice((127, rng.randint(1, 127))))
        assert np.isfinite(a).all() and float(np.abs(a).max()) < 1.0, (p1, p2, float(np.abs(a).max()))


@pytest.mark.parametrize("t", [DR.CLAP, DR.RIDE, DR.CRSH])
def test_v4_soft_hit_matches_reference(t):
    P = DR.PLACES[t]
    p1, p2 = dict(zip(P.PNAMES[:7], P.DEFAULTS[:7])), dict(zip(P.PNAMES2, P.DEFAULTS2))
    a = render_model(p1, p2, {0: 60.0}, 50, t, vel=40)
    b = render_ref(p1, p2, {0: 60.0}, 50, t, vel=40)[:len(a)]
    full = render_model(p1, p2, {0: 60.0}, 50, t)
    e = _err_db(a, b)
    print(f"{DR.TYPES[t]} at velocity 40: model vs reference {e:.1f} dB, peak {float(np.abs(a).max()):.3f} "
          f"(full {float(np.abs(full).max()):.3f})")
    assert e < DSL_TOL_DB and float(np.abs(a).max()) <= float(np.abs(full).max())


def test_v4_reference_corners_under_one():
    """the references (no DSP: quick) at 40 random corners each, every knob anywhere, velocities and notes: no NaN,
    under 1.0 (CLAP's and the cymbals' outputs held under 0.99)"""
    rng = random.Random(4)
    for kind, cls in (("CLAP", REF.Clap), ("RIDE", REF.Ride), ("CRASH", REF.Crash)):
        for _ in range(40):
            p1 = {n: rng.randint(0, 127) for n in cls.P1}
            p2 = {n: rng.randint(0, 127) / 127 for n in cls.P2}
            v = cls(p1, p2)
            v.trig(float(rng.randint(36, 84)), rng.choice((1.0, 0.7, 0.3)))
            y = v.render(int(0.4 * REF.FS))
            assert np.isfinite(y).all() and float(np.abs(y).max()) < 1.0, (kind, p1, p2)


def test_v4_set_and_count_read_as_the_page_shows():
    """the cymbals' SET (page 2 A, four detents) and CLAP's CNT (page 1 D, eight): for every value their records hold,
    the DSP's reading (ref.cym_set on the float32 value; CNT's knob) is the choice the page shows ((knob x n) >> 7,
    knob = (v 254 + top) / (2 top))"""
    _rid, _slot, lo, top = PM.FX_PARAMS[DR.PLACES[DR.RIDE].PNAMES2.index("SET")]
    assert lo == 0
    for v in range(top + 1):
        q = float(np.float32(np.float32(v) * np.float32(1.0 / top)))
        assert REF.cym_set(q) == (((v * 254 + top) // (2 * top)) * 4) >> 7, v
    _rid, _slot, lo, top = PM.PARAMS[DR.PLACES[DR.CLAP].PNAMES.index("CNT")]
    assert (lo, top) == (0, 127)
    for v in range(top + 1):
        assert REF.clap_count(v) - 1 == (((v * 254 + top) // (2 * top)) * 8) >> 7, v


def test_v4_levels_re_kick():
    """the types' levels (the User): Vpp of CLAP's 808 point (its start) 2.0 dB under KICK 808 LONG's, RIDE's and CRASH's
    starts 6.6 dB under it (levels_v3.md's method), on the reference, within 0.1 dB"""
    def vpp(y):
        return float(y.max() - y.min())
    k = REF.render({**REF.Kick.D1, **CASES["808 long"][0]},
                   {**{n: REF.Kick.D2[n] for n in REF.Kick.P2}, **{n: v / 127 for n, v in CASES["808 long"][1].items()}},
                   seconds=3.5, kind="KICK")
    for kind, sec, db in (("CLAP", 1.2, -2.0), ("RIDE", 4.0, -6.6), ("CRASH", 5.0, -6.6)):
        y = REF.render(seconds=sec, kind=kind)
        got = 20 * np.log10(vpp(y) / vpp(k))
        print(f"{kind}: {got:.2f} dB re KICK 808 LONG")
        assert abs(got - db) < 0.1, (kind, got)


# stage 5 (the User, 2026-11-20: no digital clipping): each type's worst setting the peak survey found
# (scratch/drum-engine/click/peaks.py, random and corner settings, the output holds lifted): the peak under 0.95 (hill-climbed maxima at KIT_TRIM 0.70: KICK 0.874, RIDE and OPHH below)
FULL_SCALE_WORST = [
    ("KICK", dict(TUNE=64, DCAY=64, SWEP=98, SWTM=127, CLIK=64, CLKT=64, DRIV=0),
     dict(SHAP=64, HOLD=64, SIGH=127, CLKL=103, NOIS=127, VEL=0, SWHD=127, CURV=127), 72.0),
    ("SNARE", dict(TUNE=18, DCAY=127, TONE=0, MODE=0, SNAP=38, NOIS=64, DRIV=0),
     dict(WIRE=0, GLID=64, BUZZ=0, WTON=127, WATK=64, SIZZ=127, VEL=0, WCHR=63), 60.0),
    ("CLHH", dict(TUNE=127, DCAY=0, TONE=64, NOIS=64, COLR=0, SNAP=127, DRIV=0),
     dict(HPF=64, Q=64, LOWB=0, VEL=64, TOP=64, DRFT=127), 72.0),
    ("OPHH", dict(TUNE=81, DCAY=102, TONE=30, NOIS=70, COLR=64, SNAP=3, DRIV=0),
     dict(HPF=41, Q=40, LOWB=2, VEL=118, TOP=120, DRFT=118), 60.0),
    ("TOM", dict(TUNE=64, DCAY=127, SWEP=64, TONE=127, SNAP=0, NOIS=17, DRIV=0),
     dict(SWTM=0, MODE=64, SHAP=0, RNGE=127, VEL=111), 60.0),
    ("CLAP", dict(TUNE=64, DCAY=127, TONE=0, CNT=64, SPRD=72, TAIL=64, DRIV=0),
     dict(SNAP=0, Q=127, HUMN=0, GRP=0, TLTN=127, TATK=0, RAMP=0, VEL=0), 60.0),
    ("RIDE", dict(TUNE=127, DCAY=0, TONE=112, BELL=127, COLR=64, HIT=127, DRIV=0),
     dict(SET=64, SWEL=0, ATK=0, SNAP=0, NOIS=0, DRFT=64, RIVT=127, VEL=64), 60.0),
    # (hill-climbed: a high TUNE's top band into the soft clip, no stick, bell, ring or noise: the pitch's level held, 2026-11-21)
    ("RIDE", dict(TUNE=123, DCAY=124, TONE=95, BELL=117, COLR=50, HIT=125, DRIV=20),
     dict(SET=64, SWEL=1, ATK=30, SNAP=0, NOIS=0, DRFT=47, RIVT=127, VEL=64), 97.0),
    ("KICK", dict(TUNE=64, DCAY=127, SWEP=79, SWTM=127, CLIK=64, CLKT=101, DRIV=0),
     dict(SHAP=117, HOLD=64, SIGH=127, CLKL=127, NOIS=127, VEL=0, SWHD=127, CURV=127), 54.0),
    ("CRASH", dict(TUNE=64, DCAY=56, TONE=64, BELL=127, COLR=64, HIT=127, DRIV=0),
     dict(SET=64, SWEL=0, ATK=0, SNAP=0, NOIS=0, DRFT=64, RIVT=103, VEL=68), 60.0),
]


@pytest.mark.parametrize("kind,p1,p2,note", FULL_SCALE_WORST, ids=[w[0] for w in FULL_SCALE_WORST])
def test_no_type_reaches_full_scale(kind, p1, p2, note):
    y = REF.render(p1, {n: v / 127 for n, v in p2.items()}, hits=[(0.0, note, 1.0)], seconds=1.2 if kind == "RIDE" else 0.35, kind=kind)
    pk = float(np.abs(y).max())
    print(f"{kind}: worst-case peak {pk:.3f}")
    assert np.isfinite(y).all() and pk < 0.95, (kind, pk)
