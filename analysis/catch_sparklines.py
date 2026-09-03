#!/usr/bin/env python3
"""catch_sparklines.py — a tiny envelope trace for every confirmed event.

WHY A SHARED SCALE. The obvious implementation normalises each sparkline to its own
peak, and it is wrong here: peak amplitude across the record spans 3.8 to 519.9 uV --
137x, 2.1 decades -- so a self-normalised M0.4 at 44 km would draw exactly like the M4.2
at 46 km. On a page whose entire argument is about amplitude and range, that is not
decoration, it is misinformation.

Every sparkline is therefore drawn against ONE log scale spanning the whole record. The
M4.2 towers over its neighbours, the marginal catches are visibly marginal, and scrolling
the log shows amplitude falling off with distance without a word of explanation.

Log rather than linear because linear would flatten everything below ~50 uV into a
straight line, which throws away 30 of the 35 events to flatter the five loudest.

Output: dashboard/catches/sparklines.json, {slug: [N ints 0-100]}. Small enough to inline
as SVG in the table -- no extra requests, no JS, crisp at any size, themeable.

    python analysis/catch_sparklines.py
"""
import glob
import json
import math
import os
import sys

import numpy as np
from obspy import Stream, UTCDateTime, read

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dashboard"))
import catches                                                   # noqa: E402

ARCHIVE = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "..", "dashboard", "catches", "sparklines.json")
UV = 2.5 * 2 / (64 * (2 ** 23 - 1)) * 1e6
BAND = (1.0, 15.0)
PRE, POST = 10.0, 40.0       # around the predicted P -- the SAME 50 s span the catch
                             # clips and images use, so a sparkline and the figure it
                             # links to show the same seconds.
                             #
                             # It started at 5/25 and that was too short for the far
                             # field: at 319 km Petrolia's Sn lands ~34 s after Pn, so a
                             # 30 s window cut off the event's actual peak and drew it
                             # SMALLER than events a fifth its size. A sparkline that
                             # misrepresents relative amplitude is worse than none, since
                             # the whole reason for a shared scale is that height means
                             # something.
N_POINTS = 96
SCALE_LO, SCALE_HI = 1.0, 600.0    # uV, the shared log scale for every event


def envelope_for(origin, tp):
    o = UTCDateTime(origin)
    hits = sorted(glob.glob(f"{ARCHIVE}/*.D.{o.year}.{o.julday:03d}.mseed"))
    if not hits:
        return None
    st = read(hits[-1], starttime=o + tp - PRE, endtime=o + tp + POST)
    try:
        st.merge(method=1, fill_value="interpolate")
    except Exception:
        rates = [t.stats.sampling_rate for t in st]
        keep = max(set(rates), key=rates.count)
        st = Stream([t for t in st if t.stats.sampling_rate == keep])
        st.merge(method=1, fill_value="interpolate")
    if not len(st):
        return None
    tr = max(st, key=lambda t: t.stats.npts)
    fs = float(tr.stats.sampling_rate)
    if tr.stats.npts < (PRE + POST) * fs * 0.6:
        return None
    from scipy import signal
    x = np.asarray(tr.data, float) * UV
    x -= np.median(x)
    sos = signal.butter(4, [BAND[0] / (fs / 2), min(BAND[1], fs / 2 * 0.95) / (fs / 2)],
                        "bandpass", output="sos")
    env = np.abs(signal.sosfilt(sos, x))
    n = min(len(env), int((PRE + POST) * fs))
    env = env[:n]
    # peak per output column: a sparkline should show the spike, not average it away
    edges = np.linspace(0, n, N_POINTS + 1).astype(int)
    cols = np.array([env[a:b].max() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
    lo, hi = math.log10(SCALE_LO), math.log10(SCALE_HI)
    h = (np.log10(np.maximum(cols, SCALE_LO)) - lo) / (hi - lo)
    return [int(round(float(v) * 100)) for v in np.clip(h, 0, 1)]


def main():
    out, miss = {}, 0
    for e in catches.EVENTS:
        slug = catches.slug_for(e.get("origin"))
        try:
            tp = float(e.get("tp_s") or 0)
        except (TypeError, ValueError):
            tp = 0.0
        v = envelope_for(e["origin"], tp)
        if v is None:
            miss += 1
            print(f"  no data: {slug}  {e.get('place','')[:32]}")
            continue
        out[slug] = v
        print(f"  {slug}  M{float(e.get('mag') or 0):<5.2f} peak col {max(v):>3d}/100  "
              f"{e.get('place','')[:30]}")
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"\n{len(out)} sparklines, {miss} without data -> "
          f"{os.path.relpath(OUT, os.path.join(HERE, '..'))} "
          f"({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
