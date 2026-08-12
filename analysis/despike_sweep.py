#!/usr/bin/env python3
"""despike_sweep.py — replay an archived day through Despiker at several thresholds.

The recorder already despiked the archive at jump=200,000 counts, so this can only
find the population BELOW that. That is exactly the point: single-sample garbage
frames at 8k-25k counts sail under the current threshold and speckle the helicorder
(2026-08-12). This answers "where should `jump` be set" with counts, not opinion.

Reimplements station/rdatac.py:Despiker EXACTLY -- the discriminator is ISOLATION,
not magnitude: hold only when the excursion returns to baseline on the very next
sample. A real event stays displaced, so `d_after` also exceeds jump and the sample
is kept. That is what makes lowering the threshold safe, and what this checks.

    PYTHONPATH=. python analysis/despike_sweep.py --day 223
"""
import argparse

import numpy as np
from obspy import UTCDateTime, read

UV_PER_COUNT = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6

# Windows that must survive untouched: confirmed catalog events in this archive.
# A hold inside one of these is a false positive on real ground motion.
EVENTS = [
    ("M2.8 Geysers 45 km", "2026-08-11T21:35:20", "2026-08-11T21:35:45"),
]


def despike(x: np.ndarray, jump: int):
    """Faithful replay of Despiker.push(). Returns (output, held_indices).

    Only indices that could possibly trip the test are visited, but `prev` is
    propagated exactly, so consecutive candidates behave as they would live.
    """
    out = x.copy()
    # A hold needs |judged - prev| > jump. prev == previous OUTPUT, which differs
    # from x[i-1] only right after a hold, so screen on the raw diff first.
    cand = np.flatnonzero(np.abs(np.diff(x)) > jump) + 1
    cand = cand[(cand >= 1) & (cand < len(x) - 1)]
    held = []
    prev_override = {}
    for i in cand:
        prev = prev_override.get(i - 1, out[i - 1])
        if abs(x[i] - prev) > jump and abs(x[i + 1] - prev) < jump:
            out[i] = prev
            prev_override[i] = prev
            held.append(i)
    return out, np.array(held, dtype=int)


def band_rms(x, fs, lo, hi):
    """Median of per-10 s band RMS -- the project's standard metric."""
    from obspy import Trace
    t = Trace(x.astype("float64"))
    t.stats.sampling_rate = fs
    t.detrend("demean")
    t.filter("bandpass", freqmin=lo, freqmax=hi, corners=4, zerophase=True)
    seg = int(10 * fs)
    a = t.data[: len(t.data) // seg * seg].reshape(-1, seg)
    return float(np.median(a.std(axis=1)) * UV_PER_COUNT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="analysis/data/XX.OAKMT.00.SHZ.D.2026.223.mseed")
    ap.add_argument("--thresholds", default="200000,100000,50000,20000,10000,5000,2000")
    args = ap.parse_args()

    st = read(args.file)
    for tr in st:
        tr.stats.sampling_rate = 100.0
    st.merge(method=1, fill_value="interpolate")
    tr = st[0]
    fs, start = 100.0, tr.stats.starttime
    x = tr.data.astype(np.int64)
    hours = len(x) / fs / 3600.0
    print(f"{args.file}")
    print(f"  {len(x):,} samples = {hours:.1f} h, {start} -> {tr.stats.endtime}")
    print(f"  archive was already despiked live at jump=200,000\n")

    base15 = band_rms(x, fs, 1, 15)
    base5 = band_rms(x, fs, 1, 5)
    print(f"{'jump (ct)':>10} {'~uV':>7} {'held':>7} {'/hour':>7} {'% samp':>8}"
          f" {'1-15 Hz':>9} {'1-5 Hz':>8}  event holds")
    print(f"{'-'*10} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*9} {'-'*8}  {'-'*12}")
    print(f"{'(none)':>10} {'':>7} {0:>7} {0:>7.1f} {0:>7.3f}% "
          f"{base15:>9.2f} {base5:>8.2f}  --")

    for j in (int(v) for v in args.thresholds.split(",")):
        out, held = despike(x, j)
        n = len(held)
        r15, r5 = band_rms(out, fs, 1, 15), band_rms(out, fs, 1, 5)
        bad = []
        for name, t0, t1 in EVENTS:
            i0 = int((UTCDateTime(t0) - start) * fs)
            i1 = int((UTCDateTime(t1) - start) * fs)
            k = int(np.sum((held >= i0) & (held <= i1)))
            if k:
                bad.append(f"{k} in {name}")
        print(f"{j:>10,} {j*UV_PER_COUNT:>7.0f} {n:>7,} {n/hours:>7.1f} "
              f"{100*n/len(x):>7.3f}% {r15:>9.2f} {r5:>8.2f}  "
              f"{'; '.join(bad) if bad else 'none'}")

    print("\nevent windows checked:")
    for name, t0, t1 in EVENTS:
        i0 = int((UTCDateTime(t0) - start) * fs)
        i1 = int((UTCDateTime(t1) - start) * fs)
        seg = x[i0:i1]
        d = np.abs(np.diff(seg))
        print(f"  {name}: {t0}..{t1}  peak |sample-to-sample jump| = "
              f"{d.max():,} ct ({d.max()*UV_PER_COUNT:.0f} uV)")
        print(f"    -> any threshold above {d.max():,} counts cannot touch it")


if __name__ == "__main__":
    main()
