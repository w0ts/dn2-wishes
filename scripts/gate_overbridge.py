"""Overbridge's code untouched (docs/ROADMAP.md 1b; v0.41): no byte the build changes in MAIN OS
lies in an instruction Overbridge's audio path can execute.

    python scripts/gate_overbridge.py STOCK_SECTION_3 BUILD_SECTION_3 [--json OUT]

Overbridge's audio is moved by stock code we never patch (docs/link-research.md):
- 0x40003118 builds the 140-byte USB packets in mode 6 (SHARC RX slots 0..13 and the reply
  records: main, tracks, FX returns, input);
- 0x40003376 puts the DAW's audio into TX slots 0..7;
- 0x40004734 is the USB writer; 0x40006c4a the getter of the USB mode (5 class audio, 6 Overbridge);
- the audio interrupt 0x40025e36, up to the mod's link hook at 0x40026098, picks the mode and
  runs those fills (the hook sits where every transmit-fill mode has ended, and is the one
  patch the interrupt carries: docs/sampler.md "The fast link").

From those roots (and every instruction of the interrupt from 0x40025e36 up to the hook) the
stock code is followed by recursive descent: branches, both ways of a conditional one, and the
targets of bsr/jsr with an absolute or pc-relative address, until rts/rte/an indirect jump.
Every byte of every instruction reached must be stock's in the build. An indirect call (jsr
(a0)) is not followed; they are counted and listed, as what the check cannot see.
The mod's own link (TDM slots 8..15 in, 14..15 out) is clear of Overbridge's slots 0..13 by
design (docs/link-research.md); that is the hardware checklist's to confirm (docs/overbridge.md).

2026-11-18 (the User: "allow if bit identical yes and add a flag to switch back if needed"; the same
for csrc/obfast's Overbridge sites, DN2_OB_FAST): the declared sites (dnfw.waverider.coldfire
declared_sites: csrc/stocklink's, DN2_STOCK_LINK_FAST, and csrc/obfast's) are allowed in that path, each
only as the jump or call to its own code the composer writes there (an absolute jmp/jsr, then the
declared tail: nops over the rest of the displaced instructions, or obfast's bra.s to the loop's top).
They are proved byte for byte against stock's by the gate's linkfast step (scripts/check_stocklink.py
gate), which blocks. Any other byte the build changes in the path still fails; a build without them
(the flags off) is held to the rule as before.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from emulib.image import differences                           # noqa: E402

BASE = 0x40000400
ROOTS = {0x40003118: "the Overbridge packet builder (mode 6: RX slots 0..13 and the records to USB)",
         0x40003376: "the Overbridge input (mode 6: USB to TX slots 0..7)",
         0x40004734: "the USB writer",
         0x40006C4A: "the USB mode's getter"}
ISR, HOOK, HOOK_BYTES = 0x40025E36, 0x40026098, 8
# a stocklink site on: the stock code its routine calls or goes back into, walked as roots too (what the jump
# would hide from the walk is still checked)
STOCKLINK_ROOTS = {"skl_fill": (0x400CFA62, 0x400CFAB4), "skl_rcopy": (0x40134770,),
                   "skl_mode5": (0x40003EDE, 0x4013419C), "skl_modex": (0x4013419C,), "skl_isr_install": (),
                   "skl_usbout": (0x400253D0,), "skl_rxclr": (0x4013419C,), "obf_clr": (0x4013419C,),
                   "obf_build_pair": (0x40134770, 0x400032AE), "obf_in32": (0x40134770,)}   # csrc/obfast: stock's memcpy (and the builder after its sample loop)

LINE = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4} )+)\s*(\S+)\s*(.*)$")
ABS = re.compile(r"^(?:0x)?([0-9a-f]+)(?:\s|$|<)")


def disassemble(image: bytes, tmp: pathlib.Path) -> dict[int, tuple[int, str, str]]:
    """-> {va: (length, mnemonic, operands)} for the whole section (linear sweep)."""
    f = tmp / "ob_stock.bin"
    f.write_bytes(image)
    r = subprocess.run(["m68k-linux-gnu-objdump", "-D", "-b", "binary", "-m", "m68k:cfv4e",
                        f"--adjust-vma={BASE:#x}", str(f)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"objdump failed: {r.stderr[:200]}")
    out = {}
    for line in r.stdout.splitlines():
        m = LINE.match(line)
        if m:
            va = int(m.group(1), 16)
            out[va] = (2 * len(m.group(2).split()), m.group(3), m.group(4))
    return out


def target(ops: str) -> int | None:
    """the absolute target objdump prints for a branch or a call, None if indirect"""
    s = ops.strip()
    if s.startswith("%") or s.startswith("(") or "@" in s:
        return None
    m = ABS.match(s)
    return int(m.group(1), 16) if m else None


def reach(code: dict, roots: list[int], stop_at: set[int]) -> tuple[set[int], list[int]]:
    seen: set[int] = set()
    indirect: list[int] = []
    todo = list(roots)
    while todo:
        va = todo.pop()
        while va in code and va not in seen and va not in stop_at:
            seen.add(va)
            n, mn, ops = code[va]
            base = mn.split(".")[0]
            if base in ("rts", "rte", "halt", "illegal"):
                break
            if base in ("jmp", "bra"):
                t = target(ops)
                if t is None:
                    indirect.append(va)
                    break
                va = t
                continue
            if base in ("jsr", "bsr"):
                t = target(ops)
                if t is None:
                    indirect.append(va)
                else:
                    todo.append(t)
            elif base.startswith("b") and base not in ("bset", "bclr", "bchg", "btst", "bitrev", "byterev"):
                t = target(ops)                   # a conditional branch: both ways
                if t is not None:
                    todo.append(t)
            va += n
    return seen, indirect


def stocklink_sites():
    """the declared sites (dnfw.waverider.coldfire.declared_sites: csrc/stocklink's and csrc/obfast's):
    (va, stock bytes hex, symbol, call, what, the bytes after the jump or None for nops)"""
    sys.path.insert(0, str(HERE.parent / "src"))
    from dnfw.waverider.coldfire import declared_sites     # noqa: PLC0415
    return declared_sites()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("stock")
    p.add_argument("build")
    p.add_argument("--json")
    p.add_argument("--control", default=None, help="a root the build is known to patch: it must be found")
    a = p.parse_args()
    stock = pathlib.Path(a.stock).read_bytes()
    build = pathlib.Path(a.build).read_bytes()
    tmp = pathlib.Path(a.json).parent if a.json else pathlib.Path(".")
    code = disassemble(stock, tmp)
    changed: set[int] = set()
    for va, blob in differences(stock, build):
        if va + len(blob) <= BASE + len(stock):
            changed.update(range(va, va + len(blob)))
    allowed = set(range(HOOK, HOOK + HOOK_BYTES))
    linkfast, extra_roots = [], []
    for va, stock_hex, sym, call, _what, tail in stocklink_sites():
        n = len(stock_hex) // 2
        at = va - BASE
        have = build[at:at + n]
        if have == bytes.fromhex(stock_hex):
            continue
        rest = bytes.fromhex(tail) if tail else b""
        shape = have[:2] == bytes.fromhex("4eb9" if call else "4ef9") and \
            have[6:] == rest + bytes.fromhex("4e71") * ((n - 6 - len(rest)) // 2) and \
            not BASE <= int.from_bytes(have[2:6], "big") < BASE + len(stock)
        if shape:                       # the declared jump out of MAIN OS: allowed (linkfast proves it)
            allowed.update(range(va, va + n))
            linkfast.append(f"{va:#x} {sym}")
            extra_roots += list(STOCKLINK_ROOTS[sym])
    isr_part = [va for va in code if ISR <= va < HOOK]
    if a.control:                       # the negative control: the detector must see a patched site
        cs, _ = reach(code, [int(a.control, 0)], stop_at=set())
        chit = [va for va in cs if any(b in changed for b in range(va, va + code[va][0]))]
        print(("PASS" if chit else "FAIL") + f": the control from {a.control}: {len(chit)} patched "
              f"instructions found (must be some)")
        return 0 if chit else 1
    seen, indirect = reach(code, list(ROOTS) + isr_part + extra_roots, stop_at={HOOK})
    hits = sorted(va for va in seen
                  if any(b in changed and b not in allowed for b in range(va, va + code[va][0])))
    roots_found = {f"{r:#x}": r in code for r in ROOTS}
    ok = not hits and all(roots_found.values()) and len(seen) > 100
    rep = {"ok": ok, "instructions_reached": len(seen), "patched_bytes": len(changed),
           "hits": [f"{h:#x}" for h in hits[:20]], "indirect_calls_not_followed": len(indirect),
           "indirect_at": [f"{v:#x}" for v in indirect[:20]], "roots": roots_found,
           "hook_only_in_isr": all(b in allowed or b not in changed for b in range(ISR, HOOK + HOOK_BYTES)),
           "stocklink_sites_allowed": linkfast}
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))
    print(("PASS" if ok else "FAIL") + f": {len(seen)} instructions of Overbridge's path, "
          f"{len(hits)} touched by the build; {len(indirect)} indirect calls not followed"
          + (f"; {len(linkfast)} declared sites allowed (proved by linkfast)" if linkfast else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
