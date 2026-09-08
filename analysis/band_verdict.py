#!/usr/bin/env python3
"""band_verdict.py -- at a MATCHED false-positive rate, does a narrower band detect more?

Reads analysis/data/band_scan.csv (built by band_detect.py: every catalogue event scored
in 11 bands, plus 4 same-shape null draws per event from its own pre-origin noise).

The whole point is the matched operating point. A narrower band raises the signal's SNR
AND the noise distribution's tail; comparing raw SNR between bands compares two
different thresholds and always flatters the narrow one. So each band gets its threshold
set at a chosen percentile of ITS OWN null, and only then are detections counted.

`sustain` is required alongside SNR, as harvest_events.py has always done and as
catch_audit.py showed is the guard that actually works -- a lull inflates a ratio, but
nothing except a wavetrain lasts.
"""
import argparse
import csv
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from band_scan import BANK, WIDE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="analysis/data/band_scan.csv")
    ap.add_argument("--fpr", type=float, default=1.0, help="false-positive rate, percent")
    ap.add_argument("--sustain", type=float, default=2.0)
    ap.add_argument("--curve", action="store_true",
                    help="sweep the threshold and plot detections vs measured FPR")
    ap.add_argument("--split", default="",
                    help="ISO date: pick the best band on events BEFORE it, then report "
                         "that band's performance on events AFTER it. The band was "
                         "chosen as best-of-10 on the same data everywhere else, which "
                         "is an argmax that has to be paid for.")
    args = ap.parse_args()

    ev, nl = [], []
    for r in csv.DictReader(open(args.csv)):
        f = lambda k: float(r[k]) if r[k] not in ("", None) else np.nan
        rec = (float(r["dist_km"]), float(r["mag"]),
               np.array([f(f"snr_{i}") for i in range(len(BANK))]),
               np.array([f(f"sus_{i}") for i in range(len(BANK))]), r["seen"],
               r["origin"])
        (ev if r["kind"] == "event" else nl).append(rec)
    print(f"{len(ev)} events, {len(nl)} null draws, {len(BANK)} bands")
    print(f"threshold per band = {100-args.fpr:.0f}th pct of that band's OWN null, "
          f"AND sustain >= {args.sustain} s\n")

    if args.curve:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8.2, 5.6))
        for i, style in ((WIDE, dict(color="#555", ls="--", lw=2)),
                         (5, dict(color="#c62828", lw=2.4)),
                         (4, dict(color="#1f77b4", lw=1.2, alpha=0.8)),
                         (6, dict(color="#2e7d32", lw=1.2, alpha=0.8))):
            lo, hi = BANK[i]
            xs, ys = [], []
            for q in np.linspace(97.0, 99.98, 60):
                t = np.percentile([n[2][i] for n in nl if np.isfinite(n[2][i])], q)
                f = sum(1 for n in nl if np.isfinite(n[2][i]) and n[2][i] >= t
                        and n[3][i] >= args.sustain) / max(1, len(nl))
                d = sum(1 for e in ev if np.isfinite(e[2][i]) and e[2][i] >= t
                        and e[3][i] >= args.sustain)
                # chance-corrected: at rate f, this many of the catalogue passes anyway
                xs.append(100 * f); ys.append(d - f * len(ev))
            ax.plot(xs, ys, label=f"{lo}-{hi} Hz" + (" (incumbent)" if i == WIDE else ""),
                    **style)
        ax.set_xlabel("measured false-positive rate (%), from same-shape noise windows")
        ax.set_ylabel("detections in excess of chance")
        ax.grid(alpha=0.3); ax.legend()
        ax.set_title("Detection trade-off: the band is worth more than the threshold",
                     loc="left", weight="bold")
        fig.text(0.5, -0.02, f"{len(ev)} catalogue events, {len(nl)} null draws. "
                 "Counts corrected for chance: at rate f, f x N of the catalogue passes "
                 "with no signal present.", ha="center", fontsize=8.5, color="#444")
        import os; os.makedirs("reports", exist_ok=True)
        fig.savefig("reports/band-verdict.png", dpi=140, bbox_inches="tight")
        print("wrote reports/band-verdict.png")
        return

    thr = []
    for i in range(len(BANK)):
        v = np.array([n[2][i] for n in nl if np.isfinite(n[2][i])
                      and n[3][i] >= args.sustain])
        allv = np.array([n[2][i] for n in nl if np.isfinite(n[2][i])])
        # percentile taken over ALL null draws, then the sustain gate applied on top:
        # gating first would silently lower the FPR and inflate the detection count.
        thr.append(np.percentile(allv, 100 - args.fpr) if len(allv) else np.inf)

    print(f"{'band Hz':>12} {'thresh':>7} {'measured FPR':>13} {'detections':>11} "
          f"{'of which >50 km':>16} {'max km':>8}")
    res = []
    for i, (lo, hi) in enumerate(BANK):
        fp = sum(1 for n in nl if np.isfinite(n[2][i]) and n[2][i] >= thr[i]
                 and n[3][i] >= args.sustain)
        det = [e for e in ev if np.isfinite(e[2][i]) and e[2][i] >= thr[i]
               and e[3][i] >= args.sustain]
        far = sum(1 for e in det if e[0] > 50)
        mx = max((e[0] for e in det), default=0.0)
        tag = "  <- incumbent" if i == WIDE else ""
        print(f"{lo:5.1f}-{hi:<5.1f} {thr[i]:8.2f} {100*fp/max(1,len(nl)):12.2f}% "
              f"{len(det):11d} {far:16d} {mx:8.1f}{tag}")
        res.append((len(det), far, mx, i))

    if args.split:
        tr = [e for e in ev if e[5] < args.split]
        te = [e for e in ev if e[5] >= args.split]
        ntr = [n for n in nl if n[5] < args.split]
        nte = [n for n in nl if n[5] >= args.split]
        def count(sub, nsub, i, t):
            d = sum(1 for e in sub if np.isfinite(e[2][i]) and e[2][i] >= t
                    and e[3][i] >= args.sustain)
            f = sum(1 for n in nsub if np.isfinite(n[2][i]) and n[2][i] >= t
                    and n[3][i] >= args.sustain)
            return d, 100 * f / max(1, len(nsub))
        # threshold refit on the TRAIN nulls only, so nothing from the test half leaks
        thr_tr = [np.percentile([n[2][i] for n in ntr if np.isfinite(n[2][i])],
                                100 - args.fpr) if ntr else np.inf
                  for i in range(len(BANK))]
        pick = max(range(WIDE), key=lambda i: count(tr, ntr, i, thr_tr[i])[0])
        lo, hi = BANK[pick]
        dtr, ftr = count(tr, ntr, pick, thr_tr[pick])
        dte, fte = count(te, nte, pick, thr_tr[pick])
        itr, iftr = count(tr, ntr, WIDE, thr_tr[WIDE])
        ite, ifte = count(te, nte, WIDE, thr_tr[WIDE])
        print(f"\n  HELD-OUT (split {args.split}): {len(tr)} train events, {len(te)} test")
        print(f"    band chosen on TRAIN only: {lo}-{hi} Hz")
        print(f"    train: {lo}-{hi} {dtr} det @ {ftr:.2f}% FPR   vs incumbent {itr} "
              f"@ {iftr:.2f}%   ({dtr-itr:+d})")
        print(f"    TEST : {lo}-{hi} {dte} det @ {fte:.2f}% FPR   vs incumbent {ite} "
              f"@ {ifte:.2f}%   ({dte-ite:+d})")
        return

    best = max(res[:WIDE])
    inc = res[WIDE]
    print(f"\nincumbent 1-15 Hz: {inc[0]} detections, furthest {inc[2]:.1f} km")
    lo, hi = BANK[best[3]]
    print(f"best narrow band {lo}-{hi} Hz: {best[0]} detections, furthest {best[2]:.1f} km")
    # Chance-corrected: at a measured rate f, f x N catalogue events pass with nothing
    # there. Raw counts flatter whichever band sits at the higher operating point.
    fpr_b = sum(1 for n in nl if np.isfinite(n[2][best[3]]) and n[2][best[3]] >= thr[best[3]]
                and n[3][best[3]] >= args.sustain) / max(1, len(nl))
    fpr_i = sum(1 for n in nl if np.isfinite(n[2][WIDE]) and n[2][WIDE] >= thr[WIDE]
                and n[3][WIDE] >= args.sustain) / max(1, len(nl))
    xb, xi = best[0] - fpr_b * len(ev), inc[0] - fpr_i * len(ev)
    d = best[0] - inc[0]
    print(f"\n  DIFFERENCE: {d:+d} detections ({100*d/max(1,inc[0]):+.1f}%)")
    print(f"  CHANCE-CORRECTED: {xb:.0f} vs {xi:.0f} real detections above the "
          f"{100*fpr_b:.2f}% / {100*fpr_i:.2f}% expected -> {xb/max(xi,1e-9):.2f}x")
    if best[2] > inc[2] + 0.5:
        print(f"  REACH: {inc[2]:.1f} -> {best[2]:.1f} km")
    else:
        print(f"  REACH: unchanged ({inc[2]:.1f} km)")


if __name__ == "__main__":
    main()
