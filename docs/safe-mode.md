# SAFE MODE (2026-11-21)

If the Wishes firmware stops the DN2 from starting (a crash or a freeze before the UI has run for 30 s), the next
start comes up in **SAFE MODE**: stock Digitone II OS 1.12's own ColdFire code, byte for byte, with no DSP program
(no audio) and an empty project. Its job is to let the User send a fixed firmware with Elektron Transfer over USB
(the stock update, `OsUpgradeStart / Write / End`), about a minute, instead of the Early Start-up Menu over DIN MIDI
(about 12 minutes). The Early Start-up Menu stays the last resort.

Design and the User's answers: `scratch/safe-boot-design.md`; the stage 1 study with addresses and evidence:
`scratch/safe-boot-stage1.md`.

## How a boot goes

| moment | what runs | what it does |
|---|---|---|
| the loader, before `main` (caches off, before the BSS clear) | the kernel's init (`csrc/safemode/kernel.c` `sm_init`; the kernel is the area's first CODE chunk) | reads the RAM mark at `0x476F8000` and wipes it (a mark lasts one boot). A SAFE mark of this build: SAFE MODE (below) |
| the eMMC-ready point `0x400cf0f2`, before the DSP upload and before any UI, MIDI or +Drive task | `sm_late` (`csrc/safemode/normal.c`, from `dn7_late`) | reads the boot record (+Drive sector `0x6E0300`). The last boot never became healthy (`pending`) and `safe_tries < 2`: `safe_tries + 1` written, the SAFE mark left (through the uncached alias), our soft reset. Otherwise `pending = 1` written |
| every UI pass | `sm_poll` (from `wr_poll`) | after 3,630 panel ticks (30 s on the unit): `pending = 0`, `safe_tries = 0` written once. In the first ~3 s: STOP held alone without a break for 1 s (`SM_STOP_HOLD`, 121 ticks; stock's own button state `0x445a2e30`: STOP and no other button, FUNC included; not the maintenance combination; a tap, e.g. STOP to stop a playing pattern, does nothing here, main 2026-11-21) -> SAFE mark, `pending = 0` written, our soft reset |

Everything fails open: no kernel (its head's magic), the +Drive not up, a failed read, a bad record or mark, another
build's record or mark: a normal boot.

**The record** (`0x5FFB00` since v0.69.2, moved once from `0x6E0300` at the first boot's eMMC-ready point; 512 B, the first 32 used): `DN2B`, version 1, the build id, pending, safe_tries, entries,
a CRC-32. The build id is a CRC-32 of the build's MAIN OS and area (`dnfw.mods.safemode`), so a new firmware starts
from a fresh record: flashing a fix never inherits the old build's failures. ERASE MOD DATA erases it (job 12).

## SAFE MODE

The kernel's init, with a SAFE mark of this build:

1. checks the unpatch table's CRC-32 and that it decodes, and that each override site will hold stock's bytes once
   the table is applied; any failure leaves this boot normal (nothing written);
2. applies the table: stock 1.12's bytes over every byte the build changed in MAIN OS (1,240 runs, 9,142 B on
   up-v067), **except** the two runs the loader is running in: the start-up call `0x4000053e` (the loader returns
   to `0x40000544`; stock's bytes there would be half a `bsr`, an illegal instruction) and the loader's cave
   `0x4028dfae`. Neither is reached again after `main`;
3. writes the overrides:
   - **O1** `0x400cf73a` (the DSP uploader's `jsr 0x40136820`, stock's aPLib) -> `jsr sm_refuse7`, which answers
     `0x100000`: the uploader takes its stock error path, the DSP gets no program, and stock's aPLib never reads our
     LZMA section 7;
   - **O2** `0x4002e464` (the UI loop's isDirty) -> `jsr sm_isdirty`, where the question opens (below);
   - **O4** `0x400bb4a0` (`move.l %d0,0x405ce858`) -> nops: the empty project is not written over the saved working
     state (the User's C10 choice b, 2026-11-21);
   - boot flag bit 0 (`0x40287a60`, the Early Start-up Menu's EMPTY RESET): stock does not read the working project
     from the +Drive and starts with an empty project;
4. zeroes the init entry of every CODE chunk after its own (none of ours has one today; the rule stands for any
   that does).

SAFE MODE writes nothing to the +Drive. The update RPC is stock's.

**Leaving it:** a flash (the new build's record is fresh); NO to the question (a NORMAL-ONCE mark and a restart:
one normal boot whose earlier failures are not counted); or power cycles: each one with the record still pending
comes back to SAFE MODE until `safe_tries` reaches 2, then the boot is normal.

**The question** (`csrc/safemode/question.c`, O2): at the first UI pass where MainScreenView is up, the kernel opens
stock 1.12's own ConfirmWindow (`0x40112d0e`, class `0x4020671c`), built as stock builds "SAVE ALL ...?" and
"UPGRADE OS NOW?" and opened over MainScreenView as `rec.c`'s NAME screen is (`0x4011cb9e`):

    LAST START FAILED              (STOP HELD AT START, after the STOP entry)
    START SAFE MODE? Y/N

The window takes YES and NO itself and calls the kernel's answer:
- **YES**: the window closes, the stock UI stays, in SAFE MODE.
- **NO**: the NORMAL-ONCE mark (kind 2, why 3) through the uncached alias, then our soft reset: one normal boot whose
  earlier failures are not counted (`sm_late` writes `pending = 1`, `safe_tries = 0`). Nothing is written to the
  +Drive in SAFE MODE.
- **No answer**: SAFE MODE goes on with the question up.

Measured in the emulator on stock 1.12's UI (`scripts/emu_safemode_question.py`, 2026-11-21): the window opens by
itself, from the kernel, last on MainScreenView's screen, drawn over the page; YES takes it down with no reset; NO
leaves the NORMAL-ONCE mark of this build and writes SOFTRST.

## RAM and room

| | |
|---|---|
| RAM | `0x476F8000..0x47700000` (`pages.SM_RAM`): the mark, then the kernel chunk at `0x476F8100` (1,792 B of code + the table) |
| image | +5,353 B on up-v067 (75,334 -> 69,981 B free in the 2 MiB USB buffer): the table, the kernel with its question, `normal.c` |
| CPU | 0 per audio frame; until healthy, a few instructions a UI pass |
| +Drive | one 512 B read and one write per boot, one write at healthy |

## Gate steps (brick-risk, blocking)

- **`safeboot-table`** (static, `scripts/safeboot_table.py`): the kernel is the first CODE chunk, its code the
  sources' (`scripts/gen_safemode_code.py --check` runs in `code-fresh` too), no BSS; the head's table, CRC and build
  id; the table applied to the build's MAIN OS gives stock 1.12 except exactly the two never-restored runs; every
  override site stock under it; the start-up call and the cave hold the platform's loader.
- **`safeboot`** (emulator from reset, `scripts/emu_safeboot.py`, the +Drive played, the uncached alias as the same
  memory): a, the normal boot's record; b, a pending record -> the SAFE mark and a reset, then the SAFE boot (MAIN OS
  = stock 1.12 + the declared bytes right after the loader, no DSP push, no +Drive write, no fault, the UI); e,
  hostile marks and records -> normal boots; t, the mark lost across resets -> two resets, then a normal boot.

  Also in the step: f (in b's SAFE boot), the empty project: the working project's +Drive read (`0x400f21e4`) never
  reached, stock's empty project built, the MRAM flag never set (O4), no "Write project MRAM" job, no block write;
  n, a NORMAL-ONCE mark (NO) -> a normal boot that counts afresh, the SHARC programmed, and a SAFE mark of the STOP
  entry -> SAFE MODE with reason 2. Then the question (`scripts/emu_safemode_question.py`) on stock 1.12's UI
  snapshot: a from-reset run never reaches the UI loop's isDirty site (no MainScreenView by 1.1 G instructions,
  measured), so the snapshot is put in the state the kernel's init leaves (the kernel chunk at `SM_LOAD`, `sm_live`
  SAFE, O2 written) and driven through the panel's own bytes.

  The STOP entry (`scripts/emu_safemode_stop.py`), the build installed over the same snapshot as
  `emu_waverider_menu.py` installs it, the +Drive played: STOP alone writes the record (pending 0, entered 1) and the
  SAFE mark (why 2) and resets; FUNC + STOP and no key do nothing. FUNC never reaches the UI queue as a key item, so
  `rec.c`'s held keys cannot see it (measured: FUNC + STOP entered before the check read stock's button state).
  Part c, the update RPC (`scripts/emu_safemode_rpc.py`, below), with 4 chunks.

## The update RPC in SAFE MODE (part c)

Measured 2026-11-21 on stock 1.12's UI snapshot, stock as it is and in SAFE MODE's state (the kernel, `sm_live` SAFE,
O2: SAFE MODE's own question up and unanswered), side by side, identical:

| request (Transfer's own bytes, `scratch/flash-capture`) | reply |
|---|---|
| Ping `0x01` | `0x81`, "Digitone II" |
| SoftwareVersion `0x02` | `0x82`, "1.12" |
| OsUpgradeStart `0x50` (2,549,152 B, "sysex", flag 1) | `0xD0`, status 0: accepted |
| OsUpgradeWrite `0x51`, 2,048 B chunks of stock 1.12's .syx | `0xD1`, the next offset (`0x800`, `0x1000`, ...), status 0 |

How the requests go in: each whole SysEx message is handed to stock's USB MIDI receive callback `0x4011f3c0(bytes,
len)`, which posts it to the MIDI task's queue; the MIDI task routes it in its own context, so the RPC handler can post
its job to the main application and wait for the answer. Three emulator matters, none of them the firmware's:
- digikit's `unblock` fakes every semaphore wait whose poster it cannot see; the RPC job's answer comes through a
  semaphore on the MIDI task's stack (`0x40129db2`), so the probe adds each one to digikit's exception set as it is
  pended. Faked, the wait returns at once and the answer is "Could not initiate OS upgrade", in stock too (that was the
  earlier "refused" result: the harness, not SAFE MODE);
- the first message wakes the parked MIDI task (a call from the snapshot's context); every later one is entered from
  the MIDI task's own loop;
- stock's sender returns at once after the capture (`--sender-returns`): the emulator has no USB host.

The chunk CRC is Transfer's: reflected CRC-32 with the register at 0 and the result inverted (`zlib.crc32(data,
0xFFFFFFFF)`); plain `zlib.crc32` draws `0xD1` with status 2 (bad CRC). `0xD1` is `op, u32 next offset, status`.
Transfer's capture has no `0x52`; it ends with the last chunk.

Not yet measured: the whole file (1,245 chunks) and the "UPGRADE OS NOW?" question after the last chunk; on the unit,
Transfer itself.

## Open

- The update RPC from reset: stage 1's harness got no reply, in the control too. Device `0x10` routes every command to
  `0x40120c0c` (USB or port 4 only), then the RPC entry `0x40126cec`, which drops the request unless the byte
  `0x445fb350` is set; only the main application's start-up sets it (`0x4002e9aa`). A from-reset run never reaches it
  [read]; on the UI snapshot it is 1 and the RPC answers (above).
- The whole upload and its "UPGRADE OS NOW?" in SAFE MODE (emulator, a longer run), then Transfer on the unit.
- Whether the panel reports a key held since power-on (the STOP entry): only the unit can say.
- On the unit: that a soft reset keeps `0x476F8000` (the wishes record above it is kept over a restart), the screen,
  and stock 1.12 sent with Transfer from SAFE MODE (the User; Claude never flashes).
