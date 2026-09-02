#!/usr/bin/env python3
"""ringdown.py — measure the geophone's damping ratio from a tap, and size a shunt.

WHY. The rev-2 interface board has an empty screw-down socket across AIN0/AIN1 for a
shunt damping resistor. Whether to fit one, and what value, is a MEASUREMENT, not a
datasheet lookup: our element is from a mislabelled listing, so its moving mass and
generator constant are not trustworthy, and it may already be damped internally.

This does two jobs:

  measure   Fit the decay of a tap's ring-down and report the damping ratio, zeta.
  solve     Given TWO measurements (no shunt, and one known trial shunt), solve for
            the element's electrical-damping constant and print the resistor needed
            for any target zeta -- plus what it costs in sensitivity.

THE PHYSICS, so the two-point method is checkable:

  A tapped geophone rings as  A(t) = A0 * exp(-alpha*t) * cos(omega_d*t)
  with  alpha = zeta*omega_0  and  omega_d = omega_0*sqrt(1 - zeta^2).
  Those combine exactly:  omega_0 = hypot(alpha, omega_d),  zeta = alpha/omega_0.
  So fitting the envelope decay and reading the ringing frequency is sufficient --
  no need to know f0 in advance, and no small-zeta approximation.

  Damping splits into mechanical (fixed) and electrical (what the shunt buys):
      zeta = zeta_mech + k / (Rc + R_load),     k = G^2 / (2*M*omega_0)
  k folds up the generator constant and moving mass we do not trust. Measure zeta at
  two known loads and k drops out of the algebra.

THE TRADEOFF, which is why this is not a default. A shunt damps by LOADING the coil,
so the ADC sees Rs/(Rc+Rs) of the open-circuit voltage. Absolute calibration is
already ~7.5x low and this station is explicitly sensitivity-first, so deliberate
UNDER-damping is defensible. `solve` prints the sensitivity cost next to every
candidate so the choice is made with both numbers visible.

    python ringdown.py measure tap.npz
    python ringdown.py solve --z0 0.31 --z1 0.55 --r1 1000
"""
import argparse
import math
import sys

import numpy as np
from scipy import signal

F_ELEMENT = 4.5          # nominal element resonance, Hz
RC_COIL = 375.0          # geophone coil resistance, ohms
R_BIAS = 200_000.0       # the rev-1/2 bias network across the coil: 2 x 100k in
                         # series. Effectively open next to a shunt, but carried
                         # explicitly so "no shunt" is not silently "infinite load".


def zeta_from_ringdown(x, fs, f_lo=0.05, f_hi=45.0, win_s=4.0, f_expect=F_ELEMENT,
                       z_max=0.8):
    """Damping ratio from one ring-down burst.

    Fits the FULL damped-sinusoid model  A*exp(-alpha*t)*cos(w_d*t + phi)  by least
    squares. Two things this had to get right, both found by testing against
    synthetic ring-downs of KNOWN zeta -- and both only bite in the well-damped
    regime, which is exactly the regime where the answer is "leave the socket empty":

      1. Fitting the log-envelope slope and taking w_d from zero crossings works
         only when the element rings for many cycles. Above zeta ~ 0.3 it rings for
         barely one and both estimators run out of data.
      2. The pass-band must be WIDE, and the high-pass corner LOW. A heavily damped
         resonance is broad (Q ~ 0.7) with energy well below f0, so a snug 2-9 Hz
         filter read zeta 0.80 as 0.57, and even a 1 Hz corner over-read 0.60 as
         0.70. At 0.2 Hz the error is <= 0.02 out to zeta 0.70. A 4th-order corner
         that low still rejects the known sub-Hz thermal drift by ~250x, and the tap
         is ~300 uV against a ~1 uV drift, so nothing is at risk.
      3. The ringing frequency MUST be bounded near the element's resonance. Tapping
         the case excites the CASE's own modes, which for a firm tap are louder than
         the element -- an unbounded fit lands at 7-13 Hz against a 4.5 Hz element
         and returns a damping ratio for the wrong resonator entirely (measured on
         real data, 2026-08-10). Bounded to +-40 % of f_expect, a fit that wants to
         sit at the bound is a signal that the tap was too hard, not a result.
      4. The fit window must follow the burst. A fixed 4 s window is almost all
         noise once the ring dies in under a second, and least squares then pulls
         the amplitude toward zero and the decay toward nonsense.

    ACCURACY, first characterisation (taps, 60 uV and 300 uV on a 2 uV noise floor):
    within 0.02 for zeta <= 0.60; degrading above, and OVER-reading by 0.13-0.19 at
    zeta 0.80. SNR matters up there -- a 300 uV tap held the error to 0.03 at zeta 0.70
    where a 60 uV tap gave 0.13, so TAP FIRMLY. Full scale at gain 64 is +-78 mV and a
    normal tap is a few hundred uV, so there is ~200x of headroom to spend on
    signal-to-noise.

    ACCURACY, second characterisation (2026-09-02, ahead of the injector). Swept
    synthetic releases A*exp(-zeta*w0*t)*sin(w_d*t) at f0 4.5 Hz into realistic red
    noise, 12 seeds per cell, SNR = peak/background RMS:

        zeta      SNR 50      SNR 100     SNR 200
        0.30    +0.003        -0.001      -0.003
        0.60    -0.032        -0.041      -0.044
        0.75    -0.091        -0.092      -0.093
        0.85    -0.176        -0.145      -0.145

    Two things to take from that, and one unresolved.

    THE HARD LIMIT, now fixed. zeta 0.85 failed 11-12 times out of 12 at EVERY signal
    level including SNR 200 -- more signal cannot rescue an answer the bounds exclude.
    See the w_lo comment below: the old lower bound of 0.6*f_expect is exactly a ceiling
    of zeta = sqrt(1 - 0.6^2) = 0.80. That is now the `z_max` parameter.

    THE BIAS DOES NOT IMPROVE WITH SNR, so it is a method bias, not noise. Widening the
    fitter's band from 20 Hz to 45 Hz recovers about a third of it at zeta 0.85 (-0.145
    to -0.093) and none at 0.60, so band-limiting a short, broadband transient is a
    contributor but not the cause.

    RESOLVED (2026-09-02): the bias was THE FIT BAND, and the default is now wide.

    Run the estimator on a NOISELESS synthetic and the bias is still there, growing
    monotonically with zeta -- so it was never a noise effect, which is how two harnesses
    at different SNRs could disagree about its sign. The mechanism shows in the fitted
    w_d, which comes out systematically HIGH at large zeta (2.48 Hz against a true
    1.96 Hz at zeta 0.90); since zeta = alpha/hypot(alpha, w_d), over-reading w_d
    under-reads zeta.

    The cause is that a heavily damped ring-down is SHORT and therefore BROADBAND -- it
    is nearly a single pulse, with content from near-DC to tens of Hz. Band-passing to
    0.2-20 Hz truncates both tails and leaves something that looks more oscillatory and
    less decayed than the real transient. Widening the band fixes it, noiselessly:

        zeta      0.2-20 Hz    0.01-49 Hz
        0.30        -0.006        -0.001
        0.60        -0.047        -0.005
        0.85        -0.131        -0.008
        0.90        -0.159        -0.009

    On REAL archive noise at SNR 50, which is what the injector will actually deliver:

        zeta      0.2-20 Hz       0.05-45 Hz
        0.30   -0.006 +-0.01   +0.001 +-0.01
        0.60   -0.046 +-0.04   -0.005 +-0.07
        0.85   -0.066 +-0.13   -0.066 +-0.10

    So the default band is now 0.05-45 Hz. It trades a little scatter for most of the
    bias, which is the right trade HERE for a specific reason: bias does not average
    away and scatter does, and the injector fires 12 releases a day forever. A week is
    ~84 releases, so 0.10 of scatter becomes ~0.01 of standard error while a 0.046 bias
    would have stayed 0.046 no matter how long we waited.

    STILL OPEN: the -0.066 residual at zeta 0.85 on real noise, which widening does not
    touch. If the element turns out that heavily damped, average hard and quote it with
    the caveat. The injector settles this empirically -- a known, repeatable stimulus
    many times a day is exactly the input neither synthetic characterisation had.

    Do NOT narrow this band back to reject drift. The high-pass is not the right tool
    for that; de-trending the (short) fit window is, and it does not distort the
    transient's spectrum.

    Returns (zeta, f0, f_damped, n_cycles_fitted).
    """
    from scipy.optimize import curve_fit

    x = np.asarray(x, float)
    x = x - x.mean()
    sos = signal.butter(4, [f_lo / (fs / 2), f_hi / (fs / 2)], btype="band", output="sos")
    y = signal.sosfiltfilt(sos, x)

    env = np.abs(signal.hilbert(y))
    i0 = int(np.argmax(env))
    # window follows the burst: run until the envelope reaches 3x the tail noise,
    # clamped to [0.6 s, win_s] so a short ring still gets enough samples to fit.
    noise = np.median(env[-max(int(2.0 * fs), 10):])
    below = np.where(env[i0:] < 3.0 * noise)[0]
    n = below[0] if len(below) else len(env) - i0
    n = int(np.clip(n, 0.6 * fs, win_s * fs))
    i1 = min(len(y), i0 + n)
    seg = y[i0:i1]
    if len(seg) < 8:
        raise ValueError("burst too short to fit — tap nearer the start of the capture")
    t = np.arange(len(seg)) / fs

    # initial guesses: w_d from the burst's spectral peak, alpha from the envelope
    fr = np.fft.rfftfreq(len(seg), 1 / fs)
    mag = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    band = (fr >= f_lo) & (fr <= f_hi)
    fd0 = fr[band][int(np.argmax(mag[band]))]
    e = env[i0:i1]
    n_e = max(4, int(0.5 * fs))
    alpha0 = max(1e-3, -np.polyfit(t[:n_e], np.log(np.maximum(e[:n_e], 1e-18)), 1)[0])

    def model(tt, A, alpha, wd, phi):
        return A * np.exp(-alpha * tt) * np.cos(wd * tt + phi)

    p0 = [seg[0] if abs(seg[0]) > 0 else np.max(np.abs(seg)), alpha0, 2 * np.pi * fd0, 0.0]
    # The lower frequency bound IS a ceiling on zeta, and it is worth writing it that
    # way rather than as a bare 0.6. A damped oscillator rings at
    # w_d = w_0 * sqrt(1 - zeta^2), so bounding f_d below at 0.6 * f_expect admits
    # nothing above zeta = sqrt(1 - 0.6^2) = 0.8 -- above that the fit pins on the bound
    # and raises, no matter how clean the data is. That was found by sweeping synthetic
    # ring-downs (2026-09-02): zeta 0.85 failed 11 or 12 times out of 12 at EVERY signal
    # level, including SNR 200, because more signal cannot rescue an excluded answer.
    #
    # It matters because zeta is the unknown we are building the injector to measure.
    # The 0.6 in station/SS.OAKM1.xml is a vendor guess; if the element is really 0.85,
    # the default bound would simply refuse to say so.
    #
    # The bound exists for a reason on TAPS -- a hard tap rings the case, not the
    # element, and the bound catches that. An injector drives the coil electrically and
    # excites no case mode, so that path can afford a wider window. Hence a parameter,
    # with the tap-safe value as the default.
    w_lo = 2 * np.pi * f_expect * math.sqrt(max(1e-6, 1.0 - min(z_max, 0.999) ** 2))
    w_hi = 2 * np.pi * 1.5 * f_expect
    p0[2] = min(max(p0[2], w_lo * 1.01), w_hi * 0.99)
    popt, _ = curve_fit(model, t, seg, p0=p0, maxfev=20000,
                        bounds=([-np.inf, 0.0, w_lo, -2 * np.pi],
                                [np.inf, 200.0, w_hi, 2 * np.pi]))
    _, alpha, w_d, _ = popt
    if not (w_lo * 1.02 < w_d < w_hi * 0.98):
        raise ValueError(f"fit pinned at the frequency bound ({w_d/2/np.pi:.2f} Hz; "
                         f"z_max={z_max} allows {w_lo/2/np.pi:.2f}-{w_hi/2/np.pi:.2f} Hz) — "
                         "the tap excited a case mode, not the element. Tap gentler.")
    w_0 = np.hypot(alpha, w_d)
    zeta = alpha / w_0
    return zeta, w_0 / (2 * np.pi), w_d / (2 * np.pi), len(seg) / fs * (w_d / (2 * np.pi))


def solve_shunt(z0, z1, r1, r0=R_BIAS, rc=RC_COIL, targets=(0.5, 0.6, 0.7, 0.8)):
    """Two-point solve. z0 at load r0 (no shunt), z1 with trial shunt r1 fitted."""
    g0, g1 = 1.0 / (rc + r0), 1.0 / (rc + r1)
    if z1 <= z0:
        raise ValueError("the trial shunt did not increase damping — check the wiring")
    k = (z1 - z0) / (g1 - g0)
    z_mech = z0 - k * g0
    out = []
    for zt in targets:
        denom = (zt - z_mech) / k
        rs = (1.0 / denom - rc) if denom > 0 else float("inf")
        sens = rs / (rc + rs) if np.isfinite(rs) and rs > 0 else float("nan")
        out.append((zt, rs, sens))
    return k, z_mech, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="fit zeta from a capture containing a tap")
    m.add_argument("npz", nargs="?", help="capture_raw.py .npz (keys: counts, fs)")
    # An injector fires while the station is recording normally, so the transient is
    # already in the day-file -- no separate capture, and nothing has to be touched
    # (which is what otherwise costs ~35 min of settling before the rig is quiet again).
    m.add_argument("--at", nargs="+", metavar="UTC",
                   help="read release instants straight out of the archive instead")
    m.add_argument("--archive", default="analysis/data",
                   help="directory of day-files for --at")
    m.add_argument("--skip-s", type=float, default=0.06,
                   help="skip after the release: opening the injector drops its IR "
                        "offset instantly and the anti-alias filter smears that step")
    m.add_argument("--win-s", type=float, default=1.5, help="fit window after --skip-s")
    m.add_argument("--gain", type=int, default=64)
    m.add_argument("--band", type=float, nargs=2, default=(0.05, 45.0),
                   help="fit band. Wide on purpose -- see the ACCURACY note")

    s = sub.add_parser("solve", help="size the shunt from two zeta measurements")
    s.add_argument("--z0", type=float, required=True, help="zeta with NO shunt")
    s.add_argument("--z1", type=float, required=True, help="zeta with the trial shunt")
    s.add_argument("--r1", type=float, required=True, help="trial shunt, ohms")
    s.add_argument("--rc", type=float, default=RC_COIL)

    a = ap.parse_args(argv)

    if a.cmd == "measure":
        if a.at:
            import glob as _glob
            from obspy import UTCDateTime as _UTC, read as _read
            zs = []
            for iso in a.at:
                t = _UTC(iso)
                hits = _glob.glob(f"{a.archive}/*.D.{t.year}.{t.julday:03d}.mseed")
                if not hits:
                    print(f"  {iso}: no day-file"); continue
                st = _read(hits[0], starttime=t - 0.5, endtime=t + a.skip_s + a.win_s + 1)
                st.merge(method=1, fill_value="interpolate")
                tr = st[0]; fs = float(tr.stats.sampling_rate)
                i0 = int((t - tr.stats.starttime + a.skip_s) * fs)
                seg = np.asarray(tr.data[i0:i0 + int(a.win_s * fs)], float)
                if len(seg) < 20:
                    print(f"  {iso}: window too short"); continue
                z, f0, fd, _ = zeta_from_ringdown(seg, fs, *a.band)
                print(f"  {iso}  zeta {z:.3f}  f0 {f0:.2f} Hz  fd {fd:.2f} Hz")
                zs.append((z, f0))
            if len(zs) < 3:
                raise SystemExit("fewer than 3 usable releases")
            arr = np.array(zs)
            print(f"\n{len(arr)} releases:  zeta median {np.median(arr[:,0]):.3f} "
                  f"(MAD {np.median(np.abs(arr[:,0]-np.median(arr[:,0]))):.3f})   "
                  f"f0 median {np.median(arr[:,1]):.2f} Hz")
            print("  NB the estimator is biased above zeta ~0.6 and the two\n"
                  "     characterisations disagree in SIGN -- see the docstring.")
            print("  Feed f0/zeta into analysis/make_stationxml.py (F0, ZETA).")
            return
        if not a.npz:
            raise SystemExit("give an .npz or --at UTC ...")
        d = np.load(a.npz)
        fs = float(d["fs"])
        counts = d["counts"].astype(float)
        v = (counts - counts.mean()) * (2 * 2.5 / a.gain / 2 ** 23)
        FS = 2 ** 23 - 1

        # Find EVERY tap and fit each. One tap is not a measurement -- the spread
        # across taps is what tells you whether the number means anything.
        sos = signal.butter(4, [0.2 / (fs / 2), 20 / (fs / 2)], btype="band", output="sos")
        env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, v)))
        noise = np.median(env[-int(2 * fs):])
        pk, _ = signal.find_peaks(env, height=20 * noise, distance=int(3 * fs))
        print(f"fs {fs:.2f} sps | {len(pk)} taps | tail noise {noise * 1e6:.1f} uV\n")
        print(f"{'tap':>4} {'t(s)':>7} {'peak(uV)':>10} {'zeta':>7} {'f0(Hz)':>8}  note")
        good = []
        for i, p in enumerate(pk):
            lo, hi = max(0, p - int(fs)), min(len(v), p + int(11 * fs))
            clipped = bool((np.abs(counts[lo:hi]) > 0.99 * FS).any())
            try:
                z, f0, fd, _ = zeta_from_ringdown(v[lo:hi], fs, *a.band)
                note = "CLIPPED, ignored" if clipped else ""
                if not clipped:
                    good.append(z)
                print(f"{i+1:>4} {p/fs:>7.1f} {env[p]*1e6:>10.0f} {z:>7.3f} {f0:>8.2f}  {note}")
            except ValueError as e:
                print(f"{i+1:>4} {p/fs:>7.1f} {env[p]*1e6:>10.0f} {'--':>7} {'--':>8}  {e}")
        if not good:
            print("\nNo usable taps. Tap GENTLY -- aim for a few mV, not tens of mV; a "
                  "hard strike rings the case instead of the element.")
            return 1
        zeta, spread = float(np.median(good)), float(max(good) - min(good))
        print(f"\n{len(good)} usable taps | ZETA = {zeta:.3f} | spread {spread:.3f}")
        if len(good) < 3:
            # A spread of 0.000 across one tap is not agreement, it is a sample size
            # of one. Do not let it read as a result.
            print(f"  ⚠ only {len(good)} usable tap(s) — not a measurement. Need at "
                  "least 3 that agree before this number means anything.")
            return 1
        if spread > 0.08:
            print("  ⚠ spread is too wide to act on — the taps are not measuring the same "
                  "thing. Tap gentler and more consistently, then re-run.")
            return 1
        if zeta > 0.6:
            print("  -> already well damped. Leave the socket empty; a shunt would cost "
                  "sensitivity for nothing.")
        elif zeta > 0.4:
            print("  -> moderately damped. Optional; decide from whether real events show "
                  "4.5 Hz ringing in their coda.")
        else:
            print("  -> lightly damped. Fit a trial shunt and use `solve`.")
        return 0

    k, z_mech, rows = solve_shunt(a.z0, a.z1, a.r1, rc=a.rc)
    print(f"k = {k:.1f} ohm  (G^2 / 2*M*w0, folded)   mechanical zeta = {z_mech:.3f}")
    print(f"{'target zeta':>12} {'shunt':>12} {'sensitivity kept':>18}")
    for zt, rs, sens in rows:
        if not np.isfinite(rs) or rs <= 0:
            print(f"{zt:>12.2f} {'unreachable':>12} {'-':>18}")
        else:
            print(f"{zt:>12.2f} {rs:>11.0f}R {sens * 100:>17.1f}%")
    print("\nSensitivity kept = Rs/(Rc+Rs): what the ADC still sees of the open-circuit\n"
          "voltage. This station is sensitivity-first and already reads ~7.5x low, so\n"
          "deliberate under-damping is a legitimate choice — pick with both columns in view.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
