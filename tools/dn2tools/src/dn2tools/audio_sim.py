"""What the simulated unit would sound like, for the dry run of the audio scenarios: the notes it was played, per track,
as band-limited saws (an A2 filter weights the harmonics; XDLY adds echoes; FDN8 a decaying tail; a glide track glides),
rendered from the voice log of `UnitSim`. A model: it exists so every audio assertion can pass and fail before the unit
is connected. Faults (in `UnitSim.faults`): audio_clicks (a click every block), audio_silent (no output),
filter_dead (the A2 filters do nothing), glide_dead, delay_dead, hold_dead (in the simulator itself)."""

from __future__ import annotations

import numpy as np

from .audio import Recorder
from .audio_analysis import BLOCK, FS
from .sim import DirectUnit

RELEASE_S = 0.3
GLIDE_S = 0.4
CUTOFF = {"SVF": 1500.0, "LADR": 1000.0, "OTA": 2000.0, "DIOD": 800.0, "MS20": 1200.0}
ECHO_S, ECHO_TAPS = 0.25, 3
TAIL_S = 1.4


def _freq(note: float) -> float:
    return 440.0 * 2.0 ** ((note - 69.0) / 12.0)


def _voice(v, tr, t_end: float, t_start: float, faults) -> tuple[int, np.ndarray]:
    """(first sample, samples) of one voice, to T_END (the last instant of the recording); times from T_START"""
    start = v.at
    end = (v.rel_at + 3 * RELEASE_S) if v.rel_at is not None else t_end      # held or latched: to the end
    n = max(0, int((min(end, t_end) - start) * FS))
    t = np.arange(n) / FS
    if tr.glide and v.legato_from is not None and "glide_dead" not in faults:
        f0, f1 = _freq(v.legato_from), _freq(v.note)
        ramp = np.clip(t / GLIDE_S, 0.0, 1.0)
        f = f0 * (f1 / f0) ** ramp
    else:
        f = np.full(n, _freq(v.note))
    ph = 2 * np.pi * np.cumsum(f) / FS
    sig = np.zeros(n)
    fund = float(f[-1]) if n else 440.0
    nh = max(1, int(min(16_000.0, FS / 2 - 100) / max(fund, 50.0)))
    for k in range(1, min(nh, 40) + 1):
        w = 1.0 / k
        if tr.filter and "filter_dead" not in faults:
            w *= 1.0 / (1.0 + (k * fund / CUTOFF[tr.filter]) ** 4)
        sig += w * np.sin(k * ph)
    amp = 0.25 * (v.vel / 127.0)
    env = np.ones(n)
    a = min(n, int(0.005 * FS))
    env[:a] = np.linspace(0, 1, a, endpoint=False)
    rel = v.rel_at
    if rel is not None and rel < t_end:
        i = int((rel - start) * FS)
        m = n - i
        if m > 0:
            env[i:] *= np.exp(-np.arange(m) / (RELEASE_S / 4.6 * FS))
    return int(start * FS), amp * sig * env


class SimRecorder(Recorder):
    def __init__(self, unit: DirectUnit):
        self.unit = unit

    def start(self) -> None:
        self.t0 = self.unit.clock()

    def stop(self) -> np.ndarray:
        sim, project = self.unit.sim, self.unit.sim.project
        t_end = self.unit.clock()
        n = int((t_end - self.t0) * FS)
        out = np.zeros(n)
        if "audio_silent" in sim.faults:
            return np.zeros((n, 2), np.float32)
        rng = np.random.RandomState(7)
        tails: dict[int, np.ndarray] = {}
        for v in sim.log:
            if v.at >= t_end or (v.rel_at is not None and v.rel_at + RELEASE_S * 3 < self.t0):
                continue
            tr = project.tracks[v.track]
            s0, sig = _voice(v, tr, t_end, self.t0, sim.faults)
            buf = tails.setdefault(v.track, np.zeros(n))
            a = s0 - int(self.t0 * FS)
            lo, hi = max(a, 0), min(a + len(sig), n)
            if hi > lo:
                buf[lo:hi] += sig[lo - a:hi - a]
        for k, buf in tails.items():
            tr = project.tracks[k]
            if tr.insert == "XDLY" and "delay_dead" not in sim.faults:
                d = int(ECHO_S * FS)
                wet = buf.copy()
                for tap in range(1, ECHO_TAPS + 1):
                    wet[tap * d:] += buf[:n - tap * d] * 0.55 ** tap
                buf = wet
            elif tr.insert == "FDN8" and "delay_dead" not in sim.faults:
                ir = rng.randn(int(TAIL_S * FS)) * np.exp(-np.arange(int(TAIL_S * FS)) / (TAIL_S / 6.9 * FS)) * 0.02
                buf = buf + np.fft.irfft(np.fft.rfft(buf, n + len(ir)) * np.fft.rfft(ir, n + len(ir)))[:n]
            elif tr.insert == "CHOR" and "delay_dead" not in sim.faults:
                m = int(0.012 * FS)
                buf = buf + 0.7 * np.concatenate([np.zeros(m), buf[:n - m]])
            out += buf
        if "audio_clicks" in sim.faults:
            out[::BLOCK * 40] += 0.5
        out = np.clip(out, -1, 1)
        return np.stack([out, out], axis=1).astype(np.float32)
