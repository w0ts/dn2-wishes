"""The waverider build without the boot-screen stamp (NOBOOT): no intro hook, no stamp CODE chunk, no ANIZ/ANZL
chunks. Every 1.12 build is made this way (on 1.12 the stamp at 0x46708000 sat under the +Drive bounce buffer;
dn2mk2-scratch/os112/build_noboot043.py, then autobuild/rebase/lib/noboot.py, of which this is a copy), so the
gate's rebuild step rebuilds a NOBOOT image the same way.

    import noboot; noboot.install()     # before dnfw mods apply / dn2patch.build(); the tree's src/ on sys.path
"""


def install() -> None:
    from dnfw.mods import ModError, Result, platform, waverider as W
    release_apply = W.apply

    def apply_noboot(firmware):
        cf = firmware.container.find(W.MAIN_OS)
        ds = firmware.container.find(W.DSP_STREAM)
        if cf is None or ds is None:
            raise ModError("image has no MAIN OS or no DSP boot stream")
        main_os, stream = cf.unpack(), ds.unpack()
        main_os, others = platform.split(main_os)
        section7 = W.dsp.section7(stream)
        codes = [(platform.area.CODE, platform.area.CodeChunk(load, code).pack())
                 for load, code, _ in W._chunks()]
        base_os = bytearray(W._main_os(main_os))
        # v0.67 (upstream): the arp on MIDI tracks (midiarp), its sites checked stock in this image first, as the
        # release apply does (its spec ported to 1.12: scripts/build_arp_midi_play.py, gen_midiarp_code.py)
        from dnfw.mods import midiarp as MA
        MA.check(bytes(base_os))
        MA.write(base_os, main_os)
        content = platform.join(bytes(base_os), others + codes)
        area_length = len(content) - platform.STOCK_LENGTH
        ext = [e for e in W.extents(firmware, area_length) if "intro hook" not in e.what]
        # how each section is stored is the release build's (2026-11-11: section 7 as LZMA, docs/lzma7.md);
        # a tree whose Result has no codecs stores every section as before
        codecs = getattr(release_apply(firmware), "codecs", None)
        extra = {"codecs": codecs} if codecs else {}
        return Result(payloads={W.MAIN_OS: content, W.DSP_STREAM: section7}, extents=ext,
                      notes=["no boot-screen stamp (intro stock)"], **extra)

    W.apply = apply_noboot
