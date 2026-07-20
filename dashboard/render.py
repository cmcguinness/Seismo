"""render.py — ObsPy helicorder/spectrum PNG rendering for the public dashboard.

Reads the locally-mirrored miniSEED (rsync'd onto the Dokku host from the Pi),
so it never touches the network or the acquisition box. Returns PNG bytes.
"""
import glob
import io
import math
import os
from collections import Counter

import numpy as np

DATA = os.environ.get("SEISMO_DATA", "/data/data")
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
UVPC = (2.5 * 2 / (GAIN * (2 ** 23 - 1))) * 1e6      # microvolts per count


def _load_day(path):
    """Read a day-file -> gap-split Stream, normalizing mixed sample rates
    (early archive has 55/57 sps segments; ObsPy won't merge across rates)."""
    import obspy

    st = obspy.read(path)
    dom = Counter(round(t.stats.sampling_rate) for t in st).most_common(1)[0][0]
    off = [t for t in st if round(t.stats.sampling_rate) != dom]
    if off:
        for t in off:
            t.resample(float(dom))
        for t in st:
            t.data = t.data.astype("float64")
    st.merge(method=1)
    return st.split()


def _latest():
    files = sorted(glob.glob(os.path.join(DATA, "*.mseed")), key=os.path.getmtime)
    return files[-1] if files else None


def helicorder_png(hours=8, interval=15):
    path = _latest()
    if not path:
        return None
    st = _load_day(path)
    latest = max(t.stats.endtime for t in st)
    st.trim(latest - hours * 3600, latest)
    for t in list(st):
        if t.stats.npts == 0:
            st.remove(t)
    if not len(st):
        return None
    st.detrend("demean")
    start = min(t.stats.starttime for t in st)
    interval_s = interval * 60
    boundary = start - (start.timestamp % interval_s)          # clock-align rows
    # nearest_sample=False pads to the sample *at or after* the boundary, so the
    # first row starts at :00.00x — not :59.99x, which dayplot would floor to ":59".
    min(st, key=lambda t: t.stats.starttime).trim(
        boundary, pad=True, fill_value=None, nearest_sample=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # show_y_UTC_label=False: suppress ObsPy's auto caption ("local time = UTC +
    # HH:MM"), which reflects the *render host's* timezone (irrelevant) — set our own.
    fig = st.plot(type="dayplot", interval=interval,
                  title=f"{st[0].id}   {start.date}",
                  color=["k", "r", "b", "g"], one_tick_per_line=True,
                  show_y_UTC_label=False, show=False)
    fig.axes[0].set_ylabel("UTC")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def spectrum_png(minutes=60):
    """Welch ASD (uV/sqrtHz) over the last `minutes`.

    The archive is fragmented into hundreds of short segments by sub-second
    timing gaps (the ~57 sps declared-vs-actual jitter), so the single longest
    *continuous* fragment is only ~1-3 min -> a noisy spectrum that changes
    every refresh. We instead take the whole `minutes` window and bridge those
    micro-gaps by interpolation, giving one long record and ~50 Welch averages
    for a smooth, stable ASD. (Real outages would interpolate a straight line,
    which after demean is just a low-freq ramp -- rare and self-corrects hourly.)
    """
    import numpy.ma as ma
    from scipy import signal
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = _latest()
    if not path:
        return None
    st = _load_day(path)
    latest = max(t.stats.endtime for t in st)
    st.trim(latest - minutes * 60, latest)
    st.merge(method=1, fill_value="interpolate")       # bridge the timing micro-gaps
    if not len(st):
        return None
    tr = max(st, key=lambda t: t.stats.npts)
    tr.detrend("demean")
    fs = tr.stats.sampling_rate
    x = tr.data
    if ma.isMaskedArray(x):                             # any unfilled edge gaps
        x = x.filled(0.0)
    x = x.astype(float) * UVPC
    if x.size < 1024:
        return None
    nper = min(8192, x.size)
    f, pxx = signal.welch(x, fs=fs, nperseg=nper)
    asd = np.sqrt(pxx)
    win_min = x.size / fs / 60
    navg = max(1, int(2 * x.size / nper) - 1)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.loglog(f[1:], asd[1:], "k", lw=0.8, zorder=5)
    # Floor at 0.05 Hz: below the microseism the 4.5 Hz geophone is ~60 dB down,
    # so anything lower is instrument self-noise, not ground motion. 0.05 (not 0.1)
    # keeps both microseism humps (primary ~0.05-0.1, secondary ~0.1-0.35).
    ax.set_xlim(0.05, fs / 2)

    # --- educational annotations ---
    tx = ax.get_xaxis_transform()          # x in data coords, y in axes fraction
    ax.axvspan(0.1, 0.35, color="#2aa198", alpha=0.13, lw=0)     # ocean microseism
    ax.text(0.185, 0.95, "ocean\nmicroseism", transform=tx, ha="center", va="top",
            fontsize=8, color="#2aa198")
    ax.axvspan(1, 15, color="#268bd2", alpha=0.07, lw=0)         # local-quake band
    ax.text(5, 0.04, "local-earthquake band", transform=tx, ha="center", va="bottom",
            fontsize=8, color="#268bd2")
    ax.axvline(4.5, color="#dc322f", ls="--", lw=1)             # geophone corner
    ax.text(4.5, 0.99, "4.5 Hz corner\n(flat above · deaf below)", transform=tx,
            ha="center", va="top", fontsize=8, color="#dc322f")
    ax.text(0.98, 0.05, "electronic floor →", transform=ax.transAxes, ha="right",
            va="bottom", fontsize=8, color="#888")

    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("ASD (µV/√Hz)")
    ax.set_title(f"{tr.id}  Welch ASD  ({win_min:.0f} min · ~{navg} averages)")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
