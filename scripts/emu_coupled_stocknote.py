"""stocknote (stage 1, warm): a stock note through both processors (emu_coupled.py), OS 1.12.

The ColdFire resumes this build's own UI snapshot (snap800); the DSP runs this build's section 7 from the
runner's warm state. [TRK] + [TRIG t], KEYBOARD, [TRIG 9] held for N periods on two stock tracks: each
track's voices must put sound in their track buffers (the DSP's block after the chain). The main mix tap
(sampler.machines.MAIN_TAP) is reported only: pvmix fills it, and it reads 0 here on r11f too (heard on the unit).

Stage 2 (a cold boot: the ColdFire's power-on upload and READY) is not covered here: the DSP side is warm.

2026-11-14: --ours TRACK:TYPE puts our machine on by MACHINE SEL's commit (the gate's ournote: 2:21 DRONE, then 2:23
JUNO, each in its own run). Until the runner's G12-G14 only voice slot 0 sounded here, so the gate's runs play their
note first; with the warm snapshot built under them every slot does (docs/coupled-emulator.md).

Validated 2026-11-13: r11f (heard on the unit) 0.0232, r14 (silent on the unit) 0.0001, r14b (r14, optstock off)
0.0232. A gate step that must pass on ours whatever clean does (autobuild report.MUST_PASS).

Usage (bench):
  python -u scripts/emu_coupled_stocknote.py --build X.syx --stock 1.12.syx --snapshot S [--json OUT]"""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
Coupled = importlib.import_module("emu_coupled").Coupled         # the tree's own harness

KIT, STRIDE, SOUND_TYPE = 0x800052A0, 1163, 0xDE
SLOT_TRACK = 0x80005308                  # the ColdFire's voice -> track table
KB_ON = 0x42432A9C                       # KEYBOARD on (1.11's 0x42431A9C, BSS + 0x1000 on 1.12)
TRK, KEYBOARD, TRIG1, NOTE_KEY = 16, 18, 25, 33
FLOOR, CEIL = 1e-3, 4.0
SMOOTHER = 0x400DB28E                   # the stock parameter smoother (1.12; emu_slides.py)
SM_STATE, SM_SRC, SM_OUT = 0x8000DE60, 0x80003AF0, 0x800068E4
OWNER_FN = 0x4018AC5A                   # MACHINE SEL's model owner (1.12; emu_coupled_recplay.py)


def install_smoother_model(c) -> None:
    """emu_slides.py's model of the stock smoother (1.12): its one-pole filter runs in the EMAC's fractional mode,
    and digikit's EMAC halves every fractional product, so emulated the state decays to about half a frame and
    every voice's levels fall to nothing (the first stocknote runs: r11f, heard on the unit, silent here). The
    routine's entry runs this instead: state' = (0x7c29 state + 0x3d7 (src << 16)) >> 15, out = (state' + 0x8000)
    >> 16, then its block copy and the LFO DEST copies, as its code does."""
    K = importlib.import_module("unicorn.m68k_const")
    hook = importlib.import_module("unicorn").UC_HOOK_CODE
    m = c.machine

    def smoother(uc_, address, size, user):
        src = struct.unpack(">1734H", bytes(m.read(SM_SRC, 2 * 1734)))
        st = list(struct.unpack(">1734i", bytes(m.read(SM_STATE, 4 * 1734))))
        out = []
        for i in range(1734):
            v = (0x7C29 * st[i] + 0x3D7 * (src[i] << 16)) >> 15
            v = max(-0x80000000, min(0x7FFFFFFF, v))
            st[i] = v
            out.append(((v + 0x8000) >> 16) & 0xFFFF)
        m.write(SM_STATE, struct.pack(">1734i", *st))
        for t in range(16):
            for off in (42, 58, 74):
                out[(off + 202 * t) // 2] = src[(off + 202 * t) // 2]
        m.write(SM_OUT, struct.pack(">1734H", *out))
        m.write(0x80007670, bytes(m.read(SM_SRC + 3468, 0x990)))
        sp = uc_.reg_read(K.UC_M68K_REG_A7)
        uc_.reg_write(K.UC_M68K_REG_A7, sp + 4)
        uc_.reg_write(K.UC_M68K_REG_D0, SM_OUT)
        uc_.reg_write(K.UC_M68K_REG_PC, m.long(sp))
    c.uc.hook_add(hook, smoother, begin=SMOOTHER, end=SMOOTHER)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--stock", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--tracks", default="1", help="stock tracks (0-based; not 0: unassigned voices read 0); 1: track 2, type 0")
    p.add_argument("--ours", default="", help="TRACK:TYPE of ours put on first (21 DRONE, 23 JUNO: the gate's ournote, "
                                                 "one a run with --tracks '', so its note is on voice slot 0)")
    p.add_argument("--layout", default=str(REPO / "src/dnfw/mods/waverider_code.json"))
    p.add_argument("--periods", type=int, default=48)
    p.add_argument("--advance", type=int, default=0, help="short notes played first on --advance-track, so the next "
                                                          "note lands on that voice slot (the ColdFire's turn)")
    p.add_argument("--advance-track", type=int, default=1)
    p.add_argument("--expect-slot", type=int, default=None, help="our tracks' voices must include this slot")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    c = Coupled(a.build, a.snapshot, a.stock, verbose=True)
    c.watchdog()
    install_smoother_model(c)
    P = c.panel.panelin

    def key(code):
        return divmod(code - 1, 8)

    def held(code, on, n=3):
        c.machine.pc = (P.press if on else P.release)(c.machine.m, c.panel.profile, *key(code))
        c.periods(n)

    def tap(code):
        held(code, True)
        held(code, False)

    c.periods(8)
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    ours = [tuple(int(x) for x in s.split(":")) for s in a.ours.split(",") if s]
    owner = c.call(OWNER_FN)[0]
    for t, ty in ours:
        c.call(lay["smp_machine_commit"], owner + 0xF4, t, ty, 1, 1)
        c.periods(2)
    kit = c.long(KIT)
    types = [c.read(kit + 52 + STRIDE * t + SOUND_TYPE, 1)[0] for t in range(16)]
    rep = {"types": types, "tracks": {}, "halt": None}
    print(f"  machine types, tracks 1..16: {types}", flush=True)
    SM = importlib.import_module("dnfw.sampler.machines")
    ok_all = True
    side = {int(x): "stock" for x in a.tracks.split(",") if x} | {t: "ours" for t, _ in ours}
    if a.advance:                               # 2026-11-14: the voice slots the ColdFire hands out in turn moved on
        held(TRK, True)
        tap(TRIG1 + a.advance_track)
        held(TRK, False)
        c.periods(4)
        if not c.read(KB_ON, 1)[0]:
            tap(KEYBOARD)
        for _ in range(a.advance):
            held(NOTE_KEY, True, 2)
            held(NOTE_KEY, False, 2)
        c.periods(8)
        print(f"  {a.advance} short notes on track {a.advance_track + 1} first: slot tracks "
              f"{list(struct.unpack('>16I', c.read(SLOT_TRACK, 64)))}", flush=True)
    for t in side:
        held(TRK, True)
        tap(TRIG1 + t)
        held(TRK, False)
        c.periods(4)
        if not c.read(KB_ON, 1)[0]:
            tap(KEYBOARD)
        kb = c.read(KB_ON, 1)[0]
        c.machine.pc = P.press(c.machine.m, c.panel.profile, *key(NOTE_KEY))
        peak, main_peak, voices = 0.0, 0.0, set()
        for k in range(a.periods):
            if not c.period():
                break
            if k == 10:                             # juno-engine's split: what the ColdFire hands the DSP, as built
                pool = importlib.import_module("dnfw.sampler.live").layout().pool
                rep.setdefault("dumps", {})[t] = {
                    "frame_be": c.last_frame.hex(),
                    "pool": pool, "link_words": [c.dsp_word(pool + a_) for a_ in range(0xED0, 0x1000, 4)]}
            vt = struct.unpack(">16I", c.read(SLOT_TRACK, 64))
            pk_now = 0.0
            for v in range(16):
                if vt[v] == t:
                    voices.add(v)
                    pk_now = max(pk_now, max(abs(x) for x in c.last_bufs[v]))
            peak = max(peak, pk_now)
            rep.setdefault("series", {}).setdefault(t, []).append(pk_now)
            if k % 4 == 0:
                print(f"    period {k}: track {t + 1} peak {pk_now:.4g}", flush=True)
            main_peak = max(main_peak, max(abs(x) for x in c.dsp_floats(SM.MAIN_TAP, 64)))
        c.machine.pc = P.release(c.machine.m, c.panel.profile, *key(NOTE_KEY))
        c.periods(16)
        # (main_peak reported only: MAIN_TAP is pvmix's, 0 here). 2026-11-14: and bounded (a block after the chain is
        # within +-CEIL; JUNO's first coupled run read 1.1e33, a blow-up the floor alone passed)
        ok = bool(voices) and FLOOR < peak < CEIL and not c.halt
        if a.expect_slot is not None and side[t] == "ours":     # (the advance run: our note on that slot)
            ok &= a.expect_slot in voices
        ok_all &= ok
        rep["tracks"][t] = {"side": side[t], "type": types[t], "keyboard": kb, "voices": sorted(voices), "track_peak": peak,
                            "main_peak": main_peak, "ok": ok}
        print(("  ok    " if ok else "  FAIL  ") + f"track {t + 1} ({side[t]}, type {types[t]}): voices {sorted(voices)}, "
              f"track peak {peak:.4f}, main peak {main_peak:.4f}, keyboard {kb}"
              + ("" if 0 in voices else " (not on voice slot 0)"),
              flush=True)
    rep["halt"], rep["status"] = c.halt, getattr(c, "last_status", None)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1, default=str))
    print(f"  DSP status tail: {rep['status']}", flush=True)
    for s in ("stock", "ours"):
        got = [v["ok"] for v in rep["tracks"].values() if v["side"] == s]
        print(f"  {s}: {sum(got)} of {len(got)} tracks sound", flush=True)
    print(("PASS" if ok_all else "FAIL") + (f" (halt: {c.halt})" if c.halt else ""), flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
