"""Compile Waverider's C page renderer (`csrc/waverider/page.c`) for `coldfire.compose`.

One subject: the generated header and the source in, the linked bytes out. The
header (`wr_gen.h`: the control table and the wave spans) is written beside a
temporary copy of nothing else; `page.c` is compiled from the repository.

Only `scripts/gen_waverider_code.py` (and the test that replays it) need this and the
m68k GCC it drives; applying the mod reads the committed bytes.
"""

from __future__ import annotations

import pathlib
import tempfile

from ..patch import cbuild

SOURCE = pathlib.Path(__file__).resolve().parents[3] / "csrc" / "waverider" / "page.c"
ENTRY = "wr_page_draw"
POLL = "wr_poll"                        # the UI loop's redraw test (coldfire.POLL_SITE)
OVERLAY = "wr_cell"                     # after each stock cell widget: parameter slides' marks
# v0.14: the sample link (csrc/sampler), linked into the same chunk
LINK_SOURCES = [SOURCE.parents[1] / "sampler" / "link.c", SOURCE.parents[1] / "sampler" / "hooks.S",
                SOURCE.parents[1] / "sampler" / "smp_page.c", SOURCE.parents[1] / "sampler" / "rec.c",
                SOURCE.parents[1] / "sampler" / "rec_dt2.c",        # the RECORDER as the DT2's screens
                SOURCE.parents[1] / "sampler" / "fmt.c", SOURCE.parent / "md_page.c",
                SOURCE.parents[1] / "sampler" / "slice.c",
                SOURCE.parents[1] / "sampler" / "lib.c",
                SOURCE.parents[1] / "sampler" / "pools.c",          # v0.38: per-project pools
                SOURCE.parents[1] / "sampler" / "erase.c",          # v0.39: ERASE MOD DATA
                SOURCE.parents[1] / "sampler" / "rectrig.c",        # v0.41: REC trigs, buffers, QREC/QPLAY
                SOURCE.parent / "lzma7.c",                          # 2026-11-11: section 7 as LZMA (docs/lzma7.md)
                SOURCE.parent / "lzma7cache.c", SOURCE.parent / "lzma7late.S",   # ... decoded once, kept on the +Drive
                SOURCE.parents[1] / "jump" / "jump.c", SOURCE.parents[1] / "jump" / "hooks.S",   # DIRECT JUMP
                SOURCE.parents[1] / "slides" / "slide.c", SOURCE.parents[1] / "slides" / "hooks.S",   # parameter slides
                SOURCE.parents[1] / "meter" / "meter.c", SOURCE.parents[1] / "meter" / "hooks.S",   # the system meter
                SOURCE.parents[1] / "meter" / "quiet.c",              # ... the CPU label quiet while stock loads or upgrades
                SOURCE.parents[1] / "fdn8" / "ui.c",                 # FDN8's TYPE knob and names (docs/fdn8.md)
                SOURCE.parents[1] / "xdly" / "ui.c",                 # XDLY's TYPE knob and names (docs/xdly.md)
                SOURCE.parents[1] / "fxpage" / "fxp.c",               # the send pages' second page (docs/fxpage.md)
                SOURCE.parents[1] / "inserts" / "ins.c",              # the per-track inserts' page (docs/inserts.md)
                SOURCE.parents[1] / "inserts" / "store.c",            # ... saved with the project (2026-11-10)
                SOURCE.parents[1] / "inserts" / "hooks.S",
                SOURCE.parents[1] / "scope" / "scope.c",              # AMP page 2's oscilloscope (2026-11-11)
                SOURCE.parents[1] / "hold" / "hold.c",                # DRONE's HOLD latch (2026-11-10)
                SOURCE.parents[1] / "hold" / "hooks.S",
                SOURCE.parent / "popup.c",                            # the list popup (2026-11-09)
                SOURCE.parents[1] / "msel" / "msel.c",               # MACHINE SEL in two columns (2026-11-11)
                SOURCE.parents[1] / "msel" / "live.c",               # ... LIVE SELECT, its PERSONALIZE row (2026-11-12)
                SOURCE.parents[1] / "load" / "load.c",               # the DSP load budget at note-on (2026-11-12)
                SOURCE.parents[1] / "load" / "hooks.S",
                SOURCE.parents[1] / "msel" / "live.S",
                SOURCE.parent / "popup_stock.c",                      # ... on stock parameters' lists
                SOURCE.parents[1] / "devtest" / "devtest.c",          # the test channel (docs/remote-ui.md, 2026-11-11)
                SOURCE.parents[1] / "devtest" / "whitelist.c",        # ... its one whitelist
                SOURCE.parents[1] / "wishes" / "table.c",             # the wishes record (docs/wishes-record.md)
                SOURCE.parents[1] / "wishes" / "tlv.c",
                SOURCE.parents[1] / "wishes" / "store.c",
                SOURCE.parents[1] / "wishes" / "hooks.S",
                SOURCE.parents[1] / "wishes" / "item.c",              # ... on kits and patterns (2026-11-12)
                SOURCE.parents[1] / "wishes" / "items.S",
                SOURCE.parents[1] / "matrix" / "matrix.c",          # the matrix's routes (docs/matrix.md)
                SOURCE.parents[1] / "matrix" / "env2_page.c",       # ... AMP's ENV2 page
                SOURCE.parents[1] / "matrix" / "routes_pop.c",      # ... the routes popup (FUNC + push)
                SOURCE.parents[1] / "modulation" / "cascade.c",       # LFOs on the LFOs above them (2026-11-11)
                SOURCE.parents[1] / "modulation" / "hooks.S",
                SOURCE.parents[1] / "modulation" / "moving.c",        # controls that move (2026-11-11)
                SOURCE.parents[1] / "devtest" / "prof.c",             # ... the CPU profiler (PROFILE, remoteui-5)
                SOURCE.parents[1] / "devtest" / "prof.S",
                SOURCE.parents[1] / "devtest" / "glass.S",            # ... the glass inverted while armed
                SOURCE.parents[1] / "presets" / "engfilt.c",          # the preset browser's ENGINE filter (2026-11-12)
                SOURCE.parents[1] / "presets" / "hooks.S",
                SOURCE.parents[1] / "devtest" / "usbcfg.c",           # ... REMOTE CONTROL in USB CONFIG (2026-11-12)
                SOURCE.parents[1] / "devtest" / "usbcfg.S"]
LINK_ENTRIES = ["smp_rx_hook", "kb_rec_hook", "smp_hi", "smp_walk", "smp_booted", "smp_key", "smp_cmds", "smp_quant_hook", "fx_type_hook", "smp_tdm_hook", "smp_tdm_sent", "smp_tdm_heard", "smp_retries", "smp_saved", "smp_boot", "smp_save_recording", "smp_save_mark", "smp_load", "smp_lstate", "smp_ui_pop", "wr_screen", "rec_combo", "wr_lfo_mask", "rec_overlay", "rec_src", "rec_dest", "smp_ram", "rec_phase", "trim_slot", "trim_n", "trim_s", "trim_e", "nm_cur", "nm_text", "slc_state", "slc_page_seen", "smp_analyse", "smp_analysis", "smp_onsets", "smp_slices_set", "smp_slices_get", "slc_keynotes", "slc_nfr", "slc_sl", "slc_ns", "slc_cur", "slc_grid_n", "smp_pos", "smp_pos_at", "smp_periods", "smp_mod_apply", "smp_dir_ok", "smp_meta_ok", "smp_lst_open", "smp_fb_open", "smp_fb_folder", "smp_fb_cur", "rec_pv_on", "smp_func_held", "smp_question_up", "sn_opens", "sn_results", "sn_up", "smp_machine_commit", "smp_fb_store", "smp_lib_refresh", "smp_lib_pending", "smp_lp_queued", "smp_lib_load", "smp_lib_slot_of", "smp_lib_preview", "smp_lib_preview_stop", "smp_fb_rowtext", "smp_mq_off", "smp_fb_mcur", "smp_lp_done", "smp_lp_full", "smp_fb_auto", "smp_fb_auto_starts", "smp_lp_skipped", "smp_lib_state", "smp_lib_writes", "smp_held_lo", "smp_held_hi", "smp_knob_d", "smp_knob_at", "smp_dsp_load", "smp_load_peak", "smp_load_seen", "smp_load_at", "rec_state", "rec_heard", "slc_kb_c", "slc_alloc_n", "smp_tables", "smp_pv_state", "trim_zoom", "trim_head_x", "sl_ui_table_now", "smp_push_slot", "sl_rec_knob", "sl_rec_held", "sl_rec_table", "rec_view", "rec_rlen", "rec_link", "rec_room", "as_done", "rec_saved_slot", "rec_rstrt", "rec_thres", "rec_src", "rec_chan", "sl_rec_page", "smp_rec_place", "smp_slot_empty", "smp_pl_dirp", "rec_combo", "rec_overlay", "rt_on", "rt_play", "rt_rplace", "rt_rbytes", "rt_pend", "rt_cur", "rt_manual", "rt_qrec", "rt_qplay", "rt_pos", "rt_steps", "rt_nx_place", "rt_nx_room", "rt_nx_need", "rt_w", "rt_gen", "q_gen", "q_fire", "q_cancel", "rt_fired", "rt_refused", "rt_swaps", "rt_qfired", "rt_why", "rt_trig", "rt_cur_end", "rt_bounce_samp", "rt_is_bounce", "rt_buf_of", "rt_trig_get", "rt_trig_toggle", "rt_rearm", "rt_count", "rt_take_handover", "rt_regions", "rt_rsteps", "rt_last_step", "rt_used", "rt_fired_at", "rt_fired_trk", "rt_why_trk", "rt_last_key", "bn_page", "bn_yes_at", "bn_active", "bn_led_walk", "bn_led_poll", "bn_led_claims", "bn_open", "bn_save", "bn_pages", "bn_said_at", "bn_said_n", "bn_nothing_at", "rt_frame", "rt_poll", "rt_cut", "smp_rt_sent", "rec_rt_take", "rt_q_set", "rt_q_waiting", "rt_knob", "rt_state", "rt_arm", "rt_req", "bn_sub", "rt_flex_req", "rt_req_waiting", "rt_buf_value", "rt_buf_code", "rt_samp_buf", "smp_samp_direct", "rec_gain", "sl_knob_push", "rt_clear", "bn_clear_ask", "bn_cleared", "bn_cleared_at", "fx_get", "fx_set", "fx_valid", "ms_frame", "ms_mask", "ms_frames", "rt_mute_knob", "bn_mute", "rec_peak",
                # DIRECT JUMP (csrc/jump, docs/jump.md)
                "jmp_cue", "jmp_tick", "jmp_arm", "jmp_switch", "jmp_tracks", "jmp_key", "jmp_poll",
                "jmp_on", "jmp_armed", "jmp_pending", "jmp_count", "jmp_last", "jmp_loaded", "jmp_dirty",
                "jmp_reads", "jmp_writes", "jmp_to", "jmp_from",
                # v0.38: per-project pools (pools.c, hooks.S)
                "smp_pj_begin_hook", "smp_pj_loaded_hook", "smp_pj_end_hook", "smp_pj_new_hook", "smp_pj_begins", "smp_pj_ends", "smp_pj_loads", "smp_pj_news", "smp_pj_slot", "smp_pj_newslot", "smp_pj_last", "smp_blank_req", "smp_blank_sent", "smp_pl_on", "smp_pl_owner", "smp_pl_state", "smp_pl_writes", "smp_pl_switches", "smp_pl_lists_written", "smp_pl_events", "smp_pl_src", "smp_pl_boot_case", "smp_pl_gen", "smp_pl_skipped", "smp_pl_mismatch", "smp_discard", "smp_rename",
                 # v0.38: the count to the DSP after a live add (link.c K_HEAD)
                 "smp_heads", "smp_head_due", "smp_head_min", "smp_count_cover",
                 # v0.39: ERASE MOD DATA (erase.c)
                 "smp_er_lock", "smp_er_req", "smp_er_state", "smp_er_err", "smp_er_sector", "smp_er_value",
                 "smp_er_done", "smp_er_total", "smp_er_trims", "smp_er_reads", "smp_er_checks", "smp_er_nchecks",
                 "smp_er_job", "smp_er_start", "smp_er_poll", "smp_fb_menu",
                 "smp_er_retries", "smp_er_waits", "smp_er_resume",   # v0.41
                 # v0.40: the slice menus' wait, LINKED points, the playhead's redraw (gate: slice, samplist)
                 "slc_pop", "slc_poll", "slc_stock_asked", "slc_fails", "slc_linked", "smp_norm_state",
                 "smp_pl_quiesce", "smp_analysis_slot", "smp_slot_frames", "wr_draws", "smp_pos_in", "smp_playhead",
                 # v0.40: folders inside folders (lib.c, smp_page.c)
                 "smp_lib_fpar", "smp_fb_titletext", "smp_fb_delete",
                 # the RECORDER as the DT2's screens (rec_dt2.c): the DSP's status the checks set
                 "rec_room", "rec_frames", "rec_peak", "rec_wave", "rec_thres", "rec_link",
                 # AMP page 2's oscilloscope (csrc/scope, docs/scope.md): the state the checks read
                 "scope_up", "scope_taps", "scope_ring", "scope_pos", "smp_rx_sh"]
# parameter slides (csrc/slides, dnfw.slides): the hooks and the state the checks read
SLIDE_ENTRIES = ["sl_ui_table", "sl_cell", "sl_knob", "sl_screen", "sl_page_up", "sl_page_seen", "sl_pre_hook", "sl_pre", "sl_apply", "sl_smooth", "sl_build", "sl_clear", "sl_load", "sl_save",
                 "sl_lock_get", "sl_lock_set", "sl_v", "sl_cap", "sl_started", "sl_ticks"]
# the system meter (csrc/meter, docs/meter.md): its three hooks and the figures the checks read
METER_ENTRIES = ["mtr_isr_out", "mtr_switch", "mtr_poll", "mtr_draw"]
# FDN8 (csrc/fdn8, docs/fdn8.md): its poll and the state the checks read
FDN8_ENTRIES = ["rvt_poll", "rvt_cell", "rvt_state", "rvt_placed", "rvt_seen"]
# XDLY (csrc/xdly, docs/xdly.md): the Delay page's TYPE, the same way
XDLY_ENTRIES = ["dlt_poll", "dlt_cell", "dlt_state", "dlt_placed", "dlt_seen"]
FXP_ENTRIES = ["fxp_pop", "fxp_draw", "fxp_begin", "fxp_seen", "fxp_words", "fxp_active", "fxp_gen", "fxp_up", "fxp_v", "fxp_record", "fxp_set_record", "fxp_defaults"]
# the per-track inserts (csrc/inserts, docs/inserts.md): the page's hooks and the values the checks read
INS_ENTRIES = ["ins_pop", "ins_draw", "ins_visible", "ins_words", "ins_gen", "ins_up", "ins_sel", "ins_selv", "ins_mod", "ins_kv", "ins_hdr_tail",
               "ins_inst", "ins_edits", "ins_pj_write_hook", "ins_store_poll", "ins_wr_ring", "ins_wr_head",
               "ins_st_writes", "ins_st_loads", "ins_st_fails"]
HOLD_ENTRIES = ["hold_note_hook", "hold_final_hook", "hold_final", "hold_len", "hold_keys", "hold_poll", "hold_seq", "hold_key", "hold_count", "hold_drops", "hold_rel"]   # DRONE's HOLD (csrc/hold)
DEVTEST_ENTRIES = ["dt_rx", "dt_poll", "dt_sw", "smp_bulk_at", "prof_isr", "prof_audio",
                   "dt_glass", "dt_present", "dt_inv",   # the test channel (csrc/devtest)
                   "dt_usb_rebuild", "dt_usb_items", "dt_usb_changes", "set_remote", "set_reset_seen"]
LZMA7_ENTRIES = ["dn_depack7", "dn7_status", "dn7_length", "dn7_late", "dn7c_state", "dn7c_why"]    # 2026-11-11 (docs/lzma7.md)
MOD_ENTRIES = ["mod_mask_hook", "mod_lfo_mask", "mod_eval", "mod_eval_pre", "mod_wb", "mod_wb_cell",   # csrc/modulation
               "mv_begin", "mv_cell", "mv_cell_span", "mv_knob", "mv_poll"]
# the wishes record (csrc/wishes, docs/wishes-record.md): its four stubs and the state the checks read
WISH_ENTRIES = ["wish_memcpy_stub", "wish_memset_stub", "wish_load_stub", "wish_save_stub", "wish_poll",
                "wish_n", "wish_ready", "wish_busy", "wish_reentered", "wish_full", "wish_wants",
                "wish_loads", "wish_links_in", "wish_saves", "wish_links_out", "wish_copies", "wish_carries",
                "wish_clears", "wish_cells_written", "wish_cells_found", "wish_cells_read", "wish_resolved",
                "wish_missing", "wish_pend_head", "wish_pend_tail", "wish_pend_lost", "wish_io_fails",
                "wish_get", "wish_put", "wish_find", "wish_edits",
                "wish_item", "wish_kit_load_stub", "wish_kit_save_stub", "wish_pat_load_stub", "wish_pat_save_stub",
                "wish_song_load_stub", "wish_song_save_stub", "wish_ps_load_stub", "wish_ps_save_stub",
                "wish_item_loads", "wish_item_saves", "wish_item_nolane", "wish_item_dropped",
                "mx_poll", "mx_eval", "mx_lay", "mx_compiles", "mx_env_on", "mx_env_off",
                "mxp_pop", "mxp_poll", "mxp_draw", "mxp_visible",
                "mxp_pushes", "mxp_opens", "mxp_refusals", "mxp_why", "mxp_rid", "mxp_turns", "mxp_keys", "mxp_detents",
                "env2_visible", "mx_env2_locks", "sl_e2_held", "sl_e2_set",     # the matrix (csrc/matrix)
                "mxp_setup_dep", "mxp_setup_rows", "mxp_erased", "ins_title_now",
                "wish_rx", "wish_put_wait", "wish_puts"]                         # travel (store.c: PUT, GET)
# the preset browser's ENGINE filter (csrc/presets, dnfw.waverider.engfilt): its hooks and the state the checks read
ENG_ENTRIES = ["eng_test_hook", "eng_sort_hook", "eng_ctor_hook", "eng_label", "eng_title", "eng_list", "eng_sort_row",
               "eng_clear", "eng_toggle", "eng_tick", "eng_match", "eng_mask", "eng_tests", "eng_lists", "eng_n"]
# LIVE SELECT (csrc/msel/msel.c, live.c, live.S): its hooks and the state the checks read
LIVE_ENTRIES = ["live_menu_hook", "live_label", "live_box", "live_yes", "live_delta", "live_row", "live_on", "live_rows",
                "msel_poll", "ls_commits", "ls_reverts", "set_bits"]
# 2026-11-12: the DSP load budget (csrc/load): its hook and the state the emulator check reads
LOAD_ENTRIES = ["load_alloc_hook", "load_poll", "load_voice", "load_stock", "load_fx", "load_off", "load_checks",
                "load_over", "load_keyups", "load_sp_min", "load_last_sum", "load_last_need", "load_rows",
                # 2026-11-13: the budget by the DSP's room, the release tails (the checks set and read them)
                "load_meas", "load_busins", "load_pend", "load_pend_at", "load_tails", "load_by_room", "load_last_free",
                "smp_tlm_cost", "smp_room_now", "smp_room_at", "smp_periods"]
LINK_ENTRIES = LINK_ENTRIES + WISH_ENTRIES + LOAD_ENTRIES + LIVE_ENTRIES + ENG_ENTRIES + DEVTEST_ENTRIES + LZMA7_ENTRIES + MOD_ENTRIES + SLIDE_ENTRIES + METER_ENTRIES + FDN8_ENTRIES + XDLY_ENTRIES + FXP_ENTRIES + INS_ENTRIES + HOLD_ENTRIES


# the list popup (csrc/waverider/popup.c, docs/popups.md): on our machines' and FX's list parameters,
# and on stock parameters' lists (popup_stock.c); each part ships alone
POPUP_OURS = True
POPUP_STOCK = True
POPUP_MIN = 4          # the shortest list that pops up: 2 or 3 entries (a switch, FDN8's TYPE) do not (the User)


def available() -> bool:
    return cbuild.available()


def compile_page(header: str, *, base: int) -> tuple[bytes, dict[str, int], int]:
    """-> (image, symbols, bss) of page.c linked at BASE, with HEADER as wr_gen.h."""
    with tempfile.TemporaryDirectory(prefix="wr_gen_", dir=SOURCE.parent) as tmp:
        (pathlib.Path(tmp) / "wr_gen.h").write_bytes(header.encode())
        from ..sampler import machines as SM
        from . import dsp
        defines = {"SMP_MIRROR": hex(SM.MIRROR), "SMP_MIRROR_BYTES": hex(SM.MIRROR_BYTES),
                   "SMP_POOL_DDR": hex(dsp.SMP_POOL_DDR), "LINK_SEED": hex(SM.LINK_SEED),
                   "POOL_MAGIC": hex(SM.POOL_MAGIC) + "u", "NAMES_OFFSET": SM.NAMES_OFFSET,
                   "NAME_BYTES": SM.NAME_BYTES, "DATA_OFFSET": hex(SM.DATA_OFFSET),
                   "POOL_SLOTS": SM.POOL_SLOTS}
        from . import pages as PG
        defines["METER_RAM"] = hex(PG.METER_RAM)      # the system meter's block (csrc/meter)
        defines["WISH_AREA"] = hex(PG.WISH_RAM) + "u"  # the wishes record's RAM (csrc/wishes/wish.h)
        defines["MX_RAM"] = hex(PG.MX_RAM) + "u"      # the matrix's tables (csrc/matrix/matrix.c)
        defines["MX_BYTES"] = PG.MX_BYTES
        defines["WR_LOAD_BOUND"] = PG.TYPES_LAST + 2   # the stored-sound LOAD's machine bound (csrc/wishes/hooks.S replays it)
        defines["MOD_RAM"] = hex(PG.MOD_RAM) + "u"    # csrc/modulation's state (2026-11-11)
        defines["MOD_CASCADE_BYTES"] = PG.MOD_CASCADE_BYTES
        defines["MOD_MOVING_RAM"] = hex(PG.MOD_RAM + PG.MOD_CASCADE_BYTES) + "u"
        defines["MOD_MOVING_BYTES"] = PG.MOD_BYTES - PG.MOD_CASCADE_BYTES
        defines["PROF_RAM"] = hex(PG.PROF_RAM)        # the CPU profiler's state and ring (csrc/devtest/prof.c)
        defines["PROF_BYTES"] = hex(PG.PROF_BYTES)
        defines["WPOP_OURS"] = int(POPUP_OURS)        # the list popup's two parts (csrc/waverider/popup.c)
        defines["WPOP_STOCK"] = int(POPUP_STOCK)
        defines["WPOP_MIN"] = int(POPUP_MIN)
        for name in ("POOL_BYTES", "REC_OFFSET", "REC_END", "RAM_PROVEN", "SLICE_AREA", "TABLE_AREA", "TABLE_ROOM", "TABLE_READY", "TABLE_MAGIC", "TABLE_SUM_AT", "TABLE_LOAD", "CMD_OFFSET", "STATUS_MAGIC", "TDM_TAG",
                     "RX_MAGIC", "TX_MAGIC", "POS_MAGIC", "POS_NONE", "POS_ONE", "META_PTR", "META_PTR_MAGIC", "META_MAGIC", "META_FOLDERS",
                     "META_FOLDER_BYTES", "META_SLOT_BYTES", "META_NAME_BYTES", "META_BYTES", "LIBID_OFFSET"):      # v0.16; v0.25 POS
            defines[name] = hex(getattr(SM, name)) + "u"
        for name in ("REC_FIRST", "REC_SLOTS", "REC_SLOT_SHIFT", "CMD_SEND", "CMD_VERIFY", "CMD_PROBE", "CMD_PREVIEW", "CMD_SCAN",
                     "RX_WORDS", "TX_WORDS", "CMD_WORDS",
                     "BUF_N", "BUF_HALVES", "BUF_ENTRY", "BUF_DIR", "BUF_SLOT0", "BOUNCE_TYPE"):   # v0.44 BOUNCE
            defines[name] = int(getattr(SM, name))
        import os
        if PG.stock_units_on():
            defines["DN2_STOCK_UNITS"] = 1            # the stock records' units (md_page.c, page.c): a build option
        if PG.lfo4_on():
            defines["DN2_LFO4"] = 1                   # lfo4's side in our code (page.c; docs/lfo-112-port.md): an option
        if os.environ.get("DNFW_SMP_STORE_TEST"):
            # an emulator-only build: the +Drive region inside the emulator's 15 MB device
            # (never shipped: scripts/gen_waverider_code.py refuses to write it)
            sector, floor = os.environ["DNFW_SMP_STORE_TEST"].split(",")
            defines.update({"STORE_SECTOR": sector + "u", "STORE_FLOOR": floor + "u"})
        linked = cbuild.build([SOURCE, *LINK_SOURCES], base=base,
                              entries=[ENTRY, POLL, OVERLAY, *LINK_ENTRIES],
                              include=[pathlib.Path(tmp)], defines=defines)
    # libgcc's 64-bit helpers use instructions the ColdFire lacks (an illegal-instruction
    # exception on the instrument, found in the emulator in v0.16): none may be linked
    wide = sorted(n for n in linked.symbols if n.endswith("di3") or n.endswith("di4"))
    if wide:
        raise RuntimeError(f"the page renderer links libgcc's 64-bit helpers {wide}: use 32-bit arithmetic")
    return linked.image, linked.symbols, linked.bss
