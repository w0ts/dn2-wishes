"""What each Monomachine-style machine's knobs read in (2026-11-10, the User: no parameter of ours may
show a bare 0..127): the value readout (SYN held, csrc/waverider/md_page.c) draws Hz, ms or s, cents,
percent, signed percent from the knob 0..127. A choice shows its name (dnfw.waverider.pages.MNM_CHOICES),
semitones its own text; everything else is listed here, per machine and control, as a kind and, for a
curve that is not a straight line, the function of the knob it follows (17 points, 8 knobs apart, the
page code interpolates between them).

Kinds: pct (0..100 %), spct (-100..+99 %, 64 is 0), c (cents, the knob itself), c10 (tenths of a cent
from the curve), hz (Hz from the curve), hz100 (hundredths of a Hz from the curve), ms (milliseconds from
the curve). `off` after a kind: the knob 0 reads OFF.
"""

from __future__ import annotations

import math

KINDS = ("raw", "pct", "spct", "hz", "hz100", "ms", "c10", "c", "db", "oct", "patn", "rate", "pctc", "mode", "ms10", "voic",
         "glid")
# 2026-11-11: GLID up to 5 minutes (dnfw.mnm.a2glide.ms_of): too steep for a 17-point curve, so read exactly a knob
# from its own table (`glid_table`), one a record span: ANALOG 2's LEV2 0..127, DRONE's AMD 0..120
GLID_TOPS = (127, 120)
OFF_BIT = 0x80


def _tone_hz(k: int) -> float:
    """DRONE's TONE: the one-pole's coefficient a = (128 + tone x 30236) / 2^15, tone = knob / 128: its
    cutoff -ln(1 - a) fs / 2 pi"""
    a = (128.0 + (k / 128.0) * 30236.0) / 32768.0
    return -math.log(1.0 - a) * 44100.0 / (2.0 * math.pi)


# machine -> control -> (kind, function of the knob 0..127 or None, off at 0)
UNITS: dict[str, dict[str, tuple]] = {
    "DRONE": {
        "SPRD": ("pct", None, False), "CPL": ("pct", None, False), "CHAR": ("pct", None, False),
        "DRFT": ("c10", lambda k: k * 68.0 / 127.0, False),             # up to +-6.8 cents
        "TONE": ("hz", _tone_hz, False),
        "BEAT": ("hz100", lambda k: 5.0 * 800.0 ** (k / 127.0), True),   # Optimist's F_LFOHZ: 0.05 .. 40 Hz, 0 OFF
        "DTUN": ("c10", lambda k: k * 67.0 / 128.0, False),              # the generators' step, up to ~6.7 cents
        "GLID": ("glid", None, True),                                    # 1 ms .. 5 min (a2glide.ms_of), 0 OFF
    },
    "ANALOG2": {
        "DTN": ("c", None, False), "MIX": ("pct", None, False), "NOIS": ("pct", None, False),
        "CUT": ("hz", lambda k: 30.0 * 2.0 ** (k * math.log2(16000.0 / 30.0) / 127.0), False),
        "RES": ("pct", None, False), "DRV": ("pct", None, False), "KTR": ("spct", None, False),
        "SDTN": ("pct", None, False), "DRFT": ("pct", None, False),
        "GLID": ("glid", None, True),                                    # 2026-11-11, page 3: DRONE's, 0 OFF
    },
}


# the inserts (csrc/inserts/ins.c, the value readout with SYN held), by type number (dnfw.inserts.design) and
# knob 0..5, 7 the MIX; the types of the ports session's (SUB DIST GATER RING), after Optimist's: the curves
# are design.py's (SUB: LEV BAND TONE OCT DRY; DIST: DRIV TONE BIAS LOW LEV; GATER: DPTH PATN RATE SHPE SWNG;
# RING: FREQ SHPE AM LEV)
INS_TYPES = ("OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM", "FDN8", "XDLY", "SUB", "DIST", "GATER", "RING")
INS_UNITS: dict[str, dict[int, tuple]] = {
    # the older inserts (dnfw.inserts.design's constants): FUZZ DRIV TONE BIAS PRE GATE LEV; TAPE DRIV WOW WRAT FLUT AGE
    # HISS; FOLD AMNT SYMM SHPE TONE LEV; CHOR DPTH RATE DLY VOIC WDTH FDBK; WIDE WDTH TIME BASS TONE; HARM AMNT FREQ
    # EVEN TONE LEV; FDN8 PRE SIZE DAMP MOD HPF LPF; XDLY TIM1 TIM2 FDBK MOD TONE (a TONE whose range the design does
    # not give, and XDLY's TIM1 TIM2, read in percent: no physical unit known)
    "FUZZ": {0: ("db", lambda k: 48.0 * k / 127.0, False), 1: ("hz", lambda k: 300.0 * 40.0 ** (k / 127.0), False),
             2: ("pct", None, False), 3: ("pct", None, False), 4: ("pct", None, False), 5: ("pct", None, False)},
    "TAPE": {0: ("db", lambda k: 18.0 * k / 127.0, False), 1: ("pct", None, False),
             2: ("hz100", lambda k: 10.0 * 20.0 ** (k / 127.0), False), 3: ("pct", None, False),
             4: ("hz", lambda k: 16000.0 * 2.0 ** (-3.0 * k / 127.0), False), 5: ("pct", None, False)},
    "FOLD": {0: ("db", lambda k: 24.0 * k / 127.0, False), 1: ("spct", None, False), 2: ("pct", None, False),
             3: ("pct", None, False), 4: ("pct", None, False)},
    "CHOR": {0: ("ms10", lambda k: 40.0 * k / 127.0, False), 1: ("hz100", lambda k: 5.0 * 100.0 ** (k / 127.0), False),
             2: ("ms", lambda k: 5.0 + 10.0 * k / 127.0, False), 3: ("voic", None, False), 4: ("pct", None, False),
             5: ("pctc", lambda k: 70.0 * k / 127.0, False)},
    "WIDE": {0: ("pct", None, False), 1: ("ms10", lambda k: (24.0 + 936.0 * k / 127.0) / 48.0 * 10.0, False),
             2: ("hz", lambda k: 40.0 * 16.0 ** (k / 127.0), False), 3: ("pct", None, False)},
    "HARM": {0: ("pct", None, False), 1: ("hz", lambda k: 500.0 * 16.0 ** (k / 127.0), False),
             2: ("pct", None, False), 3: ("pct", None, False), 4: ("pct", None, False)},
    "FDN8": {0: ("ms", lambda k: 100.0 * (k / 127.0) ** 2, False), 1: ("pct", None, False), 2: ("pct", None, False),
             3: ("pctc", lambda k: 200.0 * k / 127.0, False), 4: ("hz", lambda k: 20.0 * 100.0 ** (k / 127.0), False),
             5: ("hz", lambda k: 200.0 * 100.0 ** (k / 127.0), False)},
    "XDLY": {0: ("pct", None, False), 1: ("pct", None, False), 2: ("pctc", lambda k: 105.0 * k / 127.0, False),
             3: ("pct", None, False), 4: ("hz", lambda k: 200.0 * 100.0 ** (k / 127.0), False)},
    "SUB": {0: ("pct", None, False), 1: ("hz", lambda k: 110.0 * 8.0 ** (k / 127.0), False),
            2: ("hz", lambda k: 60.0 * 16.0 ** (k / 127.0), False), 3: ("oct", None, False), 4: ("pct", None, False)},
    "DIST": {0: ("db", lambda k: 20.0 * math.log10(0.5 * 2.0 ** (math.log2(96.0) * k / 127.0)), False),
             1: ("hz", lambda k: 300.0 * 40.0 ** (k / 127.0), False), 2: ("spct", None, False),
             3: ("hz", lambda k: 20.0 * 16.0 ** (k / 127.0), False), 4: ("pctc", lambda k: k * 200.0 / 127.0, False)},
    "GATER": {0: ("pct", None, False), 1: ("patn", None, False), 2: ("rate", None, False),
              3: ("pct", None, False), 4: ("pctc", lambda k: k * 50.0 / 127.0, False)},
    "RING": {0: ("hz", lambda k: 26.0 * 100.0 ** (k / 127.0), False), 1: ("pct", None, False),
             2: ("pct", None, False), 3: ("pct", None, False)},
}


# the A2 filter machines' FLTR page (dnfw.a2f, Multi-Mode's records): record id -> kind and curve. FREQ and FRQ2
# are CUT units (30 Hz x 2^(cut x log2(16000 / 30) / 127)), RESO and RES2 percent, MODE and MOD2 the five modes
# (LP12 LP24 BP HP NTCH), ATK 0.1 ms x 4000^(k / 127) (tenths of a millisecond), DEC 2 ms x 5000^(k / 127), ENV
# the envelope's depth signed percent (64 none)
FLT_IDS = (36, 37, 38, 44, 45, 46, 47, 48, 49)
_CUT = lambda k: 30.0 * 2.0 ** (k * math.log2(16000.0 / 30.0) / 127.0)     # noqa: E731
FLT_UNITS = {36: ("hz", _CUT), 37: ("pct", None), 38: ("mode", None), 44: ("mode", None),
             45: ("ms10", lambda k: 1.0 * 4000.0 ** (k / 127.0)), 46: ("ms", lambda k: 2.0 * 5000.0 ** (k / 127.0)),
             47: ("hz", _CUT), 48: ("pct", None), 49: ("spct", None)}


def flt_tables(base: int) -> tuple[list[int], list[int], list[list[int]]]:
    """-> (kinds, curve indices (from BASE), the curves) for FLT_IDS"""
    curves: list[list[int]] = []
    kinds, at = [], []
    for rid in FLT_IDS:
        kind, fn = FLT_UNITS[rid]
        idx = 0
        if fn is not None:
            c = curve(fn)
            if c not in curves:
                curves.append(c)
            idx = base + curves.index(c)
        kinds.append(KINDS.index(kind))
        at.append(idx)
    return kinds, at, curves


def ins_tables() -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    """-> (kind per insert type and knob 0..7, curve index, the curves): the inserts' readout. Every type's
    MIX (7) is a percent; the types not listed show nothing yet (raw)"""
    curves: list[list[int]] = []
    kinds, at = [], []
    for name in INS_TYPES:
        krow, arow = [], []
        for j in range(8):
            if j == 7:
                kind, fn, off = ("pct", None, False) if name != "OFF" else ("raw", None, False)
            else:
                kind, fn, off = INS_UNITS.get(name, {}).get(j, ("raw", None, False))
            idx = 0
            if fn is not None:
                c = curve(fn)
                if c not in curves:
                    curves.append(c)
                idx = curves.index(c)
            krow.append(KINDS.index(kind) | (OFF_BIT if off else 0))
            arow.append(idx)
        kinds.append(krow)
        at.append(arow)
    return kinds, at, curves


def curve(fn) -> list[int]:
    return [int(round(fn(min(127, 8 * i)))) for i in range(17)]


def _glid_code(ms: float) -> int:
    """a GLID time as the page reads it: ms under 10 s, else 10000 + tenths of a second"""
    return int(round(ms)) if ms < 9999.5 else 10000 + int(round(ms / 100.0))


def glid_table(top: int) -> list[int]:
    """GLID's time for each knob 0..127 the page shows (md_page.c mnm_k: (v 254 + top) / (2 top)) of a record
    value v 0..top, as the DSP reads it (q = v / top); a knob no value gives takes the nearest value's"""
    from .a2glide import ms_of
    out: list[int | None] = [None] * 128
    for v in range(top + 1):
        out[(v * 254 + top) // (2 * top)] = _glid_code(ms_of(v / top))
    return [x if x is not None else _glid_code(ms_of(round(k * top / 127) / top)) for k, x in enumerate(out)]


def tables(machines, pnames, tops=None) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    """-> (kind code per machine and control (OFF_BIT set: knob 0 reads OFF), curve index per machine and
    control, the curves). `machines` the CF machines in table order, `pnames(M)` their 24 control names,
    `tops(j)` control j's record span (a glid kind's curve index is its place in GLID_TOPS)"""
    curves: list[list[int]] = []
    kinds, at = [], []
    for M in machines:
        krow, arow = [], []
        for j, name in enumerate(pnames(M)):
            kind, fn, off = UNITS.get(M.NAME, {}).get(name, ("raw", None, False))
            code = KINDS.index(kind) | (OFF_BIT if off else 0)
            idx = 0
            if kind == "glid":
                idx = GLID_TOPS.index(tops(j) if tops else 127)
            elif fn is not None:
                c = curve(fn)
                if c not in curves:
                    curves.append(c)
                idx = curves.index(c)
            krow.append(code)
            arow.append(idx)
        kinds.append(krow)
        at.append(arow)
    return kinds, at, curves or [[0] * 17]
