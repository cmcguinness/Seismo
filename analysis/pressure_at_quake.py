#!/usr/bin/env python3
"""pressure_at_quake.py -- what the barometer did during the M3.3, and why.

RESULT: nothing, and the reason is arithmetic rather than mystery.

The M3.3 under Larkfield-Wikiup (2026-09-03T17:33:27Z, 13.3 km) peaked at 2,668 uV in
1-15 Hz on EHZ. At the measured 9.0 V/(m/s) that is a peak ground velocity of
2.96e-4 m/s. Ground moving vertically at velocity v radiates an acoustic pressure of
roughly rho*c*v into the air above it -- 1.2 kg/m^3 x 343 m/s x 2.96e-4 m/s = 0.12 Pa.

On 2026-09-03 the pressure channel was logged with two decimals of hPa, quantising at
EXACTLY 1 Pa, on a sensor whose floor measured ~2.3 Pa/sqrt(Hz). The expected signal was
about EIGHT TIMES BELOW the quantisation step alone. There was never anything to see;
the flat trace in panel B is the correct outcome, not a null result about coupling.

Since 2026-09-05 the same channel resolves 0.01 Pa with an averaged floor near 0.35 Pa,
so a repeat of this event would sit at ~1/3 of the floor -- still marginal. Scaling by
peak velocity, an event ~10x stronger at the same distance (very roughly M5 nearby)
would put ~1-4 Pa on this channel, which would be unmistakable. That is the honest
threshold: not "pressure cannot see earthquakes here", but "this sensor, at this floor,
needs about ten times this event".

What panel C is for: the same channel over two hours, where pressure is doing something
real and large. The instrument is not broken or insensitive -- it is measuring the
atmosphere, which is what it is for, and the atmosphere simply dwarfs a small local
earthquake at these frequencies.

Writes reports/pressure-at-quake.png.
"""
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import obspy

warnings.simplefilter("ignore")

DATA = Path("analysis/data/ldo")
OUT = Path("reports/pressure-at-quake.png")
ORIGIN = obspy.UTCDateTime("2026-09-03T17:33:27Z")
TP_S = 2.57                      # measured P pick, analysis/event_harvest.csv
PEAK_UV = 2667.855               # peak 1-15 Hz, same row
SENS_V_PER_MS = 9.0              # measured vs NP.1835
RHO, C_AIR = 1.2, 343.0

v_peak = PEAK_UV * 1e-6 / SENS_V_PER_MS
p_expect = RHO * C_AIR * v_peak


def load(chan, t1, t2):
    st = obspy.read(str(DATA / f"SS.OAKM1.{'00' if chan == 'EHZ' else '20'}."
                         f"{chan}.D.2026.246.mseed"))
    st.trim(t1, t2)
    st.merge(method=0, fill_value=None)
    return st[0] if len(st) else None


def rel(tr):
    return tr.stats.starttime - ORIGIN + np.arange(tr.stats.npts) / tr.stats.sampling_rate


fig, ax = plt.subplots(3, 1, figsize=(11, 10.5),
                       gridspec_kw={"height_ratios": [1.1, 1.3, 1.0], "hspace": 0.42})

# --- A: the earthquake, so there is no doubt it was there --------------------------
tr = load("EHZ", ORIGIN - 60, ORIGIN + 180)
d = tr.copy().detrend("demean").filter("bandpass", freqmin=1, freqmax=15).data * 1e6 / 1.07374e8
ax[0].plot(rel(tr), d, lw=0.4, color="#1f3b73")
ax[0].set_ylabel("ground velocity\n(µV, 1–15 Hz)")
ax[0].set_title("A.  SS.OAKM1.00.EHZ — the M3.3 under Larkfield-Wikiup, 13.3 km",
                loc="left", fontsize=11, weight="bold")

# --- B: the barometer over the same window ------------------------------------------
pt = load("LDO", ORIGIN - 60, ORIGIN + 180)
pv = np.ma.filled(pt.data.astype(float), np.nan) / 100.0     # counts -> Pa
pv -= np.nanmean(pv)
ax[1].step(rel(pt), pv, where="post", lw=1.1, color="#8a5a00")
ax[1].plot(rel(pt), pv, ".", ms=4, color="#8a5a00")
ax[1].axhspan(-p_expect, p_expect, color="#c62828", alpha=0.22, zorder=0,
              label=f"predicted acoustic signal, ±{p_expect:.2f} Pa (ρcv)")
ax[1].set_ylabel("pressure (Pa,\nde-meaned)")
ax[1].set_title("B.  SS.OAKM1.20.LDO — the same 4 minutes. The staircase is the 1 Pa "
                "logging step, not the atmosphere.", loc="left", fontsize=11, weight="bold")
ax[1].legend(loc="upper right", fontsize=8.5, framealpha=0.9)
ax[1].annotate("breaks in the trace are dropped samples — the pre-2026-09-05 firmware\n"
               "lost 3.9 % of them to a clock that had run out of float resolution",
               xy=(0.015, 0.045), xycoords="axes fraction", fontsize=8,
               color="#555", bbox=dict(boxstyle="round,pad=0.3", fc="white",
                                       ec="#bbb", alpha=0.9))

for a in ax[:2]:
    a.axvline(0, color="#c62828", lw=1.0, ls="--")
    a.axvline(TP_S, color="#2e7d32", lw=1.0, ls=":")
    a.set_xlim(-60, 180)
    a.grid(alpha=0.25)
ax[0].annotate("origin", xy=(0.30, 0.93), xycoords="axes fraction",
               color="#c62828", fontsize=8.5, ha="left")
ax[0].annotate(f"P +{TP_S:.2f} s", xy=(0.30, 0.84), xycoords="axes fraction",
               color="#2e7d32", fontsize=8.5, ha="left")
# name the holes before anyone reads them as signal
ngap = int(np.sum(np.isnan(np.ma.filled(load("LDO", ORIGIN - 60, ORIGIN + 180)
                                        .data.astype(float), np.nan))))
ax[1].set_xlabel("seconds from origin")

# --- C: two hours, where the channel is doing its actual job -------------------------
pw = load("LDO", ORIGIN - 3600, ORIGIN + 3600)
wv = np.ma.filled(pw.data.astype(float), np.nan) / 100.0
wv -= np.nanmean(wv)
ax[2].plot(rel(pw) / 60.0, wv, lw=0.8, color="#8a5a00")
ax[2].axvline(0, color="#c62828", lw=1.0, ls="--")
ax[2].set_xlabel("minutes from origin")
ax[2].set_ylabel("pressure (Pa,\nde-meaned)")
ax[2].set_title("C.  The same channel, ±1 hour. It is not insensitive — it is measuring "
                "the atmosphere, which is far larger.", loc="left", fontsize=11, weight="bold")
ax[2].grid(alpha=0.25)
span = np.nanmax(wv) - np.nanmin(wv)
ax[2].annotate(f"weather swing over 2 h: {span:.0f} Pa\n"
               f"earthquake, predicted: {p_expect:.2f} Pa  ({span/p_expect:.0f}× smaller)",
               xy=(0.015, 0.06), xycoords="axes fraction", fontsize=9,
               bbox=dict(boxstyle="round,pad=0.4", fc="#fff8e1", ec="#8a5a00", alpha=0.95))

fig.suptitle("Barometric pressure during the M3.3 — a measured absence, not a null result",
             fontsize=13, weight="bold", y=0.975)
fig.text(0.5, 0.008,
         f"Peak ground velocity {v_peak*1e3:.3f} mm/s → acoustic pressure ρcv ≈ {p_expect:.2f} Pa, "
         f"against a 1 Pa logging step and a ~2.3 Pa/√Hz floor on 2026-09-03. "
         "Since 2026-09-05: 0.01 Pa resolution, ~0.35 Pa floor.",
         ha="center", fontsize=8.5, color="#444")
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches="tight")
print(f"wrote {OUT}")
print(f"  peak ground velocity {v_peak:.3e} m/s -> predicted {p_expect:.3f} Pa")
print(f"  observed pressure over ±2 min: p2p {np.nanmax(pv)-np.nanmin(pv):.2f} Pa, "
      f"rms {np.nanstd(pv):.2f} Pa, distinct values {len(np.unique(pv[~np.isnan(pv)]))}")
print(f"  ±1 h weather swing: {span:.1f} Pa ({span/p_expect:.0f}x the predicted signal)")
