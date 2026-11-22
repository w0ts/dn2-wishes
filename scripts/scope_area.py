"""The scope writes only its own place (2026-11-21, the gate gap "nothing checks that the scope never writes outside its
strip"; csrc/scope/scope.c), for scripts/emu_scope.py --proof.

Every write made by the scope's own code is watched (a Unicorn write hook, on while it runs):

- scope_draw (in every full draw, on the draw's canvas): from its entry to its return. On the canvas, every pixel it
  changed must be in the scope's place, AREA_X x AREA_Y (the strip clear_strip clears, x 18..127, rows 0..53 counted
  up from the bottom: the trace, its zero line, the labels of G and H; rows 54..63, the title bar, and columns 0..17,
  stock's left panel, are not its);
- scope_poll (a frame drawn alone): from its entry to panel_diff's call or its return. It writes FRONT (the glass
  copied, its changed columns over it: emu_scope.py check_alone compares that frame byte for byte), never the canvas
  it is not drawing;
- both: any other write of its code (a PC outside stock's image) lands in the build's C chunk (scope.c's own state),
  on the stack below the call, or in the call's argument slot (gcc's tail call to SET_DIRTY reuses it). Any write
  elsewhere (stock's RAM, the other frame buffer, a table of stock's) fails, with its address and PC.

Writes made in the window by others are not the scope's: an interrupt (the status register's level above the one at
the entry), another task (the stack pointer outside the call's stack), and stock's routines it calls (SET_DIRTY's
dirty byte, the labels' text routines' own state: measured on v0.67.1, PCs 0x4011d5e4, 0x40120116, 0x40120474,
0x4012048c; counted and listed, and on the canvas still compared pixel for pixel). Python's own writes (the harness,
the emulator's DMA) are never seen by a write hook.

Control (`control()`): a stub run at the next scope_draw's entry writes one byte of free RAM and one pixel of the canvas
at column 2 (stock's left panel), then jumps to scope_draw: both must be reported. The stub and the RAM byte are in
the snapshot's free RAM (emu_encoder_trace.STACK_TOP + 0x1000, as emu_slides' scratch canvases).
"""

from __future__ import annotations

import struct

AREA_X, AREA_Y = (18, 127), (0, 53)
STACK_SPAN = 0x4000                             # bytes below the call's stack pointer that are its own frames
STOCK_CODE_END = 0x40400000                     # stock 1.12's image (section 3, 3.6 MB from 0x40000000) below; ours (the C chunk, the control's stub) far above
STUB, CONTROL_RAM = 0x46A21800, 0x46A21C00      # free RAM in the snapshot (emu_encoder_trace STACK_TOP + 0x1800)
CONTROL_PIXEL = (2, 20)


def in_area(i: int, bit: int) -> bool:
    """byte I of a canvas, bit BIT (0x80 >> (y % 8)): in the scope's place"""
    x, y = i // 8, 8 * (i % 8) + (7 - bit.bit_length() + 1)
    return AREA_X[0] <= x <= AREA_X[1] and AREA_Y[0] <= y <= AREA_Y[1]


def outside_pixels(before: bytes, after: bytes) -> list[tuple[int, int]]:
    """the pixels (x, y) changed from BEFORE to AFTER outside the scope's place"""
    out = []
    for i, (p, q) in enumerate(zip(before, after)):
        d = p ^ q
        while d:
            bit = d & -d
            d ^= bit
            if not in_area(i, bit):
                out.append((i // 8, 8 * (i % 8) + 8 - bit.bit_length()))
    return out


class AreaWatch:
    def __init__(self, m, K, sym: dict, chunk: tuple[int, int], panel_diff: int, fb_front: int):
        from unicorn import UC_HOOK_CODE
        self.m, self.K, self.chunk = m, K, chunk
        self.fb_front = fb_front
        self.win = None
        self.rets: set[int] = set()
        self.counts = {"draws": 0, "alone": 0, "writes": 0, "others": 0, "stock's": 0}
        self.stock_pcs: set[int] = set()
        self.fails: list[str] = []
        self.control_armed, self.control_seen = False, None
        self.draw, self.poll = sym["scope_draw"], sym["scope_poll"]
        m.uc.hook_add(UC_HOOK_CODE, self.on_draw, begin=self.draw, end=self.draw)
        m.uc.hook_add(UC_HOOK_CODE, self.on_poll, begin=self.poll, end=self.poll)
        m.uc.hook_add(UC_HOOK_CODE, self.on_diff, begin=panel_diff, end=panel_diff)

    # --- the window ---------------------------------------------------------------------------------------------
    def _open(self, kind: str, buf: int | None):
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
        uc, K = self.m.uc, self.K
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        ret = self.m.long(sp)
        self.win = {"kind": kind, "sp": sp, "ret": ret, "ipl": (uc.reg_read(K.UC_M68K_REG_SR) >> 8) & 7,
                    "buf": buf, "before": bytes(self.m.read(buf, 1024)) if buf else None,
                    "front": self.m.long(self.fb_front), "bad": [], "hook": uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write)}
        if ret not in self.rets:
            self.rets.add(ret)
            uc.hook_add(UC_HOOK_CODE, self.on_ret, begin=ret, end=ret)

    def _close(self):
        w, self.win = self.win, None
        self.m.uc.hook_del(w["hook"])
        what = "scope_draw" if w["kind"] == "draw" else "scope_poll (a frame alone)"
        bad = list(w["bad"])
        if w["buf"]:
            px = outside_pixels(w["before"], bytes(self.m.read(w["buf"], 1024)))
            if px:
                bad.append(f"{len(px)} canvas pixels outside x {AREA_X[0]}..{AREA_X[1]}, rows {AREA_Y[0]}..{AREA_Y[1]} "
                           f"changed (first {px[:4]})")
        self.counts["draws" if w["kind"] == "draw" else "alone"] += 1
        if self.control_seen is not None and w["kind"] == "draw" and self.control_seen == []:
            self.control_seen = bad
            return
        for b in bad[:3]:
            if len(self.fails) < 20:
                self.fails.append(f"{what}: {b}")

    def on_draw(self, uc, ad, sz, us):
        if self.win is not None:
            return                              # (the control's jump back to scope_draw: the same window)
        canvas = self.m.long(uc.reg_read(self.K.UC_M68K_REG_A7) + 4)
        self._open("draw", self.m.long(canvas + 16))
        if self.control_armed:
            self.control_armed = False
            self.control_seen = []
            self._stub(self.win["buf"])
            uc.reg_write(self.K.UC_M68K_REG_PC, STUB)

    def on_poll(self, uc, ad, sz, us):
        if self.win is None:
            self._open("poll", None)

    def on_diff(self, uc, ad, sz, us):
        if self.win is not None and self.win["kind"] == "poll":
            self._close()

    def on_ret(self, uc, ad, sz, us):
        w = self.win
        if w is not None and ad == w["ret"] and uc.reg_read(self.K.UC_M68K_REG_A7) == w["sp"] + 4:
            self._close()

    def on_write(self, uc, typ, addr, size, value, data):
        w = self.win
        K = self.K
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        if ((uc.reg_read(K.UC_M68K_REG_SR) >> 8) & 7) > w["ipl"] or not (w["sp"] - STACK_SPAN <= sp <= w["sp"]):
            self.counts["others"] += 1          # an interrupt, or another task
            return
        self.counts["writes"] += 1
        end = addr + size
        if w["sp"] - STACK_SPAN <= addr and end <= w["sp"]:
            return
        if w["sp"] + 4 <= addr and end <= w["sp"] + 8:
            return                              # (its own argument's slot: gcc's tail call to SET_DIRTY passes it there)
        pc = uc.reg_read(K.UC_M68K_REG_PC)
        if pc < STOCK_CODE_END:                 # stock's routines the scope calls (SET_DIRTY, the label's text):
            self.counts["stock's"] += 1         # theirs; on the canvas still compared pixel for pixel
            self.stock_pcs.add(pc)
            return
        if self.chunk[0] <= addr and end <= self.chunk[1]:
            return
        if w["buf"] is not None and w["buf"] <= addr and end <= w["buf"] + 1024:
            return                              # (the canvas: its pixels compared at the window's end)
        if w["kind"] == "poll" and w["front"] <= addr and end <= w["front"] + 1024:
            return                              # (FRONT: check_alone compares the frame)
        if len(w["bad"]) < 8:
            w["bad"].append(f"wrote {size} B at {addr:#010x} (PC {pc:#010x})")

    # --- the control --------------------------------------------------------------------------------------------
    def _stub(self, buf: int):
        x, y = CONTROL_PIXEL
        px = buf + 8 * x + (y >> 3)
        old = self.m.read(px, 1)[0]
        code = (struct.pack(">HHI", 0x13FC, 0x005A, CONTROL_RAM)
                + struct.pack(">HHI", 0x13FC, old ^ (0x80 >> (y & 7)), px)
                + struct.pack(">HI", 0x4EF9, self.draw))
        self.m.write(STUB, code)
        self.m.flush()

    def control(self) -> None:
        """arm the control for the next scope_draw"""
        self.control_armed, self.control_seen = True, None

    def control_result(self) -> tuple[bool, list[str]]:
        """(both faults seen, what was reported)"""
        seen = self.control_seen or []
        ram = any(f"{CONTROL_RAM:#010x}" in s for s in seen)
        pixel = any("canvas pixels outside" in s and f"({CONTROL_PIXEL[0]}, {CONTROL_PIXEL[1]})" in s for s in seen)
        return ram and pixel, seen
