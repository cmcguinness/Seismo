#!/usr/bin/env python3
"""eventcheck.py — did the station catch a catalog earthquake?

Give it a USGS event (origin time + epicenter + depth). It computes the
epicentral distance and P/S arrival times for our station, pulls the miniSEED,
windows around the predicted arrivals, band-passes out the microseism, and
plots raw + filtered with P/S markers — then prints a simple detection verdict
(signal-vs-noise in the P–S window).

Times: paste the USGS *local* time and it converts with --offset-hours
(default -7 = PDT). Epicenter/depth from the USGS page.

  python eventcheck.py --origin "2026-07-20T00:15:29" \
      --lat 38.824 --lon -122.812 --depth 2.8 --mag 0.7 --label "The Geysers"

Robust to the archive's mixed-rate/fragmented segments: it slices the window,
keeps the dominant sample rate, and merges that.

Needs the analysis venv:  analysis/.venv/bin/python eventcheck.py ...
"""
import argparse
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from helicorder import LOCAL_DATA, pull

# Station location — Oakmont, Santa Rosa (measured at the sensor site).
STA_LAT, STA_LON = 38.451817, -122.621049
STA_ELEV_M = 119.0   # above MSL; catalogue depths are from MSL, so it adds
# Local crustal P/S velocities (km/s). Vp is MEASURED at this station, not assumed:
# five confirmed events over 18.4-45.7 km give onset = dist/5.19 + 0.30 s with <=0.3 s
# residuals (2026-07-29, STATUS.md). Vp=6.0 predicted arrivals ~1.4 s early at 45 km.
VP, VS = 5.19, 3.00              # Vp/Vs≈1.73
T0_INTERCEPT = 0.30              # seconds; the fitted intercept of that same relation


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True, help="origin time, ISO (e.g. 2026-07-20T00:15:29)")
    ap.add_argument("--offset-hours", type=float, default=-7.0,
                    help="UTC offset of --origin (default -7 = PDT); UTC = origin - offset")
    ap.add_argument("--lat", type=float, required=True, help="epicenter latitude")
    ap.add_argument("--lon", type=float, required=True, help="epicenter longitude")
    ap.add_argument("--depth", type=float, default=8.0, help="hypocenter depth km")
    ap.add_argument("--mag", type=float, help="magnitude (label only)")
    ap.add_argument("--label", default="event", help="event name for the title")
    ap.add_argument("--stalat", type=float, default=STA_LAT)
    ap.add_argument("--stalon", type=float, default=STA_LON)
    ap.add_argument("--gain", type=int, default=64)
    ap.add_argument("--band", default="2,15", help="bandpass 'fmin,fmax' Hz")
    ap.add_argument("--pre", type=float, default=20.0, help="seconds before origin")
    ap.add_argument("--post", type=float, default=0.0, help="seconds after origin (0=auto)")
    ap.add_argument("--no-pull", action="store_true")
    args = ap.parse_args()

    from obspy import Stream, UTCDateTime, read

    origin = UTCDateTime(args.origin) - args.offset_hours * 3600.0     # -> UTC
    epi = haversine_km(args.stalat, args.stalon, args.lat, args.lon)
    hypo = math.hypot(epi, args.depth + STA_ELEV_M / 1000.0)
    # +T0_INTERCEPT on P: the measured relation is onset = dist/5.19 + 0.30 s (see the
    # VP comment above), and dropping the intercept drew every P marker 0.30 s EARLY,
    # which made real arrivals look systematically late on every plot (2026-08-12).
    tP, tS = hypo / VP + T0_INTERCEPT, hypo / VS
    post = args.post if args.post > 0 else tS + 40.0
    fmin, fmax = (float(x) for x in args.band.split(","))
    uvpc = (2.5 * 2 / (args.gain * (2 ** 23 - 1))) * 1e6

    print(f"{args.label}  M{args.mag}  origin {origin} UTC")
    print(f"  epicentral {epi:.1f} km, hypocentral {hypo:.1f} km, depth {args.depth} km")
    print(f"  predicted P +{tP:.1f}s, S +{tS:.1f}s (Vp {VP}, Vs {VS} km/s)")

    if not args.no_pull:
        pull("seismo.local")

    matches = sorted(LOCAL_DATA.glob(f"*.D.{origin.year}.{origin.julday:03d}.mseed"))
    if not matches:
        raise SystemExit(f"no day-file for {origin.year}.{origin.julday:03d} in {LOCAL_DATA}")
    st = read(str(matches[-1]))
    win = st.slice(origin - args.pre, origin + post)
    if not len(win):
        raise SystemExit("NO DATA in the event window (recorder gap at that time?)")
    # The archive is fragmented into many short segments by sub-second timing
    # micro-gaps. The old code split() the window and kept only the ONE segment
    # best overlapping the P-S window -- which discarded the adjacent fragments
    # holding the pre-event noise, so every event looked like it had a ~6s "gap"
    # over the P arrival (noise pp 0.0 -> bogus "NOT DETECTED"). Instead, bridge
    # the micro-gaps by interpolation into a single continuous trace.
    from collections import Counter
    dom = Counter(round(tr.stats.sampling_rate) for tr in win).most_common(1)[0][0]
    win = Stream([tr for tr in win if round(tr.stats.sampling_rate) == dom])
    win.merge(method=1, fill_value="interpolate")
    tr = max(win, key=lambda t: t.stats.npts)

    raw = tr.copy(); raw.detrend("demean")
    filt = tr.copy(); filt.detrend("demean")
    filt.filter("bandpass", freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    t = raw.times() + (raw.stats.starttime - origin)
    bp = filt.data * uvpc

    def pp(lo, hi):
        seg = bp[(t > lo) & (t < hi)]
        return float(np.ptp(seg)) if seg.size else 0.0
    noise, signal = pp(-args.pre, tP - 2), pp(tP - 1, tS + 20)
    ratio = signal / noise if noise else 0.0
    verdict = ("LIKELY DETECTED" if ratio > 2.5 else
               "AMBIGUOUS" if ratio > 1.5 else "NOT DETECTED (signal below floor)")
    print(f"  band {fmin}-{fmax} Hz: noise pp {noise:.1f} uV, P-S pp {signal:.1f} uV, "
          f"ratio {ratio:.2f} -> {verdict}")

    fig, (a1, a2) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))
    a1.plot(t, raw.data * uvpc, "k", lw=0.6); a1.set_ylabel("raw µV")
    mag = f"M{args.mag} " if args.mag is not None else ""
    a1.set_title(f"{tr.id}   {mag}{args.label} ({epi:.0f} km)   raw")
    a2.plot(t, bp, "b", lw=0.6); a2.set_ylabel(f"{fmin:g}-{fmax:g} Hz µV")
    # NOT "microseism removed": this station has essentially no microseism to remove.
    # The 4.5 Hz element is ~60 dB down at 0.07-0.15 Hz, and measurement agrees --
    # 0.454 uV in the 0.05-0.2 Hz band against 5.5 uV raw (2026-08-13). What the
    # filter actually discards here is mostly content ABOVE 15 Hz. That is why the
    # two panels look nearly identical, which is a property of the instrument, not
    # a bug -- so name the band and let the reader see it.
    a2.set_title(f"bandpass {fmin:g}-{fmax:g} Hz   ratio {ratio:.2f} -> {verdict}")
    for a in (a1, a2):
        a.axvline(0, color="g", ls="--"); a.axvline(tP, color="r", ls=":")
        a.axvline(tS, color="orange", ls=":"); a.grid(alpha=0.3)
    a2.set_xlabel(f"s after origin {origin.strftime('%H:%M:%S')} UTC   "
                  f"(green=origin  red=P+{tP:.1f}s  orange=S+{tS:.1f}s)")
    fig.tight_layout()
    out = LOCAL_DATA.parent / "eventcheck.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")
    import subprocess
    subprocess.run(["open", "-a", "Preview", str(out)], check=False)


if __name__ == "__main__":
    main()
