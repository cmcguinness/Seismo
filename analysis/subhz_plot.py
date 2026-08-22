import datetime as dt, os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
d = np.load(os.path.join(S, "joined.npz"))
t = [dt.datetime.fromtimestamp(x, dt.timezone.utc) for x in d["t"]]
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
fig, axes = plt.subplots(4, 1, figsize=(13, 11), sharex=True, facecolor=SURFACE,
                         gridspec_kw=dict(hspace=0.28))
for a in axes:
    a.set_facecolor(SURFACE)
    for s in ("top", "right"): a.spines[s].set_visible(False)
    a.grid(axis="y", color="#e8e7e4", lw=0.8)

ax = axes[0]
for k, c, lab in (("vlf", "#9ec5f4", "0.005-0.02 Hz"), ("lf", "#975bc9", "0.02-0.12 Hz"),
                  ("ms", "#960854", "0.12-0.5 Hz (microseism band)")):
    ax.plot(t, d[k], lw=1.2, color=c, label=lab)
ax.set_yscale("log"); ax.set_ylabel("band RMS, µV")
ax.set_title("Sub-1 Hz band levels — the part the drum high-passes away", loc="left",
             fontsize=12, color=INK)
ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper left")
ax.set_ylim(0.2, 3)

ax = axes[1]
ax.plot(t, d["dc"], lw=1.2, color="#2a78d6", label="DC level (raw interval mean)")
ax.set_ylabel("counts", color="#2a78d6")
a2 = ax.twinx(); a2.plot(t, d["temp"], lw=1.2, color="#e2191c", label="temp")
a2.set_ylabel("CLUE temp, °C (self-heated: read swings)", color="#e2191c")
for s in ("top",): a2.spines[s].set_visible(False)
r = stats.spearmanr(d["dc"], d["temp"]).statistic
ax.set_title(f"DC baseline vs garage temperature — Spearman ρ = {r:.2f}", loc="left",
             fontsize=12, color=INK)

ax = axes[2]
ax.plot(t, d["press"], lw=1.2, color="#1baf7a")
ax.set_ylabel("pressure, hPa")
ax.set_title("Barometric pressure", loc="left", fontsize=12, color=INK)

ax = axes[3]
ax.plot(t, d["tilt"], lw=1.2, color="#eda100")
ax.set_ylabel("tilt off vertical, µrad")
ax.set_title("Tilt from the CLUE accelerometer (coarse — a sanity channel, not a tiltmeter)",
             loc="left", fontsize=12, color=INK)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.set_xlabel("UTC")

fig.suptitle("Sub-1 Hz probe · 8.9 days, one configuration (13–21 Aug 2026)",
             x=0.09, ha="left", fontsize=14, color=INK)
fig.savefig("analysis/subhz_probe.png", dpi=110, facecolor=SURFACE, bbox_inches="tight")
print("wrote analysis/subhz_probe.png")

for k in ("vlf", "lf", "ms"):
    v = d[k]
    print(f"{k:4} median {np.median(v):.2f} µV   p10-p90 {np.percentile(v,10):.2f}-"
          f"{np.percentile(v,90):.2f}   max {v.max():.2f}   max/median {v.max()/np.median(v):.1f}x")
print("DC range:", f"{d['dc'].min():.0f} to {d['dc'].max():.0f} counts "
      f"({(d['dc'].max()-d['dc'].min())*2.5*2/(64*(2**23-1))*1e6:.1f} µV p-p)")
print("temp range:", f"{d['temp'].min():.1f} to {d['temp'].max():.1f} C")
