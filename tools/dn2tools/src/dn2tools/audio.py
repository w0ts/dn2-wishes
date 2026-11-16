"""Capturing the unit's output: USB audio through sounddevice (48 kHz stereo), or, for the dry run, the simulator's
rendering of what it was played. Plus the WAV writer the reports use."""

from __future__ import annotations

import wave
from abc import ABC, abstractmethod

import numpy as np

from .audio_analysis import FS
from .unit import Unit


class Recorder(ABC):
    t0: float = 0.0

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> np.ndarray:
        """-> float32 (N, 2) at 48 kHz, from `start` to now"""

    def close(self) -> None:
        pass


class DeviceRecorder(Recorder):
    """the Digitone II's USB audio input (sounddevice); the device is found by name"""

    def __init__(self, unit: Unit, name: str = "Digitone"):
        import sounddevice as sd                       # the "audio" extra: pip install "./tools/dn2tools[audio]"
        self.sd, self.unit = sd, unit
        found = [(k, d) for k, d in enumerate(sd.query_devices()) if name.lower() in d["name"].lower() and d["max_input_channels"] >= 2]
        if not found:
            raise SystemExit(f"no audio input with {name!r} in its name and two channels: is the Digitone II in USB audio mode? "
                             f"(inputs: {[d['name'] for d in sd.query_devices() if d['max_input_channels']] or 'none'})")
        self.index, self.info = found[0]
        self.chunks: list[np.ndarray] = []
        self.stream = None

    def start(self) -> None:
        self.chunks = []
        self.stream = self.sd.InputStream(device=self.index, channels=2, samplerate=FS, dtype="float32",
                                          callback=lambda data, frames, t, status: self.chunks.append(data.copy()))
        self.stream.start()
        self.t0 = self.unit.clock()

    def stop(self) -> np.ndarray:
        self.stream.stop()
        self.stream.close()
        return np.concatenate(self.chunks) if self.chunks else np.zeros((0, 2), np.float32)


def write_wav(path, x: np.ndarray, fs: int = FS) -> None:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())
