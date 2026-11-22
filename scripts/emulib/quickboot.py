"""dspboot.run without its per-instruction Python hook (v0.43: the gate's boot steps faster).

digikit's `emu.dspboot.run(fast=True)` adds one GLOBAL code hook, `cover`, that runs a Python
call on every instruction to count instructions and collect the addresses seen (`st['n']`,
`st['seen']`, `st['stall_pcs']`, `st['curve']`). The boot steps' verdicts never read those:
they come from per-address hooks (the frame, the fault reporter, the build's routines, the
start-up animation's stamp and show), and the run's length is `emu_start(count=limit)`, which
Unicorn counts natively. So the hook costs the gate time and checks nothing.

This runs the same boot with that one hook left out. Nothing else changes: the same machine,
MMIO models, scheduler tick (driven by the idle-spin addresses, not by instruction count),
flash HLE and count. Measured on this firmware (docs/emu-speed.md): the machine's whole memory
and its registers are byte-identical with and without it at 30M and at 700M instructions, and
the boot runs 1.7x faster.

What is lost: `st['n']` is not counted along the way. It is set to the limit when the run ends
on it; a run stopped early (the fault reporter) leaves it 0, so `counted` is False and callers
print no instruction number for the stop.
"""
from __future__ import annotations

import os

import unicorn

from emu import dspboot


DDR, DDR_BYTES = 0x40000000, 0x08000000          # the ColdFire's DDR, 128 MiB
_KEEP: list = []
UNCACHED = 0x48000000                            # its uncached alias (MCF5441x ACRs): 0x4e6f9300 is 0x466f9300


def _alias_ddr():
    """2026-11-16: map 0x48000000..0x4fffffff onto the same host memory as 0x40000000..0x47ffffff, as on
    the instrument. Without it the emulator kept two separate memories, and stock 1.12's +Drive bounce
    buffer (0x4e6f9300, eDMA) never reached what lies under 0x466f9300 (the 7f7e7d6c crash: the
    stamp at 0x46708000 overwritten at power-on). -> (restore, keepalive)."""
    import ctypes
    import mmap

    mem = mmap.mmap(-1, DDR_BYTES)               # anonymous: zeros, committed only where used
    _KEEP.append(mem)                            # never freed before Unicorn: it is the machine's RAM
    base = ctypes.addressof(ctypes.c_char.from_buffer(mem))
    orig = unicorn.Uc.mem_map

    done = set()

    def mem_map(self, address, size, perms=unicorn.UC_PROT_ALL):
        if getattr(self, "_arch", None) != unicorn.UC_ARCH_M68K or not DDR <= address < DDR + 2 * DDR_BYTES:
            return orig(self, address, size, perms)
        if address + size > DDR + 2 * DDR_BYTES:
            raise ValueError(f"a mapping {address:#x}+{size:#x} runs past the DDR's alias")
        if id(self) not in done:                 # the whole DDR, both views, once: every page exists
            self.mem_map_ptr(DDR, DDR_BYTES, unicorn.UC_PROT_ALL, base)   # (the eSDHC's eDMA maps only
            self.mem_map_ptr(UNCACHED, DDR_BYTES, unicorn.UC_PROT_ALL, base)   # its first page itself)
            done.add(id(self))
        return None                              # already mapped: the same host memory

    unicorn.Uc.mem_map = mem_map

    def restore():
        unicorn.Uc.mem_map = orig
    return restore, mem


def run(syx_path, main_img, limit, **kw):
    """-> (m, st, stop), as dspboot.run, without the `cover` hook. st['counted'] says whether
    st['n'] is the run's real length."""
    orig = unicorn.Uc.hook_add
    left_out = []

    def hook_add(self, htype, callback, user_data=None, begin=1, end=0, *a, **k):
        if (htype == unicorn.UC_HOOK_CODE and begin == 1 and end == 0
                and getattr(callback, "__name__", "") == "cover"
                and getattr(callback, "__module__", "") == dspboot.__name__):
            left_out.append(callback)
            return 0
        return orig(self, htype, callback, user_data, begin, end, *a, **k)

    unicorn.Uc.hook_add = hook_add
    alias = _alias_ddr() if os.environ.get("DNFW_DDR_ALIAS") == "1" else None
    if os.environ.get("DNFW_CARD_IMAGE") and "card_image" not in kw:   # a +Drive image (scripts/drive_card.py)
        kw["card_image"] = os.environ["DNFW_CARD_IMAGE"]
    try:
        m, st, stop = dspboot.run(syx_path, main_img, limit=limit, fast=True, **kw)
    finally:
        unicorn.Uc.hook_add = orig
        if alias is not None:
            alias[0]()
            m_keep = alias[1]                     # the host memory lives as long as the machine
    if alias is not None:
        m.ddr_alias = m_keep
    if not left_out:
        # digikit changed: the hook ran as before, so the run is the old (slower) one, still correct
        print("  (quickboot: dspboot's cover hook not found; ran with it)")
        st["counted"] = True
        return m, st, stop
    st["counted"] = stop == "instruction limit"
    if st["counted"]:
        st["n"] = limit
    return m, st, stop
