# dn2tools

Test a Digitone II running a dn2-wishes **test build**, over USB: telemetry, runtime switches, the screen
(mirror, PNG snapshots), the keys and encoders (armed, with a destructive-key blacklist), audio checks.

    python3 -m venv .venv && .venv/bin/pip install "./tools/dn2tools[audio]"
    .venv/bin/dn2test smoke          # read only
    .venv/bin/dn2ui snap             # the screen as a PNG
    .venv/bin/dn2ui --sim mirror     # no unit: the simulator
    .venv/bin/dn2test profile --seconds 30 --label idle --out prof/   # the ColdFire's CPU profile (remoteui-5)

The manual is `docs/remote-ui.md` (quickstart, commands, safety, troubleshooting); the wire format is
`docs/remote-ui-protocol.md`; the measurement scenarios are `docs/device-tests.md`.

Tests (no hardware): `.venv/bin/pip install "./tools/dn2tools[dev]" && .venv/bin/pytest tools/dn2tools`.

Licence: AGPL-3.0-or-later. No Elektron code or bytes.
