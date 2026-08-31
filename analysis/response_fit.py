#!/usr/bin/env python3
"""response_fit.py — fit the geophone's poles-and-zeros from data, against NP.1835.

WHY. refstation.py compares OAKM1 with the reference in 5-15 Hz, deliberately ABOVE the
4.5 Hz corner "where its 28.8 V/(m/s) is flat and no response model is needed on our
side". That is the right call for a scalar, and it is exactly why the result can only
ever BE a scalar: it never looks at the corner. A real StationXML response needs the
corner -- the natural frequency f0 and the damping zeta -- and those live below 5 Hz.

METHOD. For each anchor event, take the shaking window at both stations, remove the
reference response to VELOCITY, and form the ratio of amplitude spectra

    |H(f)|  =  A_OAKM1(f) [counts]  /  A_ref(f) [m/s]

which is this station's whole chain in counts/(m/s). Fit the standard moving-coil model

    |H(f)| = S . (f/f0)^2 / sqrt( (1-(f/f0)^2)^2 + (2.zeta.f/f0)^2 )

for S, f0, zeta. Two zeros at the origin and a conjugate pole pair is the entire sensor
response; there is no analog gain or filtering on this board (the PGA and buffer are
inside the ADS1256), so S absorbs the digitiser and the geophone sensitivity together.

WHAT THIS CANNOT DO. The stations are 1.64 km apart, so the ratio carries SITE response
as well as instrument response, and refstation.py already warns that local conditions
differ by ~2x at 5-15 Hz. Site response varies smoothly with frequency while a corner is
a sharp second-order feature, so the SHAPE near f0 should survive; the absolute S is the
part to distrust. And the reference is a strong-motion accelerometer with a noise floor
-- it is deaf exactly where the geophone is comfortable -- so only the loudest anchors
have usable reference signal below 5 Hz. Both effects push the same way: trust f0 and
zeta more than S, and treat this as a cross-check on a bench ring-down, not a
replacement for one.

RESULT, 2026-08-30 — THIS DOES NOT WORK, AND HERE IS THE EVIDENCE. Fitted over four
anchors it returns f0 3.65 Hz, zeta 0.523, sensitivity 7.19 V/(m/s) — but the residual is
0.298 in log amplitude, i.e. **2x scatter**, exactly the site-response difference
refstation.py warns about. Two checks show the numbers are not constraints:

  * Forcing f0 and refitting barely moves the residual between 2.5 and 4.5 Hz
    (0.3189 / 0.2983 / 0.3241). The data excludes a corner above ~5 Hz and says nothing
    more. 4.5 Hz nameplate fits essentially as well as the 3.65 the optimiser picked.
  * Per anchor: zeta spans 0.39-0.70 — the whole width of the shunt-damping decision —
    and sensitivity spans 4.4x (Geysers 9.63 / 9.64 / 6.35, San Leandro 2.21). The three
    Geysers events share a path and agree; San Leandro is a different path and does not.
    The scatter is geological, so more events on the SAME two paths will not average it
    down.

So f0 and zeta need the bench ring-down (coil reciprocity: drive DC through the coil,
open the circuit, fit the free oscillation). Keep this script: it is the cross-check for
that measurement, and it is worth re-running when anchors from more independent azimuths
exist. It does corroborate one thing — the Geysers-path sensitivity of ~9.6 V/(m/s) sits
on refstation.py's measured 9.0, so the scalar calibration is sound and it is only the
frequency SHAPE that is out of reach here.

    python analysis/response_fit.py
"""
import glob
import warnings

warnings.filterwarnings("ignore")

import numpy as np
from obspy import UTCDateTime, read
from obspy.clients.fdsn import Client
from scipy.optimize import least_squares

UV_PER_COUNT = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
REF = ("NP", "1835", "HNZ")
FIT_BAND = (1.5, 20.0)          # spans the 4.5 Hz corner; below 1.5 the reference is noise
NOMINAL_SENS = 28.8

ANCHORS = [
    ("M2.8 Geysers",     "2026-08-11T21:35:14"),
    ("M3.2 Geysers",     "2026-08-12T10:28:21"),
    ("M4.1 San Leandro", "2026-08-13T15:30:04"),
    ("M2.4 Geysers",     "2026-08-25T00:22:31"),
]


def dayfile(t):
    g = glob.glob(f"analysis/data/*.D.{t.year}.{t.julday:03d}.mseed")
    return g[0] if g else None


def spectrum(x, fs, nperseg=512):
    """Median amplitude spectrum over half-overlapping windows -- median, not mean, so
    one loud sub-window cannot carry the estimate (the lesson from mean-Welch)."""
    step = nperseg // 2
    segs = [x[i:i + nperseg] for i in range(0, max(1, len(x) - nperseg + 1), step)]
    segs = [s for s in segs if len(s) == nperseg]
    if not segs:
        return None, None
    w = np.hanning(nperseg)
    A = np.array([np.abs(np.fft.rfft(s * w)) for s in segs])
    f = np.fft.rfftfreq(nperseg, 1 / fs)
    return f, np.median(A, axis=0)


def geophone(f, S, f0, zeta):
    r = f / f0
    return S * r ** 2 / np.sqrt((1 - r ** 2) ** 2 + (2 * zeta * r) ** 2)


def main():
    c = Client("NCEDC", timeout=60)
    fs_all, ratios, used = None, [], []
    for label, iso in ANCHORS:
        o = UTCDateTime(iso)
        p = dayfile(o)
        if not p:
            print(f"  {label}: no local day-file, skipped")
            continue
        a, b = o + 2, o + 32                       # the shaking window
        try:
            ref = c.get_waveforms(REF[0], REF[1], "*", REF[2], a - 60, b + 60,
                                  attach_response=True)
            ref.merge(method=1, fill_value="interpolate")
            ref.remove_response(output="VEL", pre_filt=(0.3, 0.6, 40, 45), water_level=60)
            r = ref.slice(a, b)[0]
            mine = read(p, starttime=a - 5, endtime=b + 5)
            mine.merge(method=1, fill_value="interpolate")
            m = mine.slice(a, b)[0]
        except Exception as exc:
            print(f"  {label}: fetch/read failed ({exc})")
            continue
        fs = float(m.stats.sampling_rate)
        if abs(float(r.stats.sampling_rate) - fs) > 1e-6:
            r = r.copy().resample(fs)
        r.detrend("demean"); m.detrend("demean")
        n = min(len(r.data), len(m.data))
        fr, Ar = spectrum(np.asarray(r.data[:n], float), fs)
        fm, Am = spectrum(np.asarray(m.data[:n], float), fs)
        if fr is None or fm is None:
            continue
        sel = (fr >= FIT_BAND[0]) & (fr <= FIT_BAND[1]) & (Ar > 0)
        ratios.append((fr[sel], Am[sel] / Ar[sel]))
        used.append(label)
        fs_all = fs
        print(f"  {label}: {sel.sum()} usable bins, ref RMS {r.data.std()*1e6:.2f} um/s")

    if len(ratios) < 2:
        raise SystemExit("\nnot enough anchors with usable reference signal")

    f = ratios[0][0]
    H = np.median(np.array([np.interp(f, fq, hq) for fq, hq in ratios]), axis=0)

    def resid(p):
        S, f0, zeta = p
        return np.log(geophone(f, S, f0, zeta)) - np.log(H)

    S0 = np.median(H[(f > 10) & (f < 18)]) or 1.0
    sol = least_squares(resid, [S0, 4.5, 0.5], bounds=([S0*1e-3, 2.0, 0.05],
                                                      [S0*1e3, 9.0, 1.2]))
    S, f0, zeta = sol.x
    counts_per_volt = 1e6 / UV_PER_COUNT
    sens = S / counts_per_volt                       # V/(m/s)

    print(f"\nfitted over {len(used)} anchors ({', '.join(used)}), {FIT_BAND[0]}-{FIT_BAND[1]} Hz\n")
    print(f"  f0    {f0:6.2f} Hz        (nameplate 4.5)")
    print(f"  zeta  {zeta:6.3f}           ({'UNDER-damped' if zeta < 0.4 else 'moderately damped' if zeta < 0.6 else 'well damped'})")
    print(f"  S     {S:.4g} counts/(m/s)  ->  sensitivity {sens:.2f} V/(m/s)")
    print(f"        vs nameplate {NOMINAL_SENS} V/(m/s)  =  {NOMINAL_SENS/sens:.2f}x low"
          f"   (refstation scalar: 3.20x)")
    rms = float(np.sqrt(np.mean(resid(sol.x) ** 2)))
    print(f"  fit residual (log amplitude) RMS {rms:.3f}  = {10**rms:.2f}x scatter")
    print("\n  shape check -- |H| measured vs fitted:")
    for fx in (2, 3, 4.5, 6, 9, 15):
        i = int(np.argmin(np.abs(f - fx)))
        print(f"    {f[i]:5.2f} Hz   measured {H[i]:10.3g}   fitted {geophone(f[i],S,f0,zeta):10.3g}"
              f"   ratio {H[i]/geophone(f[i],S,f0,zeta):5.2f}")


if __name__ == "__main__":
    main()
