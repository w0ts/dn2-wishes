"""Kept for a release: the driver moved into the dn2tools package (tools/dn2tools; `pip install ./tools/dn2tools`,
then `dn2test`). This runs it from the checkout without installing it."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "dn2tools" / "src"))

from dn2tools.cli.dn2test import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
