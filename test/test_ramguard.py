"""The RAM guard's own logic, without an emulator (scripts/emulib/ramguard.py, 2026-11-17).

`no_dma` rows (lfo4's LFO state arrays): any DMA or uncached-alias write into them fails, whatever it
writes and whether or not the byte was armed; the CPU writes them freely (they are state).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from emulib import ramguard  # noqa: E402

ALIAS = ramguard.ALIAS
STATE = 0x46808000


def _guard():
    g = ramguard.Guard([
        {"name": "code", "load": 0x46A40000, "code": "4e754e75", "const_end": 0x46A40004},
        {"name": "LFO state LIVE", "load": STATE, "code": "00" * 16, "const_end": STATE, "no_dma": True},
    ])
    g.started = True
    return g


def test_dma_into_lfo_state_fails_even_unarmed():
    g = _guard()
    g.host_write(STATE + 4, b"\x12\x34", dma=True)
    assert g.n_bad == 1 and g.bad[0]["chunk"] == "LFO state LIVE" and g.bad[0]["by"] == "dma"


def test_alias_write_into_lfo_state_fails():
    g = _guard()
    g._check(STATE + ALIAS + 8, b"\x01", "cpu")             # noqa: SLF001
    assert g.n_bad == 1


def test_cpu_writes_lfo_state_freely():
    g = _guard()
    g._check(STATE, b"\x7f\x00\x01", "cpu")                  # noqa: SLF001
    g._check(STATE + 15, b"\xff", "cpu")                     # noqa: SLF001
    assert g.n_bad == 0


def test_dma_outside_the_rows_is_not_ours():
    g = _guard()
    g.host_write(STATE + 0x1000, b"\xff" * 64, dma=True)
    assert g.n_bad == 0


def test_the_code_row_keeps_its_old_rule():
    g = _guard()
    g.host_write(0x46A40000, bytes.fromhex("4e754e75"), dma=False)    # the loader: armed
    g._check(0x46A40000, b"\x00", "cpu")                     # noqa: SLF001
    assert g.n_bad == 1


def test_build_rows_without_an_image_has_no_state_rows():
    rows = ramguard.build_rows()
    assert not any(r.get("no_dma") for r in rows)
