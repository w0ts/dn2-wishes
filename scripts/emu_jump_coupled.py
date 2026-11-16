"""DIRECT JUMP's rapid-fire sweep on the coupled emulator: emu_jump.py's `rapid`, its own code and checks, with the
ColdFire run as emu_coupled.py runs it (each audio period the UI's slice, then the audio ISR; the sequencer's ISR at the
tempo's rate between them).

Why (2026-11-14, the 1.12 gate's blind spots): emu_jump.py runs the UI only in short windows (200 K instructions every 8
sequencer entries), with no TDM side. On 1.12 the switch to A04 starts a kit load that never completes there (the
screen shows another kit, an empty pattern box); from then on no key reaches stock's PTN cue and every later cue fails.
On the coupled emulator, from the same snapshot, the same kit load completes (A04 FUCHSIA 67.0) and every cue arms.

What stays emu_jump's: the four patterns, the plan (83 cues), the checks and the JSON line `emu_jump rapid: {...}`
(emu_jump.rapid itself is called). The +Drive is served as there, the setting turned on with PTN + YES as there, and
stock's fault reporter is hooked as there. What the coupled emulator brings: the UI and the audio ISR run every period.
As in emu_jump, the sequencer does not advance while a key is down or being let go (its entries are counted from the
cue), and one `isr()` is one sequencer entry: the periods up to and including the one that entered it.

    emu_jump_coupled.py --build BUILD.syx --stock STOCK.syx --snapshot SNAP [--json OUT] [--png-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_jump as J                                    # noqa: E402
from emu_coupled import UI_SLICE, Coupled               # noqa: E402
from emulib.panel import SETTLE, TAP, YES                       # noqa: E402

ENTRIES_A_PERIOD_MAX = 1                                # at most one sequencer entry a period below 937 BPM
SEQ_WAIT_MOST = 3000                                    # periods (2 s) without an entry: the sequencer stopped (an entry is due every ~12 at 81 BPM)


class Paced(Coupled):
    """the coupled emulator whose sequencer can be held (no entry, no time for it) while keys are handled"""

    seq_hold = False

    def _seq_tick(self):
        if not self.seq_hold:
            super()._seq_tick()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--build", required=True, help="the build (.syx)")
    p.add_argument("--stock", required=True, help="stock (.syx)")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--json")
    p.add_argument("--png-dir")
    a = p.parse_args()

    c = Paced(a.build, a.snapshot, a.stock, png_dir=a.png_dir, dsp=False)
    m, uc = c.machine, c.uc
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    syms = {k: v for k, v in lay.items() if k.startswith("jmp_")}

    # the +Drive, served as emu_jump.py serves it
    disk: dict[int, bytes] = {}
    io = {"reads": [], "writes": []}

    def blk(uc_, address, size, user):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        sector, n, buf = struct.unpack(">3I", bytes(uc.mem_read(sp + 4, 12)))
        if address == J.BLK_READ:
            io["reads"].append(sector)
            uc.mem_write(buf, b"".join(disk.get(sector + k, bytes(512)) for k in range(n // 512)))
        else:
            io["writes"].append(sector)
            data = bytes(uc.mem_read(buf, n))
            for k in range(n // 512):
                disk[sector + k] = data[512 * k:512 * k + 512]
    for va in (J.BLK_READ, J.BLK_WRITE):
        m.write(va, bytes.fromhex("70004e75"))          # moveq #0,%d0 ; rts: the hook does the work
        uc.hook_add(UC_HOOK_CODE, blk, begin=va, end=va)
    m.write(J.BLK_READY, struct.pack(">I", 1))
    m.write(J.BLK_SECTORS, struct.pack(">I", 0x3A00000))
    m.flush()

    faults: list[str] = []
    uc.hook_add(UC_HOOK_CODE, lambda u, ad, sz, us: faults.append(f"{u.reg_read(K.UC_M68K_REG_PC):#x}"),
                begin=J.FAULT_REPORTER, end=J.FAULT_REPORTER)
    entries = [0]
    uc.hook_add(UC_HOOK_CODE, lambda u, ad, sz, us: entries.__setitem__(0, entries[0] + 1),
                begin=J.SEQ_ISR, end=J.SEQ_ISR)

    def periods(n):
        if not c.periods(n):
            raise SystemExit(f"emu_jump rapid: {json.dumps({'ok': False, 'halt': c.halt, 'faults': faults})}")

    def u8(va): return c.read(va, 1)[0]
    def u16(va): return struct.unpack(">H", c.read(va, 2))[0]
    def u32(va): return c.long(va)

    def sym(name, n=1):
        return int.from_bytes(c.read(syms[name], n), "big") if name in syms else None

    def isr():
        """one sequencer entry: the periods up to and including the one that entered it"""
        e0, waited = entries[0], 0
        while entries[0] == e0:
            periods(1)
            waited += 1
            if waited > SEQ_WAIT_MOST:
                raise SystemExit(f"emu_jump rapid: {json.dumps({'ok': False, 'why': f'no sequencer entry in {waited} periods', 'faults': faults})}")
        if entries[0] - e0 > ENTRIES_A_PERIOD_MAX:
            raise SystemExit(f"{entries[0] - e0} sequencer entries in one period")

    class Keys:
        """emu_jump's Panel calls, in periods: the UI and the audio ISR run, the sequencer is held"""

        @staticmethod
        def _run(instructions):
            c.seq_hold = True
            try:
                periods(max(1, math.ceil(instructions / UI_SLICE)))
            finally:
                c.seq_hold = False

        def hold(self, key, instructions=SETTLE):
            m.pc = c.panel.panelin.press(m.m, c.panel.profile, *key)
            self._run(instructions)

        def let_go(self, key, after=SETTLE):
            m.pc = c.panel.panelin.release(m.m, c.panel.profile, *key)
            self._run(after)

        def tap(self, key, after=SETTLE):
            self.hold(key, TAP)
            self.let_go(key, after)

        def settle(self, instructions=SETTLE):          # between entries the UI already ran its periods
            return instructions

        def screen(self, name):
            return c.panel.screen(name)

    panel = Keys()
    trace: list[dict] = []

    def pat_index():
        return (u32(0x42C5B9A0) - J.P0) // J.PSTRIDE

    def record(tag=""):
        import hashlib                          # noqa: PLC0415
        block = c.read(0x42C5B900, 0x200) + c.read(0x446493D0, 0xF4)
        row = {"n": len(trace), "tag": tag, "pat": pat_index(), "a91c": u16(0x42C5B91C), "tick": u8(0x42C5B91E),
               "t6": u32(0x42C5B9D0) * 6 + u32(0x42C5B9D4),
               "cur": list(c.read(0x42C5B984, 16)), "next": list(c.read(0x42C5B964, 16)),
               "digest": hashlib.sha256(block).hexdigest()[:16]}
        trace.append(row)
        return row

    out = {"scenario": "rapid", "variant": "pp", "stock": False, "emulator": "coupled (dsp off)"}

    def press_with_ptn(key, name):
        panel.hold(J.PTN, 3_000_000)
        panel.tap(key, 3_000_000)
        out[f"png_{name}"] = panel.screen(name)
        panel.let_go(J.PTN, 3_000_000)

    c.seq_hold = True                           # as emu_jump: the UI settles before PLAY
    periods(20)
    c.seq_hold = False
    press_with_ptn(YES, "ptn_yes")
    Keys._run(5_000_000)
    s = disk.get(J.SET_SECTOR)
    out.update(on=sym("jmp_on"), sector_after_yes=None if s is None else s[:16].hex(), writes_after_yes=list(io["writes"]))
    return J.rapid(a, m, panel, out, record, trace, sym, faults, isr, u8, u32, press_with_ptn)


if __name__ == "__main__":
    raise SystemExit(main())
