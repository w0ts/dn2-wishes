"""The parts a build can leave out (docs/builder.md), as Optimist's builder lists its items.

Each part is a KEY with 0/1 in a configuration (`presets/*.config`, `KEY=0` / `KEY=1` lines).
Every part's default is 1: all of them on is the full build, byte for byte the branch's own
(`dnfw.builder.build` checks this against `presets/full.config`'s recorded sha256).

How a part comes out (never by editing another part's code):
- a machine: its code is not emitted; its machine type stays RESERVED as SID's did (28eb110):
  the DSP's lookup sends a track on it to the MIDI engine's slot (it renders nothing), and the
  ColdFire takes it off MACHINE SEL and names it Removed;
- an effect: its code is not emitted and its hook stays stock (FDN8: the stock reverb; XDLY:
  the stock delay); an insert type plays as OFF (the track passes through untouched).

Pure data, no imports of the build: the page reads it too (via builder.json).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Part:
    key: str
    label: str
    group: str
    what: str
    requires: tuple[str, ...] = ()
    os: tuple[str, ...] = ("1.12",)
    notes: tuple[str, ...] = field(default_factory=tuple)


GROUPS = (
    ("machines", "Machines"),
    ("md", "Machinedrum machines (PERC's TYPE knob)"),
    ("filters", "Filter machines"),
    ("fx", "Send effects"),
    ("inserts", "Per-track inserts"),
)

# PERC's Machinedrum machines in TYPE's order (dnfw.md.machines.ORDER), as the builder branch keys them
MD_NAMES = ("TRX-BD", "TRX-B2", "TRX-SD", "TRX-XT", "TRX-CP", "TRX-RS", "TRX-CB", "TRX-CH",
            "TRX-OH", "TRX-CY", "TRX-MA", "TRX-CL", "TRX-XC", "TRX-S2",
            "EFM-BD", "EFM-SD", "EFM-XT", "EFM-CP", "EFM-RS", "EFM-CB", "EFM-HH", "EFM-CY",
            "GND-SN", "GND-NS", "GND-IM",
            "PI-BD", "PI-SD", "PI-MT", "PI-ML", "PI-MA", "PI-RS", "PI-RC", "PI-CC", "PI-HH")
_MD_FAMILY = {"TRX": "TRX (Machinedrum TR-style)", "EFM": "EFM (Machinedrum FM)",
              "GND": "GND (Machinedrum ground)", "PI": "P-I (Machinedrum physical models)"}


def md_key(name: str) -> str:
    return "MD_" + name.replace("-", "_")


PARTS: tuple[Part, ...] = (
    Part("MNM_SOPHIE", "SOPHIE", "machines",
         "Schwung Sophie's percussion voice (MIT port), machine type 17."),
    Part("MNM_PLAITS", "PLAITS", "machines",
         "Mutable Instruments Plaits (MIT port): its MODL engines, machine type 18."),
    Part("MNM_TB303", "TB-303", "machines",
         "Open303 / Schwung 303 (MIT port), machine type 19."),
    Part("MNM_DRONE", "DRONE", "machines",
         "Optimist's DRONE (after Caravel's, GPL-3.0-only): a coupled network of four generators, BEAT, glide."),
    Part("MNM_ANALOG2", "ANALOG 2", "machines",
         "Optimist's ANALOG 2 (GPL-3.0-only): two oscillators, sync, swarm, drive, its filter and models."),
    Part("FLT_A2SVF", "A2 SVF", "filters", "Filter machine: two ANALOG 2 SVFs (LP12 LP24 BP HP NOTCH)."),
    Part("FLT_A2LADR", "A2 Ladder", "filters", "Filter machine: two transistor ladders (Moog-style)."),
    Part("FLT_A2OTA", "A2 OTA", "filters", "Filter machine: two OTA 4-poles (IR3109, Juno-style)."),
    Part("FLT_A2DIOD", "A2 Diode", "filters", "Filter machine: two diode ladders (303-style)."),
    Part("FLT_A2MS20", "A2 MS-20", "filters", "Filter machine: two Sallen-Key 2-poles (MS-20-style)."),
    *(Part(md_key(n), n, "md", f"{_MD_FAMILY[n.split('-')[0]]}. Off: its place on TYPE stays, silent, "
           "named ---.") for n in MD_NAMES),
    Part("FX_FDN8", "FDN8 reverb", "fx",
         "The 8-line feedback-delay reverb in the reverb's place (with LONG); off: the stock reverb."),
    Part("FX_XDLY", "XDLY delay", "fx",
         "The delay with a TYPE knob in the delay's place; off: the stock delay."),
    Part("INS_FUZZ", "FUZZ", "inserts", "Insert FUZZ; off: that M.SEL passes the track through."),
    Part("INS_TAPE", "TAPE", "inserts", "Insert TAPE (saturation, wow, flutter, hiss)."),
    Part("INS_FOLD", "FOLD", "inserts", "Insert FOLD (wavefolder)."),
    Part("INS_HARM", "HARM", "inserts", "Insert HARM (even/odd exciter)."),
    Part("INS_SUB", "SUB", "inserts", "Insert SUB (Optimist's octave-down flip-flop, one or two octaves)."),
    Part("INS_DIST", "DIST", "inserts", "Insert DIST (Optimist's peak-relative drive; shares FUZZ's loop)."),
    Part("INS_GATER", "GATER", "inserts", "Insert GATER (Optimist's tempo-synced pattern gate)."),
    Part("INS_RING", "RING", "inserts", "Insert RING (ring modulator, 26 Hz .. 2.6 kHz)."),
)

BY_KEY = {p.key: p for p in PARTS}


def defaults() -> dict[str, int]:
    return {p.key: 1 for p in PARTS}


class ConfigError(ValueError):
    pass


def parse(text: str) -> tuple[dict[str, int], dict[str, str]]:
    """A .config's text -> (values, header). Lines `KEY=0|1`; `# name: x` style comments are the
    header; any other comment or blank line is ignored. Unknown keys or values are refused; a key
    not given keeps its default (1)."""
    vals = defaults()
    head: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line[1:].strip()
            if ":" in body and body.split(":", 1)[0].strip().isidentifier():
                k, v = body.split(":", 1)
                head.setdefault(k.strip().lower(), v.strip())
            continue
        if "=" not in line:
            raise ConfigError(f"line {n}: expected KEY=0 or KEY=1, got {line!r}")
        k, v = (s.strip() for s in line.split("=", 1))
        if k not in BY_KEY:
            raise ConfigError(f"line {n}: unknown part {k!r}")
        if v not in ("0", "1"):
            raise ConfigError(f"line {n}: {k} must be 0 or 1, got {v!r}")
        vals[k] = int(v)
    return vals, head


def check(vals: dict[str, int], os_version: str = "1.12") -> list[str]:
    """Configuration errors (empty: fine): a part on whose requirement is off, an OS mismatch."""
    errs = []
    for p in PARTS:
        if not vals.get(p.key):
            continue
        for r in p.requires:
            if not vals.get(r):
                errs.append(f"{p.key} needs {r}")
        if os_version not in p.os:
            errs.append(f"{p.key} is not available on OS {os_version}")
    return errs


def canonical(vals: dict[str, int]) -> str:
    """The configuration as one canonical text (every key, registry order): its hash names it."""
    return "".join(f"{p.key}={int(bool(vals.get(p.key, 1)))}\n" for p in PARTS)


def config_id(vals: dict[str, int]) -> str:
    import hashlib
    return hashlib.sha256(canonical(vals).encode()).hexdigest()[:12]
