"""AMP ON/OFF for the drum machines on the ColdFire (csrc/msel/ampsw.c, dnfw.waverider.ampsw, docs/live-select.md):
the gate's `drumamp` step, on the ColdFire emulator with the build installed over its own UI snapshot, the UI running.
(The DSP's half, the bypass itself, is the `ampdsp` step: scripts/sharc_ampsw_step.py.)

  1. picks (MACHINE SEL's commit, smp_machine_commit, as the UI calls it) of every machine on a track with an odd AMP
     set A0 and VOL: the sound's AMP words and VOL never change (nothing of ours writes them any more); the mask
     (as_mask, what the DSP is sent) has the track's bit exactly when the machine is a drum (MACHINEDRUM, SOPHIE, DRUM;
     PLAITS on BD/SD/HH) and its AMP is OFF; every new pick reads OFF (no field);
  2. PLAITS: MODL turned (stock's setter, as a knob) onto BD, SD, VA, HH: the bit on, on, off, on;
  3. the field: as_set ON clears the bit, OFF sets it; ON is the record's field WT_AMP_SW (as_on), OFF none;
  4. the page (stock's AMP page, AMP 1/2, on the active track): on a drum, H is drawn as AMP (as_draws moves, the screen
     archived); H turned right: ON, left: OFF, VOL's word untouched; H's push toggles; on WaveTone H turns VOL as stock
     (its word moves, the field and the counters do not);
  5. stock's SAVE and LOAD carry it: a drum sound saved ON, then set OFF, loaded back: ON; a stored sound without our
     link (an old sound, a preset) loaded over it: OFF;
  6. the link: as_sent (the word last sent to the DSP) == as_mask once the link has sent (reported when it never runs);
  7. no fault.

Every check prints PASS or FAIL; the last line is PASS or FAIL.
Usage: emu_amp_switch.py --build BUILD.syx --snapshot SNAP [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

KIT_PTR, STRIDE, TYPE_AT, VALUES = 0x800052A0, 1163, 0xDE, 0x14
UI_TRACK = 0x42432A6C
OWNER_FN, PARAM_SET, SET_VALUE = 0x4018AC5A, 0x40041A40, 0x40037326
LOAD, SAVE, STORED = 0x400DD34E, 0x400DD80A, 359      # stock's sound LOAD / SAVE (scripts/emu_wishes.py)
SCRATCH = 0x46A30000                                   # our stored sounds (emu_wishes.py's place)
AMP_KEY = (0, 3)                                       # [AMP] (code 4: scope.c K_AMP)
KNOB_H, PUSH_H = 7, (5, 7)
AMP_SLOTS = (80, 81, 82, 83, 84, 85, 91, 92)           # DEL ATK HOLD DEC SUS REL MODE RSET
VOL_SLOT = 90
A0 = (0x0300, 0x0A40, 0x4000, 0x2A00, 0x5500, 0x3300, 0x0000, 0x0000)
VOL0 = 0x5300
WAVETONE, SWARMER, FMTONE, FMDRUM, ONESHOT, MONO = 1, 3, 0, 2, 8, 6


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--json", default=None)
    p.add_argument("--layout", default=str(HERE.parent / "src/dnfw/mods/waverider_code.json"))
    a = p.parse_args()
    from emu_encoder_trace import guest
    from emulib.image import differences
    from emulib.machine import Machine
    from emulib.panel import Panel
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    from dnfw.mods import platform
    from dnfw.sampler import machines as SMx
    from dnfw.waverider import ampsw as AS
    from dnfw.waverider import msel as MS
    from unicorn import UC_PROT_ALL, UcError

    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    m = Machine(a.snapshot)
    stock = open(pathlib.Path(os.environ.get("DT2_SECTIONS", HERE.parent.parent / "sec111")) / "section_3_MAIN_OS.bin",
                 "rb").read()
    m.apply([(va, stock[va - 0x40000400:va - 0x40000400 + len(b)])
             for va, b in differences(stock, open(a.snapshot + ".section_3_MAIN_OS.bin", "rb").read())
             if va + len(b) <= 0x40000400 + len(stock)])
    sec3 = load(read_image(pathlib.Path(a.build))).container.find(3).unpack()
    m.apply(differences(stock, sec3))
    for va, blob in platform.runtime(sec3):
        m.write(va, blob)
    from emulib import attkit
    attkit.store_kit(m)  # (2026-11-21) a converted kit stored back: converted once
    for at, n in ((SMx.MIRROR, 0x500000), (SCRATCH, 0x10000)):
        for pg in range(at & ~0xFFFFF, at + n, 0x100000):
            try:
                m.uc.mem_map(pg, 0x100000, UC_PROT_ALL)
            except UcError:
                pass
    m.flush()
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/amp_switch").with_suffix("")) + "_png")

    results: list[tuple[str, bool]] = []
    report: dict = {}

    def check(name, ok, detail=""):
        results.append((name, bool(ok)))
        print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)

    if "as_mask" not in lay:
        check("the build has AMP ON/OFF (as_mask in its layout)", False)
        print("FAIL: no AMP ON/OFF in this build", flush=True)
        return 1
    drums = set(AS.drum_types())
    pl = AS.plaits()
    kit = m.long(KIT_PTR)

    def snd(t):
        return kit + 52 + STRIDE * t

    def mtype(t):
        return struct.unpack(">b", bytes(m.read(snd(t) + TYPE_AT, 1)))[0]

    def word(t, slot):
        return struct.unpack(">H", bytes(m.read(snd(t) + VALUES + 2 * slot, 2)))[0]

    def put_word(t, slot, v):
        m.write(snd(t) + VALUES + 2 * slot, struct.pack(">H", v))

    def amp(t):
        return tuple(word(t, s) for s in AMP_SLOTS) + (word(t, VOL_SLOT),)

    def mask():
        return m.long(lay["as_mask"]) & 0xFFFF

    def on(t):
        return guest(m, lay["as_on"], snd(t)) & 1

    def is_drum(t):
        return AS.is_drum(mtype(t), word(t, pl[1]) if pl else 0)

    def commit(t, ty):
        owner = guest(m, OWNER_FN)
        guest(m, lay["smp_machine_commit"], owner + 0xF4, t, ty, 1, 1)
        panel.settle(3_000_000)

    def setter(t, rid, value):
        owner = guest(m, OWNER_FN)
        ps = guest(m, PARAM_SET, owner, rid, t)
        if ps:
            guest(m, SET_VALUE, ps, rid, value, t, 0, 0, 1)
        panel.settle(5_000_000)

    def poll():
        guest(m, lay["as_poll"])

    def bit(t):
        poll()
        return (mask() >> t) & 1

    panel.settle(5_000_000)
    ui = m.read(UI_TRACK, 1)[0]
    d = 1 if ui != 1 else 2
    print(f"active track {ui}, direct moves on track {d}; drum types {sorted(drums)}, PLAITS {pl}", flush=True)

    # 1. picks
    commit(d, WAVETONE)
    for s, v in zip(AMP_SLOTS, A0):
        put_word(d, s, v)
    put_word(d, VOL_SLOT, VOL0)
    before = amp(d)
    seq = [SWARMER, 5, 53, 55, 5, WAVETONE, FMTONE, 54, 53, 52, 50, 5, ONESHOT, FMDRUM, 18, MONO, 51]
    seq += sorted(t for t in drums if t not in (5, 53)) + [WAVETONE]
    bad_amp, bad_bit = [], []
    for ty in seq:
        commit(d, ty)
        if amp(d) != before:
            bad_amp.append((ty, amp(d)))
        want = int(is_drum(d))
        if bit(d) != want or (want and on(d)):
            bad_bit.append((ty, MS.machine_names().get(ty, ty), bit(d), want))
    check(f"1. {len(seq)} picks: the AMP words and VOL never written", not bad_amp, str(bad_amp[:3]))
    check("1. the mask's bit exactly on the drum machines, each picked OFF", not bad_bit, str(bad_bit[:4]))

    # 2. PLAITS' MODL
    if pl:
        ty_pl, slot, lo, dmin, dmax = pl
        from dnfw.engines.plaits import plaits as PLT
        from dnfw.perc import machines as PM
        rid = PM.PARAMS[PLT.MODL_K][0]
        w = {"BD": (lo + dmin + 2) << 8, "SD": (lo + dmin + 10) << 8, "VA": (lo + 20) << 8, "HH": (lo + dmax - 2) << 8}
        commit(d, ty_pl)
        got = []
        for model, want in (("BD", 1), ("SD", 1), ("VA", 0), ("HH", 1)):
            setter(d, rid, w[model])
            got.append((model, bit(d), want))
        check("2. PLAITS: MODL onto BD SD VA HH: the bit on, on, off, on", all(g == x for _m, g, x in got), str(got))
    else:
        check("2. PLAITS in the build", False)

    # 3. the field
    commit(d, 53)
    s3 = []
    guest(m, lay["as_set"], snd(d), 1)
    s3.append(("ON", on(d), bit(d)))
    guest(m, lay["as_set"], snd(d), 0)
    s3.append(("OFF", on(d), bit(d)))
    check("3. as_set ON: as_on 1, the bit off; OFF: as_on 0, the bit on", s3 == [("ON", 1, 0), ("OFF", 0, 1)], str(s3))

    # 4. the page, on the active track
    u = ui
    commit(u, 53)
    put_word(u, VOL_SLOT, VOL0)
    panel.tap(AMP_KEY, after=20_000_000)
    panel.settle(20_000_000)
    draws0 = m.long(lay["as_draws"])
    panel.settle(20_000_000)
    report["drum page"] = panel.screen("amp_page_drum")
    draws = m.long(lay["as_draws"])
    check("4. stock's AMP page on a drum: H drawn as AMP ON/OFF", draws > 0, f"as_draws {draws0} -> {draws}")

    def turn(delta):
        panel.m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_H, delta)
        panel.settle(10_000_000)
    turns0 = m.long(lay["as_turns"])
    turn(+1)
    r_on = (on(u), bit(u), word(u, VOL_SLOT))
    report["drum page ON"] = panel.screen("amp_page_drum_on")
    turn(-1)
    r_off = (on(u), bit(u), word(u, VOL_SLOT))
    check("4. H right: ON (the bit off), VOL untouched", r_on == (1, 0, VOL0), str(r_on))
    check("4. H left: OFF (the bit on), VOL untouched", r_off == (0, 1, VOL0), str(r_off))
    panel.tap(PUSH_H)
    r_push = (on(u), word(u, VOL_SLOT))
    panel.tap(PUSH_H)
    r_push2 = (on(u), word(u, VOL_SLOT))
    check("4. H pushed: ON, pushed again: OFF, VOL untouched", (r_push, r_push2) == ((1, VOL0), (0, VOL0)),
          f"{r_push} {r_push2}")
    turns1 = m.long(lay["as_turns"])
    commit(u, WAVETONE)
    put_word(u, VOL_SLOT, VOL0)
    panel.settle(20_000_000)
    # (2026-11-21: H turned as a sustained turn, 4 records of 12 counts: stock 1.12's own rest guard (0x4011364e: while
    # its rest counter is above 24 it eats 3 x the counts) held the first ones (measured on drum-64 84f5906f: +1 x 2,
    # +3 x 4, one +12 moved nothing; +12 x 3 more moved VOL 12 steps; stock and our build alike)
    for _ in range(4):
        turn(+12)
    report["wavetone page"] = panel.screen("amp_page_wavetone")
    vol_wt = word(u, VOL_SLOT)
    check("4. on WaveTone H turns VOL as stock (its word moved, nothing of ours)",
          vol_wt != VOL0 and m.long(lay["as_turns"]) == turns1 and on(u) == 0, f"VOL {vol_wt:#06x}")
    report["turns"] = (turns0, turns1)

    # 5. stock's SAVE and LOAD
    st_on, st_old = SCRATCH, SCRATCH + 0x200
    m.write(st_on, bytes(STORED))
    m.write(st_old, bytes(STORED))
    commit(d, WAVETONE)
    guest(m, SAVE, st_old, snd(d), 0)                    # a stored sound with no record: an old sound, a preset
    commit(d, 53)
    guest(m, lay["as_set"], snd(d), 1)
    guest(m, SAVE, st_on, snd(d), 0)
    commit(u, 53)                                        # another drum track, OFF
    r5a = on(u)
    guest(m, LOAD, snd(u), st_on)                        # (2026-11-21: into another track, as emu_wishes' 3: the record
    panel.settle(10_000_000)                             # from RAM; this harness has no +Drive for the cell)
    r5 = (mtype(u), r5a, on(u), bit(u))
    check("5. a SOPHIE sound saved ON, loaded into an OFF drum track: ON", r5 == (53, 0, 1, 0), str(r5))
    guest(m, lay["as_set"], snd(d), 0)
    guest(m, LOAD, snd(d), st_old)
    panel.settle(10_000_000)
    commit(d, 53)
    r5b = (mtype(d), on(d), bit(d))
    check("5. a stored sound without our record loaded, SOPHIE picked: OFF", r5b == (53, 0, 1), str(r5b))

    # 6. the link
    panel.settle(30_000_000)
    poll()
    sent, msk = m.long(lay["as_sent"]), mask()
    report["link"] = {"as_sent": sent, "as_mask": msk}
    if sent == msk:
        check("6. the word the DSP was last sent == the mask", True, f"{msk:#06x}")
    else:
        print(f"NOTE 6. the link has not sent the mask here (as_sent {sent:#x}, mask {msk:#x}): the emulator's TDM "
              "link may not run; the DSP side is the ampdsp step", flush=True)

    faults = getattr(m.m, "faults", [])
    check("7. no fault", not faults, str(faults[:3]))
    failed = [n for n, ok in results if not ok]
    report["results"] = results
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1, default=str))
    print(f"{len(results) - len(failed)}/{len(results)} passed", flush=True)
    print(("FAIL: " + "; ".join(failed[:6])) if failed else
          "PASS: AMP ON/OFF on the drum machines' page, field and mask; picks never touch AMP; VOL stock elsewhere",
          flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
