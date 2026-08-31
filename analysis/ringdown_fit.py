#!/usr/bin/env python3
"""ringdown_fit.py — measure the geophone's f0 and zeta from a coil-release transient.

THE METHOD. A moving-coil geophone is its own actuator: by reciprocity the force constant
in N/A equals the voltage sensitivity in V/(m/s). Push a small DC current through the coil
and the mass sits at a new equilibrium; open the circuit and it returns freely while the
same coil reports its velocity. No ground motion is involved, so this measures the
INSTRUMENT and nothing else -- which is exactly what response_fit.py could not do from
spectral ratios, where 1.64 km of site response swamped the corner.

    battery 3 V -> 300 kohm -> switch -> across the coil, in parallel with the ADC
    close, wait ~2 s, OPEN (the open edge is the measurement; closing bounces)

10 uA gives 33 um of deflection and ~27 mV peak EMF: 27,000x the noise floor and
comfortably inside the ADS1256's +-78 mV. Do NOT wind the current up -- at ~1 mA the mass
travels past its stops. Leave the element connected and on the slab so the damping is the
one it actually operates with.

WHY NOT LOG DECREMENT. The usual textbook route -- ratio successive peaks -- needs several
cycles. If zeta is near the vendor's 0.6 the amplitude falls x0.009 per cycle: one
overshoot and it is gone. (That is almost certainly why scanning 61 archive impulses for
ring-downs yielded 4 fits -- there was nothing to find.) So fit the whole second-order
response instead, which works at any damping:

    v(t) = A . exp(-zeta.w0.t) . sin(w_d.t + phi),   w_d = w0.sqrt(1 - zeta^2)

The first few samples are skipped: opening the switch removes a 3.75 mV IR drop
instantly, and the anti-alias filter smears that step over several samples.

    python analysis/ringdown_fit.py 2026-09-01T02:15:03 2026-09-01T02:15:13 ...
    python analysis/ringdown_fit.py --list times.txt
"""
import argparse
import glob
import sys

import numpy as np
from obspy import UTCDateTime, read
from scipy.optimize import least_squares

UV_PER_COUNT = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
SKIP_S = 0.06        # skip the electrical step + filter smear
FIT_S = 0.60         # ~2 damped periods at 4.5 Hz; beyond this it is noise


def dayfile(t):
    g = glob.glob(f"analysis/data/*.D.{t.year}.{t.julday:03d}.mseed")
    return g[0] if g else None


def fit_one(y, fs):
    """Fit A.exp(-zeta.w0.t).sin(w_d.t + phi) + c. Returns (f0, zeta, amp, rms)."""
    t = np.arange(len(y)) / fs
    y = y - np.median(y[-max(5, len(y) // 5):])

    def model(p):
        A, f0, zeta, phi, c = p
        w0 = 2 * np.pi * f0
        wd = w0 * np.sqrt(max(1e-9, 1 - zeta ** 2))
        return A * np.exp(-zeta * w0 * t) * np.sin(wd * t + phi) + c

    best = None
    for f0g in (3.5, 4.5, 5.5):
        for zg in (0.25, 0.5, 0.75):
            try:
                s = least_squares(lambda p: model(p) - y,
                                  [np.max(np.abs(y)) or 1.0, f0g, zg, 0.0, 0.0],
                                  bounds=([-np.inf, 1.5, 0.02, -np.pi, -np.inf],
                                          [np.inf, 12.0, 0.99, np.pi, np.inf]))
            except Exception:
                continue
            r = float(np.sqrt(np.mean(s.fun ** 2)))
            if best is None or r < best[0]:
                best = (r, s.x)
    if best is None:
        return None
    r, (A, f0, zeta, phi, c) = best
    return f0, zeta, abs(A), r / (np.max(np.abs(y)) or 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("times", nargs="*", help="UTC instants of the switch OPEN")
    ap.add_argument("--list", help="file with one UTC instant per line")
    ap.add_argument("--max-resid", type=float, default=0.25,
                    help="reject fits worse than this fraction of peak amplitude")
    a = ap.parse_args()
    times = list(a.times)
    if a.list:
        times += [l.strip() for l in open(a.list) if l.strip() and not l.startswith("#")]
    if not times:
        sys.exit("give at least one release time (UTC), or --list")

    res = []
    for iso in times:
        t = UTCDateTime(iso)
        p = dayfile(t)
        if not p:
            print(f"  {iso}: no day-file"); continue
        try:
            st = read(p, starttime=t - 0.5, endtime=t + FIT_S + 1.0)
            st.merge(method=1, fill_value="interpolate")
            tr = st[0]
        except Exception as exc:
            print(f"  {iso}: read failed ({exc})"); continue
        fs = float(tr.stats.sampling_rate)
        x = np.asarray(tr.data, float) * UV_PER_COUNT
        i0 = int((t - tr.stats.starttime + SKIP_S) * fs)
        seg = x[i0:i0 + int(FIT_S * fs)]
        if len(seg) < 20:
            print(f"  {iso}: window too short"); continue
        out = fit_one(seg, fs)
        if out is None:
            print(f"  {iso}: fit failed"); continue
        f0, zeta, amp, rr = out
        ok = rr <= a.max_resid
        print(f"  {iso}  f0 {f0:5.2f} Hz  zeta {zeta:5.3f}  peak {amp:8.1f} uV  "
              f"resid {rr:5.3f}{'' if ok else '   REJECTED'}")
        if ok:
            res.append((f0, zeta))

    if len(res) < 3:
        sys.exit("\nfewer than 3 good fits -- check the release times and the current")
    r = np.array(res)
    print(f"\n{len(r)} accepted releases")
    print(f"  f0    median {np.median(r[:,0]):5.2f} Hz   spread (MAD) "
          f"{np.median(np.abs(r[:,0]-np.median(r[:,0]))):.3f}")
    print(f"  zeta  median {np.median(r[:,1]):5.3f}      spread (MAD) "
          f"{np.median(np.abs(r[:,1]-np.median(r[:,1]))):.3f}")
    z = float(np.median(r[:, 1]))
    print(f"\n  shunt-damping.md: zeta {z:.2f} -> "
          + ("leave the socket empty, already well damped" if z > 0.6 else
             "optional, decide from whether real events ring at 4.5 Hz" if z > 0.4 else
             "UNDER-damped -- a shunt would flatten the response"))
    print(f"  put these into analysis/make_stationxml.py (F0, ZETA) and regenerate.")


if __name__ == "__main__":
    main()
