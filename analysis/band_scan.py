#!/usr/bin/env python3
"""band_scan.py -- which frequency band actually carries the signal, and does it move
with distance?

The detector uses ONE fixed band (1-15 Hz) for a 10 km event and a 250 km event alike.
Attenuation is frequency-dependent, so that cannot be right at both ends -- but "cannot
be right" is not a measurement, so this measures it before anything is changed.

METHOD. For every catalogued event with archive coverage, peak SNR is computed in a bank
of overlapping bands, using the harvest's own P and S boxes and the AUDITED noise level
(median of 75 s windows tiled across o-300..o-15 -- a single pre-origin window is what
catch_audit.py showed can be a lull, and this whole exercise is worthless measured
against a ruler we already know is bent).

THE TRAP THIS AVOIDS. Picking the best band per event and reporting the improvement is
circular: with 9 bands, the max of 9 noise draws beats the max of 1 even when nothing is
there. So the deliverable here is NOT "SNR went up". It is the BAND-vs-DISTANCE TREND,
from which a smooth rule can be fitted and then tested at a fixed false-positive rate in
a separate step. Per-event argmax appears below only as the evidence for that trend, and
the same argmax is computed on pure noise windows to show what the trend looks like when
there is no signal at all -- that null curve is the control, and any real trend has to
beat it.

Writes reports/band-vs-distance.png.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import obspy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_events import band_peak, band_rms, band_sustain, load_archive

# Overlapping half-octave-ish bands spanning what a 4.5 Hz geophone at 100 sps can see.
BANK = [(0.5, 1.5), (0.8, 2.5), (1.0, 3.0), (1.5, 4.0), (2.0, 5.0), (3.0, 7.0),
        (4.0, 10.0), (6.0, 14.0), (9.0, 20.0), (14.0, 30.0), (1.0, 15.0)]
WIDE = len(BANK) - 1                    # index of the incumbent 1-15 Hz band
NOISE_LEN = 75.0
PRE_SPAN = (-300.0, -15.0)


def noise_levels(st, o, uvpc, bands):
    """Median band_rms across tiled pre-origin windows, per band. The audited estimator."""
    out = [[] for _ in bands]
    t = PRE_SPAN[0]
    while t + NOISE_LEN <= PRE_SPAN[1]:
        try:
            w = st.slice(o + t, o + t + NOISE_LEN)
            if len(w) and w[0].stats.npts > 1024:
                for i, (lo, hi) in enumerate(bands):
                    v = band_rms(w[0], lo, hi, uvpc)
                    if np.isfinite(v) and v > 0:
                        out[i].append(v)
        except Exception:
            pass
        t += NOISE_LEN
    return [float(np.median(v)) if len(v) >= 3 else float("nan") for v in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="analysis/data")
    ap.add_argument("--harvest", default="analysis/event_harvest.csv")
    ap.add_argument("--gain", type=float, default=64.0)
    ap.add_argument("--min-snr", type=float, default=4.0,
                    help="SNR threshold an event must clear to inform the trend")
    ap.add_argument("--select", choices=("wide", "max"), default="wide",
                    help="'wide' selects on the INCUMBENT 1-15 Hz band -- unbiased with "
                         "respect to which narrow band wins. 'max' selects on the best "
                         "of all bands and is CIRCULAR: it keeps events that happen to "
                         "spike in some narrow band, which is what the comparison is "
                         "trying to measure. Kept only to show the size of the effect.")
    args = ap.parse_args()

    uvpc = 2.5 * 2 / (args.gain * (2 ** 23 - 1)) * 1e6
    archive = load_archive(args.data)
    rows = [r for r in csv.DictReader(open(args.harvest)) if r.get("seen") == "1"]
    print(f"{len(rows)} catches; scanning {len(BANK)} bands each\n")

    ev, nul = [], []
    for r in rows:
        o = obspy.UTCDateTime(r["origin"])
        d = datetime.fromisoformat(r["origin"].replace("Z", "+00:00")).astimezone(timezone.utc)
        path = archive.get((d.year, d.timetuple().tm_yday))
        if path is None:
            continue
        tp, ts = float(r["tp_s"]), float(r["ts_s"])
        try:
            st = obspy.read(path, starttime=o + PRE_SPAN[0] - 5, endtime=o + ts + 40)
            st.merge(method=1, fill_value="interpolate")
            sig = st.slice(o + tp - 2, o + ts + 22)
            if not len(sig) or sig[0].stats.npts < 512:
                continue
        except Exception:
            continue
        fs = float(sig[0].stats.sampling_rate)
        rel = (np.arange(sig[0].stats.npts) / fs) + (sig[0].stats.starttime - o)
        mask = (((rel >= tp - 2) & (rel <= tp + 12)) | ((rel >= ts - 4) & (rel <= ts + 22)))
        if mask.sum() < 512:
            continue
        nl = noise_levels(st, o, uvpc, BANK)
        snr = []
        for i, (lo, hi) in enumerate(BANK):
            pk = band_peak(sig[0], lo, hi, uvpc, smooth_s=1.0, mask=mask)
            snr.append(pk / nl[i] if np.isfinite(nl[i]) and nl[i] > 0 else np.nan)
        snr = np.array(snr)

        # CONTROL: the identical statistic on a pure-noise window of the same shape,
        # so the argmax-of-many-bands bias is visible rather than assumed away.
        try:
            nw = st.slice(o - 200, o - 200 + (ts + 24 - tp + 2))
            if len(nw) and nw[0].stats.npts >= sig[0].stats.npts:
                nm = np.zeros(nw[0].stats.npts, bool)
                nm[:mask.sum()] = True
                nsnr = [band_peak(nw[0], lo, hi, uvpc, 1.0, nm) / nl[i]
                        if np.isfinite(nl[i]) and nl[i] > 0 else np.nan
                        for i, (lo, hi) in enumerate(BANK)]
                nul.append(np.array(nsnr))
        except Exception:
            pass
        ev.append((float(r["dist_km"]), float(r["mag"]), snr, r["origin"]))

    # Selection must not depend on the quantity under test. Measured, because the
    # difference is not small: selecting on max-across-bands at threshold 8 made the
    # 3-7 Hz band look 1.51x better than the incumbent, while selecting on the incumbent
    # itself is the honest comparison. Both are runnable; only 'wide' is quotable.
    good = [e for e in ev if (np.nanmax(e[2][:WIDE]) if args.select == "max"
                              else e[2][WIDE]) >= args.min_snr]
    print(f"{len(ev)} scanned, {len(good)} clear enough (max SNR >= {args.min_snr}) "
          f"to inform the trend; {len(nul)} noise controls\n")

    cen = np.array([np.sqrt(lo * hi) for lo, hi in BANK])
    print(f"{'band Hz':>12}  {'median SNR':>10}  {'won':>5}  {'won on NOISE':>13}")
    wins = np.zeros(len(BANK)); nwins = np.zeros(len(BANK))
    for _, _, s, _ in good:
        wins[int(np.nanargmax(s[:WIDE]))] += 1
    for s in nul:
        if np.any(np.isfinite(s[:WIDE])):
            nwins[int(np.nanargmax(s[:WIDE]))] += 1
    for i, (lo, hi) in enumerate(BANK):
        med = np.nanmedian([e[2][i] for e in good])
        tag = "  <- incumbent" if i == WIDE else ""
        w = f"{int(wins[i]):5d}" if i < WIDE else "    -"
        nw_ = f"{100*nwins[i]/max(1,len(nul)):12.0f}%" if i < WIDE else "            -"
        print(f"{lo:5.1f}-{hi:<5.1f} {med:11.2f}  {w}  {nw_}{tag}")

    dists = np.array([e[0] for e in good])
    best = np.array([cen[int(np.nanargmax(e[2][:WIDE]))] for e in good])
    gain = np.array([np.nanmax(e[2][:WIDE]) / e[2][WIDE] for e in good])
    print(f"\nbest-band centre vs distance: "
          f"<50 km median {np.median(best[dists<50]):.1f} Hz (n={int((dists<50).sum())}), "
          f"50-150 km {np.median(best[(dists>=50)&(dists<150)]):.1f} Hz "
          f"(n={int(((dists>=50)&(dists<150)).sum())}), "
          f">150 km {np.median(best[dists>=150]):.1f} Hz "
          f"(n={int((dists>=150).sum())})")
    if len(nul):
        nbest = np.array([cen[int(np.nanargmax(s[:WIDE]))] for s in nul
                          if np.any(np.isfinite(s[:WIDE]))])
        print(f"  NOISE control, same statistic: median best band "
              f"{np.median(nbest):.1f} Hz -- if the event medians look like this, the "
              f"'trend' is the argmax bias, not physics")
    print(f"  median SNR gain from best-of-10 over the incumbent 1-15 Hz: "
          f"{np.median(gain):.2f}x  (inflated by argmax over 10 bands -- see docstring)")

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 5), gridspec_kw={"width_ratios": [1.4, 1]})
    sc = ax[0].scatter(dists, best, c=[e[1] for e in good], cmap="viridis",
                       s=42, edgecolor="k", linewidth=0.4)
    ax[0].set_xscale("log"); ax[0].set_yscale("log")
    ax[0].set_xlabel("hypocentral distance (km)"); ax[0].set_ylabel("best band centre (Hz)")
    ax[0].grid(alpha=0.3, which="both")
    if len(nul):
        ax[0].axhline(np.median(nbest), color="#c62828", ls="--", lw=1.2,
                      label=f"noise control, {np.median(nbest):.1f} Hz")
        ax[0].legend(fontsize=8.5)
    plt.colorbar(sc, ax=ax[0], label="magnitude")
    ax[0].set_title("A.  Where the signal actually is", loc="left", weight="bold", fontsize=11)
    for lab, m in (("<50 km", dists < 50), ("50-150 km", (dists >= 50) & (dists < 150)),
                   (">150 km", dists >= 150)):
        if m.sum() >= 3:
            ax[1].plot(cen[:WIDE], np.nanmedian([e[2][:WIDE] for e, k in zip(good, m) if k],
                                                axis=0), "o-", label=f"{lab} (n={int(m.sum())})")
    ax[1].set_xscale("log"); ax[1].set_yscale("log")
    ax[1].set_xlabel("band centre (Hz)"); ax[1].set_ylabel("median SNR")
    ax[1].grid(alpha=0.3, which="both"); ax[1].legend(fontsize=8.5)
    ax[1].set_title("B.  Median SNR spectrum by distance", loc="left", weight="bold", fontsize=11)
    fig.suptitle("Does the detection band need to move with distance?", weight="bold", y=1.0)
    fig.tight_layout()
    os.makedirs("reports", exist_ok=True)
    fig.savefig("reports/band-vs-distance.png", dpi=140, bbox_inches="tight")
    print("\nwrote reports/band-vs-distance.png")


if __name__ == "__main__":
    main()
