#!/usr/bin/env python3
"""refstation_spectra.py — is the 1.2x against NP.1835 flat in frequency, or a site bump?

refstation_compare.py reduces every shared event to one number, the 5-15 Hz RMS ratio,
and that number sits at ~1.2 with 0.6-3x scatter. One number cannot say whether the
discrepancy is a calibration constant (our sensitivity is wrong by 20%: the ratio is the
same at every frequency) or a site effect (the 1.64 km of alluvium under Fire Station 7
amplifies some band relative to our garage slab: the ratio has shape). This script keeps
the frequency axis.

For every confirmed event both stations recorded above their own floors:
  * both records in ground velocity, exactly as refstation_compare (1835 response
    removed by obspy; ours = counts * UV_PER_COUNT / EFFECTIVE_SENS, no response model),
  * Welch PSD (median-averaged) over the harvest's P/S window and over the 60 s before it,
  * the amplitude ratio  R(f) = sqrt(PSD_1835 / PSD_ours)  wherever BOTH stations are at
    least SNR_MIN above their own pre-event PSD in that bin (else NaN: not a measurement),
then the median R(f) over events with its 16-84% band, and the same for the pre-event
noise (which is the two instruments' noise floors as much as the ground, so it is shown
but not fitted).

Below the 4.5 Hz geophone corner ours is not corrected, so the ratio there is the
geophone's response, not the ground; that region is shaded and excluded from the fit.
The fit is a straight line in log-log over 5-15 Hz; the slope is the answer. Zero slope
and a flat curve at 1.2 = a constant, fix the sensitivity. A tilt or a bump = site.

    analysis/.venv/bin/python analysis/refstation_spectra.py            # all confirmed
    analysis/.venv/bin/python analysis/refstation_spectra.py --no-cache  # refetch NCEDC

Writes doc/refstation-spectra.png and prints the per-band table. Reference waveforms are
cached under analysis/data/refcache/ (gitignored with the rest of analysis/data).
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import epochs                                                                  # noqa: E402
from refstation import BAND, EFFECTIVE_SENS, REF, UV_PER_COUNT, reference      # noqa: E402
from refstation_compare import ANCHOR, CSV, JSON_OUT, harvest_row, our_trace   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "refcache")
OUT_PNG = os.path.join(os.path.dirname(HERE), "doc", "refstation-spectra.png")
OUT_JSON = os.path.join(os.path.dirname(HERE), "doc", "refstation-spectra.json")

NPERSEG = 256          # 2.56 s at 100 sps -> 0.39 Hz bins; the P/S boxes are 20-60 s
NOISE_S = 60.0         # pre-event window length
SNR_MIN = 3.0          # power ratio signal/noise a bin needs, on BOTH stations, to count
FMIN, FMAX = 1.0, 30.0
FIT = BAND             # 5-15 Hz, above the geophone corner and below 1835's pre_filt roll-off

TEAL, INK, RED, BLUE, MUT = "#2f6f6b", "#16211f", "#c0392b", "#2c6e9b", "#6b7775"


def cached_reference(o, t0, t1, use_cache=True):
    """NP.1835 velocity trace for [t0, t1], cached as miniSEED of the corrected data."""
    from obspy import read
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{'.'.join(REF)}.{str(o)[:19].replace(':', '')}.vel.mseed")
    if use_cache and os.path.exists(path):
        return read(path)[0]
    tr = reference(t0, t1)
    tr.data = tr.data.astype(np.float64)
    tr.write(path, format="MSEED", encoding="FLOAT64")
    return tr


def psd(x, fs):
    from scipy.signal import welch
    f, p = welch(x, fs=fs, nperseg=min(NPERSEG, len(x)), average="median", detrend="constant")
    return f, p


def one_event(origin, row, use_cache=True):
    from obspy import UTCDateTime
    o = UTCDateTime(origin)
    tp, ts = float(row["tp_s"]), float(row["ts_s"])
    w0, w1 = tp - 2.0, ts + 22.0                                  # harvest's P/S box
    n0, n1 = w0 - 2.0 - NOISE_S, w0 - 2.0
    t0, t1 = o + n0 - 60, o + w1 + 60
    ref = cached_reference(o, t0, t1, use_cache)
    mine = our_trace(o, t0, t1)
    out = {}
    for name, tr, scale in (("ref", ref, 1e6), ("our", mine, UV_PER_COUNT / EFFECTIVE_SENS)):
        tr = tr.copy().detrend("demean")
        fs = float(tr.stats.sampling_rate)
        sig = tr.slice(o + w0, o + w1).data.astype(float) * scale      # um/s
        noi = tr.slice(o + n0, o + n1).data.astype(float) * scale
        if len(sig) < NPERSEG or len(noi) < NPERSEG:
            raise ValueError(f"{name}: window too short ({len(sig)}, {len(noi)} samples)")
        f, ps = psd(sig, fs)
        _, pn = psd(noi, fs)
        out[name] = (f, ps, pn)
    fr, ps_r, pn_r = out["ref"]
    fm, ps_m, pn_m = out["our"]
    if len(fr) != len(fm) or np.max(np.abs(fr - fm)) > 1e-6:
        # 1835 HNZ is 100 sps too, but guard: interpolate ours onto the reference grid
        ps_m, pn_m = np.interp(fr, fm, ps_m), np.interp(fr, fm, pn_m)
    good = (ps_r >= SNR_MIN * pn_r) & (ps_m >= SNR_MIN * pn_m)
    ratio = np.where(good, np.sqrt(ps_r / ps_m), np.nan)
    noise_ratio = np.sqrt(pn_r / pn_m)
    return dict(f=fr, ratio=ratio, noise_ratio=noise_ratio, good=good,
                ps_r=ps_r, ps_m=ps_m, pn_r=pn_r, pn_m=pn_m,
                amp_epoch_ok=not epochs.crossed(ANCHOR, origin, "amplitude"))


def usable_origins():
    """Confirmed events whose reference was above its floor (refstation.json says so)."""
    with open(JSON_OUT) as fh:
        store = json.load(fh)
    return [(k, v) for k, v in sorted(store.items()) if v.get("ref_ok")]


def band_stats(f, curves, lo, hi):
    """Median ratio over a band, pooling every event's bins in it."""
    m = (f >= lo) & (f <= hi)
    vals = np.concatenate([c[m] for c in curves])
    vals = vals[np.isfinite(vals)]
    if vals.size < 5:
        return float("nan"), float("nan"), float("nan"), int(vals.size)
    q16, q50, q84 = np.percentile(vals, [16, 50, 84])
    return float(q50), float(q16), float(q84), int(vals.size)


def fit_slope(f, med):
    m = (f >= FIT[0]) & (f <= FIT[1]) & np.isfinite(med)
    if m.sum() < 4:
        return float("nan"), float("nan")
    x, y = np.log10(f[m]), np.log10(med[m])
    slope, icpt = np.polyfit(x, y, 1)
    return float(slope), float(10 ** (icpt + slope * np.log10(10.0)))   # slope, ratio at 10 Hz


def figure(f, results, labels, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    R = np.array([r["ratio"] for r in results])
    N = np.array([r["noise_ratio"] for r in results])
    count = np.isfinite(R).sum(axis=0)
    with np.errstate(all="ignore"):
        med = np.where(count >= 3, np.nanmedian(R, axis=0), np.nan)
        lo = np.where(count >= 3, np.nanpercentile(R, 16, axis=0), np.nan)
        hi = np.where(count >= 3, np.nanpercentile(R, 84, axis=0), np.nan)
        nmed = np.nanmedian(N, axis=0)
    slope, r10 = fit_slope(f, med)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 8.4), dpi=100, sharex=True,
                                 gridspec_kw=dict(height_ratios=[3, 2], hspace=0.08))
    for a in (a1, a2):
        a.set_xscale("log")
        a.set_yscale("log")
        a.axvspan(FMIN, 4.5, color="#e6e0d2", alpha=0.6, lw=0)
        a.axvspan(*FIT, color=TEAL, alpha=0.06, lw=0)
        a.axhline(1.0, color=MUT, lw=0.8, ls=":")
        a.grid(True, which="both", color="#eee", lw=0.6)
        a.set_xlim(FMIN, FMAX)
    for r in R:
        a1.plot(f, r, color=TEAL, alpha=0.18, lw=0.8)
    a1.fill_between(f, lo, hi, color=TEAL, alpha=0.25, lw=0, label="16-84% of events")
    a1.plot(f, med, color=INK, lw=2.4, label=f"median of {len(results)} events")
    a1.axhline(1.21, color=RED, lw=1.2, ls="--", label="1.21 = the 5-15 Hz RMS ratio (refstation_compare)")
    if np.isfinite(slope):
        fx = np.geomspace(*FIT, 50)
        a1.plot(fx, r10 * (fx / 10.0) ** slope, color=RED, lw=1.6,
                label=f"fit 5-15 Hz: slope {slope:+.2f}, {r10:.2f} at 10 Hz")
    a1.set_ylim(0.2, 6)
    a1.set_ylabel("amplitude ratio  NP.1835 / OAKM1", fontsize=11)
    a1.text(1.05, 4.6, "below the 4.5 Hz\ngeophone corner:\nours uncorrected", fontsize=8.5, color=MUT, va="top")
    a1.legend(loc="lower right", fontsize=9, framealpha=0.95)
    a1.set_title("Is the 1835 discrepancy flat (calibration) or shaped (site)?  Event spectra, both stations "
                 "above their own floor", fontsize=12.5, color=INK, loc="left")

    a2.plot(f, nmed, color=BLUE, lw=2.0, label="pre-event noise ratio, median (instrument floors included)")
    for n in N:
        a2.plot(f, n, color=BLUE, alpha=0.12, lw=0.7)
    a2.set_ylim(0.1, 30)
    a2.set_ylabel("noise ratio  1835 / OAKM1", fontsize=11)
    a2.set_xlabel("frequency (Hz)", fontsize=11)
    a2.legend(loc="upper right", fontsize=9, framealpha=0.95)
    a2.set_xticks([1, 2, 3, 5, 7, 10, 15, 20, 30])
    a2.set_xticklabels(["1", "2", "3", "5", "7", "10", "15", "20", "30"])

    fig.text(0.01, 0.01, "Welch PSD, 2.56 s segments, median-averaged, over the harvest P/S window; a bin counts only when both "
             f"stations are >= {SNR_MIN:g}x their own pre-event PSD. Ours: counts -> velocity by the provisional "
             f"{EFFECTIVE_SENS:.1f} V/(m/s), no response model. 1835: NCEDC response removed to velocity.",
             fontsize=8, color=MUT)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    return med, lo, hi, nmed, count, slope, r10


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--all-epochs", action="store_true",
                    help="include events across an amplitude epoch boundary (default: anchor epoch only)")
    ap.add_argument("--out", default=OUT_PNG)
    args = ap.parse_args()

    results, labels, skipped = [], [], []
    for origin, meta in usable_origins():
        row = harvest_row(origin)
        if row is None:
            skipped.append((origin, "no harvest row")); continue
        try:
            r = one_event(origin, row, use_cache=not args.no_cache)
        except Exception as e:                                   # noqa: BLE001
            skipped.append((origin, str(e)[:70])); continue
        if not r["amp_epoch_ok"] and not args.all_epochs:
            skipped.append((origin, "crosses an amplitude epoch")); continue
        nb = int(r["good"][(r["f"] >= FIT[0]) & (r["f"] <= FIT[1])].sum())
        if nb < 4:
            skipped.append((origin, f"only {nb} usable bins in 5-15 Hz")); continue
        results.append(r)
        labels.append(f"{origin[:16]} M{meta['mag']:.1f} {meta['place']}")
        print(f"  {origin[:16]}  M{meta['mag']:.1f} {meta['dist_km']:5.1f} km  "
              f"{nb:2d}/{int(((r['f'] >= FIT[0]) & (r['f'] <= FIT[1])).sum())} bins  "
              f"{meta['place']}")
    if len(results) < 3:
        sys.exit(f"only {len(results)} usable events; skipped: {skipped}")

    f = results[0]["f"]
    med, lo, hi, nmed, count, slope, r10 = figure(f, results, labels, args.out)
    bands = [(1.0, 2.0), (2.0, 4.5), (4.5, 5.0), (5.0, 7.0), (7.0, 10.0), (10.0, 15.0),
             (15.0, 20.0), (20.0, 30.0)]
    print(f"\n{len(results)} events in the stack, {len(skipped)} skipped")
    for o, why in skipped:
        print(f"    skip {o[:16]}  {why}")
    print(f"\n  band (Hz)     median   16%    84%   bins    noise-ratio median")
    table = []
    curves = [r["ratio"] for r in results]
    for lo_f, hi_f in bands:
        q50, q16, q84, n = band_stats(f, curves, lo_f, hi_f)
        nq = band_stats(f, [r["noise_ratio"] for r in results], lo_f, hi_f)[0]
        tag = "  <- geophone corner, uncorrected" if hi_f <= 4.5 else ""
        print(f"  {lo_f:4.1f}-{hi_f:4.1f}   {q50:6.2f} {q16:6.2f} {q84:6.2f}  {n:5d}      {nq:6.2f}{tag}")
        table.append(dict(lo=lo_f, hi=hi_f, median=q50, p16=q16, p84=q84, n=n, noise_median=nq))
    print(f"\n  log-log slope over {FIT[0]:g}-{FIT[1]:g} Hz: {slope:+.3f}   (ratio at 10 Hz {r10:.2f})")
    print("  flat + ~1.2 => a constant, i.e. sensitivity; tilt or bump => the ground (or a response error)")
    with open(OUT_JSON, "w") as fh:
        json.dump(dict(n_events=len(results), events=labels, slope=slope, ratio_10hz=r10,
                       bands=table, fit_band=FIT, snr_min=SNR_MIN, nperseg=NPERSEG,
                       skipped=skipped), fh, indent=1)
    print(f"\n  wrote {args.out}\n        {OUT_JSON}")


if __name__ == "__main__":
    main()
