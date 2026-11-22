"""DRUM's reference model (float32, numpy scalars): the arithmetic the SHARC code does, written plainly.

The design and its stage-1 / 1b renders: scratch/drum-engine (design.md, drum_v2.py). This module is drum_v2's KICK
and SNARE as the firmware plays them, with the User's 2026-11-20 choices on top: a DC blocker after the drive, ADAA
(first-order antiderivative anti-aliasing) on KICK's soft clip, the phase kept in 0..1 every sample.

Stage 3 (2026-11-20, scratch/drum-engine/drum_v3.py, design.md 10 / 11): the re-voicing ported, as drum_v3 has it.
KICK: SIGH follows the hit's level (velocity, drive), SWHD (page 2 G, the sweep held 0..30 ms), velocity into the clip.
SNARE: WCHR (page 2 H, PERC's TYPE record: 64 today's wires, 0..64 the 909's band with a wire hold and a threshold
close, 64..127 the 808's 2-pole high-pass), velocity into the clip. HATS: the swing VCA's diode knee, CLOSED's hold
then stop, OPEN's 6 ms rise, flat 30 % then a straight-line close (an exponential tail at long DCAY: OPEN_X0..X1),
the VCA before the high-pass, TOP (page 2 E), DRFT (page 2 F: the metal's jitter and drift), velocity into the knee.
TOM (new): drum_v3's Tom3 (stage 1b's TOM: a swept sine, two skin modes, skin noise, the stick, the soft drive),
RNGE (page 2 D) LOW / MID / HI. The levels: the TR-808's mix-out balance (scratch/drum-engine/levels_v3.md).

The SHARC side (dnfw.engines.drum.kick, snare) uses PERC's sine polynomial, its exp2 polynomial and reciprocal where
this uses numpy's sin, exp and division (SNARE's modes take the DSP's sine polynomial here too: Snare.half);
test/test_drum.py holds the two within a declared tolerance (DSL_TOL_DB).

Knobs: page 1 as the DN2's 0..127 (the DSP reads knob / 128 x 128 / 127), page 2 as 0..1 (the DSP reads
(value - lo) / top: dnfw.mnm.core.page2).
"""

from __future__ import annotations

import math

import numpy as np

F = np.float32
FS = 44100.0
HALF = 16
TWO_PI = 2.0 * math.pi
LN_THOUSAND = 6.907755278982137              # ln(1000): an exponential's fall of 60 dB
DC_PRE_HZ = 12.0                             # the click's DC out before the drive (stage 1)
DC_POST_HZ = 5.0                             # 2026-11-20: the drive's DC out after it (10.4 % -> 0.14 % in the driven corner)
ADAA_EPS = 2e-3                              # |u - u_prev| under this: the soft clip of the midpoint
ADAA_G = 10.0                                # ADAA only above this gain (below it the plain clip: no aliasing to speak of)
CHIRP_AT = 0.8                               # CLKT from here: the chirp click (below: the pulse and noise)
DECLICK_S = 0.001                            # a retrig: the cut sound fades in 1 ms
BASE_HZ = 50.0                               # KICK at TUNE 0 st, note 60
SWEEP_TOP_HZ = 12000.0                       # the sweep's start held under this
CHIRP_END_HZ = 250.0


def expo(k: float, lo: float, hi: float) -> float:
    return lo * (hi / lo) ** k


def decay_coef(t60: float) -> np.float32:
    return F(math.exp(-LN_THOUSAND / (t60 * FS)))


def tau_coef(tau: float) -> np.float32:
    return F(math.exp(-1.0 / (tau * FS)))


def onepole_a(fc: float) -> np.float32:
    return F(1.0 - math.exp(-TWO_PI * min(fc, 0.45 * FS) / FS))


# PERC's sine polynomial (dnfw.engines.plaits.plk SIN_POLY, sinp; test/test_drum.py holds the copies equal): sin(2 pi r)
# on |r| <= 1/4 as r (c1 + c3 r^2 + ..), 1.9e-7 off sin. A copy, so that this module needs numpy alone.
SIN_POLY = (6.283185005187988, -41.34165573120117, 81.60099792480469, -76.5496597290039, 39.53581237792969)


def sinp(x: float) -> np.float32:
    """sin(2 pi x) as the DSP computes it (plk.ref_sinp), float32 step by step"""
    r = F(x + 0.5)
    r = F(r - math.floor(r))
    r = F(r - F(0.5))
    if r > 0.25:
        r = F(F(0.5) - r)
    if r < -0.25:
        r = F(F(-0.5) - r)
    r2 = r * r
    acc = F(SIN_POLY[-1])
    for c in reversed(SIN_POLY[:-1]):
        acc = acc * r2 + F(c)
    return acc * r


def soft(x: np.float32) -> np.float32:
    """Plaits' SoftClip: x (27 + x^2) / (27 + 9 x^2), +-1 beyond +-3"""
    if x < -3.0:
        return F(-1.0)
    if x > 3.0:
        return F(1.0)
    x2 = x * x
    return x * (F(27.0) + x2) / (F(27.0) + F(9.0) * x2)


SOFT_F3 = 0.5 + 4.0 / 3.0 * math.log(12.0)   # the antiderivative at 3


def soft_F(u: np.float32) -> np.float32:
    """SoftClip's antiderivative: v^2 / 18 + 4/3 ln(3 + v^2) with v = clamp(u, -3, 3), plus |u| - 3 beyond"""
    v = F(min(max(float(u), -3.0), 3.0))
    v2 = v * v
    return F(v2 * F(1.0 / 18.0) + F(4.0 / 3.0) * F(math.log(float(F(3.0) + v2)))
             + F(max(abs(float(u)) - 3.0, 0.0)))


# stage 5 (the User, 2026-11-20: no digital clipping): every type's level x KIT_TRIM (-3.1 dB), so that at every knob
# setting no type's output reaches full scale: KICK's worst (CLIK at its centre, a bright click on the body's first
# peak, NOIS and SHAP up) measured 1.18 before it, CLAP's soft clip at DRIV 0 tops at CLAP_GAIN (1.137); the kit's
# balance (the 808 MIX-OUT levels) is kept, every type the same factor (scratch/drum-engine/click/peaks.py)
KIT_TRIM = 0.70
KICK_GAIN = KIT_TRIM


def comp(g: float) -> float:
    """the drive's level held: g^-0.45 up to x10, then nearly flat"""
    return g ** -0.45 if g <= 10.0 else 10.0 ** -0.45 * (10.0 / g) ** 0.08


class Noise:
    """Plaits' stmlib Random (the LCG), a signed sample in -1..1: int32(word) / 2^31"""

    def __init__(self, seed: int = 0x21):
        self.s = seed

    def __call__(self) -> np.float32:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        v = self.s - (1 << 32) if self.s & 0x80000000 else self.s
        return F(v * (1.0 / 2147483648.0))


def sin1(ph: float) -> np.float32:
    return F(math.sin(TWO_PI * ph))


SWHD_MAX = 0.030                             # stage 3: KICK's sweep hold, 0 .. 30 ms (page 2 G)
# stage 5 (the User, 2026-11-20): KICK's CLIK, a balance in SNAP's place: centre = body+noise and click both at 100 %, left
# end = body+noise only, right end = the click only (linear); the click's 100 % = SNAP's old maximum (1.5), high-passed
# at 300 Hz (x 2) on the pulse path, added AFTER the drive (not clipped with the body) x CLICK_POST: the click alone
# peaks about as the body does. CURV (page 2 H): the sweep's fall, 64 = the exponential as before, 0 = a straight line
# over 5 time constants, 127 = the concave r (2 - r) (holds, then drops); between, a linear blend with the exponential.
CLICK_HP_HZ, CLICK_HP_G, CLICK_POST = 300.0, 2.0, 0.24 * 0.4 * KIT_TRIM   # (0.4: the worst-case peak; KIT_TRIM)
CURV_MID, CURV_SPAN = 64, 64.0
CURV_T = 5.0                                 # the ramp's length in sweep time constants
HAT_BAL_K = 0.748031497001648         # the hats' balance: both parts x the old start's metal share (1 - NOIS 32's)


BAL_L, BAL_R = 127.0 / 63.0, 127.0 / 64.0     # a balance's slopes: knob 64 both 100 %, 0 the first only, 127 the second


def balance(b: float) -> tuple[np.float32, np.float32]:
    """a balance knob's two gains (b = knob / 127, the DSP's u): min(1, (1 - b) 127/63), min(1, b 127/64), float32;
    the readout -64 .. +63 (knob - 64)"""
    b = F(b)
    return F(min(F(F(F(1.0) - b) * F(BAL_L)), F(1.0))), F(min(F(b * F(BAL_R)), F(1.0)))


def vel_mod(vel_knob: float, vel: float) -> np.float32:
    """vm = 1 + VEL (vel - 1), float32 as the DSP (kick.vm)"""
    return F(F(F(F(vel) + F(-1.0)) * F(vel_knob)) + F(1.0))


class Kick:
    """KICK. Page 1: TUNE DCAY SWEP SWTM CLIK CLKT DRIV (TYPE on H); page 2: SHAP HOLD SIGH CLKL NOIS VEL SWHD CURV.
    Stage 3: the sigh follows the hit's level (hl = vm g^0.25: f0 (1 - SIGH (1 - min(hl amp, 1)))), the sweep held
    SWHD samples at its top, the clip at g x vm (its level held at g's: a soft hit cleaner and quieter)."""
    P1 = ("TUNE", "DCAY", "SWEP", "SWTM", "CLIK", "CLKT", "DRIV")
    P2 = ("SHAP", "HOLD", "SIGH", "CLKL", "NOIS", "VEL", "SWHD", "CURV")
    # the starts (stage 1's KICK defaults, as DN2 knobs; page 2 as 0..1 of 127)
    D1 = dict(TUNE=51, DCAY=81, SWEP=45, SWTM=64, CLIK=64, CLKT=57, DRIV=16)
    D2 = dict(SHAP=13 / 127, HOLD=20 / 127, SIGH=32 / 127, CLKL=38 / 127, NOIS=6 / 127, VEL=64 / 127, SWHD=0.0,
              CURV=CURV_MID / 127)

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        self.k1 = {**self.D1, **(p1 or {})}
        self.k2 = {**self.D2, **(p2 or {})}
        self.noise = Noise(seed)
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.up = F(0.0)
        self.fup = soft_F(F(0.0))
        self.dc2 = F(0.0)
        self.dc2_a = onepole_a(DC_POST_HZ)

    @staticmethod
    def knobs(k1: dict, k2: dict) -> dict:
        """the controls as the DSP reads them"""
        u = {n: float(F(F(v / 128.0) * F(128.0 / 127.0))) for n, v in k1.items()}
        st = math.trunc(k1["TUNE"] * 60.0 / 127.0 + 0.5) - 24       # whole semitones, -24..+36
        return dict(
            st=st,
            t60=expo(u["DCAY"], 0.005, 8.0),
            octs=7.0 * u["SWEP"],
            swtau=expo(u["SWTM"], 0.001, 0.15),
            clik=u["CLIK"],
            curv=knob_of(k2.get("CURV", CURV_MID / 127)),
            clkt=u["CLKT"],
            g=1.0 + 30.0 * u["DRIV"] * u["DRIV"],
            pm=0.45 * k2["SHAP"],
            hold=int(0.25 * k2["HOLD"] * k2["HOLD"] * FS),
            sigh=0.25 * k2["SIGH"],
            clkl=expo(k2["CLKL"], 0.0002, 0.02),
            nz=0.5 * k2["NOIS"],
            vel=k2["VEL"],
            swhd=math.trunc(float(F(F(k2.get("SWHD", 0.0)) * F(SWHD_MAX * FS)))),
        )

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        q = self.knobs(self.k1, self.k2)
        self.q = q
        vm = float(vel_mod(q["vel"], vel))
        f0 = BASE_HZ * 2.0 ** ((q["st"] + note - 60.0) / 12.0)
        self.f0 = F(f0 / FS)
        octs = q["octs"] * (0.5 + 0.5 * vm)
        self.sw_amt = F(min(f0 * (2.0 ** octs - 1.0), SWEEP_TOP_HZ - f0) / FS)
        self.sw = F(1.0)
        self.sw_d = tau_coef(q["swtau"])
        self.sigh = F(q["sigh"])
        self.hold = q["hold"]
        self.n = 0
        self.amp = F(1.0)
        self.amp_d = decay_coef(q["t60"])
        self.pm = F(q["pm"])
        self.ph = F(0.0)
        self.g1, g2 = balance(q["clik"])
        self.clk = F(F(F(g2) * F(1.5)) * F(vm))
        self.clk_d = tau_coef(q["clkl"])
        self.chp = F(0.0)
        self.chp_a = onepole_a(CLICK_HP_HZ)
        c = q["curv"] - CURV_MID                      # CURV: the blend with a line (left) or the concave (right)
        self.cv_a = F(abs(c) / CURV_SPAN if c < 0 else c / CURV_SPAN)
        self.cv_k = 0 if c == 0 else (1 if c < 0 else 2)
        self.cv_r = F(1.0)
        self.cv_dr = F(1.0 / (CURV_T * q["swtau"] * FS))
        ct = q["clkt"]
        self.chirp = F(1.0 if ct >= CHIRP_AT else 0.0)
        self.clk_a = onepole_a(expo(min(ct, 0.75) / 0.75, 400.0, 16000.0))
        self.clk_lp = F(0.0)
        self.ch_f0 = F(expo(max(ct - CHIRP_AT, 0.0) / (1.0 - CHIRP_AT), 1500.0, 9000.0) / FS)
        self.ch_end = F(CHIRP_END_HZ / FS)
        self.ch_e = F(1.0)
        self.ch_d = tau_coef(max(q["clkl"] * 0.6, 0.0004))
        self.ch_ph = F(0.0)
        self.nz = F(q["nz"])
        self.nz_d = decay_coef(q["t60"] * 0.3)
        self.nz_a = onepole_a(1500.0 + 6000.0 * (q["pm"] / 0.3))
        self.nz_lp = F(0.0)
        self.dc_a = onepole_a(DC_PRE_HZ)
        self.dc = F(0.0)
        self.g = F(F(q["g"]) * F(vm))                # stage 3: the clip sees the velocity, the level does not
        self.comp = F(comp(q["g"]) * KICK_GAIN)
        self.adaa = self.g > ADAA_G
        if self.adaa:
            self.fup = soft_F(self.up)
        self.hl = F(F(vm) * F(q["g"] ** 0.25))      # stage 3: the hit's level the sigh follows
        self.swhd = q["swhd"]
        self.sh_n = 0
        if self.on:
            self.dk = self.last                      # the cut sound fades out (no step)
        self.on = True

    def drive(self, x: np.float32) -> np.float32:
        """the soft clip at gain g with ADAA, level held, then the DC blocker"""
        u = x * self.g
        if self.adaa:
            fu = soft_F(u)
            d = u - self.up
            if abs(float(d)) < ADAA_EPS:
                y = soft(F(0.5) * (u + self.up))
            else:
                y = (fu - self.fup) * F(1.0 / float(d))
            self.fup = fu
        else:
            y = soft(u)
        self.up = u
        y = y * self.comp
        self.dc2 += self.dc2_a * (y - self.dc2)
        return y - self.dc2

    def sample(self) -> np.float32:
        lv = min(self.hl * self.amp, F(1.0))
        f = self.f0 * (F(1.0) - self.sigh * (F(1.0) - lv)) + self.sw_amt * self.sw
        if self.cv_k:                                # CURV off its centre: the sweep's shape blended
            r = self.cv_r
            sh = r if self.cv_k == 1 else r * (F(2.0) - r)
            f = f + self.sw_amt * (self.cv_a * (sh - self.sw))
        if self.sh_n < self.swhd:                    # the sweep held at its top (SWHD), then its fall
            self.sh_n += 1
        else:
            self.sw *= self.sw_d
            self.cv_r = max(self.cv_r - self.cv_dr, F(0.0))
        ph = self.ph + f
        self.ph = ph - F(math.floor(float(ph)))
        body = sin1(float(self.ph + self.pm * sin1(float(self.ph))))
        if self.n >= self.hold:
            self.amp *= self.amp_d
        else:
            self.n += 1
        if self.chirp > 0.0:
            cf = self.ch_end + (self.ch_f0 - self.ch_end) * self.ch_e
            self.ch_e *= self.ch_d
            cp = self.ch_ph + cf
            self.ch_ph = cp - F(math.floor(float(cp)))
            click = F(1.2) * sin1(float(self.ch_ph))
        else:
            src = F(1.0) + F(0.7) * self.noise()
            self.clk_lp += self.clk_a * (src - self.clk_lp)
            self.chp += self.chp_a * (self.clk_lp - self.chp)
            click = (self.clk_lp - self.chp) * F(CLICK_HP_G)
        click = click * self.clk
        self.clk *= self.clk_d
        nz = self.noise()
        self.nz_lp += self.nz_a * (nz - self.nz_lp)
        noise = self.nz_lp * self.nz
        self.nz *= self.nz_d
        x = (body * self.amp + noise) * self.g1
        self.dc += self.dc_a * (x - self.dc)
        y = (self.drive(x - self.dc) + click * F(CLICK_POST)) + self.dk
        self.dk *= self.dk_d
        self.last = y
        return y

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            out[i] = self.sample()
        return out


class Svf:
    """stmlib's Svf (Plaits' set_f_q, Process): five words g, r, h, s1, s2"""

    def __init__(self):
        self.g = self.r = self.h = self.s1 = self.s2 = F(0.0)

    def set(self, fc: float, q: float) -> None:
        """g = tan(pi fc / FS), r = 1 / q, h = 1 / (1 + r g + g g); the state zeroed (a hit's)"""
        g = F(math.tan(math.pi * fc / FS))
        r = F(1.0 / q)
        self.g, self.r = g, r
        self.h = F(1.0 / float((r * g + F(1.0)) + g * g))
        self.s1 = self.s2 = F(0.0)

    def tick(self, x: np.float32) -> tuple[np.float32, np.float32, np.float32]:
        hp = (((x - self.r * self.s1) - self.g * self.s1) - self.s2) * self.h
        bp = self.g * hp + self.s1
        self.s1 = self.g * hp + bp
        lp = self.g * bp + self.s2
        self.s2 = self.g * bp + lp
        return lp, bp, hp


# SNARE (2026-11-20, stage 2b): scratch/drum-engine/drum_v2.py Snare2 with the User's choices: RING gone (the body's
# T60 is DCAY's), four modes always, the stmlib SVF, the DC out after the drive, one per-type level
SNARE_HZ = 180.0                             # SNARE at TUNE 0 st, note 60
ANALOG = (1.0, 2.0, 3.18, 4.16)              # Plaits' first four 808-style modes
MEMBRANE = (1.0, 1.59, 2.14, 2.295)          # a drum head's (0,1) (1,1) (2,1) (0,2)
MODE_TOP = 0.45                              # a mode's frequency held under this (of FS)
GLIDE_MAX, GLIDE_TAU = 0.12, 0.025           # the tension glide: up to 12 %, falling in 25 ms
STICK_MAX, STICK_TAU, STICK_HP_HZ = 1.6, 0.0015, 1800.0
PULSE_N, PULSE = 13, 0.6                     # the stick's 0.3 ms pulse (13 samples)
WATK_SPLIT = 0.7                             # WATK above this: clap bursts before the wires
BURST_TAU = 0.0028
WIRE_Q, SIZZ_Q, SIZZ_RATIO, SIZZ_TOP_HZ = 0.9, 1.2, 2.2, 14000.0
WIRE_HP_HZ = 350.0
NOIS_MAX = 1.4
# the types' levels (stage 3, the User 2026-11-20): the TR-808's MIX-OUT balance (Service Notes p. 14 and the mix
# resistors, scratch/drum-engine/levels_v3.md), peak-to-peak of each type's 808 point against KICK's 808 LONG: SNARE
# -4.9 dB (808 re-voiced), TOM -4.0 (808 LO / MID / HI's mean), CL.HH -7.9 (CH 808 re-voiced), OP.HH -8.1 (OH 808
# re-voiced). KICK's level stays the machine's (dnfw.perc.program LEVEL_DB["DRUM"])
SNARE_GAIN = 0.4945 * KIT_TRIM
# stage 3: WCHR (page 2 H, PERC's TYPE record 0..127, read as its knob): 64 the wires as before; 0..64 the 909's band
# (no high-pass share) with a wire hold up to 24 ms and a threshold close; 64..127 the band into the SVF's high-pass
WCHR_MID = 64
WIRE_HOLD_MAX, WIRE_VT = 0.024, 2e-4
WIRE_FLOOR = -1e30                           # the threshold's floor when WCHR is 64 or above: none


def knob_of(q: float) -> int:
    """a page-2 control read back as its knob, trunc(q 127 + 0.5) in float32 (the DSP's; pages.host_dsp_choice)"""
    return math.trunc(float(F(F(F(q) * F(127.0)) + F(0.5))))


class Snare:
    """SNARE. Page 1: TUNE DCAY TONE MODE SNAP NOIS DRIV (TYPE on H); page 2: WIRE GLID BUZZ WTON WATK SIZZ VEL WCHR.
    The modes are retuned every 16-sample half after the hit (the glide). Stage 3: WCHR, the clip at g x vm."""
    P1 = ("TUNE", "DCAY", "TONE", "MODE", "SNAP", "NOIS", "DRIV")
    P2 = ("WIRE", "GLID", "BUZZ", "WTON", "WATK", "SIZZ", "VEL", "WCHR")
    # its start RICH (stage 1b's: the 4th mode, sizzle; the User 2026-11-20); WCHR 64: the wires as stage 2
    D1 = dict(TUNE=64, DCAY=57, TONE=100, MODE=90, SNAP=48, NOIS=38, DRIV=25)     # (stage 5: NOIS 76 as the balance)
    D2 = dict(WIRE=61 / 127, GLID=55 / 127, BUZZ=60 / 127, WTON=70 / 127, WATK=22 / 127, SIZZ=45 / 127, VEL=64 / 127,
              WCHR=64 / 127)

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        self.k1 = {**self.D1, **(p1 or {})}
        self.k2 = {**self.D2, **(p2 or {})}
        self.noise = Noise(seed)
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.up = F(0.0)
        self.dc2 = F(0.0)
        self.dc2_a = onepole_a(DC_POST_HZ)
        self.wsvf, self.ssvf = Svf(), Svf()
        self.n = 0

    @staticmethod
    def knobs(k1: dict, k2: dict) -> dict:
        """the controls as the DSP reads them"""
        u = {n: F(F(v / 128.0) * F(128.0 / 127.0)) for n, v in k1.items()}
        st = math.trunc(k1["TUNE"] * 48.0 / 127.0 + 0.5) - 24       # whole semitones, -24..+24
        t60 = expo(float(u["DCAY"]), 0.03, 2.0)
        tone = float(u["TONE"])
        return dict(
            st=st,
            t60=t60,
            tone=min(tone / 0.75, 1.0),
            g4=0.7 * max(0.0, (tone - 0.75) / 0.25),
            mode=u["MODE"],
            stk=STICK_MAX * float(u["SNAP"]),
            bal=balance(u["NOIS"]),                    # stage 5: NOIS, the balance body / wires
            g=1.0 + 20.0 * float(u["DRIV"]) ** 2,
            wire=min(max(t60 * expo(k2["WIRE"], 0.25, 6.0), 0.03), 3.0),
            glid=k2["GLID"],
            buzz=k2["BUZZ"],
            wton=expo(k2["WTON"], 1500.0, 9000.0),
            watk=k2["WATK"],
            sizz=k2["SIZZ"],
            vel=k2["VEL"],
            wchr=knob_of(k2.get("WCHR", WCHR_MID / 127)),
        )

    def wchr(self, k: int) -> None:
        """WCHR's knob K: the band's and the high-pass's shares, the wire hold (samples), the threshold, its floor
        and 1 / (1 - threshold) (float32, as snare.hit)"""
        d = F(F(max(WCHR_MID - k, 0)) * F(1.0 / WCHR_MID))          # 1 at the 909's end, 0 from the middle
        w = F(F(max(k - WCHR_MID, 0)) * F(1.0 / (127 - WCHR_MID)))  # 1 at the 808's end
        self.bpg = F(F(1.0) - w)
        self.hpg = F(F(F(0.3) - F(F(0.3) * d)) + F(F(0.7) * w))
        self.whold = math.trunc(float(F(d * F(WIRE_HOLD_MAX * FS))))
        self.vt = F(d * F(WIRE_VT))
        if d > 0.0:
            self.vlo, self.vtn = F(0.0), F(1.0 / float(F(F(1.0) - self.vt)))
        else:
            self.vlo, self.vtn = F(WIRE_FLOOR), F(1.0)

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        q = self.knobs(self.k1, self.k2)
        self.q = q
        vm = float(vel_mod(q["vel"], vel))
        m = q["mode"]
        self.ratios = [F(b - a) * m + F(a) for a, b in zip(ANALOG, MEMBRANE)]
        self.f = F(SNARE_HZ * 2.0 ** ((q["st"] + note - 60.0) / 12.0) / FS)
        self.rs = [F(math.exp(-LN_THOUSAND * float(r) / (q["t60"] * FS))) for r in self.ratios]
        tone = q["tone"]
        g1 = q["bal"][0]
        self.re = [g1, F(F(0.2 + 0.8 * tone) * g1), F(F(0.8 * tone * tone) * g1), F(F(q["g4"]) * g1)]
        self.im = [F(0.0)] * 4
        self.c = [F(0.0)] * 4
        self.s = [F(0.0)] * 4
        self.glide = F(q["glid"] * GLIDE_MAX * (0.6 + 0.4 * vm))
        self.gl = F(1.0)
        self.gl_d = tau_coef(GLIDE_TAU)
        self.stk = F(q["stk"] * (0.5 + 0.5 * vm))
        self.stk_d = tau_coef(STICK_TAU)
        self.stk_lp = F(0.0)
        self.stk_a = onepole_a(STICK_HP_HZ)
        self.w_dec = F(1.0)
        self.w_att = F(1.0)
        self.w_dd = decay_coef(q["wire"])
        wa = q["watk"]
        self.w_ad = tau_coef(expo(min(wa, WATK_SPLIT) / WATK_SPLIT, 0.0003, 0.008))
        # the clap bursts: NB at 0, D, 2D .. (D whole samples), the wires from NB x D; none below the split
        self.nb, self.bd, self.w_start = 0, 0, 0
        if F(wa) > F(WATK_SPLIT):                    # (float32, as the DSP: the counts are whole numbers)
            c = (F(wa) + F(-WATK_SPLIT)) * F(1.0 / (1.0 - WATK_SPLIT))
            self.nb = 1 + math.trunc(float(c * F(3.0) + F(0.5)))
            self.bd = math.trunc(float((c * F(0.004) + F(0.006)) * F(FS)))
            self.w_start = self.nb * self.bd
        self.bc = 0
        self.b_env = F(0.0)
        self.b_d = tau_coef(BURST_TAU)
        self.w_lvl = F(q["bal"][1] * F(NOIS_MAX))
        self.omb = F(1.0 - q["buzz"])
        self.b2 = F(2.0 * q["buzz"])
        self.bph = F(0.0)
        wf = q["wton"] * 2.0 ** (vm - 1.0)           # a soft hit darker
        self.wsvf.set(wf, WIRE_Q)
        self.sz = F(0.8 * q["sizz"])
        self.ssvf.set(min(wf * SIZZ_RATIO, SIZZ_TOP_HZ), SIZZ_Q)
        self.whp_a = onepole_a(WIRE_HP_HZ)
        self.whp = F(0.0)
        self.g = F(F(q["g"]) * F(vm))                # stage 3: the clip sees the velocity
        self.comp = F(comp(q["g"]) * SNARE_GAIN)
        self.wchr(q["wchr"])
        self.wh_end = self.w_start + self.whold      # the wires' decay starts here (the hold)
        self.n = 0
        if self.on:
            self.dk = self.last                      # the cut sound fades out (no step)
        self.on = True

    def half(self) -> None:
        """the modes at this half's tension (the glide), their decays. The sines are the DSP's polynomial
        (sinp, 1.9e-7 off sin): a rotor turns its coefficients' last bits into phase, sample after sample, and
        the drive's slope (up to x7 at zero) shows that phase: against numpy's sin the model drifts to -44 dB under the
        peak in 40 ms at full drive and no glide (a frequency 3e-8 of FS apart, inaudible)."""
        fb = self.f * (self.glide * self.gl + F(1.0))
        self.fb = fb
        for k in range(4):
            ph = min(fb * self.ratios[k], F(MODE_TOP))
            self.c[k] = sinp(float(ph + F(0.25))) * self.rs[k]
            self.s[k] = sinp(float(ph)) * self.rs[k]

    def sample(self) -> np.float32:
        self.gl *= self.gl_d
        body = None
        for k in range(4):
            re, im, c, s = self.re[k], self.im[k], self.c[k], self.s[k]
            self.re[k] = c * re - s * im
            self.im[k] = s * re + c * im
            body = self.im[k] if body is None else body + self.im[k]
        nz = self.noise()
        self.stk_lp += self.stk_a * (nz - self.stk_lp)
        hp = nz - self.stk_lp
        if self.n < PULSE_N:
            hp = hp + F(PULSE)
        stick = hp * self.stk
        self.stk *= self.stk_d
        b = self.bph + self.fb
        self.bph = b - F(math.floor(float(b)))
        tri = abs(self.bph - F(0.5)) * F(4.0) - F(1.0)
        rattle = self.omb + self.b2 * max(tri, F(0.0))
        if self.n < self.w_start:
            if self.bc == 0:
                self.b_env = F(1.0)
                self.bc = self.bd
            self.bc -= 1
        env = self.b_env * self.w_lvl
        self.b_env *= self.b_d
        if self.n >= self.w_start:
            we = max(self.w_dec - self.w_att - self.vt, self.vlo) * self.vtn   # the threshold close (WCHR < 64)
            env = env + we * self.w_lvl
            if self.n >= self.wh_end:                # the wire hold (WCHR < 64), then the decay
                self.w_dec *= self.w_dd
            self.w_att *= self.w_ad
        self.n += 1
        wn = self.noise() * rattle
        _lp, bp, hpw = self.wsvf.tick(wn)
        w = bp * self.bpg + hpw * self.hpg
        w = w + self.sz * self.ssvf.tick(wn)[1]
        self.whp += self.whp_a * (w - self.whp)
        wires = (w - self.whp) * env
        x = (body * F(0.8) + stick) + wires
        u = x * self.g
        self.up = u
        y = soft(u) * self.comp
        self.dc2 += self.dc2_a * (y - self.dc2)
        y = y - self.dc2 + self.dk
        self.dk *= self.dk_d
        self.last = y
        return y

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            if self.n % HALF == 0:
                self.half()
            out[i] = self.sample()
        return out


# HATS (2026-11-20, stage 2c): scratch/drum-engine/drum_v2.py Hat2 / OpenHat2 with the User's choices: plain squares
# (no anti-aliasing) on the 808's six at its 47.98 % duty, their phases 32-bit integers (they wrap by themselves and
# a square is one signed compare: the edges are the DSP's to the sample, so the reference counts them the same way),
# the stmlib SVF, one level per type, the choke (an OPEN voice's envelope falls in 3 ms when a CLOSED hit lands on
# its track: docs/drum.md)
EXP2_POLY = (0.00021877562525891297, 0.0012387871006721122, 0.009684565724072036, 0.05548044028510092,
             0.2402304964795069, 0.6931469295754649, 1.000000002548704)   # PERC's exp2 (plk.exp2p; a copy)
HAT_F808 = (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)                     # Werner, Abel, Smith, ICMC-SMC 2014
HAT_LOG2 = tuple(float(F(math.log2(f / HAT_F808[0]))) for f in HAT_F808)  # each square's octaves over the first
HAT_BASE = float(F(HAT_F808[0] / FS))
HAT_DUTY = 0.4798
HAT_T = int(round(HAT_DUTY * 2.0 ** 32)) - (1 << 31)    # a phase word (signed, offset by half a turn) under this: +1
HAT_PH0 = tuple(int(0.13 * i * 2.0 ** 32) - (1 << 31) for i in range(6))   # each hit's phases (stage 1b's 0.13 i)
HAT_INC_TOP = 0.45                                      # a square's frequency held under this (of FS)
HAT_T60 = ((0.008, 0.6), (0.08, 4.0))                   # CLOSED, OPEN
HAT_BAND_HZ, HAT_LOWB_HZ = 7100.0, 3440.0
HAT_HP_Q, HAT_LOWB_Q = 0.75, 1.5
HAT_SNAP_TAU, HAT_CHOKE_TAU = 0.002, 0.003
SVF_TOP_HZ = 0.45 * FS                                  # a hat filter's frequency held under this
HAT_GAIN = (0.3857 * KIT_TRIM, 0.4619 * KIT_TRIM)                              # CLOSED, OPEN: the types' levels (SNARE_GAIN)
HAT_Q0 = expo(44 / 127, 0.8, 8.0)                       # the band's Q at its start (Q 44): the clip's level held above it
HAT_TOP = 0.99                                          # the output held under this (a noise burst's rare peak)


def choke_block(open_block: int, closed_block: int) -> int | None:
    """the block (PERC's 32-sample blocks) from which an OPEN hit at OPEN_BLOCK is choked by a CLOSED hit on its track
    at CLOSED_BLOCK, or None. A later block: from that block (PERC renders the newest voice first, so the CLOSED hit
    comes before the older OPEN voice in its block). The SAME block (the User, 2026-11-20: the OPEN is always choked,
    whatever the slots' render order): from the next block, in either order. An earlier block: never."""
    if closed_block > open_block:
        return closed_block
    if closed_block == open_block:
        return open_block + 1
    return None
HAT_SNAP_HOLD, HAT_LOWB_HOLD, HAT_RING_HOLD = 1.0, 1.5, 0.5   # the level x 1 / ((1 + SNAP) (1 + 1.5 LOWB) (1 + 0.5 ring))


def exp2p(x: float) -> np.float32:
    """2^x as the DSP computes it (plk.exp2p: floor and fraction, EXP2_POLY by Horner, the power's exponent bits),
    float32 step by step"""
    x = F(x)
    i = math.trunc(float(x))
    f = F(i)
    if x < f:
        f = F(f - F(1.0))
        i -= 1
    fr = F(x - f)
    acc = F(EXP2_POLY[0])
    for c in EXP2_POLY[1:]:
        acc = F(acc * fr) + F(c)
    return acc * F(2.0 ** i)


def s32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


# stage 3 (drum_v3 Hat3): the swing VCA's diode knee, OPEN's shape, TOP, DRFT
KNEE_V, KNEE_W = 0.5899, 1.2                 # the swing VCA's diode: knee point, knee width (8W8's figures)
E0_TOP = 4.0                                 # the envelope's start (8W8's 4 V trigger) at full velocity
CL_TAU = 0.43                                # CLOSED: tau = this x DCAY's T60 (the -40 dB point kept)
OP_LEN, OP_HOLD = 0.78, 0.30                 # OPEN: length = OP_LEN x DCAY's T60, flat for OP_HOLD of it, then a line
OP_RISE = 0.006                              # OPEN: the rise's time constant
# the User's choice (2026-11-20): an exponential tail at long DCAY. Up to OPEN_X0 the line alone; the exponential's
# share rises linearly to all of it at OPEN_X1 (DCAY's 0..1). Its T60 (after the same rise and hold) keeps the -40 dB
# point where DCAY puts it (2/3 T60): EXP_T60 = 1.5 (2/3 - OP_HOLD OP_LEN) of DCAY's T60
OPEN_X0, OPEN_X1 = 80 / 127, 100 / 127       # DCAY 80 (T60 0.94 s) .. 100 (T60 1.75 s)
EXP_T60 = 1.5 * (2.0 / 3.0 - OP_HOLD * OP_LEN)
TOP_EMPH = 1.5                               # TOP: the first difference's share at TOP 1
JIT = 0.0052                                 # the 808's period jitter (a cycle's, +-), at DRFT 64
DRIFT_STEP, DRIFT_LEAK, DRIFT_HALVES = 2.5e-4, 0.98, 16   # the drift's walk: every 16 halves (256 samples)
JRNG_SEED = 0x21 ^ 0x5A5A                    # the jitter's own generator (the noise's sequence stays as before)
HAT_RISE = float(F(1.0 - math.exp(-1.0 / (OP_RISE * FS))))


def knee(e: np.float32) -> np.float32:
    """the diode's knee: 0 under KNEE_V, (e - V)^2 / 2W over the knee, e - V - W / 2 above (float32, branch-free as
    hats.sample: o = max(e - V, 0), k = min(o, W), k^2 / 2W + (o - k))"""
    o = max(F(e - F(KNEE_V)), F(0.0))
    k = min(o, F(KNEE_W))
    return F(F(F(k * k) * F(1.0 / (2.0 * KNEE_W))) + F(o - k))


IK0 = float(F(1.0 / float(knee(F(E0_TOP)))))


def log2p(x: float) -> np.float32:
    """log2 as the DSP computes it (dmath.log2_inline: the exponent, LOG2_POLY on the mantissa), float32"""
    from . import dmath as _dm
    b = int(np.array([x], dtype=np.float32).view(np.uint32)[0])
    e = F((b >> 23) - 127)
    m = np.array([(b & 0x7FFFFF) | 0x3F800000], dtype=np.uint32).view(np.float32)[0]
    t = F(m + F(-1.0))
    acc = F(_dm.LOG2_POLY[0])
    for c in _dm.LOG2_POLY[1:]:
        acc = F(F(acc * t) + F(c))
    return F(acc + e)


class Hat:
    """CLOSED / OPEN HAT (OPEN by the flag). Page 1: TUNE DCAY TONE NOIS COLR SNAP DRIV (TYPE on H); page 2: HPF Q
    LOWB VEL TOP DRFT. choke(): a CLOSED hit on the track (an OPEN voice's envelope falls in 3 ms from there).
    Stage 3: the VCA through the diode knee (CLOSED holds, then stops; OPEN rises in 6 ms, stays flat 30 % of its
    length, then falls in a line, or exponentially at long DCAY), the VCA before the high-pass, TOP, DRFT."""
    P1 = ("TUNE", "DCAY", "TONE", "NOIS", "COLR", "SNAP", "DRIV")
    P2 = ("HPF", "Q", "LOWB", "VEL", "TOP", "DRFT")
    # the starts (stage 1b's, from v1's: drum.PLACES CLHH / OPHH); DRFT 64: the 808's amount
    D1 = dict(TUNE=64, DCAY=58, TONE=64, NOIS=22, COLR=44, SNAP=44, DRIV=32)   # (stage 5: NOIS 32 as the balance)
    D1_OPEN = dict(D1, DCAY=55)
    D2 = dict(HPF=64 / 127, Q=44 / 127, LOWB=0.0, VEL=64 / 127, TOP=0.0, DRFT=64 / 127)

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21, open_: bool = False):
        self.open = open_
        self.k1 = {**(self.D1_OPEN if open_ else self.D1), **(p1 or {})}
        self.k2 = {**self.D2, **(p2 or {})}
        self.noise = Noise(seed)
        self.jrng = Noise(JRNG_SEED)
        self.drift = [F(0.0)] * 6                    # the drift's walk: kept from hit to hit (its own words)
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.bsvf, self.hsvf, self.lsvf = Svf(), Svf(), Svf()

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        k1, k2 = self.k1, self.k2
        u = {n: F(F(v / 128.0) * F(128.0 / 127.0)) for n, v in k1.items()}
        vm = vel_mod(k2["VEL"], vel)
        # TUNE: whole semitones on the 808's six, plus the note: tr = 2^((st + note - 60) / 12)
        st = math.trunc(k1["TUNE"] * 48.0 / 127.0 + 0.5) - 24
        tr = exp2p(F(F(F(F(st) + F(note)) + F(-60.0)) * F(1.0 / 12.0)))
        # COLR: the ratios bent r^(0.6 .. 1.4) to 0.7, the ring-modulated pairs above it
        c = u["COLR"]
        w = min(F(c * F(1.0 / 0.7)), F(1.0))
        warp = F(F(F(w + F(-0.5)) * F(0.8)) + F(1.0))
        self.ring = max(F(F(c + F(-0.7)) * F(1.0 / 0.3)), F(0.0))
        self.inc0 = []                               # each square's increment before DRFT (float32: its word x 2^32)
        for lg in HAT_LOG2:
            a = F(F(exp2p(F(warp * F(lg))) * F(HAT_BASE)) * tr)
            a = min(a, F(HAT_INC_TOP))
            self.inc0.append(F(a * F(2.0 ** 32)))
        self.inc = [math.trunc(float(x)) for x in self.inc0]
        self.ph = list(HAT_PH0)
        g1, g2 = balance(u["NOIS"])                  # stage 5: NOIS, the balance metal / noise, x HAT_BAL_K
        omm, mix = F(g1 * F(HAT_BAL_K)), F(g2 * F(HAT_BAL_K))
        self.mix = mix
        self.ka = F(F(F(1.0) - self.ring) * omm) * F(1.0 / 6.0)     # the squares' sum's weight
        self.kb = F(self.ring * omm) * F(1.0 / 3.0)                  # the pairs' sum's
        # the band at 7.1 kHz x 2^((TONE - 0.5) 3), a soft hit darker; the high-pass at it x HPF; the low band
        tone_r = 2.0 ** ((float(u["TONE"]) - 0.5) * 3.0)
        fc = min(HAT_BAND_HZ * tone_r * 2.0 ** ((float(vm) - 1.0) * 0.5), SVF_TOP_HZ)
        q = expo(k2["Q"], 0.8, 8.0)
        self.bsvf.set(fc, q)
        self.hsvf.set(min(fc * expo(k2["HPF"], 0.4, 1.4), SVF_TOP_HZ), HAT_HP_Q)
        self.lsvf.set(HAT_LOWB_HZ * tone_r, HAT_LOWB_Q)
        # the level held (the User, 2026-11-20: no corner over 1.0): against SNAP, LOWB, the ring and Q above its start
        gain = HAT_GAIN[self.open] / ((1.0 + HAT_SNAP_HOLD * float(u["SNAP"])) * (1.0 + HAT_LOWB_HOLD * k2["LOWB"])
                                      * (1.0 + HAT_RING_HOLD * float(self.ring)))
        self.lowb = F(k2["LOWB"] * 2.0 * gain)
        g = 1.0 + 20.0 * float(u["DRIV"]) ** 2
        self.g2 = F(F(g) + F(g))
        self.comp = F(comp(g * max(q / HAT_Q0, 1.0)) * gain)
        self.snap = F(2.0 * float(u["SNAP"]) * (0.5 + 0.5 * float(vm)))
        self.snap_d = tau_coef(HAT_SNAP_TAU)
        # the VCA (stage 3): DCAY's T60 in samples (as hats.hit: PERC's exp2), the knee's start by velocity
        lo, hi = HAT_T60[self.open]
        t60s = F(exp2p(F(u["DCAY"] * F(math.log2(hi / lo)))) * F(lo * FS))
        self.e0 = F(F(F(F(vm) * F(0.4)) + F(0.6)) * F(E0_TOP))
        self.n = 0
        if self.open:
            self.e = F(0.0)
            self.hold_n = math.trunc(float(F(t60s * F(OP_HOLD * OP_LEN))))
            self.m = F(1.0)
            self.s1 = F(self.e0 * F(1.0 / float(F(t60s * F((1.0 - OP_HOLD) * OP_LEN)))))
            self.mx = F(math.exp(-LN_THOUSAND / float(F(t60s * F(EXP_T60)))))
            self.xt = min(max(F(F(u["DCAY"] + F(-OPEN_X0)) * F(1.0 / (OPEN_X1 - OPEN_X0))), F(0.0)), F(1.0))
        else:
            self.e = self.e0
            self.hold_n = 0
            self.m = F(math.exp(-1.0 / float(F(t60s * F(CL_TAU)))))
            self.s1 = F(0.0)
            self.mx = F(1.0)
            self.xt = F(0.0)
        self.ex = F(0.0)
        # TOP: the pre-emphasis and the band toward its high-pass; DRFT: the metal's jitter (a draw a square a half)
        # and its drift (a leaky walk every 16 halves): DRFT 64 the 808's
        top = F(k2["TOP"])
        self.top_a = F(top * F(TOP_EMPH))
        self.bpg, self.hpg = F(F(1.0) - top), top
        self.x1 = F(0.0)
        dr = F(F(k2["DRFT"]) * F(127.0 / 64.0))
        jd = F(dr * F(JIT))
        self.jit = []
        for x in self.inc0:
            y = max(F(x * F(16.0 / 2.0 ** 32)), F(16.0 / FS))      # 16 a (a = the square's frequency / FS)
            self.jit.append(F(exp2p(F(log2p(y) * F(-0.5))) * jd))   # JIT x DRFT / sqrt(16 a)
        self.dstep = F(dr * F(DRIFT_STEP))
        self.choke_d = tau_coef(HAT_CHOKE_TAU)
        if self.on:
            self.dk = self.last                      # the cut sound fades out (no step)
        self.on = True

    def choke(self) -> None:
        """a CLOSED hit on this OPEN voice's track: its VCA falls in 3 ms from here (both shapes; out of the hold)"""
        if self.open:
            self.hold_n = 0
            self.m, self.s1, self.mx = self.choke_d, F(0.0), self.choke_d

    def half(self) -> None:
        """each 16 samples: the drift's walk every 16 halves, then a jitter draw a square (the generator always
        drawn: its sequence the same at every DRFT)"""
        if self.n % (HALF * DRIFT_HALVES) == 0:
            for i in range(6):
                self.drift[i] = F(F(self.drift[i] + F(self.dstep * self.jrng())) * F(DRIFT_LEAK))
        for i in range(6):
            j = F(self.jit[i] * self.jrng())
            self.inc[i] = math.trunc(float(F(self.inc0[i] * F(F(F(1.0) + self.drift[i]) + j))))

    def gate(self) -> np.float32:
        """the VCA: e through the knee (OPEN: the rise and the hold, then the line), the exponential share xt at long
        DCAY (OPEN), the choke's fall on both"""
        held = self.n < self.hold_n
        if held:
            self.e = F(self.e + F(F(self.e0 - self.e) * F(HAT_RISE)))
        else:
            self.e = max(F(F(self.e * self.m) - self.s1), F(0.0))
        kn = F(knee(self.e) * F(IK0))
        self.ex = kn if held else F(self.ex * self.mx)
        return F(kn + F(F(self.ex - kn) * self.xt))

    def sample(self) -> np.float32:
        if self.n % HALF == 0:
            self.half()
        sq = []
        for i in range(6):
            self.ph[i] = s32(self.ph[i] + self.inc[i])
            sq.append(F(1.0) if self.ph[i] < HAT_T else F(-1.0))
        metal = ((((sq[0] + sq[1]) + sq[2]) + sq[3]) + sq[4]) + sq[5]
        rm = (sq[0] * sq[1] + sq[2] * sq[3]) + sq[4] * sq[5]
        x = (metal * self.ka + rm * self.kb) + self.noise() * self.mix
        pre = x + self.top_a * (x - self.x1)
        self.x1 = x
        _lp, bp, hp = self.bsvf.tick(pre)
        band = bp * self.bpg + hp * self.hpg
        y = soft(band * self.g2) * self.comp
        v = self.gate() + self.snap
        self.snap *= self.snap_d
        self.n += 1
        h = self.hsvf.tick(y * v)[2]
        out = h + self.lsvf.tick(x)[1] * self.lowb * v
        out = out + self.dk
        self.dk *= self.dk_d
        out = min(max(out, F(-HAT_TOP)), F(HAT_TOP))
        self.last = out
        return out

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            out[i] = self.sample()
        return out


class OpenHat(Hat):
    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        super().__init__(p1, p2, seed, open_=True)


# TOM (stage 3, 2026-11-20): drum_v3's Tom3 (stage 1b's Tom2 re-voiced): a sine body swept SWEP (square law) in SWTM,
# two skin modes (rotors: 1.41 / 3.0 .. 1.59 / 2.14 by MODE above 0.25; toward the 909's 1.5 / 2.75 on their own
# 66 / 42 ms below), SHAP the body from a sine to the 909's rounded triangle, the skin noise (a one-pole at 6 f0), the
# stick, the soft clip at g x vm, its level held (KICK's), the DC out after it, the declick. RNGE (page 2 D): LOW / MID /
# HI add RNGE_ST semitones to TUNE (the study's 808 toms: 92 / 133 / 192 Hz apart as the TR-808's).
TOM_HZ = 110.0                               # TOM at TUNE 0 st, RNGE MID, note 60
RNGE_ST = (-6.5, 0.0, 6.25)
TOM_P909 = (1.5, 2.75)                       # 9W9's upper partials
TOM_T909 = (0.110 * 0.6, 0.070 * 0.6)        # their T60s (110 / 70 ms to -100 dB)
TOM_MODE_909 = 0.25
TOM_TRI_G = 2.0
TOM_TRI_N = float(F(1.0 / float(soft(F(TOM_TRI_G)))))
TOM_GAIN = 0.6327 * KIT_TRIM                            # the type's level (SNARE_GAIN)


def rnge_of(q: float) -> int:
    """RNGE's choice (LOW MID HI) from its page-2 value: its knob (knob_of), (knob x 3) >> 7, as the page"""
    return (knob_of(q) * 3) >> 7


class Tom:
    """TOM. Page 1: TUNE DCAY SWEP TONE SNAP NOIS DRIV (TYPE on H); page 2: SWTM MODE SHAP RNGE VEL."""
    P1 = ("TUNE", "DCAY", "SWEP", "TONE", "SNAP", "NOIS", "DRIV")
    P2 = ("SWTM", "MODE", "SHAP", "RNGE", "VEL")
    # its start: the study's re-voiced 808 MID (TUNE +4 st: 138.6 Hz, SWEP +8.2 %, SWTM 45 ms), RNGE MID
    D1 = dict(TUNE=74, DCAY=69, SWEP=21, TONE=0, SNAP=10, NOIS=8, DRIV=0)     # (stage 5: NOIS 15 as the balance)
    D2 = dict(SWTM=64 / 127, MODE=1.0, SHAP=0.0, RNGE=64 / 127, VEL=64 / 127)

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        self.k1 = {**self.D1, **(p1 or {})}
        self.k2 = {**self.D2, **(p2 or {})}
        self.noise = Noise(seed)
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.up = F(0.0)
        self.dc2 = F(0.0)
        self.dc2_a = onepole_a(DC_POST_HZ)

    @staticmethod
    def knobs(k1: dict, k2: dict) -> dict:
        u = {n: float(F(F(v / 128.0) * F(128.0 / 127.0))) for n, v in k1.items()}
        st = math.trunc(k1["TUNE"] * 48.0 / 127.0 + 0.5) - 24
        return dict(
            st=st,
            rng=RNGE_ST[rnge_of(k2["RNGE"])],
            t60=expo(u["DCAY"], 0.04, 3.0),
            usw=u["SWEP"],
            swtau=expo(k2["SWTM"], 0.005, 0.4),
            tone=u["TONE"],
            stk=0.8 * u["SNAP"],
            bal=balance(u["NOIS"]),                    # stage 5: NOIS, the balance body / skin noise
            g=1.0 + 20.0 * u["DRIV"] ** 2,
            mode=k2["MODE"],
            shap=k2["SHAP"],
            vel=k2["VEL"],
        )

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        q = self.knobs(self.k1, self.k2)
        self.q = q
        vm = float(vel_mod(q["vel"], vel))
        # the pitch and the sweep's depth in float32 as tom.hit (the phase follows them sample by sample: the drive's
        # slope shows a last bit's difference)
        x = F(F(F(F(q["st"]) + F(note)) + F(-60.0)) * F(1.0 / 12.0))
        f0h = F(exp2p(F(x + F(q["rng"] / 12.0))) * F(TOM_HZ))
        f0 = float(f0h)
        self.f0 = F(f0h * F(1.0 / FS))
        usw = F(q["usw"])
        self.sw_amt = F(F(F(usw * usw) * F(3.0)) * F(F(F(vm) * F(0.4)) + F(0.6)))
        self.sw = F(1.0)
        self.sw_d = tau_coef(q["swtau"])
        t60 = q["t60"]
        g1, g2 = q["bal"]
        self.amp = g1
        self.amp_d = decay_coef(t60)
        m = F(q["mode"])
        t9 = max(F(F(m * F(-1.0 / TOM_MODE_909)) + F(1.0)), F(0.0))
        mo = max(F(F(m + F(-TOM_MODE_909)) * F(1.0 / (1.0 - TOM_MODE_909))), F(0.0))
        old = (F(F(mo * F(0.18)) + F(1.41)), F(F(mo * F(-0.86)) + F(3.0)))
        self.ratios = [F(o + F(F(F(p) - o) * t9)) for o, p in zip(old, TOM_P909)]
        self.rs = [decay_coef(t60 / (float(r) * 1.3) * (1.0 - float(t9)) + t * float(t9))
                   for r, t in zip(self.ratios, TOM_T909)]
        tone = q["tone"]
        self.re = [F(F(0.6 * tone) * g1), F(F(0.4 * tone * tone) * g1)]
        self.im = [F(0.0), F(0.0)]
        self.c = [F(0.0), F(0.0)]
        self.s = [F(0.0), F(0.0)]
        self.ph = F(0.0)
        self.shap = F(q["shap"])
        self.nz = F(g2 * F(0.6))
        self.nz_d = decay_coef(t60 * 0.3)
        self.nz_a = onepole_a(f0 * 6.0)
        self.nz_lp = F(0.0)
        self.stk = F(q["stk"] * vm)
        self.stk_d = tau_coef(0.001)
        self.g = F(F(q["g"]) * F(vm))                # the clip at g x vm, its level held at g's
        self.comp = F(comp(q["g"]) * TOM_GAIN)
        self.n = 0
        if self.on:
            self.dk = self.last                      # the cut sound fades out (no step)
        self.on = True

    def half(self) -> None:
        """the skin modes at this half's pitch (the sweep): c = r cos, s = r sin (PERC's sine polynomial)"""
        fb = self.f0 * (F(1.0) + self.sw_amt * self.sw)
        for k in range(2):
            ph = min(fb * self.ratios[k], F(MODE_TOP))
            self.c[k] = sinp(float(ph + F(0.25))) * self.rs[k]
            self.s[k] = sinp(float(ph)) * self.rs[k]

    def sample(self) -> np.float32:
        f = self.f0 * (F(1.0) + self.sw_amt * self.sw)
        self.sw *= self.sw_d
        ph = self.ph + f
        self.ph = ph - F(math.floor(float(ph)))
        s = sinp(float(self.ph))
        fr = self.ph + F(0.75)                       # the triangle in phase with the sine: frac(ph - 1/4)
        fr = fr - F(math.floor(float(fr)))
        tri = abs(fr - F(0.5)) * F(4.0) - F(1.0)
        s = s + (soft(F(TOM_TRI_G) * tri) * F(TOM_TRI_N) - s) * self.shap
        body = s * self.amp
        self.amp *= self.amp_d
        skin = None
        for k in range(2):
            re, im, c, sn = self.re[k], self.im[k], self.c[k], self.s[k]
            self.re[k] = c * re - sn * im
            self.im[k] = sn * re + c * im
            skin = self.im[k] if skin is None else skin + self.im[k]
        nz = self.noise()
        self.nz_lp += self.nz_a * (nz - self.nz_lp)
        noise = self.nz_lp * self.nz
        self.nz *= self.nz_d
        stick = (nz - self.nz_lp) * self.stk
        self.stk *= self.stk_d
        u = (((body + skin) + noise) + stick) * self.g
        self.up = u
        y = soft(u) * self.comp
        self.dc2 += self.dc2_a * (y - self.dc2)
        y = y - self.dc2 + self.dk
        self.dk *= self.dk_d
        self.n += 1
        self.last = y
        return y

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            if self.n % HALF == 0:
                self.half()
            out[i] = self.sample()
        return out


# STAGE 4 (2026-11-20): CLAP, RIDE and CRASH (scratch/drum-engine/drum_v4.py, design.md section 12) as the firmware
# plays them (dnfw.engines.drum.clap, cymbal): drum_v4's loops in float32, every value set the way the DSP sets it (its
# exp2, log2, reciprocal and e^x: exp2p, log2p, recipp, coefp), so the burst times, the squares' edges and the long
# decays agree with the DSP's; the User's choices: GRP, the bell and the rivets always run (a level of 0 when off: one
# cost), RIDE and CRASH one code (two TYPE entries: their starts and levels), the exponential envelopes as rendered.
def recipp(x: float) -> np.float32:
    """1 / x as the DSP computes it (dnfw.perc.machines._recip_inline): the seed 0x7ef311c7 - bits, three Newton
    steps, float32"""
    b = int(np.array([x], dtype=np.float32).view(np.uint32)[0])
    d = np.array([(0x7EF311C7 - b) & 0xFFFFFFFF], dtype=np.uint32).view(np.float32)[0]
    x = F(x)
    for _ in range(3):
        t = F(x * d)
        t = F(F(2.0) - t)
        d = F(d * t)
    return d


def exp_negp(x: float) -> np.float32:
    """e^x (x <= 0) as the DSP computes it (dmath.exp_neg): its series above -0.125, 2^(x log2 e) below"""
    x = F(x)
    if x > F(-0.125):
        acc = F(1.0 / 24.0)
        for c in (1.0 / 6.0, 0.5, 1.0, 1.0):
            acc = F(F(acc * x) + F(c))
        return acc
    return exp2p(F(x * F(1.4426950408889634)))


def coefp(x: float, k: float) -> np.float32:
    """e^(k / x) as kick._coef: the reciprocal, x k, e^"""
    return exp_negp(F(recipp(x) * F(k)))


def expop(x: float, lo: float, hi: float) -> np.float32:
    """lo (hi / lo)^x as kick._expo (PERC's exp2)"""
    return F(exp2p(F(F(x) * F(math.log2(hi / lo)))) * F(lo))


def drive_comp(g: float, gain: float = 1.0) -> np.float32:
    """the drive's level held (kick.drive_level): the larger of -0.45 log2 g and the flat law above g = 10, by log2p
    and exp2p, x GAIN"""
    lg = log2p(F(g))
    a = F(lg * F(-0.45))
    b = F(F(F(lg + F(-math.log2(10.0))) * F(-0.08)) + F(-0.45 * math.log2(10.0)))
    c = exp2p(max(a, b))
    return F(c * F(gain)) if gain != 1.0 else c


def u_of(k1: dict) -> dict:
    return {n: F(F(v / 128.0) * F(128.0 / 127.0)) for n, v in k1.items()}


def tune_x(knob: float, note: float) -> np.float32:
    """(st + note - 60) / 12, st = trunc(TUNE x 48 / 127 + 0.5) - 24 (kick.tune_oct)"""
    st = math.trunc(knob * 48.0 / 127.0 + 0.5) - 24
    return F(F(F(F(st) + F(note)) + F(-60.0)) * F(1.0 / 12.0))


CLAP_HZ = 1000.0                             # the band at TUNE 0 st, note 60 (the 808 at -2 st: 891 Hz)
CLAP_T60 = (0.05, 4.0)                       # DCAY: the tail's T60
CLAP_SPRD = (0.003, 0.030)                   # SPRD: the bursts' spacing
CLAP_SNAP = (0.0008, 0.015)                  # SNAP: a burst's time constant (127 the shortest)
CLAP_Q = (0.6, 8.0)
CLAP_TATK = (0.0003, 0.080)                  # TATK: the tail's rise (time constant)
CLAP_FLOOR, CLAP_FLOOR_X, CLAP_FLOOR_MAX = 0.03, 8.6, 6.0    # the 808's floor: 0.03 of the tail, 8.6 x its T60
CLAP_GRP_RATIO, CLAP_GRP_QX, CLAP_TAIL_QX = 1.26, 0.8, 0.6  # the second clapper's band (+4 st) and Q; the tail's Q
CLAP_GRP_SP = 1.07                           # the second clapper's bursts' spacing x this
CLAP_NB_T = float(F(math.sqrt(1.0 / CLAP_TAIL_QX)))          # the bands' levels held against Q and place (bp x r)
CLAP_NB_G = float(F(math.sqrt(1.0 / (CLAP_GRP_QX * CLAP_GRP_RATIO))))
# (2026-11-21, no setting reaches the soft clip's flat top: at TAIL 64 and up a narrow tail band's noise peaked at a
# clip input of 2.40 at Q 64, 2.72 at Q 96, 2.99 at Q 127, the flat top from 3) the tail's level above Q's centre
# x 2^(-0.71 (Q - 0.5)): 0.78 at Q 127, back to the peaks of Q 64; Q 0 .. 64 unchanged. Q's range is exponential, so
# this is q^-0.19 above q 2.19
CLAP_TQ_U0, CLAP_TQ_K = 0.5, 0.71
# (2026-11-21) the bands' level held, sqrt(1000 / (q fc)), with fc at least 250 Hz: at a low TUNE and a low note
# (fc 16 Hz at TUNE 0, note 12) it rose x 10 and the clip's input reached 11; above 250 Hz unchanged (the start 891 Hz)
CLAP_NB_FMIN = 250.0
# and with q at least 1.25 (just under the start's 1.276): at a low Q the low-pass share (TONE under 64) does not
# narrow, and the hold boosted it to a clip input of 4.0; with the low-pass share 0.6 (was 0.8) the worst is 2.54
CLAP_NB_QMIN = 1.25
CLAP_LO, CLAP_HI = 0.6, 0.2                  # TONE: the low-pass share below 64 (x 2; 0.8 until 2026-11-21), the high-pass share above
CLAP_N = 8                                   # CNT: 1 .. 8 bursts
CLAP_GAIN = 1.1676 * KIT_TRIM                           # the type's level: the 808 point (its start) 2.0 dB under KICK 808 LONG, Vpp
CLAP_TOP = 0.99                              # the output held under this (a dense corner's rare peaks)
SVF_TOP = float(F(0.45 * FS))


def clap_count(knob: int) -> int:
    """CNT's bursts, 1 .. 8: 1 + (knob x 8) >> 7"""
    return 1 + ((int(knob) * CLAP_N) >> 7)


def clap_train(n: int, sp, hum, ramp, t0, rnd) -> list:
    """(sample, level) of each of N bursts (clap.train): times t0 + sp (1 + 0.35 HUMN r) apart (rounded to samples),
    levels over the train 1 + RAMP (i / (n - 1) - 0.5) x (1 + 0.25 HUMN r), at least 0.05; two draws a burst"""
    kt, kl = F(F(hum) * F(0.35)), F(F(hum) * F(0.25))
    if n > 1:
        step = F(F(ramp) * recipp(F(n - 1)))
        lv = F(F(F(ramp) * F(-0.5)) + F(1.0))
    else:
        step, lv = F(0.0), F(1.0)
    t, out = F(t0), []
    for _ in range(n):
        m = F(F(kl * rnd()) + F(1.0))
        out.append((math.trunc(float(F(t + F(0.5)))), max(F(lv * m), F(0.05))))
        m = F(F(kt * rnd()) + F(1.0))
        t = F(t + F(F(sp) * m))
        lv = F(lv + step)
    return out


class Clap:
    """CLAP. Page 1: TUNE DCAY TONE CNT SPRD TAIL DRIV (TYPE on H); page 2: SNAP Q HUMN GRP TLTN TATK RAMP VEL (VEL on
    H: PERC's TYPE record, q7). Noise through saw-shaped bursts (the 808's hand VCA) into a band-pass; the tail
    (the 808's reverberation VCA) on its own band with a rise and a long faint floor; a second clapper (GRP) always
    run, its level 0 when off; the soft clip; the output held under 0.99."""
    P1 = ("TUNE", "DCAY", "TONE", "CNT", "SPRD", "TAIL", "DRIV")
    P2 = ("SNAP", "Q", "HUMN", "GRP", "TLTN", "TATK", "RAMP", "VEL")
    # the start: the 808 point (891 Hz Q 1.29, 3 + 1 bursts 9.4 ms apart, 4.5 ms teeth, tail 266 ms, a 3 ms rise)
    D1 = dict(TUNE=58, DCAY=48, TONE=52, CNT=56, SPRD=63, TAIL=40, DRIV=5)     # (stage 5: TAIL 79 as the balance)
    D2 = dict(SNAP=52 / 127, Q=37 / 127, HUMN=0.0, GRP=0.0, TLTN=64 / 127, TATK=52 / 127, RAMP=64 / 127, VEL=64 / 127)

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        self.k1 = {**self.D1, **(p1 or {})}
        self.k2 = {**self.D2, **(p2 or {})}
        self.noise = Noise(seed)
        self.noise2 = Noise(JRNG_SEED)               # GRP's clapper (drum_v4's seed ^ 0x5A5A)
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.svf = [Svf(), Svf(), Svf()]             # the bursts' band, the tail's, GRP's

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        k1, k2 = self.k1, self.k2
        u = u_of(k1)
        vm = vel_mod(k2["VEL"], vel)
        # the band: 1 kHz x 2^(TUNE + note), a soft hit darker (x 2^((vm - 1) / 2)); Q; the tail's x 2^(2 (TLTN - 0.5)),
        # Q x 0.6; GRP's x 1.26, Q x 0.8
        x = F(tune_x(k1["TUNE"], note) + F(F(vm + F(-1.0)) * F(0.5)))
        fc = F(exp2p(x) * F(CLAP_HZ))
        q = expop(k2["Q"], *CLAP_Q)
        fct = F(fc * exp2p(F(F(F(k2["TLTN"]) + F(-0.5)) * F(2.0))))
        for s, (f, qq) in zip(self.svf, ((fc, q), (fct, F(q * F(CLAP_TAIL_QX))),
                                         (F(fc * F(CLAP_GRP_RATIO)), F(q * F(CLAP_GRP_QX))))):
            s.set(min(float(f), SVF_TOP), float(qq))
        # the bands' levels held: nb = sqrt(1000 / (q fc)) (noise through bp x r has power ~ fc / Q); TONE's shares
        nb = exp2p(F(log2p(F(recipp(F(max(q, F(CLAP_NB_QMIN)) * max(fc, F(CLAP_NB_FMIN)))) * F(CLAP_HZ))) * F(0.5)))
        t2 = F(u["TONE"] + u["TONE"])
        hi = F(max(F(t2 + F(-1.0)), F(0.0)) * F(CLAP_HI))
        lo = F(max(F(F(1.0) - t2), F(0.0)) * F(2.0 * CLAP_LO))
        gl = F(k2["GRP"])
        self.mix = []
        g1, g2 = balance(u["TAIL"])                  # stage 5: TAIL, the balance bursts / tail
        for nbk, w in ((F(nb * g1), None), (F(nb * F(CLAP_NB_T)), None), (F(F(nb * F(CLAP_NB_G)) * g1), gl)):
            m = (F(lo * nbk), nbk, F(hi * nbk))
            self.mix.append(m if w is None else tuple(F(v * w) for v in m))
        # the bursts: CNT of them SPRD apart, HUMN, RAMP; GRP's clapper SPRD x 1.07 apart from 0.3 .. 0.7 SPRD on
        n = clap_count(k1["CNT"])
        sp = expop(u["SPRD"], CLAP_SPRD[0] * FS, CLAP_SPRD[1] * FS)
        hum = F(k2["HUMN"])
        ramp = F(F(F(k2["RAMP"]) + F(-0.5)) * F(1.2))
        self.bursts = clap_train(n, sp, hum, ramp, 0.0, self.noise)
        off = F(F(F(self.noise2() * F(0.2)) + F(0.5)) * sp)
        self.gbursts = clap_train(n, F(sp * F(CLAP_GRP_SP)), max(hum, F(0.5)), ramp, off, self.noise2)
        self.b_d = coefp(expop(F(F(1.0) - F(k2["SNAP"])), CLAP_SNAP[0] * FS, CLAP_SNAP[1] * FS), -1.0)
        t60 = expop(u["DCAY"], CLAP_T60[0] * FS, CLAP_T60[1] * FS)
        self.t_d = coefp(t60, -LN_THOUSAND)
        self.fl_d = coefp(min(F(t60 * F(CLAP_FLOOR_X)), F(CLAP_FLOOR_MAX * FS)), -LN_THOUSAND)
        self.t_rise = F(F(1.0) - coefp(expop(k2["TATK"], CLAP_TATK[0] * FS, CLAP_TATK[1] * FS), -1.0))
        tq = exp2p(min(F(F(F(k2["Q"]) + F(-CLAP_TQ_U0)) * F(-CLAP_TQ_K)), F(0.0)))   # the tail's trim above Q 64
        self.t_lvl = F(F(g2 + g2) * tq)
        g = F(F(F(u["DRIV"] * u["DRIV"]) * F(20.0)) + F(1.0))
        self.comp = drive_comp(g, CLAP_GAIN)
        self.g = F(g * vm)                           # velocity into the clip (stage 3's)
        if self.on:
            self.dk = self.last
        self.on = True
        self.n = 0
        self.ia = self.ig = 0
        self.eb = self.eg = self.et = self.ef = F(0.0)
        self.rising = False

    def sample(self) -> np.float32:
        n = self.n
        x = self.noise()
        if self.ia < len(self.bursts) and n == self.bursts[self.ia][0]:
            self.eb = self.bursts[self.ia][1]
            self.ia += 1
            if self.ia == len(self.bursts):          # the tail opens with the last burst
                self.rising = True
                self.ef = F(CLAP_FLOOR)
        if self.ig < len(self.gbursts) and n == self.gbursts[self.ig][0]:
            self.eg = self.gbursts[self.ig][1]
            self.ig += 1

        def band(k: int, u: np.float32) -> np.float32:
            lp, bp, hp = self.svf[k].tick(u)
            la, ba, ha = self.mix[k]
            return F(F(F(la * lp) + F(ba * bp)) + F(ha * hp))
        y = band(0, F(x * self.eb))
        self.eb = F(self.eb * self.b_d)
        if self.rising:
            self.et = F(self.et + F(F(F(1.0) - self.et) * self.t_rise))
            if self.et > F(0.98):
                self.rising = False
        else:
            self.et = F(self.et * self.t_d)
        u = F(F(x * F(self.et + self.ef)) * self.t_lvl)
        self.ef = F(self.ef * self.fl_d)
        y = F(y + band(1, u))
        y = F(y + band(2, F(self.noise2() * self.eg)))
        self.eg = F(self.eg * self.b_d)
        out = F(soft(F(y * self.g)) * self.comp)
        out = F(out + self.dk)
        self.dk = F(self.dk * self.dk_d)
        out = min(max(out, F(-CLAP_TOP)), F(CLAP_TOP))
        self.last = out
        self.n += 1
        return out

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            out[i] = self.sample()
        return out


# CYMBAL (RIDE, CRASH): the hats' metal (six squares, COLR's bend and ring pairs, NOIS, DRFT) into the 808 cymbal's three
# bands on three envelopes: the BELL pair (2.94 / 3.27 kHz x TUNE x the SET's ratio, Q 75 / 32) on DCAY x 1.3, the BODY
# (7.15 kHz x TONE, Q 2.6) on DCAY, gliding up from SWEL x 2 octaves down (retuned every half) and swelling from 1 - SWEL,
# the TOP (the metal's first difference under a 12 kHz one-pole) on HIT; the stick (SNAP), the rivets (RIVT: |noise|
# over 0.94, high-passed, on the bell's envelope), ATK's 60 dB swell (all three held until it ends), the soft clip
CYM_SETS = (                                 # SET (page 2 A, four detents): the six squares (Hz at TUNE 0, note 60), the bell's ratio
    ("808", (205.3, 304.4, 369.6, 522.7, 540.0, 800.0), 1.0),
    ("WIDE", tuple(205.3 * r for r in (1.0, 1.47, 1.98, 2.73, 3.42, 4.61)), 0.82),
    ("CLUSTER", tuple(300.0 * r for r in (1.0, 1.06, 1.13, 1.19, 1.27, 1.34)), 1.12),
    ("LOW", tuple(140.0 * r for r in (1.0, 1.34, 1.71, 2.12, 2.6, 3.19)), 0.62),
)
SET_NAMES = tuple(s[0] for s in CYM_SETS)
CYM_LOG2 = tuple(tuple(float(F(math.log2(f / fr[0]))) for f in fr) for _n, fr, _b in CYM_SETS)
CYM_R0 = tuple(float(F(fr[0] / HAT_F808[0])) for _n, fr, _b in CYM_SETS)   # the first square against the hats' 205.3 Hz
CYM_BELL_R = tuple(float(F(b)) for _n, _f, b in CYM_SETS)
BELL_HZ, BELL_Q, BELL_W = (2944.0, 3265.0), (75.0, 32.0), (1.4, 1.0)
CYM_BODY_HZ, CYM_BODY_Q = 7150.0, 2.6
CYM_TOP_LVL, CYM_TOP_HZ = 0.7, 12000.0
CYM_T60 = (0.15, 12.0)                       # DCAY: the body's T60 (the bell's x 1.3)
BELL_TX = 1.3
CYM_HIT_T60 = (0.02, 3.0)                    # HIT: the top's T60
CYM_ATK = (0.005, 2.0)                       # ATK: the swell's length (0 = none)
SWEL_OCT, SWEL_TAU, SWEL_AMP = 2.0, (0.05, 0.40), 0.12
CYM_SNAP_TAU, CYM_SNAP_MAX = 0.0015, 3.0
RIVT_TH, RIVT_HZ, RIVT_MAX = 0.94, 2500.0, 0.3
BELL_FLOOR = 2.0 ** -20                      # BELL^1.5 = BELL sqrt(max(BELL, this)): exactly 0 at BELL 0
CYM_BAL_K = {"RIDE": 0.905511811375618, "CRASH": 0.6850393712520599}   # stage 5: the NOIS balance x the old start's metal share
CYM_GAIN = {"RIDE": 1.5420 * KIT_TRIM, "CRASH": 1.0901 * KIT_TRIM}  # (2026-11-21: the level held into the clip)  # the types' levels: their starts 6.6 dB under KICK 808 LONG, Vpp
CYM_TOP = 0.99
# (2026-11-21, no setting reaches the soft clip's flat top: with the level held after the clip, its input reached 5.1
# (RIDE) and 3.9 (CRASH) at DRIV 0, the flat top from 3) the level held (1 / h: the stick, the bell, the ring, the
# noise) goes INTO the clip, x g x vm: the same level below the clip's knee, its input at most ~0.9 at DRIV 0
# and the level held against the pitch above an octave up (TUNE + the note): the top band (the metal's first
# difference) grows with it, the clip's input 1.84 at TUNE 123, note 97 against 0.86 at TUNE 64: x 2^(-0.3 (x - 1)),
# x = (st + note - 60) / 12 octaves, x <= 1 unchanged (every start at notes up to 72)
CYM_TH_X0, CYM_TH_A = 1.0, 0.3


def cym_set(q: float) -> int:
    """SET's choice (808 WIDE CLUSTER LOW) from its page-2 value: its knob (knob_of), (knob x 4) >> 7, as the page"""
    return (knob_of(q) * 4) >> 7


class Cymbal:
    """RIDE / CRASH (one code; KIND picks the start and the level). Page 1: TUNE DCAY TONE BELL COLR HIT DRIV (TYPE
    on H); page 2: SET SWEL ATK SNAP NOIS DRFT RIVT VEL."""
    P1 = ("TUNE", "DCAY", "TONE", "BELL", "COLR", "HIT", "DRIV")
    P2 = ("SET", "SWEL", "ATK", "SNAP", "NOIS", "DRFT", "RIVT", "VEL")
    STARTS = {
        "RIDE": (dict(TUNE=64, DCAY=76, TONE=64, BELL=103, COLR=44, HIT=90, DRIV=10),
                 dict(SET=0.0, SWEL=12 / 127, ATK=0.0, SNAP=50 / 127, NOIS=7 / 127, DRFT=64 / 127, RIVT=0.0,
                      VEL=64 / 127)),
        "CRASH": (dict(TUNE=64, DCAY=86, TONE=74, BELL=121, COLR=100, HIT=84, DRIV=16),
                  dict(SET=48 / 127, SWEL=72 / 127, ATK=0.0, SNAP=64 / 127, NOIS=29 / 127, DRFT=80 / 127, RIVT=0.0,
                       VEL=64 / 127)),
    }
    KIND = "RIDE"

    def __init__(self, p1: dict | None = None, p2: dict | None = None, seed: int = 0x21):
        d1, d2 = self.STARTS[self.KIND]
        self.k1 = {**d1, **(p1 or {})}
        self.k2 = {**d2, **(p2 or {})}
        self.noise = Noise(seed)
        self.jrng = Noise(JRNG_SEED)
        self.drift = [F(0.0)] * 6
        self.on = False
        self.last = F(0.0)
        self.dk = F(0.0)
        self.dk_d = tau_coef(DECLICK_S)
        self.svf = [Svf(), Svf(), Svf()]             # the bell pair, the body
        self.top_a = onepole_a(CYM_TOP_HZ)
        self.rv_a = onepole_a(RIVT_HZ)
        self.snap_d = tau_coef(CYM_SNAP_TAU)

    def trig(self, note: float = 60.0, vel: float = 1.0) -> None:
        k1, k2 = self.k1, self.k2
        u = u_of(k1)
        vm = vel_mod(k2["VEL"], vel)
        tr = exp2p(tune_x(k1["TUNE"], note))
        s = cym_set(k2["SET"])
        # COLR, the squares' increments (the hats' arithmetic: the SET's octaves over its first, its first x 205.3 Hz)
        c = u["COLR"]
        w = min(F(c * F(1.0 / 0.7)), F(1.0))
        warp = F(F(F(w + F(-0.5)) * F(0.8)) + F(1.0))
        ring = max(F(F(c + F(-0.7)) * F(1.0 / 0.3)), F(0.0))
        tr0 = F(tr * F(CYM_R0[s]))
        self.inc0 = []
        for lg in CYM_LOG2[s]:
            a = F(F(exp2p(F(warp * F(lg))) * F(HAT_BASE)) * tr0)
            a = min(a, F(HAT_INC_TOP))
            self.inc0.append(F(a * F(2.0 ** 32)))
        self.inc = [math.trunc(float(x)) for x in self.inc0]
        self.ph = list(HAT_PH0)
        g1, g2 = balance(k2["NOIS"])                 # stage 5: NOIS, the balance metal / noise, x the kind's CYM_BAL_K
        bk = F(CYM_BAL_K[self.KIND])
        omm, mix = F(g1 * bk), F(g2 * bk)
        self.mix = mix
        self.ka = F(F(F(F(1.0) - ring) * omm) * F(1.0 / 6.0))
        self.kb = F(F(ring * omm) * F(1.0 / 3.0))
        # the bands: the bell pair x clamp(tr, 1/4, 4) x the SET's ratio, the body at 7.15 kHz x 2^(3 (TONE - 0.5)) x
        # 2^((vm - 1) / 2), from SWEL x 2 octaves under it
        xt = F(F(F(u["TONE"] + F(-0.5)) * F(3.0)) + F(F(vm + F(-1.0)) * F(0.5)))
        self.fb = min(F(exp2p(xt) * F(CYM_BODY_HZ)), F(SVF_TOP))
        trc = F(min(max(tr, F(0.25)), F(4.0)) * F(CYM_BELL_R[s]))
        sw = F(k2["SWEL"])
        self.swx = F(sw + sw)
        self.sw_d = coefp(expop(sw, SWEL_TAU[0] * FS / HALF, SWEL_TAU[1] * FS / HALF), -1.0)
        for sv_, (f, q) in zip(self.svf, ((F(trc * F(BELL_HZ[0])), BELL_Q[0]), (F(trc * F(BELL_HZ[1])), BELL_Q[1]),
                                          (F(self.fb * exp2p(F(-self.swx))), CYM_BODY_Q))):
            sv_.set(min(float(f), SVF_TOP), q)
        self.swa = sw
        self.swa_d = coefp(max(F(sw * F(SWEL_AMP * FS)), F(1e-4 * FS)), -1.0)
        # levels: BELL 4 BELL^1.5 (the pair's weights 1.4 / 75 and 1 / 32: bp x r), RIVT 0.3 RIVT^2
        b, self.wg = balance(u["BELL"])              # stage 5: BELL, the balance bell / wash
        bl = F(F(b * F(4.0)) * exp2p(F(log2p(max(b, F(BELL_FLOOR))) * F(0.5))))
        self.wa, self.wb = F(bl * F(BELL_W[0] / BELL_Q[0])), F(bl * F(BELL_W[1] / BELL_Q[1]))
        self.rivt = F(F(F(k2["RIVT"]) * F(k2["RIVT"])) * F(RIVT_MAX))
        # the envelopes: the bell DCAY x 1.3, the body DCAY, the top HIT; ATK's swell
        t60 = expop(u["DCAY"], CYM_T60[0] * FS, CYM_T60[1] * FS)
        self.d1 = coefp(F(t60 * F(BELL_TX)), -LN_THOUSAND)
        self.d2 = coefp(t60, -LN_THOUSAND)
        self.d3 = coefp(expop(u["HIT"], CYM_HIT_T60[0] * FS, CYM_HIT_T60[1] * FS), -LN_THOUSAND)
        a = F(k2["ATK"])
        if a > F(0.0):
            self.atk_n = math.trunc(float(expop(a, CYM_ATK[0] * FS, CYM_ATK[1] * FS)))
            self.atk_m = exp2p(F(F(math.log2(1000.0)) * recipp(F(self.atk_n))))
            self.ra = F(1e-3)
        else:
            self.atk_n, self.atk_m, self.ra = 0, F(1.0), F(1.0)
        self.e1 = self.e2 = self.e3 = F(1.0)
        self.snap = F(F(F(k2["SNAP"]) * F(CYM_SNAP_MAX)) * F(F(vm * F(0.5)) + F(0.5)))
        # the drive; the level held against the stick, the bell, the ring and the noise; the type's level
        g = F(F(F(u["DRIV"] * u["DRIV"]) * F(20.0)) + F(1.0))
        h = F(F(F(self.snap * F(0.5)) + F(1.0)) * F(F(bl * F(0.25)) + F(1.0)))
        h = F(h * F(F(ring * F(0.5)) + F(1.0)))
        h = F(h * F(mix + F(1.0)))
        h = F(h * exp2p(F(max(F(tune_x(k1["TUNE"], note) + F(-CYM_TH_X0)), F(0.0)) * F(CYM_TH_A))))   # the pitch
        self.comp = drive_comp(g, CYM_GAIN[self.KIND])
        self.g = F(F(g * vm) * recipp(h))            # the level held into the clip
        # DRFT: the hats'
        dr = F(F(k2["DRFT"]) * F(127.0 / 64.0))
        jd = F(dr * F(JIT))
        self.jit = []
        for x in self.inc0:
            y = max(F(x * F(16.0 / 2.0 ** 32)), F(16.0 / FS))
            self.jit.append(F(exp2p(F(log2p(y) * F(-0.5))) * jd))
        self.dstep = F(dr * F(DRIFT_STEP))
        self.tl1 = self.tl2 = self.rl = F(0.0)
        self.n = 0
        if self.on:
            self.dk = self.last
        self.on = True

    def half(self) -> None:
        """each 16 samples: DRFT (the hats'), the body's glide (SWEL: retuned, its state kept)"""
        Hat.half(self)
        self.swx = F(self.swx * self.sw_d)
        fc = F(self.fb * exp2p(F(-self.swx)))
        b = self.svf[2]
        s1, s2 = b.s1, b.s2
        b.set(min(float(fc), SVF_TOP), CYM_BODY_Q)
        b.s1, b.s2 = s1, s2

    def sample(self) -> np.float32:
        if self.n % HALF == 0:
            self.half()
        sq = []
        for i in range(6):
            self.ph[i] = s32(self.ph[i] + self.inc[i])
            sq.append(F(1.0) if self.ph[i] < HAT_T else F(-1.0))
        metal = ((((sq[0] + sq[1]) + sq[2]) + sq[3]) + sq[4]) + sq[5]
        rm = (sq[0] * sq[1] + sq[2] * sq[3]) + sq[4] * sq[5]
        wn = self.noise()
        x = (metal * self.ka + rm * self.kb) + wn * self.mix
        bell = F(self.svf[0].tick(x)[1] * self.wa)
        bell = F(bell + F(self.svf[1].tick(x)[1] * self.wb))
        body = F(self.svf[2].tick(x)[1] * self.svf[2].r)
        self.tl2 = F(self.tl2 + F(F(F(x - self.tl1) - self.tl2) * self.top_a))
        self.tl1 = x
        c = wn if abs(wn) > F(RIVT_TH) else F(0.0)
        self.rl = F(self.rl + F(F(c - self.rl) * self.rv_a))
        if self.n < self.atk_n:
            self.ra = min(F(self.ra * self.atk_m), F(1.0))
            a1 = a2 = a3 = self.ra
        else:
            self.e1, self.e2, self.e3 = F(self.e1 * self.d1), F(self.e2 * self.d2), F(self.e3 * self.d3)
            a1, a2, a3 = self.e1, self.e2, self.e3
        k = F(F(self.snap + F(1.0)) * self.wg)
        self.snap = F(self.snap * self.snap_d)
        self.swa = F(self.swa * self.swa_d)
        y = F(bell * a1)
        y = F(y + F(F(F(body * a2) * F(F(1.0) - self.swa)) * k))
        y = F(y + F(F(F(self.tl2 * F(CYM_TOP_LVL)) * a3) * k))
        y = F(y + F(F(F(c - self.rl) * self.rivt) * a1))
        out = F(soft(F(y * self.g)) * self.comp)
        out = F(out + self.dk)
        self.dk = F(self.dk * self.dk_d)
        out = min(max(out, F(-CYM_TOP)), F(CYM_TOP))
        self.last = out
        self.n += 1
        return out

    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float32)
        if not self.on:
            return out
        for i in range(n):
            out[i] = self.sample()
        return out


class Ride(Cymbal):
    KIND = "RIDE"


class Crash(Cymbal):
    KIND = "CRASH"


TYPES = {"KICK": Kick, "SNARE": Snare, "CLHH": Hat, "OPHH": OpenHat, "TOM": Tom, "CLAP": Clap, "RIDE": Ride,
         "CRASH": Crash}


def render(p1: dict | None = None, p2: dict | None = None, hits=((0.0, 60.0, 1.0),), seconds: float = 1.0,
           seed: int = 0x21, kind: str = "KICK") -> np.ndarray:
    """a track of hits of one type [(time s, note, velocity 0..1)]"""
    v = TYPES[kind](p1, p2, seed)
    n = int(seconds * FS)
    out = np.zeros(n, dtype=np.float32)
    pos = 0
    for t, note, vel in sorted(hits) + [(seconds, None, None)]:
        at = min(int(t * FS), n)
        out[pos:at] = v.render(at - pos)
        pos = at
        if note is not None:
            v.trig(note, vel)
    return out
