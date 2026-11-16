"""JUNO (machine type 23, dnfw.engines.juno.juno) in the model (the program the SHARC runs bit for bit): its tables, its
place in the registry and on the pages, every WAVE x HPF choice finite and audible, its pitch, the VCF envelope's
release; and ANALOG2 unchanged by the ladder core JUNO shares (2026-11-12: dnfw.engines.analog2.filters.models.ladder_core)."""

from __future__ import annotations

import hashlib
import math

import pytest

from dnfw.md import core as MDK
from dnfw.engines.analog2 import analog2 as A2
from dnfw.engines.juno import juno as J
from dnfw.engines.juno import juno_data as JD
from dnfw.mnm import machines as MM
from dnfw.mnm import tables as T
from dnfw.engines import units as U
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits
from dnfw.waverider import pages as WP

NOTE_OFF_WORD = 0x25C4B0


def _type(name: str) -> int:
    return next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == name)


def _harness(name: str, knobs, knobs2):
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):             # the coordinator loads the filters' mix tables
        h.words[h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = bits(v)
    h.set_mnm(_type(name), list(knobs))
    for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, knobs2):
        h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
    return h


def _render(knobs, knobs2=J.DEFAULTS2, blocks=40, note=48.0, off_at=None):
    h = _harness("JUNO", knobs, knobs2)
    out = []
    for b in range(blocks):
        if off_at is not None and b in (off_at, off_at + 1):
            w = h.mem.get(NOTE_OFF_WORD)
            h.mem.put(NOTE_OFF_WORD, w | 1 if b == off_at else w & ~1)
        out += h.block(note=note, trig=b == 0)
    return out


def test_tables():
    v = T.juno_values()
    assert len(v) == T.JU_WORDS == len(T.juno_words())
    assert len(JD.G1Q) == 1025 and all(a <= b for a, b in zip(JD.G1Q, JD.G1Q[1:]))   # KR-106's curve rises
    assert JD.RES_K[0] == 0 and all(a <= b for a, b in zip(JD.RES_K, JD.RES_K[1:]))
    assert T.juno_drive(0) == T.juno_drive(80) == 0.2 and T.juno_drive(127) == 0.5


def test_registry_and_pages():
    k = MM.NAMES.index("JUNO")
    assert MM.TYPES[k] == 23 and 23 not in MM.RESERVED
    assert MM.MACHINES[k].PNAMES == J.PNAMES and MM.MACHINES[k].PNAMES2[:7] == J.PNAMES2
    ch = WP.MNM_CHOICES["JUNO"]
    assert len(ch["WAVE"]) == len(J.WAVES) and len(ch["HPF"]) == len(J.HPFS)
    assert len(ch["PWM"]) == len(J.PWMS) and len(ch["RNGE"]) == len(J.RANGES)
    assert all(n in WP.MNM_LONG or ("JUNO", n) in WP.MNM_LONG_BY for n in J.PNAMES + J.PNAMES2)
    assert 1 < U._juno_hz(0) < 30 and 15000 < U._juno_hz(127) < 20000      # (KR-106: 5.6 Hz .. 18.7 kHz)


@pytest.mark.parametrize("hpf", range(4))
@pytest.mark.parametrize("wave", range(4))
def test_every_wave_and_hpf_is_finite_and_audible(wave, hpf):
    knobs = (wave * 32 + 16, 40, 0 if wave else 90, 0 if wave else 60, 90, 60, 0, hpf * 32 + 16)
    out = _render(knobs)
    assert all(math.isfinite(x) for x in out)
    assert max(abs(x) for x in out[-320:]) > 0.01
    assert max(abs(x) for x in out) <= 4.0


def test_pitch():
    """note 69 is 440 Hz at the voice's 48 kHz output (an open saw: its upward zero crossings)"""
    out = _render((48, 0, 0, 0, 127, 0, 0, 48), blocks=120, note=69.0)[1600:]
    ups = [i + (-out[i]) / (out[i + 1] - out[i]) for i in range(len(out) - 1) if out[i] < 0.0 <= out[i + 1]]
    per = sorted(b - a for a, b in zip(ups, ups[1:]))[len(ups) // 2]
    assert abs(48000.0 / per - 440.0) < 0.5


def test_range_moves_an_octave():
    def f(rnge):
        k2 = list(J.DEFAULTS2)
        k2[6] = rnge
        out = _render((48, 0, 0, 0, 127, 0, 0, 48), k2, blocks=60, note=69.0)[800:]
        return sum(1 for a, b in zip(out, out[1:]) if a < 0.0 <= b)
    assert 1.8 < f(127) / f(64) < 2.2 and 1.8 < f(64) / f(0) < 2.2


def test_the_release_closes_the_filter():
    k2 = list(J.DEFAULTS2)
    k2[0] = 120                                          # ENV well up
    knobs = (48, 0, 0, 0, 30, 60, 0, 48)
    held = _render(knobs, k2, note=60.0)
    rel = _render(knobs, k2, note=60.0, off_at=6)
    assert held[:6 * 32] == rel[:6 * 32]
    tail = slice(32 * 32, None)
    assert max(abs(x) for x in rel[tail]) < 0.5 * max(abs(x) for x in held[tail])


# ANALOG2's output before the shared core (the pre-JUNO source, 8 blocks, RES 120, DRV 60, note 60; same hashes
# from the source after it: scratch/juno-engine/a2pin.py)
A2_PIN = {"SVF LP12": "333b2ab24832187f", "LADR LP24": "ef9b827338a5120d", "OTA LP24": "ed53a4ea4757c535",
          "OTA BP": "ef462cf3406ae185", "DIOD LP24": "9df57ab811d2517c"}


@pytest.mark.parametrize("name", sorted(A2_PIN))
def test_analog2_unchanged_by_the_shared_core(name):
    fi = A2.FLTS.index(name)
    knob = next(kv for kv in range(128) if kv * len(A2.FLTS) // 128 == fi)
    kn = list(A2.DEFAULTS)
    kn[5], kn[6] = 120, 60
    p2 = list(A2.DEFAULTS2)
    p2[6] = knob
    h = _harness("ANALOG2", kn, p2)
    hh = hashlib.sha256()
    for b in range(8):
        hh.update(b"".join(bits(x).to_bytes(4, "little") for x in h.block(note=60.0, trig=b == 0)))
    assert hh.hexdigest()[:16] == A2_PIN[name]
