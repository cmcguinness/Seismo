#!/usr/bin/env python3
"""break_1641.py — characterise the front-end fault that started 2026-07-31 16:41 PDT.

The 13:40 PDT tile->slab move settled clean (DC back to ~+334k counts, std ~700).
Three hours later the DC dumped to about -2.2M counts and the noise went up
20-200x, and it has not recovered. This plots the transition, the present-day
waveform, and the present spectrum so the failure mode can be named (open
circuit / intermittent contact / mains pickup / saturating amplifier).
"""
import warnings
from pathlib import Path

import numpy as np
import obspy
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
from helicorder import LOCAL_DATA, load_day          # noqa: E402
from spectrum import UV_PER_COUNT                    # noqa: E402

OUT = Path(__file__).resolve().parent / "break_1641.png"
FULL_SCALE = 2 ** 23


def window(julian, t0, t1):
    st = load_day(LOCAL_DATA / f"XX.OAKMT.00.SHZ.D.{julian}.mseed")
    st = st.slice(obspy.UTCDateTime(t0), obspy.UTCDateTime(t1))
    st.merge(method=1, fill_value="interpolate")
    tr = max(st, key=lambda t: t.stats.npts)
    return tr, tr.data.astype(float), tr.stats.sampling_rate


fig, ax = plt.subplots(4, 1, figsize=(13, 12))

# 1. the transition itself, in counts against full scale
tr, d, fs = window("2026.212", "2026-07-31T23:30:00", "2026-08-01T00:10:00")
t = np.arange(len(d)) / fs / 60.0
ax[0].plot(t, d, lw=0.4)
ax[0].axhline(-FULL_SCALE, color="r", ls=":", label="negative full scale")
ax[0].axhline(0, color="k", lw=0.5)
ax[0].set_xlabel("minutes from 16:30 PDT")
ax[0].set_ylabel("counts")
ax[0].set_title("the break: 16:30-17:10 PDT (DC leaves +334k, never returns)")
ax[0].legend(fontsize=8)

# 2. two minutes of "now"
tr, d, fs = window("2026.213", "2026-08-01T05:10:00", "2026-08-01T05:12:00")
t = np.arange(len(d)) / fs
ax[1].plot(t, d * UV_PER_COUNT, lw=0.5)
ax[1].set_xlabel("seconds from 22:10 PDT")
ax[1].set_ylabel(r"$\mu$V")
ax[1].set_title("present state, 2 min (mean removed? no -- absolute, gain-64 input referred)")

# 3. five seconds of it, to see the waveform shape
seg = d[: int(5 * fs)]
ax[2].plot(np.arange(len(seg)) / fs, (seg - seg.mean()) * UV_PER_COUNT, lw=0.8, marker=".", ms=1.5)
ax[2].set_xlabel("seconds")
ax[2].set_ylabel(r"$\mu$V (de-meaned)")
ax[2].set_title("5 s zoom -- steps/telegraph = intermittent contact; sinusoid = pickup")

# 4. spectrum now vs before the move
f2, p2 = signal.welch((d - d.mean()) * UV_PER_COUNT, fs=fs, nperseg=8192)
trb, db, fsb = window("2026.212", "2026-07-31T18:00:00", "2026-07-31T20:00:00")
f1, p1 = signal.welch((db - db.mean()) * UV_PER_COUNT, fs=fsb, nperseg=8192)
ax[3].loglog(f1, np.sqrt(p1), label="before move (11-13 PDT, healthy)", lw=1)
ax[3].loglog(f2, np.sqrt(p2), label="now (22:10 PDT, faulted)", lw=1)
for h in (60, 120, 180):
    ax[3].axvline(h, color="r", ls=":", lw=0.7)
ax[3].set_xlabel("Hz")
ax[3].set_ylabel(r"ASD ($\mu$V/$\sqrt{Hz}$)")
ax[3].set_title("spectrum, healthy vs faulted (red dotted = mains harmonics)")
ax[3].legend(fontsize=8)
ax[3].grid(True, which="both", alpha=0.3)

fig.tight_layout()
fig.savefig(OUT, dpi=110)
print("wrote", OUT)
