"""float32 bit patterns as the SHARC runner's steps read them (2026-11-14): what counts as sound, what is finite.

`w & 0x7fffffff` alone counts NaN and infinity as sound: a step whose output went NaN passed a "it sounds" check
(stockout, a2f, fdn8 until 2026-11-14). Every runner step that asks "does it sound" uses `sounds`, and asks
`finite` beside it. Words are 32-bit patterns (None, as m2.word gives for an unknown word, reads as 0).
"""

from __future__ import annotations

EXP_MASK = 0x7F800000                           # every exponent bit set: NaN or infinity


def finite(words) -> bool:
    """every word a finite float32 (no NaN, no infinity)"""
    return all(((w or 0) & EXP_MASK) != EXP_MASK for w in words)


def sounds(words) -> bool:
    """some word is a finite, nonzero float32 (NaN and infinity are not sound; -0.0 is silence)"""
    return any(((w or 0) & EXP_MASK) != EXP_MASK and (w or 0) & 0x7FFFFFFF for w in words)


class Ear:
    """what a step heard over a run: `n` finite nonzero words, `bad` NaN or infinity. `ok(k)`: more than K heard and
    nothing non-finite (a "the test hears something" check that a run of NaN cannot pass)"""

    def __init__(self) -> None:
        self.n = 0
        self.bad = 0

    def hear(self, words) -> "Ear":
        for w in words:
            w = (w or 0) & 0xFFFFFFFF
            if (w & EXP_MASK) == EXP_MASK:
                self.bad += 1
            elif w & 0x7FFFFFFF:
                self.n += 1
        return self

    def ok(self, more_than: int) -> bool:
        return self.n > more_than and self.bad == 0

    def __repr__(self) -> str:
        return f"{self.n} heard, {self.bad} non-finite"
