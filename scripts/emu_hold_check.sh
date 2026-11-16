#!/usr/bin/env bash
# DRONE's HOLD on the real ISR path in the ColdFire emulator (2026-11-10): the build's snapshot (a booted
# 800M-instruction one: ports3/boot_snap.sh NAME TREE), DRONE on track 1, HOLD turned on, a played key down
# and up, the same key again, HOLD turned off; the frames the ISR builds are checked by check_hold_frames.py.
#   emu_hold_check.sh DIR   (DIR: the folder the emulator driver writes the frames to)
# The emulator driver is run as ports3/emu47.sh runs it (docker bench, scripts/emu_waverider_menu.py):
#   --steps "$STEPS" --png-dir DIR
# HOLD off is a poke of the track's HOLD value (sound + 20 + 2 x 40, big-endian: 0000); the emulator's
# `turn` does not turn negative.
STEPS="func-src,wait:20,down,down,down,down,down,yes,wait:20,tap:2,wait:10,tap:2,wait:10"
STEPS="$STEPS,turn:6:60,wait:10,press:25,wait:5,frame:on_f1,frame:on_f2,release:25,wait:5,frame:on_f3,frame:on_f4,press:25,wait:5,frame:on_f5,frame:on_f6,release:25,wait:5,frame:on_f7"
STEPS="$STEPS,press:25,wait:5,frame:rel_f1,frame:rel_f2,release:25,wait:5,frame:rel_f3,poke:\$KIT_HOLD:0000,frame:rel_f4,frame:rel_f5"
STEPS="$STEPS,press:25,wait:5,frame:off_f1,frame:off_f2,release:25,wait:5,frame:off_f3"
echo "$STEPS"
# KIT_HOLD: the kit pointer ([0x800052a0], read with mem:) + 52 + 20 + 80
python3 "$(dirname "$0")/check_hold_frames.py" "${1:?DIR}"
