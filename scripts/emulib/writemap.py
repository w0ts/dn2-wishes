"""The write map: which RAM blocks a ColdFire run writes, and who wrote them (2026-11-16).

With DNFW_WRITEMAP=FILE (the gate's sitecustomize installs it, as the RAM guard), every m68k Unicorn
in the process records the 256-byte blocks of [LO, HI) written, through 0x46... and through the
uncached alias 0x4e..., by the CPU (with the first PC of each block) and by the emulator's own
peripherals (eDMA, eSDHC: `uc.mem_write` from digikit's emu.* modules once the run started). At exit
one JSON line is appended to FILE: {"argv", "blocks": {"0x46708000": [cpu, dma, alias, "first pc"]}}.

scripts/stock_ram_map.py runs stock 1.12 under it (boot from reset, a stock UI walk) and keeps the
union: the RAM stock writes. dnfw's test_ram_112 (and the gate's `rammap` step) hold every chunk of
ours out of it.
"""

from __future__ import annotations

import atexit
import json
import os
import sys

LO, HI = 0x46600000, 0x48000000           # stock's upper buffers to the end of the DDR
ALIAS = 0x08000000
BLOCK = 0x100


def install_process(path: str) -> None:
    import unicorn                                       # noqa: PLC0415
    from unicorn import UC_HOOK_MEM_WRITE                # noqa: PLC0415
    from unicorn import m68k_const as K                  # noqa: PLC0415

    blocks: dict[int, list] = {}
    state = {"started": set()}

    def note(addr: int, size: int, kind: int, pc=None):
        alias = addr >= HI
        a = addr - ALIAS if alias else addr
        for b in range(a & ~(BLOCK - 1), a + size, BLOCK):
            if not LO <= b < HI:
                continue
            r = blocks.get(b)
            if r is None:
                r = blocks[b] = [0, 0, 0, None]
            r[kind] += 1
            if alias:
                r[2] += 1
            if r[3] is None and pc is not None:
                r[3] = f"{pc:#010x}"

    orig_start, orig_write = unicorn.Uc.emu_start, unicorn.Uc.mem_write

    def emu_start(self, *a, **k):
        if getattr(self, "_arch", None) == unicorn.UC_ARCH_M68K and id(self) not in state["started"]:
            state["started"].add(id(self))

            def wrote(uc, access, address, size, value, user):
                note(address, size, 0, uc.reg_read(K.UC_M68K_REG_PC))
            self.hook_add(UC_HOOK_MEM_WRITE, wrote, begin=LO, end=HI - 1)
            self.hook_add(UC_HOOK_MEM_WRITE, wrote, begin=LO + ALIAS, end=HI + ALIAS - 1)
        return orig_start(self, *a, **k)

    def mem_write(self, address, data, *a, **k):
        if id(self) in state["started"]:
            f = sys._getframe(1)                         # noqa: SLF001
            if f.f_globals.get("__name__", "").startswith("emu."):
                end = address + len(data)
                if (address < HI and end > LO) or (address < HI + ALIAS and end > LO + ALIAS):
                    note(address, len(data), 1)
        return orig_write(self, address, data, *a, **k)

    unicorn.Uc.emu_start = emu_start
    unicorn.Uc.mem_write = mem_write

    def at_exit():
        with open(path, "a") as f:
            f.write(json.dumps({"argv": sys.argv[:4], "pid": os.getpid(),
                                "blocks": {f"{b:#010x}": r for b, r in sorted(blocks.items())}}) + "\n")
    atexit.register(at_exit)
