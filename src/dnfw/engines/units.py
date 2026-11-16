"""What each Monomachine-style machine's knobs read in (2026-11-10, the User: no parameter of ours may
show a bare 0..127): the value readout (SYN held, csrc/waverider/md_page.c) draws Hz, ms or s, cents,
percent, signed percent from the knob 0..127. A choice shows its name (dnfw.waverider.pages.MNM_CHOICES),
semitones its own text; everything else is listed here, per machine and control, as a kind and, for a
curve that is not a straight line, the function of the knob it follows (17 points, 8 knobs apart, the
page code interpolates between them).

Kinds: pct (0..100 %), spct (-100..+99 %, 64 is 0), c (cents, the knob itself), c10 (tenths of a cent
from the curve), hz (Hz from the curve), hz100 (hundredths of a Hz from the curve), ms (milliseconds from
the curve), st10 (signed semitones in tenths from the curve: +1.5, then +12). `off` after a kind: the
knob 0 reads OFF.
"""

from __future__ import annotations

import json
import math
import pathlib

KINDS = ("raw", "pct", "spct", "hz", "hz100", "ms", "c10", "c", "db", "oct", "patn", "rate", "pctc", "mode", "ms10", "voic",
         "glid", "st10", "juno", "onoff")
# 2026-11-11: GLID up to 5 minutes (dnfw.engines.analog2.a2glide.ms_of): too steep for a 17-point curve, so read exactly a knob
# from its own table (`glid_table`), one a record span: ANALOG 2's LEV2 0..127, DRONE's AMD 0..120
GLID_TOPS = (127, 120)
OFF_BIT = 0x80


def _tone_hz(k: int) -> float:
    """DRONE's TONE: the one-pole's coefficient a = (128 + tone x 30236) / 2^15, tone = knob / 128: its
    cutoff -ln(1 - a) fs / 2 pi"""
    a = (128.0 + (k / 128.0) * 30236.0) / 32768.0
    return -math.log(1.0 - a) * 44100.0 / (2.0 * math.pi)


def _tune10(k: int) -> float:
    """TB303's and SOPHIE's TUNE: knob x 48 / 128 - 24 semitones (C.par is knob / 128), in tenths"""
    return (k * 48.0 / 128.0 - 24.0) * 10.0


# machine -> control -> (kind, function of the knob 0..127 or None, off at 0)
UNITS: dict[str, dict[str, tuple]] = {
    # 2026-11-11 (units session), from the DSP programs (dnfw.engines.plaits.plaits, tb303, sophie): `_unit` is knob / 127
    "PLAITS": {"HARM": ("pct", None, False), "TIMB": ("pct", None, False), "MORP": ("pct", None, False)},
    "TB303": {
        "CUT": ("hz", lambda k: 314.0 * (2394.0 / 314.0) ** (k / 127.0), False),   # 314 Hz .. 2.39 kHz
        "RES": ("pctc", lambda k: 100.0 * (1.0 - math.exp(-3.0 * k / 127.0)) / (1.0 - math.exp(-3.0)), False),
        "ENV": ("pct", None, False),
        "DEC": ("ms", lambda k: 200.0 * 10.0 ** (k / 127.0), False),               # 200 ms .. 2 s
        "ACC": ("pct", None, True),                                                 # 0: no accent
        "SLID": ("ms", lambda k: 2.0 + 358.0 * k / 127.0, True),                    # 2 .. 360 ms, 0: no slide
        "WAVE": ("pct", None, False),                                               # saw 0 % .. square 100 %
        "TUNE": ("st10", _tune10, False),
    },
    "SOPHIE": {
        "DCAY": ("ms", lambda k: 30.0 * (4.0 / 0.03) ** (k / 127.0), False),       # 30 ms .. 4 s
        "COLR": ("pct", None, False), "METL": ("pct", None, False), "FBK": ("pct", None, False),
        "SWEP": ("spct", None, False),                                              # -1 .. +1 of the model's sweep
        "CRSH": ("pct", None, True),                                                # 0: off
        "TUNE": ("st10", _tune10, False),
    },
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
        "WDTH": ("pct", None, False),                                    # 2026-11-11: the swarm's stereo width
        "GLID": ("glid", None, True),                                    # 2026-11-11, page 3: DRONE's, 0 OFF
    },
    # 2026-11-12: JUNO (dnfw.engines.juno.juno): CUT through KR-106's curve at RES 0 (G = g / (1 + g), g = tan(pi f / fs)),
    # the envelope's times as its rates (page 2's knob k reads q = k / 127)
    "JUNO": {
        "PW": ("pct", None, False), "SUB": ("pct", None, True), "NOIS": ("pct", None, True),
        "CUT": ("hz", lambda k: _juno_hz(k), False), "RES": ("pct", None, False), "KEY": ("pct", None, False),
        "ENV": ("spct", None, False),
        "ATK": ("ms", lambda k: 1.5 * 2000.0 ** (k / 127.0), False),    # 1.5 ms .. 3 s
        "DEC": ("ms", lambda k: 1.5 * 8000.0 ** (k / 127.0), False),    # 1.5 ms .. 12 s
        "SUS": ("pct", None, False),
        "REL": ("ms", lambda k: 1.5 * 8000.0 ** (k / 127.0), False),
    },
}


def _juno_hz(k: int) -> float:
    """JUNO's CUT k (KEY, ENV 0): the DAC's code k x 128 / 4, KR-106's G there (G1Q, a point every 4 codes)"""
    from .juno.juno_data import G1Q
    g = G1Q[min(1024, (k * 128 // 4) // 4)] / 32768.0
    return math.atan(g / (1.0 - g)) * 44100.0 / math.pi


# XDLY's TIME 1 / TIME 2 (dnfw.xdly.design T_MIN .. T_MAX: 1 ms x 10000^(k / 127), the inserts' and the send's
# engine alike; 2026-11-11, was percent)
_XT = lambda k: 10000.0 ** (k / 127.0)     # noqa: E731

# the inserts (csrc/inserts/ins.c, the value readout with SYN held), by type number (dnfw.inserts.design) and
# knob 0..5, 7 the MIX; the types of the ports session's (SUB DIST GATER RING), after Optimist's: the curves
# are design.py's (SUB: LEV BAND TONE OCT DRY; DIST: DRIV TONE BIAS LOW LEV; GATER: DPTH PATN RATE SHPE SWNG;
# RING: FREQ SHPE AM LEV)
INS_TYPES = ("OFF", "FUZZ", "TAPE", "FOLD", "CHOR", "WIDE", "HARM", "FDN8", "XDLY", "SUB", "DIST", "GATER", "RING",
             "JUNO")
INS_UNITS: dict[str, dict[int, tuple]] = {
    # the older inserts (dnfw.inserts.design's constants): FUZZ DRIV TONE BIAS PRE GATE LEV; TAPE DRIV WOW WRAT FLUT AGE
    # HISS; FOLD AMNT SYMM SHPE TONE LEV; CHOR DPTH RATE DLY VOIC WDTH FDBK; WIDE WDTH TIME BASS TONE; HARM AMNT FREQ
    # EVEN TONE LEV; FDN8 PRE SIZE DAMP MOD HPF LPF; XDLY TIM1 TIM2 FDBK MOD TONE (a TONE whose range the design does
    # not give reads in percent)
    "FUZZ": {0: ("db", lambda k: 48.0 * k / 127.0, False), 1: ("hz", lambda k: 300.0 * 40.0 ** (k / 127.0), False),
             2: ("pct", None, False), 3: ("pct", None, False), 4: ("pct", None, False), 5: ("pct", None, False),
             6: ("onoff", None, False)},           # 6: AUTO (2026-11-13, ins.c X_AUTO)
    "TAPE": {0: ("db", lambda k: 18.0 * k / 127.0, False), 1: ("pct", None, False),
             2: ("hz100", lambda k: 10.0 * 20.0 ** (k / 127.0), False), 3: ("pct", None, False),
             4: ("hz", lambda k: 16000.0 * 2.0 ** (-3.0 * k / 127.0), False), 5: ("pct", None, False),
             6: ("onoff", None, False),            # 6: AUTO, 8: PGAIN (2026-11-13: knob 64 0 dB, 1 dB a step)
             8: ("db", lambda k: float(min(max(k - 64, -32), 31)), False)},
    "FOLD": {0: ("db", lambda k: 24.0 * k / 127.0, False), 1: ("spct", None, False), 2: ("pct", None, False),
             3: ("pct", None, False), 4: ("pct", None, False), 5: ("onoff", None, False)},
    "CHOR": {0: ("ms10", lambda k: 40.0 * k / 127.0, False), 1: ("hz100", lambda k: 5.0 * 100.0 ** (k / 127.0), False),
             2: ("ms", lambda k: 5.0 + 10.0 * k / 127.0, False), 3: ("voic", None, False), 4: ("pct", None, False),
             5: ("pctc", lambda k: 70.0 * k / 127.0, False)},
    "WIDE": {0: ("pct", None, False), 1: ("ms10", lambda k: (24.0 + 936.0 * k / 127.0) / 48.0 * 10.0, False),
             2: ("hz", lambda k: 40.0 * 16.0 ** (k / 127.0), False), 3: ("pct", None, False)},
    "HARM": {0: ("pct", None, False), 1: ("hz", lambda k: 500.0 * 16.0 ** (k / 127.0), False),
             2: ("pct", None, False), 3: ("pct", None, False), 4: ("pct", None, False), 5: ("onoff", None, False)},
    "FDN8": {0: ("ms", lambda k: 100.0 * (k / 127.0) ** 2, False), 1: ("pct", None, False), 2: ("pct", None, False),
             3: ("pctc", lambda k: 200.0 * k / 127.0, False), 4: ("hz", lambda k: 20.0 * 100.0 ** (k / 127.0), False),
             5: ("hz", lambda k: 200.0 * 100.0 ** (k / 127.0), False)},
    "XDLY": {0: ("ms", _XT, False), 1: ("ms", _XT, False), 2: ("pctc", lambda k: 105.0 * k / 127.0, False),
             3: ("pct", None, False), 4: ("hz", lambda k: 200.0 * 100.0 ** (k / 127.0), False)},
    "SUB": {0: ("pct", None, False), 1: ("hz", lambda k: 110.0 * 8.0 ** (k / 127.0), False),
            2: ("hz", lambda k: 60.0 * 16.0 ** (k / 127.0), False), 3: ("oct", None, False), 4: ("pct", None, False)},
    "DIST": {0: ("db", lambda k: 20.0 * math.log10(0.5 * 2.0 ** (math.log2(96.0) * k / 127.0)), False),
             1: ("hz", lambda k: 300.0 * 40.0 ** (k / 127.0), False), 2: ("spct", None, False),
             3: ("hz", lambda k: 20.0 * 16.0 ** (k / 127.0), False), 4: ("pctc", lambda k: k * 200.0 / 127.0, False),
             5: ("onoff", None, False)},           # AUTO (2026-11-12, design.AUTO_TYPES): OFF 0..63, ON 64..127
    "GATER": {0: ("pct", None, False), 1: ("patn", None, False), 2: ("rate", None, False),
              3: ("pct", None, False), 4: ("pctc", lambda k: k * 50.0 / 127.0, False)},
    "RING": {0: ("hz", lambda k: 26.0 * 100.0 ** (k / 127.0), False), 1: ("pct", None, False),
             2: ("pct", None, False), 3: ("pct", None, False)},
    "JUNO": {0: ("juno", None, False)},          # MODE I / II / I+II (design.JN_MODE_K)
}


# the A2 filter machines' FLTR page (dnfw.engines.analog2.filters, Multi-Mode's records): record id -> kind and curve. FREQ and FRQ2
# are CUT units (30 Hz x 2^(cut x log2(16000 / 30) / 127)), RESO and RES2 percent, MODE and MOD2 the five modes
# (LP12 LP24 BP HP NTCH), ATK 0.1 ms x 4000^(k / 127) (tenths of a millisecond), DEC 2 ms x 5000^(k / 127), ENV
# the envelope's depth signed percent (64 none)
FLT_IDS = (36, 37, 38, 44, 45, 46, 47, 48, 49)
_CUT = lambda k: 30.0 * 2.0 ** (k * math.log2(16000.0 / 30.0) / 127.0)     # noqa: E731
FLT_UNITS = {36: ("hz", _CUT), 37: ("pct", None), 38: ("mode", None), 44: ("mode", None),
             45: ("ms10", lambda k: 1.0 * 4000.0 ** (k / 127.0)), 46: ("ms", lambda k: 2.0 * 5000.0 ** (k / 127.0)),
             47: ("hz", _CUT), 48: ("pct", None), 49: ("spct", None)}


# the send pages' second page (csrc/fxpage/fxp.c, docs/fxpage.md): page (0 Delay with XDLY, 1 Reverb with FDN8 /
# LONG) and place 0..7 -> kind and curve, from the engines' own derivations (dnfw.xdly.design / fdn8.design derive):
# 2026-11-13, the User: no bare 0..127; were all percent. Delay A (TIME) is stock's cell, its record's formatter
def _fxp_units() -> dict[int, dict[int, tuple]]:
    from ..xdly import design as XD
    from ..fdn8 import design as FD
    return {
        0: {1: ("ms", lambda k: XD.SL_T0 * 1000.0 ** (k / 127.0) / 48.0),       # SLEW: the times' follow, 1 ms .. 1 s
            2: ("db", lambda k: 20.0 * math.log10(XD.KN_LO + k * XD.KN_STEP)),    # KNEE: the soft knee's level
            3: ("pct", None),                                                      # WDTH: 0 mono .. 100 hard
            4: ("spct", None)},                                                    # INPT: (k - 64) / 64, 0 the mono sum
        1: {0: ("pctc", lambda k: 100.0 * k * FD.DF_K),                           # DIFF: the diffusers x k / 64
            1: ("pct", None), 2: ("pct", None)},                                   # WDTH, FREZ: k / 127
    }


def fxp_tables(base: int) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    """-> (kind per page and place, curve index (from BASE), the curves) for the send pages' page 2"""
    curves: list[list[int]] = []
    kinds, at = [], []
    for page in range(2):
        krow, arow = [], []
        for i in range(8):
            kind, fn = _fxp_units()[page].get(i, ("raw", None))
            idx = 0
            if fn is not None:
                c = curve(fn)
                if c not in curves:
                    curves.append(c)
                idx = base + curves.index(c)
            krow.append(KINDS.index(kind))
            arow.append(idx)
        kinds.append(krow)
        at.append(arow)
    return kinds, at, curves


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
        for j in range(9):
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
    from .analog2.a2glide import ms_of
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


# -- stock records (2026-11-11, the User: "proper values every where ... gate it with a compile option"): built only
# with DN2_STOCK_UNITS set at generation (dnfw.waverider.pages, cpage); without it nothing below reaches the code.
# record id -> (kind, function of the knob or None, off at 0, stock 1.12's formatter at that record). Phase 1: the
# plain amounts (levels, sends, mixes, depths, amounts) as a percent of their range, NOT a measured unit; the
# times, frequencies and gains wait for their measurement in the SHARC runner (phase 2), the numbers that are the
# value (MIDI, notes, velocity, counts, conditions, waveform positions) stay stock's.
STOCK_PLAIN = 0x400E3030                      # stock's "%d" of the knob
_STOCK_PCT = (10, 37, 40, 47, 55, 58, 65, 72, 80, 90, 100, 105, 108, 109, 110, 111, 112, 119, 120, 121, 129, 130,
              132, 133, 134, 135, 139, 140, 141, 142, 143, 144, 145, 146, 147, 158, 159,
              206, 214, 215, 218, 219, 235, 236, 237,               # FM TONE
              241, 245, 252, 256, 260,                              # WaveTone
              269, 274, 278, 282, 288, 291, 292,                    # FM DRUM
              295, 298, 299,                                        # SWARMER
              304, 319)
STOCK_UNITS: dict[int, tuple] = {r: ("pct", None, False, STOCK_PLAIN) for r in _STOCK_PCT}
# phase 2, a fitted law (docs/stock-units.md has the points): the Multimode filter's FREQ, its cutoff (the 2-pole
# low-pass's -90 degree point) = 2^(2.2692 + 0.09521 knob) Hz, measured in the SHARC runner at knobs 32..124 (within
# +4.3 % at 32, +-1.2 % from 80 on); under 32 (a cutoff below ~40 Hz, under the track's DC blocker) extrapolated
STOCK_UNITS[36] = ("hz", lambda k: 2.0 ** (2.2692 + 0.09521 * k), False, 0x400E305A)
# stock 1.12's formatter at the records a measured table may take (the image's record + 0x34; test_stock_units holds them)
_STOCK_FMT_OF = {44: STOCK_PLAIN, 45: STOCK_PLAIN, 46: 0x400E381A, 48: 0x400E381A,
                 61: STOCK_PLAIN, 62: STOCK_PLAIN, 63: 0x400E37DC, 64: 0x400E381A, 66: 0x400E381A}
STOCK_MACHINE_IDS = range(200, 301)           # the machines' own records: their text only on a stock machine's track

# phase 2: what was measured in Elektron's DSP (scripts/stock_units_measure.py, docs/stock-units.md), one entry a
# quantity: its records, its unit, how it was found, and its value at each knob 0..127 (null: no end, INF). Read
# exactly a knob (the GLID kind's table), so no curve between measured points
_MEASURED = pathlib.Path(__file__).with_name("stock_measured.json")
GLID_INF = 0xFFFF                             # a table's "never" (a decay that does not fall): the page shows INF


def stock_measured() -> dict:
    return json.loads(_MEASURED.read_text()) if _MEASURED.exists() else {}


def _stock_table_rows() -> tuple[dict[int, int], list[list[int]]]:
    """-> (record -> its row among the stock tables, the rows: 128 GLID codes each)"""
    rows: list[list[int]] = []
    at: dict[int, int] = {}
    for q in stock_measured().values():
        vals = q["values"]
        if len(vals) != 128:
            raise ValueError(f"{q['records']}: a table needs every knob 0..127, has {len(vals)}")
        row = [GLID_INF if v is None else _glid_code(v) for v in vals]
        for rid in q["records"]:
            at[rid] = len(rows)
        rows.append(row)
    return at, rows


def stock_glid_rows() -> list[list[int]]:
    return _stock_table_rows()[1]


def stock_tables(base: int) -> tuple[list[int], list[int], list[int], list[int], list[list[int]]]:
    """-> (record ids, kinds, curve indices (from BASE), stock formatters, the curves) for STOCK_UNITS"""
    rows_at, _rows = _stock_table_rows()
    units = {**STOCK_UNITS, **{r: ("glid", None, False, _STOCK_FMT_OF[r]) for r in rows_at}}
    ids = sorted(units)
    curves: list[list[int]] = []
    kinds, at, stock = [], [], []
    for rid in ids:
        kind, fn, off, fmt = units[rid]
        idx = 0
        if kind == "glid":
            idx = len(GLID_TOPS) + rows_at[rid]        # a row of mnm_glid after GLID's own
        elif fn is not None:
            c = curve(fn)
            if c not in curves:
                curves.append(c)
            idx = base + curves.index(c)
        kinds.append(KINDS.index(kind) | (OFF_BIT if off else 0))
        at.append(idx)
        stock.append(fmt)
    return ids, kinds, at, stock, curves
