#!/usr/bin/env python3
"""band_detect.py -- does a narrower band DETECT more, at a matched false-positive rate?

band_scan.py measured median SNR in each band over the events we already catch, and
found 3-7 Hz worth ~1.9x over the incumbent 1-15 Hz on strong events and nothing on
weak ones. That is not the detector question. A detector is judged by how many events it
finds at a FIXED false-alarm rate, and a narrower band raises SNR and the noise
distribution's tail together -- comparing raw SNR between bands silently compares two
different operating points.

So this sweeps the WHOLE catalogue, not just the catches, and for every event records:
  - peak SNR and sustain in each band, against the audited median pre-origin noise
  - the SAME statistic at NULL_PER_EVENT random offsets inside the pre-origin noise

The null draws are what make the comparison fair: each band gets its own threshold set
at a chosen percentile of its OWN null, so every band is scored at the same measured
false-positive rate. Only then does "detections" mean the same thing across bands.

Writes analysis/data/band_scan.csv (one row per event, plus null rows) so the analysis
is offline and cheap to redo. Streaming, so a long run can be inspected while it works.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

import numpy as np
import obspy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from band_scan import BANK, NOISE_LEN, PRE_SPAN, WIDE, noise_levels
from harvest_events import band_peak, band_sustain, load_archive

NULL_PER_EVENT = 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="analysis/data")
    ap.add_argument("--harvest", default="analysis/event_harvest.csv")
    ap.add_argument("--gain", type=float, default=64.0)
    ap.add_argument("--out", default="analysis/data/band_scan.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    uvpc = 2.5 * 2 / (args.gain * (2 ** 23 - 1)) * 1e6
    archive = load_archive(args.data)
    rows = list(csv.DictReader(open(args.harvest)))
    if args.limit:
        rows = rows[:args.limit]
    rng = np.random.default_rng(11)

    cols = (["origin", "mag", "dist_km", "kind", "seen"]
            + [f"snr_{i}" for i in range(len(BANK))]
            + [f"sus_{i}" for i in range(len(BANK))])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    fh = open(args.out, "w", newline="")
    w = csv.writer(fh)
    w.writerow(cols)

    done = 0
    for n, r in enumerate(rows):
        if n % 100 == 0:
            print(f"  {n}/{len(rows)}  ({done} usable)", flush=True)
            fh.flush()
        o = obspy.UTCDateTime(r["origin"])
        d = datetime.fromisoformat(r["origin"].replace("Z", "+00:00")).astimezone(timezone.utc)
        path = archive.get((d.year, d.timetuple().tm_yday))
        if path is None:
            continue
        try:
            tp, ts = float(r["tp_s"]), float(r["ts_s"])
        except (ValueError, KeyError):
            continue
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
        if not np.any(np.isfinite(nl)):
            continue

        def score(tr, m):
            s, u = [], []
            for i, (lo, hi) in enumerate(BANK):
                if not (np.isfinite(nl[i]) and nl[i] > 0):
                    s.append(""); u.append(""); continue
                pk = band_peak(tr, lo, hi, uvpc, smooth_s=1.0, mask=m)
                s.append(round(pk / nl[i], 3))
                u.append(round(band_sustain(tr, lo, hi, uvpc, 0.5 * pk, mask=m), 2))
            return s, u

        s, u = score(sig[0], mask)
        w.writerow([r["origin"], r["mag"], r["dist_km"], "event", r.get("seen", "")] + s + u)

        # NULL: same window shape, random offsets inside the pre-origin noise only.
        span = ts + 24 - tp + 2
        for _ in range(NULL_PER_EVENT):
            off = float(rng.uniform(PRE_SPAN[0] + 5, PRE_SPAN[1] - span - 5))
            try:
                nw = st.slice(o + off, o + off + span)
                if not len(nw) or nw[0].stats.npts < sig[0].stats.npts:
                    continue
                nm = np.zeros(nw[0].stats.npts, bool)
                nm[:int(mask.sum())] = True
                ns, nu = score(nw[0], nm)
                w.writerow([r["origin"], r["mag"], r["dist_km"], "null", ""] + ns + nu)
            except Exception:
                pass
        done += 1

    fh.close()
    print(f"done: {done} usable events -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
