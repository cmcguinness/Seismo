#!/usr/bin/env python3
"""traffic_features.py — build a training table from observed car counts.

You collect a label log of discrete intervals with car counts (watching the road
or a video feed); this joins each interval to the seismic archive over exactly
that window and reduces it to features. Output is a CSV of features + count, one
row per interval, ready to train a car-counter.

Labels CSV (header required; column names are matched loosely):
    start_utc, stop_utc, cars
    2026-07-24T14:00:00, 2026-07-24T14:00:30, 3
    2026-07-24T14:00:30, 2026-07-24T14:01:00, 5

Times are parsed by ObsPy (ISO8601 best). If you logged LOCAL time, pass
--offset-hours -7 (PDT) and they'll be converted to UTC. Keep your logging clock
on network time; at 30 s granularity sub-second alignment does not matter.

Features are all HIGH-PASSED (>=1 Hz), so they are immune to the front end's DC
operating point and the 2026-07-24 epoch change — but DO collect a given label
run within one epoch (no hardware changes mid-session), or the transfer function
shifts under you.

  analysis/.venv/bin/python traffic_features.py --labels labels.csv
  analysis/.venv/bin/python traffic_features.py --labels labels.csv --offset-hours -7 --no-pull
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from helicorder import LOCAL_DATA, load_day, pull

GAIN_DEFAULT = 64
UV = lambda gain: 2.5 * 2 / (gain * (2 ** 23 - 1)) * 1e6   # counts -> µV

# Sub-bands to summarise. Traffic energy tends to sit mid/high; the earthquake
# working band is ~1-15 Hz. Reported separately so the training step can see
# which band actually discriminates cars rather than baking in a guess.
BANDS = [("rms_1_5", 1.0, 5.0), ("rms_5_15", 5.0, 15.0), ("rms_15_28", 15.0, 28.0)]
TRAFFIC_BAND = (2.0, 25.0)          # band the bump-counter works in


def _col(header, *names):
    """Find a column index by any of several loose names."""
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    sys.exit(f"labels CSV needs a column named one of {names}; got {header}")


def read_labels(path, offset_hours):
    import obspy
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        si = _col(header, "start_utc", "start", "t0", "begin")
        ei = _col(header, "stop_utc", "end_utc", "stop", "end", "t1", "finish")
        ci = _col(header, "cars", "total", "count", "n", "vehicles")
        for r in reader:
            if not r or not r[si].strip():
                continue                              # blank line
            try:
                t0 = obspy.UTCDateTime(r[si].strip()) - offset_hours * 3600
                t1 = obspy.UTCDateTime(r[ei].strip()) - offset_hours * 3600
                cars = int(float(r[ci].strip()))
            except Exception as e:
                print(f"  skipping unparseable row {r}: {e}")
                continue
            rows.append((t0, t1, cars))
    if not rows:
        sys.exit(f"no usable label rows in {path}")
    return rows


def load_span(t0, t1):
    """Merged stream covering [t0, t1], across day-file boundaries."""
    import obspy
    days = {(t0 + i * 43200).strftime("%Y.%j")
            for i in range(int((t1 - t0) / 43200) + 2)}   # every 12 h in span
    files = []
    for d in days:
        files += sorted(LOCAL_DATA.glob(f"*.D.{d}.mseed"))
    files = sorted(set(files))
    if not files:
        return None
    st = obspy.Stream()
    for fp in files:
        st += load_day(fp)                # normalizes mixed rates, splits on gaps
    return st


def features(st, t0, t1, gain):
    """Reduce the signal in [t0, t1] to a feature dict. None if no data."""
    seg = st.slice(t0, t1).copy()
    seg = seg.select(channel="SHZ") or seg
    if not len(seg):
        return None
    seg.merge(method=1, fill_value=None)
    tr = seg[0]
    fs = tr.stats.sampling_rate
    d = np.ma.filled(tr.data.astype(float), np.nan)
    good = np.isfinite(d)
    if good.sum() < fs * 2:                # need a couple of seconds
        return None
    coverage = good.sum() / max(1, round((t1 - t0) * fs))
    d = np.nan_to_num(d, nan=np.nanmean(d[good]))
    uv = UV(gain)

    def bp(lo, hi):
        t = tr.copy(); t.data = d - d.mean(); t.detrend("linear")
        t.filter("bandpass", freqmin=lo, freqmax=min(hi, fs / 2 - 0.5),
                 corners=4, zerophase=True)
        return t.data * uv

    hp = bp(1.0, fs / 2 - 0.5)                      # broadband, DC-free
    feat = {"rms_uv": float(hp.std()), "peak_uv": float(np.abs(hp).max())}
    for name, lo, hi in BANDS:
        feat[name] = float(bp(lo, hi).std())

    # bump count: envelope of the traffic band, threshold at a robust baseline,
    # count upward crossings with a refractory so one vehicle = one bump.
    tb = np.abs(bp(*TRAFFIC_BAND))
    win = max(1, int(fs * 0.5))
    env = np.convolve(tb, np.ones(win) / win, mode="same")
    med = np.median(env)
    mad = np.median(np.abs(env - med)) or 1e-9
    thr = med + 4.0 * 1.4826 * mad
    above = env > thr
    refr = int(fs * 1.5)                            # >=1.5 s between counted bumps
    bumps, last = 0, -refr
    for i in np.nonzero(above[1:] & ~above[:-1])[0]:
        if i - last >= refr:
            bumps += 1; last = i
    feat["n_bumps"] = bumps
    feat["coverage"] = round(coverage, 3)
    feat["dur_s"] = round(t1 - t0, 1)
    return feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True, help="CSV: start,stop,cars")
    ap.add_argument("--offset-hours", type=float, default=0.0,
                    help="UTC offset of label times (default 0=UTC; -7=PDT)")
    ap.add_argument("--host", default="seismo.local")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--gain", type=int, default=GAIN_DEFAULT)
    ap.add_argument("--out", default=None, help="output CSV (default <labels>.features.csv)")
    args = ap.parse_args()

    if not args.no_pull:
        pull(args.host)

    labels = read_labels(args.labels, args.offset_hours)
    t_lo = min(t0 for t0, _, _ in labels)
    t_hi = max(t1 for _, t1, _ in labels)
    st = load_span(t_lo, t_hi)
    if st is None:
        sys.exit(f"no archive covering {t_lo} .. {t_hi} in {LOCAL_DATA}")

    cols = ["start_utc", "stop_utc", "dur_s", "coverage", "cars",
            "rms_uv", "peak_uv", "rms_1_5", "rms_5_15", "rms_15_28", "n_bumps"]
    out = Path(args.out) if args.out else Path(args.labels).with_suffix(".features.csv")
    n_ok = 0
    print(f"\n  {'start (UTC)':19} {'cars':>4} {'cov':>5} {'rms':>6} {'peak':>7} "
          f"{'1-5':>5} {'5-15':>5} {'15-28':>6} {'bumps':>5}")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for t0, t1, cars in labels:
            feat = features(st, t0, t1, args.gain)
            if feat is None:
                print(f"  {t0.strftime('%Y-%m-%dT%H:%M:%S')} {cars:>4}   -- no archive data --")
                continue
            row = {"start_utc": t0.isoformat(), "stop_utc": t1.isoformat(), "cars": cars, **feat}
            w.writerow({k: row.get(k, "") for k in cols})
            n_ok += 1
            print(f"  {t0.strftime('%Y-%m-%dT%H:%M:%S')} {cars:>4} {feat['coverage']:>5.2f} "
                  f"{feat['rms_uv']:>6.2f} {feat['peak_uv']:>7.1f} {feat['rms_1_5']:>5.2f} "
                  f"{feat['rms_5_15']:>5.2f} {feat['rms_15_28']:>6.2f} {feat['n_bumps']:>5}")
    print(f"\nwrote {n_ok}/{len(labels)} rows -> {out}")
    if n_ok:
        print("features are high-passed (DC/epoch-robust). Collect each run within one epoch.")


if __name__ == "__main__":
    main()
