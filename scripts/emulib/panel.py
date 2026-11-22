"""Driving the instrument as a person would, and keeping what the screen said.

Two things here are not obvious and have each cost a run:

**A tap is not a hold.** The firmware calls a press longer than about 7.5 M
instructions a hold, and the natural pacing of a harness is longer than that.
So `tap` releases inside `TAP`, and `hold` is the one that lingers. A held
`[MOD]` does not cycle the pages.

**And a dwell is only a dwell if something reads it.** `settle` used to spin a
full `CHUNK` whatever it was asked for, so every tap ran 10 M and was a hold
after all -- while the code said `TAP = 2_000_000` and a `--dwell` argument
sat there being passed and ignored. It cost a sweep that reported the same
result at 500 K and at 2 M and a plan note blaming the instrument, so: a
constant that names a duration is a claim, and the first probe to lean on one
should check that changing it changes something.

**A plain turn does nothing in a menu.** Values move when the encoder's push is
held *while* it turns, which is what `push_and_turn` does. A probe that turned
without holding reported zero writes -- a clean-looking null that meant nothing.

The timers are claimed through digikit's `restore_timers`, never constructed:
`ui1200M` carries armed DMA timer registers, and ordinary construction
"repairs" them as stale, which is exactly the state the snapshot exists to hold.
"""

from __future__ import annotations

import pathlib
import struct

TAP = 2_000_000                     # well inside the hold threshold
SETTLE = 10_000_000                 # let the UI compose after an input
CHUNK = 10_000_000
CLOCK_CHUNK = 500_000              # frame_clock(): FRAMES moves every 160 frames (0.1 s), not every 2 s

# (channel, bit); `code_for` is channel * 8 + bit + 1, so code = these + 1.
MOD = (0, 5)
UP, DOWN = (1, 2), (1, 5)
YES, NO = (1, 1), (1, 3)            # codes 10 and 12, from the firmware's own table
LEFT, RIGHT = (1, 4), (1, 6)
ENCODER_PUSH = [(5, b) for b in range(8)]      # A..H, codes 41..48

# 2026-11-18: time as the unit keeps it. Stock's panel tick (0..4095, wraps) is the key task's clock (0x4011f8bc): a
# held key's repeats come from it (the first REPEAT_FIRST ticks after the press, then one every REPEAT_EVERY; on the
# unit 24 and 8, read there by PEEK), each an item with bit 3 set beside the press's own bits (bit 0). The unit runs
# UNIT_TICKS of them and UNIT_FRAMES audio frames (FRAMES_NOW) a second.
TICK_VA = 0x466768B0
REPEAT_FIRST_VA, REPEAT_EVERY_VA = 0x4029F0C8, 0x4029F0C4
UNIT_TICKS, UNIT_FRAMES = 121, 1500
F_REPEAT = 0x08


class Panel:
    """A `Machine` driven through its front panel."""

    def __init__(self, machine, png_dir="out/screens"):
        from emu import config, panel, panelin, symbols
        from emu.dtim import restore_timers

        self.m = machine
        self.panel, self.panelin = panel, panelin
        self.profile = symbols.resolve(open(config.main_image(), "rb").read())
        # Capture at `panel_diff` entry, the only moment the front buffer holds
        # a complete, untorn frame (digikit's `emu/panel.py`). `hook_at` is the
        # registrar `longrun.build` returns -- an earlier version of this looked
        # for it in `ev`, found nothing, and quietly captured no frames at all.
        self.capture = panel.Capture(machine.hook_at, diff_addr=self.profile.panel_diff,
                                     front_addr=self.profile.fb_front)
        self.timers = restore_timers(machine.m, machine.ev["deferred_checkpoint_restore"])
        if self.timers is None:
            raise SystemExit("this snapshot carries no timer state to claim")
        self.png_dir = pathlib.Path(png_dir)
        self.ran = 0                # instructions run since the snapshot resumed (every settle)
        self.clock = None           # frame_clock(): (FRAMES's address, its value at the resume, frames a second)
        self.tclock = None          # tick_clock(): [FRAMES's address, its value at tick 0, last tick read, ticks run]
        # v0.34 (docs/timing-model.md): the audio interrupt at its real cadence, when the
        # machine was built with digikit's SSI0/eDMA event source (Machine(ssi0_request_hz=..))
        ssi = machine.ev.get("ssi0_dma") if hasattr(machine, "ev") else None
        self.events = (ssi,) if ssi is not None else ()

    # --- time ---------------------------------------------------------------
    def settle(self, instructions=SETTLE):
        """Run for `instructions`, in chunks. -> what it actually ran.

        The budget is `min(CHUNK, what is left)`, and the `min` is the whole
        point: an earlier version passed `CHUNK` every time, so **every window
        shorter than a chunk ran a full chunk**. `tap` asked for 2 M and got
        10 M, past the hold threshold -- so every tap this harness ever made
        was a hold, and `--dwell` changed nothing because nothing read it. The
        page probes that came out identical at 500 K and at 2 M were measuring
        the same 10 M twice.

        A window that executes nothing ends it: `spin` returns normally having
        run zero when a vector has no handler, and a caller that only watches
        the screen reads that as "the input did nothing".
        """
        from emu import longrun

        done = 0
        while done < instructions:
            budget = min(CLOCK_CHUNK if self.clock or self.tclock else CHUNK, instructions - done)
            self.m.pc, ran, _stop = longrun.spin(self.m.m, self.m.pc, budget,
                                                 pits=self.timers, fast=True, async_events=self.events)
            done += ran
            if self.clock:
                self._tick(self.ran + done)
            if self.tclock:
                self._tock()
            if ran == 0:
                break
        self.ran += done
        return done

    def frame_clock(self, frames_va, per_sec=1500):
        """2026-11-15: the audio frame counter (FRAMES, PER_SEC a second, the audio ISR's) moves with
        the UI's instructions at digikit's instruction clock (emu.pit.INSTR_PER_SEC), written after
        each chunk (CLOCK_CHUNK while it runs). Without the audio ISR it stood still (0 since the
        snapshot's boot), so what the firmware times by it never moved: a note's 1.5 s (slice.c)
        never ended, and the overlay's redraw tick (page.c, FRAMES_NOW - rec_next) never came
        again: a new note was never drawn"""
        self.clock = (frames_va, self.m.long(frames_va), per_sec)

    def _tick(self, ran):
        from emu.pit import INSTR_PER_SEC
        va, f0, per_sec = self.clock
        self.m.write(va, struct.pack(">I", (f0 + ran * per_sec // INSTR_PER_SEC) & 0xFFFFFFFF))

    def tick_clock(self, frames_va):
        """2026-11-18: the audio frame counter (FRAMES) follows stock's panel tick at the unit's rate (UNIT_FRAMES to
        UNIT_TICKS), written after each CLOCK_CHUNK. What the firmware times by FRAMES (a held NO's 0.6 s) then runs
        against the key repeats stock's key task sends by the tick, as on the unit. Replaces frame_clock"""
        self.clock = None
        self.tclock = [frames_va, self.m.long(frames_va), self.m.long(TICK_VA) & 0xFFF, 0]

    def _tock(self):
        t = self.m.long(TICK_VA) & 0xFFF
        c = self.tclock
        c[3] += (t - c[2]) & 0xFFF                  # (the tick wraps at 4,096: a chunk is far less than that)
        c[2] = t
        self.m.write(c[0], struct.pack(">I", (c[1] + c[3] * UNIT_FRAMES // UNIT_TICKS) & 0xFFFFFFFF))

    def ticks(self):
        """panel ticks run since tick_clock()"""
        return self.tclock[3]

    def skip_frames(self, n):
        """FRAMES moved on by N with no ticks run (a word's 1 s on screen let pass)"""
        self.tclock[1] += n
        self._tock()

    def run_ticks(self, n):
        """run until N more panel ticks have gone (tick_clock first) -> the ticks run"""
        t0 = self.ticks()
        for _ in range(4 * n + 40):                 # (a tick is ~1.1 M instructions, two CLOCK_CHUNKs)
            if self.ticks() - t0 >= n:
                break
            self.settle(CLOCK_CHUNK)
        return self.ticks() - t0

    def repeat_timing(self):
        """-> (the first repeat, then every): stock's key task's ticks, as the snapshot holds them (24, 8 on the unit)"""
        return self.m.long(REPEAT_FIRST_VA), self.m.long(REPEAT_EVERY_VA)

    def watch_items(self, entry_va):
        """the UI items a routine taking (u8 *item) is called with, each with the panel tick it came at:
        -> a list filled as the machine runs, of (tick, type, code, flags); a held key's repeats show bit 3"""
        from unicorn import UC_HOOK_CODE, m68k_const
        seen = []

        def on(uc, ad, sz, us):
            sp = uc.reg_read(m68k_const.UC_M68K_REG_A7)
            it = bytes(uc.mem_read(struct.unpack(">I", bytes(uc.mem_read(sp + 4, 4)))[0], 12))
            code, flags = struct.unpack(">II", it[4:12])
            seen.append(((self.tclock[3] if self.tclock else 0), it[0], code, flags))
        self.m.uc.hook_add(UC_HOOK_CODE, on, begin=entry_va, end=entry_va)
        return seen

    # --- input --------------------------------------------------------------
    def tap(self, key, after=SETTLE):
        channel, bit = key
        self.m.pc = self.panelin.press(self.m.m, self.profile, channel, bit)
        self.settle(TAP)
        self.m.pc = self.panelin.release(self.m.m, self.profile, channel, bit)
        return self.settle(after)

    def hold(self, key, instructions=SETTLE):
        channel, bit = key
        self.m.pc = self.panelin.press(self.m.m, self.profile, channel, bit)
        return self.settle(instructions)

    def let_go(self, key, after=SETTLE):
        channel, bit = key
        self.m.pc = self.panelin.release(self.m.m, self.profile, channel, bit)
        return self.settle(after)

    def press_for(self, key, ticks):
        """KEY pressed, then N panel ticks run with it down (stock's key task sends its repeats meanwhile, as on the
        unit; tick_clock first) -> the ticks run"""
        channel, bit = key
        self.m.pc = self.panelin.press(self.m.m, self.profile, channel, bit)
        return self.run_ticks(ticks)

    def release_for(self, key, ticks):
        """KEY let go, then N panel ticks run"""
        channel, bit = key
        self.m.pc = self.panelin.release(self.m.m, self.profile, channel, bit)
        return self.run_ticks(ticks)

    def push_and_turn(self, encoder, delta, times=2, dwell=SETTLE // 2):
        """Hold the encoder's push and turn it -- the only thing that moves a
        value in a menu."""
        push = ENCODER_PUSH[encoder]
        self.hold(push, dwell)
        for _ in range(times):
            self.m.pc = self.panelin.encoder(self.m.m, self.profile, encoder, delta)
            self.settle(dwell)
        self.let_go(push, dwell)

    # --- what the screen said ------------------------------------------------
    def frames(self):
        return len(self.capture.frames) if self.capture else 0

    def screen(self, name):
        """Archive the last untorn frame. -> its path, or a note.

        The screens are the evidence: a slot number says which parameter moved,
        a picture says which page was open. They are a 128x64 mono panel and
        carry no firmware bytes.
        """
        if not self.capture or not self.capture.frames:
            return "(no frame composed)"
        self.png_dir.mkdir(parents=True, exist_ok=True)
        path = self.png_dir / f"{name}.png"
        self.panel.write_png(bytes(self.capture.frames[-1]), str(path))
        return str(path)
