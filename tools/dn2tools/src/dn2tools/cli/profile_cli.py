"""dn2test profile: what the ColdFire spends its time on (PROFILE, a test build since remoteui-5).

    dn2test profile --seconds 20 --label idle --out prof/ --stock-dis stock112.dis --ours waverider_code.json
    dn2test profile --compare prof/idle.json prof/busy.json      per function, A vs B (markdown)
    dn2test profile --report prof/idle.raw.json --stock-dis ...  the report again from a saved run
    dn2test profile --status | --stop                           the firmware's profiler state; stop a stray run

The unit only runs the sampler (its own RAM, DMA timer 0's compare, vector 96); the samples are read after
the run, then symbolized here. Without --stock-dis / --stock-bin / --stock-symbols the stock PCs are
named by 256-byte block; without --ours, the mod's by chunk.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from .. import profile as PR
from .. import symbols as S
from ..channel import TestChannel
from ..unit import NoTestChannel, StatusError
from .common import add_target_args, open_unit


def load_symbols(a) -> S.Symbols:
    stock: dict[int, str] = {}
    if a.stock_symbols:
        stock = {int(k): v for k, v in json.loads(pathlib.Path(a.stock_symbols).read_text()).items()}
    elif a.stock_dis:
        stock = S.parse_objdump(pathlib.Path(a.stock_dis).read_text())
    elif a.stock_bin:
        stock = S.parse_objdump(S.objdump_stock(a.stock_bin))
    else:
        stock = {k: v[0] for k, v in S.STOCK_NAMES.items()}
    ours, regions = S.ours_from_code_json(a.ours) if a.ours else ({}, [])
    return S.Symbols.build(stock, ours, regions)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="dn2test profile", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_target_args(ap)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--rate", type=int, default=997, help="samples a second asked (timer 10..10000; audio 10..1500)")
    ap.add_argument("--source", choices=("auto", "timer", "audio"), default="auto",
                    help="auto: the timer, else the audio interrupt (docs/remote-ui.md: the two sources' bias)")
    ap.add_argument("--label", default="profile")
    ap.add_argument("--out", default="profile-report")
    ap.add_argument("--stock-dis", default=None, help="objdump -D of the 1.12 MAIN OS (--adjust-vma=0x40000400)")
    ap.add_argument("--stock-bin", default=None, help="the 1.12 MAIN OS section: objdump is run on it")
    ap.add_argument("--stock-symbols", default=None, help="a stock_symbols.json an earlier run wrote")
    ap.add_argument("--ours", default=None, help="the build's src/dnfw/mods/waverider_code.json (its C functions)")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"), help="two reports: per function, A vs B")
    ap.add_argument("--report", default=None, metavar="RAW.json", help="the report again from a saved run")
    ap.add_argument("--status", action="store_true", help="the firmware's profiler status")
    ap.add_argument("--stop", action="store_true", help="stop a profile left running")
    a = ap.parse_args(argv)
    if a.compare:
        print(PR.compare(*a.compare))
        return 0
    sym = load_symbols(a)
    out = pathlib.Path(a.out)
    if a.report:
        r = PR.Run.from_json(json.loads(pathlib.Path(a.report).read_text()))
        j, m = PR.write(out, r, PR.analyse(r, sym), sym)
        print(f"report: {m}\njson:   {j}")
        return 0
    unit = open_unit(a)
    ch = TestChannel(unit)
    try:
        if a.status or a.stop:
            st = ch.profile_stop() if a.stop else ch.profile_status()
            for k, v in st.__dict__.items():
                print(f"{k:13s} {v:#x}" if isinstance(v, int) and k in ("dtim0", "dtrr0", "intc", "vector96", "ring")
                      else f"{k:13s} {v}")
            if st.why:
                print(f"why          {st.why_text}")
            return 0
        r = PR.run(ch, a.seconds, a.rate, a.source, a.label)
    except NoTestChannel as e:
        print(f"no test channel: {e}")
        return 2
    except StatusError as e:
        print(e)
        return 1
    finally:
        unit.close()
    res = PR.analyse(r, sym)
    j, m = PR.write(out, r, res, sym)
    if not a.stock_symbols and (a.stock_dis or a.stock_bin):
        cache = out / "stock_symbols.json"
        cache.write_text(json.dumps({str(k): v for k, v, o in zip(sym.starts, sym.names, sym.origin) if o == "stock"}))
    print(PR.markdown(res).split("## By interrupt mask")[0].rstrip())
    print(f"\nreport: {m}\njson:   {j}")
    return 0
