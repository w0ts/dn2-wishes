"""The telemetry frame: SysEx 32 TLM's 32 big-endian words (csrc/sampler/link.c, csrc/meter/meter.c).

    0 'TLM1'  1 build id  2 audio frames since power-on (1,500 a second)  3 sample-link periods
    4 D now, permille (the DSP's load, last half second's peak)  5 D peak, percent  6 C now, permille
    7 C peak, percent  8 heap used, bytes  9 heap total  10 heap walk faults
    11 label bits: lit now (bit 0 D, 1 C, 2 M) | hysteresis << 8 | forced << 16
    12..14 frames since each label's last event (D, C, M)
    15 voices skipped for time (bit v) | insert full << 16  16 insert blocks passed through for time
    17 periods since the last of those  18 HOLD latches made  19 HOLD same-key drops  20 voices latched (bit v)
    21 A2 voices filtered | dry << 16 (16 bits each)  22 sum of the slots' cost, cycles
    23 slots sounding: cost over SOUNDING_CYCLES (every slot's voice code runs every block, sounding or not: an idle
       slot costs ~1,500 cycles, a held note 16,000..28,000; measured on the unit 2026-11-11)
    24..31 slot costs / 16, two to a word (slot 0 in the high half)
A value the unit has no figure for reads 0xFFFFFFFF (None here).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

CMD_TLM = 32
MAGIC = 0x544C4D31
NONE = 0xFFFFFFFF
WORDS = 32
FRAMES_PER_S = 1500
FRAME_CYCLES = 666_667
SOUNDING_CYCLES = 8_000           # csrc/sampler/link.c TLM_SOUNDING: a slot over this is sounding
IDLE_SLOT_CYCLES = 1_456          # what an idle slot's voice code costs a block (the unit, 2026-11-11)
LABELS = ("D", "C", "M")          # the title bar's DSP / CPU / RAM words


def _opt(v: int) -> int | None:
    return None if v == NONE else v


@dataclass(frozen=True)
class Telemetry:
    build: int
    frames: int
    periods: int
    d_pm: int | None
    d_peak_pct: int | None
    c_pm: int | None
    c_peak_pct: int | None
    heap_used: int | None
    heap_total: int | None
    heap_faults: int
    labels_lit: int
    labels_hys: int
    labels_force: int
    label_age: tuple[int | None, int | None, int | None]
    skip_mask: int
    ins_full: bool
    ins_skips: int
    ins_skip_age: int | None
    hold_count: int
    hold_drops: int
    hold_seq: int
    a2_filtered: int
    a2_dry: int
    frame_cost: int
    voices: int
    slot_cost: tuple[int, ...]

    @property
    def d_pct(self) -> float | None:
        return None if self.d_pm is None else self.d_pm / 10.0

    @property
    def c_pct(self) -> float | None:
        return None if self.c_pm is None else self.c_pm / 10.0

    @property
    def heap_pct(self) -> float | None:
        if self.heap_used is None or not self.heap_total:
            return None
        return 100.0 * self.heap_used / self.heap_total

    @property
    def lit(self) -> tuple[str, ...]:
        return tuple(n for k, n in enumerate(LABELS) if self.labels_lit >> k & 1)

    @property
    def cost_pct(self) -> float:
        """the slots' summed cost against the frame (666,667 cycles)"""
        return 100.0 * self.frame_cost / FRAME_CYCLES

    @property
    def latched(self) -> int:
        return bin(self.hold_seq & 0xFFFF).count("1")

    @property
    def skipped_voices(self) -> int:
        return bin(self.skip_mask & 0xFFFF).count("1")


def decode(payload: bytes) -> Telemetry:
    if len(payload) < 4 * WORDS:
        raise ValueError(f"telemetry frame: {len(payload)} bytes, {4 * WORDS} expected")
    w = struct.unpack(f">{WORDS}I", payload[:4 * WORDS])
    if w[0] != MAGIC:
        raise ValueError(f"telemetry frame: magic {w[0]:#010x}, not 'TLM1'")
    costs = []
    for k in range(8):
        costs += [(w[24 + k] >> 16) * 16, (w[24 + k] & 0xFFFF) * 16]
    return Telemetry(
        build=w[1], frames=w[2], periods=w[3], d_pm=_opt(w[4]), d_peak_pct=_opt(w[5]), c_pm=_opt(w[6]),
        c_peak_pct=_opt(w[7]), heap_used=_opt(w[8]), heap_total=_opt(w[9]), heap_faults=w[10],
        labels_lit=w[11] & 7, labels_hys=w[11] >> 8 & 7, labels_force=w[11] >> 16 & 7,
        label_age=(_opt(w[12]), _opt(w[13]), _opt(w[14])), skip_mask=w[15] & 0xFFFF, ins_full=bool(w[15] >> 16 & 1),
        ins_skips=w[16], ins_skip_age=_opt(w[17]), hold_count=w[18], hold_drops=w[19], hold_seq=w[20],
        a2_filtered=w[21] & 0xFFFF, a2_dry=w[21] >> 16, frame_cost=w[22], voices=w[23], slot_cost=tuple(costs))


def _raw(v: int | None) -> int:
    return NONE if v is None else v


def encode(t: Telemetry) -> bytes:
    """the frame the unit would send (the simulator's reply; decode's inverse up to the /16 rounding)"""
    w = [0] * WORDS
    w[0], w[1], w[2], w[3] = MAGIC, t.build, t.frames & 0xFFFFFFFF, t.periods & 0xFFFFFFFF
    w[4], w[5], w[6], w[7] = _raw(t.d_pm), _raw(t.d_peak_pct), _raw(t.c_pm), _raw(t.c_peak_pct)
    w[8], w[9], w[10] = _raw(t.heap_used), _raw(t.heap_total), t.heap_faults
    w[11] = t.labels_lit | t.labels_hys << 8 | t.labels_force << 16
    w[12], w[13], w[14] = (_raw(a) for a in t.label_age)
    w[15] = t.skip_mask | int(t.ins_full) << 16
    w[16], w[17] = t.ins_skips & 0xFFFFFFFF, _raw(t.ins_skip_age)
    w[18], w[19], w[20] = t.hold_count, t.hold_drops, t.hold_seq
    w[21] = (t.a2_filtered & 0xFFFF) | (t.a2_dry & 0xFFFF) << 16
    w[22], w[23] = t.frame_cost, t.voices
    for k in range(8):
        w[24 + k] = (t.slot_cost[2 * k] // 16 & 0xFFFF) << 16 | (t.slot_cost[2 * k + 1] // 16 & 0xFFFF)
    return struct.pack(f">{WORDS}I", *w)
