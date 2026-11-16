"""What both console commands share: opening the unit (or the simulator) and printing a command's cost."""

from __future__ import annotations

from importlib import resources

from ..project import Project
from ..sim import DirectUnit
from ..unit import MidoUnit, Unit


def add_target_args(ap) -> None:
    ap.add_argument("--port", default="Elektron Digitone II", help="MIDI port name (a part of it); default matches both USB modes: AUDIO+MIDI and OVERBRIDGE")
    ap.add_argument("--sim", action="store_true", help="the simulator, in process (no unit)")
    ap.add_argument("--fault", action="append", default=[], help="simulator fault (repeatable): no_channel, torn, ...")
    ap.add_argument("--quiet", action="store_true", help="no per-command cost lines")


def open_unit(a) -> Unit:
    if getattr(a, "sim", False) or getattr(a, "dry_run", False):
        return DirectUnit(Project.load(str(resources.files("dn2tools") / "data" / "project.json")), a.fault)
    return MidoUnit(a.port)


def cost(unit: Unit, what: str, quiet: bool = False) -> None:
    """the last command's round trip and SysEx bytes (the simulator's are 0)"""
    if quiet or not unit.last_cost[1]:
        return
    s, out, inp = unit.last_cost
    print(f"  [{what}: {s * 1000:.1f} ms, {out} B out, {inp} B in]")
