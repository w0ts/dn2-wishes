"""The A2 filter machines' names on the FLTR page (2026-11-10; PING's and SHFT's mechanism, P2, S2, both removed).

A PING (6) or SHFT (7) track's FLTR page is Multi-Mode's page (`dnfw.ping.coldfire`):
the same records, which the DSP side reads as that type's controls (`dnfw.ping.live`,
`dnfw.shft.live`). While the active track's filter is one of them, `flt_names`
(csrc/waverider/page.c, from the UI loop's poll, as W2's `wr_names` does for Waverider)
points the records whose meaning changes at that type's names, so the page, the LFO and
modulation destination lists and the header's parameter line all say what the knob
does; the stock pointers go back as soon as it is neither. Records whose meaning is
unchanged keep their names.

    PING   ATK  DEC  CURV STRK  /  FREQ RING TYPE ENV     (DRIV on page 2)
    SHFT   ATK  DEC  MIX  -     /  SHFT FDBK MODE ENV     (DRIV on page 2)
    GRAN   FDBK -    MIX  -     /  SIZE DENS MODE SPRD    (DRIV on page 2)
"""

from __future__ import annotations

SETS: dict = {}           # filter type -> {record id: (long name, short name)}, short <= 5
# 2026-11-09: ANALOG 2's filters as filter machines 7..11 (dnfw.engines.analog2.filters, docs/a2f.md), two filters each;
# the User's page: ATK DEC FRQ2 RES2 / FREQ RES MODE ENV, page 2 MOD2 . . KEY.T / BASE WDTH BW.RT RSET
A2F_NAMES = {38: ("Filter Mode", "MODE"),     # Multi-Mode's Filter Type: filter 1's mode
             47: ("Filter 2 Freq", "FRQ2"),   # ... Sustain Level: filter 2's cutoff
             48: ("Filter 2 Reso", "RES2"),   # ... Release Time: filter 2's resonance
             44: ("Filter 2 Mode", "MOD2")}   # ... Env. Delay: filter 2's mode
A2F_MODES = ("LP12", "LP24", "BP", "HP", "NTCH")


def _a2f_types() -> tuple[int, ...]:
    from . import design
    return design.BUILT_TYPES


for _t in _a2f_types():
    SETS[_t] = dict(A2F_NAMES)


def ids() -> list[int]:
    return sorted({rid for names in SETS.values() for rid in names})


# the TYPE cell (Multi-Mode's Filter Type, record 38) as text, quarters / thirds of its
# range: what the type's core or mode is called (dnfw.ping.live.TYPES, shft.live.MODES)
TYPE_ID = 38
MOD2_ID = 44                                      # 2026-11-09: the A2 filters' second mode, as text too
TEXT_IDS = (TYPE_ID, MOD2_ID)
# filter type -> {record id: the choices' names}; a record a type does not name stays a stock knob
TEXT: dict = {}
for _t in _a2f_types():
    TEXT[_t] = {TYPE_ID: A2F_MODES, MOD2_ID: A2F_MODES}
TYPE_TEXT = {t: TEXT[t][TYPE_ID] for t in TEXT}


def c_header() -> str:
    if not SETS:                              # no filter machine in this build
        return "#define FLT_SETS 0\n"
    q = chr(34)
    order = ids()
    filters = sorted(SETS)

    def row(t, col):
        return "{" + ", ".join(q + SETS[t][r][col] + q if r in SETS[t] else "0" for r in order) + "}"
    return (f"#define FLT_SETS {len(filters)}\n"
            f"static const signed char flt_filters[FLT_SETS] = {{{', '.join(map(str, filters))}}};\n"
            f"#define FLT_NAMED {len(order)}\n"
            f"static const unsigned short flt_named_ids[FLT_NAMED] = {{{', '.join(map(str, order))}}};\n"
            f"static const char *const flt_named_long[FLT_SETS][FLT_NAMED] = "
            f"{{{', '.join(row(t, 0) for t in filters)}}};\n"
            f"static const char *const flt_named_short[FLT_SETS][FLT_NAMED] = "
            f"{{{', '.join(row(t, 1) for t in filters)}}};\n"
            f"#define FLT_TEXT_IDS {len(TEXT_IDS)}\n"
            f"static const unsigned short flt_text_ids[FLT_TEXT_IDS] = {{{', '.join(map(str, TEXT_IDS))}}};\n"
            f"static const unsigned char flt_type_count[FLT_SETS][FLT_TEXT_IDS] = "
            f"{{{', '.join('{' + ', '.join(str(len(TEXT[t].get(i, ()))) for i in TEXT_IDS) + '}' for t in filters)}}};\n"
            f"static const char flt_type_text[FLT_SETS][FLT_TEXT_IDS][5][5] = "
            f"{{{', '.join('{' + ', '.join('{' + (', '.join(q + x + q for x in TEXT[t].get(i, ())) or q + q) + '}' for i in TEXT_IDS) + '}' for t in filters)}}};\n")
