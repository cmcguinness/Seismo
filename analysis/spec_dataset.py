#!/usr/bin/env python3
"""spec_dataset.py — build the spectrogram tensor the CNN trains on.

Charles's proposal, 2026-09-04: stop hand-crafting summaries of the spectrum's shape and
feed the model the picture instead. Trim a window around each trigger, take overlapping
FFTs across it, bin them in frequency, and hand the resulting time-frequency image to a
convolutional network.

WHY THIS IS THE RIGHT SHAPE OF IDEA. The 17 features in trigger_features.py collapse the
whole window into ONE spectrum, so every trace of how the spectrum EVOLVES is destroyed
before the model sees anything. That evolution -- broad at onset, narrowing toward low
frequency as the high bands attenuate away -- is what Charles can see by eye on a
spectrogram and is exactly what coda_probe.py failed to capture in two hand-made numbers
(see its header: real, measurable, could not be shown to help). A spectrogram has it
natively. This feeds the model the representation the human expert actually diagnoses
from.

THREE CHOICES THAT ARE NOT THE OBVIOUS ONES, and why:

  LOG-SPACED FREQUENCY BINS, not the linear 1 Hz bins first proposed. The two strongest
  features in the tree model are frac_1_3 (+0.371) and frac_3_8 (+0.332): the
  discriminating power is concentrated in 1-8 Hz. Linear 1 Hz bins would spend 3 bins on
  that octave and 12 on 8-20 Hz where frac_15_30 is nearly dead. Attenuation is a
  log-frequency process anyway, so log bins put the resolution where the physics and the
  measured importances both say it belongs.

  UP TO 45 Hz, not 20. The narrowing is visible below 25 Hz, but on 2026-09-04 the M3.3
  measured 16x above the noise floor in 35-50 Hz and was audible. frac_30_45 is already
  a feature. Capping at 20 would discard that band by assumption; better to include it
  and let the model report whether it earns its place.

  PER-SPECTROGRAM NORMALISATION. Each image is converted to dB and then shifted so its
  own maximum is 0. That discards absolute amplitude on purpose -- the same reason
  trigger_train.py withholds peak_uv and friends (the front end was rebuilt 2026-08-07
  and amplitude encodes hardware history), and the same conclusion Yeck et al. reach
  from the opposite direction, normalising by the max across components because station
  sensitivities differ across a global network.

THE WINDOW IS THE EXPENSIVE CHOICE. --post 55 captures the narrowing, which is still
running at 42 s on the reference spectrogram, but a trigger cannot be scored until the
window closes. Yeck's team met the same wall and chose 14 s: "relying on short time
windows after the arrival reduces the delay in pick classification, which is critical in
a real-time environment." Build both and measure what the latency buys.

    analysis/.venv/bin/python analysis/spec_dataset.py --post 55 --out data/spec55.npz
    analysis/.venv/bin/python analysis/spec_dataset.py --post 25 --out data/spec25.npz
"""
import argparse
import csv
import glob
import os
import sys

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CSV = os.path.join(DATA, "trigger_features.csv")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6

MIN_RATIO = 10.0          # the rows the deployed model actually scores
F_LO, F_HI = 1.0, 45.0
N_BINS = 24
NPERSEG_S = 2.0           # 0.5 Hz resolution -- enough to resolve the lowest log bins
HOP_S = 0.5


def log_edges(lo=F_LO, hi=F_HI, n=N_BINS):
    return np.geomspace(lo, hi, n + 1)


def spectrogram_image(x, fs, pre, post):
    """One (n_bins, n_times) dB image, its own max at 0 dB."""
    x = np.asarray(x, float) - np.median(x)
    f, t, S = signal.spectrogram(x * UV, fs=fs, nperseg=int(NPERSEG_S * fs),
                                 noverlap=int((NPERSEG_S - HOP_S) * fs), mode="psd")
    e = log_edges()
    img = np.empty((N_BINS, S.shape[1]), dtype=np.float32)
    for i in range(N_BINS):
        m = (f >= e[i]) & (f < e[i + 1])
        img[i] = S[m].mean(axis=0) if m.any() else 0.0
    img = 10.0 * np.log10(img + 1e-12)
    return (img - img.max()).astype(np.float32)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--pre", type=float, default=5.0)
    a.add_argument("--post", type=float, default=55.0)
    a.add_argument("--out", default=os.path.join(DATA, "spec55.npz"))
    a.add_argument("--limit", type=int, default=0)
    a = a.parse_args()

    from obspy import UTCDateTime, read

    rows = [r for r in csv.DictReader(open(CSV))
            if float(r.get("peak_ratio") or 0) >= MIN_RATIO]
    by_day = {}
    for r in rows:
        t = UTCDateTime(r["start"])
        by_day.setdefault((t.year, t.julday), []).append(r)

    imgs, labels, groups, starts = [], [], [], []
    for (y, j), day_rows in sorted(by_day.items()):
        hits = sorted(glob.glob(os.path.join(DATA, f"*.D.{y}.{j:03d}.mseed")))
        if not hits:
            continue
        st = read(hits[-1]); st.merge(method=1, fill_value="interpolate")
        tr = st[0]; fs = float(tr.stats.sampling_rate); t0 = tr.stats.starttime
        d = tr.data.astype(float)
        for r in day_rows:
            ts = UTCDateTime(r["start"])
            i0 = int((ts - t0 - a.pre) * fs); i1 = i0 + int((a.pre + a.post) * fs)
            if i0 < 0 or i1 > len(d):
                continue
            imgs.append(spectrogram_image(d[i0:i1], fs, a.pre, a.post))
            labels.append(int(r["label"]))
            # the SAME grouping the tree model uses: an aftershock must not vouch for
            # its own mainshock, so positives group by catalogue event, negatives by day
            groups.append(r["origin"] if r["label"] == "1" else r["start"][:10])
            starts.append(r["start"])
            if a.limit and len(imgs) >= a.limit:
                break
        print(f"  {y}.{j:03d}: {len(imgs)} images", flush=True)
        if a.limit and len(imgs) >= a.limit:
            break

    X = np.stack(imgs)
    yv = np.array(labels, dtype=np.int64)
    np.savez_compressed(a.out, X=X, y=yv, groups=np.array(groups), starts=np.array(starts),
                        edges=log_edges(), pre=a.pre, post=a.post)
    print(f"\nwrote {a.out}")
    print(f"  X {X.shape} (n, freq bins, time steps)  float32  "
          f"{X.nbytes/1e6:.0f} MB in memory")
    print(f"  {int(yv.sum())} quake, {int((1-yv).sum())} cultural, "
          f"{len(set(np.array(groups)[yv == 1]))} distinct events")


if __name__ == "__main__":
    main()
