"""This machine's own settings for the farm tooling (scripts/runq_hosts.py, docs/runq.md): the farm's
ssh host, its bench directory, its paths and the CPU limits. They are kept out of the repository, in
a TOML file: $DN2_HOSTS_FILE, else ~/.config/dn2-wishes/hosts.toml (an example:
docs/hosts.example.toml). Without the file the neutral defaults below apply."""

from __future__ import annotations

import copy
import os
import pathlib
import tomllib

DEFAULT_FILE = pathlib.Path.home() / ".config" / "dn2-wishes" / "hosts.toml"

# neutral defaults: an ssh alias named "farm", the bench in its home, one small CPU cap at all times
DEFAULTS = {
    "farm": {
        "host": "farm",              # the ssh host (an alias in ~/.ssh/config)
        "bench": "~/bench",   # the bench directory on the farm (bench_ns112.sh, runq/)
        "load_max": 12.0,            # a job starts only while the farm's load1 + its CPUs stay under this
        "cpus": 8.0,                 # our CPUs on the farm at most, all our processes counted
        "paths": {},                 # {NAME} placeholders in a farm command -> the farm's paths
    },
}


class ConfigError(ValueError):
    """the hosts file is there but cannot be used"""


def config_path() -> pathlib.Path:
    env = os.environ.get("DN2_HOSTS_FILE")
    return pathlib.Path(env).expanduser() if env else DEFAULT_FILE


def _merge(base: dict, over: dict) -> dict:
    """a new dict: BASE with OVER's keys on top (tables merged key by key)"""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def _check_window(w: dict) -> dict:
    """an optional [farm.window]: a different CPU cap on some weekdays between two hours"""
    days, start, end, cpus = w.get("days", []), w.get("start"), w.get("end"), w.get("cpus")
    if not (isinstance(days, list) and all(isinstance(d, int) and 0 <= d <= 6 for d in days)):
        raise ConfigError("farm.window.days: a list of weekdays 0 (Monday) .. 6")
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 24):
        raise ConfigError("farm.window.start/end: hours 0..24, start before end")
    if not isinstance(cpus, (int, float)) or cpus <= 0:
        raise ConfigError("farm.window.cpus: a positive number")
    return {"days": tuple(days), "start": start, "end": end, "cpus": float(cpus)}


def load(path: pathlib.Path | None = None) -> dict:
    """the settings: the file's on top of the defaults (no file: the defaults)"""
    p = path or config_path()
    raw: dict = {}
    if p.is_file():
        try:
            raw = tomllib.loads(p.read_text())
        except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
            raise ConfigError(f"{p}: {e}") from e
    cfg = _merge(copy.deepcopy(DEFAULTS), raw)          # never shares a table with DEFAULTS
    farm = cfg["farm"]
    for k in ("host", "bench"):
        if not isinstance(farm[k], str) or not farm[k]:
            raise ConfigError(f"{p}: farm.{k}: a non-empty string")
    for k in ("load_max", "cpus"):
        if not isinstance(farm[k], (int, float)) or farm[k] <= 0:
            raise ConfigError(f"{p}: farm.{k}: a positive number")
    if not isinstance(farm["paths"], dict) or not all(isinstance(v, str) for v in farm["paths"].values()):
        raise ConfigError(f"{p}: farm.paths: names -> path strings")
    farm["window"] = _check_window(farm["window"]) if "window" in farm else None
    return cfg
