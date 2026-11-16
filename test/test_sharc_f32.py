"""The runner steps' sound checks (scripts/sharc_f32.py, 2026-11-14): NaN and infinity are not sound, a frame
holding either is not finite. Until then `w & 0x7fffffff` counted a run of NaN as sound (stockout, a2f, fdn8)."""
from __future__ import annotations

import pathlib
import struct
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sharc_f32 as F32  # noqa: E402


def w(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


NAN, QNAN_NEG, INF, NINF = 0x7FC00000, 0xFFC00001, 0x7F800000, 0xFF800000


def test_a_nan_frame_is_not_sound():
    assert not F32.sounds([NAN] * 64)
    assert not F32.sounds([QNAN_NEG, NAN] * 32)


def test_infinity_is_not_sound():
    assert not F32.sounds([INF, NINF] * 32)


def test_silence_is_not_sound():
    assert not F32.sounds([0, 0x80000000, None] * 32)    # +0.0, -0.0, an unknown word


def test_a_finite_word_is_sound():
    assert F32.sounds([0] * 63 + [w(1e-6)])
    assert F32.sounds([w(-0.25)] + [NAN] * 63)            # sound, and the finite check fails it


def test_finite():
    assert F32.finite([0, w(0.5), w(-3.0e38), 0x00000001, None])   # a denormal is finite
    assert not F32.finite([0] * 63 + [NAN])
    assert not F32.finite([w(0.5), INF])


def test_the_steps_use_it():
    """every step that asks "does it sound" asks it through sharc_f32, with a finite check beside it, and no step
    tests sound with the bare mask any more"""
    for name, need in (("sharc_stockout_step.py", ("sounds(", "finite(")),
                       ("sharc_a2f_step.py", ("F32.sounds(", "F32.finite(")),
                       ("sharc_fdn8_step.py", ("F32.sounds(", "F32.finite(", "F32.Ear(")),
                       ("sharc_xdly_step.py", ("F32.Ear(",)), ("sharc_jsend_step.py", ("F32.Ear(",)),
                       ("sharc_inserts_step.py", ("F32.Ear(",)), ("sharc_insall_step.py", ("F32.Ear(",)),
                       ("sharc_inspost_step.py", ("F32.Ear(",))):
        src = (SCRIPTS / name).read_text(encoding="utf-8")
        for n in need:
            assert n in src, (name, n)
        assert "& 0x7FFFFFFF" not in src, name           # no bare-mask "it sounds" test left


def test_the_ear_fails_on_nan():
    e = F32.Ear().hear([w(0.1)] * 5000 + [NAN])
    assert e.n == 5000 and e.bad == 1 and not e.ok(3000)
    assert F32.Ear().hear([w(0.1)] * 5000 + [0, None]).ok(3000)
    assert not F32.Ear().hear([0] * 5000).ok(0)
