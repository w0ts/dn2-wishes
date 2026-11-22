"""scripts/hostcfg.py: this machine's farm settings, read from an untracked TOML file with neutral defaults."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import hostcfg  # noqa: E402


def test_no_file_gives_the_neutral_defaults(tmp_path):
    hostcfg.load(tmp_path / "missing.toml")["farm"]["paths"]["X"] = "changed"     # a caller may change its copy
    farm = hostcfg.load(tmp_path / "missing.toml")["farm"]
    assert farm["host"] == "farm" and farm["bench"] == "~/bench"
    assert farm["window"] is None and farm["paths"] == {}


def test_the_file_overrides_key_by_key(tmp_path):
    p = tmp_path / "h.toml"
    p.write_text('[farm]\nhost = "x"\n[farm.paths]\nSTOCK112 = "/a/b.syx"\n'
                 '[farm.window]\ndays = [5]\nstart = 1\nend = 2\ncpus = 3\n')
    farm = hostcfg.load(p)["farm"]
    assert farm["host"] == "x" and farm["bench"] == "~/bench"      # bench kept from the defaults
    assert farm["paths"] == {"STOCK112": "/a/b.syx"}
    assert farm["window"] == {"days": (5,), "start": 1, "end": 2, "cpus": 3.0}
    assert hostcfg.DEFAULTS["farm"]["host"] == "farm" and "window" not in hostcfg.DEFAULTS["farm"]


def test_the_env_names_the_file(tmp_path, monkeypatch):
    p = tmp_path / "h.toml"
    p.write_text('[farm]\nhost = "y"\n')
    monkeypatch.setenv("DN2_HOSTS_FILE", str(p))
    assert hostcfg.load()["farm"]["host"] == "y"


@pytest.mark.parametrize("body", ['[farm]\ncpus = 0\n', '[farm]\nhost = ""\n', 'not toml [',
                                  '[farm.window]\ndays = [7]\nstart = 1\nend = 2\ncpus = 1\n',
                                  '[farm.window]\ndays = [1]\nstart = 9\nend = 8\ncpus = 1\n'])
def test_a_bad_file_is_refused(tmp_path, body):
    p = tmp_path / "h.toml"
    p.write_text(body)
    with pytest.raises(hostcfg.ConfigError):
        hostcfg.load(p)
