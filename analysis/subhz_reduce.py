#!/usr/bin/env python3
"""subhz_reduce.py — per-interval SUB-1 Hz band levels straight off the miniSEED.

Runs ON pi5, where the archive lives: 976 MB of day-files is not worth pulling over
the LAN to answer a yes/no question. Emits one small CSV.

Everything already in /data/heli is high-passed at 1 Hz, so none of it can see the
0.02-0.12 Hz undulation or the microseism. This reduction deliberately goes the other
way: decimate 100 -> 5 sps (Nyquist 2.5 Hz, ample for a 0.5 Hz ceiling) and measure
what lives below the drum's corner.

Per 15-min interval:
  dc_counts   raw interval mean, NOT de-meaned -- a direct baseline/tilt proxy, and the
              one number the whole pipeline throws away first
  dc_slope    least-squares counts/hour across the interval (drift rate)
  vlf/lf/ms   band RMS (counts) over 0.005-0.02 / 0.02-0.12 / 0.12-0.5 Hz, by median
              Welch: the MEAN Welch is hijacked by one loud minute (learned the hard way)
Uncalibrated on purpose: a 4.5 Hz geophone rolls off as f^2 below resonance, so these
are instrument counts, fine for correlation and trend, meaningless as ground velocity.

    python subhz_reduce.py <data_dir> <out.csv> [first_jday] [last_jday]
"""
import glob
import os
import sys

import numpy as np
import obspy
from scipy import signal

INTERVAL_S = 900
TARGET_SPS = 5.0
BANDS = {"vlf": (0.005, 0.02), "lf": (0.02, 0.12), "ms": (0.12, 0.5)}


def band_rms(x, fs):
    """{band: RMS counts} by integrating a MEDIAN-averaged Welch PSD."""
    nper = min(len(x), int(fs * 300))            # 300 s segments -> 0.0033 Hz bins
    if nper < int(fs * 60):
        return {k: np.nan for k in BANDS}
    f, pxx = signal.welch(x, fs=fs, nperseg=nper, noverlap=nper // 2,
                          average="median", detrend="linear")
    out = {}
    for name, (lo, hi) in BANDS.items():
        sel = (f >= lo) & (f < hi)
        out[name] = float(np.sqrt(np.trapezoid(pxx[sel], f[sel]))) if sel.sum() > 1 else np.nan
    return out


def main(data_dir, out_path, first_j=None, last_j=None):
    files = sorted(glob.glob(os.path.join(data_dir, "*.mseed")))
    if first_j is not None:
        files = [f for f in files if first_j <= int(f.split(".")[-2]) <= last_j]
    rows = []
    for path in files:
        st = obspy.read(path)
        st.merge(method=1, fill_value="interpolate")   # day-files arrive as ~10 s fragments
        st = st.select(component="Z") or st
        for tr in st:
            if tr.stats.sampling_rate < 50:            # early mixed-rate segments
                continue
            tr.detrend("linear")
            fac = int(round(tr.stats.sampling_rate / TARGET_SPS))
            for f in (5, 2, 2):                        # stepwise; obspy warns on big factors
                while fac % f == 0 and fac > 1:
                    tr.decimate(f, no_filter=False)
                    fac //= f
            fs = float(tr.stats.sampling_rate)
            t_start = tr.stats.starttime.timestamp
            data = tr.data.astype(np.float64)
            t0 = np.ceil(t_start / INTERVAL_S) * INTERVAL_S
            while t0 + INTERVAL_S <= t_start + len(data) / fs:
                i0 = int(round((t0 - t_start) * fs))
                seg = data[i0:i0 + int(INTERVAL_S * fs)]
                if len(seg) > fs * 300:
                    t = np.arange(len(seg)) / fs
                    slope = np.polyfit(t, seg, 1)[0] * 3600.0
                    b = band_rms(seg, fs)
                    rows.append((t0, len(seg), seg.mean(), slope,
                                 b["vlf"], b["lf"], b["ms"]))
                t0 += INTERVAL_S
        print(f"  {os.path.basename(path)}: {len(rows)} intervals so far", flush=True)
    with open(out_path, "w") as fh:
        fh.write("t0,n,dc_counts,dc_slope_per_h,vlf,lf,ms\n")
        for r in rows:
            fh.write("%.0f,%d,%.1f,%.2f,%.4f,%.4f,%.4f\n" % r)
    print(f"wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], int(a[2]) if len(a) > 3 else None, int(a[3]) if len(a) > 3 else None)
