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


def load():
    rows = [r for r in csv.DictReader(open(CSV))
            if not any(a <= r["start"][:16] <= b for a, b in EXCLUDE)]
    X = np.array([[float(r[f]) if r[f] not in ("", "None") else np.nan for f in FEATURES] for r in rows])
    y = np.array([int(r["label"]) for r in rows])
    groups = np.array([r["origin"] if r["label"] == "1" else r["start"][:10] for r in rows])
    return rows, X, y, groups


def main():
    rows, X, y, groups = load()
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

    # --- grouped CV ------------------------------------------------------------------
    w = np.where(y == 1, (y == 0).sum() / max(1, (y == 1).sum()), 1.0)
    oof = np.zeros(len(y))
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for k, (tr, te) in enumerate(cv.split(X, y, groups)):
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                           l2_regularization=1.0, min_samples_leaf=20, random_state=k)
        m.fit(X[tr], y[tr], sample_weight=w[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    print(f"\nGBM out-of-fold: PR-AUC {average_precision_score(y, oof):.3f}  ROC-AUC {roc_auc_score(y, oof):.3f}")
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
    st = pr_ >= MIN_RATIO_TRAIN
    Xs, ys, gs = X[st], y[st], groups[st]
    ws = np.where(ys == 1, (ys == 0).sum() / max(1, (ys == 1).sum()), 1.0)
    mk = lambda seed: HistGradientBoostingClassifier(max_depth=2, learning_rate=0.05, max_iter=200,
                                                     l2_regularization=2.0, min_samples_leaf=15,
                                                     random_state=seed)
    oofs = np.zeros(len(ys))
    for k, (tr, te) in enumerate(StratifiedGroupKFold(n_splits=min(5, int(ys.sum())), shuffle=True,
                                                      random_state=0).split(Xs, ys, gs)):
        m = mk(k); m.fit(Xs[tr], ys[tr], sample_weight=ws[tr]); oofs[te] = m.predict_proba(Xs[te])[:, 1]
    print(f"\nDEPLOYABLE MODEL (trained on peak_ratio >= {MIN_RATIO_TRAIN:g}: {len(ys)} triggers, {int(ys.sum())} quake)")
    for name, m_ in (("ratio>=10", np.ones(len(ys), bool)), ("ratio>=20", Xs[:, FEATURES.index("peak_ratio")] >= MIN_RATIO_EVAL)):
        print(f"  {name}: PR-AUC {average_precision_score(ys[m_], oofs[m_]):.3f}  ROC {roc_auc_score(ys[m_], oofs[m_]):.3f}")
        for t in (0.5, 0.7):
            pd_ = (oofs >= t) & m_
            tpk = int((pd_ & (ys == 1)).sum()); fpk = int((pd_ & (ys == 0)).sum())
            print(f"     p>={t}: precision {tpk/(tpk+fpk+1e-9):.2f} recall {tpk/max(1,ys[m_].sum()):.2f} flagged {int(pd_.sum())}")
    final = mk(0)
    final.fit(Xs, ys, sample_weight=ws)
    imp = permutation_importance(final, Xs, ys, scoring="average_precision", n_repeats=5, random_state=0)
    order = np.argsort(-imp.importances_mean)
    print("\npermutation importance (PR-AUC drop):")
    for i in order[:10]:
        print(f"  {FEATURES[i]:14s} {imp.importances_mean[i]:+.3f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "min_ratio": MIN_RATIO_TRAIN,
                 "n_train": int(len(ys)), "n_pos": int(ys.sum()),
                 # Stamped, not hardcoded: this string is what the pi5 detector
                 # prints at startup, so a stale literal makes a fresh model look
                 # like the old one in the log.
                 "trained": datetime.date.today().isoformat(),
                 "note": "Stage-1 trigger classifier; p_quake advisory, threshold 0.5 suggested"}, OUT)
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()
