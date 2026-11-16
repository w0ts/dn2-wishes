"""dn2test's read commands: info, switches, switch NAME VALUE, counters [reset], trace, state, peek ADDR [LEN],
smoke. All read only except `switch` (a whitelisted RAM word, bounded by the firmware) and `counters reset`."""

from __future__ import annotations

import pathlib

from .. import buildid
from .. import protocol as P
from ..channel import TestChannel
from ..unit import NoTestChannel, StatusError
from .common import cost, open_unit

TYPE_NAMES = {-1: "none"}


def _hex(data: bytes, base: int) -> str:
    return "\n".join(f"{base + i:08x}  {data[i:i + 16].hex(' ')}" for i in range(0, len(data), 16))


def smoke(ch: TestChannel, quiet: bool) -> int:
    """the hardware smoke test: every read-only command once, and the numbers that must move do"""
    u = ch.unit
    ok = True

    def step(name: str, fn):
        nonlocal ok
        try:
            r = fn()
            cost(u, name, quiet)
            print(f"PASS {name}: {r}")
        except (NoTestChannel, StatusError, ValueError) as e:
            ok = False
            print(f"FAIL {name}: {e}")

    step("HELLO", lambda: f"link protocol {u.hello()}")
    step("TLM", lambda: f"build {u.tlm().build:#010x}")
    step("BUILDINFO", lambda: ch.info())
    step("SWITCH", lambda: ", ".join(f"{s.name}={s.value}" for s in ch.switches()))
    step("COUNTERS", lambda: ch.counters())
    step("STATE", lambda: ch.state())
    step("TRACE", lambda: f"{len(ch.trace()[1])} entries")
    step("SCREEN", lambda: f"{len(ch.screen())} bytes, hash {ch.screen_hash()[0]:#010x}")
    s1 = ch.state()
    u.wait(0.5)
    s2 = ch.state()
    if s2.frames == s1.frames:
        print("NOTE the audio frame counter did not move in 0.5 s (the simulator, or no audio running)")
    else:
        rate = (s2.tick - s1.tick) * 1500.0 / (s2.frames - s1.frames)
        print(f"PASS clocks: panel tick {rate:.0f}/s against the audio frames (the firmware's estimate {s2.ticks_per_s}/s)")
    print("SMOKE PASS" if ok else "SMOKE FAIL")
    return 0 if ok else 1


def identity(ch: TestChannel, a) -> int:
    """remoteui-6: the mod's version and the code's CRC; with --file, whether the unit runs that file"""
    try:
        ident = ch.identity()
    except TimeoutError as e:
        print(f"identity: {e}")
        return 1
    if ident is None:
        print("identity: none (a build before remoteui-6 does not report one)")
        return 1 if a.file else 0
    ms = ident.ticks / 132_000.0                 # DMA timer 0: 132.002 MHz on the unit (profiler, 2026-11-11)
    print(f"mod version {ident.mod_version or '?'}; code CRC-32 {ident.crc:08x} over {ident.code_lo:#010x} "
          f"+{ident.code_len:,} B (computed in {ident.ticks:,} timer ticks, ~{ms:.2f} ms, longest slice "
          f"{ident.slice_max:,})")
    if not a.file:
        return 0
    ok, line = buildid.match(ident, pathlib.Path(a.file))
    print(line)
    return 0 if ok else 1


def main(a) -> int:
    unit = open_unit(a)
    ch = TestChannel(unit)
    cmd, rest = a.command[0], a.command[1:]
    try:
        if cmd == "info":
            i = ch.info()
            cost(unit, "BUILDINFO", a.quiet)
            caps = [n for n in P.CAPS if i.has(n)]
            print(f"{i.label}: test channel protocol {i.proto}, OS {i.os}, screen {i.width}x{i.height}, "
                  f"panel tick {i.ticks_per_s}/s\ncapabilities: {', '.join(caps)}")
            return identity(ch, a)
        elif cmd == "switches":
            for s in ch.switches():
                print(f"{s.index} {s.name:8s} = {s.value:5d}   ({s.min}..{s.max}, default {s.default})")
        elif cmd == "switch":
            if len(rest) != 2:
                raise SystemExit("switch NAME VALUE")
            v = ch.set_switch(rest[0], int(rest[1], 0))
            cost(unit, "SWITCH", a.quiet)
            print(f"{rest[0].upper()} = {v}")
        elif cmd == "counters":
            c = ch.counters(reset=bool(rest and rest[0] == "reset"))
            cost(unit, "COUNTERS", a.quiet)
            for k, v in c.items():
                print(f"{k:18s} {v}")
        elif cmd == "trace":
            since = int(rest[0]) if rest else 0
            nxt, entries = ch.trace(since)
            for e in entries:
                extra = f" ({P.REFUSE_WHY.get(e.b, e.b)})" if e.kind == "REFUSED" else ""
                print(f"{e.tick:10d} {e.kind:8s} {e.a:3d} {e.b:5d}{extra}")
            print(f"next: {nxt}")
        elif cmd == "state":
            s = ch.state()
            cost(unit, "STATE", a.quiet)
            for k, v in s.__dict__.items():
                print(f"{k:14s} {v}")
        elif cmd == "peek":
            addr = int(rest[0], 0)
            n = int(rest[1], 0) if len(rest) > 1 else 64
            print(_hex(ch.peek(addr, n), addr))
        elif cmd == "smoke":
            return smoke(ch, a.quiet)
        else:
            raise SystemExit(f"unknown command {cmd!r}: info, switches, switch, counters, trace, state, peek, smoke")
    except NoTestChannel as e:
        print(f"no test channel: {e}")
        return 2
    except StatusError as e:
        print(e)
        return 1
    finally:
        unit.close()
    return 0
