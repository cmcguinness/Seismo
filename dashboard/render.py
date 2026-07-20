"""render.py — ObsPy helicorder/spectrum PNG rendering for the public dashboard.

Reads the locally-mirrored miniSEED (rsync'd onto the Dokku host from the Pi),
so it never touches the network or the acquisition box. Returns PNG bytes.
"""
import glob
import io
import math
import os
import tempfile
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
    min(st, key=lambda t: t.stats.starttime).trim(boundary, pad=True, fill_value=None)
    with tempfile.NamedTemporaryFile(suffix=".png") as tf:
        st.plot(type="dayplot", interval=interval,
                title=f"{st[0].id}   {start.date}",
                color=["k", "r", "b", "g"], one_tick_per_line=True,
                show_y_UTC_label=True, outfile=tf.name)
        tf.seek(0)
        return tf.read()


def spectrum_png(minutes=None):
    """Welch ASD (uV/sqrtHz) of the most recent continuous segment."""
    from scipy import signal
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = _latest()
    if not path:
        return None
    st = _load_day(path)
    st.detrend("demean")
    tr = max(st, key=lambda t: t.stats.npts)           # longest continuous segment
    fs = tr.stats.sampling_rate
    x = tr.data.astype(float) * UVPC
    if x.size < 512:
        return None
    f, pxx = signal.welch(x, fs=fs, nperseg=min(2048, x.size))
    asd = np.sqrt(pxx)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.loglog(f[1:], asd[1:], "k", lw=0.8, zorder=5)
    ax.set_xlim(f[1], fs / 2)

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
    ax.set_title(f"{tr.id}  Welch ASD  ({tr.stats.npts / fs / 60:.0f} min)")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
