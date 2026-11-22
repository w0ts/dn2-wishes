"""Our machines and filters (the mod is still called `waverider`, its first machine).

**Since v0.11 machine type 5 is PERC** (docs/perc.md): the owner's 24 drum machines
(TRX, EFM, GND, from his Ravel firmware), one a track, chosen with TYPE; Waverider, the
wavetable machine that held type 5 until v0.10, is gone. Also: RESONATOR (type 6,
docs/rings.md), CZ (type 7, docs/cz.md), and the filters PING, SHFT and GRAN (types 6-8,
docs/ping.md, docs/shft.md, docs/gran.md), all since removed (PING last, in v0.45).

## How it applies

Two sections, both from committed data:

- **MAIN OS (3):** `waverider_code.json`, written by `scripts/gen_waverider_code.py`
  from `dnfw.waverider.coldfire` (the MACHINE SEL list, the names, the permission rows,
  the WaveTone clone, our SYN pages). Every edit's stock bytes are checked first; the
  pages, the machines' tables run from RAM as platform `CODE` chunks.
- **The DSP boot stream (7):** `dnfw.waverider.dsp.section7`, from the committed SHARC
  objects. It refuses a section 7 that is not stock.

## A sound or project saved with one of our machines

Saved as its machine type by the stock SAVE. This build keeps 5-7 on LOAD; stock
firmware (and any build without this mod) loads them as **FM Tone**, the stock LOAD
bound's own fallback (`0x400dd3ea`), with their parameters as they were. A sound saved
with Waverider (type 5) on v0.10 or earlier loads as PERC here, its WaveTone values
read as PERC's controls.
"""

from __future__ import annotations

import json
import struct
import pathlib

from . import RAM, Extent, ModError, Result, platform
from ..waverider import dsp

ID = "waverider"
NAME = "PERC, the sample machines and the Monomachine machines"
SUMMARY = ("PERC (the Machinedrum's machines), the Digitakt II sample machines and the Monomachine's "
           "machines in MACHINE SEL. Modified DSP code.")
DEVICE = 0x15                      # Digitone II
MAIN_OS, DSP_STREAM = 3, 7
BASE = 0x40000400
SPEC = json.loads((pathlib.Path(__file__).with_name("waverider_code.json")).read_text())


def _boot():
    """v0.37: the start-up animation (dnfw.bootanim, by s!Rwa²; v0.39: his own frames) through the boot-screen
    mod's stamp (scripts/gen_bootscreen_code.py, its ANIZ path): the intro hook's site and
    stock bytes, the stamp's CODE chunk, the ANIZ data chunk"""
    from . import bootscreen as B
    from .. import bootanim
    spec = B.SPEC
    return spec, bootanim.chunk()


def _label():
    """v0.39: the mod's version over the animation's last frame (dnfw.bootanim.label_chunk)"""
    from .. import bootanim
    return bootanim.LABEL_CHUNK, bootanim.label_chunk()


def extents(firmware=None, area_length: int = 0) -> list[Extent]:
    out = [Extent(MAIN_OS, e["va"] - BASE, len(e["new"]) // 2, e["what"]) for e in SPEC["edits"]]
    from . import bootscreen as B
    out.append(Extent(MAIN_OS, B.SPEC["intro_va"] - BASE, 8, "v0.37: the intro hook (the start-up animation)"))
    from . import midiarp as MA                 # v0.67: the arp on MIDI tracks
    out += [Extent(MAIN_OS, x.start, x.length, "v0.67 midiarp: " + x.what) for x in MA.extents()]
    out += platform.extents(area_length)
    size = None
    if firmware is not None:
        section = firmware.container.find(DSP_STREAM)
        content = section.unpack() if section is not None else None
        size = len(content) if content is not None else None
    # The boot stream is rebuilt as a whole (blocks inserted before its final
    # block), so the whole of it is declared: nothing else may write it too.
    out.append(Extent(DSP_STREAM, 0, size or 836_956,
                      "the DSP boot stream, rebuilt: our code and state in L1 block 1, "
                      "PERC's code in L2, tables in DDR, the entry jump, the machine lookup"))
    return out


def _chunks() -> list[tuple[int, bytes, str]]:
    out = [(SPEC["chunk"]["load"], bytes.fromhex(SPEC["chunk"]["code"]),
            "our machines' SYN pages: code, descriptors, labels")]
    if "c_chunk" in SPEC:
        out.append((SPEC["c_chunk"]["load"], bytes.fromhex(SPEC["c_chunk"]["code"]),
                    "our machines' page renderer (csrc/waverider/page.c)"))
    if "flt_chunk" in SPEC:                      # 2026-11-10: the A2 filter machines (dnfw.engines.analog2.filters.coldfire)
        out.append((SPEC["flt_chunk"]["load"], bytes.fromhex(SPEC["flt_chunk"]["code"]),
                    "the A2 filter machines' FLTR-list shims, list and names"))
    if "machines_chunk" in SPEC:
        out.append((SPEC["machines_chunk"]["load"], bytes.fromhex(SPEC["machines_chunk"]["code"]),
                    "the machine shims, names, attributes and MACHINE SEL list (PERC, RESONATOR, CZ)"))
    md = _md_ui()
    if md is not None:
        out.append(md)
    out.append(_tables())
    return out


def _tables() -> tuple[int, bytes, str]:
    """v0.26: the tables the ColdFire sends the DSP at power-on (csrc/sampler/link.c,
    K_TABLES): the Machinedrum's (and the Monomachine's) from the owner's own firmware
    files, read now (never committed): TABLE_MAGIC, the length, then the bytes."""
    import struct
    from ..md import core as md_core
    from ..sampler import machines as SM
    data = md_core.tables_bytes()
    if len(data) > SM.TABLE_ROOM - 512 or 8 + len(data) > SM.TABLE_RAM_MAX:   # v0.65.1: the banks' RAM follows
        raise ModError(f"the tables ({len(data):,} B) do not fit the DSP's table area")
    return (SM.TABLE_LOAD, struct.pack("<II", SM.TABLE_MAGIC, len(data)) + data,
            "the Machinedrum's and Monomachine's tables, sent to the DSP at power-on (v0.26)")


def _md_ui() -> tuple[int, bytes, str] | None:
    """v0.20: the Machinedrum's screen graphics for PERC's page (csrc/waverider/md_page.c),
    read from the owner's MD OS 1.63 now (dnfw.md.ui; never committed). Without it the page
    is drawn as before."""
    from ..md import rom as md_rom, ui as md_ui
    from ..waverider import pages
    if not md_rom.available():
        return None
    return (pages.MDUI_LOAD, md_ui.blob(),
            "the Machinedrum's knob, pointers, clip and fonts (read from your MD OS, v0.20)")


def ram() -> list[Extent]:
    from ..sampler import machines as SM
    from ..waverider import pages as PG
    from . import bootscreen as B
    return ([Extent(RAM, load, len(code), what) for load, code, what in _chunks()]
            + B.ram()
            + [Extent(RAM, SM.MIRROR, SM.MIRROR_BYTES,
                      "the sample link's mirror of the pool (csrc/sampler/link.c, v0.14)")]
            + [Extent(RAM, SM.BANK_RAM, SM.BANK_RAM_BYTES,
                      "PROJECT RAM banks B..D: their pages, their slots' RAM, the bank lists (v0.65)")]
            + [Extent(RAM, PG.METER_RAM, PG.METER_BYTES,
                      "the system meter's state: its counters and figures (csrc/meter)")]
            + [Extent(RAM, PG.WISH_RAM, PG.WISH_BYTES,
                      "the wishes record: the sounds' records, their index and the cells for the +Drive (csrc/wishes)")]
            + [Extent(RAM, PG.MX_RAM, PG.MX_BYTES,
                      "the matrix: each track's routes laid out for the audio frame (csrc/matrix)")]
            + [Extent(RAM, PG.MOD_RAM, PG.MOD_BYTES,
                      "modulation's state: the LFO cascade's shadow cells, the moving controls (csrc/modulation)")]
            + [Extent(RAM, PG.PROF_RAM, PG.PROF_BYTES,
                      "the CPU profiler's state and samples (csrc/devtest/prof.c), while PROFILE runs")]
            + _shared_ram())


# Bytes that only look like RAM above BSS (`dnfw.mods.ramcheck`), as arpplocks and lfowaves list theirs: at 0x400285c4,
# the PARA VOICE-menu hook `jsr <our C>` at 0x400285c0 (4e b9 46 a6 46 80 on the 2026-11-18 batch) and stock's next
# instruction `clr.l -(%sp)` (42 a7) straddle into 0x468042a7: the jsr target's low half and an opcode, never an address
# (a known false alarm: the User approved this entry 2026-11-18)
NOT_RAM = (0x400285C4,)


def word_spans() -> list[tuple[int, int, str]]:
    """For ramcheck (`not_addresses`, 2026-11-17): our C's text is code (gcc's, read by disassembly); the DSP's
    tables chunk (0x47000000, the Machinedrum's and Monomachine's) is opaque: sent to the DSP, no ColdFire pointer"""
    lay = SPEC.get("layout", {})
    out = [(lay["c_load"], lay["c_text_end"], "code")] if "c_text_end" in lay else []
    out += [(lo, hi, "opaque") for lo, hi in lay.get("c_number_tables", ())]      # the header's number tables
    out += [(p, p + 4, "pointer") for p in lay.get("c_pointer_sites", ())]      # ... and its relocated pointers
    return out + [(load, load + len(code), "opaque") for load, code, what in _chunks()
                  if "sent to the DSP" in what]


def _shared_ram() -> list[Extent]:
    """RAM other mods place and our code names (2026-11-17, test_mods_ramcheck): lfowaves' runtime (our pages read
    its names and tables: lea 0x467804b4 ..), and with DN2_LFO4 lfo4's LFO state arrays and chunks (our modulation,
    matrix and wishes code read and write them). Declared here too, so what this build names is what it declares"""
    from ..waverider import pages as PG
    from . import lfo4, lfowaves
    # each keeps its mod as owner: the same range declared twice by design, never a conflict between the two
    out = [Extent(RAM, e.start, e.length, f"lfowaves': {e.what}", owner=e.owner) for e in lfowaves.ram()[:1]]
    if PG.lfo4_on():
        out += [Extent(RAM, e.start, e.length, f"lfo4's: {e.what}", owner=e.owner) for e in lfo4.ram()]
    return out


def _main_os(original: bytes) -> bytes:
    if len(original) < SPEC["stock_length"]:
        raise ModError(f"MAIN OS is {len(original):,} B, shorter than "
                       f"{SPEC['stock_length']:,}: not Digitone II 1.12")
    for g in SPEC["guards"]:
        want = bytes.fromhex(g["bytes"])
        at = g["va"] - BASE
        if original[at:at + len(want)] != want:
            raise ModError(f"0x{g['va']:08x} ({g['what']}) is not stock; this mod is "
                           "for unmodified Digitone II 1.12")
    content = bytearray(original)
    for e in SPEC["edits"]:
        old, new = bytes.fromhex(e["stock"]), bytes.fromhex(e["new"])
        at = e["va"] - BASE
        if bytes(content[at:at + len(old)]) != old:
            raise ModError(f"0x{e['va']:08x} ({e['what']}) is not stock; this mod is for "
                           "unmodified Digitone II 1.12, or another mod already wrote there")
        content[at:at + len(new)] = new
    return bytes(content)


def apply(firmware) -> Result:
    cf = firmware.container.find(MAIN_OS)
    ds = firmware.container.find(DSP_STREAM)
    if cf is None or ds is None:
        raise ModError("image has no MAIN OS or no DSP boot stream")
    main_os, stream = cf.unpack(), ds.unpack()
    if main_os is None or stream is None:
        raise ModError("MAIN OS or the DSP boot stream did not depack")
    main_os, others = platform.split(main_os)
    try:
        section7 = dsp.section7(stream)
    except dsp.DspError as exc:
        raise ModError(f"the DSP boot stream: {exc}") from exc
    codes = [(platform.area.CODE, platform.area.CodeChunk(load, code).pack())
             for load, code, _ in _chunks()]
    # v0.37: the start-up animation: the intro routine's first 8 bytes jump to the stamp
    bspec, aniz = _boot()
    base_os = bytearray(_main_os(main_os))
    at, stock = bspec["intro_va"] - BASE, bytes.fromhex(bspec["intro_stock"])
    if bytes(base_os[at:at + 8]) != stock:
        raise ModError(f"0x{bspec['intro_va']:08x} (the intro routine) is not stock; this mod is "
                       "for unmodified Digitone II 1.12")
    base_os[at:at + 8] = b"\x4e\xf9" + struct.pack(">I", bspec["stamp"]) + b"\x4e\x71"
    # v0.67 (owner, 2026-11-20: "just arp on midi tracks"): the midiarp mod (upstream's, Angel Linares's
    # dn2_firmware_explore; tested on his unit 2026-09-17 as arp-midi-play4), its sites checked stock in this image first
    from . import midiarp as MA
    MA.check(bytes(base_os))
    MA.write(base_os, main_os)
    codes += [(platform.area.CODE, platform.area.CodeChunk(bspec["load"], bytes.fromhex(bspec["code"])).pack()),
              (bspec["aniz_chunk"].encode(), aniz), _label()]
    content = platform.join(bytes(base_os), others + codes)
    area_length = len(content) - platform.STOCK_LENGTH
    # 2026-11-11 (docs/lzma7.md): section 7 stored as LZMA, decoded by the uploader's dn_depack7
    return Result(payloads={MAIN_OS: content, DSP_STREAM: section7}, codecs={DSP_STREAM: "lzma7"},
                  extents=extents(firmware, area_length),
                  notes=[f"MACHINE SEL offers {SPEC['names'][0].upper()} after SWARMER "
                         f"(type {SPEC['new_type']}; WaveTone's pages)",
                         f"{len(SPEC['edits'])} edits in section 3, nothing appended; "
                         f"section 7 {len(stream):,} -> {len(section7):,} B"])
