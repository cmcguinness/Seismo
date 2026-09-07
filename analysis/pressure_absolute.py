#!/usr/bin/env python3
"""pressure_absolute.py -- SS.OAKM1.20.LDO in absolute units, not de-meaned.

The de-meaned view answers "did anything happen"; the absolute view answers "is this
instrument telling the truth", and it is the one that can be checked against the
outside world.

Station pressure runs near 1000 hPa because the garage sits at 128.3 m. Reduced to sea
level with the standard atmosphere it should land near a local forecast's QNH -- that
is the only external check available on this channel, and unlike EHZ it is a check on
an ABSOLUTE number, because the BMP280 is factory-calibrated in Pa while the geophone's
f0 and zeta are still guesses.

The reduction uses the STANDARD atmosphere's 15 C, deliberately NOT the CLUE's own
temp_C: that channel reads the board's self-heat (~27 C indoors), not ambient air, and
feeding it into a barometric formula would produce a confidently wrong number.

SCALE, which is the real content of the absolute view:

    absolute reading            ~100,080 Pa
    weather swing over 2 h              38 Pa   (4e-4 of the reading)
    predicted earthquake signal       0.12 Pa   (1.2e-6 of the reading)

Finding an earthquake in this channel means finding one part in a million of the number
the sensor reports. That is not hopeless -- differencing removes the baseline entirely,
which is what panel B does -- but it is why the absolute plot looks like a flat line
with weather on it and nothing else.

Writes reports/pressure-absolute.png.
"""
import glob
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import obspy

warnings.simplefilter("ignore")

DATA = Path("analysis/data/ldo")
OUT = Path("reports/pressure-absolute.png")
ORIGIN = obspy.UTCDateTime("2026-09-03T17:33:27Z")
ELEV_M = 128.3
P_QUAKE_PA = 0.122            # rho*c*v, see pressure_at_quake.py


def sea_level(p_hpa, h_m=ELEV_M, t0_c=15.0):
    """Standard-atmosphere reduction to sea level (QNH). t0 is the STANDARD 15 C --
    the CLUE's own temperature channel is board self-heat, not ambient air."""
    return p_hpa * (1.0 - 0.0065 * h_m / (t0_c + 0.0065 * h_m + 273.15)) ** -5.257


st = obspy.Stream()
for f in sorted(glob.glob(str(DATA / "SS.OAKM1.20.LDO.D.*.mseed"))):
    st += obspy.read(f)
st.merge(method=0, fill_value=None)
tr = st[0]
p = np.ma.filled(tr.data.astype(float), np.nan) / 10000.0          # counts -> hPa
t = tr.stats.starttime.matplotlib_date + np.arange(tr.stats.npts) / 86400.0
print(f"{tr.stats.npts} samples, {tr.stats.starttime} -> {tr.stats.endtime}")

fig, ax = plt.subplots(2, 1, figsize=(12, 8.5),
                       gridspec_kw={"height_ratios": [1.35, 1.0], "hspace": 0.34})

# --- A: the whole record, absolute -------------------------------------------------
ax[0].plot(t, p, lw=0.5, color="#8a5a00")
ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax[0].xaxis.set_major_locator(mdates.DayLocator(interval=5))
ax[0].set_ylabel("station pressure (hPa)")
ax[0].grid(alpha=0.25)
ax[0].axvline(ORIGIN.matplotlib_date, color="#c62828", lw=1.0, ls="--")
ax[0].set_title(f"A.  SS.OAKM1.20.LDO, absolute — the whole record, "
                f"{np.nanmin(p):.1f} to {np.nanmax(p):.1f} hPa at 128.3 m elevation",
                loc="left", fontsize=11, weight="bold")
sec = ax[0].secondary_yaxis("right", functions=(sea_level,
                                                lambda q: q / (sea_level(1.0))))
sec.set_ylabel("reduced to sea level, QNH (hPa)")
ax[0].annotate("the M3.3", xy=(ORIGIN.matplotlib_date, 0.93), xycoords=("data", "axes fraction"),
               color="#c62828", fontsize=9, ha="right", va="top",
               xytext=(-6, 0), textcoords="offset points")

# --- B: the quake hour, absolute, with the earthquake drawn to scale ----------------
i0 = int((ORIGIN - 3600 - tr.stats.starttime) * tr.stats.sampling_rate)
i1 = int((ORIGIN + 3600 - tr.stats.starttime) * tr.stats.sampling_rate)
tw, pw = t[i0:i1], p[i0:i1]
ax[1].plot(tw, pw, lw=0.8, color="#8a5a00")
ax[1].axvline(ORIGIN.matplotlib_date, color="#c62828", lw=1.0, ls="--")
ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax[1].set_ylabel("station pressure (hPa)")
ax[1].set_xlabel("2026-09-03 (UTC)")
ax[1].grid(alpha=0.25)
ax[1].set_title("B.  The quake hour, same absolute scale. The red bar is the predicted "
                "earthquake signal, drawn to scale.", loc="left", fontsize=11, weight="bold")

# The predicted signal drawn TO SCALE, in clear headroom above the trace. It is a
# couple of pixels tall on purpose -- that is the entire point of the absolute view.
lo, hi = np.nanmin(pw), np.nanmax(pw)
ax[1].set_ylim(lo - 0.02, hi + 0.10)
xbar = ORIGIN.matplotlib_date + 0.016
ybar = hi + 0.045
ax[1].errorbar([xbar], [ybar], yerr=[P_QUAKE_PA / 200.0], color="#c62828",
               capsize=7, lw=2.5, capthick=2.5, zorder=5)
ax[1].annotate(f"predicted earthquake, to scale:\n{P_QUAKE_PA:.2f} Pa = "
               f"{P_QUAKE_PA/100:.4f} hPa",
               xy=(xbar, ybar), xytext=(-150, -4), textcoords="offset points",
               fontsize=9, color="#c62828", va="center", ha="left",
               arrowprops=dict(arrowstyle="->", color="#c62828", lw=1.2,
                               shrinkA=2, shrinkB=6))

rng_pa = (np.nanmax(pw) - np.nanmin(pw)) * 100
ax[1].annotate(f"absolute reading  ≈ {np.nanmean(pw)*100:,.0f} Pa\n"
               f"weather, this 2 h  = {rng_pa:.0f} Pa   ({rng_pa/(np.nanmean(pw)*100):.1e} of it)\n"
               f"earthquake         = {P_QUAKE_PA:.2f} Pa   "
               f"({P_QUAKE_PA/(np.nanmean(pw)*100):.1e} of it)",
               xy=(0.015, 0.06), xycoords="axes fraction", fontsize=9, family="monospace",
               bbox=dict(boxstyle="round,pad=0.45", fc="#fff8e1", ec="#8a5a00", alpha=0.95))

fig.suptitle("Absolute barometric pressure — one part in a million is the target",
             fontsize=13, weight="bold", y=0.965)
fig.text(0.5, 0.005,
         f"Mean station pressure {np.nanmean(p):.2f} hPa → {sea_level(np.nanmean(p)):.2f} hPa "
         f"reduced to sea level (standard atmosphere, 15 °C, 128.3 m). The BMP280 is "
         "factory-calibrated in absolute Pa, so unlike EHZ this number can be checked "
         "against a local forecast.", ha="center", fontsize=8.5, color="#444")

OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches="tight")
print(f"wrote {OUT}")
print(f"  station mean {np.nanmean(p):.2f} hPa, range {np.nanmin(p):.2f}-{np.nanmax(p):.2f}")
print(f"  sea-level equivalent {sea_level(np.nanmean(p)):.2f} hPa "
      f"(check against a local forecast)")
print(f"  quake-hour weather {rng_pa:.1f} Pa; predicted earthquake {P_QUAKE_PA:.3f} Pa "
      f"= 1 part in {np.nanmean(p)*100/P_QUAKE_PA:,.0f}")
