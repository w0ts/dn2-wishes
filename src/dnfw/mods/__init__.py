"""Firmware mods: what one is, and how two of them are known not to collide.

A **mod** is a named, reversible change to one or more sections of a firmware
image, expressed as bytes written at declared offsets. It is deliberately a
smaller idea than `dnfw.patch`, which models a single same-length edit with
`expect` guards: a mod may rewrite hundreds of kilobytes (a sample bank), and
carries its own notion of what the user supplies.

## Why extents are declared rather than discovered

The point of this package is that a user can eventually apply **several** mods
to one image. Two mods are safe together when the bytes they write do not
overlap, so every mod must be able to say what it will touch *before* it
touches it. `extents()` is that promise, and `check_compatible()` is what turns
a set of mods into a yes or no.

This is not a guarantee of musical or behavioural compatibility -- two mods can
write disjoint bytes and still fight over the same feature. It is the weakest
useful guarantee, and it is checkable, which is why it is the one enforced.

## What a mod must not do

**Change any section's length.** Every address after a resized section moves,
and nothing in this repository fixes up the code that refers to them
(`dnfw.patch.spec` says the same about patches). A mod that needs more room is
a code-cave or new-section problem — `docs/ideas-backlog.md` §1a and §6.

**Touch the "Multiplier" key material** (`docs/ele3-format.md` §5).

Integrity is not a mod's business: `dnfw build` recomputes the section byte-sum,
the content checksum and the HMAC-SHA256 trailer, and re-verifies the result
before writing. A mod produces section payloads; the build path makes them into
a firmware the device accepts.
"""

from dataclasses import dataclass, field


# The mods a shipped build applies, in order, to stock (the patcher's build, tools/patcher/dn2patch.py, and the
# gate's rebuild, scripts/ship_gate.py). 2026-11-14 (the User: "Port both"): lfowaves joins on OS 1.12; lfo4
# joins with DN2_LFO4 set at generation (docs/lfo-112-port.md), after lfowaves. 2026-11-16 (v0.56.2, the User: "now ..
# we can add more feature"): DN2_LFO4 is ON unless set to 0 or empty. 2026-11-19 (the User: "lfo4 i think we can drop
# behind a build flag", its CPU): OFF unless DN2_LFO4 is set (to anything but 0 or empty).
def shipped(env=None) -> tuple[str, ...]:
    """-> the shipped build's mods for ENV (default: this process's): lfo4 last when DN2_LFO4 is set, not 0 or empty
    (dnfw.waverider.pages.lfo4_on; on by default v0.56.2..v0.60.1, off since 2026-11-19)"""
    import os
    env = os.environ if env is None else env
    # 2026-11-21 (the User: SAFE MODE "IN THE COMBINED BUILD"): safemode last, after every mod that writes MAIN OS
    return (("waverider", "lfowaves") + (("lfo4",) if env.get("DN2_LFO4", "0") not in ("", "0") else ())
            + ("safemode",))


SHIPPED = shipped()

# The pseudo-section of RAM a mod uses outside the image: an Extent in it is an
# absolute address range at run time, compared like any other (`ram()`).
RAM = -1


class ModError(ValueError):
    """A mod cannot apply to this image, or its inputs are wrong."""


@dataclass(frozen=True)
class Extent:
    """A byte range a mod writes, inside one section's *unpacked* payload."""

    section: int
    start: int
    length: int
    what: str = ""
    # Set on a range several mods share by design (the platform's loader and
    # appended area, `mods.platform`): two extents with the same owner do not
    # conflict, because that owner merges what each mod contributes.
    owner: str = ""
    # Set on a hook site whose stock bytes the hook replays unchanged in its own
    # code (`platform.displace`): another mod's edit wholly inside it is written
    # to that copy (`platform.write`), so it is not a conflict.
    displaced: bool = False

    @property
    def end(self) -> int:
        return self.start + self.length

    def overlaps(self, other: "Extent") -> bool:
        if self.owner and self.owner == other.owner:
            return False
        for site, edit in ((self, other), (other, self)):
            if (site.displaced and not edit.displaced and site.section == edit.section
                    and site.start <= edit.start and edit.end <= site.end):
                return False
        return (self.section == other.section
                and self.start < other.end and other.start < self.end)

    def __str__(self) -> str:
        return (("RAM " if self.section == RAM else f"section {self.section} ")
                + f"[0x{self.start:08x}..0x{self.end:08x}) "
                f"{self.length:,} B{' — ' + self.what if self.what else ''}")


@dataclass(frozen=True)
class Result:
    """What a mod produced: replacement payloads, and what it wrote."""

    payloads: dict[int, bytes]        # section id -> whole new payload
    extents: list[Extent]
    notes: list[str]
    codecs: dict[int, str] = field(default_factory=dict)   # section id -> how it is stored, if not as the original


def check_compatible(named_extents) -> list[str]:
    """-> a list of conflict descriptions; empty means the set is compatible.

    `named_extents` is [(mod_id, [Extent, ...]), ...]. Every pair is compared,
    because "A is fine with B" and "B is fine with C" says nothing about A and
    C. The comparison is byte-range overlap only -- see the module docstring
    for what that does and does not promise.
    """
    conflicts = []
    items = list(named_extents)
    for i, (a_id, a_ext) in enumerate(items):
        for b_id, b_ext in items[i + 1:]:
            for a in a_ext:
                for b in b_ext:
                    if a.overlaps(b):
                        lo = max(a.start, b.start)
                        hi = min(a.end, b.end)
                        conflicts.append(
                            f"{a_id} and {b_id} both "
                            + ("use RAM " if a.section == RAM else f"write section {a.section} ")
                            + f"0x{lo:08x}..0x{hi:08x} ({hi - lo:,} bytes)")
    return conflicts
