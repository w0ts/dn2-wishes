"""Audio analysis for the on-device tests (numpy only): clicks and dropouts, spectra, level envelopes, pitch tracks,
echoes, decay times. Pure functions over float arrays at 48 kHz; the scenarios (audio_scenarios.py) decide what to assert."""

from __future__ import annotations

import numpy as np

FS = 48_000
BLOCK = 32                                      # the DSP's block: 1,500 a second


def mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=1) if x.ndim == 2 else x


def db(v: float) -> float:
    return 20.0 * np.log10(max(float(v), 1e-12))


def rms_db(x: np.ndarray) -> float:
    x = mono(x)
    return db(np.sqrt(np.mean(x * x))) if len(x) else -240.0


def peak(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if len(x) else 0.0


def envelope(x: np.ndarray, fs: int = FS, hop_s: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """RMS in dB per hop: (times in s, dB)"""
    x, h = mono(x), max(1, int(hop_s * fs))
    n = len(x) // h
    if n == 0:
        return np.zeros(0), np.zeros(0)
    r = np.sqrt(np.mean(x[:n * h].reshape(n, h) ** 2, axis=1))
    return (np.arange(n) + 0.5) * h / fs, 20.0 * np.log10(np.maximum(r, 1e-12))


def level_at(x: np.ndarray, t: float, fs: int = FS, width_s: float = 0.1) -> float:
    """RMS dB in the window of WIDTH_S centred on T seconds"""
    a, b = max(0, int((t - width_s / 2) * fs)), int((t + width_s / 2) * fs)
    return rms_db(x[a:b])


# -- clicks, dropouts ------------------------------------------------------------------------

def clicks(x: np.ndarray, fs: int = FS, k: float = 8.0, floor: float = 0.02, merge: int = 8) -> dict:
    """isolated sample-to-sample jumps: the second difference over its own local RMS (1,024 samples) above K and over
    FLOOR (absolute). -> {events: sample indices, n, rate_per_s, block_phase_share, periodic}. `block_phase_share` is the
    share of clicks at the commonest position within a 32-sample block (random: 1/32); `periodic` when it is over a half
    with at least 8 clicks: a click once a DSP block."""
    x = mono(x)
    if len(x) < 2048:
        return {"events": [], "n": 0, "rate_per_s": 0.0, "block_phase_share": 0.0, "periodic": False}
    d2 = np.diff(x, 2)
    sq = d2 * d2
    c = np.cumsum(np.concatenate([[0.0], sq]))
    w = 1024
    scale = np.sqrt((c[w:] - c[:-w]) / w)
    scale = np.concatenate([np.full(w // 2, scale[0]), scale, np.full(len(d2) - len(scale) - w // 2, scale[-1])])[:len(d2)]
    hit = np.nonzero((np.abs(d2) > k * np.maximum(scale, 1e-9)) & (np.abs(d2) > floor))[0]
    ev: list[int] = []
    for i in hit:
        if not ev or i - ev[-1] > merge:
            ev.append(int(i) + 1)
    share = 0.0
    if len(ev) >= 8:
        share = float(np.bincount(np.array(ev) % BLOCK, minlength=BLOCK).max() / len(ev))
    return {"events": ev, "n": len(ev), "rate_per_s": len(ev) * fs / len(x), "block_phase_share": share,
            "periodic": len(ev) >= 8 and share > 0.5}


def dropouts(x: np.ndarray, fs: int = FS, min_run: int = 24, thr: float = 1e-4, around: int = 480, sig: float = 0.003) -> list[tuple[int, int]]:
    """runs of (near) zero samples at least MIN_RUN long with signal on both sides: (start, length)"""
    x = mono(x)
    quiet = np.abs(x) < thr
    out, i, n = [], 0, len(x)
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if j - i >= min_run and i >= around and j + around <= n:
                before, after = x[i - around:i], x[j:j + around]
                if np.sqrt(np.mean(before ** 2)) > sig and np.sqrt(np.mean(after ** 2)) > sig:
                    out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


# -- spectra ---------------------------------------------------------------------------------

def spectrum(x: np.ndarray, fs: int = FS, nfft: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """averaged Hann periodogram: (Hz, dB)"""
    x = mono(x)
    if len(x) < nfft:
        x = np.pad(x, (0, nfft - len(x)))
    win, acc, cnt = np.hanning(nfft), np.zeros(nfft // 2 + 1), 0
    for s in range(0, len(x) - nfft + 1, nfft // 2):
        acc += np.abs(np.fft.rfft(x[s:s + nfft] * win)) ** 2
        cnt += 1
    return np.fft.rfftfreq(nfft, 1.0 / fs), 10.0 * np.log10(np.maximum(acc / cnt, 1e-24))


def band_levels(x: np.ndarray, fs: int = FS, lo: float = 100.0, hi: float = 12_000.0, bands: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """energy per log-spaced band, dB: (band centre Hz, dB)"""
    f, s = spectrum(x, fs)
    edges = np.geomspace(lo, hi, bands + 1)
    p = 10.0 ** (s / 10.0)
    out = [10.0 * np.log10(max(p[(f >= a) & (f < b)].sum(), 1e-24)) for a, b in zip(edges[:-1], edges[1:])]
    return np.sqrt(edges[:-1] * edges[1:]), np.array(out)


def spectral_diff_db(a: np.ndarray, b: np.ndarray, fs: int = FS) -> float:
    """the largest difference between two signals' band levels, after matching their overall level (a filter that only
    turns the level down does not count): dB"""
    _, la = band_levels(a, fs)
    _, lb = band_levels(b, fs)
    la, lb = la - np.max(la), lb - np.max(lb)
    return float(np.max(np.abs(la - lb)))


def centroid(x: np.ndarray, fs: int = FS) -> float:
    f, s = spectrum(x, fs)
    p = 10.0 ** (s / 10.0)
    m = (f > 50) & (f < 16_000)
    return float(np.sum(f[m] * p[m]) / max(np.sum(p[m]), 1e-24))


def peak_gain_near(x: np.ndarray, hz: float, fs: int = FS, width: float = 0.25) -> float:
    """the spectrum's highest level within +-WIDTH (fraction) of HZ, dB (a resonance peak at the cutoff)"""
    f, s = spectrum(x, fs)
    m = (f > hz * (1 - width)) & (f < hz * (1 + width))
    return float(np.max(s[m])) if m.any() else -240.0


# -- pitch, echoes, decay ---------------------------------------------------------------------

def pitch_track(x: np.ndarray, fs: int = FS, hop_s: float = 0.02, win_s: float = 0.06, fmin: float = 60.0, fmax: float = 2000.0,
                voiced: float = 0.6) -> tuple[np.ndarray, np.ndarray]:
    """autocorrelation pitch per window: (times, Hz; nan where unvoiced)"""
    x = mono(x)
    h, w = int(hop_s * fs), int(win_s * fs)
    lo, hi = int(fs / fmax), int(fs / fmin)
    ts, fs_out = [], []
    for s in range(0, len(x) - w - hi, h):
        seg = x[s:s + w + hi]
        seg = seg - np.mean(seg)
        n = 1 << (len(seg) * 2 - 1).bit_length()
        spec = np.fft.rfft(seg, n)
        ac = np.fft.irfft(spec * np.conj(spec))[:hi + 1]
        if ac[0] <= 1e-12:
            ts.append(s / fs + win_s / 2); fs_out.append(np.nan); continue
        ac = ac / ac[0]
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] < voiced or k <= lo or k >= hi:
            f = np.nan
        else:
            a, b, c = ac[k - 1], ac[k], ac[k + 1]
            den = a - 2 * b + c
            f = fs / (k + (0.5 * (a - c) / den if den else 0.0))
        ts.append(s / fs + win_s / 2)
        fs_out.append(f)
    return np.array(ts), np.array(fs_out)


def transition_time(t: np.ndarray, f: np.ndarray, f_from: float, f_to: float, lo: float = 0.1, hi: float = 0.9) -> float | None:
    """seconds the pitch takes to go from LO to HI of the log distance between F_FROM and F_TO (None: it never gets there)"""
    ok = ~np.isnan(f)
    if ok.sum() < 3:
        return None
    pos = (np.log(f[ok]) - np.log(f_from)) / (np.log(f_to) - np.log(f_from))
    tt = t[ok]
    a = np.nonzero(pos >= lo)[0]
    b = np.nonzero(pos >= hi)[0]
    if not len(a) or not len(b):
        return None
    return float(tt[b[0]] - tt[a[0]])


def echo_delays(x: np.ndarray, fs: int = FS, hop_s: float = 0.005, min_ms: float = 40.0, max_ms: float = 1500.0, min_ac: float = 0.25) -> list[float]:
    """delays (ms) at which the level envelope repeats itself: peaks of the envelope's autocorrelation (an echo of a short
    note). An empty list: no repeat"""
    _, e = envelope(x, fs, hop_s)
    if len(e) < 8:
        return []
    lin = 10.0 ** (e / 20.0)
    lin = lin - lin.mean()
    n = 1 << (len(lin) * 2 - 1).bit_length()
    sp = np.fft.rfft(lin, n)
    ac = np.fft.irfft(sp * np.conj(sp))[:len(lin)]
    if ac[0] <= 1e-18:
        return []
    ac = ac / ac[0]
    lo, hi = int(min_ms / 1000 / hop_s), min(len(ac) - 1, int(max_ms / 1000 / hop_s))
    peaks = [k for k in range(max(lo, 1), hi) if ac[k] >= min_ac and ac[k] >= ac[k - 1] and ac[k] > ac[k + 1]]
    return [round(k * hop_s * 1000.0, 1) for k in peaks]


def decay_time(x: np.ndarray, t0: float, fs: int = FS, drop_db: float = 40.0, hop_s: float = 0.01, max_s: float = 6.0) -> float | None:
    """seconds from T0 until the level has fallen DROP_DB below the level at T0 (None: not within MAX_S)"""
    t, e = envelope(x, fs, hop_s)
    i0 = int(t0 / hop_s)
    if i0 >= len(e):
        return None
    ref = np.max(e[i0:i0 + 5]) if i0 + 5 <= len(e) else e[i0]
    for k in range(i0, min(len(e), i0 + int(max_s / hop_s))):
        if e[k] <= ref - drop_db:
            return float((k - i0) * hop_s)
    return None
