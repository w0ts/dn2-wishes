"""2026-11-20 (DRUM's room: the DSP upload had 267 B left): R12 loads that nothing reads, folded away over PERC's
whole program (every span: perc.asm, perc2a.asm, perc2b.asm), by its control flow; and over each other DSL program
of the upload (smp.asm, fdn8.asm, xdly.asm, inserts.asm, inspost.asm, jsend.asm, a2f.asm: fold_text).

R12 is the DSL's scratch. Three emitted shapes load it only to pass a value on in the next instruction:

- a leaf call: `R12 = <return address - 1>; I12 = R12; JUMP sub`        -> `I12 = <return address - 1>; JUMP sub`
- an I register's address: `R12 = K; In = R12`                         -> `In = K` (the stock's `I5 = 0x25d748`)
- a zero: `R12 = 0x0; Fd = FLOAT Rx BY R12` -> `Fd = FLOAT Rx`, `Rd = R12 - Rx` -> `Rd = -Rx`,
  `Rd = R12 + Rx` (or `Rx + R12`) -> `Rd = PASS Rx` (the same result and the same AZ / AN flags, the only ones the
  code tests: no AC, AV or CI in PERC)
- 2026-11-20 (CLAP and the cymbals' room; PERC's program only): an integer add's first operand moved through R12 (G5: an add takes R8..R15
  first): `R12 = PASS Ra; Rd = R12 + Rb` (or `Rb + R12`) with Rb in R8..R15 -> `Rd = Rb + Ra` (the same sum, the
  add's own flags last in both)

A site is folded only when R12 is DEAD after the pair: every path from the instruction after it writes R12 (F12)
without reading it, before any read. The paths follow the text's own control flow: the next instruction, a JUMP to
the label its `// -> label.` names (both ways for IF .. JUMP), a DO loop's end back to its top. Anything else ends the
search as "live" (conservative): an indirect jump (a subroutine's return `JUMP (M14, I12)`, the machine dispatch), an
absolute jump, CALL / RTS, a conditional write of R12, a SIMD region (MODE1), the end of the text. Run mode is
unchanged (it never loaded R12 for a call: a leaf body runs inline), so the model holds the DSP to the same outputs:
`dnfw.perc.dsl._zero_scale`'s rule (nothing reads the dropped value), proved over branches instead of only straight
line. Emit mode only; the jump resolver fills the return address in whichever register carries the comment.
"""
from __future__ import annotations

import re

_REG = re.compile(r"\b[RF]12\b")
_LABEL = re.compile(r"^\s*([A-Za-z_]\w*)\.:\s*$")
_TARGET = re.compile(r"//\s*->\s*([A-Za-z_]\w*)\.")
_DO = re.compile(r"\bDO ([A-Za-z_]\w*)\. UNTIL\b")
_K = re.compile(r"R12 = (-?0x[0-9a-f]+);")
_UREG = re.compile(r"(I\d+) = R12;")
_PASS = re.compile(r"R12 = PASS (R\d+);")
_ADD_FORMS = (re.compile(r"(R\d+) = R12 \+ (R\d+);"), re.compile(r"(R\d+) = (R\d+) \+ R12;"))
_ZERO_FORMS = ((re.compile(r"(F\d+) = FLOAT (R\d+) BY R12;"), "{0} = FLOAT {1};"),
               (re.compile(r"(R\d+) = R12 - (R\d+);"), "{0} = -{1};"),
               (re.compile(r"(R\d+) = R12 \+ (R\d+);"), "{0} = PASS {1};"),
               (re.compile(r"(R\d+) = (R\d+) \+ R12;"), "{0} = PASS {1};"))


def _body(line: str) -> str:
    return line.split("//", 1)[0].strip()


def _use(body: str) -> str | None:
    """'r' if BODY reads R12 / F12 (or writes it only on a condition), 'w' if it writes it without reading it,
    None if it does not name it"""
    if not _REG.search(body):
        return None
    write = False
    for part in (x.strip() for x in body.rstrip(";").split(",") if x.strip()):
        lhs, eq, rhs = part.partition(" = ")
        if not eq:
            if _REG.search(part):
                return "r"
            continue
        dest = lhs.strip()
        if _REG.search(rhs):
            return "r"
        if re.fullmatch(r"[RF]12", dest):
            write = True
        elif _REG.search(dest):
            return "r"                          # a conditional write (IF .. R12 = ..), or R12 in an address
    return "w" if write else "r"


class _Flow:
    def __init__(self, lines: list[str]):
        self.ins: list[int] = []               # line index of each instruction
        at: dict[str, int] = {}
        pending: list[str] = []
        for k, line in enumerate(lines):
            m = _LABEL.match(line)
            if m:
                pending.append(m.group(1))
                continue
            b = _body(line)
            if not b or b.startswith("."):
                continue
            for name in pending:
                at[name] = len(self.ins)
            pending = []
            self.ins.append(k)
        self.lines, self.at = lines, at
        self.of_line = {k: i for i, k in enumerate(self.ins)}
        self.loop_top: dict[int, int] = {}      # a DO loop's last instruction -> its first
        for i, k in enumerate(self.ins):
            m = _DO.search(_body(lines[k]))
            if m and m.group(1) in at:
                self.loop_top[at[m.group(1)]] = i + 1

    def _next(self, i: int) -> list[int] | None:
        line = self.lines[self.ins[i]]
        b = _body(line)
        if b.startswith("BIT ") and "MODE1" in b:
            return None                         # a SIMD region (or any mode change): not followed
        if "CALL" in b or "RTS" in b or "RTI" in b:
            return None
        out = []
        if "JUMP" in b:
            m = _TARGET.search(line)
            if "JUMP (" in b or not m or m.group(1) not in self.at:
                return None                     # indirect (a return, the dispatch) or absolute: not followed
            out.append(self.at[m.group(1)])
            if b.startswith("IF "):
                out.append(i + 1)
        else:
            out.append(i + 1)
        if i in self.loop_top:
            out.append(self.loop_top[i])
        return out

    def dead(self, start: int) -> bool:
        """every path from instruction START writes R12 before it reads it"""
        seen: set[int] = set()
        todo = [start]
        while todo:
            i = todo.pop()
            if i in seen:
                continue
            seen.add(i)
            if i >= len(self.ins):
                return False
            use = _use(_body(self.lines[self.ins[i]]))
            if use == "r":
                return False
            if use == "w" and "JUMP" not in self.lines[self.ins[i]]:
                continue
            nxt = self._next(i)
            if nxt is None:
                return False
            todo.extend(nxt)
        return True


def _keep_note(line: str, new_body: str) -> str:
    code, sep, note = line.partition("//")
    lead = code[:len(code) - len(code.lstrip())]
    text = lead + new_body
    return (text.ljust(40) + sep + note) if sep else text


def _sites(lines: list[str], g5: bool = True) -> list[tuple[str, int, int, str]]:
    """every foldable pair whose R12 is dead in LINES as they are: (kind, line kept, line dropped, its new text)"""
    flow = _Flow(lines)
    out = []
    for i, k in enumerate(flow.ins[:-1]):
        k2 = flow.ins[i + 1]
        pa = _PASS.fullmatch(_body(lines[k]))
        if g5 and pa and k2 == k + 1 and pa.group(1) != "R12":
            for form in _ADD_FORMS:
                z = form.fullmatch(_body(lines[k2]))
                if z and 8 <= int(z.group(2)[1:]) <= 15 and z.group(2) != "R12" and flow.dead(i + 2):
                    out.append(("pass", k2, k, _keep_note(lines[k2], f"{z.group(1)} = {z.group(2)} + {pa.group(1)};")))
                    break
            continue
        m = _K.fullmatch(_body(lines[k]))
        if not m or k2 != k + 1:
            continue                            # not a constant load, or a label between: not a pair
        nb = _body(lines[k2])
        u = _UREG.fullmatch(nb)
        if u:
            if flow.dead(i + 2):
                out.append(("call" if "return address" in lines[k] else "ireg", k, k2,
                            _keep_note(lines[k], f"{u.group(1)} = {m.group(1)};")))
            continue
        if m.group(1) != "0x0":
            continue
        for form, rewrite in _ZERO_FORMS:
            z = form.fullmatch(nb)
            if z and "12" not in z.group(2) and flow.dead(i + 2):
                out.append(("zero", k2, k, _keep_note(lines[k2], rewrite.format(*z.groups()))))
                break
    return out


def _apply(lines: list[str], sites) -> tuple[list[str], list[int]]:
    """LINES with SITES folded; and the line index, in the result, of each site's folded instruction"""
    new, drop = list(lines), set()
    for _kind, keep, gone, text in sites:
        new[keep] = text
        drop.add(gone)
    index, out = {}, []
    for j, line in enumerate(new):
        if j not in drop:
            index[j] = len(out)
            out.append(line)
    return out, [index[keep] for _kind, keep, _gone, _text in sites]


def fold(spans: dict[str, list[str]], g5: bool = True) -> tuple[dict[str, list[str]], dict[str, int]]:
    """SPANS (name -> its lines, every span of one program) with each dead R12 pair folded; and the count of each
    kind folded ('call', 'ireg', 'zero').

    Each pair is found dead in the text as emitted; folding drops R12 writes that may have been what made ANOTHER
    pair dead, so every fold is then checked again in the folded text (R12 dead after its folded instruction: the
    dropped value is never read there) and any that fails is unfolded, until all hold."""
    names = list(spans)
    lines: list[str] = []
    span_of: list[str] = []
    for name in names:
        lines += spans[name]
        span_of += [name] * len(spans[name])
    sites = _sites(lines, g5)
    while True:
        out, at = _apply(lines, sites)
        flow = _Flow(out)
        ok = [s for s, k in zip(sites, at) if flow.dead(flow.of_line[k] + 1)]
        if len(ok) == len(sites):
            break
        sites = ok
    gone = {s[2] for s in sites}
    result: dict[str, list[str]] = {name: [] for name in names}
    new = list(lines)
    for _kind, keep, _gone, text in sites:
        new[keep] = text
    for j, line in enumerate(new):
        if j not in gone:
            result[span_of[j]].append(line)
    counts = {"call": 0, "ireg": 0, "zero": 0, "pass": 0}
    for kind, *_rest in sites:
        counts[kind] += 1
    return result, counts


def fold_text(text: str) -> str:
    """one program's text (a single span: smp.asm, fdn8.asm, ...) with its dead R12 pairs folded (fold(); the G5 shape
    in PERC's alone, 2026-11-20: these programs' texts as before)"""
    folded, _counts = fold({"text": text.splitlines()}, g5=False)
    return "\n".join(folded["text"]) + "\n"
