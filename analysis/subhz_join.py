#!/usr/bin/env python3
"""Join the per-interval sub-Hz bands to the env node and ask the open question:
does pressure or tilt explain the 0.02-0.12 Hz undulation?"""
import csv
import datetime as dt
import glob
import os
import sys

import numpy as np
from scipy import stats

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
START = dt.datetime(2026, 8, 13, tzinfo=dt.timezone.utc).timestamp()   # clear of 08-12

seis = np.genfromtxt(os.path.join(S, "subhz.csv"), delimiter=",", names=True)
seis = seis[seis["t0"] >= START]

# --- env node: 1 Hz CSVs -> per-interval medians -------------------------------
et, temp, press, humid, ax, ay, az = [], [], [], [], [], [], []
for p in sorted(glob.glob(os.path.join(S, "env", "env-*.csv"))):
    with open(p) as fh:
        for row in csv.DictReader(fh):
            try:
                et.append(dt.datetime.fromisoformat(row["utc"]).timestamp())
                temp.append(float(row["temp_C"])); press.append(float(row["press_hPa"]))
                humid.append(float(row["humid_pct"]))
                ax.append(float(row["ax_ms2"])); ay.append(float(row["ay_ms2"]))
                az.append(float(row["az_ms2"]))
            except Exception:
                pass
et = np.array(et)
env = {k: np.array(v) for k, v in
       dict(temp=temp, press=press, humid=humid, ax=ax, ay=ay, az=az).items()}
# tilt magnitude off vertical, microradians -- the CLUE's accel is coarse, so this is
# a sanity channel more than a tiltmeter.
env["tilt"] = np.hypot(env["ax"], env["ay"]) / np.abs(env["az"]) * 1e6

order = np.argsort(et)
et = et[order]
env = {k: v[order] for k, v in env.items()}

cols = {}
for k, v in env.items():
    out = np.full(len(seis), np.nan)
    lo = np.searchsorted(et, seis["t0"])
    hi = np.searchsorted(et, seis["t0"] + 900)
    for i, (a, b) in enumerate(zip(lo, hi)):
        if b > a:
            out[i] = np.median(v[a:b])
    cols[k] = out

keep = np.isfinite(cols["temp"]) & np.isfinite(seis["lf"])
seis, cols = seis[keep], {k: v[keep] for k, v in cols.items()}
t = seis["t0"]
print(f"{len(t)} intervals, {(t[-1]-t[0])/86400:.1f} days "
      f"({dt.datetime.utcfromtimestamp(t[0]):%d %b} - {dt.datetime.utcfromtimestamp(t[-1]):%d %b} UTC)\n")

# --- the correlations ----------------------------------------------------------
def d_dt(x):
    return np.gradient(x, t / 3600.0)

drivers = {"temp": cols["temp"], "dTemp/dt": d_dt(cols["temp"]),
           "press": cols["press"], "dPress/dt": d_dt(cols["press"]),
           "humid": cols["humid"], "tilt": cols["tilt"]}
targets = {"vlf 0.005-0.02Hz": seis["vlf"] * UV, "lf 0.02-0.12Hz": seis["lf"] * UV,
           "ms 0.12-0.5Hz": seis["ms"] * UV, "dc level": seis["dc_counts"],
           "dc slope": np.abs(seis["dc_slope_per_h"])}
print(f"{'Spearman rho':<20}" + "".join(f"{d:>12}" for d in drivers))
for tn, tv in targets.items():
    line = f"{tn:<20}"
    for dv in drivers.values():
        ok = np.isfinite(tv) & np.isfinite(dv)
        r = stats.spearmanr(tv[ok], dv[ok]).statistic if ok.sum() > 10 else np.nan
        line += f"{r:>12.2f}"
    print(line)

print("\nband levels, uV (median / p10 / p90):")
for tn in ("vlf 0.005-0.02Hz", "lf 0.02-0.12Hz", "ms 0.12-0.5Hz"):
    v = targets[tn][np.isfinite(targets[tn])]
    print(f"  {tn:<20} {np.median(v):8.1f} {np.percentile(v,10):8.1f} {np.percentile(v,90):8.1f}"
          f"   swing p90/p10 = {np.percentile(v,90)/np.percentile(v,10):.1f}x")

# diurnality, local time
tz = __import__("zoneinfo").ZoneInfo("America/Los_Angeles")
hours = np.array([dt.datetime.fromtimestamp(x, tz).hour for x in t])
print("\nhour-of-day medians, local (uV):")
print("  hour " + " ".join(f"{h:5d}" for h in range(0, 24, 2)))
for tn in ("lf 0.02-0.12Hz", "ms 0.12-0.5Hz"):
    v = targets[tn]
    print(f"  {tn[:3]:<5}" + " ".join(f"{np.nanmedian(v[hours==h]):5.0f}" for h in range(0, 24, 2)))
# distinct keys: "dc level" and "dc slope" both start with "dc" and one silently
# overwrote the other on the first pass.
np.savez(os.path.join(S, "joined.npz"), t=t, **cols,
         vlf=seis["vlf"] * UV, lf=seis["lf"] * UV, ms=seis["ms"] * UV,
         dc=seis["dc_counts"], dc_slope=np.abs(seis["dc_slope_per_h"]))
