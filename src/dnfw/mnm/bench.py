"""The Monomachine-style machines in run mode, outside PERC's voice: the bench's layout, its
table memory, and a signal comparison (each machine's reference lives outside the repository:
docs/sophie.md). Until 2026-11-08 this also held SID, the DPRO machines and VO-6 to the
Monomachine's own output (golden vectors); those machines are gone."""

from __future__ import annotations

import math
import struct

from . import core as C
from . import tables as T
from ..perc.dsl import bits

STATE = 0x00100000                       # the bench's slot words
SCRATCH = 0x00200000
TABLES = 0x00400000
MD_SCRATCH = 0x00080000
PERC_TABLES = 0x00700000
PERC_SCRATCH = 0x00090000
MD_DELAY = 0x00900000                    # (STATE + 1 MB, the default, is SCRATCH here)


def layout() -> C.Layout:
    from ..perc import machines as PM
    perc = PM.Layout(state=0x000A0000, scratch=PERC_SCRATCH, tables=PERC_TABLES, sin=0,
                     md_state=STATE, md_tables=0x00600000, mnm_scratch=SCRATCH, mnm_tables=TABLES)
    perc.md.delay = MD_DELAY
    return perc.md.mnm


_TM: dict[int, int] = {}


def table_mem(L: C.Layout) -> dict[int, int]:
    """the tables as the DSP holds them: the Monomachine machines' (dnfw.mnm.tables, as table_fill
    stores them) and PERC's"""
    if not _TM:
        for k, v in enumerate(T.table_words()):
            _TM[L.tables + 4 * k] = bits(v * C.Q23)
        from ..perc import machines as PM
        data, _ = PM.tables_bytes()
        for k in range(0, len(data), 4):
            _TM[PERC_TABLES + k] = struct.unpack_from("<I", data, k)[0]
    return _TM


def compare(ours, theirs) -> dict:
    err = [a - b for a, b in zip(ours, theirs)]
    pe = max((abs(e) for e in err), default=0.0)
    sig = math.sqrt(sum(x * x for x in theirs) / max(1, len(theirs)))
    rms = math.sqrt(sum(e * e for e in err) / max(1, len(err)))
    snr = 200.0 if rms == 0 else (20 * math.log10(sig / rms) if sig > 0 else -200.0)
    return {"peak_err": pe, "rms_err": rms, "signal_rms": sig, "snr_db": snr}


# v0.51 (owner: the lighter Monomachine machines, "we can make them sound good without being exact
# replicas"; a significant cut is worth it at about 70 % of the likeness): a trimmed machine is held
# to the Monomachine by its level and its spectrum's shape, not sample for sample. Octave bands from
# 0 to 24 kHz (Hann window over the whole case); every band within BAND_SPAN dB of the Monomachine's
# loudest must lie within BAND_DB of it (the top octave, 16..24 kHz, within TOP_DB: DDRW read at 1x
# folds a little of its highest partials back there at high pitches); the level (RMS) within
# LEVEL_DB. NOIS (a random register's output, its low bands a few values over a short case) is held
# to its level only.
LEVEL_DB, BAND_DB, TOP_DB, BAND_SPAN = 2.5, 6.0, 15.0, 20.0
EDGES = (0, 250, 500, 1000, 2000, 4000, 8000, 16000, 24001)


def bands(x) -> list[float]:
    import numpy as np
    a = np.asarray(x, dtype=float)
    X = np.abs(np.fft.rfft(a * np.hanning(len(a)))) ** 2
    f = np.fft.rfftfreq(len(a), 1 / 48000)
    return [10 * math.log10(X[(f >= lo) & (f < hi)].sum() + 1e-20) for lo, hi in zip(EDGES, EDGES[1:])]


def likeness(ours, theirs, noise: bool = False) -> dict:
    lo = sum(v * v for v in ours) / max(len(ours), 1)
    lt = sum(v * v for v in theirs) / max(len(theirs), 1)
    level = 10 * math.log10((lo + 1e-30) / (lt + 1e-30))
    bo, bt = bands(ours), bands(theirs)
    top = max(bt)
    dev = 0.0 if noise else max((abs(a - b) for a, b in zip(bo[:-1], bt[:-1]) if b > top - BAND_SPAN), default=0.0)
    tdev = 0.0 if noise or bt[-1] <= top - BAND_SPAN else abs(bo[-1] - bt[-1])
    ok = (lt < 1e-12 and lo < 1e-12) or (abs(level) <= LEVEL_DB and dev <= BAND_DB and tdev <= TOP_DB)
    return {"ok": ok, "level_db": level, "band_dev_db": dev, "top_dev_db": tdev, "ours": bo, "theirs": bt}
