#!/usr/bin/env python3
"""source_signature.py — fingerprint a noise source in a labelled window.

Given a time window (or a label from annotations.csv), report the two things that
actually separate the sources this station sees:

  1. WHERE THE ENERGY IS. Band RMS in 1-5 / 5-15 / 15-45 Hz against a quiet
     reference window either side. An earthquake loads the low bands; anything
     mechanical within a few metres loads 15-45 Hz and leaves the quake band flat
     (>15 Hz does not survive propagation, so its presence means "very close").
  2. WHETHER THERE IS A LINE. Rotating machinery puts a narrow peak at its shaft
     rate; impacts and vehicles are broadband. The line frequency is an identity —
     the washing machine's 19.9 Hz is 1195 RPM and nothing else in the house does
     that.

Usage:
  source_signature.py FILE --start 20:42:51 --end 20:50:46
  source_signature.py FILE --label "washing machine spin"     # every logged window
"""
import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
BANDS = [(1, 5), (5, 15), (15, 45)]
UV_PER_COUNT = 2.5 / 64 / (2 ** 23) * 1e6      # v_ref 2.5, gain 64, 24-bit


def _band_rms(tr, lo, hi):
    w = tr.copy()
    w.detrend("demean")
    w.filter("bandpass", freqmin=lo, freqmax=min(hi, w.stats.sampling_rate / 2 * 0.99),
             corners=4, zerophase=True)
    x = w.data.astype(float) * UV_PER_COUNT
    return float(np.sqrt(np.mean(x * x))) if x.size else float("nan")


def _line(tr, fmin=2.0):
    """Strongest narrow spectral peak above fmin: (freq, ASD, x-over-continuum).

    Continuum is the median ASD in +/-2 Hz shoulders around the peak, so a genuine
    line scores high and a broadband hump scores ~1.
    """
    from scipy.signal import welch
    x = tr.data.astype(float) * UV_PER_COUNT
    x = x - x.mean()
    fs = float(tr.stats.sampling_rate)
    nper = min(len(x), 2048)
    if nper < 256:
        return None
    f, p = welch(x, fs=fs, nperseg=nper)
    a = np.sqrt(p)
    ok = (f > fmin) & (f < fs / 2 * 0.96)
    if not ok.any():
        return None
    k = np.argmax(a[ok])
    fpk, apk = f[ok][k], a[ok][k]
    sh = ((f > fpk - 3) & (f < fpk - 1)) | ((f > fpk + 1) & (f < fpk + 3))
    cont = float(np.median(a[sh])) if sh.any() else float("nan")
    return fpk, float(apk), (apk / cont if cont else float("nan"))


def _amp_at(tr, freq, half_bw=0.5):
    """Peak ASD within +/-half_bw of `freq` -- for asking whether a line the event
    shows is also present, at what strength, in the quiet reference."""
    from scipy.signal import welch
    x = tr.data.astype(float) * UV_PER_COUNT
    x = x - x.mean()
    nper = min(len(x), 2048)
    if nper < 256:
        return float("nan")
    f, p = welch(x, fs=float(tr.stats.sampling_rate), nperseg=nper)
    m = (f > freq - half_bw) & (f < freq + half_bw)
    return float(np.sqrt(p[m]).max()) if m.any() else float("nan")


def report(tr_full, t0, t1, label=""):
    import obspy

    ev = tr_full.slice(t0, t1)
    if ev.stats.npts < 256:
        print(f"  {label or t0}: no data in window")
        return
    pad = max(30.0, (t1 - t0) * 0.5)
    ref = tr_full.slice(t0 - pad - 10, t0 - 10)       # quiet reference just before
    if ref.stats.npts < 256:
        ref = tr_full.slice(t1 + 10, t1 + 10 + pad)

    print(f"\n{label or ''}  {t0} -> {t1}   ({t1 - t0:.0f} s)")
    print("   band        event      quiet     ratio")
    for lo, hi in BANDS:
        e, q = _band_rms(ev, lo, hi), _band_rms(ref, lo, hi)
        print(f"   {lo:>2}-{hi:<3} Hz  {e:8.2f}  {q:9.2f}  {e / q if q else float('nan'):8.2f}")
    ln = _line(ev)
    if ln:
        f, a, x = ln
        # A high continuum ratio alone is NOT enough: this station carries standing
        # lines (a persistent ~41 Hz, and a weak one near 20 Hz) that score x10 in
        # DEAD QUIET. Only a line whose AMPLITUDE grows against the reference window
        # belongs to the source. Calling 41 Hz a washing-machine harmonic on the
        # continuum ratio alone was exactly the error this check exists to stop.
        aq = _amp_at(ref, f)
        grow = a / aq if aq else float("nan")
        if x >= 5 and grow >= 3:
            verdict = f"LINE from this source — {f * 60:.0f} RPM if a shaft rate"
        elif x >= 5:
            verdict = "standing line, NOT this source (amplitude unchanged)"
        else:
            verdict = "no line — broadband (impact / vehicle / quake)"
        print(f"   peak {f:6.2f} Hz  {a:5.2f} uV/rtHz (quiet {aq:5.2f}, x{grow:.1f})"
              f"  x{x:.1f} over continuum")
        print(f"   [{verdict}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="miniSEED day-file")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--label", help="fingerprint every annotations.csv row with this label")
    ap.add_argument("--annotations", default=str(_SCRIPT_DIR / "annotations.csv"))
    args = ap.parse_args()

    import obspy

    st = obspy.read(args.file)
    st.merge(method=1, fill_value="interpolate")
    tr = st[0]
    day = tr.stats.starttime

    def parse(s):
        if ":" in s and "T" not in s:
            h, m, *rest = s.split(":")
            return obspy.UTCDateTime(day.year, day.month, day.day,
                                     int(h), int(m), int(rest[0]) if rest else 0)
        return obspy.UTCDateTime(s)

    if args.label:
        if not os.path.exists(args.annotations):
            sys.exit(f"no annotations at {args.annotations}")
        with open(args.annotations) as f:
            rows = [r for r in csv.DictReader(f)
                    if r["label"].strip().lower() == args.label.strip().lower()]
        if not rows:
            sys.exit(f"no rows labelled {args.label!r}")
        for r in rows:
            report(tr, obspy.UTCDateTime(r["t_start_utc"]),
                   obspy.UTCDateTime(r["t_end_utc"]), r["label"])
    elif args.start and args.end:
        report(tr, parse(args.start), parse(args.end))
    else:
        sys.exit("give --start/--end or --label")


if __name__ == "__main__":
    main()
