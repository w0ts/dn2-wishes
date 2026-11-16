"""dnfw.waverider.dsp / live / harmonics: Milestone 5's section-7 builder and its contract.

The runner gate is scripts/sharc_waverider_m5.py; these need no runner, no WSL and
no firmware beyond the DN2 1.11 image (skipped cleanly when it is absent).
"""

from __future__ import annotations

import cmath
import hashlib
import json
import math
import pathlib
import struct

import pytest

from dnfw.image import bootstream, sharc_object
from dnfw.waverider import dsp

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE = ROOT / "00_Resources" / "00_Firmware" / "Digitone_II_OS1.11_dist.zip"
SHARC = ROOT / "csrc" / "waverider" / "sharc"


@pytest.fixture(scope="module")
def stock7() -> bytes:
    if not IMAGE.exists():
        pytest.skip(f"{IMAGE.name} not present")
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    sec = load(read_image(IMAGE)).container.find(7)
    return sec.unpack() or sec.raw_payload


@pytest.fixture(scope="module")
def built(stock7) -> bytes:
    return dsp.section7(stock7)


# -- the committed objects -----------------------------------------------------------------

def test_committed_objects_match_their_sources():
    spec = json.loads(dsp.CODE.read_text(encoding="utf-8"))
    for key, name in (("perc", "perc"), ("idle_load", "idle_load"), ("block_count", "block_count"),
                      ("entry_mark", "entry_mark"), ("ping", "ping")):   # (v0.26: RESONATOR and CZ gone; v0.27: GRAN)
        src = (SHARC / f"{name}.asm").read_bytes().replace(b"\r\n", b"\n")
        assert spec[key]["source_sha256"] == hashlib.sha256(src).hexdigest(), name
        csrc = json.loads((SHARC / f"{name}.json").read_text(encoding="utf-8"))
        assert csrc["object_parcels_be"] == spec[key]["object_parcels_be"], name
    assert spec["entry_jump"]["source"] == "JUMP 0x16f600;"
    assert spec["idle_jump"]["source"] == "JUMP 0x16f500;" and spec["idle_jump"]["at_sw"] == "0xb88abb"


def test_our_sources_avoid_dag1_m0_m3_in_memory_accesses():
    """No DM(..M0..M3..) access and no pre-modify read outside a DO loop (the two
    forms selas and selmap disagree on; docs/waverider-m5-dsp.md)."""
    import re
    for name in ("perc", "idle_load", "block_count", "entry_mark"):
        in_loop = False
        for line in (SHARC / f"{name}.asm").read_text().splitlines():
            code = line.split("//", 1)[0].strip().upper()
            if "DO " in code and "UNTIL" in code:
                in_loop = True
            assert not re.search(r"DM\s*\([^)]*\bM[0-3]\b", code), (name, line)
            # the one exception is the firmware's own return idiom, byte for byte
            # its `i12=dm(m7,i6)` (3b fe4d3f0e)
            if re.search(r"DM\s*\(\s*M\d+\s*,", code) and code != "I12 = DM(M7, I6);":
                assert in_loop, (name, line)
            if code.startswith(".WR5_LOOP_END"):
                in_loop = False


# -- the builder ------------------------------------------------------------------------------

def test_refuses_anything_but_stock(stock7):
    with pytest.raises(dsp.DspError):
        dsp.section7(stock7[:100] + bytes([stock7[100] ^ 1]) + stock7[101:])


def test_is_deterministic_and_walks(stock7, built):
    assert dsp.section7(stock7) == built
    w = bootstream.walk(built)
    assert w.complete and w.stopped_at == len(built)


def test_every_added_span_is_in_block_1s_free_tail_and_outside_every_stock_block(stock7):
    # Milestone 5c: M5's L1 block 2 silenced the instrument (docs/waverider-dsp-silence.md)
    stock_blocks = [b for b in bootstream.walk(stock7).blocks if b.count]
    for what, at, payload in dsp.spans():
        lo, hi = at - dsp.LOAD_ALIAS, at - dsp.LOAD_ALIAS + len(payload)
        assert 0x2DD52C <= lo and hi <= 0x2E8000, what          # above stock, below a 32 KB DM cache
        assert not (0x300000 <= lo < 0x320000), what            # nothing left in block 2
        for b in stock_blocks:
            assert not (b.target < at + len(payload) and at < b.target + b.count), what


def test_loaded_image_holds_our_bytes(built):
    for what, at, payload in dsp.spans():
        assert bootstream.read_span(built, at, len(payload)) == payload, what


def test_the_five_patches_and_nothing_else_in_the_stock_blocks(stock7, built):
    entry = bootstream.read_span(built, dsp.sw_to_load(dsp.ENTRY_SW), 8)
    assert entry == bytes.fromhex("3e06160000f60100")          # jump 0x16f600 (the block counter) ; nop
    # v0.13: the stock 8-entry lookup stays stock; its base pointer (sw 0x1c2958) moves to
    # a 16-entry copy with the same [-1] guard
    assert struct.unpack("<8I", bootstream.read_span(built, dsp.dm_to_load(dsp.LOOKUP_DM), 32)) == dsp.LOOKUP_STOCK
    n = dsp.MACHINE_TYPES                                        # 16 (v0.26: 17 with a type 16)
    lookup = struct.unpack(f"<{n + 1}I", bootstream.read_span(built, dsp.dm_to_load(dsp.LOOKUP16_DM - 4), 4 * n + 4))
    assert lookup[0] == struct.unpack("<I", bootstream.read_span(stock7, dsp.dm_to_load(dsp.LOOKUP_DM - 4), 4))[0] == 0
    assert lookup[1:7] == (0, 1, 2, 3, 4, 5)
    # the sample machines (8..13) and the Monomachine's (6, 7, 14..) borrow PERC's engine
    # slot; nothing reads past slot 7
    assert dsp.SMP_ENGINE_SLOT == 5
    assert all(lookup[1 + t] == 5 for t in (*dsp.SMP_TYPES, *dsp.MNM_TYPES))
    # 2026-11-08: a removed machine's reserved type reads the MIDI machine's slot (silent; lookup16)
    assert all(lookup[1 + t] == dsp.MIDI_ENGINE_SLOT for t in dsp.RESERVED_TYPES)
    assert all(v in (0, k) for k, v in enumerate(lookup[1:])
               if k not in dsp.SMP_TYPES and k not in dsp.MNM_TYPES and k not in dsp.RESERVED_TYPES) and max(lookup) <= 7
    assert bootstream.read_span(built, dsp.sw_to_load(dsp.LOOKUP_SITE_SW), 6) == dsp.objects()["lookup_ptr"]
    # the idle loop's back edge, jump (pc,-0x10) at sw 0xb88abb in L2, becomes JUMP 0x16f500
    site = dsp.l2_sw_to_load(dsp.IDLE_SITE_SW)
    assert bootstream.read_span(stock7, site, 6) == bytes.fromhex("3e07ff00f0ff")
    assert bootstream.read_span(built, site, 6) == bytes.fromhex("3e061600" "00f5")
    # the handler's call of the per-block routine: r4 = 0x268438 becomes JUMP 0x16f680
    call = dsp.sw_to_load(dsp.CALL_SITE_SW)
    assert bootstream.read_span(stock7, call, 6) == dsp.CALL_SITE_STOCK
    assert bootstream.read_span(built, call, 6) == dsp.objects()["emark_jump"]
    # the clamp min(R2, 4) stays stock: its R0 = 0x4 parcel pair at sw 0x1c294a
    clamp = dsp.sw_to_load(0x1C294A)
    assert bootstream.read_span(built, clamp, 4) == bootstream.read_span(stock7, clamp, 4) \
        == bytes.fromhex("800f0400")
    # the per-type setup table is not touched
    assert bootstream.read_span(built, 0x8052DB90, 24) == bootstream.read_span(stock7, 0x8052DB90, 24)
    # every stock block's payload differs from stock only at the two patches
    final = bootstream.walk(stock7).final
    head = built[:final.offset]
    diff = [k for k in range(final.offset) if head[k] != stock7[k]]
    entry_off = bootstream.spans(stock7, dsp.sw_to_load(dsp.ENTRY_SW), 8)[0][0]
    look_off = bootstream.spans(stock7, dsp.sw_to_load(dsp.LOOKUP_SITE_SW), 6)[0][0]
    idle_off = bootstream.spans(stock7, dsp.l2_sw_to_load(dsp.IDLE_SITE_SW), 6)[0][0]
    call_off = bootstream.spans(stock7, dsp.sw_to_load(dsp.CALL_SITE_SW), 6)[0][0]
    # v0.25: the driver's call of 0x1c9d3f becomes JUMP wr_pvmix (its two delay slots stay)
    pv = dsp.sw_to_load(dsp.PVMIX_SITE_SW)
    assert bootstream.read_span(stock7, pv, 18) == dsp.PVMIX_SITE_STOCK
    assert bootstream.read_span(built, pv, 18) == dsp.objects()["pvmix_jump"] + dsp.PVMIX_SITE_STOCK[6:]
    pv_off = bootstream.spans(stock7, pv, 6)[0][0]
    # FDN8 and XDLY: the FX bus's reverb CJUMP and delay CALL, each with only its target changed
    rv, dl = dsp.sw_to_load(dsp.REVERB_SITE_SW), dsp.sw_to_load(dsp.DELAY_SITE_SW)
    assert bootstream.read_span(stock7, rv, 6) == dsp.REVERB_SITE_STOCK
    assert bootstream.read_span(built, rv, 6) == dsp.reverb_cjump()
    assert bootstream.read_span(stock7, dl, 6) == dsp.DELAY_SITE_STOCK
    assert bootstream.read_span(built, dl, 6) == dsp.delay_call()
    rv_off, dl_off = bootstream.spans(stock7, rv, 6)[0][0], bootstream.spans(stock7, dl, 6)[0][0]
    # CHOR/WIDE (b6): the engine's CJUMP to the FX sends, its target wr_inpost
    sn = dsp.sw_to_load(dsp.SENDS_SITE_SW)
    assert bootstream.read_span(stock7, sn, 6) == dsp.SENDS_SITE_STOCK
    assert bootstream.read_span(built, sn, 6) == dsp.sends_cjump()
    sn_off = bootstream.spans(stock7, sn, 6)[0][0]
    # the chorus send's TYPE JUNO (2026-11-12): the FX bus's CALL of the stock chorus, its target wr_jsend
    ch = dsp.sw_to_load(dsp.CHORUS_SITE_SW)
    assert bootstream.read_span(stock7, ch, 6) == dsp.CHORUS_SITE_STOCK
    assert bootstream.read_span(built, ch, 6) == dsp.chorus_call()
    ch_off = bootstream.spans(stock7, ch, 6)[0][0]
    allowed = (set(range(entry_off, entry_off + 8)) | set(range(look_off, look_off + 6))
               | set(range(idle_off, idle_off + 6)) | set(range(call_off, call_off + 6))
               | set(range(pv_off, pv_off + 6)) | set(range(rv_off, rv_off + 6)) | set(range(dl_off, dl_off + 6))
               | set(range(sn_off, sn_off + 6)) | set(range(ch_off, ch_off + 6)))
    assert diff and set(diff) <= allowed


def test_ddr_spans_are_clear_of_the_stock_image_and_the_engine():
    from dnfw.md import core as MDK
    ddr = dsp.ddr_spans()
    # the Monomachine's scratch and state (zeros; v0.26: RESONATOR's and CZ's state and
    # tables went), PING's and PERC's tables (v0.27: SHFT's and GRAN's, GRAN's buffers went);
    # Waverider's wavetables went in v0.11. v0.26: the Machinedrum's shipped tables (the
    # host's pitch table, zpack) are not in the image: the ColdFire sends them at power-on.
    # v0.45: PING's tables went with PING
    # 2026-11-10 (shrink): AMD's sine (v0.31) ships over the link now, with PERC's tan
    # 2026-11-12: the DT2 reader's coefficients (v0.18) went to L2 and L1
    assert [a for _, a, _ in ddr] == [dsp.PERC_TABLES_DDR,
                                      dsp.MD_TABLES_DDR,
                                      dsp.MD_DELAY_DDR,                         # v0.32: P-I's lines, zeroed
                                      dsp.FDN8_RING_DDR,                        # FDN8's ring, zeroed
                                      0x82500000,                               # the inserts' TAPE rings, zeroed
                                      0x82510000,                               # the post inserts' rings, zeroed
                                      0x82550000,                               # the chorus send's JUNO: words, ring
                                      dsp.SMP_POOL_DDR, dsp.SMP_POOL_DDR + 8]   # v0.17: the MD's
    assert not any(ddr[-1][2])
    # v0.45: PING's tables went: every index one lower than b4's; 2026-11-10: the sine's, one more;
    # 2026-11-12: the DT2 reader's coefficients, one more
    assert not any(ddr[3][2]) and len(ddr[3][2]) == dsp.FDN8_RING_BYTES       # FDN8: zeros at power-on
    assert dsp.MD_DELAY_DDR + len(ddr[2][2]) <= dsp.FDN8_RING_DDR
    assert dsp.FDN8_RING_DDR + 0x80000 <= 0x82500000                         # (FDN8 LONG's 512 KB too)
    assert not any(ddr[4][2]) and 0x82500000 + len(ddr[4][2]) <= 0x82510000
    from dnfw.mnm import plk                                              # PLAITS' per-voice DDR
    assert not any(ddr[5][2]) and 0x82510000 + len(ddr[5][2]) <= plk.BIG_DDR <= dsp.SMP_POOL_DDR
    assert not any(ddr[1][2]) and not any(ddr[2][2])      # the MD's tables (the DSP fills them), P-I's lines
    assert dsp.MD_TABLES_DDR + len(ddr[1][2]) <= dsp.MD_DELAY_DDR
    # v0.32: the voices' working state in L2 (zeros), inside the room proven on units
    from dnfw.perc import live as PL
    L = PL.layout()
    l2 = {a: p for _, a, p in dsp.l2_spans()}
    assert L.md.state == dsp.MD_STATE_DM and L.md.mnm.scratch == dsp.MNM_SCRATCH_L2
    assert L.md.delay == dsp.MD_DELAY_DDR                 # not state + 1 MB: L2 has no room for it
    l1 = {a: p for _, a, p in dsp.spans()}                # 2026-11-10: the slots in L1 block 1 (zeros)
    at = dsp.dm_to_load(dsp.MD_STATE_DM)
    assert not any(l1[at]) and len(l1[at]) >= 16 * MDK.MD_STRIDE
    assert dsp.MD_STATE_DM + 16 * MDK.MD_STRIDE <= dsp.REGION[1] <= dsp.DM_CACHE_16K - 0x1000
    # 2026-11-11: zeros but for ANALOG2's filter mix tables (dsp._mnm_scratch, 2026-11-09), exactly those floats
    scratch = bytearray(l2[dsp.MNM_SCRATCH_L2])
    from dnfw.mnm import machines as MMx
    if "ANALOG2" in MMx.NAMES:
        import struct as _st
        from dnfw.mnm import analog2 as A2
        words = A2.table_words()
        n = 4 * len(words)
        assert bytes(scratch[A2.TABLES_OFF:A2.TABLES_OFF + n]) == _st.pack(f"<{len(words)}f", *words)
        scratch[A2.TABLES_OFF:A2.TABLES_OFF + n] = bytes(n)
    assert not any(scratch) and dsp.MD_STATE_L2 + 16 * MDK.MD_STRIDE <= dsp.MNM_SCRATCH_L2
    assert 0x20088400 <= dsp.MD_STATE_L2 and dsp.MNM_SCRATCH_L2 + dsp.MNM_SCRATCH_BYTES <= 0x200B0000
    # v0.43: the Monomachine render scratch in L1, after GRAN's state, inside the region (zeros
    # at boot: the region's tail is padding), its bookkeeping still in L2
    from dnfw.mnm import core as MNC
    m = L.md.mnm
    assert m.render == dsp.MNM_RENDER_DM and m.IN == dsp.MNM_RENDER_DM and m.scratch == dsp.MNM_SCRATCH_L2
    assert dsp.GRAN_STATE_DM + 16 * dsp.GRAN_STATE_STRIDE <= dsp.MNM_RENDER_DM
    assert MNC.RENDER_BYTES <= dsp.MNM_RENDER_BYTES and dsp.MNM_RENDER_DM + dsp.MNM_RENDER_BYTES <= dsp.REGION[1]
    assert all(dsp.MNM_RENDER_DM <= a < dsp.MNM_RENDER_DM + MNC.RENDER_BYTES
               for a in (m.IN, m.XB, m.YB, m.COEF, m.BUF, m.MIX, m.W1, m.W2, *m.W.values(), *m.DG.values()))
    tail = [(a, len(pl)) for _, a, pl in dsp.spans()]
    assert any(a <= dsp.dm_to_load(dsp.MNM_RENDER_DM) and dsp.dm_to_load(dsp.MNM_RENDER_DM + dsp.MNM_RENDER_BYTES) <= a + n
               for a, n in tail)
    # v0.17: the sample pool's directory begins with its magic, and holds nothing (the
    # +Drive's samples are loaded in; the test sounds are gone)
    assert struct.unpack_from("<II", ddr[-2][2]) == (0x31504D53, 0)
    # the stock stream loads DDR to 0x8052fbe0 and init writes up to 0x80530be8
    # (scripts/sharc_ddr_ceiling.py); ours start 16 MB in
    assert min(a for _, a, _ in ddr) >= dsp.DDR_FLOOR > 0x80530BE8


def test_the_sample_machines_scratch_fits_its_span():
    # 2026-11-12: 65 words had grown into a 256 B span, the last ('segnext') on the recorder's
    # staging block's first word
    from dnfw.sampler import live as SLv
    from dnfw.sampler import machines as SMm
    from dnfw.sampler import program as SP
    C = SLv.layout().C
    assert min(C.values()) == dsp.SMP_SCRATCH_DM and len(set(C.values())) == len(SP.SC_WORDS)
    assert max(C.values()) + 4 <= dsp.SMP_SCRATCH_DM + dsp.SMP_SCRATCH_BYTES == dsp.SMP_STAGE_DM == SMm.REC_STAGE
    l1 = {a: len(p) for _, a, p in dsp.spans()}
    assert l1[dsp.dm_to_load(dsp.SMP_SCRATCH_DM)] == dsp.SMP_SCRATCH_BYTES
    # v0.52 merge: the recorder's GAIN (v0.50, 0x2e0080) moved into this span: SMP_DTAB_DM has that room
    assert SMm.REC_GAIN == dsp.REC_GAIN_DM == C["rgain"] and C["rgfac"] == SMm.REC_GAIN + 4


def test_the_sample_readers_coefficients_are_loaded_where_it_reads_them():
    # 2026-11-12: the interpolator's rows in L2 (the Machinedrum slots' old room, inside the range
    # proven on units), the decimator's four and the gain in L1 after the voices' decimators
    from dnfw.sampler import live as SLv
    from dnfw.sampler import program as SP
    L, tb = SLv.layout(), SP.tables_bytes()
    assert L.T["poly"] == dsp.SMP_TABLES_L2 and L.T["decim"] == dsp.SMP_DTAB_DM and L.T["gain"] == dsp.SMP_DTAB_DM + 16
    l2 = {a: p for _, a, p in dsp.l2_spans()}
    assert l2[dsp.SMP_TABLES_L2] == tb[:SP.POLY_BYTES]
    assert 0x20088400 <= dsp.SMP_TABLES_L2 and dsp.SMP_TABLES_L2 + SP.POLY_BYTES <= dsp.MNM_SCRATCH_L2
    l1 = {a: p for _, a, p in dsp.spans()}
    dec = l1[dsp.dm_to_load(dsp.SMP_DEC_DM)]
    off = dsp.SMP_DTAB_DM - dsp.SMP_DEC_DM
    assert not any(dec[:off]) and dec[off:off + SP.DTAB_BYTES] == tb[SP.POLY_BYTES:]
    assert not any(dec[off + SP.DTAB_BYTES:])               # RELATCH's words: zeros at power-on
    assert dsp.SMP_DTAB_DM + SP.DTAB_BYTES <= dsp.SMP_LINE_DM - 8                   # the line's switch, its tag
    assert L.line == dsp.SMP_LINE_DM and dsp.SMP_LINE_DM + 4 * SP.LINE_WORDS <= SP.RELATCH


def test_perc_code_is_in_l2_above_the_stock_image_and_below_the_uncached_window(stock7, built):
    # scripts/sharc_l2_ceiling.py (2026-10-20, a fresh engine init and every stock machine):
    # nothing reads or writes L2 above the image's end, 0x2008823c
    # v0.13: the sample machines' code follows PERC's span
    spans = dsp.l2_spans()
    names = ("perc", *dsp.PERC_SPANS, "smp")     # 2026-11-12 (perc-layout): PERC's event code in its own spans
    data = spans[len(names):]                    # v0.32: the voices' state, zeros, below the code
    spans = spans[:len(names)]
    assert [(at, len(pl)) for _, at, pl in spans] == [(dsp.PERC_L2_LOAD, dsp.PERC_L2_SPAN),
                                                      *((a, sp) for a, sp, _sw in dsp.PERC_SPANS.values()),
                                                      (dsp.SMP_L2_LOAD, dsp.SMP_L2_SPAN)]
    for _w, at, payload in data:
        assert dsp.L2_IMAGE_END + 0x10000 <= at and at + len(payload) <= dsp.PERC_L2_LOAD
        assert not (at < dsp.SMP_L2_LOAD + dsp.SMP_L2_SPAN and dsp.SMP_L2_LOAD < at + len(payload))
        assert bootstream.read_span(built, at, len(payload)) == payload
    # 2026-11-09: the sample machines' code below PERC's, after FDN8's (until then after PERC's span)
    assert dsp.FDN8_L2_LOAD + dsp.FDN8_L2_SPAN <= dsp.SMP_L2_LOAD
    assert dsp.SMP_L2_LOAD + dsp.SMP_L2_SPAN <= dsp.PERC_L2_LOAD
    for (what, at, payload), name in zip(spans, names):
        code = dsp.objects()[name]
        if name == "smp":                        # v0.25: wr_pvmix in the span's last 1 KB
            pv, room = dsp.pvmix_object(), dsp.PVMIX_L2_LOAD - at
            assert payload[room:room + len(pv)] == pv and not any(payload[room + len(pv):])
            assert len(payload) - room - len(pv) >= 64
            payload_code = payload[:room]
        else:
            payload_code = payload
        assert payload_code[:len(code)] == code and not any(payload_code[len(code):])
        assert len(payload_code) - len(code) >= 64
        assert dsp.L2_IMAGE_END + 0x10000 <= at and at + len(payload) <= dsp.L2_NOCACHE - 0x10000
        assert bootstream.read_span(built, at, len(payload)) == payload
    for b in bootstream.walk(stock7).blocks:
        if b.count and 0x20000000 <= b.target < 0x20100000:
            assert b.target + b.count <= dsp.L2_IMAGE_END
    assert dsp.PERC_SW == 0xBDF100 and dsp.l2_sw_to_load(dsp.PERC_SW) == dsp.PERC_L2_LOAD
    assert dsp.SMP_SW == 0xBDB000 and dsp.l2_sw_to_load(dsp.SMP_SW) == dsp.SMP_L2_LOAD
    assert {n: sw for n, (_a, _s, sw) in dsp.PERC_SPANS.items()} == {"perc2a": 0xBCDA00, "perc2b": 0xBD1400}
    for _n, (a, _s, sw) in dsp.PERC_SPANS.items():
        assert dsp.l2_sw_to_load(sw) == a


def test_the_region_is_written_end_to_end_and_code_is_nop_padded():
    sp = dsp.spans()
    at = [a - dsp.LOAD_ALIAS for _, a, _ in sp]
    ends = [a - dsp.LOAD_ALIAS + len(p) for _, a, p in sp]
    assert at[0] == dsp.REGION[0] and ends[-1] == dsp.REGION[1]
    assert all(e == a for e, a in zip(ends, at[1:]))           # no unwritten gap
    obj = dsp.objects()
    code_spans = [x for x in sp if "asm" in x[0]]
    assert len(code_spans) == 5       # (2026-11-10: + trackbuf.asm)  # (the type lookup is data, not code; v0.26: RESONATOR, CZ gone; v0.27: GRAN)
    # v0.11: Waverider's reader, loop and osc 2 are gone (their room is zeros); PERC is in L2
    for (what, _, payload), code in zip(code_spans, (obj["idle_load"], obj["block_count"], obj["entry_mark"],
                                                     obj["ping"], obj["trackbuf"])):
        assert payload[:len(code)] == code
        assert len(payload) - len(code) >= 64 and not any(payload[len(code):]), what


def test_the_idle_only_stream_is_stock_but_the_stub(stock7):
    """section7_idle_only: the stock engine with the idle stub and nothing of Waverider."""
    built = dsp.section7_idle_only(stock7)
    w = bootstream.walk(built)
    assert w.complete and w.stopped_at == len(built)
    site = dsp.l2_sw_to_load(dsp.IDLE_SITE_SW)
    assert bootstream.read_span(built, site, 6) == bytes.fromhex("3e061600" "00f5")
    # idle-only: the handler's call of the per-block routine stays stock
    assert bootstream.read_span(built, dsp.sw_to_load(dsp.CALL_SITE_SW), 6) == dsp.CALL_SITE_STOCK
    code = dsp.objects()["idle_load"]
    assert bootstream.read_span(built, dsp.dm_to_load(dsp.IDLE_DM), len(code)) == code
    assert bootstream.read_span(built, dsp.dm_to_load(dsp.IDLE_STATE_DM), 0x20) == bytes(0x20)
    # none of Waverider: the entry and the lookup stay stock
    assert bootstream.read_span(built, dsp.sw_to_load(dsp.ENTRY_SW), 8) == dsp.ENTRY_STOCK
    lookup = struct.unpack("<8I", bootstream.read_span(built, dsp.dm_to_load(dsp.LOOKUP_DM), 32))
    assert lookup == dsp.LOOKUP_STOCK
    final = bootstream.walk(stock7).final
    diff = [k for k in range(final.offset) if built[k] != stock7[k]]
    idle_off = bootstream.spans(stock7, site, 6)[0][0]
    assert diff and set(diff) <= set(range(idle_off, idle_off + 6))


def test_the_idle_stub_is_placed_and_returns_where_its_source_says():
    """idle_load.asm: its skip lands on wr_idle_out, it returns to the idle loop's top,
    and its variables sit in the state block's free tail, clear of the render loop's."""
    spec = json.loads((SHARC / "idle_load.json").read_text(encoding="utf-8"))
    assert int(spec["load_sw"], 16) == dsp.IDLE_SW == 0x16F500
    be = bytes.fromhex(spec["object_parcels_be"])
    offs = spec["instruction_offsets"]
    src = [ln.split("//", 1)[0].strip() for ln in (SHARC / "idle_load.asm").read_text().splitlines()]
    src = [c for c in src if c and not c.startswith(".") and not c.endswith(":")]
    at = {c: dsp.IDLE_SW + o // 2 for c, o in zip(src, offs)}
    assert at["R8 = DM(0x2de100);"] == 0x16F57B                   # wr_idle_out.
    assert at["R8 = DM(0x2de10c);"] == 0x16F55A                   # wr_idle_after.
    assert be[offs[src.index("IF GE JUMP 0x16f53d;")]:][:6].hex() == "06220016f53d"
    assert at["R11 = DM(0x2de13c);"] == 0x16F53D                  # wr_idle_busy.
    assert be[offs[-1]:].hex() == "063e00b88aab" and dsp.IDLE_RETURN_SW == 0xB88AAB
    # its DM: 0x2de100..0x2de13f, inside the state block, after PERC's scratch, before PERC's state
    from dnfw.perc import machines as PM
    assert dsp.PERC_SCRATCH_DM + 4 * len(PM.SC_WORDS) <= dsp.IDLE_STATE_DM
    # v0.52 merge: the guard's insert words below its block (perc.guard.INS_LO) lie after PERC's scratch
    from dnfw.perc import guard as PG
    assert dsp.PERC_SCRATCH_DM + 4 * len(PM.SC_WORDS) <= PG.INS_LO < PG.INS_LO_END <= PG.GUARD
    assert dsp.IDLE_STATE_DM + dsp.IDLE_STATE_BYTES <= dsp.STATE_DM + dsp.STATE_BYTES == dsp.PERC_STATE_DM
    stores = {c for c in src if c.startswith("DM(")}
    assert stores <= {"DM(0x2de100) = R8;", "DM(0x2de104) = R9;", "DM(0x2de108) = R10;", "DM(0x2de134) = R11;",
                      "DM(0x2de114) = R9;", "DM(0x2de10c) = R8;", "DM(0x2de110) = R9;",
                      "DM(0x2de128) = R9;", "DM(0x2de12c) = R9;",
                      "DM(0x2c49d4) = R9;", "DM(0x2c59d4) = R9;", "DM(0x2c49dc) = R9;", "DM(0x2c59dc) = R9;",
                      "DM(0x2c49e0) = R9;", "DM(0x2c59e0) = R9;"}


def test_the_block_counter_goes_on_to_perc():
    spec = json.loads((SHARC / "block_count.json").read_text(encoding="utf-8"))
    assert int(spec["load_sw"], 16) == dsp.COUNT_SW == 0x16F600
    be = bytes.fromhex(spec["object_parcels_be"])
    assert be[spec["instruction_offsets"][-1]:].hex() == "063e00bdf100"   # JUMP 0xbdf100, PERC in L2 (v0.11; 0xbe0000 until 2026-11-12)
    src = [ln.split("//", 1)[0].strip() for ln in (SHARC / "block_count.asm").read_text().splitlines()]
    stores = {c for c in src if c.startswith("DM(")}
    assert stores == {"DM(0x2de11c) = R8;", "DM(0x2de120) = R9;", "DM(0x2de118) = R8;",
                      "DM(0x2c49d8) = R8;", "DM(0x2c59d8) = R8;", "DM(0x2de124) = R8;"}
    assert dsp.IDLE_STATE_DM + dsp.IDLE_STATE_BYTES >= 0x2DE124 and dsp.IDLE_STATE_DM + dsp.IDLE_STATE_BYTES <= dsp.PERC_STATE_DM


def test_the_entry_mark_does_the_displaced_load_and_returns_to_the_call():
    spec = json.loads((SHARC / "entry_mark.json").read_text(encoding="utf-8"))
    assert int(spec["load_sw"], 16) == dsp.EMARK_SW == 0x16F680
    be = bytes.fromhex(spec["object_parcels_be"])
    offs = spec["instruction_offsets"]
    assert be[offs[-1]:].hex() == "063e001c9fbc"                    # JUMP 0x1c9fbc, the cjump
    assert sharc_object.load_bytes(be[offs[-2]:offs[-1]]) == dsp.CALL_SITE_STOCK  # r4 = 0x268438, as stock
    src = [ln.split("//", 1)[0].strip() for ln in (SHARC / "entry_mark.asm").read_text().splitlines()]
    assert {c for c in src if c.startswith("DM(")} == {"DM(0x2de138) = R9;", "DM(0x2de13c) = R9;"}
    assert dsp.IDLE_STATE_DM + dsp.IDLE_STATE_BYTES >= 0x2DE140


def _code_lines(name):
    lines = [ln.split("//", 1)[0].strip() for ln in (SHARC / f"{name}.asm").read_text().splitlines()]
    return [ln for ln in lines if ln and not ln.startswith(".") and not ln.endswith(":")]


def test_smp_hands_on_to_the_inserts_and_writes_only_saved_registers():
    # v0.13: PERC -> the sample machines -> (2026-11-09) the inserts -> (v0.26) PING, whose tail
    # restores what PERC saved
    lines = _code_lines("smp")
    assert f"JUMP {dsp.INS_SW:#x};" in lines
    import re
    for ln in lines:
        m = re.match(r"(I|M|L|B)(\d+) =", ln)
        if m:
            # v0.18: I0 (the DT2 decimator's coefficients), I3 (its interpolator's row) and I5
            # (its state): saved by PERC; used only pre-modified, DM(k, In), which no circular
            # buffer (L) touches
            assert f"{m.group(1)}{m.group(2)}" in ("I0", "I1", "I2", "I3", "I4", "I5", "I12"), ln
        assert not re.search(r"\b(R1[6-9]|R[2-9]\d|F1[6-9]|USTAT|MODE1|MODE2|LCNTR)\b", ln), ln
        assert not re.search(r"DM\(I[035], M", ln), ln
    assert not any(re.search(r"\bCALL\b|\bDO\b|\bRTS\b", ln) for ln in lines)


def test_inserts_hand_on_to_ping_and_write_only_saved_registers():
    import re
    lines = _code_lines("inserts")
    assert f"JUMP {dsp.PING_SW:#x};" in lines
    for ln in lines:
        m = re.match(r"(I|M|L|B)(\d+) =", ln)
        if m:
            assert f"{m.group(1)}{m.group(2)}" in ("I0", "I1", "I4", "I12"), ln
        assert not re.search(r"\b(R1[6-9]|R[2-9]\d|F1[6-9]|USTAT|MODE1|MODE2|LCNTR)\b", ln), ln
    assert not any(re.search(r"\bCALL\b|\bDO\b|\bRTS\b", ln) for ln in lines)


def test_inspost_saves_what_it_uses_and_hands_on_to_the_sends():
    """the post inserts run inside the engine's call of the FX sends: every register they write is
    saved first and restored before the JUMP on (dnfw.inserts.post.save / restore)"""
    import re
    from dnfw.inserts import post
    lines = _code_lines("inspost")
    assert f"JUMP {post.SENDS_SW:#x};" in lines
    saved = {f"R{k}" for k in range(16)} | {f"I{i}" for i in post.SAVE_I}
    for ln in lines:
        m = re.match(r"(I|M|L|B)(\d+) =", ln)
        if m:
            assert f"{m.group(1)}{m.group(2)}" in saved, ln
        assert not re.search(r"\b(R1[6-9]|R[2-9]\d|F1[6-9]|USTAT|MODE1|MODE2|LCNTR)\b", ln), ln
    assert not any(re.search(r"\bCALL\b|\bDO\b|\bRTS\b", ln) for ln in lines)
    assert lines[:16] == [f"DM({post.C[f'sv{k}']:#x}) = R{k};" for k in range(16)]


def test_the_sends_call_gets_wr_inpost_as_its_target():
    assert dsp.SENDS_SITE_STOCK.hex() == "04181c003817"               # CJUMP 0x1c1738 (DB)
    new = dsp.sends_cjump()
    assert new[:2] == dsp.SENDS_SITE_STOCK[:2] and len(new) == 6
    assert (int.from_bytes(new[2:4], "little") << 16 | int.from_bytes(new[4:6], "little")) == dsp.POST_SW


def test_perc_saves_what_ping_restores_and_hands_on_to_resonator():
    lines = _code_lines("perc")
    regs = [f"R{k}" for k in range(16)] + ["I0", "I1", "I2", "I3", "I4", "I5", "I12", "M0", "M1", "M2", "M3", "M4"]
    assert lines[:len(regs)] == [f"DM({0x2DDE00 + 4 * k:#x}) = {r};" for k, r in enumerate(regs)]
    assert f"JUMP {dsp.SMP_SW:#x};" in lines
    # only the registers saved there are written (and no M, L, B or DAG2 other than I12)
    import re
    for ln in lines:
        m = re.match(r"(I|M|L|B)(\d+) =", ln)
        if m:
            # v0.17: I3 (a slot's Machinedrum words) and I5 (a machine's output), both saved
            # (v0.24: and I0, the P-I machines', saved with the rest)
            assert f"{m.group(1)}{m.group(2)}" in ("I0", "I1", "I2", "I3", "I4", "I5", "I12"), ln
    assert not any(re.search(r"\bCALL\b|\bDO\b|\bRTS\b", ln) for ln in lines)


def test_no_source_is_left_with_its_branch_targets_unresolved():
    # v0.28: ping.asm regenerated without scripts/sharc_resolve_jumps.py assembled with
    # JUMP 0x0 throughout (the SHARC runner caught it); every shipped source is resolved
    import re
    for name in ("perc", "smp", "ping", "block_count", "pvmix", "entry_mark", "idle_load"):
        src = (SHARC / f"{name}.asm").read_text(encoding="utf-8")
        assert not re.search(r"JUMP\s+0x0;|=\s*0x0;\s*// return address", src), name


def test_every_branch_to_a_label_lands_inside_its_own_code():
    # v0.28: the sample span grew, pvmix moved, and its jumps still named the old place
    # (the gate's runner caught it): a `JUMP 0x.. // -> label.` lands in its own object
    import json
    import re
    # (2026-11-12, perc-layout: PERC's three spans are one program: a jump of any of them lands in one of them)
    def span(name):
        spec = json.loads((SHARC / f"{name}.json").read_text(encoding="utf-8"))
        lo = int(spec["load_sw"], 16) if isinstance(spec["load_sw"], str) else spec["load_sw"]
        return lo, lo + len(bytes.fromhex(spec["object_parcels_be"])) // 2
    perc = ("perc", *dsp.PERC_SPANS)
    for name in (*perc, "smp", "ping", "pvmix", "block_count"):
        ranges = [span(n) for n in (perc if name in perc else (name,))]
        src = (SHARC / f"{name}.asm").read_text(encoding="utf-8")
        for m in re.finditer(r"JUMP\s+(0x[0-9a-fA-F]+);\s*//\s*->\s*\w+\.", src):
            assert any(lo <= int(m.group(1), 16) < hi for lo, hi in ranges), (name, m.group(0))


def test_the_voice_order_lives_in_the_monomachine_scratch_tail():
    # v0.29: the slots' keys, costs and order (dnfw.perc.program) in the Monomachine
    # scratch's free tail, past what dnfw.mnm.core uses, inside the scratch span
    from dnfw.perc import program as PP
    from dnfw.perc import live as PL
    L = PL.layout()
    assert PP.MNM_SCRATCH == dsp.MNM_SCRATCH_L2 == L.md.mnm.scratch
    used = max(L.md.mnm.DG.values()) + 4
    assert used <= PP.MNM_SCRATCH + PP.MNM_KEYS_OFF
    assert PP.MNM_SCRATCH + PP.SMP_I + 4 <= dsp.MNM_SCRATCH_L2 + dsp.MNM_SCRATCH_BYTES


def test_every_table_perc_reads_is_loaded_by_a_span():
    """v0.31: v0.28 dropped SHFT's tables, and with them the sine PERC's amp modulation
    reads (L.sin): AMD then read whatever the DDR held, and on the instrument any AMD above
    0 silenced everything until a reboot. Every table PERC's program reads must lie inside
    a span the image loads, byte for byte the model's."""
    from dnfw.perc import live as PL, machines as PM
    from dnfw.shft import live as SL
    L = PL.layout()
    spans = [(a, a + len(b), b) for _, a, b in dsp.ddr_spans()]

    def loaded(lo, data):
        for a, z, b in spans:
            if a <= lo and lo + len(data) <= z:
                return b[lo - a:lo - a + len(data)] == data
        return False
    # 2026-11-10 (shrink): tan and AMD's sine ship over the link with the Machinedrum's tables
    # (the voices wait for them: C['fill']); exp2 stays in the stream (the sample machines read it)
    from dnfw.md import core as MDK
    shipped, base = MDK.tables_bytes(), L.md.T[MDK.SHIPPED]

    def sent(lo, data):
        return base <= lo and lo + len(data) <= base + len(shipped) \
            and shipped[lo - base:lo - base + len(data)] == data
    sdata, at = SL.tables_bytes()
    assert sent(L.sin, sdata[at["sin"]:at["pow2"]]), "PERC's sine (AMD) is not shipped"
    pdata, pat = PM.tables_bytes()
    assert sent(L.T["tan"], pdata[pat["tan"]:]), "PERC's tan is not shipped"
    assert loaded(L.tables, pdata[:pat["tan"]]), "PERC's exp2 is not loaded"
    assert L.T["exp2"] == L.tables


def test_v037_the_recorders_main_tap_is_one_place():
    """the tap pvmix fills and the recorder's MAIN reads: one address, in the DSP's map,
    in proven L2, past the DPRO tables' room"""
    from dnfw.sampler import machines as SM
    from dnfw.waverider import dsp
    assert SM.MAIN_TAP == dsp.MAIN_TAP_L2 == dsp.MNM_DT_L2 + dsp.MNM_DT_BYTES
    assert 0x20088400 <= dsp.MAIN_TAP_L2 and dsp.MAIN_TAP_L2 + dsp.MAIN_TAP_BYTES <= 0x200B0000
