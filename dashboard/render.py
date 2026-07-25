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
# Band for the live HUD's band-limited RMS: the local-quake band the station is
# tuned for. Broadband RMS is dominated by out-of-band sub-Hz tilt, so this is the
# figure that's comparable to the quoted noise floor (~0.7 uV settled).
LIVE_BAND = (float(os.environ.get("SEISMO_LIVE_HP", "1.0")),
             float(os.environ.get("SEISMO_LIVE_LP", "15.0")))
SPEC_TTL = float(os.environ.get("SEISMO_SPECTRUM_TTL", "1800"))   # spectrum cache, 30 min


def _load_day(path, starttime=None):
    """Read a day-file -> gap-split Stream, normalizing mixed sample rates
    (early archive has 55/57 sps segments; ObsPy won't merge across rates).

    `starttime` is passed to obspy.read so records before it are never decoded --
    decoding a full day-file costs ~45 s on the pi5, and the sparkline/character
    fill only ever needs the windows around recent detections."""
    import obspy

    st = obspy.read(path, starttime=starttime)
    if not len(st):
        return st              # nothing at/after starttime in this file
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
    which after de-mean is just a low-freq ramp -- rare and self-corrects hourly.)
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
    fig, ax = plt.subplots(figsize=(14, 7))     # 1400 px at dpi 100; covers the
    #                                             full-width card without upscaling
    ax.loglog(f[1:], asd[1:], "k", lw=1.0, zorder=5)
    # Floor at 0.05 Hz: below the microseism the 4.5 Hz geophone is ~60 dB down,
    # so anything lower is instrument self-noise, not ground motion. 0.05 (not 0.1)
    # keeps both microseism humps (primary ~0.05-0.1, secondary ~0.1-0.35).
    ax.set_xlim(0.05, fs / 2)

    # --- educational annotations ---
    tx = ax.get_xaxis_transform()          # x in data coords, y in axes fraction
    # Ocean microseism band -- drawn for ORIENTATION, not because we measure it. The
    # 4.5 Hz geophone is ~60 dB down here, so the summer microseism reaches the ADC at
    # ~10 nV, roughly 100x under our sub-Hz noise. Measured 2026-07-23: the sub-Hz
    # peaks are NARROW lines at 0.035/0.07/0.14/0.195 Hz -- a 28.6 s fundamental plus
    # harmonics, i.e. house machinery -- sitting on a smooth 1/f^0.8 instrument floor.
    # A real microseism would be a BROAD hump. The unqualified old label read as "this
    # is the microseism", which is exactly the misreading to avoid (Charles caught it).
    ax.axvspan(0.1, 0.35, color="#2aa198", alpha=0.08, lw=0)
    ax.text(0.185, 0.95, "ocean microseism\n(below our response —\nnot measured here)",
            transform=tx, ha="center", va="top", fontsize=7, color="#2aa198")
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

# --- character scoring (cultural-impulse flag) --------------------------------
# Thresholds set empirically 2026-07-22 from 127 logged triggers over 2 days (see
# CHARACTER.md). Envelope KURTOSIS + duration-above-25%-of-peak + peak/median SNR
# separate the classes cleanly; the two populations don't overlap on kurtosis
# (impulsive p10 45 vs sustained p90 26).
CHAR_KURT = float(os.environ.get("SEISMO_CHAR_KURT", "40"))     # envelope kurtosis
CHAR_DUR = float(os.environ.get("SEISMO_CHAR_DUR", "1.0"))      # s above 25% of peak
CHAR_SNR = float(os.environ.get("SEISMO_CHAR_SNR", "8"))        # peak / median envelope
CHAR_WEAK_SNR = float(os.environ.get("SEISMO_CHAR_WEAK_SNR", "6"))

MEMO_MAX = int(os.environ.get("SEISMO_SPARK_MEMO", "800"))   # entries before eviction
MEMO_KEEP = MEMO_MAX // 2                                    # retained after eviction

_spark_cache = {}                 # start_iso -> svg string (or "" for no data)
_char_cache = {}                  # start_iso -> character dict (or {} for no data)
_spark_lock = threading.Lock()


def _load_recent(n=2, starttime=None):
    """Last `n` day-files merged (micro-gaps bridged) into one Stream. A detection
    window can straddle the 00:00 UTC day-file rollover, so keep two. `starttime`
    limits decoding to the span the caller actually needs (see _load_day)."""
    files = sorted(glob.glob(os.path.join(DATA, "*.mseed")), key=os.path.getmtime)
    if not files:
        return None
    st = None
    for path in files[-n:]:
        s = _load_day(path, starttime=starttime)
        if not len(s):
            continue
        st = s if st is None else st + s
    if st is None or not len(st):
        return None
    st.merge(method=1, fill_value="interpolate")     # bridge the timing micro-gaps
    return st


def _event_trace(st, start_iso):
    """De-meaned single Trace covering [start-PRE, start+POST], or None if that
    window holds no usable data (real gap, or pruned out of the archive). Sliced
    once and shared by the sparkline and the character scorer."""
    import obspy

    try:
        t0 = obspy.UTCDateTime(start_iso)
    except Exception:
        return None
    seg = st.slice(t0 - SPARK_PRE, t0 + SPARK_POST).copy()
    if not len(seg):
        return None
    seg.merge(method=1, fill_value="interpolate")
    tr = max(seg, key=lambda t: t.stats.npts)
    if tr.stats.npts < 20:
        return None
    tr.detrend("demean")
    return tr


def _envelope_1_15(tr):
    """Smoothed (~0.2 s) absolute envelope of the 1-15 Hz band -- the local-quake
    band the trigger works in. Returns (env, fs)."""
    fs = float(tr.stats.sampling_rate)
    tb = tr.copy()
    tb.filter("bandpass", freqmin=1.0, freqmax=min(15.0, fs / 2 * 0.99),
              corners=4, zerophase=True)
    y = np.abs(np.nan_to_num(np.asarray(tb.data, float)))
    w = max(3, int(0.2 * fs))
    return np.convolve(y, np.ones(w) / w, mode="same"), fs


def _build_character(tr):
    """Score a detection's WAVEFORM SHAPE to flag probable cultural impulses.

    Metrics (all on the 1-15 Hz envelope):
      kurt -- envelope kurtosis. A footstep/door-thump is one spike in an
              otherwise quiet window -> very peaked; ambient wobble -> ~3-8.
      dur  -- seconds spent above 25% of peak. Thumps: <1 s. Quake coda: many s.
      snr  -- peak / median envelope.

    Verdict is deliberately SOFT ("impulsive"), never a hard drop: a *very local*
    earthquake is also impulsive and HF-rich, and this station has no confirmed
    quake yet to calibrate the positive class against (Phase 5 open). So this
    flags shape only -- it is not an earthquake/not-earthquake classifier.

    hf/flat are reported but NOT used in the verdict: measured over 127 real
    triggers they do NOT separate the classes -- the impulsive population came out
    LOWER in HF fraction (median 0.09) than the sustained one (0.41), i.e. these
    thumps are low-band-dominated, not broadband. The backlog's
    "score by HF fraction / spectral flatness" premise was wrong for this site.
    """
    env, fs = _envelope_1_15(tr)
    if env.size < int(5 * fs):
        return {}
    ip = int(np.argmax(env))
    pk = float(env[ip])
    if not np.isfinite(pk) or pk <= 0:
        return {}
    sd = float(env.std())
    kurt = float(np.mean(((env - env.mean()) / sd) ** 4)) if sd > 0 else 0.0
    dur = float((env > 0.25 * pk).sum() / fs)
    med = float(np.median(env))
    snr = pk / med if med > 0 else float("inf")

    # informational only (see docstring): spectral content of the impulse itself,
    # in a +/-1.5 s window around the envelope peak.
    hf = float("nan")
    try:
        from scipy.signal import welch
        nyq = fs / 2
        a, b = max(0, ip - int(1.5 * fs)), min(env.size, ip + int(1.5 * fs))
        th = tr.copy()
        th.filter("highpass", freq=1.0, corners=2, zerophase=True)
        sig = np.nan_to_num(np.asarray(th.data, float))[a:b]
        if sig.size >= int(0.5 * fs):
            f, p = welch(sig, fs=fs, nperseg=int(min(sig.size, fs)))
            bnd = (f >= 1.0) & (f < nyq * 0.98)
            if p[bnd].sum() > 0:
                hf = float(p[bnd][f[bnd] >= 12.0].sum() / p[bnd].sum())
    except Exception:
        pass

    if kurt >= CHAR_KURT or (dur <= CHAR_DUR and snr >= CHAR_SNR):
        label, cls = "impulsive", "cultural"
    elif snr < CHAR_WEAK_SNR:
        label, cls = "near-threshold", "weak"
    else:
        label, cls = "sustained", "plain"
    return {"kurt": round(kurt, 1), "dur": round(dur, 2), "snr": round(snr, 1),
            "hf": None if not np.isfinite(hf) else round(hf, 3),
            "label": label, "cls": cls}


def _build_spark_svg(tr):
    """Inline-SVG min/max envelope of the 1-15 Hz waveform in
    [start-PRE, start+POST]. Returns an <svg> string, or "" if the window holds
    no usable data."""
    fs = float(tr.stats.sampling_rate)
    tr = tr.copy()
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
    """Build+memoize the sparkline AND character score for any of `starts` not
    already cached. Loads the mirrored day-file(s) at most once, and only when a
    detection new to the cache appears -- so the steady state (nothing new) does
    zero I/O. Both products come from ONE slice per event, so scoring adds no I/O.
    Lock-guarded so concurrent first-hits load once. An event whose data isn't
    mirrored yet is left uncached and retried on the next request."""
    import obspy

    starts = [s for s in starts if s]
    if all(s in _spark_cache for s in starts):
        return
    with _spark_lock:
        missing = [s for s in starts if s not in _spark_cache]
        if not missing:
            return
        # Decode only from the earliest window we need. Without this the fill
        # re-parsed two FULL day-files per pass; when the trigger misbehaves and
        # new detections appear every few seconds, the cache is never complete, so
        # every page load spawned another full-archive parse -> periodic 100% CPU.
        earliest = None
        for s in missing:
            try:
                t = obspy.UTCDateTime(s)
            except Exception:
                continue
            earliest = t if earliest is None else min(earliest, t)
        st = _load_recent(starttime=None if earliest is None
                          else earliest - SPARK_PRE - 60)
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
            tr = _event_trace(st, s)
            _spark_cache[s] = _build_spark_svg(tr) if tr is not None else ""
            _char_cache[s] = _build_character(tr) if tr is not None else {}
        # Bound the memo, but keep it comfortably ABOVE the most rows the table can
        # ask for (app._recent_events max_rows=250). If the bound is below the
        # request size the cache THRASHES: every call evicts entries it is about to
        # be asked for again, so each request re-loads the day-files (~90 s for a
        # 2-day archive). Evict oldest-by-event-time, not insertion order.
        if len(_spark_cache) > MEMO_MAX:
            for k in sorted(_spark_cache)[:-MEMO_KEEP]:
                _spark_cache.pop(k, None)
                _char_cache.pop(k, None)


_fill_thread = None


def ensure_sparklines_async(starts):
    """Kick the sparkline/character fill onto a BACKGROUND thread and return at once.

    The fill's cost is dominated by parsing the mirrored day-files (~90 s for a
    2-day archive), and uvicorn serves this app on a single-threaded event loop --
    so doing it inline made a cold container hang the public home page for ~90 s
    AND stall the 300 ms /live-data polls behind it. Same rule as the helicorder:
    heavy work never sits on the request path. Un-built rows render as an empty
    waveform cell + em-dash badge and fill in on a later load."""
    global _fill_thread
    starts = [s for s in starts if s]
    if not starts or all(s in _spark_cache for s in starts):
        return
    if _fill_thread is not None and _fill_thread.is_alive():
        return                                    # a fill is already running
    _fill_thread = threading.Thread(target=ensure_sparklines, args=(starts,),
                                    daemon=True)
    _fill_thread.start()


def event_sparkline(start_iso):
    """Cached inline-SVG sparkline for a detection, or "" if not built yet.
    Call ensure_sparklines() first to populate."""
    return _spark_cache.get(start_iso, "")


def event_character(start_iso):
    """Cached character score for a detection ({} if not built yet). Keys:
    label/cls/kurt/dur/snr/hf -- see _build_character."""
    return _char_cache.get(start_iso, {})


def live_ring_json():
    """Live strip-chart payload from the /dev/shm ring that the Pi mirrors and the
    seismo-live-pull service copies here (Pi->pi5). Served from pi5, so viewers
    never make the acquisition Pi transmit (which conducts noise into the ADC)."""
    import time
    try:
        mtime = os.path.getmtime(RING)
        with np.load(RING) as d:
            counts = d["counts"].astype(float)
            fs = float(d["fs"])
            gain = int(d["gain"])
            # t_end = UTC epoch of the newest sample, stamped by the station's
            # live_publisher. Older rings lack it -> fall back to our copy's
            # mtime (close enough: the pull runs every 3 s).
            t_end = float(d["t_end"]) if "t_end" in d.files else mtime
        age = time.time() - t_end
    except Exception:
        return {"uv": [], "pp": 0.0, "fs": 0.0, "gain": 0, "age": None, "t_end": None}
    uvpc = (2.5 * 2 / (gain * (2 ** 23 - 1))) * 1e6
    uv = counts * uvpc
    if uv.size:
        uv = uv - uv.mean()
    return {"uv": [round(float(v), 2) for v in uv],
            "pp": float(np.ptp(uv)) if uv.size else 0.0,
            "rms": round(float(np.sqrt(np.mean(uv * uv))), 2) if uv.size else 0.0,
            "rms_band": _band_rms_cached(uv, fs, t_end),
            "spec": live_spectrum(uv, fs, t_end),
            "fs": fs, "gain": gain, "age": round(age, 1), "t_end": t_end}


SPEC_BINS = int(os.environ.get("SEISMO_LIVE_SPEC_BINS", "110"))   # log-spaced output bins
SPEC_FMIN = float(os.environ.get("SEISMO_LIVE_SPEC_FMIN", "0.2"))  # 30 s window -> no
                                                                   # resolution below ~0.15 Hz
_spec_live_memo = {"t_end": None, "val": None}


def live_spectrum(uv, fs, t_end):
    """Amplitude spectral density (µV/√Hz) of the live ring, log-binned for plotting.

    Welch over the 30 s window: nperseg ~8 s gives ~0.12 Hz resolution with ~6
    averages -- enough to see the 4.5 Hz corner and the noise floor without the
    estimate being pure variance. Returned as {f, asd} on SPEC_BINS log-spaced
    bins so the payload stays small at 300 ms polling.

    Memoized on t_end for the same reason as _band_rms_cached: the ring only
    changes every ~3 s, so this runs ~10x less often than it is requested and N
    viewers cost nothing extra."""
    if _spec_live_memo["t_end"] == t_end:
        return _spec_live_memo["val"]
    val = None
    try:
        from scipy.signal import welch
        nyq = fs / 2
        nper = int(min(uv.size, 2 ** int(math.log2(max(64.0, fs * 8)))))
        if uv.size >= 256 and nper >= 64:
            f, p = welch(uv, fs=fs, nperseg=nper)
            asd = np.sqrt(np.maximum(p, 0.0))
            fmax = nyq * 0.98
            keep = (f >= SPEC_FMIN) & (f <= fmax) & (asd > 0)
            if keep.sum() > 4:
                fk, ak = f[keep], asd[keep]
                # average onto log-spaced bins (raw Welch bins are linear, so the
                # low end would otherwise be one point per bin and the high end 100s)
                edges = np.logspace(math.log10(fk[0]), math.log10(fk[-1]),
                                    SPEC_BINS + 1)
                idx = np.clip(np.digitize(fk, edges) - 1, 0, SPEC_BINS - 1)
                fo, ao = [], []
                for b in range(SPEC_BINS):
                    m = idx == b
                    if m.any():
                        fo.append(round(float(fk[m].mean()), 4))
                        ao.append(round(float(ak[m].mean()), 4))
                val = {"f": fo, "asd": ao}
    except Exception:
        val = None
    _spec_live_memo.update(t_end=t_end, val=val)
    return val


_band_rms_memo = {"t_end": None, "val": None}


def _band_rms_cached(uv, fs, t_end):
    """RMS of the ring band-limited to LIVE_BAND, or None if it can't be computed.

    This is the number that's comparable to the noise-floor figures we quote
    (broadband RMS is dominated by out-of-band sub-Hz tilt). Memoized on t_end
    because the ring only refreshes every ~3 s while each viewer polls at 300 ms --
    so the filter runs ~10x less often than it's asked for, and N viewers cost
    nothing extra."""
    if _band_rms_memo["t_end"] == t_end:
        return _band_rms_memo["val"]
    val = None
    try:
        from scipy.signal import butter, sosfiltfilt
        nyq = fs / 2
        hi = min(LIVE_BAND[1], nyq * 0.98)
        if uv.size > 30 and 0 < LIVE_BAND[0] < hi:
            sos = butter(4, [LIVE_BAND[0] / nyq, hi / nyq], btype="band", output="sos")
            y = sosfiltfilt(sos, uv)
            val = round(float(np.sqrt(np.mean(y * y))), 2)
    except Exception:
        val = None
    _band_rms_memo.update(t_end=t_end, val=val)
    return val
