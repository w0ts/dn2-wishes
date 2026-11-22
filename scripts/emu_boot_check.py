"""The gate every build passes before it is allowed near the instrument.

    # in WSL, with digikit's venv (docs/emulator.md):
    DT2_SECTIONS=/root/dn2-sections-111 /root/dn2-emu-venv/bin/python -u \
        scripts/emu_boot_check.py out/lfo4-bridge/section_3_MAIN_OS.bin

One question, asked from **reset**: does this image boot and draw its UI?

`lfo4-bridge` is why this exists. It passed every check it had, then drew the
instrument's `EXCEPTION` screen at boot -- because every one of those checks
restored `ui1200M`, a snapshot of a machine that has *already booted*. Nothing
ever ran the loader, the init, or the first call into the new code from reset.
Flashing is a ten-minute MIDI transfer and a recovery if it fails; this costs
nothing but wall-clock and runs unattended.

Three outcomes, and they are deliberately not the same:

- **fault** -- the firmware's own reporter at `0x4011ed4a` ran. That routine
  formats `V%02x M%x P%08x`, so the vector, the mode and the faulting PC come
  from the machine rather than from a photograph of the screen.
- **no UI** -- it never faulted and never composed a frame either. A hang looks
  like a pass to anything that only watches for a crash, which is why the
  milestone is checked and not assumed.
- **booted** -- frames were composed and nothing faulted.

The control is the stock image, and it is not optional: it fixes how many
instructions a real boot takes on this machine, so "no UI yet" can be told
apart from "not far enough yet". Its result is cached in `out/boot-check/`,
since stock does not change.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import pathlib
import sys
import time

sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

from emu import dspboot, symbols                              # noqa: E402
from emulib import quickboot                                  # noqa: E402
from unicorn import UC_HOOK_CODE                              # noqa: E402
from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_D3  # noqa: E402

ROOT = pathlib.Path("/mnt/d/01_Code/Z_Personal/dn2_firmware")
SYX = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.11_dist/Digitone_II_OS1.11.syx"
CACHE = ROOT / "out/boot-check/control.json"
REPORTER = 0x4011ED4A
ANIZ_LIMIT = 700_000_000                 # v0.37: past the intro's first frame (measured: shown before 700M)

# **The control is only a control while the emulator it was measured on stays
# put.** This caches what a stock boot does, because stock does not change --
# but digikit does, and a change there can move the boot without moving the
# image. Its `machine-ideas-menu` branch replaces `unblock`'s single
# `display_sem` skip with a `never_fake` list of seven semaphores, which is
# exactly the kind of change that alters how far a from-reset boot gets.
#
# Comparing a build against a control measured under a different emulator is
# comparing two things at once. So the cache carries a fingerprint of the
# emulator's own sources, and refreshes itself when they move.
EMU = pathlib.Path("/mnt/d/01_Code/Z_Personal/digikit-up/emu")


def emulator_fingerprint():
    """-> a digest of digikit's `emu/` sources, or None if they are not here."""
    import hashlib

    if not EMU.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(EMU.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def stock_path():
    return os.path.join(os.environ["DT2_SECTIONS"], "section_3_MAIN_OS.bin")


# 2026-11-16 (7f7e7d6c, EXCEPTION at every power-on: OS 1.12's +Drive bounce buffer, 0x4e6f9300..0x4e709300,
# the uncached alias of 0x466f9300..0x46709300, overwrote the boot-screen stamp at 0x46708000). Stock's read
# (0x4012c87a) goes through that buffer whenever its destination is not 16-aligned or its length not whole
# sectors, 64 KiB a call. A blank emulated card never makes such a read long enough (measured: stock's own
# boot reads end at 0x4e6f9500 on a blank card, 0x4e701300 with a project, in 32 KiB pieces); a unit with a
# project and samples does. BOUNCE makes one: after stock's first +Drive read at power-on (it returns to
# 0x400f1804), the boot task calls stock's read itself, SECTOR, BYTES into BUF (unaligned), then goes on as
# before. Everything under the buffer is then what the instrument would hold. With DNFW_DDR_ALIAS=1
# (emulib/quickboot.py) 0x4e... is the same memory as 0x46..., as on the instrument.
READ_112, FIRST_READ_RET = 0x4012C87A, 0x400F1804


def bounce_read(uc, spec, state):
    from unicorn.m68k_const import (UC_M68K_REG_A0, UC_M68K_REG_A1, UC_M68K_REG_A7,  # noqa: PLC0415
                                    UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_PC)
    sector, nbytes, buf = spec
    regs = (UC_M68K_REG_D0, UC_M68K_REG_D1, UC_M68K_REG_A0, UC_M68K_REG_A1)
    box = {}

    def at_ret(uc, address, size, user):
        sp = uc.reg_read(UC_M68K_REG_A7)
        if not box:                                         # stock's first read is back: ours now
            box["saved"] = [uc.reg_read(r) for r in regs]
            box["sp"] = sp
            frame = sp - 16
            uc.mem_write(frame, struct.pack(">4I", FIRST_READ_RET, sector, nbytes, buf))
            uc.reg_write(UC_M68K_REG_A7, frame)
            uc.reg_write(UC_M68K_REG_PC, READ_112)
        elif "done" not in box and sp == box["sp"] - 12:      # ours is back (its rts popped the return
            box["done"] = uc.reg_read(UC_M68K_REG_D0)         # address; the arguments are ours to pop)
            uc.reg_write(UC_M68K_REG_A7, box["sp"])          # as before it
            for r, v in zip(regs, box["saved"]):
                uc.reg_write(r, v)
            state["bounce"] = {"sector": sector, "bytes": nbytes, "buf": f"{buf:#010x}", "rc": box["done"]}
    uc.hook_add(UC_HOOK_CODE, at_ret, begin=FIRST_READ_RET, end=FIRST_READ_RET)


def bounce_spec():
    v = os.environ.get("DNFW_BOOT_BOUNCE")
    return None if not v else tuple(int(x, 0) for x in v.split(":"))


def run(image_path, limit, frame_at, entries=(), aniz=None, guard=False, bounce=None):
    """Boot from reset. -> (instructions, frames, the fault or None, reached, the code guard's failure or None).

    `entries` are the build's own routines. Whether they ran is as much a part
    of the result as whether it crashed: see `coverage` below.
    """
    holder, state = {}, {"frames": 0, "fault": None, "guard": None}
    reached = {name: 0 for name, _ in entries}

    def pre_start(m):
        st = holder["st"]

        def at_frame(uc, address, size, user):
            state["frames"] += 1

        def at_reporter(uc, address, size, user):
            a2 = uc.reg_read(UC_M68K_REG_A2)
            try:
                record = bytes(uc.mem_read(a2, 16))
            except Exception:                                  # noqa: BLE001
                record = b""
            state["fault"] = {"at": st["n"], "a2": a2, "record": record.hex()}
            if aniz is not None:
                try:
                    state["fault"]["stamp_words"] = bytes(uc.mem_read(aniz["stamp"], 8)).hex()
                except Exception:                              # noqa: BLE001
                    pass
            uc.emu_stop()

        m.uc.hook_add(UC_HOOK_CODE, at_frame, begin=frame_at, end=frame_at)
        m.uc.hook_add(UC_HOOK_CODE, at_reporter, begin=REPORTER, end=REPORTER)
        if bounce is not None:
            bounce_read(m.uc, bounce, state)
        for name, addr in entries:
            def hit(uc, address, size, user, name=name):
                reached[name] += 1
            m.uc.hook_add(UC_HOOK_CODE, hit, begin=addr, end=addr)
        if aniz is not None:
            # v0.37, the start-up animation: each time the stamp's decoder has a frame
            # ready to show (aniz_show), the frame it decoded (zst + 16, 1 KB) against the
            # frame d3 (dnfw.bootanim: s!Rwa²'s own since v0.39), bit for bit
            def at_show(uc, address, size, user):
                k = uc.reg_read(UC_M68K_REG_D3)
                got = bytes(uc.mem_read(aniz["zst"] + 16, 1024))
                aniz["shown"] += 1
                aniz["frames"].add(k)
                if not (0 <= k < len(aniz["expect"])) or got != aniz["expect"][k]:
                    aniz["wrong"].append(k)
            m.uc.hook_add(UC_HOOK_CODE, at_show, begin=aniz["show"], end=aniz["show"])

            def at_stamp(uc, address, size, user):
                aniz["calls"] += 1
                if aniz["calls"] == 1:
                    aniz["first_at"] = st["n"]
            m.uc.hook_add(UC_HOOK_CODE, at_stamp, begin=aniz["stamp"], end=aniz["stamp"])

    # v0.43: without dspboot's per-instruction counting hook (emulib/quickboot.py): the same
    # machine state, 1.7x faster; the instruction count of a stop is not kept
    m, st, stop = quickboot.run(str(SYX), open(image_path, "rb").read(), limit=limit,
                                machine_out=holder, pre_start=pre_start)
    if guard and os.environ.get("DNFW_CODEGUARD") == "1":   # remoteui-6: the C chunk's code as built
        from emulib import codeguard                         # noqa: PLC0415
        state["guard"] = codeguard.after_boot(m.uc)
    print(f"  the run stopped on: {stop}", flush=True)
    if bounce is not None:
        print(f"  +Drive read through the bounce buffer at power-on: {state.get('bounce', 'NOT MADE')}")
        if "bounce" not in state:
            state["guard"] = state["guard"] or "CODEGUARD FAIL: the boot never made its +Drive bounce read"
    return st["n"], state["frames"], state["fault"], reached, state["guard"]


def control(limit, frame_at, refresh=False):
    """-> what a stock boot does here, cached: stock does not change.

    The emulator does, though, so a cache measured under a different `emu/`
    is re-measured rather than trusted -- and says so, because a control that
    silently re-ran is a twenty-minute surprise and a control that silently
    did not is a wrong answer.
    """
    now = emulator_fingerprint()
    if CACHE.exists() and not refresh:
        row = json.loads(CACHE.read_text())
        if row.get("emulator") == now:
            return row
        print(f"  the emulator changed since this control was measured "
              f"({row.get('emulator')} -> {now}); re-measuring it")
    started = time.time()
    ran, frames, fault, _, _ = run(stock_path(), limit, frame_at)
    row = {"ran": ran, "frames": frames, "fault": fault, "limit": limit,
           "seconds": round(time.time() - started, 1), "emulator": now}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(row, indent=1) + "\n")
    return row


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("image", help="a built section_3_MAIN_OS.bin")
    p.add_argument("--limit", type=int, default=450_000_000)
    p.add_argument("--refresh-control", action="store_true")
    p.add_argument("--aniz", action="store_true",
                   help="v0.37: the build plays the start-up animation (dnfw.bootanim): every frame the "
                        "stamp shows is checked against his (s!Rwa²'s), and every frame must show")
    args = p.parse_args()

    profile = symbols.resolve(open(stock_path(), "rb").read())
    frame_at = profile.panel_diff

    base = control(args.limit, frame_at, args.refresh_control)
    print(f"  control (stock 1.11): {base['frames']} frame(s) in {base['ran']:,} "
          f"instruction(s){'' if base['seconds'] is None else f', {base['seconds']}s'}"
          f"{'  [cached]' if not args.refresh_control else ''}")
    if base["fault"] or not base["frames"]:
        print("  the control did not boot cleanly here -- fix the harness, not the build.")
        return 2

    started = time.time()
    # The build writes its routines beside its section, so the list comes from
    # the build itself rather than one kept in step by hand. `routines.json`
    # is `nm`'s code symbols only; `symbols.json` is everything, and filtering
    # it by name is the older, worse answer -- it reported counters as
    # routines that never ran, which is true of a counter and says nothing.
    entries = []
    folder = os.path.dirname(args.image)
    beside = os.path.join(folder, "routines.json")
    fallback = os.path.join(folder, "symbols.json")
    if os.path.exists(beside):
        sym = {k: int(v, 16) for k, v in json.load(open(beside)).items()}
        entries = sorted((k, v) for k, v in sym.items() if not k.endswith("_displaced"))
    elif os.path.exists(fallback):
        sym = {k: int(v, 16) for k, v in json.load(open(fallback)).items()}
        entries = sorted((k, v) for k, v in sym.items()
                         if k.startswith(("lfo4_", "dnfw_")) and not k.endswith("_displaced")
                         and not k.startswith("lfo4_size"))
        print("  no routines.json: falling back to filtering symbols.json by name, "
              "which lists data as routines.")
    else:
        print("  no symbols.json beside the image: coverage cannot be reported, "
              "and a boot alone does not clear a build.")
    aniz = None
    if args.aniz:
        here = pathlib.Path(__file__).resolve().parent
        sys.path.insert(0, str(here.parent / "src"))
        from dnfw import bootanim                                # noqa: PLC0415
        from dnfw.mods import bootscreen                         # noqa: PLC0415
        aniz = {"show": bootscreen.SPEC["aniz_show"], "zst": bootscreen.SPEC["zst"],
                "stamp": bootscreen.SPEC["stamp"], "calls": 0, "first_at": None,
                "expect": bootanim.images(), "shown": 0, "frames": set(), "wrong": []}
        # from reset the intro first calls the stamp near 316M, and its first frame is
        # shown (aniz_show) after the stock intro routine returns, past 450M; under dspboot
        # the intro's timers do not run on (stock too stops at one frame), so here the first
        # frame is checked, and scripts/emu_aniz_check.py checks every frame from `boot400M`
        args.limit = max(args.limit, ANIZ_LIMIT)
    bounce = bounce_spec()
    ran, frames, fault, reached, guard = run(args.image, args.limit, frame_at, entries, aniz, guard=True,
                                             bounce=bounce)
    print(f"  {os.path.basename(os.path.dirname(args.image))}: {frames} frame(s) in "
          f"{ran:,} instruction(s), {round(time.time() - started, 1)}s\n")

    if aniz is not None and fault:
        print(f"  the intro called the stamp {aniz['calls']} time(s); the stamp's first words when it stopped: "
              f"{fault.get('stamp_words', '?')}")
    if fault:
        rec = bytes.fromhex(fault["record"])
        print("  FAULT -- the firmware drew EXCEPTION." if not fault["at"] else
              f"  FAULT after {fault['at']:,} instructions -- the firmware drew EXCEPTION.")
        print(f"    record at {fault['a2']:#010x}: {fault['record']}")
        if len(rec) >= 8:
            print(f"    a2@(2) = {rec[2]:#04x}   a2@(4) = "
                  f"{int.from_bytes(rec[4:8], 'big'):#010x}")
        print("\n  DO NOT FLASH.")
        return 1
    if guard:                                                # remoteui-6 (emulib/codeguard.py)
        print(f"{guard}\n\n  DO NOT FLASH.")
        return 1
    if not frames:
        print(f"  NO UI: it never faulted and never composed a frame, while stock composed "
              f"{base['frames']} by here.\n  That is a hang, not a pass.\n\n  DO NOT FLASH.")
        return 1
    # Booting is necessary and nowhere near sufficient. `lfo4-bridge` booted
    # here for 400 M instructions without ever calling `lfo4_refresh` -- the
    # audio engine does not run -- and then faulted on the instrument the
    # moment it did. A gate that says passed about code it never executed is
    # the exact failure it exists to prevent, so coverage is part of the
    # verdict rather than a footnote under it.
    if aniz is not None:
        n = len(aniz["expect"])
        print(f"  the intro called the stamp {aniz['calls']} time(s)"
              + (f", the first at instruction {aniz['first_at']}" if aniz["first_at"] else ""))
        print(f"  start-up animation: {aniz['shown']} frame(s) shown, {len(aniz['frames'])} of {n} "
              f"distinct, {len(aniz['wrong'])} not his")
        if aniz["wrong"] or 0 not in aniz["frames"]:
            print(f"  the animation is wrong or incomplete (wrong: {sorted(set(aniz['wrong']))[:10]}, "
                  f"missing: {sorted(set(range(n)) - aniz['frames'])[:10]}).\n\n  DO NOT FLASH.")
            return 1
    ran_names = sorted(n for n, c in reached.items() if c)
    idle = sorted(n for n, c in reached.items() if not c)
    print(f"  booted and drew its UI ({frames} frame(s), control {base['frames']}).")
    listed = ", ".join(f"{n} x{reached[n]}" for n in ran_names) or "none"
    print(f"  of this build's {len(reached)} routine(s), {len(ran_names)} ran: {listed}")
    if idle:
        print("")
        print("  NOT EXERCISED: " + ", ".join(idle))
        print("  Booting says these did not break the boot. It says NOTHING about")
        print("  whether they work, because they never ran. Anything the sequencer")
        print("  or the audio engine reaches needs its own harness -- the emulator")
        print("  runs neither. scripts/emu_boot_engine.py covers the engine path.")
        print("")
        print("  Boots, but NOT cleared for flashing on its own.")
        return 1
    print("")
    print("  Safe to flash as far as booting goes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
