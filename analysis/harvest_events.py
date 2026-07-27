#!/usr/bin/env python3
"""harvest_events.py — build a labelled event set from the USGS catalog + our archive.

The point: we do not have to DETECT catalogued earthquakes to learn from them. The
catalog gives origin time and location, so we can cut the archive at the predicted
arrival and measure what is there — including events far below the STA/LTA threshold.
Non-detections are data too: they are what defines the detection curve.

Produces one row per catalogued event that our archive covers, with:
  - ground truth from the catalog: magnitude, hypocentral distance, depth
  - measured band energy (1-5 / 5-15 / 15-45 Hz) in the event window and in a
    pre-event noise window, and the excess ratio of each
  - snr, and `seen` (did the excess clear a threshold)
  - `triggered` — did the STA/LTA actually fire near the predicted arrival
  - the low/high band-excess ratio, which is the distance proxy we want to tune

EPOCH MATTERS. This station changed sample rate and front end repeatedly (see
STATUS.md); rows carry `fs` and `epoch` so a fit can be restricted to comparable data.
Mixing epochs in a regression would be measuring the hardware, not the ground.

Usage:
    harvest_events.py --days 30 --radius 300 --out analysis/event_harvest.csv
    harvest_events.py --start 2026-07-19 --end 2026-07-28
"""
import argparse
import csv
import glob
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

STA_LAT, STA_LON = 38.451817, -122.621049
VP, VS = 6.0, 3.5                      # km/s, crude crustal model for arrival prediction
BANDS = [("lo", 1.0, 5.0), ("mid", 5.0, 15.0), ("hi", 15.0, 45.0)]
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Acquisition epochs — a fit must not straddle these. (start_iso, label, nominal fs)
EPOCHS = [
    ("2026-07-25T23:39:00Z", "100sps", 100),
    ("2026-07-24T02:15:00Z", "60sps-post-jumper", 60),
    ("2026-07-23T08:56:00Z", "60sps-rdatac", 60),
    ("1970-01-01T00:00:00Z", "pre-rdatac", 57),
]


def epoch_of(iso):
    for start, label, fs in EPOCHS:
        if iso >= start:
            return label, fs
    return "unknown", 0


# Amplitude prediction anchor: the first confirmed quake (M2.5 @ 18.4 km, ~126 uV peak
# 1-15 Hz). Everything is scaled from it via the California ML attenuation, so `resid`
# below is "how much louder/quieter than that anchor predicts" -- which is where an
# azimuth-dependent PATH effect would show up as a systematic offset per direction.
REF_MAG, REF_DIST_KM, REF_PEAK_UV = 2.5, 18.4, 126.0
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def ml_atten(r):
    """California ML distance term, -log A0."""
    return 1.11 * math.log10(r) + 0.00189 * r + 0.591


def predict_uv(mag, dist):
    """Peak 1-15 Hz in uV this station would see, scaled from the anchor event."""
    return REF_PEAK_UV * 10 ** ((mag - REF_MAG) - (ml_atten(dist) - ml_atten(REF_DIST_KM)))


def back_azimuth(lat, lon):
    """Bearing from the STATION to the event, degrees clockwise from north.

    This is the direction the energy arrives FROM, so it is the axis to bin by when
    testing whether path geology (e.g. the Napa-Sonoma marshes to the SE vs Coast Range
    basement to the N) systematically changes what reaches us.
    """
    p1, p2 = math.radians(STA_LAT), math.radians(lat)
    dl = math.radians(lon - STA_LON)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def hypo_km(lat, lon, depth):
    dlat = (lat - STA_LAT) * 111.32
    dlon = (lon - STA_LON) * 111.32 * math.cos(math.radians((lat + STA_LAT) / 2))
    return math.hypot(math.hypot(dlat, dlon), depth or 0.0)


def fetch(start, end, radius, minmag):
    q = urllib.parse.urlencode({
        "format": "geojson", "starttime": start, "endtime": end,
        "latitude": STA_LAT, "longitude": STA_LON,
        "maxradiuskm": radius, "minmagnitude": minmag, "orderby": "time"})
    with urllib.request.urlopen(f"{USGS}?{q}", timeout=60) as r:
        return json.load(r)["features"]


def band_rms(tr, lo, hi, uvpc):
    w = tr.copy()
    if w.stats.npts < 64:
        return float("nan")
    w.detrend("demean")
    nyq = w.stats.sampling_rate / 2
    w.filter("bandpass", freqmin=lo, freqmax=min(hi, nyq * 0.98),
             corners=4, zerophase=True)
    x = np.asarray(w.data, float) * uvpc
    return float(np.sqrt(np.mean(x * x)))


def band_peak(tr, lo, hi, uvpc, smooth_s=1.0):
    """Peak of the smoothed |signal| envelope in a band -- the detection number."""
    w = tr.copy()
    if w.stats.npts < 64:
        return float("nan")
    w.detrend("demean")
    nyq = w.stats.sampling_rate / 2
    w.filter("bandpass", freqmin=lo, freqmax=min(hi, nyq * 0.98),
             corners=4, zerophase=True)
    x = np.abs(np.asarray(w.data, float) * uvpc)
    n = max(1, int(smooth_s * w.stats.sampling_rate))
    return float(np.convolve(x, np.ones(n) / n, mode="same").max())


def load_archive(data_dir):
    """{(year, julday): path} for every day-file we can see."""
    out = {}
    # Also match suffixed epoch files (…206.mseed.60sps-epoch). Matching only
    # "*.mseed" silently dropped the whole of day 206 -- which is the day of the
    # station's FIRST confirmed earthquake. A coverage gap that hides your best
    # events is worse than no harvest at all.
    for p in glob.glob(os.path.join(data_dir, "*.mseed")) + \
             glob.glob(os.path.join(data_dir, "*.mseed.*-epoch")):
        b = os.path.basename(p).split(".")
        i = b.index("mseed") if "mseed" in b else len(b)
        try:
            key = (int(b[i - 2]), int(b[i - 1]))
        except (ValueError, IndexError):
            continue
        # prefer the file that actually covers more of the day (bigger one)
        if key not in out or os.path.getsize(p) > os.path.getsize(out[key]):
            out[key] = p
    return out


def load_triggers(path):
    """events.log start-times as epoch seconds, for the `triggered` column."""
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    out.append(datetime.fromisoformat(e["start"]).timestamp())
                except Exception:
                    pass
    except OSError:
        pass
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--radius", type=float, default=300.0, help="km from the station")
    ap.add_argument("--minmag", type=float, default=0.0)
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--events", default=os.path.join(os.path.dirname(__file__), "events.log"),
                    help="events.log for the `triggered` column (optional)")
    ap.add_argument("--gain", type=int, default=64)
    ap.add_argument("--snr-seen", type=float, default=5.0,
                    help="peak 1-15 Hz excess counted as 'seen'. Default 5.0 is the "
                         "MEASURED 99th percentile of the null -- 3.0 was the 95th, "
                         "i.e. a threshold that fires on 5%% of empty windows.")
    ap.add_argument("--controls", type=int, default=200,
                    help="random no-event windows, to calibrate the FP rate")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "event_harvest.csv"))
    args = ap.parse_args()

    import obspy
    from obspy import UTCDateTime

    end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = args.start or (datetime.now(timezone.utc)
                           - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"USGS: events within {args.radius:g} km, {start} .. {end}", flush=True)
    feats = fetch(start, end, args.radius, args.minmag)
    print(f"  {len(feats)} catalogued", flush=True)

    archive = load_archive(args.data)
    print(f"  archive day-files: {len(archive)}", flush=True)
    trigs = load_triggers(args.events)
    uvpc = 2.5 * 2 / (args.gain * (2 ** 23 - 1)) * 1e6

    rows, covered, cache = [], 0, {}
    for ft in feats:
        p, c = ft["properties"], ft["geometry"]["coordinates"]
        if p.get("mag") is None:
            continue
        o = UTCDateTime(p["time"] / 1000.0)
        key = (o.year, o.julday)
        path = archive.get(key)
        if path is None:
            continue
        dist = hypo_km(c[1], c[0], c[2])
        tp, ts = dist / VP, dist / VS
        # Windows: noise well before origin, signal from just before P through the coda.
        # 30 s of signal covers P+S+coda out to ~300 km without running into the next event.
        try:
            # Read ONLY the window. Caching whole day-files and .copy()ing per event
            # cost ~2 s each -- 14 minutes of CPU for 367 events, because every copy
            # duplicates a 26 MB trace to use 2 minutes of it. Same lesson as
            # heli_build: decode the span you need, not the file it lives in.
            st = obspy.read(path, starttime=o - 95, endtime=o + tp + 35)
            if not len(st):
                continue
            st.merge(method=1, fill_value="interpolate")
            pre = st.slice(o - 90, o - 15)
            sig = st.slice(o + tp - 2, o + tp + 30)
        except Exception as e:
            print(f"  skip {o}: {e}", flush=True)
            continue
        if not len(pre) or not len(sig) or pre[0].stats.npts < 1024 or sig[0].stats.npts < 512:
            continue
        covered += 1
        fs = float(sig[0].stats.sampling_rate)
        m = {}
        for name, lo, hi in BANDS:
            n = band_rms(pre[0], lo, hi, uvpc)
            s = band_rms(sig[0], lo, hi, uvpc)
            m[f"pre_{name}"], m[f"sig_{name}"] = n, s
            m[f"r_{name}"] = s / n if n and np.isfinite(n) and n > 0 else float("nan")
        # 1-15 Hz combined excess = the "did we see it" number
        pre15 = band_rms(pre[0], 1.0, 15.0, uvpc)
        sig15 = band_rms(sig[0], 1.0, 15.0, uvpc)
        # PEAK-based SNR is the detection number. RMS over the whole 32 s signal
        # window dilutes a ~10 s burst by ~2x and made an M1.2 at 18 km score 1.33.
        peak15 = band_peak(sig[0], 1.0, 15.0, uvpc, smooth_s=1.0)
        snr = peak15 / pre15 if pre15 > 0 else float("nan")
        snr_rms = sig15 / pre15 if pre15 > 0 else float("nan")
        lohi = (m["r_lo"] / m["r_hi"]
                if m["r_hi"] and np.isfinite(m["r_hi"]) and m["r_hi"] > 0 else float("nan"))
        az = back_azimuth(c[1], c[0])
        pred = predict_uv(float(p["mag"]), dist)
        # Residual is ONLY meaningful for events actually seen -- for the rest it is an
        # upper limit, since `peak15` is then just noise.
        resid = (math.log10(peak15 / pred) if pred > 0 and peak15 > 0 else float("nan"))
        iso = o.strftime("%Y-%m-%dT%H:%M:%SZ")
        ep, _ = epoch_of(iso)
        # did the STA/LTA fire within the signal window?
        lo_t, hi_t = (o + tp - 3).timestamp, (o + tp + 30).timestamp
        triggered = any(lo_t <= t <= hi_t for t in trigs)
        rows.append({
            "origin": iso, "mag": round(float(p["mag"]), 2),
            "place": p.get("place", ""), "dist_km": round(dist, 1),
            "depth_km": round(float(c[2] or 0), 1), "fs": fs, "epoch": ep,
            "pre_1_15": round(pre15, 3), "sig_1_15": round(sig15, 3),
            "snr": round(snr, 2), "snr_rms": round(snr_rms, 2),
            "peak_1_15": round(peak15, 3),
            "az_deg": round(az, 1), "az": COMPASS[int((az + 11.25) % 360 // 22.5)],
            "pred_uv": round(pred, 3),
            "resid_log10": round(resid, 3) if np.isfinite(resid) else "", "seen": int(snr >= args.snr_seen),
            "triggered": int(triggered),
            **{k: round(v, 3) for k, v in m.items() if np.isfinite(v)},
            "lo_hi": round(lohi, 3) if np.isfinite(lohi) else "",
        })

    if not rows:
        sys.exit("no catalogued events fell inside the archive")
    cols = list(rows[0].keys())
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    seen = [r for r in rows if r["seen"]]
    trig = [r for r in rows if r["triggered"]]
    print(f"\n{covered} catalogued events fall inside the archive; wrote {args.out}")
    print(f"  seen (1-15 Hz excess >= {args.snr_seen:g}x): {len(seen)}")
    print(f"  STA/LTA actually triggered:                 {len(trig)}")
    if seen:
        print(f"\n  {'origin':22s} {'M':>4} {'dist':>7} {'snr':>6} {'lo/hi':>6}  seen/trig")
        for r in sorted(seen, key=lambda r: -r["snr"])[:15]:
            print(f"  {r['origin']:22s} {r['mag']:4.1f} {r['dist_km']:6.1f}k "
                  f"{r['snr']:6.1f} {str(r['lo_hi']):>6}   {r['seen']}/{r['triggered']}")
    # NULL DISTRIBUTION. Without it a threshold is a guess: with 265 windows sampled,
    # some will contain a passing truck, and "M0.6 at 249 km, SNR 5.1" is not a
    # detection -- it is the base rate showing through. Measure the same statistic at
    # random times so the threshold can be set where real events beat chance.
    if args.controls:
        import random
        random.seed(0)
        spans = []
        for (yr, jd), pth in sorted(archive.items()):
            try:
                hdr = obspy.read(pth, headonly=True)
                spans.append((pth, min(t.stats.starttime for t in hdr),
                              max(t.stats.endtime for t in hdr)))
            except Exception:
                pass
        ctl = []
        tries = 0
        while len(ctl) < args.controls and tries < args.controls * 8:
            tries += 1
            pth, t0, t1 = random.choice(spans)
            if t1 - t0 < 300:
                continue
            o = t0 + random.uniform(120, float(t1 - t0) - 60)
            try:
                st = obspy.read(pth, starttime=o - 95, endtime=o + 35)
                st.merge(method=1, fill_value="interpolate")
                pre = st.slice(o - 90, o - 15)
                sig = st.slice(o - 2, o + 30)
                if not len(pre) or not len(sig):
                    continue
                pn = band_rms(pre[0], 1.0, 15.0, uvpc)
                pk = band_peak(sig[0], 1.0, 15.0, uvpc, smooth_s=1.0)
                if pn > 0 and np.isfinite(pk):
                    ctl.append(pk / pn)
            except Exception:
                continue
        if ctl:
            a = np.array(ctl)
            print(f"\n  NULL ({len(a)} random windows, no catalogued event):")
            for q in (50, 90, 95, 99):
                print(f"     p{q}: {np.percentile(a, q):5.2f}")
            print(f"     max: {a.max():5.2f}")
            thr = float(np.percentile(a, 99))
            real = [r for r in rows if r["snr"] > thr]
            print(f"\n  events beating the 99th-percentile null ({thr:.2f}):")
            for r in sorted(real, key=lambda r: -r["snr"]):
                print(f"     M{r['mag']:.1f}  {r['dist_km']:6.1f} km  snr {r['snr']:6.2f}"
                      f"  lo/hi {r['lo_hi']}   {r['place'][:34]}")

    # Azimuth summary -- the reason the column exists. Only SEEN events carry a
    # meaningful residual; the rest bound it from above.
    if seen:
        print("\n  SEEN events, observed vs predicted (residual >0 = louder than the")
        print("  anchor predicts). Bin these by azimuth once there are enough:")
        print(f"     {'origin':21s} {'M':>4} {'dist':>7} {'az':>6} {'pred':>8} {'obs':>8}  resid")
        for r in sorted(seen, key=lambda r: r["az_deg"]):
            print(f"     {r['origin']:21s} {r['mag']:4.1f} {r['dist_km']:6.1f}k "
                  f"{r['az']:>4}{r['az_deg']:5.0f} {r['pred_uv']:8.2f} {r['peak_1_15']:8.2f}"
                  f"  {r['resid_log10']:+}")
        import collections
        byaz = collections.defaultdict(list)
        for r in rows:
            byaz[r["az"]].append(r)
        print(f"\n  catalogue coverage by azimuth (all {len(rows)} windows):")
        for k in sorted(byaz, key=lambda k: -len(byaz[k]))[:8]:
            n_seen = sum(x["seen"] for x in byaz[k])
            print(f"     {k:>4}: {len(byaz[k]):4d} events, {n_seen} seen")

    ms = [r["mag"] for r in seen]
    if ms:
        print(f"\n  smallest SEEN: M{min(ms):.1f}   "
              f"largest MISSED: M{max([r['mag'] for r in rows if not r['seen']], default=0):.1f}")


if __name__ == "__main__":
    main()
