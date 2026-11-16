# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG 2's filter models in float32, operation by operation: the contract dnfw.a2f.models (and the
filter pass, dnfw.a2f.program) is held to bit for bit. Ported from Optimist (GPL-3.0-only),
firmware/src/engines/analog/a2_models.c and eng_analog2.c (ANALOG 2's SVF).

Every value is a numpy float32 and every operation rounds as the SHARC's (round to nearest), in the
DSP code's order. Against the C (a2_models.c compiled with -ffp-contract=off, and the SVF's integer
C), what differs and why:

- a division is a reciprocal: the seed 0x7ef311c7 - bits, then three Newton steps r = 2r - r (x r);
- g = tan(pi fc / FS): exp2 of the cutoff by a polynomial (dnfw.fdn8's), tan by tan(2u) = 2t / (1 -
  t^2), t = tan(u) a polynomial (rel 6e-8); the C's fm_exp2f / fm_tanf are other approximations;
- the SVF (Q-integer in the C) in float: g exact, not SVF_G's Q12 table (whose truncation moves the
  lowest cutoffs: SVF_G[0] = 8 for 8.75); its damping a2_k continuous in RES; its states' knees with
  the Pade tanh (the C's softclip is tanh by a 257-point table: tanh(2) = 0.964 where the Pade gives
  0.984): the self-oscillation's level follows that;
- DIOD's 4 x 4 system y = (I - g A)^-1 (s + g u e1) is solved per sample by elimination (Thomas: the
  matrix is tridiagonal), not as the inverse a segment (Gauss-Jordan): the same values, other roundings;
- LADR/OTA, DIOD and MS20 mix their outputs by table rows (the C's own coefficients for the first two);
  every term the C leaves out is a product by 0, which adds nothing;
- the SVF's LP24: the C clamps its second stage's input to +-2; here the first stage's output (which
  only the second stage reads); every other output is clamped to +-32 (the C's A2M_OUT, the SVF none:
  its states are bounded by their knees).
"""

from __future__ import annotations

import numpy as np

from . import models as M

F = np.float32
Z = F(0.0)


def bits(x) -> int:
    return int(np.array(x, dtype=np.float32).view(np.uint32))


def flt(b: int):
    return np.array(b & 0xFFFFFFFF, dtype=np.uint32).view(np.float32)[()]


def fmin(a, b):
    return a if a < b else b


def fmax(a, b):
    return a if a > b else b


def newton(x, r):
    for _ in range(3):
        t = x * r
        t = r * t
        r = r + r
        r = r - t
    return r


def recip(x):
    return newton(x, flt(M.RECIP_MAGIC - bits(x)))


def tanh(x):
    x = fmin(x, F(3.0))
    x = fmax(x, F(-3.0))
    x2 = x * x
    den = F(9.0) * x2
    den = F(27.0) + den
    num = F(27.0) + x2
    num = x * num
    return num * recip(den)


def poly(c, x):
    d = F(c[-1])
    for k in range(len(c) - 2, -1, -1):
        d = d * x
        d = d + F(c[k])
    return d


def g_of(cut):
    """g = tan(pi fc / FS) at CUT units (clamped to 0..127)"""
    x = fmin(fmax(F(cut), Z), F(127.0))
    x = x * F(M.K_OCT)
    n = int(x)
    x = x - F(n)
    e = poly(M.EXP2_C, x)
    e = e * flt((n + 127) << 23)
    u = e * F(M.W0H)
    u = fmin(u, F(M.UMAX))
    z = u * u
    t = poly(M.TAN_C, z)
    t = u * t
    d = t * t
    d = F(1.0) - d
    t = t + t
    return t * newton(d, flt(M.RECIP_MAGIC - bits(d)))


def svf_k(res):
    res = F(res)
    k = res * F(M.SVF_K1)
    k = F(2.0) - k
    d = res - F(100.0)
    if d > Z:
        d = d * d
        d = d * F(M.SVF_K2)
        k = k - d
    return k


def svf_coef(g, k):
    t = g + k
    t = g * t
    t = F(1.0) + t
    a1 = recip(t)
    a2 = g * a1
    a3 = g * a2
    return [a1, a2, a3]


def knee(x, lim):
    a = abs(x)
    if not a > F(lim):
        return x
    a = a - F(lim)
    if lim != 1.0:
        a = a * F(1.0 / lim)
    a = fmin(a, F(2.0))
    a = tanh(a)
    if lim != 1.0:
        a = a + a
    a = F(lim) + a
    return Z - a if x < Z else a


def svf_stage(buf, z, o, gs, ge, k, row):
    """one SVF stage over buf (16 floats, in place): states z[o], z[o + 1]; row = SVFMIX's"""
    c = svf_coef(gs, k)
    e = svf_coef(ge, k)
    d = [Z] * 3
    for i in range(3):
        d[i] = e[i] - c[i]
        d[i] = d[i] * F(1.0 / M.N)
        c[i] = c[i] + d[i]
    cx, cbk, cb1, cl, lim, nlim = (F(v) for v in row)
    cb = cbk * k
    cb = cb + cb1
    ic1, ic2 = z[o], z[o + 1]
    a1, a2, a3 = c
    for i in range(M.N):
        x = buf[i]
        v3 = x - ic2
        v1 = a1 * ic1
        v1 = v1 + a2 * v3
        v2 = a2 * ic1
        v2 = v2 + a3 * v3
        v2 = ic2 + v2
        ic1 = (v1 + v1) - ic1
        ic2 = (v2 + v2) - ic2
        y = cx * x
        y = y + cb * v1
        y = y + cl * v2
        y = fmax(fmin(y, lim), nlim)
        buf[i] = y
        ic1 = knee(ic1, 1.0)
        ic2 = knee(ic2, 2.0)
        a1 = a1 + d[0]
        a2 = a2 + d[1]
        a3 = a3 + d[2]
    z[o], z[o + 1] = ic1, ic2


def svf_half(buf, z, gs, ge, res, mode):
    k = svf_k(res)
    svf_stage(buf, z, 0, gs, ge, k, M.SVFMIX[mode])
    if mode == 1:
        svf_stage(buf, z, 2, gs, ge, F(M.K2ND), M.SVFMIX[5])


def _ratio(ge):
    r = recip(F(1.0) + ge)
    return r, ge * r


def ladder_half(buf, z, ge, res, mode, ota):
    k = F(res) * F(M.OTA_K if ota else M.LADR_K)
    if ota:
        cin = F(0.5) * k
        cin = F(1.0) + cin
    else:
        cin = F(1.0)
    _, G = _ratio(ge)
    H = F(1.0) - G
    G4 = G * G
    G4 = G4 * G
    G4 = G4 * G
    inv = recip(F(1.0) + k * G4)
    m = [F(v) for v in M.LMIX[mode]]
    z1, z2, z3, z4 = z
    for i in range(M.N):
        x = buf[i] * cin
        S = G * z1
        S = S + z2
        S = G * S
        S = S + z3
        S = G * S
        S = S + z4
        S = H * S
        t = k * S
        t = x - t
        t = t * inv
        if ota:
            a = G4 * t
            a = a + S
            u = tanh(a)
            u = k * u
            u = x - u
        else:
            u = tanh(t)
        ys = []
        yin = u
        zs = [z1, z2, z3, z4]
        for j in range(4):
            v = yin - zs[j]
            v = v * G
            y = v + zs[j]
            zs[j] = y + v
            ys.append(y)
            yin = y
        z1, z2, z3, z4 = zs
        o = m[0] * u
        for j in range(4):
            o = o + m[j + 1] * ys[j]
        buf[i] = fmax(fmin(o, F(M.OUT_MAX)), F(-M.OUT_MAX))
    z[:] = [z1, z2, z3, z4]


def diod_half(buf, z, ge, res, mode):
    k = F(res) * F(M.DIOD_K)
    cin = F(1.0) + F(0.5) * k
    gout = F(1.0) + k * F(M.DIOD_OUT)
    gd = ge * F(M.DIOD_GSC)
    t1 = gd + gd
    t1 = F(1.0) + t1
    g2 = gd * gd
    piv = t1
    ip, gp = [], []
    for i in range(4):
        r = recip(piv)
        ip.append(r)
        gp.append(gd * r)
        if i < 3:
            t = g2 * r
            piv = (t1 if i < 2 else F(1.0) + gd) - t
    h = [gp[0]]
    for i in (1, 2, 3):
        h.append(gp[i] * h[-1])
    inv = recip(F(1.0) + k * h[3])
    m = [F(v) for v in M.DMIX[mode]]
    s = list(z)
    for i in range(M.N):
        x = buf[i]
        e = [s[0] * ip[0]]
        for j in (1, 2, 3):
            t = gd * e[-1]
            t = s[j] + t
            e.append(t * ip[j])
        a = x * cin
        a = a - k * e[3]
        a = a * inv
        u = tanh(a)
        y = [e[j] + h[j] * u for j in range(4)]
        y[2] = y[2] + gp[2] * y[3]
        y[1] = y[1] + gp[1] * y[2]
        y[0] = y[0] + gp[0] * y[1]
        for j in range(4):
            s[j] = (y[j] + y[j]) - s[j]
        o = m[0] * u
        for j in range(4):
            o = o + m[j + 1] * y[j]
        o = gout * o
        buf[i] = fmax(fmin(o, F(M.OUT_MAX)), F(-M.OUT_MAX))
    z[:] = s


def ms20_half(buf, z, ge, res, mode):
    k = F(res) * F(M.MS20_K)
    h, G = _ratio(ge)
    omG = F(1.0) - G
    t = k * G
    t = t * omG
    dn = recip(F(1.0) - t)
    Gk = G * k
    cx, cb, cy, cl = (F(v) for v in M.MSMIX[mode])
    s1, s2, s4 = z[0], z[1], z[3]
    for i in range(M.N):
        x = buf[i]
        a = G * x
        b = Gk * s2
        b = s1 - b
        b = b * h
        a = a + b
        a = a * dn
        c = omG * a
        s2h = s2 * h
        c = c - s2h
        f = k * tanh(c)
        xf = x + f
        y1 = G * xf
        y1 = y1 + s1 * h
        y2 = G * y1
        y2 = y2 + s2h
        s1 = (y1 + y1) - s1
        s2 = (y2 + y2) - s2
        bp = y1 - y2
        bp = bp + bp
        v = y2 - s4
        v = v * G
        l4 = v + s4
        s4 = l4 + v
        o = cx * xf
        o = o - cb * bp
        o = o - cy * y2
        o = o + cl * l4
        buf[i] = fmax(fmin(o, F(M.OUT_MAX)), F(-M.OUT_MAX))
    z[0], z[1], z[3] = s1, s2, s4


def half(model, buf, z, gs, ge, res, mode):
    """model (0..4) over 16 floats of buf in place; z its 4 state floats (a list, updated)"""
    if model == M.SVF:
        svf_half(buf, z, gs, ge, res, mode)
    elif model in (M.LADR, M.OTA):
        ladder_half(buf, z, ge, res, mode, model == M.OTA)
    elif model == M.DIOD:
        diod_half(buf, z, ge, res, mode)
    elif model == M.MS20:
        ms20_half(buf, z, ge, res, mode)


GUARD = 0x461C4000                       # bits of 1e4: a state at or past it (or NaN) clears all four


def guard(z) -> None:
    if any((bits(v) & 0x7FFFFFFF) >= GUARD for v in z):
        z[:] = [Z, Z, Z, Z]


def block(model, mode, res, c0, cut, z, buf):
    """a2m_block / a2_filter's shape over 32 floats: the cutoff c0 -> cut (CUT units) in two halves,
    the SVF's coefficients ramped from g(c0), the models' at each half's end"""
    guard(z)
    mid = F(c0) + (F(cut) - F(c0)) * F(0.5)
    g = [g_of(c0), g_of(mid), g_of(cut)]
    for h in range(2):
        seg = buf[16 * h:16 * h + 16]
        half(model, seg, z, g[h], g[h + 1], F(res), mode)
        buf[16 * h:16 * h + 16] = seg


# -- the pass (dnfw.a2f.program), over a memory image ----------------------------------------------
def _word(mem, a) -> int:
    return mem.get(a) & 0xFFFFFFFF


def _f(mem, a):
    return flt(_word(mem, a))


def _put(mem, a, x) -> None:
    mem.put(a, x if isinstance(x, int) else bits(x))


def _half16(mem, base, i) -> int:
    w = _word(mem, base + 4 * (i >> 1))
    return (w >> 16 if i & 1 else w) & 0xFFFF


def _clamp(x, lo, hi):
    return fmin(fmax(x, F(lo)), F(hi))


def _choice(x) -> int:
    return min(4, int(_clamp(x, 0.0, 1.0) * F(5.0)))


def pass_ref(mem, models=None) -> None:
    """the filter pass over MEM (a dnfw.perc.dsl.Mem), as dnfw.a2f.program.body does it"""
    from . import program as P
    from ..fdn8 import ref as FR
    X = P.ctx(models)
    built = [M.MODELS.index(m) for m in X.models]
    if not built:
        return
    for s in range(16):
        sp = P.STATE + 64 * s
        tr = _half16(mem, P.ROUTE, s)
        m1 = 0
        if tr <= 15:
            model = _half16(mem, P.FTYPE, tr) - P.TYPE0
            if model in built:
                m1 = model + 1
        if not m1:
            _put(mem, sp + 4 * P.TAG, 0)
            continue
        if _word(mem, sp + 4 * P.TAG) != m1 or _word(mem, sp + 4 * P.TRK) != tr:
            for k in range(P.SLOT_WORDS):
                _put(mem, sp + 4 * k, 0)
            _put(mem, sp + 4 * P.C01, F(P.NONE))
            _put(mem, sp + 4 * P.C02, F(P.NONE))
            _put(mem, sp + 4 * P.TAG, m1)
            _put(mem, sp + 4 * P.TRK, tr)
        model = m1 - 1
        rec = P.RECORDS + P.RECORD_STRIDE * tr

        def r(off):
            return _f(mem, rec + off)
        filt = [(_clamp(r(P.R_FREQ) * F(128.0), 0.0, 127.0), _clamp(r(P.R_RES) * F(128.0), 0.0, 127.0),
                 _choice(r(P.R_MODE1)), 0),
                (_clamp(r(P.R_FRQ2) * F(127.0), 0.0, 127.0), _clamp(r(P.R_RES2) * F(127.0), 0.0, 127.0),
                 _choice(r(P.R_MODE2)), 4 * P.Z2)]
        dmod = (r(P.R_ENV) - F(0.5)) * F(P.ENV_UNITS)
        key = _clamp(r(P.R_KEY), 0.0, P.KEY_MAX)
        nb = _word(mem, P.NOTES + 4 * tr)
        note = Z if ((nb >> 23) & 0xFF) == 0xFF or nb >> 31 else flt(nb)
        kmod = key * (note - F(60.0))
        kmod = kmod * F(P.UNITS_PER_SEMI)
        step = FR.exp2(F(P.ATK_A0) + _clamp(r(P.R_ATK), 0.0, 1.0) * F(-P.ATK_A1))
        coef = FR.exp2(FR.exp2(_clamp(r(P.R_DEC), 0.0, 1.0) * F(-P.DEC_A1)) * F(-P.DEC_K))
        if (_word(mem, P.TRIGW) >> 16) & (1 << tr):
            _put(mem, sp + 4 * P.STG, 1)
        lvl = _f(mem, sp + 4 * P.LVL)
        stg = _word(mem, sp + 4 * P.STG)
        lv = []
        for _ in range(2):
            if stg:
                lvl = lvl + step
                if lvl >= F(1.0):
                    lvl, stg = F(1.0), 0
            else:
                lvl = lvl * coef
            lv.append(lvl)
        _put(mem, sp + 4 * P.LVL, lvl)
        _put(mem, sp + 4 * P.STG, stg)
        bufb = _word(mem, P.BUFFERS + 4 * s)
        for base, res, mode, zoff in filt:
            bk = base + kmod
            cA = _clamp(bk + dmod * lv[0], 0.0, 127.0)
            cB = _clamp(bk + dmod * lv[1], 0.0, 127.0)
            zp = sp + zoff
            c0 = _f(mem, zp + 16)
            if c0 < Z:
                c0 = cB
            _put(mem, zp + 16, cB)
            z = [_f(mem, zp + 4 * k) for k in range(4)]
            if any((bits(v) & 0x7FFFFFFF) >= GUARD for v in z):
                z = [Z] * 4
            g = [g_of(c0) if model == M.SVF else c0, g_of(cA), g_of(cB)]
            for h in range(2):
                a = bufb + 64 * h
                buf = [_f(mem, a + 4 * i) for i in range(M.N)]
                half(model, buf, z, g[h], g[h + 1], res, mode)
                for i in range(M.N):
                    _put(mem, a + 4 * i, buf[i])
            for k in range(4):
                _put(mem, zp + 4 * k, z[k])
