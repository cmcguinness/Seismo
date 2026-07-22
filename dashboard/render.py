"""render.py — ObsPy helicorder/spectrum PNG rendering for the public dashboard.

Reads the locally-mirrored miniSEED (rsync'd onto the Dokku host from the Pi),
so it never touches the network or the acquisition box. Returns PNG bytes.
"""
import glob
import io
import math
import os
import threading
import time
from collections import Counter

import numpy as np

DATA = os.environ.get("SEISMO_DATA", "/data/data")
GAIN = int(os.environ.get("SEISMO_GAIN", "64"))
UVPC = (2.5 * 2 / (GAIN * (2 ** 23 - 1))) * 1e6      # microvolts per count
RING = os.environ.get("SEISMO_RING", "/data/seismo_live.npz")  # live ring, pulled Pi->pi5
SPEC_TTL = float(os.environ.get("SEISMO_SPECTRUM_TTL", "1800"))   # spectrum cache, 30 min


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
    tend = tr.stats.endtime
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
    fig.text(0.995, 0.005, f"data to {tend.strftime('%Y-%m-%d %H:%M')} UTC",
             ha="right", va="bottom", fontsize=7.5, color="#888")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


_spec_cache = {"png": None, "ts": 0.0}
_spec_lock = threading.Lock()


def spectrum_png_cached():
    """spectrum_png() memoized with a 30-min TTL. The Welch render re-parses the
    whole day-file and takes ~30 s on the pi5, so without this every visit (and
    every bounce around the app) would re-run it. Lock-guarded so concurrent
    first-hits after expiry don't all render -- one renders, the rest get the
    fresh result."""
    png = _spec_cache["png"]
    if png is not None and (time.time() - _spec_cache["ts"]) < SPEC_TTL:
        return png
    with _spec_lock:
        png = _spec_cache["png"]                 # re-check: another thread may have rendered
        if png is not None and (time.time() - _spec_cache["ts"]) < SPEC_TTL:
            return png
        png = spectrum_png()
        if png:
            _spec_cache["png"] = png
            _spec_cache["ts"] = time.time()
        return png


# --- event sparklines --------------------------------------------------------
# A tiny inline-SVG waveform around each detection, shown in the home page's
# detections table. Built from the mirrored miniSEED (1-15 Hz band, the same
# local-quake band the STA/LTA triggers on). Event windows are immutable, so
# each sparkline is built at most once and memoized; the heavy day-file load
# happens only when a NEW above-threshold detection first appears -- the common
# case (no new events) does zero I/O and the home route stays O(1).

SPARK_PRE = float(os.environ.get("SEISMO_SPARK_PRE", "8"))     # s of window before start
SPARK_POST = float(os.environ.get("SEISMO_SPARK_POST", "22"))  # s of window after start
SPARK_BUCKETS = int(os.environ.get("SEISMO_SPARK_BUCKETS", "150"))
SPARK_W, SPARK_H = 180, 40

_spark_cache = {}                 # start_iso -> svg string (or "" for no data)
_spark_lock = threading.Lock()


def _load_recent(n=2):
    """Last `n` day-files merged (micro-gaps bridged) into one Stream. A detection
    window can straddle the 00:00 UTC day-file rollover, so keep two."""
    files = sorted(glob.glob(os.path.join(DATA, "*.mseed")), key=os.path.getmtime)
    if not files:
        return None
    st = None
    for path in files[-n:]:
        s = _load_day(path)
        st = s if st is None else st + s
    if st is None or not len(st):
        return None
    st.merge(method=1, fill_value="interpolate")     # bridge the timing micro-gaps
    return st


def _build_spark_svg(st, start_iso):
    """Inline-SVG min/max envelope of the 1-15 Hz waveform in
    [start-PRE, start+POST]. Returns an <svg> string, or "" if the window holds
    no usable data (real gap, or pruned out of the archive)."""
    import obspy

    try:
        t0 = obspy.UTCDateTime(start_iso)
    except Exception:
        return ""
    seg = st.slice(t0 - SPARK_PRE, t0 + SPARK_POST).copy()
    if not len(seg):
        return ""
    seg.merge(method=1, fill_value="interpolate")
    tr = max(seg, key=lambda t: t.stats.npts)
    if tr.stats.npts < 20:
        return ""
    tr.detrend("demean")
    fs = float(tr.stats.sampling_rate)
    tr.filter("bandpass", freqmin=1.0, freqmax=min(15.0, fs / 2 * 0.99),
              corners=4, zerophase=True)
    x = np.nan_to_num(np.asarray(tr.data, float))
    if x.size < 2 or not np.any(x):
        return ""

    # bucket to columns; per-bucket (min,max) envelope. nb<=size, and idx spreads
    # evenly, so every bucket catches >=1 sample -> all finite.
    nb = int(min(SPARK_BUCKETS, x.size))
    idx = np.minimum(np.arange(x.size) * nb // x.size, nb - 1)
    lo = np.full(nb, np.inf)
    hi = np.full(nb, -np.inf)
    np.minimum.at(lo, idx, x)
    np.maximum.at(hi, idx, x)

    amp = max(float(np.max(np.abs(x))), 1e-9)
    yc = SPARK_H / 2.0
    sc = (SPARK_H / 2.0 * 0.90) / amp                 # 90% of half-height at peak
    xs = (np.arange(nb) + 0.5) * SPARK_W / nb
    top = " ".join(f"{xs[i]:.1f},{yc - hi[i] * sc:.1f}" for i in range(nb))
    bot = " ".join(f"{xs[i]:.1f},{yc - lo[i] * sc:.1f}" for i in range(nb - 1, -1, -1))
    x_on = SPARK_PRE / (SPARK_PRE + SPARK_POST) * SPARK_W   # trigger onset marker
    return (
        f'<svg viewBox="0 0 {SPARK_W} {SPARK_H}" width="{SPARK_W}" height="{SPARK_H}" '
        f'preserveAspectRatio="none" class="spark" role="img" '
        f'aria-label="waveform around the detection">'
        f'<line x1="0" y1="{yc:.0f}" x2="{SPARK_W}" y2="{yc:.0f}" '
        f'stroke="#e6e8eb" stroke-width="1"/>'
        f'<line x1="{x_on:.0f}" y1="0" x2="{x_on:.0f}" y2="{SPARK_H}" stroke="#dc322f" '
        f'stroke-width="1" stroke-dasharray="2 2" opacity="0.55"/>'
        f'<polygon points="{top} {bot}" fill="#2f6f6b" fill-opacity="0.85"/>'
        f'</svg>'
    )


def ensure_sparklines(starts):
    """Build+memoize sparklines for any of `starts` not already cached. Loads the
    mirrored day-file(s) at most once, and only when a detection new to the cache
    appears -- so the steady state (nothing new) does zero I/O. Lock-guarded so
    concurrent first-hits load once. An event whose data isn't mirrored yet is
    left uncached and retried on the next request."""
    import obspy

    starts = [s for s in starts if s]
    if all(s in _spark_cache for s in starts):
        return
    with _spark_lock:
        missing = [s for s in starts if s not in _spark_cache]
        if not missing:
            return
        st = _load_recent()
        if st is None:
            return
        t_end = max(t.stats.endtime for t in st)
        for s in missing:
            try:
                fresh = obspy.UTCDateTime(s) > t_end + 5     # window past mirrored data
            except Exception:
                fresh = False
            if fresh:
                continue                                     # not here yet -> retry later
            _spark_cache[s] = _build_spark_svg(st, s)
        if len(_spark_cache) > 300:                          # bound the memo
            for k in list(_spark_cache)[:-150]:
                _spark_cache.pop(k, None)


def event_sparkline(start_iso):
    """Cached inline-SVG sparkline for a detection, or "" if not built yet.
    Call ensure_sparklines() first to populate."""
    return _spark_cache.get(start_iso, "")


def live_ring_json():
    """Live strip-chart payload from the /dev/shm ring that the Pi mirrors and the
    seismo-live-pull service copies here (Pi->pi5). Served from pi5, so viewers
    never make the acquisition Pi transmit (which conducts noise into the ADC)."""
    import time
    try:
        age = time.time() - os.path.getmtime(RING)
        with np.load(RING) as d:
            counts = d["counts"].astype(float)
            fs = float(d["fs"])
            gain = int(d["gain"])
    except Exception:
        return {"uv": [], "pp": 0.0, "fs": 0.0, "gain": 0, "age": None}
    uvpc = (2.5 * 2 / (gain * (2 ** 23 - 1))) * 1e6
    uv = counts * uvpc
    if uv.size:
        uv = uv - uv.mean()
    return {"uv": [round(float(v), 2) for v in uv],
            "pp": float(np.ptp(uv)) if uv.size else 0.0,
            "fs": fs, "gain": gain, "age": round(age, 1)}
