"""2026-11-16 (gate speed): a step's own temporary folder in the gate cache's record (scripts/gate_cache.py inputs,
_program_inputs), with its negative controls.

A step's temporary files go in a folder made empty for it (ship_gate.run). That folder is left out of the step's
record only when every program the step ran is accounted for: Python (traced itself), QUIET programs, and a cross
toolchain's programs, whose command-line files outside the folder go into the record. Any other program, or a file
named on a toolchain's command line that has gone, keeps the folder in the record (as before: not reused)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import gate_cache as GC                                         # noqa: E402


@pytest.fixture
def tmp_path():
    """a folder outside /tmp/pytest-* (gate_cache.SKIP leaves that out of every record)"""
    out = pathlib.Path(__file__).resolve().parent.parent / "out"
    out.mkdir(exist_ok=True)
    d = pathlib.Path(tempfile.mkdtemp(prefix="gc_scratch_", dir=out))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _step(tmp: pathlib.Path, programs: list[tuple[str, list[str]]], more=()):
    """a traced step: its Python read a file it did not write in its temporary folder, and ran PROGRAMS"""
    trace, scratch, work = tmp / "trace", tmp / "scratch", tmp / "work"
    for d in (trace, scratch, work, work / "logs"):
        d.mkdir(parents=True)
    made = scratch / "out.bin"                  # made by a program, read by the step's Python
    made.write_bytes(b"\x01\x02")
    lines = [["py", [sys.executable, sys.version]], ["scratch", [str(scratch)]], ["r", str(made)],
             ["d", str(scratch)]]
    lines += [["x", [exe, argv, str(tmp)]] for exe, argv in programs] + list(more)
    (trace / "trace-1.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    return GC.inputs(trace, work, work / "logs"), str(made), str(scratch)


def _tool(tmp: pathlib.Path, name: str) -> str:
    """a stand-in cross binutils program (not gcc: no gcc -M needed)"""
    p = tmp / "bin" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    return str(p)


def test_only_python_leaves_the_folder_out(tmp_path):
    ins, made, scratch = _step(tmp_path, [(sys.executable, [sys.executable, "-c", "pass"])])
    assert made not in ins and scratch not in ins


def test_an_unknown_program_keeps_the_folder_in(tmp_path):
    """the control: a program whose reads nothing accounts for (its output in the folder is the only witness)"""
    ins, made, scratch = _step(tmp_path, [("/bin/sh", ["/bin/sh", "-c", "true"])])
    assert ins.get(made, "").startswith("f:") and ins.get(scratch, "").startswith("d:")


def test_a_toolchain_program_puts_its_files_in(tmp_path):
    src = tmp_path / "input.elf"
    src.write_bytes(b"ELF")
    tool = _tool(tmp_path, "m68k-linux-gnu-objcopy")
    ins, made, _ = _step(tmp_path, [(tool, [tool, "-O", "binary", str(src), str(tmp_path / "scratch" / "x.bin")])])
    assert made not in ins
    assert ins[str(src)] == "f:" + GC._sha(str(src))
    assert ins[tool].startswith("x:")


def test_a_gone_input_keeps_the_folder_in(tmp_path):
    """the control: a file on a toolchain's command line, outside the folder, that has gone cannot be hashed"""
    tool = _tool(tmp_path, "m68k-linux-gnu-nm")
    ins, made, _ = _step(tmp_path, [(tool, [tool, "--defined-only", str(tmp_path / "gone" / "x.elf")])])
    assert ins.get(made, "").startswith("f:")


def test_an_output_is_not_an_input(tmp_path):
    tool = _tool(tmp_path, "m68k-linux-gnu-ld")
    out = tmp_path / "linked.elf"
    out.write_bytes(b"out")
    ins, made, _ = _step(tmp_path, [(tool, [tool, "-Ttext=0x4000", "-e", "0", str(tmp_path / "scratch" / "a.o"),
                                            "-o", str(out)])])
    assert made not in ins and str(out) not in ins
    assert os.path.join(str(tmp_path), "0") not in ins          # an option's value, not a file


def test_a_compile_puts_what_gcc_read_in(tmp_path):
    """the tracer's gcc -M account of a compile (["gd", [cwd, deps]]): each file in the record; a header the step
    wrote itself and has gone is accounted for; one that has gone and the step did not write is not (control)"""
    hdr = tmp_path / "csrc" / "x.h"
    hdr.parent.mkdir()
    hdr.write_text("#define X 1\n")
    gen = tmp_path / "gen" / "g.h"
    ins, made, _ = _step(tmp_path, [], [["gd", [str(tmp_path), [str(hdr)]]], ["w", str(gen)],
                                        ["gd", [str(tmp_path), [str(gen)]]]])
    assert made not in ins and ins[str(hdr)] == "f:" + GC._sha(str(hdr))
    assert ins[str(hdr.parent)].startswith("d:")              # the source's folder ("x.h" is looked up there)
    ins, made, _ = _step(tmp_path / "b", [], [["gd", [str(tmp_path), [str(tmp_path / "gone.h")]]]])
    assert ins.get(made, "").startswith("f:")


def test_a_compile_gcc_could_not_account_for_keeps_the_folder_in(tmp_path):
    ins, made, _ = _step(tmp_path, [], [["gd-fail", ["m68k-linux-gnu-gcc", "-c", "x.c"]]])
    assert ins.get(made, "").startswith("f:")


def test_native_code_the_step_built(tmp_path):
    """a library the step built and loaded, and a program it built and ran: accounted for when they call nothing
    that reads or finds a file (the tracer's nm check, ["native", [path, calls]]); the controls: one that calls
    fopen, one never checked, a library loaded but never checked"""
    scr = tmp_path / "scratch"
    lib, prog = str(scr / "lib.so"), str(scr / "prog")
    ins, made, _ = _step(tmp_path, [(prog, [prog])], [["dl", lib], ["native", [lib, []]], ["native", [prog, []]]])
    assert made not in ins
    ins, made, _ = _step(tmp_path / "b", [], [["dl", str(tmp_path / "b" / "scratch" / "lib.so")],
                                              ["native", [str(tmp_path / "b" / "scratch" / "lib.so"), ["fopen"]]]])
    assert ins.get(made, "").startswith("f:")
    ins, made, _ = _step(tmp_path / "c", [(str(tmp_path / "c" / "scratch" / "prog"), ["prog"])])
    assert ins.get(made, "").startswith("f:")
    ins, made, _ = _step(tmp_path / "d", [], [["dl", str(tmp_path / "d" / "scratch" / "lib.so")]])
    assert ins.get(made, "").startswith("f:")
