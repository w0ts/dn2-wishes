# The test channel's protocol (version 1)

The wire format of the commands a **test build** answers over USB SysEx, so anyone can write a client.
`tools/dn2tools/src/dn2tools/protocol.py` is its executable form; `tools/dn2tools/tests/test_channel.py`
holds the two together (golden bytes, and the firmware's rules read from `csrc/devtest/*.c`). The firmware
is `csrc/devtest/devtest.c` (commands), `csrc/devtest/whitelist.c` (the only words it writes, the only
ranges it reads), dispatched from `csrc/sampler/link.c` `smp_rx`.

## Framing

    request  F0 00 20 3C 7D 01 <pack7( u16 seq, u8 cmd, args... )> F7
    reply    F0 00 20 3C 7D 01 <pack7( u16 seq, u8 cmd | 0x80, u8 status, data... )> F7

- USB only (the unit ignores this channel on its DIN ports). Big-endian numbers.
- `pack7`: each group of up to 7 bytes is preceded by one byte holding their top bits, bit 6 for the first
  byte of the group, bit 0 for the seventh; the bytes follow with their top bit cleared.
- `seq` is the host's; the reply echoes it. The unit answers every request it understands once, from the
  MIDI input task; it never answers from the audio interrupt.
- Stock firmware does not answer at all (a timeout). A build without the test channel answers commands
  33..42 with status 2. Read BUILDINFO first.
- The longest reply's data is 156 bytes (the firmware's reply buffer is 160 bytes with the header).

## Statuses

| status | meaning |
|---|---|
| 0 | ok |
| 2 | bad arguments, an unknown sub-command, or a command this build does not have |
| 3 | not armed (KEY) |
| 4 | refused: the destructive blacklist, or a wrong / stale / spent nonce (ARM) |
| 5 | busy: the key queue (16 events) has no room for the whole message |
| 6 | outside the whitelist (PEEK range, SWITCH bounds) |

## Commands

The channel's other commands (1..31: the sample link's image writes, the +Drive library, ERASE MOD DATA)
can change the unit's storage. **dn2tools refuses to encode anything but 1, 32 and 33..42.** A client of
your own should do the same.

### 1 HELLO, 32 TLM (from the telemetry build)

HELLO → `u16 link protocol (7)`, then the link's numbers. TLM → the 32-word telemetry frame,
`docs/device-tests.md` (word 0 `'TLM1'`, word 1 the build id).

### 33 BUILDINFO

args: none → data (36 bytes):

| offset | type | |
|---|---|---|
| 0 | 4 bytes | `DTB1` |
| 4 | u16 | test channel protocol (1) |
| 6 | 2 bytes | OS version, BCD (`01 12`) |
| 8 | u32 | capability bits: 0 TLM, 1 BUILDINFO, 2 SWITCH, 3 PEEK, 4 COUNTERS, 5 TRACE, 6 STATE, 7 SCREEN, 8 ARM, 9 KEY |
| 12 | u8 | number of switches |
| 13 | u8, u8 | screen width, height (128, 64) |
| 15 | u8 | screen chunks (8) |
| 16 | 16 bytes | build label, NUL padded (`remoteui-1`) |
| 32 | u32 | the panel tick's rate the firmware measured (ticks a second; 1000 until the audio runs) |

### 34 SWITCH

Whitelisted RAM words the firmware reads at run time (`whitelist.c`): today `HOLD` (DRONE's HOLD latch,
0/1, default 1), `LABELS` (the load labels' events, 0/1, default 1), `ARMTIME` (30..1800 s, default 300).
They reset to their defaults at power-on.

| sub | args | data |
|---|---|---|
| 0 INFO | `u8 0, u8 k` | `u8 k, char name[8], u32 value, u32 min, u32 max, u32 default` |
| 1 GET | `u8 1` | `u8 n, u32 value[n]` |
| 2 SET | `u8 2, u8 k, u32 value` | `u8 k, u32 value now` (status 6 if out of bounds: unchanged) |

Every SET is logged in the trace.

### 35 PEEK

args `u32 address, u8 length (1..128)` → data `u32 address, bytes`. Only inside the whitelist's ranges
(0x40000000..0x48000000, 0x80000000..0x80010000, and since remoteui-4 the TDM receive window
0x4E6E7100..0x4E6E8100), else status 6.

### 36 COUNTERS

Ticks everywhere in this protocol are the panel tick **unwrapped** (the firmware's own counter wraps at 4,096).

args `u8 reset (0 read, 1 read then zero)` → data `u8 n (12), u32 counter[n], u32 trace total, u32 tick,
u32 audio frames`. Counters: commands, refused, keys down, keys up, encoder events, arms, disarms,
auto-disarms, screen snapshots, torn copies, switch writes, the DSP load's maximum (percent) since the reset.

### 37 TRACE

args `u32 since` → data `u32 total, u32 first, u8 n (<= 16), n x (u32 tick, u32 event)`. The ring keeps the
last 64 events; `since` older than that starts at the oldest kept. `event = kind << 24 | a << 16 | b`:

| kind | | a | b |
|---|---|---|---|
| 1 | ARM | destructive flag | |
| 2 | DISARM | 0 asked, 1 timed out | |
| 3 | DOWN | key code | hold ms |
| 4 | UP | key code | |
| 5 | ENC | encoder | signed delta (16 bits) |
| 6 | SWITCH | switch | value (low 16 bits) |
| 7 | REFUSED | key code | 1 SETTINGS, 2 not with FUNC held, 3 FUNC over a held key |
| 8 | RESET | | |
| 9 | TORN | the copy's try | |

### 38 STATE

args none → data (88 bytes): `u32 audio frames, u32 tick, u32 ticks a second, u8 armed, u8 flags (bit 0
destructive), u16 seconds until auto-disarm, u32 held keys (codes 1..32, bit code-1), u32 held keys (codes
33..54, bit code-33), u8 queued events, u8 panel state[7] (each channel's 8-bit mask as the UI last saw
it), i8 machine type[16] (each track's sound, -1 none), u8 insert type[16][2], u32 front buffer address,
u32 back buffer address`.

### 40 SCREEN

args `u8 flags (bit 0 the frame being drawn instead of the one on the glass, bit 1 take a new frame), u8 chunk
(0..7, or 255 for no data)` → data `u8 chunk, u8 chunks (8), u8 tries, u8 whole, u32 frame seq, u32 hash, then 128 bytes`
(none for chunk 255).

The panel is double-buffered: after each swap one buffer (behind `0x402a10cc`) holds the frame on the glass,
untouched until the next swap, while the UI draws the next one into the other (`0x402a10c8`). The default is the
glass's: a copy of the one being drawn can be a frame paused half drawn. The unit copies the whole buffer (1,024
bytes) when asked for a new frame (or the other buffer), checks
the copy (the pointer did not move and a second read hashes the same; up to 4 tries; `whole` 0 if none
agreed) and serves that copy in 8 chunks until the next new frame. `hash` is FNV-1a 32 over the 1,024
bytes; a mirror polls `chunk 255, new frame` and fetches the chunks only when the hash changed.

Layout: 128 x 64, 1 bit a pixel, column-major: pixel (x, y) is bit `y % 8` of byte `8 x + 7 - y / 8`;
1 is lit.

### 41 ARM

Key injection is disarmed at power-on.

| sub | args | data |
|---|---|---|
| 0 ASK | `u8 0` | `u32 nonce`, then the status below |
| 1 CONFIRM | `u8 1, 'A' 'R' 'M' '!', u32 nonce, u8 flags (bit 0 destructive)` | status below; status 4 if the nonce is wrong, older than 10 s or already tried |
| 2 DISARM | `u8 2` | status below |
| 3 STATUS | `u8 3` | status below (and, armed, it counts as a command) |

Status data: `u8 armed, u8 flags, u32 ARMTIME`. The unit disarms itself ARMTIME seconds after the last
ARM or KEY command. Disarming lets every injected key go and drops the queue.

### 42 KEY

args `u8 n (1..16), n x (u8 kind, u8 code, u16 at ms, u16 value)`; all checked before any is queued;
data `u8 queued, u8 room left` (status 2 or 4: `u8 index of the bad event`; status 5: `u8 room`).

| kind | code | value |
|---|---|---|
| 1 PRESS | key code 1..54 | hold ms 1..10000: the unit lets the key go after it |
| 2 ENCODER | encoder 0..8 (A..H, LEVEL) | signed delta -30..30, not 0 |
| 3 RELEASE | key code | |

`at` (0..10000 ms) delays the event from the message's arrival. The unit plays due events in arrival order
once a UI pass, through the panel's own handlers (the same path as the panel's UART bytes), with
interrupts masked for the call. A key held on the panel stays held: the injected bit is set in (or cleared
from) the channel's real state.

Key codes: 1 TRIG, 2 SRC, 3 FLTR, 4 AMP, 5 FX, 6 MOD, 7 PRESET, 8 SETTINGS, 9 TEMPO, 10 YES, 11 UP, 12 NO,
13 LEFT, 14 DOWN, 15 RIGHT, 16 TRK, 17 FUNC, 18 KEYBOARD, 19 RECORD, 20 PLAY, 21 STOP, 22 PAGE, 23 PTN,
24 SONG, 25..40 the trigs 1..16, 41..48 the encoder pushes A..H, 49 LEVEL, 50 VOICE, 51 ARP, 52 PLUS,
53 STACK, 54 MINUS. Codes 1..48 are panel channel `(code-1)/8`, bit `(code-1)%8`; 49..54 channel 6 bits
1, 0, 4, 5, 6, 7.

**The firmware's blacklist** (unless armed destructive): SETTINGS is refused at the message (status 4)
and again when due; with FUNC held only 1..6, 11, 13, 14, 15, 20, 21, 22, 41..48 may go down; FUNC may not
go down while another key outside that set is held. A refusal when due is counted and traced, not
answered (the message was answered when it was queued).
