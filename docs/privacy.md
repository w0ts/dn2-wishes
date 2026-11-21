# Privacy: nothing private in what is pushed

This repository and its fork are public. Host names, home directories, private networks, the
schedules of the machines it runs on and people's names or e-mail addresses stay out of every
tracked file, commit message and commit author.

## Where the private settings live

- **The farm** (`scripts/runq.py`, `scripts/runq_hosts.py`): its ssh host, bench directory, the
  `{STOCK111}`/`{STOCK112}`/`{DIGIKIT}` paths and the CPU caps are this machine's settings, in
  `~/.config/dn2-wishes/hosts.toml` (or the file `DN2_HOSTS_FILE` names), read by
  `scripts/hostcfg.py`. `docs/hosts.example.toml` shows every key; without the file, neutral
  defaults apply. Docs and comments say "the farm" and `$BENCH`.
- **People**: docs and comments name the owner "the User" (as `CLAUDE.md` does).

## The check

`scripts/privacy_check.py` looks for private names in commits (messages, author, committer and
every line their diffs add, even a line a later commit removes: the history is public too) or in
a whole tree. Two lists, matched without regard to case:

- generic ones, in the script: home directories (`/Users/…`, `/home/…` of a named user), tailnet names,
  private IP addresses (100.64/10, 10/8, 172.16/12, 192.168/16), e-mail addresses other than
  no-reply ones, the personal rules folder;
- this machine's own, never tracked: one regular expression a line in
  `~/.config/dn2-wishes/private-patterns.txt` (or `DN2_PRIVATE_PATTERNS`), plus the farm's host and
  bench directory from `hosts.toml`.

```
python3 scripts/privacy_check.py --tree HEAD          # the tree as committed
python3 scripts/privacy_check.py --range origin/main..main
python3 scripts/privacy_check.py --install            # the pre-push hook of this clone
```

Installed, it runs on every `git push` and stops the push when a commit the remote does not have
yet matches (exit 1, every match listed). It is a copy: run `--install` again after the script
changes. `test/test_privacy_check.py` covers it and checks that the committed tree is clean.
