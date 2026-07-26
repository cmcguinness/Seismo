#!/usr/bin/env python3
"""heli_build.py — precompute the helicorder envelope: miniSEED -> per-interval npz.

The dashboard used to re-parse and re-plot the whole growing day-file on every
request. This is the INGEST half of the fix: once per data pull, reduce each
15-minute wall-clock interval to a fixed-width (min, max) envelope -- one pair
per output pixel column -- and bank it as a small npz. The renderer then never
touches miniSEED; it just stacks these envelopes into a drum plot.

Design (see dashboard/HELICORDER.md):
  - Intervals are clock-aligned to :00/:15/:30/:45. Each file holds NPIX pairs.
  - Values are de-meaned RAW COUNTS (float32); the drum scales by sigma, so the
    counts->uV factor cancels and the gain is irrelevant here.
  - A pixel bucket with no samples (real gap, or the still-filling current
    interval) is NaN -> the renderer leaves it blank.
  - sigma is the interval's RMS (de-meaned); the renderer's global scale is
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

# Envelopes are KEPT back to the start of the current acquisition epoch so the
# /history page can render any past window. Earlier epochs are deliberately out
# of scope: the archive before this ran at 57/60 sps through a different analog
# front end, so those drums are not comparable to today's and putting them behind
# the same date picker would invite exactly that mistake.
#
# 2026-07-25T23:39:01Z = the first 100 sps record (see STATUS.md "SWITCHED TO
# 100 sps"); 23:45 is the first fully-covered 15-min interval.
EPOCH_START = os.environ.get("SEISMO_EPOCH_START", "2026-07-25T23:45:00Z")


def epoch_start_ts():
    """EPOCH_START as epoch seconds, snapped down to an interval boundary."""
    import datetime
    dt = datetime.datetime.fromisoformat(EPOCH_START.replace("Z", "+00:00"))
    return dt.timestamp() // INTERVAL_S * INTERVAL_S


def _load_day(path, starttime=None):
    """miniSEED day-file -> list of contiguous single-rate traces (gaps blank).

    Mirrors analysis/helicorder.load_day: normalize the early archive's mixed
    sample rates, heal the ~ms per-block overlaps (merge), then split so only
    real gaps remain as breaks.

    `starttime` is passed through to obspy.read so records before the drum's
    window are never decoded. This matters a lot: the worker re-runs on every
    data change (~1/min from the rsync timer), and decoding two FULL day-files
    took ~91 s -- longer than the interval that re-triggers it, which pegged a
    core permanently. Reading only the window makes a cycle a few seconds.
    """
    import obspy

    st = obspy.read(str(path), starttime=starttime)
    if not len(st):
        return st            # file lies entirely before the window -> nothing to do
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

    vals are de-meaned counts. Returns (mins, maxs) float32[NPIX], NaN where a
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
    # Load the last TWO day-files and combine. A 4 h window can straddle the 00:00
    # UTC rollover, and the pre-midnight interval's tail minute (23:59->00:00) lives
    # in the PRIOR day-file. Loading only files[-1] froze the 23:45 row ~1 min short
    # once the recorder rolled to the new file (its samples were no longer loaded, so
    # the interval could never fill or mark complete). A 4 h window touches at most
    # two day-files, so the last two always cover it.
    #
    # Read ONLY the window: a header-only scan gives the archive end cheaply, then
    # each file is decoded from the window start. Decoding the files in full cost
    # ~91 s/cycle and pegged a core (see _load_day).
    import obspy

    hdr = obspy.read(files[-1], headonly=True)
    if not len(hdr):
        return 0
    newest = max(t.stats.endtime for t in hdr)
    # one extra interval of margin so the first row isn't filter-clipped
    win_start = obspy.UTCDateTime(
        (newest.timestamp - hours * 3600) // INTERVAL_S * INTERVAL_S - INTERVAL_S)
    st = None
    for path in files[-2:]:
        s = _load_day(path, starttime=win_start)
        if not len(s):
            continue                      # file lies entirely before the window
        st = s if st is None else st + s
    if st is None or not len(st):
        return 0
    if HP_HZ > 0:                     # knock down tilt/drift before enveloping
        st.detrend("demean")
        st.filter("highpass", freq=HP_HZ, corners=2, zerophase=True)

    latest = max(t.stats.endtime.timestamp for t in st)
    first_t0 = (latest - hours * 3600) // INTERVAL_S * INTERVAL_S
    last_t0 = latest // INTERVAL_S * INTERVAL_S
    written = _write_intervals(st, heli_dir, first_t0, last_t0, latest)
    # Prune only what predates the current epoch. Everything inside it is kept for
    # /history (~20 KB per interval, ~2 MB/day -- nothing next to 44 MB/day of
    # miniSEED), so the live cycle no longer deletes the window behind it.
    _prune(heli_dir, epoch_start_ts())
    return written


def _write_intervals(st, heli_dir, first_t0, last_t0, latest):
    """Envelope every 15-min interval in [first_t0, last_t0] from an already
    filtered Stream, writing one npz each. Returns the number written.

    Shared by the live `build()` and the one-shot `backfill()` so both produce
    byte-identical files -- a history window must not look different from the
    live drum that scrolled past the same minutes.
    """
    # collect every trace's (timestamp, count) once; bucket per interval below
    all_t = np.concatenate([t.times("timestamp") for t in st])
    all_v = np.concatenate([t.data.astype(np.float64) for t in st])
    written = 0
    t0 = first_t0
    while t0 <= last_t0:
        path = os.path.join(heli_dir, _fname(t0))
        # Skip only intervals already built with FULL coverage. An interval built
        # while still current is partial (data ran only to `latest`, up to ~1 min
        # short of its end); it must be rebuilt once `latest` passes its end or it
        # freezes truncated. Files predating the `complete` flag read incomplete
        # -> rebuilt once.
        if os.path.exists(path) and _is_complete(path):
            t0 += INTERVAL_S
            continue
        sel = (all_t >= t0) & (all_t < t0 + INTERVAL_S)
        v = all_v[sel]
        if v.size:
            v = v - v.mean()                      # de-mean this interval
            mins, maxs = _envelope(v, all_t[sel], t0)
            sigma = float(np.sqrt(np.mean(v * v)))       # sample RMS (kept for reference)
            # `env` = typical single-sided envelope excursion actually DRAWN per pixel
            # (median |min|,|max|). The renderer scales on this, not sigma, so the
            # noise band's on-screen thickness is what we target -- sigma undershoots
            # because a pixel's min/max spans several sigma of spiky noise.
            env = float(np.nanmedian(np.maximum(np.abs(mins), np.abs(maxs))))
            complete = latest >= t0 + INTERVAL_S  # data runs past the interval end
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:      # file handle -> savez won't append .npz
                np.savez(fh, mins=mins, maxs=maxs,
                         sigma=np.float32(sigma), env=np.float32(env),
                         t0=np.float64(t0), complete=np.bool_(complete),
                         npix=np.int32(NPIX), interval_s=np.int32(INTERVAL_S))
            os.replace(tmp, path)
            written += 1
        t0 += INTERVAL_S
    return written


def backfill(data_dir=DATA, heli_dir=HELI, t_from=None, t_to=None):
    """One-shot: build every missing interval from `t_from` to `t_to`, day-file by
    day-file. Defaults to the whole current epoch up to now.

    Separate from build() because it is deliberately expensive (it decodes whole
    day-files) and must never run on the live 20 s cycle -- run it once by hand
    after a deploy, or after a gap is healed by the collector's backfill.
    """
    import obspy

    os.makedirs(heli_dir, exist_ok=True)
    t_from = epoch_start_ts() if t_from is None else t_from
    total = 0
    for path in sorted(glob.glob(os.path.join(data_dir, "*.mseed"))):
        try:
            hdr = obspy.read(path, headonly=True)
        except Exception as e:
            print(f"  skip {os.path.basename(path)}: {e}", flush=True)
            continue
        if not len(hdr):
            continue
        f_end = max(t.stats.endtime.timestamp for t in hdr)
        f_start = min(t.stats.starttime.timestamp for t in hdr)
        if f_end <= t_from or (t_to is not None and f_start >= t_to):
            continue                                  # file lies outside the range
        st = _load_day(path, starttime=obspy.UTCDateTime(max(f_start, t_from)))
        if not len(st):
            continue
        if HP_HZ > 0:
            st.detrend("demean")
            st.filter("highpass", freq=HP_HZ, corners=2, zerophase=True)
        latest = max(t.stats.endtime.timestamp for t in st)
        first = max(f_start, t_from) // INTERVAL_S * INTERVAL_S
        last = (latest if t_to is None else min(latest, t_to)) // INTERVAL_S * INTERVAL_S
        n = _write_intervals(st, heli_dir, first, last, latest)
        total += n
        print(f"  {os.path.basename(path)}: +{n} interval(s)", flush=True)
    _prune(heli_dir, epoch_start_ts())
    return total


def _is_complete(path):
    """True if the interval file was built with data covering its full span (so it
    never needs rebuilding). Missing/legacy files without the flag read False."""
    try:
        with np.load(path) as d:
            return bool(d["complete"])
    except Exception:
        return False


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
    args = [a for a in sys.argv[1:] if a != "--backfill"]
    data = args[0] if len(args) > 0 else DATA
    heli = args[1] if len(args) > 1 else HELI
    if "--backfill" in sys.argv:
        print(f"backfilling {heli} from {EPOCH_START} ...", flush=True)
        n = backfill(data, heli)
    else:
        n = build(data, heli)
    print(f"built/updated {n} interval file(s) in {heli}")
