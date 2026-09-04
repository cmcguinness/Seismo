#!/usr/bin/env python3
"""trigger_train.py — fit and judge the trigger classifier (Stage 1: gradient boosting).

Reads analysis/data/trigger_features.csv (trigger_dataset.py). Fits a
HistGradientBoostingClassifier with class weighting, evaluated by GROUPED
cross-validation -- positives grouped by catalog event (so an aftershock cannot vouch
for its mainshock), negatives grouped by day -- and compares it with the rule the
station uses today: hf_lf < 1.4 means "seismic". Prints PR-AUC, the precision/recall
trade-off, the permutation importances, and the triggers where the model and the rule
disagree most (the useful by-product). Then refits on everything and saves
analysis/models/trigger_gbm.joblib with its feature list, for the pi5 detector.

    python analysis/trigger_train.py
"""
import argparse
import csv
import datetime
import os

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "data", "trigger_features.csv")
OUT = os.path.join(HERE, "models", "trigger_gbm.joblib")
CULTURAL_HF_LF = 1.4

# Amplitude-RELATIVE features only: peak_uv / noise_uv / rms_uv / peak_env_uv straddle the
# 2026-08-07 front-end rebuild (an amplitude epoch in epochs.py) and would teach the model
# the hardware's history instead of the ground's. Ratios and shapes survive the rebuild.
FEATURES = ["peak_ratio", "duration_s", "hf_lf",
            "frac_1_3", "frac_3_8", "frac_8_15", "frac_15_30", "frac_30_45",
            "hf_lf_win", "centroid_hz", "dom_hz", "snr_env",
            "rise_s", "decay_s", "dur3_s", "kurtosis", "peak_pos_s"]
# The front-end fault (STATUS 2026-07-31 16:41 PDT -> fixed 08-03): 180 s triggers at
# millivolts that are neither cultural nor seismic. Not training data.
EXCLUDE = [("2026-07-31T23:00", "2026-08-03T12:00")]
MIN_RATIO_EVAL = 20.0      # the Detections page's display floor -- the slice that matters
# The DEPLOYED model is trained on triggers with peak_ratio >= MIN_RATIO_TRAIN only. Below
# that the log is ~20,000 near-threshold blips a month with a handful of M1.3-1.8 quakes
# hiding in them, and a model trained on that mass learns the blips (PR-AUC 0.06). Trained
# on the displayed range it learns quakes (PR-AUC 0.65 at >=10, 0.91 at >=20; 2026-08-26).
# The detector scores only triggers at/above this floor; others get no p_quake.
MIN_RATIO_TRAIN = 10.0

# HELD-OUT SET, frozen 2026-08-30. Every model to date has seen every row in the archive,
# so no evaluation here can claim to be out-of-sample in the strict sense -- the grouped CV
# is honest about leakage between folds but not about the many times these same rows have
# informed a choice of feature, threshold or filter. From this date forward, triggers are
# reserved: never fitted, only scored. It costs nothing today (there is no data after it
# yet) and it is the one thing that cannot be arranged retroactively -- you cannot un-see
# data. Move this date forward ONLY by deliberately promoting the holdout into training and
# choosing a new one; never to make a number look better.
HOLDOUT_AFTER = "2026-08-31"


def load(aug_csv=None):
    """Real rows, plus optionally augmented positives from augment.py.

    Augmented rows are TRAIN-ONLY -- see the aug handling in main(). They inherit their
    source event's `origin`, which is what positives are grouped on, so every derivative
    of one earthquake lands in the same CV fold automatically. Without that, near-copies
    would straddle the split and the score would climb for no reason at all.
    """
    rows = [r for r in csv.DictReader(open(CSV))
            if not any(a <= r["start"][:16] <= b for a, b in EXCLUDE)]
    for r in rows:
        r.setdefault("is_aug", "0")
    if aug_csv and os.path.exists(aug_csv):
        extra = [r for r in csv.DictReader(open(aug_csv))
                 if not any(a <= r["start"][:16] <= b for a, b in EXCLUDE)]
        rows += extra
        print(f"loaded {len(extra)} augmented positives from {os.path.basename(aug_csv)}")
    X = np.array([[float(r[f]) if r[f] not in ("", "None") else np.nan for f in FEATURES] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    groups = np.array([r["origin"] if r["label"] == "1" else r["start"][:10] for r in rows])
    is_aug = np.array([str(r.get("is_aug", "0")) == "1" for r in rows])
    return rows, X, y, groups, is_aug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aug", nargs="?", const=os.path.join(HERE, "data",
                    "trigger_features_aug.csv"), default=None,
                    help="also train on augmented positives from augment.py")
    args = ap.parse_args()
    rows, X, y, groups, is_aug = load(args.aug)
    print(f"{len(y)} triggers, {y.sum()} quake, {len(y) - y.sum()} cultural, "
          f"{len(set(groups[y == 1]))} distinct catalog events")

    # --- baseline: the station's rule ---------------------------------------------
    hf = X[:, FEATURES.index("hf_lf")]
    rule = (hf < CULTURAL_HF_LF).astype(int)
    has = ~np.isnan(hf)
    tp = int(((rule == 1) & (y == 1) & has).sum()); fp = int(((rule == 1) & (y == 0) & has).sum())
    fn = int(((rule == 0) & (y == 1) & has).sum())
    print(f"\nRULE hf_lf<{CULTURAL_HF_LF} (on {has.sum()} triggers with hf_lf): "
          f"precision {tp/(tp+fp+1e-9):.3f}  recall {tp/(tp+fn+1e-9):.3f}  "
          f"({tp} TP, {fp} FP, {fn} FN)")

    # Reserve the holdout: fitted on nothing after HOLDOUT_AFTER.
    held = np.array([r["start"][:10] > HOLDOUT_AFTER for r in rows]) & ~is_aug
    X_held = y_held = None
    if held.any():
        X_all_held, y_all_held = X[held], y[held]
        print(f"\nHELD OUT (never fitted): {held.sum()} triggers after {HOLDOUT_AFTER}, "
              f"{int(y[held].sum())} of them quake")
        X, y, groups, rows = X[~held], y[~held], groups[~held], [r for r, h in zip(rows, held) if not h]
        is_aug = is_aug[~held]
        # rule/has are built above from the FULL table, so they have to be trimmed here
        # too or the `rule[ev]` further down indexes a 36,704-long array with a
        # 32,367-long mask. This branch had never executed before 2026-09-04: the
        # holdout was chosen on 08-30 with no data after it yet, so the first run that
        # actually held anything out was the first run to touch these two lines.
        rule, has = rule[~held], has[~held]
        X_held, y_held = X_all_held, y_all_held
    else:
        print(f"\nholdout after {HOLDOUT_AFTER}: empty so far (it starts accruing tomorrow)")

    # --- grouped CV ------------------------------------------------------------------
    w = np.where(y == 1, (y == 0).sum() / max(1, (y == 1).sum()), 1.0)
    oof = np.zeros(len(y))
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for k, (tr, te) in enumerate(cv.split(X, y, groups)):
        # Augmented rows train, never test. A PR-AUC that counted synthetic positives
        # would be scoring the augmentation, not the classifier -- and since every
        # augmented row is a positive, it would only ever flatter the number.
        te = te[~is_aug[te]]
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                           l2_regularization=1.0, min_samples_leaf=20, random_state=k)
        m.fit(X[tr], y[tr], sample_weight=w[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    # every metric below is computed on REAL rows only, but the FULL arrays are kept
    # so the deployable model further down can still train on the augmented positives
    ev = ~is_aug
    Xa, ya, ga, auga = X, y, groups, is_aug
    X, y, groups, oof = X[ev], y[ev], groups[ev], oof[ev]
    rows = [r for r, e in zip(rows, ev) if e]
    rule, has = rule[ev], has[ev]
    print(f"\nevaluating on {ev.sum()} real rows ({int(y.sum())} quake); "
          f"{(~ev).sum()} augmented rows were train-only")
    print(f"GBM out-of-fold: PR-AUC {average_precision_score(y, oof):.3f}  ROC-AUC {roc_auc_score(y, oof):.3f}")
    pr, rc, th = precision_recall_curve(y, oof)
    print("  threshold  precision  recall  #flagged")
    for t in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        pred = oof >= t
        tpk = int((pred & (y == 1)).sum()); fpk = int((pred & (y == 0)).sum())
        print(f"    {t:4.1f}      {tpk/(tpk+fpk+1e-9):6.3f}    {tpk/y.sum():5.2f}   {int(pred.sum())}")

    # --- the slice that is actually shown: peak_ratio >= MIN_RATIO_EVAL ---------------
    pr_ = X[:, FEATURES.index("peak_ratio")]
    sl = pr_ >= MIN_RATIO_EVAL
    print(f"\nDISPLAYED SLICE (peak_ratio >= {MIN_RATIO_EVAL:g}): {sl.sum()} triggers, {int(y[sl].sum())} quake")
    tp = int(((rule == 1) & (y == 1) & has & sl).sum()); fp = int(((rule == 1) & (y == 0) & has & sl).sum())
    fn = int(((rule == 0) & (y == 1) & has & sl).sum())
    print(f"  RULE on slice: precision {tp/(tp+fp+1e-9):.3f} recall {tp/(tp+fn+1e-9):.3f} ({tp} TP, {fp} FP, {fn} FN)")
    print(f"  GBM  on slice: PR-AUC {average_precision_score(y[sl], oof[sl]):.3f}  ROC-AUC {roc_auc_score(y[sl], oof[sl]):.3f}")
    print("  threshold  precision  recall  #flagged (slice)")
    for t in (0.3, 0.5, 0.6, 0.7, 0.8):
        pred = (oof >= t) & sl
        tpk = int((pred & (y == 1)).sum()); fpk = int((pred & (y == 0)).sum())
        print(f"    {t:4.1f}      {tpk/(tpk+fpk+1e-9):6.3f}    {tpk/max(1,y[sl].sum()):5.2f}   {int(pred.sum())}")

    # --- the quakes the model missed, and the cultural triggers it liked ------------
    print("\nquake triggers ranked by out-of-fold p_quake (low = missed):")
    for i in np.argsort(oof)[::1]:
        if y[i] == 1:
            r = rows[i]
            print(f"  p={oof[i]:.2f}  {r['start'][:19]}  M{r['mag']} {r['place'][:26]:26s} {float(r['dist']):5.1f} km  hf_lf={r['hf_lf']} ratio={r['peak_ratio']}")
    print("\ntop cultural-labelled triggers by p_quake (candidates for a catalog miss, or the model's blind spot):")
    for i in np.argsort(-oof)[:12]:
        if y[i] == 0:
            r = rows[i]
            print(f"  p={oof[i]:.2f}  {r['start'][:19]}  hf_lf={r['hf_lf']} ratio={r['peak_ratio']} dur={r['duration_s']} peak={r['peak_uv']}uV hour={r['hour_local']}")

    # --- the deployable model: trained on the displayed range only -------------------
    st = Xa[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_TRAIN
    Xs, ys, gs, augs = Xa[st], ya[st], ga[st], auga[st]
    ws = np.where(ys == 1, (ys == 0).sum() / max(1, (ys == 1).sum()), 1.0)
    mk = lambda seed: HistGradientBoostingClassifier(max_depth=2, learning_rate=0.05, max_iter=200,
                                                     l2_regularization=2.0, min_samples_leaf=15,
                                                     random_state=seed)
    oofs = np.zeros(len(ys))
    for k, (tr, te) in enumerate(StratifiedGroupKFold(n_splits=min(5, int(ys.sum())), shuffle=True,
                                                      random_state=0).split(Xs, ys, gs)):
        te = te[~augs[te]]          # augmented rows train, never score
        m = mk(k); m.fit(Xs[tr], ys[tr], sample_weight=ws[tr]); oofs[te] = m.predict_proba(Xs[te])[:, 1]
    # Metrics on the REAL rows of the slice; the model TRAINS on the full slice.
    #
    # Those are two different sets and they need two different names. The block that
    # splits the main dataset above is careful about this -- it keeps Xa/ya/ga/auga so
    # the deployable model can still see the augmented positives -- and this block used
    # to narrow Xs/ys in place instead, which broke both halves at once: `ws` was still
    # the full length, so final.fit() died with a shape error (2026-09-04), and had it
    # not died it would have quietly trained the shipped model on REAL ROWS ONLY,
    # throwing away the 420 augmented positives that are the entire point of --aug.
    # The crash was the only thing standing between us and a silently worse model.
    rs = ~augs
    print(f"\nDEPLOYABLE MODEL (trained on peak_ratio >= {MIN_RATIO_TRAIN:g}: {len(ys)} triggers, "
          f"{int(ys.sum())} quake; {int(augs.sum())} of them augmented, train-only)")
    Xr, yr, oofr = Xs[rs], ys[rs], oofs[rs]          # real rows -> every number reported
    for name, m_ in (("ratio>=10", np.ones(len(yr), bool)), ("ratio>=20", Xr[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_EVAL)):
        print(f"  {name}: PR-AUC {average_precision_score(yr[m_], oofr[m_]):.3f}  ROC {roc_auc_score(yr[m_], oofr[m_]):.3f}")
        for t in (0.5, 0.7):
            pd_ = (oofr >= t) & m_
            tpk = int((pd_ & (yr == 1)).sum()); fpk = int((pd_ & (yr == 0)).sum())
            print(f"     p>={t}: precision {tpk/(tpk+fpk+1e-9):.2f} recall {tpk/max(1,yr[m_].sum()):.2f} flagged {int(pd_.sum())}")
    final = mk(0)
    final.fit(Xs, ys, sample_weight=ws)              # full slice: augmented rows included
    # Importance on REAL rows: measured over the augmented ones it would partly be
    # describing augment.py's noise, not the ground's.
    imp = permutation_importance(final, Xr, yr, scoring="average_precision", n_repeats=5, random_state=0)
    order = np.argsort(-imp.importances_mean)
    # THE HOLDOUT, SCORED. Reserving rows and never looking at them is not a holdout, it
    # is just deleting data -- and until 2026-09-04 this block had nothing to score, so
    # the omission was invisible. These rows were never in any fold and never fitted, so
    # this is the only number here that is out-of-sample in the strict sense. It is also
    # tiny: with a handful of quakes it moves by a whole event, so read it as a smoke
    # test that nothing is catastrophically wrong, not as a performance figure.
    if X_held is not None and len(y_held):
        hs = X_held[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_TRAIN
        if hs.sum() and y_held[hs].sum():
            ph = final.predict_proba(X_held[hs])[:, 1]
            yh = y_held[hs]
            flagged = int((ph >= 0.7).sum())
            tp = int(((ph >= 0.7) & (yh == 1)).sum())
            print(f"\nHOLDOUT (never fitted, never in a fold): {int(hs.sum())} triggers at "
                  f"ratio >= {MIN_RATIO_TRAIN:g}, {int(yh.sum())} quake")
            print(f"  PR-AUC {average_precision_score(yh, ph):.3f}  "
                  f"ROC {roc_auc_score(yh, ph):.3f}")
            print(f"  p>=0.7: caught {tp}/{int(yh.sum())}, flagged {flagged} "
                  f"({flagged - tp} false)")
        else:
            print(f"\nHOLDOUT: {int(hs.sum())} triggers at ratio >= {MIN_RATIO_TRAIN:g} "
                  f"but no quake among them -- nothing to score yet")

    print("\npermutation importance (PR-AUC drop):")
    for i in order[:10]:
        print(f"  {FEATURES[i]:14s} {imp.importances_mean[i]:+.3f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "min_ratio": MIN_RATIO_TRAIN,
                 # n_pos counts what it TRAINED on, which includes augmented rows;
                 # n_pos_real is how many independent earthquakes are actually behind
                 # them. A reader who saw only the first number would badly overestimate
                 # how much this model has seen.
                 "n_train": int(len(ys)), "n_pos": int(ys.sum()),
                 "n_pos_real": int(yr.sum()),
                 # Stamped, not hardcoded: this string is what the pi5 detector
                 # prints at startup, so a stale literal makes a fresh model look
                 # like the old one in the log.
                 "trained": datetime.date.today().isoformat(),
                 "note": "Stage-1 trigger classifier; p_quake advisory, threshold 0.5 suggested"}, OUT)
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()
