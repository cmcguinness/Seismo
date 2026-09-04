#!/usr/bin/env python3
"""coda_probe.py — does frequency-dependent attenuation separate quakes from trucks?

THE OBSERVATION (Charles, 2026-09-04): watching real earthquakes on the spectrogram, the
spectrum starts broad and narrows toward low frequency as the event goes on. High
frequencies die faster.

THE PHYSICS. Intrinsic attenuation goes as exp(-pi f t / Q): the decay rate is
proportional to FREQUENCY, so along any path the high frequencies are stripped first.
Inside one event this shows up in the coda, whose later arrivals are scattered energy
that travelled further and lost more high frequency on the way. Measuring exactly this is
a standard technique -- coda Q.

WHY IT SHOULD DISCRIMINATE, which is what makes it worth measuring rather than merely
true. A passing truck is a SOURCE IN MOTION past a fixed sensor: its spectrum changes
with distance and Doppler, not by frequency-dependent absorption along a fixed path. A
door slam decays fast in every band at once -- that is structural damping. An earthquake
should be the only one of the three whose high bands decay measurably faster than its low
bands.

>>> MEASURED RESULT: THE EFFECT IS REAL AND MEASURABLE. IT CANNOT BE SHOWN TO HELP. <<<

Run it and the best candidate, `drop_diff_hi_lo_db`, separates at ROC-AUC 0.871 on every
row with no thresholds -- better than any single feature already in the model. The
candidates are also NOT redundant with the existing seventeen: the largest Spearman
correlation anywhere in the matrix is drop_hi_db against kurtosis at +0.50, and the
prediction that decay_lo would merely re-describe dur3_s was wrong at rho 0.17.

And then `coda_ab.py` adds them to the model and the gain vanishes into fold noise. All
nine candidates: mean per-fold delta +0.016, positive in 2 of 5 folds. The pre-specified
best two: +0.042, positive in 3 of 5. Both flip sign between folds. With 33 positives
split five ways, one Geysers sequence landing in a different fold moves PR-AUC by 0.25,
and the effect we are chasing is around 0.04. The experiment is underpowered, not the
idea disproved -- revisit at ~100 positives, when this measurement is already built.

ONE FINDING SURVIVES REGARDLESS, and it is the useful one: the sign is BACKWARDS from
the physics. Cultural triggers show the high band falling 11.7 dB further than the low;
earthquakes show -2.0 dB, their LOW band falling further. That is very likely saturation
rather than propagation -- the measurement bottoms out once a band reaches its own noise
floor, and a truck's high band starts far above the HF floor while its low band barely
clears the LF background. So this reads "which band had more headroom to lose", which is
close to "how bass-heavy was it" and is not coda Q. Anyone reviving this should fix that
before claiming attenuation physics.

WHAT THIS SCRIPT IS NOT. It does not add anything to the model. It measures the candidate
on the rows we already have labels for and reports whether it separates, so the decision
to spend a feature column is made on evidence. With 33 real positives, adding columns is
how you overfit, and a candidate that cannot show separation here should not be added.

Note a feature does NOT have to work on every earthquake to be worth having (Charles):
a tree ensemble is perfectly happy with a feature that is decisive in one corner of the
space and useless elsewhere. So the summary reports the tail as well as the average.

    analysis/.venv/bin/python analysis/coda_probe.py
    analysis/.venv/bin/python analysis/coda_probe.py --min-ratio 20
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

# THE WINDOW IS THE FIRST FINDING, and it is why the model cannot possibly see this.
#
# server/trigger_features.py uses PRE=5, POST=25 -- the window closes 25 s after the
# trigger. On the spectrogram that inspired this (2026-09-04) the arrival is at ~2 s and
# the narrowing toward low frequency is still visibly running at 42 s. More than a third
# of the evidence is outside the window the classifier is handed, so no feature computed
# on that window could encode it, however cleverly written.
#
# This probe therefore reads a LONGER window straight from the day-files. If the
# candidate earns a column, trigger_features.py's POST has to grow with it -- which is a
# real change, because it also delays how soon a live trigger can be scored.
PRE, POST = 5.0, 60.0
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6

# Bands for the decay measurement. Deliberately only three and deliberately wide: we are
# fitting a slope in each, and a narrow band on a short noisy coda gives a slope with no
# meaning. LO and HI are the pair the ratio is built from; MID is reported for shape.
# Bands chosen from where the effect is actually VISIBLE and the instrument is honest.
# The inspiring spectrogram is plotted 0-25 Hz and the narrowing happens entirely inside
# it, so the old 15-40 Hz high band was looking above the phenomenon -- and into the
# region where the ADC's sinc^5 roll-off is already -12 dB at 40 Hz, i.e. the noisiest
# part of our band. 10-20 Hz is high enough to attenuate visibly and low enough to trust.
B_LO, B_MID, B_HI = (2.0, 5.0), (5.0, 10.0), (10.0, 20.0)

# Out to 30 s, not 8. The narrowing is a slow business: on the reference spectrogram the
# high bands are still fading at 40 s. An 8 s fit measures the first moments of a decay
# whose whole point is what it does later.
FIT_FROM, FIT_TO = 0.5, 30.0
MIN_FIT_DB = 3.0                      # need this much decay to fit a slope at all


def band_env(x, fs, lo, hi):
    """Smoothed Hilbert envelope of one band."""
    sos = signal.butter(4, [lo, min(hi, fs / 2 * 0.98)], btype="band", fs=fs, output="sos")
    e = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))
    k = max(1, int(0.25 * fs))
    return np.convolve(e, np.ones(k) / k, "same")


def decay_rate(env, fs, noise, t_idx):
    """Decay constant in nepers/second from a straight-line fit to the log-envelope after
    this band's own peak, or nan if the band was never measurable.

    THREE THINGS HERE ARE NOT OBVIOUS, and all three were bugs first (2026-09-04):

    - The peak is searched only in the 12 s AFTER THE TRIGGER, not over the whole window.
      Searching everywhere lets a louder unrelated event later in the 25 s tail steal the
      peak, and the fit then measures that instead. It showed up as "peak at 33.9 s of
      34 s", which is not this trigger at all.

    - Each band finds its OWN peak, which is the point rather than a detail: on a big
      local event the low band is still RISING when the high band has already peaked,
      because the surface waves have not arrived yet. A shared peak index would measure
      the low band's rise as a negative decay, and it did.

    - The fit stops at the LAST sample above the floor, not the first dip below it. An
      envelope wobbles; truncating at the first excursion threw away codas that ran for
      seconds, and was why this measured almost nothing on the first run.

    nan rather than 0 on failure, deliberately: 0 reads as "did not decay", which is a
    measurement, and we did not make one. The model handles missing values natively.
    """
    hunt_to = min(len(env), t_idx + int(12.0 * fs))
    ipk = t_idx + int(np.argmax(env[t_idx:hunt_to])) if hunt_to > t_idx else int(np.argmax(env))
    a = ipk + int(FIT_FROM * fs)
    b = min(len(env), ipk + int(FIT_TO * fs))
    if b - a < int(1.0 * fs) or env[ipk] <= 0 or noise <= 0:
        return np.nan
    seg = env[a:b]
    above = np.flatnonzero(seg > noise * 1.2)
    if len(above) < int(1.0 * fs):
        return np.nan
    seg = seg[: above[-1] + 1]                   # to the END of the sustained coda
    if len(seg) < int(1.0 * fs):
        return np.nan
    y = np.log(np.maximum(seg, 1e-12))
    if (y[0] - y[-1]) < MIN_FIT_DB / 8.686:      # dB -> nepers; must actually decay
        return np.nan
    t = np.arange(len(seg)) / fs
    return float(-np.polyfit(t, y, 1)[0])


def drop_db(env, fs, t_idx, at=(15.0, 25.0)):
    """How far this band fell, in dB, from its own peak to a fixed slice of coda later.

    THE POINT OF THIS ONE IS THAT IT HAS NO THRESHOLDS. decay_rate() above refuses to
    answer unless the coda clears a noise floor and falls at least MIN_FIT_DB, so it
    returns nan on 81-91% of rows -- and "nan" then carries the discrimination, which
    means the feature is really encoding *whether my guards were satisfied*. Change
    MIN_FIT_DB from 3 to 4 and the feature silently changes meaning. That is a brittle
    thing to ship, and it throws away a perfectly good number to do it.

    So: measure the fall and report it, always, and let the model choose its own
    threshold. It saturates once the band reaches the noise floor -- past that you are
    measuring signal-to-noise rather than decay -- but the model has snr_env alongside
    and trees are perfectly happy with a saturating feature.
    """
    hunt_to = min(len(env), t_idx + int(12.0 * fs))
    ipk = t_idx + int(np.argmax(env[t_idx:hunt_to])) if hunt_to > t_idx else int(np.argmax(env))
    a, b = ipk + int(at[0] * fs), ipk + int(at[1] * fs)
    if b > len(env) or env[ipk] <= 0:
        return np.nan
    late = float(np.mean(env[a:b]))
    return float(20.0 * np.log10(env[ipk] / max(late, 1e-12)))


def centroid(x, fs, lo=1.0, hi=45.0):
    if len(x) < int(0.5 * fs):
        return np.nan
    f, p = signal.welch(x, fs=fs, nperseg=min(len(x), int(2 * fs)), average="median")
    m = (f >= lo) & (f < hi)
    return float(np.sum(f[m] * p[m]) / (np.sum(p[m]) + 1e-30))


def candidates(x, fs, t_idx):
    """The features under test, for one window of raw counts."""
    x = (np.asarray(x, float) - np.median(x)) * UV
    pre = x[: max(1, t_idx - int(0.5 * fs))]
    out = {}

    rates, drops = {}, {}
    for name, (lo, hi) in (("lo", B_LO), ("mid", B_MID), ("hi", B_HI)):
        e = band_env(x, fs, lo, hi)
        n = float(np.median(band_env(pre, fs, lo, hi))) if len(pre) > int(fs) else float(np.median(e))
        rates[name] = decay_rate(e, fs, n, t_idx)
        out[f"decay_{name}"] = rates[name]
        drops[name] = drop_db(e, fs, t_idx)
        out[f"drop_{name}_db"] = drops[name]

    # THE HEADLINE. >1 means the high band died faster than the low band, which is what
    # attenuation along a path does and what a truck driving past does not.
    out["decay_ratio_hi_lo"] = (rates["hi"] / rates["lo"]
                                if np.isfinite(rates["hi"]) and np.isfinite(rates["lo"])
                                and rates["lo"] > 0 else np.nan)

    # THE DIRECT TEST OF THE HYPOTHESIS, and the one that is almost always computable:
    # did the high band fall FURTHER than the low band over the same stretch of coda?
    # Positive = yes = high frequencies attenuated faster, which is what Charles saw on
    # the spectrogram and what propagation through rock is supposed to do. A difference
    # of decibels rather than a ratio of rates, because a difference is defined whenever
    # both numbers exist and a ratio blows up when the denominator is near zero.
    out["drop_diff_hi_lo_db"] = (drops["hi"] - drops["lo"]
                                 if np.isfinite(drops["hi"]) and np.isfinite(drops["lo"])
                                 else np.nan)

    # The same story told without fitting anything: where the spectrum sits early in the
    # event minus where it sits late. Positive = narrowed toward low frequency.
    ipk = t_idx + int(np.argmax(np.abs(x[t_idx:]))) if t_idx < len(x) else t_idx
    # Straddle the narrowing rather than sampling twice inside its opening seconds.
    early = x[ipk: ipk + int(5 * fs)]
    late = x[ipk + int(20 * fs): ipk + int(45 * fs)]
    ce, cl = centroid(early, fs), centroid(late, fs)
    out["centroid_drift"] = ce - cl if np.isfinite(ce) and np.isfinite(cl) else np.nan
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-ratio", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=0, help="stop after N rows (debug)")
    ap.add_argument("--out", default=None,
                    help="write the measured candidates to a CSV, keyed by trigger start, "
                         "so trigger_train.py can join them onto the existing feature table "
                         "and answer the only question that matters: do they ADD anything?")
    a = ap.parse_args()

    from obspy import UTCDateTime, read

    rows = [r for r in csv.DictReader(open(CSV))
            if float(r.get("peak_ratio") or 0) >= a.min_ratio]
    by_day = {}
    for r in rows:
        t = UTCDateTime(r["start"])
        by_day.setdefault((t.year, t.julday), []).append(r)

    got, feats = 0, []
    for (y, j), day_rows in sorted(by_day.items()):
        hits = sorted(glob.glob(os.path.join(DATA, f"*.D.{y}.{j:03d}.mseed")))
        if not hits:
            continue
        st = read(hits[-1])
        st.merge(method=1, fill_value="interpolate")
        tr = st[0]
        fs = float(tr.stats.sampling_rate)
        t0 = tr.stats.starttime
        data = tr.data.astype(float)
        for r in day_rows:
            ts = UTCDateTime(r["start"])
            i0 = int((ts - t0 - PRE) * fs)
            i1 = i0 + int((PRE + POST) * fs)
            if i0 < 0 or i1 > len(data):
                continue
            c = candidates(data[i0:i1], fs, int(PRE * fs))
            c["label"] = int(r["label"])
            c["start"] = r["start"]
            feats.append(c)
            got += 1
            if a.limit and got >= a.limit:
                break
        print(f"  {y}.{j:03d}: {got} windows", flush=True)
        if a.limit and got >= a.limit:
            break

    if not feats:
        sys.exit("no windows measured -- are the day-files in analysis/data/?")

    if a.out:
        import csv as _csv
        cols = ["start", "label"] + [k for k in feats[0] if k not in ("start", "label")]
        with open(a.out, "w", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for f in feats:
                w.writerow(f)
        print(f"wrote {a.out} ({len(feats)} rows)")

    lab = np.array([f["label"] for f in feats])
    print(f"\n{len(feats)} windows measured: {lab.sum()} quake, {(1-lab).sum()} cultural\n")

    from sklearn.metrics import average_precision_score, roc_auc_score
    names = [k for k in feats[0] if k not in ("label", "start")]   # start is a key, not a feature
    print(f"{'feature':>20}  {'computable':>10}  {'quake med':>10}  {'cult med':>10}  "
          f"{'ROC-AUC':>8}  {'PR-AUC':>7}\n")
    for n in names:
        v = np.array([f[n] for f in feats], float)
        ok = np.isfinite(v)
        if ok.sum() < 20 or lab[ok].sum() < 3:
            print(f"{n:>20}  {100*ok.mean():9.0f}%   (too few finite values to judge)")
            continue
        q, c = v[ok & (lab == 1)], v[ok & (lab == 0)]
        # HOW OFTEN IT IS COMPUTABLE IS ITSELF A SIGNAL, and it quietly inflates PR-AUC.
        # PR-AUC is measured only on rows where the feature is finite; if quakes are far
        # more likely to be computable than cultural triggers, that subset has a higher
        # base rate and the score flatters the feature. Report the subset's own base rate
        # so the multiple below is honest, and report computability by class, because a
        # feature that simply EXISTS more often for earthquakes is telling you something
        # even before its value is looked at.
        # direction-agnostic: a feature that separates the wrong way is still separating
        auc = roc_auc_score(lab[ok], v[ok])
        pr = average_precision_score(lab[ok], v[ok] if auc >= 0.5 else -v[ok])
        sub_base = lab[ok].mean()
        print(f"{n:>20}  {100*ok.mean():9.0f}%  {np.median(q):10.3f}  {np.median(c):10.3f}  "
              f"{max(auc, 1-auc):8.3f}  {pr:7.3f}   "
              f"[computable: {100*ok[lab==1].mean():.0f}% of quakes vs "
              f"{100*ok[lab==0].mean():.0f}% of cultural; subset base {sub_base:.4f}, "
              f"so PR-AUC is {pr/sub_base:.0f}x that subset]")

    base = lab.mean()
    print(f"\nbase rate {base:.4f} -- a PR-AUC at that level is a feature telling you nothing.")
    print("ROC-AUC is reported direction-agnostic (max of auc, 1-auc).")


if __name__ == "__main__":
    main()
