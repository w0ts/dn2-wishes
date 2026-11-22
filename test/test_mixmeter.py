"""The mixer meters (2026-11-20; scratch/mixer-overview.md): the ColdFire's side (csrc/meter/mixer.c, compiled for the
host and driven through ctypes) and the DSP's (dnfw.sampler.program levels, dac_guard, the levels packet in tdm_tx,
run as the model over a memory of its own) against independent Python. The drawing on the glass, the latches' and the
CLIP label's timing are the emulator's (scripts/emu_mixmeter.py); the DSP code itself the SHARC runner's (levels,
dacover)."""

from __future__ import annotations

import ctypes
import math
import os
import pathlib
import shutil
import struct
import subprocess

import pytest

from dnfw.perc.dsl import Mem, Prog, bits, flt, f32
from dnfw.sampler import live as SL
from dnfw.sampler import machines as SM
from dnfw.sampler import program as SP

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIXER = ROOT / "csrc" / "meter" / "mixer.c"

HARNESS = r"""
typedef unsigned int u32;
volatile u32 host_frames, host_tick, host_reply, host_mode;
volatile unsigned char host_out_on;
volatile signed char host_sel[2];
u32 smp_input_seq;
volatile u32 host_rx[16 * 32];
volatile u32 mix_host_owner[16];
u32 smp_rx_sh;
int mtr_big;
u32 ins_view_of(u32 cls) { (void)cls; return 0; }
int smp_question_up(void) { return 0; }
int wpop_shown(void) { return 0; }
int mxp_visible(void) { return 0; }
int ldp_visible(void) { return 0; }
int ovw_visible(void) { return 0; }
int rec_state;
int ovw_up;
"""


def defines() -> list[str]:
    out = ["-DMIX_HOST", "-DFRAMES=host_frames", "-DTICK=host_tick", "-DREPLY_W6=host_reply", "-DUSB_MODE=host_mode",
           "-DUSB_OUT_ON=host_out_on", "-DUSB_OUT_SEL=host_sel"]
    for name in ("LV_MAGIC", "LV_ONE", "LV_WANT_OFF", "LV_WANT", "LV_REPLY_AT", "LV_REPLY_MAGIC"):
        out.append(f"-D{name}={getattr(SM, name):#x}u")
    for name in ("LV_CH", "LV_BIT_MAIN_OB", "LV_BIT_DAC", "LV_BIT_IN", "LV_BIT_REC"):
        out.append(f"-D{name}={getattr(SM, name)}")
    return out


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    assert cc, "no host C compiler"
    d = tmp_path_factory.mktemp("mixer")
    (d / "harness.c").write_text(HARNESS)
    (d / "proto.h").write_text("extern volatile unsigned int host_frames, host_tick, host_reply, host_mode;\n"
                               "extern volatile unsigned char host_out_on;\nextern volatile signed char host_sel[2];\n"
                               "extern volatile unsigned int host_rx[16 * 32];\n")
    so = d / "mixer.so"
    r = subprocess.run([cc, "-O1", "-Wall", "-Wno-int-to-pointer-cast", "-shared", "-fPIC", *defines(), "-include",
                        str(d / "proto.h"), str(MIXER), str(d / "harness.c"), "-o", str(so)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lib = ctypes.CDLL(str(so))
    lib.mix_chan_bit.restype = ctypes.c_uint
    lib.mix_live_bits.restype = ctypes.c_uint
    lib.mix_ov_live_bits.restype = ctypes.c_uint
    lib.mix_ov_live_bits.argtypes = [ctypes.c_uint]
    lib.mix_ovw_get.restype = ctypes.c_uint
    lib.mix_ovw_get.argtypes = [ctypes.c_int]
    lib.mix_rows_of.argtypes = [ctypes.c_uint]
    lib.mix_clip_recent.argtypes = [ctypes.c_uint]
    return lib


def var(lib, name, ctype=ctypes.c_uint):
    return ctype.in_dll(lib, name)


# -- the ColdFire's side --------------------------------------------------------------------------------------------

def test_rows_are_3_db_each_the_top_full_scale(lib):
    """a peak lights j rows (j = 1..17) from 10^((3 j - 51) / 20) x LV_ONE; the 17th only at full scale"""
    for j in range(1, 18):
        th = round(10 ** ((3 * j - 51) / 20) * SM.LV_ONE)
        assert lib.mix_rows_of(th) == j, j
        assert lib.mix_rows_of(th - 1) == j - 1, j
    assert lib.mix_rows_of(0) == 0
    assert lib.mix_rows_of(SM.LV_ONE - 1) == 16                 # just under full scale: not the top row
    assert lib.mix_rows_of(0xFFFF) == 17


def test_channel_to_clip_bit_follows_overbridges_map(lib):
    """docs/link-research.md: 0, 1 main; 2..33 tracks 1..16 L / R; 34..39 the 3 returns; 40, 41 the input"""
    want = {0: 19, 1: 19, 40: 21, 41: 21}
    want.update({2 + 2 * t + s: t for t in range(16) for s in (0, 1)})
    want.update({34 + 2 * r + s: 16 + r for r in range(3) for s in (0, 1)})
    for c in range(42):
        assert lib.mix_chan_bit(c) == 1 << want[c], c
    for c in (-1, 42, 100):
        assert lib.mix_chan_bit(c) == 0


@pytest.mark.parametrize("mode,on,sel,extra", [
    (0, 0, (0, 1), 0), (6, 0, (0, 1), 1 << 19), (5, 1, (2, 3), 1), (5, 1, (0, 1), 1 << 19),
    (5, 0, (2, 3), 0), (5, 1, (36, 37), 1 << 17), (5, 1, (12, 33), 1 << 5 | 1 << 15)])
def test_outputs_in_use(lib, mode, on, sel, extra):
    var(lib, "host_mode").value = mode
    var(lib, "host_out_on", ctypes.c_ubyte).value = on
    arr = (ctypes.c_byte * 2).in_dll(lib, "host_sel")
    arr[0], arr[1] = sel
    base = 1 << SM.LV_BIT_DAC | 1 << SM.LV_BIT_IN | 1 << SM.LV_BIT_REC
    assert lib.mix_live_bits() == base | extra


BITS = 24                                # mixer.c: the DSP's 23 clip bits, then a voice's clip with no track known


def stamps(lib):
    return list((ctypes.c_uint * BITS).in_dll(lib, "mix_clip_at"))


def clear(lib):
    a = (ctypes.c_uint * BITS).in_dll(lib, "mix_clip_at")
    for k in range(BITS):
        a[k] = 0


def test_clip_word_halves_magic_and_outputs_in_use(lib):
    var(lib, "mix_live").value = 1 << 20 | 1 << 3
    var(lib, "host_frames").value = 1000
    clear(lib)
    w = SM.LV_REPLY_MAGIC | 1 << 3 | 1 << 5 | 1 << 20
    var(lib, "host_reply").value = (w & 0xFFFF) << 16 | w >> 16          # the DSP's store, halves swapped
    lib.mix_clip_in()
    at = stamps(lib)
    assert at[3] == 1001 and at[20] == 1001 and at[5] == 0             # (5: not in use)
    clear(lib)
    w = 1 << 3                                                         # no magic: stock's zeros, anything else
    var(lib, "host_reply").value = (w & 0xFFFF) << 16 | w >> 16
    lib.mix_clip_in()
    assert stamps(lib) == [0] * BITS
    var(lib, "host_reply").value = SM.LV_REPLY_MAGIC | 1 << 3          # unswapped: the magic in the wrong half
    lib.mix_clip_in()
    assert stamps(lib) == [0] * BITS


def test_a_voices_own_clip_stamps_its_track(lib):
    """2026-11-20 (clip-inner; the User: "NO DIGITAL CLIPPING ... if it does, i want the alert"): a clip packet's
    voice slots, each stamped on the track it plays (OWNER), whatever the outputs in use; a slot with no track (OWNER
    out of range) lights the label alone"""
    own = (ctypes.c_uint * 16).in_dll(lib, "mix_host_owner")
    for s in range(16):
        own[s] = (s + 3) % 16
    own[9] = 127
    var(lib, "mix_live").value = 1 << 20                               # Overbridge's tracks not in use: irrelevant
    var(lib, "host_frames").value = 3000
    clear(lib)
    lib.mix_inner_in(1 << 1 | 1 << 9 | 1 << 14, 0, 0)
    at = stamps(lib)
    assert at[4] == 3001 and at[1] == 3001                             # slots 1 -> track 4, 14 -> track 1
    assert at[23] == 3001                                              # slot 9: no track, the label only
    assert sum(1 for x in at if x) == 3
    assert var(lib, "mix_inner_last").value == 1 << 4 | 1 << 1
    assert lib.mix_clip_recent(3000 + 100)
    clear(lib)
    lib.mix_inner_in(0, 0, 0)
    assert stamps(lib) == [0] * BITS
    lib.mix_inner_in(0, 1 << 7 | 1 << 15 | 1 << 16, 1 << 0 | 1 << 2)  # per-track stages' tracks, the sends' returns
    at = stamps(lib)
    assert at[7] == 3001 and at[15] == 3001 and at[16] == 3001 and at[18] == 3001
    assert sum(1 for x in at if x) == 4                                # (track bits past 15 ignored)


def ov_stamps(lib):
    return list((ctypes.c_uint * BITS).in_dll(lib, "mix_ov_clip_at"))


def ov_clear(lib):
    a = (ctypes.c_uint * BITS).in_dll(lib, "mix_ov_clip_at")
    for k in range(BITS):
        a[k] = 0


@pytest.mark.parametrize("mode,extra", [(6, 0x7FFFF), (5, 0), (0, 0)])
def test_overview_outputs_in_use(lib, mode, extra):
    """2026-11-21, the OUTPUTS overview: in Overbridge mode every track's and return's own channel too"""
    var(lib, "host_mode").value = mode
    assert lib.mix_ov_live_bits(1 << 20) == 1 << 20 | extra


def test_overview_stamps_every_output_in_use_the_label_its_own(lib):
    """an Overbridge track channel's clip stamps the overview's own stamps, never the CLIP label's / the MIXER's "!"
    (their 2026-11-20 rule); a voice's own clip (mix_inner_in) stamps theirs, never the overview's"""
    var(lib, "host_mode").value = 6
    live = 1 << 19 | 1 << 20 | 1 << 21 | 1 << 22
    var(lib, "mix_live").value = live
    var(lib, "mix_ov_live").value = lib.mix_ov_live_bits(live)
    var(lib, "host_frames").value = 7000
    clear(lib)
    ov_clear(lib)
    w = SM.LV_REPLY_MAGIC | 1 << 4 | 1 << 17 | 1 << 19
    var(lib, "host_reply").value = (w & 0xFFFF) << 16 | w >> 16
    lib.mix_clip_in()
    ov, at = ov_stamps(lib), stamps(lib)
    assert ov[4] == 7001 and ov[17] == 7001 and ov[19] == 7001 and sum(1 for x in ov if x) == 3
    assert at[19] == 7001 and at[4] == 0 and at[17] == 0 and sum(1 for x in at if x) == 1
    clear(lib)
    ov_clear(lib)
    lib.mix_inner_in(0, 1 << 6, 0)
    assert stamps(lib)[6] == 7001 and ov_stamps(lib) == [0] * BITS
    var(lib, "host_mode").value = 5                                      # USB audio, no pair: a track's channel unused
    var(lib, "mix_ov_live").value = lib.mix_ov_live_bits(1 << 20)
    lib.mix_clip_in()
    assert ov_stamps(lib) == [0] * BITS


def test_overview_bars_in_use(lib):
    """mix_ovw_get's in-use bit: the recorder's only while it records (rec_state 2); -1 gives the USB mode"""
    var(lib, "host_mode").value = 6                                      # (mix_live in Overbridge mode: its main too)
    var(lib, "mix_ov_live").value = lib.mix_ov_live_bits(1 << 19 | 1 << 20 | 1 << 21 | 1 << 22)
    rec = var(lib, "rec_state", ctypes.c_int)
    for st, want in ((0, 0), (1, 0), (2, 1), (3, 0)):
        rec.value = st
        assert lib.mix_ovw_get(24) >> 17 & 1 == want, st
    assert all(lib.mix_ovw_get(ch) >> 17 & 1 for ch in range(24))
    var(lib, "host_mode").value = 0
    var(lib, "mix_ov_live").value = lib.mix_ov_live_bits(1 << 20 | 1 << 21 | 1 << 22)
    assert [lib.mix_ovw_get(ch) >> 17 & 1 for ch in range(24)] == [0] * 21 + [1, 1, 1]
    assert lib.mix_ovw_get(-1) == 0 and lib.mix_ovw_get(25) == 0


def test_label_three_seconds_after_a_clip(lib):
    clear(lib)
    assert not lib.mix_clip_recent(5000)
    a = (ctypes.c_uint * BITS).in_dll(lib, "mix_clip_at")
    a[7] = 5001
    assert lib.mix_clip_recent(5000)
    assert lib.mix_clip_recent(5001 + 4498)
    assert not lib.mix_clip_recent(5001 + 4500)


MIX_CH = SM.LV_CH                        # mixer.c: the DSP's channels, 22 / 23 Overbridge / USB main L, R


def test_levels_keep_each_channels_largest(lib):
    acc = (ctypes.c_ushort * (2 * MIX_CH)).in_dll(lib, "mix_acc")
    for k in range(2 * MIX_CH):
        acc[k] = 0
    sel = var(lib, "mix_sel").value & 1
    u = (ctypes.c_ushort * SM.LV_CH)(*[100 * (k + 1) for k in range(SM.LV_CH)])
    lib.mix_lvl_in(u)
    u = (ctypes.c_ushort * SM.LV_CH)(*[3000 - 100 * k for k in range(SM.LV_CH)])
    lib.mix_lvl_in(u)
    got = [acc[MIX_CH * sel + k] for k in range(SM.LV_CH)]
    assert got == [max(100 * (k + 1), 3000 - 100 * k) for k in range(SM.LV_CH)]


def test_dsp_main_ob_bit_is_taken(lib):
    """2026-11-20: the DSP's bit 19 is Overbridge / USB main as sent (TX slots 0, 1, sampler.program ob_peaks): kept
    while that output is in use, dropped while not"""
    clear(lib)
    var(lib, "host_frames").value = 2000
    var(lib, "mix_live").value = 1 << 20
    w = SM.LV_REPLY_MAGIC | 1 << 19 | 1 << 20
    var(lib, "host_reply").value = (w & 0xFFFF) << 16 | w >> 16
    lib.mix_clip_in()
    assert stamps(lib)[19] == 0 and stamps(lib)[20] == 2001
    clear(lib)
    var(lib, "mix_live").value = 1 << 19 | 1 << 20
    lib.mix_clip_in()
    assert stamps(lib)[19] == 2001 and stamps(lib)[20] == 2001


# -- the DSP's side, its model ---------------------------------------------------------------------------------------

G = flt(SM.OB_GAIN_BITS)


def test_constants():
    assert abs(G - 1 / 0.7) < 1e-6
    assert SM.LINK_DM + 4 * len(SM.LINK_WORDS) <= SM.LINK_BUF
    assert SM.TABLE_READY + 0x120 <= SM.LV_WANT_OFF < SM.TABLE_READY + 512           # after TAPE's PGAIN words
    assert f32(SM.DAC_TOP) == SM.DAC_TOP and SM.DAC_TOP < 1.0 and math.nextafter(SM.DAC_TOP, 2.0) >= 1.0 - 1e-7
    assert round(f32(SM.DAC_TOP) * 2 ** 31) < 2 ** 31                   # FIX BY 31 of it fits
    assert SM.LV_CH == 25 and SM.LV_UNIT_REC == 24 and SM.LV_TOP * SM.LV_ONE < 0x10000


@pytest.mark.skipif(not os.environ.get("DT2_SECTIONS"), reason="needs the stock image's sections (DT2_SECTIONS)")
def test_gain_is_stocks_channel_table_gain():
    """the image holds 1 / 0.7 as the output stage's gain (a 48-bit immediate: its halves swapped)"""
    s7 = (pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_7_BLOB.bin").read_bytes()
    w = SM.OB_GAIN_BITS
    assert s7.count(struct.pack("<HH", w >> 16, w & 0xFFFF)) >= 1


def run_levels(mem: Mem, flag: int) -> Prog:
    L = SL.layout()
    mem.put(SP.LV_SRC_WORD, flag << 16)
    p = Prog("run", mem=mem)
    SP.levels(p, L)
    return p


def fill(mem: Mem, base: int, xs) -> None:
    for j, x in enumerate(xs):
        mem.put(base + 4 * j, bits(f32(x)))


def test_levels_model():
    L = SL.layout()
    K = SP.LK
    for flag in (0, 1):
        mem = Mem(lambda a: 0)
        amps = [0.3 + 0.1 * t for t in range(16)]
        for t in range(16):
            xs = [amps[t] * math.sin(0.3 * j + t) for j in range(64)]
            xs[11] = amps[t] * (-1 if t % 2 else 1)
            fill(mem, (SP.LV_TRK_A if flag else SP.LV_TRK_B) + 0x100 * t, xs)
            fill(mem, (SP.LV_TRK_B if flag else SP.LV_TRK_A) + 0x100 * t, [9.0] * 64)   # the other source: unread
        for r in range(3):
            xs = [0.65 + 0.05 * r] * 64
            fill(mem, (SP.LV_RET_A if flag else SP.LV_RET_B) + SP.LV_RET_STRIDE * r, xs)
        fill(mem, SM.MAIN_TAP, [9.0] * 64)                               # (no longer read: the analog main)
        mem.put(K["dobl"], 0x7FFFFF)                                      # Overbridge's main: L at its top (a clip)
        mem.put(K["dobr"], 0x123456)
        mem.put(K["dpkl"], bits(f32(1.2)))
        mem.put(K["dpkr"], bits(f32(0.5)))
        fill(mem, SM.IN_BUF, [0.99995] + [0.0] * 63)
        mem.put(L.C["rst"], 2)
        mem.put(L.C["rpk"], bits(f32(SM.REC_TOP)))
        mem.put(K["lprev"], 1 << 7)
        run_levels(mem, flag)
        want, kept = 0, []
        for t in range(16):
            p = f32(f32(amps[t]) * G)                                     # (sample 11 is the peak, +-amp)
            if not p < 1.0:
                want |= 1 << t
            kept.append(f32(p) if p < f32(SM.LV_TOP) else f32(SM.LV_TOP))
        for r in range(3):
            p = f32(f32(0.65 + 0.05 * r) * G)
            if not p < 1.0:
                want |= 1 << (16 + r)
            kept.append(p)
        want |= 1 << SM.LV_BIT_MAIN_OB                                   # dobl at 0x7fffff
        want |= 1 << SM.LV_BIT_DAC                                       # 1.2
        want |= 1 << SM.LV_BIT_IN                                        # 0.99995 >= IN_TOP
        want |= 1 << SM.LV_BIT_REC
        kept += [f32(1.2), f32(0.5), f32(0.99995), 0x7FFFFF / 2 ** 23, 0x123456 / 2 ** 23, f32(SM.REC_TOP)]
        got_kept = [flt(mem.get(K[f"lpk{k}"])) for k in range(SM.LV_CH)]
        assert mem.get(K["lprev"]) == want, f"{mem.get(K['lprev']):#x} != {want:#x}"
        for k in range(SM.LV_CH):
            assert got_kept[k] == pytest.approx(kept[k], rel=1e-6), k
        for page in SM.REPLY_PAGES:
            assert mem.get(page + SM.LV_REPLY_AT) == SM.LV_REPLY_MAGIC | want | 1 << 7


def test_levels_nan_and_kept_max():
    K = SP.LK
    mem = Mem(lambda a: 0)
    xs = [0.1] * 64
    xs[30] = float("nan")
    fill(mem, SP.LV_TRK_A + 0x100 * 4, xs)
    mem.put(K["lpk2"], bits(f32(0.9)))                                   # a peak kept from before: kept
    run_levels(mem, 1)
    assert mem.get(K["lprev"]) & (1 << 4)                                # a NaN: a clip
    assert flt(mem.get(K["lpk4"])) == f32(SM.LV_TOP)                     # ... sent as LV_TOP
    assert flt(mem.get(K["lpk2"])) == f32(0.9)
    assert mem.get(K["lprev"]) & ~(1 << 4) == 0


def test_levels_recorder_peak_only_while_recording():
    """2026-11-21 (the OUTPUTS overview): lpk24 keeps the recorder's block peak while it records (state 2), the larger,
    held under LV_TOP; in any other state it is left as it was"""
    L = SL.layout()
    K = SP.LK
    for st, rpk, before, want in ((2, 0.25, 0.5, 0.5), (2, 0.75, 0.5, 0.75), (2, 9.0, 0.0, SM.LV_TOP),
                                  (1, 0.75, 0.0, 0.0), (3, 0.75, 0.125, 0.125), (0, 0.75, 0.0, 0.0)):
        mem = Mem(lambda a: 0)
        mem.put(L.C["rst"], st)
        mem.put(L.C["rpk"], bits(f32(rpk)))
        mem.put(K["lpk24"], bits(f32(before)))
        run_levels(mem, 0)
        assert flt(mem.get(K["lpk24"])) == f32(want), (st, rpk, before)
        assert bool(mem.get(K["lprev"]) >> SM.LV_BIT_REC & 1) == (st == 2 and f32(rpk) >= f32(SM.REC_TOP)), st


def test_dac_guard_model():
    L = SL.layout()
    K = SP.LK
    mem = Mem(lambda a: 0)
    xs = [0.5 * math.sin(0.2 * j) for j in range(64)]
    xs[3], xs[40], xs[41], xs[42] = 1.5, -1.0, -3.0, SM.DAC_TOP
    fill(mem, SM.MIX_BUF, xs)
    p = Prog("run", mem=mem)
    SP.dac_guard(p, L)
    held = [flt(mem.get(SM.MIX_BUF + 4 * j)) for j in range(64)]
    for x, h in zip(xs, held):
        x = f32(x)
        assert h == (x if abs(x) <= SM.DAC_TOP else math.copysign(f32(SM.DAC_TOP), x))
    assert flt(mem.get(K["dpkl"])) == f32(1.5)
    assert flt(mem.get(K["dpkr"])) == f32(3.0)


@pytest.mark.parametrize("page", [0, 1])
def test_ob_peaks_model(page):
    """2026-11-20: Overbridge / USB main's peaks from TX slots 0, 1 of this block's page, as the ColdFire's mix_ob_main
    read them before: max |w >> 8| (arithmetic) of each side's 32 words; the other page and the other slots unread"""
    L = SL.layout()
    K = SP.LK
    import random
    rnd = random.Random(7 + page)
    edges = [0, 1, -1, 0x7FFFFF00, 0x7FFFFFFF, -0x80000000, -0x7FFFFF00, -0x7FFFFE01, 0x7FFFFEFF, 0xFF, -0x100]
    for case in range(40):
        mem = Mem(lambda a: 0)
        mem.put(SM.TDM_PAGE, page | (2 if case % 3 == 0 else 0))
        base = SM.TDM_TX + (page << 11)
        other = SM.TDM_TX + ((1 - page) << 11)
        ws = {}
        for f in range(32):
            for s_ in (0, 1):
                w = rnd.choice(edges) if case % 2 else rnd.randrange(-(1 << 31), 1 << 31)
                if case == 0:
                    w = 0
                ws[(f, s_)] = w
                mem.put(base + 64 * f + 4 * s_, w & 0xFFFFFFFF)
                mem.put(other + 64 * f + 4 * s_, 0x7FFFFFFF)
            mem.put(base + 64 * f + 8, 0x7FFFFFFF)                       # slot 2: a track's, unread
        p = Prog("run", mem=mem)
        SP.ob_peaks(p, L)
        for s_, key in ((0, "dobl"), (1, "dobr")):
            want = max(abs(ws[(f, s_)] >> 8) for f in range(32))
            assert mem.get(K[key]) == want, (case, key, mem.get(K[key]), want)
