#!/usr/bin/env python3
"""trigger_features.py — the ONE definition of a trigger's feature vector, and its scorer.

Shared by analysis/trigger_dataset.py (training, on the Mac) and server/detector.py
(scoring, on pi5) so the deployed model sees exactly the features it was trained on.
If you change anything here, retrain (analysis/trigger_train.py) and redeploy the model.

Window: PRE s before the trigger start to POST s after, at the archive rate. Features are
amplitude-RELATIVE (fractions, ratios, shapes) so they survive front-end changes; the
absolute-amplitude ones are computed too (the dataset keeps them for inspection) but
the model never uses them.
"""
import math

import numpy as np
from scipy import signal, stats

UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
PRE, POST = 5.0, 25.0
BANDS = [(1, 3), (3, 8), (8, 15), (15, 30), (30, 45)]


def features(x, fs, t_trig_idx):
    """Feature dict for one window of raw counts; t_trig_idx = index of the trigger start."""
    x = np.asarray(x, dtype=np.float64) * UV
    x = x - np.median(x)
    sos = signal.butter(4, [1, 45], btype="bandpass", fs=fs, output="sos")
    xb = signal.sosfiltfilt(sos, x)
    f, p = signal.welch(xb, fs=fs, nperseg=min(len(xb), int(4 * fs)), average="median")
    tot = np.trapezoid(p[(f >= 1) & (f < 45)], f[(f >= 1) & (f < 45)]) + 1e-30
    out = {}
    for lo, hi in BANDS:
        s = (f >= lo) & (f < hi)
        out[f"frac_{lo}_{hi}"] = float(np.trapezoid(p[s], f[s]) / tot)
    lf = np.trapezoid(p[(f >= 1) & (f < 8)], f[(f >= 1) & (f < 8)]) + 1e-30
    hf = np.trapezoid(p[(f >= 15) & (f < 45)], f[(f >= 15) & (f < 45)])
    out["hf_lf_win"] = float(np.sqrt(hf / lf))
    s = (f >= 1) & (f < 30)
    out["centroid_hz"] = float(np.sum(f[s] * p[s]) / (np.sum(p[s]) + 1e-30))
    out["dom_hz"] = float(f[s][np.argmax(p[s])])
    sos2 = signal.butter(4, [1, 15], btype="bandpass", fs=fs, output="sos")
    xq = signal.sosfiltfilt(sos2, x)
    env = np.abs(signal.hilbert(xq))
    k = max(1, int(0.3 * fs))
    env = np.convolve(env, np.ones(k) / k, "same")
    pre = env[: max(1, t_trig_idx - int(0.5 * fs))]
    noise = float(np.median(pre)) if pre.size else float(np.median(env))
    ipk = int(np.argmax(env))
    pk = float(env[ipk])
    out["noise_uv"] = noise
    out["peak_env_uv"] = pk
    out["snr_env"] = pk / (noise + 1e-9)
    out["rise_s"] = max(0.0, (ipk - t_trig_idx) / fs)
    above = env > pk / math.e
    j = ipk
    while j < len(env) and above[j]:
        j += 1
    out["decay_s"] = (j - ipk) / fs
    out["dur3_s"] = float(np.sum(env > 3 * noise) / fs)
    out["kurtosis"] = float(stats.kurtosis(xq))
    out["peak_pos_s"] = ipk / fs
    out["rms_uv"] = float(np.sqrt(np.mean(xq ** 2)))
    return out


class TriggerScorer:
    """Loads the joblib bundle from analysis/trigger_train.py and scores one event."""

    def __init__(self, path):
        import joblib
        b = joblib.load(path)
        self.model, self.features, self.min_ratio = b["model"], b["features"], float(b.get("min_ratio", 0))
        self.meta = {k: b[k] for k in ("trained", "n_train", "n_pos") if k in b}

    def score(self, ev, window_counts, fs):
        """p_quake for a detector event dict + its raw window, or None if below the
        model's ratio floor (the model was not trained there and must not guess)."""
        if float(ev.get("peak_ratio", 0) or 0) < self.min_ratio:
            return None
        fe = features(window_counts, fs, int(PRE * fs))
        fe.update({"peak_ratio": ev.get("peak_ratio"), "duration_s": ev.get("duration_s"),
                   "hf_lf": ev.get("hf_lf")})
        row = [float(fe[k]) if fe.get(k) not in (None, "") else float("nan") for k in self.features]
        return float(self.model.predict_proba(np.array([row]))[0, 1])
