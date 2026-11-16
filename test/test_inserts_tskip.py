"""2026-11-12 (round 13, main: which insert is refused): every block an insert is left out is counted under its type
(dnfw.perc.guard.INS_TSKIP), and the counts reach the ColdFire (idle packet units 42..57, link.c, DIAG). The counting
itself is checked in the SHARC runner's insdl step (TIGHT: the counts add up to INS_SKIPS)."""

from __future__ import annotations

import pathlib

from dnfw.inserts import bus as B
from dnfw.inserts import design as D
from dnfw.inserts import post as Q
from dnfw.inserts import program as P
from dnfw.perc import guard as G
from dnfw.waverider import dsp

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_the_counts_sit_in_their_claim_and_hold_every_type():
    assert G.INS_TSKIP == dsp.INS_TSKIP_DM and G.INS_TEL_END - G.INS_TSKIP == dsp.INS_TSKIP_BYTES
    assert len(D.NAMES) <= G.INS_TSKIP_WORDS - 2                # two words kept for the inserts' own gate
    src = (ROOT / "src/dnfw/waverider/dsp.py").read_text()      # (dsp._raw_spans needs the DT2 sections)
    assert "INS_TSKIP_DM, bytes(64) + (0x7FFFFFFF).to_bytes(4, \"little\") * 4" in src


def test_every_insert_admit_counts_its_type():
    # 2026-11-12 (opt-inserts): every pass's inserts go through guard.ins_gate, which counts a refused block under the
    # type in C['sel'] (count_skip_r), a held-out one under 14 and a faded one (the bus) under 15
    pre, post, bus = P.program(dsp.PING_SW), Q.program(), B.program()
    for name, text in (("pre", pre), ("post", post), ("bus", bus)):
        assert f"{G.INS_TSKIP:#x}" in text and "R9 = R1 AND R12;" in text, name
        assert f"R1 = {G.INS_TSKIP_WORDS - 2:#x};" in text or f"R1 = {G.INS_TSKIP_WORDS - 2};" in text, name
    assert f"R1 = {G.INS_TSKIP_WORDS - 1:#x};" in bus or f"R1 = {G.INS_TSKIP_WORDS - 1};" in bus


def test_the_model_never_counts():
    # run mode (the model, the references) is untouched: count_skip emits nothing there
    class Run:
        run = True
    G.count_skip(Run(), D.FDN8)
    G.count_skip(Run(), typ_at=B.C["sel"])


def test_the_counts_reach_the_coldfire_and_diag():
    link = (ROOT / "csrc/sampler/link.c").read_text()
    assert "smp_ins_tskip[t] = v[42 + t];" in link
    assert "smp_ins_tskip[t] | (u32)smp_ins_tskip[t + 1] << 16" in link
    smp = (ROOT / "src/dnfw/sampler/program.py").read_text()
    assert "p.loop_r(11, G.INS_TSKIP_WORDS, tskip)" in smp


def test_the_register_form_counts_the_type_in_a_register():
    from dnfw.perc.dsl import Prog
    p = Prog("emit", prefix="t")
    G.count_skip_r(p, 5)
    text = "\n".join(p.lines)
    assert f"{G.INS_TSKIP:#x}" in text and "R9 = R5 AND R12;" in text
