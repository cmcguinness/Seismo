#!/usr/bin/env python3
"""Spike-polarity asymmetry check.

Ground motion is symmetric; a rectifying nonlinearity in the signal path is not.
Counts excursions beyond N sigma, positive vs negative, in the raw counts and in
a few bands, over a chosen window of a miniSEED day-file.

Usage: asymmetry.py FILE [--start HH:MM] [--end HH:MM] [--hp 1.0]
"""
import argparse
import sys

import numpy as np
from obspy import UTCDateTime, read


def counts(x, sigmas=(3, 4, 5, 6, 8)):
    x = x - np.median(x)
    # robust sigma (MAD) so a handful of huge spikes don't inflate the threshold
    s = 1.4826 * np.median(np.abs(x))
    rows = []
    for n in sigmas:
        pos = int(np.sum(x > n * s))
        neg = int(np.sum(x < -n * s))
        ratio = pos / neg if neg else float("inf") if pos else 1.0
        rows.append((n, pos, neg, ratio))
    return s, rows


def report(label, x, fs):
    s, rows = counts(x)
    print(f"\n--- {label}   (n={len(x)}, {len(x)/fs/60:.1f} min, MAD-sigma={s:.4g})")
    print(f"  skew={float(np.mean(((x-np.mean(x))/np.std(x))**3)):+.3f}   "
          f"max={np.max(x):+.4g}  min={np.min(x):+.4g}  "
          f"|max|/|min|={abs(np.max(x))/abs(np.min(x)):.2f}")
    print("   sigma      +count    -count    ratio")
    for n, pos, neg, ratio in rows:
        print(f"   {n:>2}       {pos:>8}  {neg:>8}    {ratio:>6.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--start", help="UTC ISO or HH:MM (same day as file)")
    ap.add_argument("--end")
    ap.add_argument("--hp", type=float, default=1.0)
    args = ap.parse_args()

    st = read(args.file)
    st.merge(method=1, fill_value="interpolate")
    tr = st[0]
    day = tr.stats.starttime

    def parse(t):
        if t is None:
            return None
        if ":" in t and "T" not in t and len(t) <= 5:
            h, m = t.split(":")
            return UTCDateTime(day.year, day.month, day.day, int(h), int(m))
        return UTCDateTime(t)

    t0, t1 = parse(args.start), parse(args.end)
    if t0 or t1:
        tr = tr.slice(starttime=t0, endtime=t1)
    if tr.stats.npts == 0:
        sys.exit("empty window")

    fs = tr.stats.sampling_rate
    print(f"{tr.id}  {tr.stats.starttime} → {tr.stats.endtime}  fs={fs}")

    uv = 2.5 / 64 / (2**23) * 1e6  # v_ref 2.5, gain 64, 24-bit -> microvolts/count

    raw = tr.data.astype(np.float64) * uv
    report("RAW (DC included, uV)", raw, fs)

    for lo, hi in [(args.hp, None), (1.0, 15.0), (3.0, 15.0), (15.0, 45.0)]:
        w = tr.copy()
        w.detrend("demean")
        if hi:
            w.filter("bandpass", freqmin=lo, freqmax=hi, corners=4, zerophase=True)
            lbl = f"{lo}-{hi} Hz (uV)"
        else:
            w.filter("highpass", freq=lo, corners=4, zerophase=True)
            lbl = f"HP {lo} Hz (uV)"
        report(lbl, w.data.astype(np.float64) * uv, fs)


if __name__ == "__main__":
    main()
