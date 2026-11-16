"""Runs scenarios against a Unit and collects Results."""

from __future__ import annotations

import time

from .ctx import Ctx, Params, Result
from .project import Project
from .scenarios import registry
from .unit import Unit


def run(unit: Unit, project: Project, params: Params, only: list[str] | None = None, log=print) -> list[Result]:
    results = []
    for name, title, fn in registry(project):
        if only and name not in only:
            continue
        res = Result(name, title or "")
        if fn is None:
            res.skipped = title
            results.append(res)
            log(f"  {name:12s} SKIP  {title}")
            continue
        ctx = Ctx(unit, project, params, res)
        try:
            fn(ctx)
        except (SystemExit, TimeoutError, ValueError, OSError) as e:       # the unit went away or refused
            res.error = f"{type(e).__name__}: {e}"
        finally:
            try:
                unit.all_notes_off()
            except Exception as e:                  # noqa: BLE001 - cleanup must not hide the result
                res.notes.append(f"all notes off failed: {e}")
        if not res.checks and not res.error:
            res.skipped = "the project has no track for it"
        results.append(res)
        failed = [c for c in res.checks if not c.ok]
        log(f"  {name:12s} {res.status:5s} {len(res.checks) - len(failed)}/{len(res.checks)} checks"
            + (f"  <- {failed[0].name}: {failed[0].detail}" if failed else "") + (f"  {res.error}" if res.error else ""))
    return results
