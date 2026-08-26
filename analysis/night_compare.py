#!/usr/bin/env python3
"""night_compare.py — did a station change move the noise floor? Same quiet hours, two nights.

Compares the LOCAL quiet window (00:00-05:00 PDT = 07:00-12:00 UTC) on two day-files:
per-band RMS from a median-Welch PSD, the event-robust 1-15 Hz RMS (median of 10 s
windows, so a single truck cannot hijack it), and the per-bin PSD ratio's largest
persistent excursions -- a new narrow line from a hardware or software change shows up
there before it shows up anywhere else.

Built for the 2026-08-25 C-reader cutover (STATUS.md "quiet-night PSD comparison is
still owed"); reusable for the GPS clock, the Pi 3B+, or any change that could touch the
analog side. Same-hours-on-two-nights is the fair test: the daytime floor swings 4x.

    python analysis/night_compare.py <jday_before> <jday_after> [--start-utc 7 --hours 5]
Day-files come from analysis/data (scp them from the station first).
"""
import argparse
import os
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import obspy
from obspy import UTCDateTime
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6         # counts -> uV at PGA 64
BANDS = [(1, 3), (3, 8), (8, 15), (15, 30), (30, 45)]


def load_window(jday, start_utc, hours, year=2026):
    path = os.path.join(DATA, f"XX.OAKMT.00.SHZ.D.{year}.{jday:03d}.mseed")
    st = obspy.read(path)
    t0 = UTCDateTime(year=year, julday=jday, hour=start_utc)
    st = st.trim(t0, t0 + hours * 3600)
    st.merge(method=1, fill_value="interpolate")
    tr = st[0]
    tr.detrend("linear")
    return tr, t0


def band_table(tr):
    f, p = signal.welch(tr.data * UV, fs=tr.stats.sampling_rate,
                        nperseg=int(30 * tr.stats.sampling_rate), average="median")
    out = {}
    for lo, hi in BANDS:
        sel = (f >= lo) & (f < hi)
        out[(lo, hi)] = float(np.sqrt(np.trapezoid(p[sel], f[sel])))
    return f, p, out


def robust_rms(tr, lo=1.0, hi=15.0, win_s=10.0):
    x = tr.copy().filter("bandpass", freqmin=lo, freqmax=hi, corners=4).data * UV
    w = int(win_s * tr.stats.sampling_rate)
    r = np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, w)])
    return float(np.median(r)), float(np.percentile(r, 10)), float(np.percentile(r, 90))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=int)
    ap.add_argument("after", type=int)
    ap.add_argument("--start-utc", type=int, default=7)
    ap.add_argument("--hours", type=float, default=5.0)
    a = ap.parse_args()

    tb, t0b = load_window(a.before, a.start_utc, a.hours)
    ta, t0a = load_window(a.after, a.start_utc, a.hours)
    print(f"before: jday {a.before}  {t0b} +{a.hours:g} h   ({len(tb.data)/tb.stats.sampling_rate/3600:.2f} h of data)")
    print(f"after:  jday {a.after}  {t0a} +{a.hours:g} h   ({len(ta.data)/ta.stats.sampling_rate/3600:.2f} h of data)")

    fb, pb, bb = band_table(tb)
    fa, pa, ba = band_table(ta)
    print("\nband       before    after   ratio   (uV rms, median-Welch)")
    for k in BANDS:
        print(f"{k[0]:>2}-{k[1]:<2} Hz  {bb[k]:7.3f}  {ba[k]:7.3f}   {ba[k]/bb[k]:5.2f}")

    rb = robust_rms(tb); ra = robust_rms(ta)
    print(f"\n1-15 Hz robust RMS (median of 10 s windows; p10 / p90):")
    print(f"  before {rb[0]:.2f} uV  ({rb[1]:.2f} / {rb[2]:.2f})")
    print(f"  after  {ra[0]:.2f} uV  ({ra[1]:.2f} / {ra[2]:.2f})   ratio {ra[0]/rb[0]:.2f}")

    # narrow-line hunt: PSD ratio after/before, smoothed over 3 bins, above 0.5 Hz
    r = pa / np.interp(fa, fb, pb)
    rs = np.convolve(r, np.ones(3) / 3, "same")
    m = fa > 0.5
    idx = np.argsort(rs[m])[-6:][::-1]
    print("\nlargest after/before PSD ratios (3-bin smoothed, >0.5 Hz):")
    for i in idx:
        print(f"  {fa[m][i]:6.2f} Hz  x{rs[m][i]:.2f}")
    idx = np.argsort(rs[m])[:4]
    print("smallest (lines that went away):")
    for i in idx:
        print(f"  {fa[m][i]:6.2f} Hz  x{rs[m][i]:.2f}")
    print("\nrule of thumb: band ratios within 0.8-1.25 and no smoothed bin above x3 = floor unchanged.")


if __name__ == "__main__":
    main()
