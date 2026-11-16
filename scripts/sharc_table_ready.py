"""The tables' READY with this build's checksum, on the SHARC runner (docs/mnm.md, "READY carries this build's
checksum"): the DSP's own decode (a cold init: nothing pre-filled) in three cases, JUNO's note at block NOTE (its
tables are zpack's last words, so a wrong decode shows there first):

  (a) another build's ready word in DDR (the magic, a wrong checksum) over another build's table bytes (zpack's
      tail zeroed): the decode must wait; at block READY_AT the ColdFire's tables and READY arrive, it decodes, JUNO plays;
  (b) this build's word kept from the boot before (a restart on the same build): it decodes at once, JUNO plays;
  (c) a cold DDR (nothing there): it waits for READY at block READY_AT, then decodes, JUNO plays.

Each case: the decode's position (fill) before and after READY_AT, JUNO's peaks after its note, and the PERC
voices' bit-exactness to the model. The runner's step `tableready` (sharc_waverider_m5.py, gate_sharc's part of its
own, about 15 min); alone:
    python scripts/sharc_table_ready.py IMAGE DIGIKIT"""
import pathlib
import struct
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
from dnfw.md import core as MDK  # noqa: E402
from dnfw.mnm import machines as MM  # noqa: E402
from dnfw.perc import live as PL  # noqa: E402
from dnfw.sampler import machines as SM  # noqa: E402

READY_AT, NOTE, AFTER = 20, 80, 48
STALE_TAIL = 4000                         # bytes of zpack's end (JUNO's words) another build did not have
PLAYS = 0.1                               # JUNO's peak at its defaults is ~1.0 on PERC's series (warm init)


def run(M5, snap, m2mach, m5img, stockimg, sound, machines) -> dict:
    """cases a, b, c on the runner module M5 (sharc_waverider_m5) -> {"ok", "checks", "numbers"}"""
    m2 = M5.m2
    jk = MM.NAMES.index("JUNO")
    jt = dict(enumerate(MM.TYPES))[jk]
    L = PL.layout().md
    shipped, at, total = MDK.tables_bytes(), L.T[MDK.SHIPPED], MDK.table_sum()
    words = [struct.unpack_from("<I", shipped, k)[0] for k in range(0, len(shipped), 4)]
    zend = 4 * (MDK.TABLE_LAYOUT["hostP"][1] + MDK.TABLE_LAYOUT["zpack"][1])   # zpack's end (PERC's own tables after)
    stale_from, stale_to = (zend - STALE_TAIL) // 4, zend // 4

    def ready(st, magic, s):
        m2.poke(st, L.ready, magic)
        m2.poke(st, L.ready + SM.TABLE_SUM_AT, s)

    def ship(st):
        for k, w in enumerate(words):
            m2.poke(st, at + 4 * k, w)

    def fb(b):
        return M5.base_frame(sound, machines, t0=jt, overrides=M5.mnm_words(jk, None), note=0x3C00,
                             trigger=b == NOTE).to_bytes()

    checks, numbers = {}, {}
    for case, what in (("a", "another build's ready word: waits, decodes after READY"),
                       ("b", "this build's word kept: decodes at once"),
                       ("c", "a cold DDR: waits, decodes after READY")):
        init = M5.init_on(snap, m2mach, m5img, warm=False)          # this build's tables and READY, as today
        if case == "a":
            for k in range(stale_from, stale_to):
                m2.poke(init.state, at + 4 * k, 0)
            ready(init.state, SM.TABLE_MAGIC, (total ^ 0x5A5A5A5A) & 0xFFFFFFFF)
        elif case == "c":
            ready(init.state, 0, 0)
        seen = {"n": 0, "fill": []}

        def at_dispatch(r, case=case, seen=seen):
            seen["fill"].append(m2.word(r.state, L.C["fill"]) or 0)
            if case in "ac" and seen["n"] == READY_AT:              # the ColdFire's tables, then READY
                ship(r.state)
                ready(r.state, SM.TABLE_MAGIC, total)
            seen["n"] += 1
        rr = M5.run_blocks(init, fb, NOTE + AFTER, extra_hooks={M5.m3.DISPATCH: at_dispatch})
        s = M5.perc_series(rr, 0)
        B = M5.BLOCK
        pk = [round(M5.V.peak(s[k * B:(k + 8) * B]), 4) for k in range(NOTE, NOTE + AFTER, 8)]
        f = seen["fill"]
        before = f[READY_AT - 1] if len(f) >= READY_AT else None
        after = f[-1] if f else None
        timing = before == 0 if case in "ac" else (len(f) > 2 and f[2] > 0)
        exact = M5.perc_exact(rr)
        checks[f"({case}) {what}; whole, JUNO plays"] = (bool(rr["ok"]) and timing and after == MDK.Z_N
                                                        and max(pk or [0]) > PLAYS)
        numbers[case] = {"fill_before_ready": before, "fill_end": after, "peaks": pk, "exact": exact}
        print(f"  case {case}: fill before READY {before}, at the end {after} (Z_N {MDK.Z_N}); JUNO peaks/8 blocks "
              f"{pk}; exact {exact}", flush=True)
    return {"ok": all(checks.values()), "checks": checks, "numbers": numbers}


def main() -> int:
    import sharc_waverider_m5 as R
    from dnfw.waverider import dsp
    image, digikit = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    dk = R.m1.Digikit(digikit)
    R.fx.bind(str(digikit / "tools"))
    R.m4.IMAGE = image
    stock = R.m1.dn2_section7(image)
    sound, machines = R.m4.init_sound(image)
    m5 = R.Image(dk, dsp.section7(stock))
    R.OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=R.OUT) as tmp:
        snap, m2mach = R.snapshot_path(dk, stock, pathlib.Path(tmp))
        res = run(R, snap, m2mach, m5, stock, sound, machines)
    for k, v in res["checks"].items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"\n  table ready: {'PASS' if res['ok'] else 'FAIL'}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
