"""The CPU profiler (PROFILE, csrc/devtest/prof.c) in the ColdFire emulator: the `dt:profile:...` steps of
scripts/emu_waverider_menu.py.

The emulator models neither DMA timer 0 (its counter stands at 0, its mode register reads 0: on the unit
the boot left it running) nor the interrupt controller's SIMR / CIMR (stock's own writes to them change
nothing here). So, for source 32 only (stock never touches it):

- `start` puts DTMR0 as the unit's boot leaves it (0x0003: enabled, bus clock, free running) if it reads 0,
  and IMRH bit 0 at its reset value (masked), then sends PROFILE START; a write hook makes SIMR / CIMR
  writes of 32 set / clear IMRH bit 0, as the hardware does;
- `run:N:SLICE` runs the UI SLICE instructions at a time, N times, and after each slice raises vector 96
  at level 6 when the firmware has armed it (ICR32 = 6, unmasked, DTMR0.ORRI) and the CPU's mask is below
  6: the timer's interrupt, at the instant a slice ends. The handler runs to its rte (back to the
  interrupted PC), its instructions counted: the profiler's cost per sample;
- `read:NAME` stops it and reads the ring: the samples, each PC checked against the one the interrupt
  was raised at, every PC inside code.
"""

from __future__ import annotations

import struct

DTMR0, DTRR0, ICR32, IMRH0, SIMR0, CIMR0 = 0xFC070000, 0xFC070004, 0xFC048060, 0xFC048008, 0xFC04801C, 0xFC04801D
VEC96 = 0x40000180
ORRI = 0x10
CODE = ((0x40000400, 0x4030C980), (0x466B74D0, 0x47000000))     # stock MAIN OS; the mods' chunks above BSS


class Prof:
    def __init__(self, machine, uc, K, panel, dt_call, DP):
        self.m, self.uc, self.K, self.panel, self.call, self.P = machine, uc, K, panel, dt_call, DP
        self.raised: list[int] = []
        self.cost: list[int] = []
        self.masked = 0
        self.hook = None
        self.result: dict = {"notes": []}

    # the hardware this emulator leaves out, for source 32 only
    def _intc(self, uc_, access, address, size, value, user):
        if value & 0xFF != 32:
            return
        imrh = self.m.long(IMRH0)
        self.m.write(IMRH0, struct.pack(">I", imrh | 1 if address == SIMR0 else imrh & ~1))

    def start(self, source: int, rate: int) -> None:
        from unicorn import UC_HOOK_MEM_WRITE
        if self.hook is None:
            self.hook = self.uc.hook_add(UC_HOOK_MEM_WRITE, self._intc, begin=SIMR0, end=CIMR0)
        if self.m.word(DTMR0) == 0:
            self.m.write(DTMR0, struct.pack(">H", 0x0003))
            self.result["notes"].append("DTMR0 read 0 (no boot loader here): set 0x0003 as the unit's boot leaves it")
        self.m.write(IMRH0, struct.pack(">I", self.m.long(IMRH0) | 1))
        r = self.call(self.P.PROFILE, self.P.args_profile_start(source, rate))
        st = None if r is None else self.P.parse_profile_status(r.data)
        self.result["start"] = {"status": None if r is None else r.status, "why": None if st is None else st.why_text,
                                "vector96": f"{self.m.long(VEC96):#010x}", "icr32": self.m.read(ICR32, 1)[0],
                                "imrh_bit0": self.m.long(IMRH0) & 1, "dtmr0": f"{self.m.word(DTMR0):#06x}",
                                "dtrr0": f"{self.m.long(DTRR0):#010x}"}
        print(f"  dt profile start: {self.result['start']}")

    def _armed(self) -> bool:
        return (self.m.read(ICR32, 1)[0] & 7) == 6 and not self.m.long(IMRH0) & 1 and bool(self.m.word(DTMR0) & ORRI)

    def _deliver(self) -> None:
        uc, K = self.uc, self.K
        ret = self.m.pc
        uc.reg_write(K.UC_M68K_REG_PC, ret)
        if (uc.reg_read(K.UC_M68K_REG_SR) >> 8 & 7) >= 6:
            self.masked += 1                      # the hardware would hold it until the mask drops
            return
        if not self.m.m.raise_vector(96, level=6):
            self.result["notes"].append("raise_vector(96) refused")
            return
        from unicorn import UC_HOOK_CODE
        n = [0]

        def tick(uc_, address, size, user):
            n[0] += 1
        h = uc.hook_add(UC_HOOK_CODE, tick)
        stepper = getattr(self.m.m, "_fast_stepper_obj", None)
        if stepper is not None:
            stepper.left = 1 << 40
        try:
            uc.emu_start(uc.reg_read(K.UC_M68K_REG_PC), ret, count=20_000)
        finally:
            if stepper is not None:
                stepper.left = 0
            uc.hook_del(h)
        self.m.pc = uc.reg_read(K.UC_M68K_REG_PC)
        if self.m.pc != ret:
            self.result["notes"].append(f"the handler did not return to {ret:#010x} (at {self.m.pc:#010x})")
        self.raised.append(ret)
        self.cost.append(n[0])

    def run(self, times: int, slice_: int) -> None:
        for _ in range(times):
            self.panel.settle(slice_)
            if self._armed():
                self._deliver()
        print(f"  dt profile run: {len(self.raised)} interrupts raised, {self.masked} held by the mask, "
              f"handler {min(self.cost, default=0)}..{max(self.cost, default=0)} instructions")

    def read(self, name: str) -> dict:
        P = self.P
        r = self.call(P.PROFILE, P.args_profile_stop())
        st = P.parse_profile_status(r.data) if r is not None and r.status == 0 else None
        samples, since = [], 0
        while st is not None and since < st.samples:
            q = self.call(P.PROFILE, P.args_profile_read(since))
            if q is None or q.status:
                break
            _total, first, got = P.parse_profile_read(q.data)
            if not got:
                break
            samples += got
            since = first + len(got)
        pcs = [s.pc for s in samples]
        in_code = sum(1 for pc in pcs if any(lo <= pc < hi for lo, hi in CODE))
        top: dict[str, int] = {}
        for pc in pcs:
            top[f"{pc:#010x}"] = top.get(f"{pc:#010x}", 0) + 1
        out = {**self.result, "name": name,
               "status": None if st is None else {k: (f"{v:#x}" if k in ("dtim0", "dtrr0", "intc", "vector96", "ring") else v)
                                                  for k, v in st.__dict__.items()},
               "after_stop": {"vector96": f"{self.m.long(VEC96):#010x}", "icr32": self.m.read(ICR32, 1)[0],
                              "imrh_bit0": self.m.long(IMRH0) & 1, "dtmr0": f"{self.m.word(DTMR0):#06x}",
                              "dtrr0": f"{self.m.long(DTRR0):#010x}"},
               "raised": len(self.raised), "masked": self.masked, "samples": len(samples), "in_code": in_code,
               "pcs_match_raised": pcs == self.raised[:len(pcs)],
               "ipl": sorted({s.ipl for s in samples}),
               "ipl_counts": {str(k): sum(1 for s in samples if s.ipl == k) for k in sorted({s.ipl for s in samples})},
               "tcbs": sorted({f"{s.tcb:#010x}" for s in samples})[:12],
               "top_pcs": sorted(top.items(), key=lambda kv: -kv[1])[:20],
               "handler_instructions": {"min": min(self.cost, default=0), "max": max(self.cost, default=0),
                                        "mean": round(sum(self.cost) / len(self.cost), 1) if self.cost else 0}}
        print(f"  dt profile {name}: {len(samples)} samples, {in_code} in code, PCs match the raised ones: "
              f"{out['pcs_match_raised']}, handler {out['handler_instructions']} instructions")
        return out
