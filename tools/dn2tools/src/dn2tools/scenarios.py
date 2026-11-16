"""The scenarios (docs/device-tests.md). Each plays notes on the tracks the project file names, polls the
telemetry and asserts; a scenario whose track is not in the project is skipped, not failed."""

from __future__ import annotations

from typing import Callable

from .ctx import CHORD, SIXTEEN, Ctx, Result, delta16
from .frame import FRAMES_PER_S, Telemetry
from .project import FILTERS, Track

PROTO_MIN = 7                          # the sample link's version that has the telemetry's neighbours
BUILD_MAJOR = 0x0047                   # the frame's build id: 0.47 << 16 | format


def _cause(s: Telemetry, label: str, ins_age_max: int = 1600) -> bool:
    """does this reading show why a label may be lit (the triggers in csrc/meter/meter.c)"""
    if label == "D":
        return bool(s.skip_mask) or (s.d_pct or 0) >= 97 or (s.d_peak_pct or 0) >= 97 \
            or (s.ins_skip_age is not None and s.ins_skip_age <= ins_age_max)
    if label == "C":
        return (s.c_pct or 0) >= 85 or (s.c_peak_pct or 0) >= 85
    return s.ins_full or (s.heap_pct or 0) >= 90


def labels_explained(ctx: Ctx, window_s: float = 2.5) -> None:
    """no label is lit without a cause in the last `window_s` seconds of readings (the 2026-11 report:
    DSP lit below 70 % load). The label holds a second after its event, hence the window."""
    bad = []
    for k, (t, s) in enumerate(ctx.samples):
        for bit, name in enumerate("DCM"):
            if s.labels_lit >> bit & 1 and not s.labels_force >> bit & 1:
                recent = [x for u, x in ctx.samples[:k + 1] if t - u <= window_s]
                if not any(_cause(x, name) for x in recent):
                    bad.append(f"t={t:.1f}s {name} lit, D {s.d_pct}% C {s.c_pct}% skip {s.skip_mask:#x}")
    ctx.check("a label is lit only with a cause", not bad, "; ".join(bad[:3]))


def _tracks(ctx: Ctx, pred) -> tuple[Track, ...]:
    return ctx.project.where(pred)


# -- scenarios ------------------------------------------------------------------------------

def link(ctx: Ctx) -> None:
    """the telemetry answers, is the right build, the audio frame counter runs"""
    proto = ctx.unit.hello()
    ctx.number("sample_link_proto", proto)
    ctx.check("sample link version", proto >= PROTO_MIN, f"{proto}, {PROTO_MIN} or later")
    a = ctx.sample()
    ctx.wait(0.5)
    b = ctx.sample()
    ctx.number("build_id", f"{a.build:#010x}")
    ctx.check("build id is the 0.47 telemetry frame", a.build >> 16 == BUILD_MAJOR, f"{a.build:#010x}")
    grew = (b.frames - a.frames) & 0xFFFFFFFF
    ctx.check("audio frame counter runs at 1,500 a second", 0.7 * 0.5 * FRAMES_PER_S <= grew <= 1.3 * 0.5 * FRAMES_PER_S,
              f"{grew} frames in 0.5 s")
    ctx.check("heap walked, no fault", b.heap_faults == 0 and b.heap_used is not None, f"faults {b.heap_faults}")


def idle(ctx: Ctx) -> None:
    """nothing playing, sequencer stopped: the meters read low and no label is lit"""
    ctx.silence(1.0)
    rs = ctx.run(2.0)
    last = rs[-1]
    d, c = max(r.d_peak_pct or 0 for r in rs), max(r.c_peak_pct or 0 for r in rs)
    ctx.number("idle D peak %", d)
    ctx.number("idle C peak %", c)
    ctx.number("idle heap %", round(last.heap_pct or 0, 1))
    ctx.number("idle voices rendering", last.voices)
    ctx.check("DSP load at idle", d <= ctx.params.idle_d_max, f"{d} % (limit {ctx.params.idle_d_max})")
    ctx.check("ColdFire load at idle", c <= ctx.params.idle_c_max, f"{c} % (limit {ctx.params.idle_c_max})")
    ctx.check("no label lit at idle", all(not r.lit for r in rs), f"lit: {sorted({n for r in rs for n in r.lit})}")
    ctx.check("no voice skipped for time at idle", all(r.skip_mask == 0 for r in rs))
    ctx.check("no insert block passed through at idle", rs[-1].ins_skips == rs[0].ins_skips)
    ctx.check("no voice rendering at idle", last.voices == 0, f"{last.voices} slots with a cost")
    labels_explained(ctx)


def wiring(ctx: Ctx) -> None:
    """each project track answers its channel: a note makes a voice render, and stops"""
    ctx.silence(1.0)
    for tr in ctx.project.tracks:
        base = ctx.sample().voices
        ctx.play(tr, (60,))
        ctx.wait(0.5)
        on = ctx.sample()
        ctx.release(tr, (60,))
        ctx.wait(1.5)
        off = ctx.sample()
        ctx.check(f"{tr.label}: ch {tr.channel + 1} plays a voice", on.voices > base, f"{base} -> {on.voices} slots rendering")
        if tr.hold:                                      # the key is latched: the same key again lets it go
            ctx.play(tr, (60,))
            ctx.wait(0.15)
            ctx.release(tr, (60,))
            ctx.wait(2.0)
            continue
        ctx.check(f"{tr.label}: the voice ends", off.voices <= base, f"{off.voices} after the release (slot cost never clears?)")
    labels_explained(ctx)


def a2_filter(tr: Track) -> Callable[[Ctx], None]:
    def scenario(ctx: Ctx) -> None:
        p = ctx.params
        ctx.silence(1.0)
        base = ctx.sample()
        # one note held: still sounding and still filtered after the first second
        ctx.play(tr, (60,))
        rs = ctx.run(p.hold_s)
        end = rs[-1]
        late = [r for r in rs if r.frames - rs[0].frames >= FRAMES_PER_S] or rs[-1:]    # (a hold under a second: the last reading)
        ctx.check("one note: still rendering after the hold", end.voices > base.voices,
                  f"{base.voices} -> {end.voices} slots, {end.cost_pct:.1f} % of a frame")
        ctx.check("one note: filtered the whole hold", delta16(late[0].a2_filtered, end.a2_filtered) > 0,
                  f"filtered +{delta16(late[0].a2_filtered, end.a2_filtered)} in the last {p.hold_s - 1:.0f} s")
        ctx.check("one note: filter not left dry", delta16(rs[0].a2_dry, end.a2_dry) <= delta16(rs[0].a2_filtered, end.a2_filtered),
                  f"dry +{delta16(rs[0].a2_dry, end.a2_dry)}")
        ctx.number("1 voice: slots cost %", round(end.cost_pct - base.cost_pct, 1))
        ctx.release(tr, (60,))
        ctx.silence(1.0)
        # four stacked
        mid = ctx.sample()
        ctx.play(tr, CHORD)
        rs = ctx.run(p.hold_s)
        end = rs[-1]
        last_s = [r for r in rs if end.frames - r.frames <= FRAMES_PER_S]
        fil, dry = delta16(last_s[0].a2_filtered, end.a2_filtered), delta16(last_s[0].a2_dry, end.a2_dry)
        ctx.check("4 stacked: 4 voices rendering", end.voices >= mid.voices + 4, f"{mid.voices} -> {end.voices} slots")
        ctx.check("4 stacked: still filtering in the last second", fil > 0, f"filtered +{fil}, dry +{dry}")
        ctx.check("4 stacked: not mostly dry", dry <= fil, f"dry +{dry} vs filtered +{fil}")
        ctx.check("4 stacked: inserts not passed through", end.ins_skips - mid.ins_skips <= p.ins_skip_cap,
                  f"+{end.ins_skips - mid.ins_skips} blocks (cap {p.ins_skip_cap})")
        top = max(r.d_peak_pct or 0 for r in rs)
        ctx.check("4 stacked: DSP load under the limit", top < p.d_limit, f"peak {top} %")
        ctx.check("4 stacked: no voice skipped for time", all(r.skip_mask == 0 for r in rs))
        ctx.number("4 voices: DSP peak %", top)
        ctx.number("4 voices: slots cost %", round(end.cost_pct - mid.cost_pct, 1))
        ctx.release(tr, CHORD)
        ctx.silence(1.0)
        ctx.check("voices end after the release", ctx.sample().voices <= base.voices, "")
        labels_explained(ctx)
    scenario.__doc__ = f"A2 filter {tr.filter} (T{tr.number}): one note held, then four stacked; still filtered, DSP under the limit"
    return scenario


def hold(ctx: Ctx) -> None:
    """DRONE HOLD (counters hold_count / hold_drops / hold_seq): a latch holds, the same key lets go, another key takes over"""
    for tr in _tracks(ctx, lambda t: t.hold):
        ctx.silence(1.0)
        b = ctx.sample()
        ctx.play(tr, (60,))
        ctx.wait(0.15)
        ctx.release(tr, (60,))
        ctx.wait(1.5)
        s1 = ctx.sample()
        ctx.check(f"{tr.label}: a latch was made", s1.hold_count == b.hold_count + 1, f"hold_count {b.hold_count} -> {s1.hold_count}")
        ctx.check(f"{tr.label}: the key is latched (hold_seq)", s1.latched == 1, f"hold_seq {s1.hold_seq:#06x}")
        ctx.check(f"{tr.label}: still sounding after the key went up", s1.voices > b.voices, f"{b.voices} -> {s1.voices} slots")
        ctx.play(tr, (60,))                                  # the same key again: it lets go
        ctx.wait(0.15)
        ctx.release(tr, (60,))
        ctx.wait(0.5)
        s2 = ctx.sample()
        ctx.check(f"{tr.label}: same key again drops the latch", s2.hold_drops == b.hold_drops + 1 and s2.latched == 0,
                  f"hold_drops {b.hold_drops} -> {s2.hold_drops}, hold_seq {s2.hold_seq:#06x}")
        ctx.play(tr, (64,))
        ctx.wait(0.15)
        ctx.release(tr, (64,))
        ctx.wait(0.5)
        ctx.play(tr, (67,))                                   # another key takes the latch over
        ctx.wait(0.15)
        ctx.release(tr, (67,))
        ctx.wait(1.0)
        s3 = ctx.sample()
        ctx.check(f"{tr.label}: another key takes over: one voice latched", s3.latched == 1 and s3.hold_count == s2.hold_count + 2,
                  f"hold_count {s2.hold_count} -> {s3.hold_count}, hold_seq {s3.hold_seq:#06x}")
        ctx.play(tr, (67,))                                   # let go: leave the unit clean
        ctx.wait(0.15)
        ctx.release(tr, (67,))
        ctx.wait(2.0)
        s4 = ctx.sample()
        ctx.check(f"{tr.label}: released at the end", s4.latched == 0 and s4.voices <= b.voices,
                  f"hold_seq {s4.hold_seq:#06x}, {s4.voices} slots")
        ctx.number(f"{tr.label}: hold_count / hold_drops", f"{s4.hold_count} / {s4.hold_drops}")
    labels_explained(ctx)


def glide(ctx: Ctx) -> None:
    """DRONE glide (legato): overlapping notes, then separate ones. The telemetry sees the voices, not the pitch"""
    for tr in _tracks(ctx, lambda t: t.glide):
        ctx.silence(1.0)
        b = ctx.sample()
        ctx.play(tr, (60,))
        ctx.wait(0.6)
        ctx.play(tr, (67,))                                    # legato: the second key down before the first is up
        rs = ctx.run(1.5)
        ctx.release(tr, (60,))
        ctx.wait(0.5)
        ctx.release(tr, (67,))
        ctx.wait(1.5)
        ctx.check(f"{tr.label}: legato: at most two voices", max(r.voices for r in rs) <= b.voices + 2,
                  f"max {max(r.voices for r in rs)} slots (idle {b.voices})")
        ctx.check(f"{tr.label}: legato: DSP under the limit", max(r.d_peak_pct or 0 for r in rs) < ctx.params.d_limit)
        for n in (60, 67):                                      # separate notes
            ctx.play(tr, (n,))
            ctx.wait(0.4)
            ctx.release(tr, (n,))
            ctx.wait(1.5)
        e = ctx.sample()
        ctx.check(f"{tr.label}: voices end", e.voices <= b.voices, f"{e.voices} slots")
    ctx.note("pitch glide itself is audio: see 'What cannot be tested' in docs/device-tests.md")
    labels_explained(ctx)


def inserts(ctx: Ctx) -> None:
    """XDLY / FDN8 inserts engaged: not passed through for time (ins_skips), not full, DSP under the limit"""
    for tr in _tracks(ctx, lambda t: t.insert):
        p = ctx.params
        ctx.silence(1.0)
        for n in (1, 4):
            b = ctx.sample()
            ctx.play(tr, CHORD[:n])
            rs = ctx.run(p.hold_s)
            ctx.release(tr, CHORD[:n])
            e = rs[-1]
            ctx.check(f"{tr.label}, {n} voice(s): insert not passed through", e.ins_skips - b.ins_skips <= p.ins_skip_cap,
                      f"ins_skips +{e.ins_skips - b.ins_skips} (cap {p.ins_skip_cap})")
            ctx.check(f"{tr.label}, {n} voice(s): an instance is free", not any(r.ins_full for r in rs))
            ctx.check(f"{tr.label}, {n} voice(s): DSP under the limit", max(r.d_peak_pct or 0 for r in rs) < p.d_limit,
                      f"peak {max(r.d_peak_pct or 0 for r in rs)} %")
            ctx.check(f"{tr.label}, {n} voice(s): sounding", e.voices > b.voices, f"{b.voices} -> {e.voices} slots")
            ctx.number(f"{tr.label}, {n} voice(s): slots cost %", round(e.cost_pct - b.cost_pct, 1))
            ctx.silence(1.0)
    ctx.note("the unit's inserts are not visible beyond skips / full: whether an insert changes the sound is audio")
    labels_explained(ctx)


def stress(ctx: Ctx) -> None:
    """16 voices on each project track, held: D and C readings, skips, the unit survives and lets go"""
    p = ctx.params
    for tr in ctx.project.tracks:
        if tr.hold:
            continue                                            # a latch would keep them: HOLD is its own scenario
        ctx.silence(1.5)
        b = ctx.sample()
        ctx.play(tr, SIXTEEN, 90)
        rs = ctx.run(p.hold_s)
        ctx.release(tr, SIXTEEN)
        top_d, top_c = max(r.d_peak_pct or 0 for r in rs), max(r.c_peak_pct or 0 for r in rs)
        ctx.number(f"{tr.label}: 16 voices D peak %", top_d)
        ctx.number(f"{tr.label}: 16 voices C peak %", top_c)
        ctx.number(f"{tr.label}: 16 voices rendering (max)", max(r.voices for r in rs))
        ctx.number(f"{tr.label}: 16 voices skipped for time (max)", max(r.skipped_voices for r in rs))
        ctx.number(f"{tr.label}: 16 voices insert blocks passed through", rs[-1].ins_skips - b.ins_skips)
        ctx.check(f"{tr.label}: 16 voices: DSP under the limit", top_d < p.d_limit, f"peak {top_d} %")
        ctx.check(f"{tr.label}: 16 voices: the unit still answers and its clock runs", rs[-1].frames != rs[0].frames)
        ctx.silence(2.5)
        e = ctx.sample()
        ctx.check(f"{tr.label}: 16 voices: all end after the release", e.voices <= b.voices, f"{e.voices} slots")
    labels_explained(ctx)


def registry(project) -> list[tuple[str, str, Callable[[Ctx], None]]]:
    """(name, title, function) in the order they run; scenarios whose tracks the project lacks are still listed (then skipped)"""
    out = [("link", link.__doc__, link), ("idle", idle.__doc__, idle), ("wiring", wiring.__doc__, wiring)]
    for f in FILTERS:
        tr = next((t for t in project.tracks if t.filter == f), None)
        if tr:
            fn = a2_filter(tr)
            out.append((f"a2_{f.lower()}", fn.__doc__, fn))
        else:
            out.append((f"a2_{f.lower()}", f"A2 filter {f}: no track with it in the project", None))
    out += [("hold", hold.__doc__, hold), ("glide", glide.__doc__, glide), ("inserts", inserts.__doc__, inserts),
            ("stress", stress.__doc__, stress)]
    return out
