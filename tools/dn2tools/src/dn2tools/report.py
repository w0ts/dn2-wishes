"""The run's report: results.json (everything, with the readings) and report.md (what to read)."""

from __future__ import annotations

import json
import pathlib
import time

from .ctx import Result


def to_dict(results: list[Result], meta: dict) -> dict:
    return {"meta": meta,
            "summary": {"pass": sum(r.status == "PASS" for r in results), "fail": sum(r.status == "FAIL" for r in results),
                        "error": sum(r.status == "ERROR" for r in results), "skip": sum(r.status == "SKIP" for r in results)},
            "scenarios": [{"name": r.name, "title": r.title, "status": r.status, "skipped": r.skipped, "error": r.error,
                           "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in r.checks],
                           "numbers": r.numbers, "notes": r.notes, "series": r.series} for r in results]}


def markdown(results: list[Result], meta: dict) -> str:
    out = [f"# Device test report: {meta.get('project', '')}", "",
           f"- when: {meta.get('when')}", f"- target: {meta.get('target')}", f"- build id: {meta.get('build', '?')}", ""]
    out += ["| scenario | result | checks failed |", "|---|---|---|"]
    for r in results:
        failed = [c.name for c in r.checks if not c.ok]
        out.append(f"| {r.name} | **{r.status}** | {len(failed)} of {len(r.checks)} |")
    for r in results:
        out += ["", f"## {r.name}: {r.status}", "", r.title or ""]
        if r.skipped:
            out.append(f"\nskipped: {r.skipped}")
        if r.error:
            out.append(f"\nERROR: {r.error}")
        if r.checks:
            out += ["", "| check | result | detail |", "|---|---|---|"]
            out += [f"| {c.name} | {'ok' if c.ok else '**FAIL**'} | {c.detail} |" for c in r.checks]
        if r.numbers:
            out += ["", "| reading | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in r.numbers.items()]
        out += [f"\nnote: {n}" for n in r.notes]
    return "\n".join(out) + "\n"


def write(out_dir: str | pathlib.Path, results: list[Result], meta: dict) -> tuple[pathlib.Path, pathlib.Path]:
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    j, m = d / f"results-{stamp}.json", d / f"report-{stamp}.md"
    j.write_text(json.dumps(to_dict(results, meta), indent=1, default=str))
    m.write_text(markdown(results, meta))
    return j, m
