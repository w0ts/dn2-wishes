"""PC -> function, for the CPU profiler (profile.py): stock OS 1.12's functions and the mod's own.

Stock (no Elektron bytes here: addresses only, read from the image the user supplies):
  - function starts parsed from an objdump of the 1.12 MAIN OS (`objdump -D -b binary -m m68k:cfv4e
    --adjust-vma=0x40000400`): every call target (jsr / bsr, absolute or pc-relative), every pc-relative
    lea / pea of code (callbacks), every instruction that opens a frame (link, lea -N(sp),sp) right after
    a return or a branch, and every handler the code installs in the vector table (VBR 0x40000000);
  - the names this repository measured on 1.12 (STOCK_NAMES, each with where it was measured); the rest
    are `fn_<address>`, a vector's handler `isr_vec<N>`.
Ours: `src/dnfw/mods/waverider_code.json` of the build that made the image: `c_text_symbols` (every function
of the C chunk, written by scripts/gen_waverider_code.py since 2026-11-11), the `layout` names inside the
chunks, and the chunks' extents (a PC in a chunk with no name: `<chunk>+offset`).
"""

from __future__ import annotations

import bisect
import json
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field

STOCK_BASE = 0x40000400
STOCK_END = 0x4030C980                   # the end of the loaded 1.12 MAIN OS (its code ends well before)
VBR = 0x40000000
IDLE_PC = 0x400CF246                     # the idle task's spin, bra.s * (csrc/meter/hooks.S IDLE_PC)
IDLE_TCB = 0x4243D900                    # the idle task, prio 1 (csrc/meter/hooks.S IDLE_TCB)
AUDIO_ISR = 0x40025E36                   # vector 191, 1,500 Hz (csrc/sampler/hooks.S)
ABOVE_BSS = (0x466B74D0, 0x48000000)     # the mods' RAM (docs/memory-map.md)

# names measured on OS 1.12 in this repository (address -> (name, where))
STOCK_NAMES = {
    0x40000410: ("rtos_switch", "context switch, trap #0 / vector 205 (docs/coldfire-tasks.md, 1.12 disasm)"),
    0x40001252: ("default_exception", "the handler 0x40001992 puts in all 256 vectors"),
    0x400012C8: ("task_create", "TASK_CREATE(tcb, entry, prio, stack, size): the idle task's call at 0x400ced30"),
    0x400CED18: ("prio0_task", "TASK_CREATE(0x424398ac, here, prio 0) at 0x400cf26c; creates the idle task, spins"),
    0x400CED46: ("prio0_spin", "its bra.s * (1.11: prio 0 never runs, docs/coldfire-tasks.md)"),
    0x400CEDFC: ("idle_task", "TASK_CREATE(0x4243d900, here, prio 1) at 0x400ced30: the boot's setup, then the spin"),
    0x400CF246: ("idle_spin", "the idle task's bra.s * (csrc/meter/hooks.S IDLE_PC)"),
    0x400CF248: ("idle_task_tail", "after the spin (two calls, then the spin), 1.12 disasm"),
    0x40001608: ("mutex_lock", "csrc/meter/meter.c LOCK"),
    0x4000172A: ("mutex_unlock", "csrc/meter/meter.c UNLOCK"),
    0x40001896: ("os_queue_post", "csrc/devtest/devtest.c"),
    0x40025E36: ("audio_isr", "vector 191, the SSI audio interrupt (csrc/sampler/hooks.S)"),
    0x40037B74: ("param_setter", "csrc/sampler/hooks.S smp_quant_hook"),
    0x4003EB62: ("project_slot_set", "csrc/sampler/hooks.S pools hooks"),
    0x400428C0: ("project_new", "csrc/sampler/hooks.S smp_pj_new_hook"),
    0x40042E6E: ("project_load", "csrc/sampler/hooks.S smp_pj_begin_hook"),
    0x40113E70: ("set_pixel", "csrc/meter/meter.c SET_PIXEL"),
    0x4011D5DE: ("set_dirty", "csrc/meter/meter.c SET_DIRTY"),
    0x4011F8BC: ("panel_timer_cb", "csrc/devtest/devtest.c"),
    0x4011FC8C: ("panel_buttons", "csrc/devtest/devtest.c PANEL_BUTTONS"),
    0x4011FF0C: ("panel_encoder", "csrc/devtest/devtest.c PANEL_ENCODER"),
    0x4011FFBC: ("panel_rx_byte", "csrc/devtest/devtest.c"),
    0x4012194E: ("sysex_router", "csrc/sampler/hooks.S smp_rx_hook"),
    0x401236D2: ("sysex_send", "csrc/sampler/link.c SYSEX_SEND"),
    0x40131FD2: ("panel_diff", "docs/remote-ui.md (OS 1.12)"),
}

_LINE = re.compile(r"^\s*([0-9a-f]{8}):\t[0-9a-f ]+\t(\S+)\s*(.*)$")
_HEX = re.compile(r"0x([0-9a-f]{8})")
TERMINATORS = ("rts", "rte", "jmp", "bras", "braw", "bral", "bra", "halt")


def _code(a: int, end: int) -> bool:
    return STOCK_BASE <= a < end and not a & 1


def parse_objdump(text: str) -> dict[int, str]:
    """an objdump of the stock MAIN OS (adjusted to 0x40000400) -> {function start: name}"""
    rows = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            rows.append((int(m.group(1), 16), m.group(2), m.group(3)))
    starts: dict[int, str] = {}
    calls = set()
    for _a, mn, ops in rows:
        if mn in ("jsr", "bsrw", "bsrs", "bsrl", "bsr") and (h := _HEX.search(ops)):
            calls.add(int(h.group(1), 16))
    end = (max(calls) + 0x10000) if calls else STOCK_BASE
    insns = {a for a, _m, _o in rows}
    for t in calls:
        if _code(t, end) and t in insns:
            starts[t] = f"fn_{t:08x}"
    regs: dict[str, int] = {}
    prev = ""
    for a, mn, ops in rows:
        if mn in ("lea", "pea") and "%pc@(" in ops and (h := _HEX.search(ops)):
            t = int(h.group(1), 16)
            if _code(t, end) and t in insns:
                starts.setdefault(t, f"fn_{t:08x}")
        if prev in TERMINATORS and (mn == "linkw" or (mn == "lea" and re.match(r"%sp@\(-\d+\),%sp", ops))):
            starts.setdefault(a, f"fn_{a:08x}")
        # the vector table: movel #V,%dN / lea V,%aN, then movel %Rn,0x400000xx..0x400003fc
        m = re.match(r"#(-?\d+),%([da]\d)$", ops) if mn == "movel" else None
        if m:
            regs[m.group(2)] = int(m.group(1)) & 0xFFFFFFFF
        elif mn == "lea" and (m := re.match(r"(?:%pc@\()?0x([0-9a-f]{8})\)?,%(a\d)$", ops)):
            regs[m.group(2)] = int(m.group(1), 16)
        m = re.match(r"%([da]\d),0x(400003[0-9a-f]{2}|400002[0-9a-f]{2}|400001[0-9a-f]{2}|400000[0-9a-f]{2})$", ops) \
            if mn == "movel" else None
        if m and m.group(1) in regs:
            v, vec = regs[m.group(1)], (int(m.group(2), 16) - VBR) // 4
            if _code(v, end) and v in insns and v != 0x40001252:
                starts[v] = f"isr_vec{vec}"
        if mn != "nop":
            prev = mn
    for a, (name, _why) in STOCK_NAMES.items():
        starts[a] = name
    return starts


def objdump_stock(binary: str) -> str:
    """run objdump on the user's 1.12 MAIN OS section (section_3_MAIN_OS.bin)"""
    tool = next((t for t in ("m68k-linux-gnu-objdump", "m68k-elf-objdump") if shutil.which(t)), None)
    if tool is None:
        raise SystemExit("no m68k objdump on the PATH: give --stock-dis FILE (an objdump -D of the MAIN OS, "
                         "--adjust-vma=0x40000400) or --stock-symbols FILE instead")
    r = subprocess.run([tool, "-D", "-b", "binary", "-m", "m68k:cfv4e", "--adjust-vma=0x40000400", binary],
                       capture_output=True, text=True, check=True)
    return r.stdout


@dataclass
class Symbols:
    """sorted function starts with names and where they come from; regions for the PCs between them"""
    starts: list[int] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    origin: list[str] = field(default_factory=list)          # "stock" or "ours"
    regions: list[tuple[int, int, str]] = field(default_factory=list)   # (lo, hi, name) code extents

    @classmethod
    def build(cls, stock: dict[int, str] | None = None, ours: dict[int, str] | None = None,
              regions: list[tuple[int, int, str]] | None = None) -> "Symbols":
        merged = {a: (n, "stock") for a, n in (stock or {}).items()}
        merged.update({a: (n, "ours") for a, n in (ours or {}).items()})
        s = cls(regions=sorted(regions or []))
        for a in sorted(merged):
            s.starts.append(a)
            s.names.append(merged[a][0])
            s.origin.append(merged[a][1])
        return s

    def region(self, pc: int) -> tuple[int, int, str] | None:
        for lo, hi, name in self.regions:
            if lo <= pc < hi:
                return lo, hi, name
        return None

    def lookup(self, pc: int) -> tuple[str, str]:
        """-> (function name, origin: stock / ours / unknown)"""
        reg = self.region(pc)
        k = bisect.bisect_right(self.starts, pc) - 1
        if reg is not None:
            if k >= 0 and self.starts[k] >= reg[0]:
                return self.names[k], self.origin[k]
            return f"{reg[2]}+{pc - reg[0]:#x}", "ours"
        if STOCK_BASE <= pc < STOCK_END:
            if k >= 0 and self.origin[k] == "stock":
                return self.names[k], "stock"
            return f"stock@{pc & ~0xFF:08x}", "stock"
        if ABOVE_BSS[0] <= pc < ABOVE_BSS[1]:
            return f"ram_above_bss@{pc & ~0xFFF:08x}", "ours"
        return f"?{pc:08x}", "unknown"

    def to_json(self) -> dict:
        return {"starts": [[a, n, o] for a, n, o in zip(self.starts, self.names, self.origin)],
                "regions": [list(r) for r in self.regions]}

    @classmethod
    def from_json(cls, d: dict) -> "Symbols":
        s = cls(regions=[tuple(r) for r in d.get("regions", [])])
        for a, n, o in d["starts"]:
            s.starts.append(a)
            s.names.append(n)
            s.origin.append(o)
        return s


CHUNKS = (("chunk", "waverider_asm"), ("c_chunk", "waverider_c"), ("machines_chunk", "machines"), ("flt_chunk", "a2_filters"))


def ours_from_code_json(path: str | pathlib.Path) -> tuple[dict[int, str], list[tuple[int, int, str]]]:
    """the build's waverider_code.json -> ({start: name}, chunk regions)"""
    d = json.loads(pathlib.Path(path).read_text())
    regions = []
    for key, name in CHUNKS:
        if key in d:
            lo = d[key]["load"]
            regions.append((lo, lo + len(d[key]["code"]) // 2, name))
    names: dict[int, str] = {}
    for n, a in d.get("layout", {}).items():
        if isinstance(a, int) and any(lo <= a < hi for lo, hi, _ in regions):
            names.setdefault(a, n)
    for n, a in d.get("c_text_symbols", {}).items():
        names[a] = n
    c_end = d.get("layout", {}).get("c_text_end")
    if c_end:                                    # the C chunk's code only (its data follows)
        regions = [(lo, c_end, nm) if nm == "waverider_c" else (lo, hi, nm) for lo, hi, nm in regions]
    return names, regions
