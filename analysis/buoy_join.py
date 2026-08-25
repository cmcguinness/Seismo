#!/usr/bin/env python3
"""buoy_join.py — does OAKMT's sub-Hz channel hear the ocean at Bodega Bay?

The 0.1-0.5 Hz "secondary microseism" is swell hammering the coast: its frequency is
TWICE the swell frequency (Longuet-Higgins), and its amplitude scales roughly with
wave height squared. NDBC buoy 46013 (Bodega Bay, ~35 km W of the station) reports
significant wave height (WVHT), dominant period (DPD) and average period (APD) every
10 min, and the last 45 days are public at
    https://www.ndbc.noaa.gov/data/realtime2/46013.txt

This joins that to the per-15-min sub-Hz reduction (`subhz_reduce.py` -> subhz.csv)
and asks whether the `ms` band (0.12-0.5 Hz) follows the buoy. Prior finding
(2026-08-21): all three sub-Hz bands sit on the electronics floor, as the f^2 roll-off
of a 4.5 Hz element predicts -- so a null here is the expected answer, and a positive
one is news.

Predictors tried, per interval (buoy medianed onto the same 15-min grid):
    Hs          significant wave height, m
    Hs2         Hs**2 (energy)
    f_ms        2/DPD -- where the microseism should sit; only matters inside the band
    Hs2_in      Hs**2 when 2/DPD falls inside 0.12-0.5 Hz, else 0  (the physical proxy)
Correlations are Spearman (monotone, outlier-safe), on ALL intervals and on the
local-night subset (00-05 PDT) where cultural noise is lowest.

    python analysis/buoy_join.py [ndbc_file] [subhz_csv]
"""
import datetime as dt
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, "data")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6          # counts -> uV at PGA 64
BAND = (0.12, 0.5)
PDT = -7


def load_ndbc(path):
    """realtime2 stdmet text -> (t, Hs, DPD, APD, pres), MM rows dropped."""
    t, hs, dpd, apd, pres = [], [], [], [], []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            f = line.split()
            if len(f) < 13 or f[8] == "MM":
                continue
            y, mo, d, h, mi = (int(x) for x in f[:5])
            t.append(dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc).timestamp())
            hs.append(float(f[8]))
            dpd.append(float(f[9]) if f[9] != "MM" else np.nan)
            apd.append(float(f[10]) if f[10] != "MM" else np.nan)
            pres.append(float(f[12]) if f[12] != "MM" else np.nan)
    o = np.argsort(t)
    return (np.array(t)[o], np.array(hs)[o], np.array(dpd)[o],
            np.array(apd)[o], np.array(pres)[o])


def to_grid(bt, bv, grid, half=1800.0):
    """median of buoy samples within +-half s of each grid time (nan if none)."""
    out = np.full(len(grid), np.nan)
    for i, g in enumerate(grid):
        sel = (bt >= g - half) & (bt < g + half)
        v = bv[sel]
        v = v[np.isfinite(v)]
        if len(v):
            out[i] = np.median(v)
    return out


def rho(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 10:
        return np.nan, np.nan, int(m.sum())
    r, p = stats.spearmanr(x[m], y[m])
    return r, p, int(m.sum())


def main():
    ndbc = sys.argv[1] if len(sys.argv) > 1 else os.path.join(S, "ndbc_46013.txt")
    sub = sys.argv[2] if len(sys.argv) > 2 else os.path.join(S, "subhz.csv")
    seis = np.genfromtxt(sub, delimiter=",", names=True)
    bt, hs, dpd, apd, pres = load_ndbc(ndbc)

    g = seis["t0"]
    Hs = to_grid(bt, hs, g)
    DPD = to_grid(bt, dpd, g)
    APD = to_grid(bt, apd, g)
    P = to_grid(bt, pres, g)
    f_ms = 2.0 / DPD
    inband = (f_ms >= BAND[0]) & (f_ms < BAND[1])
    Hs2 = Hs ** 2
    Hs2_in = np.where(inband, Hs2, 0.0)

    hour_local = ((g / 3600.0 + PDT) % 24)
    night = (hour_local >= 0) & (hour_local < 5)

    ok = np.isfinite(Hs)
    t0 = dt.datetime.fromtimestamp(g[ok].min(), dt.timezone.utc)
    t1 = dt.datetime.fromtimestamp(g[ok].max(), dt.timezone.utc)
    print(f"overlap {t0:%Y-%m-%d %H:%M} -> {t1:%Y-%m-%d %H:%M} UTC, "
          f"{ok.sum()} intervals ({night[ok].sum()} night)")
    print(f"buoy over overlap: Hs {np.nanmin(Hs[ok]):.1f}-{np.nanmax(Hs[ok]):.1f} m, "
          f"DPD {np.nanmin(DPD[ok]):.0f}-{np.nanmax(DPD[ok]):.0f} s, "
          f"2/DPD in band {inband[ok].mean()*100:.0f}% of the time")
    for b in ("ms", "lf", "vlf"):
        v = seis[b] * UV
        print(f"  {b}: median {np.nanmedian(v[ok]):.3f} uV, "
              f"p5-p95 {np.nanpercentile(v[ok],5):.3f}-{np.nanpercentile(v[ok],95):.3f}")

    preds = dict(Hs=Hs, Hs2=Hs2, DPD=DPD, APD=APD, f_ms=f_ms, Hs2_in=Hs2_in, pres=P)
    print("\nSpearman rho (p) -- rows: seismic band; cols: buoy predictor")
    for subset, mask in (("ALL", ok), ("NIGHT 00-05 PDT", ok & night)):
        print(f"\n[{subset}]  n={mask.sum()}")
        print("      " + "".join(f"{k:>16}" for k in preds))
        for b in ("ms", "lf", "vlf", "dc_counts"):
            row = f"{b:>9} "
            for k, x in preds.items():
                r, p, n = rho(x[mask], seis[b][mask])
                row += f"{r:>+8.2f} ({p:6.1g})" if np.isfinite(r) else f"{'--':>16}"
            print(row)

    # lag scan: does ms follow Hs2_in with a delay? (+lag = seismic lags buoy)
    print("\nlag scan, ms vs Hs2_in (night only), lag in hours (+ = station lags buoy):")
    for lag_h in (-6, -3, -1, 0, 1, 3, 6, 12):
        sh = int(round(lag_h * 4))
        x = np.roll(Hs2_in, sh)
        m = ok & night
        if sh > 0:
            m = m & (np.arange(len(g)) >= sh)
        elif sh < 0:
            m = m & (np.arange(len(g)) < len(g) + sh)
        r, p, n = rho(x[m], seis["ms"][m])
        print(f"  {lag_h:+3d} h  rho {r:+.2f}  p {p:.2g}  n {n}")

    # --- figure ---------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tt = [dt.datetime.fromtimestamp(x, dt.timezone.utc) for x in g]
    fig, ax = plt.subplots(4, 1, figsize=(13, 10), sharex=True)
    ax[0].plot(tt, Hs, "k-", lw=1); ax[0].set_ylabel("Hs  m")
    a2 = ax[0].twinx(); a2.plot(tt, DPD, "c.", ms=2); a2.set_ylabel("DPD  s", color="c")
    a2.axhspan(2 / BAND[1], 2 / BAND[0], color="c", alpha=0.08)
    ax[0].set_title("NDBC 46013 Bodega Bay: wave height (black), dominant period (cyan; "
                    "shaded = 2/DPD inside 0.12-0.5 Hz)")
    ax[1].plot(tt, Hs2_in, "b-", lw=1); ax[1].set_ylabel("Hs$^2$ in-band  m$^2$")
    ax[2].plot(tt, seis["ms"] * UV, "r.", ms=2)
    ax[2].plot(np.array(tt)[night], seis["ms"][night] * UV, "k.", ms=3, label="night 00-05 PDT")
    ax[2].set_ylabel("OAKMT 0.12-0.5 Hz  uV RMS"); ax[2].legend(loc="upper right")
    ax[2].set_yscale("log")
    ax[3].plot(tt, seis["lf"] * UV, ".", ms=2, color="0.5", label="0.02-0.12 Hz")
    ax[3].plot(tt, seis["vlf"] * UV, ".", ms=2, color="orange", label="0.005-0.02 Hz")
    ax[3].set_ylabel("uV RMS"); ax[3].set_yscale("log"); ax[3].legend(loc="upper right")
    for a in ax:
        a.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    out = os.path.join(HERE, "buoy_microseism.png")
    fig.savefig(out, dpi=110)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
