"""The audio scenarios (docs/device-tests.md, "Audio"): the unit's main output captured over USB audio while the
scenario plays, analysed with audio_analysis. Thresholds are in a JSON file (data/audio_thresholds.json). Every
scenario starts at a low velocity, announces itself on the console first, and saves its capture as a WAV."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, fields

import numpy as np

from . import audio_analysis as A
from .audio import Recorder, write_wav
from .ctx import Ctx, Params, Result
from .project import Project, Track
from .unit import Unit

NOTE_C4, NOTE_G4 = 60, 67
HZ_C4, HZ_G4 = 261.63, 392.0


@dataclass(frozen=True)
class Thresholds:
    velocity: int = 40
    note_hold_s: float = 1.5
    min_level_db: float = -60.0
    max_peak: float = 0.99
    max_clicks: int = 0
    max_click_rate_per_s: float = 0.5
    filter_diff_db: float = 6.0
    filter_pair_diff_db: float = 3.0
    resonance_gain_db: float = 6.0
    hold_persist_db: float = 6.0
    hold_decay_db: float = 30.0
    glide_min_s: float = 0.08
    glide_max_s: float = 3.0
    jump_max_s: float = 0.05
    echo_min_count: int = 1
    reverb_extra_s: float = 0.3
    reverb_min_s: float = 0.5
    insert_diff_db: float = 3.0
    pitch_tolerance_cents: float = 60

    @staticmethod
    def load(path: str | pathlib.Path | None) -> "Thresholds":
        if not path or not pathlib.Path(path).exists():
            return Thresholds()
        d = json.loads(pathlib.Path(path).read_text())
        known = {f.name for f in fields(Thresholds)}
        bad = set(d) - known
        if bad:
            raise ValueError(f"unknown threshold(s) {sorted(bad)} in {path}")
        return Thresholds(**d)


class ACtx(Ctx):
    """a Ctx with a recorder, the thresholds, and takes"""

    def __init__(self, unit: Unit, project: Project, params: Params, result: Result, rec: Recorder, thr: Thresholds, out_dir, cc_map: dict):
        super().__init__(unit, project, params, result)
        self.rec, self.thr, self.out_dir, self.cc_map = rec, thr, pathlib.Path(out_dir), cc_map
        self.x = np.zeros((0, 2))
        self.takes = 0

    def announce(self, text: str) -> None:
        print(f"  >> {self.result.name}: {text}   (velocity {self.thr.velocity}; sound plays on the unit)", flush=True)

    def at(self) -> float:
        """seconds since the capture started"""
        return self.unit.clock() - self.rec.t0

    def hold(self, seconds: float) -> None:
        self.unit.wait(seconds)

    def begin(self) -> None:
        self.rec.start()
        self.unit.wait(0.15)

    def end(self, tag: str) -> np.ndarray:
        self.x = self.rec.stop()
        self.takes += 1
        self.out_dir.mkdir(parents=True, exist_ok=True)
        write_wav(self.out_dir / f"{self.result.name}-{self.takes:02d}-{tag}.wav", self.x)
        return self.x

    def seg(self, t0: float, t1: float) -> np.ndarray:
        return self.x[int(t0 * A.FS):int(t1 * A.FS)]

    def play_note(self, tr: Track, note: int, seconds: float, tail: float = 0.0, vel: int | None = None) -> tuple[float, float]:
        """play NOTE on the track for SECONDS, then wait TAIL; -> (on, off) in capture time"""
        on = self.at()
        self.unit.note_on(tr.channel, note, vel or self.thr.velocity)
        self.unit.wait(seconds)
        off = self.at()
        self.unit.note_off(tr.channel, note)
        self.unit.wait(tail)
        return on, off

    def clean(self, name: str, x: np.ndarray) -> None:
        c = A.clicks(x)
        self.check(f"{name}: no clicks", c["n"] <= self.thr.max_clicks and not c["periodic"],
                   f"{c['n']} click(s), {c['rate_per_s']:.2f}/s, block phase share {c['block_phase_share']:.2f}")
        d = A.dropouts(x)
        self.check(f"{name}: no dropouts", not d, f"{len(d)} run(s) of zeros" + (f", first at {d[0][0] / A.FS:.2f} s ({d[0][1]} samples)" if d else ""))


def _reference(project: Project) -> Track | None:
    return next((t for t in project.tracks if t.reference), None)


# -- scenarios -------------------------------------------------------------------------------

def a_level(c: ACtx) -> None:
    """every machine at its default: not silent, not clipping, clean"""
    thr = c.thr
    for tr in c.project.tracks:
        c.announce(f"{tr.label}: one note, {thr.note_hold_s} s")
        c.begin()
        on, off = c.play_note(tr, NOTE_C4, thr.note_hold_s, 0.8)
        if tr.hold:                                              # the latch: the same key again lets it go
            c.unit.note_on(tr.channel, NOTE_C4, thr.velocity)
            c.hold(0.1)
            c.unit.note_off(tr.channel, NOTE_C4)
            c.hold(1.5)
        x = c.end(f"T{tr.number}")
        note = c.seg(on + 0.1, off)
        lvl = A.rms_db(note)
        c.number(f"{tr.label}: level dBFS", round(lvl, 1))
        c.check(f"{tr.label}: sounds (level over {thr.min_level_db} dBFS)", lvl > thr.min_level_db, f"{lvl:.1f} dBFS")
        c.check(f"{tr.label}: no clipping", A.peak(x) < thr.max_peak, f"peak {A.peak(x):.3f}")
        c.clean(tr.label, c.seg(on + 0.05, off + 0.5))
        c.silence(0.5)


def a_clicks(c: ACtx) -> None:
    """crackle: a held chord on each track, then every track at once: clicks, once-a-block clicks, dropouts"""
    thr = c.thr
    for tr in [t for t in c.project.tracks if not t.hold]:
        c.announce(f"{tr.label}: four stacked voices, 4 s")
        c.begin()
        for n in (60, 64, 67, 71):
            c.unit.note_on(tr.channel, n, thr.velocity)
        c.hold(4.0)
        for n in (60, 64, 67, 71):
            c.unit.note_off(tr.channel, n)
        c.hold(0.5)
        x = c.end(f"T{tr.number}-chord")
        c.clean(f"{tr.label} chord", c.seg(0.4, 4.2))
        c.silence(0.8)
    c.announce("every track at once, 6 s")
    c.begin()
    tracks = [t for t in c.project.tracks if not t.hold]
    for tr in tracks:
        c.unit.note_on(tr.channel, 60 + tr.number % 12, thr.velocity)
    c.hold(6.0)
    for tr in tracks:
        c.unit.note_off(tr.channel, 60 + tr.number % 12)
    c.hold(0.5)
    c.end("all")
    c.clean("all tracks", c.seg(0.5, 6.0))
    rate = A.clicks(c.seg(0.5, 6.0))["rate_per_s"]
    c.number("all tracks: clicks per second", round(rate, 2))
    c.check("all tracks: click rate", rate <= c.thr.max_click_rate_per_s, f"{rate:.2f}/s")


def a_filters(c: ACtx) -> None:
    """does each A2 filter do anything: its spectrum against the dry reference track (and against each other)"""
    thr, ref = c.thr, _reference(c.project)
    filt = [t for t in c.project.tracks if t.filter]
    spectra: dict[str, np.ndarray] = {}
    for tr in ([ref] if ref else []) + filt:
        c.announce(f"{tr.label}: one held note")
        c.begin()
        on, off = c.play_note(tr, NOTE_C4, 2.0, 0.5)
        c.end(f"T{tr.number}")
        spectra[tr.label] = c.seg(on + 0.3, off)
        c.number(f"{tr.label}: spectral centroid Hz", round(A.centroid(spectra[tr.label])))
        c.silence(0.6)
    if ref:
        for tr in filt:
            diff = A.spectral_diff_db(spectra[ref.label], spectra[tr.label])
            c.check(f"{tr.label}: differs from the dry reference", diff >= thr.filter_diff_db, f"{diff:.1f} dB (needs {thr.filter_diff_db})")
    else:
        c.note("no reference track (\"reference\": true) in the project: filters compared with each other only")
    labels = [t.label for t in filt]
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            diff = A.spectral_diff_db(spectra[a], spectra[b])
            c.check(f"{a} vs {b}: not the same sound", diff >= thr.filter_pair_diff_db, f"{diff:.1f} dB")
    res_cc, cut_cc = c.cc_map.get("resonance"), c.cc_map.get("cutoff")
    if res_cc is None or cut_cc is None:
        c.note("resonance sweep skipped: no --cc-map with \"cutoff\" and \"resonance\" controllers (the harness sends no parameter CC otherwise)")
        return
    for tr in filt:
        peaks = []
        for res in (0, 110):
            c.unit.param(tr.channel, res_cc, res)
            c.unit.param(tr.channel, cut_cc, 64)
            c.announce(f"{tr.label}: resonance {res}")
            c.begin()
            on, off = c.play_note(tr, NOTE_C4, 1.5, 0.4)
            c.end(f"T{tr.number}-res{res}")
            f, s = A.spectrum(c.seg(on + 0.3, off))
            m = (f > 150) & (f < 8000)
            peaks.append(float(np.max(s[m]) - np.median(s[m])))
            c.silence(0.4)
        c.check(f"{tr.label}: resonance raises the spectral peak", peaks[1] - peaks[0] >= thr.resonance_gain_db,
                f"{peaks[0]:.1f} -> {peaks[1]:.1f} dB over the median")


def a_hold(c: ACtx) -> None:
    """DRONE HOLD: the level persists after note off, and decays after the same key lets go"""
    thr = c.thr
    for tr in [t for t in c.project.tracks if t.hold]:
        c.announce(f"{tr.label}: note on, off after 0.4 s; listen 2 s; the same key again")
        c.begin()
        on, off = c.play_note(tr, NOTE_C4, 0.4, 2.0)
        t_rel = c.at()
        c.unit.note_on(tr.channel, NOTE_C4, thr.velocity)
        c.hold(0.1)
        c.unit.note_off(tr.channel, NOTE_C4)
        c.hold(3.0)
        x = c.end(f"T{tr.number}")
        at_off = A.level_at(x, off + 0.1)
        later = A.level_at(x, off + 1.5)
        after = A.level_at(x, t_rel + 2.5)
        c.number(f"{tr.label}: level after off / 1.4 s later / after release dBFS", f"{at_off:.1f} / {later:.1f} / {after:.1f}")
        c.check(f"{tr.label}: still sounding 1.4 s after the key went up", later >= at_off - thr.hold_persist_db,
                f"{at_off:.1f} -> {later:.1f} dBFS (loses at most {thr.hold_persist_db} dB)")
        c.check(f"{tr.label}: decays after the same key", after <= at_off - thr.hold_decay_db, f"{after:.1f} dBFS, {at_off - after:.1f} dB down")
        c.silence(0.5)


def a_glide(c: ACtx) -> None:
    """DRONE glide: overlapping (legato) notes slide in pitch over a time; separate notes jump"""
    thr = c.thr
    for tr in [t for t in c.project.tracks if t.glide]:
        c.announce(f"{tr.label}: legato C4 then G4 overlapping")
        c.begin()
        c.unit.note_on(tr.channel, NOTE_C4, thr.velocity)
        c.hold(1.0)
        t_switch = c.at()
        c.unit.note_on(tr.channel, NOTE_G4, thr.velocity)
        c.hold(0.3)
        c.unit.note_off(tr.channel, NOTE_C4)
        c.hold(2.2)
        c.unit.note_off(tr.channel, NOTE_G4)
        c.hold(0.8)
        x = c.end(f"T{tr.number}-legato")
        t, f = A.pitch_track(c.seg(t_switch - 0.5, t_switch + 3.0))
        slide = A.transition_time(t, f, HZ_C4, HZ_G4)
        c.number(f"{tr.label}: legato slide time s", None if slide is None else round(slide, 3))
        c.check(f"{tr.label}: legato slides (takes {thr.glide_min_s}..{thr.glide_max_s} s)",
                slide is not None and thr.glide_min_s <= slide <= thr.glide_max_s, f"{slide}")
        c.silence(0.6)
        c.announce(f"{tr.label}: separate notes C4 then G4")
        c.begin()
        c.play_note(tr, NOTE_C4, 0.8, 0.8)
        t_g = c.at()
        c.play_note(tr, NOTE_G4, 1.0, 0.8)
        c.end(f"T{tr.number}-separate")
        t, f = A.pitch_track(c.seg(0.0, t_g + 1.2))
        jump = A.transition_time(t, f, HZ_C4, HZ_G4)
        c.number(f"{tr.label}: separate-notes pitch change s", None if jump is None else round(jump, 3))
        c.check(f"{tr.label}: separate notes jump (under {thr.jump_max_s} s)", jump is not None and jump <= thr.jump_max_s, f"{jump}")
        c.silence(0.6)


def a_inserts(c: ACtx) -> None:
    """XDLY echoes, FDN8 tail, CHOR: wet against the dry reference track"""
    thr, ref = c.thr, _reference(c.project)
    dry = {}
    if ref:
        c.announce(f"{ref.label}: reference, a short note")
        c.begin()
        on, off = c.play_note(ref, NOTE_C4, 0.1, 3.0)
        c.end("reference")
        dry = {"x": c.seg(on, off + 3.0), "off": off - on, "tail": A.decay_time(c.seg(on, off + 3.0), off - on + 0.01, drop_db=40)}
        c.silence(0.5)
    for tr in [t for t in c.project.tracks if t.insert]:
        c.announce(f"{tr.label}: a short note, listen 3 s")
        c.begin()
        on, off = c.play_note(tr, NOTE_C4, 0.1, 3.0)
        c.end(f"T{tr.number}")
        wet = c.seg(on, off + 3.0)
        t_off = off - on
        if tr.insert == "XDLY":
            d = A.echo_delays(c.seg(on, off + 3.0))
            c.number(f"{tr.label}: echo delays ms", d[:4])
            c.check(f"{tr.label}: echoes", len(d) >= thr.echo_min_count, f"{d[:4]}")
        elif tr.insert == "FDN8":
            tail = A.decay_time(wet, t_off + 0.01, drop_db=40)
            floor = (dry.get("tail") or 0.0) + thr.reverb_extra_s if dry else thr.reverb_min_s
            c.number(f"{tr.label}: tail to -40 dB s", None if tail is None else round(tail, 2))
            c.check(f"{tr.label}: reverb tail", tail is None or tail >= floor, f"{tail} s (dry {dry.get('tail')}; needs {floor:.2f})")
        if dry:
            diff = A.spectral_diff_db(dry["x"][:len(wet)], wet[:len(dry["x"])])
            c.check(f"{tr.label}: wet differs from dry", diff >= thr.insert_diff_db, f"{diff:.1f} dB")
        c.silence(0.5)


def a_page2(c: ACtx) -> None:
    """ANALOG2 / DRONE page-2 controls change the spectrum (needs the User's CC map: the harness sends no parameter CC otherwise)"""
    m = c.cc_map.get("page2")
    if not m:
        c.note("skipped: no --cc-map with a \"page2\" list of {track, cc, low, high} entries")
        return
    for e in m:
        tr = next((t for t in c.project.tracks if t.number == e["track"]), None)
        if tr is None:
            continue
        spectra = []
        for v in (e["low"], e["high"]):
            c.unit.param(tr.channel, e["cc"], v)
            c.announce(f"{tr.label}: CC {e['cc']} = {v}")
            c.begin()
            on, off = c.play_note(tr, NOTE_C4, 1.5, 0.4)
            c.end(f"T{tr.number}-cc{e['cc']}-{v}")
            spectra.append(c.seg(on + 0.3, off))
            c.silence(0.4)
        diff = A.spectral_diff_db(*spectra)
        c.check(f"{tr.label}: CC {e['cc']} changes the sound", diff >= c.thr.insert_diff_db, f"{diff:.1f} dB")


REGISTRY = [("a_level", a_level), ("a_clicks", a_clicks), ("a_filters", a_filters), ("a_hold", a_hold), ("a_glide", a_glide),
            ("a_inserts", a_inserts), ("a_page2", a_page2)]


def run_audio(unit: Unit, project: Project, params: Params, rec: Recorder, thr: Thresholds, out_dir, cc_map: dict | None = None,
              only=None, log=print) -> list[Result]:
    results = []
    for name, fn in REGISTRY:
        if only and name not in only:
            continue
        res = Result(name, (fn.__doc__ or "").strip())
        c = ACtx(unit, project, params, res, rec, thr, out_dir, cc_map or {})
        try:
            fn(c)
        except (SystemExit, TimeoutError, ValueError, OSError) as e:
            res.error = f"{type(e).__name__}: {e}"
        finally:
            try:
                unit.all_notes_off()
            except Exception as e:                         # noqa: BLE001
                res.notes.append(f"all notes off failed: {e}")
        if not res.checks and not res.error:
            res.skipped = res.notes[0] if res.notes else "nothing to test in this project"
        results.append(res)
        failed = [x for x in res.checks if not x.ok]
        log(f"  {name:12s} {res.status:5s} {len(res.checks) - len(failed)}/{len(res.checks)} checks"
            + (f"  <- {failed[0].name}: {failed[0].detail}" if failed else "") + (f"  {res.error}" if res.error else ""))
    return results
