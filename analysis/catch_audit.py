#!/usr/bin/env python3
"""catch_audit.py -- re-decide every confirmed catch against a BRACKETING noise level.

WHY. Both detection verdicts in this repo measure a candidate arrival against the noise
in the stretch immediately BEFORE the origin, and cultural noise here is wildly
non-stationary. If that stretch happens to be a quiet lull, the ratio is inflated by the
lull rather than by an earthquake. That failure was caught in the wild on 2026-09-07:
`eventcheck.py` returned "AMBIGUOUS, p = 0.011" in four different bands for the M3.7
Hydesville at 252 km -- identical p in every band, because its null is drawn ONLY from
the 300 s before origin, and that afternoon those 300 s were the quietest run of the
whole record. Widened to +-15 minutes the arrival ranked 11th of 64 windows.

The harvest is built better and this audit expects most catches to survive: `seen`
requires snr >= 5 AND sustain >= 2 s, and a quiet lull can inflate snr but cannot
manufacture two seconds of sustained envelope. But `snr` still divides by a 75 s
pre-origin window (o-90 .. o-15), so the exposure is real and unquantified. This
measures it rather than assuming either way.

METHOD. Everything is reused verbatim from harvest_events.py -- same bands, same P and S
boxes, same peak/sustain helpers -- so the ONLY thing that changes is the noise
denominator:

  pre75      (what the harvest does):  RMS over o-90 .. o-15, one window
  pre-median (the clean fix):           MEDIAN of windows tiled across o-300 .. o-15
  bracketing (the strict fix):          MEDIAN of those PLUS o+ts+40 .. o+ts+300

THREE estimates, not two, because the strict one has a bias of its own: the post-coda
windows can catch the event's OWN coda, which raises the noise level and would drop a
real event for being too energetic. A big regional event's coda runs for minutes; the
40 s pad after S is not always enough.

So `pre-median` is the honest discriminator. It removes the lull artefact -- a single
quiet window can no longer set the denominator -- while being structurally incapable of
including any of the earthquake. Where `bracketing` drops an event that `pre-median`
keeps, the most likely explanation is that the event's own coda inflated the far side,
and the audit says so rather than counting it as a failure.

Windows overlapping a data gap are dropped, not interpolated.

Usage:  catch_audit.py [--data analysis/data] [--snr-seen 5.0] [--sustain-seen 2.0]
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

import numpy as np
import obspy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest_events import (arrivals_s, band_peak, band_rms, band_sustain,
                            epi_km, hypo_km, load_archive)

NOISE_LEN = 75.0          # same length as the harvest's pre window, so RMS is comparable
PRE_SPAN = (-300.0, -15.0)
POST_PAD = 40.0           # clear the S coda before sampling the far side
POST_SPAN = 300.0


def tile(lo, hi, length):
    """Non-overlapping window starts covering [lo, hi]."""
    out, t = [], lo
    while t + length <= hi:
        out.append(t)
        t += length
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="analysis/data")
    ap.add_argument("--harvest", default="analysis/event_harvest.csv")
    ap.add_argument("--gain", type=float, default=64.0)
    ap.add_argument("--snr-seen", type=float, default=5.0)
    ap.add_argument("--sustain-seen", type=float, default=2.0)
    args = ap.parse_args()

    uvpc = 2.5 * 2 / (args.gain * (2 ** 23 - 1)) * 1e6
    archive = load_archive(args.data)
    rows = [r for r in csv.DictReader(open(args.harvest)) if r.get("seen") == "1"]
    print(f"{len(rows)} catches marked seen=1 in the harvest\n")

    kept, lost, skipped = [], [], []
    for r in rows:
        o = obspy.UTCDateTime(r["origin"])
        d = datetime.fromisoformat(r["origin"].replace("Z", "+00:00")).astimezone(timezone.utc)
        path = archive.get((d.year, d.timetuple().tm_yday))
        if path is None:
            skipped.append((r, "no day-file")); continue
        lat, lon, dep = float(r["dist_km"]), None, float(r["depth_km"] or 0)
        # geometry comes back from the harvest columns; re-derive arrivals from distance
        dist = float(r["dist_km"])
        tp, ts = float(r["tp_s"]), float(r["ts_s"])
        try:
            st = obspy.read(path, starttime=o + PRE_SPAN[0] - 5,
                            endtime=o + ts + POST_PAD + POST_SPAN + 5)
            st.merge(method=1, fill_value="interpolate")
            if not len(st):
                skipped.append((r, "empty")); continue
            sig = st.slice(o + tp - 2, o + ts + 22)
            if not len(sig) or sig[0].stats.npts < 512:
                skipped.append((r, "short signal")); continue
        except Exception as e:
            skipped.append((r, str(e)[:40])); continue

        fs = float(sig[0].stats.sampling_rate)
        rel = (np.arange(sig[0].stats.npts) / fs) + (sig[0].stats.starttime - o)
        sigmask = (((rel >= tp - 2) & (rel <= tp + 12)) |
                   ((rel >= ts - 4) & (rel <= ts + 22)))
        if sigmask.sum() < 512:
            skipped.append((r, "mask too small")); continue

        peak15 = band_peak(sig[0], 1.0, 15.0, uvpc, smooth_s=1.0, mask=sigmask)
        sustain = band_sustain(sig[0], 1.0, 15.0, uvpc, 0.5 * peak15, mask=sigmask)

        starts = ([(s, s + NOISE_LEN) for s in tile(*PRE_SPAN, NOISE_LEN)] +
                  [(s, s + NOISE_LEN) for s in
                   tile(ts + POST_PAD, ts + POST_PAD + POST_SPAN, NOISE_LEN)])
        levels, pre_levels = [], []
        for a, b in starts:
            try:
                w = st.slice(o + a, o + b)
                if len(w) and w[0].stats.npts > 1024:
                    v = band_rms(w[0], 1.0, 15.0, uvpc)
                    if np.isfinite(v) and v > 0:
                        levels.append(v)
                        if b <= -15.0:
                            pre_levels.append(v)
            except Exception:
                pass
        if len(levels) < 4:
            skipped.append((r, f"only {len(levels)} noise windows")); continue

        # SELF-CHECK. Before any new noise level is trusted, reproduce the harvest's
        # own number with the harvest's own window. If peak15 or the boxes differ, every
        # comparison below is measuring my reimplementation, not the noise level.
        try:
            w = st.slice(o - 90, o - 15)
            n_h = band_rms(w[0], 1.0, 15.0, uvpc) if len(w) else float("nan")
        except Exception:
            n_h = float("nan")
        repro = peak15 / n_h if np.isfinite(n_h) and n_h > 0 else float("nan")

        n_brack = float(np.median(levels))
        n_pre = float(np.median(pre_levels)) if len(pre_levels) >= 2 else float("nan")
        snr_brack = peak15 / n_brack
        snr_pre = peak15 / n_pre if np.isfinite(n_pre) and n_pre > 0 else float("nan")
        snr_old = float(r["snr"])
        ok = lambda v: v >= args.snr_seen and sustain >= args.sustain_seen
        rec = dict(r=r, old=snr_old, repro=repro, pre=snr_pre, brack=snr_brack,
                   sustain=sustain,
                   n_pre75=float(r["pre_1_15"]), n_premed=n_pre, n_brack=n_brack,
                   nw=len(levels))
        (kept if ok(snr_pre) else lost).append(rec)

    print(f"{'origin':21s} {'M':>5} {'km':>6} | {'snr':>7} {'snr':>7} {'snr':>7} | "
          f"{'sust':>5} | {'noise uV: 1-window':>18} {'pre-med':>8} {'bracket':>8}")
    print(f"{'':21s} {'':>5} {'':>6} | {'harvest':>7} {'pre-med':>7} {'bracket':>7} |"
          f"{'':6} | {'(harvest)':>18}")
    for rec in sorted(kept + lost, key=lambda x: x["pre"]):
        r = rec["r"]
        v = "keeps" if rec in kept else "DROPS"
        flag = "  <- bracket disagrees" if (
            (rec["brack"] >= args.snr_seen) != (rec["pre"] >= args.snr_seen)) else ""
        print(f"{r['origin']:21s} {r['mag']:>5} {float(r['dist_km']):6.1f} | "
              f"{rec['old']:7.2f} {rec['pre']:7.2f} {rec['brack']:7.2f} | "
              f"{rec['sustain']:5.2f} | {rec['n_pre75']:18.2f} {rec['n_premed']:8.2f} "
              f"{rec['n_brack']:8.2f}  {v}{flag}")

    n = len(kept) + len(lost)
    rep = [(abs(rec["repro"] - rec["old"]) / rec["old"], rec) for rec in kept + lost
           if np.isfinite(rec["repro"]) and rec["old"] > 0]
    if rep:
        worst = max(rep, key=lambda x: x[0])
        med = float(np.median([x[0] for x in rep]))
        print(f"\n  SELF-CHECK, harvest's own window reproduced: median error "
              f"{med*100:.1f}%, worst {worst[0]*100:.1f}% "
              f"({worst[1]['r']['origin']}, stored {worst[1]['old']:.2f} vs "
              f"recomputed {worst[1]['repro']:.2f})")
        bad = [x for x in rep if x[0] > 0.15]
        print(f"  {len(bad)}/{len(rep)} differ by more than 15% -- those are NOT "
              f"auditable and are excluded from the counts below"
              if bad else "  every event reproduces within 15%")
        for x in bad:
            kept[:] = [k for k in kept if k is not x[1]]
            lost[:] = [l for l in lost if l is not x[1]]
    n = len(kept) + len(lost)
    print(f"\n  survive a MEDIAN pre-origin noise level: {len(kept)}/{n}")
    nb = sum(1 for rec in kept + lost if rec["brack"] >= args.snr_seen
             and rec["sustain"] >= args.sustain_seen)
    print(f"  survive the stricter BRACKETING level:   {nb}/{n}"
          "   (lower partly from coda self-contamination -- see the docstring)")
    if lost:
        print("\n  DROPPED by the median pre-origin level:")
        for rec in sorted(lost, key=lambda x: -x["pre"]):
            r = rec["r"]
            bad = ([] if rec["pre"] >= args.snr_seen else ["snr"]) + \
                  ([] if rec["sustain"] >= args.sustain_seen else ["sustain"])
            why = "+".join(bad)
            print(f"    {r['origin']}  M{r['mag']:>5} at {float(r['dist_km']):6.1f} km  "
                  f"snr {rec['old']:6.2f} -> {rec['pre']:5.2f}  [{why}]  "
                  f"the harvest's single window read {rec['n_pre75']:.2f} uV against a "
                  f"median of {rec['n_premed']:.2f} uV")
    if skipped:
        print(f"  not auditable ({len(skipped)}): "
              + ", ".join(f"{r['origin'][:10]} [{w}]" for r, w in skipped[:8])
              + (" ..." if len(skipped) > 8 else ""))


if __name__ == "__main__":
    main()
