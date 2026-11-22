"""v0.68 (upstream): MACHINE SEL's icons, the owner's sheet (src/dnfw/msicons.py).

v0.68.1 (the User, 2026-11-22, "A"): our two-column MACHINE SEL covers stock's left pane, so upstream's pane
hooks are not in our build; upstream's machines show the owner's icons in our 7 x 5 cells instead
(dnfw.waverider.msel OWNER_ICONS). The emulator's machines step reads them off the screen."""
from dnfw import msicons
from dnfw.waverider import coldfire, msel


def test_upstreams_machines_are_mod_machines():
    assert set(msicons.TYPE_ICON) <= set(coldfire.NEW_TYPES)


def test_every_owner_icon_has_a_cell_icon():
    assert set(msel.OWNER_ICONS) == set(msicons.ORDER)


def test_cell_icons_are_7_by_5():
    for name, rows in msel.OWNER_ICONS.items():
        assert len(rows) == 5 and all(len(r) == 7 and set(r) <= {"#", "."} for r in rows), name
        assert any("#" in r for r in rows), name


def test_upstreams_machines_show_the_owners_icons():
    icons = msel.machine_icons()
    for t, n in msicons.TYPE_ICON.items():
        if t in msel.OWNER_KEEP:
            continue
        assert icons[t] == msel.OWNER_ICONS[n], (t, n)


def test_monomachine_ours_and_stock_keep_theirs():
    icons = msel.machine_icons()
    assert icons[6] == msel.OWNER_ICONS["SID"]                # MONOMACHINE: the owner's SID (the User, 2026-11-22)
    for t in range(5):                                       # FM TONE, WAVETONE, FM DRUM, SWARMER, MIDI
        assert icons[t] == msel.MACHINE_ICONS[t]
    for t, n in msel._ours().items():
        if t not in msicons.TYPE_ICON:
            assert icons[t] == msel.OUR_ICONS[n], (t, n)


def test_the_owners_icons_are_told_apart():
    shown = [tuple(r) for n, r in msel.OWNER_ICONS.items()]
    assert len(set(shown)) == len(shown)


def test_no_pane_hooks_in_our_build():
    from dnfw.waverider import cpage
    assert not hasattr(coldfire, "MACHSEL_ICON_SITE") and not hasattr(coldfire, "MACHSEL_LABEL_SITE")
    assert "ms_icon_hook" not in cpage.LINK_ENTRIES and not any(p.name == "msicon.c" for p in cpage.LINK_SOURCES)
