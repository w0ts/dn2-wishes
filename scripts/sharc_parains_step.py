"""2026-11-15 (main: "inserts running on members' silent slots can cost more than PARA saves"): the SHARC runner's
PARA + inserts check, part of step para (scripts/sharc_waverider_m5.step_para). Each PARA engine's 4-note chord
(a2_para_frames: slots 0..3 on track 0, slot 3 leads, 0..2 members) with a voice insert on track 0 in each pass:
FUZZ in slot 1 (the pre pass, dnfw.inserts.program) and CHOR in slot 2 (the post pass, dnfw.inserts.post).

Two runs a engine, the same build and frames:
  after:  as built: the passes read the chord's ROLE words and play the members' inserts as OFF;
  before: the ROLE words hidden from the passes (zeroed at the pre pass's entry, put back at the sends': PERC
          reads them before and after, so its output is the same), so the passes run every slot as before the fix.

Checks: in AFTER, each block, every slot after each pass is the reference's (dnfw.inserts.ref, postref) with the
members off their track, bit for bit; the leader's buffer and stereo block after each pass are BEFORE's, bit for
bit (its inserts unchanged); the members' are their input (no insert ran). Numbers: each pass's instructions a
block (from block FROM on), before and after: the members' insert cost that is gone.
"""

from __future__ import annotations

import struct

import numpy as np

from dnfw.engines.analog2 import para as PA
from dnfw.inserts import design as D
from dnfw.inserts import post as P
from dnfw.inserts import postref as PR
from dnfw.inserts import ref as R
from dnfw.waverider import dsp

SLOTS = 4                                        # the chord's slots (0..3; 3 leads)
LEADER = 3
FROM = 4                                         # cost from this block (the chord formed, the records unpacked)
FUZZ = [D.FUZZ, 127, 90, 70, 20, 40, 0, 100]
CHOR = [D.CHOR, 90, 80, 50, 60, 127, 100, 60]


def bf(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])


def fb(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def table() -> bytes:
    """track 0: FUZZ in slot 1, CHOR in slot 2 (CHOR is a mover only in slot 1)"""
    p1, p2 = bytearray(128), bytearray(128)
    p1[0:8], p2[0:8] = bytes(FUZZ), bytes(CHOR)
    return D.records(bytes(p1), bytes(p2))


def masked(route: list[int], roles: list[int]) -> list[int]:
    return [0xFFFF if (roles[s] >> PA.ROLE_SHIFT) & 1 else route[s] for s in range(16)]


def one_run(M5, init, fbytes, blocks: int, hide: bool) -> dict:
    m2 = M5.m2
    recs = table()
    gen = D.pack(recs, 1)
    caps, cur = [], {}

    def stereo(st):
        return ([[m2.word(st, D.STEREO + D.STEREO_STRIDE * s + 4 * j) or 0 for j in range(32)] for s in range(16)],
                [[m2.word(st, D.STEREO + D.STEREO_STRIDE * s + D.STEREO_R + 4 * j) or 0 for j in range(32)]
                 for s in range(16)])

    def at_perc(r):
        for k, w in enumerate(gen):
            m2.poke(r.state, D.GEN + 4 * k, w)

    def at_ins(r):
        st = r.state
        cur.clear()
        cur["roles"] = [m2.word(st, PA.ROLE + 4 * u) or 0 for u in range(16)]
        if hide:
            for u in range(16):
                m2.poke(st, PA.ROLE + 4 * u, 0)
        cur["ptr"] = [m2.word(st, D.BUFFERS + 4 * t) or 0 for t in range(16)]
        cur["in"] = [[m2.word(st, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
        cur["route"] = [((m2.word(st, D.ROUTE + 4 * (s // 2)) or 0) >> (16 * (s & 1))) & 0xFFFF for s in range(16)]
        cur["s_ins"] = r.steps_n

    def at_ping(r):
        cur["out"] = [[m2.word(r.state, cur["ptr"][t] + 4 * j) or 0 for j in range(32)] for t in range(16)]
        cur["pre"] = r.steps_n - cur["s_ins"]

    def at_post(r):
        if "out" in cur:
            cur["st_in"] = stereo(r.state)
            cur["s_post"] = r.steps_n

    def at_sends(r):
        if "st_in" in cur and "st_out" not in cur:
            cur["st_out"] = stereo(r.state)
            cur["post"] = r.steps_n - cur["s_post"]
            if hide:
                for u, w in enumerate(cur["roles"]):
                    m2.poke(r.state, PA.ROLE + 4 * u, w)
            caps.append(dict(cur))
    out = M5.run_blocks(init, fbytes, blocks, extra_hooks={dsp.PERC_SW: at_perc, dsp.INS_SW: at_ins,
                                                           dsp.PING_SW: at_ping, dsp.POST_SW: at_post,
                                                           P.SENDS_SW: at_sends})
    return {"ok": bool(out.get("ok")) and len(caps) == blocks, "halt": str(out.get("halt")), "caps": caps,
            "recs": recs}


def exact_to_refs(run: dict) -> tuple[bool, int | None]:
    """every slot after each pass as the references' with the members off their track"""
    ref, pref = R.Ref(), PR.PostRef()
    for b, c in enumerate(run["caps"]):
        rt = masked(c["route"], c["roles"])
        bufs = [[bf(w) for w in c["in"][t]] for t in range(16)]
        ref.block(run["recs"], bufs, rt)
        lin = [[bf(w) for w in c["st_in"][0][s]] for s in range(16)]
        rin = [[bf(w) for w in c["st_in"][1][s]] for s in range(16)]
        pref.block(run["recs"], lin, rin, rt)
        if (c["out"] != [[fb(x) for x in row] for row in bufs]
                or c["st_out"] != ([[fb(x) for x in row] for row in lin], [[fb(x) for x in row] for row in rin])):
            return False, b
    return True, None


def run(M5, init, frames_of, engines) -> dict:
    """FRAMES_OF(para, engine) -> a frame function; ENGINES: (engine, tag). Returns checks and numbers"""
    checks, numbers = {}, {}
    blocks = M5.A2_PARA_BLOCKS
    for engine, tag in engines:
        fbytes = frames_of(3, engine)
        after = one_run(M5, init, fbytes, blocks, False)
        before = one_run(M5, init, fbytes, blocks, True)
        ok = after["ok"] and before["ok"]
        ca, cb = after["caps"], before["caps"]
        members = [u for u in range(SLOTS) if u != LEADER]
        chord = ok and all((ca[b]["roles"][u] >> PA.ROLE_SHIFT) & 3 == PA.MEMBER for b in range(FROM, blocks)
                           for u in members) and all((ca[b]["roles"][LEADER] >> PA.ROLE_SHIFT) & 3 == PA.LEADER
                                                     for b in range(FROM, blocks))
        exact, bad = exact_to_refs(after) if ok else (False, None)
        leader_same = ok and all(ca[b]["out"][LEADER] == cb[b]["out"][LEADER]
                                 and ca[b]["st_out"][0][LEADER] == cb[b]["st_out"][0][LEADER]
                                 and ca[b]["st_out"][1][LEADER] == cb[b]["st_out"][1][LEADER] for b in range(blocks))
        leader_changed = ok and any(ca[b]["out"][LEADER] != ca[b]["in"][LEADER] for b in range(FROM, blocks)) and any(
            ca[b]["st_out"][0][LEADER] != ca[b]["st_in"][0][LEADER] for b in range(FROM, blocks))
        members_untouched = ok and all(ca[b]["out"][u] == ca[b]["in"][u] and ca[b]["st_out"][0][u] == ca[b]["st_in"][0][u]
                                       and ca[b]["st_out"][1][u] == ca[b]["st_in"][1][u]
                                       for b in range(FROM, blocks) for u in members)
        n = max(blocks - FROM, 1)
        cost = {k: {"pre": sum(c["pre"] for c in r["caps"][FROM:]) // n,
                    "post": sum(c["post"] for c in r["caps"][FROM:]) // n}
                for k, r in (("before", before), ("after", after))} if ok else None
        gone = (cost["before"]["pre"] + cost["before"]["post"] - cost["after"]["pre"] - cost["after"]["post"]) if ok else None
        numbers[f"parains_{tag}"] = {"cost_per_block": cost, "members_cost_gone": gone, "first_mismatch": bad,
                                     "halt": None if ok else (after["halt"], before["halt"]),
                                     "roles_last": [hex(w) for w in ca[-1]["roles"][:SLOTS]] if ok and ca else None}
        checks[f"{engine} PARA with inserts (FUZZ pre, CHOR post on the chord's track): every slot after each pass is "
               "the references' with the members off their track, every block, bit for bit"] = chord and exact
        checks[f"{engine} PARA with inserts: the leader's buffer and stereo block after each pass are bit-identical to "
               "the run with the roles hidden from the passes (its inserts unchanged), and the inserts change it"] = (
            leader_same and leader_changed)
        checks[f"{engine} PARA with inserts: the members' inserts do not run (their buffers and stereo blocks pass "
               "untouched) and the passes cost less than with the roles hidden"] = (
            members_untouched and gone is not None and gone > 0)
    return {"checks": checks, "numbers": numbers}
