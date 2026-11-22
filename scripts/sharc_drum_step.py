"""2026-11-20 (DRUM, machine type 56; docs/drum.md): the SHARC runner's DRUM step. DRUM on track 0 at settings across
its range (KICK: its start, a tick, an 808, a chirp-click techno kick, a driven held body, the worst-cost corner, two
random corners; SNARE (stage 2b): its start, an 808, a loose acoustic, a trap clap-snare, a rim, the worst corner, two
random corners; the hats (stage 2c): CLOSED at its start, a tick, a 909, an acoustic one (ring, low band), the worst, a
random corner, OPEN at its start, washy, the worst, a random corner), a retrig on a sounding hit, a retrig across types
(a KICK cut by a SNARE; an OPEN cut by a CLOSED and back), a soft hit of each type (velocity 40), the choke (two slots
on one track: slot 1's CLOSED hit chokes slot 0's OPEN; on two tracks it does not), the same-block choke (2026-11-20:
a CLOSED and an OPEN hit in one block, the OPEN on slot 0 or on slot 1: the OPEN choked from the next block in both
orders, the two orders the same; controls on two tracks); stage 3 (2026-11-20): the re-voiced points (KICK 909 with
SWHD, 808 BOOM; SNARE 808 with WCHR 127, 909 with WCHR 0; CLOSED 808 with TOP, DRFT 0; OPEN 808 with TOP, OPEN long:
the exponential tail), TOM (its start, RNGE HI, the 808 LO, the 909 MID, the conga, the worst, a random corner, a soft
hit, a KICK cut by a TOM), each run bit-exact to the model (dnfw.perc.program run on the DSP's memory at PERC's entry, every block,
sharc_waverider_m5.run_blocks). Checks: every run bit-exact, audible, finite and under 4.0; the retrigs and the soft
hits differ from the plain hit where they should. Numbers: each run's instructions a block (the runner's count: the
whole program's, DRUM's voice in it)."""

from __future__ import annotations

import math
import random

RUN_BLOCKS = 24
# KICK's settings: page 1 (TUNE DCAY SWEP SWTM CLIK CLKT DRIV), page 2 (SHAP HOLD SIGH CLKL NOIS VEL SWHD CURV), as knobs
# (stage 5: SNAP's old values as CLIK's, SNAP / 2)
SETTINGS = {
    "start": ({}, {}),
    "tick": (dict(TUNE=127, DCAY=0, SWEP=30, SWTM=10, CLIK=55, CLKT=70, DRIV=10), dict(HOLD=0, CLKL=15, NOIS=0)),
    "808": (dict(TUNE=55, DCAY=106, SWEP=23, SWTM=44, CLIK=7, CLKT=38, DRIV=5), dict(SHAP=0, HOLD=0, SIGH=64)),
    "techno": (dict(DCAY=70, SWEP=55, SWTM=45, CLIK=30, CLKT=100, DRIV=55), dict(SHAP=20, HOLD=25, CLKL=35)),
    "held": (dict(DCAY=127, SWEP=0, CLIK=0, DRIV=100), dict(HOLD=127, SIGH=0, NOIS=0, SHAP=60)),
    # the dearest: the click between pulse and chirp (both paths), full drive (ADAA's division every sample), air
    "worst": (dict(TUNE=127, DCAY=127, SWEP=127, SWTM=127, CLIK=64, CLKT=102, DRIV=127),
              dict(SHAP=127, HOLD=127, SIGH=127, CLKL=127, NOIS=127, VEL=127, SWHD=127, CURV=127)),
    # stage 5: CLIK at its ends (body+noise only; the click only), CURV a line and the concave
    "noclick": (dict(CLIK=0), {}),
    "clickonly": (dict(CLIK=127, CLKT=40), dict(CLKL=40)),
    "curvline": (dict(SWEP=80, SWTM=70), dict(CURV=0)),
    "curvconc": (dict(SWEP=80, SWTM=70), dict(CURV=127, SWHD=20)),
    # stage 3: the 909 re-voiced (SWHD 16 ms, HOLD 40 ms), 808 BOOM (the sigh from the drive's level)
    "909r": (dict(TUNE=51, DCAY=82, SWEP=21, SWTM=65, CLIK=24, CLKT=67, DRIV=26),
             dict(SHAP=17, HOLD=51, SIGH=13, CLKL=34, NOIS=10, VEL=64, SWHD=68)),
    "boom": (dict(TUNE=48, DCAY=115, SWEP=32, SWTM=45, CLIK=10, CLKT=36, DRIV=42), dict(SHAP=0, HOLD=30, SIGH=64, NOIS=0)),
}
# SNARE's (stage 2b): page 1 (TUNE DCAY TONE MODE SNAP NOIS DRIV), page 2 (WIRE GLID BUZZ WTON WATK SIZZ VEL; WCHR on H)
SNARE_SETTINGS = {
    "start": ({}, {}),
    "808": (dict(TUNE=64, DCAY=57, TONE=33, MODE=0, SNAP=33, NOIS=64, DRIV=19),
            dict(WIRE=48, GLID=13, BUZZ=0, WTON=76, WATK=22, SIZZ=0)),
    "loose": (dict(TUNE=53, DCAY=80, TONE=105, MODE=127, SNAP=70, NOIS=90, DRIV=25),
              dict(WIRE=85, GLID=75, BUZZ=90, WTON=55, WATK=50, SIZZ=40)),
    "trap": (dict(TUNE=70, DCAY=35, TONE=50, MODE=20, SNAP=60, NOIS=110, DRIV=35),
             dict(WIRE=70, GLID=44, BUZZ=0, WTON=80, WATK=120, SIZZ=50)),
    "rim": (dict(TUNE=95, DCAY=15, TONE=60, MODE=30, SNAP=127, NOIS=35, DRIV=30),
            dict(WIRE=30, GLID=44, BUZZ=44, WTON=95, WATK=22, SIZZ=0)),
    # the dearest: every knob up (the 4th mode, the sizzle, full drive) but WATK just under the clap bursts (88): the
    # wires' rise and decay run from the first sample (the bursts' countdown, while it runs, is cheaper)
    "worst": ({n: 127 for n in ("TUNE", "DCAY", "TONE", "MODE", "SNAP", "NOIS", "DRIV")},
              {**{n: 127 for n in ("WIRE", "GLID", "BUZZ", "WTON", "SIZZ", "VEL")}, "WATK": 88, "WCHR": 0}),
    # stage 3: the 808 re-voiced (WCHR 127: the high-pass), the 909 re-voiced (WCHR 0: the band, the hold, the close)
    "808r": (dict(TUNE=64, DCAY=69, TONE=40, MODE=18, SNAP=40, NOIS=38, DRIV=5),
             dict(WIRE=75, GLID=0, BUZZ=0, WTON=11, WATK=0, SIZZ=0, VEL=64, WCHR=127)),
    "909r": (dict(TUNE=75, DCAY=56, TONE=40, MODE=127, SNAP=45, NOIS=100, DRIV=10),
             dict(WIRE=94, GLID=48, BUZZ=0, WTON=44, WATK=0, SIZZ=0, VEL=64, WCHR=0)),
}
# the hats' (stage 2c): page 1 (TUNE DCAY TONE NOIS COLR SNAP DRIV), page 2 (HPF Q LOWB VEL TOP DRFT); stage 1b's points
HAT_SETTINGS = {
    "clhh-start": ("CLHH", {}, {}),
    "clhh-tick": ("CLHH", dict(DCAY=0, TONE=85, NOIS=50, SNAP=110), dict(HPF=90)),
    "clhh-909": ("CLHH", dict(DCAY=55, TONE=75, NOIS=100, COLR=30, SNAP=60, DRIV=20), dict(Q=15)),
    "clhh-acoustic": ("CLHH", dict(DCAY=44, TONE=60, NOIS=70, COLR=115, SNAP=80), dict(Q=25, LOWB=60)),
    # the dearest: every knob up (the ring's pairs, the low band, the drive: all of a hat runs every sample anyway)
    "clhh-worst": ("CLHH", {n: 127 for n in ("TUNE", "DCAY", "TONE", "NOIS", "COLR", "SNAP", "DRIV")},
                   {n: 127 for n in ("HPF", "Q", "LOWB", "VEL", "TOP", "DRFT")}),
    # stage 3: the 808 re-voiced (TOP 42), the metal static (DRFT 0)
    "clhh-808r": ("CLHH", dict(DCAY=75), dict(TOP=42)),
    "clhh-drft0": ("CLHH", {}, dict(DRFT=0)),
    "ophh-start": ("OPHH", {}, {}),
    "ophh-washy": ("OPHH", dict(DCAY=95, TONE=50, NOIS=60, COLR=127, DRIV=40), dict(Q=10, LOWB=50)),
    "ophh-worst": ("OPHH", {n: 127 for n in ("TUNE", "DCAY", "TONE", "NOIS", "COLR", "SNAP", "DRIV")},
                   {n: 127 for n in ("HPF", "Q", "LOWB", "VEL", "TOP", "DRFT")}),
    # stage 3: the 808 re-voiced (TOP 10), a long OPEN (DCAY 110: the exponential tail)
    "ophh-808r": ("OPHH", dict(DCAY=66, TONE=56), dict(TOP=10)),
    "ophh-long": ("OPHH", dict(DCAY=110), {}),
}


def _tk(st: int) -> int:
    return round((0.5 + st / 48.0) * 127)


# TOM's (stage 3): page 1 (TUNE DCAY SWEP TONE SNAP NOIS DRIV), page 2 (SWTM MODE SHAP RNGE VEL)
TOM_SETTINGS = {
    "tom-start": ({}, {}),
    "tom-rnge-hi": ({}, dict(RNGE=127)),
    "tom-808lo": (dict(TUNE=_tk(-3), DCAY=77, SWEP=21, TONE=0, NOIS=15, SNAP=10, DRIV=0), dict(SWTM=64, SHAP=0)),
    "tom-909mid": (dict(TUNE=_tk(-1), DCAY=80, SWEP=25, TONE=115, NOIS=0, SNAP=80, DRIV=30),
                   dict(SWTM=87, MODE=0, SHAP=127)),
    "tom-conga": (dict(TUNE=_tk(17), SWEP=13, DCAY=54, TONE=0, NOIS=0, SNAP=10, DRIV=0), dict(SWTM=64, SHAP=0)),
    # the dearest: TOM is branch-free (every part every sample): every knob up
    "tom-worst": ({n: 127 for n in ("TUNE", "DCAY", "SWEP", "TONE", "SNAP", "NOIS", "DRIV")},
                  {n: 127 for n in ("SWTM", "MODE", "SHAP", "RNGE", "VEL")}),
}
# stage 4 (2026-11-20): CLAP's page 1 (TUNE DCAY TONE CNT SPRD TAIL DRIV), page 2 (SNAP Q HUMN GRP TLTN TATK RAMP VEL);
# the cymbals' page 1 (TUNE DCAY TONE BELL COLR HIT DRIV), page 2 (SET SWEL ATK SNAP NOIS DRFT RIVT VEL)
CLAP_SETTINGS = {
    "clap-start": ({}, {}),
    "clap-909": (dict(TUNE=61, DCAY=41, TONE=64, CNT=56, SPRD=76, TAIL=27, DRIV=22), dict(SNAP=53, Q=59, TATK=0, RAMP=104)),
    "clap-group": (dict(DCAY=60, TONE=60, CNT=72, SPRD=70, TAIL=85), dict(Q=30, HUMN=90, GRP=110)),
    "clap-snap": (dict(TUNE=87, DCAY=15, TONE=80, CNT=0, TAIL=30), dict(SNAP=110, Q=75, TATK=0)),
    # every knob up (8 bursts, GRP, the drive): CLAP runs every part every sample (GRP's level 0 when off)
    "clap-worst": ({**{n: 127 for n in ("TUNE", "DCAY", "TONE", "CNT", "SPRD", "TAIL", "DRIV")}, "TAIL": 64},
                   {n: 127 for n in ("SNAP", "Q", "HUMN", "GRP", "TLTN", "TATK", "RAMP", "VEL")}),
}
_CY1, _CY2 = ("TUNE", "DCAY", "TONE", "BELL", "COLR", "HIT", "DRIV"), ("SET", "SWEL", "ATK", "SNAP", "NOIS", "DRFT", "RIVT", "VEL")
CYM_SETTINGS = {
    "ride-start": ("RIDE", {}, {}),
    "ride-darkjazz": ("RIDE", dict(TONE=40, DCAY=85, BELL=35, HIT=40, COLR=70), dict(SET=96, DRFT=110, NOIS=25, SWEL=25)),
    "ride-sizzle": ("RIDE", dict(TONE=40, DCAY=92, BELL=35, HIT=40, COLR=70),
                    dict(SET=96, DRFT=110, NOIS=25, SWEL=25, RIVT=95)),
    "ride-trash": ("RIDE", dict(COLR=110, DRIV=70, TONE=60), dict(SET=64)),
    # every knob up but ATK 0 (the decays run from the first sample; ATK's swell, while it runs, is cheaper)
    "ride-worst": ("RIDE", {n: 127 for n in _CY1}, {**{n: 127 for n in _CY2}, "ATK": 0}),
    "crash-start": ("CRSH", {}, {}),
    "crash-reverse": ("CRSH", dict(DCAY=10, HIT=10), dict(ATK=110, SNAP=0, SWEL=0)),
    "crash-gong": ("CRSH", dict(TUNE=32, DCAY=115, HIT=40, BELL=70, TONE=30), dict(SET=96, SWEL=100)),
    "crash-worst": ("CRSH", {n: 127 for n in _CY1}, {**{n: 127 for n in _CY2}, "ATK": 0}),
}
RETRIG_AT = 12
SOFT_VEL = 40
CHOKE_AT = 10                                  # the two-slot choke: slot 1's CLOSED hit, slot 0's OPEN at block 1


def cost_cases() -> dict:
    """dsp_cost / sharc_cost: name -> (type, page 1, page 2), each type at its start and its dearest"""
    from dnfw.engines.drum import drum as DR
    return {"DRUM-KICK": (DR.KICK, {}, {}), "DRUM-KICK-WORST": (DR.KICK, *SETTINGS["worst"]),
            "DRUM-SNAR": (DR.SNARE, {}, {}), "DRUM-SNAR-WORST": (DR.SNARE, *SNARE_SETTINGS["worst"]),
            "DRUM-CLHH": (DR.CLHH, {}, {}), "DRUM-CLHH-WORST": (DR.CLHH, *HAT_SETTINGS["clhh-worst"][1:]),
            "DRUM-OPHH": (DR.OPHH, {}, {}), "DRUM-OPHH-WORST": (DR.OPHH, *HAT_SETTINGS["ophh-worst"][1:]),
            "DRUM-TOM": (DR.TOM, {}, {}), "DRUM-TOM-WORST": (DR.TOM, *TOM_SETTINGS["tom-worst"]),
            "DRUM-CLAP": (DR.CLAP, {}, {}), "DRUM-CLAP-WORST": (DR.CLAP, *CLAP_SETTINGS["clap-worst"]),
            "DRUM-RIDE": (DR.RIDE, {}, {}), "DRUM-RIDE-WORST": (DR.RIDE, *CYM_SETTINGS["ride-worst"][1:]),
            "DRUM-CRSH": (DR.CRSH, {}, {}), "DRUM-CRSH-WORST": (DR.CRSH, *CYM_SETTINGS["crash-worst"][1:])}


def knobs_of(t: int, p1: dict, p2: dict) -> tuple[list, dict]:
    """type T's page 1 as the eight knobs (TYPE on H), page 2 by name; the type's starts where not given"""
    from dnfw.engines.drum import drum as DR
    P = DR.PLACES[t]
    k1 = [p1.get(n, d) for n, d in zip(P.PNAMES[:7], P.DEFAULTS[:7])] + [DR.type_knob(t)]
    return k1, {n: p2.get(n, d) for n, d in zip(P.PNAMES2, P.DEFAULTS2)}


def _knobs():
    """run name -> (type, page 1, page 2)"""
    from dnfw.engines.drum import drum as DR
    rng = random.Random(56)
    s = {n: (DR.KICK, *v) for n, v in SETTINGS.items()}
    for k in range(2):
        s[f"random{k}"] = (DR.KICK, {n: rng.randint(0, 127) for n in DR.PNAMES[:7]},
                           {n: rng.randint(0, 127) for n in DR.PNAMES2})
    P = DR.PLACES[DR.SNARE]
    s.update({f"snare-{n}": (DR.SNARE, *v) for n, v in SNARE_SETTINGS.items()})
    for k in range(2):
        s[f"snare-random{k}"] = (DR.SNARE, {n: rng.randint(0, 127) for n in P.PNAMES[:7]},
                                 {n: rng.randint(0, 127) for n in P.PNAMES2})
    s.update({n: ((DR.CLHH, DR.OPHH)[v[0] == "OPHH"], *v[1:]) for n, v in HAT_SETTINGS.items()})
    for t in (DR.CLHH, DR.OPHH):
        P = DR.PLACES[t]
        s[f"{DR.TYPES[t].lower()}-random"] = (t, {n: rng.randint(0, 127) for n in P.PNAMES[:7]},
                                             {n: rng.randint(0, 127) for n in P.PNAMES2})
    s.update({n: (DR.TOM, *v) for n, v in TOM_SETTINGS.items()})
    P = DR.PLACES[DR.TOM]
    s["tom-random"] = (DR.TOM, {n: rng.randint(0, 127) for n in P.PNAMES[:7]},
                       {n: rng.randint(0, 127) for n in P.PNAMES2})
    # stage 4 (2026-11-20): CLAP, RIDE, CRASH (the random corners after every earlier draw: those are as before)
    s.update({n: (DR.CLAP, *v) for n, v in CLAP_SETTINGS.items()})
    s.update({n: ((DR.RIDE, DR.CRSH)[v[0] == "CRSH"], *v[1:]) for n, v in CYM_SETTINGS.items()})
    for t, name in ((DR.CLAP, "clap"), (DR.RIDE, "ride"), (DR.CRSH, "crash")):
        P = DR.PLACES[t]
        s[f"{name}-random"] = (t, {n: rng.randint(0, 127) for n in P.PNAMES[:7]},
                               {n: rng.randint(0, 127) for n in P.PNAMES2})
    return s


def rec2(j: int) -> tuple:
    """page-2 control j's record: PERC's page-2 records, the eighth (H) its TYPE record (0..127: SNARE's WCHR, q7)"""
    from dnfw.perc import machines as PM
    return PM.FX_PARAMS[j] if j < 7 else PM.TYPE_REC + (0, 127)


def _frames(m5, sound, machines, t: int, p1: dict, p2: dict, trig=(1,), vel: int | None = None, then=None):
    """THEN = (block, type, page 1, page 2): from that block on the frames carry that type's knobs (a retrig across
    types when the block is a trig)"""
    from dnfw.mnm import machines as MM
    from dnfw.perc import live as PL
    from dnfw.perc import machines as PM
    k = MM.NAMES.index("DRUM")
    first = knobs_of(t, p1, p2)
    second = knobs_of(*then[1:]) if then else first

    def fb(b):
        k1, k2 = second if then and b >= then[0] else first
        f = m5.base_frame(sound, machines, t0=MM.TYPES[k], overrides=m5.mnm_words(k, k1), note=0x3C00,
                          trigger=b in trig)
        for j, x in enumerate(k2.values()):
            _rid, slot, lo, top = rec2(j)
            f.param(0, slot, PL.knob_word(x, top, lo))
        if vel is not None:
            f.param(0, PM.VEL_SLOT, vel << 8)
        return f.to_bytes()
    return fb


ROUTE_FRAME = 0xA5A                           # the frame's slot map: 16 x s16, the track each voice slot plays
                                               # (dnfw.inserts.design.ROUTE: the frame's 0xa5a + 2 s)


def _two_slots(m5, sound, machines, tracks=(0, 0), open_slot=0, open_at=1, closed_at=CHOKE_AT):
    """an OPEN hit (DCAY 100) on slot OPEN_SLOT at block OPEN_AT, a CLOSED hit on the other slot at CLOSED_AT; slot s on
    track TRACKS[s]"""
    from dnfw.engines.drum import drum as DR
    from dnfw.mnm import machines as MM
    from dnfw.perc import live as PL
    from dnfw.perc import machines as PM
    k = MM.NAMES.index("DRUM")
    o = knobs_of(DR.OPHH, dict(DCAY=100), {})
    c = knobs_of(DR.CLHH, {}, {})
    knobs = (o, c) if open_slot == 0 else (c, o)
    hits = (open_at, closed_at) if open_slot == 0 else (closed_at, open_at)

    def fb(b):
        f = m5.base_frame(sound, machines, t0=MM.TYPES[k], overrides=m5.mnm_words(k, knobs[0][0]), note=0x3C00,
                          trigger=b == hits[0])
        f.header(FR_MACHINE, 1, MM.TYPES[k])
        for slot, w in m5.mnm_words(k, knobs[1][0]).items():
            f.param(1, slot, w)
        for t in (0, 1):
            for j, x in enumerate(knobs[t][1].values()):
                _rid, slot, lo, top = rec2(j)
                f.param(t, slot, PL.knob_word(x, top, lo))
        for s, trk in enumerate(tracks):
            f.put(ROUTE_FRAME + 2 * s, trk)
        if b == hits[1]:
            f.trigger(1)
        return f.to_bytes()
    return fb


SAME_AT = 2                                    # the same-block choke: both hits in this block


FR_MACHINE = 148                               # (dnfw.waverider.frame.MACHINE: the header's machine types)


def runs(m5, init, sound, machines) -> dict:
    from dnfw.engines.drum import drum as DR
    out = {}

    def run(fb):
        return m5._slim(m5.run_blocks(init, fb, RUN_BLOCKS))
    for name, (t, p1, p2) in _knobs().items():
        out[name] = run(_frames(m5, sound, machines, t, p1, p2))
    out["retrig"] = run(_frames(m5, sound, machines, DR.KICK, {}, {}, trig=(1, RETRIG_AT)))
    out["kick>snare"] = run(_frames(m5, sound, machines, DR.KICK, {}, {}, trig=(1, RETRIG_AT),
                                    then=(RETRIG_AT, DR.SNARE, {}, {})))
    out["soft"] = run(_frames(m5, sound, machines, DR.KICK, {}, {}, vel=SOFT_VEL))
    out["snare-soft"] = run(_frames(m5, sound, machines, DR.SNARE, {}, {}, vel=SOFT_VEL))
    # the hats: a CLOSED hit taking a sounding OPEN one on its voice and back, a soft hit, the two-slot choke (one
    # track) and its control (two tracks)
    out["ophh>clhh"] = run(_frames(m5, sound, machines, DR.OPHH, dict(DCAY=100), {}, trig=(1, RETRIG_AT),
                                   then=(RETRIG_AT, DR.CLHH, {}, {})))
    out["clhh>ophh"] = run(_frames(m5, sound, machines, DR.CLHH, {}, {}, trig=(1, RETRIG_AT),
                                   then=(RETRIG_AT, DR.OPHH, {}, {})))
    out["clhh-soft"] = run(_frames(m5, sound, machines, DR.CLHH, {}, {}, vel=SOFT_VEL))
    # stage 3: TOM's soft hit, a KICK cut by a TOM (the declick across types)
    out["tom-soft"] = run(_frames(m5, sound, machines, DR.TOM, {}, {}, vel=SOFT_VEL))
    out["kick>tom"] = run(_frames(m5, sound, machines, DR.KICK, {}, {}, trig=(1, RETRIG_AT),
                                  then=(RETRIG_AT, DR.TOM, {}, {})))
    # stage 4: soft hits; a KICK cut by a CLAP; a CLOSED hat cut by a RIDE and back (the metal's words shared)
    out["clap-soft"] = run(_frames(m5, sound, machines, DR.CLAP, {}, {}, vel=SOFT_VEL))
    out["ride-soft"] = run(_frames(m5, sound, machines, DR.RIDE, {}, {}, vel=SOFT_VEL))
    out["kick>clap"] = run(_frames(m5, sound, machines, DR.KICK, {}, {}, trig=(1, RETRIG_AT),
                                   then=(RETRIG_AT, DR.CLAP, {}, {})))
    out["clhh>ride"] = run(_frames(m5, sound, machines, DR.CLHH, {}, {}, trig=(1, RETRIG_AT),
                                   then=(RETRIG_AT, DR.RIDE, {}, {})))
    out["ride>clhh"] = run(_frames(m5, sound, machines, DR.RIDE, {}, {}, trig=(1, RETRIG_AT),
                                   then=(RETRIG_AT, DR.CLHH, {}, {})))
    out["choke"] = run(_two_slots(m5, sound, machines))
    out["nochoke"] = run(_two_slots(m5, sound, machines, tracks=(0, 1)))
    # 2026-11-20 (the User): a CLOSED and an OPEN hit on one track in ONE block: the OPEN always choked, whatever the
    # slots' render order (slot 0 OPEN: it renders first; slot 1 OPEN: the CLOSED renders first); controls on two tracks
    for os_ in (0, 1):
        out[f"same{os_}"] = run(_two_slots(m5, sound, machines, open_slot=os_, open_at=SAME_AT, closed_at=SAME_AT))
        out[f"samefree{os_}"] = run(_two_slots(m5, sound, machines, tracks=(0, 1), open_slot=os_, open_at=SAME_AT,
                                               closed_at=SAME_AT))
    return out


def step(m5, init, sound, machines) -> dict:
    rr = runs(m5, init, sound, machines)
    exact = {k: m5.perc_exact(r) for k, r in rr.items() if r["ok"]}
    series = {k: m5.perc_series(r, 0) for k, r in rr.items() if r["ok"]}
    peaks = {k: max((abs(x) for x in s), default=0.0) for k, s in series.items()}
    B = m5.BLOCK if hasattr(m5, "BLOCK") else 32
    n = {"exact_voice_blocks_out_state_mismatches": exact,
         "peaks": {k: round(v, 4) for k, v in peaks.items()},
         "instructions_per_block": {k: round(r.get("instructions", 0) / RUN_BLOCKS) for k, r in rr.items() if r["ok"]},
         "halts": {k: r.get("halt") for k, r in rr.items() if not r["ok"]}}
    c = {}
    c["every DRUM run returns every block"] = all(r["ok"] for r in rr.values())
    c["every DRUM run (" + ", ".join(rr) + "), every block, bit-exact to the model"] = (
        c["every DRUM run returns every block"] and all(v[0] > 0 and v[1:] == (0, 0) for v in exact.values()))
    c["every DRUM run sounds (peak > 0.01), finite and under 4.0"] = (
        bool(series) and all(peaks[k] > 0.01 and all(math.isfinite(x) and abs(x) <= 4.0 for x in s)
                             for k, s in series.items()))
    cut = (RETRIG_AT + 1) * B
    for r, what in (("retrig", "the retrig"), ("kick>snare", "the retrig across types (KICK, then SNARE)"),
                    ("kick>tom", "the retrig across types (KICK, then TOM)"),
                    ("kick>clap", "the retrig across types (KICK, then CLAP)")):
        if r in series and "start" in series:
            a, b = series["start"], series[r]
            c[what + ": the same as one hit until it, a new hit after it"] = (
                a[:RETRIG_AT * B] == b[:RETRIG_AT * B] and a[cut:] != b[cut:])
    r = ("ophh>clhh", "a CLOSED trig on a sounding OPEN hit (one voice)")
    if r[0] in series and "clhh>ophh" in series:
        a, b = series["clhh>ophh"], series[r[0]]
        c[r[1] + ", and an OPEN trig on a CLOSED one: each a new hit after the trig"] = (
            a[cut:] != b[cut:] and any(abs(x) > 0.01 for x in b[cut:]))
    if "choke" in series and "nochoke" in series:
        # slot 0's OPEN voice: the same until the CLOSED hit on slot 1; then, on one track, choked (its RMS 10..20
        # blocks after the hit under a tenth of the voice on another track's)
        o, o2 = series["choke"], series["nochoke"]
        at = CHOKE_AT * B
        late = slice(at + 10 * B, at + 20 * B)
        rms = [math.sqrt(sum(x * x for x in v[late]) / max(len(v[late]), 1)) for v in (o, o2)]
        n["choke_open_rms_after"] = [round(x, 6) for x in rms]
        c["the two-slot choke: slot 0's OPEN the same as on another track until slot 1's CLOSED hit, then choked "
          "(RMS 10..20 blocks on under a tenth)"] = (o[:at] == o2[:at] and rms[0] < 0.1 * rms[1] and rms[1] > 1e-3)
        s1 = [m5.perc_series(rr[k], 1) for k in ("choke", "nochoke")]
        c["the CLOSED hit on slot 1 sounds alike on either track"] = (s1[0] == s1[1] and
                                                                      max(abs(x) for x in s1[0]) > 0.01)
    if all(k in rr and rr[k]["ok"] for k in ("same0", "same1", "samefree0", "samefree1")):
        # the OPEN voice's slot's series: the two orders the same; against its own control (two tracks) the same
        # through the hits' block, then choked (RMS 10..20 blocks after under a tenth); the CLOSED alike everywhere
        op = {k: m5.perc_series(rr[k], int(k[-1])) for k in ("same0", "same1", "samefree0", "samefree1")}
        cl = {k: m5.perc_series(rr[k], 1 - int(k[-1])) for k in ("same0", "same1", "samefree0", "samefree1")}
        at = (SAME_AT + 1) * B
        late = slice(at + 10 * B, at + 20 * B)
        rms = {k: math.sqrt(sum(x * x for x in v[late]) / max(len(v[late]), 1)) for k, v in op.items()}
        n["same_block_open_rms_after"] = {k: round(v, 6) for k, v in rms.items()}
        c["the same-block choke: the OPEN's sound the same whichever slot renders first, and the CLOSED's"] = (
            op["same0"] == op["same1"] and cl["same0"] == cl["same1"])
        c["the same-block choke: the OPEN as on another track through the hits' block, then choked (RMS 10..20 "
          "blocks on under a tenth), in both orders"] = all(
            op[f"same{s}"][:at] == op[f"samefree{s}"][:at] and rms[f"same{s}"] < 0.1 * rms[f"samefree{s}"]
            and rms[f"samefree{s}"] > 1e-3 for s in (0, 1))
        c["the same-block choke: the CLOSED alike on one track or two, and sounding"] = all(
            cl[f"same{s}"] == cl[f"samefree{s}"] and max(abs(x) for x in cl[f"same{s}"]) > 0.01 for s in (0, 1))
    for a_, b_, what in (("clhh>ride", "clhh-start", "a RIDE trig on a sounding CLOSED hat (one voice)"),
                         ("ride>clhh", "ride-start", "a CLOSED trig on a sounding RIDE (one voice)")):
        if a_ in series and b_ in series:
            c[what + ": the same as the first hit until it, a new hit after it"] = (
                series[a_][:RETRIG_AT * B] == series[b_][:RETRIG_AT * B] and series[a_][cut:] != series[b_][cut:]
                and any(abs(x) > 0.01 for x in series[a_][cut:]))
    for soft, full in (("soft", "start"), ("snare-soft", "snare-start"), ("clhh-soft", "clhh-start"),
                       ("tom-soft", "tom-start"), ("clap-soft", "clap-start"), ("ride-soft", "ride-start")):
        if soft in series and full in series:
            c[f"the soft hit (velocity 40, {soft}) is quieter than the full one (PERC's level by velocity)"] = (
                peaks[soft] < 0.8 * peaks[full])
    return {"ok": all(c.values()), "checks": c, "numbers": n}
