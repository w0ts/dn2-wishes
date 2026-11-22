"""The playing kit stored back as a boot has it, on a snapshot whose build converted it (the DEP attenuverter,
csrc/matrix/atten.c; 2026-11-21).

A snapshot made by a build with the attenuverter holds the playing kit CONVERTED: its UI pass moved each sound's DEP
into its LFOs' first routes' depths D (the wishes record) and set DEP to the attenuverter A (100 % on an old sound).
A ColdFire harness that writes a build's runtime over such a snapshot (code, .data, zeroed BSS: no wishes record, no
W_ATT, the matrix not loaded) leaves stock's kit converted while our code starts as at boot: the next UI pass converts
it again, D = A (every LFO of an old sound at full depth). No unit reaches that state: at boot stock loads the kit
stored (DEP = C = mxa_compat(D, A)). `store_kit` writes the stored form back, in the sound, the rows of the voices
playing it and the parameter smoother (settled), so the build's first UI pass converts once.

D and A are read where the snapshot keeps them: the matrix's tables (pages.MX_RAM, struct mx_state, laid out by the
snapshot's own build: its layout from its magic, 'MX' << 16 | its size; each track's live table's first-route words
nx1 = -2 x (D - 0x4000), MX_PASS (odd) for a sound not converted) and the sound's DEP (A). Each stored table's words
are then set to MX_PASS, so a second call stores nothing (the first UI pass clears MX_RAM anyway: mx_zero).

scripts/emu_coupled.py has its own copy (Coupled._store_kit, 2026-11-20); the two meet once the combined branch holds
emulib/mxlayout.py (claude/route-meas): emu_coupled then calls this.

    from emulib import attkit
    report = attkit.store_kit(m)       # after the runtime is written; m: .long(va), .read(va, n), .write(va, b)

DNFW_ATTKIT=0 skips it (the negative control: the double conversion back).
"""

from __future__ import annotations

import os
import struct

KIT_PTR, SOUND_STRIDE, VSOUND = 0x800052A0, 1163, 0x800052A8
SM_STATE, SM_SRC, SM_OUT = 0x8000DE60, 0x80003AF0, 0x800068E4
MX_KIT, MX_SOUND, MX_LIVE, MX_HEAD = 8, 28, 92, 720
MX_PASS = 1
SLOTS = 23
DEP_SLOT = (8, 16, 24)                  # LFO1-3 DEP in a sound's / a voice row's cells (atten.c mxr_dep_rec, 1.12)


def compat(depth: int, a: int) -> int:
    """atten.c mxa_compat: the DEP a stock unit plays (C) for a first route of DEPTH under the attenuverter A"""
    q = 16384 if a >= 0x7F00 else a - 0x4000
    return max(0, min(0x7FFE, 0x4000 + (((depth - 0x4000) * q) >> 14)))


def table_layout(magic: int) -> tuple[int, int] | None:
    """struct mx_state's tables as the build that wrote MAGIC lays them out -> (struct mx_tab's bytes, nx1's offset in
    it), or None for no matrix state / a size no attenuverter build makes. A route 12 bytes or 8 (DN2_ROUTE8), env_out's
    rows 30 words or 40 (DN2_LFO4): the same arithmetic as scripts/emulib/mxlayout.py (claude/route-meas)"""
    if magic >> 16 != 0x4D58:
        return None
    for entry in (12, 8):
        for lfo_w in (30, 40):
            tab_b = SLOTS * entry + 8 + 16 + 12
            none = MX_HEAD + 32 * tab_b
            env_out = none + tab_b
            scratch = env_out + 4 * 16 * lfo_w
            size = scratch + 2 * (2 * 16 * 101) + 32
            if size == magic & 0xFFFF:
                return tab_b, SLOTS * entry + 24
    return None


def _s32(m, va) -> int:
    return struct.unpack(">i", bytes(m.read(va, 4)))[0]


def _u16(m, va) -> int:
    return struct.unpack(">H", bytes(m.read(va, 2)))[0]


LAST: dict | None = None                # the last call's report (scripts/emu_matrix.py attsnap reads it)


def store_kit(m, mx_ram: int | None = None) -> dict | None:
    """-> {"sounds": n, "deps": [[t, lfo, A, D, C], ...]}, {"skipped": why}, or None (no converted kit here).
    DNFW_ATTKIT=0: nothing written, the report {"skipped": ..., "found": what it would have stored}"""
    global LAST
    LAST = _store_kit(m, mx_ram, os.environ.get("DNFW_ATTKIT", "1") != "0")
    return LAST


def _store_kit(m, mx_ram, write) -> dict | None:
    if mx_ram is None:
        from dnfw.waverider import pages
        mx_ram = pages.MX_RAM
    try:
        lay = table_layout(m.long(mx_ram))
        kit = m.long(KIT_PTR)
        mx_kit = m.long(mx_ram + MX_KIT)
    except Exception as e:                                      # MX_RAM not in this snapshot
        return {"skipped": f"no matrix state readable ({e})"}
    if lay is None:
        return None
    if not kit or mx_kit != kit:
        return {"skipped": "the matrix's tables were laid out for another kit"}
    tab_b, nx1 = lay
    out = {"sounds": 0, "deps": []}
    for t in range(16):
        snd = kit + 52 + SOUND_STRIDE * t
        if m.long(mx_ram + MX_SOUND + 4 * t) != snd:
            continue
        tab = mx_ram + MX_HEAD + tab_b * (2 * t + (m.long(mx_ram + MX_LIVE + 4 * t) & 1))
        stored = 0
        for lfo in range(3):
            x1 = _s32(m, tab + nx1 + 4 * lfo)
            if x1 & 1:                                          # MX_PASS: not converted, DEP is the depth already
                continue
            slot = DEP_SLOT[lfo]
            a = _u16(m, snd + 20 + 2 * slot)
            d = 0x4000 - x1 // 2
            c = compat(d, a)
            out["deps"].append([t, lfo + 1, a, d, c])
            stored = 1
            if not write:
                continue
            m.write(snd + 20 + 2 * slot, struct.pack(">H", c))
            for v in range(16):
                if m.long(VSOUND + 4 * v) != snd:
                    continue
                i = 17 + 101 * v + slot                         # the voice row's cell, as the smoother indexes it
                m.write(SM_SRC + 2 * i, struct.pack(">H", c))
                m.write(SM_STATE + 4 * i, struct.pack(">i", c << 16))
                m.write(SM_OUT + 2 * i, struct.pack(">H", c))
            m.write(tab + nx1 + 4 * lfo, struct.pack(">i", MX_PASS))   # stored: a second call leaves it
        out["sounds"] += stored
    return out if write else {"skipped": "DNFW_ATTKIT=0", "found": out}
