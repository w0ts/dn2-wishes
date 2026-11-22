"""No chunk of ours lies in RAM stock OS 1.12 writes (dnfw.mods.stockram, 2026-11-16).

The negative control is the layout that crashed the unit: the boot-screen stamp at 0x46708000
(combined build 7f7e7d6c, EXCEPTION at every power-on). It must be caught.
"""

from dataclasses import dataclass

from dnfw.mods import stockram


@dataclass(frozen=True)
class _E:
    start: int
    length: int
    what: str

    def __str__(self):
        return self.what


def test_no_chunk_of_ours_where_stock_writes():
    """Every chunk of ours, the boot-screen stamp included (moved to 0x4670e000, bb9e4b9c), is clear.
    The gate's `rammap` step checks the image itself (its area's chunks) as well."""
    bad = stockram.clashes(stockram.ours())
    assert not bad, "\n".join(bad)


def test_the_stamp_is_clear_of_the_bounce_buffer():
    """The stamp sat at 0x46708000, under stock 1.12's +Drive bounce buffer, and crashed a unit at every
    power-on (7f7e7d6c). PR1 bb9e4b9c moved it to 0x4670e000: no clash with what stock writes."""
    from dnfw.mods import bootscreen
    assert not stockram.clashes(bootscreen.ram()), stockram.clashes(bootscreen.ram())


def test_the_old_stamp_place_is_caught():
    bad = stockram.clashes([_E(0x46708000, 1692, "the stamp where 7f7e7d6c had it")])
    assert any("bounce buffer" in b for b in bad), bad


def test_the_bounce_buffer_is_where_the_read_routine_puts_it():
    assert stockram.BOUNCE == (0x466F9300, 0x46709300)


def test_the_map_was_measured():
    ranges = stockram.measured()
    assert ranges, "stock112_writes.json holds no range"
    assert all(a < b for a, b in ranges)


def test_the_boot_steps_probe_read_lands_where_no_one_is():
    sector, n, buf = stockram.PROBE_READ
    assert buf & 15 and n == 0x10000, "unaligned and a whole 64 KiB call, or stock skips its bounce buffer"
    probe = [_E(buf, n, "the boot step's probe read")]
    assert not [b for b in stockram.clashes(probe) if "bounce" not in b], stockram.clashes(probe)
    for e in stockram.ours():
        assert not (e.start < buf + n and buf < e.start + e.length), f"the probe read lands on {e}"


def test_lfo4_state_is_checked_and_clear():
    """2026-11-17: lfo4's LFO state arrays sat at 0x46700000.. under the bounce buffer, unchecked, because ours()
    held waverider's and bootscreen's RAM alone. Every shipped mod's RAM is checked now, lfo4's state included."""
    from dnfw.mods import lfo4
    have = {(e.start, e.length) for e in stockram.ours({"DN2_LFO4": "1"})}
    assert {(va, n) for va, n, _ in lfo4.STATE_RAM} <= have
    assert not stockram.clashes([_E(va, n, what) for va, n, what in lfo4.STATE_RAM])


def test_the_old_lfo4_state_place_is_caught():
    bad = stockram.clashes([_E(0x46700000, 2560, "LFO state LIVE where v0.56.2..v0.57.5 had it")])
    assert any("bounce buffer" in b for b in bad), bad


def test_every_lfo4_state_address_agrees():
    """the build's edits (build_lfo4_tick), the mod's declaration and our C's view of them (pages) are one place"""
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import build_lfo4_tick as tick
    from dnfw.mods import lfo4
    from dnfw.waverider import pages
    assert [va for va, _n, _w in lfo4.STATE_RAM] == [tick.LIVE, tick.SECOND, tick.BACKUP]
    assert all(n == tick.STATE_LEN for _va, n, _w in lfo4.STATE_RAM)
    assert pages.LFO4_LIVE == tick.LIVE and pages.LFO4_STRIDE == tick.STATE_STRIDE
