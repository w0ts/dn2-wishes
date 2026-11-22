"""The oscilloscope's frames drawn alone and never queued behind the panel UART (csrc/scope/scope.c, 2026-11-17): the facts
its emulator check (scripts/emu_scope.py, gate step scope) relies on."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCOPE = (ROOT / "csrc/scope/scope.c").read_text()
PAGE = (ROOT / "csrc/waverider/page.c").read_text()


def _function(text, head):
    i = text.index(head)
    return text[i:text.index("\n}\n", i)]


def test_stock_returns_in_d0_are_read_as_words():
    # panel_diff returns the new FRONT in %d0: declared as a pointer, gcc reads %a0 (the null canvas of sc1)
    assert "#define PANEL_DIFF ((u32 (*)(void))0x40131FD2u)" in SCOPE
    assert "LOOP_BUF = (u8 *)PANEL_DIFF();" in SCOPE
    assert "#define IS_DIRTY   ((u8 (*)(void *))0x4011D5D4u)" in SCOPE


def test_a_frame_never_waits_for_the_uart():
    poll = _function(SCOPE, "void scope_poll(void *screen)")
    assert poll.index("uart_backlog() >= UART_IDLE") < poll.index("SET_DIRTY(screen);")
    assert poll.index("uart_backlog() >= UART_IDLE") < poll.index("PANEL_DIFF()")
    assert re.search(r"#define UART_IDLE\s+128u", SCOPE)


def test_alone_only_over_the_frame_the_scope_ended():
    poll = _function(SCOPE, "void scope_poll(void *screen)")
    assert "!scope_back || FB_BACK != scope_back || (IS_DIRTY(screen) & 0xFFu)" in poll
    screen = PAGE[PAGE.index("void wr_screen("):PAGE.index("int wr_poll(")]
    assert screen.count("scope_end(canvas,") == 2
    # (2026-11-18: the DEST popup, csrc/matrix/dest_pop.c, covers the screen as the routes popup does)
    assert "scope_end(canvas, drew && !wpop_shown() && !mxp_visible() && !ldp_visible() && !ovw_visible());" in screen


def test_the_drawing_sets_bytes_not_pixels():
    draw = _function(SCOPE, "void scope_draw(void *c)\n{")
    assert "SET_PIXEL" not in draw and "clear_strip(b, 18, 127);" in draw
    assert "vspan(b, X0 + x, span_lo[x], span_hi[x]);" in draw
    # 2026-11-18 (the User: "i still get cpu in osclillo"): a frame drawn alone writes only the trace's changed columns,
    # by whole bytes, and draws no label and no page dots (they are on the frame it is drawn over)
    alone = _function(SCOPE, "static void scope_trace_alone(u8 *b)\n{")
    assert "SET_PIXEL" not in alone and "wg_label" not in alone and "PAGE_DOTS" not in alone
    assert "lo[x] != span_lo[x] || hi[x] != span_hi[x]" in alone
    assert "scope_trace_alone(front);" in _function(SCOPE, "void scope_poll(void *screen)")
    assert "scope_draw(" not in _function(SCOPE, "void scope_poll(void *screen)")


def test_the_title_message_running_out_redraws():
    # 2026-11-18: "WAVEFORM" stayed on the bar after its message ran out (frames drawn alone never touch the bar)
    poll = _function(SCOPE, "void scope_poll(void *screen)")
    assert "(title_msg_drawn && !title_msg_up())" in poll
    assert "title_msg_drawn = scope_back ? title_msg_up() : 0;" in _function(SCOPE, "void scope_end(void *canvas, int clean)")


def test_auto_is_the_default_and_the_settings_are_kept():
    # 2026-11-18 (the User: "auto should be default for oscilator and we should rfememebr the values set for it")
    assert 'int scope_gain __attribute__((section(".data"))) = GAINS;' in SCOPE
    assert 'int scope_auto __attribute__((section(".data"))) = -1;' in SCOPE
    # kept in jump.c's settings sector, in flags bits no other setting uses (jump.c's own bits 0, 1; LIVE SELECT 2;
    # the VOICE BUDGET 3)
    assert "#define SET_GAIN_SHIFT 4" in SCOPE and "#define SET_SPAN_SHIFT 8" in SCOPE
    assert "#define SET_LIVE_OFF 4u" in (ROOT / "csrc/msel/live.c").read_text()
    assert "#define SET_BUDGET_OFF 8u" in (ROOT / "csrc/load/load.c").read_text()
    jump = (ROOT / "csrc/jump/jump.c").read_text()
    assert "#define SET_OWN (SET_JUMP | SET_REMOTE_OFF)" in jump and "set_bits = sector[2] & ~SET_OWN;" in jump
    frm = _function(SCOPE, "void scope_settings_from(u32 bits)")
    assert "g >= 1u && g <= GAINS ? (int)g - 1 : GAINS" in frm      # out of range: AUTO
    assert "z >= 1u && z <= ZOOMS ? (int)z - 1 : ZOOM_DEFAULT" in frm
    # written only after the sector was read (jmp_poll would write over the other settings unread)
    assert "save_due && jmp_loaded" in _function(SCOPE, "static void settings_poll(void)")


def test_the_gate_runs_it():
    gate = (ROOT / "scripts/ship_gate.py").read_text()
    assert '"scripts/emu_scope.py"' in gate and '"--proof"' in gate and '"test/test_scope_alone.py"' in gate


def test_gains_below_x1_by_shifts():
    # 2026-11-17 (the User: "autozoom vertical (below X1)"): x1/8..x16 and AUTO, labels in the 4-character slot
    texts = re.search(r"GAIN_TEXT\[GAINS \+ 1\] = \{([^}]*)\}", SCOPE).group(1)
    names = re.findall(r'"([^"]*)"', texts)
    assert names == ["x1/8", "x1/4", "x1/2", "x1", "x2", "x4", "x8", "x16", "AUTO"]
    assert all(len(n) <= 4 for n in names)
    # 2026-11-18 (the User: "just put 'auto', not A4 A8 etc"): G's label is GAIN_TEXT's, AUTO says AUTO at any gain
    assert "AUTO_TEXT" not in SCOPE
    assert "wg_label(c, 6, GAIN_TEXT[scope_gain]);" in _function(SCOPE, "void scope_draw(void *c)\n{")
    ypix = _function(SCOPE, "static int ypix(s16 v, int k)")
    assert "/" not in ypix.split("{", 1)[1]          # no divide per sample
    assert re.search(r"#define ZOOM_IN_HOLD \d+", SCOPE)


def test_the_gain_model_matches_v1_at_v1s_gains():
    # emu_scope's model at shift k is v1's v * g * HALF / 32768 (truncated toward zero) for g = 2^k, k 0..4
    src = (ROOT / "scripts/emu_scope.py").read_text()
    assert "abs(q) * 2 ** k // 32768 if k >= 0 else abs(q) // (32768 << -k)" in src
    for k in range(5):
        for v in (-32768, -16385, -16384, -1, 0, 1, 1637, 16383, 32767):
            q = v * (1 << k) * 20
            want = int(q / 32768)
            t = abs(v * 20) * 2 ** k // 32768
            assert (t if v >= 0 else -t) == want, (k, v)


def test_the_tap_reads_only_before_a_frame():
    # 2026-11-18: the ring is filled afresh in the 8 x D blocks (and two) before a frame is due; earlier blocks unread
    tap = _function(SCOPE, "void scope_tap(u32 h)")
    assert re.search(r"#define LEAD\(d\)\s+\(8u \* \(d\) \+ 2u\)", SCOPE)
    assert "if ((int)(next_draw - FRAMES_NOW) > (int)LEAD(d)) {" in tap
    assert tap.index("LEAD(d)") < tap.index("UI_TRACK")
    # 256 samples at every Dth of 32 a block: LEAD blocks always hold them
    for d in (1, 2, 4, 8, 16, 32):
        assert (8 * d + 2) * 32 // d >= 256


def test_a_long_trig_opens_it_and_amp_has_two_pages():
    # 2026-11-19 (the User): the scope opens on [TRIG] held a second (the overviews' own constant, ovw.c LONG_TICKS),
    # over stock's TRIG page only; it is no longer an AMP page: [AMP] steps AMP 1/2 -> 2/2 (ENV2) -> 1/2
    amp = (ROOT / "csrc/waverider/amp_pages.h").read_text()
    assert re.search(r"#define AMP_PAGES 2\b", amp) and re.search(r"#define AMP_SCOPE AMP_PAGES\b", amp)
    ovw = (ROOT / "csrc/inserts/ovw.c").read_text()
    poll = _function(ovw, "void ovw_poll(void *screen)")
    assert "ticks_since(fx_at) >= LONG_TICKS" in poll
    assert poll.index("ticks_since(fx_at) >= LONG_TICKS") < poll.index("hk == K_TRIG") < poll.index("scope_long();")
    assert "#define K_TRIG        1u" in ovw and "return code >= K_TRIG && code <= K_MOD;" in ovw
    # the press with the scope up is not watched (it closes the scope, scope_pop)
    assert "(code == K_TRIG && scope_visible()) ? OWN_STOCK : OWN_WATCH" in ovw
    assert "#define TRIG_PAGE_VTABLE 0x401E2180u" in SCOPE
    opener = _function(SCOPE, "int scope_long(void)")
    assert "!trig_page()" in opener and "amp_sub = AMP_SCOPE;" in opener
    assert "PAGE_DOTS" not in _function(SCOPE, "void scope_draw(void *c)\n{")
    assert "amp_open((amp_sub + 1) % AMP_PAGES);" in SCOPE
