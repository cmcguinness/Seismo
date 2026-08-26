#!/usr/bin/env python3
"""trigger_dataset.py — every STA/LTA trigger as a feature row, labelled by the catalog.

Stage 1 of the trigger classifier (STATUS.md 2026-08-26, after Yeck et al. 2020): keep
STA/LTA as the detector, learn to *believe* its triggers less. This script builds the
training table; trigger_train.py fits and evaluates.

Rows:    one per trigger in the pi5 detector's events.log (the log the Detections page
         and the future deployment read), restricted to days with a local day-file.
Label:   1 (quake) if the trigger starts within [-3, +40] s of a CONFIRMED catalog
         event's predicted P arrival (origin + hypo/5.19 + 0.30 s; the same criteria as
         detection_map.calibrate: snr>=3, -1.2<resid<0.4, lo_hi>=1 in event_harvest.csv).
         0 (cultural) otherwise -- EXCEPT triggers within +-180 s of ANY catalog event the
         harvester marked `seen` (or of a confirmed event), which are dropped as
         ambiguous rather than mislabelled. The Cloverdale aftershock hours are therefore
         mostly excluded, on purpose.
Features (per trigger, window = start-5 s .. start+25 s of the 100 sps archive):
         the detector's own fields (peak_ratio, duration_s, peak_uv, hf_lf) plus
         waveform features the classifier can't get from the log: band-energy fractions
         (1-3 / 3-8 / 8-15 / 15-30 / 30-45 Hz of 1-45), hf/lf ratio recomputed, spectral
         centroid and dominant frequency in 1-30 Hz, pre-window noise RMS, peak/noise,
         envelope rise time (onset -> peak) and decay time (peak -> 1/e), duration above
         3x noise, kurtosis, and the peak's position in the window.
Output:  analysis/data/trigger_features.csv

    python analysis/trigger_dataset.py [--events analysis/data/events.pi5.log]
"""
import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import obspy
from obspy import UTCDateTime
from scipy import signal, stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
STA_LAT, STA_LON = 38.451817, -122.621049
VP, T0_INT = 5.19, 0.30
PRE, POST = 5.0, 25.0              # window around the trigger start, seconds
BANDS = [(1, 3), (3, 8), (8, 15), (15, 30), (30, 45)]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_catalog():
    """(confirmed arrivals, all 'seen' arrivals) as epoch seconds, from the harvest CSV."""
    conf, seen = [], []
    for r in csv.DictReader(open(os.path.join(HERE, "event_harvest.csv"))):
        if r["epoch"] != "100sps":
            continue
        t = UTCDateTime(r["origin"]).timestamp
        hypo = math.hypot(float(r["dist_km"]), float(r["depth_km"]))
        arr = t + hypo / VP + T0_INT
        rec = dict(arr=arr, mag=float(r["mag"]), dist=float(r["dist_km"]), place=r["place"], origin=r["origin"])
        ok = (float(r["snr"]) >= 3 and -1.2 < float(r["resid_log10"]) < 0.4 and float(r["lo_hi"]) >= 1)
        if ok:
            conf.append(rec)
        if ok or r["seen"] == "1":
            seen.append(rec)
    return conf, seen


def load_triggers(path):
    out = []
    with open(path) as fh:
        for line in fh:
            try:
                e = json.loads(line)
                t = dt.datetime.fromisoformat(e["start"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=dt.timezone.utc)
                e["t"] = t.timestamp()
                out.append(e)
            except Exception:
                pass
    return out


def features(x, fs, t_trig_idx):
    """Feature dict for one window (raw counts -> uV inside)."""
    x = x.astype(np.float64) * UV
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
    # envelope in the 1-15 Hz band, where a quake lives
    sos2 = signal.butter(4, [1, 15], btype="bandpass", fs=fs, output="sos")
    xq = signal.sosfiltfilt(sos2, x)
    env = np.abs(signal.hilbert(xq))
    env = np.convolve(env, np.ones(int(0.3 * fs)) / int(0.3 * fs), "same")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=os.path.join(DATA, "events.pi5.log"))
    ap.add_argument("--out", default=os.path.join(DATA, "trigger_features.csv"))
    ap.add_argument("--start", default="2026-07-25")
    a = ap.parse_args()

    conf, seen = load_catalog()
    conf_arr = np.array([c["arr"] for c in conf]); seen_arr = np.array([c["arr"] for c in seen])
    trig = [e for e in load_triggers(a.events) if e["t"] >= UTCDateTime(a.start).timestamp]
    print(f"{len(trig)} triggers since {a.start}; {len(conf)} confirmed catalog events, {len(seen)} seen")

    # group triggers by day-file
    by_day = {}
    for e in trig:
        d = dt.datetime.fromtimestamp(e["t"], dt.timezone.utc)
        by_day.setdefault((d.year, d.timetuple().tm_yday), []).append(e)

    rows, n_pos, n_amb = [], 0, 0
    for (y, j), evs in sorted(by_day.items()):
        path = os.path.join(DATA, f"XX.OAKMT.00.SHZ.D.{y}.{j:03d}.mseed")
        if not os.path.exists(path):
            continue
        st = obspy.read(path)
        st.merge(method=1, fill_value="interpolate")
        tr = st[0]
        fs = float(tr.stats.sampling_rate)
        for e in evs:
            t = e["t"]
            d_conf = conf_arr - t if conf_arr.size else np.array([])
            hit = np.where((d_conf >= -40) & (d_conf <= 3))[0]      # trigger 3 s before .. 40 s after arrival
            d_seen = np.abs(seen_arr - t) if seen_arr.size else np.array([])
            if hit.size:
                label = 1; n_pos += 1
                c = conf[int(hit[np.argmin(np.abs(d_conf[hit]))])]
                meta = dict(mag=c["mag"], dist=c["dist"], place=c["place"], origin=c["origin"])
            elif d_seen.size and d_seen.min() < 180:
                n_amb += 1
                continue                                             # ambiguous: drop
            else:
                label = 0; meta = dict(mag="", dist="", place="", origin="")
            w0 = UTCDateTime(t - PRE); w1 = UTCDateTime(t + POST)
            sub = tr.slice(w0, w1)
            if sub.stats.npts < int((PRE + POST) * fs * 0.9):
                continue
            fe = features(sub.data, fs, int(PRE * fs))
            row = dict(start=e["start"], label=label,
                       peak_ratio=e.get("peak_ratio", ""), duration_s=e.get("duration_s", ""),
                       peak_uv=e.get("peak_uv", ""), hf_lf=e.get("hf_lf", ""),
                       hour_local=(dt.datetime.fromtimestamp(t, dt.timezone.utc).hour - 7) % 24,
                       **meta, **fe)
            rows.append(row)
        print(f"  {y}.{j:03d}: {len(rows)} rows so far ({n_pos} quake, {n_amb} dropped as ambiguous)", flush=True)

    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {a.out}: {n_pos} quake, {len(rows) - n_pos} cultural, {n_amb} dropped")


if __name__ == "__main__":
    main()
