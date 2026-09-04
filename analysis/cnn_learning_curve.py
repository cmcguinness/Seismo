#!/usr/bin/env python3
"""cnn_learning_curve.py — is the CNN data-limited, or is the approach wrong?

"Not enough data" is the most comfortable conclusion available to anyone whose model
just lost, and the least falsifiable. This turns it into a measurement.

Train the same network on a growing fraction of the EVENTS (never the rows: half the
rows of one earthquake is still one earthquake) and watch the out-of-fold score. If it
is still climbing at the full 27 events, more data will help and "data-limited" is a
finding. If it has flattened, more data of THIS KIND will not help THIS CONFIGURATION.

That second reading is narrower than it looks, and the distinction matters. A flat curve
is evidence about one architecture, one preprocessing chain, one set of hyperparameters
and one person's choices -- not about the approach. On 2026-09-04 this project produced
three results that looked like "does not work" and were somebody's bug: the CNN could not
learn until batches contained any earthquakes at all; pooling away the frequency axis
cost 27% of the score, and 80 parameters bought it back; and the first A/B verdict rule
compared a paired delta against a between-fold spread and would have discarded a real
effect. Each, stopped one step earlier, reads as proof of impossibility.

So: report what was measured, name the configuration it was measured on, and leave the
general claim alone. Failure is never proof of impossibility -- it is evidence about the
attempt.

Subsampling is by event for positives and by day for negatives, matching the grouping
the folds use. Negatives are held at full strength throughout so that only the positive
count varies -- otherwise the base rate moves under us and the scores stop comparing.

    analysis/.venv/bin/python analysis/cnn_learning_curve.py --data data/spec55.npz
"""
import argparse
import os

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
from trigger_cnn import fit_one, predict   # noqa: E402


def run(X, y, groups, seeds, epochs, lr, dropout, nfk, device):
    oof = np.full((seeds, len(y)), np.nan)
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for tr, te in cv.split(X, y, groups):
        pw = float((y[tr] == 0).sum() / max(1, (y[tr] == 1).sum()))
        for s in range(seeds):
            p, _ = fit_one(X[tr], y[tr], X[te], s, epochs, lr, pw, device, dropout,
                           8, 16, 0, nfk)
            oof[s, te] = p
    return [average_precision_score(y, oof[s]) for s in range(seeds)], \
           [roc_auc_score(y, oof[s]) for s in range(seeds)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data", "spec55.npz"))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--nfk", type=int, default=6)
    a = ap.parse_args()

    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    d = np.load(a.data, allow_pickle=True)
    X, y, groups = d["X"], d["y"], d["groups"]
    events = sorted(set(groups[y == 1]))
    print(f"{len(events)} distinct events, {int(y.sum())} positive rows, "
          f"{int((1-y).sum())} negatives held constant\n")

    rng = np.random.default_rng(0)
    print(f"{'events':>7}  {'pos rows':>9}  {'PR-AUC mean':>12}  {'sd':>7}  {'ROC':>7}")
    curve = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        k = max(2, int(round(frac * len(events))))
        keep_ev = set(rng.choice(events, k, replace=False)) if k < len(events) else set(events)
        m = (y == 0) | np.isin(groups, list(keep_ev))
        prs, rocs = run(X[m], y[m], groups[m], a.seeds, a.epochs, a.lr, a.dropout,
                        a.nfk, device)
        curve.append((k, np.mean(prs)))
        print(f"{k:>7}  {int(y[m].sum()):>9}  {np.mean(prs):12.4f}  {np.std(prs):7.4f}  "
              f"{np.mean(rocs):7.4f}", flush=True)

    print()
    (k0, p0), (k1, p1) = curve[-2], curve[-1]
    slope = (p1 - p0) / max(1, k1 - k0)
    print(f"slope over the last step: {slope:+.4f} PR-AUC per event")
    if slope > 0.004:
        print("  STILL CLIMBING -- the curve has not flattened, so the limit is DATA.")
        need = (0.899 - p1) / slope
        print(f"  at this rate, reaching the trees' 0.899 would take roughly "
              f"{need:.0f} more events ({k1 + need:.0f} total).")
        print("  That extrapolation is linear and almost certainly optimistic -- learning"
              "\n  curves bend. Treat it as a lower bound on what is needed.")
    else:
        print("  FLAT for THIS configuration. More data of this kind would not close"
              " the gap for\n  this architecture, preprocessing and hyperparameters --"
              " which is not a claim\n  about spectrogram CNNs. Not varied here, any of"
              " which could move it: window\n  length, bin spacing and count, augmentation"
              " (time jitter, noise burial),\n  deeper stacks with real regularisation,"
              " pretraining on the cultural rows,\n  transfer from a public catalogue, or a"
              " ranking loss.")


if __name__ == "__main__":
    main()
