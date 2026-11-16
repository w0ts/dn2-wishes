"""The SHARC's L1 / L2 claims (docs/memory-map.md "DSP optimisation claims 2026-11-12") as data, and three checks:
every claim disjoint from every other; every module-level L1 / L2 address constant of dnfw inside a claim that names
its module (or the constant itself, for dnfw.waverider.dsp); every span dsp.py loads starting inside a claim that takes
spans. A new area, or one placed inside another owner's room, fails here until its claim is added.

2026-11-12: the L1 "hole" F3 was allotted although inserts.bus.FD_L1 (the bus FDN8 stores, a run-time area outside
dsp.py) filled it; this file is what would have caught it."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import dnfw
from dnfw.waverider import dsp

ALIAS = 0x28000000
L1 = (dsp.REGION[0], dsp.DM_CACHE_16K)            # our L1 room: REGION and the gap below the DM cache
L2 = (dsp.L2_IMAGE_END, dsp.L2_NOCACHE)           # L2 above the stock image, below the non-cacheable window

# (name, lo, hi, owners, spans): owners are module names (any constant of theirs may lie inside) or, for
# dnfw.waverider.dsp, "dnfw.waverider.dsp.NAME" (that constant only); spans: dsp.py may load a span starting here
CLAIMS = [
    # L1 block 1, REGION
    ("a2f state", 0x2DD600, 0x2DDE00, ("dnfw.a2f.program", "dnfw.waverider.dsp.A2F_STATE_DM"), True),
    ("save area, PERC scratch, guard, idle", 0x2DDE00, 0x2DE180,
     ("dnfw.perc.program", "dnfw.perc.guard", "dnfw.waverider.dsp.STATE_DM", "dnfw.waverider.dsp.PERC_SCRATCH_DM",
      "dnfw.waverider.dsp.IDLE_STATE_DM", "dnfw.waverider.dsp.TWIN_FLAG_DM"), True),
    ("PERC state", 0x2DE180, 0x2DEA00, ("dnfw.waverider.dsp.PERC_STATE_DM",), True),
    ("idle_load code", 0x2DEA00, 0x2DEC00, ("dnfw.waverider.dsp.IDLE_DM",), True),
    ("block_count code", 0x2DEC00, 0x2DED00, ("dnfw.waverider.dsp.COUNT_DM",), True),
    ("entry_mark code", 0x2DED00, 0x2DEE00, ("dnfw.waverider.dsp.EMARK_DM",), True),
    ("machine lookup", 0x2DEE00, 0x2DEF00, ("dnfw.waverider.dsp.LOOKUP16_DM",), True),
    ("sample machines' state", 0x2DEF00, 0x2DF700, ("dnfw.waverider.dsp.SMP_STATE_DM",), True),
    ("sample machines' scratch", 0x2DF700, 0x2DF800, ("dnfw.waverider.dsp.SMP_SCRATCH_DM",), True),
    ("recorder staging", 0x2DF800, 0x2DF880, ("dnfw.sampler.machines", "dnfw.waverider.dsp.SMP_STAGE_DM"), True),
    ("fast link", 0x2DF880, 0x2DFD80, ("dnfw.sampler.machines", "dnfw.waverider.dsp.SMP_LINK_DM"), True),
    ("decimators", 0x2DFD80, 0x2E0080, ("dnfw.waverider.dsp.SMP_DEC_DM",), True),
    # opt-samples: the decimator + LEV gain table (0x2E0080..0x2E0094), the taps line (switch 0x2E0098, tag 0x2E009C,
    # its words to 0x2E0100)
    ("opt-samples' sample reader", 0x2E0080, 0x2E0100,
     ("dnfw.sampler", "dnfw.waverider.dsp.SMP_DTAB_DM", "dnfw.waverider.dsp.SMP_LINE_DM"), False),
    ("SLICE / GRID relatch", 0x2E0100, 0x2E0200, ("dnfw.sampler.program", "dnfw.waverider.dsp.W2_RND_DM"), False),
    ("ping code (the shared tail) + its 128 B", 0x2E0500, 0x2E0640, ("dnfw.waverider.dsp.PING_CODE_DM",), True),
    ("F1: opt-synths' PERC exp2 copy", 0x2E0640, 0x2E0E44, ("dnfw.waverider.dsp.PERC_EXP2_DM",), True),
    ("trackbuf code + its 128 B", 0x2E1000, 0x2E1200, ("dnfw.waverider.dsp.TRACKBUF_CODE_DM",), True),
    ("F2: opt-mnm's DPRO interp table", 0x2E1200, 0x2E1700, ("dnfw.mnm", "dnfw.waverider.dsp"), True),
    ("the stock track buffers in L1", 0x2E1C00, 0x2E3000,
     ("dnfw.waverider.dsp.TRACKAUX_DM", "dnfw.waverider.dsp.TRACKBUF_DM"), True),
    ("the inserts' state", 0x2E3000, 0x2E3A40, ("dnfw.inserts.program", "dnfw.inserts.design",
                                                 "dnfw.waverider.dsp.INS_STATE_DM"), True),
    ("the stereo inserts' state", 0x2E3A40, 0x2E4050, ("dnfw.inserts.post", "dnfw.waverider.dsp.POST_STATE_DM"), True),
    ("the bus FDN8 instances' stores (run time)", 0x2E4050, 0x2E53D0, ("dnfw.inserts.bus",), False),
    ("the Monomachine render scratch (opt-inserts: IN transient in the post pass)", 0x2E5400, 0x2E6400,
     ("dnfw.waverider.dsp.MNM_RENDER_DM", "dnfw.inserts.post"), False),     # post.LINE: JUNO's / CHOR's taps' span
    ("FDN8 state", 0x2E6400, 0x2E6E00, ("dnfw.fdn8.program", "dnfw.waverider.dsp.FDN8_STATE_DM"), True),
    ("XDLY state", 0x2E6E00, 0x2E7000, ("dnfw.xdly.program", "dnfw.waverider.dsp.XDLY_STATE_DM"), True),
    ("Machinedrum / Monomachine voice slots", 0x2E7000, 0x2EB000, ("dnfw.waverider.dsp.MD_STATE_DM",), True),
    # L2 above the stock image
    # opt-stock: the stock delay's control words and the chorus's state, moved from DDR 0x80459130 (5,532 B, FX_L2;
    # CHORUS_L2 inside it); the rest of the allotment reserved for the reverb's hot words
    ("opt-stock: the send FX' hot state", 0x20098400, 0x2009B400,
     ("dnfw.waverider.dsp", "dnfw.waverider.stockfx", "dnfw.fx"), True),
    ("perc-layout 2a: PERC's event-only code", 0x2009B400, 0x200A0000, ("dnfw.waverider.dsp", "dnfw.perc"), True),
    ("opt-samples", 0x200A0000, 0x200A1800, ("dnfw.sampler", "dnfw.waverider.dsp"), True),
    ("juno-chorus: jsend.asm", 0x200A1800, 0x200A2800, ("dnfw.waverider.dsp", "dnfw.inserts"), True),
    ("perc-layout 2b: init bodies", 0x200A2800, 0x200A4000, ("dnfw.waverider.dsp", "dnfw.perc"), True),
    ("the Monomachine L2 scratch", 0x200A4000, 0x200A8000,
     ("dnfw.perc.program", "dnfw.waverider.dsp.MNM_SCRATCH_L2"), True),
    ("the DPRO tables", 0x200A8000, 0x200A9000, ("dnfw.waverider.dsp.MNM_DT_L2",), True),
    ("the main mix's tap", 0x200A9000, 0x200A9200, ("dnfw.sampler.machines", "dnfw.waverider.dsp.MAIN_TAP_L2"), True),
    ("fdn8.asm", 0x200AA000, 0x200AC400, ("dnfw.waverider.dsp.FDN8_L2_LOAD",), True),
    ("xdly.asm", 0x200AC400, 0x200ADA00, ("dnfw.waverider.dsp.XDLY_L2_LOAD",), True),
    ("inserts.asm", 0x200ADA00, 0x200B0000, ("dnfw.waverider.dsp.INS_L2_LOAD",), True),
    ("inspost.asm", 0x200B0000, 0x200B1800, ("dnfw.waverider.dsp.POST_L2_LOAD",), True),
    # DRONE's BEAT and ANALOG 2's WDTH write the slot's side block (one machine a slot at a time)
    ("the side blocks (DRONE's BEAT, ANALOG 2's WDTH)", 0x200B1800, 0x200B2100,
     ("dnfw.inserts.post", "dnfw.mnm.drone", "dnfw.mnm.analog2"), True),
    ("a2f.asm", 0x200B2400, 0x200B5800, ("dnfw.a2f.program", "dnfw.waverider.dsp.A2F_L2_LOAD"), True),
    ("smp.asm and pvmix", 0x200B6000, 0x200BC000,
     ("dnfw.waverider.dsp.SMP_L2_LOAD", "dnfw.waverider.dsp.PVMIX_L2_LOAD"), True),
    ("insbus.asm", 0x200BC000, 0x200BD000, ("dnfw.waverider.dsp.INSBUS_L2_LOAD",), True),
    ("the bus inserts' state", 0x200BD000, 0x200BE100, ("dnfw.inserts", "dnfw.waverider.dsp.INSBUS_STATE_L2"), True),
    ("perc.asm", dsp.PERC_L2_LOAD, dsp.PERC_L2_LOAD + dsp.PERC_L2_SPAN, ("dnfw.waverider.dsp.PERC_L2_LOAD",), True),
]

# constants that are bounds, retired names or harness layouts, not areas (with why)
NOT_AREAS = {
    "dnfw.waverider.dsp.L2_IMAGE_END": "a bound: the stock image's end",
    "dnfw.waverider.dsp.L2_NOCACHE": "a bound: the non-cacheable window",
    "dnfw.waverider.dsp.DM_CACHE_32K": "a bound: a 32 KB DM cache's floor",
    "dnfw.waverider.dsp.MD_STATE_L2": "retired 2026-11-10 (the room is left unused)",
    "dnfw.waverider.dsp.GRAN_CODE_DM": "GRAN: not loaded since v0.27",
    "dnfw.waverider.dsp.GRAN_SCRATCH_DM": "GRAN: not loaded",
    "dnfw.waverider.dsp.GRAN_STATE_DM": "GRAN: not loaded",
    "dnfw.waverider.dsp.SHFT_STATE_DM": "SHFT: not loaded (only its tables travel)",
    "dnfw.waverider.dsp.PING_STATE_DM": "PING: removed v0.45 (its name kept)",
    "dnfw.waverider.dsp.PING_T_DM": "PING: removed v0.45",
    "dnfw.inserts.design.BUS_STATE_END": "a bound",
}
HARNESS = ("dnfw.md.bench", "dnfw.mnm.bench")      # the model's bench layouts, not the DSP's


def _claim_of(a: int):
    return [c for c in CLAIMS if c[1] <= a < c[2]]


def _constants():
    out = set()
    for m in pkgutil.walk_packages(dnfw.__path__, "dnfw."):
        if m.name.startswith(HARNESS):
            continue
        try:
            mod = importlib.import_module(m.name)
        except Exception:                          # (modules that need the owner's ROMs or tools to import)
            continue
        for n, v in vars(mod).items():
            if isinstance(v, int) and not isinstance(v, bool):
                a = v - ALIAS if L1[0] <= v - ALIAS < L1[1] else v
                if L1[0] <= a < L1[1] or L2[0] <= a < L2[1]:
                    out.add((a, getattr(mod, "__name__", m.name), n))
    return sorted(out)


def _owns(claim, module: str, name: str) -> bool:
    q = f"{module}.{name}"
    return any(q == o or (not o.startswith("dnfw.waverider.dsp.") and module.startswith(o)) for o in claim[3])


def test_claims_are_disjoint():
    s = sorted(CLAIMS, key=lambda c: c[1])
    for a, b in zip(s, s[1:]):
        assert a[2] <= b[1], f"{a[0]} ({a[1]:#x}..{a[2]:#x}) overlaps {b[0]} ({b[1]:#x}..{b[2]:#x})"
    for c in s:
        assert c[1] < c[2] and (L1[0] <= c[1] and c[2] <= L1[1] or L2[0] <= c[1] and c[2] <= L2[1]), c[0]


def test_real_extents_fit_their_claims():
    """what the code really takes stays inside its claim (the spans are padded, so their lengths say nothing)"""
    from dnfw.inserts import bus, design, post
    obj = dsp.objects()
    assert dsp.PING_CODE_DM + len(obj["ping"]) + dsp.L2_TAIL <= 0x2E0640
    assert dsp.TRACKBUF_CODE_DM + len(obj["trackbuf"]) + dsp.L2_TAIL <= 0x2E1200
    assert bus.FD_L1 + design.FDN8_INSTANCES * bus.FD_L1_BYTES <= 0x2E53D0
    assert post.SCRATCH + post.SCRATCH_BYTES <= 0x2E4050
    assert dsp.SMP_DEC_DM + 16 * 48 <= 0x2E0080
    assert dsp.MD_STATE_DM + 16 * 1024 <= 0x2EB000
    assert dsp.MNM_RENDER_DM + dsp.MNM_RENDER_BYTES <= 0x2E6400
    if hasattr(dsp, "FX_DM"):                      # opt-stock's block (dnfw.waverider.stockfx)
        assert 0x20098400 <= dsp.FX_DM and dsp.FX_DM + dsp.FX_BYTES <= 0x2009B400


@pytest.mark.parametrize("addr,module,name", _constants())
def test_every_address_constant_is_inside_its_owners_claim(addr, module, name):
    q = f"{module}.{name}"
    if q in NOT_AREAS:
        return
    claims = _claim_of(addr)
    if not claims and name.endswith("END"):        # an end marker sits at its claim's top
        claims = _claim_of(addr - 1)
    assert claims, f"{q} = {addr:#x} is in no claim: add it to CLAIMS (and docs/memory-map.md)"
    assert any(_owns(c, module, name) for c in claims), \
        f"{q} = {addr:#x} lies in {claims[0][0]!r}, which does not list it: another owner's room"


def test_every_span_starts_inside_a_claim_that_takes_spans():
    for what, at, _payload in list(dsp.spans()) + list(dsp.l2_spans()):
        a = at - ALIAS if at >= ALIAS else at
        if not (L1[0] <= a < L1[1] or L2[0] <= a < L2[1]):
            continue
        claims = _claim_of(a)
        assert claims and any(c[4] for c in claims), f"span {what!r} at {a:#x} starts in {claims or 'no claim'}"
