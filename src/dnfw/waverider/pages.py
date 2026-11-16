"""Waverider's own SYN pages (Milestone 7): the page count, the page descriptors and the
knob labels a Waverider track shows. `docs/waverider-m7-pages.md` has the evidence.

A Waverider track is WaveTone to most of the UI (`coldfire`, M5): the SYN page readers
are asked about type 1, whatever the track. So these routines do not trust the type
they are handed. They ask whether the **active track** (the byte `0x42432a6c`, whose
sound is `[0x800052a0] + 52 + 1163 * t`) is a Waverider (`sound+0xDE` = 5), and only
then answer with Waverider's pages and labels:

- `wr_count`, entered by `jsr` from the page-count reader `0x400c2636` (in place of M5's
  `canon_arg` there): 2 pages; otherwise exactly what `canon_arg` does.
- `wr_page`, entered by `jsr` from the page reader `0x400c2652` at `0x400c2656` (in
  place of M5's `canon_page`): our descriptor for pages 0-1, the stock empty page past
  them; otherwise exactly what `canon_page` does.
- `wr_icons`, entered by `jsr` from the SYN page draw at `0x4001821e`: on a Waverider
  track, WaveTone's oscillator icons (drawn at B and F from `WAV1`/`TBL1` and
  `WAV2`/`TBL2` after the grid of page id 7) are skipped; otherwise the stock page-id test.
- `wr_grid`, entered by `jsr` from the SYN page draw at `0x40018214` (in place of its
  call to the grid `0x40017428`): a Waverider track gets its own page, drawn by
  `wr_page_draw` (`csrc/waverider/page.c`, M8.1); every other track the stock grid.
- `wr_label`, entered by `jsr` from the SYN page's label fetch at `0x40064622` (in place
  of `jsr getShortName`): the record ids Waverider relabels get our labels; every
  other id, and every other track, goes to the stock `getShortName` `0x400372da`
  unchanged (a tail jump, so the stack is the caller's own).

The labels and the page layout are the owner's (2026-10-01), from the Waverider mockup,
with our own names:

    page 1, OSC 1   A TUNE  B LEV   C POS   D TBL   E RATE  F MPOS  G MLEV  H MOVE
    page 2, OSC 2   A DETN  B LEV   C POS   D TBL   E RATE  F MPOS  G MLEV  H MOVE

Only TUNE, POS and TBL work in M7 (the loop reads TUN1, WAV1 and TBL1); every other
place is an empty entry (0), drawn as an empty box, until its milestone.

The code, the descriptors and the strings run from RAM as one platform `CODE` chunk at
`LOAD` (`dnfw.mods.platform`): the caves Waverider already uses are full.

The page is drawn in C (`csrc/waverider/page.c`), the way Tonverk's Wavefinder page
is laid out: the wave across the middle, A..D in a slim strip above it, E..H below.
That code is compiled and linked into the same chunk at `C_LOAD`, and reads this
module's control table and `wave`'s spans from a generated header (`c_header`).

This module is pure: it builds the source; `coldfire.compose` assembles and places it.
"""

from __future__ import annotations

LOAD = 0x4670C000                 # RAM above BSS, clear of every declared range (docs/mods-compatibility.md)
# v0.13: the C page renderer is a CODE chunk of its own, well above the others (it outgrew
# the room after this assembly, LOAD + 0x600 .. PING's chunk)
C_LOAD = 0x46A40000                # clear of the emulator harnesses' stack and scratch (0x46a00000..0x46a40000)
C_SPAN = 0xB0000                   # 2026-11-12: down from 0x46ac0000, 704 KB up to the MD graphics at 0x46af0000
                                  # (the User's ruling; docs/memory-map.md). v0.41..v0.48: 0x30000 (v0.29..v0.40: 0x20000,
                                  # to them at 0x46ae0000, and v0.40's renderer was within 2.5 KB of it;
                                  # REC trigs took it past). 64 KB until v0.28; all unclaimed RAM above
                                  # BSS (docs/memory-map.md); the pool's mirror starts at 0x46b00000
C_END = 0x46710000                # the platform runtime starts here
ACTIVE_TRACK = 0x42432A6C         # byte: the UI's active track, 0..15
KIT_POINTER = 0x800052A0          # the live kit; sound t at + 52 + 1163 t
SOUND_BASE, SOUND_STRIDE, SOUND_TYPE = 52, 1163, 0xDE
NEW_TYPE, CLONE = 5, 1
from ..mnm import machines as _mnm_types
from ..sampler import machines as _smp
TYPES_LAST = max(13, *_mnm_types.CF_TYPES, _smp.BOUNCE_TYPE)   # dnfw.waverider.coldfire.TYPES_LAST: 5.. are ours (v0.20: 13,
                                  # SLICE, had been left out here: its track got WaveTone's pages;
                                  # v0.26: the Monomachine's from 14 on)
GET_SHORT_NAME = 0x400372DA
EMPTY_PAGE = 0x42433BD4           # the readers' own empty-page fallback
TAG = 10                          # the tag every stock SYN descriptor ends with

# PERC (machine 5, docs/perc.md; Waverider's place until v0.11): two pages on WaveTone
# records -- the eight parameters of dnfw.perc.machines.PARAMS; then TYPE (DRIF) and the
# track effects (FX_PARAMS). What each
# parameter is depends on TYPE, so its names are swapped per machine at run time
# (wr_names in page.c, from perc_c_header's tables); the page reads them back from the
# records, so it, the header line and the LFO lists always agree.
from ..perc import machines as _perc

TITLES = ("PRC 1", "PRC 2")
SUBTITLE = "Perc"
TYPE_ID = _perc.TYPE_REC[0]                                  # 252, DRIF
PARAM_IDS = tuple(r for r, _slot, _lo, _top in _perc.PARAMS)  # 238 242 254 253 256 257 260 240
FX_IDS = tuple(r for r, _slot, _lo, _top in _perc.FX_PARAMS)   # 239 246 250 244 243 258 253
# 2026-11-11 (the User): the engine on page 1 knob H on every machine with engines: TYPE on page 1 H, the machine's
# eighth parameter on page 2 H (TYPE's place since v0.20, SRR's on the Machinedrum). The records stay theirs.
PAGES = (
    (*PARAM_IDS[:7], TYPE_ID),                  # the machine's first seven, TYPE
    (*FX_IDS, PARAM_IDS[7]),                    # AMD AMF EQF EQG / FLTF FLTW FLTQ, the machine's eighth
)
# no static labels: wr_label hands every PERC record to the stock getShortName, which
# reads the names wr_names swapped in
LABELS: dict[int, str] = {}
TYPE_NAMES = ("Perc Type", "TYPE")
UNUSED = tuple(r for r in range(238, 263) if r != TYPE_ID and r not in PARAM_IDS and r not in FX_IDS)
UNUSED_LONG, UNUSED_SHORT = "Unused", "-"
# a parameter's long name (LFO and modulation lists, the header line) from its short one
LONG = {"HAMR": "Hammer", "TENS": "Tension", "RING": "Ring", "RVOL": "Rattle Vol", "POS": "Position",   # v0.24 P-I
        "GRNS": "Grains", "GLEN": "Grain Length", "AG": "Highs Up", "AU": "Highs Down", "BR": "Lows",
        "GRAB": "Grab", "CLSN": "Closeness", "CLOS": "Close Time",
        "PTCH": "Pitch", "DEC": "Decay", "RAMP": "Ramp", "RDEC": "Ramp Decay", "STRT": "Start",
        "NOIS": "Noise", "HARM": "Harmonics", "CLIP": "Clip", "HOLD": "Hold", "TICK": "Tick",
        "DIRT": "Dirt", "DIST": "Distortion", "BUMP": "Bump", "BENV": "Bump Env", "SNAP": "Snap",
        "TONE": "Tone", "TUNE": "Tune", "DAMP": "Damping", "DTYP": "Dist Type", "CLPY": "Claps",
        "HARD": "Hardness", "RICH": "Richness", "RATE": "Rate", "ROOM": "Room", "RSIZ": "Room Size",
        "RTUN": "Room Tune", "ENH": "Enhance", "GAP": "Gap", "HPF": "High-Pass", "LPF": "Low-Pass",
        "MTAL": "Metal", "TOP": "Top", "TTUN": "Top Tune", "SIZE": "Size", "PEAK": "Peak",
        "ATT": "Attack", "SUS": "Sustain", "REV": "Reverse", "RATL": "Rattle", "RTYP": "Rattle Type",
        "DUAL": "Dual", "CLIC": "Click", "MOD": "Mod Amount", "MFRQ": "Mod Freq", "MDEC": "Mod Decay",
        "MFB": "Mod Feedback", "NDEC": "Noise Decay", "CLPS": "Claps", "CDEC": "Clap Decay",
        "SNAR": "Snare", "SPTC": "Snare Pitch", "SDEC": "Snare Decay", "SMOD": "Snare Mod",
        "FB": "Feedback", "TREM": "Tremolo", "TFRQ": "Trem Freq", "UP": "Up", "UVAL": "Up Value",
        "DOWN": "Down", "DVAL": "Down Value", "POWR": "Power", "NTUN": "Noise Tune",
        "NTYP": "Noise Type", "-": "Unused"}
# what each machine is, under its name in the middle of the page
DESCRIPTIONS = {"BD": "Bass Drum", "B2": "Bass Drum 2", "SD": "Snare", "XT": "Tom", "CP": "Clap",
                "RS": "Rimshot", "CB": "Cowbell", "CH": "Closed Hat", "OH": "Open Hat",
                "CY": "Cymbal", "MA": "Maracas", "CL": "Claves", "XC": "Conga", "HH": "Hi-Hat",
                "S2": "Snare 2",
                "SN": "Sine", "NS": "Noise", "IM": "Impulse",
                "MT": "Tom", "ML": "Metallica", "RC": "Ride", "CC": "Crash"}       # v0.24: P-I's


def type_of(word: int) -> int:
    """TYPE's record value (0..0x7f00) -> the machine, as the DSP reads it (dnfw.perc.program)"""
    return (min(127, max(0, word >> 8)) * _perc.N) >> 7


# v0.26: the Monomachine's machines (types 6, 7: docs/mnm.md), one page each, on PERC's
# eight records (PARAM_IDS), named per machine while such a track is active
from ..mnm import machines as _mnm
from ..mnm import plaits as _mnm_plaits
MNM_LONG = {"TUNE": "Tune", "---": "Unused",
            "ENGN": "Engine",                   # 2026-11-11: MONOMACHINE's (page 1 H)
            # SOPHIE (docs/sophie.md)
            "DCAY": "Decay", "COLR": "Color", "METL": "Metal", "FBK": "Feedback", "SWEP": "Sweep",
            "CRSH": "Crush", "MODL": "Model",
            # PLAITS (docs/plaits.md)
            "HARM": "Harmonics", "TIMB": "Timbre", "MORP": "Morph", "FINE": "Fine Tune",
            # TB303 (docs/tb303.md)
            "CUT": "Cutoff", "RES": "Resonance", "ENV": "Env Mod", "DEC": "Decay", "ACC": "Accent",
            "SLID": "Slide", "WAVE": "Saw/Square",
            # DRONE (docs/drone.md)
            "SPRD": "Spread", "CPL": "Couple", "TOPO": "Topology", "CHAR": "Character", "DRFT": "Drift",
            "TONE": "Tone", "BEAT": "Binaural Beat", "DTUN": "Detune", "GLID": "Glide Time",
            "GLTY": "Glide Type", "HOLD": "Hold", "OCT": "Octave",
            # ANALOG2 (docs/analog2.md)
            "DTN": "Detune", "MIX": "Osc Mix", "NOIS": "Noise", "DRV": "Drive", "KTR": "Key Track",
            "SWRM": "Swarm", "SEMI": "Osc2 Semi", "SDTN": "Swarm Spread", "SYNC": "Hard Sync",
            "WAV2": "Osc2 Wave", "FLT2": "Filter 2 Type", "WDTH": "Stereo Width",
            # JUNO (docs/mnm.md "JUNO"; PW, NOIS, CUT, RES, ENV, DEC: above)
            "SUB": "Sub Osc", "KEY": "Key Track", "ATK": "Attack", "SUS": "Sustain", "REL": "Release", "PWM": "PW Mod",
            "RNGE": "Range",
            # SID 6581, DPRO WAVE / DDRW / DENS, VO-6 (v0.26; removed 2026-11-08, back 2026-11-11):
            # their names as at 28eb110's parent (MIX, SYNC, WAV2, WAVE: below, by machine)
            "PW": "Pulse Width", "PWAD": "PW Sweep", "PWRS": "PW Restart",
            "MOD": "Modulation", "MSRC": "Mod Source", "MFRQ": "Mod Freq",
            "WP": "Wave Position", "WPM": "WP Mod", "WPRS": "WP Restart",
            "SFRQ": "Sync Freq",
            "WAV1": "Wave 1", "TIME": "Fade Time",
            "BR1": "Bit Reduce 1", "WID": "Detune Width", "BR2": "Bit Reduce 2",
            "PCH2": "Pitch 2", "PCH3": "Pitch 3", "PCH4": "Pitch 4",
            "VOC1": "Vocal Freq 1", "VOC2": "Vocal Freq 2", "V-SW": "Vowel Switch",
            "VOIC": "Voice Type", "CONS": "Consonant", "CLEN": "Cons Length", "CVOL": "Cons Volume"}


def _ck(M, sh: str) -> tuple[str, str]:
    """2026-11-11: the key a control's choices, widget and tags go by: (machine, control); on a MONOMACHINE place
    ENGN is MONOMACHINE's, its other controls the engine's (M.NAME)"""
    return (M.HOST, sh) if sh == _mnm.MONO_ENGN and hasattr(M, "HOST") else (M.NAME, sh)


def _choices(M) -> dict:
    """machine M's controls with choices (MNM_CHOICES), MONOMACHINE's ENGN on its places"""
    out = dict(MNM_CHOICES.get(M.NAME, {}))
    if hasattr(M, "HOST"):
        out.update(MNM_CHOICES.get(M.HOST, {}))
    return out


# a name one machine means otherwise (MNM_LONG is by short name across machines)
MNM_LONG_BY = {("ANALOG2", "WAVE"): "Waveform", ("JUNO", "WAVE"): "Waveform", ("JUNO", "ENV"): "VCF Env",
               ("JUNO", "HPF"): "High-Pass",
               ("SID 6581", "WAVE"): "Waveform", ("DPRO-WAVE", "WAVE"): "Waveform", ("DPRO-DENS", "WAVE"): "Waveform",
               ("DPRO-DDRW", "MIX"): "Wave Mix", ("DPRO-DDRW", "WAV2"): "Wave 2", ("DPRO-WAVE", "SYNC"): "Sync"}
# parameters the port does not run (DENS's chorus is the Monomachine's effect after the
# machine): drawn as "-", as an unused one
MNM_UNPORTED = {"CHRL", "CHRW"}


def _pch_names() -> tuple[tuple[int, ...], tuple[str, ...]]:
    """DENS's PCH2..4: the knob -> its choice (the ROM's ratio table runs, 33 of them),
    and their names as the Monomachine's: semitones -12..+12, OFF for 1.0, else the ratio.
    Without DPRO-DENS in this build (dnfw.builder) the page code's table stays, unused (no
    control is MNM_PCH)."""
    import fractions
    import itertools
    import math
    if "DPRO-DENS" not in _mnm.NAMES:
        return tuple(0 for _ in range(128)), ()
    from ..mnm import rom as mrom
    if not mrom.available():
        return tuple(range(128)), tuple(str(k) for k in range(128))
    t = mrom.words(*mrom.PCH)
    idx, names = [], []
    for v, g in itertools.groupby(t):
        r = v / 0x200000
        st = 12 * math.log2(r)
        if abs(st - round(st)) < 1e-3:
            n = "OFF" if round(st) == 0 else f"{round(st):+d}"
        else:
            f = fractions.Fraction(r).limit_denominator(6)
            n = f"{f.numerator}/{f.denominator}"
        idx += [len(names)] * len(list(g))
        names.append(n)
    return tuple(idx), tuple(names)


# the enumerated parameters: their choices by name, as the Monomachine shows them (0: a knob)
MNM_CHOICES = {
    "SID 6581": {"PWRS": ("OFF", "ON"), "WAVE": ("TRI", "SAW", "PULS", "MIX", "NOIS"),
                 "MOD": ("OFF", "RING", "SYNC", "R+S"), "MSRC": ("MFRQ", "PRCH")},
    "DPRO-WAVE": {"WAVE": 32, "WPRS": ("OFF", "ON"), "SYNC": ("OFF", "SFRQ", "PRCH")},
    # the Digibank's 64 (here the ROM's 32, twice: S01..S32) and DENS's pitches (by table)
    "DPRO-DDRW": {"WAV1": 64, "WAV2": 64},
    "DPRO-DENS": {"WAVE": 64, "PCH2": "pch", "PCH3": "pch", "PCH4": "pch"},
    # VO-6: its manual's names (Appendix A); V-SW below 64 ends the vowel
    "VO-6": {"V-SW": ("OFF", "ON"), "CONS": ("-", "B", "D", "F", "G", "H", "J", "K", "L", "M", "N",
                                            "P", "R", "RR", "S", "SJ", "T", "TJ", "TH", "V", "Z")},
    "SOPHIE": {"MODL": ("FUSE", "STAK", "SPLT", "SHRD", "PIPE", "BOOM", "KICK")},
    "ANALOG2": {"WAVE": ("SAW", "SQR", "TRI", "SIN", "PWM"), "WAV2": ("=1", "SAW", "SQR", "TRI", "SIN", "PWM"),
                "SYNC": ("OFF", "ON"), "SWRM": ("OFF", "1", "2", "3", "4", "5", "6"), "SEMI": 49,
                "FLT2": tuple(m[0] + md.replace("NTCH", "NT") for m in ("SVF", "LADR", "OTA", "DIOD", "MS20")
                             for md in ("L12", "L24", "BP", "HP", "NTCH")),
                "GLTY": ("OFF", "RATE", "TIME")},           # 2026-11-11: page 3 (OFF: the record's stock default)
    "JUNO": {"WAVE": ("OFF", "SAW", "PULS", "BOTH"), "HPF": ("BOOS", "FLAT", "236", "754"), "PWM": ("MAN", "ENV"),
             "RNGE": ("16'", "8'", "4'")},
    "DRONE": {"TOPO": ("PAIR", "CHN", "RING"), "GLTY": ("RATE", "TIME"), "HOLD": ("OFF", "ON"),
              # 2026-11-11, the User: an octave knob, -3..+3 (dnfw.mnm.drone q2), in its unit
              "OCT": ("-3oc", "-2oc", "-1oc", "0oct", "+1oc", "+2oc", "+3oc")},
    "PLAITS": {"MODL": _mnm_plaits.MODELS, "TUNE": 49, "FINE": 128},   # TUNE, FINE: steps (MW_SEMIS, MW_CENTS)      # 2026-11-09: every engine ported (dnfw.mnm.plaits)
    # 2026-11-11: MONOMACHINE's engine (page 1 H), the list popup's names (dnfw.mnm.machines MONO_CHOICES)
    _mnm.MONO_NAME: {_mnm.MONO_ENGN: tuple(_mnm.MONO_CHOICES[n] for n in _mnm.MONO_ENGINES)},
}
# v0.27: the controls the Monomachine draws as other than a knob (owner, 2026-10-27; 0 a knob,
# 1 empty): 2 a grid the marker steps through row by row, 3 a bar sliding along a line, 4 a
# needle at the bottom moving left or right, 5 a knob switch pointing at its position (the
# removed machines used 2..4; md_page.c keeps their drawing)
MNM_WIDGET = {("SOPHIE", "MODL"): 5, ("PLAITS", "MODL"): 5, (_mnm.MONO_NAME, _mnm.MONO_ENGN): 5,
              # the Monomachine's own (back 2026-11-11, as at 28eb110's parent): DPRO-WAVE's WAVE and
              # VO-6's CONS a grid, DDRW's WAV1 / WAV2 and DENS's WAVE a bar, DENS's PCH2..4 a needle
              ("DPRO-WAVE", "WAVE"): 2, ("VO-6", "CONS"): 2,
              ("DPRO-DDRW", "WAV1"): 3, ("DPRO-DDRW", "WAV2"): 3, ("DPRO-DENS", "WAVE"): 3,
              ("DPRO-DENS", "PCH2"): 4, ("DPRO-DENS", "PCH3"): 4, ("DPRO-DENS", "PCH4"): 4,
              ("SID 6581", "PWRS"): 5, ("SID 6581", "WAVE"): 5, ("SID 6581", "MOD"): 5,
              ("SID 6581", "MSRC"): 5, ("DPRO-WAVE", "WPRS"): 5, ("DPRO-WAVE", "SYNC"): 5,
              ("VO-6", "V-SW"): 5,
              ("DRONE", "TOPO"): 5, ("ANALOG2", "WAVE"): 5, ("ANALOG2", "WAV2"): 5, ("ANALOG2", "SYNC"): 5,
              ("ANALOG2", "SWRM"): 5, ("ANALOG2", "FLT2"): 5, ("ANALOG2", "SEMI"): 6, ("DRONE", "GLTY"): 5, ("DRONE", "HOLD"): 5, ("DRONE", "OCT"): 5,
              ("ANALOG2", "GLTY"): 5,
              ("JUNO", "WAVE"): 5, ("JUNO", "HPF"): 5, ("JUNO", "PWM"): 5, ("JUNO", "RNGE"): 5,
              # 2026-11-09: 6 MW_SEMIS, the step - n / 2 as +7 / -12 / 0 (the User, build #3: semitones,
              # not the note name); 7 MW_CENTS, the step - n / 2 as +12c / -30c
              ("PLAITS", "TUNE"): 6, ("PLAITS", "FINE"): 7}   # 2026-11-09: md_page.c draws a choice as a
                                                               # knob with its choice's name; 5 marks it a choice
MNM_WAVES = 32
MNM_PCH = 255                       # mnm_choices' mark: the choice by mnm_pch_idx[knob]


# the Monomachine's machines (v0.26; kinds 2 and 3 were RESONATOR's and CZ's until v0.25):
# is_wr's kind is the type - 4, so 2, 3 (types 6, 7) and 10.. (types 14..); one page of
# PERC's eight records each, labelled per machine
MNM_KINDS = tuple(t - 4 for t in _mnm_types.CF_TYPES)   # a reserved type's too (an empty page)
MNM_PAGE = PARAM_IDS
# 2026-11-09: a machine with PNAMES2 (DRONE, ANALOG 2) has a second page on PERC's page-2 records (the
# Machinedrum's track-FX records and TYPE, which PERC applies only to its own machines): 16 controls
MNM_PAGE2 = (*FX_IDS, TYPE_ID)
from ..mnm import units as _mnm_units
# 2026-11-11: a machine with PNAMES3 (ANALOG 2's GLID, GLTY) has a third page on eight WaveTone records no
# machine of ours uses (their stock ranges and defaults: dnfw.perc.machines.P3_RECS): 24 controls
MNM_PAGE3 = tuple(r for r, _slot, _lo, _top in _perc.P3_RECS)
MNM_RECS = (tuple(_perc.PARAMS) + tuple(_perc.FX_PARAMS) + (_perc.TYPE_REC + (0, 127),)
            + tuple(_perc.P3_RECS))   # (rid, slot, lo, top) x 24


def mnm_pnames(M) -> tuple[str, ...]:
    """a machine's 24 control names: its eight, then its page 2's and page 3's (none: eight '---')"""
    return tuple(M.PNAMES) + tuple(getattr(M, "PNAMES2", ("---",) * 8)) + tuple(getattr(M, "PNAMES3", ("---",) * 8))


def _mnm_ix(d: int) -> int:
    """wr_count / wr_page compute kind - 8 (kinds 2, 3 give 0, 1): -> the machine's index in
    CF_MACHINES (0xff: none). v0.45's BOUNCE (type 17, kind 13) is a sample machine, so every
    Monomachine type above it sits one place lower than kind - 8 (found 2026-11-10: DRONE drew
    ANALOG 2's title)"""
    kind = d + 2 if d < 2 else d + 8
    return MNM_KINDS.index(kind) if kind in MNM_KINDS else 0xFF


def mnm_pages(M) -> int:
    return 3 if hasattr(M, "PNAMES3") else 2 if hasattr(M, "PNAMES2") else 1


def mnm_order(M) -> tuple[int, ...]:
    """2026-11-11: the control j (0..23, mnm_pnames' order: the record it keeps) drawn at each of the 24 places
    (page 8 p + knob). A machine's LAYOUT (pages of names, None an empty knob) places its controls; the rest (its
    unused controls) fill the places left, in order. No LAYOUT: j at place j"""
    layout = getattr(M, "LAYOUT", None)
    if layout is None:
        return tuple(range(24))
    names = mnm_pnames(M)
    at = [None] * 24
    for pg, row in enumerate(layout):
        if len(row) > 8:
            raise ValueError(f"{M.NAME}: page {pg + 1} has {len(row)} knobs")
        for s, sh in enumerate(row):
            if sh is not None:
                if sh not in names or names.index(sh) in at:
                    raise ValueError(f"{M.NAME}: {sh} not a control, or placed twice")
                at[8 * pg + s] = names.index(sh)
    placed = [sh for row in layout for sh in row if sh is not None]
    missing = [sh for sh in names if sh != "---" and sh not in MNM_UNPORTED and sh not in placed]
    if missing:
        raise ValueError(f"{M.NAME}: LAYOUT leaves out {missing}")
    rest = iter(j for j in range(24) if j not in at)
    return tuple(j if j is not None else next(rest) for j in at)
MNM_LABELS = [{r: (sh if sh != "---" and sh not in MNM_UNPORTED else "-") for r, sh in zip(PARAM_IDS, M.PNAMES)}
              for M in _mnm.CF_MACHINES]
MNM_LABELS2 = [{r: (sh if sh != "---" else "-") for r, sh in zip(MNM_PAGE2, mnm_pnames(M)[8:16])}
               for M in _mnm.CF_MACHINES]
MNM_LABELS3 = [{r: (sh if sh != "---" else "-") for r, sh in zip(MNM_PAGE3, mnm_pnames(M)[16:])}
               for M in _mnm.CF_MACHINES]
MNM_TITLES = tuple(sh for _lo, sh in _mnm.CF_LIST_NAMES)
MNM_SUBTITLES = tuple(lo for lo, _sh in _mnm.CF_LIST_NAMES)


def mnm_named(k: int) -> dict[int, tuple[str, str]]:
    """record -> (long, short) on a Monomachine machine's track"""
    M = _mnm.CF_ALL[k]
    out = {r: ((MNM_LONG_BY.get((M.NAME, sh), MNM_LONG.get(sh, sh)), sh) if sh != "---" and sh not in MNM_UNPORTED
               else (UNUSED_LONG, "-"))
           for r, sh in zip(PARAM_IDS + MNM_PAGE2 + MNM_PAGE3, mnm_pnames(M))}
    out.update({r: (UNUSED_LONG, UNUSED_SHORT) for r in range(238, 263) if r not in out})
    return out


def mnm_retired() -> str:
    """MNM_RETIRED's C test: the (machine, control, choice) whose name is empty (one at most);
    "0" for none"""
    hits = []
    for mi, M in enumerate(_mnm.CF_ALL):
        for j, sh in enumerate(M.PNAMES):
            names = _choices(M).get(sh, 0)
            if isinstance(names, tuple):
                hits += [(mi, j, c) for c, n in enumerate(names) if n == ""]
    if len(hits) > 1:
        raise ValueError(f"one retired choice at most, not {hits}")
    if not hits:
        return "0"
    mi, j, c = hits[0]
    if c == 0:
        raise ValueError("a retired choice needs one before it")
    if c == len(_choices(_mnm.CF_ALL[mi])[_mnm.CF_ALL[mi].PNAMES[j]]) - 1:
        raise ValueError("a retired choice needs one after it")
    return f"((mi) == {mi} && (j) == {j} && (c) == {c})"


def mnm_default_words(d, M) -> list[int]:
    """the 24 words MACHINE SEL writes for machine M (page 1's DEFAULTS d), 0xffff: not written"""
    out = [_knob_word(x, t, lo) for (_r, _s, lo, t), x in zip(_perc.PARAMS, d)]
    for pg, attr in ((1, "DEFAULTS2"), (2, "DEFAULTS3")):
        recs = MNM_RECS[8 * pg:8 * pg + 8]
        out += ([_knob_word(x, t, lo) for (_r, _s, lo, t), x in zip(recs, getattr(M, attr))]
                if hasattr(M, attr) else [0xFFFF] * 8)
    return out


# 2026-11-11 (the User: MACHINEDRUM's engine list "is nice": its rows say what each machine is): the same tag beside
# each engine in PLAITS' and SOPHIE's list popups, 11 characters at most (our words; SOPHIE's from Schwung Sophie's
# source comments: Fuse two modulators in series, Stack a dense FM stack, Split parallel operators, Shard a 12-bit
# wavetable/noise hybrid, PIPE an FM carrier with an inharmonic ring, BOOM a clean fundamental with a metallic skin)
MNM_CHOICE_TAGS = {
    ("PLAITS", "MODL"): ("WAVESHAPER", "", "ANALOG VCOS", "2-OP FM", "ADDITIVE", "SAW SWARM", "FILT NOISE",
                         "PARTICLES", "STRING", "RESONATOR", "BASS DRUM", "SNARE", "HI-HAT"),
    ("SOPHIE", "MODL"): ("SERIES FM", "FM STACK", "PARALLEL FM", "12-BIT WAVE", "FM + RING", "METAL SKIN",
                         "TUNED KICK"),
    # 2026-11-11: MONOMACHINE's engines (page 1 H)
    (_mnm.MONO_NAME, _mnm.MONO_ENGN): tuple(_mnm.MONO_TAGS[n] for n in _mnm.MONO_ENGINES),
}
TAG_MAX = 11                                    # popup.c TAG_X 64 .. the box's edge, "%.11s"


def mnm_c_header() -> str:
    q = chr(34)
    names, tags, tag_lists, rows_n, rows_at = [], [], [], [], []
    for M in _mnm.CF_ALL:
        ch = _choices(M)
        n_row, at_row = [], []
        for sh in mnm_pnames(M):
            c = ch.get(sh, 0) if sh != "---" else 0
            if c == "pch":
                n_row.append(MNM_PCH)
                at_row.append(len(names))
                names += list(_pch_names()[1])
            elif isinstance(c, int):
                n_row.append(c)
                at_row.append(0)
            else:
                n_row.append(len(c))
                at_row.append(len(names))
                names += list(c)
                tg = MNM_CHOICE_TAGS.get(_ck(M, sh))
                if tg:
                    assert len(tg) == len(c) and all(len(t) <= TAG_MAX for t in tg), (M.NAME, sh)
                    tag_lists.append((_mnm.CF_ALL.index(M), mnm_pnames(M).index(sh), len(tags)))
                    tags += list(tg)
        rows_n.append(n_row)
        rows_at.append(at_row)

    def arr(rows):
        return ", ".join("{" + ", ".join(map(str, r)) + "}" for r in rows)
    labels = ", ".join("{" + ", ".join(q + (sh if sh != "---" and sh not in MNM_UNPORTED else "-") + q
                                       for sh in mnm_pnames(M)) + "}" for M in _mnm.CF_ALL)
    pidx = _pch_names()[0]
    _UNITS = _mnm_units.tables(_mnm.CF_ALL, mnm_pnames, tops=lambda j: MNM_RECS[j][3])
    _ik, _ia, _ic = _mnm_units.ins_tables()
    _base = len(_UNITS[2])
    _UNITS = (_UNITS[0], _UNITS[1], _UNITS[2] + _ic)
    _fk, _fa, _fc = _mnm_units.flt_tables(len(_UNITS[2]))
    _UNITS = (_UNITS[0], _UNITS[1], _UNITS[2] + _fc)
    _ia = [[(x + _base) if k & 127 and x < len(_ic) and _ic else x for x, k in zip(r, kr)] for r, kr in zip(_ia, _ik)]
    _st = None
    _glid = [_mnm_units.glid_table(t) for t in _mnm_units.GLID_TOPS]
    if stock_units_on():
        _glid += _mnm_units.stock_glid_rows()       # the measured stock tables, exact a knob                         # 2026-11-11: stock records' units, a build option (default off)
        _st = _mnm_units.stock_tables(len(_UNITS[2]))
        _UNITS = (_UNITS[0], _UNITS[1], _UNITS[2] + _st[4])
    lines = [
        f"#define MNM_N {len(_mnm.CF_ALL)}",
        # the machine's name in the track box (MACHINE SEL's long name, in capitals; a reserved
        # type's REMOVED), one per place: generated so a machine added or removed cannot leave a hole
        f"static const char *const mnm_name_upper[MNM_N] = {{{', '.join(q + lo.upper() + q for lo, _sh in _mnm.CF_ALL_LIST_NAMES)}}};",
        # 2026-11-09: the left panel's track box (stock's SYN place): MACHINE SEL's short name
        f"static const char *const mnm_name_short[MNM_N] = {{{', '.join(q + sh.upper() + q for _lo, sh in _mnm.CF_ALL_LIST_NAMES)}}};",
        "/* is_wr's kind -> the Monomachine machine's index, -1 for any other kind */",
        "static inline int mnm_index(int kind)",
        "{",
        *[f"    if (kind == {kd}) return {k};" for k, kd in enumerate(MNM_KINDS)],
        "    return -1;",
        "}",
        f"#define MNM_WAVES {MNM_WAVES}",
        f"#define MNM_PCH {MNM_PCH}",
        f"static const unsigned char mnm_pch_idx[128] = {{{', '.join(map(str, pidx))}}};",
        "#define MNM_J 24                       /* a machine's controls: page 1's eight, page 2's, page 3's */",
        f"static const unsigned char mnm_npages[MNM_N] = {{{', '.join(str(mnm_pages(M)) for M in _mnm.CF_ALL)}}};",
        f"static const char mnm_labels[MNM_N][MNM_J][6] = {{{labels}}};",
        f"static const unsigned char mnm_lo[MNM_J] = {{{', '.join(str(lo) for _r, _s, lo, _t in MNM_RECS)}}};",
        f"static const unsigned char mnm_top[MNM_J] = {{{', '.join(str(t) for _r, _s, _lo, t in MNM_RECS)}}};",
        f"static const unsigned char mnm_choices[MNM_N][MNM_J] = {{{arr(rows_n)}}};",
        f"static const unsigned char mnm_choice_at[MNM_N][MNM_J] = {{{arr(rows_at)}}};",
        f"static const char mnm_choice_names[{max(1, len(names))}][5] = {{{', '.join(q + n + q for n in names)}}};",
        # 2026-11-11: the list popup's tag beside each choice, as PERC's TYPE list's: only the lists that have them
        # (machine, control, first tag); "" none
        f"#define MNM_TAG_LISTS {max(1, len(tag_lists))}",
        f"static const unsigned char mnm_tag_list[MNM_TAG_LISTS][3] = {{{', '.join('{%d, %d, %d}' % t for t in tag_lists) or '{255, 255, 0}'}}};",
        f"static const char mnm_choice_tags[{max(1, len(tags))}][{TAG_MAX + 1}] = {{{', '.join(q + t + q for t in tags) or q + q}}};",
        # v0.27: the frame slot of each of the eight (smp_quant's 4 detents a choice), and each
        # control's widget as the Monomachine draws it (docs/mnm-pages-plan.md)
        f"static const unsigned char mnm_slot[MNM_J] = {{{', '.join(str(sl) for _r, sl, _lo, _t in MNM_RECS)}}};",
        # v0.33: each machine's own start (dnfw.mnm's DEFAULTS), set by MACHINE SEL (rec.c), as
        # the words the eight records take (perc.live.knob_word), and the records' ids
        f"static const unsigned short mnm_rid[MNM_J] = {{{', '.join(str(r) for r, _s, _lo, _t in MNM_RECS)}}};",
        # 2026-11-11: the control drawn at each place (page 8 p + knob), as the descriptors' records
        f"static const unsigned char mnm_order[MNM_N][MNM_J] = {{{arr([list(mnm_order(M)) for M in _mnm.CF_ALL])}}};",   # every place, MONOMACHINE's engines too (2026-11-12)
        # page 2's and page 3's start: a machine with PNAMES2 / PNAMES3 its DEFAULTS2 / DEFAULTS3 (knob
        # 0..127 each), else the records' words untouched (0xffff: not written)
        f"static const unsigned short mnm_default[MNM_N][MNM_J] = {{{arr([mnm_default_words(d, M) for d, M in zip(_mnm.CF_ALL_DEFAULTS, _mnm.CF_ALL)])}}};",
        # 2026-11-09: a RETIRED choice (an empty name: PLAITS' GRAN, removed): shown as the choice
        # before it, stepped past (md_page.c, page.c, fmt.c); its knob slot stays, so saved knobs keep
        # their choice
        f"#define MNM_RETIRED(mi, j, c) {mnm_retired()}",
        "enum { MW_KNOB, MW_EMPTY, MW_GRID, MW_SLIDE, MW_VU, MW_SWITCH, MW_SEMIS, MW_CENTS };",
        f"static const unsigned char mnm_widget[MNM_N][MNM_J] = {{{arr([[MNM_WIDGET.get(_ck(M, sh), 1 if sh == '---' or sh in MNM_UNPORTED else 0) for sh in mnm_pnames(M)] for M in _mnm.CF_ALL])}}};",
        # 2026-11-10: the value readout's units (dnfw.mnm.units): kind (bit 7: 0 reads OFF), curve, the curves
        "enum { MU_RAW, MU_PCT, MU_SPCT, MU_HZ, MU_HZ100, MU_MS, MU_C10, MU_C, MU_DB, MU_OCT, MU_PATN, MU_RATE, MU_PCTC, MU_MODE, MU_MS10, MU_VOIC, MU_GLID, MU_ST10, MU_JUNO };",
        f"static const unsigned char mnm_unit[MNM_N][MNM_J] = {{{arr(_UNITS[0])}}};",
        f"static const unsigned char mnm_unit_curve[MNM_N][MNM_J] = {{{arr(_UNITS[1])}}};",
        f"static const short mnm_curves[{len(_UNITS[2])}][17] = {{{arr(_UNITS[2])}}};",
        # 2026-11-11: GLID's time a knob (MU_GLID; ms under 10 s, else 10000 + tenths of a second), a record span each
        f"static const unsigned short mnm_glid[{len(_glid)}][128] = {{{arr(_glid)}}};",
        f"static const unsigned char flt_unit[{len(_fk)}] = {{{', '.join(map(str, _fk))}}};",
        f"static const unsigned char flt_unit_curve[{len(_fk)}] = {{{', '.join(map(str, _fa))}}};",
        f"#define FLT_UNIT_IDS {{{', '.join(map(str, _mnm_units.FLT_IDS))}}}",
        f"static const unsigned char ins_unit[{len(_ik)}][8] = {{{arr(_ik)}}};",
        f"static const unsigned char ins_unit_curve[{len(_ia)}][8] = {{{arr(_ia)}}};",
    ]
    if _st is not None:                          # only with DN2_STOCK_UNITS: without it the header is as before
        ids, kinds, at, stock, _c = _st
        lines += [
            f"#define STU_N {len(ids)}",
            f"static const unsigned short stu_ids[STU_N] = {{{', '.join(map(str, ids))}}};",
            f"static const unsigned char stu_unit[STU_N] = {{{', '.join(map(str, kinds))}}};",
            f"static const unsigned char stu_unit_curve[STU_N] = {{{', '.join(map(str, at))}}};",
            f"static const unsigned int stu_stock[STU_N] = {{{', '.join(hex(a) + 'u' for a in stock)}}};",
            f"#define STU_MACHINE_LO {_mnm_units.STOCK_MACHINE_IDS.start}",
            f"#define STU_MACHINE_HI {_mnm_units.STOCK_MACHINE_IDS.stop - 1}",
            "#define STU_FNS(X) " + " ".join(f"X({k})" for k in range(len(ids))),
        ]
    return "\n".join(lines + mnm_mono_lines()) + "\n"


def mnm_mono_lines() -> list[str]:
    """2026-11-11: MONOMACHINE (dnfw.mnm.machines): its place (the type's, MNM_MONO; -1 none) is its first engine's,
    the others' after the types' places; ENGN (control MNM_MONO_J, page 1 H) picks the place every table is read at
    (mnm_live), the choice as the page shows it and the DSP reads it (dnfw.perc.program MONO_THRESHOLDS)"""
    from ..perc import program as _pp
    n = len(_mnm.MONO_ENGINES)
    places = _mnm.CF_MONO_PLACES or (0,)
    th = _pp.MONO_THRESHOLDS or (0,)
    k, j = _mnm.MONO_ENGINE_K, _mnm.MONO_TUNE_J
    assert MNM_RECS[k][:4] == _pp.MONO_ENGN_REC and MNM_RECS[j][:2] == _pp.MONO_TUNE_REC[:2]
    for e in range(n):                         # MACHINE SEL's and an engine change's ENGN word lands on the engine
        w = _knob_word(_mnm.mono_knob(e), MNM_RECS[k][3], MNM_RECS[k][2]) >> 8
        assert sum(w >= t for t in _pp.MONO_THRESHOLDS) == e, (e, w)
    return [
        f"#define MNM_MONO {_mnm.CF_MONO}",
        f"#define MNM_MONO_TYPE {_mnm.MONO_TYPE}",
        f"#define MNM_MONO_N {max(1, n)}",
        f"#define MNM_MONO_J {k}                    /* ENGN: page 1 H */",
        f"static const unsigned char mnm_mono_place[MNM_MONO_N] = {{{', '.join(map(str, places))}}};",
        f"static const unsigned char mnm_mono_th[MNM_MONO_N] = {{{', '.join(map(str, th))}}};",
        "/* ENGN's record value (word >> 8) -> the engine, 0..MNM_MONO_N-1 */",
        "static inline int mnm_mono_engine(int v)",
        "{",
        "    int e = 0;",
        "    for (int i = 0; i < MNM_MONO_N - 1; i++)",
        "        if (v >= mnm_mono_th[i])",
        "            e++;",
        "    return e;",
        "}",
        "/* the place the tables are read at: MONOMACHINE's engine's (ENGN's word W), any other machine's own */",
        "static inline int mnm_live(int mi, int w)",
        "{",
        "    return MNM_MONO >= 0 && mi == MNM_MONO ? mnm_mono_place[mnm_mono_engine((w >> 8) & 0xFF)] : mi;",
        "}",
    ]


def stock_units_on() -> bool:
    """2026-11-11 (the User: proper values on stock pages too, "gate it with a compile option at first"): the stock
    records' units are built only with DN2_STOCK_UNITS set (to anything but 0 or empty) when the code is generated"""
    import os
    return os.environ.get("DN2_STOCK_UNITS", "") not in ("", "0")


# the Digitakt II's sample machines (types 8..12, docs/sampler.md): one page each, on
# WaveTone records (dnfw.sampler.machines.PAGES); named per machine by wr_names, as PERC's
from ..sampler import machines as _smp
SMP_FIRST = _smp.FIRST_TYPE
SMP_PAGES = tuple(tuple(r for r, _sh, _lo in _smp.PAGES.get(n, _smp.PAGES["ONESHOT"])) for n in _smp.NAMES)
SMP_TITLES = _smp.SHORT
SMP_SUBTITLES = tuple(n.capitalize() for n in _smp.NAMES)
SMP_REC_IDS = tuple(r for r, _sh, _lo in _smp.REC_PAGE)            # every sample machine's page 2


def smp_named(name: str) -> dict[int, tuple[str, str]]:
    """record -> (long, short) on a sample machine's track"""
    out = {r: (lo, sh) for r, sh, lo in _smp.PAGES.get(name, _smp.PAGES["ONESHOT"]) if r}
    out.update({r: (UNUSED_LONG, UNUSED_SHORT) for r in range(238, 263) if r not in out})
    return out


LABELS_OUT = ("is_wr", "wr_count", "wr_page", "wr_label", "wr_icons", "wr_grid", "wr_id9",
              "wr_cell_tail", "labels", "descriptors")
# every stock page cell's widget is drawn by 0x4006448a; its one exit
CELL_EXIT = 0x400646CA            # movem.l %sp@,%d2-%d7/%a2-%fp ; lea %sp@(80),%sp ; rts
CELL_EXIT_STOCK = "4cd77cfc4fef00504e75"
# W2: `labels` is where the assembly's code ends and its data (the label table, the
# descriptors, the strings) begins: the ship gate checks only [is_wr, labels) as code
GRID = 0x40017428                 # the stock grid: (view, canvas)
ICON_PAGE = 7                     # the SYN page draw's id for WaveTone's OSC page
ICON_SKIP = 0x400182C6            # its branch target past the oscillator icons
# CZ: the draw sends a type-1 page of id 9 (WaveTone's third page, which a CZ track's
# third page is to it) to the grid variant 0x400175e4; wr_id9 sends ours to the grid
# call wr_grid hooks instead
ID9_SITE = 0x40018202             # moveq #9,%d1 ; cmp.l %d3,%d1 ; bne.s 0x40018214
ID9_STOCK = "7209b283660c"
ID9_GRID = 0x40018214             # the standard grid's call (wr_grid's site)


def _rep(label: str, text: str) -> str:
    """A std::string's characters with the header the firmware's copy-on-write strings
    keep in front of them (libstdc++'s old ABI: length, capacity, reference count; the
    string object is a pointer to the characters). The descriptors' title and subtitle
    are such strings (the initializer builds them with a string constructor, `jsr %a2@`
    after `pea` of the text). Reference count -1 marks the string unshareable: a copy
    clones it, and nothing ever frees this one."""
    return (f"    .align 2\n    .long {len(text)}, {len(text)}, -1\n"
            f'{label}: .asciz "{text}"')


def label(rid: int) -> str:
    """-> what place `rid` is called on the page with no machine applied ("-" if none)."""
    return LABELS.get(rid, "-") if rid else "-"


def named() -> list[tuple[int, str, str]]:
    """(record id, long name, short name) of the names wr_names swaps in for every PERC
    machine alike: TYPE, the track effects, and the WaveTone records PERC leaves unused.
    The machine's eight are per machine (perc_names)."""
    return ([(TYPE_ID, *TYPE_NAMES)] + [(r, lo, sh) for r, (sh, lo) in zip(FX_IDS, _perc.FX_NAMES)]
            + [(r, UNUSED_LONG, UNUSED_SHORT) for r in UNUSED])


def perc_names() -> list[list[tuple[str, str]]]:
    """[machine][parameter] = (long, short), PARAM_IDS order"""
    return [[(LONG[sh], sh) for sh in _perc.PNAMES[name]] for name in _perc.NAMES]


def c_header() -> str:
    """The control tables, as C for `wr_gen.h`: per page, eight record ids and labels
    (Waverider's, then RESONATOR's); the names `wr_names` swaps in for each machine (a
    0 keeps the stock name); the scanner's shape names."""
    q = chr(34)
    ids = ",\n".join(" {" + ", ".join(str(r) for r in page) + "}" for page in PAGES)
    names = ",\n".join(" {" + ", ".join(f'"{label(r)}"' for r in page) + "}" for page in PAGES)
    wr = {r: (lo, sh) for r, lo, sh in named()}
    mnm = [mnm_named(k) for k in range(len(_mnm.CF_MACHINES))]
    mono = [mnm_named(k) for k in _mnm.CF_MONO_PLACES[1:]]     # 2026-11-11: MONOMACHINE's other engines
    smp = [smp_named(n) for n in _smp.NAMES]
    order = sorted(set(wr) | set(PARAM_IDS) | {r for m in mnm + mono + smp for r in m})
    # by kind (is_wr: the type - 4), from 1: PERC, the sample machines at SMP_FIRST_KIND..,
    # the Monomachine's at MNM_KINDS
    # (v0.44: a sample machine's kind is its type - 4: 4..9, and BOUNCE's 13)
    by_kind = {1: wr, **{_smp.TYPE_OF[n] - 4: m for n, m in zip(_smp.NAMES, smp)},
               **{kd: m for kd, m in zip(MNM_KINDS, mnm)}}
    if sorted(by_kind) != list(range(1, len(by_kind) + 1)):
        raise ValueError(f"the kinds are not 1..n: {sorted(by_kind)}")
    kinds = [by_kind[k] for k in sorted(by_kind)]

    def row(m, col):
        return "{" + ", ".join(q + m[r][col] + q if r in m else "0" for r in order) + "}"
    return (f"#define WR_PAGES {len(PAGES)}\n"
            f"static const unsigned short wr_ids[WR_PAGES][8] = {{\n{ids}\n}};\n"
            f"static const char wr_labels[WR_PAGES][8][6] = {{\n{names}\n}};\n"
            f"#define WR_NAMED {len(order)}\n"
            f"static const unsigned short wr_named_ids[WR_NAMED] = {{{', '.join(map(str, order))}}};\n"
            f"#define WR_KINDS {len(kinds)}\n"
            f"static const char *const wr_named_long[WR_KINDS][WR_NAMED] = {{{', '.join(row(m, 0) for m in kinds)}}};\n"
            f"static const char *const wr_named_short[WR_KINDS][WR_NAMED] = {{{', '.join(row(m, 1) for m in kinds)}}};\n"
            # 2026-11-11: MONOMACHINE on its second engine on (wr_names: its kind's row is its first engine's)
            f"#define WR_MONO_ROWS {max(1, len(mono))}\n"
            f"static const char *const wr_mono_long[WR_MONO_ROWS][WR_NAMED] = {{{', '.join(row(m, 0) for m in mono) or row({}, 0)}}};\n"
            f"static const char *const wr_mono_short[WR_MONO_ROWS][WR_NAMED] = {{{', '.join(row(m, 1) for m in mono) or row({}, 1)}}};\n"
            + perc_c_header() + smp_c_header() + mnm_c_header())


def smp_c_header() -> str:
    """The sample machines' tables for page.c: each machine's page (record ids), the
    records drawn as text, and the pool's sound names (the test sounds until loading)."""
    q = chr(34)
    from ..sampler import live as smp_live
    ids = ",\n".join(" {" + ", ".join(str(r) for r in page) + "}" for page in SMP_PAGES)
    names = ", ".join(q + n + q for n in _smp.NAMES)
    snd = ", ".join(q + n + q for n in smp_live.TEST_NAMES)
    # v0.44: the kinds 4..9 are the six DT2 machines, in a run; BOUNCE's kind is 13 (type 17),
    # its tables' row SMP_N0 (page.c's SMP_IDX(kind) gives the row, -1 for another kind)
    return (f"#define SMP_KIND0 4\n#define SMP_N {len(_smp.NAMES)}\n#define SMP_N0 {len(_smp.NAMES) - 1}\n"
            f"#define SMP_BOUNCE_KIND {_smp.BOUNCE_TYPE - 4}\n#define SMP_BUF_ID {_smp.BUF_REC}\n"
            f"#define SMP_IDX(kind) ((kind) >= SMP_KIND0 && (kind) < SMP_KIND0 + SMP_N0 ? (kind) - SMP_KIND0 : (kind) == SMP_BOUNCE_KIND ? SMP_N0 : -1)\n"
            f"#define WR_TYPES_LAST {TYPES_LAST}\n"
            f"static const unsigned short smp_ids[SMP_N][8] = {{\n{ids}\n}};\n"
            f"static const char smp_machine[SMP_N][8] = {{{names}}};\n"
            f"#define SMP_PLAY_ID {_smp.PLAY_REC}\n#define SMP_SAMP_ID {_smp.SAMP_REC}\n"
            f"#define SMP_STRT_ID {_smp.STRT_REC}\n#define SMP_LEN_ID {_smp.LEN_REC}\n"
            f"#define SMP_LOOP_ID {_smp.LOOP_REC}\n#define SMP_GRID_ID {_smp.GRID_REC}\n"
            f"#define SMP_SLICE_ID {_smp.SLICE_REC}\n#define SMP_SLEN_ID {_smp.SLEN_REC}\n"
            f"#define SMP_GRID_KIND {SMP_FIRST_KIND + _smp.NAMES.index('GRID')}\n"
            f"#define SMP_WERP_KIND {SMP_FIRST_KIND + _smp.NAMES.index('WERP')}\n"
            f"#define SMP_SLICE_KIND {SMP_FIRST_KIND + _smp.NAMES.index('SLICE')}\n"
            f"#define SMP_STRETCH_KIND {SMP_FIRST_KIND + _smp.NAMES.index('STRETCH')}\n"
            f"#define SMP_REPITCH_KIND {SMP_FIRST_KIND + _smp.NAMES.index('REPITCH')}\n"
            f"#define SMP_BARS_ID {_smp.BARS_REC}\n#define SMP_SEG_ID {_smp.SEG_REC}\n"
            f"#define SMP_MODE_ID {_smp.MODE_REC}\n"
            f"static const unsigned short smp_rec_ids[8] = {{{', '.join(str(r) for r in SMP_REC_IDS)}}};\n"
            f"#define SMP_RSRC_ID {_smp.RSRC_REC}\n#define SMP_RCHAN_ID {_smp.RCHAN_REC}\n"
            f"#define SMP_RTHR_ID {_smp.RTHR_REC}\n#define SMP_RDST_ID {_smp.RDST_REC}\n"
            f"#define SMP_RLEN_ID {_smp.RLEN_REC}\n#define SMP_RSTRT_ID {_smp.RSTRT_REC}\n"
            f"#define SMP_ARM_ID {_smp.ARM_REC}\n#define SMP_REC_FIRST {_smp.REC_FIRST}\n"
            f"#define SMP_REC_SECONDS10 {_smp.REC_FRAMES * 10 // 48000}\n"
            f"#define SMP_REC_SOURCES {len(_smp.SRC_NAMES)}\n"
            f"#define SMP_REC_CHANS {len(_smp.CHAN_NAMES)}\n"
            # v0.51: FLEX REC's settings kept per track in its sound (rectrig.c fx_get / fx_set)
            "#define FX_SRC 0\n#define FX_CHAN 1\n#define FX_RLEN 2\n#define FX_GAIN 3\n#define FX_QREC 4\n#define FX_ARM 5\n"
            # v0.52: MUTE SRC (owner, option B: the SRC track out of the mix while ON, still recorded)
            "#define FX_MUTE 6\n#define FX_N 7\n"
            f"static const char smp_rec_chan[3][4] = {{{', '.join(q + m + q for m in ('L+R', 'L', 'R'))}}};\n"
            f"static const char smp_rec_src[{len(_smp.SRC_NAMES)}][8] = {{{', '.join(q + m + q for m in _smp.SRC_NAMES)}}};\n"
            f"static const char smp_bars[8][4] = {{{', '.join(q + b + q for b in ('1', '2', '4', '8', '8', '8', '8', '8'))}}};\n"
            f"static const unsigned char smp_bars_steps[7] = {{{', '.join(map(str, _smp.BARS_STEPS))}}};\n"
            f"static const unsigned char smp_seg_steps[7] = {{{', '.join(map(str, _smp.SEG_STEPS))}}};\n"
            f"static const char smp_play[4][5] = {{{', '.join(q + m + q for m in _smp.PLAY_MODES)}}};\n"
            f"static const unsigned char smp_grids[{len(_smp.GRIDS)}] = {{{', '.join(map(str, _smp.GRIDS))}}};\n"
            + smp_widgets_header() + smp_quant_header() +
            f"#define SMP_SOUNDS {len(smp_live.TEST_NAMES)}\n"
            f"static const char smp_sound[SMP_SOUNDS][6] = {{{snd}}};\n")


SMP_FIRST_KIND = 4                 # is_wr's answer for type 8; 5..8 for 9..12


def _knob_word(x, top, lo):
    from ..perc import live as _pl
    return _pl.knob_word(x, top, lo)


def smp_quant_header() -> str:
    """v0.15: the one-detent-a-choice tables for csrc/sampler/fmt.c (dnfw.sampler.machines.QUANT)"""
    def mask(names):
        return sum(1 << _smp.NAMES.index(n) for n in names)
    rows, steps = [], []
    for names, rec, th, rep in _smp.QUANT:
        slot = _smp.RECORDS[rec][0]
        thr = list(th) + [255] * (17 - len(th))
        rp = list(rep) + [0] * (18 - len(rep))
        rows.append(f" {{{mask(names)}, {slot}, {len(rep)}, {{{', '.join(map(str, thr))}}}, "
                    f"{{{', '.join(map(str, rp))}}}}}")
    for names, rec, step in _smp.QUANT_STEP:
        slot, lo, top = _smp.RECORDS[rec]
        steps.append(f" {{{mask(names)}, {slot}, {step}, {lo}, {lo + top}}}")
    return ("struct smp_q { unsigned char types, slot, n, th[17], rep[18]; };\n"
            "struct smp_qs { unsigned char types, slot, step, lo, hi; };\n"
            f"#define SMP_NQ {len(rows)}\nstatic const struct smp_q smp_q[SMP_NQ] = {{\n" + ",\n".join(rows) + "\n};\n"
            f"#define SMP_NQS {len(steps)}\nstatic const struct smp_qs smp_qs[SMP_NQS] = {{\n" + ",\n".join(steps) + "\n};\n"
            f"#define SMP_PLAY_REC {_smp.PLAY_REC}\n#define SMP_MODE_REC {_smp.MODE_REC}\n"
            f"#define SMP_BARS_REC {_smp.BARS_REC}\n#define SMP_SEG_REC {_smp.SEG_REC}\n"
            f"#define SMP_GRID_REC {_smp.GRID_REC}\n#define SMP_SAMP_REC {_smp.SAMP_REC}\n#define SMP_LEV_REC {_smp.LEV_REC}\n#define SMP_LEV_UNITY {_smp.LEV_UNITY}\n"
            f"#define SMP_SEG_LO {_smp.RECORDS[_smp.SEG_REC][1]}\n"
            f"#define SMP_SEG_SLOT {_smp.RECORDS[_smp.SEG_REC][0]}\n"
            f"#define SMP_SAMP_SLOT {_smp.RECORDS[_smp.SAMP_REC][0]}\n"
            # v0.32: FUNC + turn: the controls whose stock FUNC jump is right for us (sample
            # TUNE and PERC's first control by octaves on record 238, PERC's TYPE)
            f"#define SMP_TUNE_SLOT {_smp.RECORDS[_smp.TUNE_REC][0]}\n"
            f"#define PERC_PTCH_SLOT {_perc.PARAMS[0][1]}\n"
            f"#define PERC_TYPE_SLOT {_perc.TYPE_REC[1]}\n")
SMP_WAVE_W, SMP_WAVE_AMP = 100, 11         # the waveform strip: columns, half-height in pixels
SMP_GLYPHS = "0123456789AB/-YESLRMPTDCWIU."  # v0.44: L, R for the CHAN icon; v0.51: FLEX REC's state column


def smp_widgets_header() -> str:
    """v0.15, the DT2-style page: each record's widget kind, a 3x5 font for the SAMP box's
    inverted bank letter and digits, and the test sounds' waveform overviews (peak per
    column, 0..SMP_WAVE_AMP) -- the uploaded sounds' are read from the mirror."""
    import json
    import pathlib
    from ..sampler import live as smp_live
    kinds = ("none", "bipolar", "play", "empty", "samp", "knob", "fader", "seg", "bars")
    w = _smp.WIDGETS
    font = json.loads((pathlib.Path(__file__).resolve().parents[1] / "font3x5.json").read_text())["glyphs"]
    glyphs = ", ".join("{" + ", ".join(str(int(r, 2)) for r in font[ch]) + "}" for ch in SMP_GLYPHS)
    waves = []
    for snd in smp_live.test_samples():
        n = len(snd)
        col = []
        for c in range(SMP_WAVE_W):
            seg = snd[c * n // SMP_WAVE_W:max(c * n // SMP_WAVE_W + 1, (c + 1) * n // SMP_WAVE_W)]
            col.append(min(SMP_WAVE_AMP, round(max(abs(x) for x in seg) * SMP_WAVE_AMP)))
        waves.append("{" + ", ".join(map(str, col)) + "}")
    ids = sorted(w)
    q = chr(34)
    return (f"#define SMP_WAVE_W {SMP_WAVE_W}\n#define SMP_WAVE_AMP {SMP_WAVE_AMP}\n"
            + "".join(f"#define W_{k.upper()} {i}\n" for i, k in enumerate(kinds))
            + f"#define SMP_WIDGETS {len(ids)}\n"
            f"static const unsigned short smp_widget_ids[SMP_WIDGETS] = {{{', '.join(map(str, ids))}}};\n"
            f"static const unsigned char smp_widget_kind[SMP_WIDGETS] = {{{', '.join(str(kinds.index(w[r])) for r in ids)}}};\n"
            f"static const char smp_glyph_chars[] = {q}{SMP_GLYPHS}{q};\n"
            f"static const unsigned char smp_glyph[{len(SMP_GLYPHS)}][5] = {{{glyphs}}};\n"
            f"static const unsigned char smp_test_wave[{len(waves)}][SMP_WAVE_W] = {{{', '.join(waves)}}};\n")


def perc_c_header() -> str:
    """PERC's tables for page.c: the machines' names and what they are, the records its
    parameters sit on, and each machine's names for them (short, as chars; long, as an
    index into one list of distinct long names)."""
    q = chr(34)
    longs = sorted({lo for row in perc_names() for lo, _ in row})
    names = ", ".join(q + n + q for n in _perc.NAMES)
    desc = ", ".join(q + DESCRIPTIONS[n.split("-")[1]] + q for n in _perc.NAMES)
    shorts = ",\n".join(" {" + ", ".join(q + sh + q for _, sh in row) + "}" for row in perc_names())
    lidx = ",\n".join(" {" + ", ".join(str(longs.index(lo)) for lo, _ in row) + "}" for row in perc_names())
    return (f"#define PERC_N {_perc.N}\n#define PERC_TYPE_ID {TYPE_ID}\n"
            f"static const char perc_machine[PERC_N][7] = {{{names}}};\n"
            f"static const char perc_what[PERC_N][12] = {{{desc}}};\n"
            f"static const unsigned short perc_param_ids[8] = {{{', '.join(map(str, PARAM_IDS))}}};\n"
            f"static const char perc_short[PERC_N][8][5] = {{\n{shorts}\n}};\n"
            f"static const char *const perc_longs[{len(longs)}] = {{{', '.join(q + x + q for x in longs)}}};\n"
            f"static const unsigned char perc_long[PERC_N][8] = {{\n{lidx}\n}};\n"
            + md_c_header())


MDUI_LOAD = 0x46AF0000                          # the Machinedrum's screen graphics (dnfw.md.ui; 6.8 KB;
                                                # v0.41: up 64 KB, past the renderer's larger span)
assert C_LOAD + C_SPAN <= MDUI_LOAD and MDUI_LOAD + 0x8000 <= 0x46B00000, "renderer, MD graphics, the pool's mirror"
METER_RAM = 0x46AFF000                          # the system meter's state (csrc/meter), 256 B: its counters change
METER_BYTES = 0x100                             # at every context switch, so they live outside every CODE chunk
assert MDUI_LOAD + 0x8000 <= METER_RAM and METER_RAM + METER_BYTES <= 0x46B00000, "MD graphics, meter, mirror"
MOD_RAM = 0x46AF8000                            # 2026-11-11: csrc/modulation's state (the LFO cascade's
MOD_BYTES = 0x800                               # shadow cells, written in the audio ISR; the moving controls'
MOD_CASCADE_BYTES = 0x500                       # cells): RAM above BSS, like the meter's
assert MDUI_LOAD + 0x8000 <= MOD_RAM and MOD_RAM + MOD_BYTES <= METER_RAM, "MD graphics, modulation, meter"
# 2026-11-11, remoteui-5: the CPU profiler's state and sample ring (csrc/devtest/prof.c), written only while
# PROFILE runs. Above the DSP's tables (sampler.machines.TABLE_LOAD 0x47000000, up to 512 KB) and 14 MB under
# the boot stack's top (0x48000000; the tasks run on their own stacks in BSS, docs/coldfire-tasks.md)
PROF_RAM = 0x47100000
PROF_BYTES = 0x100000
assert 0x47000000 + (512 << 10) <= PROF_RAM and PROF_RAM + PROF_BYTES <= 0x47800000, "tables, profiler, stack"
# the wishes record's RAM (csrc/wishes/wish.h WISH_O_END; docs/wishes-record.md): the sorted index, the free
# stack, the hash cache, the queue of cells for the +Drive and 8,192 entries of 512 B. Above the DSP tables
# (dnfw.mods.waverider._tables, 0x47000000..) and remoteui's profiler (0x47100000..0x47200000, 1 MB,
# csrc/devtest/prof.c), far below the stack (from 0x48000000). docs/memory-map.md lists every claim up here
WISH_RAM = 0x47280000                           # 512 KB clear above the profiler
WISH_BYTES = 0x464200                           # 4 x 8192 + 2 x 8192 x 2 + 2 x 16384 + 512 x 512 + 512 + 6 x 8192 + 512 x 8192
assert PROF_RAM + PROF_BYTES + (512 << 10) <= WISH_RAM and WISH_RAM + WISH_BYTES <= 0x47800000, "DSP tables, profiler, wishes, the stack"
MX_RAM = 0x476F0000                             # the matrix's tables (csrc/matrix/matrix.c struct mx_state): each
MX_BYTES = 0x8000                               # track's routes laid out twice, the envelopes, the scratch row
assert WISH_RAM + WISH_BYTES <= MX_RAM and MX_RAM + MX_BYTES <= 0x47800000, "wishes, matrix, the stack"
MD_FX_NIBBLES = 0x31313311                      # AMD-AMF, EQF-EQG, FLTF-FLTW-FLTQ clipped, as the MD's
TRACK_LEVEL_ID = 10                             # record 10, "Track Level" / LEV, 0..0x7f00 (read from the 1.11 record table)


def md_c_header() -> str:
    """md_page.c's: where the MD's graphics are and how they are laid out (dnfw.md.ui: no
    Elektron data here), the FX page's clips, the machines' descriptions in capitals."""
    from ..md import ui
    q = chr(34)
    upper = ", ".join(q + DESCRIPTIONS[n.split("-")[1]].upper() + q for n in _perc.NAMES)
    return (ui.c_header() + f"#define MDUI_LOAD {MDUI_LOAD:#x}u\n#define MD_FX_NIBBLES {MD_FX_NIBBLES:#x}u\n"
            f"#define TRACK_LEVEL_ID {TRACK_LEVEL_ID}\n"
            f"static const char perc_what_upper[PERC_N][12] = {{{upper}}};\n")


def source(page_draw: int, cell: int) -> str:
    """The chunk's assembly (GNU as, ColdFire), linked at LOAD. PAGE_DRAW is the C
    renderer's entry, `wr_page_draw(view, canvas)`; CELL its `wr_cell(view, canvas, x,
    y, id)`, run as each cell widget of a stock page finishes (parameter slides' marks)."""
    table = "\n".join(f"    .long {rid}, lab_{rid}" for rid in LABELS)
    strings = "\n".join(f'lab_{rid}: .asciz "{name}"' for rid, name in LABELS.items())
    pages = []
    for k, entries in enumerate(PAGES):
        pages.append(f"    .long title_{k}, subtitle\n"
                     f"    .long {', '.join(str(e) for e in entries)}\n"
                     f"    .long {TAG}")
    page_data = "\n".join(pages)
    mlabs = [{**lab, **(MNM_LABELS2[k] if mnm_pages(_mnm.CF_MACHINES[k]) > 1 else {}),
              **(MNM_LABELS3[k] if mnm_pages(_mnm.CF_MACHINES[k]) > 2 else {})}
             for k, lab in enumerate(MNM_LABELS)]
    mtables = "\n".join(f"    .long mnm_labels_{k}" for k in range(len(mlabs)))
    mtables += "\n" + "\n".join(f"mnm_labels_{k}:\n" + "\n".join(f"    .long {rid}, mlab_{k}_{rid}" for rid in lab)
                                + "\n    .long 0" for k, lab in enumerate(mlabs))
    mstrings = "\n".join(f'mlab_{k}_{rid}: .asciz "{name}"' for k, lab in enumerate(mlabs)
                          for rid, name in lab.items())
    # v0.45: wr_label's Monomachine dispatch, one explicit test a kind, index k into
    # mnm_label_tables (not a range: a range let BOUNCE, kind 13, index past the table)
    if len(MNM_KINDS) != len(MNM_LABELS):
        raise ValueError(f"{len(MNM_KINDS)} Monomachine kinds, {len(MNM_LABELS)} label tables")
    mnm_label_pick = "\n".join(f"    moveq   #{kd - 1},%d1\n    cmp.l   %d1,%d0\n    bne.s   wl_n{k}\n"
                               f"    moveq   #{k},%d0\n    bra.s   wl_hit\nwl_n{k}:"
                               for k, kd in enumerate(MNM_KINDS))
    # 2026-11-11: each machine's knobs in its own order (mnm_order: a control keeps its record wherever it is drawn)
    mnm_page_data, mnm2_page_data, mnm3_page_data = (
        "\n".join(f"    .long mnm_title_{k}, mnm_subtitle_{k}\n"
                  f"    .long {', '.join(str(MNM_RECS[j][0]) for j in mnm_order(M)[8 * pg:8 * pg + 8])}\n"
                  f"    .long {TAG}" for k, M in enumerate(_mnm.CF_MACHINES))
        for pg in range(3))
    smp_page_data = "\n".join(f"    .long smp_title_{k}, smp_subtitle_{k}\n"
                              f"    .long {', '.join(str(e) for e in entries)}\n"
                              f"    .long {TAG}" for k, entries in enumerate(SMP_PAGES))
    smp_page_data += ("\nsmp_rec_descriptor:\n    .long smp_rec_title, smp_rec_subtitle\n"
                      f"    .long {', '.join(str(e) for e in SMP_REC_IDS)}\n    .long {TAG}")
    return f"""
| -- the active track's machine, as ours: d0 = its type - 4 for types 5..{TYPES_LAST}: 1 PERC,
| 4..9 the sample machines (8..13), 2, 3 and 10.. the Monomachine's (6, 7, 14..), else 0;
| every other register kept
is_wr:
    move.l  %a0,%sp@-
    move.l  %d1,%sp@-
    moveq   #0,%d1
    move.b  {ACTIVE_TRACK:#010x},%d1
    mulu.w  #{SOUND_STRIDE},%d1
    movea.l {KIT_POINTER:#010x},%a0
    adda.l  %d1,%a0
    mvs.b   %a0@({SOUND_BASE + SOUND_TYPE}),%d1
    moveq   #0,%d0
    subq.l  #{NEW_TYPE - 1},%d1
    ble.s   1f
    cmpi.l  #{TYPES_LAST - NEW_TYPE + 1},%d1
    bgt.s   1f
    move.l  %d1,%d0
1:  move.l  %sp@+,%d1
    movea.l %sp@+,%a0
    rts

| -- 0x400c2636 pages(type), from its first instruction by jsr. The stack: our return
| into the reader, the caller's return, the type. A Waverider track: 2, straight back
| to the caller. Otherwise M5's canon_arg: the displaced loads, 5 read as 1.
wr_count:
    bsr.w   is_wr
    tst.l   %d0
    beq.w   1f
    addq.l  #4,%sp
    subq.l  #1,%d0
    bne.w   3f
    moveq   #{len(PAGES)},%d0
    rts
3:  moveq   #2,%d1                         | d0 = kind - 1: 1, 2 and 9.. the Monomachine's
    cmp.l   %d1,%d0
    bls.w   4f
    moveq   #8,%d1
    cmp.l   %d1,%d0
    bls.w   5f
4:  moveq   #9,%d1                         | a Monomachine machine: its pages (2026-11-09: 1 or 2)
    cmp.l   %d1,%d0
    bcc.w   11f
    subq.l  #1,%d0                         | d0 = kind - 1: 1, 2 -> 0, 1
    bra.w   12f
11: subq.l  #7,%d0                         | 9.. -> 2..
    move.l  %a0,%sp@-                      | (2026-11-10) the computed kind - 8 -> the machine's index
    lea     mnm_ix_tab,%a0                 | (types past BOUNCE's 17 are one place lower)
    move.b  %a0@(0,%d0:l),%d0
    andi.l  #0xff,%d0
    movea.l %sp@+,%a0
12: move.l  %a0,%sp@-
    lea     mnm_npages_tab,%a0
    moveq   #0,%d1
    move.b  %a0@(0,%d0:l),%d1
    movea.l %sp@+,%a0
    move.l  %d1,%d0
    rts
5:  moveq   #2,%d0                         | a sample machine: its two pages (v0.22: the recorder is FUNC + VOICE)
    rts
1:  move.l  %sp@(8),%d0
    cmpi.l  #{NEW_TYPE},%d0
    blt.w   2f
    cmpi.l  #{TYPES_LAST},%d0
    bgt.w   2f
    moveq   #{CLONE},%d0
2:  moveq   #4,%d1
    rts

| -- 0x400c2652 page(type, n), from 0x400c2656 by jsr (after its own push of d2). The
| stack: our return, the saved d2, the caller's return, the type, the page. A Waverider
| track: our descriptor n (0..1) or the stock empty page, and back to the caller with d2
| restored. Otherwise M5's canon_page.
wr_page:
    bsr.w   is_wr
    tst.l   %d0
    beq.w   3f
    subq.l  #1,%d0
    bne.w   5f
    move.l  %sp@(16),%d0
    moveq   #{len(PAGES)},%d1
    cmp.l   %d1,%d0
    bcs.w   1f
6:  move.l  #{EMPTY_PAGE:#010x},%d0
    bra.w   2f
1:  moveq   #44,%d1
    mulu.w  %d1,%d0
    addi.l  #descriptors,%d0
    bra.w   2f
| d0 = kind - 1: 1, 2 -> the Monomachine's 0, 1; 3..8 a sample machine; 9.. -> 2..;
| v0.44: 12 (BOUNCE, kind 13) -> the sample row 6 (d0 9 at 4:, as 3..8 give 0..5)
5:  moveq   #{_smp.BOUNCE_TYPE - 5},%d1
    cmp.l   %d1,%d0
    bne.w   10f
    moveq   #{len(_smp.NAMES) + 2},%d0
    bra.w   4f
10: moveq   #9,%d1
    cmp.l   %d1,%d0
    bcc.w   7f
    moveq   #3,%d1
    cmp.l   %d1,%d0
    bcc.w   4f
    addq.l  #6,%d0
7:  subq.l  #7,%d0                         | the Monomachine machine's index
    move.l  %a0,%sp@-                      | (2026-11-10) the computed kind - 8 -> the machine's index
    lea     mnm_ix_tab,%a0                 | (types past BOUNCE's 17 are one place lower)
    move.b  %a0@(0,%d0:l),%d0
    andi.l  #0xff,%d0
    movea.l %sp@+,%a0
    move.l  %a0,%sp@-                      | its page 0..npages - 1 (2026-11-09: 2; 2026-11-11: 3), else
    lea     mnm_npages_tab,%a0             | the empty page
    moveq   #0,%d1
    move.b  %a0@(0,%d0:l),%d1
    movea.l %sp@+,%a0
    cmp.l   %sp@(16),%d1
    bls.w   6b
    move.l  %sp@(16),%d1
    beq.w   10f
    subq.l  #1,%d1
    beq.w   13f
    moveq   #44,%d1                        | page 3
    mulu.w  %d1,%d0
    addi.l  #mnm3_descriptors,%d0
    bra.w   2f
13: moveq   #44,%d1                        | page 2
    mulu.w  %d1,%d0
    addi.l  #mnm2_descriptors,%d0
    bra.w   2f
10: moveq   #44,%d1
    mulu.w  %d1,%d0
    addi.l  #mnm_descriptors,%d0
    bra.w   2f
4:  subq.l  #2,%d0
| a sample machine (d0 = its kind - 3): pages 0 and 1 its own (the DT2's SRC page 1 and
| page 2, the same parameters), page 2 the recorder
8:  move.l  %sp@(16),%d1
    subq.l  #2,%d1
    bcs.w   9f
    bne.w   6b
    move.l  #smp_rec_descriptor,%d0
    bra.w   2f
9:  subq.l  #1,%d0
    moveq   #44,%d1
    mulu.w  %d1,%d0
    addi.l  #smp_descriptors,%d0
2:  addq.l  #4,%sp
    move.l  %sp@+,%d2
    rts
3:  move.l  %sp@(12),%d1
    move.l  %sp@(16),%d0
    cmpi.l  #{NEW_TYPE},%d1
    blt.w   0f
    cmpi.l  #{TYPES_LAST},%d1
    bgt.w   0f
    moveq   #{CLONE},%d1
0:  rts

| -- the SYN page's label fetch at 0x40064622 (jsr getShortName(this, id)), now jsr
| here. A Waverider track and a relabelled id: our label. Anything else: the stock
| getShortName, by a tail jump, so it returns to the page itself.
wr_label:
    bsr.w   is_wr
    tst.l   %d0
    beq.w   9f
    lea     labels,%a0
    subq.l  #1,%d0
    beq.w   0f
| d0 = kind - 1. Only a Monomachine machine's kind (MNM_KINDS, each named below) reads
| mnm_label_tables; every other kind -- the sample machines, BOUNCE, and any type
| added later -- gets the stock names (wr_names swapped them in). v0.44 tested ranges
| here (3..8 stock, 9.. "the Monomachine's"), so BOUNCE (kind 13) read entry 5 of the
| five-entry table: the first id of table 0 (0xEE), walked as a label table from
| absolute address 0x000000EE -- the unit froze drawing the first cell of any page of a
| BOUNCE track (MACHINE SEL's YES; every boot of a project holding one).
{mnm_label_pick}
    bra.w   9f
wl_hit:
    lsl.l   #2,%d0
    lea     mnm_label_tables,%a0
    adda.l  %d0,%a0
    movea.l %a0@,%a0
0:  move.l  %sp@(8),%d0
1:  move.l  %a0@+,%d1
    beq.w   9f
    cmp.l   %d0,%d1
    beq.w   2f
    addq.l  #4,%a0
    bra.w   1b
2:  move.l  %a0@,%d0
    rts
9:  jmp     {GET_SHORT_NAME:#010x}

| -- the SYN page draw at 0x4001821e (`moveq #7 ; cmp.l %d3,%d0 ; bne.w` past the icons),
| now `jsr` here and a nop. Back to the icons (0x40018226) when the stock test would draw
| them: page id 7 in d3, and not a Waverider track. Otherwise the return address becomes
| the stock branch target, past them. d0 is scratch there (the stock code loads it).
wr_icons:
    bsr.w   is_wr
    tst.l   %d0
    bne.s   3f
    moveq   #{ICON_PAGE},%d0
    cmp.l   %d3,%d0
    beq.s   2f
1:  move.l  #{ICON_SKIP:#010x},%sp@
2:  rts
| a Waverider track: never WaveTone's icons (its page, wave included, is wr_grid's)
3:  bra.s   1b

| -- the SYN page draw at 0x40018214 (`move.l %d2,-(%sp) ; move.l %a2,-(%sp) ; jsr grid ;
| addq.l #8,%sp`, 10 bytes), now jsr here and two nops. a2 = the view, d2 = the canvas.
wr_grid:
    move.l  %d2,%sp@-
    move.l  %a2,%sp@-
    bsr.w   is_wr
    tst.l   %d0
    beq.s   1f
    jsr     {page_draw:#010x}
    addq.l  #8,%sp
    rts
1:  jsr     {GRID:#010x}
    addq.l  #8,%sp
    rts

| -- the exit of 0x4006448a, a page's cell widget (view, canvas, x, y, id, ...), at
| 0x400646ca, now `jmp` here: its own epilogue, then wr_cell(view, canvas, x, y, id)
| with its d0 and d1 kept, and back to its caller.
wr_cell_tail:
    movem.l %sp@,%d2-%d7/%a2-%a6
    lea     %sp@(80),%sp
    movea.l %sp,%a1
    move.l  %d0,%sp@-
    move.l  %d1,%sp@-
    move.l  %a1@(20),%sp@-
    move.l  %a1@(16),%sp@-
    move.l  %a1@(12),%sp@-
    move.l  %a1@(8),%sp@-
    move.l  %a1@(4),%sp@-
    jsr     {cell:#010x}
    lea     %sp@(20),%sp
    move.l  %sp@+,%d1
    move.l  %sp@+,%d0
    rts

| -- the SYN page draw at 0x40018202 (`moveq #9,%d1 ; cmp.l %d3,%d1 ; bne.s` to the grid
| call), now jsr here: back to the id-9 grid variant (0x40018208) only when the stock
| test would go there -- page id 9 in d3 and not one of our tracks; otherwise to the
| standard grid's call ({ID9_GRID:#010x}), which wr_grid answers. d1 = 9 either way,
| as stock leaves it; d0 is scratch (the grid call follows).
wr_id9:
    bsr.w   is_wr
    moveq   #9,%d1
    tst.l   %d0
    bne.s   1f
    cmp.l   %d3,%d1
    beq.s   2f
1:  move.l  #{ID9_GRID:#010x},%sp@
2:  rts

    .align 2
labels:
{table}
    .long 0
mnm_label_tables:
{mtables}
descriptors:
{page_data}
mnm_descriptors:
{mnm_page_data}
mnm2_descriptors:
{mnm2_page_data}
mnm3_descriptors:
{mnm3_page_data}
mnm_ix_tab:
    .byte {", ".join(str(_mnm_ix(d)) for d in range(max(MNM_KINDS) - 7))}
    .align 2
mnm_npages_tab:
    .byte {", ".join(str(mnm_pages(M)) for M in _mnm.CF_MACHINES)}
    .align 2
smp_descriptors:
{smp_page_data}
{_rep("subtitle", SUBTITLE)}
{chr(10).join(_rep(f"mnm_title_{k}", t) for k, t in enumerate(MNM_TITLES))}
{chr(10).join(_rep(f"mnm_subtitle_{k}", t) for k, t in enumerate(MNM_SUBTITLES))}
{chr(10).join(_rep(f"smp_title_{k}", t) for k, t in enumerate(SMP_TITLES))}
{chr(10).join(_rep(f"smp_subtitle_{k}", t) for k, t in enumerate(SMP_SUBTITLES))}
{_rep("smp_rec_title", "REC")}
{_rep("smp_rec_subtitle", "Recorder")}
{chr(10).join(_rep(f"title_{k}", t) for k, t in enumerate(TITLES))}
{strings}
{mstrings}
    .align 2
"""
