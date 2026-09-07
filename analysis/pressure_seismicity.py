#!/usr/bin/env python3
"""pressure_seismicity.py -- does barometric pressure predict earthquakes here? Measured.

SHORT ANSWER: none, in two independent senses.

(1) MEASURED HERE: no effect, all four tests p = 0.34 to 0.94. But that is nearly
    uninformative, because the binding constraint is not how many earthquakes we have
    (1,208) -- it is how many INDEPENDENT WEATHER STATES we have sampled. Pressure
    anomalies persist for days, so 44 days of record holds only a couple of dozen
    independent draws of the predictor, and no number of earthquakes inside the same
    weather raises that ceiling. See the power printout.

(2) STRUCTURALLY, and this one does not go away with more data: every published effect
    in this class is a few-percent modulation of a RATE over decades of catalogue. If
    the daily probability of a damaging local earthquake is ~1e-5, a 10% modulation
    makes it 1.1e-5. A rate modulation is a statement about a catalogue; a prediction
    is a statement about tomorrow. Nothing in this literature bridges that gap.

WHY THE QUESTION IS REASONABLE. A 10 hPa weather swing is a 1 kPa load on the ground.
That is the same order as the solid-earth and ocean tidal stresses that DO measurably
modulate seismicity by a few percent (Cochran, Vidale & Tanaka 2004, Science), and far
below the ~10 kPa Coulomb change usually quoted as a triggering threshold. There is
credible published evidence for atmospheric and hydrological loading changing seismic
rates: typhoon-driven pressure drops triggering slow slip in Taiwan (Liu, Linde & Sacks
2009, Nature), seasonal water storage modulating California seismicity (Johnson, Fu &
Burgmann 2017, Science), monsoon loading in the Himalaya (Bettinelli et al. 2008,
Nature Geoscience), snow load in Japan (Heki 2003). Citations from memory -- verify
before quoting them anywhere that matters.

Every one of those is a RATE MODULATION of a few percent detected over years to decades
of catalogue. None is a prediction of an individual earthquake, and that distinction is
the whole answer to the question.

WHAT THIS SCRIPT TESTS. For every catalogued event with pressure coverage: the pressure
anomaly (deviation from a 10-DAY running mean) and the 3 h tendency (dP/dt, the "is it
falling" question) at the moment of origin.

The baseline length is a real choice, not a default. The first version removed a 24 h
running mean, which high-passes away precisely the multi-day systems the cited papers
are about -- a typhoon is a 10-25 hPa drop over days. The tell was the decorrelation
time coming out at 4 hours, i.e. the atmospheric tide, not weather. A 10-day baseline
keeps synoptic systems, and the measured decorrelation time moves to where physical
sense says it should be. Compared against the same quantities sampled over all covered time. KS test for distribution shape, plus a CIRCULAR TIME-SHIFT null for the mean shift: the
whole event list is slid by a random lag against the pressure series and the statistic
recomputed. That is the right null here because it preserves BOTH things that would
otherwise manufacture significance -- the clustering of events (aftershocks, swarms) and
the autocorrelation of pressure (weather systems last days). An i.i.d. bootstrap
preserves neither, and the first version of this script used one: it reported the
anomaly shift as "outside the null" while the KS test on the same data said p = 0.54.
Two tests disagreeing that hard is a bug, not a discovery, and it was.

THE GEYSERS ARE SPLIT OUT. Roughly half the local catalogue is geothermal injection
seismicity at The Geysers, whose rate is driven by the operator's injection schedule.
Leaving it in means measuring a power plant, not the crust.

CONFOUND WORTH NAMING: this uses the USGS CATALOGUE, not our own detections, on purpose.
Our detection threshold rises with wind and rain, so correlating OUR detections against
weather would find a beautiful, entirely spurious signal -- the weather changing what we
can hear, not what the ground does.

Writes reports/pressure-seismicity.png.
"""
import csv
import datetime as dt
import glob
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import obspy
from scipy import stats
from scipy.ndimage import uniform_filter1d

warnings.simplefilter("ignore")

DATA = Path("analysis/data/ldo")
OUT = Path("reports/pressure-seismicity.png")
SMOOTH_H = 240         # 10-day baseline: the anomaly must KEEP multi-day weather
                       # systems, which is what the loading literature is about
TEND_H = 3             # tendency window
RNG = np.random.default_rng(7)


def load_pressure():
    st = obspy.Stream()
    for f in sorted(glob.glob(str(DATA / "SS.OAKM1.20.LDO.D.*.mseed"))):
        st += obspy.read(f)
    st.merge(method=0, fill_value=None)
    tr = st[0]
    p = np.ma.filled(tr.data.astype(float), np.nan) / 100.0        # Pa
    t = tr.stats.starttime.timestamp + np.arange(tr.stats.npts)    # 1 sps
    # hourly means: robust to the pre-fix gaps, and the physics is not a 1 s question
    nh = len(p) // 3600
    ph = np.nanmean(p[:nh * 3600].reshape(nh, 3600), axis=1)
    th = t[:nh * 3600].reshape(nh, 3600)[:, 1800]
    # mode="nearest", NOT np.convolve: zero-padding at the edges gave the first and
    # last 12 hours a ~50 kPa fake anomaly and dragged the background mean to +575 Pa,
    # which is what exposed the bug.
    filled = np.where(np.isfinite(ph), ph, np.nanmean(ph))
    base = uniform_filter1d(filled, size=SMOOTH_H, mode="nearest")
    anom = ph - base
    tend = np.full(nh, np.nan)
    tend[TEND_H:] = (ph[TEND_H:] - ph[:-TEND_H]) / TEND_H          # Pa/h
    return th, ph, anom, tend


def load_events():
    ev = []
    with open("analysis/event_harvest.csv") as f:
        for r in csv.DictReader(f):
            ev.append((dt.datetime.fromisoformat(r["origin"].replace("Z", "+00:00")).timestamp(),
                       float(r["mag"]), "Geysers" in r["place"]))
    return ev


def shift_null(series, idx, n=4000):
    """Circular time-shift null: slide the event list against the pressure series.

    Preserves the clustering of the events AND the autocorrelation of the weather,
    which is exactly what an i.i.d. bootstrap destroys. Returns (observed shift,
    null 2.5%, null 97.5%, two-sided p).
    """
    bg = np.nanmean(series[np.isfinite(series)])
    obs = np.nanmean(series[idx]) - bg
    m = len(series)
    null = np.empty(n)
    for i in range(n):
        sh = (idx + RNG.integers(1, m)) % m
        null[i] = np.nanmean(series[sh]) - bg
    pv = float(np.mean(np.abs(null - np.mean(null)) >= abs(obs - np.mean(null))))
    return obs, float(np.percentile(null, 2.5)), float(np.percentile(null, 97.5)), pv


th, ph, anom, tend = load_pressure()
ev = load_events()
t0, t1 = th[0], th[-1]
print(f"pressure: {len(th)} hours, {dt.datetime.utcfromtimestamp(t0):%Y-%m-%d} -> "
      f"{dt.datetime.utcfromtimestamp(t1):%Y-%m-%d}")

results = {}
fig, ax = plt.subplots(2, 2, figsize=(12.5, 8.6))
for col, (label, keep) in enumerate((("all catalogue events", lambda g: True),
                                     ("Geysers removed", lambda g: not g))):
    idx, mags = [], []
    for ts, mag, geys in ev:
        if not keep(geys) or not (t0 <= ts <= t1):
            continue
        i = int(round((ts - t0) / 3600.0))
        if 0 <= i < len(th) and np.isfinite(anom[i]) and np.isfinite(tend[i]):
            idx.append(i); mags.append(mag)
    idx = np.array(idx)
    days = (th[idx] // 86400).astype(int)
    print(f"\n=== {label}: {len(idx)} events on {len(np.unique(days))} distinct days ===")
    for row, (name, series, unit) in enumerate(
            (("pressure anomaly", anom, "Pa"), (f"{TEND_H} h tendency", tend, "Pa/h"))):
        bg = series[np.isfinite(series)]
        vals = series[idx]
        ks = stats.ks_2samp(vals, bg)
        obs, lo, hi, pv_shift = shift_null(series, idx)
        sig = "OUTSIDE" if (obs < lo or obs > hi) else "inside"
        print(f"  {name:16s}: events {np.mean(vals):+7.2f} {unit}, background "
              f"{np.mean(bg):+7.2f} {unit}")
        print(f"  {'':16s}  shift {obs:+.2f} {unit}, time-shift null 95% "
              f"[{lo:+.2f}, {hi:+.2f}] -> {sig} the null (p = {pv_shift:.3f})")
        print(f"  {'':16s}  KS p = {ks.pvalue:.3f}")
        results[(label, name)] = (obs, lo, hi, ks.pvalue, len(idx))

        a = ax[row, col]
        bins = np.linspace(np.percentile(bg, 0.5), np.percentile(bg, 99.5), 40)
        a.hist(bg, bins=bins, density=True, color="#bbb", label="all covered hours")
        a.hist(vals, bins=bins, density=True, histtype="step", lw=1.8,
               color="#c62828", label=f"at earthquakes (n={len(idx)})")
        a.axvline(np.mean(bg), color="#666", lw=1, ls="--")
        a.axvline(np.mean(vals), color="#c62828", lw=1, ls="--")
        a.set_xlabel(f"{name} ({unit})")
        a.set_ylabel("density")
        a.set_title(f"{'ABCD'[col*2+row]}.  {name} — {label}", loc="left",
                    fontsize=10.5, weight="bold")
        a.legend(fontsize=8)
        a.annotate(f"shift {obs:+.2f} {unit}\nnull 95% [{lo:+.2f}, {hi:+.2f}]\n"
                   f"shift-null p = {pv_shift:.2f}\nKS p = {ks.pvalue:.2f}",
                   xy=(0.02, 0.72), xycoords="axes fraction", fontsize=8.5,
                   family="monospace",
                   bbox=dict(boxstyle="round,pad=0.35", fc="#fff8e1", ec="#8a5a00"))

# --- the number that actually answers the question ---------------------------------
# The limiting quantity is NOT how many earthquakes we have. It is how many INDEPENDENT
# states of the predictor we have seen. Pressure anomalies are weather: they persist for
# days, so 44 days of record contains only a couple of dozen independent draws, and no
# quantity of earthquakes inside those draws can manufacture more.
a = anom[np.isfinite(anom)] - np.nanmean(anom[np.isfinite(anom)])
ac = np.correlate(a, a, mode="full")[len(a) - 1:]
ac /= ac[0]
tau_h = int(np.argmax(ac < 1 / np.e)) if np.any(ac < 1 / np.e) else len(ac)
n_indep = (len(th) / tau_h)
n_ev = results[("Geysers removed", "pressure anomaly")][4]

print("\n=== POWER: what would it take to see a real effect? ===")
print(f"Pressure anomaly decorrelation time (1/e): {tau_h} h = {tau_h/24:.1f} days.")
print(f"So {len(th)/24:.0f} days of record = ~{n_indep:.0f} INDEPENDENT weather states,")
print(f"not {n_ev} independent trials. That is the ceiling on this test, and adding")
print("earthquakes inside the same weather does not raise it.")
print("\nDetecting a correlation of size rho across N independent epochs needs")
print("roughly N > 4/rho^2 for 2 sigma:")
for rho in (0.5, 0.3, 0.2, 0.1):
    need = 4 / rho**2
    print(f"  rho = {rho:.1f} -> {need:6.0f} weather epochs = "
          f"{need * tau_h / 24 / 365:6.1f} years of continuous recording")
print("\nAnd the published effects in this class are a few PERCENT rate modulation,")
print("which is far below rho = 0.1. Those studies used decades of catalogue.")
print("\nTHE DECISIVE POINT IS NOT STATISTICAL. Suppose a real 10% modulation existed")
print("and we had the decades to prove it. If the daily chance of a damaging local")
print("earthquake is ~1e-5, a 10% modulation makes it 1.1e-5. Both round to 'no'.")
print("A rate modulation is a statement about a catalogue; a prediction is a statement")
print("about tomorrow. Nothing in this literature bridges that gap.")

fig.suptitle("Does barometric pressure predict earthquakes here? Measured on 44 days — "
             "and the answer is about power, not p-values",
             fontsize=12.5, weight="bold", y=0.985)
fig.tight_layout(rect=(0, 0.03, 1, 0.955))
fig.text(0.5, 0.005,
         "USGS catalogue, not our own detections: our threshold rises with wind and rain, "
         "so testing our detections against weather would find a spurious signal — the "
         "weather changing what we can hear, not what the ground does.",
         ha="center", fontsize=8.5, color="#444")
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches="tight")
print(f"\nwrote {OUT}")
