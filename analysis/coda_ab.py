#!/usr/bin/env python3
"""coda_ab.py — do the coda candidates ADD anything the existing features do not?

Single-feature separation (coda_probe.py) cannot answer this. A candidate can look
excellent on its own and contribute nothing, because seventeen features already in the
model say the same thing in other words. `frac_1_3` carries the largest permutation
importance we have (+0.569) and `dur3_s` is third (+0.223); "low-frequency energy that
lasts" is arguably what a low-band decay rate measures too.

>>> MEASURED RESULT (2026-09-04): NOT ESTABLISHED. DO NOT ADD THE COLUMNS YET. <<<

  nine candidates: per-fold deltas -0.067 +0.240 +0.178 -0.261 -0.009  -> mean +0.016
  best two only:   per-fold deltas +0.044 +0.175 +0.221 -0.171 -0.058  -> mean +0.042

Pooled PR-AUC rises (0.4548 -> 0.5354 with all nine), which looks convincing and is not.
Pooling hides that two folds improved and two got worse by as much. The paired per-fold
view is the honest one, and it says the sign is not even stable.

So this does two things, in the order they are worth doing:

  1. CORRELATION. Each candidate against every existing feature. Cheap, and if the
     A/B below shows nothing this says WHERE the redundancy is rather than leaving it
     a mystery. Spearman rather than Pearson: we care whether they rank rows the same
     way, not whether the relationship is a straight line.

  2. THE A/B. Grouped cross-validation with the existing features, then the same folds
     with the candidates appended. Same seeds, same grouping (positives by catalog
     event so an aftershock cannot vouch for its mainshock, negatives by day), same
     everything -- only the columns change. The delta is the answer.

Read the delta with suspicion. With 33 positives grouped by event, one Geysers sequence
landing in a different fold moves PR-AUC by points on its own, so the per-fold spread is
reported next to the mean. An improvement smaller than that spread is not an improvement.

    analysis/.venv/bin/python analysis/coda_ab.py
"""
import csv
import os
import sys

import numpy as np
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_CSV = os.path.join(HERE, "data", "trigger_features.csv")
CAND_CSV = os.path.join(HERE, "data", "coda_candidates.csv")

sys.path.insert(0, HERE)
from trigger_train import FEATURES, MIN_RATIO_EVAL, MIN_RATIO_TRAIN   # noqa: E402


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of candidates to test. Nine new columns "
                         "against 33 positives is too many; naming a SMALL subset up front "
                         "is the sensible experiment. Choose it on stated grounds before "
                         "you look at the result, or you are just fishing.")
    a_ = ap.parse_args()
    cand = {r["start"]: r for r in csv.DictReader(open(CAND_CSV))}
    cand_cols = [c for c in next(iter(cand.values())) if c not in ("start", "label")]
    if a_.only:
        want = [c.strip() for c in a_.only.split(",")]
        missing = [c for c in want if c not in cand_cols]
        if missing:
            sys.exit(f"unknown candidate(s): {missing}")
        cand_cols = want

    rows = [r for r in csv.DictReader(open(BASE_CSV))
            if fnum(r.get("peak_ratio")) >= MIN_RATIO_TRAIN and r["start"] in cand]
    print(f"{len(rows)} rows joined on trigger start, {sum(int(r['label']) for r in rows)} quake")
    print(f"candidates: {', '.join(cand_cols)}\n")

    X0 = np.array([[fnum(r.get(f)) for f in FEATURES] for r in rows])
    XC = np.array([[fnum(cand[r["start"]].get(c)) for c in cand_cols] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    groups = np.array([r["origin"] if r["label"] == "1" else r["start"][:10] for r in rows])

    # ---- 1. where does each candidate already live in the existing feature set? ----
    print("SPEARMAN |rho| of each candidate against its closest existing features")
    print("(high = the model may already know this; computed on rows where both exist)\n")
    for j, c in enumerate(cand_cols):
        cor = []
        for i, f in enumerate(FEATURES):
            m = np.isfinite(XC[:, j]) & np.isfinite(X0[:, i])
            if m.sum() < 50:
                continue
            rho = spearmanr(XC[m, j], X0[m, i]).statistic
            if np.isfinite(rho):
                cor.append((abs(rho), f, rho))
        cor.sort(reverse=True)
        top = "   ".join(f"{f} {r:+.2f}" for _, f, r in cor[:4])
        print(f"  {c:22s} {top}")

    # ---- 2. does adding them move the number? ----
    def cv(X, tag):
        oof = np.full(len(y), np.nan)
        per_fold, fold_id = [], []
        cvs = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
        for k, (tr, te) in enumerate(cvs.split(X, y, groups)):
            m = HistGradientBoostingClassifier(max_depth=2, learning_rate=0.05, max_iter=200,
                                               l2_regularization=2.0, min_samples_leaf=15,
                                               random_state=k)
            w = np.where(y[tr] == 1, (y[tr] == 0).sum() / max(1, (y[tr] == 1).sum()), 1.0)
            m.fit(X[tr], y[tr], sample_weight=w)
            oof[te] = m.predict_proba(X[te])[:, 1]
            if y[te].sum() >= 2:
                per_fold.append(average_precision_score(y[te], oof[te]))
            fold_id.append((k, te))
        sl = X0[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_EVAL
        print(f"\n  {tag}")
        print(f"    all rows      PR-AUC {average_precision_score(y, oof):.4f}   "
              f"ROC {roc_auc_score(y, oof):.4f}")
        print(f"    ratio>=20     PR-AUC {average_precision_score(y[sl], oof[sl]):.4f}   "
              f"ROC {roc_auc_score(y[sl], oof[sl]):.4f}")
        print(f"    per-fold PR-AUC  mean {np.mean(per_fold):.4f}  sd {np.std(per_fold):.4f}  "
              f"({len(per_fold)} folds)")
        return average_precision_score(y, oof), np.std(per_fold), per_fold

    print("\n" + "=" * 78)
    a, sd_a, fa = cv(X0, f"WITHOUT candidates ({X0.shape[1]} features)")
    b, sd_b, fb = cv(np.hstack([X0, XC]), f"WITH candidates ({X0.shape[1] + XC.shape[1]} features)")
    print("\n" + "=" * 78)
    print(f"  pooled delta PR-AUC {b - a:+.4f}")

    # PAIRED, because both models saw the IDENTICAL folds. Comparing the delta against
    # the spread BETWEEN folds (which the first version of this script did) is far too
    # conservative: most of that spread is how hard each fold happens to be, and that
    # difficulty is common to both models and cancels in the difference. What matters is
    # whether the delta is consistently positive fold by fold.
    d = np.array(fb) - np.array(fa)
    print(f"\n  per-fold deltas: {'  '.join(f'{x:+.3f}' for x in d)}")
    print(f"  mean {d.mean():+.4f}  sd {d.std(ddof=1):.4f}  "
          f"positive in {int((d > 0).sum())}/{len(d)} folds")
    se = d.std(ddof=1) / np.sqrt(len(d))
    t = d.mean() / se if se > 0 else float("inf")
    print(f"  paired t = {t:.2f} on {len(d)-1} df")
    print("  " + ("CONSISTENT: positive in every fold." if (d > 0).all()
                  else "MIXED: the sign flips between folds, so this is not established."))
    print("\n  With 33 positives across 5 folds, treat any p-value as decoration --"
          "\n  the useful question is whether the sign is stable, not whether t clears 2.")


if __name__ == "__main__":
    main()
