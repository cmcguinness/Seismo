#!/usr/bin/env python3
"""heli_build.py — precompute the helicorder envelope: miniSEED -> per-interval npz.

The dashboard used to re-parse and re-plot the whole growing day-file on every
request. This is the INGEST half of the fix: once per data pull, reduce each
15-minute wall-clock interval to a fixed-width (min, max) envelope -- one pair
per output pixel column -- and bank it as a small npz. The renderer then never
touches miniSEED; it just stacks these envelopes into a drum plot.

Design (see dashboard/HELICORDER.md):
  - Intervals are clock-aligned to :00/:15/:30/:45. Each file holds NPIX pairs.
  - Values are demeaned RAW COUNTS (float32); the drum scales by sigma, so the
    counts->uV factor cancels and the gain is irrelevant here.
  - A pixel bucket with no samples (real gap, or the still-filling current
    interval) is NaN -> the renderer leaves it blank.
  - sigma is the interval's RMS (demeaned); the renderer's global scale is
    keyed to the median sigma across retained intervals.
  - Completed intervals are immutable, so we skip ones already on disk; only the
    current partial interval is rebuilt each run. Files older than HOURS (by
    mtime) are pruned.

Ingest uses obspy (already a dashboard dep) because it handles the archive's
mixed-rate early segments and per-block overlaps cleanly. The RENDERER stays
obspy-free by design.
"""
import glob
import os
import sys
from collections import Counter

import numpy as np

NPIX = int(os.environ.get("SEISMO_HELI_NPIX", "1835"))   # plot-area width in px
INTERVAL_S = int(os.environ.get("SEISMO_HELI_INTERVAL", "900"))   # 15 min
HOURS = float(os.environ.get("SEISMO_HELI_HOURS", "4"))
HP_HZ = float(os.environ.get("SEISMO_HELI_HP", "1.0"))   # high-pass corner; 0 disables.
                                                         # Kills slow tilt/drift that
                                                         # otherwise swamps the drum
                                                         # (and microseism); keeps the
                                                         # 1-15 Hz local-quake band.
DATA = os.environ.get("SEISMO_DATA", "/data/data")
HELI = os.environ.get("SEISMO_HELI", "/data/heli")


def _load_day(path):
    """miniSEED day-file -> list of contiguous single-rate traces (gaps blank).

    Mirrors analysis/helicorder.load_day: normalize the early archive's mixed
    sample rates, heal the ~ms per-block overlaps (merge), then split so only
    real gaps remain as breaks.
    """
    import obspy

    st = obspy.read(str(path))
    dom = Counter(round(t.stats.sampling_rate) for t in st).most_common(1)[0][0]
    off = [t for t in st if round(t.stats.sampling_rate) != dom]
    if off:
        for t in off:
            t.resample(float(dom))
        for t in st:
            t.data = t.data.astype("float64")
    st.merge(method=1)
    return st.split()


def _fname(t0):
    """t0 (epoch seconds, interval-aligned) -> heli.YYYY.JJJ.HHMM.npz."""
    import datetime
    dt = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc)
    return f"heli.{dt.year}.{dt.timetuple().tm_yday:03d}.{dt:%H%M}.npz"


def _envelope(vals, times, t0):
    """Reduce (vals, times) inside [t0, t0+INTERVAL_S) to NPIX (min,max) pairs.

    vals are demeaned counts. Returns (mins, maxs) float32[NPIX], NaN where a
    pixel bucket caught no samples.
    """
    idx = ((times - t0) / INTERVAL_S * NPIX).astype(int)
    ok = (idx >= 0) & (idx < NPIX)
    idx, v = idx[ok], vals[ok]
    mins = np.full(NPIX, np.inf, dtype=np.float64)
    maxs = np.full(NPIX, -np.inf, dtype=np.float64)
    np.minimum.at(mins, idx, v)
    np.maximum.at(maxs, idx, v)
    mins[np.isinf(mins)] = np.nan
    maxs[np.isinf(maxs)] = np.nan
    return mins.astype(np.float32), maxs.astype(np.float32)


def build(data_dir=DATA, heli_dir=HELI, hours=HOURS):
    """(Re)build interval envelopes covering the last `hours`, then prune."""
    os.makedirs(heli_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(data_dir, "*.mseed")), key=os.path.getmtime)
    if not files:
        return 0
    st = _load_day(files[-1])
    if not len(st):
        return 0
    if HP_HZ > 0:                     # knock down tilt/drift before enveloping
        st.detrend("demean")
        st.filter("highpass", freq=HP_HZ, corners=2, zerophase=True)

    latest = max(t.stats.endtime.timestamp for t in st)
    # collect every trace's (timestamp, count) once; bucket per interval below
    all_t = np.concatenate([t.times("timestamp") for t in st])
    all_v = np.concatenate([t.data.astype(np.float64) for t in st])

    first_t0 = (latest - hours * 3600) // INTERVAL_S * INTERVAL_S
    last_t0 = latest // INTERVAL_S * INTERVAL_S
    written = 0
    t0 = first_t0
    while t0 <= last_t0:
        path = os.path.join(heli_dir, _fname(t0))
        is_current = (t0 == last_t0)
        if os.path.exists(path) and not is_current:
            t0 += INTERVAL_S
            continue          # completed intervals are immutable
        sel = (all_t >= t0) & (all_t < t0 + INTERVAL_S)
        v = all_v[sel]
        if v.size:
            v = v - v.mean()                      # demean this interval
            mins, maxs = _envelope(v, all_t[sel], t0)
            sigma = float(np.sqrt(np.mean(v * v)))       # sample RMS (kept for reference)
            # `env` = typical single-sided envelope excursion actually DRAWN per pixel
            # (median |min|,|max|). The renderer scales on this, not sigma, so the
            # noise band's on-screen thickness is what we target -- sigma undershoots
            # because a pixel's min/max spans several sigma of spiky noise.
            env = float(np.nanmedian(np.maximum(np.abs(mins), np.abs(maxs))))
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:      # file handle -> savez won't append .npz
                np.savez(fh, mins=mins, maxs=maxs,
                         sigma=np.float32(sigma), env=np.float32(env),
                         t0=np.float64(t0),
                         npix=np.int32(NPIX), interval_s=np.int32(INTERVAL_S))
            os.replace(tmp, path)
            written += 1
        t0 += INTERVAL_S

    _prune(heli_dir, first_t0)
    return written


def _fname_t0(path):
    """heli.YYYY.JJJ.HHMM.npz -> interval-start epoch seconds (UTC)."""
    import datetime
    _, year, jjj, hhmm, _ = os.path.basename(path).split(".")
    dt = (datetime.datetime(int(year), 1, 1, int(hhmm[:2]), int(hhmm[2:]),
                            tzinfo=datetime.timezone.utc)
          + datetime.timedelta(days=int(jjj) - 1))
    return dt.timestamp()


def _prune(heli_dir, cutoff_t0):
    """Delete interval files whose interval START is before cutoff_t0. Keyed on
    the interval time in the filename, NOT file mtime -- a bulk rebuild writes
    every file 'now', so mtime can't distinguish old intervals from fresh ones."""
    for p in glob.glob(os.path.join(heli_dir, "heli.*.npz")):
        try:
            if _fname_t0(p) < cutoff_t0:
                os.remove(p)
        except Exception:
            pass


if __name__ == "__main__":
    data = sys.argv[1] if len(sys.argv) > 1 else DATA
    heli = sys.argv[2] if len(sys.argv) > 2 else HELI
    n = build(data, heli)
    print(f"built/updated {n} interval file(s) in {heli}")
