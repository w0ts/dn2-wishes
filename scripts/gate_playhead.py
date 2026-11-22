"""The samplist step's playhead verdict (ship_gate.py 6f, v0.40; 2026-11-16 per UI pass), apart so its
negative control runs the very same code.

The playhead run (emu_waverider_menu.py) sends four DSP packets on the page's track -- moved (none ->
0x2000), moved (0xA000, the newer note), STILL (0xA008, the same column), moved (0xE000) -- and after each:
smp_wants_redraw() (our redraw ask), wr_draws, one whole pass of the UI's redraw routine (`pass:`), the
playhead read back, a screenshot (v1..v4; v0 before), wr_draws again.

Why per pass and not per time: the routine runs about every 4.4 M instructions in the emulator and draws at
every run (stock asks it), on v0.56.1 (bc9018e3) and v0.56.2 (a43bc22a) alike, so the draw count cannot tell a
still playhead's redraw from stock's. What tells it: our ask (0 for the still packet) and the screen.
"""

from __future__ import annotations

import io
import pathlib

# The screenshot rows that may change in the still packet's pass: the top strip only. Measured 2026-11-16 on the
# 768 x 384 screenshots (128 x 64 at 6x) of v2 against v3 (the still pass): the differing box is rows 0..29 on
# v0.56.1 bc9018e3 and rows 0..35 on v0.56.2 a43bc22a, columns 102..749, nothing at or below row 36; the
# waveform and the playhead are below. Rows WAVE_ROW0.. must be byte-identical across that pass.
WAVE_ROW0 = 37


def wave_rows(png: bytes) -> bytes:
    from PIL import Image                                # noqa: PLC0415
    im = Image.open(io.BytesIO(png)).convert("L")
    return im.crop((0, WAVE_ROW0, im.width, im.height)).tobytes()


def playhead_fact(pr: dict, smp_playhead: int, smp_wants_redraw: int, wr_draws: int) -> tuple[bool, bool, str]:
    """-> (newest note's playhead ok, moved drawn / still not redrawn ok, detail) from the run's JSON PR"""
    pm = pr.get("memory", {})
    wd = f"{wr_draws:#x}"
    calls = pr.get("direct_calls", [])
    heads = [c["d0"] for c in calls if int(c["fn"], 16) == smp_playhead]
    asks = [c["d0"] for c in calls if int(c["fn"], 16) == smp_wants_redraw]
    sh = {n: pathlib.Path(pr["screens"][n]).read_bytes() if n in pr.get("screens", {}) else b""
          for n in ("v0", "v1", "v2", "v3", "v4")}
    dr = [int(pm[k], 16) for k in [wd] + [f"{wd}@{i}" for i in range(2, 9)] if k in pm]
    passes = [u for u in pr.get("until", []) if u[0] == "pass"]
    newest = pm.get("0x42432a6c") == "00" and heads == [0x2000, 0xA000, 0xA008, 0xE000]
    still_same = bool(sh["v2"]) and bool(sh["v3"]) and wave_rows(sh["v2"]) == wave_rows(sh["v3"])
    parts = {"4 passes, each done": len(passes) == 4 and all(u[2] for u in passes),
             "redraw asks [1, 1, 0, 1]": asks == [1, 1, 0, 1],
             "moved shown (v1 != v0, v2 != v1, v4 != v3)": sh["v1"] != sh["v0"] and sh["v2"] != sh["v1"] and sh["v4"] != sh["v3"],
             "moved drawn by the pass (draws up)": len(dr) == 8 and dr[1] > dr[0] and dr[3] > dr[2] and dr[7] > dr[6],
             f"still: rows {WAVE_ROW0}.. of v2 and v3 byte-identical": still_same}
    detail = (f" playheads {heads} redraw asks {asks} draws (before, after each pass) {dr} passes {passes} "
              f"parts {parts}")
    return newest, all(parts.values()), detail
