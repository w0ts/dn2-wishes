"""2026-11-16 (PARA as one voice, the User: "one bigger voice"; docs/paraphonic-onevoice.md): the SHARC runner's PARA
checks, part of step para (and step mnm). The chord plays on ONE slot (slot 0, track 0: the slot the runner's frames
latch notes on); its joined notes are the ColdFire's row (csrc/para/one.c), in slot 0's own frame words (frame slots
para.ROW_SLOT.., as pv_out writes them since 2026-11-17; until then the TDM link wrote it to the rows' DDR). The model runs on the DSP's memory at PERC's
entry (sharc_waverider_m5.run_blocks), so every run is held to the model, block by block, bit for bit.

Runs, each PARA engine (tag):
  PV_tag:       note 60 on at block 1, held 80 blocks (past the quiet test's 64); the row from block 1: the leader's
                own note and +4 +7 +11;
  PVL_tag:      (2026-11-17, v0.57.1 on the unit: only the chord's lowest note sounded, its row late over the TDM
                link) PV_tag with the row LATE_ROW - 1 blocks after the note-on: the leader's note-on at block 1
                meets no chord in its frame words, the chord comes at block LATE_ROW;
  PV_tag_off:   the same frames and rows, PARA OFF: the slot plays its own note, no shadow;
  PV8_tag:      eight places at block 1 (0, +3 .. +21); at NINTH a ninth place and the leader's own note dropped
                (the ColdFire's "Drop the oldest"); at TENTH a tenth and place 1 dropped;
  PV_tag_guard: (not held to the model, which has no clock) PV_tag with the frame guard refusing slot 0 from block GUARD_FROM (the clock fed past its limit at its
                first read): the whole chord silent then (one voice), no word of a shadow left over.
Checks: the runs bit-exact to the model; every note of the chord heard in the leader's render (PV and PVL: each
note's fundamental at least 4 x its level in PARA OFF's render, where only the leader's note plays, and at least a
tenth of the leader's fundamental); the chord sounds on its slot, LEADER, three blocks of the pool taken, none
lost; PARA OFF none; held past the quiet test it still sounds; PV8: after each event the pool holds the playing places
(a dropped one freed after its fade), the leader sounds every block, no step around the events larger than the
chord's own before or after (x 1.2 + 0.05); the refused leader silent, its blocks still the chord's.
"""

from __future__ import annotations

import struct

PV_HELD = 80
LATE_ROW = 4                                    # PVL: the chord's row reaches the DSP 3 blocks after the leader's note-on
HEAR_FROM = 8                                   # the notes-heard check: blocks HEAR_FROM .. PV_HELD of the render
NINTH, TENTH, PV8_BLOCKS = 24, 60, 100
GUARD_FROM, GUARD_BLOCKS = 6, 24
CHORD = {0: 0, 1: 4, 2: 7, 3: 11}


def _row(places: dict, seq: int = 1, lead: int = 60) -> list[int]:
    """the row's words: PLACES {k: (offset, sounding)}"""
    from dnfw.engines.analog2 import para as PA
    hw = [0] * (2 * PA.row_words())
    hw[0] = 0x8000 | (seq << 8) | lead
    for k, (off, snd) in places.items():
        hw[1 + k] = (off & 0xFF) | 0x100 | (PA.P_SOUND if snd else 0) | PA.P_USED | (1 << 12)
    return [hw[2 * j] | hw[2 * j + 1] << 16 for j in range(PA.row_words())]


def _frames(m5, sound, machines, para: int, engine: str, schedule: dict | None = None):
    """slot 0 on ENGINE at its defaults, track 0, note 60 on at block 1 and held; PARA PARA; SCHEDULE {b: row words}:
    from block b on, slot 0's frame words carry that row (2026-11-17: the row rides in the voice's own frame words,
    frame slots para.ROW_SLOT.., as csrc/para/one.c pv_out writes them)"""
    from dnfw.engines.analog2 import para as PA
    from dnfw.mnm import machines as MM
    ak = MM.NAMES.index(engine)
    t0 = MM.TYPES[ak]

    def fb(b):
        f = m5.base_frame(sound, machines, t0=t0, overrides=m5.mnm_words(ak), note=0x3C00)
        if b == 1:
            f.trigger(0, masks=(m5.FR.TRIG_NOTE, 38))      # (Frame.trigger sets 36 too: no note-off here)
        f.param(0, m5.A2_PARA_SLOT, para << 8)
        at = [k for k in (schedule or {}) if k <= b]
        if at:
            w = schedule[max(at)]
            for i in range(2 * len(w)):
                f.param(0, PA.ROW_SLOT + i, (w[i >> 1] >> (16 * (i & 1))) & 0xFFFF)
        return f.to_bytes()
    return fb


def _hooks(m5, schedule: dict, seen: list):
    """after block b's PERC (the sample machines' entry): ROLE[0], FREE, LOST and the pool's META words recorded, and
    block b + 1's row (SCHEDULE {b: row words}) poked into slot 0's row"""
    from dnfw.engines.analog2 import para as PA
    from dnfw.waverider import dsp
    st = {"b": -1}

    def at_perc(r):
        st["b"] += 1

    def at_smp(r):
        wd = lambda a: m5.m2.word(r.state, a) or 0          # noqa: E731
        import os
        if os.environ.get("PV_ONLY") and st["b"] in schedule and st["b"] > 1 and m5.LAST_MODEL_MEM is not None:
            mm = m5.LAST_MODEL_MEM                # (a diagnosis: where the DSP's words and the model's first part)
            spans = [("slot 0", m5.PERC_L.md.state, 256)] + [(f"pool {k}", PA.POOL + PA.BLOCK * k, 256)
                                                            for k in range(PA.POOL_N)] + [("para", PA.AREA, PA.WORDS)]
            for name, base, n in spans:
                d = [(k, hex(wd(base + 4 * k)), hex(mm.get(base + 4 * k) & 0xFFFFFFFF)) for k in range(n)
                     if wd(base + 4 * k) != mm.get(base + 4 * k) & 0xFFFFFFFF]
                if d:
                    print(f"    block {st['b']}: {name} differs at (word, dsp, model): {d[:6]} ({len(d)} words)",
                          flush=True)
        seen.append({"role": wd(PA.ROLE), "free": wd(PA.FREE), "lost": wd(PA.LOST),
                     "metas": [wd(PA.POOL + PA.BLOCK * k + 4 * PA.META) for k in range(PA.POOL_N)]})
        # (until 2026-11-17 the next block's row was poked into the rows' DDR here; it now rides in the frames, _frames)
    return {dsp.PERC_SW: at_perc, dsp.SMP_SW: at_smp}


def _run(m5, init, fb, blocks, schedule, extra=None):
    seen = []
    hooks = _hooks(m5, schedule, seen)
    hooks.update(extra or {})
    r = m5._slim(m5.run_blocks(init, fb, blocks, extra_hooks=hooks))
    r["seen"] = seen
    return r


def runs(m5, init, sound, machines, engines=None) -> dict:
    """ENGINES (2026-11-16, gate speed: step mnm's parts): the PARA engines to run, (engine, tag) pairs; None every
    one of m5.PARA_ENGINES"""
    import os
    only = os.environ.get("PV_ONLY")            # (a diagnosis: one run, e.g. PV8_a2)
    out = {}
    four = {1: _row({k: (o, True) for k, o in CHORD.items()})}
    eight = {k: (3 * k, True) for k in range(8)}
    ninth = dict(eight) | {0: (0, False), 8: (24, True)}
    tenth = dict(ninth) | {1: (3, False), 9: (27, True)}
    sched8 = {1: _row(eight), NINTH: _row(ninth), TENTH: _row(tenth)}
    for engine, tag in (m5.PARA_ENGINES if engines is None else engines):
        late = {1: [0] * len(four[1]), LATE_ROW: four[1]}
        todo = {f"PV_{tag}": (3, PV_HELD, four), f"PVL_{tag}": (3, PV_HELD, late),
                f"PV_{tag}_off": (0, PV_HELD, four),
                f"PV8_{tag}": (3, PV8_BLOCKS, sched8)}
        for name, (para, blocks, sched) in todo.items():
            if not only or name == only:
                out[name] = _run(m5, init, _frames(m5, sound, machines, para, engine, sched), blocks, sched)
    return out


def guards(m5, init, sound, machines, engines=None) -> dict:
    """the guard runs (not held to the model: the model has no clock), each engine (ENGINES as runs')"""
    four = {1: _row({k: (o, True) for k, o in CHORD.items()})}
    return {f"PV_{tag}_guard": _guard(m5, init, _frames(m5, sound, machines, 3, engine, four), four)
            for engine, tag in (m5.PARA_ENGINES if engines is None else engines)}


def _guard(m5, init, fb, schedule):
    """the frame guard refusing slot 0 from GUARD_FROM (its first clock read fed past its limit)"""
    from dnfw.perc import guard as G
    at = m5._after_emuclk("perc")
    st = {"b": -1}

    def count(r):
        st["b"] += 1

    def feed(r):
        if st["b"] >= GUARD_FROM:
            lim = m5.m2.word(r.state, G.LIMIT_PERC) or 0
            mark0 = m5.m2.word(r.state, G.MARK0) or 0
            r.state.uregs[m5.fx.UREG_CODES["R8"]] = m5.fx.Const((mark0 + lim + 1) & 0xFFFFFFFF)

    def back(r):
        if st["b"] >= GUARD_FROM:
            r.state.uregs[m5.fx.UREG_CODES["R8"]] = m5.fx.Const(m5.m2.word(r.state, G.START) or 0)
    seen = []
    hooks = _hooks(m5, schedule, seen)
    perc_hook = hooks[next(iter(hooks))]
    from dnfw.waverider import dsp
    hooks[dsp.PERC_SW] = lambda r: (count(r), perc_hook(r))
    hooks[at[0]] = feed
    hooks[at[1]] = back
    r = m5._slim(m5.run_blocks(init, fb, GUARD_BLOCKS, extra_hooks=hooks))
    r["seen"] = seen
    return r


def _blocks_of(seen, b, owner=0):
    """the pool blocks slot OWNER holds after block B (in use, not out)"""
    from dnfw.engines.analog2 import para as PA
    if b >= len(seen):
        return None
    return [k for k, m in enumerate(seen[b]["metas"])
            if m & PA.M_USE and (m >> PA.M_SLOT) & 15 == owner]


def _level(x: list[float], f: float, rate: int) -> float:
    """the Hann-windowed magnitude of X at F Hz (Goertzel), per sample"""
    import math
    n = len(x)
    if not n:
        return 0.0
    w = 2 * math.cos(2 * math.pi * f / rate)
    s1 = s2 = 0.0
    for k, v in enumerate(x):
        s0 = v * (0.5 - 0.5 * math.cos(2 * math.pi * k / (n - 1))) + w * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - w * s1 * s2)) / n


def heard(m5, run, off) -> dict:
    """each chord note's fundamental in RUN's leader render (blocks HEAR_FROM .. PV_HELD), beside PARA OFF's (OFF:
    the leader's note alone): {offset: (level, off level)}"""
    a = m5.perc_series(run, 0)[32 * HEAR_FROM:32 * PV_HELD]
    b = m5.perc_series(off, 0)[32 * HEAR_FROM:32 * PV_HELD]
    hz = lambda o: 440.0 * 2 ** ((60 + o - 69) / 12)          # noqa: E731 (the frames' note 60)
    return {o: (_level(a, hz(o), m5.RATE), _level(b, hz(o), m5.RATE)) for o in CHORD.values()}


def all_heard(lv: dict) -> bool:
    lead = lv[0][0]
    return lead > 0 and all(v >= 4 * w and v >= 0.1 * lead for o, (v, w) in lv.items() if o)


def checks(m5, rr: dict, gg: dict, n: dict) -> dict:
    from dnfw.engines.analog2 import para as PA
    V = m5.V
    out = {}
    for engine, tag in m5.PARA_ENGINES:
        pv, off, p8 = (rr.get(k) for k in (f"PV_{tag}", f"PV_{tag}_off", f"PV8_{tag}"))
        g = gg.get(f"PV_{tag}_guard")
        if not pv:
            continue
        ok = all(x and x["ok"] for x in (pv, off, p8, g))
        lead = m5.perc_series(pv, 0) if ok else []
        role = [(s["role"] >> PA.ROLE_SHIFT) & 3 for s in pv["seen"]] if ok else []
        n[f"pv_{tag}"] = {"peak": round(V.peak(lead), 4) if lead else None,
                          "blocks_after_1": _blocks_of(pv["seen"], 1) if ok else None,
                          "lost": pv["seen"][-1]["lost"] if ok else None,
                          "off_peak": round(V.peak(m5.perc_series(off, 0)), 4) if ok else None}
        out[f"{engine} PARA one voice: a 4-note chord on slot 0: LEADER, its three joined notes in three pool blocks, "
            "none lost; it sounds; PARA OFF: no role, no block, the note sounds"] = (
            ok and V.peak(lead) > 0.05 and role[2] == PA.LEADER and len(_blocks_of(pv["seen"], 2)) == 3
            and pv["seen"][-1]["lost"] == 0 and all((s["role"] >> PA.ROLE_SHIFT) & 3 == 0 for s in off["seen"])
            and _blocks_of(off["seen"], len(off["seen"]) - 1) == [] and V.peak(m5.perc_series(off, 0)) > 0.05)
        tail = lead[32 * (PV_HELD - 8):] if ok else []
        out[f"{engine} PARA one voice: held {PV_HELD} blocks (past the quiet test's 64) the chord still sounds, its "
            "blocks still its own"] = ok and V.peak(tail) > 0.05 and len(_blocks_of(pv["seen"], PV_HELD - 1)) == 3
        l8 = m5.perc_series(p8, 0) if ok else []
        held = {b: _blocks_of(p8["seen"], b) for b in (NINTH - 1, NINTH + 12, TENTH + 12)} if ok else {}
        steps = [abs(l8[k] - l8[k - 1]) for k in range(1, len(l8))]

        def most(b0, b1):
            return max(steps[32 * b0:32 * b1]) if len(steps) >= 32 * b1 - 1 else None
        nend = len(steps) // 32
        events = [(NINTH, most(NINTH - 1, NINTH + 8), most(8, NINTH - 1), most(NINTH + 9, TENTH - 1)),
                  (TENTH, most(TENTH - 1, TENTH + 8), most(NINTH + 9, TENTH - 1), most(TENTH + 9, nend))] if ok else []
        clean = ok and all(None not in ev and ev[1] <= 1.2 * max(ev[2], ev[3]) + 0.05 for ev in events)
        per = [l8[32 * b:32 * b + 32] for b in range(len(l8) // 32)]
        n[f"pv8_{tag}"] = {"blocks": held, "events": events,
                           "own_fade": [(s["role"] >> PA.FADE_SHIFT) & 7 for s in p8["seen"][NINTH - 1:NINTH + 8]]
                           if ok else None}
        out[f"{engine} PARA one voice, 8 notes: 7 blocks before the 9th; the 9th takes one and the leader's own note "
            "fades out; the 10th takes one and place 1's is freed after its fade; the leader sounds every block"] = (
            ok and len(held[NINTH - 1]) == 7 and len(held[NINTH + 12]) == 8 and len(held[TENTH + 12]) == 8
            and (p8["seen"][NINTH + 12]["role"] >> PA.FADE_SHIFT) & 7 == PA.FADE_OUT
            and all(V.peak(x) > 0.005 for x in per[4:]))
        out[f"{engine} PARA one voice, 8 notes: no click around the 9th and 10th notes (the leader's largest step no "
            "more than the chord's own before or after, x 1.2 + 0.05)"] = clean
        pvl = rr.get(f"PVL_{tag}")
        ok_l = ok and bool(pvl and pvl["ok"])
        lv = heard(m5, pv, off) if ok else {}
        lvl = heard(m5, pvl, off) if ok_l else {}
        n[f"heard_{tag}"] = {"row_at_note_on": {o: [round(x, 5) for x in v] for o, v in lv.items()},
                             "row_late": {o: [round(x, 5) for x in v] for o, v in lvl.items()},
                             "late_blocks": _blocks_of(pvl["seen"], LATE_ROW + 1) if ok_l else None}
        out[f"{engine} PARA one voice: every note of a 4-note chord heard (its fundamental in the leader's render, "
            "4 x PARA OFF's), its row there at the note-on"] = ok and all_heard(lv)
        out[f"{engine} PARA one voice: every note heard when the chord's row comes {LATE_ROW - 1} blocks after the "
            "leader's note-on (as the TDM link brings it), three pool blocks taken"] = (
            ok_l and all_heard(lvl) and len(_blocks_of(pvl["seen"], LATE_ROW + 1) or []) == 3)
        gl = m5.perc_series(g, 0) if ok else []
        out[f"{engine} PARA one voice under the frame guard: refused from block {GUARD_FROM}, the whole chord is "
            "silent (one voice); its blocks stay the chord's"] = (
            ok and V.peak(gl[32 * 3:32 * GUARD_FROM]) > 0.05 and V.peak(gl[32 * (GUARD_FROM + 1):]) == 0.0
            and len(_blocks_of(g["seen"], GUARD_BLOCKS - 1)) == 3)
    return out


def step(m5, init, sound, machines) -> dict:
    """the runs, each bit-exact to the model, and their checks"""
    import os
    rr = runs(m5, init, sound, machines)
    gg = {} if os.environ.get("PV_ONLY") else guards(m5, init, sound, machines)
    exact = {k: m5.perc_exact(r) for k, r in rr.items() if r["ok"]}
    # where a run differs from the model: its blocks, and the slot's words that differ there
    where = {k: [(b, t, v["out_mismatches"], v.get("differ")) for b, blk in enumerate(r["perc"]) for t, v in blk.items()
                 if v["out_mismatches"] or v["state_mismatches"]] for k, r in rr.items() if r["ok"]}
    n = {"exact": exact, "differs_at": {k: v[:20] for k, v in where.items() if v}}
    for k, v in n["differs_at"].items():
        print(f"    {k} differs from the model at (block, slot, words): {v}", flush=True)
    c = {"every PARA run (" + ", ".join(rr) + "), every block, bit-exact to the model":
         all(r["ok"] for r in rr.values()) and all(v[0] > 0 and v[1:] == (0, 0) for v in exact.values())}
    c.update(checks(m5, rr, gg, n))
    return {"ok": all(c.values()), "checks": c, "numbers": n}


_ = struct
