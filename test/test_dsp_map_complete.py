"""The DSP map is complete (2026-11-20, the ghost audit, docs/memory-map.md "The DSP's write windows").

1. Every literal address in the built SHARC objects' assembly (L1, L2, DDR; negative immediates as their words)
   lies in an area of dsp.regions() or a known stock area, or is in NOT_ADDRESSES (constants read in context).
2. regions() holds every area the build's code constants name: PARA_DM, PIRS_TAB_L2, PI_CURVE_L2, the P-I lines in
   L1 block 2 (MD_DELAY_L1), the FDN8 diffusers (a sub-area of the Monomachine scratch).
3. The pool's inner areas (command block, recordings, table area, READY / LV_WANT, slice tables, the RAM check's
   two areas) are sub-areas of the pool, so dsp.check_regions() refuses an overlap among them.

Before 2026-11-20, (2) and (3) failed: dsp.check_regions() could not see those areas. No overlap was hiding there."""
from __future__ import annotations

import pathlib
import re

import pytest

from dnfw.waverider import dsp

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASM = ROOT / "csrc/waverider/sharc"
RANGES = ((0x240000, 0x3A0000), (0x20000000, 0x20100000), (0x80000000, 0xA0000000))
STOCK = ((0x240000, 0x270000), (0x2C0000, dsp.STOCK_BLOCK1_END), (0x20000000, dsp.L2_IMAGE_END),
         (0x80000018, 0x80530BE8))
# read in context, 2026-11-20 (asm-v0626.txt): not addresses
NOT_ADDRESSES = {0x80000000, 0x80008000, 0x2EB800, 0x305700, 0x333333, 0x336468, 0x27801F, 0x399999, 0x37E6D3,
                 0x9E3779B9, 0x83C6B450, 0x2E6280}


def literals():
    names = [n for n in dsp.objects() if not n.endswith("_jump") and n != "lookup_ptr"]
    for name in names:
        for ln, line in enumerate((ASM / f"{name}.asm").read_text().splitlines(), 1):
            code = line.split("//")[0]
            if "JUMP" in code or "CALL" in code:
                continue
            for m in re.finditer(r"(-?)0x([0-9a-fA-F]+)", code):
                a = int(m.group(2), 16)
                a = (-a) & 0xFFFFFFFF if m.group(1) else a
                if any(lo <= a < hi for lo, hi in RANGES) and a not in NOT_ADDRESSES:
                    yield name, ln, a


def test_every_literal_address_is_mapped():
    areas = [(lo, hi) for _w, lo, hi, _c in dsp.regions()] + list(STOCK)
    bad = sorted({(n, ln, a) for n, ln, a in literals() if not any(lo <= a < hi for lo, hi in areas)})
    assert not bad, "\n".join(f"{n}.asm:{ln} {a:#x} in no area of dsp.regions()" for n, ln, a in bad[:40])


@pytest.mark.parametrize("name", ["PARA_DM", "PIRS_TAB_L2", "PI_CURVE_L2", "MD_DELAY_L1"])
def test_constant_areas_in_regions(name):
    at = getattr(dsp, name)
    assert any(lo <= at < hi for _w, lo, hi, _c in dsp.regions() if "pool" not in _w), f"{name} {at:#x}"


def test_pool_inner_areas_in_regions():
    from dnfw.sampler import machines as SM
    pool = dsp.SMP_POOL_DDR
    want = [pool + SM.CMD_OFFSET, pool + SM.REC_OFFSET, pool + SM.TABLE_AREA, pool + SM.TABLE_READY,
            pool + SM.LV_WANT_OFF, pool + SM.SLICE_AREA, pool + SM.PROBE_LO, pool + SM.PROBE_HI]
    subs = [(lo, hi) for _w, lo, hi, c in dsp.regions() if c == "the sample pool"]
    missing = [hex(a) for a in want if not any(lo <= a < hi for lo, hi in subs)]
    assert not missing, missing
