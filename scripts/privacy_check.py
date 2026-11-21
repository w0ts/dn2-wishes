#!/usr/bin/env python3
"""Refuse to publish private infrastructure or personal data (docs/privacy.md).

Checks commits (their messages, author and committer, and every line their diffs add) or a whole
tree against two lists of patterns, matched without regard to case:

- the generic ones below (home directories, tailnet names, private IP addresses, e-mail addresses
  other than no-reply ones, the personal rules folder): nothing private in them;
- this machine's own: one regular expression a line in ~/.config/dn2-wishes/private-patterns.txt
  (or the file DN2_PRIVATE_PATTERNS names; a line starting with '#' is a comment), plus the farm's ssh host and
  bench directory from the farm settings (scripts/hostcfg.py's file), so the names stay private too.

    privacy_check.py --range A..B      the commits in A..B (also: --range REV, its commits not on any remote)
    privacy_check.py --tree REV        every text file of REV's tree
    privacy_check.py --install         install this file as the repository's pre-push hook

As the pre-push hook (git runs it with the remote's name and URL, and the refs on stdin) it checks
the commits each pushed ref adds to the remote and stops the push on any match. Exit 0: clean;
1: matches (listed); 2: it could not check (a missing pattern file is not an error).
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Iterable, NamedTuple

ZERO = "0" * 40
HOSTS_FILE = pathlib.Path.home() / ".config" / "dn2-wishes" / "hosts.toml"
PATTERNS_FILE = pathlib.Path.home() / ".config" / "dn2-wishes" / "private-patterns.txt"
NEUTRAL_HOSTS = {"farm", "localhost"}

# addresses that name nobody: GitHub's and Anthropic's no-reply ones, the autobuild's, examples
EMAIL_OK = re.compile(r"(@users\.noreply\.github\.com|^noreply@anthropic\.com|@localhost\.invalid"
                      r"|@example\.(com|org|net))$", re.I)
# (a literal is written with one letter in [ ], so this file does not match itself)
GENERIC = {
    "a home directory on a Mac": r"/Users/(?!Shared\b)[A-Za-z0-9._-]+",
    "a home directory": r"/home/(?!(?:claude|someone|runner|user)\b)[A-Za-z0-9._-]+",
    "a shared home directory": r"/data/h[o]me\b",
    "a tailnet name": r"\.ts\.net\b|\btailscale\b",
    "a private IP address": r"(?<![\d.])(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])|10\.\d{1,3}|192\.168"
                            r"|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?![\d.])",
    "the personal rules folder": r"\.claude/rul[e]s\b",
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?<=[A-Za-z])")


class Hit(NamedTuple):
    where: str      # "COMMIT message", "COMMIT author", "COMMIT path", "REV:path"
    what: str       # the pattern's name
    text: str       # the line, shortened


def git(*args: str, data: bytes | None = None) -> str:
    r = subprocess.run(["git", *args], input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode("utf-8", errors="replace")


# -- the patterns --------------------------------------------------------------------------------

def local_patterns(path: pathlib.Path | None = None, hosts: pathlib.Path | None = None) -> dict[str, str]:
    """this machine's patterns: the private file's lines, and the farm settings' host and bench"""
    out: dict[str, str] = {}
    p = path or pathlib.Path(os.environ.get("DN2_PRIVATE_PATTERNS", PATTERNS_FILE)).expanduser()
    if p.is_file():
        for n, line in enumerate(p.read_text().splitlines(), 1):
            line = line.strip()
            if line and not line.startswith("#"):
                re.compile(line)                 # a bad line stops the check (exit 2), never skips it
                out[f"private pattern {n} ({p.name})"] = line
    h = hosts or pathlib.Path(os.environ.get("DN2_HOSTS_FILE", HOSTS_FILE)).expanduser()
    if h.is_file():
        farm = tomllib.loads(h.read_text()).get("farm", {})
        host = farm.get("host", "")
        if host and host.lower() not in NEUTRAL_HOSTS:
            out["the farm's host (hosts.toml)"] = r"\b" + re.escape(host) + r"\b"
        bench = farm.get("bench", "")
        if bench.startswith("/"):
            out["the farm's bench (hosts.toml)"] = re.escape(bench.rstrip("/"))
    return out


def compile_all(extra: dict[str, str]) -> list[tuple[str, re.Pattern]]:
    return [(name, re.compile(rx, re.I)) for name, rx in {**GENERIC, **extra}.items()]


def scan_text(text: str, pats: list[tuple[str, re.Pattern]]) -> list[tuple[str, str]]:
    """(pattern name, line) for every line of TEXT a pattern or a personal e-mail address matches"""
    out = []
    lines: list[str] | None = None
    for name, rx in pats:
        if rx.search(text):                              # most texts match nothing: one pass each
            lines = text.splitlines() if lines is None else lines
            out += [(name, ln.strip()[:160]) for ln in lines if rx.search(ln)]
    if "@" in text:
        for ln in (text.splitlines() if lines is None else lines):
            if "@" in ln and any(not EMAIL_OK.search(m.group(0)) for m in EMAIL.finditer(ln)):
                out.append(("an e-mail address", ln.strip()[:160]))
    return out


# -- what is checked -----------------------------------------------------------------------------

def added_lines(sha: str) -> dict[str, str]:
    """path -> the lines SHA's diff adds (a merge: what it adds beyond its parents, as git show does)"""
    out: dict[str, list[str]] = {}
    path = "?"
    for line in git("show", "--format=", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                    sha).splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("diff --cc ") or line.startswith("diff --combined "):
            path = line.split(" ", 2)[2]
        elif line.startswith("+") or line.startswith(" +") or line.startswith("++"):
            out.setdefault(path, []).append(line.lstrip(" ")[1:].lstrip("+"))
    return {p: "\n".join(v) for p, v in out.items()}


def check_commits(shas: Iterable[str], pats: list[tuple[str, re.Pattern]]) -> list[Hit]:
    hits = []
    for sha in shas:
        short = sha[:10]
        meta = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", sha).split("\n", 2)
        for who, line in (("author", meta[0]), ("committer", meta[1])):
            hits += [Hit(f"{short} {who}", n, t) for n, t in scan_text(line, pats)]
        hits += [Hit(f"{short} message", n, t) for n, t in scan_text(meta[2] if len(meta) > 2 else "", pats)]
        for path, text in added_lines(sha).items():
            hits += [Hit(f"{short} {path}", n, t) for n, t in scan_text(path + "\n" + text, pats)]
    return hits


def check_tree(rev: str, pats: list[tuple[str, re.Pattern]]) -> list[Hit]:
    hits = []
    entries = [e for e in git("ls-tree", "-r", "-z", rev).split("\0") if e]
    blobs = [(e.split("\t", 1)[1], e.split()[2]) for e in entries if e.split()[1] == "blob"]
    with subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as cat:
        for path, obj in blobs:
            cat.stdin.write(obj.encode() + b"\n")
            cat.stdin.flush()
            size = int(cat.stdout.readline().split()[2])
            data = cat.stdout.read(size + 1)[:size]
            if b"\0" in data[:8000]:
                data = b""                               # a binary file: its path only
            text = path + "\n" + data.decode(errors="replace")
            hits += [Hit(f"{rev}:{path}", n, t) for n, t in scan_text(text, pats)]
    return hits


def commits_in(spec: str, remote: str | None = None) -> list[str]:
    """A..B, or a single REV: its commits on no remote (or not on REMOTE's refs)"""
    if ".." in spec:
        return git("rev-list", spec).split()
    not_on = f"--remotes={remote}" if remote else "--remotes"
    return git("rev-list", spec, "--not", not_on).split()


def pre_push_commits(remote: str, stdin: str) -> list[str]:
    shas: list[str] = []
    for line in stdin.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:          # a deletion pushes nothing
            continue
        local, remote_sha = parts[1], parts[3]
        known = remote_sha != ZERO and subprocess.run(["git", "cat-file", "-e", remote_sha + "^{commit}"],
                                                      capture_output=True).returncode == 0
        shas += git("rev-list", f"{remote_sha}..{local}").split() if known else commits_in(local, remote)
    return list(dict.fromkeys(shas))


def merged(hits: list[Hit]) -> list[Hit]:
    """one hit a line: the names of every pattern that matched it, together"""
    out: dict[tuple[str, str], list[str]] = {}
    for h in hits:
        out.setdefault((h.where, h.text), []).append(h.what)
    return [Hit(w, ", ".join(dict.fromkeys(n)), t) for (w, t), n in out.items()]


def report(hits: list[Hit], checked: str) -> int:
    hits = merged(hits)
    if not hits:
        print(f"privacy check: clean ({checked})")
        return 0
    print(f"privacy check: {len(hits)} match(es) in {checked}:")
    for h in hits:
        print(f"  {h.where}: {h.what}: {h.text}")
    print("Nothing was pushed. Move the private part to this machine's settings, or rewrite the commits.")
    return 1


def install() -> int:
    hooks = pathlib.Path(git("rev-parse", "--git-common-dir").strip()).resolve() / "hooks"
    custom = subprocess.run(["git", "config", "--get", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
    if custom:
        hooks = pathlib.Path(custom).expanduser()
    dst = hooks / "pre-push"
    me = pathlib.Path(__file__).resolve()
    if dst.exists() and dst.read_bytes() != me.read_bytes() and b"privacy_check" not in dst.read_bytes():
        print(f"{dst} exists and is another hook: not replaced", file=sys.stderr)
        return 2
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(me, dst)
    dst.chmod(0o755)
    print(f"installed {dst} (a copy of {me.name}: run --install again after it changes)")
    return 0


def main(argv: list[str]) -> int:
    try:
        if pathlib.Path(sys.argv[0]).name == "pre-push":
            pats = compile_all(local_patterns())
            remote = argv[0] if argv else "origin"
            shas = pre_push_commits(remote, sys.stdin.read())
            return report(check_commits(shas, pats), f"{len(shas)} commit(s) to push to {remote}")
        if argv[:1] == ["--install"]:
            return install()
        if len(argv) == 2 and argv[0] in ("--range", "--tree"):
            pats = compile_all(local_patterns())
            if argv[0] == "--tree":
                return report(check_tree(argv[1], pats), f"the tree of {argv[1]}")
            shas = commits_in(argv[1])
            return report(check_commits(shas, pats), f"{len(shas)} commit(s) of {argv[1]}")
    except (RuntimeError, re.error, tomllib.TOMLDecodeError, OSError) as e:
        print(f"privacy check: could not check: {e}", file=sys.stderr)
        return 2
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
