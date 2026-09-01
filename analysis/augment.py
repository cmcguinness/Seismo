#!/usr/bin/env python3
"""augment.py — more training positives by adding real noise to real earthquakes.

WHY, and what this does NOT buy. The classifier has 33 positives against thousands of
cultural negatives, and that count is set by how often the ground moves inside our
89 km reach -- roughly 5/week. Template matching was the route that would have added
genuinely new events; it does not work on this catalogue (see template_match.py, which
records the measurement). So the remaining cheap move is augmentation.

Be clear about what it is worth: this multiplies the SAMPLE COUNT, not the
INFORMATION. There are still 33 independent earthquakes in here afterwards. What it
buys is the decision boundary -- by burying known events in progressively more real
noise we generate the weak, marginal, barely-triggering positives that the catalogue
gives us only a handful of, and those are exactly the class the model is worst at. It
will not improve generalisation to genuinely new sources, and nobody should read a
PR-AUC computed on augmented rows as if it had.

HOW, and why it is not just "add noise to the waveform".

  REAL NOISE, NOT SYNTHETIC. The noise comes from our own archive, sampled across the
  day so the diurnal range is represented, and drawn at least 180 s from any catalogue
  event so an augmentation cannot quietly contain a second earthquake. Gaussian noise
  would be the wrong distribution: this station's background is cultural, impulsive and
  strongly non-stationary, and a model taught to separate quakes from white noise has
  learned nothing about the problem it faces.

  peak_ratio IS TRANSFORMED ANALYTICALLY, NOT RE-MEASURED. Three of the model's
  features -- peak_ratio, duration_s, hf_lf -- come from the STA/LTA rather than the
  waveform, and copying them onto a noisier copy would describe a trigger that could
  never occur: a buried event would have had a LOWER peak_ratio.

  Re-running the detector on a windowed slice does not reproduce it either. On pi5 the
  STA/LTA runs CONTINUOUSLY, so its 30 s LTA carries hours of history; cold-started on a
  150 s lead it reported peak_ratio 5.2 where the real detector logged 61.2. Worse, many
  real positives sit barely over the trigger threshold -- one is 4.07 against trig=4.0 --
  so a slightly different LTA means they do not re-trigger at all, and 60% of the events
  were being lost to that.

  The physics gives it directly and needs no detector state. The characteristic function
  is energy, so the LTA converges to the background variance and the peak ratio of an
  event of amplitude A over background sigma is

      R = (A^2 + sigma^2) / sigma^2  =  1 + A^2/sigma^2.

  Adding INDEPENDENT noise at alpha times the background takes sigma^2 to
  sigma^2 (1 + alpha^2), and A is untouched, so

      R' = 1 + (R - 1) / (1 + alpha^2).

  That is exact under the assumptions the detector already makes, it starts from the
  real logged R, and it is monotone -- burying an event always lowers its ratio.

  duration_s and hf_lf are scaled by what the WAVEFORM does, measuring both on the clean
  and the noisy window with the same code and keeping the ratio, so any bias cancels.
  These come from features(), which was checked against the real rows and reproduces
  them closely (kurtosis 3.33 vs 3.28, 1.93 vs 1.92, 8.73 vs 8.73).

  AUGMENTATIONS THAT FALL BELOW THE TRIGGER ARE DROPPED, on purpose. Bury an event
  deep enough and R' drops under the detector's trig threshold -- and the classifier
  only ever scores things that triggered, so a row for an untriggered event would
  describe a situation the model cannot encounter. The drop rate is reported: it maps
  where the detector's own floor sits, which is useful in itself.

  ONLY THE NOISE CHANGES. The window is the real trigger's window, so the only
  difference between a real positive row and its augmentations is the added noise. If
  augmented rows differed systematically in some other way -- window alignment, say --
  the model could learn to recognise "augmented" and, since every augmented row is a
  positive, that shortcut would BE the label.

  GROUPS ARE INHERITED. Every augmentation carries its source event's `origin`, which
  is what trigger_train.py groups positives on, so all derivatives of one earthquake
  land in the same CV fold. Without that, near-duplicates straddle the split and the
  score climbs for no reason. `is_aug` marks them so training can keep them out of the
  test folds and the holdout entirely.

    python analysis/augment.py --n-noise 6 --out analysis/data/trigger_features_aug.csv
"""
import argparse
import csv
import glob
import os
import random
import sys

import numpy as np
from obspy import Stream, UTCDateTime, read

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
from trigger_features import features, PRE, POST, UV         # noqa: E402

CSV_IN = os.path.join(HERE, "data", "trigger_features.csv")
HARVEST = os.path.join(HERE, "event_harvest.csv")
ARCHIVE = os.path.join(HERE, "data")
FS = 100.0
LEAD_S = 150.0      # ahead of the trigger: the LTA is 30 s and needs priming, and a
                    # cold-started LTA would inflate every ratio we then report
TRAIL_S = 90.0
TRIG = 4.0          # detector.py's trigger threshold: below this there is no row
ALPHAS = (0.5, 1.0, 2.0, 3.5, 6.0)   # noise scale: added RMS relative to the window's own


def load_trace(path):
    st = read(path)
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [t.stats.sampling_rate for t in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([t for t in st if t.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    tr = max(st, key=lambda t: t.stats.npts)
    return tr if abs(tr.stats.sampling_rate - FS) < 0.5 else None


def rl(v):
    return float(v) if v not in ("", "None") else float("nan")


def _safe(a_, b_):
    """a_/b_, falling back to 1.0 when either is missing or degenerate."""
    try:
        a_, b_ = float(a_), float(b_)
    except (TypeError, ValueError):
        return 1.0
    if not np.isfinite(a_) or not np.isfinite(b_) or b_ == 0:
        return 1.0
    return a_ / b_


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-noise", type=int, default=6, help="noise draws per event per alpha")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "trigger_features_aug.csv"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool-files", type=int, default=12)
    ap.add_argument("--pool-per-file", type=int, default=25)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    pos = [r for r in csv.DictReader(open(CSV_IN)) if r["label"] == "1"]
    print(f"{len(pos)} real positive rows, {len(set(r['origin'] for r in pos))} distinct events")

    # times to keep the noise pool away from: every catalogue event, seen or not
    cat = [UTCDateTime(r["origin"]).timestamp
           for r in csv.DictReader(open(HARVEST))]
    cat = np.array(sorted(cat))

    files = sorted(glob.glob(f"{ARCHIVE}/*.mseed"))
    span = LEAD_S + TRAIL_S

    # Build the noise pool ONCE. Drawing a fresh window per augmentation meant loading
    # and merging a ~25 MB day-file per draw, which put a single pass over 58 events at
    # the wrong side of ten minutes; the noise is drawn with replacement anyway.
    print(f"building noise pool from {min(len(files), a.pool_files)} day-files "
          f"(>=180 s from any catalogue event)...", flush=True)
    pool = []
    rng.shuffle(files)
    for f in files[:a.pool_files]:
        tr = load_trace(f)
        if tr is None or tr.stats.npts < span * FS * 2:
            continue
        dur = tr.stats.npts / FS
        for _ in range(a.pool_per_file):
            t0 = tr.stats.starttime + rng.uniform(0, dur - span - 1)
            if cat.size and np.abs(cat - (t0.timestamp + span / 2)).min() < 180 + span / 2:
                continue
            seg = tr.slice(t0, t0 + span)
            if seg.stats.npts >= int(span * FS):
                x = np.asarray(seg.data[:int(span * FS)], float)
                pool.append(x - np.mean(x))
    if not pool:
        print("no clean noise windows found"); return 1
    rms = [float(np.std(p)) for p in pool]
    print(f"  {len(pool)} noise windows, RMS {min(rms):.0f}-{max(rms):.0f} counts "
          f"(median {np.median(rms):.0f}) -- the diurnal spread is the point")

    cache = {}

    def get(path):
        if path not in cache:
            if len(cache) > 3:
                cache.clear()
            cache[path] = load_trace(path)
        return cache[path]

    rows, lost, kept_by_alpha = [], 0, {al: 0 for al in ALPHAS}
    for n, r in enumerate(pos, 1):
        t_trig = UTCDateTime(r["start"])
        f = sorted(glob.glob(f"{ARCHIVE}/*.D.{t_trig.year}.{t_trig.julday:03d}.mseed"))
        if not f:
            continue
        tr = get(f[-1])
        if tr is None:
            continue
        seg = tr.slice(t_trig - LEAD_S, t_trig + TRAIL_S)
        if seg.stats.npts < int(span * FS):
            continue
        base = np.asarray(seg.data[:int(span * FS)], float)
        base_rms = float(np.std(base[:int(60 * FS)])) or 1.0
        i_trig = int(LEAD_S * FS)
        w0, w1 = i_trig - int(PRE * FS), i_trig + int(POST * FS)
        if w0 < 0 or w1 > len(base):
            continue
        fe_base = features(base[w0:w1], FS, int(PRE * FS))
        R = rl(r["peak_ratio"])

        for alpha in ALPHAS:
            # the analytic transform: energy CF, independent noise
            R_new = 1.0 + (R - 1.0) / (1.0 + alpha ** 2)
            if not (R_new >= TRIG):
                lost += a.n_noise       # buried past the detector's own floor
                continue
            for _ in range(a.n_noise):
                nz = rng.choice(pool)
                nz = nz * (alpha * base_rms / (np.std(nz) or 1.0))
                aug = base + nz
                fe = features(aug[w0:w1], FS, int(PRE * FS))
                dscale = _safe(fe.get("dur3_s"), fe_base.get("dur3_s"))
                hscale = _safe(fe.get("hf_lf_win"), fe_base.get("hf_lf_win"))
                rows.append(dict(
                    start=r["start"][:19], label=1,
                    peak_ratio=round(R_new, 2),
                    duration_s=round(rl(r["duration_s"]) * dscale, 2),
                    peak_uv=round(rl(r["peak_uv"]), 1),
                    # missingness is carried through: hf_lf is absent from 25 of the 58
                    # real positive rows (an older events.log schema), and filling it in
                    # only for augmented rows would make them identifiable -- which,
                    # since every augmented row is a positive, the model could use as
                    # the label itself.
                    hf_lf=("" if r["hf_lf"] in ("", "None")
                           else round(rl(r["hf_lf"]) * hscale, 2)),
                    hour_local=r.get("hour_local", ""),
                    mag=r.get("mag", ""), dist=r.get("dist", ""),
                    place=r.get("place", ""), origin=r["origin"],
                    is_aug=1, aug_alpha=alpha, **fe))
                kept_by_alpha[alpha] += 1
        print(f"  [{n}/{len(pos)}] {r['origin'][:19]} -> {len(rows)} rows, {lost} lost",
              flush=True)

    if not rows:
        print("no augmented rows produced"); return 1
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    tried = len(pos) * len(ALPHAS) * a.n_noise
    print(f"\nwrote {len(rows)} augmented positives -> {a.out}")
    print(f"  {lost}/{tried} ({100*lost/tried:.0f}%) failed to trigger and were dropped")
    print("  kept by noise scale:  " +
          "  ".join(f"a={al}: {k}" for al, k in kept_by_alpha.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
