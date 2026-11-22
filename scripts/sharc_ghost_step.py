"""The SHARC runner's ghost step (2026-11-20, the User: a ghost delay long after, the unit idle; "are we sure we
don't have overlaps?"). Gate step sharc:ghost (parts ghost-z, ghost-d, ghost-h; docs/memory-map.md "The DSP's write windows").

Every scenario runs with a WRITE WATCH: every DM write the image's code makes (not the harness's pokes) is
attributed to the code object its PC lies in (our L1 / L2 objects by their spans, everything else "stock") and to
the memory area it lands in (dsp.regions(), its sub-areas, the areas regions() leaves out, stock's known DDR areas).
A write into a delay line / ring / FX state by a writer that is not one of its owners is FOREIGN.

Scenarios (GHOST_SCEN, comma separated; GHOST_N blocks each, GHOST_HITS the trigger blocks):
  H  ours: the slot-0 voice (DRUM if the build has it, else PI-SD; GHOST_VOICE overrides) hit at GHOST_HITS, every
     send up, reverb FDN8, delay XDLY, chorus JUNO, bus FDN8 (track 1) and XDLY (track 0) inserts fed a noise burst
     while the hits play, the levels pass asked (LV_WANT), the RAM check (CMD_PROBE) started at block 0; then
     nothing: the outputs (main mix, FX returns, every track's bus block) must decay and stay silent (no block above
     LATE after LATE_GAP silent blocks).
  (the gate runs Z, D and H in three parts; S and the long bus settings, GHOST_BUS=long, by hand)
  S  stock: WAVETONE on slot 0, stock FX types, the stock delay at 1,024 samples; the same decay check.
  Z  never any input, ours as H, with the run-time (unloaded) delay areas first filled with noise, as a unit's DDR /
     L2 holds whatever was there before a DSP restart: every output word exactly as a run on zeroed memory
     (differential, bit for bit), and silent.
  D  as H (with hits) on zeroed memory and on noise-filled memory: every captured word bit-identical.
"""

from __future__ import annotations

import bisect
import collections
import hashlib
import json
import math
import os
import random
import struct
import sys

from dnfw.inserts import bus as B
from dnfw.inserts import design as D
from dnfw.inserts import post as POST
from dnfw.sampler import machines as SM
from dnfw.waverider import dsp
import gen_inserts_asm as GEN                   # label_sw: JUNO's one copy's entry

OUTPUT_CALL_SW = 0x1C307B
MAIN = (0x268438, 64)
FX_RETURNS = (0x25B068, 0x800 // 4)
SEND_SLOTS = (86, 87, 88)
FRAME_COPY = 0x25C48C
FX_TYPE_OFFSETS = (0x25CEB4 - FRAME_COPY, 0x25CEA4 - FRAME_COPY)
# LATE_GAP: an output that comes back after this many silent blocks is a late return. Above every legitimate onset of
# an engine with no early path: FDN8's shortest line is 2,963 samples (92.6 blocks; its first output comes that long
# after its input), LONG's about twice that (186 blocks)
SILENT, LATE, LATE_GAP = 1e-6, 1e-5, 192
TRACE_WORDS = [int(x, 0) for x in os.environ.get("GHOST_TRACE_WORDS", "").split(",") if x]

STOCK_AREAS = [
    ("stock reverb line", 0x80000018, 0x8005912C),
    ("stock delay state + sample area", 0x8005912C, 0x80459388),
    ("stock FX/init words (chorus state)", 0x80459388, 0x8045B000),
    ("stock transient bank", 0x8045B000, 0x804AC000),
    ("stock machine tables / track buffers", 0x804AC000, 0x8052D790),
    ("stock dispatch tables..sine", 0x8052D790, 0x80530BE8),
    ("DDR between stock's top and DDR_FLOOR", 0x80530BE8, dsp.DDR_FLOOR),
    ("DDR above DDR_FLOOR, below ours (0x80600000..0x81000000)", dsp.DDR_FLOOR, 0x81000000),
    ("L2 stock image", 0x20000000, dsp.L2_IMAGE_END),
    ("L2 below dsp.py floor (unclaimed)", dsp.L2_IMAGE_END, 0x2009B400),
    ("L2 above the bus FDN8 diffusers (the User's reserve)", 0x200F5000, dsp.L2_NOCACHE),
    ("L2 non-cacheable window", dsp.L2_NOCACHE, 0x20100000),
    ("L1 block 2 (harness frame / P-I lines / PM cache)", 0x300000, 0x320000),
]

# (area name prefix, owners): a write by anyone else is FOREIGN
OWNERS = [
    ("FDN8's ring", {"fdn8"}),
    ("the bus FDN8 instances' rings", {"fdn8", "insbus"}),
    ("the bus XDLY instances' lines", {"xdly", "insbus"}),
    ("the inserts' TAPE rings", {"inserts"}),
    ("the post inserts' rings", {"inspost"}),
    ("the moved inserts' rings", {"insbus", "inserts", "inspost"}),
    ("the chorus send's JUNO", {"jsend"}),
    ("Machinedrum P-I delay lines", {"perc", "perc2a", "perc2b"}),
    ("PLAITS' big buffers", {"perc", "perc2a", "perc2b"}),
    ("stock reverb line", {"stock", "fdn8"}),
    ("stock delay state + sample area", {"stock", "xdly"}),
    ("stock FX/init words", {"stock", "jsend"}),
    ("XTRA FDN8 diffusers", {"fdn8"}),
    ("the bus FDN8 instances 1..7's diffusers", {"fdn8", "insbus"}),   # (regions(), 2026-11-21)
    ("XTRA P-I lines in L1", {"perc", "perc2a", "perc2b"}),
    ("the bus FDN8 instances' stores", {"fdn8", "insbus"}),
    ("the bus XDLY instances' stores", {"xdly", "insbus"}),
    ("the bus inserts' XDLY stores", {"xdly", "insbus"}),
    ("FDN8 state", {"fdn8", "insbus", "xdly"}),          # XDLY borrows FDN8's block buffers (claims 2026-11-14)
    ("XDLY state", {"xdly", "insbus", "fdn8"}),
    ("PARA as one voice's shadow pool", {"perc", "perc2a", "perc2b"}),
]


def extra_areas() -> list[tuple[str, int, int]]:
    """areas regions() does not list (found by scratch/dsp-overlap-audit.md's static scan)"""
    from dnfw.fdn8 import program as FP
    out = [("XTRA FDN8 diffusers (send, bus 0) in MNM scratch", FP.DIFF_SEND_L2, FP.DIFF_BUS0_L2 + 4 * FP.DIFF_WORDS)]
    if hasattr(dsp, "PARA_DM"):
        out.append(("XTRA PARA chords in L1 (dsp.PARA_DM .. F1's end)", dsp.PARA_DM, 0x2E1000))
    for n, sz in (("PIRS_TAB_L2", 2696), ("PI_CURVE_L2", 2048)):
        if hasattr(dsp, n):
            out.append((f"XTRA {n}", getattr(dsp, n), getattr(dsp, n) + sz))
    if hasattr(dsp, "MD_DELAY_L1"):
        out.append(("XTRA P-I lines in L1 (MD_DELAY_L1)", dsp.MD_DELAY_L1, dsp.MD_DELAY_L1_END))
    pool = dsp.SMP_POOL_DDR
    out += [("XTRA pool: RAM check low area", pool + SM.PROBE_LO, pool + SM.PROBE_LO + SM.PROBE_BYTES),
            ("XTRA pool: RAM check high area", pool + SM.PROBE_HI, pool + SM.PROBE_HI + SM.PROBE_BYTES),
            ("XTRA pool: recordings area", pool + SM.REC_OFFSET, pool + SM.TABLE_AREA),
            ("XTRA pool: shipped table area", pool + SM.TABLE_AREA, pool + SM.TABLE_READY),
            ("XTRA pool: TABLE_READY .. slice area (READY, LV_WANT, ...)", pool + SM.TABLE_READY, pool + SM.SLICE_AREA),
            ("XTRA pool: slice tables", pool + SM.SLICE_AREA, pool + SM.PV_TABLE),
            ("XTRA pool: directory page (entries, names, BUF_DIR, FXP, CMD)", pool, pool + SM.DATA_OFFSET)]
    return out


JUNO_JRET = POST.C["jret"]                    # where JUNO's one copy keeps its caller's return address - 1


def juno_copy_span(code: list[tuple[int, int, str]]) -> tuple[int, int]:
    """[entry, end of inspost.asm): JUNO's one copy (dnfw.inserts.post.juno_body, emitted last), which the post pass
    and the chorus send (jsend) both enter (b2a24efb, 2026-11-21). Its writes belong to the caller, not to inspost:
    the code address alone named the send's writes to its own JUNO ring FOREIGN (inspost)"""
    sharc = GEN.ROOT / "csrc" / "waverider" / "sharc"
    obj = json.loads((sharc / "inspost.json").read_text())
    entry = GEN.label_sw((sharc / "inspost.asm").read_text(), obj["instruction_offsets"], int(obj["load_sw"], 16),
                         f"wr_ip_{POST.JUNO_ENTRY}")
    ends = [hi for lo, hi, name in code if name == "inspost" and lo <= entry < hi]
    assert len(ends) == 1, ("JUNO's copy is not inside inspost.asm's code", hex(entry))
    return entry, ends[0]


class Watch:
    """the write watch: (area, writer) -> count, the first (block, pc, address) of each"""

    def __init__(self):
        reg = dsp.regions()
        areas = [(w, lo, hi) for w, lo, hi, _c in reg] + STOCK_AREAS + extra_areas()
        self.areas = areas
        self.lo = sorted({lo for _w, lo, _h in areas})
        self.code = []                                  # (sw_lo, sw_hi, name)
        for what, at, payload in dsp.l2_spans():
            if ".asm" in what:
                self.code.append((0xB80000 + (at - 0x20000000) // 2, 0xB80000 + (at - 0x20000000 + len(payload)) // 2,
                                  what.split(".asm")[0].split()[-1]))
        for what, at, payload in dsp._raw_spans():
            if ".asm" in what:
                self.code.append((at // 2, (at + len(payload) + 64) // 2, what.split(".asm")[0].split()[-1]))
        self.code.sort()
        self.code_lo = [c[0] for c in self.code]
        self.juno_lo, self.juno_hi = juno_copy_span(self.code)
        self.juno_caller = "inspost"                    # who entered JUNO's one copy last (note_jret)
        self.counts = collections.Counter()
        self.first = {}
        self.armed = False
        self.block = -1

    def writer(self, pc) -> str:
        if pc is None:
            return "?"
        if self.juno_lo <= pc < self.juno_hi:          # JUNO's one copy writes for whoever called it
            return self.juno_caller
        k = bisect.bisect_right(self.code_lo, pc) - 1
        if k >= 0 and self.code[k][0] <= pc < self.code[k][1]:
            return self.code[k][2]
        return "stock"

    def where(self, a: int) -> list[str]:
        if 0x28000000 <= a < 0x28400000:               # the byte alias of L1
            a -= 0x28000000
        hit = [w for w, lo, hi in self.areas if lo <= a < hi]
        if hit:
            return hit
        if 0x80000000 <= a < 0xA0000000:
            return [f"UNMAPPED DDR page {a & ~0xFFFFF:#x}"]
        if 0x20000000 <= a < 0x20100000:
            return [f"UNMAPPED L2 page {a & ~0xFFF:#x}"]
        return []                                       # L1 stock / MMR / others: not watched

    def note_jret(self, address, value) -> None:
        """the copy's first instruction stores the caller's return address - 1 (I12) in C['jret']: the code that
        holds return address is the caller, the writer of every word the copy writes until the next entry"""
        a, v = getattr(address, "value", address), getattr(value, "value", value)
        if a == JUNO_JRET and isinstance(v, int):
            self.juno_caller = self.writer_static(v + 1)

    def writer_static(self, pc: int) -> str:
        k = bisect.bisect_right(self.code_lo, pc) - 1
        if k >= 0 and self.code[k][0] <= pc < self.code[k][1]:
            return self.code[k][2]
        return "stock"

    def note(self, state, address, width):
        if not self.armed:
            return
        a = getattr(address, "value", address)
        if not isinstance(a, int):
            return
        if not (0x80000000 <= a < 0xA0000000 or 0x20000000 <= a < 0x20100000 or 0x2DD600 <= a < 0x320000
                or 0x282DD600 <= a < 0x28320000):
            return
        pc = getattr(state, "pc_sw", None)
        w = self.writer(pc)
        for area in self.where(a):
            key = (area, w)
            self.counts[key] += 1
            if key not in self.first:
                self.first[key] = (self.block, pc, a)

    def foreign(self) -> list[tuple]:
        out = []
        for (area, w), n in self.counts.items():
            for pre, owners in OWNERS:
                if area.startswith(pre) and w not in owners:
                    out.append((area, w, n, self.first[(area, w)]))
        return sorted(out)

    def table(self) -> list[str]:
        rows = collections.defaultdict(dict)
        for (area, w), n in self.counts.items():
            rows[area][w] = n
        return [f"{area[:80]}: {dict(sorted(ws.items()))}" for area, ws in sorted(rows.items())]


WATCH: Watch | None = None


def install(watch: Watch) -> None:
    import sharc_core.memory as mem
    orig = getattr(mem._dm_write, "__wrapped_ghost__", mem._dm_write)

    def w(state, address, width, value):
        watch.note_jret(address, value)
        watch.note(state, address, width)
        return orig(state, address, width, value)
    w.__wrapped_ghost__ = orig
    for m in list(sys.modules.values()):
        cur = getattr(m, "_dm_write", None)
        if cur is orig or getattr(cur, "__wrapped_ghost__", None) is orig:
            try:
                setattr(m, "_dm_write", w)
            except (AttributeError, TypeError):
                pass


def f32(w) -> float:
    return struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0]


def fb(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def peak(words) -> float:
    m = 0.0
    for w in words:
        x = f32(w)
        if not math.isfinite(x):
            return float("inf")
        m = max(m, abs(x))
    return m


def rec(typ, inst, mix, *k):
    return [typ | inst << D.TYPE_BITS, mix] + list(k) + [0] * (6 - len(k))


def bus_table(on: bool, b: int = 0) -> bytes:
    """GHOST_BUS: long (XDLY FDBK 100, FDN8 SIZE 90: tails of seconds), short (XDLY FDBK 20, FDN8 SIZE 5: under -80 dB within ~0.7 s), moved (short, a TAPE in slot 2 under each: moved to the bus), off"""
    out = bytearray(8 * D.RECORDS)
    mode = os.environ.get("GHOST_BUS", "short")
    if on and mode != "off":
        rows = {(0, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 0, 90), (1, 0): rec(D.FDN8, 0, 127, 10, 90, 30, 64, 0, 127)}
        if mode in ("short", "moved"):
            rows = {(0, 0): rec(D.XDLY, 0, 127, 3, 4, 20, 0, 90), (1, 0): rec(D.FDN8, 0, 127, 0, 5, 100, 0, 0, 127)}
        if mode == "moved":                                   # 2026-11-20: a TAPE in slot 2 under each, moved to the
            for t in (0, 1):                                  # bus (design.moved): its rings at MV_RING_DDR
                rows[(t, 1)] = rec(D.TAPE, 0, 127, 64, 64, 64, 64, 64, 64)
        jump = int(os.environ.get("GHOST_XJUMP", "0") or 0)   # from this block on, XDLY's times at 10 s: the heads
        if jump and b >= jump:                                # jump into the lines' never-written part
            rows[(0, 0)] = rec(D.XDLY, 0, 127, 127, 127, rows[(0, 0)][4], 0, 90)
        for (t, j), v in rows.items():
            out[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
    return bytes(out)


def voice(M5, name: str | None):
    """(t0, overrides) for the slot-0 voice"""
    from dnfw.mnm import machines as MM
    from dnfw.perc import machines as PM
    name = name or ("DRUM" if "DRUM" in MM.NAMES else "PI-SD")
    if name in MM.NAMES:
        k = MM.NAMES.index(name)
        knobs = list(MM.DEFAULTS[name])
        for kv in filter(None, os.environ.get("GHOST_KNOBS", "").split(",")):   # "7=79": PLAITS' MODL on STRG
            j, v = (int(x) for x in kv.split("="))
            knobs[j] = v
        return name, MM.TYPES[k], M5.mnm_words(k, tuple(knobs))
    return name, 5, M5.perc_words(PM.NAMES.index(name))


def stale_fill(M5, st, seed: int) -> int:
    """the run-time (unloaded) delay areas filled with noise, as a unit's memory holds old audio"""
    from dnfw.engines.plaits import plk
    rnd = random.Random(seed)
    areas = [(D.MV_RING_DDR, D.MV_INSTANCES * 2048), (plk.BIG_DDR, 16 * plk.BIG_STRIDE),
             (D.FDN8_RING_DDR, D.FDN8_INSTANCES * D.FDN8_RING_STRIDE),
             (D.XDLY_LINES_DDR, D.XDLY_INSTANCES * D.XDLY_LINES_STRIDE),
             (dsp.PARA_POOL_L2, dsp.PARA_POOL_BYTES)]
    # 2026-11-20, measured on the unit (SCAN, idle, 42 min after power-on): every other word of these areas is
    # non-finite (the bus FDN8 rings, the bus XDLY lines, PLAITS' big buffers: the odd words; the moved inserts'
    # rings: the even ones). So: odd words NaN (0xFFFFFFFF), even words noise
    words = [0xFFFFFFFF if k & 1 else fb(rnd.uniform(-0.25, 0.25)) for k in range(4096)]
    n = 0
    for lo, size in areas:
        for k in range(0, size, 4):
            M5.m2.poke(st, lo + k, words[(k >> 2) & 4095])
            n += 1
    return n


def scenario(M5, snap, m2mach, img, sound, machines, *, ours: bool, hits, n: int, stale: bool, probe: bool,
             levels: bool, vname=None, keep=False) -> dict:
    m2 = M5.m2
    watch = WATCH
    rnd = random.Random(5)
    init = M5.init_on(snap, m2mach, img, warm=True)
    if stale:
        stale_fill(M5, init.state, 99)
    if levels:
        m2.poke(init.state, dsp.SMP_POOL_DDR + SM.LV_WANT_OFF, SM.LV_WANT)
    if ours:
        name, t0, words = voice(M5, vname)
    else:
        name, t0, words = "WAVETONE", 1, {}
    send = int(os.environ.get("GHOST_SEND", str(0x7F00)), 0)
    words = {**words, **{s: send for s in SEND_SLOTS}}
    glob = {o: (0 if ours else 0x2000) for o in FX_TYPE_OFFSETS}
    if not ours or os.environ.get("GHOST_DTIME0"):
        glob[0x9C8 + 2 * 32] = 0                       # the delay's TIME (k 32) at its shortest

    def frame(b):
        f = M5.base_frame(sound, machines, t0=t0, overrides=words, trigger=b in hits)
        for o, v in glob.items():
            f.put(o, v)
        return f.to_bytes()

    hit_end = max(hits, default=-1) + 24
    series, digests, cur, trace = [], [], {}, []

    def at_bus(r):
        st = r.state
        if not ours:
            return
        b = watch.block
        loud = 1.0 if b in range(min(hits, default=10 ** 9), hit_end) else 0.0
        watch.armed = False
        for t in (0, 1):
            for j in range(32):
                x = rnd.uniform(-loud, loud) if loud else 0.0
                m2.poke(st, D.BUS_BLOCKS + 0x100 * t + 4 * j, fb(x))
                m2.poke(st, D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j, fb(x * 0.7))
        tab = bus_table(True, b)
        for k, v in enumerate(tab):
            m2.poke(st, D.TABLE + 4 * k, v)
        for k, v in enumerate(D.flags(tab)):
            m2.poke(st, D.FLAGS + 4 * k, v)
        watch.armed = True

    def at_bus_out(r):
        st = r.state
        cur["bus"] = [m2.word(st, D.BUS_BLOCKS + 0x100 * t + o + 4 * j) or 0
                      for t in range(16) for o in (0, D.BUS_R) for j in range(32)]

    def at_chorus(r):
        if ours:
            watch.armed = False
            m2.poke(r.state, D.JS_TYPE, D.JS_JUNO)
            watch.armed = True

    def at_out(r):
        st = r.state
        cur["main"] = [m2.word(st, MAIN[0] + 4 * k) or 0 for k in range(MAIN[1])]
        cur["ret"] = [m2.word(st, FX_RETURNS[0] + 4 * k) or 0 for k in range(FX_RETURNS[1])]

    def at_delay(r):
        if not ours and watch.block == 0:
            watch.armed = False
            m2.poke(r.state, 0x8005912C + 0x400104, 1024)
            m2.poke(r.state, 0x8005912C + 0x400240, fb(1024.0))
            watch.armed = True

    hooks = {OUTPUT_CALL_SW: at_out, dsp.CHORUS_SITE_SW: at_chorus, dsp.DELAY_SITE_SW: at_delay}
    if ours:
        hooks[dsp.INSBUS_SW] = at_bus
        hooks[B.RESUME_SW] = at_bus_out
    state = init
    halt = None
    import time
    t_0 = time.time()
    for b in range(n):
        watch.block = b
        cur.clear()
        if probe and b == 0:
            m2.poke(state.state, dsp.SMP_POOL_DDR + SM.CMD_OFFSET, 0x7001)
            for k, v in enumerate((SM.CMD_PROBE, 0, 0, 0, 0)):
                m2.poke(state.state, dsp.SMP_POOL_DDR + SM.CMD_OFFSET + 4 + 4 * k, v)
        f = M5.fixups(hooks)
        r = M5.m4.unpack_call(state, frame(b))
        watch.armed = True
        res = M5.fx.run(r, 8_000_000, f)
        watch.armed = False
        if not (res[0] == "halt" and res[1].pc_sw == M5.m4.UNPACK_RETURN):
            halt = f"block {b}: {res[0]} {getattr(res[1], 'reason', res[1])}"
            break
        state = r
        pk = {k: peak(cur.get(k, [])) for k in ("main", "ret", "bus")}
        series.append(pk)
        if os.environ.get("GHOST_TRACE") and "bus" in cur:
            bw = cur["bus"]
            trace.append((b, round(peak(bw[0:64]), 8), round(peak(bw[64:128]), 8), round(peak(bw[128:]), 8),
                          [m2.word(state.state, a) for a in TRACE_WORDS]))
        digests.append(hashlib.sha256(struct.pack(f"<{len(cur.get('main', [])) + len(cur.get('ret', [])) + len(cur.get('bus', []))}I",
                                                  *(cur.get("main", []) + cur.get("ret", []) + cur.get("bus", []))))
                       .hexdigest()[:16])
        if b % 100 == 0:
            print(f"    ghost: block {b}/{n} {time.time() - t_0:.0f} s peaks {pk}", flush=True)
    loud = [max(p.values()) for p in series]
    last_loud = max((b for b, x in enumerate(loud) if x > LATE), default=None)
    late = []
    quiet = 0
    for b, x in enumerate(loud):
        if b <= hit_end:
            continue
        if x <= SILENT:
            quiet += 1
        else:
            if quiet >= LATE_GAP and x > LATE:
                late.append((b, x))
            quiet = 0
    out = {"voice": name, "blocks": len(series), "halt": halt, "wall_s": round(time.time() - t_0),
           "last block above LATE": last_loud, "late returns (block, peak)": late[:20],
           "peaks every 50 blocks": [round(max(loud[k:k + 50]), 7) for k in range(0, len(loud), 50)],
           "peaks every 50 blocks, by capture": {key: [round(max(p[key] for p in series[k:k + 50]), 7)
                                                       for k in range(0, len(series), 50)]
                                                 for key in ("main", "ret", "bus")},
           "never above SILENT": all(x <= SILENT for x in loud)}
    if trace:
        out["trace (block, track 0 peak, track 1 peak, others, words)"] = trace
    if keep:
        out["digests"] = digests
        out["loud"] = loud
    if probe:
        C = M5.SMP_L.C
        out["probe pph/pix/pres"] = [m2.word(state.state, C[k]) for k in ("pph", "pix", "pres") if k in C]
    return out


# the gate's parts (sharc_waverider_m5 steps ghost-z, ghost-d, ghost-h): (scenarios, blocks)
PARTS = {"ghost-z": ("Z", 400), "ghost-d": ("D", 400), "ghost-h": ("H", 600)}


def run(M5, snap, m2mach, m5img, stockimg, sound, machines, part: str | None = None) -> dict:
    global WATCH
    WATCH = Watch()
    install(WATCH)
    dscen, dn = PARTS.get(part, ("Z,H,S,D", 600))
    scen = os.environ.get("GHOST_SCEN", dscen).split(",")
    n = int(os.environ.get("GHOST_N", str(dn)))
    hits = tuple(int(x) for x in os.environ.get("GHOST_HITS", "1,13,25").split(","))
    vname = os.environ.get("GHOST_VOICE") or None
    checks, numbers = {}, {}
    if "Z" in scen:
        zc = scenario(M5, snap, m2mach, m5img, sound, machines, ours=True, hits=(), n=n // 2, stale=False, probe=False,
                      levels=True, vname=vname, keep=True)
        zs = scenario(M5, snap, m2mach, m5img, sound, machines, ours=True, hits=(), n=n // 2, stale=True, probe=False,
                      levels=True, vname=vname, keep=True)
        same = zc["digests"] == zs["digests"]
        first = next((b for b, (x, y) in enumerate(zip(zc["digests"], zs["digests"])) if x != y), None)
        checks["Z: no input ever: silent (every output word <= 1e-6), zeroed memory"] = zc["never above SILENT"]
        checks["Z: no input ever, stale noise in the unloaded delay areas: bit-identical to zeroed, silent"] = (
            same and zs["never above SILENT"])
        for d in (zc, zs):
            d.pop("digests"), d.pop("loud")
        numbers["Z zeroed"], numbers["Z stale"] = zc, zs
        numbers["Z first differing block"] = first
    if "H" in scen:
        h = scenario(M5, snap, m2mach, m5img, sound, machines, ours=True, hits=hits, n=n, stale=False, probe=True,
                     levels=True, vname=vname)
        checks["H: ours after the hits: no late return"] = h["halt"] is None and not h["late returns (block, peak)"]
        numbers["H ours"] = h
    if "S" in scen:
        s = scenario(M5, snap, m2mach, m5img, sound, machines, ours=False, hits=hits, n=n, stale=False, probe=False,
                     levels=False)
        checks["S: stock FX after the hits: no late return"] = s["halt"] is None and not s["late returns (block, peak)"]
        numbers["S stock"] = s
    if "D" in scen:
        nd = int(os.environ.get("GHOST_ND", str(n // 2)))
        a = scenario(M5, snap, m2mach, m5img, sound, machines, ours=True, hits=hits, n=nd, stale=False, probe=False,
                     levels=True, vname=vname, keep=True)
        b = scenario(M5, snap, m2mach, m5img, sound, machines, ours=True, hits=hits, n=nd, stale=True, probe=False,
                     levels=True, vname=vname, keep=True)
        first = next((k for k, (x, y) in enumerate(zip(a["digests"], b["digests"])) if x != y), None)
        checks["D: hits, stale noise in the unloaded delay areas: every output bit-identical to zeroed"] = (
            first is None and len(a["digests"]) == len(b["digests"]) == nd)
        numbers["D first differing block"] = first
        if first is not None:
            numbers["D loud zeroed/stale near it"] = (a["loud"][first:first + 8], b["loud"][first:first + 8])
    fr = WATCH.foreign()
    checks["watch: no FOREIGN write into a delay line / ring / FX state"] = not fr
    um = sorted((a, w, c) for (a, w), c in WATCH.counts.items() if a.startswith("UNMAPPED"))
    checks["watch: no write into DDR / L2 outside every known area"] = not um
    numbers["watch: UNMAPPED (area, writer, count)"] = um
    numbers["watch: FOREIGN (area, writer, count, first (block, pc, address))"] = [
        (a, w, c, (f[0], hex(f[1] or 0), hex(f[2]))) for a, w, c, f in fr]
    numbers["watch: area <- writer counts"] = WATCH.table()
    return {"ok": bool(checks) and all(checks.values()), "checks": checks, "numbers": numbers}
