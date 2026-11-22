"""Waverider on the ColdFire: machine type 5, offered by MACHINE SEL, a WaveTone clone
everywhere else (`docs/waverider-feasibility.md`, "Milestone 5").

The DSP renders type 5 with our own code (section 7, `dnfw.waverider.dsp`). The
ColdFire's job is smaller and is only this:

1. **offer it** -- MACHINE SEL lists the machine types from a static list
   (`{0, 2, 1, 3, 4}` at `0x401de168`, copied into a `std::vector` by
   `0x4004d8b6`) and draws a divider wherever the group `0x40059274(type)`
   changes. The list gains a 5 before MIDI, and 5 (with 6, reserved for
   a second sample machine) is a group of its own, so it reads synths | WAVERIDER | MIDI;
2. **name it** -- the three name accessors (`0x400dc496` long, `0x400dc4bc`
   short, `0x400dc4e2` the third column) are bounded at 4 and read 12-byte rows
   at `0x401f7c04`. The 192 zero bytes after that table are a live 16-long
   array (`0x400dc362`, `docs/machine-list.md`), so the table moves to a cave
   with a sixth row, `Waverider` / `WVR`;
3. **permit it** -- the per-type attribute rows at `0x401f7d40` (a byte, then a
   16-bit track mask) are read by the permission test `0x400dc2fe(type, track)`
   that the machine setter `0x4004cc08` asks before it writes `sound+0xDE`, and
   by two neighbours. Row 5 would be the 16-long table at `0x401f7d54`, so these
   move too, with WaveTone's row as the sixth;
4. **behave as WaveTone** -- the one place the sound's machine parameters are
   resolved, `param_set_slot_to_id(slot, type, filter)` (`0x400dc18e`), sends
   type 5 to WaveTone's forty machine slots. So the SYN pages are WaveTone's
   pages, WaveTone's defaults load when the machine is chosen, and the frame
   carries WaveTone's machine parameters -- `WAV1` (index 26) is Waverider's
   POS and `TBL1` (27) its SLOT on the DSP side.

What is **not** changed: the sound's machine type byte stays 5 (so it is saved
and loaded by the stock mechanism, and the frame builder `0x400274ba` sends 5
at frame offset `148 + 2t` from the per-track mirror it already keeps), and no
new storage is added anywhere.

Pure: `compose(stock, assemble)` takes the stock MAIN OS and an assembler
(`dnfw.patch.assemble.assemble`), and returns the edits. Every edit carries the
stock bytes it replaces, and every cave must be zero, with a 4-byte margin.
"""

from __future__ import annotations

import struct

from . import pages
from dataclasses import dataclass

BASE = 0x40000400
NEW_TYPE = 5
from ..mnm import machines as _mnm           # noqa: E402
# PERC; the Monomachine's machines (docs/mnm.md: 6, 7, then 14.. after the sample machines);
# the Digitakt II's sample machines (docs/sampler.md, 8..13): all WaveTone clones
from ..sampler import machines as _smpm         # noqa: E402
NEW_TYPES = tuple(range(5, max(13, *_mnm.CF_TYPES, _smpm.BOUNCE_TYPE) + 1))   # v0.44: BOUNCE 17; ours to 20, with the removed machines' reserved types
CLONE = 1                               # WaveTone
LONG_NAME, SHORT_NAME = "Perc", "PRC"           # v0.11: PERC in Waverider's place
MACHINE_NAMES = {5: ("Perc", "PRC"),
                 8: ("Oneshot", "ONE"), 9: ("Werp", "WRP"), 10: ("Stretch", "STR"),
                 11: ("Repitch", "RPT"), 12: ("Grid", "GRD"), 13: ("Slice", "SLC"),
                 _smpm.BOUNCE_TYPE: ("Flex", "FLX"),       # v0.44: a section of its own, after the sample machines
                 **{t: nm for t, nm in zip(_mnm.CF_TYPES, _mnm.CF_LIST_NAMES)}}   # v0.26; a reserved type: Removed
if set(MACHINE_NAMES) != set(NEW_TYPES):
    raise ImportError(f"machine types {sorted(set(NEW_TYPES) - set(MACHINE_NAMES))} have no machine")
# RESONATOR (2026-10-18): the shims, the name table, the attribute rows and the list
# outgrew the three caves W5 used, so all of it is a platform CODE chunk in RAM, after
# what was PING's (0x4670F000..; v0.45: PING removed) and below the platform runtime; the caves are
# left as stock had them.
MCHUNK = 0x4670F800
PAGES_END = 0x4670E000                  # the pages assembly's room ends here; 0x4670E000..0x4670F000 is the boot-screen
                                        # stamp's (scripts/gen_bootscreen_code.py LOAD_VA, 1.12)
MCHUNK_END = 0x46710000

# -- 1. the MACHINE SEL list -------------------------------------------------------------
LIST_STOCK_VA = 0x401DE168             # {0, 2, 1, 3, 4}, five longs
LIST_STOCK = (0, 2, 1, 3, 4)
# PERC, RESONATOR, CZ after Swarmer; then the Digitakt II's sample machines in its own
# order (v0.15: all five; v0.13 offered ONESHOT and GRID); then MIDI
LIST_NEW = (0, 2, 1, 3, 5, *_mnm.LIST_TYPES, 8, 9, 10, 11, 13, 12, *((_smpm.BOUNCE_TYPE,) if _smpm.BOUNCE_LISTED else ()), 4)   # v0.19: SLICE before GRID, the DT2's order; v0.44 BOUNCE after them (group 3: its own divider); never a reserved type
LIST_ALLOC = 0x4004D8E0                 # pea 0x14 -- the vector's storage, 5 longs
LIST_END = 0x4004D900                   # pea 0x401de17c -- the copy's end
LIST_CAP = 0x4004D906                   # lea %a0@(20),%a0 -- the vector's capacity
LIST_BEGIN = 0x4004D90A                 # pea 0x401de168 -- the copy's start

GROUP_FN = 0x40059274                   # group(type): <0 or >4 -> 0, 0..3 -> 1, 4 -> 2
GROUP_STOCK = bytes.fromhex("202f00046d147203b2806c0a123c0004b280670a600470014e7542004e7570024e75")

# -- 2. the name table -------------------------------------------------------------------
NAMES_STOCK_VA = 0x401F7C04             # 5 rows of {long, short, third}
NAME_ROW = 12
NAME_SITES = (                          # (bound site, base site, stock base, column)
    (0x400DC496, 0x400DC4A6, "41f9", 0),     # long:  moveq #4 / lea table,%a0
    (0x400DC4BC, 0x400DC4CE, "0680", 4),     # short: moveq #4 / addil table+4,%d0
    (0x400DC4E2, 0x400DC4F4, "0680", 8),     # third: moveq #4 / addil table+8,%d0
)

# -- 3. the per-type attribute rows ------------------------------------------------------
ATTR_STOCK_VA = 0x401F7D40              # 5 rows of {byte, 0, u16 track mask}
ATTR_ROW = 4
ATTR_BOUNDS = (0x400DC2C0, 0x400DC300)  # moveq #4 (byte getter), moveq #4 (permission)
ATTR_BASES = ((0x400DC2CA, 0), (0x400DC2E4, 2), (0x400DC316, 2))   # lea site, column

# -- 4. param_set_slot_to_id: type 5 resolves as WaveTone ---------------------------------
SLOT_TO_ID = 0x400DC18E
SLOT_HOOK = 0x400DC196                  # movel %sp@(12),%d0 ; moveal %sp@(16),%a1
SLOT_HOOK_STOCK = bytes.fromhex("202f000c226f0010")
SLOT_RESUME = 0x400DC19E
# 2026-11-14, DN2_LFO4 (docs/lfo-112-port.md 4.4, the cascade with LFO4): LFO4's value slots 101..108 answered with
# lfo4's records (ids 321..330, rows 320..329: dnfw.patch.lfo4records), as LFO3's slots 17..24 are answered from
# stock's runtime table (0x400dc1c6) plus the distance between the two groups; and the two bounds that keep a slot
# above 100 out of the destination builder's walk and the evaluator's DEST write
SLOT_EXIT = 0x400DC210                  # movel %sp@+,%d2 ; rts
SLOT_TABLE = 0x42C65B3C                 # stock's runtime table: slot -> id, for slots up to 24
LFO4_SLOTS, LFO3_SLOTS, LFO4_ID_SHIFT = 101, 17, 321 - 95   # LFO4's first slot, LFO3's; ids 95.. -> 321..
BUILDER_BOUND, BUILDER_BOUND_STOCK = 0x400395B8, bytes.fromhex("7265")   # moveq #101 (the walk's end)
BUILDER_RESERVE, BUILDER_RESERVE_STOCK = 0x4003956E, bytes.fromhex("0065")   # pea 0x65's word (the list's room)
EVAL_DEST_BOUND, EVAL_DEST_BOUND_STOCK = 0x40137D6E, bytes.fromhex("7264")   # moveq #100 (DEST past it: no write)

# -- 5. the stored-sound LOAD (0x400dd34e) --------------------------------------------------
# `d1 = (stored[244] + 1) & 0xff; keep the type if 6 > d1, else 0`. The bound is
# a `moveq #6,%d2` reused for nothing else before the compare (the filter type
# loads its own `moveq #7`). SAVE copies `sound+0xDE` to `stored+244` as it is.
LOAD_BOUND = 0x400DD3EA
# 2026-11-11, the wishes record (csrc/wishes, docs/wishes-record.md): every reference to stock's memcpy and
# memset, and the stored-sound loader and saver just past their value loops. The load site's 6 bytes hold that
# bound: its stub replays `moveq #TYPES_LAST + 2,%d2`, so one hook owns it.
# memcpy and memset themselves stay stock (they are on Overbridge's audio path, scripts/gate_overbridge.py): each
# jsr / jmp / lea / move.l # that names them names the wishes stub instead (the User, 2026-11-11: "A: keep
# Overbridge stock"), except the four in Overbridge's own code (measured: they copy 56/84 B packet pieces, 32 B
# input pieces, 108 B records and a DSP-side block, never a sound), whose operands are WISH_KEEP
WISH_MEMCPY = 0x40134770
WISH_MEMSET = 0x401347B8
WISH_KEEP = (0x400031A8,                # lea memcpy,%a3 in the Overbridge packet builder (0x40003118)
             0x40003436,                # lea memcpy,%fp in the Overbridge input (0x40003376)
             0x400CF958,                # jsr memcpy, a DSP-side block from 0x80001a20 (the audio interrupt's path)
             0x400D7ED4)                # move.l #memcpy,%d4, 108 B records (the audio interrupt's path)
# v0.52 merge: references another hook already takes, left to it: the frame ISR's 14-byte frame copy (MUTE_SITE's jsr,
# upstream v0.52's ms_frame; the audio interrupt's path, as WISH_KEEP's)
WISH_HOOKED = (0x400275B2,
               0x400254F2, 0x4002594E)  # 2026-11-21: MOD SETUP's two copies into a voice (MXS_COPY_SITES)
# 2026-11-21 (csrc/matrix/setup.c, setup.S; docs/matrix.md "MOD SETUP's rows"): stock's two copies of a sound's 153 MOD
# SETUP bytes into a voice (0x4002549c at a note, 0x4002591e at an edit) load memcpy into %a3 once; that `lea` names
# mxs_copy (a muted entry lands with depth 0; any other size goes on to wish_memcpy_stub as the wishes build did)
MXS_COPY_SITES = (0x400254F0, 0x4002594C)
MXS_COPY_STOCK = bytes.fromhex("47f940134770")          # lea 0x40134770,%a3
# 2026-11-18 (the User's CPU, claude/cpu-cuts): the audio interrupt's memcpy calls in its voice loop (four a voice, 16
# voices) and just past it (four) become one jsr each to a copy of the same bytes (csrc/wishes/hooks.S); the bytes
# they jump over stay stock (their memcpy references are still named, by the loop below, and never run)
VOICE_COPY_SITE = 0x40027526            # pea 0x52 ; pea 84(%a5) ; pea 218(%a4) ; jsr (%a1) -> jsr ; bra.s 0x40027574
VOICE_COPY_STOCK = bytes.fromhex("48780052486d0054")
POST_COPY_SITE = 0x400275B6             # pea 0x12 ; pea 3330(%a2) ; pea 0x... -> lea 12(%sp) ; jsr ; bra.s 0x40027612
POST_COPY_STOCK = bytes.fromhex("48780012486a0d0248798000")
WISH_REFS = {WISH_MEMCPY: 694, WISH_MEMSET: 307}     # every reference in stock 1.12's MAIN OS (measured)
# the instructions a reference may be the operand of: jsr / jmp abs.l, lea abs.l,An, move.l #imm,Dn
WISH_OPS = {0x4EB9, 0x4EF9} | {0x41F9 | r << 9 for r in range(8)} | {0x203C | r << 9 for r in range(8)}
WISH_LOAD_SITE = 0x400DD3E6             # mvs.b 28(%a2),%d0 ; moveq #6,%d2 (a2 live, a3 stored)
WISH_LOAD_STOCK = bytes.fromhex("712a001c7406")
WISH_SAVE_SITE = 0x400DD888             # mvs.b 54(%a2),%d0 ; move.l (%a0,%d0.l*4),%d0 (a2 stored, a3 live)
WISH_SAVE_STOCK = bytes.fromhex("712a003620300c00")
# the wishes record on kits and patterns (csrc/wishes/item.c, items.S): past each loader's and saver's own work
WISH_KIT_LOAD_SITE = 0x400DDF52         # pea 10264(%a2) ; lea 23840(%a3),%a3 (a3 live kit, a2 stored)
WISH_KIT_LOAD_STOCK = bytes.fromhex("486a281847eb5d20")
WISH_KIT_SAVE_SITE = 0x400DE0CE         # moveq #4,%d0 ; move.l %d0,4(%a2) (a3 live kit, a2 stored)
WISH_KIT_SAVE_STOCK = bytes.fromhex("700425400004")
WISH_PAT_LOAD_SITE = 0x400DE85E         # move.l #122474,%d0 (a2 live pattern, d2 stored + 68148)
WISH_PAT_LOAD_STOCK = bytes.fromhex("203c0001de6a")
WISH_PAT_SAVE_SITE = 0x400DE9B2         # movea.l %d2,%a0 ; moveq #4,%d1 ; move.l %d1,(%a0) (d2 stored)
WISH_PAT_SAVE_STOCK = bytes.fromhex("204272042081")
WISH_SONG_LOAD_SITE = 0x400DEC52        # move.l 3679(%a2),%d1 ; clr.l %d0 (a2 live song, a3 stored)
WISH_SONG_LOAD_STOCK = bytes.fromhex("222a0e5f4280")
WISH_SONG_SAVE_SITE = 0x400DEDB8        # clr.l (%a2) ; lea 12(%sp),%sp (a2 stored, live at 40(%sp))
WISH_SONG_SAVE_STOCK = bytes.fromhex("42924fef000c")
WISH_PS_LOAD_SITE = 0x400DF58C          # move.w 236(%a3),%d1 ; mvs.w %d1,%d0 (a2 live settings, a3 stored)
WISH_PS_LOAD_STOCK = bytes.fromhex("322b00ec7141")
WISH_PS_SAVE_SITE = 0x400DF89E          # moveq #2,%d0 ; move.l %d0,(%a2) ; moveq #1,%d0 (a2 stored, a3 live)
WISH_PS_SAVE_STOCK = bytes.fromhex("700224807001")

# the caves: clean runs from `dnfw cave scan` that no other mod writes, entered
# 4 bytes in and left 4 bytes short, as arpmodes does (docs/memory-map.md).
# (W5 to v0.5: DATA_CAVE 0x4028ee98, CODE_CAVE 0x402908bc, NAME_CAVE 0x4028e064; now unused)

# Read, never written: what the edits rely on.
GUARDS = (
    (0x400DC18E, "2f027264206f0008", "slot_to_id: saves d2, d1 = 100, a0 = slot"),
    (0x400DC19E, "b288", "slot_to_id resumes with cmpl %a0,%d1"),
    (0x400DC1A4, "7402", "... and overwrites d2 before it reads it"),
    (0x4004CC42, "4eb9400dc2fe", "the machine setter asks the permission test"),
    (0x4004CC94, "114200de", "... and writes the type byte at sound+0xDE"),
    (0x4002757C, "10280d8c", "the frame builder takes each track's type from its mirror"),
    (0x40027582, "37400092", "... and writes it at frame offset 148 + 2t"),
    (0x4005B35C, "2a1b", "MACHINE SEL walks the list..."),
    (0x4005B364, "4eb940059274", "... and asks the group of each type"),
    (0x4005B6C2, "4eb94003134e", "MACHINE SEL's current machine (view +412) is 0x4003134e"),
    # v0.35, colsw: the column switch, the row vectors and the follow it relies on
    (0x4005BA9C, "254001a8", "MACHINE SEL LEFT / RIGHT writes the column (+424)"),
    (0x4005BAB6, "256a01a001a4", "... and the cursor (+420) from the filter type (+416)"),
    (0x4005B162, "2f0a2f02206f000c202801a8", "the type under the cursor(view) saves a2, d2; reads +424"),
    (0x4005A92C, "206f0004202801a8", "rows in the column(view)"),
    (0x4005A956, "2f0a2f02246f000c", "the scroll-follow(view) saves a2 and d2"),
)


@dataclass(frozen=True)
class Edit:
    va: int
    stock: bytes
    new: bytes
    what: str

    def to_json(self) -> dict:
        return {"va": self.va, "stock": self.stock.hex(), "new": self.new.hex(), "what": self.what}


class ComposeError(ValueError):
    """The image is not the one these edits were read from."""


def _read(content: bytes, va: int, n: int) -> bytes:
    return bytes(content[va - BASE:va - BASE + n])


def _need(content: bytes, va: int, want: bytes, why: str) -> None:
    have = _read(content, va, len(want))
    if have != want:
        raise ComposeError(f"{va:#010x}: expected {want.hex()}, found {have.hex()} ({why})")


def _long(v: int) -> bytes:
    return struct.pack(">I", v & 0xFFFFFFFF)


SAMPLE_GROUP = 3                        # our synth machines: PERC (5), the Monomachine's (6, 7, 14..)
SAMPLER_GROUP = 4                       # the sample machines (8..13), a section of their own
SAMPLER_FIRST, SAMPLER_LAST = 8, 13
TYPES_LAST = NEW_TYPES[-1]              # every type 5..TYPES_LAST is a WaveTone clone

# MACHINE SEL (and the second list at 0x40059cdc) inserts a divider row -- an
# unlabelled row of value -1, drawn as dots -- wherever this group changes. The
# groups are only compared for equality, so a third one is just another section.
GROUP_SOURCE = f"""
| group(type), rewritten in place at {GROUP_FN:#010x}: the synths 0..3 -> 1, MIDI (4)
| -> 2, the sample machines {SAMPLER_FIRST}..{SAMPLER_LAST} -> {SAMPLER_GROUP}, every other type from
| {NEW_TYPE} on (PERC, the Monomachine's: 5..7, 14..) -> {SAMPLE_GROUP}, a negative one 0 (stock: 0..3 ->
| 1, 4 -> 2, else 0). d0 holds the answer to each test before it is made, and every
| branch follows the instruction that set its flags: `moveq` clears C, so it never sits
| between a `subq` and its `bcs` (the first version of this did, and put the synths in
| group 0 -- the emulator caught it). Borrows are unsigned, after the sign test. Callers
| read the low byte. 34 bytes, the stock function's own size (v0.26: 5..7 and 14.. one
| group, so the Monomachine's machines after the sample machines in type order still sit
| together in the list).
    moveq   #0,%d0
    move.l  %sp@(4),%d1
    blt.s   9f
    moveq   #1,%d0
    subq.l  #4,%d1
    bcs.s   9f
    moveq   #2,%d0
    tst.l   %d1
    beq.s   9f
    moveq   #{SAMPLER_GROUP},%d0
    subq.l  #{SAMPLER_FIRST - 4},%d1
    bcs.s   8f
    subq.l  #{SAMPLER_LAST - SAMPLER_FIRST + 1},%d1
    bcs.s   9f
8:  moveq   #{SAMPLE_GROUP},%d0
9:  rts
"""


def group_function(assemble) -> bytes:
    code = assemble(GROUP_SOURCE, base=GROUP_FN)
    if len(code) > len(GROUP_STOCK):
        raise ComposeError(f"the group function grew: {len(code)} > {len(GROUP_STOCK)}")
    return code + bytes(len(GROUP_STOCK) - len(code))


TRACK_TYPE_EXIT = 0x4004B81E            # getMachineType(track): its common exit

def _lfo4_slots() -> str:
    """DN2_LFO4: slots 101..108 -> lfo4's records, at the shim's start (a0 the slot; d2 saved at entry)"""
    if not pages.lfo4_on():
        return ""
    return f"""    move.l  %a0,%d2                        | DN2_LFO4: LFO4's slots 101..108
    subi.l  #{LFO4_SLOTS},%d2
    moveq   #7,%d0
    cmp.l   %d2,%d0
    bcs.s   9f                             | not one of them
    lea     {SLOT_TABLE + 4 * LFO3_SLOTS:#010x},%a1
    move.l  %a1@(0,%d2.l*4),%d0            | the record LFO3's same control has
    beq.s   8f
    addi.l  #{LFO4_ID_SHIFT},%d0           | ... in LFO4's group
8:  jmp     {SLOT_EXIT:#010x}
9:
"""


SHIMS = f"""
| param_set_slot_to_id, entered from {SLOT_HOOK:#010x}: the two loads it displaced,
| then types {NEW_TYPE}..{TYPES_LAST} -> {CLONE} (WaveTone), then back. d2 is saved at entry and
| overwritten before it is read ({SLOT_TO_ID + 0x16:#010x}).
slot_shim:
{_lfo4_slots()}    move.l  %sp@(12),%d0
    movea.l %sp@(16),%a1
    cmpi.l  #{NEW_TYPE},%d0
    blt.s   1f
    cmpi.l  #{TYPES_LAST},%d0
    bgt.s   1f
    moveq   #{CLONE},%d0
1:  jmp     {SLOT_RESUME:#010x}

| A one-argument per-machine UI accessor whose first two instructions were
| `moveq #4,%d1 ; move.l %sp@(4),%d0`, now `jsr` here: the same two loads, with
| types {NEW_TYPE}..{TYPES_LAST} read as {CLONE}. The jsr's return address sits on top, so the
| caller's argument is at 8. The accessor goes on to `cmp.l %d0,%d1`.
canon_arg:
    move.l  %sp@(8),%d0
    cmpi.l  #{NEW_TYPE},%d0
    blt.s   1f
    cmpi.l  #{TYPES_LAST},%d0
    bgt.s   1f
    moveq   #{CLONE},%d0
1:  moveq   #4,%d1
    rts

| The page accessor 0x400c2652(type, page): its `move.l %sp@(8),%d1 ; move.l
| %sp@(12),%d0` (after its own push of d2), now `jsr` here, with types {NEW_TYPE}..{TYPES_LAST}
| read as {CLONE}. d2 holds its bound 4 and is left alone; it compares next.
canon_page:
    move.l  %sp@(12),%d1
    move.l  %sp@(16),%d0
    cmpi.l  #{NEW_TYPE},%d1
    blt.s   1f
    cmpi.l  #{TYPES_LAST},%d1
    bgt.s   1f
    moveq   #{CLONE},%d1
1:  rts

| getMachineType(track) 0x4004b7f2, from its read of sound+0xDE: the UI's view of
| a track's machine. Types {NEW_TYPE}..{TYPES_LAST} are reported as {CLONE}, so the ~60 places the UI
| asks behave as they do for WaveTone. Back to its common exit.
canon_track:
    mvs.b   %a0@(222),%d0
    cmpi.l  #{NEW_TYPE},%d0
    blt.s   1f
    cmpi.l  #{TYPES_LAST},%d0
    bgt.s   1f
    moveq   #{CLONE},%d0
1:  jmp     {TRACK_TYPE_EXIT:#010x}

| The same question, answered with the machine the track really has: for the
| few callers that show or keep the identity (see IDENTITY_SITES). The body of
| 0x4004b7f2 as it stands in stock: the sound through vtable +40, or -1.
raw_track:
    move.l  %a2,%sp@-
    movea.l %sp@(8),%a2
    movea.l %a2@,%a0
    move.l  %a2,%sp@-
    movea.l %a0@(40),%a0
    jsr     %a0@
    addq.l  #4,%sp
    tst.l   %d0
    beq.s   1f
    movea.l %d0,%a0
    mvs.b   %a0@(222),%d0
    bra.s   2f
1:  moveq   #-1,%d0
2:  movea.l %sp@+,%a2
    rts

| v0.35: MACHINE SEL's LEFT / RIGHT (0x4005ba9c..0x4005babc) switches the column (+424),
| sets the cursor (+420) from the current type (+412 / +416, as if types were rows) and
| redraws (jsr 0x4011ca9a) without the scroll-follow 0x4005a956 that UP / DOWN run. Stock's
| lists fit the screen, so the top row (+428) was always 0; ours scrolls, so RIGHT from a
| machine low in the SRC list kept a top row past the FLTR list's end: an empty FLTR
| column (flupperich6l, v0.33). Here, from the redraw's jsr: the cursor on the first row
| whose type (0x4005b162(view): the row under the cursor, through the row object) is the
| column's current one, over the column's rows (0x4005a92c(view)); stock's cursor kept if
| none is; the follow; then the redraw. The YES paths share the site: a no-op there.
colsw:
    lea     %sp@(-20),%sp
    movem.l %d2-%d5/%a2,%sp@
    movea.l %sp@(24),%a2
    move.l  %a2@(420),%d5
    move.l  %a2@(424),%d0
    beq.s   3f
    moveq   #1,%d1
    cmp.l   %d0,%d1
    bne.s   5f
    move.l  %a2@(416),%d2
    bra.s   4f
3:  move.l  %a2@(412),%d2
4:  move.l  %a2,%sp@-
    jsr     0x4005a92c
    addq.l  #4,%sp
    move.l  %d0,%d4
    moveq   #0,%d3
1:  cmp.l   %d4,%d3
    bge.s   7f
    move.l  %d3,%a2@(420)
    move.l  %a2,%sp@-
    jsr     0x4005b162
    addq.l  #4,%sp
    cmp.l   %d0,%d2
    beq.s   5f
    addq.l  #1,%d3
    bra.s   1b
7:  move.l  %d5,%a2@(420)
5:  move.l  %a2,%sp@-
    jsr     0x4005a956
    addq.l  #4,%sp
    movem.l %sp@,%d2-%d5/%a2
    lea     %sp@(20),%sp
    jmp     0x4011ca9a
"""
SHIM_LABELS = ("slot_shim", "canon_arg", "canon_page", "canon_track", "raw_track", "colsw")

# -- 8. the sound's "is this parameter mine?" (vtable +0x50, 0x40036bfa) --------------------
# For a machine parameter it answers `sound+0xDE == record[param].page`. WaveTone's
# records are page 1, so a Waverider sound would disown its own machine parameters
# (the p-lock, LFO-destination and CC paths ask this). The read becomes a jsr to a
# shim that reads the type as WaveTone's and replays the push it displaced.
VALID_SITE = 0x40036C24                 # mvs.b %a0@(222),%d3 ; move.l %d2,-(%sp)
VALID_STOCK = bytes.fromhex("772800de2f02")
VALID_NEXT = bytes.fromhex("4eb9400dbe4c")   # jsr record page(param)
SHIMS2 = f"""
| from {VALID_SITE:#010x} by jsr: the type byte into d3, {NEW_TYPE}..{TYPES_LAST} read as {CLONE}, then
| the displaced `move.l %d2,-(%sp)` under the return address. a1 is free: the jsr
| that follows (0x400dbe4c) is a scratch-register call.
canon_valid:
    mvs.b   %a0@(222),%d3
    cmpi.l  #{NEW_TYPE},%d3
    blt.s   1f
    cmpi.l  #{TYPES_LAST},%d3
    bgt.s   1f
    moveq   #{CLONE},%d3
1:  movea.l %sp@+,%a1
    move.l  %d2,%sp@-
    jmp     %a1@
"""
SHIM2_LABELS = ("canon_valid",)

# -- 7. getMachineType(track): WaveTone for the UI, the real type for identity ----------
TRACK_TYPE_READ = 0x4004B816            # mvs.b %a0@(222),%d0 ; bra.s exit
TRACK_TYPE_READ_STOCK = bytes.fromhex("712800de6002")
TRACK_TYPE_FN = 0x4004B7F2
TRACK_TYPE_FN_STOCK = bytes.fromhex("2f0a246f00082052" "2f0a20680028" "4e90588f4a806714"
                                    "20522f0a20680028" "4e90588f2040712800de600270ff245f4e75")
# The callers that must see the real type, each an absolute reference to 0x4004b7f2
# (the pc-relative ones in 0x4004b822..0x4004dde0 cannot reach a cave, and are all
# behavioural: the permission test, the parameter reset, the list position).
IDENTITY_SITES = (
    (0x4005A4AC, "47f9", "MACHINE SEL: the current machine's marker (lea into a3)"),
    (0x40071912, "4eb9", "the track's machine name, drawn from the long-name table"),
    (0x4002DB2C, "4eb9", "re-commit of the track's own machine type (0x40031880)"),
    (0x400D5BD6, "4eb9", "the track state message: machine type byte"),
    (0x400D68C2, "4eb9", "an incoming machine type, compared with the track's before commit"),
    # v0.22: TRK + CLEAR (0x40071e80, "CLEAR TRK %d PRESET") re-initialises the sound as
    # the machine it reads here (0x4004d5f0 -> 0x400e7eb0: the type into +0xde, every slot's
    # record through param_set_slot_to_id, which reads ours as WaveTone's); canonical, a
    # cleared PERC, sample or RESONATOR track became WaveTone (the owner's v0.21 report)
    (0x40071EB6, "4eb9", "TRK + CLEAR: the machine the cleared preset is made for"),
)

# -- 7b. getMachineType(model, track) 0x4003134e: the real type -------------------------
# The model-level question -- "what machine does track t have?" -- is 0x4003134e,
# which finds the track and ends in a tail `jmp 0x4004b7f2`. A `jmp`, not a `jsr`,
# so the identity search above never saw it, and the answer came back canonical:
# a Waverider track read as WaveTone to every one of its twelve callers. Four of
# them are MACHINE SEL: the machine it marks and puts the cursor on (view +412,
# set at open, after every commit and on every model change). So YES on WAVERIDER
# wrote 5, and the view at once re-read 1 and marked WAVETONE; a second YES found
# 1 != 5 and committed 5 again; reopening marked WAVETONE (hardware, 2026-09-27;
# `out/fix-select/`, emulator). Three more re-commit the type they read: the track
# swap `0x40041bca`, and the two "restore the old machine" paths `0x400a80f6` /
# `0x400b174c` -- each would turn a Waverider track into a WaveTone one for real.
# The rest ask "is it MIDI?" (compare 4), or hand the type to the SYN overview and
# page accessors (0x400c25f2, 0x400c2652), which read 5 as WaveTone's rows already.
# So the tail jump goes to raw_track, and all twelve see 5.
MODEL_TRACK_TYPE_JMP = 0x40031394      # jmp 0x4004b7f2, the tail of 0x4003134e

# -- 6. the per-machine UI tables (0x42433ad4, 0x42433b24): the SYN pages ---------------
# `pages(type)`, `page(type, n)` and `overview(type)` read five-row tables built
# at boot and fall back to an empty page above 4 -- which is what a type-5 track's
# SYN page showed in the emulator before this. Type 5 reads WaveTone's rows.
CANON_ARG_SITES = (
    (0x400C25F2, "overview descriptor(type): 0x42433b24 + 44 type"),
)
# Milestone 7 (dnfw.waverider.pages): the page count and the page reader answer a
# Waverider track with its own two pages, and the SYN page's label fetch gives it
# its own labels. Everything else behaves as the M5 shims did.
COUNT_SITE = 0x400C2636                 # SYN page count(type): 0x42433ad4[type].count
LABEL_SITE = 0x40064622                 # the SYN page's jsr getShortName(this, id)
LABEL_STOCK = bytes.fromhex("4eb9400372da")
CANON_ARG_STOCK = bytes.fromhex("7204202f0004")
PAGE_SITE = 0x400C2656                  # 0x400c2652: after `move.l %d2,-(%sp) ; moveq #4,%d2`
PAGE_STOCK = bytes.fromhex("222f0008202f000c")
# the SYN page draw (0x40018118), after the grid of a type-1 page: page id 7 (WaveTone's
# OSC page) goes on to draw WaveTone's two oscillator icons at B and F from WAV1/TBL1
# and WAV2/TBL2. A Waverider track is type 1 to it: wr_icons takes the page id test.
ICON_SITE = 0x4001821E                  # moveq #7,%d0 ; cmp.l %d3,%d0 ; bne.w 0x400182c6
ICON_STOCK = bytes.fromhex("7007b083660000a2")
# the same draw, a type-1 page other than page id 9: push the canvas and the view, call
# the grid 0x40017428 (a pc-relative jsr), pop them. wr_grid draws Waverider's own page.
GRID_SITE = 0x40018214
GRID_STOCK = bytes.fromhex("2f022f0a4ebaf20e508f")
# the UI task's loop asks its screen `isDirty()` (0x4011d5d4, the byte at screen +32) once
# a pass, and redraws every view on it when set (0x4011d60a). The stock UI sets it on a
# change: at rest a shown page redraws once a second, and a modulation never redraws it
# (instrument, modview1). wr_poll asks the same question, first setting the byte through
# the stock 0x4011d5de while a modulation marker on Waverider's page would move.
# v0.14, the sample link (csrc/sampler, docs/sampler.md): the SysEx router's hook (the USB
# probe's site, docs/usbprobe.md). v0.14..v0.19 also hooked the frame builder (0x400276a2)
# to put packets in the frame's words 2650..2681; those are the DSP's per-track routing,
# so v0.20 leaves the frame builder stock (LINK_FEED_SITE is kept for the test that says so)
# 2026-11-11: the glass inverted while the test channel is armed (csrc/devtest/devtest.c, glass.S): the
# panel controller's 8-byte group sender and panel_diff, each entered by a jmp to C that replays stock's
GLASS_SEND_SITE = 0x40131F04            # lea -16(%sp),%sp ; movem.l %d2-%d4/%a2,(%sp)
GLASS_SEND_STOCK = bytes.fromhex("4feffff048d7041c")
PANEL_DIFF_SITE = 0x40131FD2            # lea -40(%sp),%sp ; movem.l %d2-%d6/%a2-%a4,(%sp)
PANEL_DIFF_STOCK = bytes.fromhex("4fefffd848d71c7c")
GLASS_WHOLE_SITE = 0x40131F54           # the whole-frame send dt_present calls (lea -28(%sp),%sp ; movem.l ...)
# 2026-11-12: the preset browser's ENGINE filter (csrc/presets, dnfw.waverider.engfilt; measured in stock 1.12)
ENG_TEST_SITE = 0x400AC9A8              # the preset list's rebuild: tst.b 1413(%a4) ; beq.s 0x400ac9ba (MIDI's test)
ENG_TEST_STOCK = bytes.fromhex("4a2c0585670c")
ENG_SORT_SITE = 0x400AD194              # the SORTING menu's builder after FILTER's row: pea 4 ; clr.l -56(%fp)
ENG_SORT_STOCK = bytes.fromhex("4878000442aeffc8")
ENG_CTOR_SITE = 0x400AC62C              # the view's constructor: move.b %d1,1412(%a2) ; move.b %d1,1413(%a2)
ENG_CTOR_STOCK = bytes.fromhex("1541058415410585")
# 2026-11-12: REMOTE CONTROL in USB CONFIG (csrc/devtest/usbcfg.c, usbcfg.S): UsbConfigMenuView::rebuild
# (0x40104f42), its three choices added, jmps to dt_usb_rebuild (a fourth item) before it puts the cursor back
USB_REBUILD_SITE = 0x40105220           # movea.l (%a2),%a0 ; clr.l -(%sp) ; move.l %d6,-(%sp)
USB_REBUILD_STOCK = bytes.fromhex("205242a72f06")
# 2026-11-12: LIVE SELECT's row in SETTINGS > PERSONALIZE (csrc/msel/live.c, live.S)
# 2026-11-12, the DSP load budget at note-on (csrc/load, docs/load-budget.md): the audio ISR's note-on call of the
# voice allocator (jsr 0x4002a6a2), its nine arguments pushed just before
LOAD_ALLOC_SITE = 0x400269E6
LOAD_ALLOC_STOCK = bytes.fromhex("4eb94002a6a2")
# 2026-11-16 (PARA as one voice, csrc/para/one.c): the ISR's key-up call of the allocator (type not 1), its nine
# arguments pushed just before (move.l %d3,-(%sp): the track), then lea 36(%sp),%sp
PV_REL_SITE = 0x40026D86
PV_REL_STOCK = bytes.fromhex("4eb94002a6a2")
LIVE_MENU_SITE = 0x400987A2             # PersonalizeMenuView's constructor ends: movem.l 24(%sp),%d2-%d6/%a2-%a6
LIVE_MENU_STOCK = bytes.fromhex("4cef7c7c0018")
LINK_RX_SITE = 0x4012197A               # lea 0x40207f9e,%a3: F0 00 20 3C, before the compare
LINK_RX_STOCK = bytes.fromhex("47f940207f9e")
LINK_FEED_SITE = 0x400276A2             # lea 0x40006c4a,%a2: the frame is built
LINK_FEED_STOCK = bytes.fromhex("45f940006c4a")
AMP_DRAW_SLOT = 0x401E2330               # 2026-11-18: stock's AMP page view's draw, in its vtable (+0x10)
AMP_DRAW_STOCK = 0x4006DFB6              # the eight knobs, the shape, then the level meter (vtable + 184)
KEY_SLOT = 0x401D4DB8                    # the parameter page view's key handler, in its vtable (v0.15)
KEY_STOCK = 0x40016480                   # stock's: code 2 cycles the pages, the rest to its base
QUANT_SITE = 0x40037BE6                  # the setter's write: movea.l %d0,%a0 ; move.w %d3,14(%a0,%d2.l*2)
QUANT_STOCK = bytes.fromhex("204031832a14")
MUTE_SITE, MUTE_STOCK = 0x400275B0, "4eb940134770"   # v0.52: the frame ISR, after its voice loop: jsr 0x40134770 (a copy)
FX_TYPE_SITE = 0x40037DF6                # the kit setter's store: movea.l %d0,%a0 ; move.w %d3,0(%a0,%d2.l*2) (the FX TYPE hook, 2026-11-11)
FX_TYPE_STOCK = bytes.fromhex("204031832a00")
LOCK_SND_SLOT, LOCK_SND_STOCK = 0x401DBC50, 0x40037CB6   # 2026-11-19: the sound ParameterSet's LOCK_SET (vtable 0x401dbc0c + 68)
LOCK_KIT_SLOT, LOCK_KIT_STOCK = 0x401DBCD8, 0x40037FAC   # ... and the kit's (vtable 0x401dbc94 + 68): knob notches on p-locks
TDM_SITE = 0x40026098                    # the SSI ISR, its transmit fill done: move.l %fp,%d2 ; addi.l #-72,%d2 (v0.16)
TDM_STOCK = bytes.fromhex("240e0682ffffffb8")
# stock's DSP link and USB passes with less work, the same bytes (csrc/stocklink, scratch/dup-study.md; 2026-11-18):
# (site, its stock bytes, our symbol, jsr instead of jmp, what); only with DN2_STOCK_LINK_FAST (pages.stock_link_fast_on).
# scripts/gate_overbridge.py allows these sites alone in Overbridge's path, each proved by scripts/check_stocklink.py
STOCKLINK_SITES = (
    (0x400CFA5A, "200ab5fc00000af0", "skl_fill", False, "the SPI frame's staging fill: a long an entry"),
    (0x400CF956, "4eb940134770", "skl_rcopy", True, "the reply copy: stock's memcpy in 32-byte blocks"),
    (0x40025F66, "202effc8720b", "skl_mode5", False, "mode 5's transmit-half clear: only what was written"),
    (0x40026080, "780be9a948780800", "skl_modex", False, "the other modes' transmit-half clear: only what was written"),
    (0x40025576, "203c40025e36", "skl_isr_install", True, "the audio interrupt installed: both halves cleared whole"),
    (0x400276B2, "49f94664c074", "skl_usbout", False, "mode 5's USB audio out: each channel read once"),
    (0x400279E8, "202effc8760b48780800", "skl_rxclr", False, "mode 6's receive-half clear (2 KB + 84 B): as movem"))
# stock's Overbridge streaming path with less work, the same bytes (csrc/obfast; 2026-11-18): only with DN2_OB_FAST
# (pages.ob_fast_on), apart from DN2_STOCK_LINK_FAST. (site, stock bytes, symbol, jsr, what, the bytes after the jsr:
# a bra.s to the loop's top); the overbridge and linkfast steps hold them as the stocklink sites
OBFAST_SITES = (
    (0x40003264, "2007ed88d0af002c", "obf_build_pair", False,
     "the mode-6 packet builder's sample loop (2026-11-21: the whole loop, entered at its top): two copies straight a "
     "sample", None),
    (0x40003492, "487800202f092f00", "obf_in32", True, "the Overbridge input's frame: one copy straight", "60e6"),
    (0x40003414, "4eb94013419c", "obf_clr", True, "the Overbridge input's transmit-half clear: as movem", None))


def site_bytes(stock_hex: str, target: int, call: bool, tail: str | None = None) -> bytes:
    """a declared site's new bytes: jsr/jmp to TARGET, then TAIL (default: nops over the displaced instructions)"""
    word = bytes.fromhex("4eb9" if call else "4ef9") + _long(target)
    rest = bytes.fromhex(tail) if tail is not None else b""
    return word + rest + bytes.fromhex("4e71") * ((len(stock_hex) // 2 - len(word) - len(rest)) // 2)


def declared_sites() -> list[tuple]:
    """every declared site in Overbridge's path, whatever the flags: (va, stock hex, symbol, call, what, tail)"""
    return [(*x, None) for x in STOCKLINK_SITES] + list(OBFAST_SITES)
# DIRECT JUMP (csrc/jump, docs/jump.md): the PTN view's single cue, the sequencer tick ISR's
# queue test, arming, switch and per-track positions, and the PTN view's key handler
JUMP_CUE_SITE = 0x400FA3A6               # jsr 0x400d9554: the PTN view's one-pattern cue (0x400fa2ea)
JUMP_CUE_STOCK = bytes.fromhex("4eb9400d9554")
JUMP_ISR_SITES = (                       # (site, stock bytes, its symbol, the instruction)
    (0x400DA56A, "123942c5b91e", "jmp_tick", "move.b 0x42c5b91e,%d1: the tick's queue test (tick 2)"),
    (0x400DA5BE, "737942c5bab4", "jmp_arm", "mvs.w 0x42c5bab4,%d1: the change-length test before arming"),
    (0x400DA84A, "43f942c5b9c4", "jmp_switch", "lea 0x42c5b9c4,%a1: the switch's start step"),
    (0x400DAA30, "4879401f6f35", "jmp_tracks", "pea 0x401f6f35: the per-track positions' end"),
)
JUMP_KEY_SLOT = 0x40200CDC               # the PTN view's key handler, in its vtable
JUMP_KEY_STOCK = 0x400FA88A
JUMP_GUARDS = (                          # what the shims jump back to and rely on
    (0x400DA570, "7c027b01bc85", "jmp_tick resumes: moveq #2,%d6 ; mvs.b %d1,%d5 ; cmp.l %d5,%d6"),
    (0x400DA57A, "227942c5bac0", "the queue's path: movea.l 0x42c5bac0,%a1"),
    (0x400DA5C4, "7e01", "jmp_arm's stock way resumes: moveq #1,%d7"),
    (0x400DA636, "23c042c5b9a4", "stock's arming: move.l %d0,0x42c5b9a4 (the next pattern)"),
    (0x400DA850, "4df942c5b9c8", "jmp_switch resumes: lea 0x42c5b9c8,%fp"),
    (0x400DA85C, "23d142c5b9bc", "... then 0x42c5b9bc = (a1): the start step"),
    (0x400DA92E, "1e350800", "the per-track positions read the mode from a5"),
    (0x400DA980, "264d", "... and the tracks from a5 (movea.l %a5,%a3)"),
    (0x400DAA68, "4bf942c5b9ea", "... until a5 is set again (lea 0x42c5b9ea,%a5)"),
    (0x400DAA36, "2f394028c73c", "jmp_tracks resumes: move.l 0x4028c73c,-(%sp)"),
    (0x400FA3AC, "4fef001c", "the cue's caller pops its arguments"),
    (0x400DAA66, "42024bf942c5b9ea", "v0.40: jmp_arm's forced tick ends as stock's ticks past 2 (clr.b %d2 ; lea 0x42c5b9ea,%a5)"),
    (0x400DA580, "42b942c5baac", "v0.40: stock's tick 2 clears the arming (why jmp_tick never takes tick 1)"),
    (0x400DA68E, "4a01660003d4", "v0.40: ... and its ticks past 2 go to 0x400daa66 (tst.b %d1 ; bne.w)"),
)
# v0.40, parameter slides' SLD/SLEN drawn as stock draws RTRG and LEN (csrc/slides/slide.c,
# sl_draw_sld / sl_draw_slen): the stock routines called, and the cell routine's and LEN
# widget's own calls whose arguments they copy
SLIDE_DRAW_GUARDS = (
    (0x40036560, "4fefffec48d7007c", "slides: the widget routine (id, value, ..., canvas, x, y)"),
    (0x400BC578, "4feffff4202f0014", "slides: RTRG's toggle widget (its sheet's frame value >> 8)"),
    (0x40115948, "4e56ff44", "slides: the cell's label text routine"),
    (0x40114b22, "4fefffd4", "slides: the fill / invert routine (the p-lock look)"),
    (0x4011614C, "206f0004", "slides: the box font's set-up"),
    (0x40115FC8, "206f0004", "slides: ... and its release"),
    (0x40114906, "4fefffd4", "slides: the box's rectangle"),
    (0x400CC432, "41f9402a14884879402941a4", "slides: LEN's box: its table and font 0x402941a4"),
    (0x400CC452, "2f0448794021a0e548780002486b0006486a00092f022f034eb94011573c",
     "slides: LEN's box text: centred (2) at (x + 9, y + 6)"),
    (0x40064630, "48794021a0e548794021757142a7487800012f0a486b0009487940291ca02f03",
     "slides: the cell's label: font 0x40291ca0 at (x + 9, y), 'XXXX' wide"),
)
# v0.22, the RECORDER as a screen of its own (csrc/sampler/rec.c): the UI loop's queue
# receive (every key and knob item passes it first), its draw of the screen (the recorder
# over it), and the main key handler's FUNC + VOICE (stock: unison on/off) opening it
UI_POP_SITE = 0x4002F17E                # jsr 0x40001928: the UI queue's receive, in the UI loop
UI_POP_STOCK = bytes.fromhex("4eb940001928")
SCREEN_SITE = 0x4002E4CA                # jsr 0x4011d60a(screen, canvas): the views drawn
SCREEN_STOCK = bytes.fromhex("4eb94011d60a")
# v0.45: the trig LEDs show recorder trigs while the BOUNCE REC panel is up (csrc/sampler/rec.c
# bn_led_walk): the LED compose's walk of the views (0x4002c854's jsr 0x4011d692(screen))
LED_SITE = 0x4002C880
LED_STOCK = bytes.fromhex("4eb94011d692")
REC_COMBO_SITE = 0x4005F008             # the VOICE case's FUNC branch: push, jsr 0x40046bfe (unison)
REC_COMBO_STOCK = bytes.fromhex("2f2a00a44eb940046bfe")
REC_COMBO_EXIT = 0x4005FC50             # the handler's common exit (the key offered to the base)
LFO_MASK_LEA = 0x40039570               # the LFO destination list's lea 0x400dc472,%a2 (v0.22)
LFO_MASK_STOCK = 0x400DC472
VCHECK_SITE = 0x40039904                # the parameter set's value check: link.w %fp,#-28 ; movem.l (4 regs),(%sp)
VCHECK_STOCK = bytes.fromhex("4e56ffe448d7")
# 2026-11-11, LFOs modulating the LFOs above them (csrc/modulation, docs/modulation-more.md):
# the frame's call of the LFO evaluator, and the evaluator's write of one LFO into its DEST cell
MOD_EVAL_SITE = 0x400272D4              # jsr 0x40137a06 (its seven arguments pushed before)
MOD_EVAL_STOCK = bytes.fromhex("4eb940137a06")
MOD_WB_SITE = 0x40137D7A                # movea.l 52(%sp),%a0 ; mvs.w 82(%a4),%d1
MOD_WB_STOCK = bytes.fromhex("206f0034736c0052")
SMOOTH_SITE = 0x400DB28E                # stock's parameter smoother: lea -28(%sp),%sp ; movem.l %d2-%d6/%a2-%a3,(%sp)
SMOOTH_STOCK = bytes.fromhex("4fefffe448d70c7c")
# 2026-11-18 (the User's CPU, claude/cpu-cuts): stock's smoother snap at a voice's note (101 state words = the targets
# << 16, 909 instructions a call, up to 16 in a frame) entered by a jmp into sm_snap (csrc/modulation/snap.S)
SNAP_SITE = 0x400DAFFC                  # move.l %d2,-(%sp) ; move.l #202,%d1 ; ... (the whole routine checked below)
SNAP_STOCK = bytes.fromhex("2f02223c000000ca202f0008206f000c4c0108004201d08006808000dea475701800224054815880"
                           "4842424222c20c81000000ca66e8241f4e75")
MODS_SITE = 0x400DB390                  # stock's MOD SETUP pass: lea -60(%sp),%sp ; movem.l %d2-%d7/%a2-%fp,(%sp)
MODS_STOCK = bytes.fromhex("4fefffc448d77cfc")
KB_REC_SITES = (0x40072D74, 0x40072DCA)    # v0.48: the RECORD key's jsr 0x40055cca (grid recording on?), both toggles
KB_REC_STOCK = bytes.fromhex("4eb940055cca")
KEYNOTES_SITE = 0x40058BE8              # v0.23: KeyboardView's jsr 0x40034460(kbd, &notes, key)
KEYNOTES_STOCK = bytes.fromhex("4eb940034460")
MACHSEL_COLSW_SITE = 0x4005BABE         # v0.35: MACHINE SEL's redraw after LEFT / RIGHT (jsr 0x4011ca9a)
MACHSEL_COLSW_STOCK = bytes.fromhex("4eb94011ca9a")
MACHSEL_COMMIT_SITE = 0x4005BBA0        # v0.30: MACHINE SEL's jsr 0x40031880 (commit(model, track, type, 1, 1))
MACHSEL_COMMIT_STOCK = bytes.fromhex("4eb940031880")
MODAPPLY_SITE = 0x40027196              # v0.25: the per-frame driver's jsr 0x400db390 (apply modulation)
MODAPPLY_STOCK = bytes.fromhex("4eb9400db390")
HOLD_NOTE_SITE = 0x40026AFC             # the ISR's note-on gate store (csrc/hold/hooks.S), 12 bytes
HOLD_NOTE_STOCK = "20020680000005cc278c0c00"   # move.l %d2,%d0 ; addi.l #1484,%d0 ; move.l %a4,(%a3,%d0.l*4)
HOLD_KEYS_SITE = 0x40026F6A             # lea 0x4002a3a6,%a2: the ISR's "a key is held on track t" (released if not)
HOLD_KEYS_STOCK = "45f94002a3a6"
HOLD_FINAL_SITE = 0x40027092            # jsr 0x4002b12e after the ISR's note-off word is composed (0x4002708e)
HOLD_FINAL_STOCK = "4eb94002b12e"
# 2026-11-15: PARA on the VOICE menu's knob B (csrc/para): VoiceMenuView's draw pushes place B's "---"
# (pea 0x402108e1, the empty place's label at x 43, y 27); vm_seen_hook pushes the same and marks the menu drawn
VMENU_B_SITE = 0x400285C0
VMENU_B_STOCK = "4879402108e1"
# 2026-11-19: PARA on the VOICE key's LED (csrc/para/led.c, docs/leds.md): MainScreenView's LED routine
# (0x40060842) asks 0x40029126(x, active track) "UNISON on?" before it lights VOICE (id 8) teal (2, 131);
# pu_voice_led answers in its place and lights VOICE magenta (2, 91) itself on a PARA ON track
VOICE_LED_SITE = 0x40060D6E
VOICE_LED_STOCK = "4eb940029126"
# 2026-11-11 (lzma-dsp, docs/lzma7.md): the SHARC uploader's (0x400cf4b0) depack of section 7:
# `jsr 0x40136820` (aPLib depack(src, dst)) -> dn_depack7 (csrc/waverider/lzma7.c), same arguments
DEPACK7_SITE = 0x400CF73A
DEPACK7_STOCK = "4eb940136820"
# 2026-11-11 (lzma-cache, csrc/waverider/lzma7cache.c): the boot routine uploads the DSP program
# (jsr 0x400cf4b0) before it sets up the eMMC driver; the call moves to where its paths meet after
UPLOAD_EARLY_SITE = 0x400CF086
UPLOAD_EARLY_STOCK = "4eb9400cf4b0"
UPLOAD_LATE_SITE = 0x400CF0F2           # move.l %d0,0x4243989c: the driver's set-up result
UPLOAD_LATE_STOCK = "23c04243989c"
LFO_APPLY_SITE = 0x400272D4             # v0.65: the per-frame driver's jsr 0x40137a06 (the LFOs)
LFO_APPLY_STOCK = bytes.fromhex("4eb940137a06")
POLL_SITE = 0x4002E464                  # jsr 0x4011d5d4 (isDirty), its argument the screen
# v0.38: per-project pools (csrc/sampler/pools.c, hooks.S, docs/project-pools.md): the OS's
# project LOAD 0x40042E6E (its entry, its success where it sets the slot, its exit) and NEW
# 0x400428C0 (where it sets the slot), each a jmp to a cave that replays what it replaced
PJ_BEGIN_SITE = 0x40042E6E              # lea -36(%sp),%sp ; movem.l %d2-%d5/%a2,(%sp)
PJ_BEGIN_STOCK = bytes.fromhex("4fefffdc48d7043c")
PJ_LOADED_SITE = 0x40042ED2             # move.l %d5,-(%sp) ; move.l %d3,-(%sp) ; jsr 0x4003eb62
PJ_LOADED_STOCK = bytes.fromhex("2f052f034ebabc8a")
PJ_END_SITE = 0x40042EE6                # move.b %d4,%d0 ; movem.l (%sp),%d2-%d5/%a2 ; lea 36(%sp),%sp
PJ_END_STOCK = bytes.fromhex("10044cd7043c4fef0024")
PJ_NEW_SITE = 0x40042AF0                # move.l 12(%fp),(%sp) ; move.l %a2,-(%sp) ; jsr 0x4003eb62
PJ_NEW_STOCK = bytes.fromhex("2eae000c2f0a4ebac06a")
# 2026-11-10: the inserts saved with the project (csrc/inserts/store.c): stock's write of a project slot
# 0x40040190(project, slot, cb) (SAVE, SAVE AS, and the temp slot 128 at LOAD, NEW and autosave)
PJ_WRITE_SITE = 0x40040190              # lea -52(%sp),%sp ; movem.l %d2-%d4/%a2-%fp,(%sp)
PJ_WRITE_STOCK = bytes.fromhex("4fefffcc48d77c1c")
POLL_STOCK = bytes.fromhex("4eb94011d5d4")
# the system meter (csrc/meter/hooks.S, docs/meter.md): the ColdFire's load from the idle
# task's parked time (usbprobe's method, docs/usbprobe.md): the context switch and the audio
# ISR's frame count, each one whole 6-byte instruction replayed by the routine it calls. The
# ISR's start is taken in the link's existing hook (TDM_SITE): its code from 0x40025e36 up to
# there is Overbridge's path and stays stock's (gate_overbridge.py; v0.41).
# OS 1.12: the sites are 1.11's unchanged; FRAMES (the ISR_OUT operand) is BSS, +0x1000
METER_SITES = (
    (0x40000438, "203cffffdfff", "mtr_switch", "the context switch, interrupts masked: move.l #0xffffdfff,%d0"),
    (0x40027B82, "52b94058f8d4", "mtr_isr_out", "the audio ISR's frame count before its rte: addq.l #1,0x4058f8d4"),
)
# No screen intro (2026-11-10, the User: "just drop it completely (the one screen one)"; LED animations
# stay). The start-up code computes the intro's skip flag here (tst.l %d0 ; sne %d0 ; mvs.b %d0,%d0 ;
# neg.l %d0: normally bit 5 of the start-up flags 0x40287a60, read at 0x400cedc6), pushes it and calls
# the intro starter 0x400d3920. With the flag forced to 1 the starter takes Elektron's own skip
# branch: it posts the intro-done semaphore 0x42c4261c and never creates the intro task (entry
# 0x400d3eea, prio 7); the main application task, which waits on that semaphore at 0x4002ed50,
# starts at once. OS 1.12 addresses (measured on stock 1.12 and on the v0.46 build).
NOINTRO_SITE = 0x400CF11C
NOINTRO_STOCK = bytes.fromhex("4a8056c071004480")
NOINTRO_NEW = bytes.fromhex("70014e714e714e71")      # moveq #1,%d0 ; nop ; nop ; nop
NOINTRO_GUARDS = (                       # read, never written
    (0x400CF124, "2f004eb9400d3920", "no intro: the flag is pushed and the intro starter 0x400d3920 called"),
    (0x400D3946, "4a026714203c42c4261c", "no intro: the starter's skip branch (flag set): the intro-done semaphore 0x42c4261c posted"),
)
# the per-track inserts (csrc/inserts/hooks.S, docs/inserts.md): stock's mode header 0x40063f56
# ends here; its first three exit instructions (6 bytes, also its one-page bge's target) jsr to
# ins_hdr_tail, which renames a bare "FX" (the one-page track FX mode) "FX (1/2)" / "FX (2/2)" and
# replays them
INS_HDR_SITE = 0x40063FCC               # move.l %a3,%d0 ; movea.l (%sp)+,%a2 ; movea.l (%sp)+,%a3
INS_HDR_STOCK = bytes.fromhex("200b245f265f")
INS_HDR_GUARDS = (
    (0x40063F84, "202a0080720790aa007cb280", "inserts: the header's page count (end - begin) against 7"),
    (0x40063F90, "6c3a", "inserts: ... one page: straight to the exit (bge)"),
    (0x40063FD2, "588f4e75", "inserts: the exit's last two (addq.l #4,%sp ; rts), left as stock"),
)
METER_GUARDS = (                         # read, never written: what the hooks rely on
    (0x40000410, "46fc2700", "meter: the switch masks interrupts"),
    (0x40000452, "4ce8ffff000c4e73", "meter: ... and reloads every register from the incoming TCB"),
    (0x40025E36, "4e56ff1448d73fff", "meter: the audio ISR's register save"),
    (0x40027BBE, "4cee3fffff144e5e4e73", "meter: ... and its only rte"),
    (0x400CF246, "60fe", "meter: the idle task's spin (IDLE_PC, 1.11 0x400cf0e2)"),
    (0x400CF24E, "4eb94002e8d0", "meter: ... in its loop (digihealth's 1.12 site)"),
    (0x40001608, "2f0a2f02246f000c", "meter: the mutex take the heap walk calls"),
    (0x4000172A, "2f0a2f02246f000c", "meter: ... and the give"),
    (0x4012014A, "4879445e2e404eb940001608", "meter: the allocator locks the heap mutex 0x445e2e40"),
)


def _cave_free(content: bytes, cave: tuple[int, int]) -> None:
    at, cap = cave
    if any(_read(content, at - 4, cap + 8)):
        raise ComposeError(f"the cave at {at:#010x} (+{cap}) is not free")


_NUMBER_TYPES = {"unsigned char": 1, "signed char": 1, "char": 1, "unsigned short": 2, "short": 2,
                 "unsigned int": 4, "int": 4}


def _number_tables(header: str, syms: dict) -> list[list[int]]:
    """[[start, end]]: every `static const <integer type> NAME[N]` of HEADER that the link kept, by its symbol"""
    import re                                                    # noqa: PLC0415
    out = []
    for typ, name, n in re.findall(r"static const ((?:unsigned |signed )?(?:char|short|int)) (\w+)\[(\d+)\]", header):
        if name in syms:
            out.append([syms[name], syms[name] + _NUMBER_TYPES[typ] * int(n)])
    return sorted(out)


def compose(stock: bytes, assemble, compile_c) -> dict:
    from . import msel as _msel                  # 2026-11-11: MACHINE SEL in two columns (csrc/msel)
    from . import engfilt as _eng                # 2026-11-12: the preset browser's ENGINE filter (csrc/presets)
    """-> {"content", "edits", "layout", "chunk"}. ASSEMBLE(source, base=...) -> bytes;
    COMPILE_C(header, base=...) -> (image, symbols, bss): csrc/waverider/page.c linked at
    BASE with `header` as its generated `wr_gen.h`."""
    content = bytearray(stock)
    for va, want, why in GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    edits: list[Edit] = []

    # Milestone 7: Waverider's pages, as one platform CODE chunk in RAM (pages.LOAD)
    # the C page renderer first (the assembly calls it), at C_LOAD
    from .. import slides as SL
    from .. import modversion                   # v0.39: the mod's version (VERSION), shown at the browser's top
    from . import tunings as TU                 # v0.61: the factory tunings
    from ..engines.analog2.filters import pages as flt_pages        # 2026-11-10: the A2 filter machines' FLTR names
    from .. import load as _load                  # 2026-11-12: the DSP load budget's cost table (csrc/load)
    from . import ampsw as _da                    # 2026-11-20: AMP ON/OFF for the drum machines (csrc/msel/ampsw.c)
    c_hdr = (pages.c_header() + _msel.c_header() + _da.c_header() + _eng.c_header() + _load.c_header() + flt_pages.c_header()
             + SL.c_header(stock) + TU.c_header() + modversion.c_define())
    built_c = compile_c(c_hdr, base=pages.C_LOAD)
    cimage, csyms, cbss = built_c[:3]
    c_abs32 = built_c[3] if len(built_c) > 3 else ()        # 2026-11-18: the link's initialised pointers
    if cbss:
        raise ComposeError(f"the page renderer has {cbss} bytes of BSS; nothing zeroes it")
    if len(cimage) > pages.C_SPAN:
        raise ComposeError(f"the page renderer ({len(cimage)} B) is larger than its {pages.C_SPAN:#x}")
    ptable = "\n    .align 2\n" + "\n".join(f"    .long {n}" for n in pages.LABELS_OUT) + "\n"
    pblob = assemble(pages.source(csyms["wr_page_draw"], csyms["wr_cell"], csyms["mxp_placed"]) + ptable,
                     base=pages.LOAD)
    asm = pblob[:-4 * len(pages.LABELS_OUT)]
    if pages.LOAD + len(asm) > PAGES_END:
        raise ComposeError(f"the pages assembly ({len(asm)} B) runs past {PAGES_END:#010x}")
    chunk = asm
    playout = dict(zip(pages.LABELS_OUT, struct.unpack(f">{len(pages.LABELS_OUT)}I",
                                                       pblob[-4 * len(pages.LABELS_OUT):])))

    def edit(va: int, new: bytes, what: str, stock_bytes: bytes | None = None) -> None:
        old = _read(content, va, len(new)) if stock_bytes is None else stock_bytes
        _need(content, va, old, what)
        content[va - BASE:va - BASE + len(new)] = new
        edits.append(Edit(va, old, new, what))

    # the machines chunk (RAM, MCHUNK): the shims, the names, the name table, the
    # attribute rows, the list -- what W5 kept in three caves, for two machines now
    _need(content, LIST_STOCK_VA, b"".join(_long(t) for t in LIST_STOCK), "the MACHINE SEL list")
    names_rows = _read(content, NAMES_STOCK_VA, NAME_ROW * 5)
    attr_rows = _read(content, ATTR_STOCK_VA, ATTR_ROW * 5)
    strings = "\n".join(f'name_long_{t}:\n    .asciz "{MACHINE_NAMES[t][0]}"\n'
                        f'name_short_{t}:\n    .asciz "{MACHINE_NAMES[t][1]}"' for t in NEW_TYPES)
    labels = SHIM_LABELS + SHIM2_LABELS + tuple(f"name_{c}_{t}" for t in NEW_TYPES
                                                for c in ("long", "short")) + ("mdata",)
    table = "\n    .align 2\n" + "\n".join(f"    .long {n}" for n in labels) + "\n"
    src = SHIMS + SHIMS2 + "\n" + strings + "\n    .align 2\nmdata:\n" + table
    blob = assemble(src, base=MCHUNK)
    head = blob[:-4 * len(labels)]
    layout = dict(zip(labels, struct.unpack(f">{len(labels)}I", blob[-4 * len(labels):])))
    if layout["mdata"] != MCHUNK + len(head):
        raise ComposeError("the machines chunk's data does not follow its code")
    layout["long_name"], layout["short_name"] = layout["name_long_5"], layout["name_short_5"]
    rows = bytearray(names_rows)
    for t in NEW_TYPES:
        rows += _long(layout[f"name_long_{t}"]) + _long(layout[f"name_short_{t}"]) + _long(0)
    n_rows = 5 + len(NEW_TYPES)
    layout["names"] = layout["mdata"]
    layout["attributes"] = layout["names"] + NAME_ROW * n_rows
    layout["list"] = layout["attributes"] + ATTR_ROW * n_rows
    clone_attr = attr_rows[ATTR_ROW * CLONE:ATTR_ROW * (CLONE + 1)]
    mchunk = (head + bytes(rows) + attr_rows + clone_attr * len(NEW_TYPES)
              + b"".join(_long(t) for t in LIST_NEW))
    if MCHUNK + len(mchunk) > MCHUNK_END:
        raise ComposeError(f"the machines chunk ends past {MCHUNK_END:#010x}")
    layout["mchunk_code_end"] = layout["mdata"]
    top = TYPES_LAST                            # the highest type with a row
    if NEW_TYPES != tuple(range(NEW_TYPE, top + 1)):
        raise ComposeError("the new types must be one run from 5: each has a row")

    # 1. the list: its length is LIST_NEW's, so a seventh machine is one entry there
    n = len(LIST_NEW)
    edit(LIST_ALLOC, bytes.fromhex("4878") + struct.pack(">H", 4 * n),
         f"MACHINE SEL list: storage for {n} longs", bytes.fromhex("48780014"))
    edit(LIST_END, bytes.fromhex("4879") + _long(layout["list"] + 4 * n),
         "MACHINE SEL list: the copy's end", bytes.fromhex("4879") + _long(LIST_STOCK_VA + 20))
    edit(LIST_CAP, bytes.fromhex("41e8") + struct.pack(">H", 4 * n),
         f"MACHINE SEL list: the vector's capacity, {n} longs", bytes.fromhex("41e80014"))
    edit(LIST_BEGIN, bytes.fromhex("4879") + _long(layout["list"]),
         "MACHINE SEL list: the copy's start", bytes.fromhex("4879") + _long(LIST_STOCK_VA))
    edit(GROUP_FN, group_function(assemble), f"the MACHINE SEL group: our synth machines ({SAMPLE_GROUP}) "
         f"and the sample machines ({SAMPLER_GROUP}) are sections of their own, divided off like MIDI",
         GROUP_STOCK)

    # 2. the names
    for bound, base, op, col in NAME_SITES:
        edit(bound, bytes([0x72, top]), f"name column {col // 4}: bound 4 -> {top}",
             bytes.fromhex("7204"))
        edit(base + 2, _long(layout["names"] + col),
             f"name column {col // 4}: the {n_rows}-row table", _long(NAMES_STOCK_VA + col))
        _need(content, base, bytes.fromhex(op), "the name accessor's base instruction")

    # 3. the attribute rows
    for bound in ATTR_BOUNDS:
        edit(bound, bytes([0x74 if bound == 0x400DC300 else 0x72, top]),
             f"attribute rows: bound 4 -> {top}",
             bytes.fromhex("7404" if bound == 0x400DC300 else "7204"))
    for site, col in ATTR_BASES:
        _need(content, site, bytes.fromhex("41f9"), "the attribute accessor's lea")
        edit(site + 2, _long(layout["attributes"] + col), f"attribute rows: the {n_rows}-row copy",
             _long(ATTR_STOCK_VA + col))

    # 5. the stored-sound LOAD keeps type 5 (stock turns it into FM Tone): the wishes record's load stub
    # replays the bound as `moveq #top + 2,%d2` (csrc/wishes/hooks.S, WR_LOAD_BOUND), below
    if top + 2 > 127:
        raise ComposeError(f"the LOAD bound {top + 2} does not fit a moveq")

    # 4. slot_to_id
    edit(SLOT_HOOK, bytes.fromhex("4ef9") + _long(layout["slot_shim"]) + bytes.fromhex("4e71"),
         "param_set_slot_to_id: detour to the shim", SLOT_HOOK_STOCK)
    if pages.lfo4_on():                 # DN2_LFO4: LFO4's controls as LFO1..3's destinations (cascade.c)
        edit(BUILDER_BOUND, bytes.fromhex("726d"), "the destination builder walks LFO4's slots 101..108 too "
             "(DN2_LFO4)", BUILDER_BOUND_STOCK)
        edit(BUILDER_RESERVE, bytes.fromhex("006d"), "... its list's room 101 -> 109 (DN2_LFO4)", BUILDER_RESERVE_STOCK)
        edit(EVAL_DEST_BOUND, bytes.fromhex("726c"), "the evaluator writes a DEST up to 108: LFO4's controls, which "
             "mod_wb sends to the cascade's cells (DN2_LFO4)", EVAL_DEST_BOUND_STOCK)

    # 6. the SYN page tables
    for site, what in CANON_ARG_SITES:
        edit(site, bytes.fromhex("4eb9") + _long(layout["canon_arg"]),
             f"{what}: type 5 reads WaveTone's row", CANON_ARG_STOCK)
    edit(COUNT_SITE, bytes.fromhex("4eb9") + _long(playout["wr_count"]),
         "SYN page count(type): 2 for a Waverider track (M7); otherwise type 5 reads WaveTone's",
         CANON_ARG_STOCK)
    edit(PAGE_SITE, bytes.fromhex("4eb9") + _long(playout["wr_page"]) + bytes.fromhex("4e71"),
         "SYN page(type, n): Waverider's own pages for a Waverider track (M7); otherwise "
         "type 5 reads WaveTone's", PAGE_STOCK)
    edit(LABEL_SITE, bytes.fromhex("4eb9") + _long(playout["wr_label"]),
         "the SYN page's label fetch: Waverider's labels for a Waverider track (M7)", LABEL_STOCK)
    edit(GRID_SITE, bytes.fromhex("4eb9") + _long(playout["wr_grid"]) + bytes.fromhex("4e714e71"),
         "the SYN page draw: Waverider's own page for a Waverider track (M8.1)", GRID_STOCK)
    edit(pages.CELL_EXIT, bytes.fromhex("4ef9") + _long(playout["wr_cell_tail"]) + bytes.fromhex("4e714e71"),
         "a stock page cell's widget (0x4006448a): its exit through wr_cell_tail, which draws "
         "parameter slides' marks (v0.45: no longer PING's TYPE)", bytes.fromhex(pages.CELL_EXIT_STOCK))
    edit(pages.PLACE_EXIT, bytes.fromhex("4ef9") + _long(playout["wr_place_tail"]) + bytes.fromhex("4e714e71"),
         "a stock page's place drawer (0x400169de): its exit through wr_place_tail, which tells the routes popup "
         "each knob's parameter, FM TONE's own places included (2026-11-20)", bytes.fromhex(pages.PLACE_EXIT_STOCK))
    edit(pages.ID9_SITE, bytes.fromhex("4eb9") + _long(playout["wr_id9"]),
         "the SYN page draw: a CZ track's third page (id 9 to the draw) to wr_grid, not "
         "WaveTone's page-3 grid", bytes.fromhex(pages.ID9_STOCK))
    edit(ICON_SITE, bytes.fromhex("4eb9") + _long(playout["wr_icons"]) + bytes.fromhex("4e71"),
         "the SYN page draw: no WaveTone oscillator icons on a Waverider track (M7)", ICON_STOCK)
    _need(content, PAGE_SITE - 4, bytes.fromhex("2f027404"), "0x400c2652's push of d2 and its bound")
    _need(content, POLL_SITE - 2, bytes.fromhex("2f0a"), "the UI loop pushes the screen")
    _need(content, POLL_SITE + 6, bytes.fromhex("588f4a00"), "... and tests the answer's low byte")
    # 2026-11-10: DRONE's HOLD latch (csrc/hold): the note-on's gate length, the key-release test
    edit(HOLD_NOTE_SITE, bytes.fromhex("4eb9") + _long(csyms["hold_note_hook"]) + bytes.fromhex("4e714e714e71"),
         "DRONE's HOLD: a note's gate length through hold_len", bytes.fromhex(HOLD_NOTE_STOCK))
    edit(HOLD_KEYS_SITE, bytes.fromhex("45f9") + _long(csyms["hold_keys"]),
         "DRONE's HOLD: a latched track's keys count as held", bytes.fromhex(HOLD_KEYS_STOCK))
    edit(HOLD_FINAL_SITE, bytes.fromhex("4eb9") + _long(csyms["hold_final_hook"]),
         "DRONE's HOLD: the frame's note-off word without the latched voices", bytes.fromhex(HOLD_FINAL_STOCK))
    _need(content, VMENU_B_SITE + 6, bytes.fromhex("42a7"), "VoiceMenuView: clr.l -(sp) after B's label push")
    edit(VMENU_B_SITE, bytes.fromhex("4eb9") + _long(csyms["vm_seen_hook"]),
         "PARA on the VOICE menu's B: the menu seen as it pushes B's \"---\"", bytes.fromhex(VMENU_B_STOCK))
    _need(content, VOICE_LED_SITE - 6, bytes.fromhex("2f2effbc2f00"),
          "MainScreenView's LED routine pushes the active track, then the voice setup")
    _need(content, VOICE_LED_SITE + 6, bytes.fromhex("4fef000c4a006742487800834878000248780008"),
          "... tests the answer as a byte, then lights VOICE (id 8) teal (mode 2, palette 131)")
    edit(VOICE_LED_SITE, bytes.fromhex("4eb9") + _long(csyms["pu_voice_led"]),
         "PARA on the VOICE key's LED: pu_voice_led lights VOICE magenta on a PARA ON track, else stock's UNISON "
         "test", bytes.fromhex(VOICE_LED_STOCK))
    edit(POLL_SITE, bytes.fromhex("4eb9") + _long(csyms["wr_poll"]),
         "the UI loop's redraw test: wr_poll asks for a redraw while a modulation marker on "
         "Waverider's page would move, then answers as stock", POLL_STOCK)

    # 2026-11-11: section 7 as LZMA (docs/lzma7.md): the uploader's depack call to dn_depack7
    _need(content, DEPACK7_SITE - 8, bytes.fromhex("10fc00032f082f04"),
          "the uploader writes the 0x03 byte, then pushes dst and src")
    _need(content, DEPACK7_SITE + 6, bytes.fromhex("4fef001424005282"),
          "... and takes the answer + 1 as the length to push")
    edit(DEPACK7_SITE, bytes.fromhex("4eb9") + _long(csyms["dn_depack7"]),
         "the SHARC uploader's depack of section 7: dn_depack7 decodes our LZMA section 7 "
         "(checked by length and CRC-32; anything else refused into stock's error path) and "
         "hands stock's aPLib to 0x40136820", bytes.fromhex(DEPACK7_STOCK))
    # 2026-11-11 (lzma-cache): the upload moved after the eMMC's set-up, so dn_depack7 can read
    # and write its copy on the +Drive (csrc/waverider/lzma7cache.c, lzma7late.S)
    _need(content, UPLOAD_EARLY_SITE + 6, bytes.fromhex("4eb940027d3a"), "the boot routine goes on after the upload")
    _need(content, 0x400CF09A, bytes.fromhex("4eb94012bddc"), "the eMMC driver's set-up comes after it ...")
    _need(content, 0x400CF0A8, bytes.fromhex("4eb94012be52" "4eb94012c438" "4eb94012c620"), "... in three calls")
    _need(content, UPLOAD_LATE_SITE - 2, bytes.fromhex("7007"), "the last path falls into the meeting point")
    _need(content, UPLOAD_LATE_SITE + 6, bytes.fromhex("7040"), "... and stock writes d0 after the replayed store")
    edit(UPLOAD_EARLY_SITE, bytes.fromhex("4e714e714e71"),
         "the boot routine's DSP upload, before the eMMC is set up: moved to 0x400cf0f2",
         bytes.fromhex(UPLOAD_EARLY_STOCK))
    edit(UPLOAD_LATE_SITE, bytes.fromhex("4eb9") + _long(csyms["dn7_late"]),
         "where the boot routine's paths meet after the eMMC's set-up: the store replayed, then "
         "the DSP upload (dn_depack7 reads the +Drive's copy of the program, or decodes and writes it)",
         bytes.fromhex(UPLOAD_LATE_STOCK))

    # v0.22: the RECORDER's screen -- its keys and knobs, its draw, FUNC + VOICE
    _need(content, UI_POP_SITE - 6, bytes.fromhex("48794059e214"), "the UI loop pushes its queue")
    _need(content, UI_POP_SITE + 6, bytes.fromhex("588f72292440"), "... then takes the item: moveq #41 ; movea d0,a2")
    edit(UI_POP_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_ui_pop"]),
         "the UI loop's queue receive: smp_ui_pop takes the recorder's keys and knobs while "
         "it is up, and the sample list's UP/DOWN; everything else as stock", UI_POP_STOCK)
    _need(content, SCREEN_SITE - 4, bytes.fromhex("2f0b2f0a"), "the UI loop pushes canvas, screen")
    edit(SCREEN_SITE, bytes.fromhex("4eb9") + _long(csyms["wr_screen"]),
         "the UI loop's draw of its screen: stock's, then the RECORDER over it while it is up",
         SCREEN_STOCK)
    edit(LED_SITE, bytes.fromhex("4eb9") + _long(csyms["bn_led_walk"]),
         "the LED compose's walk of the views: bn_led_walk claims the 16 trig LEDs for the "
         "page's recorder trigs while the BOUNCE REC panel is up, then stock's walk", LED_STOCK)
    _need(content, REC_COMBO_SITE - 4, bytes.fromhex("60000ff4"), "the VOICE case without FUNC ends just before")
    _need(content, REC_COMBO_EXIT, bytes.fromhex("2f022f0a4eb94011c954"), "the key handler's common exit")
    disp = REC_COMBO_EXIT - (REC_COMBO_SITE + 8)
    edit(REC_COMBO_SITE, bytes.fromhex("4eb9") + _long(csyms["rec_combo"]) + bytes.fromhex("6000")
         + disp.to_bytes(2, "big"),
         "FUNC + VOICE: the RECORDER opens or closes (stock: unison on/off; VOICE alone "
         "still opens its menu)", REC_COMBO_STOCK)

    # v0.23: SLICES: in KEYBOARD mode a SLICE track (SLCE NOTE) plays slice k on trig k
    _need(content, KEYNOTES_SITE - 8, bytes.fromhex("2f04486effd42f00"), "the KeyboardView pushes key, &notes, view")
    edit(KEYNOTES_SITE, bytes.fromhex("4eb9") + _long(csyms["slc_keynotes"]),
         "a trig key's notes in KEYBOARD mode: on a SLICE track (SLCE NOTE) slice k, else stock's",
         KEYNOTES_STOCK)

    # v0.48 (owner): KEYBOARD mode survives grid recording. Stock keeps KEYBOARD's state when
    # RECORD turns grid recording on and gives it back only when a held RECORD is let go; a
    # second press turned grid recording off and left KEYBOARD off (seen in the emulator).
    # kb_rec_hook (sampler/hooks.S) asks the same question and gives KEYBOARD back as stock's
    # release path does.
    for site in KB_REC_SITES:
        _need(content, site - 4, bytes.fromhex("2f2a006c"), "the RECORD key's handler pushes its recorder")
        _need(content, site + 6, bytes.fromhex("4fef00104a00"), "the handler pops three arguments and tests the answer")
        edit(site, bytes.fromhex("4eb9") + _long(csyms["kb_rec_hook"]),
             "RECORD's toggle: grid recording off gives KEYBOARD back (v0.48)", KB_REC_STOCK)

    # v0.30: MACHINE SEL from one sample machine to another keeps SAMP (owner's request: the
    # commit resets the sound to the machine's defaults, SAMP to OFF; measured in the emulator)
    edit(MACHSEL_COLSW_SITE, bytes.fromhex("4eb9") + _long(layout["colsw"]),
         "MACHINE SEL LEFT / RIGHT: the cursor on the column's current machine, the scroll "
         "following it (v0.35: an empty FLTR column after RIGHT from a machine low in the list)",
         MACHSEL_COLSW_STOCK)
    edit(MACHSEL_COMMIT_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_machine_commit"]),
         "MACHINE SEL's commit: between two sample machines SAMP is kept (rec.c)", MACHSEL_COMMIT_STOCK)

    # v0.25: modulation on SAMP steps through the loaded samples (link.c, smp_mod_apply)
    _need(content, MODAPPLY_SITE - 4, bytes.fromhex("2f002440"), "the driver pushes the mirror (move.l %d0,-(sp); movea.l %d0,%a2)")
    edit(MODAPPLY_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_mod_apply"]),
         "the per-frame modulation apply: stock's 0x400db390, then a sample machine's modulated SAMP "
         "moved through the loaded slots", MODAPPLY_STOCK)

    # v0.65 (docs/banks.md): after the LFOs, each sample voice's SAMP keeps its bank. Upstream edits
    # LFO_APPLY_SITE to smp_lfo_hook; in ours that site is MOD_EVAL_SITE (mod_eval, below), which calls
    # smp_lfo_fix after the evaluator and the matrix's routes (csrc/modulation/hooks.S, v0.65.1)
    assert LFO_APPLY_SITE == MOD_EVAL_SITE

    # v0.22: the LFOs' destination list leaves out the WaveTone records our machines do not use;
    # 2026-11-11: it offers the 13 closed records (page.c), and each LFO the other LFOs' controls
    # (csrc/modulation/cascade.c, through hooks.S's mod_mask_hook, which reads the builder's want)
    _need(content, LFO_MASK_LEA, bytes.fromhex("45f9400dc472"), "the destination list: lea 0x400dc472,%a2")
    _need(content, LFO_MASK_LEA + 0x30, bytes.fromhex("4e92"), "... called once a slot (jsr %a2@)")
    _need(content, LFO_MASK_LEA + 0x2e, bytes.fromhex("2f004e924680c0af0038"),
          "... with the record pushed, want at 56(%sp) (move.l %d0,-(%sp) ; jsr (%a2) ; not.l %d0 ; and.l 56(%sp),%d0)")
    _need(content, 0x4003951E, bytes.fromhex("4fefffd448d77c7c2a6f0030"),
          "the builder's frame: lea -44(%sp),%sp ; movem.l (10 registers) ; movea.l 48(%sp),%a5")
    # 2026-11-18 (the User: "editing destination in modulation page is cpu"): stock's value check of a record, at its
    # entry: an LFO's DEST checked with one lookup and the list's mask, not a whole list built and sorted (dest_pop.c
    # ldp_valid); every other record through stock's 0x40036bac, as stock
    _need(content, VCHECK_SITE + 6, bytes.fromhex("0c0c242e000c47f9400dc472"), "the value check's body, as ldp_valid reads it")
    edit(VCHECK_SITE, bytes.fromhex("4ef9") + _long(csyms["ldp_valid"]),
         "the record value check: an LFO's DEST by one lookup and the list's mask (ldp_valid), no list built",
         VCHECK_STOCK)
    edit(LFO_MASK_LEA + 2, _long(csyms["mod_mask_hook"]),
         "the LFO destination list's mask lookup: mod_lfo_mask(record, want): 0 for a record our "
         "machine leaves unused (named -), 0x1e00 for the 13 closed ones, another LFO's control "
         "offered to every LFO, stock's 0x400dc472 for everything else",
         _long(LFO_MASK_STOCK))
    # 2026-11-11: a lower LFO's write into a higher LFO's control, heard one frame later
    _need(content, MOD_EVAL_SITE - 4, bytes.fromhex("132c2f0a"), "the frame pushes the evaluator's mirror (move.l %a2,-(%sp))")
    _need(content, MOD_EVAL_SITE + 6, bytes.fromhex("4fef001c"), "... and pops its seven arguments")
    edit(MOD_EVAL_SITE, bytes.fromhex("4eb9") + _long(csyms["mod_eval"]),
         "the frame's LFO evaluator: the lower LFOs' last writes into higher LFOs' controls added "
         "into the mirror first (mod_eval_pre), then stock's 0x40137a06, then the matrix's routes (mx_eval)",
         MOD_EVAL_STOCK)
    _need(content, MOD_WB_SITE - 0x10, bytes.fromhex("752c004a" + ("726c" if pages.lfo4_on() else "7264")
                                                     + "7f4225470068b2876538"),
          "the write: DEST = mvs.b 74(%a4) into d7, bound-checked against 100 (DN2_LFO4: 108, edited above)")
    _need(content, MOD_WB_SITE + 8, bytes.fromhex("4df07a00"), "... the cell: lea (%a0,%d7.l*2),%fp")
    _need(content, 0x40137DC2, bytes.fromhex("53af0030"), "the LFO counter at 48(%sp), 2 down to 0")
    _need(content, 0x40137DEA, bytes.fromhex("528dd3af0034"), "the voice row in %a5, its slot 0 at 52(%sp)")
    edit(MOD_WB_SITE, bytes.fromhex("4eb9") + _long(csyms["mod_wb"]) + bytes.fromhex("4e71"),
         "the LFO evaluator's DEST write: a lower LFO's into a higher LFO's control goes to a "
         "shadow cell (mod_wb_cell), carried into the mirror next frame", MOD_WB_STOCK)
    _need(content, SNAP_SITE, SNAP_STOCK, "stock's smoother snap, as sm_snap replays it")
    edit(SNAP_SITE, bytes.fromhex("4ef9") + _long(csyms["sm_snap"]),
         "the smoother snap at a voice's note: the same 101 words, 4 instructions each (sm_snap)", SNAP_STOCK[:6])
    # 2026-11-17 (the User: the constant cost); 2026-11-19 with DN2_LFO4 off too (the User: LFO4 behind its flag)
    _need(content, SMOOTH_SITE + 8, bytes.fromhex("266f00202a3c7c290000"), "the smoother's own start, as sm_fast replays it")
    edit(SMOOTH_SITE, bytes.fromhex("4ef9") + _long(csyms["sm_fast"]) + bytes.fromhex("4e71"),
         "the parameter smoother: stock's own instructions, its loop four bodies a pass (sm_fast)", SMOOTH_STOCK)
    if True:                                     # lfo4 (DN2_LFO4) and lfowaves as lfo_fast replays them, or stock's own
        from . import lfofast as _lf
        _lf_specs = _lf.specs()
        if _lf.defines(*_lf_specs, lambda va, n: _read(content, va, n)) != _lf.defines(*_lf_specs):
            raise ComposeError("lfo_fast: lfo4's cave stubs (or stock's evaluator) read differently with stock under them")
        _need(content, _lf.EVAL_VA, _lf.EVAL_ENTRY, "the LFO evaluator's own start, as lfo_fast replays it")
        edit(_lf.EVAL_VA, bytes.fromhex("4ef9") + _long(csyms["lfo_fast"]) + bytes.fromhex("4e71"),
             "the LFO evaluator A: stock's (lfo4's, lfowaves') instructions, its calls and stubs inline (lfo_fast)",
             _lf.EVAL_ENTRY)
    _need(content, MODS_SITE + 8, bytes.fromhex("246f0040428324"), "MOD SETUP's own start, as mods_fast replays it")
    _need(content, 0x400DB340, bytes.fromhex("4feffff0700448d7003c"), "MOD SETUP's kernel, as mods_fast inlines it")
    edit(MODS_SITE, bytes.fromhex("4ef9") + _long(csyms["mods_fast"]) + bytes.fromhex("4e71"),
         "MOD SETUP's pass: stock's kernel inline, its own instructions, 80 calls a frame fewer (mods_fast)", MODS_STOCK)
    for va in MXS_COPY_SITES:                    # 2026-11-21: MOD SETUP's copies into a voice (csrc/matrix/setup.S)
        edit(va, bytes.fromhex("47f9") + _long(csyms["mxs_copy"]),
             "MOD SETUP's copy into a voice: an entry the popup muted lands at depth 0 (mxs_copy)", MXS_COPY_STOCK)

    # 2026-11-11: the wishes record (csrc/wishes, docs/wishes-record.md): its four sites
    edit(WISH_SAVE_SITE, bytes.fromhex("4ef9") + _long(csyms["wish_save_stub"]) + bytes.fromhex("4e71"),
         "the stored-sound SAVE, past its value loop: a sound with a wishes record gets its link in the lane "
         "(wish_save)", WISH_SAVE_STOCK)
    edit(WISH_LOAD_SITE, bytes.fromhex("4ef9") + _long(csyms["wish_load_stub"]),
         f"the stored-sound LOAD, past its value loop: the link read into the wishes record (wish_load); the "
         f"stub replays `moveq #{top + 2},%d2`: machine types -1..{top} are kept (stock keeps -1..4; anything "
         "else loads as FM Tone)", WISH_LOAD_STOCK)
    _need(content, WISH_LOAD_SITE + 6, bytes.fromhex("20300c00"), "the loader goes on: move.l (%a0,%d0.l*4),%d0")
    _need(content, WISH_SAVE_SITE + 8, bytes.fromhex("e1883540"), "the saver goes on: lsl.l #8,%d0 ; move.w %d0,...")
    # 2026-11-12: kits and patterns (csrc/wishes/item.c, docs/wishes-record.md "Every item type")
    _need(content, 0x400DDDB6, bytes.fromhex("4fefffe048d77c1c"),
          "the kit loader's entry: lea -32(%sp),%sp ; movem.l (8 registers): a3 live, a2 stored")
    _need(content, WISH_KIT_LOAD_SITE + 8, bytes.fromhex("2f0b4eba"), "the kit loader goes on: move.l %a3,-(%sp) ; jsr")
    _need(content, 0x400DDFA8, bytes.fromhex("4fefffe448d73c1c246f0020266f0024"),
          "the kit saver's entry: a2 stored, a3 live")
    _need(content, WISH_KIT_SAVE_SITE + 6, bytes.fromhex("223cbacef00c254128ab"),
          "the kit saver goes on: the terminator at stored 10411 (the link lies past it)")
    _need(content, 0x400DE77A, bytes.fromhex("4fefffe048d73c3c246f0024242f0028"),
          "the pattern loader's entry: a2 live, d2 stored")
    _need(content, WISH_PAT_LOAD_SITE - 0x14, bytes.fromhex("4eba"), "... its lock loader call (d2 = stored + 68148)")
    _need(content, WISH_PAT_LOAD_SITE + 6, bytes.fromhex("41ef002c25900800"), "the pattern loader goes on")
    _need(content, 0x400DE90C, bytes.fromhex("4fefffe848d7047c242f001c262f0020"),
          "the pattern saver's entry: d2 stored, d3 live")
    _need(content, WISH_PAT_SAVE_SITE - 4, bytes.fromhex("4fef0018"), "... past its lock saver call (d3 = live + 97872)")
    _need(content, WISH_PAT_SAVE_SITE + 6, bytes.fromhex("6002"), "the pattern saver goes on: bra.s to its return")
    _need(content, 0x400DEBCE, bytes.fromhex("4feffff048d71c04246f0014266f0018"),
          "the song loader's entry: a2 live, a3 stored")
    _need(content, WISH_SONG_LOAD_SITE + 6, bytes.fromhex("41eb0014"), "the song loader goes on: its rows")
    _need(content, 0x400DECC6, bytes.fromhex("4fefffec48d73c04246f0018266f001c"),
          "the song saver's entry: lea -20(%sp),%sp ; 5 registers: stored 24(%sp), live 28(%sp)")
    _need(content, WISH_SONG_SAVE_SITE - 0x10, bytes.fromhex("487800ac42a7486a0b54"),
          "... its tail 2,900..3,071 zeroed (memset 172 B), 12 B pushed: live at 40(%sp) at the site")
    _need(content, WISH_SONG_SAVE_SITE + 6, bytes.fromhex("7001"), "the song saver goes on: moveq #1,%d0")
    _need(content, 0x400DF050, bytes.fromhex("4fefffec48d70c1c246f0018266f001c"),
          "the settings loader's entry: a2 live, a3 stored")
    _need(content, WISH_PS_LOAD_SITE + 6, bytes.fromhex("0681fffff060"), "the settings loader goes on")
    _need(content, 0x400DF6DE, bytes.fromhex("4feffff448d70c04246f0010266f0014"),
          "the settings saver's entry: a2 stored, a3 live")
    _need(content, WISH_PS_SAVE_SITE - 0xC, bytes.fromhex("1141021e0c80000001e2"),
          "... its tail 542..1,023 zeroed just before the site")
    _need(content, WISH_PS_SAVE_SITE + 6, bytes.fromhex("6002"), "the settings saver goes on: bra.s to its return")
    for site, stub, old, what in (
            (WISH_KIT_LOAD_SITE, "wish_kit_load_stub", WISH_KIT_LOAD_STOCK, "the kit LOAD: the link past its terminator read (wish_kit_load)"),
            (WISH_KIT_SAVE_SITE, "wish_kit_save_stub", WISH_KIT_SAVE_STOCK, "the kit SAVE: the kit's link written past its terminator (wish_kit_save)"),
            (WISH_PAT_LOAD_SITE, "wish_pat_load_stub", WISH_PAT_LOAD_STOCK, "the pattern LOAD: the link in an unused lock record read (wish_pattern_load)"),
            (WISH_PAT_SAVE_SITE, "wish_pat_save_stub", WISH_PAT_SAVE_STOCK, "the pattern SAVE: the link written into the last unused lock record (wish_pattern_save)"),
            (WISH_SONG_LOAD_SITE, "wish_song_load_stub", WISH_SONG_LOAD_STOCK, "the song LOAD: the link in its zeroed tail read (wish_song_load)"),
            (WISH_SONG_SAVE_SITE, "wish_song_save_stub", WISH_SONG_SAVE_STOCK, "the song SAVE: the link written after stock zeroes its tail (wish_song_save)"),
            (WISH_PS_LOAD_SITE, "wish_ps_load_stub", WISH_PS_LOAD_STOCK, "the project settings LOAD: the link in their zeroed tail read (wish_settings_load)"),
            (WISH_PS_SAVE_SITE, "wish_ps_save_stub", WISH_PS_SAVE_STOCK, "the project settings SAVE: the link written after stock zeroes their tail (wish_settings_save)")):
        jmp = bytes.fromhex("4ef9") + _long(csyms[stub])
        edit(site, jmp + bytes.fromhex("4e71") * ((len(old) - 6) // 2), what, old)

    # v0.38: per-project pools: the four detours, entered by jmp (the stack as stock left it)
    _need(content, PJ_BEGIN_SITE + 8, bytes.fromhex("262f0028"), "the load goes on: move.l 40(%sp),%d3")
    _need(content, PJ_LOADED_SITE - 2, bytes.fromhex("67de"), "the load's success test just before")
    _need(content, PJ_LOADED_SITE + 8, bytes.fromhex("42a72f03"), "the load goes on: clr.l -(%sp) ; move.l %d3,-(%sp)")
    _need(content, PJ_END_SITE + 10, bytes.fromhex("4e75"), "the load's rts")
    _need(content, PJ_NEW_SITE + 10, bytes.fromhex("42a72f0a"), "NEW goes on: clr.l -(%sp) ; move.l %a2,-(%sp)")
    _need(content, 0x400428C0, bytes.fromhex("4e56ffa848d71c3c"), "NEW's entry: link.w %fp,#-88 (12(%fp) its slot)")
    edit(PJ_BEGIN_SITE, bytes.fromhex("4ef9") + _long(csyms["smp_pj_begin_hook"]) + bytes.fromhex("4e71"),
         "the project LOAD's entry: counted, and the DSP's directory emptied at once (per-project pools)",
         PJ_BEGIN_STOCK)
    edit(PJ_LOADED_SITE, bytes.fromhex("4ef9") + _long(csyms["smp_pj_loaded_hook"]) + bytes.fromhex("4e71"),
         "the project LOAD's success: the slot set as stock, then noted for the pools' switch",
         PJ_LOADED_STOCK)
    edit(PJ_END_SITE, bytes.fromhex("4ef9") + _long(csyms["smp_pj_end_hook"]) + bytes.fromhex("4e714e71"),
         "the project LOAD's exit: counted (a LOAD that failed gives the pool back)", PJ_END_STOCK)
    edit(PJ_NEW_SITE, bytes.fromhex("4ef9") + _long(csyms["smp_pj_new_hook"]) + bytes.fromhex("4e714e71"),
         "NEW project: the slot set as stock, then noted (an empty pool, the owner's decision 1)",
         PJ_NEW_STOCK)
    _need(content, PJ_WRITE_SITE + 8, bytes.fromhex("246f0040286f0038262f003c"),
          "the project write goes on: movea.l 64(%sp),%a2 ; movea.l 56(%sp),%a4 ; move.l 60(%sp),%d3 (the slot)")
    edit(PJ_WRITE_SITE, bytes.fromhex("4ef9") + _long(csyms["ins_pj_write_hook"]) + bytes.fromhex("4e71"),
         "the project write (a slot to the +Drive): replayed, the slot noted, the inserts' record follows "
         "(csrc/inserts/store.c)", PJ_WRITE_STOCK)

    # 2026-11-11: the glass inverted while the test channel is armed (csrc/devtest)
    _need(content, GLASS_SEND_SITE + 8, bytes.fromhex("282f0018262f0014"),
          "the sender goes on: move.l 24(%sp),%d4 (page) ; move.l 20(%sp),%d3 (column)")
    _need(content, PANEL_DIFF_SITE + 8, bytes.fromhex("2479402a10c8"), "panel_diff goes on: movea.l FRONT,%a2")
    _need(content, GLASS_WHOLE_SITE, bytes.fromhex("4fefffe448d7043c2a39402a10c8"),
          "the whole-frame send: its frame, then FRONT")
    edit(GLASS_SEND_SITE, bytes.fromhex("4ef9") + _long(csyms["dt_glass"]) + bytes.fromhex("4e71"),
         "the glass's 8-byte group sender: the bytes flipped while the test channel is armed (dt_glass)",
         GLASS_SEND_STOCK)
    edit(PANEL_DIFF_SITE, bytes.fromhex("4ef9") + _long(csyms["dt_present"]) + bytes.fromhex("4e71"),
         "panel_diff: the whole frame once when the armed state turns, else stock's diff (dt_present)",
         PANEL_DIFF_STOCK)

    # 2026-11-12: the preset browser's ENGINE filter (csrc/presets): its SORTING row and list, the test in the rebuild
    _need(content, ENG_TEST_SITE + 6, bytes.fromhex("4e922f032f004e95"),
          "MIDI's test goes on: jsr (%a2) the library ; the slot ; jsr (%a5) is-MIDI")
    _need(content, ENG_SORT_SITE - 8, bytes.fromhex("2f064e942f034e94"), "FILTER's row added, its functions destroyed")
    _need(content, ENG_SORT_SITE + 8, bytes.fromhex("4e95223c400a"), "SEARCH's row follows: jsr (%a5) operator new")
    _need(content, ENG_CTOR_SITE - 8, bytes.fromhex("42aa058042aa0588"), "the constructor clears the tags and the sort")
    edit(ENG_TEST_SITE, bytes.fromhex("4ef9") + _long(csyms["eng_test_hook"]),
         "the preset list's rebuild: the engines ticked in ENGINE (eng_match), then MIDI's test as stock's",
         ENG_TEST_STOCK)
    edit(ENG_SORT_SITE, bytes.fromhex("4ef9") + _long(csyms["eng_sort_hook"]) + bytes.fromhex("4e71"),
         "the SORTING menu: an ENGINE row after FILTER, opening its own tick list (eng_sort_row, eng_list)",
         ENG_SORT_STOCK)
    edit(ENG_CTOR_SITE, bytes.fromhex("4eb9") + _long(csyms["eng_ctor_hook"]) + bytes.fromhex("4e71"),
         "the preset view's constructor: the engines cleared with stock's filters", ENG_CTOR_STOCK)
    # 2026-11-12: LIVE SELECT (csrc/msel): its row, the last of PERSONALIZE
    # 2026-11-12: the DSP load budget at note-on (csrc/load/hooks.S load_alloc_hook): the allocator through our check
    _need(content, LOAD_ALLOC_SITE - 2, bytes.fromhex("2f03"), "the note-on's last argument: move.l %d3,-(%sp) (the track)")
    _need(content, LOAD_ALLOC_SITE + 6, bytes.fromhex("2d42ff984fef0024"), "... after it: move.l %d2,-104(%fp) ; lea 36(%sp),%sp")
    edit(LOAD_ALLOC_SITE, bytes.fromhex("4eb9") + _long(csyms["load_alloc_hook"]),
         "the audio ISR's note-on allocation: PARA's chords (pv_pre / pv_post) and the DSP load budget "
         "(load_pre / load_post)", LOAD_ALLOC_STOCK)
    _need(content, PV_REL_SITE - 2, bytes.fromhex("2f03"), "the key-up's last argument: move.l %d3,-(%sp) (the track)")
    _need(content, PV_REL_SITE + 6, bytes.fromhex("4fef0024"), "... after it: lea 36(%sp),%sp")
    edit(PV_REL_SITE, bytes.fromhex("4eb9") + _long(csyms["pv_rel_hook"]),
         "the audio ISR's key-up of a note (the allocator's release): PARA's joined notes first (pv_rel)", PV_REL_STOCK)
    _need(content, LIVE_MENU_SITE - 10, bytes.fromhex("4e932f054e932f044e93"), "PERSONALIZE's last row's functions destroyed")
    _need(content, LIVE_MENU_SITE + 6, bytes.fromhex("4fef00804e75"), "... then lea 128(%sp),%sp ; rts")
    edit(LIVE_MENU_SITE, bytes.fromhex("4ef9") + _long(csyms["live_menu_hook"]),
         "SETTINGS > PERSONALIZE: a LIVE SELECT row after the last (live_row), then stock's epilogue",
         LIVE_MENU_STOCK)

    # 2026-11-12: REMOTE CONTROL in USB CONFIG (csrc/devtest/usbcfg.c)
    _need(content, USB_REBUILD_SITE + 6, bytes.fromhex("2f0a2068001c4e90"),
          "rebuild goes on: move.l %a2,-(%sp) ; movea.l 28(%a0),%a0 ; jsr (%a0) (the cursor put back)")
    _need(content, 0x40105064, bytes.fromhex("4e95"), "rebuild's first item: jsr (%a5), %a5 = 0x401173b8")
    _need(content, 0x40104F94, bytes.fromhex("4bf9401173b8"), "lea 0x401173b8,%a5: MenuItem's constructor")
    _need(content, 0x40104FAC, bytes.fromhex("41faf8a8"), "lea 0x40104856(%pc),%a0: the label's manager")
    _need(content, 0x40104FD6, bytes.fromhex("41faf8d0"), "lea 0x401048a8(%pc),%a0: a choice's manager")
    _need(content, 0x40104CCE, bytes.fromhex("d0b944645d84"), "a choice's box: add.l 0x44645d84,%d0")
    _need(content, 0x40104F42, bytes.fromhex("4fefff9448d77cfc"), "rebuild's entry (dt_usb_yes calls it after a change)")
    _need(content, 0x40105256, bytes.fromhex("2f0a206f00082450"), "a choice's YES: its view, then rebuild (as ours)")
    edit(USB_REBUILD_SITE, bytes.fromhex("4ef9") + _long(csyms["dt_usb_rebuild"]),
         "USB CONFIG's rebuild: a fourth item, REMOTE CONTROL (dt_usb_rebuild), before the cursor is put back",
         USB_REBUILD_STOCK)

    # the sample link: SysEx in (v0.14); out over the TDM link alone (v0.20)
    edit(LINK_RX_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_rx_hook"]),
         "the SysEx router: the sample link's requests (F0 00 20 3C 7D 01) to smp_rx", LINK_RX_STOCK)

    # the fast link (v0.16): the SSI ISR, its transmit fill done, through smp_tdm_hook
    _need(content, TDM_SITE + 8, bytes.fromhex("2f024eb94012a7c6"), "the ISR goes on: push d2 ; jsr 0x4012a7c6")
    edit(TDM_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_tdm_hook"]) + bytes.fromhex("4e71"),
         "the SSI audio ISR after its transmit fill: smp_tdm writes the sample link's packet "
         "into TDM slots 8..15 and reads the DSP's from slots 14..15", TDM_STOCK)

    for va, stock_hex, sym, call, what in (STOCKLINK_SITES if pages.stock_link_fast_on() else ()):
        edit(va, site_bytes(stock_hex, csyms[sym], call), f"stocklink: {what} ({sym})", bytes.fromhex(stock_hex))
    if pages.stock_link_fast_on():          # (2026-11-21) skl_rxclr replays these and resumes at 0x40027a10
        _need(content, 0x400279F2, bytes.fromhex("45f94013419ce7a806804e6e71002f004e924878005448798000" "53c04e92"
                                                 "4879800053c0"), "mode 6's two clears through jsr (%a2), then the resume")
    for va, stock_hex, sym, call, what, tail in (OBFAST_SITES if pages.ob_fast_on() else ()):
        edit(va, site_bytes(stock_hex, csyms[sym], call, tail), f"obfast: {what} ({sym})", bytes.fromhex(stock_hex))

    for va, want, why in SLIDE_DRAW_GUARDS:
        _need(content, va, bytes.fromhex(want), why)

    # the system meter (csrc/meter): FUNC held, DSP %, CPU % and the free heap on every page
    for va, want, why in METER_GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    for va, stock_hex, sym, what in METER_SITES:
        edit(va, bytes.fromhex("4eb9") + _long(csyms[sym]),
             f"the system meter: {what} -> {sym}, which replays it", bytes.fromhex(stock_hex))

    # no screen intro: the intro's skip flag forced to 1 (Elektron's own skip path)
    for va, want, why in NOINTRO_GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    edit(NOINTRO_SITE, NOINTRO_NEW, "no screen intro: the start-up's intro skip flag forced to 1 (moveq #1,%d0): "
         "the starter posts the intro-done semaphore and never starts the intro task", NOINTRO_STOCK)

    # the per-track inserts: the FX mode's header as a mode of two pages
    for va, want, why in INS_HDR_GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    edit(INS_HDR_SITE, bytes.fromhex("4eb9") + _long(csyms["ins_hdr_tail"]),
         "the mode header's exit: a bare \"FX\" (the track FX mode, one page) becomes \"FX (1/2)\", "
         "or \"FX (2/2)\" with the INSERT page up (ins.c ins_header)", INS_HDR_STOCK)

    # DIRECT JUMP (csrc/jump, docs/jump.md): off unless PTN + YES turns it on
    for va, want, why in JUMP_GUARDS:
        _need(content, va, bytes.fromhex(want), why)
    edit(JUMP_CUE_SITE, bytes.fromhex("4eb9") + _long(csyms["jmp_cue"]),
         "DIRECT JUMP: the PTN view's one-pattern cue: stock's, then armed if the setting is on "
         "and the sequencer plays", JUMP_CUE_STOCK)
    for va, stock_hex, sym, what in JUMP_ISR_SITES:
        edit(va, bytes.fromhex("4ef9") + _long(csyms[sym]),
             f"DIRECT JUMP, the sequencer tick: {what} -> {sym}, which replays it", bytes.fromhex(stock_hex))
    edit(JUMP_KEY_SLOT, _long(csyms["jmp_key"]),
         "DIRECT JUMP: the PTN view's key handler (vtable): PTN held + YES / NO sets it on / off; "
         "everything else to stock's 0x400fa88a", _long(JUMP_KEY_STOCK))

    # the RECORDER page's YES (v0.15): the parameter page's key handler through smp_key,
    # which takes YES on that page and hands everything else to stock's
    edit(KEY_SLOT, _long(csyms["smp_key"]),
         "the parameter page's key handler (vtable): smp_key, YES on the sample machines' "
         "RECORDER page records; every other key and page goes on to stock's 0x40016480",
         _long(KEY_STOCK))

    # 2026-11-18: ENV2's page (csrc/matrix/env2_page.c): stock's AMP draw not drawn under it, only its meter
    edit(AMP_DRAW_SLOT, _long(csyms["env2_amp_draw"]),
         "the AMP page view's draw (vtable): env2_amp_draw, while ENV2's page covers it only the level meter; "
         "every other time stock's 0x4006dfb6", _long(AMP_DRAW_STOCK))

    # one detent a choice (v0.15): the setter's write through smp_quant_hook
    _need(content, QUANT_SITE - 4, bytes.fromhex("4e90588f"), "the setter's jsr %a0@ ; addq #4 before its write")
    _need(content, QUANT_SITE + 6, bytes.fromhex("4a07"), "... and its tst.b %d7 after")
    edit(QUANT_SITE, bytes.fromhex("4eb9") + _long(csyms["smp_quant_hook"]),
         "the parameter setter's write: smp_quant moves a sample machine's few-choice "
         "control one choice a detent, then writes as stock", QUANT_STOCK)

    # 2026-11-11: the Reverb / Delay pages' TYPE (FX records 131, 122) are written by the kit setter 0x40037d86:
    # its store goes through fx_type_hook, which steps them in the list's order (STOCK first)
    _need(content, FX_TYPE_SITE - 4, bytes.fromhex("4e90588f"), "the kit setter's jsr %a0@ ; addq #4 before its write")
    _need(content, FX_TYPE_SITE + 6, bytes.fromhex("0c840000" "0094"), "... and its cmpi.l #148,%d4 after")
    edit(FX_TYPE_SITE, bytes.fromhex("4eb9") + _long(csyms["fx_type_hook"]),
         "the kit setter's write: fx_type_quant steps the Reverb / Delay TYPE in the list's order "
         "(STOCK first), then writes as stock", FX_TYPE_STOCK)

    # 2026-11-19 (the User: virtual notches on p-locks too, csrc/knobs/notch.c): the sound and kit ParameterSets'
    # LOCK_SET through kn_lock_snd / kn_lock_kit, which call stock's after a knob-driven crossing lands on the centre
    for slot, fn, stock_fn in ((LOCK_SND_SLOT, "kn_lock_snd", LOCK_SND_STOCK), (LOCK_KIT_SLOT, "kn_lock_kit", LOCK_KIT_STOCK)):
        _need(content, slot, _long(stock_fn), f"the ParameterSet vtable's LOCK_SET {stock_fn:#x}")
        edit(slot, _long(csyms[fn]), f"a ParameterSet's LOCK_SET (vtable): {fn}, a knob-driven p-lock that crosses a "
             f"bipolar value's centre lands on it; then stock's {stock_fn:#x}", _long(stock_fn))

    # 7. getMachineType(track): WaveTone for the UI, the real type where it is identity
    _need(content, TRACK_TYPE_FN, TRACK_TYPE_FN_STOCK, "getMachineType(track), as raw_track copies it")
    edit(TRACK_TYPE_READ, bytes.fromhex("4ef9") + _long(layout["canon_track"]),
         "getMachineType(track): type 5 is reported as WaveTone", TRACK_TYPE_READ_STOCK)
    for op_va, op, what in IDENTITY_SITES:
        _need(content, op_va, bytes.fromhex(op), f"{what}: the instruction")
        edit(op_va + 2, _long(layout["raw_track"]), f"{what}: asks for the real type",
             _long(TRACK_TYPE_FN))

    # 7b. getMachineType(model, track): the real type, for MACHINE SEL and the re-commits
    _need(content, MODEL_TRACK_TYPE_JMP, bytes.fromhex("4ef9"), "0x4003134e's tail jump")
    edit(MODEL_TRACK_TYPE_JMP + 2, _long(layout["raw_track"]),
         "getMachineType(model, track) 0x4003134e: the real type (MACHINE SEL's marker and "
         "cursor, the track swap, the machine restores)", _long(TRACK_TYPE_FN))

    # 8. the sound's "is this parameter mine?"
    _need(content, VALID_SITE + len(VALID_STOCK), VALID_NEXT, "the ownership test's record-page call")
    edit(VALID_SITE, bytes.fromhex("4eb9") + _long(layout["canon_valid"]),
         "the sound's parameter-ownership test: type 5 owns WaveTone's machine parameters",
         VALID_STOCK)
    # parameter slides (csrc/slides, dnfw.slides, docs/slides.md): the per-voice note block
    # and the lock applier (the trig's slide starts), the frame's smoother (every slide one
    # frame on), the lock-list builder (the step's SLD/SLEN), the step clear, the lock table's
    # LOAD and SAVE (our records' stored ids)
    edit(SL.PRE_SITE, bytes.fromhex("4eb9") + _long(csyms["sl_pre_hook"]),
         "slides: a note's voice in the frame ISR: sl_pre keeps the track's values before the trig",
         bytes.fromhex(SL.PRE_STOCK))
    _need(content, SL.PRE_SITE + 6, bytes.fromhex("49ec05ee670e"), "... then lea 1518(%a4),%a4 ; beq.s")
    edit(SL.APPLY_SITE, bytes.fromhex("4ef9") + _long(csyms["sl_apply"]) + bytes.fromhex("4e71"),
         "slides: the lock applier 0x400db1f6 through sl_apply (stock's, then the trig's slide)",
         bytes.fromhex(SL.APPLY_STOCK))
    # v0.52 MUTE SRC (rectrig.c ms_frame): the frame ISR's first copy after its voice loop (the
    # loop that writes each voice's LEVEL, slots and routing into the frame, 0x400274fa..0x4002759e)
    # through ms_frame: stock's copy, then the muted tracks' voices' LEVEL and FX sends faded to 0
    _need(content, MUTE_SITE - 18, bytes.fromhex("6600ff5a4878000e486a0cf448798000685a"),
          "the voice loop's end, then the copy's three arguments")
    edit(MUTE_SITE, bytes.fromhex("4eb9") + _long(csyms["ms_frame"]),
         "FLEX MUTE SRC: the frame ISR's copy after the voice loop through ms_frame (stock's copy, then "
         "the muted tracks' LEVEL and sends)", bytes.fromhex(MUTE_STOCK))
    _need(content, SL.SMOOTH_SITE - 10, bytes.fromhex("487980003af02d42ff64"), "the ISR pushes the smoother's source")
    edit(SL.SMOOTH_SITE, bytes.fromhex("4eb9") + _long(csyms["sl_smooth"]),
         "slides: the frame's smoother through sl_smooth (stock's, then every slide one frame on)",
         bytes.fromhex(SL.SMOOTH_STOCK))
    edit(SL.BUILD_SITE, bytes.fromhex("4ef9") + _long(csyms["sl_build"]),
         "slides: the lock-list builder through sl_build (stock's, then the step's SLD/SLEN)",
         bytes.fromhex(SL.BUILD_STOCK))
    edit(SL.CLEAR_SITE, bytes.fromhex("4ef9") + _long(csyms["sl_clear"]) + bytes.fromhex("4e71"),
         "slides: clearing a step's locks clears its SLD/SLEN too", bytes.fromhex(SL.CLEAR_STOCK))
    edit(SL.LOAD_SITE, bytes.fromhex("4ef9") + _long(csyms["sl_load"]) + bytes.fromhex("4e71"),
         "slides: a pattern's lock table LOAD keeps SLD/SLEN records (ids 200/201)",
         bytes.fromhex(SL.LOAD_STOCK))
    edit(SL.SAVE_SITE, bytes.fromhex("4ef9") + _long(csyms["sl_save"]) + bytes.fromhex("4e71"),
         "slides: a pattern's lock table SAVE stores SLD/SLEN records as ids 200/201",
         bytes.fromhex(SL.SAVE_STOCK))
    for va, stock_hex, label in SL.PASTE_SITES:    # v0.40: copy and paste carry SLD/SLEN
        n = len(stock_hex) // 2
        edit(va, bytes.fromhex("4eb9") + _long(csyms[label]) + bytes.fromhex("4e71") * ((n - 6) // 2),
             f"slides: copy/paste carries SLD/SLEN ({label})", bytes.fromhex(stock_hex))
    for name in ("sl_ui_table", "sl_page_up", "sl_page_seen", "sl_knob", "sl_pre_hook", "sl_pre", "sl_apply", "sl_smooth", "sl_build", "sl_clear", "sl_load", "sl_save",
                 "sl_lock_get", "sl_lock_set", "sl_v", "sl_cap", "sl_started", "sl_nxt_last", "sl_ticks", "sl_pasted", "sl_tclip", "sl_paste",
                 "sl_draw_sld", "sl_draw_slen"):
        layout[name] = csyms[name]
    edit(VOICE_COPY_SITE, bytes.fromhex("4eb9") + _long(csyms["wish_voice_copy"]) + bytes.fromhex("6046"),
         "the audio interrupt's voice loop: its four memcpy calls as one copy (wish_voice_copy)", VOICE_COPY_STOCK)
    edit(POST_COPY_SITE, bytes.fromhex("4fef000c4eb9") + _long(csyms["wish_post_copy"]) + bytes.fromhex("6050"),
         "the audio interrupt past its voice loop: four memcpy calls as one copy (wish_post_copy)", POST_COPY_STOCK)
    # last of every edit: each reference to memcpy / memset but Overbridge's (WISH_KEEP) names the wishes stub;
    # one that another hook already rewrote fails its stock check here
    for target, stub, word in ((WISH_MEMCPY, "wish_memcpy_stub", "memcpy"), (WISH_MEMSET, "wish_memset_stub", "memset")):
        refs = [BASE + at for at in range(2, len(stock) - 3, 2)
                if stock[at:at + 4] == _long(target) and struct.unpack_from(">H", stock, at - 2)[0] in WISH_OPS]
        if len(refs) != WISH_REFS[target] or (target == WISH_MEMCPY and not set(WISH_KEEP) <= set(refs)):
            raise ComposeError(f"{len(refs)} references to {word}, not the {WISH_REFS[target]} measured on 1.12")
        for va in refs:
            if va not in WISH_KEEP and va not in WISH_HOOKED:
                edit(va, _long(csyms[stub]), f"wishes: a {word} reference names {stub}", _long(target))
    for name in ("wish_memcpy_stub", "wish_memset_stub", "wish_load_stub", "wish_save_stub", "wish_load_displaced",
                 "wish_save_displaced", "wish_poll", "wish_n",
                 "wish_loads", "wish_links_in", "wish_saves", "wish_links_out", "wish_reentered", "wish_full",
                 "wish_copies", "wish_carries", "wish_clears", "wish_get", "wish_put", "wish_find",
                 "wish_pend_head", "wish_pend_tail", "wish_cells_written", "wish_resolved", "wish_missing",
                 "wish_wants", "wish_io_fails", "wish_edits", "wish_put_wait", "wish_puts", "wish_rx"):
        layout[name] = csyms[name]              # 2026-11-11: the wishes record (csrc/wishes): the checks read them
    for name in ("wish_item", "wish_item_loads", "wish_item_saves", "wish_item_nolane", "wish_item_dropped"):
        layout[name] = csyms[name]              # 2026-11-12: kits and patterns (csrc/wishes/item.c)
    from . import cpage as _cpage
    for name in _cpage.LOAD_ENTRIES:
        layout[name] = csyms[name]              # 2026-11-12: the DSP load budget (csrc/load): the check reads its state
    for name in _cpage.PARA_ENTRIES + _cpage.HOLD_ENTRIES:
        layout[name] = csyms[name]              # 2026-11-16: PARA as one voice (csrc/para/one.c): the check reads its state
    for name in ("mx_poll", "mx_eval", "mx_lay", "mx_compiles", "mx_env_on", "mx_env_off", "mx_dmask",
                 "ldp_pop", "ldp_poll", "ldp_draw", "ldp_visible", "ldp_p", "ldp_rows", "ldp_opens", "ldp_refusals", "ldp_turns",
                 "ldp_keys", "ldp_erased", "ldp_full", "ldp_alone", "ldp_dropped", "ldp_built", "ldp_routes_drawn", "ldp_valid", "ldp_checks", "ldp_detents",
                 "mxp_pop", "mxp_poll",
                 "mxp_draw", "mxp_visible", "mxp_pushes", "mxp_opens", "mxp_refusals", "mxp_why",
                 "mxp_rid", "mxp_turns", "mxp_keys", "mxp_detents", "mxp_setup_dep", "mxp_setup_rows", "mxp_erased",
                 "mxp_order", "mxp_setup_hint", "mxp_rows_drawn", "mxp_lit", "ins_title_now",
                 "mxp_end", "mxp_fulls", "mxp_parts", "mxp_same", "mxp_dropped", "mxp_groups", "mxp_plains", "mxp_cancels", "mxp_wobbles", "mxp_seen",
                 "mxp_note", "mxp_per_note",
                 "mxs_copy", "mxs_mark", "mxs_copies", "mxs_refresh", "mxs_set", "mxs_mute",
                 "mxs_delete", "mxs_offers", "mxp_dims", "mxp_ticks",
                 "env2_visible", "mx_env2_locks", "sl_e2_held", "sl_e2_set", "env2_amp_draw", "wr_turn_held", "wr_drawn_at"):
        layout[name] = csyms[name]              # 2026-11-12: the matrix (csrc/matrix): the checks call them
    for name in ("mod_mask_hook", "mod_lfo_mask", "mod_eval", "mod_eval_pre", "mod_wb", "mod_wb_cell",
                 "sm_fast", "lfo_fast", "mods_fast", "mv_begin", "mv_cell", "mv_cell_span", "mv_knob", "mv_poll", "mv_end", "sl_lastv", "wr_screen"):
        layout[name] = csyms[name]              # 2026-11-11: csrc/modulation (the checks call them)
    for name in (("mx_probe",) if pages.route_probe_on() else ()):
        layout[name] = csyms[name]              # 2026-11-21: DN2_ROUTE_PROBE (matrix.c mx_probe): the cost checks
    for name in (("lh_selw", "lh_n") if pages.lfo_halfrate_on() else ()):
        layout[name] = csyms[name]              # 2026-11-20: half-rate LFOs (cascade.c lh_args): each frame's voice turns,
                                                # read by the slides step's stock comparison (scripts/slides_stock.py)
    for name in ("mx_kof", "mx_m_of", "mx_atab", "mx_lay_first", "mxa_convert", "mxa_compat", "mxa_converted",
                 "mxa_changed", "mxa_saved", "mx_route_level", "wish_drop", "mxa_stored", "wish_att_head",
                 "wish_att_lost", "wish_memcpy_stub"):
        layout[name] = csyms[name]              # 2026-11-19: DEP the attenuverter (csrc/matrix/atten.c): the checks
    for name in ("wish_busy", "wish_give", "wish_queued", "wish_q_max", "mxa_commit"):
        layout[name] = csyms[name]              # 2026-11-21: the table's queue for its lock's holder (csrc/wishes/table.c)
                                                # and the conversion's commit (atten.c): the checks
    for name in ("kn_cur", "kn_tcb", "kn_d", "kn_items", "kn_seen", "kn_catches", "kn_held", "kn_passes", "kn_releases", "kn_locks",
                 "kn_item", "kn_value", "kn_units", "kn_lock_snd", "kn_lock_kit", "smp_quant_hook"):
        layout[name] = csyms[name]              # 2026-11-19: knob notches (csrc/knobs): the checks read them
    for name in ("mtr_lbl_alone", "mtr_lbl_full"):
        layout[name] = csyms[name]              # 2026-11-19: the load labels' blinks alone / by a full redraw (the checks)
    for name in ("mtr_big", "mtr_big_shows", "mtr_big_alone", "mtr_big_full", "mtr_big_due", "mtr_big_groups", "mtr_key"):
        layout[name] = csyms[name]              # 2026-11-19: the big meter, FUNC tapped then held (the checks)
    for name in ("mv_loaded", "mc_loaded", "mtr_loaded", "mx_loaded", "prof_mine", "prof_audio", "env2_field_drawn", "mx_e2_knob"):
        layout[name] = csyms[name]              # 2026-11-18: each RAM block's "cleared since this load" word (code data,
                                                # 0 after every load): the restart check sets them back to 0
    layout.update(playout)
    # W2: where the C renderer's code ends (its rodata and data follow): the ship gate
    # checks [C_LOAD, c_text_end) as code
    layout["c_load"] = pages.C_LOAD
    layout["c_text_end"] = csyms["__text_end"]
    # remoteui-6: the end of its rodata; [C_LOAD, c_rodata_end) is never written at run time (every emulator
    # step watches it, scripts/emulib/codeguard.py), the range the test channel's identity CRC covers
    layout["c_rodata_end"] = csyms["__rodata_end"]
    # 2026-11-17 (dnfw.mods.ramcheck, waverider.word_spans): the generated header's number tables (load_md's u16
    # cycles ...), [start, end) each, where they were linked: numbers, never a pointer
    layout["c_number_tables"] = _number_tables(c_hdr, csyms)
    # 2026-11-18 (the User's rule, dnfw.mods.ramcheck "pointer"): every pointer the link filled in, in our C's data
    layout["c_pointer_sites"] = [a for a in sorted(c_abs32) if pages.C_LOAD <= a < pages.C_LOAD + len(cimage)]
    for name in ("smp_hi", "smp_walk", "smp_booted", "smp_cmds", "smp_tdm_sent", "smp_tdm_heard",
                 "smp_lfo_hook", "smp_lfo_fix", "smp_bank_live", "smp_bank_count", "smp_bank_blocked", "smp_lp_bank",   # v0.65
                 "smp_row_step", "smp_word_row", "smp_row_word", "smp_name", "smp_discard", "smp_set_samp_word", "smp_samp_word",
                 "smp_retries", "smp_saved", "smp_boot", "smp_save_recording", "smp_save_mark", "smp_load", "smp_lstate",
                 "rec_overlay", "rec_src", "rec_dest", "smp_ram", "smp_ram_at", "rec_phase", "trim_slot",
                 "trim_n", "trim_s", "trim_e", "nm_cur", "nm_text", "slc_state", "slc_page_seen", "slc_seen_draw", "slc_letgo", "slc_open_track",
                 "smp_analyse", "smp_analysis", "smp_onsets", "smp_slices_set", "smp_slices_get",
                 "slc_nfr", "slc_sl", "slc_ns", "slc_cur", "slc_grid_n", "smp_pos", "smp_pos_at", "smp_periods", "smp_dir_ok", "smp_meta_ok", "smp_lst_open", "smp_fb_open", "smp_fb_folder", "smp_fb_cur", "smp_fb_count", "smp_fb_mark_count", "smp_fb_mark_unused", "smp_fb_marked", "smp_fb_menu", "smp_mod_apply", "smp_quant", "smp_samp_turned", "smp_overlay_dirty", "rec_pv_on", "smp_func_held", "smp_question_up", "sn_opens", "sn_results", "sn_up", "smp_machine_commit", "smp_rx", "smp_fb_store", "smp_lib_refresh", "smp_lib_pending", "smp_lp_queued", "smp_lib_state", "smp_lib_writes", "smp_lib_load", "smp_lib_slot_of", "smp_lib_preview", "smp_lib_preview_stop", "smp_fb_rowtext", "smp_mq_off", "smp_fb_mcur", "smp_lp_done", "smp_lp_full", "smp_fb_auto", "smp_fb_auto_starts", "smp_lp_skipped", "smp_rec_store_named", "smp_name_set", "smp_formats", "smp_rs_done", "smp_rs_last", "smp_trim", "smp_l_order", "smp_walk_total", "smp_held_lo", "smp_held_hi", "smp_knob_d", "smp_knob_at", "smp_dsp_load", "smp_load_peak", "smp_load_seen", "smp_load_at", "wr_screen_obj", "rec_state", "rec_heard", "slc_kb_c", "slc_alloc_n", "smp_tables", "smp_pv_state", "trim_zoom", "trim_head_x", "sl_ui_table_now", "smp_push_slot", "sl_rec_knob", "sl_rec_held", "sl_rec_table", "rec_view", "rec_rlen", "rec_link", "rec_room", "as_done", "rec_saved_slot", "rec_rstrt", "rec_thres", "rec_src", "rec_chan", "sl_rec_page", "smp_rec_place", "smp_slot_empty", "smp_pl_dirp", "rec_combo", "rec_overlay", "rt_on", "rt_play", "rt_rplace", "rt_rbytes", "rt_pend", "rt_cur", "rt_cur_end", "rt_manual", "rt_qrec", "rt_qplay", "rt_pos", "rt_steps", "rt_nx_place", "rt_nx_room", "rt_nx_need", "rt_w", "rt_gen", "q_gen", "q_fire", "q_cancel", "rt_fired", "rt_refused", "rt_swaps", "rt_qfired", "rt_why", "rt_why_at", "rt_trig", "rt_bounce_samp", "rt_is_bounce", "rt_buf_of", "rt_trig_get", "rt_trig_toggle", "rt_rearm", "rt_count", "rt_take_handover", "rt_regions", "rt_rsteps", "rt_last_step", "rt_used", "rt_fired_at", "rt_fired_trk", "rt_why_trk", "rt_last_key", "bn_page", "bn_yes_at", "bn_active", "bn_led_walk", "bn_led_poll", "bn_led_claims", "bn_open", "bn_save", "bn_pages", "bn_said_at", "bn_said_n", "bn_nothing_at", "rt_frame", "rt_poll", "rt_cut", "smp_rt_sent", "rec_rt_take", "rt_q_set", "rt_q_waiting", "rt_knob", "rt_state", "rt_arm", "rt_req", "bn_sub", "rt_flex_req", "rt_req_waiting", "rt_buf_value", "rt_buf_code", "rt_samp_buf", "smp_samp_direct", "rec_gain", "sl_knob_push", "rt_clear", "bn_clear_ask", "bn_cleared", "bn_cleared_at", "fx_get", "fx_set", "fx_valid", "ms_frame", "ms_mask", "ms_frames", "ms_playing_mask", "ms_play_force", "rt_mute_knob", "bn_mute", "rec_peak", "rec_mon", "rec_sent_chan", "slc_view0", "slc_fv_n", "slc_fv_lo", "slc_fv_hi", "slc_fine_views", "slc_live_sends", "slc_grid_jumps", "smp_save_keep", "smp_save_head", "kh_on", "kh_close", "kh_set", "slc_follows", "slc_snaps", "smp_fine_reads", "smp_frames_read", "tn_retune", "tn_poll", "tn_pop", "tn_draw", "tn_kb_draw", "tn_kb_up", "tn_visible", "tn_set", "tn_offset", "tn_publish", "tn_cur", "tn_root", "tn_mask", "tn_ui", "tn_user", "tn_snap", "tn_sel", "tn_frames", "tn_writes", "tn_reads", "tn_bad", "tn_owner", "tn_opens", "tn_note", "tn_from", "pf_ui", "pf_sel", "pf_col", "pf_mute", "pf_opens", "pf_frames", "pf_writes", "pf_reads", "pf_bad", "pf_owner", "pf", "pf_set", "pf_tab", "pf_tsel", "pf_dbg", "pf_poll", "pf_publish", "pf_apply", "pf_mark",
                 "jmp_on", "jmp_armed", "jmp_pending", "jmp_count", "jmp_last", "jmp_loaded", "jmp_dirty",
                 "jmp_reads", "jmp_writes", "jmp_to", "jmp_from", "jmp_key", "jmp_poll", "jmp_forced",
                 # 2026-11-12: REMOTE CONTROL in USB CONFIG (csrc/devtest/usbcfg.c; the settings sector, jump.c)
                 "set_remote", "set_reset_seen", "dt_usb_items", "dt_usb_changes", "dt_usb_rebuild",
                 "dt_present", "dt_inv",   # 2026-11-17: the lines-only check inverts the glass (scripts/emu_line_redraw.py)
                 # v0.38: per-project pools
                 "smp_pj_begins", "smp_pj_ends", "smp_pj_loads", "smp_pj_news", "smp_pj_slot", "smp_pj_newslot", "smp_pj_last", "smp_blank_req", "smp_blank_sent", "smp_pl_on", "smp_pl_owner", "smp_pl_state", "smp_pl_writes", "smp_pl_switches", "smp_pl_lists_written", "smp_pl_events", "smp_pl_src", "smp_pl_boot_case", "smp_pl_gen", "smp_pl_skipped", "smp_pl_mismatch", "smp_discard", "smp_rename",
                 # v0.38: the count to the DSP after a live add (link.c K_HEAD)
                 "smp_heads", "smp_head_due", "smp_head_min", "smp_count_cover",
                 # v0.39: ERASE MOD DATA (erase.c; scripts/emu_erase.py)
                 "smp_er_lock", "smp_er_req", "smp_er_state", "smp_er_err", "smp_er_sector", "smp_er_value",
                 "smp_er_done", "smp_er_total", "smp_er_trims", "smp_er_reads", "smp_er_checks",
                 "smp_er_nchecks", "smp_er_job", "smp_er_start", "smp_er_poll",
                 "smp_er_retries", "smp_er_waits", "smp_er_resume",   # v0.41
                 # 2026-11-11: section 7 as LZMA and its +Drive copy (scripts/emu_lzma7_cache.py)
                 "dn7_status", "dn7_length", "dn7_late", "dn7c_state", "dn7c_why",
                 # v0.40: the slice menus' wait, LINKED points, the playhead's redraw (gate: slice, samplist)
                 "slc_pop", "slc_poll", "slc_stock_asked", "slc_fails", "slc_linked", "smp_norm_state",
                 "smp_pl_quiesce", "smp_analysis_slot", "smp_slot_frames", "wr_draws", "smp_pos_in", "smp_playhead",
                 # v0.40: folders inside folders
                 "smp_lib_fpar", "smp_fb_titletext", "smp_fb_delete",
                 # the RECORDER as the DT2's screens (rec_dt2.c): the DSP's status the checks set
                 "rec_room", "rec_frames", "rec_peak", "rec_wave", "rec_thres", "rec_link",
                 # the system meter (csrc/meter): its hooks and the figures the checks read
                 "mtr_isr_out", "mtr_switch", "mtr_poll", "mtr_draw",
                 # FDN8 (csrc/fdn8): the Reverb page's TYPE and names
                 "rvt_poll", "rvt_cell", "rvt_state", "rvt_placed", "rvt_seen",
                 # XDLY (csrc/xdly): the Delay page's TYPE and names
                 "dlt_poll", "dlt_cell", "dlt_state", "dlt_placed", "dlt_seen",
                 # the per-track inserts (csrc/inserts)
                 "isel_open", "isel_at", "isel_slot", "isel_opens", "isel_picks",   # INSERT SEL (csrc/msel; gate: insel)
                 "ttl_off", "ttl_draws", "ins_title_icon",   # the title bar's icon (csrc/inserts/ins.c; gate: insel)
                 "ins_pop", "ins_draw", "ins_visible", "ins_words", "ins_gen", "ins_up", "ins_sel", "ins_selv", "ins_mod", "ins_kv", "ins_fza",
                 "ins_hdr_tail", "ins_inst", "ins_slot_state", "ovw_up", "ovw_opens", "ovw_taps", "amp_sub", "ovw_key", "ovw_poll",
                 "ovw_alone", "ovw_fulls", "smp_tlm_cost", "load_stock",
                 "ins_store_poll", "ins_st_writes", "ins_st_loads", "ins_st_fails", "ins_st_moved", "ins_st_copied",   # the inserts' records
                 "ins_st_booted", "dm_ok", "dm_run", "dm_bits", "dm_tried", "dm_runs", "dm_fails", "dm_copied"):   # (2026-11-22: the +Drive moves; gates: insmove, drivemove)
        layout[name] = csyms[name]
    for name in ("hold_seq", "hold_count", "hold_len", "hold_keys", "hold_poll", "hold_final", "hold_rel"):   # DRONE's HOLD (csrc/hold)
        layout[name] = csyms[name]
    for name in ("para_live", "para_kept", "para_count", "vm_seen_hook", "vm_begin", "vm_draw", "vm_pop", "vm_seen",
                 "vm_sets", "vm_frames", "vm_hooks", "vm_bs", "vm_why",
                 "pu_voice_led", "pu_led_poll", "pu_led_sets", "pu_led_marks", "pu_led_state"):
        layout[name] = csyms[name]              # 2026-11-15: ANALOG 2's PARA (csrc/hold legato, csrc/para): the checks read them
    for name in ("scope_up", "scope_taps", "scope_ring", "scope_pos", "smp_rx_sh", "scope_draw", "scope_poll", "smp_ui_pop", "scope_frames", "scope_alone", "scope_dropped", "scope_gain", "scope_auto", "scope_zoom", "scope_set_taken", "scope_end"):   # AMP page 2's scope (csrc/scope)
        layout[name] = csyms[name]
    for name in ("mix_poll", "mix_draw", "mix_end", "mix_acc", "mix_sel", "mix_clip_at", "mix_live", "mix_want",
                 "mix_lvl_in", "mix_clip_in", "mix_off", "mix_alone", "mix_fulls", "mix_groups", "mix_lvl_n",
                 "mix_clip_n", "mix_why", "mix_draws", "mix_live_bits",
                 "mix_clip_forget", "mix_inner_in", "mix_inner_n", "mix_inner_last", "mix_dirty", "mix_held", "mix_let", "mix_thr_off", "smp_input_seq", "mtr_start_done", "mtr_start_at", "mtr_start_polls", "mtr_starting",
                 "mix_ovw_get", "mix_ovw_takes", "ovw_mix_taps", "ovw_mix_k", "mix_ov_clip_at", "mix_ov_live",
                 "ovw_tempo_opens", "ovw_preset_opens", "smp_fb_browse", "smp_fb_nactions", "smp_fb_action"):   # 2026-11-20: the mixer meters (csrc/meter/mixer.c; gate: mixmeter); 2026-11-21: the OUTPUTS overview (mixovw), the start-up's quiet (startup.c)
        layout[name] = csyms[name]
    for name in ("ins_period", "ins_take", "ins_trig", "ins_ui_poll", "ins_knob_now", "ins_route_dest", "ins_pkt",
                 "ins_chg", "ins_pkts", "ins_urgents", "ins_trigs", "ins_lk", "ins_cell", "ins_moff", "ins_keep",
                 "ins_rr", "ins_due", "ins_hdirty", "ins_tpg_gen", "ins_tpg_w", "ins_set_record", "ins_loaded",
                 "sl_ins_held", "sl_ins_set", "sl_ins_record", "mx_ins_routes", "smp_tdm", "smp_command",
                 "smp_tdm_sent", "mv_own_knob"):   # 2026-11-20: the inserts locked and modulated (csrc/inserts; gate: matrix)
        layout[name] = csyms[name]
    for name in ("ls_commits", "ls_reverts", "live_rows", "set_bits", "set_flag_put"):   # LIVE SELECT (csrc/msel; gate: livesel)
        layout[name] = csyms[name]
    for name in ("as_mask", "as_gen", "as_turns", "as_draws", "as_drum", "as_on", "as_set", "as_poll",
                 "as_sent"):                    # 2026-11-20: AMP ON/OFF for the drum machines (csrc/msel/ampsw.c; gate: drumamp)
        layout[name] = csyms[name]
    layout["msel_draw"] = csyms["msel_draw"]    # MACHINE SEL in two columns (csrc/msel/msel.c; gate: msel, colsw)
    for name in ("eng_mask", "eng_tests", "eng_lists", "eng_n"):   # the preset browser's ENGINE filter (csrc/presets)
        layout[name] = csyms[name]
    layout["mtr_ram"] = pages.METER_RAM      # the system meter's state block (csrc/meter/meter.c MTR_*)
    # 2026-11-11: where the page renderer's writable data starts and its image ends (its `.data`: every D_
    # variable, written at run time), so the engine gate holds the code and rodata before it to the loaded copy
    layout["c_data_start"], layout["c_image_end"] = csyms["__data_start"], csyms["__image_end"]
    # 2026-11-11: the Monomachine-style machines' unit formatters (csrc/sampler/fmt.c mnm_fmts, "no bare 0..127"),
    # so a gate can tell them from v0.47's signed TUNE formatter on record 240
    layout["mnm_fmts"] = csyms["mnm_fmts"]
    # v0.45: PING removed (owner, 2026-11-08). 2026-11-10: its mechanism (the FLTR list, names, LOAD
    # bound, slot_to_id, descriptor, curve) composed again for the A2 filter machines 7..11 only
    # (dnfw.engines.analog2.filters.coldfire), in what was PING's chunk; none built: all stock, as v0.45
    from ..engines.analog2.filters import coldfire as flt_cf
    # 2026-11-11: every function of the C chunk by name, for the CPU profiler's symbolizer (tools/dn2tools
    # profile.py); the image does not change with it
    c_text = {n: a for n, a in sorted(csyms.items(), key=lambda kv: (kv[1], kv[0]))
              if pages.C_LOAD <= a < csyms["__text_end"] and not n.startswith("__")}
    out = {"content": None, "edits": edits, "layout": layout, "c_text_symbols": c_text,
           "chunk": {"load": pages.LOAD, "code": chunk},
           "c_chunk": {"load": pages.C_LOAD, "code": cimage},
           "machines_chunk": {"load": MCHUNK, "code": bytes(mchunk)}}
    if flt_cf.NEW_FILTERS:
        fbuilt = flt_cf.compose(content, edit, assemble)
        layout.update(fbuilt["layout"])
        out["flt_chunk"] = fbuilt["chunk"]
    out["content"] = bytes(content)
    return out
