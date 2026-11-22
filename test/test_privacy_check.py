"""scripts/privacy_check.py: private names in commits or a tree stop a push (docs/privacy.md)."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "privacy_check.py"
sys.path.insert(0, str(SCRIPT.parent))
import privacy_check as P  # noqa: E402

ZERO = "0" * 40


@pytest.fixture
def env(tmp_path, monkeypatch):
    """a throwaway repository, this machine's pattern and hosts files replaced by test ones"""
    pats = tmp_path / "patterns.txt"
    pats.write_text("# a comment\nsecretbox\n\\bjdoe\\b\n")
    hosts = tmp_path / "hosts.toml"
    hosts.write_text('[farm]\nhost = "farmy"\nbench = "/srv/x/bench"\n')
    repo = tmp_path / "repo"
    repo.mkdir()
    e = {**os.environ, "DN2_PRIVATE_PATTERNS": str(pats), "DN2_HOSTS_FILE": str(hosts),
         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@users.noreply.github.com",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@users.noreply.github.com",
         "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    for k in ("DN2_PRIVATE_PATTERNS", "DN2_HOSTS_FILE"):
        monkeypatch.setenv(k, e[k])
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", "-b", "main"], check=True, env=e)
    return e


def commit(e: dict, name: str, text: str, msg: str = "c", **who: str) -> str:
    pathlib.Path(name).write_text(text)
    subprocess.run(["git", "add", name], check=True, env=e)
    subprocess.run(["git", "commit", "-q", "-m", msg], check=True, env={**e, **who})
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, env=e).stdout.strip()


def run(e: dict, *args: str, script: pathlib.Path = SCRIPT, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, text=True, env=e)


def pats() -> list:
    return P.compile_all(P.local_patterns())


J = "".join          # the samples are cut in two, so this file does not match the check itself
PRIVATE = [J(["ssh me", "@box.tail1234.", "ts.net"]), J(["cd /Us", "ers/alice/x"]), J(["/ho", "me/bob/runq"]),
           J(["at 100.", "101.5.7"]), J(["192.", "168.1.20"]), J(["10.", "0.4.2"]),
           J(["see ~/.claude/", "rules/x.md"]), J(["mail jo@", "gmail.com"]), "on SecretBox now", "Jdoe said",
           "farmy: up", "/srv/x/bench/runq"]


@pytest.mark.parametrize("line", PRIVATE)
def test_private_lines_match(env, line):
    assert P.scan_text(line, pats()), line


@pytest.mark.parametrize("line", ["/home/claude/dn2/ref", "/Users/Shared", "v1.10.0.2b", "OS 1.12, 100.0 %",
                                  "t@users.noreply.github.com", "noreply@anthropic.com",
                                  "autobuild@localhost.invalid", "jdoes", "the farm", "0x100.64",
                                  "x@y", "a farm host"])
def test_plain_lines_do_not(env, line):
    assert not P.scan_text(line, pats()), line


def test_range_finds_added_lines_messages_and_authors(env):
    base = commit(env, "a.txt", "clean\n")
    commit(env, "b.txt", "ran on secretbox\n")
    commit(env, "c.txt", "fine\n", msg="as jdoe asked")
    commit(env, "d.txt", "fine\n", GIT_AUTHOR_EMAIL=J(["jd@", "example.be"]))
    r = run(env, "--range", f"{base}..HEAD")
    assert r.returncode == 1
    assert "b.txt" in r.stdout and "message" in r.stdout and "author" in r.stdout
    assert "3 commit(s)" in r.stdout and "a.txt" not in r.stdout


def test_a_line_added_then_removed_still_counts(env):
    base = commit(env, "a.txt", "clean\n")
    commit(env, "a.txt", "secretbox\n")
    commit(env, "a.txt", "clean\n")
    assert run(env, "--range", f"{base}..HEAD").returncode == 1
    assert run(env, "--tree", "HEAD").returncode == 0                  # the tree itself is clean


def test_tree_names_the_file(env):
    commit(env, "x.md", "one\nbuilt on farmy\n")
    r = run(env, "--tree", "HEAD")
    assert r.returncode == 1 and "HEAD:x.md: the farm's host" in r.stdout


def test_as_pre_push_hook_checks_only_what_is_new(env, tmp_path):
    hook = tmp_path / "hooks" / "pre-push"
    hook.parent.mkdir()
    shutil.copy(SCRIPT, hook)
    old = commit(env, "a.txt", "secretbox\n")                          # already on the remote
    new = commit(env, "b.txt", "clean\n")
    ok = run(env, "origin", "url", script=hook, stdin=f"refs/heads/main {new} refs/heads/main {old}\n")
    assert ok.returncode == 0 and "1 commit(s)" in ok.stdout
    bad = commit(env, "c.txt", "jdoe\n")
    r = run(env, "origin", "url", script=hook, stdin=f"refs/heads/main {bad} refs/heads/main {old}\n")
    assert r.returncode == 1 and "c.txt" in r.stdout
    # a new branch (the remote has nothing): every commit not on a remote counts
    r = run(env, "origin", "url", script=hook, stdin=f"refs/heads/x {new} refs/heads/x {ZERO}\n")
    assert r.returncode == 1 and "a.txt" in r.stdout
    # a deletion pushes nothing
    assert run(env, "origin", "url", script=hook, stdin=f"(delete) {ZERO} refs/heads/x {old}\n").returncode == 0


def test_a_bad_pattern_stops_the_check(env, tmp_path):
    (tmp_path / "patterns.txt").write_text("(unclosed\n")
    commit(env, "a.txt", "x\n")
    r = run(env, "--tree", "HEAD")
    assert r.returncode == 2 and "could not check" in r.stderr


def test_install_puts_itself_as_the_hook(env):
    commit(env, "a.txt", "x\n")
    assert run(env, "--install").returncode == 0
    hook = pathlib.Path(".git/hooks/pre-push")
    assert hook.read_bytes() == SCRIPT.read_bytes() and os.access(hook, os.X_OK)
    hook.write_text("#!/bin/sh\necho other\n")                         # someone else's hook stays
    assert run(env, "--install").returncode == 2 and "other" in hook.read_text()


def test_the_repository_tree_is_clean():
    """the tracked tree as committed names nothing private (with this machine's own patterns, if any)"""
    top = SCRIPT.parents[1]
    inside = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=top, capture_output=True, text=True)
    if inside.returncode or pathlib.Path(inside.stdout.strip()).resolve() != top.resolve():
        pytest.skip("not a git checkout (a gate or run-queue copy of the tree): no commits to check")
    r = subprocess.run([sys.executable, str(SCRIPT), "--tree", "HEAD"], cwd=top, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]
