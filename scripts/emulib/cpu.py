"""A guest call's CPU state kept: what the harnesses put back after calling a firmware function directly.

A harness that calls FN with the return address SENTINEL and then lets the machine run on (a panel's settle,
longrun.spin) must leave the CPU exactly as it found it: D0-D7, A0-A7, PC and SR. Two harnesses lost a run to the
PC alone (emu_flexcore 2026-11-16, emu_rectext 2026-11-17): the next chunk's interrupt pushed the CPU's PC, left
at SENTINEL, as the interrupted PC; its rte then ran into the sentinel and on into the RAM after it (stock's
exception handler at 0x40001252, "the UI never came back to its idle loop"). Which build and which timer phase
showed it was chance. SR is put back for the same reason: an IPL left changed masks the next interrupts.

    with kept(uc):
        ... uc.emu_start(fn, SENTINEL) ...
"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def kept(uc):
    """D0-D7, A0-A7, PC and SR as they are now, put back when the block ends (also when it raises)"""
    from unicorn import m68k_const as K
    regs = [getattr(K, f"UC_M68K_REG_{r}{i}") for r in "DA" for i in range(8)]
    regs += [K.UC_M68K_REG_PC, K.UC_M68K_REG_SR]
    saved = [uc.reg_read(r) for r in regs]
    try:
        yield
    finally:
        for r, v in zip(regs, saved):
            uc.reg_write(r, v)
