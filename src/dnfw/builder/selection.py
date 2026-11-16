"""The active choice of parts, for the modules that emit code (docs/builder.md).

Read once, at import, from the environment variable DN2MK2_PARTS: the canonical text of a
configuration (`KEY=0|1` lines, `dnfw.builder.parts.canonical`). Unset: every part on, the full
build. The modules that consult it (dnfw.mnm.machines, dnfw.inserts.design, dnfw.waverider.dsp)
are imported after it is set: the CLI runs each build in its own process, the page purges dnfw
from sys.modules between builds (dnfw.builder.build.fresh).
"""

from __future__ import annotations

import os

from . import parts as _parts

ENV = "DN2MK2_PARTS"

_text = os.environ.get(ENV, "")
VALUES: dict[str, int] = _parts.parse(_text)[0] if _text.strip() else _parts.defaults()


def on(key: str) -> bool:
    """Is part KEY in this build? (an unknown key is an error, not a silent yes)"""
    if key not in _parts.BY_KEY:
        raise KeyError(f"no part {key!r} in dnfw.builder.parts")
    return bool(VALUES[key])


def full() -> bool:
    return all(VALUES.values())
