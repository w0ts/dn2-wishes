"""tb303_golden.py ENGINE [OUT.json | --check REF.json]: output hashes of one voice over many settings (knobs at
random and at their ends, notes 24..127, trigs and slides along the way, 48 blocks a case), to prove a change
bit-identical: write OUT.json on the old tree, --check it on the new. ANALOG2 / DRONE / TB303 / SOPHIE / JUNO (2026-11-20) / DRUM (2026-11-21) (opt-synths'
golden.py, 2026-11-12; NCASES random cases, default 24, NB blocks). Prints the max |difference| per case against
REF when not identical. Needs the firmware paths (DT2_SECTIONS ..) and PYTHONPATH=src."""
import hashlib, json, os, random, struct, sys
from dnfw.perc import live as PL, program as PP, machines as PM, dsl
from dnfw.md import core as MDK
from dnfw.mnm import machines as MM
from dnfw.engines.analog2 import analog2 as A2
from dnfw.engines.drone import drone as DR
from dnfw.engines.tb303 import tb303 as TB
from dnfw.engines.sophie import sophie as SO
from dnfw.engines.juno import juno as JU
from dnfw.engines.drum import drum as DRM

MODS = {"ANALOG2": A2, "DRONE": DR, "TB303": TB, "SOPHIE": SO, "JUNO": JU, "DRUM": DRM}
TYP = {MM.NAMES[k]: t for t, k in PP.MNM_TYPES.items()}
NB = int(os.environ.get("NB", "48"))
# HOLD=1 (2026-11-21): the note moves only at a trig (DRUM's live re-read follows a note moved mid-hit, by design)
HOLD = os.environ.get("HOLD", "") not in ("", "0")


def cases(name, n):
    M = MODS[name]
    n1, n2 = len(M.PNAMES), len(getattr(M, "PNAMES2", ()))
    rnd = random.Random(1234)
    d1 = list(MM.DEFAULTS[name])
    d2 = [x if isinstance(x, int) else round(x * 127) for x in getattr(M, "DEFAULTS2", ())]
    yield "default", d1, d2, 60.0
    for P in getattr(M, "PLACES", ()):                # DRUM (2026-11-21): each type at its start
        yield f"type.{P.NAME}", list(P.DEFAULTS), [round(x) for x in P.DEFAULTS2] + [0] * (8 - len(P.DEFAULTS2)), 60.0
    for k in range(n1):                               # each page-1 knob at its ends
        for v in (0, 127):
            a = list(d1); a[k] = v
            yield f"p1.{k}={v}", a, d2, 60.0
    for k in range(n2):
        for v in (0, 127, 64):
            b = list(d2); b[k] = v
            yield f"p2.{k}={v}", d1, b, 60.0
    for c in range(n):
        yield (f"rnd{c}", [rnd.randrange(128) for _ in range(n1)], [rnd.randrange(128) for _ in range(n2)],
               float(rnd.choice((24, 36, 48, 60, 72, 84, 96, 108, 127))))


def render(name, k1, k2, note, seed):
    h = PL.Harness(); h.words[h.L.md.C["fill"]] = MDK.Z_N
    if name == "ANALOG2":
        for k, v in enumerate(A2.table_words()):
            h.words[h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = dsl.bits(v)
    h.set_mnm(TYP[name], k1)
    for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, k2):
        h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
    rnd = random.Random(seed)
    out, cur = [], note
    for b in range(NB):
        trig = b == 0 or rnd.random() < 0.12
        nt = note if b < NB // 2 else max(0.0, min(127.0, note + rnd.choice((-12, -5, 0, 7, 12))))
        if trig or not HOLD:
            cur = nt
        out += h.block(note=cur, trig=trig)
    return out


def main():
    name = sys.argv[1]
    n = int(os.environ.get("NCASES", "24"))
    res = {}
    for i, (label, k1, k2, note) in enumerate(cases(name, n)):
        out = render(name, k1, k2, note, i)
        raw = struct.pack(f"{len(out)}f", *out)
        res[label] = {"hash": hashlib.sha256(raw).hexdigest()[:16], "out": out}
    if len(sys.argv) > 3 and sys.argv[2] == "--check":
        ref = json.load(open(sys.argv[3]))
        bad = 0
        for label, r in res.items():
            if ref[label]["hash"] != r["hash"]:
                bad += 1
                d = max(abs(a - b) for a, b in zip(ref[label]["out"], r["out"]))
                pk = max(abs(a) for a in ref[label]["out"]) or 1.0
                print(f"DIFF {label}: max |d| {d:.3g} (peak {pk:.3g})")
        print(f"{name}: {len(res) - bad}/{len(res)} identical")
        sys.exit(1 if bad else 0)
    json.dump(res, open(sys.argv[2], "w"))
    print(f"{name}: {len(res)} cases written")


main()
