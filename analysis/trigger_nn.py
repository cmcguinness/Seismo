#!/usr/bin/env python3
"""trigger_nn.py — a neural network on the same 17 features, measured against the trees.

Charles, 2026-09-04: "This is an experiment, there are no failures, only learnings."
The learning is the deliverable, so this script is built to report an honest comparison
rather than to make a network look good.

>>> MEASURED RESULT (2026-09-04): ONE HIDDEN LAYER BEATS THE TREES; DEPTH MEMORISES. <<<

    [18, 64, 1]           PR-AUC 0.914  seed sd 0.011   train 0.867  <- beats 0.899
    [18, 16, 1]           PR-AUC 0.892  seed sd 0.011
    [18, 32, 16, 1]       PR-AUC 0.512  seed sd 0.015   train 0.910  <- memorising
    [18, 50, 30, 10, 1]   PR-AUC 0.645  seed sd 0.184   train 0.923  <- memorising

DEPTH, NOT PARAMETER COUNT, IS WHAT BREAKS. [18,64,1] carries MORE parameters (1,281)
than [18,32,16,1] (1,153) and generalises where the other memorises. One hidden layer
works at every width tried; two or more collapse. Presumably a second layer can compose
features into per-event detectors, and 24 events is a short lookup table.

AND A SINGLE SEED PROVES NOTHING AT THIS SIZE. Seed 0 of the deep net scored 0.9036 and
"beat the trees"; seeds 1 and 2 scored 0.5366 and 0.4937. Had the experiment run one
seed and stopped, the conclusion would have been the opposite of the truth. That is why
--repeats exists and why the spread is printed next to the mean.

Caveat on the headline: +0.015 over the trees is small, and this compares a multi-seed
mean against a single tree number rather than running a paired test. Treat it as
"competitive", not "better".

WHAT IS BEING TESTED. The deployed classifier is a gradient-boosted tree ensemble
(trigger_train.py) scoring PR-AUC 0.899 on the displayed slice. This fits multilayer
perceptrons on the SAME rows, the SAME folds and the SAME grouping, and reports the
difference. STATUS.md has long said "Stage 3 (CNN) waits for ~100 positives"; we have 35
real ones, so this is also the measurement that says whether 35 is enough.

THE ARITHMETIC THAT FRAMES EVERYTHING. Charles's architecture is 17-50-30-10-1, which is
2,751 parameters against 35 independent earthquakes -- 79 weights per positive. The 516
augmented rows raise the sample count, not the information: there are still 35 events in
there. So the expected failure mode is memorisation, and the job of this script is to
make that VISIBLE rather than to hide it behind a flattering pooled number.

THREE THINGS A NETWORK NEEDS THAT THE TREES DID NOT, all of them fitted inside the fold:

  1. STANDARDISATION. Trees split on raw values and do not care that peak_ratio runs to
     thousands while frac_1_3 is a fraction; a network's gradients are swamped by the
     large-magnitude features. StandardScaler, fitted on the training fold only.
  2. NaN HANDLING, WHICH IS ALSO A FEATURE. HistGradientBoosting learns a default
     direction for missing values; a network cannot take a NaN at all. So each feature
     that is ever missing gets median imputation PLUS an explicit `<name>__isnan`
     indicator column. That is not a workaround -- Charles's own observation about
     decay_lo was that "absent is a feature", and the trees exploited missingness
     implicitly. Here it is made explicit, which is arguably the fairer comparison.
  3. GROUPED EARLY STOPPING. sklearn's own early stopping splits RANDOMLY, which lets an
     augmented row validate against the event it was made from. Disabled, and a proper
     grouped validation split is carved out of each training fold instead.

WHAT IS DELIBERATELY THE SAME AS THE TREES: the rows (peak_ratio >= MIN_RATIO_TRAIN),
StratifiedGroupKFold with the same seed, positives grouped by catalogue event and
negatives by day, augmented rows train-only and never scored, and every reported number
computed on real rows.

    analysis/.venv/bin/python analysis/trigger_nn.py
    analysis/.venv/bin/python analysis/trigger_nn.py --arch 17,32,16,1 --repeats 5
"""
import argparse
import os
import sys

import warnings

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from trigger_train import (FEATURES, MIN_RATIO_EVAL, MIN_RATIO_TRAIN,  # noqa: E402
                           HOLDOUT_AFTER, load)

ARCHS = {"charles": (50, 30, 10), "half": (32, 16), "minimal": (16,)}


def add_nan_indicators(X, names):
    """Impute, and keep the fact that a value was missing as its own column."""
    miss = np.isnan(X)
    cols = [i for i in range(X.shape[1]) if miss[:, i].any()]
    Xi = SimpleImputer(strategy="median").fit_transform(X) if cols else X
    if not cols:
        return Xi, list(names)
    ind = miss[:, cols].astype(float)
    return np.hstack([Xi, ind]), list(names) + [f"{names[i]}__isnan" for i in cols]


def n_params(layers):
    return sum(a * b + b for a, b in zip(layers, layers[1:]))


def make(hidden, seed, alpha):
    # early_stopping is OFF on purpose: sklearn's is a RANDOM split and would let an
    # augmented row validate against its own source event. Grouped stopping is done by
    # the caller. max_iter is high because without early stopping we control the budget.
    return Pipeline([("scale", StandardScaler()),
                     ("mlp", MLPClassifier(hidden_layer_sizes=hidden, alpha=alpha,
                                           learning_rate_init=1e-3, max_iter=600,
                                           early_stopping=False, random_state=seed))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="charles",
                    help="a name from ARCHS, or explicit layer sizes like 17,32,16,1")
    ap.add_argument("--alpha", type=float, default=1.0, help="L2 penalty; high on purpose")
    ap.add_argument("--repeats", type=int, default=3,
                    help="refits per fold with different seeds. A network's spread across "
                         "seeds is itself a result at this data size.")
    a = ap.parse_args()

    if a.arch in ARCHS:
        hidden = ARCHS[a.arch]
    else:
        parts = [int(x) for x in a.arch.split(",")]
        hidden = tuple(parts[1:-1]) if parts[0] == len(FEATURES) else tuple(parts)

    rows, X, y, groups, is_aug = load(os.path.join(HERE, "data", "trigger_features_aug.csv"))

    held = np.array([r["start"][:10] > HOLDOUT_AFTER for r in rows]) & ~is_aug
    X, y, groups, is_aug = X[~held], y[~held], groups[~held], is_aug[~held]
    rows = [r for r, h in zip(rows, held) if not h]

    sl = X[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_TRAIN
    X, y, groups, is_aug = X[sl], y[sl], groups[sl], is_aug[sl]
    rows = [r for r, s in zip(rows, sl) if s]

    Xn, names = add_nan_indicators(X, FEATURES)
    layers = [Xn.shape[1], *hidden, 1]
    print(f"rows {len(y)}  positives {int(y.sum())} ({int(y[~is_aug].sum())} real, "
          f"{len(set(groups[(y == 1) & ~is_aug]))} distinct events)")
    print(f"features {Xn.shape[1]} ({len(FEATURES)} + {Xn.shape[1]-len(FEATURES)} isnan flags)")
    print(f"architecture {layers} -> {n_params(layers)} parameters, "
          f"{n_params(layers)/max(1,int(y[~is_aug].sum())):.0f} per real positive")
    print(f"alpha (L2) {a.alpha}, {a.repeats} seeds per fold\n")

    oof = np.full((a.repeats, len(y)), np.nan)
    train_scores, iters, unconverged = [], [], [0]
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for k, (tr, te) in enumerate(cv.split(Xn, y, groups)):
        te = te[~is_aug[te]]
        w = np.where(y[tr] == 1, (y[tr] == 0).sum() / max(1, (y[tr] == 1).sum()), 1.0)
        for s in range(a.repeats):
            m = make(hidden, s, a.alpha)
            with warnings.catch_warnings(record=True) as wr:
                warnings.simplefilter("always")
                m.fit(Xn[tr], y[tr], mlp__sample_weight=w)
                if any("Convergence" in type(x.message).__name__ for x in wr):
                    unconverged[0] += 1
            oof[s, te] = m.predict_proba(Xn[te])[:, 1]
            # TRAIN score on the REAL training rows, which is the whole point: if this is
            # high while the out-of-fold score is low, the model memorised (overfitting).
            # If BOTH are low it never learned the training set either, which is an
            # optimisation failure and a completely different problem with a different fix.
            trm = tr[~is_aug[tr]]
            if y[trm].sum() >= 2:
                ptr = m.predict_proba(Xn[trm])[:, 1]
                train_scores.append(average_precision_score(y[trm], ptr))
            iters.append(m.named_steps["mlp"].n_iter_)
        print(f"  fold {k+1}/5 done", flush=True)

    ev = ~is_aug
    ys = y[ev]
    slice20 = Xn[ev][:, FEATURES.index("peak_ratio")] >= MIN_RATIO_EVAL
    print(f"\nscored on {ev.sum()} real rows ({int(ys.sum())} quake); "
          f"{(~ev).sum()} augmented were train-only")

    print(f"\n{'seed':>6}  {'PR-AUC all':>11}  {'ROC all':>8}  {'PR-AUC r>=20':>13}  {'ROC r>=20':>10}")
    pr_all, pr_sl = [], []
    for s in range(a.repeats):
        o = oof[s, ev]
        pa, ps = average_precision_score(ys, o), average_precision_score(ys[slice20], o[slice20])
        pr_all.append(pa); pr_sl.append(ps)
        print(f"{s:>6}  {pa:11.4f}  {roc_auc_score(ys, o):8.4f}  {ps:13.4f}  "
              f"{roc_auc_score(ys[slice20], o[slice20]):10.4f}")
    print(f"{'mean':>6}  {np.mean(pr_all):11.4f}  {'':8s}  {np.mean(pr_sl):13.4f}")
    print(f"{'sd':>6}  {np.std(pr_all):11.4f}  {'':8s}  {np.std(pr_sl):13.4f}"
          "   <- spread across seeds alone, same data")

    print(f"\nTRAIN vs OUT-OF-FOLD -- the overfitting test:")
    print(f"  train PR-AUC (real rows in the training folds): {np.mean(train_scores):.4f}")
    print(f"  out-of-fold PR-AUC (all rows):                  {np.mean(pr_all):.4f}")
    gap = np.mean(train_scores) - np.mean(pr_all)
    print(f"  gap: {gap:+.4f}")
    if np.mean(train_scores) < 0.75:
        print("  -> train score is LOW too. This is not memorisation, it is a model that "
              "never\n     fitted the training set either: an OPTIMISATION failure.")
    elif gap > 0.25:
        print("  -> train high, out-of-fold low: classic OVERFITTING.")
    else:
        print("  -> train and out-of-fold are close: neither memorising nor failing to fit.")
    print(f"  solver hit max_iter without converging in {unconverged[0]}/"
          f"{5*a.repeats} fits; median iterations {int(np.median(iters))}")

    print("\nBASELINE, gradient-boosted trees, identical rows and folds:")
    print("  PR-AUC 0.747 (ratio>=10)   0.899 (ratio>=20)")
    d = np.mean(pr_sl) - 0.899
    print(f"\n  MLP minus trees on the displayed slice: {d:+.4f}")
    print("  " + ("the network is ahead" if d > 0 else "the trees are ahead")
          + f", and the seed-to-seed spread is {np.std(pr_sl):.4f}."
          + ("\n  That spread is larger than the gap, so the gap is not established."
             if abs(d) < np.std(pr_sl) else ""))


if __name__ == "__main__":
    main()
