"""emu_wish_isr.py BUILD SNAPSHOT STOCK [PERIODS]: the ColdFire's audio interrupt never reaches the wishes table
(2026-11-21, csrc/wishes/table.c's queue: a copy that finds the lock taken is queued for the holder, which is safe only
if the holder can never be interrupted by a copy that needs the table to stay put, and the matrix's per-period path
must not read the table at all).

The coupled emulator, the ColdFire alone (dsp=False: the ISR, the sequencer, the UI), idle, then a note held on four
trig keys. While the audio ISR runs, it watches:
  - every entry into our memcpy and memset stubs (their size: a sound is 1,163 B; wish_copy / wish_carry need one),
  - every entry into the table's code (wish_give, wish_find, wish_get, wish_put),
  - every read or write of the table's RAM (dnfw.waverider.pages WISH_RAM, WISH_BYTES) and of its lock words, except
    the stub's own read of wish_n (csrc/wishes/hooks.S tests the count before the size; counted apart).
Positive control, outside the ISR: one sound copied through the stub (as stock's kit copy does) must be seen by the
same hooks (a stub entry of a sound's size, table code entered, table RAM touched, wish_copies + 1 when the table
holds anything). Exit 0 when the ISR touched nothing and the control saw its copy; 1 otherwise. A probe for the
attenuverter follow-ups, not a gate step."""
import json
import struct
import sys

SOUND = 1163
KIT_PTR = 0x800052A0


def main() -> int:
    sys.path.insert(0, "scripts")
    import emu_coupled as EC
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_READ

    from dnfw.waverider import pages as PG

    build, snap, stock = sys.argv[1:4]
    n_idle = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    lay = json.loads(open("src/dnfw/mods/waverider_code.json").read())["layout"]
    c = EC.Coupled(build, snap, stock, verbose=True, dsp=False)
    state = {"isr": False}
    cnt = {"isr_calls": 0, "isr_cpy": 0, "isr_cpy_max": 0, "isr_set": 0, "isr_code": 0, "isr_mem": 0, "isr_n_reads": 0,
           "ui_cpy_sound": 0, "ui_code": 0, "ui_mem": 0}
    first = []

    def side():
        return "isr" if state["isr"] else "ui"

    def on_stub(uc, addr, size, user):
        sp = uc.reg_read(c.K.UC_M68K_REG_A7)
        n = struct.unpack(">I", bytes(uc.mem_read(sp + 12, 4)))[0]
        if state["isr"]:
            cnt["isr_cpy" if user == "cpy" else "isr_set"] += 1
            cnt["isr_cpy_max"] = max(cnt["isr_cpy_max"], n) if user == "cpy" else cnt["isr_cpy_max"]
        elif user == "cpy" and n >= SOUND:
            cnt["ui_cpy_sound"] += 1

    def on_code(uc, addr, size, user):
        cnt[side() + "_code"] += 1
        if state["isr"] and len(first) < 8:
            first.append(("code", user))

    def on_mem(uc, access, addr, size, value, user):
        if state["isr"] and access == UC_MEM_READ and addr == lay["wish_n"]:
            cnt["isr_n_reads"] += 1             # the stub's own test of the count (hooks.S: tst.l wish_n), no more
            return
        cnt[side() + "_mem"] += 1
        if state["isr"] and len(first) < 8:
            first.append(("mem", hex(addr), size))

    uc = c.uc
    uc.hook_add(UC_HOOK_CODE, on_stub, "cpy", begin=lay["wish_memcpy_stub"], end=lay["wish_memcpy_stub"])
    uc.hook_add(UC_HOOK_CODE, on_stub, "set", begin=lay["wish_memset_stub"], end=lay["wish_memset_stub"])
    for name in ("wish_give", "wish_find", "wish_get", "wish_put"):
        if name in lay:
            uc.hook_add(UC_HOOK_CODE, on_code, name, begin=lay[name], end=lay[name])
    watch = [(PG.WISH_RAM, PG.WISH_RAM + PG.WISH_BYTES - 1)]
    for name in ("wish_busy", "wish_n", "wish_queued", "wish_q_max"):
        if name in lay:
            watch.append((lay[name], lay[name] + 3))
    for lo, hi in watch:
        uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, on_mem, None, begin=lo, end=hi)

    call0 = c.call

    def call(fn, *a, **k):
        if fn == EC.ISR:
            state["isr"] = True
            cnt["isr_calls"] += 1
        try:
            return call0(fn, *a, **k)
        finally:
            state["isr"] = False

    c.call = call
    c.periods(n_idle)
    P = c.panel.panelin

    def held(code, on, n=3):
        c.machine.pc = (P.press if on else P.release)(c.machine.m, c.panel.profile, *divmod(code - 1, 8))
        c.periods(n)

    held(18, True)                                    # KEYBOARD on, then four trig keys held
    held(18, False)
    for code in (33, 35, 37, 38):
        held(code, True, 60)
        held(code, False, 30)
    c.periods(n_idle)

    # the positive control, outside the ISR: track 1's sound copied over track 4's, as stock's kit copy does
    before = {k: cnt[k] for k in ("ui_cpy_sound", "ui_code", "ui_mem")}
    copies0 = c.long(lay["wish_copies"])
    kit = c.long(KIT_PTR)
    c.call(lay["wish_memcpy_stub"], kit + 52 + SOUND * 3, kit + 52, SOUND)
    control = {k: cnt[k] - before[k] for k in before}
    control["wish_copies"] = c.long(lay["wish_copies"]) - copies0
    control["wish_n"] = struct.unpack(">H", c.read(lay["wish_n"], 2))[0]
    for name in ("wish_reentered", "wish_queued", "wish_q_max", "wish_copies", "wish_carries", "wish_clears"):
        cnt[name] = c.long(lay[name])
    cnt["halt"] = c.halt
    cnt["control"] = control
    cnt["isr_first"] = first
    isr_clean = cnt["isr_calls"] > 0 and not (cnt["isr_code"] or cnt["isr_mem"] or cnt["isr_cpy_max"] >= SOUND)
    seen = control["ui_cpy_sound"] == 1 and control["ui_code"] > 0 and control["ui_mem"] > 0 \
        and (control["wish_copies"] == 1 or control["wish_n"] == 0)
    print("RESULT " + json.dumps(cnt), flush=True)
    print(f"{'ok  ' if isr_clean else 'FAIL'}  the audio ISR ({cnt['isr_calls']} calls) never entered the table's code "
          f"({cnt['isr_code']}), touched its RAM or lock ({cnt['isr_mem']}; the stub's reads of wish_n "
          f"{cnt['isr_n_reads']}), or copied a sound (largest "
          f"{cnt['isr_cpy_max']} B)", flush=True)
    print(f"{'ok  ' if seen else 'FAIL'}  control: a sound copied outside the ISR is seen by the same hooks {control}",
          flush=True)
    return 0 if isr_clean and seen and not c.halt else 1


if __name__ == "__main__":
    sys.exit(main())
