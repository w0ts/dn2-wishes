# Rules for this repository

## Branching model (owner, 2026-11-17)

- **`main` is the truth:** upstream + every feature of ours that passed. (The pre-2026-11-17 main
  survives only as the local tag `archive/old-main-2026-11-17`; finished or abandoned branches are
  archived the same way, `archive/<branch>`, then deleted.)
- **A feature merges to `main` as soon as** its own tests/gate step AND the brick-risk steps
  (preflight … overbridge, boot, machines, engine, fuzz, on the build's own snapshot) pass on
  main + the feature. Then its branch, worktree and session are removed. No feature waits on an
  integration branch.
- **A release branch is cut from `main`**; the full `ship_gate.py` run (the release clearing)
  runs there. Fixes it finds go to `main` first, then into the release branch.
- **A new upstream release** is merged into `main` once.
- Test builds for the owner = brick-risk steps passed; releases = full gate (below).
- **Tracked files say "the User" and "the farm"**, never the owner's name, e-mail or private
  hosts/paths (`scripts/privacy_check.py`, `docs/privacy.md`; host settings live in the untracked
  `~/.config/dn2-wishes/hosts.toml`). `main` goes public as a squashed commit (owner, 2026-11-17).

## The shipping rule — no exceptions

**No build goes to the owner for flashing until `scripts/ship_gate.py` has printed
`CLEARED TO FLASH` on that exact file.** Not a smaller change, not a rebuild of
something that passed before, not a docs-only rebuild. Every build, every time.
(Owner, 2026-10-11: *"we absolutely CANNOT risk anything that will potentially harm
my unit."*)

    DT2_SECTIONS=../sec112 python scripts/ship_gate.py ../Digitone_II_OS1.12.syx BUILD.syx

It runs, in order, and stops at the first failure: preflight (bootstrap, updater,
metadata, Outbox untouched; signature; DSP size) → our RAM clear of what stock 1.12 writes
(`rammap`) → DSP identity → DSP hardware rules → ColdFire instruction-set check → the brick-risk
emulator steps (boot from reset, a power-on with our machines, engine + SAVE/LOAD, the UI fuzz;
the User, 2026-11-16: "the checks should be running the riskest first, always") → unit tests
(both cores) → the other ColdFire emulator steps, quickest first (the dead link last), with the
SHARC runner (types 0–4 bit-identical to stock) beside them; a failing SHARC part stops it at the
next step. Every emulator step runs under the RAM guard (`scripts/emulib/ramguard.py`: no one but
our loader changes a chunk we place, through 0x46..., the uncached alias 0x4e... or DMA) with the
alias mapped as the same memory; the boot makes one 64 KiB read through stock's +Drive bounce
buffer at power-on (the 7f7e7d6c crash, 2026-11-16).
**Feature steps (the User, 2026-11-16: "if a feature break, it is not reason to not flash. we
should not flash what can brick").** A step in `FEATURE_STEPS` (today `flexplay` alone) does not
stop the gate when it fails: the failure is printed and recorded in the build's `.gate.json` under
`known_issues`, and the build can still print `CLEARED TO FLASH`; every known issue is named when
the build is sent. Every other step blocks, `rammap` and the RAM guard included, and a RAM-guard
or wild-read failure inside a feature step blocks too. A step joins `FEATURE_STEPS` only with the
User's OK, and only if its failure cannot harm the unit.
`--list` prints the order. About an hour; run it in the background.

**Elektron's own DSP code (the User, 2026-11-12).** Stock code (machines, track chain, send
FX, routing, output) may be changed only when the SHARC runner's `stockout` step passes on
that build: with stock machines only, the main mix, every track's stereo blocks, the FX
returns, TDM slots 0-13 and the Overbridge records are bit-identical to the stock image's,
every block (`scripts/sharc_stockout_step.py`). A change that is not bit-identical is allowed
only where the User decided it; so far: the idle savings (send-FX idle gate, idle stock voices
skipped, the track chain skipped at a fixed point), each with the frame guard reserving the
skipped cost. Such a change declares, in `stockout`, exactly which output words may differ
and when.

**Before the first build of a release (owner, 2026-11-07, after v0.44 was gated twice with
0.43 on its screen):** bump `VERSION` to the release's number, then run
`python3 scripts/gen_waverider_code.py` (the version is compiled into the ColdFire chunk;
`VERSION` alone changes nothing on screen), then build. **Every step-by-step run starts with
the preflight steps**: `--only preflight,code-fresh,rebuild,dsp-identity,hwrules,symbols,coldfire,overbridge`
(the full run checks them first; an `--only` run does not unless named).

**Step by step first (owner, 2026-11-01).** When a change touches a step's inputs, run that
step alone until it passes: `... ship_gate.py STOCK BUILD.syx --only STEP[,STEP...]` (e.g.
`--only unit,chords`). It records its pass in the reuse cache exactly as a full run would, but
never clears a build or writes its `.gate.json`. Then run the full gate, and make no test or
script edit once it has started: it reuses the standalone passes only while nothing changed.

**Exact reuse (owner, 2026-10-25).** Every build still gets a full gate run and its own
record. The SHARC runner runs alongside the ColdFire steps. A long step's earlier pass is
reused only when nothing that step read has changed. What it read is traced: every file
its processes opened, the directories they listed, the native libraries and programs they
ran, and the gate's own inputs. Each is hashed (sha256) when the step passes. One
differing byte, or a missing file, means the step runs again (`scripts/gate_cache.py`).
The record's `reused` field says which steps were reused and from which pass. Never
widen what counts as "unchanged". (v0.28, owner 2026-10-27: the SHARC runner's verdict is
`scripts/gate_sharc.py`'s, so its record holds what the runner read and that file, not
`ship_gate.py` or the ColdFire's artefacts, which it never reads; DSP identity, never
reused, ties its pass to the build.)

**Clearing in parallel (2026-11-16, `docs/gate-speed.md`).** `scripts/gate_parallel.py` runs every
reusable step alone (`--only`, each in its own copy of the tree mounted at the tree's path),
longest first under each step's limit and memory peak (`scripts/gate_times.json`, shown by
`ship_gate.py --list`), merges their reuse records, then runs ONE full `ship_gate.py`. That
full run is the gate: it re-hashes every input before it reuses a pass, and only it can print
CLEARED TO FLASH.

- The pass is recorded in `BUILD.syx.gate.json` with the build's sha256. A file
  whose sha256 differs from its record has not been gated.
- If any gate fails, or cannot run (missing tool, emulator, objdump), the answer
  is **do not flash**. An unchecked gate is a failed gate.
- When sending a build, say which gates passed and what remains unverified on
  hardware.
- A new mod that adds a gate (its own SHARC or ColdFire harness) adds it to
  `ship_gate.py` in the same commit.

See `docs/SAFETY.md` for the risks each gate covers.

## Every cleared build is published

When a build prints `CLEARED TO FLASH`, in the same session:

1. Give it the next version number and add its entry to `FIRMWARE.md` (top of the table
   and a section: file name, sha256, gate date, source commit, what it adds, numbered
   tests, known issues).
2. Copy it and its `.gate.json` to the `builds` branch as
   `vX.Y-NAME/DN2mod_vX.Y_NAME_OS1.12.syx` (a worktree), with `FIRMWARE.md` as that
   branch's `README.md`, and push. Renaming keeps the sha256, so the gate record holds.
3. Offer it on the Wishes builder page (the User, 2026-11-19): `python scripts/web_bundle.py --wishes
   BUILD.syx X.Y OUTDIR` into the `wishes/` bundle (one build per release, newest first; it refuses a build
   whose gate record does not clear it), then `scripts/web_bundle.py --check-site wishes` and the manual
   `wishes-pages` workflow (Actions; the User starts it). The page saves only a result whose sha256 is the
   cleared build's. New or changed presets go in first: `python scripts/presets_sync.py FOLDER` (the privacy
   check, then the copy into `presets/`; `presets/README.md`), committed; the same workflow publishes their zips.
4. Firmware never goes on `main` (`.gitignore`); only the `builds` branch carries it.
   De-Pattern (github.com/De-Pattern: dn2mk2-firmware, the dn2mk2 site) is the UPSTREAM project, not
   the User (the User, 2026-11-21: "De-Pattern is not us"): never publish, commit or sign anything there.
5. Announce it: commit its Discord announcement as `releases/vX.Y.md` on `main`
   (`releases/README.md`: first line `# vX.Y · NAME`, then the post, with a **Coming next
   (not available yet)** section) and push it: a new `releases/v*.md` on `main` is the
   trigger (this session's git route cannot push tags). The workflow `discord-release.yml`
   makes the release and its tag from that file and posts it to Discord's #announcements as
   De-Pattern. Never attach firmware to a release.
   **Paused (the User, 2026-11-19: "remove the posting to discord for now"):** both jobs of
   `discord-release.yml` run only in De-Pattern/dn2mk2-firmware, so a push here makes no
   release and posts nothing (upstream's own `releases/v*.md` come in with its merges). Until
   the User turns it back on, write `releases/vX.Y.md` but expect no post.
6. **Changelogs, every build sent to the User and every upstream merge** (the User, 2026-11-22: "we
   should remember to update it"): add the build's entry to `CHANGELOG.md`, and each merged upstream
   release's section to `docs/upstream-history.md` (`autobuild.py rebase history TAG`), on our `main`
   AND on the public line (`origin/main`, w0ts/dn2-wishes: curated docs + site, diverged from ours; a
   worktree from `origin/main`, the privacy check, then `git push origin BRANCH:main`). Test builds
   (`_TEST.syx`) count: each gets its entry with its sha256, its checks and their results on the DN2.

**Test builds (owner, 2026-11-14)**, from a feature branch (e.g. `stereo`): gated exactly
like a release (`CLEARED TO FLASH` on that file). Versioned `X.Y-tN` (e.g. `0.54-t1`), named
for the feature. Published to the `builds` branch under `test/vX.Y-tN-NAME/` and to the
patcher with `web_bundle.py ... --test` (listed under TEST, never the latest, with a warning),
with a section in the branch's own `FIRMWARE.md`. Its tests and known issues go to the owner with
the build. It is announced only when the owner asks (2026-11-14, v0.54-t1): then
`releases/vX.Y-tN.md` on `main`, titled `# vX.Y-tN · NAME (TEST build)`, saying it is a test build;
the workflow makes it a pre-release, never the latest.
